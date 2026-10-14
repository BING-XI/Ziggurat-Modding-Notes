#!/usr/bin/env python
r"""
build_combatlog_lib.py -- shared helper library for combat-log lines, in AoWEPACK.dpl (2026-10-14).

Seven small routines that any cave can call to build and emit a combat-log line, so a new log line
does not have to copy the host guard, the ring protocol, the name rule and the LStr idioms of
build_combatlog_dll.py's worker again.  INERT until a caller exists: nothing in any binary calls
these addresses when this script is first applied, and nothing here hooks anything.

THE CONTRACT -- fixed entry addresses (a 5-byte `jmp` to the body, padded to 8 B with int3)
---------------------------------------------------------------------------------------------
Delphi register convention: arguments in EAX, EDX, ECX; EBX/ESI/EDI/EBP are preserved; EAX/EDX/ECX
may be clobbered (callers treat them as lost); no stack arguments, nothing for the caller to clean.
Reach them with a plain `call rel32` from any AoWEPACK cave (both ends rebase together).  From another
module use the rebase-delta idiom (build_combatlog_wallcrush.py: IAT cell + (target - export)).

  VA          name            in                                   out / effect
  0x5589AC00  cl_emit         EAX = LStr value (nil allowed)       if cl_live: one ring slot := the
                                                                   line (shortstring, cut at 127 chars),
                                                                   wrIdx += 1; dropped if the ring holds
                                                                   63 unread lines.  Else nothing.
  0x5589AC08  cl_emit_replay  EAX = LStr value (nil allowed)       appends the line straight to the log
                                                                   window's memo (TStringList.Add) and
                                                                   sets the scroll flag [form+0x70] := 1.
                                                                   For code that runs during a REPLAY,
                                                                   where the ring is not drained.  Nothing
                                                                   if the host guard fails, the value is
                                                                   nil, or the window/memo/list is nil.
  0x5589AC10  cl_name         EAX = combat object (nil / wall /    dest := strategic GetName of a
                              anything), EDX = @dest LStr          TCombatUnit's [obj+0x4C] / "Wall" for a
                                                                   TCombatWall / "?" otherwise (also nil,
                                                                   or a TCombatUnit with no unit link)
  0x5589AC18  cl_unitname     EAX = strategic TAbstractUnit (may   dest := GetName (vmt+0xF8) / "?" for
                              be nil), EDX = @dest LStr            nil or a non-TAbstractUnit
  0x5589AC20  cl_live         --                                   EAX = 1 iff the host guard passes AND
                                                                   magic 'CLG1' AND RING_TACTICAL == 1,
                                                                   else EAX = 0.  Clobbers EAX only.
  0x5589AC28  cl_take_roll    --                                   EAX = SCRATCH_R (the last
                                                                   ExecuteDamageRole RandInt(20), -1 =
                                                                   none), then SCRATCH_R := -1.
                                                                   Clobbers EAX only.
  0x5589AC30  cl_cat_int      EAX = @dest LStr, EDX = signed int   dest := dest + decimal(EDX)
  0x5589AC38 .. 0x5589AC7F    reserved for future entries; zero.  Do not call.

  @dest is the ADDRESS of an LStr variable (a stack slot the caller zeroed, or any live LStr): the
  routines assign through the VCL (@LStrLAsg / @LStrCat / the GetName result), so whatever it held is
  released properly.  The caller still owns it and must @LStrArrayClr / @LStrClr it before returning.
  A line is built with the caller's own @LStrCat (0x55701188) on cave literals with refcount -1.

WHAT THE GUARDS MEAN
  host guard   [0x40003C] = e_lfanew of the process exe; [e_lfanew + 0x400050] = its SizeOfImage
               >= 0x20E000, then 'CLG1' (0x31474C43) at 0x60D000.  AoWDevEd.exe / AoWzEd.exe load
               this DLL too and have no .clog section; the size test comes first so 0x60D000 is
               never read there.
  RING_TACTICAL [0x60D00C]: build_combatlog_exe.py's flag, set to 1 by its cave on
               TCMapActivateMap (hook 0x4581A4 -> 0x6106E0) and to 0 on TCMapDeActivateMap (hook
               0x458570 -> 0x610700) -- 1 exactly while a manual (tactical-map) battle is on.  An
               auto-resolved battle never sets it, so cl_emit is silent there: that is the live
               logger's fast-combat gate (FastCombatWin aborts its animation on a log-window blit).
               Replays go through cl_emit_replay instead.
  ring         0x60D000: +0 magic, +4 wrIdx (DLL-owned), +8 rdIdx (exe-owned), +0xC RING_TACTICAL,
               +0x20 64 slots x 128 B shortstrings.  Same layout check as the other ring writers
               (_check_wire below reads build_combatlog_exe.py).
  memo chain   [0x45B2E0] TCombatLogWin instance -> +0x48 memo -> +0x118 TStringList -> vmt+0x34 Add
               (eax = list, edx = LStr); [form+0x70] = TChatWindow.ChatMemoUpdate's scroll flag
               (build_combatlog_autoscroll.py).
  names        IsClass(obj, TCombatUnit 0x55715A94) BEFORE [obj+0x4C] (a TCombatWall keeps packed
               bytes there -- the Blt Error / freeze family, 07-ui.md 1.7); IsClass(obj, TCombatWall
               0x55715C40) -> "Wall".  cl_unitname additionally gates on IsClass(unit, TAbstractUnit
               0x55710740) so a wrong pointer type cannot reach a foreign vmt+0xF8.

SAFETY -- these run inside the combat pump, where an exception freezes the game
  Every pointer is nil-checked or class-checked before it is dereferenced; nothing allocates except
  through the VCL string thunks; no randomness is drawn (cl_take_roll only reads/clears the capture
  that build_combatlog_dll.py's roll hook writes) and no game state is written.  The only writes are
  the exe ring / memo, SCRATCH_R (cl_take_roll) and the caller's @dest.

PIC
  Each body that reaches a DLL address uses its own `call $+5; pop reg` anchor (literals, the class
  VMTs, SCRATCH_R).  VCL thunks and other bodies are rel32.  The only absolute operands are AoWz.exe's
  (0x40003C, 0x45B2E0, 0x60D000..0x60D00C, the slots) -- the exe never rebases.  check_pic() aborts the
  build on any absolute DLL operand or an anchor whose `sub` constant disagrees with its return address.

LAYOUT -- slot 0x5589AC00-0x5589AFFF, exclusive to this script (zero, no .reloc, 2026-10-14)
  0x5589AC00  7 entry stubs x 8 B          0x5589AC38  reserved (zero)
  0x5589AC80  literals "?" / "Wall"         0x5589ACA0  bodies, each 16-aligned
  No writable state.  (AoWEPACK DATA slack 0x558E9BA0-0x558E9BFF was offered and is NOT used.)

FORWARD HAZARD
  Once callers exist, --undo would leave them calling zeros.  --undo therefore scans AoWEPACK.dpl for
  any rel32 call/jmp into the slot from outside it and refuses while one exists; callers in another
  module (reached by the rebase delta) cannot be found that way -- undo those features first.
  A re-tune rewrites the slot in place (accepted when the slot is zero, holds this exact image, or
  holds a previous build of this script, recognised by its stub table).  Stub addresses never move.

    python build_scripts/build_combatlog_lib.py           dry run + state
    python build_scripts/build_combatlog_lib.py --apply
    python build_scripts/build_combatlog_lib.py --undo
    python build_scripts/build_combatlog_lib.py --dis     (with any of the above)
"""
import os, re, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm

