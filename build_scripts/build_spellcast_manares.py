#!/usr/bin/env python
r"""
build_spellcast_manares.py -- hero mana generation scales off Resistance x Spellcasting level.

WHAT THIS CHANGES.  A hero's mana income is "power generation". Every hero registers a
`THeroPowerSource` (`THero.SetPlayer @0x55787388`, `THero.Activate @0x55787512`),
`TPlayerMagicControl.GetPower @0x5577CA00` sums `Power()` over that list, and
`GetManaIncome @0x5577C95C` -> `GetNetPowerToMana` takes off the research share and applies
the player-type factor. The chain down to the number this script rewrites:

    THeroPowerSource.Power     @0x557867D0  -> hero.vtable[+0x134]
    TLeader.GetPowerGeneration @0x5578B43C     (THero's slot @0x557885E4 tail-calls it)
        GetAbilityEnabled(0x34)  via vtable[+0x148]      item-aware
        GetAbilityLevel(0x34)    via vtable[+0x144]      item-aware
        call 0x557885EC         <-- THE ONLY THING THIS SCRIPT TOUCHES

    before   a five-entry lookup table: 10 / 20 / 40 / 60 / 90 for Spellcasting I..V
    after    level * Resistance          (user ruling 2026-08-27: 1x, not 3x)

`--undo` restores that TABLE, not vanilla. Vanilla was neither: it was `lea eax,[eax+eax*4];
add eax,5` = level*5 + 5 (10/15/20/25/30) written inline. The 10/20/40/60/90 table is a
PRE-CONVENTION Ziggurat patch that no script under build_scripts/ owned until this one --
it was carved out of vanilla's duplicate `THero.GetPowerGeneration` body, which the same
patch collapsed into a tail-call, freeing exactly these 40 bytes.

NO CAVE AND NO HOOK -- this is an in-place rewrite of a zone the project already owns.
Proved on every run, not assumed:
  * 0x557885EC..0x55788613 is 40 bytes bounded by `THero.GetCastingPointsMax @0x55788614`;
  * a full-file sweep finds EXACTLY ONE reference into that range, the rel32 call at
    0x5578B461. Nothing else can land in it, so nothing else can be broken by rewriting it;
  * the range carries NO .reloc entries, so nothing needs relocating at load time.
Because no cave is allocated, this feature cannot collide with any cave-allocating script,
now or later (cf. the Magebane / dispelmagic5 collision).

REGISTER CONTRACT at 0x557885EC, read out of the caller rather than assumed:
    eax = the Spellcasting level, from `call [ecx+0x144]`
    ebx = the THero / TLeader    (`mov ebx,eax` @0x5578B43D; EBX is callee-saved under the
                                  Delphi register convention, so it survives both vtable
                                  calls -- the caller's own `pop ebx` relies on that too)
The caller's 44 bytes are verified byte-for-byte before any write, so if a future patch ever
displaces that prologue this script refuses rather than reading a stale register.

RESISTANCE comes from vtable[+0xCC], which is `THero.GetResistance @0x5578850C` for BOTH
THero and TLeader (checked: both VMTs hold the same pointer). That is the number the hero
card shows -- chassis + bought points + ability modifiers + items + morale -- and it is
clamped to [0, 40] at 0x55788586 before it returns in AL, so `movzx eax, al` can never
see a negative value. Worst case output is therefore 5 * 40 = 200 per hero per turn.
`GetPower` accumulates with a full 32-bit `add edi, eax`, so there is no byte truncation.

UNITS ARE UNAFFECTED, automatically: `TUnit` and `TAdjustableUnit` VMT +0x134 still point at
`TAbstractUnit.GetPowerGeneration @0x5577FDB4` = `xor eax,eax; ret`. build_spellcast.py
deliberately never redirected that slot ("Phase 3 -- cancelled"). Asserted on every run.

ONE BINARY. AoW.exe / AoWCompat.exe / AoWTCPCK.dpl / aowInt.dpl / AoWDevEd.exe carry neither
a copy of the formula nor any `call [reg+0x134]`; the exe reads the magic window through
GetPower / GetManaIncome / TPowerSourceList.GetItems and calls `Power()` dynamically, so
every display and the AI budget follow this change for free. No lockstep edit is needed.

POSITION INDEPENDENCE. The DPL never loads at its preferred base. The emitted code is
register-relative only -- no absolute memory operand, no rel32 -- so it needs no .reloc
entry and is valid at any load address.

USAGE
    python build_scripts/build_spellcast_manares.py            verify / dry run (writes nothing)
    python build_scripts/build_spellcast_manares.py --dis      dry run + disassembly
    python build_scripts/build_spellcast_manares.py --apply    install
    python build_scripts/build_spellcast_manares.py --undo     surgical revert to the table
"""
import argparse
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_statdouble import kill_aow, va2off  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-spellcastmanares")

