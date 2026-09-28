#!/usr/bin/env python
r"""
build_cave_flyer_morale.py -- flying units lose morale underground: -5 on Caverns, -10 on Depths,
-15 on the Abyss.  Units only; heroes and leaders are exempt, and so is any unit with Cave
Crawling.  AoWEPACK.dpl.
Owner request 2026-09-27 (heroes and Cave Crawling excluded the same day; re-tuned in place).

THE SITE
    TAbstractUnit.GetUnitMoraleValue @0x5577EED8 (VMT +0x17C) builds the raw morale value:
    relation value, then -- only when GetLocation returned a real hex -- the race-terrain pair
    (-10 disliked terrain, +10 liked terrain), then Unrest 0x35 (-40) and Panicked 0x6C (-80),
    then the [0,100] clamp.  The liked-terrain step is the last instruction of the location block:
        5577EF9B  73 03      jae  0x5577EFA0
        5577EF9D  83 C6 0A   add  esi, 0xa
        5577EFA0  ...        Unrest test (the merge point the no-location path also reaches)
    Those 5 bytes become `E9 -> cave_flymor`.  The cave replays them (a jmp leaves the flags from
    the preceding bt / cmp intact), then:
        level = byte [esp+4]        (GetLocation's level out-param; GetField consumed its push)
        penalty = PENALTY[level]    (none on Surface 0 or Firmament 3)
        if penalty and not IsClass(self, THero) and self has Flying (id 1, VMT +0x148)
                   and not Cave Crawling (id 4, VMT +0x148):
            esi -= penalty
    and jumps to 0x5577EFA0.  The penalty lands before the vanilla [0,100] clamp.  0x5577EF9B is
    itself a jump target (0x5577EF8E `ja`) and lands on the hook's first byte; nothing jumps into
    its interior (checked by the run helper).  Byte-identical to vanilla before this script.

WHO IT REACHES
    Five classes descend from TAbstractUnit.  TLeader overrides slot +0x17C with a constant 90 and
    never gets here.  THero is filtered by IsClass through the classref cell 0x55711FAC (call/pop
    anchor, the combatunitguard.py idiom), not by instance size: TUnit's size has already been
    grown 0x48 -> 0x94 by the unit-spellcasting work.  TUnit and TAdjustableUnit (editor-customised
    units) take the penalty; TWallUnit cannot fly.  The early exits for unowned units, unit type 2
    and the map's no-morale flag return 50 before the site, as they do for the terrain pair.
    Both abilities are queried item-aware (VMT +0x148), so an item or enchantment that grants
    Flying brings the penalty, and one that grants Cave Crawling lifts it.

WHEN IT IS SEEN
    The value is cached at [unit+0x26] by UpdateMoraleValue (callers: TAbstractUnit.Changed,
    TUnit.SetUnitResource, TArmy.UpdateFormation) -- the same refresh that moves the vanilla terrain
    pair, which reads the same GetLocation result.

LEVELS
    Stored index, not display order: Caverns 1, Depths 2, Abyss 4 (Firmament 3, Surface 0).  A
    sixth level would need a PENALTY entry.

Rolls: none (deterministic, MP-safe).  PIC: stack/register operands, one call/pop anchor, rel32
calls into IsClass's in-image thunk and back to the host.  Slot 0x55851800-0x5585187F, exclusive.
Surgical --undo.
"""
import struct
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run, TARGET, va2off

SLOT = (0x55851800, 0x55851880)
CAVE = 0x55851800
HOOK, VAN = 0x5577EF9B, bytes.fromhex("730383c60a")    # jae 0x5577EFA0 / add esi,0xa
RESUME = 0x5577EFA0
FN_LO, FN_HI = 0x5577EED8, 0x5577EFEC                   # TAbstractUnit.GetUnitMoraleValue

ISCLASS = 0x557010C0            # in-image thunk -> VCL30 System.@IsClass (EAX obj, EDX classref)
THERO_CELL = 0x55711FAC         # holds the THero classref 0x55711FEC (rebased by .reloc)
THERO_VMT = 0x55711FEC
FLYING = 1
CAVE_CRAWLING = 4
VMT_ABIL_ENABLED = 0x148

PENALTY = {1: 5, 2: 10, 4: 15}  # map level index -> raw morale lost by a flyer


def build(va):
    ladder = ""
    for lvl, pen in PENALTY.items():
        ladder += f"""
        mov ecx, {pen}
        cmp al, {lvl}
        je _lvl"""
    head = asm(f"""
        jae _t
        add esi, 0xa
    _t:
        mov al, byte ptr [esp + 4]
        {ladder}
        jmp _done
    _lvl:
        push ecx
        call _anc
    _anc:
    _done:
    """, va)
    # the anchor is the address `call _anc` pushes: the end of `head` minus the empty labels
    anc = va + len(head)
    body = asm(f"""
        jae _t
        add esi, 0xa
    _t:
        mov al, byte ptr [esp + 4]
        {ladder}
        jmp _done
    _lvl:
        push ecx
        call 0x{anc:X}
        pop edx
        mov edx, dword ptr [edx - 0x{anc - THERO_CELL:X}]
        mov eax, edi
        call 0x{ISCLASS:X}
        test al, al
        jnz _skip
        mov edx, {FLYING}
        mov eax, edi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x{VMT_ABIL_ENABLED:X}]
        test al, al
        jz _skip
        mov edx, {CAVE_CRAWLING}
        mov eax, edi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x{VMT_ABIL_ENABLED:X}]
        test al, al
        jnz _skip
        pop ecx
        sub esi, ecx
        jmp _done
    _skip:
        pop ecx
    _done:
        jmp 0x{RESUME:X}
    """, va)
    return body


def _check_anchor(blob, va):
    """The pop must sit at the call's return address and the next load must hit THERO_CELL."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    ins = list(md.disasm(blob, va))
    assert sum(len(x.bytes) for x in ins) == len(blob), "cave does not disassemble cleanly"
    for i, x in enumerate(ins):
        if x.mnemonic == "call" and x.operands[0].imm == x.address + 5:
            pop, load = ins[i + 1], ins[i + 2]
            assert pop.mnemonic == "pop" and pop.op_str == "edx", "anchor call not followed by pop edx"
            assert load.mnemonic == "mov" and pop.address + load.operands[1].mem.disp == THERO_CELL, \
                "anchor load does not reach THERO_CELL"
            return pop.address
    sys.exit("ABORT: no call/pop anchor in the cave")


blob = build(CAVE)
anchor = _check_anchor(blob, CAVE)
d = open(TARGET, "rb").read()
cell = struct.unpack_from("<I", d, va2off(d, THERO_CELL))[0]
if cell != THERO_VMT:
    sys.exit("ABORT: [%08X] = %08X, expected the THero classref %08X" % (THERO_CELL, cell, THERO_VMT))

caves = [("cave_flymor", CAVE, blob)]
hooks = [(HOOK, VAN, jmp_to(HOOK, CAVE, len(VAN)))]
interior = [(HOOK, HOOK + len(VAN), FN_LO, FN_HI)]

if __name__ == "__main__":
    run("build_cave_flyer_morale", hooks, caves, SLOT, interior)
