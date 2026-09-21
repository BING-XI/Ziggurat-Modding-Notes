#!/usr/bin/env python3
r"""
EDITOR RESPONSIVENESS: raise the process timer resolution  --  AoWDevEd.exe only.

THE PROBLEM (measured 2026-07-28, see Editor_Frame_Cost_Analysis.md)
  The editor's frame loop calls Sleep(1) TWICE per frame:
      HSEPack.dpl!HSMEdit.THSMEdit.UpdateFrame +0x9   (push 1 / call Sleep)
      AoWDevEd.exe!TMainForm.HSMEditUpdateFrame +0x29 (push 1 / call Sleep)
  No AoW module ever calls timeBeginPeriod, so the process runs at Windows' DEFAULT timer
  granularity of 15.625 ms and each Sleep(1) actually sleeps ~15.6 ms. Two of them =
  31.25 ms per frame, and because the render loop paces the whole message pump, the editor
  services its message queue only ~32x/second. A UI-thread profile with stack attribution
  shows 76% of the thread's time inside those two sleeps and only ~5% doing real work.

  This is also why raising the map view's DFM FrameRate stopped helping: FrameRate cannot
  pace below the Sleep floor. It is already 120 on this install and buys nothing.

THE FIX
  Call timeBeginPeriod(1) once, so Sleep(1) really is ~1 ms. Proven live before writing this
  script by injecting the call into the running editor with CreateRemoteThread: the pump
  period dropped 31.5 ms -> 8.0 ms immediately, with nothing else changed.

HOW
  * Hook the exe's kernel32 Sleep import THUNK at 0x4013C8
    (`jmp dword ptr [0x4322A0]`, ff25a0224300) -> `jmp cave` + nop. The cave does the
    one-time init on the first Sleep call (guaranteed to be the first frame) and then tail-
    jumps to the real Sleep with the caller's stack untouched. No startup hook needed and
    every later call costs one compare.
  * AoWDevEd.exe imports neither LoadLibraryA nor GetProcAddress, so the cave reaches them
    through VCL30.dpl's IAT -- the same trick build_dlgdirs.py uses for the profile APIs:
        vcl_delta      = [0x432210] - 0x41336300     (exe's IAT slot for
                         Forms.TCustomForm.Create, whose preferred VA is VCL30 base+0x36300)
        LoadLibraryA   = [0x413E4360 + vcl_delta]
        GetProcAddress = [0x413E43B4 + vcl_delta]
    then LoadLibraryA("winmm.dll") / GetProcAddress("timeBeginPeriod") / call with 1.
    Deliberately NOT derived from winmm's own export RVAs (GFXEPACK imports timeGetTime, so
    winmm's base is reachable) -- those RVAs change with every Windows update and would turn
    a servicing update into a crash.

  Windows drops the request automatically when the process exits, so no timeEndPeriod is
  needed. Cost is the usual 1 ms system timer tick; the machine this was measured on was
  already at 1 ms because other applications request it.

CONVENTIONS: dry-run by default (prints a capstone disassembly), --apply to write;
idempotent; verify-before-write (aborts unless the thunk is exactly vanilla or exactly ours);
auto-backup to `<game dir>\backups\AoWDevEd.exe.pre-timerres`. Editor-only. Close AoWDevEd.exe first.
Revert: there is no --undo here, and copying the snapshot back is NOT a revert path -- it is a
WHOLE-FILE copy, so it drops every other AoWDevEd feature applied since. Undo surgically: restore
the 6 thunk bytes at THUNK_VA and zero .tres.
⚠ `--sleep 1` is only safe while build_editor_rendergate.py's gate is installed -- restore --sleep 8
if that gate is taken out.

Needs: pip install keystone-engine capstone
"""
import argparse, os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXE = "AoWDevEd.exe"
BACKUP_SUFFIX = ".pre-timerres"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)
SECT_NAME = b".tres\0\0\0"

THUNK_VA = 0x4013C8                     # jmp dword ptr [Sleep IAT]
IAT_SLEEP = 0x4322A0
ORIG_THUNK = b"\xFF\x25" + struct.pack("<I", IAT_SLEEP)

# VCL30 anchor: the exe's IAT slot for Forms.TCustomForm.Create, preferred VA base+0x36300
VCL_BASE = 0x41300000
IAT_TCUSTOMFORM_CREATE = 0x432210
VCL_CREATE_PREF = VCL_BASE + 0x36300
VCL_IAT_LOADLIBRARYA = 0x413E4360
VCL_IAT_GETPROCADDRESS = 0x413E43B4

TARGET_MS = 1                           # timeBeginPeriod argument

