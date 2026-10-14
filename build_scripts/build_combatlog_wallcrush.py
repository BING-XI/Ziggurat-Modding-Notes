#!/usr/bin/env python
r"""
build_combatlog_wallcrush.py -- manual-combat Wall Crushing hits on a wall appear in the combat log.
AoWTCPCK.dpl + AoWEPACK.dpl.  Owner request 2026-10-14.

    Basilisk crushes Wall for 7 damage  (90%, 12 ATK vs -4 DEF)
    Basilisk CRUSHES Wall for 12 damage  (90%, 12 ATK vs -4 DEF)
    Basilisk fails to crush Wall - fumble  (90%, 12 ATK vs -4 DEF)

WHY IT WAS MISSING
    The live log (build_combatlog_dll.py) captures damage at the TDamageCA.Generate/GenerateEx
    tails.  In manual combat a wall-crush builds no combat action at all: AoWTCPCK
    CombatTE.TCAbTouchMoveTE.LastMove @0x409C80 does it inline (ability 0x75, 0x40A232..0x40A2AF):
    reseed from TAoWHSMap.Random, diff = TCAttack[0] (12) - TCityWall.GetDefense (a constant -4),
    ExecuteDamageRole(TCDamage[0], diff) through build_wallcrush_dam.py's thunk 0x43AC00 (damage =
    the attacker's DAM), then TCityWall.SetHitPoints(HP - dealt).  Auto-resolve is unaffected: its
    wall-crush is a damage CA and replays log it (build_replaylog.py).

THE HOOK -- AoWTCPCK
    6 B at 0x40A282 (`mov edx,[ebp-4] ; mov edx,[edx+0x68]`, register-only, no .reloc), right after
    the damage call returns: EAX = damage dealt (0 = miss), [ebp-4] = the TE, [TE+0x1C] = the
    attacker (TTacticalCombatUnit, a TCombatUnit), [TE+0x68] = the wall.  cave_wcl re-reads the
    defence (TCityWall.GetDefense @0x405ACC is `return -4`, no side effects) and TCAttack[0]
    (0x4671A4), calls wc_log, then replays the two moves and resumes at 0x40A288.  wc_log is
    reached by the rebase delta: [IAT cell 0x46E7F4 = AoWE.ExecuteDamageRole 0x55725EAC] +
    (wc_log - 0x55725EAC).

THE LINE -- AoWEPACK wc_log(eax=attacker, edx=dealt, [esp+4]=ATK, [esp+8]=DEF), ret 8
    Same host guard, ring protocol, name rule and odds as build_combatlog_dll.py's worker:
    exe SizeOfImage >= 0x20E000 and 'CLG1' at 0x60D000, ring not full; name = strategic
    GetName (vmt+0xF8) of [attacker+0x4C] behind IsClass(TCombatUnit), else "?"; odds =
    clamp(50 + 5*(ATK-DEF), 10, 90) (the 5% slope).  The roll comes from that script's capture
    of ExecuteDamageRole's RandInt(20) in SCRATCH_R 0x558FA810: >= 18 is the auto-max (CRUSHES),
    <= 1 the auto-miss (fumble).  wc_log resets SCRATCH_R to -1, so the next damage line no longer
    sees this roll.

Rolls: none drawn; the log never changes game state, so peers stay in step.  PIC: rel32, the
delta anchors, IAT cell and module data through the delta; the only absolutes are AoWz.exe's
(0x40003C, 0x60D000..), as in the live logger.
Caves: AoWEPACK 0x5589A800-0x5589ABFF exclusive; AoWTCPCK 0x0043B040-0x0043B0BF exclusive.
Surgical --undo.

    python build_scripts/build_combatlog_wallcrush.py            dry run + state, both modules
    python build_scripts/build_combatlog_wallcrush.py --apply
    python build_scripts/build_combatlog_wallcrush.py --undo
    python build_scripts/build_combatlog_wallcrush.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

EPACK = os.path.join(P.GAME, "AoWEPACK.dpl")
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")

E_SLOT = (0x5589A800, 0x5589AC00)
T_SLOT = (0x0043B040, 0x0043B0C0)

# ---- AoWEPACK ------------------------------------------------------------------------------
EDR        = 0x55725EAC      # AoWE.ExecuteDamageRole (export; the rebase-delta reference)
IS_CLASS   = 0x557010C0      # System.@IsClass thunk (eax=obj, edx=classref) -> al; nil-safe
TCOMBATUNIT_VMT = 0x55715A94
INTTOSTR   = 0x5570158C      # eax=int, edx=@out LStr
LSTRLASG   = 0x55701158      # eax=@dest, edx=src value
LSTRCAT    = 0x55701188      # eax=@dest, edx=src value
LSTRARRCLR = 0x55701148      # eax=@first, edx=count
GETNAME_V  = 0xF8            # strategic unit GetName(eax=unit, edx=@out)
SCRATCH_R  = 0x558FA810      # build_combatlog_dll.py's roll capture (-1 = no roll)
RING, MAGIC = 0x60D000, 0x31474C43
WR, RD, SLOTS = RING + 4, RING + 8, RING + 0x20
SLOT_SZ, SLOTS_N = 128, 64   # the wire format of build_combatlog_exe.py, asserted below

LIT = [("UNKNOWN", "?"),
       ("HIT", " crushes Wall for "),
       ("CRIT", " CRUSHES Wall for "),
       ("MISS", " fails to crush Wall"),
       ("DMG", " damage"),
       ("FUMBLE", " - fumble"),
       ("OPEN", "  ("),
       ("PCT", "%, "),
       ("ATKVS", " ATK vs "),
       ("VSDEF", " DEF)")]


def _check_wire():
    """The ring layout is shared with build_combatlog_exe.py / build_combatlog_dll.py."""
    import re
    here = os.path.dirname(os.path.abspath(__file__))
    t = open(os.path.join(here, "build_combatlog_exe.py")).read()
    m = re.search(r"RING_SLOTS\s*=\s*(\d+);\s*SLOT_SZ\s*=\s*(\d+)", t)
    assert m and (int(m.group(1)), int(m.group(2))) == (SLOTS_N, SLOT_SZ), "ring wire format changed"
    t = open(os.path.join(here, "build_combatlog_dll.py")).read()
    assert re.search(r"SCRATCH_R\s*=\s*0x558FA810", t), "roll capture moved"


_check_wire()


def lstr(s):
    """Delphi const AnsiString: refcount -1, length, chars, NUL, 4-aligned."""
    b = struct.pack("<iI", -1, len(s)) + s.encode("latin1") + b"\0"
    return b + b"\0" * (-len(b) % 4)


def anchor(reg, at):
    return f"call 0x{at + 5:X}\npop {reg}\nsub {reg}, 0x{at + 5:X}\n"


def e_caves():
    data, lit = bytearray(), {}
    for k, s in LIT:
        lit[k] = E_SLOT[0] + len(data) + 8                   # the chars
        data += lstr(s)
    code_va = (E_SLOT[0] + len(data) + 0xF) & ~0xF

    def L(k):
        return f"[edi + 0x{lit[k]:X}]"

    pre = """
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
        mov  [ebp-0x14], eax"""
    at = code_va + len(asm(pre, code_va))
    src = pre + "\n" + anchor("edi", at) + f"""
        mov  eax, [0x40003C]
        cmp  dword ptr [eax+0x400050], 0x20E000
        jb   w_bail
        cmp  dword ptr [0x{RING:X}], 0x{MAGIC:X}
        jne  w_bail
        mov  eax, [0x{WR:X}]
        sub  eax, [0x{RD:X}]
        cmp  eax, {SLOTS_N - 1}
        jae  w_bail
        mov  eax, [edi+0x{SCRATCH_R:X}]
        mov  [ebp-0x18], eax
        mov  dword ptr [edi+0x{SCRATCH_R:X}], -1
        mov  eax, [ebp-0x04]
        lea  edx, [edi+0x{TCOMBATUNIT_VMT:X}]
        call 0x{IS_CLASS:X}
        test al, al
        jz   w_noname
        mov  eax, [ebp-0x04]
        mov  eax, [eax+0x4C]
        test eax, eax
        jz   w_noname
        lea  edx, [ebp-0x0C]
        mov  ecx, [eax]
        call dword ptr [ecx+0x{GETNAME_V:X}]
        jmp  w_verb
    w_noname:
        lea  eax, [ebp-0x0C]
        lea  edx, {L('UNKNOWN')}
        call 0x{LSTRLASG:X}
    w_verb:
        cmp  dword ptr [ebp-0x08], 0
        jle  w_miss
        lea  edx, {L('HIT')}
        cmp  dword ptr [ebp-0x18], 18
        jl   w_hit
        lea  edx, {L('CRIT')}
    w_hit:
        lea  eax, [ebp-0x0C]
        call 0x{LSTRCAT:X}
        mov  eax, [ebp-0x08]
        lea  edx, [ebp-0x14]
        call 0x{INTTOSTR:X}
        lea  eax, [ebp-0x0C]
        mov  edx, [ebp-0x14]
        call 0x{LSTRCAT:X}
        lea  eax, [ebp-0x0C]
        lea  edx, {L('DMG')}
        call 0x{LSTRCAT:X}
        jmp  w_stats
    w_miss:
        lea  eax, [ebp-0x0C]
        lea  edx, {L('MISS')}
        call 0x{LSTRCAT:X}
        mov  eax, [ebp-0x18]
        test eax, eax
        js   w_stats
        cmp  eax, 1
        jg   w_stats
        lea  eax, [ebp-0x0C]
        lea  edx, {L('FUMBLE')}
        call 0x{LSTRCAT:X}
    w_stats:
        lea  eax, [ebp-0x0C]
        lea  edx, {L('OPEN')}
        call 0x{LSTRCAT:X}
        mov  eax, [ebp+0x08]
        sub  eax, [ebp+0x0C]
        imul eax, eax, 5
        add  eax, 50
        cmp  eax, 10
        jge  w_p1
        mov  eax, 10
    w_p1:
        cmp  eax, 90
        jle  w_p2
        mov  eax, 90
    w_p2:
        lea  edx, [ebp-0x14]
        call 0x{INTTOSTR:X}
        lea  eax, [ebp-0x0C]
        mov  edx, [ebp-0x14]
        call 0x{LSTRCAT:X}
        lea  eax, [ebp-0x0C]
        lea  edx, {L('PCT')}
        call 0x{LSTRCAT:X}
        mov  eax, [ebp+0x08]
        lea  edx, [ebp-0x14]
        call 0x{INTTOSTR:X}
        lea  eax, [ebp-0x0C]
        mov  edx, [ebp-0x14]
        call 0x{LSTRCAT:X}
        lea  eax, [ebp-0x0C]
        lea  edx, {L('ATKVS')}
        call 0x{LSTRCAT:X}
        mov  eax, [ebp+0x0C]
        lea  edx, [ebp-0x14]
        call 0x{INTTOSTR:X}
        lea  eax, [ebp-0x0C]
        mov  edx, [ebp-0x14]
        call 0x{LSTRCAT:X}
        lea  eax, [ebp-0x0C]
        lea  edx, {L('VSDEF')}
        call 0x{LSTRCAT:X}
        mov  eax, [ebp-0x0C]
        test eax, eax
        jz   w_clean
        mov  ecx, [eax-4]
        cmp  ecx, {SLOT_SZ - 1}
        jbe  w_len
        mov  ecx, {SLOT_SZ - 1}
    w_len:
        mov  edx, [0x{WR:X}]
        and  edx, {SLOTS_N - 1}
        shl  edx, {SLOT_SZ.bit_length() - 1}
        add  edx, 0x{SLOTS:X}
        mov  [edx], cl
        mov  esi, eax
        lea  edi, [edx+1]
        cld
        rep  movsb
        mov  eax, [0x{WR:X}]
        inc  eax
        mov  [0x{WR:X}], eax
    w_clean:
        lea  eax, [ebp-0x14]
        mov  edx, 3
        call 0x{LSTRARRCLR:X}
    w_bail:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret  8
    """
    return [("data", E_SLOT[0], bytes(data)), ("wc_log", code_va, asm(src, code_va))]


E_CAVES = e_caves()
WC_LOG = E_CAVES[1][1]

# ---- AoWTCPCK ------------------------------------------------------------------------------
T_HOOK = 0x0040A282
T_VAN = bytes.fromhex("8b55fc8b5268")             # mov edx,[ebp-4] ; mov edx,[edx+0x68]
T_RESUME = 0x0040A288
GETDEF = 0x00405ACC                               # CityWall.TCityWall.GetDefense -> -4
TCATTACK = 0x004671A4                             # AoWTC.TCAttack (TCAttack[0] = Wall Crushing ATK)
IAT_EDR = 0x0046E7F4                              # IAT cell of AoWE.ExecuteDamageRole (thunk 0x4024F4)


def t_caves():
    va = T_SLOT[0]
    pre = "pushad\nmov esi, eax"
    at = va + len(asm(pre, va))
    src = pre + "\n" + anchor("ebx", at) + f"""
        mov  eax, [ebp-4]
        mov  eax, [eax+0x68]
        call 0x{GETDEF:X}
        push eax
        push dword ptr [ebx+0x{TCATTACK:X}]
        mov  eax, [ebp-4]
        mov  eax, [eax+0x1C]
        mov  edx, esi
        mov  ecx, [ebx+0x{IAT_EDR:X}]
        add  ecx, 0x{(WC_LOG - EDR) & 0xFFFFFFFF:X}
        call ecx
        popad
        mov  edx, [ebp-4]
        mov  edx, [edx+0x68]
        jmp  0x{T_RESUME:X}
    """
    return [("cave_wcl", va, asm(src, va))]


T_CAVES = t_caves()


def check_pic():
    """Every anchor's sub constant equals its return address; no absolute operand into a DLL."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for name, va, blob in E_CAVES[1:] + T_CAVES:
        ins = list(md.disasm(blob, va))
        assert sum(len(x.bytes) for x in ins) == len(blob), "%s does not disassemble cleanly" % name
        for i, x in enumerate(ins):
            if x.mnemonic == "call" and x.op_str == hex(x.address + 5):
                s = ins[i + 2]
                assert s.mnemonic == "sub" and int(s.op_str.split(",")[1], 16) == x.address + 5, name
            for bad in ("ptr [0x55", "ptr [0x4"):
                if bad in x.op_str and "[0x40003c]" not in x.op_str:
                    sys.exit("ABORT: %s absolute DLL operand at %08X: %s" % (name, x.address, x.op_str))


check_pic()

E_HOOKS = []                                      # the AoWEPACK half is only reached from the cave
T_HOOKS = [(T_HOOK, T_VAN, jmp_to(T_HOOK, T_SLOT[0], len(T_VAN)))]
T_INTERIOR = [(T_HOOK, T_HOOK + len(T_VAN), 0x00409C80, 0x0040A3A0)]


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def go(argv):
    module(EPACK, 0x55700000)
    run("build_combatlog_wallcrush [AoWEPACK]", E_HOOKS, E_CAVES, E_SLOT, [], argv)
    module(TCPCK, 0x00400000)
    run("build_combatlog_wallcrush [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, T_INTERIOR, argv)


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])   # both modules verify first
        print("\n" + "=" * 60)
    go(argv)
