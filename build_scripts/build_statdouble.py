#!/usr/bin/env python
"""
build_statdouble.py  --  AoW1 5%-increment conversion: double every ATK/DEF/RES source.

THE OTHER HALF OF build_hitslope5.py.  Halving the to-hit slope and doubling every stat source is a
verified perfect identity (hit chance AND the full damage distribution are bit-identical); the gain is
that odd/half-steps become expressible.  Neither script is meaningful alone:

    hitslope5 alone   -> every stat point is worth half what it was
    statdouble alone  -> every stat point is worth twice what it was

STAGED BUILD.  This conversion is ~825 individual byte writes across two binaries and two data files.
It is built and verified in stages; only stages listed in STAGES_ENABLED are written.  The game is
never left half-converted because nothing is applied until the whole set is green -- see
Modding Resources/Zig notes/FivePct_Conversion_Manifest.md section 3a.

    stage 1   stat clamps + hero skill economy       16 code immediates   (manifest-driven)
    stage 2   .pfs base stats                       651 data bytes        (built in, below)
    stage 3+  not yet verified -- see the manifest

CODE SITES come from build_scripts/fivepct_manifest.json.  Those addresses are TRUE IMMEDIATE BYTE
addresses, re-anchored with capstone operand decoding: the source manifests gave INSTRUCTION addresses
and 43% were off by 1-4 bytes, which would have written into opcode/ModRM bytes.  Never re-derive an
address by pattern matching; use the manifest.

.PFS TAG MAPS DIFFER PER FILE -- the single most dangerous trap here:

    Unitres.pfs   tag 0x0E = ATK   0x0F = DEF   0x13 = RES
    HERORES.PFS   tag 0x0F = ATK   0x10 = DEF   0x14 = RES   <-- 0x13 is MOVES, NOT RES

Applying the Unitres map to HERORES doubles hero MOVEMENT (24-36 -> 48-72) and silently leaves
RESISTANCE un-doubled.  Both maps were verified from THeroResource.ReadWrite @0x55789FD4 (tag ->
field offset) and cross-checked against THeroResource.UsedSkillPoints @0x55789F50, whose cost
multipliers 5/5/10/5/5/2 identify the fields independently.  Extraction was validated by reproducing
the documented value histograms exactly (Unitres 179 records / 537 fields; HERORES 38 / 114).

ITEMS.PFS and HEROES.PFS are NOT touched: items are an explicit user exception (D2), and HEROES.PFS
is a separate decision that has not been taken.  They also carry no PFS magic and no CRC -- running a
CRC repair over them would destroy four bytes of real data.  The CRC path is gated on the magic.

IDEMPOTENCE.  A doubled stat looks exactly like a legitimate stat, so the data side cannot be probed.
A marker dword is written to free CODE cave space in AoWEPACK.dpl at MARKER_VA, recording which stages
are applied.  BSS is NOT usable for this: its SizeOfRawData is 0, so it has no file bytes at all, and
the naive VA->offset formula maps the old proposed address into .edata (it would corrupt the export
table).  MARKER_VA sits in an 853KB run of zeros verified free and unreferenced.

USAGE
    python build_statdouble.py             verify current state (writes nothing)
    python build_statdouble.py --status    per-stage summary
    python build_statdouble.py --apply     apply every ENABLED stage
    python build_statdouble.py --undo      surgical revert of every applied stage
"""
import os, sys, json, zlib, shutil, struct, argparse, subprocess

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
HERE = os.path.dirname(os.path.abspath(__file__))

DLL = os.path.join(GAME, "AoWEPACK.dpl")
TCPCK = os.path.join(GAME, "AoWTCPCK.dpl")
MODULE_PATHS = {"AoWEPACK.dpl": DLL, "AoWTCPCK.dpl": TCPCK}
MANIFEST = os.path.join(HERE, "fivepct_manifest.json")
IMAGE_BASE = 0x55700000

MARKER_VA = 0x55818000
MARKER_MAGIC = b"Z5PC"

