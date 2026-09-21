#!/usr/bin/env python3
r"""DIAGNOSTIC INSTRUMENT -- make "Exception occured during <TE>" reveal WHERE it failed.

####################################################################################
##  DIAGNOSTIC ONLY.  REVERT BEFORE CUTTING A RELEASE:                            ##
##      python build_scripts/build_te_exception_detail.py --undo                  ##
##  It adds a SECOND modal dialog after every swallowed turn-event exception.     ##
####################################################################################

WHY
    Every turn event runs inside a try/except in
    NetworkE.TTokenExecuter.ExecuteTokenEvent @0x55803D24 (Network.dpl):

        call [TE_vmt+0x4C]              ; TArmyCombatMoveTE.Execute etc.
      except:
        ShowMessage('Exception occured during ' + TE.ClassName)

    The exception object is DISCARDED, so the player sees only the TE class name and
    the game limps on with that turn event abandoned (armies vanish, 'Combat already
    created' follows later).  Every TE fault in the game is unlocatable by design.

WHAT THIS DOES
    Retargets the 5-byte `call Dialogs.ShowMessage` at 0x55803DD2 to a cave.  The cave
    shows the stock dialog unchanged, then calls SysUtils.ExceptionErrorMessage on the
    still-live exception and shows a second dialog:

        Exception EAccessViolation in module AoWEPACK.dll at 00110C93.
        Access violation at address 01260C93 in module 'AoWEPACK.dll'. Read of ...

    ExceptionErrorMessage (not `E.Message`) is the point: a *raised* Delphi exception
    such as HSEngine's 'Index out of bounds' carries no address of its own, and
    E.Message would tell us nothing.  ExceptionErrorMessage always prints a module +
    module-relative offset, for every exception class.

    DECODE:  static VA = <offset> + <module preferred base>
        AoWEPACK.dpl  0x55700000      Network.dpl   0x55800000
        HSEPack.dpl   0x55600000      vcl30.dpl     0x41300000
        aowInt.dpl    0x59800000      Dcpack.dpl    0x55100000
        AoWTCPCK.dpl  0x00400000      AoWz.exe      0x00400000
    ⚠ AoWTCPCK.dpl really does prefer 0x00400000, the same base as the exe -- it is a
    DLL that always rebases, and it is NOT 0x55A00000.  Every base above was read from
    the PE OptionalHeader of the shipped file; `--bases` reprints them live, and that
    printout is the authority if this comment ever drifts.

ADDRESSES  -- Ziggurat\Network.dpl, ImageBase 0x55800000
    CODE  va=0x1000 raw=0x400 rs=0x5400 vs=0x5210   =>  VA = file offset + 0x55800C00
    hook   0x55803DD2  (file 0x31D2)  `e8 ed d8 ff ff` = call 0x558016C4  -> call CAVE
    cave   0x55806210  (file 0x5610)  0x1F0 bytes, verified all-zero, past VirtualSize
                                      but inside SizeOfRawData, so mapped + executable
                                      in CODE.  Ends exactly at raw 0x5800 = CODE end.
    .reloc carries NO entry inside either range (858 entries, max file off 0x581C).

    thunks used (all verified to resolve to VCL30 by walking Network.dpl's imports):
        0x558016C4  Dialogs.ShowMessage
        0x558010B8  System.@LStrFromString
        0x558010A8  System.@LStrClr
    and 0x55801088 = System.@DoneExcept sits AFTER the hook, which is what proves the
    exception is still live when the cave runs.

PIC ANCHOR -- Network.dpl rebases (its preferred base overlaps AoWEPACK), so the cave
    must contain no absolute memory reference:

        call $+5 ; pop ebx ; sub ebx, <static VA of the pop>   ->  ebx = rebase delta
        mov eax,[ebx+0x55809564]                               ->  the IAT slot, relocated

    Everything else is E8 rel32 within the module or [ebp/esp]-relative.  `check_pic()`
    walks the assembled cave with capstone and rejects any mem operand with no base and
    no index register.

RTL DELTAS -- the three routines we need are NOT imported by Network.dpl.  They are
    fixed deltas from the one neighbour it DOES import, SysUtils.Exception.Create
    (IAT slot 0x55809564, verified by parsing the import descriptors).  Re-derived from
    this install's Ziggurat\vcl30.dpl export table, ImageBase 0x41300000:

        SysUtils.Exception.Create        0x4130F444   (ord 460)  <- the anchor
        SysUtils.ExceptObject            0x4130F13C   (ord 466)  = anchor - 0x308
        SysUtils.ExceptAddr              0x4130F15C   (ord 465)  = anchor - 0x2E8
        SysUtils.ExceptionErrorMessage   0x4130F188   (ord 464)  = anchor - 0x2BC

    ExceptObject / ExceptAddr take no args and return in EAX (disassembled: both are
    `call @GetExceptionPointer / test / mov eax,[eax+8 or +4] / ret`).
    ExceptionErrorMessage(EAX=ExceptObject, EDX=ExceptAddr, ECX=Buffer, Size pushed)
    returns the length in EAX and is `ret 4` at 0x4130F308 -- callee cleans, so the
    cave must NOT adjust esp after the call.  `--verify-rtl` re-checks all of this
    against vcl30.dpl and refuses to write if a delta moved.

    ExceptObject returns nil when no exception is active; the cave tests for that and
    degrades to the stock dialog alone.

CAVE FRAME
    0x140 bytes of locals.  [ebp-0x111] = ShortString length byte, [ebp-0x110..] = 250
    chars (ends at ebp-0x16), [ebp-4] = a local AnsiString.  The PChar that
    ExceptionErrorMessage fills is turned into a ShortString by writing min(len,250)
    into the byte immediately before the buffer, then @LStrFromString -> ShowMessage ->
    @LStrClr, so nothing leaks.

HAND-ASSEMBLED, NOT KEYSTONE -- deliberate.  The byte sequence is a straight port of a
    proven v2 patch; re-assembling it would add risk for no gain, and the one place the
    keystone `push imm8` trap would bite is exactly the `push 250` operand.  It is
    emitted as `68 FA 00 00 00` (imm32) and `--dis` asserts capstone reads a 5-byte
    push of 0xFA, not `6A FA` = -6.  Read the `--dis` output; do not trust the table.

RNG: the cave makes no draw and inherits none -- ShowMessage / ExceptionErrorMessage /
    @LStrFromString / @LStrClr are in neither the SYNC nor the RAW list.  Nothing to pick.

--undo IS SURGICAL: it restores the 5 vanilla bytes at 0x55803DD2 and zeroes the 0x1F0
    cave, verifying both before writing.  It touches no backup and does not restore a
    whole file.  A snapshot is minted on --apply ONLY, and only when the file is proved
    unpatched against the vanilla root copy of Network.dpl.

Usage:
    python build_scripts/build_te_exception_detail.py              # verify state (dry run)
    python build_scripts/build_te_exception_detail.py --dis        # + disassemble the cave
    python build_scripts/build_te_exception_detail.py --verify-rtl # + re-derive RTL deltas
    python build_scripts/build_te_exception_detail.py --bases      # print the decode table
    python build_scripts/build_te_exception_detail.py --apply      # write
    python build_scripts/build_te_exception_detail.py --undo       # surgical revert
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys

import capstone

# game dir = two levels up from this script (<game>/Ziggurat/Modding Resources/build_scripts/),
# which must land on <game>/Ziggurat -- NOT the vanilla game root.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

FEATURE = "texcdetail"
TARGET_NAME = "Network.dpl"

# ---- addresses (Network.dpl, ImageBase 0x55800000) -------------------------------
HOOK = 0x55803DD2                                   # call Dialogs.ShowMessage, in the handler
HOOK_LEN = 5
VANILLA_HOOK = bytes.fromhex("e8edd8ffff")          # call 0x558016C4

CAVE = 0x55806210
CAVE_ZONE = 0x1F0                                   # 0x55806210 .. 0x558063FF inclusive

F_SHOWMESSAGE = 0x558016C4
F_LSTRFROMSTRING = 0x558010B8
F_LSTRCLR = 0x558010A8

IAT_EXC_CREATE = 0x55809564                         # VCL30.dpl!SysUtils.Exception.Create
D_EXCOBJ = 0x308                                    # Exception.Create - ExceptObject
D_EXCADDR = 0x2E8                                   # Exception.Create - ExceptAddr
D_EXCMSG = 0x2BC                                    # Exception.Create - ExceptionErrorMessage

# expected VCL30 export VAs, re-checked by --verify-rtl
VCL30_BASE = 0x41300000
VCL30_EXPECT = {
    "SysUtils.Exception.Create": 0x4130F444,
    "SysUtils.ExceptObject": 0x4130F13C,
    "SysUtils.ExceptAddr": 0x4130F15C,
    "SysUtils.ExceptionErrorMessage": 0x4130F188,
}

# ---- cave frame ------------------------------------------------------------------
BUFSZ = 0xFA                    # 250 chars -- ShortString-safe
LOCALS = 0x140
O_STR = 0x04                    # [ebp-0x004]  local AnsiString
O_LEN = 0x111                   # [ebp-0x111]  ShortString length byte
O_BUF = 0x110                   # [ebp-0x110]  chars (250 -> ends at ebp-0x16)

LOCKING = ("AoW", "AoWz", "AoWCompat", "AoWzCompat",
           "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup")

# module preferred bases for the decode recipe; read live from the PE headers
DECODE_MODULES = ["AoWEPACK.dpl", "Network.dpl", "HSEPack.dpl", "AoWTCPCK.dpl",
                  "aowInt.dpl", "vcl30.dpl", "Dcpack.dpl", "AoWz.exe"]


# ---------------------------------------------------------------------------------
# minimal PE helper -- VA -> file offset is PER SECTION, never a flat delta
# ---------------------------------------------------------------------------------
class PEFile:
    def __init__(self, path):
        self.path = path
        self.data = bytearray(open(path, "rb").read())
        d = self.data
        e = struct.unpack_from("<I", d, 0x3C)[0]
        opt = e + 24
        self.opt = opt
        self.image_base = struct.unpack_from("<I", d, opt + 28)[0]
        nsec = struct.unpack_from("<H", d, e + 6)[0]
        osz = struct.unpack_from("<H", d, e + 20)[0]
        self.sections = []
        p = opt + osz
        for _ in range(nsec):
            name = d[p:p + 8].rstrip(b"\0").decode("latin1")
            vs, va, rs, raw = struct.unpack_from("<IIII", d, p + 8)
            self.sections.append((name, va, vs, raw, rs))
            p += 40

    def section_of(self, va):
        rva = va - self.image_base
        for s in self.sections:
            _, sva, vs, raw, rs = s
            if sva <= rva < sva + max(vs, rs):
                return s
        return None

    def off(self, va, length=1):
        s = self.section_of(va)
        if s is None:
            raise SystemExit(f"VA {va:#x} is in no section of {self.path}")
        name, sva, vs, raw, rs = s
        o = raw + (va - self.image_base) - sva
        if o + length > raw + rs:
            raise SystemExit(f"VA {va:#x}+{length:#x} runs past SizeOfRawData of "
                             f"section {name} -- not mapped from file")
        return o

    def read(self, va, n):
        o = self.off(va, n)
        return bytes(self.data[o:o + n])

    def write(self, va, b):
        o = self.off(va, len(b))
        self.data[o:o + len(b)] = b

    def save(self):
        with open(self.path, "wb") as f:
            f.write(self.data)

    def rva_to_off(self, rva):
        for _, sva, vs, raw, rs in self.sections:
            if sva <= rva < sva + max(vs, rs):
                return raw + rva - sva
        return None

    def reloc_offsets(self):
        """file offsets of every base-relocation target"""
        rrva, rsz = struct.unpack_from("<II", self.data, self.opt + 96 + 5 * 8)
        out = []
        if not rsz:
            return out
        off = self.rva_to_off(rrva)
        if off is None:
            return out
        end = off + rsz
        while off < end:
            page, blk = struct.unpack_from("<II", self.data, off)
            if blk < 8:
                break
            for i in range((blk - 8) // 2):
                w = struct.unpack_from("<H", self.data, off + 8 + 2 * i)[0]
                if w >> 12 == 0:
                    continue
                fo = self.rva_to_off(page + (w & 0xFFF))
                if fo is not None:
                    out.append(fo)
            off += blk
        return out


# ---------------------------------------------------------------------------------
# the cave
# ---------------------------------------------------------------------------------
def build_cave(base):
    buf = bytearray()
    rel = []        # (offset of rel32 field, absolute target VA)
    lab = {}
    j8 = []

    def db(*b):
        buf.extend(b)

    def dd(v):
        buf.extend((v & 0xFFFFFFFF).to_bytes(4, "little"))

    def call(t):
        db(0xE8)
        rel.append((len(buf), t))
        dd(0)

    def label(n):
        lab[n] = len(buf)

    def jcc(op, n):
        db(op)
        j8.append((len(buf), n))
        db(0)

    # --- prologue -----------------------------------------------------------------
    db(0x55)                                    # push ebp
    db(0x8B, 0xEC)                              # mov ebp, esp
    db(0x81, 0xC4); dd(-LOCALS)                 # add esp, -0x140
    db(0x53)                                    # push ebx
    db(0x56)                                    # push esi
    db(0x8B, 0xF0)                              # mov esi, eax     ; the finished AnsiString
    db(0x33, 0xC0)                              # xor eax, eax
    db(0x89, 0x45, 0x100 - O_STR)               # mov [ebp-4], eax ; local AnsiString := nil

    # --- PIC anchor: ebx = runtime base - preferred base ---------------------------
    call(base + len(buf) + 5)                   # call $+5
    popva = base + len(buf)
    db(0x5B)                                    # pop ebx
    db(0x81, 0xEB); dd(popva)                   # sub ebx, <static VA of the pop>

    # --- 1) the stock dialog, unchanged --------------------------------------------
    db(0x8B, 0xC6)                              # mov eax, esi
    call(F_SHOWMESSAGE)

    # --- 2) E := SysUtils.ExceptObject ---------------------------------------------
    db(0x8B, 0x83); dd(IAT_EXC_CREATE)          # mov eax, [ebx+0x55809564]
    db(0x2D); dd(D_EXCOBJ)                      # sub eax, 0x308
    db(0xFF, 0xD0)                              # call eax
    db(0x85, 0xC0)                              # test eax, eax
    jcc(0x74, "done")                           # je done      ; no live exception
    db(0x50)                                    # push eax     ; save E

    # --- 3) addr := SysUtils.ExceptAddr --------------------------------------------
    db(0x8B, 0x83); dd(IAT_EXC_CREATE)          # mov eax, [ebx+0x55809564]
    db(0x2D); dd(D_EXCADDR)                     # sub eax, 0x2E8
    db(0xFF, 0xD0)                              # call eax
    db(0x8B, 0xD0)                              # mov edx, eax

    # --- 4) len := ExceptionErrorMessage(E, addr, @buf, 250) -----------------------
    db(0x8B, 0xB3); dd(IAT_EXC_CREATE)          # mov esi, [ebx+0x55809564]
    db(0x81, 0xEE); dd(D_EXCMSG)                # sub esi, 0x2BC
    db(0x58)                                    # pop eax      ; eax = E
    db(0x8D, 0x8D); dd(-O_BUF)                  # lea ecx, [ebp-0x110]
    db(0x68); dd(BUFSZ)                         # push 250     ; imm32! 6A would sign-extend
    db(0xFF, 0xD6)                              # call esi     ; ret 4 -- callee cleans

    # --- 5) PChar -> ShortString -> AnsiString -> ShowMessage ----------------------
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

    # --- epilogue -------------------------------------------------------------------
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


# ---------------------------------------------------------------------------------
# capstone review + the checks that catch the silent failures
# ---------------------------------------------------------------------------------
def _md():
    m = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    m.detail = True
    return m


def disasm(blob, base, title):
    print(f"\n  --- {title}  ({len(blob)} bytes) ---")
    for i in _md().disasm(blob, base):
        print(f"    {i.address:08X}  {i.bytes.hex():<20} {i.mnemonic:<7} {i.op_str}")


def check_pic(blob, base):
    """Reject any absolute memory reference -- Network.dpl never loads at its base."""
    bad = []
    for i in _md().disasm(blob, base):
        for op in i.operands:
            if op.type == capstone.x86.X86_OP_MEM:
                if op.mem.base == 0 and op.mem.index == 0:
                    bad.append(f"{i.address:08X}  {i.mnemonic} {i.op_str}")
    if bad:
        raise SystemExit("NOT POSITION-INDEPENDENT:\n    " + "\n    ".join(bad))


def check_imm32_push(blob, base):
    """The standing keystone/hand-assembly trap: `push 250` must not be `6A FA` = -6."""
    for i in _md().disasm(blob, base):
        if i.mnemonic == "push" and i.operands and i.operands[0].type == capstone.x86.X86_OP_IMM:
            v = i.operands[0].imm
            if len(i.bytes) != 5 or v != BUFSZ:
                raise SystemExit(f"push imm trap at {i.address:#x}: {i.bytes.hex()} "
                                 f"= push {v} ({len(i.bytes)} bytes); wanted 5-byte push {BUFSZ}")
            return
    raise SystemExit("no `push imm` found in the cave -- the buffer size never got pushed")


def check_targets(blob, base, lo, hi):
    """every rel32 call must land inside the module image"""
    for i in _md().disasm(blob, base):
        if i.mnemonic in ("call", "jmp") and i.operands \
           and i.operands[0].type == capstone.x86.X86_OP_IMM:
            t = i.operands[0].imm
            if not lo <= t < hi:
                raise SystemExit(f"rel32 target {t:#x} at {i.address:#x} leaves the module")


# ---------------------------------------------------------------------------------
def verify_rtl():
    """Re-derive the three RTL deltas from THIS install's vcl30.dpl. Never trust the table."""
    path = None
    for cand in (os.path.join(GAME, "vcl30.dpl"), os.path.join(GAME, "VCL30.dpl")):
        if os.path.isfile(cand):
            path = cand
            break
    if path is None:
        print("  !! vcl30.dpl not found beside the target -- RTL deltas NOT re-verified")
        return False
    pe = PEFile(path)
    d = pe.data
    erva, _ = struct.unpack_from("<II", d, pe.opt + 96)
    eo = pe.rva_to_off(erva)
    obase = struct.unpack_from("<I", d, eo + 16)[0]
    nnam = struct.unpack_from("<I", d, eo + 24)[0]
    afun, anam, aord = struct.unpack_from("<III", d, eo + 28)
    fo, no, oo = pe.rva_to_off(afun), pe.rva_to_off(anam), pe.rva_to_off(aord)
    found = {}
    for i in range(nnam):
        nr = struct.unpack_from("<I", d, no + 4 * i)[0]
        o = pe.rva_to_off(nr)
        nm = d[o:d.index(b"\0", o)].decode("latin1")
        stem = nm.split("@")[0]
        if stem in VCL30_EXPECT:
            ordi = struct.unpack_from("<H", d, oo + 2 * i)[0]
            va = pe.image_base + struct.unpack_from("<I", d, fo + 4 * ordi)[0]
            found[stem] = (va, ordi + obase)
    ok = True
    print(f"  RTL re-derived from {os.path.basename(path)} (ImageBase {pe.image_base:#x}):")
    if pe.image_base != VCL30_BASE:
        print(f"    !! ImageBase {pe.image_base:#x} != documented {VCL30_BASE:#x}")
        ok = False
    for stem, want in VCL30_EXPECT.items():
        got = found.get(stem)
        if got is None:
            print(f"    !! {stem}: NOT EXPORTED")
            ok = False
            continue
        mark = "ok " if got[0] == want else "!! "
        if got[0] != want:
            ok = False
        print(f"    {mark}{stem:<32} {got[0]:#010x} (ord {got[1]})")
    anchor = found.get("SysUtils.Exception.Create", (None,))[0]
    if anchor:
        for stem, const, nm in (("SysUtils.ExceptObject", D_EXCOBJ, "D_EXCOBJ"),
                                ("SysUtils.ExceptAddr", D_EXCADDR, "D_EXCADDR"),
                                ("SysUtils.ExceptionErrorMessage", D_EXCMSG, "D_EXCMSG")):
            got = found.get(stem)
            if not got:
                continue
            delta = anchor - got[0]
            mark = "ok " if delta == const else "!! "
            if delta != const:
                ok = False
            print(f"    {mark}{nm:<12} = {delta:#x}   (script constant {const:#x})")
    print("  RTL deltas:", "VERIFIED" if ok else "*** MISMATCH -- DO NOT APPLY ***")
    return ok


