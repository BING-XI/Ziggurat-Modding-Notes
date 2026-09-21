# -*- coding: utf-8 -*-
"""
build_medal_hpmv.py — medals grant HP and Movement, slow MV-from-XP curve, and (v2+) the unit
computed-HP total cap (v4: 100).

    python build_scripts/build_medal_hpmv.py            dry run + verify (default)
    python build_scripts/build_medal_hpmv.py --apply     write the newest version (v3)
    python build_scripts/build_medal_hpmv.py --undo      restore the ORIGINAL (v0) bytes
    python build_scripts/build_medal_hpmv.py --dis       disassemble the patched region

The edits live inside a PRE-EXISTING cave pair at 0x5580BE00-0x5580BE73, which hooks
`TUnit.GetHits` (vmt+0xD0) and the vmt+0xD4 movement getter. Shape:

    stat = base + rank*K + XP/divisor          rank = 1 copper / 2 silver / 3 gold

  HP  : K at 0x5580BE27, divisor = level+1
  MV  : K at 0x5580BE12, divisor = level*2 (v1 changed the curve, see below)

VERSIONS (each site records its bytes per version; any consistent version verifies)
  v0  the cave as found: K_HP=0, K_MV=0, MV divisor level*2, plain tail, no cap
  v1  2026-07-30: K_HP=1, K_MV=1, MV divisor level*2+2 (lea rewrite)
  v2  2026-08-24 (DAM/HP doubling, decisions H5/H8 in Zig notes/DamHP_Double_Decisions.md):
      * K_HP 1 -> 2   (medal HP +2/+4/+6, keeping its worth against doubled pools)
      * TOTAL CAP 120: the HP cave's tail (mov ebx,eax; pop eax; add eax,ebx; pop ebx; ret)
        becomes `jmp cap_cave`; the cave finishes the sum and clamps to 120.
        ⚠ MANDATORY BEFORE Unitres HITS doubling: the computed total (2*base + medals +
        XP/(lvl+1)) exceeds 127 for two units otherwise — signed-byte wrap.
      * stamps the gate marker "HPC2" at file 0x117410 (VA 0x55818010) which
        build_damhpdouble.py checks before it will write the Unitres HITS stage.
      * K_MV stays 1 and the MV cave is untouched — movement never scales.
  v3  2026-08-26: THE v2 CAP CAVE WAS BROKEN — units showed HP 120 once they had experience.
      `div cl` at 0x5580BE43 is an 8-BIT divide: it divides AX by CL and writes ONLY AL (quotient)
      and AH (remainder). v2's cave read all of EAX (`mov ebx,eax`) and compared at 32-bit width,
      so AH rode into the sum worth 256 each; any non-zero remainder put it past the cap and the
      clamp returned 120. v3 uses `movzx ebx,al`, so only the quotient byte enters the sum.
      Body 17->18 B. Emulated over all (level 1-4) x (XP 0-200) pairs: 0 mismatches vs
      min(rank*K + base + XP//(level+1), 120).
      TRIGGER, precisely: `XP mod (level+1) != 0` — NOT "any XP". XP that divided exactly still
      computed correctly (level 1 broke on odd XP only; level 4 on 80% of values). XP=1 fires at
      every level, which is why it presented as "any XP". Use a non-dividing XP to retest; an
      evenly-dividing one proves nothing because it was never broken.
      ⚠ NOT a vanilla defect — do not record it as one. 0x5580BE00..0x5580BE73 is ALL ZERO in
      AoWEPACK_original_backup.dpl: the whole cave pair is mod-authored. Vanilla
      TUnit.GetHits @0x55782B68 was a medal-table lookup at 0x558E83D4 plus base HP, with NO XP
      term at all. What IS vanilla is the byte-return CONVENTION that hid the defect: vanilla
      TUnit.GetMovementPoints @0x55782B84 and TUnit.GetUnitLevel @0x55782B8C both return EAX with
      a resource pointer in bits 8-31 and only AL meaningful.
      ⭐ THE GENERAL LESSON: widening an 8-bit computation to a 32-bit compare does not merely
      add a clamp — it PROMOTES EVERY PREVIOUSLY-TRUNCATED DIRTY BIT INTO THE COMPARISON. The
      clamp is a new and stricter consumer than the byte store it sits in front of. Prove all 32
      bits are defined, or narrow explicitly (movzx/movsx) first.
      ⚠ Do NOT "tidy" `div cl` into `div ecx` (F7 F1, same length): TUnit.GetUnitLevel returns a
      pointer-dirty EAX and only CL is clean — it would divide by a pointer. `mov edx,0` at
      0x5580BE3E is dead (DIV r/m8 never touches EDX) but harmless; leave it.
      ⚠ LANDMINE — the MV twin at 0x5580BE6D is STILL `mov ebx,eax` and still returns
      (remainder<<8)|value from its own `div cl` at 0x5580BE6A. It is harmless ONLY because every
      consumer of vmt+0xD4 truncates to AL. Anyone adding an MV cap MUST use `movzx ebx,al` from
      the outset or this bug reappears verbatim.

  v4  2026-08-31: TOTAL CAP 120 -> 100 (user ruling -- reclaim margin under the 127 signed-byte
      wall that every HP note keeps flagging). Body is v3 verbatim apart from the two cap
      immediates, so v3's `movzx ebx,al` quotient fix is preserved; rebuild v4 from v3, never
      from v2. The hero-side twins move in the same session and are owned by
      build_hero_clamps.py (GetHits ceiling AND the SetUnitHits purchase cap, ladder 80/120/100).
      ⚠ The MV twin at 0x5580BE6D is STILL `mov ebx,eax` -- v4 does not touch MV, and movement
      has no cap cave at all. Anyone adding one must use `movzx ebx,al` from the outset.

The cap cave (0x55818080, 18 B, zone byte-verified free) is position-independent: no memory
operands at all, entered by rel32 jmp, leaves by ret.

⚠ The XP division is `div cl` (8-bit): its quotient must fit AL or the CPU raises #DE.
Untouched here — the XP term is not doubled, so the quotient's range is unchanged.
"""
import os, sys, struct, shutil

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP_V2 = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-medalhpmv2")

