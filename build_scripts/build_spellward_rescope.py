#!/usr/bin/env python3
r"""Spell Ward is rescoped: it blocks Town Gate and Warp Party, nothing else.

    python build_scripts/build_spellward_rescope.py            # dry run + verify current state
    python build_scripts/build_spellward_rescope.py --apply
    python build_scripts/build_spellward_rescope.py --undo --apply
    python build_scripts/build_spellward_rescope.py --dis      # also dump the host sites

Target binary: **AoWEPACK.dpl only.** `AoW.exe` / `AoWCompat.exe` / `AoWDevEd.exe` need no patch --
`TSpell.CanActivate` is reached only through the spell VMT inside the DLL, and the exe's
`THero.CastSpell` import re-runs `CanActivate` at execution time, so both the offer gate and the
execution gate come from this one function.

================================================================================
WHAT VANILLA DOES
================================================================================
`TGlobalMagicControl` hangs off `[AoWHSMap + 0x188]`. At `+0x10` it keeps a BYTE SET of the
global-enchantment TYPE CODES currently active, rebuilt by
`TGlobalMagicControl.UpdateActiveEnchantments @0x5577E46C`. `TSpellWardEnchantment.Create
@0x557F374C` declares type 6, so an active Spell Ward sets bit `0x40` of that byte.

Exactly THREE sites read bit 0x40 (byte pattern `F6 4x 10 40` across the whole module):

  1. `0x557792F9` in `AoWE.TSpell.CanActivate @0x557792D0`   -- the master gate
  2. `0x557EF97E` in `TGlobalEnchantmentSpell.CanActivate @0x557EF938` -- a redundant re-check
  3. `0x557EBAFA` in `TDisjunctionSpellCaster.CanCast @0x557EBA94`     -- the Disjunction gate

All three windows were byte-identical to `Modding Resources/AoWEPACK_original_backup.dpl` before
this patch, i.e. nothing else in Ziggurat had touched them.

The master gate, live bytes as found:

    557792E8  80 78 22 02        cmp byte ptr [eax+0x22], 2   <-- category 2 = ANY strategic-map
    557792EC  75 3B              jne 0x55779329                   spell (24 constructors set it)
    557792EE  A1 40 A0 8F 55     mov eax, [0x558FA040]        ; AoWHSMap -- .reloc @0x557792EF
    557792F3  8B 80 88 01 00 00  mov eax, [eax+0x188]
    557792F9  F6 40 10 40        test byte ptr [eax+0x10], 0x40
    557792FD  74 26              je  0x55779325               ; ALLOW
    557792FF  8D 55 F8           lea edx, [ebp-8]
    55779302  B8 4C 7D 70 55     mov eax, 0x55707D4C          ; refusal RStr -- .reloc @0x55779303
              ... LoadResString / TranslateRStr / @LStrAsg ; xor ebx,ebx (DENY)
    55779325  B3 01              mov bl, 1                    ; ALLOW (ward inactive)
    55779329  B3 01              mov bl, 1                    ; ALLOW (not category 2)

So vanilla's rule is "while a Spell Ward is up, NO strategic-map spell may be cast at all" --
summons, storms, city spells, global enchantments, everything. That is the behaviour being
narrowed.

================================================================================
WHAT THIS PATCH DOES -- ONE HOOK, TWO IMMEDIATES
================================================================================
A + B in one edit:

  A  the master gate stops testing the CATEGORY and tests the SPELL ID instead, so only
     Warp Party (34 = 0x22) and Town Gate (38 = 0x26) fall into the ward's deny path;
  B  the two subordinate readers are neutralised by zeroing their test mask, so
     `TGlobalEnchantmentSpell.CanActivate` no longer re-blocks every global enchantment and
     `TDisjunctionSpellCaster.CanCast` no longer blocks Disjunction of other global
     enchantments while a ward is up (vanilla already allowed disjuncting the ward itself).

SITE 1  `0x557792E8`, 6 bytes, reloc-free:  `80 78 22 02 75 3B`  ->  `E9 <rel32 -> cave> 90`

  cave_spellward @ 0x55847000 (22 bytes, PIC: rel32 and register operands only)

        55847000  83 78 10 22     cmp dword ptr [eax+0x10], 0x22   ; Warp Party
        55847004  74 06           je  0x5584700c
        55847006  83 78 10 26     cmp dword ptr [eax+0x10], 0x26   ; Town Gate
        5584700A  75 05           jne 0x55847011
        5584700C  E9 dd dd dd dd  jmp 0x557792EE                   ; WARDED -> the AoWHSMap load
        55847011  E9 dd dd dd dd  jmp 0x55779329                   ; ALLOW  -> host's own mov bl,1

  EAX is the `TSpell*` self pointer (`cmp byte ptr [eax+0x22],2` proves it). The spell id lives
  at `[spell+0x10]` as a DWORD, written by each constructor as a code constant:
  `TWarpParty.Create @0x557EB0A0` -> `mov dword ptr [esi+0x10], 0x22` at `0x557EB0F3`;
  `TTownGate.Create  @0x557B0BAC` -> `mov dword ptr [esi+0x10], 0x26` at `0x557B0BFF`.
  Read live from the file, not from a decompile.

  Neither resume point needs EAX preserved -- `0x557792EE` immediately reloads it from the
  AoWHSMap global and `0x55779329` is `mov bl,1`. No push/pop, no flags dependency (the host's
  next instruction after either label re-sets what it needs).

  The category test is dropped rather than kept: the two ids are unique in the spell table, so an
  id match already implies "this is the strategic Warp Party / Town Gate", and a spell that is not
  one of the two takes the ALLOW jump exactly as `jne 0x55779329` did.

SITE 2  `0x557EF981`: `40` -> `00`, the mask immediate of
        `557EF97E  F6 40 10 40  test byte ptr [eax+0x10], 0x40`
        followed by `557EF982  75 40  jne 0x557EF9C4` (the deny arm). With a zero mask ZF is
        always set, the `jne` is never taken, and the function proceeds to its real checks.

SITE 3  `0x557EBAFD`: `40` -> `00`, the mask immediate of
        `557EBAFA  F6 40 10 40  test byte ptr [eax+0x10], 0x40`
        followed by `557EBAFE  74 11  je 0x557EBB11`. With a zero mask the `je` is ALWAYS taken,
        which skips the "is the selected enchantment the ward itself" special case and lands on
        the ordinary disjunction path -- so Disjunction works on every global enchantment, the
        Spell Ward included.

Zeroing the mask rather than NOP-ing the branch keeps the instruction lengths identical, leaves
the surrounding `.reloc` entries untouched, and makes `--undo` a one-byte write per site.

================================================================================
SCOPE -- WHAT THIS DELIBERATELY DOES NOT TOUCH
================================================================================
* Mana cost and upkeep of Spell Ward are unchanged (user ruling 2026-09-06).
* `TSpellTE.Validate` -- the mid-targeting window in which a spell is committed before the ward
  goes up -- is NOT gated (user ruling 2026-09-06: leave it open).
* AI: both spells' VMT `+0x5C` `AIPrefetchCastSpellActions` is the `TSpell` stub `0x55779824`
  (a bare `ret`), so no AI player ever queues Town Gate or Warp Party. Nothing to do.
* RNG: no path here draws from either generator, so there is no new `rng_audit.py` site.
* `Dict/ResStr.mld` row "Cannot dispel when Spell Ward is active" (ResStr.txt:2175) is left alone
  -- site 3 makes it unreachable, and a dead string costs nothing.

Companion edits, in their own scripts (all three are cosmetic; the mechanic is complete without
them):
    build_resstr_names.py   "Spell Ward locks all global enchantments"
                              -> [US] "Spell Ward blocks Town Gate and Warp Party"
    build_pfs_typos.py      Release/Spells.pfs record 75 (spell id 65 + 10), tag 0x0A description
    build_ziggurat_manual.py  NEWMECH_SPELLWARD block in r_newmech()

================================================================================
REVERT
================================================================================
`--undo --apply` is surgical and touches no backup: it writes `80 78 22 02 75 3B` back at
`0x557792E8`, `0x40` back at `0x557EF981` and `0x557EBAFD`, and zeroes `0x55847000..0x558470FF`.
A `backups/AoWEPACK.dpl.pre-spellward` snapshot is minted on the first `--apply` ONLY while all
four sites are still in their pre-feature state -- never on `--undo` (the file IS the patched
state by definition) and never on a re-run over an existing install.
"""
import os
import struct
import sys

