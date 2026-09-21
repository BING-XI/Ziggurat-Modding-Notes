#!/usr/bin/env python3
r"""
AoW1 mod -- "sitedefender_vary": make exploration-site defender rosters (and dungeon prisoner
rosters) roll a DIFFERENT unit set per site, instead of every site of the same structure type and
strength getting a byte-identical garrison.

FULL ANALYSIS: Modding Resources/Investigation_Site_Defender_Rosters.md
Related: build_razeroster_vary.py (same family of bug, different function).

================================================================================
THE BUG (vanilla)
================================================================================
The map object carries a PERSISTENT RNG state field at map[+0x230]. The correct accessor is

    AoWE.TAoWHSMap.Random @0x5577827C     (EAX = map, EDX = range -> EAX = value)

which installs map[+0x230] as System.RandSeed, draws, and CRUCIALLY writes the advanced seed
back to map[+0x230] -- so the next caller gets a different number.

There are exactly FOUR unit-roster generators in AoWEPACK (all callers of
TUnitIndexListCollection.GetRndCollection @0x557835B4):

  AoWE.TStructure.GenerateRazeDefenders      @0x5575FD1C  seed = X + map[0x22C] + Y   (own bug;
                                                          fixed separately by razeroster_vary)
  PrdPlace.TProductionPlace.GenerateDefenders@0x557BF1A8  seed = TAoWHSMap.Random(...)  CORRECT
  ExploreS.TExplorationSite.GenerateDefenders@0x557C1FC0  seed = map[0x230]   *** BROKEN ***
  Dungeon.TDungeon.GeneratePrisoners         @0x557C5C2C  seed = map[0x230]   *** BROKEN ***

The two broken ones inline a RAW READ of map[+0x230] into System.RandSeed and never write the
advanced value back:

    557C1FCB  A1 94 94 8E 55        mov eax,[0x558E9494]      ; -> ptr to map control
    557C1FD0  8B 00                 mov eax,[eax]             ; -> the map object
    557C1FD2  8B 80 30 02 00 00     mov eax,[eax+0x230]       ; read persistent RNG state
    557C1FD8  8B 15 20 B7 8F 55     mov edx,[0x558FB720]      ; &System.RandSeed
    557C1FDE  89 02                 mov [edx],eax             ; install it -- never advanced

Because the state is never advanced, EVERY site installs the IDENTICAL seed and replays the
IDENTICAL draw sequence:

    tier roll (only if strength == 4 "Random")  ->  same tier
    GetRndCollection(site[8]->[0x64])           ->  same roster template
    FillWithRandomUnits(..., tier * 0x32)       ->  same units      (strength = tier * 50)

=> same structure type + same strength == byte-identical garrison, everywhere on the map.
It differs between matches only because map[+0x230] starts from a per-game value.

Caller: ExploreS.TExplorationSite.NewDay @0x557C20A4 --
    TStructure.NewDay(self);
    if (map[0x174] == 1 && site[0x30] != 0) GenerateDefenders(self);
i.e. rosters are rolled ONCE, on game day 1 (map[+0x174] is the day counter), for every site in
turn. Strength byte 0 = no defenders; 4 = the editor's "Random" strength -> RandInt(3)+1.

================================================================================
THE FIX
================================================================================
Do what the correct sibling (TProductionPlace.GenerateDefenders) already does: obtain the seed
from TAoWHSMap.Random, which advances the shared state so each site draws a fresh one.

MODE "vary" (default) -- 6-byte hook, no PIC needed
    Hook the `mov eax,[eax+0x230]` at 0x557C1FD2 / 0x557C5C3A. At that point EAX ALREADY holds
    the map object (loaded by the two preceding instructions, which are LEFT IN PLACE -- they
    carry the .reloc entries, see below). The cave just does:

        mov edx, SEED_RANGE
        call TAoWHSMap.Random          ; EAX = fresh value, map[0x230] advanced
        jmp  back                      ; to the existing `mov edx,[&RandSeed]; mov [edx],eax`

    The original seed-install instructions are reused verbatim. Everything is rel32.

    ** SIDE EFFECT, READ THIS: ** the tier roll happens AFTER the seed install, so with a varying
    seed a site whose strength is set to "Random" now also rolls a VARYING strength. That is what
    the editor's Random dropdown implies and is currently broken in the same way -- but it does
    change the strength distribution of existing maps. If you want today's strength behaviour
    preserved exactly, use --mode keep.

MODE "keep" -- preserves the current strength outcome, varies only the unit set
    Leaves the constant seed in place for the tier roll, then re-seeds AFTER it, hooking the
    6 bytes at 0x557C1FF4 / 0x557C5C5C (`mov eax,[esi+8]; mov eax,[eax+0x64|0x68]`) just before
    GetRndCollection. The map pointer is not in a register there, so this cave DOES need the
    PIC delta trick to reach the two globals.

================================================================================
SAFETY NOTES
================================================================================
* .reloc: VERIFIED (2026-07-29) that the displaced ranges carry NO base-relocation entries.
  The nearest relocs are at 0x557C1FDA / 0x557C5C42 -- the disp32 of the FOLLOWING instruction
  (`mov edx,[0x558FB720]`), which is deliberately left in place. Never displace bytes carrying a
  reloc; that is the classic "works one launch, crashes the next" trap.
* PIC: mode "vary" introduces NO absolute data references at all (rel32 call + rel32 jmp only),
  so it is rebase-safe with no delta anchor. Mode "keep" uses the standard
  `call $+5; pop; sub` delta trick for the two globals.
* Registers: TAoWHSMap.Random pushes/pops EBX and ESI, returns in EAX, clobbers EAX/EDX/ECX
  (Delphi scratch). At both hook sites ESI = Self (the site) and must survive -- it does.
* TAoWHSMap.Random has two non-default paths: if byte[[0x558FA040]+0x3C] & 8 it skips the
  saved-seed machinery and just returns RandInt(range); if its internal check
  (call 0x55775608) returns false it returns 0. Both are pre-existing behaviour shared with the
  item generator and TProductionPlace, so this patch takes on no new risk there.
* MP: NewDay is a synchronised turn event and every peer makes the same calls in the same order,
  exactly as the existing correct callers do. No new desync surface.
* DOWNSTREAM RNG DRIFT: advancing map[+0x230] once more per site shifts every later consumer of
  the map RNG. Harmless for a new game (and it is what the correct sibling already does), but a
  game started under this patch will not reproduce a vanilla draw sequence.

Cave base 0x55812400 -- inside the large verified-zero CODE run 0x55812219..0x558E7918
(874,239 bytes free as of 2026-07-29; measured on the live DLL, not just pristine).

Revert: --undo. Surgical -- restores the vanilla bytes at whichever hook sites we own and
zeroes our own caves, touching nothing else. It is also how you switch --mode.
⚠ NEVER revert by copying `backups\AoWEPACK.dpl.pre-sitedefvary` over the DLL. A .pre-*
snapshot restores the WHOLE file, so it is only ever safe for the newest layer and
silently wipes every feature applied after it was taken. It is a diagnostic artefact, not
a revert path. (`--apply` still mints one; that is all it is for.)

Dry-run by default; pass --apply (close ALL AoW binaries first -- they lock the DLL).
Idempotent: re-running with no args verifies the currently-installed state.
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
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-sitedefvary")

VA_BASE = 0x55700C00                      # VA = file_offset + this   (CODE section)
CAVE_VA = 0x55812400                      # verified-zero CODE region
CAVE_STRIDE = 0x40                        # one cave per patch site (keep-mode cave is 51 B)

FN_MAP_RANDOM = 0x5577827C                # AoWE.TAoWHSMap.Random(EAX=map, EDX=range) -> EAX
PTR_MAPCTRL   = 0x558E9494                # -> ptr -> the map object
PTR_RANDSEED  = 0x558FB720                # &System.RandSeed

SEED_RANGE = 0xFFFFFF                     # matches TExplorationSite.Generate (the item roller)
                                          # in the same class; TProductionPlace uses 0xFFFFF.

CODE_ZERO_END = 0x558E7918                # end of the CODE section (vsize)


def off(va):
    return va - VA_BASE


# ---------------------------------------------------------------- site table
# Each entry: (label, mode -> (hook_va, orig_bytes, resume_va, tail_asm))
SITES = {
    "vary": [
        dict(key="defenders",
             label="TExplorationSite.GenerateDefenders",
             hook=0x557C1FD2,
             orig=bytes.fromhex("8b8030020000"),      # mov eax,[eax+0x230]
             resume=0x557C1FD8,
             tail=[]),
        dict(key="prisoners",
             label="TDungeon.GeneratePrisoners",
             hook=0x557C5C3A,
             orig=bytes.fromhex("8b8030020000"),      # mov eax,[eax+0x230]
             resume=0x557C5C40,
             tail=[]),
    ],
    "keep": [
        dict(key="defenders",
             label="TExplorationSite.GenerateDefenders (post-tier)",
             hook=0x557C1FF4,
             orig=bytes.fromhex("8b46088b4064"),      # mov eax,[esi+8]; mov eax,[eax+0x64]
             resume=0x557C1FFA,
             tail=["mov eax, [esi+8]", "mov eax, [eax+0x64]"]),
        dict(key="prisoners",
             label="TDungeon.GeneratePrisoners (post-tier)",
             hook=0x557C5C5C,
             orig=bytes.fromhex("8b46088b4068"),      # mov eax,[esi+8]; mov eax,[eax+0x68]
             resume=0x557C5C62,
             tail=["mov eax, [esi+8]", "mov eax, [eax+0x68]"]),
    ],
}


def build_cave(mode, site, cave_va):
    """Return the assembled cave bytes for one patch site."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    if mode == "vary":
        # EAX already holds the map object on entry. No absolutes -> no PIC anchor needed.
        asm = [
            "mov edx, 0x%X" % SEED_RANGE,
            "call 0x%X" % FN_MAP_RANDOM,
            "jmp 0x%X" % site["resume"],
        ]
    else:
        # Map pointer is not live here; reach both globals through the load delta.
        pop_va = cave_va + 5          # VA of the `pop ecx` (the call pushes the next address)
        asm = [
            "call 0x%X" % pop_va,
            "pop ecx",
            "sub ecx, 0x%X" % pop_va,          # ecx = runtime - preferred delta
            "push ecx",                        # Random() clobbers ecx
            "mov eax, [ecx + 0x%X]" % PTR_MAPCTRL,
            "mov eax, [eax]",
            "mov edx, 0x%X" % SEED_RANGE,
            "call 0x%X" % FN_MAP_RANDOM,
            "pop ecx",
            "mov edx, [ecx + 0x%X]" % PTR_RANDSEED,
            "mov [edx], eax",                  # install the fresh seed
        ] + site["tail"] + [
            "jmp 0x%X" % site["resume"],
        ]

    encoding, _ = ks.asm("\n".join(asm), cave_va)
    return bytes(encoding), asm


