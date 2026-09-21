#!/usr/bin/env python3
r"""
combatunitguard.py -- the SHARED "is this combat object really a unit?" guard cave.

Imported by build_assassin.py and build_magebane.py.  Not a build script: it has no --apply of
its own.  Each importing script installs/verifies the blob through its own va2off, and calls
`undo_if_unused()` when it removes its own caves.

====================================================================================
WHY IT EXISTS -- the `combat + 0x4C` trap, in one paragraph
====================================================================================
`[combatobject + 0x4C]` is the link to the STRATEGIC unit, and it exists only on
`TCombatUnit`.  The class tree (walked live from the VMTs, 2026-09-11):

    TCombatObject   VMT 0x557158EC  instsize 0x4C     <-- has no +0x4C field AT ALL
      TCombatUnit   VMT 0x55715A94  instsize 0x5C     <-- +0x4C = the strategic unit
        TFastCombatUnit VMT 0x5571D4BC instsize 0x64  <-- inherits it (auto-resolve)
      TCombatWall   VMT 0x55715C40  instsize 0x50     <-- +0x4C..+0x4F are PACKED BYTES

On a wall, `+0x4C` = wall type and `+0x4D` = wall HP, so a stone wall reads back as the
dword `0x00002802` (type 2, HP 0x28 = 40).  That is a small NON-ZERO integer: it sails
through `test eax,eax`, and the next dereference faults.  A wall is a perfectly legal
melee AND ranged target, so any strike-path cave that reads `+0x4C` raw will crash the
moment its ability-holder swings at a walled city.

⚠⚠ `System.@IsClass` is NIL-SAFE but NOT GARBAGE-SAFE.  Its entry is VCL30.dpl RVA **0x3A14**
(export `System.@IsClass` = RVA 14868 = 0x3A14; the `ret` at 0x41303A13 ends the previous
function).  ⚠ **0x41303A18 is the LOOP BODY, not the entry** -- it is the back-edge target of the
`jne` at 0x41303A23, which is why it is the address a fault gets reported at, and why an earlier
attempt to hook this function's entry died with runtime 216: the back-edge lands inside the
displaced bytes.

    41303A14  85 c0        test eax,eax         <-- ENTRY: nil test
    41303A16  74 10        je  0x41303A28       ; -> ret with EAX==0, so AL==0
    41303A18  8b 00        mov eax,[eax]        ; @@loop -- the usual fault address
    41303A1A  39 d0        cmp eax,edx
    41303A1C  74 08        je  0x41303A26       ; @@success
    41303A1E  8b 40 e8     mov eax,[eax-0x18]   ; vmtParent, a PPClass
    41303A21  85 c0        test eax,eax
    41303A23  75 f3        jne 0x41303A18       ; back-edge into @@loop
    41303A25  c3           ret                  ; EAX==0 here, so AL==0
    41303A26  b0 01        mov al,1
    41303A28  c3           ret

So `IsClass(nil, C)` returns False safely.  What it has NO test for is a non-nil pointer that is
not an object: it goes straight to `mov eax,[eax]` to read the VMT.  **The defect class is a
GARBAGE object pointer** -- a TCombatWall's packed `+0x4C` bytes -- **not a nil one**.

This guard still nil-checks before calling @IsClass, deliberately: it lets a caller test ONE
result instead of leaning on a convention that reads as undefined at the call site, and it is the
house pattern already used by build_replaylog.py, build_combatlog_dll.py and
build_ranged_slayers.py.  (The loop back onto `mov eax,[eax]` is also why vmtParent at VMT-0x18
being a *pointer to a classref cell* works out.)

====================================================================================
THE TWO ENTRY POINTS
====================================================================================
    guard_unit(EAX = combat object)  -> EAX = [obj+0x4C] when obj is a TCombatUnit
                                        DESCENDANT (so TFastCombatUnit keeps the bonus),
                                        else 0.  Nil in = 0 out.
    guard_hero(EAX = combat object)  -> AL  = 1 iff that strategic unit is a THero,
                                        else 0.  Nil/wall in = 0 out.

Both clobber **EAX and the flags only** -- ECX, EDX, EBX, ESI, EDI and EBP all survive.
That matters: build_assassin.py's cave_melee keeps a live PIC anchor in EDI across the
call site, and cave_melee3 keeps the strike record in EBX.

Position-independent: the two classrefs are reached through a call/pop anchor
(AoWEPACK.dpl never loads at its preferred base), and everything else is rel32.

====================================================================================
CAVE OWNERSHIP
====================================================================================
    0x55849000 .. 0x558490FF   exclusive reservation, ~90 B used.
Chosen above build_powerleech.py's 0x55848000+0x400 (the previous high-water mark) and
verified zero before first write.  Add it to the table in Zig notes/12-re-toolchain.md
whenever that file is refreshed.
"""

