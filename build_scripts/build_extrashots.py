#!/usr/bin/env python
r"""
build_extrashots.py -- Extra Shots (ability 0xC1): every missile shot has a CHANCE % chance to let
the unit shoot again, and an extra shot rolls the same way, so runs of extra shots are possible.
AoWEPACK.dpl + AoWTCPCK.dpl.  Owner's design 2026-10-21 (25 %, chaining; missiles only).

WHICH ATTACKS -- MISSILES, every id made by the TRangedAttackAbility factory 0x5576ED48 or the
    TBoltsAbility factory 0x5576EDE8 (asserted against a scan of the whole DLL, cave registrations
    included), minus Call Flames 0x1F (an area attack).  Breaths (TBreathAbility, own
    fcExecuteCombatCommand) and Flame Throwing (own class) are other classes and never reach either
    hook.  Spells cast through the tactical ranged event carry ability id 0x34 and are not in the set.

AUTO-RESOLVE (AoWEPACK)
    F  0x5576EBEF  TRangedAttackAbility.fcExecuteCombatCommand's shot loop `dec edi / cmp edi,-1 /
                   jne 0x5576EBCA` (6 B) -> jmp cave_fc + nop.  EBX = the shooter, EBP = the target,
                   EDI = shots left, [esp] = the ability.  TBoltsAbility inherits this method (VMT
                   +0xA4).  One draw per shot, then: missile, shooter has Extra Shots (combat VMT
                   +0xA8), target still standing (VMT +0x60, the host's own pre-loop test), roll <
                   CHANCE -> back to the loop top with EDI unchanged; else the original countdown.
    RNG   P2 COMBAT RAW: the host is auto-resolve code, run after TCombat.Execute's re-anchor.  The
          draw is hoisted out of every gate (one @RandInt per shot for every shooter), so the draw
          count does not depend on who has the ability (12-re-toolchain.md §4.5).

MANUAL COMBAT (AoWTCPCK)
    T  0x0040F436  TCAbRangedTE.NextStrike's shot count `mov eax,[ebp-4] / add dword [eax+0x34],1`
                   (7 B) -> jmp cave_tc + 2 nop.  [TE+0x34] = shots fired, [TE+0x28] = shots in the
                   attack (set by Execute from GetAttackRepeatRA), [TE+0x14] = the ability id,
                   [TE+0x10] = the shooter.  The cave replays the count; for a missile whose shooter
                   has Extra Shots it draws, and on roll < CHANCE adds one to [TE+0x28].  Execute's
                   per-frame driver (0x0040CB29) reads [TE+0x28] live: it fires again and ends the
                   event only when shots fired reaches it.  Resumes at 0x0040F444 (the IntOver
                   check after the count is dropped: the counter cannot overflow).
    RNG   P1 SYNCED DRAW: NextStrike is in AoWTCPCK's SYNC list (its own TAoWHSMap.Random at
          0x0040D9E4) and raw draws there are cosmetic, so a raw roll would not replicate.  Gated
          on replicated state only (ability id, the shooter's abilities), so every peer draws the
          same number of times.  RandSeed is not restored, as vanilla's own draw here does not.
    The tactical cave does not test the target: an extra shot at a target that has already fallen
    flies to its hex and does nothing (vanilla's remaining shots behave the same).

REGISTRATION (package init -- prove by launching the exe)
    R  0x557BCD6A  `call RegisterAbility` in PassiveAb.RegisterPassiveAbilities (EBX = the control)
                   -> call cave_reg: replays it, then CreateEnhancementAbility 0x5576601C (EAX 0xC1,
                   EDX the name, CX 0x03FF) + RegisterAbility.  Name literal through a call/pop anchor.
    Record (description, cost, mask): build_extrashots_pfs.py.  Ceilings: LADDER 0xC2 in
    build_abilityid_ceilings.py and build_tcablist_ceiling.py.  Hero Offers row at 0 %
    (heroskill_races.json), Ranged column (herodlg_cats.py).

Slots: AoWEPACK 0x558B2200-0x558B23FF exclusive; AoWTCPCK 0x0043B800-0x0043B8FF exclusive.  PIC:
rel32, register-relative, call/pop anchors.  Surgical --undo (both modules).

    python build_scripts/build_extrashots.py            dry run + state (both modules)
    python build_scripts/build_extrashots.py --apply
    python build_scripts/build_extrashots.py --undo
    python build_scripts/build_extrashots.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

EPACK = P.TARGET
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")
ABIL_ID = 0xC1
NAME = "Extra Shots"
MASK = 0x03FF
CHANCE = 25                                     # percent, per shot (owner 2026-10-21)
NOT_MISSILES = {0x1F}                           # Call Flames: two eruptions around the target

# AoWEPACK
E_SLOT = (0x558B2200, 0x558B2400)
CEA, REGISTER, RANDINT = 0x5576601C, 0x55750238, 0x55701080
RANGED_FACTORY, BOLTS_FACTORY = 0x5576ED48, 0x5576EDE8
R_SITE = 0x557BCD6A
F_SITE, F_LOOP, F_DONE = 0x5576EBEF, 0x5576EBCA, 0x5576EBF5
F_VAN = bytes.fromhex("4f83ffff75d5")           # dec edi / cmp edi,-1 / jne 0x5576EBCA
F_FN = (0x5576EB70, 0x5576EC10)                 # TRangedAttackAbility.fcExecuteCombatCommand
# AoWTCPCK
T_SLOT = (0x0043B800, 0x0043B900)
T_SITE, T_BACK = 0x0040F436, 0x0040F444
T_VAN = bytes.fromhex("8b45fc83403401")         # mov eax,[ebp-4] / add dword [eax+0x34],1
T_FN = (0x0040D290, 0x0040F4B0)                 # TCAbRangedTE.NextStrike
T_MAPCELL, T_RANDOM = 0x0046E8D4, 0x0040298C    # AoWHSMap import cell, TAoWHSMap.Random thunk

ANCHOR = b"\xE8\x00\x00\x00\x00"


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def ansistr(s):
    b = s.encode("latin1")
    return struct.pack("<iI", -1, len(b)) + b + b"\0"


def missiles():
    """Ids registered through the two missile factories anywhere in the DLL, minus NOT_MISSILES."""
    d = open(EPACK, "rb").read()
    _e, secs = P.sections(d)
    found = set()
    for vs, sva, rs, ra in secs:
        for i in range(ra, ra + rs - 5):
            if d[i] != 0xE8:
                continue
            src = P.IMAGE_BASE + sva + (i - ra)
            if src + 5 + struct.unpack_from("<i", d, i + 1)[0] in (RANGED_FACTORY, BOLTS_FACTORY):
                for k in range(5, 40):
                    if d[i - k] == 0xB8:
                        found.add(struct.unpack_from("<I", d, i - k + 1)[0])
                        break
    found = {x for x in found if x < 0x100}
    assert NOT_MISSILES <= found, "Call Flames is no longer a TRangedAttackAbility"
    return sorted(found - NOT_MISSILES)


def bitset(ids):
    b = bytearray(32)
    for x in ids:
        b[x // 8] |= 1 << (x % 8)
    return bytes(b)


ANCHOR_SRC = """
        call anc
    anc:
        pop  ecx"""


def with_anchor(src, va, tail, fields):
    """Assemble `src` once -- its ANCHOR_SRC lines are the call/pop anchor (ECX), and each name in
    `fields` is a disp32 placeholder -- then patch every placeholder to (target - anchor) in place,
    so no instruction changes length.  `tail` is appended after 4-byte alignment; a field whose
    target is 'TAIL' points at it."""
    ph = {n: 0x7FFFFF00 + 4 * k for k, n in enumerate(fields)}
    code = bytearray(asm(src.format(**ph), va))
    k = code.find(ANCHOR + b"\x59")
    assert k >= 0 and code.find(ANCHOR + b"\x59", k + 1) < 0, "call/pop anchor not found exactly once"
    anchor = va + k + 5
    while len(code) % 4:
        code += b"\x90"
    tail_va = va + len(code)
    for n, tgt in fields.items():
        pos = [j for j in range(len(code) - 3) if code[j:j + 4] == struct.pack("<I", ph[n])]
        assert len(pos) == 1, "placeholder %s found %d times" % (n, len(pos))
        struct.pack_into("<i", code, pos[0], (tail_va if tgt == "TAIL" else tgt) - anchor)
    return bytes(code) + tail


def build_reg(va):
    code = bytearray(asm(f"call {REGISTER:#x}", va))
    at = va + len(code)
    code += ANCHOR
    anchor = at + 5
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
    code += ansistr(NAME)
    struct.pack_into("<i", code, fix + 2, lit - anchor)
    return bytes(code)


def build_fc(va, bits):
    src = f"""
        mov  eax, 100
        call {RANDINT:#x}
        cmp  eax, {CHANCE}
        jae  normal
        mov  eax, dword ptr [esp]
        mov  edx, dword ptr [eax + 0xc]
        cmp  edx, 0xff
        ja   normal
    {ANCHOR_SRC}
        bt   dword ptr [ecx + {{BITS}}], edx
        jae  normal
        mov  edx, {ABIL_ID:#x}
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        je   normal
        mov  eax, ebp
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        jne  {F_LOOP:#x}
    normal:
        dec  edi
        cmp  edi, -1
        jne  {F_LOOP:#x}
        jmp  {F_DONE:#x}
    """
    return with_anchor(src, va, bits, {"BITS": "TAIL"})


def build_tc(va, bits):
    src = f"""
        mov  eax, dword ptr [ebp - 4]
        add  dword ptr [eax + 0x34], 1
        mov  edx, dword ptr [eax + 0x14]
        cmp  edx, 0xff
        ja   out
    {ANCHOR_SRC}
        bt   dword ptr [ecx + {{BITS}}], edx
        jae  out
        push ecx
        mov  eax, dword ptr [eax + 0x10]
        test eax, eax
        je   out_pop
        mov  edx, {ABIL_ID:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        je   out_pop
        pop  ecx
        mov  eax, dword ptr [ecx + {{CELL}}]
        mov  eax, dword ptr [eax]
        mov  edx, 100
        call {T_RANDOM:#x}
        cmp  eax, {CHANCE}
        jae  out
        mov  eax, dword ptr [ebp - 4]
        inc  dword ptr [eax + 0x28]
        jmp  out
    out_pop:
        pop  ecx
    out:
        jmp  {T_BACK:#x}
    """
    return with_anchor(src, va, bits, {"BITS": "TAIL", "CELL": T_MAPCELL})


def layout():
    bits = bitset(missiles())
    e, va = [], E_SLOT[0]
    for name, fn in (("cave_reg", lambda v: build_reg(v)), ("cave_fc", lambda v: build_fc(v, bits))):
        blob = fn(va)
        e.append((name, va, blob))
        va = (va + len(blob) + 0xF) & ~0xF
    t = [("cave_tc", T_SLOT[0], build_tc(T_SLOT[0], bits))]
    return {n: v for n, v, _b in e + t}, e, t


def check_id():
    """0xC1 must be ours alone: no CreateEnhancementAbility idiom outside our slot registers it,
    and ability_names gives it no other name."""
    d = open(EPACK, "rb").read()
    _e, secs = P.sections(d)
    used = []
    for vs, sva, rs, ra in secs:
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
    named = ability_names.names()
    if named.get(ABIL_ID, NAME) != NAME:
        sys.exit("ABORT: ability_names gives %#x to %r -- re-derive ABIL_ID" % (ABIL_ID, named[ABIL_ID]))
    print("  id %#x ours alone (highest other CreateEnhancementAbility id %#x); Ability.pfs record %s;"
          " ability_names %s" % (ABIL_ID, max(i for i, _s in other),
                                 "present" if ABIL_ID in keys else "absent",
                                 "names it" if ABIL_ID in named else "DOES NOT NAME IT (add to MODDED)"))
    print("  missiles: %s" % ", ".join("%#x %s" % (x, named.get(x, "?")) for x in missiles()))


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


at, E_CAVES, T_CAVES = layout()
# entry points, asserted (and read by rng_audit.py --owners)
ENTRY = {"cave_reg": 0x558B2200, "cave_fc": 0x558B2240, "cave_tc": 0x0043B800}
assert all(at[n] == va for n, va in ENTRY.items()), "the cave layout moved"
E_HOOKS = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, at["cave_reg"])),
           (F_SITE, F_VAN, jmp_to(F_SITE, at["cave_fc"], 6))]
E_INTERIOR = [(F_SITE, F_SITE + 6, F_FN[0], F_FN[1])]
T_HOOKS = [(T_SITE, T_VAN, jmp_to(T_SITE, at["cave_tc"], 7))]
T_INTERIOR = [(T_SITE, T_SITE + 7, T_FN[0], T_FN[1])]


def go(argv):
    module(EPACK, 0x55700000)
    run("build_extrashots [AoWEPACK]", E_HOOKS, E_CAVES, E_SLOT, E_INTERIOR, argv)
    module(TCPCK, 0x00400000)
    run("build_extrashots [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, T_INTERIOR, argv)
    module(EPACK, 0x55700000)


if __name__ == "__main__":
    check_id()
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])   # both modules verify first
        print("\n" + "=" * 60)
    go(argv)
