#!/usr/bin/env python3
r"""
AoW1 mod -- "mastery_cost": rework Sphere Mastery mana economics.

    vanilla :  opposed sphere x2.00     same sphere  x1.00 (no effect)
    this    :  opposed sphere x1.50     same sphere  x0.75

Doubling the opposed sphere is a hard lockout; +50% still stings without being anti-fun, and the
same-sphere discount finally makes a Mastery feel like *your* sphere's mastery.

================================================================================
THE MECHANIC
================================================================================
`TGlobalMagicControl` lives at `[[0x558FA040] + 0x188]` and holds a per-sphere counter array at
`mc + 0x18 + sphere*4`. `GetSphereManaDoubled @0x5577E230` is just `counter != 0`.

The ONLY things that touch that array are the six Mastery enchantments' Activate methods, and each
flags **its own opposite** (verified against all six, 2026-07-30):

    Life(1)  -> flags Death(2)      Death(2) -> flags Life(1)
    Earth(3) -> flags Air(4)        Air(4)   -> flags Earth(3)
    Fire(5)  -> flags Water(6)      Water(6) -> flags Fire(5)

**That is the key to the discount: no new state is needed.** For a spell of sphere S,
"a Mastery of S is active" is exactly `doubled[opposite(S)] != 0`, where
`opposite(s) = s+1 if s odd else s-1` (and sphere 0 = Cosmos has no opposite).

Cost chokepoint -- `THero.CastingMana @0x557894EC`:

    ebx = spell[0x14]                       ; base casting cost
    eax = [0x558FA040]                      ; map            <-- carries the only .reloc here
    eax = [eax+0x188]                       ; TGlobalMagicControl
    dl  = spell[0x20]                       ; the spell's sphere
    if GetSphereManaDoubled(mc, dl): ebx *= 2
    return ebx

`CastingMana` is a single chokepoint with 20+ callers -- CanCastSpell, CanCastCombatSpell, CastSpell,
ExecuteStartCasting, CastingTurns, TSpell.CombatSpellCast, TCombatSpell.CreateCA, and
TUnitSpellCaster.GetRequiredMana (our unit-spellcasting feature). Patching it therefore covers every
cost preview, every AI affordability check and every actual charge, in one place.

================================================================================
THE PATCH
================================================================================
Hook `0x557894F8` (`mov eax,[eax+0x188]`, 6 bytes, register-only). **`eax` already holds the map
pointer there**, loaded by the preceding `mov eax,[0x558FA040]` which is LEFT IN PLACE because its
disp32 carries the function's only base-relocation (verified: the sole reloc in CastingMana is at
`0x557894F4`). So the cave needs no PIC anchor -- rel32 jumps and register ops only.

    mov   eax,[eax+0x188]              ; replay displaced -> mc
    movzx edx, byte [esi+0x20]         ; S = spell sphere
    cmp   [eax+edx*4+0x18], 0          ; opposed Mastery active?
    jne   opposed
    test  edx, edx                     ; Cosmos has no opposite
    jz    done
    ecx = opposite(S)                  ; odd -> S+1, even -> S-1
    cmp   [eax+ecx*4+0x18], 0          ; own-sphere Mastery active?
    je    done
    ebx = ebx * OWN_MUL >> OWN_SHIFT           ; x0.75
    jmp   done
  opposed:
    ebx = ebx * OPPOSED_MUL >> OPPOSED_SHIFT   ; x1.50
  done:
    jmp   0x55789510                   ; the original epilogue: mov eax,ebx; pop esi; pop ebx; ret

PRECEDENCE: if both a sphere and its opposite have Masteries up, the OPPOSED penalty wins (checked
first) -- the discount is not applied. Matches vanilla's "any count != 0" semantics; stacking two
Masteries of the same sphere does not compound, exactly as vanilla's x2 did not.

ROUNDING: integer, truncating by default, which rounds in the caster's favour in BOTH directions
(a 5-mana spell becomes 7 opposed, 3 same-sphere). Set ROUND_UP = True to bias the other way.

⚠ GLOBAL, NOT PER-CASTER: `TGlobalMagicControl` is a single global with no owner tracking -- this is
vanilla's design, where your Fire Mastery doubles water costs for *everyone*. The new discount is
global too, so casting Fire Mastery makes fire spells 25% cheaper for every wizard, not just you.
Making it caster-only would require per-player state the engine does not have.

Backup: backups\AoWEPACK.dpl.pre-masterycost -- minted by --apply as a diagnostic
artefact. ⚠ NOT a revert path: restoring it puts back the WHOLE file and silently wipes
every feature applied after it was taken. Revert with --undo.
Dry-run by default; --apply to commit; --undo to remove surgically (no backup touched).
"""

