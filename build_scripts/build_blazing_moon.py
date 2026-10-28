#!/usr/bin/env python
r"""
build_blazing_moon.py -- Blazing Moon (id 95), the Air/Fire dual tier-3 world-map global enchantment.
AoWEPACK.dpl.  Data: build_blazing_moon_pfs.py.  Owner's design 2026-10-27 (05-spells-added.md,
"Air/Fire: Blazing Moon -- agreed design").

THE SPELL  a TSpellWard INSTANCE (Astral Ward's class, as Blessing of Stygia is), registered at
  0x557F3AD7 (Water Mastery's `call RegisterSpell` in RegisterGlobalEnchantmentSpells, replayed
  first; EBX = the control).  Mana 80, research 240 (the single tier-4 figure), upkeep 20 (spell
  +0x1C), sphere 7 (dual), tier 3.  The AI never casts it (Astral Ward's AI weight -1 kept).
  CREATE  TSpellWard VMT +0xA0 (0x557EF778, .reloc kept) -> cave_create: for spell 95 a
          TSpellWardEnchantment re-typed by TGlobalEnchantment.Setup to REC_TYPE 0x58, name "Blazing
          Moon", upkeep 20; any other id goes on to build_blessing_stygia.py's cave (STY_CREATE).
  CANACT  record VMT +0x64 (0x557EF618, .reloc kept) -> cave_canact: a 0x58 record is refused while
          its caster already has an active one, by vanilla's "%s is already active" branch
          (Stygia's idiom: CanActivate's prologue replayed, its exception handler pushed, then
          0x5577DB2A); other types go on to Stygia's cave (STY_CANACT).

EACH DAY  record VMT +0x44 MsgProc (0x557EF5F8, .reloc kept) -> cave_msg, which first calls
  build_awaken_volcano.py's entry (VOLC_MSG, which calls the original MsgProc).  On message
  0x20020003 (a player's world-map turn start, after upkeep) to the caster of an active 0x58 record
  that is the FIRST active 0x58 record in the global magic list (so the land dries once a day,
  however many moons are up): every field of levels 0 (Surface) and 3 (Firmament), row by row,
  rolls TAoWHSMap.Random(map, 100) when its terrain is one of (a level the map lacks is skipped:
  TMapContainer.GetMapLevel has no bounds check, so the level list's count [[container+8]+8] is)
      Snow 3 -> Grass 1 (10)   Grass 1 -> Steppe 4 (10)   Dirt 0xC -> Steppe 4 (10)
      Steppe 4 -> Desert 2 (10)   Wasteland 5 -> Desert 2 (5)   Ice 6 -> Water 0 (25)
  and on a roll under the chance changes it with TAoWHSMap.ChangeTerrain (map VMT +0xD0, radius 0):
  an army that cannot stand on the result vetoes it; forests and other terrain objects re-skin or
  remove themselves (TILTerrainMO.TerrainChanged); the overlay (roads, rivers) is kept.

FEMALES +4 DAM  every unit and hero whose GetGender (VMT +0x10C) is 1, every player's, while any
  0x58 record is active.  Added before each getter's clamp, so every reader (the unit card, both
  combat engines through TCombatUnit.GetDamage -> the strategic unit's +0xC8, the AI) sees it:
    0x55782AC4  TUnit.GetDamage   `add al,dl / movsx edx,al` (5 B) -> jmp cave_udam  (clamp 2..60)
    0x557884D5  THero.GetDamage   `add al,dl / mov [esp],al` (5 B) -> jmp cave_hdam  (clamp 2..40;
                TLeader shares it)
  Read live: TUnit's cached block (+0x44..0x47) is not involved, so nothing needs refreshing when the
  moon rises or sets.

THE WARM LIGHT  0x55778A73, TAoWHSMap.DrawDynamicScene's `call DrawFog` -> call cave_tint, which
  then jumps to DrawFog: after the scene (terrain, objects, armies), before fog, grid and selection.
  On the live map ([AoWHSMap]) showing level 0 or 3 while any 0x58 record is active, every pixel of
  the locked back buffer's clip rectangle (+0x10..+0x1C, rows [top, bottom), columns [left, right);
  row = +0x20 + y * +0x0C) goes through a 64K table: red x284, green x252, blue x200 /256, rounded,
  capped (option F).  The table is built on first use, and again when the masks change, for RGB565
  (masks F800/07E0/001F) or RGB555 (7C00/03E0/001F); other formats are left alone.  It is held with
  System.@GetMem (thunk 0x55701008) at BSS LUT, its red mask at LUT_FMT.  THSMapViewer.ShowScene
  gives the target a fresh static image (drawn, or blitted whole from the cache) before every
  DrawDynamicScene, so the light never compounds.

RNG: P1 SYNCED DRAW (12-re-toolchain.md section 4.10): the per-hex roll runs inside the global magic
control's 0x20020003 broadcast, as Awaken Volcano's spill does, gated on replicated state only (the
fields' terrain, row order); ChangeTerrain reseeds RandSeed itself.
Site 0x558C52E7 (the dry run prints it).
The DAM bonus and the light read replicated state only (the global magic list, the unit's gender).

Slot 0x558C5000-0x558C5FFF, exclusive.  BSS 0x558FAED8 (LUT pointer) and 0x558FAEDC (its red mask).
PIC: one call/pop anchor per routine.  Surgical --undo.  The registration runs at package init:
proved only by launching the exe.

FORWARD HAZARDS
  * Chained in front of build_blessing_stygia.py (CREATE, CANACT) and build_awaken_volcano.py (MSG),
    whose installed entries are the expected "vanilla" bytes of those slots: apply this script after
    both and undo it before either.  Both accept this script's entries (PINNED) as their applied
    state and refuse --apply / --undo while they are in place.
  * build_los_terrain.py owns 0x55778A6A, the scene call just before 0x55778A73.

Unproven, static checks cannot reach it: how the light looks in game; how long a day's drying takes
on a large map (thousands of ChangeTerrain calls); forests' re-skins; the record in the Magic window.

    python build_scripts/build_blazing_moon.py            dry run + state
    python build_scripts/build_blazing_moon.py --apply
    python build_scripts/build_blazing_moon.py --undo
    python build_scripts/build_blazing_moon.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic, ansistr

SPELL_ID, SPELL_NAME = 95, "Blazing Moon"
REC_TYPE = 0x58
MANA, RESEARCH, UPKEEP, SPHERE, TIER = 80, 240, 20, 7, 3
LEVELS = (0, 3)
DRY = {0x03: (10, 0x01), 0x01: (10, 0x04), 0x0C: (10, 0x04), 0x04: (10, 0x02),
       0x05: (5, 0x02), 0x06: (25, 0x00)}             # terrain: (chance %, new terrain)
FEMALE, DAM_BONUS = 1, 4
GAINS = (284, 252, 200)                                # red, green, blue, /256
MASKS = {"565": (0xF800, 0x07E0, 0x001F), "555": (0x7C00, 0x03E0, 0x001F)}
SLOT = (0x558C5000, 0x558C6000)
LUT, LUT_FMT = 0x558FAED8, 0x558FAEDC

AOWHSMAP = 0x558FA040
REGISTER_SPELL, LSTRASG, GETMEM = 0x55779B40, 0x55701150, 0x55701008
WARDSPELL_CELL, WARDSPELL_CREATE = 0x557EF698, 0x557F37F4
WARD_CELL, WARD_CREATE, GE_SETUP, GE_CANACT = 0x557EF574, 0x557F374C, 0x5577DA8C, 0x5577DAE8
CANACT_HANDLER, CANACT_REFUSE = 0x5577DB91, 0x5577DB2A
GETENCH, GETMAPLEVEL, LEVEL_GETFIELD = 0x5577E13C, 0x557020EC, 0x557020DC
RANDOM, DRAWFOG = 0x5577827C, 0x55772EB8

# chained entries, the slots' current ("vanilla" to this script) values
STY_CREATE, STY_CANACT = 0x558BD940, 0x558BD9A0          # build_blessing_stygia.py
VOLC_MSG = 0x558BB00F                                    # build_awaken_volcano.py ENTRY["msg"]

S_REG = 0x557F3AD7
WARD_VMT = 0x557EF5B4
S_MSG, S_CANACT, S_CREATE = WARD_VMT + 0x44, WARD_VMT + 0x64, 0x557EF778
S_UDAM, V_UDAM, R_UDAM = 0x55782AC4, bytes.fromhex("02c20fbed0"), 0x55782AC9
S_HDAM, V_HDAM, R_HDAM = 0x557884D5, bytes.fromhex("02c2880424"), 0x557884DA
S_FOG = 0x55778A73
A = {}
# the chain entries Stygia's and Volcano's scripts accept as their applied state (they hold these)
PINNED = {"create": 0x558C5100, "canact": 0x558C5160, "msg": 0x558C51C0}


def rel(src, dst, op):
    return bytes([op]) + struct.pack("<i", dst - (src + 5))


def c_scan(va):
    """scan(eax = player P, dl = mode) -> eax the first active 0x58 record in list order, or 0.
    mode 0: any; 1: its caster is P."""
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
        mov  ebp, eax
        xor  edi, edi
    s_loop:
        cmp  edi, ebp
        jge  s_no
        mov  eax, esi
        mov  edx, edi
        call {GETENCH:#x}
        inc  edi
        test eax, eax
        je   s_loop
        cmp  byte ptr [eax + 0x18], {REC_TYPE:#x}
        jne  s_loop
        test byte ptr [eax + 0x10], 1
        je   s_loop
        cmp  byte ptr [esp + 4], 0
        je   s_out
        movsx ecx, byte ptr [eax + 0x19]
        cmp  ecx, dword ptr [esp]
        jne  s_loop
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


def c_reg(va):
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
        jne  {STY_CREATE:#x}
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
        mov  dl, {REC_TYPE:#x}
        mov  eax, ebx
        call {GE_SETUP:#x}
        mov  eax, ebx
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "esi", {"WCELL": WARD_CELL, "NAME": ("TAIL", 8)}, ansistr(SPELL_NAME))


def c_canact(va):
    """record +0x64 CanActivate(eax rec, dl player, ecx var msg) -> al."""
    src = f"""
        cmp  byte ptr [eax + 0x18], {REC_TYPE:#x}
        jne  {STY_CANACT:#x}
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


def c_msg(va):
    """record +0x44 MsgProc(eax rec, edx msg): Awaken Volcano's entry (and through it the original)
    first, then the day's drying for the first active moon at its caster's turn start."""
    return asm(f"""
        push ebx
        push esi
        push edi
        push ebp
        mov  esi, eax
        mov  edi, edx
        call {VOLC_MSG:#x}
        cmp  byte ptr [esi + 0x18], {REC_TYPE:#x}
        jne  m_out
        test byte ptr [esi + 0x10], 1
        je   m_out
        cmp  dword ptr [edi], 0x20020003
        jne  m_out
        movsx eax, byte ptr [esi + 0x19]
        cmp  eax, dword ptr [edi + 0x18]
        jne  m_out
        or   eax, -1
        xor  edx, edx
        call {A['scan']:#x}
        cmp  eax, esi
        jne  m_out
        call {A['dry']:#x}
    m_out:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


def dry_table():
    t = bytearray(32)
    for ter, (chance, new) in DRY.items():
        t[2 * ter], t[2 * ter + 1] = chance, new
    return bytes(t)


def c_dry(va):
    """Every field of LEVELS, row by row: the synced roll and ChangeTerrain (see the docstring).
    Frame: +0 level index, +4 level object, +8 W, +0C H, +10 y, +14 x, +18 chance, +1C new terrain,
    +20 level number."""
    lv = "".join(f"""
        cmp  dword ptr [ebp], {i}
        jne  d_lv{i}
        mov  dword ptr [ebp + 0x20], {n}
    d_lv{i}:""" for i, n in enumerate(LEVELS))
    src = f"""
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, 0x24
        mov  ebp, esp
        {{ANC}}
        mov  dword ptr [ebp], 0
    d_level:
        cmp  dword ptr [ebp], {len(LEVELS)}
        jge  d_done
        {lv}
        mov  eax, dword ptr [ebx + {{MAP}}]
        test eax, eax
        je   d_done
        mov  eax, dword ptr [eax + 0x10]
        mov  edx, dword ptr [ebp + 0x20]
        mov  ecx, dword ptr [eax + 8]
        cmp  edx, dword ptr [ecx + 8]
        jge  d_nextlv
        call {GETMAPLEVEL:#x}
        test eax, eax
        je   d_nextlv
        mov  dword ptr [ebp + 4], eax
        mov  ecx, dword ptr [eax + 0xc]
        mov  dword ptr [ebp + 8], ecx
        mov  ecx, dword ptr [eax + 0x10]
        mov  dword ptr [ebp + 0xc], ecx
        mov  dword ptr [ebp + 0x10], 0
    d_row:
        mov  eax, dword ptr [ebp + 0x10]
        cmp  eax, dword ptr [ebp + 0xc]
        jge  d_nextlv
        mov  dword ptr [ebp + 0x14], 0
    d_col:
        mov  eax, dword ptr [ebp + 0x14]
        cmp  eax, dword ptr [ebp + 8]
        jge  d_nextrow
        mov  eax, dword ptr [ebp + 4]
        mov  edx, dword ptr [ebp + 0x14]
        mov  ecx, dword ptr [ebp + 0x10]
        call {LEVEL_GETFIELD:#x}
        test eax, eax
        je   d_nextcol
        movzx ecx, byte ptr [eax + 0x14]
        cmp  ecx, 0xf
        ja   d_nextcol
        lea  edx, [ebx + {{TBL}}]
        movzx eax, byte ptr [edx + ecx*2]
        test eax, eax
        je   d_nextcol
        mov  dword ptr [ebp + 0x18], eax
        movzx eax, byte ptr [edx + ecx*2 + 1]
        mov  dword ptr [ebp + 0x1c], eax
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edx, 100
        call {RANDOM:#x}
        cmp  eax, dword ptr [ebp + 0x18]
        jge  d_nextcol
        push dword ptr [ebp + 0x10]
        push dword ptr [ebp + 0x20]
        push 0
        push dword ptr [ebp + 0x1c]
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edi, dword ptr [eax]
        mov  ecx, dword ptr [ebp + 0x14]
        xor  edx, edx
        call dword ptr [edi + 0xd0]
    d_nextcol:
        inc  dword ptr [ebp + 0x14]
        jmp  d_col
    d_nextrow:
        inc  dword ptr [ebp + 0x10]
        jmp  d_row
    d_nextlv:
        inc  dword ptr [ebp]
        jmp  d_level
    d_done:
        add  esp, 0x24
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP, "TBL": ("TAIL", 0)}, dry_table())


def c_fem(va):
    """fem(eax = a unit or hero) -> eax 1 when it is female and a moon is up, else 0."""
    return asm(f"""
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x10c]
        cmp  al, {FEMALE}
        jne  f_no
        or   eax, -1
        xor  edx, edx
        call {A['scan']:#x}
        test eax, eax
        je   f_no
        mov  eax, 1
        ret
    f_no:
        xor  eax, eax
        ret
    """, va)


def c_udam(va):
    """TUnit.GetDamage, before its clamp (ebx = the unit, al = the sum)."""
    return asm(f"""
        add  al, dl
        push eax
        mov  eax, ebx
        call {A['fem']:#x}
        test eax, eax
        pop  eax
        je   u_out
        add  al, {DAM_BONUS}
    u_out:
        movsx edx, al
        jmp  {R_UDAM:#x}
    """, va)


def c_hdam(va):
    """THero.GetDamage, before its clamp (ebp = the hero, al = the sum, [esp] its byte)."""
    return asm(f"""
        add  al, dl
        push eax
        mov  eax, ebp
        call {A['fem']:#x}
        test eax, eax
        pop  eax
        je   h_out
        add  al, {DAM_BONUS}
    h_out:
        mov  byte ptr [esp], al
        jmp  {R_HDAM:#x}
    """, va)


_LBL = [0]


def chan(sh, bits, gain, out_sh):
    """One channel of the table entry for v = ecx: (c * gain + 128) >> 8, capped, into edx."""
    mx = (1 << bits) - 1
    _LBL[0] += 1
    ok = "c_ok%d" % _LBL[0]
    return f"""
        mov  eax, ecx
        shr  eax, {sh}
        and  eax, {mx:#x}
        imul eax, eax, {gain}
        add  eax, 0x80
        shr  eax, 8
        cmp  eax, {mx:#x}
        jbe  {ok}
        mov  eax, {mx:#x}
    {ok}:
        shl  eax, {out_sh}
        or   edx, eax"""


def c_tint(va):
    """call target at 0x55778A73 (eax = map, edx = the locked back-buffer record); ends in DrawFog."""
    r5, g5, b5 = GAINS
    m565, m555 = MASKS["565"], MASKS["555"]

    def fill(tag, rs, gbits):
        body = (chan(rs, 5, r5, rs) + chan(5, gbits, g5, 5) + chan(0, 5, b5, 0))
        return f"""
    {tag}:
        xor  edx, edx{body}
        mov  word ptr [esi + ecx*2], dx
        inc  ecx
        cmp  ecx, 0x10000
        jb   {tag}
        jmp  t_ready"""

    src = f"""
        pushad
        {{ANC}}
        mov  edi, dword ptr [esp + 0x14]
        test edi, edi
        je   t_out
        mov  eax, dword ptr [esp + 0x1c]
        cmp  dword ptr [ebx + {{MAP}}], eax
        jne  t_out
        mov  ecx, dword ptr [eax + 0x88]
        test ecx, ecx
        je   t_lv
        cmp  ecx, 3
        jne  t_out
    t_lv:
        cmp  dword ptr [edi + 8], 16
        jne  t_out
        cmp  dword ptr [edi + 0x34], {m565[2]:#x}
        jne  t_out
        mov  eax, dword ptr [edi + 0x2c]
        cmp  eax, {m565[0]:#x}
        jne  t_f555
        cmp  dword ptr [edi + 0x30], {m565[1]:#x}
        jne  t_out
        jmp  t_fmt
    t_f555:
        cmp  eax, {m555[0]:#x}
        jne  t_out
        cmp  dword ptr [edi + 0x30], {m555[1]:#x}
        jne  t_out
    t_fmt:
        or   eax, -1
        xor  edx, edx
        call {A['scan']:#x}
        test eax, eax
        je   t_out
        mov  eax, dword ptr [edi + 0x2c]
        mov  esi, dword ptr [ebx + {{LUT}}]
        test esi, esi
        je   t_alloc
        cmp  dword ptr [ebx + {{LUTFMT}}], eax
        je   t_ready
        jmp  t_fill
    t_alloc:
        push eax
        mov  eax, 0x20000
        call {GETMEM:#x}
        mov  esi, eax
        mov  dword ptr [ebx + {{LUT}}], esi
        pop  eax
    t_fill:
        mov  dword ptr [ebx + {{LUTFMT}}], eax
        xor  ecx, ecx
        cmp  eax, {m565[0]:#x}
        jne  t_l555
        {fill("t_l565", 11, 6)}
    t_l555:
        {fill("t_l555b", 10, 5)}
    t_ready:
        mov  edx, dword ptr [edi + 0x14]
    t_row:
        cmp  edx, dword ptr [edi + 0x1c]
        jge  t_out
        mov  eax, edx
        imul eax, dword ptr [edi + 0xc]
        add  eax, dword ptr [edi + 0x20]
        mov  ecx, dword ptr [edi + 0x10]
        lea  ebp, [eax + ecx*2]
        mov  ecx, dword ptr [edi + 0x18]
        sub  ecx, dword ptr [edi + 0x10]
        jle  t_nextrow
    t_px:
        movzx eax, word ptr [ebp]
        mov  ax, word ptr [esi + eax*2]
        mov  word ptr [ebp], ax
        add  ebp, 2
        dec  ecx
        jne  t_px
    t_nextrow:
        inc  edx
        jmp  t_row
    t_out:
        popad
        jmp  {DRAWFOG:#x}
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP, "LUT": LUT, "LUTFMT": LUT_FMT})


BUILDERS = [("scan", c_scan), ("reg", c_reg), ("create", c_create), ("canact", c_canact),
            ("msg", c_msg), ("dry", c_dry), ("fem", c_fem), ("udam", c_udam), ("hdam", c_hdam),
            ("tint", c_tint)]


def layout():
    for name, _b in BUILDERS:           # forward references: far enough for rel32 on the first pass
        A.setdefault(name, SLOT[0] + 0x800)
    for _ in range(3):
        va, blobs = SLOT[0], []
        for name, b in BUILDERS:
            A[name] = va
            blob = b(va)
            blobs.append(("cave_" + name, va, blob))
            va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    for name, pinned in PINNED.items():
        assert A[name] == pinned, ("%s moved to %08X: update PINNED and the accepted-chain values in "
                                   "build_blessing_stygia.py / build_awaken_volcano.py" % (name, A[name]))
    return blobs


def rng_sites(blobs):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    out = []
    for _n, va, b in blobs:
        out += [i.address for i in md.disasm(b, va) if i.mnemonic == "call" and i.op_str == "%#x" % RANDOM]
    return out


def checks(d):
    u = lambda v: struct.unpack_from("<I", d, P.va2off(d, v))[0]
    if u(WARDSPELL_CELL) != 0x557EF6D8 or u(WARD_CELL) != WARD_VMT:
        sys.exit("ABORT: a TSpellWard class cell moved")
    for site, van, ours, what in ((S_REG, REGISTER_SPELL, A["reg"], "RegisterSpell"),
                                  (S_FOG, DRAWFOG, A["tint"], "DrawFog")):
        o = P.va2off(d, site)
        if d[o] != 0xE8 or site + 5 + struct.unpack_from("<i", d, o + 1)[0] not in (van, ours):
            sys.exit("ABORT: %08X is not `call %s` (or this script's)" % (site, what))
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:
        for i in range(ra, ra + rs - 7):
            src = P.IMAGE_BASE + sva + (i - ra)
            if SLOT[0] <= src < SLOT[1]:
                continue
            if d[i:i + 3] == b"\xc7\x47\x10" and struct.unpack_from("<I", d, i + 3)[0] == SPELL_ID:
                sys.exit("ABORT: %08X also stores spell id %d" % (src, SPELL_ID))
            if d[i:i + 4] == b"\x80\x78\x18" + bytes([REC_TYPE]):
                sys.exit("ABORT: %08X already tests record type %#x" % (src, REC_TYPE))


def main():
    from build_lethe import interior_jumps
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d)
    pk = lambda v: struct.pack("<I", v)
    hooks = [(S_REG, rel(S_REG, REGISTER_SPELL, 0xE8), rel(S_REG, A["reg"], 0xE8)),
             (S_CREATE, pk(STY_CREATE), pk(A["create"])),
             (S_CANACT, pk(STY_CANACT), pk(A["canact"])),
             (S_MSG, pk(VOLC_MSG), pk(A["msg"])),
             (S_UDAM, V_UDAM, rel(S_UDAM, A["udam"], 0xE9)),
             (S_HDAM, V_HDAM, rel(S_HDAM, A["hdam"], 0xE9)),
             (S_FOG, rel(S_FOG, DRAWFOG, 0xE8), rel(S_FOG, A["tint"], 0xE8))]
    bad = interior_jumps(d, [(S_UDAM, S_UDAM + 5), (S_HDAM, S_HDAM + 5)])
    if bad:
        sys.exit("ABORT: jumps into a hook's interior: " + ", ".join("%08X->%08X" % x for x in bad))
    print("  interior sweep: no branch lands inside a displaced range")
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    print("  RNG sites (synced TAoWHSMap.Random): " + ", ".join("%08X" % a for a in rng_sites(blobs)))
    run("build_blazing_moon -- Blazing Moon (AoWEPACK)", hooks, blobs, SLOT, [],
        reloc_ok=(S_CREATE, S_CANACT, S_MSG))


if __name__ == "__main__":
    main()
