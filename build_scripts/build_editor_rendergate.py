#!/usr/bin/env python3
r"""
EDITOR RENDER GATE: decouple map render rate from the message pump  --  HSEPack.dpl.

THE PROBLEM (measured 2026-07-28, see Editor_Frame_Cost_Analysis.md)
  The editor's frame loop renders the map on EVERY iteration, so render rate and message-pump
  rate are the same number and you can only trade one for the other:
        latency ~= Sleep + 6.5 ms      CPU ~= 6.5 / (Sleep + 6.5)
  At the shipped Sleep(8) that is 27% of a core for ~70 fps of map animation, which a map
  editor does not need. Turning the DFM FrameRate DOWN makes both worse (measured), so it is
  not a throttle -- see the doc.

THE FIX
  Render only every Nth pass, while the loop keeps pumping every pass. CPU then depends on the
  render period and latency only on the per-pass sleep, so BOTH improve at once. Measured
  maximised (2180x1210), all samples foreground-validated:
      vanilla (gate off)               29.2% CPU   p50 14.0 ms   p95 14.9 ms
      every=16 skip=4, exe Sleep 1      5.2% CPU   p50  6.4 ms   p95  7.6 ms   (~11 fps)
  i.e. 5.6x less CPU, 2.2x better p50 and 2x better p95, all at once.

  ⚠ COUPLED WITH build_editor_timerres.py --sleep 1. Once this gate paces the loop, the exe's
  Sleep(8) no longer paces anything and only pads the RENDER pass -- which is what pins p95 near
  15 ms in every gate-only config. Dropping it to 1 halves p95. But `--sleep 1` is ONLY safe with
  this gate installed: take this gate out without restoring --sleep 8 and the loop free-runs
  at ~117 fps. Revert both or neither.

  ⚠ MEASUREMENT: the editor self-throttles when it is NOT the foreground window (~1-3% CPU,
  ~31 ms latency regardless of tuning). Validate foreground per sample; Windows' foreground lock
  defeats SetForegroundWindow and SwitchToThisWindow from a background script, so relaunch the
  editor to get foreground rights.

HOW
  HSMEdit.THSMEdit.UpdateFrame (0x55614904) is the renderer. It is reached ONLY through its VMT
  slot (THSMEdit+0xAC), and the exe's TMainForm.HSMEditUpdateFrame is merely the OnUpdateFrame
  event -- gating the exe side would skip the status bar, not the rendering.

  The 7 bytes at 0x55614912 (`cmp byte ptr [esi+0x1bc], 0`, 80 BE BC 01 00 00 00) become
  `jmp cave` + 2 nops. The cave counts passes and either
    * re-runs the displaced compare and jumps back to the original `je` at 0x55614919
      (render this pass), or
    * sleeps `skip_sleep` ms and jumps to the function's EPILOGUE at 0x55614C2E.

  ⚠ The skip path must jump to the epilogue (0x55614C2E), NOT to the function's own early-exit
  at 0x55614C27. That label still runs `call TCustomDisplay.UpdateFrame` at 0x55614C29, which is
  where the present (GFXE.TDIB16Surface.BltDC -> StretchDIBits) happens. The first version of
  this patch jumped to 0x55614C27 and CPU only fell 35% -> 22.5%, with a UI-thread profile still
  showing 27% in NtGdiStretchDIBitsInternal. Do not "simplify" it back.
  (The tempting-but-wrong reasoning was: the blank-map measurement showed 0.6% CPU for a full
  viewport, so a present with nothing dirty must be free. It is not free on this path.)

  Because that same call is what fires OnUpdateFrame -- and hence the exe's Sleep(8) -- the cave
  has to do the sleeping itself on skipped passes, or the loop free-runs at the DLL's Sleep(1).

  ⚠ The displaced range stops one byte short of the `.reloc` entry at 0x55614920 (the absolute
  operand of `mov eax,[0x5562E2F4]` at 0x5561491F). Do not widen it.

  The cave is position-independent (HSEPack rebases): its state is reached with call/pop, and
  both exits are rel32 within the same image, which survives rebasing. State lives in the new
  R/W/X section, so each process that loads HSEPack gets its own copy-on-write counter.

  `every` is a live-tunable dword at the section base+4, so the render period can be swept with
  WriteProcessMemory without rebuilding.

SCOPE: THSMEdit is the EDITOR's map control; AoW.exe never executes this path, though it does
load HSEPack.dpl. Close AoWDevEd.exe *and* AoW.exe before --apply (the DLL is locked by either).

CONVENTIONS: dry-run by default, --apply to write, --every N to set the period, idempotent
(rewrites its section in place, comparing the whole body -- matching hook bytes alone are NOT
proof of being up to date), verify-before-write, auto-backup to
`<game dir>\backups\HSEPack.dpl.pre-rendergate`.
Revert: there is no --undo here, and copying that snapshot back is NOT a revert path -- it is a
WHOLE-FILE copy, so it also drops build_dlgdirs.py's .dlgd cave and its 16 call-site edits on this
same DLL. Undo surgically instead: restore ORIG_HOOK at HOOK_VA and zero the .rgt body.
⚠ And restore build_editor_timerres.py --sleep 8 at the same time (see the coupling note above).

Needs: pip install keystone-engine capstone
"""
import argparse, os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL = "HSEPack.dpl"
BACKUP_SUFFIX = ".pre-rendergate"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)
SECT_NAME = b".rgt\0\0\0\0"

