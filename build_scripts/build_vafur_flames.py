#!/usr/bin/env python
r"""
build_vafur_flames.py -- the AoWEPACK half of Vafur Flames (id 97), a Fire tier-2 battle spell: a
jagged wall of fire up to 6 hexes long whose flames strike with a 10/5 fire strike.  The wall, its
flames and their strikes: build_vafur_flames_tc.py.  Data: build_vafur_flames_pfs.py.  Owner's design
2026-10-29 (05-spells-added.md, "Vafur Flames").

THE SPELL  a TDeathRay instance (a plain TCombatSpell, Mist's recipe), registered at 0x557FA7CC (the
  last direct `call RegisterSpell` in RegisterCombatSpells, EBX = the control, replayed first).  Mana
  7, research 80 (Fire Breath's, the Fire tier-2 battle spell), upkeep 0, sphere 5 (Fire), tier 2,
  caster family 1 (Evoker) at +0x23; ATK 10 / DMG 5 at +0x34/+0x35, damage types 0x0001 (Fire) at
  +0x36, 1 shot, range 8 (Triple Fireball's live range, as for Weight of the World), no auto-combat
  extras, side 2, +0x3C 0 (the strike rolls against Defence).  The manual battle's strikes use
  TCombatSpell.CreateCA (+0x78), so Fire Immunity, Fire Protection and the fire strike's Burning
  roll are the generic handlers'.
  Its RUN-TIME VMT copy (VMT-0x40..+0x9C; parent stays TCombatSpell) keeps it out of both AIs and
  out of auto-resolve (owner: not cast in auto-combat; the battle AI never casts it):
    +0x80 GetCombatDamageValue    0
    +0x84 ...Ex                   the out record zeroed (ret 4)
    +0x90 fcPrefetchCombatCommands  queues nothing
    +0x94 fcExecuteCombatCommand    does nothing, AL = 1
    +0x98 fcGetDamageValueEx      the out record zeroed (ret 8)
RNG: none.  Slot 0x558C8800-0x558C8BFF, exclusive.  PIC.  Surgical --undo.  The registration runs at
package init: proved only by launching the exe.

    python build_scripts/build_vafur_flames.py            dry run + state
    python build_scripts/build_vafur_flames.py --apply
    python build_scripts/build_vafur_flames.py --undo
    python build_scripts/build_vafur_flames.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic, ansistr

VAFUR_ID, VAFUR_NAME = 97, "Vafur Flames"
MANA, RESEARCH, SPHERE, TIER, FAMILY = 7, 80, 5, 2, 1
ATK, DMG, TYPES, SHOTS, RANGE = 10, 5, 0x0001, 1, 8
SLOT = (0x558C8800, 0x558C8C00)
REGISTER_SPELL, LSTRASG, GETMEM = 0x55779B40, 0x55701150, 0x55701008
DEATHRAY_CELL, DEATHRAY_CREATE, DEATHRAY_VMT = 0x557F46A0, 0x557F82B0, 0x557F46E0
VMT_NEG, VMT_SLOTS = 0x40, 0x9C
H_REG = 0x557FA7CC
A = {}


def c_val(va):
    return asm("""
        xor  eax, eax
        ret
    """, va)


def c_zeroed(va, out_at, popn):
    """A DV-record method whose out pointer is [esp+out_at] at entry: zero 0x14 bytes, ret popn."""
    return asm(f"""
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


def c_fcpre(va):
    return asm("ret", va)


def c_fcexec(va):
    return asm("""
        mov  al, 1
        ret
    """, va)


def c_reg(va):
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
        lea  edx, [esi + {{NAME}}]
        call {LSTRASG:#x}
        mov  dword ptr [edi + 0x10], {VAFUR_ID}
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
        mov  byte ptr [edi + 0x3a], 0
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
        lea  eax, [esi + {{VAL}}]
        mov  dword ptr [edx + 0x80], eax
        lea  eax, [esi + {{VALEX}}]
        mov  dword ptr [edx + 0x84], eax
        lea  eax, [esi + {{FCPRE}}]
        mov  dword ptr [edx + 0x90], eax
        lea  eax, [esi + {{FCEXEC}}]
        mov  dword ptr [edx + 0x94], eax
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
    return pic(src, va, "esi", {"DRCELL": DEATHRAY_CELL, "VAL": A["val"], "VALEX": A["valex"],
                                "FCPRE": A["fcpre"], "FCEXEC": A["fcexec"], "FCVAL": A["fcval"],
                                "NAME": ("TAIL", 8)}, ansistr(VAFUR_NAME))


BUILDERS = [("val", c_val), ("valex", lambda va: c_zeroed(va, 4, 4)),
            ("fcval", lambda va: c_zeroed(va, 4, 8)), ("fcpre", c_fcpre), ("fcexec", c_fcexec),
            ("reg", c_reg)]


def layout():
    for name, _b in BUILDERS:
        A.setdefault(name, SLOT[0] + 0x200)
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
    if u(DEATHRAY_CELL) != DEATHRAY_VMT or u(DEATHRAY_VMT - 0x20) - DEATHRAY_VMT != VMT_SLOTS:
        sys.exit("ABORT: TDeathRay's class cell or VMT size moved")
    if rb(H_REG - 2, 2) != b"\x8b\xc3":
        sys.exit("ABORT: `mov eax,ebx` is not before %08X" % H_REG)
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:            # nobody else creates spell 97
        for i in range(ra, ra + rs - 7):
            src = P.IMAGE_BASE + sva + (i - ra)
            if SLOT[0] <= src < SLOT[1]:
                continue
            if d[i] == 0xC7 and d[i + 1] in range(0x40, 0x48) and d[i + 2] == 0x10 \
                    and struct.unpack_from("<I", d, i + 3)[0] == VAFUR_ID:
                sys.exit("ABORT: %08X also stores spell id %d" % (src, VAFUR_ID))


def main():
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d)
    rel = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
    hooks = [(H_REG, rel(H_REG, REGISTER_SPELL), rel(H_REG, A["reg"]))]
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    run("build_vafur_flames -- Vafur Flames (AoWEPACK)", hooks, blobs, SLOT, [])


if __name__ == "__main__":
    main()
