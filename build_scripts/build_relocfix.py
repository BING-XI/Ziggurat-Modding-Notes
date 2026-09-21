#!/usr/bin/env python3
r"""
AoW1 mod -- neutralise STALE BASE RELOCATIONS left inside patched code.

THE DEFECT CLASS
  A `.reloc` HIGHLOW (type 3) entry says "add the rebase delta to the dword at this RVA".
  When a patch overwrites the absolute operand that entry described, THE ENTRY SURVIVES, and
  the loader adds the delta to whatever bytes now occupy those four addresses -- live code --
  on every launch, in memory only.

  ⚠⚠ INVISIBLE TO EVERY STATIC CHECK IN THIS PROJECT.  The file on disk is correct, `dasm.py`
  is correct, a byte-diff against the pristine root binary is correct, and the owning build
  script verifies clean.  The corruption is applied by the loader after all of that.

  Module bases are 64 KB aligned, so the delta's low 16 bits are always zero: only bytes
  RVA+2 and RVA+3 of the relocated dword move.  A stale entry smashes exactly two bytes, two
  bytes into the new instruction stream -- which is why the damage is so localised.

THE BUG THIS WAS BUILT FOR -- the Death Altar
  `AoWE.TAbstractUnit.ExecuteStormDamage @0x55780668` dispatches the per-storm debuff mask.
  The live build replaced the Death arm

      557807F8  66 8b 15 40 08 78 55   mov dx, [0x55780840]      (vanilla, reloc @0x807FB)
  with
      557807FA  eb 1a                  jmp 0x55780816            (no-debuff storms)
      557807FC  66 ba 20 00            mov dx, 0x20              (Death)

  and left the reloc.  The loader rewrites 0x807FD/0x807FE -- the `ba` opcode and the `20`
  immediate -- so ONLY the Death arm executes garbage.  Divine (`0x55780802`) lies past the
  relocated dword and Pestilence (`0x55780808`) keeps its own, still valid, entry.

      Exception EExternalException in module AoWEPACK.dpl at 000807FE.
      External exception 80000003.

  000807FE is the SECOND corrupted byte; 80000003 = STATUS_BREAKPOINT, i.e. the garbage
  decoded to an `int 3`.  Simulated over all 65536 64 KB-aligned deltas: 95 put an `int3` at
  exactly 0x557807FE (base band 0x00BC0000-0x01B30000, where a non-ASLR package lands), and
  exactly ONE delta leaves the instruction intact -- delta 0, which never happens.  ⚠ The
  exception CODE is therefore a function of the load address: the same defect presents as a
  breakpoint on one boot and an access violation on another.

THE FIX
  Flip the entry's 4-bit type from 3 (HIGHLOW) to 0 (IMAGE_REL_BASED_ABSOLUTE).  Type 0 is
  defined as "skip this entry; used to pad a block"; ntdll's `LdrProcessRelocationBlockLongLong`
  (and ReactOS's and Wine's equivalents) do `case 0: break;` without ever reading the offset
  field.  So the 12-bit offset survives as an exact `--undo` key.
  ⚠ ONE byte changes on disk per entry -- the high half of the 16-bit entry word (`3c`->`0c`
  etc.).  No block size, no entry count, no file length changes.
  It is the correct repair and not merely the cheap one: the absolute operand the entry
  described no longer exists, so there is nothing left to relocate.

DETECTION -- two rules, and the first ALONE IS NOT SUFFICIENT
  A  "target dword is not inside [ImageBase, ImageBase+SizeOfImage)".  Needs nothing but the
     module itself.  Vanilla scores 0 across 35 root modules (~225k entries).
     ⚠⚠ SYSTEMATIC FALSE NEGATIVE: when the displaced instruction's operand sat at the END of
     the displaced range, the tail of the old address survives and the residual dword still
     reads as an in-image VA.  `AoWz.exe` 0xABF5 / 0xACA1 / 0x4723C / 0x47274 all leave
     `0x0045A420` or `0x0045A400` behind and rule A calls them clean.
  B  "the byte immediately BEFORE the operand differs from the vanilla twin" -- i.e. the
     opcode/modrm moved, so the operand is orphaned.  A deliberate absolute RETARGET changes
     only the dword and is correctly ignored.  Measured: B is a strict superset of A here and
     produced zero false positives across all 33 packages.
     ⚠ B needs a vanilla twin.  `AoWDevEd.exe`/`AoWzEd.exe` have none -- the root copy is the
     same modded build -- so the editor is covered by rule A only.
  C  the REVERSE check: a type-0 entry whose dword IS in-image and whose preceding byte matches
     vanilla means a feature was reverted and put its absolute operand back UNDER A DISABLED
     RELOCATION.  In `AoWEPACK.dpl`, which always rebases, that is a live defect, not a latent
     one.  See "REVERSE COUPLING" below.

REVERSE COUPLING -- ⚠ FORWARD HAZARD, undo these and you must re-enable their entry
  | undoing this                          | restores                         | entry to re-enable   |
  | build_medal_hpmv.py --undo            | TUnit.GetHits' 0x558E83D4 lookup | AoWEPACK.dpl 0x82B77 |
  | build_clogwin_gate.py --off           | stock prologue @0x451218         | AoWz.exe     0x5121C |
  | build_editor_timerres.py undo         | the Sleep thunk @0x4013C8        | AoWDevEd.exe 0x13CA  |
  | build_tierresearch_exe.py verify-rest | push @0x42EDAD / 0x42EE13        | AoWz.exe 0x2EDAE/14  |
  `--audit` rule C catches it after the fact; running this script with no args also aborts.

USAGE
  python build_relocfix.py                 verify current state of every target (default)
  python build_relocfix.py --audit         rules A + B + C over EVERY module in Ziggurat\ --
                                           the standing check; run it after any feature that
                                           displaces bytes
  python build_relocfix.py --apply         write
  python build_relocfix.py --undo --apply  restore type 3 on exactly the listed entries

⚠ `--audit` globs `Ziggurat\*.dpl|*.exe` only.  `Ziggurat\Ziggurat release\` is staging and is
  NOT covered -- run `re_tools/mod_manifest.py --stage` before cutting a release or the payload
  ships the pre-fix binaries.

Backups to <game>\backups\<name>.pre-relocfix, minted on --apply only.  Idempotent,
verify-before-write, aborts on any mismatch.  Close every AoW binary first.
"""
import os, sys, glob, struct, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
ROOT = os.path.dirname(GAME)                       # the pristine vanilla install
BACKUP_DIR = os.path.join(GAME, "backups")

