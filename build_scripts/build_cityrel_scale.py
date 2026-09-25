#!/usr/bin/env python
r"""
build_cityrel_scale.py -- Migrate, Loot and Raze move race relations in proportion to the city.
AoWEPACK.dpl.  Owner's design 2026-09-25.

    M = 10 x (hexes - 1)  +  15 x upgrades  +  5 x wall level

hexes = TCity.GetSize ([[city+8]+0x78], the footprint count), upgrades = level [city+0x4D] - 1
(floored at 0), wall level = [city+0x4C] (0 none / 1 wood / 2 stone).  15 and 5 are the live Upgrade
and Fortify relation bonuses, so a city's improvements count at the rate they were paid for.
Every change is relation(race, acting player) += k:

    action   when                   race    vanilla   now
    Migrate  ordered                old       -15     -5 - M
             completion             new       +10     +0 + M
             cancelled, same turn   old       +15     +5 + M
             cancelled later        old       +10     +0 + M
    Loot     ordered                city's    -30     -20 - M
             cancelled, same turn   city's    +30     +20 + M
             cancelled later        city's    +20     +10 + M
    Raze     success                city's    -30     -20 - M

Upgrade (+15) and Fortify (+5) are unchanged (owner ruling).

MECHANISM.  Every site is `call TRace.GetPlayerRelationValue` followed by a 3-byte `add/sub eax,imm8`.
The call is retargeted to a stub that calls the original and adds or subtracts M; the imm8 becomes
the new baseline.  The production-control object holds the city at [self+0x28]:
    ExecuteProduction 0x557A7F0C (ordered)  self = ESI    stub_neg_esi
    NewTurn           0x557A82A8 (complete) self = EDI    stub_pos_edi
    ExecuteCancelProduction 0x557A88BC      self = EBX    stub_pos_ebx
Raze: TCity.ExecuteRaze 0x557AB414 calls TStructure.ExecuteRaze (returns BL: 1 = razed) and only
then adjusts the relation -- by which time SetRazed has zeroed the walls.  So the base call
(0x557AB41F) goes through stub_raze, which measures M first and parks it in byte 1 of the wrapper's
`push ecx` slot (only byte 0 holds the result flag), then tail-jumps to the base.  stub_razeadj
at the wrapper's Get (0x557AB445) reads it back.  Ziggurat's raze battles reach the wrapper through
cave_razedispatch's `jmp`, which leaves the same stack shape.

Stubs clobber only EAX/ECX/EDX, which the host reloads after each call.  No draw anywhere (no roll).
Slot 0x5584E400-0x5584E4FF, exclusive.  PIC: rel32 calls only.  Surgical --undo.

    python build_scripts/build_cityrel_scale.py            dry run + state
    python build_scripts/build_cityrel_scale.py --apply
    python build_scripts/build_cityrel_scale.py --undo
    python build_scripts/build_cityrel_scale.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True

from aowepack_patch import asm, run

SLOT = (0x5584E400, 0x5584E500)
GETPRV = 0x5574CDFC           # TRace.GetPlayerRelationValue
BASE_RAZE = 0x5575FFC8        # TStructure.ExecuteRaze (EAX self, DL player) -> AL
K_SIZE, K_UPG, K_WALL = 10, 15, 5


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def imm(op, v):
    """3-byte add/sub eax,imm8."""
    return bytes([0x83, {"add": 0xC0, "sub": 0xE8}[op], v & 0xFF])


def build_m(va):
    """EAX = city -> EAX = M.  Clobbers ECX/EDX."""
    return asm(f"""
        movzx ecx, byte ptr [eax + 0x4D]
        dec   ecx
        jge   m_lvl
        xor   ecx, ecx
    m_lvl:
        imul  ecx, ecx, {K_UPG}
        movzx edx, byte ptr [eax + 0x4C]
        imul  edx, edx, {K_WALL}
        add   ecx, edx
        mov   edx, dword ptr [eax + 8]
        movzx edx, byte ptr [edx + 0x78]
        dec   edx
        jle   m_done
        imul  edx, edx, {K_SIZE}
        add   ecx, edx
    m_done:
        mov   eax, ecx
        ret
    """, va)


def build_stub(va, reg, neg, cave_m):
    return asm(f"""
        call  {GETPRV:#x}
        push  eax
        mov   eax, dword ptr [{reg} + 0x28]
        call  {cave_m:#x}
        {"neg eax" if neg else ""}
        pop   edx
        add   eax, edx
        ret
    """, va)


def build_raze(va, cave_m):
    """Entry from the wrapper's `call base`: [esp] ret, [esp+4] the wrapper's result slot."""
    return asm(f"""
        push  eax
        push  edx
        call  {cave_m:#x}
        cmp   eax, 0xFF
        jbe   r_fits
        mov   eax, 0xFF
    r_fits:
        mov   byte ptr [esp + 0xD], al
        pop   edx
        pop   eax
        jmp   {BASE_RAZE:#x}
    """, va)


def build_razeadj(va):
    return asm(f"""
        call  {GETPRV:#x}
        movzx ecx, byte ptr [esp + 5]
        sub   eax, ecx
        ret
    """, va)


def layout():
    caves, va = [], SLOT[0]
    at = {}
    def put(name, fn):
        nonlocal va
        blob = fn(va)
        caves.append((name, va, blob))
        at[name] = va
        va = (va + len(blob) + 0xF) & ~0xF
    put("cave_m", build_m)
    put("stub_neg_esi", lambda v: build_stub(v, "esi", True, at["cave_m"]))
    put("stub_pos_edi", lambda v: build_stub(v, "edi", False, at["cave_m"]))
    put("stub_pos_ebx", lambda v: build_stub(v, "ebx", False, at["cave_m"]))
    put("stub_raze", lambda v: build_raze(v, at["cave_m"]))
    put("stub_razeadj", build_razeadj)
    return at, caves


at, caves = layout()

# (call site, stub, (vanilla op, vanilla imm), (new op, new imm))
SITES = [
    (0x557A80EB, "stub_neg_esi", ("add", -30), ("add", -20)),   # Loot ordered
    (0x557A8243, "stub_neg_esi", ("add", -15), ("add", -5)),    # Migrate ordered
    (0x557A882E, "stub_pos_edi", ("add", 10), ("add", 0)),      # Migrate completion (new race)
    (0x557A8918, "stub_pos_ebx", ("sub", -30), ("sub", -20)),   # Loot cancelled, same turn
    (0x557A8970, "stub_pos_ebx", ("add", 20), ("add", 10)),     # Loot cancelled later
    (0x557A89D3, "stub_pos_ebx", ("sub", -15), ("sub", -5)),    # Migrate cancelled, same turn
    (0x557A8A28, "stub_pos_ebx", ("add", 10), ("add", 0)),      # Migrate cancelled later
    (0x557AB445, "stub_razeadj", ("add", -30), ("add", -20)),   # Raze success
]

hooks = [(s, call_to(s, GETPRV) + imm(*van), call_to(s, at[stub]) + imm(*new))
         for s, stub, van, new in SITES]
hooks.append((0x557AB41F, call_to(0x557AB41F, BASE_RAZE), call_to(0x557AB41F, at["stub_raze"])))

if __name__ == "__main__":
    run("build_cityrel_scale", hooks, caves, SLOT, [])
