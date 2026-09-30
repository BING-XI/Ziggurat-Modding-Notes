#!/usr/bin/env python3
r"""
AoW1 mod -- the FIRMAMENT (a fourth map level, index 3, filled with Sky
terrain 0x0E and treated as SURFACE by the rules that matter) and, since v3,
the ABYSS (a fifth map level, index 4, a third cave level BELOW Depths).

DISPLAY NAMES: **Firmament** and **Abyss**.  The script filename predates both
and is left alone; every user-visible string says "Firmament", deliberately
distinct from the Sky *terrain* (id 0x0E) that fills it.  The level-strip
caption literals live in the exes and belong to build_skylevel_ui.py.

LEVEL ORDER, top to bottom, against the STORED index (which is simply the order
the levels were added in):

    Firmament 3  /  Surface 0  /  Caverns 1  /  Depths 2  /  Abyss 4

So "one level down" from Depths is index 4, and "one level up" from the Abyss
is index 2.  Vanilla computes a cave's other end as level +/- 1; section G
routes every such site through one helper that knows the order above.

Target: AoWEPACK.dpl ONLY.  The AoW.exe / AoWCompat.exe world-map level-strip
UI is a separate feature (build_skylevel_ui.py, exe cave 0x0062A000); this
script does not touch either exe.

USER RULINGS BAKED IN (2026-09-06)
  * The Firmament is level INDEX 3.  Display order is the UI half's problem.
  * Vision: the Firmament counts as SURFACE -- unhalved, and no Night Vision
    needed.  BOTH `VisibilityRange` level compares flip.
  * Global-target spells are ALLOWED from the Firmament (the "cannot cast
    underground" gate gets the same surface-or-firmament predicate).
  * v2 (2026-09-06): STORM SPELLS and BIRD'S VIEW follow the same global-target
    ruling -- castable while viewing the Firmament, still refused on Caverns
    and Depths.  Three more gates, section F below.
  * Towers are BUILDABLE on the Firmament, and on every other level, because
    TTowerConstructionControl.CanConstruct @0x557C38D4 has no live level gate
    left: its `cmp byte [ebp-3],0` at 0x557C390D is followed by `90 90` where
    the pristine DLL has `jne 0x557C3922`, so the result is discarded.  This
    script deliberately does not touch the function -- but "not touched" does
    NOT mean "still blocked", and an earlier version of this note said it did.
    The NOP pair is an undocumented pre-convention live edit owned by no build
    script.  Byte-compared against AoWEPACK_original_backup.dpl 2026-09-09.
  * The 6-hex border ring (terrain 0x0F) stays on the Firmament, like every
    other level.
  * Earth elementals do NOT heal on the Firmament, and (v6, 2026-09-06) AIR
    elementals DO -- both live in build_waterheal.py (cave 0x55824000), not
    here.  See the FORWARD HAZARD below.

  v3 (2026-09-27, owner request): THE ABYSS
  * Level INDEX 4, displayed and linked BELOW Depths.  Levels are appended in
    index order, so a map with an Abyss stores index 3 too -- since v4 that
    level may be a DISABLED placeholder (section H).
  * It is an ordinary cave level: EarthWall fill, halved vision, no global /
    storm / Bird's View casting, the underground ranged malus.  Every one of
    those already holds for index 4 with no change, because each existing test
    is `level == 0` or `level == 0 or 3` (section G lists them).
  * Caves link Depths <-> Abyss.

  v5 (2026-09-30, owner request): FIRMAMENT <-> SURFACE CAVES
  * The Firmament joins the top of the cave chain: (3, 0, 1, 2, 4).  The map
    maker places a cave while viewing the Firmament, as for every cave (always
    on the higher level); its lower mouth spawns on the Surface.  A Surface cave
    placed from the Surface still leads to Caverns; one Surface hex holds one
    mouth, so the two kinds never share a hex.
  * Only strict4's chain changes (section I).  Every site, the placement
    guards and the pathfinder link already go through twin_strict.

NO RANDOM DRAWS.  Not one block in this cave rolls anything, so neither RNG is
involved and `rng_audit.py --owners` is unchanged by this feature.

================================================================================
WHAT IS PATCHED  (every byte below read LIVE with re_tools/dasm.py, 2026-09-06;
                  every displaced range checked .reloc-free)
================================================================================
A. THE CAP BYTE -- 1 byte, no cave
   TAoWHSMap.AddMapLevel @0x55777684
     5577768B  83 7E 14 03   cmp dword ptr [esi+0x14], 3
     5577768F  jge <bail>
   The imm8 at 0x5577768E (file 0x76A8E) is the level ceiling: `>= 3 -> refuse`.
   03 -> 04 (v1/v2, the Firmament) -> 05 (v3, the Abyss).  Nothing else in the
   DLL encodes the ceiling; build_shipyard_income.py's MAX_LEVELS must track it.

B. THE FIRMAMENT FILL -- hook @0x5577747E -> cave_fillterr
   TAoWHSMap.InitializeMapLevel @0x557773CC (EAX=map, DL=level) has two arms:
   level 0 fills the interior with Water(0) inset 6; every other level fills the
   interior with EarthWall(7) from 1..w-7.  Both arms then fall into the shared
   6-hex border ring at terrain 0x0F.
   The `!= 0` arm's inner loop, live:
     55777479  53              push ebx          ; loop entry -- back-jump target
     5577747A  8A 44 24 08     mov  al, [esp+8]  ; AL = the level parameter
     5577747E  50              push eax          ; param5 = level
     5577747F  6A 07           push 7            ; param6 = TERRAIN  <-- the knob
     55777481  8B CE           mov  ecx, esi
     55777483  8B 44 24 0C     mov  eax, [esp+0xC]
     ...       call [ebp+0x50]                   ; SetTerrain-alike
   The param order was read off the level-0 arm (`push ebx / push 0 / push 0` --
   level 0, terrain 0 = water) and off the ring (`push ebx / push al / push 0xF`),
   so param6 is unambiguously the terrain byte.
   AL ALREADY HOLDS THE LEVEL one instruction before the terrain push, which is
   why the hook sits at 0x5577747E and not at the push itself: 0x5577747E..82
   (`50 6A 07 8B CE`) is exactly 5 bytes -- one E9, nothing displaced twice, and
   the cave never has to re-read the stack.  Resumes at 0x55777483.
   ⚠ 0x55777479 (the loop's back-jump target) is BEFORE the hook and untouched.

C. THE VISION PREDICATE -- two hooks -> cave_vis1 / cave_vis2
   TAbstractUnit.VisibilityRange @0x55780EF8, live:
     55780F2D  call TAbstractUnit.GetLocation   ; locals: [esp]=x [esp+1]=y [esp+2]=level
     55780F32  80 7C 24 02 00  cmp byte [esp+2], 0
     55780F37  74 13           je  0x55780F4C     ; surface -> skip the Night Vision test
     55780F39  ...             GetAbility(0x27)   ; underground: need Night Vision
     55780F4A  74 2A           je  0x55780F76     ; ...else HALVE
     55780F4C  80 7C 24 02 00  cmp byte [esp+2], 0
     55780F51  75 26           jne 0x55780F79     ; underground -> done, no halve
     55780F53  ...             surface: player flag bit 3 -> halve
     55780F76  46 / D1 EE      inc esi ; shr esi,1
   Each 5-byte compare becomes `E9 -> cave`.  The cave sets ZF exactly as the
   compare would for levels 0/1/2 and ADDITIONALLY sets ZF for level 3 (the
   Firmament), then
   jumps back to the je/jne that follows.  `pop` does not touch flags, which is
   what makes the save/restore of EAX free:
       push eax
       movzx eax, byte [esp+6]     ; +2 for the local, +4 for the push
       cmp  eax, 3
       jne  .l                     ; level 3 -> force EAX 0 so the test sets ZF
       xor  eax, eax
     .l: test eax, eax             ; ZF = (level == 0 or level == 3)
       pop  eax
       jmp  <the je/jne>
   ⚠ build_vision9.py owns 0x55780F12 in this same function (the `add esi,3`
   ceiling site).  Different bytes, no overlap -- but do not let the two scripts'
   verify ranges drift into each other.

D. THE GLOBAL-TARGET SPELL GATE -- hook @0x5579E78B -> cave_spellgate
   GlobalTargetSpells.TGlobalTargetSpell.CanActivate @0x5579E73C, live:
     5579E786  call TAbstractUnit.GetLocation   ; [ebp-7] = level
     5579E78B  80 7D F9 00     cmp byte [ebp-7], 0
     5579E78F  74 25           je  0x5579E7B6   ; surface -> allowed
     5579E791  xor ebx, ebx                     ; underground -> refuse +
     5579E793  ...             LoadResString CannotCastSpellInUndergound...
   The compare is the disp8 form (FOUR bytes), so the hook takes cmp+je = 6
   bytes: E9 rel32 + one 0x90.  The cave computes the same
   surface-or-Firmament predicate and jumps to 0x5579E7B6 (allow) or
   0x5579E791 (refuse) itself.
   ⚠ The reloc'd `mov eax,[0x558E8FE4]` at 0x5579E796 is well clear of the
   displaced range; the range itself carries no .reloc entry (checked).

E. TCave.PlaceHX GUARD -- hook @0x557B36BB -> cave_placeguard
   Cave.TCave.PlaceHX @0x557B3670 pairs a cave with a twin on the neighbouring
   level.  [esi+0x30] is the polarity flag: 1 = upper mouth, twin at level+1;
   0 = lower mouth, twin at level-1.
     557B36B1  cmp byte [esi+0x30], 1
     557B36B5  jne 0x557B373D                 ; the flag-0 (twin at level-1) arm
     557B36BB  0F BE 45 08     movsx eax, byte [ebp+8]   ; [ebp+8] = the level
     557B36BF  40              inc eax                   ; twin at level+1
     557B36C0  50              push eax  ; -> GetField(map, x, y, level+1)
   With four levels, a flag-1 cave placed on level 2 would now SUCCEED in
   digging its twin into the Firmament.  v1/v2's guard blocked level >= 2
   outright (`cmp eax,2 / jge .block / inc eax`).  v3 rewrites the block IN
   PLACE, same VA, same hook bytes, to ask section G's order instead:
       movsx eax, byte [ebp+8]
       mov   dl, 1                       ; DOWN
       mov   ecx, [ebp-4]                ; the TMapContainer (count at +0x14)
       call  twin_place                  ; -> the level below, or -1
       test  eax, eax
       js    .block
       jmp   0x557B36C0
     .block:
       xor   ebx, ebx
       jmp   0x557B37BA        ; mov eax,ebx / pop esi / pop ebx / leave / ret 8
   0x557B37BA is the function's single epilogue and returns EBX, so EBX=0 is
   "placement failed" -- byte-identical in shape to the engine's OWN failure
   return at 0x557B372F.  Nothing is half-created: the guard fires BEFORE the
   twin is allocated.  v3's block is 30 B and must stay <= 32 (stormcast
   starts at 0x558440A0); build() asserts it.

   ⚠ DEVIATION FROM THE SPEC, and the reason.  The spec proposed bailing to
   0x557B373D (the flag-0 arm).  That is not a bail-out, it is the MIRROR arm,
   and the two arms are not interchangeable: each one's "twin already exists"
   branch asserts the OPPOSITE polarity on the twin it finds
   (flag-1 arm 0x557B371A `cmp [twin+0x30],0 / sete bl`; flag-0 arm 0x557B379C
   `cmp [twin+0x30],1 / sete bl`).  Sending a flag-1 object down the flag-0 arm
   makes it create a twin at level-1 that ALSO carries flag 1; that twin's own
   PlaceHX (VMT slot +0x118) then finds the original, sees the wrong polarity,
   `sete bl` -> 0, and DESTROYS it via [vmt-4].  A guard that destroys the cave
   it was protecting is worse than the bug.  Hence the clean failure return.

F. STORM SPELLS + BIRD'S VIEW -- v2, three more gates (2026-09-06 ruling)
   All three are the SAME instruction pair as section D, in the SAME operand
   form (`80 7D F9 00` -- byte [ebp-7], filled by a
   TAbstractUnit.GetLocation(EAX=unit, EDX=&x, ECX=&y, [esp]=&level) call a few
   instructions earlier), so each takes a 6-byte E9+0x90 hook and its own stub.
   The stubs cannot be shared with cave_spellgate: the predicate is identical
   but the two branch targets differ per site, and they are baked as rel32
   tails.  Live bytes read with dasm.py 2026-09-06; all three ranges carry no
   .reloc entry (63883-entry scan, none within +/-3 bytes).

     site                                        displaced      allow / deny
     Storms.TStormSpell.CanActivate
       @0x557CDCC8   80 7D F9 00 74 25           cmp+je 6 B     0x557CDCF3 /
                                                                0x557CDCCE
     Storms.TStormSpell.AICastSpellPriority
       @0x557CDF88   80 7D F9 00 75 66           cmp+jne 6 B    0x557CDF8E /
                                                                0x557CDFF4
     GlobalSpells.TBirdsView.CanActivate
       @0x557EAB90   80 7D F9 00 74 25           cmp+je 6 B     0x557EABBB /
                                                                0x557EAB96

   ⚠ The AI site's polarity is INVERTED (jne, not je): "underground" is the
   JUMP there, and the target 0x557CDF8E is simply the fall-through address.
   Its deny target 0x557CDFF4 is the finally-epilogue, entered with EDI = -1
   from `or edi,0xFFFFFFFF` @0x557CDF74 -- i.e. the engine's own "no priority"
   return.  Jumping to 0x557CDFF1 instead would re-execute that `or` harmlessly
   but is one byte further from the shape the vanilla code uses; the stub uses
   0x557CDFF4 so the deny path is byte-for-byte the vanilla one.
   ⚠ Both CanActivate sites' allow target skips a `xor ebx,ebx` as well as the
   CannotCastSpellInUndergound message -- EBX is the return value, so falling
   through would refuse the cast AND leave the message set.  The stubs jump to
   the je target, never to the compare's fall-through.

G. THE ABYSS -- v3 (2026-09-27): cave links follow the level ORDER, not +/- 1
   A TCave is one mouth of a two-mouth pair.  [cave+0x30] is its polarity:
   1 = upper mouth (the other end is BELOW), 0 = lower mouth (ABOVE), 2 while
   Destroy runs.  Vanilla computes the other end as level+1 / level-1 at twelve
   sites, all inside the Cave unit (0x557B3424..0x557B3F74); a byte-pattern
   sweep for the TCave ClassID 0x2037E and a capstone sweep of every GetField /
   GetMapLevel caller for inc/dec found no cave arithmetic anywhere else, and
   AoWz.exe imports only TCave.CanEnter / Enter.  All twelve now ask one helper:

     twin_strict(eax=level, dl=dir) -> eax     dir != 0 = DOWN, 0 = UP
         DOWN  0->1  1->2  2->4          else -1
         UP    1->0  2->1  4->2          else -1
     twin_place (+ ecx = TMapContainer)  also -1 when the result >= [ecx+0x14]
     twin_safe                           as strict, but -1 -> the INPUT level

   (v3's table; v4 and v5 widened it -- sections H and I.)  Placement asks
   twin_place (refuse cleanly); the run-time sites ask twin_safe, so a cave no
   placement path can create (hand-edited map, third-party generator) resolves
   to its own hex instead of vanilla's unchecked GetField(-1) / GetField(count),
   which reads past the level list.  At the run-time sites the pair already
   exists, so the level count needs no second check there.

     site                                    VA          B   dir      helper
     TCave.CanPlace       level+1 < count    0x557B3652  15  by flag  twin_place
     TCave.PlaceHX        GetField (down)    0x557B36BB   5  DOWN     twin_place (E)
     TCave.PlaceHX        twin.PlaceHX lvl   0x557B36FD   5  DOWN     twin_strict
     TCave.PlaceHX        GetField (up)      0x557B373D   5  UP       twin_place
     TCave.PlaceHX        twin.PlaceHX lvl   0x557B377F   5  UP       twin_strict
     TCave.Destroy        flag-0 arm         0x557B3494   5  UP       twin_safe
     TCave.Destroy        flag-1 arm         0x557B34D4   5  DOWN     twin_safe
     TCave.MoveExclusive  flag-1 arm         0x557B3810   5  DOWN     twin_safe
     TCave.MoveExclusive  flag-0 arm         0x557B3832   5  UP       twin_safe
     TCave.EnterMovePoints  both arms        0x557B38D6  30  by flag  twin_safe
     TCave.CanEnterSelection both arms       0x557B393C  30  by flag  twin_safe
     TCave.EnterEx        both arms          0x557B3A8E  33  by flag  twin_safe
     TCave.ArmyPlaced     both arms          0x557B3E3C  34  by flag  twin_safe

   MoveExclusive is the PATHFINDER's vertical link (TCave.UpdateMapField sets
   the field's exclusive-move bit 0x8000; TMoveControl calls the VMT slot), so
   AI routing through the Abyss comes from the same helper as the player's own
   EnterEx move -- which is what keeps build_fly_levels.py's ValidPath re-run
   agreeing with a cave path.

   CanPlace was `if (level+1 >= count && flag != 0) refuse`: flag-0 caves were
   never checked.  Now BOTH polarities must have a twin level inside the map.
   That only refuses what vanilla would have mis-built (a lower mouth on the
   top level), and a twin's own PlaceHX -> CanPlace always passes, because a
   flag-0 twin sits exactly one step below a valid flag-1 cave.

   "by flag" = `cmp byte [cave+0x30],1 / sete dl` -- flag 1 DOWN, anything else
   UP, exactly vanilla's `== 1 ? +1 : -1`.  EnterEx is the exception: vanilla
   there leaves the target at 0 for a flag >= 2, and the stub keeps that.
   The five 30..34-byte sites re-issue vanilla's own GetLevel virtual call
   (`call [vmt+0x7C]`, register-indirect) so both arms collapse into one.

   Level tests that needed NO change for index 4 (all read live 2026-09-27):
     vision halving / Night Vision   vis1/vis2  `level == 0 or 3`   -> halved
     global / storm / Bird's View    D + F      `level == 0 or 3`   -> refused
     fill                            B          `level == 3 ? Sky`  -> EarthWall
     +3 Firmament sight              build_firmament_vision.py `== 3` -> none
     ranged malus                    build_firmament_rangedmalus.py parity:
                                     4 = 0b100, odd -> malus applies
     earth / air elemental heal      build_waterheal.py v6  `!= 0 and != 3` /
                                     `== 0 or 3`   -> earth heals, air does not
     fly between levels              build_fly_levels.py UP_T/DN_T already
                                     carry the Abyss row (up 4->2, down 2->4)
     Raise Terrain underground arm   `level != 0` -> underground
   Needed a change ELSEWHERE: build_townquake_retune.py (tested "level 1 or 2"),
   build_shipyard_income.py (MAX_LEVELS), build_skylevel_ui.py and
   build_deved_levelnav.py (5-entry display order + the palette flip).

H. DISABLED LEVELS -- v4 (2026-09-27, owner request): a per-map mask
   A map can leave out any level but Surface.  Because a level's identity IS
   its index, a left-out level below the highest one is kept as a DISABLED
   placeholder: present in the file, blank, hidden, and skipped by every link.
     * TAoWHSMap (a leaf class in every module) grows 0x41C -> 0x420; the
       byte at +0x41C is the mask, bit L set = level L disabled.
     * TAoWHSMap.ReadWrite's `call THSMap.ReadWrite` @0x55776E50 is retargeted
       to cave_rw, which streams the byte as property id 0x60 (the class chain
       uses 2..6, 7, 0xB..0x3F) and tail-jumps to the original.  It runs BEFORE
       the levels and objects load, so no cave code sees a stale mask.  An old
       map has no id 0x60 and rwByte zeroes the byte: all levels enabled.
     * twin_strict (0x55844100) is now a trampoline to strict4, which walks
       CAVE_CHAIN (0, 1, 2, 4) from the level's position and skips any level
       that is disabled or missing (>= the level count).  Caverns off => a
       Surface cave pairs with Depths.  No map (global nil) => nothing skipped.
       strict4 reads the map global through the anchor's load delta.
   The mask is written only by the editor (build_levelset.py).  Flying skips
   disabled levels the same way (build_fly_levels.py fly_next).  Verified live
   in AoWzEd.exe 2026-09-27: popup edits, save as id 0x60 = 08, reload reads 08.

I. FIRMAMENT <-> SURFACE CAVES -- v5 (2026-09-30, owner request)
   The chain becomes (3, 0, 1, 2, 4).  strict4 (116 B) is followed directly by
   cave_rw, whose VA the ReadWrite call site holds, so the one-byte-longer chain
   cannot be rewritten in place: v5 appends strict5 (the same source, the new
   chain) after cave_rw, repoints the twin_strict trampoline at it and zeroes
   strict4's 116 bytes.  No hook site changes.
   Checked statically, nothing else needed:
     * Art is chosen by polarity, not level: TCave.GetTerrainTypeImage
       @0x557B361C returns the image index for flag 1 and index+0x1E for flag 0.
     * No cave arithmetic outside the Cave unit, no level-named text in the
       entry prompt (TCave.EnterEx), AoWz.exe imports only CanEnter / Enter.
     * Placement re-terrains the footprint: TILTerrainMO.CanPlace (HSEPack
       0x55618A04) sets the structure's terrain through THSMap.CanChangeTerrain,
       which checks the hex's objects and no level.  The cave has no Sky art, so
       a mouth on Sky falls back on TStructure.ForceTerrainType @0x5575E93C:
       Grass on the Firmament since build_firmament_structart.py (Dirt before).
       The mouth hex is never Sky, so build_fly_levels.py's cave_mv drain (127
       for a vertical move touching Sky or Chasm) does not fire.
   A walker that climbs to the Firmament can stand on the mouth hex but cannot
   leave it onto Sky; the map maker paints land around the mouth if walkers
   are meant to use it.
   ⚠ Disabling the Firmament (build_levelset.py) with caves on it: the Surface
   mouths resolve to their own hex (twin_safe), as for any orphaned cave.

================================================================================
LEFT ALONE ON PURPOSE -- these keep reading `level != 0` as "underground"
================================================================================
  Path of Life / Path of Decay   0x557801A4 / 0x557801C4
  Raise Terrain's underground arm, the terrain-change and road gates
  Air- and Earth-elemental healing  build_waterheal.py cave 0x55824000
  TCombatUnit.GetVisibilityRange 0x55724AD0 -- NOT level-derived at all; it
    halves on `cmp byte [combat+0x40], 1`, and [TCombat+0x40] is the combat KIND
    (1 = exploration-site interior, written at TExplorationSite.SetupCombat
    0x557C1A17; 2 = default armies, TCombat.InitDefaultArmies 0x55727BF5), read
    the same way by TAoWHSMap.DestroyCombat 0x5577894D.  A Firmament field
    battle is kind 2 and already gets full tactical vision.  No patch needed.

NOT in the list above, because its gate no longer reads anything:
  TTowerConstructionControl.CanConstruct 0x557C38D4 -- `cmp byte [ebp-3],0` at
    0x557C390D is followed by `90 90` where the pristine DLL has `jne
    0x557C3922`, so towers build on EVERY level, Firmament included.  An
    undocumented pre-convention live edit; no build script owns those two bytes.

⚠ FORWARD HAZARD -- build_waterheal.py cave 0x55824000 and this script both
  encode the level-3 predicate.  Re-applying an OLD revision of waterheal alone
  reverts the Earth-elemental Firmament skip (v5) and the Air-elemental
  Firmament heal (v6) without touching anything here, and nothing in this
  script will notice.

================================================================================
CAVE 0x55844000..0x558443FF
================================================================================
Verified all-zero on disk (0x55843E00..0x558445FF is clear) and unclaimed:
the nearest neighbours in build_scripts/ are 0x55843000 and 0x55846000.
CODE section, so file offset = VA - 0x55700C00.

POSITION INDEPENDENCE: mandatory (AoWEPACK.dpl never loads at its preferred
base).  This cave needs NO globals at all -- every block is register/stack-only
plus rel32 jumps back into the module, so there is not one absolute memory
operand and no call/pop anchor is required.  Asserted at build time by scanning
the capstone listing of every block for a `0x55......` memory operand.

RE-TUNE IN PLACE (project convention -- never revert-and-reapply).  Every
version APPENDS: v2's three stubs follow the five v1 blocks (16-aligned), v3's
three helpers and twelve stubs start at 0x55844100 (4-aligned).  So every v1/v2
hook still points at the same address and keeps the same bytes.  The two
v3 changes inside older territory are the cap byte (04 -> 05) and the
placeguard block, rewritten at its own VA.

    0x55844000  fillterr    0x55844060  spellgate    0x558440C0  stormai
    0x55844020  vis1        0x55844080  placeguard   0x558440E0  birdsview
    0x55844040  vis2        0x558440A0  stormcast    0x55844100  v3 helpers,
                                                                 then 12 stubs
    0x55844274  (strict4, v4; zeroed in v5)    0x558442E8  cave_rw (v4)
    0x55844308  strict5 (v5), ends 0x5584437C

--apply accepts orig, v1, v2, v3 or v4 (each recognised exactly: its site bytes
plus cave == that version's regenerated payload, zero beyond it) and writes v5.
A no-arg run over an older version reports "NEEDS RE-TUNE", never "applied".
--undo restores all 23 sites and zeroes the whole v5 length.

Usage:
  no args   dry run: verify + report the state of all 21 sites; also runs the
            helper model (a small interpreter executes the assembled helpers
            against the Python order table for levels -2..7, both directions)
  --apply   patch (verify-before-write; backup only from proven-vanilla;
            in-place rewrite from an installed v1 or v2)
  --undo    surgical: cap byte -> 03, restore all 20 hook sites, zero the
            emitted cave.  No backup touched.
  --dis / --show   capstone-disassemble every block and every hook, exit
"""
import os
import re
import struct
import sys
import shutil

