#!/usr/bin/env python
r"""
build_combatlog_ticks.py -- manual-combat status ticks and expiries appear in the combat log.
AoWEPACK.dpl only.  Owner request 2026-10-14 (combat-log package P5, report G5).

    Goblin burns for 4 damage  (90% vs res 12)
    Goblin resists burning  (70% vs res 16)
    Zombie decays for 2 damage
    Swordsman is no longer Stunned
    Goblin is no longer Burning

WHERE THE EVENTS HAPPEN
    TCombatUnit.NewTurn -> TAbilityOwner.TriggerNewCombatTurn -> ability vmt+0xF8 NewCombatTurn,
    inside TNewCombatTurnCA.Execute (the turn change).  In every override EAX = self = the ability
    (kept in EDI), EDX = the combat object (kept in ESI), CL = the side whose turn starts.
      TDurationAbility.NewCombatTurn @0x55764D8C (Stunned, Webbed, Panicked, Poisoned, Cursed, Holy
        Fear, Vertigo, Bloodlust, Crusader, Nature's Blessing, High Prayer Blessing, Decay ...):
        counter data+0xC; at 0 `call [ecx+0x98]` @0x55764DDC removes the ability from the owner.
      TUnitEnchantmentAbility.NewCombatTurn @0x55765AAC (combat-duration unit enchantments):
        counter data+0xE; at 0 `call [ecx+0x98]` @0x55765AFC.
      TBurningAbility.NewCombatTurn @0x557BA3D4: its own counter copy, removal @0x557BA42A, then
        (still this turn) HitRole(20 - RES) @0x557BA46B and, on a hit, the damage through
        build_burning_sailing.py's hook 0x557BA479 -> cave 0x5582E000 -> ExecuteDamage, then
        0x557BA483 `jmp 0x557BA49A` -> the epilogue 0x557BA49A.
      TDecayAbility.NewCombatTurn @0x557BA728: ExecuteDamage(2) `call [ecx+0x124]` @0x557BA77A
        (EDX = the tick, build_damhp_gapfix.py's imm at 0x557BA772).
    NOT logged: the GetAbilityData==nil cleanup branches 0x55764DF3, 0x55765B13, 0x557BA494 (a
    stale ability with no data is removed; nothing wore off).

THE HOOKS -- six, all reloc-free, none displacing an instruction boundary
    0x55764DDC  FF 91 98 00 00 00 -> E8 xp_dur  + 90   duration expiry
    0x55765AFC  FF 91 98 00 00 00 -> E8 xp_dur  + 90   enchantment expiry
    0x557BA42A  FF 91 98 00 00 00 -> E8 xp_burn + 90   Burning expiry (deferred, see below)
    0x557BA46B  E8 -> HitRole      -> E8 br_roll       call retarget, 4 bytes change
    0x557BA49A  5F 5E 5B C3 8B C0  -> E9 br_ep   + 90  Burning epilogue (pop edi/esi/ebx/ret +
                                                       the 2-byte `mov eax,eax` alignment pad)
    0x557BA77A  FF 91 24 01 00 00 -> E8 dc_tick + 90   decay damage
    A 6-byte `call [ecx+N]` becomes `call stub ; nop`: the stub makes the original virtual call
    itself (EAX/EDX/ECX untouched) and returns to the nop.

THE CAVES -- slot 0x5589D800-0x5589DFFF (exclusive to this script), state DATA 0x558E9AE0-0x558E9AF3
    p5_emit(eax=combat object, edx=kind, ecx=n | ability) builds one line and cl_emit()s it:
        kind 1 "<name> burns for <n> damage  (<p>% vs res <r>)"
        kind 2 "<name> resists burning  (<p>% vs res <r>)"
        kind 3 "<name> decays for <n> damage"
        kind 4 "<name> is no longer <ability [ecx+8]>"
      <name> = cl_name(combat object) (wall-safe); p = clamp(50 + 5*power, 10, 90), HitRole's own
      formula on the power it was handed; r = the RES the engine read (EDX at the call).  The
      ability name is TAbility.GetName's field [ability+8] read directly: the virtual GetName
      (vmt+0x58, TDurationAbility/TUnitEnchantmentAbility overrides) appends the turns left from
      the owner's ability data, which the removal has just deleted.
    br_roll   pass-through HitRole: calls it EXACTLY ONCE with the host's EAX, records
              {combat object, AL, power, RES} in state, returns AL unchanged.  No draw of its own.
    br_ep     the Burning epilogue: if state names this ESI and cl_live: kind 1 with EAX = the
              ExecuteDamage return (the damage actually applied -- burning_sailing's cave jumps to
              0x557BA483 with it still in EAX) or kind 2; then a deferred Burning expiry (kind 4).
              Always clears state, then pop edi / pop esi / pop ebx / ret.
    xp_burn   removal call, then state.X_OBJ := ESI.  Deferred so the last tick's damage line
              comes before "is no longer Burning" (vanilla removes Burning, then burns once more).
    xp_dur    removal call, then kind 4 if cl_live.
    dc_tick   if cl_live: n = min(EDX, GetHitPoints (vmt+0x88, AL signed)) -- exactly the amount
              TCombatObject.ExecuteDamage @0x55726C58 applies -- kind 3 if n > 0; then tail-jumps
              `jmp [ecx+0x124]` with EAX/EDX/ECX restored.  Logged BEFORE the damage so that a
              lethal tick reads "decays" then the death line.
    State (DATA raw slack, RW, file-backed zeros; the file copy is never written):
        +0x00 B_OBJ  +0x04 B_HIT  +0x08 B_POWER  +0x0C B_RES  +0x10 X_OBJ

GATE
    These run in TNewCombatTurnCA.Execute in manual battles, auto-resolve and replay seeks.  Lines
    are built only when cl_live (0x5589AC20) says a manual battle is live; cl_emit gates again.
    br_roll/xp_burn record state unconditionally and br_ep clears it unconditionally.

RNG / game state
    No draw: br_roll replaces the vanilla HitRole call 1:1.  No game state written; the only
    writes are this script's 20 bytes of state and the log ring (through cl_emit).

PIC
    rel32 to HitRole, the lib entries and the VCL thunks; one `call $+5 / pop / sub` anchor per
    routine that reaches a DLL address (literals, state).  No absolute DLL operand.

COUPLINGS / FORWARD HAZARDS
  * build_burning_sailing.py owns 0x557BA479..0x557BA482 and cave 0x5582E000; its tail jumps to
    0x557BA483 -> 0x557BA49A, where br_ep reads EAX as the damage dealt.  This script asserts that
    0x557BA479 is vanilla or burning_sailing's jmp, and that 0x557BA470 `test al,al / je 0x557BA49A`
    and 0x557BA483 `jmp 0x557BA49A` are intact.  A future change that makes the damage path
    leave anything but ExecuteDamage's return in EAX before 0x557BA49A breaks the burn amount.
    Either script can be undone independently.
  * build_damhp_gapfix.py owns the imm32s at 0x557BA475 (burn tick) and 0x557BA772 (decay tick);
    this script only checks their opcode byte (BA) and reads the values at run time.
  * Lethal burning tick: the damage line is emitted after ExecuteDamage returns, so a death line
    emitted inside ExecuteDamage/DestroyObject (combat-log package P3) prints BEFORE the burn line.
    The decay line is emitted before the damage and has no such inversion.

    python build_scripts/build_combatlog_ticks.py           dry run + state
    python build_scripts/build_combatlog_ticks.py --apply
    python build_scripts/build_combatlog_ticks.py --undo    surgical: six sites restored, slot zeroed
    python build_scripts/build_combatlog_ticks.py --dis     (with any of the above)
"""
import os, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, run

