#!/usr/bin/env python3
r"""
build_bltprobe.py -- DIAGNOSTIC ONLY. Capture what actually fails when aowInt raises "Blt Error".

Pair with:  python re_tools/read_bltprobe.py   (reads the probe out of the LIVE process)

THE PROBLEM
-----------
An `Error - FCWin` / `Blt Error` dialog fires on ANY damage to a combat WALL (confirmed with cannons,
so not touch-ability specific). Every suspect has been eliminated by A/B test against that repro:

  * `touch` DLL hooks off                 -> persists
  * ALL SEVEN combat-log DLL hooks off    -> persists      (the DLL half is EXONERATED)
  * exe: cloned window forced never-visible -> persists     (visibility EXONERATED)
  * exe: cave_drain unhooked from the paint pump -> persists
  * exe: cloned window never CREATED      -> persists       (the window itself EXONERATED)
  * lower screen resolution               -> persists

`TCombatWall.Show` / `ShowHitPcnt` are never called in these battles (zero HITP records across 77
combats on the razediag probe), so the wall is drawn by FCWin's own paint path, not by our code.

WHY THE MESSAGE HAS NEVER TOLD US ANYTHING
------------------------------------------
`"Blt Error"` (aowInt 0x59807F70) is pushed from exactly ONE place, 0x59807D6E, and **nothing branches
there**. What precedes it is `jmp @HandleAnyException` at 0x59807D50 -- so 0x59807D55 is the EXCEPT arm
of a try/except, and the string is a fixed label, not a description. The caption is built at 0x59807D65
as `Format("Error - ", component.Name)` from `[[ebp-4]+8]`, which is why it reads "Error - FCWin": the
component whose paint raised IS FCWin. Siblings in the same routine ("Verify Surface Error", "Draw
Error", "SB Draw Events Error", "Exception during DrawSurface") confirm the pattern.

The try is exactly 0x59807BC6 (`mov fs:[eax],esp`) .. 0x59807D48, and its body has THREE shapes:

    59807BCC  cmp byte [self+0x102],0
    59807BD3  je   59807D35          -- "not dirty" -> the virtual call below, nothing else
    59807BDC  cmp dword [self+0xE4],0
    59807BE3  jle  59807D43          -- no BltRects -> straight to try END, cannot raise
    59807C0F  call [self+0x110]      -- pre-draw event   (guard: word [self+0x112] <> 0)
    59807C32..59807D07               -- the BltRect blit loop
    59807D2D  call [self+0x108]      -- post-draw event  (guard: word [self+0x10a] <> 0)
    59807D3D  call [self.VMT+0x9C]   -- the "not dirty" path's virtual draw

WHAT PROBE v1 FOUND (2026-07-22, one live capture)
--------------------------------------------------
    self = 0193464C, self.Name = 'FCWin'        <- frame and EBP are sound
    rect count [self+0xE4] = 0
    rect / BltRect index / remaining = garbage  <- those locals were never written

Count 0 means the blit loop never ran. And per the head above, count <= 0 with a set dirty flag exits
the try immediately without executing anything, so it could not have raised. The only path that both
leaves the loop locals unwritten AND can raise is `[self+0x102] == 0` -> the virtual call at 0x59807D3D.

**So "Blt Error" is not about blitting.** It is the label on a try block whose failing statement, on
this path, is a single virtual method call. v2 therefore captures `[self+0x102]` (to confirm the path)
and `[[self]+0x9C]` (the method itself) -- and the module that address lands in answers the question
this whole investigation has been stuck on: vanilla, or ours.

EAX AND THE EXCEPTION OBJECT
----------------------------
The handler opens `push 0 ; mov eax,[ebp-4]`, overwriting EAX. For `except on E: ... do` Delphi passes
the exception object in EAX, so that looked like a free win -- but v1 captured EAX = 00858E20 whose
first dword is 001ADEAC, which is in no loaded module and therefore is not a VMT. This is a BARE
`except`, and @HandleAnyException does not guarantee EAX for that form. Don't re-try reading EAX as the
exception object. v2 instead dumps 40 dwords of raw stack and lets the reader hunt for a pointer whose
class metadata checks out.

WHAT IT RECORDS (aowInt DATA slack at 0x5983E100, 256 bytes)
    +00 magic 'BLTP'  +04 hits          +08 EAX at entry (NOT the exception object -- see above)
    +0C..+18 rect     +1C blt index     +20 remaining     +24 self     +28 src surface
    +2C dest arg      +30 transparent   +34 rect count    +38 ebp      +3C esp at handler
    +40 dirty [self+0x102]   <- 0 means the virtual-call path
    +44 self VMT             +48 [VMT+0x9C]  <- THE METHOD THAT RAISED
    +4C/+50 post-draw event code/data        +54/+58 pre-draw event code/data
    +5C BltRect list [self+0xDC]
    +60..+FF 40 dwords of stack from the handler's ESP

DESIGN NOTES (both learned the hard way in this project)
--------------------------------------------------------
* aowInt's CODE section is 60000020 = CODE|EXEC|READ -- **not writable**, so cave-local state is
  impossible. Its DATA section (C0000040, READ|WRITE) declares VirtualSize 0x24 but has 0x200 raw
  bytes, so 0x5983E024..0x5983E1FF is mapped, writable, raw-backed slack. 0x5983E100..0x5983E1FF is
  verified zero and sits 220 bytes clear of the last real datum. The game exe's `.clog` (E0000060)
  would also work, but aowInt is loaded by the editor too, which has no `.clog` -- writing there
  would be a wild store in the editor. Staying inside our own module avoids that entirely.
* The DPL rebases, so the scratch is reached PIC-style (call/pop, then add a link-time delta).
* **The cave dereferences nothing it doesn't have to.** A stray read inside an except arm means a
  nested exception, which in Delphi 3 is a hard failure. It records raw POINTERS; `read_bltprobe.py`
  walks them out-of-process with ReadProcessMemory, which returns an error instead of faulting.
* Behaviour is unchanged: all registers and flags are saved/restored, the two displaced instructions
  are replayed, and control returns to 0x59807D5A. The dialog still appears -- and because it is
  MODAL, the process sits still holding the evidence while you run the reader.

Hook: 5 bytes at 0x59807D55 (`6a 00 8b 45 fc`). Verified: no reloc in range, no branch lands inside it,
and nothing jumps to it (reached only via @HandleAnyException).

Idempotent, verify-before-write, dry-run by default. --apply / --revert / --dis.

REVERT is `--revert --apply`, and it is SURGICAL: it restores the 5 stock hook bytes and zeroes the
0x200-byte cave zone. It reads no backup.
Backup: `<game dir>\backups\aowInt.dpl.pre-bltprobe`, minted only when the file is PROVED unpatched
(stock hook bytes + an all-zero cave zone). Not minted on a revert or on an in-place cave revision --
in both of those the current file IS a patched state, and a snapshot of it would sit on disk looking
authoritative while containing exactly what a backup must not.

⚠ The write guard scans `zigexe.ALL_EXES` -- the MOD binaries only. Naming the pre-2026-09-09 pair
here was wrong in BOTH directions: a running `AoWz.exe` went undetected (guard passes, the write
then dies on PermissionError), while a running VANILLA `AoW.exe` blocked a write that was fine.
"""
import os, shutil, struct, subprocess, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