PFS_MAGIC = bytes([0x1C, 0xDF, 0x44, 0x21])
PFS_RESIDUE = 0x2144DF1C          # crc32(d[4:]) of an intact .pfs

STAGES_ENABLED = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12)         # raise as later stages are verified

# .pfs stat tags, PER FILE.  See the header warning -- these are not interchangeable.
PFS_TARGETS = {
    "Unitres.pfs": {0x0E: "ATK", 0x0F: "DEF", 0x13: "RES"},
    "HERORES.PFS": {0x0F: "ATK", 0x10: "DEF", 0x14: "RES"},
}
PFS_EXPECT = {"Unitres.pfs": (179, 537), "HERORES.PFS": (38, 114)}

AOW_PROCS = ("AoW", "AoWCompat", "AoWDevEd", "AoWEd")


# ------------------------------------------------------------------ helpers

def kill_aow():
    killed = [n for n in AOW_PROCS
              if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                                capture_output=True, text=True).returncode == 0]
    if killed:
        print("  killed running: " + ", ".join(killed))


def pe_sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    sec = e + 24 + opt
    out = []
    for _ in range(nsec):
        name = d[sec:sec + 8].rstrip(b"\0").decode(errors="replace")
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, sec + 8)
        out.append((name, vaddr, vsize, raw, rsize))
        sec += 40
    return out


def va2off(d, va):
    rva = va - IMAGE_BASE
    for name, vaddr, vsize, raw, rsize in pe_sections(d):
        if vaddr <= rva < vaddr + max(vsize, rsize):
            off = raw + (rva - vaddr)
            return off if off < len(d) else None
    return None


def marker_read(d):
    off = va2off(d, MARKER_VA)
    if off is None or d[off:off + 4] != MARKER_MAGIC:
        return 0
    return struct.unpack_from("<I", d, off + 4)[0]


def marker_write(d, mask):
    off = va2off(d, MARKER_VA)
    d[off:off + 4] = MARKER_MAGIC
    struct.pack_into("<I", d, off + 4, mask)


def marker_clear(d):
    """Zero the whole marker on undo.  Writing magic+0 instead would leave the four magic bytes
    behind, so --undo would not restore the file byte-identically -- which a byte-diff QA check
    rightly flags, and which would make a later 'is this pristine?' comparison lie."""
    off = va2off(d, MARKER_VA)
    d[off:off + 8] = b"\0" * 8


# ------------------------------------------------------------------ .pfs

def pfs_records(d):
    """-> [(record_id, absolute_body_offset, body_bytes)]"""
    best = None
    for s in range(0, 0x40):
        ids, offs, p = [], [], s
        while p + 8 <= len(d):
            i, o = struct.unpack_from("<II", d, p)
            if ids and (i <= ids[-1] or o <= offs[-1]):
                break
            if i > 0x10000 or o > len(d):
                break
            ids.append(i); offs.append(o); p += 8
        if len(ids) > 5 and (best is None or len(ids) > len(best[1])):
            best = (s, ids, offs)
    if best is None:
        raise ValueError("no .pfs index found")
    S, wids, woffs = best
    N = len(wids)
    small = []
    for p in range(0, S):
        if not (d[p] & 0x80) or p + 5 > len(d):
            continue
        if struct.unpack_from("<I", d, p + 1)[0] != N:
            continue
        ns = d[p] & 0x7f
        if p + 5 + 2 * ns == S:
            small = [(d[p + 5 + 2 * k], d[p + 6 + 2 * k]) for k in range(ns)]
            break
    ids = [i for i, _ in small] + wids
    offs = [o for _, o in small] + woffs
    base = S + 8 * N
    out = []
    for k in range(len(ids)):
        a = base + offs[k]
        b = base + offs[k + 1] if k + 1 < len(offs) else len(d)
        out.append((ids[k], a, d[a:b]))
    return out


