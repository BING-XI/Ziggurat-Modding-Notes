#!/usr/bin/env python3
r"""
build_bltprobe_exe.py -- DIAGNOSTIC ONLY. Capture the ORIGINAL exception behind "Blt Error",
before AoWz.exe throws it away.

Pair with:  python re_tools/read_bltprobe.py   (reads BOTH this probe and the aowInt one)
Companion:  build_bltprobe.py                  (the aowInt half -- keep both installed)

WHY THIS EXISTS
---------------
`Error - FCWin` / `Blt Error` fires on any damage to a combat wall. Probe v2 on the aowInt side
(build_bltprobe.py) traced it to its source:

  1. aowInt's draw routine calls FCWin's virtual draw at 0x59807D3D (the `[self+0x102]==0` path).
  2. That reaches `TFastCombatForm.FCWinDrawSurface` @ AoWz.exe 0x435E7C, FCWin's OnDrawSurface
     handler (the DFM binds it; probe v2 read the method pointer straight out of [self+0x108]).
  3. Its body Locks the surface, calls the real draw at 0x435CE4, Unlocks.
  4. Its except arm at 0x435F26 does:

         mov ecx, 0x435F54          ; 'Exception during FastCombatWin.DrawSurface'
         mov dl, 1
         mov eax, [0x45D45C]        ; class Exception
         call 0x40143C              ; Exception.Create
         call 0x4010A8              ; @RaiseExcept   <-- ORIGINAL EXCEPTION DISCARDED

  5. That generic replacement propagates up into aowInt's try (0x59807BC6..0x59807D48), whose
     handler prints the fixed label "Blt Error" with caption "Error - " + self.Name.

So the message names neither the error nor the component that failed -- both were destroyed on the
way up. This probe runs at 0x435F26, *before* the Create, and records the real exception.

WHAT IT RECORDS (AoWz.exe DATA slack at 0x0045A640)
    +00 magic 'BLT2'   +04 hits
    +08..+24 the eight pushad slots, in pushad order: EDI ESI EBP ESP EBX EDX ECX EAX
    +28 esp at the handler
    +2C 64 dwords of raw stack from there -- carries the Delphi exception frame AND the return
        addresses, so the reader recovers both the exception object and where inside 0x435CE4 it blew

EAX IS NOT THE EXCEPTION OBJECT. Measured on the aowInt side: this is a bare `except`, not
`except on E:`, and @HandleAnyException does not guarantee EAX for that form (v1 captured EAX whose
first dword was in no module, so not a VMT). We dump the stack and let the reader hunt for a pointer
whose class metadata actually validates. Do not "simplify" this back to reading EAX.

PLACEMENT
    cave    0x00610720  .clog (E0000060: EXEC|READ|WRITE), in the verified-zero tail 0x610714..0x610800
    scratch 0x0045A640  DATA raw slack 0x45A634..0x45A800 (460 B, verified zero, C0000040 READ|WRITE)
AoWz.exe is fixed-base 0x400000, so absolute addressing is fine here -- no PIC needed, unlike the DPL.
NOTE 0x60D004..0x60F020 also scans as free but is the combat-log ring buffer; never allocate there.

Patches BOTH canonical mod exes `Ziggurat\AoWz.exe` and `Ziggurat\AoWzCompat.exe` (names from
`zigexe.py`; byte-identical at this site, and the notes record the compat twin being silently
skipped once). ⚠ Follow --apply with ⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.) Idempotent, verify-before-write, dry-run by default, --apply / --revert.
Backups: backups\<exe>.pre-bltprobe, minted ONLY from a file proved to carry neither the hook nor
the cave -- never on --revert, never over our own previous output.
"""
import os, shutil, struct, subprocess, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                   # mod binary names (AoWz.exe / AoWzCompat.exe)
EXES = zigexe.EXES
BACKUP_DIR = os.path.join(GAME, "backups")      # ⚠ backups/, never the game root -- rule 2026-09-03
ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

HOOK = 0x435F26
ORIG = bytes.fromhex("b9545f4300")           # mov ecx, 0x435F54
CONT = 0x435F2B
CAVE = 0x00610720
CAVE_MAX = 0xE0                              # 0x610720..0x610800, the end of .clog
SCR = 0x0045A640
SCR_LEN = 0x12C                              # 0x2C header + 64 stack dwords
STACK_N = 64
PROLOGUE = bytes.fromhex("609cbf")           # pushad; pushfd; mov edi,imm32

