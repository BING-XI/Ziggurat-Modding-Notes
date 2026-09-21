#!/usr/bin/env python3
r"""
AoW1 map-editor TIMER AUTOSAVE  --  binary patch for Ziggurat\AoWDevEd.exe.

STATUS: SPECULATIVE / NOT APPLIED, and currently NOT APPLICABLE.  `--apply` aborts with
"no PE header room for a new section": AoWDevEd.exe's e_lfanew is 0x100 and its thirteen
section headers end at exactly 0x400, where CODE's raw data begins.  The seven custom
sections already there (.dlgd .mtb .ctp .vgo .pty .tres .nmg) used the room up, so the
`.asv` approach below cannot be taken as written.  Re-home the cave in page slack inside an
existing writable section -- `build_deved_levelnav.py` does exactly that in `.tres` and is
the worked example.

WHAT IT DOES
  Every N minutes (default 5) the editor writes the CURRENT map to a fixed backup
  file (<gamedir>\Save\editor_autosave.hsm) WITHOUT touching the user's real
  filename and WITHOUT clearing the modified/dirty flag -- so the user still sees
  unsaved changes and their own Save target is undisturbed. A crash/hang then
  costs at most N minutes of work.

HOOK  (verified independently per exe)
  TMainForm.HSMEditUpdateFrame -- the editor's per-rendered-frame handler (the
  render loop; ~60/s after the FrameRate patch). We overwrite its 6-byte entry
  prologue  `push ebp; mov ebp,esp; add esp,-0x64`  (55 8B EC 83 C4 9C) with
  `jmp <cave>` (E9) + one NOP. eax = TMainForm at entry (untouched at this point).
  JMP not CALL: nothing pushed, so re-running the prologue keeps the function's own
  `ret` correct (a CALL hook would ret into the body -> crash).
    AoWDevEd.exe : entry 0x00428D18  -> resume 0x00428D1E
  ⚠ `AoWEd.exe` (RETIRED as a target -- see the trap below) carries the byte-identical
  entry at 0x00428CA0 -> resume 0x00428CA6. Kept as reusable RE machinery.

================================================================================
⚠⚠ THE EDITOR EXE TRAP -- an editor patch is TWO steps
================================================================================
`Ziggurat\AoWDevEd.exe` (zigexe.SRC_EDITOR) is the PATCH SOURCE, and nothing runs
it. The editor the owner actually launches is `Ziggurat\AoWzEd.exe`
(zigexe.LIVE_EDITOR), which `build_zigeditor.py` REBUILDS from AoWDevEd.exe. Skip
the second step and the patch sits in a file no one loads -- silently:

    python build_editor_autosave.py --apply    # patches Ziggurat\AoWDevEd.exe
    python build_zigeditor.py       --apply    # rebuilds -> Ziggurat\AoWzEd.exe

(build_zigeditor.py takes --apply / --undo / --png PATH; no args = dry run.)

⚠ `AoWEd.exe` is NO LONGER A TARGET. The 2026-09-09 move left no copy in the overlay
-- only the game root's stock one, which is VANILLA and must never be patched.

⚠⚠ AUTOSAVE_PATH IS BAKED INTO THE CAVE AS AN ABSOLUTE STRING, AND IT IS RESOLVED
FROM `GAME`. On this machine that string contains the owner's profile directory, so
applying this script as written would write a personal path into a binary -- the
exact defect `build_dlgdirs.py` shipped into HSEPack.dpl and AoWDevEd.exe (CLAUDE.md,
"a resolved path must never be BAKED INTO A PATCHED BINARY"). It is also a
correctness bug: a baked path works on one install and fails SILENTLY elsewhere,
because Win32 resolves a bare filename against %WINDIR%. Fix before applying --
derive the directory at run time with GetModuleFileNameA(NULL, buf, MAX_PATH), scan
back to the last '\', append "Save\editor_autosave.hsm". ⭐ Check the exe's own
import table first: the editor binaries already import it with a Delphi thunk, so it
is one `call rel32`.

TIMER  (frame-count based -- fully self-contained, NO imports)
  Neither exe imports GetElapsedMilliSeconds (GFXEPACK exports it but the exe does
  NOT import it) nor GetTickCount/timeGetTime -- verified in the IAT. Rather than
  perform risky import-table surgery or hardcode a rebasing cross-DLL address, the
  cave keeps a 32-bit frame counter in its own data. The handler is the render
  loop, so counting frames is a robust clock with no rollover / first-call edge
  cases. Threshold AUTOSAVE_FRAMES = minutes * 60 * FPS (FPS = the DFM FrameRate,
  60 after build_editor_framerate.py). Change MINUTES / FPS below to retune.
  (SPECULATIVE precision: wall-clock accuracy tracks the actual frame rate; if the
  user sets a different FrameRate, pass --fps to match, else the interval scales.)

GUARDS (skip the save unless it is worth doing)  -- all null-checked:
  HSMEdit  = [TMainForm+0x22c]          ; must be non-null
  [HSMEdit+0x1bc] != 0                   ; "map loaded" flag (Save early-outs on 0)
  HSSet    = [HSMEdit+0x1c0]             ; the THSEngine container; non-null
  THSMap   = [HSSet+0x3c]                ; non-null
  [THSMap+0x3c] & 1                       ; modified/dirty bit (SetModified/ResetModified
                                           OR/AND-NOT a const byte = 0x01 -- verified)

THE SAVE  (identical convention to HSMEdit.THSMEdit.Save @0x55614ED0, verified)
  push 0                 ; callback DATA  ([ebp+0xc] in SaveHSM -> stream+0x20)
  push 0                 ; callback CODE  ([ebp+0x8] -> stream+0x1c)  == NIL
  mov  edx, <lit+8>      ; filename AnsiString ptr (our const literal, NOT +0x1e4)
  mov  eax, HSSet
  mov  ecx, [eax]        ; HSSet vmt
  call [ecx+0xAC]        ; THSEngine.SaveHSM  (VMT slot verified = 0x5561043C)
  We do NOT call THSMap.ResetModified afterwards, so the dirty flag persists.

  NIL CALLBACK IS SAFE (verified): SaveHSM forwards the 2 stack params to
  TEngine.WriteEObject, which stores them at stream+0x1c (code) / +0x20 (data).
  Engine.TEStorageStream.ShowProgress @0x5550FF58 guards with
  `cmp word ptr [stream+0x1e],0 / je skip` -- i.e. it tests the HIGH WORD of the
  code pointer. A NIL (0) code pointer => guard skips the call entirely.

ANSISTRING LITERAL  (Delphi 3 const layout, verified against exe literals like
  0x404EE4 'Index', 0x407B84 'Change Terrain'):
     [lit+0] = FF FF FF FF   (refcount -1 => immutable, never freed)
     [lit+4] = <length:dword>
     [lit+8] = <chars...> 00  (NUL-terminated)
  We pass edx = lit+8. Immutable refcount means no LStrClr/LStrAsg needed and the
  callee cannot free or realloc it.

CAVE placement: new PE section ".asv" appended to each exe (fixed base 0x400000,
so absolute data refs inside the cave are fine). Keystone-assembled, capstone
dumped below for review.

CONVENTIONS: dry-run by default; --apply to write; idempotent (re-run verifies);
verify-before-write aborts on any byte mismatch; auto-backup to
<game dir>\backups\<exe>.pre-autosave.
The editor locks its own exe; close it before --apply.

REVERT: this script has NO revert flag, and there is no snapshot layer to fall back
on -- both `.pre-*` stacks were purged (2026-08-08 and 2026-09-03) and nothing has
rebuilt them, so any `.pre-autosave` on disk is at most one disposable copy of that
day's file. Undo it surgically: restore the 6 entry bytes at the hook and drop the
`.asv` section (it shares no cave with any other feature).

Usage:
  python build_editor_autosave.py                 # dry-run
  python build_editor_autosave.py --apply         # patch
  python build_editor_autosave.py --minutes 10    # retune interval
  python build_editor_autosave.py --fps 30        # match a non-default FrameRate
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

import zigexe

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
IB   = 0x00400000
BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP_SUFFIX = ".pre-autosave"

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

# ---- feature constants -------------------------------------------------------
DEFAULT_MINUTES = 5
DEFAULT_FPS     = 60          # DFM FrameRate after build_editor_framerate.py

# ⚠⚠ BAKED INTO THE CAVE AS AN ABSOLUTE STRING -- see the docstring. On this machine it
# resolves to a path under the owner's profile directory, which must never end up inside a
# patched binary, and which would not survive being shared. Derive it at run time instead
# (GetModuleFileNameA) before this script is ever applied.
AUTOSAVE_PATH = os.path.join(GAME, "Save", "editor_autosave.hsm")

# ---- HSEPack.dpl object-layout facts (verified statically) -------------------
OFF_HSMEDIT   = 0x22c   # [TMainForm+0x22c]  -> THSMEdit
OFF_HSSET     = 0x1c0   # [THSMEdit+0x1c0]   -> THSEngine (HSSet)
OFF_LOADED    = 0x1bc   # [THSMEdit+0x1bc]   -> byte "map loaded" flag
OFF_MAP       = 0x3c    # [HSSet+0x3c]       -> THSMap
OFF_MODIFIED  = 0x3c    # [THSMap+0x3c]      -> flags byte; bit0 = modified
MODIFIED_BIT  = 0x01
SAVE_VMT_SLOT = 0xAC    # [ [HSSet]+0xAC ]   -> THSEngine.SaveHSM

# ---- per-exe hook facts (verified independently) -----------------------------
# entry prologue overwritten (both identical): push ebp; mov ebp,esp; add esp,-0x64
ENTRY_ORIG = bytes.fromhex("55 8b ec 83 c4 9c".replace(" ", ""))
# ⚠ ONE target. AoWEd.exe was the second (entry 0x00428CA0) and is retired -- see the trap in
# the docstring, which keeps its address.
TARGETS = {
    zigexe.SRC_EDITOR: dict(entry=0x00428D18),
}
# resume = entry + len(ENTRY_ORIG); the displaced prologue is re-run in the cave.

# ---- PE helpers (add-section pattern, from build_spellcast_card_v2) ----------
def load_sections(d):
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e+6)[0]
    optsz = struct.unpack_from('<H', d, e+20)[0]
    opt = e+24
    sectbl = opt+optsz
    secs = []
    for i in range(nsec):
        b = sectbl+i*40
        vsz, va, rsz, raw = struct.unpack_from('<IIII', d, b+8)
        secs.append((va, vsz, raw, rsz, b))
    return dict(e=e, nsec=nsec, opt=opt,
                salign=struct.unpack_from('<I', d, opt+32)[0],
                falign=struct.unpack_from('<I', d, opt+36)[0],
                sectbl=sectbl, secs=secs)

def align(x, a): return (x + a - 1) // a * a

def va2off(secs, va):
    r = va - IB
    for va0, vsz, raw, rsz, _ in secs:
        if va0 <= r < va0 + max(vsz, rsz):
            return raw + (r - va0)
    raise ValueError(hex(va))

def rel32(src, dst): return struct.pack('<i', dst - (src + 5))

# ---- build one exe's cave + patch plan --------------------------------------
def build_cave(cave_va, entry_va, frames):
    """Return (cave_bytes, ansistr_offset_in_cave, ctr_offset_in_cave, dump_str).

    Cave layout:  [code][32-byte-aligned data: frame_ctr dword][AnsiString literal]
    The literal's char pointer (lit+8) is what SaveHSM receives in edx.
    """
    resume_va = entry_va + len(ENTRY_ORIG)

    # We need absolute VAs for the two data items, but their offsets depend on the
    # code length. Assemble the code once with placeholder absolute addresses, then
    # fix up. Simpler: assemble code referencing symbolic absolute constants we
    # compute up front by laying data at a FIXED offset region *after* a code area
    # whose max size we bound. To stay exact, we assemble twice.
    def asm_code(ctr_va, str_va):
        src = f"""
            /* --- frame timer --- */
            inc     dword ptr [0x{ctr_va:08X}]
            cmp     dword ptr [0x{ctr_va:08X}], {frames}
            jb      _done
            mov     dword ptr [0x{ctr_va:08X}], 0
            /* --- guards (eax = TMainForm at cave entry) --- */
            mov     ecx, dword ptr [eax+0x{OFF_HSMEDIT:X}]   /* HSMEdit */
            test    ecx, ecx
            jz      _done
            cmp     byte ptr [ecx+0x{OFF_LOADED:X}], 0        /* map loaded? */
            jz      _done
            mov     edx, dword ptr [ecx+0x{OFF_HSSET:X}]      /* HSSet */
            test    edx, edx
            jz      _done
            mov     ecx, dword ptr [edx+0x{OFF_MAP:X}]        /* THSMap */
            test    ecx, ecx
            jz      _done
            test    byte ptr [ecx+0x{OFF_MODIFIED:X}], {MODIFIED_BIT}  /* modified? */
            jz      _done
            /* --- do the save (edx still = HSSet); preserve eax=Self across call --- */
            push    eax                                        /* SAVE Self (TMainForm) */
            push    0                                          /* callback data */
            push    0                                          /* callback code (NIL) */
            mov     eax, edx                                   /* eax = HSSet */
            mov     edx, 0x{str_va:08X}                        /* edx = filename AnsiString ptr */
            mov     ecx, dword ptr [eax]                       /* HSSet vmt */
            call    dword ptr [ecx+0x{SAVE_VMT_SLOT:X}]        /* THSEngine.SaveHSM (ret 8) */
            pop     eax                                        /* RESTORE Self */
        _done:
            /* restore original entry prologue, then resume */
            push    ebp
            mov     ebp, esp
            add     esp, -0x64
            jmp     0x{resume_va:08X}
        """
        # NOTE (corrected during review): the hook is a JMP, so nothing is on the
        # stack at cave entry beyond the caller's frame; re-running the prologue
        # therefore builds a correct frame ([ebp+4] = real caller retaddr).
        # EAX is preserved across the save because the resumed body does
        # `mov ebx,eax` at 0x428D2F using eax as Self BEFORE reloading it; the save
        # path push/pop's eax around SaveHSM. ecx/edx ARE dead there (the body
        # reloads them), so we let them be clobbered. Stack balance on the save
        # path: push eax + (SaveHSM `ret 8` @0x5561051D cleans the 2 zero args) +
        # pop eax = net zero; SaveHSM (Delphi ABI) preserves ebx/esi/edi.
        code, _ = ks.asm(src, cave_va)
        return bytes(code)

    # Stack balance: SaveHSM @0x5561043C epilogue is `pop esi/ebx/ebp; ret 8`
    # (@0x5561051D) -> the 2 callback dwords we push are cleaned by the callee.
    # (A runtime subclass override of vmt+0xAC must keep the same `ret 8` ABI --
    # see design-doc apply-time checklist.)

    # First pass with dummy data VAs to measure code length.
    code0 = asm_code(0x11111111, 0x22222222)
    code_len = len(code0)
    data_start = align(code_len, 4)                 # dword-align the counter
    ctr_off = data_start                            # frame counter dword
    lit_off = ctr_off + 4                           # AnsiString literal
    str_off = lit_off + 8                           # char pointer (lit+8)
    ctr_va = cave_va + ctr_off
    str_va = cave_va + str_off
    # Re-assemble with real absolute VAs (lengths are identical: all refs are
    # abs32 imm/disp, size-invariant to the address value).
    code = asm_code(ctr_va, str_va)
    assert len(code) == code_len, "code length changed after VA fixup"

    # data blob: [pad to data_start][ctr dword=0][ansistring literal]
    path_bytes = AUTOSAVE_PATH.encode("latin1")
    literal = struct.pack("<iI", -1, len(path_bytes)) + path_bytes + b"\x00"
    blob = bytearray(code)
    blob += b"\x00" * (data_start - len(blob))      # pad to counter
    blob += struct.pack("<I", 0)                    # frame counter
    blob += literal                                 # refcount,-1 | len | chars | NUL

    dump = []
    dump.append(f"    cave @ {cave_va:08X}  code {code_len}B  ctr@{ctr_va:08X}  "
                f"str@{str_va:08X}  ('{AUTOSAVE_PATH}')")
    for ins in cs.disasm(code, cave_va):
        dump.append(f"    {ins.address:08X}  {ins.bytes.hex(' '):<24}{ins.mnemonic} {ins.op_str}")
    return bytes(blob), str_va, ctr_va, "\n".join(dump)

# ---- process one exe ---------------------------------------------------------
def process(exe_name, minutes, fps, apply):
    path = os.path.join(GAME, exe_name)
    if not os.path.exists(path):
        print(f"[{exe_name}] MISSING - skipped")
        return True
    frames = minutes * 60 * fps
    d = bytearray(open(path, "rb").read())
    F = load_sections(d)
    secs = F["secs"]

    # idempotency: our section marker present?
    already = any(bytes(d[s[4]:s[4]+4]) == b".asv" for s in secs)
    entry = TARGETS[exe_name]["entry"]
    eoff = va2off(secs, entry)
    cur_entry = bytes(d[eoff:eoff+len(ENTRY_ORIG)])
    hooked = cur_entry[:1] == b"\xE9"

    if already or hooked:
        print(f"[{exe_name}] already patched (.asv section / hook present) - idempotent no-op")
        return True

    # compute new section VA/raw
    newva = align(max(s[0] + max(s[1], s[3]) for s in secs), F["salign"])
    newraw = align(len(d), F["falign"])
    cave_va = IB + newva

    blob, str_va, ctr_va, dump = build_cave(cave_va, entry, frames)

    print(f"[{exe_name}]  entry 0x{entry:08X} -> resume 0x{entry+len(ENTRY_ORIG):08X}  "
          f"| interval {minutes} min @ {fps} fps = {frames} frames")
    print(dump)

    # verify the entry bytes are the pristine prologue
    if cur_entry != ENTRY_ORIG:
        print(f"[{exe_name}] ABORT: entry bytes not the expected prologue\n"
              f"     exp {ENTRY_ORIG.hex(' ')}\n     got {cur_entry.hex(' ')}")
        return False
    # header room for one more section descriptor
    if F["sectbl"] + F["nsec"]*40 + 40 > secs[0][2]:
        print(f"[{exe_name}] ABORT: no PE header room for a new section")
        return False
    print(f"[{exe_name}] entry prologue verified; header room OK")

    if not apply:
        print(f"[{exe_name}] dry-run OK")
        return True

    # Snapshot goes in <game dir>\backups\, never beside the binary (CLAUDE.md 2026-09-03).
    # We reach here only when the entry bytes were verified to be the pristine prologue and no
    # .asv section exists, so the file is PROVED unpatched with respect to this feature.
    backup = os.path.join(BACKUP_DIR, exe_name + BACKUP_SUFFIX)
    if not os.path.exists(backup):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, backup)
        print(f"[{exe_name}] backup -> {backup}")

    # append section raw data
    if len(d) < newraw:
        d += b"\x00" * (newraw - len(d))
    rawsz = align(len(blob), F["falign"])
    d += blob + b"\x00" * (rawsz - len(blob))
    # new section header
    b = F["sectbl"] + F["nsec"]*40
    struct.pack_into("<8sIIII", d, b, b".asv\0\0\0\0", len(blob), newva, rawsz, newraw)
    struct.pack_into("<IIHHI", d, b+24, 0, 0, 0, 0, 0x60000020)  # code|exec|read
    struct.pack_into("<H", d, F["e"]+6, F["nsec"]+1)             # NumberOfSections
    struct.pack_into("<I", d, F["opt"]+56,
                     align(newva + len(blob), F["salign"]))       # SizeOfImage
    # patch the hook: jmp <cave> + nop  (JMP, not CALL -- see cave NOTE)
    patch = b"\xE9" + rel32(entry, cave_va) + b"\x90"
    assert len(patch) == len(ENTRY_ORIG)
    d[eoff:eoff+len(patch)] = patch

    try:
        open(path, "wb").write(d)
    except PermissionError:
        print(f"[{exe_name}] LOCKED - close the editor and retry")
        return False
    print(f"[{exe_name}] written: hook + .asv cave. Revert SURGICALLY -- restore the 6 entry "
          f"bytes and drop the .asv section; do not restore a snapshot over the file.")
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exe", nargs="?", help="restrict to one exe (default: every target)")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--minutes", type=int, default=DEFAULT_MINUTES, help="autosave interval (min)")
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS, help="assumed FrameRate for frame->time")
    args = ap.parse_args()
    if not (1 <= args.minutes <= 120):
        sys.exit("--minutes out of range (1..120)")
    if not (2 <= args.fps <= 240):
        sys.exit("--fps out of range (2..240)")

    which = [args.exe] if args.exe else list(TARGETS.keys())
    for e in which:
        if e not in TARGETS:
            print(f"[{e}] unknown exe - skipped"); continue

    allok = True
    print(f"AoW1 editor autosave  |  interval {args.minutes} min @ {args.fps} fps\n")
    for e in which:
        if e in TARGETS:
            allok &= process(e, args.minutes, args.fps, args.apply)
            print()
    if not args.apply:
        print("[dry-run] Re-run with --apply to write. Close the editor first.")
    elif allok:
        print("[done] Applied to the PATCH SOURCE. Now run:  python build_zigeditor.py --apply\n"
              "       (rebuilds Ziggurat\\AoWzEd.exe, the editor that actually runs).\n"
              "       Revert is surgical: restore the 6 entry bytes, drop the .asv section.")
    else:
        print("[!] One or more exes not fully applied - see above.")

main()
