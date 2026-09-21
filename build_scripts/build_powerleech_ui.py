#!/usr/bin/env python3
r"""
AoW1 POWER LEECH -- the income row.  `Ziggurat\AoWz.exe` + `AoWzCompat.exe` (names from
`zigexe.py`), 7 host bytes + one cave.  ⚠ The exe is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from
`Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step;
that script is retired.)

DISPLAY ONLY. The mechanic is `build_powerleech.py` (AoWEPACK.dpl: a call-retarget at
0x5577CEC5 into cave_powerleech @0x55848000, plus the halving byte killed at 0x5577CED8).
NOTHING in AoWEPACK.dpl is touched here, and nothing here knows what a magic node is.

WHAT IT SHOWS
-------------
The Magic window's tab 4 is the power breakdown: a scrolling name column
(`TMagicWin.PowerSourceList`, [form+0x110]) beside a value column (`PowerValueList`,
[form+0x108]), one row per power source, filled by the loop at 0x0042CDE8. This adds ONE row
at the end of both columns:

    caster of the leech   "Power Leech (gained)"    +N
    a victim of it        "Power Leech (lost)"      -N
    neither               (no row at all)

A player is either the caster or a victim, never both -- cave_powerleech skips the caster's own
nodes -- so one row with a side-dependent label and sign covers every case.

`Power Base` ([form+0xE8]) still shows the RAW, un-leeched total. That is vanilla behaviour and
was deliberately left alone; this row is what makes the leech visible.

HOW THE NUMBER IS OBTAINED -- no knowledge of the mechanic, and no new import
----------------------------------------------------------------------------
    delta = TPlayerMagicControl.GetNetPower(pmc) - TPlayerMagicControl.GetPower(pmc)

With the vanilla halving dead (`test byte ptr [edx+0x10], 8` -> `, 0`, so the `je` at
0x5577CED9 is always taken), GetNetPower is exactly `cave_powerleech`, i.e. GetPower plus the
leech and nothing else -- verified by disassembling the live GetNetPower @0x5577CEC4:

    5577CEC4  call 0x55848000              <- cave_powerleech (build_powerleech.py)
    5577CEC9  mov edx,[0x558FA040]
    5577CECF  mov edx,[edx+0x188]
    5577CED5  test byte ptr [edx+0x10], 0  <- the halving is dead
    5577CED9  je 0x5577CEE3
    5577CEE3  ret

so the difference IS the leech: positive for the caster, negative for a victim, zero otherwise.
AoWz.exe already imports both (IAT 0x0045DD4C GetNetPower / 0x0045DD50 GetPower, thunks
0x0040262C / 0x00402624, 1 ref each), so the import table is untouched.

⚠ FORWARD HAZARD: this script's row appears if and only if GetNetPower != GetPower. If the
vanilla halving is ever restored (build_powerleech.py --undo), a player who is not the caster
gets a "Power Leech (lost)" row for the halving instead -- but only in a game where the halving
option bit is set, since the restored test is `test byte ptr [gmc+0x10], 8` and the halve runs
only when that bit is on. Undo this script alongside it.

THE HOST WRITE -- 0x0042CFD9, 7 bytes
-------------------------------------
      vanilla  8B C3              mov eax, ebx                 (ebx = the TPlayerMagicControl)
               E8 44 56 FD FF     call 0x00402624              (GetPower thunk)
      patched  E8 <rel32>         call cave_powerleech_ui
               90 90              padding

The site sits immediately after the value-column loop terminator at 0x0042CFD7, so both lists
are fully populated when the cave runs and the new row lands last. `mov eax,ebx / call GetPower`
is not re-emitted: the cave calls GetPower itself for the delta and returns that same raw value
in EAX, which is what 0x0042CFE0 (`lea edx,[ebp-0xC] ; call IntToStr`) consumes for Power Base.

  - Entered by `call`, not `jmp`, so EBP is still the host's frame pointer inside the cave:
    [ebp-4] = the TMagicWin, [ebp-0xC] = the same managed AnsiString temp the fill loop reuses
    (zeroed by the prologue at 0x0042CDEB, released by @LStrArrayClr at 0x0042D27B).
  - 0x0042CFD9 IS a branch target -- 0x0042CF4F `jl 0x42CFD9` skips the loop when the player has
    no power sources -- and it is the FIRST byte of the displaced run, so the jump still lands on
    the `E8`. The script scans every rel8/rel32 branch in CODE and aborts if any lands strictly
    inside 0x0042CFDA..0x0042CFDF.
  - .reloc: zero entries in 0x0042CF00..0x0042D100 below 0x0042D00C (which is the operand of
    `push 0x42D298`, well past our window). AoWz.exe is NOT relocs-stripped (11909 entries), so
    the script re-derives this from the file rather than trusting the note.

THE CAVE -- 0x0062D100, span 0x200, in `.hcol`
----------------------------------------------
`.hcol` is VA 0x00612000, VirtualSize 0x1C000, characteristics 0xE0000060 (CODE|EXEC|READ|WRITE),
raw 0x20C200. It is `build_herodlg_columns.py`'s section; its current occupants are
build_herodlg_columns (0x612000 upward, top 0x0062417B), build_skylevel_ui (0x0062A000..0x62A3FF),
build_unitwin_ability (0x0062D000, 0x40) and build_savedate_format (0x0062D020, 0x80, last
non-zero byte 0x0062D07A). 0x0062D0A0..0x0062DFFF is verified all-zero, so 0x0062D100 is the next
clear 0x100-aligned slot above the highest existing occupant. Chosen for that reason: no new PE
section (only ONE free section-header slot remains in AoWz.exe, 0x3D8..0x400, and a display row is
not what to spend it on), and no collision with `.syd`, which build_shipyard_income_display.py
rewrites wholesale.

⚠ FORWARD HAZARD: build_herodlg_columns.py grows its `.hcol` code upward from 0x612000 with only
a `< 0x62E000` bound. It would overwrite this cave -- and build_skylevel_ui's, and the two other
0x0062Dxxx caves -- without noticing.

Layout (all offsets printed by --dis, all re-derived from the assembled bytes at build time):

    +0x000  LIT_GAIN   Delphi 3 literal AnsiString  FF FF FF FF | 14 00 00 00 | "Power Leech (gained)" 00
    +0x020  LIT_LOSS   Delphi 3 literal AnsiString  FF FF FF FF | 12 00 00 00 | "Power Leech (lost)" 00
    +0x040  RET_STUB   31 C0 C3  = xor eax,eax ; ret
    +0x044  FAKE_VMT   24 dwords (+0x00..+0x5C), every slot = RET_STUB
    +0x0A4  FAKE_OBJ   one dword = FAKE_VMT
    +0x0A8  code

THE LABEL TEXT -- why a literal, not a resourcestring
-----------------------------------------------------
Every existing row's name comes from the power source's own `Name` virtual ([srcvmt+0x4C]),
which returns an AnsiString; the surrounding labels come from Delphi resourcestrings via
TranslateRStr. Minting a new resourcestring means growing `.rsrc` -- not worth it for one row.

Instead the cave carries two compiler-shaped literal AnsiStrings. The representation was read
out of this very function rather than assumed: at 0x0042D00B the compiler does `push 0x42D298`,
and 0x0042D290 holds `FF FF FF FF | 01 00 00 00 | 2D 00 00 00` -- refCnt -1, length 1, then "-".
So StrRec skew is 8: [-8] refCnt, [-4] length, [0] chars, and the pointer handed around is the
address of the chars. refCnt -1 marks it a literal, which is what makes it safe to hand to VCL:
Delphi's _LStrAsg copies a negative-refcount string instead of incrementing it, so nothing ever
tries to free or realloc a string that lives in our section.

THE AddObject / Add ABI -- copied from the loop, not invented
-------------------------------------------------------------
Mirrored verbatim from 0x0042CF7D..0x0042CFD0:

    name column   EAX = [[form+0x110]+0x114]   the TStrings behind the TAOWListBox
                  EDX = the AnsiString
                  ECX = the associated TObject
                  call [[EAX]+0x38]            TStrings.AddObject
    value column  EAX = [[form+0x108]+0x114]
                  EDX = the AnsiString
                  call [[EAX]+0x34]            TStrings.Add
    IntToStr      EAX = value, EDX = @result   thunk 0x004013AC -> VCL30 SysUtils.IntToStr

⚠⚠ THE ASSOCIATED OBJECT CANNOT BE NIL -- this is a real crash, not a nicety.
`TMagicWin.PowerSourceListDoubleClick @0x0042D944` and `TMagicWin.PowerValueListMouseDown
@0x0042D988` (right button; it reads the NAME list's ItemIndex) both do

    call [[strings]+0x18]     TStrings.GetObject(ItemIndex)
    mov  edx, [eax]           <-- unconditional, NOT nil-checked
    call [edx+0x5C]           TPlayerStructurePowerSource.Select     (double-click)
    call [edx+0x58]           TPowerSource.CenterToLocation          (right-click)

Both are index-bounds-checked and neither is nil-checked, so a row added with a nil object
faults the moment the player selects it and double-clicks or right-clicks. The value column is
safe (every one of its rows already has a nil object) because nothing reads Objects[] from it,
and TAOWListBox's drawing never touches Objects -- which is why plain `Add` is correct there.

So the name row is added with a 4-byte FAKE_OBJ pointing at a 24-slot FAKE_VMT whose every entry
is `xor eax,eax ; ret`. Double-clicking or right-clicking the Power Leech row does nothing, which
is the right behaviour -- it is not a map object. Slot count 24 (+0x00..+0x5C) is the full VMT of
TPlayerStructurePowerSource, read from 0x55714250 (its class-name string begins at +0x60).
Negative VMT slots are left zero: nothing constructs, destroys or class-queries these objects --
TStrings.Clear does not free them, which is why the live power sources can be listed at all.

REGISTERS
---------
ebx (the pmc), esi and edi are pushed and popped; ebp is never touched; eax/ecx/edx are dead at
0x0042CFE0 apart from EAX, which the cave supplies. `raw` is parked in EDI across the two VCL
calls -- callee-saved under Delphi's register convention, and the host's own fill loop already
relies on that for ebx/esi across the same calls.

GUARDS (all run at import, before anything can be written)
----------------------------------------------------------
  G1  the two literals round-trip: refCnt -1, correct length, NUL-terminated, chars readable.
  G2  every absolute operand in the assembled cave is one of LIT_GAIN / LIT_LOSS / FAKE_OBJ.
  G3  every direct call leaves the cave only to GETPOWER / GETNETPOWER / INTTOSTR.
  G4  the keystone `push imm8` trap: no operand renders as -1 anywhere in the cave.
  G5  one `ret` in the code block, and push/pop are balanced 3/3 plus the edi spill pair.
  G6  every FAKE_VMT slot resolves to RET_STUB, and RET_STUB disassembles to xor eax,eax ; ret.

AoWzCompat.exe LOCKSTEP
----------------------
AoWzCompat.exe is AoWz.exe with exactly one byte changed -- file offset 0x3BB7C, 0x0F vs 0x05 (the
build number). Both exes are patched here in one pass with the identical byte writes at the
identical VAs; the script re-checks after writing that `AoWz.exe` and `AoWzCompat.exe` still differ
in exactly that one byte and aborts loudly if not.

RE-TUNING -- an in-place cave rewrite, never revert-and-reapply
--------------------------------------------------------------
Change a label or the cave code and just re-run `--apply`. The positive test is the host hook: if
0x0042CFD9 holds `E8 rel32` + NOP padding whose target lands anywhere inside our reservation, the
reservation's contents are ours by construction and are overwritten wholesale. The blob is always
written at the full CAVE_SPAN, so any zone a longer cave grows into is covered, and 0x0062D0A0..
0x0062D100 and 0x0062D300..0x0062E000 are still asserted zero either side of it. A re-tune mints
NO backup: `pristine` counts only bytes proved to be PRE-FEATURE, never our own past output.

UNDO
----
`--undo --apply` is surgical and touches no backup: 0x0042CFD9 goes back to
`8B C3 E8 44 56 FD FF` and 0x0062D100..0x0062D2FF is zeroed, in both exes. Round-trips to
byte-identical files.

Backups (`backups\AoWz.exe.pre-powerleechui`, `backups\AoWzCompat.exe.pre-powerleechui`) are minted
ONLY from a file proved to be in the pre-feature state -- the host bytes still vanilla AND our
zone still zero -- never on --undo, never on a re-apply over our own output, and never merely
because the backup file is missing.

Usage:
  python build_scripts/build_powerleech_ui.py                  dry run + verify current state
  python build_scripts/build_powerleech_ui.py --apply          patch both exes
  python build_scripts/build_powerleech_ui.py --undo --apply   surgical revert
  python build_scripts/build_powerleech_ui.py --dis            disassemble the cave and stop
"""
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys

