#!/usr/bin/env python3
r"""DIAGNOSTIC INSTRUMENT -- make "Error loading <file>.hss" reveal WHERE it failed.

####################################################################################
##  DIAGNOSTIC ONLY.  REVERT BEFORE CUTTING A RELEASE:                            ##
##      python build_scripts/build_hss_exception_detail.py --undo                 ##
##  It adds a SECOND modal dialog after every failed mapset load.                 ##
####################################################################################

WHY
    `HSSEdit.THSSEdit.LoadHSSFile` (HSEPack 0x55615D78) wraps the whole mapset load
    in a bare except and reports only the filename:

        try
          THSEngine.LoadHSS(...)          @0x5560F75C
          THSSet.ResetModified
          <vmt+0x28>
          THSSEdit.Activate(...)          @0x55615FA0   <-- ALSO inside the try
        except
          ShowMessage('Error loading ' + FileName)      <-- @0x55615E0A

    The exception object is DISCARDED.  Every mapset fault -- container, resource,
    editor-grid -- looks identical, which is exactly what stalled the 1128-resource
    ceiling investigation (see 09-terrain-movement.md §7).

WHAT THIS DOES
    Retargets the 5-byte `call Dialogs.ShowMessage` at 0x55615E0A to a cave.  The cave
    shows the stock dialog unchanged, then calls SysUtils.ExceptionErrorMessage on the
    still-live exception and shows a second dialog:

        Exception EListError in module AoWzEd.exe at 0007ABCD.
        List index out of bounds (1128)

    `@DoneExcept` is not reached until 0x55615E19 -- AFTER the ShowMessage call -- which
    is what proves the exception is still live when the cave runs.

    ExceptionErrorMessage (not `E.Message`) is the point: a *raised* Delphi exception
    carries no address of its own, and E.Message alone would not say which module.
    ExceptionErrorMessage always prints module + module-relative offset.

    DECODE:  static VA = <offset> + <module preferred base>
        AoWEPACK.dpl  0x55700000      Network.dpl   0x55800000
        HSEPack.dpl   0x55600000      vcl30.dpl     0x41300000
        EngineP.dpl   0x55500000      ILPACK.dpl    0x55200000
        aowInt.dpl    0x59800000      Dcpack.dpl    0x55100000
        AoWTCPCK.dpl  0x00400000      AoWzEd.exe    0x00400000
    ⚠ AoWTCPCK.dpl really does prefer 0x00400000, the same base as the exe.
    `--bases` reprints them live from each PE header; that printout is the authority.

ADDRESSES -- Ziggurat\HSEPack.dpl, ImageBase 0x55600000
    CODE  rva=0x1000 raw=0x400 vsize=0x2C818 rsize=0x2CA00
    hook   0x55615E0A  `e8 65 bc fe ff` = call 0x55601A74  -> call CAVE
    cave   0x5561B000  0x200 bytes, verified all-zero.  The highest real CODE export is
           `HSEPack.@PackageUnload @0x5561ACD4`, so everything above ~0x5561ACEB is
           linker padding -- inside VirtualSize, therefore mapped and executable.
    .reloc carries NO entry inside either range (checked before every write).

    thunks (each verified to be `jmp [<iat slot>]` resolving to VCL30):
        0x55601A74  Dialogs.ShowMessage        (iat 0x556308CC)
        0x55601140  System.@LStrFromString     (iat 0x5563047C)
        0x55601120  System.@LStrClr            (iat 0x5563048C)
        0x556015FC  SysUtils.Exception.Create  (iat 0x55630658)  <- the RTL anchor

PIC ANCHOR -- HSEPack.dpl rebases, so the cave contains no absolute memory reference:

        call $+5 ; pop ebx ; sub ebx, <static VA of the pop>   ->  ebx = rebase delta
        mov eax,[ebx+0x55630658]                               ->  the IAT slot, relocated

    Everything else is E8 rel32 within the module or [ebp/esp]-relative.  `check_pic()`
    walks the assembled cave with capstone and rejects any mem operand with no base and
    no index register.

RTL DELTAS -- ExceptObject / ExceptAddr / ExceptionErrorMessage are NOT imported by
    HSEPack.dpl.  They are fixed deltas from the one neighbour it DOES import,
    SysUtils.Exception.Create.  Re-derived from this install's vcl30.dpl (ImageBase
    0x41300000) and re-checked by `--verify-rtl`, which refuses to write if one moved:

        SysUtils.Exception.Create        0x4130F444   <- the anchor
        SysUtils.ExceptObject            0x4130F13C   = anchor - 0x308
        SysUtils.ExceptAddr              0x4130F15C   = anchor - 0x2E8
        SysUtils.ExceptionErrorMessage   0x4130F188   = anchor - 0x2BC

    ExceptObject / ExceptAddr take no args and return in EAX; ExceptObject returns nil
    when no exception is active and the cave degrades to the stock dialog alone.
    ExceptionErrorMessage(EAX=E, EDX=Addr, ECX=Buffer, Size pushed) returns the length
    in EAX and is `ret 4` -- callee cleans, so the cave must NOT adjust esp after it.

CAVE FRAME
    0x140 bytes of locals.  [ebp-0x111] = ShortString length byte, [ebp-0x110..] = 250
    chars, [ebp-4] = a local AnsiString.  The PChar ExceptionErrorMessage fills is turned
    into a ShortString by writing min(len,250) into the byte immediately before the
    buffer, then @LStrFromString -> ShowMessage -> @LStrClr, so nothing leaks.

⚠ HAND-ASSEMBLED, NOT KEYSTONE -- a straight port of the proven
    `build_te_exception_detail.py` v2 cave.  The one place the keystone `push imm8` trap
    would bite is the `push 250` operand; it is emitted as `68 FA 00 00 00` (imm32) and
    `--dis` asserts capstone reads a 5-byte push of 0xFA, not `6A FA` = -6.

RNG: the cave makes no draw and inherits none.

Usage:
    build_hss_exception_detail.py              # verify state (dry run)
    build_hss_exception_detail.py --dis        # + disassemble the cave
    build_hss_exception_detail.py --verify-rtl # + re-derive the RTL deltas
    build_hss_exception_detail.py --bases      # print the decode table
    build_hss_exception_detail.py --apply      # write
    build_hss_exception_detail.py --undo       # surgical revert
"""
import argparse, os, shutil, struct, subprocess, sys