sys.dont_write_bytecode = True
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

import zigexe

# game dir = two levels up from this script; AOW_GAME_DIR overrides.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-maplevel4")

# ⚠ "this feature's sites are original" is NOT proof the FILE is unpatched --
# after --undo it is exactly the state this script itself just produced, over a
# DLL carrying every other feature.  A snapshot minted there would sit on disk
# looking authoritative while holding a patched image.  So gate the backup on a
# positive byte-compare against the pristine reference instead.
PRISTINE = os.path.join(GAME, "Modding Resources", "AoWEPACK_original_backup.dpl")


def proven_pristine():
    """True only if the live DLL is byte-identical to the pristine reference."""
    try:
        with open(PRISTINE, "rb") as f:
            ref = f.read()
    except OSError:
        return False
    with open(DLL, "rb") as f:
        return f.read() == ref


ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

DLL_BASE = 0x55700000

SKY_LEVEL = 3          # the Firmament level index (user ruling)
ABYSS_LEVEL = 4        # the Abyss level index (v3, owner request 2026-09-27)
SKY_TERRAIN = 0x0E     # build_chasm_sky_movement.py: 0x0E = SKY, 0x0B = CHASM
WALL_TERRAIN = 0x07    # EarthWall -- what every non-surface level fills with

# The cave neighbours of each level (section G).  A level missing from a map
# has no neighbour; twin_strict implements exactly these two tables and
# model_check() executes the assembled helper against them.
CAVE_DOWN = {0: 1, 1: 2, 2: ABYSS_LEVEL}
CAVE_UP = {1: 0, 2: 1, ABYSS_LEVEL: 2}

