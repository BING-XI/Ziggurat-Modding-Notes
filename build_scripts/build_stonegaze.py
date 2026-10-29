#!/usr/bin/env python
r"""
build_stonegaze.py -- Stone Gaze (ability 0xCB) and its status Petrified (0xCC).  AoWEPACK.dpl +
AoWTCPCK.dpl.  Owner's design 2026-10-22 (memory project-stone-gaze-design).

THE GAZE
    Stone Gaze is a TEnhancementAbility whose one object gets a run-time copy of the class VMT with
    +0xF8 NewCombatTurn -> cave_gaze (Searing Aura's machinery).  TriggerNewCombatTurn calls it for
    the holder at EVERY turn start with CL = the combat player whose turn begins; the gaze acts when
    that is not the holder's own player -- the victims' turn.  A gazer that is dead or locked
    (GetLocked: stunned, webbed, frozen, entangled, turned, petrified) does not gaze.
    Victims: every live enemy TCombatUnit of that player that is not immune --
      Magic Immunity (0x06), Stone Gaze (0xCB), already Petrified (0xCC), a machine
      (unit GetUnitType == 2, utMachine) -- and in reach:
        manual combat   hex distance 1..RADIUS and MUTUAL FACING: the victim lies in the gazer's
                        arc and the gazer in the victim's.  The arc is 120 degrees centred on the
                        facing (TUnitHS+0x14, HN 1..6 clockwise from North); a hex counts when half
                        or more of it is inside, so the two hexes the edges cut exactly in half
                        count.  The edges run along the hex directions F-1 and F+1, so the rule is
                        exact: the cube vector d (victim - gazer) lies in the closed cone spanned by
                        those two directions -- two sign tests on (q, r, s), CONE below.  Offset ->
                        cube is odd-q (HSEngine.HXtoHP shifts odd columns down; HNtoXYTable agrees,
                        asserted below): q = x, r = y - (x >> 1).  Proof against exact hex areas:
                        Zig notes/03-abilities-added.md "Stone Gaze".
        auto-resolve    no facing exists: every enemy in melee reach (TAbility.fcValidRoundDistance),
                        as the auras do.
    The roll: a 50 % proc (RandInt(2) == 0), then HitRole(ATTACK - RES) with ATTACK 8 = 90 - 5*RES %,
    clamped 10..90 by the engine.  A failed victim gains Petrified (ExpandAbility, which calls
    Changed); after the loop, TCombat.CheckTerminate, so petrifying a side's last free unit ends the
    battle as a death would.
RNG   manual combat: before each victim's draws System.RandSeed := TAoWHSMap.Random(map, $FFFFFF)
      (section 4.4's bridge; the end-turn event is synchronised, raw draws there are not).
      Auto-resolve: P2 COMBAT RAW.  Sites: RNG_SITES.

PETRIFIED
    A second TStunnedAbility instance (TStunnedAbility.Create, id 0xCC, name, duration mode 3 =
    the whole battle; TDurationAbility.CombatDone removes modes 2 and 3) with a run-time VMT copy:
    +0x60 GetDefense -> cave_pdef (+8; Stunned's is -4).
    L   0x55724BA4  TCombatUnit.GetLocked entry (8 B) -> cave_locked: Petrified -> locked.  GetLocked
        is the engine's one total-incapacity test (Frozen/Webbed/Stunned/Entangled/Turned): the
        selection control, the tactical AI, TFastCombat.ExecuteCombatRound, the melee round (no
        retaliation) and the turn hand-over all ask it, for TCombatUnit, TFastCombatUnit and (via
        the import thunk) TTacticalCombatUnit alike -- so a statue acts and auto-passes like a
        stunned unit.  It stays attackable.
    C   0x55726E5B  TCombatSide.GetUndestroyedConquerObjects (6 B) -> cave_count: a statue is not
        counted, so CheckTerminate, UpdateStatus, TFastCombat.Execute and the combat log all treat
        it as dead.
    T   0x557274B8  TCombat.Terminate entry (5 B) -> cave_term: on the first call, every live statue
        on a side that has no counted unit left is destroyed (combat VMT +0x120 DestroyObject) while
        [combat+0x34] is held at 1, so the deaths' CheckTerminate calls return at once.  Statues on
        the other side are left; TCombat.Finalize's CombatDone pass removes Petrified (mode 3), so
        they leave the battle as flesh with the HP they had.  A battle that ends with both sides
        still holding free units (a fallen leader, a flight) kills no statue.
    Removal mid-battle:
    R   0x557E741E  TRemedy.ExecuteSpell's last RemoveAbility (Burning, `call [ecx+0x98]`, 6 B) ->
        call cave_remedy + nop: then Petrified too.
    D   0x5576CAD5  TDispelMagicCA.Execute (8 B, after ListEnchantments; EBX = the target) ->
        cave_dispel: Petrified removed, unconditionally.  The Dispel Magic ability's CA and the
        spell's CA both run this method.  The site sits just past the 30 bytes
        build_combatlog_actions.py asserts (0x5576CAB7..0x5576CAD4); build_command_bond.py's E3
        (0x5576CB4C) is in the same function.
    LOOK  AoWTCPCK zone 0x43C800: header "SGZ1", tint_draw 0x43C810 and the colour table 0x43CB00
        (pinned): 64 RGB565 then 64 RGB555 beige-greys indexed by 6-bit luminance.  Each statue
        pixel is drawn as the table's entry for its luminance.  build_mirrorimage.py's Show wrapper
        owns the body-draw hooks: it marks a unit holding 0xCC (slot byte 2 bit 1) when this header
        is present, and its dispatch draws the marked unit through build_unit_vfx.py's vfx_core
        with this table as the colour map (opacity 256; 128 for Mirror Image's copies of a statue),
        which works for every sprite class.  Fixed 2026-10-29: tint_draw alone tinted only
        TRLESprite16 / TTransparentRLESprite16, and 16048 of the 17676 unit sprites are
        TRLESprite08.  tint_draw (a copy of ILPACK's RLE16 sprite draw, those two classes only, the
        engine's clipping) is now the fallback for when build_unit_vfx.py's header is absent.
        ⚠ COUPLING: the tint is drawn only while build_mirrorimage.py is applied, and on 8-bit
        sprites only while build_unit_vfx.py is applied too.  Any of the three may be undone first:
        Mirror Image checks this header before marking and build_unit_vfx.py's before calling
        vfx_core, and this zone holds no call into either.

REGISTRATION (package init -- prove by launching the exe)
    0x557BCC9B  `call RegisterAbility` -> cave_reg: replay; Stone Gaze (CreateEnhancementAbility,
    mask 0x03FF, VMT copy); Petrified (TStunnedAbility.Create, VMT copy).  Records:
    build_stonegaze_pfs.py.  Holders: build_stonegaze_holders.py.  LADDER 0xCD.

Slots: AoWEPACK 0x558B5000-0x558B57FF, AoWTCPCK 0x0043C800-0x0043CBFF, exclusive.  PIC.
Surgical --undo (both modules).

    python build_scripts/build_stonegaze.py            dry run + state
    python build_scripts/build_stonegaze.py --apply
    python build_scripts/build_stonegaze.py --undo
    python build_scripts/build_stonegaze.py --dis
"""
import itertools, os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run
from piccave import pic, ansistr

