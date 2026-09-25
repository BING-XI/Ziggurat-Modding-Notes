#!/usr/bin/env python
r"""
build_marksmanship_atk2.py -- Marksmanship ATK bonus +1/level -> +2/level (5% conversion).

⚠⚠ DO NOT APPLY -- owner ruling 2026-09-24: Marksmanship stays +1 ATK per level.  Kept for the
cave analysis below; its dry run reporting CLEAN is the intended state.

WHY
---
Part of the 10pp -> 5pp to-hit conversion (see Zig notes/FivePct_Conversion_Manifest.md).  Every
ATK/DEF/RES source doubles so the halved slope cancels out.  Marksmanship's bonus is `add bl, al`
where AL = the ability level, i.e. ATK += level.  It must become ATK += 2*level.

WHY THIS NEEDS A SCRIPT AND NOT A BYTE POKE
-------------------------------------------
There is no immediate to double -- the bonus IS the register.  Doubling needs an inserted
`add al, al`, which costs 2 bytes, and those bytes sit at the very START of the cave:

    5580C240  02 D8     add bl, al        <-- the whole Marksmanship bonus
    5580C242  56        push esi          <-- the Cave/Depths -2 malus block begins
    ...
    5580C287  C3        ret

So the entire 72-byte body has to move down 2 bytes.  The cave at 0x5580C240 is UNOWNED -- no
build script emits it; `build_marksmanship8.py` only HOOKS it (`call 0x5580C240` @0x5576E689) and
verifies the call target.  This script therefore takes ownership of the relocation.

RELOCATION ANALYSIS (all four branch kinds enumerated from the live bytes)
-------------------------------------------------------------------------
  * 4 internal rel8 jumps, all -> 0x5580C286.  Source AND target both move +2, so every
    displacement is UNCHANGED.  Nothing to fix.
  * 1 external rel32: `call 0x5577ED94` @0x5580C273.  The source moves +2 and the target does not,
    so its displacement must DECREASE BY 2.  This is the only fix-up.
  * The single entry point is `call 0x5580C240`, which still lands on the new first instruction.
  * No absolute/`.reloc` operands in the body (checked: the only memory operands are [esi+4],
    [ecx+0x148] and [esp+N], all register-relative).

  new layout:  5580C240  00 C0     add al, al      <-- INSERTED: AL = 2 * level
               5580C242  02 D8     add bl, al          (the original body, shifted +2)
               ...
               5580C289  C3        ret
  The body grows 72 -> 74 bytes, ending at 0x5580C28A.  The 8 free bytes at 0x5580C288..0x5580C28F
  absorb it with 5 to spare; real code resumes at 0x5580C290.  The script asserts that zone is zero
  before writing.

⚠ THE MALUS MOVES WITH IT.  This cave also carries the Cave/Depths -2 ranged malus (gated on Night
Vision 0x27), already doubled to -4 by the conversion's stage 12.  It is preserved verbatim by the
relocation -- this script does NOT re-tune it.

USAGE
    python build_marksmanship_atk2.py            verify / dry run (writes nothing)
    python build_marksmanship_atk2.py --dis      also disassemble before and after
    python build_marksmanship_atk2.py --apply    relocate and insert
    python build_marksmanship_atk2.py --undo     surgical revert (shift back, restore the rel32)
"""
import os, sys, io, json, struct, shutil, argparse, subprocess

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-marksatk2")
IMAGE_BASE = 0x55700000

CAVE      = 0x5580C240        # unowned cave: Marksmanship bonus + Cave/Depths malus
BODY_LEN  = 0x48              # 72 bytes, 0x5580C240..0x5580C287 inclusive
SLACK_END = 0x5580C290        # real code resumes here
CALL_OFF  = 0x33              # offset of `call 0x5577ED94` within the ORIGINAL body
CALL_DEST = 0x5577ED94        # AoWE.TAbstractUnit.GetLocation
INSERT    = b"\x00\xC0"       # add al, al

# The Cave/Depths ranged malus (`sub bl, N`) lives INSIDE this body, and its immediate is a
# stage-12 entry in build_statdouble.py's manifest.  Relocating the body moves that immediate,
# so this script keeps the manifest in lockstep -- otherwise build_statdouble.py aborts with
# "1 sites in stage 12 hold bytes that are neither the live nor the target value".
MANIFEST   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fivepct_manifest.json")
MALUS_PRE  = (0x5580C285, 0x10B685)   # immediate VA / file offset BEFORE the relocation
MALUS_POST = (0x5580C287, 0x10B687)   # ... and after (+2)

AOW_PROCS = ("AoW", "AoWCompat", "AoWDevEd", "AoWEd")


def kill_aow():
    k = [n for n in AOW_PROCS
         if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                           capture_output=True, text=True).returncode == 0]
    if k:
        print("  killed running: " + ", ".join(k))


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


