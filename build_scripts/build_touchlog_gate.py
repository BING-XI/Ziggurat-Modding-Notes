#!/usr/bin/env python3
r"""
build_touchlog_gate.py -- turn OFF any subset of the combat log's seven DLL hooks, for A/B isolation.

`build_combatlog_dll.py` installs SEVEN hooks (its own header still claims three):

    tails       0x55729C8C  TDamageCA.Generate epilogue      -> the line-building worker
                0x55729D08  TDamageCA.GenerateEx epilogue
    roll        0x55725EBC  ExecuteDamageRole's RandInt call  -> records the d20 for crit/fumble
    turnundead  0x5576B55C  CreateTurnUndeadCA stage-1 HitRole
    touch       0x557681B0  TTouchAbility.CombatTouchRole entry  (the whole 16-ability touch family,
                0x557681D6  ... roll 1 (vs GetDefense)            which INCLUDES TWallCrushing)
                0x55768216  ... roll 2 (vs GetResistance)

WHY THIS EXISTS -- and why it only turns things OFF
---------------------------------------------------
Isolating which hook causes a symptom needs one variable at a time, and `build_combatlog_dll.py`
rebuilds its whole cave image, so it cannot install a partial set.

This tool deliberately knows ONLY what STOCK looks like at each site. It does NOT hardcode cave stub
addresses: the cave moves whenever its image is revised or relocated, and an earlier version of this
tool did hardcode them -- then aborted with "another patch may own this site" when the bytes it found
were in fact our own newer build. Anything that is not the stock encoding at one of OUR hook sites is
our hook, whichever generation it belongs to, and that is all we need in order to restore it.

To turn hooks back ON, run `build_combatlog_dll.py --apply`: it regenerates every hook against the
current cave layout, keeping exactly one source of truth for where the cave lives.

USAGE
    python build_touchlog_gate.py --off [--touch] [--tails] [--roll] [--turnundead] [--all] [--apply]

Idempotent, verify-before-write, dry-run by default, refuses to write while the game/editor is
running. Touches only call sites -- never the cave, never a backup layer.

⚠ The write guard scans `zigexe.ALL_EXES` -- the MOD binaries only. Naming the pre-2026-09-09 pair
here was wrong in BOTH directions: a running `AoWz.exe` went undetected (guard passes, the write
then dies on PermissionError), while a running VANILLA `AoW.exe` blocked a write that was fine.
"""
import os, struct, subprocess, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

import zigexe

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL  = os.path.join(GAME, "AoWEPACK.dpl")
BASE = 0x55700000
cs = Cs(CS_ARCH_X86, CS_MODE_32)

HITROLE = 0x55725D98          # AoWE.HitRole   -- stock target of the three roll captures
RANDINT = 0x55701080          # System RandInt -- stock target of the ExecuteDamageRole capture
POPS    = bytes.fromhex("5f5e5b595d")     # pop edi/esi/ebx/ecx/ebp -- the displaced epilogue

def rel32(src, dst):
    return struct.pack("<i", dst - (src + 5))

# (va, description, STOCK bytes)
GROUPS = {
    "touch": [
        (0x557681B0, "CombatTouchRole entry",            bytes.fromhex("53565751890c24")),
        (0x557681D6, "CombatTouchRole roll 1 (vs DEF)",  b"\xE8" + rel32(0x557681D6, HITROLE)),
        (0x55768216, "CombatTouchRole roll 2 (vs RES)",  b"\xE8" + rel32(0x55768216, HITROLE)),
    ],
    "tails": [
        (0x55729C8C, "TDamageCA.Generate epilogue",      POPS),
        (0x55729D08, "TDamageCA.GenerateEx epilogue",    POPS),
    ],
    "roll": [
        (0x55725EBC, "ExecuteDamageRole RandInt capture", b"\xE8" + rel32(0x55725EBC, RANDINT)),
    ],
    "turnundead": [
        (0x5576B55C, "CreateTurnUndeadCA stage-1 HitRole", b"\xE8" + rel32(0x5576B55C, HITROLE)),
    ],
}

def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e + 6)[0]
    opt = struct.unpack_from("<H", data, e + 0x14)[0]
    out = []
    for i in range(nsec):
        o = e + 0x18 + opt + i * 40
        vs, va, rs, ptr = struct.unpack_from("<IIII", data, o + 8)
        out.append((va, vs, rs, ptr))
    return out

def va2off(secs, va):
    r = va - BASE
    for sva, vs, rs, ptr in secs:
        if sva <= r < sva + max(vs, rs):
            return ptr + (r - sva)
    raise ValueError("VA %#x not mapped" % va)

def locked():
    """Which mod binary is holding Ziggurat\\AoWEPACK.dpl open, if any.

    ⚠ The MOD names only. The root's vanilla AoW.exe / AoWCompat.exe load the ROOT's copy of every
    package, so one of those running does not lock this DLL and must not stop a write."""
    try:
        out = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True).stdout
    except Exception:
        return None
    for exe in zigexe.ALL_EXES:
        if exe.lower() in out.lower():
            return exe
    return None

def main():
    if "--on" in sys.argv:
        sys.exit("To turn hooks back ON run:  python build_combatlog_dll.py --apply\n"
                 "  It regenerates every hook against the CURRENT cave layout. This tool only knows\n"
                 "  what stock looks like, deliberately -- see the docstring.")
    if "--off" not in sys.argv:
        sys.exit("usage: build_touchlog_gate.py --off [--touch] [--tails] [--roll] [--turnundead]\n"
                 "                              [--all] [--apply]\n"
                 "  groups default to --touch. Re-enable with build_combatlog_dll.py --apply.")
    apply_ = "--apply" in sys.argv
    groups = list(GROUPS) if "--all" in sys.argv else \
             ([g for g in GROUPS if "--" + g in sys.argv] or ["touch"])

    data = bytearray(open(DLL, "rb").read())
    secs = load_sections(data)
    print("combat-log hooks [%s] -> STOCK (off)\n" % ", ".join(groups))

    plan = []
    for va, desc, stock in (x for g in groups for x in GROUPS[g]):
        o = va2off(secs, va)
        cur = bytes(data[o:o + len(stock)])
        if cur == stock:
            state = "already stock"
        else:
            state = "hooked -> restore"
            plan.append((va, o, cur, stock, desc))
        txt = next(cs.disasm(cur, va), None)
        print("  %-34s @ %08X  %-20s [%s]"
              % (desc, va, (txt.mnemonic + " " + txt.op_str) if txt else cur.hex(), state))

    if not plan:
        print("\n[= ] already in the requested state.")
        return 0
    if not apply_:
        print("\n[dry-run] %d site(s) would change. Re-run with --apply." % len(plan))
        return 0
    who = locked()
    if who:
        sys.exit("[x] %s is running and locks the DLL. Close it and retry." % who)
    for va, o, cur, stock, desc in plan:
        assert bytes(data[o:o + len(stock)]) == cur, "verify-before-write failed at %#x" % va
        data[o:o + len(stock)] = stock
        print("  [w ] %08X %s" % (va, desc))
    open(DLL, "wb").write(bytes(data))
    chk = open(DLL, "rb").read()
    for va, o, cur, stock, desc in plan:
        assert chk[o:o + len(stock)] == stock, "readback mismatch at %#x" % va
    print("\n[done] %d site(s) restored to stock and verified." % len(plan))
    return 0

if __name__ == "__main__":
    sys.exit(main())