EPACK = P.TARGET
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")
GAZE, NAME_GAZE = 0xCB, "Stone Gaze"
PETRIFIED, NAME_PET = 0xCC, "Petrified"
MASK = 0x03FF
RADIUS, ATTACK, DEF_BONUS = 6, 8, 8
MAGIC_IMMUNITY, UT_MACHINE = 0x06, 2

# ---------------------------------------------------------------- AoWEPACK
E_SLOT = (0x558B5000, 0x558B5800)
R_SITE = 0x557BCC9B
REGISTER, CEA, GETMEM, LSTRASG = 0x55750238, 0x5576601C, 0x55701008, 0x55701150
ISCLASS, HSRANDOM, RANDINT, HITROLE = 0x557010C0, 0x5577827C, 0x55701080, 0x55725D98
GETOPPSIDE, GETOBJECTS, FCVALID = 0x55726688, 0x55726DBC, 0x5574E784
CHECKTERM, GETUNDESTROYED, STUN_CREATE = 0x557274D8, 0x55726E28, 0x557BA4A0
VMT_TCOMBATUNIT, VMT_FAST = 0x55715A94, 0x5571D4BC
CELL_TENH = 0x5571DA7C                          # TEnhancementAbility VMT - 0x40
VMT_STUN = 0x557B600C
CELL_STUN = VMT_STUN - 0x40
VAR_AOWHSMAP, CELL_RANDSEED = 0x558FA040, 0x558FB720
VMT_NEG, ENH_SLOTS, STUN_SLOTS = 0x40, 0x10C, 0x114
SLOT_NEWCOMBATTURN, SLOT_GETDEFENSE = 0xF8, 0x60
E_SITES = {   # name: (va, vanilla, resume, function lo, hi)
    "locked": (0x55724BA4, bytes.fromhex("538bd8ba5f000000"), 0x55724BAC, 0x55724BA4, 0x55724C14),
    "count":  (0x55726E5B, bytes.fromhex("f64648017401"), 0x55726E61, 0x55726E28, 0x55726E6F),
    "term":   (0x557274B8, bytes.fromhex("5380783400"), 0x557274BD, 0x557274B8, 0x557274D6),
    "remedy": (0x557E741E, bytes.fromhex("ff9198000000"), None, 0x557E736C, 0x557E7431),
    "dispel": (0x5576CAD5, bytes.fromhex("8b434cba9b000000"), 0x5576CADD, 0x5576CA60, 0x5576CB58),
}
COUNT_SKIP = 0x55726E62

# ---------------------------------------------------------------- AoWTCPCK
MAGIC_VA, MAGIC = 0x0043C800, 0x315A4753        # "SGZ1": build_mirrorimage.py tests it
T_SLOT = (0x0043C810, 0x0043CC00)               # the 16-byte header is written as a hook
TINT_ENTRY = 0x0043C810
LUT_VA = 0x0043CB00                              # the colour table; build_mirrorimage.py reads it
IAT_GET = 0x0046DE04                             # AoWTCPCK's ILPACK TCustomImageLibrary.Get cell
GET_PREF = 0x5521A8B8                            # ILPACK's own (preferred) address of Get
VMT_RLE16, VMT_TRLE16 = 0x5520B020, 0x5520B158   # TRLESprite16 / TTransparentRLESprite16 (ILPACK)
FMT565, FMT555 = 0x56509310, 0x55509310

