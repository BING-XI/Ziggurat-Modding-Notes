#!/usr/bin/env python
r"""
build_mentaldiscipline.py -- Mental Discipline (ability 0xC7): the holder cannot be targeted by
Charm, Seduce, Dominate, Possess or Turn Undead.  AoWEPACK.dpl only (both combat systems).
Owner's design 2026-10-21/22.  No effect on fear: Fearless covers that (owner 2026-10-22).

UNTARGETABLE
    T   0x557682AC  TTouchAbility.CanTouch entry (7 B) -> cave_touch.  Every touch ability's
        CanTouch (VMT +0x11C) calls this base first with EAX = the ability unchanged: Dominate,
        Charm and Seduce through TCommandAbility.CanTouch, Possess and Turn Undead directly
        (build_turnundead_evilcommand.py's +0x11C cave on Turn Undead calls the vanilla method,
        which calls this).  It is the target pick of the manual-combat click
        (TTacticalCombatUnitHS.CanMoveOn), the manual-combat AI (TCAI.CheckUnit) and the
        auto-resolve AI (both fcPrefetchCombatCommands).  For ability ids 0x1C Dominate, 0x1D
        Seduce, 0x26 Turn Undead, 0x6A Possess and 0x94 Charm, a target holding 0xC7 -> False.
    The Turn Undead combat SPELL has no target filter in vanilla (a living target is accepted and
    nothing happens); a holder is treated as not undead in both of its undead tests:
    S   0x557F7CA0  TTurnUndead.CreateCA (11 B) -> cave_tuspell: no damage CA, as for the living;
    V   0x557F7D25  TTurnUndead.fcGetDamageValueEx (11 B) -> cave_tuvalue: value 0 for the AI.

REGISTRATION (package init -- prove by launching the exe)
    0x557BCCF7  `call RegisterAbility` -> piccave.enhancement_reg (CreateEnhancementAbility, mask
    0x03FF).  Record: build_mentaldiscipline_pfs.py.  LADDER 0xC8.  Hero Offers 0 %, Resistances.

RNG none.  Slot 0x558B4000-0x558B43FF, exclusive.  PIC.  Surgical --undo.

    python build_scripts/build_mentaldiscipline.py            dry run + state
    python build_scripts/build_mentaldiscipline.py --apply
    python build_scripts/build_mentaldiscipline.py --undo
    python build_scripts/build_mentaldiscipline.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run
from piccave import pic, enhancement_reg

DISCIPLINE, NAME = 0xC7, "Mental Discipline"
MASK = 0x03FF
BLOCKED = (0x1C, 0x1D, 0x26, 0x6A, 0x94)        # Dominate, Seduce, Turn Undead, Possess, Charm

SLOT = (0x558B4000, 0x558B4400)
R_SITE = 0x557BCCF7
REGISTER, CEA, ISCLASS = 0x55750238, 0x5576601C, 0x557010C0
VMT_TCOMBATUNIT = 0x55715A94
V_ABENABLED = 0xA8
SITES = {   # name: (va, vanilla, resume, function lo, hi)
    "touch":  (0x557682AC, bytes.fromhex("5356578bf18bfa"), 0x557682B3, 0x557682AC, 0x55768374),
    "tuspell": (0x557F7CA0, bytes.fromhex("8b464c8b10ff9214010000"), 0x557F7CAB, 0x557F7C50, 0x557F7D00),
    "tuvalue": (0x557F7D25, bytes.fromhex("8b434c8b10ff9214010000"), 0x557F7D30, 0x557F7D00, 0x557F7D9C),
}
TUSPELL_SKIP, TUVALUE_ZERO = 0x557F7CF4, 0x557F7D72


def build_has(va):
    """EAX = combat object -> AL = 1 when it is a combat unit holding Mental Discipline.  Keeps
    EBX/ESI/EDI/EBP."""
    src = f"""
        push ebx
        push edi
        mov  ebx, eax
        test ebx, ebx
        je   h_no
        {{ANC}}
        mov  eax, ebx
        lea  edx, [edi + {{TCU}}]
        call {ISCLASS:#x}
        test al, al
        je   h_no
        mov  eax, ebx
        mov  edx, {DISCIPLINE:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ABENABLED:#x}]
        jmp  h_out
    h_no:
        xor  eax, eax
    h_out:
        pop  edi
        pop  ebx
        ret
    """
    return pic(src, va, "edi", {"TCU": VMT_TCOMBATUNIT})


def build_touch(va, has):
    cmps = "\n".join(f"        cmp  eax, {i:#x}\n        je   t_chk" for i in BLOCKED)
    return asm(f"""
        push eax
        push edx
        push ecx
        mov  eax, dword ptr [eax + 0xc]
{cmps}
        jmp  t_go
    t_chk:
        mov  eax, dword ptr [esp]
        call {has:#x}
        test al, al
        jne  t_no
    t_go:
        pop  ecx
        pop  edx
        pop  eax
        push ebx
        push esi
        push edi
        mov  esi, ecx
        mov  edi, edx
        jmp  {SITES['touch'][2]:#x}
    t_no:
        pop  ecx
        pop  edx
        pop  eax
        xor  eax, eax
        ret
    """, va)


def build_undead(va, has, reg, name, skip):
    return asm(f"""
        mov  eax, {reg}
        call {has:#x}
        test al, al
        jne  u_skip
        mov  eax, dword ptr [{reg} + 0x4c]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x114]
        jmp  {SITES[name][2]:#x}
    u_skip:
        jmp  {skip:#x}
    """, va)


def layout():
    caves, at, va = [], {}, SLOT[0]

    def put(n, b):
        nonlocal va
        caves.append(("cave_" + n, va, b))
        at[n] = va
        va = (va + len(b) + 0xF) & ~0xF

    put("has", build_has(va))
    put("touch", build_touch(va, at["has"]))
    put("tuspell", build_undead(va, at["has"], "esi", "tuspell", TUSPELL_SKIP))
    put("tuvalue", build_undead(va, at["has"], "ebx", "tuvalue", TUVALUE_ZERO))
    put("reg", enhancement_reg(va, REGISTER, CEA, DISCIPLINE, NAME, MASK))
    return at, caves


def checks():
    d = open(P.TARGET, "rb").read()
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:
        for i in range(ra, ra + rs - 5):
            if d[i] == 0xE8 and P.IMAGE_BASE + sva + (i - ra) + 5 + struct.unpack_from("<i", d, i + 1)[0] == CEA:
                for k in range(5, 30):
                    if d[i - k] == 0xB8:
                        src = P.IMAGE_BASE + sva + (i - ra)
                        if struct.unpack_from("<I", d, i - k + 1)[0] == DISCIPLINE and not SLOT[0] <= src < SLOT[1]:
                            sys.exit("ABORT: %08X also registers %#x" % (src, DISCIPLINE))
                        break
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    import ability_names
    nm = ability_names.names()
    if nm.get(DISCIPLINE, NAME) != NAME:
        sys.exit("ABORT: ability_names gives %#x another name" % DISCIPLINE)
    want = {0x1C: "Dominate", 0x1D: "Seduce", 0x26: "Turn Undead", 0x6A: "Possess", 0x94: "Charm"}
    if any(nm.get(i) != n for i, n in want.items()):
        sys.exit("ABORT: a blocked id no longer names the ability it was chosen for")


AT, CAVES = layout()
call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
HOOKS = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, AT["reg"]))] + \
    [(va, van, jmp_to(va, AT[n], len(van))) for n, (va, van, _res, _lo, _hi) in SITES.items()]
INTERIOR = [(va, va + len(van), lo, hi) for _n, (va, van, _r, lo, hi) in SITES.items()]
# entry points, asserted (and read by rng_audit.py --owners)
ENTRY = {"has": 0x558B4000, "touch": 0x558B4040, "tuspell": 0x558B4090, "tuvalue": 0x558B40B0,
         "reg": 0x558B40D0}
assert AT == ENTRY, "the cave layout moved"

if __name__ == "__main__":
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in AT.items()))
    checks()
    run("build_mentaldiscipline", HOOKS, CAVES, SLOT, INTERIOR, sys.argv[1:])