import os
import sys
import shutil
import struct
import argparse

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

DLL = os.path.join(GAME, "AoWEPACK.dpl")
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-masterycost")

VA_BASE = 0x55700C00
CAVE_VA = 0x55812880          # free CODE. Taken so far: 0x55812400-47F sitedefender_vary,
                              # 0x55812500-7FF crusade_spawns, 0x55812800-83F stormeffectroll
CAVE_LIMIT = 0x60
CODE_ZERO_END = 0x558E7918

HOOK_VA = 0x557894F8
HOOK_ORIG = bytes.fromhex("8b8088010000")     # mov eax,[eax+0x188]
EPILOGUE_VA = 0x55789510                      # mov eax,ebx; pop esi; pop ebx; ret

MC_OFF = 0x188                # map -> TGlobalMagicControl
CNT_OFF = 0x18                # mc + 0x18 + sphere*4 = per-sphere Mastery counter

# ---- TUNING -----------------------------------------------------------------
# cost = cost * MUL >> SHIFT
OPPOSED_MUL, OPPOSED_SHIFT = 3, 1     # x1.50   (vanilla was 2,0 = x2.00)
OWN_MUL, OWN_SHIFT = 3, 2             # x0.75   (vanilla had no same-sphere effect)
ROUND_UP = False                      # True -> add (1<<SHIFT)-1 before the shift
# -----------------------------------------------------------------------------


def off(va):
    return va - VA_BASE


def scale_asm(mul, shift):
    """ebx = ebx * mul >> shift, using eax as scratch."""
    out = ["imul eax, ebx, %d" % mul]
    if ROUND_UP and shift:
        out.append("add eax, %d" % ((1 << shift) - 1))
    if shift:
        out.append("shr eax, %d" % shift)
    out.append("mov ebx, eax")
    return out


def build_cave(cave_va):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    asm = "\n".join([
        "mov   eax, [eax + 0x%X]" % MC_OFF,          # replay displaced -> mc
        "movzx edx, byte ptr [esi + 0x20]",          # S = spell sphere
        "cmp   dword ptr [eax + edx*4 + 0x%X], 0" % CNT_OFF,
        "jne   opposed",
        "test  edx, edx",                            # Cosmos (0) has no opposite
        "jz    done",
        "mov   ecx, edx",
        "test  cl, 1",
        "jz    even",
        "inc   ecx",                                 # odd  -> S+1
        "jmp   chk",
        "even:",
        "dec   ecx",                                 # even -> S-1
        "chk:",
        "cmp   dword ptr [eax + ecx*4 + 0x%X], 0" % CNT_OFF,
        "je    done",
    ] + scale_asm(OWN_MUL, OWN_SHIFT) + [
        "jmp   done",
        "opposed:",
    ] + scale_asm(OPPOSED_MUL, OPPOSED_SHIFT) + [
        "done:",
        "jmp   0x%X" % EPILOGUE_VA,
    ])
    enc, _ = ks.asm(asm, cave_va)
    return bytes(enc)


def make_hook(cave_va):
    rel = cave_va - (HOOK_VA + 5)
    return b"\xE9" + struct.pack("<i", rel) + b"\x90" * (len(HOOK_ORIG) - 5)


