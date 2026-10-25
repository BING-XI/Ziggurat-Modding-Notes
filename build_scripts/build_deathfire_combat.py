#!/usr/bin/env python
r"""
build_deathfire_combat.py -- the AoWEPACK half of the two Death/Fire battle spells (owner's design,
05-spells-added.md "Death/Fire -- the first pair"): registration, parameters, and Taint the
Flame's auto-combat and AI value overrides.  AoWTCPCK half: build_deathfire_tc.py.  Data:
build_deathfire_pfs.py.  Dual-sphere groundwork: build_dual_sphere.py (both ids are in its table).

TAINT THE FLAME  id 80, a TDeathRay instance (a plain TCombatSpell): ATK 12, DMG 12, Death (0x20),
  1 shot, range 0xFF, side 2, against RES; sphere 7 (dual), tier 1, mana 8, research 80.
  It gets a RUN-TIME COPY of TDeathRay's VMT (GetMem, VMT-0x40..+0x9C; parent stays TCombatSpell)
  with five slots replaced -- a unit "qualifies" when it holds Burning 0x7F, Living Flame 0x52 or
  the Living Flame enchantment 0xA3 (combat VMT +0xA8, item-aware; walls answer 0):
    +0x80 GetCombatDamageValue / +0x84 ...Ex   0 for a unit that does not qualify (manual-combat
          AI: EvalBattle's gates and Sacred Wrath's EvalAll then sum qualifying enemies minus
          qualifying own units -- the value-weighted reading of "more targets than its own side")
    +0x98 fcGetDamageValueEx                   the same, for auto-combat
    +0x90 fcPrefetchCombatCommands             queues commands only when the enemy side holds more
          qualifying units than the caster's side (then the original, which now values only
          qualifying enemies)
    +0x94 fcExecuteCombatCommand               every qualifying unit on both sides takes one CA;
          the first carries the hero flag (mana)
PILLAR OF BANEFIRE  id 81, a TFireBall instance (a plain TCombatSpell): ATK 10, DMG 15, Death + Fire
  + Wall (0x0121), 2 shots (= two CAs per target in auto-combat), range 8, 3 extra auto-combat
  targets (4 in all), side 2, against RES; sphere 7, tier 2, mana 16, research 160.
Both: caster family 1 (Evoker), category and combat flag from TCombatSpell.Create.  Spells.pfs
tags 0xD/0xE/0xF/0x10/0x11/0x12 override mana, upkeep, research, sphere, tier and family on load.

SITE  0x557FA828  RegisterCombatSpells' last direct `call RegisterSpell` (Shock Wave's; EBX = the
      control) -> cave_reg: replays it, then builds and registers both spells.
      A package-init cave: proved only by launching the exe.
Slot 0x558B6800-0x558B6FFF, exclusive.  PIC.  No RNG (the CAs roll in combat: P2 COMBAT RAW).

    python build_scripts/build_deathfire_combat.py            dry run + state
    python build_scripts/build_deathfire_combat.py --apply
    python build_scripts/build_deathfire_combat.py --undo
    python build_scripts/build_deathfire_combat.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic, ansistr

TAINT_ID, PILLAR_ID = 80, 81
DUAL_SPHERE = 7
SLOT = (0x558B6800, 0x558B7000)

REGISTER_SPELL, LSTRASG, GETMEM = 0x55779B40, 0x55701150, 0x55701008
DEATHRAY_CELL, DEATHRAY_CREATE = 0x557F46A0, 0x557F82B0
FIREBALL_CELL, FIREBALL_CREATE = 0x557F5618, 0x557F8FD4
ORIG_VAL, ORIG_VALEX = 0x557F7268, 0x557F7324
ORIG_FCPRE, ORIG_FCEXEC, ORIG_FCVAL = 0x557F76BC, 0x557F7838, 0x557F7464
GETOBJECTS, GETSIDE, EXEC_CA = 0x55726DBC, 0x55726660, 0x55727224
VMT_NEG, VMT_SLOTS = 0x40, 0x9C
BURNING, LIVING_FLAME, LIVING_FLAME_ENCH = 0x7F, 0x52, 0xA3

H_REG = 0x557FA828
A = {}            # cave name -> VA, filled by layout()


def rel(src, dst, op):
    return bytes([op]) + struct.pack("<i", dst - (src + 5))


def c_qualifies(va):
    # in: eax = combat object; out: eax = 1 if it holds Burning or Living Flame, else 0.
    return asm(f"""
        push ebx
        mov  ebx, eax
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        mov  edx, {BURNING:#x}
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  Lyes
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        mov  edx, {LIVING_FLAME:#x}
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  Lyes
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        mov  edx, {LIVING_FLAME_ENCH:#x}
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  Lyes
        xor  eax, eax
        pop  ebx
        ret
    Lyes:
        mov  eax, 1
        pop  ebx
        ret
    """, va)


def c_val(va):
    # +0x80 GetCombatDamageValue(eax spell, edx, ecx target): 0 for a non-qualifier.
    return asm(f"""
        push eax
        push edx
        push ecx
        mov  eax, ecx
        call {A['qualifies']:#x}
        test eax, eax
        pop  ecx
        pop  edx
        pop  eax
        je   Lzero
        jmp  {ORIG_VAL:#x}
    Lzero:
        xor  eax, eax
        ret
    """, va)


def c_zeroed(va, orig, out_at, popn):
    # A DV-struct method whose out pointer is [esp+out_at] at entry: zero 0x14 bytes for a
    # non-qualifier and return (ret popn), else go on to the original.
    return asm(f"""
        push eax
        push edx
        push ecx
        mov  eax, ecx
        call {A['qualifies']:#x}
        test eax, eax
        pop  ecx
        pop  edx
        pop  eax
        je   Lzero
        jmp  {orig:#x}
    Lzero:
        push edi
        mov  edi, dword ptr [esp + {out_at + 4:#x}]
        xor  eax, eax
        mov  dword ptr [edi], eax
        mov  dword ptr [edi + 4], eax
        mov  dword ptr [edi + 8], eax
        mov  dword ptr [edi + 0xc], eax
        mov  dword ptr [edi + 0x10], eax
        pop  edi
        ret  {popn:#x}
    """, va)


def c_count(va):
    # in: eax = TCombatSide; out: eax = its live, enabled, qualifying objects.
    return asm(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        xor  edi, edi
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  esi, eax
    Lloop:
        dec  esi
        js   Ldone
        mov  eax, ebx
        mov  edx, esi
        call {GETOBJECTS:#x}
        test eax, eax
        je   Lloop
        test byte ptr [eax + 0x47], 1
        jne  Lloop
        push eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        pop  eax
        je   Lloop
        call {A['qualifies']:#x}
        test eax, eax
        je   Lloop
        inc  edi
        jmp  Lloop
    Ldone:
        mov  eax, edi
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


def c_fcpre(va):
    # +0x90 (eax spell, edx context: +4 caster, +8 TFastCombat, +0xC enemy side).
    return asm(f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        mov  eax, dword ptr [edi + 0xc]
        call {A['count']:#x}
        mov  ebx, eax
        mov  eax, dword ptr [edi + 4]
        call {GETSIDE:#x}
        movzx eax, al
        and  eax, 0x7f
        mov  edx, dword ptr [edi + 8]
        mov  eax, dword ptr [edx + eax*4 + 0x1c]
        call {A['count']:#x}
        cmp  ebx, eax
        mov  eax, esi
        mov  edx, edi
        pop  edi
        pop  esi
        pop  ebx
        jg   Lgo
        ret
    Lgo:
        jmp  {ORIG_FCPRE:#x}
    """, va)


def c_fcexec(va):
    # +0x94 (eax spell, edx context, ecx command) -> al = 1.  Every qualifying unit on both sides.
    return asm(f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x10
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp - 4], eax
        mov  dword ptr [ebp - 8], edx
        xor  eax, eax
        mov  dword ptr [ebp - 0xc], eax
        mov  dword ptr [ebp - 0x10], eax
    Lside:
        mov  edx, dword ptr [ebp - 8]
        mov  edx, dword ptr [edx + 8]
        mov  eax, dword ptr [ebp - 0x10]
        mov  esi, dword ptr [edx + eax*4 + 0x1c]
        test esi, esi
        je   Lnext
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  edi, eax
    Lobj:
        dec  edi
        js   Lnext
        mov  eax, esi
        mov  edx, edi
        call {GETOBJECTS:#x}
        mov  ebx, eax
        test ebx, ebx
        je   Lobj
        test byte ptr [ebx + 0x47], 1
        jne  Lobj
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   Lobj
        mov  eax, ebx
        call {A['qualifies']:#x}
        test eax, eax
        je   Lobj
        cmp  dword ptr [ebp - 0xc], 0
        sete al
        push eax
        mov  ecx, ebx
        mov  edx, dword ptr [ebp - 8]
        mov  eax, dword ptr [ebp - 4]
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0x78]
        mov  ebx, eax
        mov  edx, eax
        mov  eax, dword ptr [ebp - 8]
        mov  eax, dword ptr [eax + 8]
        call {EXEC_CA:#x}
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
        inc  dword ptr [ebp - 0xc]
        jmp  Lobj
    Lnext:
        inc  dword ptr [ebp - 0x10]
        cmp  dword ptr [ebp - 0x10], 2
        jl   Lside
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        mov  al, 1
        ret
    """, va)


def c_reg(va):
    t_name = ansistr("Taint the Flame")
    tail = t_name + ansistr("Pillar of Banefire")
    src = f"""
        call {REGISTER_SPELL:#x}
        push esi
        push edi
        {{ANC}}
        mov  eax, dword ptr [esi + {{DRCELL}}]
        xor  ecx, ecx
        mov  dl, 1
        call {DEATHRAY_CREATE:#x}
        mov  edi, eax
        lea  eax, [edi + 8]
        lea  edx, [esi + {{NTAINT}}]
        call {LSTRASG:#x}
        mov  dword ptr [edi + 0x10], {TAINT_ID}
        mov  dword ptr [edi + 0x14], 8
        mov  dword ptr [edi + 0x18], 80
        mov  dword ptr [edi + 0x1c], 0
        mov  byte ptr [edi + 0x20], {DUAL_SPHERE}
        mov  byte ptr [edi + 0x21], 1
        mov  byte ptr [edi + 0x23], 1
        mov  byte ptr [edi + 0x34], 12
        mov  byte ptr [edi + 0x35], 12
        mov  word ptr [edi + 0x36], 0x20
        mov  byte ptr [edi + 0x38], 1
        mov  byte ptr [edi + 0x39], 0xff
        mov  byte ptr [edi + 0x3b], 2
        mov  byte ptr [edi + 0x3c], 1
        mov  eax, {VMT_NEG + VMT_SLOTS:#x}
        call {GETMEM:#x}
        mov  edx, eax
        push esi
        push edi
        mov  esi, dword ptr [edi]
        sub  esi, {VMT_NEG:#x}
        mov  edi, edx
        mov  ecx, {(VMT_NEG + VMT_SLOTS) // 4:#x}
        cld
        rep movsd dword ptr es:[edi], dword ptr [esi]
        pop  edi
        pop  esi
        add  edx, {VMT_NEG:#x}
        lea  eax, [esi + {{TVAL}}]
        mov  dword ptr [edx + 0x80], eax
        lea  eax, [esi + {{TVALEX}}]
        mov  dword ptr [edx + 0x84], eax
        lea  eax, [esi + {{TFCPRE}}]
        mov  dword ptr [edx + 0x90], eax
        lea  eax, [esi + {{TFCEXEC}}]
        mov  dword ptr [edx + 0x94], eax
        lea  eax, [esi + {{TFCVAL}}]
        mov  dword ptr [edx + 0x98], eax
        mov  dword ptr [edi], edx
        mov  edx, edi
        mov  eax, ebx
        call {REGISTER_SPELL:#x}
        mov  eax, dword ptr [esi + {{FBCELL}}]
        xor  ecx, ecx
        mov  dl, 1
        call {FIREBALL_CREATE:#x}
        mov  edi, eax
        lea  eax, [edi + 8]
        lea  edx, [esi + {{NPILLAR}}]
        call {LSTRASG:#x}
        mov  dword ptr [edi + 0x10], {PILLAR_ID}
        mov  dword ptr [edi + 0x14], 16
        mov  dword ptr [edi + 0x18], 160
        mov  dword ptr [edi + 0x1c], 0
        mov  byte ptr [edi + 0x20], {DUAL_SPHERE}
        mov  byte ptr [edi + 0x21], 2
        mov  byte ptr [edi + 0x23], 1
        mov  byte ptr [edi + 0x34], 10
        mov  byte ptr [edi + 0x35], 15
        mov  word ptr [edi + 0x36], 0x121
        mov  byte ptr [edi + 0x38], 2
        mov  byte ptr [edi + 0x39], 8
        mov  byte ptr [edi + 0x3a], 3
        mov  byte ptr [edi + 0x3b], 2
        mov  byte ptr [edi + 0x3c], 1
        mov  edx, edi
        mov  eax, ebx
        call {REGISTER_SPELL:#x}
        pop  edi
        pop  esi
        ret
    """
    return pic(src, va, "esi",
               {"DRCELL": DEATHRAY_CELL, "FBCELL": FIREBALL_CELL,
                "TVAL": A["val"], "TVALEX": A["valex"], "TFCPRE": A["fcpre"],
                "TFCEXEC": A["fcexec"], "TFCVAL": A["fcval"],
                "NTAINT": ("TAIL", 8), "NPILLAR": ("TAIL", len(t_name) + 8)}, tail)


BUILDERS = [   # name, builder; laid out in this order, 16-byte aligned
    ("qualifies", c_qualifies),
    ("val", c_val),
    ("valex", lambda va: c_zeroed(va, ORIG_VALEX, 4, 4)),
    ("fcval", lambda va: c_zeroed(va, ORIG_FCVAL, 8, 8)),
    ("count", c_count),
    ("fcpre", c_fcpre),
    ("fcexec", c_fcexec),
    ("reg", c_reg),
]


def layout():
    # two passes: sizes do not depend on targets beyond rel32/disp32, so the second pass is stable
    for _ in range(2):
        va, blobs = SLOT[0], []
        for name, b in BUILDERS:
            A.setdefault(name, va)
            A[name] = va
            blob = b(va)
            blobs.append((name, va, blob))
            va = (va + len(blob) + 15) & ~15
    return blobs


def main():
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    for cell, vmt_want in ((DEATHRAY_CELL, 0x557F46E0), (FIREBALL_CELL, 0x557F5658)):
        assert struct.unpack_from("<I", d, P.va2off(d, cell))[0] == vmt_want, "class cell moved"
    hooks = [(H_REG, rel(H_REG, REGISTER_SPELL, 0xE8), rel(H_REG, A["reg"], 0xE8))]
    run("build_deathfire_combat -- Taint the Flame + Pillar of Banefire (AoWEPACK)", hooks, blobs,
        SLOT, [])


if __name__ == "__main__":
    main()