import struct

# ---- the cave -------------------------------------------------------------------------
GUARD_VA    = 0x55849000
GUARD_LIMIT = 0x100                  # exclusive reservation; zeroed whole on a full undo
GUARD_UNIT  = GUARD_VA + 0x00
GUARD_HERO  = GUARD_VA + 0x40        # fixed sub-address so neither importer depends on
                                     # guard_unit's exact length

# ---- engine constants (all verified live, 2026-09-11) ---------------------------------
ISCLASS     = 0x557010C0   # AoWEPACK thunk -> VCL30.dpl!System.@IsClass (EAX=obj, EDX=classref -> AL)
TCU_CELL    = 0x55715A54   # CELL holding the TCombatUnit classref: [0x55715A54] = 0x55715A94.
                           # ⚠ A CELL, so `mov edx,[cell]`.  Contrast 0x5571D4BC, which is a VMT
                           # BASE and needs `lea`.  Getting that backwards makes the gate inert.
THERO_CELL  = 0x55711FAC   # CELL holding the THero classref: [0x55711FAC] = 0x55711FEC


def _asm(src, va):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, va)[0])


def _disp(target, anchor):
    """`[reg <sign> 0xNN]` displacement text. The cells sit BELOW any cave we allocate, so this is
    negative in practice -- and keystone cannot parse `[edi + 0x-1335B7]`, it needs the minus
    outside the literal."""
    d = target - anchor
    return "+ 0x%X" % d if d >= 0 else "- 0x%X" % -d


def blob():
    """The exact bytes for GUARD_VA .. GUARD_VA+len(blob). Deterministic; no placeholders."""
    # --- guard_unit -------------------------------------------------------------------
    # prologue is push*4 (4) + mov esi,eax (2) + call $+5 (5) = 11 bytes, so the anchor
    # (the address the `pop edi` yields) is GUARD_UNIT + 11.  Asserted below.
    a1 = GUARD_UNIT + 11
    src_unit = f"""
        push ecx
        push edx
        push esi
        push edi
        mov  esi, eax
        call 0x{a1:X}
        pop  edi
        test esi, esi
        jz   gu_no
        mov  edx, [edi {_disp(TCU_CELL, a1)}]
        mov  eax, esi
        call 0x{ISCLASS:X}
        test al, al
        jz   gu_no
        mov  eax, [esi + 0x4C]
        jmp  gu_out
    gu_no:
        xor  eax, eax
    gu_out:
        pop  edi
        pop  esi
        pop  edx
        pop  ecx
        ret
    """
    b_unit = _asm(src_unit, GUARD_UNIT)
    assert b_unit[6:11] == b"\xE8\x00\x00\x00\x00", \
        "guard_unit PIC anchor is not at +6 (%s)" % b_unit[:12].hex(" ")

    # --- guard_hero -------------------------------------------------------------------
    # call guard_unit (5) + test (2) + jz (2) + push ecx (1) + push edx (1) + call $+5 (5)
    a2 = GUARD_HERO + 16
    src_hero = f"""
        call 0x{GUARD_UNIT:X}
        test eax, eax
        jz   gh_no
        push ecx
        push edx
        call 0x{a2:X}
        pop  ecx
        mov  edx, [ecx {_disp(THERO_CELL, a2)}]
        call 0x{ISCLASS:X}
        pop  edx
        pop  ecx
        ret
    gh_no:
        xor  eax, eax
        ret
    """
    b_hero = _asm(src_hero, GUARD_HERO)
    assert b_hero[11:16] == b"\xE8\x00\x00\x00\x00", \
        "guard_hero PIC anchor is not at +11 (%s)" % b_hero[:18].hex(" ")

    out = bytearray(GUARD_HERO - GUARD_UNIT + len(b_hero))
    out[0:len(b_unit)] = b_unit
    assert len(b_unit) <= GUARD_HERO - GUARD_UNIT, "guard_unit overruns guard_hero's slot"
    out[GUARD_HERO - GUARD_UNIT:] = b_hero
    assert len(out) <= GUARD_LIMIT, "guard blob overruns its %d-byte reservation" % GUARD_LIMIT
    return bytes(out)


