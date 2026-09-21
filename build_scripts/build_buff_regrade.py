#!/usr/bin/env python
r"""
build_buff_regrade.py -- re-grade unit-enchantment and combat-boost modifiers onto the ODD grades
that the 5% conversion exists to make expressible.

WHY
---
The 10pp -> 5pp shift halved the to-hit slope and doubled every stat, so every buff landed on an
EVEN number (a vanilla +2 became +4, a vanilla +3 became +6). The whole point of the finer slope was
to make the in-between grades usable. This script spends that headroom: each affected buff drops one
notch onto an odd value it could not previously express.

User decisions 2026-08-24 (see Zig notes/Unit_Enchantments.md):
  * enchantment buffs go one notch down       (+6 -> +5, +4 -> +3, +2 -> +1)
  * Enchanted Weapon lands at +3/+3           (explicitly, not the mechanical +4/+4)
  * Vertigo and Poisoned soften to -3/-3      (the only debuffs re-graded)
  * Monster Slaying / Assassin / Charge -> +5 (conditional "combat boosts", same rule)
Everything not listed keeps its doubled value: Cursed, Entangled, Stunned, Webbed (-4 DEF),
Bloodlust DEF and Fury DEF (-2), the ranged slayer riders (+2/+2 from +1/+1).

RE-TUNE 2026-09-13 (user): Blessed -> DEF +2 / RES +4, and High Prayer Blessing follows it there
(they share the display name "Blessed", and 2026-08-24's E5 equalised their stat effect). Blessed's
DEF/RES and High Prayer's DEF are thereby EXEMPT from the re-grade -- they sit back on the plain
doubled value, so `live == new` for those rows and `--undo` is a no-op there. High Prayer RES alone
ends one above its doubling (vanilla +1, doubled +2, now +4). Nature's Blessing was left at +1/+3:
it has a distinct display name, so nothing forces it to track the pair.
⚠ The card text is a separate owner: `build_pfs_typos.py`, `Ability.pfs` records 168 (Blessed) and
110 (High Prayer). Move both or the numbers on screen contradict the ones in combat.

⚠ TWO ENCODING FORMS, BOTH PRESENT HERE
---------------------------------------
  mov-form : B0 nn          `mov al, imm8`   -- immediate at fn+1
  or-form  : 83 C8 nn       `or eax, imm8`   -- immediate at fn+2  (Poisoned ATK and DAM)
A patcher keyed on one form silently misses the other; every row records its form and the script
asserts the opcode before writing. Combat-boost rows carry their own shapes (`add bl,imm8`,
`add byte [esp],imm8`, `add dword [ebx],imm8`, `add dword [ebx+4],imm8`) and are likewise checked.

⚠ THE CAVE COPIES ARE NOT HERE
------------------------------
Assassin and the cave-side Monster Slaying bonuses live in code caves owned by
`build_assassin.py` (`MELEE_ATK_BONUS` / `MELEE_DAM_BONUS`) and `build_ranged_slayers.py`. They are
re-tuned by editing those constants and re-running them -- with the magebane chain dance, because
their cave terminators are repointed:
    build_magebane.py --undo  ->  owner scripts --apply  ->  build_magebane.py --apply
This script owns ONLY the engine immediates listed below.

⚠ PARENT-MANIFEST SYNC
----------------------
Every byte here is also a row in `fivepct_manifest.json` and/or `damhp_manifest.json`, whose
verifiers accept only "at the recorded live value" or "at the recorded target". Moving a byte off
its recorded target would make both conversions report FOREIGN. So this script rewrites those rows'
`newValue` when it applies, and restores them when it undoes -- the same coupling
`build_marksmanship_atk2.py` maintains for the stage-12 malus. The `live` fields are left alone:
they remain the correct pre-doubling undo target for the parent scripts.

USAGE
    python build_buff_regrade.py            verify / dry run (writes nothing)
    python build_buff_regrade.py --apply
    python build_buff_regrade.py --undo     back to the plain doubled values
"""
import os, sys, io, json, struct, shutil, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_statdouble import kill_aow  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-buffregrade")
IMAGE_BASE = 0x55700000
PARENTS = [os.path.join(HERE, "fivepct_manifest.json"), os.path.join(HERE, "damhp_manifest.json")]

MOV = ("mov",   b"\xB0",         1)    # opcode bytes, immediate offset from fn VA
OR_ = ("or",    b"\x83\xC8",     2)
ADDBL = ("addbl",   b"\x80\xC3",     2)
ADDESP = ("addesp", b"\x80\x04\x24", 3)
ADDEBX = ("addebx", b"\x83\x03",     2)
ADDEBX4 = ("addebx4", b"\x83\x43\x04", 3)