import capstone

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
from pescan import PE                                                  # noqa: E402
from aowsyms import get_symbols                                        # noqa: E402

FEATURE = "hssexcdetail"
TARGET_NAME = "HSEPack.dpl"
TARGET = os.path.join(GAME, TARGET_NAME)
BACKUP = os.path.join(BACKUP_DIR, TARGET_NAME + ".pre-" + FEATURE)

HOOK = 0x55615E0A                                   # call Dialogs.ShowMessage, in the handler
HOOK_LEN = 5
VANILLA_HOOK = bytes.fromhex("e865bcfeff")          # call 0x55601A74

CAVE = 0x5561B000
CAVE_ZONE = 0x200

F_SHOWMESSAGE = 0x55601A74
F_LSTRFROMSTRING = 0x55601140
F_LSTRCLR = 0x55601120

IAT_EXC_CREATE = 0x55630658                         # VCL30.dpl!SysUtils.Exception.Create
D_EXCOBJ = 0x308
D_EXCADDR = 0x2E8
D_EXCMSG = 0x2BC

BUFSZ = 0xFA                    # 250 chars -- ShortString-safe
LOCALS = 0x140
O_STR = 0x04                    # [ebp-0x004]  local AnsiString
O_LEN = 0x111                   # [ebp-0x111]  ShortString length byte
O_BUF = 0x110                   # [ebp-0x110]  chars

LOCKING = ("AoW", "AoWz", "AoWCompat", "AoWzCompat", "AoWDevEd", "AoWzEd", "AoWEd")
DECODE_MODULES = ["AoWEPACK.dpl", "HSEPack.dpl", "EngineP.dpl", "ILPACK.dpl",
                  "Network.dpl", "AoWTCPCK.dpl", "vcl30.dpl", "AoWzEd.exe", "AoWz.exe"]