# ---- A. the cap byte --------------------------------------------------------
CAP_VA = 0x5577768B                                # cmp dword [esi+0x14], N
CAP_ORIG = bytes.fromhex("837E1403")
CAP_V12 = bytes.fromhex("837E1404")                # v1 / v2: four levels
CAP_V3 = bytes.fromhex("837E1405")                 # v3: five levels
CAP_IMM_VA = 0x5577768E                            # the imm8 itself (file 0x76A8E)

# ---- B..E. the five v1 hook sites -------------------------------------------
FILL_HOOK = 0x5577747E
FILL_ORIG = bytes.fromhex("506A078BCE")            # push eax; push 7; mov ecx,esi
FILL_CONT = 0x55777483

VIS1_HOOK = 0x55780F32
VIS1_ORIG = bytes.fromhex("807C240200")            # cmp byte [esp+2], 0
VIS1_CONT = 0x55780F37                             # the je

VIS2_HOOK = 0x55780F4C
VIS2_ORIG = bytes.fromhex("807C240200")
VIS2_CONT = 0x55780F51                             # the jne

SPELL_HOOK = 0x5579E78B
SPELL_ORIG = bytes.fromhex("807DF9007425")         # cmp byte [ebp-7],0 ; je +0x25
SPELL_ALLOW = 0x5579E7B6                           # the je target: allowed
SPELL_DENY = 0x5579E791                            # fall-through: refuse + message

PLACE_HOOK = 0x557B36BB
PLACE_ORIG = bytes.fromhex("0FBE450840")           # movsx eax,[ebp+8] ; inc eax
PLACE_CONT = 0x557B36C0                            # push eax
PLACE_FAIL = 0x557B37BA                            # mov eax,ebx / epilogue / ret 8
PLACE_MAXLEVEL = 2                                 # v1/v2 only: level >= 2 -> no twin

# ---- F. v2 (2026-09-06): storm spells + Bird's View -------------------------
# All three are `cmp byte [ebp-7],0` + a 2-byte conditional jump = 6 displaced
# bytes, exactly like SPELL_HOOK.  ALLOW / DENY are absolute VAs the stub jumps
# to itself, so each site needs its own stub even though the predicate is shared.
STORM_HOOK = 0x557CDCC8                            # Storms.TStormSpell.CanActivate
STORM_ORIG = bytes.fromhex("807DF9007425")         # cmp byte [ebp-7],0 ; je +0x25
STORM_ALLOW = 0x557CDCF3
STORM_DENY = 0x557CDCCE

STORMAI_HOOK = 0x557CDF88                    # Storms.TStormSpell.AICastSpellPriority
STORMAI_ORIG = bytes.fromhex("807DF9007566")       # cmp byte [ebp-7],0 ; jne +0x66
STORMAI_ALLOW = 0x557CDF8E                         # fall-through (INVERTED polarity)
STORMAI_DENY = 0x557CDFF4                          # epilogue with EDI = -1