from capstone import CS_ARCH_X86, CS_MODE_32, Cs
from keystone import KS_ARCH_X86, KS_MODE_32, Ks

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                   # mod binary names (AoWz.exe / AoWzCompat.exe)
EXES = zigexe.EXES
BACKUP_DIR = os.path.join(GAME, "backups")
SUFFIX = ".pre-powerleechui"
IMAGE_BASE = 0x00400000

# AoWzCompat.exe = AoWz.exe with this one byte flipped (build number 15 -> 5).
COMPAT_OFF, COMPAT_AOW, COMPAT_CPT = zigexe.COMPAT_BYTE, 0x0F, 0x05

# ---- host site -------------------------------------------------------------------------
SITE = 0x0042CFD9                       # immediately after the value-loop terminator 0x42CFD7
SITE_OLD = bytes.fromhex("8b c3 e8 44 56 fd ff")   # mov eax,ebx ; call 0x00402624
SITE_LEN = 7

FILL_FN = 0x0042CDE8                    # TMagicWin fill routine -- opening bytes asserted
LOOP_END = 0x0042CFD7                   # `jne 0x42CF5B`, the value-loop terminator

# ---- imported entry points (thunks; all three already have exactly 1 IAT ref) -----------
GETPOWER = 0x00402624                   # jmp [0x0045DD50] AoWE.TPlayerMagicControl.GetPower
GETNETPOWER = 0x0040262C                # jmp [0x0045DD4C] AoWE.TPlayerMagicControl.GetNetPower
INTTOSTR = 0x004013AC                   # jmp [0x0045D448] VCL30 SysUtils.IntToStr
IAT_GETPOWER, IAT_GETNETPOWER, IAT_INTTOSTR = 0x0045DD50, 0x0045DD4C, 0x0045D448

