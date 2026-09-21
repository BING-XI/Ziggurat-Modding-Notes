# -*- coding: utf-8 -*-
r"""
build_turnundead_evilcommand.py — an EVIL caster's Turn Undead SEIZES the undead target
instead of damaging and stunning it; the seized unit reverts if the caster dies that battle.

    python build_scripts/build_turnundead_evilcommand.py            dry run + verify + disassembly
    python build_scripts/build_turnundead_evilcommand.py --apply     write it
    python build_scripts/build_turnundead_evilcommand.py --undo      restore both hooks, zero the cave
    python build_scripts/build_turnundead_evilcommand.py --dis       disassemble the installed caves

Implements §4b / §4c of `Zig notes/TurnUndead_EvilCommand_Design.md`. Target: AoWEPACK.dpl only.
Run `build_turnundead_resroll.py` FIRST — it owns the seize CHANCE (§4a-ter); this script owns
the seize ITSELF and does not touch the roll.

────────────────────────────────────────────────────────────────────────────────────────────
EFFECT
────────────────────────────────────────────────────────────────────────────────────────────
`AoWE.TTurnUndeadCA.Execute @0x5576AC00` is replaced wholesale by cave_exec, which reads the
ATTACKER's alignment (combat VMT +0x90 = GetAlignment):

  * NOT alEvil(4) / alPureEvil(5)  ⇒ the vanilla body, instruction for instruction: damage,
    then the flee/panic status 0x22 on a surviving victim.
  * EVIL ⇒ `TDamageCA.Execute` is SKIPPED ENTIRELY — that is what suppresses the HP loss AND
    the damage-type statuses — and on success (`ca[+0x10] != 0`) the target is COMMANDED
    instead, exactly as Seduce/Dominate/Charm command theirs.

Revert-on-caster-death comes free: it is already the vanilla contract of the TCommandAbility
family (`CombatObjectDestroyed` → `ResetCommandedUnits` → `Uncommand`, which restores the
side byte stashed at `data[+0x18]`). Caster survives the battle ⇒ control becomes permanent,
because `TCommandAbility.CombatDone` drops the commander's record at end of combat.

⭐ `TCommandAbility.Command @0x5576FE50` is called DIRECTLY rather than through
`CreateCommandCA`. That is what keeps this build small: `CombatTouchRole`, `GetTouchAttack`
and `GetLevel` are never consulted, so ability N needs no private VMT and can be a plain
cloned instance. It also means three things `TCommandCA.Execute @0x5576FC68` normally does
must be replicated here or consciously dropped — see cave_exec.

⚠⚠ DO NOT "suppress the damage by zeroing it". `ca[+0x10]` is the damage amount AND the
success flag: a zero rating makes the roll fail and the seize never fires. Suppression is by
not calling `TDamageCA.Execute`, never by reducing the damage input.

────────────────────────────────────────────────────────────────────────────────────────────
TWO NEW ABILITIES, CLONED AS INSTANCES — no new class, no new save/network ClassID
────────────────────────────────────────────────────────────────────────────────────────────
  N  the hidden CONTROLLER, a second instance of `AoWE.TCommandAbility` (the base class
     Seduce/Dominate/Charm all derive from). Its VMT already carries every slot the machinery
     reaches for: +0x124 Command, +0x128 CreateCommandCA, +0x12C ResetCommandedUnits,
     +0x130 Uncommand, +0xF4 CombatObjectDestroyed, +0xFC CombatDone, +0x108 AbilityDataClass
     (→ TCommandAbilityData). Fields poked after construction: `[+0x0C]` = N, `[+0x28]` = M,
     `[+0x20]` = 0 (selection mask: never offered in the editor, on items, or at level-up).

     The design doc says "clone TDominateAbility". `TCommandAbility` is used instead and the
     result is identical: TDominateAbility overrides only `Create` (which sets an id, a
     resource-string name and a paired id we would overwrite anyway) and `GetTouchAttack`
     (never consulted, because Command is called directly). Its ctor also drags in a Delphi
     exception frame + LoadResString + TranslateRStr, all of it at package-init time — which
     is precisely where the Embrittle "runtime error 216" was manufactured. TCommandAbility's
     ctor is four instructions and no exception frame.

  M  the COMMANDED STATUS on the seized undead, an instance of `AoWE.TCommandedAbility` (what
     "Seduced" / "Dominated" / "Charmed" are). `Command` sets the victim's bit for M and
     `Uncommand` strips it; `TCommandedAbility.CombatObjectDestroyed` handles the mirror case
     (the victim dies) by looking up `GetAbility(data[+0x14])` — the controller id — and
     calling its `vmt[0x130]`. THAT is why N has to be a registered ability at its own id and
     cannot borrow Turn Undead's 0x26: `TTurnUndeadAbility`'s VMT ends at +0x124, so a
     `vmt[0x130]` call on it would execute the class-name shortstring.

⚠ IDS ARE MEASURED, NEVER QUOTED. A duplicate id is a bare `Runtime error 217` at startup,
before the main window appears. check_ids_free() re-measures from the live DLL on every run
and aborts before writing — see its docstring for which sources may drive that abort and,
just as importantly, which may not.

⚠⚠ BOTH IDS ARE DELIBERATELY TAKEN FROM VANILLA GAPS BELOW 170, NOT FROM THE TOP OF THE
RANGE. `ID_Ceilings.md`'s forward hazard: a new ability at id ≥ 170 built on `TTouchAbility`
IS selectable (`GetControlType & 2` — TCommandAbility inherits `TTouchAbility.GetControlType`
@0x557680C0, whose byte at 0x557680C8 is 0x02; `GetCombatMode` is 2, so it is not filtered
either), so it reaches `[TTacticalCombatUnitHS+0x34]` and hits

    AoWTCPCK.dpl  0x004280D7   bound eax, qword ptr [0x4288a8]        ; the [0..169] pair
    AoWTCPCK.dpl  0x004280DD   mov   al, byte ptr [eax + 0x467248]    ; AoWTC.AbilTypes

— a range-check error, not a silence. ⚠ THE MODULE MATTERS: that is AoWTCPCK.dpl, which shares
the 0x00400000 image base with AoW.exe but is the ONLY module in this game compiled with range
checks on. `AoW.exe` contains no real `BOUND` at all, and 0x004280D7 in AoW.exe is the middle
of a `jmp`. Do not re-attribute this to the exe.

Ids 0x88/0x89 are two of the 21 vanilla gaps (33, 78–85, 91, 102–105, 110, 133–137, 151) and
sit under every ceiling, so `build_abilityid_ceilings.py` and `build_tcablist_ceiling.py` do
NOT need bumping, and AoW.exe / AoWCompat.exe / AoWTCPCK.dpl are not touched at all.

N IS VISIBLE ON THE CASTER'S PANEL, AND THAT IS THE DECISION (user ruling 2026-09-01).
`[+0x20] = 0` stops N being OFFERED (editor, items, hero level-up) but does NOT hide it from a
unit's ability LIST: `CreateTCAbList @0x00423430` (AoWTCPCK.dpl) gates inclusion on
`GetAbilityEnabled(id)` alone, and the `test al,2` after it only chooses front (selectable)
versus back. So once a caster owns N — the SetAb below is mandatory — "Can Command Undead"
appears at the FRONT of its in-combat panel. The user has ruled that acceptable provided the
string reads as an obviously informational passive, which is what the "Can " prefix is for.
⚠ DO NOT "fix" this by cloning N's VMT into BSS with an `xor eax,eax; ret` in slot +0x98, and
do not filter the id out of `CreateTCAbList`. Both were considered and both are explicitly
rejected; the name is the whole remedy.

⚠⚠⚠ AND DO NOT GIVE N A PRIVATE VMT FOR ANY OTHER REASON EITHER — ONE IS LOAD-BEARING FOR
SAFETY, NOT JUST FOR EFFORT. The caster genuinely owns 0x88, so the tactical AI's
`fcPrefetchCombatCommands` does enumerate it. It is inert only because `TCommandAbility` does
NOT override `GetTouchAttack`, so VMT `+0x10C` is `TTouchAbility.GetTouchAttack @0x557680CC` =
`mov al, 0xF6` = **−10**, and that is the sentinel:

    55768270  call dword ptr [ecx + 0x10c]   ; GetTouchAttack
    55768276  movsx eax, al
    5576827B  cmp  ebx, -0xa                 ; AoWE.TTouchAbility.CombatTouchRoleProbability
    5576827E  je   0x5576829e                ; -> probability 0.0, every target skipped

Give 0x88 a private VMT with a real `GetTouchAttack` and that branch stops firing, at which
point N becomes a GENERIC DOMINATE the auto-resolve AI will fire at any non-machine living
enemy: `TCommandAbility.CanTouch @0x55770008` / `CanTouchUnit @0x55770068` impose no undead
gate and no alignment gate — those live on `TTurnUndeadAbility`, which is not in this path.
Turn Undead's targeting is safe (§5) precisely because only the CA's *execute* is redirected.

⚠ `Release/Ability.pfs` has no record for 146/147 (= id + 10), so neither ability has a
description or an icon, and nothing overwrites the `[+0x20]` mask the cave sets (tag 9 would).
Both materialise the moment the set is saved from AoWDevEd, and from then on the data file
wins. Deliberately left for later, as with Embrittled.

────────────────────────────────────────────────────────────────────────────────────────────
THE STRIP LIST — a fourth command ability means a fourth entry (user-approved 2026-09-01)
────────────────────────────────────────────────────────────────────────────────────────────
Before taking a victim, every mind-control path strips whatever control is already on it: two
loops over `AoWE.CommandAbilityIDs @0x558E84E4` = {0x1D Seduce, 0x1C Dominate, 0x94 Charm},
calling `vmt[0x12C]` ResetCommandedUnits then `vmt[0x130]` Uncommand on each.

Vanilla is correct because that list is complete FOR THE TCommandAbility FAMILY: whichever of
those holds the victim, its own `Uncommand` runs, and `Uncommand` cleans the commander's
TByteList keyed on `[ability+0x0C]` — its own id, which by construction matches the record
`Command` created. We added a FOURTH command ability and left the list at three, so nothing ever
called OUR `Uncommand`. An enemy Dominate / Seduce / Charm / Possess / Mind Decay taking a unit
we hold would leave our control record live and the victim's stashed original side
(`data[+0x18]`) stale — and on the wrong death order the unit ends up permanently with the wrong
player.

⚠ THE FIX IS ONE-DIRECTIONAL FOR MIND DECAY, AND THAT IS NOT A REGRESSION. Mind Decay RUNS the
strip loops (so it now releases our hold — that half is fixed), but it does not TAKE its victim
through the Command machinery at all:

    557F84F8  mov  edx, 0x83                 ; PassiveAb.TDecayAbility, "Decay"
    557F84FD  call GetAbility
    557F8507  call [ecx+0xD0]                ; TAbility.Expand — just grant 0x83 to the victim
    557F8510  mov  dl, [caster+0x45]
    557F8517  call [ecx+0x68]                ; SetCombatPlayer — flip the side, and that is all

No TCommandAbilityData, no TCommandedAbilityData, no controller-ability id. So `0x83` cannot go
into CommandAbilityIDs even in principle: `PassiveAb..TDecayAbility`'s VMT ends at **+0x110**
(its class-name shortstring begins at 0x557B5E00), so a `vmt[0x12C]` / `vmt[0x130]` call on it
would execute the ASCII of "DecayAbility" — the same trap recorded above for
TTurnUndeadAbility. Consequence: our seize does NOT clear `0x83` off a Mind-Decayed victim.
VANILLA DOMINATE HAS EXACTLY THE SAME GAP, so this is pre-existing engine behaviour that the
feature neither introduces nor is expected to fix. Do not "complete" the list with 0x83.

FIX: a 4-entry array {0x1D, 0x1C, 0x94, 0x88} in our cave zone; the loops are repointed at it
and their counts bumped 3 → 4. THE VANILLA ARRAY IS LEFT IN PLACE AND UNMODIFIED — the two AI
scorers below keep the 3-entry view, which is right for them.

⚠⚠ THERE ARE SIX LOOPS, NOT FOUR. A raw scan for the constant 0x558E84E4 finds only four,
because `CombatSpells.TMindDecayCA.Execute` reaches the array INDIRECTLY through a DATA pointer
cell. Ghidra's `get_xrefs_to` found it; the byte scan did not. Full census, 2026-09-01:

  patched — the six strip loops
    AoWE.TCommandCA.Execute            count 0x5576FCD4  ptr 0x5576FCD9   mov esi, imm32
                                       count 0x5576FD00  ptr 0x5576FD05
    AoWE.TPossessCA.Execute            count 0x55769712  ptr 0x55769717
                                       count 0x5576973E  ptr 0x55769743
    CombatSpells.TMindDecayCA.Execute  count 0x557F848E  ptr via DATA cell 0x558E91FC
                                       count 0x557F84BD  ptr via the same cell
    (+ our own cave_exec's two loops, which move with them — see build_exec)

  NOT patched — deliberately left on the vanilla 3
    AoWE.TCombatUnit.CommandingTargetPriority  ptr 0x55725886
    AoWE.TCombatUnit.CommandingTargetStrength  ptr 0x557258DA
    Both are AI target SCORING heuristics, not strip loops. Adding our id there would change
    how the AI values a target, which is a balance decision nobody has made.

  other references, untouched: the export-table RVA @0x5591121C.

⚠ 0x558E91FC is ordinary DATA (the section runs 0x558E8000..0x558E9A5C), NOT an .idata import
thunk (.idata starts at 0x558FB000). CombatSpells is a different Delphi unit inside the same
package and reaches AoWE's globals through cells like this one; its neighbour 0x558E92E8 holds
AoWE.AoWHSSet by the identical idiom. Both units live in AoWEPACK.dpl, so nothing re-resolves
the cell at load time — the loader only rebases it.

⚠ ALL FIVE POINTER SITES ARE RELOC-COVERED, AND THAT IS WHY THIS IS LEGAL. Retargeting a
reloc-covered immediate to another VA inside the SAME module keeps the entry correct: the
loader adds the rebase delta to whatever is stored. Verified per site before writing
(assert_strip_sites), along with the inverse for the six counts — plain `BB imm32` constants
with no entry, patched as immediates, never re-assembled.

⚠⚠ THE STRIP LIST AND THE ABILITY REGISTRATION ARE ONE ATOMIC UNIT, WHICH IS WHY THIS IS NOT A
SEPARATE SCRIPT. The patched loops call `GetAbility(0x88)` and then vcall the result.
`TAbilityControl.GetAbility @0x557501C0` bounds-checks against the registry Count and returns
NIL past it (`cmp esi,[eax+8]; jge -> xor eax,eax`), and the caller's next instruction is
`mov ecx,[eax]`. So a strip-list-on / registration-off state null-dereferences on EVERY vanilla
Dominate, Seduce, Charm, Possess and Mind Decay, in ordinary play, with our feature nominally
"removed". Same PATCHES list, one state verdict, one `--apply`, one atomic `--undo`, plus an
explicit assertion over the buffer about to be written.

ORDERING, checked rather than assumed: `RegisterPassiveAbilities` runs during PACKAGE INIT, at
DLL load, before the exe's main and long before any combat can construct a CA. Measured in a
live AoWDevEd.exe: registry Count = 179 with 0x88 and 0x89 both non-nil while only the main
form was up. So GetAbility(0x88) cannot be reached before it resolves.

────────────────────────────────────────────────────────────────────────────────────────────
RETALIATION — the design's last open risk, closed (user-approved 2026-09-01)
────────────────────────────────────────────────────────────────────────────────────────────
The two ability families disagree about who gets a free swing back, and until now Turn Undead's
rule applied to a seize:

    TCommandAbility.fcExecuteCombatCommand @0x557703C0
      557703EF  cmp  byte ptr [ebx + 0x14], 0    ; the CA success flag
      557703F3  jne  0x55770417                  ; SUCCEEDED -> no retaliation

    TTurnUndeadAbility.fcExecuteCombatCommand @0x5576B5C0
      5576B5EC  mov  eax, ebx                    ; ebx = the TARGET combat object
      5576B5EE  mov  edx, [eax]
      5576B5F0  call dword ptr [edx + 0x60]      ; GetEnabled
      5576B5F3  test al, al / je 0x5576B619      ; retaliates whenever the target still stands

⚠⚠ THIS GAP IS AUTO-RESOLVE ONLY, AND THE SCOPE MATTERS — do not read the block above as a
general statement. `TTurnUndeadAbility.fcExecuteCombatCommand` is reached ONLY through
`TTurnUndeadAbility` VMT slot +0xA4 (VA 0x5571FEA0): its address occurs exactly once in
AoWEPACK.dpl (that slot) and NOWHERE in AoWTCPCK.dpl, AoW.exe or aowInt.dpl. The dispatcher on
this path is `AoWE.TFastCombatUnit.fcExecute @0x55744268` (the call is at 0x5574445E) — the FAST
/ AUTO-RESOLVE unit. So it was auto-resolve that handed a successfully seized undead a
retaliation strike against its new owner.

MANUAL TACTICAL COMBAT NEVER HAD THE BUG AND IS NOT TOUCHED HERE. It re-implements the whole
sequence itself in `AoWTCPCK.dpl` → `CombatTE.TCAbTouchMoveTE.LastMove @0x0040A7ED..0x0040ABBE`:
it builds the CA, stores `TTurnUndeadCA.GetSuccessfull @0x5576ABF8` into `[TE+0x61]` (four
`88 42 61` stores, one per ability branch), and gates retaliation at

    0040AB20  mov eax,[ebp-4] / cmp byte ptr [eax+0x61],0 / jne 0x40AC13   ; SUCCEEDED -> skip

— i.e. Command's rule, and it has always been there. ⭐ `cave_exec` (the seize itself) IS on
both paths, because manual combat still reaches `TTurnUndeadCA.Execute` via
`TCombat.ExecuteCombatAction`. Only the RETALIATION half is auto-resolve-only.
⚠ Do not "fix" AoWTCPCK to match. There is nothing there to fix.

The 7 bytes at 0x5576B5EC become `call cave_retal` + two nops; the `test al,al / je` that follows
is left exactly as it is and consumes the cave's return value.

The evil path now gets Command's rule (retaliate only on failure). ⚠ THE NON-EVIL PATH IS
DELIBERATELY UNCHANGED: vanilla Turn Undead lets a stunned target retaliate, and that stays.
cave_retal's four arms are laid out in its own docstring, along with the two-hop combat-data
chain and why GetEnabled is tested first.

⚠⚠ THIS IS WHY IT IS IN THIS SCRIPT AND NOT ITS OWN. Undo the ability registration while
leaving the guard installed and cave_exec is gone, so a successful roll is an ordinary STUN --
and the guard would then suppress retaliation on an evil caster's stun. That is a behaviour
change on a feature the user believes they removed, and nothing would report it. The site is in
the same PATCHES list and the same coupling assertion as the other eleven.



THE ANKH OVERLAY — the last cosmetic gap (user-approved 2026-09-02)
────────────────────────────────────────────────────────────────────────────────────────────
A `Release/Ability.pfs` record for 0x89 (build_commandedundead_pfs.py, key 147) gives the
ability its image sequence, and on its own that draws NOTHING: persistent status icons are not
drawn generically. `AoWE.TAbstractUnit.ShowEx @0x557812EC` — the shared sprite draw, used by
fast combat directly and by manual tactical through AoWTCPCK's import of `TCombatUnit.Show` —
holds a HARD-CODED chain of per-ability blocks:

    0x60 0x62 0x5D 0x91 0x04 0x30 Seduced 0x96 Dominated 0x95 Charmed 0x61 0x5C 0x5F 0x5E 0x7F
    0x6B Possessed 0x22 Turned Undead 0x46

each `if GetAbilityEnabled(unit, ID) then ShowLooped(GetAbility(ID)->[+0x1C])`. The five
command-family statuses all draw at (x+0x20, y+0x28); 0x89 has no block, so cave_ankh adds
one, at the same spot as its siblings.

HOOK: a `call rel32` RETARGET, the project's preferred idiom. ShowEx's epilogue runs for
every drawn unit after the whole chain:

    55781A2E  e8 c5 22 00 00   call TUnitGFXResourceList.GetUnitGFXResource   <- retargeted
    55781A33  mov edx,[eax] / call [edx+0x2C]                                   ; Release

cave_ankh saves EAX/EDX (both live inputs to that callee), runs the 0x89 block, restores
them, and `jmp`s to GetUnitGFXResource so its return value flows back to 0x55781A33 untouched.
Control-flow audit, so nobody re-derives it: the only `ret` in ShowEx is the epilogue's, and
the one early exit (`0x5578132B je 0x557814A9`) lands at the START of the icon chain, not past
it — every path draws the chain and reaches the hook.

TWO GUARDS, both mandatory:
  1. GetAbility(0x89) is nil-checked in the cave BEFORE anything is pushed. GetAbilityEnabled
     reads the unit's BITSET, not the registry, so a save carrying bit 0x89 loaded with the
     registration reverted would otherwise dereference nil on every unit draw. That is why the
     hook is in THIS script (undo of the registration removes it too); the nil check is
     belt-and-braces on top.
  2. assert_ankh_pfs() refuses to --apply unless Ability.pfs holds record 147. Without it
     `[+0x1C]` is the empty TImageSequenceList TAbility.Create built, and ImageLib.Get has no
     bounds check — an out-of-range read on every seized-unit draw, not a blank icon.

The 13th coupled site: in PATCHES, _STRIP_VAS, the pre-write assertion, PRIOR_BUILDS and the
coupling display, exactly like the retaliation guard.


────────────────────────────────────────────────────────────────────────────────────────────
────────────────────────────────────────────────────────────────────────────────────────────
THE FOUR HOOK SITES
────────────────────────────────────────────────────────────────────────────────────────────
  0x557BCE30  the LAST still-direct `call TAbilityControl.RegisterAbility` inside
              `PassiveAb.RegisterPassiveAbilities @0x557BC1CC`. Measured live 2026-09-01:
              81 of the 88 calls there are still direct; the SEVEN already repointed are
              0x557BC9E9 (path_sand -> 0x5580E000), 0x557BCE65 (embrittle), 0x557BCE9A
              (reformingflesh), 0x557BCECF (shield), 0x557BCF04 (caster_cost), 0x557BCF39
              (drillmaster) and 0x557BCE30 (this feature).
              ⚠ This comment used to say FIVE, because assert_reg_site's cave band began at
              0x55810000 and so could not see path_sand's target at 0x5580E000. The band is now
              CAVE_BAND_LO, shared with the id scan.
              assert_reg_site() re-measures on every run rather than trusting this
              comment — taking a site another feature already owns is the documented
              silent-unlink failure, and nothing reports it.
              EBX holds the TAbilityControl for the whole of that function (0x557BCE2E
              `mov eax,ebx` immediately before the site is the proof), and EBP is the host's
              frame pointer, so cave_reg preserves EBX/EBP and uses ESI/EDI.

  0x5576AC00  `TTurnUndeadCA.Execute` entry, 5 bytes `53 56 57 8b f2` -> `E9 rel32`. The rest
              of the original function becomes dead code; cave_exec never returns into it.

  0x5576B5EC  the retaliation gate inside `TTurnUndeadAbility.fcExecuteCombatCommand
              @0x5576B5C0`, 7 bytes `8b c3 8b 10 ff 52 60` -> `E8 rel32` + two nops. The
              `test al,al / je 0x5576B619` at 0x5576B5F3 is LEFT IN PLACE and consumes
              cave_retal's return value. AUTO-RESOLVE ONLY — see the RETALIATION section.
              Verified byte-identical to AoWEPACK_original_backup.dpl before writing, so
              nothing else owns the run.

  0x55781A2E  `TAbstractUnit.ShowEx` epilogue, 5 bytes `e8 c5 22 00 00` (`call
              GetUnitGFXResource`) retargeted to cave_ankh, which tail-jumps to the original
              callee. A call-rel32 retarget: nothing is displaced. Verified byte-identical to
              AoWEPACK_original_backup.dpl before writing.

None of the four displaced runs carries a `.reloc` entry (asserted before writing).

────────────────────────────────────────────────────────────────────────────────────────────
POSITION INDEPENDENCE / RNG
────────────────────────────────────────────────────────────────────────────────────────────
The DPL never loads at its preferred base. Both caves need module globals (the two classref
pointers and the two name literals in cave_reg; `AoWE.AoWHSSet` and `AoWE.CommandAbilityIDs`
in cave_exec), so each uses the standard `call <addr> ; pop <reg>` delta anchor with the
rel32 zeroed. Everything else is rel32 calls, register-indirect virtual calls and immediates.
Nothing anywhere uses an absolute address.

NO RNG DRAW IS ADDED OR MOVED. The seize rides on `ca[+0x10]`, which `TDamageCA.GenerateEx`
already filled at CA-creation time inside `CreateTurnUndeadCA`. `rng_audit.py --owners` must
show no new site.

⚠ A cave that runs at PACKAGE INIT cannot be proved by any static check — byte verification,
the .reloc scan, the PIC audit and the --undo round trip were ALL green for Embrittle v1, and
the game still died with `Runtime error 216` on launch. This build must be proved by LAUNCHING
THE EXE. (216 = GPF, 217 = duplicate ability id.)
"""
import os
import shutil
import struct
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

