#!/usr/bin/env python
r"""
build_liquidbody.py -- Liquid Body (ability 0xBA), a plain passive for Water Elementals and the
like: Swimming, Physical Protection and no Burning, in one ability.  AoWEPACK.dpl.  Owner's
design 2026-09-25.

WHY NOT LIQUID FORM (0xA6)
    Liquid Form already grants Swimming + Physical Protection, but it is a spell enchantment
    (TUnitEnchantmentAbility): its Ability.pfs mask is 0 so the editor will not offer it,
    TUnitEnchantmentAbility.GetSourceName @0x55765784 dereferences the cast record without a nil
    check (a unit that merely starts with it has no cast record), and Magebane counts it as an
    enchantment.  Liquid Body is an ordinary TEnhancementAbility, like the Weaknesses.

WHAT IT DOES
    Swimming   TAbilityOwner.GetAbMoveTypesAll: the Swimming/Water Walking/Liquid Form test
               (last query 0xA6 at 0x5574F80B) also accepts 0xBA.
    Phys Prot  TAbilityOwner.GetAbProtectionTypesAll: the Physical Protection test (last query
               0xA6 at 0x5574F9A3) also accepts 0xBA.
    Burning    TAbstractUnit.ExecuteCombatDamageEffects @0x55781ED8 is the one place Burning (0x7F)
               is added: fire bit 0 of the effect mask, after `~immunity & mask`.  A unit with 0xBA
               skips that block.  Every fire source reaches it through TDamageCA (melee, ranged,
               spells, fire hexes), tactical and auto-resolve alike.  Fire damage itself is
               untouched, and there is no lava walking (that is Fire Immunity's move type).
               The fire roll upstream still happens, so the draw count is unchanged.

REGISTRATION (package init -- ⚠ prove by launching the exe)
    CreateEnhancementAbility 0x5576601C (EAX id, EDX name, CX mask) + RegisterAbility 0x55750238,
    spliced at the vanilla `call RegisterAbility` 0x557BCDC6 in PassiveAb.RegisterPassiveAbilities
    (the Crusader registration; EBX = the control), replayed first.  Name literal read through a
    call/pop anchor.  Mask 0x0201 = astUnit | astEditor: assignable to units in the editor only.
    Record (description, mask): build_liquidbody_pfs.py.  Ceilings: LADDER 0xBB in
    build_abilityid_ceilings.py and build_tcablist_ceiling.py.

HOOKS (vanilla bytes asserted, no .reloc under any)
    R  0x557BCDC6  call RegisterAbility -> call cave_reg
    M  0x5574F80B  call [ecx+0x88] (6 B) -> call cave_or + nop     (EAX owner, EDX 0xA6)
    P  0x5574F9A3  call [ecx+0x88] (6 B) -> call cave_or + nop     (same cave)
    B  0x55781F0D  test bl,1 / je 0x55781F3F (5 B) -> jmp cave_burn

Slot 0x5584E200-0x5584E3FF, exclusive.  PIC: rel32, register-relative, one call/pop anchor.
Surgical --undo.

    python build_scripts/build_liquidbody.py            dry run + state
    python build_scripts/build_liquidbody.py --apply
    python build_scripts/build_liquidbody.py --undo
    python build_scripts/build_liquidbody.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584E200, 0x5584E400)
CAVE = 0x5584E200
ABIL_ID = 0xBA
NAME = "Liquid Body"
MASK = 0x0201
LIQUID_FORM = 0xA6
BURNING = 0x7F

CEA, REGISTER = 0x5576601C, 0x55750238
R_SITE = 0x557BCDC6
M_SITE, P_SITE = 0x5574F80B, 0x5574F9A3
Q_VAN = bytes.fromhex("ff9188000000")                 # call dword ptr [ecx+0x88]
B_SITE, B_FIRE, B_NEXT = 0x55781F0D, 0x55781F12, 0x55781F3F
B_VAN = bytes.fromhex("f6c301742d")                   # test bl,1 / je 0x55781F3F


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def ansistr(s):
    b = s.encode("latin1")
    return struct.pack("<iI", -1, len(b)) + b + b"\0"


def build_or(va):
    """Replaces the host's query for 0xA6: AL = has(0xA6) or has(0xBA), self-only VMT +0x88 as the
    host uses.  The owner comes in EAX and is kept on the stack across the first call."""
    return asm(f"""
        push eax
        call dword ptr [ecx + 0x88]
        test al, al
        pop  edx
        jne  o_done
        mov  eax, edx
        mov  edx, {ABIL_ID:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x88]
    o_done:
        ret
    """, va)


def build_burn(va):
    """ESI = the unit, BX = surviving effect bits.  Fire bit set and no Liquid Body -> the host's
    Burning block; otherwise the next branch.  Clobbers EAX/ECX/EDX, which both targets reload."""
    return asm(f"""
        test bl, 1
        je   {B_NEXT:#x}
        mov  eax, esi
        mov  edx, {ABIL_ID:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  {B_NEXT:#x}
        jmp  {B_FIRE:#x}
    """, va)


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
    put("cave_or", build_or(va))
    put("cave_burn", build_burn(va))
    put("cave_reg", build_reg(va))
    return {n: v for n, v, _b in caves}, caves


def check_id():
    """0xBA must be free: no other CreateEnhancementAbility idiom registers it or anything above
    it, and Ability.pfs has no record for it unless it is ours (a DevEd save keeps it)."""
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
    other = [i for i, src in used if i < 0x100 and not lo <= src < hi]
    if max(other) >= ABIL_ID:
        sys.exit("ABORT: something else registers %#x -- re-derive ABIL_ID" % max(other))
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "re_tools"))
    import pfs
    keys = {rid - 10 for rid, _b in pfs.load("ability.pfs")[0]}
    print("  id %#x free (highest other CreateEnhancementAbility id %#x); Ability.pfs record %s"
          % (ABIL_ID, max(other), "present" if ABIL_ID in keys else "absent"))


at, caves = layout()
hooks = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, at["cave_reg"])),
         (M_SITE, Q_VAN, call_to(M_SITE, at["cave_or"]) + b"\x90"),
         (P_SITE, Q_VAN, call_to(P_SITE, at["cave_or"]) + b"\x90"),
         (B_SITE, B_VAN, jmp_to(B_SITE, at["cave_burn"], 5))]
interior = [(B_SITE, B_SITE + 5, 0x55781ED8, 0x55782038)]

if __name__ == "__main__":
    check_id()
    run("build_liquidbody", hooks, caves, SLOT, interior)