PREF_BASE  = 0x55600000
HOOK_VA    = 0x55614912                                   # cmp byte ptr [esi+0x1bc], 0
ORIG_HOOK  = bytes([0x80, 0xBE, 0xBC, 0x01, 0x00, 0x00, 0x00])
RESUME_VA  = 0x55614919                                   # the original `je 0x55614c27`
EPILOGUE_VA = 0x55614C2E                                  # pop ecx/edx/esi/ebx; ret
EPI_BYTES  = bytes([0x59, 0x5A, 0x5E, 0x5B, 0xC3])
SLEEP_THUNK = 0x556014FC                                  # jmp dword ptr [0x55630640] (kernel32 Sleep)
RELOC_VA   = 0x55614920                                   # first reloc after the hook -- keep clear
SELF_FLAG  = 0x1BC                                        # the byte the displaced cmp tests

# Skipped passes must jump PAST the call to TCustomDisplay.UpdateFrame at 0x55614C29, because
# that is where the present (GFXE.TDIB16Surface.BltDC -> StretchDIBits) happens -- measured at
# 27% of the UI thread even with the scene rebuild fully gated. Jumping to the function's own
# early-exit at 0x55614C27 (the first attempt) still ran it, and CPU only fell 35% -> 22.5%.
# But that call is ALSO what fires the exe's OnUpdateFrame (and hence its Sleep(8)), so the cave
# has to do the sleeping itself or the loop free-runs.
DEFAULT_EVERY = 16
DEFAULT_SKIP_SLEEP = 4


def asm_src(ks, src, va):
    """keystone (LLVM) has no ';' comments in Intel mode -- strip them first."""
    clean = "\n".join(ln.split(";", 1)[0] for ln in src.splitlines())
    code, _ = ks.asm(clean, va)
    return bytes(code)


