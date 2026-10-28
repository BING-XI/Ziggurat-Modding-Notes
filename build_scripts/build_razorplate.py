#!/usr/bin/env python
r"""
build_razorplate.py -- Razor Plate (ability 0xBD): every melee strike that lands on the unit costs
the striker d5 physical damage.  AoWEPACK.dpl + AoWTCPCK.dpl.  Owner's design 2026-10-09; v2
2026-10-10 (every melee blow, flinch and blood, log lines, replay number, AI).

RULES (owner's rulings 2026-10-09/10)
    Trigger    every melee strike that lands on a Razor Plate unit: the ordinary melee round (attack
               and retaliation), Round Attack, the free swing at a unit moving away, and the swing a
               touched unit makes back at a failed touch.  Once per landed strike.  Ranged attacks do
               not trigger it (another CA class).
    Landed     CA+0x10 != 0 after Generate.  A miss never executes in manual combat (the TEs skip the
               CA), so this is the only rule both engines share.  A strike fully absorbed by the
               Razor Plate unit's own immunity also rolls 0 and does not cut.
    Damage     1..5 uniform, no to-hit roll.  Physical, in ExecuteDamageRole's own order: Physical
               Immunity (bit 0x80 of GetImmunityTypes) -> 0; Embrittled (0xB2; Spectral Wings
               answers it too) x1.5 rounded up, (3d+1)>>1, as build_embrittle.py's cave_dmg;
               Physical Protection (bit 0x80 of GetProtectionTypes) halves, rounding up, as
               vanilla's (dmg+1)>>1; Embrittled and Physical Protection together cancel (the cut
               is unchanged), as cave_dmg's doubling before the halve does.  x2 until 2026-10-28.
    Dealer     the Razor Plate unit, through DoDamage (VMT +0x108), so a kill earns it kill XP.  If
               the strike killed the Razor Plate unit, the cut lands through ExecuteDamage (+0x124)
               with no dealer and no XP.
    Round      a Round Attacker killed by a cut stops: manual combat's sweep already tests
    Attack     GetEnabled first thing every frame (0x0040A3B4) and ends cleanly; auto-resolve gets
               the same rule from cave_rnd (owner: dying partway is fine, 2026-10-10).

HOW
  roll   one RandInt(5) per strike built, ungated; the store is gated on landed + target
         GetAbilityEnabled(0xBD) (VMT +0xA8: item-aware, nil-safe, 0 on a wall).  roll+1 goes into
         bits 0xE0 of CA+0x18, the one strike-flag byte TStrikeCA.ReadWrite serialises (tag 0x14), so
         the auto-resolve replay, which re-runs Execute from the recorded CAs, reproduces it.
         Three builders: TMeleeRound.CreateStrikeCA side 0 and side 1, and AoWE.CreateStrikeCA (Round
         Attack, free swing, touch retaliation -- both engines).
         CA+0x18 after this: 01 Cause Fear, 02 vanilla LifeStealing (vestigial), 04 Entangle Strike,
         08 LifeStealing, 10 Dark Gift (build_lifesteal_roundattack.py), E0 Razor Plate.
  apply  TStrikeCA.Execute, between the Cause Fear and Entangle Strike blocks (after the strike's own
         damage and the lifesteal heal).  EBX = CA, EDI = striker, ESI = struck unit.  The cut that
         lands is stored in CA+0x16 (TDamageCA alignment padding: no method or ReadWrite touches
         +0x16/+0x17), zeroed first on every Execute.  CA+0x16 feeds the manual-combat visuals, the
         replay number and both log lines.
  stop   vanilla's invariant was that a striker cannot fall to its own blow.
           melee round, auto-resolve  TStrikeAbility.fcExecuteCombatCommand: stop unless both units
                                      are GetEnabled (cave_loop)
           melee round, manual        TCMeleeMoveTE.LastMove state 4: attacker down -> vanilla's
                                      attacker-died ending ([ebp-5] := 3); defender down -> its
                                      defender-died ending (state 1 + attacker SetAction); else
                                      NextStrike (cave_tc)
           Round Attack, auto         the follow-up blows skip a fallen attacker (cave_rnd: NIL,
                                      which the caller already tests)
           free swing, manual         TCombatMoveTE.DefaultMove resets and then waits on the
                                      swinger's HS after its blow; a unit that dies in manual
                                      combat has its HS FREED (TTacticalCombatUnit.ExecuteDamage
                                      0x0042069D, [unit+0x60] := 0).  cave_fsx skips a missing HS,
                                      cave_fsw treats one as ready, cave_sa makes SetAction itself
                                      return on a nil HS (vanilla never passes one).
           touch retaliation          nothing touches the retaliator after its blow; no change.
  show   manual combat, after the strike executes, a surviving cut striker plays the engine's own
         flinch (SetAction 4) and MakeHitBlood(unit, cut).  Melee round: when the round ends on that
         strike the attacker keeps the flinch instead of action 7 (state 1 waits on +0x25, which
         action 4 sets, as vanilla's own flinch waits do).  Free swing: flinch in place of action 7.
         Round Attack: blood only, since a flinch would reset the sweep's frame counter.
  replay TDamageCA.ShowObject's striker branch draws ShowDamageIcon over the striker once the blow
         has landed (same frame gate as the target's number).
  log    "<striker> is cut by Razor Plate for N damage".  Live manual combat: into the combat log's
         ring at 0x60D000 from cave_apply, gated on RING_TACTICAL (0x60D00C) == 1.  Auto-resolve
         replay: into the log memo from a wrapper on TStrikeCA's VMT +0x54 Play slot, on the trigger
         tick only (a slider seek re-Executes without Play, so it prints nothing).  Guards and wire
         format copied from build_combatlog_dll.py / build_replaylog.py and cross-checked at run time.
  AI     TMeleeRound.CalculateDV (tail): for each strike whose target has Razor Plate, adds
         P(land) x E[cut] to the striker's side's "damage taken back" DV (+0x1C for an attacker's
         strike, +0x18 for a defender's).  P(land)x100 = StatisticsToDV(atk+mod, 1, ...), the engine's
         own estimator at damage 1, so immunity counts.  E[cut] in tenths: 30, 18 with Physical
         Protection, 48 Embrittled (60 until 2026-10-28), 30 both, 0 Physical Immunity.  Combat objects (+0x10/+0x14) and
         prediction (+0x20/+0x24, strategic slots) both covered, so every consumer of
         GetAttackerDV/GetDefenderDV sees it.  Melee rounds only.

RNG: P2 COMBAT RAW -- the three builders draw through TStrikeCA.Generate -> ExecuteDamageRole, in the
RAW list; one draw per strike built, ungated (sec 4.5).  Manual combat re-anchors RandSeed from a synced
draw before every strike it builds (0x00409B45, 0x0040A525, 0x0040ABA3, 0x004089D6).  The blood is P3
COSMETIC RAW (MakeHitBlood's own draws, as vanilla's per-hit blood, run by every peer's TE alike).

REGISTRATION (package init -- prove by launching the exe)
    CreateEnhancementAbility 0x5576601C + RegisterAbility 0x55750238, spliced at the vanilla `call
    RegisterAbility` 0x557BCD98 in PassiveAb.RegisterPassiveAbilities (High Prayer Blessing; EBX =
    the control), replayed first.  Mask 0x03FF, every selection bit (units, items, leader
    customisation, hero level-up at 12 points, editor), as the record's tag 9 (2026-10-10; was
    0x0201).  Record: build_razorplate_pfs.py.
    Ceilings: LADDER 0xBE in build_abilityid_ceilings.py and build_tcablist_ceiling.py;
    re_tools/ability_names.py MODDED.

HOOKS (vanilla bytes asserted, no .reloc under any but the VMT slot)
  AoWEPACK.dpl
    R   0x557BCD98  call RegisterAbility -> call cave_reg
    S0  0x55767EDA  mov edx,0x76 (5 B) -> call cave_s0         melee round, side 0
    S1  0x55767F3E  12 B Generate call -> jmp cave_s1           melee round, side 1 (EDI as the VMT
                    scratch instead of EBX, so the round survives the call)
    S2  0x557666FB  call SetDefensive -> call cave_s2            AoWE.CreateStrikeCA
    X   0x55766806  test byte [ebx+0x18],4 / je (6 B) -> jmp cave_apply
    L   0x557670B9  mov al,[esp+0x18] / sub al,1 (6 B) -> jmp cave_loop; 0x557670BF-0x557670E2 dead
    RA  0x5576964E  call CreateStrikeCA -> call cave_rnd         TRoundAttackAbility.fc, follow-ups
    SH  0x55729E34  ShowObject striker branch (35 B) -> jmp cave_show
    PL  0x5571E398  TStrikeCA VMT +0x54 Play 0x55766860 -> cave_play (.reloc kept: in-image value)
    DV  0x55768045  CalculateDV epilogue pop edx/edi/esi/ebx/ret -> jmp cave_dv
  AoWTCPCK.dpl
    T0  0x004096CD  15 B post-execute test, melee side 0 -> jmp cave_tc
    T1  0x00409726  15 B post-execute test, melee side 1 -> jmp cave_tc
    SA  0x004236E0  SetAction prologue (6 B) -> jmp cave_sa
    FX  0x00408BE5  free swing, after the blow (23 B) -> jmp cave_fsx
    FW  0x00408C39  free swing, state 1 wait (19 B) -> jmp cave_fsw
    TR  0x0040AF2C  touch retaliation, after the blow (11 B) -> jmp cave_tch
    RT  0x0040A5B1  Round Attack sweep, after the blow (11 B) -> jmp cave_rat
  Every jump into the TCPCK hook starts comes from the same state block, with the CA in [TE+0x34].

Slots: AoWEPACK 0x5589A000-0x5589A7FF exclusive (above build_sky_anim.py's reservation);
AoWTCPCK 0x0043AE40-0x0043B03F exclusive.  PIC: rel32, register-relative and call/pop anchors; the
only absolutes are AoWz.exe's (0x40003C, 0x60D0xx, 0x45B2E0), fixed-base, as in the combat log.

Couplings.  build_lifesteal_roundattack.py owns CA+0x18 bits 08/10 and the 0x5576678C hook in the same
function.  The Embrittled rule is a COPY of build_embrittle.py's cave_dmg, so re-tune both together
(cave_apply and dv_body's E[cut]).  It is a copy because TCombatObject.ExecuteDamageRole, where
Embrittle and the Weaknesses live, is a damage ROLL from ATK and DAM with no fixed-amount entry;
build_flight_fall.py's forced core roll (0x55781B0D, the strategic twin) is the pattern that would
let the cut go through it instead.
build_panic_cleardamage.py's ExecuteDamage hook clears Panic on a striker that takes the cut.  The log
lines depend on build_combatlog_exe.py's ring and RING_TACTICAL and on build_replaylog.py's memo chain
(checked at run time); with either absent the guards make them silent.  build_simfly.py's raze
predictor reads GetDefenderDV and so sees the cut.

Unproven, static checks cannot reach it: the flinch and blood timing against the next strike's wind-up,
and the replay number's placement over the striker.

Undo: --undo is surgical.  Remove Razor Plate from every unit and run build_razorplate_pfs.py --undo
first -- a unit carrying an unregistered id meets a nil registry slot.

    python build_scripts/build_razorplate.py            dry run + state, both modules
    python build_scripts/build_razorplate.py --apply
    python build_scripts/build_razorplate.py --undo
    python build_scripts/build_razorplate.py --dis
"""
import os, re, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

