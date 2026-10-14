#!/usr/bin/env python
r"""
build_combatlog_actions.py -- live manual-combat log lines for the combat actions that print nothing
today: round markers, healing, lifesteal / Dark Gift heals, touch outcomes, spell casts with their
mana, non-damaging spell outcomes, and command attempts on a Leader.  AoWEPACK.dpl.
Combat-log expansion package P2, 2026-10-14; v2 the same day (owner: no overstated outcomes --
unit-spell result and real dispel count; "spends N mana on X"; a zero heal prints no number).

THE LINES (manual combat only; cl_emit gates on RING_TACTICAL)
    --- Round 3 ---
    Priest heals Swordsman for 6                    no HP change: "Priest heals Swordsman" (replays too)
    Vampire drains 4 HP from Swordsman              lifesteal, CA+0x18 bit 08
    Vampire gains 3 HP from Dark Gift               CA+0x18 bit 10
    Swordsman is possessed by Spirit
    Swordsman is webbed by Giant Spider             only if Webbed (0x61) is on the target afterwards
    Swordsman is entangled by Treant                only if Entangled (0x5E) is on afterwards
    Lich invokes death on Swordsman for 6 damage
    Swordsman is seduced by Siren                   dominated (0x1C) / seduced (0x1D) / charmed (0x94),
                                                    else "commanded"
    Siren cannot command Lord Varn (a Leader)       G11: failed TCommandCA whose target is a TLeader
    Druid dispels 2 enchantments from Swordsman     the success-list ids FindID finds (= what Execute
                                                    dispels); ability: only when something is removed
    Mage dispels nothing from Swordsman             (spell)
    Druid breaks the command on Swordsman           build_command_bond.py's sentinel in the list
    Shaman spends 12 mana on Lethargy               TSpell.CombatSpellCast, every manual cast
    Swordsman is blessed by High Prayer (+3 HP)
    Shaman takes control of Swordsman (Mind Decay)
    Swordsman is slowed (Lethargy) / is embrittled (Embrittle)
    Swordsman is entangled (Entangle)
    Swordsman is terrified (Terror)
    Swordsman is unaffected by Lethargy             spell CA whose roll failed, or no status landed
    Necromancer recalls the spirit of Swordsman
    Necromancer raises Swordsman from the dead
    Swordsman receives Haste                        TUnitSpellCA: ExecuteSpell returned true and (for
                                                    the 15 spells in UNITSPELL_AB) the ability is on
    Swordsman is unaffected by Haste                otherwise (or ExecuteCA bailed)
Damage is never printed here: every damage CA already prints at the TDamageCA.Generate tails
(build_combatlog_dll.py), including the damage of a TStrikeCA whose heal this script prints.

SITE 1 -- TCombat.ExecuteCombatAction @0x55727224 (EAX = TCombat, EDX = CA)
    Vanilla body (0x25 B): `if [combat+8]&4 then logbook.Add(CA); CA.Execute(combat)`.  Every CA run
    in manual combat passes through it once (AoWTCPCK calls it from 30 sites, all real TEs/messages);
    the replay viewer calls Execute directly, so replays never come here.  Hook: the 6 B prologue
    `53 56 8B F2 8B D8` (reloc-free, nothing jumps into it) -> jmp ca_entry.
    ca_entry: cl_live? no -> jmp ca_tramp (the original runs untouched).  Yes -> frame, then
      PRE   dispatch on the EXACT class VMT; lines whose facts are known before Execute are emitted
            here, so they precede anything the action itself logs (P3's deaths from Invoke Death /
            Possess / a dispelled summon, P5's tick and expiry lines inside TNewCombatRoundCA).
            The ROUND line is emitted PRE: round = [[combat+0xC]+0x44] + 1, because
            TNewCombatRoundCA.Execute @0x5572A398 does `inc [data+0x44]` unconditionally first thing.
            Classes that need an after-state store a kind code and a snapshot (HP) in the frame.
      call  ca_tramp: `push ebx / push esi / mov esi,edx / mov ebx,eax / jmp 0x5572722A` -- the
            original function, which returns here.  Its EAX is kept and returned.
      POST  by kind: HP differences (heal, lifesteal, High Prayer) and status checks (web, entangle,
            slow, terror; TCombatUnit.GetAbilityEnabled, VMT +0xA8, behind IsClass(TCombatUnit)).
    No string is held across Execute: if Execute raises, the frame is unwound with nothing to free.
    Combat objects are re-found by id after Execute (FindID, nil-checked), never cached.

    Field maps, each from that class's own ReadWrite / Initialize / Execute (they differ):
      TSingleTargetCA family     +0x0C flags, +0x0D actor id, +0x0E target id (bytes)
        TPossessCA/TWebCA/TEntangleCA/TInvokeDeathCA   +0x10 success byte (set at creation)
        TCommandCA               +0x10 ability id (dword), +0x14 success byte
        THealingCA               nothing else; the amount is the target's HP difference
        TStrikeCA                +0x16 Razor Plate cut (build_razorplate.py, zeroed every Execute),
                                 +0x18 strike flags (08 lifesteal +4, 10 Dark Gift +3,
                                 build_lifesteal_roundattack.py cave 0x5580DC80)
        TDispelMagicCA family    +0x10 TIntegerList of enchantment ids that rolled success;
                                 TDispelMagicSpellCA adds +0x14 spell id, +0x18 mana
      TExclusiveCombatSpellCA    +0x0C caster id, +0x0D target id, +0x10 mana, +0x14 success
        (High Prayer, Mind Decay, Slow, Entangle spell, Recall Spirit, Animate Dead)  +0x18 spell id
        TAnimateDeadCA           +0x14 = the corpse is destroyed (no roll)
        TSlowCA                  status = Embrittled 0xB2 for spell 0x6D, else Slow Enchantment 0x84
                                 (build_embrittle.py's 0x5582D110)
      TTacticalCombatTerrorCA    +0x0C caster, +0x0D target, +0x10 mana, +0x14 success; spell 0x69;
                                 status Panicked 0x6C
      TUnitSpellCA               +0x0C spell id (dword), +0x10 caster id, +0x11 target id,
                                 +0x14 8 B argument block for ExecuteSpell (only Cosmetic Surgery
                                 reads it: the new appearance), +0x1C mana (TUnitSpell.CreateCA's
                                 flag; spent by CombatCastingDone on success when [combat+8] bit 0)
    G11: CreateCommandCA @0x55770358 forces success = 0 with no roll when [target+0x4C] IsClass
    TLeader (VMT 0x55712238, cell 0x557121F8, test at 0x5577037D).  Logged here when a failed
    TCommandCA's target unit IsClass TLeader; no other failure prints (the touch roll already did).

SITE 2 -- TSpell.CombatSpellCast @0x5577954C, mana site 0x5577955C
    6 B `8B C8 8B D6 8B C3` (mov ecx,eax / mov edx,esi / mov eax,ebx; reloc-free, nothing jumps into
    it) -> jmp cast_entry.  EAX = mana from THero.CastingMana, EBX = TSpell (+0x08 name LStr),
    ESI = caster (combat unit; vanilla already reads its +0x4C).  The only caller of CombatSpellCast is
    AoWTCPCK TCAbRangedTE.Execute @0x0040B44D, at the start of the cast before NextStrike builds any
    CA, so the cast line precedes the spell's damage/outcome lines.  cast_entry emits the line, then
    replays the three moves and resumes at 0x55779562.  EAX/EBX/ESI/EDI/EBP preserved.

SITE 3 -- TUnitSpell.ExecuteCA @0x5577B3B4, its ExecuteSpell call 0x5577B41F
    Can a unit enchantment fail?  Yes, with no roll.  TUnitSpellCA.Execute -> spell vmt+0xBC =
    TUnitSpell.ExecuteCA (no override in any unit spell): both ids must be TCombatUnits, then spell
    vmt+0xB4 ExecuteSpell(caster unit, target unit, @CA+0x14, [CA+0x1C]) -> AL.  Every override first
    asks its ValidTargetUnit (vmt+0x9C; e.g. Haste refuses a target already holding 0x98) and returns
    0 if it refuses.  Then TAbilityOwner.ExpandAbility (vmt+0x94; = TAbility vmt+0xD0): Haste returns
    0 if that refuses, but the other 14 ability spells return 1 regardless (their failure branch
    jumps to `mov al, 1`), so AL alone overstates for them; Remedy and Healing Water return 1 once
    ValidTargetUnit passes, Dispel Magic (strategic) 1 if the unit had any enchantment.  ExecuteCA throws AL away, so the 6 B `FF 97 B4 00 00 00`
    (call [edi+0xB4]; reloc-free, nothing jumps into it) become `call 0x5589B810` + nop -> es_stub,
    which re-pushes the two stack arguments, calls [edi+0xB4], stores AL in RESBYTE (DATA
    0x558E9A60, P2's assigned slack) and returns EAX untouched with `ret 8`.  pre_unitspell sets
    RESBYTE := 0xFF; post_unitspell prints "receives" for 1 -- if the spell's class VMT is in USTBL
    (UNITSPELL_AB: the 15 ExpandAbility spells, derived from the file and asserted) only when the
    target's GetAbilityEnabled(that id) is now true -- and "is unaffected by" otherwise.  Runs in
    replays too (Play -> Execute): build_combatlog_replays.py reads the same byte and table.

DISPEL COUNT -- TDispelMagicCA.Execute (0x5576CA60) builds a TEnchantmentList from the target's
    ListEnchantments and dispels (vmt+0x68) each success-list id that FindID finds.  dsp_count does
    the same before Execute, behind the same guards, and frees its list as Execute and Generate do;
    the count is exactly the entries Execute dispels.  build_command_bond.py's sentinels (never
    enchantment ids) still give "breaks the command on".

FIXED ENTRY STUBS -- 0x5589B800 jmp ca_entry, 0x5589B808 jmp cast_entry, 0x5589B810 jmp es_stub (8 B
    each).  The three hooks target these, so a re-tune rewrites the slot in place: run() sees the
    hooks "installed" and the caves different, zeroes the slot and writes the new image.

HELPERS -- build_combatlog_lib.py (fixed entries): cl_emit, cl_name, cl_live, cl_cat_int.  A frame
helper set inside this slot shares one layout across both entries: [ebp-0xC] the line,
[ebp-0x10]/[ebp-0x14] temporaries, all cleared by h_emit.  EDI = the slot base at run time
(get_base: call/pop, then `sub edi, const`), so every DLL operand is [edi +/- delta].

RNG: none.  No cave draws, and none writes game state; the only writes are the ring (cl_emit), the
frame and RESBYTE.  es_stub calls ExecuteSpell exactly once and passes its EAX through.  Every pointer is nil-checked or class-checked; GetSpell is never handed a negative id.
PIC: rel32 + the one get_base anchor; check_pic() aborts on any absolute DLL operand.

SLOT: AoWEPACK 0x5589B800-0x5589C7FF, exclusive (package map 2026-10-14).  Writable state: RESBYTE
0x558E9A60 (one byte of the assigned DATA 0x558E9A60-0x558E9A9F; the rest unused).

FORWARD HAZARDS
  * build_combatlog_lib.py must stay applied while this is (it refuses --undo while callers exist).
  * Lifesteal amounts read CA+0x16 (build_razorplate.py) and CA+0x18 bits 08/10
    (build_lifesteal_roundattack.py); re-tuning either flag layout breaks the heal lines.
  * TSlowCA's status mapping copies build_embrittle.py's 0x5582D110 (spell 0x6D -> 0xB2, else 0x84).
  * build_command_bond.py's dispel sentinels 0x7FFFFFF0/0x7FFFFFF1 are matched here.
  * build_combatlog_replays.py reads RESBYTE (its TUnitSpellCA lines go silent while this script is
    undone) and asserts its shared literals equal these: change wording in both.
  * The dispel count reproduces TDispelMagicCA.Execute's list/FindID logic; a patch to that loop
    (e.g. a new build_command_bond.py sentinel) must be mirrored in dsp_count.

    python build_scripts/build_combatlog_actions.py            dry run + state
    python build_scripts/build_combatlog_actions.py --apply    (also re-tunes an installed v2 in place)
    python build_scripts/build_combatlog_actions.py --undo
    python build_scripts/build_combatlog_actions.py --dis
"""
import os, re, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5589B800, 0x5589C800)

