#!/usr/bin/env python
r"""
build_weakness.py -- seven Weakness abilities, the inverse of the Protections: Fire, Cold,
Lightning, Magic, Poison, Death and Holy Weakness (no Physical Weakness, owner's ruling
2026-09-25; Embrittled 0xB2 already covers physical).  AoWEPACK.dpl.

Design from Inioch's AoWx weakness abilities (share8 weakness-abilities-SHELVED.md -- done and
confirmed in his game despite the file name); re-derived on our DLL, which differs at every site.

WHAT A WEAKNESS DOES (damage bit b, ability id 0xB3 + b)
    damage  x1.5, rounded up ((3d+1)>>1, capped at 126 like Embrittled), when a hit carries a type
            the unit is weak to and not protected against.
    effects -4 on the Resistance check against that type's status effect (Burning, Frozen,
            Stunned, Poisoned, Cursed, Vertigo) and on typed resistance rolls -- the mirror of our
            Protection's +4 (0x55781C1E etc.).  Magic has damage only, as its Protection does.
    cancelling: Protection + Weakness of one type = neither (the protection's halving is dropped,
            the x1.5 is not applied, the +4 and -4 sum to 0).  Immunity wins outright: an immune
            type is removed from the hit before any of this runs.  Every protection/immunity source
            (abilities, items, enchantments, Fire Halo, Blessed, Liquid Form) comes through the
            engine's own GetProtectionTypes / GetImmunityTypes, so all of them cancel.

REGISTRATION
    Seven TEnhancementAbility passives through CreateEnhancementAbility 0x5576601C +
    RegisterAbility 0x55750238, spliced at the free `call RegisterAbility` 0x557BCDFB inside
    PassiveAb.RegisterPassiveAbilities (EBX = the control).  Ids measured free on every run
    (check_ids): the DLL's `mov eax,<id> / call CreateEnhancementAbility` idioms and Release/
    Ability.pfs keys; highest in use before this was 0xB2 (Embrittled).
    Selection mask 0x027F = astUnit | the five item slots | astEditor: assignable to units, heroes
    and items in the editor, never offered at hero level-up (that needs 0x100) or at leader
    customisation (0x80).  Records (description, mask, no level-up cost): build_weakness_pfs.py.
    ⚠ The tactical ceilings must cover 0xB9: build_abilityid_ceilings.py and
    build_tcablist_ceiling.py LADDERs append 0xBA.

HOOKS (all vanilla bytes except where noted; none carries a .reloc)
    R  0x557BCDFB  call RegisterAbility -> cave_reg (replays it, then registers the seven)
    S1 0x55726A43  TCombatObject strike funnel (ExecuteDamageRole, the one at 0x557269EF), the 6 B
                   after build_embrittle.py's `call 0x5582D130` (which returns the protection mask):
                   `nop / not eax / and ax,si` -> cave_strike1
    S2 0x55726AD8  the same in TCombatObject.ExecuteDamageRoleEx -> cave_strike2
       (EBX = the combat object, SI = hit types minus immunities, EDI = damage, EAX = protection;
       ability test through the combat object's GetAbilityEnabled, VMT +0xA8)
    T  0x55781B14  TAbstractUnit.ExecuteDamageRole (strategic hits), the 10 B protection call ->
                   cave_strat (ability test via the strategic unit's VMT +0x148)
    E1..E6         TAbstractUnit.ExecuteDamageEffectsRole, each block's `mov eax,0xA / sub eax,edi`
                   (7 B, just before its effect roll) -> cave_eff_k: -4 via EDI when weak
                   0x55781C30 fire  0x55781C90 lightning  0x55781CE2 poison
                   0x55781D34 death 0x55781D86 holy       0x55781DE6 cold
    X  0x55781B84  TAbstractUnit.ExecuteResistanceRole, after its protection `sub edi,4`: the 10 B
                   GetResistance call -> cave_resist, EDI += 4 when weak to type BL

Rolls: none added and none moved -- only thresholds and amounts change, so the draw count is
identical and multiplayer stays in lockstep.  PIC: rel32 and register-relative only; the names
are read through a call/pop anchor.  Slot 0x5584DB00-0x5584DEFF, exclusive.  Surgical --undo.
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584DB00, 0x5584DF00)
CAVE = 0x5584DB00
FIRST_ID = 0xB3
NAMES = ["Fire Weakness", "Cold Weakness", "Lightning Weakness", "Magic Weakness",
         "Poison Weakness", "Death Weakness", "Holy Weakness"]          # damage bits 0..6
MASK = 0x027F
CEA, REGISTER = 0x5576601C, 0x55750238
SPLICE = 0x557BCDFB
S1, S1_BACK = 0x55726A43, 0x55726A49
S2, S2_BACK = 0x55726AD8, 0x55726ADE
T_SITE, T_BACK = 0x55781B14, 0x55781B1E
X_SITE, X_BACK = 0x55781B84, 0x55781B8E
EFF = [(0x55781C30, 0), (0x55781C90, 2), (0x55781CE2, 4),
       (0x55781D34, 5), (0x55781D86, 6), (0x55781DE6, 1)]            # (site, damage bit)
EFF_VAN = bytes.fromhex("b80a0000002bc7")                            # mov eax,0xA / sub eax,edi
DMG_CAP = 0x7E


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def ansistr(s):
    b = s.encode("latin1")
    return struct.pack("<iI", -1, len(b)) + b + b"\0"


def build_weakmask(va):
    """eax = object, ecx = VMT offset of its GetAbilityEnabled -> eax = weakness bit mask.
    Preserves ebx, esi, edi, ebp."""
    return asm(f"""
        push ebx
        push esi
        push edi
        push ebp
        mov  esi, eax
        mov  ebp, ecx
        xor  edi, edi
        mov  ebx, 6
    wm_loop:
        lea  edx, [ebx + {FIRST_ID:#x}]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        add  ecx, ebp
        call dword ptr [ecx]
        test al, al
        je   wm_next
        bts  edi, ebx
    wm_next:
        dec  ebx
        jns  wm_loop
        mov  eax, edi
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


def body_scale(wm, slot_off):
    """Common tail: EAX = protection on entry -> EDI scaled when weak, EAX = effective protection."""
    return f"""
        push eax
        mov  eax, ebx
        mov  ecx, {slot_off:#x}
        call {wm:#x}
        pop  edx
        mov  ecx, edx
        not  ecx
        and  ecx, eax
        test cx, si
        je   b_noboost
        test edi, edi
        jle  b_noboost
        lea  edi, [edi + edi*2 + 1]
        sar  edi, 1
        cmp  edi, {DMG_CAP:#x}
        jle  b_noboost
        mov  edi, {DMG_CAP:#x}
    b_noboost:
        not  eax
        and  eax, edx
    """


def build_strike(va, wm, back):
    return asm(body_scale(wm, 0xA8) + f"""
        not  eax
        and  ax, si
        jmp  {back:#x}
    """, va)


def build_strat(va, wm):
    return asm(f"""
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xf0]
    """ + body_scale(wm, 0x148) + f"""
        jmp  {T_BACK:#x}
    """, va)


def build_eff(va, site, bit):
    return asm(f"""
        mov  eax, ebx
        mov  edx, {FIRST_ID + bit:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        je   e_go
        sub  edi, 4
    e_go:
        mov  eax, 0xa
        sub  eax, edi
        jmp  {site + 7:#x}
    """, va)


def build_resist(va):
    return asm(f"""
        cmp  bl, 6
        ja   r_go
        movzx edx, bl
        add  edx, {FIRST_ID:#x}
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        je   r_go
        add  edi, 4
    r_go:
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xcc]
        jmp  {X_BACK:#x}
    """, va)


def build_reg(va):
    """Replays the displaced RegisterAbility, then registers the seven.  One anchor per ability:
    `mov eax,<id>` destroys EAX between registrations.  The anchor is emitted as raw E8 00000000
    (keystone assembles `call $+5` to nothing)."""
    code = bytearray(asm(f"call {REGISTER:#x}", va))
    fix = []
    for i in range(len(NAMES)):
        at = va + len(code)
        code += b"\xE8\x00\x00\x00\x00"
        anchor = at + 5
        code += asm("pop eax", anchor)
        fix.append((len(code), anchor, i))            # lea edx,[eax+disp32] patched below
        code += b"\x8D\x90" + b"\0\0\0\0"
        cur = va + len(code)
        code += asm(f"""
            mov  cx, {MASK:#x}
            mov  eax, {FIRST_ID + i:#x}
            call {CEA:#x}
            mov  edx, eax
            mov  eax, ebx
            call {REGISTER:#x}
        """, cur)
    code += b"\xC3"
    while len(code) % 4:
        code += b"\x90"
    lits = []
    for i, n in enumerate(NAMES):
        lits.append(va + len(code) + 8)               # the chars; header is 8 B before
        code += ansistr(n)
        while len(code) % 4:
            code += b"\0"
    for off, anchor, i in fix:
        struct.pack_into("<i", code, off + 2, lits[i] - anchor)
    return bytes(code)


def layout():
    caves, va = [], CAVE
    def put(name, blob):
        nonlocal va
        caves.append((name, va, blob))
        va = (va + len(blob) + 0xF) & ~0xF
    wm = CAVE
    put("weak_mask", build_weakmask(wm))
    put("cave_strike1", build_strike(va, wm, S1_BACK))
    put("cave_strike2", build_strike(va, wm, S2_BACK))
    put("cave_strat", build_strat(va, wm))
    put("cave_resist", build_resist(va))
    effs = []
    for site, bit in EFF:
        effs.append((site, va))
        put("cave_eff_%x" % site, build_eff(va, site, bit))
    put("cave_reg", build_reg(va))
    return caves, effs


def check_ids():
    """Every id we register must be free: no other CreateEnhancementAbility idiom in the DLL, and
    no record in Release/Ability.pfs unless it is ours (a DevEd save writes our own records)."""
    d = open(P.TARGET, "rb").read()
    _e, secs = P.sections(d)
    vs, sva, rs, ra = secs[0]
    used = set()
    for i in range(ra, ra + rs - 5):
        if d[i] == 0xE8:
            src = P.IMAGE_BASE + sva + (i - ra)
            if src + 5 + struct.unpack_from("<i", d, i + 1)[0] == CEA:
                for k in range(5, 30):
                    if d[i - k] == 0xB8:
                        used.add((struct.unpack_from("<I", d, i - k + 1)[0], src))
                        break
    ours_lo, ours_hi = SLOT
    foreign = sorted(i for i, src in used if FIRST_ID <= i < FIRST_ID + len(NAMES)
                     and not ours_lo <= src < ours_hi)
    if foreign:
        sys.exit("ABORT: ids %s are already registered elsewhere" % [hex(i) for i in foreign])
    top = max(i for i, _s in used if i < 0x100 and not ours_lo <= _s < ours_hi)
    if top >= FIRST_ID:
        sys.exit("ABORT: something registers %#x -- re-derive FIRST_ID" % top)
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "re_tools"))
    import pfs
    keys = {rid - 10 for rid, _b in pfs.load("ability.pfs")[0]}
    have = [hex(i) for i in range(FIRST_ID, FIRST_ID + len(NAMES)) if i in keys]
    print("  ids %#x..%#x free (highest other CreateEnhancementAbility id %#x); Ability.pfs records "
          "present for %s" % (FIRST_ID, FIRST_ID + len(NAMES) - 1, top, have or "none"))


