#!/usr/bin/env python
r"""
build_healwrap_fixes.py -- close the LAST 8-bit heal-wrap sites, and land the two heal doublings
the DAM/HP pass missed (High Prayer was already doubled; Showers and Remedy were not).

FOUND BY (2026-08-24, user-prompted re-audit of the Regeneration claim)
-----------------------------------------------------------------------
A systematic sweep of every `SetHitPoints` call site in AoWEPACK.dpl -- all 92 byte-pattern hits on
vmt+0xE4 (strategic) and vmt+0x8C (combat) triaged by boundary-aligned disassembly -- left exactly
three sites with the NewTurn wrap idiom (8-bit `add dl, N` of a heal onto current HP, no cap):

  | site | function | live | window (15 B) |
  |------|----------|------|----------------|
  | 0x557F7DE3 | THighPrayer fast-combat Execute   | add dl,10 | 8B D0 80 C2 0A 8B C3 8B 08 FF 91 8C 00 00 00 |
  | 0x557F7EC6 | THighPrayer tactical Execute      | add dl,10 | same, unit in EBX, combat setter +0x8C |
  | 0x557A1DDD | THealingShowersTE.Process         | add dl,3  | 8B D0 80 C2 03 8B C6 8B 08 FF 91 E4 00 00 00 |

`SetHitPoints` itself (TUnit/THero @0x557827C4/0x55787048) clamps to max and floors negatives at 0
-- so the ONLY failure mode is the 8-bit add wrapping past 127 into a negative char BEFORE the
setter sees it, which the setter then turns into 0 HP. With the HP cap at 120, High Prayer zeroes
any friendly unit at cur >= 118 -- it heals the whole side, so full-health units qualify.

Every other adder is safe by construction (verified by decompile/disassembly): HealUnit caps at
missing HP first; Remedy computes 32-bit and clamps at max; HealingWater/CallHero/HealUnits/
NaturesBlessing set cur = max; lifesteal adds 32-bit and relies on the setter clamp; damage
subtraction floors at 0 by design. The old cave_5580C150 lifesteal also carries an uncapped add but
is DEAD (bypassed by build_lifesteal_roundattack.py -- do not resurrect it).

THE FIX -- same shape as build_newturn_healcap.py
-------------------------------------------------
Each 15-byte window (which starts right after the GetHitPoints call, so AL = current HP) becomes
`call cave` + 10 NOPs. The cave does the sum in 32 bits and pre-clamps at 127; the setter then
applies the exact max clamp:

    movsx edx, al ; add edx, HEAL ; if (edx > 127) edx = 127 ; SetHitPoints(unit, edx)

Position-independent: register-indirect virtual calls only, no globals; `.reloc` scanned over all
three windows -- no entries displaced.

TWO MISSED DOUBLINGS LAND HERE TOO (single ownership):
  * Healing Showers 3 -> 6 (the draft manifest carried it as a singular-`imm` row, which the
    converter skipped -- found only by this sweep; the Spells.pfs text already says "Heal +6").
    ⚠ the 3 was a Ziggurat HAND EDIT (vanilla 5); 6 preserves the user's own ratio, decision H17.
  * Remedy `add esi,5` imm @0x557E739F -> 10 (same converter gap; wrap-safe shape, plain poke).

USAGE
    python build_healwrap_fixes.py            verify / dry run
    python build_healwrap_fixes.py --dis      also disassemble the caves
    python build_healwrap_fixes.py --apply
    python build_healwrap_fixes.py --undo     restore all three windows + Remedy, zero the caves
"""
import os, sys, struct, shutil, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_statdouble import kill_aow  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-healwrap")
IMAGE_BASE = 0x55700000

#        hook VA      original window (15 B)                              cave VA      unit  setter  heal
SITES = [
    (0x557F7DE3, "8bd080c20a8bc38b08ff918c000000", 0x55818100, "ebx", 0x8C, 10, "High Prayer fast-combat heal"),
    (0x557F7EC6, "8bd080c20a8bc38b08ff918c000000", 0x55818130, "ebx", 0x8C, 10, "High Prayer tactical heal"),
    (0x557A1DDD, "8bd080c2038bc68b08ff91e4000000", 0x55818160, "esi", 0xE4, 6,  "Healing Showers heal (3 -> 6 here)"),
]
HOOK_LEN = 15
CAVE_MAX = 0x30
REMEDY_IMM = 0x557E739F          # add esi, 5 @0x557E739D
REMEDY_OLD, REMEDY_NEW = 5, 10


