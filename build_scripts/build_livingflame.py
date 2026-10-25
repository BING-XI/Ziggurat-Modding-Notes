#!/usr/bin/env python
r"""
build_livingflame.py -- Living Flame: fire HEALS a unit whose life essence is elemental fire.
AoWEPACK.dpl only.  Owner's design 2026-10-22.

TWO ABILITIES, ONE NAME
    0xA3  Fire Halo's enchantment, renamed Living Flame (the spell too: one Dict/ResStr row,
          "Fire Halo" -> "Living Flame", since both load AoWE.FireAuraRStr).  Keeps its vanilla
          effects: fire immunity, fire strike, lava movement.
    0x52  Living Flame, a plain TEnhancementAbility passive registered here, carried by Fire
          Elemental (226), Fire Sprite (228) and Salamander (58).  An enchantment cannot be
          innate (build_liquidbody.py, WHY NOT LIQUID FORM: GetSourceName dereferences the cast
          record with no nil check, Dispel and Magebane count it), so the creatures get the
          passive.  Heroes may learn it: mask 0x03FF, Hero Offers 0 % except Azracs 10 %, cost 20
          (owner 2026-10-22; Ability.pfs record 92 tag 6/9, build_livingflame_pfs.py).
    Either one makes fire heal.  The passive adds nothing else: the three creatures already carry
    Fire Immunity, which is what makes a fire hit "fully immune" below.

IN BATTLE (here) -- tactical combat and auto-resolve alike
    TCombatObject.ExecuteDamageRole @0x557269F0 (DEF) and ...Ex @0x55726A6C (RES) are the only
    damage rolls; both start `mask_left = ~GetImmunityTypes & mask` and return 0 at once when it
    is 0 -- a fully immune hit makes no roll at all.  The hooks replace that computation
    (`mov esi,eax / not esi / and si,[mask]`, 8 B, no .reloc) with a call: the cave recomputes
    ESI exactly, and when it is 0, the hit carries fire (mask bit 0) and the target holds 0xA3 or
    0x52 (combat VMT +0xA8, the item-aware query; a wall answers 0), it heals the target by
    ExecuteDamageRole_500(damage, margin 8), never less than 1 -- the map rule of
    build_firefeed.py v2: the damage roll's size, no to-hit roll -- through GetHitPoints +0x88 /
    GetHits +0x84 / SetHitPoints +0x8C, summed in 32 bits and capped at max HP first (the setter
    takes a byte).  The roll then returns 0 as vanilla does for an immune target, so no hit,
    flinch or Burning follows.  A hit that is fire AND something the unit is not immune to
    (fire + physical) is not fully immune: it damages as vanilla, no heal.
        DEF  0x55726A0A  8B F0 F7 D6 66 23 75 08 -> call cave_def + 3 nop   resume 0x55726A12
        RES  0x55726A86  8B F0 F7 D6 66 23 75 0C -> call cave_res + 3 nop   resume 0x55726A8E
    ON THE MAP: build_firefeed.py (v3 tests 0xA3 / 0x52 instead of unit index 226 / 228).

RNG  P2 COMBAT RAW: the heal draws once through ExecuteDamageRole_500 @0x55725EAC, the host's own
     roller (its RandInt is in the RAW list; build_combatlog_strikes.py's wrapper at 0x55725EBC),
     where vanilla drew nothing for an immune target.  Deterministic on every peer.

REGISTRATION (package init -- prove by launching the exe)
    0x557BCC84 `call RegisterAbility` (the last still-direct one in RegisterPassiveAbilities,
    EBX = the control) -> piccave.enhancement_reg: CreateEnhancementAbility(0x52, "Living Flame",
    mask 0x03FF) + RegisterAbility.  Id 0x52 is a verified gap below 0xAA (nil registry slot, no
    record, no code loads it as an ability id in AoWEPACK, AoWTCPCK or AoWz.exe, category 0), so
    no loop ceiling moves.

Unproven: no "+N" number is drawn for a heal in battle (the roll reports 0, as for any immune hit).

Slot 0x558B5800-0x558B5BFF, exclusive.  PIC.  Surgical --undo.

    python build_scripts/build_livingflame.py            dry run + state
    python build_scripts/build_livingflame.py --apply
    python build_scripts/build_livingflame.py --undo
    python build_scripts/build_livingflame.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import enhancement_reg

LIVING_FLAME, NAME, MASK = 0x52, "Living Flame", 0x03FF
FIRE_AURA = 0xA3                                  # Fire Halo's enchantment, now "Living Flame"
SLOT = (0x558B5800, 0x558B5C00)
R_SITE = 0x557BCC84
REGISTER, CEA = 0x55750238, 0x5576601C
ROLL = 0x55725EAC                                 # AoWE.ExecuteDamageRole_500 (EAX dmg, EDX margin)
NOMISS_MARGIN = 8                                 # build_firefeed.py v2's value
V_HITS, V_HP, V_SETHP, V_ABENABLED = 0x84, 0x88, 0x8C, 0xA8
FIRE_BIT = 0x01
SITES = {   # name: (va, vanilla, mask displacement, resume, function lo, hi)
    "def": (0x55726A0A, bytes.fromhex("8bf0f7d666237508"), 0x08, 0x55726A12, 0x557269F0, 0x55726A68),
    "res": (0x55726A86, bytes.fromhex("8bf0f7d66623750c"), 0x0C, 0x55726A8E, 0x55726A6C, 0x55726B00),
}


def build_heal(va):
    """EBX = the target combat object, EBP = the roll's frame ([ebp-8] = damage).  Keeps EBX/ESI/
    EDI/EBP (every call below is Delphi-register, which preserves them)."""
    return asm(f"""
        mov  eax, ebx
        mov  edx, {FIRE_AURA:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ABENABLED:#x}]
        test al, al
        jne  h_go
        mov  eax, ebx
        mov  edx, {LIVING_FLAME:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ABENABLED:#x}]
        test al, al
        je   h_out
    h_go:
        mov  eax, dword ptr [ebp - 8]
        mov  edx, {NOMISS_MARGIN}
        call {ROLL:#x}
        test eax, eax
        jne  h_amt
        mov  eax, 1
    h_amt:
        push eax
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_HP:#x}]
        movsx eax, al
        add  dword ptr [esp], eax
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_HITS:#x}]
        movsx eax, al
        pop  edx
        cmp  edx, eax
        jle  h_set
        mov  edx, eax
    h_set:
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_SETHP:#x}]
    h_out:
        ret
    """, va)


def build_site(va, disp, heal):
    """Replays `mov esi,eax / not esi / and si,[ebp+disp]` (EAX = GetImmunityTypes) and heals when
    nothing is left of the mask and the hit carries fire.  ESI is recomputed exactly; the flags
    after the call are not read (the host reloads AX and compares again)."""
    return asm(f"""
        mov  esi, eax
        not  esi
        and  si, word ptr [ebp + {disp:#x}]
        jne  s_out
        test byte ptr [ebp + {disp:#x}], {FIRE_BIT:#x}
        je   s_out
        call {heal:#x}
    s_out:
        ret
    """, va)


def layout():
    caves, at, va = [], {}, SLOT[0]

    def put(n, b):
        nonlocal va
        caves.append(("cave_" + n, va, b))
        at[n] = va
        va = (va + len(b) + 0xF) & ~0xF

    put("heal", build_heal(va))
    for n in ("def", "res"):
        put(n, build_site(va, SITES[n][2], at["heal"]))
    put("reg", enhancement_reg(va, REGISTER, CEA, LIVING_FLAME, NAME, MASK))
    return at, caves


def checks():
    d = open(P.TARGET, "rb").read()
    rb = lambda va, n: d[P.va2off(d, va):P.va2off(d, va) + n]
    for va, want, what in (
            (0x55726A07, bytes.fromhex("ff527c"), "ExecuteDamageRole's `call [edx+0x7C]` (immunity)"),
            (0x55726A83, bytes.fromhex("ff527c"), "ExecuteDamageRoleEx's `call [edx+0x7C]` (immunity)"),
            (0x557269F9, bytes.fromhex("894df88955fc"), "ExecuteDamageRole's damage/attack spills"),
            (0x55726A75, bytes.fromhex("894df88955fc"), "ExecuteDamageRoleEx's damage/attack spills"),
            (0x557BCC82, bytes.fromhex("8bc3"), "`mov eax,ebx` before the registration site")):
        if rb(va, len(want)) != want:
            sys.exit("ABORT: %s is not at %08X" % (what, va))
    # the id must be free: no other CreateEnhancementAbility of 0x52, no other name for it
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:
        for i in range(ra, ra + rs - 5):
            if d[i] == 0xE8 and P.IMAGE_BASE + sva + (i - ra) + 5 + struct.unpack_from("<i", d, i + 1)[0] == CEA:
                for k in range(5, 30):
                    if d[i - k] == 0xB8:
                        src = P.IMAGE_BASE + sva + (i - ra)
                        if struct.unpack_from("<I", d, i - k + 1)[0] == LIVING_FLAME and not SLOT[0] <= src < SLOT[1]:
                            sys.exit("ABORT: %08X also registers %#x" % (src, LIVING_FLAME))
                        break
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    import ability_names
    if ability_names.names().get(LIVING_FLAME, NAME) != NAME:
        sys.exit("ABORT: ability_names gives %#x another name" % LIVING_FLAME)


AT, CAVES = layout()
call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
HOOKS = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, AT["reg"]))]
HOOKS += [(va, van, call_to(va, AT[n]) + b"\x90" * 3) for n, (va, van, _d, _r, _lo, _hi) in SITES.items()]
INTERIOR = [(va, va + len(van), lo, hi) for _n, (va, van, _d, _r, lo, hi) in SITES.items()]
ENTRY = {"heal": 0x558B5800, "def": AT["def"], "res": AT["res"], "reg": AT["reg"]}
assert AT == ENTRY, "the cave layout moved"

if __name__ == "__main__":
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in AT.items()))
    checks()
    run("build_livingflame", HOOKS, CAVES, SLOT, INTERIOR, sys.argv[1:])