def pfs_fields(body, abs_base):
    """-> {tag: (absolute_offset, length)}.  top=True: skip the 4-byte class word."""
    p = 4
    n = body[p]; p += 1
    small, wide = n & 0x7f, 0
    if n & 0x80:
        wide = struct.unpack_from("<I", body, p)[0]; p += 4
    ent = []
    for _ in range(small):
        ent.append((body[p], body[p + 1])); p += 2
    for _ in range(wide):
        t, o = struct.unpack_from("<II", body, p); ent.append((t, o)); p += 8
    ds = p
    order = sorted(range(len(ent)), key=lambda k: ent[k][1])
    f = {}
    for j, k in enumerate(order):
        t, o = ent[k]
        a = ds + o
        b = ds + ent[order[j + 1]][1] if j + 1 < len(order) else len(body)
        f[t] = (abs_base + a, b - a)
    return f


def pfs_sites(path, tagmap):
    """-> [(absolute_offset, tag_name, current_value)] for every stat byte in the file."""
    d = open(path, "rb").read()
    if d[:4] != PFS_MAGIC:
        raise ValueError("%s has no PFS magic -- refusing to touch it" % os.path.basename(path))
    if zlib.crc32(d[4:]) & 0xFFFFFFFF != PFS_RESIDUE:
        raise ValueError("%s CRC residue is wrong BEFORE any edit -- the file is already damaged; "
                         "refusing to stamp a fresh CRC over it" % os.path.basename(path))
    recs = pfs_records(d)
    sites = []
    for rid, abso, body in recs:
        f = pfs_fields(body, abso)
        for tag, name in tagmap.items():
            if tag not in f:
                continue
            off, ln = f[tag]
            if ln != 1:
                continue          # stat bytes are 1 wide; the last record's tail can over-report
            sites.append((off, name, d[off]))
    return d, recs, sites


# ------------------------------------------------------------------ state

def load_manifest():
    m = json.load(open(MANIFEST, encoding="utf-8"))
    return [e for e in m["entries"]
            if e.get("stage") in STAGES_ENABLED and e["decision"] in ("DOUBLE", "HALVE")]


def stage_bit(s):
    return 1 << (s - 1)


def pending_stages(mask):
    """Enabled stages not yet recorded in the marker.  Staging is INCREMENTAL: enabling a new
    stage and re-running must apply only that stage, not refuse because the marker is non-zero."""
    return [s for s in STAGES_ENABLED if not mask & stage_bit(s)]


def applied_stages(mask):
    return [s for s in range(1, 9) if mask & stage_bit(s)]


def code_state(mods, entries):
    """mods: {module_name: bytearray}.  Entries carry their own module -- stage 9 onward touch
    AoWTCPCK.dpl as well as AoWEPACK.dpl, so a single-buffer version silently indexes the wrong file."""
    clean = applied = foreign = 0
    for e in entries:
        d = mods[e["module"]]
        off = int(e["immFile"], 16)
        w = e["width"]
        cur = int.from_bytes(d[off:off + w], "little", signed=True)
        if cur == e["live"]:
            clean += 1
        elif cur == e["newValue"]:
            applied += 1
        else:
            foreign += 1
    return clean, applied, foreign