# With a 1 ms timer, Sleep(1) really is ~1 ms, so the frame loop free-runs: measured pump 8 ms
# but ~55% of a core at idle (the loop then blits the map ~125x/second for nothing). The frame
# budget therefore has to be put back by hand. Per-frame work is ~4 ms, so idle CPU is roughly
# work/period. Measured in one process by toggling the timer at runtime:
#     stock (15.6 ms timer)      pump 31.0 ms   CPU 13.6%
#     1 ms timer, Sleep(1)       pump  8.1 ms   CPU 55%
# Patching the exe's own Sleep argument sets the period without giving up the accurate timer.
# push 1 -> push N at TMainForm.HSMEditUpdateFrame+0x29; HSEPack's own Sleep(1) still adds ~1 ms.
SLEEP_ARG_VA = 0x428D40                 # the imm8 of `push 1` at 0x428D3F
DEFAULT_SLEEP = 1                       # ONLY safe with build_editor_rendergate.py installed:
                                        # the gate's skip_sleep paces the loop. Without the gate
                                        # use 8, or the frame loop free-runs at ~117 fps.


def asm_src(ks, src, va):
    """keystone (LLVM) has no ';' comments in Intel mode -- strip them first."""
    clean = "\n".join(ln.split(";", 1)[0] for ln in src.splitlines())
    code, _ = ks.asm(clean, va)
    return bytes(code)


def gen(base_va):
    off = 0
    g_done = base_va + off; off += 4
    s_winmm = base_va + off
    winmm_b = b"winmm.dll\0"
    off += len(winmm_b)
    s_tbp = base_va + off
    tbp_b = b"timeBeginPeriod\0"
    off += len(tbp_b)
    off = (off + 15) & ~15
    code_va = base_va + off

    src = f"""
hook:
        cmp  dword ptr [{g_done:#x}], 0
        jne  ht_tail
        mov  dword ptr [{g_done:#x}], 1
        pushad

        mov  eax, dword ptr [{IAT_TCUSTOMFORM_CREATE:#x}]   ; vcl_delta
        sub  eax, {VCL_CREATE_PREF:#x}
        mov  ebx, eax

        mov  eax, dword ptr [ebx + {VCL_IAT_LOADLIBRARYA:#x}]
        test eax, eax
        jz   ht_pop
        mov  edi, dword ptr [ebx + {VCL_IAT_GETPROCADDRESS:#x}]
        test edi, edi
        jz   ht_pop

        push {s_winmm:#x}                                   ; LoadLibraryA("winmm.dll")
        call eax
        test eax, eax
        jz   ht_pop

        push {s_tbp:#x}                                     ; GetProcAddress(h,"timeBeginPeriod")
        push eax
        call edi
        test eax, eax
        jz   ht_pop

        push {TARGET_MS}                                    ; timeBeginPeriod(1)
        call eax

    ht_pop:
        popad
    ht_tail:
        jmp  dword ptr [{IAT_SLEEP:#x}]
"""
    return src, dict(base=base_va, code=code_va, g_done=g_done, s_winmm=s_winmm,
                     s_tbp=s_tbp, winmm_b=winmm_b, tbp_b=tbp_b, data_len=code_va - base_va)


def load_sections(d):
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e + 6)[0]
    optsz = struct.unpack_from('<H', d, e + 20)[0]
    opt = e + 24
    sectbl = opt + optsz
    secs = []
    for i in range(nsec):
        b = sectbl + i * 40
        vsz, va, rsz, raw = struct.unpack_from('<IIII', d, b + 8)
        secs.append((va, vsz, raw, rsz, b))
    return dict(e=e, nsec=nsec, opt=opt, sectbl=sectbl, secs=secs,
                salign=struct.unpack_from('<I', d, opt + 32)[0],
                falign=struct.unpack_from('<I', d, opt + 36)[0],
                hdrsz=struct.unpack_from('<I', d, opt + 84)[0])


def align(x, a): return (x + a - 1) // a * a


