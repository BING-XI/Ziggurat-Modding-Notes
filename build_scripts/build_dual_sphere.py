#!/usr/bin/env python
r"""
build_dual_sphere.py -- the dual-sphere spell groundwork in AoWEPACK.dpl: the side table, the
turn-start grant, the unit tier gate and the Mastery cost for two spheres.

Owner's rules (2026-10-24/25, 05-spells-added.md "Dual-sphere spells" and "Death/Fire -- the first
pair"): dual tiers 1-3, never researched; a pair's tier N is GRANTED, at a player's turn start, once
tier N of BOTH its spheres is known; the event log names the spell; units (not heroes) need
Spellcasting tier+1; both spheres' Mastery modifiers apply and multiply.

HOW A DUAL SPELL IS STORED
  sphere byte [spell+0x20] = 7 (Secret) and tier [spell+0x21] = its dual tier 1-3.  Ziggurat has no
  Secret spells (the four vanilla ones were moved to Cosmos), and a leader can never pick Secret, so
  GetSpherePicks(7) is 0 and every research, tier-grant, day-1, campaign and Magic-tab loop that
  matches a (sphere, tier) word skips these spells untouched -- no other script's cave changes.
  The two real spheres live in TABLE (u16 spell id, u8 first sphere, u8 second sphere; 0xFFFF ends
  it).  TABLE and dual_find are PINNED: the exe half and later spell scripts reach them by address.

SITES (all rel32 retargets; nothing displaced)
  grant   0x5577CE54  TPlayerMagicControl.NewTurn's last `call Update` -> cave_grant, which ends
          `jmp Update`.  Runs every turn for every player on every peer (lockstep, no RNG).
  gate    0x5584601F  build_spellcast_herotier.py's non-hero tail `jmp cave_tiergate` -> cave_gate:
          a sphere-7 spell compares Spellcasting (vcall +0x144, item-aware) >= tier + 1; anything
          else goes on to cave_tiergate.  Heroes never reach this tail (ungated by ruling).
  mastery 0x557894F8  build_mastery_cost.py's hook `jmp cave` -> cave_mastery: a dual spell gets
          the per-sphere step (opposed x1.5, own x0.75) for each of its two spheres; anything else
          goes on to that script's cave.
  Both chained scripts accept this retarget as their applied state and refuse --undo while it is
  in place.  ⚠ Undo THIS script before undoing either of them.

cave_grant: one registry pass counts, per (sphere 1-6, tier 1-4), the spells a tier grant would
  give (category <= 2, vmt+0x64 enabled; the filter of build_tierresearch_dll.py's cave_grant) and
  how many of them the player knows.  "Tier N of S known" = count > 0 and all known.  Then each TABLE
  entry not yet known, registered and enabled, whose spheres both have its tier known, is added with
  ExecuteSpellResearched and a TLocationTextEventLog "Spell learned: <name>" goes to that player's
  logbook (history only, no popup).  Skips player id 0.
  Tower-bought spells count as known, so buying the last missing spell of a tier completes it.

Slot 0x558B6000-0x558B67FF, exclusive.  PIC.  No RNG.  Surgical --undo.

    python build_scripts/build_dual_sphere.py            dry run + state
    python build_scripts/build_dual_sphere.py --apply
    python build_scripts/build_dual_sphere.py --undo
    python build_scripts/build_dual_sphere.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic, ansistr

DEATH, FIRE = 2, 5
# spell id -> (first sphere, second sphere).  The first-named sphere goes on the left of the icon.
DUALS = [
    (80, DEATH, FIRE),      # Taint the Flame      (build_taint_flame.py)
    (81, DEATH, FIRE),      # Pillar of Banefire   (build_pillar_banefire.py)
    (82, DEATH, FIRE),      # Enmity of Nine Hells (build_demon_curse.py)
]
DUAL_SPHERE = 7             # the sphere byte every dual spell carries
MAX_DUALS = 63

SLOT = (0x558B6000, 0x558B6800)
TABLE = 0x558B6000          # PINNED: 4 B per entry, 0xFFFF terminator, 0x100 B
DUAL_FIND = 0x558B6100      # PINNED: in EDX = spell id; out EAX = entry or 0 (ZF), all else kept
CAVE_GRANT = 0x558B6140
CAVE_GATE = 0x558B6340
CAVE_MASTERY = 0x558B63A0

AOWHSSET = 0x558FA044       # [.] = AoWHSSet; [+0x84] = TSpellControl
GETCOUNT, GETSPELL = 0x55779AC0, 0x55779AC8
INDEXOF = 0x55702EA4
EXEC_RESEARCHED = 0x5577CBF8
UPDATE = 0x5577D248
LSTRCAT3 = 0x55701190
EVLOG_CELL = 0x557FC624     # [.] = TLocationTextEventLog VMT 0x557FC664
EVLOG_CREATE = 0x557FDC74
ADD_EVENT = 0x557FDB90
TIERGATE, CANCAST_CONT, CANCAST_FAIL = 0x5580D95E, 0x55789753, 0x55789826
MASTERY_CAVE, CASTMANA_EXIT = 0x55812880, 0x55789510

H_GRANT, H_GATE, H_MASTERY = 0x5577CE54, 0x5584601F, 0x557894F8


def rel(src, dst, op):
    return bytes([op]) + struct.pack("<i", dst - (src + 5))


def table_blob():
    assert len(DUALS) <= MAX_DUALS
    b = b"".join(struct.pack("<HBB", i, a, c) for i, a, c in DUALS) + b"\xff\xff"
    return b + b"\0" * (0x100 - len(b))


def cave_find():
    return pic("""
        push ecx
        {ANC}
        lea  eax, [ecx + {TABLE}]
    Lloop:
        cmp  word ptr [eax], 0xffff
        je   Lnone
        cmp  word ptr [eax], dx
        je   Lfound
        add  eax, 4
        jmp  Lloop
    Lnone:
        xor  eax, eax
    Lfound:
        pop  ecx
        test eax, eax
        ret
    """, DUAL_FIND, "ecx", {"TABLE": TABLE})


def cave_grant():
    # Stack while the grid is live: [esp+0x00..0x17] total[sphere-1][tier-1], [esp+0x18..0x2F] known.
    # ebp = magic control, esi = spell control, ebx = anchor, edi = loop index / table entry.
    src = f"""
        pushad
        sub  esp, 0x30
        mov  ebp, eax
        mov  eax, dword ptr [ebp + 0x10]
        cmp  byte ptr [eax + 0xa6], 0
        je   Ldone
        mov  edi, esp
        xor  eax, eax
        mov  ecx, 12
        cld
        rep stosd
        {{ANC}}
        mov  eax, dword ptr [ebx + {{HSSET}}]
        mov  esi, dword ptr [eax + 0x84]
        mov  eax, esi
        call {GETCOUNT:#x}
        mov  edi, eax
    Lgrid:
        dec  edi
        js   Lgriddone
        mov  eax, esi
        mov  edx, edi
        call {GETSPELL:#x}
        test eax, eax
        je   Lgrid
        movzx ecx, byte ptr [eax + 0x20]
        dec  ecx
        cmp  ecx, 5
        ja   Lgrid
        movzx edx, byte ptr [eax + 0x21]
        dec  edx
        cmp  edx, 3
        ja   Lgrid
        cmp  byte ptr [eax + 0x22], 2
        ja   Lgrid
        lea  ecx, [ecx*4 + edx]
        push ecx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x64]
        pop  ecx
        test al, al
        je   Lgrid
        inc  byte ptr [esp + ecx]
        push ecx
        mov  eax, dword ptr [ebp + 0x30]
        mov  edx, edi
        call {INDEXOF:#x}
        pop  ecx
        inc  eax
        je   Lgrid
        inc  byte ptr [esp + ecx + 0x18]
        jmp  Lgrid
    Lgriddone:
        lea  edi, [ebx + {{TABLE}}]
    Ldual:
        movzx edx, word ptr [edi]
        cmp  dx, 0xffff
        je   Ldone
        mov  eax, dword ptr [ebp + 0x30]
        call {INDEXOF:#x}
        inc  eax
        jne  Lnext
        movzx edx, word ptr [edi]
        mov  eax, esi
        call {GETSPELL:#x}
        test eax, eax
        je   Lnext
        movzx ecx, byte ptr [eax + 0x21]
        dec  ecx
        cmp  ecx, 3
        ja   Lnext
        push ecx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x64]
        pop  edx
        test al, al
        je   Lnext
        movzx ecx, byte ptr [edi + 2]
        dec  ecx
        cmp  ecx, 5
        ja   Lnext
        lea  ecx, [ecx*4 + edx]
        mov  al, byte ptr [esp + ecx]
        test al, al
        je   Lnext
        cmp  al, byte ptr [esp + ecx + 0x18]
        jne  Lnext
        movzx ecx, byte ptr [edi + 3]
        dec  ecx
        cmp  ecx, 5
        ja   Lnext
        lea  ecx, [ecx*4 + edx]
        mov  al, byte ptr [esp + ecx]
        test al, al
        je   Lnext
        cmp  al, byte ptr [esp + ecx + 0x18]
        jne  Lnext
        mov  eax, ebp
        movzx edx, word ptr [edi]
        call {EXEC_RESEARCHED:#x}
        mov  eax, dword ptr [ebx + {{EVCELL}}]
        mov  dl, 1
        xor  ecx, ecx
        call {EVLOG_CREATE:#x}
        push eax
        mov  edx, dword ptr [ebp + 0x10]
        mov  dl, byte ptr [edx + 0xa6]
        mov  byte ptr [eax + 0x10], dl
        movzx edx, word ptr [edi]
        mov  eax, esi
        call {GETSPELL:#x}
        mov  ecx, dword ptr [eax + 8]
        lea  edx, [ebx + {{LIT}}]
        mov  eax, dword ptr [esp]
        add  eax, 0x18
        call {LSTRCAT3:#x}
        mov  eax, dword ptr [ebp + 0x10]
        mov  eax, dword ptr [eax + 0xd8]
        mov  edx, dword ptr [esp]
        call {ADD_EVENT:#x}
        pop  eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
    Lnext:
        add  edi, 4
        jmp  Ldual
    Ldone:
        add  esp, 0x30
        popad
        jmp  {UPDATE:#x}
    """
    return pic(src, CAVE_GRANT, "ebx",
               {"HSSET": AOWHSSET, "TABLE": TABLE, "EVCELL": EVLOG_CELL, "LIT": ("TAIL", 8)},
               ansistr("Spell learned: "))


def cave_gate():
    return asm(f"""
        cmp  byte ptr [eax + 0x20], {DUAL_SPHERE}
        je   Ldual
        jmp  {TIERGATE:#x}
    Ldual:
        mov  esi, eax
        push esi
        push edi
        push ebx
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        push 0x34
        pop  edx
        call dword ptr [ecx + 0x144]
        pop  ebx
        pop  edi
        pop  esi
        movzx eax, al
        movzx edx, byte ptr [esi + 0x21]
        inc  edx
        cmp  eax, edx
        jl   Lfail
        movsx edx, byte ptr [ebx + 0x24]
        jmp  {CANCAST_CONT:#x}
    Lfail:
        xor  ebx, ebx
        jmp  {CANCAST_FAIL:#x}
    """, CAVE_GATE)


def cave_mastery():
    # in: eax = map, esi = spell, ebx = cost.  Out to CastingMana's exit with ebx scaled.
    return asm(f"""
        cmp  byte ptr [esi + 0x20], {DUAL_SPHERE}
        jne  Lplain
        push edx
        push ecx
        push eax
        mov  edx, dword ptr [esi + 0x10]
        call {DUAL_FIND:#x}
        mov  edx, eax
        pop  eax
        je   Ldone
        mov  eax, dword ptr [eax + 0x188]
        movzx ecx, byte ptr [edx + 2]
        call Lstep
        movzx ecx, byte ptr [edx + 3]
        call Lstep
    Ldone:
        pop  ecx
        pop  edx
        jmp  {CASTMANA_EXIT:#x}
    Lplain:
        jmp  {MASTERY_CAVE:#x}
    Lstep:
        cmp  dword ptr [eax + ecx*4 + 0x18], 0
        jne  Lopposed
        dec  ecx
        xor  ecx, 1
        inc  ecx
        cmp  dword ptr [eax + ecx*4 + 0x18], 0
        je   Lret
        imul ebx, ebx, 3
        shr  ebx, 2
    Lret:
        ret
    Lopposed:
        imul ebx, ebx, 3
        shr  ebx, 1
        ret
    """, CAVE_MASTERY)


def main():
    blobs = [("TABLE", TABLE, table_blob()), ("dual_find", DUAL_FIND, cave_find()),
             ("cave_grant", CAVE_GRANT, cave_grant()), ("cave_gate", CAVE_GATE, cave_gate()),
             ("cave_mastery", CAVE_MASTERY, cave_mastery())]
    hooks = [
        (H_GRANT, rel(H_GRANT, UPDATE, 0xE8), rel(H_GRANT, CAVE_GRANT, 0xE8)),
        (H_GATE, rel(H_GATE, TIERGATE, 0xE9), rel(H_GATE, CAVE_GATE, 0xE9)),
        (H_MASTERY, rel(H_MASTERY, MASTERY_CAVE, 0xE9), rel(H_MASTERY, CAVE_MASTERY, 0xE9)),
    ]
    # Pre-conditions: the two chained scripts must be in place, or our jumps lead nowhere.
    d = open(P.TARGET, "rb").read()
    assert d[P.va2off(d, TIERGATE):P.va2off(d, TIERGATE) + 2] == b"\x89\xc6", \
        "cave_tiergate is not build_spellcast_multiturn.py's body"
    assert d[P.va2off(d, MASTERY_CAVE):P.va2off(d, MASTERY_CAVE) + 6] == bytes.fromhex("8b8088010000"), \
        "build_mastery_cost.py's cave is not at 0x55812880"
    run("build_dual_sphere -- dual-sphere groundwork", hooks, blobs, SLOT, [])


if __name__ == "__main__":
    main()
