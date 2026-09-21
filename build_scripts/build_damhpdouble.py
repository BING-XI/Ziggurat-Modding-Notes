#!/usr/bin/env python
r"""
build_damhpdouble.py -- double every DAMAGE source and every HP pool (the DAM/HP congruence pass).

THE DESIGN (see Zig notes/DamHP_Double_Decisions.md -- decisions H1-H9 + adopted defaults)
------------------------------------------------------------------------------------------
The 5% conversion doubled ATK/DEF/RES and halved the to-hit slope (an identity). This is the second
identity: double every damage value AND every hit-point pool, so time-to-kill is unchanged and
half-step damage/HP become expressible. Driven by `damhp_manifest.json` (148 entries, every one
byte-verified against the live binaries at build time by the converter that generated it).

WHAT THIS SCRIPT OWNS -- and what it deliberately does NOT
----------------------------------------------------------
Owns (4 internal stages, in apply order):
  1  S4  clamps, prices, AI thresholds, the >=50-damage assert, and the CONVERSION REPAIRS
         (stage-1 clamp mov-twins, Self-Destruct/breath/FlameThrowing attack gaps)
  2  S3  HP and healing immediates (healing caps, High Prayer, Remedy, Showers, walls,
         resurrect/animate, regen floor, MakeDefaultLevelUnit HITS...)
  3  S2  engine damage immediates in BOTH DPLs (combat-spell +0x35 bytes, ranged registrations,
         slayer adds, Wall Crushing / Self-Destruct damage families, hazards, storms, DoT ticks...)
  4  S1  .pfs data: Unitres DAM(0x10)+HITS(0x11), HERORES HP(0x12), HEROES.PFS all five bonus
         tags (0x10/0x11/0x12/0x13/0x15 -- decision H6)

Does NOT own (other scripts, same apply session -- see the decisions doc):
  * hero Get* bounds        -> build_hero_clamps.py      (DAM ceil 60, HP ceil 120, floors 2)
  * NewTurn overheal fix    -> build_newturn_healcap.py  (structural; lifts the HP ceiling to 127)
  * unit computed-HP cap    -> build_medal_hpmv.py       (cave rewrite, cap 120, K 1->2)
  * cave damage constants   -> build_assassin.py, build_ranged_slayers.py, build_turnundead_res.py,
                               build_magebane.py (BONUS_PER 2), build_marksmanship8.py (drop shr)
  * medal DAM ladder        -> build_copper_medal.py  ([0,0,1,2] -- decision H2)
  * ITEMS.PFS damage        -> NOTHING (decision H1: items unchanged, incl. the 5 bolt imms)
  * HERORES DAM (tag 0x11)  -> already x2 by build_hero_chassis_atkdam.py -- MUST NOT double again

ORDERING CONSTRAINTS
--------------------
  * Stage 4 (data) must land WITH or AFTER build_medal_hpmv.py's computed-HP cap: doubled Unitres
    HITS push two units' computed totals past 127 without it. This script REFUSES stage 4 unless
    the cap cave verifies (checked via its marker bytes).
  * The assert raise (stage 1) must land before any doubled damage -- it does, by stage order.
  * HEROES.PFS and ITEMS.PFS carry NO magic and NO CRC -- the CRC repair is gated per file.

IDEMPOTENCE
-----------
Marker dword pair at VA 0x55818008 (file 0x117408): "Z5DH" + u32 stage mask -- directly after
build_statdouble.py's "Z5PC" marker (0x117400), zone byte-verified free. Data-side double-run guard:
per-file-per-tag (count, sum) fingerprints -- PRE and 2xPRE both recognised, anything else aborts.

USAGE
    python build_damhpdouble.py             verify / dry run (writes nothing)
    python build_damhpdouble.py --status    per-stage summary
    python build_damhpdouble.py --apply     apply every pending stage (kills running AoW)
    python build_damhpdouble.py --undo      surgical revert of every applied stage + clear marker

--apply snapshots every target (both .dpl modules and the Release/*.pfs in PFS_PLAN) to
`<game dir>\backups\<file>.pre-damhp`, never beside the target. Those snapshots are a courtesy, not
the revert path -- `--undo` is, and it touches no backup.
"""
import os, sys, io, json, zlib, struct, shutil, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_statdouble import (pfs_records, pfs_fields, kill_aow,           # noqa: E402
                              PFS_MAGIC, PFS_RESIDUE)

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
MANIFEST = os.path.join(HERE, "damhp_manifest.json")
MODULES = {"AoWEPACK.dpl": os.path.join(GAME, "AoWEPACK.dpl"),
           "AoWTCPCK.dpl": os.path.join(GAME, "AoWTCPCK.dpl")}
