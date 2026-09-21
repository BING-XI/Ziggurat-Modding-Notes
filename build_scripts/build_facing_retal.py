#!/usr/bin/env python
r"""
build_facing_retal.py -- deferred-retaliation facing for AoWTCPCK.dpl (manual tactical combat).

STATUS 2026-08-27: APPLIED, CONFIRMED WORKING IN-GAME BY THE USER, THEN REVERTED BY CHOICE.
    Applied 2026-08-26/27 (parts a, b, c -- 66 bytes over 4 runs) and validated in a live
    tactical battle: the defender kept its back turned for the incoming blow and snapped round
    only for its own retaliation, exactly as designed. NO DEFECT WAS FOUND.
    Reverted the same day with `--undo` (66 bytes restored, file byte-identical to
    .pre-facingretal) purely because the feature that MOTIVATED it went away: Shield was
    narrowed to ranged-only (vanilla Parry 0x71 already covers melee), so preserving the
    defender's melee-time facing no longer buys anything, and vanilla's on-being-hit turn is
    the more familiar behaviour to leave in place.
    ** This script is KEPT AS A WORKING, RECORDED TECHNICAL OPTION. ** Every site reads its
    original bytes again, so `--apply` re-installs cleanly with no further work. If a future
    feature needs per-strike defender facing in manual tactical combat, re-apply this rather
    than re-deriving it -- and re-read the DO NOT DO THESE list below first, all of it still
    applies.

Design source: "Modding Resources/Zig notes/Shield_And_Retaliation_Facing_Spec_2026-08-26.md"
sections 3.1 / 3.2 / 3.4b.  Background only (out of scope):
"Modding Resources/Zig notes/Facing_Mechanics_Feasibility_2026-08-25.md".

WHAT IT DOES -- three independent edits, selectable with --parts:

  a  Remove the on-being-hit turn.
     Vanilla `TCMeleeMoveTE.LastMove` state 0 turns the DEFENDER to face its attacker the
     instant the blow is declared (0x004092B9-0x0040931F: attackerFacing+3, SetDirection,
     mod-6 wrap, SetDirection again).  Part A jumps that whole block over to the join at
     0x00409320.  A unit struck from behind now keeps its back to the attacker.

  b  Add the just-before-retaliation turn.
     Hook 0x00409BB3, the head of `ExecuteStrike`'s `side flag != 0` arm -- the retaliation
     branch, reached once per retaliation strike and never otherwise (its only inbound edge
     is the `jne` at 0x00409B81).  The cave computes attackerFacing+3 (mod 6) and hands it
     to the DEFENDER's `TUnitHS.SetDirection`, then re-issues the 6 displaced bytes and
     resumes at 0x00409BB9.  Net effect: the victim stays turned away for your blow, then
     snaps round on its own swing.

  c  Remove the touch-ability TARGET re-face.
     0x00409F2A jumps to the block's own continuation 0x0040A06C.  The touch ACTOR re-face
     at 0x00409E60 is deliberately KEPT (it is the exact mirror of melee's 0x004092B4, which
     part A keeps, and part B depends on it -- see "the +3 idiom" below).

DEPENDENCY between a and b: the cave reads the ATTACKER's facing byte and adds 3.  That is
only the defender->attacker direction because 0x004092B4 (state 0, kept by part A) already
faced the attacker at its target, and because the two are adjacent.  If 0x004092B4 is ever
removed, the cave must be rewritten to recompute with `AoWTC.GetMeleeDirIndex @0x00430C58`
from the two hexes (HS+0x04 -> TMapField, X = byte [field+0x10], Y = byte [field+0x11]).

DO NOT DO THESE -- each one has cost someone real time:

 1. ** Do NOT NOP the skipped spans at a or c. **  Live .reloc entries sit inside both:
    0x004092D3 and 0x0040930E in a's span, and 0x00409F44 / 0x00409F83 / 0x00409FCD /
    0x0040A026 in c's.  A .dpl rebases, so the loader rewrites those disp32s at load time to
    a machine-dependent value.  Under a NOP run that turns into base-dependent junk
    instructions -- the documented mechanism behind "crashes on his machine, not mine,
    identical files" in the sibling AoWx project.  Jump OVER the span; leave the bytes
    physically intact and never executed.  (c's last two relocs are not even dead: they live
    in the Wall-Crushing block at 0x00409F9A-0x0040A067, which stays reachable through the
    two guards at 0x00409F1F / 0x00409F28.)

 2. ** Part c must jump to 0x0040A06C, never 0x00409F9A. **  0x00409F9A is
    `cmp dword [eax+0x3c],0x75` -- a Wall-Crushing branch head, not a join.  The re-face
    block's own two exits (the `jbe` at 0x00409F63 and the `jmp` at 0x00409F95) both target
    0x0040A06C, so that is the "block ran and finished" continuation.

 3. ** Do NOT touch 0x0040AAAF. **  It is the opposite assignment -- it copies the TARGET's
    facing onto the ACTOR, as part of the Possess / appearance-swap path that also calls
    SetUnitGFXResourceIndex at 0x0040AA67.

 4. ** pushad/popad in the cave is mandatory. **  ExecuteStrike's prologue is only
    `push ebp; mov ebp,esp; add esp,-0x18; mov [ebp-4],eax` -- it does NOT push EBX/ESI/EDI,
    but its caller `LastMove` does (0x00409062-0x00409064).  A cave clobbering them would
    corrupt LastMove's saved registers.  It is free: nothing is live at the hook (the
    previous instruction is the call to GetMeleeStrike, whose result went to the stack), and
    EFLAGS are dead because the resume instruction 0x00409BB9 `cmp byte [eax+0x10],0` sets
    them itself -- no pushfd needed.

 5. ** Wrap the direction BEFORE the call. **  `SetDirection @0x5578480C` range-checks
    nothing; vanilla's two-call idiom leaves the facing byte transiently holding 7/8/9.  The
    cave writes only 1..6, so the sprite index range narrows, never widens.

WHY THIS CHANGES NO COMBAT NUMBER.  Every strike delta and DV is precomputed at 0x00409208
(`TMeleeRound.Calculate` -> `CalculateStrikes`), and nothing in Calculate / CalculateStrikes /
CreateStrikeCA / StatisticsToDV reads hex geometry -- no GetXhx, no GetYhx, no field lookup,
no direction call anywhere in the chain.  Facing is consumed only by the renderer
(`TTacticalCombatUnitHS.Show @0x00421EE0`, sprite index = facing + K).

CAVE 0x00438200 -- OCCUPANCY MAP OF AoWTCPCK.dpl's TAIL (this map exists in no other build
script, because one of its owners is not a build script at all):

    0x00437FA0 - 0x00437FD2   Blood Types mod -- BH spurt cave            (51 B)
    0x00437FE0 - 0x00438014   Blood Types mod -- ground blood             (53 B)
    0x00438018 - 0x0043802A   Blood Types mod -- Show cave 3A             (19 B)
    0x0043802C - 0x00438038   Blood Types mod -- Show cave 3B             (13 B)
    0x0043803C - 0x0043807F   Blood Types mod -- corpse blood             (68 B)
    0x00438080 - 0x004380FF   free
    0x00438100 - 0x0043810C   build_spellcast_tcpck.py CAVE_BASE          (13 B)
    0x0043810D - 0x00466C0F   free -- 191,221 contiguous zero bytes
    0x00438200 - 0x00438232   THIS SCRIPT (51 B); 0x00438233-0x0043823F asserted zero

** Grepping build_scripts/ is NOT sufficient for this binary. **  The Blood Types caves are
installed by  <game dir>\Modding Resources\AoW1 Modding\Projects\BloodTypes\install_blood_mod.py,
which lives outside build_scripts/ entirely; a grep of the 100-odd build scripts finds only
build_spellcast_tcpck.py and misses 0x00437FA0-0x0043807F completely.  Byte-check the live
file before claiming any address here.

REVERT-ORDER NOTE.  The Blood Types installer has no surgical revert -- its documented
uninstall restores a `.backup` full-file copy, which would wipe all three edits AND the cave.
If anyone ever runs it, re-run `build_facing_retal.py --apply` afterwards.

USAGE
    python build_scripts/build_facing_retal.py                 status / dry run, writes nothing
    python build_scripts/build_facing_retal.py --dis           also print the cave disassembly
    python build_scripts/build_facing_retal.py --apply         install (backup -> .pre-facingretal)
    python build_scripts/build_facing_retal.py --undo          surgical revert, touches no backup
    ... --apply --parts a,c                                    per-part selection (default a,b,c)
"""
import os
import sys
import struct
import shutil
import hashlib
import argparse
import subprocess

