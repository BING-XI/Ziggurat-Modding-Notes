#!/usr/bin/env python
r"""
build_combatlog_replays.py -- combat log in REPLAYS: every non-damage combat action, deaths, strike
side-effects and round markers.  AoWEPACK.dpl only.  Combat-log package P6, 2026-10-14;
v2 the same day (owner: replay lines use the live wording; outcomes printed only when they happened).

Covers any re-opened battle replay and the viewer that plays straight after an auto-resolve (both are
TCombatViewer, driven by AoWz.exe's fast-combat window).  Damage lines already print from
build_replaylog.py (TDamageCA.Play / TCombatSpellCA.Play hooks) and Razor Plate's cut from
build_razorplate.py's TStrikeCA Play wrapper; this script never prints either again.

LINES -- the wording of build_combatlog_actions.py (live, P2) and build_combatlog_endings.py (P3);
check_targets() asserts every literal the two scripts share is spelled identically.
    --- Round 3 ---
    Priest heals Swordsman for 6                no HP change: "Priest heals Swordsman" (same rule live)
    Vampire drains 4 HP from Swordsman          strike flag 08: min(gain, 4)
    Vampire gains 3 HP from Dark Gift           strike flag 10: min(rest of the gain, 3)
    Shadow is panicked / Shadow is entangled    Cause Fear / Entangle Strike landed, target alive
    Swordsman is possessed by Spirit            Spirit fails to possess Swordsman
    Swordsman is webbed by Spider               only if Webbed (0x61) is on the target after Play;
    Swordsman is entangled by Treant            Entangled (0x5E) likewise; failure: "fails to web/entangle"
    Lich invokes death on Swordsman for 6 damage    (the target's HP before);  "fails to invoke death on"
    Knight is charmed by Nymph                  dominated 0x1C / seduced 0x1D / charmed 0x94, else
                                                "commanded"; failure "Nymph fails to charm Knight"
    Siren cannot command Lord Varn (a Leader)   failed TCommandCA whose target's unit IsClass TLeader
    Druid dispels 2 enchantments from Swordsman the success-list ids TEnchantmentList.FindID finds
    Mage dispels nothing from Swordsman         (spell only; an ability that removes nothing is silent)
    Druid breaks the command on Swordsman       build_command_bond.py's sentinel in the success list
    Swordsman receives Haste                    TUnitSpellCA whose ExecuteSpell returned true and (15
                                                ExpandAbility spells) whose ability is now on the target
    Swordsman is unaffected by Haste            otherwise
    Swordsman is blessed by High Prayer (+3 HP) success only (no "(+N HP)" when HP did not change)
    Shaman takes control of Ogre (Mind Decay)   failure: "Ogre is unaffected by Mind Decay"
    Ogre is slowed (Lethargy) / embrittled (Embrittle) / entangled (Entangle) / terrified (Terror)
                                                success byte AND the status on the target after Play,
                                                else "Ogre is unaffected by <Spell>"
    Necromancer recalls the spirit of Ghoul     success only
    Necromancer raises Ghoul from the dead      success only
    Mage casts High Prayer                      auto-resolve multi-target High Prayer / Terror (no
                                                live counterpart: auto-resolve is not logged live)
    Halfling flees the battle
    Shadow is slain                             any unit (self-destruct included, as live)
    The Wall is breached                        a non-unit object (cl_name "Wall") at 0 HP, as P4 live
Not reproduced: the live touch-roll line ("fails to Possess X - resisted (60%, ...)"): the replay
holds no roll; the replay prints the outcome line only.  The live mana line ("spends 12 mana on X")
comes from TSpell.CombatSpellCast, which a replay never runs.

THE HOOK -- one site, TCombatViewer.Update @0x55729610, its only Play dispatch
    0x55729672  8B D6 8B 08 FF 51 54   mov edx,esi / mov ecx,[eax] / call [ecx+0x54]   (7 B, reloc-free,
                no jump lands inside it) -> jmp 0x5589E000 (fixed entry stub -> c_entry) + 2 nop.
                EAX = the CA, ESI = the viewer, [ESI+0x14] = the action's tick (-1 -> 0 just before
                its first Play, 0x55729660), so [ESI+0x14]==0 runs once per action.  Play returns
                AL = 0 when the action is finished; Play runs Execute (vmt+0x50) inside it.
    c_entry     tick 0: call c_pre (before Play, so before Execute)  ->  the original Play call, with
                the CA kept on the stack  ->  AL == 0: call c_post (ECX = that CA)  ->  jmp 0x55729679.
                The displaced bytes are re-done verbatim; after 0x55729679 vanilla reads only EAX.
    Play is reached only from here, and TCombatViewer is imported only by AoWz.exe (no other module
    imports it or GetCombatActions), so none of this runs in a live battle; a slider seek
    (TCombatViewer.SetPosition) Executes without Play and prints nothing, as build_replaylog.py.

DISPATCH -- by EXACT VMT through a 27-entry table (7 B each: VMT - table as a signed 24-bit value,
kind, attacker-id offset, target-id offset, extra; ends in 4 zero bytes).  Classes not in it print
nothing (TNewCombatTurnCA, TCombatObjectTurnDoneCA, TUpdateHeaderCA, TMoveWallCA -- a gate
opening/closing -- and TDamageEffectCA, which nothing builds).  Field offsets, each from that class's
ReadWrite/Execute:
    TSingleTargetCA family     +0x0D attacker id, +0x0E target id; TStrikeCA +0x18 flags (tag 0x14),
                               +0x16 Razor Plate cut (build_razorplate.py)
    TWebCA/TEntangleCA/TPossessCA/TInvokeDeathCA   +0x10 success (bool, tag 0x14)
    TCommandCA                 +0x10 ability id (dword), +0x14 success
    TDispelMagicCA family      +0x10 TIntegerList of the enchantment ids whose dispel roll passed
                               (Generate); Execute dispels only those TEnchantmentList.FindID finds
    TUnitSpellCA               +0x0C spell id, +0x10 caster id, +0x11 target id, +0x14 8 B argument
                               block handed to ExecuteSpell (only Cosmetic Surgery reads it: the new
                               appearance), +0x1C mana (CreateCA's flag: spent by CombatCastingDone
                               on success when [combat+8] bit 0)
    TExclusiveCombatSpellCA    +0x0C caster, +0x0D target, +0x10 mana, +0x14 success, +0x18 spell id
    TTacticalCombatTerrorCA    +0x0C caster, +0x0D target, +0x10 mana, +0x14 success (spell 0x69)
    TMultiTargetCombatSpellCA  +0x0C caster, +0x10 target list, +0x14 mana, +0x18 bool, +0x1C spell id
    TFleeCA                    +0x0C unit id
    THealingCA                 +0x0D healer, +0x0E target (no amount stored: HP diff)
    TNewCombatRoundCA          none; Execute increments [TCombatData+0x44] = the round shown

TUnitSpellCA OUTCOME -- can a unit enchantment fail?  Yes, with no roll: TUnitSpellCA.Execute ->
    spell vmt+0xBC = TUnitSpell.ExecuteCA @0x5577B3B4 (every unit spell; no override) -> requires both
    ids to be TCombatUnits, then spell vmt+0xB4 ExecuteSpell(caster unit, target unit, @CA+0x14,
    [CA+0x1C]) -> AL.  Each override first asks its ValidTargetUnit (vmt+0x9C; e.g. Haste refuses a
    target that already has 0x98) and then TAbilityOwner.ExpandAbility (vmt+0x94), returning 0 if
    either refuses; Remedy / Healing Water return 1 once ValidTargetUnit passes.  ExecuteCA throws
    the AL away, so build_combatlog_actions.py hooks its `call [edi+0xB4]` (0x5577B41F) with es_stub,
    which writes AL to RESBYTE (DATA 0x558E9A60).  All ExpandAbility spells but Haste return 1 even
    when ExpandAbility refuses, so for the class VMTs in UNITSPELL_AB (imported from that script) the
    ability must also be on the target after Play.  c_pre sets RESBYTE := 0xFF before Play; c_post
    prints "receives" / "is unaffected by" accordingly, and nothing for 0xFF (ExecuteCA bailed, or
    build_combatlog_actions.py is not installed).

c_pre (tick 0)  FindID both ids on [[viewer+8]+0xC]; names via cl_name into two LStr slots in the
                state block (fetched BEFORE Execute: TPossessCA moves the target's unit into the
                possessor, and a dead object's unit link is not relied on); alive = [obj+0x47] bit 0
                clear; HP = TCombatUnit vmt+0x88 (behind IsClass).  Lines whose facts are known before
                Execute print here; kinds with an after-state are remembered as PENDING (the CA).
                Dispel counts and the Leader test run here (the unit links are intact before Execute).
c_post          (Play returned 0, CA == pending)  round, heal, strike side-effects, web/entangle and
                status-spell checks (TCombatUnit vmt+0xA8 GetAbilityEnabled behind IsClass), the unit
                spell outcome, then deaths: target first, then attacker, each only on an alive -> dead
                transition.  Life-steal gain = attacker HP now - before + the Razor Plate cut (+0x16).
c_line          EAX = a list of (type, value) dword pairs ending in type 0: 1 shortstring literal,
                2 @LStr variable, 3 integer, 4 spell id (< 0: nothing; GetSpell([AoWHSSet]+0x84, id)
                -> +0x08, never with a negative id: it raises).  The line is built as a shortstring in
                the frame (cut at 255), turned into an LStr with System.@LStrFromString and handed to
                cl_emit_replay (build_combatlog_lib.py).  Callers push the list on the stack.

WRITABLE STATE -- AoWEPACK DATA raw slack 0x558E9B60-0x558E9B9F (assigned to this package; RW,
file-backed zero, inside DATA's mapped page past its VirtualSize)
    +00 pending CA   +04 kind/aoff/toff/extra   +08 TCombatData   +0C attacker id  +0D target id
    +0E bits (1 attacker alive, 2 target alive, 4 attacker present, 8 target present)
    +10 attacker name LStr   +14 target name LStr   +18 attacker HP   +1C target HP
    +20 dispel: a command-bond sentinel is listed
The two LStr slots keep the last names between actions (one string each, released on the next
assignment by the VCL).  Also writes RESBYTE 0x558E9A60 (build_combatlog_actions.py's DATA; 0xFF
before a TUnitSpellCA plays).  The dispel count builds and frees one TEnchantmentList per dispel
action exactly as TDispelMagicCA.Execute / Generate build theirs (references, no copies).  Nothing
else is written; no randomness is drawn; no game state changes.

STRIKE LABELS ("hits back at" for a free swing / Round Attack) -- NOT FIXED, cannot be told apart.
    The replay verb reads TStrikeCA +0x0C bit 0, set by TSingleTargetCA.SetDefensive.  In manual
    combat the failed-touch counter-strike (0x0040ABBE), the free swing at a unit moving away
    (0x004089F1) and Round Attack (0x0040A540) all call AoWE.CreateStrikeCA(attacker, target, cl=1),
    one function with identical arguments; every serialised field (+0x0C..+0x13 via
    TDamageCA.ReadWrite, +0x18 via TStrikeCA.ReadWrite) is filled by the same code from the same
    inputs.  No replicated field distinguishes them.  Auto-resolve is not affected: its Round Attack
    passes cl=0 (0x55769501 / cave_rnd 0x55769648), it has no free swing, and its only cl=1 strikes
    are the failed-touch counter-strikes (Possess/Web/Entangle/Turn Undead/Invoke Death/Command
    fc* functions), which are real counter-blows.  So the mislabel can only appear in a replay of a
    MANUAL battle's logbook.  A fix belongs at creation (pass cl=0 at TC 0x004089EF / 0x0040A53E),
    which changes a CA flag other code may read -- out of this package.

RNG: none drawn (no pattern applies).  PIC: one call/pop/sub anchor in each of c_pre and c_post (EDI =
rebase delta; c_line and the helpers run with the caller's EDI); VMTs, literals, the table, the state,
RESBYTE and AoWHSSet are [edi + preferred VA]; the class table stores VMT - table, rebase-invariant.
The only absolute operands are AoWz.exe's (0x40003C, 0x60D000).
SLOT 0x5589E000-0x5589F7FF exclusive: 0x5589E000-0x5589E7FF (package map 2026-10-14) plus
0x5589E800-0x5589F7FF claimed by v2 (verified zero and reloc-free 2026-10-14; ~2 KB headroom).
Entry stub at 0x5589E000 (fixed: a re-tune rewrites the slot in place, the hook never moves).
Calls build_combatlog_lib.py's cl_emit_replay / cl_name (undo this before that library).

FORWARD HAZARDS
  * TUnitSpellCA outcomes need build_combatlog_actions.py's es_stub (0x5577B41F); with that script
    undone they print nothing in replays (RESBYTE stays 0xFF).  Undo order: either first.
  * Wording is shared with build_combatlog_actions.py / build_combatlog_endings.py (asserted).
  * Lifesteal reads TStrikeCA +0x16 (build_razorplate.py) and +0x18 bits 08/10
    (build_lifesteal_roundattack.py); dispel reads build_command_bond.py's sentinels.

    python build_scripts/build_combatlog_replays.py           dry run + state
    python build_scripts/build_combatlog_replays.py --apply   (also re-tunes an installed v2 in place)
    python build_scripts/build_combatlog_replays.py --undo    (hook restored, slot zeroed)
    python build_scripts/build_combatlog_replays.py --dis
"""
import os, re, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5589E000, 0x5589F800)
STATE = (0x558E9B60, 0x558E9BA0)
ENTRY = SLOT[0]                                    # fixed entry stub: jmp c_entry

