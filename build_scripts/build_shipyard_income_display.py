#!/usr/bin/env python3
r"""
AoW1 SHIPYARD WATER INCOME -- the DISPLAY half (`Ziggurat\AoWz.exe` + `AoWzCompat.exe`,
LOCKSTEP; names from `zigexe.py`).  ⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)

The income mechanic itself lives in build_shipyard_income.py (AoWEPACK.dpl, TShipyard VMT
+0x1F4 GetIncome). That half is CONFIRMED WORKING in-game (2026-08-26) and this script does
not touch it, or the DLL, or AoWDevEd.exe. Two surfaces in AoWz.exe never showed the number:

  PHASE A -- map structure-info panel, 4 bytes at 0x004438A0
      The panel gates the gold row on GetBaseIncome (VMT+0x22C) but PRINTS GetIncome
      (VMT+0x1F4) at 0x004438BE. The design deliberately leaves +0x22C at the zero stub, so
      the gate always closed. Repoint the GATE'S disp32 only:
          FF 92 2C 02 00 00  ->  FF 92 F4 01 00 00
      Displaces nothing, carries no .reloc entry.

      *** THREE other `call [reg+0x22C]` sites look identical and MUST NOT BE TOUCHED. ***
      This script asserts all of them unchanged on every run:
        0x00443B41  activity CAPTION if/else ([0x45E214] ProducingMerchandiseRStr vs
                    [0x45E3DC] NoneRStr). Repointing it makes every earning shipyard read
                    "Producing Merchandise" -- exactly what leaving +0x22C at zero bought.
        0x00440AD3  TProductionScreen.ActivityPreDraw -- CREATES a Merchandise
                    production-queue item on non-zero.
        0x0043F33F  production-screen control enable.
        0x00443119 / 0x00443140 / 0x0044318D  the ALTAR panel. On TAltar, +0x22C is
                    GetRechargeDays and +0x230 is CanTarget -- offset aliasing.

      Blast radius of the one edit: the dispatcher at 0x00444032 reaches this function only
      for TProductionPlace descendants with GetMagicSphere()==8, so the six magic nodes never
      arrive. That leaves TProductionPlace / TShipyard / TBuildersGuild / TRandomNode, and
      only TShipyard overrides +0x1F4 or +0x22C; for the other three GetIncome == 0 exactly
      when GetBaseIncome == 0.

  PHASE B -- Realm window gets a sixth income row, "Shipyards"
      0x00449030..0x004491CB emits five hard-coded rows into two TAOWMemo string lists,
      [ebx+0x140] IncomeMem (labels) and [ebx+0x184] IncomeValue (values), via
      [list+0x118].[vmt+0x34] = TStringList.Add. A sixth row needs no geometry work.

      Everything is in the exe. No DLL cave, no rebase-delta trick, NO NEW IMPORT: AoWz.exe
      already imports TPlayerStructureList.GetStructure (thunk 0x004023DC),
      TPlayerList.GetPlayers (0x00402464), TranslateRStr (0x004021E4), IntToStr (0x004013AC)
      and the AoWE.AoWHSMap slot [0x0045DF7C]; everything else is a VMT call.

      New PE section `.syd` @ VA 0x0062E000 (11th; template build_tierresearch_exe.py,
      second example build_herodlg_columns.py:258) holding:
        LIT_SHIPYARDS  a Delphi AnsiString literal (dd -1, dd 9, "Shipyards", NUL) fed to
                       TranslateRStr, which takes an AnsiString rather than a resource
                       record -- so the label stays dictionary-translatable via
                       Dict/ResStr.txt, and the -1 refcount makes @LStrAsg/@LStrClr no-ops.
                       (AoWE.ShipyardRStr is NOT usable: AoWz.exe imports 1,625 AoWEPACK
                       symbols and it is not among them; the five vanilla row labels are
                       *data* imports. Adding an import is a recorded refusal --
                       Editor_Modernization_DialogDirs_Toolbar.md:124, "fragile table
                       surgery".)
        cave_sum       (EDX = seated player index) -> EAX. Shape-cloned from
                       Mine.MineIncome @0x557B47C4 -- SHAPE, not bytes: 0x557B47CE and
                       0x557B47DC are absolute DLL globals. Walks the player's
                       TPlayerStructureList, keeps ClassID == 0x000204BE (TShipyard) owned by
                       that index, sums [vmt+0x1F4].
                       *** Returns 0, NOT -1, on a nil map. *** MineIncome's -1 would print
                       as a literal "-1" row, because the row's skip test is `test esi,esi`.
        cave_row       the hook body: sum, skip if zero, else Add the label and the value,
                       then re-execute the 9 displaced bytes and jmp back.

      Hook: E9 rel32 at 0x004491CC + 4x 0x90, displacing 9 .reloc-clean bytes
      `8B 07 0F BE 90 A5 00 00 00` (mov eax,[edi] / movsx edx,byte [eax+0xA5]). The only
      inbound branch (je at 0x00449180) lands exactly on the hook. Cave resumes 0x004491D5.

      The frame's own [ebp-4] LStr temp is reused exactly as the five vanilla rows do; the
      epilogue's @LStrArrayClr at 0x00449219 already frees it. No BSS, no leak.

COLUMN CAPACITY -- computed statically, NOT the lever the spec expected
      Row capacity is TAOWMemo [+0x124], set in TAOWMemo.SetSize (aowInt.dpl 0x598189C0).
      TAOWMemo.Validate (0x5981893C) sets the style byte [+0x16A] = 0 when BOTH ILFrame
      (+0x15C) and ILTexture (+0x160) are non-nil, else 1. SetSize then does:
          style 0 (framed):    [+0x124] = (WinHeight - frame[idx+1].h - frame[idx+6].h)
                                          div ItemHeight
          style 1 (frameless): [+0x124] =  WinHeight div ItemHeight
      and TAOWMemo.Draw runs `for i := 0 to [+0x124] do`, i.e. [+0x124]+1 rows, clipped at
      absTop + WinHeight. BorderHeight (+0x9C) is only the text y-inset, NOT part of the
      capacity formula -- so `IncomeValue.BorderHeight 4 -> 1` would have changed nothing and
      is NOT applied.
      Both memos are ahBoth in IncomePnl with TopOffset 0 / BottomOffset 21, so their runtime
      heights are always equal (designer 76 = IncomePnl 97 - 0 - 21). ItemHeight 12 both.
        IncomeMem   ILFrame GenericF + ILTexture GenericT -> framed. ILIndexFrame 113, so
                    the edges are GenericF ids 114 and 119, both 3px high (FrGoldD.BMP):
                    [+0x124] = (76 - 3 - 3) div 12 = 5  ->  6 rows drawn, row 5 at y+1+60=61
        IncomeValue no ILFrame/ILTexture at all -> frameless:
                    [+0x124] =  76           div 12 = 6  ->  7 rows drawn, row 5 at y+4+60=64
      Both hold the sixth row inside the 76px clip, so NO DFM edit is applied. IncomeMem's
      scrollbar (IncomeSB) does become live at 6 items vs a page of 5; it does not auto-scroll
      ([+0x128] only follows the scrollbar's own position in TAOWMemo.Update).
      *** Still worth a look in-game: a clipped or misaligned sixth row is cosmetic and
      immediately visible. ***

WHY THIS IS A SEPARATE SCRIPT from build_shipyard_income.py
      That script's --undo is proven to return AoWEPACK.dpl byte-identical to
      .pre-shipyardincome; folding exe writes into it would make the proof partial and the
      backup name a lie. The income half is confirmed, the display half is not, and a display
      defect must be revertible without disturbing a confirmed feature. This is also a
      STRUCTURAL PE change (new section, NumberOfSections, SizeOfImage, file length) whose
      undo must truncate the file -- only safe while it owns the last section.

⚠⚠ FORWARD HAZARD, LIVE SINCE build_unitwin_party_arrows.py APPENDED `.pyar` (found 2026-09-09)
      That script added a 12th section `.pyar` @ VA 0x0062F000, raw 0x229200, i.e. AFTER `.syd`.
      `.syd` itself is untouched and this feature is fully installed (gate repointed, hook ours,
      blob byte-identical -- verified 2026-09-09 on both mod exes), but THREE checks here assume
      `.syd` is still the last section and now all report a false negative:

        state()      `nsec != EXP_NSEC + 1`               -> "mixed: .syd present but nsec=12"
        drift()      `soi != NEW_SOI`                     -> SizeOfImage is 0x230000, not 0x22F000
        drift()      `len(d) != SEC_FOFF + SEC_SIZE`      -> EOF is 0x22A200, not 0x229200

      So a no-arg run prints FAILED and exits 1 even though nothing is wrong with this feature.
      LEFT AS IS DELIBERATELY (2026-09-09, exe-rename migration): loosening a guard is a
      behaviour change and this pass was scoped to the rename. Read the three lines above as the
      explanation whenever this script cries wolf.

      ⚠ DO NOT RUN `--apply` UNTIL THAT IS RESOLVED. The re-tune arm of do_apply() ends with
      `struct.pack_into("<I", d, soi_off, NEW_SOI)`, which would write SizeOfImage back DOWN to
      0x22F000 and leave `.pyar`'s page UNMAPPED -- silently breaking the party-arrow caves.
      `--undo` is safe: it already refuses while anything sits after `.syd` (it would have to
      truncate the file), and prints why.

CROSS-SCRIPT COUPLING -- measured with `.syd` installed, 2026-08-26
      Both other section-appending scripts still report their own feature healthy and no-op:
        build_tierresearch_exe.py  finds its `.tres` blob at 0x20B200 and prints "already
              applied". Its `nsec == 8` / `EOF == 0x20B200` asserts only guard a FRESH apply,
              so if `.tres` were ever removed, re-applying it with `.syd` present aborts
              (safe) rather than corrupts.
        build_herodlg_columns.py   add_section() returns early because `.hcol` exists, so its
              --apply (which undoes and rebuilds) never re-appends. Its undo deliberately
              leaves the inert `.hcol` section in place, which is what keeps that true.
      *** The one dangerous ordering CORRUPTS THE IMAGE -- it is not an inconvenience.
      If `.hcol` is ever removed and build_herodlg_columns.py is re-applied while `.syd` is
      installed, its add_section() (build_herodlg_columns.py:258) appends `.hcol` at the new
      EOF and then sets
          SizeOfImage = align_up(its OWN rva + size) = align_up(0x212000 + 0x1C000) = 0x22E000
      -- computed from its own section, not from the highest one. That is BELOW `.syd`'s end
      0x22F000, so the loader stops mapping at 0x0062E000 and OUR ENTIRE CAVE PAGE IS
      UNMAPPED: the hook at 0x004491CC then jumps into nothing and the Realm window kills the
      process. Our --undo additionally REFUSES at that point (EOF != .syd end) rather than
      truncating someone else's section, so there is no self-service way out.
      So: undo `.syd` FIRST, re-apply either of them from scratch, then re-apply `.syd`.

Backups: backups\AoWz.exe.pre-shipyarddisplay / backups\AoWzCompat.exe.pre-shipyarddisplay --
         taken ONLY from a
file proved unpatched by this feature (10 sections, EOF 0x228200, both sites vanilla). Never
on --undo, never on a re-tune.

Usage:
  python build_scripts/build_shipyard_income_display.py            dry run + verify state
  python build_scripts/build_shipyard_income_display.py --apply    patch (in-place re-tune ok)
  python build_scripts/build_shipyard_income_display.py --undo      surgical revert + truncate
  python build_scripts/build_shipyard_income_display.py --dis       disassemble the caves
  python build_scripts/build_shipyard_income_display.py --selftest  fire every build assertion

GUARDS
      build_checks()  G1..G8, offline -- they tie the ASSEMBLED CAVE to the constants.
      host_checks()   G2 and G4 again, tied to the BINARIES instead: the resume address is
                      re-derived by disassembling AoWz.exe forward from the inbound `je`, and
                      the ClassID is read out of Shipyard.TShipyard.ClassID in AoWEPACK.dpl.
                      Without these two, mutating HOOK_RESUME or SHIPYARD_CLASSID moves both
                      sides of the comparison and the build stays clean. Both run at import,
                      so a wrong constant aborts every mode including --dis.
      A verification run (no flags) also FAILS, loudly and non-zero, if what is installed is
      not byte-identical to what this script builds.
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

EXES = list(zigexe.EXES)
BACKUP_SUFFIX = ".pre-shipyarddisplay"
BACKUP_DIR = os.path.join(GAME, "backups")      # ⚠ backups/, never the game root -- rule 2026-09-03
IB = 0x00400000

# ---- the new section ----------------------------------------------------------------
SEC_NAME = b".syd"
SEC_VA = 0x0062E000
SEC_RVA = SEC_VA - IB            # 0x22E000, exactly the end of .hcol
SEC_SIZE = 0x1000
SEC_FOFF = 0x00228200            # current EOF of both exes (asserted)
EXP_NSEC = 10
EXP_SOI = 0x0022E000
NEW_SOI = 0x0022F000
SEC_CHARS = 0xE0000060

# ---- PHASE A ------------------------------------------------------------------------
GATE_VA = 0x004438A0
GATE_OLD = bytes.fromhex("ff922c020000")     # call [edx+0x22C]  GetBaseIncome
GATE_NEW = bytes.fromhex("ff92f4010000")     # call [edx+0x1F4]  GetIncome

# ---- PHASE B ------------------------------------------------------------------------
HOOK_VA = 0x004491CC
HOOK_ORIG = bytes.fromhex("8b070fbe90a5000000")   # 9 bytes, .reloc-clean
HOOK_RESUME = 0x004491D5

# import thunks already present in AoWz.exe (asserted against the live file)
T_GETSTRUCT = 0x004023DC          # AoWE.TPlayerStructureList.GetStructure
T_GETPLAYERS = 0x00402464         # AoWE.TPlayerList.GetPlayers
T_TRANSLATE = 0x004021E4          # AoWE.TranslateRStr
T_INTTOSTR = 0x004013AC           # SysUtils.IntToStr
THUNKS = {
    T_GETSTRUCT: bytes.fromhex("ff2574de4500"),
    T_GETPLAYERS: bytes.fromhex("ff2530de4500"),
    T_TRANSLATE: bytes.fromhex("ff2570df4500"),
    T_INTTOSTR: bytes.fromhex("ff2548d44500"),
}
G_MAP = 0x0045DF7C                # import slot; [G_MAP] = &AoWE.AoWHSMap, [[G_MAP]] = the map
SHIPYARD_CLASSID = 0x000204BE     # Shipyard.TShipyard.ClassID -- ANCHORED to the live DLL below
CLASSID_STUB_VA = 0x557C75C8      # AoWEPACK.dpl Shipyard.TShipyard.ClassID: b8 <id> c3
CLASSID_DLL = "AoWEPACK.dpl"

# ---- sites that must NOT move -------------------------------------------------------
UNTOUCHED = [
    (0x00443B41, GATE_OLD, "activity caption if/else (Producing Merchandise vs None)"),
    (0x00440AD3, GATE_OLD, "TProductionScreen.ActivityPreDraw (creates a queue item)"),
    (0x0043F33F, GATE_OLD, "production-screen control enable"),
    (0x00443119, GATE_OLD, "Altar panel (+0x22C = GetRechargeDays)"),
    (0x00443140, GATE_OLD, "Altar panel (+0x22C = GetRechargeDays)"),
    (0x0044318D, GATE_OLD, "Altar panel (+0x22C = GetRechargeDays)"),
]
ROWS_LO, ROWS_HI = 0x00448FF0, 0x004491CC     # the five vanilla Realm row blocks
ROWS_SHA1 = "719d65d6df6af0f78cc339ce34fdfff62f5966f4"
JE_VA, JE_BYTES = 0x00449180, bytes.fromhex("744a")   # je 0x4491CC -- lands on the hook

UNRELATED = ["AoWEPACK.dpl", "AoWDevEd.exe"]
LOCKSTEP_BYTE = zigexe.COMPAT_BYTE  # AoWzCompat.exe = AoWz.exe with this one byte 0x0F -> 0x05

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)


# ============================================================ .syd blob
blob = bytearray()
caves = []


def align(n):
    while len(blob) % n:
        blob.append(0)


def lit(s):
    """Delphi AnsiString literal: dd -1 (refcnt), dd len, bytes, NUL. -> VA of the chars."""
    align(4)
    blob.extend(struct.pack("<ii", -1, len(s)))
    ptr = SEC_VA + len(blob)
    blob.extend(s.encode("latin1") + b"\x00")
    return ptr


def add_cave(name, src):
    align(16)
    va = SEC_VA + len(blob)
    code = bytes(ks.asm(src, va)[0])
    blob.extend(code)
    caves.append((name, va, code))
    return va


LIT_SHIPYARDS = lit("Shipyards")

# cave_sum(EDX = seated player index) -> EAX = total shipyard income for that player.
# ebx/esi/edi/ebp are callee-saved under the Delphi register convention, so they survive the
# calls; [esp] = the index, [esp+4] = the running sum.
# NOTE: keystone rejects `;` and `//` comments inside the source -- keep this block bare.
SRC_SUM = f"""
    push ebx
    push esi
    push edi
    push ebp
    add esp, -8
    mov dword ptr [esp], edx
    mov dword ptr [esp+4], 0
    mov eax, dword ptr [0x{G_MAP:X}]
    test eax, eax
    je Lnil
    mov eax, dword ptr [eax]
    test eax, eax
    je Lnil
    mov eax, dword ptr [eax+0x140]
    test eax, eax
    je Lnil
    mov edx, dword ptr [esp]
    call 0x{T_GETPLAYERS:X}
    test eax, eax
    je Lnil
    mov ebp, dword ptr [eax+0x1c]
    test ebp, ebp
    je Lnil
    mov eax, ebp
    mov edx, dword ptr [eax]
    call dword ptr [edx+0x54]
    mov esi, eax
    test esi, esi
    jle Ldone
    xor edi, edi