# ---- struct offsets, all read out of the live fill loop --------------------------------
O_FORM = -0x04                          # [ebp-4]     the TMagicWin
O_TMP = -0x0C                           # [ebp-0xC]   the managed AnsiString temp it reuses
O_NAMELIST = 0x110                      # [form+0x110] PowerSourceList  (TAOWListBox)
O_VALUELIST = 0x108                     # [form+0x108] PowerValueList   (TAOWListBox)
O_STRINGS = 0x114                       # [listbox+0x114] the TStrings behind it
V_ADD = 0x34                            # [stringsvmt+0x34] TStrings.Add
V_ADDOBJECT = 0x38                      # [stringsvmt+0x38] TStrings.AddObject

# ---- cave ------------------------------------------------------------------------------
CAVE = 0x0062D100                       # `.hcol` slack; see the docstring for why here
CAVE_SPAN = 0x200                       # bytes this script owns and zeroes on --undo
HCOL_VA, HCOL_SIZE = 0x00612000, 0x1C000
ZONE_START = 0x0062D0A0                 # first byte past build_savedate_format.py's 0x80 slot
ZONE_END = 0x0062E000                   # end of `.hcol`; asserted zero outside our span

LABEL_GAIN = b"Power Leech (gained)"
LABEL_LOSS = b"Power Leech (lost)"

