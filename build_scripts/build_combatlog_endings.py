#!/usr/bin/env python
r"""
build_combatlog_endings.py -- manual-combat log lines for how units leave the field and how the
battle ends.  AoWEPACK.dpl + AoWTCPCK.dpl.  Owner request 2026-10-14 (combat-log package P3).

    Goblin Bomber is slain                    a unit dies (any damage: strike, spell, tick, ...)
    Swordsman is lost with its transport      a passenger dies because the ship carrying it died
    Swordsman flees the battle                a unit leaves by a flee hex
    Swordsman surrenders and is lost          one line per unit when its player presses Surrender
    Battle won by the attackers               the battle is decided
    Battle won by the defenders
    Battle drawn
    Battle ends: a leader has fallen

All four are LIVE MANUAL COMBAT only: every line goes through cl_emit, which drops it unless
RING_TACTICAL == 1 (auto-resolve, replay seeks and the editor print nothing).

G1 DEATHS -- AoWEPACK TCombatUnit.DestroyObject @0x557256F0 (6 B entry `53 56 8B D8 8B C3`,
    no .reloc, no jump into 0x557256F1..F5).  EAX = the combat object.  Every unit death funnels
    here: the vmt+0x120 callers that pass a combat unit are
        TCombatObject.ExecuteDamage  call @0x55726CC9, ret 0x55726CCF  HP reached 0  -> "is slain"
        TCombatUnit.ObjectDestroyed  call @0x557252DB, ret 0x557252E1                -> "is lost with
            its transport": self has [+0x54] != 0 (TCombat.AddArmy @0x5572792C sets it for a unit
            that cannot stand on the battle terrain and rides a transporter), the destroyed object's
            strategic unit answers GetTransporter (TAbstractUnit vmt+0x108 @0x5577FD40) and both
            are on the same side ([+0x46] >> 4).  Verified 2026-10-14; it is NOT summoned dependants.
        TPossessCA.Execute           call @0x55769783, ret 0x55769789  -> NO LINE.  The object
            destroyed is the possessor's old body, already unlinked (SetUnit(nil) @0x55769779, so
            [+0x4C] is nil); the possessor itself lives on in the victim's body.  Possession is
            P2's outcome line (ExecuteCombatAction); a death line here would be false.
        TFastCombatUnit.DestroyObject (direct call @0x557441B9) -- auto-resolve only, gated off.
        Any other return address -> "is destroyed" (none known in live combat).
    The vmt+0x120 calls in UpdateWallCombatFeatures / the predictor / TDecayAbility.CombatDone are on
    strategic units or predictor objects (different classes), not here.
    Skip guard: [obj+0x47] & 9 (already dead or fled) -- a passenger that died earlier is
    re-destroyed when its ship dies; it must not die twice in the log.
    Surrender does NOT come here (TCombatUnit.Surrender @0x557257B8 sets the bit itself), nor does
    flee (SetStatus 8), so G1/G9/G13 never print twice for one unit.

G9 FLEE -- AoWTCPCK TCombatMoveTE.ExecuteDefaultMove: `call 0x4024AC` (SetStatus thunk) @0x4083B8,
    DL = [0x4085EC] = 8, EAX = [TE+0x1C] the moving unit.  Call-retarget (4-byte rel32, nothing
    displaced, no .reloc): cave_fl logs, then tail-jumps to the thunk.  The line is emitted BEFORE
    SetStatus, whose CheckTerminate can end the battle -- so it lands before the result line.

G13 SURRENDER -- AoWTCPCK TCEndCombatTE.Execute: `call [edx+0x11C]` (Surrender) @0x407E06, once per
    enabled TCombatUnit of the current player.  6 B FF 92 1C 01 00 00 -> `call cave_su ; nop`
    (no .reloc; the loop's jumps land on 0x407D59 / 0x407E0C, never inside).  cave_su logs, then
    tail-jumps through the same vmt slot; the return lands on the nop.  Surrender sets HP 0, the
    dead bit and calls KillUnit (vmt+0x138), so the unit is lost, not retreated -- hence the
    wording.  One line PER UNIT, not one per player: this is the only point that names who is lost,
    and the TE has no cheap player name.  Passengers of a surrendering ship get G1's transport line.

G10 BATTLE RESULT -- AoWEPACK TCombat.CheckTerminate: `call TCombat.Terminate` @0x55727507
    (call-retarget, no .reloc).  Terminate runs once ([combat+0x34] guard); cave_bt logs only when
    [combat+0x34] == 0, then tail-jumps to Terminate.
    WHY HERE AND NOT AT THE END.  The vanilla result is computed late: TTacticalCombat.Deactivate
    @0x429064 calls UpdateStatus (vmt+0x4C), then DestroyCombat runs TTacticalCombat.Finalize
    @0x429418, which calls TAoWHSMap.ReleaseCombatMap @0x557786DC (triggers the map's deactivate
    notify list -- RING_TACTICAL := 0 on TCMapDeActivateMap) BEFORE TCombat.Finalize reaches
    GetCombatResultText / SetFinalData.  The exe's drain clears the memo and discards unread ring
    lines on that mode change (build_combatlog_exe.py cave_drain, `_m_none`), and no frame is drawn
    between Deactivate and ReleaseCombatMap, so a line emitted at the real end is never seen.
    Terminate is the decision point: TAoWCombatMap.EndCombat @0x41C88C is its OnTerminate
    ([combat+0x38], set @0x4299A1) and only queues TTerminateCombatTE.
    THE OUTCOME mirrors TCombat.UpdateStatus @0x557282E4 read-only: n0/n1 =
    TCombatSide.GetUndestroyedConquerObjects of [combat+0x1C] (side 0) / [combat+0x20] (side 1);
        n0 > 0, n1 = 0 -> 3 "Battle Won"   n0 = 0, n1 > 0 -> 4 "Battle Lost"
        both 0         -> 5 (drawn)        both > 0       -> 2 (vanilla prints "Cannot inflict damage")
        4 or 5 and any combat object with [+0x47] & 8 (fled) -> 9 (drawn)
    Side 0 is the attacker: TCombat.InitDefaultArmies adds the moving army with CL = 0 (@0x55727C09)
    and the army found on the target field with CL = 1 (@0x55727C49); vanilla's "Battle Won"/"Battle
    Lost" (res 65370/65371) are side 0's view.  Both sides alive at Terminate happens only through
    CheckTerminate's third test: the list [[combat+0xC]+0x2C] is non-empty, which DestroyObject
    @0x55725790 and Surrender @0x55725805 fill with the player of a dying TLeader (class
    0x55712238); TCombat.Finalize later calls GameOver for each -- hence "a leader has fallen".
    (build_autocombat_roundcap.py calls that list the "flee list"; it is the fallen-leader list.)

Rolls: none drawn; no game state written (only cl_emit's ring).  Peers stay in step.
PIC: AoWEPACK caves anchor once per entry (`call $+5 / pop / sub`), everything else rel32; the
AoWTCPCK caves reach AoWEPACK by the rebase delta off IAT cell 0x46E7F4 (AoWE.ExecuteDamageRole
0x55725EAC), as build_combatlog_wallcrush.py.  No absolute DLL operand anywhere.
Caves: AoWEPACK 0x5589C800-0x5589CFFF, AoWTCPCK 0x0043B100-0x0043B1FF, exclusive.  No writable
state (the DATA slack 0x558E9AA0-0x558E9ADF assigned to this package is unused).
Needs build_combatlog_lib.py INSTALLED (cl_emit 0x5589AC00, cl_name 0x5589AC10, cl_live 0x5589AC20).

FORWARD HAZARDS
    * Undo this script before build_combatlog_lib.py (its --undo refuses while an AoWEPACK caller
      exists; the AoWTCPCK half reaches it only through this script's AoWEPACK caves).
    * Another feature hooking DestroyObject's entry, CheckTerminate's Terminate call, TC 0x4083B8 or
      TC 0x407E06 must chain through these caves (they replay/tail-jump to the vanilla targets).
    * The return addresses 0x55726CCF / 0x557252E1 / 0x55769789 are the wording switch: a feature
      that moves one of those vmt+0x120 calls into a cave changes the wording to "is destroyed".

UNPROVEN RISK
    * The result line is predicted at Terminate; deaths later in the same turn event (the rest of a
      self-destruct blast, the rest of a surrender loop after a Leader) can change the final result
      vanilla records.  The line is visible only for the frames between Terminate and the queued
      TTerminateCombatTE; on a fast machine that may be very short.

    python build_scripts/build_combatlog_endings.py            dry run + state, both modules
    python build_scripts/build_combatlog_endings.py --apply
    python build_scripts/build_combatlog_endings.py --undo
    python build_scripts/build_combatlog_endings.py --dis
"""
import os, re, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