# ---------------------------------------------------------------- the arc, derived and asserted
DIRS = {1: (0, -1, 1), 2: (1, -1, 0), 3: (1, 0, -1), 4: (0, 1, -1), 5: (-1, 1, 0), 6: (-1, 0, 1)}
_EVEN = {1: (0, -1), 2: (1, -1), 3: (1, 0), 4: (0, 1), 5: (-1, 0), 6: (-1, -1)}   # HNtoXYTable
_ODD = {1: (0, -1), 2: (1, 0), 3: (1, 1), 4: (0, 1), 5: (-1, 1), 6: (-1, 0)}


def cube(x, y):
    return (x, y - (x >> 1), -x - (y - (x >> 1)))


for _x0 in (10, 11):
    for _hn in range(1, 7):
        _dx, _dy = (_EVEN if _x0 % 2 == 0 else _ODD)[_hn]
        _a, _b = cube(_x0, 20), cube(_x0 + _dx, 20 + _dy)
        assert tuple(_b[i] - _a[i] for i in range(3)) == DIRS[_hn], "odd-q conversion"


def in_cone(F, d):
    u, v = DIRS[(F - 2) % 6 + 1], DIRS[F % 6 + 1]
    det = u[0] * v[1] - u[1] * v[0]
    a = (d[0] * v[1] - d[1] * v[0]) / det
    b = (u[0] * d[1] - u[1] * d[0]) / det
    return a >= -1e-9 and b >= -1e-9


def derive_cone():
    cells = [(q, r, -q - r) for q in range(-12, 13) for r in range(-12, 13)
             if max(abs(q), abs(r), abs(q + r)) <= 12]
    out = {}
    for F in range(1, 7):
        for (i, si), (j, sj) in itertools.combinations([(i, s) for i in range(3) for s in (1, -1)], 2):
            if i != j and all((si * c[i] >= 0 and sj * c[j] >= 0) == in_cone(F, c) for c in cells):
                out[F] = ((i, si), (j, sj))
                break
        assert F in out, F
    return out


CONE = derive_cone()
CONE_BYTES = b"".join(struct.pack("<BbBb", i * 4, si, j * 4, sj) for F in range(1, 7)
                      for (i, si), (j, sj) in [CONE[F]])


def build_isstat(va):
    src = f"""
        push ebx
        push edi
        mov  ebx, eax
        test ebx, ebx
        je   i_no
        {{ANC}}
        mov  eax, ebx
        lea  edx, [edi + {{TCU}}]
        call {ISCLASS:#x}
        test al, al
        je   i_no
        mov  eax, ebx
        mov  edx, {PETRIFIED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        jmp  i_out
    i_no:
        xor  eax, eax
    i_out:
        pop  edi
        pop  ebx
        ret
    """
    return pic(src, va, "edi", {"TCU": VMT_TCOMBATUNIT})


def build_locked(va):
    return asm(f"""
        push ebx
        mov  ebx, eax
        mov  eax, dword ptr [ebx + 0x4c]
        mov  edx, {PETRIFIED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  l_yes
        mov  edx, 0x5f
        jmp  {E_SITES['locked'][2]:#x}
    l_yes:
        mov  al, 1
        pop  ebx
        ret
    """, va)


def build_count(va, isstat):
    return asm(f"""
        test byte ptr [esi + 0x48], 1
        je   n_skip
        mov  eax, esi
        call {isstat:#x}
        test al, al
        jne  n_skip
        jmp  {E_SITES['count'][2]:#x}
    n_skip:
        jmp  {COUNT_SKIP:#x}
    """, va)


def build_term(va, isstat):
    return asm(f"""
        cmp  byte ptr [eax + 0x34], 0
        jne  t_orig
        pushal
        mov  ebp, eax
        mov  byte ptr [ebp + 0x34], 1
        xor  esi, esi
    t_side:
        mov  ebx, dword ptr [ebp + esi*4 + 0x1c]
        test ebx, ebx
        je   t_next
        mov  eax, ebx
        call {GETUNDESTROYED:#x}
        test eax, eax
        jne  t_next
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  edi, eax
    t_obj:
        dec  edi
        js   t_next
        mov  edx, edi
        mov  eax, ebx
        call {GETOBJECTS:#x}
        test eax, eax
        je   t_obj
        push eax
        call {isstat:#x}
        test al, al
        pop  eax
        je   t_obj
        push eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        pop  eax
        je   t_obj
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x120]
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        cmp  edi, eax
        jbe  t_obj
        mov  edi, eax
        jmp  t_obj
    t_next:
        inc  esi
        cmp  esi, 2
        jb   t_side
        mov  byte ptr [ebp + 0x34], 0
        popal
    t_orig:
        push ebx
        cmp  byte ptr [eax + 0x34], 0
        jmp  {E_SITES['term'][2]:#x}
    """, va)


def build_remedy(va):
    return asm(f"""
        call dword ptr [ecx + 0x98]
        mov  eax, ebx
        mov  edx, {PETRIFIED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        je   m_out
        mov  eax, ebx
        mov  edx, {PETRIFIED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x98]
    m_out:
        ret
    """, va)


def build_dispel(va):
    return asm(f"""
        mov  eax, dword ptr [ebx + 0x4c]
        test eax, eax
        je   p_go
        mov  edx, {PETRIFIED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        je   p_go
        mov  eax, dword ptr [ebx + 0x4c]
        mov  edx, {PETRIFIED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x98]
    p_go:
        mov  eax, dword ptr [ebx + 0x4c]
        mov  edx, 0x9b
        jmp  {E_SITES['dispel'][2]:#x}
    """, va)


