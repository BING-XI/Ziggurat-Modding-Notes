#!/usr/bin/env python3
r"""Re-arm an ITEM-granted Healing on new turn, so it stops sticking at "Healing (used)".

STATUS: CONFIRMED WORKING in game (2026-08-28). Last of the four patches in the chain below.

THE BUG (vanilla) -- the fourth and last gate in the item-granted-ability chain
------------------------------------------------------------------------------
Using an item-granted activatable ability on the strategic map crosses four separate self-only
checks, each of which fails silently, so each was only visible once the previous one was fixed:

  1. `TUnitWindow.UseAbility @0x409EF7`  (AoW.exe) ...... clicking the ability did nothing
                                                          -> build_unitwin_ability.py
  2. `cave_tiergate` in `THero.CanCastSpell`  (ours) .... spellbook opened, spells would not cast
                                                          -> build_spellcast_multiturn.py M2 v2
  3. `THealingTE.Execute @0x5576C773` .................. the order was issued and nothing happened
                                                          -> build_abilityte_itemgrant.py
  4. **the per-turn re-arm, HERE** ..................... it healed once, then stuck at "(used)"

`TAbilityOwner.MsgProc @0x5574FF10` turns the new-turn message (`0x20020002`) into
`TAbilityOwner.TriggerNewTurn @0x5574FE14`, which enumerates the owner's abilities like this:

    5574FE22  call [owner.vmt+0x54]    ; GetAbCount    -- SELF-ONLY width
              loop id = 0 .. count-1
    5574FE35  call [owner.vmt+0x4C]    ; GetAbSet(id)  -- SELF-ONLY bit
    5574FE3A  je   next                ;   no bit -> the ability is skipped entirely
    5574FE49  call TAbilityControl.GetAbility(id)
              ... ability.NewTurn(owner, player)  ->  SetEnabled(owner, 1)

The hero holds the *data record* -- `THealingAbility.SetEnabled @0x5576BEEC` created it on first
use -- but not the *bit*, which lives on the item. So the hero's Healing is never visited, the
re-arm never runs, and `[record+0x0C]` stays 0 for the rest of the game.

WHY NOT WIDEN THE ENUMERATION
-----------------------------
`+0x14C GetAbilitySet` / `+0x158 GetAbilityCount` are the item-aware pair, but they are slots on
the `TAbstractUnit` hierarchy and `TriggerNewTurn` runs on **every** `TAbilityOwner`, `TItem`
included -- which has no such slot. Widening either dispatch would send an item through whatever
happens to sit at that offset in `TItem`'s VMT. The owner's DATA-RECORD CHAIN, by contrast, is a
plain `TAbilityOwner` field and is valid for every owner.

THE PATCH -- drive the re-arm off the record chain instead of the bitset
-----------------------------------------------------------------------
All three facts this relies on were read out of the live DLL, not assumed:

    [owner+0x10]              head of the ability-data list   (TAbilityOwner.AddAbilityData
                                @0x5574F278 pushes onto it; GetAbilityData @0x5574F1C4 walks it)
    [record+0x08]             next record
    record.vmt[+0x4C]         GetAbilityID  (THealingAbilityData's @0x5576BE10 is `mov eax,0x2F`)
    [record+0x0C]             the once-per-turn flag  (THealingAbility.SetEnabled writes it at
                                0x5576BF22: `mov [ebx+0xC], al`)

so re-arming is just `mov byte [record+0x0C], 1` on the owner's own record -- **no ability object,
no `TAbilityControl.GetAbility`, and therefore no absolute global**. The cave is entirely
register-relative and the hook is `E9 rel32`, so it is position-independent as every AoWEPACK cave
must be. Verified: no `.reloc` entry covers the five displaced bytes or the cave.

Scope: **Healing `0x2F` only**, per the author's ruling 2026-08-28 -- it is the only once-per-turn
ability that any item actually grants. `TDispelMagicAbility` has the identical machinery (it is the
other of the only two classes with a `SetEnabled`), but no item in `Release/ITEMS.PFS` or
`User/Zig.ail` grants `0x3C`, so it is deliberately left out; if that ever changes, the constant
`HEAL_ID` below is the one-byte edit.

Idempotent for free: the vanilla loop also sets the flag to 1 for a hero who owns Healing
innately, so a hero with both paths just gets it set twice. Nothing is skipped and nothing is
double-consumed -- the pass only ever *arms*, never clears.

Usage:
  python build_scripts/build_healing_rearm.py            dry run + report state
  python build_scripts/build_healing_rearm.py --apply    patch AoWEPACK.dpl
  python build_scripts/build_healing_rearm.py --undo     surgical revert (site + zero cave)
  python build_scripts/build_healing_rearm.py --dis      disassemble the cave
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DPL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DPL) + ".pre-healingrearm")
IMAGE_BASE = 0x55700000

HOOK = 0x5574FE14                                  # TAbilityOwner.TriggerNewTurn, first instruction
HOOK_ORIG = bytes.fromhex("5356575551")            # push ebx/esi/edi/ebp/ecx
RESUME = HOOK + len(HOOK_ORIG)                     # 0x5574FE19: mov byte [esp], dl

CAVE_VA = 0x55818260                               # after build_abilityte_itemgrant.py's cave
CAVE_MAX = 0x40
NEIGHBOUR_END = 0x5581825B                         # that cave ends here

HEAL_ID = 0x2F
REC_NEXT, REC_FLAG, OWNER_LIST = 0x08, 0x0C, 0x10
VMT_GETABILITYID = 0x4C


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


CAVE_SRC = """
    push ebx
    push esi
    push edi
    push ebp
    push ecx
    push eax
    push edx
    mov esi, dword ptr [eax + 0x%X]