HOOK, HOOK_VAN, HOOK_BACK = 0x55729672, bytes.fromhex("8bd68b08ff5154"), 0x55729679
UPDATE = (0x55729610, 0x557296CC)                  # TCombatViewer.Update

# AoWEPACK (rebases: rel32 or [edi + VA])
FINDID = 0x55728C68            # eax = TCombatData, edx = id -> eax = object / 0
IS_CLASS = 0x557010C0
GETSPELL = 0x55779AC8          # eax = TSpellControl, edx = id (>= 0) -> eax = TSpell / 0
LSTRFROMSTRING = 0x55701168    # System.@LStrFromString thunk: eax = @dest LStr, edx = @shortstring
LSTRARRCLR = 0x55701148
INTTOSTR = 0x5570158C          # eax = int, edx = @out LStr
INTLIST_GET = 0x55702E94       # TIntegerList.Get thunk (eax = list, edx = index)
TENODE_CREATE = 0x557031A4     # Engine.TENode.Create thunk (eax = class, dl = 1, ecx = 0)
LISTENCH = 0x5577F45C          # TAbstractUnit.ListEnchantments(eax = unit, edx = list)
ENCH_FINDID = 0x5577C204       # TEnchantmentList.FindID(eax = list, edx = id) -> enchantment / 0
TOBJ_FREE = 0x557010B8         # System.TObject.Free thunk
ENCHLIST_CELL = 0x5570AA30     # classref cell of TEnchantmentList
AOWHSSET = 0x558FA044          # AoWE.AoWHSSet variable; TSpellControl at +0x84
TCOMBATUNIT_VMT = 0x55715A94
TLEADER_VMT = 0x55712238
GETHP_V, HASAB_V = 0x88, 0xA8  # TCombatUnit: GetHitPoints -> AL, GetAbilityEnabled(edx = id) -> AL
CL_EMIT_REPLAY, CL_NAME = 0x5589AC08, 0x5589AC10
RESBYTE = 0x558E9A60           # build_combatlog_actions.py: ExecuteSpell's AL of the last TUnitSpellCA
SENT_FRESH, SENT_BOUND = 0x7FFFFFF0, 0x7FFFFFF1   # build_command_bond.py
AB_WEBBED, AB_ENTANGLED, AB_PANICKED = 0x61, 0x5E, 0x6C
AB_EMBRITTLED, AB_SLOWENCH, SP_EMBRITTLE, SP_TERROR = 0xB2, 0x84, 0x6D, 0x69
# AoWz.exe (fixed base)
RING, MAGIC = 0x60D000, 0x31474C43
# unit spell class VMT -> the ability its ExecuteSpell expands (build_combatlog_actions.py derives it
# from the file and asserts it; one table for live and replay)
import build_combatlog_actions as _act
UNITSPELL_AB = list(_act.UNITSPELL_AB)

