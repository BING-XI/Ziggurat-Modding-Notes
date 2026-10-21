#!/usr/bin/env python3
r"""
build_heroicchoice.py -- a HEROIC unit chooses one of its type's options.  AoWEPACK.dpl + AoWz.exe.
Owner's design 2026-10-20.

    Heroic medal   XP >= tier*30, double gold (build_copper_medal.py's HEROIC; not a rank, so no
                   medal abilities of its own).  "Heroic" here is GetNextRankExperience (VMT +0x164)
                   == 0, so the ladder has one definition, in that script.
    Heroic bonus   every heroic unit, options or not: HEROIC_TOTALS, ATK +4 DEF +2 DAM +3 RES +4
                   HP +10 MV +4, in place of gold's.  GetRank stays gold, so the caves add the
                   difference, reading gold's figures at run time (see STATS).
    Options        up to three per unit type: an ability bundle + six signed stat deltas
                   (build_heroicchoice_data.py; authored on the editor's Heroic 1-3 tabs,
                   build_deved_heroicchoice.py).  Layout: heroicchoice.py.
    The unit       TUnit +0x3F (vanilla dead byte): bits 0-1 the option taken, bit 7 "announced".
                   Saved as tag 0x24.  A taken option is permanent.

WHO CHOOSES, AND WHEN -- at the start of the owner's turn (TUnit.NewTurn), as heroes level up
    one option present   granted outright, no prompt
    AI owner             a uniform draw over the present options: TAoWHSMap.Random(map, n).
                         P1 SYNCED DRAW: the host, NewTurn, draws nothing itself and the result is
                         replicated unit state; vanilla's own AI level-up chooser
                         (THero.ExecuteUpgradeHeroAI, called from THero.NewTurn) is in the SYNC
                         list.  Outside combat, so System.RandSeed needs no save/restore.
    human owner          a THeroUpgradeEventLog marked +0x1C = +0x1D = 0xFF (old/new level, both
                         streamed) goes into the owner's logbook only.  The first one pops up
                         under the player's hero-level-up popup setting; it reopens from the log
                         until an option is taken; when the log trims it (3 days) a fresh one is
                         added quietly.  Picking sends THeroUpgradeTE (+0x15 = the option) through
                         the token manager, so every peer applies it in THeroUpgradeTE.Execute.
    day 1                TUnit.NewDay's day-1 rebuild (SetAbCount 0 + medal regrant) re-grants the
                         taken option's abilities, so a campaign carry-over keeps them.

THE ALWAYS SET (owner, 2026-10-20) -- every heroic unit also gains its type's Always owner
    (TUnitResource +0x74), independent of the options: at the start of the owner's turn a heroic
    unit whose state lacks bit 0x40 and whose type has an Always set gets UpdateDefaultAbilities
    + apply_choice's refresh, and bit 0x40 is set; no prompt, no choice, AI and human alike.  The
    day-1 rebuild re-grants it to units with bit 0x40.  Deterministic from unit state, no draw.
    cave_always_turn / cave_always_day wrap cave_newturn / cave_newday, appended after cave_rw so
    every pinned entry below (and RNG_SITE) is where it was.

APPLYING OPTION k    unit+0x3F |= k; UpdateDefaultAbilities(unit, option owner) and the Leadership
    aura refresh build_leadership_aura.py uses (TArmy.UpdateFormation on [unit+4]); Changed; current
    HP and moves re-set through SetHitPoints / SetMovePoints, which clamp to the new maxima.
STATS               the heroic increment (total - gold) and the taken option's deltas, both read
    live.  ATK/DEF/RES/DAM: added to TUnit.Changed's ability-modifier cache (+0x44..+0x47), before
    the getters' own clamps; gold = the stat tables' entry 3 (0x558E83C4.., build_copper_medal.py).
    TUnit.SetExperience calls Changed after every XP change, so the bonus lands as the unit crosses
    tier*30.  HP/MV: gold = 3 * the per-rank multiplier imm8 (0x5580BE27 / 0x5580BE12,
    build_medal_hpmv.py).  HP after GetHits, MV after GetMoves (build_haste_moves.py's wrapper);
    when either moved the value, floor 1, ceiling = the HP cap (read from 0x55818088) / 127.

DLL HOOKS (dwords are VMT slots; their .reloc entries are kept)
    TUnit +0x090 Changed    0x55710D3C  0x55782B34 -> cave_changed
    TUnit +0x0D0 GetHits    0x55710D7C  0x55782B68 -> cave_hits
    TUnit +0x0D4 GetMoves   0x55710D80  0x558A0000 (build_haste_moves.py) -> cave_moves
    TUnit +0x138 NewDay     0x55710DE4  0x55782C98 -> cave_always_day (-> cave_newday)
    TUnit +0x13C NewTurn    0x55710DE8  0x5580D940 (build_spellcast_multiturn.py)
                                                   -> cave_always_turn (-> cave_newturn)
    THeroUpgradeEventLog +0x4C GetText  0x55711BD4  0x55785558 -> cave_evtext
    THeroUpgradeEventLog +0x70 Execute  0x55711BF8  0x5578566C -> cave_evexec
    THeroUpgradeTE       +0x4C Execute  0x5571196C  0x55785450 -> cave_teexec
    TUnit.ReadWrite body    0x55782D13  15 B (tag 7, XP) -> call cave_rw + 10 nop (tag 7, then tag
                            0x24 for +0x3F).  Inside the vanilla body, so build_spellcast_persist.py's
                            VMT wrapper around ReadWrite is untouched.
    Nothing calls any of these methods directly; no class inherits from TUnit, THeroUpgradeEventLog
    or THeroUpgradeTE.  Slot 0x558B1000-0x558B1FFF, exclusive.  PIC (get_delta + disp32).

EXE HOOK
    0x0044F1F3  TMapEvents.TheMapExecuteEventLog's `call THeroUpgradeDlg.Setup` -> cave_dispatch:
                a marked event opens the choice window, anything else goes on to the hero dialog.
    The window is a CLONE of TPartyJoinDlg: its VMT block [V-0x40, V+0x28) copied, its own method
    table, everything else shared -- including the class name, so TDataModule.Create loads the
    donor's own DFM (no resource added).  Created once, with Owner nil (two components named
    PartyJoinDlg under Application would collide).  The DFM's handler names bind through the
    clone's method table: Left/Middle/Right = the options in order (two options: Left and Right),
    Close = later; Create, Destroy, DlgHide (the donor's close routine 0x437A18: fires the event
    callback, releases the event) and DlgKeyDown (Esc) stay the donor's.  FaceFramePreDraw re-runs
    the donor's prologue and joins its body after the event check (0x4380DB), which would call a
    party-event method the level-up event does not have; U1PreDraw / U1MouseDown are no-ops (the
    unit strip is hidden).  Slot 0x0062C400-0x0062CFFF, exclusive (`.hcol` RWX).

ENTRY POINTS (asserted against the layout on every run; RNG_SITE is the one draw)
    DLL  get_delta 0x558B1000  opt_present 0x558B1070  pending_count 0x558B10C0
         nth_option 0x558B1120  apply_choice 0x558B1150  raise_event 0x558B11D0
         cave_hits 0x558B12B0  cave_moves 0x558B1320  cave_changed 0x558B1390  cave_newday 0x558B1410
         cave_newturn 0x558B1460 (RNG_SITE 0x558B14C4: P1 SYNCED DRAW, host TUnit.NewTurn)
         cave_evexec 0x558B14F0  cave_evtext 0x558B15B0  cave_teexec 0x558B1620  cave_rw 0x558B16B0
         always_any 0x558B16D0  grant_always 0x558B1700  cave_always_turn 0x558B17A0
         cave_always_day 0x558B17C0
    EXE  G_DLG 0x0062C400  G_KS 0x0062C404  G_BTN 0x0062C408  append_option 0x0062C580
         fill 0x0062C850  clone VMT block 0x0062CA20 (VMT 0x0062CA60)  cave_dispatch 0x0062CA88
         click 0x0062CB40  method table 0x0062CC54

⚠ The DLL half must never ship without the exe half: a marked event reaching the unpatched exe
opens the HERO level-up dialog on a plain unit.  This script applies and undoes both together.

Couplings (undo this first): build_copper_medal.py (HEROIC; the stat tables are read, never
written, so re-tuning them is safe), build_heroicchoice_data.py, build_haste_moves.py,
build_spellcast_multiturn.py, build_medal_hpmv.py (HP cap, the two per-rank multipliers read live),
build_levelup_eventloc.py (owns the event's ReadWrite and ViewLocation slots, untouched here;
a unit event keeps flag 0, so right-click follows the unit).

    python build_scripts/build_heroicchoice.py            dry run + state (both binaries)
    python build_scripts/build_heroicchoice.py --apply
    python build_scripts/build_heroicchoice.py --undo
    python build_scripts/build_heroicchoice.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aowepack_patch as AP          # noqa: E402
import exe_patch as XP               # noqa: E402
import heroicchoice as G             # noqa: E402

asm = AP.asm


def lstr(s):
    raw = s.encode("latin1")
    blob = b"\xff\xff\xff\xff" + struct.pack("<I", len(raw)) + raw + b"\0"
    return blob + b"\0" * (-len(blob) % 4)


class Layout:
    def __init__(self, base, end):
        self.va, self.end, self.parts, self.sym = base, end, [], {}

    def add(self, name, blob, align=16):
        self.sym[name] = self.va
        self.parts.append((name, self.va, blob))
        self.va = (self.va + len(blob) + align - 1) & ~(align - 1)
        assert self.va <= self.end, "%s overflows its slot" % name
        return self.sym[name]


# ================================================================================ DLL ==========
D_SLOT = (0x558B1000, 0x558B2000)
MAP_VAR, ENGINE_VAR = 0x558FA040, 0x558FA048
TUNIT_VMT = 0x55710CAC
FINDUNIT, GETPLAYERS, RANDOM = 0x5577E948, 0x557544D0, 0x5577827C
UDA, ISCLASS, TARMY_CELL, UPDFORM = 0x5574F518, 0x557010C0, 0x557130AC, 0x5578D034
EVLOG_CELL, EVLOG_VMT, EVLOG_CREATE, EVLOG_EXEC = 0x55711B48, 0x55711B88, 0x557FD398, 0x557FD56C
LB_ADD, LB_COUNT, LB_GET = 0x557FDB90, 0x557FD998, 0x557FDA9C
REG_CLASSIC, REG_SIMUL = 0x5570553C, 0x557055E8
TOKEN_EXEC = 0x55703654
LSTRCAT3, LSTRASG, LSTRCLR = 0x55701190, 0x55701150, 0x55701140
HPCAP_VA = 0x55818088                 # imm8 of build_medal_hpmv.py's `cmp eax, cap`
GETNEXT_TAIL_JMP = 0x55782942         # build_copper_medal.py's jmp into the heroic step

SLOTS = {   # name: (slot VA, value expected there now)
    "changed": (0x55710D3C, 0x55782B34),
    "hits":    (0x55710D7C, 0x55782B68),
    "moves":   (0x55710D80, 0x558A0000),
    "newday":  (0x55710DE4, 0x55782C98),
    "newturn": (0x55710DE8, 0x5580D940),
    "evtext":  (0x55711BD4, 0x55785558),
    "evexec":  (0x55711BF8, 0x5578566C),
    "teexec":  (0x5571196C, 0x55785450),
}
RW_SITE = 0x55782D13
RW_ORIG = bytes.fromhex("8d563cb9070000008bc38b38ff5730")
RW_FN = (0x55782CEC, 0x55782E37)

# Heroic's medal bonus (owner 2026-10-20): TOTALS, in place of gold's.  A heroic unit's GetRank is
# gold (3), so the caves add TOTAL - gold, with gold read live from build_copper_medal.py's stat
# tables and build_medal_hpmv.py's per-rank multipliers: re-tuning either keeps these totals.
HEROIC_TOTALS = {"Attack": 4, "Defense": 2, "Damage": 3, "Resistance": 4, "Hits": 10, "Moves": 4}
GOLD = 3
RANK_TABLE = {"Defense": 0x558E83C4, "Attack": 0x558E83C8, "Damage": 0x558E83CC, "Resistance": 0x558E83D0}
RANK_K = {"Moves": 0x5580BE12, "Hits": 0x5580BE27}   # imm8 of build_medal_hpmv.py's `imul eax, eax, K`
CACHE = [(0x44, "Attack"), (0x45, "Defense"), (0x46, "Resistance"), (0x47, "Damage")]
GETNEXT = 0x164                                    # TUnit VMT: GetNextRankExperience, 0 = heroic

TXT_SUFFIX = " has earned the Heroic medal"
TXT_FALLBACK = "A unit has earned the Heroic medal"
OWN_K = "dword ptr [{r} + {k}*4 + 0x50]"      # option owner k (1..3) = +0x54 + 4*(k-1)
DELTA_K = 0x60 - G.NSTATS                    # +DELTA_K + 6*k = option k's deltas (k 1..3)


def dll_caves(hpcap):
    L = Layout(*D_SLOT)
    GD = L.add("get_delta", asm(f"""
        call gd_next
    gd_next:
        pop  eax
        sub  eax, {D_SLOT[0] + 5:#x}
        ret
    """, D_SLOT[0]))
    lit_suffix = L.add("lit_suffix", lstr(TXT_SUFFIX)) + 8
    lit_fallback = L.add("lit_fallback", lstr(TXT_FALLBACK)) + 8

    OPT = L.add("opt_present", asm(f"""
        push ebx
        mov  ebx, eax
        mov  eax, dword ptr [ebx + edx*4 + 0x54]
        test eax, eax
        je   stats
        mov  ecx, dword ptr [eax + 0xc]
        mov  eax, dword ptr [eax + 8]
        test eax, eax
        je   stats
        add  ecx, 7
        shr  ecx, 3
    bits:
        test ecx, ecx
        je   stats
        cmp  byte ptr [eax], 0
        jne  yes
        inc  eax
        dec  ecx
        jmp  bits
    stats:
        imul ecx, edx, 6
        lea  eax, [ebx + ecx + 0x60]
        xor  ecx, ecx
    sl:
        cmp  byte ptr [eax + ecx], 0
        jne  yes
        inc  ecx
        cmp  ecx, 6
        jb   sl
        xor  eax, eax
        pop  ebx
        ret
    yes:
        mov  eax, 1
        pop  ebx
        ret
    """, L.va))

    PENDING = L.add("pending_count", asm(f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        test byte ptr [esi + 0x3f], 3
        jne  no
        mov  ebx, dword ptr [esi + 0x40]
        test ebx, ebx
        je   no
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x164]
        test eax, eax
        jne  no
        xor  edi, edi
        mov  eax, ebx
        xor  edx, edx
        call {OPT:#x}
        add  edi, eax
        mov  eax, ebx
        mov  edx, 1
        call {OPT:#x}
        add  edi, eax
        mov  eax, ebx
        mov  edx, 2
        call {OPT:#x}
        add  edi, eax
        mov  eax, edi
        jmp  out
    no:
        xor  eax, eax
    out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))

    NTH = L.add("nth_option", asm(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        xor  edi, edi
    lp:
        mov  eax, ebx
        mov  edx, edi
        call {OPT:#x}
        test eax, eax
        je   nx
        test esi, esi
        je   hit
        dec  esi
    nx:
        inc  edi
        cmp  edi, 3
        jb   lp
        xor  eax, eax
        jmp  o
    hit:
        lea  eax, [edi + 1]
    o:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))

    APPLY = L.add("apply_choice", asm(f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        mov  al, byte ptr [esi + {G.UNIT_STATE_OFF:#x}]
        and  al, {G.STATE_ANNOUNCED:#x}
        or   al, dl
        mov  byte ptr [esi + {G.UNIT_STATE_OFF:#x}], al
        mov  eax, dword ptr [esi + 0x40]
        mov  edx, {OWN_K.format(r="eax", k="edi")}
        mov  eax, esi
        call {UDA:#x}
        mov  ebx, dword ptr [esi + 4]
        test ebx, ebx
        je   nof
        call {GD:#x}
        mov  edx, dword ptr [eax + {TARMY_CELL:#x}]
        mov  eax, ebx
        call {ISCLASS:#x}
        test al, al
        je   nof
        mov  eax, ebx
        call {UPDFORM:#x}
    nof:
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x90]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xe0]
        mov  edx, eax
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xe4]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xd8]
        mov  edx, eax
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xdc]
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))

    RAISE = L.add("raise_event", asm(f"""
        push ebx
        push esi
        push edi
        push ebp
        mov  esi, eax
        mov  edi, edx
        mov  ebp, dword ptr [edi + 0xd8]
        test ebp, ebp
        je   o
        mov  eax, ebp
        call {LB_COUNT:#x}
        mov  ebx, eax
    s:
        test ebx, ebx
        jle  create
        dec  ebx
        mov  eax, ebp
        mov  edx, ebx
        call {LB_GET:#x}
        test eax, eax
        je   s
        cmp  byte ptr [eax + 0x1c], 0xff
        jne  s
        cmp  byte ptr [eax + 0x1d], 0xff
        jne  s
        mov  edx, dword ptr [eax + 0x18]
        cmp  edx, dword ptr [esi + 0x18]
        jne  s
        push eax
        call {GD:#x}
        lea  edx, [eax + {EVLOG_VMT:#x}]
        pop  eax
        cmp  dword ptr [eax], edx
        jne  s
        jmp  o
    create:
        call {GD:#x}
        mov  eax, dword ptr [eax + {EVLOG_CELL:#x}]
        mov  dl, 1
        xor  ecx, ecx
        call {EVLOG_CREATE:#x}
        mov  ebx, eax
        mov  byte ptr [ebx + 0x1c], 0xff
        mov  byte ptr [ebx + 0x1d], 0xff
        mov  eax, dword ptr [edi + 0x5c]
        mov  dword ptr [ebx + 0x20], eax
        mov  al, byte ptr [esi + 0x24]
        mov  byte ptr [ebx + 0x10], al
        mov  eax, dword ptr [esi + 0x18]
        mov  dword ptr [ebx + 0x18], eax
        mov  eax, ebp
        mov  edx, ebx
        call {LB_ADD:#x}
        test byte ptr [esi + {G.UNIT_STATE_OFF:#x}], {G.STATE_ANNOUNCED:#x}
        jne  rel
        or   byte ptr [esi + {G.UNIT_STATE_OFF:#x}], {G.STATE_ANNOUNCED:#x}
        call {GD:#x}
        mov  eax, dword ptr [eax + {MAP_VAR:#x}]
        mov  al, byte ptr [eax + 0xa5]
        cmp  al, byte ptr [esi + 0x24]
        jne  rel
        cmp  byte ptr [edi + 0xa7], 0
        jne  rel
        push 0
        push 0
        xor  ecx, ecx
        xor  edx, edx
        mov  eax, ebx
        mov  ebp, dword ptr [eax]
        call dword ptr [ebp + 0x70]
    rel:
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
    o:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))

    # ---- VMT wrappers ---------------------------------------------------------------------
    def stat_wrap(orig, name, lo, hi):
        """GetHits / GetMoves: + heroic's increment over gold, + the taken option's delta; clamped
        lo..hi only when either moved the value, so every other unit reads exactly as before."""
        field = G.STAT_FIELDS.index(name)
        return f"""
        push ebx
        push esi
        mov  ebx, eax
        call {orig:#x}
        movsx esi, al
        push esi
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {GETNEXT:#x}]
        test eax, eax
        jne  opt
        call {GD:#x}
        movzx edx, byte ptr [eax + {RANK_K[name]:#x}]
        imul edx, edx, {GOLD}
        neg  edx
        add  edx, {HEROIC_TOTALS[name]}
        add  esi, edx
    opt:
        movzx ecx, byte ptr [ebx + {G.UNIT_STATE_OFF:#x}]
        and  ecx, {G.STATE_PICK_MASK:#x}
        je   fin
        mov  edx, dword ptr [ebx + 0x40]
        test edx, edx
        je   fin
        imul ecx, ecx, {G.NSTATS}
        movsx edx, byte ptr [edx + ecx + {DELTA_K + field:#x}]
        add  esi, edx
    fin:
        pop  eax
        cmp  esi, eax
        je   o
        mov  eax, esi
        cmp  eax, {lo}
        jge  lo_ok
        mov  eax, {lo}
    lo_ok:
        cmp  eax, {hi}
        jle  o
        mov  eax, {hi}
    o:
        pop  esi
        pop  ebx
        ret"""

    L.add("cave_hits", asm(stat_wrap(SLOTS['hits'][1], "Hits", 1, hpcap), L.va))
    L.add("cave_moves", asm(stat_wrap(SLOTS['moves'][1], "Moves", 1, 0x7f), L.va))
    heroic_cache = "".join(f"""
        mov  dl, {HEROIC_TOTALS[name]}
        sub  dl, byte ptr [eax + {RANK_TABLE[name] + GOLD:#x}]
        add  byte ptr [ebx + {off:#x}], dl""" for off, name in CACHE)
    L.add("cave_changed", asm(f"""
        push ebx
        mov  ebx, eax
        call {SLOTS['changed'][1]:#x}
        cmp  dword ptr [ebx + 0x40], 0
        je   o
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {GETNEXT:#x}]
        test eax, eax
        jne  opt
        call {GD:#x}
        {heroic_cache}
    opt:
        movzx ecx, byte ptr [ebx + {G.UNIT_STATE_OFF:#x}]
        and  ecx, {G.STATE_PICK_MASK:#x}
        je   o
        mov  edx, dword ptr [ebx + 0x40]
        test edx, edx
        je   o
        imul ecx, ecx, {G.NSTATS}
        lea  edx, [edx + ecx + {DELTA_K:#x}]
        mov  al, byte ptr [edx + 0]
        add  byte ptr [ebx + 0x44], al
        mov  al, byte ptr [edx + 1]
        add  byte ptr [ebx + 0x45], al
        mov  al, byte ptr [edx + 5]
        add  byte ptr [ebx + 0x46], al
        mov  al, byte ptr [edx + 2]
        add  byte ptr [ebx + 0x47], al
    o:
        pop  ebx
        ret
    """, L.va))
    L.add("cave_newday", asm(f"""
        push ebx
        mov  ebx, eax
        call {SLOTS['newday'][1]:#x}
        call {GD:#x}
        mov  eax, dword ptr [eax + {MAP_VAR:#x}]
        cmp  dword ptr [eax + 0x174], 1
        jne  o
        movzx edx, byte ptr [ebx + {G.UNIT_STATE_OFF:#x}]
        and  edx, {G.STATE_PICK_MASK:#x}
        je   o
        mov  eax, dword ptr [ebx + 0x40]
        test eax, eax
        je   o
        mov  edx, {OWN_K.format(r="eax", k="edx")}
        mov  eax, ebx
        call {UDA:#x}
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x90]
    o:
        pop  ebx
        ret
    """, L.va))
    L.add("cave_newturn", asm(f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  ebx, edx
        call {SLOTS['newturn'][1]:#x}
        cmp  bl, byte ptr [esi + 0x24]
        jne  o
        cmp  byte ptr [esi + 0x24], 0
        jle  o
        mov  eax, esi
        call {PENDING:#x}
        test eax, eax
        je   o
        mov  edi, eax
        cmp  edi, 1
        je   only
        call {GD:#x}
        mov  eax, dword ptr [eax + {MAP_VAR:#x}]
        mov  eax, dword ptr [eax + 0x140]
        movsx edx, byte ptr [esi + 0x24]
        call {GETPLAYERS:#x}
        cmp  byte ptr [eax + 0xa7], 0
        jne  ai
        mov  edx, eax
        mov  eax, esi
        call {RAISE:#x}
        jmp  o
    ai:
        call {GD:#x}
        mov  eax, dword ptr [eax + {MAP_VAR:#x}]
        mov  edx, edi
        call {RANDOM:#x}
        mov  edx, eax
        jmp  pick
    only:
        xor  edx, edx
    pick:
        mov  eax, dword ptr [esi + 0x40]
        call {NTH:#x}
        test eax, eax
        je   o
        mov  edx, eax
        mov  eax, esi
        call {APPLY:#x}
    o:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))
    L.add("cave_evexec", asm(f"""
        cmp  byte ptr [eax + 0x1c], 0xff
        jne  van
        cmp  byte ptr [eax + 0x1d], 0xff
        jne  van
        push ebx
        push esi
        push edi
        push ebp
        mov  esi, eax
        mov  ebx, edx
        movzx edi, cl
        call {GD:#x}
        mov  ebp, eax
        mov  eax, dword ptr [ebp + {MAP_VAR:#x}]
        mov  eax, dword ptr [eax + 0xfc]
        mov  edx, dword ptr [esi + 0x18]
        call {FINDUNIT:#x}
        test eax, eax
        je   no
        mov  edx, dword ptr [ebp + {MAP_VAR:#x}]
        mov  cl, byte ptr [edx + 0xa5]
        cmp  cl, byte ptr [eax + 0x24]
        jne  no
        call {PENDING:#x}
        test eax, eax
        je   no
        cmp  edi, 1
        je   go
        mov  eax, dword ptr [ebp + {MAP_VAR:#x}]
        mov  al, byte ptr [eax + 0x239]
        cmp  al, 1
        jne  try2
        mov  eax, dword ptr [ebp + {ENGINE_VAR:#x}]
        mov  eax, dword ptr [eax + 0x5c]
        call {REG_CLASSIC:#x}
        test al, 0x40
        jne  go
        jmp  no
    try2:
        cmp  al, 2
        jne  no
        mov  eax, dword ptr [ebp + {ENGINE_VAR:#x}]
        mov  eax, dword ptr [eax + 0x5c]
        call {REG_SIMUL:#x}
        test al, 0x40
        jne  go
    no:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        xor  eax, eax
        ret  8
    go:
        mov  eax, esi
        mov  edx, ebx
        mov  ecx, edi
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        jmp  {EVLOG_EXEC:#x}
    van:
        jmp  {SLOTS['evexec'][1]:#x}
    """, L.va))
    L.add("cave_evtext", asm(f"""
        cmp  byte ptr [eax + 0x1c], 0xff
        jne  van
        cmp  byte ptr [eax + 0x1d], 0xff
        jne  van
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  edi, edx
        push 0
        call {GD:#x}
        mov  esi, eax
        mov  eax, dword ptr [esi + {MAP_VAR:#x}]
        mov  eax, dword ptr [eax + 0xfc]
        mov  edx, dword ptr [ebx + 0x18]
        call {FINDUNIT:#x}
        test eax, eax
        je   fallback
        mov  edx, esp
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xf8]
        mov  eax, edi
        mov  edx, dword ptr [esp]
        lea  ecx, [esi + {lit_suffix:#x}]
        call {LSTRCAT3:#x}
        jmp  clr
    fallback:
        mov  eax, edi
        lea  edx, [esi + {lit_fallback:#x}]
        call {LSTRASG:#x}
    clr:
        mov  eax, esp
        call {LSTRCLR:#x}
        pop  eax
        pop  edi
        pop  esi
        pop  ebx
        ret
    van:
        jmp  {SLOTS['evtext'][1]:#x}
    """, L.va))
    L.add("cave_teexec", asm(f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        call {GD:#x}
        mov  edi, eax
        mov  eax, dword ptr [edi + {MAP_VAR:#x}]
        mov  eax, dword ptr [eax + 0xfc]
        mov  edx, dword ptr [esi + 0x10]
        call {FINDUNIT:#x}
        mov  ebx, eax
        test ebx, ebx
        je   van
        lea  eax, [edi + {TUNIT_VMT:#x}]
        cmp  dword ptr [ebx], eax
        jne  van
        mov  eax, esi
        call {TOKEN_EXEC:#x}
        push eax
        mov  al, byte ptr [ebx + 0x24]
        cmp  al, byte ptr [esi + 0x14]
        jne  done
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xe0]
        test al, al
        je   done
        mov  eax, ebx
        call {PENDING:#x}
        test eax, eax
        je   done
        movzx edx, byte ptr [esi + 0x15]
        dec  edx
        cmp  edx, 2
        ja   done
        mov  eax, dword ptr [ebx + 0x40]
        call {OPT:#x}
        test eax, eax
        je   done
        movzx edx, byte ptr [esi + 0x15]
        mov  eax, ebx
        call {APPLY:#x}
    done:
        pop  eax
        pop  edi
        pop  esi
        pop  ebx
        ret
    van:
        mov  eax, esi
        pop  edi
        pop  esi
        pop  ebx
        jmp  {SLOTS['teexec'][1]:#x}
    """, L.va))
    L.add("cave_rw", asm(f"""
        lea  edx, [esi + 0x3c]
        mov  ecx, 7
        mov  eax, ebx
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0x30]
        lea  edx, [esi + {G.UNIT_STATE_OFF:#x}]
        mov  ecx, {G.UNIT_TAG:#x}
        mov  eax, ebx
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0x30]
        ret
    """, L.va))

    # ---- the Always set (added 2026-10-20; appended so every pinned entry above stays put) ------
    # always_any: EAX = TUnitResource -> EAX = 1 when its Always owner has any ability bit
    ANY = L.add("always_any", asm(f"""
        mov  eax, dword ptr [eax + {G.ALWAYS_OFF:#x}]
        test eax, eax
        je   no
        mov  ecx, dword ptr [eax + 0xc]
        mov  eax, dword ptr [eax + 8]
        test eax, eax
        je   no
        add  ecx, 7
        shr  ecx, 3
    bits:
        test ecx, ecx
        je   no
        cmp  byte ptr [eax], 0
        jne  yes
        inc  eax
        dec  ecx
        jmp  bits
    no:
        xor  eax, eax
        ret
    yes:
        mov  eax, 1
        ret
    """, L.va))
    # grant_always: EAX = unit.  Heroic, not yet granted, and the type has an Always set -> mark
    # it, UpdateDefaultAbilities, then apply_choice's own refresh (aura, Changed, HP, moves).
    GRANT = L.add("grant_always", asm(f"""
        push ebx
        push esi
        mov  esi, eax
        test byte ptr [esi + {G.UNIT_STATE_OFF:#x}], {G.STATE_ALWAYS:#x}
        jne  out
        mov  ebx, dword ptr [esi + 0x40]
        test ebx, ebx
        je   out
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {GETNEXT:#x}]
        test eax, eax
        jne  out
        mov  eax, ebx
        call {ANY:#x}
        test eax, eax
        je   out
        or   byte ptr [esi + {G.UNIT_STATE_OFF:#x}], {G.STATE_ALWAYS:#x}
        mov  edx, dword ptr [ebx + {G.ALWAYS_OFF:#x}]
        mov  eax, esi
        call {UDA:#x}
        mov  ebx, dword ptr [esi + 4]
        test ebx, ebx
        je   nof
        call {GD:#x}
        mov  edx, dword ptr [eax + {TARMY_CELL:#x}]
        mov  eax, ebx
        call {ISCLASS:#x}
        test al, al
        je   nof
        mov  eax, ebx
        call {UPDFORM:#x}
    nof:
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x90]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xe0]
        mov  edx, eax
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xe4]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xd8]
        mov  edx, eax
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xdc]
    out:
        pop  esi
        pop  ebx
        ret
    """, L.va))
    # cave_always_turn: the NewTurn hook.  cave_newturn (options) unchanged, then on the owner's
    # turn the Always grant -- whether or not the type has options or the player has chosen.
    L.add("cave_always_turn", asm(f"""
        push ebx
        push esi
        mov  esi, eax
        mov  ebx, edx
        call {L.sym['cave_newturn']:#x}
        cmp  bl, byte ptr [esi + 0x24]
        jne  o
        cmp  byte ptr [esi + 0x24], 0
        jle  o
        mov  eax, esi
        call {GRANT:#x}
    o:
        pop  esi
        pop  ebx
        ret
    """, L.va))
    # cave_always_day: the NewDay hook.  cave_newday (day-1 option re-grant) unchanged, then on day
    # 1 a unit that had its Always set gets it back after the day-1 ability rebuild.
    L.add("cave_always_day", asm(f"""
        push ebx
        mov  ebx, eax
        call {L.sym['cave_newday']:#x}
        call {GD:#x}
        mov  eax, dword ptr [eax + {MAP_VAR:#x}]
        cmp  dword ptr [eax + 0x174], 1
        jne  o
        test byte ptr [ebx + {G.UNIT_STATE_OFF:#x}], {G.STATE_ALWAYS:#x}
        je   o
        mov  eax, dword ptr [ebx + 0x40]
        test eax, eax
        je   o
        mov  edx, dword ptr [eax + {G.ALWAYS_OFF:#x}]
        mov  eax, ebx
        call {UDA:#x}
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x90]
    o:
        pop  ebx
        ret
    """, L.va))
    return L


HOOK_CAVE = {"newturn": "cave_always_turn", "newday": "cave_always_day"}   # the rest: "cave_" + name


# ================================================================================ EXE ==========
X_SLOT = (0x0062C400, 0x0062D000)
MAPPTR = 0x0045DF7C                  # [[MAPPTR]] = the map
X_FINDUNIT, X_GETPLAYERS, X_GETBUSY = 0x00402684, 0x00402464, 0x004023FC
X_TE_CELL, X_TE_CREATE, X_TE_SETUP, X_GETTOKENCTRL = 0x0045DFD0, 0x004026E4, 0x004026EC, 0x00401ED4
X_LISTABIL, X_TSL_IAT, X_TOBJ_CREATE, X_TOBJ_FREE = 0x004023C4, 0x0045D4E4, 0x00401058, 0x00401068
X_LSTRCAT, X_LSTRASG, X_LSTRCLR, X_INTTOSTR = 0x00401118, 0x004010E8, 0x004010D8, 0x004013AC
X_LABEL_SETG, X_BTN_SETG = 0x00403254, 0x0040323C
X_CLICK_OBJ, X_CLICK_SND = 0x0045A420, 0x00455DFC
HERO_SETUP = 0x00446268
DISPATCH_SITE = 0x0044F1F3
DONOR_VMT, DONOR_INIT, DONOR_CLOSE, DONOR_FACE_BODY = 0x00437734, 0x00437ABC, 0x00437A18, 0x004380DB
DONOR_METHODS = {"LeftBtnClick": 0x437DE0, "MiddleBtnClick": 0x437E68, "RightBtnClick": 0x437EF0,
                 "PartyJoinDlgCreate": 0x4379C8, "PartyJoinDlgDestroy": 0x4379E4,
                 "U1MouseDown": 0x4381CC, "CloseClick": 0x437F1C, "FaceFramePreDraw": 0x4380BC,
                 "U1PreDraw": 0x438158, "DlgHide": 0x43824C, "DlgKeyDown": 0x438254}
# donor fields (TPartyJoinDlg field table 0x0043775C)
F_UNITPNL, F_MIDBTN, F_TITLEICON, F_TITLE, F_RIGHTBTN, F_LEFTBTN, F_DLG = 0x44, 0x68, 0x6C, 0x70, 0x78, 0x7C, 0x80
F_MEMO, F_HEADER, F_DETAILS = 0x8C, 0x90, 0x98
F_CBCODE, F_CBDATA, F_EVENT, F_UNIT = 0xA4, 0xA8, 0xAC, 0xB8
DISPLAY = [(0, " Attack"), (1, " Defense"), (5, " Resistance"), (2, " Damage"), (3, " Hits"), (4, " Moves")]


def exe_caves(donor_vmt_block):
    L = Layout(*X_SLOT)
    G_DLG = L.add("G_DLG", b"\0" * 4, 4)
    G_KS = L.add("G_KS", b"\0" * 4, 4)        # present option numbers, in order
    G_BTN = L.add("G_BTN", b"\0" * 4, 4)      # option per button: Left, Middle, Right, (Close = 0)
    L.va = (L.va + 15) & ~15
    lit = {}
    for s in ("Heroic Medal", ", ", "+", "Heroic 1: ", "Heroic 2: ", "Heroic 3: ",
              "Heroic 1", "Heroic 2", "Heroic 3") + tuple(n for _f, n in DISPLAY):
        lit[s] = L.add("lit:" + s, lstr(s), 4) + 8
    t_line = L.add("tbl_line", struct.pack("<3I", *(lit["Heroic %d: " % k] for k in (1, 2, 3))), 4)
    t_btn = L.add("tbl_btn", struct.pack("<3I", *(lit["Heroic %d" % k] for k in (1, 2, 3))), 4)

    OPTX = L.add("opt_present", asm("""
        push ebx
        mov  ebx, eax
        mov  eax, dword ptr [ebx + edx*4 + 0x54]
        test eax, eax
        je   stats
        mov  ecx, dword ptr [eax + 0xc]
        mov  eax, dword ptr [eax + 8]
        test eax, eax
        je   stats
        add  ecx, 7
        shr  ecx, 3
    bits:
        test ecx, ecx
        je   stats
        cmp  byte ptr [eax], 0
        jne  yes
        inc  eax
        dec  ecx
        jmp  bits
    stats:
        imul ecx, edx, 6
        lea  eax, [ebx + ecx + 0x60]
        xor  ecx, ecx
    sl:
        cmp  byte ptr [eax + ecx], 0
        jne  yes
        inc  ecx
        cmp  ecx, 6
        jb   sl
        xor  eax, eax
        pop  ebx
        ret
    yes:
        mov  eax, 1
        pop  ebx
        ret
    """, L.va))

    stats = ""
    for j, (field, name) in enumerate(DISPLAY):
        stats += f"""
        imul ecx, esi, {G.NSTATS}
        movsx eax, byte ptr [ebx + ecx + {G.STATS_OFF + field:#x}]
        test eax, eax
        je   st_skip{j}
        mov  dword ptr [ebp - 0xc], eax
        cmp  dword ptr [ebp - 8], 0
        jne  st_first{j}
        mov  eax, edi
        mov  edx, {lit[', ']:#x}
        call {X_LSTRCAT:#x}
    st_first{j}:
        mov  dword ptr [ebp - 8], 0
        cmp  dword ptr [ebp - 0xc], 0
        jle  st_neg{j}
        mov  eax, edi
        mov  edx, {lit['+']:#x}
        call {X_LSTRCAT:#x}
    st_neg{j}:
        mov  eax, dword ptr [ebp - 0xc]
        lea  edx, [ebp - 4]
        call {X_INTTOSTR:#x}
        mov  eax, edi
        mov  edx, dword ptr [ebp - 4]
        call {X_LSTRCAT:#x}
        mov  eax, edi
        mov  edx, {lit[name]:#x}
        call {X_LSTRCAT:#x}
    st_skip{j}:"""
    APPEND = L.add("append_option", asm(f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x14
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        mov  edi, ecx
        mov  dword ptr [ebp - 4], 0
        mov  dword ptr [ebp - 8], 1
        mov  eax, dword ptr [{X_TSL_IAT:#x}]
        mov  dl, 1
        call {X_TOBJ_CREATE:#x}
        mov  dword ptr [ebp - 0x14], eax
        mov  eax, dword ptr [ebx + esi*4 + 0x54]
        test eax, eax
        je   ab_end
        mov  edx, dword ptr [ebp - 0x14]
        call {X_LISTABIL:#x}
        mov  eax, dword ptr [ebp - 0x14]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x14]
        mov  dword ptr [ebp - 0x10], eax
        mov  dword ptr [ebp - 0xc], 0
    ab_lp:
        mov  eax, dword ptr [ebp - 0xc]
        cmp  eax, dword ptr [ebp - 0x10]
        jge  ab_end
        cmp  dword ptr [ebp - 8], 0
        jne  ab_first
        mov  eax, edi
        mov  edx, {lit[', ']:#x}
        call {X_LSTRCAT:#x}
    ab_first:
        mov  dword ptr [ebp - 8], 0
        lea  ecx, [ebp - 4]
        mov  edx, dword ptr [ebp - 0xc]
        mov  eax, dword ptr [ebp - 0x14]
        push ebx
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0xc]
        pop  ebx
        mov  eax, edi
        mov  edx, dword ptr [ebp - 4]
        call {X_LSTRCAT:#x}
        inc  dword ptr [ebp - 0xc]
        jmp  ab_lp
    ab_end:
        mov  eax, dword ptr [ebp - 0x14]
        call {X_TOBJ_FREE:#x}
        {stats}
        lea  eax, [ebp - 4]
        call {X_LSTRCLR:#x}
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    """, L.va))

    hide = "".join(f"""
        mov  eax, dword ptr [ebx + {f:#x}]
        xor  edx, edx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x6c]""" for f in (F_UNITPNL, F_TITLEICON, F_LEFTBTN, F_MIDBTN, F_RIGHTBTN))
    buttons = "".join(f"""
        movzx eax, byte ptr [{G_BTN + slot:#x}]
        test eax, eax
        je   b_skip{slot}
        mov  edx, dword ptr [eax*4 + {t_btn - 4:#x}]
        mov  eax, dword ptr [ebx + {f:#x}]
        call {X_BTN_SETG:#x}
        mov  eax, dword ptr [ebx + {f:#x}]
        mov  dl, 1
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x6c]
    b_skip{slot}:""" for slot, f in enumerate((F_LEFTBTN, F_MIDBTN, F_RIGHTBTN)))
    FILL = L.add("fill", asm(f"""
        push esi
        push ebp
        sub  esp, 8
        xor  eax, eax
        mov  dword ptr [esp], eax
        mov  dword ptr [esp + 4], eax
        mov  eax, dword ptr [ebx + {F_TITLE:#x}]
        mov  edx, {lit['Heroic Medal']:#x}
        call {X_LABEL_SETG:#x}
        lea  edx, [esp + 4]
        mov  eax, edi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xf8]
        mov  eax, dword ptr [ebx + {F_HEADER:#x}]
        mov  edx, dword ptr [esp + 4]
        call {X_LABEL_SETG:#x}
        mov  eax, dword ptr [ebx + {F_DETAILS:#x}]
        xor  edx, edx
        call {X_LABEL_SETG:#x}
        {hide}
        mov  eax, dword ptr [ebx + {F_MEMO:#x}]
        mov  eax, dword ptr [eax + 0x118]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x40]
        mov  dword ptr [{G_KS:#x}], 0
        mov  dword ptr [{G_BTN:#x}], 0
        xor  ebp, ebp
        xor  esi, esi
    lp:
        mov  eax, dword ptr [edi + 0x40]
        mov  edx, esi
        call {OPTX:#x}
        test eax, eax
        je   nx
        mov  eax, esp
        mov  edx, dword ptr [esi*4 + {t_line:#x}]
        call {X_LSTRASG:#x}
        mov  eax, dword ptr [edi + 0x40]
        mov  edx, esi
        mov  ecx, esp
        call {APPEND:#x}
        mov  eax, dword ptr [ebx + {F_MEMO:#x}]
        mov  eax, dword ptr [eax + 0x118]
        mov  edx, dword ptr [esp]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x34]
        lea  eax, [esi + 1]
        mov  byte ptr [ebp + {G_KS:#x}], al
        inc  ebp
    nx:
        inc  esi
        cmp  esi, 3
        jb   lp
        cmp  ebp, 1
        je   one
        cmp  ebp, 2
        je   two
        cmp  ebp, 3
        jne  btn_done
        mov  al, byte ptr [{G_KS:#x}]
        mov  byte ptr [{G_BTN:#x}], al
        mov  al, byte ptr [{G_KS + 1:#x}]
        mov  byte ptr [{G_BTN + 1:#x}], al
        mov  al, byte ptr [{G_KS + 2:#x}]
        mov  byte ptr [{G_BTN + 2:#x}], al
        jmp  btn_set
    one:
        mov  al, byte ptr [{G_KS:#x}]
        mov  byte ptr [{G_BTN + 1:#x}], al
        jmp  btn_set
    two:
        mov  al, byte ptr [{G_KS:#x}]
        mov  byte ptr [{G_BTN:#x}], al
        mov  al, byte ptr [{G_KS + 1:#x}]
        mov  byte ptr [{G_BTN + 2:#x}], al
    btn_set:
        {buttons}
    btn_done:
        mov  eax, esp
        call {X_LSTRCLR:#x}
        lea  eax, [esp + 4]
        call {X_LSTRCLR:#x}
        add  esp, 8
        mov  eax, ebp
        pop  ebp
        pop  esi
        ret
    """, L.va))

    CLONE_VMT = L.va + 0x40
    vmt_block = bytearray(donor_vmt_block)
    L.add("clone_vmt", bytes(0x68), 4)            # placeholder; patched below once the table exists
    assert L.sym["clone_vmt"] + 0x40 == CLONE_VMT

    DISPATCH = L.add("cave_dispatch", asm(f"""
        cmp  byte ptr [edx + 0x1c], 0xff
        jne  hero
        cmp  byte ptr [edx + 0x1d], 0xff
        jne  hero
        push ebx
        push esi
        push edi
        mov  esi, edx
        mov  ebx, dword ptr [{G_DLG:#x}]
        test ebx, ebx
        jne  have
        mov  eax, {CLONE_VMT:#x}
        mov  dl, 1
        xor  ecx, ecx
        call dword ptr [eax + 0x24]
        mov  dword ptr [{G_DLG:#x}], eax
        mov  ebx, eax
    have:
        mov  eax, ebx
        call {DONOR_INIT:#x}
        mov  dword ptr [ebx + {F_EVENT:#x}], esi
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x28]
        mov  eax, dword ptr [esp + 0x10]
        mov  dword ptr [ebx + {F_CBCODE:#x}], eax
        mov  eax, dword ptr [esp + 0x14]
        mov  dword ptr [ebx + {F_CBDATA:#x}], eax
        mov  eax, dword ptr [{MAPPTR:#x}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0xfc]
        mov  edx, dword ptr [esi + 0x18]
        call {X_FINDUNIT:#x}
        mov  dword ptr [ebx + {F_UNIT:#x}], eax
        test eax, eax
        je   close
        mov  edi, eax
        call {FILL:#x}
        test eax, eax
        je   close
        mov  eax, dword ptr [ebx + {F_DLG:#x}]
        mov  dl, 1
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x6c]
        jmp  out
    close:
        mov  eax, ebx
        call {DONOR_CLOSE:#x}
    out:
        pop  edi
        pop  esi
        pop  ebx
        ret  8
    hero:
        jmp  {HERO_SETUP:#x}
    """, L.va))

    CLICK = L.add("click", asm(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        movzx edi, byte ptr [ecx + {G_BTN:#x}]
        mov  eax, dword ptr [{X_CLICK_OBJ:#x}]
        mov  eax, dword ptr [eax]
        xor  edx, edx
        call {X_CLICK_SND:#x}
        test edi, edi
        je   hide
        mov  eax, dword ptr [ebx + {F_EVENT:#x}]
        test eax, eax
        je   hide
        mov  edx, dword ptr [eax + 0x18]
        mov  eax, dword ptr [{MAPPTR:#x}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0xfc]
        call {X_FINDUNIT:#x}
        test eax, eax
        je   hide
        mov  esi, eax
        movsx edx, byte ptr [esi + 0x24]
        mov  eax, dword ptr [{MAPPTR:#x}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x140]
        call {X_GETPLAYERS:#x}
        call {X_GETBUSY:#x}
        test al, al
        jne  hide
        mov  eax, dword ptr [{X_TE_CELL:#x}]
        mov  dl, 1
        xor  ecx, ecx
        call {X_TE_CREATE:#x}
        push eax
        mov  edx, esi
        call {X_TE_SETUP:#x}
        mov  eax, dword ptr [esp]
        mov  edx, edi
        mov  byte ptr [eax + 0x15], dl
        movsx edx, byte ptr [esi + 0x24]
        mov  eax, dword ptr [{MAPPTR:#x}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x23c]
        call {X_GETTOKENCTRL:#x}
        mov  edx, dword ptr [esp]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x10]
        pop  eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
    hide:
        mov  eax, dword ptr [ebx + {F_DLG:#x}]
        xor  edx, edx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x6c]
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))
    handlers = {}
    for slot, name in enumerate(("LeftBtnClick", "MiddleBtnClick", "RightBtnClick", "CloseClick")):
        handlers[name] = L.add("h:" + name, asm(f"mov ecx, {slot}\njmp {CLICK:#x}", L.va), 4)
    handlers["FaceFramePreDraw"] = L.add("h:FaceFramePreDraw", asm(f"""
        push ebx
        push esi
        push edi
        add  esp, -0x4c
        mov  esi, ecx
        lea  edi, [esp]
        mov  ecx, 0xf
        rep movsd dword ptr es:[edi], dword ptr [esi]
        mov  ebx, eax
        jmp  {DONOR_FACE_BODY:#x}
    """, L.va), 4)
    handlers["U1PreDraw"] = L.add("h:U1PreDraw", b"\xc3", 4)
    handlers["U1MouseDown"] = L.add("h:U1MouseDown", asm("ret 0xc", L.va), 4)
    for name in ("PartyJoinDlgCreate", "PartyJoinDlgDestroy", "DlgHide", "DlgKeyDown"):
        handlers[name] = DONOR_METHODS[name]

    mt = struct.pack("<H", len(DONOR_METHODS))
    for name in DONOR_METHODS:                      # same order as the donor's table
        nm = name.encode()
        mt += struct.pack("<HI", 2 + 4 + 1 + len(nm), handlers[name]) + bytes([len(nm)]) + nm
    MTAB = L.add("method_table", mt, 4)

    struct.pack_into("<I", vmt_block, 0x00, CLONE_VMT)       # vmtSelfPtr
    struct.pack_into("<I", vmt_block, 0x40 - 0x28, MTAB)     # vmtMethodTable
    L.parts = [(n, va, bytes(vmt_block) if n == "clone_vmt" else b) for n, va, b in L.parts]
    L.clone_vmt = CLONE_VMT
    return L, DISPATCH


# ============================================================================== checks =========
def assumptions():
    """Everything this script relies on that another script owns.  Aborts with the owner's name."""
    d = open(AP.TARGET, "rb").read()
    u32 = lambda va: struct.unpack_from("<I", d, AP.va2off(d, va))[0]
    if u32(0x55710A48) != G.INSTSIZE:
        sys.exit("ABORT: build_heroicchoice_data.py is not installed (TUnitResource size)")
    if d[AP.va2off(d, GETNEXT_TAIL_JMP)] != 0xE9:
        sys.exit("ABORT: build_copper_medal.py has no HEROIC step (GetNextRankExperience)")
    hpcap = d[AP.va2off(d, HPCAP_VA)]
    if d[AP.va2off(d, HPCAP_VA) - 2:AP.va2off(d, HPCAP_VA)] != b"\x83\xf8":
        sys.exit("ABORT: build_medal_hpmv.py's HP cap compare moved (0x55818086)")
    for name, va in RANK_K.items():
        if d[AP.va2off(d, va) - 2:AP.va2off(d, va)] != b"\x6b\xc0":
            sys.exit("ABORT: build_medal_hpmv.py's %s multiplier moved (%08X)" % (name, va - 2))
    gold = {n: struct.unpack("b", d[AP.va2off(d, va + GOLD):][:1])[0] for n, va in RANK_TABLE.items()}
    gold.update({n: GOLD * d[AP.va2off(d, va)] for n, va in RANK_K.items()})
    print("heroic totals " + "  ".join("%s %+d (gold %+d)" % (n, t, gold[n]) for n, t in HEROIC_TOTALS.items()))
    x = open(os.path.join(XP.GAME, XP.zigexe.GAME_EXE), "rb").read()
    xo = XP.va2off(x, DONOR_VMT - 0x40)
    block = x[xo:xo + 0x68]
    mt = struct.unpack_from("<I", block, 0x40 - 0x28)[0]
    mo = XP.va2off(x, mt)
    n = struct.unpack_from("<H", x, mo)[0]
    p, names = mo + 2, {}
    for _ in range(n):
        sz, code = struct.unpack_from("<HI", x, p)
        names[x[p + 7:p + 7 + x[p + 6]].decode()] = code
        p += sz
    if names != DONOR_METHODS:
        sys.exit("ABORT: TPartyJoinDlg's method table is not the expected donor (%r)" % names)
    if struct.unpack_from("<I", block, 0)[0] != DONOR_VMT:
        sys.exit("ABORT: TPartyJoinDlg VMT self-pointer mismatch")
    return hpcap, block


ENTRY = {"get_delta": 0x558B1000, "opt_present": 0x558B1070, "pending_count": 0x558B10C0,
         "nth_option": 0x558B1120, "apply_choice": 0x558B1150, "raise_event": 0x558B11D0,
         "cave_hits": 0x558B12B0, "cave_moves": 0x558B1320, "cave_changed": 0x558B1390,
         "cave_newday": 0x558B1410, "cave_newturn": 0x558B1460, "cave_evexec": 0x558B14F0,
         "cave_evtext": 0x558B15B0, "cave_teexec": 0x558B1620, "cave_rw": 0x558B16B0,
         "always_any": 0x558B16D0, "grant_always": 0x558B1700, "cave_always_turn": 0x558B17A0,
         "cave_always_day": 0x558B17C0}
X_ENTRY = {"G_DLG": 0x0062C400, "G_KS": 0x0062C404, "G_BTN": 0x0062C408, "append_option": 0x0062C580,
           "fill": 0x0062C850, "clone_vmt": 0x0062CA20, "cave_dispatch": 0x0062CA88, "click": 0x0062CB40,
           "method_table": 0x0062CC54}
RNG_SITE = 0x558B14C4


def main():
    argv = sys.argv[1:]
    hpcap, block = assumptions()
    DL = dll_caves(hpcap)
    XL, dispatch = exe_caves(block)
    moved = [n for n, va in ENTRY.items() if DL.sym[n] != va] + \
            [n for n, va in X_ENTRY.items() if XL.sym[n] != va]
    assert not moved, "layout moved (%s): update ENTRY / X_ENTRY and the docstring" % ", ".join(moved)
    nt = next(b for n, _v, b in DL.parts if n == "cave_newturn")
    assert nt[RNG_SITE - ENTRY["cave_newturn"]] == 0xE8 and struct.unpack_from(
        "<i", nt, RNG_SITE - ENTRY["cave_newturn"] + 1)[0] == RANDOM - (RNG_SITE + 5), "RNG_SITE moved"
    dhooks = [(va, struct.pack("<I", cur), struct.pack("<I", DL.sym[HOOK_CAVE.get(k, "cave_" + k)]))
              for k, (va, cur) in SLOTS.items()]
    dhooks.append((RW_SITE, RW_ORIG, b"\xe8" + struct.pack("<i", DL.sym["cave_rw"] - (RW_SITE + 5))
                   + b"\x90" * 10))
    xhooks = [(DISPATCH_SITE, b"\xe8" + struct.pack("<i", HERO_SETUP - (DISPATCH_SITE + 5)),
               b"\xe8" + struct.pack("<i", dispatch - (DISPATCH_SITE + 5)))]
    reloc_ok = tuple(va for va, _c in SLOTS.values())
    interior = [(RW_SITE, RW_SITE + 15, RW_FN[0], RW_FN[1])]
    dcaves = [(n, va, b) for n, va, b in DL.parts]
    xcaves = [(n, va, b) for n, va, b in XL.parts]
    print("heroic choice -- HP cap %d, clone VMT %08X\n" % (hpcap, XL.clone_vmt))
    flags = [a for a in argv if a in ("--apply", "--undo")]
    dis = ["--dis"] if "--dis" in argv else []
    # verify both halves before writing either
    AP.run("build_heroicchoice [AoWEPACK.dpl]", dhooks, dcaves, D_SLOT, interior, dis, reloc_ok=reloc_ok)
    XP.run("build_heroicchoice [AoWz.exe]", xhooks, xcaves, X_SLOT, dis)
    if not flags:
        return
    AP.run("build_heroicchoice [AoWEPACK.dpl]", dhooks, dcaves, D_SLOT, interior, flags, reloc_ok=reloc_ok)
    try:
        XP.run("build_heroicchoice [AoWz.exe]", xhooks, xcaves, X_SLOT, flags)
    except BaseException:
        if flags == ["--apply"]:
            print("\n!! exe half failed -- undoing the DLL half so neither ships alone")
            AP.run("build_heroicchoice [AoWEPACK.dpl]", dhooks, dcaves, D_SLOT, interior, ["--undo"],
                   reloc_ok=reloc_ok)
        raise


if __name__ == "__main__":
    main()