_next:
    test esi, esi
    jz _done
    push esi
    mov eax, esi
    mov ecx, dword ptr [eax]
    call dword ptr [ecx + 0x%X]
    pop esi
    cmp eax, 0x%X
    jne _skip
    mov byte ptr [esi + 0x%X], 1
_skip:
    mov esi, dword ptr [esi + 0x%X]
    jmp _next
_done:
    pop edx
    pop eax
    jmp 0x%X
""" % (OWNER_LIST, VMT_GETABILITYID, HEAL_ID, REC_FLAG, REC_NEXT, RESUME)


def build_cave():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    blob = bytes(ks.asm(CAVE_SRC, CAVE_VA)[0])
    # The five replicated pushes must be byte-identical to what we displaced, or the cave is
    # not a faithful prologue.
    assert blob[:5] == HOOK_ORIG, "replicated prologue %s != displaced %s" % (
        blob[:5].hex(), HOOK_ORIG.hex())
    return blob


def disassemble(blob, va):
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    return ["  %08X  %-22s %s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str)
            for i in md.disasm(blob, va)]


def hook_bytes():
    return b"\xE9" + struct.pack("<i", CAVE_VA - (HOOK + 5))


def main(argv):
    apply_ = "--apply" in argv
    undo = "--undo" in argv
    blob = build_cave()
    assert len(blob) <= CAVE_MAX, "cave %d > slot %d" % (len(blob), CAVE_MAX)
    assert CAVE_VA >= NEIGHBOUR_END, "cave overlaps build_abilityte_itemgrant.py's cave"

    if "--dis" in argv:
        print("cave_healrearm @%08X (%d bytes)" % (CAVE_VA, len(blob)))
        print("\n".join(disassemble(blob, CAVE_VA)))
        print("\nhook %08X: %s -> %s   (resumes at %08X)"
              % (HOOK, HOOK_ORIG.hex(), hook_bytes().hex(), RESUME))
        return 0

    d = bytearray(open(DPL, "rb").read())

    def rd(va, n):
        o = va2off(d, va)
        return bytes(d[o:o + n])

    def wr(va, b):
        o = va2off(d, va)
        d[o:o + len(b)] = b

    cur = rd(HOOK, 5)
    cave_now = rd(CAVE_VA, len(blob))
    if cur == HOOK_ORIG:
        state = "vanilla"
    elif cur == hook_bytes() and cave_now == blob:
        state = "applied"
    else:
        state = "foreign"
    print("%08X  %-8s %s   TAbilityOwner.TriggerNewTurn" % (HOOK, state, cur.hex()))
    print("cave      %08X  %s" % (CAVE_VA, "installed" if cave_now == blob else
                                  ("zero" if cave_now == b"\0" * len(blob) else "FOREIGN")))

    if state == "foreign":
        print("\nABORT: the site holds bytes this script does not recognise -- someone else owns "
              "%08X. TriggerNewTurn is a hot path; resolve that before patching." % HOOK)
        return 2

    if undo:
        if state == "vanilla":
            print("\nalready vanilla -- nothing to undo")
            return 0
        wr(HOOK, HOOK_ORIG)
        wr(CAVE_VA, b"\0" * CAVE_MAX)
        open(DPL, "wb").write(bytes(d))
        print("\nreverted: prologue restored, cave zeroed, no backup touched")
        return 0

    if state == "applied":
        print("\nalready applied -- hook and cave verified byte-for-byte")
        return 0

    print("\ncave_healrearm @%08X (%d bytes)" % (CAVE_VA, len(blob)))
    print("\n".join(disassemble(blob, CAVE_VA)))
    print("\nhook %08X: %s -> %s   (resumes at %08X)"
          % (HOOK, HOOK_ORIG.hex(), hook_bytes().hex(), RESUME))
    if not apply_:
        print("\nDRY RUN -- pass --apply to write")
        return 0

    assert rd(CAVE_VA, CAVE_MAX) == b"\0" * CAVE_MAX, "cave slot is not zero"
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DPL, BACKUP)
        print("backup written: %s" % os.path.basename(BACKUP))
    wr(CAVE_VA, blob)
    wr(HOOK, hook_bytes())
    open(DPL, "wb").write(bytes(d))

    d2 = bytearray(open(DPL, "rb").read())
    assert bytes(d2[va2off(d2, HOOK):va2off(d2, HOOK) + 5]) == hook_bytes(), "read-back failed"
    print("patched %08X + cave; read-back verified." % HOOK)
    print("\nIN-GAME TEST NEEDED -- this script cannot confirm anything:")
    print("  1. hero with item-granted Healing: heal, end turn, heal again next turn -> must work.")
    print("  2. same turn, second heal -> must still be refused (the flag must ARM, not disable).")
    print("  3. hero with INNATE Healing: unchanged, still once per turn.")
    print("  4. ⚠ TriggerNewTurn runs for every ability owner every turn -- watch the first few")
    print("     turns for any slowdown or instability, not just the healing itself.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
