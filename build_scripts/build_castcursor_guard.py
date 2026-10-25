#!/usr/bin/env python
r"""
build_castcursor_guard.py -- arming Spellcasting with Q no longer raises "Invalid SpellID".
AoWTCPCK.dpl.  Owner report 2026-10-23: Q in tactical combat opens the spell book and shows
    Invalid SpellID (D:\AoWDev\AoWE\inc\Spells.PAS, line 54989)
non-fatal; the game carries on after OK.

CAUSE
    The assert is AoWE.TSpellControl.GetSpell @0x55779AC8 (live AoWEPACK.dpl, byte-identical to
    vanilla): `test esi,esi / jge` then System.@Assert('Invalid SpellID', Spells.PAS, 0xD6CD =
    54989) at 0x55779AD2.  It fires only for a NEGATIVE id; an id past the registry returns nil.
    The id rejected is -1.

    TTacticalCombatUnitHS.SelectAbility @0x422F0C (eax = tcu, edx = 0x34 Spellcasting):
        0x42305A  GetAbility(0x34).ActivateCombat (VMT +0xBC, TAbility.ActivateCombat 0x5574F004)
                  fires TActivateAbilityInfo; the exe's TTCMapEvents.TCMapActivateAbility 0x458CB0
                  opens the combat spell book (0x430E28, mode 1) synchronously
        0x423063  [tcu+0x38] := -1        selected spell: none yet, the book will set it
        0x423070  [tcu+0x34] := 0x34      armed ability
        0x423235  call [sel VMT+0xC] = TCombatUnitSelectionControl.UpdateMoveCursor 0x41F6E8
    UpdateMoveCursor returns at 0x41F725/0x41F739 when the combat map's mouse hex is -1.  Past
    that, with an ability armed, it does
        0x41F832  cmp [tcu+0x34], 0x34 / jne 0x41F869
        0x41F84B  GetSpell([tcu+0x38])                 -> GetSpell(-1) -> the assert
    with no test of [tcu+0x38].

    Q (build_unit_ai.py `cycle`, AoWTCPCK 0x43A850) calls SelectAbility 0x422F0C directly while
    the cursor is on the battlefield, so the mouse hex is valid and 0x41F84B is reached.  A click
    on Spellcasting in the unit panel (TTCUnit.UAbilLBMouseDown 0x434938, via build_rally.py's
    cave_click 0x62D300) or TUnitWindow.UseAbility 0x409FC5 runs the same SelectAbility, but with
    the cursor on that panel the map's mouse hex is -1 and UpdateMoveCursor returns at 0x41F725;
    that is vanilla's own route into the combat book.  There is no spell button on the combat
    toolbar (TTBWindow's combat controls are Next, Start bar, End Turn, Scanner, Unit, Auto, Chat).
    Once the book is up it raises the window manager's over-priority (SetOverPri 0x31,
    0x42E76E) and the map gets no mouse input until it closes, so only this synchronous call
    sees the -1.  The same unguarded read sits in MouseDownEvent 0x41F512 -> 0x41F530 and
    CalculateRangedPath 0x41DCF3 -> 0x41DD0C (map-click path only) and in
    TTacticalCombatUnitHS.NewFrame 0x421D71 -> 0x421DB1 (cast-animation sound); none is on the
    Q path and all three are left vanilla.

FIX -- one hook, one cave
    0x41F82F  `8B 45 F0 / 83 78 34 34 / 75 31` (mov eax,[ebp-0x10] / cmp [eax+0x34],0x34 / jne)
              -> jmp cave_castcursor + 4 nop.  No .reloc entry in the 9 bytes; the next
              instruction 0x41F838 (`mov eax,[0x46E8D0]`, relocated) is untouched.
    cave_castcursor (zone 0x43CC00..0x43CC3F) replays the compare; Spellcasting armed with
    [tcu+0x38] < 0 leaves UpdateMoveCursor at its common exit 0x41FCF1 with the map cursor
    [mouse+0x34] = 0 (cleared at 0x41F714), the same state as its off-map early exit.  Otherwise
    it resumes at 0x41F869 (other ability) or 0x41F838 (Spellcasting with a spell).  With the
    exit taken, SelectAbility finishes: [map+0x114] fires and the unit panel updates, as after a
    click.  Once a spell is picked (SelectSpell 0x423270 sets [tcu+0x38]) the cursor is vanilla.

Rolls: none (cursor only, local).  PIC: rel32 jumps only.  Surgical --undo.

Unproven without playing: that the cursor shape over uncovered map while the book is open is
acceptable (it is the off-map/no-selection state); the Q hook's second press while the book is
open is untouched by this script.

    python build_scripts/build_castcursor_guard.py            dry run + state
    python build_scripts/build_castcursor_guard.py --apply
    python build_scripts/build_castcursor_guard.py --undo
    python build_scripts/build_castcursor_guard.py --dis
"""
import os, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000

SLOT = (0x0043CC00, 0x0043CC40)
SITE = 0x0041F82F                  # UpdateMoveCursor: mov eax,[ebp-0x10] / cmp [eax+0x34],0x34 / jne
VANILLA = bytes.fromhex("8b45f0837834347531")
SPELL_PATH = 0x0041F838            # Spellcasting armed: GetSpell([tcu+0x38])
ABILITY_PATH = 0x0041F869          # any other armed ability
EXIT = 0x0041FCF1                  # pop ebx / leave / ret
FN = (0x0041F6E8, 0x0041FCF6)      # UpdateMoveCursor, for the interior-jump check
SPELLCASTING = 0x34

CAVES = [("cave_castcursor", SLOT[0], asm(f"""
        mov eax, dword ptr [ebp-0x10]
        cmp dword ptr [eax+0x34], {SPELLCASTING:#x}
        jne {ABILITY_PATH:#x}
        cmp dword ptr [eax+0x38], 0
        jl {EXIT:#x}
        jmp {SPELL_PATH:#x}
    """, SLOT[0]))]
HOOKS = [(SITE, VANILLA, jmp_to(SITE, SLOT[0], len(VANILLA)))]
INTERIOR = [(SITE, SITE + len(VANILLA), FN[0], FN[1])]

if __name__ == "__main__":
    run("build_castcursor_guard", HOOKS, CAVES, SLOT, INTERIOR, sys.argv[1:])
