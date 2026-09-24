#!/usr/bin/env python3
r"""Audit every RNG draw in the AoW1 binaries and say whether it is lockstep-safe.

AoW1 has two generators and they are NOT interchangeable:

  SYNCED  AoWE.TAoWHSMap.Random @0x5577827C   EAX=map, EDX=n -> 0..n-1
          Draws from map[+0x230], the replicated seed, and writes the advanced value
          back, so every peer walks the same sequence. That value is also what the
          out-of-sync comparator reads (TPlayerControl.GetSyncValue @0x55754CE8).
          Guarded: outside a synchronised context it pops "Invalid AoWHSMap.Random
          use" and returns 0.

  RAW     System.@RandInt (VCL30) through each module's own import thunk.
          Draws from System.RandSeed, a per-process global. Peers diverge unless
          something re-anchored RandSeed from a synced draw first. Inside tactical
          combat that IS the case -- TCombat.Execute @0x557282C8 is exactly
          `System.RandSeed := AoWHSMap.Random($FFFFFF)` -- so raw draws made during
          a battle ride a synchronised seed, and are the RIGHT choice there because
          a synced draw mid-combat would perturb the sync value.

There is also a THIRD standard pattern that makes no draw at all: P4 DERIVED HASH
(build_scripts/rngstd.py), which derives the answer from replicated state instead of
rolling for it. A P4 site references neither generator, so the scan above is blind to
it BY CONSTRUCTION -- `--hash` is what finds those, and without it "the audit is clean"
silently means "I did not look".

The rule this enforces: "Zig notes/12-re-toolchain.md" section 4 (taxonomy + the
four-pattern selection test in 4.10).

Targets are the live modules in GAME (<root>/Ziggurat). Each is diffed against its stock
copy at the game ROOT, which is a byte-clean GOG install: the root is located by the GOG
manifest (goggame-*.hashdb lives only there) and every reference is md5-checked against that
manifest before use. A missing target, a missing reference or a reference that is not stock
is an ERROR (exit 2, nothing audited) -- until 2026-09-23 a missing target printed "(missing)",
counted as zero sites and exited 0, which is how the 2026-09-09 exe rename dropped both mod
exes out of every default run unnoticed.

Usage:
    python rng_audit.py                  # every module, diffed against its root reference
    python rng_audit.py AoWEPACK.dpl     # one module
    python rng_audit.py --owners         # attribute each modded site to a build script
    python rng_audit.py --all-sites      # list stock sites too, not just modded ones
    python rng_audit.py --functions      # which functions draw, and from which generator
    python rng_audit.py --hash           # P4 derived-hash sites (rngstd) -- makes no draw
"""
import os, re, sys, struct, subprocess

TOOLS = os.path.dirname(os.path.abspath(__file__))
# game dir = <root>/Ziggurat, two levels up from this script (<root>/Ziggurat/Modding
# Resources/re_tools/); override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, TOOLS)
from pescan import PE
from zignames import zigexe
from mod_manifest import HASHDB, parse_hashdb, md5

# the vanilla install = the folder holding the GOG manifest (anchored on contents, not depth)
ROOT = os.path.dirname(HASHDB)

# module in GAME -> its stock name at ROOT (None = no stock copy exists anywhere).
# Exe names come from zigexe, never a literal (re_tools/README.md).
REFS = {
    "AoWEPACK.dpl":    "AoWEPACK.dpl",
    zigexe.GAME_EXE:   zigexe.VANILLA_EXE,
    zigexe.COMPAT_EXE: zigexe.VANILLA_COMPAT,
    "AoWTCPCK.dpl":    "AoWTCPCK.dpl",
    "aowInt.dpl":      "aowInt.dpl",
    zigexe.SRC_EDITOR: None,        # the root copy is modded too; the hashdb has no entry
    "HSEPack.dpl":     "HSEPack.dpl",
}
MODULES = list(REFS)

RAW_RE    = re.compile(r"@RandInt|@Random$|Randomize|RandomRange", re.I)
SEED_RE   = re.compile(r"RandSeed", re.I)
SYNC_NAME = "TAoWHSMap.Random"
MARK      = {"SYNC": "ok  ", "RAW": "RAW ", "SEED": "seed"}

