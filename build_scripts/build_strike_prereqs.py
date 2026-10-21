#!/usr/bin/env python
r"""
build_strike_prereqs.py -- which abilities depend on Strike (0x15).  AoWEPACK.dpl only.
Owner's rulings 2026-10-20:
    Monster Slaying 0x70, Parry 0x71   no longer need Strike: their ranged and defensive halves work
                                       without a melee attack (monsterslay.py; Parry takes 8 off the
                                       attacker's strike against the holder in
                                       TMeleeRound.CalculateStrikes, no Strike test on the holder).
    Round Attack 0x72                  needs Strike: a unit with Round Attack and no Strike breaks
                                       in game (TRoundAttackAbility's strikes read Strike's record,
                                       GetAbility(0x15)).

VANILLA (all three sites byte-identical to the root DLL)
    Fourteen abilities are TStrikeEnhancementAbility (VMT 0x5571E4D0), made by the strike factory
    0x5576727C from 0x557672B4: Fire/Cold/Lightning/Poison/Death/Holy/Magic Strike (0x0E-0x14),
    Charge 0x6F, Monster Slaying 0x70, Parry 0x71, Extra Strike 0x73, First Strike 0x74,
    Lifestealing 0x76, Entangle Strike 0x77.  The class adds two Strike rules to TAbility:
    CanExpand @0x5576723C (VMT +0xC4): TAbility.CanExpand (not held, mask matches) AND (the owner
        holds 0x15 OR the owner is a TItem).  The editor's Ability Editor lists and enables Add
        through it; the hero level-up dialog offers through it.
    TStrikeAbility.Remove @0x55766A64: removing Strike removes every held TStrikeEnhancementAbility
        (`call System.@IsClass` @0x55766AC0 picks them; the loop calls Remove until it fails).
    Round Attack is TRoundAttackAbility (VMT 0x5571FFA0, parent TTouchAbility, no subclasses, id
    0x72 only) and inherits plain TAbility.CanExpand, so nothing tied it to Strike.
    Granting asks neither rule: UpdateDefaultAbilities (rank sets, heroic options) copies the bits,
    and combat's GetAbilityEnabled is TAbility.GetEnabled (the owner holds the id).

THE CHANGE
    S1 0x5571E594  TStrikeEnhancementAbility VMT +0xC4  0x5576723C -> cave_ce: ids in FREE ->
                   TAbility.CanExpand 0x5574E8B8, anything else -> the class's own CanExpand.
    S2 0x55720064  TRoundAttackAbility VMT +0xC4  0x5574E8B8 -> 0x5576723C: Round Attack takes the
                   strike enhancements' vanilla test (TAbility's, then Strike or an item).
    R  0x55766AC0  TStrikeAbility.Remove's `call System.@IsClass` (rel32 retarget) -> cave_rmcls:
                   ids in FREE -> AL 0 (kept), Round Attack -> AL 1 (removed with Strike; its
                   Remove is TAbility.Remove, as the enhancements' is), else IsClass 0x557010C0.
    Nothing calls 0x5576723C or 0x5574E8B8 through these two slots' classes directly; both slots'
    .reloc entries are kept (the new values are inside the image).

Slot 0x558B2100-0x558B21FF, exclusive.  PIC: rel32 only.  No RNG.  Surgical --undo.
The editor half (on a medal or Heroic tab, a Strike-dependent ability counts Strike held by a
lower set) is build_deved_medalfilter.py; it asserts both VMTs.

    python build_scripts/build_strike_prereqs.py            dry run + state
    python build_scripts/build_strike_prereqs.py --apply
    python build_scripts/build_strike_prereqs.py --undo
    python build_scripts/build_strike_prereqs.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as AP
from aowepack_patch import asm, run

SLOT = (0x558B2100, 0x558B2200)
FREE = (0x70, 0x71)                     # Monster Slaying, Parry
ROUND_ATTACK = 0x72
AB_ID = 0x0C
SE_CLASSREF = 0x5571E490               # cell holding the TStrikeEnhancementAbility class
SE_VMT = 0x5571E4D0
RA_VMT = 0x5571FFA0                     # TRoundAttackAbility
SLOT_SE = SE_VMT + 0xC4                 # 0x5571E594
SLOT_RA = RA_VMT + 0xC4                 # 0x55720064
SE_CANEXPAND = 0x5576723C               # TStrikeEnhancementAbility.CanExpand
TABILITY_CANEXPAND = 0x5574E8B8
SITE_R = 0x55766AC0                     # TStrikeAbility.Remove: call System.@IsClass
ISCLASS = 0x557010C0
REMOVE_FN = (0x55766A64, 0x55766AF8)

d = open(AP.TARGET, "rb").read()
rd = lambda va: struct.unpack_from("<I", d, AP.va2off(d, va))[0]
cls = lambda vmt: d[AP.va2off(d, rd(vmt - 0x20)) + 1:][:d[AP.va2off(d, rd(vmt - 0x20))]]
assert rd(SE_CLASSREF) == SE_VMT, "TStrikeEnhancementAbility's VMT is not at %08X" % SE_VMT
for vmt, name in ((SE_VMT, b"TStrikeEnhancementAbility"), (RA_VMT, b"TRoundAttackAbility")):
    assert rd(vmt - 0x40) == vmt and cls(vmt) == name, "%s's VMT is not at %08X" % (name, vmt)
assert d[AP.va2off(d, SITE_R) - 6:AP.va2off(d, SITE_R)] == b"\x8b\x15" + \
    struct.pack("<I", SE_CLASSREF), "0x55766ABA is no longer `mov edx, [TStrikeEnhancementAbility]`"


def build_ce(va):
    return asm(f"""
        cmp  dword ptr [eax + {AB_ID:#x}], {FREE[0]:#x}
        je   {TABILITY_CANEXPAND:#x}
        cmp  dword ptr [eax + {AB_ID:#x}], {FREE[1]:#x}
        je   {TABILITY_CANEXPAND:#x}
        jmp  {SE_CANEXPAND:#x}
    """, va)


def build_rmcls(va):
    return asm(f"""
        test eax, eax
        je   isclass
        mov  ecx, dword ptr [eax + {AB_ID:#x}]
        cmp  ecx, {ROUND_ATTACK:#x}
        je   enh
        cmp  ecx, {FREE[0]:#x}
        je   kept
        cmp  ecx, {FREE[1]:#x}
        jne  isclass
    kept:
        xor  eax, eax
        ret
    enh:
        mov  al, 1
        ret
    isclass:
        jmp  {ISCLASS:#x}
    """, va)


def layout():
    out, va = [], SLOT[0]
    for name, fn in (("cave_ce", build_ce), ("cave_rmcls", build_rmcls)):
        blob = fn(va)
        out.append((name, va, blob))
        va = (va + len(blob) + 15) & ~15
    return out


caves = layout()
CAVE_CE, CAVE_RMCLS = (v for _n, v, _b in caves)
call = lambda src, dst: b"\xe8" + struct.pack("<i", dst - (src + 5))
hooks = [(SLOT_SE, struct.pack("<I", SE_CANEXPAND), struct.pack("<I", CAVE_CE)),
         (SLOT_RA, struct.pack("<I", TABILITY_CANEXPAND), struct.pack("<I", SE_CANEXPAND)),
         (SITE_R, call(SITE_R, ISCLASS), call(SITE_R, CAVE_RMCLS))]

if __name__ == "__main__":
    run("build_strike_prereqs", hooks, caves, SLOT,
        [(SITE_R, SITE_R + 5, REMOVE_FN[0], REMOVE_FN[1])], reloc_ok=(SLOT_SE, SLOT_RA))