try:
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    sys.exit("needs keystone-engine and capstone:  py -m pip install keystone-engine capstone")

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-turnundeadevilcmd")
DLL_BASE = 0x55700000

# ================================================================== the knobs
N_ID = 0x88                     # the CONTROLLER   (vanilla gap 136; measured, see check_ids_free)
M_ID = 0x89                     # COMMANDED status (vanilla gap 137)
# ⚠ N's name IS SEEN IN GAME. It shows on the caster's in-combat ability panel from the first
# successful seize onwards (see the docstring), so the user ruled 2026-09-01 that it must read
# as an obviously informational passive: "Can Command Undead", not "Command Undead". Changing
# its length moves the M literal and the `add edx, imm32` offsets that reach both — which is
# why build_zone() computes the layout rather than hard-coding it, and why the previous name
# has to stay in PRIOR_ZONES.
N_NAME = b"Can Command Undead"
# ⚠ M's name is seen on the SEIZED unit. It was "Turned" until the user ruled 2026-09-01 that
# it collides with vanilla ability 0x22 "Turned Undead" — Turn Undead's own panic/flee status,
# which can sit in the SAME unit's ability list in the same battle. "Turned" next to "Turned
# Undead" is too easy to misread. "Commanded Undead" also pairs with the caster's "Can Command
# Undead", so the two halves of the feature read as an obvious pair.
M_NAME = b"Commanded Undead"
ALIGN_LO = 4                    # alEvil        \ the caster test is (align - 4) <= 1 unsigned
ALIGN_SPAN = 1                  # alPureEvil    /
# ===========================================================================