def main():
    ap = argparse.ArgumentParser(description="AoW1 5% conversion: double ATK/DEF/RES sources")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--repair", action="store_true",
                    help="write target over live for entries in an ALREADY-APPLIED stage "
                         "(re-targeted newValue, or a file restored independently)")
    args = ap.parse_args()

    for p in (DLL, TCPCK, MANIFEST):
        if not os.path.exists(p):
            sys.exit("ERROR: not found: %s" % p)

    mods = {n: bytearray(open(f, "rb").read()) for n, f in MODULE_PATHS.items()}
    dll = mods["AoWEPACK.dpl"]          # the marker lives here; AoWTCPCK carries none
    mask = marker_read(dll)
    entries = load_manifest()

    done = applied_stages(mask)
    pending = pending_stages(mask)

    print("build_statdouble -- double every ATK/DEF/RES source")
    print("stages enabled %s | already applied %s | pending %s\n"
          % (list(STAGES_ENABLED), done or "none", pending or "none"))

    # ---- code immediates, grouped by stage
    for st in STAGES_ENABLED:
        g = [e for e in entries if e.get("stage") == st]
        if not g:
            continue
        c, a, f = code_state(mods, g)
        print("  stage %d  code : %3d entries -- at-live %3d / at-target %3d / UNEXPECTED %d%s"
              % (st, len(g), c, a, f, "   <-- pending" if st in pending else ""))
        if f:
            sys.exit("\nABORT: %d sites in stage %d hold bytes that are neither the live nor the "
                     "target value.\nSomething else has moved them. Investigate first." % (f, st))
        # The marker lives in AoWEPACK.dpl only.  If a stage is recorded applied but its bytes are
        # back at their live values, some file was restored independently -- e.g. AoWTCPCK.dpl put
        # back from a backup while the marker still says stage 9 is in.  Re-running --apply would
        # NOT repair it, because that stage is no longer pending.
        if st in done and c:
            print("     ** DESYNC: stage %d is marked applied but %d of its sites are back at their "
                  "live values.\n     ** A file was restored independently, or the entry was "
                  "re-targeted. Run --repair (NOT --undo,\n     ** which would wipe every layer "
                  "applied since)." % (st, c))

    # ---- .pfs data (stage 2 only).  Parsed whenever stage 2 is enabled so --status can report it.
    pfs_state = {}
    if 2 in STAGES_ENABLED:
        for fn, tagmap in PFS_TARGETS.items():
            path = os.path.join(GAME, "Release", fn)
            try:
                d, recs, sites = pfs_sites(path, tagmap)
            except Exception as ex:
                sys.exit("\nABORT: %s" % ex)
            er, ef = PFS_EXPECT[fn]
            if (len(recs), len(sites)) != (er, ef):
                sys.exit("\nABORT: %s parsed %d records / %d stat fields, expected %d / %d.\n"
                         "The file is not what this script was verified against."
                         % (fn, len(recs), len(sites), er, ef))
            pfs_state[fn] = (path, d, sites)
            print("  stage 2  data : %-12s %d records, %d stat bytes, CRC residue OK%s"
                  % (fn, len(recs), len(sites), "   <-- pending" if 2 in pending else ""))

    if args.status or not (args.apply or args.undo or args.repair):
        print("\n(dry run -- nothing written)")
        if pending:
            extra = ""
            if 2 in pending:
                extra = " + %d .pfs bytes" % sum(len(v[2]) for v in pfs_state.values())
            print("pending stages would write: %d code immediates%s"
                  % (sum(1 for e in entries if e.get("stage") in pending), extra))
        print("\nREMINDER: build_hitslope5.py is the other half. Stages not yet built are still at")
        print("their old values, so the game is not balanced until every stage lands.")
        return

    # ---------------------------------------------------------------- undo
    if args.undo:
        if not mask:
            print("\nnothing to undo -- marker says no stage is applied.")
            return
        kill_aow()
        n = 0
        for e in entries:
            if e.get("stage") not in done:
                continue
            d = mods[e["module"]]
            off = int(e["immFile"], 16); w = e["width"]
            cur = int.from_bytes(d[off:off + w], "little", signed=True)
            if cur == e["newValue"]:
                d[off:off + w] = int(e["live"]).to_bytes(w, "little", signed=True)
                n += 1
        marker_clear(dll)
        for nm, f in MODULE_PATHS.items():
            open(f, "wb").write(bytes(mods[nm]))
        nd = 0
        if 2 in done:
            for fn, (path, d, sites) in pfs_state.items():
                out = bytearray(d)
                for off, name, val in sites:
                    if val % 2 != 0:
                        sys.exit("ABORT: %s offset %s holds %d, which is odd -- it cannot be a "
                                 "doubled value. Refusing to halve." % (fn, hex(off), val))
                    out[off] = val // 2
                    nd += 1
                struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
                assert zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF == PFS_RESIDUE, "CRC repair failed"
                open(path, "wb").write(bytes(out))
        print("\nUNDONE -- stages %s reverted: %d code immediates, %d .pfs bytes. Marker cleared."
              % (done, n, nd))
        print("REMINDER: undo build_hitslope5.py too, or the two halves disagree.")
        return

    # -------------------------------------------------------------- repair / re-target
    if args.repair:
        stale = []
        for e in entries:
            if e.get("stage") not in done:
                continue
            d = mods[e["module"]]
            off, w = int(e["immFile"], 16), e["width"]
            if int.from_bytes(d[off:off + w], "little", signed=True) == e["live"]:
                stale.append(e)
        if not stale:
            print("\nnothing to repair -- every applied stage is at its target.")
            return
        kill_aow()
        for e in stale:
            d = mods[e["module"]]
            off, w = int(e["immFile"], 16), e["width"]
            cur = int.from_bytes(d[off:off + w], "little", signed=True)
            assert cur == e["live"], "verify-before-write failed at %s" % e["immVA"]
            d[off:off + w] = int(e["newValue"]).to_bytes(w, "little", signed=True)
            print("  repair %-12s %s  %s -> %s   %s"
                  % (e["module"], e["immVA"], e["live"], e["newValue"],
                     str(e.get("what", ""))[:58]))
        for nm, f in MODULE_PATHS.items():
            open(f, "wb").write(bytes(mods[nm]))
        print("\nREPAIRED -- %d immediate(s) written. Marker untouched." % len(stale))
        return

    # --------------------------------------------------------------- apply
    if not pending:
        print("\nevery enabled stage is already applied -- nothing to do (idempotent).")
        return
    kill_aow()
    touched = {e["module"] for e in entries if e.get("stage") in pending} | {"AoWEPACK.dpl"}
    def _bak(p):
        return os.path.join(BACKUP_DIR, os.path.basename(p) + ".pre-statdouble")
    backups = [(MODULE_PATHS[m], _bak(MODULE_PATHS[m])) for m in sorted(touched)]
    if 2 in pending:
        backups += [(p, _bak(p)) for p, _, _ in pfs_state.values()]
    for src, dst in backups:
        if not os.path.exists(dst):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(src, dst)
            print("  backup -> %s" % os.path.basename(dst))

    nw = 0
    for e in entries:
        if e.get("stage") not in pending:
            continue
        d = mods[e["module"]]
        off = int(e["immFile"], 16); w = e["width"]
        cur = int.from_bytes(d[off:off + w], "little", signed=True)
        assert cur == e["live"], "verify-before-write failed at %s (%s)" % (e["immVA"], e["module"])
        d[off:off + w] = int(e["newValue"]).to_bytes(w, "little", signed=True)
        nw += 1
    marker_write(dll, mask | sum(stage_bit(s) for s in pending))
    for nm, f in MODULE_PATHS.items():
        open(f, "wb").write(bytes(mods[nm]))

    nd = 0
    if 2 in pending:
        for fn, (path, d, sites) in pfs_state.items():
            out = bytearray(d)
            for off, name, val in sites:
                assert out[off] == val, "verify-before-write failed in %s at %s" % (fn, hex(off))
                assert val * 2 <= 127, "%s %s would overflow a signed byte" % (fn, hex(off))
                out[off] = val * 2
                nd += 1
            struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
            assert zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF == PFS_RESIDUE, "CRC repair failed for " + fn
            open(path, "wb").write(bytes(out))

    tail = ", %d .pfs stat bytes (CRCs repaired)" % nd if nd else ""
    print("\nAPPLIED stages %s -- %d code immediates%s." % (pending, nw, tail))
    print("\n*** build_hitslope5.py must also be applied. Stages outside %s are NOT built --"
          % (done + pending))
    print("*** the game is NOT fully converted and should not be balance-tested yet.")


if __name__ == "__main__":
    main()
