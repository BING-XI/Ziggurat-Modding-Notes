#!/usr/bin/env python
r"""
build_wotw_field.py -- Weight of the World's field, the AoWEPACK half: movement costs double on a
field hex, and the movement-type flag the grounding uses.  AoWTCPCK half (the path step costs, the
grounding, Tremors): build_wotw_field_tc.py.  The field is marked by build_wotw_tc.py's landing:
bit 0x20 of [field+0x1B] on every hex within 6 of the target, for the rest of the battle.
Owner's design 2026-10-26 (05-spells-added.md).

THE ROUTER  every TMoveControl search costs a hex through the method pointer [mc+0x140]/[mc+0x144],
  set to one of two procs (EAX = the move control, EDX = the field, ECX passed through; EAX = the
  cost, negative = impassable).  Their immediates are retargeted to wrappers (each keeps its .reloc
  entry: the new value is another address in this image):
    M1a  0x55746637  Activate's ExploredOnlyMoveOnMovePointProc (0x5574642C) -> wrap_explored
    M1b  0x5574665B  Activate's DefaultMoveOnMovePointProc (0x557454D8)      -> wrap_default
    M1c  0x557454AA  Create's default proc                                    -> wrap_default
  A wrapper calls its proc; when the result r > 0 and the field carries bit 0x20, r += the hex's own
  table cost c (c > 0), at most 0x7F.  The terrain cost doubles; the zone-of-control surcharge does
  not; 0 (an attack target) and impassable stay.  Strategic fields never carry the bit.
THE FLAG  0x5577FDD3  TAbstractUnit.CreateMovePointTable's `call [edx+0xE8]` GetMoveTypes (6 B) ->
  call cave_types + nop: while the byte FLAG (BSS 0x558FAED0) is set and the types have the flying
  bit 2, the types become (types & ~2) | 1 -- a walker's table, with every per-unit adjustment the
  function makes after (Enchanted Roads, Wheeled, race rows, build_race_terrain_move.py's cave).
  build_wotw_field_tc.py sets FLAG around its own CreateMovePointTable call for a grounded mover.
  The function's entry (0x5577FDC4) is build_race_terrain_move.py's jmp; independent.
RNG: none.  Slot 0x558C1000-0x558C1FFF, exclusive.  PIC.  Surgical --undo.

    python build_scripts/build_wotw_field.py            dry run + state
    python build_scripts/build_wotw_field.py --apply
    python build_scripts/build_wotw_field.py --undo
    python build_scripts/build_wotw_field.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic

FIELD_BIT = 0x20
SLOT = (0x558C1000, 0x558C2000)
FLAG = 0x558FAED0                          # BSS, free per 12-re-toolchain.md (0x558FAED0..DF)
PROC_EXPLORED, PROC_DEFAULT = 0x5574642C, 0x557454D8
IMM = {"M1a": (0x55746637, PROC_EXPLORED, "explored"), "M1b": (0x5574665B, PROC_DEFAULT, "default"),
       "M1c": (0x557454AA, PROC_DEFAULT, "default")}
T_SITE, T_VAN = 0x5577FDD3, "ff92e8000000"
A = {}


def c_wrap(va, proc):
    return asm(f"""
        push edx
        push eax
        call {proc:#x}
        pop  ecx
        pop  edx
        test eax, eax
        jle  w_out
        test byte ptr [edx + 0x1b], {FIELD_BIT:#x}
        je   w_out
        push ebx
        movsx ebx, byte ptr [edx + 0x14]
        shl  ebx, 4
        add  ebx, ecx
        movsx edx, byte ptr [edx + 0x15]
        movsx ebx, byte ptr [ebx + edx + 0x31]
        test ebx, ebx
        jle  w_pop
        add  eax, ebx
        cmp  eax, 0x7f
        jle  w_pop
        mov  eax, 0x7f
    w_pop:
        pop  ebx
    w_out:
        ret
    """, va)


def c_types(va):
    src = f"""
        call dword ptr [edx + 0xe8]
        push ebx
        {{ANC}}
        cmp  byte ptr [ebx + {{FLAG}}], 0
        pop  ebx
        je   t_out
        test al, 2
        je   t_out
        and  al, 0xfd
        or   al, 1
    t_out:
        ret
    """
    return pic(src, va, "ebx", {"FLAG": FLAG})


BUILDERS = [("explored", lambda va: c_wrap(va, PROC_EXPLORED)), ("default", lambda va: c_wrap(va, PROC_DEFAULT)),
            ("types", c_types)]


def layout():
    va, blobs = SLOT[0], []
    for name, b in BUILDERS:
        A[name] = va
        blob = b(va)
        blobs.append(("cave_" + name, va, blob))
        va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    return blobs


def checks(d):
    rb = lambda va, n: bytes(d[P.va2off(d, va):P.va2off(d, va) + n])
    for name, (va, proc, _w) in IMM.items():
        if rb(va - 6, 6) != bytes.fromhex("c78340010000"):
            sys.exit("ABORT: %s: `mov [ebx+0x140], imm32` is not at %08X" % (name, va - 6))


def main():
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d)
    hooks = [(va, struct.pack("<I", proc), struct.pack("<I", A[w])) for va, proc, w in IMM.values()]
    hooks.append((T_SITE, bytes.fromhex(T_VAN), b"\xE8" + struct.pack("<i", A["types"] - (T_SITE + 5)) + b"\x90"))
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    run("build_wotw_field -- Weight of the World's field (AoWEPACK)", hooks, blobs, SLOT,
        [(T_SITE, T_SITE + 6, 0x5577FDC4, 0x5577FFCC)], reloc_ok=[va for va, _p, _w in IMM.values()])


if __name__ == "__main__":
    main()