# ---- build_combatlog_lib.py contract ------------------------------------------------------
CL_EMIT, CL_NAME, CL_LIVE, CL_CAT_INT = 0x5589AC00, 0x5589AC10, 0x5589AC20, 0x5589AC30

# ---- AoWEPACK (all reached rel32 or [edi +/- delta]) --------------------------------------
IS_CLASS   = 0x557010C0      # System.@IsClass (eax=obj, edx=classref) -> al; nil-safe
LSTRCAT    = 0x55701188      # eax=@dest, edx=src value
LSTRARRCLR = 0x55701148      # eax=@first, edx=count
FINDID     = 0x55728C68      # TCombatData.FindID(eax=data, edx=id) -> obj or 0; no raise
INTLIST_GET = 0x55702E94     # TIntegerList.Get thunk (eax=list, edx=index)
GETSPELL   = 0x55779AC8      # TSpellControl.GetSpell(eax=ctrl, edx=id) -> 0 if id>=count; RAISES if <0
AOWHSSET   = 0x558FA044      # AoWE.AoWHSSet (cell holds the object); +0x84 TSpellControl
TCOMBATUNIT_VMT = 0x55715A94
TLEADER_VMT     = 0x55712238
GETHP_V, HASAB_V = 0x88, 0xA8   # TCombatObject VMT: GetHitPoints -> AL (signed); GetAbilityEnabled -> AL