# AoWEPACK preferred VAs, hunted as bare constants in EVERY module: a cave in another
# binary reaches these through the rebase-delta idiom (`add esi, 0x55701080 ; call esi`,
# build_party_random.py), which has no call target for the scan above to match.
KNOWN_VAS = {
    0x55701080: ("RAW",  "AoWEPACK thunk -> VCL30 System.@RandInt (by constant)"),
    0x55701030: ("RAW",  "AoWEPACK thunk -> VCL30 System.Randomize (by constant)"),
    0x5577827C: ("SYNC", "AoWE.TAoWHSMap.Random (by constant)"),
    0x558FB720: ("SEED", "IAT slot -> VCL30 System.RandSeed (by constant)"),
}

# Project-installed wrappers. Without these a cave that draws correctly THROUGH a stub is
# invisible to the audit -- it stops printing RAW, but it never starts printing ok either,
# so a later mistake at that site would go unreported. Add any new wrapper here.
WRAPPERS = {
    0x55827000: ("SYNC", "Ziggurat rng_sync stub -> TAoWHSMap.Random "
                         "(build_rng_lockstep.py)"),
}


def exec_ranges(pe):
    """[(va, file_off, length)] for every EXECUTE/CODE section.

    Not just CODE/.text: build_party_random.py puts its cave in a custom `.pty`
    section, so a name whitelist silently skips real modded code.
    """
    d = pe.data
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsize = struct.unpack_from("<H", d, e + 20)[0]
    sec = e + 24 + optsize
    out = []
    for i in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, sec + 8)
        chars = struct.unpack_from("<I", d, sec + 36)[0]
        if chars & 0x20000020:                     # MEM_EXECUTE | CNT_CODE
            out.append((pe.image_base + vaddr, raw, min(vsize, rsize)))
        sec += 40
    return out


def iat_map(pe):
    base, iat = pe.image_base, {}
    rva_dir, _ = pe.dirs[1]
    if not rva_dir:
        return iat
    i = 0
    while True:
        ent = pe.read(rva_dir + i * 20, 20)
        if ent is None or ent == b"\0" * 20:
            break
        oft, ts, fc, name_rva, ft = struct.unpack("<IIIII", ent)
        dll = pe.cstr(name_rva) or "?"
        thunk = oft or ft
        j = 0
        while True:
            v = pe.u32(thunk + j * 4)
            if not v:
                break
            if not (v & 0x80000000):
                nm = pe.cstr(v + 2, 2048)
                if nm:
                    iat[base + ft + j * 4] = dll + "!" + re.sub(r"@[0-9A-F]{8}$", "", nm)
            j += 1
        i += 1
    return iat


def targets(pe):
    """-> (call_targets {va: (kind, label)}, slot_targets {iat_va: (kind, label)})"""
    base, d = pe.image_base, pe.data
    slots = {}
    for slot, nm in iat_map(pe).items():
        leaf = nm.split("!")[-1]
        if SEED_RE.search(leaf):
            slots[slot] = ("SEED", nm)
        elif RAW_RE.search(leaf):
            slots[slot] = ("RAW", nm)
        elif leaf.endswith(SYNC_NAME):
            slots[slot] = ("SYNC", nm)

    calls = {}
    for va, kl in WRAPPERS.items():
        off = None
        for va0, o, ln in exec_ranges(pe):
            if va0 <= va < va0 + ln:
                off = o + (va - va0)
        if off is not None and d[off:off + 8] != bytes(8):   # present, not a zeroed cave
            calls[va] = kl
    for name, frva in pe.exports():
        clean = re.sub(r"@[0-9A-F]{8}$", "", name)
        if clean.endswith(SYNC_NAME):
            calls[base + frva] = ("SYNC", clean)
        elif RAW_RE.search(clean):
            calls[base + frva] = ("RAW", clean)

    # in-module import thunks:  FF 25 <abs32 slot>   =   jmp [slot]
    for va0, off, ln in exec_ranges(pe):
        k = off
        while k < off + ln - 6:
            k = d.find(b"\xFF\x25", k, off + ln)
            if k < 0:
                break
            slot = struct.unpack_from("<I", d, k + 2)[0]
            if slot in slots:
                calls[va0 + (k - off)] = slots[slot]
            k += 1
    return calls, slots


