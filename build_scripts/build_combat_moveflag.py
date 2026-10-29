#!/usr/bin/env python
r"""
build_combat_moveflag.py -- after a MANUAL battle, the stack left on the attacker's hex is no longer
stuck "moving", so units can merge into it again (board a ship, join a stack).  AoWEPACK.dpl only.
Owner's report 2026-10-29: a catapult unloaded from a ship to fight in an adjacent power node, with
two Crossbowmen left aboard; after the battle it could not board the ship again -- it ended on the
ship's hex as a second stack.  Vanilla.

THE FLAG   TArmy+0x11 bit 0x04, "moving".  Set by TMoveArmyTE.InitializeMove @0x55747E7C (0x55747F93)
    on the army that walks -- a NEW army when only part of a stack moves -- and cleared on te.army
    by TMoveArmyTE.FinishMove @0x55747FBC (0x5574805C).  GetNoneMovingArmyHS @0x557479D4, which
    FinishMove uses to find the stack an arriving army merges into, SKIPS any army with the bit set,
    so the arriver stays a separate stack on the hex.  TArmy.ReadWrite @0x5578E8EC clears the bit on
    load (0x5578E9C3) -- vanilla's own repair, and why the bug never outlives a reload (in a PBEM game
    the next player's load always clears it).

THE LEAK (captured live 2026-10-29: execution breakpoints and hex polling over a repeat of the battle)
    TArmyCombatMoveTE's combat execution @0x55749924 first pours every unit standing on the
    attacker's hex into the attacker's army (0x557499F2..0x55749A63), so that army -- flagged by
    InitializeMove -- is the whole stack during the battle.
      auto-resolve: the aftermath runs in the same function; the army left behind is cleared
        (0x55749EA5 / 0x55749F20, or by FinishMove through VMT +0x60).
      MANUAL battle: the battle is pending (result 1), so the function leaves through 0x55749F41
        with te.army = nil (FinishMove does nothing) and hands the aftermath to the callback
        TArmyCombatMoveTE.CombatExecuted @0x557496D4 (set at 0x55749B2C).  That callback splits the
        survivors who attacked into a queued TArmyDefaultMoveTE (0x5574A248) on a win, or just clears
        the attack marks on a loss -- and never touches TArmy+0x11.
    So after every manual battle the army on the attacker's hex keeps the bit: after a win when part
    of the stack attacked, after a loss or retreat always.  Captured: army 106387E8 (Cog + surviving
    Crossbowman) kept 04 after the catapult won and moved into the node; the catapult's move back
    found no merge partner.

THE FIX
    hook 0x557498FF (5 B, `xor edx,edx / mov eax,[ebx+0x18]`, past both branches' join, not a jump
    target, no .reloc entry) -> cave_clear: the attacker's hex from the combat's record
    ([ebx+0xC] +0x14/+0x18/+0x1C, the same fields both branches read) through the same
    TAoWHSMap.GetMapField thunk call (0x557020FC); every child that is a TArmyHS (class id
    0x20217) whose parent is that hex -- GetNoneMovingArmyHS's own filter, which excludes armies of
    neighbouring hexes listed there by sprite overlap -- gets bit 0x04 cleared.  Then the 5 bytes,
    resume 0x55749904.  A follow-up move queued for the winners sets the bit again in its own
    InitializeMove, as every move does.
    Nothing is moving at this point: the attack move has ended and its follow-up is only queued.

RANDOMNESS  none.  Deterministic from synchronised state (TE callback): every machine clears the same
    bits.  Mixed patched/unpatched multiplayer diverges on later merges, as any rule change does.
COUPLINGS   build_flight_fall.py owns three sites in CombatExecuted (0x557497D6, 0x55749803: the
    CREATE_XYL calls; 0x55749913: the exit), none inside this window; its ENT_VEND terrain check
    skips armies with bit 0x04, so a stack left on water by a manual battle is now checked like
    any stationary stack (a transporter that can stand there keeps its passengers).
Slot 0x558CB000-0x558CB0FF, exclusive.  PIC (one call/pop anchor for the AoWHSMap variable).
Surgical --undo restores the 5 bytes and zeroes the slot.

    python build_scripts/build_combat_moveflag.py            dry run + state
    python build_scripts/build_combat_moveflag.py --apply
    python build_scripts/build_combat_moveflag.py --undo
    python build_scripts/build_combat_moveflag.py --dis
    python build_scripts/build_combat_moveflag.py --emulate   run the cave under unicorn
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aowepack_patch as P
from aowepack_patch import run, jmp_to
from piccave import pic

SLOT = (0x558CB000, 0x558CB100)
CAVE = 0x558CB000
FN, FN_END = 0x557496D4, 0x5574991A          # TArmyCombatMoveTE.CombatExecuted
HOOK, RESUME = 0x557498FF, 0x55749904
HOOK_VAN = bytes.fromhex("33d28b4318")       # xor edx,edx / mov eax,[ebx+0x18]
VAR_HSMAP = 0x558FA040                       # AoWHSMap
GETFIELD = 0x557020FC                        # thunk: (map, x, y, [level]) -> field, callee pops 4
CID_ARMYHS = 0x20217
MOVING = 0x04


def build_cave(va):
    return pic(f"""
        push ecx
        push esi
        push edi
        push ebp
        push ebx
        mov  esi, dword ptr [ebx + 0xc]
        test esi, esi
        je   out
        {{ANC}}
        mov  eax, dword ptr [ecx + {{HSMAP}}]
        test eax, eax
        je   out
        mov  eax, dword ptr [eax + 0x10]
        push dword ptr [esi + 0x1c]
        mov  ecx, dword ptr [esi + 0x18]
        mov  edx, dword ptr [esi + 0x14]
        call {GETFIELD:#x}
        test eax, eax
        je   out
        mov  edi, eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  ebp, eax
    lp:
        dec  ebp
        js   out
        mov  eax, dword ptr [edi + 8]
        mov  ebx, dword ptr [eax + ebp*4]
        test ebx, ebx
        je   lp
        mov  eax, dword ptr [ebx]
        call dword ptr [eax + 0x24]
        cmp  eax, {CID_ARMYHS:#x}
        jne  lp
        cmp  edi, dword ptr [ebx + 4]
        jne  lp
        mov  eax, dword ptr [ebx + 0x1c]
        test eax, eax
        je   lp
        and  byte ptr [eax + 0x11], {0xFF ^ MOVING:#x}
        jmp  lp
    out:
        pop  ebx
        pop  ebp
        pop  edi
        pop  esi
        pop  ecx
        xor  edx, edx
        mov  eax, dword ptr [ebx + 0x18]
        jmp  {RESUME:#x}
    """, va, "ecx", {"HSMAP": VAR_HSMAP})


caves = [("cave_clear", CAVE, build_cave(CAVE))]
hooks = [(HOOK, HOOK_VAN, jmp_to(HOOK, CAVE, len(HOOK_VAN)))]
interior = [(HOOK, HOOK + len(HOOK_VAN), FN, FN_END)]


def selfcheck():
    """The host shapes the cave relies on, read from the live file."""
    d = open(P.TARGET, "rb").read()
    rd = lambda va, n: d[P.va2off(d, va):P.va2off(d, va) + n]
    # both branches read the attacker's hex from [ebx+0xC] +0x14/+0x18/+0x1C through GETFIELD
    for at in (0x55749700, 0x55749833):
        assert rd(at, 3) == bytes.fromhex("8b730c"), "%08X: mov esi,[ebx+0C] moved" % at
    for at in (0x55749715, 0x55749848):
        rel = struct.unpack("<i", rd(at + 1, 4))[0]
        assert rd(at, 1) == b"\xe8" and at + 5 + rel == GETFIELD, "%08X: GetMapField call moved" % at
    assert rd(RESUME, 5) == bytes.fromhex("e883f9fdff"), "resume: call 0x5572928C moved"
    # GetNoneMovingArmyHS's filter, which the cave copies
    assert rd(0x557479F1, 28) == bytes.fromhex(
        "8b03ff5024" "3d17020200" "7512" "3b7b04" "750d" "8b431c" "f6401104" "7504" "8beb"), \
        "GetNoneMovingArmyHS filter moved"
    for _n, va, blob in caves:
        for k in range(len(blob) - 3):
            w = struct.unpack_from("<I", blob, k)[0]
            assert not (P.IMAGE_BASE <= w < 0x55A00000), "%s: absolute in-image dword at +%d" % (_n, k)


def emulate():
    """Run cave_clear from the hook on a fake hex: an own army flagged 05, a neighbour's army
    listed by sprite overlap flagged 05, a non-army child; and with a nil combat record."""
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
                                   UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP)
    d = bytearray(open(P.TARGET, "rb").read())
    for va, van, new in hooks:
        o = P.va2off(d, va)
        assert bytes(d[o:o + len(van)]) in (van, new), "%08X foreign" % va
        d[o:o + len(new)] = new
    IMG, HEAP, STK = P.IMAGE_BASE, 0x10000000, 0x30000000
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    e, secs = P.sections(d)
    top = max(vaddr + max(vsize, rsize) for vsize, vaddr, rsize, raw in secs)
    mu.mem_map(IMG, (top + 0xFFF) & ~0xFFF)
    for vsize, vaddr, rsize, raw in secs:
        mu.mem_write(IMG + vaddr, bytes(d[raw:raw + rsize]))
    for _n, va, blob in caves:
        mu.mem_write(va, blob)
    mu.mem_map(HEAP, 0x10000); mu.mem_map(STK, 0x10000)
    w32 = lambda a, v: mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))
    r8 = lambda a: mu.mem_read(a, 1)[0]
    asm_at = lambda a, src: mu.mem_write(a, P.asm(src, a))
    FIELD, OTHERF, VMTF, VMTA, VMTX = HEAP + 0x100, HEAP + 0x180, HEAP + 0x200, HEAP + 0x280, HEAP + 0x300
    HS1, HS2, OBJ, A1, A2, ITEMS = HEAP + 0x400, HEAP + 0x480, HEAP + 0x500, HEAP + 0x600, HEAP + 0x680, HEAP + 0x700
    HSMAP, MAPOBJ, REC, RES = HEAP + 0x800, HEAP + 0x880, HEAP + 0x900, HEAP + 0x980
    STUBS = HEAP + 0x1000
    # GetMapField thunk -> returns FIELD for (7, 9, 1), else 0; callee pops the level
    asm_at(GETFIELD, f"""
        cmp edx, 7
        jne gf0
        cmp ecx, 9
        jne gf0
        cmp dword ptr [esp + 4], 1
        jne gf0
        mov eax, {FIELD:#x}
        ret 4
    gf0:
        xor eax, eax
        ret 4""")
    asm_at(STUBS, "mov eax, 3\nret"); w32(VMTF + 0x54, STUBS)                       # field count
    asm_at(STUBS + 0x20, f"mov eax, {CID_ARMYHS:#x}\nret"); w32(VMTA + 0x24, STUBS + 0x20)
    asm_at(STUBS + 0x40, "mov eax, 0x12345\nret"); w32(VMTX + 0x24, STUBS + 0x40)
    w32(FIELD, VMTF); w32(FIELD + 8, ITEMS)
    w32(ITEMS, HS1); w32(ITEMS + 4, OBJ); w32(ITEMS + 8, HS2)
    w32(HS1, VMTA); w32(HS1 + 4, FIELD); w32(HS1 + 0x1C, A1)
    w32(HS2, VMTA); w32(HS2 + 4, OTHERF); w32(HS2 + 0x1C, A2)
    w32(OBJ, VMTX)
    mu.mem_write(A1 + 0x11, b"\x05"); mu.mem_write(A2 + 0x11, b"\x05")
    w32(VAR_HSMAP, HSMAP); w32(HSMAP + 0x10, MAPOBJ)          # vanilla: [[0x558FA040]+0x10] = map
    w32(REC, 0); w32(REC + 0x14, 7); w32(REC + 0x18, 9); w32(REC + 0x1C, 1)

    def go(rec_ptr):
        w32(RES + 0xC, rec_ptr); w32(RES + 0x18, 0xFEED)
        for reg, v in ((UC_X86_REG_EBX, RES), (UC_X86_REG_ESI, 0x5151), (UC_X86_REG_EDI, 0xD1D1),
                       (UC_X86_REG_EBP, 0xBEBE), (UC_X86_REG_ECX, 0xC0C0), (UC_X86_REG_EAX, 0x1111),
                       (UC_X86_REG_EDX, 0x2222), (UC_X86_REG_ESP, STK + 0x8000)):
            mu.reg_write(reg, v)
        mu.emu_start(HOOK, RESUME, count=5000)
        got = {n: mu.reg_read(r) for n, r in (("eax", UC_X86_REG_EAX), ("edx", UC_X86_REG_EDX),
               ("ebx", UC_X86_REG_EBX), ("esi", UC_X86_REG_ESI), ("edi", UC_X86_REG_EDI),
               ("ebp", UC_X86_REG_EBP), ("ecx", UC_X86_REG_ECX), ("esp", UC_X86_REG_ESP))}
        ok = (got["eax"] == 0xFEED and got["edx"] == 0 and got["ebx"] == RES and got["esi"] == 0x5151
              and got["edi"] == 0xD1D1 and got["ebp"] == 0xBEBE and got["ecx"] == 0xC0C0
              and got["esp"] == STK + 0x8000)
        return ok, got

    ok1, g1 = go(REC)
    t1 = ok1 and r8(A1 + 0x11) == 0x01 and r8(A2 + 0x11) == 0x05
    print("  own army 05 -> %02X, overlap army 05 -> %02X, registers %s  %s" % (
        r8(A1 + 0x11), r8(A2 + 0x11), "kept" if ok1 else g1, "PASS" if t1 else "FAIL"))
    mu.mem_write(A1 + 0x11, b"\x05")
    ok2, g2 = go(0)
    t2 = ok2 and r8(A1 + 0x11) == 0x05
    print("  nil combat record: nothing touched, registers %s  %s" % ("kept" if ok2 else g2,
                                                                    "PASS" if t2 else "FAIL"))
    w32(REC + 0x14, 8)
    ok3, g3 = go(REC)
    t3 = ok3 and r8(A1 + 0x11) == 0x05
    print("  hex lookup returns nil: nothing touched  %s" % ("PASS" if t3 else "FAIL"))
    return t1 and t2 and t3


if __name__ == "__main__":
    selfcheck()
    if "--emulate" in sys.argv[1:]:
        sys.exit(0 if emulate() else 1)
    run("build_combat_moveflag", hooks, caves, SLOT, interior, argv=sys.argv[1:])