# ------------------------------------------------------------------- PE helpers
class Mod:
    def __init__(self, path):
        self.pe = PE(path)
        self.base = self.pe.image_base
        self.secs = self.pe.sections

    def section_of(self, va):
        rva = va - self.base
        for s in self.secs:
            if s[1] <= rva < s[1] + max(s[2], s[4]):
                return s
        raise SystemExit(f"VA {va:#010x} is in no section")

    def off(self, va, need=1):
        s = self.section_of(va)
        d = va - self.base - s[1]
        if d + need > s[4]:
            raise SystemExit(f"VA {va:#010x}+{need} runs past {s[0]}'s raw data")
        return s[3] + d

    def read(self, va, n):
        o = self.off(va, n)
        return bytes(self.pe.data[o:o + n])

    def reloc_offsets(self):
        out = []
        rva, size = self.pe.dirs[5]
        if not size:
            return out
        p = self.pe.rva2off(rva)
        end = p + size
        while p < end:
            page, blk = struct.unpack_from("<II", self.pe.data, p)
            if blk == 0:
                break
            for i in range(p + 8, p + blk, 2):
                w = struct.unpack_from("<H", self.pe.data, i)[0]
                if (w >> 12) == 3:
                    out.append(self.base + page + (w & 0xFFF))
            p += blk
        return out


# ------------------------------------------------------------------------- cave
def build_cave(base):
    buf = bytearray()
    rel, lab, j8 = [], {}, []

    def db(*b):
        buf.extend(b)

    def dd(v):
        buf.extend((v & 0xFFFFFFFF).to_bytes(4, "little"))

    def call(t):
        db(0xE8); rel.append((len(buf), t)); dd(0)

    def label(n):
        lab[n] = len(buf)

    def jcc(op, n):
        db(op); j8.append((len(buf), n)); db(0)

    db(0x55)                                    # push ebp
    db(0x8B, 0xEC)                              # mov ebp, esp
    db(0x81, 0xC4); dd(-LOCALS)                 # add esp, -0x140
    db(0x53)                                    # push ebx
    db(0x56)                                    # push esi
    db(0x8B, 0xF0)                              # mov esi, eax     ; the stock AnsiString
    db(0x33, 0xC0)                              # xor eax, eax
    db(0x89, 0x45, 0x100 - O_STR)               # mov [ebp-4], eax ; local AnsiString := nil

    call(base + len(buf) + 5)                   # call $+5
    popva = base + len(buf)
    db(0x5B)                                    # pop ebx
    db(0x81, 0xEB); dd(popva)                   # sub ebx, <static VA of the pop>

    db(0x8B, 0xC6)                              # mov eax, esi
    call(F_SHOWMESSAGE)                         # the stock dialog, unchanged

    db(0x8B, 0x83); dd(IAT_EXC_CREATE)          # mov eax, [ebx+iat]
    db(0x2D); dd(D_EXCOBJ)                      # sub eax, 0x308      -> ExceptObject
    db(0xFF, 0xD0)                              # call eax
    db(0x85, 0xC0)                              # test eax, eax
    jcc(0x74, "done")                           # je done  ; no live exception
    db(0x50)                                    # push eax ; save E

    db(0x8B, 0x83); dd(IAT_EXC_CREATE)          # mov eax, [ebx+iat]
    db(0x2D); dd(D_EXCADDR)                     # sub eax, 0x2E8      -> ExceptAddr
    db(0xFF, 0xD0)                              # call eax
    db(0x8B, 0xD0)                              # mov edx, eax

    db(0x8B, 0xB3); dd(IAT_EXC_CREATE)          # mov esi, [ebx+iat]
    db(0x81, 0xEE); dd(D_EXCMSG)                # sub esi, 0x2BC      -> ExceptionErrorMessage
    db(0x58)                                    # pop eax  ; eax = E
    db(0x8D, 0x8D); dd(-O_BUF)                  # lea ecx, [ebp-0x110]
    db(0x68); dd(BUFSZ)                         # push 250 ; imm32! 6A would sign-extend
    db(0xFF, 0xD6)                              # call esi ; ret 4 -- callee cleans

    db(0x3D); dd(BUFSZ)                         # cmp eax, 250
    jcc(0x76, "fits")                           # jbe fits
    db(0xB8); dd(BUFSZ)                         # mov eax, 250
    label("fits")
    db(0x88, 0x85); dd(-O_LEN)                  # mov [ebp-0x111], al
    db(0x8D, 0x95); dd(-O_LEN)                  # lea edx, [ebp-0x111]
    db(0x8D, 0x45, 0x100 - O_STR)               # lea eax, [ebp-4]
    call(F_LSTRFROMSTRING)
    db(0x8B, 0x45, 0x100 - O_STR)               # mov eax, [ebp-4]
    call(F_SHOWMESSAGE)
    db(0x8D, 0x45, 0x100 - O_STR)               # lea eax, [ebp-4]
    call(F_LSTRCLR)

    label("done")
    db(0x5E)                                    # pop esi
    db(0x5B)                                    # pop ebx
    db(0x8B, 0xE5)                              # mov esp, ebp
    db(0x5D)                                    # pop ebp
    db(0xC3)                                    # ret

    for off, tgt in rel:
        buf[off:off + 4] = (tgt - (base + off + 4)).to_bytes(4, "little", signed=True)
    for off, n in j8:
        d = lab[n] - (off + 1)
        if not -128 <= d <= 127:
            raise SystemExit(f"short jump to {n} out of range: {d}")
        buf[off] = d & 0xFF
    if len(buf) > CAVE_ZONE:
        raise SystemExit(f"cave is {len(buf):#x} bytes, zone is {CAVE_ZONE:#x}")
    return bytes(buf)


