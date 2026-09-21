#!/usr/bin/env python3
r"""
AoWSetup INSTALL-CHECK FALLBACK  --  AoWSetup.exe ONLY.

WHAT IT FIXES
  AoWSetup decides whether the game is installed by reading a registry string and
  testing that the file it names exists:

      TLoaderForm.IsInstalled @0x00468618
        call GetRootDirectory                    ; -> [ebp-4]
        cmp  dword [ebp-4], 0 ; je -> NOT INSTALLED
        call GetRootDirectory                    ; -> [ebp-8]
        LStrCat([ebp-8], '\aow.exe' @0x004686A0)
        FileExists @0x00407194 -> bl

  When that string comes back empty the home screen collapses to Install/Exit --
  no Play!, no Settings, no Editor.  This patch gives the getter a fallback of '.'
  so the check becomes FileExists('.\aow.exe'), which is true whenever AoWSetup is
  run from the game folder.  The install check then does not depend on the registry
  at all.

WHY IT IS NEEDED HERE
  `build_regiso.py` moves the settings tree to ...\Age of Wonders Z.  Applying it
  reproduced exactly this symptom.  ⚠ **The mechanism was never pinned down.**  Ruled
  out by measurement, all of it: the patched constant is well-formed (refcount -1,
  len 43, NUL present); `Root Directory` and `General` are intact; the value reads
  correctly out of the Z tree; `aow.exe` exists where it points; no RUNASADMIN layer;
  and launching AoWSetup creates no unexpected key, so TRegistry.OpenKey on the Z
  path succeeds.  By the disassembly the check should pass, and it did not.

  This patch is therefore a **fallback, not a diagnosis**.  It is worth having on its
  own terms -- it removes a registry dependency from a check that only ever needed to
  answer "are the game files next to me?" -- but if AoWSetup still shows Install/Exit
  after this, the cause is upstream of the getter and the hunt is still open.

  Inioch shipped the identical fix on 2026-08-13 after the same symptom bit a player
  of AoWx (`Inioch/share6/memory/aowsetup-installcheck-devtab.md`).  His cause was
  different and understood: a *fresh* AoWx install has no isolated tree yet, so the
  read genuinely returns nil.  Ours should not.  Same remedy either way.

MECHANISM -- a call-rel32 retarget, the project's cheapest hook
  GetRootDirectory @0x00467584 ends:

      push esi                  ; @result
      push 0                    ; mode 0 = read
      mov  ecx, 0x004675B0      ; 'Root Directory'
      mov  edx, 0x004675C8      ; 'General'
      mov  eax, ebx             ; the registry object
      call 0x0046719C   <<-- retargeted; 4 bytes of operand, nothing displaced
      pop  esi / pop ebx / ret

  0x0046719C is **ret 8** (verified: epilogue at 0x0046725D), so the cave has to
  re-push both arguments and clean them itself.  Stack on cave entry is
  [esp]=return, [esp+4]=mode, [esp+8]=@result; after the two pushes the helper sees
  its own [ebp+8]=mode / [ebp+0xC]=@result, and its `ret 8` restores the frame.

  eax is clobbered deliberately: neither GetRootDirectory nor either of its callers
  (0x00468636, 0x00468A70) uses the return value -- both read the out-parameter.

  ⚠ Storing straight into the out-var is only safe because it is NIL at that point
  (the cave tests for exactly that).  The '.' image is a refcount -1 Delphi literal,
  so the later LStrCat allocates a fresh string instead of mutating it, and LStrClr
  skips it.  No RTL call is needed to assign it.

CAVE -- re-derived on OUR binary, not reused from his
  His allocation was 0x004698E0 / 0x004698EC.  Standing rule 2 (`Zig notes/Inioch.md`
  §1): his addresses are reliable, his allocations are not.  Independently measured
  here: CODE VirtualSize 0x6880C ends at VA 0x0046980C, SizeOfRawData 0x68A00 runs to
  VA 0x00469A00 -> 500 bytes of tail, verified all-zero, section characteristics
  0x60000020 = CODE|EXECUTE|READ.

      0x0046980C  10 B   '.' as a Delphi AnsiString image (chars at 0x00469814)
      0x00469820  27 B   the cave body
      next free: 0x00469840

  ⚠ **R-X, not writable** -- code and read-only constants only.  This cave holds no
  mutable state, which is why it fits.
  CODE VirtualSize is bumped 0x6880C -> 0x68A00 so the cave sits formally inside the
  section (it is in the already-mapped 0x469000 page either way; this is hygiene).
  DATA starts at VA 0x0046A000, so nothing overlaps.  SizeOfImage is unchanged.
  DllCharacteristics is 0x0000 -- no DYNAMIC_BASE -- so absolute addresses are legal
  in this binary.

KNOWN LIMIT
  '.' is relative to the process working directory.  Launched from the game folder
  (Explorer, or a shortcut whose "Start in" is the game folder) it resolves; launched
  with some other working directory it does not, and the check falls back to the
  registry answer as before.  Deriving the real directory via GetModuleFileNameA
  would be robust, but it needs a writable buffer and this section is R-X -- BSS has
  only ~5 bytes free past [0x0046BA34].  Not worth a new section for a fallback path.

STATUS: applied 2026-09-09, UNTESTED.  Needs the in-game check in
`Zig notes/11-engine-internals.md`.

Needs no third-party packages to apply; `--dis` wants capstone.
"""
import argparse
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")
EXE = "AoWSetup.exe"
BACKUP = os.path.join(BACKUP_DIR, EXE + ".pre-setupcheck")

