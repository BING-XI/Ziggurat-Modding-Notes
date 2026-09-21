#!/usr/bin/env python
r"""
build_morale_hero_atk.py -- give HEROES the same morale->Attack ladder units already have.

THE ASYMMETRY (measured 2026-08-27, live AoWEPACK.dpl vs AoWEPACK_original_backup.dpl).
Morale is a field on the shared base class: `AoWE.TAbstractUnit.GetMorale @0x5577F178` is
just `movsx eax,[eax+0x26]; call MoraleValueToMorale` -- so a THero carries a morale value
at +0x26 exactly as a TUnit does, and both convert it to a band 0..4 the same way. Despite
that, only two of the three stats reach heroes:

  stat  units                                       heroes
  RES   TUnit.GetResistance  @0x55782AF7 (table)    THero.GetResistance @0x5578856D (table)
  DEF   TUnit.GetDefense     @0x55782A6B (table)    THero.GetDefense    @0x55788449 (table)
  ATK   cave @0x5580C0FC off TUnit.GetAttack        -- NOTHING --

Both tables (`MoraleResistanceModifier @0x558E83D8`, `MoraleDefenseModifier @0x558E83E0`)
are read from both classes -- verified by a full disp32 xref sweep of CODE, which finds
exactly the four sites above and one cave. The ATK ladder is a *Ziggurat addition* with no
vanilla counterpart (`build_morale_scale.py`), and it was only ever wired into the unit
path. It uses neither `GetMorale` nor a table -- it reads the raw byte `[unit+0x26]` and
inlines the same 21/41/61/81 thresholds `MoraleValueToMorale` uses -- which is why an xref
hunt for morale readers does not turn it up and the gap went unnoticed.

User ruling 2026-08-27: heroes should feel morale on Attack exactly as units do. This
script closes that gap and nothing else.

WHAT IT DOES. One 5-byte hook plus one cave, both in `AoWEPACK.dpl`.

  hook  0x557883B1  in AoWE.THero.GetAttack, displacing EXACTLY five bytes:
                      02 c2        add   al, dl          ; fold in bought + chassis ATK
                      88 04 24     mov   byte [esp], al  ; store to the byte scratch
                    Byte-identical in the pristine DLL, so the site is vanilla code and no
                    other feature owns it. `build_hero_clamps.py` owns 0x557883CB/0x557883D1
                    (the [0,40] ceiling) -- five bytes clear of this hook, and the ceiling
                    still runs AFTER the ladder because the cave returns to 0x557883B6.

  cave  0x55818200  allocated out of the 0x5581817B..0x55820000 free run: 32,389 zero bytes
                    in both the live and the pristine DLL, and the ONLY run above
                    0x55810000 that no script under build_scripts/ mentions by address.
                    ⚠ A zero run is not a reservation -- so --undo
                    zeroes only the exact length this script emitted, never the whole run.

REGISTER STATE at the hook (read out of the function, not assumed):
  ebp = the THero          (set by `mov ebp,eax` @0x55788365, callee-saved thereafter)
  al  = the summed Attack  (abilities + items + bought [ebp+0x6a] + chassis [ecx+0x24])
  dl  = the last addend    (consumed by the displaced `add al,dl`)
  esp -> the one-byte scratch pushed by `push ecx` @0x55788364
edx is dead after the displaced add -- the tail reads only [esp] and eax -- so the cave is
free to clobber it. The cave pushes nothing, so [esp] still addresses the scratch.

LADDER -- identical to the unit cave @0x5580C0FC, deliberately including its BONUSES at the
top. Bands are the raw morale thresholds, not the 0..4 index:
      < 0x15  -4      < 0x29  -2      < 0x3d   0      < 0x51  +2      else  +4
Applied BEFORE the [0,40] clamp, matching the unit path exactly.

POSITION INDEPENDENCE. The DPL never loads at its preferred base. The cave uses only
register-relative operands ([ebp+0x26], [esp]) and one rel32 jump back into the host; the
hook is a rel32 jump out. Nothing here is an absolute address, so nothing needs a .reloc
entry, and none of the displaced bytes carries one (asserted on every run).

USAGE
    python build_scripts/build_morale_hero_atk.py            verify / dry run (writes nothing)
    python build_scripts/build_morale_hero_atk.py --dis      dry run + disassemble the cave
    python build_scripts/build_morale_hero_atk.py --apply    install
    python build_scripts/build_morale_hero_atk.py --undo     surgical revert (no backup touched)
"""
import argparse
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_statdouble import kill_aow, pe_sections, va2off  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
PRISTINE = os.path.join(GAME, "Modding Resources", "AoWEPACK_original_backup.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-moraleheroatk")

