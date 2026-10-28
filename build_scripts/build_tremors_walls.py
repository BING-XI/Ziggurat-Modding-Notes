#!/usr/bin/env python
r"""
build_tremors_walls.py -- Tremors does x4 damage to walls and gates (owner, 2026-10-27), in manual
battles and in auto-combat.  City buildings ("Structure") keep the normal damage (owner's ruling).
AoWTCPCK.dpl + AoWEPACK.dpl.

The multiplier is on the damage DEALT: ExecuteDamageRole's result times 4, so a hit is 0, 4, 8, 12
or 16 at DMG 4, not a roll of DMG 16.  The to-hit roll is untouched.

MANUAL BATTLES (AoWTCPCK)
    Tremors' landing (CombatTE.TCAbRangedTE.Execute @0x40BAA4, ability 0x34 + spell 0x70 only) sends
    map-field message 0x31004.  TCityWall.MapFieldMsgProc @0x405D04 (walls AND gates: TCityWallDoor
    inherits it; TCombatStructure has its own handler and is not touched) dispatches on
    msg - 0x31000 through a 15-entry jump table, so the case @0x406205 never shows the literal: it
    fetches spell 0x70 by id, rolls ExecuteDamageRole(DMG [ebp-0x15], ATK [ebp-0x16] - GetDefense)
    and calls SetHitPoints(HP - dealt).
      H_TC  0x00406274  6 B `mov edx,[ebp-4] / mov edx,[edx+0x20]`, right after the roll, ->
            `call cave_tc / nop`.  cave_tc 0x00447000: shl eax,2, the two loads, ret.
    The `call ExecuteDamageRole` itself is NOT retargeted: build_combatlog_siege.py's scan needs that
    call before every SetHitPoints.  Its log line reads old HP - new HP at SetHitPoints, so it
    prints the x4 damage.

AUTO-COMBAT (AoWEPACK)
    Walls are TCombatWall objects (VMT 0x55715C40, no descendants; immune to all but dtWall, DEF 0);
    Tremors (types 0x180) reaches them through TCombatSpell.CreateCA -> TCombatSpellCA (VMT
    0x557F3CC8, spell id dword at +0x18, written before GenerateEx) -> TDamageCA.GenerateEx, whose
    roll (`call cave_roleex`, build_mirrorimage.py, 0x55729CCA) returns the damage in AL.
      H_AC  0x55729CD0  7 B `mov [ebx+0x10],al / cmp byte [ebx+0x10],0` -> `jmp cave_ac`.
            cave_ac 0x558C4100: when AL > 0, [CA] is TCombatSpellCA, [CA+0x18] = 0x70 and [target]
            is TCombatWall: AL x 4 (127 above 31), then the two displaced instructions and back to
            the `je` at 0x55729CD7.  EBX = CA, ESI = target; ECX/EDX are reloaded before use.
    The CA stores the multiplied damage, so the replay (which re-executes stored CAs), the live log
    (GenerateEx's epilogue, build_combatlog_dll.py) and the replay log all read the x4 figure.

Weight of the World (spell 91, a TTremors instance) reaches neither site: it sends no 0x31004, its
CA carries id 91, and its types (0x0080) exclude dtWall.

RNG: no draw (P1-P5 selection test not applicable).  No writable state.  PIC: cave_tc has no
operand at all; cave_ac reads both VMTs through one call/pop anchor and returns by rel32.

Unproven: the AI estimates are unchanged -- auto-combat's fcGetDamageValueEx still values a Tremors
hit on a wall at x1, so it may under-rate casting Tremors at a wall.

Caves: AoWTCPCK 0x00447000-0x0044703F, AoWEPACK 0x558C4100-0x558C41FF, both exclusive.

FORWARD HAZARDS
  * build_combatlog_siege.py derives its SetHitPoints table from the live TCityWall.MapFieldMsgProc.
    The new `call cave_tc` sits between the ExecuteDamageRole call and SetHitPoints and changes no
    return address, so its scan still matches (that script's own OPEN hazard, build_deathfire_tc.py's
    cave at 0x405F06, is unrelated).
  * build_mirrorimage.py's 6-byte call at 0x55729CCA ends where H_AC starts; build_combatlog_dll.py
    owns the epilogue 0x55729D08.  Neither overlaps.

    python build_scripts/build_tremors_walls.py            dry run + state, both modules
    python build_scripts/build_tremors_walls.py --apply
    python build_scripts/build_tremors_walls.py --undo     surgical: hooks back, slots zeroed
    python build_scripts/build_tremors_walls.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run
from piccave import pic

EPACK = os.path.join(P.GAME, "AoWEPACK.dpl")
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")

TREMORS = 0x70

# ---- AoWTCPCK -------------------------------------------------------------------------------
T_SLOT = (0x00447000, 0x00447040)
MFMP_WALL = (0x00405D04, 0x00406300)          # TCityWall.MapFieldMsgProc, through its epilogue
JT_WALL, JT_N = 0x00405D43, 15                # its msg - 0x31000 jump table
CASE_TREMORS = 0x00406205                     # entry 4 (0x31004)
H_TC = 0x00406274
V_TC = bytes.fromhex("8b55fc8b5220")          # mov edx,[ebp-4] ; mov edx,[edx+0x20]
EDR_CALL = 0x0040626F                         # call ExecuteDamageRole thunk, just before H_TC
EDR_THUNK = 0x004024F4

CAVE_TC = T_SLOT[0]
BLOB_TC = asm("""
    shl  eax, 2
    mov  edx, dword ptr [ebp - 4]
    mov  edx, dword ptr [edx + 0x20]
    ret