K = dict(DMG=1, STRIKE=2, HEAL=3, ROUND=4, INVOKE=5, TOUCH=6, USPELL=7, PRAYER=8, STATUS=9,
         CMD=10, DISPEL=11, MIND=12, RECALL=13, ANIMATE=14, MULTI=15, FLEE=16)

# (name, VMT, kind, attacker-id offset, target-id offset, extra)
CLASSES = [
    ("TDamageCA",                   0x557162F4, "DMG",     0x0D, 0x0E, 0),
    ("TStrikeCA",                   0x5571E344, "STRIKE",  0x0D, 0x0E, 0),
    ("TRangedAttackCA",             0x5571E7EC, "DMG",     0x0D, 0x0E, 0),
    ("TTurnUndeadCA",               0x5571FD18, "DMG",     0x0D, 0x0E, 0),
    ("TSelfDestructCA",             0x55721084, "DMG",     0x0D, 0x0E, 0),
    ("TCombatSpellCA",              0x557F3CC8, "DMG",     0x0D, 0x0E, 0),
    ("TTurnUndeadSpellCA",          0x557F41D0, "DMG",     0x0D, 0x0E, 0),
    ("THealingCA",                  0x557214BC, "HEAL",    0x0D, 0x0E, 0),
    ("TNewCombatRoundCA",           0x5571667C, "ROUND",   0,    0,    0),
    ("TInvokeDeathCA",              0x5571FA98, "INVOKE",  0x0D, 0x0E, 0),
    ("TFleeCA",                     0x55716954, "FLEE",    0x0C, 0,    0),
    ("TWebCA",                      0x5571F5C4, "TOUCH",   0x0D, 0x0E, 0),
    ("TEntangleCA",                 0x5571F824, "TOUCH",   0x0D, 0x0E, 1),
    ("TPossessCA",                  0x5571F0E0, "TOUCH",   0x0D, 0x0E, 2),
    ("TCommandCA",                  0x557203A0, "CMD",     0x0D, 0x0E, 0),
    ("TDispelMagicAbilityCA",       0x55721A34, "DISPEL",  0x0D, 0x0E, 0),
    ("TDispelMagicSpellCA",         0x557E530C, "DISPEL",  0x0D, 0x0E, 1),
    ("TUnitSpellCA",                0x557234B8, "USPELL",  0x10, 0x11, 0),
    ("TTacticalCombatHighPrayerCA", 0x557F44D0, "PRAYER",  0x0C, 0x0D, 0),
    ("TMindDecayCA",                0x557F4908, "MIND",    0x0C, 0x0D, 0),
    ("TSlowCA",                     0x557F4D2C, "STATUS",  0x0C, 0x0D, 0),
    ("TEntangleSpellCA",            0x557F4F08, "STATUS",  0x0C, 0x0D, 1),
    ("TRecallSpiritCA",             0x557F662C, "RECALL",  0x0C, 0x0D, 0),
    ("TAnimateDeadCA",              0x557F6828, "ANIMATE", 0x0C, 0x0D, 0),
    ("TTacticalCombatTerrorCA",     0x557F60E0, "STATUS",  0x0C, 0x0D, 2),
    ("TFastCombatHighPrayerCA",     0x557F43DC, "MULTI",   0x0C, 0,    0),
    ("TFastCombatTerrorCA",         0x557F5FF4, "MULTI",   0x0C, 0,    0),
]