Lloop:
    mov eax, ebp
    mov edx, edi
    call 0x{T_GETSTRUCT:X}
    test eax, eax
    je Lnext
    mov ebx, eax
    mov edx, dword ptr [eax]
    call dword ptr [edx+0x24]
    cmp eax, 0x{SHIPYARD_CLASSID:X}
    jne Lnext
    mov al, byte ptr [ebx+0x30]
    cmp al, byte ptr [esp]
    jne Lnext
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx+0x1f4]
    add dword ptr [esp+4], eax
Lnext:
    inc edi
    dec esi
    jne Lloop
Ldone:
    mov eax, dword ptr [esp+4]
    jmp Lout
Lnil:
    xor eax, eax
Lout:
    add esp, 8
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret
"""
CAVE_SUM = add_cave("cave_sum", SRC_SUM)

# cave_row: hook body at 0x004491CC. Live there: ebx = the form, edi = &AoWHSMap, ebp = frame.
# esi is dead after the BuildersGuilds row but is preserved anyway; eax/ecx/edx too.
SRC_ROW = f"""
    push eax
    push ecx
    push edx
    push esi
    mov eax, dword ptr [edi]
    test eax, eax
    je Lskip
    movsx edx, byte ptr [eax+0xa5]
    call 0x{CAVE_SUM:X}
    mov esi, eax
    test esi, esi
    je Lskip
    mov eax, 0x{LIT_SHIPYARDS:X}
    lea edx, [ebp-4]
    call 0x{T_TRANSLATE:X}
    mov edx, dword ptr [ebp-4]
    mov eax, dword ptr [ebx+0x140]
    mov eax, dword ptr [eax+0x118]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x34]
    lea edx, [ebp-4]
    mov eax, esi
    call 0x{T_INTTOSTR:X}
    mov edx, dword ptr [ebp-4]
    mov eax, dword ptr [ebx+0x184]
    mov eax, dword ptr [eax+0x118]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x34]