SRC = f"""
    pushad
    pushfd
    mov   edi, {SCR}                     /* fixed base -- absolute is safe in the exe */
    mov   dword ptr [edi+0x00], 0x32544C42   /* 'BLT2' */
    inc   dword ptr [edi+0x04]

    /* the eight pushad slots verbatim: EDI ESI EBP ESP EBX EDX ECX EAX */
    lea   esi, [esp+4]
    lea   ebx, [edi+8]
    mov   ecx, 8
Lreg:
    mov   eax, dword ptr [esi]
    mov   dword ptr [ebx], eax
    add   esi, 4
    add   ebx, 4
    dec   ecx
    jnz   Lreg

    /* raw stack from the handler's ESP: the Delphi exception frame plus return addresses */
    lea   esi, [esp+0x24]                /* undo pushad(32) + pushfd(4) */
    mov   dword ptr [edi+0x28], esi
    lea   ebx, [edi+0x2C]
    mov   ecx, {STACK_N}
Lstk:
    mov   eax, dword ptr [esi]
    mov   dword ptr [ebx], eax
    add   esi, 4
    add   ebx, 4
    dec   ecx
    jnz   Lstk

    popfd
    popad
    mov   ecx, {hex(0x435F54)}           /* replay the displaced instruction */
    jmp   {CONT}
"""