sys.path.insert(0, HERE)
import zigexe

HIGHLOW, ABSOLUTE = 3, 0

#: modules whose vanilla twin at the ROOT has a different name
TWIN = {zigexe.GAME_EXE: zigexe.VANILLA_EXE, zigexe.COMPAT_EXE: zigexe.VANILLA_COMPAT}
#: no vanilla twin exists -- rule B cannot see these
NO_TWIN = {zigexe.SRC_EDITOR, zigexe.LIVE_EDITOR}

# (rva, file offset of the 16-bit entry word, what displaced the operand).
# The file offset is the key, not the RVA: 23 page-aligned RVAs in AoWEPACK.dpl carry BOTH a
# type-3 entry and a type-0 pad at offset 0, so an (rva, type) lookup can alias the pad.
EXE_ENTRIES = [
    (0x00ABF5, 0x06D014, "e9 hook @0x40ABF0 over `mov eax,[0x45A420]` -- orphan tail, dead"),
    (0x00ACA1, 0x06D026, "e9 hook @0x40AC9C over `mov eax,[0x45A420]` -- orphan tail, dead"),
    (0x02EDAE, 0x06EFEC, "build_tierresearch_exe.py, push @0x42EDAD nop'd out"),
    (0x02EE14, 0x06EFF0, "build_tierresearch_exe.py, push @0x42EE13 nop'd out"),
    (0x04723C, 0x0701B8, "build_herodlg_columns.py e9 @0x447238 -- orphan tail, dead"),
    (0x047274, 0x0701BA, "build_herodlg_columns.py e9 @0x447270 -- orphan tail, dead"),
    (0x05121C, 0x070D12, "build_clogwin_gate.py / build_combatlog_exe.py hook @0x451218"),
]
TABLE = {
    "AoWEPACK.dpl": [
        (0x07CC75, 0x27F3E2, "build_tierresearch_dll.py e9 @0x5577CC72 over "
                             "`mov eax,[0x558FC958]` -- hits two dead nops"),
        (0x0807FB, 0x27F5C4, "ExecuteStormDamage Death/Divine dispatch rewrite -- "
                             "THE DEATH-ALTAR CRASH.  No owning build script."),
        (0x082B77, 0x27F6E4, "build_medal_hpmv.py shrank TUnit.GetHits -- hits inter-function "
                             "padding"),
    ],
    zigexe.GAME_EXE:   list(EXE_ENTRIES),
    zigexe.COMPAT_EXE: list(EXE_ENTRIES),
    zigexe.SRC_EDITOR: [
        (0x0013CA, 0x03D0E0, "build_editor_timerres.py e9 @0x4013C8 over the Sleep thunk.  "
                             "RVA+2 is the MSB of that rel32 -- NOT padding-dead."),
    ],
}