def build_pdef(va):
    return asm(f"""
        mov  al, {DEF_BONUS}
        ret
    """, va)


REACH = RADIUS


def build_gaze(va):
    """NewCombatTurn(EAX = ability, EDX = the gazer, CL = the combat player whose turn begins).
    Locals: -4 turn player, -8 fast?, -0xC gazer HS, -0x10 gazer F, -0x14 gq, -0x18 gr,
    -0x1C side, -0x20 index, -0x24 victim F, -0x28 vx, -0x30 any petrified, -0x3C/-0x38/-0x34 d."""
    src = f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x40
        push ebx
        push esi
        push edi
        mov  esi, edx
        mov  byte ptr [ebp - 4], cl
        mov  byte ptr [ebp - 0x30], 0
        {{ANC}}
        mov  al, byte ptr [esi + 0x45]
        cmp  al, byte ptr [ebp - 4]
        je   g_out
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   g_out
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x64]
        test al, al
        jne  g_out
        xor  eax, eax
        lea  edx, [edi + {{FAST}}]
        cmp  dword ptr [esi], edx
        sete al
        mov  dword ptr [ebp - 8], eax
        test eax, eax
        jne  g_side
        mov  eax, dword ptr [esi + 0x60]
        test eax, eax
        je   g_out
        mov  dword ptr [ebp - 0xc], eax
        movzx ecx, byte ptr [eax + 0x14]
        dec  ecx
        cmp  ecx, 5
        ja   g_out
        inc  ecx
        mov  dword ptr [ebp - 0x10], ecx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        mov  dword ptr [ebp - 0x14], eax
        mov  eax, dword ptr [ebp - 0xc]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        mov  ecx, dword ptr [ebp - 0x14]
        sar  ecx, 1
        sub  eax, ecx
        mov  dword ptr [ebp - 0x18], eax
    g_side:
        mov  eax, esi
        call {GETOPPSIDE:#x}
        movzx eax, al
        cmp  eax, 1
        ja   g_out
        mov  edx, dword ptr [esi + 8]
        mov  eax, dword ptr [edx + eax*4 + 0x1c]
        test eax, eax
        je   g_out
        mov  dword ptr [ebp - 0x1c], eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  dword ptr [ebp - 0x20], eax
    g_next:
        dec  dword ptr [ebp - 0x20]
        js   g_done
        mov  edx, dword ptr [ebp - 0x20]
        mov  eax, dword ptr [ebp - 0x1c]
        call {GETOBJECTS:#x}
        mov  ebx, eax
        test ebx, ebx
        je   g_next
        mov  eax, ebx
        lea  edx, [edi + {{TCU}}]
        call {ISCLASS:#x}
        test al, al
        je   g_next
        mov  al, byte ptr [ebx + 0x45]
        cmp  al, byte ptr [ebp - 4]
        jne  g_next
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   g_next
        mov  eax, ebx
        mov  edx, {MAGIC_IMMUNITY:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  g_next
        mov  eax, ebx
        mov  edx, {GAZE:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  g_next
        mov  eax, ebx
        mov  edx, {PETRIFIED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  g_next
        mov  eax, dword ptr [ebx + 0x4c]
        test eax, eax
        je   g_next
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x114]
        cmp  al, {UT_MACHINE}
        je   g_next
        cmp  dword ptr [ebp - 8], 0
        je   g_tac
        mov  ecx, ebx
        mov  edx, esi
        xor  eax, eax
        call {FCVALID:#x}
        test al, al
        je   g_next
        jmp  g_roll
    g_tac:
        mov  eax, dword ptr [ebx + 0x60]
        test eax, eax
        je   g_next
        movzx ecx, byte ptr [eax + 0x14]
        dec  ecx
        cmp  ecx, 5
        ja   g_next
        inc  ecx
        mov  dword ptr [ebp - 0x24], ecx
        push eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        mov  dword ptr [ebp - 0x28], eax
        pop  eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        mov  ecx, dword ptr [ebp - 0x28]
        sar  ecx, 1
        sub  eax, ecx
        mov  ecx, dword ptr [ebp - 0x28]
        sub  ecx, dword ptr [ebp - 0x14]
        mov  dword ptr [ebp - 0x3c], ecx
        sub  eax, dword ptr [ebp - 0x18]
        mov  dword ptr [ebp - 0x38], eax
        mov  edx, ecx
        add  edx, eax
        neg  edx
        mov  dword ptr [ebp - 0x34], edx
        mov  eax, ecx
        cdq
        xor  eax, edx
        sub  eax, edx
        mov  ecx, eax
        mov  eax, dword ptr [ebp - 0x38]
        cdq
        xor  eax, edx
        sub  eax, edx
        cmp  eax, ecx
        jle  g_d1
        mov  ecx, eax
    g_d1:
        mov  eax, dword ptr [ebp - 0x34]
        cdq
        xor  eax, edx
        sub  eax, edx
        cmp  eax, ecx
        jle  g_d2
        mov  ecx, eax
    g_d2:
        test ecx, ecx
        je   g_next
        cmp  ecx, {REACH}
        jg   g_next
        mov  eax, dword ptr [ebp - 0x10]
        lea  edx, [ebp - 0x3c]
        mov  ecx, 1
        call g_cone
        test al, al
        je   g_next
        mov  eax, dword ptr [ebp - 0x24]
        lea  edx, [ebp - 0x3c]
        mov  ecx, -1
        call g_cone
        test al, al
        je   g_next
        mov  eax, dword ptr [edi + {{MAPVAR}}]
        mov  edx, 0xffffff
        call {HSRANDOM:#x}
        mov  ecx, dword ptr [edi + {{SEED}}]
        mov  dword ptr [ecx], eax
    g_roll:
        mov  eax, 2
        call {RANDINT:#x}
        test eax, eax
        jne  g_next
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx edx, al
        mov  eax, {ATTACK}
        sub  eax, edx
        call {HITROLE:#x}
        test al, al
        je   g_next
        mov  eax, dword ptr [ebx + 0x4c]
        mov  edx, {PETRIFIED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x94]
        mov  byte ptr [ebp - 0x30], 1
        jmp  g_next
    g_done:
        cmp  byte ptr [ebp - 0x30], 0
        je   g_out
        mov  eax, dword ptr [esi + 8]
        call {CHECKTERM:#x}
    g_out:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    g_cone:
        push ebx
        push esi
        lea  esi, [edi + eax*4 + {{CONEM4}}]
        movzx ebx, byte ptr [esi]
        mov  eax, dword ptr [edx + ebx]
        movsx ebx, byte ptr [esi + 1]
        imul eax, ebx
        imul eax, ecx
        test eax, eax
        js   c_no
        movzx ebx, byte ptr [esi + 2]
        mov  eax, dword ptr [edx + ebx]
        movsx ebx, byte ptr [esi + 3]
        imul eax, ebx
        imul eax, ecx
        test eax, eax
        js   c_no
        mov  al, 1
        jmp  c_out
    c_no:
        xor  eax, eax
    c_out:
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "edi", {"FAST": VMT_FAST, "TCU": VMT_TCOMBATUNIT, "MAPVAR": VAR_AOWHSMAP,
                                "SEED": CELL_RANDSEED, "CONEM4": ("TAIL", -4)}, CONE_BYTES)


def build_reg(va, gaze_va, pdef_va):
    tail = ansistr(NAME_GAZE)
    t_pet = len(tail)
    tail += ansistr(NAME_PET)
    src = f"""
        call {REGISTER:#x}
        push ebp
        mov  ebp, esp
        push esi
        push edi
        {{ANC}}
        push eax
        lea  edx, [eax + {{NGAZE}}]
        mov  cx, {MASK:#x}
        mov  eax, {GAZE:#x}
        call {CEA:#x}
        push eax
        mov  eax, {VMT_NEG + ENH_SLOTS:#x}
        call {GETMEM:#x}
        mov  edi, eax
        mov  esi, dword ptr [esp]
        mov  esi, dword ptr [esi]
        sub  esi, {VMT_NEG:#x}
        mov  ecx, {(VMT_NEG + ENH_SLOTS) // 4:#x}
        rep movsd dword ptr es:[edi], dword ptr [esi]
        lea  edx, [eax + {VMT_NEG:#x}]
        mov  dword ptr [eax], edx
        mov  ecx, dword ptr [ebp - 0xc]
        lea  esi, [ecx + {{GAZEF}}]
        mov  dword ptr [edx + {SLOT_NEWCOMBATTURN:#x}], esi
        lea  esi, [ecx + {{TENH}}]
        mov  dword ptr [edx - 0x18], esi
        pop  eax
        mov  dword ptr [eax], edx
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER:#x}
        mov  ecx, dword ptr [ebp - 0xc]
        lea  eax, [ecx + {{STUNVMT}}]
        xor  ecx, ecx
        mov  dl, 1
        call {STUN_CREATE:#x}
        mov  dword ptr [eax + 0xc], {PETRIFIED:#x}
        mov  byte ptr [eax + 0x28], 3
        push eax
        lea  eax, [eax + 8]
        mov  ecx, dword ptr [ebp - 0xc]
        lea  edx, [ecx + {{NPET}}]
        call {LSTRASG:#x}
        mov  eax, {VMT_NEG + STUN_SLOTS:#x}
        call {GETMEM:#x}
        mov  edi, eax
        mov  esi, dword ptr [esp]
        mov  esi, dword ptr [esi]
        sub  esi, {VMT_NEG:#x}
        mov  ecx, {(VMT_NEG + STUN_SLOTS) // 4:#x}
        rep movsd dword ptr es:[edi], dword ptr [esi]
        lea  edx, [eax + {VMT_NEG:#x}]
        mov  dword ptr [eax], edx
        mov  ecx, dword ptr [ebp - 0xc]
        lea  esi, [ecx + {{PDEF}}]
        mov  dword ptr [edx + {SLOT_GETDEFENSE:#x}], esi
        lea  esi, [ecx + {{STUNCELL}}]
        mov  dword ptr [edx - 0x18], esi
        pop  eax
        mov  dword ptr [eax], edx
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER:#x}
        pop  eax
        pop  edi
        pop  esi
        pop  ebp
        ret
    """
    return pic(src, va, "eax", {"NGAZE": ("TAIL", 8), "NPET": ("TAIL", t_pet + 8), "GAZEF": gaze_va,
                                "TENH": CELL_TENH, "STUNVMT": VMT_STUN, "PDEF": pdef_va,
                                "STUNCELL": CELL_STUN}, tail)


def e_layout():
    caves, at, va = [], {}, E_SLOT[0]

    def put(n, b):
        nonlocal va
        caves.append(("cave_" + n, va, b))
        at[n] = va
        va = (va + len(b) + 0xF) & ~0xF

    put("isstat", build_isstat(va))
    put("locked", build_locked(va))
    put("count", build_count(va, at["isstat"]))
    put("term", build_term(va, at["isstat"]))
    put("remedy", build_remedy(va))
    put("dispel", build_dispel(va))
    put("pdef", build_pdef(va))
    put("gaze", build_gaze(va))
    put("reg", build_reg(va, at["gaze"], at["pdef"]))
    return at, caves


# ---------------------------------------------------------------- the tint (AoWTCPCK)
def luts():
    """64 entries each, indexed by 6-bit luminance: a warm beige-grey, shadows lifted a little."""
    out565, out555 = b"", b""
    for i in range(64):
        t = 0.10 + 0.90 * (i / 63.0)
        r, g, b = (min(255, int(round(c * t))) for c in (232, 220, 192))
        out565 += struct.pack("<H", ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
        out555 += struct.pack("<H", ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3))
    return out565, out555


def build_tint(va):
    """tint_draw(EAX = image, EDX = x, ECX = y, [esp+4] = surface), `ret 4`, EBX = the image VMT
    (kept).  ILPACK TRLESprite16.ShowTransparent's wrapper (load on demand, pixel-format remap,
    unload) around a per-pixel RLE16 walk with the engine's clip rectangle.
    Locals: -4 img, -8 x, -0xC y, -0x11 loaded-by-us, -0x12 unknown format, -0x18 lut, -0x1C fmt,
    -0x20 x0, -0x24 row y, -0x28 rows left, -0x2C key, -0x30 record end, -0x34 px, -0x38 row base,
    -0x39 row visible."""
    src = f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x40
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp - 4], eax
        mov  dword ptr [ebp - 8], edx
        mov  dword ptr [ebp - 0xc], ecx
        mov  byte ptr [ebp - 0x11], 0
        mov  byte ptr [ebp - 0x12], 0
        {{ANC}}
        mov  ecx, dword ptr [edi + {{GETIAT}}]
        sub  ecx, {GET_PREF:#x}
        mov  edx, dword ptr [eax]
        lea  esi, [ecx + {VMT_RLE16:#x}]
        cmp  edx, esi
        je   t_rle
        lea  esi, [ecx + {VMT_TRLE16:#x}]
        cmp  edx, esi
        jne  t_plain
    t_rle:
        mov  ebx, eax
        cmp  byte ptr [ebx + 8], 0
        jne  t_loaded
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x50]
        mov  byte ptr [ebp - 0x11], 1
    t_loaded:
        mov  esi, dword ptr [ebp + 8]
        mov  eax, dword ptr [esi + 0x28]
        cmp  eax, dword ptr [ebx + 0x40]
        je   t_fmt
        mov  edx, eax
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x5c]
        test eax, eax
        jne  t_unknown
    t_fmt:
        mov  eax, dword ptr [ebx + 0x40]
        mov  dword ptr [ebp - 0x1c], eax
        lea  edx, [edi + {{L565}}]
        cmp  eax, {FMT565:#x}
        je   t_lut
        lea  edx, [edi + {{L555}}]
        cmp  eax, {FMT555:#x}
        jne  t_unknown
    t_lut:
        mov  dword ptr [ebp - 0x18], edx
        mov  eax, dword ptr [ebp - 8]
        add  eax, dword ptr [ebx + 0x28]
        add  eax, dword ptr [ebx + 0x50]
        mov  dword ptr [ebp - 0x20], eax
        mov  eax, dword ptr [ebp - 0xc]
        add  eax, dword ptr [ebx + 0x2c]
        add  eax, dword ptr [ebx + 0x54]
        mov  dword ptr [ebp - 0x24], eax
        mov  eax, dword ptr [ebx + 0x5c]
        mov  dword ptr [ebp - 0x28], eax
        movzx eax, word ptr [ebx + 0x48]
        mov  dword ptr [ebp - 0x2c], eax
        mov  esi, dword ptr [ebx + 0x4c]
        test esi, esi
        je   t_end
    t_row:
        cmp  dword ptr [ebp - 0x28], 0
        jle  t_end
        mov  ecx, dword ptr [esi]
        lea  edx, [esi + ecx]
        mov  dword ptr [ebp - 0x30], edx
        add  esi, 4
        mov  eax, dword ptr [ebp - 0x20]
        mov  dword ptr [ebp - 0x34], eax
        mov  byte ptr [ebp - 0x39], 0
        mov  ecx, dword ptr [ebp + 8]
        mov  eax, dword ptr [ebp - 0x24]
        cmp  eax, dword ptr [ecx + 0x14]
        jl   t_pix
        cmp  eax, dword ptr [ecx + 0x1c]
        jge  t_pix
        imul eax, dword ptr [ecx + 0xc]
        add  eax, dword ptr [ecx + 0x20]
        mov  dword ptr [ebp - 0x38], eax
        mov  byte ptr [ebp - 0x39], 1
    t_pix:
        cmp  esi, dword ptr [ebp - 0x30]
        jae  t_rowend
        movzx eax, word ptr [esi]
        cmp  eax, dword ptr [ebp - 0x2c]
        jne  t_lit
        movzx eax, word ptr [esi + 2]
        shr  eax, 1
        add  dword ptr [ebp - 0x34], eax
        add  esi, 4
        jmp  t_pix
    t_lit:
        add  esi, 2
        cmp  byte ptr [ebp - 0x39], 0
        je   t_adv
        mov  ecx, dword ptr [ebp + 8]
        mov  edx, dword ptr [ebp - 0x34]
        cmp  edx, dword ptr [ecx + 0x10]
        jl   t_adv
        cmp  edx, dword ptr [ecx + 0x18]
        jge  t_adv
        mov  ebx, eax
        cmp  dword ptr [ebp - 0x1c], {FMT565:#x}
        jne  t_555
        mov  ecx, ebx
        shr  ecx, 11
        imul ecx, ecx, 154
        mov  edx, ebx
        shr  edx, 5
        and  edx, 63
        imul edx, edx, 150
        add  ecx, edx
        jmp  t_blue
    t_555:
        mov  ecx, ebx
        shr  ecx, 10
        and  ecx, 31
        imul ecx, ecx, 154
        mov  edx, ebx
        shr  edx, 5
        and  edx, 31
        imul edx, edx, 300
        add  ecx, edx
    t_blue:
        and  ebx, 31
        imul ebx, ebx, 58
        add  ecx, ebx
        shr  ecx, 8
        cmp  ecx, 63
        jbe  t_put
        mov  ecx, 63
    t_put:
        mov  edx, dword ptr [ebp - 0x18]
        movzx eax, word ptr [edx + ecx*2]
        mov  edx, dword ptr [ebp - 0x38]
        mov  ecx, dword ptr [ebp - 0x34]
        mov  word ptr [edx + ecx*2], ax
    t_adv:
        inc  dword ptr [ebp - 0x34]
        jmp  t_pix
    t_rowend:
        mov  esi, dword ptr [ebp - 0x30]
        add  esi, 3
        and  esi, 0xfffffffc
        inc  dword ptr [ebp - 0x24]
        dec  dword ptr [ebp - 0x28]
        jmp  t_row
    t_unknown:
        mov  byte ptr [ebp - 0x12], 1
    t_end:
        mov  ebx, dword ptr [ebp - 4]
        cmp  byte ptr [ebp - 0x11], 0
        je   t_done
        cmp  byte ptr [ebx + 0x16], 2
        jne  t_done
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x4c]
    t_done:
        cmp  byte ptr [ebp - 0x12], 0
        jne  t_plain
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret  4
    t_plain:
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [ebp - 8]
        mov  ecx, dword ptr [ebp - 0xc]
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        jmp  dword ptr [ebx + 0x84]
    """
    return pic(src, va, "edi", {"GETIAT": IAT_GET, "L565": LUT_VA, "L555": LUT_VA + 128})


def t_layout():
    """tint_draw and the colour table, both pinned (build_mirrorimage.py reads the table)."""
    tint = build_tint(TINT_ENTRY)
    assert TINT_ENTRY + len(tint) <= LUT_VA, "tint_draw overruns the colour table"
    l565, l555 = luts()
    return {"tint": TINT_ENTRY, "lut": LUT_VA}, [("cave_tint", TINT_ENTRY, tint),
                                                ("cave_lut", LUT_VA, l565 + l555)]


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def checks():
    module(EPACK, 0x55700000)
    d = open(EPACK, "rb").read()
    rd = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    for vmt, cname in ((VMT_TCOMBATUNIT, b"TCombatUnit"), (VMT_FAST, b"TFastCombatUnit"),
                       (VMT_STUN, b"TStunnedAbility"), (CELL_TENH + 0x40, b"TEnhancementAbility")):
        cn = P.va2off(d, rd(vmt - 0x20))
        if rd(vmt - 0x40) != vmt or d[cn + 1:cn + 1 + d[cn]] != cname:
            sys.exit("ABORT: %s VMT not at %08X" % (cname.decode(), vmt))
    if rd(VMT_STUN - 0x20) - VMT_STUN != STUN_SLOTS or rd(CELL_TENH + 0x40 - 0x20) - CELL_TENH - 0x40 != ENH_SLOTS:
        sys.exit("ABORT: a copied VMT changed size")
    if rd(VMT_STUN + SLOT_GETDEFENSE) != 0x557BA550:
        sys.exit("ABORT: TStunnedAbility +0x60 is not GetDefense")
    if rd(VMT_TCOMBATUNIT + 0x64) != E_SITES["locked"][0] or rd(VMT_FAST + 0x64) != E_SITES["locked"][0]:
        sys.exit("ABORT: GetLocked is not the combat units' +0x64")
    if rd(VMT_TCOMBATUNIT + 0x120) != 0x557256F0:
        sys.exit("ABORT: TCombatUnit +0x120 is not DestroyObject")
    _e, secs = P.sections(d)
    for aid in (GAZE, PETRIFIED):
        for vs, sva, rs, ra in secs:
            blob = d[ra:ra + rs]
            for pat in (b"\xb8" + struct.pack("<I", aid) + b"\xe8",
                        bytes([0xC7, 0x40, 0x0C]) + struct.pack("<I", aid)):
                k = blob.find(pat)
                while k >= 0:
                    src = P.IMAGE_BASE + sva + k
                    if not E_SLOT[0] <= src < E_SLOT[1]:
                        sys.exit("ABORT: %08X also registers %#x" % (src, aid))
                    k = blob.find(pat, k + 1)
    module(TCPCK, 0x00400000)
    t = open(TCPCK, "rb").read()
    o = P.va2off(t, 0x004016F4)
    if t[o:o + 2] != b"\xff\x25" or struct.unpack_from("<I", t, o + 2)[0] != IAT_GET:
        sys.exit("ABORT: AoWTCPCK's Get thunk no longer reads IAT %08X" % IAT_GET)
    il = open(os.path.join(P.GAME, "ILPACK.dpl"), "rb").read()
    P.IMAGE_BASE = 0x55200000
    ri = lambda va: struct.unpack_from("<I", il, P.va2off(il, va))[0]
    for vmt, cname in ((VMT_RLE16, b"TRLESprite16"), (VMT_TRLE16, b"TTransparentRLESprite16")):
        cn = P.va2off(il, ri(vmt - 0x20))
        if ri(vmt - 0x40) != vmt or il[cn + 1:cn + 1 + il[cn]] != cname:
            sys.exit("ABORT: ILPACK %s VMT not at %08X" % (cname.decode(), vmt))
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    from aowsyms import get_symbols
    if get_symbols("ILPACK.dpl")[2].get(GET_PREF) != "ImageLib.TCustomImageLibrary.Get":
        sys.exit("ABORT: ILPACK's TCustomImageLibrary.Get is not at %08X" % GET_PREF)
    module(TCPCK, 0x00400000)
    if t[P.va2off(t, MAGIC_VA):P.va2off(t, MAGIC_VA) + 16] not in (bytes(16), T_HEAD):
        sys.exit("ABORT: the Stone Gaze header bytes at %08X are someone else's" % MAGIC_VA)
    module(EPACK, 0x55700000)
    import ability_names
    nm = ability_names.names()
    if nm.get(GAZE, NAME_GAZE) != NAME_GAZE or nm.get(PETRIFIED, NAME_PET) != NAME_PET:
        sys.exit("ABORT: ability_names gives 0xCB/0xCC other names")
    import build_mirrorimage as MI
    if MI.SG_MAGIC_VA != MAGIC_VA or MI.SG_MAGIC != MAGIC or MI.SG_TINT != TINT_ENTRY or \
            MI.SG_LUT != LUT_VA or MI.PETRIFIED != PETRIFIED:
        sys.exit("ABORT: build_mirrorimage.py's Stone Gaze constants disagree with this script")


E_AT, E_CAVES = e_layout()
T_AT, T_CAVES = t_layout()
call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
E_HOOKS = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, E_AT["reg"]))]
for _n, (_va, _van, _res, _lo, _hi) in E_SITES.items():
    if _n == "remedy":
        E_HOOKS.append((_va, _van, call_to(_va, E_AT[_n]) + b"\x90"))
    else:
        E_HOOKS.append((_va, _van, jmp_to(_va, E_AT[_n], len(_van))))
E_INTERIOR = [(va, va + len(van), lo, hi) for _n, (va, van, _r, lo, hi) in E_SITES.items()]
T_HEAD = struct.pack("<I", MAGIC) + bytes(12)
T_HOOKS = [(MAGIC_VA, bytes(16), T_HEAD)]
# entry points, asserted (and read by rng_audit.py --owners)
ENTRY = {"isstat": 0x558B5000, "locked": E_AT["locked"], "count": E_AT["count"], "term": E_AT["term"],
         "remedy": E_AT["remedy"], "dispel": E_AT["dispel"], "pdef": E_AT["pdef"], "gaze": E_AT["gaze"],
         "reg": E_AT["reg"], "tint": 0x0043C810, "lut": 0x0043CB00}
assert {**E_AT, **T_AT} == ENTRY, "the cave layout moved"


def rng_sites():
    """The gaze's re-anchor (TAoWHSMap.Random), its proc (@RandInt) and its HitRole call."""
    code = dict((n, b) for n, _va, b in E_CAVES)["cave_gaze"]
    base = E_AT["gaze"]
    out = []
    for i in range(len(code) - 5):
        if code[i] == 0xE8:
            tgt = base + i + 5 + struct.unpack_from("<i", code, i + 1)[0]
            if tgt in (HSRANDOM, RANDINT, HITROLE):
                out.append((base + i, tgt))
    return out


RNG_SITES = rng_sites()
assert [t for _s, t in RNG_SITES] == [HSRANDOM, RANDINT, HITROLE], RNG_SITES
# literal, so rng_audit.py --owners attributes the draws here
RNG_SITE_ANCHOR, RNG_SITE_PROC, RNG_SITE_HITROLE = 0x558B53C1, 0x558B53D3, 0x558B53F1
assert [s for s, _t in RNG_SITES] == [RNG_SITE_ANCHOR, RNG_SITE_PROC, RNG_SITE_HITROLE], RNG_SITES


def go(argv):
    module(EPACK, 0x55700000)
    run("build_stonegaze [AoWEPACK]", E_HOOKS, E_CAVES, E_SLOT, E_INTERIOR, argv)
    module(TCPCK, 0x00400000)
    run("build_stonegaze [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, [], argv)
    module(EPACK, 0x55700000)


if __name__ == "__main__":
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in {**E_AT, **T_AT}.items()))
    print("  cone:", {F: CONE[F] for F in CONE})
    print("  RNG sites:", ", ".join("%08X" % s for s, _t in RNG_SITES))
    checks()
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])
        print("\n" + "=" * 60)
    go(argv)