IMAGE_BASE = 0x55700000

HOOK_VA = 0x557883B1                      # inside AoWE.THero.GetAttack
HOOK_ORIG = bytes.fromhex("02c2880424")   # add al,dl ; mov byte [esp],al
RESUME_VA = 0x557883B6                    # the [0,40] clamp, straight after the scratch store
CAVE_VA = 0x55818200
CAVE_MAX = 0x40                           # reserved; the emitted length is what --undo zeroes

FREE_RUN = (0x5581817B, 0x55820000)       # the zero run the cave is allocated from

# Same five bands as the unit cave at 0x5580C0FC.
BANDS = ((0x15, -4), (0x29, -2), (0x3D, 0), (0x51, +2), (None, +4))


def cave_asm():
    """Emit the cave source. Kept as one string so --dis shows exactly what is assembled."""
    return """
        add   al, dl
        movsx edx, byte ptr [ebp + 0x26]
        cmp   edx, 0x15
        jl    band_terrible
        cmp   edx, 0x29
        jl    band_poor
        cmp   edx, 0x3d
        jl    done
        cmp   edx, 0x51
        jl    band_good
        add   al, 4
        jmp   done
    band_terrible:
        sub   al, 4
        jmp   done
    band_poor:
        sub   al, 2
        jmp   done
    band_good:
        add   al, 2
    done:
        mov   byte ptr [esp], al
    """


def assemble():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    body, _ = ks.asm(cave_asm(), CAVE_VA)
    body = bytes(body)
    # tail: jmp back into the host, rel32 from the end of the cave body
    tail_va = CAVE_VA + len(body)
    rel = RESUME_VA - (tail_va + 5)
    cave = body + b"\xe9" + struct.pack("<i", rel)
    if len(cave) > CAVE_MAX:
        sys.exit("cave %d bytes exceeds the %d reserved" % (len(cave), CAVE_MAX))
    hook = b"\xe9" + struct.pack("<i", CAVE_VA - (HOOK_VA + 5))
    assert len(hook) == len(HOOK_ORIG), "hook must displace exactly %d bytes" % len(HOOK_ORIG)
    return hook, cave


def disasm(blob, va):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for i in md.disasm(blob, va):
        print("    %08X  %-22s %s %s"
              % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str))


def reloc_vas(d):
    """Every VA carrying a .reloc entry, so a displaced run can be proven relocation-free."""
    e = struct.unpack_from("<I", d, 0x3C)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    dd = e + 24 + opt - 128 + 5 * 8          # IMAGE_DIRECTORY_ENTRY_BASERELOC
    rva, size = struct.unpack_from("<II", d, dd)
    if not rva:
        return set()
    base = va2off(d, IMAGE_BASE + rva)
    out, p, end = set(), base, base + size
    while p < end - 8:
        prva, blk = struct.unpack_from("<II", d, p)
        if not blk:
            break
        for k in range(p + 8, p + blk, 2):
            v = struct.unpack_from("<H", d, k)[0]
            if v >> 12:
                out.add(IMAGE_BASE + prva + (v & 0xFFF))
        p += blk
    return out


def check_environment(d):
    """Everything that must be true before this feature may be written."""
    ho = va2off(d, HOOK_VA)
    co = va2off(d, CAVE_VA)
    if ho is None or co is None:
        sys.exit("hook or cave VA does not map into the file")

    # the free run the cave sits in must still be zero end to end, minus our own cave
    fo, fe = va2off(d, FREE_RUN[0]), va2off(d, FREE_RUN[1])
    run = bytearray(d[fo:fe])
    _, cave = assemble()
    rel = co - fo
    run[rel:rel + len(cave)] = b"\x00" * len(cave)
    if any(run):
        first = next(i for i, b in enumerate(run) if b)
        sys.exit("free run no longer clear: first foreign byte at 0x%08X -- another feature "
                 "has taken this zone, pick a new CAVE_VA" % (FREE_RUN[0] + first))

    # the displaced run must carry no relocation
    rl = reloc_vas(d)
    hit = [v for v in rl if HOOK_VA <= v < HOOK_VA + len(HOOK_ORIG)]
    if hit:
        sys.exit("displaced bytes carry .reloc entries at %s -- cannot hook here"
                 % ", ".join("0x%08X" % v for v in hit))
    return ho, co