def disasm(data, va, title):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    print("   --- %s ---" % title)
    for i in md.disasm(data, va):
        print("   %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))


def main():
    ap = argparse.ArgumentParser(description="Mastery casting-cost rework")
    ap.add_argument("--apply", action="store_true", help="write the patch (default: dry run)")
    ap.add_argument("--undo", action="store_true",
                    help="surgically remove: restore the displaced instruction + zero the cave. "
                         "No .pre-* backup is touched.")
    args = ap.parse_args()

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s\n(set AOW_GAME_DIR)" % DLL)
    data = bytearray(open(DLL, "rb").read())

    cave = build_cave(CAVE_VA)
    hook = make_hook(CAVE_VA)
    cur = bytes(data[off(HOOK_VA):off(HOOK_VA) + len(HOOK_ORIG)])
    ours = cur == hook

    if args.undo:
        if not ours:
            print("Nothing to undo: 0x%08X does not carry this feature." % HOOK_VA)
            return
        data[off(HOOK_VA):off(HOOK_VA) + len(HOOK_ORIG)] = HOOK_ORIG
        data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = b"\x00" * CAVE_LIMIT
        open(DLL, "wb").write(data)
        print("UNDO: restored 0x%08X, zeroed cave 0x%08X. No backup touched." % (HOOK_VA, CAVE_VA))
        return

    def pct(mul, shift):
        return 100.0 * mul / (1 << shift)

    print("build_mastery_cost")
    print("  opposed sphere : x%.2f  (vanilla x2.00)" % (pct(OPPOSED_MUL, OPPOSED_SHIFT) / 100))
    print("  same sphere    : x%.2f  (vanilla x1.00)" % (pct(OWN_MUL, OWN_SHIFT) / 100))
    print("  rounding       : %s" % ("round up" if ROUND_UP else "truncate (favours caster)"))
    print("  hook 0x%08X  %s -> %s" % (HOOK_VA, HOOK_ORIG.hex(), hook.hex()))
    print("  cave 0x%08X  %d bytes (limit %d)" % (CAVE_VA, len(cave), CAVE_LIMIT))
    disasm(cave, CAVE_VA, "cave")
    print()
    print("  example: a 12-mana spell -> %d opposed, %d same-sphere, 12 unaffected"
          % (12 * OPPOSED_MUL >> OPPOSED_SHIFT, 12 * OWN_MUL >> OWN_SHIFT))
    print()

    if len(cave) > CAVE_LIMIT:
        sys.exit("ERROR: cave is %d bytes, limit %d" % (len(cave), CAVE_LIMIT))
    if CAVE_VA + CAVE_LIMIT > CODE_ZERO_END:
        sys.exit("ERROR: cave runs past the end of CODE")

    if ours and bytes(data[off(CAVE_VA):off(CAVE_VA) + len(cave)]) == cave:
        print("Already applied and up to date -- nothing to do.")
        return
    if not ours and cur != HOOK_ORIG:
        sys.exit("ABORT: unexpected bytes at 0x%08X: %s (want %s or our jmp)"
                 % (HOOK_VA, cur.hex(), HOOK_ORIG.hex()))
    if not ours:
        zone = bytes(data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT])
        if zone != b"\x00" * CAVE_LIMIT:
            sys.exit("ABORT: cave zone 0x%08X is not zero -- someone else owns it" % CAVE_VA)

    if not args.apply:
        print("DRY RUN -- re-run with --apply to commit.")
        print("(Close AoW.exe / AoWCompat.exe / AoWDevEd.exe first -- they lock the DLL.)")
        return

    if not os.path.exists(BAK):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BAK)
        print("backup -> %s" % os.path.basename(BAK))

    data[off(HOOK_VA):off(HOOK_VA) + len(hook)] = hook
    payload = bytearray(CAVE_LIMIT)
    payload[0:len(cave)] = cave
    data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = payload
    try:
        open(DLL, "wb").write(data)
    except PermissionError:
        sys.exit("ERROR: %s is locked. Close the AoW binaries and retry." % os.path.basename(DLL))

    print("APPLIED. Revert with --undo -- surgical. (A .pre-* snapshot is NOT a revert path:")
    print("  it restores the whole file and wipes every feature applied after it.)")
    print("TEST: with a Mastery up, check the spellbook cost of an opposed-sphere spell (+50%)")
    print("      and a same-sphere spell (-25%). Unrelated spheres must be unchanged.")


if __name__ == "__main__":
    main()