def print_bases():
    print("\n  --- decode recipe:  static VA = <offset in dialog> + base ---")
    for nm in DECODE_MODULES:
        p = os.path.join(GAME, nm)
        if not os.path.isfile(p):
            print(f"    {nm:<14} (not present)")
            continue
        try:
            print(f"    {nm:<14} {PEFile(p).image_base:#010x}")
        except Exception as exc:                                # noqa: BLE001
            print(f"    {nm:<14} ?? {exc}")
    print("    the dialog names the module, so pick its row and add.")


def kill_game():
    names = "|".join(LOCKING)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         f"Get-Process | Where-Object {{ $_.ProcessName -match '^({names})$' }} | Stop-Process -Force"],
        capture_output=True)


# ---------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the patch")
    ap.add_argument("--undo", action="store_true",
                    help="surgical revert (restore the 5 hook bytes, zero the cave)")
    ap.add_argument("--dis", "--show", dest="dis", action="store_true",
                    help="disassemble the cave and the hook site")
    ap.add_argument("--verify-rtl", action="store_true",
                    help="re-derive the RTL deltas from vcl30.dpl")
    ap.add_argument("--bases", action="store_true", help="print the decode base table")
    args = ap.parse_args()

    if args.apply and args.undo:
        raise SystemExit("--apply and --undo are mutually exclusive")

    # GAME must be <game>/Ziggurat, never the vanilla root.
    if not os.path.isdir(os.path.join(GAME, "Release")):
        raise SystemExit(f"GAME resolved to {GAME!r}, which has no Release\\ -- refusing to run.\n"
                         "This script lives in Ziggurat\\Modding Resources\\build_scripts\\ and must "
                         "resolve two levels up to <game>\\Ziggurat. Is AOW_GAME_DIR set?")
    if os.path.isfile(os.path.join(GAME, "goggame-1207658883.hashdb")):
        raise SystemExit(f"GAME resolved to {GAME!r}, which carries the GOG hashdb -- that is the "
                         "VANILLA root. Refusing to patch it.")

    path = os.path.join(GAME, TARGET_NAME)
    if not os.path.isfile(path):
        raise SystemExit(f"missing {path}")
    pristine = os.path.join(GAME, "..", TARGET_NAME)            # the vanilla root copy

    blob = build_cave(CAVE)
    hook = hook_bytes(CAVE)

    pe = PEFile(path)
    sec = pe.section_of(CAVE)
    lo, hi = pe.image_base, pe.image_base + 0x20000
    check_pic(blob, CAVE)
    check_imm32_push(blob, CAVE)
    check_targets(blob, CAVE, lo, hi)

    print(f"=== {TARGET_NAME}  (ImageBase {pe.image_base:#x})  {path}")
    print(f"  cave  {CAVE:#010x}  file {pe.off(CAVE, CAVE_ZONE):#06x}  "
          f"{len(blob)} of {CAVE_ZONE} bytes  section {sec[0]}")
    print(f"  hook  {HOOK:#010x}  file {pe.off(HOOK, HOOK_LEN):#06x}  "
          f"{VANILLA_HOOK.hex()} -> {hook.hex()}")

    # --- .reloc must not cross either range ---------------------------------------
    h_off, c_off = pe.off(HOOK, HOOK_LEN), pe.off(CAVE, CAVE_ZONE)
    hits = [x for x in pe.reloc_offsets()
            if (h_off <= x + 3 and x < h_off + HOOK_LEN)
            or (c_off <= x + 3 and x < c_off + CAVE_ZONE)]
    if hits:
        raise SystemExit("reloc entries inside the patch ranges: "
                         + ", ".join(hex(x) for x in hits))
    print("  reloc: clean over both ranges")

    rtl_ok = True
    if args.verify_rtl or args.apply:
        rtl_ok = verify_rtl()

    # --- current state -------------------------------------------------------------
    live_hook = pe.read(HOOK, HOOK_LEN)
    live_cave = pe.read(CAVE, CAVE_ZONE)
    want_cave = blob + b"\0" * (CAVE_ZONE - len(blob))

    if live_hook == VANILLA_HOOK and live_cave == b"\0" * CAVE_ZONE:
        state = "vanilla"
    elif live_hook == hook and live_cave == want_cave:
        state = "applied"
    elif live_hook == hook:
        state = "applied-stale"
    else:
        raise SystemExit(f"UNRECOGNISED STATE at {HOOK:#x}: {live_hook.hex()} "
                         f"(vanilla {VANILLA_HOOK.hex()}, ours {hook.hex()}) -- "
                         "someone else's patch? aborting, nothing written.")
    print(f"  state: {state}")

    if args.dis:
        disasm(blob, CAVE, f"cave @{CAVE:#010x}")
        print(f"\n  --- hook site as it reads after --apply ---")
        disasm(hook, HOOK, f"hook @{HOOK:#010x}")
    if args.bases:
        print_bases()

    # --- undo ----------------------------------------------------------------------
    if args.undo:
        if state == "vanilla":
            print("  already vanilla -- nothing to undo.")
            return
        kill_game()
        pe = PEFile(path)                       # re-read after the kill
        if pe.read(HOOK, HOOK_LEN) != hook:
            raise SystemExit("verify-before-write failed: hook no longer ours")
        pe.write(HOOK, VANILLA_HOOK)
        pe.write(CAVE, b"\0" * CAVE_ZONE)
        pe.save()
        print("  UNDONE -- hook restored, cave zeroed. No backup touched.")
        return

    # --- dry run -------------------------------------------------------------------
    if not args.apply:
        print("\n  DIAGNOSTIC ONLY -- revert with --undo before cutting a release.")
        print("  DRY RUN -- nothing written. Re-run with --apply.")
        return

    if not rtl_ok:
        raise SystemExit("RTL delta verification failed -- refusing to write.")

    kill_game()
    pe = PEFile(path)                           # re-read after the kill

    # --- backup: minted on --apply ONLY, and only from a PROVEN-unpatched file ------
    if state == "vanilla":
        fresh = (pe.read(HOOK, HOOK_LEN) == VANILLA_HOOK
                 and pe.read(CAVE, CAVE_ZONE) == b"\0" * CAVE_ZONE)
        if os.path.isfile(pristine):
            ref = PEFile(pristine)
            fresh = (fresh
                     and ref.read(HOOK, HOOK_LEN) == VANILLA_HOOK
                     and ref.read(CAVE, CAVE_ZONE) == b"\0" * CAVE_ZONE)
        else:
            print(f"  note: vanilla reference missing ({pristine}) -- freshness proved "
                  "from the vanilla byte pattern alone")
        if fresh:
            backup_dir = os.path.join(GAME, "backups")
            os.makedirs(backup_dir, exist_ok=True)
            backup = os.path.join(backup_dir, f"{TARGET_NAME}.pre-{FEATURE}")
            if not os.path.exists(backup):
                shutil.copy2(path, backup)
                print(f"  backup -> backups\\{os.path.basename(backup)}")
            else:
                print(f"  backup already present: backups\\{os.path.basename(backup)}")
        else:
            print("  no backup minted -- this file is not provably unpatched at the hook site")
    else:
        print("  re-tune over an existing install -- rewriting the cave in place, no backup minted")
        tail = pe.read(CAVE + len(blob), CAVE_ZONE - len(blob))
        if set(tail) - {0}:
            raise SystemExit("the zone the cave grows into is NOT zero -- aborting")

    if pe.read(HOOK, HOOK_LEN) not in (VANILLA_HOOK, hook):
        raise SystemExit("verify-before-write failed at the hook site")

    pe.write(CAVE, want_cave)
    pe.write(HOOK, hook)
    pe.save()
    print("  APPLIED (diagnostic, untested)")
    print("\n  Second dialog now reads:")
    print("    Exception <class> in module <module> at <offset>. <message>")
    print_bases()
    print("\n  DIAGNOSTIC ONLY -- run --undo before cutting a release.")


if __name__ == "__main__":
    sys.exit(main())