def show(prefix="   "):
    """Print the guard's disassembly. Read it -- keystone's `push imm` trap and friends."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    b = blob()
    print("%scave_guard @ %08X (%d B)  guard_unit=%08X  guard_hero=%08X"
          % (prefix, GUARD_VA, len(b), GUARD_UNIT, GUARD_HERO))
    # disassembled per ENTRY -- the zero padding between them desyncs a linear pass and prints
    # nonsense for guard_hero's first instructions.
    split = GUARD_HERO - GUARD_UNIT
    for va, part, name in ((GUARD_UNIT, b[:split], "guard_unit"), (GUARD_HERO, b[split:], "guard_hero")):
        print("%s  -- %s --" % (prefix, name))
        for ins in cs.disasm(part.rstrip(b"\x00") or part, va):
            print("%s  %08X %-24s%s %s" % (prefix, ins.address, ins.bytes.hex(" "),
                                           ins.mnemonic, ins.op_str))


def state(rd):
    """`rd(va, n) -> bytes`.  Returns 'ours' | 'free' | 'foreign'."""
    b = blob()
    cur = rd(GUARD_VA, len(b))
    if cur == b:
        return "ours"
    if not any(rd(GUARD_VA, GUARD_LIMIT)):
        return "free"
    return "foreign"


def patch_entry(rd):
    """The (va, expected_original, new_bytes, description) tuple for an importer's patch list.

    `expected_original` is whichever of {zeros, our blob} is actually on disk, so the caller's
    ordinary verify-before-write accepts both a virgin zone and a re-run -- and rejects anything
    else, which is what stops us silently overwriting a stranger's cave."""
    b = blob()
    cur = rd(GUARD_VA, len(b))
    orig = b if cur == b else bytes(len(b))
    return (GUARD_VA, orig, b, "cave_guard (shared TCombatUnit/THero guard)")


def callers(rd, lo=0x55701000, hi=0x558E7918, exclude=()):
    """Every `call rel32` in CODE that lands on guard_unit or guard_hero, outside `exclude`.

    `exclude` is a list of (lo, hi) VA ranges -- an importer passes its OWN caves so it does not
    count itself when deciding whether the shared guard is still needed.

    ⚠ The guard's own zone is always excluded: guard_hero calls guard_unit, so without this the
    cave counts itself as a live user and undo_if_unused() could never fire."""
    exclude = tuple(exclude) + ((GUARD_VA, GUARD_VA + GUARD_LIMIT),)
    blk = rd(lo, hi - lo)
    hits = []
    for i in range(len(blk) - 5):
        if blk[i] != 0xE8:
            continue
        src = lo + i
        tgt = src + 5 + struct.unpack_from("<i", blk, i + 1)[0]
        if tgt not in (GUARD_UNIT, GUARD_HERO):
            continue
        if any(a <= src < b for a, b in exclude):
            continue
        hits.append(src)
    return hits


def undo_if_unused(rd, wr, exclude=(), quiet=False):
    """Zero the guard cave, but ONLY if no cave outside `exclude` still calls it.

    Returns True when it was zeroed.  ⚠ The guard is SHARED between build_assassin.py and
    build_magebane.py; a script that zeroed it unconditionally on --undo would break the other
    feature's caves into a call through zeroed memory."""
    left = callers(rd, exclude=exclude)
    if left:
        if not quiet:
            print("[i] cave_guard %08X kept -- still called from %s"
                  % (GUARD_VA, ", ".join("%08X" % v for v in left)))
        return False
    wr(GUARD_VA, bytes(GUARD_LIMIT))
    if not quiet:
        print("[w] cave_guard %08X zeroed (%d B) -- no caller left" % (GUARD_VA, GUARD_LIMIT))
    return True


if __name__ == "__main__":
    show("")
