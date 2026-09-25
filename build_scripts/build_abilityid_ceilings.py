#!/usr/bin/env python3
r"""Raise the six REMAINING vanilla 0xAA ability-id ceilings, so Ziggurat's ids 0xAA and up stop
being invisible to the tactical AI and to the two banner popups.

WHY THIS EXISTS
---------------
`build_tcablist_ceiling.py` raised ONE such ceiling (the in-combat unit panel, `CreateTCAbList
@0x00423430`) and is confirmed working. The id-ceiling audit of 2026-08-28
(`Zig notes/ID_Ceilings.md`) found that the same vanilla idiom occurs at **seven** distinct VAs in total and
that only that one had ever been raised. The other six are patched here -- eight file sites,
because AoWz.exe's two are mirrored into AoWzCompat.exe, so nine across the two scripts.

Vanilla's highest ability id was 0xA9, so every "iterate ids 1..N, ask GetAbilityEnabled" loop was
written with the terminator `cmp <counter>, 0xAA` -- "one past the last id", exactly big enough.
Ziggurat then minted eight more:

    0xAA Magebane   0xAB Drillmaster   0xAC Evoker   0xAD Conjurer
    0xAE Enchanter  0xAF Ritualist     0xB0 Shield   0xB1 Reforming Flesh

Everything from 0xAA up is silently skipped by every unraised loop. Not a crash -- a silence.

*** THIS BOUND IS A SHARED RESOURCE. THE NEXT ABILITY ADDED WILL NEED IT BUMPED AGAIN. ***
------------------------------------------------------------------------------------------
These loops are exclusive: `inc <counter>; cmp <counter>, BOUND; jne body`, so the body never runs
for id == BOUND. The bound is therefore "highest registered id + 1", and every new ability id
lands exactly one past it.

THE SYMPTOM, so nobody re-diagnoses it from scratch: the new ability **works perfectly** -- it
heals, it buffs, whatever it does, and it shows up in the full Unit dialog and in the hero
level-up dialog (both of those derive their bound from `GetCount`, not from an immediate). It is
simply **absent from the in-combat unit panel, the item banner popup and the unit hover popup, and
invisible to the tactical AI's battle scoring**. "Works but you cannot see it listed anywhere" is
this ceiling, every time.

THE FIX is two constants that must be moved together, in two scripts:
    build_abilityid_ceilings.py  LADDER   (this file, 8 of the 9 sites)
    build_tcablist_ceiling.py    LADDER   (the 9th, CreateTCAbList)
Append the new value to each LADDER -- do not replace the old one. The ladder is the
verify-before-write whitelist, so keeping every shipped value in it is what makes a bump an
in-place rewrite instead of the revert-and-re-apply this project does not have. Both scripts
recompute "highest registered id + 1" from the live `.pfs` on every run and ABORT if their target
has drifted from it, so a plain dry run of either is the check.

    2026-08-28  0xAA -> 0xB1  (ids up to Shield 0xB0)
    2026-09-01  0xB2 -> 0xB3  (id 0xB2 Embrittled, build_embrittle.py)
    2026-08-31  0xB1 -> 0xB2  (id 0xB1 Reforming Flesh; found by QA -- the ability healed
                               correctly but was invisible in every panel above)

WHAT IS ACTUALLY BROKEN BY THIS
-------------------------------
Sites 1-4 are the four ability scan loops in `TCAI.EvalBattle` (AoWTCPCK.dpl), so **the tactical
AI never enumerates any of the eight abilities when it scores a battle**. That is a balance
defect, not a cosmetic one: the AI cannot see Shield on a defender, cannot see Magebane, and so on.
Sites 5-6 are the two banner popups in AoWz.exe, which is cosmetic -- the abilities are absent from
the item banner and from the unit hover popup while present in the full unit dialog.

The loop body is unambiguous (verified at `0x0041870D`, the head of site 1's loop):

    0041870D  mov edx, [ebp-0x14]        ; <- the ability id, the bounded counter
    00418710  mov eax, [ebp-0x2c]        ; the unit
    00418715  call [ecx+0xA8]            ; GetAbilityEnabled(id)
    0041871B  test al,al / je skip
    00418723  cmp [ebp-0x14], 0x34       ; ...then per-id logic (Spellcasting here)

THE SITES -- all six verified byte-for-byte on the live files 2026-08-28
-----------------------------------------------------------------------
    AoWTCPCK.dpl  0x00418A73  81 7d ec aa 00 00 00   cmp [ebp-0x14],0xAA   TCAI.EvalBattle scan 1
    AoWTCPCK.dpl  0x00418D1F  81 7d f4 aa 00 00 00   cmp [ebp-0x0C],0xAA   scan 2
    AoWTCPCK.dpl  0x004190FA  81 7d f4 aa 00 00 00   cmp [ebp-0x0C],0xAA   scan 3
    AoWTCPCK.dpl  0x0041977F  81 7d f4 aa 00 00 00   cmp [ebp-0x0C],0xAA   scan 4
    AoWz.exe      0x00406DEF  81 fe aa 00 00 00      cmp esi,0xAA          TItemBanner popup
    AoWz.exe      0x00455DE1  81 fb aa 00 00 00      cmp ebx,0xAA          unit hover popup

One byte each -- the immediate, at +3 in the `[ebp-disp8]` form and at +2 in the register form.
`AoWzCompat.exe` takes the AoWz.exe pair in lockstep.  ⚠ Follow --apply with
⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)

⚠ NOT AN OUT-OF-BOUNDS RISK, and the reason matters. Over-iterating is safe:
`TAbilityControl.GetAbility @0x557501C0` returns **nil** past the registered count, and the bitset
readers `GetAbSet @0x5574E0E0` / `GetAbilitySet @0x5577F618` both open `cmp edx,[eax+0xC]; jae ->
return False`. (An earlier docstring of `build_tcablist_ceiling.py` claimed otherwise; corrected.)
The bound is nevertheless kept at exactly "highest registered id + 1" so the drift check below
stays meaningful, and this script recomputes that from the live data on every run.

⚠⚠ THIS SCRIPT REQUIRES `build_abiltypes_relocate.py`. RUN THAT FIRST, OR SITES 1-4 CRASH.
------------------------------------------------------------------------------------------
These four terminators are not themselves the `bound` instructions -- `AoWTCPCK.dpl` carries a
genuine hardware `BOUND eax,(0,169)` on `AoWTC.AbilTypes` (a 170-byte table, one category byte per
id 0..169) at 15 separate sites. But raising sites 1-4 **drives ids 0xAA..0xB2 straight into six of
them**, and that is a crash.

An earlier version of this paragraph claimed the opposite -- "our ids are safe above that bound
only because they are `TEnhancementAbility` and so never become *selectable*". **That reasoning is
true of the map-click path and FALSE of these four loops**, and believing it shipped a live defect.
There is no `GetControlType` gate anywhere between the enabled-test and the `bound` in
`TCAI.EvalBattle`; disassembled at scan 1:

    0041870D  mov  edx, [ebp-0x14]      ; the ability id -- the counter THIS script raises
    00418715  call [ecx+0xA8]           ; GetAbilityEnabled(id)
    0041871B  test al,al / je next      ; not enabled -> skip
    00418723  cmp  [ebp-0x14], 0x34     ; the only other test on the path
    ...
    004188E9  bound eax, [0x41B03C]     ; {0,169} -- reached by ANY enabled id
    004188EF  cmp  byte [eax+0x467248], 0

**Observed in game 2026-09-01**: an AI turn with priest heroes present raised #BR, which Delphi
turns into a range-check error and the caller swallows into the modal **"Error during Create Unit
List"**. Confirmed pre-existing to that day's other work by reverting the Turn Undead feature and
reproducing.

`build_abiltypes_relocate.py` is the fix and is now a **prerequisite** for this script: it moves
`AbilTypes` to a 256-byte table at `0x00469440`, repoints all 13 references, and widens all nine
`{0,169}` limit words to `{0,255}` -- atomically, because widening without relocating would read
past the original into `AoWTC.SpellTypes` and hand the AI spell categories as ability categories.
A dry run of it reports whether it is installed. Sites 5-6 (AoWz.exe) are unaffected either way;
`AoWz.exe` contains no real `BOUND` instructions at all.

⚠ The `Zig notes/ID_Ceilings.md` forward rule **"above id 169, passives only"** is **LIFTED** once
`build_abiltypes_relocate.py` is applied -- selectable abilities (`TTouchAbility`,
`TRangedAttackAbility`, `THealingAbility`, `TDispelMagicAbility`, `TSpellCastingAbility`) become
safe up to id 255. Until it is applied the rule still binds, and now it binds harder: with these
four loops raised, even a *passive* above 169 crashes the AI scan. Selectability is decided by
`TAbility.GetControlType` (VMT +0x98), not by any of these counters.

⚠⚠ BUT "LIFTED" IS ONLY HALF OF "IT WORKS". The relocation fills ids 170..255 with category **0**,
and category 0 is **inert at every consumer** -- correct for the passives that exist today,
useless for anything new. A selectable ability minted at id >= 170 would list in the panel and
then **deselect itself the instant it is clicked**:

    0041EC66  mov  al, [eax+0x469440]   ; the category byte
    0041EC72  sub  al, 1
    0041EC74  jb   0x41EC7F             ; CF set <=> category == 0
    0041EC7F  or   edx, 0xFFFFFFFF      ; -1
    0041EC85  call 0x00422F0C           ; TTacticalCombatUnitHS.SelectAbility(-1) = DESELECT

It would also stay invisible to the AI, draw no ranged path, and be excluded from `EvalPath` /
`CheckUnit`. **So a new id >= 170 needs BOTH: this bound raised, AND `[0x00469440 + id]` set to
its real category** -- 1/2/3/5/7/11 for attack categories, 4 for touch/command
(`sub al,1; jb` = 0, then `sub al,3; je` = 4). Do not invent values outside that set.

Usage:
  python build_scripts/build_abilityid_ceilings.py           dry run + report state
  python build_scripts/build_abilityid_ceilings.py --apply   patch all three binaries
  python build_scripts/build_abilityid_ceilings.py --undo    restore 0xAA at every site
"""
import os
import shutil
import struct
import subprocess
import sys