SLOT = (0x5589AC00, 0x5589B000)
STUB_BASE, STUB_SZ = 0x5589AC00, 8
RESERVED = (0x5589AC38, 0x5589AC80)
LIT_VA = 0x5589AC80
BODY_VA = 0x5589ACA0

ENTRIES = ["cl_emit", "cl_emit_replay", "cl_name", "cl_unitname", "cl_live", "cl_take_roll",
           "cl_cat_int"]
STUB = {n: STUB_BASE + STUB_SZ * i for i, n in enumerate(ENTRIES)}
assert STUB == {"cl_emit": 0x5589AC00, "cl_emit_replay": 0x5589AC08, "cl_name": 0x5589AC10,
                "cl_unitname": 0x5589AC18, "cl_live": 0x5589AC20, "cl_take_roll": 0x5589AC28,
                "cl_cat_int": 0x5589AC30}, "the entry addresses are a fixed contract"
assert STUB_BASE + STUB_SZ * len(ENTRIES) == RESERVED[0]

# ---- AoWEPACK (rebases: reached rel32 or through an anchor) --------------------------------
IS_CLASS = 0x557010C0          # System.@IsClass thunk (eax=obj, edx=classref value) -> al
LSTRLASG = 0x55701158          # eax=@dest, edx=src value
LSTRCAT = 0x55701188           # eax=@dest, edx=src value -> dest := dest + src
LSTRARRCLR = 0x55701148        # eax=@first, edx=count
INTTOSTR = 0x5570158C          # eax=int, edx=@out LStr
TCOMBATUNIT_VMT = 0x55715A94
TCOMBATWALL_VMT = 0x55715C40
TABSTRACTUNIT_VMT = 0x55710740  # self-ptr at 0x55710700, the cell vanilla code loads it from
GETNAME_V = 0xF8               # TAbstractUnit.GetName (eax=unit, edx=@out)
UNIT_LINK = 0x4C               # TCombatUnit -> strategic unit (TCombatUnit ONLY)
SCRATCH_R = 0x558FA810         # build_combatlog_dll.py's roll capture, -1 = none