BACKUP_SUFFIX = ".pre-damhp"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)

MARKER_FILE = 0x117408                 # AoWEPACK.dpl file offset (VA 0x55818008)
MARKER_MAGIC = b"Z5DH"
STAGE_OF = {"S4-clamps-prices-ai": 1, "S3-hp-heal": 2, "S2-engine-dam": 3}
STAGE_NAMES = {1: "S4 clamps/prices/AI/repairs", 2: "S3 hp+heal", 3: "S2 engine damage", 4: "S1 pfs data"}

# statdouble must be fully applied (stages 1..10 + 12 = mask 0x0BFF) -- this pass layers on it.
STATDOUBLE_MARKER_FILE = 0x117400
STATDOUBLE_MASK = 0x0BFF

# unit computed-HP cap: build_medal_hpmv.py's cave must carry the cap before Unitres HITS double.
# The retuned cave writes its own recognisable header; we check its version byte.
MEDAL_CAP_CHECK = ("AoWEPACK.dpl", None)   # filled by --apply via medal_hpmv marker probe (see below)

# ---- .pfs data stage -----------------------------------------------------------------
# fingerprints measured 2026-08-24 (count, sum) of the PRE state; POST = (count, 2*sum)
PFS_PLAN = {
    "Unitres.pfs": {"tags": {0x10: "DAM", 0x11: "HITS"}, "records": 179, "crc": True,
                    "pre": {0x10: (179, 570), 0x11: (179, 1786)}},
    "HERORES.PFS": {"tags": {0x12: "HP"}, "records": 38, "crc": True,
                    "pre": {0x12: (38, 339)}},
    # H6: all five bonus tags. ⚠ NO magic, NO CRC on this file -- never stamp one.
    "HEROES.PFS": {"tags": {0x10: "ATK", 0x11: "DEF", 0x12: "DAM", 0x13: "HP", 0x15: "RES"},
                   "records": 50, "crc": False,
                   "pre": {0x10: (39, 41), 0x11: (37, 45), 0x12: (21, 21),
                           0x13: (2, 4), 0x15: (32, 34)}},
}


def load_manifest():
    m = json.load(io.open(MANIFEST, encoding="utf-8"))
    for e in m:
        e["_stage"] = STAGE_OF[e["stage"]]
    return m


def read_marker(dll):
    if bytes(dll[MARKER_FILE:MARKER_FILE + 4]) != MARKER_MAGIC:
        return 0
    return struct.unpack_from("<I", dll, MARKER_FILE + 4)[0]


def write_marker(dll, mask):
    if mask:
        dll[MARKER_FILE:MARKER_FILE + 4] = MARKER_MAGIC
        struct.pack_into("<I", dll, MARKER_FILE + 4, mask)
    else:
        dll[MARKER_FILE:MARKER_FILE + 8] = b"\x00" * 8


def entry_state(data, e):
    """-> 'live' | 'target' | 'foreign' for one manifest entry against its module bytes."""
    off = int(e["immFile"], 16)
    if "liveBytes" in e:
        cur = bytes(data[off:off + e["width"]]).hex()
        if cur == e["liveBytes"]:
            return "live"
        if cur == e["newBytes"]:
            return "target"
        return "foreign"
    w = e["width"]
    cur = int.from_bytes(data[off:off + w], "little", signed=True)
    curu = int.from_bytes(data[off:off + w], "little", signed=False)
    for name, want in (("live", e["live"]), ("target", e["newValue"])):
        if cur == want or curu == (want & ((1 << (8 * w)) - 1)):
            return name
    return "foreign"


def write_entry(data, e, to_target):
    off, w = int(e["immFile"], 16), e["width"]
    if "liveBytes" in e:
        data[off:off + w] = bytes.fromhex(e["newBytes"] if to_target else e["liveBytes"])
        return
    v = e["newValue"] if to_target else e["live"]
    data[off:off + w] = int(v).to_bytes(w, "little", signed=(v < 0))


