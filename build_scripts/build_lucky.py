#!/usr/bin/env python
r"""
build_lucky.py -- Lucky (ability 0xC9): once per battle, damage that would kill the holder leaves it
at 1 hit point instead.  AoWEPACK.dpl only (both combat systems).  Owner's request 2026-10-22.

THE ONE HP STEP
    Every damage source reaches TCombatObject.ExecuteDamage (combat VMT +0x124): strikes, shots and
    spells through DoDamage (+0x108, from the damage CAs), Invoke Death (DoDamage for the target's
    full HP), Burning and other damage over time (+0x124 directly), Razor Plate's cut.  Manual
    combat's TTacticalCombatUnit.ExecuteDamage (AoWTCPCK 0x00420250) calls it inherited and only then
    asks GetEnabled to choose the flinch or the death animation.  Inside it, dealt = min(damage, HP),
    SetHitPoints(HP - dealt), and DestroyObject (+0x120) when the unit reached 0: the only place a
    combat unit dies of damage, so nothing upstream treats the unit as dead first.
    C   0x55726C8A (10 B, `cmp ebx,edi / jle / mov ebp,edi / jmp / mov ebp,ebx`) -> cave_clamp:
        the same min; when it is lethal (damage >= HP > 0) and the target is a combat unit holding
        0xC9 whose slot byte B_LUCKY is still 0, the byte is set and dealt = HP - 1.  Resume
        0x55726C94.  (build_panic_cleardamage.py owns the function's entry, 0x55726C58.)
    S   0x55768A05 (6 B) TSelfDestructCA.Execute's `call [ecx+0x124]` on the user (its full HP) ->
        call cave_selfd + nop: spends the luck first, so a holder's own blast still kills it.
    Lucky does not cover deaths that are not damage: a unit destroyed with the object it is bound
    to (TCombatUnit.ObjectDestroyed), a possessor consumed by Possess, Decay at battle end.

STATE combatunit_slot.py byte B_LUCKY (tactical [unit+0x6B], auto-resolve [unit+0x67]), zeroed with
every combat object, so the luck returns each battle.  Needs build_combatunit_slot.py.

REGISTRATION (package init -- prove by launching the exe)
    0x557BCCC9  `call RegisterAbility` -> piccave.enhancement_reg (CreateEnhancementAbility, mask
    0x03FF).  Record: build_lucky_pfs.py.  LADDER 0xCA.  Hero Offers 0 %, Resistances column.

RNG none.  Slot 0x558B4800-0x558B4BFF, exclusive.  PIC.  Surgical --undo.

    python build_scripts/build_lucky.py            dry run + state
    python build_scripts/build_lucky.py --apply
    python build_scripts/build_lucky.py --undo
    python build_scripts/build_lucky.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run
from piccave import pic, enhancement_reg
import combatunit_slot as S

LUCKY, NAME = 0xC9, "Lucky"
MASK = 0x03FF
TAC_FLAG = S.TAC_SLOT + S.B_LUCKY                # [unit+0x6B]
FAST_FLAG = S.FAST_SLOT + S.B_LUCKY              # [unit+0x67]

TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")
SLOT = (0x558B4800, 0x558B4C00)
R_SITE = 0x557BCCC9
REGISTER, CEA, ISCLASS = 0x55750238, 0x5576601C, 0x557010C0
VMT_TCOMBATUNIT, VMT_FAST = 0x55715A94, S.FAST_VMT
V_ABENABLED, V_EXECDAMAGE = 0xA8, 0x124
SITES = {   # name: (va, vanilla, function lo, hi)
    "clamp": (0x55726C8A, bytes.fromhex("3bdf7e048befeb028beb"), 0x55726C58, 0x55726CD6),
    "selfd": (0x55768A05, bytes.fromhex("ff9124010000"), 0x557689A0, 0x55768A14),
}
CLAMP_RESUME = 0x55726C94


def build_flag(va):
    """EAX = combat object -> EAX = address of its B_LUCKY byte if it is a combat unit holding
    Lucky, else 0.  Keeps EBX/ESI/EDI/EBP."""
    src = f"""
        push ebx
        push edi
        mov  ebx, eax
        test ebx, ebx
        je   f_no
        {{ANC}}
        mov  eax, ebx
        lea  edx, [edi + {{TCU}}]
        call {ISCLASS:#x}
        test al, al
        je   f_no
        mov  eax, ebx
        mov  edx, {LUCKY:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ABENABLED:#x}]
        test al, al
        je   f_no
        lea  eax, [ebx + {TAC_FLAG:#x}]
        lea  ecx, [edi + {{FAST}}]
        cmp  dword ptr [ebx], ecx
        jne  f_out
        lea  eax, [ebx + {FAST_FLAG:#x}]
        jmp  f_out
    f_no:
        xor  eax, eax
    f_out:
        pop  edi
        pop  ebx
        ret
    """
    return pic(src, va, "edi", {"TCU": VMT_TCOMBATUNIT, "FAST": VMT_FAST})


def build_clamp(va, flag):
    # EBX = damage, EDI = hit points, ESI = the object; EAX/ECX/EDX are free (reloaded at the resume)
    return asm(f"""
        mov  ebp, ebx
        cmp  ebx, edi
        jl   k_done
        mov  ebp, edi
        test edi, edi
        jle  k_done
        mov  eax, esi
        call {flag:#x}
        test eax, eax
        je   k_done
        cmp  byte ptr [eax], 0
        jne  k_done
        mov  byte ptr [eax], 1
        lea  ebp, [edi - 1]
    k_done:
        jmp  {CLAMP_RESUME:#x}
    """, va)


def build_selfd(va, flag):
    # EAX = the self-destructing unit, EDX = its hit points, ECX = its VMT
    return asm(f"""
        push eax
        push edx
        push ecx
        call {flag:#x}
        test eax, eax
        je   d_go
        mov  byte ptr [eax], 1
    d_go:
        pop  ecx
        pop  edx
        pop  eax
        jmp  dword ptr [ecx + {V_EXECDAMAGE:#x}]
    """, va)


def layout():
    caves, at, va = [], {}, SLOT[0]

    def put(n, b):
        nonlocal va
        caves.append(("cave_" + n, va, b))
        at[n] = va
        va = (va + len(b) + 0xF) & ~0xF

    put("flag", build_flag(va))
    put("clamp", build_clamp(va, at["flag"]))
    put("selfd", build_selfd(va, at["flag"]))
    put("reg", enhancement_reg(va, REGISTER, CEA, LUCKY, NAME, MASK))
    return at, caves


def checks():
    d = open(P.TARGET, "rb").read()
    rb = lambda va, n: d[P.va2off(d, va):P.va2off(d, va) + n]
    rd = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    for va, want, what in ((0x55726C87, bytes.fromhex("0fbef8"), "ExecuteDamage's `movsx edi,al` (HP)"),
                           (CLAMP_RESUME, bytes.fromhex("8bd78bc52ad0"), "ExecuteDamage's SetHitPoints setup"),
                           (0x55768A01, bytes.fromhex("8bc68b08"), "Self Destruct's `mov eax,esi / mov ecx,[eax]`")):
        if rb(va, len(want)) != want:
            sys.exit("ABORT: %s is not at %08X" % (what, va))
    if rd(VMT_FAST - 0x1C) != S.FAST_SIZE:
        sys.exit("ABORT: TFastCombatUnit is not %#x bytes -- apply build_combatunit_slot.py first" % S.FAST_SIZE)
    t = open(TCPCK, "rb").read()
    base, P.IMAGE_BASE = P.IMAGE_BASE, 0x00400000
    try:
        tac = struct.unpack_from("<I", t, P.va2off(t, S.TAC_VMT - 0x1C))[0]
    finally:
        P.IMAGE_BASE = base
    if tac != S.TAC_SIZE:
        sys.exit("ABORT: TTacticalCombatUnit is not %#x bytes -- apply build_combatunit_slot.py first" % S.TAC_SIZE)
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:
        for i in range(ra, ra + rs - 5):
            if d[i] == 0xE8 and P.IMAGE_BASE + sva + (i - ra) + 5 + struct.unpack_from("<i", d, i + 1)[0] == CEA:
                for k in range(5, 30):
                    if d[i - k] == 0xB8:
                        src = P.IMAGE_BASE + sva + (i - ra)
                        if struct.unpack_from("<I", d, i - k + 1)[0] == LUCKY and not SLOT[0] <= src < SLOT[1]:
                            sys.exit("ABORT: %08X also registers %#x" % (src, LUCKY))
                        break
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    import ability_names
    if ability_names.names().get(LUCKY, NAME) != NAME:
        sys.exit("ABORT: ability_names gives %#x another name" % LUCKY)


AT, CAVES = layout()
call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
HOOKS = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, AT["reg"])),
         (SITES["clamp"][0], SITES["clamp"][1], jmp_to(SITES["clamp"][0], AT["clamp"], 10)),
         (SITES["selfd"][0], SITES["selfd"][1], call_to(SITES["selfd"][0], AT["selfd"]) + b"\x90")]
INTERIOR = [(va, va + len(van), lo, hi) for _n, (va, van, lo, hi) in SITES.items()]
# entry points, asserted (and read by rng_audit.py --owners)
ENTRY = {"flag": 0x558B4800, "clamp": AT["clamp"], "selfd": AT["selfd"], "reg": AT["reg"]}
assert AT == ENTRY, "the cave layout moved"

if __name__ == "__main__":
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in AT.items()))
    checks()
    run("build_lucky", HOOKS, CAVES, SLOT, INTERIOR, sys.argv[1:])
