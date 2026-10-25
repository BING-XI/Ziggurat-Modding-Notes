#!/usr/bin/env python
r"""
build_wizardtower_dual.py -- Wizard's Towers offer two spells and re-roll (AoWEPACK.dpl half).
Owner's rulings 2026-10-25 (05-spells-added.md, "Death/Fire -- the first pair", Wizard's Towers):

  * A Custom tower (one hand-picked spell) offers that spell and never re-rolls.  Every other
    tower offers two different spells (two offers may share a sphere); each player may buy each
    once (CanBuy already refuses a known spell).
  * A spell is eligible when its sphere is ticked and its tier is in the tower's level set; a dual
    spell (sphere 7, build_dual_sphere.py's TABLE) when BOTH its spheres are ticked, counting as
    level tier+1.  Only spells whose GetEnabled (vmt+0x64) passes; never Warp Party (id 0x22) when
    the map's ban flag map+0x193 is set (build_warpban.py).
  * Random towers re-roll both offers every d20 days; a re-roll also changes the tower hex's
    terrain to a different one of Grass 1, Desert 2, Snow 3, Steppe 4, Wasteland 5, Dirt 0xC (any
    level, never Water) that the tower has art for -- not Grass if an offer is a Death spell, not
    Wasteland if one is a Life spell (dual spheres count).  The day-1 roll keeps the map terrain.
  * Old saves: a random tower that already has its first spell rolls the second and re-rolls on
    the next day.
  * The AI buys the cheaper valid offer, then the other if it can still afford it.
  * Price unchanged: 3/8 of the research cost (BuyCost, the owner's hand-edit cave 0x5580C211).
  * New towers (the editor) get a random sphere set, never Life with Death; existing ones keep
    theirs (ReadWrite overwrites the default).

STATE (TWizardsTower instance 0x38 -> 0x40, dword 0x557D54EC; no subclass, no .reloc)
  +0x38 dword  the second offer (0 = none)                           rwInteger id 0x22
  +0x3C byte   level set, bit n = level n+1 (0 = derive from +0x33)  \
  +0x3D byte   1 = rolled by this code                                > one rwInteger, id 0x23
  +0x3E word   day of the next re-roll                               /
  (TStructure's chain uses 0, 1, 3, 4, 0x62, 0x63; the tower 0x1E-0x21.)

SITES
  VMT 0x557D5508 slots (.reloc kept): +0x18 ReadWrite -> cave_rw, +0x168 ExecuteTE -> cave_exec,
  +0x174 NewDay -> cave_newday, +0x180 ArmyPlaced -> cave_placed, +0x1C4 UpdateAITarget -> cave_upd.
  buy     0x557D604C  Buy's `movsx esi,bl / mov [edi+0x20],esi` -> call cave_buy + nop: the token
          also carries the bought spell in TE+0x24 (TStructureTE streams it as id 0x17; vanilla
          leaves it 0).  The exe half swaps +0x34/+0x38 around its Buy call for the second offer.
  create  0x557D59CB  Create's `mov byte [esi+0x33],2 / test bl,bl` -> call cave_create + nop: a
          random sphere set from rdtsc (no game RNG stream is touched; in the game every tower
          comes from a map or save, whose ReadWrite replaces it).
  cave_exec: TE+0x24 = 0 (an old token) buys slot A as before; = slot B's spell swaps A/B around
          the vanilla ExecuteTE; anything else (re-rolled since) blanks A so CanBuy refuses.
  cave_upd / cave_placed: pick the AI's slot (both valid -> the cheaper, else the valid one) and
          swap A/B around the vanilla method; after a purchase cave_placed buys the other offer
          too when CanBuy passes (same SetGems + known-list Add as vanilla, no token: ArmyPlaced is
          synchronised).

RNG: P1 SYNCED DRAW (host TWizardsTower.NewDay; vanilla GetRandomSpell drew P1 there): offer A,
  offer B, the re-roll terrain and the d20, all TAoWHSMap.Random 0x5577827C.  The rdtsc in
  cave_create feeds no game state.

COUPLINGS: reads build_dual_sphere.py's dual_find 0x558B6100 and build_warpban.py's map+0x193.
  The exe half (build_wizardtower_dual_exe.py) needs this half; the editor half
  (build_wizardtower_dual_editor.py) writes +0x3C.

Slot 0x558B8000-0x558B8FFF, exclusive.  PIC.  Surgical --undo (restores 0x38; towers saved while
applied carry ids 0x22/0x23, which vanilla's reader skips).

    python build_scripts/build_wizardtower_dual.py            dry run + state
    python build_scripts/build_wizardtower_dual.py --apply
    python build_scripts/build_wizardtower_dual.py --undo
    python build_scripts/build_wizardtower_dual.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic

SLOT = (0x558B8000, 0x558B9000)

TOWER_VMT = 0x557D5508
INST_VA, INST_OLD, INST_NEW = 0x557D54EC, 0x38, 0x40
TAG_B, TAG_PACK = 0x22, 0x23
WARP_ID, WARP_FLAG = 0x22, 0x193
TERRAINS = (1, 2, 3, 4, 5, 0xC)
GRASS, WASTELAND, LIFE, DEATH = 1, 5, 1, 2
DUAL_SPHERE = 7

AOWHSMAP, AOWHSSET = 0x558FA040, 0x558FA044
DUAL_FIND = 0x558B6100
GETCOUNT, GETSPELL = 0x55779AC0, 0x55779AC8
INDEXOF, ILIST_ADD = 0x55702EA4, 0x55702E74
GETPLAYERS, RANDOM, SETGEMS = 0x557544D0, 0x5577827C, 0x55751F38
LSTRCLR = 0x55701140
ILTER_VALID = 0x5570352C            # thunk -> ILTer.TILTerrainMO.ValidTerrainType (art exists)
BUYCOST, CANBUY = 0x557D5EC8, 0x557D5EF4

VMT_SLOTS = {   # name: (slot va, vanilla target)
    "rw":     (TOWER_VMT + 0x18, 0x557D59EC),
    "exec":   (TOWER_VMT + 0x168, 0x557D5D98),
    "newday": (TOWER_VMT + 0x174, 0x557D5CEC),
    "placed": (TOWER_VMT + 0x180, 0x557D5B34),
    "upd":    (TOWER_VMT + 0x1C4, 0x557D5ABC),
}
SITES = {   # name: (va, vanilla, function lo, hi)
    "buy":    (0x557D604C, bytes.fromhex("0fbef3897720"), 0x557D5FF0, 0x557D6080),
    "create": (0x557D59CB, bytes.fromhex("c646330284db"), 0x557D59A0, 0x557D59E4),
}


# ---- helpers ------------------------------------------------------------------------------------
def build_swap(va):
    """EAX = tower: exchange the two offers.  Every register kept."""
    return asm("""
        push edx
        mov  edx, dword ptr [eax + 0x34]
        xchg edx, dword ptr [eax + 0x38]
        mov  dword ptr [eax + 0x34], edx
        pop  edx
        ret
    """, va)


def build_hassph(va):
    """EAX = spell id, EDX = sphere -> AL = the spell is of that sphere (a dual one counts both)."""
    return pic(f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        xor  eax, eax
        test esi, esi
        je   s_out
        {{ANC}}
        mov  eax, dword ptr [ebx + {{HSSET}}]
        mov  eax, dword ptr [eax + 0x84]
        mov  edx, esi
        call {GETSPELL:#x}
        test eax, eax
        je   s_no
        movzx ecx, byte ptr [eax + 0x20]
        cmp  ecx, edi
        je   s_yes
        cmp  ecx, {DUAL_SPHERE}
        jne  s_no
        mov  edx, esi
        call {DUAL_FIND:#x}
        je   s_no
        movzx ecx, byte ptr [eax + 2]
        cmp  ecx, edi
        je   s_yes
        movzx ecx, byte ptr [eax + 3]
        cmp  ecx, edi
        je   s_yes
    s_no:
        xor  eax, eax
        jmp  s_out
    s_yes:
        mov  eax, 1
    s_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va, "ebx", {"HSSET": AOWHSSET})


def build_list(va):
    """EAX = tower, EDX = spell id to leave out, ECX = buffer of 256 dwords -> EAX = count.
    Frame: -4 exclude, -8 buffer, -0xC count, -0x10 level mask, -0x14 spell control,
    -0x18 tower, -0x1C sphere mask.  ESI = anchor, EDI = spell id, EBX = spell."""
    return pic(f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x1c
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp - 0x18], eax
        mov  dword ptr [ebp - 4], edx
        mov  dword ptr [ebp - 8], ecx
        mov  dword ptr [ebp - 0xc], 0
        movzx edx, word ptr [eax + 0x31]
        mov  dword ptr [ebp - 0x1c], edx
        movzx edx, byte ptr [eax + 0x3c]
        test edx, edx
        jne  l_lv
        movzx ecx, byte ptr [eax + 0x33]
        dec  ecx
        cmp  ecx, 7
        ja   l_lv
        mov  edx, 1
        shl  edx, cl
    l_lv:
        mov  dword ptr [ebp - 0x10], edx
        {{ANC}}
        mov  eax, dword ptr [esi + {{HSSET}}]
        mov  eax, dword ptr [eax + 0x84]
        mov  dword ptr [ebp - 0x14], eax
        call {GETCOUNT:#x}
        mov  edi, eax
    l_next:
        dec  edi
        js   l_done
        cmp  edi, dword ptr [ebp - 4]
        je   l_next
        mov  eax, dword ptr [ebp - 0x14]
        mov  edx, edi
        call {GETSPELL:#x}
        test eax, eax
        je   l_next
        mov  ebx, eax
        movzx eax, byte ptr [ebx + 0x20]
        movzx ecx, byte ptr [ebx + 0x21]
        cmp  eax, {DUAL_SPHERE}
        jne  l_plain
        mov  edx, edi
        call {DUAL_FIND:#x}
        je   l_next
        movzx edx, byte ptr [eax + 2]
        bt   dword ptr [ebp - 0x1c], edx
        jnc  l_next
        movzx edx, byte ptr [eax + 3]
        bt   dword ptr [ebp - 0x1c], edx
        jnc  l_next
        inc  ecx
        jmp  l_level
    l_plain:
        cmp  eax, 15
        ja   l_next
        bt   dword ptr [ebp - 0x1c], eax
        jnc  l_next
    l_level:
        dec  ecx
        cmp  ecx, 7
        ja   l_next
        bt   dword ptr [ebp - 0x10], ecx
        jnc  l_next
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x64]
        test al, al
        je   l_next
        cmp  edi, {WARP_ID}
        jne  l_add
        mov  eax, dword ptr [esi + {{MAP}}]
        cmp  byte ptr [eax + {WARP_FLAG:#x}], 0
        jne  l_next
    l_add:
        mov  ecx, dword ptr [ebp - 0xc]
        cmp  ecx, 0x100
        jae  l_next
        mov  eax, dword ptr [ebp - 8]
        mov  dword ptr [eax + ecx*4], edi
        inc  dword ptr [ebp - 0xc]
        jmp  l_next
    l_done:
        mov  eax, dword ptr [ebp - 0xc]
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    """, va, "esi", {"HSSET": AOWHSSET, "MAP": AOWHSMAP})