# --- engine entry points (every one verified against the live DLL 2026-09-01) ------
REGISTER_ABIL = 0x55750238      # TAbilityControl.RegisterAbility  (EAX=ctrl, EDX=ability)
# The band every mod cave in this DLL lives in: from the lowest address any build script
# claims (0x5580BE00, build_glowboost) up to the end of the CODE section. ⚠ ONE constant,
# used by BOTH the id scan and assert_reg_site. They disagreed before: assert_reg_site
# started at 0x55810000 and so did not recognise 0x557BC9E9 -> 0x5580E000 (build_path_sand,
# a genuinely repointed RegisterAbility call) as taken. It counted as neither direct nor
# repointed and the printed tally read one short -- and that printed line is exactly what a
# future session reads to decide whether a registration site is free.
CAVE_BAND_LO = 0x5580B000
CAVE_BAND_HI = 0x558E7900       # end of CODE (vsize 0x1E6918 from 0x55701000)

CREATE_ENH = 0x5576601C         # AoWE.CreateEnhancementAbility — NOT used here; the id scan
                                # looks for other features' calls to it (see _scan_cave_band)
GET_ABILITY = 0x557501C0        # TAbilityControl.GetAbility       (EAX=ctrl, EDX=id) -> EAX
GET_ABDATA = 0x5574F1C4         # TAbilityOwner.GetAbilityData     (EAX=owner, EDX=id) -> EAX
SETAB = 0x5574E718              # TAbility.SetAb  (EAX=this, EDX=owner, ECX=id, [esp+4]=val) ret 4
CMD_CREATE = 0x5576FDBC         # TCommandAbility.Create           (EAX=class, DL=1) -> EAX
CMD_CLSPTR = 0x55720504         # ptr -> AoWE..TCommandAbility     (VMT 0x55720544 minus 0x40)
CMDED_CREATE = 0x5576FADC       # TCommandedAbility.Create         (EAX=class, DL=1) -> EAX
CMDED_CLSPTR = 0x557201D8       # ptr -> AoWE..TCommandedAbility   (VMT 0x55720218 minus 0x40)
COMMAND = 0x5576FE50            # TCommandAbility.Command (EAX=ability, EDX=commanderCO, ECX=victimCO)
FINDID = 0x55728C68             # TCombatData.FindID               (EAX=combatdata, EDX=id) -> EAX
GETSIDE = 0x55726660            # TCombatObject.GetSide            (EAX=co) -> AL  (2 = unsided)
DAMAGECA_EXEC = 0x55729D14      # TDamageCA.Execute                (EAX=ca, EDX=combat)
LSTRASG = 0x55701150            # thunk -> VCL30.dpl!System.@LStrAsg  (EAX=@dest, EDX=source)
HSSET = 0x558FA044              # AoWE.AoWHSSet;  ability control = [[HSSET] + 0x80]
CMDIDS = 0x558E84E4             # AoWE.CommandAbilityIDs = {0x1D Seduce, 0x1C Dominate, 0x94 Charm}
CMDIDS_VANILLA = (0x1D, 0x1C, 0x94)     # left in the DLL untouched — see the strip-list section

# --- the strip list: the six loop sites, and the one indirect cell -----------------
# (count-immediate VA, expected opcode VA, function) — all six are `BB imm32` = mov ebx,imm32,
# none of them reloc-covered. Patched as an IMMEDIATE; the loop is never re-assembled.
STRIP_COUNTS = [
    (0x5576FCD4, 0x5576FCD3, "AoWE.TCommandCA.Execute        loop1 (ResetCommandedUnits)"),
    (0x5576FD00, 0x5576FCFF, "AoWE.TCommandCA.Execute        loop2 (Uncommand)"),
    (0x55769712, 0x55769711, "AoWE.TPossessCA.Execute        loop1 (ResetCommandedUnits)"),
    (0x5576973E, 0x5576973D, "AoWE.TPossessCA.Execute        loop2 (Uncommand)"),
    (0x557F848E, 0x557F848D, "CombatSpells.TMindDecayCA.Execute loop1 (ResetCommandedUnits)"),
    (0x557F84BD, 0x557F84BC, "CombatSpells.TMindDecayCA.Execute loop2 (Uncommand)"),
]
# (imm VA, expected opcode VA, opcode byte, function) — the four DIRECT `mov esi, imm32`
# array loads. Every one carries a .reloc entry, so pointing it at another VA INSIDE THIS
# MODULE keeps that entry correct: the loader simply adds the rebase delta, exactly as it does
# for the vanilla value. Asserted before writing.
STRIP_PTRS = [
    (0x5576FCD9, 0x5576FCD8, 0xBE, "AoWE.TCommandCA.Execute  loop1  mov esi, <array>"),
    (0x5576FD05, 0x5576FD04, 0xBE, "AoWE.TCommandCA.Execute  loop2  mov esi, <array>"),
    (0x55769717, 0x55769716, 0xBE, "AoWE.TPossessCA.Execute  loop1  mov esi, <array>"),
    (0x55769743, 0x55769742, 0xBE, "AoWE.TPossessCA.Execute  loop2  mov esi, <array>"),
]
# CombatSpells reaches AoWE's globals through unit-level POINTER CELLS in DATA rather than by
# constant, so TMindDecayCA's two loops are `mov esi, dword ptr [0x558E91FC]` — no immediate to
# repoint. The cell itself is repointed instead. It is ordinary DATA (0x558E8000..0x558E9A5C),
# NOT an .idata import thunk (.idata starts at 0x558FB000), and it carries a .reloc entry, so
# the same "same module ⇒ entry stays valid" argument applies. Its neighbour 0x558E92E8 holds
# AoWE.AoWHSSet by the identical idiom, which is what identifies the pattern.
# ⚠ Ghidra says TMindDecayCA.Execute is the ONLY reader of this cell. If that ever stops being
# true, a new reader silently inherits the 4-entry view.
CMDIDS_CELL = 0x558E91FC

VMT_ALIGNMENT = 0x90            # combat object: GetAlignment -> AL
VMT_EXPAND = 0xD0               # ability: TAbility.Expand (grant to an owner)
VMT_RESETCMD = 0x12C            # ability: ResetCommandedUnits
VMT_UNCOMMAND = 0x130           # ability: Uncommand
FLEE_AB = 0x22                  # the flee/panic status Turn Undead grants on a normal stun
CA_ATTACKER = 0x0D              # [CA+0x0D] attacker combat-object id
CA_VICTIM = 0x0E                # [CA+0x0E] victim   combat-object id
CA_SUCCESS = 0x10               # [CA+0x10] rolled damage == the success flag
CO_OWNER = 0x4C                 # combat object -> its TAbilityOwner (the strategic unit)
CO_SIDEBYTE = 0x45              # combat object -> combat-player slot
CO_STATE = 0x47                 # combat object -> state flags; bit0 clear == survived

# --- hook sites, with their exact vanilla bytes -----------------------------------
REG_INJ = 0x557BCE30
REG_ORIG = b"\xE8" + struct.pack("<i", REGISTER_ABIL - (REG_INJ + 5))
EXEC_INJ = 0x5576AC00
EXEC_ORIG = bytes.fromhex("5356578bf2")         # push ebx; push esi; push edi; mov esi,edx
# The retaliation guard, inside AoWE.TTurnUndeadAbility.fcExecuteCombatCommand @0x5576B5C0:
#   5576B5EC  8b c3        mov  eax, ebx        #   5576B5EE  8b 10        mov  edx, [eax]       } 7 bytes -> call rel32 + two nops
#   5576B5F0  ff 52 60     call [edx+0x60]      /  TCombatObject.GetEnabled
#   5576B5F3  84 c0 / 74 22  test al,al / je    <- LEFT ALONE; it consumes our return value
# Verified 2026-09-01: byte-identical to AoWEPACK_original_backup.dpl (so nothing else owns
# it) and no .reloc entry touches the run.
RETAL_INJ = 0x5576B5EC
RETAL_ORIG = bytes.fromhex("8bc38b10ff5260")
VMT_GETENABLED = 0x60           # combat object: GetEnabled -> AL
NOP2 = bytes.fromhex("9090")   # the two-byte tail of the 7-byte retaliation hook
# The Ankh status overlay. AoWE.TAbstractUnit.ShowEx @0x557812EC draws persistent status icons
# through a HARD-CODED chain of per-ability blocks (0x60 0x62 0x5D 0x91 0x04 0x30 0x96 0x95
# 0x61 0x5C 0x5F 0x5E 0x7F 0x6B 0x22 0x46); 0x89 has no block, so its image sequence is never
# drawn however correct the .pfs record is. Hooked by RETARGETING the epilogue's call:
#   55781A2E  e8 c5 22 00 00   call TUnitGFXResourceList.GetUnitGFXResource   (runs for EVERY
#                              drawn unit, after the whole chain -- verified: the only `ret`
#                              in ShowEx is the epilogue's, and the 0x5578132B early exit lands
#                              at 0x557814A9, the START of the chain, not past it)
# Verified 2026-09-02: byte-identical to AoWEPACK_original_backup.dpl, no .reloc on the run.
ANKH_INJ = 0x55781A2E
ANKH_ORIG = bytes.fromhex("e8c5220000")
GETUNITGFX = 0x55783CF8         # TUnitGFXResourceList.GetUnitGFXResource -- cave tail-jumps here
SHOWLOOPED = 0x55702914         # thunk -> ILPACK.dpl!ImageLib.TImageSequenceList.ShowLooped
HSMAP = 0x558FA040              # AoWE.AoWHSMap (= AoWHSSet - 4); [+0x40] = animation frame counter
VMT_STRAT_ABENABLED = 0x148     # strategic unit: GetAbilityEnabled(id) -> AL (item-aware)
ICON_DX, ICON_DY = 0x20, 0x28   # where 0x30/0x96/0x95/0x6B/0x22 all draw; 0x89 joins its siblings
PH_HSMAP = 0x73111107

# --- cave placement ---------------------------------------------------------------
# 0x55832000: page-aligned, one page above build_turnundead_resroll.py's 0x55831000, and above
# EVERY address claimed by any build script (highest prior claim: build_embrittle.py's
# 0x5582D000 zone; the highest non-zero byte in the whole CODE section is 0x5582F044).
# Verified 2026-09-01: `grep -rl "55832" "Modding Resources/build_scripts/"` -> no hits, and
# there is not one .reloc entry anywhere in 0x55830000..0x55840000.
# ⚠ A zero run is not proof a zone is unclaimed — read the scripts, not the zeros.
CAVE = 0x55832000
CAVE_ZONE_LEN = 0x400           # reservation incl. growth slack; asserted zero (or ours)

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

PH_NNAME = 0x73111101           # placeholders, replaced with (target - PIC anchor)
PH_MNAME = 0x73111102
PH_NCLS = 0x73111103
PH_MCLS = 0x73111104
PH_HSSET = 0x73111105
PH_CMDIDS = 0x73111106

AOW_PROCS = ["AoW", "AoWCompat", "AoWDevEd", "AoWEd"]


def kill_aow():
    """Game files are locked while any AoW binary runs; AoWDevEd loads AoWEPACK.dpl too.
    Standing authorization to kill them — the game autosaves per turn."""
    killed = [n for n in AOW_PROCS
              if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                                capture_output=True, text=True).returncode == 0]
    if killed:
        print("  killed running: " + ", ".join(killed))


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def fix_pic(code, va, pop_op, subs):
    """`call <addr> ; pop <reg>` -> a runtime delta anchor; rewrite placeholders as
    (target - anchor).

    The call's rel32 is zeroed so it falls straight through to the pop, which then holds the
    RUNTIME address of itself. Nothing in a DPL cave may use an absolute address.

    ⚠ never write the anchor as `call $+5` in the source — keystone assembles that to NOTHING,
    silently, and the search below then latches onto whatever earlier E8 happens to sit five
    bytes before a matching pop and zeroes ITS rel32. Emit a real `call <addr>`; the target is
    irrelevant because the rel32 is zeroed here anyway.
    """
    code = bytearray(code)
    i = next(k for k in range(len(code) - 5) if code[k] == 0xE8 and code[k + 5] == pop_op)
    anchor = va + i + 5
    code[i + 1:i + 5] = struct.pack("<i", 0)
    for ph, tgt in subs:
        hits = [k for k in range(len(code) - 3) if code[k:k + 4] == struct.pack("<I", ph)]
        assert len(hits) == 1, "placeholder %#x found %d times" % (ph, len(hits))
        code[hits[0]:hits[0] + 4] = struct.pack("<i", tgt - anchor)
    return bytes(code), anchor


# refcount -1 => @LStrAsg shares the literal and never tries to free it (Path of Sand recipe)
def literal(s):
    return struct.pack("<iI", -1, len(s)) + s + b"\x00"


# --------------------------------------------------------------- cave_reg
def build_reg(va, n_name_va, m_name_va, n_id=None, m_id=None):
    """Re-issue the displaced RegisterAbility, then build + register M and N.

    On entry vanilla has just set EAX = the TAbilityControl and EDX = the ability it built for
    id 0x8B, so the leading `call` finishes vanilla's business unchanged. EBX holds the control
    for the whole of RegisterPassiveAbilities and EBP is that function's frame pointer, so both
    are left alone; ESI/EDI are saved and restored.

    The anchor is taken ONCE and kept in ESI, because every constructor clobbers the volatiles.
    """
    n_id = N_ID if n_id is None else n_id
    m_id = M_ID if m_id is None else m_id
    src = """
        call 0x%X
        push esi
        push edi
        call 0x%X
        pop  esi
        mov  eax, esi
        add  eax, 0x%X
        mov  eax, dword ptr [eax]
        xor  ecx, ecx
        mov  dl, 1
        call 0x%X
        mov  edi, eax
        mov  dword ptr [edi + 0x0C], %d
        mov  edx, esi
        add  edx, 0x%X
        lea  eax, [edi + 8]
        call 0x%X
        mov  edx, edi
        mov  eax, ebx
        call 0x%X
        mov  eax, esi
        add  eax, 0x%X
        mov  eax, dword ptr [eax]
        xor  ecx, ecx
        mov  dl, 1
        call 0x%X
        mov  edi, eax
        mov  dword ptr [edi + 0x0C], %d
        mov  dword ptr [edi + 0x28], %d
        mov  word ptr [edi + 0x20], 0
        mov  edx, esi
        add  edx, 0x%X
        lea  eax, [edi + 8]
        call 0x%X
        mov  edx, edi
        mov  eax, ebx
        call 0x%X
        pop  edi
        pop  esi
        ret
    """ % (REGISTER_ABIL, va,
           PH_MCLS, CMDED_CREATE, m_id, PH_MNAME, LSTRASG, REGISTER_ABIL,
           PH_NCLS, CMD_CREATE, n_id, m_id, PH_NNAME, LSTRASG, REGISTER_ABIL)
    return fix_pic(asm(src, va), va, 0x5E,                       # 0x5E = pop esi
                   [(PH_MCLS, CMDED_CLSPTR), (PH_NCLS, CMD_CLSPTR),
                    (PH_MNAME, m_name_va), (PH_NNAME, n_name_va)])