import zigexe

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL = os.path.join(GAME, "aowInt.dpl")
BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-bltprobe")
ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

HOOK = 0x59807D55
ORIG = bytes.fromhex("6a008b45fc")          # push 0 ; mov eax,[ebp-4]
CONT = 0x59807D5A
CAVE = 0x59823000                            # CODE zero tail (free from 0x598227C7)
CAVE_MAX = 0x200                             # reserved for this probe; the tail must stay zero
SCR  = 0x5983E100                            # DATA slack -- writable, raw-backed, verified zero
SCR_LEN = 0x100
PIC  = 7                                     # pushad(1) + pushfd(1) + call rel32(5) -> the `pop edi`
PROLOGUE = bytes.fromhex("609ce8")           # how we recognise a previous generation of this cave

SRC = f"""
    pushad
    pushfd
    call  Lpic                       /* position-independent: the DPL rebases */
Lpic:
    pop   edi
    add   edi, {SCR - (CAVE + PIC)}  /* edi = live scratch base */

    mov   dword ptr [edi+0x00], 0x50544C42      /* 'BLTP' */
    inc   dword ptr [edi+0x04]

    /* ---- the frame is intact: Delphi restores EBP before entering an except arm ---- */
    mov   eax, dword ptr [ebp-0x70]             /* rect (only written if the blit loop ran) */
    mov   dword ptr [edi+0x0C], eax
    mov   eax, dword ptr [ebp-0x6C]
    mov   dword ptr [edi+0x10], eax
    mov   eax, dword ptr [ebp-0x68]
    mov   dword ptr [edi+0x14], eax
    mov   eax, dword ptr [ebp-0x64]
    mov   dword ptr [edi+0x18], eax
    mov   eax, dword ptr [ebp-0x10]             /* BltRect index */
    mov   dword ptr [edi+0x1C], eax
    mov   eax, dword ptr [ebp-0x20]             /* rects remaining */
    mov   dword ptr [edi+0x20], eax
    mov   eax, dword ptr [ebp-0x08]             /* the arg passed as EDX to the failing call */
    mov   dword ptr [edi+0x2C], eax
    mov   dword ptr [edi+0x38], ebp
    mov   eax, dword ptr [esp+0x20]             /* pushad slot for EAX (pushfd added 4) */
    mov   dword ptr [edi+0x08], eax

    /* ---- self: the handler dereferences it two instructions later, so it is sound ---- */
    mov   esi, dword ptr [ebp-0x04]
    mov   dword ptr [edi+0x24], esi
    cmp   esi, 0x10000
    jb    Lstack
    mov   eax, dword ptr [esi+0x18C]            /* source surface */
    mov   dword ptr [edi+0x28], eax
    movzx eax, byte ptr [esi+0xD8]              /* 0 = plain blt, else colour-keyed */
    mov   dword ptr [edi+0x30], eax
    mov   eax, dword ptr [esi+0xE4]             /* BltRect count */
    mov   dword ptr [edi+0x34], eax
    movzx eax, byte ptr [esi+0x102]             /* the dirty flag -- 0 selects the virtual call */
    mov   dword ptr [edi+0x40], eax
    mov   eax, dword ptr [esi+0x108]            /* post-draw event: code, then data */
    mov   dword ptr [edi+0x4C], eax
    mov   eax, dword ptr [esi+0x10C]
    mov   dword ptr [edi+0x50], eax
    mov   eax, dword ptr [esi+0x110]            /* pre-draw event: code, then data */
    mov   dword ptr [edi+0x54], eax
    mov   eax, dword ptr [esi+0x114]
    mov   dword ptr [edi+0x58], eax
    mov   eax, dword ptr [esi+0xDC]             /* BltRect list */
    mov   dword ptr [edi+0x5C], eax

    /* ---- self's VMT, and slot 0x9C: the method the "not dirty" path calls ---- */
    mov   ebx, dword ptr [esi]
    mov   dword ptr [edi+0x44], ebx
    cmp   ebx, 0x10000
    jb    Lstack
    mov   eax, dword ptr [ebx+0x9C]
    mov   dword ptr [edi+0x48], eax

Lstack:
    /* 40 dwords from the handler's ESP. Always mapped (it is the live stack), and it carries the
       Delphi exception frame -- the reader hunts it for the exception object, since EAX is not it. */
    lea   esi, [esp+0x24]                       /* undo pushad(32) + pushfd(4) */
    mov   dword ptr [edi+0x3C], esi
    lea   ebx, [edi+0x60]
    mov   ecx, 40
Lstk:
    mov   eax, dword ptr [esi]
    mov   dword ptr [ebx], eax
    add   esi, 4
    add   ebx, 4
    dec   ecx
    jnz   Lstk

    popfd
    popad
    push  0                                     /* replay the displaced instructions */
    mov   eax, dword ptr [ebp-4]
    jmp   {CONT}
"""