from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_GRP_JUMP, CS_GRP_CALL, x86

# game dir = two levels up from this script (<game>/Modding Resources/build_scripts/);
# override with the AOW_GAME_DIR environment variable.
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWTCPCK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-facingretal")
IMAGE_BASE = 0x00400000

AOW_PROCS = ("AoW", "AoWCompat", "AoWDevEd", "AoWEd")

# ---------------------------------------------------------------- addresses
SITE_A = 0x004092B9          # defender re-face block head        (3 bytes displaced)
JOIN_A = 0x00409320          # state := 2 join
SITE_B = 0x00409BB3          # ExecuteStrike retaliation arm head (6 bytes displaced)
RESUME_B = 0x00409BB9
SITE_C = 0x00409F2A          # touch TARGET re-face block head    (6 bytes displaced)
JOIN_C = 0x0040A06C          # the re-face block's own continuation
SETDIR = 0x00402AF4          # import thunk -> AoWEPACK.dpl!AoWE.TUnitHS.SetDirection

CAVE = 0x00438200
CAVE_RESERVE = 0x40          # asserted-zero zone; the body must fit inside it

# .reloc entries that must survive intact underneath the jumped-over spans (see trap 1)
SPAN_RELOCS = (0x004092D3, 0x0040930E,                       # part a
               0x00409F44, 0x00409F83, 0x00409FCD, 0x0040A026)  # part c

