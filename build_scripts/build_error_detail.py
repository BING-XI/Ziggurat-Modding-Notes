#!/usr/bin/env python
r"""
build_error_detail.py -- the game's catch-all error boxes name the real fault.  aowInt.dpl + AoWz.exe.
Owner request 2026-10-10: "adding the fault address to error messages would be nice in general".
Companion of build_te_exception_detail.py (Network.dpl, the turn-event dialog).

Every line added below is SysUtils.ExceptionErrorMessage of the exception being handled:
    Exception <class> in module <module> at <offset>.
    <the exception's own message>
DECODE: static VA = <offset> + the module's preferred base (table in build_te_exception_detail.py).

aowInt.dpl -- every `call MessageBoxA` (thunk 0x5980130C, 36 sites)
    Each control's Draw (buttons, lists, menus, tooltips, the base window's five DrawSurface arms
    "Verify Surface Error" / "Draw Error" / "Blt Error" / "SB Draw Events Error" / "Exception during
    DrawSurface") catches everything and shows a FIXED literal with caption "Error - <name>"; the
    exception is discarded.  Each call is retargeted (rel32 only) to `mbox_detail`, a stdcall
    MessageBoxA replacement: when an exception is live (SysUtils.ExceptObject <> nil) it shows
    "<text>\r\n\r\n<ExceptionErrorMessage>", otherwise the call is passed through untouched -- so a
    MessageBoxA outside an except arm (Setup, CheckIL) behaves exactly as before.
    RTL: aowInt imports none of the three routines; they are reached from its @DoneExcept import
    (IAT 0x598403C4) by fixed VCL30 deltas computed at build time from vcl30.dpl's export table.
    PIC: aowInt rebases like every package -- the cave uses a call/pop anchor and rel32 only.

AoWz.exe -- TFastCombatForm.FCWinDrawSurface's except arm (0x435F26)
    It raises Exception.Create('Exception during FastCombatWin.DrawSurface') and the ORIGINAL is
    lost before aowInt's arm ever sees anything.  The `call Exception.Create` at 0x435F32 (thunk
    0x40143C) is retargeted to `fc_create`, which builds "<that text>\r\n<ExceptionErrorMessage of
    the original>" as a stack AnsiString literal (refcount -1: @LStrAsg in Create copies it, verified
    at VCL30 0x41304784) and calls Create with it.  The aowInt arm that catches the new exception then
    shows both.  RTL via the exe's Exception.Create import (IAT 0x45D400): ExceptObject = -0x308,
    ExceptAddr = -0x2E8, ExceptionErrorMessage = -0x2BC (the same deltas build_te_exception_detail.py
    verifies).

Couplings: build_bltprobe.py (aowInt 0x59807D55) and build_bltprobe_exe.py (AoWz 0x435F26) are
diagnostics hooking these arms' ENTRY, not the retargeted calls; neither is applied (2026-10-10).
Rolls: none.  Slots: aowInt 0x59826000-0x598261FF, AoWz.exe 0x0062B100-0x0062B2FF (.hcol), exclusive.
Surgical --undo (both modules).

    python build_scripts/build_error_detail.py            dry run + state
    python build_scripts/build_error_detail.py --apply
    python build_scripts/build_error_detail.py --undo
    python build_scripts/build_error_detail.py --dis
"""
import os, re, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run

INT = os.path.join(P.GAME, "aowInt.dpl")
EXE = os.path.join(P.GAME, "AoWz.exe")
sys.path.insert(0, os.path.join(P.GAME, "Modding Resources", "re_tools"))

I_SLOT = (0x59826000, 0x59826200)
X_SLOT = (0x0062B100, 0x0062B300)
MBOX_THUNK = 0x5980130C
I_ANCHOR_IAT = 0x598403C4                     # aowInt: VCL30 System.@DoneExcept
X_CREATE_IAT, X_CREATE_THUNK = 0x0045D400, 0x0040143C
X_SITE = 0x00435F32
D_OBJ, D_ADDR, D_MSG = 0x308, 0x2E8, 0x2BC    # from SysUtils.Exception.Create
VCL = dict(create=0x4130F444, obj=0x4130F13C, addr=0x4130F15C, msg=0x4130F188)