Lskip:
    pop esi
    pop edx
    pop ecx
    pop eax
    mov eax, dword ptr [edi]
    movsx edx, byte ptr [eax+0xa5]
    jmp 0x{HOOK_RESUME:X}
"""
CAVE_ROW = add_cave("cave_row", SRC_ROW)

assert len(blob) <= SEC_SIZE, "blob %#x exceeds the section" % len(blob)
BLOB = bytes(blob) + b"\x00" * (SEC_SIZE - len(blob))

HOOK_PATCH = b"\xE9" + struct.pack("<i", CAVE_ROW - (HOOK_VA + 5)) + b"\x90" * 4
assert len(HOOK_PATCH) == len(HOOK_ORIG)


# ============================================================ build-time assertions
def disasm(code, va):
    return list(cs.disasm(code, va))


def build_checks(bl=None, hook_orig=None, hook_patch=None, resume=None,
                 thunks=None, classid=None, lit_ptr=None):
    """Every guard, over overridable inputs so --selftest can break each one in turn."""
    bl = BLOB if bl is None else bl
    hook_orig = HOOK_ORIG if hook_orig is None else hook_orig
    hook_patch = HOOK_PATCH if hook_patch is None else hook_patch
    resume = HOOK_RESUME if resume is None else resume
    thunks = THUNKS if thunks is None else thunks
    classid = SHIPYARD_CLASSID if classid is None else classid
    lit_ptr = LIT_SHIPYARDS if lit_ptr is None else lit_ptr

    def cave(name):
        return next((n, va, c) for n, va, c in caves if n == name)

    _, row_va, row = cave("cave_row")
    _, sum_va, summ = cave("cave_sum")
    row_ins = disasm(row, row_va)
    sum_ins = disasm(summ, sum_va)

    # 1. the 9 displaced bytes are re-emitted verbatim, immediately before the jmp back
    tail = row[-(len(hook_orig) + 5):-5]
    assert tail == hook_orig, (
        "G1 displaced-bytes: cave re-emits %s, original is %s" % (tail.hex(" "), hook_orig.hex(" ")))

    # 2. the jmp back targets HOOK_RESUME. This half only ties the CAVE to the constant --
    #    on its own it is tautological (mutate HOOK_RESUME and both sides move together).
    #    host_checks() below anchors the constant itself to AoWz.exe.
    last = row_ins[-1]
    assert last.mnemonic == "jmp" and int(last.op_str, 16) == resume, (
        "G2 resume: cave ends `%s %s`, expected jmp %#x" % (last.mnemonic, last.op_str, resume))

    # 3. every direct call in the caves goes to one of the four sanctioned thunks
    #    (or to cave_sum), and each thunk's bytes match the live-file thunk we expect
    targets = set()
    for ins in row_ins + sum_ins:
        if ins.mnemonic == "call" and not ins.op_str.startswith(("dword", "e", "[")):
            targets.add(int(ins.op_str, 16))
    stray = targets - set(thunks) - {sum_va}
    assert not stray, "G3 call targets: unsanctioned %s" % [hex(x) for x in sorted(stray)]
    assert set(thunks) == {T_GETSTRUCT, T_GETPLAYERS, T_TRANSLATE, T_INTTOSTR}, (
        "G3 call targets: thunk table is %s" % [hex(x) for x in sorted(thunks)])

    # 4. the ClassID immediate is exactly TShipyard's. Again this half only ties the CAVE to
    #    the constant; host_checks() anchors the constant to Shipyard.TShipyard.ClassID in the
    #    live AoWEPACK.dpl, so a wrong ClassID (e.g. TMine's) cannot build clean.
    cmps = [i for i in sum_ins if i.mnemonic == "cmp" and i.op_str.startswith("eax, 0x")]
    assert len(cmps) == 1 and int(cmps[0].op_str.split(", ")[1], 16) == classid, (
        "G4 classid: cave compares %s, expected %#x" % ([i.op_str for i in cmps], classid))

    # 5. the nil-map path returns 0, not -1 (MineIncome's -1 would print a literal "-1" row)
    nils = [i for i in sum_ins if i.mnemonic == "xor" and i.op_str == "eax, eax"]
    assert nils, "G5 nil-path: cave_sum has no `xor eax, eax` return-zero"
    bad = [i.op_str for i in sum_ins if i.mnemonic in ("mov", "or")
           and re.search(r"^eax,\s*(-1\b|0xf{8}\b)", i.op_str)]
    assert not bad, "G5 nil-path: cave_sum returns -1 (%s)" % bad

    # 6. the keystone imm8 trap: NO operand anywhere in any cave renders as -1.
    #    `push 0xFFFF` silently assembles to `6A FF` = `push -1`, which has no comma before
    #    it -- so the test must be "any operand equal to -1", not "`, -1`".
    signed = [(n, "%08X" % i.address, i.mnemonic, i.op_str)
              for n, va, c in caves for i in disasm(c, va)
              if re.search(r"(?:^|,\s*)-1\b", i.op_str)]
    assert not signed, "G6 imm8 trap: -1 operand(s) %s" % signed

    # 7. the AnsiString literal is well formed: refcnt -1, correct length, NUL-terminated
    off = lit_ptr - SEC_VA
    rc, ln = struct.unpack_from("<ii", bl, off - 8)
    assert rc == -1, "G7 literal: refcnt %d, expected -1" % rc
    assert bl[off:off + ln] == b"Shipyards" and bl[off + ln] == 0, (
        "G7 literal: %r len %d" % (bytes(bl[off:off + ln + 1]), ln))

    # 8. the hook replacement is the same length as what it displaces and lands in cave_row
    assert len(hook_patch) == len(hook_orig), "G8 hook length %d vs %d" % (
        len(hook_patch), len(hook_orig))
    assert hook_patch[0] == 0xE9 and \
        HOOK_VA + 5 + struct.unpack_from("<i", hook_patch, 1)[0] == row_va, \
        "G8 hook target: %s does not reach cave_row %#x" % (hook_patch.hex(" "), row_va)


# ============================================================ PE helpers
def pe_info(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    sect = e + 24 + optsz
    return e, nsec, optsz, sect, e + 24 + 56


def sections(d):
    _e, nsec, _o, sect, _s = pe_info(d)
    out = []
    for i in range(nsec):
        b = sect + i * 40
        vs, rva, rs, raw = struct.unpack_from("<IIII", d, b + 8)
        out.append((d[b:b + 8].rstrip(b"\0"), rva, vs, rs, raw, b))
    return out


def image_base(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    return struct.unpack_from("<I", d, e + 24 + 28)[0]


def va2off(d, va, ib=IB):
    """VA -> file offset, resolved PER SECTION (never a flat delta). ib defaults to AoWz.exe's."""
    r = va - ib
    for _nm, rva, vs, rs, raw, _b in sections(d):
        if rva <= r < rva + max(vs, rs):
            return raw + (r - rva)
    raise ValueError("VA %#x is in no section" % va)


