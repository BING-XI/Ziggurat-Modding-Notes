#!/usr/bin/env python
r"""
build_mist.py -- the AoWEPACK half of Mist (id 89), the Air/Water dual tier-2 battle spell.  The
sight cut and the cast: build_mist_tc.py.  Data: build_airwater_pfs.py.  Owner's design 2026-10-26
(05-spells-added.md, "Air/Water -- agreed design").

MIST  a TDeathRay instance (a plain TCombatSpell, Taint the Flame's recipe), registered at
  0x557FA7FA (Recall Spirit's `call RegisterSpell` in RegisterCombatSpells, EBX = the control,
  replayed first).  Mana 15, research 160 (the single tier-3 figure), upkeep 0, sphere 7 (dual),
  tier 2, caster family 1 (Evoker) at +0x23; ATK / DMG 0, no damage types, 1 shot, range 0xFF,
  side 2.  Its RUN-TIME VMT copy (VMT-0x40..+0x9C; parent stays TCombatSpell) makes it worth
  nothing to either AI and keeps it out of auto-resolve:
    +0x80 GetCombatDamageValue    0
    +0x84 ...Ex                   the out record zeroed (ret 4)
    +0x90 fcPrefetchCombatCommands  queues nothing, so auto-resolve never casts it
    +0x94 fcExecuteCombatCommand    does nothing, AL = 1
    +0x98 fcGetDamageValueEx      the out record zeroed (ret 8)
RNG: none.  Slot 0x558BF400-0x558BF7FF, exclusive.  PIC.  Surgical --undo.  The registration runs
at package init: proved only by launching the exe.

    python build_scripts/build_mist.py            dry run + state
    python build_scripts/build_mist.py --apply
    python build_scripts/build_mist.py --undo
    python build_scripts/build_mist.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic, ansistr

MIST_ID, MIST_NAME = 89, "Mist"
MANA, RESEARCH, SPHERE, TIER, FAMILY = 15, 160, 7, 2, 1
SLOT = (0x558BF400, 0x558BF800)
REGISTER_SPELL, LSTRASG, GETMEM = 0x55779B40, 0x55701150, 0x55701008
DEATHRAY_CELL, DEATHRAY_CREATE, DEATHRAY_VMT = 0x557F46A0, 0x557F82B0, 0x557F46E0
VMT_NEG, VMT_SLOTS = 0x40, 0x9C
H_REG = 0x557FA7FA
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
        mov  dword ptr [edi + 0x10], {MIST_ID}
        mov  dword ptr [edi + 0x14], {MANA}
        mov  dword ptr [edi + 0x18], {RESEARCH}
        mov  dword ptr [edi + 0x1c], 0
        mov  byte ptr [edi + 0x20], {SPHERE}
        mov  byte ptr [edi + 0x21], {TIER}
        mov  byte ptr [edi + 0x23], {FAMILY}
        mov  byte ptr [edi + 0x34], 0
        mov  byte ptr [edi + 0x35], 0
        mov  word ptr [edi + 0x36], 0
        mov  byte ptr [edi + 0x38], 1
        mov  byte ptr [edi + 0x39], 0xff
        mov  byte ptr [edi + 0x3a], 0
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
                                "NAME": ("TAIL", 8)}, ansistr(MIST_NAME))


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
    for vs, sva, rs, ra in secs:            # nobody else creates spell 89
        for i in range(ra, ra + rs - 7):
            src = P.IMAGE_BASE + sva + (i - ra)
            if SLOT[0] <= src < SLOT[1]:
                continue
            if d[i] == 0xC7 and d[i + 1] in range(0x40, 0x48) and d[i + 2] == 0x10 \
                    and struct.unpack_from("<I", d, i + 3)[0] == MIST_ID:
                sys.exit("ABORT: %08X also stores spell id %d" % (src, MIST_ID))


def main():
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d)
    rel = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
    hooks = [(H_REG, rel(H_REG, REGISTER_SPELL), rel(H_REG, A["reg"]))]
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    run("build_mist -- Mist (AoWEPACK)", hooks, blobs, SLOT, [])


if __name__ == "__main__":
    main()