EPACK = os.path.join(P.GAME, "AoWEPACK.dpl")
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")

E_SLOT = (0x5589C800, 0x5589D000)
T_SLOT = (0x0043B100, 0x0043B200)

# ---- AoWEPACK ------------------------------------------------------------------------------
CL_EMIT, CL_NAME, CL_LIVE = 0x5589AC00, 0x5589AC10, 0x5589AC20     # build_combatlog_lib.py
EDR = 0x55725EAC              # AoWE.ExecuteDamageRole (export; the rebase-delta reference)
LSTRCAT = 0x55701188          # eax=@dest, edx=src value
LSTRCLR = 0x55701140          # eax=@dest

G1_HOOK = 0x557256F0          # TCombatUnit.DestroyObject entry
G1_VAN = bytes.fromhex("53568bd88bc3")     # push ebx; push esi; mov ebx,eax; mov eax,ebx
G1_RESUME = 0x557256F6
G1_FN = (0x557256F0, 0x557257B2)
RET_DAMAGE = 0x55726CCF       # TCombatObject.ExecuteDamage, after call [edx+0x120] @0x55726CC9
RET_PASSENGER = 0x557252E1    # TCombatUnit.ObjectDestroyed, after call [edx+0x120] @0x557252DB
RET_POSSESS = 0x55769789      # TPossessCA.Execute, after call [edx+0x120] @0x55769783
GONE_MASK = 9                 # [+0x47]: 1 dead/surrendered, 8 fled