BIRD_HOOK = 0x557EAB90                       # GlobalSpells.TBirdsView.CanActivate
BIRD_ORIG = bytes.fromhex("807DF9007425")          # cmp byte [ebp-7],0 ; je +0x25
BIRD_ALLOW = 0x557EABBB
BIRD_DENY = 0x557EAB96

# ---- G. v3 (2026-09-27): the Abyss -- cave links follow the level order ------
# Every original byte-run below was read LIVE with dasm.py and byte-compared
# against the vanilla root DLL (identical) on 2026-09-27.
CAVE_UNIT = (0x557B3424, 0x557B3F74)               # Cave unit: TCave.Create .. Finalization

CANPLACE_HOOK = 0x557B3652                         # TCave.CanPlace, after TStructure.CanPlace
CANPLACE_ORIG = bytes.fromhex("0FBEC3403B46147C0A807F30007404")
CANPLACE_FAIL = 0x557B3661                         # xor eax,eax / epilogue
CANPLACE_OK = 0x557B3665                           # mov al,1 / epilogue

PTWIN_DN_HOOK = 0x557B36FD                         # mov al,[ebp+8] / inc eax / push eax
PTWIN_DN_ORIG = bytes.fromhex("8A45084050")
PTWIN_DN_CONT = 0x557B3702

PUP_HOOK = 0x557B373D                              # movsx eax,[ebp+8] / dec eax (flag-0 arm)
PUP_ORIG = bytes.fromhex("0FBE450848")
PUP_CONT = 0x557B3742                              # push eax -> GetField

PTWIN_UP_HOOK = 0x557B377F                         # mov al,[ebp+8] / dec eax / push eax
PTWIN_UP_ORIG = bytes.fromhex("8A45084850")
PTWIN_UP_CONT = 0x557B3784

DESTROY_UP_HOOK = 0x557B3494                       # movsx eax,[eax+0x12] / dec eax
DESTROY_UP_ORIG = bytes.fromhex("0FBE401248")
DESTROY_UP_CONT = 0x557B3499
DESTROY_DN_HOOK = 0x557B34D4                       # movsx eax,[eax+0x12] / inc eax
DESTROY_DN_ORIG = bytes.fromhex("0FBE401240")
DESTROY_DN_CONT = 0x557B34D9

MOVEX_DN_HOOK = 0x557B3810                         # TCave.MoveExclusive, flag 1
MOVEX_DN_ORIG = bytes.fromhex("0FBE401240")
MOVEX_DN_CONT = 0x557B3815
MOVEX_UP_HOOK = 0x557B3832                         # TCave.MoveExclusive, flag 0
MOVEX_UP_ORIG = bytes.fromhex("0FBE401248")
MOVEX_UP_CONT = 0x557B3837

# the four "both arms" sites: cmp flag / jne / GetLevel / +1 / jmp / GetLevel / -1
ENTERMP_HOOK = 0x557B38D6                          # TCave.EnterMovePoints, EBP = cave
ENTERMP_ORIG = bytes.fromhex(
    "807D3001750D8BC58B10FF527C0FBEF046EB0B8BC58B10FF527C0FBEF04E")
ENTERMP_CONT = 0x557B38F4                          # push esi
CANSEL_HOOK = 0x557B393C                           # TCave.CanEnterSelection, EBX = cave
CANSEL_ORIG = bytes.fromhex(
    "807B3001750D8BC38B10FF527C0FBEF046EB0B8BC38B10FF527C0FBEF04E")
CANSEL_CONT = 0x557B395A                           # push esi
ENTEREX_HOOK = 0x557B3A8E                          # TCave.EnterEx, EBX = cave, [ebp-9] = target
ENTEREX_ORIG = bytes.fromhex(
    "8A43302C01720F75188BC38B10FF527C408845F7EB0B8BC38B10FF527C488845F7")
ENTEREX_CONT = 0x557B3AAF                          # mov al,[ebp-9]
ARMYPL_HOOK = 0x557B3E3C                           # TCave.ArmyPlaced, ESI = cave
ARMYPL_ORIG = bytes.fromhex(
    "807E3001750F8BC68B10FF527C0FBEC0408BF0EB0D8BC68B10FF527C0FBEC0488BF0")
ARMYPL_CONT = 0x557B3E5E                           # mov edi,[ebx+0x1c]

CAVE = 0x55844000
CAVE_LIMIT = 0x400
CAVE_ZERO_END = 0x55844600                         # verified all-zero to here
V3_BASE = 0x55844100                               # v3's helpers + stubs start here

# ---- H. v4 (2026-09-27): a per-map DISABLED-levels mask ----------------------
# TAoWHSMap is a leaf class (no subclass in any module), so its instance grows
# 0x41C -> 0x420 and the mask byte lives at +0x41C.  Bit L set = level L is a
# disabled placeholder.  Saved as property id 0x60 (the chain THSMap/TAoWHSMap
# uses 2..6, 7, 0xB..0x3F; TEObject.ReadWrite writes nothing).  An old map has
# no id 0x60, rwByte zeroes the byte, so every old map reads "all enabled".
MAP_VMT = 0x5570E874                               # AoWE..TAoWHSMap
INST_VA = MAP_VMT - 0x1C                           # InstanceSize
INST_ORIG = struct.pack("<I", 0x41C)
INST_V4 = struct.pack("<I", 0x420)
MASK_OFF = 0x41C
MASK_ID = 0x60
RWCALL_VA = 0x55776E50                             # TAoWHSMap.ReadWrite: call THSMap.ReadWrite
RWCALL_TARGET = 0x557025AC                         # the HSEPack import thunk
MAPGLOBAL = 0x558FA040                             # AoWE.AoWHSMap (the map object)
CAVE_CHAIN_V4 = (0, 1, 2, ABYSS_LEVEL)             # v4's chain -- recognition only
# ---- I. v5 (2026-09-30): the Firmament joins the chain at the top ------------
CAVE_CHAIN = (SKY_LEVEL, 0, 1, 2, ABYSS_LEVEL)     # the cave chain, top to bottom
CHAINS = {"strict4": CAVE_CHAIN_V4, "strict5": CAVE_CHAIN}
CHAIN_AT = 9                                       # 4 pushes + the 5-byte call


def strip_chain(name, code):
    """A strict block with its inline chain data NOP'd, so capstone reads code only."""
    if name not in CHAINS:
        return code
    n = len(CHAINS[name])
    return code[:CHAIN_AT] + b"\x90" * n + code[CHAIN_AT + n:]


# ---- cave source: v1 --------------------------------------------------------
def src_fillterr():
    return f"""
    push eax                              // param5 = level (AL is already it)
    movzx ecx, al                         // ECX is dead: `mov ecx,esi` follows
    cmp  ecx, {SKY_LEVEL}
    je   _sky
    push {WALL_TERRAIN}                   // param6 = terrain: EarthWall
    jmp  _cont
_sky:
    push {SKY_TERRAIN}                    // param6 = terrain: Sky
_cont:
    mov  ecx, esi                         // displaced tail
    jmp  {FILL_CONT:#x}
"""


def src_issurf(cont_va):
    """ZF := (level == 0 or level == SKY_LEVEL), level byte at [esp+2] pre-push."""
    return f"""
    push eax
    movzx eax, byte ptr [esp+6]           // +2 local, +4 for the push above
    cmp  eax, {SKY_LEVEL}
    jne  _t
    xor  eax, eax                         // Sky: make the test below set ZF
_t:
    test eax, eax
    pop  eax                              // pop does not touch flags
    jmp  {cont_va:#x}
"""


def src_spellgate(allow_va=None, deny_va=None):
    """`byte [ebp-7]` level gate: allow on surface (0) or the Firmament (3).

    Shared by the four "cannot cast underground" sites -- they differ only in
    where allow/deny go, and those are rel32 tails, so each needs its own copy.
    Default arguments reproduce the v1 global-target-spell stub BYTE FOR BYTE
    (its recognition depends on that; do not change the body)."""
    allow_va = SPELL_ALLOW if allow_va is None else allow_va
    deny_va = SPELL_DENY if deny_va is None else deny_va
    return f"""
    push eax
    movzx eax, byte ptr [ebp-7]           // frame-based: no esp adjustment
    cmp  eax, {SKY_LEVEL}
    jne  _t
    xor  eax, eax
_t:
    test eax, eax
    pop  eax
    je   {allow_va:#x}                    // surface or Firmament -> allowed
    jmp  {deny_va:#x}                     // underground -> refuse + message
"""


def src_placeguard_v1():
    """FROZEN -- v1/v2's guard, kept only to recognise an installed v1 or v2."""
    return f"""
    movsx eax, byte ptr [ebp+8]           // displaced: the level parameter
    cmp   eax, {PLACE_MAXLEVEL}
    jge   _block                          // level+1 would be Sky (or off-map)
    inc   eax                             // displaced: twin one level down
    jmp   {PLACE_CONT:#x}
_block:
    xor   ebx, ebx                        // EBX is the return value
    jmp   {PLACE_FAIL:#x}                 // the function's own epilogue
"""


# ---- cave source: v3 --------------------------------------------------------
SRC_TWIN_STRICT = f"""
    test dl, dl                           // dl != 0: DOWN (upper mouth, flag 1)
    je   _up
    cmp  eax, 2
    je   _abyss                           // Depths -> Abyss
    cmp  eax, 1
    ja   _none                            // unsigned: Firmament, Abyss, negatives
    inc  eax                              // Surface -> Caverns, Caverns -> Depths
    ret
_abyss:
    add  eax, {ABYSS_LEVEL - 2}
    ret
_up:
    cmp  eax, {ABYSS_LEVEL}
    je   _depths                          // Abyss -> Depths
    dec  eax                              // Caverns -> Surface, Depths -> Caverns
    cmp  eax, 1
    jbe  _ret                             // unsigned: only 1 and 2 had a level above
_none:
    or   eax, -1
_ret:
    ret
_depths:
    sub  eax, {ABYSS_LEVEL - 2}
    ret
"""


def src_twin_place(strict):
    """twin_strict, then -1 unless the result is below [ecx+0x14] (the level count)."""
    return f"""
    call {strict:#x}
    test eax, eax
    js   _r
    cmp  eax, dword ptr [ecx+0x14]
    jl   _r
    or   eax, -1
_r:
    ret
"""