def load_pe(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    oh = struct.unpack_from("<H", d, e + 0x14)[0]
    secs = []
    for i in range(n):
        o = e + 0x18 + oh + i * 40
        name = d[o:o + 8].rstrip(b"\0").decode("latin1")
        vs, va, rs, ptr = struct.unpack_from("<IIII", d, o + 8)
        ch = struct.unpack_from("<I", d, o + 36)[0]
        secs.append((name, va, vs, rs, ptr, ch))
    return secs


def foff(secs, va, need_write=False):
    r = va - 0x400000
    for name, sva, vs, rs, ptr, ch in secs:
        if sva <= r < sva + max(vs, rs):
            if r - sva >= rs:
                raise ValueError("VA %08X is past raw data in %s" % (va, name))
            if need_write and not (ch & 0x80000000):
                raise ValueError("VA %08X is in %s, not writable (%08X)" % (va, name, ch))
            return ptr + (r - sva)
    raise ValueError("VA %08X not mapped" % va)


def running():
    try:
        out = subprocess.run(["tasklist", "/NH", "/FO", "CSV"],
                             capture_output=True, text=True).stdout
    except Exception:
        return None
    # ⚠ the mod exes were renamed AoWz*/AoWzEd on 2026-09-09; a list that stops at AoW/AoWCompat/
    # AoWDevEd misses the process actually holding the lock. Single source: zigexe.LOCKING_PROCESSES.
    for name in zigexe.LOCKING_PROCESSES:
        if (name + ".exe").lower() in out.lower():
            return name + ".exe"
    return None


def main():
    apply_ = "--apply" in sys.argv
    revert = "--revert" in sys.argv

    cave, _ = ks.asm(SRC, CAVE)
    cave = bytes(cave)
    hook, _ = ks.asm("jmp %d" % CAVE, HOOK)
    hook = bytes(hook)
    assert len(hook) == 5 == len(ORIG), "hook must be exactly 5 bytes"
    assert cave.startswith(PROLOGUE), "cave prologue changed -- update PROLOGUE"
    assert len(cave) <= CAVE_MAX, "cave is %d B, over the %d B available before .clog ends" % (
        len(cave), CAVE_MAX)

    print("cave_bltprobe_exe @ %08X  (%d B of %d)" % (CAVE, len(cave), CAVE_MAX))
    print("scratch           @ %08X  (%d B, AoWz.exe DATA slack)" % (SCR, SCR_LEN))
    print("hook              @ %08X  %s -> %s   (continue %08X)"
          % (HOOK, ORIG.hex(" "), hook.hex(" "), CONT))
    if "--dis" in sys.argv:
        print()
        for ins in cs.disasm(cave, CAVE):
            print("  %08X  %-18s %s %s" % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))
    print()

    staged, plan, pristine = {}, [], {}
    for exe in EXES:
        p = os.path.join(GAME, exe)
        if not os.path.exists(p):
            print("  %-14s MISSING -- skipped" % exe)
            continue
        d = bytearray(open(p, "rb").read())
        secs = load_pe(d)
        foff(secs, SCR, need_write=True)
        foff(secs, SCR + SCR_LEN - 1, need_write=True)
        so = foff(secs, SCR)
        if set(d[so:so + SCR_LEN]) != {0}:
            sys.exit("ABORT: %s scratch at %08X is not zero -- something else owns it" % (exe, SCR))

        cave_off = foff(secs, CAVE)
        zone = bytes(d[cave_off:cave_off + CAVE_MAX])
        if set(zone) == {0}:
            pass
        elif zone.startswith(PROLOGUE):
            print("  %-14s earlier generation present -- revising the cave in place" % exe)
        else:
            sys.exit("ABORT: %s %08X holds %s\n  neither zero nor our prologue; another patch may "
                     "own this zone." % (exe, CAVE, zone[:16].hex(" ")))

        # POSITIVE pre-feature test, computed before anything is written: the hook still holds the
        # stock instruction AND our cave zone is entirely zero. This -- not "no backup file exists"
        # -- is what licenses a snapshot. After the 2026-09-09 rename no AoWz.exe.pre-bltprobe can
        # exist, so the old gate would have minted one holding the PATCHED state.
        pristine[p] = (bytes(d[foff(secs, HOOK):foff(secs, HOOK) + len(ORIG)]) == ORIG
                       and set(zone) == {0})

        want_cave = bytes(CAVE_MAX) if revert else cave + bytes(CAVE_MAX - len(cave))
        want_hook = ORIG if revert else hook
        for va, o, new, desc in ((CAVE, cave_off, want_cave, "cave (%d B + pad)" % len(cave)),
                                 (HOOK, foff(secs, HOOK), want_hook, "FCWinDrawSurface except arm")):
            cur = bytes(d[o:o + len(new)])
            if cur == new:
                print("  %-14s [= ] %08X  %s" % (exe, va, desc))
                continue
            if va == HOOK and cur not in (ORIG, hook):
                sys.exit("ABORT: %s %08X holds %s\n  expected %s (stock) or %s (ours)"
                         % (exe, va, cur.hex(" "), ORIG.hex(" "), hook.hex(" ")))
            print("  %-14s [->] %08X  %s" % (exe, va, desc))
            plan.append((p, exe, va, o, cur, new, desc))
            staged[p] = d

    if not plan:
        print("\n[= ] already in the requested state.")
        return 0
    if not apply_:
        print("\n[dry-run] %d write(s). Re-run with --apply." % len(plan))
        return 0
    who = running()
    if who:
        sys.exit("[x] %s is running. Close it and retry." % who)

    for p in staged:
        # ⚠ Only ever snapshot a file PROVED unpatched. On --revert the file IS the patched state
        # by definition, and on a re-apply over an earlier generation of the cave it is our own
        # past output -- neither is a `.pre-` worth having.
        if revert or not pristine.get(p):
            print("  [bak] skipped for %s -- not in the pre-feature state (a .pre-* of a patched "
                  "file is a lie)" % os.path.basename(p))
            continue
        os.makedirs(BACKUP_DIR, exist_ok=True)
        bak = os.path.join(BACKUP_DIR, os.path.basename(p) + ".pre-bltprobe")
        if not os.path.exists(bak):
            shutil.copy2(p, bak)
            print("  [bak] %s" % bak)
    for p, exe, va, o, cur, new, desc in plan:
        assert bytes(staged[p][o:o + len(new)]) == cur, "verify-before-write failed %s %08X" % (exe, va)
        staged[p][o:o + len(new)] = new
    for p, d in staged.items():
        open(p, "wb").write(bytes(d))
    for p, exe, va, o, cur, new, desc in plan:
        chk = open(p, "rb").read()
        assert chk[o:o + len(new)] == new, "readback mismatch %s %08X" % (exe, va)
        print("  [w ] %-14s %08X  %s" % (exe, va, desc))

    if revert:
        print("\n[done] both exes restored to stock.")
    else:
        print("\n[done] Reproduce the wall hit, LEAVE THE DIALOG UP, then:\n"
              "         python \"Modding Resources/re_tools/read_bltprobe.py\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