def vcl_deltas():
    """aowInt's anchor is @DoneExcept: its VCL30 VA minus each routine's, read from vcl30.dpl."""
    from aowsyms import get_symbols
    _pe, _b, exp, _iat = get_symbols("VCL30.dpl")
    byname = {n: v for v, n in exp.items()}
    for k, n in (("create", "SysUtils.Exception.Create"), ("obj", "SysUtils.ExceptObject"),
                 ("addr", "SysUtils.ExceptAddr"), ("msg", "SysUtils.ExceptionErrorMessage")):
        assert byname[n] == VCL[k], "%s moved in vcl30.dpl" % n
    done = byname["System.@DoneExcept"]
    return done - VCL["obj"], done - VCL["addr"], done - VCL["msg"]


def mbox_cave(va):
    dobj, daddr, dmsg = vcl_deltas()
    anc = va + 17                                 # push ebp(1) mov(2) sub(6) push x3 -> call(5); pop here
    return asm(f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x210
        push ebx
        push esi
        push edi
        call {anc:#x}
        pop  ebx
        sub  ebx, {anc:#x}
        mov  eax, dword ptr [ebx + {I_ANCHOR_IAT:#x}]
        sub  eax, {dobj:#x}
        call eax
        test eax, eax
        je   m_plain
        mov  dword ptr [ebp - 0x208], eax
        lea  edi, [ebp - 0x200]
        mov  esi, dword ptr [ebp + 0xC]
        mov  ecx, 0xA0
        test esi, esi
        je   m_cpend
    m_cp:
        mov  al, byte ptr [esi]
        test al, al
        je   m_cpend
        mov  byte ptr [edi], al
        inc  esi
        inc  edi
        dec  ecx
        jne  m_cp
    m_cpend:
        mov  dword ptr [edi], 0x0A0D0A0D
        add  edi, 4
        mov  eax, dword ptr [ebx + {I_ANCHOR_IAT:#x}]
        sub  eax, {daddr:#x}
        call eax
        mov  edx, eax
        lea  ecx, [ebp - 0x200]
        mov  eax, edi
        sub  eax, ecx
        mov  ecx, 0x1F0
        sub  ecx, eax
        push ecx
        mov  esi, dword ptr [ebx + {I_ANCHOR_IAT:#x}]
        sub  esi, {dmsg:#x}
        mov  eax, dword ptr [ebp - 0x208]
        mov  ecx, edi
        call esi
        mov  byte ptr [edi + eax], 0
        push dword ptr [ebp + 0x14]
        push dword ptr [ebp + 0x10]
        lea  eax, [ebp - 0x200]
        push eax
        push dword ptr [ebp + 8]
        call {MBOX_THUNK:#x}
        jmp  m_out
    m_plain:
        push dword ptr [ebp + 0x14]
        push dword ptr [ebp + 0x10]
        push dword ptr [ebp + 0xC]
        push dword ptr [ebp + 8]
        call {MBOX_THUNK:#x}
    m_out:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret  0x10
    """, va)


def fc_cave(va):
    # eax = class, dl = alloc flag, ecx = the literal message; returns the new exception in eax
    return asm(f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x220
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp - 0x21C], eax
        mov  dword ptr [ebp - 0x220], edx
        mov  esi, ecx
        mov  eax, dword ptr [{X_CREATE_IAT:#x}]
        sub  eax, {D_OBJ:#x}
        call eax
        test eax, eax
        je   f_plain
        mov  dword ptr [ebp - 0x218], eax
        lea  edi, [ebp - 0x200]
        xor  ecx, ecx
        test esi, esi
        je   f_nostock
        mov  ecx, dword ptr [esi - 4]
        cmp  ecx, 0x78
        jbe  f_ok
        mov  ecx, 0x78
    f_ok:
        rep movsb
    f_nostock:
        mov  word ptr [edi], 0x0A0D
        add  edi, 2
        mov  eax, dword ptr [{X_CREATE_IAT:#x}]
        sub  eax, {D_ADDR:#x}
        call eax
        mov  edx, eax
        lea  ecx, [ebp - 0x200]
        mov  eax, edi
        sub  eax, ecx
        mov  ecx, 0x1E0
        sub  ecx, eax
        push ecx
        mov  esi, dword ptr [{X_CREATE_IAT:#x}]
        sub  esi, {D_MSG:#x}
        mov  eax, dword ptr [ebp - 0x218]
        mov  ecx, edi
        call esi
        lea  ecx, [ebp - 0x200]
        add  eax, edi
        sub  eax, ecx
        mov  byte ptr [ecx + eax], 0
        mov  dword ptr [ebp - 0x204], eax
        mov  dword ptr [ebp - 0x208], 0xFFFFFFFF
        lea  ecx, [ebp - 0x200]
        jmp  f_create
    f_plain:
        mov  ecx, esi
    f_create:
        mov  eax, dword ptr [ebp - 0x21C]
        mov  edx, dword ptr [ebp - 0x220]
        call {X_CREATE_THUNK:#x}
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    """, va)


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def int_sites():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    d = open(INT, "rb").read()
    e = struct.unpack_from("<I", d, 0x3C)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    vs, va, rs, raw = struct.unpack_from("<IIII", d, e + 24 + opt + 8)   # CODE
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.skipdata = True
    out = []
    for ins in md.disasm(d[raw:raw + rs], 0x59800000 + va):
        if ins.mnemonic != "call" or len(ins.bytes) != 5:
            continue
        t = ins.address + 5 + struct.unpack("<i", ins.bytes[1:5])[0]
        if t in (MBOX_THUNK, I_SLOT[0]) and not I_SLOT[0] <= ins.address < I_SLOT[1]:
            out.append(ins.address)        # the cave's own two calls are not sites
    return out


def check_pic(blob, va):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32, x86
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    for i in md.disasm(blob, va):
        for op in i.operands:
            if op.type == x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                sys.exit("NOT PIC: %08X %s %s" % (i.address, i.mnemonic, i.op_str))
        if i.mnemonic == "push" and i.operands and i.operands[0].type == x86.X86_OP_IMM \
                and len(i.bytes) == 2:
            sys.exit("push imm8 at %08X" % i.address)


def go(argv):
    mb = mbox_cave(I_SLOT[0])
    check_pic(mb, I_SLOT[0])
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    ins = {i.address: i for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(mb, I_SLOT[0])}
    assert ins[I_SLOT[0] + 17].mnemonic == "pop" and ins[I_SLOT[0] + 12].mnemonic == "call",         "PIC anchor is not at the pop"
    sites = int_sites()
    assert len(sites) == 36, "expected 36 MessageBoxA calls in aowInt, found %d" % len(sites)
    P.TARGET, P.IMAGE_BASE = INT, 0x59800000
    run("build_error_detail [aowInt]",
        [(s, call_to(s, MBOX_THUNK), call_to(s, I_SLOT[0])) for s in sites],
        [("mbox_detail", I_SLOT[0], mb)], I_SLOT, [], argv)
    P.TARGET, P.IMAGE_BASE = EXE, 0x00400000
    run("build_error_detail [AoWz.exe]",
        [(X_SITE, call_to(X_SITE, X_CREATE_THUNK), call_to(X_SITE, X_SLOT[0]))],
        [("fc_create", X_SLOT[0], fc_cave(X_SLOT[0]))], X_SLOT, [], argv)


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])   # both modules verify first
        print("\n" + "=" * 60)
    go(argv)