CAVE_SRC = """
    pushad
    mov   eax, [ebp-4]                  ; TCMeleeMoveTE (ExecuteStrike's own frame)
    mov   eax, [eax+0x1c]               ; attacker TTacticalCombatUnit
    mov   eax, [eax+0x60]               ; attacker HS
    movzx edx, byte ptr [eax+0x14]      ; attacker facing, 1..6
    add   edx, 3                        ; opposite direction
    cmp   edx, 6
    jbe   lbl_ok
    sub   edx, 6                        ; wrap BEFORE the call -- SetDirection range-checks nothing
lbl_ok:
    mov   eax, [ebp-4]
    mov   eax, [eax+0x28]               ; defender TTacticalCombatUnit (non-nil: state 0 bails at 0x004091D9)
    mov   eax, [eax+0x60]               ; defender HS
    call  0x{setdir:08X}                ; TUnitHS.SetDirection -- EAX=self, DL=dir
    popad
    mov   eax, [ebp-4]                  ; re-issue the 6 displaced bytes
    mov   eax, [eax+0x34]
    jmp   0x{resume:08X}
"""


# ---------------------------------------------------------------- PE helpers
def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    out, sec = [], pe + 24 + opt
    for _ in range(nsec):
        name = d[sec:sec + 8].rstrip(b"\0").decode(errors="replace")
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, sec + 8)
        out.append((name, vaddr, raw, max(vsize, rsize)))
        sec += 40
    return pe, opt, out