def pfs_state(path, plan):
    d = open(path, "rb").read()
    if plan["crc"]:
        if d[:4] != PFS_MAGIC:
            sys.exit("ABORT: %s should carry the PFS magic and does not." % os.path.basename(path))
        if zlib.crc32(d[4:]) & 0xFFFFFFFF != PFS_RESIDUE:
            sys.exit("ABORT: %s CRC residue wrong BEFORE any edit -- refusing." % os.path.basename(path))
    elif d[:4] == PFS_MAGIC:
        sys.exit("ABORT: %s unexpectedly carries a PFS magic -- plan says no CRC." % os.path.basename(path))
    recs = pfs_records(d)
    if len(recs) != plan["records"]:
        sys.exit("ABORT: %s parsed %d records, expected %d." % (os.path.basename(path), len(recs), plan["records"]))
    sites = {t: [] for t in plan["tags"]}
    for rid, abso, body in recs:
        f = pfs_fields(body, abso)
        for t in plan["tags"]:
            if t in f and f[t][1] == 1:
                sites[t].append(f[t][0])
    states = {}
    for t, offs in sites.items():
        n, s = len(offs), sum(d[o] for o in offs)
        pn, ps = plan["pre"][t]
        states[t] = "pre" if (n, s) == (pn, ps) else "post" if (n, s) == (pn, 2 * ps) else "foreign"
    return d, sites, states


def medal_cap_applied():
    """The Unitres HITS double is unsafe until build_medal_hpmv.py's cap is in. That script's
    retune stamps 'HPC2' at VA 0x55818010 (file 0x117410) -- probe it."""
    d = open(MODULES["AoWEPACK.dpl"], "rb").read()
    return d[0x117410:0x117414] == b"HPC2"