LITS = [
    ("ROUND_A", "--- Round "), ("ROUND_B", " ---"),
    ("HEALS", " heals "), ("FOR", " for "), ("DAMAGE", " damage"),
    ("DRAINS", " drains "), ("HPFROM", " HP from "), ("GAINS", " gains "),
    ("DARKGIFT", " HP from Dark Gift"),
    ("PANIC", " is panicked"), ("ENTD", " is entangled"),
    ("SLAIN", " is slain"), ("THE", "The "), ("BREACHED", " is breached"),
    ("FLEES", " flees the battle"),
    ("POSSESSED", " is possessed by "), ("WEBBED", " is webbed by "),
    ("ENTANGLEDBY", " is entangled by "), ("INVOKES", " invokes death on "),
    ("F_WEB", " fails to web "), ("F_ENT", " fails to entangle "), ("F_POSS", " fails to possess "),
    ("F_INV", " fails to invoke death on "),
    ("DOMINATED", " is dominated by "), ("SEDUCED", " is seduced by "),
    ("CHARMED", " is charmed by "), ("COMMANDED", " is commanded by "),
    ("F_DOM", " fails to dominate "), ("F_SED", " fails to seduce "), ("F_CHA", " fails to charm "),
    ("F_CMD", " fails to command "),
    ("CANNOT", " cannot command "), ("ALEADER", " (a Leader)"),
    ("DISPELS", " dispels "), ("ENCH1", " enchantment from "), ("ENCHN", " enchantments from "),
    ("DISPNONE", " dispels nothing from "), ("BREAKS", " breaks the command on "),
    ("RECEIVES", " receives "), ("UNAFFECTED", " is unaffected by "),
    ("BLESSED", " is blessed by "), ("OPENPLUS", " (+"), ("HPCLOSE", " HP)"),
    ("TAKES", " takes control of "), ("OPEN", " ("), ("CLOSE", ")"),
    ("SLOWED", " is slowed ("), ("EMBRITTLED", " is embrittled ("),
    ("ENTANGLEDP", " is entangled ("), ("TERRIFIED", " is terrified ("),
    ("RECALLS", " recalls the spirit of "), ("RAISES", " raises "), ("FROMDEAD", " from the dead"),
    ("CASTS", " casts "),
]
# the same event in build_combatlog_endings.py (P3, live): key here -> its literal key there
ENDINGS_SAME = {"SLAIN": "SLAIN", "FLEES": "FLEES"}
CMD_OK = [(0x1C, "DOMINATED"), (0x1D, "SEDUCED"), (0x94, "CHARMED")]      # else COMMANDED
CMD_FAIL = [(0x1C, "F_DOM"), (0x1D, "F_SED"), (0x94, "F_CHA")]           # else F_CMD

ANCH_IMM = 0x0BADC0DE           # placeholder of every anchor's `sub edi, <return address>`
ANCHOR = f".byte 0xE8,0,0,0,0\npop edi\nsub edi, 0x{ANCH_IMM:X}\n"
N_ANCHORS = 2


def sstr(s):
    """Shortstring literal: length byte + chars (c_line appends it to its buffer)."""
    b = s.encode("latin1")
    assert len(b) < 256
    return bytes([len(b)]) + b


def layout():
    lit, data = {}, bytearray()
    base = ENTRY + 8
    for k, s in LITS:
        lit[k] = base + len(data)
        data += sstr(s)
    tbl_va = base + len(data)
    for _n, vmt, kind, ao, to, ex in CLASSES:
        rel = vmt - tbl_va
        assert -0x800000 <= rel < 0x800000 and rel != 0
        data += struct.pack("<i", rel)[:3] + bytes([K[kind], ao, to, ex])   # 7 B: rel24 + 4 bytes
    data += b"\0" * 4                                # terminator (rel24 == 0)
    data += b"\0" * (-len(data) % 4)
    us_va = base + len(data)                         # (VMT - entry VA, ability id) x n, then 0
    for i, (vmt, ab) in enumerate(UNITSPELL_AB):
        data += struct.pack("<iI", vmt - (us_va + 8 * i), ab)
    data += b"\0" * 8
    code_va = (base + len(data) + 0xF) & ~0xF
    return bytes(data), base, lit, tbl_va, us_va, code_va


DATA, DATA_VA, LIT, TBL, USTBL, CODE_VA = layout()
S = STATE[0]


def L(k):
    return f"[edi + 0x{LIT[k]:X}]"


def line(*items):
    """asm: push a (type, value) list on the stack (last item first), call c_line, drop it.
    items: ("lit", key) | ("A",) | ("T",) | ("reg", reg holding a literal) | ("int", operand) |
    ("spell", operand).  Operands must not be EAX (the lea of a later item uses it) or ESP-relative."""
    out = ["push 0", "push 0"]
    for it in reversed(items):
        k = it[0]
        if k == "lit":
            out += [f"lea eax, {L(it[1])}", "push eax", "push 1"]
        elif k in ("A", "T"):
            out += ["lea eax, [esi+0x%X]" % (0x10 if k == "A" else 0x14), "push eax", "push 2"]
        elif k == "reg":
            out += [f"push {it[1]}", "push 1"]
        elif k == "int":
            out += [f"push {it[1]}", "push 3"]
        elif k == "spell":
            out += [f"push {it[1]}", "push 4"]
        else:
            raise ValueError(it)
        assert "eax" not in str(it[1:]) and "esp" not in str(it[1:]), it
    out += ["mov eax, esp", "call c_line", "add esp, 0x%X" % (8 * (len(items) + 1))]
    return "\n        ".join(out) + "\n"


_lbl = [0]


def chain(reg, default, pairs):
    """reg := literal of the pair whose id equals EAX, else `default` (lea leaves the flags alone)."""
    s = f"lea  {reg}, {L(default)}\n"
    for cid, key in pairs:
        _lbl[0] += 1
        s += f"        cmp  eax, 0x{cid:X}\n        jne  ch_{_lbl[0]}\n        lea  {reg}, {L(key)}\n    ch_{_lbl[0]}:\n"
    return s