def syd_slot(d):
    for nm, rva, vs, rs, raw, b in sections(d):
        if nm == SEC_NAME:
            return (rva, vs, rs, raw, b)
    return None


def rd(d, va, n):
    o = va2off(d, va)
    return bytes(d[o:o + n])


def wr(d, va, b):
    o = va2off(d, va)
    d[o:o + len(b)] = b


# ============================================================ host-anchored assertions
def host_checks(resume=None, classid=None, hook_orig=None, exe=None):
    """G2 and G4, anchored to the BINARIES rather than to the constants that built the cave.

    build_checks()'s G2/G4 compare the assembled cave against the same Python constant that
    produced it, so mutating the constant moves both sides and the guard cannot fire. These
    two read the answer out of the host files instead:

      G2  the resume address, from AoWz.exe: the inbound `je` at JE_VA gives a known-good
          instruction boundary; walking the live byte stream forward from it must land on
          HOOK_VA and on HOOK_RESUME, and HOOK_RESUME must be exactly one displacement window
          past HOOK_VA -- so it can never land INSIDE our own jump (the build_arena.py trap).
      G4  the ClassID, from AoWEPACK.dpl:  Shipyard.TShipyard.ClassID @CLASSID_STUB_VA is
          literally `mov eax,<id> / ret`; the cave's immediate must equal what it returns.
          This also makes the guard survive a future ClassID change.
    """
    resume = HOOK_RESUME if resume is None else resume
    classid = SHIPYARD_CLASSID if classid is None else classid
    hook_orig = HOOK_ORIG if hook_orig is None else hook_orig
    exe = zigexe.GAME_EXE if exe is None else exe        # AoWz.exe -- the canonical mod exe

    # ---------- G2: the resume address, anchored to the mod exe ----------
    path = os.path.join(GAME, exe)
    assert os.path.exists(path), (
        "G2 resume: %s not found -- the hook site cannot be anchored" % path)
    d = bytearray(open(path, "rb").read())

    # G2a -- relational: resume sits exactly past the bytes the jump displaces.
    assert resume == HOOK_VA + len(hook_orig), (
        "G2 resume: %#x is not HOOK_VA %#x + %d displaced bytes = %#x%s"
        % (resume, HOOK_VA, len(hook_orig), HOOK_VA + len(hook_orig),
           " -- IT LANDS INSIDE OUR OWN JUMP" if HOOK_VA <= resume < HOOK_VA + len(hook_orig)
           else ""))

    # G2b -- the known-good point: the only inbound branch, whose 2 bytes check_untouched()
    # also verifies. Its encoded target must be the hook site itself.
    je = rd(d, JE_VA, 2)
    assert je == JE_BYTES, (
        "G2 resume: inbound je at %08X is %s, expected %s -- no anchor"
        % (JE_VA, je.hex(" "), JE_BYTES.hex(" ")))
    je_target = JE_VA + 2 + struct.unpack_from("<b", je, 1)[0]
    assert je_target == HOOK_VA, (
        "G2 resume: the inbound je at %08X targets %08X, but HOOK_VA is %08X"
        % (JE_VA, je_target, HOOK_VA))

    # G2c -- walk the LIVE byte stream forward from that boundary. Both the hook site and the
    # resume address must fall on real instruction boundaries. This holds in either state:
    # vanilla the window is the 9 displaced bytes, applied it is `E9 rel32` + 4x NOP.
    anchor = JE_VA + 2
    bounds = {anchor}
    for ins in cs.disasm(rd(d, anchor, 0x60), anchor):
        bounds.add(ins.address + ins.size)
    assert HOOK_VA in bounds, (
        "G2 resume: %08X is not an instruction boundary when %s is disassembled forward from "
        "%08X" % (HOOK_VA, exe, anchor))
    assert resume in bounds, (
        "G2 resume: %08X is not an instruction boundary when %s is disassembled forward from "
        "%08X -- boundaries near it: %s"
        % (resume, exe, anchor,
           " ".join("%08X" % b for b in sorted(bounds) if abs(b - resume) <= 12)))

    # G2d -- when the host is not yet hooked, the displaced bytes we claim ARE the live bytes.
    live = rd(d, HOOK_VA, len(hook_orig))
    if live[:1] != b"\xE9":
        assert live == hook_orig, (
            "G2 resume: %s at %08X holds %s, but HOOK_ORIG is %s"
            % (exe, HOOK_VA, live.hex(" "), hook_orig.hex(" ")))

    # ---------- G4: the ClassID, anchored to AoWEPACK.dpl ----------
    dllp = os.path.join(GAME, CLASSID_DLL)
    assert os.path.exists(dllp), (
        "G4 classid: %s not found -- TShipyard.ClassID cannot be anchored" % dllp)
    dll = open(dllp, "rb").read()
    stub = bytes(dll[va2off(dll, CLASSID_STUB_VA, image_base(dll)):][:6])
    assert stub[0] == 0xB8 and stub[5] == 0xC3, (
        "G4 classid: %s @%08X is %s, not `mov eax, imm32 / ret` -- wrong address"
        % (CLASSID_DLL, CLASSID_STUB_VA, stub.hex(" ")))
    live_id = struct.unpack_from("<I", stub, 1)[0]
    assert classid == live_id, (
        "G4 classid: the cave uses %#x, but Shipyard.TShipyard.ClassID @%08X in %s returns %#x"
        % (classid, CLASSID_STUB_VA, CLASSID_DLL, live_id))