def make_hook(hook_va, cave_va, orig_len):
    """5-byte jmp to the cave, NOP-padded out to orig_len."""
    rel = cave_va - (hook_va + 5)
    return b"\xE9" + struct.pack("<i", rel) + b"\x90" * (orig_len - 5)


def disasm(data, va, title):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    print("      --- %s ---" % title)
    for i in md.disasm(data, va):
        print("      %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))


def owned_hook(data, site, cave_va):
    """True if this hook site currently holds OUR jmp to OUR cave."""
    cur = bytes(data[off(site["hook"]):off(site["hook"]) + len(site["orig"])])
    if cur[0] != 0xE9:
        return False
    rel = struct.unpack_from("<i", cur, 1)[0]
    return (site["hook"] + 5 + rel) == cave_va and all(b == 0x90 for b in cur[5:])


def undo(data):
    """Surgical removal: restore vanilla bytes + zero our caves. No backup is touched."""
    writes = []
    for mode in ("vary", "keep"):
        for idx, site in enumerate(SITES[mode]):
            cave_va = CAVE_VA + idx * CAVE_STRIDE
            if not owned_hook(data, site, cave_va):
                continue
            writes.append((off(site["hook"]), site["orig"],
                           "restore %s hook @0x%08X" % (site["key"], site["hook"])))
            writes.append((off(cave_va), b"\x00" * CAVE_STRIDE,
                           "zero cave @0x%08X" % cave_va))

    if not writes:
        print("Nothing to undo: no hook site carries this feature.")
        return

    print("UNDO -- %d region(s):" % len(writes))
    for _, _, desc in writes:
        print("   %s" % desc)

    for o, b, _ in writes:
        data[o:o + len(b)] = b
    try:
        with open(DLL, "wb") as f:
            f.write(data)
    except PermissionError:
        sys.exit("ERROR: %s is locked. Close AoW.exe / AoWCompat.exe / AoWDevEd.exe and retry."
                 % os.path.basename(DLL))
    print("Removed. No .pre-* backup was touched, so later features are intact.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="write the patch (default is a dry run)")
    ap.add_argument("--mode", choices=("vary", "keep"), default="vary",
                    help="vary = seed before the tier roll, so Random-strength sites also vary "
                         "their strength (default). keep = preserve today's strength outcome, "
                         "vary only the unit set.")
    ap.add_argument("--no-prisoners", action="store_true",
                    help="patch only TExplorationSite.GenerateDefenders, leave "
                         "TDungeon.GeneratePrisoners alone")
    ap.add_argument("--undo", action="store_true",
                    help="surgically remove this feature: restore the vanilla bytes at whichever "
                         "hook sites we own and zero our caves. Does NOT touch any .pre-* backup, "
                         "so features applied later survive. Use this to switch --mode.")
    args = ap.parse_args()

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s\n(set AOW_GAME_DIR to the game directory)" % DLL)

    data = bytearray(open(DLL, "rb").read())

    if args.undo:
        return undo(data)

    # ---- refuse to stack one mode on top of the other
    other = "keep" if args.mode == "vary" else "vary"
    for s in SITES[other]:
        cur = bytes(data[off(s["hook"]):off(s["hook"]) + len(s["orig"])])
        if cur != s["orig"]:
            sys.exit("ABORT: this feature is already applied in --mode %s "
                     "(hook 0x%08X is not vanilla).\n"
                     "       Run with --undo --mode %s first, then re-apply in --mode %s."
                     % (other, s["hook"], other, args.mode))

    sites = [s for s in SITES[args.mode]
             if not (args.no_prisoners and s["key"] == "prisoners")]

    print("build_sitedefender_vary  --  mode=%s  sites=%s" % (
        args.mode, ", ".join(s["key"] for s in sites)))
    print("  DLL   : %s" % DLL)
    print("  cave  : 0x%08X (stride 0x%X)" % (CAVE_VA, CAVE_STRIDE))
    print()

    planned = []          # (file_off, new_bytes, description)
    n_applied = 0

    for idx, site in enumerate(sites):
        cave_va = CAVE_VA + idx * CAVE_STRIDE
        cave, asm = build_cave(args.mode, site, cave_va)
        hook = make_hook(site["hook"], cave_va, len(site["orig"]))

        if len(cave) > CAVE_STRIDE:
            sys.exit("ERROR: cave for %s is %d bytes, exceeds stride 0x%X"
                     % (site["key"], len(cave), CAVE_STRIDE))

        cur_hook = bytes(data[off(site["hook"]):off(site["hook"]) + len(site["orig"])])
        cur_cave = bytes(data[off(cave_va):off(cave_va) + len(cave)])

        print("[%s] %s" % (site["key"], site["label"]))
        print("   hook @ 0x%08X  (%d bytes)" % (site["hook"], len(site["orig"])))

        # ---- verify-before-write: accept the vanilla bytes OR a cave we already own
        if cave_va + CAVE_STRIDE > CODE_ZERO_END:
            sys.exit("   ABORT: cave 0x%08X runs past the end of CODE" % cave_va)

        if owned_hook(data, site, cave_va):
            if cur_cave == cave:
                print("   STATE: already applied (hook + cave match) -- nothing to do")
                n_applied += 1
                print()
                continue
            # Same feature, changed cave contents (e.g. retuned SEED_RANGE): rewrite in place
            # rather than reverting. Zero the remainder of the stride so nothing stale survives.
            print("   STATE: ours, cave contents differ -- rewriting cave in place")
            print("   cave  : 0x%08X, %d bytes (zone zero-filled to 0x%X)"
                  % (cave_va, len(cave), CAVE_STRIDE))
            disasm(cave, cave_va, "cave %s" % site["key"])
            print()
            planned.append((off(cave_va), cave + b"\x00" * (CAVE_STRIDE - len(cave)),
                            "cave %s (rewrite)" % site["key"]))
            continue

        if cur_hook != site["orig"]:
            sys.exit("   ABORT: unexpected bytes at 0x%08X\n"
                     "          found %s\n          want  %s (vanilla) or our own jmp"
                     % (site["hook"], cur_hook.hex(), site["orig"].hex()))

        # fresh application: the cave zone must still be untouched zeros
        zone = bytes(data[off(cave_va):off(cave_va) + CAVE_STRIDE])
        if zone != b"\x00" * CAVE_STRIDE:
            sys.exit("   ABORT: cave zone 0x%08X..0x%08X is not zero -- someone else owns it\n"
                     "          %s" % (cave_va, cave_va + CAVE_STRIDE - 1, zone.hex()))

        print("   STATE: vanilla -- will patch")
        print("   orig  : %s" % cur_hook.hex())
        print("   new   : %s   (jmp 0x%08X)" % (hook.hex(), cave_va))
        print("   cave  : 0x%08X, %d bytes" % (cave_va, len(cave)))
        disasm(cave, cave_va, "cave %s" % site["key"])
        print()

        planned.append((off(site["hook"]), hook, "hook %s" % site["key"]))
        planned.append((off(cave_va), cave, "cave %s" % site["key"]))

    if not planned:
        if n_applied == len(sites):
            print("Nothing to do: all %d site(s) already patched." % len(sites))
        return

    if not args.apply:
        print("DRY RUN -- %d region(s) would be written. Re-run with --apply to commit."
              % len(planned))
        print("(Close AoW.exe / AoWCompat.exe / AoWDevEd.exe first -- they lock the DLL.)")
        return

    # ---- commit
    if not os.path.exists(BAK):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BAK)
        print("backup -> %s" % os.path.basename(BAK))
    else:
        print("backup already exists, left as-is: %s" % os.path.basename(BAK))

    for o, b, desc in planned:
        data[o:o + len(b)] = b

    try:
        with open(DLL, "wb") as f:
            f.write(data)
    except PermissionError:
        sys.exit("ERROR: %s is locked. Close AoW.exe / AoWCompat.exe / AoWDevEd.exe and retry."
                 % os.path.basename(DLL))

    print("APPLIED: %d region(s) written." % len(planned))
    print("Revert: --undo (surgical -- restores the hook bytes, zeroes our caves only).")
    print()
    print("TEST: start a NEW game (rosters are rolled on day 1 only -- an existing save keeps")
    print("      whatever it already generated). Compare two crypts of the same strength.")


if __name__ == "__main__":
    main()