def src():
    guard = f"""
        mov  eax, [0x40003C]
        cmp  dword ptr [eax+0x400050], 0x20E000
        jb   {{0}}
        cmp  dword ptr [0x{RING:X}], 0x{MAGIC:X}
        jne  {{0}}"""
    A, T = ("A",), ("T",)
    return f"""
    c_entry:
        cmp  dword ptr [esi+0x14], 0
        jne  e_play
        call c_pre
    e_play:
        push eax
        mov  edx, esi
        mov  ecx, [eax]
        call dword ptr [ecx+0x54]
        pop  ecx
        test al, al
        jne  e_back
        call c_post
    e_back:
        jmp  0x{HOOK_BACK:X}

    p_x:
        popad
        ret
    /* ---- c_pre: tick 0, before Play.  EAX = CA, ESI = viewer.  Preserves everything. ---- */
    c_pre:
        pushad
        mov  ebp, esi
        mov  ebx, eax
        {ANCHOR}
        {guard.format("p_x")}
        lea  esi, [edi + 0x{S:X}]
        xor  eax, eax
        mov  [esi], eax
        test ebx, ebx
        jz   p_x
        mov  eax, [ebp+8]
        test eax, eax
        jz   p_x
        mov  eax, [eax+0x0C]
        test eax, eax
        jz   p_x
        mov  [esi+8], eax
        mov  ecx, [ebx]
        lea  ebp, [edi + 0x{TBL:X}]
        mov  edx, ebp
    p_lp:                       /* 7-byte entries: rel24 (VMT - table), kind, aoff, toff, extra */
        mov  eax, [edx]
        shl  eax, 8
        sar  eax, 8
        jz   p_x
        add  eax, ebp
        cmp  eax, ecx
        je   p_hit
        add  edx, 7
        jmp  p_lp
    p_hit:
        mov  eax, [edx+3]
        mov  [esi+4], eax
        mov  byte ptr [esi+0x0E], 0
        xor  ecx, ecx
    p_sn:                       /* i = 0 attacker, 1 target */
        movzx eax, byte ptr [esi+ecx+5]
        test eax, eax
        jz   p_sx
        push ecx
        movzx edx, byte ptr [ebx+eax]
        mov  [esi+ecx+0x0C], dl
        mov  eax, [esi+8]
        call 0x{FINDID:X}
        mov  ebp, eax
        mov  ecx, [esp]
        lea  edx, [esi+ecx*4+0x10]
        call 0x{CL_NAME:X}
        mov  eax, ebp
        call c_obj
        mov  edx, ecx
        pop  ecx
        mov  [esi+ecx*4+0x18], edx
        and  al, 1
        or   al, 4
        shl  al, cl
        or   [esi+0x0E], al
    p_sx:
        inc  ecx
        cmp  ecx, 2
        jb   p_sn
        /* dispatch: EAX = kind, ECX = extra, EBX = CA, ESI = state, EDI = delta */
        movzx eax, byte ptr [esi+4]
        movzx ecx, byte ptr [esi+7]
        cmp  eax, {K['ROUND']}
        jbe  p_pend
        cmp  eax, {K['INVOKE']}
        je   p_invoke
        cmp  eax, {K['TOUCH']}
        je   p_touch
        cmp  eax, {K['USPELL']}
        je   p_uspell
        cmp  eax, {K['PRAYER']}
        je   p_prayer
        cmp  eax, {K['STATUS']}
        je   p_pend
        cmp  eax, {K['CMD']}
        je   p_cmd
        cmp  eax, {K['DISPEL']}
        je   p_dispel
        cmp  eax, {K['MIND']}
        je   p_mind
        cmp  eax, {K['RECALL']}
        je   p_recall
        cmp  eax, {K['ANIMATE']}
        je   p_animate
        cmp  eax, {K['MULTI']}
        je   p_multi
        cmp  eax, {K['FLEE']}
        jne  p_x
        {line(A, ("lit", "FLEES"))}
        jmp  p_x
    p_pend:
        mov  [esi], ebx
        jmp  p_x

    p_invoke:
        mov  [esi], ebx
        cmp  byte ptr [ebx+0x10], 0
        je   p_inv_f
        {line(A, ("lit", "INVOKES"), T, ("lit", "FOR"), ("int", "dword ptr [esi+0x1C]"), ("lit", "DAMAGE"))}
        jmp  p_x
    p_inv_f:
        {line(A, ("lit", "F_INV"), T)}
        jmp  p_x

    p_touch:
        cmp  byte ptr [ebx+0x10], 0
        je   p_t_f
        cmp  ecx, 2
        jne  p_pend
        {line(T, ("lit", "POSSESSED"), A)}
        jmp  p_x
    p_t_f:
        lea  ebp, {L('F_WEB')}
        cmp  ecx, 1
        jne  p_t_f1
        lea  ebp, {L('F_ENT')}
    p_t_f1:
        cmp  ecx, 2
        jne  p_t_f2
        lea  ebp, {L('F_POSS')}
    p_t_f2:
        {line(A, ("reg", "ebp"), T)}
        jmp  p_x

    p_uspell:
        mov  byte ptr [edi + 0x{RESBYTE:X}], 0xFF
        jmp  p_pend

    p_prayer:
        cmp  byte ptr [ebx+0x14], 0
        jne  p_pend
        jmp  p_x

    p_cmd:
        mov  eax, [ebx+0x10]
        cmp  byte ptr [ebx+0x14], 0
        je   p_cmd_f
        {chain("ebp", "COMMANDED", CMD_OK)}
        {line(T, ("reg", "ebp"), A)}
        jmp  p_x
    p_cmd_f:
        push eax
        call c_tleader
        test al, al
        pop  eax
        jz   p_cmd_f2
        {line(A, ("lit", "CANNOT"), T, ("lit", "ALEADER"))}
        jmp  p_x
    p_cmd_f2:
        {chain("ebp", "F_CMD", CMD_FAIL)}
        {line(A, ("reg", "ebp"), T)}
        jmp  p_x

    p_dispel:
        push ecx
        call c_dcount
        pop  ecx
        test ebp, ebp
        jnz  p_d_some
        cmp  byte ptr [esi+0x20], 0
        jne  p_d_bond
        test ecx, ecx
        jz   p_x
        {line(A, ("lit", "DISPNONE"), T)}
        jmp  p_x
    p_d_some:
        lea  edx, {L('ENCHN')}
        cmp  ebp, 1
        jne  p_d_pl
        lea  edx, {L('ENCH1')}
    p_d_pl:
        {line(A, ("lit", "DISPELS"), ("int", "ebp"), ("reg", "edx"), T)}
        cmp  byte ptr [esi+0x20], 0
        je   p_x
    p_d_bond:
        {line(A, ("lit", "BREAKS"), T)}
        jmp  p_x

    p_mind:
        cmp  byte ptr [ebx+0x14], 0
        je   p_mind_f
        {line(A, ("lit", "TAKES"), T, ("lit", "OPEN"), ("spell", "dword ptr [ebx+0x18]"), ("lit", "CLOSE"))}
        jmp  p_x
    p_mind_f:
        {line(T, ("lit", "UNAFFECTED"), ("spell", "dword ptr [ebx+0x18]"))}
        jmp  p_x

    p_recall:
        cmp  byte ptr [ebx+0x14], 0
        je   p_x
        {line(A, ("lit", "RECALLS"), T)}
        jmp  p_x

    p_animate:
        cmp  byte ptr [ebx+0x14], 0
        je   p_x
        {line(A, ("lit", "RAISES"), T, ("lit", "FROMDEAD"))}
        jmp  p_x

    p_multi:
        {line(A, ("lit", "CASTS"), ("spell", "dword ptr [ebx+0x1C]"))}
        jmp  p_x

    /* ---- c_post: Play returned 0.  ECX = the CA that just finished.  Preserves everything. ---- */
    c_post:
        pushad
        mov  ebx, ecx
        {ANCHOR}
        lea  esi, [edi + 0x{S:X}]
        test ebx, ebx
        jz   q_out
        cmp  ebx, [esi]
        jne  q_out
        xor  eax, eax
        mov  [esi], eax
        movzx eax, byte ptr [esi+4]
        movzx ecx, byte ptr [esi+7]
        cmp  eax, {K['ROUND']}
        je   q_round
        cmp  eax, {K['HEAL']}
        je   q_heal
        cmp  eax, {K['STRIKE']}
        je   q_strike
        cmp  eax, {K['TOUCH']}
        je   q_touch
        cmp  eax, {K['USPELL']}
        je   q_uspell
        cmp  eax, {K['PRAYER']}
        je   q_prayer
        cmp  eax, {K['STATUS']}
        je   q_status
        jmp  q_death

    q_round:
        mov  eax, [esi+8]
        mov  ebp, [eax+0x44]
        {line(("lit", "ROUND_A"), ("int", "ebp"), ("lit", "ROUND_B"))}
        jmp  q_out

    q_heal:
        test byte ptr [esi+0x0E], 8
        jz   q_death
        call c_tnow
        sub  ecx, [esi+0x1C]
        mov  ebp, ecx
        test ebp, ebp
        jle  q_h0
        {line(A, ("lit", "HEALS"), T, ("lit", "FOR"), ("int", "ebp"))}
        jmp  q_death
    q_h0:
        {line(A, ("lit", "HEALS"), T)}
        jmp  q_death

    q_strike:
        test byte ptr [esi+0x0E], 2
        jz   q_ls
        call c_tnow
        cmp  al, 3
        jne  q_ls
        test byte ptr [ebx+0x18], 1
        jz   q_f4
        {line(T, ("lit", "PANIC"))}
    q_f4:
        test byte ptr [ebx+0x18], 4
        jz   q_ls
        {line(T, ("lit", "ENTD"))}
    q_ls:
        movzx edx, byte ptr [ebx+0x18]
        and  edx, 0x18
        jz   q_death
        test byte ptr [esi+0x0E], 4
        jz   q_death
        push edx
        call c_anow
        pop  edx
        sub  ecx, [esi+0x18]
        movzx eax, byte ptr [ebx+0x16]
        add  ecx, eax
        jle  q_death
        test dl, 8
        jz   q_dg
        mov  ebp, ecx
        cmp  ebp, 4
        jle  q_l1
        mov  ebp, 4
    q_l1:
        sub  ecx, ebp
        push ecx
        push edx
        {line(A, ("lit", "DRAINS"), ("int", "ebp"), ("lit", "HPFROM"), T)}
        pop  edx
        pop  ecx
    q_dg:
        test dl, 0x10
        jz   q_death
        mov  ebp, ecx
        cmp  ebp, 3
        jle  q_d1
        mov  ebp, 3
    q_d1:
        test ebp, ebp
        jle  q_death
        {line(A, ("lit", "GAINS"), ("int", "ebp"), ("lit", "DARKGIFT"))}
        jmp  q_death

    q_touch:                    /* web (extra 0) / entangle (1) landed: only if the status is on */
        mov  edx, 0x{AB_WEBBED:X}
        test ecx, ecx
        jz   q_t1
        mov  edx, 0x{AB_ENTANGLED:X}
    q_t1:
        call c_has
        test al, al
        jz   q_death
        movzx ecx, byte ptr [esi+7]
        lea  ebp, {L('WEBBED')}
        test ecx, ecx
        jz   q_t2
        lea  ebp, {L('ENTANGLEDBY')}
    q_t2:
        {line(T, ("reg", "ebp"), A)}
        jmp  q_death

    q_uspell:                   /* RESBYTE 1: took effect (USTBL spells: only if the ability is on);
                                   0: not; 0xFF: unknown -> nothing */
        movzx eax, byte ptr [edi + 0x{RESBYTE:X}]
        test eax, eax
        jz   q_u_un
        cmp  eax, 1
        jne  q_death
        mov  edx, [ebx+0x0C]
        test edx, edx
        js   q_u_ok
        mov  eax, [edi + 0x{AOWHSSET:X}]
        test eax, eax
        jz   q_u_ok
        mov  eax, [eax+0x84]
        test eax, eax
        jz   q_u_ok
        call 0x{GETSPELL:X}
        test eax, eax
        jz   q_u_ok
        mov  eax, [eax]
        lea  edx, [edi + 0x{USTBL:X}]
    q_u_lp:
        mov  ecx, [edx]
        test ecx, ecx
        jz   q_u_ok
        add  ecx, edx
        cmp  ecx, eax
        je   q_u_hit
        add  edx, 8
        jmp  q_u_lp
    q_u_hit:
        mov  edx, [edx+4]
        call c_has
        test al, al
        jz   q_u_un
    q_u_ok:
        lea  ebp, {L('RECEIVES')}
        jmp  q_u_say
    q_u_un:
        lea  ebp, {L('UNAFFECTED')}
    q_u_say:
        {line(T, ("reg", "ebp"), ("spell", "dword ptr [ebx+0x0C]"))}
        jmp  q_death

    q_prayer:
        call c_tnow
        sub  ecx, [esi+0x1C]
        mov  ebp, ecx
        test ebp, ebp
        jle  q_p0
        {line(T, ("lit", "BLESSED"), ("spell", "dword ptr [ebx+0x18]"), ("lit", "OPENPLUS"), ("int", "ebp"), ("lit", "HPCLOSE"))}
        jmp  q_death
    q_p0:
        {line(T, ("lit", "BLESSED"), ("spell", "dword ptr [ebx+0x18]"))}
        jmp  q_death

    q_status:                   /* extra 0 Slow/Embrittle, 1 Entangle spell, 2 Terror */
        cmp  ecx, 2
        jne  q_s1
        mov  ebp, 0x{SP_TERROR:X}
        mov  edx, 0x{AB_PANICKED:X}
        lea  eax, {L('TERRIFIED')}
        jmp  q_s3
    q_s1:
        mov  ebp, [ebx+0x18]
        mov  edx, 0x{AB_ENTANGLED:X}
        lea  eax, {L('ENTANGLEDP')}
        cmp  ecx, 1
        je   q_s3
        mov  edx, 0x{AB_SLOWENCH:X}
        lea  eax, {L('SLOWED')}
        cmp  ebp, 0x{SP_EMBRITTLE:X}
        jne  q_s3
        mov  edx, 0x{AB_EMBRITTLED:X}
        lea  eax, {L('EMBRITTLED')}
    q_s3:
        cmp  byte ptr [ebx+0x14], 0
        je   q_s_un
        push eax
        call c_has
        test al, al
        pop  edx
        jz   q_s_un
        {line(T, ("reg", "edx"), ("spell", "ebp"), ("lit", "CLOSE"))}
        jmp  q_death
    q_s_un:
        {line(T, ("lit", "UNAFFECTED"), ("spell", "ebp"))}

    q_death:
        test byte ptr [esi+0x0E], 2
        jz   q_da
        call c_tnow
        test al, 1
        jnz  q_da
        test al, 2
        jz   q_tw
        {line(T, ("lit", "SLAIN"))}
        jmp  q_da
    q_tw:
        {line(("lit", "THE"), T, ("lit", "BREACHED"))}
    q_da:
        test byte ptr [esi+0x0E], 1
        jz   q_out
        call c_anow
        test al, 1
        jnz  q_out
        test al, 2
        jz   q_aw
        {line(A, ("lit", "SLAIN"))}
        jmp  q_out
    q_aw:
        {line(("lit", "THE"), A, ("lit", "BREACHED"))}
    q_out:
        popad
        ret

    /* ---- helpers (ESI = state, EBX = CA, EDI = delta; preserve EBX/ESI/EDI/EBP unless stated) ---- */
    c_tnow:                     /* target now -> AL = alive|unit<<1, ECX = HP */
        movzx edx, byte ptr [esi+0x0D]
        jmp  c_fnd
    c_anow:
        movzx edx, byte ptr [esi+0x0C]
    c_fnd:
        mov  eax, [esi+8]
        call 0x{FINDID:X}
    c_obj:                      /* EAX = object / 0 -> AL = alive|unit<<1, ECX = HP (0 if no unit) */
        push ebx
        push 0
        push 0
        mov  ebx, eax
        test ebx, ebx
        jz   o_done
        test byte ptr [ebx+0x47], 1
        jnz  o_dead
        mov  byte ptr [esp], 1
    o_dead:
        mov  eax, ebx
        lea  edx, [edi + 0x{TCOMBATUNIT_VMT:X}]
        call 0x{IS_CLASS:X}
        test al, al
        jz   o_done
        or   byte ptr [esp], 2
        mov  eax, ebx
        mov  edx, [eax]
        call dword ptr [edx+0x{GETHP_V:X}]
        movsx eax, al
        mov  [esp+4], eax
    o_done:
        pop  eax
        pop  ecx
        pop  ebx
        ret

    c_has:                      /* EDX = ability id -> AL = the target's GetAbilityEnabled (0 if no TCombatUnit) */
        push edx
        movzx edx, byte ptr [esi+0x0D]
        mov  eax, [esi+8]
        call 0x{FINDID:X}
        push eax
        lea  edx, [edi + 0x{TCOMBATUNIT_VMT:X}]
        call 0x{IS_CLASS:X}
        pop  ecx
        pop  edx
        test al, al
        jz   h_z
        mov  eax, ecx
        mov  ecx, [eax]
        jmp  dword ptr [ecx+0x{HASAB_V:X}]
    h_z:
        xor  eax, eax
        ret

    c_tleader:                  /* AL = 1 iff the target is a TCombatUnit whose unit IsClass TLeader */
        movzx edx, byte ptr [esi+0x0D]
        mov  eax, [esi+8]
        call 0x{FINDID:X}
        push eax
        lea  edx, [edi + 0x{TCOMBATUNIT_VMT:X}]
        call 0x{IS_CLASS:X}
        pop  edx
        test al, al
        jz   h_z
        mov  eax, [edx+0x4C]
        test eax, eax
        jz   h_z
        lea  edx, [edi + 0x{TLEADER_VMT:X}]
        jmp  0x{IS_CLASS:X}

    /* c_dcount -> EBP = success-list ids TEnchantmentList.FindID finds on the target now (what
       TDispelMagicCA.Execute will dispel, behind its guards), [esi+0x20] = 1 if a bond sentinel is
       listed.  Clobbers EAX/ECX/EDX. */
    c_dcount:
        xor  ebp, ebp
        mov  byte ptr [esi+0x20], 0
        movzx edx, byte ptr [esi+0x0C]
        mov  eax, [esi+8]
        call 0x{FINDID:X}
        lea  edx, [edi + 0x{TCOMBATUNIT_VMT:X}]
        call 0x{IS_CLASS:X}
        test al, al
        jz   dc_r
        movzx edx, byte ptr [esi+0x0D]
        mov  eax, [esi+8]
        call 0x{FINDID:X}
        push eax
        lea  edx, [edi + 0x{TCOMBATUNIT_VMT:X}]
        call 0x{IS_CLASS:X}
        pop  edx
        test al, al
        jz   dc_r
        mov  eax, [edx+0x4C]
        test eax, eax
        jz   dc_r
        mov  ecx, [ebx+0x10]
        test ecx, ecx
        jz   dc_r
        push eax
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, [edi + 0x{ENCHLIST_CELL:X}]
        call 0x{TENODE_CREATE:X}
        pop  edx
        push eax
        xchg eax, edx
        call 0x{LISTENCH:X}
        mov  eax, [ebx+0x10]
        mov  ecx, [eax+0x08]
    dc_lp:
        dec  ecx
        js   dc_done
        push ecx
        mov  edx, ecx
        mov  eax, [ebx+0x10]
        call 0x{INTLIST_GET:X}
        cmp  eax, 0x{SENT_FRESH:X}
        je   dc_s
        cmp  eax, 0x{SENT_BOUND:X}
        je   dc_s
        mov  edx, eax
        mov  eax, [esp+4]
        call 0x{ENCH_FINDID:X}
        test eax, eax
        jz   dc_n
        inc  ebp
        jmp  dc_n
    dc_s:
        mov  byte ptr [esi+0x20], 1
    dc_n:
        pop  ecx
        jmp  dc_lp
    dc_done:
        pop  eax
        call 0x{TOBJ_FREE:X}
    dc_r:
        ret

    /* ---- c_line: EAX = [type, value] pairs, type 0 ends (1 shortstring literal, 2 @LStr var,
       3 int, 4 spell id).  Runs with the caller's EDI (delta).  The line is built as a shortstring
       in the frame (cut at 255), turned into an LStr by @LStrFromString, emitted. ---- */
    c_line:
        push ebp
        mov  ebp, esp
        sub  esp, 0x108
        push ebx
        push esi
        push edi
        mov  ebx, eax
        xor  eax, eax
        mov  [ebp-0x104], eax
        mov  [ebp-0x108], eax
        mov  byte ptr [ebp-0x100], al
    cl_lp:
        mov  eax, [ebx]
        mov  edx, [ebx+4]
        add  ebx, 8
        dec  eax
        jz   t_lit
        dec  eax
        jz   t_var
        dec  eax
        jz   t_int
        dec  eax
        jnz  cl_end
        test edx, edx
        js   cl_lp
        mov  eax, [edi + 0x{AOWHSSET:X}]
        test eax, eax
        jz   cl_lp
        mov  eax, [eax+0x84]
        test eax, eax
        jz   cl_lp
        call 0x{GETSPELL:X}
        test eax, eax
        jz   cl_lp
        mov  eax, [eax+8]
        call l_lstr
        jmp  cl_lp
    t_lit:
        mov  eax, edx
        call l_short
        jmp  cl_lp
    t_var:
        mov  eax, [edx]
        call l_lstr
        jmp  cl_lp
    t_int:
        mov  eax, edx
        lea  edx, [ebp-0x104]
        call 0x{INTTOSTR:X}
        mov  eax, [ebp-0x104]
        call l_lstr
        jmp  cl_lp
    cl_end:
        lea  eax, [ebp-0x108]
        lea  edx, [ebp-0x100]
        call 0x{LSTRFROMSTRING:X}
        mov  eax, [ebp-0x108]
        call 0x{CL_EMIT_REPLAY:X}
        lea  eax, [ebp-0x108]
        mov  edx, 2
        call 0x{LSTRARRCLR:X}
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    l_short:                    /* EAX = shortstring literal / 0 (runs in c_line's frame) */
        test eax, eax
        jz   l_ret
        movzx ecx, byte ptr [eax]
        inc  eax
        jmp  l_app
    l_lstr:                     /* EAX = LStr value / nil */
        test eax, eax
        jz   l_ret
        mov  ecx, [eax-4]
    l_app:                      /* EAX = chars, ECX = count -> appended to [ebp-0x100], cut at 255 */
        push esi
        push edi
        mov  esi, eax
        movzx edx, byte ptr [ebp-0x100]
        lea  edi, [ebp+edx-0xFF]
        mov  eax, 0xFF
        sub  eax, edx
        cmp  ecx, eax
        jbe  l_fit
        mov  ecx, eax
    l_fit:
        add  byte ptr [ebp-0x100], cl
        cld
        rep  movsb
        pop  edi
        pop  esi
    l_ret:
        ret
    """