VMT = {   # exact classes (VMT base); each verified as the value of its classref cell
    "round":     0x5571667C,   # TNewCombatRoundCA        cell 0x5571663C
    "heal":      0x557214BC,   # THealingCA
    "strike":    0x5571E344,   # TStrikeCA
    "possess":   0x5571F0E0,   # TPossessCA
    "web":       0x5571F5C4,   # TWebCA
    "entangle":  0x5571F824,   # TEntangleCA
    "invoke":    0x5571FA98,   # TInvokeDeathCA
    "command":   0x557203A0,   # TCommandCA               cell 0x55720360
    "dispel_ab": 0x55721A34,   # TDispelMagicAbilityCA    cell 0x557219F4
    "dispel_sp": 0x557E530C,   # TDispelMagicSpellCA
    "prayer":    0x557F44D0,   # TTacticalCombatHighPrayerCA cell 0x557F4490
    "minddecay": 0x557F4908,   # TMindDecayCA             cell 0x557F48C8
    "slow":      0x557F4D2C,   # TSlowCA                  cell 0x557F4CEC
    "entspell":  0x557F4F08,   # TEntangleSpellCA         cell 0x557F4EC8
    "terror":    0x557F60E0,   # TTacticalCombatTerrorCA  cell 0x557F60A0
    "recall":    0x557F662C,   # TRecallSpiritCA          cell 0x557F65EC
    "animate":   0x557F6828,   # TAnimateDeadCA           cell 0x557F67E8
    "unitspell": 0x557234B8,   # TUnitSpellCA             cell 0x55723478
}
CLASSREF_CELLS = {"round": 0x5571663C, "command": 0x55720360, "dispel_ab": 0x557219F4,
                  "prayer": 0x557F4490, "minddecay": 0x557F48C8, "slow": 0x557F4CEC,
                  "entspell": 0x557F4EC8, "terror": 0x557F60A0, "recall": 0x557F65EC,
                  "animate": 0x557F67E8, "unitspell": 0x55723478}
TLEADER_CELL = 0x557121F8

TENODE_CREATE = 0x557031A4   # Engine.TENode.Create thunk (eax=class, dl=1, ecx=0) -> new object
LISTENCH   = 0x5577F45C      # TAbstractUnit.ListEnchantments(eax=unit, edx=list); refs only, no copies
ENCH_FINDID = 0x5577C204     # TEnchantmentList.FindID(eax=list, edx=id) -> enchantment or 0
TOBJ_FREE  = 0x557010B8      # System.TObject.Free thunk (nil-safe)
ENCHLIST_CELL = 0x5570AA30   # classref cell of TEnchantmentList (holds its VMT)
RESBYTE    = 0x558E9A60      # DATA raw slack (P2's): ExecuteSpell result of the last TUnitSpellCA
                             # (0xFF = not reached); written by es_stub, reset by pre_unitspell and
                             # by build_combatlog_replays.py's c_pre

# Unit spells whose ExecuteSpell adds an ability with TAbilityOwner.ExpandAbility (`mov edx, id /
# mov eax, esi / mov ecx, [eax] / call [ecx+0x94]`): spell class VMT -> that ability id.  All but
# Haste return AL = 1 even when ExpandAbility refuses, so "receives" also needs the ability on the
# target after Execute.  Spells not listed (Remedy, Healing Water, Dispel Magic) go by AL alone.
# check_static() re-derives this from the live file and aborts on any difference.
UNITSPELL_AB = [
    (0x557E5534, 0x98),  # THaste
    (0x557E5664, 0x99),  # TStoneSkin
    (0x557E579C, 0x9A),  # TEnchantWeapon
    (0x557E58DC, 0x9D),  # TFreeMovement
    (0x557E5A1C, 0x9C),  # TFury
    (0x557E5DBC, 0xA0),  # THolyChampion
    (0x557E5EFC, 0xA1),  # TUnholyChampion
    (0x557E603C, 0xA2),  # TConcealment
    (0x557E617C, 0xA3),  # TFireAura
    (0x557E62B4, 0xA4),  # TWaterWalking
    (0x557E63F4, 0xA5),  # TWindWalking
    (0x557E6534, 0xA6),  # TLiquidForm
    (0x557E666C, 0x9E),  # TBless
    (0x557E679C, 0xA9),  # TDarkGift
    (0x557E69BC, 0x7E),  # TCosmeticSurgery
]
EXECUTE_CA = 0x5577B3B4      # TUnitSpell.ExecuteCA = vmt+0xBC of every unit spell


def unitspell_table(d):
    """[(VMT, ability id)] derived from the file: every VMT whose +0xBC is ExecuteCA and whose
    ExecuteSpell (+0xB4) carries the ExpandAbility pattern."""
    u32 = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    _e, secs = P.sections(d)
    vs, va, rs, raw = secs[0]
    out, base = [], P.IMAGE_BASE + va
    for i in range(0xBC, rs - 4, 4):
        if struct.unpack_from("<I", d, raw + i)[0] != EXECUTE_CA:
            continue
        vmt = base + i - 0xBC
        o = P.va2off(d, u32(vmt + 0xB4))
        m = re.search(rb"\xBA(....)\x8B\xC6\x8B\x08\xFF\x91\x94\x00\x00\x00", d[o:o + 0x80], re.S)
        if m:
            out.append((vmt, struct.unpack("<I", m.group(1))[0]))
    return sorted(out)


SENT_FRESH, SENT_BOUND = 0x7FFFFFF0, 0x7FFFFFF1   # build_command_bond.py
AB_WEBBED, AB_ENTANGLED, AB_PANICKED = 0x61, 0x5E, 0x6C
AB_EMBRITTLED, AB_SLOWENCH, SP_EMBRITTLE, SP_TERROR = 0xB2, 0x84, 0x6D, 0x69
CMD_VERB = {0x1C: "DOMINATED", 0x1D: "SEDUCED", 0x94: "CHARMED"}

