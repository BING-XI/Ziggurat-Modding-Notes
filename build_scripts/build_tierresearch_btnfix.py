#!/usr/bin/env python3
r"""
AoW1 mod -- Research Book: move the slot BUTTONS with their panels (tier-research layout fix).

THE BUG  (measured live with re_tools/spellbook_geom.py -- NOT inferred from the DFM)
  ⚠ The DFM is misleading here. It lists `SxPnl` and `SxBtn` as flat siblings of the form with
  identical Tops, but AT RUNTIME each `SxBtn` is re-parented to become a CHILD of its `SxPnl`.
  A live dump of the Research Book proves it -- every button reports `parent = its own panel`:

      slot 0  pnl T=27  H=100  TopOff=16    btn T=27   H=100  TopOff=16   parent=THIS-PANEL
      slot 1  pnl T=131 H=100  TopOff=120   btn T=131  H=100  TopOff=120  parent=THIS-PANEL
      slot 2  pnl T=235 H=100  TopOff=224   btn T=235  H=100  TopOff=224  parent=THIS-PANEL

  So a button's `Top`/`TopOffset` are **relative to its panel**, and the panel is only 100 px
  tall. The values actually stored are PAGE-level Ys (the vanilla `30/110/190/270` pitch, or the
  research `16/120/224/328` pitch). Every row whose value is >= the panel height is therefore
  clipped completely outside its parent and can never be hit:

      row 0  -> TopOff 16 or 30   < 100  -> partly inside  -> CLICKABLE
      row 1  -> TopOff 120 or 110 > 100  -> clipped away   -> DEAD
      row 2  -> TopOff 224 or 190 > 100  -> clipped away   -> DEAD

  That is the reported "some sphere researches selectable, others not" / "only the first row is
  selectable" -- slots 0 and 4 are row 0 of the left and right page, and they are the only two
  that survive. The hover glow still paints (the panel is under the cursor), which is why an
  unresponsive entry visibly "bakes" whiter on repeated mouse-over: the book never repaints the
  parchment between paints, so the translucent lit strip accumulates.

  ⚠ This is NOT the vanilla `FillSlot` greying lock (`0x42EB97`-`0x42EC0D`), which is
  all-or-nothing and only fires while `magic+0x34 != 0`. See `Zig notes/04-spells-modded.md`.

  ⚠⚠ FAILED FIX, DO NOT RETRY: copying the panel's Y onto the button (`btn.Top = pnl.Top`).
  It looks right if you believe the DFM's sibling hierarchy, and it is exactly wrong -- writing a
  page-level Y into a panel-RELATIVE field. It reproduces the bug identically (row 0 only) and
  was measured doing so. The button must be positioned relative to its PANEL.

THE FIX -- a 6-byte hook JUST AFTER cave_layout returns, plus one small cave
  Hook `0x0042F2DC` (`mov esi,eax / dec esi / cmp esi,0`, 6 bytes, `.reloc`-free), which is the
  instruction immediately after `0x42F2D7 call cave_layout`. IN RESEARCH MODES ONLY the cave makes
  each button exactly fill its own panel -- `Top = 0`, `TopOffset = 0`, `Height = panel height` --
  then replays the three displaced instructions and jumps back to `0x0042F2E2`. `cmp` is replayed
  LAST and `jmp` does not touch flags, so the `jl` at `0x42F2E2` reads the flags it expects.

  Zero is unambiguously correct: the button already has `L=0, W=254` inside a `W=262` panel, so
  with `Top=0` and `Height=panel height` it covers its entry exactly. Cast/info modes are left
  alone (they use a different table and their own panel heights).

  ⚠ WHY NOT retarget the `call` at `0x42F2D7` (the smaller, obvious fix): that call IS one of
  `build_tierresearch_exe.py`'s verified HOOKS. Retargeting it was tried and reverted -- the
  tier script then fails its own "already applied" check and ABORTS with "file extends past
  ... with DIFFERENT content", which is a script that has NO `--undo` losing its ability to
  diagnose itself. `0x42F2DC` sits between its two verified sites in this function
  (`0x42F2D7` and `0x42F2F1` nilguard) and is claimed by neither, so both scripts verify clean.

  Cast/info modes are deliberately skipped: cave_layout writes a DIFFERENT (vanilla) table for
  them, and the cast book's buttons are already correct -- copying there could move them.

  Slot pairing (verified against the FillSlot call sites at 0x42F326+, where each slot pushes
  its button and passes its panel in ECX):
      slot 0 pnl 0x4C btn 0x114     slot 4 pnl 0xB4 btn 0x14C
      slot 1 pnl 0x64 btn 0x140     slot 5 pnl 0xCC btn 0x150
      slot 2 pnl 0x7C btn 0x144     slot 6 pnl 0xE4 btn 0x154
      slot 3 pnl 0x94 btn 0x148     slot 7 pnl 0xFC btn 0x158

  Control fields: `+0x88` absolute Y, `+0x80` height, `+0x7C` width, `[+0xD4]+0x20` alignment
  TopOffset -- all as used by `build_tierresearch_exe.py` itself.

WHERE THE CAVE LIVES -- ⚠ read this before touching build_tierresearch_exe.py
  In the `.tres` section's slack. That section is 0xEE0 bytes of blob in 0x1000 bytes of raw, so
  0x611EE0..0x611FFF (288 B) is mapped, executable and zero. `build_tierresearch_exe.py` only
  compares the first 0xEE0 bytes, so this cave does not disturb its "already applied" check.

  ⚠⚠ `build_tierresearch_exe.py` CANNOT re-apply over changed content -- it ABORTS with
  "file extends past ... with DIFFERENT content" and it has NO `--undo`. That is precisely why
  this fix is a separate call-retarget instead of an edit to `_layout_stores()`. If that script
  is ever rebuilt, re-run this one afterwards.

Both canonical mod exes `Ziggurat\AoWz.exe` + `Ziggurat\AoWzCompat.exe` are patched in lockstep
(AoWzCompat is AoWz + 1 byte; names from `zigexe.py`). Backups to <game dir>/backups/. Dry-run by
default; --apply to write; --undo to revert. Idempotent, verify-before-write. Close every AoW
binary first.
⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)
"""
import os, sys, struct, shutil

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                       # mod binary names (AoWz.exe / AoWzCompat.exe)
EXES = list(zigexe.EXES)
BACKUP_DIR = os.path.join(GAME, "backups")
IB = 0x00400000