APPLY = "--apply" in sys.argv
UNDO  = "--undo"  in sys.argv
AUDIT = "--audit" in sys.argv


class Mod:
    def __init__(self, path):
        self.path, self.name = path, os.path.basename(path)
        self.d = bytearray(open(path, "rb").read())
        d = self.d
        e = struct.unpack_from("<I", d, 0x3C)[0]
        opt = struct.unpack_from("<H", d, e + 20)[0]
        nsec = struct.unpack_from("<H", d, e + 6)[0]
        self.base = struct.unpack_from("<I", d, e + 24 + 28)[0]
        self.sizeimg = struct.unpack_from("<I", d, e + 24 + 56)[0]
        rva, size = struct.unpack_from("<II", d, e + 24 + 96 + 5 * 8)
        self.secs = []
        o = e + 24 + opt
        for _ in range(nsec):
            nm = d[o:o + 8].rstrip(b"\0").decode("latin1")
            vs, va, rs, raw = struct.unpack_from("<IIII", d, o + 8)
            self.secs.append((nm, va, vs, raw, rs))
            o += 40
        self.ents = []                   # [(word_off, rva, type)]
        self.by_off = {}                 # word_off -> index
        if rva:
            p = self.r2o(rva)
            end = p + size
            while p < end:
                pg, blk = struct.unpack_from("<II", d, p)
                if blk == 0:
                    break
                for i in range((blk - 8) // 2):
                    wo = p + 8 + i * 2
                    w = struct.unpack_from("<H", d, wo)[0]
                    self.by_off[wo] = len(self.ents)
                    self.ents.append((wo, pg + (w & 0xFFF), w >> 12))
                p += blk

    def r2o(self, rva):
        for nm, va, vs, raw, rs in self.secs:
            if va <= rva < va + max(vs, rs):
                return raw + (rva - va)
        return None

    def dword(self, rva):
        o = self.r2o(rva)
        return None if o is None or o + 4 > len(self.d) else struct.unpack_from("<I", self.d, o)[0]

    def in_image(self, v):
        return v is not None and self.base <= v < self.base + self.sizeimg

    def entry(self, wo, rva):
        """the (word_off, rva, type) triple at wo, asserting it really describes rva"""
        i = self.by_off.get(wo)
        if i is None:
            sys.exit("ABORT: %s has no .reloc entry word at file 0x%X" % (self.name, wo))
        w, r, t = self.ents[i]
        if r != rva:
            sys.exit("ABORT: %s entry word 0x%X describes RVA 0x%X, table says 0x%X"
                     % (self.name, wo, r, rva))
        return t

    def set_type(self, wo, typ):
        w = struct.unpack_from("<H", self.d, wo)[0]
        struct.pack_into("<H", self.d, wo, (typ << 12) | (w & 0xFFF))


def twin_of(name):
    p = os.path.join(ROOT, TWIN.get(name, name))
    return None if name in NO_TWIN or not os.path.exists(p) else p


def sym(modname, va):
    try:
        sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
        import bisect
        from aowsyms import get_symbols
        if modname not in sym._cache:
            pe, base, syms, iat = get_symbols(modname)
            sym._cache[modname] = (sorted(syms), syms)
        addrs, syms = sym._cache[modname]
        i = bisect.bisect_right(addrs, va) - 1
        return "%s+0x%X" % (syms[addrs[i]], va - addrs[i]) if i >= 0 else "?"
    except Exception:
        return "?"
sym._cache = {}


def audit():
    print("[audit] %s -- rules A (out-of-image) + B (twin diff) + C (reverse)" % GAME)
    seen, total = set(), 0
    for p in sorted(glob.glob(os.path.join(GAME, "*.dpl")) + glob.glob(os.path.join(GAME, "*.exe"))):
        name = os.path.basename(p)
        if name.lower() in seen or name == "Ziggurat Manual.exe":
            continue
        seen.add(name.lower())
        try:
            m = Mod(p)
        except Exception as ex:
            print("   %-20s ! %s" % (name, ex)); continue
        tp = twin_of(name)
        tw = None
        if tp:
            try:
                tw = Mod(tp)
            except Exception:
                tw = None
        hits = []
        for wo, r, t in m.ents:
            o = m.r2o(r)
            if o is None or o + 4 > len(m.d) or o < 1:
                continue
            v = struct.unpack_from("<I", m.d, o)[0]
            if t == HIGHLOW:
                if not m.in_image(v):
                    hits.append((r, v, "A out-of-image"))
                elif tw is not None:
                    to = tw.r2o(r)
                    if to is not None and to >= 1 and m.d[o - 1] != tw.d[to - 1]:
                        hits.append((r, v, "B operand orphaned (opcode moved)"))
            elif t == ABSOLUTE and (r & 0xFFF) and m.in_image(v) and tw is not None:
                to = tw.r2o(r)
                if to is not None and to >= 1 and m.d[o - 1] == tw.d[to - 1]:
                    hits.append((r, v, "C operand RESTORED under a disabled reloc -- re-enable it"))
        if not tp:
            print("   %-20s (no vanilla twin -- rules B and C unavailable)" % name)
        if hits:
            total += len(hits)
            print("   %-20s base 0x%08X  %d" % (name, m.base, len(hits)))
            for r, v, why in sorted(hits):
                print("        RVA 0x%06X  VA 0x%08X  dword 0x%08X  %-34s %s"
                      % (r, m.base + r, v, sym(name, m.base + r), why))
    print("[audit] total: %d" % total)
    return total


def types(m, rows):
    """per-entry type, asserting each entry word really describes its RVA"""
    out = []
    for r, wo, note in rows:
        t = m.entry(wo, r)
        if t not in (HIGHLOW, ABSOLUTE):
            sys.exit("ABORT: %s RVA 0x%X carries reloc type %d -- not this script's to touch"
                     % (m.name, r, t))
        out.append(t)
    return out


def kill_running():
    import subprocess
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-Process | Where-Object { $_.ProcessName -match "
                    "'^(AoW|AoWz|AoWCompat|AoWzCompat|AoWDevEd|AoWzEd|AoWEd|AoWSetup)$' } "
                    "| Stop-Process -Force"], capture_output=True)


