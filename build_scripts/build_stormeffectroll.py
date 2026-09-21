#!/usr/bin/env python3
r"""
AoW1 mod -- "stormeffectroll": make strategic-map damage EFFECTS (storm + poison-plant debuffs)
roll against Resistance instead of landing automatically.

FULL ANALYSIS: Modding Resources/Investigation_Storm_Protections.md

================================================================================
THE BUG (vanilla)
================================================================================
Two sibling functions apply damage effects, and the strategic map uses the one that never rolls:

  TAbstractUnit.ExecuteDamageEffects     @0x55781E28   <- strategic (storms, poison plant)
      types &= ~GetImmunityTypes()                        ; immunity respected
      if types & 0x10: ExpandAbility(0x60)  Poisoned      ; APPLIED UNCONDITIONALLY
      if types & 0x20: ExpandAbility(0x5D)  Cursed        ; no protection check
      if types & 0x40: ExpandAbility(0x62)  Vertigo       ; no RES roll

  TAbstractUnit.ExecuteDamageEffectsRole @0x55781BA4   <- tactical combat
      types &= ~GetImmunityTypes()
      baseRes = vmt[0xCC]()  ; partial = vmt[0xF0]()
      per bit: if vmt[0x148](immAbilityId) -> skip
               res = (partial & bit) ? baseRes + 2 : baseRes
               if HitRole(strength - res): result |= bit      ; <- THE ROLL
      returns the surviving bit set; does NOT apply anything

So on the strategic map a merely *protected* or high-RES unit always takes the debuff, while the
same unit in tactical combat gets a roll. Effect chance in the rolled path is
`clamp(50 + 10*(strength - effRES), 10, 90)` via HitRole @0x55725D98.

Per-type strengths in the rolled path: fire 4, cold 2, lightning 6, poison 3, death 4, holy 3.

Callers of ExecuteDamageEffects (xref-verified, complete):
  * TAbstractUnit.ExecuteStormDamage @0x55780668  -> Pestilence 0x10, Death Storm 0x20,
                                                     Divine Storm 0x40
  * PoisonP.TPoisonPlant.TriggerArmyDamage @0x557C41D2 -> 0x10 (poison)
Holy / Unholy Ground do NOT apply effects at all -- their TriggerArmyDamage only calls
ExecuteDamageRole for typed damage (verified 2026-07-30); the 0x40 / 0x20 constants in the older
notes are DAMAGE TYPES, not effect masks. Nothing to change for them.

================================================================================
THE FIX
================================================================================
Hook the shared function's entry and pre-roll the mask through the engine's own rolled sibling,
then let the original body apply only the survivors:

    and  dx, 0x70                  ; only poison/death/holy exist here (see below)
    push eax
    call ExecuteDamageEffectsRole  ; -> AX = bits that passed the RES roll
    mov  dx, ax
    pop  eax
    <replay displaced prologue>
    jmp  ExecuteDamageEffects+8

Result bits from the Role function are the SAME bit values as its input mask (verified: fire 0x01,
cold 0x02, lightning 0x04, poison 0x10, death 0x20, holy 0x40), so the two chain directly.

WHY `and dx,0x70` -- "no frozen / burning / stunned on the strategic map":
ExecuteDamageEffects implements ONLY 0x10/0x20/0x40; it has no branch for fire (burning), cold
(frozen) or lightning (stunned), and no vanilla strategic caller passes those bits. The mask makes
that guarantee explicit and caller-independent, so a future caller cannot introduce a
combat-round-scoped status onto the strategic map.

================================================================================
CONSEQUENCES (intended, but they ARE behaviour changes)
================================================================================
* Protection now matters: a matching partial protection gives +2 RES against that effect.
* Divine Storm vertigo gains the rolled path's extra `vmt[0x114]() != 2` gate -- one unit category
  can never receive vertigo. That is the tactical-combat rule, now applied strategically too.
* Debuffs become probabilistic: RES 5 -> 50%, RES 7 -> 30%, RES >= 9 -> 10% floor, RES <= 4 -> 90% cap.
* Immunity behaviour is unchanged (it already blocked these, twice over).

CROSS-FEATURE NOTE: build_effectroll.py has repointed five of the six HitRole call sites INSIDE
ExecuteDamageEffectsRole to combat-log stubs. Storm/plant rolls will now run those stubs. The shared
emitter @0x5580F605 guards on a 'CLG1' ring-buffer magic and bails out when it is absent or full, so
it is safe off the tactical path -- strategic rolls simply do not log unless the combat log is up.

PIC: the cave contains NO absolute data references -- rel32 call + rel32 jmp and register/immediate
ops only. Rebase-safe with no load-delta anchor.
No recursion: ExecuteDamageEffectsRole never calls ExecuteDamageEffects.
Tactical combat is untouched: it reaches the Role function directly via combat vmt+0x118.

Backup: backups\AoWEPACK.dpl.pre-stormeffectroll -- minted by --apply as a diagnostic
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
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-stormeffectroll")

VA_BASE = 0x55700C00
CAVE_VA = 0x55812800          # free CODE; 0x55812400-0x5581247F sitedefender_vary,
                              #            0x55812500-0x558127FF crusade_spawns
CAVE_LIMIT = 0x40
CODE_ZERO_END = 0x558E7918

HOOK_VA = 0x55781E28          # TAbstractUnit.ExecuteDamageEffects entry
HOOK_ORIG = bytes.fromhex("535657516689142 4".replace(" ", ""))  # push ebx/esi/edi/ecx; mov [esp],dx
RESUME_VA = 0x55781E30        # first instruction after the displaced prologue

FN_ROLE = 0x55781BA4          # TAbstractUnit.ExecuteDamageEffectsRole(EAX=self, DX=mask) -> AX
KEEP_MASK = 0x0070            # poison|death|holy -- the only effects this function implements


def off(va):
    return va - VA_BASE


def build_cave(cave_va):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    asm = f"""
        and  dx, 0x{KEEP_MASK:X}
        push eax
        call 0x{FN_ROLE:X}
        mov  dx, ax
        pop  eax
        push ebx
        push esi
        push edi
        push ecx
        mov  word ptr [esp], dx
        jmp  0x{RESUME_VA:X}
    """
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
    ap = argparse.ArgumentParser(description="Roll strategic damage effects against RES")
    ap.add_argument("--apply", action="store_true", help="write the patch (default: dry run)")
    ap.add_argument("--undo", action="store_true",
                    help="surgically remove: restore the vanilla prologue + zero the cave. "
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

    print("build_stormeffectroll")
    print("  hook 0x%08X  %s -> %s  (resume 0x%08X)"
          % (HOOK_VA, HOOK_ORIG.hex(), hook.hex(), RESUME_VA))
    print("  cave 0x%08X  %d bytes (limit %d)" % (CAVE_VA, len(cave), CAVE_LIMIT))
    disasm(cave, CAVE_VA, "cave")
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
    print("TEST: cast Pestilence / Death Storm / Divine Storm on a high-RES stack -- some units")
    print("      should now shrug off the debuff while still taking damage.")


if __name__ == "__main__":
    main()