IMAGE_BASE = 0x55700000

ZONE_VA = 0x557885EC                 # the level->power body, reached only from the caller
ZONE_END = 0x55788614                # THero.GetCastingPointsMax starts here -- hard stop
ZONE_LEN = ZONE_END - ZONE_VA        # 40 bytes

CALLER_VA = 0x5578B43C               # AoWE.TLeader.GetPowerGeneration
CALL_SITE = 0x5578B461               # the `call 0x557885EC` inside it
NEIGHBOUR_VA = 0x55788614            # THero.GetCastingPointsMax -- must stay intact
UNIT_STUB_VA = 0x5577FDB4            # TAbstractUnit.GetPowerGeneration = xor eax,eax; ret

VMT_RES = 0xCC                       # GetResistance   (THero.GetResistance @0x5578850C)
VMT_POWERGEN = 0x134                 # GetPowerGeneration

MULTIPLIER = 1                       # user ruling 2026-08-27; mana = level * RES * MULTIPLIER

# The pre-feature Ziggurat lookup table, 10/20/40/60/90 + two pad bytes. --undo writes this.
OLD_BODY = bytes.fromhex(
    "85c07501c33c017503b00ac33c027503b014c33c037503b028c33c047503b03cc331c0b05ac30000")

# The caller's full body. Establishes eax = level and ebx = self at ZONE_VA.
CALLER_ORIG = bytes.fromhex(
    "538bd8ba340000008bc38b08ff914801000084c07417"
    "ba340000008bc38b08ff9144010000e886d1ffff5bc3")

# VMT class-reference VAs (the `AoWE..TClass` symbols), used to assert the slot wiring.
VMTS = {
    "THero": 0x55711FEC,
    "TLeader": 0x55712238,
    "TUnit": 0x55710CAC,
    "TAdjustableUnit": 0x55712A54,
}


def body_asm():
    """The replacement body. One string so --dis shows exactly what gets assembled.

    No comments inside: keystone treats ';' as a statement separator, not a comment lead-in.

        movzx eax, al                 Spellcasting level, defensively widened
        push  eax
        mov   eax, ebx                self -- the THero / TLeader
        mov   edx, dword ptr [eax]    its VMT
        call  dword ptr [edx + 0xCC]  THero.GetResistance -> al, clamped [0,40]
        movzx eax, al
        pop   edx                     level
        imul  eax, edx                RES * level
        <multiplier tail>
        ret
    """
    src = """
        movzx eax, al
        push  eax
        mov   eax, ebx
        mov   edx, dword ptr [eax]
        call  dword ptr [edx + 0xCC]
        movzx eax, al
        pop   edx
        imul  eax, edx
    """
    if MULTIPLIER == 2:
        src += "        add   eax, eax\n"
    elif MULTIPLIER == 3:
        src += "        lea   eax, [eax + eax*2]\n"
    elif MULTIPLIER != 1:
        src += "        imul  eax, eax, %d\n" % MULTIPLIER
    return src + "        ret\n"


def assemble():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code, _ = ks.asm(body_asm(), ZONE_VA)
    code = bytes(code)
    if len(code) > ZONE_LEN:
        sys.exit("body %d bytes exceeds the %d-byte zone" % (len(code), ZONE_LEN))
    return code, code + b"\x00" * (ZONE_LEN - len(code))