caves, effs = layout()
hooks = [(SPLICE, call_to(SPLICE, REGISTER), call_to(SPLICE, caves[-1][1])),
         (S1, bytes.fromhex("90f7d06623c6"), jmp_to(S1, caves[1][1], 6)),
         (S2, bytes.fromhex("90f7d06623c6"), jmp_to(S2, caves[2][1], 6)),
         (T_SITE, bytes.fromhex("8bc38b10ff92f0000000"), jmp_to(T_SITE, caves[3][1], 10)),
         (X_SITE, bytes.fromhex("8bc68b10ff92cc000000"), jmp_to(X_SITE, caves[4][1], 10))]
hooks += [(site, EFF_VAN, jmp_to(site, cva, 7)) for site, cva in effs]
interior = [(S1, S1 + 6, 0x557269EF, 0x55726A68), (S2, S2 + 6, 0x55726A6C, 0x55726B00),
            (T_SITE, T_SITE + 10, 0x55781ACA, 0x55781B42), (X_SITE, X_SITE + 10, 0x55781B48, 0x55781BA4)]
interior += [(site, site + 7, 0x55781BA4, 0x55781E0A) for site, _c in effs]

if __name__ == "__main__":
    check_ids()
    run("build_weakness", hooks, caves, SLOT, interior)