# The Windows console defaults to cp1252, which cannot encode the U+26A0 warning sign used above
# and below. Without this a script writes its bytes correctly and THEN dies with a
# UnicodeEncodeError partway through printing, exiting non-zero -- which reads as a failed patch
# when it was a successful one, and can truncate the very diagnosis you needed. Same idiom as
# build_shield.py. Degrade unencodable glyphs instead of raising.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                   # mod binary names (AoWz.exe / AoWzCompat.exe)
SUFFIX = ".pre-abilceilings"
BACKUP_DIR = os.path.join(GAME, "backups")      # ⚠ backups/, never the game root -- rule 2026-09-03

# Every bound this script has ever shipped, oldest first. LADDER[0] is vanilla, LADDER[-1] is the
# target; everything between is a value we ourselves wrote on some earlier run. Verify-before-write
# accepts any of them as a starting state, which is what makes a bump an in-place rewrite rather
# than a revert-and-re-apply. APPEND to this, never replace -- and keep it equal to
# build_tcablist_ceiling.py's LADDER.
LADDER = (0xAA, 0xB1, 0xB2, 0xB3, 0xBA, 0xBB, 0xBD)
VANILLA, TARGET = LADDER[0], LADDER[-1]

# ⚠ the mod exes were renamed AoWz*/AoWzEd on 2026-09-09; a list that stops at AoW/AoWCompat/
# AoWDevEd/AoWEd cannot release a lock held by AoWz.exe or AoWzEd.exe.
AOW_PROCS = list(zigexe.LOCKING_PROCESSES)