def src_twin_safe(strict):
    """twin_strict, but "no neighbour" returns the INPUT level -- never an index
    outside the map for GetField / GetMapLevel to read past."""
    return f"""
    push ecx
    mov  ecx, eax
    call {strict:#x}
    test eax, eax
    jns  _ok
    mov  eax, ecx
_ok:
    pop  ecx
    ret
"""


def src_placeguard_v3(place):
    return f"""
    movsx eax, byte ptr [ebp+8]           // the level parameter
    mov   dl, 1                           // DOWN: flag-1 arm
    mov   ecx, dword ptr [ebp-4]          // the TMapContainer
    call  {place:#x}
    test  eax, eax
    js    _block
    jmp   {PLACE_CONT:#x}                 // push eax -> GetField(.., level below)
_block:
    xor   ebx, ebx                        // EBX is the return value
    jmp   {PLACE_FAIL:#x}                 // the function's own epilogue
"""


def src_canplace(place):
    """BL = level, ESI = TMapContainer, EDI = the cave; TStructure.CanPlace said yes."""
    return f"""
    movsx eax, bl
    cmp   byte ptr [edi+0x30], 1
    sete  dl                              // flag 1 -> DOWN, anything else -> UP
    mov   ecx, esi
    call  {place:#x}
    test  eax, eax
    js    {CANPLACE_FAIL:#x}
    jmp   {CANPLACE_OK:#x}
"""


def src_ptwin(strict, down, cont):
    """The twin's own PlaceHX level parameter -- the same level GetField got."""
    return f"""
    movsx eax, byte ptr [ebp+8]
    {"mov dl, 1" if down else "xor edx, edx"}
    call  {strict:#x}
    push  eax
    jmp   {cont:#x}
"""


def src_pguard_up(place):
    """Flag-0 arm of PlaceHX: the level above, or a clean failure return."""
    return f"""
    movsx eax, byte ptr [ebp+8]
    xor   edx, edx                        // UP
    mov   ecx, dword ptr [ebp-4]
    call  {place:#x}
    test  eax, eax
    js    _block
    jmp   {PUP_CONT:#x}
_block:
    xor   ebx, ebx
    jmp   {PLACE_FAIL:#x}
"""


def src_field_arm(safe, down, cont):
    """EAX = the cave's TMapField; its level byte is +0x12."""
    return f"""
    movsx eax, byte ptr [eax+0x12]
    {"mov dl, 1" if down else "xor edx, edx"}
    call  {safe:#x}
    jmp   {cont:#x}
"""


def src_byflag(safe, obj, out, cont):
    """Both arms of `flag == 1 ? GetLevel+1 : GetLevel-1` in one."""
    return f"""
    mov   eax, {obj}
    mov   edx, dword ptr [eax]
    call  dword ptr [edx+0x7c]            // GetLevel
    movsx eax, al
    cmp   byte ptr [{obj}+0x30], 1
    sete  dl
    call  {safe:#x}
    mov   {out}, eax
    jmp   {cont:#x}
"""


def src_enterex(safe):
    """EnterEx leaves [ebp-9] at 0 for a flag >= 2; keep that."""
    return f"""
    cmp   byte ptr [ebx+0x30], 1
    ja    _keep
    mov   eax, ebx
    mov   edx, dword ptr [eax]
    call  dword ptr [edx+0x7c]            // GetLevel
    movsx eax, al
    mov   dl, byte ptr [ebx+0x30]         // 1 DOWN, 0 UP
    call  {safe:#x}
    mov   byte ptr [ebp-9], al
_keep:
    jmp   {ENTEREX_CONT:#x}
"""


# ---- cave source: v4 --------------------------------------------------------
def src_strict(va, chain_levels):
    """twin_strict, v4/v5: walk the chain from the level's position, skipping any
    level that is disabled in the map's mask or missing (>= the level count).
    EAX = level, DL != 0 DOWN -> EAX = the level, or -1.  Preserves all but EAX.
    The chain is inline data straddled by `call`, so the pop yields its run-time
    address and, minus its link VA, the load delta for the map global.
    v4 (strict4) and v5 (strict5) differ only in the chain."""
    chain_va = va + CHAIN_AT
    chain = ", ".join(str(c) for c in chain_levels)
    n = len(chain_levels)
    return f"""
    push ebx
    push ecx
    push esi
    push edi
    call _c
    .byte {chain}
_c:
    pop  esi                              // esi = the chain, at run time
    mov  edi, esi
    sub  edi, {chain_va:#x}               // the load delta
    mov  edi, dword ptr [edi + {MAPGLOBAL:#x}]
    xor  ebx, ebx                         // no map: nothing disabled ...
    mov  ecx, 0x7f                        // ... and nothing missing (= v3)
    test edi, edi
    je   _go
    movzx ebx, byte ptr [edi + {MASK_OFF:#x}]
    mov  edi, dword ptr [edi + 0x10]      // TMapContainer
    test edi, edi
    je   _go
    mov  ecx, dword ptr [edi + 0x14]      // level count
_go:
    cmp  eax, 0xff
    ja   _none                            // unsigned: negatives too
    xor  edi, edi
_find:
    cmp  byte ptr [esi + edi], al
    je   _step
    inc  edi
    cmp  edi, {n}
    jb   _find
    jmp  _none                            // not in the chain
_step:
    test dl, dl
    je   _up
    inc  edi
    cmp  edi, {n}
    jae  _none
    jmp  _test
_up:
    dec  edi
    js   _none
_test:
    movzx eax, byte ptr [esi + edi]
    cmp  eax, ecx
    jae  _step                            // missing: keep walking
    bt   ebx, eax
    jb   _step                            // disabled: keep walking
    jmp  _ret
_none:
    or   eax, -1
_ret:
    pop  edi
    pop  esi
    pop  ecx
    pop  ebx
    ret
"""


def src_cave_rw():
    """Retarget of TAoWHSMap.ReadWrite's `call THSMap.ReadWrite`: stream the
    mask first (so it is in place before any level or object loads), then
    tail-jump to the original call target.  EAX = map, EDX = stream."""
    return f"""
    push eax
    push edx
    push esi
    mov  ecx, {MASK_ID:#x}
    lea  edx, [eax + {MASK_OFF:#x}]
    mov  eax, dword ptr [esp + 4]         // the stream
    mov  esi, dword ptr [eax]
    call dword ptr [esi + 0x30]           // rwByte(stream, &mask, id)
    pop  esi
    pop  edx
    pop  eax
    jmp  {RWCALL_TARGET:#x}
"""


V1_BLOCKS = ["fillterr", "vis1", "vis2", "spellgate", "placeguard"]
V2_BLOCKS = ["stormcast", "stormai", "birdsview"]
V3_HELPERS = ["twin_strict", "twin_place", "twin_safe"]


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build(version):
    """Assemble every block of `version` at its final VA.  Older blocks keep
    their VAs in every later version; v3 rewrites only the placeguard body."""
    early = [
        ("fillterr", src_fillterr()),
        ("vis1", src_issurf(VIS1_CONT)),
        ("vis2", src_issurf(VIS2_CONT)),
        ("spellgate", src_spellgate()),
        ("placeguard", src_placeguard_v1()),
    ]
    if version >= 2:
        early += [
            ("stormcast", src_spellgate(STORM_ALLOW, STORM_DENY)),
            ("stormai", src_spellgate(STORMAI_ALLOW, STORMAI_DENY)),
            ("birdsview", src_spellgate(BIRD_ALLOW, BIRD_DENY)),
        ]
    out, order, va = {}, [], CAVE
    for name, src in early:
        code = asm(src, va)
        out[name] = (va, code)
        order.append(name)
        va = (va + len(code) + 0xF) & ~0xF           # 16-byte align the next block
    if version >= 3:
        assert va <= V3_BASE, "v2 layout runs into V3_BASE"
        va = V3_BASE

        def put(name, src):
            nonlocal va
            code = asm(src, va)
            out[name] = (va, code)
            order.append(name)
            at = va
            va = (va + len(code) + 3) & ~3          # 4-byte align the next block
            return at

        strict = put("twin_strict", SRC_TWIN_STRICT)
        place = put("twin_place", src_twin_place(strict))
        safe = put("twin_safe", src_twin_safe(strict))
        put("canplace", src_canplace(place))
        put("ptwin_dn", src_ptwin(strict, True, PTWIN_DN_CONT))
        put("pguard_up", src_pguard_up(place))
        put("ptwin_up", src_ptwin(strict, False, PTWIN_UP_CONT))
        put("destroy_up", src_field_arm(safe, False, DESTROY_UP_CONT))
        put("destroy_dn", src_field_arm(safe, True, DESTROY_DN_CONT))
        put("movex_dn", src_field_arm(safe, True, MOVEX_DN_CONT))
        put("movex_up", src_field_arm(safe, False, MOVEX_UP_CONT))
        put("entermp", src_byflag(safe, "ebp", "esi", ENTERMP_CONT))
        put("cansel", src_byflag(safe, "ebx", "esi", CANSEL_CONT))
        put("enterex", src_enterex(safe))
        put("armyplaced", src_byflag(safe, "esi", "esi", ARMYPL_CONT))

        # the placeguard body, rewritten at its own VA
        pg_va = out["placeguard"][0]
        code = asm(src_placeguard_v3(place), pg_va)
        assert pg_va + len(code) <= out["stormcast"][0], \
            "v3 placeguard (%d B) overruns into stormcast" % len(code)
        out["placeguard"] = (pg_va, code)
    if version >= 4:
        # appended after v3's last stub; v3's twin_strict becomes a trampoline so
        # every v3 stub and hook keeps its bytes
        s4 = put("strict4", src_strict(va, CAVE_CHAIN_V4))
        put("cave_rw", src_cave_rw())
        ts_va = out["twin_strict"][0]
        out["twin_strict"] = (ts_va, asm("jmp %#x" % s4, ts_va))
    if version >= 5:
        # strict4 has no slack (cave_rw follows it directly), so the longer chain
        # goes in a new block after cave_rw; the trampoline is repointed and
        # strict4's bytes are zeroed.  cave_rw keeps its VA (the rw call site).
        s5 = put("strict5", src_strict(va, CAVE_CHAIN))
        del out["strict4"]
        order.remove("strict4")
        out["twin_strict"] = (ts_va, asm("jmp %#x" % s5, ts_va))
    for name in CHAINS:
        if name in out:
            chain = CHAINS[name]
            assert out[name][1][CHAIN_AT:CHAIN_AT + len(chain)] == bytes(chain), \
                "chain data misplaced in %s" % name
    end = max(v + len(c) for v, c in out.values())
    return out, order, end


