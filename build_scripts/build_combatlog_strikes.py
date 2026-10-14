#!/usr/bin/env python
r"""
build_combatlog_strikes.py -- live combat log: "back at" on the failed-touch counter-strike (W2), and
the Cause Fear / Entangle Strike rolls (G4).  AoWEPACK.dpl + AoWTCPCK.dpl.  Owner request 2026-10-14.

    Shadow hits back at Valkyrie for 4 damage  (55%, 7 ATK vs 6 DEF)      <- was "Shadow hits Valkyrie"
    panicked 60% vs res 8 - landed
    entangled 70% vs res 10 - resisted

W2 -- THE FAILED-TOUCH COUNTER-STRIKE READ AS AN UNPROVOKED HIT
    When a touch attack fails, AoWTCPCK CombatTE.TCAbTouchMoveTE.LastMove has the touched unit strike
    back: `call AoWE.CreateStrikeCA` @0x40ABBE (thunk 0x4027F4), EAX = [TE+0x28] the touched unit,
    EDX = [TE+0x1C] the toucher, CL = 1.  AoWE.CreateStrikeCA @0x557665E4 runs Generate
    (@0x557666F3) BEFORE TSingleTargetCA.SetDefensive (razorplate's wrapper @0x5589A070), so
    build_combatlog_dll.py's worker, which picks "hits back at" from CA+0x0C bit0 at the Generate
    tail, saw 0 and printed "hits" / "CRITS" / "misses".
    The two other cl=1 callers stay plain by owner ruling (2026-10-14): the free swing at a unit
    moving away (0x4089F1) and manual Round Attack (0x40A540) are not counter-blows.  Ordinary melee
    retaliation (TMeleeRound.CreateStrikeCA sets the flag before Generate) is untouched.

    Mechanism -- no game state is touched, CA+0x0C is never written early:
      AoWTCPCK  call-retarget @0x40ABBE (E8 rel32, 4 B operand, nothing displaced) -> tc_w2 @0x43B5C0:
                FLAG := attacker (EAX); call CreateStrikeCA (same EAX/EDX/CL); FLAG := 0; return EAX.
                FLAG is reached by the rebase delta off IAT cell 0x46E7F4 (AoWE.ExecuteDamageRole).
      AoWEPACK  the worker's three verb tests `test byte ptr [ebx+0xC],1 ; jne +8` (6 B each, at
                0x558111C4 CRITS, 0x558111DA hits, 0x558112DF misses) become `jmp` to detours that
                keep the bit test and add w2_match: FLAG <> 0 and FLAG = the worker's attacker
                [ebp-0x0C] -> take the "back at" branch, and clear FLAG (one-shot, so a fault inside
                CreateStrikeCA can mislabel at most one later line of that same unit).
    FLAG = AoWEPACK DATA raw slack 0x558E9B20 (dword; RW page, zero in the file, never written by
    this script).

G4 -- CAUSE FEAR / ENTANGLE STRIKE ROLLS (landed AND resisted)
    TStrikeCA.Generate @0x557668B4, after the inherited Generate (so after the damage line), only on a
    hit: Cause Fear `call HitRole` @0x5576691B with EAX = 10 - RES, EDX = RES (target GetResistance,
    vmt+0x74, the effective value); Entangle Strike `call HitRole` @0x55766955, EAX = 14 - RES,
    EDX = RES.  Both call-retargeted (E8 rel32, reloc-free) to stubs that call HitRole exactly once,
    keep its EAX for the caller, then emit "<status> <pct>% vs res <RES> - landed|resisted".
    pct = clamp(50 + 5*EAX, 10, 90) -- the live HitRole formula (asserted below against the bytes at
    0x55725D9F, so a slope change aborts the build).  Gate: cl_live (manual battle only).
    RNG: HitRole's RandInt is vanilla's RAW draw, unchanged in count and order (tactical combat:
    raw is correct, 12-re-toolchain.md 4.10); the log draws nothing and writes no game state.

LAYOUT
    AoWEPACK 0x5589B000-0x5589B7FF exclusive: 0x5589B000 entry table (5 x 8 B `jmp body`, int3 pad --
    the hooks point here, so bodies can move on a re-tune without touching a hook);
    0x5589B040 literals; 0x5589B0C0 bodies.  Library calls: cl_emit 0x5589AC00, cl_live 0x5589AC20,
    cl_cat_int 0x5589AC30 (build_combatlog_lib.py, asserted installed).
    AoWTCPCK 0x0043B5C0-0x0043B5FF exclusive: tc_w2.
    DATA 0x558E9B20-0x558E9B23 (FLAG); 0x558E9B24-0x558E9B5F unused.

FORWARD HAZARDS
  * build_combatlog_dll.py owns the worker.  This script rewrites 18 of its bytes (the three verb
    tests).  Re-applying build_combatlog_dll.py (forbidden anyway: it would also revert two 5 %-slope
    bytes) would rewrite them and silently drop W2; if its worker is ever rebuilt, run this script's
    --undo FIRST, then re-derive the three windows from the new worker.  --undo restores the exact
    live bytes `f6 43 0c 01 75 08`.
  * build_combatlog_lib.py: g4_emit calls cl_live / cl_cat_int / cl_emit by rel32, so the library's
    --undo refuses while this script is installed.  Undo this script first.
  * rng_audit.py --owners credits combatlog_dll's roll capture (RandInt @0x558114E0) to this script,
    because the worker addresses quoted here are the nearest literals within its 0x400 window.  This
    script draws nothing; that site belongs to build_combatlog_dll.py.
  * W2 relies on CreateStrikeCA producing exactly one Generate for the counter-strike; razorplate's
    tail (0x5589A000) rolls Razor Plate flags but builds no second CA.

Unproven: that the worker's [ebp-0x0C] is the CreateStrikeCA attacker for this CA in every build of
stub_gen (verified for the live stub: `mov edx,[ebp-4]` = Generate's attacker).

    python build_scripts/build_combatlog_strikes.py            dry run + state, both modules
    python build_scripts/build_combatlog_strikes.py --apply
    python build_scripts/build_combatlog_strikes.py --undo
    python build_scripts/build_combatlog_strikes.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run
import build_combatlog_lib as LIB

EPACK = os.path.join(P.GAME, "AoWEPACK.dpl")
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")

E_SLOT = (0x5589B000, 0x5589B800)
T_SLOT = (0x0043B5C0, 0x0043B600)
FLAG = 0x558E9B20                     # DATA raw slack, dword
FLAG_ZONE = (0x558E9B20, 0x558E9B60)  # this package's writable state (assigned)

# ---- AoWEPACK ------------------------------------------------------------------------------
EDR = 0x55725EAC              # AoWE.ExecuteDamageRole (rebase-delta reference for the TC side)
HITROLE = 0x55725D98
LSTRLASG, LSTRCAT, LSTRARRCLR = 0x55701158, 0x55701188, 0x55701148
CL_EMIT, CL_LIVE, CL_CAT_INT = LIB.STUB["cl_emit"], LIB.STUB["cl_live"], LIB.STUB["cl_cat_int"]

G4_SITES = [(0x5576691B, "fear"), (0x55766955, "entangle")]
# worker verb tests: (window VA, live bytes).  back = VA+6+8, plain = VA+6
W2_SITES = [(0x558111C4, "crit"), (0x558111DA, "hit"), (0x558112DF, "miss")]
W2_VAN = bytes.fromhex("f6430c017508")      # test byte ptr [ebx+0xC],1 ; jne $+8
WORKER = (0x55811000, 0x55811000 + 0x491)          # build_combatlog_dll.py's _worker body

ENT_VA, ENT_SZ = 0x5589B000, 8
ENTRIES = ["s_fear", "s_ent", "d_crit", "d_hit", "d_miss"]
ENT = {n: ENT_VA + ENT_SZ * i for i, n in enumerate(ENTRIES)}
LIT_VA = 0x5589B040
BODY_VA = 0x5589B0C0

LITS = [("PANIC", "panicked"), ("ENT", "entangled"), ("SP", " "), ("PCT", "% vs res "),
        ("LAND", " - landed"), ("RES", " - resisted")]


def lstr(s):
    b = struct.pack("<iI", -1, len(s)) + s.encode("latin1") + b"\0"
    return b + b"\0" * (-len(b) % 4)


LIT, _lb = {}, bytearray()
for _k, _s in LITS:
    LIT[_k] = LIT_VA + len(_lb) + 8
    _lb += lstr(_s)
LIT_BLOB = bytes(_lb)
assert LIT_VA + len(LIT_BLOB) <= BODY_VA


def rel(target, anchor):
    o = target - anchor
    return "+ 0x%X" % o if o >= 0 else "- 0x%X" % -o


def body_g4_emit(va):
    """g4_emit([esp+4]=landed, +8=RES, +0xC=diff, +0x10=idx) ret 0x10; preserves EBX/ESI/EDI/EBP."""
    a = va + 13                  # push ebp, mov ebp,esp, push 0, 3 pushes (1+2+2+3) + call (5)
    return f"""
        push ebp
        mov  ebp, esp
        push 0
        push ebx
        push esi
        push edi
        call 0x{a:X}
        pop  edi
        call 0x{CL_LIVE:X}
        test eax, eax
        jz   g_out
        lea  edx, [edi {rel(LIT['PANIC'], a)}]
        cmp  dword ptr [ebp+0x14], 0
        je   g_n
        lea  edx, [edi {rel(LIT['ENT'], a)}]
    g_n:
        lea  eax, [ebp-4]
        call 0x{LSTRLASG:X}
        lea  eax, [ebp-4]
        lea  edx, [edi {rel(LIT['SP'], a)}]
        call 0x{LSTRCAT:X}
        mov  eax, [ebp+0x10]
        imul eax, eax, 5
        add  eax, 50
        cmp  eax, 10
        jge  g_c1
        mov  eax, 10
    g_c1:
        cmp  eax, 90
        jle  g_c2
        mov  eax, 90
    g_c2:
        mov  edx, eax
        lea  eax, [ebp-4]
        call 0x{CL_CAT_INT:X}
        lea  eax, [ebp-4]
        lea  edx, [edi {rel(LIT['PCT'], a)}]
        call 0x{LSTRCAT:X}
        mov  edx, [ebp+0x0C]
        lea  eax, [ebp-4]
        call 0x{CL_CAT_INT:X}
        lea  edx, [edi {rel(LIT['LAND'], a)}]
        cmp  byte ptr [ebp+8], 0
        jne  g_o
        lea  edx, [edi {rel(LIT['RES'], a)}]
    g_o:
        lea  eax, [ebp-4]
        call 0x{LSTRCAT:X}
        mov  eax, [ebp-4]
        call 0x{CL_EMIT:X}
    g_out:
        lea  eax, [ebp-4]
        mov  edx, 1
        call 0x{LSTRARRCLR:X}
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret  0x10
    """


def body_stub(idx, g4_emit):
    """Replaces `call HitRole` (EAX = diff, EDX = RES): one HitRole call, result passed through."""
    return f"""
        push ebx
        push esi
        mov  ebx, eax
        mov  esi, edx
        call 0x{HITROLE:X}
        push eax
        push {idx}
        push ebx
        push esi
        push eax
        call 0x{g4_emit:X}
        pop  eax
        pop  esi
        pop  ebx
        ret
    """


def body_match(va):
    """ZF=1 iff FLAG <> 0 and FLAG = [ebp-0x0C] (the worker's attacker); then FLAG := 0.
    Preserves every register."""
    a = va + 7                                   # push eax (1) + push ecx (1) + call (5)
    return f"""
        push eax
        push ecx
        call 0x{a:X}
        pop  ecx
        mov  eax, [ecx {rel(FLAG, a)}]
        test eax, eax
        jz   m_no
        cmp  eax, [ebp-0x0C]
        jne  m_no
        mov  dword ptr [ecx {rel(FLAG, a)}], 0
        pop  ecx
        pop  eax
        ret
    m_no:
        or   ecx, 1
        pop  ecx
        pop  eax
        ret
    """


def body_detour(win, match):
    back, plain = win + 6 + 8, win + 6
    return f"""
        test byte ptr [ebx+0x0C], 1
        jne  0x{back:X}
        call 0x{match:X}
        je   0x{back:X}
        jmp  0x{plain:X}
    """


def e_build():
    B, caves, va = {}, [], BODY_VA

    def place(name, src_fn):
        nonlocal va
        blob = asm(src_fn(va), va)
        B[name] = va
        caves.append((name, va, blob))
        va = (va + len(blob) + 0xF) & ~0xF

    place("g4_emit", body_g4_emit)
    place("s_fear", lambda v: body_stub(0, B["g4_emit"]))
    place("s_ent", lambda v: body_stub(1, B["g4_emit"]))
    place("w2_match", body_match)
    for win, n in W2_SITES:
        place("d_" + n, lambda v, w=win: body_detour(w, B["w2_match"]))
    assert va <= E_SLOT[1], "bodies overflow the slot"
    ents = bytearray()
    for n in ENTRIES:
        s = ENT[n]
        ents += b"\xE9" + struct.pack("<i", B[n] - (s + 5)) + b"\xCC" * (ENT_SZ - 5)
    return B, [("entries", ENT_VA, bytes(ents)), ("literals", LIT_VA, LIT_BLOB)] + caves


BODIES, E_CAVES = e_build()


def check_g4_emit_anchor():
    """g4_emit's anchor was computed from a provisional assembly; prove the call $+5 sits there."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    blob = dict((n, (v, b)) for n, v, b in E_CAVES)["g4_emit"]
    ins = list(Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob[1], blob[0]))
    calls = [x for x in ins if x.mnemonic == "call" and x.op_str == hex(x.address + 5)]
    assert len(calls) == 1, "g4_emit anchor missing"
    want = calls[0].address + 5
    for x in ins:
        if "[edi " in x.op_str and x.mnemonic == "lea":
            disp = int(x.op_str.split("edi ")[1].rstrip("]").replace(" ", ""), 16)
            assert want + disp in LIT.values(), "g4_emit literal %08X off its anchor" % (want + disp)