def kill_aow():
    """Game files are locked while any AoW binary runs; the editor loads the DLLs too.
    Standing authorization to kill them -- the game autosaves per turn."""
    killed = [n for n in AOW_PROCS
              if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                                capture_output=True, text=True).returncode == 0]
    if killed:
        print("  killed running: " + ", ".join(killed))

# (file, VA, expected opcode bytes with the immediate zeroed, immediate offset, description)
SITES = [
    ("AoWTCPCK.dpl", 0x00418A73, "817dec", 3, "TCAI.EvalBattle ability scan 1"),
    ("AoWTCPCK.dpl", 0x00418D1F, "817df4", 3, "TCAI.EvalBattle ability scan 2"),
    ("AoWTCPCK.dpl", 0x004190FA, "817df4", 3, "TCAI.EvalBattle ability scan 3"),
    ("AoWTCPCK.dpl", 0x0041977F, "817df4", 3, "TCAI.EvalBattle ability scan 4"),
    (zigexe.GAME_EXE, 0x00406DEF, "81fe",   2, "TItemBanner.IBannerPopupShow"),
    (zigexe.GAME_EXE, 0x00455DE1, "81fb",   2, "unit hover banner popup"),
]
# identical bytes, applied together or not at all
LOCKSTEP = {zigexe.GAME_EXE: zigexe.COMPAT_EXE}
BASES = {"AoWTCPCK.dpl": 0x00400000,
         zigexe.GAME_EXE: 0x00400000, zigexe.COMPAT_EXE: 0x00400000}