def gen(base_va):
    """[counter:4][every:4][code]. Returns (asm, code_va, state_delta_expr)."""
    state_va = base_va                       # [0]=counter [4]=every [8]=skip sleep ms
    code_va = base_va + 12
    # The state offset MUST be a literal: keystone parses `add eax, <expr> - L1` as a MEMORY
    # operand (`add eax, dword ptr [...]`), which would read garbage instead of adjusting the
    # pointer. Compute it here from the fixed prologue length instead.
    #   push eax (1) + push ecx (1) + call rel32 (5) = 7 bytes before L1
    l1_off = 7
    back = (code_va + l1_off) - state_va
    src = f"""
gate:
        push eax
        push ecx
        call L1
    L1:
        pop  eax                              ; eax = runtime address of L1
        sub  eax, {back}                      ; -> the state block (rebase-invariant delta)
        mov  ecx, dword ptr [eax]
        inc  ecx
        cmp  ecx, dword ptr [eax + 4]
        jb   skip
        xor  ecx, ecx                         ; period reached: reset and render this pass
        mov  dword ptr [eax], ecx
        pop  ecx
        pop  eax
        cmp  byte ptr [esi + {SELF_FLAG:#x}], 0   ; the displaced instruction
        jmp  {RESUME_VA:#x}                   ; rel32, same image -> survives rebasing
    skip:
        mov  dword ptr [eax], ecx             ; remember the pass count
        push dword ptr [eax + 8]              ; Sleep(skip_ms) -- stdcall, cleans its own arg
        call {SLEEP_THUNK:#x}
        pop  ecx
        pop  eax
        xor  eax, eax
        jmp  {EPILOGUE_VA:#x}                 ; past the present AND the OnUpdateFrame event
"""
    return src, state_va, code_va


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
    ap.add_argument("--every", type=int, default=DEFAULT_EVERY,
                    help="render 1 pass in N (1 = render every pass, i.e. vanilla behaviour)")
    ap.add_argument("--skip-sleep", type=int, default=DEFAULT_SKIP_SLEEP,
                    help="ms the cave sleeps on a skipped pass (sets the pump period)")
    args = ap.parse_args()
    if not (1 <= args.every <= 200):
        sys.exit("--every out of range (1..200)")

    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    path = os.path.join(GAME, DLL)
    d = bytearray(open(path, "rb").read())
    F = load_sections(d)

    hook_off = rva2off(F["secs"], HOOK_VA - PREF_BASE)
    hook_now = bytes(d[hook_off:hook_off + 7])
    have_sect = any(bytes(d[s[4]:s[4] + 4]) == SECT_NAME[:4] for s in F["secs"])

    epi_off = rva2off(F["secs"], EPILOGUE_VA - PREF_BASE)
    assert bytes(d[epi_off:epi_off + 5]) == EPI_BYTES, (
        f"epilogue {EPILOGUE_VA:#x} is not pop ecx/edx/esi/ebx;ret - build differs, aborting")
    thunk_off = rva2off(F["secs"], SLEEP_THUNK - PREF_BASE)
    assert bytes(d[thunk_off:thunk_off + 2]) == bytes([0xFF, 0x25]), (
        f"Sleep thunk {SLEEP_THUNK:#x} is not a jmp [IAT] - build differs, aborting")
    assert HOOK_VA + len(ORIG_HOOK) <= RELOC_VA, "displaced range would reach the reloc entry"

    newva = align(max(s[0] + max(s[1], s[3]) for s in F["secs"]), F["salign"])
    if have_sect:
        for s in F["secs"]:
            if bytes(d[s[4]:s[4] + 4]) == SECT_NAME[:4]:
                newva = s[0]
    base_va = PREF_BASE + newva

    src, state_va, code_va = gen(base_va)
    code = asm_src(ks, src, code_va)
    # the call/pop delta is only correct if the prologue really is push/push/call
    assert code[:3] == b"\x50\x51\xE8", (
        f"unexpected cave prologue {code[:3].hex()} - the call/pop state delta would be wrong")
    assert code[7:9] == b"\x58\x83" or code[7] == 0x58, (
        f"expected `pop eax` at the call/pop landing site, got {code[7:9].hex()}")
    body = bytearray(struct.pack("<III", 0, args.every, args.skip_sleep)) + code

    patched_hook = b"\xE9" + struct.pack("<i", code_va - (HOOK_VA + 5)) + b"\x90\x90"

    print(f"[{DLL}] .rgt rva {newva:#x} -> VA {base_va:#x}; state {state_va:#x} "
          f"(counter, every={args.every}, skip_sleep={args.skip_sleep}ms), "
          f"code {code_va:#x} ({len(code)}B)")
    print(f"    hook {HOOK_VA:#x}: {ORIG_HOOK.hex()} -> {patched_hook.hex()}  "
          f"(render pass -> {RESUME_VA:#x}, skip -> Sleep + {EPILOGUE_VA:#x})")

    if have_sect and hook_now == patched_hook:
        sec = [s for s in F["secs"] if bytes(d[s[4]:s[4] + 4]) == SECT_NAME[:4]][0]
        cur = bytes(d[sec[2]:sec[2] + len(body)])
        if cur == bytes(body):
            print(f"[{DLL}] already patched and up to date - no-op")
            return 0
        print(f"[{DLL}] hook current but .rgt contents differ - rewriting in place")
    else:
        assert hook_now == ORIG_HOOK or (have_sect and hook_now[0] == 0xE9), (
            f"hook site {HOOK_VA:#x} is neither vanilla nor ours: {hook_now.hex()}")
        if not have_sect:
            assert F["sectbl"] + (F["nsec"] + 1) * 40 <= F["hdrsz"], "no header room for a section"

    if not args.apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            cs = Cs(CS_ARCH_X86, CS_MODE_32)
            print("---- .rgt cave ----")
            for i in cs.disasm(code, code_va):
                print(f"  {i.address:08X}  {i.mnemonic:7s} {i.op_str}")
        except ImportError:
            print("  (capstone not installed - skipping disasm preview)")
        print(f"[{DLL}] dry-run OK - re-run with --apply to write")
        return 0

    backup = os.path.join(BACKUP_DIR, os.path.basename(path) + BACKUP_SUFFIX)
    if not os.path.exists(backup):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, backup)
        print(f"    backup -> {backup}")

    if have_sect:
        sec = [s for s in F["secs"] if bytes(d[s[4]:s[4] + 4]) == SECT_NAME[:4]][0]
        va0, vsz, raw, rsz, hdr = sec
        assert raw + rsz >= len(d) - F["falign"], ".rgt is not the last section - refusing"
        rawsz = align(len(body), F["falign"])
        d = d[:raw] + bytearray(body) + bytearray(b"\x00" * (rawsz - len(body)))
        struct.pack_into("<II", d, hdr + 8, len(body), va0)
        struct.pack_into("<II", d, hdr + 16, rawsz, raw)
        struct.pack_into("<I", d, F["opt"] + 56, align(va0 + len(body), F["salign"]))
        print(f"    rewrote .rgt in place ({len(body)}B) - no backup layer added")
    else:
        newraw = align(len(d), F["falign"])
        d += b"\x00" * (newraw - len(d))
        rawsz = align(len(body), F["falign"])
        d += bytes(body) + b"\x00" * (rawsz - len(body))
        b = F["sectbl"] + F["nsec"] * 40
        struct.pack_into("<8sIIII", d, b, SECT_NAME, len(body), newva, rawsz, newraw)
        struct.pack_into("<IIHHI", d, b + 24, 0, 0, 0, 0, 0xE0000060)   # R/W/X: counter lives here
        struct.pack_into("<H", d, F["e"] + 6, F["nsec"] + 1)
        struct.pack_into("<I", d, F["opt"] + 56, align(newva + len(body), F["salign"]))
    d[hook_off:hook_off + 7] = patched_hook

    try:
        open(path, "wb").write(d)
    except PermissionError:
        print(f"[{DLL}] LOCKED - close AoWDevEd.exe and AoW.exe, then retry")
        return 1
    print(f"[{DLL}] applied: render 1 pass in {args.every}, skip sleep {args.skip_sleep} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