""", CAVE_TC)
T_CAVES = [("cave_tc", CAVE_TC, BLOB_TC)]
T_HOOKS = [(H_TC, V_TC, b"\xE8" + struct.pack("<i", CAVE_TC - (H_TC + 5)) + b"\x90")]

# ---- AoWEPACK -------------------------------------------------------------------------------
E_SLOT = (0x558C4100, 0x558C4200)
GENEX = (0x55729C98, 0x55729D10)              # TDamageCA.GenerateEx
H_AC = 0x55729CD0
V_AC = bytes.fromhex("884310807b1000")        # mov [ebx+0x10],al ; cmp byte [ebx+0x10],0
AC_BACK = 0x55729CD7                          # the je
VMT_SPELLCA = 0x557F3CC8                      # TCombatSpellCA
VMT_WALL = 0x55715C40                         # TCombatWall

CAVE_AC = E_SLOT[0]
BLOB_AC = pic(f"""
    {{ANC}}
    test al, al
    jle  store
    lea  edx, [ecx + {{CA}}]
    cmp  dword ptr [ebx], edx
    jne  store
    cmp  dword ptr [ebx + 0x18], {TREMORS:#x}
    jne  store
    lea  edx, [ecx + {{WALL}}]
    cmp  dword ptr [esi], edx
    jne  store
    cmp  al, 0x1f
    jg   clamp
    shl  al, 2
    jmp  store
clamp:
    mov  al, 0x7f
store:
    mov  byte ptr [ebx + 0x10], al
    cmp  byte ptr [ebx + 0x10], 0
    jmp  {AC_BACK:#x}
""", CAVE_AC, "ecx", {"CA": VMT_SPELLCA, "WALL": VMT_WALL})
E_CAVES = [("cave_ac", CAVE_AC, BLOB_AC)]
E_HOOKS = [(H_AC, V_AC, jmp_to(H_AC, CAVE_AC, len(V_AC)))]


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def interior(d, fn, lo, hi):
    """Branches and jump-table dwords in fn landing strictly inside (lo, hi), plus any rel32 in the
    file -- a skipdata pass, so the jump table does not stop it."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.skipdata = True
    o = P.va2off(d, fn[0])
    buf = bytes(d[o:o + fn[1] - fn[0]])
    bad = []
    for x in md.disasm(buf, fn[0]):
        if (x.mnemonic.startswith("j") or x.mnemonic == "call") and not lo <= x.address < hi:
            try:
                t = int(x.op_str, 16)
            except ValueError:
                continue
            bad += [x.address] if lo < t < hi else []
    bad += [fn[0] + i for i in range(len(buf) - 3) if lo < struct.unpack_from("<I", buf, i)[0] < hi]
    return bad + P.rel32_into(d, lo, hi)


def checks():
    module(TCPCK, 0x00400000)
    d = open(TCPCK, "rb").read()
    rd = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    assert rd(JT_WALL + 4 * 4) == CASE_TREMORS, "TCityWall's 0x31004 case moved"
    o = P.va2off(d, EDR_CALL)
    assert d[o] == 0xE8 and EDR_CALL + 5 + struct.unpack_from("<i", d, o + 1)[0] == EDR_THUNK, \
        "the Tremors case no longer calls ExecuteDamageRole at %08X" % EDR_CALL
    o = P.va2off(d, CASE_TREMORS + 0x1D)
    assert d[o:o + 5] == b"\xBA" + struct.pack("<I", TREMORS), "the case no longer fetches spell 0x70"
    bad = interior(d, MFMP_WALL, H_TC, H_TC + len(V_TC))
    assert not bad, "jump into H_TC's interior from %s" % ", ".join("%08X" % a for a in bad)
    module(EPACK, 0x55700000)
    e = open(EPACK, "rb").read()
    rd = lambda va: struct.unpack_from("<I", e, P.va2off(e, va))[0]
    assert rd(VMT_WALL - 0x40) == VMT_WALL and rd(VMT_SPELLCA - 0x40) == VMT_SPELLCA, "VMT self-pointers"
    o = P.va2off(e, H_AC - 6)
    assert e[o] == 0xE8, "GenerateEx's roll call at %08X is not a call rel32 (build_mirrorimage.py)" % (H_AC - 6)
    bad = interior(e, GENEX, H_AC, H_AC + len(V_AC))
    assert not bad, "jump into H_AC's interior from %s" % ", ".join("%08X" % a for a in bad)


def go(argv):
    checks()

    def tcpck():
        module(TCPCK, 0x00400000)
        run("build_tremors_walls [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, [], argv)

    def epack():
        module(EPACK, 0x55700000)
        run("build_tremors_walls [AoWEPACK]", E_HOOKS, E_CAVES, E_SLOT, [], argv)

    tcpck()
    epack()


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])   # both modules verify first
        print("\n" + "=" * 60)
    go(argv)