HOOK_VA   = 0x0042F2DC            # mov esi,eax / dec esi / cmp esi,0  -- right after cave_layout
HOOK_ORIG = bytes.fromhex("8bf04e83fe00")   # 6 bytes, .reloc-free (asserted below)
RESUME_VA = 0x0042F2E2            # the `jl 0x42f326` that consumes cmp's flags
TABLE_VA  = 0x00611EE0            # .tres slack (blob ends 0x611EE0, raw ends 0x611FFF)
CODE_VA   = 0x00611F00
ZONE_END  = 0x00612000
MODE_OFF  = 0x220                 # TSpellBook mode byte: 2/3 = research

# (panel field, button field) per slot 0..7
PAIRS = [(0x4C, 0x114), (0x64, 0x140), (0x7C, 0x144), (0x94, 0x148),
         (0xB4, 0x14C), (0xCC, 0x150), (0xE4, 0x154), (0xFC, 0x158)]

APPLY = "--apply" in sys.argv
UNDO  = "--undo" in sys.argv


def table_bytes():
    b = b"".join(struct.pack("<HH", p, t) for p, t in PAIRS)
    assert len(b) == 32
    return b


def build_code():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    asm = f"""
        push eax
        push ecx
        push edx
        push esi
        push edi
        movzx eax, byte ptr [ebx + 0x{MODE_OFF:X}]
        sub  eax, 2
        cmp  eax, 1
        ja   Ldone
        xor  esi, esi
    Lloop:
        cmp  esi, 8
        jge  Ldone
        movzx edi, word ptr [0x{TABLE_VA:X} + esi*4]
        mov  eax, [ebx + edi]
        test eax, eax
        jz   Lnext
        movzx edi, word ptr [0x{TABLE_VA + 2:X} + esi*4]
        mov  ecx, [ebx + edi]
        test ecx, ecx
        jz   Lnext
        mov  edx, [eax + 0x80]
        mov  [ecx + 0x80], edx
        mov  dword ptr [ecx + 0x88], 0
        mov  edi, [ecx + 0xD4]
        test edi, edi
        jz   Lnext
        mov  dword ptr [edi + 0x20], 0
    Lnext:
        inc  esi
        jmp  Lloop
    Ldone:
        pop  edi
        pop  esi
        pop  edx
        pop  ecx
        pop  eax
        mov  esi, eax
        dec  esi
        cmp  esi, 0
        jmp  0x{RESUME_VA:X}
    """
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(asm, CODE_VA)
    return bytes(enc)


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    o, out = e + 24 + opt, []
    for _ in range(n):
        vs, va, rs, raw = struct.unpack_from("<IIII", d, o + 8)
        out.append((va, vs, raw, rs)); o += 40
    return out