OFF_LIT_GAIN = 0x000                    # literal record; chars at +8
OFF_LIT_LOSS = 0x020
OFF_RET_STUB = 0x040
OFF_FAKE_VMT = 0x044
VMT_SLOTS = 24                          # +0x00..+0x5C, the whole TPlayerStructurePowerSource VMT
OFF_FAKE_OBJ = OFF_FAKE_VMT + 4 * VMT_SLOTS      # 0x0A4
OFF_CODE = 0x0A8

LIT_GAIN = CAVE + OFF_LIT_GAIN + 8
LIT_LOSS = CAVE + OFF_LIT_LOSS + 8
RET_STUB = CAVE + OFF_RET_STUB
FAKE_VMT = CAVE + OFF_FAKE_VMT
FAKE_OBJ = CAVE + OFF_FAKE_OBJ
CODE_VA = CAVE + OFF_CODE

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)


def lit(text):
    """A Delphi 3 literal AnsiString record: refCnt -1, length, chars, NUL.

    Shape read out of AoWz.exe itself -- 0x0042D290 is FF FF FF FF | 01 00 00 00 | '-' 00, and
    0x0042D00B pushes 0x0042D298, i.e. the chars, 8 past the record. refCnt -1 is what makes it
    safe: _LStrAsg copies a negative-refcount string rather than incrementing it."""
    return struct.pack("<iI", -1, len(text)) + text + b"\0"


# ============================================================ the cave
SRC = f"""
    push ebx
    push esi
    push edi
    mov eax, ebx
    call 0x{GETPOWER:X}
    mov edi, eax
    mov eax, ebx
    call 0x{GETNETPOWER:X}
    sub eax, edi
    mov esi, eax
    test esi, esi
    jz _done
    mov edx, 0x{LIT_GAIN:X}
    test esi, esi
    jg _label
    mov edx, 0x{LIT_LOSS:X}
_label:
    mov ecx, 0x{FAKE_OBJ:X}
    mov eax, dword ptr [ebp{O_FORM}]
    mov eax, dword ptr [eax+0x{O_NAMELIST:X}]
    mov eax, dword ptr [eax+0x{O_STRINGS:X}]
    push edi
    mov edi, dword ptr [eax]
    call dword ptr [edi+0x{V_ADDOBJECT:X}]
    pop edi
    mov eax, esi
    lea edx, dword ptr [ebp{O_TMP}]
    call 0x{INTTOSTR:X}
    mov edx, dword ptr [ebp{O_TMP}]
    mov eax, dword ptr [ebp{O_FORM}]
    mov eax, dword ptr [eax+0x{O_VALUELIST:X}]
    mov eax, dword ptr [eax+0x{O_STRINGS:X}]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x{V_ADD:X}]
_done:
    mov eax, edi
    pop edi
    pop esi
    pop ebx
    ret
"""

CODE = bytes(ks.asm(SRC, CODE_VA)[0])
RET_STUB_BYTES = bytes(ks.asm("xor eax, eax\nret", RET_STUB)[0])

_blob = bytearray(CAVE_SPAN)
_blob[OFF_LIT_GAIN:OFF_LIT_GAIN + len(lit(LABEL_GAIN))] = lit(LABEL_GAIN)
_blob[OFF_LIT_LOSS:OFF_LIT_LOSS + len(lit(LABEL_LOSS))] = lit(LABEL_LOSS)
_blob[OFF_RET_STUB:OFF_RET_STUB + len(RET_STUB_BYTES)] = RET_STUB_BYTES
for _i in range(VMT_SLOTS):
    struct.pack_into("<I", _blob, OFF_FAKE_VMT + 4 * _i, RET_STUB)
struct.pack_into("<I", _blob, OFF_FAKE_OBJ, FAKE_VMT)
_blob[OFF_CODE:OFF_CODE + len(CODE)] = CODE
CAVE_REGION = bytes(_blob)
ZERO_REGION = bytes(CAVE_SPAN)

SITE_NEW = (b"\xE8" + struct.pack("<i", CODE_VA - (SITE + 5))
            + b"\x90" * (SITE_LEN - 5))


