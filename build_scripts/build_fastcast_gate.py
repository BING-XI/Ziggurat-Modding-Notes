#!/usr/bin/env python3
r"""
build_fastcast_gate.py -- DIAGNOSTIC TOGGLE for the unit-spellcasting FAST-COMBAT gates.

WHY THIS EXISTS
---------------
Chasing a freeze: an AI-initiated AUTOMATIC battle against the player's WALLED CITY hangs the game
(sound running, no input, reproducible on reload). `build_combatdiag.py` localised it precisely --
the combat is created, set up, both armies added, initialised, `TFastCombat.Execute` runs, the
per-unit pump completes round 1, and then dies INSIDE a single `TFastCombatUnit.fcExecute` call in
round 2. It is stuck in one invocation, not spinning (the capped counter stopped at 10, not 600).

Already eliminated by A/B: `aiitemtarget`, `effectroll`, `debuffcache`; and by measurement: the raze
rework (zero RAZE records, no combat from cave_towerraze), a leaked `map[+0x120]`, the player-0 gate
theory, the BSS flag collision (a real bug, fixed, but not this), and the combat-log ring.

THE HYPOTHESIS (the user's, and it fits the evidence)
----------------------------------------------------
Both sides in the failing battle field a **unit spellcaster**, and the target is a **walled city**.
`build_spellcast.py` opens seven `System.@IsClass(THero)` gates to also accept ordinary units with
the Spellcasting ability, by repointing each `call ISCLASS_THUNK` to `cave_iscaster`. Three of those
seven sit in exactly the code this freeze lives in:

    0x5576E418  G2  fcPrefetchCombatCommands   -- FAST-combat command prefetch
    0x5576DF17  G3  CanCastBreachWallSpell     -- "does a castable spell make this wall attackable"
    0x557F76EB  G7  CombatSpell.fcPrefetch     -- FAST-combat spell prefetch

If anything downstream of those still assumes the caster is a `THero` -- reads a hero-only field, or
queues a combat command a non-hero can never complete -- that unit's fast-combat turn never
finishes, and the pump stalls inside its `fcExecute`. `CanCastBreachWallSpell` answering *yes* for a
unit is the wall-specific half, which is why an open-field fight (indies attacking the player) works
and a city assault does not.

WHAT THIS DOES
--------------
`--disable` points ONLY those three call sites back at the stock `System.@IsClass` thunk, so fast
combat and the wall-breach check see heroes only, exactly as vanilla. Everything else about unit
spellcasting is left alone: strategic casting, the ability button, casting-point accounting and
refill, the unit-card display, tactical (manual) combat casting, and the other four gates
(G1/G4/G5/G6) all keep working. `--restore` puts the three back to `cave_iscaster`.

This is a TEST INSTRUMENT, not a fix. If it stops the freeze, the real work is finding which
downstream consumer assumes THero and teaching it about units -- not leaving these gates shut.

Safe: three 5-byte call-target rewrites, no cave touched, no backup layer disturbed, fully
reversible either way. Idempotent, verify-before-write, dry-run by default.
"""
import os, struct, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL  = os.path.join(GAME, "AoWEPACK.dpl")
BASE = 0x55700000
cs = Cs(CS_ARCH_X86, CS_MODE_32)

ISCLASS_THUNK = 0x557010C0     # System.@IsClass thunk -- the STOCK target (hero-only behaviour)
CAVE_ISCASTER = 0x5580D900     # build_spellcast.py's cave (hero OR unit-with-Spellcasting)

# Only the three gates that live in the fast-combat / wall-breach path.
SITES = [
    (0x5576E418, "G2 fcPrefetchCombatCommands"),
    (0x5576DF17, "G3 CanCastBreachWallSpell"),
    (0x557F76EB, "G7 CombatSpell.fcPrefetch"),
]

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

def call_to(site, target):
    return b"\xE8" + (target - (site + 5)).to_bytes(4, "little", signed=True)

def main():
    disable = "--disable" in sys.argv
    restore = "--restore" in sys.argv
    apply_  = "--apply"   in sys.argv
    if disable == restore:
        sys.exit("usage: build_fastcast_gate.py (--disable | --restore) [--apply]\n"
                 "  --disable : fast-combat + wall-breach spell gates -> stock IsClass (heroes only)\n"
                 "  --restore : back to cave_iscaster (units may cast in fast combat)")

    data = bytearray(open(DLL, "rb").read())
    secs = load_sections(data)
    want_t = ISCLASS_THUNK if disable else CAVE_ISCASTER
    other_t = CAVE_ISCASTER if disable else ISCLASS_THUNK

    print("unit-spellcasting FAST-COMBAT gates -> %s\n"
          % ("STOCK IsClass (heroes only)" if disable else "cave_iscaster (units may cast)"))

    plan = []
    for va, desc in SITES:
        off = va2off(secs, va)
        cur = bytes(data[off:off + 5])
        want = call_to(va, want_t)
        oth  = call_to(va, other_t)
        if cur == want:
            state = "already"
        elif cur == oth:
            state = "to change"
            plan.append((va, off, cur, want, desc))
        else:
            sys.exit("ABORT: %s @ %#x holds %s\n  expected %s (stock) or %s (modded).\n"
                     "  Another patch may own this call site -- investigate before proceeding."
                     % (desc, va, cur.hex(), call_to(va, ISCLASS_THUNK).hex(),
                        call_to(va, CAVE_ISCASTER).hex()))
        tgt = va + 5 + struct.unpack("<i", cur[1:])[0]
        print("  %-30s @ %08X  -> %08X   [%s]" % (desc, va, tgt, state))

    if not plan:
        print("\n[= ] already in the requested state -- nothing to do.")
        return 0
    if not apply_:
        print("\n[dry-run] %d call site(s) would change. Re-run with --apply."
              " Close all AoW binaries first." % len(plan))
        return 0

    for va, off, cur, want, desc in plan:
        assert bytes(data[off:off + 5]) == cur, "verify-before-write failed at %#x" % va
        data[off:off + 5] = want
        print("  [w ] %08X %s" % (va, desc))
    try:
        open(DLL, "wb").write(bytes(data))
    except PermissionError:
        sys.exit("[x] AoWEPACK.dpl is LOCKED -- close AoW.exe / AoWCompat.exe / AoWDevEd.exe.")

    chk = open(DLL, "rb").read()
    for va, off, cur, want, desc in plan:
        assert chk[off:off + 5] == want, "readback mismatch at %#x" % va
    print("\n[done] %d gate(s) written and verified. Reverse with the opposite flag." % len(plan))
    return 0

if __name__ == "__main__":
    sys.exit(main())