BASE = 0x400000
CODE_VA = 0x00401000
CODE_RAW = 0x400

HOOK_VA = 0x004675A0          # the `call 0x0046719C` inside GetRootDirectory
HELPER_VA = 0x0046719C        # the registry rw helper, ret 8
ORIG_CALL = bytes.fromhex("e8f7fbffff")

DOT_HDR_VA = 0x0046980C       # [-1][1]['.'][NUL]
DOT_CHARS_VA = 0x00469814
CAVE_VA = 0x00469820
CAVE_END_VA = 0x00469840      # next free

CODE_HDR_OFF = 0x1F8          # CODE section header
VSIZE_OLD = 0x0006880C
VSIZE_NEW = 0x00068A00


def v2f(va):
    return va - CODE_VA + CODE_RAW


def dot_image():
    return struct.pack("<iI", -1, 1) + b".\x00"


def cave_body():
    """See MECHANISM. Hand-assembled; --dis prints it back through capstone."""
    b = bytearray()
    b += bytes.fromhex("ff742408")                    # push dword [esp+8]   @result
    b += bytes.fromhex("ff742408")                    # push dword [esp+8]   mode
    call_site = CAVE_VA + len(b)
    b += b"\xe8" + struct.pack("<i", HELPER_VA - (call_site + 5))
    b += bytes.fromhex("8b442408")                    # mov eax,[esp+8]      @result
    b += bytes.fromhex("833800")                      # cmp dword [eax],0
    b += bytes.fromhex("7506")                        # jne +6  -> ret
    b += b"\xc7\x00" + struct.pack("<I", DOT_CHARS_VA)  # mov dword [eax],'.'
    b += bytes.fromhex("c20800")                      # ret 8
    return bytes(b)


