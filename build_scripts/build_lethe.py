#!/usr/bin/env python
r"""
build_lethe.py -- the AoWEPACK half of Curse of Lethe (id 86), the Death/Water dual tier-1 battle
spell, and its status Asleep (0x50).  AoWTCPCK half: build_lethe_tc.py.  Data: build_lethe_pfs.py.
Owner's design 2026-10-25 (05-spells-added.md, "Death/Water -- agreed design").

CURSE OF LETHE  a TEntangle INSTANCE (Entangle's single-target status CA with a Resistance roll),
  registered at 0x557FA811 (RegisterCombatSpells' last free direct `call RegisterSpell`, replayed
  first).  Range 8, 1 shot, 12 mana, research 80 (the single tier-2 figure), sphere 7 (dual), tier 1,
  power 10 at +0x34, damage 0, type mask 0x08 (Magic: auto-combat drops an extra target only when
  it is immune to every type in the mask), 2 extra auto-combat targets, side 2.  Its RUN-TIME VMT
  copy (VMT-0x40..+0x9C) replaces:
    +0x78 CreateCA   TEntangle.CreateCA's shape (a TEntangleSpellCA; caster, target, spell id, mana
          on the hero CA) with this spell's filter and roll: a unit that can sleep (below) rolls
          HitRole(10 - (RES + 4 for Elves and Dark Elves)), the result in [CA+0x14].
    +0x80 / +0x84 / +0x98  the damage values (manual AI, auto-combat): 0 for a unit that cannot
          sleep, else the originals.
    +0x90 fcPrefetchCombatCommands  auto-combat queues it only when at least 2 enemy units can sleep.
  Can sleep: a combat unit (IsClass TCombatUnit, so never a wall), not Magic Immune (0x06,
  item-aware), not Undead (race 11, or Animated 0x81, Turn Undead's test), not a war machine
  (GetUnitType 2), not asleep already.
ASLEEP (0x50)  a TStunnedAbility instance (as Petrified is) registered at 0x557BCC28
  (RegisterPassiveAbilities' last free direct `call RegisterAbility`), name "Asleep", with a run-time
  VMT copy (VMT-0x40..+0x110) whose +0x110 GetTotalDuration returns 5 and whose parent is
  TStunnedAbility.  Duration mode 2 (combat turns, Stunned's) and Stunned's -4 Defence.
  E   0x557F8A04  TEntangleSpellCA.Execute after the inherited Execute (6 B) -> cave_exec: for spell
      86 with [CA+0x14] set, the target's ability owner (+0xB8) expands Asleep (+0x94) and its data's
      tick player [+0xD] becomes the target's own player [obj+0x45]: the count (5) drops at the start
      of each of that side's turns and the status goes at 0, so every sleeper misses 4 turns of its
      own, on either side.  Other spells replay the displaced test.
  L   0x55724BF7  TCombatUnit.GetLocked's `mov edx,0x22` (5 B) -> cave_locked: Asleep -> locked (no
      action, no retaliation; auto-resolve skips it), else the vanilla chain goes on.
  S   0x557817F3  TAbstractUnit.ShowEx's Stunned block `mov edx,0x5c` (5 B) -> cave_show: Stunned or
      Asleep draws Stunned's dazed frames there.
  W   0x55726CB3  TCombatObject.ExecuteDamage after the HP are set (6 B: `test ebp,ebp / je / mov
      eax,esi`, EBP = the damage dealt) -> cave_wake: damage above 0 removes Asleep (owner +0xB8 ->
      +0x4C self-only test -> +0x98 RemoveAbility), then the displaced bytes.  One body serves both
      combat systems.  build_panic_cleardamage.py hooks the same function's entry; independent.
  R   0x557E740F  TRemedy.ExecuteSpell's removal of Stunned (`call [ecx+0x98]`, 6 B; EBX = the unit)
      -> call cave_remedy + nop: Stunned, then Asleep.  build_stonegaze.py's Petrified hook is the
      last removal (0x557E741E); independent.
  D   0x5576CAE7  TDispelMagicCA.Execute after its ability test (6 B: `mov eax,[esi+0x10] / mov
      ebp,[eax+8]`; EDI = the target) -> cave_dispel: Asleep removed, unconditionally (owner
      2026-10-25: as for Petrified), then the displaced bytes.  The Dispel Magic ability's CA and
      the spell's both run it.  build_stonegaze.py's hook (0x5576CAD5, 8 B) ends at 0x5576CADC.

RNG: the roll is HitRole's raw RandInt.  Manual combat: build_lethe_tc.py reseeds
System.RandSeed from the synced TAoWHSMap.Random before each target's CreateCA.  Auto-combat: P2
COMBAT RAW, as Entangle.
Slot 0x558BD000-0x558BD7FF, exclusive.  PIC.  Surgical --undo.  R and R2 run at package init:
proved only by launching the exe.

    python build_scripts/build_lethe.py            dry run + state
    python build_scripts/build_lethe.py --apply
    python build_scripts/build_lethe.py --undo
    python build_scripts/build_lethe.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic, ansistr

SPELL_ID, SPELL_NAME = 86, "Curse of Lethe"
ASLEEP, ASLEEP_NAME = 0x50, "Asleep"
MANA, RESEARCH, SPHERE, TIER = 12, 80, 7, 1
POWER, TYPES, RANGE, EXTRAS = 10, 0x08, 8, 2
ELF_BONUS, RACE_ELF, RACE_DARKELF, RACE_UNDEAD = 4, 4, 8, 0x0B
ANIMATED, MAGIC_IMMUNITY, UT_MACHINE = 0x81, 0x06, 2
DURATION = 5                                    # ticks: 4 whole turns of the sleeper's own side
SLOT = (0x558BD000, 0x558BD800)

REGISTER_ABILITY, REGISTER_SPELL = 0x55750238, 0x55779B40
GETMEM, LSTRASG, ISCLASS, HITROLE = 0x55701008, 0x55701150, 0x557010C0, 0x55725D98
STUN_CREATE, VMT_STUN = 0x557BA4A0, 0x557B600C
ENT_CELL, ENT_CREATE = 0x557F4FB0, 0x557F8A68
ENTCA_CELL, CA_CREATE = 0x557F4EC8, 0x557298B4
TCU_CELL = 0x55715A54                           # TCombatUnit VMT - 0x40 (its self pointer)
FINDID, GETABDATA = 0x55728C68, 0x5574F1C4
GETOBJECTS, GETSIDE = 0x55726DBC, 0x55726660
ORIG_VAL, ORIG_VALEX, ORIG_FCPRE, ORIG_FCVAL = 0x557F7268, 0x557F8BAC, 0x557F76BC, 0x557F7464
VMT_NEG, SPELL_SLOTS, STUN_SLOTS = 0x40, 0x9C, 0x114

R_SITE, R2_SITE = 0x557BCC28, 0x557FA811
SITES = {   # name: (va, vanilla bytes, function lo, hi)
    "exec":   (0x557F8A04, "807b14007457", 0x557F89F4, 0x557F8A65),
    "locked": (0x55724BF7, "ba22000000", 0x55724BA4, 0x55724C14),
    "show":   (0x557817F3, "ba5c000000", None, None),
    "wake":   (0x55726CB3, "85ed74188bc6", 0x55726C58, 0x55726CD6),
}
EXEC_OUT, EXEC_GO = 0x557F8A61, 0x557F8A0A
LOCKED_YES, LOCKED_GO = 0x55724C0F, 0x55724BFC
SHOW_YES, SHOW_NO = 0x55781806, 0x5578183F
REMEDY_SITE = 0x557E740F                        # `call [ecx+0x98]`, Stunned's removal (6 B)
DISPEL_SITE, DISPEL_GO = 0x5576CAE7, 0x5576CAED  # `mov eax,[esi+0x10] / mov ebp,[eax+8]`
NOP = bytes([0x90])
WAKE_END, WAKE_GO = 0x55726CCF, 0x55726CB9
A = {}


def rel(src, dst, op):
    return bytes([op]) + struct.pack("<i", dst - (src + 5))


def c_affect(va):
    """eax = combat object -> eax 1 when it can be put to sleep."""
    src = f"""
        push ebx
        push esi
        mov  ebx, eax
        test ebx, ebx
        je   a_no
        {{ANC}}
        mov  eax, ebx
        mov  edx, dword ptr [esi + {{TCU}}]
        call {ISCLASS:#x}
        test al, al
        je   a_no
        mov  eax, ebx
        mov  edx, {MAGIC_IMMUNITY}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  a_no
        mov  eax, ebx
        mov  edx, {ASLEEP:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  a_no
        mov  esi, dword ptr [ebx + 0x4c]
        test esi, esi
        je   a_no
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xa4]
        cmp  al, {RACE_UNDEAD}
        je   a_no
        mov  eax, esi
        mov  edx, {ANIMATED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  a_no
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x114]
        cmp  al, {UT_MACHINE}
        je   a_no
        mov  eax, 1
        pop  esi
        pop  ebx
        ret
    a_no:
        xor  eax, eax
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "esi", {"TCU": TCU_CELL})