# --------------------------------------------------------------- cave_exec
def build_exec(va, n_id=None, evil=True, cmdids_va=None, cmdids_n=None):
    """Wholesale replacement of AoWE.TTurnUndeadCA.Execute.  EAX = the CA, EDX = the combat.

    Frame: [esp+0] = &AoWE.AoWHSSet   [esp+4] = &AoWE.CommandAbilityIDs   [esp+8] = scratch.
    Both are resolved from ONE PIC anchor at the top and used by both branches.

    Register plan: EBX = the CA, ESI = the combat argument, EDI = attacker combat object,
    EBP = victim combat object.  ESI/EBX are repurposed in the evil branch only, after the
    last use of the combat argument and the CA.

    `evil=False` reproduces the pure vanilla body and exists ONLY so that a build this script
    shipped earlier can be recognised as a valid pre-state — never for a live build.

    ⚠ ONE THING FROM `TCommandCA.Execute` IS DELIBERATELY NOT REPLICATED, AND IT IS NOT AN
    OVERSIGHT. Vanilla awards the commander the victim's level as experience:

        5576FCA6  mov  eax,[esp+4] / call [edx+0x98]    ; commander GetExperience
        5576FCB4  mov  eax,edi     / call [edx+0xa0]    ; victim    GetLevel
        5576FCBE  and  eax,0xff / add ebx,eax
        5576FCC5  mov  edx,ebx     / call [ecx+0x9c]    ; commander SetExperience

    That whole run (0x5576FCA6..0x5576FCD3) is omitted by design — a BALANCE choice made in the
    spec, not a gap in the port. Seizing an undead already costs nothing but the cast, and Turn
    Undead is a level-4 ladder; paying XP on top would make an evil cleric self-levelling off
    free kills it never had to make. The other two things `TCommandCA.Execute` does — the
    GetSide guard and the two CommandAbilityIDs strip loops — ARE replicated below, because
    those are correctness, not balance. If you ever want the XP back, add it right after the
    `Command` call, reading the victim through EBP and the commander through EDI.
    """
    n_id = N_ID if n_id is None else n_id
    # ⚠ OUR OWN strip loops read the SAME 4-entry array and count as the engine's. Leaving them
    # at the vanilla 3 would reproduce the exact defect this feature fixes, one attacker along:
    # two evil Turn Undead casters, the second seizing what the first holds, would leave the
    # first commander's record live and the victim's stashed original side stale.
    cmdids_va = CMDIDS if cmdids_va is None else cmdids_va
    cmdids_n = len(CMDIDS_VANILLA) if cmdids_n is None else cmdids_n
    seize = """
    L_evil:
        cmp  byte ptr [ebx + 0x%X], 0
        je   L_done
        xor  edx, edx
        mov  dl, byte ptr [ebx + 0x%X]
        mov  eax, dword ptr [esi + 0x0C]
        call 0x%X
        test eax, eax
        je   L_done
        mov  ebp, eax
        mov  eax, edi
        call 0x%X
        mov  byte ptr [esp + 8], al
        mov  eax, ebp
        call 0x%X
        cmp  byte ptr [esp + 8], al
        je   L_done
        mov  esi, dword ptr [esp + 4]
        mov  ebx, %d
    L_strip1:
        mov  eax, dword ptr [esp]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x80]
        mov  edx, dword ptr [esi]
        call 0x%X
        mov  edx, ebp
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x%X]
        add  esi, 4
        dec  ebx
        jne  L_strip1
        mov  esi, dword ptr [esp + 4]
        mov  ebx, %d
    L_strip2:
        mov  eax, dword ptr [esp]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x80]
        mov  edx, dword ptr [esi]
        call 0x%X
        mov  edx, ebp
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x%X]
        add  esi, 4
        dec  ebx
        jne  L_strip2
        mov  eax, dword ptr [esp]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x80]
        mov  edx, %d
        call 0x%X
        test eax, eax
        je   L_done
        mov  esi, eax
        push 1
        mov  ecx, %d
        mov  edx, dword ptr [edi + 0x%X]
        mov  eax, esi
        call 0x%X
        mov  ecx, ebp
        mov  edx, edi
        mov  eax, esi
        call 0x%X
        jmp  L_done
    """ % (CA_SUCCESS, CA_VICTIM, FINDID, GETSIDE, GETSIDE,
           cmdids_n, GET_ABILITY, VMT_RESETCMD,
           cmdids_n, GET_ABILITY, VMT_UNCOMMAND,
           n_id, GET_ABILITY, n_id, CO_OWNER, SETAB, COMMAND)

    gate = """
        mov  edi, eax
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x%X]
        movzx eax, al
        sub  eax, %d
        cmp  eax, %d
        jbe  L_evil
    """ % (VMT_ALIGNMENT, ALIGN_LO, ALIGN_SPAN)

    src = """
        push ebx
        push esi
        push edi
        push ebp
        add  esp, -0x0C
        mov  esi, edx
        mov  ebx, eax
        call 0x%X
        pop  ecx
        mov  eax, ecx
        add  eax, 0x%X
        mov  dword ptr [esp], eax
        add  ecx, 0x%X
        mov  dword ptr [esp + 4], ecx
        xor  edx, edx
        mov  dl, byte ptr [ebx + 0x%X]
        mov  eax, dword ptr [esi + 0x0C]
        call 0x%X
        test eax, eax
        je   L_vanilla
        %s
    L_vanilla:
        mov  edx, esi
        mov  eax, ebx
        call 0x%X
        cmp  byte ptr [ebx + 0x%X], 0
        je   L_done
        xor  edx, edx
        mov  dl, byte ptr [ebx + 0x%X]
        mov  eax, dword ptr [esi + 0x0C]
        call 0x%X
        mov  edi, eax
        xor  edx, edx
        mov  dl, byte ptr [ebx + 0x%X]
        mov  eax, dword ptr [esi + 0x0C]
        call 0x%X
        mov  ebp, eax
        test byte ptr [ebp + 0x%X], 1
        jne  L_done
        mov  eax, dword ptr [esp]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x80]
        mov  edx, %d
        call 0x%X
        mov  edx, dword ptr [ebp + 0x%X]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x%X]
        mov  eax, dword ptr [ebp + 0x%X]
        mov  edx, %d
        call 0x%X
        test eax, eax
        je   L_done
        mov  dl, byte ptr [edi + 0x%X]
        mov  byte ptr [eax + 0x0F], dl
        jmp  L_done
        %s
    L_done:
        add  esp, 0x0C
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """ % (va, PH_HSSET, PH_CMDIDS, CA_ATTACKER, FINDID,
           gate if evil else "",
           DAMAGECA_EXEC, CA_SUCCESS, CA_ATTACKER, FINDID, CA_VICTIM, FINDID, CO_STATE,
           FLEE_AB, GET_ABILITY, CO_OWNER, VMT_EXPAND, CO_OWNER, FLEE_AB, GET_ABDATA,
           CO_SIDEBYTE,
           seize if evil else "")
    return fix_pic(asm(src, va), va, 0x59,                        # 0x59 = pop ecx
                   [(PH_HSSET, HSSET), (PH_CMDIDS, cmdids_va)])


# --------------------------------------------------------------- cave_retal
def build_retal(va, n_id=None):
    """Replaces the 7-byte GetEnabled call that decides whether Turn Undead's target gets a
    retaliation strike. Returns AL: non-zero = retaliate, zero = do not.

    Entry (established by fcExecuteCombatCommand and unchanged since):
        EBX = the TARGET combat object
        ESI = the context struct; the TCombat is [ESI+8]
        EDI = the CA, i.e. the TTurnUndeadCA that CreateTurnUndeadCA just built (0x5576B5E0
              `mov edi,eax`, so EDI stops being the ability at that point)
    EBX/ESI/EDI/EBP are preserved (only EAX/ECX/EDX are touched, and TCombatData.FindID keeps
    the callee-saved four). The host's `test al,al / je 0x5576B619` at 0x5576B5F3 is left in
    place and consumes the return value unchanged.

    THE RULE, and why each arm is what it is:
      1. GetEnabled(target) FIRST. Zero -> zero. That is vanilla's own test and it must stay in
         front, so a disabled target is refused for vanilla's reason before anything of ours
         runs.
      2. `ca[+0x10] == 0` -> retaliate. The roll FAILED. Both ability families retaliate on
         failure (TCommandAbility.fcExecuteCombatCommand @0x557703EF is `cmp byte [ebx+0x14],0
         / jne skip`), so this arm is correct for every alignment and needs no alignment test.
      3. The roll succeeded and the attacker is Evil / Pure Evil -> zero. This is the whole
         change: a seized undead does not swing at its new owner. It gives the evil path
         Command's rule.
      4. Anything else -> retaliate. A NON-EVIL caster's successful stun keeps vanilla's
         behaviour exactly. ⚠ Do not "tidy" this into a single alignment test: vanilla Turn
         Undead lets a stunned target retaliate and that is deliberately unchanged.
      FindID returning nil -> retaliate. Fail safe to vanilla rather than to the new rule.

    ⚠ KNOWN AND DELIBERATE, NOT AN OVERSIGHT: cave_retal and cave_exec test `ca[+0x10] != 0`
    independently, and cave_exec can still bail AFTER that test — nil victim FindID, attacker
    and victim on the same side, or GetAbility(0x88) nil. In those cases no seize happens, yet
    cave_retal sees "enabled + succeeded + evil" and suppresses retaliation anyway. That is row
    4 of the agreed matrix implemented literally, and the cost of keeping the two caves
    independent instead of threading a result between them. Normal targeting cannot reach the
    same-side case at all: `TTouchAbility.CanTouch @0x557682AC` already requires opposing sides.
    Recorded so nobody later reads it as a bug and "fixes" it into a coupling.

    ⚠ THE COMBAT-DATA CHAIN IS TWO HOPS HERE, NOT ONE. TTurnUndeadCA.Execute reads its combat
    data as `[arg+0x0C]`, but ITS arg is the TCombat: TCombat.ExecuteCombatAction @0x55727224
    does `mov edx,ebx` (itself) / `mov eax,esi` (the CA) / `call [ecx+0x50]`. In
    fcExecuteCombatCommand the TCombat is `[ESI+8]` (it is what gets passed to
    ExecuteCombatAction at 0x5576B5E4), so the data is `[[ESI+8]+0x0C]`. Derived from those two
    functions, not assumed.

    Position-independent: one rel32 call, two register-indirect virtual calls, immediates only.
    """
    n_id = N_ID if n_id is None else n_id       # unused; kept so priors rebuild uniformly
    src = """
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x%X]
        test al, al
        jz   L_no
        cmp  byte ptr [edi + 0x%X], 0
        je   L_yes
        movzx edx, byte ptr [edi + 0x%X]
        mov  eax, dword ptr [esi + 8]
        mov  eax, dword ptr [eax + 0x0C]
        call 0x%X
        test eax, eax
        je   L_yes
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x%X]
        movzx eax, al
        sub  eax, %d
        cmp  eax, %d
        jbe  L_no
    L_yes:
        mov  al, 1
        ret
    L_no:
        xor  al, al
        ret
    """ % (VMT_GETENABLED, CA_SUCCESS, CA_ATTACKER, FINDID, VMT_ALIGNMENT,
           ALIGN_LO, ALIGN_SPAN)
    return asm(src, va), None