# ---- hooks ---------------------------------------------------------------------------------
H_ECA, H_ECA_VAN, H_ECA_RES = 0x55727224, bytes.fromhex("5356 8bf2 8bd8".replace(" ", "")), 0x5572722A
H_CST, H_CST_VAN, H_CST_RES = 0x5577955C, bytes.fromhex("8bc88bd68bc3"), 0x55779562
H_ES, H_ES_VAN = 0x5577B41F, bytes.fromhex("ff97b4000000")   # TUnitSpell.ExecuteCA: call [edi+0xB4]
assert H_ECA_VAN == bytes.fromhex("53568bf28bd8")
# Fixed entry stubs at the slot base (jmp rel32 + 3 nop each): the hooks never move when the code
# is re-tuned, so a later --apply rewrites the slot in place (run() sees the hooks "installed").
STUB_CA, STUB_CAST, STUB_ES = SLOT[0], SLOT[0] + 8, SLOT[0] + 0x10
LIT_VA = SLOT[0] + 0x18

LITS = [
    ("Q", "?"), ("ROUND_A", "--- Round "), ("ROUND_B", " ---"),
    ("HEALS", " heals "), ("FOR", " for "),
    ("DRAINS", " drains "), ("HPFROM", " HP from "), ("GAINS", " gains "),
    ("DARKGIFT", " HP from Dark Gift"),
    ("POSSESSED", " is possessed by "), ("WEBBED", " is webbed by "),
    ("ENTANGLEDBY", " is entangled by "),
    ("INVOKES", " invokes death on "), ("DAMAGE", " damage"),
    ("DOMINATED", " is dominated by "), ("SEDUCED", " is seduced by "),
    ("CHARMED", " is charmed by "), ("COMMANDED", " is commanded by "),
    ("CANNOT", " cannot command "), ("ALEADER", " (a Leader)"),
    ("DISPELS", " dispels "), ("ENCH1", " enchantment from "), ("ENCHN", " enchantments from "),
    ("DISPNONE", " dispels nothing from "), ("BREAKS", " breaks the command on "),
    ("BLESSED", " is blessed by "), ("OPENPLUS", " (+"), ("HPCLOSE", " HP)"),
    ("TAKES", " takes control of "), ("OPEN", " ("), ("CLOSE", ")"),
    ("UNAFFECTED", " is unaffected by "),
    ("EMBRITTLED", " is embrittled ("), ("SLOWED", " is slowed ("),
    ("ENTANGLEDP", " is entangled ("), ("TERRIFIED", " is terrified ("),
    ("RECALLS", " recalls the spirit of "), ("RAISES", " raises "), ("FROMDEAD", " from the dead"),
    ("RECEIVES", " receives "),
    ("SPENDS", " spends "), ("MANAON", " mana on "),
]


def lstr(s):
    """Delphi const AnsiString: refcount -1, length, chars, NUL, 4-aligned."""
    b = struct.pack("<iI", -1, len(s)) + s.encode("latin1") + b"\0"
    return b + b"\0" * (-len(b) % 4)


LIT, _blob = {}, bytearray()
for _k, _s in LITS:
    LIT[_k] = LIT_VA + len(_blob) + 8
    _blob += lstr(_s)
_blob += b"\0" * (-len(_blob) % 4)
USTBL = LIT_VA + len(_blob)              # unit-spell table: (VMT - entry VA, ability id) x n, 0
for _i, (_vmt, _ab) in enumerate(UNITSPELL_AB):
    _blob += struct.pack("<iI", _vmt - (USTBL + 8 * _i), _ab)
_blob += b"\0" * 8
LIT_BLOB = bytes(_blob)
CODE_VA = (LIT_VA + len(LIT_BLOB) + 0xF) & ~0xF
GB_RET = CODE_VA + 5                     # get_base: call $+5 / pop edi / sub edi,(GB_RET-SLOT[0]) / ret
ES_VA = CODE_VA + 13                     # es_stub follows get_base (13 B)


def R(x):
    """DLL address x as an EDI-relative operand body (EDI = run-time slot base)."""
    o = x - SLOT[0]
    return "edi + 0x%X" % o if o >= 0 else "edi - 0x%X" % -o


def L(k):
    """Append literal k to the line."""
    return f"lea edx, [{R(LIT[k])}]\ncall h_lit\n"


def idname(off):
    """Append the name of the combat object whose id byte is at [esi+off] (ESI = CA)."""
    return f"movzx edx, byte ptr [esi+0x{off:X}]\ncall h_idn\n"


def spellname(src):
    """Append the name of spell id `src` (an operand)."""
    return f"mov edx, {src}\ncall h_spell\n"


