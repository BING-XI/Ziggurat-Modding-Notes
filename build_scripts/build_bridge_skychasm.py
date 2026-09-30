#!/usr/bin/env python
r"""
build_bridge_skychasm.py -- bridges over Sky and Chasm obey the water rule: a one-hex span whose
two opposite neighbours are land.  AoWEPACK.dpl.  Owner request 2026-10-01.

THE DEFECT
  Bridges on Sky / Chasm (build_hss_addresource.py cloned a Water and a CaveWater hexagon bridge)
  could be laid side by side without end.  HxBridge.THexagonBridge.DirectionValid @0x55799C04
  accepts an axis when the hexes at both of its ends are land, asked of AoWE.Land @0x5575AEA4,
  which returns "not land" only for {0 Water, 6 Ice, 9 Lava, 10 CaveWater, 13 CaveIce}.  Sky 0x0E
  and Chasm 0x0B were land, so every Sky hex next to a Sky bridge was a bank.

WHICH BRIDGE
  Only the hexagon bridge.  The editor's road brush (TMORTerrainControl.Place, HSEPack 0x5560EA94)
  picks among resources registered with the road control by terrain, and the engine bridge never
  registers: Bridge.TBridgeResource.MsgProc (HSEPack 0x55618138) returns on message 0x10014
  without passing it to TAbstractRoadResource.MsgProc.  The engine bridge's placement
  (TAbstractRoad.CanPlace) has no bank test at all.

THE PATCH -- Land rewritten in place (28 B), no cave
      movzx eax, al / cmp al, 0xF / ja land
      mov edx, 0x6E41 / bt edx, eax / setnc al / ret        ; bit set = not land
  land: mov al, 1 / ret
  0x6E41 = bits {0, 6, 9, 10, 11, 13, 14}: vanilla's five plus Chasm 11 and Sky 14.  Terrain above
  0xF (and the border ring 0xF) stays land, as vanilla.  EDX is caller-saved in the Delphi register
  convention.
  Land has 14 callers, all in HxBridge: DirectionValid x2 and UpdateExclusiveMoves x12 (which links
  the bridge to the land at its ends for movement).  No other module imports it (checked every exe
  and package in Ziggurat\), so nothing outside the hexagon bridge changes.

EXISTING BRIDGES
  THexagonBridge.Activate re-runs only UpdateExclusiveMoves, never the axis test, so a bridge chain
  already on a map stays placed, but its links into neighbouring Sky / Chasm hexes are gone:
  walkers cannot cross it.  The editor frees a bridge whose axis becomes invalid only when a
  neighbouring hex's terrain changes (NeighbourTerrainChanged @0x5579A054).  Delete old chains by
  hand.

Rolls: none.  PIC: no absolute operand, no .reloc in the range.  Surgical --undo.
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, run, show

LAND = 0x5575AEA4
LAND_VAN = bytes.fromhex("84c074132c06740f04fd2c0272092c02740533c03401c3b0013401c3")
NOT_LAND = (0x0, 0x6, 0x9, 0xA, 0xB, 0xD, 0xE)     # Water Ice Lava CaveWater Chasm CaveIce Sky
MASK = sum(1 << t for t in NOT_LAND)
assert MASK == 0x6E41


def build(va):
    b = asm(f"""
        movzx eax, al
        cmp  al, 0xF
        ja   _land
        mov  edx, {MASK:#x}
        bt   edx, eax
        setnc al
        ret
    _land:
        mov  al, 1
        ret
    """, va)
    assert len(b) <= len(LAND_VAN), "Land rewrite is %d B" % len(b)
    return b + b"\x90" * (len(LAND_VAN) - len(b))


NEW = build(LAND)


def model():
    """Run the assembled bytes' rule against vanilla's for every terrain byte."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    text = [(i.mnemonic, i.op_str) for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(NEW, LAND)]
    assert ("mov", "edx, 0x6e41") in text and ("setae", "al") in text, text
    for t in range(256):
        vanilla = t not in (0, 6, 9, 10, 13)
        ours = t > 0xF or not (MASK >> t) & 1
        assert ours == (vanilla and t not in (0xB, 0xE)), "terrain %d" % t


model()

if __name__ == "__main__":
    if "--dis" in sys.argv:
        show([("AoWE.Land", LAND, NEW)])
    run("build_bridge_skychasm", [(LAND, LAND_VAN, NEW)], [], (LAND, LAND),
        [(LAND, LAND + len(LAND_VAN), LAND, LAND + len(LAND_VAN))])
