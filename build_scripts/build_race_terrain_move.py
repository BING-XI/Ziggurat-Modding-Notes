#!/usr/bin/env python
r"""
build_race_terrain_move.py -- Snow and Desert cost walkers +1 movement point; Frostlings walk Snow
and Azracs walk Desert at the Grass cost.  AoWEPACK.dpl.
Owner request 2026-09-27: +1 in general when walked over (not the Flying table), cancelled for the
home race only (Frostling on Snow, Azrac on Desert); Road and Structure hexes exempt.

PART A -- THE TABLES (pure data)
    Eight 16x16 base tables at 0x558E84FC + i*0x100 (row = terrain, column = overlay + 1).  The
    startup generator SUB_55744B2C takes the element-wise MIN of a unit's tables, so a penalty on
    Walking alone would be lifted by any second walking ability.  The +1 therefore goes on every
    walking-family table: Walking 0, Forestry 3, Cave Crawling 4, Mountaineering 5, Tunneling 7.
    Swimming 1 (Ooze column only on land), Flying 2 and Fire Immunity 6 (no land costs) are left
    alone.  Rows Desert 2 and Snow 3; every passable cell gets +1 except Road (column 5) and
    Structure (column 8).  Grass and Steppe were byte-identical to these rows before this script,
    and the race cave below relies on Grass still matching the pre-penalty cost.

PART B -- THE RACE DISCOUNT (cave)
    TAbstractUnit.CreateMovePointTable @0x5577FDC4 (EAX unit, EDX 256-byte buffer) is the only
    per-unit table builder: MovedTo -> MovePointCost, TArmy.CreateMovePointTable (army = MAX over
    its units, so a mixed stack pays the penalty), the move predictor, TAIGroupControl and
    TAIMoveTargetSelector all call it.  Its 6-byte prologue
        53 56 57 83 C4 F0      push ebx / push esi / push edi / add esp,-0x10
    becomes `E9 -> cave_race` + nop.  The cave keeps EAX/EDX, calls a replay of the prologue that
    jumps back to 0x5577FDCA (the function's own `ret` returns into the cave), then asks the unit
    for its race through VMT +0xA4 (AL only valid; TAbstractUnit's base returns -1, so walls and
    raceless units never match) and, for Frostling 3 / Azrac 1, copies the Grass row
    (buf+0x10) over the Snow row (buf+0x30) / Desert row (buf+0x20).  The copy runs after every
    modifier the function applies (player road flag, Enchanted/Cursed Roads, Haste), which all
    treat the three rows alike, so the home terrain ends up exactly as Grass would.  A flyer's
    rows are already equal, so the copy is a no-op for it.
    The entry hook rather than the epilogue: the dormant ability-0x84 loop (skipped by
    build_lethargy.py's jmp at 0x5577FF9E) reuses ESI, so an epilogue cave would lose the unit if
    that jmp were ever undone.

TACTICAL COMBAT -- covered by the same two parts, no AoWTCPCK patch
    AoWTCPCK imports CreateMovePointTable (thunk 0x4029BC) and builds every combat move table
    through it, on the strategic unit [TCombatUnit+0x4C]: the player's path
    (TCombatUnitSelectionControl.Update 0x41FEE5, .CalculateMovePath 0x41D926, into
    [settings+0xAC]) and six sites in TCAI.EvalBattle.  TTacticalCombatUnitHS.CanMoveOn reads it
    at 0x420B0C with the world-map layout ([+0x31 + terrain*16 + overlay]), and combat hexes use
    the world-map terrain ids (TCombatHexagon.TerrainChanged special-cases the same {0,6,0xE}).
    The cave's GetRace call is on the same object vanilla already calls virtually (VMT +0xE8), so
    it adds no exposure to the TCombatWall +0x4C alias.

NOT COVERED
    TAIMoveControl.Initialize copies a raw MovePointTables entry for one secondary object
    (+0x130), and TFortifyAGC.GetSurroundingEnemyStrength reads them too: AI estimates there see
    the +1 for Frostlings/Azracs.  Deterministic on every peer.

Rolls: none (deterministic, MP-safe).  PIC: register operands and rel32 only.
Slot 0x55851880-0x558518FF, exclusive.  Surgical --undo restores the pre-script table bytes.
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x55851880, 0x55851900)
CAVE = 0x55851880
HOOK, VAN = 0x5577FDC4, bytes.fromhex("535657 83c4f0")
RESUME = 0x5577FDCA
FN_LO, FN_HI = 0x5577FDC4, 0x5577FFCC          # TAbstractUnit.CreateMovePointTable
VMT_GETRACE = 0xA4

TABLE0 = 0x558E84FC
DESERT, SNOW, GRASS = 2, 3, 1
EXEMPT_COLS = (5, 8)                            # Road, Structure
# pre-script live rows (Desert and Snow identical), per walking-family table
ROWS = {
    0: "04ff06060403ff0603ff04ff0cffffff",      # Walking
    3: "04ff04060403ff0603ff04ff0cffffff",      # Forestry
    4: "05ff06060505ff0505ff05ff08ffffff",      # Cave Crawling
    5: "ff06ff04ffffffffffffffffffffffff",      # Mountaineering
    7: "06ff08060606ff0606ff06ff06ffffff",      # Tunneling
}
RACE_ROW = {3: SNOW, 1: DESERT}                 # Frostling -> Snow, Azrac -> Desert


def penalised(row):
    return bytes(v if v == 0xFF or c in EXEMPT_COLS else v + 1 for c, v in enumerate(row))


def build(va):
    ladder = ""
    for race, row in RACE_ROW.items():
        ladder += f"""
        mov ecx, 0x{row * 0x10:X}
        cmp al, {race}
        je _copy"""
    g = GRASS * 0x10
    return asm(f"""
        push eax
        push edx
        call _body
        pop edx
        pop eax
        push edx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x{VMT_GETRACE:X}]
        pop edx
        {ladder}
        ret
    _copy:
        add ecx, edx
        mov eax, dword ptr [edx + 0x{g:X}]
        mov dword ptr [ecx], eax
        mov eax, dword ptr [edx + 0x{g + 4:X}]
        mov dword ptr [ecx + 4], eax
        mov eax, dword ptr [edx + 0x{g + 8:X}]
        mov dword ptr [ecx + 8], eax
        mov eax, dword ptr [edx + 0x{g + 12:X}]
        mov dword ptr [ecx + 0xC], eax
        ret
    _body:
        push ebx
        push esi
        push edi
        add esp, -0x10
        jmp 0x{RESUME:X}
    """, va)


blob = build(CAVE)
caves = [("cave_race", CAVE, blob)]
hooks = [(HOOK, VAN, jmp_to(HOOK, CAVE, len(VAN)))]
for t, hexrow in ROWS.items():
    old = bytes.fromhex(hexrow)
    for terrain in (DESERT, SNOW):
        hooks.append((TABLE0 + t * 0x100 + terrain * 0x10, old, penalised(old)))
interior = [(HOOK, HOOK + len(VAN), FN_LO, FN_HI)]

if __name__ == "__main__":
    run("build_race_terrain_move", hooks, caves, SLOT, interior)