SLOT = (0x5589D800, 0x5589E000)
STATE = 0x558E9AE0                 # DATA raw slack 0x558E9AE0-0x558E9B1F assigned to P5
STATE_LEN = 0x40
B_OBJ, B_HIT, B_POWER, B_RES, X_OBJ = (STATE + 0, STATE + 4, STATE + 8, STATE + 0xC, STATE + 0x10)

# ---- AoWEPACK ------------------------------------------------------------------------------
HITROLE    = 0x55725D98      # AoWE.HitRole(eax=power) -> al; clamp(50+5p,10,90) vs RandInt(100)
LSTRCAT    = 0x55701188      # eax=@dest, edx=src value
LSTRARRCLR = 0x55701148      # eax=@first, edx=count
CL_EMIT, CL_NAME, CL_LIVE, CL_CAT_INT = 0x5589AC00, 0x5589AC10, 0x5589AC20, 0x5589AC30
REMOVE_V   = 0x98            # owner vmt+0x98: remove ability (eax=owner, edx=id)
EXECDMG_V  = 0x124           # TCombatObject.ExecuteDamage (eax=obj, edx=dmg) -> eax = applied
GETHP_V    = 0x88            # TCombatObject hit points -> al (signed), as ExecuteDamage reads it

LIT = [("BURNS", " burns for "),
       ("RESISTS", " resists burning"),
       ("DECAYS", " decays for "),
       ("DMG", " damage"),
       ("NOLONGER", " is no longer "),
       ("OPEN", "  ("),
       ("VSRES", "% vs res "),
       ("CLOSE", ")")]

