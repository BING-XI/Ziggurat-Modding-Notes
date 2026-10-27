#!/usr/bin/env python
r"""
build_surtrs_chasm.py -- Surtr's Chasm, the Earth/Fire dual tier-2 world-map spell.  AoWEPACK.dpl.
Owner's design 2026-10-25 (05-spells-added.md, "Earth/Fire -- agreed design"): 35 mana, no upkeep,
range 12, Ritualist, permanent.  It opens a jagged line of up to 6 Chasm hexes from the cast hex:
each new hex grows from the last, picked at random among the valid neighbours that touch no other
hex of this cast; the line stops early when none is left.  A valid hex is land with no unit or
structure -- forests, hills and roads are swallowed, lava counts; water, ice, Earth, Rock, Sky,
Chasm, mountains and the border are not.  Beneath each new chasm hex Rock becomes Earth.  Never on
the Firmament; on the lowest level the chasm is a bottomless pit.  The AI never casts it (the
TGlobalTargetSpell family has no AI).  Climbing its edges is build_chasm_climb.py.

THE SPELL (id 83) -- a TLevelTerrain INSTANCE (classref cell 0x5579D2B8, Create 0x5579F1D0),
  registered at 0x557A246A (Level Terrain's own `call RegisterSpell` in RegisterGlobalTargetSpells,
  replayed first).  Name "Surtr's Chasm", id 83, mana 35, research 160 (the single tier-3 figure:
  it prices Wizard's Tower offers), upkeep 0, sphere 7 (dual: build_dual_sphere.py's TABLE holds
  Earth+Fire), tier 2.  Range 12 is the family's (TGlobalTargetSpell.SetupTargetSelection).
  Spells.pfs record 93: build_surtrs_chasm_pfs.py.

SITES (all call retargets but one)
  reg   0x557A246A  call RegisterSpell -> cave_reg
  vt    0x5579F27E  TLevelTerrain.ValidTargetMapF's call of the base (which returns 1) -> cave_vt:
        id 83 -> not the Firmament (level 3), terrain in {1-5, 9, 0xC}, no mountain (overlay 0);
        Level Terrain's own tests (no structure, no army) follow.  Other ids: 1, as the base.
  vts   0x5579F2D2  ValidTargetSelectionMapF's call of the base -> cave_vts: the base (explored),
        then cave_vt's test for id 83 -- the cursor's two gates move together.
  rad   0x5579F343  SetupTargetSelection's `mov eax,2` (RadToHN(2): Level Terrain's 7 hexes) ->
        call cave_rad: 1 for id 83 (the cursor marks the cast hex only).
  exec  0x5579F18E  TLevelTerrainTE.Process's call of the worker 0x5579F068 -> cave_exec: id 83
        -> plans the chasm; others -> the worker (build_levelterrain_rocks.py hooks inside it).
  Spell 85 (Awaken Volcano, also a TLevelTerrain instance): cave_vt and cave_vts jump to its
        target test VOLC_VT, cave_rad gives it the one-hex cursor, cave_exec jumps to VOLC_EXEC
        (build_awaken_volcano.py's pinned entries; untaken while that script is undone, as
        spell 85 is then never registered).
  Spells 93 and 94 (Imbue Altar, Imbue Spring; 2026-10-26) the same way to IMB_VT / IMB_EXEC
        (build_imbue.py's pinned entries), with the one-hex cursor.
  TLevelTerrainTE's VMT (0x5579D218): slot +0x4C, TSpellTE.Execute 0x55779948 -> cave_execute
        (.reloc kept: the new value is in the image), and the instance size 0x24 -> 0x40, which
        gives every Level Terrain event 0x1C bytes for the plan (TE_PHASE .. TE_LINE).

THE CHASM opens one hex every FRAMES map frames, 0.4 s at the game's 30 (owner 2026-10-25).
  cave_exec (inside Process, after PlayDefaultEffects has placed the effect and played the sound)
  plans the whole line and stores it in the event: TE_LINE (x | y << 8 words), TE_COUNT, TE_NEXT,
  TE_FRAME (the map's frame counter, [map+0x40], which THSMap.NewFrame advances and wraps past
  0xFFFFF) and TE_PHASE = 1.  cave_execute wraps the event's Execute: on the first call it runs
  TSpellTE.Execute (validation, Process, the mana); when that reports done (1) with a plan, the
  event stays running by returning 0 -- the token manager calls Execute again until it reports
  done, as TMoveArmyTE does while an army walks.  Each call opens every hex whose frame has come
  (the cast hex at once), and after the last one drains the water and reports done (1); TE_PHASE
  2 thereafter.  Planning first and opening later draws the same line: each pick already excludes
  the earlier hexes and every hex touching one, so no pick ever read a hex this cast had changed.
  Per hex: a road (overlay 4/5) is freed as Flood frees it (FindOwnedHS(TAbstractRoad) -> its
  destructor), THSMap.ClearTerrain frees every terrain object (thunk 0x557025DC), then the map's
  ChangeTerrain (VMT +0xD0) writes Chasm 0x0B; on the level beneath (the flight chain, disabled
  levels skipped) a Rock (8) hex becomes Earth (7) the same way.  Neighbours follow the engine's
  odd-column layout (HXtoHP: odd columns sit half a hex lower).  A candidate's validity is
  TLevelTerrain.ValidTargetMapF itself, i.e. cave_vt plus Level Terrain's tests; both refuse
  Water by the field's terrain byte, so no chasm hex is ever placed on water.
  THE DRAIN (owner 2026-10-25, after the first cast): when the line is done, every Water (0) or
  underground Water (0x0A) hex next to one of its hexes becomes Dirt (0x0C), cleared and changed
  as the chasm hexes are.  A water hex keeps its water if it holds an army (0x55771EB0, Level
  Terrain's own test), a structure (0x55702004 with the structure class, likewise) or a bridge
  (overlay 5): a ship there is stranded in a one-hex pool rather than put on land, which
  TArmyHS.CanChangeTerrain would veto anyway.

RNG: P1 SYNCED DRAW, host TLevelTerrainTE.Process (a token event): the pick
  TAoWHSMap.Random(map, count) in cave_exec (rng_audit --owners: ok); ChangeTerrain, called from
  the event's Execute, reseeds RandSeed from the synced generator itself.  Every peer plans the
  same line in Process and opens the same hexes in the same order; only the pacing is local, and
  the event holds the token queue until it is done.

Slot 0x558B9800-0x558BA7FF, exclusive.  PIC.  Surgical --undo.

Unproven: road graphics on hexes next to a freed road; items lying on a swallowed hex stay there.

    python build_scripts/build_surtrs_chasm.py            dry run + state
    python build_scripts/build_surtrs_chasm.py --apply
    python build_scripts/build_surtrs_chasm.py --undo
    python build_scripts/build_surtrs_chasm.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic, ansistr

SPELL_ID, SPELL_NAME = 83, "Surtr's Chasm"
VOLC_ID, VOLC_VT, VOLC_EXEC = 85, 0x558BB000, 0x558BB005   # build_awaken_volcano.py's pinned entries
IMB_IDS, IMB_VT, IMB_EXEC = (93, 94), 0x558C3000, 0x558C3005   # build_imbue.py's pinned entries
MANA, RESEARCH, UPKEEP, SPHERE, TIER = 35, 160, 0, 7, 2
SLOT = (0x558B9800, 0x558BA800)

AOWHSMAP, AOWHSSET = 0x558FA040, 0x558FA044
LT_CELL = 0x5579D2B8             # -> GlobalTargetSpells..TLevelTerrain
LT_CREATE = 0x5579F1D0
LT_VT = 0x5579F274               # TLevelTerrain.ValidTargetMapF(eax=spell, edx=field) -> al
LT_WORKER = 0x5579F068
BASE_VT, BASE_VTS = 0x5579E4A8, 0x5579E4AC
REGISTER_SPELL, LSTRASG = 0x55779B40, 0x55701150
GETSPELL = 0x55779AC8            # TSpellControl.GetSpell(eax=[set+0x84], edx=id)
GETFIELD = 0x557020FC
CLEARTERRAIN = 0x557025DC        # (eax=map, edx=x, ecx=y; push level, 0, -1)
FINDOWNEDHS = 0x55701FFC         # TMapField.FindOwnedHS(eax=field, edx=class)
ROAD_IAT = 0x558FC0F0            # IAT -> HSEngine..TAbstractRoad
MAP_RANDOM = 0x5577827C
CHASM, EARTH, ROCK, FIRMAMENT = 0x0B, 7, 8, 3
CAVE_WATER, DIRT, BRIDGE = 0x0A, 0x0C, 5
ARMY_ON = 0x55771EB0             # the army on a field, or nil (Level Terrain's own test)
HAS_HS, STRUCT_CELL = 0x55702004, 0x55713BD8   # field holds an HS of the class (a structure)
LT_TE_VMT = 0x5579D218                           # TLevelTerrainTE
TE_EXECUTE_SLOT, TE_INSTSIZE = LT_TE_VMT + 0x4C, LT_TE_VMT - 0x1C
SPELLTE_EXECUTE = 0x55779948                     # TSpellTE.Execute, the slot's vanilla value
TE_SIZE_VAN, TE_SIZE = 0x24, 0x40
TE_PHASE, TE_COUNT, TE_NEXT, TE_FRAME, TE_LINE = 0x24, 0x25, 0x26, 0x28, 0x2C   # TE_LINE: 6 words
MAP_FRAME, FRAME_WRAP = 0x40, 0x100000           # THSMap.NewFrame's counter, which wraps past 0xFFFFF
FRAMES = 12                                      # per hex: 0.4 s at the game's 30 frames a second
LAND = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5) | (1 << 9) | (1 << 0xC)
MASK_OFF, NO = 0x41C, 0xFF
UP_T = bytes([3, 0, 1, NO, 2])
DN_T = bytes([1, 2, 4, 0, NO])
# neighbour deltas, index parity*6 + dir: N, S, NW, SW, NE, SE (odd columns sit lower)
NB_DX = bytes(b & 0xFF for b in [0, 0, -1, -1, 1, 1] * 2)
NB_DY = bytes(b & 0xFF for b in [-1, 1, -1, 0, -1, 0] + [-1, 1, 0, 1, 0, 1])

SITES = {"reg": (0x557A246A, REGISTER_SPELL, 0x557A23A4, 0x557A24FE),
         "vt": (0x5579F27E, BASE_VT, 0x5579F274, 0x5579F2C8),
         "vts": (0x5579F2D2, BASE_VTS, 0x5579F2C8, 0x5579F330),
         "exec": (0x5579F18E, LT_WORKER, 0x5579F16C, 0x5579F1CE)}
RAD_HOOK, RAD_VAN = 0x5579F343, bytes.fromhex("b802000000")


def build_reg(va):
    src = f"""
        call {REGISTER_SPELL:#x}
        {{ANC}}
        push ecx
        mov  eax, dword ptr [ecx + {{CELL}}]
        xor  ecx, ecx
        mov  dl, 1
        call {LT_CREATE:#x}
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
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER_SPELL:#x}
        ret
    """
    return pic(src, va, "ecx", {"CELL": LT_CELL, "NAME": ("TAIL", 8)}, ansistr(SPELL_NAME))


def build_vt(va):
    """eax = spell, edx = field -> al.  Register-only."""
    return asm(f"""
        cmp  dword ptr [eax + 0x10], {VOLC_ID}
        je   {VOLC_VT:#x}
        cmp  dword ptr [eax + 0x10], {IMB_IDS[0]}
        je   {IMB_VT:#x}
        cmp  dword ptr [eax + 0x10], {IMB_IDS[1]}
        je   {IMB_VT:#x}
        cmp  dword ptr [eax + 0x10], {SPELL_ID}
        je   v_ours
        mov  al, 1
        ret
    v_ours:
        cmp  byte ptr [edx + 0x12], {FIRMAMENT}
        je   v_no
        movzx ecx, byte ptr [edx + 0x14]
        cmp  ecx, 15
        ja   v_no
        mov  eax, {LAND:#x}
        bt   eax, ecx
        jae  v_no
        cmp  byte ptr [edx + 0x15], 0
        je   v_no
        mov  al, 1
        ret
    v_no:
        xor  eax, eax
        ret
    """, va)


def build_vts(va, vt):
    return asm(f"""
        push eax
        push edx
        call {BASE_VTS:#x}
        pop  edx
        pop  ecx
        test al, al
        je   s_ret
        mov  eax, ecx
        cmp  dword ptr [ecx + 0x10], {VOLC_ID}
        je   {VOLC_VT:#x}
        cmp  dword ptr [ecx + 0x10], {IMB_IDS[0]}
        je   {IMB_VT:#x}
        cmp  dword ptr [ecx + 0x10], {IMB_IDS[1]}
        je   {IMB_VT:#x}
        cmp  dword ptr [ecx + 0x10], {SPELL_ID}
        je   {vt:#x}
        mov  al, 1
    s_ret:
        ret
    """, va)


def build_rad(va):
    """In SetupTargetSelection: ESI = the selection control, [esi+0x14] = the spell."""
    return asm(f"""
        mov  eax, dword ptr [esi + 0x14]
        cmp  dword ptr [eax + 0x10], {SPELL_ID}
        je   r_one
        cmp  dword ptr [eax + 0x10], {VOLC_ID}
        je   r_one
        cmp  dword ptr [eax + 0x10], {IMB_IDS[0]}
        je   r_one
        cmp  dword ptr [eax + 0x10], {IMB_IDS[1]}
        je   r_one
        mov  eax, 2
        ret
    r_one:
        mov  eax, 1
        ret
    """, va)


def build_exec(va):
    """eax = the TLevelTerrainTE.  Plans the line and stores it in the TE (TE_LINE, TE_COUNT,
    TE_FRAME, TE_PHASE = 1); cave_execute opens it.  Frame (ebp): +4 n, +8/+0xC current x/y,
    +0x10 candidates, +0x14 dir, +0x18/+0x1C neighbour x/y, +0x20 i, +0x30 line[6],
    +0x48 cand[6] (x | y << 8).  ebx anchor, esi TE, edi the spell."""
    src = f"""
        cmp  dword ptr [eax + 0x10], {VOLC_ID}
        je   {VOLC_EXEC:#x}
        cmp  dword ptr [eax + 0x10], {IMB_IDS[0]}
        je   {IMB_EXEC:#x}
        cmp  dword ptr [eax + 0x10], {IMB_IDS[1]}
        je   {IMB_EXEC:#x}
        cmp  dword ptr [eax + 0x10], {SPELL_ID}
        jne  {LT_WORKER:#x}
        push ebp
        push ebx
        push esi
        push edi
        sub  esp, 0x60
        mov  ebp, esp
        mov  esi, eax
        mov  dword ptr [ebp + 4], 0
        {{ANC}}
        mov  eax, dword ptr [ebx + {{SET}}]
        mov  eax, dword ptr [eax + 0x84]
        mov  edx, {SPELL_ID}
        call {GETSPELL:#x}
        mov  edi, eax
        test edi, edi
        je   c_end
        movsx eax, byte ptr [esi + 0x20]
        mov  dword ptr [ebp + 8], eax
        movsx edx, byte ptr [esi + 0x21]
        mov  dword ptr [ebp + 0xc], edx
        call c_valid
        test al, al
        je   c_end
        mov  eax, dword ptr [ebp + 0xc]
        shl  eax, 8
        or   eax, dword ptr [ebp + 8]
        mov  dword ptr [ebp + 0x30], eax
        mov  dword ptr [ebp + 4], 1
    c_grow:
        cmp  dword ptr [ebp + 4], 6
        jge  c_end
        mov  dword ptr [ebp + 0x10], 0
        mov  dword ptr [ebp + 0x14], 0
    c_dir:
        mov  eax, dword ptr [ebp + 8]
        mov  edx, dword ptr [ebp + 0xc]
        mov  ecx, dword ptr [ebp + 0x14]
        call c_nb
        mov  dword ptr [ebp + 0x18], eax
        mov  dword ptr [ebp + 0x1c], edx
        mov  dword ptr [ebp + 0x20], 0
    c_chk:
        mov  ecx, dword ptr [ebp + 0x20]
        mov  eax, dword ptr [ebp + 4]
        dec  eax
        cmp  ecx, eax
        jge  c_ok
        mov  eax, dword ptr [ebp + ecx*4 + 0x30]
        movzx edx, ah
        movzx eax, al
        push edx
        push eax
        mov  eax, dword ptr [ebp + 0x18]
        mov  edx, dword ptr [ebp + 0x1c]
        call c_touch
        add  esp, 8
        test al, al
        jne  c_skip
        inc  dword ptr [ebp + 0x20]
        jmp  c_chk
    c_ok:
        mov  eax, dword ptr [ebp + 0x18]
        mov  edx, dword ptr [ebp + 0x1c]
        call c_valid
        test al, al
        je   c_skip
        mov  ecx, dword ptr [ebp + 0x10]
        mov  eax, dword ptr [ebp + 0x1c]
        shl  eax, 8
        or   eax, dword ptr [ebp + 0x18]
        mov  dword ptr [ebp + ecx*4 + 0x48], eax
        inc  dword ptr [ebp + 0x10]
    c_skip:
        inc  dword ptr [ebp + 0x14]
        cmp  dword ptr [ebp + 0x14], 6
        jl   c_dir
        mov  edx, dword ptr [ebp + 0x10]
        test edx, edx
        je   c_end
        mov  eax, dword ptr [ebx + {{MAP}}]
        call {MAP_RANDOM:#x}
        mov  eax, dword ptr [ebp + eax*4 + 0x48]
        movzx edx, ah
        movzx eax, al
        mov  dword ptr [ebp + 8], eax
        mov  dword ptr [ebp + 0xc], edx
        mov  ecx, dword ptr [ebp + 4]
        mov  eax, dword ptr [ebp + 0xc]
        shl  eax, 8
        or   eax, dword ptr [ebp + 8]
        mov  dword ptr [ebp + ecx*4 + 0x30], eax
        inc  dword ptr [ebp + 4]
        jmp  c_grow
    c_end:
        mov  ecx, dword ptr [ebp + 4]
        mov  byte ptr [esi + {TE_COUNT:#x}], cl
        mov  byte ptr [esi + {TE_NEXT:#x}], 0
        test ecx, ecx
        je   c_out
    c_copy:
        dec  ecx
        mov  eax, dword ptr [ebp + ecx*4 + 0x30]
        mov  word ptr [esi + ecx*2 + {TE_LINE:#x}], ax
        test ecx, ecx
        jne  c_copy
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + {MAP_FRAME:#x}]
        mov  dword ptr [esi + {TE_FRAME:#x}], eax
        mov  byte ptr [esi + {TE_PHASE:#x}], 1
    c_out:
        add  esp, 0x60
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret

    c_valid:
        movsx ecx, byte ptr [esi + 0x22]
        push ecx
        mov  ecx, edx
        mov  edx, eax
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x10]
        call {GETFIELD:#x}
        test eax, eax
        je   cv_no
        mov  edx, eax
        mov  eax, edi
        call {LT_VT:#x}
        ret
    cv_no:
        xor  eax, eax
        ret

    c_nb:
        push esi
        mov  esi, eax
        and  esi, 1
        imul esi, esi, 6
        add  esi, ecx
        movsx ecx, byte ptr [ebx + esi + {{NBDX}}]
        add  eax, ecx
        movsx ecx, byte ptr [ebx + esi + {{NBDY}}]
        add  edx, ecx
        pop  esi
        ret

    c_touch:
        mov  ecx, eax
        sub  ecx, dword ptr [esp + 4]
        sub  edx, dword ptr [esp + 8]
        test ecx, ecx
        jne  t_side
        inc  edx
        cmp  edx, 2
        setbe al
        ret
    t_side:
        inc  ecx
        cmp  ecx, 2
        ja   t_no
        mov  ecx, dword ptr [esp + 4]
        and  ecx, 1
        sub  edx, ecx
        inc  edx
        cmp  edx, 1
        setbe al
        ret
    t_no:
        xor  eax, eax
        ret
    """
    tail = NB_DX + NB_DY
    return pic(src, va, "ebx", {"MAP": AOWHSMAP, "SET": AOWHSSET,
                                "NBDX": ("TAIL", 0), "NBDY": ("TAIL", 12)}, tail)


def build_execute(va):
    """TLevelTerrainTE's Execute (VMT +0x4C) for every Level Terrain event.  Spell 83: the first
    call runs TSpellTE.Execute (validate, Process: effects, sound, cave_exec's plan, mana); when it
    reports done with a planned line, the event stays running (returns 0) and each later call
    opens every hex whose time has come (FRAMES map frames apart, from TE_FRAME), then drains the
    water and reports done (1).  ebx anchor, esi the TE."""
    src = f"""
        cmp  dword ptr [eax + 0x10], {SPELL_ID}
        jne  {SPELLTE_EXECUTE:#x}
        cmp  byte ptr [eax + {TE_PHASE:#x}], 1
        je   x_step
        cmp  byte ptr [eax + {TE_PHASE:#x}], 2
        je   x_done
        push eax
        call {SPELLTE_EXECUTE:#x}
        pop  ecx
        cmp  al, 1
        jne  x_ret
        cmp  byte ptr [ecx + {TE_PHASE:#x}], 1
        jne  x_ret
        mov  eax, ecx
        jmp  x_step
    x_done:
        mov  al, 1
    x_ret:
        ret
    x_step:
        push ebx
        push esi
        push edi
        mov  esi, eax
        {{ANC}}
    s_loop:
        movzx edi, byte ptr [esi + {TE_NEXT:#x}]
        movzx eax, byte ptr [esi + {TE_COUNT:#x}]
        cmp  edi, eax
        jge  s_finish
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + {MAP_FRAME:#x}]
        sub  eax, dword ptr [esi + {TE_FRAME:#x}]
        and  eax, {FRAME_WRAP - 1:#x}
        imul edx, edi, {FRAMES}
        cmp  eax, edx
        jb   s_wait
        movzx eax, byte ptr [esi + edi*2 + {TE_LINE:#x}]
        movzx edx, byte ptr [esi + edi*2 + {TE_LINE + 1:#x}]
        call o_open
        inc  byte ptr [esi + {TE_NEXT:#x}]
        jmp  s_loop
    s_wait:
        xor  eax, eax
        jmp  s_out
    s_finish:
        call o_drain
        mov  byte ptr [esi + {TE_PHASE:#x}], 2
        mov  al, 1
    s_out:
        pop  edi
        pop  esi
        pop  ebx
        ret

    o_open:
        push ebp
        sub  esp, 0x10
        mov  ebp, esp
        mov  dword ptr [ebp], eax
        mov  dword ptr [ebp + 4], edx
        movsx eax, byte ptr [esi + 0x22]
        mov  dl, 1
        call c_next
        mov  dword ptr [ebp + 8], eax
        movsx ecx, byte ptr [esi + 0x22]
        push ecx
        mov  ecx, dword ptr [ebp + 4]
        mov  edx, dword ptr [ebp]
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x10]
        call {GETFIELD:#x}
        test eax, eax
        je   o_out
        mov  cl, byte ptr [eax + 0x15]
        sub  cl, 4
        cmp  cl, 2
        jae  o_clear
        mov  edx, dword ptr [ebx + {{ROAD}}]
        call {FINDOWNEDHS:#x}
        test eax, eax
        je   o_clear
        mov  dl, 1
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx - 4]
    o_clear:
        movsx eax, byte ptr [esi + 0x22]
        push eax
        push 0
        push -1
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  ecx, dword ptr [ebp + 4]
        mov  edx, dword ptr [ebp]
        call {CLEARTERRAIN:#x}
        push dword ptr [ebp + 4]
        movsx eax, byte ptr [esi + 0x22]
        push eax
        push 0
        push {CHASM}
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edi, dword ptr [eax]
        mov  ecx, dword ptr [ebp]
        xor  edx, edx
        call dword ptr [edi + 0xd0]
        mov  ecx, dword ptr [ebp + 8]
        test ecx, ecx
        js   o_out
        push ecx
        mov  ecx, dword ptr [ebp + 4]
        mov  edx, dword ptr [ebp]
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x10]
        call {GETFIELD:#x}
        test eax, eax
        je   o_out
        cmp  byte ptr [eax + 0x14], {ROCK}
        jne  o_out
        push dword ptr [ebp + 4]
        push dword ptr [ebp + 8]
        push 0
        push {EARTH}
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edi, dword ptr [eax]
        mov  ecx, dword ptr [ebp]
        xor  edx, edx
        call dword ptr [edi + 0xd0]
    o_out:
        add  esp, 0x10
        pop  ebp
        ret

    o_drain:
        push ebp
        sub  esp, 0x10
        mov  ebp, esp
        mov  dword ptr [ebp], 0
    d_hex:
        movzx eax, byte ptr [esi + {TE_COUNT:#x}]
        cmp  dword ptr [ebp], eax
        jge  d_ret
        mov  dword ptr [ebp + 4], 0
    d_dir:
        mov  ecx, dword ptr [ebp]
        movzx eax, byte ptr [esi + ecx*2 + {TE_LINE:#x}]
        movzx edx, byte ptr [esi + ecx*2 + {TE_LINE + 1:#x}]
        mov  ecx, dword ptr [ebp + 4]
        call c_nb
        mov  dword ptr [ebp + 8], eax
        mov  dword ptr [ebp + 0xc], edx
        movsx ecx, byte ptr [esi + 0x22]
        push ecx
        mov  ecx, edx
        mov  edx, eax
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x10]
        call {GETFIELD:#x}
        test eax, eax
        je   d_next
        mov  cl, byte ptr [eax + 0x14]
        test cl, cl
        je   d_water
        cmp  cl, {CAVE_WATER:#x}
        jne  d_next
    d_water:
        cmp  byte ptr [eax + 0x15], {BRIDGE}
        je   d_next
        push eax
        call {ARMY_ON:#x}
        test eax, eax
        pop  eax
        jne  d_next
        mov  edx, dword ptr [ebx + {{STRUCT}}]
        call {HAS_HS:#x}
        test eax, eax
        jne  d_next
        movsx eax, byte ptr [esi + 0x22]
        push eax
        push 0
        push -1
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  ecx, dword ptr [ebp + 0xc]
        mov  edx, dword ptr [ebp + 8]
        call {CLEARTERRAIN:#x}
        push dword ptr [ebp + 0xc]
        movsx eax, byte ptr [esi + 0x22]
        push eax
        push 0
        push {DIRT}
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edi, dword ptr [eax]
        mov  ecx, dword ptr [ebp + 8]
        xor  edx, edx
        call dword ptr [edi + 0xd0]
    d_next:
        inc  dword ptr [ebp + 4]
        cmp  dword ptr [ebp + 4], 6
        jl   d_dir
        inc  dword ptr [ebp]
        jmp  d_hex
    d_ret:
        add  esp, 0x10
        pop  ebp
        ret

    c_nb:
        push esi
        mov  esi, eax
        and  esi, 1
        imul esi, esi, 6
        add  esi, ecx
        movsx ecx, byte ptr [ebx + esi + {{NBDX}}]
        add  eax, ecx
        movsx ecx, byte ptr [ebx + esi + {{NBDY}}]
        add  edx, ecx
        pop  esi
        ret

    c_next:
        push ecx
        push esi
        mov  ecx, dword ptr [ebx + {{MAP}}]
    n_loop:
        cmp  eax, 4
        ja   n_no
        test dl, dl
        jne  n_dn
        movzx eax, byte ptr [ebx + eax + {{UPT}}]
        jmp  n_t
    n_dn:
        movzx eax, byte ptr [ebx + eax + {{DNT}}]
    n_t:
        cmp  eax, {NO:#x}
        je   n_no
        mov  esi, dword ptr [ecx + 0x10]
        cmp  eax, dword ptr [esi + 0x14]
        jge  n_no
        movzx esi, byte ptr [ecx + {MASK_OFF:#x}]
        bt   esi, eax
        jb   n_loop
        jmp  n_ret
    n_no:
        or   eax, -1
    n_ret:
        pop  esi
        pop  ecx
        ret
    """
    tail = UP_T + b"\0" * 3 + DN_T + b"\0" * 3 + NB_DX + NB_DY
    return pic(src, va, "ebx", {"MAP": AOWHSMAP, "ROAD": ROAD_IAT, "STRUCT": STRUCT_CELL,
                                "UPT": ("TAIL", 0), "DNT": ("TAIL", 8),
                                "NBDX": ("TAIL", 16), "NBDY": ("TAIL", 28)}, tail)


def layout():
    caves, at, va = [], {}, SLOT[0]

    def put(n, b):
        nonlocal va
        caves.append(("cave_" + n, va, b))
        at[n] = va
        va = (va + len(b) + 0xF) & ~0xF

    put("reg", build_reg(va))
    put("vt", build_vt(va))
    put("vts", build_vts(va, at["vt"]))
    put("rad", build_rad(va))
    put("exec", build_exec(va))
    put("execute", build_execute(va))
    return at, caves


def checks():
    d = open(P.TARGET, "rb").read()
    rd = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    v = rd(LT_CELL)
    if rd(v - 0x40) != v:
        sys.exit("ABORT: %08X does not hold a class" % LT_CELL)
    dual = d[P.va2off(d, 0x558B6000):P.va2off(d, 0x558B6000) + 0x100]
    if not any(struct.unpack_from("<HBB", dual, k) == (SPELL_ID, 3, 5) for k in range(0, 0xFC, 4)):
        print("  NOTE: build_dual_sphere.py's TABLE does not list spell %d as Earth/Fire yet" % SPELL_ID)
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:            # nobody else creates spell 83
        for i in range(ra, ra + rs - 7):
            src = P.IMAGE_BASE + sva + (i - ra)
            if SLOT[0] <= src < SLOT[1]:
                continue
            if d[i:i + 3] == b"\xc7\x40\x10" and struct.unpack_from("<I", d, i + 3)[0] == SPELL_ID:
                sys.exit("ABORT: %08X also stores spell id %d" % (src, SPELL_ID))


AT, CAVES = layout()
call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
HOOKS = [(va, call_to(va, orig), call_to(va, AT[n])) for n, (va, orig, _lo, _hi) in SITES.items()]
HOOKS.append((RAD_HOOK, RAD_VAN, call_to(RAD_HOOK, AT["rad"])))
HOOKS.append((TE_EXECUTE_SLOT, struct.pack("<I", SPELLTE_EXECUTE), struct.pack("<I", AT["execute"])))
HOOKS.append((TE_INSTSIZE, struct.pack("<I", TE_SIZE_VAN), struct.pack("<I", TE_SIZE)))
INTERIOR = [(va, va + 5, lo, hi) for _n, (va, _o, lo, hi) in SITES.items()]
INTERIOR.append((RAD_HOOK, RAD_HOOK + 5, 0x5579F330, 0x5579F365))
assert max(va + len(b) for _n, va, b in CAVES) <= SLOT[1]

if __name__ == "__main__":
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in AT.items()))
    print("  slot used: %d of %d B" % (max(va + len(b) for _n, va, b in CAVES) - SLOT[0], SLOT[1] - SLOT[0]))
    checks()
    run("build_surtrs_chasm", HOOKS, CAVES, SLOT, INTERIOR, reloc_ok=(TE_EXECUTE_SLOT,))