def build_roll(va, at):
    """EAX = tower, EDX = 0 (roll both offers) or 1 (roll the second, keeping the first).
    Frame: -0x400 the list, -0x404 mode, -0x408 count, -0x40C index of A."""
    return pic(f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x410
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  dword ptr [ebp - 0x404], edx
        {{ANC}}
        xor  edx, edx
        cmp  dword ptr [ebp - 0x404], 0
        je   r_ex
        mov  edx, dword ptr [ebx + 0x34]
    r_ex:
        lea  ecx, [ebp - 0x400]
        mov  eax, ebx
        call {at['list']:#x}
        mov  edi, eax
        cmp  dword ptr [ebp - 0x404], 0
        je   r_both
        xor  eax, eax
        test edi, edi
        je   r_setb
        mov  edx, edi
        mov  eax, dword ptr [esi + {{MAP}}]
        call {RANDOM:#x}
        mov  eax, dword ptr [ebp + eax*4 - 0x400]
    r_setb:
        mov  dword ptr [ebx + 0x38], eax
        jmp  r_out
    r_both:
        xor  eax, eax
        mov  dword ptr [ebx + 0x34], eax
        mov  dword ptr [ebx + 0x38], eax
        test edi, edi
        je   r_out
        mov  edx, edi
        mov  eax, dword ptr [esi + {{MAP}}]
        call {RANDOM:#x}
        mov  dword ptr [ebp - 0x40c], eax
        mov  eax, dword ptr [ebp + eax*4 - 0x400]
        mov  dword ptr [ebx + 0x34], eax
        cmp  edi, 2
        jb   r_out
        lea  edx, [edi - 1]
        mov  eax, dword ptr [esi + {{MAP}}]
        call {RANDOM:#x}
        cmp  eax, dword ptr [ebp - 0x40c]
        jl   r_b
        inc  eax
    r_b:
        mov  eax, dword ptr [ebp + eax*4 - 0x400]
        mov  dword ptr [ebx + 0x38], eax
    r_out:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    """, va, "esi", {"MAP": AOWHSMAP})


def build_terrain(va, at):
    """EAX = tower: move its hex to another of TERRAINS it has art for (Grass and Wasteland
    filtered by the offers).  Frame: -0x20 candidates (dwords), -0x24 count, -0x28 flags
    (bit 0 Death offer, bit 1 Life offer)."""
    tlist = ", ".join(str(t) for t in TERRAINS)
    loop = []
    for t in TERRAINS:
        loop.append(f"""
        mov  edx, {t}
        call t_try""")
    return pic(f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x28
        push ebx
        push esi
        push edi
        mov  ebx, eax
        {{ANC}}
        xor  edi, edi
        mov  eax, dword ptr [ebx + 0x34]
        mov  edx, {DEATH}
        call {at['hassph']:#x}
        or   edi, eax
        mov  eax, dword ptr [ebx + 0x38]
        mov  edx, {DEATH}
        call {at['hassph']:#x}
        or   edi, eax
        mov  eax, dword ptr [ebx + 0x34]
        mov  edx, {LIFE}
        call {at['hassph']:#x}
        add  eax, eax
        or   edi, eax
        mov  eax, dword ptr [ebx + 0x38]
        mov  edx, {LIFE}
        call {at['hassph']:#x}
        add  eax, eax
        or   edi, eax
        mov  dword ptr [ebp - 0x28], edi
        mov  dword ptr [ebp - 0x24], 0
        {''.join(loop)}
        mov  edx, dword ptr [ebp - 0x24]
        test edx, edx
        je   t_out
        mov  eax, dword ptr [esi + {{MAP}}]
        call {RANDOM:#x}
        mov  edi, dword ptr [ebp + eax*4 - 0x20]
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        push eax
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x7c]
        movsx eax, al
        push eax
        push 0
        push edi
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx ecx, al
        xor  edx, edx
        mov  eax, dword ptr [esi + {{MAP}}]
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0xd0]
    t_out:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    t_try:
        movzx eax, byte ptr [ebx + 0x18]
        cmp  eax, edx
        je   t_skip
        cmp  edx, {GRASS}
        jne  t_w
        test byte ptr [ebp - 0x28], 1
        jne  t_skip
    t_w:
        cmp  edx, {WASTELAND}
        jne  t_art
        test byte ptr [ebp - 0x28], 2
        jne  t_skip
    t_art:
        push edx
        mov  eax, ebx
        call {ILTER_VALID:#x}
        pop  edx
        test al, al
        je   t_skip
        mov  eax, dword ptr [ebp - 0x24]
        mov  dword ptr [ebp + eax*4 - 0x20], edx
        inc  dword ptr [ebp - 0x24]
    t_skip:
        ret
    """, va, "esi", {"MAP": AOWHSMAP})


def build_sched(va):
    """EAX = tower: next re-roll = today + d20."""
    return pic(f"""
        push ebx
        push esi
        mov  ebx, eax
        {{ANC}}
        mov  eax, dword ptr [esi + {{MAP}}]
        mov  edx, 20
        call {RANDOM:#x}
        mov  edx, dword ptr [esi + {{MAP}}]
        add  eax, dword ptr [edx + 0x174]
        inc  eax
        mov  word ptr [ebx + 0x3e], ax
        pop  esi
        pop  ebx
        ret
    """, va, "esi", {"MAP": AOWHSMAP})


def build_known(va):
    """EAX = spell id, EDX = player id -> AL = that player knows it (or the id is 0)."""
    return pic(f"""
        push ebx
        push esi
        mov  ebx, eax
        mov  al, 1
        test ebx, ebx
        je   k_out
        {{ANC}}
        mov  eax, dword ptr [esi + {{MAP}}]
        mov  eax, dword ptr [eax + 0x140]
        call {GETPLAYERS:#x}
        test eax, eax
        je   k_yes
        mov  eax, dword ptr [eax + 0x54]
        mov  eax, dword ptr [eax + 0x30]
        mov  edx, ebx
        call {INDEXOF:#x}
        inc  eax
        setne al
        jmp  k_out
    k_yes:
        mov  al, 1
    k_out:
        pop  esi
        pop  ebx
        ret
    """, va, "esi", {"MAP": AOWHSMAP})


def build_player(va):
    """EAX = player id -> EAX = the TPlayer (or 0)."""
    return pic(f"""
        push esi
        mov  edx, eax
        {{ANC}}
        mov  eax, dword ptr [esi + {{MAP}}]
        mov  eax, dword ptr [eax + 0x140]
        pop  esi
        jmp  {GETPLAYERS:#x}
    """, va, "esi", {"MAP": AOWHSMAP})


def build_valid(va, at):
    """EAX = spell id, EDX = player -> AL = an AI offer worth buying: unknown, AI weight > 0."""
    return pic(f"""
        push ebx
        push esi
        mov  ebx, eax
        xor  eax, eax
        test ebx, ebx
        je   v_out
        test dl, dl
        jle  v_no
        movsx edx, dl
        mov  eax, ebx
        call {at['known']:#x}
        test al, al
        jne  v_no
        {{ANC}}
        mov  eax, dword ptr [esi + {{HSSET}}]
        mov  eax, dword ptr [eax + 0x84]
        mov  edx, ebx
        call {GETSPELL:#x}
        test eax, eax
        je   v_no
        cmp  dword ptr [eax + 0x30], 0
        setg al
        jmp  v_out
    v_no:
        xor  eax, eax
    v_out:
        pop  esi
        pop  ebx
        ret
    """, va, "esi", {"HSSET": AOWHSSET})


def build_pick(va, at):
    """EAX = tower, EDX = player -> AL = the AI's slot: both valid -> the cheaper (A on a tie),
    else the valid one, else 0."""
    return asm(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        mov  eax, dword ptr [ebx + 0x34]
        mov  edx, esi
        call {at['valid']:#x}
        movzx edi, al
        mov  eax, dword ptr [ebx + 0x38]
        mov  edx, esi
        call {at['valid']:#x}
        test al, al
        je   p_a
        test edi, edi
        je   p_b
        mov  eax, ebx
        call {BUYCOST:#x}
        mov  edi, eax
        mov  eax, ebx
        call {at['swap']:#x}
        call {BUYCOST:#x}
        push eax
        mov  eax, ebx
        call {at['swap']:#x}
        pop  eax
        cmp  eax, edi
        jl   p_b
    p_a:
        xor  eax, eax
        jmp  p_out
    p_b:
        mov  eax, 1
    p_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


# ---- the methods --------------------------------------------------------------------------------
def build_rw(va):
    return asm(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        call {VMT_SLOTS['rw'][1]:#x}
        lea  edx, [ebx + 0x38]
        mov  ecx, {TAG_B:#x}
        mov  eax, esi
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0x2c]
        lea  edx, [ebx + 0x3c]
        mov  ecx, {TAG_PACK:#x}
        mov  eax, esi
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0x2c]
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


def build_newday(va, at):
    return pic(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        {{ANC}}
        cmp  byte ptr [ebx + 0x30], 0
        jne  n_random
        cmp  dword ptr [ebx + 0x34], 0
        je   n_random
        mov  dword ptr [ebx + 0x38], 0
        jmp  n_out
    n_random:
        mov  eax, dword ptr [esi + {{MAP}}]
        mov  edi, dword ptr [eax + 0x174]
        cmp  byte ptr [ebx + 0x3d], 0
        jne  n_state
        mov  byte ptr [ebx + 0x3d], 1
        cmp  edi, 1
        jle  n_first
        cmp  dword ptr [ebx + 0x34], 0
        je   n_first
        mov  eax, ebx
        mov  edx, 1
        call {at['roll']:#x}
        lea  eax, [edi + 1]
        mov  word ptr [ebx + 0x3e], ax
        jmp  n_out
    n_first:
        mov  eax, ebx
        xor  edx, edx
        call {at['roll']:#x}
        mov  eax, ebx
        call {at['sched']:#x}
        jmp  n_out
    n_state:
        movzx eax, word ptr [ebx + 0x3e]
        cmp  edi, eax
        jl   n_out
        mov  eax, ebx
        xor  edx, edx
        call {at['roll']:#x}
        mov  eax, ebx
        call {at['terrain']:#x}
        mov  eax, ebx
        call {at['sched']:#x}
    n_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va, "esi", {"MAP": AOWHSMAP})


def build_exec(va, at):
    """ExecuteTE(EAX tower, EDX TE) -> AL.  [esp] = mode (0 plain, 1 swapped, 2 A blanked),
    [esp+4] = the saved A."""
    return asm(f"""
        push ebx
        push esi
        push edi
        sub  esp, 8
        mov  ebx, eax
        mov  esi, edx
        mov  dword ptr [esp], 0
        mov  edi, dword ptr [esi + 0x24]
        test edi, edi
        je   x_go
        cmp  edi, dword ptr [ebx + 0x34]
        je   x_go
        cmp  edi, dword ptr [ebx + 0x38]
        jne  x_block
        mov  eax, ebx
        call {at['swap']:#x}
        mov  dword ptr [esp], 1
        jmp  x_go
    x_block:
        mov  eax, dword ptr [ebx + 0x34]
        mov  dword ptr [esp + 4], eax
        mov  dword ptr [ebx + 0x34], 0
        mov  dword ptr [esp], 2
    x_go:
        mov  eax, ebx
        mov  edx, esi
        call {VMT_SLOTS['exec'][1]:#x}
        mov  edx, dword ptr [esp]
        cmp  edx, 1
        jne  x_nb
        push eax
        mov  eax, ebx
        call {at['swap']:#x}
        pop  eax
        jmp  x_out
    x_nb:
        cmp  edx, 2
        jne  x_out
        mov  edx, dword ptr [esp + 4]
        mov  dword ptr [ebx + 0x34], edx
    x_out:
        add  esp, 8
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


def build_buy(va):
    """Called from Buy: ESI = tower (the exe has swapped the chosen offer into +0x34), EDI = TE."""
    return asm("""
        mov  eax, dword ptr [esi + 0x34]
        mov  dword ptr [edi + 0x24], eax
        movsx esi, bl
        mov  dword ptr [edi + 0x20], esi
        ret
    """, va)


def build_upd(va, at):
    """UpdateAITarget(EAX tower, EDX request (player at [+0]), ECX result)."""
    return asm(f"""
        push ebx
        push esi
        push edi
        push ebp
        mov  ebx, eax
        mov  esi, edx
        mov  edi, ecx
        movsx edx, byte ptr [esi]
        mov  eax, ebx
        call {at['pick']:#x}
        movzx ebp, al
        test ebp, ebp
        je   u_go
        mov  eax, ebx
        call {at['swap']:#x}
    u_go:
        mov  eax, ebx
        mov  edx, esi
        mov  ecx, edi
        call {VMT_SLOTS['upd'][1]:#x}
        test ebp, ebp
        je   u_out
        mov  eax, ebx
        call {at['swap']:#x}
    u_out:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


def build_placed(va, at):
    """ArmyPlaced(EAX tower, EDX army HS).  Frame: -4 player, -8 slot, -0xC its spell,
    -0x10 known before, -0x14 the error string."""
    return asm(f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x14
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        mov  dword ptr [ebp - 0x14], 0
        mov  eax, dword ptr [esi + 0x1c]
        movsx edi, byte ptr [eax + 0x12]
        mov  dword ptr [ebp - 4], edi
        mov  edx, edi
        mov  eax, ebx
        call {at['pick']:#x}
        movzx eax, al
        mov  dword ptr [ebp - 8], eax
        mov  eax, dword ptr [ebx + eax*4 + 0x34]
        mov  dword ptr [ebp - 0xc], eax
        mov  edx, edi
        call {at['known']:#x}
        movzx eax, al
        mov  dword ptr [ebp - 0x10], eax
        cmp  dword ptr [ebp - 8], 0
        je   a_go
        mov  eax, ebx
        call {at['swap']:#x}
    a_go:
        mov  eax, ebx
        mov  edx, esi
        call {VMT_SLOTS['placed'][1]:#x}
        cmp  dword ptr [ebp - 8], 0
        je   a_after
        mov  eax, ebx
        call {at['swap']:#x}
    a_after:
        cmp  dword ptr [ebp - 0x10], 0
        jne  a_out
        cmp  dword ptr [ebp - 0xc], 0
        je   a_out
        mov  eax, dword ptr [ebp - 0xc]
        mov  edx, edi
        call {at['known']:#x}
        test al, al
        je   a_out
        mov  eax, dword ptr [ebp - 8]
        xor  eax, 1
        mov  eax, dword ptr [ebx + eax*4 + 0x34]
        mov  edx, edi
        call {at['valid']:#x}
        test al, al
        je   a_out
        cmp  dword ptr [ebp - 8], 0
        jne  a_buy
        mov  eax, ebx
        call {at['swap']:#x}
    a_buy:
        lea  ecx, [ebp - 0x14]
        mov  edx, edi
        mov  eax, ebx
        call {CANBUY:#x}
        test al, al
        je   a_back
        mov  eax, ebx
        call {BUYCOST:#x}
        push eax
        mov  eax, dword ptr [ebp - 4]
        call {at['player']:#x}
        pop  ecx
        mov  edx, dword ptr [eax + 0xc4]
        sub  edx, ecx
        push eax
        call {SETGEMS:#x}
        pop  eax
        mov  eax, dword ptr [eax + 0x54]
        mov  eax, dword ptr [eax + 0x30]
        mov  edx, dword ptr [ebx + 0x34]
        call {ILIST_ADD:#x}
    a_back:
        cmp  dword ptr [ebp - 8], 0
        jne  a_out
        mov  eax, ebx
        call {at['swap']:#x}
    a_out:
        lea  eax, [ebp - 0x14]
        call {LSTRCLR:#x}
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    """, va)


def build_create(va):
    """Called from TWizardsTower.Create (ESI = tower, BL = its alloc flag).  A random sphere set
    for a new tower: each of Cosmos..Water (bits 0-6) at 1/2 from rdtsc, at least one, never Life
    (bit 1) with Death (bit 2).  Ends with Create's own `test bl,bl`."""
    return asm("""
        mov  byte ptr [esi + 0x33], 2
        push eax
        push ecx
        push edx
        rdtsc
        mov  ecx, eax
        shr  eax, 3
        and  eax, 0x7f
        jne  c_some
        mov  eax, 0x10
    c_some:
        mov  edx, eax
        and  edx, 6
        cmp  edx, 6
        jne  c_set
        test ecx, 0x400
        je   c_dropd
        and  eax, 0xfd
        jmp  c_set
    c_dropd:
        and  eax, 0xfb
    c_set:
        mov  word ptr [esi + 0x31], ax
        pop  edx
        pop  ecx
        pop  eax
        test bl, bl
        ret
    """, va)


# ---- layout -------------------------------------------------------------------------------------
def layout():
    caves, at, va = [], {}, SLOT[0]

    def put(n, b):
        nonlocal va
        caves.append(("cave_" + n, va, b))
        at[n] = va
        va = (va + len(b) + 0xF) & ~0xF

    put("swap", build_swap(va))
    put("hassph", build_hassph(va))
    put("list", build_list(va))
    put("roll", build_roll(va, at))
    put("terrain", build_terrain(va, at))
    put("sched", build_sched(va))
    put("known", build_known(va))
    put("player", build_player(va))
    put("valid", build_valid(va, at))
    put("pick", build_pick(va, at))
    put("rw", build_rw(va))
    put("newday", build_newday(va, at))
    put("exec", build_exec(va, at))
    put("buy", build_buy(va))
    put("upd", build_upd(va, at))
    put("placed", build_placed(va, at))
    put("create", build_create(va))
    return at, caves


def checks():
    d = open(P.TARGET, "rb").read()
    rd = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    rb = lambda va, n: d[P.va2off(d, va):P.va2off(d, va) + n]
    if rd(TOWER_VMT - 0x40) != TOWER_VMT:
        sys.exit("ABORT: %08X is not TWizardsTower's VMT" % TOWER_VMT)
    if rb(DUAL_FIND, 2) != b"\x51\xe8":
        sys.exit("ABORT: build_dual_sphere.py's dual_find is not at %08X" % DUAL_FIND)
    for va, want, what in (
            (0x557D6045, bytes.fromhex("c7471801000000"), "Buy's `mov [edi+0x18],1` (EDI = TE)"),
            (0x55761D20, bytes.fromhex("8d5324b917000000"), "TStructureTE.ReadWrite streams +0x24 as id 0x17"),
            (0x557D5EE2, bytes.fromhex("e82a630300"), "BuyCost's call of the price cave 0x5580C211")):
        if rb(va, len(want)) != want:
            sys.exit("ABORT: %s is not at %08X" % (what, va))


AT, CAVES = layout()
call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
HOOKS = [(INST_VA, struct.pack("<I", INST_OLD), struct.pack("<I", INST_NEW))]
for name, (va, orig) in VMT_SLOTS.items():
    HOOKS.append((va, struct.pack("<I", orig), struct.pack("<I", AT[name])))
for name, (va, van, _lo, _hi) in SITES.items():
    HOOKS.append((va, van, call_to(va, AT[name]) + b"\x90" * (len(van) - 5)))
INTERIOR = [(va, va + len(van), lo, hi) for _n, (va, van, lo, hi) in SITES.items()]
RELOC_OK = tuple(va for va, _o in VMT_SLOTS.values())
assert max(va + len(b) for _n, va, b in CAVES) <= SLOT[1]

if __name__ == "__main__":
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in AT.items()))
    print("  slot used: %d of %d B" % (max(va + len(b) for _n, va, b in CAVES) - SLOT[0], SLOT[1] - SLOT[0]))
    checks()
    run("build_wizardtower_dual", HOOKS, CAVES, SLOT, INTERIOR, sys.argv[1:], reloc_ok=RELOC_OK)