# ---------------------------------------------------------------- cave_ankh
def build_ankh(va, m_id=None):
    """Retargets ShowEx's epilogue call so the Ankh loops over a seized undead.

    Entry (ShowEx's frame is live; we sit where `call GetUnitGFXResource` was):
        EAX = the TUnitGFXResourceList   (LIVE input to the callee -- saved)
        EDX = [ebp-0x14], the gfx index  (LIVE input to the callee -- saved)
        ESI = the strategic unit         [ebp-4] = x   [ebp-8] = y   [ebp+0xC] = draw target
    Exit: `jmp GetUnitGFXResource` with EAX/EDX restored, so the callee's `ret` lands on
    0x55781A33 with ITS return value, exactly as before. EBX/ESI/EDI/EBP untouched.

    Body = the Dominated block @0x5578170F..0x5578175B for id 0x89, with the two absolute
    globals resolved through the PIC anchor. Order differs from vanilla in ONE deliberate way:
    GetAbility(0x89) is resolved and NIL-CHECKED before anything is pushed, so the skip path
    needs no stack unwind. That nil check is not decoration: GetAbilityEnabled reads the
    UNIT's bitset, not the registry, so a save carrying bit 0x89 loaded with the registration
    reverted would otherwise dereference nil on every unit draw. It is why this hook lives in
    the same script as the registration -- and belt-and-braces on top of that coupling.

    ShowLooped is Delphi register convention: EAX/EDX/ECX plus three stack args pushed in
    order (y, frame, target) and CLEANED BY THE CALLEE -- the vanilla block does no `add esp`
    after it, and neither do we.
    """
    m_id = M_ID if m_id is None else m_id
    src = """
        push eax
        push edx
        mov  edx, %d
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x%X]
        test al, al
        jz   L_skip
        call 0x%X
        pop  ecx
        push ecx
        add  ecx, 0x%X
        mov  eax, dword ptr [ecx]
        mov  eax, dword ptr [eax + 0x80]
        mov  edx, %d
        call 0x%X
        pop  ecx
        test eax, eax
        jz   L_skip
        mov  edx, dword ptr [eax + 0x1C]
        mov  eax, dword ptr [ebp - 8]
        add  eax, 0x%X
        push eax
        mov  eax, ecx
        add  eax, 0x%X
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x40]
        push eax
        mov  eax, dword ptr [ebp + 0x0C]
        push eax
        mov  eax, edx
        mov  ecx, dword ptr [ebp - 4]
        add  ecx, 0x%X
        xor  edx, edx
        call 0x%X
    L_skip:
        pop  edx
        pop  eax
        jmp  0x%X
    """ % (m_id, VMT_STRAT_ABENABLED, va, PH_HSSET, m_id, GET_ABILITY,
           ICON_DY, PH_HSMAP, ICON_DX, SHOWLOOPED, GETUNITGFX)
    return fix_pic(asm(src, va), va, 0x59, [(PH_HSSET, HSSET), (PH_HSMAP, HSMAP)])


# ------------------------------------------------------------------ cave zone
def build_zone(name_ptr_bias=8, n_id=None, m_id=None, n_name=None, m_name=None, evil=True,
               with_array=True, with_retal=True, with_ankh=True, _array_va=0):
    """Lay the literals, both caves and the 4-entry strip array out from CAVE
    -> (blob, [(label, va, code)...]).

    The knob arguments exist ONLY so a layout this script shipped earlier can be reproduced
    byte-for-byte and recognised as a valid pre-state (see PRIOR_ZONES). A name is a
    variable-length literal, so changing one moves every cave after it.

    ⚠ THE ARRAY IS PLACED LAST ON PURPOSE. cave_exec has to know its address (it reaches it
    through the PIC anchor), which is a forward reference — resolved by the two-pass in
    build_zone_final() below rather than by moving the array to the front. Putting it in front
    would shift cave_reg and cave_exec by 16 bytes, which changes both hook rel32s and would
    make the ALREADY-INSTALLED hooks read as FOREIGN on the next run.
    """
    n_name = N_NAME if n_name is None else n_name
    m_name = M_NAME if m_name is None else m_name
    blob = bytearray()
    parts = []

    def place_data(label, data, align=4):
        blob.extend(bytes((-len(blob)) % align))
        va = CAVE + len(blob)
        blob.extend(data)
        parts.append((label, va, None))
        return va

    def place(label, builder, align=16):
        blob.extend(bytes((-len(blob)) % align))
        va = CAVE + len(blob)
        code, anchor = builder(va)
        blob.extend(code)
        parts.append((label, va, code))
        return va, anchor

    # ⚠⚠ `+ 8` IS LOAD-BEARING AND ITS ABSENCE IS NOT A NO-OP. A Delphi AnsiString variable
    # holds a pointer to the FIRST CHARACTER; the refcount is at ptr-8 and the length at ptr-4.
    # place_data returns the HEADER address, so the string pointer is header+8. Passing the
    # header instead shipped a game (Embrittle v1) that would not launch at all: @LStrAsg reads
    # the refcount at ptr-8, finds the zero padding before the cave, reads 0 as "a live string,
    # not a literal", and InterlockedIncrement's it — a WRITE into the read+execute CODE
    # section during package init. "Runtime error 216 at 00003924" from both AoW.exe and the
    # editor, with every static check green. The assertion at the bottom of this function is
    # the check that would have caught it.
    n_hdr = place_data("N name literal", literal(n_name))
    m_hdr = place_data("M name literal", literal(m_name))
    place("cave_reg", lambda v: build_reg(v, n_hdr + name_ptr_bias, m_hdr + name_ptr_bias,
                                          n_id, m_id))
    place("cave_exec", lambda v: build_exec(
        v, n_id, evil,
        cmdids_va=(_array_va if with_array else None),
        cmdids_n=(len(CMDIDS_VANILLA) + 1 if with_array else None)))
    if with_retal:
        place("cave_retal", lambda v: build_retal(v, n_id))
    if with_ankh:
        place("cave_ankh", lambda v: build_ankh(v, m_id))
    if with_array:
        va = place_data("CommandAbilityIDs+ours (4 dwords)",
                        struct.pack("<4I", *(CMDIDS_VANILLA + (N_ID if n_id is None else n_id,))))
        assert va == _array_va or _array_va == 0, \
            "array landed at %08X, cave_exec was built for %08X" % (va, _array_va)

    assert len(blob) <= CAVE_ZONE_LEN, "zone overflow: %d > %d" % (len(blob), CAVE_ZONE_LEN)

    if name_ptr_bias == 8:
        code = next(c for l, v, c in parts if l == "cave_reg")
        base = next(v for l, v, c in parts if l == "cave_reg")
        i = next(k for k in range(len(code) - 5)
                 if code[k] == 0xE8 and code[k + 5] == 0x5E)          # the PIC anchor
        anchor = base + i + 5
        # every `add edx, imm32` (81 C2) in cave_reg is a name-pointer resolution
        got = [anchor + struct.unpack_from("<i", code, k + 2)[0]
               for k in range(len(code) - 5) if code[k:k + 2] == b"\x81\xC2"]
        want = [m_hdr + 8, n_hdr + 8]
        assert got == want, (
            "cave_reg resolves its name pointers to %s; they must be %s (header + 8). A Delphi "
            "AnsiString points at the first character — refcount at ptr-8, length at ptr-4. "
            "Off by 8 means @LStrAsg refcounts the padding before the cave and faults on the "
            "read-only CODE section: runtime error 216 at startup."
            % (["%08X" % g for g in got], ["%08X" % w for w in want]))
        for w in want:
            assert struct.unpack_from("<i", blob, w - 8 - CAVE)[0] == -1, \
                "%08X: the dword at ptr-8 is not the -1 literal refcount" % w
    return bytes(blob), parts


def build_zone_final(**kw):
    """Two-pass wrapper: lay out once to LEARN where the array lands, then rebuild with
    cave_exec pointing at it. cave_exec's length cannot depend on the value (it is a fixed
    `add ecx, imm32`), so the second pass reproduces the first pass's layout exactly — which
    the assertion inside build_zone re-checks rather than assuming.

    (Same shape as build_drillmaster.py's `_probe`, for the same reason.)
    """
    probe_blob, probe_parts = build_zone(**kw)
    va = next((v for l, v, _c in probe_parts if l.startswith("CommandAbilityIDs")), 0)
    blob, parts = build_zone(_array_va=va, **kw)
    assert len(blob) == len(probe_blob), \
        "two-pass layout is not stable: %d vs %d bytes" % (len(blob), len(probe_blob))
    return blob, parts


ZONE, PARTS = build_zone_final()
CMDIDS4 = next((v for l, v, _c in PARTS if l.startswith("CommandAbilityIDs")), None)
assert CMDIDS4 is not None, "the 4-entry strip array was not placed"

CAVE_REG = next(v for l, v, _ in PARTS if l == "cave_reg")
CAVE_EXEC = next(v for l, v, _ in PARTS if l == "cave_exec")
CAVE_RETAL = next(v for l, v, _ in PARTS if l == "cave_retal")
CAVE_ANKH = next(v for l, v, _ in PARTS if l == "cave_ankh")


def call_to(site, target):
    return b"\xE8" + struct.pack("<i", target - (site + 5))


def jmp_to(site, target):
    return b"\xE9" + struct.pack("<i", target - (site + 5))


# Every zone layout this script has ever written. Verify-before-write accepts any of them as a
# starting state, so fixing a cave is a REWRITE IN PLACE — never a revert-and-re-apply, which
# this project has no backup stack for. APPEND here whenever a shipped cave changes; never
# replace. A name is a variable-length literal, so a rename moves every literal after it and
# every `add edx, imm32` that reaches one — which is why a prior entry has to carry the old
# NAME, not just an old constant.
#   v1 (2026-09-01)  ability 0x88 was named "Command Undead". Renamed to "Can Command Undead"
#                    by user ruling the same day: it is visible on the caster's in-combat
#                    panel, so it has to read as an informational passive. Functionally
#                    identical — only the literal and the two offsets that reach it move.
#   v2 (2026-09-01)  no 4-entry strip array: cave_exec's own two strip loops read the vanilla
#                    3-entry AoWE.CommandAbilityIDs @0x558E84E4 and counted 3. Superseded when
#                    the engine's six strip loops were repointed (see the strip-list section);
#                    ours had to move with them or two evil casters would double-hold a unit.
#   v3 (2026-09-01)  ability 0x89 was named "Turned". Renamed to "Commanded Undead" by user
#                    ruling: it collided with vanilla 0x22 "Turned Undead" in the same list.
#
# ⚠⚠ A PRIOR IS A WHOLE BUILD, NOT JUST A ZONE BLOB. A name is a variable-length literal and the
# literals sit BEFORE the caves, so changing one moves cave_reg and cave_exec — and therefore
# BOTH HOOK rel32s. Recording only the old zone bytes would leave the two hook sites matching
# neither 'vanilla' nor 'applied', i.e. FOREIGN, and the upgrade would abort on a pre-state this
# script itself shipped. (v3 -> v4 moved cave_reg 0x55832030 -> 0x55832040; that is exactly how
# this was found.) Each entry therefore carries its zone, its two hook targets, and whether the
# strip list was on.
def _prior_build(strip_on, **kw):
    """Reproduce one shipped build in full: zone bytes, both hook targets, and the exact bytes
    it wrote at each of the eleven strip sites.

    ⚠ The strip values are recorded PER BUILD, not taken from the current PATCHES. v3's array
    lived at 0x5583225C and v4's at 0x5583226C — reusing the current address would have made v3
    unrecognisable, which is the same class of bug as recording only the zone blob.
    """
    blob, parts = build_zone_final(**kw)
    reg = next(v for l, v, _c in parts if l == "cave_reg")
    exe = next(v for l, v, _c in parts if l == "cave_exec")
    arr = next((v for l, v, _c in parts if l.startswith("CommandAbilityIDs")), None)
    ret = next((v for l, v, _c in parts if l == "cave_retal"), None)
    ankh = next((v for l, v, _c in parts if l == "cave_ankh"), None)
    count = struct.pack("<I", len(CMDIDS_VANILLA) + (1 if strip_on else 0))
    ptr = struct.pack("<I", arr if strip_on else CMDIDS)
    strip = {iva: count for iva, _o, _f in STRIP_COUNTS}
    strip.update({iva: ptr for iva, _o, _c, _f in STRIP_PTRS})
    strip[CMDIDS_CELL] = ptr
    strip[RETAL_INJ] = (call_to(RETAL_INJ, ret) + NOP2) if ret else RETAL_ORIG
    strip[ANKH_INJ] = call_to(ANKH_INJ, ankh) if ankh else ANKH_ORIG
    return {"zone": blob, "strip_on": strip_on, "strip": strip, "array": arr, "retal": ret,
            "ankh": ankh,
            "hooks": {REG_INJ: call_to(REG_INJ, reg), EXEC_INJ: jmp_to(EXEC_INJ, exe)}}


PRIOR_BUILDS = [
    _prior_build(False, n_name=b"Command Undead", m_name=b"Turned", with_array=False,
                 with_retal=False, with_ankh=False),
    _prior_build(False, n_name=b"Can Command Undead", m_name=b"Turned", with_array=False,
                 with_retal=False, with_ankh=False),
    _prior_build(True, n_name=b"Can Command Undead", m_name=b"Turned", with_array=True,
                 with_retal=False, with_ankh=False),
    _prior_build(True, with_array=True, with_retal=False, with_ankh=False),
    #   v5 (2026-09-01)  retaliation guard present, no Ankh overlay yet.
    _prior_build(True, with_array=True, with_retal=True, with_ankh=False),
]
PRIOR_ZONES = [p["zone"] for p in PRIOR_BUILDS]

