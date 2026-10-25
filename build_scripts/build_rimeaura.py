#!/usr/bin/env python
r"""
build_rimeaura.py -- Rime Aura (ability 0xC8): at the start of each of the holder's turns in battle,
every enemy within RADIUS hexes rolls to be frozen exactly as a Cold Strike hit would.  The cold twin
of Searing Aura (build_searingaura.py), same machinery.  AoWEPACK.dpl only (both combat systems).
Owner approved 2026-10-22.

HOW IT RUNS
    TCombatUnit.NewTurn (0x55724B28) -> TAbilityOwner.TriggerNewCombatTurn (0x5574FE68) calls VMT
    +0xF8 NewCombatTurn(ability, combat unit, CL = the combat player whose turn begins) on every
    ability the unit holds, for every unit, at each turn start.  Rime Aura is a
    TEnhancementAbility whose one object gets a run-time copy of the class VMT (GetMem,
    VMT-0x40..VMT+0x10C, parent link kept) with +0xF8 -> cave_aura.  No hook site.
    cave_aura: CL == holder [+0x45] (its own turn) and the holder alive -> for each live enemy
    unit (TCombatUnit, the opposing side's objects):
      reach    manual combat: hex distance 1..RADIUS (dHXtoHN 1..REACH_HN-1 from the HS positions);
               auto-resolve (holder is a TFastCombatUnit): TAbility.fcValidRoundDistance(holder,
               enemy), the melee-reach test of fast combat;
      the roll the enemy's ExecuteDamageEffectsRole (combat VMT +0x118) with mask 2 (cold) -- the
               Cold Strike roll: TAbstractUnit.ExecuteDamageEffectsRole's mask-2 branch tests Cold
               Immunity (ability 8), raises the resistance for Cold Protection and returns effect
               bit 2 (word 0x55781E24); live tuning (build_effectroll.py) included -- and on bit 2
               ExecuteDamageEffects (+0x128): ExecuteCombatDamageEffects' bit-2 arm gives Frozen
               (0x5F) and takes Burning away.
RNG   the roll is HitRole (one raw draw, gated only on replicated immunity).
        auto-resolve  P2 COMBAT RAW (after TCombat.Execute's re-anchor).
        manual        the end-turn event is synchronised but raw draws there are not; before each
                      roll System.RandSeed := TAoWHSMap.Random(map, $FFFFFF) -- §4.4's bridge for a
                      cave that calls an engine routine that draws raw.

REGISTRATION (package init -- prove by launching the exe)
    0x557BCCE0  `call RegisterAbility` -> cave_reg: replay, CreateEnhancementAbility (mask 0x03FF),
    the VMT copy, RegisterAbility.  Record: build_rimeaura_pfs.py.  LADDER 0xC9.  Hero Offers 0 %,
    Melee column.

Slot 0x558B4400-0x558B47FF, exclusive.  PIC.  Surgical --undo.

    python build_scripts/build_rimeaura.py            dry run + state
    python build_scripts/build_rimeaura.py --apply
    python build_scripts/build_rimeaura.py --undo
    python build_scripts/build_rimeaura.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic, ansistr

AURA, NAME = 0xC8, "Rime Aura"
MASK = 0x03FF
COLD_EFFECT = 2                                  # ExecuteDamageEffects* mask bit: cold -> Frozen
RADIUS = 2                                       # hexes
REACH_HN = 1 + 3 * RADIUS * (RADIUS + 1)         # dHXtoHN < 19 <=> ring 0..2

SLOT = (0x558B4400, 0x558B4800)
R_SITE = 0x557BCCE0
REGISTER, CEA, GETMEM = 0x55750238, 0x5576601C, 0x55701008
ISCLASS, DHXTOHN, HSRANDOM = 0x557010C0, 0x557026A4, 0x5577827C
GETOPPSIDE, GETOBJECTS, FCVALID = 0x55726688, 0x55726DBC, 0x5574E784
VAR_AOWHSMAP, CELL_RANDSEED, CELL_TENH = 0x558FA040, 0x558FB720, 0x5571DA7C
VMT_TCOMBATUNIT, VMT_TFASTCOMBATUNIT = 0x55715A94, 0x5571D4BC
VMT_NEG, VMT_SLOTS, SLOT_NEWCOMBATTURN = 0x40, 0x10C, 0xF8
V_ROLE, V_APPLY = 0x118, 0x128


def build_aura(va):
    src = f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x20
        push ebx
        push esi
        push edi
        mov  esi, edx
        mov  byte ptr [ebp - 4], cl
        {{ANC}}
        mov  al, byte ptr [esi + 0x45]
        cmp  al, byte ptr [ebp - 4]
        jne  a_out
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   a_out
        xor  eax, eax
        lea  edx, [edi + {{FAST}}]
        cmp  dword ptr [esi], edx
        sete al
        mov  dword ptr [ebp - 8], eax
        test eax, eax
        jne  a_nopos
        cmp  dword ptr [esi + 0x60], 0
        je   a_out
        mov  eax, dword ptr [esi + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        mov  dword ptr [ebp - 0xc], eax
        mov  eax, dword ptr [esi + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        mov  dword ptr [ebp - 0x10], eax
    a_nopos:
        mov  eax, esi
        call {GETOPPSIDE:#x}
        movzx eax, al
        cmp  eax, 1
        ja   a_out
        mov  edx, dword ptr [esi + 8]
        mov  eax, dword ptr [edx + eax*4 + 0x1c]
        mov  dword ptr [ebp - 0x14], eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  dword ptr [ebp - 0x18], eax
    a_next:
        dec  dword ptr [ebp - 0x18]
        js   a_out
        mov  edx, dword ptr [ebp - 0x18]
        mov  eax, dword ptr [ebp - 0x14]
        call {GETOBJECTS:#x}
        mov  ebx, eax
        test ebx, ebx
        je   a_next
        lea  edx, [edi + {{TCU}}]
        mov  eax, ebx
        call {ISCLASS:#x}
        test al, al
        je   a_next
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   a_next
        cmp  dword ptr [ebp - 8], 0
        je   a_tac
        mov  ecx, ebx
        mov  edx, esi
        xor  eax, eax
        call {FCVALID:#x}
        test al, al
        je   a_next
        jmp  a_roll
    a_tac:
        cmp  dword ptr [ebx + 0x60], 0
        je   a_next
        mov  eax, dword ptr [ebx + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        mov  dword ptr [ebp - 0x1c], eax
        mov  eax, dword ptr [ebx + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        push eax
        mov  ecx, dword ptr [ebp - 0x1c]
        mov  edx, dword ptr [ebp - 0x10]
        mov  eax, dword ptr [ebp - 0xc]
        call {DHXTOHN:#x}
        test eax, eax
        je   a_next
        cmp  eax, {REACH_HN}
        jge  a_next
        mov  eax, dword ptr [edi + {{MAPVAR}}]
        mov  edx, 0xffffff
        call {HSRANDOM:#x}
        mov  ecx, dword ptr [edi + {{SEED}}]
        mov  dword ptr [ecx], eax
    a_roll:
        mov  edx, {COLD_EFFECT}
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ROLE:#x}]
        test al, {COLD_EFFECT}
        je   a_next
        mov  edx, {COLD_EFFECT}
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_APPLY:#x}]
        jmp  a_next
    a_out:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    """
    return pic(src, va, "edi", {"FAST": VMT_TFASTCOMBATUNIT, "TCU": VMT_TCOMBATUNIT,
                                "MAPVAR": VAR_AOWHSMAP, "SEED": CELL_RANDSEED})


