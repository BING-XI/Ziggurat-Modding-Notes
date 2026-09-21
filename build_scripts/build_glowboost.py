#!/usr/bin/env python3
r"""
AoW1 -- double the spellbook hover-glow intensity (aowInt.dpl).

The book's entry highlight is the BookWin "lit" strip drawn by TAOWBaseButton.Draw when the
hover flag [btn+0x134] is set (lit index [btn+0x12C]). It's a translucent blit, so drawing it
TWICE composites to roughly double intensity. Exactly two lit-draw call sites exist in
TAOWBaseButton.Draw (aowInt.dpl):

  @0x598113EF  call TInterfaceIL.DrawILLh (lib [btn+0x11C] flavor)
  @0x598114C1  call TInterfaceIL.DrawILI  (lib [btn+0x120] flavor)

Both are register calls (eax=lib, edx=index, ecx=&rect) + ONE stack arg (&draw-ctx), callee ret 4
(verified). Each site is re-pointed to a cave that: stashes the args in exe BSS scratch
(0x45BC04/08/0C -- free after the tier-research allocations), re-pushes the ctx, calls the
original, then IF (a) the host is the patched game exe (PE SizeOfImage == 0x211000 vanilla or
0x212000 with .tres -- aowInt.dpl is shared with AoWDevEd, whose globals differ; without this
guard the BookWin compare would deref editor garbage) and (b) the lib is the book's BookWin
TInterfaceIL ([[0x45A4A0]] IntGfxMod + 0xA0 = DFM child #23), draws a second time. Pressed-state
and up-state draws untouched; only BookWin-lib buttons (the spellbook) are affected.

Caves are position-independent: in-module rel32 calls; the absolute addresses referenced are all
in the EXE image (fixed base 0x400000, never rebased). Cave zone = the zero tail inside
aowInt.dpl's CODE section (content ends ~0x598227C6, VirtualSize runs to 0x5983D0E4, file-backed).

Backup: aowInt.dpl.pre-glowboost. Dry-run by default; --apply to write. Idempotent.
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL  = os.path.join(GAME, "aowInt.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-glowboost")
IB = 0x59800000

DRAWILLH = 0x59804028
DRAWILI  = 0x59803F84
SITE_LH  = 0x598113EF
SITE_ILI = 0x598114C1

BSS_LIB, BSS_IDX, BSS_RECT = 0x45BC04, 0x45BC08, 0x45BC0C   # exe BSS slack scratch
INTGFXMOD_GVAR = 0x45A4A0
BOOKWIN_OFF    = 0xA0            # IntGfxMod child #23 (BookWin) field
SOI_VANILLA, SOI_TRES = 0x211000, 0x212000

CAVE1 = 0x59822800               # zero tail of CODE (within VirtualSize, file-backed)

ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

def cave_src(draw):
    return f"""
    mov [0x{BSS_LIB:X}], eax
    mov [0x{BSS_IDX:X}], edx
    mov [0x{BSS_RECT:X}], ecx
    push dword ptr [esp+4]
    call 0x{draw:X}
    mov eax, [0x40003C]
    cmp eax, 0x1000
    jae Ldone
    mov eax, [eax+0x400050]
    cmp eax, 0x{SOI_VANILLA:X}
    je Lhost
    cmp eax, 0x{SOI_TRES:X}
    jne Ldone
Lhost:
    mov eax, [0x{BSS_LIB:X}]
    mov ecx, [0x{INTGFXMOD_GVAR:X}]
    mov ecx, [ecx]
    cmp eax, [ecx+0x{BOOKWIN_OFF:X}]
    jne Ldone
    push dword ptr [esp+4]
    mov eax, [0x{BSS_LIB:X}]
    mov edx, [0x{BSS_IDX:X}]
    mov ecx, [0x{BSS_RECT:X}]
    call 0x{draw:X}
Ldone:
    ret 4
"""

cave_lh = bytes(ks.asm(cave_src(DRAWILLH), CAVE1)[0])
CAVE2 = (CAVE1 + len(cave_lh) + 15) & ~15
cave_ili = bytes(ks.asm(cave_src(DRAWILI), CAVE2)[0])

for nm, va, code in (("cave_glow_lh", CAVE1, cave_lh), ("cave_glow_ili", CAVE2, cave_ili)):
    print(f"{nm} @ {va:08X} ({len(code)} bytes)")

def rel(site, dest):
    return struct.pack("<i", dest - (site + 5))

PATCHES = [
    (SITE_LH,  b"\xE8" + rel(SITE_LH, DRAWILLH), b"\xE8" + rel(SITE_LH, CAVE1),
     "lit DrawILLh -> cave_glow_lh"),
    (SITE_ILI, b"\xE8" + rel(SITE_ILI, DRAWILI), b"\xE8" + rel(SITE_ILI, CAVE2),
     "lit DrawILI -> cave_glow_ili"),
]

def load_secs(d):
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e+6)[0]
    optsz = struct.unpack_from('<H', d, e+20)[0]
    secs = []
    for i in range(nsec):
        b = e + 24 + optsz + i*40
        vs, va, rs, raw = struct.unpack_from('<IIII', d, b+8)
        secs.append((d[b:b+8].rstrip(b'\0').decode('latin1'), va, vs, raw, rs))
    return secs

def va2off(secs, va):
    r = va - IB
    for nm, v, vs, raw, rs in secs:
        if v <= r < v + max(vs, rs):
            return raw + (r - v)
    raise ValueError(hex(va))

def main():
    d = bytearray(open(DLL, 'rb').read())
    secs = load_secs(d)
    patches = list(PATCHES) + [
        (CAVE1, bytes(len(cave_lh)), cave_lh, f"cave_glow_lh @ {CAVE1:08X}"),
        (CAVE2, bytes(len(cave_ili)), cave_ili, f"cave_glow_ili @ {CAVE2:08X}"),
    ]
    ok = True; already = 0; todo = 0
    for va, orig, new, desc in patches:
        off = va2off(secs, va)
        cur = bytes(d[off:off+len(new)])
        if cur == new: already += 1
        elif cur == orig: todo += 1
        else:
            print(f"MISMATCH {desc}:\n  exp {orig.hex(' ')}\n  got {cur.hex(' ')}"); ok = False
    print(f"{already} already applied, {todo} to patch, {len(patches)} total")
    if not ok:
        print("ABORT: byte mismatch."); return 1
    if '--apply' not in sys.argv:
        print("Dry run OK. Re-run with --apply to write."); return 0
    if todo == 0:
        print("Nothing to do."); return 0
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copyfile(DLL, BACKUP); print(f"backup -> {BACKUP}")
    for va, orig, new, desc in patches:
        off = va2off(secs, va)
        d[off:off+len(new)] = new
    open(DLL, 'wb').write(d)
    print("applied.")
    return 0

sys.exit(main())
