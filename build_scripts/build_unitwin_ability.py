#!/usr/bin/env python3
r"""Let a hero USE an activatable ability that an ITEM grants, from the unit window.

STATUS: CONFIRMED WORKING in game (2026-08-28) -- but only TOGETHER with the cave_tiergate fix in
build_spellcast_multiturn.py. This patch alone opens the spellbook; the DLL-side tier gate then
refused every spell because it fetched the caster's Spell Casting level with a STATIC call to
TAbstractUnit.GetAbilityLevel (the base), bypassing THero's item-aware override. Both are needed;
neither is sufficient. See Investigation_Items.md §3.3c.

THE BUG (vanilla; confirmed in play 2026-08-28 by the author)
------------------------------------------------------------
`TUnitWindow` fills its ability list through the **item-aware** `TAbstractUnit.ListAbilityInfo`
@0x5577FA50, so an ability granted by a carried/worn item is listed and looks completely normal.
Clicking that row runs `TUnitWindow.UseAbility @0x00409E90`, whose one and only possession test is

    00409EEF  mov edx,[[0x45A420]+0xC0]     ; edx = the selected unit
    00409EF5  mov eax, esi                  ; eax = the TAbility
    00409EF7  mov ecx,[eax] / call [ecx+0x74]   <-- THE SITE
    00409EFC  test al,al / je 0x409FD7      ; -> silent return, message word still 0

and `[ability.vmt+0x74]` is `AoWE.TAbility.GetEnabled @0x5574EEF4`:

    5574EEF4  mov eax,[eax+0xC] ; xchg edx,eax ; mov ecx,[eax] ; call [ecx+0x4C]

i.e. `unit.GetAbSet(id)` -- `TCustomAbilityList.GetAbSet @0x5574E0E0`, a raw `bt` on the unit's
OWN bit array. `THero.GetAbSet @0x55788104` is a bare passthrough to it, so items are invisible
here. **List item-aware, activation self-only** -> the row is clickable-looking and inert.

⚠ It is NOT about multi-level abilities. `GetEnabled` is a bit test with no level in it, identical
for every ability class. Ranged attacks merely escape because `TRangedAttackAbility.GetControlType`
is `{acCombatAction}` with no `acAction` bit, so they are never activated from this window at all.

WHAT IS REACHABLE (installed data, not vanilla)
----------------------------------------------
Only four ability classes carry `acAction` (`GetControlType & 1`, the test inside
`TAbility.CanActivate @0x5574EF40`): Spell Casting 0x34, Healing 0x2F, Dispel Magic 0x3C,
Construct 0x7D. Censusing BOTH item tables -- `Release/ITEMS.PFS` (83 records) and the mod's own
item library `User/Zig.ail` (325 records, and ⚠ ITEMS.PFS is NOT the shipped item list):

    Spell Casting 0x34   31 Zig.ail items (26 worn, 5 itUse), authored levels 1..5
    Healing      0x2F     5 Zig.ail items (Elixir of Life, Ring of Health, Ring of Life Power,
                          Robe of Life, The Ankh) -- bits only, no level sub-record
    Dispel 0x3C / Construct 0x7D   none

So before this patch a hero whose Spell Casting came only from an item could not cast at all.
⚠ Healing 0x2F is affected by the same gate and its five items are still untested in game --
the confirmation on 2026-08-28 covered Spell Casting only.

THE PATCH -- one site, one cave, both exes
------------------------------------------
`0x00409EF7`  `8B 08 FF 51 74`  ->  `E8 <rel32 to cave>`

The cave runs the ORIGINAL virtual first and only falls back when it says "no", so nothing that
already worked changes:

    push edx / push eax
    mov  ecx,[eax] / call [ecx+0x74]      ; the original TAbility.GetEnabled(ability, unit)
    pop  ecx (ability) / pop edx (unit)
    test al,al / jnz done                 ; already enabled -> unchanged
    mov  eax,edx                          ; eax = unit  (Self)
    mov  edx,[ecx+0x0C]                   ; edx = ability id
    mov  ecx,[eax] / call [ecx+0x148]     ; THero.GetAbilityEnabled -- self OR items OR inventory
    done: ret

`[ability+0xC]` is the id (proved by `GetEnabled` itself, which feeds it to `GetAbSet`, and by
`TSpellCastingAbility.Create @0x5576DBAC` writing 0x34 there). `[unit.vmt+0x148]` is
`TAbstractUnit.GetAbilityEnabled @0x5577F5E0`, overridden by `THero @0x5578827C` into the
self -> `THeroItems @0x55786674` -> `THeroInventory @0x55786154` chain. Virtual dispatch only, so
no AoWEPACK address is baked in and DPL rebasing cannot break it.

⚠ WHY THIS IS NOT A CHEAT, and the cross-feature coupling it creates
--------------------------------------------------------------------
`+0x74` does not uniformly mean "has the ability". For `THealingAbility @0x5576BF2C` and
`TDispelMagicAbility @0x5576CE58` it means "usable RIGHT NOW": both open with the same self-only
`GetAbSet` and then read a per-owner once-per-turn flag out of `TAbilityOwner.GetAbilityData`.
The `+0x148` item leg reaches those same overrides through `TAbilityOwner.GetAbEnabled
@0x5574FD68` with **the ITEM as the owner argument**, and an item's own data record is never
consumed -- which is precisely the infinite-Healing-from-an-item bug.

That hole is already closed, by `build_useitems.py` P1, which hooks both `GetEnabled` bodies
(0x5576BF40 -> cave 0x55815060, 0x5576CE6C -> 0x55815070), IsClass-tests the owner against TItem
and walks `item+4 -> container+4` to the carrier, so the flag is read off the HERO. This patch
therefore DEPENDS on that feature staying installed, and asserts it at apply time rather than
letting a future `build_useitems.py --undo` silently turn this into an exploit.

CAVE SPACE
----------
`0x0062D000`, inside `.hcol` (VA 0x612000, vsz 0x1C000, chars 0xE0000060 = EXEC|READ|WRITE).
⚠ `.hcol` is `build_herodlg_columns.py`'s section. That script allocates upward from 0x612000 and
its blob currently ends at 0x0062417B, leaving ~36 KB before this cave; its `add_section()` returns
early when `.hcol` exists, so re-applying it neither reallocates nor zeroes the section and this
cave survives. Ordering: if `.hcol` is ever REMOVED, re-apply `build_herodlg_columns.py` first,
then this. See that script's docstring for the `.syd` / SizeOfImage hazard around the same region.

LOCKSTEP
--------
Targets are the canonical mod exes `Ziggurat\AoWz.exe` and `Ziggurat\AoWzCompat.exe` (names from
`zigexe.py`). ⚠ Follow --apply with ⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.) `AoWzCompat.exe` is `AoWz.exe` with one byte different (file 0x3BB7C), so both get the
identical patch and both are verified before either is written.

Usage:
  python build_scripts/build_unitwin_ability.py           dry run + report current state
  python build_scripts/build_unitwin_ability.py --apply   patch both exes
  python build_scripts/build_unitwin_ability.py --undo    surgical revert (restore site, zero cave)
  python build_scripts/build_unitwin_ability.py --dis     disassemble the cave as it would be built
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                   # mod binary names (AoWz.exe / AoWzCompat.exe)

EXES = zigexe.EXES
DLL = "AoWEPACK.dpl"
SUFFIX = ".pre-unitwinability"
BACKUP_DIR = os.path.join(GAME, "backups")      # ⚠ backups/, never the game root -- rule 2026-09-03

SITE = 0x00409EF7
SITE_ORIG = bytes.fromhex("8b08ff5174")          # mov ecx,[eax] ; call [ecx+0x74]

CAVE_VA = 0x0062D000
CAVE_MAX = 0x40                                   # we use 27; keep the whole slot ours and zeroed
HCOL_VA, HCOL_SIZE = 0x00612000, 0x1C000
HERODLG_TOP = 0x0062417B                          # build_herodlg_columns.py's current high-water

# build_useitems.py P1 -- the two GetEnabled hooks this patch depends on (see the docstring).
USEITEMS_HOOKS = ((0x5576BF40, 0x55815060, "THealingAbility.GetEnabled"),
                  (0x5576CE6C, 0x55815070, "TDispelMagicAbility.GetEnabled"))

VMT_GETENABLED = 0x74          # TAbility  -- self-only
VMT_ABILITYENABLED = 0x148     # TAbstractUnit/THero -- item-aware
ABILITY_ID_OFF = 0x0C


# ------------------------------------------------------------------ tiny PE helper
class PE(object):
    def __init__(self, path):
        self.path = path
        self.d = bytearray(open(path, "rb").read())
        self.pe = struct.unpack_from("<I", self.d, 0x3C)[0]
        self.nsec = struct.unpack_from("<H", self.d, self.pe + 6)[0]
        self.opt = self.pe + 24
        self.sectbl = self.opt + struct.unpack_from("<H", self.d, self.pe + 20)[0]
        self.base = struct.unpack_from("<I", self.d, self.opt + 28)[0]

    def sections(self):
        for i in range(self.nsec):
            s = self.sectbl + 40 * i
            name = self.d[s:s + 8].rstrip(b"\0").decode("latin1")
            vsz, rva, rsz, ro = struct.unpack_from("<IIII", self.d, s + 8)
            chars = struct.unpack_from("<I", self.d, s + 36)[0]
            yield name, self.base + rva, vsz, ro, rsz, chars

    def off(self, va):
        """VA -> file offset. ⚠ per-section: there is no global delta."""
        for name, sva, vsz, ro, rsz, _c in self.sections():
            if sva <= va < sva + max(vsz, rsz):
                o = ro + (va - sva)
                assert o < ro + rsz, "%08X is past %s's raw data" % (va, name)
                return o
        raise AssertionError("VA %08X is in no section of %s" % (va, self.path))

    def read(self, va, n):
        o = self.off(va)
        return bytes(self.d[o:o + n])

    def write(self, va, blob):
        o = self.off(va)
        self.d[o:o + len(blob)] = blob

    def save(self):
        open(self.path, "wb").write(bytes(self.d))


def dll_off(d, va):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    sectbl = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
    for i in range(nsec):
        s = sectbl + 40 * i
        vsz, rva, rsz, ro = struct.unpack_from("<IIII", d, s + 8)
        if base + rva <= va < base + rva + max(vsz, rsz):
            return ro + (va - base - rva)
    raise AssertionError("VA %08X is in no section of the DLL" % va)


# ------------------------------------------------------------------ the cave
def build_cave():
    """Assemble with keystone when available; fall back to the reviewed byte string.

    The fallback is not laziness -- keystone is an optional dependency here and the encoding is
    fully determined. `--dis` disassembles whichever one was used, so the two cannot drift.
    """
    src = "\n".join([
        "push edx",                                    # save unit
        "push eax",                                    # save ability
        "mov ecx, dword ptr [eax]",
        "call dword ptr [ecx + 0x%X]" % VMT_GETENABLED,   # original GetEnabled(ability, unit)
        "pop ecx",                                     # ecx = ability
        "pop edx",                                     # edx = unit
        "test al, al",
        "jnz done",
        "mov eax, edx",                                # eax = unit (Self)
        "mov edx, dword ptr [ecx + 0x%X]" % ABILITY_ID_OFF,   # edx = ability id
        "mov ecx, dword ptr [eax]",
        "call dword ptr [ecx + 0x%X]" % VMT_ABILITYENABLED,   # item-aware GetAbilityEnabled
        "done:",
        "ret",
    ])
    # ⚠ Hand-encoded once and it was WRONG (jnz disp 0x0B for a 13-byte skip); the assert below
    # caught it. This is keystone's output, disassembled and checked -- never edit it by eye.
    expect = bytes.fromhex("52508b08ff5174595a84c0750d89d08b510c8b08ff9148010000c3")
    try:
        import keystone
        ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32)
        blob = bytes(ks.asm(src, CAVE_VA)[0])
    except Exception:                                             # noqa: BLE001
        return expect, src
    assert blob == expect, ("keystone produced %s, reviewed encoding is %s -- disassemble before "
                            "trusting either (--dis)" % (blob.hex(), expect.hex()))
    return blob, src


def disassemble(blob, va):
    try:
        import capstone
    except ImportError:
        return ["  (capstone not installed -- raw bytes: %s)" % blob.hex()]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    return ["  %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str)
            for i in md.disasm(blob, va)]


# ------------------------------------------------------------------ state
def hook_bytes(cave_va=CAVE_VA):
    return b"\xE8" + struct.pack("<i", cave_va - (SITE + 5))


def state_of(pe, blob):
    """-> 'vanilla' | 'applied' | 'foreign'"""
    site = pe.read(SITE, 5)
    cave = pe.read(CAVE_VA, len(blob))
    if site == SITE_ORIG:
        return "vanilla"
    if site == hook_bytes() and cave == blob:
        return "applied"
    return "foreign"


def check_useitems():
    """build_useitems.py P1 must own both GetEnabled hooks -- see the docstring."""
    path = os.path.join(GAME, DLL)
    d = open(path, "rb").read()
    missing = []
    for va, target, name in USEITEMS_HOOKS:
        raw = d[dll_off(d, va):dll_off(d, va) + 5]
        ok = raw[0] == 0xE9 and va + 5 + struct.unpack_from("<i", raw, 1)[0] == target
        if not ok:
            missing.append("%s @%08X: %s" % (name, va, raw.hex()))
    return missing


def check_hcol(pe):
    for name, sva, vsz, _ro, _rsz, chars in pe.sections():
        if name != ".hcol":
            continue
        assert (sva, vsz) == (HCOL_VA, HCOL_SIZE), \
            ".hcol moved (%08X/%X) -- re-derive the cave address" % (sva, vsz)
        assert chars & 0x20000000, ".hcol is not executable (chars %08X)" % chars
        assert CAVE_VA + CAVE_MAX <= sva + vsz, "cave overflows .hcol"
        assert CAVE_VA > HERODLG_TOP, "cave collides with build_herodlg_columns.py's blob"
        return
    raise AssertionError(
        ".hcol is missing from %s. It is build_herodlg_columns.py's section; apply that feature "
        "first, then this one (see the CAVE SPACE note in the docstring)." % pe.path)


# ------------------------------------------------------------------ main
def main(argv):
    apply_ = "--apply" in argv
    undo = "--undo" in argv
    dis = "--dis" in argv

    blob, src = build_cave()
    assert len(blob) <= CAVE_MAX, "cave is %d bytes, slot is %d" % (len(blob), CAVE_MAX)

    if dis:
        print("cave_unitwinability @%08X (%d bytes)" % (CAVE_VA, len(blob)))
        print("\n".join(disassemble(blob, CAVE_VA)))
        print("\nhook at %08X: %s  (was %s)" % (SITE, hook_bytes().hex(), SITE_ORIG.hex()))
        return 0

    pes, states = [], []
    for name in EXES:
        p = os.path.join(GAME, name)
        if not os.path.exists(p):
            print("MISSING: %s" % p)
            return 1
        pe = PE(p)
        check_hcol(pe)
        st = state_of(pe, blob)
        pes.append(pe)
        states.append(st)
        print("%-14s %-8s site %08X = %s" % (name, st, SITE, pe.read(SITE, 5).hex()))

    if "foreign" in states:
        print("\nABORT: the site holds bytes this script does not recognise. Neither vanilla "
              "(%s) nor ours. Someone else owns %08X -- resolve that before patching."
              % (SITE_ORIG.hex(), SITE))
        return 2
    if len(set(states)) != 1:
        print("\nABORT: the two exes disagree (%s). They must stay in lockstep." % states)
        return 2
    state = states[0]

    if undo:
        if state == "vanilla":
            print("\nalready vanilla -- nothing to undo")
            return 0
        for pe in pes:
            pe.write(SITE, SITE_ORIG)
            pe.write(CAVE_VA, b"\0" * len(blob))
            assert pe.read(CAVE_VA, CAVE_MAX) == b"\0" * CAVE_MAX, "cave slot not clean after undo"
            pe.save()
            print("reverted %s (site restored, cave zeroed -- no backup touched)"
                  % os.path.basename(pe.path))
        return 0

    if state == "applied":
        print("\nalready applied -- cave verified byte-for-byte in both exes")
        return 0

    missing = check_useitems()
    if missing:
        print("\nABORT: build_useitems.py P1 is not installed in %s:" % DLL)
        for m in missing:
            print("   %s" % m)
        print("Without it the item leg of +0x148 validates Healing/Dispel Magic's once-per-turn\n"
              "flag on the ITEM, and this patch would make them infinitely usable. Apply\n"
              "build_useitems.py first (see the WHY THIS IS NOT A CHEAT note above).")
        return 2

    print("\ncave_unitwinability @%08X (%d bytes)" % (CAVE_VA, len(blob)))
    print("\n".join(disassemble(blob, CAVE_VA)))
    print("\nhook  %08X: %s -> %s" % (SITE, SITE_ORIG.hex(), hook_bytes().hex()))

    if not apply_:
        print("\nDRY RUN -- pass --apply to write")
        return 0

    for pe in pes:
        assert pe.read(SITE, 5) == SITE_ORIG, "site changed under us"
        assert pe.read(CAVE_VA, CAVE_MAX) == b"\0" * CAVE_MAX, \
            "cave slot %08X is not zero -- someone else took it" % CAVE_VA
        # Snapshot only from a file PROVED unpatched. Control reaches here only with
        # state == "vanilla" ("applied" returned early, "foreign" aborted), and the two asserts
        # directly above re-prove it byte-for-byte. "No backup file exists yet" is NOT that
        # proof -- after the 2026-09-09 rename no AoWz.exe.pre-unitwinability can exist, so a
        # gate on the file's absence alone would snapshot a patched exe.
        os.makedirs(BACKUP_DIR, exist_ok=True)
        bak = os.path.join(BACKUP_DIR, os.path.basename(pe.path) + SUFFIX)
        if not os.path.exists(bak):
            shutil.copy2(pe.path, bak)
        pe.write(CAVE_VA, blob)
        pe.write(SITE, hook_bytes())
        pe.save()
        print("patched %s (backup %s)" % (os.path.basename(pe.path), os.path.basename(bak)))

    for pe in pes:
        again = PE(pe.path)
        assert state_of(again, blob) == "applied", "read-back failed for %s" % pe.path
    print("\nread-back verified in both exes.")
    print("IN-GAME TEST NEEDED -- this script cannot confirm anything:")
    print("  1. hero with NO innate Spell Casting, give them e.g. Wizard Ring (0x34 level 4);")
    print("     the ability was already listed -- now clicking it must open the spellbook.")
    print("  2. same hero WITHOUT the item: the ability must not be listed or usable.")
    print("  3. a hero who already had Spell Casting innately: unchanged behaviour.")
    print("  4. Healing from an item (Ring of Health): usable ONCE per turn, not repeatedly.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
