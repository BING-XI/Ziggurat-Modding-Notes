#!/usr/bin/env python
r"""
build_isohex_replace.py -- an Earth/Rock brush on surface Water/Ice replaces the water hexagon
instead of re-skinning it.  HSEPack.dpl.  Owner bug report 2026-10-04.

THE CRASH
    Painting Rock onto surface water in AoWzEd: "Access violation at address 5579AF2D in module
    AoWEPACK.dpl. Read of address FFFFFFFF".  Caught live with re_tools/veh_capture.py
    (--at AoWEPACK.dpl+0x9AF2D): the hexagon being drawn was a TAoWWaterHexagon whose resource was
    a TUpperIsometricHexagonResource (the Rock wall), field terrain 8.  TAoWWaterHexagon.Show
    @0x5579AEAC draws water base tiles 140..155 (0x8C + variant) out of its resource's image list;
    the Rock list is shorter and ImageLib.TCustomImageLibrary.Get has no bounds check.

THE CAUSE
    Earth and Rock brushes place through TIsometricHexagonResource.PlaceResourceUser @0x55619BF8.
    It looks for ANY TIsometricHexagon on the field (FindOwnedHS with the class pointer at
    0x55619098) and, if it finds one, re-skins it in place (VMT +0x110 SetResource).  That is meant
    for Earth <-> Rock.  TAoWWaterHexagon descends from TLowerIsometricHexagon -> TIsometricHexagon,
    so it matches too.  Vanilla never met this: its palette offered Earth/Rock only underground,
    where there is no TAoWWaterHexagon (cave water is a TAoWHexagonResource).  build_deved_terrainpal
    made the palette cross-level.  Land brushes use THexagonResource.PlaceResourceUser, which
    searches for its own user class only, so Grass over water already replaces.

THE FIX
    55619C30  8BD8      mov  ebx, eax        <- hook (6 B, jmp + nop): no .reloc, no jump lands inside
    55619C32  85DB      test ebx, ebx
    55619C34  745B      je   0x55619C91      (create path)
    55619C36  ...                            (re-skin path)
    cave_iso re-skins only when the found hexagon's ClassID (object VMT +0x24) equals the
    resource's ResourceUserClassID (resource VMT +0x58), i.e. the hexagon is exactly what this
    resource would create.  Anything else takes the create path: CreateResourceUser, then
    THSMap.PlaceHX -> TMapObject.MainPlace -> TAbstractHexagon.PlaceHX @0x5560A6D4, which destroys
    the field's existing hexagon before placing the new one -- the same way Grass replaces water.
    Ids: TUpperIsometricHexagon 0x20170 (resource 0x20171), TAoWWaterHexagon 0x2073D (resource
    0x2073E).  Earth <-> Rock and Water <-> Ice still re-skin as in vanilla; Water/Ice painted over
    Earth/Rock now replaces too (it used to re-skin the wall with water art).

Applies to the game as well (HSEPack is shared), wherever a resource's PlaceResourceUser runs.
Rolls: none.  PIC: rel32 only.  Slot 0x5561C800-0x5561C87F (CODE zero tail), exclusive.
Surgical --undo.
"""
import os
import sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run

P.TARGET = os.path.join(P.GAME, "HSEPack.dpl")
P.IMAGE_BASE = 0x55600000

SLOT = (0x5561C800, 0x5561C880)
CAVE = 0x5561C800
HOOK = 0x55619C30
HOOK_ORIG = bytes.fromhex("8bd885db745b")
RESKIN = 0x55619C36
CREATE = 0x55619C91
FN_LO, FN_HI = 0x55619BF8, 0x55619CCA       # TIsometricHexagonResource.PlaceResourceUser


def build(va):
    # eax = found TIsometricHexagon or nil, esi = the resource being placed.
    # [res vmt+0x58] = ResourceUserClassID, [hexagon vmt+0x24] = ClassID.
    return asm(f"""
        mov  ebx, eax
        test ebx, ebx
        jz   _create
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x58]
        push eax
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x24]
        pop  edx
        cmp  eax, edx
        jne  _create
        jmp  {RESKIN:#x}
    _create:
        jmp  {CREATE:#x}
    """, va)


caves = [("cave_iso", CAVE, build(CAVE))]
hooks = [(HOOK, HOOK_ORIG, P.jmp_to(HOOK, CAVE, 6))]
interior = [(HOOK, HOOK + 6, FN_LO, FN_HI)]

if __name__ == "__main__":
    run("build_isohex_replace", hooks, caves, SLOT, interior)