def c_createca(va):
    """+0x78 CreateCA(eax spell, edx caster, ecx target, [esp+4] hero) -> eax CA; ret 4."""
    src = f"""
        push ebp
        mov  ebp, esp
        push ecx
        push ebx
        push esi
        push edi
        mov  esi, ecx
        mov  dword ptr [ebp - 4], edx
        mov  edi, eax
        {{ANC}}
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, dword ptr [ebx + {{ENTCA}}]
        call {CA_CREATE:#x}
        mov  ebx, eax
        mov  eax, dword ptr [ebp - 4]
        mov  al, byte ptr [eax + 0xc]
        mov  byte ptr [ebx + 0xc], al
        mov  al, byte ptr [esi + 0xc]
        mov  byte ptr [ebx + 0xd], al
        mov  eax, dword ptr [edi + 0x10]
        mov  dword ptr [ebx + 0x18], eax
        cmp  byte ptr [ebp + 8], 0
        je   c_roll
        mov  eax, dword ptr [edi + 0x14]
        mov  dword ptr [ebx + 0x10], eax
    c_roll:
        mov  eax, esi
        call {A['affect']:#x}
        test eax, eax
        je   c_out
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        push eax
        mov  eax, dword ptr [esi + 0x4c]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xa4]
        pop  edx
        cmp  al, {RACE_ELF}
        je   c_elf
        cmp  al, {RACE_DARKELF}
        jne  c_res
    c_elf:
        add  edx, {ELF_BONUS}
    c_res:
        movsx eax, byte ptr [edi + 0x34]
        sub  eax, edx
        call {HITROLE:#x}
        mov  byte ptr [ebx + 0x14], al
    c_out:
        mov  eax, ebx
        pop  edi
        pop  esi
        pop  ebx
        pop  ecx
        pop  ebp
        ret  4
    """
    return pic(src, va, "ebx", {"ENTCA": ENTCA_CELL})