# ============================================================ build-time guards
def build_checks():
    assert len(SITE_OLD) == SITE_LEN and len(SITE_NEW) == SITE_LEN
    assert OFF_LIT_GAIN + len(lit(LABEL_GAIN)) <= OFF_LIT_LOSS
    assert OFF_LIT_LOSS + len(lit(LABEL_LOSS)) <= OFF_RET_STUB
    assert OFF_RET_STUB + len(RET_STUB_BYTES) <= OFF_FAKE_VMT
    assert OFF_FAKE_OBJ + 4 <= OFF_CODE
    assert OFF_CODE + len(CODE) <= CAVE_SPAN, "cave overflows its %#x reservation" % CAVE_SPAN
    assert CAVE >= ZONE_START and CAVE + CAVE_SPAN <= ZONE_END
    assert HCOL_VA <= CAVE and CAVE + CAVE_SPAN <= HCOL_VA + HCOL_SIZE

    # G1 -- the literals round-trip out of the blob exactly as VCL will read them.
    for va, text in ((LIT_GAIN, LABEL_GAIN), (LIT_LOSS, LABEL_LOSS)):
        o = va - CAVE
        ref, ln = struct.unpack_from("<iI", CAVE_REGION, o - 8)
        assert ref == -1, "G1 literal @%08X refCnt %d, expected -1" % (va, ref)
        assert ln == len(text), "G1 literal @%08X length %d, expected %d" % (va, ln, len(text))
        assert CAVE_REGION[o:o + ln] == text, "G1 literal @%08X chars differ" % va
        assert CAVE_REGION[o + ln] == 0, "G1 literal @%08X is not NUL-terminated" % va

    ins = list(cs.disasm(CODE, CODE_VA))
    txt = [(i.address, i.mnemonic, i.op_str) for i in ins]
    assert sum(i.size for i in ins) == len(CODE), "G? capstone could not decode the whole cave"

    # G2 -- every absolute operand is one of ours. Direct calls are E8 rel32 (capstone prints
    #       the RESOLVED target; the bytes are relative), so they are excluded by opcode.
    branch = ("call", "jmp", "je", "jne", "jz", "jnz", "jg", "jge", "jl", "jle", "jns", "js")
    allowed_abs = {LIT_GAIN, LIT_LOSS, FAKE_OBJ}
    for a, m, o in txt:
        if m in branch:
            continue
        for w in re.findall(r"0x[0-9a-f]{6,8}", o):
            assert int(w, 16) in allowed_abs, (
                "G2 absolutes: %08X %s %s references %s" % (a, m, o, w))

    # G3 -- every direct call leaves the cave only to a sanctioned entry point.
    allowed_call = {GETPOWER, GETNETPOWER, INTTOSTR}
    out = set()
    for i in ins:
        if i.mnemonic in ("call", "jmp") and i.op_str.startswith("0x"):
            t = int(i.op_str, 16)
            if not (CODE_VA <= t < CODE_VA + len(CODE)):
                out.add(t)
    assert not out - allowed_call, ("G3 call targets: unsanctioned %s"
                                    % ["%08X" % x for x in sorted(out - allowed_call)])

    # G4 -- the keystone imm8 trap: `push 0xFFFF` silently assembles to `6A FF` = push -1.
    signed = [("%08X" % a, m, o) for a, m, o in txt if re.search(r"(?:^|,\s*)-1\b", o)]
    assert not signed, "G4 imm8 trap: -1 operand(s) %s" % signed

    # G5 -- exactly one exit, and the pushes/pops balance (3 saves + 1 spill pair).
    n_ret = sum(1 for _a, m, _o in txt if m == "ret")
    n_push = sum(1 for _a, m, o in txt if m == "push")
    n_pop = sum(1 for _a, m, o in txt if m == "pop")
    assert n_ret == 1, "G5 frames: %d ret, expected 1" % n_ret
    assert n_push == n_pop == 4, "G5 frames: %d push / %d pop, expected 4/4" % (n_push, n_pop)

    # G6 -- every fake VMT slot points at RET_STUB, and RET_STUB is `xor eax,eax ; ret`.
    for i in range(VMT_SLOTS):
        v = struct.unpack_from("<I", CAVE_REGION, OFF_FAKE_VMT + 4 * i)[0]
        assert v == RET_STUB, "G6 fake VMT slot +%#04x is %08X, expected %08X" % (
            4 * i, v, RET_STUB)
    stub = list(cs.disasm(RET_STUB_BYTES, RET_STUB))
    assert [(s.mnemonic, s.op_str) for s in stub] == [("xor", "eax, eax"), ("ret", "")], (
        "G6 ret stub is %s" % [(s.mnemonic, s.op_str) for s in stub])
    assert struct.unpack_from("<I", CAVE_REGION, OFF_FAKE_OBJ)[0] == FAKE_VMT

    # the hook must reach the cave and be a plain E8 rel32 + NOP padding
    assert SITE_NEW[0] == 0xE8 and set(SITE_NEW[5:]) <= {0x90}
    assert SITE + 5 + struct.unpack_from("<i", SITE_NEW, 1)[0] == CODE_VA


build_checks()