def hook_bytes(cave):
    return bytes([0xE8]) + (cave - (HOOK + HOOK_LEN)).to_bytes(4, "little", signed=True)


# ------------------------------------------------------------------------ checks
def _md():
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    return md


def disasm(blob, base, title):
    print(f"  --- {title} ---")
    for i in _md().disasm(blob, base):
        print(f"    {i.address:08X}  {i.bytes.hex():<20} {i.mnemonic:<7} {i.op_str}")


def check_pic(blob, base):
    bad = []
    for i in _md().disasm(blob, base):
        for op in i.operands:
            if op.type == capstone.x86.X86_OP_MEM:
                m = op.value.mem
                if m.base == 0 and m.index == 0:
                    bad.append(f"{i.address:08X} {i.mnemonic} {i.op_str}")
    if bad:
        raise SystemExit("NOT position-independent:\n  " + "\n  ".join(bad))


def check_imm32_push(blob, base):
    for i in _md().disasm(blob, base):
        if i.mnemonic == "push" and i.operands and \
                i.operands[0].type == capstone.x86.X86_OP_IMM:
            if i.operands[0].value.imm == BUFSZ and i.size != 5:
                raise SystemExit(f"push {BUFSZ} assembled in {i.size} bytes -- imm8 trap")


def check_targets(blob, base, lo, hi):
    for i in _md().disasm(blob, base):
        if i.mnemonic in ("call", "jmp") and i.operands and \
                i.operands[0].type == capstone.x86.X86_OP_IMM:
            t = i.operands[0].value.imm
            if not (lo <= t < hi):
                raise SystemExit(f"{i.address:08X} {i.mnemonic} {t:#x} leaves the module")


def verify_rtl():
    path = next((os.path.join(GAME, n) for n in ("vcl30.dpl", "VCL30.dpl")
                 if os.path.exists(os.path.join(GAME, n))), None)
    if not path:
        raise SystemExit("vcl30.dpl not found beside the mod")
    _, _, exp, _ = get_symbols(os.path.basename(path))
    want = {"SysUtils.Exception.Create": None, "SysUtils.ExceptObject": None,
            "SysUtils.ExceptAddr": None, "SysUtils.ExceptionErrorMessage": None}
    for va, n in exp.items():
        if n in want:
            want[n] = va
    missing = [k for k, v in want.items() if v is None]
    if missing:
        raise SystemExit("vcl30.dpl is missing " + ", ".join(missing))
    anchor = want["SysUtils.Exception.Create"]
    for n, d in (("SysUtils.ExceptObject", D_EXCOBJ), ("SysUtils.ExceptAddr", D_EXCADDR),
                 ("SysUtils.ExceptionErrorMessage", D_EXCMSG)):
        got = anchor - want[n]
        flag = "OK" if got == d else "MISMATCH"
        print(f"    {n:<34} {want[n]:#010x}  delta {got:#06x} (expect {d:#06x}) {flag}")
        if got != d:
            raise SystemExit(f"RTL delta for {n} moved -- refusing to write")
    print(f"    anchor SysUtils.Exception.Create  {anchor:#010x}")