build_checks()
host_checks()


# ============================================================ state + checks
def check_untouched(d, exe):
    ok = True
    for va, want, why in UNTOUCHED:
        got = rd(d, va, len(want))
        if got != want:
            print("  %s: MOVED %08X (%s)\n    exp %s\n    got %s"
                  % (exe, va, why, want.hex(" "), got.hex(" ")))
            ok = False
    got = rd(d, JE_VA, 2)
    if got != JE_BYTES:
        print("  %s: inbound `je` at %08X is %s, expected %s (must land on the hook)"
              % (exe, JE_VA, got.hex(" "), JE_BYTES.hex(" ")))
        ok = False
    rows = bytes(d[va2off(d, ROWS_LO):va2off(d, ROWS_HI)])
    if hashlib.sha1(rows).hexdigest() != ROWS_SHA1:
        print("  %s: the five vanilla Realm row blocks %08X..%08X changed (sha1 %s)"
              % (exe, ROWS_LO, ROWS_HI, hashlib.sha1(rows).hexdigest()))
        ok = False
    for va, want in THUNKS.items():
        got = rd(d, va, len(want))
        if got != want:
            print("  %s: import thunk %08X is %s, expected %s"
                  % (exe, va, got.hex(" "), want.hex(" ")))
            ok = False
    return ok


