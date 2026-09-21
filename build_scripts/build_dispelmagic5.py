#!/usr/bin/env python3
"""Dispel Magic IV + V — raise the ability's level cap from III to V (AoWEPACK.dpl).

WHY THIS IS CHEAP
-----------------
Dispel Magic has **no per-level value ladder to extend**. The entire effect of a level flows
through one formula:

    TDispelMagicAbility.GetDispelMana @0x5576CEA8  =  GetLevel(owner) * 10 + 20

which is fed straight to TEnchantment.DispelChance @0x5577C1A0:

    chance = clamp(mana - 10*ench[+0x14] + 50, 10, 90)

so IV and V get strength 60 / 70 for free, in all three consumers (fcExecuteCombatCommand,
TDispelMagicCA.Generate, TDispelMagicAbilityTE.Execute). GetSkillPoints @0x5576D174 is
`GetLevel * 5` (lea eax,[eax+eax*4]) and ExpandCost @0x5576D130 is a flat 5 — both scale or are
cap-independent. Contrast Leadership, whose fixed-size atk/def tables had to be relocated to a
cave for its 4th level (build_leadership4.py).

⚠ Dispel Magic does NOT use the base TMultiLevelAbility cap `ability[+0x28]`. It overrides the
level machinery with its own hard-coded 3 in TWO places, and its level byte is at
TDispelMagicAbilityData **+0x0D** (+0x0C is the per-turn enabled toggle), not the base class's
+0x0C. Patching `[+0x28]` would do nothing.

WHAT IS PATCHED (3 sites + 1 cave)
----------------------------------
 1. CanExpand  @0x5576D163   `cmp eax, 3`            imm 03 -> 05   (offer the upgrade)
 2. Expand     @0x5576D1D0   `cmp byte [ebp+0xD], 3` imm 03 -> 05   (allow the increment)
 3. GetLevelName default arm @0x5576CF61 — already a 5-byte `jmp 0x5576CFF8`; retarget to the
    cave. At that point EDX = level-3, EBX = out PAnsiString, EAX = 0, EBP frame with locals
    [ebp-8]/[ebp-4], SEH active. Cave appends " IV" / " V" using the function's own idiom
    (LoadResString(DispelMagicRStr) -> TranslateRStr -> @LStrCat3) and falls through to the
    original default arm for level > 5.

Level names reuse existing literals — ' IV' @0x557BBF40 (Marksmanship's), ' V' @0x5576DE04 —
byte-verified as length-prefixed Delphi strings before use. Nothing new is minted.

The cave is POSITION-INDEPENDENT (call/pop/sub delta for the three data pointers; rel32 for the
three calls), because the DPL never loads at its preferred base.

CAVE CHOICE + CAVE HISTORY
--------------------------
Current cave: **0x55821000**, an EXCLUSIVE RESERVATION of 0x55821000..0x558213FF. Verified before
allocation (2026-08-26): 1024 zero bytes, no .reloc entries in the range, inside CODE vsize
(CODE ends 0x558E7918). It sits between build_caster_cost.py's reservation (0x55820800..0x55820FFF, claimed
2026-08-26) and build_shipyard_income.py's floor (0x55822000), touching neither.

*** WHY IT MOVED -- READ THIS BEFORE ALLOCATING ANY CAVE ***
The original cave was 0x55812AA0, chosen because that zero run was "referenced by no script in
build_scripts/". That was true when written and FALSE four months later: build_magebane.py was
later given CAVE_VA = 0x55812900 with CAVE_LIMIT = 0x200, i.e. 0x55812900..0x55812AFF -- which
swallows 0x55812AA0. Magebane's registration cave now occupies 0x55812A90..0x55812AB4.

The result was a live crash. This script's three site-patches stayed correct, but its cave was
gone, so GetLevelName's default arm jumped to 0x55812AA0 -- the imm32 tail of Magebane's
`mov eax,0xAA` at 0x55812A9D. Execution began on `00 00` = `add byte ptr [eax], al` with EAX == 0
(xor eax,eax at 0x5576CF46, never rewritten), i.e. a null write. Both level caps read 05, so
Dispel Magic IV/V were reachable and faulted. Magebane itself was unharmed.

THE LESSON, worth more than the fix:
  "No script references this zero run" is a statement about a MOMENT IN TIME, not a reservation.
  Record a cave address in the allocation map the day it is claimed, declare its extent, and make
  --undo zero ONLY the emitted length -- never a rounded reservation, which is what would let one
  feature's undo silently destroy another's cave.

OLD_CAVES lists the stolen address so this script can RECOGNISE the damage instead of aborting on
it: a JMP_SITE holding a rel32 to a listed old cave is reported as STALE (recoverable) rather than
OTHER (corrupt), and --apply repairs it by repointing the jump and rebuilding the cave elsewhere.
The stolen zone is never written -- its current owner keeps it.

BACKUPS: .pre-dispelmagic5 is a 2026-08-09 snapshot and is NOT a revert path -- restoring it would
wipe every feature applied since. The revert path is --undo. This repair takes its own fresh
backup, .pre-dm5cavemove.

PRIOR ART: Inioch's `Modding Resources/Inioch/fable beast mode/share to discord 1/
patch_dispelmagic5_v1.py` does the same three sites with the same cave shape. Two of its claims do
NOT hold for this install and were re-measured rather than copied:
  * it says ExpandCost is "a flat 1 skill point" — here it is **5**;
  * it declares a hard dependency on `patch_inherent_level_fix_v1.py` (DM VMT+0x94 -> own
    GetLevel) or "level purchases would be silently discarded by UpdateDefaultAbilities".
    NOT REPRODUCED HERE and deliberately not included — see the note at the bottom of this
    docstring. If in-game testing shows purchased levels reverting, that is the first suspect.

Usage:  python build_scripts/build_dispelmagic5.py            # dry run + cave disassembly
        python build_scripts/build_dispelmagic5.py --apply
        python build_scripts/build_dispelmagic5.py --undo     # surgical: restores 3 sites, zeroes cave
"""
import os, sys, struct, shutil, subprocess

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-dispelmagic5")
# ^ nothing writes this path any more, and no such file is on disk. A whole-file restore would
#   wipe every feature applied since it was taken, so it is NOT a revert path -- --undo is.
#   The cave-move repair takes its own fresh backup (BAK_REPAIR) instead.
BAK_REPAIR = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-dm5cavemove")