def va2off(d, va):
    _pe, _opt, secs = sections(d)
    rva = va - IMAGE_BASE
    for _name, vaddr, raw, size in secs:
        if vaddr <= rva < vaddr + size:
            return raw + (rva - vaddr)
    return None


def reloc_vas(d):
    """Every VA carrying a type-3 base relocation."""
    pe, _opt, _secs = sections(d)
    dd = pe + 24 + 96
    rva, size = struct.unpack_from("<II", d, dd + 5 * 8)
    if not rva or not size:
        return set()
    off = va2off(d, IMAGE_BASE + rva)
    if off is None:
        return set()
    out, end, p = set(), off + size, off
    while p < end - 8:
        page, blk = struct.unpack_from("<II", d, p)
        if blk < 8:
            break
        for i in range((blk - 8) // 2):
            e = struct.unpack_from("<H", d, p + 8 + i * 2)[0]
            if (e >> 12) == 3:
                out.add(IMAGE_BASE + page + (e & 0xFFF))
        p += blk
    return out


def rel32(next_va, dst):
    return struct.pack("<i", dst - next_va)


def kill_aow():
    killed = [n for n in AOW_PROCS
              if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                                capture_output=True, text=True).returncode == 0]
    if killed:
        print("  killed running: " + ", ".join(killed))
    return bool(killed)


# ---------------------------------------------------------------- the patch table
def build_cave():
    # keystone chokes on `;` comments -- strip them here, keep them in CAVE_SRC for the reader.
    src = "\n".join(ln.split(";")[0].rstrip()
                    for ln in CAVE_SRC.format(setdir=SETDIR, resume=RESUME_B).splitlines())
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    enc, _ = ks.asm(src, CAVE)
    return bytes(enc)


CAVE_BYTES = build_cave()
CAVE_LEN = len(CAVE_BYTES)

# rows: (va, original bytes, patched bytes, description)
PARTS = {
    "a": [(SITE_A,
           bytes.fromhex("8b45fc"),
           b"\xEB" + struct.pack("<b", JOIN_A - (SITE_A + 2)) + b"\x90",
           "defender re-face block -> jmp short join 0x%08X" % JOIN_A)],
    "b": [(SITE_B,
           bytes.fromhex("8b45fc8b4034"),
           b"\xE9" + rel32(SITE_B + 5, CAVE) + b"\x90",
           "ExecuteStrike retaliation arm -> cave 0x%08X" % CAVE),
          (CAVE,
           b"\x00" * CAVE_LEN,
           CAVE_BYTES,
           "cave_retal_turn (%d bytes)" % CAVE_LEN)],
    "c": [(SITE_C,
           bytes.fromhex("8b45fc8b401c"),
           b"\xE9" + rel32(SITE_C + 5, JOIN_C) + b"\x90",
           "touch TARGET re-face block -> jmp join 0x%08X" % JOIN_C)],
}
PART_TITLE = {
    "a": "remove the on-being-hit turn",
    "b": "turn the defender just before it retaliates",
    "c": "remove the touch-ability TARGET re-face",
}


# ---------------------------------------------------------------- checks
def disasm(code, base):
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    return list(cs.disasm(code, base))


def print_cave():
    print("cave_retal_turn @ 0x%08X -- %d (0x%X) bytes" % (CAVE, CAVE_LEN, CAVE_LEN))
    for ins in disasm(CAVE_BYTES, CAVE):
        print("    %08X  %-18s %s %s" % (ins.address, ins.bytes.hex(" "),
                                         ins.mnemonic, ins.op_str))
    print("    %08X  (%d bytes reserved and asserted zero to 0x%08X)"
          % (CAVE + CAVE_LEN, CAVE_RESERVE - CAVE_LEN, CAVE + CAVE_RESERVE - 1))