def rel32(src, dst):
    return struct.pack("<i", dst - (src + 5))


def payload(blocks, end):
    p = bytearray(end - CAVE)
    for va, code in blocks.values():
        p[va - CAVE:va - CAVE + len(code)] = code
    return bytes(p)


B1, O1, END1 = build(1)
B2, O2, END2 = build(2)
B3, O3, END3 = build(3)
B4, O4, END4 = build(4)
B5, O5, END5 = build(5)
PAY = {1: payload(B1, END1), 2: payload(B2, END2), 3: payload(B3, END3),
       4: payload(B4, END4), 5: payload(B5, END5)}
USED = END5 - CAVE

# every block an older version owns keeps its VA in the newer one (v5 drops strict4)
for _older, _newer in ((B1, B2), (B2, B3), (B3, B4), (B4, B5)):
    for _n, (_va, _c) in _older.items():
        if _n in _newer:
            assert _newer[_n][0] == _va, "block %s moved between versions" % _n
assert set(B4) - set(B5) == {"strict4"}, "v5 dropped a block other than strict4"
_s4va, _s4 = B4["strict4"]
assert not any(PAY[5][_s4va - CAVE:_s4va - CAVE + len(_s4)]), "v5 leaves strict4 bytes behind"
assert USED <= CAVE_LIMIT, "cave payload %d B outgrew the 0x%X reservation" % (
    USED, CAVE_LIMIT)
assert CAVE + CAVE_LIMIT <= CAVE_ZERO_END, "reservation runs past the verified-zero zone"

# (label, VA, original bytes, target block, generation)
HOOK_TABLE = [
    ("fill       ", FILL_HOOK, FILL_ORIG, "fillterr", 1),
    ("vis1       ", VIS1_HOOK, VIS1_ORIG, "vis1", 1),
    ("vis2       ", VIS2_HOOK, VIS2_ORIG, "vis2", 1),
    ("spellgate  ", SPELL_HOOK, SPELL_ORIG, "spellgate", 1),
    ("placehx    ", PLACE_HOOK, PLACE_ORIG, "placeguard", 1),
    ("stormcast  ", STORM_HOOK, STORM_ORIG, "stormcast", 2),
    ("stormai    ", STORMAI_HOOK, STORMAI_ORIG, "stormai", 2),
    ("birdsview  ", BIRD_HOOK, BIRD_ORIG, "birdsview", 2),
    ("canplace   ", CANPLACE_HOOK, CANPLACE_ORIG, "canplace", 3),
    ("ptwin dn   ", PTWIN_DN_HOOK, PTWIN_DN_ORIG, "ptwin_dn", 3),
    ("pguard up  ", PUP_HOOK, PUP_ORIG, "pguard_up", 3),
    ("ptwin up   ", PTWIN_UP_HOOK, PTWIN_UP_ORIG, "ptwin_up", 3),
    ("destroy up ", DESTROY_UP_HOOK, DESTROY_UP_ORIG, "destroy_up", 3),
    ("destroy dn ", DESTROY_DN_HOOK, DESTROY_DN_ORIG, "destroy_dn", 3),
    ("movex dn   ", MOVEX_DN_HOOK, MOVEX_DN_ORIG, "movex_dn", 3),
    ("movex up   ", MOVEX_UP_HOOK, MOVEX_UP_ORIG, "movex_up", 3),
    ("entermp    ", ENTERMP_HOOK, ENTERMP_ORIG, "entermp", 3),
    ("cansel     ", CANSEL_HOOK, CANSEL_ORIG, "cansel", 3),
    ("enterex    ", ENTEREX_HOOK, ENTEREX_ORIG, "enterex", 3),
    ("armyplaced ", ARMYPL_HOOK, ARMYPL_ORIG, "armyplaced", 3),
]
HOOKS = []
for _label, _va, _orig, _blk, _gen in HOOK_TABLE:
    _new = b"\xE9" + rel32(_va, B3[_blk][0]) + b"\x90" * (len(_orig) - 5)
    assert len(_new) == len(_orig) >= 5, "hook %s: %d bytes is too short for E9" % (
        _label.strip(), len(_orig))
    HOOKS.append((_label, _va, _orig, _new, _gen))

# v4's two non-hook sites: the instance size and the retargeted ReadWrite call
RWCALL_ORIG = b"\xE8" + rel32(RWCALL_VA, RWCALL_TARGET)
RWCALL_V4 = b"\xE8" + rel32(RWCALL_VA, B5["cave_rw"][0])
SITES4 = [("inst size  ", INST_VA, INST_ORIG, INST_V4),
          ("rw call    ", RWCALL_VA, RWCALL_ORIG, RWCALL_V4)]


# ---- build-time assertions on the ASSEMBLED bytes ---------------------------
def verify_cave():
    """Never trust the keystone round trip -- read the encodings back."""
    for name in O5:
        va, code = B5[name]
        code = strip_chain(name, code)              # skip the inline chain data
        n = 0
        for ins in cs.disasm(code, va):
            n += ins.size
            # PIC: no absolute memory operand (a base register plus a 0x55...
            # displacement is the load-delta idiom and is fine).
            if "ptr [0x55" in ins.op_str:
                sys.exit("ABORT: block %s @0x%08X has an absolute memory operand: "
                         "%s %s" % (name, ins.address, ins.mnemonic, ins.op_str))
        if n != len(code):
            sys.exit("ABORT: block %s does not fully disassemble (%d of %d B)"
                     % (name, n, len(code)))

    # The push-imm8 sign-extension trap: read the terrain immediates back off
    # the bytes rather than trusting the source text.
    fill_va, fill = B3["fillterr"]
    pushes = []
    for ins in cs.disasm(fill, fill_va):
        if ins.mnemonic != "push":
            continue
        try:
            pushes.append(int(ins.op_str, 0))       # imm forms only; regs raise
        except ValueError:
            pass
    want = [WALL_TERRAIN, SKY_TERRAIN]
    if sorted(pushes) != sorted(want):
        sys.exit("ABORT: fillterr terrain immediates decode as %s, expected %s "
                 "(keystone push imm8 trap)" % (pushes, want))

    # Both vision stubs must be byte-identical apart from their tail jmp.
    v1 = B3["vis1"][1]
    v2 = B3["vis2"][1]
    if len(v1) != len(v2) or v1[:-5] != v2[:-5]:
        sys.exit("ABORT: the two vision stubs diverge before their tail jump")

    # All four [ebp-7] gates share one predicate; only the 11-byte tail
    # (je rel32 = 6 B, jmp rel32 = 5 B) may differ.
    gates = ["spellgate", "stormcast", "stormai", "birdsview"]
    heads = {B3[g][1][:-11] for g in gates}
    if len(heads) != 1:
        sys.exit("ABORT: the [ebp-7] gate stubs diverge before their tails")
    for g in gates:
        code = B3[g][1]
        if len(code) != len(B3["spellgate"][1]):
            sys.exit("ABORT: gate stub %s has an unexpected length" % g)
        if not (code[-11] == 0x0F and code[-10] == 0x84 and code[-5] == 0xE9):
            sys.exit("ABORT: gate stub %s does not end je rel32 / jmp rel32" % g)


verify_cave()


# ---- the helper model: EXECUTE the assembled helpers --------------------------
class _Mini:
    """Just enough of an x86 interpreter to run the cave-link helpers: the
    instructions they contain, EFLAGS ZF/SF/CF/OF, a stack, and a byte-addressed
    memory holding the cave itself plus a fake map object.  Anything else aborts
    the check."""
    M = 0xFFFFFFFF
    REGS32 = ("eax", "ebx", "ecx", "edx", "esi", "edi")
    REGS8 = {"al": "eax", "bl": "ebx", "cl": "ecx", "dl": "edx"}

    def __init__(self, code_map, mem):
        self.code = code_map                         # VA -> capstone insn
        self.mem = mem                               # VA -> byte

    def rd(self, a, n):
        return int.from_bytes(bytes(self.mem.get(a + i, 0) for i in range(n)), "little")

    def ea(self, r, text):
        inner = text[text.index("[") + 1:text.index("]")]
        tot = 0
        for part in inner.replace("- ", "+ -").split("+"):
            part = part.strip()
            neg = part.startswith("-")
            part = part.lstrip("-").strip()
            if part in r:
                v = r[part]
            else:
                v = int(part, 0)
            tot += -v if neg else v
        return tot & self.M

    def run(self, entry, regs):
        r = {k: 0 for k in self.REGS32}
        for k, v in regs.items():
            r[k] = v & self.M
        keep = {k: r[k] for k in self.REGS32 if k != "eax"}
        f = {"Z": 0, "S": 0, "C": 0, "O": 0}
        stack = ["RET"]
        pc = entry
        for _ in range(500):
            ins = self.code.get(pc)
            if ins is None:
                raise RuntimeError("pc 0x%08X is not an instruction" % pc)
            m, ops = ins.mnemonic, [o.strip() for o in ins.op_str.split(",")]
            nxt = pc + ins.size

            def val(o):
                if o in r:
                    return r[o]
                if o in self.REGS8:
                    return r[self.REGS8[o]] & 0xFF
                if "ptr [" in o:
                    n = 1 if o.startswith("byte") else 4
                    return self.rd(self.ea(r, o), n)
                return int(o, 0) & self.M

            def put(o, v):
                if o in self.REGS8:
                    reg = self.REGS8[o]
                    r[reg] = (r[reg] & ~0xFF & self.M) | (v & 0xFF)
                else:
                    r[o] = v & self.M

            def width(o):
                return 8 if (o in self.REGS8 or o.startswith("byte")) else 32

            def setf(res, bits):
                res &= (1 << bits) - 1
                f["Z"] = int(res == 0)
                f["S"] = res >> (bits - 1)
                return res

            def sub_flags(a, b, bits):
                mask = (1 << bits) - 1
                a, b = a & mask, b & mask
                res = setf(a - b, bits)
                f["C"] = int(a < b)
                sa, sb, sr = a >> (bits - 1), b >> (bits - 1), res >> (bits - 1)
                f["O"] = int(sa != sb and sr != sa)
                return res

            if m == "ret":
                tgt = stack.pop()
                if tgt == "RET":
                    for k, v in keep.items():
                        if r[k] != v:
                            raise RuntimeError("helper at 0x%08X clobbered %s" % (entry, k))
                    return r["eax"] - (1 << 32) if r["eax"] >> 31 else r["eax"]
                pc = tgt
                continue
            if m == "call":
                stack.append(nxt)
                pc = int(ops[0], 0)
                continue
            if m == "push":
                stack.append(val(ops[0]))
            elif m == "pop":
                r[ops[0]] = stack.pop()
            elif m == "mov":
                put(ops[0], val(ops[1]))
            elif m == "movzx":
                put(ops[0], val(ops[1]))
            elif m == "test":
                setf(val(ops[0]) & val(ops[1]), width(ops[0]))
                f["C"] = f["O"] = 0
            elif m == "cmp":
                w = min(width(ops[0]), width(ops[1])) if "ptr" in ops[0] else width(ops[0])
                sub_flags(val(ops[0]), val(ops[1]), w)
            elif m == "xor":
                put(ops[0], setf(val(ops[0]) ^ val(ops[1]), 32))
                f["C"] = f["O"] = 0
            elif m == "bt":
                f["C"] = (val(ops[0]) >> (val(ops[1]) & 31)) & 1
            elif m in ("inc", "dec", "add", "sub"):
                a = val(ops[0])
                b = 1 if m in ("inc", "dec") else val(ops[1])
                c = f["C"]
                if m in ("inc", "add"):
                    res = setf(a + b, 32)
                    sa, sb, sr = a >> 31, (b & self.M) >> 31, res >> 31
                    f["O"] = int(sa == sb and sr != sa)
                    f["C"] = int(a + (b & self.M) > self.M)
                else:
                    res = sub_flags(a, b, 32)
                if m in ("inc", "dec"):
                    f["C"] = c
                put(ops[0], res)
            elif m == "or":
                put(ops[0], setf(val(ops[0]) | val(ops[1]), 32))
                f["C"] = f["O"] = 0
            elif m.startswith("j"):
                cond = {
                    "jmp": True, "je": f["Z"], "jne": not f["Z"],
                    "ja": not f["C"] and not f["Z"], "jbe": f["C"] or f["Z"],
                    "jb": f["C"], "jae": not f["C"],
                    "jl": f["S"] != f["O"], "jge": f["S"] == f["O"],
                    "js": f["S"], "jns": not f["S"],
                }.get(m)
                if cond is None:
                    raise RuntimeError("unmodelled %s" % m)
                if cond:
                    pc = int(ops[0], 0)
                    continue
            else:
                raise RuntimeError("unmodelled %s %s" % (m, ins.op_str))
            pc = nxt
        raise RuntimeError("helper did not return")