#      group           label                       fn VA        form      live  new  [superseded...]
#
# An optional 7th+ element lists SUPERSEDED grades the live byte may still hold, so a re-tune
# migrates in place instead of needing an --undo/--apply round trip across all 36 immediates.
# Same rule as the cave retune in CLAUDE.md: verify against the installed value OR the new one.
# ⚠ A superseded value can ALIAS a legitimate state: the `1` on the two DEF rows below is at once
# the E2 grade, the pre-doubling value and the vanilla byte, so resolve() cannot tell "E2 is
# installed" from "build_statdouble stage 3 was undone" and would write +2 over a correctly
# un-doubled byte. Harmless while the doubling is applied; prune a superseded entry once no live
# binary can still hold it.
ROWS = [
 # ⚠ 2026-09-13 (user): Blessed and High Prayer Blessing are RAISED to DEF +2 / RES +4, so they no
 # longer take E2's one-notch-down. Three of these four land back on the plain doubled value --
 # i.e. exempt from the re-grade, live == new -- while High Prayer RES goes one ABOVE its doubling
 # (+2 -> +4) because E5's equalisation of the two same-named effects is kept. The 7th element in
 # each row is the superseded 2026-08-24 grade.
 ("enchantment", "Blessed DEF",              0x557BB5E4, MOV,      2,   2,  1),
 ("enchantment", "Blessed RES",              0x557BB5E8, MOV,      4,   4,  3),
 ("enchantment", "Bloodlust ATK",            0x557B9DB4, MOV,      4,   3),
 ("enchantment", "Bloodlust DAM",            0x557B9DBC, MOV,      4,   3),
 ("enchantment", "Dark Gift DAM",            0x557BB730, MOV,      4,   3),
 ("enchantment", "Enchanted Weapon ATK",     0x557BB0EC, MOV,      4,   3),
 ("enchantment", "Enchanted Weapon DAM",     0x557BB0F0, MOV,      4,   3),
 ("enchantment", "Frozen DEF",               0x557BA0B4, MOV,      4,   3),
 ("enchantment", "Fury ATK",                 0x557BB35C, MOV,      6,   5),
 # High Prayer Blessing is matched to Blessed's effect (user, 2026-08-24, re-affirmed 2026-09-13).
 # NOTE the two are in DIFFERENT families -- Blessed is a dispellable TUnitEnchantmentAbility, High
 # Prayer a TDurationAbility status lasting the combat -- so only the STAT EFFECT is equalised here;
 # duration and dispellability are structural and unchanged. ⚠ RES is not a "one notch" move like
 # its neighbours: vanilla +1, doubled +2, now +4.
 ("enchantment", "High Prayer Blessing DEF", 0x557BB80C, MOV,      2,   2,  1),
 ("enchantment", "High Prayer Blessing RES", 0x557BB810, MOV,      2,   4,  3),
 ("enchantment", "Nature's Blessing DEF",    0x557B9CC4, MOV,      2,   1),
 ("enchantment", "Nature's Blessing RES",    0x557B9CC8, MOV,      4,   3),
 ("enchantment", "Poisoned ATK",             0x557B9E68, OR_,     -4,  -3),
 ("enchantment", "Poisoned DAM",             0x557B9E74, OR_,     -4,  -3),
 ("enchantment", "Stone Skin DEF",           0x557BAF40, MOV,      4,   3),
 ("enchantment", "Vertigo ATK",              0x557BAC5C, MOV,     -4,  -3),
 ("enchantment", "Vertigo DEF",              0x557BAC60, MOV,     -4,  -3),
 ("combatboost", "Monster Slaying ATK (vs Dragon, StrikeDV)", 0x5576658A, ADDBL,    6, 5),
 ("combatboost", "Monster Slaying DAM (StrikeDV)",            0x5576658D, ADDESP,   6, 5),
 ("combatboost", "Monster Slaying ATK (CalculateUnitStrikes)",0x5576792A, ADDEBX,   6, 5),
 ("combatboost", "Monster Slaying DAM (CalculateUnitStrikes)",0x5576792D, ADDEBX4,  6, 5),
 ("combatboost", "Charge DAM (CalculateUnitStrikes)",         0x55767872, ADDEBX4,  6, 5),
 ("combatboost", "Charge DAM (CalculateStrikes)",             0x55767BCA, ADDEBX4,  6, 5),
 # Holy/Unholy Champion melee -> +5/+5 (user, 2026-08-24), matching Monster Slaying and Assassin.
 # SIX immediates each: the bonus is applied in THREE strike builders (StrikeDV, and both
 # TMeleeRound tables), ATK and DAM in each. Enumerated by decoding all three functions and
 # correlating every `add` with the ability-id test before it -- not by grepping for the value.
 # Their RANGED branch is already +2/+2, in build_ranged_slayers.py's cave, and stays there.
 ("combatboost", "Holy Champion ATK (StrikeDV)",              0x55766522, ADDBL,    4, 5),
 ("combatboost", "Holy Champion DAM (StrikeDV)",              0x55766525, ADDESP,   4, 5),
 ("combatboost", "Holy Champion DAM (CalculateUnitStrikes)",  0x557678C2, ADDEBX4,  4, 5),
 ("combatboost", "Holy Champion ATK (CalculateUnitStrikes)",  0x557678C6, ADDEBX,   4, 5),
 ("combatboost", "Holy Champion ATK (CalculateStrikes)",      0x55767C1A, ADDEBX,   4, 5),
 ("combatboost", "Holy Champion DAM (CalculateStrikes)",      0x55767C1D, ADDEBX4,  4, 5),
 ("combatboost", "Unholy Champion ATK (StrikeDV)",            0x5576655D, ADDBL,    4, 5),
 ("combatboost", "Unholy Champion DAM (StrikeDV)",            0x55766560, ADDESP,   4, 5),
 ("combatboost", "Unholy Champion DAM (CalculateUnitStrikes)",0x557678FD, ADDEBX4,  4, 5),
 ("combatboost", "Unholy Champion ATK (CalculateUnitStrikes)",0x55767901, ADDEBX,   4, 5),
 ("combatboost", "Unholy Champion ATK (CalculateStrikes)",    0x55767C55, ADDEBX,   4, 5),
 ("combatboost", "Unholy Champion DAM (CalculateStrikes)",    0x55767C58, ADDEBX4,  4, 5),
]