def scan(pe):
    """-> {va: (kind, label, mnemonic)} for every instruction that reaches an RNG entry."""
    calls, slots = targets(pe)
    d, hits = pe.data, {}
    for va0, off, ln in exec_ranges(pe):
        end = off + ln
        for k in range(off, end - 6):
            b = d[k]
            if b in (0xE8, 0xE9):
                va = va0 + (k - off)
                tgt = va + 5 + struct.unpack_from("<i", d, k + 1)[0]
                if tgt in calls:
                    kind, label = calls[tgt]
                    hits[va] = (kind, label, "call" if b == 0xE8 else "jmp")
            elif b == 0xFF and d[k + 1] in (0x15, 0x25):
                slot = struct.unpack_from("<I", d, k + 2)[0]
                if slot in slots:
                    va = va0 + (k - off)
                    if va in calls:            # this IS the thunk, not a caller
                        continue
                    kind, label = slots[slot]
                    hits[va] = (kind, label, "call[]" if d[k + 1] == 0x15 else "jmp[]")
    # A cave may compute the RNG address into a register (the exe rebase-delta idiom:
    # `add esi, 0x55701080 ; call esi`). No call/jmp target to match, so look for the
    # bare constant embedded in code -- otherwise such a draw is invisible to this audit.
    consts = dict(KNOWN_VAS)
    for va, (kind, label) in calls.items():
        consts[va] = (kind, label)
    for va0, off, ln in exec_ranges(pe):
        for k in range(off, off + ln - 4):
            v = struct.unpack_from("<I", d, k)[0]
            if v in consts and (va0 + (k - off)) not in hits:
                kind, label = consts[v]
                hits[va0 + (k - off)] = (kind, label, "const")   # VA of the constant itself
    return hits, calls, slots


_CAVE_INDEX = None
_SCRIPT_CODE = {}           # script -> its text minus the module docstring
# 0x55000000-0x58FFFFFF: AoWEPACK / HSEPack preferred VAs, each unique to one module.
# 0x00400000-0x006FFFFF: the exe range, which the exe pair, AoWDevEd.exe and AoWTCPCK.dpl all
# share (every one is based at 0x400000) -- owners() only credits a script there that NAMES
# the module. Before 2026-09-23 this range was not indexed, so every exe site read UNOWNED.
_HEX_RE = re.compile(r"0x(5[5-8][0-9A-Fa-f]{6})|\b(5[5-8][0-9A-Fa-f]{6})\b"
                     r"|0x((?:00)?[4-6][0-9A-Fa-f]{5})\b")
SHARED_BASE_TOP = 0x55000000