# ---- AoWz.exe (fixed base 0x400000) ---------------------------------------------------------
RING, MAGIC = 0x60D000, 0x31474C43
WR, RD, RING_TACTICAL, SLOTS = RING + 4, RING + 8, RING + 0xC, RING + 0x20
SLOT_SZ, SLOTS_N = 128, 64
MIN_SOI = 0x20E000
GVAR_INSTANCE, MEMO_OFF, FSTRINGS_OFF, ADD_V, SCROLL_FLAG = 0x45B2E0, 0x48, 0x118, 0x34, 0x70


def _check_wire():
    """Constants shared with the scripts that own them; a silent mismatch corrupts the ring."""
    here = os.path.dirname(os.path.abspath(__file__))
    t = open(os.path.join(here, "build_combatlog_exe.py")).read()
    m = re.search(r"RING_SLOTS\s*=\s*(\d+);\s*SLOT_SZ\s*=\s*(\d+)", t)
    assert m and (int(m.group(1)), int(m.group(2))) == (SLOTS_N, SLOT_SZ), "ring wire format changed"
    assert re.search(r"RING_TACTICAL\s*=\s*0x60D00C", t), "RING_TACTICAL moved"
    assert re.search(r"GVAR_INSTANCE\s*=\s*0x45B2E0", t), "log window global moved"
    t = open(os.path.join(here, "build_combatlog_dll.py")).read()
    assert re.search(r"SCRATCH_R\s*=\s*0x558FA810", t), "roll capture moved"
    t = open(os.path.join(here, "build_replaylog.py")).read()
    assert re.search(r"MEMO_OFF=0x48; FSTRINGS_OFF=0x118; ADD_V=0x34", t), "memo chain changed"
    assert re.search(r"SCROLL_FLAG=0x70", t), "scroll flag moved"


_check_wire()


def lstr(s):
    """Delphi const AnsiString: refcount -1, length, chars, NUL, 4-aligned."""
    b = struct.pack("<iI", -1, len(s)) + s.encode("latin1") + b"\0"
    return b + b"\0" * (-len(b) % 4)


LITS = [("Q", "?"), ("WALL", "Wall")]
LIT, _lit = {}, bytearray()
for _k, _s in LITS:
    LIT[_k] = LIT_VA + len(_lit) + 8           # the chars = the LStr value
    _lit += lstr(_s)
LIT_BLOB = bytes(_lit)
assert LIT_VA + len(LIT_BLOB) <= BODY_VA