def va2off(d, va):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    sec, rva = e + 24 + opt, va - IMAGE_BASE
    for _ in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, sec + 8)
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
        sec += 40
    return None


def resolve(d):
    """-> [(label, group, immVA, immOff, cur, live, new)] ; aborts on any shape/value surprise."""
    out = []
    for row in ROWS:
        group, label, fva, (fname, opc, ioff), live, new = row[:6]
        superseded = tuple(row[6:])
        fo = va2off(d, fva)
        if bytes(d[fo:fo + len(opc)]) != opc:
            sys.exit("ABORT: %s @%08X is not %s-form (found %s) -- re-derive before writing."
                     % (label, fva, fname, bytes(d[fo:fo + len(opc)]).hex(" ")))
        io_ = fo + ioff
        raw = d[io_]
        cur = raw - 0x100 if raw > 0x7F else raw
        if cur not in (live, new) + superseded:
            sys.exit("ABORT: %s imm @%08X holds %+d -- not the doubled %+d, the re-graded %+d, "
                     "nor any superseded grade %s."
                     % (label, fva + ioff, cur, live, new,
                        "/".join("%+d" % v for v in superseded) or "(none)"))
        out.append((label, group, fva + ioff, io_, cur, live, new))
    return out


def sync_parents(rows, to_new, write=True):
    """Keep fivepct/damhp `newValue` pointing at whatever this script has installed."""
    want = {va: (new if to_new else live) for _l, _g, va, _o, _c, live, new in rows}
    total = 0
    for path in PARENTS:
        if not os.path.exists(path):
            continue
        m = json.load(io.open(path, encoding="utf-8"))
        ents = m["entries"] if isinstance(m, dict) and "entries" in m else m
        n = 0
        for e in ents:
            va = int(e["immVA"], 16)
            if va not in want or "newValue" not in e:
                continue
            # only rows the parent actually VERIFIES matter. build_statdouble.py loads just
            # DOUBLE/HALVE entries, so an UNCHANGED row's newValue is inert bookkeeping and
            # rewriting it would only make the record misleading (e.g. fivepct's Poisoned DAM
            # row, which the DAM/HP pass later moved past).
            #
            # ⚠ EXCEPT an UNCHANGED that THIS script wrote. The flip below is ours and leaves a
            # ` | REGRADE:` marker in `ruling`; without this exemption the flip was ONE-WAY -- the
            # row became invisible here, so neither --undo nor a re-tune could ever restore it,
            # and it would keep asserting the re-graded target after the byte had moved off it.
            # Found 2026-09-13 raising Blessed to +2/+4: both DEF rows sat UNCHANGED/newValue 1
            # while the live byte was heading for 2, which is precisely the FOREIGN state this
            # whole sync exists to prevent. Only marked rows are readmitted; the other 127
            # genuinely-UNCHANGED fivepct rows stay excluded.
            dec = e.get("decision")
            if dec not in (None, "DOUBLE", "HALVE") and not (
                    dec == "UNCHANGED" and " | REGRADE:" in (e.get("ruling") or "")):
                continue
            tgt = want[va]
            # some rows record bytes unsigned (e.g. 252 for -4); preserve that convention
            if isinstance(e["newValue"], int) and e["newValue"] > 127:
                tgt &= 0xFF
            # ⚠ A re-grade of +2 -> +1 lands the byte back on the parent's recorded PRE-doubling
            # value. build_statdouble.py tests `cur == live` first, so such a row would be counted
            # "at-live" and trip its DESYNC warning even though everything is correct. Flip those
            # rows to UNCHANGED while the regrade is installed (the doubling really is a no-op
            # there now), and back to DOUBLE on undo. A verifier that cries wolf is a defect.
            flip = (e.get("decision") is not None and tgt == e.get("live"))
            want_dec = "UNCHANGED" if flip else "DOUBLE"
            need = e["newValue"] != tgt or (e.get("decision") is not None
                                            and e["decision"] != want_dec)
            if need:
                if write:
                    e["newValue"] = tgt
                    if e.get("decision") is not None:
                        e["decision"] = want_dec
                        note = ("build_buff_regrade.py re-graded this to %+d, which equals the "
                                "pre-doubling value -- the conversion's doubling is a no-op here "
                                "while that script is applied." % tgt)
                        r = (e.get("ruling") or "")
                        e["ruling"] = (r.split(" | REGRADE:")[0] + " | REGRADE: " + note).strip(" |") \
                            if flip else r.split(" | REGRADE:")[0]
                n += 1
        if n and write:
            json.dump(m, io.open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        if n:
            print("  %s %-24s %d row(s)" % ("synced" if write else "would sync",
                                            os.path.basename(path), n))
        total += n
    if not total:
        print("  parent manifests already in sync")


def main():
    ap = argparse.ArgumentParser(description="re-grade buffs onto odd values")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    a = ap.parse_args()

    d = bytearray(open(TARGET, "rb").read())
    rows = resolve(d)
    at_new = sum(1 for r in rows if r[4] == r[6])
    at_live = sum(1 for r in rows if r[4] == r[5])
    print("build_buff_regrade -- %d engine immediates\n" % len(rows))
    grp = None
    for label, group, iva, _io, cur, live, new in rows:
        if group != grp:
            print("  [%s]" % group); grp = group
        print("     %-44s imm %08X  %+d   (doubled %+d -> re-graded %+d)%s"
              % (label, iva, cur, live, new, "   <-- at target" if cur == new else ""))
    print("\nstate: %d/%d at the re-graded value" % (at_new, len(rows)))

    if not (a.apply or a.undo):
        print("\nparent-manifest sync that --apply would perform:")
        sync_parents(rows, True, write=False)
        print("\n(dry run -- nothing written)")
        print("REMINDER: the Assassin / cave-side Monster Slaying copies are owned by")
        print("build_assassin.py (MELEE_ATK_BONUS / MELEE_DAM_BONUS) -- retune them there.")
        return

    want_new = not a.undo
    if (at_new == len(rows)) == want_new:
        print("\nnothing to do -- already %s (idempotent)." % ("re-graded" if want_new else "at the doubled values"))
        sync_parents(rows, want_new)
        return
    kill_aow()
    # ⚠ CLAUDE.md 2026-09-10: a snapshot is minted on --apply ONLY, and only from a file proven to
    # be in the pre-patch state. This gate was a bare `not exists`, which meant --undo, or the first
    # --apply after a re-tune, would copy an ALREADY-PATCHED dpl to a name reading "pre-regrade".
    # `at_live == len(rows)` is the proof, the equivalent of build_panic_cleardamage.py gating on an
    # unpatched hook site: every immediate still sits on its plain doubled value.
    if want_new and at_live == len(rows) and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP); print("  backup -> %s" % os.path.basename(BACKUP))
    n = 0
    for label, group, iva, io_, cur, live, new in rows:
        tgt = new if want_new else live
        if d[io_] != (tgt & 0xFF):
            d[io_] = tgt & 0xFF; n += 1
    open(TARGET, "wb").write(bytes(d))
    sync_parents(rows, want_new)
    print("\n%s -- %d immediates written." % ("APPLIED" if want_new else "UNDONE", n))


if __name__ == "__main__":
    main()