def build_reg(va, aura_va):
    src = f"""
        call {REGISTER:#x}
        push ebp
        mov  ebp, esp
        push esi
        push edi
        {{ANC}}
        push eax
        lea  edx, [eax + {{NAME}}]
        mov  cx, {MASK:#x}
        mov  eax, {AURA:#x}
        call {CEA:#x}
        push eax
        mov  eax, {VMT_NEG + VMT_SLOTS:#x}
        call {GETMEM:#x}
        mov  edi, eax
        mov  esi, dword ptr [esp]
        mov  esi, dword ptr [esi]
        sub  esi, {VMT_NEG:#x}
        mov  ecx, {(VMT_NEG + VMT_SLOTS) // 4:#x}
        rep movsd dword ptr es:[edi], dword ptr [esi]
        lea  edx, [eax + {VMT_NEG:#x}]
        mov  dword ptr [eax], edx
        mov  ecx, dword ptr [esp + 4]
        lea  esi, [ecx + {{AURA}}]
        mov  dword ptr [edx + {SLOT_NEWCOMBATTURN:#x}], esi
        lea  esi, [ecx + {{TENH}}]
        mov  dword ptr [edx - 0x18], esi
        pop  eax
        mov  dword ptr [eax], edx
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER:#x}
        pop  eax
        pop  edi
        pop  esi
        pop  ebp
        ret
    """
    return pic(src, va, "eax", {"NAME": ("TAIL", 8), "AURA": aura_va, "TENH": CELL_TENH},
               ansistr(NAME))


def layout():
    aura_va = SLOT[0]
    aura = build_aura(aura_va)
    reg_va = (aura_va + len(aura) + 0xF) & ~0xF
    return {"cave_aura": aura_va, "cave_reg": reg_va}, [("cave_aura", aura_va, aura),
                                                        ("cave_reg", reg_va, build_reg(reg_va, aura_va))]


def checks():
    d = open(P.TARGET, "rb").read()
    rd = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    V = rd(CELL_TENH)
    assert rd(V - 0x20) - V == VMT_SLOTS and rd(V + SLOT_NEWCOMBATTURN) == 0x5574EF38, \
        "TEnhancementAbility's VMT changed (size or +0xF8 NewCombatTurn)"
    assert rd(0x557158EC + V_ROLE) == 0x55726B10 and rd(0x557158EC + V_APPLY) == 0x55726B04, \
        "the combat damage-effect slots moved"
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:
        for i in range(ra, ra + rs - 5):
            if d[i] == 0xE8 and P.IMAGE_BASE + sva + (i - ra) + 5 + struct.unpack_from("<i", d, i + 1)[0] == CEA:
                for k in range(5, 30):
                    if d[i - k] == 0xB8:
                        src = P.IMAGE_BASE + sva + (i - ra)
                        if struct.unpack_from("<I", d, i - k + 1)[0] == AURA and not SLOT[0] <= src < SLOT[1]:
                            sys.exit("ABORT: %08X also registers %#x" % (src, AURA))
                        break
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    import ability_names
    if ability_names.names().get(AURA, NAME) != NAME:
        sys.exit("ABORT: ability_names gives %#x another name" % AURA)


AT, CAVES = layout()
ENTRY = {"cave_aura": 0x558B4400, "cave_reg": 0x558B4560}
assert AT == ENTRY, "the cave layout moved"
RNG_SITE = 0x558B4521               # the re-anchor's TAoWHSMap.Random (manual combat), asserted
assert CAVES[0][2][RNG_SITE - AT["cave_aura"]] == 0xE8, "the RNG site moved"
call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
HOOKS = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, AT["cave_reg"]))]

if __name__ == "__main__":
    checks()
    print("  layout: cave_aura %08X, cave_reg %08X" % (AT["cave_aura"], AT["cave_reg"]))
    run("build_rimeaura", HOOKS, CAVES, SLOT, [])