def cave_twin_model(level, down, mask, count):
    """The reference: walk CAVE_CHAIN from `level`, skip disabled or missing."""
    if level not in CAVE_CHAIN:
        return -1
    i = CAVE_CHAIN.index(level)
    step = 1 if down else -1
    i += step
    while 0 <= i < len(CAVE_CHAIN):
        c = CAVE_CHAIN[i]
        if c < count and not (mask >> c) & 1:
            return c
        i += step
    return -1


FAKE_MAP, FAKE_CONT = 0x10000, 0x20000


def model_check():
    """Run twin_strict / twin_place / twin_safe (v5) for every level -2..7, both
    directions, every disabled mask over levels 1..5, counts 3..6, against
    cave_twin_model.  _Mini.run also refuses a helper that returns with any
    register but EAX changed."""
    code_map, mem = {}, {}
    for name in O5:
        va, code = B5[name]
        for i, b in enumerate(code):
            mem[va + i] = b
        body = strip_chain(name, code)
        for ins in cs.disasm(body, va):
            code_map[ins.address] = ins
    emu = _Mini(code_map, mem)

    def setmap(mask, count):
        for i, b in enumerate(FAKE_MAP.to_bytes(4, "little")):
            mem[MAPGLOBAL + i] = b
        mem[FAKE_MAP + MASK_OFF] = mask
        for i, b in enumerate(FAKE_CONT.to_bytes(4, "little")):
            mem[FAKE_MAP + 0x10 + i] = b
        for i, b in enumerate(count.to_bytes(4, "little")):
            mem[FAKE_CONT + 0x14 + i] = b

    bad = []
    n = 0
    for count in (3, 4, 5, 6):
        for mask in range(0, 64, 2):                  # bit 0 (Surface) never set
            setmap(mask, count)
            for level in range(-2, 8):
                for down in (0, 1):
                    want = cave_twin_model(level, down, mask, count)
                    dl = 1 if down else 0
                    tag = "L=%d %s mask=%02X n=%d" % (level, "dn" if down else "up",
                                                       mask, count)
                    got = emu.run(B5["twin_strict"][0],
                                  {"eax": level, "edx": 0xABCD00 | dl, "ecx": 0x1234,
                                   "ebx": 0x5678, "esi": 0x9ABC, "edi": 0xDEF0})
                    if got != want:
                        bad.append("strict %s: %d, want %d" % (tag, got, want))
                    got = emu.run(B5["twin_safe"][0], {"eax": level, "edx": dl})
                    if got != (level if want == -1 else want):
                        bad.append("safe %s: %d" % (tag, got))
                    got = emu.run(B5["twin_place"][0],
                                  {"eax": level, "edx": dl, "ecx": FAKE_CONT})
                    if got != (want if 0 <= want < count else -1):
                        bad.append("place %s: %d" % (tag, got))
                    n += 3
    # no map at all: behaves as v3 did (nothing disabled, nothing missing)
    for i in range(4):
        mem[MAPGLOBAL + i] = 0
    for level in range(-2, 8):
        for down in (0, 1):
            want = cave_twin_model(level, down, 0, 0x7F)
            got = emu.run(B5["twin_strict"][0], {"eax": level, "edx": down})
            if got != want:
                bad.append("no-map L=%d: %d, want %d" % (level, got, want))
            n += 1
    if bad:
        sys.exit("ABORT: helper model mismatch (%d of %d):\n  " % (len(bad), n)
                 + "\n  ".join(bad[:20]))
    return n


MODEL_RUNS = model_check()


# ---- PE section mapping -----------------------------------------------------
def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e + 6)[0]
    optsize = struct.unpack_from("<H", data, e + 20)[0]
    sec = e + 24 + optsize
    secs = []
    for _ in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", data, sec + 8)
        secs.append((vaddr, vsize, raw, rsize))
        sec += 40
    return secs


def va2off(secs, va):
    """VA -> file offset THROUGH THE SECTION TABLE (the delta is per-section:
    CODE is +0x55700C00, DATA is +0x55701200).  Never a flat delta."""
    rva = va - DLL_BASE
    for vaddr, vsize, raw, rsize in secs:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
    raise ValueError("VA %08X not mapped" % va)


def reloc_vas(data):
    """Every base-relocation target VA in the image."""
    e = struct.unpack_from("<I", data, 0x3C)[0]
    rva, size = struct.unpack_from("<II", data, e + 24 + 136)
    secs = load_sections(data)
    off = va2off(secs, DLL_BASE + rva)
    end, out = off + size, set()
    while off < end:
        page, blk = struct.unpack_from("<II", data, off)
        if blk < 8:
            break
        for k in range((blk - 8) // 2):
            ent = struct.unpack_from("<H", data, off + 8 + 2 * k)[0]
            if ent >> 12:
                out.add(DLL_BASE + page + (ent & 0xFFF))
        off += blk
    return out


def safety_checks(data):
    """For the v3 sites: no .reloc dword overlaps a displaced range, and no
    branch outside a range lands strictly inside it (rel32 E8/E9 anywhere in
    CODE, plus every capstone branch in the Cave unit, short forms included)."""
    secs = load_sections(data)
    ranges = [(va, va + len(orig), label.strip()) for label, va, orig, _n, gen in HOOKS
              if gen == 3]
    problems = []
    rel = reloc_vas(data)
    for lo, hi, label in ranges + [(va, va + len(o), l.strip()) for l, va, o, _n in SITES4]:
        hit = [v for v in rel if v < hi and v + 4 > lo]
        if hit:
            problems.append(".reloc under %s: %s" % (label, ", ".join("%08X" % v for v in hit)))
    vaddr, vsize, raw, rsize = secs[0]                   # CODE
    code = data[raw:raw + min(vsize, rsize)]
    base = DLL_BASE + vaddr
    for m in re.finditer(b"[\xE8\xE9]", code):
        i = m.start()
        if i + 5 > len(code):
            break
        src = base + i
        tgt = src + 5 + struct.unpack_from("<i", code, i + 1)[0]
        for lo, hi, label in ranges:
            if lo < tgt < hi and not (lo <= src < hi):
                problems.append("rel32 %08X -> inside %s (%08X)" % (src, label, tgt))
    ulo, uhi = CAVE_UNIT
    o = va2off(secs, ulo)
    for ins in cs.disasm(bytes(data[o:o + uhi - ulo]), ulo):
        if not (ins.mnemonic.startswith("j") or ins.mnemonic == "call"):
            continue
        try:
            tgt = int(ins.op_str, 16)
        except ValueError:
            continue
        for lo, hi, label in ranges:
            if lo < tgt < hi and not (lo <= ins.address < hi):
                problems.append("branch %08X -> inside %s (%08X)"
                                % (ins.address, label, tgt))
    return problems


def disasm(code, va, title=None):
    if title:
        print("   --- %s @0x%08X (%d B) ---" % (title, va, len(code)))
    for ins in cs.disasm(code, va):
        print("  %08X  %-22s %s %s"
              % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))


def kill_aow():
    """Standing authorisation (CLAUDE.md).  The names come from zigexe -- the
    pre-2026-09-09 list here missed AoWz / AoWzEd, which lock this DLL too."""
    import subprocess
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match '^(%s)$' } | "
         "Stop-Process -Force" % "|".join(zigexe.LOCKING_PROCESSES)],
        capture_output=True)