# ---- (VA, new bytes, original bytes, description) --------------------------------
PATCHES = [
    # ⚠⚠ THE CAVE ENTRY SPANS THE WHOLE RESERVATION, NOT JUST THE BYTES WE EMIT.
    # It used to be `(CAVE, ZONE, bytes(len(ZONE)))`, i.e. 620 of the 1024 reserved bytes, and
    # that left 0x5583226C..0x55832400 unverified on EVERY path. The separate
    # "zone is zero or one of ours" assertion in apply() covers all 1024 — but it sits AFTER the
    # `if st == want: return` early exit, so on an already-applied install it never ran.
    # QA demonstrated it: `CC CC CC CC` poked at 0x55832300 gave "already applied — nothing to
    # do", show() cheerfully printed "620 B used of 1024 reserved", and the foreign bytes
    # survived until a later --undo silently zeroed them. That is the silent-unlink class, on
    # the REVERT path, which is the one with no backup stack behind it.
    # Padding `new` to the full reservation fixes it three ways at once: state_of compares all
    # 1024 (so a foreign tail is FOREIGN and apply/undo both abort), --apply scrubs any stale
    # tail as it writes, and --undo needs no special case because `orig` is now 1024 zeros.
    (CAVE, ZONE + bytes(CAVE_ZONE_LEN - len(ZONE)), bytes(CAVE_ZONE_LEN),
     "cave zone (%d B of %d reserved, tail verified zero): %s"
     % (len(ZONE), CAVE_ZONE_LEN, ", ".join("%s@%08X" % (l, v) for l, v, _ in PARTS))),
    (REG_INJ, call_to(REG_INJ, CAVE_REG), REG_ORIG,
     "RegisterAbility call -> cave_reg (registers %s 0x%02X + %s 0x%02X)"
     % (M_NAME.decode(), M_ID, N_NAME.decode(), N_ID)),
    (EXEC_INJ, jmp_to(EXEC_INJ, CAVE_EXEC), EXEC_ORIG,
     "TTurnUndeadCA.Execute entry -> cave_exec (evil casters command instead of damaging)"),
    (RETAL_INJ, call_to(RETAL_INJ, CAVE_RETAL) + NOP2, RETAL_ORIG,
     "fcExecuteCombatCommand %08X: retaliation gate -> cave_retal (a SEIZED undead does not "
     "swing back)" % RETAL_INJ),
    (ANKH_INJ, call_to(ANKH_INJ, CAVE_ANKH), ANKH_ORIG,
     "ShowEx epilogue %08X: GetUnitGFXResource call -> cave_ankh (Ankh overlay over a seized "
     "undead, then jmp to the original callee)" % ANKH_INJ),
] + [
    (iva, struct.pack("<I", len(CMDIDS_VANILLA) + 1), struct.pack("<I", len(CMDIDS_VANILLA)),
     "strip count 3 -> 4: %s" % fn)
    for iva, _opc_va, fn in STRIP_COUNTS
] + [
    (iva, struct.pack("<I", CMDIDS4), struct.pack("<I", CMDIDS), "strip array -> %s" % fn)
    for iva, _opc_va, _opc, fn in STRIP_PTRS
] + [
    (CMDIDS_CELL, struct.pack("<I", CMDIDS4), struct.pack("<I", CMDIDS),
     "DATA cell %08X (CombatSpells' pointer to CommandAbilityIDs) -> our 4-entry array"
     % CMDIDS_CELL),
]

# The registration hook and the strip-list patch are ONE unit and the script must never be able
# to ship half of them. Every entry above is in the same PATCHES list, so state_of() collapses
# them into a single verdict and apply() refuses anything but a uniform one — but state that
# intent as an assertion too, because the failure it prevents is severe and silent-looking:
#   * strip list applied, registration reverted  -> the six patched loops call GetAbility(0x88)
#     past the registry Count. GetAbility @0x557501C0 returns NIL there (`cmp esi,[eax+8]; jge
#     -> xor eax,eax`), and the very next instruction is `mov ecx,[eax]` — an instant null
#     dereference on EVERY vanilla Dominate / Seduce / Charm / Possess / Mind Decay, in
#     ordinary play, with our feature nominally "removed".
#   * registration applied, strip list reverted  -> the original defect, silently.
_STRIP_VAS = {iva for iva, _o, _f in STRIP_COUNTS} | {iva for iva, _o, _c, _f in STRIP_PTRS} \
    | {CMDIDS_CELL, RETAL_INJ, ANKH_INJ}
assert _STRIP_VAS <= {va for va, _n, _o, _d in PATCHES} and \
    REG_INJ in {va for va, _n, _o, _d in PATCHES}, \
    "the strip-list sites and the registration hook must live in the SAME patch set"


# ============================================================== file plumbing
def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    tbl = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    out = []
    for i in range(nsec):
        s = tbl + 40 * i
        vsz, rva, rsz, ro = struct.unpack_from("<IIII", d, s + 8)
        out.append((d[s:s + 8].rstrip(b"\0"), rva, max(vsz, rsz), rsz, ro))
    return out


def va2off(d, va):
    """⚠ per-section, never one global delta — this DLL's DATA skews differently from CODE."""
    for _nm, rva, sz, rsz, ro in sections(d):
        if DLL_BASE + rva <= va < DLL_BASE + rva + sz:
            off = ro + (va - DLL_BASE - rva)
            assert off < ro + rsz, "%08X past raw data" % va
            return off
    raise AssertionError("VA %08X in no section" % va)


def off2va(d, off):
    for _nm, rva, sz, rsz, ro in sections(d):
        if ro <= off < ro + rsz:
            return DLL_BASE + rva + (off - ro)
    return None


def reloc_set(d):
    out = set()
    for nm, rva, _sz, rsz, ro in sections(d):
        if nm != b".reloc":
            continue
        p, end = ro, ro + rsz
        while p + 8 <= end:
            page, sz = struct.unpack_from("<II", d, p)
            if sz < 8 or p + sz > end:
                break
            for k in range(p + 8, p + sz, 2):
                e = struct.unpack_from("<H", d, k)[0]
                if e >> 12:
                    out.add(DLL_BASE + page + (e & 0xFFF))
            p += sz
    return out


def read(path):
    with open(path, "rb") as f:
        return bytearray(f.read())


# ==================================================== the two measured checks
def assert_reg_site(d):
    """The registration site must still be a DIRECT `call RegisterAbility`.

    Taking a site another feature already repointed is the documented silent-unlink failure
    (the Magebane/Shield chain note in CLAUDE.md): the earlier feature's cave simply stops
    being called and nothing reports it. Measured on every run, never taken on trust.
    """
    start, end = 0x557BC1CC, 0x557BC1CC + 0xE00
    direct, taken = [], []
    for va in range(start, end):
        o = va2off(d, va)
        if d[o] != 0xE8:
            continue
        tgt = (va + 5 + struct.unpack_from("<i", d, o + 1)[0]) & 0xFFFFFFFF
        if tgt == REGISTER_ABIL:
            direct.append(va)
        elif CAVE_BAND_LO <= tgt < CAVE_BAND_HI:
            taken.append((va, tgt))
    ours = [t for v, t in taken if v == REG_INJ]
    print("  RegisterPassiveAbilities: %d direct calls left, %d repointed (%s)"
          % (len(direct), len(taken),
             ", ".join("%08X->%08X" % (v, t) for v, t in taken) or "none"))
    if ours:
        # ⚠ A PRIOR BUILD'S cave_reg IS STILL OURS. The literals sit before the caves, so a name
        # change moves cave_reg — v3 had it at 0x55832030, v4 at 0x55832040. Comparing only
        # against the CURRENT address made an in-place rename abort with "another feature owns
        # this site", which is both wrong and alarming. Accept every address this script has
        # ever pointed here; anything else really is someone else's.
        mine = {CAVE_REG} | {(va + 5 + struct.unpack_from("<i", p["hooks"][REG_INJ], 1)[0])
                             & 0xFFFFFFFF for p in PRIOR_BUILDS for va in (REG_INJ,)}
        if ours[0] not in mine:
            sys.exit("ABORT: %08X is already repointed to %08X, which is not our cave_reg "
                     "(%s). Another feature owns this site."
                     % (REG_INJ, ours[0], ", ".join("%08X" % m for m in sorted(mine))))
        if ours[0] != CAVE_REG:
            print("    (currently pointing at %08X — an earlier build of this feature; it will "
                  "move to %08X)" % (ours[0], CAVE_REG))
        return
    if REG_INJ not in direct:
        sys.exit("ABORT: %08X is not a direct `call RegisterAbility` and is not ours either. "
                 "Pick another site from: %s"
                 % (REG_INJ, ", ".join("%08X" % v for v in direct[-4:])))
    if direct and REG_INJ != direct[-1]:
        print("  note: %08X is not the LAST direct call (%08X is). Harmless, but the "
              "convention is to chain from the end." % (REG_INJ, direct[-1]))


def _scan_cave_band(d):
    """{id: VA} for every ability id a CAVE registers, our own zone excluded.

    Two idioms, because mods use both and neither is visible to a constructor scan:
      `mov eax,<id>; call CreateEnhancementAbility`  — Magebane 0xAA .. Reforming Flesh 0xB1
      `mov dword ptr [reg+0x0C], <id>`               — an INSTANCE CLONE (Embrittled 0xB2, and
                                                       this feature) poking a cloned object
    The band starts at 0x5580B000, the first cave any build script claims, and ends at the end
    of CODE. Restricting the second idiom to the cave band is what keeps it free of false
    positives: measured 2026-09-01 it returns exactly one hit in the whole band (0xB2).
    """
    out = {}
    start, end = va2off(d, CAVE_BAND_LO), va2off(d, CAVE_BAND_HI)
    ours = range(CAVE, CAVE + CAVE_ZONE_LEN)

    for modrm in (0x40, 0x41, 0x42, 0x43, 0x46, 0x47):            # C7 /0 [reg+disp8=0x0C]
        pat = bytes([0xC7, modrm, 0x0C])
        o = start - 1
        while True:
            o = d.find(pat, o + 1, end)
            if o < 0:
                break
            imm = struct.unpack_from("<I", d, o + 3)[0]
            va = off2va(d, o)
            if imm < 0x200 and va is not None and va not in ours:
                out[imm] = va

    o = start - 1
    while True:                                                    # B8 imm32 ; E8 rel32
        o = d.find(b"\xB8", o + 1, end)
        if o < 0:
            break
        if d[o + 5] != 0xE8:
            continue
        va = off2va(d, o + 5)
        if va is None or va in ours:
            continue
        tgt = (va + 5 + struct.unpack_from("<i", d, o + 6)[0]) & 0xFFFFFFFF
        if tgt == CREATE_ENH:
            out[struct.unpack_from("<I", d, o + 1)[0]] = va
    return out


def assert_strip_sites(d, relocs=None):
    """Verify every strip-list site is the instruction this script was written against.

    Checked per site, and all of it is measured rather than assumed:
      counts   the opcode really is `BB` (mov ebx,imm32) and the immediate is 3 or 4 — nothing
               else. Patching an immediate inside a loop we never re-assemble is only safe if
               the loop is the one we read.
      pointers the opcode really is `BE` (mov esi,imm32), the value is the vanilla array or
               ours, AND the immediate still carries its .reloc entry. That entry is what makes
               a same-module retarget legal: the loader adds the rebase delta to whatever VA is
               stored. Losing it would leave a preferred-base address in a rebased image.
      cell     0x558E91FC likewise — a reloc-covered DATA pointer, not an .idata thunk.
    """
    relocs = reloc_set(d) if relocs is None else relocs
    ok_counts = {len(CMDIDS_VANILLA), len(CMDIDS_VANILLA) + 1}
    # every array address this script has ever pointed a loop at, plus vanilla's
    ok_ptrs = {CMDIDS, CMDIDS4} | {p["array"] for p in PRIOR_BUILDS if p["array"]}
    for iva, opc_va, fn in STRIP_COUNTS:
        got = d[va2off(d, opc_va)]
        cur = struct.unpack_from("<I", d, va2off(d, iva))[0]
        if got != 0xBB or cur not in ok_counts:
            sys.exit("ABORT: %08X (%s) is `%02X ... %d`, expected `BB` (mov ebx,imm32) with an "
                     "immediate in %s. This is not the loop this script was written against."
                     % (opc_va, fn, got, cur, sorted(ok_counts)))
        if iva in relocs:
            sys.exit("ABORT: the loop-count immediate at %08X carries a .reloc entry — it is "
                     "not a plain constant. Investigate before patching it." % iva)
    for iva, opc_va, opc, fn in STRIP_PTRS:
        got = d[va2off(d, opc_va)]
        cur = struct.unpack_from("<I", d, va2off(d, iva))[0]
        if got != opc or cur not in ok_ptrs:
            sys.exit("ABORT: %08X (%s) is `%02X ... %08X`, expected `%02X` with a value in %s."
                     % (opc_va, fn, got, cur, opc,
                        ", ".join("%08X" % v for v in sorted(ok_ptrs))))
        if iva not in relocs:
            sys.exit("ABORT: the array-pointer immediate at %08X has NO .reloc entry. "
                     "Retargeting it would bake a preferred-base address into a module that "
                     "rebases." % iva)
    cur = struct.unpack_from("<I", d, va2off(d, CMDIDS_CELL))[0]
    if cur not in ok_ptrs:
        sys.exit("ABORT: DATA cell %08X holds %08X, neither the vanilla array nor ours."
                 % (CMDIDS_CELL, cur))
    if CMDIDS_CELL not in relocs:
        sys.exit("ABORT: DATA cell %08X has NO .reloc entry — it is not the relocated "
                 "cross-unit pointer this script expects." % CMDIDS_CELL)


NL = chr(10)   # newline, spelled this way so no shell/heredoc can eat a backslash


def ankh_image_count(recs=None):
    """-> number of image sequences in Ability.pfs record 147's tag 8, or None if no record.

    The tag directory is parsed the way build_drillmaster.pfs_tag9_offset does it: byte 0 low
    7 bits = short-entry count, bit 7 = a u32 long-entry count follows, then (tag, off) pairs
    as bytes and then as u32 pairs, offsets relative to the end of the directory. Tag 8's
    payload begins with a u32 sequence count; `00 00 00 00` is the EMPTY list.
    """
    import importlib.util
    if recs is None:
        sp = os.path.join(GAME, "Modding Resources", "re_tools", "pfs.py")
        spec = importlib.util.spec_from_file_location("pfs", sp)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        recs = m.load("ability.pfs")[0]
    body = dict(recs).get(M_ID + 10)
    if body is None:
        return None
    p = 1 + (4 if body[0] & 0x80 else 0)
    ent = [(body[1 + 2 * k], body[2 + 2 * k]) for k in range(body[0] & 0x7F)]
    p += 2 * len(ent)
    for k in range(struct.unpack_from("<I", body, 1)[0] if body[0] & 0x80 else 0):
        t, o = struct.unpack_from("<II", body, p + 8 * k); ent.append((t, o))
    p += 8 * (len(ent) - (body[0] & 0x7F))
    for t, o in ent:
        if t == 8:
            return struct.unpack_from("<I", body, p + o)[0]
    return 0