HERE = os.path.dirname(os.path.abspath(__file__))
EPACK = os.path.join(P.GAME, "AoWEPACK.dpl")
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")

ABIL_ID = 0xBD
NAME = "Razor Plate"
MASK = 0x03FF
DIE = 5                       # RandInt(DIE)+1; the 3-bit field holds at most 7
EMBRITTLED = 0xB2
PHYS = 0x80                   # physical damage-type bit
LINE_CUT, LINE_DMG, LINE_UNK = " is cut by Razor Plate for ", " damage", "?"

E_SLOT = (0x5589A000, 0x5589A800)
T_SLOT = (0x0043AE40, 0x0043B040)

# AoWEPACK.dpl
CEA, REGISTER, RANDINT = 0x5576601C, 0x55750238, 0x55701080
SETDEFENSIVE, CREATESTRIKE = 0x557299E4, 0x557665E4
STRIKE_PLAY, FINDID, STATS_DV = 0x55766860, 0x55728C68, 0x55726038
DMGTYPE, SHOWICON = 0x5575AE00, 0x5575A8CC
INTTOSTR, LSTRLASG, LSTRCAT, LSTRARRCLR = 0x5570158C, 0x55701158, 0x55701188, 0x55701148
IS_CLASS, TCOMBATUNIT_VMT = 0x557010C0, 0x55715A94
GETNAME_V = 0xF8                                    # strategic unit: GetName(eax, edx=@out)
# AoWz.exe (fixed base): the combat log's ring and window, guards as build_combatlog_dll.py
HOST_LFANEW, HOST_MINSIZE = 0x40003C, 0x20E000
RING, MAGIC = 0x60D000, 0x31474C43
WR, RD, RING_TACTICAL, SLOTS = RING + 4, RING + 8, RING + 0xC, RING + 0x20
SLOT_SZ, SLOTS_N = 128, 64
LOGWIN, MEMO_OFF, FSTRINGS_OFF, ADD_V = 0x45B2E0, 0x48, 0x118, 0x34
# AoWTCPCK.dpl
SETACTION, MAKEBLOOD, NEXTSTRIKE = 0x004236E0, 0x0040992C, 0x00409A68

