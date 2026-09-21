#!/usr/bin/env python3
r"""
build_hpbar_clamp.py -- fix the VANILLA "Blt Error" when an HP bar is drawn from a NEGATIVE hit-point
value (in practice: a wall crushed past 0 by Wall Crushing).

THE BUG (vanilla, byte-verified 2026-07-22)
-------------------------------------------
`AoWE.HitPointsToHitPcnt @0x5575A804` converts hit points to a 0..100 percentage:

    movsx eax, cl          ; hp      -- SIGNED
    imul  eax, eax, 0x64
    movsx edx, bl          ; maxhp   -- SIGNED
    idiv  ebx              ; SIGNED divide
    test  eax, eax / jne / test cl,cl / je / mov eax,1     ; "not-quite-zero" nudge
    cmp   eax, 0x64
    jle   +5
    mov   eax, 0x64        ; <-- clamps the TOP ONLY
    pop ebx ; ret

There is **no lower clamp**, so a negative hit-point byte yields a NEGATIVE percentage. Its consumer
`AoWE.ShowHitPcnt @0x5575A830` turns that straight into a clip rectangle:

    iVar2 = pcnt + 3 ;  if (iVar2 < 0) iVar2 = pcnt + 6
    local_30 = x + (iVar2 >> 2)          ; local_30 IS ctx[6] -- the clip rect's RIGHT edge
    if (ctx[6] < local_30) local_30 = ctx[6]

A negative percentage puts the right edge LEFT of the left edge. An inverted rectangle is exactly
what the blitter rejects, and `aowInt.dpl` raises **"Blt Error"** -- surfaced by FastCombatWin's
handler as the `Error - FCWin` dialog.

WHY WALL CRUSHING
-----------------
`TCombatWall.Show @0x55725C7C` draws the wall's HP bar from the signed byte at `wall+0x4D`
(`mov al,[ebx+0x4d]` @0x55725CF0). Wall Crushing is the ability that overkills a wall hard enough to
drive that byte below zero; ordinary attacks rarely do. Damage still applies -- the fault is purely
in the display path -- but the dialog is intrusive and it stops the HP bar repainting, which makes it
look as though the wall took no damage.

This is NOT caused by the combat-log mod. An earlier A/B appeared to implicate it, but that was a
false negative: the control battle simply never overkilled the wall. Single-trial A/B on a game with
RNG damage is weak evidence.

THE FIX
-------
Clamp the low end too. The 12 bytes from 0x5575A824 (`cmp/jle/mov/pop/ret`) are displaced to a cave
that re-implements both clamps:

    cmp eax,0x64 / jle .hi / mov eax,0x64
  .hi: test eax,eax / jns .lo / xor eax,eax        <-- the missing clamp
  .lo: pop ebx / ret

Naturally position-independent (register-only, rel8 branches, no absolute operands), so it needs no
load-delta anchor. 0x5575A824 is a jump target from inside the function (from 0x5575A819 and
0x5575A81D) -- both land on the FIRST byte of our jmp, which is safe; nothing jumps INTO the range.
Verified reloc-free.

BLAST RADIUS: `HitPointsToHitPcnt` has exactly two callers -- `TCombatWall.Show` and
`TAbstractUnit.ShowEx` -- so this fixes wall and unit HP bars alike. Clamping a negative percentage
to 0 (empty bar) is correct for both: a thing at or below 0 HP is destroyed.

Idempotent; verify-before-write; dry-run by default, --apply to write, --revert to undo (close all
AoW binaries first). Backup AoWEPACK.dpl.pre-hpbarclamp.
"""
import os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL  = os.path.join(GAME, "AoWEPACK.dpl")
BASE = 0x55700000
ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

HOOK  = 0x5575A824                                     # tail of HitPointsToHitPcnt
ORIG  = bytes.fromhex("83f8647e05b8640000005bc3")      # cmp/jle/mov 100/pop ebx/ret  (12 B)
CAVE  = 0x558180C0                                     # re-homed 2026-08-24: the original cave
# 0x55812000 was reclaimed by another feature while this fix was not installed (found by the
# DAM/HP discovery audit). 0x558180C0 sits after the newturn-healcap (0x55818040) and medal
# cap (0x55818080) caves; zone byte-verified zero before the re-home.

SRC = """
    cmp  eax, 0x64
    jle  Lhi
    mov  eax, 0x64
Lhi:
    test eax, eax
    jns  Llo
    xor  eax, eax
Llo:
    pop  ebx
    ret
"""

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

def main():
    apply_ = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    data = bytearray(open(DLL, "rb").read())
    secs = load_sections(data)

    cave, _ = ks.asm(SRC, CAVE); cave = bytes(cave)
    hook, _ = ks.asm(f"jmp 0x{CAVE:X}", HOOK); hook = bytes(hook)
    assert len(hook) == 5, "expected a 5-byte jmp"
    hook = hook + b"\x90" * (len(ORIG) - len(hook))     # pad to the displaced length

    print(f"cave_hpclamp @ {CAVE:08X}  ({len(cave)} B)")
    for ins in cs.disasm(cave, CAVE):
        print(f"  {ins.address:08X}  {ins.bytes.hex():<14s} {ins.mnemonic} {ins.op_str}")
    print(f"\nhook @ {HOOK:08X}: {ORIG.hex(' ')}\n            -> {hook.hex(' ')}")

    targets = [(CAVE, bytes(len(cave)), cave, "cave_hpclamp"),
               (HOOK, ORIG, hook, "HitPointsToHitPcnt tail -> cave (add the missing low clamp)")]
    if revert:
        targets = [(CAVE, cave, bytes(len(cave)), "cave_hpclamp -> zeroed"),
                   (HOOK, hook, ORIG, "HitPointsToHitPcnt tail -> STOCK")]

    plan = []
    for va, orig, new, desc in targets:
        o = va2off(secs, va)
        cur = bytes(data[o:o + len(new)])
        if cur == new:
            print(f"[= ] {va:08X} {desc}")
        elif cur == orig:
            plan.append((va, o, orig, new, desc))
        else:
            sys.exit(f"ABORT: {va:08X} holds {cur.hex(' ')}\n  expected {orig.hex(' ')} or {new.hex(' ')}"
                     "\n  another patch may own this site -- investigate before proceeding.")
    if not plan:
        print("\n[= ] already in the requested state.")
        return 0
    if not apply_:
        print(f"\n[dry-run] {len(plan)} write(s). Re-run with --apply. Close all AoW binaries first.")
        return 0

    os.makedirs(BACKUP_DIR, exist_ok=True)
    bak = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-hpbarclamp")
    if not os.path.exists(bak):
        shutil.copy2(DLL, bak); print(f"[bak] {os.path.basename(bak)}")
    for va, o, orig, new, desc in plan:
        assert bytes(data[o:o + len(new)]) == orig, f"verify-before-write failed at {va:08X}"
        data[o:o + len(new)] = new
        print(f"[w ] {va:08X} {desc}")
    try:
        open(DLL, "wb").write(bytes(data))
    except PermissionError:
        sys.exit("[x] AoWEPACK.dpl is LOCKED -- close AoW.exe / AoWCompat.exe / AoWDevEd.exe.")
    chk = open(DLL, "rb").read()
    for va, o, orig, new, desc in plan:
        assert chk[o:o + len(new)] == new, f"readback mismatch at {va:08X}"
    print("\n[done] Applied and verified. Negative HP now shows an empty bar instead of an inverted"
          "\n       clip rect. Revert with --revert (this patch owns only these two sites).")
    return 0

if __name__ == "__main__":
    sys.exit(main())