def assert_ankh_pfs(recs=None):
    """Abort unless Release/Ability.pfs record 147 (= 0x89 + 10) exists AND its tag 8 holds at
    least one image sequence -- the record build_commandedundead_pfs.py writes.

    Presence alone is NOT the precondition. The sibling record 146 (0x88, the caster's passive)
    exists and is CORRECTLY icon-less: `tag 8 = 00 00 00 00`. A 147 that looked like that would
    pass a presence check and still leave `[ability+0x1C]` the empty TImageSequenceList that
    TAbility.Create built -- and ImageLib.Get has no bounds check (Copper_Medal_Design.md; the
    Embrittle note), so drawing from it is an out-of-range read on every seized-unit draw, not
    a blank icon. The data is a precondition of the hook, checked at apply time, never assumed.
    """
    try:
        n = ankh_image_count(recs)
    except Exception as exc:                                             # noqa: BLE001
        sys.exit("ABORT: could not read Release/Ability.pfs (%s); the Ankh hook needs record "
                 "%d with a non-empty image list and I cannot prove it has one."
                 % (exc, M_ID + 10))
    if n is None:
        sys.exit(("ABORT: Release/Ability.pfs has no record %d for ability 0x%02X, so its image "
                  "sequence is EMPTY and the Ankh hook would read past the end of it. Run" + NL +
                  "       python build_scripts/build_commandedundead_pfs.py --apply" + NL +
                  "       first, then re-run this script.") % (M_ID + 10, M_ID))
    if n < 1:
        sys.exit("ABORT: Release/Ability.pfs record %d (0x%02X) exists but its tag 8 image list "
                 "is EMPTY -- the hook would draw from an empty TImageSequenceList (no bounds "
                 "check in ImageLib.Get). Re-run build_commandedundead_pfs.py --apply."
                 % (M_ID + 10, M_ID))
    print("  Ability.pfs record %d (0x%02X %s) present with %d image sequence(s) -- the Ankh "
          "has frames to draw" % (M_ID + 10, M_ID, M_NAME.decode(), n))


def check_ids_free(d):
    """Abort unless both ids are free. Every source is RE-DERIVED from the binary, never quoted.

    A duplicate id is not a soft failure: RegisterAbility raises during package init, before a
    handler exists, and Delphi reports `Runtime error 217` before the main window appears.

    ⚠⚠ WHICH SOURCES MAY DRIVE THE ABORT IS THE WHOLE DESIGN HERE, AND GETTING IT WRONG BRICKS
    THE SCRIPT. Only sources that STRUCTURALLY CANNOT CONTAIN OUR OWN IDS are allowed to abort:

      ABORTS   _scan_cave_band(d)                    — our cave zone is excluded from it, so a
                                                       hit on 0x88/0x89 is genuinely someone
                                                       else's cave
               ability_names._from_constructors()    — real ability classes only, gated on the
                                                       ctor chaining to TAbility.Create; a cave
                                                       is not an exported `*.Create`, so ours
                                                       can never appear here

      WIDENS   ability_names.names()                 — includes the MODDED map, which carries
      ONLY                                             OUR ids from the moment this feature
                                                       ships
               Release/Ability.pfs record keys       — DevEd writes a record for our ids the
                                                       first time the set is saved

    The rejected design, because it shipped and QA hit it: gate the exclusion on "is our
    cave_reg installed", subtracting N_ID/M_ID from ability_names.names() only then. `--undo`
    ZEROES the cave, so `installed` goes False while the MODDED entry stays — and because
    show() runs before apply(), EVERY mode then aborted, including the undo itself and the bare
    dry run. The feature was left with no revert path at all. Never key a self-exclusion off
    state that the undo destroys; key it off what the source structurally can and cannot see.

    (`build_drillmaster.py` records the same rule for Ability.pfs alone. This is that rule
    generalised to the whole id oracle.)
    """
    known, ctor_ids = {}, {}
    try:
        sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
        import ability_names
        known = dict(ability_names.names())
        ctor_ids = dict(ability_names._from_constructors())          # noqa: SLF001
    except Exception as exc:                                         # noqa: BLE001
        print("  ⚠ could not read re_tools/ability_names.py (%s) — the id check is running on "
              "the cave scan alone, which is WEAKER. Investigate before trusting it." % exc)

    cave_ids = _scan_cave_band(d)
    aborting = set(ctor_ids) | set(cave_ids)                          # may abort
    widening = set(known) | aborting                                  # report only

    bad = [i for i in (N_ID, M_ID) if i in aborting]
    if bad:
        free = [x for x in range(1, 0xAA) if x not in widening]
        sys.exit("ABORT: ability id(s) %s already registered — this is the collision that shows "
                 "in game as `Runtime error 217`.\n"
                 "       Owners: %s\n"
                 "       Free ids below the 170 selectable-ability bound: %s"
                 % (", ".join("0x%02X" % i for i in bad),
                    ", ".join("0x%02X=%s" % (i, ctor_ids.get(i) or "cave @%08X" % cave_ids[i])
                              for i in bad),
                    ", ".join("0x%02X" % x for x in free)))
    print("  ids 0x%02X (%s) and 0x%02X (%s) free — %d ids known (%d from class ctors), highest "
          "0x%02X; other caves registering ids: %s"
          % (N_ID, N_NAME.decode(), M_ID, M_NAME.decode(), len(widening), len(ctor_ids),
             max(widening),
             ", ".join("0x%02X@%08X" % (k, v) for k, v in sorted(cave_ids.items())) or "none"))
    if max(N_ID, M_ID) >= 0xAA:
        print("  ⚠ an id is at/above 0xAA: bump the LADDER in build_abilityid_ceilings.py AND "
              "build_tcablist_ceiling.py, and re-check the bound eax,(0,169) hazard.")


# =================================================================== reporting
STRIP_SITE_VAS = _STRIP_VAS


def state_of(d):
    """-> ('applied' | 'vanilla' | 'stale' | 'mixed', per-site verdicts).

    ⚠ A PRIOR ZONE IS SHORTER THAN THE CURRENT ONE, so it can only be matched as a PREFIX with
    an all-zero tail — never by equality. Comparing `cur == prior[:len(cur)]` (which is what
    this did before the strip array was appended) can never be true once the zone grows: the
    slice is just the whole shorter prior. That read as FOREIGN and would have aborted the
    upgrade over a perfectly legitimate pre-state.

    'stale' here means one specific, legitimate combination — an EARLIER VERSION OF THIS
    FEATURE, before the strip list existed: zone = a layout we shipped, both hooks ON, all
    eleven strip sites still vanilla. That is a real install to upgrade in place. Anything else
    with a mixture is 'mixed' and aborts, because a genuine half-applied strip list is the
    null-dereference described in the docstring.
    """
    prior = next((p for p in PRIOR_BUILDS if _matches_prior(d, p)), None)
    verdicts = []
    for va, new, orig, desc in PATCHES:
        o = va2off(d, va)
        cur = bytes(d[o:o + len(new)])
        if cur == new:
            v = "applied"
        elif cur == orig:
            v = "vanilla"
        elif prior is not None:
            v = "stale"
        else:
            v = "FOREIGN"
        verdicts.append((va, desc, v))

    kinds = {v for _va, _d, v in verdicts}
    if kinds == {"applied"}:
        return "applied", verdicts
    if kinds == {"vanilla"}:
        return "vanilla", verdicts
    if prior is not None:
        return "stale", verdicts
    return "mixed", verdicts


def _matches_prior(d, p):
    """Is the install EXACTLY one earlier build of this feature — zone, both hooks, and the
    strip list all together?

    Checked as a whole rather than site by site, so a half state can never be waved through as
    'stale'. The zone is matched as a PREFIX with an all-zero tail, because an older zone is
    shorter than the current one and could never match by equality.
    """
    o = va2off(d, CAVE)
    cur = bytes(d[o:o + CAVE_ZONE_LEN])
    z = p["zone"]
    if not (cur[:len(z)] == z and set(cur[len(z):]) <= {0}):
        return False
    for va, want in p["hooks"].items():
        if bytes(d[va2off(d, va):va2off(d, va) + len(want)]) != want:
            return False
    for va, want in p["strip"].items():
        if bytes(d[va2off(d, va):va2off(d, va) + len(want)]) != want:
            return False
    return True


def show():
    d = read(DLL)
    st, verdicts = state_of(d)
    relocs = reloc_set(d)
    print("build_turnundead_evilcommand — evil Turn Undead COMMANDS instead of damaging")
    print("target: %s" % DLL)
    print()
    check_ids_free(d)
    assert_reg_site(d)
    assert_strip_sites(d, relocs)
    assert_ankh_pfs()
    print()
    for va, desc, v in verdicts:
        print("  %08X  %-8s  %s" % (va, v, desc))
    print()
    print("  state: %s   cave zone %08X..%08X (%d B used of %d reserved)"
          % (st.upper(), CAVE, CAVE + CAVE_ZONE_LEN, len(ZONE), CAVE_ZONE_LEN))
    exempt = {iva for iva, _o, _c, _f in STRIP_PTRS} | {CMDIDS_CELL}
    bad = [hex(x) for va, new, _o, _d in PATCHES if va != CAVE and va not in exempt
           for x in relocs if va <= x < va + len(new)]
    print("  .reloc: %s displaced run(s) cover an entry; the %d retargeted pointer(s) all "
          "keep theirs (required)" % (bad or "no", len(exempt)))
    # The coupling, restated at runtime over the LIVE bytes rather than over the patch table.
    # ⚠ "ON" means "one of OURS", not "the current build's": a name change moves cave_reg and
    # the array, so comparing only against today's addresses reported a perfectly healthy v3
    # install as OFF/OFF. What matters for the coupling is that the two halves agree.
    ours_reg = {call_to(REG_INJ, CAVE_REG)} | {p["hooks"][REG_INJ] for p in PRIOR_BUILDS}
    ours_arr = {CMDIDS4} | {p["array"] for p in PRIOR_BUILDS if p["array"]}
    reg_on = bytes(d[va2off(d, REG_INJ):va2off(d, REG_INJ) + 5]) in ours_reg
    # ⚠ ALL TWELVE COUPLED SITES, not just STRIP_PTRS[0]. Deriving this from one pointer made
    # the line read "strip list ON -> consistent" for a guard-only, lone-count or
    # DATA-cell-only divergence that state_of correctly called MIXED. The write-time assertion
    # always covered all twelve, so nothing could ship broken — but this line is what a human
    # reads to answer "are the halves in step?", and it was answering wrongly.
    ours_cnt = len(CMDIDS_VANILLA) + 1
    coupled = [struct.unpack_from("<I", d, va2off(d, iva))[0] in ours_arr
               for iva, _o, _c, _f in STRIP_PTRS]
    coupled.append(struct.unpack_from("<I", d, va2off(d, CMDIDS_CELL))[0] in ours_arr)
    coupled += [struct.unpack_from("<I", d, va2off(d, iva))[0] == ours_cnt
                for iva, _o, _f in STRIP_COUNTS]
    ours_ret = {call_to(RETAL_INJ, CAVE_RETAL) + NOP2} | {p["strip"][RETAL_INJ]
                                                          for p in PRIOR_BUILDS}
    ours_ret.discard(RETAL_ORIG)
    coupled.append(bytes(d[va2off(d, RETAL_INJ):va2off(d, RETAL_INJ) + 7]) in ours_ret)
    ours_ankh = {call_to(ANKH_INJ, CAVE_ANKH)} | {p["strip"][ANKH_INJ] for p in PRIOR_BUILDS}
    ours_ankh.discard(ANKH_ORIG)
    coupled.append(bytes(d[va2off(d, ANKH_INJ):va2off(d, ANKH_INJ) + 5]) in ours_ankh)
    on = sum(coupled)
    strip_on = on == len(coupled)
    print("  coupling: registration hook %s, %d/%d coupled sites ON  -> %s"
          % ("ON " if reg_on else "OFF", on, len(coupled),
             "consistent" if reg_on == strip_on else
             "an EARLIER version of this feature — upgrade in place" if st == "stale" else
             "⚠⚠ HALF-APPLIED — apply() will refuse to write"))
    return st


