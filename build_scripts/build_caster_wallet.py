#!/usr/bin/env python
r"""
build_caster_wallet.py -- every hero spell charge and every instant-cast gate uses
THero.CastingMana, not the raw [spell+0x14].  AoWEPACK.dpl.   (2026-09-25)

THE DEFECT (vanilla; widened by build_caster_cost.py and build_mastery_cost.py)
    THero.CastSpell's instant gate 0x557898B3 compares CastingMana with the casting points
    [hero+0x80], but ~25 spell classes build their token event with the RAW cost [spell+0x14],
    and TSpellTE.Validate 0x557798B8 hands [TE+0x1C] to THero.CanCastSpellInstantly 0x55789640,
    which rejects the cast when that raw cost exceeds the points.  In the band
    CastingMana <= points < raw the spell is accepted and then silently does nothing (Fire
    Mastery + Cloud of Ashes with 4-5 points left).  The same raw cost is what gets CHARGED, so a
    x1.5 opposed-sphere surcharge never reached an instant cast.  The combat spellbook (AoWz.exe
    0x42EB82) and the TCAI gate (AoWTCPCK 0x4187BB) also pass the raw cost to the same gate.

THE FIX -- three hooks, one rule: a cost EQUAL to [spell+0x14] becomes CastingMana(caster, spell)
0x557894EC (eax=hero, edx=spell).  Exact, not min(): the x1.5 surcharge is now charged too.
Idempotent for callers that already pass CastingMana (tactical combat's TSpell.CombatSpellCast,
build_caster_cost.py's sites A-C): their cost is either != raw (left alone) or == raw ==
CastingMana.  Exact is safe because every gate before a charge ends in THero.CanCastSpell's
mana >= CastingMana test (0x5578976E), and all five AI cast routines gate through
CanCastSpellInstantly.  Disjunction's TE carries its own spell id (TDisjunction.Activate sets
caster +8 = [spell+0x10] at 0x557EBF1C), so the equality test is sound there too.

  F    THero.CanCastSpellInstantly 0x5578964A  8b f9 8b f2 8b d8 (6 B) -> cave_f, resume 0x55789650
       eax=hero edx=spell id ecx=cost.  Spell via TSpellControl.GetSpell 0x55779AC8
       (eax=[[0x558FA044]+0x84], edx=id); 0x558FA044 (AoWHSSet) through a call/pop PIC anchor.
       Nil-guards: hero, id < 0 (GetSpell asserts on it), AoWHSSet, spell control, spell.
       EDI=cost afterwards, exactly as the displaced `mov edi,ecx` left it; ECX/EDX are dead
       (both rewritten before use from 0x55789650 on).
  CD   TSpell.CastingDone 0x557794D6  8b cf 8b 53 10 8b c6 (7 B) -> cave_cd, resume 0x557794DD
       the hero branch, just before `call THero.CastingDone`; ebx=spell esi=hero edi=cost.
       All 43 world-map charge callers pass through here.
  CCD  TSpell.CombatCastingDone 0x55779517  8b 47 4c 8b cd 8b 56 10 (8 B) -> cave_ccd,
       resume 0x5577951F (`call THero.CastingDone`); esi=spell edi=combat unit, [edi+0x4C]=hero
       (already tested THero at 0x55779503), ebp=cost.  EBP is dead after the call (popped).
       Auto-resolve's TCombatSpellCA / TExclusiveCombatSpellCA / TMultiTargetCombatSpellCA
       .Execute and TUnitSpell.ExecuteCA charge through here with the raw cost.
    No .reloc entry under any window; no jump lands inside one.  CastingMana, GetSpell and
    THero.CastingDone are Delphi register calls (EBX/ESI/EDI/EBP preserved).

RNG: none -- the caves make no draw.

Slot 0x5584D300-0x5584D3FF, exclusive.

USAGE
    python build_caster_wallet.py            verify / dry run (writes nothing)
    python build_caster_wallet.py --dis
    python build_caster_wallet.py --apply
    python build_caster_wallet.py --undo     surgical: hooks restored, slot zeroed
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584D300, 0x5584D400)
CASTINGMANA, GETSPELL, AOWHSSET = 0x557894EC, 0x55779AC8, 0x558FA044

F_HOOK, F_VAN, F_RESUME = 0x5578964A, bytes.fromhex("8bf98bf28bd8"), 0x55789650
CD_HOOK, CD_VAN, CD_RESUME = 0x557794D6, bytes.fromhex("8bcf8b53108bc6"), 0x557794DD
CCD_HOOK, CCD_VAN, CCD_RESUME = 0x55779517, bytes.fromhex("8b474c8bcd8b5610"), 0x5577951F

F_CAVE, CD_CAVE, CCD_CAVE = 0x5584D300, 0x5584D360, 0x5584D3A0

F_SRC = f"""
    mov edi, ecx
    mov esi, edx
    mov ebx, eax
    test ebx, ebx
    jz f_out
    test esi, esi
    jl f_out
    call f_anchor
f_anchor:
    pop eax
    sub eax, f_anchor
    mov eax, [eax+{AOWHSSET:#x}]
    test eax, eax
    jz f_out
    mov eax, [eax+0x84]
    test eax, eax
    jz f_out
    mov edx, esi
    call {GETSPELL:#x}
    test eax, eax
    jz f_out
    cmp edi, [eax+0x14]
    jne f_out
    mov edx, eax
    mov eax, ebx
    call {CASTINGMANA:#x}
    mov edi, eax
f_out:
    jmp {F_RESUME:#x}
"""

CD_SRC = f"""
    cmp edi, [ebx+0x14]
    jne cd_out
    mov eax, esi
    mov edx, ebx
    call {CASTINGMANA:#x}
    mov edi, eax
cd_out:
    mov ecx, edi
    mov edx, [ebx+0x10]
    mov eax, esi
    jmp {CD_RESUME:#x}
"""

CCD_SRC = f"""
    mov eax, [edi+0x4c]
    cmp ebp, [esi+0x14]
    jne ccd_out
    mov edx, esi
    call {CASTINGMANA:#x}
    mov ebp, eax
    mov eax, [edi+0x4c]
ccd_out:
    mov ecx, ebp
    mov edx, [esi+0x10]
    jmp {CCD_RESUME:#x}
"""

caves = [("cave_f", F_CAVE, asm(F_SRC, F_CAVE)),
         ("cave_cd", CD_CAVE, asm(CD_SRC, CD_CAVE)),
         ("cave_ccd", CCD_CAVE, asm(CCD_SRC, CCD_CAVE))]
assert F_CAVE + len(caves[0][2]) <= CD_CAVE and CD_CAVE + len(caves[1][2]) <= CCD_CAVE
hooks = [(F_HOOK, F_VAN, jmp_to(F_HOOK, F_CAVE, len(F_VAN))),
         (CD_HOOK, CD_VAN, jmp_to(CD_HOOK, CD_CAVE, len(CD_VAN))),
         (CCD_HOOK, CCD_VAN, jmp_to(CCD_HOOK, CCD_CAVE, len(CCD_VAN)))]
interior = [(F_HOOK, F_HOOK + len(F_VAN), 0x55789640, 0x55789710),
            (CD_HOOK, CD_HOOK + len(CD_VAN), 0x557794BC, 0x557794E6),
            (CCD_HOOK, CCD_HOOK + len(CCD_VAN), 0x557794E8, 0x55779549)]

if __name__ == "__main__":
    run("build_caster_wallet", hooks, caves, SLOT, interior)