def c_val(va):
    return asm(f"""
        push eax
        push edx
        push ecx
        mov  eax, ecx
        call {A['affect']:#x}
        test eax, eax
        pop  ecx
        pop  edx
        pop  eax
        je   v_zero
        jmp  {ORIG_VAL:#x}
    v_zero:
        xor  eax, eax
        ret
    """, va)


def c_zeroed(va, orig, out_at, popn):
    return asm(f"""
        push eax
        push edx
        push ecx
        mov  eax, ecx
        call {A['affect']:#x}
        test eax, eax
        pop  ecx
        pop  edx
        pop  eax
        je   z_zero
        jmp  {orig:#x}
    z_zero:
        push edi
        mov  edi, dword ptr [esp + {out_at + 4:#x}]
        xor  eax, eax
        mov  dword ptr [edi], eax
        mov  dword ptr [edi + 4], eax
        mov  dword ptr [edi + 8], eax
        mov  dword ptr [edi + 0xc], eax
        mov  dword ptr [edi + 0x10], eax
        pop  edi
        ret  {popn:#x}
    """, va)


def c_fcpre(va):
    """+0x90 (eax spell, edx context: +4 caster, +8 TFastCombat, +0xC enemy side)."""
    return asm(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  edi, edx
        mov  esi, dword ptr [edi + 0xc]
        test esi, esi
        je   p_no
        push ebp
        xor  ebp, ebp
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  ecx, eax
    p_loop:
        dec  ecx
        js   p_done
        push ecx
        mov  eax, esi
        mov  edx, ecx
        call {GETOBJECTS:#x}
        test eax, eax
        je   p_next
        test byte ptr [eax + 0x47], 1
        jne  p_next
        push eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        pop  eax
        je   p_next
        call {A['affect']:#x}
        add  ebp, eax
    p_next:
        pop  ecx
        jmp  p_loop
    p_done:
        cmp  ebp, 2
        pop  ebp
        jl   p_no
        mov  eax, ebx
        mov  edx, edi
        pop  edi
        pop  esi
        pop  ebx
        jmp  {ORIG_FCPRE:#x}
    p_no:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


def c_exec(va):
    """TEntangleSpellCA.Execute after the inherited Execute: ebx = CA, esi = TCombat."""
    return asm(f"""
        cmp  dword ptr [ebx + 0x18], {SPELL_ID}
        je   x_ours
        cmp  byte ptr [ebx + 0x14], 0
        je   {EXEC_OUT:#x}
        jmp  {EXEC_GO:#x}
    x_ours:
        cmp  byte ptr [ebx + 0x14], 0
        je   {EXEC_OUT:#x}
        xor  edx, edx
        mov  dl, byte ptr [ebx + 0xd]
        mov  eax, dword ptr [esi + 0xc]
        call {FINDID:#x}
        test eax, eax
        je   {EXEC_OUT:#x}
        mov  edi, eax
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xb8]
        test eax, eax
        je   {EXEC_OUT:#x}
        push eax
        mov  edx, {ASLEEP:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x94]
        pop  eax
        mov  edx, {ASLEEP:#x}
        call {GETABDATA:#x}
        test eax, eax
        je   {EXEC_OUT:#x}
        mov  dl, byte ptr [edi + 0x45]
        mov  byte ptr [eax + 0xd], dl
        jmp  {EXEC_OUT:#x}
    """, va)


def c_locked(va):
    return asm(f"""
        mov  edx, {ASLEEP:#x}
        mov  eax, dword ptr [ebx + 0x4c]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  {LOCKED_YES:#x}
        mov  edx, 0x22
        jmp  {LOCKED_GO:#x}
    """, va)


def c_show(va):
    return asm(f"""
        mov  edx, 0x5c
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  {SHOW_YES:#x}
        mov  edx, {ASLEEP:#x}
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  {SHOW_YES:#x}
        jmp  {SHOW_NO:#x}
    """, va)


def c_wake(va):
    """EBP = the damage dealt, ESI = the struck object."""
    return asm(f"""
        test ebp, ebp
        jle  w_done
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xb8]
        test eax, eax
        je   w_done
        push eax
        mov  edx, {ASLEEP:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        pop  eax
        je   w_done
        mov  edx, {ASLEEP:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x98]
    w_done:
        test ebp, ebp
        je   {WAKE_END:#x}
        mov  eax, esi
        jmp  {WAKE_GO:#x}
    """, va)


def c_remedy(va):
    """Replaces Remedy's `call [ecx+0x98]` for Stunned: eax = ebx = the unit, edx = 0x5C."""
    return asm(f"""
        call dword ptr [ecx + 0x98]
        mov  edx, {ASLEEP:#x}
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x98]
        ret
    """, va)


def c_dispel(va):
    """TDispelMagicCA.Execute: edi = the target combat unit."""
    return asm(f"""
        mov  eax, dword ptr [edi + 0x4c]
        test eax, eax
        je   q_go
        mov  edx, {ASLEEP:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x98]
    q_go:
        mov  eax, dword ptr [esi + 0x10]
        mov  ebp, dword ptr [eax + 8]
        jmp  {DISPEL_GO:#x}
    """, va)


def c_dur(va):
    return asm(f"""
        mov  eax, {DURATION}
        ret
    """, va)


def c_reg_ab(va):
    """`call RegisterAbility` replayed (EBX = the control), then Asleep."""
    src = f"""
        call {REGISTER_ABILITY:#x}
        push esi
        push edi
        {{ANC}}
        lea  eax, [esi + {{STUNVMT}}]
        xor  ecx, ecx
        mov  dl, 1
        call {STUN_CREATE:#x}
        mov  dword ptr [eax + 0xc], {ASLEEP:#x}
        push eax
        lea  eax, [eax + 8]
        lea  edx, [esi + {{NAME}}]
        call {LSTRASG:#x}
        mov  eax, {VMT_NEG + STUN_SLOTS:#x}
        call {GETMEM:#x}
        push esi
        mov  edi, eax
        mov  esi, dword ptr [esp + 4]
        mov  esi, dword ptr [esi]
        sub  esi, {VMT_NEG:#x}
        mov  ecx, {(VMT_NEG + STUN_SLOTS) // 4:#x}
        cld
        rep movsd dword ptr es:[edi], dword ptr [esi]
        pop  esi
        lea  edx, [eax + {VMT_NEG:#x}]
        mov  dword ptr [eax], edx
        lea  ecx, [esi + {{DUR}}]
        mov  dword ptr [edx + 0x110], ecx
        lea  ecx, [esi + {{STUNSELF}}]
        mov  dword ptr [edx - 0x18], ecx
        pop  eax
        mov  dword ptr [eax], edx
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER_ABILITY:#x}
        pop  edi
        pop  esi
        ret
    """
    return pic(src, va, "esi", {"STUNVMT": VMT_STUN, "STUNSELF": VMT_STUN - VMT_NEG,
                                "DUR": A["dur"], "NAME": ("TAIL", 8)}, ansistr(ASLEEP_NAME))


def c_reg_spell(va):
    """`call RegisterSpell` replayed (EBX = the control), then Curse of Lethe."""
    src = f"""
        call {REGISTER_SPELL:#x}
        push esi
        push edi
        {{ANC}}
        mov  eax, dword ptr [esi + {{ENTCELL}}]
        xor  ecx, ecx
        mov  dl, 1
        call {ENT_CREATE:#x}
        mov  edi, eax
        lea  eax, [edi + 8]
        lea  edx, [esi + {{NAME}}]
        call {LSTRASG:#x}
        mov  dword ptr [edi + 0x10], {SPELL_ID}
        mov  dword ptr [edi + 0x14], {MANA}
        mov  dword ptr [edi + 0x18], {RESEARCH}
        mov  dword ptr [edi + 0x1c], 0
        mov  byte ptr [edi + 0x20], {SPHERE}
        mov  byte ptr [edi + 0x21], {TIER}
        mov  byte ptr [edi + 0x23], 1
        mov  byte ptr [edi + 0x34], {POWER}
        mov  byte ptr [edi + 0x35], 0
        mov  word ptr [edi + 0x36], {TYPES:#x}
        mov  byte ptr [edi + 0x38], 1
        mov  byte ptr [edi + 0x39], {RANGE}
        mov  byte ptr [edi + 0x3a], {EXTRAS}
        mov  byte ptr [edi + 0x3b], 2
        mov  byte ptr [edi + 0x3c], 1
        mov  eax, {VMT_NEG + SPELL_SLOTS:#x}
        call {GETMEM:#x}
        mov  edx, eax
        push esi
        push edi
        mov  esi, dword ptr [edi]
        sub  esi, {VMT_NEG:#x}
        mov  edi, edx
        mov  ecx, {(VMT_NEG + SPELL_SLOTS) // 4:#x}
        cld
        rep movsd dword ptr es:[edi], dword ptr [esi]
        pop  edi
        pop  esi
        add  edx, {VMT_NEG:#x}
        lea  eax, [esi + {{CREATECA}}]
        mov  dword ptr [edx + 0x78], eax
        lea  eax, [esi + {{VAL}}]
        mov  dword ptr [edx + 0x80], eax
        lea  eax, [esi + {{VALEX}}]
        mov  dword ptr [edx + 0x84], eax
        lea  eax, [esi + {{FCPRE}}]
        mov  dword ptr [edx + 0x90], eax
        lea  eax, [esi + {{FCVAL}}]
        mov  dword ptr [edx + 0x98], eax
        mov  dword ptr [edi], edx
        mov  edx, edi
        mov  eax, ebx
        call {REGISTER_SPELL:#x}
        pop  edi
        pop  esi
        ret
    """
    return pic(src, va, "esi", {"ENTCELL": ENT_CELL, "CREATECA": A["createca"], "VAL": A["val"],
                                "VALEX": A["valex"], "FCPRE": A["fcpre"], "FCVAL": A["fcval"],
                                "NAME": ("TAIL", 8)}, ansistr(SPELL_NAME))


BUILDERS = [
    ("affect", c_affect), ("createca", c_createca), ("val", c_val),
    ("valex", lambda va: c_zeroed(va, ORIG_VALEX, 4, 4)),
    ("fcval", lambda va: c_zeroed(va, ORIG_FCVAL, 4, 8)),
    ("fcpre", c_fcpre), ("exec", c_exec), ("locked", c_locked), ("show", c_show),
    ("wake", c_wake), ("dur", c_dur), ("reg_ab", c_reg_ab), ("reg_spell", c_reg_spell),
    ("remedy", c_remedy), ("dispel", c_dispel),
]


def layout():
    for _ in range(2):
        va, blobs = SLOT[0], []
        for name, b in BUILDERS:
            A.setdefault(name, va)
            A[name] = va
            blob = b(va)
            blobs.append(("cave_" + name, va, blob))
            va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    return blobs


def interior_jumps(d, ranges):
    """Every branch in AoWEPACK's CODE that lands strictly inside a displaced range."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.skipdata = True
    _e, secs = P.sections(d)
    vs, sva, rs, ra = secs[0]
    lo = P.IMAGE_BASE + sva
    bad = []
    for ins in md.disasm(bytes(d[ra:ra + rs]), lo):
        if ins.mnemonic.startswith("j") or ins.mnemonic == "call":
            try:
                t = int(ins.op_str, 16)
            except ValueError:
                continue
            for a, b in ranges:
                if a < t < b and not (a <= ins.address < b):
                    bad.append((ins.address, t))
    return bad


def checks(d):
    u = lambda v: struct.unpack_from("<I", d, P.va2off(d, v))[0]
    for vmt, name in ((VMT_STUN, b"TStunnedAbility"), (u(ENT_CELL), b"TEntangle"),
                      (u(TCU_CELL), b"TCombatUnit")):
        cn = P.va2off(d, u(vmt - 0x20))
        if u(vmt - 0x40) != vmt or d[cn + 1:cn + 1 + d[cn]] != name:
            sys.exit("ABORT: %s VMT moved" % name.decode())
    if u(VMT_STUN - 0x20) - VMT_STUN != STUN_SLOTS:
        sys.exit("ABORT: TStunnedAbility's VMT changed size")
    if u(VMT_STUN + 0x110) != 0x557BA548 or u(u(ENT_CELL) + 0x78) != 0x557F8B20:
        sys.exit("ABORT: GetTotalDuration / TEntangle.CreateCA moved")
    for va, val in ((u(ENT_CELL) + 0x80, ORIG_VAL), (u(ENT_CELL) + 0x84, ORIG_VALEX),
                    (u(ENT_CELL) + 0x90, ORIG_FCPRE), (u(ENT_CELL) + 0x98, ORIG_FCVAL)):
        if u(va) != val:
            sys.exit("ABORT: TEntangle VMT slot %08X is not %08X" % (va, val))
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:            # nobody else creates spell 86 or ability 0x50
        for i in range(ra, ra + rs - 7):
            src = P.IMAGE_BASE + sva + (i - ra)
            if SLOT[0] <= src < SLOT[1]:
                continue
            if d[i:i + 3] == b"\xc7\x40\x10" and struct.unpack_from("<I", d, i + 3)[0] == SPELL_ID:
                sys.exit("ABORT: %08X also stores spell id %d" % (src, SPELL_ID))
            if d[i:i + 3] == b"\xc7\x40\x0c" and struct.unpack_from("<I", d, i + 3)[0] == ASLEEP:
                sys.exit("ABORT: %08X also stores ability id %#x" % (src, ASLEEP))


def main():
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d)
    hooks = [(R_SITE, rel(R_SITE, REGISTER_ABILITY, 0xE8), rel(R_SITE, A["reg_ab"], 0xE8)),
             (R2_SITE, rel(R2_SITE, REGISTER_SPELL, 0xE8), rel(R2_SITE, A["reg_spell"], 0xE8))]
    ranges = []
    for name, (va, orig, _lo, _hi) in SITES.items():
        orig = bytes.fromhex(orig)
        hooks.append((va, orig, rel(va, A[name], 0xE9) + b"\x90" * (len(orig) - 5)))
        ranges.append((va, va + len(orig)))
    hooks.append((REMEDY_SITE, bytes.fromhex("ff9198000000"), rel(REMEDY_SITE, A["remedy"], 0xE8) + NOP))
    hooks.append((DISPEL_SITE, bytes.fromhex("8b46108b6808"), rel(DISPEL_SITE, A["dispel"], 0xE9) + NOP))
    ranges += [(REMEDY_SITE, REMEDY_SITE + 6), (DISPEL_SITE, DISPEL_SITE + 6)]
    bad = interior_jumps(d, ranges)
    if bad:
        sys.exit("ABORT: jumps into a hook's interior: " + ", ".join("%08X->%08X" % x for x in bad))
    print("  interior sweep: no branch lands inside a displaced range")
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    run("build_lethe -- Curse of Lethe + Asleep (AoWEPACK)", hooks, blobs, SLOT, [])


if __name__ == "__main__":
    main()