# ============================================================ PE helpers
def load_secs(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    sect = e + 24 + optsz
    secs = []
    for i in range(nsec):
        b = sect + i * 40
        vs, va, rs, raw = struct.unpack_from("<IIII", d, b + 8)
        chars = struct.unpack_from("<I", d, b + 36)[0]
        secs.append((bytes(d[b:b + 8]).rstrip(b"\0").decode("latin1"), va, vs, raw, rs, chars))
    return secs


def va2off(secs, va):
    """VA -> file offset, resolved PER SECTION -- never a flat delta."""
    r = va - IMAGE_BASE
    for nm, v, vs, raw, rs, _c in secs:
        if v <= r < v + max(vs, rs):
            o = raw + (r - v)
            assert o < raw + rs, "%08X is past %s's raw data" % (va, nm)
            return o
    raise ValueError("VA %08X is in no section" % va)


def reloc_hits(d, secs, lo, hi):
    """Every .reloc entry whose target VA lies in [lo, hi)."""
    e = struct.unpack_from("<I", d, 0x3C)[0]
    magic = struct.unpack_from("<H", d, e + 24)[0]
    dd = e + 24 + (96 if magic == 0x10B else 112)
    rva, size = struct.unpack_from("<II", d, dd + 5 * 8)
    if not rva or not size:
        return []
    off = va2off(secs, IMAGE_BASE + rva)
    end, hits = off + size, []
    while off < end:
        pg, blk = struct.unpack_from("<II", d, off)
        if blk == 0:
            break
        for i in range((blk - 8) // 2):
            w = struct.unpack_from("<H", d, off + 8 + i * 2)[0]
            if w >> 12 and lo <= IMAGE_BASE + pg + (w & 0xFFF) < hi:
                hits.append(IMAGE_BASE + pg + (w & 0xFFF))
        off += blk
    return hits


def branches_into(d, secs, lo, hi):
    """Every rel8/rel32 branch in CODE that could land strictly inside (lo, hi).

    A jump landing exactly on `lo` is fine -- it hits the first byte of the replacement, and one
    does: 0x0042CF4F `jl 0x0042CFD9` skips the fill loop when the player has no power sources.
    A jump landing anywhere AFTER it would be cut in half by the E8, which is the classic
    displaced-bytes disaster, so that is a hard abort.

    This is a byte-pattern sweep, not a linear disassembly: it over-reports (a rel32 displacement
    that happens to sit inside data will match) and never under-reports, which is the direction
    to be wrong in."""
    for nm, v, vs, raw, rs, _c in secs:
        if nm == "CODE":
            base, off, ln = IMAGE_BASE + v, raw, min(vs, rs)
            break
    blob = bytes(d[off:off + ln])
    hits = []
    for i in range(ln - 5):
        b = blob[i]
        if b in (0xE8, 0xE9):                                   # call/jmp rel32
            t = base + i + 5 + struct.unpack_from("<i", blob, i + 1)[0]
            n = 5
        elif b == 0x0F and 0x80 <= blob[i + 1] <= 0x8F:         # jcc rel32
            t = base + i + 6 + struct.unpack_from("<i", blob, i + 2)[0]
            n = 6
        elif b == 0xEB or 0x70 <= b <= 0x7F or b in (0xE0, 0xE1, 0xE2, 0xE3):   # rel8
            t = base + i + 2 + struct.unpack_from("<b", blob, i + 1)[0]
            n = 2
        else:
            continue
        if lo < t < hi:
            hits.append((base + i, "%02x" % b, t, n))
    return hits


# ============================================================ report
def show_dis():
    print("cave_powerleech_ui @ %08X  (span %#x, code %d bytes at %08X)"
          % (CAVE, CAVE_SPAN, len(CODE), CODE_VA))
    print("  section .hcol  %08X..%08X   zone asserted zero %08X..%08X outside our span"
          % (HCOL_VA, HCOL_VA + HCOL_SIZE, ZONE_START, ZONE_END))
    print()
    print("  data")
    for va, text in ((LIT_GAIN, LABEL_GAIN), (LIT_LOSS, LABEL_LOSS)):
        rec = va - 8
        o = rec - CAVE
        print("    %08X  %s  refCnt -1, length %d   chars @%08X  %r"
              % (rec, CAVE_REGION[o:o + 8].hex(" "), len(text), va, text.decode()))
    print("    %08X  %s  ret stub: xor eax, eax ; ret" % (RET_STUB, RET_STUB_BYTES.hex(" ")))
    print("    %08X  fake VMT, %d slots (+0x00..+0x%02X), every one -> %08X"
          % (FAKE_VMT, VMT_SLOTS, 4 * VMT_SLOTS - 4, RET_STUB))
    print("    %08X  fake object, one dword -> %08X" % (FAKE_OBJ, FAKE_VMT))
    print()
    print("  code")
    names = {LIT_GAIN: "LIT_GAIN", LIT_LOSS: "LIT_LOSS", FAKE_OBJ: "FAKE_OBJ",
             GETPOWER: "GetPower", GETNETPOWER: "GetNetPower", INTTOSTR: "IntToStr"}
    for i in cs.disasm(CODE, CODE_VA):
        tag = ""
        for w in re.findall(r"0x[0-9a-f]{6,8}", i.op_str):
            n = names.get(int(w, 16))
            if n:
                tag = "   <-- " + n
        print("    %08X  %-22s %s %s%s"
              % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str, tag))
    print()
    print("  hook @ %08X (%d bytes): %s -> %s"
          % (SITE, SITE_LEN, SITE_OLD.hex(" "), SITE_NEW.hex(" ")))
    print("        rel32 %+d  ->  %08X" % (struct.unpack_from("<i", SITE_NEW, 1)[0], CODE_VA))


def kill_running():
    # SCRATCH GUARD: AOW_GAME_DIR set => not the real install; never kill the user's game.
    if os.environ.get("AOW_GAME_DIR"):
        return
    # ⚠ the mod exes were renamed AoWz*/AoWzEd on 2026-09-09; a list that stops at AoW/AoWCompat/
    # AoWDevEd/AoWEd cannot release a lock held by AoWz.exe or AoWzEd.exe. Single source:
    # zigexe.LOCKING_PROCESSES.
    ps = ("Get-Process | Where-Object { $_.ProcessName -match '^(%s)$' } | Stop-Process -Force"
          % "|".join(zigexe.LOCKING_PROCESSES))
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=30)
    except Exception as ex:                                       # noqa: BLE001
        print("  (could not run the process kill: %s)" % ex)