from capstone import CS_ARCH_X86, CS_MODE_32, Cs
from keystone import KS_ARCH_X86, KS_MODE_32, Ks

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-spellward")
IMAGE_BASE = 0x55700000

# ---- addresses (preferred-base VAs, every one verified against the live file) -------------
GATE_SITE = 0x557792E8      # cmp byte [eax+0x22],2 / jne -- the 6 bytes we displace
GATE_WARD = 0x557792EE      # resume: mov eax,[0x558FA040] (AoWHSMap) -- .reloc at +1, DO NOT MOVE
GATE_ALLOW = 0x55779329     # the host's own ALLOW label (mov bl,1)
GATE_ANCHOR = 0x557792EE    # must always read A1 40 A0 8F 55, patched or not

GENCH_MASK = 0x557EF981     # mask imm of test byte [eax+0x10],0x40 @0x557EF97E
GENCH_TEST = 0x557EF97E
DISJ_MASK = 0x557EBAFD      # mask imm of test byte [eax+0x10],0x40 @0x557EBAFA
DISJ_TEST = 0x557EBAFA

SPELL_ID_OFF = 0x10         # TSpell field: spell id, dword
ID_WARP_PARTY = 0x22        # 34 -- TWarpParty.Create @0x557EB0A0 writes it at 0x557EB0F3
ID_TOWN_GATE = 0x26         # 38 -- TTownGate.Create  @0x557B0BAC writes it at 0x557B0BFF
WARP_CTOR_IMM = 0x557EB0F3  # asserted: mov dword ptr [esi+0x10], 0x22
GATE_CTOR_IMM = 0x557B0BFF  # asserted: mov dword ptr [esi+0x10], 0x26

