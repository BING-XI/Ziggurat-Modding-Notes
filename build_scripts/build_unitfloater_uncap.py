#!/usr/bin/env python3
r"""Editor Unit Floater: uncap the 160-unit "All" tab, and give the race floater its type tabs.

THE PROBLEM
-----------
`Release/Unitres.pfs` holds **179** unit records. The editor's Unit Floater "All" tab shows only
**160**, so 19 units cannot be placed on a map at all. Confirmed by counting the .pfs this session.

WHY 160 -- `ImageLib.TCustomImageDrawGrid.UpdateDimensions @0x55214D24` (ILPACK.dpl), disassembled:

    55214D27  mov al,[ebx+0x1C0]      ; GrowDirection
    55214D2D  dec al / je 55214D37    ; 1 = ilHorizontal -> SetColCount((RowCount + Count) div RowCount)
    55214D33  dec al / je 55214D5E    ; 2 = ilVertical   -> SetRowCount((ColCount + Count) div ColCount)
    55214D35  jmp 55214D83            ; 0 = ilNone -> no-op

With `ilHorizontal`: cols = (20 + 179) div 20 = 9, clamped to `MaxColCount` 8; **RowCount is never
written on that arm**, so it stays at the designer's 20. 8 x 20 = 160.
With `ilVertical`:   rows = (8 + 179) div 8 = **23**, and `MaxRowCount` is **0**, which disables the
clamp entirely (`SetRowCount @0x55214F50`: `test ecx,ecx / je skip`). Columns stay pinned at 8
because `MinColCount == MaxColCount == 8`. 8 x 23 = 184 cells, all 179 units reachable.

⭐ The DFM already ships the target idiom on the sibling grid: `HeroControlGrid` is
`GrowDirection = ilVertical` with `MaxRowCount 0`. **Do not touch that one.**
⭐ And it is future-proof: `MaxRowCount 0` means adding more units later needs no further patch.

PATCH A -- the cap (DFM, length-neutral)
----------------------------------------
One contiguous 56-byte run inside the `TUnitFloater` DFM, at DFM-relative `+0x84C`:

    OLD  0d "GrowDirection" 07 0c "ilHorizontal"  0b "MinRowCount" 02 04  0b "MinColCount" 02 08
    NEW  0d "GrowDirection" 07 0a "ilVertical"    0b "MinRowCount" 03 04 00  0b "MinColCount" 03 08 00

`ilVertical` is 2 chars shorter than `ilHorizontal`. Those 2 bytes are paid back by re-encoding
`MinRowCount` and `MinColCount` from `vaInt8` (`0x02`, one payload byte) to `vaInt16` (`0x03`, two)
-- **their values are unchanged, 4 and 8**. The same form already encodes `ClientHeight` and
`ClientWidth` as `vaInt16`, so the form is valid Delphi either way.

⚠ **Length-neutral is the whole point.** The DFM is exactly 0xC8A bytes with **zero slack**
(`walk().consumed == 0xC8A`), and the next resource begins 2 alignment bytes later. A growing edit
would be impossible. Because the total is unchanged, the resource `Size` and `OffsetToData` are
NOT touched, there is no tail shift, and every byte from `+0x884` (`MaxRowCount`) on is identical.

⚠ Do not use `MaxValue` as filler -- `build_editor_spinners.py` scans the whole file for
`\x08MaxValue\x02<i8>` and this DFM has none today. Keep it that way.
⚠ Do not zero `MinColCount`: the `ilVertical` arm does `idiv` on `GetColCount`.
⚠ Do not raise `MaxColCount` to 0 instead (the tempting one-byte alternative): 9 columns x 48px =
432px into a ~407px viewport with no horizontal scrollbar, so column 9 would be unreachable -- and
it breaks again at 200 units.

PATCH B -- the race floater's type tabs (code, one byte)
--------------------------------------------------------
`TRaceResourceEditForm.FormCreate @0x00411730` configures the shared floater for the race context
and switches the category tabs OFF. Three adjacent flag stores, verified live:

    004117D5  mov eax,[eax+0x140]     ; -> the TUnitSelectionControl
    004117DB  c6 40 4b 01             ; +0x4B All tab       ON
    004117DF  c6 40 49 00             ; +0x49 race tabs     OFF
    004117E3  c6 40 4a 00             ; +0x4A category tabs OFF   <-- flip this immediate to 1

`AoWE.TUnitSelectionControl.UpdateSelection @0x5574DCC4` reads all three in sequence
(`0x5574DD05` +0x4B, `0x5574DD74` +0x4A, `0x5574DDE8` +0x49), each gating one tab group. The
`+0x4A` group is built from a `TUnitCategoryList`, and the categories are the unit-type enum we
already document in `re_tools/pfs.py` (Unitres tag 0x15: 0 = humanoid/racial, 1 = monster/creature,
2 = machine) -- i.e. the Humanoid / Creatures / Siege tabs.

⭐ Inioch gives this site as VA `0x4117E3` in HIS editor build, and it is **byte-identical at the
identical address in ours** -- as is the floater global `[0x42F100]` he cites. Our `AoWDevEd.exe`
and his `AoWDevX.exe` are evidently the same build, so his EDITOR findings port 1:1. That is NOT
true of his AoWEPACK work, where standing rule 1 applies.

⚠ The site is located **by pattern, not by address**: the three adjacent stores
`c6404b01 c6404900 c6404a00` occur exactly ONCE in the editor (checked), which pins the block
without hard-coding a VA. That mattered when this script had two targets and is worth keeping --
`AoWDevEd.exe` and the retired `AoWEd.exe` are near-identical builds offset by a few bytes, so any
address taken from one is a coin-flip in the other. Both carry the identical block, at
`AoWDevEd` VA `0x004117E3` / file `0x010BDB` and `AoWEd` VA `0x004117D3` / file `0x010BCB`.
(`AoWEd.exe` does have `TRaceResourceEditForm`, contrary to an earlier draft of this file.)

================================================================================
⚠⚠ THE EDITOR EXE TRAP -- an editor patch is TWO steps
================================================================================
`Ziggurat\AoWDevEd.exe` (zigexe.SRC_EDITOR) is the PATCH SOURCE, and nothing runs it. The editor
the owner actually launches is `Ziggurat\AoWzEd.exe` (zigexe.LIVE_EDITOR), which
`build_zigeditor.py` REBUILDS from AoWDevEd.exe. Skip the second step and the patch sits in a file
no one loads -- silently:

    python build_unitfloater_uncap.py --apply    # patches Ziggurat\AoWDevEd.exe
    python build_zigeditor.py         --apply    # rebuilds -> Ziggurat\AoWzEd.exe

(build_zigeditor.py takes --apply / --undo / --png PATH; no args = dry run.)

⚠ `AoWEd.exe` is NO LONGER A TARGET. The 2026-09-09 move left no copy in the overlay -- only the
game root's stock one, which is VANILLA and must never be patched. Its addresses above are kept as
reusable RE machinery.

WHAT IS DELIBERATELY NOT DONE
-----------------------------
`ClientHeight` 253 -> 475. It is comfort only -- the grid is already `ScrollBars = ssVertical` and
`Align = alClient`, so it scrolls today and will scroll after. Offered as `--tall`, **off by
default**, because raising a form past 432px high is the shape of the `aow1-dialog-resize-clamp`
hazard. That clamp turns out NOT to govern this window (`TUnitFloater`'s parent is
`VCL30.dpl Forms..TForm`, while the clamp is a rect pass over `AoWComp.TAoWComponent` descendants
owned by `AOWWinManager` in `aowInt.dpl` -- a different object universe, and `AoWDevEd.exe`
imports no aowInt methods at all), but the cap fix does not need the height, so it is not taken by
default.

Usage:
  python build_scripts/build_unitfloater_uncap.py           dry run + report state
  python build_scripts/build_unitfloater_uncap.py --apply   patch the editor
  python build_scripts/build_unitfloater_uncap.py --undo    surgical revert
  python build_scripts/build_unitfloater_uncap.py --apply --tall   also raise ClientHeight

`--undo` is surgical (restores the DFM run, the ClientHeight and the tabs byte) and touches no
backup. There is no snapshot layer to fall back on -- both `.pre-*` stacks were purged
(2026-08-08, 2026-09-03).
"""
import os
import shutil
import struct
import sys

