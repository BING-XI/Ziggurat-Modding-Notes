#!/usr/bin/env python
r"""
build_satchels.py -- Dwarven Satchels, the Earth/Fire dual tier-1 unit enchantment, and the attack
it grants, Throw Explosive Flask.  AoWEPACK.dpl half (the manual-combat half: build_satchels_tc.py).
Owner's design 2026-10-25 (05-spells-added.md, "Earth/Fire -- agreed design"): 16 mana, no upkeep,
Enchanter, castable on the map and in battle on one of your units, one per unit, kept until thrown.
The flask: 10 ATK against DEF, 15 fire damage, range 4 (band 1), one shot, a lob; the blast strikes
every unit within one hex of where it lands; one throw, then the satchel is gone.

THREE REGISTRATIONS (package init -- prove by launching the exe)
  spell 84  a TEnchantWeapon INSTANCE (classref cell 0x557E575C, Create 0x557E6D98): name "Dwarven
            Satchels", id 84, mana 16, research 80 (the single tier-2 figure: it prices Wizard's
            Tower offers), upkeep 0, sphere 7 (dual: build_dual_sphere.py's TABLE holds Earth+Fire),
            tier 1, enchantment level 2.  Spliced at RegisterUnitSpells' `call RegisterSpell`
            0x557E8E0C.  Combat flag [+0xC] = 3 from the ctor; SpellTypes[84] = 7
            (build_battlecast_unitspells.py).  Spells.pfs record 94 (build_satchels_pfs.py).
  E 0x4E    the enchantment "Dwarven Satchels": a TUnitEnchantmentAbility INSTANCE (base ctor
            0x55765518) with a run-time VMT copy (GetMem, VMT-0x40..+0x120, parent link to the
            original) whose Expand (+0xD0) and Remove (+0xD4) also set and clear F on the unit
            (owner VMT +0x50, TAbility.SetAb's own call).  So F lives exactly as long as E, through
            saves (both are ability bits) and through dispel, expiry or the throw.  Spliced at
            RegisterPassiveAbilities' `call RegisterAbility` 0x557BCC3F.  Ability.pfs record 88.
  F 0x4F    the attack "Throw Explosive Flask": a TRangedAttackAbility from the ranged ctor
            0x5576ED48 (Shoot Bolt's), ATK 10, DAM 15, 1 shot, band 1 (4 hexes), types 0x0001
            (Fire), with a run-time VMT copy whose fcExecuteCombatCommand (+0xA4) is cave_fcexec.
            Spliced at the ranged routine's `call RegisterAbility` 0x5576F7A3.  Ability.pfs record 89.
  Ids 0x4E/0x4F: registry gaps below 0xAA; re_tools/idladder.py finds them only inside generic
  range ladders (2026-10-25), so no ceiling script moves.

SITES (TEnchantWeapon hard-codes its enchantment 0x9A; the spell's own id picks)
  X1  0x557E6E81  ExecuteSpell `mov edx,0x9A` -> call cave_sel   (EBX = the spell: 84 -> 0x4E)
  X2  0x557E6E94  ExecuteSpell `mov edx,0x9A` -> call cave_sel
  V   0x557E6ED0  ValidTargetUnit entry (6 B) -> jmp cave_vtu: id 84 -> TUnitSpell.ValidTargetUnit,
                  refuse a unit that already carries E, and, for an AI caster ([player+0xA7]), a
                  unit that has a ranged attack (any held ability whose GetCombatMode, VMT +0x84,
                  is 3..5).  The vanilla unit-spell AI picks the highest-scoring valid unit, so the
                  AI satchels its strongest non-shooters (owner's rule) with no AI hook.

AUTO-COMBAT (cave_fcexec, F's fcExecuteCombatCommand)
  The vanilla shot at the command's target, then up to two other standing units of the target's
  side, picked at random, take the same strike (CreateRangedAttackCA + TCombat.ExecuteCombatAction,
  as the vanilla shot loop does), then E is removed from the thrower (E's Remove clears F).
  Auto-resolve has no positions, so "within one hex" becomes "up to two others".
  RNG: P2 COMBAT RAW (@RandInt, auto-resolve code after TCombat.Execute's re-anchor).

Slot 0x558BA800-0x558BAFFF, exclusive.  PIC.  Surgical --undo.

    python build_scripts/build_satchels.py            dry run + state
    python build_scripts/build_satchels.py --apply
    python build_scripts/build_satchels.py --undo
    python build_scripts/build_satchels.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run
from piccave import pic, ansistr

SPELL_ID, SPELL_NAME = 84, "Dwarven Satchels"
ENCH, ENCH_NAME = 0x4E, "Dwarven Satchels"
FLASK, FLASK_NAME = 0x4F, "Throw Explosive Flask"
MANA, RESEARCH, UPKEEP, SPHERE, TIER, LEVEL = 16, 80, 0, 7, 1, 2
ATK, DAM, SHOTS, BAND, TYPES, FC_ICON = 10, 15, 1, 1, 0x0001, 0x70
EXTRA = 2                                 # auto-combat: other units of the target's side struck
SLOT = (0x558BA800, 0x558BB000)

AOWHSMAP, AOWHSSET = 0x558FA040, 0x558FA044
REGISTER_ABIL, REGISTER_SPELL, LSTRASG = 0x55750238, 0x55779B40, 0x55701150
GETMEM, RANDINT = 0x55701008, 0x55701080
TUEA_CREATE, TUEA_VMT = 0x55765518, 0x55722364
TUEA_EXPAND, TUEA_REMOVE = 0x55765894, 0x557659A8
CREATE_RANGED = 0x5576ED48
RA_FCEXEC = 0x5576EB70
CREATE_RA_CA = 0x5576EAE4             # CreateRangedAttackCA(eax=ab, edx=shooter, ecx=target, [cover])
EXEC_CA = None                        # TCombat.ExecuteCombatAction, resolved below
EW_CELL, EW_CREATE = 0x557E575C, 0x557E6D98
UNITSPELL_VTU = 0x5577ACAC
GETPLAYERS = 0x557544D0
GETABILITY = 0x557501C0               # TAbilityControl.GetAbility(eax=[set+0x80], edx=id)
CD_COUNT, CD_GET = 0x55728BEC, 0x55728BF8   # TCombatData.GetCount / GetObjects
GETSIDE = 0x55726660
ISCLASS, TCU_CELL = 0x557010C0, 0x55715A54   # System.@IsClass; cell -> AoWE..TCombatUnit
VMT_NEG, VMT_LEN = 0x40, 0x120
SLOT_EXPAND, SLOT_REMOVE, SLOT_FCEXEC = 0xD0, 0xD4, 0xA4
MAX_ABIL = 0xD0

SITES = {   # name: (va, vanilla bytes, function lo, hi)
    "reg_spell": (0x557E8E0C, bytes.fromhex("e82f0df9ff"), 0x557E8C84, 0x557E8E44),
    "reg_ench":  (0x557BCC3F, bytes.fromhex("e8f435f9ff"), 0x557BC1CC, 0x557BCFCC),
    "reg_flask": (0x5576F7A3, bytes.fromhex("e8900afeff"), 0x5576F2EC, 0x5576F800),
    "sel1":      (0x557E6E81, bytes.fromhex("ba9a000000"), 0x557E6E60, 0x557E6ECE),
    "sel2":      (0x557E6E94, bytes.fromhex("ba9a000000"), 0x557E6E60, 0x557E6ECE),
    "vtu":       (0x557E6ED0, bytes.fromhex("53568bf18bce"), 0x557E6ED0, 0x557E6F14),
}


def find_exec_ca():
    """TCombat.ExecuteCombatAction: the call right after CreateRangedAttackCA in the vanilla shot
    loop of TRangedAttackAbility.fcExecuteCombatCommand."""
    d = open(P.TARGET, "rb").read()
    o = P.va2off(d, RA_FCEXEC)
    tgts = []
    for i in range(0x90):
        if d[o + i] == 0xE8:
            tgts.append(RA_FCEXEC + i + 5 + struct.unpack_from("<i", d, o + i + 1)[0])
    k = tgts.index(CREATE_RA_CA)
    return tgts[k + 1]


EXEC_CA = find_exec_ca()


def build_sel(va):
    return asm(f"""
        mov  edx, 0x9a
        cmp  dword ptr [ebx + 0x10], {SPELL_ID}
        jne  s_out
        mov  edx, {ENCH:#x}
    s_out:
        ret
    """, va)


def build_vtu(va):
    src = f"""
        cmp  dword ptr [eax + 0x10], {SPELL_ID}
        je   v_ours
        push ebx
        push esi
        mov  esi, ecx
        mov  ecx, esi
        jmp  0x557e6ed6
    v_ours:
        push ebx
        push esi
        push edi
        mov  esi, ecx
        mov  edi, edx
        call {UNITSPELL_VTU:#x}
        test al, al
        je   v_no
        mov  eax, esi
        mov  edx, {ENCH:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  v_no
        {{ANC}}
        movsx edx, byte ptr [edi + 0x24]
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x140]
        call {GETPLAYERS:#x}
        test eax, eax
        je   v_yes
        cmp  byte ptr [eax + 0xa7], 0
        je   v_yes
        push ebp
        mov  ebp, 1
    v_loop:
        cmp  ebp, {MAX_ABIL:#x}
        jae  v_none
        cmp  ebp, {FLASK:#x}
        je   v_next
        mov  eax, esi
        mov  edx, ebp
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        je   v_next
        mov  eax, dword ptr [ebx + {{SET}}]
        mov  eax, dword ptr [eax + 0x80]
        mov  edx, ebp
        call {GETABILITY:#x}
        test eax, eax
        je   v_next
        mov  edx, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x84]
        sub  al, 3
        cmp  al, 2
        jbe  v_shooter
    v_next:
        inc  ebp
        jmp  v_loop
    v_shooter:
        pop  ebp
        jmp  v_no
    v_none:
        pop  ebp
    v_yes:
        mov  al, 1
        jmp  v_out
    v_no:
        xor  eax, eax
    v_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP, "SET": AOWHSSET})


def build_expand(va):
    """E's Expand: the original, then F on the owner."""
    return asm(f"""
        push ebx
        mov  ebx, edx
        call {TUEA_EXPAND:#x}
        push eax
        mov  eax, ebx
        mov  edx, {FLASK:#x}
        mov  cl, 1
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0x50]
        pop  eax
        pop  ebx
        ret
    """, va)


def build_remove(va):
    """E's Remove: the original, then F off the owner."""
    return asm(f"""
        push ebx
        mov  ebx, edx
        call {TUEA_REMOVE:#x}
        push eax
        mov  eax, ebx
        mov  edx, {FLASK:#x}
        xor  ecx, ecx
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0x50]
        pop  eax
        pop  ebx
        ret
    """, va)


def build_fcexec(va):
    """F's fcExecuteCombatCommand (eax = F, edx = the shooter, ecx = the command).
    Frame: [ebp-4] F, [ebp-8] shooter, [ebp-0xC] command, [ebp-0x10] target, [ebp-0x14] side,
    [ebp-0x18] eligible count n, [ebp-0x1C] i, [ebp-0x20] j, [ebp-0x24] combat data,
    [ebp-0x28]/[ebp-0x2C] the two picks k1/k2 (k2 = -1 when n < 2), [ebp-0x30]/[ebp-0x34] o1/o2.
    Both picks are taken in one pass before either strike, so a death cannot shift the list."""
    src = f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x34
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp - 4], eax
        mov  dword ptr [ebp - 8], edx
        mov  dword ptr [ebp - 0xc], ecx
        call {RA_FCEXEC:#x}
        {{ANC}}
        mov  ecx, dword ptr [ebp - 0xc]
        mov  eax, dword ptr [ecx + 0x18]
        mov  dword ptr [ebp - 0x10], eax
        test eax, eax
        je   f_consume
        call {GETSIDE:#x}
        movzx eax, al
        mov  dword ptr [ebp - 0x14], eax
        mov  eax, dword ptr [ebp - 8]
        mov  eax, dword ptr [eax + 8]
        mov  eax, dword ptr [eax + 0xc]
        mov  dword ptr [ebp - 0x24], eax
        xor  eax, eax
        mov  dword ptr [ebp - 0x18], eax
        mov  dword ptr [ebp - 0x1c], eax
        mov  dword ptr [ebp - 0x30], eax
        mov  dword ptr [ebp - 0x34], eax
    f_count:
        mov  eax, dword ptr [ebp - 0x24]
        call {CD_COUNT:#x}
        cmp  dword ptr [ebp - 0x1c], eax
        jge  f_counted
        mov  edx, dword ptr [ebp - 0x1c]
        mov  eax, dword ptr [ebp - 0x24]
        call {CD_GET:#x}
        call f_eligible
        test al, al
        je   f_cnext
        inc  dword ptr [ebp - 0x18]
    f_cnext:
        inc  dword ptr [ebp - 0x1c]
        jmp  f_count
    f_counted:
        mov  eax, dword ptr [ebp - 0x18]
        test eax, eax
        je   f_consume
        call {RANDINT:#x}
        mov  dword ptr [ebp - 0x28], eax
        mov  dword ptr [ebp - 0x2c], -1
        mov  eax, dword ptr [ebp - 0x18]
        cmp  eax, 2
        jl   f_pass
        dec  eax
        call {RANDINT:#x}
        cmp  eax, dword ptr [ebp - 0x28]
        jl   f_k2
        inc  eax
    f_k2:
        mov  dword ptr [ebp - 0x2c], eax
    f_pass:
        mov  dword ptr [ebp - 0x1c], 0
        mov  dword ptr [ebp - 0x20], 0
    f_find:
        mov  eax, dword ptr [ebp - 0x24]
        call {CD_COUNT:#x}
        cmp  dword ptr [ebp - 0x1c], eax
        jge  f_strikes
        mov  edx, dword ptr [ebp - 0x1c]
        mov  eax, dword ptr [ebp - 0x24]
        call {CD_GET:#x}
        mov  esi, eax
        call f_eligible
        test al, al
        je   f_fnext
        mov  eax, dword ptr [ebp - 0x20]
        cmp  eax, dword ptr [ebp - 0x28]
        jne  f_not1
        mov  dword ptr [ebp - 0x30], esi
    f_not1:
        cmp  eax, dword ptr [ebp - 0x2c]
        jne  f_not2
        mov  dword ptr [ebp - 0x34], esi
    f_not2:
        inc  dword ptr [ebp - 0x20]
    f_fnext:
        inc  dword ptr [ebp - 0x1c]
        jmp  f_find
    f_strikes:
        mov  esi, dword ptr [ebp - 0x30]
        call f_strike
        mov  esi, dword ptr [ebp - 0x34]
        call f_strike
    f_consume:
        mov  eax, dword ptr [ebp - 8]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xb8]
        test eax, eax
        je   f_out
        mov  esi, eax
        mov  eax, dword ptr [ebx + {{SET}}]
        mov  eax, dword ptr [eax + 0x80]
        mov  edx, {ENCH:#x}
        call {GETABILITY:#x}
        test eax, eax
        je   f_out
        mov  edx, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {SLOT_REMOVE:#x}]
    f_out:
        mov  al, 1
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret

    f_strike:
        test esi, esi
        je   k_ret
        push 0
        mov  ecx, esi
        mov  edx, dword ptr [ebp - 8]
        mov  eax, dword ptr [ebp - 4]
        call {CREATE_RA_CA:#x}
        mov  edi, eax
        mov  edx, eax
        mov  eax, dword ptr [ebp - 8]
        mov  eax, dword ptr [eax + 8]
        call {EXEC_CA:#x}
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
    k_ret:
        ret

    f_eligible:
        cmp  eax, dword ptr [ebp - 0x10]
        je   e_no
        test eax, eax
        je   e_no
        push eax
        mov  edx, dword ptr [ebx + {{TCU}}]
        call {ISCLASS:#x}
        test al, al
        pop  eax
        je   e_no
        push eax
        call {GETSIDE:#x}
        movzx edx, al
        pop  eax
        cmp  edx, dword ptr [ebp - 0x14]
        jne  e_no
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        ret
    e_no:
        xor  eax, eax
        ret
    """
    return pic(src, va, "ebx", {"SET": AOWHSSET, "TCU": TCU_CELL})


def vmt_copy(slots):
    """Asm: EAX = the new ability object -> its VMT replaced by a GetMem copy, `slots` = {offset:
    field name} patched to anchor-relative addresses (ECX = anchor), parent = the original."""
    pat = "\n".join(f"""
        lea  esi, [ecx + {{{name}}}]
        mov  dword ptr [edx + {off:#x}], esi""" for off, name in slots.items())
    return f"""
        push eax
        push ecx
        mov  eax, {VMT_NEG + VMT_LEN:#x}
        call {GETMEM:#x}
        mov  edi, eax
        mov  esi, dword ptr [esp + 4]
        mov  esi, dword ptr [esi]
        push esi
        sub  esi, {VMT_NEG:#x}
        mov  ecx, {(VMT_NEG + VMT_LEN) // 4:#x}
        rep movsd dword ptr es:[edi], dword ptr [esi]
        lea  edx, [eax + {VMT_NEG:#x}]
        mov  dword ptr [eax], edx
        pop  esi
        sub  esi, {VMT_NEG:#x}
        mov  dword ptr [edx - 0x18], esi
        pop  ecx
        {pat}
        pop  eax
        mov  dword ptr [eax], edx
"""


def build_reg_ench(va, at):
    src = f"""
        call {REGISTER_ABIL:#x}
        push esi
        push edi
        {{ANC}}
        push ecx
        lea  eax, [ecx + {{VMT}}]
        xor  ecx, ecx
        mov  dl, 1
        call {TUEA_CREATE:#x}
        pop  ecx
        push ecx
        push eax
        lea  edx, [ecx + {{NAME}}]
        add  eax, 8
        call {LSTRASG:#x}
        pop  eax
        pop  ecx
        mov  dword ptr [eax + 0xc], {ENCH:#x}
        {vmt_copy({SLOT_EXPAND: "EXP", SLOT_REMOVE: "REM"})}
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER_ABIL:#x}
        pop  edi
        pop  esi
        ret
    """
    return pic(src, va, "ecx", {"VMT": TUEA_VMT, "NAME": ("TAIL", 8),
                                "EXP": at["expand"], "REM": at["remove"]}, ansistr(ENCH_NAME))


def build_reg_flask(va, at):
    src = f"""
        call {REGISTER_ABIL:#x}
        push esi
        push edi
        {{ANC}}
        push ecx
        push {DAM}
        push {SHOTS}
        push {BAND}
        push {TYPES:#x}
        push {FC_ICON:#x}
        lea  edx, [ecx + {{NAME}}]
        mov  cl, {ATK:#x}
        mov  eax, {FLASK:#x}
        call {CREATE_RANGED:#x}
        pop  ecx
        {vmt_copy({SLOT_FCEXEC: "FCX"})}
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER_ABIL:#x}
        pop  edi
        pop  esi
        ret
    """
    return pic(src, va, "ecx", {"NAME": ("TAIL", 8), "FCX": at["fcexec"]}, ansistr(FLASK_NAME))


def build_reg_spell(va):
    src = f"""
        call {REGISTER_SPELL:#x}
        {{ANC}}
        push ecx
        mov  eax, dword ptr [ecx + {{CELL}}]
        xor  ecx, ecx
        mov  dl, 1
        call {EW_CREATE:#x}
        pop  ecx
        push eax
        lea  edx, [ecx + {{NAME}}]
        add  eax, 8
        call {LSTRASG:#x}
        pop  eax
        mov  dword ptr [eax + 0x10], {SPELL_ID}
        mov  dword ptr [eax + 0x14], {MANA}
        mov  dword ptr [eax + 0x18], {RESEARCH}
        mov  dword ptr [eax + 0x1c], {UPKEEP}
        mov  byte ptr [eax + 0x20], {SPHERE}
        mov  byte ptr [eax + 0x21], {TIER}
        mov  byte ptr [eax + 0x3c], {LEVEL}
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER_SPELL:#x}
        ret
    """
    return pic(src, va, "ecx", {"CELL": EW_CELL, "NAME": ("TAIL", 8)}, ansistr(SPELL_NAME))


def layout():
    caves, at, va = [], {}, SLOT[0]

    def put(n, b):
        nonlocal va
        caves.append(("cave_" + n, va, b))
        at[n] = va
        va = (va + len(b) + 0xF) & ~0xF

    put("sel", build_sel(va))
    put("vtu", build_vtu(va))
    put("expand", build_expand(va))
    put("remove", build_remove(va))
    put("fcexec", build_fcexec(va))
    put("reg_spell", build_reg_spell(va))
    put("reg_ench", build_reg_ench(va, at))
    put("reg_flask", build_reg_flask(va, at))
    return at, caves


def checks():
    d = open(P.TARGET, "rb").read()
    rd = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    for vmt, name in ((TUEA_VMT, "TUnitEnchantmentAbility"), (0x5571E8D4, "TRangedAttackAbility")):
        if rd(vmt - 0x40) != vmt or rd(vmt - 0x20) - vmt != VMT_LEN:
            sys.exit("ABORT: %s's VMT is not %#x bytes" % (name, VMT_LEN))
    if rd(TUEA_VMT + SLOT_EXPAND) != TUEA_EXPAND or rd(TUEA_VMT + SLOT_REMOVE) != TUEA_REMOVE:
        sys.exit("ABORT: TUnitEnchantmentAbility's Expand/Remove slots moved")
    if rd(0x5571E8D4 + SLOT_FCEXEC) != RA_FCEXEC:
        sys.exit("ABORT: TRangedAttackAbility's fcExecuteCombatCommand slot moved")
    v = rd(EW_CELL)
    if rd(v - 0x40) != v:
        sys.exit("ABORT: %08X does not hold a class" % EW_CELL)
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:            # nobody else registers 84, 0x4E or 0x4F
        for i in range(ra, ra + rs - 7):
            src = P.IMAGE_BASE + sva + (i - ra)
            if SLOT[0] <= src < SLOT[1]:
                continue
            if d[i:i + 3] == b"\xc7\x40\x10" and struct.unpack_from("<I", d, i + 3)[0] == SPELL_ID:
                sys.exit("ABORT: %08X also stores spell id %d" % (src, SPELL_ID))
            if d[i:i + 3] == b"\xc7\x40\x0c" and struct.unpack_from("<I", d, i + 3)[0] in (ENCH, FLASK):
                sys.exit("ABORT: %08X also stores ability id %#x" % (src, struct.unpack_from("<I", d, i + 3)[0]))
    dual = d[P.va2off(d, 0x558B6000):P.va2off(d, 0x558B6000) + 0x100]
    if not any(struct.unpack_from("<HBB", dual, k) == (SPELL_ID, 3, 5) for k in range(0, 0xFC, 4)):
        print("  NOTE: build_dual_sphere.py's TABLE does not list spell %d as Earth/Fire yet" % SPELL_ID)


AT, CAVES = layout()
call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
HOOKS = []
for name, (va, van, _lo, _hi) in SITES.items():
    tgt = {"reg_spell": "reg_spell", "reg_ench": "reg_ench", "reg_flask": "reg_flask",
           "sel1": "sel", "sel2": "sel", "vtu": "vtu"}[name]
    if name == "vtu":
        HOOKS.append((va, van, jmp_to(va, AT[tgt], len(van))))
    else:
        HOOKS.append((va, van, call_to(va, AT[tgt])))
INTERIOR = [(va, va + len(van), lo, hi) for _n, (va, van, lo, hi) in SITES.items()]
assert max(va + len(b) for _n, va, b in CAVES) <= SLOT[1]

if __name__ == "__main__":
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in AT.items()))
    print("  slot used: %d of %d B; TCombat.ExecuteCombatAction %08X" % (
        max(va + len(b) for _n, va, b in CAVES) - SLOT[0], SLOT[1] - SLOT[0], EXEC_CA))
    checks()
    run("build_satchels", HOOKS, CAVES, SLOT, INTERIOR)