def hook_is_ours(hook):
    """True only if these bytes are a jump WE could have written -- E9 into .syd, NOP tail.

    `hook[0] == 0xE9` alone is not enough: a foreign hook installed at the same site by some
    other script is also an E9, and treating it as ours would make --undo stamp HOOK_ORIG
    over someone else's patch.
    """
    if len(hook) < 5 or hook[0] != 0xE9:
        return False
    if hook[5:] != b"\x90" * (len(hook) - 5):
        return False
    tgt = HOOK_VA + 5 + struct.unpack_from("<i", hook, 1)[0]
    return SEC_VA <= tgt < SEC_VA + SEC_SIZE


def state(d):
    """-> 'vanilla' | 'applied' | ('mixed', why)"""
    slot = syd_slot(d)
    gate = rd(d, GATE_VA, 6)
    hook = rd(d, HOOK_VA, len(HOOK_ORIG))
    _e, nsec, _o, _sect, _soi = pe_info(d)
    if slot is None:
        if nsec == EXP_NSEC and len(d) == SEC_FOFF and gate == GATE_OLD and hook == HOOK_ORIG:
            return "vanilla", ""
        return "mixed", ("no .syd section, but nsec=%d len=%#x gate=%s hook=%s"
                         % (nsec, len(d), gate.hex(" "), hook.hex(" ")))
    rva, vs, rs, raw, _b = slot
    if (rva, vs, rs, raw) != (SEC_RVA, SEC_SIZE, SEC_SIZE, SEC_FOFF):
        return "mixed", (".syd header is rva=%#x vs=%#x rs=%#x raw=%#x, expected %#x/%#x/%#x/%#x"
                         % (rva, vs, rs, raw, SEC_RVA, SEC_SIZE, SEC_SIZE, SEC_FOFF))
    if nsec != EXP_NSEC + 1:
        return "mixed", ".syd present but nsec=%d" % nsec
    if gate not in (GATE_OLD, GATE_NEW):
        return "mixed", "gate bytes %s" % gate.hex(" ")
    if hook != HOOK_ORIG and not hook_is_ours(hook):
        return "mixed", ("hook bytes %s at %08X are not ours -- an E9 here must resolve into "
                         ".syd [%08X..%08X)"
                         % (hook.hex(" "), HOOK_VA, SEC_VA, SEC_VA + SEC_SIZE))
    return "applied", ""


def fully_applied(d):
    return (state(d)[0] == "applied"
            and rd(d, GATE_VA, 6) == GATE_NEW
            and rd(d, HOOK_VA, len(HOOK_ORIG)) == HOOK_PATCH
            and bytes(d[SEC_FOFF:SEC_FOFF + SEC_SIZE]) == BLOB
            and struct.unpack_from("<I", d, pe_info(d)[4])[0] == NEW_SOI)


def blob_where(va):
    """Name the part of the .syd blob a VA falls in, for drift reporting."""
    for name, cva, code in caves:
        if cva <= va < cva + len(code):
            return "%s+%#x" % (name, va - cva)
    if LIT_SHIPYARDS - 8 <= va < LIT_SHIPYARDS + 10:
        return "LIT_SHIPYARDS%+d" % (va - LIT_SHIPYARDS)
    return "padding"


def drift(d):
    """What the INSTALLED patch has that this build does not. [] == byte-identical."""
    out = []
    gate = rd(d, GATE_VA, 6)
    if gate != GATE_NEW:
        out.append("gate %08X is %s, this build writes %s%s"
                   % (GATE_VA, gate.hex(" "), GATE_NEW.hex(" "),
                      "  (phase A not applied)" if gate == GATE_OLD else ""))
    hook = rd(d, HOOK_VA, len(HOOK_ORIG))
    if hook != HOOK_PATCH:
        out.append("hook %08X is %s, this build writes %s%s"
                   % (HOOK_VA, hook.hex(" "), HOOK_PATCH.hex(" "),
                      "  (phase B not applied)" if hook == HOOK_ORIG else
                      "  (jumps to %08X, this build's cave_row is at %08X)"
                      % (HOOK_VA + 5 + struct.unpack_from("<i", hook, 1)[0], CAVE_ROW)))
    cur = bytes(d[SEC_FOFF:SEC_FOFF + SEC_SIZE])
    if cur != BLOB:
        bad = [i for i in range(min(len(cur), SEC_SIZE)) if cur[i] != BLOB[i]]
        runs, start, prev = [], None, None
        for i in bad:
            if start is None or i != prev + 1:
                if start is not None:
                    runs.append((start, prev))
                start = i
            prev = i
        if start is not None:
            runs.append((start, prev))
        shown = ["%08X..%08X in %s (%s -> %s)"
                 % (SEC_VA + a, SEC_VA + b, blob_where(SEC_VA + a),
                    cur[a:b + 1][:8].hex(" "), BLOB[a:b + 1][:8].hex(" "))
                 for a, b in runs[:6]]
        out.append(".syd contents differ from this build in %d byte(s), %d run(s): %s%s"
                   % (len(bad), len(runs), "; ".join(shown),
                      " ..." if len(runs) > 6 else ""))
    soi = struct.unpack_from("<I", d, pe_info(d)[4])[0]
    if soi != NEW_SOI:
        out.append("SizeOfImage is %#x, expected %#x -- the cave page may be UNMAPPED"
                   % (soi, NEW_SOI))
    if len(d) != SEC_FOFF + SEC_SIZE:
        out.append("EOF is %#x, expected %#x -- something was appended after .syd"
                   % (len(d), SEC_FOFF + SEC_SIZE))
    return out


# ============================================================ mutate
def kill_running():
    # ⚠ SCRATCH GUARD (2026-09-03): AOW_GAME_DIR set => not the real install; never kill
    # the user's running game. See the note in build_minddecay_oos.py.
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
    except Exception as ex:                                   # noqa: BLE001
        print("  (could not run the process kill: %s)" % ex)