import zigexe

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")
SUFFIX = ".pre-unitfloater"
EDITORS = (zigexe.SRC_EDITOR,)          # AoWEd.exe retired 2026-09-09 -- see the trap above

DFM_SIZE = 0xC8A
DFM_HEAD = b"TPF0\x0cTUnitFloater"
RUN_REL = 0x84C
OLD_RUN = (b"\x0dGrowDirection\x07\x0cilHorizontal"
           b"\x0bMinRowCount\x02\x04"
           b"\x0bMinColCount\x02\x08")
NEW_RUN = (b"\x0dGrowDirection\x07\x0ailVertical"
           b"\x0bMinRowCount\x03\x04\x00"
           b"\x0bMinColCount\x03\x08\x00")
TAIL_REL = 0x884                                  # MaxRowCount onward must be untouched
TAIL_EXPECT = b"\x0bMaxRowCount\x02\x00\x0bMaxColCount\x02\x08"

CH_REL = 0x06A                                    # ClientHeight property start
CH_OLD = b"\x0cClientHeight\x03\xfd\x00"          # 253
CH_NEW = b"\x0cClientHeight\x03\xdb\x01"          # 475

# Patch B -- both editors, but at different addresses, so find the block by PATTERN.
# The three adjacent stores in TRaceResourceEditForm.FormCreate:
#   c6 40 4b 01   mov byte [eax+0x4B], 1   All tab       ON
#   c6 40 49 00   mov byte [eax+0x49], 0   race tabs     OFF
#   c6 40 4a 00   mov byte [eax+0x4A], 0   category tabs OFF  <- the byte we flip (offset +11)
TABS_BLOCK_OLD = bytes.fromhex("c6404b01" "c6404900" "c6404a00")
TABS_BLOCK_NEW = bytes.fromhex("c6404b01" "c6404900" "c6404a01")
TABS_FLIP_OFF = 11                                # the immediate of the +0x4A store