def code():
    s = f"""
    get_base:
        call 0x{GB_RET:X}
        pop  edi
        sub  edi, 0x{GB_RET - SLOT[0]:X}
        ret

    /* ===================== SITE 3: TUnitSpell.ExecuteCA's ExecuteSpell call ===================== */
    /* entered by `call` from 0x5577B41F: [esp] ret, [esp+4] @CA+0x14, [esp+8] mana; EAX spell,
       EDX caster unit, ECX target unit, EDI = the spell's VMT.  Calls ExecuteSpell with the same two
       stack arguments, records AL, returns its EAX untouched and pops the caller's two arguments. */
    es_stub:
        push dword ptr [esp+8]
        push dword ptr [esp+8]
        call dword ptr [edi+0xB4]
        push edi
        call get_base
        mov  byte ptr [{R(RESBYTE)}], al
        pop  edi
        ret  8

    /* ===================== SITE 1: ExecuteCombatAction ===================== */
    ca_entry:
        push eax
        call 0x{CL_LIVE:X}
        test eax, eax
        pop  eax
        jz   ca_tramp
        push ebp
        mov  ebp, esp
        sub  esp, 0x20
        push ebx
        push esi
        push edi
        mov  [ebp-0x04], eax
        mov  [ebp-0x08], edx
        xor  eax, eax
        mov  [ebp-0x0C], eax
        mov  [ebp-0x10], eax
        mov  [ebp-0x14], eax
        mov  [ebp-0x18], eax
        mov  [ebp-0x1C], eax
        call get_base
        mov  esi, [ebp-0x08]
        test esi, esi
        jz   ca_run
        call pre
    ca_run:
        mov  eax, [ebp-0x04]
        mov  edx, [ebp-0x08]
        call ca_tramp
        mov  [ebp-0x20], eax
        cmp  dword ptr [ebp-0x1C], 0
        je   ca_done
        mov  esi, [ebp-0x08]
        call post
    ca_done:
        mov  eax, [ebp-0x20]
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    ca_tramp:
        push ebx
        push esi
        mov  esi, edx
        mov  ebx, eax
        jmp  0x{H_ECA_RES:X}

    /* ===================== SITE 2: CombatSpellCast mana ===================== */
    cast_entry:
        push eax
        call 0x{CL_LIVE:X}
        test eax, eax
        jz   cast_out
        push ebp
        mov  ebp, esp
        sub  esp, 0x20
        push edi
        xor  eax, eax
        mov  [ebp-0x0C], eax
        mov  [ebp-0x10], eax
        mov  [ebp-0x14], eax
        call get_base
        mov  eax, esi
        call h_obj
        {L('SPENDS')}
        mov  edx, [ebp+0x04]
        call h_int
        {L('MANAON')}
        mov  edx, [ebx+0x08]
        test edx, edx
        jz   cast_noname
        call h_lit
        jmp  cast_done
    cast_noname:
        {L('Q')}
    cast_done:
        call h_emit
        pop  edi
        mov  esp, ebp
        pop  ebp
    cast_out:
        pop  eax
        mov  ecx, eax
        mov  edx, esi
        mov  eax, ebx
        jmp  0x{H_CST_RES:X}

    /* ===================== helpers (EBP = an entry frame, EDI = base) ===================== */
    h_lit:
        lea  eax, [ebp-0x0C]
        jmp  0x{LSTRCAT:X}
    h_int:
        lea  eax, [ebp-0x0C]
        jmp  0x{CL_CAT_INT:X}
    h_obj:
        lea  edx, [ebp-0x10]
        call 0x{CL_NAME:X}
        mov  edx, [ebp-0x10]
        jmp  h_lit
    h_id:
        mov  eax, [ebp-0x04]
        mov  eax, [eax+0x0C]
        test eax, eax
        jz   h_id_z
        jmp  0x{FINDID:X}
    h_id_z:
        ret
    h_idn:
        call h_id
        jmp  h_obj
    h_hp:
        test eax, eax
        jz   h_hp_z
        mov  edx, [eax]
        call dword ptr [edx+0x{GETHP_V:X}]
        movsx eax, al
        ret
    h_hp_z:
        xor  eax, eax
        ret
    h_has:
        test eax, eax
        jz   h_has_z
        push edx
        push eax
        lea  edx, [{R(TCOMBATUNIT_VMT)}]
        call 0x{IS_CLASS:X}
        test al, al
        pop  eax
        pop  edx
        jz   h_has_z
        mov  ecx, [eax]
        call dword ptr [ecx+0x{HASAB_V:X}]
        movzx eax, al
        ret
    h_has_z:
        xor  eax, eax
        ret
    h_spell:
        test edx, edx
        js   h_spell_q
        mov  eax, [{R(AOWHSSET)}]
        test eax, eax
        jz   h_spell_q
        mov  eax, [eax+0x84]
        test eax, eax
        jz   h_spell_q
        call 0x{GETSPELL:X}
        test eax, eax
        jz   h_spell_q
        mov  edx, [eax+0x08]
        test edx, edx
        jz   h_spell_q
        jmp  h_lit
    h_spell_q:
        lea  edx, [{R(LIT['Q'])}]
        jmp  h_lit
    h_iscu:                     /* EAX = object / nil -> AL = IsClass(TCombatUnit) */
        lea  edx, [{R(TCOMBATUNIT_VMT)}]
        jmp  0x{IS_CLASS:X}
    h_emit:
        mov  eax, [ebp-0x0C]
        call 0x{CL_EMIT:X}
        lea  eax, [ebp-0x14]
        mov  edx, 3
        jmp  0x{LSTRARRCLR:X}

    /* ===================== PRE dispatch (ESI = CA) ===================== */
    pre:
        mov  ebx, [esi]
    """
    order = ["round", "heal", "strike", "possess", "web", "entangle", "invoke", "command",
             "dispel_ab", "dispel_sp", "prayer", "minddecay", "slow", "entspell", "terror",
             "recall", "animate", "unitspell"]
    for k in order:
        s += f"""
        lea  eax, [{R(VMT[k])}]
        cmp  ebx, eax
        je   pre_{k}"""
    s += "\n        ret\n"

    s += f"""
    pre_round:
        mov  eax, [ebp-0x04]
        mov  eax, [eax+0x0C]
        test eax, eax
        jz   pre_ret
        mov  ebx, [eax+0x44]
        inc  ebx
        {L('ROUND_A')}
        mov  edx, ebx
        call h_int
        {L('ROUND_B')}
        jmp  h_emit
    pre_ret:
        ret

    pre_heal:
        movzx edx, byte ptr [esi+0x0E]
        call h_id
        call h_hp
        mov  [ebp-0x18], eax
        mov  dword ptr [ebp-0x1C], 1
        ret

    pre_strike:
        test byte ptr [esi+0x18], 0x18
        jz   pre_ret
        movzx edx, byte ptr [esi+0x0D]
        call h_id
        call h_hp
        mov  [ebp-0x18], eax
        mov  dword ptr [ebp-0x1C], 2
        ret

    pre_possess:
        cmp  byte ptr [esi+0x10], 0
        je   pre_ret
        {idname(0x0E)}
        {L('POSSESSED')}
        {idname(0x0D)}
        jmp  h_emit

    pre_web:
        cmp  byte ptr [esi+0x10], 0
        je   pre_ret
        mov  dword ptr [ebp-0x1C], 3
        ret

    pre_entangle:
        cmp  byte ptr [esi+0x10], 0
        je   pre_ret
        mov  dword ptr [ebp-0x1C], 4
        ret

    pre_invoke:
        cmp  byte ptr [esi+0x10], 0
        je   pre_ret
        movzx edx, byte ptr [esi+0x0E]
        call h_id
        call h_hp
        mov  ebx, eax
        {idname(0x0D)}
        {L('INVOKES')}
        {idname(0x0E)}
        {L('FOR')}
        mov  edx, ebx
        call h_int
        {L('DAMAGE')}
        jmp  h_emit

    pre_command:
        cmp  byte ptr [esi+0x14], 0
        je   pre_cmd_fail
        {idname(0x0E)}
        mov  eax, [esi+0x10]
        lea  edx, [{R(LIT['COMMANDED'])}]
        cmp  eax, 0x1C
        jne  pre_cmd_1
        lea  edx, [{R(LIT['DOMINATED'])}]
    pre_cmd_1:
        cmp  eax, 0x1D
        jne  pre_cmd_2
        lea  edx, [{R(LIT['SEDUCED'])}]
    pre_cmd_2:
        cmp  eax, 0x94
        jne  pre_cmd_3
        lea  edx, [{R(LIT['CHARMED'])}]
    pre_cmd_3:
        call h_lit
        {idname(0x0D)}
        jmp  h_emit
    pre_cmd_fail:
        movzx edx, byte ptr [esi+0x0E]
        call h_id
        test eax, eax
        jz   pre_ret
        mov  ebx, eax
        lea  edx, [{R(TCOMBATUNIT_VMT)}]
        call 0x{IS_CLASS:X}
        test al, al
        jz   pre_ret
        mov  eax, [ebx+0x4C]
        test eax, eax
        jz   pre_ret
        lea  edx, [{R(TLEADER_VMT)}]
        call 0x{IS_CLASS:X}
        test al, al
        jz   pre_ret
        {idname(0x0D)}
        {L('CANNOT')}
        mov  eax, ebx
        call h_obj
        {L('ALEADER')}
        jmp  h_emit

    /* dispel: EBX = what Execute will remove, [ebp-0x18] = sentinel seen, [ebp-0x1C] stays 0 */
    pre_dispel_ab:
        xor  ecx, ecx
        jmp  pre_dispel
    pre_dispel_sp:
        mov  ecx, 1
    pre_dispel:
        push ecx
        call dsp_count
        pop  ecx
        test ebx, ebx
        jnz  pre_dsp_some
        cmp  dword ptr [ebp-0x18], 0
        jne  pre_dsp_bond
        test ecx, ecx
        jz   pre_ret
        {idname(0x0D)}
        {L('DISPNONE')}
        {idname(0x0E)}
        jmp  h_emit
    pre_dsp_some:
        {idname(0x0D)}
        {L('DISPELS')}
        mov  edx, ebx
        call h_int
        lea  edx, [{R(LIT['ENCHN'])}]
        cmp  ebx, 1
        jne  pre_dsp_pl
        lea  edx, [{R(LIT['ENCH1'])}]
    pre_dsp_pl:
        call h_lit
        {idname(0x0E)}
        call h_emit
        cmp  dword ptr [ebp-0x18], 0
        je   pre_dsp_end
    pre_dsp_bond:
        {idname(0x0D)}
        {L('BREAKS')}
        {idname(0x0E)}
        call h_emit
    pre_dsp_end:
        mov  dword ptr [ebp-0x18], 0
        ret

    /* dsp_count (ESI = CA): EBX := the success-list ids TEnchantmentList.FindID finds on the
       target's enchantments now -- exactly the entries TDispelMagicCA.Execute will dispel, behind
       the same guards (both objects TCombatUnit; else Execute removes nothing and skips the bond
       code); [ebp-0x18] := 1 if a build_command_bond.py sentinel is listed.  The list is built and
       freed the way Execute and Generate build theirs (references only). */
    dsp_count:
        xor  ebx, ebx
        mov  dword ptr [ebp-0x18], 0
        movzx edx, byte ptr [esi+0x0D]
        call h_id
        call h_iscu
        test al, al
        jz   dc_ret
        movzx edx, byte ptr [esi+0x0E]
        call h_id
        push eax
        call h_iscu
        pop  edx
        test al, al
        jz   dc_ret
        mov  eax, [edx+0x4C]
        test eax, eax
        jz   dc_ret
        mov  ecx, [esi+0x10]
        test ecx, ecx
        jz   dc_ret
        push eax
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, [{R(ENCHLIST_CELL)}]
        call 0x{TENODE_CREATE:X}
        pop  edx
        push eax
        xchg eax, edx
        call 0x{LISTENCH:X}
        mov  eax, [esi+0x10]
        mov  ecx, [eax+0x08]
    dc_loop:
        dec  ecx
        js   dc_done
        push ecx
        mov  edx, ecx
        mov  eax, [esi+0x10]
        call 0x{INTLIST_GET:X}
        cmp  eax, 0x{SENT_FRESH:X}
        je   dc_sent
        cmp  eax, 0x{SENT_BOUND:X}
        je   dc_sent
        mov  edx, eax
        mov  eax, [esp+4]
        call 0x{ENCH_FINDID:X}
        test eax, eax
        jz   dc_next
        inc  ebx
        jmp  dc_next
    dc_sent:
        mov  dword ptr [ebp-0x18], 1
    dc_next:
        pop  ecx
        jmp  dc_loop
    dc_done:
        pop  eax
        call 0x{TOBJ_FREE:X}
    dc_ret:
        ret

    pre_prayer:
        cmp  byte ptr [esi+0x14], 0
        je   pre_ret
        movzx edx, byte ptr [esi+0x0D]
        call h_id
        call h_hp
        mov  [ebp-0x18], eax
        mov  dword ptr [ebp-0x1C], 5
        ret

    pre_minddecay:
        cmp  byte ptr [esi+0x14], 0
        je   pre_unaffected_d
        {idname(0x0C)}
        {L('TAKES')}
        {idname(0x0D)}
        {L('OPEN')}
        {spellname('[esi+0x18]')}
        {L('CLOSE')}
        jmp  h_emit
    pre_unaffected_d:
        {idname(0x0D)}
        {L('UNAFFECTED')}
        {spellname('[esi+0x18]')}
        jmp  h_emit

    pre_slow:
        mov  dword ptr [ebp-0x1C], 6
        ret
    pre_entspell:
        mov  dword ptr [ebp-0x1C], 7
        ret
    pre_terror:
        mov  dword ptr [ebp-0x1C], 8
        ret

    pre_recall:
        cmp  byte ptr [esi+0x14], 0
        je   pre_ret
        {idname(0x0C)}
        {L('RECALLS')}
        {idname(0x0D)}
        jmp  h_emit

    pre_animate:
        cmp  byte ptr [esi+0x14], 0
        je   pre_ret
        {idname(0x0C)}
        {L('RAISES')}
        {idname(0x0D)}
        {L('FROMDEAD')}
        jmp  h_emit

    pre_unitspell:
        mov  byte ptr [{R(RESBYTE)}], 0xFF
        mov  dword ptr [ebp-0x1C], 9
        ret

    /* ===================== POST dispatch (ESI = CA, [ebp-0x1C] = kind) ===================== */
    post:
        mov  eax, [ebp-0x1C]
        cmp  eax, 1
        je   post_heal
        cmp  eax, 2
        je   post_strike
        cmp  eax, 3
        je   post_web
        cmp  eax, 4
        je   post_entangle
        cmp  eax, 5
        je   post_prayer
        cmp  eax, 6
        je   post_slow
        cmp  eax, 7
        je   post_entspell
        cmp  eax, 8
        je   post_terror
        cmp  eax, 9
        je   post_unitspell
    post_ret:
        ret

    /* TUnitSpellCA: es_stub recorded ExecuteSpell's AL; 0 or 0xFF (ExecuteCA bailed: caster or
       target not a TCombatUnit) = nothing happened.  AL = 1 and the spell's class is in USTBL: it
       took effect only if that ability is now on the target (EBX := GetAbilityEnabled). */
    post_unitspell:
        movzx ebx, byte ptr [{R(RESBYTE)}]
        cmp  ebx, 1
        jne  post_us_say
        mov  edx, [esi+0x0C]
        test edx, edx
        js   post_us_say
        mov  eax, [{R(AOWHSSET)}]
        test eax, eax
        jz   post_us_say
        mov  eax, [eax+0x84]
        test eax, eax
        jz   post_us_say
        call 0x{GETSPELL:X}
        test eax, eax
        jz   post_us_say
        mov  eax, [eax]
        lea  edx, [{R(USTBL)}]
    post_us_lp:
        mov  ecx, [edx]
        test ecx, ecx
        jz   post_us_say
        add  ecx, edx
        cmp  ecx, eax
        je   post_us_hit
        add  edx, 8
        jmp  post_us_lp
    post_us_hit:
        push dword ptr [edx+4]
        movzx edx, byte ptr [esi+0x11]
        call h_id
        pop  edx
        call h_has
        mov  ebx, eax
    post_us_say:
        {idname(0x11)}
        lea  edx, [{R(LIT['UNAFFECTED'])}]
        cmp  ebx, 1
        jne  post_us_1
        lea  edx, [{R(LIT['RECEIVES'])}]
    post_us_1:
        call h_lit
        {spellname('[esi+0x0C]')}
        jmp  h_emit

    post_heal:
        movzx edx, byte ptr [esi+0x0E]
        call h_id
        call h_hp
        sub  eax, [ebp-0x18]
        mov  ebx, eax
        {idname(0x0D)}
        {L('HEALS')}
        {idname(0x0E)}
        test ebx, ebx
        jle  post_heal_end
        {L('FOR')}
        mov  edx, ebx
        call h_int
    post_heal_end:
        jmp  h_emit

    post_strike:
        movzx edx, byte ptr [esi+0x0D]
        call h_id
        call h_hp
        sub  eax, [ebp-0x18]
        movzx edx, byte ptr [esi+0x16]
        add  eax, edx
        jns  post_st_pos
        xor  eax, eax
    post_st_pos:
        mov  [ebp-0x18], eax
        test byte ptr [esi+0x18], 8
        jz   post_st_dg
        mov  ebx, [ebp-0x18]
        cmp  ebx, 4
        jle  post_st_ls
        mov  ebx, 4
    post_st_ls:
        sub  [ebp-0x18], ebx
        test ebx, ebx
        jle  post_st_dg
        {idname(0x0D)}
        {L('DRAINS')}
        mov  edx, ebx
        call h_int
        {L('HPFROM')}
        {idname(0x0E)}
        call h_emit
    post_st_dg:
        test byte ptr [esi+0x18], 0x10
        jz   post_ret
        mov  ebx, [ebp-0x18]
        cmp  ebx, 3
        jle  post_st_dg2
        mov  ebx, 3
    post_st_dg2:
        test ebx, ebx
        jle  post_ret
        {idname(0x0D)}
        {L('GAINS')}
        mov  edx, ebx
        call h_int
        {L('DARKGIFT')}
        jmp  h_emit

    post_web:
        movzx edx, byte ptr [esi+0x0E]
        call h_id
        mov  edx, 0x{AB_WEBBED:X}
        call h_has
        test eax, eax
        jz   post_ret
        {idname(0x0E)}
        {L('WEBBED')}
        {idname(0x0D)}
        jmp  h_emit

    post_entangle:
        movzx edx, byte ptr [esi+0x0E]
        call h_id
        mov  edx, 0x{AB_ENTANGLED:X}
        call h_has
        test eax, eax
        jz   post_ret
        {idname(0x0E)}
        {L('ENTANGLEDBY')}
        {idname(0x0D)}
        jmp  h_emit

    post_prayer:
        movzx edx, byte ptr [esi+0x0D]
        call h_id
        call h_hp
        sub  eax, [ebp-0x18]
        mov  ebx, eax
        {idname(0x0D)}
        {L('BLESSED')}
        {spellname('[esi+0x18]')}
        test ebx, ebx
        jle  post_pr_end
        {L('OPENPLUS')}
        mov  edx, ebx
        call h_int
        {L('HPCLOSE')}
    post_pr_end:
        jmp  h_emit

    /* status spells: EBX = status id, [ebp-0x18] = spell id, ECX-free verb in [ebp-0x1C] */
    post_slow:
        mov  ebx, 0x{AB_SLOWENCH:X}
        lea  eax, [{R(LIT['SLOWED'])}]
        cmp  dword ptr [esi+0x18], 0x{SP_EMBRITTLE:X}
        jne  post_slow_1
        mov  ebx, 0x{AB_EMBRITTLED:X}
        lea  eax, [{R(LIT['EMBRITTLED'])}]
    post_slow_1:
        mov  [ebp-0x1C], eax
        mov  eax, [esi+0x18]
        mov  [ebp-0x18], eax
        jmp  post_status
    post_entspell:
        mov  ebx, 0x{AB_ENTANGLED:X}
        lea  eax, [{R(LIT['ENTANGLEDP'])}]
        mov  [ebp-0x1C], eax
        mov  eax, [esi+0x18]
        mov  [ebp-0x18], eax
        jmp  post_status
    post_terror:
        mov  ebx, 0x{AB_PANICKED:X}
        lea  eax, [{R(LIT['TERRIFIED'])}]
        mov  [ebp-0x1C], eax
        mov  dword ptr [ebp-0x18], 0x{SP_TERROR:X}
    post_status:
        cmp  byte ptr [esi+0x14], 0
        je   post_unaff
        movzx edx, byte ptr [esi+0x0D]
        call h_id
        mov  edx, ebx
        call h_has
        test eax, eax
        jz   post_unaff
        {idname(0x0D)}
        mov  edx, [ebp-0x1C]
        call h_lit
        {spellname('[ebp-0x18]')}
        {L('CLOSE')}
        jmp  h_emit
    post_unaff:
        {idname(0x0D)}
        {L('UNAFFECTED')}
        {spellname('[ebp-0x18]')}
        jmp  h_emit
    """
    return s