def main():
    apply_ = "--apply" in sys.argv
    undo = "--undo" in sys.argv
    dis = "--dis" in sys.argv or "--show" in sys.argv
    if apply_ and undo:
        sys.exit("pick one of --apply / --undo")

    print("build_maplevel4 v5   Firmament = level %d (Sky 0x%02X), Abyss = level %d   "
          "cave 0x%08X..0x%08X (%d of %d B; v4 %d, v3 %d, v2 %d, v1 %d)"
          % (SKY_LEVEL, SKY_TERRAIN, ABYSS_LEVEL, CAVE, END5 - 1, USED, CAVE_LIMIT,
             END4 - CAVE, END3 - CAVE, END2 - CAVE, END1 - CAVE))
    print("cave chain %s, skipping disabled (mask [map+0x%X], id 0x%X) and missing "
          "levels   (helper model: %d runs ok)"
          % (list(CAVE_CHAIN), MASK_OFF, MASK_ID, MODEL_RUNS))
    for name in O5:
        va, code = B5[name]
        tag = ("" if name in V1_BLOCKS else "   [v2]" if name in V2_BLOCKS else
               "   [v4]" if name == "cave_rw" else "   [v5]" if name == "strict5" else
               "   [v3]")
        if name == "placeguard":
            tag = "   [v1, body rewritten in v3]"
        if name == "twin_strict":
            tag = "   [v3, a trampoline to strict5 since v5]"
        print("    %-11s 0x%08X  %4d B%s" % (name, va, len(code), tag))
    print("    (v4's strict4 at 0x%08X, %d B, is zeroed in v5)"
          % (_s4va, len(_s4)))

    if dis:
        print()
        for name in O5:
            va, code = B5[name]
            if name in CHAINS:
                print("   (%s carries the chain %s as data at 0x%08X)"
                      % (name, list(CHAINS[name]), va + CHAIN_AT))
            disasm(strip_chain(name, code), va, name)
            print()
        print("   --- cap byte 0x%08X: %s -> %s ---\n"
              % (CAP_VA, CAP_ORIG.hex(" "), CAP_V3.hex(" ")))
        for label, va, orig, new in SITES4:
            print("   --- %s 0x%08X: %s -> %s ---" % (label.strip(), va, orig.hex(" "),
                                                     new.hex(" ")))
        print()
        for label, va, orig, new, gen in HOOKS:
            disasm(new, va, "site %s gen%d (was: %s)"
                   % (label.strip(), gen, orig.hex(" ")))
            print()
        return

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s" % DLL)
    data = bytearray(open(DLL, "rb").read())
    secs = load_sections(data)

    def rd(va, n):
        o = va2off(secs, va)
        return bytes(data[o:o + n])

    def wr(va, b):
        o = va2off(secs, va)
        data[o:o + len(b)] = b

    cur_cave = rd(CAVE, CAVE_LIMIT)
    cave_is = {0: cur_cave == bytes(CAVE_LIMIT)}
    for v in (1, 2, 3, 4, 5):
        p = PAY[v]
        cave_is[v] = cur_cave[:len(p)] == p and not any(cur_cave[len(p):])

    print()
    cap = rd(CAP_VA, 4)
    cap_st = {CAP_ORIG: "original", CAP_V12: "v1/v2 (4 levels)",
              CAP_V3: "v3+ (5 levels)"}.get(cap, "FOREIGN")
    print("  cap byte    gen- 0x%08X  %-17s %s" % (CAP_VA, cap.hex(" "), cap_st))
    s4 = []
    for label, va, orig, new in SITES4:
        cur = rd(va, len(orig))
        st = "original" if cur == orig else "patched" if cur == new else "FOREIGN"
        s4.append(st)
        print("  %s gen4 0x%08X  %-17s %s" % (label, va, cur.hex(" "), st))
    states = []
    for label, va, orig, new, gen in HOOKS:
        cur = rd(va, len(orig))
        st = ("original" if cur == orig else
              "patched" if cur == new else "FOREIGN")
        states.append((st, gen))
        show = cur if len(cur) <= 6 else cur[:6]
        print("  %s gen%d 0x%08X  %-17s %s%s"
              % (label, gen, va, show.hex(" "), st, "" if len(cur) <= 6 else "  (%d B)" % len(cur)))
    known = [v for v in (5, 4, 3, 2, 1, 0) if cave_is[v]]
    print("  cave        0x%08X  %s"
          % (CAVE, "all zero" if cave_is[0] else
             "v%d payload (%d B), rest zero" % (known[0], len(PAY[known[0]])) if known else
             "DIFFERS from every state this script knows"))

    if cap_st == "FOREIGN" or "FOREIGN" in s4 or any(st == "FOREIGN" for st, _ in states):
        sys.exit("\nABORT: at least one site holds bytes this script neither wrote "
                 "nor expects. Inspect before writing.")

    def gens(g, want):
        return all(st == want for st, gen in states if gen == g)

    g4o = all(x == "original" for x in s4)
    g4p = all(x == "patched" for x in s4)
    st_orig = cap == CAP_ORIG and gens(1, "original") and gens(2, "original") \
        and gens(3, "original") and g4o and cave_is[0]
    st_v1 = cap == CAP_V12 and gens(1, "patched") and gens(2, "original") \
        and gens(3, "original") and g4o and cave_is[1]
    st_v2 = cap == CAP_V12 and gens(1, "patched") and gens(2, "patched") \
        and gens(3, "original") and g4o and cave_is[2]
    st_v3 = cap == CAP_V3 and gens(1, "patched") and gens(2, "patched") \
        and gens(3, "patched") and g4o and cave_is[3]
    st_v4 = cap == CAP_V3 and gens(1, "patched") and gens(2, "patched") \
        and gens(3, "patched") and g4p and cave_is[4]
    st_v5 = cap == CAP_V3 and gens(1, "patched") and gens(2, "patched") \
        and gens(3, "patched") and g4p and cave_is[5]

    problems = safety_checks(data)
    print("  v3/v4 sites: .reloc / interior-branch check: %s"
          % ("CLEAN" if not problems else "!! " + "; ".join(problems)))

    older = st_v1 or st_v2 or st_v3 or st_v4
    if st_orig:
        print("\nSTATUS: orig -- NOT applied")
    elif st_v1:
        print("\nSTATUS: applied (v1 -- NEEDS RE-TUNE to v5)")
    elif st_v2:
        print("\nSTATUS: applied (v2 -- NEEDS RE-TUNE to v5: no Abyss)")
    elif st_v3:
        print("\nSTATUS: applied (v3 -- NEEDS RE-TUNE to v5: no disabled-levels mask)")
    elif st_v4:
        print("\nSTATUS: applied (v4 -- NEEDS RE-TUNE to v5: no Firmament caves)")
    elif st_v5:
        print("\nSTATUS: applied (v5 -- up to date)")
    else:
        print("\nSTATUS: PARTIAL / UNRECOGNISED -- the site states and the cave "
              "do not add up to orig, v1, v2, v3, v4 or v5.")

    # ---- undo ----
    if undo:
        if st_orig:
            print("Nothing to undo.")
            return
        if not (older or st_v5):
            sys.exit("ABORT: unrecognised state -- refusing to undo blind.")
        wr(CAP_VA, CAP_ORIG)
        for label, va, orig, new in SITES4:
            wr(va, orig)
        for label, va, orig, new, gen in HOOKS:
            wr(va, orig)                       # restores every generation's sites
        wr(CAVE, bytes(max(USED, END4 - CAVE)))    # the FULL v4/v5 length
        if any(rd(CAVE, CAVE_LIMIT)):
            sys.exit("BUG: undo left non-zero bytes in the reservation -- not writing.")
        kill_aow()
        try:
            open(DLL, "wb").write(data)
        except PermissionError:
            sys.exit("ERROR: AoWEPACK.dpl is locked. Kill every AoW binary and retry.")
        print("UNDO: cap byte 0x%08X -> 03, instance size -> 0x41C, ReadWrite call "
              "restored, %d hook sites restored, cave 0x%08X zeroed (%d B). No backup "
              "touched." % (CAP_IMM_VA, len(HOOKS), CAVE, USED))
        return

    if not apply_:
        if not st_v5:
            print("DRY RUN -- re-run with --apply to commit%s."
                  % (" (in-place cave rewrite -> v5)" if older else ""))
        return

    if st_v5:
        print("\nAlready applied (v5) and up to date -- nothing to do.")
        return

    if not (st_orig or older):
        sys.exit("ABORT: --apply accepts only the orig, v1, v2, v3 or v4 state.")
    if problems:
        sys.exit("ABORT: a v3/v4 site fails the .reloc / interior-branch check.")

    # The st_orig check only proves this feature's sites and its own cave are
    # unpatched -- it says nothing about the rest of the DLL, and after an
    # --undo it is precisely the state this script itself just produced. So the
    # backup is gated on proven_pristine() (a byte-compare against
    # AoWEPACK_original_backup.dpl), never on st_orig and never on the absence
    # of a backup file.
    if st_orig and not os.path.exists(BACKUP) and proven_pristine():
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("backup -> backups\\%s" % os.path.basename(BACKUP))
    elif older:
        print("in-place rewrite -> v5: NO backup taken (the file on disk is this "
              "script's own previous output, not a proven-unpatched state)")
    elif not os.path.exists(BACKUP):
        print("backup skipped -- the live DLL is not byte-identical to the "
              "pristine reference, so a snapshot of it would prove nothing")

    wr(CAP_VA, CAP_V3)
    for label, va, orig, new in SITES4:
        wr(va, new)
    for label, va, orig, new, gen in HOOKS:
        wr(va, new)
    wr(CAVE, bytes(CAVE_LIMIT))
    wr(CAVE, PAY[5])

    kill_aow()
    try:
        open(DLL, "wb").write(data)
    except PermissionError:
        sys.exit("ERROR: AoWEPACK.dpl is locked. Kill every AoW binary and retry.")
    print("\nAPPLIED v5: cap byte 0x%08X -> 05; TAoWHSMap 0x41C -> 0x420 with the mask at "
          "+0x%X (id 0x%X); %d hooks; cave chain %s; cave %d B at 0x%08X."
          % (CAP_IMM_VA, MASK_OFF, MASK_ID, len(HOOKS), list(CAVE_CHAIN), USED, CAVE))
    print("Revert with --undo (surgical). No RNG draws in this feature.")


if __name__ == "__main__":
    main()