def find_tabs(d):
    """File offset of the flag block. Refuses to guess if it is not unique."""
    old = d.find(TABS_BLOCK_OLD)
    new = d.find(TABS_BLOCK_NEW)
    i = old if old >= 0 else new
    assert i >= 0, "TRaceResourceEditForm flag block not found"
    for pat in (TABS_BLOCK_OLD, TABS_BLOCK_NEW):
        assert d.find(pat, i + 1) < 0, "flag block is not unique -- refusing to guess"
    return i


def va2off(d, va):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    tbl = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    for i in range(nsec):
        s = tbl + 40 * i
        vsz, rva, rsz, ro = struct.unpack_from("<IIII", d, s + 8)
        if 0x400000 + rva <= va < 0x400000 + rva + max(vsz, rsz):
            off = ro + (va - 0x400000 - rva)
            assert off < ro + rsz, "%08X past raw data" % va
            return off
    raise AssertionError("VA %08X in no section" % va)


def find_dfm(d):
    """Locate the TUnitFloater DFM by content, not by a hard-coded offset."""
    i = d.find(DFM_HEAD)
    assert i >= 0, "TUnitFloater DFM not found"
    assert d.find(DFM_HEAD, i + 1) < 0, "more than one TUnitFloater DFM -- refusing to guess"
    return i


def state_of(d, base, tall):
    run = bytes(d[base + RUN_REL:base + RUN_REL + len(OLD_RUN)])
    ch = bytes(d[base + CH_REL:base + CH_REL + len(CH_OLD)])
    if run == OLD_RUN:
        return "vanilla"
    if run == NEW_RUN and (not tall or ch == CH_NEW):
        return "applied"
    return "foreign"


