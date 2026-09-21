#!/usr/bin/env python3
r"""Let an item-granted Healing / Dispel Magic order actually APPLY when it executes.

STATUS: CONFIRMED WORKING in game (2026-08-28), together with build_healing_rearm.py -- without
that one the heal fires once and then sticks at "(used)" forever.

THE BUG (vanilla) -- the third gate in the same chain
----------------------------------------------------
Using an item-granted activatable ability on the strategic map passes through THREE self-only
`[ability.vmt+0x74] TAbility.GetEnabled` gates, and each one had to be found separately because
each fails silently and only the next symptom is visible:

  1. `TUnitWindow.UseAbility @0x409EF7`  (AoW.exe) ...... clicking the ability did nothing
                                                          -> build_unitwin_ability.py
  2. `cave_tiergate` in `THero.CanCastSpell`  (ours) .... spellbook opened, spells would not cast
                                                          -> build_spellcast_multiturn.py M2 v2
  3. **the turn event's own re-check, HERE** ............ the order is issued and nothing happens

Stage 3 is a *turn event*: `Activate` only puts the game into target-selection, and the real work
runs later in the TE's `Execute`, which re-resolves the ability by id and re-tests it against the
caster before applying:

    ; AoWE.THealingTE.Execute
    5576C763  mov edx, 0x2F                     ; Healing
    5576C768  call TAbilityControl.GetAbility   ; ebp = the THealingAbility
    5576C76F  mov edx, esi                      ; esi = the CASTER unit
    5576C771  mov eax, ebp
    5576C773  mov ecx,[eax] / call [ecx+0x74]   <-- SITE 1, self-only
    5576C77A  je  0x5576C859                    ; -> silent bail, no heal, no message
    5576C786  call THealingAbility.SetEnabled   ; consume the once-per-turn flag (on the caster)
    5576C78F  call THealingAbility.HealUnit     ; the actual heal

`THealingAbility.GetEnabled @0x5576BF2C` opens with `owner.GetAbSet(id)` -- `[owner.vmt+0x4C]`,
the self-only bitset -- so a hero whose Healing comes from an item fails it and the order
evaporates between issuing and applying.

`AoWE.TDispelMagicAbilityTE.Execute @0x5576D7FC` is the byte-identical twin (SITE 2). It is
**latent today** -- no item in `Release/ITEMS.PFS` or `User/Zig.ail` grants Dispel Magic 0x3C --
and is patched here only because it is the same five bytes with the same register contract, so
leaving it would guarantee re-deriving this whole chain the day such an item is authored.

WHY NOT FIX `THealingAbility.GetEnabled` ITSELF
----------------------------------------------
Tempting -- one edit instead of two -- and wrong. `GetEnabled` is called with an **item** as the
owner too (that is how `THeroItems.GetAbilityEnabled` -> `TAbilityOwner.GetAbEnabled @0x5574FD68`
re-checks the ability against the item). `+0x14C GetAbilitySet` is a slot on the
`TAbstractUnit` hierarchy; `TItem` is a `TAbilityOwner` and has no such slot, so widening the test
inside `GetEnabled` would dispatch through whatever happens to sit at `+0x14C` in `TItem`'s VMT.
Patch the CALL SITES, where the receiver is known to be a unit.

THE PATCH -- two sites, one shared cave
---------------------------------------
Both sites are `8B 08 FF 51 74` with EAX = the ability and EDX = the unit, i.e. the identical
contract `build_unitwin_ability.py` already handles in the exe, so the cave body is the same:

    push edx / push eax
    mov  ecx,[eax] / call [ecx+0x74]      ; the ORIGINAL virtual, unchanged behaviour first
    pop  ecx (ability) / pop edx (unit)
    test al,al / jnz done                 ; already enabled -> nothing changes
    mov  eax,edx                          ; eax = unit (Self)
    mov  edx,[ecx+0x0C]                   ; edx = ability id
    mov  ecx,[eax] / call [ecx+0x148]     ; item-aware GetAbilityEnabled
    done: ret

⚠ POSITION-INDEPENDENT, as every AoWEPACK cave must be: the hook is `E8 rel32` and the cave body
is register-relative only -- no absolute global is referenced, so DPL rebasing cannot break it.
Verified: no `.reloc` entry covers either five-byte site or the cave.

⚠ THE ONCE-PER-TURN FLAG STILL BINDS. The `+0x148` item leg re-enters the same
`THealingAbility.GetEnabled` with the ITEM as owner, and an item's own data record is never
consumed -- that is the infinite-Healing bug. `build_useitems.py` P1 closes it by redirecting an
item owner to its carrier (hooks at 0x5576BF40 -> 0x55815060 and 0x5576CE6C -> 0x55815070), so the
flag is read off the HERO, and `THealingTE.Execute` then writes it back to the hero via
`SetEnabled(caster)`. This script ABORTS if those hooks are absent rather than shipping an
infinite heal.

CAVE SPACE
----------
`0x55818240`, 28 bytes, in the CODE zero run that starts after `build_morale_hero_atk.py`'s cave
(which occupies 0x55818200..0x5581822F). Verified zero for 0x3D0 bytes from 0x55818230; a 16-byte
gap is left after the neighbour deliberately.

Usage:
  python build_scripts/build_abilityte_itemgrant.py           dry run + report state
  python build_scripts/build_abilityte_itemgrant.py --apply   patch AoWEPACK.dpl
  python build_scripts/build_abilityte_itemgrant.py --undo    surgical revert (sites + zero cave)
  python build_scripts/build_abilityte_itemgrant.py --dis     disassemble the cave
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DPL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DPL) + ".pre-abilityte")
IMAGE_BASE = 0x55700000

SITE_ORIG = bytes.fromhex("8b08ff5174")            # mov ecx,[eax] ; call [ecx+0x74]
SITES = ((0x5576C773, "THealingTE.Execute (Healing 0x2F -- LIVE: 5 Zig.ail items grant it)"),
         (0x5576D7FC, "TDispelMagicAbilityTE.Execute (Dispel 0x3C -- latent: no item grants it)"))

CAVE_VA = 0x55818240
CAVE_MAX = 0x30
NEIGHBOUR_END = 0x55818230                         # build_morale_hero_atk.py's cave ends here

USEITEMS_HOOKS = ((0x5576BF40, 0x55815060, "THealingAbility.GetEnabled"),
                  (0x5576CE6C, 0x55815070, "TDispelMagicAbility.GetEnabled"))

VMT_GETENABLED = 0x74
VMT_ABILITYENABLED = 0x148
ABILITY_ID_OFF = 0x0C


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    tbl = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    for i in range(nsec):
        s = tbl + 40 * i
        name = bytes(d[s:s + 8]).rstrip(b"\0").decode("latin1")
        vsz, rva, rsz, ro = struct.unpack_from("<IIII", d, s + 8)
        yield name, rva, vsz, ro, rsz


def va2off(d, va):
    rva = va - IMAGE_BASE
    for name, srva, vsz, ro, rsz in sections(d):
        if srva <= rva < srva + max(vsz, rsz):
            off = ro + (rva - srva)
            assert off < ro + rsz, "%08X past %s's raw data" % (va, name)
            return off
    raise AssertionError("VA %08X in no section" % va)


def build_cave():
    src = "\n".join([
        "push edx", "push eax",
        "mov ecx, dword ptr [eax]",
        "call dword ptr [ecx + 0x%X]" % VMT_GETENABLED,
        "pop ecx", "pop edx",
        "test al, al", "jnz done",
        "mov eax, edx",
        "mov edx, dword ptr [ecx + 0x%X]" % ABILITY_ID_OFF,
        "mov ecx, dword ptr [eax]",
        "call dword ptr [ecx + 0x%X]" % VMT_ABILITYENABLED,
        "done:", "ret",
    ])
    # Same encoding build_unitwin_ability.py uses; keystone is authoritative, this is the check.
    expect = bytes.fromhex("52508b08ff5174595a84c0750d89d08b510c8b08ff9148010000c3")
    try:
        import keystone
        ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32)
        blob = bytes(ks.asm(src, CAVE_VA)[0])
    except ImportError:
        return expect
    assert blob == expect, "keystone %s != reviewed %s -- run --dis" % (blob.hex(), expect.hex())
    return blob


def disassemble(blob, va):
    try:
        import capstone
    except ImportError:
        return ["  (capstone not installed -- %s)" % blob.hex()]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    return ["  %08X  %-22s %s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str)
            for i in md.disasm(blob, va)]


def hook_for(site):
    return b"\xE8" + struct.pack("<i", CAVE_VA - (site + 5))


def main(argv):
    apply_ = "--apply" in argv
    undo = "--undo" in argv
    blob = build_cave()
    assert len(blob) <= CAVE_MAX, "cave %d > slot %d" % (len(blob), CAVE_MAX)
    assert CAVE_VA >= NEIGHBOUR_END, "cave overlaps build_morale_hero_atk.py's cave"

    if "--dis" in argv:
        print("cave_abilityte @%08X (%d bytes)" % (CAVE_VA, len(blob)))
        print("\n".join(disassemble(blob, CAVE_VA)))
        for va, desc in SITES:
            print("hook %08X: %s -> %s   %s"
                  % (va, SITE_ORIG.hex(), hook_for(va).hex(), desc))
        return 0

    d = bytearray(open(DPL, "rb").read())

    def rd(va, n):
        o = va2off(d, va)
        return bytes(d[o:o + n])

    def wr(va, blob_):
        o = va2off(d, va)
        d[o:o + len(blob_)] = blob_

    states = []
    for va, desc in SITES:
        cur = rd(va, 5)
        st = "vanilla" if cur == SITE_ORIG else ("applied" if cur == hook_for(va) else "foreign")
        states.append(st)
        print("%08X  %-8s %s   %s" % (va, st, cur.hex(), desc))
    cave_now = rd(CAVE_VA, len(blob))
    print("cave      %08X  %s" % (CAVE_VA, "installed" if cave_now == blob else
                                  ("zero" if cave_now == b"\0" * len(blob) else "FOREIGN")))

    if "foreign" in states:
        print("\nABORT: a site holds bytes this script does not recognise -- someone else owns it.")
        return 2
    if len(set(states)) != 1:
        print("\nABORT: the two sites disagree (%s); refusing a half-applied state." % states)
        return 2
    state = states[0]

    if undo:
        if state == "vanilla":
            print("\nalready vanilla -- nothing to undo")
            return 0
        for va, _desc in SITES:
            wr(va, SITE_ORIG)
        wr(CAVE_VA, b"\0" * CAVE_MAX)
        open(DPL, "wb").write(bytes(d))
        print("\nreverted: both sites restored, cave zeroed, no backup touched")
        return 0

    if state == "applied" and cave_now == blob:
        print("\nalready applied -- both sites and the cave verified byte-for-byte")
        return 0

    missing = []
    for va, target, name in USEITEMS_HOOKS:
        raw = rd(va, 5)
        if not (raw[0] == 0xE9 and va + 5 + struct.unpack_from("<i", raw, 1)[0] == target):
            missing.append("%s @%08X: %s" % (name, va, raw.hex()))
    if missing:
        print("\nABORT: build_useitems.py P1 is not installed:")
        for m in missing:
            print("   %s" % m)
        print("Its owner-redirect is what makes the +0x148 fallback read the once-per-turn flag\n"
              "off the HERO instead of the item. Without it this patch is an infinite heal.")
        return 2

    print("\ncave_abilityte @%08X (%d bytes)" % (CAVE_VA, len(blob)))
    print("\n".join(disassemble(blob, CAVE_VA)))
    if not apply_:
        print("\nDRY RUN -- pass --apply to write")
        return 0

    assert rd(CAVE_VA, CAVE_MAX) == b"\0" * CAVE_MAX, "cave slot is not zero"
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DPL, BACKUP)
        print("backup written: %s" % os.path.basename(BACKUP))
    wr(CAVE_VA, blob)
    for va, desc in SITES:
        assert rd(va, 5) == SITE_ORIG, "site %08X changed under us" % va
        wr(va, hook_for(va))
        print("patched %08X  %s" % (va, desc))
    open(DPL, "wb").write(bytes(d))

    d2 = bytearray(open(DPL, "rb").read())
    for va, _desc in SITES:
        o = va2off(d2, va)
        assert bytes(d2[o:o + 5]) == hook_for(va), "read-back failed at %08X" % va
    print("\nread-back verified.")
    print("IN-GAME TEST NEEDED -- this script cannot confirm anything:")
    print("  1. hero with NO innate Healing, wearing Ring of Health / Ring of Life Power /")
    print("     Robe of Life: issue a heal order on a damaged unit -- it must actually heal.")
    print("  2. the SAME hero, same turn, a second heal: must be refused (once per turn).")
    print("  3. next turn: the heal must work again.")
    print("  4. a hero with innate Healing: unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