# ---- addresses (preferred-base VAs) -------------------------------------------------
CANEXPAND_IMM = 0x5576D163          # the 03 in `cmp eax, 3`
EXPAND_IMM    = 0x5576D1D0          # the 03 in `cmp byte [ebp+0xD], 3`
JMP_SITE      = 0x5576CF61          # `jmp 0x5576CFF8`, 5 bytes
NAME_DEF      = 0x5576CFF8          # GetLevelName's bare-name epilogue

DM_RSTR  = 0x55709AEC               # AoWE.DispelMagicRStr
LOADRES  = 0x55701210               # VCL30 System.LoadResString thunk
TRANSL   = 0x557249FC               # AoWE.TranslateRStr
LSTRCAT3 = 0x55701190               # VCL30 System.@LStrCat3 thunk
LIT_IV   = 0x557BBF40               # ' IV'
LIT_V    = 0x5576DE04               # ' V'

CAVE       = 0x55821000              # EXCLUSIVE RESERVATION 0x55821000..0x558213FF
CAVE_LIMIT = 0x55821400             # (absolute end VA, not a length)

# Cave addresses this feature used to live at whose zone has since been taken by another feature.
# JMP_SITE pointing at one of these means "my jmp is installed but my cave was stolen" -- a
# RECOVERABLE state, not a corrupt one. See CAVE HISTORY in the docstring.
OLD_CAVES  = (0x55812AA0,)          # taken by build_magebane.py 0x55812900..0x55812AFF
NEW_CAP    = 5

PROCS = ("AoW", "AoWCompat", "AoWDevEd", "AoWEd")


# ---- VA -> file offset via the PE section table (never a flat delta: it is per-section) ----
def sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    out = []
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        name = data[o:o + 8].rstrip(b"\0").decode()
        vsz, va, rsz, praw = struct.unpack_from("<IIII", data, o + 8)
        out.append((name, base + va, max(vsz, rsz), praw))
    return out


def va2off(data, va):
    for name, sva, sz, praw in sections(data):
        if sva <= va < sva + sz:
            return praw + (va - sva)
    raise ValueError("VA %08X is in no section" % va)