def rel(target, anchor):
    o = target - anchor
    return "+ 0x%X" % o if o >= 0 else "- 0x%X" % -o


def host_guard(fail):
    return f"""
        mov  eax, [0x40003C]
        cmp  dword ptr [eax+0x400050], 0x{MIN_SOI:X}
        jb   {fail}
        cmp  dword ptr [0x{RING:X}], 0x{MAGIC:X}
        jne  {fail}"""


def body_live(va, B):
    return f"""
        {host_guard("lv_no")}
        cmp  dword ptr [0x{RING_TACTICAL:X}], 1
        jne  lv_no
        mov  eax, 1
        ret
    lv_no:
        xor  eax, eax
        ret
    """


def body_take_roll(va, B):
    a = va + 6                                  # push ecx (1) + call (5)
    return f"""
        push ecx
        call 0x{a:X}
        pop  ecx
        mov  eax, [ecx {rel(SCRATCH_R, a)}]
        mov  dword ptr [ecx {rel(SCRATCH_R, a)}], -1
        pop  ecx
        ret
    """


def body_cat_int(va, B):
    return f"""
        push ebx
        mov  ebx, eax
        push 0
        mov  eax, edx
        mov  edx, esp
        call 0x{INTTOSTR:X}
        mov  eax, ebx
        mov  edx, [esp]
        call 0x{LSTRCAT:X}
        mov  eax, esp
        mov  edx, 1
        call 0x{LSTRARRCLR:X}
        pop  ecx
        pop  ebx
        ret
    """


def body_unitname(va, B):
    a = va + 12                                 # 3 pushes + 2 movs (2 B each) + call (5)
    return f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        call 0x{a:X}
        pop  edi
        test ebx, ebx
        jz   un_q
        mov  eax, ebx
        lea  edx, [edi {rel(TABSTRACTUNIT_VMT, a)}]
        call 0x{IS_CLASS:X}
        test al, al
        jz   un_q
        mov  eax, ebx
        mov  edx, esi
        mov  ecx, [ebx]
        call dword ptr [ecx+0x{GETNAME_V:X}]
        jmp  un_done
    un_q:
        mov  eax, esi
        lea  edx, [edi {rel(LIT['Q'], a)}]
        call 0x{LSTRLASG:X}
    un_done:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """


def body_name(va, B):
    a = va + 12
    return f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        call 0x{a:X}
        pop  edi
        test ebx, ebx
        jz   nm_q
        mov  eax, ebx
        lea  edx, [edi {rel(TCOMBATUNIT_VMT, a)}]
        call 0x{IS_CLASS:X}
        test al, al
        jz   nm_notunit
        mov  eax, [ebx+0x{UNIT_LINK:X}]
        mov  edx, esi
        call 0x{B['cl_unitname']:X}
        jmp  nm_done
    nm_notunit:
        mov  eax, ebx
        lea  edx, [edi {rel(TCOMBATWALL_VMT, a)}]
        call 0x{IS_CLASS:X}
        test al, al
        jz   nm_q
        mov  eax, esi
        lea  edx, [edi {rel(LIT['WALL'], a)}]
        call 0x{LSTRLASG:X}
        jmp  nm_done
    nm_q:
        mov  eax, esi
        lea  edx, [edi {rel(LIT['Q'], a)}]
        call 0x{LSTRLASG:X}
    nm_done:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """


def body_emit(va, B):
    return f"""
        push esi
        push edi
        mov  esi, eax
        test esi, esi
        jz   em_out
        call 0x{B['cl_live']:X}
        test eax, eax
        jz   em_out
        mov  eax, [0x{WR:X}]
        sub  eax, [0x{RD:X}]
        cmp  eax, {SLOTS_N - 1}
        jae  em_out
        mov  ecx, [esi-4]
        cmp  ecx, {SLOT_SZ - 1}
        jbe  em_len
        mov  ecx, {SLOT_SZ - 1}
    em_len:
        mov  edx, [0x{WR:X}]
        and  edx, {SLOTS_N - 1}
        shl  edx, {SLOT_SZ.bit_length() - 1}
        add  edx, 0x{SLOTS:X}
        mov  [edx], cl
        lea  edi, [edx+1]
        cld
        rep  movsb
        inc  dword ptr [0x{WR:X}]
    em_out:
        pop  edi
        pop  esi
        ret
    """


