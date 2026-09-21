#!/usr/bin/env python
"""
build_hitslope5.py  --  AoW1 to-hit granularity: 10 percentage points -> 5 per stat point.

WHAT THIS DOES
--------------
Every to-hit curve in AoW1 builds its x10 slope as "x2 then x5":

    add  eax, eax        <- the x2            (03 C0, or 01 C0 in the Ziggurat caves)
    imul eax, eax, 5     <- the x5            (6B C0 05, or lea eax,[eax+eax*4] in pristine)
    add  eax, 0x32       <- the +50 intercept

NOPping the x2 leaves x5, i.e. clamp(50 + 5d, 10, 90) instead of clamp(50 + 10d, 10, 90).
Seven sites carry that idiom for real (a further 12 look identical but compute something else --
see DECOYS below, and never pattern-match for this edit).

    4 engine sites   the two roll primitives, the weapon-strike roll, and the AI's model of it
    3 cave sites     Ziggurat combat-log lines that PRINT the odds; if they are not moved with the
                     engine the log prints the old percentages beside rolls made on the new curve

THIS SCRIPT IS HALF OF A PAIR.  It must be applied together with build_statdouble.py, which doubles
every ATK/DEF/RES source.  Slope-halving plus stat-doubling is a verified perfect identity (hit chance
AND the full damage distribution are bit-identical); the gain is that odd/half-steps become
expressible.  Applying this script ALONE halves the effect of every stat point in the game.

    See:  Modding Resources/Zig notes/FivePct_Conversion_Manifest.md   (decisions, state)
          Modding Resources/Zig notes/HitChance_Increment_Audit.md     (the site inventory)

WHY NOT EIGHT SITES
-------------------
TEnchantment.DispelChance @0x5577C1A4 carries the same clamp SHAPE and was listed as an eighth site
until 2026-08-18.  It is not one.  Read directly it is

    clamp(dispelMana - 10*[ench+0x14] + 50, 10, 90),  GetDispelMana = 10*abilityLevel + 20
    => clamp(10*(abilityLevel - enchStrength) + 70, 10, 90)

The difference is ability level vs enchantment strength.  Neither is an ATK/DEF/RES stat and neither
is doubled by build_statdouble.py, so halving that slope is a pure buff to dispelling -- and it cannot
be made an identity at all, because the +50 and +20 constants do not scale.  Left alone deliberately,
along with both GetDispelMana copies (0x5576CEB7 and 0x557E89F8).

DECOYS -- do NOT locate these sites by byte pattern
---------------------------------------------------
An "add r,r followed by x5" census over AoWEPACK returns 18 hits.  Only the 7 below are slope sites.
The other 11 compute skill-point prices, dispel mana, and unrelated arithmetic:
    0x5572D3FC 0x5572D484 0x55730676 0x55730780 0x5576CEB7 0x557875E8
    0x55787605 0x55789F69 0x557A1AFB 0x557AC405 0x557CEB34 0x557DB2A9
This script writes by absolute address only, and refuses to run if any site's bytes are unexpected.

IDEMPOTENCE
-----------
No version marker is needed here: 90 90 at these seven addresses is unambiguous, because both the
live file and the pristine backup hold 03 C0 / 01 C0.  The check is all-or-nothing -- a PARTIAL state
(some applied, some not) aborts rather than repairing, because it means something else moved bytes.

USAGE
-----
    python build_hitslope5.py            verify current state (default, writes nothing)
    python build_hitslope5.py --dis      also disassemble each site for review
    python build_hitslope5.py --apply    apply (backs up to AoWEPACK.dpl.pre-hitslope5)
    python build_hitslope5.py --undo     surgical revert (restores 03 C0 / 01 C0 in place)
"""
import os, sys, shutil, argparse, subprocess

# game dir = two levels up from this script (<game>/Modding Resources/build_scripts/)
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

TARGET = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-hitslope5")
IMAGE_BASE = 0x55700000

APPLIED = b"\x90\x90"

# (VA, original bytes, description).  File offsets are derived from the PE section table at run
# time -- never hard-coded, because VA->offset is per-section in this DLL.
SITES = [
    (0x55725D9D, b"\x03\xC0", "AoWE.HitRole                 -- clamp(50+10d,10,90) vs RandInt(100)"),
    (0x55725DCF, b"\x03\xC0", "AoWE.HitRoleProbability      -- float mirror, AI estimator"),
    (0x55725ED7, b"\x03\xC0", "AoWE.ExecuteDamageRole       -- T = 10-2d; THE weapon-strike hit test"),
    (0x55725E3B, b"\x03\xC0", "AoWE.DMDCtoDV                -- the AI's closed-form model of the above"),
    (0x5580F6C3, b"\x01\xC0", "cave build_effectroll.py     -- effect-roll log line (prints the odds)"),
    (0x558110C7, b"\x01\xC0", "cave build_combatlog_dll.py  -- _gotdef damage log line"),
    (0x558118F0, b"\x01\xC0", "cave build_combatlog_dll.py  -- _tstats touch log line"),
]

AOW_PROCS = ("AoW", "AoWCompat", "AoWDevEd", "AoWEd")


# ---------------------------------------------------------------- PE helpers

def sections(data):
    import struct
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[e_lfanew:e_lfanew + 4] == b"PE\0\0", "not a PE file"
    coff = e_lfanew + 4
    nsec, opt_size = struct.unpack_from("<H", data, coff + 2)[0], struct.unpack_from("<H", data, coff + 16)[0]
    sec = coff + 20 + opt_size
    out = []
    for _ in range(nsec):
        name = data[sec:sec + 8].rstrip(b"\0").decode(errors="replace")
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", data, sec + 8)
        out.append((name, vaddr, vsize, raw, rsize))
        sec += 40
    return out