CAVE = 0x55847000           # exclusive reservation for this feature
CAVE_SPAN = 0x100           # bytes this script owns and zeroes on --undo
ZONE_END = 0x55848000       # end of the reservation (asserted zero beyond the cave)

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)


def rel32(site, dest):
    return struct.pack("<i", dest - (site + 5))


# ---- the cave --------------------------------------------------------------------------
# NOTE: no ';' comments inside the asm string -- keystone hangs on them (project trap).
CAVE_SRC = f"""
        cmp dword ptr [eax + 0x{SPELL_ID_OFF:X}], 0x{ID_WARP_PARTY:X}
        je Lward
        cmp dword ptr [eax + 0x{SPELL_ID_OFF:X}], 0x{ID_TOWN_GATE:X}
        jne Lallow
    Lward:
        jmp 0x{GATE_WARD:X}
    Lallow:
        jmp 0x{GATE_ALLOW:X}
"""
cave = bytes(ks.asm(CAVE_SRC, CAVE)[0])
assert len(cave) <= CAVE_SPAN, f"cave {len(cave)} B exceeds owned span {CAVE_SPAN}"
cave_region = cave + b"\x00" * (CAVE_SPAN - len(cave))
zero_region = b"\x00" * CAVE_SPAN

HOOK_OLD = bytes.fromhex("80 78 22 02 75 3B")
HOOK_NEW = b"\xE9" + rel32(GATE_SITE, CAVE) + b"\x90"
assert len(HOOK_NEW) == len(HOOK_OLD) == 6