def disasm(blob, va):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob, va):
        print("    %08X  %-16s %s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str))


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    p = e + 24 + struct.unpack_from("<H", d, e + 20)[0]
    out = []
    for _ in range(n):
        name = bytes(d[p:p + 8]).rstrip(b"\x00").decode("latin1")
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, p + 8)
        out.append((name, vaddr, vsize, raw, rsize))
        p += 40
    return out


def reloc_vas(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + opt - 128 + 5 * 8)
    if not rva:
        return set()
    p = va2off(d, IMAGE_BASE + rva)
    out, end = set(), p + size
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


def refs_into_zone(d):
    """Every rel32 call/jmp and every absolute dword landing inside the zone."""
    hits = []
    for name, vaddr, vsize, raw, rsize in sections(d):
        lim = min(vsize, rsize)
        if not lim:
            continue
        sec = bytes(d[raw:raw + lim])
        if name in ("CODE", ".text", ".itext"):
            for i in range(lim - 5):
                if sec[i] in (0xE8, 0xE9):
                    src = IMAGE_BASE + vaddr + i
                    tgt = (src + 5 + struct.unpack_from("<i", sec, i + 1)[0]) & 0xFFFFFFFF
                    if ZONE_VA <= tgt < ZONE_END:
                        hits.append(("rel32", src, tgt))
        for i in range(lim - 3):
            v = struct.unpack_from("<I", sec, i)[0]
            if ZONE_VA <= v < ZONE_END:
                hits.append(("abs", IMAGE_BASE + vaddr + i, v))
    return hits


def rd32(d, va):
    return struct.unpack_from("<I", d, va2off(d, va))[0]


def check_environment(d):
    """Everything that must hold before this zone may be rewritten."""
    zo = va2off(d, ZONE_VA)
    if zo is None:
        sys.exit("zone VA does not map into the file")

    # 1. the caller must be intact -- it is what puts eax = level and ebx = self
    co = va2off(d, CALLER_VA)
    cur = bytes(d[co:co + len(CALLER_ORIG)])
    if cur != CALLER_ORIG:
        sys.exit("caller at 0x%08X has changed -- the eax/ebx contract is no longer proven.\n"
                 "  expected %s\n  found    %s"
                 % (CALLER_VA, CALLER_ORIG.hex(" "), cur.hex(" ")))

    # 2. VMT wiring: heroes reach this code, units must NOT
    for cls, exp in (("THero", 0x557885E4), ("TLeader", CALLER_VA)):
        got = rd32(d, VMTS[cls] + VMT_POWERGEN)
        if got != exp:
            sys.exit("%s VMT +0x%X is 0x%08X, expected 0x%08X" % (cls, VMT_POWERGEN, got, exp))
    for cls in ("TUnit", "TAdjustableUnit"):
        got = rd32(d, VMTS[cls] + VMT_POWERGEN)
        if got != UNIT_STUB_VA:
            sys.exit("%s VMT +0x%X is 0x%08X, not the zero stub 0x%08X -- units would start "
                     "generating mana. Refusing." % (cls, VMT_POWERGEN, got, UNIT_STUB_VA))
    so = va2off(d, UNIT_STUB_VA)
    if bytes(d[so:so + 4]) != bytes.fromhex("33c0c390"):
        sys.exit("TAbstractUnit.GetPowerGeneration is no longer `xor eax,eax; ret`")

    # 3. GetResistance must be the same implementation for both hero classes
    rh, rl = rd32(d, VMTS["THero"] + VMT_RES), rd32(d, VMTS["TLeader"] + VMT_RES)
    if rh != rl:
        sys.exit("THero and TLeader disagree on GetResistance (0x%08X vs 0x%08X); one "
                 "`call [edx+0xCC]` can no longer serve both" % (rh, rl))

    # 4. nothing but the known call site may reach into the zone
    hits = refs_into_zone(d)
    foreign = [h for h in hits if not (h[0] == "rel32" and h[1] == CALL_SITE)]
    if foreign:
        sys.exit("foreign references into the zone: %s -- refusing to rewrite"
                 % ", ".join("%s from 0x%08X -> 0x%08X" % h for h in foreign))
    if not hits:
        sys.exit("no reference into the zone at all -- the site is unreachable, so ZONE_VA "
                 "or the caller is wrong")

    # 5. the zone must carry no relocation, and the neighbour must be untouched
    bad = [v for v in reloc_vas(d) if ZONE_VA <= v < ZONE_END]
    if bad:
        sys.exit("zone carries .reloc entries at %s" % ", ".join("0x%08X" % v for v in bad))
    nb = va2off(d, NEIGHBOUR_VA)
    if bytes(d[nb:nb + 8]) != bytes.fromhex("538bd8ba34000000"):
        sys.exit("THero.GetCastingPointsMax @0x%08X does not start where expected -- the zone "
                 "bound is wrong" % NEIGHBOUR_VA)
    return zo