check_g4_emit_anchor()

# ---- AoWTCPCK ------------------------------------------------------------------------------
T_HOOK = 0x0040ABBE               # call AoWE.CreateStrikeCA (failed-touch counter-strike)
CSCA_THUNK = 0x004027F4           # jmp [0x46E674]
IAT_EDR = 0x0046E7F4              # IAT cell of AoWE.ExecuteDamageRole (thunk 0x4024F4)
EDR_THUNK = 0x004024F4


def t_build():
    va = T_SLOT[0]
    a = va + 7                        # push ebx (1) + push esi (1) + call (5)
    src = f"""
        push ebx
        push esi
        call 0x{a:X}
        pop  ebx
        sub  ebx, 0x{a:X}
        mov  esi, [ebx + 0x{IAT_EDR:X}]
        add  esi, 0x{(FLAG - EDR) & 0xFFFFFFFF:X}
        mov  [esi], eax
        call 0x{CSCA_THUNK:X}
        mov  dword ptr [esi], 0
        pop  esi
        pop  ebx
        ret
    """
    return [("tc_w2", va, asm(src, va))]


T_CAVES = t_build()


def check_pic():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    import re
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for name, va, blob in E_CAVES[2:] + T_CAVES:
        ins = list(md.disasm(blob, va))
        assert sum(len(x.bytes) for x in ins) == len(blob), "%s does not disassemble cleanly" % name
        for i, x in enumerate(ins):
            if x.mnemonic == "call" and x.op_str == hex(x.address + 5):
                assert ins[i + 1].mnemonic == "pop", name
            for m in re.finditer(r"\[(0x[0-9a-f]+)\]", x.op_str):
                sys.exit("ABORT: %s absolute operand at %08X: %s" % (name, x.address, x.op_str))
            if x.mnemonic in ("push", "mov") and re.search(r"0x55[0-9a-f]{6}", x.op_str) and "[" not in x.op_str:
                sys.exit("ABORT: %s immediate DLL address at %08X: %s" % (name, x.address, x.op_str))