CAP_V23 = 120           # the cap v2 and v3 installed -- keep, so historical states still verify
CAP = 100               # v4 target (2026-08-31 user ruling; see the v4 note above)
CAP_CAVE = 0x55818080
HP_TAIL = 0x5580BE46

# Cap cave. On entry EAX holds the result of `div cl` at 0x5580BE43 -- AL = XP quotient,
# AH = remainder, bits 16-31 = ZERO (TUnit.GetExperience @0x557828AC is `movzx eax, byte
# [eax+0x3c]`, and SetExperience clamps XP to 200, so the sole contaminant is AH).
# Stack on entry = [partial sum][saved ebx][ret]; the pushed partial sum is provably clean
# (`and eax,0x7f` -> `imul eax,eax,2` -> 8-bit `add al,[edx+0x2c]`), so it needs no laundering.
# v2 (BROKEN): mov ebx,eax   -- drags AH (the division remainder) into a 32-bit compare, worth
#              256 each, so the clamp fired whenever XP mod (level+1) != 0 and HP read 120.
# v3 (fixed) : movzx ebx,al  -- only the quotient byte reaches the sum.
# Every variant is padded to CAVE_LEN so the version comparison reads one fixed window.
CAVE_LEN = 18
CAVE_V2 = bytes([0x89, 0xC3,                       # mov   ebx, eax   <-- the defect
                 0x58,                             # pop   eax
                 0x01, 0xD8,                       # add   eax, ebx
                 0x83, 0xF8, CAP_V23,              # cmp   eax, 120
                 0x7E, 0x05,                       # jle   +5
                 0xB8, CAP_V23, 0x00, 0x00, 0x00,  # mov   eax, 120
                 0x5B, 0xC3,                       # pop   ebx / ret
                 0x00])                            # pad to CAVE_LEN -- LOAD-BEARING, keep it:
#            the version scan reads one CAVE_LEN window, so without this pad the installed 17-byte
#            v2 matches neither v0 (18 zeros) nor v3 and the script aborts, unable to apply OR undo.
#            It also makes --undo zero all 18 bytes instead of leaving a stray 0xC3.
CAVE_V3 = bytes([0x0F, 0xB6, 0xD8,                 # movzx ebx, al    <-- the fix
                 0x58,                             # pop   eax
                 0x01, 0xD8,                       # add   eax, ebx
                 0x83, 0xF8, CAP_V23,              # cmp   eax, 120
                 0x7E, 0x05,                       # jle   +5
                 0xB8, CAP_V23, 0x00, 0x00, 0x00,  # mov   eax, 120
                 0x5B, 0xC3])                      # pop   ebx / ret
# v4 = v3 with the cap lowered to 100. Body is byte-identical apart from the two immediates, so the
# div-quotient zero-extension (the v3 fix) is preserved -- do NOT rebuild this from CAVE_V2.
CAVE_V4 = bytes([0x0F, 0xB6, 0xD8,                 # movzx ebx, al
                 0x58,                             # pop   eax
                 0x01, 0xD8,                       # add   eax, ebx
                 0x83, 0xF8, CAP,                  # cmp   eax, 100
                 0x7E, 0x05,                       # jle   +5
                 0xB8, CAP, 0x00, 0x00, 0x00,      # mov   eax, 100
                 0x5B, 0xC3])                      # pop   ebx / ret