G10_HOOK = 0x55727507         # TCombat.CheckTerminate: call TCombat.Terminate
TERMINATE = 0x557274B8
G10_FN = (0x557274D8, 0x5572750E)
GUCO = 0x55726E28             # TCombatSide.GetUndestroyedConquerObjects (eax=side) -> eax
DATA_COUNT = 0x55728BEC       # TCombatData.GetCount (eax=data)
DATA_OBJ = 0x55728BF8         # TCombatData.GetObjects (eax=data, edx=index)

LIT = [("SLAIN", " is slain"),
       ("LOST", " is lost with its transport"),
       ("DESTROYED", " is destroyed"),
       ("FLEES", " flees the battle"),
       ("SURR", " surrenders and is lost"),
       ("WON_A", "Battle won by the attackers"),
       ("WON_D", "Battle won by the defenders"),
       ("DRAWN", "Battle drawn"),
       ("LEADER", "Battle ends: a leader has fallen")]


def _check_wire():
    here = os.path.dirname(os.path.abspath(__file__))
    t = open(os.path.join(here, "build_combatlog_lib.py")).read()
    for n, va in (("cl_emit", CL_EMIT), ("cl_name", CL_NAME), ("cl_live", CL_LIVE)):
        assert re.search(r'"%s": 0x%X' % (n, va), t), "library entry %s moved" % n


_check_wire()


def lstr(s):
    """Delphi const AnsiString: refcount -1, length, chars, NUL, 4-aligned."""
    b = struct.pack("<iI", -1, len(s)) + s.encode("latin1") + b"\0"
    return b + b"\0" * (-len(b) % 4)


def anchor(reg, at):
    return f"call 0x{at + 5:X}\npop {reg}\nsub {reg}, 0x{at + 5:X}\n"


def align16(va):
    return (va + 0xF) & ~0xF