def body_emit_replay(va, B):
    return f"""
        push ebx
        mov  ebx, eax
        test ebx, ebx
        jz   er_out
        {host_guard("er_out")}
        mov  eax, [0x{GVAR_INSTANCE:X}]
        test eax, eax
        jz   er_out
        mov  eax, [eax+0x{MEMO_OFF:X}]
        test eax, eax
        jz   er_out
        mov  eax, [eax+0x{FSTRINGS_OFF:X}]
        test eax, eax
        jz   er_out
        mov  edx, ebx
        mov  ecx, [eax]
        call dword ptr [ecx+0x{ADD_V:X}]
        mov  eax, [0x{GVAR_INSTANCE:X}]
        test eax, eax
        jz   er_out
        mov  byte ptr [eax+0x{SCROLL_FLAG:X}], 1
    er_out:
        pop  ebx
        ret
    """


# assembled in dependency order: a body only calls bodies placed before it
ORDER = [("cl_live", body_live), ("cl_take_roll", body_take_roll), ("cl_cat_int", body_cat_int),
         ("cl_unitname", body_unitname), ("cl_name", body_name), ("cl_emit", body_emit),
         ("cl_emit_replay", body_emit_replay)]


def build():
    B, caves, va = {}, [], BODY_VA
    for name, fn in ORDER:
        blob = asm(fn(va, B), va)
        B[name] = va
        caves.append(("body " + name, va, blob))
        va = (va + len(blob) + 0xF) & ~0xF
    assert va <= SLOT[1], "bodies overflow the slot"
    stubs = bytearray()
    for n in ENTRIES:
        s = STUB[n]
        stubs += b"\xE9" + struct.pack("<i", B[n] - (s + 5)) + b"\xCC" * (STUB_SZ - 5)
    return B, [("stubs", STUB_BASE, bytes(stubs)), ("literals", LIT_VA, LIT_BLOB)] + caves


BODIES, CAVES = build()


def image():
    """The whole slot as it must read when installed."""
    img = bytearray(SLOT[1] - SLOT[0])
    for _n, va, blob in CAVES:
        img[va - SLOT[0]:va - SLOT[0] + len(blob)] = blob
    return bytes(img)


IMAGE = image()