def va2off(d, va, base):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    tbl = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    for i in range(nsec):
        s = tbl + 40 * i
        vsz, rva, rsz, ro = struct.unpack_from("<IIII", d, s + 8)
        if base + rva <= va < base + rva + max(vsz, rsz):
            off = ro + (va - base - rva)
            assert off < ro + rsz, "%08X past raw data" % va
            return off
    raise AssertionError("VA %08X in no section" % va)


def highest_ability_id():
    """The live highest registered ability id, or None if re_tools is unavailable."""
    try:
        sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
        import ability_names
        return max(ability_names.names())
    except Exception:                                                    # noqa: BLE001
        return None


def targets():
    """-> [(filename, va, immoff, opcode_hex, desc)] including the lockstep twins."""
    out = []
    for fn, va, opc, immoff, desc in SITES:
        out.append((fn, va, immoff, opc, desc))
        if fn in LOCKSTEP:
            out.append((LOCKSTEP[fn], va, immoff, opc, desc + " (lockstep)"))
    return out


def main(argv):
    apply_ = "--apply" in argv
    undo = "--undo" in argv
    want = VANILLA if undo else TARGET

    hi = highest_ability_id()
    if hi is None:
        print("NOTE: could not read the live ability list; the drift check is skipped.")
    else:
        print("highest registered ability id: 0x%02X  =>  the bound should be 0x%02X" % (hi, hi + 1))
        if not undo and hi + 1 != TARGET:
            print("\nABORT: this script targets 0x%02X but the live data wants 0x%02X.\n"
                  "An ability was added or removed. APPEND 0x%02X to LADDER here AND to the\n"
                  "LADDER in build_tcablist_ceiling.py -- the two must stay on the same value --\n"
                  "then re-apply both. Until you do, the new ability heals/buffs correctly but is\n"
                  "invisible in the in-combat panel, the banner popups and the tactical AI's scan."
                  % (TARGET, hi + 1, hi + 1))
            return 2

    blobs, plan = {}, []
    for fn, va, immoff, opc, desc in targets():
        path = os.path.join(GAME, fn)
        if not os.path.exists(path):
            print("MISSING: %s" % path)
            return 1
        if fn not in blobs:
            blobs[fn] = bytearray(open(path, "rb").read())
        d = blobs[fn]
        off = va2off(d, va, BASES[fn])
        got_opc = bytes(d[off:off + immoff]).hex()
        if got_opc != opc:
            print("\nABORT: %s %08X opcode is %s, expected %s -- this is not the instruction\n"
                  "this script was written against." % (fn, va, got_opc, opc))
            return 2
        cur = d[off + immoff]
        if cur not in LADDER:
            print("\nABORT: %s %08X immediate is 0x%02X, off the ladder %s.\n"
                  "Someone else owns this byte."
                  % (fn, va, cur, ", ".join("0x%02X" % v for v in LADDER)))
            return 2
        state = ("vanilla" if cur == VANILLA else
                 "raised" if cur == TARGET else "stale")
        print("%-14s %08X  %-8s 0x%02X  %s" % (fn, va, state, cur, desc))
        plan.append((fn, off + immoff, cur, desc))

    todo = [p for p in plan if p[2] != want]
    print("\n%d site(s) already at 0x%02X, %d to change" % (len(plan) - len(todo), want, len(todo)))
    if not todo:
        print("nothing to do")
        return 0
    if not (apply_ or undo):
        print("\nDRY RUN -- pass --apply to write (or --undo to restore 0x%02X)" % VANILLA)
        return 0

    kill_aow()

    # ⚠ BACKUP GATING -- only ever snapshot a file PROVED unpatched.
    # The gate is a POSITIVE test that EVERY site this script owns in that file still holds the
    # vanilla immediate, never "no backup file exists yet". Absence of a backup is not evidence of
    # freshness: on a re-tune (a LADDER bump over an existing install) the file is this script's
    # own previous output, and on --undo it is the patched state by definition. Either would mint a
    # `.pre-*` full of PATCHED bytes that then sits on disk looking authoritative.
    vanilla_files = {fn for fn in {p[0] for p in plan}
                     if all(p[2] == VANILLA for p in plan if p[0] == fn)}
    for fn in sorted({p[0] for p in todo}):
        path = os.path.join(GAME, fn)
        bak = os.path.join(BACKUP_DIR, fn + SUFFIX)   # ⚠ backups/, never the game root
        if undo or os.path.exists(bak):
            continue
        if fn in vanilla_files:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(path, bak)
            print("backup written: %s (every site verified vanilla 0x%02X)"
                  % (bak, VANILLA))
        else:
            print("no backup taken for %s: it is not vanilla at these sites "
                  "(a .pre-* full of patched bytes is worse than none)." % fn)
    for fn, off, cur, desc in todo:
        blobs[fn][off] = want
    for fn in sorted({p[0] for p in todo}):
        open(os.path.join(GAME, fn), "wb").write(bytes(blobs[fn]))
        print("wrote %s" % fn)

    for fn, off, _cur, _desc in todo:
        d2 = open(os.path.join(GAME, fn), "rb").read()
        assert d2[off] == want, "read-back failed in %s at file offset 0x%X" % (fn, off)
    print("read-back verified at every site.")
    if undo:
        return 0
    print("\nIN-GAME TEST NEEDED -- this script cannot confirm anything:")
    print("  1. hover a unit carrying Shield (0xB0) or Reforming Flesh (0xB1) -- each must now")
    print("     appear in the hover popup; hover an item granting a 0xAA-0x%02X ability --"
          % (TARGET - 1))
    print("     likewise in the item banner.")
    print("  2. !! THE REAL ONE: fight a tactical battle against the AI where the AI's decision")
    print("     should be swayed by one of the eight (e.g. a defender with Shield). The AI now")
    print("     SEES those abilities when scoring -- watch for changed, not broken, behaviour.")
    print("  3. Watch for any range-check error in tactical combat. There should be none: these")
    print("     are loop terminators, not the `bound` instructions -- but this is the first time")
    print("     the AI scan loops have ever run past id 0xA9.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
