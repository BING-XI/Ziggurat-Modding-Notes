#!/usr/bin/env python3
r"""
AoW1 fix -- "enchassert": stop "Assertion failure (D:\AoWDev\AoWE\inc\AoWAb.PAS, line 46181)" when
replaying a combat that enchanted an off-map defender.

ONE BYTE:  0x557658DA   7F -> EB     (jg short 0x557658F0  ->  jmp short 0x557658F0)

================================================================================
THE SYMPTOM
================================================================================
Rewinding a fast-combat record raises the assert above. Non-fatal (the exception is swallowed) but
it kills the replay transport arrows for the rest of the session. First observed 2026-07-30 on an
arena battle (build_arena.py stage 2), but the arena does NOT cause it -- see below.

================================================================================
ROOT CAUSE -- the engine violates its own invariant by design
================================================================================
The filename literal 'D:\AoWDev\AoWE\inc\AoWAb.PAS' lives at VA 0x5576596C. Exactly two asserts
reference it; line 46181 (0xB465) is the one at 0x557658DC, inside
AoWE.TUnitEnchantmentAbility.Expand @0x55765894:

    557658C6  mov edx,[esi+0xC]                 ; ability id
    557658C9  mov eax,edi                       ; edi = the unit receiving the enchantment
    557658CB  call TAbilityOwner.GetAbilityData @0x5574F1C4
    557658D2  test ebx,ebx
    557658D4  jne  .haveData                    ; already enchanted -> nothing to assert
    557658D6  cmp dword ptr [edi+0x18], 0       ; <-- the invariant: "owner has a unit id"
    557658DA  jg   0x557658F0
    557658DC  mov ecx,0xB465 ; mov edx,<file> ; mov eax,'Assertion failure'
    557658EB  call System.@Assert @0x55701138
    557658F0  ...create the TUnitEnchantmentAbilityData...

`unit[+0x18]` is the unit id. Three reads settle it:

  * TAbstractUnit.Create @0x5577EB28 initialises it: `mov dword ptr [esi+0x18], 0xFFFFFFFF` = **-1**.
  * An id is only ever assigned by TUnitControl.RegisterUnit @0x5577E988
    (`if [unit+0x18] == -1 -> GetFreeID`), and **its sole caller is
    TAbstractUnit.Activate @0x5577FBC7** -- i.e. a unit gets an id only when it is put on the map.
  * Hidden defenders are never activated. TCombat.AddArmyEx is called with (-1,-1,-1) = "join with
    NO map field", so the whole defending stack keeps id -1.

That is how EVERY hidden defender stack in the game works: TExplorationSite defenders, TDungeon
prisoners, the raze militia (build_razebattle_tower.py) and arena militia (build_arena.py) alike.
So the moment anything expands a *unit enchantment* onto one of them -- Entangled 0x5E from
EntangleStrike, Panicked 0x6C from CauseFear, a cast buff/debuff -- the assert fires.

It surfaces on REPLAY rather than during the live battle because the live fast combat carries the
enchantment on the TCombatUnit (the Expand vs ExpandAbility split -- see
Investigation_Status_Debuff_StatModifiers.md), while rewinding re-drives the strategic-side Expand.

================================================================================
WHY SKIPPING THE ASSERT UNCONDITIONALLY IS EXACTLY RIGHT (not merely "good enough")
================================================================================
The assert asks `id > 0`. A registered unit's id is ALWAYS >= 1:

    TUnitControl.Create @0x5577E850 : `mov dword ptr [esi+8], 1`      -- counter starts at 1
    TUnitControl.GetFreeID @0x5577E95C : increments, and on exceeding 0xFFFFFFF wraps to **1**,
                                          never to 0.

So `id <= 0` <=> the unit was never registered. Skipping the assert therefore loses NO debug
coverage for any reachable legitimate case -- it is precisely a scoped "don't assert on
unregistered units" fix, with no cave and no extra compare. Nothing after 0x557658F0 reads
`[edi+0x18]`; the code just builds the ability-data record.

Implementation is the 2-byte `jg` at 0x557658DA -> `jmp`, same displacement, same length:
    7F 14  jg  0x557658F0        ->    EB 14  jmp 0x557658F0
This also skips the three now-pointless `mov` register loads. The assert block itself is left in
place (unreachable), so a future disassembly still shows what was there.

================================================================================
SIBLING SWEEP (2026-07-30) -- there is exactly one such site
================================================================================
Of the **56** `call System.@Assert` sites in AoWEPACK.dpl, exactly **1** is guarded by the unit-id
invariant `cmp dword ptr [reg+0x18],0 ; jg` -- this one. (Scan: match `83 /r 18 00 7F` within 26
bytes before each assert call.) The other assert in AoWAb.PAS, line 46175 @0x557658B3, is the
`owner is TAbstractUnit` type check in the same function and is left alone -- it is a real check.

================================================================================
SAFETY
================================================================================
* .reloc: the patched byte is the opcode of a SHORT relative jump. No relocation exists or could
  exist at 0x557658DA (verified). The displacement byte is untouched.
* PROVENANCE: 0x557658D6..0x557658EF is byte-identical between the live AoWEPACK.dpl and
  Modding Resources/AoWEPACK_original_backup.dpl -- vanilla code, no other mod owns this site.
  (Do NOT skip this class of check: see Verify-against-a-pristine-DLL in the project memory.)
* No cave, no BSS, no VMT slot. Footprint is one byte.
* MP: identical on every peer; the assert is a local debug raise, not game state.
* Scope: fixes the replay of exploration-site, dungeon, raze AND arena battles at once. Kept as its
  own script (not folded into build_arena.py) so each feature's --undo stays single-purpose.

Backup: AoWEPACK.dpl.pre-enchassert
Dry-run by default; --apply to write (close ALL AoW binaries first -- they lock the DLL).
--undo restores the stock byte. Idempotent: re-running with no args verifies the current state.
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
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-enchassert")
VANILLA = os.path.join(GAME, "Modding Resources", "AoWEPACK_original_backup.dpl")

VA_BASE = 0x55700C00                 # CODE: file_offset = VA - VA_BASE

VA_JG = 0x557658DA                   # the `jg 0x557658F0` guarding the assert
STOCK = bytes.fromhex("7f14")        # jg  short +0x14
FIXED = bytes.fromhex("eb14")        # jmp short +0x14

# The whole assert block, checked for provenance (must match vanilla before we touch anything).
VA_BLOCK = 0x557658D6
BLOCK_LEN = 0x1A
BLOCK_STOCK = bytes.fromhex(
    "83 7f 18 00"                    # cmp dword ptr [edi+0x18], 0
    "7f 14"                          # jg  0x557658F0
    "b9 65 b4 00 00"                 # mov ecx, 0xB465          (line 46181)
    "ba 6c 59 76 55"                 # mov edx, 0x5576596C      ('...AoWAb.PAS')
    "b8 94 59 76 55"                 # mov eax, 0x55765994      ('Assertion failure')
    "e8 48 b8 f9 ff".replace(" ", "")  # call System.@Assert @0x55701138
)
BLOCK_FIXED = BLOCK_STOCK[:4] + FIXED + BLOCK_STOCK[6:]

JMP_TARGET = 0x557658F0              # where both the jg and the jmp land


def off(va):
    return va - VA_BASE


def check_target():
    """The displacement must still land on the instruction after the assert."""
    dest = VA_JG + 2 + STOCK[1]
    if dest != JMP_TARGET:
        raise SystemExit("displacement sanity check failed: %08X != %08X" % (dest, JMP_TARGET))


def provenance(data):
    """Confirm the assert block is untouched vanilla before patching it."""
    if not os.path.exists(VANILLA):
        return "vanilla reference missing -- SKIPPED"
    with open(VANILLA, "rb") as f:
        van = f.read()
    v = van[off(VA_BLOCK):off(VA_BLOCK) + BLOCK_LEN]
    if v != BLOCK_STOCK:
        raise SystemExit(
            "ABORT: the vanilla DLL does not contain the expected assert block at 0x%08X.\n"
            "  expected %s\n  found    %s" % (VA_BLOCK, BLOCK_STOCK.hex(" "), v.hex(" ")))
    return "matches vanilla"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the file (default: dry run)")
    ap.add_argument("--undo", action="store_true", help="restore the stock `jg`")
    args = ap.parse_args()

    check_target()

    with open(DLL, "rb") as f:
        data = bytearray(f.read())

    cur_block = bytes(data[off(VA_BLOCK):off(VA_BLOCK) + BLOCK_LEN])
    if cur_block == BLOCK_STOCK:
        state = "stock"
    elif cur_block == BLOCK_FIXED:
        state = "applied"
    else:
        raise SystemExit(
            "ABORT: the assert block at 0x%08X is neither stock nor applied -- another mod may own "
            "it.\n  stock   %s\n  applied %s\n  found   %s"
            % (VA_BLOCK, BLOCK_STOCK.hex(" "), BLOCK_FIXED.hex(" "), cur_block.hex(" ")))

    print("=" * 78)
    print("enchassert   dll=%s" % DLL)
    print("=" * 78)
    print("  site       AoWE.TUnitEnchantmentAbility.Expand +0x46   @%08X" % VA_JG)
    print("  state      [%s]" % state)
    print("  provenance %s" % provenance(data))
    print("  change     %s -> %s   (jg -> jmp, target %08X unchanged)"
          % (STOCK.hex(" "), FIXED.hex(" "), JMP_TARGET))
    print()

    if args.undo:
        if state == "stock":
            print("nothing to undo -- already stock.")
            return
        if not args.apply:
            print("DRY RUN (--undo). Add --apply to write.")
            return
        data[off(VA_JG):off(VA_JG) + 2] = STOCK
        with open(DLL, "wb") as f:
            f.write(data)
        print("UNDONE. No .pre-* backup was touched.")
        return

    if state == "applied":
        print("ALREADY APPLIED. Nothing to do.")
        return
    if not args.apply:
        print("DRY RUN. Add --apply to write (close AoW.exe / AoWCompat.exe / AoWDevEd.exe first).")
        return

    if not os.path.exists(BAK):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BAK)
        print("backup -> %s" % BAK)
    else:
        print("backup already exists (kept): %s" % BAK)

    data[off(VA_JG):off(VA_JG) + 2] = FIXED
    with open(DLL, "wb") as f:
        f.write(data)
    print("APPLIED.")


if __name__ == "__main__":
    main()