def rva2off(secs, rva):
    for va0, vsz, raw, rsz, _ in secs:
        if va0 <= rva < va0 + max(vsz, rsz):
            return raw + (rva - va0)
    raise ValueError(hex(rva))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sleep", type=int, default=DEFAULT_SLEEP,
                    help="ms the editor's frame loop sleeps (1..60). Lower = more responsive and "
                         "more idle CPU; 1 free-runs at ~55%% of a core, the default 8 gives "
                         "~13 ms pump for ~30%%, stock behaviour is ~31 ms for ~14%%.")
    args = ap.parse_args()
    if not (1 <= args.sleep <= 60):
        sys.exit("--sleep out of range (1..60)")

    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    path = os.path.join(GAME, EXE)
    d = bytearray(open(path, "rb").read())
    F = load_sections(d)

    th_off = rva2off(F["secs"], THUNK_VA - 0x400000)
    th_now = bytes(d[th_off:th_off + 6])
    sl_off = rva2off(F["secs"], SLEEP_ARG_VA - 0x400000)
    sl_now = d[sl_off]
    assert d[sl_off - 1] == 0x6A, (
        f"expected `push imm8` at {SLEEP_ARG_VA - 1:#x}, found opcode {d[sl_off-1]:#04x}")
    have_sect = any(bytes(d[s[4]:s[4] + 5]) == SECT_NAME[:5] for s in F["secs"])

    newva = align(max(s[0] + max(s[1], s[3]) for s in F["secs"]), F["salign"])
    if have_sect:
        for s in F["secs"]:
            if bytes(d[s[4]:s[4] + 5]) == SECT_NAME[:5]:
                newva = s[0]
    base_va = 0x400000 + newva

    src, S = gen(base_va)
    code = asm_src(ks, src, S["code"])
    body = bytearray(b"\x00" * S["data_len"]) + code
    body[S["s_winmm"] - base_va:S["s_winmm"] - base_va + len(S["winmm_b"])] = S["winmm_b"]
    body[S["s_tbp"] - base_va:S["s_tbp"] - base_va + len(S["tbp_b"])] = S["tbp_b"]

    patched = b"\xE9" + struct.pack("<i", S["code"] - (THUNK_VA + 5)) + b"\x90"

    print(f"[{EXE}] .tres rva {newva:#x} -> VA {base_va:#x}; data {S['data_len']}B code {len(code)}B "
          f"(hook {S['code']:#x})")
    print(f"    Sleep thunk {THUNK_VA:#x}: {ORIG_THUNK.hex()} -> {patched.hex()}; "
          f"timeBeginPeriod({TARGET_MS}) once, then tail-jmp to [{IAT_SLEEP:#x}]")

    print(f"    frame loop Sleep({sl_now}) -> Sleep({args.sleep}) at {SLEEP_ARG_VA - 1:#x}")

    if have_sect and th_now == patched:
        sec = [s for s in F["secs"] if bytes(d[s[4]:s[4] + 5]) == SECT_NAME[:5]][0]
        if bytes(d[sec[2]:sec[2] + len(body)]) == bytes(body) and sl_now == args.sleep:
            print(f"[{EXE}] already patched and up to date - no-op")
            return 0
        print(f"[{EXE}] hook current but .tres contents differ - rewriting in place")
    elif have_sect != (th_now == patched):
        print(f"[{EXE}] INCONSISTENT: section={have_sect} thunk={th_now.hex()} - refusing")
        return 1
    else:
        assert th_now == ORIG_THUNK, (
            f"Sleep thunk {THUNK_VA:#x} is neither vanilla nor ours: {th_now.hex()} "
            f"(expected {ORIG_THUNK.hex()})")
        assert F["sectbl"] + (F["nsec"] + 1) * 40 <= F["hdrsz"], "no header room for a new section"

    if not args.apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            cs = Cs(CS_ARCH_X86, CS_MODE_32)
            print("---- .tres cave ----")
            for i in cs.disasm(code, S["code"]):
                print(f"  {i.address:08X}  {i.mnemonic:7s} {i.op_str}")
        except ImportError:
            print("  (capstone not installed)")
        print(f"[{EXE}] dry-run OK - re-run with --apply to write")
        return 0

    backup = os.path.join(BACKUP_DIR, os.path.basename(path) + BACKUP_SUFFIX)
    if not os.path.exists(backup):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, backup)
        print(f"    backup -> {backup}")

    if have_sect:
        sec = [s for s in F["secs"] if bytes(d[s[4]:s[4] + 5]) == SECT_NAME[:5]][0]
        va0, vsz, raw, rsz, hdr = sec
        assert raw + rsz >= len(d) - F["falign"], ".tres is not the last section - refusing"
        rawsz = align(len(body), F["falign"])
        d = d[:raw] + bytearray(body) + bytearray(b"\x00" * (rawsz - len(body)))
        struct.pack_into("<II", d, hdr + 8, len(body), va0)
        struct.pack_into("<II", d, hdr + 16, rawsz, raw)
        struct.pack_into("<I", d, F["opt"] + 56, align(va0 + len(body), F["salign"]))
        print(f"    rewrote .tres in place ({len(body)}B)")
    else:
        newraw = align(len(d), F["falign"])
        d += b"\x00" * (newraw - len(d))
        rawsz = align(len(body), F["falign"])
        d += bytes(body) + b"\x00" * (rawsz - len(body))
        b = F["sectbl"] + F["nsec"] * 40
        struct.pack_into("<8sIIII", d, b, SECT_NAME, len(body), newva, rawsz, newraw)
        struct.pack_into("<IIHHI", d, b + 24, 0, 0, 0, 0, 0xE0000060)   # R/W/X (the once-flag)
        struct.pack_into("<H", d, F["e"] + 6, F["nsec"] + 1)
        struct.pack_into("<I", d, F["opt"] + 56, align(newva + len(body), F["salign"]))
    d[th_off:th_off + 6] = patched
    d[sl_off] = args.sleep

    try:
        open(path, "wb").write(d)
    except PermissionError:
        print(f"[{EXE}] LOCKED - close the editor and retry")
        return 1
    print(f"[{EXE}] applied: .tres @ rva {newva:#x}, Sleep thunk -> {S['code']:#x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