def state(d):
    ho, co = va2off(d, HOOK_VA), va2off(d, CAVE_VA)
    hook, cave = assemble()
    cur = bytes(d[ho:ho + len(HOOK_ORIG)])
    if cur == HOOK_ORIG and not any(d[co:co + len(cave)]):
        return "VANILLA"
    if cur == hook and bytes(d[co:co + len(cave)]) == cave:
        return "APPLIED"
    return "FOREIGN"


def main():
    ap = argparse.ArgumentParser(description="morale -> Attack for heroes (AoWEPACK.dpl)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true", help="disassemble the cave")
    a = ap.parse_args()

    print("build_morale_hero_atk -- morale ladder on THero.GetAttack")
    print("target: %s\n" % TARGET)

    d = bytearray(open(TARGET, "rb").read())
    hook, cave = assemble()
    st = state(d)

    # the hook site must be vanilla code -- proves no other feature owns it
    po = va2off(d, HOOK_VA)
    pris = open(PRISTINE, "rb").read()
    if bytes(pris[po:po + len(HOOK_ORIG)]) != HOOK_ORIG:
        sys.exit("pristine DLL disagrees about the hook site; HOOK_ORIG is wrong")

    print("  hook  0x%08X  %s  (%d bytes displaced, vanilla-matched)"
          % (HOOK_VA, HOOK_ORIG.hex(" "), len(HOOK_ORIG)))
    print("  cave  0x%08X  %d bytes emitted of %d reserved" % (CAVE_VA, len(cave), CAVE_MAX))
    print("  ladder %s  (raw morale thresholds, same as the unit cave @0x5580C0FC)"
          % " ".join("<0x%02X:%+d" % (t, v) if t else "else:%+d" % v for t, v in BANDS))
    print("\n  state: %s\n" % st)

    if a.dis:
        print("  cave disassembly (assembled at 0x%08X):" % CAVE_VA)
        disasm(cave, CAVE_VA)
        print()

    if a.undo:
        if st == "VANILLA":
            print("  already vanilla -- nothing to do.")
            return
        if st != "APPLIED":
            sys.exit("state is FOREIGN -- refusing to undo bytes this script did not write")
        kill_aow()
        ho, co = va2off(d, HOOK_VA), va2off(d, CAVE_VA)
        d[ho:ho + len(HOOK_ORIG)] = HOOK_ORIG
        d[co:co + len(cave)] = b"\x00" * len(cave)   # only our own emitted length
        open(TARGET, "wb").write(bytes(d))
        print("  reverted: hook restored, %d cave bytes zeroed. No backup touched." % len(cave))
        return

    if not a.apply:
        print("(dry run -- nothing written.  --apply to patch, --undo to revert)")
        return

    if st == "APPLIED":
        print("  already applied and up to date -- nothing to do.")
        return
    if st == "FOREIGN":
        sys.exit("state is FOREIGN -- the hook site or cave holds bytes this script did not "
                 "write. Refusing to overwrite.")

    ho, co = check_environment(d)
    kill_aow()
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP)
        print("  backup -> %s" % os.path.basename(BACKUP))
    d[ho:ho + len(hook)] = hook
    d[co:co + len(cave)] = cave
    open(TARGET, "wb").write(bytes(d))
    print("  applied: hook + %d-byte cave written." % len(cave))
    print("\n  NEEDS THE USER'S IN-GAME TEST -- nothing here is confirmed:")
    print("    1. a hero at High morale (81+) shows Attack +4 over its unmodified value")
    print("    2. a hero at Terrible morale (<21) shows -4, and never below 0")
    print("    3. a hero at Okay morale (41-60) is unchanged")
    print("    4. units are unaffected by this change (their ladder is a separate cave)")
    print("    5. the hero level-up dialog and the unit card agree on the number")


if __name__ == "__main__":
    main()