def va2off(d, va):
    r = va - IB
    for va0, vs, raw, rs in sections(d):
        if va0 <= r < va0 + max(vs, rs):
            return raw + (r - va0)
    sys.exit(f"ABORT: VA {va:08X} outside every section")


def rel(site, dest):
    return struct.pack("<i", dest - (site + 5))


def reloc_vas(d):
    """Every VA carrying a base relocation -- displacing one would corrupt the fixup."""
    e = struct.unpack_from("<I", d, 0x3C)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 96 + 5 * 8)
    if size == 0:
        return set()
    base, out = va2off(d, IB + rva), set()
    p, end = base, base + size
    while p < end - 8:
        page, blk = struct.unpack_from("<II", d, p)
        if blk < 8:
            break
        for i in range((blk - 8) // 2):
            w = struct.unpack_from("<H", d, p + 8 + i * 2)[0]
            if w >> 12:
                out.add(IB + page + (w & 0xFFF))
        p += blk
    return out


def disasm(blob, va):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob, va):
        print(f"   {i.address:08X}  {i.mnemonic:<7} {i.op_str}")


def process(exe, code, tbl, show):
    path = os.path.join(GAME, exe)
    d = bytearray(open(path, "rb").read())
    co = va2off(d, CODE_VA); to = va2off(d, TABLE_VA); so = va2off(d, HOOK_VA)

    new_hook = b"\xE9" + rel(HOOK_VA, CODE_VA) + b"\x90" * (len(HOOK_ORIG) - 5)
    cur = bytes(d[so:so + len(HOOK_ORIG)])

    bad = sorted(v for v in reloc_vas(d) if HOOK_VA <= v < HOOK_VA + len(HOOK_ORIG))
    if bad:
        print(f"  {exe}: ABORT -- displaced range carries .reloc entries "
              f"{[hex(v) for v in bad]}"); return False

    have = bytes(d[co:co + len(code)]) == code and bytes(d[to:to + 32]) == tbl
    applied  = (cur == new_hook and have)
    pristine = (cur == HOOK_ORIG and
                all(b == 0 for b in d[to:va2off(d, ZONE_END)]))

    if show:
        print(f"[tierresearch button-Y fix]  hook {HOOK_VA:08X} -> cave {CODE_VA:08X} "
              f"({len(code)} B code + 32 B table, zone {ZONE_END - TABLE_VA} B), "
              f"resume {RESUME_VA:08X}")
        disasm(code, CODE_VA)
    print(f"  {exe}: {'APPLIED' if applied else 'PRISTINE' if pristine else 'UNKNOWN'}")

    if UNDO:
        if pristine: print(f"  {exe}: already pristine"); return True
        if not applied: print(f"  {exe}: ABORT -- not cleanly applied, refusing"); return False
        if not APPLY: print(f"  {exe}: [dry] would restore 6 bytes + zero cave"); return True
        d[so:so + len(HOOK_ORIG)] = HOOK_ORIG
        for i in range(to, va2off(d, ZONE_END)): d[i] = 0
        open(path, "wb").write(d); print(f"  {exe}: reverted"); return True

    if applied: print(f"  {exe}: already applied"); return True
    if not pristine:
        print(f"  {exe}: ABORT -- hook site is {cur.hex(' ')} (expected {HOOK_ORIG.hex(' ')}) "
              f"or cave zone not free"); return False
    if CODE_VA + len(code) > ZONE_END:
        print(f"  {exe}: ABORT -- cave overflows .tres slack"); return False
    if not APPLY: print(f"  {exe}: [dry] fits, call site verified"); return True

    os.makedirs(BACKUP_DIR, exist_ok=True)
    bp = os.path.join(BACKUP_DIR, exe + ".pre-tierresearchbtnfix")
    if not os.path.exists(bp): shutil.copy2(path, bp); print(f"  [bak] {bp}")
    d[to:to + 32] = tbl
    d[co:co + len(code)] = code
    d[so:so + len(HOOK_ORIG)] = new_hook
    try:
        open(path, "wb").write(d)
    except PermissionError:
        sys.exit("[x] LOCKED -- close every AoW binary first (%s)"
                 % ", ".join(zigexe.ALL_EXES))
    print(f"  {exe}: applied"); return True


def main():
    code, tbl = build_code(), table_bytes()
    ok = all(process(e, code, tbl, i == 0) for i, e in enumerate(EXES))
    if not APPLY and ok:
        print("\nDry run OK. Re-run with --apply to write.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