def sync_manifest(applied, write=True, quiet=False):
    """Point build_statdouble.py's stage-12 entry at wherever the malus immediate now lives.

    Idempotent and address-guarded: it rewrites ONLY the single stage-12 entry, and only when that
    entry already holds one of the two known addresses. Anything else is left alone and reported.
    """
    want_va, want_off = MALUS_POST if applied else MALUS_PRE
    known = {MALUS_PRE[0], MALUS_POST[0]}
    try:
        m = json.load(io.open(MANIFEST, encoding="utf-8"))
    except Exception as ex:
        print("  ! could not read fivepct_manifest.json (%s) -- stage-12 address NOT synced" % ex)
        return
    ents = m if isinstance(m, list) else m.get("entries", m)
    hits = [e for e in ents if e.get("stage") == 12]
    if len(hits) != 1:
        print("  ! expected exactly 1 stage-12 manifest entry, found %d -- NOT synced" % len(hits))
        return
    e = hits[0]
    cur = int(e["immVA"], 16)
    if cur not in known:
        print("  ! stage-12 entry points at %08X, which is neither %08X nor %08X -- NOT synced"
              % (cur, MALUS_PRE[0], MALUS_POST[0]))
        return
    if cur == want_va:
        if not quiet:
            print("  stage-12 malus address already %08X -- manifest in sync" % want_va)
        return
    if not write:
        print("  fivepct_manifest.json stage-12 malus is at %08X, should be %08X -- would sync"
              % (cur, want_va))
        return
    e["immVA"] = "0x%08x" % want_va
    e["immFile"] = "0x%x" % want_off
    json.dump(m, io.open(MANIFEST, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("  synced fivepct_manifest.json stage-12 malus %08X -> %08X" % (cur, want_va))


def build_new(orig):
    """orig = the 72-byte body as installed. -> the 74-byte relocated body."""
    body = bytearray(orig)
    # the one external rel32: source moves +2, target does not
    old = struct.unpack_from("<i", body, CALL_OFF + 1)[0]
    src_after = CAVE + 2 + CALL_OFF + 5          # address after the call, once shifted
    struct.pack_into("<i", body, CALL_OFF + 1, CALL_DEST - src_after)
    assert CAVE + CALL_OFF + 5 + old == CALL_DEST, "original rel32 does not reach GetLocation"
    return INSERT + bytes(body)


def state(d):
    off = va2off(d, CAVE)
    cur = bytes(d[off:off + BODY_LEN + 2])
    if cur[:2] == b"\x02\xD8":
        return "clean", off, cur[:BODY_LEN]
    if cur[:4] == INSERT + b"\x02\xD8":
        return "applied", off, cur
    return "foreign", off, cur


def show(d, off, n, base, title):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        print("  (pip install capstone for --dis)"); return
    print("\n  ---- %s" % title)
    for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(bytes(d[off:off + n]), base):
        print("    %08X  %-20s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic + " " + ins.op_str))


def main():
    ap = argparse.ArgumentParser(description="Marksmanship ATK +1/level -> +2/level")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(TARGET):
        sys.exit("ERROR: not found: %s" % TARGET)
    d = bytearray(open(TARGET, "rb").read())
    st, off, cur = state(d)

    print("build_marksmanship_atk2 -- Marksmanship ATK +1/level -> +2/level")
    print("cave %08X, body %d B, slack to %08X\nstate: %s\n" % (CAVE, BODY_LEN, SLACK_END, st.upper()))

    if st == "foreign":
        sys.exit("ABORT: the cave starts with %s -- neither `add bl,al` (clean) nor "
                 "`add al,al; add bl,al` (applied).\nSomething else has moved these bytes; "
                 "investigate before running this script." % cur[:4].hex(" "))

    if a.dis:
        show(d, off, BODY_LEN + 2, CAVE, "current")

    if st == "clean":
        new = build_new(cur)
        grow = d[off + BODY_LEN:off + BODY_LEN + (len(new) - BODY_LEN)]
        print("  grows %d -> %d bytes; zone it grows into: %s"
              % (BODY_LEN, len(new), grow.hex(" ") or "(none)"))
        if any(b for b in grow):
            sys.exit("ABORT: the bytes this cave would grow into are not free.")
        if CAVE + len(new) > SLACK_END:
            sys.exit("ABORT: relocated body would run past %08X into live code." % SLACK_END)

    if not (a.apply or a.undo):
        sync_manifest(st == "applied", write=False)
        print("\n(dry run -- nothing written)")
        return

    if a.undo:
        if st == "clean":
            sync_manifest(False)
            print("nothing to undo."); return
        kill_aow()
        body = bytearray(cur[2:2 + BODY_LEN])           # drop the inserted `add al,al`
        struct.pack_into("<i", body, CALL_OFF + 1, CALL_DEST - (CAVE + CALL_OFF + 5))
        d[off:off + BODY_LEN] = body
        d[off + BODY_LEN:off + BODY_LEN + 2] = b"\x00\x00"   # re-zero the slack we used
        open(TARGET, "wb").write(bytes(d))
        sync_manifest(False)
        print("UNDONE -- body shifted back, rel32 restored, slack re-zeroed.")
        return

    if st == "applied":
        sync_manifest(True)   # reconcile even when the binary needs no change
        print("already applied -- nothing to do (idempotent)."); return
    kill_aow()
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP); print("  backup -> %s" % os.path.basename(BACKUP))
    new = build_new(cur)
    d[off:off + len(new)] = new
    open(TARGET, "wb").write(bytes(d))
    sync_manifest(True)
    print("APPLIED -- Marksmanship now grants +2 ATK per level.")
    if a.dis:
        show(d, off, len(new) + 2, CAVE, "after")


if __name__ == "__main__":
    main()
