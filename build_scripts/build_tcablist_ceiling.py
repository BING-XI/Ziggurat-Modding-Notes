#!/usr/bin/env python
r"""
build_tcablist_ceiling.py -- raise the ability-id ceiling on the in-combat unit panel.

THE BUG (diagnosed 2026-08-27 from the user's report that Shield was missing from the
embedded in-combat unit card while the full Unit dialog listed it).

`AoWTC.TTacticalCombatUnitHS.CreateTCAbList @0x00423430` (AoWTCPCK.dpl) builds the TList at
`[combatunit+0x40]` that `TTacticalCombatUnitHS.ListAbilities @0x0042355C` renders into that
panel. It is a plain counted loop over ability ids:

    00423489  c7 45 f8 01 00 00 00   mov   dword [ebp-8], 1      ; id := 1
    0042349B  ff 51 a8               call  [ecx+0xA8]            ; GetAbilityEnabled(id)
    004234A1  84 c0 / 74 ..          test  al,al / je next       ; <- the ONLY inclusion test
    004234E1  ff 51 98               call  [ecx+0x98]            ; GetControlType()
    004234E7  a8 02                  test  al, 2                 ; <- ORDERING ONLY
    004234E9  74 4e                  je    add_at_end            ;    set -> TList.Insert (front)
                                                                 ;    clear -> TList.Add (end)
    0042354A  81 7d f8 aa 00 00 00   cmp   dword [ebp-8], 0xAA   ; id <= 0xA9
    00423551  75 ..                  jne   loop

⚠ THE OBVIOUS READING IS WRONG, so do not "fix" this by touching that call. There is no
type filter here: `test al,2` only chooses Insert-at-front versus Add-at-end, and BOTH
branches add the ability. A passive is perfectly welcome in this list; Parry (id 0x71) has
always appeared there.

⚠ NAMING CORRECTED 2026-08-28: VMT **+0x98 is `TAbility.GetControlType`**, not GetCombatMode
(`GetCombatMode` is +0x84). The distinction matters elsewhere -- the front/back split this
call drives is exactly what makes an ability SELECTABLE in tactical combat, and a selectable
id above 169 reaches `bound eax,(0,169)` on `AoWTC.AbilTypes` on the next map click. The ids
this script lists are all TEnhancementAbility, whose GetControlType returns 0, so they land at
the back and are never selected -- safe **on this path**.

⚠⚠ DO NOT GENERALISE THAT. An earlier version of this paragraph said "selectable ids are the
only ones that reach `bound eax,(0,169)`", and `build_abilityid_ceilings.py` acted on it. FALSE:
the four `TCAI.EvalBattle` scan loops that script raises have **no selectability gate at all**
between `GetAbilityEnabled` and the `bound`, so every enabled id above 169 crashes them. That
shipped, and fired in game 2026-09-01 as **"Error during Create Unit List"**. The fix, and now a
prerequisite for `build_abilityid_ceilings.py`, is `build_abiltypes_relocate.py`: it moves
AbilTypes to a 256-byte table at 0x00469440 and widens all nine `{0,169}` limit words to
`{0,255}`, atomically. This script is not itself affected -- `CreateTCAbList` contains none of the
15 guarded reads -- but it is what puts a selectable id in front of the map-click bound, so the
relocation is what makes listing one above 169 safe.

⚠ The `Zig notes/ID_Ceilings.md` forward rule **"above id 169, passives only"** is **LIFTED** once
`build_abiltypes_relocate.py` is applied: selectable abilities become safe up to id 255. Until
then the rule still binds.

The real ceiling is the loop bound. Vanilla's highest ability id was 0xA9 and the bound is
"one past the last id", so the loop was always exactly big enough -- until Ziggurat minted
ids above it. Everything from 0xAA up is silently invisible in the in-combat panel:

    0xAA Magebane   0xAB Drillmaster   0xAC Evoker   0xAD Conjurer
    0xAE Enchanter  0xAF Ritualist     0xB0 Shield   0xB1 Reforming Flesh

Confirmed pre-existing: the `aa` immediate is byte-identical in all six
`AoWTCPCK.dpl.pre-*` snapshots on disk, so no feature of this project introduced it.

WHAT THIS SCRIPT DOES. One immediate at VA 0x0042354D (file 0x02294D), currently
`0xAA` -> `0xB2`. That covers ids 1..0xB1, i.e. through Reforming Flesh.

*** THIS BOUND IS A SHARED RESOURCE. THE NEXT ABILITY ADDED WILL NEED IT BUMPED AGAIN. ***
The loop is exclusive (`inc; cmp; jne body`), so a new id lands exactly one past the bound and
its body never runs. SYMPTOM, so nobody re-diagnoses it from scratch: the ability **works** --
it heals/buffs correctly, and it appears in the full Unit dialog and the hero level-up dialog
(both derive their bound from `GetCount`, not from an immediate) -- but it is **absent from
this in-combat panel**, and from the banner popups and the tactical AI scan owned by
`build_abilityid_ceilings.py`. "Works but is listed nowhere" is this ceiling, every time.
Append the new value to LADDER here AND to the LADDER in `build_abilityid_ceilings.py`; the two
MUST stay on the same value. Both scripts recompute "highest registered id + 1" from the live
`.pfs` on every run, so a plain dry run of either is the check.

    2026-08-28  0xAA -> 0xB1  (ids up to Shield 0xB0)
    2026-09-01  0xB2 -> 0xB3  (id 0xB2 Embrittled, build_embrittle.py)
    2026-08-31  0xB1 -> 0xB2  (id 0xB1 Reforming Flesh; found by QA)

⚠ WHY NOT A ROOMIER BOUND -- AND A CORRECTION. This used to say that iterating past the
highest registered id is "an out-of-bounds read". **It is not**, and that claim was wrong
(corrected 2026-08-28): `TAbilityControl.GetAbility @0x557501C0` returns **nil** past the
registered count, and the bitset readers `GetAbSet @0x5574E0E0` / `GetAbilitySet @0x5577F618`
both open `cmp edx,[eax+0xC]; jae -> return False`. Over-iterating is safe; it is merely
pointless work. The bound is still kept at "highest registered id + 1" to match the vanilla
invariant and to keep the drift check meaningful -- see the shared-resource note above for the
consequence and the symptom.

WALKING STAYS HIDDEN (user ruling 2026-08-27). Walking is id 0x00 and is excluded by the
loop STARTING at 1, not by the ceiling. That is vanilla behaviour and is deliberately left
alone -- the loop-init at 0x00423489 is asserted unchanged on every run so a future edit
cannot quietly re-admit it.

POSITION INDEPENDENCE is not a concern here even though AoWTCPCK.dpl rebases: the patched
bytes are the immediate of `cmp reg, imm32`. No address, no .reloc entry, nothing to fix up.

USAGE
    python build_scripts/build_tcablist_ceiling.py            verify / dry run (writes nothing)
    python build_scripts/build_tcablist_ceiling.py --apply    write the raised ceiling
    python build_scripts/build_tcablist_ceiling.py --undo     restore the vanilla 0xAA
"""
import argparse
import os
import shutil
import struct
import sys