# combat-object vs strategic-unit VMT slots for the AI estimate (CalculateStrikes / CalculateUnitStrikes)
COMBAT = dict(OA=0x10, OD=0x14, ATK=0x6C, DEF=0x70, RES=0x74, IMM=0x7C, PROT=0x80, ABIL=0xA8)
STRAT = dict(OA=0x20, OD=0x24, ATK=0xC0, DEF=0xC4, RES=0xCC, IMM=0xEC, PROT=0xF0, ABIL=0x148)

R_SITE = 0x557BCD98
S0_SITE, S0_VAN = 0x55767EDA, bytes.fromhex("ba76000000")
S1_SITE, S1_BACK = 0x55767F3E, 0x55767F4A
S1_VAN = bytes.fromhex("8b4b108bd58bc68b18ff5368")
S2_SITE = 0x557666FB
X_SITE, X_VAN = 0x55766806, bytes.fromhex("f6431804744a")
X_SKIP, X_ENT = 0x55766856, 0x5576680C
L_SITE, L_VAN, L_JOIN = 0x557670B9, bytes.fromhex("8a4424182c01"), 0x557670E3
RA_SITE = 0x5576964E
SH_SITE, SH_END, SH_OUT = 0x55729E34, 0x55729E57, 0x55729F0A
SH_VAN = bytes.fromhex("8b4510508b450c508b4508508b45fc8b50148bc18bce8b18ff9300010000e9b3000000")
PL_SLOT = 0x5571E344 + 0x54
DV_SITE, DV_VAN = 0x55768045, bytes.fromhex("5a5f5e5bc3")

T0_SITE, T0_VAN = 0x004096CD, bytes.fromhex("8b45fc8b40288b10ff526084c07519")
T1_SITE, T1_VAN = 0x00409726, bytes.fromhex("8b45fc8b401c8b10ff526084c0740a")
T_ATT_DOWN, T_DONE = 0x0040973F, 0x00409743
SA_SITE, SA_VAN, SA_BODY = 0x004236E0, bytes.fromhex("558bec83c4f8"), 0x004236E6
FX_SITE, FX_BACK = 0x00408BE5, 0x00408BFC
FX_VAN = bytes.fromhex("8b45fcc64031018b45fc8b402c8b4060b207e8e4aa0100")
FW_SITE, FW_READY, FW_WAIT = 0x00408C39, 0x00408C4C, 0x00408CD6
FW_VAN = bytes.fromhex("8b45fc8b402c8b4060807825000f848a000000")
TR_SITE, TR_BACK = 0x0040AF2C, 0x0040AF37
TR_VAN = bytes.fromhex("8b45fc8b401c8b10ff5260")
RT_SITE, RT_BACK = 0x0040A5B1, 0x0040A5BC
RT_VAN = bytes.fromhex("8b45fc8b40348b10ff522c")


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def dsp(d):
    return "+ %#x" % d if d >= 0 else "- %#x" % -d


def lstr(s):
    b = s.encode("latin1")
    return struct.pack("<iI", -1, len(b)) + b + b"\0"


def check_wire():
    """The log lines write into a ring and a memo owned by three other scripts; a silent mismatch
    corrupts the log window's heap.  Every constant is read back from its owner."""
    def src(name):
        return open(os.path.join(HERE, name), encoding="utf-8").read()
    dll, exe, rpl = src("build_combatlog_dll.py"), src("build_combatlog_exe.py"), src("build_replaylog.py")
    want = [(dll, r"RING=0x([0-9A-Fa-f]+); WR=RING\+4; RD=RING\+8; SLOTS=RING\+0x20", RING),
            (dll, r"MAGIC=0x([0-9A-Fa-f]+)", MAGIC),
            (exe, r"RING_TACTICAL\s*=\s*0x([0-9A-Fa-f]+)", RING_TACTICAL),
            (rpl, r"GVAR_INSTANCE=0x([0-9A-Fa-f]+)", LOGWIN),
            (rpl, r"MEMO_OFF=0x([0-9A-Fa-f]+); FSTRINGS_OFF=0x([0-9A-Fa-f]+); ADD_V=0x([0-9A-Fa-f]+)",
             (MEMO_OFF, FSTRINGS_OFF, ADD_V))]
    for text, pat, val in want:
        m = re.search(pat, text)
        got = tuple(int(g, 16) for g in m.groups()) if m else None
        if got != (val if isinstance(val, tuple) else (val,)):
            sys.exit("ABORT: combat-log wire constant drifted (%s): %r" % (pat, got))
    m = re.search(r"RING_SLOTS\s*=\s*(\d+);\s*SLOT_SZ\s*=\s*(\d+)", exe)
    if not m or (int(m.group(1)), int(m.group(2))) != (SLOTS_N, SLOT_SZ):
        sys.exit("ABORT: combat-log ring geometry drifted")