def main():
    if AUDIT:
        sys.exit(0 if audit() == 0 else 1)

    plan = []
    for name, rows in TABLE.items():
        path = os.path.join(GAME, name)
        if not os.path.exists(path):
            sys.exit("ABORT: %s not found" % path)
        m = Mod(path)
        ts = types(m, rows)
        want = HIGHLOW if UNDO else ABSOLUTE
        need = [(r, wo) for (r, wo, _), t in zip(rows, ts) if t != want]
        print("[relocfix] %-16s base 0x%08X  %d entries  %d type-3 / %d type-0  -> %d to change"
              % (name, m.base, len(rows), ts.count(HIGHLOW), ts.count(ABSOLUTE), len(need)))
        tp = twin_of(name)
        tw = Mod(tp) if tp else None
        for (r, wo, note), t in zip(rows, ts):
            v = m.dword(r)
            print("    RVA 0x%06X  VA 0x%08X  dword 0x%08X  type %d  %s"
                  % (r, m.base + r, v, t, note))
            # rule C: a revert may have put a real operand back under a disabled entry
            if t == ABSOLUTE and tw is not None:
                o, to = m.r2o(r), tw.r2o(r)
                if o and to and m.d[o - 1] == tw.d[to - 1] and m.in_image(v):
                    sys.exit("ABORT: %s RVA 0x%X matches vanilla again -- a feature was "
                             "reverted and its absolute operand is now live under a DISABLED "
                             "relocation.  Re-enable it with --undo --apply." % (name, r))
        if need:
            plan.append((name, path, m, need))

    want = HIGHLOW if UNDO else ABSOLUTE
    if not plan:
        print("[= ] every entry already %s -- nothing to do"
              % ("HIGHLOW (pristine)" if UNDO else "ABSOLUTE (fixed)"))
        return
    if not APPLY:
        n = sum(len(t[3]) for t in plan)
        print("\n[dry] would set type %d on %d entries in: %s\n      Re-run with --apply."
              % (want, n, ", ".join(t[0] for t in plan)))
        return

    kill_running()
    os.makedirs(BACKUP_DIR, exist_ok=True)
    todo = plan
    for name, path, m, need in todo:
        if not UNDO:
            bak = os.path.join(BACKUP_DIR, name + ".pre-relocfix")
            if not os.path.exists(bak):
                shutil.copy2(path, bak)
                print("[bak] %s" % bak)
        for r, wo in need:
            m.set_type(wo, want)
        try:
            open(path, "wb").write(bytes(m.d))
        except PermissionError:
            sys.exit("[x] LOCKED -- close every AoW binary first (%s)" % name)
        print("[w ] %-16s %d entries -> type %d" % (name, len(need), want))
    print("[done] %s" % ("reverted" if UNDO else "applied"))
    if any(t[0] == zigexe.SRC_EDITOR for t in todo):
        print("\n[!] %s is the editor SOURCE.  Run  build_zigeditor.py --apply  "
              "to rebuild %s, or the live editor keeps the bad entry."
              % (zigexe.SRC_EDITOR, zigexe.LIVE_EDITOR))


if __name__ == "__main__":
    main()
