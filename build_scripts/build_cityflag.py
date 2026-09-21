#!/usr/bin/env python3
r"""
AoW1 mod -- "cityflag": refresh the city flag ID when the city's upgrade level changes, so the
golden baubles on the flagpole stop lagging the actual level.

FULL ANALYSIS: Modding Resources/Zig notes/City_Flag_Bauble_Lag.md

================================================================================
THE BUG (vanilla -- byte-identical to the pristine DLL, not a Ziggurat regression)
================================================================================
The bauble count is not computed at draw time. It is cached in one byte:

    TCity+0x54 = flag ID    bits 0-4 race (banner art) | bit 5 (0x20) independent
                            bits 6-7 = upgradeLevel - 1   <-- THE BAUBLES
                            0x3F = draw no flag
    TCity+0x4D = upgrade level 1..4 (the real value; saved, ReadWrite property id 0x10)

  producer:  City.TCity.UpdateFlagID @0x557AC8B0  (VMT slot +0x1FC, VMT base 0x557A73F0)
                 [+0x54] = [player+0xA5] + ((byte)[+0x4D] - 1) << 6
  consumer:  City.TCity.Show @0x557ACA88 -> AoWE.TFlagControl.ShowStructureFlag @0x5575A34C
                 ImageLib.Get(lib, flagID >> 6)     <- the pole-with-N-baubles sprite

`TCity.UpdateImages @0x557AC494` ends with `call [vmt+0x1FC]` (@0x557AC616), so calling it always
refreshes the flag ID. There is exactly one producer and one consumer -- no second cache.

Two paths change [+0x4D] without ever calling the producer:

  1. UPGRADE COMPLETES -- City.TCityProductionControl.NewTurn @0x557A82A8, switch case 2
     (table @0x557A8322; case 2 body starts 0x557A8346):

         557A834D  mov  eax, [edi+0x28]        ; the TCity
         557A8350  mov  dl, [eax+0x4D]
         557A8353  inc  edx
         557A8354  call 0x557AC75C             ; TCity.SetUpgradeLevel  <-- [+0x4D] changes
         ...                                   ; relation bump, ProductionDone, event log
         557A846B  call 0x5575CB70             ; EndUpdate

     SetUpgradeLevel writes [+0x4D] (@0x557AC784) and rebuilds the production list -- nothing
     else. Case 2 never calls UpdateImages or slot +0x1FC, and EndUpdate -> ProductionControl.
     Update -> TCity.Update -> UpdateIncome + TStructure.Update does not either.
     Compare case 3 (Fortify), same function: `557A854E call 0x557AC494 ; TCity.UpdateImages`.
     That is the missing call, and it is why new walls appear instantly but new baubles do not.

  2. RAZED CITY REBUILT -- City.TCity.BuildingDone @0x557A97D8 writes [+0x4D]=1 and [+0x4C]=0
     directly, then calls SetRace([player+0xA5]).  TCity.SetRace @0x557AC990 EARLY-OUTS when the
     race is unchanged, so rebuilding with a builder of the city's existing race skips
     UpdateImages entirely; the inherited TPlayerStructure.BuildingDone @0x557608F4 only reaches
     UpdatePlayer, which refreshes conditionally. A rebuilt level-1 city can keep the old HIGH
     bauble count.

WHY IT LOOKS INTERMITTENT: [+0x54] is NOT saved (TCity.ReadWrite @0x557ACBCC persists +0x44,
+0x45, +0x48, +0x4C, +0x4D, +0x50, +0x58, +0x74 -- not +0x54), so TCity.Activate @0x557AC9C0 ->
UpdateImages rebuilds it on every map load. Save/reload always corrects it; in-session it also
catches up on owner change, fortify, migration, terrain change, raze, the domain-contested bit
[+0x44]&1 toggling, or a player being eliminated. None of that correlates with upgrading.

================================================================================
THE FIX -- retarget one call per site, no instruction displacement
================================================================================
Each site is an existing 5-byte `call rel32`. Only the 4-byte rel32 changes; it is repointed at a
thunk that does the original call and then refreshes the images:

    cave1 (upgrade)        cave2 (rebuild)
      push eax               push eax
      call SetUpgradeLevel   call TPlayerStructure.BuildingDone
      pop  eax               pop  eax
      call UpdateImages      call UpdateImages
      ret                    ret

* No displaced instructions, so no hook-resume hazard and nothing to replay.
* rel32 + register ops only => position-independent, which the .dpl requires (it rebases).
* Register contract: both callees are Delphi `register` procedures taking Self in EAX with no
  stack arguments and a plain `ret` (verified: SetUpgradeLevel @0x557AC898,
  TPlayerStructure.BuildingDone tail, UpdateImages @0x557AC622), so push/pop around them is
  balanced. UpdateImages needs only EAX. At site 1 the caller reloads EAX at 0x557A8359
  (`mov eax, edi`) and EBX/ESI/EDI are callee-saved, so clobbering EAX/EDX/ECX is free; at site 2
  the caller's next instruction is `pop ebx; ret`.
* Ordering at site 2: UpdateImages runs AFTER the inherited BuildingDone, so UpdatePlayer has
  already settled [+0x44] before the flag ID is recomputed from it.
* Safety of calling UpdateImages inside BeginUpdate/EndUpdate at site 1 is demonstrated by vanilla
  itself -- Fortify does exactly that, ten instructions later in the same function.

PATCH SURFACE: all in AoWEPACK.dpl, shared by AoW.exe / AoWCompat.exe / AoWDevEd.exe -- one patch
covers all three, no per-exe work. Both sites and all three callees are byte-identical to pristine.
The other live patches in NewTurn are outside case 2's body except Ziggurat's race-relation hand
edit at 0x557A8380 (+5 -> +0xF), which this does not touch.

Backup: backups\AoWEPACK.dpl.pre-cityflag -- minted by --apply as a diagnostic artefact.
⚠ NOT a revert path: restoring it puts back the WHOLE file and silently wipes every
feature applied after it was taken. Revert with --undo.
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
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-cityflag")

VA_BASE = 0x55700C00          # CODE section: file offset = va - VA_BASE
CODE_ZERO_END = 0x558E7918

CAVE_VA = 0x55819000          # free CODE. Highest script-owned byte below is 0x5581828C
CAVE_LIMIT = 0x40             # (build_combatlog_dll.py); zeros run past 0x5581C000.
CAVE1_OFF = 0x00
CAVE2_OFF = 0x20

FN_SETUPGRADELEVEL = 0x557AC75C   # City.TCity.SetUpgradeLevel(EAX=self, DL=level)
FN_UPDATEIMAGES    = 0x557AC494   # City.TCity.UpdateImages(EAX=self)   -> ends in call [vmt+0x1FC]
FN_PS_BUILDINGDONE = 0x557608F4   # AoWE.TPlayerStructure.BuildingDone(EAX=self)

# (site VA, original 5-byte call, original target, cave offset, label)
SITES = [
    (0x557A8354, bytes.fromhex("e803440000"), FN_SETUPGRADELEVEL, CAVE1_OFF,
     "upgrade completes  (TCityProductionControl.NewTurn case 2)"),
    (0x557A980B, bytes.fromhex("e8e470fbff"), FN_PS_BUILDINGDONE, CAVE2_OFF,
     "razed city rebuilt (TCity.BuildingDone)"),
]


def off(va):
    return va - VA_BASE


def build_caves():
    """Return {cave_offset: bytes} -- one thunk per site."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    out = {}
    for _site, _orig, target, coff, _label in SITES:
        asm = (
            "push eax\n"
            "call 0x%X\n" % target +
            "pop eax\n"
            "call 0x%X\n" % FN_UPDATEIMAGES +
            "ret\n"
        )
        enc, _ = ks.asm(asm, CAVE_VA + coff)
        out[coff] = bytes(enc)
    return out