def state(d):
    """(patched, sane) -- sane means the bytes are one of the two known states."""
    cur = bytes(d[v2f(HOOK_VA):v2f(HOOK_VA) + 5])
    want = b"\xe8" + struct.pack("<i", CAVE_VA - (HOOK_VA + 5))
    if cur == ORIG_CALL:
        return False, True
    if cur == want:
        return True, True
    print("  !! hook site 0x%08X holds %s -- neither vanilla nor ours" % (HOOK_VA, cur.hex()))
    return None, False


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true", help="surgical revert")
    ap.add_argument("--dis", action="store_true", help="disassemble the cave")
    args = ap.parse_args()
    if args.apply and args.undo:
        ap.error("--apply and --undo are mutually exclusive")

    path = os.path.join(GAME, EXE)
    d = bytearray(open(path, "rb").read())
    patched, sane = state(d)
    if not sane:
        sys.exit(2)

    body = cave_body()
    dot = dot_image()
    assert CAVE_VA + len(body) <= CAVE_END_VA, "cave body overruns its allocation"

    vs = struct.unpack_from("<I", d, CODE_HDR_OFF + 8)[0]
    print("%s: hook %s, CODE VirtualSize 0x%X" % (EXE, "PATCHED" if patched else "vanilla", vs))

    if args.dis:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        except ImportError:
            sys.exit("--dis needs capstone")
        print("\ncave @0x%08X (%d B), '.' image @0x%08X chars 0x%08X"
              % (CAVE_VA, len(body), DOT_HDR_VA, DOT_CHARS_VA))
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(body, CAVE_VA):
            print("  %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
        print("  hook: 0x%08X  e8 %s  -> 0x%08X"
              % (HOOK_VA, struct.pack("<i", CAVE_VA - (HOOK_VA + 5)).hex(), CAVE_VA))

    want_patched = not args.undo
    if patched == want_patched:
        print("\nnothing to do -- already in the requested state.")
        return
    if not (args.apply or args.undo):
        print("\ndry run.  Re-run with --apply (or --undo) to write.")
        return

    # the growth zone must still be zero before we claim it
    if want_patched:
        zone = d[v2f(DOT_HDR_VA):v2f(CAVE_END_VA)]
        if set(zone) != {0}:
            print("  !! 0x%08X..0x%08X is not zero -- someone else owns this slack"
                  % (DOT_HDR_VA, CAVE_END_VA))
            sys.exit(2)

    import subprocess
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-Process | Where-Object { $_.ProcessName -match "
                    "'^(AoW|AoWCompat|AoWDevEd|AoWEd|AoWSetup)$' } | Stop-Process -Force"],
                   capture_output=True)

    if want_patched:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        if not os.path.exists(BACKUP):
            shutil.copyfile(path, BACKUP)
            print("  backup -> backups\\%s" % os.path.basename(BACKUP))
        d[v2f(DOT_HDR_VA):v2f(DOT_HDR_VA) + len(dot)] = dot
        d[v2f(CAVE_VA):v2f(CAVE_VA) + len(body)] = body
        d[v2f(HOOK_VA):v2f(HOOK_VA) + 5] = b"\xe8" + struct.pack("<i", CAVE_VA - (HOOK_VA + 5))
        struct.pack_into("<I", d, CODE_HDR_OFF + 8, VSIZE_NEW)
        print("  cave written, hook retargeted, CODE VirtualSize 0x%X -> 0x%X" % (vs, VSIZE_NEW))
    else:
        d[v2f(HOOK_VA):v2f(HOOK_VA) + 5] = ORIG_CALL
        d[v2f(DOT_HDR_VA):v2f(CAVE_END_VA)] = b"\x00" * (CAVE_END_VA - DOT_HDR_VA)
        struct.pack_into("<I", d, CODE_HDR_OFF + 8, VSIZE_OLD)
        print("  hook restored, cave zeroed, CODE VirtualSize 0x%X -> 0x%X" % (vs, VSIZE_OLD))

    open(path, "wb").write(d)

    d2 = bytearray(open(path, "rb").read())
    p2, s2 = state(d2)
    print("  verify: hook %s, CODE VirtualSize 0x%X"
          % ("PATCHED" if p2 else "vanilla", struct.unpack_from("<I", d2, CODE_HDR_OFF + 8)[0]))


if __name__ == "__main__":
    main()