# The Windows console defaults to cp1252, which cannot encode the U+26A0 warning sign this script
# PRINTS (not merely documents) when the ladder has drifted. Without this the warning truncates
# mid-sentence and the script exits non-zero on a UnicodeEncodeError -- hiding the very diagnosis
# it was trying to deliver, which is exactly what happened when Reforming Flesh (0xB1) overran the
# ceiling. Same idiom as build_shield.py. Degrade unencodable glyphs instead of raising.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
from build_statdouble import kill_aow  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWTCPCK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-tcablceiling")

# `cmp dword [ebp-8], imm32` -- the whole instruction is verified, not just the immediate,
# so a shifted or recompiled build cannot be patched blind.
BOUND_VA = 0x0042354A
BOUND_PREFIX = bytes.fromhex("817df8")
# Every bound this script has ever shipped, oldest first. LADDER[0] is vanilla, LADDER[-1] is the
# target; everything between is a value we ourselves wrote on an earlier run. Verify-before-write
# accepts any of them as a starting state, which is what makes a bump an in-place rewrite rather
# than the revert-and-re-apply this project does not have. APPEND, never replace -- and keep this
# equal to build_abilityid_ceilings.py's LADDER.
LADDER = (0xAA, 0xB1, 0xB2, 0xB3)                 # vanilla .. target

# `mov dword [ebp-8], 1` -- asserted unchanged: this is what keeps Walking (id 0) hidden.
INIT_VA = 0x00423489
INIT_BYTES = bytes.fromhex("c745f801000000")


def pe_base_and_sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    base = struct.unpack_from("<I", d, e + 24 + 28)[0]
    sec, out = e + 24 + opt, []
    for _ in range(nsec):
        name = d[sec:sec + 8].rstrip(b"\0").decode(errors="replace")
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, sec + 8)
        out.append((name, vaddr, vsize, raw, rsize))
        sec += 40
    return base, out


def va2off(d, va):
    base, secs = pe_base_and_sections(d)
    rva = va - base
    for _n, vaddr, vsize, raw, rsize in secs:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
    return None


def highest_ability_id():
    """The live highest registered ability id, or None if re_tools is unavailable."""
    try:
        import ability_names
        return max(ability_names.names())
    except Exception as exc:                     # noqa: BLE001 - advisory only
        print("  (could not read the live ability ids: %s)" % exc)
        return None