def do_apply(d, exe, path):
    st, why = state(d)
    if st == "mixed":
        print("  %s: ABORT -- %s" % (exe, why))
        return None
    e, nsec, _o, sect, soi_off = pe_info(d)

    if st == "vanilla":
        # ⚠ backups/, never the game root -- rule 2026-09-03.
        os.makedirs(BACKUP_DIR, exist_ok=True)
        backup = os.path.join(BACKUP_DIR, os.path.basename(path) + BACKUP_SUFFIX)
        # backup gate: this file is PROVED unpatched by this feature (state() checked
        # nsec/length/gate/hook), so the snapshot is honest. Never taken on a re-tune.
        # It is the POSITIVE `st == "vanilla"` test that licenses it, not the absence of the
        # backup file -- after the 2026-09-09 rename no AoWz.exe.pre-shipyarddisplay can exist.
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
            print("  %s: backup -> %s" % (exe, backup))
        else:
            print("  %s: backup already exists, left alone" % exe)
        assert len(d) == SEC_FOFF
        hdr = struct.pack("<8sIIIIIIHHI", SEC_NAME, SEC_SIZE, SEC_RVA, SEC_SIZE,
                          SEC_FOFF, 0, 0, 0, 0, SEC_CHARS)
        s = sect + 40 * nsec
        assert s + 40 <= struct.unpack_from("<I", d, e + 24 + 60)[0], \
            "no spare section-header slot inside SizeOfHeaders"
        assert all(b == 0 for b in d[s:s + 40]), "section-header slot %#x is not free" % s
        d[s:s + 40] = hdr
        struct.pack_into("<H", d, e + 6, nsec + 1)
        struct.pack_into("<I", d, soi_off, NEW_SOI)
        d.extend(BLOB)
        verb = "applied"
    else:
        # in-place re-tune: .syd is ours exclusively (header already asserted exact), so the
        # whole page is rewritten. Nothing else can own bytes in it.
        prev = bytes(d[SEC_FOFF:SEC_FOFF + SEC_SIZE])
        d[SEC_FOFF:SEC_FOFF + SEC_SIZE] = BLOB
        struct.pack_into("<I", d, soi_off, NEW_SOI)
        verb = "already current" if (prev == BLOB and fully_applied(d)) else "re-tuned in place"

    wr(d, GATE_VA, GATE_NEW)
    wr(d, HOOK_VA, HOOK_PATCH)
    assert len(d) == SEC_FOFF + SEC_SIZE, "unexpected length %#x" % len(d)
    return verb


def do_undo(d, exe):
    st, why = state(d)
    if st == "vanilla":
        print("  %s: already vanilla, nothing to undo" % exe)
        return "nothing to do"
    if st == "mixed":
        print("  %s: ABORT -- %s" % (exe, why))
        return None
    e, nsec, _o, sect, soi_off = pe_info(d)
    # refuse if anything was appended after our section -- truncating would eat it
    if len(d) != SEC_FOFF + SEC_SIZE:
        print("  %s: REFUSING to undo -- EOF %#x != .syd end %#x. Another script appended a "
              "section after ours; remove that one first." % (exe, len(d), SEC_FOFF + SEC_SIZE))
        return None
    s = sect + 40 * (nsec - 1)
    if bytes(d[s:s + 8]).rstrip(b"\0") != SEC_NAME:
        print("  %s: REFUSING to undo -- the LAST section header is %r, not %r"
              % (exe, bytes(d[s:s + 8]).rstrip(b"\0"), SEC_NAME))
        return None
    wr(d, GATE_VA, GATE_OLD)
    wr(d, HOOK_VA, HOOK_ORIG)
    d[s:s + 40] = b"\x00" * 40
    struct.pack_into("<H", d, e + 6, nsec - 1)
    struct.pack_into("<I", d, soi_off, EXP_SOI)
    del d[SEC_FOFF:]
    return "undone"