# ---- PE helpers -------------------------------------------------------------------------
def load_secs(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    sect = e + 24 + optsz
    secs = []
    for i in range(nsec):
        b = sect + i * 40
        vs, va, rs, raw = struct.unpack_from("<IIII", d, b + 8)
        secs.append((d[b:b + 8].rstrip(b"\0").decode("latin1"), va, vs, raw, rs))
    return secs


def va2off(secs, va):
    """VA -> file offset THROUGH THE SECTION TABLE. Never a flat delta: CODE and DATA in
    AoWEPACK.dpl have different ones."""
    r = va - IMAGE_BASE
    for nm, v, vs, raw, rs in secs:
        if v <= r < v + max(vs, rs):
            return raw + (r - v)
    raise ValueError(hex(va))


def reloc_hits(d, secs, lo, hi):
    """Every .reloc entry whose target VA lies in [lo, hi)."""
    e = struct.unpack_from("<I", d, 0x3C)[0]
    magic = struct.unpack_from("<H", d, e + 24)[0]
    dd = e + 24 + (96 if magic == 0x10B else 112)
    rva, size = struct.unpack_from("<II", d, dd + 5 * 8)
    off = va2off(secs, IMAGE_BASE + rva)
    end, hits = off + size, []
    while off < end:
        pg, blk = struct.unpack_from("<II", d, off)
        if blk == 0:
            break
        for i in range((blk - 8) // 2):
            w = struct.unpack_from("<H", d, off + 8 + i * 2)[0]
            if w >> 12 and lo <= IMAGE_BASE + pg + (w & 0xFFF) < hi:
                hits.append(IMAGE_BASE + pg + (w & 0xFFF))
        off += blk
    return hits


# ---- report -----------------------------------------------------------------------------
print(f"cave_spellward @ {CAVE:08X}  ({len(cave)} bytes, owns {CAVE_SPAN} to "
      f"{CAVE + CAVE_SPAN:08X}; reservation to {ZONE_END:08X})")
for ins in cs.disasm(cave, CAVE):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<18} {ins.mnemonic} {ins.op_str}")
if any(b"\x55\x70" in ins.bytes[1:] for ins in cs.disasm(cave, CAVE)):
    print("  WARNING: an in-image absolute operand may have been emitted -- read the above")
print(f"hook @ {GATE_SITE:08X}:  {HOOK_OLD.hex(' ')}  ->  {HOOK_NEW.hex(' ')}")
print(f"mask @ {GENCH_MASK:08X}:  40  ->  00   (TGlobalEnchantmentSpell.CanActivate re-check)")
print(f"mask @ {DISJ_MASK:08X}:  40  ->  00   (TDisjunctionSpellCaster.CanCast)")
print()


def main():
    undo = "--undo" in sys.argv
    dis = "--dis" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    secs = load_secs(d)

    def rd(va, n):
        o = va2off(secs, va)
        return bytes(d[o:o + n])

    # --- preconditions: state-invariant anchors, true before AND after the patch ----------
    checks = [
        (GATE_ANCHOR, bytes.fromhex("A1 40 A0 8F 55"),
         "AoWHSMap load at the WARDED resume point"),
        (GATE_ALLOW, bytes.fromhex("B3 01"), "host ALLOW label (mov bl,1)"),
        (GENCH_TEST, bytes.fromhex("F6 40 10"), "TGlobalEnchantmentSpell test opcode"),
        (GENCH_TEST + 4, bytes.fromhex("75 40"), "its jne (deny arm)"),
        (DISJ_TEST, bytes.fromhex("F6 40 10"), "TDisjunctionSpellCaster test opcode"),
        (DISJ_TEST + 4, bytes.fromhex("74 11"), "its je (skip-to-ordinary-path arm)"),
        (WARP_CTOR_IMM, bytes.fromhex("C7 46 10 22 00 00 00"),
         "TWarpParty.Create sets spell id 0x22"),
        (GATE_CTOR_IMM, bytes.fromhex("C7 46 10 26 00 00 00"),
         "TTownGate.Create sets spell id 0x26"),
    ]
    for va, want, what in checks:
        got = rd(va, len(want))
        if got != want:
            print(f"ABORT: {what} @ {va:08X} reads {got.hex(' ')}, expected {want.hex(' ')}")
            return 1
    print(f"anchors: {len(checks)}/{len(checks)} ok "
          f"(spell ids read live from both constructors)")

    hits = (reloc_hits(d, secs, GATE_SITE, GATE_SITE + len(HOOK_NEW))
            + reloc_hits(d, secs, GENCH_MASK, GENCH_MASK + 1)
            + reloc_hits(d, secs, DISJ_MASK, DISJ_MASK + 1)
            + reloc_hits(d, secs, CAVE, CAVE + CAVE_SPAN))
    if hits:
        print(f"ABORT: .reloc entries inside a write window: {[f'{h:08X}' for h in hits]}")
        return 1
    print("reloc: no entry inside any write window "
          f"(the two in TSpell.CanActivate stay at 557792EF / 55779303)")

    tail = rd(CAVE + CAVE_SPAN, ZONE_END - CAVE - CAVE_SPAN)
    if set(tail) != {0}:
        print(f"ABORT: reservation {CAVE + CAVE_SPAN:08X}..{ZONE_END:08X} is not zero.")
        return 1
    print(f"reservation {CAVE + CAVE_SPAN:08X}..{ZONE_END:08X}: "
          f"{len(tail)} bytes, all zero")

    # --- patch table ---------------------------------------------------------------------
    patches = [
        (GATE_SITE, HOOK_OLD, HOOK_NEW, "TSpell.CanActivate: category gate -> cave_spellward"),
        (GENCH_MASK, b"\x40", b"\x00", "TGlobalEnchantmentSpell.CanActivate ward mask"),
        (DISJ_MASK, b"\x40", b"\x00", "TDisjunctionSpellCaster.CanCast ward mask"),
        (CAVE, zero_region, cave_region, f"cave_spellward @ {CAVE:08X}"),
    ]

    if dis:
        print()
        for va, old, new, desc in patches[:3]:
            print(f"  {va:08X}  now {rd(va, len(new)).hex(' '):<18} "
                  f"pre-feature {old.hex(' '):<18} patched {new.hex(' ')}   {desc}")

    ok = True
    already = todo = pristine = 0
    for va, old, new, desc in patches:
        target, other = (old, new) if undo else (new, old)
        cur = rd(va, len(new))
        if cur == target:
            already += 1
            if undo:
                pristine += 1
        elif cur == other:
            todo += 1
            if not undo:
                pristine += 1
        else:
            print(f"MISMATCH {desc} @ {va:08X}:\n  pre-feature {old[:24].hex(' ')}"
                  f"\n  patched     {new[:24].hex(' ')}\n  found       {cur[:24].hex(' ')}")
            ok = False
    verb = "undone" if undo else "applied"
    print(f"\n{already} already {verb}, {todo} to change, {len(patches)} total")
    if not ok:
        print("ABORT: byte mismatch (different/partial patch state).")
        return 1
    if "--apply" not in sys.argv:
        print("\nDry run OK. Re-run with --apply to write, --undo --apply to remove.")
        return 0
    if todo == 0:
        print("Nothing to do.")
        return 0

    # Snapshot ONLY from a file proved to be in the pre-feature state -- never on --undo (the
    # current file IS the patched state by definition), never over an existing install.
    if not undo and pristine == len(patches) and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        with open(DLL, "rb") as f:
            blob = f.read()
        with open(BACKUP, "wb") as f:
            f.write(blob)
        print(f"backup -> {BACKUP}")
    elif not undo and not os.path.exists(BACKUP):
        print("(no backup: file is not in the pre-feature state; --undo is the revert path)")

    for va, old, new, desc in patches:
        o = va2off(secs, va)
        blob = old if undo else new
        d[o:o + len(blob)] = blob
        print(f"  wrote {va:08X}  {desc}")
    open(DLL, "wb").write(bytes(d))
    print("undone." if undo else "applied.")
    return 0


sys.exit(main())