# ---- cave assembly (hand-encoded; disassembled below for review) --------------------
class Asm:
    def __init__(self, base):
        self.base, self.buf, self.lab, self.fix = base, bytearray(), {}, []

    def here(self):
        return self.base + len(self.buf)

    def db(self, *b):
        self.buf += bytes(b)

    def dd(self, v):
        self.buf += struct.pack("<I", v & 0xFFFFFFFF)

    def label(self, n):
        self.lab[n] = self.here()

    def j8(self, op, n):
        self.db(op); self.fix.append((len(self.buf), n)); self.db(0)

    def call(self, t):
        self.db(0xE8); self.buf += struct.pack("<i", t - (self.here() + 4))

    def jmp32(self, t):
        self.db(0xE9); self.buf += struct.pack("<i", t - (self.here() + 4))

    def pic_delta(self):
        """EAX := runtimeBase - preferredBase, without touching any other register."""
        self.call(self.here() + 5)          # call $+5
        link = self.here()
        self.db(0x58)                       # pop eax
        self.db(0x2D); self.dd(link)        # sub eax, <link VA>

    def done(self):
        for off, n in self.fix:
            rel = self.lab[n] - (self.base + off + 1)
            assert -128 <= rel <= 127, "short jump out of range"
            self.buf[off] = rel & 0xFF
        return bytes(self.buf)


def build_cave():
    a = Asm(CAVE)
    a.db(0x4A)                       # dec edx           ; level 4 -> 0
    a.j8(0x74, "four")
    a.db(0x4A)                       # dec edx           ; level 5 -> 0
    a.j8(0x74, "five")
    a.jmp32(NAME_DEF)                # level > 5 -> bare name

    a.label("four")
    a.pic_delta()
    a.db(0x8D, 0x88); a.dd(LIT_IV)   # lea ecx, [eax + LIT_IV]
    a.j8(0xEB, "body")

    a.label("five")
    a.pic_delta()
    a.db(0x8D, 0x88); a.dd(LIT_V)    # lea ecx, [eax + LIT_V]

    a.label("body")
    a.db(0x51)                       # push ecx          ; stash the literal's runtime addr
    a.db(0x05); a.dd(DM_RSTR)        # add eax, DM_RSTR  ; eax = runtime DispelMagicRStr
    a.db(0x8D, 0x55, 0xF8)           # lea edx, [ebp-8]
    a.call(LOADRES)
    a.db(0x8B, 0x45, 0xF8)           # mov eax, [ebp-8]
    a.db(0x8D, 0x55, 0xFC)           # lea edx, [ebp-4]
    a.call(TRANSL)
    a.db(0x59)                       # pop ecx
    a.db(0x8B, 0x55, 0xFC)           # mov edx, [ebp-4]
    a.db(0x8B, 0xC3)                 # mov eax, ebx      ; out PAnsiString
    a.call(LSTRCAT3)
    a.jmp32(NAME_DEF)                # rejoin the epilogue (it clears the locals)
    return a.done()


def rel32(src, dst):
    return b"\xE9" + struct.pack("<i", dst - (src + 5))


def disasm(code, va):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return "  (capstone not installed - cave not disassembled)"
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    return "\n".join("  %08X  %-8s %s" % (i.address, i.mnemonic, i.op_str)
                     for i in md.disasm(code, va))


def kill_game():
    # ⚠ SCRATCH GUARD (2026-09-03): AOW_GAME_DIR set => we are NOT writing to the real
    # install, so we must NOT kill the user's running game. Without this, an agent doing a
    # "safe" scratch-copy round-trip still terminates the live game -- which happened, and
    # was misreported as a crash-on-expiry. Standing kill authorization applies to the real
    # install only.
    if os.environ.get("AOW_GAME_DIR"):
        return
    ps = ("Get-Process | Where-Object { $_.ProcessName -match '^(%s)$' } | Stop-Process -Force"
          % "|".join(PROCS))
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True, text=True)