def pic_audit():
    """A .dpl rebases: the cave must be rel32/register-only.  Refuse anything else."""
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    cs.detail = True
    bad, span, n = [], 0, 0
    for ins in cs.disasm(CAVE_BYTES, CAVE):
        n += 1
        span = ins.address + ins.size - CAVE
        branch = ins.group(CS_GRP_JUMP) or ins.group(CS_GRP_CALL)
        for op in ins.operands:
            if op.type == x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                bad.append("%08X absolute disp32 memory operand (%s %s)"
                           % (ins.address, ins.mnemonic, ins.op_str))
            if op.type == x86.X86_OP_IMM and not branch and 0x00401000 <= op.imm < 0x00466C00:
                bad.append("%08X code-range imm32 outside a rel32 branch (%s %s)"
                           % (ins.address, ins.mnemonic, ins.op_str))
        if branch and ins.bytes[0] not in (0xE8, 0xE9, 0x76, 0xEB) :
            bad.append("%08X unexpected branch encoding %02X" % (ins.address, ins.bytes[0]))
    if span != CAVE_LEN:
        bad.append("disassembly does not cover the emitted body (%d of %d bytes)" % (span, CAVE_LEN))
    # every branch target must be inside the cave or one of the two known externals
    for ins in cs.disasm(CAVE_BYTES, CAVE):
        if ins.group(CS_GRP_JUMP) or ins.group(CS_GRP_CALL):
            t = ins.operands[0].imm if ins.operands[0].type == x86.X86_OP_IMM else None
            if t is None:
                bad.append("%08X indirect branch in a cave" % ins.address)
            elif not (CAVE <= t < CAVE + CAVE_LEN) and t not in (SETDIR, RESUME_B):
                bad.append("%08X branches to unexpected 0x%08X" % (ins.address, t))
    return bad, n


def row_state(d, va, orig, new):
    off = va2off(d, va)
    if off is None:
        return "NOSECT", None
    cur = bytes(d[off:off + len(orig)])
    if cur == new:
        return "INSTALLED", cur
    if cur == orig:
        return "VANILLA", cur
    return "FOREIGN", cur