def disassemble():
    d = read(DLL)
    print()
    for label, va, code in PARTS:
        o = va2off(d, va)
        if code is None:
            is_array = label.startswith("CommandAbilityIDs")
            blob = (struct.pack("<4I", *(CMDIDS_VANILLA + (N_ID,))) if is_array
                    else literal(N_NAME if label.startswith("N") else M_NAME))
            live = bytes(d[o:o + len(blob)])
            tag = "" if live == blob else ("   (not yet applied)" if set(live) <= {0}
                                           else "   ⚠ LIVE DIFFERS — shown: THIS BUILD")
            print("; ---- %s @%08X (%d B)%s ----" % (label, va, len(blob), tag))
            if is_array:
                names = ("Seduce", "Dominate", "Charm", N_NAME.decode())
                for i in range(4):
                    print("     %08X  %s  = 0x%02X  %s"
                          % (va + i * 4, blob[i * 4:i * 4 + 4].hex(" "),
                             struct.unpack_from("<I", blob, i * 4)[0], names[i]))
            else:
                print("     refcount %s  length %s  string ptr %08X -> %r"
                      % (blob[:4].hex(" "), blob[4:8].hex(" "), va + 8, blob[8:-1]))
            print()
            continue
        live = bytes(d[o:o + len(code)])
        tag = "" if live == code else ("   (not yet applied)" if set(live) <= {0}
                                       else "   ⚠ LIVE DIFFERS — shown: THIS BUILD")
        print("; ---- %s @%08X (%d B)%s ----" % (label, va, len(code), tag))
        for ins in cs.disasm(code, va):
            print("  %08X  %-18s %-6s %s"
                  % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))
        print()
    # ⚠ ONLY THE TWO HOOK SITES ARE CODE. The other eleven are raw immediates and dwords, and
    # disassembling them produces plausible-looking nonsense: `04 00` renders as `add al, 0` and
    # a 4-byte pointer as `pop esp`. --dis exists to be READ, and a reviewer's eye must not land
    # on `pop esp` at a patch site and have to work out that it is not an instruction.
    print("; ---- hook sites: CODE (bytes THIS BUILD writes) ----")
    for va, new, orig, desc in PATCHES:
        if va not in (REG_INJ, EXEC_INJ, RETAL_INJ, ANKH_INJ):
            continue
        print("  ; was: %s" % " ".join("%02X" % b for b in orig))
        for ins in cs.disasm(new, va):
            print("  %08X  %-18s %-6s %-14s ; %s"
                  % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str, desc))
            desc = ""

    print()
    print("; ---- strip-list sites: DATA, not code — shown as dwords ----")
    for va, new, orig, desc in PATCHES:
        if va in (CAVE, REG_INJ, EXEC_INJ, RETAL_INJ, ANKH_INJ):
            continue
        o, n = struct.unpack("<I", orig)[0], struct.unpack("<I", new)[0]
        if va == CMDIDS_CELL or va in {iva for iva, _o, _c, _f in STRIP_PTRS}:
            note = "%08X -> %08X   (%s -> our 4-entry array)" % (
                o, n, "AoWE.CommandAbilityIDs" if o == CMDIDS else "?")
        else:
            note = "%d -> %d          (loop trip count)" % (o, n)
        print("  %08X  %-18s dd     %s" % (va, new.hex(" "), note))
        print("  %s; %s" % (" " * 28, desc))


# ==================================================================== writing
def apply(undo=False):
    kill_aow()
    d = read(DLL)
    st, verdicts = state_of(d)
    foreign = [(va, desc) for va, desc, v in verdicts if v == "FOREIGN"]
    if foreign:
        for va, desc in foreign:
            print("  ABORT: %08X holds neither our bytes nor vanilla — %s" % (va, desc))
        sys.exit("aborted: verify-before-write refused (another feature owns a site)")

    want = "vanilla" if undo else "applied"
    if st == want:
        print("  already %s — nothing to do" % want)
        return
    if st == "mixed":
        # Not an abort: a mixed state is one this script cannot produce (every write is uniform,
        # and the assertion below re-checks that), so arriving here means the install is ALREADY
        # inconsistent — quite possibly in the null-dereference state. Both --apply and --undo
        # repair it. Refusing would leave the user broken. But it must never be silent.
        odd = [(va, desc, v) for va, desc, v in verdicts if v != verdicts[0][2]]
        print("  ⚠⚠ THE INSTALL IS ALREADY HALF-APPLIED — this script cannot have produced it.")
        for va, desc, v in odd:
            print("       %08X  %-8s  %s" % (va, v, desc))
        print("     Proceeding to a uniform '%s'; that repairs it. If you did not expect this,\n"
              "     stop and find out who wrote those bytes before trusting the result." % want)
    if not undo:
        check_ids_free(d)
        assert_reg_site(d)
        assert_ankh_pfs()

    relocs = reloc_set(d)
    assert_strip_sites(d, relocs)
    # ⚠ The four `mov esi, imm32` array loads and the CombatSpells DATA cell are RELOC-COVERED
    # BY DESIGN and are therefore exempt from the "displaces no .reloc entry" rule — they are
    # not displaced, their VALUE is retargeted within the same module, which is exactly what
    # keeps the existing entry correct. assert_strip_sites() checks the inverse for them: that
    # the entry is still there. Everything else must be reloc-free.
    exempt = {iva for iva, _o, _c, _f in STRIP_PTRS} | {CMDIDS_CELL}
    for va, new, _orig, _desc in PATCHES:
        if va == CAVE or va in exempt:
            continue
        clash = [x for x in relocs if va <= x < va + len(new)]
        assert not clash, "%08X displaces a .reloc entry %s" % (va, [hex(x) for x in clash])

    o = va2off(d, CAVE)
    zone = bytes(d[o:o + CAVE_ZONE_LEN])
    ok = (set(zone) <= {0}
          or zone[:len(ZONE)] == ZONE and set(zone[len(ZONE):]) <= {0}
          or any(zone[:len(p)] == p and set(zone[len(p):]) <= {0} for p in PRIOR_ZONES))
    assert ok, ("cave zone %08X holds bytes that are neither zero nor a layout this script "
                "shipped — someone else is there" % CAVE)

    # ⚠ BACKUP GATING — only ever snapshot a file PROVED not to carry this feature. A positive
    # test that every site still holds its vanilla bytes, never "no backup file exists yet":
    # on --undo the file is the patched state by definition, and on a re-tune it is this
    # script's own previous output. Either would mint a `.pre-*` full of patched bytes.
    if not undo and st == "vanilla" and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("  backup -> %s (every site verified un-patched)" % os.path.basename(BACKUP))
    elif not undo and not os.path.exists(BACKUP):
        print("  no backup taken: the file is not un-patched at these sites "
              "(a .pre-* full of patched bytes is worse than none).")

    # One uniform loop, no special case for CAVE: its `new` is the zone padded to the full
    # reservation and its `orig` is CAVE_ZONE_LEN zeros, so --apply scrubs the tail and --undo
    # zeroes the whole zone surgically. (The old code zeroed the zone separately BEFORE the
    # loop, which is what let the tail drift out of state_of's view — see PATCHES.)
    for va, new, orig, _desc in PATCHES:
        oo = va2off(d, va)
        d[oo:oo + len(new)] = orig if undo else new

    # ⚠ THE COUPLING, ENFORCED ON THE BUFFER ABOUT TO BE WRITTEN. Checked here rather than only
    # in the patch table because this is the state that reaches disk. Half-applied is not a
    # cosmetic inconsistency: strip-list-on with registration-off makes every vanilla Dominate /
    # Seduce / Charm / Possess / Mind Decay call GetAbility(0x88), get NIL back (it is past the
    # registry Count), and immediately `mov ecx,[eax]`.
    reg_on = bytes(d[va2off(d, REG_INJ):va2off(d, REG_INJ) + 5]) == call_to(REG_INJ, CAVE_REG)
    strip_on = [struct.unpack_from("<I", d, va2off(d, iva))[0] == CMDIDS4
                for iva, _o, _c, _f in STRIP_PTRS]
    strip_on.append(struct.unpack_from("<I", d, va2off(d, CMDIDS_CELL))[0] == CMDIDS4)
    strip_on += [struct.unpack_from("<I", d, va2off(d, iva))[0] == len(CMDIDS_VANILLA) + 1
                 for iva, _o, _f in STRIP_COUNTS]
    # The retaliation guard is part of the same unit. Left installed with the registration
    # reverted, cave_exec would be gone, so a successful roll would be an ordinary STUN --
    # and the guard would then suppress retaliation on an evil caster's stun, a silent
    # behaviour change on a feature the user believes they removed.
    strip_on.append(bytes(d[va2off(d, RETAL_INJ):va2off(d, RETAL_INJ) + 7])
                    == call_to(RETAL_INJ, CAVE_RETAL) + NOP2)
    # and the Ankh hook: left installed with the registration reverted it would read a
    # registry slot that is nil (the cave nil-checks, so no crash -- but it is our hook on a
    # feature the user believes they removed, and it must go with the rest).
    strip_on.append(bytes(d[va2off(d, ANKH_INJ):va2off(d, ANKH_INJ) + 5])
                    == call_to(ANKH_INJ, CAVE_ANKH))
    assert len(set(strip_on)) == 1, \
        "the 13 coupled sites disagree with each other: %r" % strip_on
    assert reg_on == strip_on[0], (
        "REFUSING TO WRITE A HALF-APPLIED STATE: registration hook %s but the coupled "
        "sites %s. "
        "Strip-list-on with registration-off null-dereferences on every vanilla mind-control "
        "in ordinary play; registration-on with strip-list-off silently reinstates the "
        "double-controller defect." % ("ON" if reg_on else "OFF",
                                       "ON" if strip_on[0] else "OFF"))

    try:
        with open(DLL, "wb") as f:
            f.write(d)
    except PermissionError:
        sys.exit("  LOCKED — an AoW binary is still holding AoWEPACK.dpl. Re-run.")
    print("  AoWEPACK.dpl  %s  (%d sites + cave zone)"
          % ("REVERTED" if undo else "PATCHED", len(PATCHES) - 1))

    st2, _ = state_of(read(DLL))
    assert st2 == want, "read-back says %s, expected %s" % (st2, want)
    print("  read-back verified: %s  (registration + strip list in step)" % st2)

    print()
    if undo:
        print("  reverted. Turn Undead is back to damage+stun for every alignment.")
        return
    print("  NEXT:")
    print("      python \"Modding Resources/re_tools/rng_audit.py\" --owners   # expect no new site")
    print()
    print("  ⚠⚠ LAUNCH THE GAME FIRST, BEFORE ANY OTHER TEST. cave_reg runs at PACKAGE INIT and")
    print("     no static check can see an init-time fault (Embrittle precedent: runtime error")
    print("     216 with every static check green). If AoW.exe or AoWDevEd.exe dies on launch:")
    print("       216 = GPF (a bad pointer in cave_reg)   217 = duplicate ability id")
    print("     `--undo` restores both hooks and zeroes the cave.")
    print()
    print("  NEEDS THE USER'S IN-GAME TEST — nothing below can be checked from the files:")
    print("   1. A GOOD or NEUTRAL Turn Undead user still damages and stuns exactly as before.")
    print("   2. An EVIL or PURE EVIL user seizes the undead target instead: no damage, no")
    print("      stun, the unit changes side mid-battle.")
    print("   3. The seized unit shows \"%s\" in its ability list while it is held."
          % M_NAME.decode())
    print("      ⚠ Read that list carefully: vanilla ability 0x22 \"Turned Undead\" (Turn")
    print("      Undead's own panic/flee status) can appear on a unit in the SAME battle, and")
    print("      the two names were chosen to be told apart. Confirm they read distinctly on")
    print("      screen, and that \"%s\" pairs obviously with the caster's \"%s\"."
          % (M_NAME.decode(), N_NAME.decode()))
    print("   4. KILL THE CASTER in the same battle -> the seized unit reverts to its original")
    print("      owner. This is the ownership-gate test; it is the one that fails silently if")
    print("      the SetAb in cave_exec ever stops working.")
    print("   5. Caster SURVIVES the battle -> the unit stays yours afterwards.")
    print("   6. An evil caster cannot seize an undead that is ALREADY on its own side.")
    print("   7. THE STRIP LIST — what the 11 extra sites buy, and none of it is checkable off")
    print("      the files. Seize an undead, then have an ENEMY take it off you with EACH of:")
    print("      Dominate, Seduce, Charm, Possess, and the MIND DECAY combat spell. Every time,")
    print("      the unit must end up with exactly ONE controller, and killing YOU afterwards")
    print("      must NOT hand it back to you. Mind Decay is the one nobody would think to")
    print("      try: it reaches the id list through a DATA pointer cell and was invisible to")
    print("      the byte scan — Ghidra's xrefs found it.")
    print("      Mirror case: a SECOND evil Turn Undead caster seizing what the first holds.")
    print("      ⚠ MIND DECAY IS ONE-DIRECTIONAL AND THAT IS CORRECT. It now releases OUR hold,")
    print("      but seizing a unit that is ALREADY Mind-Decayed does not clear its \"Decay\"")
    print("      status — Mind Decay grants ability 0x83 and flips the side directly, with no")
    print("      command record to strip. Vanilla Dominate behaves identically, so do not")
    print("      report that direction as a bug in this feature.")
    print("      And the regression side: vanilla Dominate/Seduce/Charm/Possess/Mind Decay")
    print("      between two units with NO involvement of ours must behave exactly as before.")
    print("   8. The caster's IN-COMBAT ability panel will list \"%s\" from the first"
          % N_NAME.decode())
    print("      successful seize onwards, at the FRONT (selectable) end — EXPECTED, and ruled")
    print("      acceptable. Check only that the wording reads as an informational passive and")
    print("      that clicking it does nothing harmful (it has no targeting mode: AbilTypes is")
    print("      0 for this id).")
    print("   9. RETALIATION. A SUCCESSFULLY seized undead must NOT swing back at its new")
    print("      owner. A FAILED evil Turn Undead attempt still draws a retaliation strike,")
    print("      and so does a non-evil caster's successful stun — vanilla behaviour on both")
    print("      counts, deliberately unchanged. Those three cases are the whole guard.")
    print("  9b. THE ANKH. Seize an undead with an evil caster in BOTH manual tactical and")
    print("      auto-resolve: the Ankh status icon loops over the seized unit, in the same")
    print("      place Dominated/Seduced/Charmed draw theirs. A NON-evil caster's stunned")
    print("      target still shows Turned Undead exactly as before. Nothing new appears over")
    print("      any other unit -- if something does, the hook is drawing for the wrong bit.")
    print("  10. Auto-resolve a battle with an evil Turn Undead user — no assert dialog.")


if __name__ == "__main__":
    args = set(sys.argv[1:])
    if args - {"--apply", "--undo", "--dis"}:
        sys.exit(__doc__.split("Implements")[0])
    if "--dis" in args:
        disassemble()
    elif "--undo" in args:
        show(); apply(undo=True)
    elif "--apply" in args:
        show(); apply()
    else:
        show()
        disassemble()
        print()
        print("(dry run — nothing written.  --apply to patch, --undo to revert)")