PATCHES = [
    (SITE, SITE_OLD, SITE_NEW, "TMagicWin power fill: mov eax,ebx / call GetPower -> cave"),
    (CAVE, ZERO_REGION, CAVE_REGION, "cave_powerleech_ui @ %08X" % CAVE),
]


def check_one(path, undo):
    """Verify one exe. Returns (ok, todo, pristine, data, secs) -- data is a bytearray."""
    d = bytearray(open(path, "rb").read())
    secs = load_secs(d)
    name = os.path.basename(path)

    def rd(va, n):
        o = va2off(secs, va)
        return bytes(d[o:o + n])

    # ---- preconditions: the host really is the function we think it is ------------------
    if rd(FILL_FN, 5) != bytes.fromhex("55 8b ec b9 04".replace(" ", "")):
        print("ABORT %s: %08X does not open `push ebp / mov ebp,esp / mov ecx,4`."
              % (name, FILL_FN))
        return False, 0, 0, d, secs
    if rd(LOOP_END, 2) != bytes.fromhex("7582"):
        print("ABORT %s: %08X is %s, not the value-loop `jne` terminator."
              % (name, LOOP_END, rd(LOOP_END, 2).hex(" ")))
        return False, 0, 0, d, secs
    for thunk, slot, label in ((GETPOWER, IAT_GETPOWER, "GetPower"),
                               (GETNETPOWER, IAT_GETNETPOWER, "GetNetPower"),
                               (INTTOSTR, IAT_INTTOSTR, "IntToStr")):
        b = rd(thunk, 6)
        if b[0:2] != b"\xFF\x25" or struct.unpack_from("<I", b, 2)[0] != slot:
            print("ABORT %s: thunk %08X (%s) is %s, not `jmp [%08X]`."
                  % (name, thunk, label, b.hex(" "), slot))
            return False, 0, 0, d, secs

    # ---- the cave's home ---------------------------------------------------------------
    hcol = [s for s in secs if s[0] == ".hcol"]
    if not hcol or hcol[0][1] + IMAGE_BASE != HCOL_VA or hcol[0][2] != HCOL_SIZE:
        print("ABORT %s: `.hcol` is missing or has moved -- %s"
              % (name, [(s[0], hex(IMAGE_BASE + s[1]), hex(s[2])) for s in secs]))
        return False, 0, 0, d, secs
    if not hcol[0][5] & 0x20000000:
        print("ABORT %s: `.hcol` is not executable (characteristics %08X)."
              % (name, hcol[0][5]))
        return False, 0, 0, d, secs

    # ---- .reloc must not touch anything we write ---------------------------------------
    hits = (reloc_hits(d, secs, SITE, SITE + SITE_LEN)
            + reloc_hits(d, secs, CAVE, CAVE + CAVE_SPAN))
    if hits:
        print("ABORT %s: .reloc entries inside a written window: %s"
              % (name, ["%08X" % h for h in hits]))
        return False, 0, 0, d, secs

    # ---- nothing may branch into the middle of the displaced run ------------------------
    into = branches_into(d, secs, SITE, SITE + SITE_LEN)
    if into:
        print("ABORT %s: branch(es) landing inside the displaced bytes: %s"
              % (name, ["%08X op %s -> %08X" % (a, o, t) for a, o, t, _n in into]))
        return False, 0, 0, d, secs

    # ---- the rest of the .hcol tail stays somebody else's / zero -----------------------
    lo = rd(ZONE_START, CAVE - ZONE_START)
    hi = rd(CAVE + CAVE_SPAN, ZONE_END - CAVE - CAVE_SPAN)
    if set(lo) != {0} or set(hi) != {0}:
        print("ABORT %s: %08X..%08X outside our span is not zero -- something else moved in."
              % (name, ZONE_START, ZONE_END))
        return False, 0, 0, d, secs

    # ---- is SOME version of this feature installed? -------------------------------------
    # Re-tuning is an in-place cave rewrite, never revert-and-reapply. The positive test is the
    # host hook: if 0x0042CFD9 is an `E8 rel32` + NOP padding whose target lands anywhere inside
    # OUR reservation, then the reservation's contents are ours by construction and may be
    # overwritten wholesale -- the blob is always written at full CAVE_SPAN, so any zone a longer
    # cave grows into is covered, and the zero-assert above still guards everything outside it.
    # This does NOT relax the backup gate: `pristine` only counts bytes that are provably
    # PRE-FEATURE, so a re-tune mints no snapshot of its own previous output.
    hook_cur = rd(SITE, SITE_LEN)
    installed = False
    if hook_cur[0] == 0xE8 and set(hook_cur[5:]) <= {0x90}:
        tgt = SITE + 5 + struct.unpack_from("<i", hook_cur, 1)[0]
        installed = CAVE <= tgt < CAVE + CAVE_SPAN

    ok, todo, pristine, retune = True, 0, 0, 0
    for va, old, new, desc in PATCHES:
        target, other = (old, new) if undo else (new, old)
        cur = rd(va, len(new))
        if cur == target:
            if undo:
                pristine += 1
        elif cur == other:
            todo += 1
            if not undo:
                pristine += 1
        elif installed:
            todo += 1
            retune += 1
        else:
            print("MISMATCH %s: %s @ %08X\n  pre-feature %s\n  patched     %s\n  found       %s"
                  % (name, desc, va, old[:24].hex(" "), new[:24].hex(" "), cur[:24].hex(" ")))
            ok = False
    if retune:
        print("  %s: %d site(s) hold a DIFFERENT version of this feature -- rewriting in place, "
              "no backup" % (name, retune))
    return ok, todo, pristine, d, secs