# ---- sites ----------------------------------------------------------------------------------
REMOVE_CALL = bytes.fromhex("ff9198000000")
H_DUR, H_ENCH, H_BEXP = 0x55764DDC, 0x55765AFC, 0x557BA42A
H_ROLL, H_EPI, H_DECAY = 0x557BA46B, 0x557BA49A, 0x557BA77A
EPI_VAN = bytes.fromhex("5f5e5bc38bc0")
DECAY_VAN = bytes.fromhex("ff9124010000")

# Bytes this feature depends on but never writes.  (va, accepted byte strings, why)
BS_HOOK, BS_CAVE = 0x557BA479, 0x5582E000
GUARDS = [
    (0x557BA470, [bytes.fromhex("84c07426")],
     "test al,al / je 0x557BA49A after HitRole: a miss goes straight to the epilogue"),
    (0x557BA483, [bytes.fromhex("eb15")],
     "jmp 0x557BA49A: the damage path reaches the epilogue with ExecuteDamage's EAX"),
    (BS_HOOK, [bytes.fromhex("8bc68b08ff9124010000"),
               b"\xE9" + struct.pack("<i", BS_CAVE - (BS_HOOK + 5)) + b"\x90" * 5],
     "vanilla ExecuteDamage call or build_burning_sailing.py's hook"),
    (0x557BA474, None, "mov edx, tick (build_damhp_gapfix.py) -- opcode BA only"),
    (0x557BA771, None, "mov edx, tick (build_damhp_gapfix.py) -- opcode BA only"),
]


def lstr(s):
    """Delphi const AnsiString: refcount -1, length, chars, NUL, 4-aligned."""
    b = struct.pack("<iI", -1, len(s)) + s.encode("latin1") + b"\0"
    return b + b"\0" * (-len(b) % 4)


def anchor(reg, at):
    return f"call 0x{at + 5:X}\npop {reg}\nsub {reg}, 0x{at + 5:X}\n"


def with_anchor(va, pre, reg, post):
    at = va + len(asm(pre, va)) if pre.strip() else va
    return asm(pre + "\n" + anchor(reg, at) + post, va)


def align16(v):
    return (v + 0xF) & ~0xF