def load_pe(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    oh = struct.unpack_from("<H", d, e + 0x14)[0]
    img = struct.unpack_from("<I", d, e + 0x34)[0]
    secs = []
    for i in range(n):
        o = e + 0x18 + oh + i * 40
        name = d[o:o + 8].rstrip(b"\0").decode("latin1")
        vs, va, rs, ptr = struct.unpack_from("<IIII", d, o + 8)
        ch = struct.unpack_from("<I", d, o + 36)[0]
        secs.append((name, va, vs, rs, ptr, ch))
    return img, secs


def foff(img, secs, va, need_write=False):
    r = va - img
    for name, sva, vs, rs, ptr, ch in secs:
        if sva <= r < sva + max(vs, rs):
            if r - sva >= rs:
                raise ValueError("VA %#x is past raw data in %s" % (va, name))
            if need_write and not (ch & 0x80000000):
                raise ValueError("VA %#x is in %s which is NOT writable (%08X)" % (va, name, ch))
            return ptr + (r - sva)
    raise ValueError("VA %#x not mapped" % va)


def running():
    """Which mod binary is holding Ziggurat\\aowInt.dpl open, if any.

    ⚠ The MOD names only. The root's vanilla AoW.exe / AoWCompat.exe load the ROOT's copy of every
    package, so one of those running does not lock this DLL and must not stop a write."""
    try:
        out = subprocess.run(["tasklist", "/NH", "/FO", "CSV"],
                             capture_output=True, text=True).stdout
    except Exception:
        return None
    for exe in zigexe.ALL_EXES:
        if exe.lower() in out.lower():
            return exe
    return None


def main():
    apply_ = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    img, secs = load_pe(d)

    cave, _ = ks.asm(SRC, CAVE)
    cave = bytes(cave)
    hook, _ = ks.asm("jmp %d" % CAVE, HOOK)
    hook = bytes(hook)

    # assumptions worth asserting rather than trusting
    assert len(hook) == 5 == len(ORIG), "hook must be exactly 5 bytes"
    assert cave[PIC] == 0x5F, ("PIC offset wrong: expected `pop edi` (5F) at +%d, got %02X"
                               % (PIC, cave[PIC]))
    foff(img, secs, SCR, need_write=True)                  # scratch must be writable + raw-backed
    foff(img, secs, SCR + SCR_LEN - 1, need_write=True)
    assert set(d[foff(img, secs, SCR):foff(img, secs, SCR) + SCR_LEN]) <= {0}, \
        "scratch at %08X is not zero -- something else may own it" % SCR

    print("cave_bltprobe @ %08X  (%d B)" % (CAVE, len(cave)))
    print("scratch       @ %08X  (%d B, aowInt DATA slack, PIC delta +%#x)"
          % (SCR, SCR_LEN, SCR - (CAVE + PIC)))
    print("hook          @ %08X  %s -> %s   (continue %08X)"
          % (HOOK, ORIG.hex(" "), hook.hex(" "), CONT))
    if "--dis" in sys.argv:
        print()
        for ins in cs.disasm(cave, CAVE):
            print("  %08X  %-20s %s %s" % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))

    # The cave is revised IN PLACE across generations -- never by reverting. Reverting aowInt today
    # is harmless (one layer), but the habit is what matters: a `.pre-*` backup is a whole-file
    # snapshot, so "revert and re-apply" silently destroys every layer added since. We therefore own
    # the whole CAVE_MAX zone and always rewrite it as `new + zero padding`, which also guarantees no
    # stale tail from a longer previous generation.
    cave_off = foff(img, secs, CAVE)
    hook_off = foff(img, secs, HOOK)
    zone = bytes(d[cave_off:cave_off + CAVE_MAX])
    # PROVED unpatched: stock hook bytes AND an untouched cave zone. Only this state may be
    # snapshotted -- a `.pre-*` minted on a revert, or over an earlier generation of our own cave,
    # is a snapshot of a PATCHED file wearing an "original" name.
    pristine = set(zone) == {0} and bytes(d[hook_off:hook_off + len(ORIG)]) == ORIG
    if set(zone) == {0}:
        pass                                        # fresh
    elif zone.startswith(PROLOGUE):
        print("  [~ ] %08X  an earlier generation of cave_bltprobe is installed -- revising in place"
              % CAVE)
    else:
        sys.exit("ABORT: %08X holds %s\n  that is neither zero nor a cave_bltprobe prologue (%s);\n"
                 "  another patch may own this zone." % (CAVE, zone[:16].hex(" "), PROLOGUE.hex(" ")))
    assert len(cave) <= CAVE_MAX, "cave is %d B, over the %d B reserved" % (len(cave), CAVE_MAX)

    cave_img = cave + bytes(CAVE_MAX - len(cave))
    targets = [(CAVE, cave_off, zone, cave_img, "cave_bltprobe (%d B + pad)" % len(cave)),
               (HOOK, hook_off, None, hook, "Blt Error except-arm -> probe")]
    if revert:
        targets = [(CAVE, cave_off, zone, bytes(CAVE_MAX), "cave_bltprobe -> zeroed"),
                   (HOOK, hook_off, None, ORIG, "except arm -> STOCK")]

    plan = []
    print()
    for va, o, _prev, new, desc in targets:
        cur = bytes(d[o:o + len(new)])
        if cur == new:
            print("  [= ] %08X  %s" % (va, desc))
            continue
        if va == HOOK and cur not in (ORIG, hook):
            sys.exit("ABORT: %08X holds %s\n  expected %s (stock) or %s (ours)"
                     % (va, cur.hex(" "), ORIG.hex(" "), hook.hex(" ")))
        print("  [->] %08X  %s" % (va, desc))
        plan.append((va, o, cur, new, desc))

    if not plan:
        print("\n[= ] already in the requested state.")
        return 0
    if not apply_:
        print("\n[dry-run] %d write(s). Re-run with --apply." % len(plan))
        return 0
    who = running()
    if who:
        sys.exit("[x] %s is running and locks the DLL. Close it and retry." % who)

    if not pristine:
        print("  [--] no backup taken: aowInt.dpl is not in the stock state (revert, or an "
              "in-place cave revision)")
    elif os.path.exists(BACKUP):
        print("  [--] backup already exists: %s" % BACKUP)
    else:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("  [bak] %s" % BACKUP)
    for va, o, orig, new, desc in plan:
        assert bytes(d[o:o + len(new)]) == orig, "verify-before-write failed at %08X" % va
        d[o:o + len(new)] = new
        print("  [w ] %08X  %s" % (va, desc))
    open(DLL, "wb").write(bytes(d))
    chk = open(DLL, "rb").read()
    for va, o, orig, new, desc in plan:
        assert chk[o:o + len(new)] == new, "readback mismatch at %08X" % va

    if revert:
        print("\n[done] aowInt.dpl restored to stock.")
    else:
        print("\n[done] Now:\n"
              "  1. start the game, get into a tactical combat, hit a WALL\n"
              "  2. LEAVE THE ERROR DIALOG UP (it is modal -- the process holds still)\n"
              "  3. python \"Modding Resources/re_tools/read_bltprobe.py\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
