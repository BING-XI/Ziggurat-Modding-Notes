#!/usr/bin/env python
r"""
build_imbue.py -- Imbue Altar (spell 93, Death/Earth tier 2) and Imbue Spring (spell 94, Life/Earth
tier 2), world-map rituals that place the game's own Blood Shrine and Spring of Life.  AoWEPACK.dpl.
Data: build_imbue_pfs.py (Spells.pfs records 103-104).  Owner's design 2026-10-26 (05-spells-added.md,
"Imbue Altar and Imbue Spring -- agreed design"): 60 mana each, Ritualist, a target hex as Surtr's
Chasm takes one; the structure is neutral and blesses whoever steps on it, as a map-placed one does;
the Spring of Life never on Snow or Wasteland, where it would not bless.

THE SPELLS -- TLevelTerrain INSTANCES (classref cell 0x5579D2B8, Create 0x5579F1D0), registered at
  0x557A2498 (Watcher's `call RegisterSpell` in RegisterGlobalTargetSpells, replayed first).  Mana 60,
  research 160 (the single tier-3 figure: it prices Wizard's Tower offers), upkeep 0, sphere 7 (dual:
  build_dual_sphere.py's TABLE holds Death+Earth and Life+Earth), tier 2.  build_surtrs_chasm.py's
  TLevelTerrain caves send both ids here: cave_vt and cave_vts to IMB_VT, cave_rad to the one-hex
  cursor, cave_exec to IMB_EXEC.

THE STRUCTURES -- found at run time in the set's resource list ([[AoWHSSet+0x24]+8]) by class:
  TBloodShrineResource (ClassID 0x20131) for 93, TSpringOfLifeResource (0x20101) for 94; the
  Release set holds one of each (STR_BLDS.ILB, STR_SOL.ILB).  No resource: the spell has no valid
  target.

THE TARGET (IMB_VT, eax = spell, edx = field -> al): every hex of the resource's footprint
  (TTerrainList [res+0x28], walked with InitHNWalk from the target, as construction walks it) is on
  the map, has no owner (TAoWMapField.GetPlayer = -1), no structure (FindNoneTransparentHS), no
  mountain (overlay 0) and no overlay 2, and terrain Grass, Desert, Snow, Steppe, Wasteland or Dirt
  (1-5, 0x0C) -- TStructureConstructionControl.ValidateLocation's rules, with "no owner" for "the
  builder's".  Imbue Spring also refuses Snow (3) and Wasteland (5) on the target hex, the field
  TSpringOfLife.ArmyPlaced reads.  Level Terrain's own tests (no structure, no army) follow.
THE CAST (IMB_EXEC, inside TLevelTerrainTE.Process after PlayDefaultEffects, before the mana; eax =
  the event, x [+0x20], y [+0x21], level [+0x22]): THSMap.ClearTerrain on every footprint hex, then
  the resource's PlaceResourceUser (VMT +0x68: eax resource, edx map, cl x, push y, push level),
  as TConstructStructureTE.Execute builds a tower or shipyard.  The structure is saved with the map
  as any map-placed one is; it has no owner.

RNG: none (the token event runs on every peer; ClearTerrain and the placement draw nothing).
Slot 0x558C3000-0x558C37FF, exclusive.  PIC.  Pinned entries: VT +0, EXEC +5, REG +10.  Surgical
--undo.  The registration runs at package init: proved only by launching the exe.

Couplings
  * build_surtrs_chasm.py dispatches ids 93 and 94 to IMB_VT / IMB_EXEC; either can be undone alone
    (without this script the spells are not registered, so the dispatch is never taken).

    python build_scripts/build_imbue.py            dry run + state
    python build_scripts/build_imbue.py --apply
    python build_scripts/build_imbue.py --undo
    python build_scripts/build_imbue.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic, ansistr

ALTAR, SPRING = 93, 94
NAMES = {ALTAR: "Imbue Altar", SPRING: "Imbue Spring"}
RES_CLASS = {ALTAR: 0x20131, SPRING: 0x20101}
MANA, RESEARCH, UPKEEP, SPHERE, TIER = 60, 160, 0, 7, 2
SLOT = (0x558C3000, 0x558C3800)
ENTRIES = ("vt", "exec", "reg")
ENTRY = {n: SLOT[0] + 5 * i for i, n in enumerate(ENTRIES)}

AOWHSMAP, AOWHSSET = 0x558FA040, 0x558FA044
LT_CELL, LT_CREATE = 0x5579D2B8, 0x5579F1D0
REGISTER_SPELL, LSTRASG = 0x55779B40, 0x55701150
GETMAPLEVEL, LEVEL_GETFIELD = 0x557020EC, 0x557020DC
INITHNWALK, WALKTONEXT, TL_GETUSED = 0x557026D4, 0x557026DC, 0x55701C9C
FIELD_GETPLAYER, FIND_NT_HS, STRUCT_CELL = 0x55771C98, 0x55702004, 0x55713BD8
CLEARTERRAIN = 0x557025DC
SNOW, WASTELAND = 3, 5
LAND = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5) | (1 << 0xC)
REG_SITE = 0x557A2498
A = {}


def r_find(va):
    """eax = spell id -> eax = the resource or 0; ebx = anchor (kept)."""
    return pic(f"""
        push esi
        push edi
        mov  edx, {RES_CLASS[ALTAR]:#x}
        cmp  eax, {ALTAR}
        je   f_go
        mov  edx, {RES_CLASS[SPRING]:#x}
        cmp  eax, {SPRING}
        jne  f_no
    f_go:
        push edx
        {{ANC}}
        mov  eax, dword ptr [esi + {{SET}}]
        mov  eax, dword ptr [eax + 0x24]
        mov  edi, dword ptr [eax + 8]
        xor  esi, esi
    f_loop:
        cmp  esi, dword ptr [edi + 8]
        jge  f_none
        mov  eax, dword ptr [edi + 4]
        mov  eax, dword ptr [eax + esi*4]
        inc  esi
        test eax, eax
        je   f_loop
        push eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x24]
        mov  edx, eax
        pop  eax
        cmp  edx, dword ptr [esp]
        jne  f_loop
        pop  edx
        pop  edi
        pop  esi
        ret
    f_none:
        pop  edx
    f_no:
        xor  eax, eax
        pop  edi
        pop  esi
        ret
    """, va, "esi", {"SET": AOWHSSET})


def r_vt(va):
    """eax = spell, edx = field -> al.  Frame (ebp): +0 resource, +4 the field's level object,
    +8 spell id, +0x10.. the hex walker (+8 HN, +0x10 x, +0x14 y)."""
    return pic(f"""
        push ebp
        push ebx
        push esi
        push edi
        sub  esp, 0x30
        mov  ebp, esp
        mov  esi, edx
        mov  eax, dword ptr [eax + 0x10]
        mov  dword ptr [ebp + 8], eax
        cmp  eax, {SPRING}
        jne  v_find
        mov  cl, byte ptr [esi + 0x14]
        cmp  cl, {SNOW}
        je   v_no
        cmp  cl, {WASTELAND}
        je   v_no
    v_find:
        call {A['find']:#x}
        test eax, eax
        je   v_no
        mov  dword ptr [ebp], eax
        {{ANC}}
        movsx edx, byte ptr [esi + 0x12]
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x10]
        call {GETMAPLEVEL:#x}
        mov  dword ptr [ebp + 4], eax
        push 0
        movsx ecx, byte ptr [esi + 0x11]
        movsx edx, byte ptr [esi + 0x10]
        lea  eax, [ebp + 0x10]
        call {INITHNWALK:#x}
    v_loop:
        mov  eax, dword ptr [ebp]
        mov  eax, dword ptr [eax + 0x28]
        mov  ecx, dword ptr [ebp + 0x18]
        cmp  ecx, dword ptr [eax + 4]
        jge  v_yes
        mov  edx, ecx
        call {TL_GETUSED:#x}
        test al, al
        je   v_next
        mov  edx, dword ptr [ebp + 0x20]
        mov  ecx, dword ptr [ebp + 0x24]
        test edx, edx
        jl   v_no
        test ecx, ecx
        jl   v_no
        mov  eax, dword ptr [ebp + 4]
        cmp  edx, dword ptr [eax + 0xc]
        jge  v_no
        cmp  ecx, dword ptr [eax + 0x10]
        jge  v_no
        call {LEVEL_GETFIELD:#x}
        mov  edi, eax
        test edi, edi
        je   v_no
        movzx ecx, byte ptr [edi + 0x14]
        cmp  ecx, 15
        ja   v_no
        mov  eax, {LAND:#x}
        bt   eax, ecx
        jae  v_no
        mov  al, byte ptr [edi + 0x15]
        test al, al
        je   v_no
        cmp  al, 2
        je   v_no
        mov  eax, edi
        call {FIELD_GETPLAYER:#x}
        cmp  al, 0xff
        jne  v_no
        mov  edx, dword ptr [ebx + {{STRUCT}}]
        mov  eax, edi
        call {FIND_NT_HS:#x}
        test eax, eax
        jne  v_no
    v_next:
        lea  eax, [ebp + 0x10]
        call {WALKTONEXT:#x}
        jmp  v_loop
    v_yes:
        mov  al, 1
        jmp  v_out
    v_no:
        xor  eax, eax
    v_out:
        add  esp, 0x30
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret
    """, va, "ebx", {"MAP": AOWHSMAP, "STRUCT": STRUCT_CELL})


def r_exec(va):
    """eax = the TLevelTerrainTE.  Frame (ebp): +0 resource, +4 level object, +8 the event,
    +0x10.. the hex walker."""
    return pic(f"""
        push ebp
        push ebx
        push esi
        push edi
        sub  esp, 0x30
        mov  ebp, esp
        mov  esi, eax
        mov  dword ptr [ebp + 8], eax
        mov  eax, dword ptr [esi + 0x10]
        call {A['find']:#x}
        test eax, eax
        je   x_out
        mov  dword ptr [ebp], eax
        {{ANC}}
        movsx edx, byte ptr [esi + 0x22]
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x10]
        call {GETMAPLEVEL:#x}
        mov  dword ptr [ebp + 4], eax
        push 0
        movsx ecx, byte ptr [esi + 0x21]
        movsx edx, byte ptr [esi + 0x20]
        lea  eax, [ebp + 0x10]
        call {INITHNWALK:#x}
    x_loop:
        mov  eax, dword ptr [ebp]
        mov  eax, dword ptr [eax + 0x28]
        mov  ecx, dword ptr [ebp + 0x18]
        cmp  ecx, dword ptr [eax + 4]
        jge  x_place
        mov  edx, ecx
        call {TL_GETUSED:#x}
        test al, al
        je   x_next
        mov  edx, dword ptr [ebp + 0x20]
        mov  ecx, dword ptr [ebp + 0x24]
        test edx, edx
        jl   x_next
        test ecx, ecx
        jl   x_next
        mov  eax, dword ptr [ebp + 4]
        cmp  edx, dword ptr [eax + 0xc]
        jge  x_next
        cmp  ecx, dword ptr [eax + 0x10]
        jge  x_next
        movsx eax, byte ptr [esi + 0x22]
        push eax
        push 0
        push -1
        mov  eax, dword ptr [ebx + {{MAP}}]
        call {CLEARTERRAIN:#x}
    x_next:
        lea  eax, [ebp + 0x10]
        call {WALKTONEXT:#x}
        jmp  x_loop
    x_place:
        movsx eax, byte ptr [esi + 0x21]
        push eax
        movsx eax, byte ptr [esi + 0x22]
        push eax
        movsx ecx, byte ptr [esi + 0x20]
        mov  edx, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [ebp]
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0x68]
    x_out:
        add  esp, 0x30
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret
    """, va, "ebx", {"MAP": AOWHSMAP})


def r_reg(va):
    """Watcher's `call RegisterSpell` (ebx = the spell control): replayed, then 93 and 94."""
    one = lambda sid, lit: f"""
        mov  eax, dword ptr [esi + {{CELL}}]
        xor  ecx, ecx
        mov  dl, 1
        call {LT_CREATE:#x}
        mov  edi, eax
        lea  eax, [edi + 8]
        lea  edx, [esi + {{{lit}}}]
        call {LSTRASG:#x}
        mov  dword ptr [edi + 0x10], {sid}
        mov  dword ptr [edi + 0x14], {MANA}
        mov  dword ptr [edi + 0x18], {RESEARCH}
        mov  dword ptr [edi + 0x1c], {UPKEEP}
        mov  byte ptr [edi + 0x20], {SPHERE}
        mov  byte ptr [edi + 0x21], {TIER}
        mov  edx, edi
        mov  eax, ebx
        call {REGISTER_SPELL:#x}"""
    src = f"""
        call {REGISTER_SPELL:#x}
        push esi
        push edi
        {{ANC}}
        {one(ALTAR, "N1")}
        {one(SPRING, "N2")}
        pop  edi
        pop  esi
        ret
    """
    t1 = ansistr(NAMES[ALTAR])
    t1 += b"\0" * (-len(t1) % 4)
    return pic(src, va, "esi", {"CELL": LT_CELL, "N1": ("TAIL", 8), "N2": ("TAIL", len(t1) + 8)},
               t1 + ansistr(NAMES[SPRING]))


BUILDERS = [("find", r_find), ("vt", r_vt), ("exec", r_exec), ("reg", r_reg)]


def layout():
    base = (SLOT[0] + 5 * len(ENTRIES) + 15) & ~15
    for n, _b in BUILDERS:
        A.setdefault(n, base)
    for _ in range(3):
        va, blobs = base, []
        for n, b in BUILDERS:
            A[n] = va
            blob = b(va)
            blobs.append(("r_" + n, va, blob))
            va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    jt = b"".join(b"\xE9" + struct.pack("<i", A[n] - (ENTRY[n] + 5)) for n in ENTRIES)
    return [("entries", SLOT[0], jt)] + blobs


def checks(d):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    u = lambda v: struct.unpack_from("<I", d, P.va2off(d, v))[0]
    rb = lambda va, n: bytes(d[P.va2off(d, va):P.va2off(d, va) + n])
    vmt = u(LT_CELL)
    if rb(u(vmt - 0x20) + 1, 13) != b"TLevelTerrain":
        sys.exit("ABORT: %08X no longer holds TLevelTerrain" % LT_CELL)
    if rb(u(u(STRUCT_CELL) - 0x20) + 1, 10) != b"TStructure":
        sys.exit("ABORT: %08X no longer holds TStructure" % STRUCT_CELL)
    if rb(REG_SITE - 4, 4) != bytes.fromhex("8bd08bc3"):
        sys.exit("ABORT: Watcher's registration site moved")
    _e, secs = P.sections(d)
    for _vs, sva, rs, ra in secs:            # nobody else creates spell 93 or 94
        for i in range(ra, ra + rs - 7):
            src = P.IMAGE_BASE + sva + (i - ra)
            if SLOT[0] <= src < SLOT[1]:
                continue
            if d[i] == 0xC7 and d[i + 1] in range(0x40, 0x48) and d[i + 2] == 0x10 \
                    and struct.unpack_from("<I", d, i + 3)[0] in (ALTAR, SPRING):
                sys.exit("ABORT: %08X also stores spell id %d" % (src, struct.unpack_from("<I", d, i + 3)[0]))
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for n, va, blob in layout()[1:]:
        code = blob
        for lit in (ansistr(NAMES[ALTAR]), ansistr(NAMES[SPRING])):
            if lit in code:
                code = code[:code.index(lit)]
        code = code.rstrip(b"\x90\x00")
        ins = list(md.disasm(code, va))
        assert sum(i.size for i in ins) == len(code), "%s does not disassemble cleanly" % n
        for i in ins:
            if i.mnemonic == "push" and i.op_str.startswith("0x"):
                v = int(i.op_str, 16)
                assert v < 0x80 or v == 0xFFFFFFFF, "%08X: push %s (imm8 sign trap)" % (i.address, i.op_str)


def main():
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d)
    rel = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
    hooks = [(REG_SITE, rel(REG_SITE, REGISTER_SPELL), rel(REG_SITE, ENTRY["reg"]))]
    print("  routines: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    run("build_imbue -- Imbue Altar and Imbue Spring (AoWEPACK)", hooks, blobs, SLOT,
        [(REG_SITE, REG_SITE + 5, 0x557A23A4, 0x557A24FE)])


if __name__ == "__main__":
    main()