def check_pic():
    """Clean disassembly; every anchor's `pop` follows its call and every anchor-relative operand
    was computed against that return address; no absolute operand into the DLL."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    exe_abs = {0x40003C, RING, WR, RD, RING_TACTICAL, GVAR_INSTANCE}
    for name, va, blob in CAVES:
        if not name.startswith("body"):
            continue
        ins = list(md.disasm(blob, va))
        assert sum(len(x.bytes) for x in ins) == len(blob), "%s does not disassemble cleanly" % name
        anchors = 0
        for i, x in enumerate(ins):
            if x.mnemonic == "call" and x.op_str.startswith("dword"):
                continue                        # GetName / Add, through the object's own VMT
            if x.mnemonic == "call" and va <= int(x.op_str, 16) < va + len(blob):
                assert x.op_str == hex(x.address + 5) and ins[i + 1].mnemonic == "pop", \
                    "%s: in-body call at %08X is not a call $+5 / pop anchor" % (name, x.address)
                anchors += 1
            elif x.mnemonic == "call" and not x.op_str.startswith("dword"):
                t = int(x.op_str, 16)
                assert t in (IS_CLASS, LSTRLASG, LSTRCAT, LSTRARRCLR, INTTOSTR) or t in BODIES.values(), \
                    "%s: call to unexpected %08X" % (name, t)
        want = 1 if name in ("body cl_take_roll", "body cl_unitname", "body cl_name") else 0
        assert anchors == want, "%s: %d anchors, expected %d" % (name, anchors, want)
        for i, x in enumerate(ins):
            for m in re.finditer(r"\[(0x[0-9a-f]+)\]", x.op_str):
                v = int(m.group(1), 16)
                if v not in exe_abs:
                    sys.exit("ABORT: %s absolute operand at %08X: %s" % (name, x.address, x.op_str))
            if x.mnemonic in ("push", "mov") and "0x55" in x.op_str and "[" not in x.op_str:
                sys.exit("ABORT: %s immediate DLL address at %08X: %s" % (name, x.address, x.op_str))


check_pic()


def callers_into_slot(d):
    """rel32 call/jmp anywhere in AoWEPACK.dpl, outside the slot, that lands in the stubs or bodies."""
    return [v for v in P.rel32_into(d, SLOT[0] - 1, SLOT[1]) if not SLOT[0] <= v < SLOT[1]]


def prior_build(zone):
    """A previous build of this script: the 7 stubs are E9 jumps into the body area, 3 int3 pads,
    and the reserved range is zero."""
    for i in range(len(ENTRIES)):
        s = zone[STUB_SZ * i:STUB_SZ * (i + 1)]
        if s[0] != 0xE9 or s[5:] != b"\xCC" * (STUB_SZ - 5):
            return False
        t = STUB_BASE + STUB_SZ * i + 5 + struct.unpack_from("<i", s, 1)[0]
        if not BODY_VA <= t < SLOT[1]:
            return False
    r = zone[RESERVED[0] - SLOT[0]:RESERVED[1] - SLOT[0]]
    return not any(r)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="combat-log helper library (AoWEPACK.dpl)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", "--show", action="store_true")
    a = ap.parse_args(argv)

    d = bytearray(open(P.TARGET, "rb").read())
    print("build_combatlog_lib -- %s" % P.TARGET)
    zo, zh = P.va2off(d, SLOT[0]), P.va2off(d, SLOT[1] - 1) + 1
    assert zh - zo == len(IMAGE), "slot crosses a section boundary"
    zone = bytes(d[zo:zh])
    if zone == IMAGE:
        state = "INSTALLED"
    elif not any(zone):
        state = "ZERO"
    elif prior_build(zone):
        state = "OLDER BUILD"
    else:
        state = "FOREIGN"
    rl = P.relocs_in(d, SLOT[0], SLOT[1])
    callers = callers_into_slot(d)
    used = max(va + len(b) for _n, va, b in CAVES) - SLOT[0]
    print("  slot %08X-%08X: %s   (image %d of %d B)" % (SLOT[0], SLOT[1], state, used, len(IMAGE)))
    for n in ENTRIES:
        print("    %08X  %-15s -> body %08X" % (STUB[n], n, BODIES[n]))
    print("  .reloc in slot: %s" % (", ".join("%08X" % v for v in rl) or "none"))
    print("  rel32 callers into the slot: %s" % (", ".join("%08X" % v for v in callers) or "none"))
    if a.dis:
        P.show(CAVES[:1] + CAVES[2:])
        print("\n  ---- literals @%08X: %s" % (LIT_VA, ", ".join('%s @%08X' % (k, v) for k, v in LIT.items())))
    if rl:
        sys.exit("ABORT: .reloc entries inside the slot")
    if state == "FOREIGN":
        sys.exit("ABORT: slot holds bytes this script did not write")
    if not (a.apply or a.undo):
        print("\nstate: %s\n(dry run -- nothing written)" % state)
        return
    if a.apply and state == "INSTALLED":
        print("\nalready installed -- nothing to do")
        return
    if a.undo and state == "ZERO":
        print("\nalready zero -- nothing to do")
        return
    if a.undo and callers:
        sys.exit("ABORT: callers still reach the library -- undo those features first")
    P.kill_aow()
    with open(P.TARGET, "r+b") as f:
        f.seek(zo)
        f.write(IMAGE if a.apply else bytes(len(IMAGE)))
    back = open(P.TARGET, "rb").read()
    assert back[zo:zh] == (IMAGE if a.apply else bytes(len(IMAGE))), "slot did not stick"
    print("\n%s" % ("APPLIED" if a.apply else "UNDONE -- slot zeroed"))


if __name__ == "__main__":
    main(sys.argv[1:])
