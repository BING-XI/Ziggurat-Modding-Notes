#!/usr/bin/env python
r"""
build_rally.py -- Rally (ability 0xC2) and its status Rallied (0xC3).  AoWEPACK.dpl + AoWTCPCK.dpl +
AoWz.exe.  Owner's design 2026-10-21.

THE ABILITY
    Activated in battle, no target: clicking it (the unit panel, or the unit window's Use) fires at
    once and spends the unit's action, so once per combat round.  Every allied unit within RADIUS
    hexes of the user, the user included:
      * a panicked one (0x6C) rolls 50 % to recover (one roll each);
      * gains Rallied (0xC3) if it lacks it: +MORALE morale for the rest of the battle.
    Rallied is a second TPanickedAbility instance with its own id -- a TDurationAbility of mode 3
    ("entire combat"), removed by TDurationAbility.CombatDone at battle end; every panic effect in
    the engine keys on id 0x6C, so this instance carries none of them.  Morale: UpdateMoraleValue
    adds MORALE while the unit holds 0xC3; TPanickedAbility.Expand (gain) and Healing's removal
    path both call Changed, which recomputes morale, so the bonus and the cure act mid-battle.
    Auto-resolve has no hex positions: there every ally is in range.

THE AI RULE (rally_value, shared by both AIs; owner 2026-10-21)
    value = PANIC_DV per panicked ally in range + BUFF_DV per ally in range without Rallied, when
    at least one ally in range is panicked;
    otherwise BUFF_DV per unbuffed ally in range, but only when an enemy unit is within RADIUS (any
    enemy, in auto-resolve) AND the enemy side cannot panic anyone: no enemy unit in the battle has
    Cause Fear (0x33), and no enemy caster could cast Terror (spell 105) -- the owning player has it
    researched (TPlayerMagicControl +0x30, or the engine's know-every-spell case ListSpells tests),
    and the caster is a hero/leader with Spell Casting, or a unit whose Spell Casting level is at
    least Terror's tier (read live: TSpell +0x21).  Else 0 (no rally).

WIRING
    AoWEPACK  R  0x557BCD53  `call RegisterAbility` (Fire Protection's) -> cave_reg: replays it,
                 registers Rally through CreateEnhancementAbility (mask 0x03FF), then gives that one
                 object a run-time copy of TEnhancementAbility's VMT (GetMem, VMT-0x40..VMT+0x10C;
                 parent link -> TEnhancementAbility, so IsClass still says yes) with +0xA0
                 fcPrefetchCombatCommands -> cave_fcpre and +0xA4 fcExecuteCombatCommand ->
                 cave_fcexec; then registers Rallied (TPanickedAbility.Create, id and name replaced).
              M  0x5577F074  UpdateMoraleValue's `call [edi+0x17C]` (GetUnitMoraleValue, 6 B) ->
                 call cave_morale + nop: the original, then +MORALE if the unit holds 0xC3.
              auto-resolve: TFastCombatUnit.fcExecute asks every ability the unit holds (+0xA0);
                 cave_fcpre adds one TFastCombatCommand (target = the actor, DV = rally_value,
                 DEV = DVtoDEV) when the rule says so; cave_fcexec runs rally_effect.
    AoWz.exe  C  0x0043498C (TTCUnit.UAbilLBMouseDown, the panel click) and 0x00409FC5
                 (TUnitWindow.UseAbility): rel32 of `call SelectAbility` -> cave_click: Rally ->
                 AoWTCPCK rally_click (through the rebase delta of the SelectAbility import cell);
                 any other id -> SelectAbility as before.  The Q / right-click cycles call
                 SelectAbility from AoWTCPCK, so they still only select.
    AoWTCPCK  rally_click (EAX = the unit's HS): SelectAbility's own gates (the active side is the
                 local one, the unit not busy, moves left, its side active) plus "holds Rally", then
                 [HS+0x34] = Rally, AbRangedTC(HS, own hex) -- the engine's touch-without-moving
                 path, the one SelectSpell uses for a no-target spell -- and the HS's +0x100.
              T  0x0040B3B0  TCAbRangedTE.Execute phase 0, right after [TE+0x10] = the user (6 B)
                 -> cave_te: ability Rally -> rally_effect (through the rebase delta of the
                 GetAbility import cell), the user's moves to 0 ([+0x5C], as the event does for a
                 shot), done flag, exit at 0x0040B70F.  Every peer runs the event.
              A  0x0041921A  TCAI, after the friendly-target loop and build_ai_selfheal.py's
                 proposal (6 B) -> cave_aiprop: a mover with moves left and Rally proposes a type-1
                 move on itself (ability Rally, value tcDVtoDEV(rally_value)), self-heal's shape;
                 build_ai_selfheal.py's executor (0x0041ACE4) sends it through AbRangedTC like a
                 self-heal -- it accepts Rally since 2026-10-21.

RNG   rally_effect draws once per allied unit in range (hoisted out of the panic test, so the count
      depends only on who stands where):
        tactical  P1 SYNCED DRAW -- TCAbRangedTE.Execute is in AoWTCPCK's SYNC list; raw draws in
                  the event are not replicated.  RandSeed is saved and restored around it.
        auto      P2 COMBAT RAW -- fcExecuteCombatCommand runs after TCombat.Execute's re-anchor.
      rally_value draws nothing.

Slots: AoWEPACK 0x558B2400-0x558B2FFF, AoWTCPCK 0x0043B900-0x0043BBFF, AoWz.exe 0x0062D300-
0x0062D3FF (.hcol tail), all exclusive.  The two DLLs' caves are PIC (call/pop anchors, rel32).
Surgical --undo, all three modules.  Records: build_rally_pfs.py.  Ceilings: LADDER 0xC4.

Couplings: build_ai_selfheal.py's executor knows RALLY; the AoWTCPCK caves call AoWEPACK at
E_STUB_EFFECT / E_STUB_VALUE (pinned stubs) and the exe calls AoWTCPCK at T_CLICK (pinned).

    python build_scripts/build_rally.py            dry run + state (three modules)
    python build_scripts/build_rally.py --apply
    python build_scripts/build_rally.py --undo
    python build_scripts/build_rally.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
import exe_patch as XP
from aowepack_patch import asm, jmp_to, run

EPACK = P.TARGET
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")

RALLY, RALLIED = 0xC2, 0xC3
NAME_RALLY, NAME_RALLIED = "Rally", "Rallied"
MASK = 0x03FF
RADIUS = 6
RADIUS_HN = 1 + 3 * RADIUS * (RADIUS + 1)       # first spiral hex number of ring RADIUS+1 = 127
MORALE = 30
PANIC_DV, BUFF_DV = 1000, 300
PANICKED, CAUSE_FEAR, SPELLCASTING, TERROR = 0x6C, 0x33, 0x34, 105

# ---------------------------------------------------------------- AoWEPACK
E_SLOT = (0x558B2400, 0x558B3000)
E_STUB_EFFECT, E_STUB_VALUE = 0x558B2400, 0x558B2408
REGISTER, CEA, GETABILITY = 0x55750238, 0x5576601C, 0x557501C0
GETMEM, LSTRASG, ISCLASS, RANDINT = 0x55701008, 0x55701150, 0x557010C0, 0x55701080
HSRANDOM, DHXTOHN, INDEXOF = 0x5577827C, 0x557026A4, 0x55702EA4
GETSIDE, GETOPPSIDE, GETOBJECTS, GETPLAYER = 0x55726660, 0x55726688, 0x55726DBC, 0x557268E4
GETPLAYERS, GETSPELL, DVTODEV = 0x557544D0, 0x55779AC8, 0x55725F10
FC_CREATE, FC_ADD = 0x55743858, 0x557439F4
PANICKED_CREATE = 0x557BA790
VAR_AOWHSMAP, VAR_AOWHSSET, CELL_RANDSEED = 0x558FA040, 0x558FA044, 0x558FB720
CELL_FC_CLASS, CELL_TENH, CELL_PANICKED, CELL_THERO = 0x55715E9C, 0x5571DA7C, 0x557B6794, 0x55711FAC
VMT_TCOMBATUNIT = 0x55715A94
VMT_NEG, VMT_SLOTS = 0x40, 0x10C                # TEnhancementAbility: VMT-0x40 .. last slot +0x108
R_SITE = 0x557BCD53
M_SITE, M_VAN = 0x5577F074, bytes.fromhex("ff977c010000")

# ---------------------------------------------------------------- AoWTCPCK
T_SLOT = (0x0043B900, 0x0043BC00)
T_CLICK = 0x0043B900                             # pinned: AoWz.exe's cave_click jumps here
T_SELECTABILITY, T_ABRANGEDTC = 0x00422F0C, 0x00423860
T_DV2DEV, T_CREATEMOVE = 0x00413664, 0x004135B8
T_VAR_CTL, T_CELL_GETABIL = 0x0046C064, 0x0046E6EC
TE_SITE, TE_BACK, TE_EXIT = 0x0040B3B0, 0x0040B3B6, 0x0040B70F
TE_VAN = bytes.fromhex("8b45fc8b4010")
TE_FN = (0x0040B2F8, 0x0040CDC0)
AI_SITE, AI_BACK = 0x0041921A, 0x00419220
AI_VAN = bytes.fromhex("8b45c88b4008")
AI_FN = (0x00419140, 0x00419260)

# ---------------------------------------------------------------- AoWz.exe
X_SLOT = (0x0062D300, 0x0062D400)
X_SITES = (0x0043498C, 0x00409FC5)               # call SelectAbility (thunk 0x00403394)
X_THUNK, X_CELL_SELECT = 0x00403394, 0x0045EBC0

ANCHOR = b"\xE8\x00\x00\x00\x00"


def ansistr(s):
    b = s.encode("latin1")
    return struct.pack("<iI", -1, len(b)) + b + b"\0"


def pic(src, va, reg, fields, tail=b""):
    """Assemble `src` once.  `{ANC}` marks a `call anc / anc: pop <reg>` anchor (exactly one); each
    `{NAME}` in `fields` is a disp32 placeholder patched to (target - anchor), so no instruction
    changes length.  A target of ("TAIL", n) is byte n of `tail`, appended after 4-byte alignment."""
    ph = {n: 0x7FFFF000 + 0x10 * k for k, n in enumerate(fields)}
    pop = {"eax": 0x58, "ecx": 0x59, "edx": 0x5A, "ebx": 0x5B, "esi": 0x5E, "edi": 0x5F}[reg]
    text = src.replace("{ANC}", "call anc_%s\n    anc_%s:\n        pop %s" % (reg, reg, reg))
    code = bytearray(asm(text.format(**{n: "%#x" % v for n, v in ph.items()}), va))
    k = code.find(ANCHOR + bytes([pop]))
    assert k >= 0 and code.find(ANCHOR + bytes([pop]), k + 1) < 0, "anchor not found exactly once"
    anchor = va + k + 5
    while len(code) % 4:
        code += b"\x90"
    tail_va = va + len(code)
    for n, tgt in fields.items():
        pos = [j for j in range(len(code) - 3) if code[j:j + 4] == struct.pack("<I", ph[n])]
        assert pos, "placeholder %s not found" % n
        t = tail_va + tgt[1] if isinstance(tgt, tuple) else tgt
        for j in pos:
            struct.pack_into("<i", code, j, t - anchor)
    assert not any(code[j:j + 4] == struct.pack("<I", v) for v in ph.values()
                   for j in range(len(code) - 3)), "a placeholder survived"
    return bytes(code) + tail


# ================================================================ AoWEPACK caves
def unit_in_range(lbl, skip):
    """EBX = a combat object.  Falls to `skip` unless it is a live TCombatUnit within RADIUS of the
    actor (frame: [ebp-4] tactical, [ebp-8]/[ebp-0xC] actor x/y; EDI = the PIC base)."""
    return f"""
        test ebx, ebx
        je   {skip}
        lea  edx, [edi + {{TCU}}]
        mov  eax, ebx
        call {ISCLASS:#x}
        test al, al
        je   {skip}
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   {skip}
        cmp  dword ptr [ebp - 4], 0
        je   {lbl}_in
        mov  eax, dword ptr [ebx + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        mov  dword ptr [ebp - 0x10], eax
        mov  eax, dword ptr [ebx + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        push eax
        mov  ecx, dword ptr [ebp - 0x10]
        mov  edx, dword ptr [ebp - 0xc]
        mov  eax, dword ptr [ebp - 8]
        call {DHXTOHN:#x}
        cmp  eax, {RADIUS_HN}
        jge  {skip}
    {lbl}_in:
    """


PROLOGUE = f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x40
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  dword ptr [ebp - 4], edx
        {{ANC}}
        xor  eax, eax
        mov  dword ptr [ebp - 8], eax
        mov  dword ptr [ebp - 0xc], eax
        cmp  dword ptr [ebp - 4], 0
        je   have_pos
        mov  eax, dword ptr [esi + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        mov  dword ptr [ebp - 8], eax
        mov  eax, dword ptr [esi + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        mov  dword ptr [ebp - 0xc], eax
    have_pos:
"""

EPILOGUE = """
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
"""


def side_loop(lbl, getside, body):
    """For each object of the actor's own (GETSIDE) or opposing (GETOPPSIDE) side, EBX = object."""
    return f"""
        mov  eax, esi
        call {getside:#x}
        movzx eax, al
        cmp  eax, 1
        ja   {lbl}_done
        mov  edx, dword ptr [esi + 8]
        mov  eax, dword ptr [edx + eax*4 + 0x1c]
        mov  dword ptr [ebp - 0x14], eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  dword ptr [ebp - 0x18], eax
    {lbl}_next:
        dec  dword ptr [ebp - 0x18]
        js   {lbl}_done
        mov  edx, dword ptr [ebp - 0x18]
        mov  eax, dword ptr [ebp - 0x14]
        call {GETOBJECTS:#x}
        mov  ebx, eax
        {body}
    {lbl}_skip:
        jmp  {lbl}_next
    {lbl}_done:
    """


def has_ab(obj_reg, aid):
    return f"""
        mov  edx, {aid:#x}
        mov  eax, {obj_reg}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
    """


def build_value(va):
    """rally_value(EAX = actor, EDX = tactical) -> EAX = DV (0: do not rally).
    frame: [-0x1c] panicked, [-0x20] unbuffed, [-0x24] enemy near, [-0x28] threat, [-0x2c] tier."""
    own = unit_in_range("vo", "vo_skip") + has_ab("ebx", PANICKED) + """
        je   vo_np
        inc  dword ptr [ebp - 0x1c]
    vo_np:
    """ + has_ab("ebx", RALLIED) + """
        jne  vo_skip
        inc  dword ptr [ebp - 0x20]
    """
    enemy = f"""
        test ebx, ebx
        je   ve_skip
        lea  edx, [edi + {{TCU}}]
        mov  eax, ebx
        call {ISCLASS:#x}
        test al, al
        je   ve_skip
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   ve_skip
    """ + has_ab("ebx", CAUSE_FEAR) + """
        je   ve_nofear
        mov  dword ptr [ebp - 0x28], 1
    ve_nofear:
    """ + has_ab("ebx", SPELLCASTING) + f"""
        je   ve_range
        mov  eax, ebx
        call {GETPLAYER:#x}
        movsx edx, al
        test edx, edx
        js   ve_range
        mov  eax, dword ptr [edi + {{MAPVAR}}]
        mov  eax, dword ptr [eax + 0x140]
        call {GETPLAYERS:#x}
        test eax, eax
        je   ve_range
        mov  eax, dword ptr [eax + 0x54]
        test eax, eax
        je   ve_range
        cmp  byte ptr [eax + 0xc], 0
        je   ve_list
        mov  edx, dword ptr [eax + 0x10]
        test edx, edx
        je   ve_list
        cmp  byte ptr [edx + 0xa7], 0
        je   ve_known
    ve_list:
        mov  eax, dword ptr [eax + 0x30]
        test eax, eax
        je   ve_range
        mov  edx, {TERROR}
        call {INDEXOF:#x}
        test eax, eax
        js   ve_range
    ve_known:
        mov  eax, dword ptr [ebx + 0x4c]
        mov  edx, dword ptr [edi + {{THERO}}]
        call {ISCLASS:#x}
        test al, al
        jne  ve_threat
        mov  edx, {SPELLCASTING:#x}
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xb0]
        movzx eax, al
        cmp  eax, dword ptr [ebp - 0x2c]
        jl   ve_range
    ve_threat:
        mov  dword ptr [ebp - 0x28], 1
    ve_range:
        cmp  dword ptr [ebp - 0x24], 0
        jne  ve_skip
    """ + unit_in_range("ver", "ve_skip") + """
        mov  dword ptr [ebp - 0x24], 1
    """
    src = PROLOGUE + f"""
        xor  eax, eax
        mov  dword ptr [ebp - 0x1c], eax
        mov  dword ptr [ebp - 0x20], eax
        mov  dword ptr [ebp - 0x24], eax
        mov  dword ptr [ebp - 0x28], eax
        mov  dword ptr [ebp - 0x2c], 0xff
        mov  eax, dword ptr [edi + {{SETVAR}}]
        mov  eax, dword ptr [eax + 0x84]
        mov  edx, {TERROR}
        call {GETSPELL:#x}
        test eax, eax
        je   v_tier
        movzx eax, byte ptr [eax + 0x21]
        mov  dword ptr [ebp - 0x2c], eax
    v_tier:
    """ + side_loop("vo", GETSIDE, own) + side_loop("ve", GETOPPSIDE, enemy) + f"""
        mov  eax, dword ptr [ebp - 0x1c]
        test eax, eax
        je   v_nopanic
        imul eax, eax, {PANIC_DV}
        mov  ecx, dword ptr [ebp - 0x20]
        imul ecx, ecx, {BUFF_DV}
        add  eax, ecx
        jmp  v_out
    v_nopanic:
        mov  eax, dword ptr [ebp - 0x20]
        test eax, eax
        je   v_out
        cmp  dword ptr [ebp - 0x24], 0
        je   v_zero
        cmp  dword ptr [ebp - 0x28], 0
        jne  v_zero
        imul eax, eax, {BUFF_DV}
        jmp  v_out
    v_zero:
        xor  eax, eax
    v_out:
    """ + EPILOGUE
    return pic(src, va, "edi", {"TCU": VMT_TCOMBATUNIT, "MAPVAR": VAR_AOWHSMAP,
                                "THERO": CELL_THERO, "SETVAR": VAR_AOWHSSET})


def build_effect(va):
    """rally_effect(EAX = actor, EDX = tactical): every allied unit in range draws once; a panicked
    one recovers on 0 (of 2); any one without Rallied gains it."""
    body = unit_in_range("eo", "eo_skip") + f"""
        cmp  dword ptr [ebp - 4], 0
        je   eo_raw
        mov  eax, dword ptr [edi + {{SEED}}]
        push dword ptr [eax]
        mov  eax, dword ptr [edi + {{MAPVAR}}]
        mov  edx, 2
        call {HSRANDOM:#x}
        mov  ecx, dword ptr [edi + {{SEED}}]
        pop  dword ptr [ecx]
        jmp  eo_drawn
    eo_raw:
        mov  eax, 2
        call {RANDINT:#x}
    eo_drawn:
        mov  dword ptr [ebp - 0x1c], eax
    """ + has_ab("ebx", PANICKED) + f"""
        je   eo_np
        cmp  dword ptr [ebp - 0x1c], 0
        jne  eo_np
        mov  eax, dword ptr [ebx + 0x4c]
        mov  edx, {PANICKED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x98]
        mov  eax, dword ptr [ebx + 0x4c]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x90]
    eo_np:
    """ + has_ab("ebx", RALLIED) + f"""
        jne  eo_skip
        mov  eax, dword ptr [ebx + 0x4c]
        mov  edx, {RALLIED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x94]
    """
    src = PROLOGUE + side_loop("eo", GETSIDE, body) + EPILOGUE
    return pic(src, va, "edi", {"TCU": VMT_TCOMBATUNIT, "SEED": CELL_RANDSEED,
                                "MAPVAR": VAR_AOWHSMAP})


def build_reg(va, at):
    tail = ansistr(NAME_RALLY)
    t_rallied = len(tail)
    tail += ansistr(NAME_RALLIED)
    src = f"""
        call {REGISTER:#x}
        push ebp
        mov  ebp, esp
        push esi
        push edi
        {{ANC}}
        push eax
        lea  edx, [eax + {{NRALLY}}]
        mov  cx, {MASK:#x}
        mov  eax, {RALLY:#x}
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
        lea  esi, [ecx + {{FCPRE}}]
        mov  dword ptr [edx + 0xa0], esi
        lea  esi, [ecx + {{FCEXEC}}]
        mov  dword ptr [edx + 0xa4], esi
        lea  esi, [ecx + {{TENH}}]
        mov  dword ptr [edx - 0x18], esi
        pop  eax
        mov  dword ptr [eax], edx
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER:#x}
        mov  ecx, dword ptr [esp]
        mov  eax, dword ptr [ecx + {{PANICKED}}]
        xor  ecx, ecx
        mov  dl, 1
        call {PANICKED_CREATE:#x}
        mov  dword ptr [eax + 0xc], {RALLIED:#x}
        push eax
        mov  ecx, dword ptr [esp + 4]
        lea  edx, [ecx + {{NRALLIED}}]
        lea  eax, [eax + 8]
        call {LSTRASG:#x}
        pop  edx
        mov  eax, ebx
        call {REGISTER:#x}
        pop  eax
        pop  edi
        pop  esi
        pop  ebp
        ret
    """
    return pic(src, va, "eax", {"NRALLY": ("TAIL", 8), "NRALLIED": ("TAIL", t_rallied + 8),
                                "FCPRE": at["cave_fcpre"], "FCEXEC": at["cave_fcexec"],
                                "TENH": CELL_TENH, "PANICKED": CELL_PANICKED}, tail)


def build_morale(va):
    return asm(f"""
        call dword ptr [edi + 0x17c]
        push eax
        mov  edx, {RALLIED:#x}
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        pop  eax
        je   m_out
        add  eax, {MORALE}
    m_out:
        ret
    """, va)


def build_fcpre(va):
    src = f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        mov  eax, dword ptr [esi + 4]
        xor  edx, edx
        call {E_STUB_VALUE:#x}
        test eax, eax
        jle  p_out
        mov  edi, eax
        {{ANC}}
        mov  eax, dword ptr [ecx + {{FCCLASS}}]
        mov  ecx, dword ptr [ebx + 0xc]
        mov  dl, 1
        call {FC_CREATE:#x}
        mov  ebx, eax
        mov  eax, dword ptr [esi + 4]
        mov  dword ptr [ebx + 0x18], eax
        mov  dword ptr [ebx + 8], edi
        xor  eax, eax
        mov  dword ptr [ebx + 0xc], eax
        mov  dword ptr [ebx + 0x14], eax
        push dword ptr [esi + 4]
        mov  ecx, dword ptr [esi + 4]
        xor  edx, edx
        mov  eax, edi
        call {DVTODEV:#x}
        mov  dword ptr [ebx + 0x10], eax
        mov  edx, ebx
        mov  eax, esi
        call {FC_ADD:#x}
    p_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ecx", {"FCCLASS": CELL_FC_CLASS})


def build_fcexec(va):
    return asm(f"""
        mov  eax, edx
        xor  edx, edx
        call {E_STUB_EFFECT:#x}
        mov  al, 1
        ret
    """, va)


def e_layout():
    at, caves, va = {}, [], E_SLOT[0]
    stubs_end = E_STUB_VALUE + 8
    order = ["cave_fcpre", "cave_fcexec", "cave_morale", "rally_value", "rally_effect", "cave_reg"]
    sizes = {}
    # two passes: lengths do not depend on the addresses (rel32 / disp32 throughout)
    for _pass in range(2):
        va = (stubs_end + 0xF) & ~0xF
        for n in order:
            at[n] = va
            va = (va + sizes.get(n, 0x200) + 0xF) & ~0xF
        blobs = {"cave_fcpre": build_fcpre(at["cave_fcpre"]), "cave_fcexec": build_fcexec(at["cave_fcexec"]),
                 "cave_morale": build_morale(at["cave_morale"]),
                 "rally_value": build_value(at["rally_value"]),
                 "rally_effect": build_effect(at["rally_effect"]), "cave_reg": build_reg(at["cave_reg"], at)}
        sizes = {n: len(b) for n, b in blobs.items()}
    stubs = asm(f"jmp {at['rally_effect']:#x}", E_STUB_EFFECT)
    stubs += b"\x90" * (E_STUB_VALUE - E_STUB_EFFECT - len(stubs))
    stubs += asm(f"jmp {at['rally_value']:#x}", E_STUB_VALUE)
    caves = [("stubs", E_STUB_EFFECT, stubs)] + [(n, at[n], blobs[n]) for n in order]
    return at, caves


# ================================================================ AoWTCPCK caves
def build_click(va):
    """rally_click(EAX = the unit's HS) -> EAX = -1."""
    src = f"""
        push ebx
        push esi
        mov  ebx, eax
        {{ANC}}
        mov  eax, dword ptr [esi + {{CTL}}]
        test eax, eax
        je   c_out
        mov  dl, byte ptr [eax + 0xed]
        cmp  dl, byte ptr [eax + 0xec]
        jne  c_out
        mov  eax, dword ptr [ebx + 0x1c]
        test eax, eax
        je   c_out
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x64]
        test al, al
        jne  c_out
        mov  eax, dword ptr [ebx + 0x1c]
        cmp  dword ptr [eax + 0x5c], 0
        jle  c_out
        mov  dl, byte ptr [eax + 0x45]
        mov  ecx, dword ptr [esi + {{CTL}}]
        cmp  dl, byte ptr [ecx + 0xed]
        jne  c_out
        mov  edx, {RALLY:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        je   c_out
        mov  dword ptr [ebx + 0x34], {RALLY:#x}
        mov  dword ptr [ebx + 0x38], -1
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        push eax
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx edx, al
        pop  ecx
        mov  eax, ebx
        call {T_ABRANGEDTC:#x}
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x100]
    c_out:
        or   eax, -1
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "esi", {"CTL": T_VAR_CTL})


def build_te(va):
    src = f"""
        mov  eax, dword ptr [ebp - 4]
        cmp  dword ptr [eax + 0x14], {RALLY:#x}
        jne  t_vanilla
        mov  eax, dword ptr [eax + 0x10]
        test eax, eax
        je   t_done
        push eax
        {{ANC}}
        mov  ecx, dword ptr [ecx + {{GETABIL}}]
        add  ecx, {E_STUB_EFFECT - GETABILITY:#x}
        mov  eax, dword ptr [esp]
        mov  edx, 1
        call ecx
        pop  eax
        mov  dword ptr [eax + 0x5c], 0
    t_done:
        mov  byte ptr [ebp - 9], 1
        jmp  {TE_EXIT:#x}
    t_vanilla:
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x10]
        jmp  {TE_BACK:#x}
    """
    return pic(src, va, "ecx", {"GETABIL": T_CELL_GETABIL})


def build_aiprop(va):
    src = f"""
        pushad
        mov  esi, dword ptr [ebp - 0x28]
        test esi, esi
        je   a_done
        cmp  dword ptr [esi + 0x5c], 1
        jl   a_done
        mov  edx, {RALLY:#x}
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        je   a_done
        {{ANC}}
        mov  ecx, dword ptr [ebx + {{GETABIL}}]
        add  ecx, {E_STUB_VALUE - GETABILITY:#x}
        mov  eax, esi
        mov  edx, 1
        call ecx
        test eax, eax
        jle  a_done
        mov  edi, eax
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x88]
        movsx eax, al
        test eax, eax
        jle  a_done
        push eax
        push esi
        push esi
        mov  edx, edi
        xor  ecx, ecx
        mov  eax, dword ptr [ebp - 4]
        call {T_DV2DEV:#x}
        test eax, eax
        jle  a_done
        mov  edi, eax
        mov  eax, dword ptr [ebp - 4]
        inc  dword ptr [eax + 0x2c]
        mov  eax, dword ptr [esi + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        push eax
        push edi
        push {RALLY:#x}
        push 0
        push esi
        push esi
        mov  eax, dword ptr [esi + 0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx ecx, al
        mov  dl, 1
        mov  eax, dword ptr [ebp - 4]
        call {T_CREATEMOVE:#x}
    a_done:
        popad
        mov  eax, dword ptr [ebp - 0x38]
        mov  eax, dword ptr [eax + 8]
        jmp  {AI_BACK:#x}
    """
    return pic(src, va, "ebx", {"GETABIL": T_CELL_GETABIL})


def t_layout():
    caves, va = [], T_SLOT[0]
    for n, fn in (("rally_click", build_click), ("cave_te", build_te), ("cave_aiprop", build_aiprop)):
        b = fn(va)
        caves.append((n, va, b))
        va = (va + len(b) + 0xF) & ~0xF
    assert caves[0][1] == T_CLICK
    return {n: v for n, v, _b in caves}, caves


# ================================================================ AoWz.exe cave
def build_xclick(va):
    return asm(f"""
        cmp  edx, {RALLY:#x}
        je   x_rally
        jmp  {X_THUNK:#x}
    x_rally:
        mov  ecx, dword ptr [{X_CELL_SELECT:#x}]
        sub  ecx, {T_SELECTABILITY:#x}
        add  ecx, {T_CLICK:#x}
        jmp  ecx
    """, va)


# ================================================================ checks
def check_ids():
    d = open(EPACK, "rb").read()
    _e, secs = P.sections(d)
    used = []
    for vs, sva, rs, ra in secs:
        for i in range(ra, ra + rs - 5):
            if d[i] == 0xE8:
                src = P.IMAGE_BASE + sva + (i - ra)
                if src + 5 + struct.unpack_from("<i", d, i + 1)[0] == CEA:
                    for k in range(5, 30):
                        if d[i - k] == 0xB8:
                            used.append((struct.unpack_from("<I", d, i - k + 1)[0], src))
                            break
    lo, hi = E_SLOT
    clash = [(i, s) for i, s in used if i in (RALLY, RALLIED) and not lo <= s < hi]
    if clash:
        sys.exit("ABORT: CreateEnhancementAbility at %08X also registers %#x" % (clash[0][1], clash[0][0]))
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    import ability_names
    named = ability_names.names()
    for aid, nm in ((RALLY, NAME_RALLY), (RALLIED, NAME_RALLIED)):
        if named.get(aid, nm) != nm:
            sys.exit("ABORT: ability_names gives %#x to %r" % (aid, named[aid]))
    rd = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    V = rd(CELL_TENH)
    cn = rd(V - 0x20)
    assert rd(V - 0x40) == V and cn - V == VMT_SLOTS, "TEnhancementAbility's VMT is not %#x slots" % VMT_SLOTS
    _e, secs = P.sections(d)
    vs, sva, rs, ra = secs[0]
    assert all(P.IMAGE_BASE + sva <= rd(V + 4 * k) < P.IMAGE_BASE + sva + vs for k in range(VMT_SLOTS // 4))
    assert rd(V + 0xA0) == 0x5574EF24 and rd(V + 0xA4) == 0x5574EF28, "+0xA0/+0xA4 are not TAbility's fc pair"
    print("  ids %#x/%#x free of other registrations; TEnhancementAbility VMT %08X, %d slots" % (
        RALLY, RALLIED, V, VMT_SLOTS // 4))


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


E_AT, E_CAVES = e_layout()
T_AT, T_CAVES = t_layout()
# entry points, asserted against the layout on every run (and read by rng_audit.py --owners)
ENTRY = {"cave_fcpre": 0x558B2410, "cave_fcexec": 0x558B2470, "cave_morale": 0x558B2480,
         "rally_value": 0x558B24A0, "rally_effect": 0x558B27A0, "cave_reg": 0x558B2920,
         "rally_click": 0x0043B900, "cave_te": 0x0043B9A0, "cave_aiprop": 0x0043B9F0}
RNG_SITES = (0x558B2895, 0x558B28A9)            # rally_effect: P1 synced (tactical), P2 raw (auto)
assert all({**E_AT, **T_AT}[n] == va for n, va in ENTRY.items()), "the cave layout moved"
call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
E_HOOKS = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, E_AT["cave_reg"])),
           (M_SITE, M_VAN, call_to(M_SITE, E_AT["cave_morale"]) + b"\x90")]
E_INTERIOR = [(M_SITE, M_SITE + 6, 0x5577F058, 0x5577F178)]
T_HOOKS = [(TE_SITE, TE_VAN, jmp_to(TE_SITE, T_AT["cave_te"], 6)),
           (AI_SITE, AI_VAN, jmp_to(AI_SITE, T_AT["cave_aiprop"], 6))]
T_INTERIOR = [(TE_SITE, TE_SITE + 6, TE_FN[0], TE_FN[1]), (AI_SITE, AI_SITE + 6, AI_FN[0], AI_FN[1])]
X_CAVES = [("cave_click", X_SLOT[0], build_xclick(X_SLOT[0]))]
X_HOOKS = [(s, call_to(s, X_THUNK), call_to(s, X_SLOT[0])) for s in X_SITES]


def go(argv):
    module(EPACK, 0x55700000)
    run("build_rally [AoWEPACK]", E_HOOKS, E_CAVES, E_SLOT, E_INTERIOR, argv)
    module(TCPCK, 0x00400000)
    run("build_rally [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, T_INTERIOR, argv)
    module(EPACK, 0x55700000)
    XP.run("build_rally [AoWz.exe]", X_HOOKS, X_CAVES, X_SLOT, argv)


if __name__ == "__main__":
    check_ids()
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])   # every module verifies first
        print("\n" + "=" * 60)
    go(argv)