def e_caves():
    data, lit = bytearray(), {}
    for k, s in LIT:
        lit[k] = E_SLOT[0] + len(data) + 8                   # the chars = the LStr value
        data += lstr(s)
    caves = [("literals", E_SLOT[0], bytes(data))]
    va = align16(E_SLOT[0] + len(data))

    def L(k):
        return f"[edi + 0x{lit[k]:X}]"

    # name + suffix -> cl_emit.  In: esi = combat object, ebx = suffix LStr value.  Uses [esp].
    def line(tag):
        return f"""
        push 0
        mov  edx, esp
        mov  eax, esi
        call 0x{CL_NAME:X}
        mov  eax, esp
        mov  edx, ebx
        call 0x{LSTRCAT:X}
        mov  eax, [esp]
        call 0x{CL_EMIT:X}
        mov  eax, esp
        call 0x{LSTRCLR:X}
        pop  eax
        """

    # ---- G1: DestroyObject entry ------------------------------------------------------------
    pre = "pushad\nmov esi, eax\n"
    at = va + len(asm(pre, va))
    src = pre + anchor("edi", at) + f"""
        call 0x{CL_LIVE:X}
        test eax, eax
        jz   g1_done
        test byte ptr [esi+0x47], {GONE_MASK}
        jnz  g1_done
        mov  eax, [esp+0x20]
        sub  eax, edi
        cmp  eax, 0x{RET_POSSESS:X}
        je   g1_done
        lea  ebx, {L('SLAIN')}
        cmp  eax, 0x{RET_DAMAGE:X}
        je   g1_have
        lea  ebx, {L('LOST')}
        cmp  eax, 0x{RET_PASSENGER:X}
        je   g1_have
        lea  ebx, {L('DESTROYED')}
    g1_have:
        {line('g1')}
    g1_done:
        popad
        push ebx
        push esi
        mov  ebx, eax
        mov  eax, ebx
        jmp  0x{G1_RESUME:X}
    """
    g1 = asm(src, va)
    caves.append(("g1_death", va, g1))
    va = align16(va + len(g1))

    # ---- G10: CheckTerminate -> Terminate ---------------------------------------------------
    pre = "pushad\nmov ebx, eax\n"
    at = va + len(asm(pre, va))
    src = pre + anchor("edi", at) + f"""
        cmp  byte ptr [ebx+0x34], 0
        jne  bt_done
        call 0x{CL_LIVE:X}
        test eax, eax
        jz   bt_done
        mov  eax, [ebx+0x1C]
        call 0x{GUCO:X}
        mov  esi, eax
        mov  eax, [ebx+0x20]
        call 0x{GUCO:X}
        mov  ebp, eax
        lea  edx, {L('LEADER')}
        test esi, esi
        jz   bt_a0
        test ebp, ebp
        jnz  bt_emit
        lea  edx, {L('WON_A')}
        jmp  bt_emit
    bt_a0:
        lea  edx, {L('WON_D')}
        test ebp, ebp
        jnz  bt_fled
        lea  edx, {L('DRAWN')}
    bt_fled:
        push edx
        mov  eax, [ebx+0x0C]
        call 0x{DATA_COUNT:X}
        mov  esi, eax
    bt_loop:
        dec  esi
        js   bt_nofled
        mov  eax, [ebx+0x0C]
        mov  edx, esi
        call 0x{DATA_OBJ:X}
        test eax, eax
        jz   bt_loop
        test byte ptr [eax+0x47], 8
        jz   bt_loop
        pop  edx
        lea  edx, {L('DRAWN')}
        jmp  bt_emit
    bt_nofled:
        pop  edx
    bt_emit:
        mov  eax, edx
        call 0x{CL_EMIT:X}
    bt_done:
        popad
        jmp  0x{TERMINATE:X}
    """
    bt = asm(src, va)
    caves.append(("g10_result", va, bt))
    va = align16(va + len(bt))

    # ---- G9 / G13 formatters, reached from AoWTCPCK: eax = combat unit; Delphi register ABI --
    out = {}
    for name, key in (("fl_log", "FLEES"), ("su_log", "SURR")):
        pre = "push ebx\npush esi\npush edi\nmov esi, eax\n"
        at = va + len(asm(pre, va))
        src = pre + anchor("edi", at) + f"""
        call 0x{CL_LIVE:X}
        test eax, eax
        jz   {name}_out
        lea  ebx, {L(key)}
        {line(name)}
    {name}_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
        """
        b = asm(src, va)
        caves.append((name, va, b))
        out[name] = va
        va = align16(va + len(b))
    return caves, out


E_CAVES, E_ENTRY = e_caves()
FL_LOG, SU_LOG = E_ENTRY["fl_log"], E_ENTRY["su_log"]
G1_CAVE = [va for n, va, _b in E_CAVES if n == "g1_death"][0]
G10_CAVE = [va for n, va, _b in E_CAVES if n == "g10_result"][0]

