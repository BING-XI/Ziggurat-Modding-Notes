#!/usr/bin/env python
r"""
build_wotw.py -- the AoWEPACK half of Weight of the World (spell 91), an Earth tier-2 battle spell:
one strike on every unit within 6 hexes of the target, friend and foe, then a battle-long field.
Manual combat (the cast, the strike loop, the field mark, the AI, the preview): build_wotw_tc.py.
The field's rules: build_wotw_field.py + build_wotw_field_tc.py.  Its animation: build_wotw_anim.py.
Data: build_wotw_pfs.py.  Owner's design 2026-10-26 (05-spells-added.md, "Entangle to Life/Earth,
Weight of the World -- agreed design"; AoWx's Gravity Well made a pure Earth spell and renamed).

THE SPELL  a TTremors instance (a plain TCombatSpell; its VMT matches TFireBall's and TDeathRay's from
  +0x70 to +0x98), registered at 0x557FA7E3 (Animate Dead's `call RegisterSpell` in
  RegisterCombatSpells, EBX = the control, replayed first).  Mana 10, research 80, upkeep 0, sphere 3
  (Earth), tier 2, caster family 1 (Evoker) at +0x23; ATK 14 / DMG 4 at +0x34/+0x35, damage types
  0x0080 (Physical) at +0x36, 1 shot, range 8, auto-combat extras 0x7F at +0x3A, side 2, +0x3C 0
  (rolls against Defence).
  Auto-combat (vanilla fcExecuteCombatCommand): the target and every eligible unit on its side
  (alive, not fully immune, in reach) -- enemy units only (owner).  Walls cannot be hurt: their
  immunity is everything but dtWall.
  Its RUN-TIME VMT copy (VMT-0x40..+0x9C; parent stays TCombatSpell) wraps three slots so a target
  that flies, floats or wind-walks by nature takes DMG 6 instead of 4 (+50 %, owner): the spell's DMG
  byte is raised for the call and restored after it.
    +0x78 CreateCA (the roll: manual landing and auto-combat), +0x84 GetCombatDamageValueEx (the
    manual AI), +0x98 fcGetDamageValueEx (auto-combat's value; out record at [esp+4], ret 8).
  Airborne = a TCombatUnit whose unit holds Flying (1), Floating (0x3B) or Wind Walking (0xA5)
  through the unit's own +0x148 (item-aware; build_airwater_ench.py counts Mistform as Floating) --
  NOT the combat +0xA8, which build_wotw_field_tc.py's grounding answers for units in a field.
RNG: none here (the strikes roll in their CAs: manual combat reseeds per unit, build_wotw_tc.py;
auto-combat P2 COMBAT RAW, vanilla's own extra-target picks).
Slot 0x558C0000-0x558C0FFF, exclusive.  PIC.  Surgical --undo.  The registration runs at package init:
proved only by launching the exe.

    python build_scripts/build_wotw.py            dry run + state
    python build_scripts/build_wotw.py --apply
    python build_scripts/build_wotw.py --undo
    python build_scripts/build_wotw.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic, ansistr

WOTW, NAME = 91, "Weight of the World"
MANA, RESEARCH, SPHERE, TIER, FAMILY = 10, 80, 3, 2, 1
ATK, DMG, TYPES, SHOTS, RANGE, EXTRAS = 14, 4, 0x0080, 1, 8, 0x7F
AIRBORNE = (0x01, 0x3B, 0xA5)
SLOT = (0x558C0000, 0x558C1000)
REGISTER_SPELL, LSTRASG, GETMEM, ISCLASS = 0x55779B40, 0x55701150, 0x55701008, 0x557010C0
TREMORS_CELL, TREMORS_CREATE, TREMORS_VMT = 0x557F50C0, 0x557F8C74, 0x557F5100
ORIG = {"createca": (0x557F72C0, 1), "valex": (0x557F7324, 1), "fcval": (0x557F7464, 2)}
SLOT_OF = {"createca": 0x78, "valex": 0x84, "fcval": 0x98}
TCU_CELL = 0x55715A54                     # TCombatUnit VMT - 0x40 (its self pointer)
VMT_NEG, VMT_SLOTS = 0x40, 0x9C
H_REG = 0x557FA7E3
A = {}


def c_air(va):
    """eax = a combat object -> eax 1 when it is a TCombatUnit whose unit flies, floats or wind-walks."""
    tests = "".join(f"""
        mov  eax, ebx
        mov  edx, {i:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  a_yes""" for i in AIRBORNE)
    src = f"""
        push ebx
        push esi
        mov  ebx, eax
        test ebx, ebx
        je   a_no
        {{ANC}}
        mov  eax, ebx
        mov  edx, dword ptr [esi + {{TCU}}]
        call {ISCLASS:#x}
        test al, al
        je   a_no
        mov  ebx, dword ptr [ebx + 0x4c]
        test ebx, ebx
        je   a_no
        {tests}
    a_no:
        xor  eax, eax
        pop  esi
        pop  ebx
        ret
    a_yes:
        mov  eax, 1
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "esi", {"TCU": TCU_CELL})


def c_swap(va, orig, nargs):
    """VMT wrapper (eax spell, edx caster, ecx target, nargs stack dwords): DMG x 1.5 for the call when
    the target is airborne, restored after; ret 4 * nargs."""
    pushes = "\n".join("        push dword ptr [esp + %#x]" % (0x8 + 4 * nargs) for _ in range(nargs))
    return asm(f"""
        push ebx
        push esi
        mov  ebx, eax
        movzx esi, byte ptr [ebx + 0x35]
        push eax
        push edx
        push ecx
        mov  eax, ecx
        call {A['air']:#x}
        test al, al
        pop  ecx
        pop  edx
        pop  eax
        je   s_call
        push edx
        mov  edx, esi
        shr  edx, 1
        add  edx, esi
        mov  byte ptr [ebx + 0x35], dl
        pop  edx
    s_call:
{pushes}
        call {orig:#x}
        push edx
        mov  edx, esi
        mov  byte ptr [ebx + 0x35], dl
        pop  edx
        pop  esi
        pop  ebx
        ret  {4 * nargs:#x}
    """, va)


def c_reg(va):
    src = f"""
        call {REGISTER_SPELL:#x}
        push esi
        push edi
        {{ANC}}
        mov  eax, dword ptr [esi + {{CELL}}]
        xor  ecx, ecx
        mov  dl, 1
        call {TREMORS_CREATE:#x}
        mov  edi, eax
        lea  eax, [edi + 8]
        lea  edx, [esi + {{NAME}}]
        call {LSTRASG:#x}
        mov  dword ptr [edi + 0x10], {WOTW}
        mov  dword ptr [edi + 0x14], {MANA}
        mov  dword ptr [edi + 0x18], {RESEARCH}
        mov  dword ptr [edi + 0x1c], 0
        mov  byte ptr [edi + 0x20], {SPHERE}
        mov  byte ptr [edi + 0x21], {TIER}
        mov  byte ptr [edi + 0x23], {FAMILY}
        mov  byte ptr [edi + 0x34], {ATK}
        mov  byte ptr [edi + 0x35], {DMG}
        mov  word ptr [edi + 0x36], {TYPES:#x}
        mov  byte ptr [edi + 0x38], {SHOTS}
        mov  byte ptr [edi + 0x39], {RANGE}
        mov  byte ptr [edi + 0x3a], {EXTRAS:#x}
        mov  byte ptr [edi + 0x3b], 2
        mov  byte ptr [edi + 0x3c], 0
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
        lea  eax, [esi + {{CCA}}]
        mov  dword ptr [edx + 0x78], eax
        lea  eax, [esi + {{VALEX}}]
        mov  dword ptr [edx + 0x84], eax
        lea  eax, [esi + {{FCVAL}}]
        mov  dword ptr [edx + 0x98], eax
        mov  dword ptr [edi], edx
        mov  edx, edi
        mov  eax, ebx
        call {REGISTER_SPELL:#x}
        pop  edi
        pop  esi
        ret
    """
    return pic(src, va, "esi", {"CELL": TREMORS_CELL, "CCA": A["createca"], "VALEX": A["valex"],
                                "FCVAL": A["fcval"], "NAME": ("TAIL", 8)}, ansistr(NAME))


BUILDERS = [("air", c_air)] + [(n, (lambda n: lambda va: c_swap(va, *ORIG[n]))(n)) for n in ORIG] + [("reg", c_reg)]


def layout():
    for name, _b in BUILDERS:
        A.setdefault(name, SLOT[0] + 0x800)
    for _ in range(3):
        va, blobs = SLOT[0], []
        for name, b in BUILDERS:
            A[name] = va
            blob = b(va)
            blobs.append(("cave_" + name, va, blob))
            va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    return blobs


def checks(d):
    u = lambda v: struct.unpack_from("<I", d, P.va2off(d, v))[0]
    rb = lambda va, n: bytes(d[P.va2off(d, va):P.va2off(d, va) + n])
    vmt = u(TREMORS_CELL)
    p = P.va2off(d, u(vmt - 0x20))
    if vmt != TREMORS_VMT or d[p + 1:p + 1 + d[p]] != b"TTremors" or u(vmt - 0x20) - vmt != VMT_SLOTS:
        sys.exit("ABORT: TTremors' class cell / VMT moved")
    for n, (orig, _k) in ORIG.items():
        if u(vmt + SLOT_OF[n]) != orig:
            sys.exit("ABORT: TTremors VMT +%#x is not %08X" % (SLOT_OF[n], orig))
    if rb(H_REG - 2, 2) != b"\x8b\xc3":
        sys.exit("ABORT: `mov eax,ebx` is not before %08X" % H_REG)
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:            # nobody else creates spell 91
        for i in range(ra, ra + rs - 7):
            src = P.IMAGE_BASE + sva + (i - ra)
            if SLOT[0] <= src < SLOT[1]:
                continue
            if d[i] == 0xC7 and d[i + 1] in range(0x40, 0x48) and d[i + 2] == 0x10 \
                    and struct.unpack_from("<I", d, i + 3)[0] == WOTW:
                sys.exit("ABORT: %08X also stores spell id %d" % (src, WOTW))


def main():
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d)
    rel = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
    hooks = [(H_REG, rel(H_REG, REGISTER_SPELL), rel(H_REG, A["reg"]))]
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    run("build_wotw -- Weight of the World (AoWEPACK)", hooks, blobs, SLOT, [])


if __name__ == "__main__":
    main()