def make_call(site_va, cave_off):
    rel = (CAVE_VA + cave_off) - (site_va + 5)
    return b"\xE8" + struct.pack("<i", rel)


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
    ap = argparse.ArgumentParser(
        description="Refresh the city flag ID when the upgrade level changes (bauble lag fix)")
    ap.add_argument("--apply", action="store_true", help="write the patch (default: dry run)")
    ap.add_argument("--undo", action="store_true",
                    help="surgically remove: restore both original call targets and zero the "
                         "cave. No .pre-* backup is touched.")
    args = ap.parse_args()

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s\n(set AOW_GAME_DIR)" % DLL)
    data = bytearray(open(DLL, "rb").read())

    caves = build_caves()
    want = {}       # site_va -> our 5 bytes
    ours = {}       # site_va -> bool
    for site_va, orig, _t, coff, _label in SITES:
        want[site_va] = make_call(site_va, coff)
        cur = bytes(data[off(site_va):off(site_va) + 5])
        ours[site_va] = (cur == want[site_va])

    if args.undo:
        if not any(ours.values()):
            print("Nothing to undo: neither site carries this feature.")
            return
        for site_va, orig, _t, _c, label in SITES:
            if ours[site_va]:
                data[off(site_va):off(site_va) + 5] = orig
                print("  restored 0x%08X -> %s   (%s)" % (site_va, orig.hex(), label))
        data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = b"\x00" * CAVE_LIMIT
        try:
            open(DLL, "wb").write(data)
        except PermissionError:
            sys.exit("ERROR: %s is locked. Close the AoW binaries and retry."
                     % os.path.basename(DLL))
        print("UNDO: zeroed cave 0x%08X (%d bytes). No backup touched." % (CAVE_VA, CAVE_LIMIT))
        return

    print("build_cityflag")
    for site_va, orig, target, coff, label in SITES:
        print("  site 0x%08X  %s -> %s   call 0x%08X -> cave 0x%08X"
              % (site_va, orig.hex(), want[site_va].hex(), target, CAVE_VA + coff))
        print("       %s" % label)
    total = max(c + len(b) for c, b in caves.items())
    print("  cave 0x%08X  %d bytes used (limit %d)" % (CAVE_VA, total, CAVE_LIMIT))
    for coff, blob in sorted(caves.items()):
        disasm(blob, CAVE_VA + coff, "cave +0x%02X" % coff)
    print()

    if total > CAVE_LIMIT:
        sys.exit("ERROR: caves need %d bytes, limit %d" % (total, CAVE_LIMIT))
    if CAVE_VA + CAVE_LIMIT > CODE_ZERO_END:
        sys.exit("ERROR: cave runs past the end of CODE")
    for coff, blob in sorted(caves.items()):
        nxt = coff + len(blob)
        end = min(CAVE_LIMIT, coff + CAVE2_OFF) if coff == CAVE1_OFF else CAVE_LIMIT
        if nxt > end:
            sys.exit("ERROR: cave +0x%02X overruns its slot" % coff)

    # verify-before-write: every site must be either vanilla or already ours
    for site_va, orig, _t, _c, _label in SITES:
        cur = bytes(data[off(site_va):off(site_va) + 5])
        if cur != orig and not ours[site_va]:
            sys.exit("ABORT: unexpected bytes at 0x%08X: %s (want %s or our call)"
                     % (site_va, cur.hex(), orig.hex()))

    payload = bytearray(CAVE_LIMIT)
    for coff, blob in caves.items():
        payload[coff:coff + len(blob)] = blob
    zone = bytes(data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT])

    if all(ours.values()) and zone == bytes(payload):
        print("Already applied and up to date -- nothing to do.")
        return
    if not all(ours.values()) and zone != b"\x00" * CAVE_LIMIT:
        sys.exit("ABORT: cave zone 0x%08X is not zero -- someone else owns it" % CAVE_VA)

    if not args.apply:
        print("DRY RUN -- re-run with --apply to commit.")
        print("(Close AoW.exe / AoWCompat.exe / AoWDevEd.exe first -- they lock the DLL.)")
        return

    if not os.path.exists(BAK):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BAK)
        print("backup -> %s" % os.path.basename(BAK))

    for site_va, _o, _t, _c, _label in SITES:
        data[off(site_va):off(site_va) + 5] = want[site_va]
    data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = payload
    try:
        open(DLL, "wb").write(data)
    except PermissionError:
        sys.exit("ERROR: %s is locked. Close the AoW binaries and retry." % os.path.basename(DLL))

    print("APPLIED. Revert with --undo -- surgical. (A .pre-* snapshot is NOT a revert path:")
    print("  it restores the whole file and wipes every feature applied after it.)")
    print("TEST 1: upgrade a 2+-hex city. The moment the upgrade completes, the baubles on its")
    print("        flagpole should step up -- WITHOUT saving and reloading.")
    print("TEST 2: raze a high-level city, rebuild it. It should drop back to one bauble.")


if __name__ == "__main__":
    main()
