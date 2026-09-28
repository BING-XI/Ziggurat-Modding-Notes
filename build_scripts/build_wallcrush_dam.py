#!/usr/bin/env python
r"""
build_wallcrush_dam.py -- Wall Crushing rolls the carrying unit's DAM against a wall, in place of the
flat 12.  AoWEPACK.dpl + AoWTCPCK.dpl.  Owner's ruling 2026-09-27.  ATK stays 12.

Every Wall Crushing damage figure was the constant 12 (vanilla 6, doubled by the DAM/HP pass).  Each
reader below now takes the attacker's GetDamage instead.  All of them land on the same number: the
tactical and auto-resolve unit's GetDamage (TCombatUnit +0x78) forwards to the strategic unit's
(TAbstractUnit +0xC8), so the info card, the AI estimates, auto-resolve and manual combat agree.

AoWEPACK.dpl -- TWallCrushingAbility, attacker by method:
    GetDamageValue       0x557685B8  EDX on entry, lost by the LimitedDV call   strategic +0xC8
    GetDamageValueEx     0x55768618  EDX on entry, lost                          strategic +0xC8
    fcGetDamageValueEx   0x557686E8  [ebp-8]                                    combat    +0x78
    tcGetDamageValueEx   0x557687C8  [ebp-8]                                    combat    +0x78
    GetCombatInfo        0x557688A8  EDX (info card byte [rec+2])               strategic +0xC8
    fcExecuteCombatCommand 0x557688DC ESI (auto-resolve: CreateDamageCA dmg)    combat    +0x78
    GetOffensiveStrength 0x55768924  EBX (AI army strength)                     strategic +0xC8
AoWTCPCK.dpl:
    TCAbTouchMoveTE.LastMove  call ExecuteDamageRole @0x0040A27D, dmg = TCDamage[0]; attacker is
    [[ebp-4]+0x1C] (TTacticalCombatUnit, whose +0x78 is imported TCombatUnit.GetDamage).  TCDamage[0]
    has no other reader (xref of slot 0x004693FC: the other three read TCDamage[1], fire).

Mechanism.  Every damage call is RETARGETED (rel32 only) to a thunk that swaps the damage argument
and tail-jumps to the original callee: StatisticsToLimitedDV 0x55726094 (EDX), StatisticsToMaxDamage
0x55725FE0 (EAX), CreateDamageCA 0x55729F18 (stack dword at [esp+8]), the GetOffensiveStrength
helper 0x55726100 (EDX), ExecuteDamageRole thunk 0x004024F4 (EAX).  No manifest-owned immediate
(damhp_manifest / fivepct_manifest) is written; the 12s stay in place as the nil fallback.
GetDamageValue/GetDamageValueEx lose the attacker before their call, so their ENTRY jumps to a cave
that stashes EDX on the stack and calls the untouched body as a subroutine (prologue replayed):
    GetDamageValue    thunk reads the stash at [esp+0x20] (5 args + saved ebx + return)
    GetDamageValueEx  args re-pushed; the stash sits at [ebp+0x10], body's `ret 8` returns to the cave
GetCombatInfo has no call to retarget: TWallCrushingAbility's VMT slot +0x104 (0x55721418, .reloc
kept -- the new value is in-image) points at a wrapper that runs the original then overwrites [rec+2].

A nil strategic unit keeps 12 (GetDamageValue/Ex, GetCombatInfo).

RNG: no draw added.  ExecuteDamageRole draws once only when damage >= 1, so the draw count now
follows DAM -- replicated unit state, equal on every peer.  P2 COMBAT RAW, unchanged: host
ExecuteDamageRole is in the RAW list.

Couplings.  build_ai_ram_breach.py reads the target lists these estimates fill; rams (DAM 2) now
carry a sixth of their former wall value.  Inioch's share2 patch_wallcrush_leveled_v1.py /
patch_wallcrush_preview_v1.py replace the same methods -- never apply them over this.

Caves: AoWEPACK 0x55851900-0x55851AFF exclusive; AoWTCPCK 0x0043AC00-0x0043AC3F exclusive.
PIC: rel32 and register-indirect only.  Surgical --undo.

    python build_scripts/build_wallcrush_dam.py            dry run + state, both modules
    python build_scripts/build_wallcrush_dam.py --apply
    python build_scripts/build_wallcrush_dam.py --undo
    python build_scripts/build_wallcrush_dam.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

EPACK = os.path.join(P.GAME, "AoWEPACK.dpl")
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")

LDV, MXD, CDCA, OFS = 0x55726094, 0x55725FE0, 0x55729F18, 0x55726100
EDR_THUNK = 0x004024F4
STRAT, COMBAT = 0xC8, 0x78                       # GetDamage slot: TAbstractUnit / TCombatObject

E_SLOT = (0x55851900, 0x55851B00)
T_SLOT = (0x0043AC00, 0x0043AC40)
VMT_INFO = 0x55721418                            # TWallCrushingAbility VMT +0x104
GCI = 0x557688A8                                 # TWallCrushingAbility.GetCombatInfo


def call(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


# --- AoWEPACK caves --------------------------------------------------------------------------
def th_edx(va, att, slot, target):
    """Replace EDX (damage) with [att].GetDamage; keep EAX/ECX; nil keeps EDX."""
    return asm(f"""
        push eax
        push ecx
        mov eax, {att}
        test eax, eax
        je t_keep
        mov edx, dword ptr [eax]
        call dword ptr [edx + {slot:#x}]
        movsx edx, al
    t_keep:
        pop ecx
        pop eax
        jmp {target:#x}
    """, va)


def th_eax(va, att, slot, target):
    """Replace EAX (damage) with [att].GetDamage; keep ECX/EDX; nil keeps EAX."""
    return asm(f"""
        push ecx
        push edx
        push eax
        mov eax, {att}
        test eax, eax
        je t_nil
        mov edx, dword ptr [eax]
        call dword ptr [edx + {slot:#x}]
        movsx eax, al
        add esp, 4
        jmp t_out
    t_nil:
        pop eax
    t_out:
        pop edx
        pop ecx
        jmp {target:#x}
    """, va)


def e_caves():
    specs = [
        ("wc_gdv", lambda va: asm("""
            push edx
            call g_body
            add esp, 4
            ret
        g_body:
            push ebx
            mov ebx, ecx
            mov eax, ebx
            jmp 0x557685BD
        """, va)),
        ("wc_gdvx", lambda va: asm("""
            push edx
            push dword ptr [esp + 0xC]
            push dword ptr [esp + 0xC]
            call x_body
            add esp, 4
            ret 8
        x_body:
            push ebp
            mov ebp, esp
            push ebx
            push esi
            jmp 0x5576861D
        """, va)),
        ("th_ldv_s20", lambda va: th_edx(va, "dword ptr [esp + 0x28]", STRAT, LDV)),
        ("th_ldv_bp10", lambda va: th_edx(va, "dword ptr [ebp + 0x10]", STRAT, LDV)),
        ("th_mxd_bp10", lambda va: th_eax(va, "dword ptr [ebp + 0x10]", STRAT, MXD)),
        ("th_ldv_bm8", lambda va: th_edx(va, "dword ptr [ebp - 8]", COMBAT, LDV)),
        ("th_mxd_bm8", lambda va: th_eax(va, "dword ptr [ebp - 8]", COMBAT, MXD)),
        ("th_ofs", lambda va: th_edx(va, "ebx", STRAT, OFS)),
        ("th_cdca", lambda va: asm(f"""
            push eax
            push ecx
            push edx
            mov eax, esi
            test eax, eax
            je c_keep
            mov edx, dword ptr [eax]
            call dword ptr [edx + {COMBAT:#x}]
            movsx eax, al
            mov dword ptr [esp + 0x14], eax
        c_keep:
            pop edx
            pop ecx
            pop eax
            jmp {CDCA:#x}
        """, va)),
        ("wc_info", lambda va: asm(f"""
            push edx
            push ecx
            call {GCI:#x}
            pop ecx
            pop edx
            test edx, edx
            je i_out
            push ecx
            mov eax, edx
            mov edx, dword ptr [eax]
            call dword ptr [edx + {STRAT:#x}]
            pop ecx
            mov byte ptr [ecx + 2], al
        i_out:
            ret
        """, va)),
    ]
    va, caves = E_SLOT[0], []
    for name, gen in specs:
        blob = gen(va)
        caves.append((name, va, blob))
        va = (va + len(blob) + 0xF) & ~0xF
    assert va <= E_SLOT[1], "AoWEPACK caves overflow the slot"
    return caves


E_CAVES = e_caves()
at = {n: v for n, v, _b in E_CAVES}

# (site, current callee, thunk)
E_CALLS = [
    (0x5576860C, LDV, "th_ldv_s20"),     # GetDamageValue
    (0x5576867D, LDV, "th_ldv_bp10"),    # GetDamageValueEx
    (0x557686A7, MXD, "th_mxd_bp10"),
    (0x5576875C, LDV, "th_ldv_bm8"),     # fcGetDamageValueEx
    (0x55768783, MXD, "th_mxd_bm8"),
    (0x5576883C, LDV, "th_ldv_bm8"),     # tcGetDamageValueEx
    (0x55768863, MXD, "th_mxd_bm8"),
    (0x55768900, CDCA, "th_cdca"),       # fcExecuteCombatCommand
    (0x55768948, OFS, "th_ofs"),         # GetOffensiveStrength
]
E_HOOKS = [(0x557685B8, bytes.fromhex("538bd98bc3"), jmp_to(0x557685B8, at["wc_gdv"], 5)),
           (0x55768618, bytes.fromhex("558bec5356"), jmp_to(0x55768618, at["wc_gdvx"], 5)),
           (VMT_INFO, struct.pack("<I", GCI), struct.pack("<I", at["wc_info"]))]
E_HOOKS += [(s, call(s, dst), call(s, at[th])) for s, dst, th in E_CALLS]
E_INTERIOR = [(0x557685B8, 0x557685BD, 0x557685B8, 0x55768613),
              (0x55768618, 0x5576861D, 0x55768618, 0x557686DE)]

# --- AoWTCPCK cave ---------------------------------------------------------------------------
T_CAVES = [("th_lastmove", T_SLOT[0],
            th_eax(T_SLOT[0], "dword ptr [ebp - 4]\n mov eax, dword ptr [eax + 0x1C]",
                   COMBAT, EDR_THUNK))]
T_HOOKS = [(0x0040A27D, call(0x0040A27D, EDR_THUNK), call(0x0040A27D, T_SLOT[0]))]


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def go(argv):
    module(EPACK, 0x55700000)
    run("build_wallcrush_dam [AoWEPACK]", E_HOOKS, E_CAVES, E_SLOT, E_INTERIOR, argv,
        reloc_ok=(VMT_INFO,))
    module(TCPCK, 0x00400000)
    run("build_wallcrush_dam [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, [], argv)


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])   # both modules verify first
        print("\n" + "=" * 60)
    go(argv)