def va2off(data, va):
    rva = va - IMAGE_BASE
    for name, vaddr, vsize, raw, rsize in sections(data):
        if vaddr <= rva < vaddr + max(vsize, rsize):
            off = raw + (rva - vaddr)
            if off + 2 > len(data):
                return None          # virtual-only tail (e.g. BSS): not file-backed
            return off
    return None


def kill_aow():
    """Game files are locked while any AoW binary runs.  Standing authorisation: just kill them."""
    killed = []
    for name in AOW_PROCS:
        r = subprocess.run(["taskkill", "/F", "/IM", name + ".exe"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            killed.append(name)
    if killed:
        print("  killed running: " + ", ".join(killed))


# ---------------------------------------------------------------- state

def read_state(data):
    """-> ('clean'|'applied'|'partial'|'foreign', [(va, found, expected, desc), ...])"""
    rows, clean, applied = [], 0, 0
    for va, orig, desc in SITES:
        off = va2off(data, va)
        if off is None:
            rows.append((va, None, orig, desc))
            continue
        found = data[off:off + 2]
        rows.append((va, found, orig, desc))
        if found == orig:
            clean += 1
        elif found == APPLIED:
            applied += 1
    n = len(SITES)
    if clean == n:
        return "clean", rows
    if applied == n:
        return "applied", rows
    if clean + applied == n:
        return "partial", rows
    return "foreign", rows


def show(rows, state):
    print("  %-12s %-8s %-8s  %s" % ("VA", "found", "expect", "site"))
    for va, found, orig, desc in rows:
        f = found.hex(" ") if found else "??"
        mark = "ok " if found == orig else ("APPLIED" if found == APPLIED else "*** UNEXPECTED ***")
        print("  %-12s %-8s %-8s  %-6s %s" % (hex(va), f, orig.hex(" "), mark, desc))
    print("\n  state: %s" % state.upper())


def disassemble(data):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        print("  (pip install capstone for --dis)")
        return
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for va, orig, desc in SITES:
        off = va2off(data, va)
        print("\n  ---- %s  %s" % (hex(va), desc))
        # Decode FROM the site, not before it.  Backing up a fixed number of bytes lands
        # mid-instruction on the cave sites (their preceding instruction is not 2 bytes long),
        # which silently swallows the slope instruction and hides the marker.
        print("    %08X  (preceding 4 bytes: %s)" % (va - 4, data[off - 4:off].hex(" ")))
        for ins in md.disasm(bytes(data[off:off + 20]), va):
            flag = "  <== SLOPE" if ins.address == va else ""
            print("    %08X  %-22s %s%s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic + " " + ins.op_str, flag))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="AoW1 to-hit slope 10pp -> 5pp")
    ap.add_argument("--apply", action="store_true", help="write the patch")
    ap.add_argument("--undo", action="store_true", help="surgical revert")
    ap.add_argument("--dis", action="store_true", help="disassemble each site")
    args = ap.parse_args()

    if not os.path.exists(TARGET):
        sys.exit("ERROR: not found: %s\n(set AOW_GAME_DIR if the install is elsewhere)" % TARGET)

    data = bytearray(open(TARGET, "rb").read())
    state, rows = read_state(data)

    print("build_hitslope5 -- to-hit granularity 10pp -> 5pp")
    print("target: %s\n" % TARGET)
    show(rows, state)
    if args.dis:
        disassemble(data)

    if state == "foreign":
        sys.exit("\nABORT: at least one site holds bytes that are neither the original nor 90 90.\n"
                 "Something else has moved these bytes.  Investigate before running this script.")
    if state == "partial":
        sys.exit("\nABORT: HALF-APPLIED state -- some sites patched, some not.\n"
                 "This script is all-or-nothing.  Do not repair automatically; find out what happened.")

    if not (args.apply or args.undo):
        print("\n(dry run -- nothing written.  --apply to patch, --undo to revert)")
        if state == "clean":
            print("\nREMINDER: apply build_statdouble.py in the same session.  This script alone")
            print("halves the value of every stat point in the game.")
        return

    if args.undo:
        if state == "clean":
            print("\nnothing to undo -- already at the original bytes.")
            return
        kill_aow()
        for va, orig, desc in SITES:
            off = va2off(data, va)
            assert data[off:off + 2] == APPLIED, "unexpected bytes at %s" % hex(va)
            data[off:off + 2] = orig
        open(TARGET, "wb").write(bytes(data))
        print("\nUNDONE -- %d sites restored in place (no backup touched)." % len(SITES))
        print("REMINDER: undo build_statdouble.py too, or the two halves disagree.")
        return

    # --apply
    if state == "applied":
        print("\nalready applied -- nothing to do (idempotent).")
        return
    kill_aow()
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP)
        print("\n  backup -> %s" % os.path.basename(BACKUP))
    else:
        print("\n  backup already exists, left as-is: %s" % os.path.basename(BACKUP))
    for va, orig, desc in SITES:
        off = va2off(data, va)
        assert data[off:off + 2] == orig, "verify-before-write failed at %s" % hex(va)
        data[off:off + 2] = APPLIED
    open(TARGET, "wb").write(bytes(data))
    print("\nAPPLIED -- %d sites, %d bytes.  Curve is now clamp(50 + 5d, 10, 90)." % (len(SITES), 2 * len(SITES)))
    print("\n*** NOW APPLY build_statdouble.py -- do not test the game until both are in. ***")


if __name__ == "__main__":
    main()
