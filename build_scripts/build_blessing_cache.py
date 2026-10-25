#!/usr/bin/env python
r"""
build_blessing_cache.py -- High Prayer's blessing and the Blood Shrine's Bloodlust reach a unit's
stats at once.  AoWEPACK.dpl.

THE DEFECT (vanilla; the class build_debuffcache.py fixed for Web and Entangle)
    TUnit serves ATK/DEF/RES/DAM from a cached block at unit+0x44..+0x47 that only TUnit.Changed
    (unit VMT +0x90, 0x55782B34) rebuilds.  TAbilityOwner.ExpandAbility calls it; a direct call to
    the ability's Expand (ability VMT +0xD0) does not.  Three more sites attach an ability that way:
        TFastCombatHighPrayerCA.Execute     0x557F7E0E   High Prayer Blessing 0x64, auto-resolve
        TTacticalCombatHighPrayerCA.Execute 0x557F7EF1   High Prayer Blessing 0x64, manual combat
        TBloodShrine.ExecuteBloodlust       0x557E2CB3   Bloodlust 0xA8, world map
    The ability shows and its timer runs, but a non-hero keeps its old DEF/RES (the blessing) or ATK
    (Bloodlust) until something unrelated calls Changed.  Heroes recompute live and are unaffected.
    Missed by build_debuffcache.py's census; found through Inioch's share9, where his own High Prayer
    clone showed "ability shows, stats unchanged" in game until he added the Changed call.

THE PATCH
    Each site's 6-byte `call dword ptr [ecx+0xD0]` (FF 91 D0 00 00 00) -> `jmp cave` + nop.  All
    three enter with EAX = the ability, EDX = the unit, ECX = the ability's VMT; Expand takes no stack
    argument.  The cave keeps the unit across Expand, calls the unit's Changed unless it is nil, and
    returns Expand's EAX:
        push edx / call [ecx+0xD0] / pop edx / push eax
        test edx,edx / je done / mov eax,edx / mov ecx,[eax] / call [ecx+0x90]
        done: pop eax / jmp <site+6>
    Changed is unconditional (as in build_debuffcache.py): it is idempotent, and it also heals a
    cache left stale by a save made before this patch.  Delphi's register convention keeps EBX/ESI/
    EDI/EBP, which the two loops (auto-resolve, Blood Shrine) and the tactical epilogue rely on.

Slot 0x558B3800-0x558B38FF, exclusive (three 32-byte caves).  PIC: register-indirect calls and
rel32 jumps only; no .reloc under any hook.

RNG: none.  Changed recompacts four bytes from the current ability set on every peer alike; no draw
is added or moved.

Couplings.
  * build_healwrap_fixes.py hooks the same two High Prayer functions at 0x557F7DE3 / 0x557F7EC6
    (the heal); no byte is shared, either may be undone first.
  * build_debuffcache.py: the same fix at the Web/Entangle sites, with its own caves.

Unproven, static checks cannot reach it: the unit card showing the new numbers at once.

    python build_scripts/build_blessing_cache.py            dry run + state
    python build_scripts/build_blessing_cache.py --apply
    python build_scripts/build_blessing_cache.py --undo     surgical: the three calls back, slot zeroed
    python build_scripts/build_blessing_cache.py --dis
"""
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x558B3800, 0x558B3900)
STRIDE = 0x20
EXPAND_CALL = bytes.fromhex("ff91d0000000")              # call dword ptr [ecx+0xD0]

# (name, call VA, enclosing function [lo, hi) for the interior-jump check)
SITES = [
    ("fast High Prayer",     0x557F7E0E, 0x557F7DA4, 0x557F7E20),
    ("tactical High Prayer", 0x557F7EF1, 0x557F7E98, 0x557F7EFC),
    ("Blood Shrine",         0x557E2CB3, 0x557E2C68, 0x557E2D6C),
]


def cave(va, ret):
    return asm(f"""
        push edx
        call dword ptr [ecx + 0xd0]
        pop  edx
        push eax
        test edx, edx
        je   done
        mov  eax, edx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x90]
    done:
        pop  eax
        jmp  {ret:#x}
    """, va)


caves, hooks, interior = [], [], []
for i, (name, site, lo, hi) in enumerate(SITES):
    va = SLOT[0] + i * STRIDE
    blob = cave(va, site + len(EXPAND_CALL))
    assert len(blob) <= STRIDE, "%s cave is %d bytes" % (name, len(blob))
    caves.append(("cave_" + name.replace(" ", "_"), va, blob))
    hooks.append((site, EXPAND_CALL, jmp_to(site, va, len(EXPAND_CALL))))
    interior.append((site, site + len(EXPAND_CALL), lo, hi))

if __name__ == "__main__":
    run("build_blessing_cache", hooks, caves, SLOT, interior)