check_pic()


def e8(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


E_HOOKS = [(va, e8(va, HITROLE), e8(va, ENT["s_" + ("fear" if n == "fear" else "ent")]))
           for va, n in G4_SITES] + \
          [(va, W2_VAN, jmp_to(va, ENT["d_" + n], 6)) for va, n in W2_SITES]
E_INTERIOR = [(va, va + 5, 0x557668B4, 0x55766970) for va, _n in G4_SITES] + \
             [(va, va + 6, WORKER[0], WORKER[1]) for va, _n in W2_SITES]
T_HOOKS = [(T_HOOK, e8(T_HOOK, CSCA_THUNK), e8(T_HOOK, T_SLOT[0]))]
T_INTERIOR = [(T_HOOK, T_HOOK + 5, 0x00409C80, 0x0040B208)]


def preflight():
    """Read-only facts the caves depend on; abort on any mismatch."""
    P.IMAGE_BASE = 0x55700000
    d = open(EPACK, "rb").read()

    def rd(va, n):
        o = P.va2off(d, va)
        return bytes(d[o:o + n])
    lo, hi = LIB.SLOT
    if rd(lo, hi - lo) != LIB.IMAGE:
        sys.exit("ABORT: build_combatlog_lib.py is not installed (slot %08X differs)" % lo)
    # live HitRole: chance = clamp(50 + 5*eax, 10, 90)
    if rd(0x55725D9F, 6) != bytes.fromhex("6bc00583c032") or rd(0x55725DA7, 3) != bytes.fromhex("83fb0a") \
            or rd(0x55725DB1, 3) != bytes.fromhex("83fb5a"):
        sys.exit("ABORT: HitRole's slope/clamp bytes changed -- the printed odds would be wrong")
    # the two roll sites' operands: 10 - RES / 14 - RES, RES in EDX
    if rd(0x55766913, 8) != bytes.fromhex("b80a0000005a2bc2") or rd(0x5576694D, 8) != bytes.fromhex("b80e0000005a2bc2"):
        sys.exit("ABORT: the Cause Fear / Entangle Strike operand setup changed")
    # worker: the three windows' back/plain targets load the BACK / plain verb literals
    # (the first instruction at each plain target is `lea edx,[edi+lit]`)
    for va, _n in W2_SITES:
        if rd(va + 6, 2) != b"\x8d\x97" or rd(va + 14, 2) != b"\x8d\x97":
            sys.exit("ABORT: worker layout around %08X changed" % va)
    if rd(0x5581100F, 3) != bytes.fromhex("8955f4"):
        sys.exit("ABORT: the worker no longer keeps the attacker at [ebp-0x0C]")
    z = rd(FLAG_ZONE[0], FLAG_ZONE[1] - FLAG_ZONE[0])
    if any(z):
        sys.exit("ABORT: DATA flag zone %08X is not zero in the file" % FLAG_ZONE[0])
    if P.relocs_in(d, FLAG_ZONE[0], FLAG_ZONE[1]):
        sys.exit("ABORT: .reloc inside the DATA flag zone")
    P.IMAGE_BASE = 0x00400000
    t = open(TCPCK, "rb").read()
    o = P.va2off(t, CSCA_THUNK)
    if t[o:o + 6] != b"\xff\x25" + struct.pack("<I", 0x46E674):
        sys.exit("ABORT: AoWTCPCK thunk 0x4027F4 is not jmp [CreateStrikeCA]")
    o = P.va2off(t, EDR_THUNK)
    if t[o:o + 6] != b"\xff\x25" + struct.pack("<I", IAT_EDR):
        sys.exit("ABORT: AoWTCPCK thunk 0x4024F4 is not jmp [ExecuteDamageRole]")
    o = P.va2off(t, 0x0040ABAE)
    if t[o:o + 16] != bytes.fromhex("8902 8b45fc 8b501c 8b45fc 8b4028 b101".replace(" ", "")):
        sys.exit("ABORT: AoWTCPCK failed-touch counter-strike setup changed")
    print("preflight: library installed, HitRole 5% slope, roll operands, worker layout, flag zone, "
          "TC thunks -- ok")


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def go(argv):
    module(EPACK, 0x55700000)
    run("build_combatlog_strikes [AoWEPACK]", E_HOOKS, E_CAVES, E_SLOT, E_INTERIOR, argv)
    module(TCPCK, 0x00400000)
    run("build_combatlog_strikes [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, T_INTERIOR, argv)


if __name__ == "__main__":
    argv = sys.argv[1:]
    preflight()
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])   # both modules verify first
        print("\n" + "=" * 60)
    go(argv)