def main():
    ap = argparse.ArgumentParser(
        description="raise the in-combat ability-panel id ceiling (AoWTCPCK.dpl)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    print("build_tcablist_ceiling -- CreateTCAbList ability-id ceiling")
    print("target: %s\n" % TARGET)

    if not os.path.exists(TARGET):
        sys.exit("ERROR: not found: %s" % TARGET)
    d = bytearray(open(TARGET, "rb").read())

    io_ = va2off(d, INIT_VA)
    bo = va2off(d, BOUND_VA)
    if io_ is None or bo is None:
        sys.exit("ERROR: a target VA does not map into the file")

    if bytes(d[io_:io_ + len(INIT_BYTES)]) != INIT_BYTES:
        sys.exit("ABORT: loop init at 0x%08X is not `mov dword [ebp-8], 1` (%s).\n"
                 "Walking's exclusion depends on it; refusing to touch the ceiling."
                 % (INIT_VA, bytes(d[io_:io_ + len(INIT_BYTES)]).hex(" ")))
    print("  loop init  0x%08X  %s  mov dword [ebp-8], 1   (Walking stays hidden)"
          % (INIT_VA, INIT_BYTES.hex(" ")))

    if bytes(d[bo:bo + 3]) != BOUND_PREFIX:
        sys.exit("ABORT: 0x%08X is not `cmp dword [ebp-8], imm32` (%s)"
                 % (BOUND_VA, bytes(d[bo:bo + 7]).hex(" ")))
    cur = struct.unpack_from("<I", d, bo + 3)[0]
    if cur not in LADDER:
        sys.exit("ABORT: ceiling is 0x%02X, off the ladder %s. Nothing written."
                 % (cur, ", ".join("0x%02X" % v for v in LADDER)))

    vanilla, target = LADDER[0], LADDER[-1]
    state = ("VANILLA" if cur == vanilla else
             "APPLIED" if cur == target else "APPLIED (stale, an earlier rung)")
    print("  ceiling    0x%08X  %s  cmp dword [ebp-8], 0x%02X   -> covers ids 1..0x%02X"
          % (BOUND_VA, bytes(d[bo:bo + 7]).hex(" "), cur, cur - 1))
    print("\n  state: %s\n" % state)

    hi = highest_ability_id()
    drifted = False
    if hi is not None:
        want = hi + 1
        print("  highest registered ability id: 0x%02X  =>  the bound should be 0x%02X" % (hi, want))
        if want != target:
            drifted = True
            print("  ⚠ THE LADDER IS OUT OF DATE. An ability id has been added since this script\n"
                  "    was last tuned. APPEND 0x%02X to LADDER here AND to the LADDER in\n"
                  "    build_abilityid_ceilings.py -- the two must stay on the same value -- then\n"
                  "    re-apply both. Until you do, id 0x%02X and up work but are listed nowhere."
                  % (want, target))
        excluded = [i for i in range(cur, want)]
        if excluded:
            print("  currently hidden by the ceiling: %s"
                  % ", ".join("0x%02X" % i for i in excluded))
    print()

    # Refuse to WRITE a bound the live data has already outgrown. (--undo is still allowed: going
    # back to vanilla is always a valid thing to want.) The sibling script aborts on the same
    # condition; the asymmetry where one aborts and the other only warns is itself a trap.
    if drifted and a.apply:
        sys.exit("ABORT: refusing to apply a stale bound. Fix LADDER in BOTH scripts first.")

    if a.undo:
        if cur == vanilla:
            print("  already at the vanilla ceiling -- nothing to do.")
            return
        kill_aow()
        struct.pack_into("<I", d, bo + 3, vanilla)
        open(TARGET, "wb").write(bytes(d))
        print("  reverted: ceiling back to 0x%02X. No backup touched." % vanilla)
        return

    if not a.apply:
        print("(dry run -- nothing written.  --apply to patch, --undo to revert)")
        return

    if cur == target:
        print("  already applied and up to date -- nothing to do.")
        return

    kill_aow()
    # ⚠ BACKUP GATING -- only ever snapshot a file PROVED unpatched.
    # The gate is a POSITIVE test that the ceiling still reads vanilla, never "no backup file
    # exists yet". Absence of a backup is not evidence of freshness: on a LADDER bump over an
    # existing install the file is this script's own previous output, and a `.pre-*` minted from it
    # would sit on disk looking authoritative while holding a patched state.
    if not os.path.exists(BACKUP):
        if cur == vanilla:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(TARGET, BACKUP)
            print("  backup -> %s (ceiling verified vanilla 0x%02X)"
                  % (os.path.basename(BACKUP), vanilla))
        else:
            print("  no backup taken: the ceiling already reads 0x%02X, not vanilla 0x%02X "
                  "(a .pre-* full of patched bytes is worse than none)." % (cur, vanilla))
    struct.pack_into("<I", d, bo + 3, target)
    open(TARGET, "wb").write(bytes(d))
    print("  applied: ceiling 0x%02X -> 0x%02X (ids 1..0x%02X now listed)."
          % (cur, target, target - 1))
    print("\n  NEEDS THE USER'S IN-GAME TEST -- nothing here is confirmed:")
    print("    1. a unit with Shield (0xB0) or Reforming Flesh (0xB1) shows it in the embedded")
    print("       in-combat unit panel")
    print("    2. Walking is STILL absent from that panel (it must stay hidden)")
    print("    3. Strike is still listed FIRST, above any passive (Insert-vs-Add ordering)")
    print("    4. a hero with Evoker / Conjurer / Enchanter / Ritualist shows them too")
    print("    5. clicking a passive entry does nothing harmful (same as Parry today)")


if __name__ == "__main__":
    main()