def main():
    apply_ = "--apply" in sys.argv
    undo = "--undo" in sys.argv
    cave = build_cave()
    assert CAVE + len(cave) <= CAVE_LIMIT, "cave overflow: %d bytes" % len(cave)

    data = bytearray(open(DLL, "rb").read())

    # (va, vanilla_bytes, patched_bytes, description)
    sites = [
        (CANEXPAND_IMM, b"\x03", bytes([NEW_CAP]), "CanExpand cap 3 -> %d" % NEW_CAP),
        (EXPAND_IMM,    b"\x03", bytes([NEW_CAP]), "Expand increment cap 3 -> %d" % NEW_CAP),
        (JMP_SITE, rel32(JMP_SITE, NAME_DEF), rel32(JMP_SITE, CAVE),
         "GetLevelName default arm -> cave_dm5name"),
        (CAVE, bytes(len(cave)), cave, "cave_dm5name @0x%X (%dB)" % (CAVE, len(cave))),
    ]

    stale_jmps = {rel32(JMP_SITE, ov): ov for ov in OLD_CAVES}

    state = []
    for va, orig, new, desc in sites:
        cur = bytes(data[va2off(data, va):va2off(data, va) + len(orig)])
        if cur == new:
            state.append("patched")
        elif cur == orig:
            state.append("vanilla")
        elif va == JMP_SITE and cur in stale_jmps:
            state.append("STALE")
        else:
            state.append("OTHER")

    print("Dispel Magic level cap III -> V   (%s)" % DLL)
    for (va, orig, new, desc), st in zip(sites, state):
        print("  [%-7s] %08X  %s" % (st, va, desc))

    if "STALE" in state:
        cur = bytes(data[va2off(data, JMP_SITE):va2off(data, JMP_SITE) + 5])
        print("")
        print("  *** CAVE WAS STOLEN ***")
        print("      GetLevelName's default arm still jumps to 0x%08X, which now belongs to"
              % stale_jmps[cur])
        print("      another feature. Dispel Magic IV/V crash there: the jump lands")
        print("      mid-instruction and EAX is 0, so it executes as a null write.")
        print("      --apply repoints the jump at the new cave 0x%08X and rebuilds it." % CAVE)
        print("      The stolen zone is NOT touched -- its current owner keeps it.")

    if "OTHER" in state:
        print("\nABORT: a site holds bytes that are neither vanilla nor this patch.")
        for (va, orig, new, desc), st in zip(sites, state):
            if st == "OTHER":
                off = va2off(data, va)
                print("  %08X expected %s\n           or       %s\n           found    %s"
                      % (va, orig.hex(" ")[:64], new.hex(" ")[:64],
                         bytes(data[off:off + len(orig)]).hex(" ")[:64]))
        return 1

    if undo:
        if all(s == "vanilla" for s in state):
            print("\nAlready vanilla - nothing to undo."); return 0
        kill_game()
        if not os.path.exists(BAK_REPAIR):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(DLL, BAK_REPAIR); print("\nBackup: %s" % BAK_REPAIR)
        for va, orig, new, desc in sites:
            off = va2off(data, va)
            data[off:off + len(orig)] = orig
        open(DLL, "wb").write(data)
        print("\nUNDONE: 3 sites restored, cave zeroed. Dispel Magic is back to I-III.")
        return 0

    if all(s == "patched" for s in state):
        print("\nALREADY APPLIED - nothing to do.")
        print(cave_report())
        return 0

    print("\ncave_dm5name @0x%X (%d bytes):" % (CAVE, len(cave)))
    print(disasm(cave, CAVE))
    print(cave_report())

    if not apply_:
        print("\nDry run OK. Re-run with --apply to write.")
        return 0

    kill_game()
    if not os.path.exists(BAK_REPAIR):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BAK_REPAIR); print("\nBackup: %s" % BAK_REPAIR)
    for va, orig, new, desc in sites:
        off = va2off(data, va)
        data[off:off + len(new)] = new
        print("Patched: %s" % desc)
    open(DLL, "wb").write(data)
    print("\nAoWEPACK.dpl patched. Dispel Magic now goes to V.")
    return 0


def cave_report():
    return (
        "\nResulting ladder (strength = GetDispelMana = level*10+20):\n"
        "  level     I    II   III    IV     V\n"
        "  strength 30    40    50    60    70\n"
        "  skill pt  5    10    15    20    25   (GetSkillPoints = level*5; each buy costs 5)\n"
        "\n  dispel chance = clamp(strength - 10*R + 50, 10, 90), R = enchantment resistance:\n"
        "    R=3 (Bless/Haste/Fury/Stone Skin/Enchant Weapon/Dark Gift)  50 60 70 80 90 %\n"
        "    R=4 (Concealment/Fire Aura/Free Movement/Champion/Healing Water) 40 50 60 70 80 %\n"
        "    R=5 (Liquid Form/Wind Walking)                              30 40 50 60 70 %\n"
        "    R=6 (Water Walking)                                         20 30 40 50 60 %\n"
        "  V vs an R=3 enchantment hits the 90% clamp - the ceiling is reached at level V.")


if __name__ == "__main__":
    sys.exit(main())
