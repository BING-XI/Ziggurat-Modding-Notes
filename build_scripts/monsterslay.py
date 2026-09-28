#!/usr/bin/env python3
r"""
monsterslay.py -- the SHARED Monster Slaying test cave, and the one place its numbers live.

Imported by build_monster_slaying.py (which owns the feature), build_assassin.py and
build_ranged_slayers.py (whose caves carry two of the five Monster Slaying sites).  Not a build
script: it has no --apply of its own.

====================================================================================
THE RULE (owner's design, 2026-09-26; melee re-tuned +4/+4 -> +5/+5 on 2026-09-28)
====================================================================================
Monster Slaying (ability 0x70) against a Monster (marker 0x3F):
    melee   +5 DAM when the slayer strikes a Monster, +5 DEF when a Monster strikes the slayer
    ranged  +2 DAM on the slayer's shots/breath,      +2 DEF against a Monster's shots/breath
No ATK bonus any more (it was +5 melee / +2 ranged).  The DEF half applies to EVERY melee strike --
deliberate, retaliation, opportunity, Round Attack -- unlike Parry, which sits on the deliberate
path only.  Breath counts as ranged: it goes through the same builder (CreateRangedAttackCA).

DEF is delivered as an ATTACK REDUCTION on the Monster's strike, the way vanilla Parry is
(`sub dword ptr [ebx], 8` @0x55767BE1): the strike record carries the attacker's ATK, and the
defender's DEF is read at resolution time, so taking N off the one is taking N off
(ATK - DEF), which is all the to-hit roll sees.
  * dword sites ([EBX] strike records) subtract UNCLAMPED, exactly like Parry on the same record.
    Parry runs before us in CalculateStrikes, so [EBX] may already be negative; a clamp to 0
    there would RAISE a parried Monster's attack.
  * byte sites (BL, a pushed ATK byte) clamp at 0 on borrow, so a weak attacker cannot wrap to
    ~250.

====================================================================================
THE FIVE SITES
====================================================================================
    site                          host / hook                 owner script
    StrikeDV (AI strike value)    0x55766564 -> 0x55766591    build_monster_slaying.py
    CalculateUnitStrikes          0x55767904 -> 0x55767931    build_monster_slaying.py
    CreateStrikeCA (opp./round)   cave_melee  @0x5580E070     build_assassin.py
    CalculateStrikes (deliberate) cave_melee3 @0x5580E120     build_assassin.py
    CreateRangedAttackCA          cave_rng    @0x5580E190     build_ranged_slayers.py

The last three already REPLAYED vanilla's Monster Slaying block in their caves, so the rule change
lives in the owning scripts' generators, switched by REWORK below.  A re-run of either owner
therefore keeps the rework instead of silently reinstalling +5/+5.

====================================================================================
ms_test -- the helper
====================================================================================
    in   EAX = attacker, EDX = target, ECX = GetAbilityEnabled VMT slot
             (0xA8 on combat objects, 0x148 on strategic units)
    out  AL bit 0 = attacker has Monster Slaying AND target is a Monster  -> +DAM
         AL bit 1 = attacker is a Monster AND target has Monster Slaying  -> -ATK (the DEF)
    Clobbers EAX, ECX, EDX and the flags; EBX, ESI, EDI, EBP survive (cave_melee3 keeps the
    strike record in EBX, cave_rng its PIC anchor in EDI).
Register/rel32 only -- no absolute operand, so it is position-independent as it stands.

====================================================================================
CAVE OWNERSHIP
====================================================================================
    0x5584F300 .. 0x5584F3FF   exclusive, owned by build_monster_slaying.py
        ms_test   0x5584F300
        cave_sdv  0x5584F380   (build_monster_slaying.py)
        cave_cus  0x5584F3C0   (build_monster_slaying.py)
Chosen above build_command_resroll.py's 0x5584F200..0x5584F300 (the previous high-water mark);
verified zero before first write.

REVERT: set REWORK = False, re-run build_assassin.py --apply and build_ranged_slayers.py --apply
(they regenerate the old inline +5/+5 and +2/+2 blocks), then build_monster_slaying.py --undo.
"""

import struct

REWORK = True          # False = the owner scripts emit the pre-2026-09-26 inline blocks