def build():
    src = code()
    blob = asm(src, CODE_VA)
    # Both entries, and nothing else, start `push eax / call cl_live`; find them in the image
    # (keystone reports no label addresses).  Source order: ca_entry, then cast_entry.
    ent = [CODE_VA + i for i in range(len(blob) - 6)
           if blob[i] == 0x50 and blob[i + 1] == 0xE8
           and struct.unpack_from("<i", blob, i + 2)[0] == CL_LIVE - (CODE_VA + i + 6)]
    assert len(ent) == 2, "expected exactly two entries, found %s" % [hex(e) for e in ent]
    assert blob[ES_VA - CODE_VA:ES_VA - CODE_VA + 8] == bytes.fromhex("ff742408ff742408"), \
        "es_stub is not where the stub table expects it"
    return blob, ent[0], ent[1]


CODE, CA_ENTRY, CAST_ENTRY = build()
STUBS = (jmp_to(STUB_CA, CA_ENTRY, 8) + jmp_to(STUB_CAST, CAST_ENTRY, 8) + jmp_to(STUB_ES, ES_VA, 8))
CAVES = [("entry stubs", SLOT[0], STUBS), ("literals", LIT_VA, LIT_BLOB), ("code", CODE_VA, CODE)]
assert CODE_VA + len(CODE) <= SLOT[1], "code overflows the slot"