def main():
    argv = sys.argv[1:]
    show_dis()
    print()
    if "--dis" in argv or "--show" in argv:
        return 0

    undo = "--undo" in argv
    state = {}
    allok, anytodo = True, 0
    for exe in EXES:
        path = os.path.join(GAME, exe)
        if not os.path.exists(path):
            print("ABORT: %s not found" % path)
            return 1
        ok, todo, pristine, d, secs = check_one(path, undo)
        verb = "undone" if undo else "applied"
        print("%-14s %d of %d to change, %d already %s%s"
              % (exe, todo, len(PATCHES), len(PATCHES) - todo, verb,
                 "" if ok else "   <-- MISMATCH"))
        state[exe] = (path, d, secs, todo, pristine)
        allok = allok and ok
        anytodo += todo

    if not allok:
        print("\nABORT: byte mismatch (different/partial patch state).")
        return 1
    todos = {e: state[e][3] for e in EXES}
    if len(set(todos.values())) != 1:
        print("\nABORT: the two exes are in DIFFERENT states %s -- fix the lockstep by hand "
              "before writing." % todos)
        return 1

    if "--apply" not in argv:
        print("\nDry run OK. Re-run with --apply to write, --undo --apply to remove.")
        return 0
    if anytodo == 0:
        print("\nNothing to do.")
        return 0

    kill_running()

    for exe in EXES:
        path, d, secs, todo, pristine = state[exe]
        # Backup ONLY from a file PROVED pre-feature -- never on --undo (the current file IS the
        # patched state by definition), never on a re-apply over our own output, and never
        # merely because no backup file exists.
        if not undo and pristine == len(PATCHES):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            bak = os.path.join(BACKUP_DIR, exe + SUFFIX)
            if not os.path.exists(bak):
                shutil.copyfile(path, bak)
                print("backup -> backups/%s" % os.path.basename(bak))
            else:
                print("backup backups/%s already exists, left alone" % os.path.basename(bak))
        elif not undo:
            print("(%s: no backup -- not in the pre-feature state; --undo is the revert path)"
                  % exe)

        for va, old, new, _desc in PATCHES:
            o = va2off(secs, va)
            blob = old if undo else new
            d[o:o + len(blob)] = blob
            print("  %-14s wrote %08X  %d byte(s)" % (exe, va, len(blob)))
        open(path, "wb").write(bytes(d))
        print("  %-14s sha-256 %s" % (exe, hashlib.sha256(bytes(d)).hexdigest()))

    # ---- lockstep proof: exactly one differing byte, and it is the build number ---------
    a = open(os.path.join(GAME, EXES[0]), "rb").read()
    b = open(os.path.join(GAME, EXES[1]), "rb").read()
    if len(a) != len(b):
        print("ABORT: %s and %s differ in LENGTH (%d vs %d)"
              % (EXES[0], EXES[1], len(a), len(b)))
        return 1
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if diff != [COMPAT_OFF] or a[COMPAT_OFF] != COMPAT_AOW or b[COMPAT_OFF] != COMPAT_CPT:
        print("ABORT: lockstep broken -- differing offsets %s (expected [%#x] with %#02x/%#02x)"
              % (["%#x" % x for x in diff[:8]], COMPAT_OFF, COMPAT_AOW, COMPAT_CPT))
        return 1
    print("lockstep OK: %s vs %s differ in exactly 1 byte, at %#x (%#02x/%#02x)"
          % (EXES[0], EXES[1], COMPAT_OFF, COMPAT_AOW, COMPAT_CPT))
    print("undone." if undo else "applied, UNTESTED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
