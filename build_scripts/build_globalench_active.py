#!/usr/bin/env python
r"""
build_globalench_active.py -- a loaded game's global enchantments are active again, so they can be
cancelled and dispelled.  AoWEPACK.dpl.

THE DEFECT (vanilla)
    Bit 0 of TGlobalEnchantment[+0x10] means "active".  Activate 0x5577DBA0 sets it and adds the
    enchantment to TGlobalMagicControl's list ([[AoWHSMap]+0x188]+0x14); Deactivate 0x5577DC3C clears
    it and removes (or destroys) the enchantment.  At run time, then, "in the list" and "bit 0 set"
    are the same thing.  But TGlobalEnchantment.ReadWrite 0x5577DA1C streams +8, +0x14, +0x18, +0x19,
    +0x1C and +0x20 and not +0x10, so after a load every listed enchantment has bit 0 clear.  The
    control's rebuild pass, UpdateActiveEnchantments 0x5577E46C (called from its ReadWrite at
    0x5577E215 and from Update at 0x5577E411), recomputes only its own type set.
    Vanilla readers that return early on a clear bit 0 (the `test byte [reg+0x10],1`):
        TCityEnchantment.Deactivate       0x557AE308   (every city enchantment)
        TSmokeCloudEnchantment.Deactivate 0x5579C348
        TWatcherEnchantment.Deactivate    0x5579F7A8
        TWatcherHS.Deactivate             0x5579FE6E
    Remove 0x5577E077 and Dispel 0x5577DED7 reach them through VMT +0x60.  So after a reload,
    cancelling or dispelling one of those enchantments does nothing, and it stays listed with its
    upkeep.  Found through Inioch's share9 (patch_globalench_loadactive_v1.py, where it broke his own
    "is spell X active" caves); the vanilla readers above are ours.

THE PATCH
    LB 0x5577E493, inside the pass's per-member loop with EAX = the member: the 5 bytes
    `mov dl,[eax+0x18] / mov eax,esp` (8A 50 18 8B C4) -> `call cave_lb`:
        or byte ptr [eax+0x10], 1      ; listed = active
        mov dl, byte ptr [eax+0x18]    ; replayed
        lea eax, [esp+4]               ; replayed `mov eax,esp`: the caller's ESP, past our return
        ret
    The pass runs after every load, every save and every Activate/Deactivate, after the list has
    changed, so it only restores the run-time truth.

Slot 0x558B3900-0x558B39FF, exclusive (12 B used).  No absolute address: PIC.  No .reloc under the
hook.

RNG: none.  Every peer loads the same list and sets the same bits.

Unproven, static checks cannot reach it: that a dispel after a reload now ends the enchantment and
its upkeep.

    python build_scripts/build_globalench_active.py            dry run + state
    python build_scripts/build_globalench_active.py --apply
    python build_scripts/build_globalench_active.py --undo     surgical: the 5 bytes back, slot zeroed
    python build_scripts/build_globalench_active.py --dis
"""
import struct
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, run

SLOT = (0x558B3900, 0x558B3A00)
LB, LB_VAN, LB_RET = 0x5577E493, bytes.fromhex("8a50188bc4"), 0x5577E498
PASS_LO, PASS_HI = 0x5577E46C, 0x5577E4B4            # UpdateActiveEnchantments, up to its set constant

CAVE = SLOT[0]
blob = asm("""
    or   byte ptr [eax + 0x10], 1
    mov  dl, byte ptr [eax + 0x18]
    lea  eax, [esp + 4]
    ret
""", CAVE)
hook = b"\xE8" + struct.pack("<i", CAVE - LB_RET)

caves = [("cave_lb", CAVE, blob)]
hooks = [(LB, LB_VAN, hook)]
interior = [(LB, LB + len(LB_VAN), PASS_LO, PASS_HI)]

if __name__ == "__main__":
    run("build_globalench_active", hooks, caves, SLOT, interior)