# --- AoWEPACK caves --------------------------------------------------------------------------
def build_roll(va):
    """EAX = the strike CA, EDX = the struck unit.  Draws once, always; keeps EBX/ESI/EDI/EBP."""
    return asm(f"""
        push ebx
        push esi
        mov  ebx, eax
        mov  esi, edx
        mov  eax, {DIE}
        call {RANDINT:#x}
        push eax
        cmp  byte ptr [ebx + 0x10], 0
        je   r_skip
        mov  eax, esi
        mov  edx, {ABIL_ID:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        je   r_skip
        pop  eax
        inc  eax
        shl  eax, 5
        or   byte ptr [ebx + 0x18], al
        pop  esi
        pop  ebx
        ret
    r_skip:
        pop  eax
        pop  esi
        pop  ebx
        ret
    """, va)


def build_s0(va, at):
    """Melee round side 0: ESI = CA, EBX = the round, [round+0x14] = the defender.  Returns EDX =
    0x76, the LifeStealing query this call displaced."""
    return asm(f"""
        mov  eax, esi
        mov  edx, dword ptr [ebx + 0x14]
        call {at['cave_roll']:#x}
        mov  edx, 0x76
        ret
    """, va)


def build_s1(va, at):
    """Melee round side 1: the displaced Generate call, then the roll.  [round+0x10] is struck."""
    return asm(f"""
        mov  ecx, dword ptr [ebx + 0x10]
        mov  edx, ebp
        mov  eax, esi
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0x68]
        mov  eax, esi
        mov  edx, dword ptr [ebx + 0x10]
        call {at['cave_roll']:#x}
        jmp  {S1_BACK:#x}
    """, va)


def build_s2(va, at):
    """AoWE.CreateStrikeCA after Generate: EDI = CA, ESI = the struck unit, EBP = the striker."""
    return asm(f"""
        call {SETDEFENSIVE:#x}
        mov  eax, edi
        mov  edx, esi
        jmp  {at['cave_roll']:#x}
    """, va)


def build_apply(va, at):
    """TStrikeCA.Execute: EBX = CA, EDI = striker, ESI = struck unit; EBP is free (vanilla uses it
    as VMT scratch).  Ends in the displaced Entangle Strike test."""
    return asm(f"""
        mov  byte ptr [ebx + 0x16], 0
        movzx ebp, byte ptr [ebx + 0x18]
        shr  ebp, 5
        je   a_out
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   a_out
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x7c]
        test al, {PHYS:#x}
        jne  a_out
        mov  eax, edi
        mov  edx, {EMBRITTLED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        push eax
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x80]
        pop  ecx
        test al, {PHYS:#x}
        jne  a_halve
        test cl, cl
        je   a_deal
        lea  ebp, [ebp + ebp*2 + 1]
        jmp  a_shr
    a_halve:
        test cl, cl
        jne  a_deal
        inc  ebp
    a_shr:
        shr  ebp, 1
    a_deal:
        mov  eax, ebp
        mov  byte ptr [ebx + 0x16], al
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   a_nodealer
        mov  ecx, ebp
        mov  edx, edi
        mov  eax, esi
        mov  ebp, dword ptr [eax]
        call dword ptr [ebp + 0x108]
        jmp  a_log
    a_nodealer:
        mov  edx, ebp
        mov  eax, edi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x124]
    a_log:
        mov  eax, edi
        movzx edx, byte ptr [ebx + 0x16]
        xor  ecx, ecx
        call {at['cave_line']:#x}
    a_out:
        test byte ptr [ebx + 0x18], 4
        je   {X_SKIP:#x}
        jmp  {X_ENT:#x}
    """, va)


def build_loop(va, at):
    """Auto-resolve melee loop: [esp+8] = defender, EBP = attacker, [esp+4] = the stop flag."""
    return asm(f"""
        mov  eax, dword ptr [esp + 8]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   l_stop
        mov  eax, ebp
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   l_stop
        mov  byte ptr [esp + 4], 0
        jmp  {L_JOIN:#x}
    l_stop:
        mov  byte ptr [esp + 4], 1
        jmp  {L_JOIN:#x}
    """, va)


def build_rnd(va, at):
    """Round Attack's follow-up blows, auto-resolve: EAX = the attacker, EDX = target, CL = 0.
    A fallen attacker builds no strike (NIL, which the caller tests)."""
    return asm(f"""
        push eax
        push ecx
        push edx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        pop  edx
        pop  ecx
        pop  eax
        je   n_none
        jmp  {CREATESTRIKE:#x}
    n_none:
        xor  eax, eax
        ret
    """, va)


def build_show(va, at):
    """TDamageCA.ShowObject, striker branch: EBX = CA, ECX = the object, ESI = [ebp+0x14],
    [ebp-4] = the viewer.  The striker's own draw, then the cut's number over it."""
    return asm(f"""
        push ebx
        push dword ptr [ebp + 0x10]
        push dword ptr [ebp + 0xc]
        push dword ptr [ebp + 8]
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [eax + 0x14]
        mov  eax, ecx
        mov  ecx, esi
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0x100]
        pop  ebx
        movzx eax, byte ptr [ebx + 0x16]
        test eax, eax
        je   h_out
        mov  edx, dword ptr [ebp - 4]
        movzx ecx, byte ptr [edx + 0xc]
        cmp  ecx, 5
        jb   h_cap
        mov  ecx, 5
    h_cap:
        cmp  dword ptr [edx + 0x14], ecx
        jl   h_out
        push eax
        mov  ax, {PHYS:#x}
        call {DMGTYPE:#x}
        push eax
        mov  ecx, dword ptr [ebp + 8]
        mov  edx, dword ptr [ebp + 0xc]
        mov  eax, dword ptr [ebp + 0x10]
        call {SHOWICON:#x}
    h_out:
        jmp  {SH_OUT:#x}
    """, va)


