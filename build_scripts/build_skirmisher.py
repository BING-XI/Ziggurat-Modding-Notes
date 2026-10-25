#!/usr/bin/env python
r"""
build_skirmisher.py -- Skirmisher (ability 0xC4): attacking no longer ends the unit's turn.  A melee
or ranged attack costs MOVE_COST movement points and the unit keeps the rest, but it cannot attack
again that round.  Manual combat only (auto-resolve has no movement).  AoWEPACK.dpl (registration)
+ AoWTCPCK.dpl.  Owner's design 2026-10-21.

VANILLA  an attack zeroes the attacker's moves ([unit+0x5C]):
    melee   TCMeleeMoveTE.LastMove   0x004097CA..0x004097D5  `[attacker+0x5C] = 0`
    ranged  TCAbRangedTE.Execute     0x0040B6F6..0x0040B701  `[shooter+0x5C] = 0` (phase 0)
    TTacticalCombatUnit.NewTurn (0x0041CF7D) refills them at the start of the unit's side's turn.

THE CHANGE (state: combatunit_slot.py's dword, byte B_SKIRMISH = [unit+0x69], "attacked")
    M  0x004097CA (11 B) -> cave_melee: a Skirmisher keeps max(0, moves - MOVE_COST) and is
       marked; anyone else 0, as before.
    R  0x0040B6F6 (11 B) -> cave_ranged: the same for a ranged ATTACK -- [TE+0x14] is not 0x34 (a
       spell) and its AbilTypes category (build_abiltypes_relocate.py's table 0x00469440) is
       neither 0 nor 4 (touch: Healing, Rally ...); any other use of the ranged event as before.
    N  0x0041CF7D (6 B) -> cave_newturn: the refill, then the mark cleared.
    G  three gates refuse a marked unit's next attack, so "once per round" holds while it moves:
       0x00422CD8  MeleeMoveTC entry (6 B): the sole creator of the melee event (player + AI),
                   which also covers wall smashing -> returns False, the token-refusal path;
       0x00423860  AbRangedTC entry (6 B): the ranged event's sole sender -> returns 0 for an
                   attack category, passes spells, touches and Rally;
       0x004152A8  TCAI.CheckUnit entry (9 B): the mover (TList.Get([cai+8], [cai+0x20]), as
                   EvalBattle reads it) marked -> the hex is not evaluated (`ret 0x1C`: CheckUnit
                   takes seven stack arguments), so the AI proposes nothing more for it this round.
    Not gated: free swings and retaliation (reactive), touch abilities (they end the turn as
    before), and the cursor glyph -- a marked unit still shows the attack cursor; the click does
    nothing.

REGISTRATION (package init -- prove by launching the exe)
    0x557BCD3C  `call RegisterAbility` -> piccave.enhancement_reg (CreateEnhancementAbility, mask
    0x03FF).  Record: build_skirmisher_pfs.py.  LADDER 0xC5.  Hero Offers 0 %, Wayfaring column.

RNG none.  Slots: AoWEPACK 0x558B3000-0x558B30FF, AoWTCPCK 0x0043BC00-0x0043BFFF, exclusive.  PIC.
Needs build_combatunit_slot.py (asserted).  Surgical --undo (both modules).

    python build_scripts/build_skirmisher.py            dry run + state
    python build_scripts/build_skirmisher.py --apply
    python build_scripts/build_skirmisher.py --undo
    python build_scripts/build_skirmisher.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run
from piccave import pic, enhancement_reg
import combatunit_slot as S

EPACK = P.TARGET
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")
SKIRMISHER, NAME = 0xC4, "Skirmisher"
MOVE_COST = 12
FLAG = S.TAC_SLOT + S.B_SKIRMISH                 # [unit+0x69]
SPELLCASTING = 0x34

E_SLOT = (0x558B3000, 0x558B3100)
REGISTER, CEA = 0x55750238, 0x5576601C
R_SITE = 0x557BCD3C

T_SLOT = (0x0043BC00, 0x0043C000)
ABILTYPES = 0x00469440
TLIST_GET = 0x0040153C
CHECKUNIT_ARGS = 0x1C                           # TCAI.CheckUnit ends `ret 0x1C` (0x004180A5)
SITES = {   # name: (va, vanilla bytes, resume)
    "melee":     (0x004097CA, bytes.fromhex("8b45fc8b401c33d289505c"), 0x004097D5),
    "ranged":    (0x0040B6F6, bytes.fromhex("8b45fc8b401033d289505c"), 0x0040B701),
    "newturn":   (0x0041CF7D, bytes.fromhex("8b55fc89425c"), 0x0041CF83),
    "meleegate": (0x00422CD8, bytes.fromhex("558bec83c4f0"), 0x00422CDE),
    "rangegate": (0x00423860, bytes.fromhex("558bec83c4f0"), 0x00423866),
    "aigate":    (0x004152A8, bytes.fromhex("558bec81c44cffffff"), 0x004152B1),
}
FNS = {"melee": (0x0040905C, 0x00409A68), "ranged": (0x0040B2F8, 0x0040CDC0),
       "newturn": (0x0041CF44, 0x0041CF88), "meleegate": (0x00422CD8, 0x00422D68),
       "rangegate": (0x00423860, 0x004238FE), "aigate": (0x004152A8, 0x00418170)}

KEEP = f"""
        mov  edx, dword ptr [eax + 0x5c]
        sub  edx, {MOVE_COST}
        jge  k_set
        xor  edx, edx
    k_set:
        mov  dword ptr [eax + 0x5c], edx
        mov  byte ptr [eax + {FLAG:#x}], 1
"""


def is_skirmisher(lbl_no):
    return f"""
        push eax
        mov  edx, {SKIRMISHER:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        pop  eax
        je   {lbl_no}
    """


def build_melee(va):
    back = SITES["melee"][2]
    return asm(f"""
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x1c]
        {is_skirmisher("m_zero")}
        {KEEP}
        jmp  {back:#x}
    m_zero:
        xor  edx, edx
        mov  dword ptr [eax + 0x5c], edx
        jmp  {back:#x}
    """, va)


ATTACK_CAT = """
        cmp  edx, {spell}
        je   {no}
        cmp  edx, 0xff
        ja   {no}
        {{ANC}}
        movzx ecx, byte ptr [ecx + edx + {{TYPES}}]
        test ecx, ecx
        je   {no}
        cmp  ecx, 4
        je   {no}
"""


def build_ranged(va):
    back = SITES["ranged"][2]
    src = f"""
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [eax + 0x14]
        mov  eax, dword ptr [eax + 0x10]
        {ATTACK_CAT.format(spell=SPELLCASTING, no="r_zero")}
        {is_skirmisher("r_zero")}
        {KEEP}
        jmp  {back:#x}
    r_zero:
        xor  edx, edx
        mov  dword ptr [eax + 0x5c], edx
        jmp  {back:#x}
    """
    return pic(src, va, "ecx", {"TYPES": ABILTYPES})


def build_newturn(va):
    return asm(f"""
        mov  edx, dword ptr [ebp - 4]
        mov  dword ptr [edx + 0x5c], eax
        mov  byte ptr [edx + {FLAG:#x}], 0
        jmp  {SITES['newturn'][2]:#x}
    """, va)


def build_meleegate(va):
    return asm(f"""
        mov  ecx, dword ptr [eax + 0x1c]
        test ecx, ecx
        je   g_go
        cmp  byte ptr [ecx + {FLAG:#x}], 0
        je   g_go
        xor  eax, eax
        ret
    g_go:
        push ebp
        mov  ebp, esp
        add  esp, -0x10
        jmp  {SITES['meleegate'][2]:#x}
    """, va)


def build_rangegate(va):
    src = f"""
        push ecx
        push edx
        mov  ecx, dword ptr [eax + 0x1c]
        test ecx, ecx
        je   q_go
        cmp  byte ptr [ecx + {FLAG:#x}], 0
        je   q_go
        mov  edx, dword ptr [eax + 0x34]
        {ATTACK_CAT.format(spell=SPELLCASTING, no="q_go")}
        pop  edx
        pop  ecx
        xor  eax, eax
        ret
    q_go:
        pop  edx
        pop  ecx
        push ebp
        mov  ebp, esp
        add  esp, -0x10
        jmp  {SITES['rangegate'][2]:#x}
    """
    return pic(src, va, "ecx", {"TYPES": ABILTYPES})


def build_aigate(va):
    return asm(f"""
        push eax
        push edx
        push ecx
        mov  edx, dword ptr [eax + 0x20]
        mov  eax, dword ptr [eax + 8]
        call {TLIST_GET:#x}
        test eax, eax
        je   a_go
        cmp  byte ptr [eax + {FLAG:#x}], 0
        je   a_go
        pop  ecx
        pop  edx
        pop  eax
        ret  {CHECKUNIT_ARGS:#x}
    a_go:
        pop  ecx
        pop  edx
        pop  eax
        push ebp
        mov  ebp, esp
        add  esp, -0xb4
        jmp  {SITES['aigate'][2]:#x}
    """, va)


BUILDERS = {"melee": build_melee, "ranged": build_ranged, "newturn": build_newturn,
            "meleegate": build_meleegate, "rangegate": build_rangegate, "aigate": build_aigate}


def t_layout():
    caves, va = [], T_SLOT[0]
    for n, fn in BUILDERS.items():
        b = fn(va)
        caves.append(("cave_" + n, va, b))
        va = (va + len(b) + 0xF) & ~0xF
    return {n[5:]: v for n, v, _b in caves}, caves


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def checks():
    module(TCPCK, 0x00400000)
    t = open(TCPCK, "rb").read()
    rd = lambda va: struct.unpack_from("<I", t, P.va2off(t, va))[0]
    if rd(S.TAC_VMT - 0x1C) != S.TAC_SIZE:
        sys.exit("ABORT: TTacticalCombatUnit is not %#x bytes -- apply build_combatunit_slot.py first"
                 % S.TAC_SIZE)
    for va, want, what in ((0x004180A5, bytes.fromhex("c21c00"), "TCAI.CheckUnit's `ret 0x1C`"),
                           (0x00422D66, bytes.fromhex("c3"), "MeleeMoveTC's plain `ret`"),
                           (0x004238FD, bytes.fromhex("c3"), "AbRangedTC's plain `ret`")):
        if t[P.va2off(t, va):P.va2off(t, va) + len(want)] != want:
            sys.exit("ABORT: %s is not at %08X -- the gates' early returns would unbalance the stack"
                     % (what, va))
    tb = t[P.va2off(t, ABILTYPES):P.va2off(t, ABILTYPES) + 256]
    if not (tb[0x16] == 1 and tb[0x2F] == 4 and tb[0x34] == 0 and tb[0x56] == 5):
        sys.exit("ABORT: AbilTypes is not at %08X -- apply build_abiltypes_relocate.py first" % ABILTYPES)
    module(EPACK, 0x55700000)
    d = open(EPACK, "rb").read()
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:
        for i in range(ra, ra + rs - 5):
            if d[i] == 0xE8 and P.IMAGE_BASE + sva + (i - ra) + 5 + struct.unpack_from("<i", d, i + 1)[0] == CEA:
                for k in range(5, 30):
                    if d[i - k] == 0xB8:
                        src = P.IMAGE_BASE + sva + (i - ra)
                        if struct.unpack_from("<I", d, i - k + 1)[0] == SKIRMISHER and not E_SLOT[0] <= src < E_SLOT[1]:
                            sys.exit("ABORT: %08X also registers %#x" % (src, SKIRMISHER))
                        break
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    import ability_names
    if ability_names.names().get(SKIRMISHER, NAME) != NAME:
        sys.exit("ABORT: ability_names gives %#x another name" % SKIRMISHER)


T_AT, T_CAVES = t_layout()
E_CAVES = [("cave_reg", E_SLOT[0], enhancement_reg(E_SLOT[0], REGISTER, CEA, SKIRMISHER, NAME))]
call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
E_HOOKS = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, E_SLOT[0]))]
T_HOOKS = [(va, van, jmp_to(va, T_AT[n], len(van))) for n, (va, van, _b) in SITES.items()]
T_INTERIOR = [(va, va + len(van), FNS[n][0], FNS[n][1]) for n, (va, van, _b) in SITES.items()]
# entry points, asserted (and read by rng_audit.py --owners)
ENTRY = {"melee": 0x0043BC00, "ranged": 0x0043BC40, "newturn": 0x0043BCA0, "meleegate": 0x0043BCB0,
         "rangegate": 0x0043BCD0, "aigate": 0x0043BD20}
assert T_AT == ENTRY, "the cave layout moved"


def go(argv):
    module(EPACK, 0x55700000)
    run("build_skirmisher [AoWEPACK]", E_HOOKS, E_CAVES, E_SLOT, [], argv)
    module(TCPCK, 0x00400000)
    run("build_skirmisher [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, T_INTERIOR, argv)
    module(EPACK, 0x55700000)


if __name__ == "__main__":
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in T_AT.items()))
    checks()
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])
        print("\n" + "=" * 60)
    go(argv)