def main():
    ap = argparse.ArgumentParser(description="double every DAMAGE source and HP pool")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--repair", action="store_true",
                    help="write target over live for entries in an ALREADY-APPLIED stage "
                         "(re-targeted newValue, or a file restored independently)")
    a = ap.parse_args()

    ents = load_manifest()
    data = {m: bytearray(open(p, "rb").read()) for m, p in MODULES.items()}
    dll = data["AoWEPACK.dpl"]

    sd = struct.unpack_from("<I", dll, STATDOUBLE_MARKER_FILE + 4)[0] \
        if bytes(dll[STATDOUBLE_MARKER_FILE:STATDOUBLE_MARKER_FILE + 4]) == b"Z5PC" else 0
    if sd != STATDOUBLE_MASK:
        sys.exit("ABORT: build_statdouble.py marker mask is 0x%X, expected 0x%X -- the stat\n"
                 "conversion must be fully applied before the DAM/HP pass layers on it." % (sd, STATDOUBLE_MASK))

    mask = read_marker(dll)
    applied = [s for s in (1, 2, 3, 4) if mask & (1 << (s - 1))]
    pending = [s for s in (1, 2, 3, 4) if s not in applied]

    print("build_damhpdouble -- double every DAMAGE source and HP pool")
    print("marker mask 0x%X | applied %s | pending %s\n" % (mask, applied or "none", pending or "none"))

    # ---- code stages 1..3
    for s in (1, 2, 3):
        g = [e for e in ents if e["_stage"] == s]
        st = {"live": 0, "target": 0, "foreign": 0}
        for e in g:
            st[entry_state(data[e["module"]], e)] += 1
        flag = "   <-- pending" if s in pending else ""
        print("  stage %d %-28s : %3d entries -- at-live %3d / at-target %3d / FOREIGN %d%s"
              % (s, STAGE_NAMES[s], len(g), st["live"], st["target"], st["foreign"], flag))
        if st["foreign"]:
            for e in g:
                if entry_state(data[e["module"]], e) == "foreign":
                    off = int(e["immFile"], 16)
                    print("      FOREIGN %s %s holds %s | %s" % (e["module"], e["immVA"],
                          bytes(data[e["module"]][off:off + e["width"]]).hex(" "), e["what"][:60]))
            sys.exit("\nABORT: foreign bytes in stage %d -- investigate before writing." % s)

    # ---- data stage 4
    pfs = {}
    for fn, plan in PFS_PLAN.items():
        path = os.path.join(GAME, "Release", fn)
        d, sites, states = pfs_state(path, plan)
        pfs[fn] = (path, d, sites, states)
        pretty = "  ".join("0x%02X:%s" % (t, states[t]) for t in sorted(states))
        print("  stage 4 %-13s %-15s: %s%s" % ("S1 pfs data", fn, pretty,
              "   <-- pending" if 4 in pending else ""))
        if any(v == "foreign" for v in states.values()):
            sys.exit("\nABORT: %s holds values matching neither the recorded pre-state nor its "
                     "double.\nSomething else changed it -- investigate." % fn)

    if a.status or not (a.apply or a.undo or a.repair):
        print("\n(dry run -- nothing written)")
        if 4 in pending and not medal_cap_applied():
            print("⚠ stage 4 is GATED: build_medal_hpmv.py's computed-HP cap ('HPC2' marker) is not\n"
                  "  installed; doubled Unitres HITS would overflow two units' computed totals.")
        return

    # ------------------------------------------------------------------ undo
    if a.undo:
        if not applied:
            print("nothing to undo -- marker says no stage is applied.")
            return
        kill_aow()
        n = 0
        for e in ents:
            if e["_stage"] in applied and entry_state(data[e["module"]], e) == "target":
                write_entry(data[e["module"]], e, False); n += 1
        write_marker(dll, 0)
        for m, p in MODULES.items():
            open(p, "wb").write(bytes(data[m]))
        nd = 0
        if 4 in applied:
            for fn, (path, d, sites, states) in pfs.items():
                out = bytearray(d)
                for t, offs in sites.items():
                    if states[t] != "post":
                        continue
                    for o in offs:
                        if out[o] % 2:
                            sys.exit("ABORT: %s offset %s odd -- cannot be doubled; refusing." % (fn, hex(o)))
                        out[o] //= 2; nd += 1
                if PFS_PLAN[fn]["crc"]:
                    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
                    assert zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF == PFS_RESIDUE
                open(path, "wb").write(bytes(out))
        print("\nUNDONE -- stages %s: %d code sites, %d data bytes. Marker cleared." % (applied, n, nd))
        print("REMINDER: the owner-script retunes (assassin, turnundead, medal_hpmv, hero_clamps,\n"
              "magebane, marksmanship8, copper_medal) are separate -- undo them individually if intended.")
        return

    # ----------------------------------------------------------------- repair / re-target
    # A stage marked applied can still hold `live` bytes -- a file restored independently, or an
    # entry deliberately RE-TARGETED. --apply cannot help (the stage is not pending) and --undo
    # would wipe every layer applied since, which CLAUDE.md forbids as a re-tune procedure.
    if a.repair:
        stale = [e for e in ents
                 if e["_stage"] in applied and entry_state(data[e["module"]], e) == "live"]
        if not stale:
            print("\nnothing to repair -- every applied stage is at its target.")
            return
        kill_aow()
        for e in stale:
            assert entry_state(data[e["module"]], e) == "live", e["immVA"]
            write_entry(data[e["module"]], e, True)
            print("  repair %-14s %s  %s -> %s   %s"
                  % (e["module"], e["immVA"], e.get("live"), e.get("newValue"),
                     str(e.get("what", ""))[:56]))
        for m, p in MODULES.items():
            open(p, "wb").write(bytes(data[m]))
        print("\nREPAIRED -- %d immediate(s) written. Marker untouched." % len(stale))
        return

    # ------------------------------------------------------------------ apply
    if not pending:
        print("\nevery stage already applied -- nothing to do (idempotent).")
        return
    if 4 in pending and not medal_cap_applied():
        sys.exit("\nABORT: stage 4 refused -- build_medal_hpmv.py's computed-HP cap ('HPC2') is not\n"
                 "installed. Apply that first, or two units' computed HP overflow a signed byte.")
    kill_aow()
    for p in list(MODULES.values()) + [os.path.join(GAME, "Release", fn) for fn in PFS_PLAN]:
        bp = os.path.join(BACKUP_DIR, os.path.basename(p) + BACKUP_SUFFIX)
        if not os.path.exists(bp):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(p, bp); print("  backup -> %s" % bp)

    n = 0
    for s in (1, 2, 3):
        if s not in pending:
            continue
        for e in ents:
            if e["_stage"] == s and entry_state(data[e["module"]], e) == "live":
                write_entry(data[e["module"]], e, True); n += 1
    newmask = mask | sum(1 << (s - 1) for s in pending)
    write_marker(dll, newmask)
    for m, p in MODULES.items():
        open(p, "wb").write(bytes(data[m]))

    nd = 0
    if 4 in pending:
        for fn, (path, d, sites, states) in pfs.items():
            out = bytearray(d)
            for t, offs in sites.items():
                if states[t] != "pre":
                    continue          # already doubled (or empty) -- e.g. after a partial re-run
                for o in offs:
                    assert out[o] * 2 <= 127, "%s %s: %d*2 leaves signed byte" % (fn, hex(o), out[o])
                    out[o] *= 2; nd += 1
            if PFS_PLAN[fn]["crc"]:
                struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
                assert zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF == PFS_RESIDUE, "CRC repair failed " + fn
            open(path, "wb").write(bytes(out))

    print("\nAPPLIED stages %s -- %d code sites, %d data bytes (CRCs repaired where present)." % (pending, n, nd))
    print("REMINDER: this is HALF the session -- the owner-script retunes and the two structural")
    print("scripts (newturn_healcap, medal_hpmv cap) must land in the same sitting. See the decisions doc.")


if __name__ == "__main__":
    main()