assert len(CAVE_V2) == len(CAVE_V3) == len(CAVE_V4) == CAVE_LEN
CAVE_ZONE = 0x40
_rel = CAP_CAVE - (HP_TAIL + 5)
TAIL_V2 = b"\xE9" + struct.pack("<i", _rel) + b"\x90\x90"
TAIL_V01 = bytes.fromhex("89c35801d85bc3")

_MVDIV_V0 = bytes([0x89, 0xC1, 0x6B, 0xC9, 0x02])
_MVDIV_V1 = bytes([0x8D, 0x4C, 0x00, 0x02, 0x90])

#            VA          (v0, v1, v2, v3)                                 what
SITES = [
    (0x5580BE27, (b"\x00", b"\x01", b"\x02", b"\x02", b"\x02"), "HP: rank multiplier K"),
    (0x5580BE12, (b"\x00", b"\x01", b"\x01", b"\x01", b"\x01"),
     "MV: rank multiplier K (unchanged since v1)"),
    (0x5580BE58, (_MVDIV_V0, _MVDIV_V1, _MVDIV_V1, _MVDIV_V1, _MVDIV_V1),
     "MV: XP divisor level*2 -> level*2+2"),
    (HP_TAIL, (TAIL_V01, TAIL_V01, TAIL_V2, TAIL_V2, TAIL_V2),
     "HP: tail -> jmp cap cave (total cap %d)" % CAP),
    (CAP_CAVE, (b"\x00" * CAVE_LEN, b"\x00" * CAVE_LEN, CAVE_V2, CAVE_V3, CAVE_V4),
     "cap cave (%d B, PIC; v3 zero-extends the quotient, v4 caps at %d)" % (CAVE_LEN, CAP)),
    (0x55818010, (b"\x00" * 4, b"\x00" * 4, b"HPC2", b"HPC2", b"HPC2"),
     "gate marker for build_damhpdouble.py"),
]
TARGET_V = 4


def va_to_off(data, va):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 0x34)[0]
    sh = pe + 24 + optsz
    for i in range(nsec):
        o = sh + i * 40
        vsz, vaddr, rsz, raw = struct.unpack_from("<IIII", data, o + 8)
        if base + vaddr <= va < base + vaddr + max(vsz, rsz):
            return raw + (va - base - vaddr)
    raise ValueError("VA %08X is not in any section" % va)


def site_versions(data, va, variants):
    o = va_to_off(data, va)
    cur = bytes(data[o:o + len(variants[0])])
    return {v for v, b in enumerate(variants) if cur == b}, cur


def main():
    apply_ = "--apply" in sys.argv
    undo = "--undo" in sys.argv
    if not os.path.exists(DLL):
        sys.exit("not found: %s" % DLL)
    data = bytearray(open(DLL, "rb").read())

    print("build_medal_hpmv -- medal HP/MV + unit computed-HP cap %d (target v%d)\n"
          % (CAP, TARGET_V))
    per_site, common = [], set(range(TARGET_V + 1))
    for va, variants, desc in SITES:
        vs, cur = site_versions(data, va, variants)
        per_site.append((va, vs, cur, desc))
        common &= vs
        print("  %08X  matches v%-8s %s" % (va, ",".join(map(str, sorted(vs))) or "NONE", desc))
    if not common:
        for va, vs, cur, desc in per_site:
            if not vs:
                print("      %08X holds %s" % (va, cur.hex(" ")))
        sys.exit("\nABORT: no single version matches every site -- mixed or foreign state. "
                 "Investigate before writing.")
    ver = max(common)
    print("\nstate: v%d (target v%d)" % (ver, TARGET_V))

    if not (apply_ or undo):
        print("\ndry run. --apply writes v%d, --undo restores v0." % TARGET_V)
        return
    want = 0 if undo else TARGET_V
    if ver == want:
        print("nothing to do -- already v%d." % want)
        return

    if not undo and not os.path.exists(BACKUP_V2):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP_V2)
        print("backup: %s" % os.path.basename(BACKUP_V2))
    for va, variants, _desc in SITES:
        o = va_to_off(data, va)
        assert bytes(data[o:o + len(variants[ver])]) == variants[ver], "verify failed at %08X" % va
        data[o:o + len(variants[want])] = variants[want]
    with open(DLL, "wb") as f:
        f.write(data)
    print("\n%s -- now v%d." % ("UNDONE" if undo else "APPLIED", want))
    if want == TARGET_V:
        print("The 'HPC2' gate is stamped: build_damhpdouble.py stage 4 is now unblocked.")


if __name__ == "__main__":
    main()