# ---- AoWTCPCK ------------------------------------------------------------------------------
IAT_EDR = 0x0046E7F4          # IAT cell of AoWE.ExecuteDamageRole (thunk 0x4024F4)
G9_HOOK = 0x004083B8          # call 0x4024AC (TCombatUnit.SetStatus thunk), DL = 8
SETSTATUS_THUNK = 0x004024AC
G9_FN = (0x00408278, 0x004085E9)          # TCombatMoveTE.ExecuteDefaultMove (code part)
G13_HOOK = 0x00407E06         # call dword ptr [edx+0x11C]  (TCombatUnit.Surrender)
G13_VAN = bytes.fromhex("ff921c010000")
G13_FN = (0x00407D10, 0x00407E24)         # TCEndCombatTE.Execute


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def t_caves():
    caves, va = [], T_SLOT[0]
    out = {}
    for name, target, tail in (("cave_fl", FL_LOG, f"jmp 0x{SETSTATUS_THUNK:X}"),
                               ("cave_su", SU_LOG, "jmp dword ptr [edx+0x11C]")):
        pre = "pushad"
        at = va + len(asm(pre, va))
        src = pre + "\n" + anchor("ebx", at) + f"""
        mov  ecx, [ebx+0x{IAT_EDR:X}]
        add  ecx, 0x{(target - EDR) & 0xFFFFFFFF:X}
        call ecx
        popad
        {tail}
        """
        b = asm(src, va)
        caves.append((name, va, b))
        out[name] = va
        va = align16(va + len(b))
    return caves, out


T_CAVES, T_ENTRY = t_caves()


def check_pic():
    """Every anchor's sub constant equals its return address; no absolute operand into a DLL."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for name, va, blob in E_CAVES[1:] + T_CAVES:
        ins = list(md.disasm(blob, va))
        assert sum(len(x.bytes) for x in ins) == len(blob), "%s does not disassemble cleanly" % name
        anchors = 0
        for i, x in enumerate(ins):
            if x.mnemonic == "call" and x.op_str == hex(x.address + 5):
                s = ins[i + 2]
                assert s.mnemonic == "sub" and int(s.op_str.split(",")[1], 16) == x.address + 5, name
                anchors += 1
            if "ptr [0x" in x.op_str:
                sys.exit("ABORT: %s absolute memory operand at %08X: %s" % (name, x.address, x.op_str))
        assert anchors == 1, "%s: %d anchors" % (name, anchors)


check_pic()

E_HOOKS = [(G1_HOOK, G1_VAN, jmp_to(G1_HOOK, G1_CAVE, len(G1_VAN))),
           (G10_HOOK, call_to(G10_HOOK, TERMINATE), call_to(G10_HOOK, G10_CAVE))]
E_INTERIOR = [(G1_HOOK, G1_HOOK + len(G1_VAN)) + G1_FN,
              (G10_HOOK, G10_HOOK + 5) + G10_FN]
T_HOOKS = [(G9_HOOK, call_to(G9_HOOK, SETSTATUS_THUNK), call_to(G9_HOOK, T_ENTRY["cave_fl"])),
           (G13_HOOK, G13_VAN, call_to(G13_HOOK, T_ENTRY["cave_su"]) + b"\x90")]
T_INTERIOR = [(G9_HOOK, G9_HOOK + 5) + G9_FN,
              (G13_HOOK, G13_HOOK + len(G13_VAN)) + G13_FN]


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def check_lib():
    """The library stubs must be installed (an E9 at each entry) before anything calls them."""
    module(EPACK, 0x55700000)
    d = open(EPACK, "rb").read()
    for va in (CL_EMIT, CL_NAME, CL_LIVE):
        if d[P.va2off(d, va)] != 0xE9:
            sys.exit("ABORT: build_combatlog_lib.py is not installed (%08X)" % va)


def go(argv):
    if "--apply" in argv:
        check_lib()
    # AoWTCPCK's caves call into AoWEPACK's: install the callee first, remove the caller first.
    steps = [(EPACK, 0x55700000, "AoWEPACK", E_HOOKS, E_CAVES, E_SLOT, E_INTERIOR),
             (TCPCK, 0x00400000, "AoWTCPCK", T_HOOKS, T_CAVES, T_SLOT, T_INTERIOR)]
    if "--undo" in argv:
        steps.reverse()
    for path, base, tag, hooks, caves, slot, interior in steps:
        module(path, base)
        run("build_combatlog_endings [%s]" % tag, hooks, caves, slot, interior, argv)


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])   # both modules verify first
        print("\n" + "=" * 60)
    go(argv)
