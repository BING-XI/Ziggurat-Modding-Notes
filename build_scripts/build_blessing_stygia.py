#!/usr/bin/env python
r"""
build_blessing_stygia.py -- Blessing of Stygia (id 87), the Death/Water dual tier-2 world-map global
enchantment, and its status Blessing of Stygia (0x51).  AoWEPACK.dpl.  Data:
build_blessing_stygia_pfs.py.  The purple-black water: build_stygia_tint.py, which asks this slot's
pinned STY_ANY entry whether to tint.  Owner's design 2026-10-25 (05-spells-added.md, "Death/Water --
agreed design").

THE SPELL  a TSpellWard INSTANCE (Astral Ward's class: a no-target global enchantment cast from the
  book), registered at 0x557F3AEE (Astral Ward's `call RegisterSpell` in
  RegisterGlobalEnchantmentSpells, replayed first).  Mana 30, research 160 (the single tier-3 figure),
  upkeep 5 (spell +0x1C, which TGlobalEnchantmentSpell.SetupEnchantment copies into the record),
  sphere 7 (dual), tier 2.  The AI never casts it (Astral Ward's AI weight [spell+0x34] = -1 kept).
  CREATE  TSpellWard VMT +0xA0 CreateEnchantment (0x557EF778, .reloc kept) -> cave_create: for spell
          87 a TSpellWardEnchantment re-typed by TGlobalEnchantment.Setup to STY_TYPE 0x57, name
          "Blessing of Stygia"; Astral Ward (any other id) gets its own record.  The record type is
          streamed, so saves keep it.  Types >= 8 are never refused or recorded by the active set.
  CANACT  ward VMT +0x64 CanActivate (0x557EF618, .reloc kept; the one test behind the book, the
          event's Validate and Cast) -> cave_canact: a 0x57 record is refused while the caster
          already has an active one -- vanilla's own refusal ("%s is already active"): the cave
          replays CanActivate's prologue, pushing its exception handler 0x5577DB91 position-
          independently, and jumps into the refusal branch 0x5577DB2A.  Everything else goes on to
          TGlobalEnchantment.CanActivate.
THE STATUS (0x51)  a TDurationAbility instance (as Nature's Blessing is: mode 1 = days, type byte 4),
  registered at 0x557BCC11 (a free `call RegisterAbility` in RegisterPassiveAbilities), name
  "Blessing of Stygia", with a run-time VMT copy (VMT-0x40..+0x110) whose +0x110 GetTotalDuration is
  TStunnedAbility's (returns 1), so the unit card reads "(1/1 days)".
  TURN  0x55780E28  TAbstractUnit.NewTurnDone's entry (7 B) -> cave_turn, then the displaced bytes.
        NewTurnDone is the unit's handler for message 0x20020003 (the world-map turn start, after
        the 0x20020002 pass that ticks day statuses).  For a unit whose owner P > 0 is the player
        starting the turn, when an active 0x57 record's caster C is P or P's ally (diplomatic
        relation 2), and the unit's hex or one of its six neighbours on its level is Water (0) or
        underground Water (0x0A): the status's data gets +0xC = 1 and tick player +0xD = P -- a
        unit that has it is refreshed; one with Physical Protection already (GetProtectionTypes bit
        0x80) gains nothing; any other expands it first.  So it lasts until P's next turn start,
        through other players' turns and their battles, and goes in that turn's tick unless renewed.
        Water on battle maps plays no part.
  PP    0x5574F990  TAbilityOwner.GetAbProtectionTypesAll's `call [ecx+0x88]` for Physical
        Protection 0x4D (6 B) -> call cave_pp + nop: 0x4D, else 0x51.  Every protection read goes
        through it: TAbstractUnit / THero GetProtectionTypes (VMT +0xF0), TCombatUnit's (+0x80, all
        three combat unit classes), the strategic and combat damage funnels and the effect and
        resistance rolls.
  The status is not an enchantment: Dispel Magic and Remedy do not remove it; it runs out.  Ending
  the spell (unpaid upkeep, Disjunction, the Magic window) stops new grants only.
STY_ANY  (pinned, this slot +0): AL = 1 when any active 0x57 record exists (build_stygia_tint.py).

RNG: none.  Every peer grants the same statuses from replicated state.
Coupling: build_blazing_moon.py chains CREATE and CANACT in front of cave_create / cave_canact (at
their current addresses).  Its entries in those slots read as this script's applied state; --apply
and --undo refuse while they are there: undo build_blazing_moon.py first.
Slot 0x558BD800-0x558BDFFF, exclusive.  PIC.  Surgical --undo.  The two registrations run at
package init: proved only by launching the exe.

    python build_scripts/build_blessing_stygia.py            dry run + state
    python build_scripts/build_blessing_stygia.py --apply
    python build_scripts/build_blessing_stygia.py --undo
    python build_scripts/build_blessing_stygia.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic, ansistr

SPELL_ID, SPELL_NAME = 87, "Blessing of Stygia"
STATUS, STATUS_NAME = 0x51, "Blessing of Stygia"
STY_TYPE = 0x57
MANA, RESEARCH, UPKEEP, SPHERE, TIER = 30, 160, 5, 7, 2
WATER, CAVE_WATER = 0x00, 0x0A
PHYS_PROT, PHYS_BIT = 0x4D, 0x80
SLOT = (0x558BD800, 0x558BE000)
STY_ANY = SLOT[0]

AOWHSMAP = 0x558FA040
REGISTER_ABILITY, REGISTER_SPELL = 0x55750238, 0x55779B40
GETMEM, LSTRASG = 0x55701008, 0x55701150
WARDSPELL_CELL, WARDSPELL_CREATE, WARD_CREATEENCH = 0x557EF698, 0x557F37F4, 0x557F3914
WARD_CELL, WARD_CREATE, GE_SETUP, GE_CANACT = 0x557EF574, 0x557F374C, 0x5577DA8C, 0x5577DAE8
CANACT_HANDLER, CANACT_REFUSE = 0x5577DB91, 0x5577DB2A
GETENCH, GETRELATION = 0x5577E13C, 0x55754150
DUR_CREATE, VMT_DUR, DUR_ONE = 0x55764CD4, 0x5571DD68, 0x557BA548
GETABDATA, GETLOCATION = 0x5574F1C4, 0x5577ED94
CENTERHN, GETMAPLEVEL, LEVEL_GETFIELD = 0x55702694, 0x557020EC, 0x557020DC
VMT_NEG, DUR_SLOTS = 0x40, 0x114

S_REGSPELL, S_REGAB = 0x557F3AEE, 0x557BCC11
S_CREATE, S_CANACT = 0x557EF778, 0x557EF618
SITES = {   # name: (va, vanilla bytes, resume) -- displaced-byte hooks
    "turn": (0x55780E28, "53568bf08a5e24", 0x55780E2F),
    "pp":   (0x5574F990, "ff9188000000", None),
}
A = {}


def rel(src, dst, op):
    return bytes([op]) + struct.pack("<i", dst - (src + 5))


def c_entries(va):
    return asm(f"""
        jmp  {A['scan_any']:#x}
    """, va)


def c_scan(va):
    """scan(eax = player P, dl = mode) -> eax 1/0 over the active 0x57 records (caster C):
    mode 0 any; 1 C == P; 2 C == P or P and C allied."""
    src = f"""
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, 8
        mov  dword ptr [esp], eax
        mov  byte ptr [esp + 4], dl
        {{ANC}}
        mov  eax, dword ptr [ebx + {{MAP}}]
        test eax, eax
        je   s_no
        mov  eax, dword ptr [eax + 0x188]
        test eax, eax
        je   s_no
        mov  esi, dword ptr [eax + 0x14]
        test esi, esi
        je   s_no
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  edi, eax
    s_loop:
        dec  edi
        js   s_no
        mov  eax, esi
        mov  edx, edi
        call {GETENCH:#x}
        test eax, eax
        je   s_loop
        cmp  byte ptr [eax + 0x18], {STY_TYPE:#x}
        jne  s_loop
        test byte ptr [eax + 0x10], 1
        je   s_loop
        cmp  byte ptr [esp + 4], 0
        je   s_yes
        movsx ebp, byte ptr [eax + 0x19]
        cmp  ebp, dword ptr [esp]
        je   s_yes
        cmp  byte ptr [esp + 4], 2
        jne  s_loop
        cmp  dword ptr [esp], 0
        jle  s_loop
        test ebp, ebp
        jle  s_loop
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x140]
        mov  dl, byte ptr [esp]
        mov  ecx, ebp
        call {GETRELATION:#x}
        cmp  al, 2
        jne  s_loop
    s_yes:
        mov  eax, 1
        jmp  s_out
    s_no:
        xor  eax, eax
    s_out:
        add  esp, 8
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP})


def c_scan_any(va):
    return asm(f"""
        or   eax, -1
        xor  edx, edx
        jmp  {A['scan']:#x}
    """, va)


def c_reg_spell(va):
    src = f"""
        call {REGISTER_SPELL:#x}
        push esi
        push edi
        {{ANC}}
        mov  eax, dword ptr [esi + {{WSCELL}}]
        xor  ecx, ecx
        mov  dl, 1
        call {WARDSPELL_CREATE:#x}
        mov  edi, eax
        lea  eax, [edi + 8]
        lea  edx, [esi + {{NAME}}]
        call {LSTRASG:#x}
        mov  dword ptr [edi + 0x10], {SPELL_ID}
        mov  dword ptr [edi + 0x14], {MANA}
        mov  dword ptr [edi + 0x18], {RESEARCH}
        mov  dword ptr [edi + 0x1c], {UPKEEP}
        mov  byte ptr [edi + 0x20], {SPHERE}
        mov  byte ptr [edi + 0x21], {TIER}
        mov  edx, edi
        mov  eax, ebx
        call {REGISTER_SPELL:#x}
        pop  edi
        pop  esi
        ret
    """
    return pic(src, va, "esi", {"WSCELL": WARDSPELL_CELL, "NAME": ("TAIL", 8)}, ansistr(SPELL_NAME))


def c_create(va):
    """TSpellWard +0xA0 CreateEnchantment(eax = the spell) -> eax the record."""
    src = f"""
        cmp  dword ptr [eax + 0x10], {SPELL_ID}
        jne  {WARD_CREATEENCH:#x}
        push ebx
        push esi
        {{ANC}}
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, dword ptr [esi + {{WCELL}}]
        call {WARD_CREATE:#x}
        mov  ebx, eax
        push {UPKEEP}
        lea  ecx, [esi + {{NAME}}]
        mov  dl, {STY_TYPE:#x}
        mov  eax, ebx
        call {GE_SETUP:#x}
        mov  eax, ebx
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "esi", {"WCELL": WARD_CELL, "NAME": ("TAIL", 8)}, ansistr(SPELL_NAME))


def c_canact(va):
    """ward +0x64 CanActivate(eax rec, dl player, ecx var msg) -> al."""
    src = f"""
        cmp  byte ptr [eax + 0x18], {STY_TYPE:#x}
        jne  {GE_CANACT:#x}
        push eax
        push edx
        push ecx
        movsx eax, dl
        mov  dl, 1
        call {A['scan']:#x}
        test eax, eax
        pop  ecx
        pop  edx
        pop  eax
        je   {GE_CANACT:#x}
        push ebp
        mov  ebp, esp
        add  esp, -0x10
        push ebx
        push esi
        xor  ebx, ebx
        mov  dword ptr [ebp - 4], ebx
        mov  dword ptr [ebp - 8], ebx
        mov  esi, ecx
        mov  ebx, eax
        xor  eax, eax
        push ebp
        {{ANC}}
        lea  ecx, [ecx + {{HNDL}}]
        push ecx
        push dword ptr fs:[eax]
        mov  dword ptr fs:[eax], esp
        jmp  {CANACT_REFUSE:#x}
    """
    return pic(src, va, "ecx", {"HNDL": CANACT_HANDLER})


def c_gf(va):
    """gf(eax = x, edx = y, ecx = level) -> eax the field or 0.  Callers' ebx = the anchor."""
    src = f"""
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        mov  edx, ecx
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x10]
        call {GETMAPLEVEL:#x}
        test eax, eax
        je   g_no
        test esi, esi
        js   g_no
        cmp  esi, dword ptr [eax + 0xc]
        jge  g_no
        test edi, edi
        js   g_no
        cmp  edi, dword ptr [eax + 0x10]
        jge  g_no
        mov  edx, esi
        mov  ecx, edi
        call {LEVEL_GETFIELD:#x}
        pop  edi
        pop  esi
        ret
    g_no:
        xor  eax, eax
        pop  edi
        pop  esi
        ret
    """
    return src


def c_turn(va):
    """TAbstractUnit.NewTurnDone entry: eax = the unit, dl = the player whose turn starts.  Locals:
    [esp] the location bytes, +4/+8 the hex x/y, +0xC its level, +0x10/+0x14 a neighbour x/y."""
    r = SITES["turn"]
    src = f"""
        push eax
        push edx
        push ecx
        call t_body
        pop  ecx
        pop  edx
        pop  eax
        push ebx
        push esi
        mov  esi, eax
        mov  bl, byte ptr [esi + 0x24]
        jmp  {r[2]:#x}
    t_body:
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, 0x20
        mov  esi, eax
        movsx ebp, dl
        movsx eax, byte ptr [esi + 0x24]
        cmp  eax, ebp
        jne  t_out
        test ebp, ebp
        jle  t_out
        {{ANC}}
        mov  eax, ebp
        mov  dl, 2
        call {A['scan']:#x}
        test eax, eax
        je   t_out
        lea  eax, [esp + 2]
        push eax
        lea  ecx, [esp + 5]
        lea  edx, [esp + 4]
        mov  eax, esi
        call {GETLOCATION:#x}
        movzx eax, byte ptr [esp]
        cmp  al, 0xff
        je   t_out
        mov  dword ptr [esp + 4], eax
        movzx eax, byte ptr [esp + 1]
        mov  dword ptr [esp + 8], eax
        movsx eax, byte ptr [esp + 2]
        mov  dword ptr [esp + 0xc], eax
        xor  edi, edi
    t_hex:
        mov  eax, dword ptr [esp + 4]
        mov  edx, dword ptr [esp + 8]
        test edi, edi
        je   t_at
        lea  ecx, [esp + 0x10]
        push ecx
        lea  ecx, [esp + 0x18]
        push ecx
        mov  ecx, edi
        call {CENTERHN:#x}
        mov  eax, dword ptr [esp + 0x10]
        mov  edx, dword ptr [esp + 0x14]
    t_at:
        mov  ecx, dword ptr [esp + 0xc]
        call t_gf
        test eax, eax
        je   t_next
        mov  cl, byte ptr [eax + 0x14]
        cmp  cl, {WATER:#x}
        je   t_water
        cmp  cl, {CAVE_WATER:#x}
        je   t_water
    t_next:
        inc  edi
        cmp  edi, 7
        jl   t_hex
        jmp  t_out
    t_water:
        mov  eax, esi
        mov  edx, {STATUS:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        jne  t_data
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xf0]
        test al, {PHYS_BIT:#x}
        jne  t_out
        mov  eax, esi
        mov  edx, {STATUS:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x94]
    t_data:
        mov  eax, esi
        mov  edx, {STATUS:#x}
        call {GETABDATA:#x}
        test eax, eax
        je   t_out
        mov  byte ptr [eax + 0xc], 1
        mov  edx, ebp
        mov  byte ptr [eax + 0xd], dl
    t_out:
        add  esp, 0x20
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    t_gf:
    """ + c_gf(va)
    return pic(src, va, "ebx", {"MAP": AOWHSMAP})


def c_pp(va):
    """Replaces `call [ecx+0x88]` (eax = ebx = the owner, edx = 0x4D)."""
    return asm(f"""
        call dword ptr [ecx + 0x88]
        test al, al
        jne  p_out
        mov  edx, {STATUS:#x}
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x88]
    p_out:
        ret
    """, va)


def c_reg_ab(va):
    src = f"""
        call {REGISTER_ABILITY:#x}
        push esi
        push edi
        {{ANC}}
        lea  eax, [esi + {{DURVMT}}]
        xor  ecx, ecx
        mov  dl, 1
        call {DUR_CREATE:#x}
        mov  dword ptr [eax + 0xc], {STATUS:#x}
        mov  byte ptr [eax + 0x24], 4
        mov  word ptr [eax + 0x20], 0
        mov  byte ptr [eax + 0x28], 1
        push eax
        lea  eax, [eax + 8]
        lea  edx, [esi + {{NAME}}]
        call {LSTRASG:#x}
        mov  eax, {VMT_NEG + DUR_SLOTS:#x}
        call {GETMEM:#x}
        push esi
        mov  edi, eax
        mov  esi, dword ptr [esp + 4]
        mov  esi, dword ptr [esi]
        sub  esi, {VMT_NEG:#x}
        mov  ecx, {(VMT_NEG + DUR_SLOTS) // 4:#x}
        cld
        rep movsd dword ptr es:[edi], dword ptr [esi]
        pop  esi
        lea  edx, [eax + {VMT_NEG:#x}]
        mov  dword ptr [eax], edx
        lea  ecx, [esi + {{DURONE}}]
        mov  dword ptr [edx + 0x110], ecx
        lea  ecx, [esi + {{DURSELF}}]
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
    return pic(src, va, "esi", {"DURVMT": VMT_DUR, "DURSELF": VMT_DUR - VMT_NEG, "DURONE": DUR_ONE,
                                "NAME": ("TAIL", 8)}, ansistr(STATUS_NAME))


BUILDERS = [
    ("entries", c_entries),
    ("scan", c_scan), ("scan_any", c_scan_any), ("reg_spell", c_reg_spell), ("create", c_create),
    ("canact", c_canact), ("turn", c_turn), ("pp", c_pp), ("reg_ab", c_reg_ab),
]


def layout():
    for name, _b in BUILDERS:           # forward references: far enough for rel32 on the first pass
        A.setdefault(name, SLOT[0] + 0x700)
    for _ in range(3):
        va, blobs = SLOT[0], []
        for name, b in BUILDERS:
            A.setdefault(name, va)
            A[name] = va
            blob = b(va)
            blobs.append(("cave_" + name, va, blob))
            va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    assert A["entries"] == STY_ANY
    return blobs


def checks(d):
    u = lambda v: struct.unpack_from("<I", d, P.va2off(d, v))[0]
    if u(WARDSPELL_CELL) != 0x557EF6D8 or u(WARD_CELL) != 0x557EF5B4:
        sys.exit("ABORT: a TSpellWard class cell moved")
    cn = P.va2off(d, u(VMT_DUR - 0x20))
    if u(VMT_DUR - 0x40) != VMT_DUR or d[cn + 1:cn + 1 + d[cn]] != b"TDurationAbility":
        sys.exit("ABORT: TDurationAbility's VMT moved")
    if u(VMT_DUR - 0x20) - VMT_DUR != DUR_SLOTS:
        sys.exit("ABORT: TDurationAbility's VMT changed size")
    o = P.va2off(d, DUR_ONE)
    if d[o:o + 6] != bytes.fromhex("b801000000c3"):
        sys.exit("ABORT: %08X no longer returns 1" % DUR_ONE)
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:
        for i in range(ra, ra + rs - 7):
            src = P.IMAGE_BASE + sva + (i - ra)
            if SLOT[0] <= src < SLOT[1]:
                continue
            if d[i:i + 3] == b"\xc7\x40\x10" and struct.unpack_from("<I", d, i + 3)[0] == SPELL_ID:
                sys.exit("ABORT: %08X also stores spell id %d" % (src, SPELL_ID))
            if d[i:i + 3] == b"\xc7\x40\x0c" and struct.unpack_from("<I", d, i + 3)[0] == STATUS:
                sys.exit("ABORT: %08X also stores ability id %#x" % (src, STATUS))


def main():
    from build_lethe import interior_jumps
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d)
    pk = lambda v: struct.pack("<I", v)
    hooks = [(S_REGSPELL, rel(S_REGSPELL, REGISTER_SPELL, 0xE8), rel(S_REGSPELL, A["reg_spell"], 0xE8)),
             (S_REGAB, rel(S_REGAB, REGISTER_ABILITY, 0xE8), rel(S_REGAB, A["reg_ab"], 0xE8)),
             (S_CREATE, pk(WARD_CREATEENCH), pk(A["create"])),
             (S_CANACT, pk(GE_CANACT), pk(A["canact"]))]
    va, orig, _r = SITES["turn"]
    orig = bytes.fromhex(orig)
    hooks.append((va, orig, rel(va, A["turn"], 0xE9) + b"\x90" * (len(orig) - 5)))
    va2, orig2, _r = SITES["pp"]
    orig2 = bytes.fromhex(orig2)
    hooks.append((va2, orig2, rel(va2, A["pp"], 0xE8) + b"\x90"))
    bad = interior_jumps(d, [(va, va + len(orig)), (va2, va2 + len(orig2))])
    if bad:
        sys.exit("ABORT: jumps into a hook's interior: " + ", ".join("%08X->%08X" % x for x in bad))
    print("  interior sweep: no branch lands inside a displaced range")
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    # build_blazing_moon.py's cave_create / cave_canact (pinned there) chain in front of ours: an
    # accepted applied state; --apply and --undo refuse while they are in place.
    moon = {S_CREATE: 0x558C5100, S_CANACT: 0x558C5160}
    held = [va for va, m in moon.items() if d[P.va2off(d, va):P.va2off(d, va) + 4] == pk(m)]
    if held:
        if "--apply" in sys.argv or "--undo" in sys.argv:
            sys.exit("REFUSED: build_blazing_moon.py chains through %s; undo it first."
                     % ", ".join("%08X" % v for v in held))
        hooks = [(va, van, pk(moon[va]) if va in held else new) for va, van, new in hooks]
        print("  chained: build_blazing_moon.py holds %s (accepted as applied)"
              % ", ".join("%08X" % v for v in held))
    run("build_blessing_stygia -- Blessing of Stygia (AoWEPACK)", hooks, blobs, SLOT, [],
        reloc_ok=(S_CREATE, S_CANACT))


if __name__ == "__main__":
    main()