def print_bases():
    for n in DECODE_MODULES:
        p = os.path.join(GAME, n)
        if os.path.exists(p):
            print(f"    {n:<16} {PE(p).image_base:#010x}")


def kill_locking():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-Process | Where-Object { $_.ProcessName -match "
                    "'^(" + "|".join(LOCKING) + ")$' } | Stop-Process -Force"],
                   capture_output=True)


# -------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    ap.add_argument("--verify-rtl", action="store_true")
    ap.add_argument("--bases", action="store_true")
    args = ap.parse_args()

    if args.bases:
        print("  module preferred bases (add to the reported offset):")
        print_bases()
        return 0

    m = Mod(TARGET)
    blob = build_cave(CAVE)
    hook = hook_bytes(CAVE)
    sec = m.section_of(CAVE)
    lo = m.base + sec[1]
    hi = m.base + sec[1] + max(sec[2], sec[4])

    check_pic(blob, CAVE)
    check_imm32_push(blob, CAVE)
    check_targets(blob, CAVE, m.base, m.base + 0x100000)

    print(f"{TARGET_NAME}: base {m.base:#010x}")
    print(f"  cave  {CAVE:#010x}  file {m.off(CAVE, CAVE_ZONE):#08x}  "
          f"{len(blob)} of {CAVE_ZONE} bytes  section {sec[0]}")
    print(f"  hook  {HOOK:#010x}  file {m.off(HOOK, HOOK_LEN):#08x}  "
          f"{VANILLA_HOOK.hex()} -> {hook.hex()}")

    relocs = [r for r in m.reloc_offsets()
              if (HOOK - 3 <= r <= HOOK + HOOK_LEN) or (CAVE - 3 <= r < CAVE + CAVE_ZONE)]
    if relocs:
        print(f"ABORT: {len(relocs)} .reloc entr(ies) inside the hook or cave: "
              + ", ".join(f"{r:#010x}" for r in relocs))
        return 1
    print("  .reloc: no entry inside either range")

    if args.verify_rtl or args.apply:
        print("  RTL deltas:")
        verify_rtl()
    if args.dis:
        disasm(blob, CAVE, "cave")

    live_hook = m.read(HOOK, HOOK_LEN)
    live_cave = m.read(CAVE, CAVE_ZONE)
    want_cave = blob + b"\0" * (CAVE_ZONE - len(blob))
    patched = live_hook == hook and live_cave == want_cave
    vanilla = live_hook == VANILLA_HOOK and live_cave == bytes(CAVE_ZONE)

    if args.undo:
        if vanilla:
            print("already reverted (no-op)"); return 0
        if not patched:
            print(f"ABORT: unexpected live bytes -- hook {live_hook.hex()}"); return 1
        new_hook, new_cave = VANILLA_HOOK, bytes(CAVE_ZONE)
        what = "restore the vanilla call, zero the cave"
    else:
        if patched:
            print("already applied (idempotent no-op)"); return 0
        if not vanilla:
            print(f"ABORT: hook is {live_hook.hex()}, expected {VANILLA_HOOK.hex()}; "
                  f"cave zero: {live_cave == bytes(CAVE_ZONE)}")
            return 1
        new_hook, new_cave = hook, want_cave
        what = f"write the {len(blob)}-byte cave and retarget the call"

    print(f"  {what}")
    if not args.apply:
        print("dry run - re-run with --apply to write")
        return 0

    kill_locking()
    if not os.path.exists(BACKUP) and vanilla:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP)
        print(f"  backup -> {os.path.basename(BACKUP)}")

    data = bytearray(m.pe.data)
    n = len(data)
    data[m.off(HOOK, HOOK_LEN):m.off(HOOK, HOOK_LEN) + HOOK_LEN] = new_hook
    data[m.off(CAVE, CAVE_ZONE):m.off(CAVE, CAVE_ZONE) + CAVE_ZONE] = new_cave
    assert len(data) == n, "the .dpl changed length -- it must not"
    try:
        open(TARGET, "wb").write(bytes(data))
    except PermissionError:
        print("LOCKED - close every AoW binary and retry")
        return 1
    print("applied" if not args.undo else "reverted")
    if not args.undo:
        print("  *** DIAGNOSTIC -- run --undo before cutting a release ***")
    return 0


if __name__ == "__main__":
    sys.exit(main())