def main(argv):
    apply_, undo, tall = "--apply" in argv, "--undo" in argv, "--tall" in argv
    blobs, bases, states = {}, {}, []

    # ⚠ EVERY target is validated before ANY of them is opened, let alone written. With more than
    # one target, returning on the first missing file mid-loop is how a run half-applies.
    missing = [fn for fn in EDITORS if not os.path.exists(os.path.join(GAME, fn))]
    if missing:
        for fn in missing:
            print("MISSING: %s" % os.path.join(GAME, fn))
        return 1

    for fn in EDITORS:
        p = os.path.join(GAME, fn)
        d = bytearray(open(p, "rb").read())
        base = find_dfm(d)
        assert bytes(d[base + TAIL_REL:base + TAIL_REL + len(TAIL_EXPECT)]) == TAIL_EXPECT, \
            "%s: the DFM tail past the edit is not what we expect -- aborting" % fn
        blobs[fn], bases[fn] = d, base
        st = state_of(d, base, tall)
        states.append(st)
        run = bytes(d[base + RUN_REL:base + RUN_REL + 16])
        print("%-14s DFM @0x%06X  %-8s  %s..." % (fn, base, st, run[:16].hex()))

    # Patch B state -- both editors, located by pattern (their VAs differ)
    tabs, tstates = {}, []
    for fn, d in blobs.items():
        i = find_tabs(d)
        tabs[fn] = i
        blk = bytes(d[i:i + len(TABS_BLOCK_OLD)])
        st = ("vanilla" if blk == TABS_BLOCK_OLD else
              ("applied" if blk == TABS_BLOCK_NEW else "foreign"))
        tstates.append(st)
        print("%-14s tabs @0x%06X  %-8s  %s" % (fn, i, st, blk.hex()))
    tabs_state = tstates[0] if len(set(tstates)) == 1 else "foreign"

    if "foreign" in states or "foreign" in tstates:
        print("\nABORT: unrecognised bytes -- neither vanilla nor ours. Someone else owns a site.")
        return 2
    if len(set(states)) != 1:
        print("\nABORT: the targets disagree (%s); they must stay in lockstep." % states)
        return 2

    if undo:
        if states[0] == "vanilla" and tabs_state == "vanilla":
            print("\nalready vanilla -- nothing to undo")
            return 0
        for fn, d in blobs.items():
            b = bases[fn]
            d[b + RUN_REL:b + RUN_REL + len(OLD_RUN)] = OLD_RUN
            if bytes(d[b + CH_REL:b + CH_REL + len(CH_OLD)]) == CH_NEW:
                d[b + CH_REL:b + CH_REL + len(CH_OLD)] = CH_OLD
            d[tabs[fn]:tabs[fn] + len(TABS_BLOCK_OLD)] = TABS_BLOCK_OLD
            open(os.path.join(GAME, fn), "wb").write(bytes(d))
            print("reverted %s (DFM run + tabs byte, no backup touched)" % fn)
        return 0

    if states[0] == "applied" and tabs_state == "applied":
        print("\nalready applied -- DFM run and tabs byte both verified")
        return 0

    print("\nA  cap : GrowDirection ilHorizontal -> ilVertical (+ Min*Count re-encoded to vaInt16,")
    print("         values unchanged 4 / 8). 8 cols x 20 rows = 160  ->  8 x 23 = 184 cells.")
    print("B  tabs: +0x4A category tabs ON for the race floater, at file %s"
          % ", ".join("%s 0x%06X" % (f, o) for f, o in sorted(tabs.items())))
    print("   tall: %s" % ("YES -- ClientHeight 253 -> 475" if tall else "no (default)"))
    if not apply_:
        print("\nDRY RUN -- pass --apply to write")
        return 0

    for fn, d in blobs.items():
        b = bases[fn]
        # Snapshot goes in <game dir>\backups\, never beside the binary (CLAUDE.md 2026-09-03),
        # and only from a file PROVED unpatched -- `states[0] == "vanilla"` is that proof. We reach
        # here only on apply, so the alternative is "applied", i.e. our own earlier output.
        bak = os.path.join(BACKUP_DIR, fn + SUFFIX)
        if states[0] != "vanilla":
            print("no backup taken (%s is %s, not vanilla)" % (fn, states[0]))
        elif not os.path.exists(bak):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(os.path.join(GAME, fn), bak)
            print("backup written: %s" % bak)
        before = len(d)
        d[b + RUN_REL:b + RUN_REL + len(OLD_RUN)] = NEW_RUN
        assert len(d) == before, "the DFM edit changed the file length -- that must never happen"
        assert bytes(d[b + TAIL_REL:b + TAIL_REL + len(TAIL_EXPECT)]) == TAIL_EXPECT, \
            "the DFM tail moved -- aborting before write"
        if tall:
            assert bytes(d[b + CH_REL:b + CH_REL + len(CH_OLD)]) in (CH_OLD, CH_NEW)
            d[b + CH_REL:b + CH_REL + len(CH_OLD)] = CH_NEW
        d[tabs[fn]:tabs[fn] + len(TABS_BLOCK_NEW)] = TABS_BLOCK_NEW
        open(os.path.join(GAME, fn), "wb").write(bytes(d))
        print("patched %s" % fn)

    for fn in EDITORS:
        d = bytearray(open(os.path.join(GAME, fn), "rb").read())
        b = find_dfm(d)
        assert bytes(d[b + RUN_REL:b + RUN_REL + len(NEW_RUN)]) == NEW_RUN, "read-back failed " + fn
        i = find_tabs(d)
        assert bytes(d[i:i + len(TABS_BLOCK_NEW)]) == TABS_BLOCK_NEW, "tabs read-back failed " + fn
    print("read-back verified.")
    print("\nIN-EDITOR TEST NEEDED -- this script cannot confirm anything:")
    print("  0. Run build_zigeditor.py --apply FIRST -- the tests below need Ziggurat\\AoWzEd.exe,")
    print("     which is rebuilt from the AoWDevEd.exe this script just patched.")
    print("  1. AoWzEd: open the Unit Floater, All tab -- scroll to the end, all 179 units")
    print("     must be reachable, not 160. Still 8 columns, no horizontal scrollbar.")
    print("  2. Unit ORDER must be unchanged -- spot-check the first row and one mid-list unit.")
    print("  3. Switch tabs repeatedly (All -> a race -> All). Watch for a stuck scroll position,")
    print("     a selection landing on the wrong unit, or an exception. !! This is the one real")
    print("     risk: RowCount now changes on tab switch, which it never did for this grid.")
    print("  4. Place a unit from BEYOND the old 160 boundary and confirm the right one lands.")
    print("  5. The Heroes tab must still work (shares the form, sibling grid untouched).")
    print("  6. Open a RACE resource -- its floater should now show Humanoid/Creatures/Siege tabs.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