HOOKS = [(H_ECA, H_ECA_VAN, jmp_to(H_ECA, STUB_CA, len(H_ECA_VAN))),
         (H_CST, H_CST_VAN, jmp_to(H_CST, STUB_CAST, len(H_CST_VAN))),
         (H_ES, H_ES_VAN, b"\xE8" + struct.pack("<i", STUB_ES - (H_ES + 5)) + b"\x90")]
INTERIOR = [(H_ECA, H_ECA + len(H_ECA_VAN), 0x55727224, 0x55727249),
            (H_CST, H_CST + len(H_CST_VAN), 0x5577954C, 0x5577956A),
            (H_ES, H_ES + len(H_ES_VAN), 0x5577B3B4, 0x5577B460)]


def check_pic():
    """Clean disassembly; one call/pop anchor (get_base) whose sub constant matches; every call
    target is a known routine or inside the code; no absolute DLL operand or immediate."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    ins = list(md.disasm(CODE, CODE_VA))
    assert sum(len(x.bytes) for x in ins) == len(CODE), "code does not disassemble cleanly"
    assert ins[0].mnemonic == "call" and int(ins[0].op_str, 16) == GB_RET
    assert ins[1].mnemonic == "pop" and ins[1].op_str == "edi"
    assert ins[2].mnemonic == "sub" and int(ins[2].op_str.split(",")[1], 16) == GB_RET - SLOT[0]
    known = {CL_EMIT, CL_NAME, CL_LIVE, CL_CAT_INT, IS_CLASS, LSTRCAT, LSTRARRCLR, FINDID,
             INTLIST_GET, GETSPELL, GB_RET, CODE_VA, H_ECA_RES, H_CST_RES,
             TENODE_CREATE, LISTENCH, ENCH_FINDID, TOBJ_FREE}
    for x in ins:
        if x.mnemonic in ("call", "jmp") or x.mnemonic.startswith("j"):
            try:
                t = int(x.op_str, 16)
            except ValueError:
                assert x.op_str.startswith("dword ptr [e"), "%08X %s %s" % (x.address, x.mnemonic, x.op_str)
                continue
            assert t in known or CODE_VA <= t < CODE_VA + len(CODE), \
                "%08X: branch to unexpected %08X" % (x.address, t)
        for m in re.finditer(r"\[(0x[0-9a-f]+)\]", x.op_str):
            sys.exit("ABORT: absolute operand at %08X: %s" % (x.address, x.op_str))
        if re.search(r"0x55[0-9a-f]{6}", x.op_str) and x.mnemonic not in ("call", "jmp") \
                and not x.mnemonic.startswith("j"):
            sys.exit("ABORT: DLL address as an immediate at %08X: %s %s" % (x.address, x.mnemonic, x.op_str))
        if x.mnemonic == "push" and x.op_str.startswith("0x"):
            sys.exit("ABORT: push imm at %08X (keystone imm8 trap)" % x.address)


check_pic()


def check_static(d):
    """Facts this build relies on, read from the live file before anything is written."""
    u32 = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    for k, cell in CLASSREF_CELLS.items():
        assert u32(cell) == VMT[k], "classref cell %08X no longer holds %s's VMT" % (cell, k)
    assert u32(TLEADER_CELL) == TLEADER_VMT, "TLeader classref moved"
    assert u32(TCOMBATUNIT_VMT + GETHP_V) == 0x55725064, "TCombatUnit.GetHitPoints slot moved"
    assert u32(TCOMBATUNIT_VMT + HASAB_V) == 0x55725004, "TCombatUnit.GetAbilityEnabled slot moved"
    # TNewCombatRoundCA.Execute still increments the round first thing (PRE emits round + 1)
    o = P.va2off(d, 0x5572A398)
    assert d[o:o + 10] == bytes.fromhex("53568bf28b460cff4044"), "TNewCombatRoundCA.Execute changed"
    # TUnitSpell.ExecuteCA pushes exactly two arguments for ExecuteSpell (es_stub copies two)
    o = P.va2off(d, 0x5577B40B)
    assert d[o:o + 0x14] == bytes.fromhex("8b431c508d4314508b4f4c8b564c8b4424088b38"), \
        "TUnitSpell.ExecuteCA's ExecuteSpell call frame changed"
    assert u32(0x55723590 + 0xBC) == 0x5577B3B4, "TUnitSpell vmt+0xBC is no longer ExecuteCA"
    # dispel helpers: TDispelMagicCA.Execute still builds its list this way and dispels by FindID
    o = P.va2off(d, 0x5576CAB7)
    assert d[o:o + 0x1E] == bytes.fromhex("33c9b201a130aa7055e8df66f9ff8904248bdf8b434c8b1424e887290100"), \
        "TDispelMagicCA.Execute changed"
    o = P.va2off(d, u32(u32(ENCHLIST_CELL) - 0x20))
    assert d[o + 1:o + 1 + d[o]] == b"TEnchantmentList", "ENCHLIST_CELL is not TEnchantmentList's classref"
    live = unitspell_table(d)
    assert live == sorted(UNITSPELL_AB), "unit-spell ability table differs from the file: %s" \
        % [(hex(v), hex(a)) for v, a in live]
    # the result byte is file-zero, reloc-free DATA slack
    o = P.va2off(d, RESBYTE)
    assert d[o] == 0 and not P.relocs_in(d, RESBYTE, RESBYTE + 1), "RESBYTE is not free DATA slack"
    # the library this script calls is installed
    import importlib
    lib = importlib.import_module("build_combatlog_lib")
    lo = P.va2off(d, lib.SLOT[0])
    assert d[lo:lo + len(lib.IMAGE)] == lib.IMAGE, "build_combatlog_lib.py is not installed"
    # build_command_bond.py's sentinels
    here = os.path.dirname(os.path.abspath(__file__))
    t = open(os.path.join(here, "build_command_bond.py")).read()
    assert re.search(r"SENT_FRESH, SENT_BOUND = 0x7FFFFFF0, 0x7FFFFFF1", t), "bond sentinels changed"


if __name__ == "__main__":
    _d = open(P.TARGET, "rb").read()
    check_static(_d)
    print("  entries: ca_entry %08X, cast_entry %08X; code %08X-%08X (%d B), literals %d B"
          % (CA_ENTRY, CAST_ENTRY, CODE_VA, CODE_VA + len(CODE), len(CODE), len(LIT_BLOB)))
    run("build_combatlog_actions", HOOKS, CAVES, SLOT, INTERIOR, sys.argv[1:])
