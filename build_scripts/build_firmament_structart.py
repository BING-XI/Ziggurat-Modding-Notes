#!/usr/bin/env python
r"""
build_firmament_structart.py -- cities (and every structure) on the Firmament wear their SURFACE
art, not their cave art.  AoWEPACK.dpl.  Owner request 2026-10-01.

WHY THEY LOOKED UNDERGROUND
  Two level tests, both `level == 0 ? surface : underground`, so the Firmament (level 3) fell on
  the underground side.

  1. The terrain a structure stands on.  ILTer.TILTerrainMO.GetValidTerrainType (HSEPack
     0x55618780) takes the most frequent terrain under the footprint (VMT +0x124); when the
     structure has no art for it -- Sky, on the Firmament -- it asks VMT +0x130 ForceTerrainType.
     AoWE.TStructure.ForceTerrainType @0x5575E93C and Pad.TPad.ForceTerrainType @0x557FE950 are
     the same 20 bytes:
         cmp dword [edx+8], 0 / je -> -1 / mov al, 0xC        ; [TMapLevel+8] = the level index
     (TMapContainer.AddLevel, HSEPack 0x55608E18, stores the level count there), so every
     structure placed on Firmament Sky got Dirt 0xC.  TMultiHexMO.OverrideTerrain then writes
     that into the hex's terrain cache, and TCity.UpdateImages @0x557AC494 reads the cache:
     terrain {5, 7, 8, 9, 0xC, 0xD} -> image offset 0x28, the U_wall / underground set.
     42 classes inherit TStructure's copy (City, Cave, Mine, Tower, the nodes, the sites ...).
  2. The city picture itself.  AoWE.TRaceResource.GetCityImage @0x55759EBC (EDX = size, ECX =
     terrain, [ebp+8] = the hex's level) tries a terrain-specific picture, id terrain*10 + 0x46
     + size - 1, and when the race has none falls back on
         level == 0 ? id 0x32 + size - 1 (surface) : id 0x3C + size - 1 (underground)
     at 0x55759F08.  Firmament terrain rarely has its own picture, so this alone gave the cave
     city.

THE PATCH -- three in-place rewrites, no cave
  A/B. Both ForceTerrainType bodies (20 B each) become
         movsx eax, byte [edx+8] / dec eax / js -> ret      ; level 0: EAX = -1, as vanilla
         cmp al, 2 / mov al, 0xC / jne -> ret               ; not the Firmament: Dirt, as vanilla
         mov al, 1 / ret 4                                  ; the Firmament: Grass
     18 B + 2 NOPs after the ret.  Grass (1) rather than vanilla's surface "-1": -1 sends
     GetValidTerrainType into its terrain scan from index 0, and a resource with an image 0
     (Str_cave.ILB has one) would turn the hex into Water.  Grass is what the scan returns for
     structures on the surface (build_pad_skyalias.py), and it gives a Firmament cave mouth a
     walkable, non-Sky hex, so build_fly_levels.py's Sky/Chasm movement drain never fires on it.
     Only the FALLBACK changes: a structure on Firmament terrain it has art for (painted Grass,
     Desert ...) keeps that terrain, exactly as on the surface.
  C.   GetCityImage's fallback (22 B at 0x55759F08) becomes
         mov ebx, [ebp-4] / add ebx, 0x31                   ; surface id
         mov eax, [ebp+8] / test eax, eax / je done
         cmp eax, 3 / je done
         add ebx, 0xA                                       ; underground id
       done: nop                                            ; 0x55759F1E: mov edx, ebx ...
     EAX is dead there (0x55759F20 reloads it).

  A structure's own terrain (+0x18) is not saved -- TMultiHexMO.ReadWrite streams only x, y --
  and TILTerrainMO.Activate (HSEPack 0x55618C10) works it out again at every load, so cities
  already on the Firmament pick this up when the map is next opened.
  Unproven: that at Activate time the hex's terrain cache no longer holds the Dirt the old rule
  published.  If an existing Firmament city still looks underground, delete and re-place it.

LEFT ALONE
  Shipyard.TShipyardConstructionControl.StructureResource +0x0F (0x557C769C) still picks the
  underground shipyard resource (0x6B) off the surface; a shipyard built in play on the
  Firmament wears the cave sprite (11-engine-internals.md, "Every level == 0 site").

COUPLINGS
  * build_pad_skyalias.py repoints TPad's VMT +0x12C (GetTerrainTypeImage) so a pad accepts Sky;
    it does not touch ForceTerrainType.  No shared bytes.
  * build_maplevel4.py v5 (Firmament <-> Surface caves): its Firmament mouth now lands on Grass
    where it used to land on Dirt.
  * A sixth map level would take the Dirt arm (it is neither 0 nor 3) in both edits.

Rolls: none.  PIC: no absolute operand, no .reloc under any site.  Surgical --undo.
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, run

FIRMAMENT = 3
GRASS, DIRT = 1, 0x0C

FT_VAN = bytes.fromhex("558bec837a08007404b00ceb0383c8ff5dc20400")
FT_STRUCT = 0x5575E93C                      # AoWE.TStructure.ForceTerrainType
FT_PAD = 0x557FE950                         # Pad.TPad.ForceTerrainType

CI_SITE = 0x55759F08                        # TRaceResource.GetCityImage fallback
CI_VAN = bytes.fromhex("837d080075098b5dfc83c3324beb078b5dfc83c33c4b")
CI_FN = (0x55759EBC, 0x55759F42)


def build_ft(va):
    b = asm(f"""
        movsx eax, byte ptr [edx + 8]
        dec  eax
        js   _r
        cmp  al, {FIRMAMENT - 1}
        mov  al, {DIRT}
        jne  _r
        mov  al, {GRASS}
    _r:
        ret  4
    """, va)
    assert len(b) <= len(FT_VAN), "ForceTerrainType rewrite is %d B" % len(b)
    return b + b"\x90" * (len(FT_VAN) - len(b))


def build_ci(va):
    b = asm(f"""
        mov  ebx, dword ptr [ebp - 4]
        add  ebx, 0x31
        mov  eax, dword ptr [ebp + 8]
        test eax, eax
        je   _d
        cmp  eax, {FIRMAMENT}
        je   _d
        add  ebx, 0xA
    _d:
    """, va)
    assert len(b) <= len(CI_VAN), "GetCityImage rewrite is %d B" % len(b)
    return b + b"\x90" * (len(CI_VAN) - len(b))


hooks = [(FT_STRUCT, FT_VAN, build_ft(FT_STRUCT)),
         (FT_PAD, FT_VAN, build_ft(FT_PAD)),
         (CI_SITE, CI_VAN, build_ci(CI_SITE))]
interior = [(FT_STRUCT, FT_STRUCT + len(FT_VAN), FT_STRUCT, FT_STRUCT + len(FT_VAN)),
            (FT_PAD, FT_PAD + len(FT_VAN), FT_PAD, FT_PAD + len(FT_VAN)),
            (CI_SITE, CI_SITE + len(CI_VAN), CI_FN[0], CI_FN[1])]


if __name__ == "__main__":
    if "--dis" in sys.argv:
        from aowepack_patch import show
        show([("ForceTerrainType (TStructure)", FT_STRUCT, hooks[0][2]),
              ("ForceTerrainType (TPad)", FT_PAD, hooks[1][2]),
              ("GetCityImage fallback", CI_SITE, hooks[2][2])])
    run("build_firmament_structart", hooks, [], (FT_STRUCT, FT_STRUCT), interior)
