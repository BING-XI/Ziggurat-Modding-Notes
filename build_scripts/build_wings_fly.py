#!/usr/bin/env python
r"""
build_wings_fly.py -- Spectral Wings (enchantment 0x97, build_airwater_ench.py) gets the Flying
ability's "fly up / fly down" click (build_fly_levels.py; owner, 2026-10-27).  AoWEPACK.dpl.

The flight itself already counts a winged unit: fly_check asks GetAbilityEnabled(1) (VMT +0x148),
which build_airwater_ench.py's query widening answers for 0x97.  What was missing is the click: the
unit window offers Flying's row because TMovementAbility's GetControlType / Activate slots point at
build_fly_levels.py's cave_gct / cave_act, which act for ability id 1 only.  A winged unit's row is
the enchantment, a TWindWalkingEnchantment, whose two slots are TAbility's own -- the very functions
those caves fall back to.

    +0x98  0x557B8F38  TWindWalkingEnchantment GetControlType (0x5574E730) -> cave_wgct
    +0xB4  0x557B8F54  TWindWalkingEnchantment Activate       (0x5574EF68) -> cave_wact
    (.reloc kept: each new value is another address in this image)
Each cave: id 0x97 -> jump into build_fly_levels.py's cave past its `cmp [eax+0xC],1 / jne` (10 B);
anything else (Wind Walking 0xA5, Mistform 0x54) -> TAbility's function, as before.

RNG: none.  Slot 0x558C6000-0x558C60FF, exclusive.  PIC (rel32 only).  Surgical --undo.
FORWARD HAZARD: the two jump targets are build_fly_levels.py's cave_gct + 10 and cave_act + 10, read
from its own layout at build time and checked against the live bytes: re-laying out that script
moves them -- undo this script first, re-apply it after.

    python build_scripts/build_wings_fly.py            dry run + state
    python build_scripts/build_wings_fly.py --apply
    python build_scripts/build_wings_fly.py --undo
    python build_scripts/build_wings_fly.py --dis
"""
import importlib.util, os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("_fly", os.path.join(HERE, "build_fly_levels.py"))
FL = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FL)

WINGS = 0x97
SLOT = (0x558C6000, 0x558C6100)
WWE_VMT = 0x557B8EA0
S_GCT, S_ACT = WWE_VMT + 0x98, WWE_VMT + 0xB4
GCT_ORIG, ACT_ORIG = FL.GCT_ORIG, FL.ACT_ORIG
PREFIX = 10                                         # cmp dword [eax+0xC],1 (4) + jne rel32 (6)
GCT_BODY, ACT_BODY = FL.ADDR["cave_gct"] + PREFIX, FL.ADDR["cave_act"] + PREFIX

CAVE_G, CAVE_A = SLOT[0], SLOT[0] + 0x20
BLOB_G = asm(f"""
    cmp  dword ptr [eax + 0xc], {WINGS:#x}
    jne  {GCT_ORIG:#x}
    jmp  {GCT_BODY:#x}
""", CAVE_G)
BLOB_A = asm(f"""
    cmp  dword ptr [eax + 0xc], {WINGS:#x}
    jne  {ACT_ORIG:#x}
    jmp  {ACT_BODY:#x}
""", CAVE_A)


def checks(d):
    u = lambda v: struct.unpack_from("<I", d, P.va2off(d, v))[0]
    p = P.va2off(d, u(WWE_VMT - 0x20))
    if u(WWE_VMT - 0x40) != WWE_VMT or d[p + 1:p + 1 + d[p]] != b"TWindWalkingEnchantment":
        sys.exit("ABORT: TWindWalkingEnchantment's VMT moved")
    for name, orig in (("cave_gct", GCT_ORIG), ("cave_act", ACT_ORIG)):
        va = FL.ADDR[name]
        o = P.va2off(d, va)
        want = dict(FL.CAVES[1:] and [(n, b) for n, _v, b in FL.CAVES])[name]
        if bytes(d[o:o + len(want)]) != want:
            sys.exit("ABORT: build_fly_levels.py's %s is not installed as its layout says (%08X)" % (name, va))
        if d[o:o + 6] != bytes.fromhex("83780c010f85") or va + PREFIX + struct.unpack_from("<i", d, o + 6)[0] != orig:
            sys.exit("ABORT: %s no longer opens with `cmp [eax+0xC],1 / jne %08X`" % (name, orig))


def main():
    d = open(P.TARGET, "rb").read()
    checks(d)
    pk = lambda v: struct.pack("<I", v)
    hooks = [(S_GCT, pk(GCT_ORIG), pk(CAVE_G)), (S_ACT, pk(ACT_ORIG), pk(CAVE_A))]
    caves = [("cave_wgct", CAVE_G, BLOB_G), ("cave_wact", CAVE_A, BLOB_A)]
    print("  jump targets: cave_gct+10 %08X, cave_act+10 %08X" % (GCT_BODY, ACT_BODY))
    run("build_wings_fly -- Spectral Wings flies up / down (AoWEPACK)", hooks, caves, SLOT, [],
        reloc_ok=(S_GCT, S_ACT))


if __name__ == "__main__":
    main()
