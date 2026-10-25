#!/usr/bin/env python
r"""
build_regen_spell.py -- Regeneration, a Water tier-1 unit enchantment: the unit heals fully at the
start of each turn, as the Regeneration ability (0x31) does.  AoWEPACK.dpl.  Owner's design
2026-10-22: Water, tier 1, 20 mana, upkeep 2.

THE SPELL (id 79) -- a TStoneSkin INSTANCE, no new class (05-spells-added.md, "The recipe")
    Built at package init by TStoneSkin.Create (classref cell 0x557E5624, `xor ecx,ecx / mov dl,1`
    as RegisterUnitSpells does), then: name "Regeneration" (LStrAsg of a literal), id 79, mana 20,
    upkeep [+0x1C] 2, research 40, sphere 6 (Water), tier 1.  Spells.pfs record 89
    (build_regen_spell_pfs.py) carries the same numbers, the description and the icon, and wins
    once a set is loaded.  Id 79 is the first of the free strategic ids 79-99: no record, no code
    loads it, and SpellTypes[79] in AoWTCPCK is 0 -- so it is cast on the world map only, which is
    where Regeneration acts (Stone Skin's own byte is 7: castable in battle).
    Registered at 0x557E8E3A, the last `call RegisterSpell` in RegisterUnitSpells (Dark Gift's;
    EBX = the control), replayed first.

    TStoneSkin hard-codes its enchantment 0x99 in three places; the spell's own id [+0x10] picks:
      X1  0x557E6D15  ExecuteSpell `mov edx,0x99` (5 B) -> call cave_sel   EBX = the spell
      X2  0x557E6D28  ExecuteSpell `mov edx,0x99` (5 B) -> call cave_sel   (EDX = 0x53 for id 79)
      V   0x557E6D64  ValidTargetUnit entry `push ebx / push esi / mov esi,ecx / mov ecx,esi` (6 B)
          -> jmp cave_vtu + nop: for id 79, TUnitSpell.ValidTargetUnit and then refuse a unit that
          already regenerates (0x31) or already carries this enchantment (0x53); every other id
          replays the four instructions and rejoins at 0x557E6D6A.

THE ENCHANTMENT (ability 0x53) -- a TUnitEnchantmentAbility INSTANCE
    Built by the base constructor TUnitEnchantmentAbility.Create @0x55765518 (class pointer = its
    VMT 0x55722364, reached by delta; type 4, mask 0, as every unit enchantment), then name
    "Regeneration" and id 0x53.  A base-class instance has no Remove override, which is right: no
    terrain or protection to undo when it ends.  Dispellable and counted by Magebane, like every
    enchantment.  Registered at 0x557BCC6D, Holy Champion's `call RegisterAbility` in
    RegisterPassiveAbilities (EBX = the control), replayed first.  Id 0x53 is a verified gap below
    0xAA (nil slot, no record, no code loads it, category 0), and under the 0xCD save-tag ceiling
    that an enchantment's data record needs.  Ability.pfs record 93 (build_regen_spell_pfs.py).

THE EFFECT
    R  0x55780DA6  TAbstractUnit.NewTurn's `call [ecx+0x148]` for 0x31 (6 B) -> call cave_regen + nop:
       the vanilla query, then the same query for 0x53.  Either one takes vanilla's full-heal
       branch (0x55780DDA); neither falls to the partial overnight heal.  ESI = the unit.

RNG none.  Slot 0x558B5C00-0x558B5FFF, exclusive.  PIC.  Surgical --undo.

Unproven: the AI casts it through TStoneSkin's inherited AI (weight [+0x30] 5, Stone Skin's).

    python build_scripts/build_regen_spell.py            dry run + state
    python build_scripts/build_regen_spell.py --apply
    python build_scripts/build_regen_spell.py --undo
    python build_scripts/build_regen_spell.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run
from piccave import pic, ansistr

SPELL_ID, SPELL_NAME = 79, "Regeneration"
ENCH, ENCH_NAME = 0x53, "Regeneration"
REGEN = 0x31
STONESKIN_ENCH = 0x99
MANA, UPKEEP, RESEARCH, SPHERE, TIER = 20, 2, 40, 6, 1

SLOT = (0x558B5C00, 0x558B6000)
REGISTER_ABIL, REGISTER_SPELL = 0x55750238, 0x55779B40
LSTRASG = 0x55701150
TUEA_CREATE, TUEA_VMT = 0x55765518, 0x55722364
STONESKIN_CREATE, STONESKIN_CELL = 0x557E6C2C, 0x557E5624
UNITSPELL_VTU = 0x5577ACAC
V_ABENABLED = 0x148
SITES = {   # name: (va, vanilla, function lo, hi)
    "sel1":  (0x557E6D15, bytes.fromhex("ba99000000"), 0x557E6CF4, 0x557E6D62),
    "sel2":  (0x557E6D28, bytes.fromhex("ba99000000"), 0x557E6CF4, 0x557E6D62),
    "vtu":   (0x557E6D64, bytes.fromhex("53568bf18bce"), 0x557E6D64, 0x557E6D95),
    "regen": (0x55780DA6, bytes.fromhex("ff9148010000"), 0x55780D4C, 0x55780E18),
}
R_ABIL, R_SPELL = 0x557BCC6D, 0x557E8E3A
VTU_RESUME = 0x557E6D6A


def build_sel(va):
    return asm(f"""
        mov  edx, {STONESKIN_ENCH:#x}
        cmp  dword ptr [ebx + 0x10], {SPELL_ID}
        jne  s_out
        mov  edx, {ENCH:#x}
    s_out:
        ret
    """, va)


def build_vtu(va):
    """EAX = the spell, EDX = (passed through), ECX = the unit; returns AL; plain ret."""
    return asm(f"""
        cmp  dword ptr [eax + 0x10], {SPELL_ID}
        jne  v_vanilla
        push ebx
        push esi
        mov  esi, ecx
        call {UNITSPELL_VTU:#x}
        test al, al
        je   v_no
        mov  eax, esi
        mov  edx, {REGEN:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ABENABLED:#x}]
        test al, al
        jne  v_no
        mov  eax, esi
        mov  edx, {ENCH:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ABENABLED:#x}]
        test al, al
        jne  v_no
        mov  al, 1
        jmp  v_out
    v_no:
        xor  eax, eax
    v_out:
        pop  esi
        pop  ebx
        ret
    v_vanilla:
        push ebx
        push esi
        mov  esi, ecx
        mov  ecx, esi
        jmp  {VTU_RESUME:#x}
    """, va)


def build_regen(va):
    """Replaces NewTurn's `call [ecx+0x148]` (EAX = the unit, EDX = 0x31, ECX = its VMT)."""
    return asm(f"""
        call dword ptr [ecx + {V_ABENABLED:#x}]
        test al, al
        jne  r_out
        mov  eax, esi
        mov  edx, {ENCH:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ABENABLED:#x}]
    r_out:
        ret
    """, va)


def build_reg_ench(va):
    """Replays Holy Champion's RegisterAbility, then builds + registers the enchantment 0x53."""
    src = f"""
        call {REGISTER_ABIL:#x}
        {{ANC}}
        push ecx
        lea  eax, [ecx + {{VMT}}]
        xor  ecx, ecx
        mov  dl, 1
        call {TUEA_CREATE:#x}
        pop  ecx
        push eax
        lea  edx, [ecx + {{NAME}}]
        add  eax, 8
        call {LSTRASG:#x}
        pop  eax
        mov  dword ptr [eax + 0xC], {ENCH:#x}
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER_ABIL:#x}
        ret
    """
    return pic(src, va, "ecx", {"VMT": TUEA_VMT, "NAME": ("TAIL", 8)}, ansistr(ENCH_NAME))


def build_reg_spell(va):
    """Replays Dark Gift's RegisterSpell, then builds + registers spell 79 from TStoneSkin."""
    src = f"""
        call {REGISTER_SPELL:#x}
        {{ANC}}
        push ecx
        mov  eax, dword ptr [ecx + {{CELL}}]
        xor  ecx, ecx
        mov  dl, 1
        call {STONESKIN_CREATE:#x}
        pop  ecx
        push eax
        lea  edx, [ecx + {{NAME}}]
        add  eax, 8
        call {LSTRASG:#x}
        pop  eax
        mov  dword ptr [eax + 0x10], {SPELL_ID}
        mov  dword ptr [eax + 0x14], {MANA}
        mov  dword ptr [eax + 0x18], {RESEARCH}
        mov  dword ptr [eax + 0x1C], {UPKEEP}
        mov  byte ptr [eax + 0x20], {SPHERE}
        mov  byte ptr [eax + 0x21], {TIER}
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER_SPELL:#x}
        ret
    """
    return pic(src, va, "ecx", {"CELL": STONESKIN_CELL, "NAME": ("TAIL", 8)}, ansistr(SPELL_NAME))


def layout():
    caves, at, va = [], {}, SLOT[0]

    def put(n, b):
        nonlocal va
        caves.append(("cave_" + n, va, b))
        at[n] = va
        va = (va + len(b) + 0xF) & ~0xF

    put("sel", build_sel(va))
    put("vtu", build_vtu(va))
    put("regen", build_regen(va))
    put("reg_ench", build_reg_ench(va))
    put("reg_spell", build_reg_spell(va))
    return at, caves


def checks():
    d = open(P.TARGET, "rb").read()
    rb = lambda va, n: d[P.va2off(d, va):P.va2off(d, va) + n]
    rd = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    for va, want, what in (
            (0x557BCC6B, bytes.fromhex("8bc3"), "`mov eax,ebx` before the ability registration site"),
            (0x557E8E38, bytes.fromhex("8bc3"), "`mov eax,ebx` before the spell registration site"),
            (0x557E8E2C, bytes.fromhex("a15c677e55"), "Dark Gift's classref load before the spell site"),
            (0x55780D9D, bytes.fromhex("ba31000000"), "NewTurn's `mov edx,0x31`"),
            (0x557E6D0B, bytes.fromhex("ff979c000000"), "Stone Skin ExecuteSpell's `call [edi+0x9c]`")):
        if rb(va, len(want)) != want:
            sys.exit("ABORT: %s is not at %08X" % (what, va))
    if rd(STONESKIN_CELL) != STONESKIN_CELL + 0x40:
        sys.exit("ABORT: %08X is not TStoneSkin's class cell" % STONESKIN_CELL)
    if rd(TUEA_VMT - 0x40) != TUEA_VMT or rd(TUEA_VMT - 0x1C) != 0x28:
        sys.exit("ABORT: %08X is not TUnitEnchantmentAbility's VMT" % TUEA_VMT)
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    import ability_names, pfs
    if ENCH in ability_names.names() and ability_names.names()[ENCH] != ENCH_NAME:
        sys.exit("ABORT: ability_names gives %#x another name" % ENCH)
    try:                                    # informational only; a scratch tree has no Release/
        keys = {rid for rid, _b in pfs.load("spells.pfs")[0]}
    except (OSError, ValueError):
        keys = None
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:            # no other code stores spell id 79 into a spell
        for i in range(ra, ra + rs - 7):
            if d[i:i + 3] == b"\xc7\x40\x10" and struct.unpack_from("<I", d, i + 3)[0] == SPELL_ID:
                src = P.IMAGE_BASE + sva + (i - ra)
                if not SLOT[0] <= src < SLOT[1]:
                    sys.exit("ABORT: %08X also stores spell id %d" % (src, SPELL_ID))
    print("  spell id %d: Spells.pfs record %d %s" % (SPELL_ID, SPELL_ID + 10,
          "unread" if keys is None else "present" if SPELL_ID + 10 in keys else "absent"))


AT, CAVES = layout()
call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
HOOKS = [(R_ABIL, call_to(R_ABIL, REGISTER_ABIL), call_to(R_ABIL, AT["reg_ench"])),
         (R_SPELL, call_to(R_SPELL, REGISTER_SPELL), call_to(R_SPELL, AT["reg_spell"])),
         (SITES["sel1"][0], SITES["sel1"][1], call_to(SITES["sel1"][0], AT["sel"])),
         (SITES["sel2"][0], SITES["sel2"][1], call_to(SITES["sel2"][0], AT["sel"])),
         (SITES["vtu"][0], SITES["vtu"][1], jmp_to(SITES["vtu"][0], AT["vtu"], 6)),
         (SITES["regen"][0], SITES["regen"][1], call_to(SITES["regen"][0], AT["regen"]) + b"\x90")]
INTERIOR = [(va, va + len(van), lo, hi) for _n, (va, van, lo, hi) in SITES.items()]
ENTRY = {"sel": 0x558B5C00, "vtu": AT["vtu"], "regen": AT["regen"], "reg_ench": AT["reg_ench"],
         "reg_spell": AT["reg_spell"]}
assert AT == ENTRY, "the cave layout moved"

if __name__ == "__main__":
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in AT.items()))
    checks()
    run("build_regen_spell", HOOKS, CAVES, SLOT, INTERIOR, sys.argv[1:])