def build_play(va, at):
    """TStrikeCA VMT +0x54: EAX = CA, EDX = the viewer.  Play, then on the action's trigger tick
    (TDamageCA.Play executes when [v+0x14] == min([v+0xC], 5)) the cut's line into the memo."""
    return asm(f"""
        push ebx
        push esi
        mov  ebx, eax
        mov  esi, edx
        call {STRIKE_PLAY:#x}
        push eax
        movzx ecx, byte ptr [esi + 0xc]
        cmp  ecx, 5
        jb   p_cap
        mov  ecx, 5
    p_cap:
        cmp  dword ptr [esi + 0x14], ecx
        jne  p_out
        movzx edx, byte ptr [ebx + 0x16]
        test edx, edx
        je   p_out
        push edx
        mov  eax, dword ptr [esi + 8]
        mov  eax, dword ptr [eax + 0xc]
        movzx edx, byte ptr [ebx + 0xd]
        call {FINDID:#x}
        pop  edx
        test eax, eax
        je   p_out
        mov  ecx, 1
        call {at['cave_line']:#x}
    p_out:
        pop  eax
        pop  esi
        pop  ebx
        ret
    """, va)


def build_line(va, at):
    """EAX = the cut striker's combat object, EDX = the cut, ECX = sink (0 = the live ring, manual
    combat only; 1 = the replay's log memo).  Builds "<name> is cut by Razor Plate for N damage"."""
    def body(d_tcu, d_cut, d_dmg, d_unk):
        return f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x18
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp - 0x10], eax
        mov  dword ptr [ebp - 0x14], edx
        mov  dword ptr [ebp - 0x18], ecx
        xor  eax, eax
        mov  dword ptr [ebp - 4], eax
        mov  dword ptr [ebp - 8], eax
        mov  dword ptr [ebp - 0xc], eax
        """, f"""
        pop  edi
        mov  eax, dword ptr [{HOST_LFANEW:#x}]
        cmp  dword ptr [eax + 0x400050], {HOST_MINSIZE:#x}
        jb   g_out
        cmp  dword ptr [{RING:#x}], {MAGIC:#x}
        jne  g_out
        cmp  dword ptr [ebp - 0x18], 0
        jne  g_name
        cmp  dword ptr [{RING_TACTICAL:#x}], 1
        jne  g_out
        mov  eax, dword ptr [{WR:#x}]
        sub  eax, dword ptr [{RD:#x}]
        cmp  eax, {SLOTS_N - 1}
        jae  g_out
    g_name:
        mov  eax, dword ptr [ebp - 0x10]
        lea  edx, [edi {dsp(d_tcu)}]
        call {IS_CLASS:#x}
        test al, al
        je   g_unk
        mov  eax, dword ptr [ebp - 0x10]
        mov  eax, dword ptr [eax + 0x4c]
        test eax, eax
        je   g_unk
        lea  edx, [ebp - 8]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {GETNAME_V:#x}]
        jmp  g_text
    g_unk:
        lea  eax, [ebp - 8]
        lea  edx, [edi {dsp(d_unk)}]
        call {LSTRLASG:#x}
    g_text:
        lea  eax, [ebp - 4]
        mov  edx, dword ptr [ebp - 8]
        call {LSTRLASG:#x}
        lea  eax, [ebp - 4]
        lea  edx, [edi {dsp(d_cut)}]
        call {LSTRCAT:#x}
        mov  eax, dword ptr [ebp - 0x14]
        lea  edx, [ebp - 0xc]
        call {INTTOSTR:#x}
        lea  eax, [ebp - 4]
        mov  edx, dword ptr [ebp - 0xc]
        call {LSTRCAT:#x}
        lea  eax, [ebp - 4]
        lea  edx, [edi {dsp(d_dmg)}]
        call {LSTRCAT:#x}
        mov  eax, dword ptr [ebp - 4]
        test eax, eax
        je   g_clean
        cmp  dword ptr [ebp - 0x18], 0
        jne  g_memo
        mov  ecx, dword ptr [eax - 4]
        cmp  ecx, {SLOT_SZ - 1}
        jbe  g_len
        mov  ecx, {SLOT_SZ - 1}
    g_len:
        mov  edx, dword ptr [{WR:#x}]
        and  edx, {SLOTS_N - 1}
        shl  edx, {SLOT_SZ.bit_length() - 1}
        add  edx, {SLOTS:#x}
        mov  byte ptr [edx], cl
        mov  esi, eax
        lea  edi, [edx + 1]
        cld
        rep  movsb
        mov  eax, dword ptr [{WR:#x}]
        inc  eax
        mov  dword ptr [{WR:#x}], eax
        jmp  g_clean
    g_memo:
        mov  eax, dword ptr [{LOGWIN:#x}]
        test eax, eax
        je   g_clean
        mov  eax, dword ptr [eax + {MEMO_OFF:#x}]
        test eax, eax
        je   g_clean
        mov  eax, dword ptr [eax + {FSTRINGS_OFF:#x}]
        test eax, eax
        je   g_clean
        mov  edx, dword ptr [ebp - 4]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {ADD_V:#x}]
    g_clean:
        lea  eax, [ebp - 0xc]
        mov  edx, 3
        call {LSTRARRCLR:#x}
    g_out:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
        """

    def emit(d_tcu, d_cut, d_dmg, d_unk):
        head, tail = body(d_tcu, d_cut, d_dmg, d_unk)
        code = bytearray(asm(head, va))
        anchor = va + len(code) + 5
        code += b"\xE8\x00\x00\x00\x00"
        code += asm(tail, anchor)
        return code, anchor

    big = 0x10000                                   # forces disp32 in the sizing pass
    code, anchor = emit(big, big, big, big)
    while len(code) % 4:
        code += b"\x90"
    lits, pool = {}, b""
    for k, s in (("cut", LINE_CUT), ("dmg", LINE_DMG), ("unk", LINE_UNK)):
        lits[k] = va + len(code) + len(pool) + 8    # the chars, past refcount and length
        pool += lstr(s)
        while len(pool) % 4:
            pool += b"\0"
    final, anchor2 = emit(TCOMBATUNIT_VMT - anchor, lits["cut"] - anchor, lits["dmg"] - anchor,
                          lits["unk"] - anchor)
    assert anchor2 == anchor and len(final) <= len(code), "cave_line layout moved between passes"
    final += b"\x90" * (len(code) - len(final))
    return bytes(final) + pool


def dv_body(M, tag):
    """One CalculateDV pass over the round's strikes with slot set M (combat or strategic).
    EDI = the round.  Locals at [ebp-4] A, [ebp-8] D, [ebp-0xC]/[ebp-0x10] A/D carry Razor Plate,
    [ebp-0x14]/[ebp-0x18] A's/D's expected cut in tenths, [ebp-0x1C] the strike index."""
    return f"""
        mov  eax, dword ptr [edi + {M['OA']:#x}]
        mov  dword ptr [ebp - 4], eax
        mov  eax, dword ptr [edi + {M['OD']:#x}]
        mov  dword ptr [ebp - 8], eax
        mov  eax, dword ptr [ebp - 4]
        mov  edx, {ABIL_ID:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {M['ABIL']:#x}]
        movzx eax, al
        mov  dword ptr [ebp - 0xc], eax
        mov  eax, dword ptr [ebp - 8]
        mov  edx, {ABIL_ID:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {M['ABIL']:#x}]
        movzx eax, al
        mov  dword ptr [ebp - 0x10], eax
        or   eax, dword ptr [ebp - 0xc]
        je   {tag}_done
        mov  eax, dword ptr [ebp - 4]
        call {tag}_ecut
        mov  dword ptr [ebp - 0x14], eax
        mov  eax, dword ptr [ebp - 8]
        call {tag}_ecut
        mov  dword ptr [ebp - 0x18], eax
        xor  eax, eax
        mov  dword ptr [ebp - 0x1c], eax
    {tag}_loop:
        mov  eax, dword ptr [ebp - 0x1c]
        cmp  eax, dword ptr [edi + 4]
        jge  {tag}_done
        lea  edx, [eax + eax*4]
        mov  ebx, dword ptr [edi + 0xc]
        lea  ebx, [ebx + edx*4]
        cmp  byte ptr [ebx + 0xc], 0
        jne  {tag}_s1
        cmp  dword ptr [ebp - 0x10], 0
        je   {tag}_next
        mov  esi, dword ptr [ebp - 0x14]
        test esi, esi
        je   {tag}_next
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [ebp - 8]
        mov  cx, word ptr [edi + 0x30]
        call {tag}_pland
        imul eax, esi
        mov  ecx, 10
        cdq
        idiv ecx
        add  dword ptr [edi + 0x1c], eax
        jmp  {tag}_next
    {tag}_s1:
        cmp  dword ptr [ebp - 0xc], 0
        je   {tag}_next
        mov  esi, dword ptr [ebp - 0x18]
        test esi, esi
        je   {tag}_next
        mov  eax, dword ptr [ebp - 8]
        mov  edx, dword ptr [ebp - 4]
        mov  cx, word ptr [edi + 0x32]
        call {tag}_pland
        imul eax, esi
        mov  ecx, 10
        cdq
        idiv ecx
        add  dword ptr [edi + 0x18], eax
    {tag}_next:
        inc  dword ptr [ebp - 0x1c]
        jmp  {tag}_loop
    {tag}_ecut:
        push ebx
        mov  ebx, eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {M['IMM']:#x}]
        test al, {PHYS:#x}
        jne  {tag}_ezero
        mov  eax, ebx
        mov  edx, {EMBRITTLED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {M['ABIL']:#x}]
        push eax
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {M['PROT']:#x}]
        pop  ecx
        test al, {PHYS:#x}
        jne  {tag}_eprot
        mov  eax, 30
        test cl, cl
        je   {tag}_eout
        mov  eax, 48
        jmp  {tag}_eout
    {tag}_eprot:
        mov  eax, 18
        test cl, cl
        je   {tag}_eout
        mov  eax, 30
        jmp  {tag}_eout
    {tag}_ezero:
        xor  eax, eax
    {tag}_eout:
        pop  ebx
        ret
    {tag}_pland:
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        push ecx
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {M['DEF']:#x}]
        movsx eax, al
        push eax
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {M['RES']:#x}]
        movsx eax, al
        push eax
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {M['IMM']:#x}]
        push eax
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {M['PROT']:#x}]
        push eax
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {M['ATK']:#x}]
        movsx eax, al
        add  eax, dword ptr [ebx]
        mov  edx, 1
        mov  ecx, dword ptr [esp + 0x10]
        call {STATS_DV:#x}
        pop  ecx
        pop  edi
        pop  esi
        ret
    {tag}_done:
    """


def build_dv(va, at):
    """TMeleeRound.CalculateDV epilogue: EDI = the round; EBX/ESI/EDX are popped next.  Prediction
    mode when [round+0x10] is nil, exactly as vanilla's own test."""
    return asm(f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x20
        cmp  dword ptr [edi + 0x10], 0
        je   v_strat
        {dv_body(COMBAT, 'c')}
        jmp  v_out
    v_strat:
        {dv_body(STRAT, 's')}
    v_out:
        mov  esp, ebp
        pop  ebp
        pop  edx
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


def build_reg(va, at):
    code = bytearray(asm(f"call {REGISTER:#x}", va))
    at_ = va + len(code)
    code += b"\xE8\x00\x00\x00\x00"
    anchor = at_ + 5
    code += asm("pop eax", anchor)
    fix = len(code)
    code += b"\x8D\x90" + b"\0\0\0\0"                  # lea edx,[eax+disp32] -> the name chars
    code += asm(f"""
        mov  cx, {MASK:#x}
        mov  eax, {ABIL_ID:#x}
        call {CEA:#x}
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER:#x}
        ret
    """, va + len(code))
    while len(code) % 4:
        code += b"\x90"
    lit = va + len(code) + 8
    code += lstr(NAME)
    struct.pack_into("<i", code, fix + 2, lit - anchor)
    return bytes(code)


def layout(slot, specs):
    """Two passes: sizes first, then every cave knows every other cave's address."""
    def place(at):
        caves, va = [], slot[0]
        for name, gen in specs:
            blob = gen(va, at)
            caves.append((name, va, blob))
            va = (va + len(blob) + 0xF) & ~0xF
        assert va <= slot[1], "caves overflow the slot"
        return caves
    guess = {n: slot[0] for n, _g in specs}
    first = place(guess)
    at = {n: v for n, v, _b in first}
    caves = place(at)
    assert [v for _n, v, _b in caves] == [at[n] for n, _g in specs], "layout moved between passes"
    return at, caves


E_SPECS = [("cave_roll", lambda va, at: build_roll(va)), ("cave_s0", build_s0), ("cave_s1", build_s1),
           ("cave_s2", build_s2), ("cave_apply", build_apply), ("cave_loop", build_loop),
           ("cave_rnd", build_rnd), ("cave_show", build_show), ("cave_play", build_play),
           ("cave_line", build_line), ("cave_dv", build_dv), ("cave_reg", build_reg)]


# --- AoWTCPCK caves --------------------------------------------------------------------------
def build_tc(va, at):
    """LastMove state 4, after ExecuteCombatAction: [ebp-4] = the TE, +0x1C attacker, +0x28
    defender, +0x34 the strike.  ESI/EDI are free here (LastMove saves them and keeps nothing in
    them).  A surviving cut striker flinches and bleeds; then vanilla's three endings, with an
    attacker that took the cut keeping its flinch when the round ends on this strike."""
    return asm(f"""
        mov  eax, dword ptr [ebp - 4]
        xor  esi, esi
        mov  ecx, dword ptr [eax + 0x34]
        movzx edx, byte ptr [ecx + 0x16]
        test edx, edx
        je   c_route
        test byte ptr [ecx + 0xc], 1
        mov  edi, dword ptr [eax + 0x1c]
        je   c_who
        mov  edi, dword ptr [eax + 0x28]
    c_who:
        mov  ecx, dword ptr [edi + 0x60]
        test ecx, ecx
        je   c_route
        push edx
        mov  eax, ecx
        mov  dl, 4
        call {SETACTION:#x}
        pop  edx
        mov  eax, edi
        call {MAKEBLOOD:#x}
        mov  eax, dword ptr [ebp - 4]
        cmp  edi, dword ptr [eax + 0x1c]
        jne  c_route
        mov  esi, edi
    c_route:
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x1c]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   {T_ATT_DOWN:#x}
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x28]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        jne  c_next
        mov  eax, dword ptr [ebp - 4]
        mov  byte ptr [eax + 0x31], 1
        mov  dl, 7
        test esi, esi
        je   c_end
        mov  dl, 4
    c_end:
        mov  eax, dword ptr [eax + 0x1c]
        mov  eax, dword ptr [eax + 0x60]
        call {SETACTION:#x}
        jmp  {T_DONE:#x}
    c_next:
        mov  eax, dword ptr [ebp - 4]
        call {NEXTSTRIKE:#x}
        test esi, esi
        je   c_done
        mov  eax, dword ptr [ebp - 4]
        cmp  byte ptr [eax + 0x31], 1
        jne  c_done
        mov  eax, dword ptr [eax + 0x1c]
        mov  eax, dword ptr [eax + 0x60]
        mov  dl, 4
        call {SETACTION:#x}
    c_done:
        jmp  {T_DONE:#x}
    """, va)


def build_sa(va, at):
    """SetAction(EAX = HS, DL = action): a dead unit's HS is freed and its pointer nilled, so a nil
    HS is a no-op."""
    return asm(f"""
        test eax, eax
        je   z_ret
        push ebp
        mov  ebp, esp
        add  esp, -8
        jmp  {SA_BODY:#x}
    z_ret:
        ret
    """, va)


def build_fsx(va, at):
    """Free swing, after the blow: state 1; a surviving swinger flinches and bleeds if cut, else
    vanilla's action 7; a swinger the cut killed has no HS left to touch."""
    return asm(f"""
        mov  eax, dword ptr [ebp - 4]
        mov  byte ptr [eax + 0x31], 1
        mov  eax, dword ptr [eax + 0x2c]
        mov  ecx, dword ptr [eax + 0x60]
        test ecx, ecx
        je   f_out
        mov  edx, dword ptr [ebp - 4]
        mov  edx, dword ptr [edx + 0x34]
        movzx edx, byte ptr [edx + 0x16]
        test edx, edx
        je   f_idle
        push eax
        push edx
        mov  eax, ecx
        mov  dl, 4
        call {SETACTION:#x}
        pop  edx
        pop  eax
        call {MAKEBLOOD:#x}
        jmp  f_out
    f_idle:
        mov  eax, ecx
        mov  dl, 7
        call {SETACTION:#x}
    f_out:
        jmp  {FX_BACK:#x}
    """, va)


def build_fsw(va, at):
    """Free swing, state 1: wait for the swinger's HS, or not at all once the cut freed it."""
    return asm(f"""
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x2c]
        mov  eax, dword ptr [eax + 0x60]
        test eax, eax
        je   {FW_READY:#x}
        cmp  byte ptr [eax + 0x25], 0
        je   {FW_WAIT:#x}
        jmp  {FW_READY:#x}
    """, va)


def build_tch(va, at):
    """Touch retaliation, after the blow: the retaliator ([TE+0x28]) flinches and bleeds if cut and
    standing, then the displaced toucher test."""
    return asm(f"""
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [eax + 0x34]
        movzx edx, byte ptr [edx + 0x16]
        test edx, edx
        je   t_go
        mov  eax, dword ptr [eax + 0x28]
        mov  ecx, dword ptr [eax + 0x60]
        test ecx, ecx
        je   t_go
        push eax
        push edx
        mov  eax, ecx
        mov  dl, 4
        call {SETACTION:#x}
        pop  edx
        pop  eax
        call {MAKEBLOOD:#x}
    t_go:
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x1c]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        jmp  {TR_BACK:#x}
    """, va)


def build_rat(va, at):
    """Round Attack sweep, after a blow: blood on a surviving cut attacker (no flinch -- it would
    reset the sweep), then the displaced CA release."""
    return asm(f"""
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [eax + 0x34]
        movzx edx, byte ptr [edx + 0x16]
        test edx, edx
        je   b_go
        mov  eax, dword ptr [eax + 0x1c]
        cmp  dword ptr [eax + 0x60], 0
        je   b_go
        call {MAKEBLOOD:#x}
    b_go:
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x34]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
        jmp  {RT_BACK:#x}
    """, va)


T_SPECS = [("cave_tc", build_tc), ("cave_sa", build_sa), ("cave_fsx", build_fsx),
           ("cave_fsw", build_fsw), ("cave_tch", build_tch), ("cave_rat", build_rat)]

E_AT, E_CAVES = layout(E_SLOT, E_SPECS)
T_AT, T_CAVES = layout(T_SLOT, T_SPECS)

E_HOOKS = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, E_AT["cave_reg"])),
           (S0_SITE, S0_VAN, call_to(S0_SITE, E_AT["cave_s0"])),
           (S1_SITE, S1_VAN, jmp_to(S1_SITE, E_AT["cave_s1"], len(S1_VAN))),
           (S2_SITE, call_to(S2_SITE, SETDEFENSIVE), call_to(S2_SITE, E_AT["cave_s2"])),
           (X_SITE, X_VAN, jmp_to(X_SITE, E_AT["cave_apply"], len(X_VAN))),
           (L_SITE, L_VAN, jmp_to(L_SITE, E_AT["cave_loop"], len(L_VAN))),
           (RA_SITE, call_to(RA_SITE, CREATESTRIKE), call_to(RA_SITE, E_AT["cave_rnd"])),
           (SH_SITE, SH_VAN, jmp_to(SH_SITE, E_AT["cave_show"], len(SH_VAN))),
           (PL_SLOT, struct.pack("<I", STRIKE_PLAY), struct.pack("<I", E_AT["cave_play"])),
           (DV_SITE, DV_VAN, jmp_to(DV_SITE, E_AT["cave_dv"], len(DV_VAN)))]
E_INTERIOR = [(S0_SITE, S0_SITE + 5, 0x55767E68, 0x55767F51),
              (S1_SITE, S1_BACK, 0x55767E68, 0x55767F51),
              (S2_SITE, S2_SITE + 5, 0x557665E4, 0x5576670C),
              (X_SITE, X_SITE + 6, 0x55766738, 0x5576685B),
              (L_SITE, L_SITE + 6, 0x55766FCC, 0x5576710F),
              (RA_SITE, RA_SITE + 5, 0x55769458, 0x557696A0),
              (SH_SITE, SH_END, 0x55729E1C, 0x55729F14),
              (DV_SITE, DV_SITE + 5, 0x55767F58, 0x5576804A)]

LASTMOVE = (0x004090B5, 0x00409896)          # TCMeleeMoveTE.LastMove past its jump table
DEFAULTMOVE = (0x004088C2, 0x00408F44)       # TCombatMoveTE.DefaultMove past its jump table
TOUCHMOVE = (0x00409CEB, 0x0040B096)         # TCAbTouchMoveTE.LastMove past its jump table
T_HOOKS = [(T0_SITE, T0_VAN, jmp_to(T0_SITE, T_AT["cave_tc"], len(T0_VAN))),
           (T1_SITE, T1_VAN, jmp_to(T1_SITE, T_AT["cave_tc"], len(T1_VAN))),
           (SA_SITE, SA_VAN, jmp_to(SA_SITE, T_AT["cave_sa"], len(SA_VAN))),
           (FX_SITE, FX_VAN, jmp_to(FX_SITE, T_AT["cave_fsx"], len(FX_VAN))),
           (FW_SITE, FW_VAN, jmp_to(FW_SITE, T_AT["cave_fsw"], len(FW_VAN))),
           (TR_SITE, TR_VAN, jmp_to(TR_SITE, T_AT["cave_tch"], len(TR_VAN))),
           (RT_SITE, RT_VAN, jmp_to(RT_SITE, T_AT["cave_rat"], len(RT_VAN)))]
T_INTERIOR = [(T0_SITE, T0_SITE + 15) + LASTMOVE, (T1_SITE, T1_SITE + 15) + LASTMOVE,
              (SA_SITE, SA_SITE + 6, 0x004236E0, 0x00423741),
              (FX_SITE, FX_BACK) + DEFAULTMOVE, (FW_SITE, FW_READY) + DEFAULTMOVE,
              (TR_SITE, TR_BACK) + TOUCHMOVE, (RT_SITE, RT_BACK) + TOUCHMOVE]


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def check_id():
    """0xBD must be ours alone: no CreateEnhancementAbility idiom outside our slot registers it,
    and ability_names gives it no other name.  Higher ids are other abilities, not a clash."""
    module(EPACK, 0x55700000)
    d = open(P.TARGET, "rb").read()
    _e, secs = P.sections(d)
    vs, sva, rs, ra = secs[0]
    used = []
    for i in range(ra, ra + rs - 5):
        if d[i] == 0xE8:
            src = P.IMAGE_BASE + sva + (i - ra)
            if src + 5 + struct.unpack_from("<i", d, i + 1)[0] == CEA:
                for k in range(5, 30):
                    if d[i - k] == 0xB8:
                        used.append((struct.unpack_from("<I", d, i - k + 1)[0], src))
                        break
    lo, hi = E_SLOT
    other = [(i, src) for i, src in used if i < 0x100 and not lo <= src < hi]
    clash = [u for u in other if u[0] == ABIL_ID]
    if clash:
        sys.exit("ABORT: CreateEnhancementAbility at %08X also registers %#x -- re-derive ABIL_ID"
                 % (clash[0][1], ABIL_ID))
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    import pfs, ability_names
    keys = {rid - 10 for rid, _b in pfs.load("ability.pfs")[0]}
    named = ability_names.names()                     # constructor scan + MODDED
    if named.get(ABIL_ID, NAME) != NAME:
        sys.exit("ABORT: ability_names gives %#x to %r -- re-derive ABIL_ID" % (ABIL_ID, named[ABIL_ID]))
    print("  id %#x ours alone (highest other CreateEnhancementAbility id %#x, highest other named id "
          "%#x); Ability.pfs record %s" % (ABIL_ID, max(i for i, _s in other),
                                           max(k for k in named if k != ABIL_ID),
                                           "present" if ABIL_ID in keys else "absent"))


def go(argv):
    module(EPACK, 0x55700000)
    run("build_razorplate [AoWEPACK]", E_HOOKS, E_CAVES, E_SLOT, E_INTERIOR, argv,
        reloc_ok=(PL_SLOT,))
    module(TCPCK, 0x00400000)
    run("build_razorplate [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, T_INTERIOR, argv)


if __name__ == "__main__":
    check_wire()
    check_id()
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])   # both modules verify first
        print("\n" + "=" * 60)
    go(argv)
