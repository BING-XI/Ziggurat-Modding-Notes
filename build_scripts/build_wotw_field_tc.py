#!/usr/bin/env python
r"""
build_wotw_field_tc.py -- Weight of the World's field, the AoWTCPCK half: step costs double on field
hexes, and Flying / Floating / Wind Walking units standing in a field are grounded.  AoWEPACK half
(the router, the movement-type flag): build_wotw_field.py.  The field is bit 0x20 of [field+0x1B],
marked by build_wotw_tc.py's landing.  Owner's design 2026-10-26 (05-spells-added.md).

MOVEMENT  the router (build_wotw_field.py) plans with doubled field hexes; every path then carries
  its step costs in byte 3 of each entry (x byte 0, y byte 1; the last entry is the start), and the
  move is charged from those bytes.  Both writers are followed:
  M2  0x0041DBDC  CalculateMovePath's `call PosToMovePoints` (5 B; EAX = the path's list) -> call
      m_cmp: entries 0..count-2 on a field hex with a cost 1..0x3F double, then PosToMovePoints.
      The player's preview, orders, group moves and build_tactical_los.py's calcwrap all pass here.
  M3  0x00414337  TCAI.MakeTerrainPath's sum `movsx eax,[edx+eax*4+3] / add [ebp-0x10],eax` (8 B) ->
      jmp m_mtp + 3 nop: the same doubling, written back, then the sum (the `jno` after it reads the
      replayed add).  Build_skirmisher.py's flat 12 per attack is not a hex entry and stays.
GROUNDING  grounded(HS) = its hex F = [HS+4] carries bit 0x20 and a walker could stand there (the
  Walking move table, MovePointTables + 0x100 in AoWEPACK, at F's terrain and overlay is >= 0).  A
  flyer over water, chasm or lava inside a field keeps flying, so it is never stranded.
  G1  0x00412BF4  TTacticalCombatUnit VMT +0xA8 (GetAbilityEnabled; .reloc kept) -> g_air: Flying
      (1), Floating (0x3B) and Wind Walking (0xA5) answer no for a grounded unit; everything else,
      and every unit outside a field, goes on to the original thunk 0x004023F4.  Every tactical
      flyer test reads this slot: melee legality (cursor, path, AI), zone of control, free swings,
      touch, walls, gates, obstacles and the unit's drawing height.  The strike's +50 % reads the
      unit's own +0x148 instead, so a grounded flyer still takes it (build_wotw.py).
  G2  0x00412AC8  TCombatMoveControl VMT +4 ProcessMove (.reloc kept) -> g_pm: for a grounded mover
      (the HS at settings+0x9C) the movement table at settings+0xAC is rebuilt by
      CreateMovePointTable with build_wotw_field.py's FLAG set (a walker's table, every per-unit
      adjustment kept), then the original 0x0041D038.  So it walks: terrain costs, walls, rivers.
  G3  0x00421686  the Tremors handler's `call [edx+0xE8]` (6 B; [ebp-4] = the HS) -> call g_tq + nop:
      a grounded flyer reads as a walker, so Tremors hits it.
  Grounding is decided where the unit stands when it moves; a flyer starting outside flies its
  whole move and pays double on field hexes.
Cross-module: AoWEPACK's FLAG and MovePointTables are reached through the rebase delta of the
CreateMovePointTable import cell 0x0046E590 (its value minus 0x5577FDC4).
RNG: none.  Slot 0x00445000-0x00445FFF, exclusive.  PIC.  Surgical --undo.

    python build_scripts/build_wotw_field_tc.py            dry run + state
    python build_scripts/build_wotw_field_tc.py --apply
    python build_scripts/build_wotw_field_tc.py --undo
    python build_scripts/build_wotw_field_tc.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000
from aowepack_patch import asm, run
from piccave import pic

FIELD_BIT = 0x20
SLOT = (0x00445000, 0x00446000)
AIR_IDS = (0x01, 0x3B, 0xA5)
VAR_COMBATMAP = 0x0046C064
GETMAPLEVEL, GETFIELD = 0x00401E64, 0x00401E54
L_W, L_H = 0x0C, 0x10
CELL_CMPT, CMPT_PREF = 0x0046E590, 0x5577FDC4           # CreateMovePointTable: import cell, preferred VA
CMPT_THUNK = 0x004029BC
EP_FLAG, EP_WALKTABLE = 0x558FAED0, 0x558EA040 + 0x100     # AoWEPACK (preferred VAs)
POS_TO_MP, MTP_RESUME = 0x00402744, 0x0041433F
G1_CELL, G1_ORIG = 0x00412BF4, 0x004023F4
G2_CELL, G2_ORIG = 0x00412AC8, 0x0041D038
SITES = {   # name: (va, vanilla, kind)
    "cmp": (0x0041DBDC, "e8634bfeff", "call"),
    "mtp": (0x00414337, "0fbe4482030145f0", "jmp"),
    "tq":  (0x00421686, "ff92e8000000", "call"),
}
A = {}


def c_field(va):
    """eax = x, edx = y -> eax = the combat field, or 0 off the level.  Keeps ebx/esi/edi/ebp."""
    src = f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        {{ANC}}
        mov  eax, dword ptr [ebx + {{MAP}}]
        test eax, eax
        je   f_no
        mov  eax, dword ptr [eax + 0x10]
        xor  edx, edx
        call {GETMAPLEVEL:#x}
        test eax, eax
        je   f_no
        cmp  esi, dword ptr [eax + {L_W:#x}]
        jae  f_no
        cmp  edi, dword ptr [eax + {L_H:#x}]
        jae  f_no
        mov  edx, esi
        mov  ecx, edi
        call {GETFIELD:#x}
        jmp  f_out
    f_no:
        xor  eax, eax
    f_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"MAP": VAR_COMBATMAP})


def c_delta(va):
    """-> eax = AoWEPACK's rebase delta (runtime minus preferred).  Keeps everything else but eax."""
    src = f"""
        push ebx
        {{ANC}}
        mov  eax, dword ptr [ebx + {{CELL}}]
        sub  eax, {CMPT_PREF:#x}
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"CELL": CELL_CMPT})


def c_grounded(va):
    """eax = a unit HS -> eax 1 when its hex is in a field and a walker could stand there."""
    return asm(f"""
        test eax, eax
        je   g_no
        mov  eax, dword ptr [eax + 4]
        test eax, eax
        je   g_no
        test byte ptr [eax + 0x1b], {FIELD_BIT:#x}
        je   g_no
        push ebx
        mov  ebx, eax
        call {A['delta']:#x}
        movsx edx, byte ptr [ebx + 0x14]
        shl  edx, 4
        movsx ecx, byte ptr [ebx + 0x15]
        add  edx, ecx
        movsx eax, byte ptr [eax + edx + {EP_WALKTABLE:#x}]
        pop  ebx
        test eax, eax
        js   g_no
        mov  eax, 1
        ret
    g_no:
        xor  eax, eax
        ret
    """, va)


def c_air(va):
    """G1: GetAbilityEnabled(eax combat unit, edx id) -> al."""
    tests = "".join(f"""
        cmp  edx, {i:#x}
        je   a_chk""" for i in AIR_IDS)
    return asm(f"""
        {tests}
        jmp  {G1_ORIG:#x}
    a_chk:
        push eax
        push edx
        mov  eax, dword ptr [eax + 0x60]
        call {A['grounded']:#x}
        test eax, eax
        pop  edx
        pop  eax
        jne  a_no
        jmp  {G1_ORIG:#x}
    a_no:
        xor  eax, eax
        ret
    """, va)


def c_pm(va):
    """G2: ProcessMove(eax move control, edx settings)."""
    return asm(f"""
        push eax
        push edx
        push ebx
        mov  ebx, edx
        mov  eax, dword ptr [ebx + 0x9c]
        call {A['grounded']:#x}
        test eax, eax
        je   p_go
        mov  eax, dword ptr [ebx + 0x9c]
        mov  eax, dword ptr [eax + 0x1c]
        test eax, eax
        je   p_go
        mov  eax, dword ptr [eax + 0x4c]
        test eax, eax
        je   p_go
        push eax
        call {A['delta']:#x}
        mov  byte ptr [eax + {EP_FLAG:#x}], 1
        pop  eax
        lea  edx, [ebx + 0xac]
        call {CMPT_THUNK:#x}
        call {A['delta']:#x}
        mov  byte ptr [eax + {EP_FLAG:#x}], 0
    p_go:
        pop  ebx
        pop  edx
        pop  eax
        jmp  {G2_ORIG:#x}
    """, va)


def c_tq(va):
    """G3: replaces `call [edx+0xE8]` in the Tremors handler; [ebp-4] = the HS."""
    return asm(f"""
        call dword ptr [edx + 0xe8]
        test al, 2
        je   q_out
        push eax
        mov  eax, dword ptr [ebp - 4]
        call {A['grounded']:#x}
        test eax, eax
        pop  eax
        je   q_out
        and  al, 0xfd
        or   al, 1
    q_out:
        ret
    """, va)


DOUBLE_ENTRY = f"""
        movzx eax, byte ptr [ecx]
        movzx edx, byte ptr [ecx + 1]
        push ecx
        call {{FIELD}}
        pop  ecx
        test eax, eax
        je   {{SKIP}}
        test byte ptr [eax + 0x1b], {FIELD_BIT:#x}
        je   {{SKIP}}
        movsx eax, byte ptr [ecx + 3]
        cmp  eax, 1
        jl   {{SKIP}}
        cmp  eax, 0x3f
        jg   {{SKIP}}
        shl  eax, 1
        mov  byte ptr [ecx + 3], al"""


def c_cmp(va):
    """M2: replaces `call PosToMovePoints` (eax = the path's list, edx = 0)."""
    body = DOUBLE_ENTRY.format(FIELD="%#x" % A["field"], SKIP="c_next")
    return asm(f"""
        push eax
        push edx
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  edi, dword ptr [esi + 8]
        dec  edi
        jle  c_done
        xor  ebx, ebx
    c_loop:
        mov  ecx, dword ptr [esi + 4]
        lea  ecx, [ecx + ebx*4]
        {body}
    c_next:
        inc  ebx
        cmp  ebx, edi
        jl   c_loop
    c_done:
        pop  edi
        pop  esi
        pop  ebx
        pop  edx
        pop  eax
        jmp  {POS_TO_MP:#x}
    """, va)


def c_mtp(va):
    """M3: eax = the entry index, edx = the entries, [[ebp-0xC]] = the list."""
    body = DOUBLE_ENTRY.format(FIELD="%#x" % A["field"], SKIP="m_pop")
    return asm(f"""
        push eax
        push edx
        push ecx
        mov  ecx, dword ptr [ebp - 0xc]
        mov  ecx, dword ptr [ecx]
        mov  ecx, dword ptr [ecx + 8]
        dec  ecx
        cmp  eax, ecx
        jge  m_pop
        lea  ecx, [edx + eax*4]
        {body}
    m_pop:
        pop  ecx
        pop  edx
        pop  eax
        movsx eax, byte ptr [edx + eax*4 + 3]
        add  dword ptr [ebp - 0x10], eax
        jmp  {MTP_RESUME:#x}
    """, va)


BUILDERS = [("field", c_field), ("delta", c_delta), ("grounded", c_grounded), ("air", c_air),
            ("pm", c_pm), ("tq", c_tq), ("cmp", c_cmp), ("mtp", c_mtp)]


def layout():
    for n, _b in BUILDERS:
        A.setdefault(n, SLOT[0] + 0x800)
    for _ in range(3):
        va, blobs = SLOT[0], []
        for n, b in BUILDERS:
            A[n] = va
            blob = b(va)
            blobs.append(("cave_" + n, va, blob))
            va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    return blobs


def checks(d):
    u = lambda v: struct.unpack_from("<I", d, P.va2off(d, v))[0]
    rb = lambda va, n: bytes(d[P.va2off(d, va):P.va2off(d, va) + n])
    if rb(CMPT_THUNK, 6) != b"\xff\x25" + struct.pack("<I", CELL_CMPT):
        sys.exit("ABORT: %08X is not CreateMovePointTable's import thunk" % CMPT_THUNK)
    if u(G1_CELL) not in (G1_ORIG, A["air"]) or u(G2_CELL) not in (G2_ORIG, A["pm"]):
        sys.exit("ABORT: a VMT cell holds an unexpected value")
    if rb(0x0042167B, 11) != bytes.fromhex("8b45fc8b401c8b404c8b10"):
        sys.exit("ABORT: the Tremors handler's HS load moved")


def main():
    from build_wotw_tc import interior_jumps
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d)
    hooks = []
    for name, (va, van, kind) in SITES.items():
        van = bytes.fromhex(van)
        op = 0xE8 if kind == "call" else 0xE9
        hooks.append((va, van, bytes([op]) + struct.pack("<i", A[name] - (va + 5)) + b"\x90" * (len(van) - 5)))
    hooks.append((G1_CELL, struct.pack("<I", G1_ORIG), struct.pack("<I", A["air"])))
    hooks.append((G2_CELL, struct.pack("<I", G2_ORIG), struct.pack("<I", A["pm"])))
    bad = interior_jumps(d, [(va, va + len(bytes.fromhex(v))) for va, v, _k in SITES.values()])
    if bad:
        sys.exit("ABORT: jumps into a hook's interior: " + ", ".join("%08X->%08X" % x for x in bad))
    print("  interior sweep: no branch lands inside a displaced range")
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    run("build_wotw_field_tc -- Weight of the World's field (AoWTCPCK)", hooks, blobs, SLOT, [],
        reloc_ok=[G1_CELL, G2_CELL])


if __name__ == "__main__":
    main()