def state(d):
    zo = va2off(d, ZONE_VA)
    cur = bytes(d[zo:zo + ZONE_LEN])
    _, new = assemble()
    if cur == OLD_BODY:
        return "TABLE"
    if cur == new:
        return "APPLIED"
    return "FOREIGN"


def main():
    ap = argparse.ArgumentParser(description="hero mana generation = Spellcasting level x RES")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true", help="disassemble the replacement body")
    a = ap.parse_args()

    print("build_spellcast_manares -- mana generation = Spellcasting level x Resistance x %d"
          % MULTIPLIER)
    print("target: %s\n" % TARGET)

    d = bytearray(open(TARGET, "rb").read())
    code, new = assemble()
    st = state(d)

    print("  zone   0x%08X..0x%08X  (%d bytes, sole caller 0x%08X)"
          % (ZONE_VA, ZONE_END - 1, ZONE_LEN, CALL_SITE))
    print("  body   %d bytes emitted, %d spare" % (len(code), ZONE_LEN - len(code)))
    print("  before 10 / 20 / 40 / 60 / 90 for Spellcasting I..V (flat table)")
    for r in (4, 6, 8, 12, 20, 40):
        print("  after  RES %-2d ->  %s"
              % (r, " / ".join("%3d" % (lv * r * MULTIPLIER) for lv in range(1, 6))))
    print("\n  state: %s\n" % st)

    if a.dis:
        print("  replacement body (assembled at 0x%08X):" % ZONE_VA)
        disasm(code, ZONE_VA)
        print()

    if a.undo:
        if st == "TABLE":
            print("  already the 10/20/40/60/90 table -- nothing to do.")
            return
        if st != "APPLIED":
            sys.exit("state is FOREIGN -- refusing to undo bytes this script did not write")
        kill_aow()
        zo = va2off(d, ZONE_VA)
        d[zo:zo + ZONE_LEN] = OLD_BODY
        open(TARGET, "wb").write(bytes(d))
        print("  reverted: the 10/20/40/60/90 lookup table is back. No backup touched.")
        return

    if not a.apply:
        print("(dry run -- nothing written.  --apply to patch, --undo to revert)")
        return

    if st == "APPLIED":
        print("  already applied and up to date -- nothing to do.")
        return
    if st == "FOREIGN":
        sys.exit("state is FOREIGN -- the zone holds bytes this script did not write and that "
                 "are not the known table. Refusing to overwrite.")

    zo = check_environment(d)
    kill_aow()
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP)
        print("  backup -> %s" % os.path.basename(BACKUP))
    d[zo:zo + ZONE_LEN] = new
    open(TARGET, "wb").write(bytes(d))
    print("  applied: %d-byte body written, %d trailing bytes zeroed."
          % (len(code), ZONE_LEN - len(code)))
    print("\n  NEEDS THE USER'S IN-GAME TEST -- nothing here is confirmed:")
    print("    1. a hero with Spellcasting I and RES 6 adds 6 to power, not 10")
    print("    2. raising that hero's RES (level-up point or a RES item) raises the income")
    print("    3. the leader/wizard scales the same way (TLeader shares the code)")
    print("    4. a UNIT with Spellcasting still generates NOTHING")
    print("    5. hiring a hero mid-game and loading a save with heroes both work -- the new")
    print("       code runs GetResistance during THero.Activate's power-source registration")
    print("    6. the magic window's per-hero power line matches level x RES")


if __name__ == "__main__":
    main()