def part_state(d, key):
    states = [row_state(d, va, o, n)[0] for va, o, n, _ in PARTS[key]]
    if all(s == "INSTALLED" for s in states):
        return "INSTALLED"
    if all(s == "VANILLA" for s in states):
        return "VANILLA"
    if "FOREIGN" in states or "NOSECT" in states:
        return "FOREIGN"
    return "MIXED"


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def write_file(data):
    for attempt in (1, 2):
        try:
            with open(TARGET, "wb") as fh:
                fh.write(bytes(data))
            return
        except PermissionError:
            if attempt == 2:
                raise
            print("  file is locked -- killing any running AoW binary and retrying")
            kill_aow()


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="deferred-retaliation facing for AoWTCPCK.dpl (a: no turn on being hit, "
                    "b: turn just before retaliating, c: no touch-target re-face)")
    ap.add_argument("--apply", action="store_true", help="write the patch")
    ap.add_argument("--undo", action="store_true", help="surgical revert (touches no backup)")
    ap.add_argument("--dis", action="store_true", help="print the cave disassembly")
    ap.add_argument("--parts", default="a,b,c",
                    help="comma-separated subset of a,b,c (default all)")
    a = ap.parse_args()

    if a.apply and a.undo:
        sys.exit("ERROR: --apply and --undo are mutually exclusive.")
    sel = [p.strip().lower() for p in a.parts.split(",") if p.strip()]
    if not sel or any(p not in PARTS for p in sel):
        sys.exit("ERROR: --parts takes a subset of a,b,c (got %r)" % a.parts)

    print("build_facing_retal -- AoWTCPCK.dpl deferred-retaliation facing")
    print("target: %s" % TARGET)
    if not os.path.exists(TARGET):
        sys.exit("ERROR: not found: %s" % TARGET)

    # --- the cave is audited before the file is even opened -------------------
    bad, ninsn = pic_audit()
    if bad:
        print("\nCAVE AUDIT FAILED:")
        for b in bad:
            print("  " + b)
        sys.exit("ABORT: the cave is not position-independent. Nothing written.")
    print("cave audit OK: %d instructions, %d bytes, rel32/register-only, "
          "branch targets in {cave, 0x%08X, 0x%08X}" % (ninsn, CAVE_LEN, SETDIR, RESUME_B))
    if CAVE_LEN > CAVE_RESERVE:
        sys.exit("ABORT: cave body %d bytes exceeds the %d-byte reservation." % (CAVE_LEN, CAVE_RESERVE))
    if a.dis:
        print()
        print_cave()

    d = bytearray(open(TARGET, "rb").read())
    relocs = reloc_vas(d)
    print("\n%d type-3 relocations in the image" % len(relocs))

    # --- reloc safety --------------------------------------------------------
    for key in PARTS:
        for va, orig, new, desc in PARTS[key]:
            hit = [x for x in range(va, va + len(orig)) if x in relocs]
            if hit:
                sys.exit("ABORT: part %s writes over .reloc entries at %s (%s). Nothing written."
                         % (key, ", ".join("0x%08X" % x for x in hit), desc))
    missing = [x for x in SPAN_RELOCS if x not in relocs]
    if missing:
        sys.exit("ABORT: the .reloc entries that must survive under the jumped-over spans are "
                 "absent: %s -- this file is not what the spec measured. Nothing written."
                 % ", ".join("0x%08X" % x for x in missing))
    print("reloc check OK: no displaced byte is relocated; all %d span relocs "
          "(%s) present and left intact" % (len(SPAN_RELOCS),
                                            ", ".join("0x%08X" % x for x in SPAN_RELOCS)))

    # --- cave tail must still be zero ---------------------------------------
    coff = va2off(d, CAVE)
    if coff is None:
        sys.exit("ABORT: cave VA 0x%08X is not in any section." % CAVE)
    tail = bytes(d[coff + CAVE_LEN:coff + CAVE_RESERVE])
    if any(tail):
        sys.exit("ABORT: the reserved zone 0x%08X-0x%08X is not zero (%s) -- someone else has "
                 "claimed it. Nothing written." % (CAVE + CAVE_LEN, CAVE + CAVE_RESERVE - 1,
                                                   tail.hex(" ")))

    # --- status --------------------------------------------------------------
    print()
    states = {}
    for key in ("a", "b", "c"):
        st = part_state(d, key)
        states[key] = st
        mark = "*" if key in sel else " "
        print("%s part %s  %-9s  %s" % (mark, key, st, PART_TITLE[key]))
        for va, orig, new, desc in PARTS[key]:
            rs, cur = row_state(d, va, orig, new)
            show = (cur or b"")[:12]
            print("      %08X  %-9s  %-46s %s%s"
                  % (va, rs, desc, show.hex(" "), " ..." if len(cur or b"") > 12 else ""))
            if rs == "FOREIGN":
                print("      %8s  expected vanilla %s\n      %8s   or patched  %s"
                      % ("", orig.hex(" ")[:60], "", new.hex(" ")[:60]))
    print("\n(* = selected)")

    bad_sel = [k for k in sel if states[k] in ("FOREIGN", "MIXED")]
    if bad_sel:
        sys.exit("\nABORT: part(s) %s hold bytes that are neither vanilla nor this script's "
                 "output. Refusing to guess. Nothing written." % ", ".join(bad_sel))

    if not (a.apply or a.undo):
        print("\nDry run -- nothing written, no backup taken.")
        print("  --apply to install, --undo to revert, --dis for the cave disassembly.")
        return

    want_installed = bool(a.apply)
    todo = [k for k in sel if (states[k] == "INSTALLED") != want_installed]
    if not todo:
        print("\nAlready %s for part(s) %s -- nothing to do (idempotent). File untouched."
              % ("installed" if want_installed else "reverted", ", ".join(sel)))
        return

    # --- backup gate ---------------------------------------------------------
    # Only ever take a .pre-* snapshot from a file this feature has NOT touched.  The gate is
    # a positive test that every one of our sites reads its ORIGINAL bytes (and the cave is
    # zero) -- never "the backup file does not exist yet", which would happily snapshot our
    # own previous output on a re-tune, and never on the --undo path, where the current file
    # is the patched state by definition.
    if a.apply:
        pristine = all(part_state(d, k) == "VANILLA" for k in PARTS)
        if os.path.exists(BACKUP):
            print("\nbackup kept: %s (not overwritten)" % os.path.basename(BACKUP))
        elif not pristine:
            print("\nNO BACKUP TAKEN: part(s) %s are already installed, so the current file is "
                  "this script's own output, not a pre-feature state. The revert path is --undo."
                  % ", ".join(k for k in PARTS if part_state(d, k) != "VANILLA"))
        else:
            kill_aow()
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(TARGET, BACKUP)
            print("\nbackup -> %s" % os.path.basename(BACKUP))
    else:
        print("\n(--undo: the backup is neither read nor written)")

    # --- write ---------------------------------------------------------------
    kill_aow()
    before = sha(TARGET)
    written = 0
    for key in todo:
        for va, orig, new, desc in PARTS[key]:
            off = va2off(d, va)
            cur = bytes(d[off:off + len(orig)])
            tgt = new if want_installed else orig
            src = orig if want_installed else new
            if cur == tgt:
                continue
            if cur != src:      # belt and braces: verify immediately before the write
                sys.exit("ABORT: %08X changed under us (have %s, expected %s). Nothing written."
                         % (va, cur.hex(" "), src.hex(" ")))
            d[off:off + len(tgt)] = tgt
            written += len(tgt)
            print("  %s %08X  %-46s %s" % ("patch " if want_installed else "revert",
                                           va, desc, tgt.hex(" ")[:48]))
    if not written:
        print("\nnothing to write.")
        return
    write_file(d)
    print("\n%s -- part(s) %s, %d bytes written."
          % ("APPLIED" if want_installed else "UNDONE", ", ".join(todo), written))
    print("sha256 %s -> %s" % (before[:16], sha(TARGET)[:16]))

    if want_installed:
        print("""
STATUS: applied, untested. Nothing here has been run in the game.

NEEDS THE USER'S IN-GAME TEST -- none of this can be checked from the binary:
  * part a  attack a unit from behind or the flank. The victim does NOT spin to face you,
            and its hit/blood animation still plays: no blank frame, no sideways swing,
            no "Blt Error".
  * part b  attack a unit that WILL retaliate: it stays turned away for your blow, then
            snaps to face you immediately before its own swing, animating in the right
            direction.
  * part b  negative case -- attack something that CANNOT retaliate (locked, no melee
            damage, or killed by the first blow). It must never turn.
  * part b  multi-strike -- in a 2- or 3-strike exchange your later blows now land on the
            defender's NEW front. That is the deliberate consequence of turning per strike;
            say now if it does not feel right.
  * part b  first-strike defender -- fight something with First Strike, where the defender
            swings before the attacker. It must still turn correctly, nothing desyncs.
  * part c  a webbed / entangled / turn-undead victim no longer spins to face whoever
            touched it. The TOUCHER still turns.
  * part c  Wall Crushing (ability 0x75) against a wall behaves exactly as before.
  * Possess / appearance-swap unaffected (0x0040AAAF was deliberately left alone).
  * No crash and no "Exception occurred during ..." dialog across a full manual tactical
    battle, including a siege with walls.

Multiplayer: both peers load this module, so both must carry the identical patch
(standing no-mixed-mod rule).""")


if __name__ == "__main__":
    main()