MELEE_DAM  = 5         # 2026-09-28, owner's numbers, current scale (4 from 2026-09-26)
MELEE_DEF  = 5
RANGED_DAM = 2
RANGED_DEF = 2

# Every number a re-tune may find installed. The owner scripts regenerate their bodies across this
# range and accept any of them, so changing a number above is an in-place rewrite.
RETUNE = range(1, 13)

ZONE_VA    = 0x5584F300
ZONE_LIMIT = 0x100
MS_TEST    = ZONE_VA
MS_TEST_MAX = 0x80     # cave_sdv starts at ZONE_VA + 0x80

SLAYING = 0x70         # Monster Slaying ability id
MONSTER = 0x3F         # Monster marker ability id


def _asm(src, va):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, va)[0])


def blob():
    src = f"""
        push ebx
        push esi
        push edi
        push ebp
        mov  esi, eax
        mov  edi, edx
        mov  ebp, ecx
        xor  ebx, ebx
        mov  edx, 0x{SLAYING:X}
        mov  eax, esi
        mov  ecx, [eax]
        call dword ptr [ecx+ebp]
        test al, al
        jz   ms_t2
        mov  edx, 0x{MONSTER:X}
        mov  eax, edi
        mov  ecx, [eax]
        call dword ptr [ecx+ebp]
        test al, al
        jz   ms_t2
        or   bl, 1
    ms_t2:
        mov  edx, 0x{MONSTER:X}
        mov  eax, esi
        mov  ecx, [eax]
        call dword ptr [ecx+ebp]
        test al, al
        jz   ms_t3
        mov  edx, 0x{SLAYING:X}
        mov  eax, edi
        mov  ecx, [eax]
        call dword ptr [ecx+ebp]
        test al, al
        jz   ms_t3
        or   bl, 2
    ms_t3:
        mov  eax, ebx
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    b = _asm(src, MS_TEST)
    assert len(b) <= MS_TEST_MAX, "ms_test is %d B, over its %d-byte slot" % (len(b), MS_TEST_MAX)
    return b


def call_text(attacker, target, slot):
    """asm that leaves the two result bits in AL. `target` may be a memory operand."""
    return f"""
    mov eax, {attacker}
    mov edx, {target}
    mov ecx, 0x{slot:X}
    call 0x{MS_TEST:X}"""


def apply_text(tag, dam_op, atk_op, dam, dfn, clamp):
    """asm consuming AL from call_text(): bit 0 -> `add dam_op, dam`; bit 1 -> `sub atk_op, dfn`.
    `clamp` floors a BYTE attack at 0 on borrow; dword sites stay unclamped (see the header)."""
    floor = f"""
    jae {tag}_b
    mov {atk_op}, 0""" if clamp else ""
    return f"""
    test al, 1
    jz {tag}_a
    add {dam_op}, {dam}
{tag}_a:
    test al, 2
    jz {tag}_b
    sub {atk_op}, {dfn}{floor}
{tag}_b:"""


def show(prefix="   "):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    b = blob()
    print("%sms_test @ %08X (%d B)" % (prefix, MS_TEST, len(b)))
    for ins in cs.disasm(b, MS_TEST):
        print("%s  %08X %-24s%s %s" % (prefix, ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))


def state(rd):
    """'ours' | 'free' | 'foreign' for the helper's own bytes."""
    b = blob()
    cur = rd(MS_TEST, len(b))
    if cur == b:
        return "ours"
    if not any(rd(MS_TEST, MS_TEST_MAX)):
        return "free"
    return "foreign"


def patch_entry(rd):
    """(va, expected_original, new, desc): accepts a virgin slot or our own blob, nothing else."""
    b = blob()
    cur = rd(MS_TEST, len(b))
    orig = b if cur == b else bytes(len(b))
    return (MS_TEST, orig, b, "ms_test (shared Monster Slaying test)")


def callers(rd, lo=0x55701000, hi=0x558E7918, exclude=()):
    """Every `call rel32` in CODE landing on ms_test, outside `exclude` ranges."""
    blk = rd(lo, hi - lo)
    hits = []
    for i in range(len(blk) - 5):
        if blk[i] != 0xE8:
            continue
        src = lo + i
        if src + 5 + struct.unpack_from("<i", blk, i + 1)[0] != MS_TEST:
            continue
        if any(a <= src < b for a, b in exclude):
            continue
        hits.append(src)
    return hits