def va2off(d, va):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    sec, rva = e + 24 + opt, va - IMAGE_BASE
    for _ in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, sec + 8)
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
        sec += 40
    return None


def build_cave(cave_va, unitreg, setter, heal):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    src = """
        movsx edx, al
        add  edx, %d
        cmp  edx, 0x7F
        jle  _s
        mov  edx, 0x7F
    _s:
        mov  eax, %s
        mov  ecx, [eax]
        call dword ptr [ecx + 0x%X]
        ret
    """ % (heal, unitreg, setter)
    body = bytes(ks.asm(src, cave_va)[0])
    assert len(body) <= CAVE_MAX
    return body


def hook_bytes(hook_va, cave_va):
    return b"\xe8" + struct.pack("<i", cave_va - (hook_va + 5)) + b"\x90" * (HOOK_LEN - 5)


def main():
    ap = argparse.ArgumentParser(description="heal 8-bit wrap fixes + missed heal doublings")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()

    d = bytearray(open(TARGET, "rb").read())
    states = []
    print("build_healwrap_fixes -- the last three 8-bit heal-wrap sites + Remedy\n")
    for hva, orig_hex, cva, reg, slot, heal, name in SITES:
        ho, co = va2off(d, hva), va2off(d, cva)
        orig = bytes.fromhex(orig_hex)
        cave = build_cave(cva, reg, slot, heal)
        hook = hook_bytes(hva, cva)
        cur = bytes(d[ho:ho + HOOK_LEN])
        st = "clean" if cur == orig else "applied" if cur == hook else "FOREIGN"
        print("  %-36s hook %08X -> cave %08X (%2d B, heal %d)  %s" % (name, hva, cva, len(cave), heal, st))
        if st == "FOREIGN":
            sys.exit("ABORT: window holds %s" % cur.hex(" "))
        if st == "clean":
            zone = bytes(d[co:co + CAVE_MAX])
            if any(zone):
                sys.exit("ABORT: cave zone %08X not free." % cva)
        if a.dis:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(cave, cva):
                print("      %08X  %-18s %s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))
        states.append((st, ho, co, orig, cave, hook))
    ro = va2off(d, REMEDY_IMM)
    rcur = d[ro]
    rst = "clean" if rcur == REMEDY_OLD else "applied" if rcur == REMEDY_NEW else "FOREIGN"
    print("  %-36s imm  %08X  add esi,%d -> %d   %s" % ("Remedy heal", REMEDY_IMM, REMEDY_OLD, REMEDY_NEW, rst))
    if rst == "FOREIGN":
        sys.exit("ABORT: Remedy imm holds %d." % rcur)

    allstates = {s for s, *_ in states} | {rst}
    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written; state %s)" % sorted(allstates))
        return
    want = "clean" if a.undo else "applied"
    if allstates == {want}:
        print("\nnothing to do -- already %s (idempotent)." % want)
        return
    kill_aow()
    if not a.undo and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP); print("  backup -> %s" % os.path.basename(BACKUP))
    for (st, ho, co, orig, cave, hook) in states:
        if a.undo:
            d[ho:ho + HOOK_LEN] = orig
            d[co:co + CAVE_MAX] = b"\x00" * CAVE_MAX
        else:
            d[co:co + len(cave)] = cave
            d[ho:ho + HOOK_LEN] = hook
    d[ro] = REMEDY_OLD if a.undo else REMEDY_NEW
    open(TARGET, "wb").write(bytes(d))
    print("\n%s -- 3 heal sites %s, Remedy at %d." %
          ("UNDONE" if a.undo else "APPLIED",
           "restored" if a.undo else "now 32-bit + clamped", REMEDY_OLD if a.undo else REMEDY_NEW))


if __name__ == "__main__":
    main()
