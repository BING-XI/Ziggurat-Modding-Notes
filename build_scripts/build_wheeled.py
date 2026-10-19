#!/usr/bin/env python
r"""
build_wheeled.py -- Wheeled (ability 0xC0), a passive for machines that roll on wheels: a road hex
costs 2 movement points instead of 3.  AoWEPACK.dpl.  Owner's design 2026-10-19.

WHERE ROAD COSTS COME FROM
    TAbstractUnit.CreateMovePointTable @0x5577FDC4 copies the unit's combined 16x16 table out of
    MovePointTables (row = terrain, column = overlay + 1, Road = overlay 4 = column 5) and then
    applies the owner's modifiers.  Every cost reader calls it: MovePointCost (the real deduction),
    the move predictor cave (0x5580D7E5), TArmy.CreateMovePointTable / MoveOnMovePoints (an army
    moves at its slowest unit's cost), the strategic AI (TAIGroupControl.UpdateGroupChanges,
    TAIMoveTargetSelector.ProcessStates) and AoWTCPCK through its import (TCAI.EvalBattle x6,
    TCombatUnitSelectionControl.CalculateMovePath / .Update).  So the game, the path preview and
    both AIs see the same road cost.  Enchanted Roads is the first modifier: owner > 0 and
    [GetPlayers(owner)+0x54]+0x44 bit 2 (TEnchantedRoadsEnchantment.Activate ORs it in) turns a
    road cell of exactly 3 into 2, in all 16 rows.  Walking, Forestry, Cave Crawling and
    Tunneling rows reach 3 on roads; Flying's are 4 and 5, so flyers are untouched.

WHAT IT DOES
    W  0x5577FE13  `mov bl,[esi+0x24] / test bl,bl` (5 B, just after the table copy, before the
                   owner test) -> jmp cave_road.  ESI = the unit, [esp] = the table.  With
                   GetAbilityEnabled(0xC0) (VMT +0x148, item-aware) every Road cell of exactly 3
                   becomes ROAD_COST; the displaced pair is replayed and control returns to the
                   owner test at 0x5577FE18.  Running before the owner test covers independents
                   (owner 0), which skip every other modifier.  Bridges (column 6) keep their 3,
                   as under Enchanted Roads.
    STACK          False (the owner's ruling 2026-10-19): Wheeled and Enchanted Roads do not add
                   up; either one makes a road 2.  Enchanted Roads' own block then finds no 3.
                   True would make a road 1 for a wheeled unit whose owner holds Enchanted Roads
                   (the cave reads the same player flag through a call/pop anchor to the AoWHSMap
                   global 0x558FA040).
    The race cave (build_race_terrain_move.py) copies the Grass row over Snow/Desert after the
    whole body, Road column included, so a Frostling or Azrac machine keeps the Wheeled road.

REGISTRATION (package init -- prove by launching the exe)
    R  0x557BCD81  `call RegisterAbility` (TDecayAbility's, in PassiveAb.RegisterPassiveAbilities,
                   EBX = the control) -> call cave_reg, which replays it first, then
                   CreateEnhancementAbility 0x5576601C (EAX 0xC0, EDX the name, CX 0x03FF) +
                   RegisterAbility 0x55750238.  Name literal through a call/pop anchor.
    Record (description, cost, mask): build_wheeled_pfs.py.  Carriers: the owner assigns them in
    the editor (ruling 2026-10-19), so no script writes Unitres.pfs.
    Ceilings: LADDER 0xC1 in build_abilityid_ceilings.py and build_tcablist_ceiling.py.  Hero
    Offers row 192 at 0 % (heroskill_races.json), Wayfaring column (herodlg_cats.py).

RNG     none -- no draw; the table is a pure function of the unit and its owner.

Slot 0x558A0100-0x558A02FF, exclusive.  PIC: rel32, register-relative, call/pop anchors.
Surgical --undo.  No coupling: the hook bytes are vanilla and no other script touches them.

    python build_scripts/build_wheeled.py            dry run + state
    python build_scripts/build_wheeled.py --apply
    python build_scripts/build_wheeled.py --undo
    python build_scripts/build_wheeled.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

SLOT = (0x558A0100, 0x558A0300)
CAVE = 0x558A0100
ABIL_ID = 0xC0
NAME = "Wheeled"
MASK = 0x03FF
STACK = False                 # with Enchanted Roads: False -> a road costs 2, True -> 1
ROAD_COL = 5                  # overlay 4 (Road) + 1
ROAD_COST, ROAD_WAS = 2, 3

CEA, REGISTER = 0x5576601C, 0x55750238
GET_PLAYERS, AOWHSMAP = 0x557544D0, 0x558FA040
R_SITE = 0x557BCD81
W_SITE, W_BACK = 0x5577FE13, 0x5577FE18
W_VAN = bytes.fromhex("8a5e2484db")                  # mov bl,[esi+0x24] / test bl,bl


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def ansistr(s):
    b = s.encode("latin1")
    return struct.pack("<iI", -1, len(b)) + b + b"\0"


ANCHOR = b"\xE8\x00\x00\x00\x00\x58"                 # call next / pop eax


def layout_road(va):
    """ESI = the unit, [esp] = the 256-byte table.  EAX/ECX/EDX are dead here: the host reloads
    all three before reading them.  CL = the road cost; the STACK arm keeps it on the stack
    across its GetPlayers call."""
    er = f"""
        push {ROAD_COST}
        movsx edx, byte ptr [esi + 0x24]
        test edx, edx
        jle  r_cost
        call r_anchor
    r_anchor:
        pop  eax
        mov  eax, dword ptr [eax + DISP]
        mov  eax, dword ptr [eax + 0x140]
        call {GET_PLAYERS:#x}
        test eax, eax
        je   r_cost
        mov  eax, dword ptr [eax + 0x54]
        test byte ptr [eax + 0x44], 2
        je   r_cost
        dec  dword ptr [esp]
    r_cost:
        pop  ecx
    """ if STACK else f"mov ecx, {ROAD_COST}"
    src = f"""
        mov  edx, {ABIL_ID:#x}
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        je   r_out
        {er}
        mov  eax, dword ptr [esp]
        add  eax, {ROAD_COL}
        mov  edx, 16
    r_loop:
        cmp  byte ptr [eax], {ROAD_WAS}
        jne  r_next
        mov  byte ptr [eax], cl
    r_next:
        add  eax, 0x10
        dec  edx
        jne  r_loop
    r_out:
        mov  bl, byte ptr [esi + 0x24]
        test bl, bl
        jmp  {W_BACK:#x}
    """
    if not STACK:
        return asm(src, va)
    # two passes: a disp32 placeholder finds the anchor, then the real displacement (same length)
    probe = asm(src.replace("DISP", "0x7fffffff"), va)
    k = probe.find(ANCHOR)
    assert k > 0 and probe.find(ANCHOR, k + 1) < 0, "call/pop anchor not found exactly once"
    anchor = va + k + 5
    code = asm(src.replace("DISP", "%#x" % (AOWHSMAP - anchor)), va)
    assert len(code) == len(probe) and code.find(ANCHOR) == k, "anchor moved between passes"
    return code


def build_reg(va):
    code = bytearray(asm(f"call {REGISTER:#x}", va))
    at = va + len(code)
    code += b"\xE8\x00\x00\x00\x00"
    anchor = at + 5
    code += asm("pop eax", anchor)
    fix = len(code)
    code += b"\x8D\x90" + b"\0\0\0\0"                  # lea edx,[eax+disp32] -> the name chars
    code += asm(f"""
        mov  cx, {MASK:#x}
        mov  eax, {ABIL_ID:#x}
        call {CEA:#x}
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER:#x}
        ret
    """, va + len(code))
    while len(code) % 4:
        code += b"\x90"
    lit = va + len(code) + 8
    code += ansistr(NAME)
    struct.pack_into("<i", code, fix + 2, lit - anchor)
    return bytes(code)


def layout():
    caves, va = [], CAVE
    def put(name, blob):
        nonlocal va
        caves.append((name, va, blob))
        va = (va + len(blob) + 0xF) & ~0xF
    put("cave_road", layout_road(va))
    put("cave_reg", build_reg(va))
    return {n: v for n, v, _b in caves}, caves


def check_id():
    """0xC0 must be ours alone: no CreateEnhancementAbility idiom outside our slot registers it,
    and ability_names gives it no other name.  Ability.pfs is reported only: its record for 0xC0
    is ours (build_wheeled_pfs.py)."""
    d = open(P.TARGET, "rb").read()
    _e, secs = P.sections(d)
    vs, sva, rs, ra = secs[0]
    used = []
    for i in range(ra, ra + rs - 5):
        if d[i] == 0xE8:
            src = P.IMAGE_BASE + sva + (i - ra)
            if src + 5 + struct.unpack_from("<i", d, i + 1)[0] == CEA:
                for k in range(5, 30):
                    if d[i - k] == 0xB8:
                        used.append((struct.unpack_from("<I", d, i - k + 1)[0], src))
                        break
    lo, hi = SLOT
    other = [(i, src) for i, src in used if i < 0x100 and not lo <= src < hi]
    clash = [u for u in other if u[0] == ABIL_ID]
    if clash:
        sys.exit("ABORT: CreateEnhancementAbility at %08X also registers %#x -- re-derive ABIL_ID"
                 % (clash[0][1], ABIL_ID))
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "re_tools"))
    import pfs, ability_names
    keys = {rid - 10 for rid, _b in pfs.load("ability.pfs")[0]}
    named = ability_names.names()
    if named.get(ABIL_ID, NAME) != NAME:
        sys.exit("ABORT: ability_names gives %#x to %r -- re-derive ABIL_ID" % (ABIL_ID, named[ABIL_ID]))
    print("  id %#x ours alone (highest other CreateEnhancementAbility id %#x); Ability.pfs record %s"
          % (ABIL_ID, max(i for i, _s in other), "present" if ABIL_ID in keys else "absent"))


at, caves = layout()
hooks = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, at["cave_reg"])),
         (W_SITE, W_VAN, jmp_to(W_SITE, at["cave_road"], 5))]
interior = [(W_SITE, W_SITE + 5, 0x5577FDC4, 0x5577FFCC)]

if __name__ == "__main__":
    check_id()
    run("build_wheeled", hooks, caves, SLOT, interior)