def build_code():
    blob = bytearray(asm(src(), CODE_VA))
    pat = b"\xE8\x00\x00\x00\x00\x5F\x81\xEF" + struct.pack("<I", ANCH_IMM)
    n, i = 0, blob.find(pat)
    while i >= 0:
        struct.pack_into("<I", blob, i + 8, CODE_VA + i + 5)    # the `pop edi` = the return address
        n += 1
        i = blob.find(pat, i + 1)
    assert n == N_ANCHORS, "expected %d anchors, found %d" % (N_ANCHORS, n)
    assert struct.pack("<I", ANCH_IMM) not in blob, "an anchor placeholder survived"
    assert blob[:4] == bytes.fromhex("837e1400"), "c_entry is not at the start of the code"
    return bytes(blob)


CODE = build_code()
CAVES = [("entry stub", ENTRY, jmp_to(ENTRY, CODE_VA, 8)),
         ("cave_data (literals, class table)", DATA_VA, DATA), ("cave_code", CODE_VA, CODE)]
assert CODE_VA + len(CODE) <= SLOT[1], "cave overflows the slot (%d B)" % (CODE_VA + len(CODE) - SLOT[0])


def check_pic():
    """Every anchor's sub constant is its return address; no absolute DLL operand; every DLL
    operand goes through EDI (the delta); every rel32 call lands on a known routine or helper."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    ins = list(md.disasm(CODE, CODE_VA))
    assert sum(len(x.bytes) for x in ins) == len(CODE), "cave_code does not disassemble cleanly"
    ok_calls = {FINDID, IS_CLASS, GETSPELL, LSTRFROMSTRING, LSTRARRCLR, INTTOSTR, CL_EMIT_REPLAY, CL_NAME,
                INTLIST_GET, TENODE_CREATE, LISTENCH, ENCH_FINDID, TOBJ_FREE}
    for i, x in enumerate(ins):
        if x.mnemonic == "call" and x.op_str == hex(x.address + 5):
            s = ins[i + 2]
            assert ins[i + 1].mnemonic == "pop" and s.mnemonic == "sub" and \
                int(s.op_str.split(",")[1], 16) == x.address + 5, "bad anchor at %08X" % x.address
            continue
        if x.mnemonic in ("call", "jmp") and not x.op_str.startswith("dword"):
            t = int(x.op_str, 16)
            assert t in ok_calls or t == HOOK_BACK or CODE_VA <= t < CODE_VA + len(CODE), \
                "%s to %08X" % (x.mnemonic, t)
        for m in re.finditer(r"\[(0x[0-9a-f]+)\]", x.op_str):
            if int(m.group(1), 16) not in (0x40003C, RING):
                sys.exit("ABORT: absolute operand at %08X: %s" % (x.address, x.op_str))
        for m in re.finditer(r"\[(\w+) \+ (0x55[0-9a-f]{6})\]", x.op_str):
            if m.group(1) != "edi":
                sys.exit("ABORT: DLL address off a register other than the delta at %08X" % x.address)
        if x.mnemonic in ("push", "mov") and re.search(r"(^|, )0x55[0-9a-f]{6}$", x.op_str):
            sys.exit("ABORT: immediate DLL address at %08X: %s" % (x.address, x.op_str))
        if x.mnemonic == "push" and x.op_str.startswith("0x") and int(x.op_str, 16) > 4:
            sys.exit("ABORT: push imm at %08X (keystone imm8 trap)" % x.address)
    jt = [x for x in ins if x.mnemonic == "jmp" and x.op_str == hex(HOOK_BACK)]
    assert len(jt) == 1, "the return jump to %08X is missing" % HOOK_BACK


check_pic()


def check_targets():
    """The class table names the right VMTs (Delphi 3 vmtClassName at VMT-0x20 reads back the
    class name); the classes and slots the cave calls are where it expects; the writable state is
    zero in the file and reloc-free; the wording matches the live scripts."""
    d = open(P.TARGET, "rb").read()
    u32 = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]

    def cname(vmt):
        o = P.va2off(d, u32(vmt - 0x20))
        return d[o + 1:o + 1 + d[o]].decode("latin1")
    for name, vmt, *_ in CLASSES:
        assert cname(vmt) == name, "VMT %08X is %s, not %s" % (vmt, cname(vmt), name)
    assert cname(TCOMBATUNIT_VMT) == "TCombatUnit" and cname(TLEADER_VMT) == "TLeader"
    assert cname(u32(ENCHLIST_CELL)) == "TEnchantmentList", "ENCHLIST_CELL moved"
    assert u32(TCOMBATUNIT_VMT + GETHP_V) == 0x55725064, "TCombatUnit.GetHitPoints slot moved"
    assert u32(TCOMBATUNIT_VMT + HASAB_V) == 0x55725004, "TCombatUnit.GetAbilityEnabled slot moved"
    o = P.va2off(d, STATE[0])
    zone = d[o:o + STATE[1] - STATE[0]]
    assert not any(zone), "writable state %08X-%08X is not zero in the file" % STATE
    assert not P.relocs_in(d, *STATE), ".reloc entry inside the state block"
    o = P.va2off(d, RESBYTE)
    assert d[o] == 0 and not P.relocs_in(d, RESBYTE, RESBYTE + 1), "RESBYTE is not free DATA slack"
    # one wording for one event: literals shared with the live scripts must be identical
    import importlib
    act = importlib.import_module("build_combatlog_actions")
    assert act.RESBYTE == RESBYTE, "RESBYTE differs from build_combatlog_actions.py's"
    mine, live = dict(LITS), dict(act.LITS)
    for k in set(mine) & set(live):
        assert mine[k] == live[k], "wording differs from build_combatlog_actions.py: %s %r vs %r" \
            % (k, mine[k], live[k])
    here = os.path.dirname(os.path.abspath(__file__))
    t = open(os.path.join(here, "build_combatlog_endings.py")).read()
    for k, kk in ENDINGS_SAME.items():
        assert re.search(r'\("%s", "%s"\)' % (kk, re.escape(mine[k])), t), \
            "wording differs from build_combatlog_endings.py: %s" % k
    t = open(os.path.join(here, "build_command_bond.py")).read()
    assert re.search(r"SENT_FRESH, SENT_BOUND = 0x7FFFFFF0, 0x7FFFFFF1", t), "bond sentinels changed"


def main(argv):
    check_targets()
    run("build_combatlog_replays [AoWEPACK]", [(HOOK, HOOK_VAN, jmp_to(HOOK, ENTRY, len(HOOK_VAN)))],
        CAVES, SLOT, [(HOOK, HOOK + len(HOOK_VAN), UPDATE[0], UPDATE[1])], argv)
    print("  code %08X-%08X (%d B), slot used %d of %d B; state %08X-%08X"
          % (CODE_VA, CODE_VA + len(CODE), len(CODE), CODE_VA + len(CODE) - SLOT[0],
             SLOT[1] - SLOT[0], STATE[0], STATE[1]))


if __name__ == "__main__":
    main(sys.argv[1:])