def _cave_index():
    """{VA: {script}} for every module VA literal appearing in build_scripts/*.py."""
    global _CAVE_INDEX
    if _CAVE_INDEX is not None:
        return _CAVE_INDEX
    _CAVE_INDEX = {}
    bs = os.path.join(GAME, "Modding Resources", "build_scripts")
    for fn in sorted(os.listdir(bs)) if os.path.isdir(bs) else []:
        if not fn.endswith(".py"):
            continue
        try:
            text = open(os.path.join(bs, fn), "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        # drop the module docstring: it names OTHER features' addresses in prose, which would
        # attribute their sites to this script
        m = re.search(r'^r?"""', text, re.M)
        if m:
            end = text.find('"""', m.end())
            if end != -1:
                text = text[:m.start()] + text[end + 3:]
        _SCRIPT_CODE[fn] = text
        for m in _HEX_RE.finditer(text):
            _CAVE_INDEX.setdefault(int(m.group(1) or m.group(2) or m.group(3), 16),
                                   set()).add(fn)
    return _CAVE_INDEX


def _names_module(fn, modname):
    """Does script `fn`'s code name `modname` as a target -- by literal or by zigexe constant?"""
    toks = [modname] + ["zigexe." + c for c in ("GAME_EXE", "COMPAT_EXE", "SRC_EDITOR",
                                                "LIVE_EDITOR")
                        if getattr(zigexe, c) == modname]
    if modname in zigexe.EXES:
        toks.append("zigexe.EXES")
    return any(t in _SCRIPT_CODE[fn] for t in toks)


def owners(va, modname, window=0x400, code_re=None):
    """Nearest VA literal at or before `va` in any build script -- that is the cave owner.

    A cave's RNG call sits some bytes past the cave base, so an exact-match grep misses
    it; the nearest preceding literal within `window` bytes is the reliable attribution.
    Below SHARED_BASE_TOP the same VA exists in several modules, so only scripts that name
    `modname` are candidates. `code_re`, if given, must also match the script's code.
    """
    idx = _cave_index()
    cands = {}
    for v, fns in idx.items():
        if va - window <= v <= va:
            if va < SHARED_BASE_TOP:
                fns = set(f for f in fns if _names_module(f, modname))
            if code_re is not None:
                fns = set(f for f in fns if code_re.search(_SCRIPT_CODE[f]))
            if fns:
                cands[v] = fns
    if not cands:
        return []
    best = max(cands)
    return ["%s (+0x%X from %08X)" % (s, va - best, best) for s in sorted(cands[best])]


def preflight(mods, need_refs):
    """-> {module: (target path, reference path or None)}, or exit 2 listing every problem.

    Runs before anything is printed, so a partial audit can never be read as a clean one.
    """
    errs, out, db = [], {}, None
    for m in mods:
        tgt = os.path.join(GAME, m)
        if not os.path.isfile(tgt):
            hint = ""
            if m in (zigexe.VANILLA_EXE, zigexe.VANILLA_COMPAT):
                hint = (" -- %s is the vanilla REFERENCE at the root; the mod pair is %s"
                        % (m, " / ".join(zigexe.EXES)))
            errs.append("target not found: %s%s" % (tgt, hint))
            continue
        ref = None
        if need_refs and REFS.get(m):
            ref = os.path.join(ROOT, REFS[m])
            if not os.path.isfile(ref):
                errs.append("reference not found: %s" % ref)
                continue
            if os.path.samefile(ref, tgt):
                errs.append("target IS its reference (%s) -- GAME resolved to the vanilla "
                            "root; is AOW_GAME_DIR set?" % tgt)
                continue
            if db is None:
                db = parse_hashdb(HASHDB) if os.path.isfile(HASHDB) else {}
            entry = db.get(REFS[m].lower())
            if entry is None or entry[1] != md5(ref):
                errs.append("reference is not stock: %s does not match %s"
                            % (ref, os.path.basename(HASHDB)))
                continue
        out[m] = (tgt, ref)
    if db == {}:
        errs.insert(0, "GOG manifest not found: %s -- no reference can be proved stock" % HASHDB)
    if errs:
        for e in errs:
            print("rng_audit: ERROR: " + e, file=sys.stderr)
        sys.exit(2)
    return out


def enclosing(pe, va, exp_sorted, exp):
    """Name of the exported function containing `va` (Delphi packages export everything)."""
    import bisect
    i = bisect.bisect_right(exp_sorted, va) - 1
    if i < 0:
        return "?"
    start = exp_sorted[i]
    return "%s+0x%X" % (exp[start], va - start)


def by_function(modname, path, ref):
    """Which vanilla/live functions draw RAW and which draw SYNC -- the evidence base
    for 'match the generator the surrounding function already uses'."""
    for label, path in (("LIVE", path), ("PRISTINE", ref)):
        if path is None:
            print("\n-- PRISTINE: none for %s --" % modname)
            continue
        pe = PE(path)
        exp = {}
        for name, frva in pe.exports():
            exp[pe.image_base + frva] = re.sub(r"@[0-9A-F]{8}$", "", name)
        exp_sorted = sorted(exp)
        hits = scan(pe)[0]
        groups = {}
        for va, (kind, _lbl, _m) in hits.items():
            if kind == "SEED":
                continue
            groups.setdefault(kind, []).append(enclosing(pe, va, exp_sorted, exp))
        print("\n-- %s %s --" % (label, os.path.relpath(path, ROOT)))
        for kind in ("SYNC", "RAW"):
            names = sorted(set(n.split("+")[0] for n in groups.get(kind, [])))
            print("   %s: %d site(s) in %d function(s)" %
                  (kind, len(groups.get(kind, [])), len(names)))
            for n in names:
                print("      %s" % n)


def _rngstd_signature():
    """rngstd.SIGNATURE, imported -- never a second copy of the constant here.

    Two copies of a byte string is exactly the drift this convention exists to stop.
    """
    bs = os.path.join(GAME, "Modding Resources", "build_scripts")
    if bs not in sys.path:
        sys.path.insert(0, bs)
    import rngstd
    return rngstd.SIGNATURE


_IMPORTS_RNGSTD = re.compile(r"^\s*(import rngstd|from rngstd import)", re.M)


def hash_sites(pe, sig=None):
    """[va] for every rngstd fmix32 signature in an EXECUTE section of `pe`."""
    if sig is None:
        sig = _rngstd_signature()
    d, hits = pe.data, []
    for va0, off, ln in exec_ranges(pe):
        k = off
        while True:
            k = d.find(sig, k, off + ln)
            if k < 0 or k > off + ln - len(sig):
                break
            hits.append(va0 + (k - off))
            k += 1
    return sorted(hits)


def hash_audit(modname, path):
    """P4 DERIVED HASH sites: scan every EXECUTE section for rngstd's fmix32 signature.

    A P4 site derives its answer from replicated state and makes NO draw, so it
    references neither generator and audit() cannot see it. Anything that rolls
    without drawing has to be found by its arithmetic instead.
    """
    print("\n== %s ==" % modname)
    sig = _rngstd_signature()
    hits = hash_sites(PE(path), sig)
    if not hits:
        print("   P4 sites  none")
        return 0
    print("   P4 sites  %d   (rngstd fmix32: imul eax,eax,0x%s)"
          % (len(hits), sig[2:][::-1].hex().upper()))
    for va in hits:
        # only a script that emits rngstd's bytes can own one -- other scripts name the same
        # cave in their collision lists (build_herodlg_columns.py's .hcol squatters)
        o = owners(va, modname, code_re=_IMPORTS_RNGSTD)
        print("      P4  %08X  imul   rngstd.fmix32   <- %s"
              % (va, ", ".join(o) if o else "UNOWNED (no build script)"))
    return len(hits)


def audit(modname, path, ref, show_all=False, show_owners=False):
    pe = PE(path)
    hits, calls, slots = scan(pe)
    print("\n== %s ==" % modname)
    entries = sorted(set(calls.values()) | set(slots.values()))
    if not entries and not hits:
        print("   no RNG entry point imported, exported or referenced by constant")
        return 0
    if not entries:
        print("   no RNG import/export -- reached only by constant (cross-module delta idiom)")
    for kind, label in entries:
        print("   entry  %-5s %s" % (kind, label))

    # a reference with ZERO sites is still a reference: every live site is then NEW
    ref_hits = scan(PE(ref))[0] if ref else {}

    tot = {}
    for kind, _, _ in hits.values():
        tot[kind] = tot.get(kind, 0) + 1
    print("   sites  " + ", ".join("%d %s" % (v, k) for k, v in sorted(tot.items())) +
          ("   (ref: %s)" % os.path.relpath(ref, ROOT) if ref else
           "   (NO pristine reference -- cannot separate modded from stock)"))

    if not ref:
        if show_all:
            print("   all sites:")
            for va in sorted(hits):
                kind, label, mnem = hits[va]
                print("      %-5s %08X  %-6s %s" % (kind, va, mnem, label))
        return 0
    new = dict((va, v) for va, v in hits.items() if va not in ref_hits)
    changed = dict((va, v) for va, v in hits.items()
                   if va in ref_hits and ref_hits[va][:2] != v[:2])
    if True:
        if not new and not changed:
            print("   MODDED SITES: none -- every RNG draw is stock")
        for tag, group in (("NEW vs reference", new), ("CHANGED vs reference", changed)):
            if not group:
                continue
            print("   %s: %d" % (tag, len(group)))
            for va in sorted(group):
                kind, label, mnem = group[va]
                own = ""
                if show_owners:
                    o = owners(va, modname)
                    own = "   <- " + (", ".join(o) if o else "UNOWNED (no build script)")
                print("      %s %08X  %-6s %s%s" % (MARK[kind], va, mnem, label, own))
    if show_all:
        print("   all sites:")
        for va in sorted(hits):
            kind, label, mnem = hits[va]
            print("      %-5s %08X  %-6s %s" % (kind, va, mnem, label))
    return len(new) + len(changed)


def main():
    args = sys.argv[1:]
    show_all = "--all-sites" in args
    show_owners = "--owners" in args
    mods = [a for a in args if not a.startswith("--")] or MODULES
    paths = preflight(mods, need_refs="--hash" not in args)
    if "--functions" in args:
        for m in mods:
            by_function(m, *paths[m])
        return
    if "--hash" in args:
        n = 0
        for m in mods:
            n += hash_audit(m, paths[m][0])
        print("\n%d P4 derived-hash site(s). These make NO draw, so --owners cannot see "
              "them -- see Zig notes/12-re-toolchain.md section 4.10." % n)
        return
    n = 0
    for m in mods:
        n += audit(m, paths[m][0], paths[m][1], show_all, show_owners)
    print("\n%d modded RNG site(s). A RAW site is correct ONLY inside tactical combat "
          "-- see Zig notes/12-re-toolchain.md section 4. P4 derived-hash sites make no "
          "draw and are invisible here: run --hash as well." % n)


if __name__ == "__main__":
    main()