def caves():
    data, lit = bytearray(), {}
    for k, s in LIT:
        lit[k] = SLOT[0] + len(data) + 8
        data += lstr(s)
    out = [("lits", SLOT[0], bytes(data))]

    def L(k):
        return f"[edi + 0x{lit[k]:X}]"

    def cat(k):
        return f"lea eax, [ebp-0x0C]\nlea edx, {L(k)}\ncall 0x{LSTRCAT:X}\n"

    def cat_int(src):
        return f"lea eax, [ebp-0x0C]\nmov edx, {src}\ncall 0x{CL_CAT_INT:X}\n"

    # ---- p5_emit(eax=combat object, edx=kind, ecx=n | ability) ------------------------------
    va = align16(SLOT[0] + len(data))
    pre = """
        push ebp
        mov  ebp, esp
        sub  esp, 0x0C
        push ebx
        push esi
        push edi
        mov  [ebp-0x04], eax
        mov  [ebp-0x08], ecx
        mov  ebx, edx
        xor  eax, eax
        mov  [ebp-0x0C], eax"""
    post = f"""
        mov  eax, [ebp-0x04]
        lea  edx, [ebp-0x0C]
        call 0x{CL_NAME:X}
        cmp  ebx, 1
        je   k_burn
        cmp  ebx, 2
        je   k_res
        cmp  ebx, 3
        je   k_decay
        {cat('NOLONGER')}
        mov  eax, [ebp-0x08]
        test eax, eax
        jz   k_emit
        mov  edx, [eax+8]
        lea  eax, [ebp-0x0C]
        call 0x{LSTRCAT:X}
        jmp  k_emit
    k_burn:
        {cat('BURNS')}
        {cat_int('[ebp-0x08]')}
        {cat('DMG')}
        jmp  k_odds
    k_res:
        {cat('RESISTS')}
        jmp  k_odds
    k_decay:
        {cat('DECAYS')}
        {cat_int('[ebp-0x08]')}
        {cat('DMG')}
        jmp  k_emit
    k_odds:
        {cat('OPEN')}
        mov  edx, [edi + 0x{B_POWER:X}]
        imul edx, edx, 5
        add  edx, 50
        cmp  edx, 10
        jge  k_p1
        mov  edx, 10
    k_p1:
        cmp  edx, 90
        jle  k_p2
        mov  edx, 90
    k_p2:
        lea  eax, [ebp-0x0C]
        call 0x{CL_CAT_INT:X}
        {cat('VSRES')}
        {cat_int(f'[edi + 0x{B_RES:X}]')}
        {cat('CLOSE')}
    k_emit:
        mov  eax, [ebp-0x0C]
        call 0x{CL_EMIT:X}
        lea  eax, [ebp-0x0C]
        mov  edx, 1
        call 0x{LSTRARRCLR:X}
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    """
    emit = with_anchor(va, pre, "edi", post)
    out.append(("p5_emit", va, emit))
    P5_EMIT = va
    va = align16(va + len(emit))

    # ---- br_roll: pass-through HitRole at 0x557BA46B (eax = power, edx = RES) ----------------
    pre = f"""
        push eax
        push edx
        call 0x{HITROLE:X}
        push eax"""
    post = f"""
        mov  [ecx + 0x{B_OBJ:X}], esi
        movzx edx, al
        mov  [ecx + 0x{B_HIT:X}], edx
        mov  edx, [esp+4]
        mov  [ecx + 0x{B_RES:X}], edx
        mov  edx, [esp+8]
        mov  [ecx + 0x{B_POWER:X}], edx
        pop  eax
        add  esp, 8
        ret
    """
    b = with_anchor(va, pre, "ecx", post)
    out.append(("br_roll", va, b))
    BR_ROLL = va
    va = align16(va + len(b))

    # ---- br_ep: the Burning epilogue (jmp from 0x557BA49A) ------------------------------------
    pre = "push eax"
    post = f"""
        mov  eax, [ebx + 0x{B_OBJ:X}]
        or   eax, [ebx + 0x{X_OBJ:X}]
        jz   ep_out
        call 0x{CL_LIVE:X}
        test eax, eax
        jz   ep_clear
        cmp  [ebx + 0x{B_OBJ:X}], esi
        jne  ep_x
        mov  edx, 2
        cmp  dword ptr [ebx + 0x{B_HIT:X}], 0
        je   ep_b
        mov  edx, 1
    ep_b:
        mov  eax, esi
        mov  ecx, [esp]
        call 0x{P5_EMIT:X}
    ep_x:
        cmp  [ebx + 0x{X_OBJ:X}], esi
        jne  ep_clear
        mov  eax, esi
        mov  edx, 4
        mov  ecx, edi
        call 0x{P5_EMIT:X}
    ep_clear:
        xor  eax, eax
        mov  [ebx + 0x{B_OBJ:X}], eax
        mov  [ebx + 0x{X_OBJ:X}], eax
    ep_out:
        pop  eax
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    b = with_anchor(va, pre, "ebx", post)
    out.append(("br_ep", va, b))
    BR_EP = va
    va = align16(va + len(b))

    # ---- xp_burn: Burning removal, deferred line ----------------------------------------------
    pre = f"call dword ptr [ecx + 0x{REMOVE_V:X}]"
    post = f"""
        mov  [ecx + 0x{X_OBJ:X}], esi
        ret
    """
    b = with_anchor(va, pre, "ecx", post)
    out.append(("xp_burn", va, b))
    XP_BURN = va
    va = align16(va + len(b))

    # ---- xp_dur: duration / enchantment removal + line ----------------------------------------
    b = asm(f"""
        call dword ptr [ecx + 0x{REMOVE_V:X}]
        call 0x{CL_LIVE:X}
        test eax, eax
        jz   xd_out
        mov  eax, esi
        mov  edx, 4
        mov  ecx, edi
        call 0x{P5_EMIT:X}
    xd_out:
        ret
    """, va)
    out.append(("xp_dur", va, b))
    XP_DUR = va
    va = align16(va + len(b))

    # ---- dc_tick: decay damage (eax = obj, edx = tick, ecx = vmt) ----------------------------
    b = asm(f"""
        push eax
        push edx
        push ecx
        call 0x{CL_LIVE:X}
        test eax, eax
        jz   dc_go
        mov  eax, [esp+8]
        mov  ecx, [eax]
        call dword ptr [ecx + 0x{GETHP_V:X}]
        movsx ecx, al
        mov  edx, [esp+4]
        cmp  ecx, edx
        jle  dc_min
        mov  ecx, edx
    dc_min:
        test ecx, ecx
        jle  dc_go
        mov  eax, [esp+8]
        mov  edx, 3
        call 0x{P5_EMIT:X}
    dc_go:
        pop  ecx
        pop  edx
        pop  eax
        jmp  dword ptr [ecx + 0x{EXECDMG_V:X}]
    """, va)
    out.append(("dc_tick", va, b))
    DC_TICK = va
    va += len(b)
    assert va <= SLOT[1], "caves overflow the slot"
    return out, dict(P5_EMIT=P5_EMIT, BR_ROLL=BR_ROLL, BR_EP=BR_EP, XP_BURN=XP_BURN,
                     XP_DUR=XP_DUR, DC_TICK=DC_TICK)


CAVES, ENT = caves()


def call5(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


HOOKS = [
    (H_DUR, REMOVE_CALL, call5(H_DUR, ENT["XP_DUR"]) + b"\x90"),
    (H_ENCH, REMOVE_CALL, call5(H_ENCH, ENT["XP_DUR"]) + b"\x90"),
    (H_BEXP, REMOVE_CALL, call5(H_BEXP, ENT["XP_BURN"]) + b"\x90"),
    (H_ROLL, call5(H_ROLL, HITROLE), call5(H_ROLL, ENT["BR_ROLL"])),
    (H_EPI, EPI_VAN, b"\xE9" + struct.pack("<i", ENT["BR_EP"] - (H_EPI + 5)) + b"\x90"),
    (H_DECAY, DECAY_VAN, call5(H_DECAY, ENT["DC_TICK"]) + b"\x90"),
]
INTERIOR = [
    (H_DUR, H_DUR + 6, 0x55764D8C, 0x55764DFD),
    (H_ENCH, H_ENCH + 6, 0x55765AAC, 0x55765B1D),
    (H_BEXP, H_BEXP + 6, 0x557BA3D4, 0x557BA49E),
    (H_ROLL, H_ROLL + 5, 0x557BA3D4, 0x557BA49E),
    (H_EPI, H_EPI + 6, 0x557BA3D4, 0x557BA49A),
    (H_DECAY, H_DECAY + 6, 0x557BA728, 0x557BA784),
]


def check_pic():
    """Every anchor's sub constant equals its return address; no absolute DLL operand; the one
    HitRole call is in br_roll; immediates of the kinds compare as assembled."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    hitrole_calls = []
    for name, va, blob in CAVES[1:]:
        ins = list(md.disasm(blob, va))
        assert sum(len(x.bytes) for x in ins) == len(blob), "%s does not disassemble cleanly" % name
        for i, x in enumerate(ins):
            if x.mnemonic == "call" and x.op_str == hex(x.address + 5):
                s = ins[i + 2]
                assert s.mnemonic == "sub" and int(s.op_str.split(",")[1], 16) == x.address + 5, name
            if "ptr [0x" in x.op_str:
                sys.exit("ABORT: %s absolute operand at %08X: %s" % (name, x.address, x.op_str))
            if x.mnemonic in ("push",) and x.op_str.startswith("0x"):
                sys.exit("ABORT: %s push imm at %08X (keystone imm8 trap)" % (name, x.address))
            if x.mnemonic == "call" and x.op_str == hex(HITROLE):
                hitrole_calls.append((name, x.address))
    assert [n for n, _ in hitrole_calls] == ["br_roll"], "HitRole must be called once, in br_roll"


check_pic()


def check_guards(d):
    bad = []
    for va, accepted, why in GUARDS:
        o = P.va2off(d, va)
        if accepted is None:
            ok = d[o] == 0xBA
            got = d[o:o + 5].hex(" ")
        else:
            n = len(accepted[0])
            got = bytes(d[o:o + n])
            ok = got in accepted
            got = got.hex(" ")
        print("  guard %08X %-30s %s  %s" % (va, got, "ok " if ok else "BAD", why))
        if not ok:
            bad.append(va)
    so = P.va2off(d, STATE)
    st = bytes(d[so:so + STATE_LEN])
    print("  state %08X-%08X (file) %s" % (STATE, STATE + STATE_LEN - 1,
                                            "zero" if not any(st) else "NOT ZERO"))
    if any(st):
        bad.append(STATE)
    if bad:
        sys.exit("ABORT: a guarded byte run moved or the state block is not zero")


def main(argv):
    d = open(P.TARGET, "rb").read()
    print("build_combatlog_ticks -- guards")
    check_guards(d)
    run("build_combatlog_ticks [AoWEPACK]", HOOKS, CAVES, SLOT, INTERIOR, argv)


if __name__ == "__main__":
    main(sys.argv[1:])