# ============================================================ driver
def show_dis():
    print("=== .syd @ %08X  (%d bytes used of %#x) ===" % (SEC_VA, len(blob), SEC_SIZE))
    off = LIT_SHIPYARDS - SEC_VA
    rc, ln = struct.unpack_from("<ii", blob, off - 8)
    print("%08X  LIT_SHIPYARDS  refcnt=%d len=%d %r"
          % (LIT_SHIPYARDS, rc, ln, bytes(blob[off:off + ln + 1])))
    for name, va, code in caves:
        print("\n---- %s @ %08X (%d bytes) ----" % (name, va, len(code)))
        for i in cs.disasm(code, va):
            print("  %08X  %-26s %s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str))
    print("\n---- hook @ %08X ----" % HOOK_VA)
    print("  orig %s" % HOOK_ORIG.hex(" "))
    print("  new  %s  (jmp %08X)" % (HOOK_PATCH.hex(" "), CAVE_ROW))
    print("\n---- gate @ %08X ----" % GATE_VA)
    print("  orig %s  call [edx+0x22C] GetBaseIncome" % GATE_OLD.hex(" "))
    print("  new  %s  call [edx+0x1F4] GetIncome" % GATE_NEW.hex(" "))


def _rebuild(name, src):
    """Reassemble ONE cave from modified source at its real VA. -> restore callable."""
    saved = list(caves)
    va = next(v for n, v, _c in saved if n == name)
    caves[:] = [(n, v, c) for n, v, c in saved if n != name]
    caves.append((name, va, bytes(ks.asm(src, va)[0])))
    caves.sort(key=lambda t: t[1])

    def restore():
        caves[:] = saved
    return restore


def selftest():
    """Break each build assertion once, surgically, and confirm THAT guard fires."""
    snapshot = list(caves)
    # G5: MineIncome's literal -1 nil return in place of `xor eax,eax`. Everything else in
    #     cave_sum survives, so G3/G4 still pass and only G5 can fire.
    src5a = SRC_SUM.replace("Lnil:\n    xor eax, eax", "Lnil:\n    mov eax, 1")
    src5b = SRC_SUM.replace("Lnil:\n    xor eax, eax",
                            "Lnil:\n    xor eax, eax\n    mov eax, 0xffffffff")
    assert src5a != SRC_SUM and src5b != SRC_SUM, "selftest G5 source rewrite missed"
    # G6: the keystone imm8 trap -- `push 0xFFFF` assembles to `6A FF` = `push -1`. The
    #     displaced-byte tail and the jmp back are untouched, so G1/G2 still pass.
    src6 = SRC_ROW.replace("Lskip:\n    pop esi",
                           "Lskip:\n    push 0xffff\n    pop eax\n    pop esi")
    assert src6 != SRC_ROW, "selftest G6 source rewrite missed"

    # (fn, label, kwargs, optional cave rebuild). `fn` is build_checks for the offline guards
    # and host_checks for the two that are anchored to the binaries.
    B, H = build_checks, host_checks
    faults = [
        (B, "G1 displaced bytes", dict(hook_orig=b"\x90" * len(HOOK_ORIG)), None),
        (B, "G2 cave jmp target", dict(resume=HOOK_RESUME + 1), None),
        # QA's exact mutation: resume INSIDE the 9 bytes the jump displaces. build_checks
        # cannot see it (both sides move together) -- the host anchor must.
        (H, "G2 resume 4491CE (host)", dict(resume=0x004491CE), None),
        (H, "G2 resume past window", dict(resume=HOOK_RESUME + 2), None),
        (B, "G3 call targets", dict(thunks={T_GETSTRUCT: b"", T_GETPLAYERS: b"",
                                            T_TRANSLATE: b"", 0xDEADBEEF: b""}), None),
        (B, "G4 cave ClassID imm", dict(classid=0x000204BF), None),
        # QA's exact mutation: TMine's ClassID. Only the DLL anchor can reject it.
        (H, "G4 ClassID TMine (host)", dict(classid=0x0002037A), None),
        (B, "G5 nil-map returns 0", dict(), ("cave_sum", src5a)),
        (B, "G5 nil-map returns -1", dict(), ("cave_sum", src5b)),
        (B, "G6 -1 operand trap", dict(), ("cave_row", src6)),
        (B, "G7 AnsiString literal",
         dict(bl=bytearray(BLOB[:LIT_SHIPYARDS - SEC_VA - 8] + struct.pack("<i", 1)
                           + BLOB[LIT_SHIPYARDS - SEC_VA - 4:])), None),
        (B, "G8 hook reaches cave_row",
         dict(hook_patch=b"\xE9\x00\x00\x00\x00\x90\x90\x90\x90"), None),
    ]
    bad = 0
    for fn, name, kw, rebuild in faults:
        restore = _rebuild(*rebuild) if rebuild else (lambda: None)
        try:
            fn(**kw)
            print("  %-26s DID NOT FIRE" % name)
            bad += 1
        except AssertionError as ex:
            msg = str(ex)
            if msg.startswith(name[:2]):
                print("  %-26s fired: %s" % (name, msg[:88]))
            else:
                print("  %-26s fired the WRONG guard: %s" % (name, msg[:88]))
                bad += 1
        restore()
    assert list(caves) == snapshot, "selftest corrupted the caves"
    build_checks()
    host_checks()
    print("  all guards restored, clean build re-verified against the live binaries")
    return bad == 0


def main():
    argv = sys.argv[1:]
    if "--dis" in argv or "--show" in argv:
        show_dis()
        return 0
    if "--selftest" in argv:
        print("=== build-assertion selftest ===")
        return 0 if selftest() else 1

    apply_ = "--apply" in argv
    undo = "--undo" in argv
    if apply_ and undo:
        print("--apply and --undo are mutually exclusive")
        return 2

    before = {f: hashlib.sha256(open(os.path.join(GAME, f), "rb").read()).hexdigest()
              for f in UNRELATED if os.path.exists(os.path.join(GAME, f))}

    print("=== shipyard income DISPLAY (%s + %s) ===" % (EXES[0], EXES[1]))
    print("cave_sum %08X  cave_row %08X  literal %08X  blob %d/%#x bytes"
          % (CAVE_SUM, CAVE_ROW, LIT_SHIPYARDS, len(blob), SEC_SIZE))

    files = {}
    ok = True
    drifted = False
    for exe in EXES:
        path = os.path.join(GAME, exe)
        d = bytearray(open(path, "rb").read())
        st, why = state(d)
        dr = drift(d) if st == "applied" else []
        note = why
        if not note and st == "applied":
            note = "fully applied" if not dr else "DIFFERS from this build in %d place(s)" % len(dr)
        elif not note and st == "vanilla":
            note = "not installed"
        print("  %-14s %-8s %s" % (exe, st, note))
        for line in dr:
            print("      %s" % line)
        if dr:
            drifted = True
        if not check_untouched(d, exe):
            ok = False
        if st == "mixed":
            ok = False
        files[exe] = (path, d)
    if not ok:
        print("\nFAILED pre-checks -- nothing written.")
        return 1

    if not (apply_ or undo):
        if drifted:
            # A verification run must FAIL when what is installed is not what this script
            # builds -- a corrupted or foreign cave must not report success.
            print("\nFAILED -- the installed patch is not byte-identical to this build "
                  "(differences listed above).")
            print("  --apply rewrites the caves in place;  --undo removes the feature.")
            return 1
        print("\nDry run OK. --apply to write, --undo to revert, --dis to read the caves.")
        return 0
    if drifted:
        print("  (the differences above will be %s)"
              % ("rewritten in place" if apply_ else "removed"))

    kill_running()
    results = {}
    for exe, (path, d) in files.items():
        res = do_apply(d, exe, path) if apply_ else do_undo(d, exe)
        if res is None:
            print("\nABORTED -- nothing written for any exe.")
            return 1
        results[exe] = res
    for exe, (path, d) in files.items():
        if results[exe] == "nothing to do":
            continue
        with open(path, "wb") as f:
            f.write(d)
        print("  %-14s %s" % (exe, results[exe]))

    # ---- post-write verification ----
    a = open(os.path.join(GAME, EXES[0]), "rb").read()
    b = open(os.path.join(GAME, EXES[1]), "rb").read()
    good = True
    if len(a) != len(b):
        print("  LOCKSTEP FAIL: lengths %#x vs %#x" % (len(a), len(b)))
        good = False
    else:
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if diff == [LOCKSTEP_BYTE]:
            print("  lockstep OK: exactly one differing byte at %#x (%02X vs %02X)"
                  % (LOCKSTEP_BYTE, a[LOCKSTEP_BYTE], b[LOCKSTEP_BYTE]))
        else:
            print("  LOCKSTEP FAIL: %d differing bytes %s"
                  % (len(diff), [hex(x) for x in diff[:8]]))
            good = False
    for f, sha in before.items():
        now = hashlib.sha256(open(os.path.join(GAME, f), "rb").read()).hexdigest()
        if now != sha:
            print("  %s CHANGED -- this script must never touch it" % f)
            good = False
    if good:
        print("  %s untouched (sha-256 unchanged)" % ", ".join(before))

    for exe in EXES:
        d = bytearray(open(os.path.join(GAME, exe), "rb").read())
        st, _why = state(d)
        want = "applied" if apply_ else "vanilla"
        tag = "OK" if (st == want and (not apply_ or fully_applied(d))) else "UNEXPECTED"
        print("  %-14s post-state %-8s %s" % (exe, st, tag))
        if tag != "OK":
            good = False
        if not check_untouched(d, exe):
            good = False

    print("\n%s" % ("DONE -- applied, UNTESTED." if apply_ and good else
                    "DONE -- reverted." if undo and good else "FINISHED WITH PROBLEMS."))
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
