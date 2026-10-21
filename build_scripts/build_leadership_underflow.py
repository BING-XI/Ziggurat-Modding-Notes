#!/usr/bin/env python
r"""
build_leadership_underflow.py -- a multi-level ability can no longer be removed below level 0, and
a Leadership level beyond the cap read from a save is reset to 0.  AoWEPACK.dpl only.  2026-10-20,
from the owner's report: units stacked with certain heroes showed 40 Attack / 0 Defense.

THE DEFECT (vanilla: TMultiLevelAbility.Remove is byte-identical to the root DLL)
    TMultiLevelAbility.Remove @0x557653E0 (VMT +0xD4): record level 1 -> delete the record; any other
    level -> `dec byte [rec+0x0C]`.  Level 0 is not special-cased, so it wraps to 255.
    A hero standing in another leader's aura holds a Leadership record with own level 0 and the
    borrowed level set (TLeadershipAbility.SetExternalSource creates it and sets the bit).  In the
    hero level-up dialog that Leadership is listed, it is not "inherent", so
    THeroUpgradeDlg.RemoveBtnClick (AoWz.exe 0x00447134) skips its level comparison and calls
    RemoveAbility -> Remove: own 0 -> 255.  The card still shows the received level, so repeated
    clicks go on down (254, 252, 250 in the owner's PBEM files).  Done grants the edited hero
    through UpdateDefaultAbilities, which copies the record because 254 reads as higher than 0.
    The aura pass then takes 254 as the stack's best level, every other unit borrows 254, and the
    bonus getters index build_leadership4.py's 5-entry ladders (0x5580F0C0 / 0x5580F0C8) with it,
    reading code bytes: a huge attack bonus and a wrapped-negative defense, clamped to 40 / 0.
    Units recover when moved out of the stack (their borrowed level is recomputed).

THE FIX
    R  0x55765419  `dec byte [esi+0xc] / jmp 0x5576542E` (5 B) -> jmp cave_remove: level 0 ->
                   refuse (EBX = 0, nothing changed), else the original decrement.  Every caller.
    S  0x55721F34  TLeadershipAbilityData VMT +0x18 ReadWrite 0x55766130 -> cave_leadrw: the
                   original, then on a true load (StorageMode & 0x45 == 1, the engine's own test;
                   the translation pass and copies streamed for Assign are not loads) own [+0x0C]
                   and borrowed [+0x10] above CAP become 0.  Heals the heroes already corrupted in
                   live saves the first time an updated client loads them.  Its .reloc is kept.
    CAP is build_leadership4.py's Leadership cap, read from its imm32 at 0x5576618A (asserted).

Slot 0x558B2000-0x558B20FF, exclusive.  PIC: rel32 only.  No RNG; deterministic, so every peer on
this build computes the same.  Surgical --undo.  Interior and .reloc audits run every time.

    python build_scripts/build_leadership_underflow.py            dry run + state
    python build_scripts/build_leadership_underflow.py --apply
    python build_scripts/build_leadership_underflow.py --undo
    python build_scripts/build_leadership_underflow.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as AP
from aowepack_patch import asm, run

SLOT = (0x558B2000, 0x558B2100)
REMOVE_FN = (0x557653E0, 0x55765435)
SITE_R = 0x55765419
ORIG_R = bytes.fromhex("fe4e0ceb10")
RESUME = 0x5576542E                     # Remove's shared exit: mov eax, ebx / pops / ret
SLOT_S = 0x55721F34                     # TLeadershipAbilityData VMT +0x18
ORIG_S = 0x55766130                     # TLeadershipAbilityData.ReadWrite
CAP_IMM = 0x5576618A                    # build_leadership4.py: TLeadershipAbility.Create's cap imm32
LOAD_MASK = 0x45

d = open(AP.TARGET, "rb").read()
CAP = struct.unpack_from("<I", d, AP.va2off(d, CAP_IMM))[0]
assert d[AP.va2off(d, CAP_IMM) - 3:AP.va2off(d, CAP_IMM)] == b"\xc7\x46\x28", \
    "the Leadership cap is no longer `mov dword ptr [esi+0x28], imm32` at 0x55766187"
assert 1 <= CAP <= 9, "implausible Leadership cap %d" % CAP


def build_remove(va):
    return asm(f"""
        cmp  byte ptr [esi + 0xc], 0
        je   refuse
        dec  byte ptr [esi + 0xc]
        jmp  {RESUME:#x}
    refuse:
        xor  ebx, ebx
        jmp  {RESUME:#x}
    """, va)


def build_leadrw(va):
    return asm(f"""
        push ebx
        push esi
        mov  ebx, eax
        mov  esi, edx
        call {ORIG_S:#x}
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx]
        and  al, {LOAD_MASK:#x}
        cmp  al, 1
        jne  out
        cmp  byte ptr [ebx + 0xc], {CAP}
        jbe  own_ok
        mov  byte ptr [ebx + 0xc], 0
    own_ok:
        cmp  byte ptr [ebx + 0x10], {CAP}
        jbe  out
        mov  byte ptr [ebx + 0x10], 0
    out:
        pop  esi
        pop  ebx
        ret
    """, va)


def layout():
    out, va = [], SLOT[0]
    for name, fn in (("cave_remove", build_remove), ("cave_leadrw", build_leadrw)):
        blob = fn(va)
        out.append((name, va, blob))
        va = (va + len(blob) + 15) & ~15
    return out


caves = layout()
CAVE_REMOVE, CAVE_LEADRW = (v for _n, v, _b in caves)
hooks = [(SITE_R, ORIG_R, b"\xe9" + struct.pack("<i", CAVE_REMOVE - (SITE_R + 5))),
         (SLOT_S, struct.pack("<I", ORIG_S), struct.pack("<I", CAVE_LEADRW))]

if __name__ == "__main__":
    print("Leadership cap read live: %d" % CAP)
    run("build_leadership_underflow", hooks, caves, SLOT,
        [(SITE_R, SITE_R + len(ORIG_R), REMOVE_FN[0], REMOVE_FN[1])], reloc_ok=(SLOT_S,))
