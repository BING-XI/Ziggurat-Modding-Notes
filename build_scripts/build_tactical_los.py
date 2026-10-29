#!/usr/bin/env python
r"""
build_tactical_los.py -- line of sight and fog of war in every tactical combat (owner's rulings
2026-10-23).  AoWTCPCK.dpl.

RULES
    * Combat sight = 3 x (3 + Vision level) (SIGHT_MUL) in world battles.  Inside an exploration
      site it is 3 + Vision, halved and rounded UP without Night Vision (owner, 2026-10-26): 2 for
      Vision 0 or I, 3 for II; Night Vision keeps 3 + Vision.  Tried and dropped: tripled then
      halved (2026-10-25), the engine's rounded-down half (2026-10-26).
    * A unit explores every hex within its combat sight + 8 (EXPLORE_BUF) that it has a clear line
      to, when it moves or is activated, and every unit does so at once when a wall, gate or
      building drops to 0 hit points; explored hexes stay explored.
    * An object blocks only on its solid hexes: its own hex, plus the parts its resource's terrain
      list marks used (a few big trees and buildings).  The engine also makes every object a
      child of the hexes its sprite overlaps (a tree 4, a house or gate 7, big buildings up to
      37); those hexes do not block (spart).  When a wall, gate, house or structure's solid hex is
      explored, the hexes its sprite covers are explored too, so it is not drawn half black
      (wclose).
    * Outside exploration sites, at battle start each player also explores everything a flood fill
      from its units reaches without crossing rock, a wall or gate it may not see past, or the
      off-map border, plus the blockers that flood touches.  Exploration sites (dungeons, lairs,
      ruins...) start dark.
    * A hex is SEEN while one of the seated player's own units has it within combat sight and a
      clear line.  Vision is per player: allied armies share nothing.
    * An explored hex nobody sees shows its terrain under the fog shade, and keeps drawing its
      decorations (DECOR: walls and gates in any state, trees, rocks, houses, corpses, blood, ooze,
      fire, dropped items...).  Units, unit shadows and effects are not drawn there, and the cursor,
      clicks and the camera ignore it.  Unexplored hexes stay black.
    * Rock blocks sight and exploration everywhere: lair rock (every isometric combat hex, incl.
      the cave-entrance map) and the "Wall" single hexes of site maps.
    * Obstacles block sight everywhere but exploration only inside exploration sites (owner,
      2026-10-24): houses, the Inn, Mine and Sacred Stones (BLOCK_MAIN) while they have hit points,
      combat obstacles (site cave walls and pillars, bridge sides), Trees, Dead Trees, Pine Trees,
      Willow Trees, Rocks (BLOCK_TERR).  So in a world battle explore and the start flood look
      past them; the fog still hides what stands behind them.  The first blocking hex is itself
      seen.
    * Move orders (owner, 2026-10-25): a move may target any explored hex, seen or not, and the
      route is planned as if units the player cannot see were not there.  A plain move stops when
      its next hex is occupied (vanilla), and also as soon as the moving unit sees an occupied hex
      further along its route (within its combat sight, clear line).  Melee and touch moves keep
      vanilla's rule only.
    * City walls and gates with hit points block one way: a unit standing inside the walls sees
      out over them, a unit outside does not see in.  Inside = reached from the map centre without
      crossing a wall, gate or the border, or enclosed from the border by walls, or a wall or gate
      hex itself; fixed once per battle from the template (inside_build).  The start flood of a
      player with any unit inside passes walls and gates.

VANILLA (11-engine-internals.md, "Tactical line of sight and fog of war")
    TRndTacHsm.RandomMap 0x424FBC..0x424FDB sets the combat map's exploration flag [map+0xC9] only
    for an exploration-site interior (TCombat+0x40 == 1) and forces fog [map+0xC8] off.  Explored
    bits ([field+0x18], bit player-1) are written by TAbstractAoWHSMap.ExploreArea, called from
    TTacticalCombatUnitHS.Activate and TCombatMoveTE.ExecuteDefaultMove.  Nothing in tactical
    combat maintains the fog counter [field+0x1A].  With exploration on,
    TAbstractAoWHSMap.UpdateStaticScene/UpdateDynamicScene draw only explored hexes' objects, and
    DrawFog paints unexplored hexes black and counter-0 hexes with the shade.  A field's children
    [field+8] split into static ([0, [field+0xE])) and dynamic ([[field+0xE], [field+0xD])); walls,
    trees and corpses are among the dynamic ones.

SITES (all vanilla in the live file before this script; none carries a .reloc entry except the
VMT cell, whose new value is another address in this image)
    RM_EXPL  0x424FBC  mov dl,[ebp-0x3B] -> mov dl,1; nop     exploration on in every combat
    RM_FOG   0x424FCC  xor edx,edx      -> mov dl,1           fog on in every combat
    RM_FOGON 0x424FD5  call [ecx+0x100] -> call fogon; nop    RandomMap's SetFogEnabled call,
                       after the template and its walls are loaded, before any unit is placed
    ST_SITE  0x429940  call SetSeatedCombatPlayer -> call startflood   TTacticalCombat.Execute,
                       after RandomMap has placed the map, its decorations and every unit
    EX_ACT   0x420DBA  call ExploreArea -> call explore       TTacticalCombatUnitHS.Activate
    EX_MOVE  0x4084B2  call ExploreArea -> call explore       TCombatMoveTE.ExecuteDefaultMove
    VMT_UDS  0x413260  TAoWCombatMap VMT +0xDC (UpdateDynamicScene) -> uds
    DF_SITE  0x41BFDF  call DrawFog     -> call drawfog       TAoWCombatMap.DrawDynamicScene
    CAM x4             call GetExplored -> call seen          camera on moves/strikes/shots
                       (0x408DDE 0x409129 0x409D99 0x40B4A6)
    INPUT x5           call GetExplored -> call xpl           move orders in ExecuteMoveSelection
                       (0x41E49A group, 0x41EBEF single, 0x41ECE1 movement ability) and the cursor
                       in UpdateMoveCursor (0x41F7A0, 0x41FCB4)
    AI_SPOT  0x4183B7  call GetExplored -> call aispot        TCAI.EvalBattle phase 0
    UNIT_AT  x6        call [ecx+0x80]  -> call hover; nop    the unit-on-hex lookups of local
                       input: TAoWCombatMap.MouseMoveEvent 0x41B864 (hover cursor),
                       TCombatUnitSelectionControl.MouseDownEvent 0x41EFC3 0x41F260 0x41F4E6
                       0x41F69A (what a click selects or attacks), UpdateMoveCursor 0x41F7B7
    CS x2    0x408480 0x420D96  call [edx+0xA4] (GetVisibilityRange) -> call csight; nop, the
                       radius both explore calls pass
    CALC     0x412EBC  TCombatUnitSelectionControl VMT +8 (CalculateMovePath) -> calcwrap
    CANON    0x412DD8  TTacticalCombatUnitHS VMT +0xD0 (CanMoveOn) -> canon
    CANOVER  0x412DDC  TTacticalCombatUnitHS VMT +0xD4 (CanMoveOver) -> canover; the value it
                       replaced (vanilla thunk 0x402A94, or build_group_move_tc.py's cave_unit) is
                       kept in T_PREV and restored by --undo
    STEP     0x408E5A  call TAoWMapField.GetPlayer -> call stepchk   TCombatMoveTE.DefaultMove,
                       the next step's hex
    The four VMT cells keep their .reloc entries: their new values are addresses in this image.
    HP_WALL  0x405C12  mov eax,[ebp-8]; mov edx,[ebp-4] -> call wallhp; nop
    HP_STR   0x432A4A  the same, ahead of the hit-point write in TCityWall.SetHitPoints (walls,
                       gates) and TCombatStructure.SetHitPoints (houses and the other buildings)

CAVES  zone 0x00441000-0x00443FFF, exclusive.  Entry stubs at fixed addresses, 8 B each in STUBS
order from 0x441000 (explore, uds, drawfog, seen, aispot, hover, startflood, fogon, wallhp,
csight, xpl, calcwrap, canon, canover, stepchk), so a re-tune never changes a hook's bytes;
T_PREV 0x441078; tables from 0x441080 (neighbour deltas, the blocking resource guids, the
decoration VMTs), then the routines, packed.
    explore   replaces ExploreArea (same ABI, ret 0xC): rebuilds the blocking bitmap from the
              live hexes (obstacles left out in a world battle: [+0x38] = 1), then sets the owner's
              explored bit on every hex within combat sight + 8 with a clear line, then wclose.
              Player 0 (independents) is skipped -- GetExplored already answers 1 for it.  New
              hexes for the seated player, or any wclose change, set [map+0x30] (static scene
              invalid; ShowScene rebuilds it); every call clears the fog signature so the next
              frame recounts.  Runs inside TEs on every machine from synchronised state only.
    spart     is this part of an object solid: part 0 yes; other parts only for structures,
              obstacles and terrain objects whose terrain list marks them used.  blocker, iswall
              and wclose skip the rest.
    wclose    gives the explored bits of players 1..12 (0x0FFF; bits 12-15 of [field+0x18] are the
              engine's movement flags) of each hex where a wall, gate, house or structure is solid
              to the neighbouring hexes holding the same object; only hexes explored before the
              call give, so it never chains (a 2026-10-24 version chained along whole wall rings
              and treated sprite hexes as solid).
    csight    eax = TCombatUnit -> combat sight: GetVisibilityRange x 3 outside exploration sites;
              inside one, 3 + Vision halved and rounded up without Night Vision (base minus the
              engine's rounded-down half), unhalved with it.  Then, while build_mist_tc.py's pinned
              entry 0x43CC40 starts with E9, that entry adjusts it (Mist).  Used by explore's
              callers, fog_update, reexplore and stepchk.
    xpl       GetExplored for the move-order and cursor sites: explored for the seat (expl), seen
              or not; nil -> 0.
    calcwrap  CalculateMovePath with O_PLAN set around it: the only way the local player's
              orders, previews and group plans are pathed.  aispot clears O_PLAN too.
    hidn      an occupant is hidden from the planner when O_PLAN is set, the moving unit
              ([[pos]+0x1E0]+0x1C) belongs to the seated player and the occupant's hex is not seen.
    canon     CanMoveOn: a hidden occupant vetoes nothing, else the original.
    canover   CanMoveOver: a hidden occupant is passable, else the T_PREV method.
    stepchk   DefaultMove's next-hex test: occupied -> that player (vanilla stops).  Free, and a
              plain TCombatMoveTE: scans the rest of the path (TXYLList [te+0x14], [te+0x18]
              steps left, path[0] the destination, which is not scanned) and returns 0 (stop) for the first occupied hex
              within the mover's combat sight with a clear line.  Synchronised state only.
    wallhp    in both SetHitPoints ([ebp-8] the new hit points, already clamped to >= 0, [ebp-4]
              Self): on a drop from > 0 to 0 it writes the 0 itself, then reexplore runs explore
              for every live unit in TCombatData, as if each had just moved.  Without it a breach
              is seen (fog counter > 0) but stays black until a unit moves or is activated.  The
              setter's own write then stores the same 0.  TE code: every machine.
    fogon     runs inside_build, then the SetFogEnabled call it replaced.  inside_build sets bit
              0x01 of [field+0x1B] (kept all battle) on the inside hexes: walls and gates marked
              0x08, the border seeds 0x04; a flood from the centre (0x10) stopped by walls, gates
              and the border, a flood from the border (0x04) stopped by walls and gates; inside =
              0x10 or 0x08 set, or 0x04 clear.  Scratch bits cleared after.  Runs once per battle
              on every machine from the template only.
    startflood  calls SetSeatedCombatPlayer, then worldflood: outside exploration sites, marks the
              solid hexes (bit 0x08) and the standing walls and gates (0x10), and for each player
              with a live unit floods (bit 0x04, forward/backward relaxation sweeps until nothing
              changes) from that player's units, stopped by solid hexes and the border, and by
              walls and gates unless one of the player's units stands inside; then sets that
              player's explored bit on the flood and on the stopping hexes it touches, then
              wclose.  Scratch bits cleared after, 0x01 and 0x02 kept.  Runs once per battle on
              every machine from synchronised state only.
    uds       TAoWCombatMap's UpdateDynamicScene: vanilla's loop, but per hex: seen -> every
              dynamic object (HSEngine CopyDynamicVisibleHS); explored, not seen -> only the
              dynamic objects whose VMT is in T_DECOR (decor); unexplored -> nothing.  First it
              calls fog_update.  Seated player 0xFF (a watching non-participant) gets HSEngine's
              base routine: everything drawn.
    fog_update  rebuilds the blocking bitmap, hashes it with the seated player's live units
              (hex, combat sight) and the seat; on a change zeroes every [field+0x1A] and adds 1
              over each such unit's combat sight through the line test.  Per machine, display only.
              A seat change calls UpdateStaticScene (VMT +0xD8) itself: fog_update runs inside
              ShowScene after its UpdateStaticScene, so setting [map+0x30] here made
              DrawStaticHS raise "Static scene is invalid" once per battle (fixed 2026-10-24).
    drawfog   skips DrawFog for seat 0xFF; otherwise vanilla DrawFog.
    seen      GetExplored for the nine input/camera sites: nil field -> 0 (the DefaultMove site
              could pass nil, which the real GetExplored dereferences), else explored and counter
              > 0 for the seated player.
    aispot    the AI's "has the human found this unit" test keeps vanilla semantics inside an
              exploration site and answers 1 everywhere else, so in open battles the AI acts from
              the first turn exactly as before.  A visibility test here would park every AI unit
              the human cannot see, and an unseen AI attacker would never advance.
              EXCEPT when the AI plays for the seated player (build_unit_ai.py's Space, vanilla
              Auto: [TCombatData+0x31], the combat player EvalBattle moves, == [map+0xEC]): then a
              unit is sorted into the AI's lists only if its own hex is seen (ring index
              [ebp-0xC] == 0 in EvalBattle's frame, the other 18 ring hexes answer 0), so the
              auto-played units know only the enemies their player can see.
              ⚠ The site branch reads this machine's seat [map+0xA5], as vanilla did.  The AI of
              a Global player (independents, computer players) may run on every machine in live
              multiplayer (Inioch's lan-desync notes, share9), where that would diverge.  Not
              reachable today: TExplorationSite.Search raises the tactical dialog only with one
              human player or in PBEM, so live-MP site battles auto-resolve.  A patch that opens
              them must first give this branch a synchronised answer (Inioch's mod: always 1).
    hover     the input unit lookups return nothing on a hex that is not seen, so a hidden
              enemy is neither hovered, selected nor attacked; the click then falls through to
              the move path, which refuses an unseen hex.
    los       two greedy hex walks centre->target with opposite tie-breaks (build_los_terrain.py's
              method and neighbour table); seen if either crosses no blocking intermediate.  A
              standing wall or gate blocks only when the viewer's hex is outside (bit 0x01 clear,
              copied to +0x1C by fill).  Off-map intermediates do not block; 64-step cap fails open.

[field+0x1B] ON COMBAT MAPS: 0x01 inside the walls (this script, all battle); 0x02 the engine's "a
unit here"; 0x04/0x08/0x10 this script's scratch during the two floods; 0x20/0x40
build_wotw_tc.py; 0x80 build_los_terrain.py.  Bit 0x02 is set by TTacticalCombatUnitHS.UpdateMapField
(0x420CEB) when a unit connects to the hex (TUnitHS.PlaceOnMap / MoveTo -> Connect -> the field's
UpdateMapField), and nothing in the engine clears it (TAoWMapField.UpdateMapField 0x55771C88 clears
only 0xE000 of the dword).  While it is clear TAoWMapField.GetPlayer (0x55771C9B) answers 0xFF
without asking the hex's objects.  GetPlayer's combat callers: stepchk (0x44296E next hex,
0x442A49 look-ahead) and ValidMultiMoveSelection 0x41EE0F.  No routine here writes 0x02.

BSS 0x0046C200-0x0046C73F (writable, loader-zeroed): +0 signature, +4 unit count, +8/+0xC bitmap
width/height (0 = no bitmap: lines never block), +0x10 blocking cell count, +0x14 level, +0x18
last seat, +0x1C viewer inside, +0x20..+0x34 the flood's level, width, height, mark, border stop,
wall stop, +0x38 exploration bitmap (1 = obstacles left out; set by each bitmap builder), +0x3C
planning flag (calcwrap), +0x40 64 unit records (x | y<<8 | combat sight<<16), +0x140 the 4096-bit solid bitmap,
+0x340 the 4096-bit standing wall and gate bitmap.

MULTIPLAYER
    Synchronised: the flag bytes (combat setup), startflood (battle start), explore, wallhp and
    stepchk (TE code);  move routes are planned on the ordering machine (O_PLAN, its fog) and
    travel inside the move tokens, as vanilla's do;
    inputs synchronised: unit position and sight, hexes' objects and hit points.  Per machine:
    the fog counter, uds, drawfog, seen, hover -- display and local input only.  An observer (a
    third player watching) is never seated, stays at 0xFF and sees the whole battle (owner,
    2026-10-24); the camera calls
    inside TEs already differed per seat in vanilla.  The tactical AI runs on one machine and stays
    omniscient on its own turns.  No random draws.

KNOWN LEAKS: build_group_move_tc.py's cluster search skips hexes held by any unit, hidden ones
included; the AI playing the seat (Space, Auto) paths with full knowledge; sounds of hidden units (kept on purpose, owner 2026-10-23); combat-log lines naming hidden units (four
independent ring writers, not filtered; owner 2026-10-23: leave as is).  Decorations under fog are
live, so a corpse, a fire or a falling wall shows there as it happens.

COUPLINGS: the explore radius ignores the sight+2 hand edit in TAoWMapLevel.ExploreArea
(0x557721BE) and build_los_terrain.py's terrain 7/8 filter, because explore no longer calls
ExploreArea.  build_unit_ai.py hooks the heads of SetSeatedCombatPlayer/NewTurn; startflood calls
SetSeatedCombatPlayer through that hook as vanilla did.  build_mirrorimage.py's cave_show draws
through TTacticalCombatUnitHS.Show; uds decides whether Show is reached at all.
build_mist_tc.py's entry 0x43CC40 is called from csight while it starts with E9; either script
may be undone alone.
build_combatlog_siege.py hooks the prologues of both SetHitPoints (0x405AE4, 0x432930); wallhp's
sites are further in and share no bytes with them.
⚠ build_group_move_tc.py owns TTacticalCombatUnitHS VMT +0xD4 (cave_unit); canover now sits in
that slot and chains to it through T_PREV, so build_group_move_tc.py reports MIXED and refuses
--apply / --undo.  Undo this script first, then that one; re-apply that one first, then this.
Its markers and CalculateMovePath calls (through VMT +8) all pass through calcwrap.
HISTORY: 2026-10-26 the start flood's mark moved from bit 0x02 to 0x04 and inside_build's centre
mark from 0x02 to 0x10.  Clearing 0x02 after the start flood made every unit that had not moved
since battle start read as absent to GetPlayer in world battles.  DefaultMove's next-step test
and stepchk's look-ahead missed it, so a plain move routed through fog could walk onto a hidden
stationary unit's hex (TUnitHS.MoveTo does not refuse).  ValidMultiMoveSelection accepted a group
move onto it.
2026-10-25 the zone moved from 0x43D000-0x43E7FF (full) to 0x441000; migrate() undoes
an old-zone install on --apply / --undo.  2026-10-23 walls went one-way, both ways, then one-way
again (owner).  The first one-way
build hooked 0x424FD5 to the stub at 0x43D030; --apply and --undo put that site back to vanilla
first (clear_v2), then --apply installs the fogon stub.

    python build_scripts/build_tactical_los.py            dry run + state
    python build_scripts/build_tactical_los.py --apply
    python build_scripts/build_tactical_los.py --undo     surgical: hooks vanilla, zone zeroed
    python build_scripts/build_tactical_los.py --dis      disassemble the caves
    python build_scripts/build_tactical_los.py --test     line-walk model vs a cube-space reference
    python build_scripts/build_tactical_los.py --emulate  run the caves under unicorn (fake map
                                                          plus the real 0126c000 template)
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
import aowepack_patch as P
from aowepack_patch import run

P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000
COMB_RES = os.path.join(P.GAME, "Release", "comb_res.pfs")
HSEPACK = os.path.join(P.GAME, "HSEPack.dpl")

# ---------------------------------------------------------------- tuning
SIGHT_MUL = 3            # combat sight = 3 x (3 + Vision level) in world battles; inside an
                         # exploration site the engine's own sight, halved without Night Vision
                         # (owner, 2026-10-26)
EXPLORE_BUF = 8          # explored radius = combat sight + 8 (owner, 2026-10-23)
RMAX = 40                # radius clamp
STEP_CAP = 64            # line-walk cap; exhausted = clear
MAXCELLS = 4096          # bitmap size in bits (combat maps are 65 x 59 = 3835)
MAXU = 64                # seated player's units tracked per frame

#   resource names (comb_res.pfs tag 6) that block, per resource class
BLOCK_TERR = ("Tree", "Dead Tree", "Pine Tree", "Willow Tree", "Rock")   # 0x220167 TCombatTerrain
BLOCK_SINGLE = ("Wall",)                                                 # 0x22051F single hexes
BLOCK_MAIN = ("Inn", "Mine", "Sacred Stones")                            # 0x22051D TMainStructure
RC_TERR, RC_SINGLE, RC_MAIN = 0x220167, 0x22051F, 0x22051D

# ---------------------------------------------------------------- addresses (verified at run time)
ZONE = (0x00441000, 0x00444000)
OLD_ZONE = (0x0043D000, 0x0043E800)  # the zone until 2026-10-25; --apply / --undo migrate off it
MIST_ENTRY = 0x0043CC40              # build_mist_tc.py's pinned mist_adj (eax sight, edx unit -> eax)
STUBS = ("explore", "uds", "drawfog", "seen", "aispot", "hover", "startflood", "fogon", "wallhp",
         "csight", "xpl", "calcwrap", "canon", "canover", "stepchk")
E = {n: ZONE[0] + 8 * i for i, n in enumerate(STUBS)}
E_EXPLORE, E_UDS, E_DRAWFOG, E_SEEN, E_AISPOT, E_HOVER, E_START, E_FOGON, E_WALLHP, E_CSIGHT = \
    (E[n] for n in STUBS[:10])
T_PREV = ZONE[0] + 0x78             # dword: what TTacticalCombatUnitHS VMT +0xD4 held before canover
T_DELTA = ZONE[0] + 0x80
BSS = 0x0046C200
O_SIG, O_NU, O_BW, O_BH, O_NB, O_LVL, O_SEAT, O_VIN = 0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C
O_ILVL, O_IW, O_IH, O_MARK, O_STOP, O_WSTOP, O_XPL = 0x20, 0x24, 0x28, 0x2C, 0x30, 0x34, 0x38
O_PLAN = 0x3C                       # 1 while the local player's move order is being planned
O_UNITS, O_BMAP, O_WMAP = 0x40, 0x140, 0x340
F_FLAGS = 0x1B      # [field+0x1B]: 0x01 inside the walls (kept all battle); 0x04/0x08/0x10 scratch;
                    # 0x02 is the engine's (a unit here, read by GetPlayer): never written
BORDER = 15                         # off-map terrain id ([field+0x14])
PASS_CAP = 512                      # flood-fill sweep pairs

V_SCREEN = 0x0046C064               # the combat map
THUNK = {                           # import thunk -> expected import (rel32 targets)
    0x0040287C: "AoWE.TAoWMapField.GetExplored",
    0x004028FC: "AoWE.TAbstractAoWHSMap.ExploreArea",
    0x0040290C: "AoWE.TAbstractAoWHSMap.DrawFog",
    0x00402934: "AoWE.TAbstractAoWHSMap.UpdateDynamicScene",
    0x00401E64: "HSEngine.TMapContainer.GetMapLevel",
    0x00402544: "AoWE.TCombatObject.GetPlayer",
    0x00402894: "AoWE.TAoWMapField.GetPlayer",
    0x00401B1C: "HSEngine.TXYLList.Get",
}
GETEXPLORED_T, EXPLOREAREA_T, DRAWFOG_T, UDS_VAN_T = 0x40287C, 0x4028FC, 0x40290C, 0x402934
GETMAPLEVEL_T, GETPLAYER_T = 0x401E64, 0x402544
IAT_NAMES = {                       # resolved to thunks below by FF 25 scan
    "isclass": "System.@IsClass",
    "cd_count": "AoWE.TCombatData.GetCount",
    "cd_objects": "AoWE.TCombatData.GetObjects",
}
IAT_TCOMBATUNIT = 0x0046E904        # AoWEPACK TCombatUnit class reference
IAT_HSE = 0x0046E014                # HSEngine.THSMap.DrawDynamicScene, the HSEPack delta anchor
HSE_ANCHOR = 0x5560D6E4
HSE = {"reset": (0x5560D294, "HSEngine.THSMap.ResetVisibleDynamicHS"),
       "base": (0x5560D4B8, "HSEngine.THSMap.UpdateDynamicScene"),
       "copy": (0x556079A0, "HSEngine.TMapField.CopyDynamicVisibleHS"),
       "anchor": (HSE_ANCHOR, "HSEngine.THSMap.DrawDynamicScene")}
VMT = {                             # class VMTs whose instances can block
    "wall": (0x00405008, "TCityWall"), "door": (0x004052AC, "TCityWallDoor"),
    "house": (0x00434584, "THouse"), "struct": (0x0043258C, "TCombatStructure"),
    "town": (0x004341F8, "TTownhall"), "work": (0x004334E0, "TWorkshop"),
    "main": (0x00435310, "TMainStructure"), "obst": (0x00431BB8, "TCombatObstacle"),
    "iso": (0x0043386C, "TIsometricCombatHexagon"), "terr": (0x0040FCA0, "TCombatTerrain"),
    "single": (0x00434E38, "TSingleCombatHexagon"), "map": (0x00413184, "TAoWCombatMap"),
}
HP_OFF = 0x20                       # TCityWall / TCombatStructure hit points; 0 = destroyed
DECOR = {                           # dynamic objects still drawn on an explored hex nobody sees
    "hex": (0x0040340C, "TCombatHexagon"), "whex": (0x004036A8, "TWaterCombatHexagon"),
    "ilsh": (0x004041E4, "TCombatILTerrainShadow"), "il": (0x00404378, "TCombatILTerrain"),
    "fil": (0x00404644, "TCombatFixedILTerrain"), "wall": (0x00405008, "TCityWall"),
    "door": (0x004052AC, "TCityWallDoor"), "fire": (0x00406B24, "TCombatFire"),
    "tsh": (0x0040FB0C, "TCombatTerrainShadow"), "terr": (0x0040FCA0, "TCombatTerrain"),
    "road": (0x00410C0C, "TCombatRoad"), "item": (0x00412198, "TCItemHS"),
    "blood": (0x0041249C, "TCBloodHS"), "corpse": (0x0041261C, "TCCorpseHS"),
    "ooze": (0x0041279C, "TCOozeHS"), "flee": (0x00430EB4, "TFleeLocation"),
    "osh": (0x00431888, "TCombatObstacleShadow"), "oov": (0x00431A20, "TCombatObstacleOverlay"),
    "obst": (0x00431BB8, "TCombatObstacle"), "struct": (0x0043258C, "TCombatStructure"),
    "work": (0x004334E0, "TWorkshop"), "iso": (0x0043386C, "TIsometricCombatHexagon"),
    "town": (0x004341F8, "TTownhall"), "house": (0x00434584, "THouse"),
    "single": (0x00434E38, "TSingleCombatHexagon"), "main": (0x00435310, "TMainStructure"),
    "cview": (0x004356E0, "TCenterViewLocation"),
}

# odd-q neighbour deltas, parity = x & 1 (HSEPack walk table, as build_los_terrain.py)
DELTAS_EVEN = [(1, 0), (0, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
DELTAS_ODD = [(1, 1), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, 0)]

CAM_SITES = (0x00408DDE, 0x00409129, 0x00409D99, 0x0040B4A6)          # camera -> seen
INPUT_SITES = (0x0041E49A, 0x0041EBEF, 0x0041ECE1, 0x0041F7A0, 0x0041FCB4)  # move order, cursor -> xpl
SEEN_SITES = CAM_SITES + INPUT_SITES
AI_SITE = 0x004183B7
EX_SITES = (0x00420DBA, 0x004084B2)
DF_SITE = 0x0041BFDF
VMT_UDS = 0x00413260
RM_EXPL, RM_EXPL_VAN, RM_EXPL_NEW = 0x00424FBC, bytes.fromhex("8a55c5"), bytes.fromhex("b20190")
RM_FOG, RM_FOG_VAN, RM_FOG_NEW = 0x00424FCC, bytes.fromhex("33d2"), bytes.fromhex("b201")
ST_SITE, SETSEAT = 0x00429940, 0x0041BAB8   # TTacticalCombat.Execute: call SetSeatedCombatPlayer
RM_FOGON, RM_FOGON_VAN = 0x00424FD5, bytes.fromhex("ff9100010000")   # RandomMap: SetFogEnabled
HOVER_SITES = ((0x0041B864, 0x0041B7C0, 0x0041B884),      # (site, function start, end)
               (0x0041EFC3, 0x0041EE28, 0x0041F6E8), (0x0041F260, 0x0041EE28, 0x0041F6E8),
               (0x0041F4E6, 0x0041EE28, 0x0041F6E8), (0x0041F69A, 0x0041EE28, 0x0041F6E8))
OLD_HOVER = HOVER_SITES
HOVER_SITES = OLD_HOVER + ((0x0041F7B7, 0x0041F6E8, 0x0041FD08),)   # UpdateMoveCursor's lookup
HOVER_VAN = bytes.fromhex("ff9180000000")
HP_SITES = ((0x00405C12, 0x00405AE4, 0x00405CB2),         # TCityWall.SetHitPoints (site, start, end)
            (0x00432A4A, 0x00432930, 0x00432A5E))         # TCombatStructure.SetHitPoints
HP_VAN = bytes.fromhex("8b45f88b55fc")                    # mov eax,[ebp-8]; mov edx,[ebp-4]
CS_SITES = (0x00408480, 0x00420D96)   # call [edx+0xA4] (GetVisibilityRange) feeding the explore calls
CS_VAN = bytes.fromhex("ff92a4000000")
CALC_SLOT, CALC_ORIG = 0x00412EBC, 0x0041D678     # TCombatUnitSelectionControl VMT +8 CalculateMovePath
CANON_SLOT, CANON_ORIG = 0x00412DD8, 0x0042079C   # TTacticalCombatUnitHS VMT +0xD0 CanMoveOn
CANOVER_SLOT, CANOVER_VAN = 0x00412DDC, 0x00402A94  # VMT +0xD4 CanMoveOver (vanilla import thunk)
GM_ZONE = (0x00439800, 0x0043A400)                # build_group_move_tc.py's zone (its cave_unit)
STEP_SITE = 0x00408E5A                            # DefaultMove: call TAoWMapField.GetPlayer, next hex
FPLAYER_T, XYLGET_T = 0x00402894, 0x00401B1C
MOVETE_VMT = 0x004076D4                           # TCombatMoveTE (melee and touch moves subclass it)
PREV = [CANOVER_VAN]                              # set by main() from the live slot
FNV0, FNVP = 0x811C9DC5, 0x01000193
NOP1 = bytes([0x90])


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def jmp8(src, dst):
    return b"\xE9" + struct.pack("<i", dst - (src + 5)) + b"\x90\x90\x90"


def asm(src, va):
    """keystone, with ';' comments stripped (this keystone build rejects them)."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, va)
    return bytes(enc)


# ---------------------------------------------------------------- data
def guid_tables():
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    import pfs
    d = open(COMB_RES, "rb").read()
    want = {RC_TERR: set(BLOCK_TERR), RC_SINGLE: set(BLOCK_SINGLE), RC_MAIN: set(BLOCK_MAIN)}
    got = {RC_TERR: [], RC_SINGLE: [], RC_MAIN: []}
    seen_names = {k: set() for k in want}
    for _rid, body in pfs.parse_index(d):
        if len(body) < 4:
            continue
        cls = struct.unpack_from("<I", body, 0)[0]
        if cls not in want:
            continue
        f = pfs.parse_dir(body, top=True)
        v = f.get(6, b"")
        name = v[1:].decode("latin-1").strip() if v and v[0] == len(v) - 1 else ""
        if 1 not in f or name not in want[cls]:
            continue
        got[cls].append(struct.unpack_from("<I", f[1], 0)[0])
        seen_names[cls].add(name)
    for cls in want:
        missing = want[cls] - seen_names[cls]
        if missing:
            sys.exit("ABORT: comb_res.pfs has no %s resource named %s" % (hex(cls), sorted(missing)))
    return got


def delta_table():
    t = bytearray()
    for dl in (DELTAS_EVEN, DELTAS_ODD):
        for dx, dy in dl:
            t += struct.pack("<ii", dx, dy)
    return bytes(t)


# ---------------------------------------------------------------- routines
def routines(A, T):
    """A: routine name -> address (dummy in pass 1).  T: table addresses."""
    B = BSS
    hse = {k: (v[0] - HSE_ANCHOR) & 0xFFFFFFFF for k, v in HSE.items()}
    vm = {k: v[0] for k, v in VMT.items()}
    R = {}

    R["get_delta"] = f"""
        call {A['get_delta'] + 5:#x}
        pop  eax
        sub  eax, {A['get_delta'] + 5:#x}
        ret
    """

    # vis: eax = field, edx = map -> eax 1 seen / 0 not.  Clobbers ecx, edx.
    R["vis"] = f"""
        movsx ecx, byte ptr [edx + 0xa5]
        cmp  ecx, -1
        je   yes
        cmp  byte ptr [edx + 0xc9], 0
        je   fog
        test ecx, ecx
        je   fog
        dec  ecx
        bt   dword ptr [eax + 0x18], ecx
        jae  no
    fog:
        cmp  byte ptr [edx + 0xc8], 0
        je   yes
        cmp  byte ptr [eax + 0x1a], 0
        je   no
    yes:
        mov  eax, 1
        ret
    no:
        xor  eax, eax
        ret
    """

    # seen: GetExplored ABI (eax = field, edx = player) for the input / camera sites.
    R["seen"] = f"""
        test eax, eax
        je   no
        push eax
        call {A['get_delta']:#x}
        mov  edx, dword ptr [eax + {V_SCREEN:#x}]
        pop  eax
        test edx, edx
        je   yes
        jmp  {A['vis']:#x}
    yes:
        mov  eax, 1
        ret
    no:
        xor  eax, eax
        ret
    """

    # aispot: GetExplored ABI, called only from TCAI.EvalBattle 0x4183B7 (ebp = its frame,
    # [ebp-0xC] = the ring index 0..18 round the unit being sorted).  When the AI plays for the
    # seated combat player (Space, Auto: [TCombatData+0x31] == [map+0xEC]) a unit counts only if
    # its own hex is seen.  Otherwise vanilla inside an exploration site, 1 elsewhere.
    R["aispot"] = f"""
        push eax
        call {A['get_delta']:#x}
        mov  dword ptr [eax + {B + O_PLAN:#x}], 0
        pop  eax
        test eax, eax
        je   no
        push ebx
        push esi
        mov  esi, eax
        mov  ebx, edx
        call {A['get_delta']:#x}
        mov  ecx, dword ptr [eax + {V_SCREEN:#x}]
        test ecx, ecx
        je   van
        mov  edx, dword ptr [ecx + 0xe4]
        test edx, edx
        je   van
        mov  eax, dword ptr [edx + 0xc]
        test eax, eax
        je   kind
        mov  al, byte ptr [eax + 0x31]
        cmp  al, 0xff
        je   kind
        cmp  al, byte ptr [ecx + 0xec]
        jne  kind
        cmp  dword ptr [ebp - 0xc], 0
        jne  zero
        mov  eax, esi
        mov  edx, ecx
        pop  esi
        pop  ebx
        jmp  {A['vis']:#x}
    kind:
        cmp  byte ptr [edx + 0x40], 1
        je   van
        mov  eax, 1
        pop  esi
        pop  ebx
        ret
    van:
        mov  eax, esi
        mov  edx, ebx
        pop  esi
        pop  ebx
        jmp  {GETEXPLORED_T:#x}
    zero:
        xor  eax, eax
        pop  esi
        pop  ebx
        ret
    no:
        xor  eax, eax
        ret
    """

    # hover: replaces `call [ecx+0x80]` (field FindHS: eax = field, edx = class id).
    R["hover"] = f"""
        push eax
        push ecx
        push edx
        call {A['get_delta']:#x}
        mov  edx, dword ptr [eax + {V_SCREEN:#x}]
        mov  eax, dword ptr [esp + 8]
        test edx, edx
        je   go
        test eax, eax
        je   go
        call {A['vis']:#x}
        test eax, eax
        jne  go
        add  esp, 0xc
        xor  eax, eax
        ret
    go:
        pop  edx
        pop  ecx
        pop  eax
        jmp  dword ptr [ecx + 0x80]
    """

    # drawfog: eax = map, edx = surface.
    R["drawfog"] = f"""
        cmp  byte ptr [eax + 0xa5], 0xff
        je   skip
        jmp  {DRAWFOG_T:#x}
    skip:
        ret
    """

    # hd: eax = x1, edx = y1, [esp+4] = x2, [esp+8] = y2 -> eax = hex distance; ret 8.
    R["hd"] = f"""
        push esi
        push edi
        mov  ecx, eax
        and  ecx, 1
        mov  esi, eax
        sub  esi, ecx
        sar  esi, 1
        sub  edx, esi
        mov  esi, dword ptr [esp + 0xc]
        mov  edi, dword ptr [esp + 0x10]
        mov  ecx, esi
        and  ecx, 1
        push esi
        sub  esi, ecx
        sar  esi, 1
        sub  edi, esi
        pop  esi
        sub  eax, esi
        sub  edx, edi
        mov  ecx, eax
        add  ecx, edx
        neg  ecx
        mov  esi, eax
        sar  esi, 31
        xor  eax, esi
        sub  eax, esi
        mov  esi, edx
        sar  esi, 31
        xor  edx, esi
        sub  edx, esi
        mov  esi, ecx
        sar  esi, 31
        xor  ecx, esi
        sub  ecx, esi
        add  eax, edx
        add  eax, ecx
        sar  eax, 1
        pop  edi
        pop  esi
        ret  8
    """

    # blocker: edi = field, ebx = delta -> eax = 1 rock (lair rock, a site's "Wall" hex): blocks
    # everything; else a mask of 2 a standing wall or gate (blocks a viewer outside the walls) and
    # 4 an obstacle (houses and buildings with hit points, combat obstacles, listed trees and
    # rocks): blocks sight, and exploration only inside an exploration site; 0 nothing.  Only
    # children at a solid part count (spart).  Clobbers eax/ecx/edx.
    R["blocker"] = f"""
        push esi
        push 0
        movzx ecx, byte ptr [edi + 0xd]
        mov  esi, dword ptr [edi + 8]
        test esi, esi
        je   no
    lp:
        dec  ecx
        js   no
        mov  eax, dword ptr [esi + ecx*4]
        test eax, eax
        je   lp
        movzx edx, byte ptr [edi + 0xc]
        lea  edx, [esi + edx*4]
        movzx edx, byte ptr [edx + ecx]
        call {A['spart']:#x}
        test edx, edx
        je   lp
        mov  edx, dword ptr [eax]
        sub  edx, ebx
        cmp  edx, {vm['wall']:#x}
        je   whp
        cmp  edx, {vm['door']:#x}
        je   whp
        cmp  edx, {vm['house']:#x}
        je   hp
        cmp  edx, {vm['struct']:#x}
        je   hp
        cmp  edx, {vm['town']:#x}
        je   hp
        cmp  edx, {vm['work']:#x}
        je   hp
        cmp  edx, {vm['obst']:#x}
        je   soft
        cmp  edx, {vm['iso']:#x}
        je   yes
        cmp  edx, {vm['terr']:#x}
        je   terr
        cmp  edx, {vm['single']:#x}
        je   single
        cmp  edx, {vm['main']:#x}
        je   main
        jmp  lp
    whp:
        cmp  dword ptr [eax + {HP_OFF:#x}], 0
        je   lp
        or   dword ptr [esp], 2
        jmp  lp
    hp:
        cmp  dword ptr [eax + {HP_OFF:#x}], 0
        je   lp
    soft:
        or   dword ptr [esp], 4
        jmp  lp
    main:
        cmp  dword ptr [eax + {HP_OFF:#x}], 0
        je   lp
        mov  edx, {T['main']:#x}
        jmp  guid
    terr:
        mov  edx, {T['terr']:#x}
        jmp  guid
    single:
        mov  edx, {T['single']:#x}
    guid:
        mov  eax, dword ptr [eax + 8]
        test eax, eax
        je   lp
        mov  eax, dword ptr [eax + 0xc]
        push ecx
        add  edx, ebx
        mov  ecx, dword ptr [edx]
    g:
        test ecx, ecx
        je   gno
        cmp  eax, dword ptr [edx + ecx*4]
        je   gyes
        dec  ecx
        jmp  g
    gno:
        pop  ecx
        jmp  lp
    gyes:
        sub  edx, ebx
        pop  ecx
        cmp  edx, {T['single']:#x}
        jne  soft
    yes:
        add  esp, 4
        mov  eax, 1
        pop  esi
        ret
    no:
        pop  eax
        pop  esi
        ret
    """

    # iswall: edi = field, ebx = delta -> eax = 1 if it holds a city wall or gate, standing or not.
    R["iswall"] = f"""
        push esi
        movzx ecx, byte ptr [edi + 0xd]
        mov  esi, dword ptr [edi + 8]
        test esi, esi
        je   no
    lp:
        dec  ecx
        js   no
        mov  eax, dword ptr [esi + ecx*4]
        test eax, eax
        je   lp
        movzx edx, byte ptr [edi + 0xc]
        lea  edx, [esi + edx*4]
        movzx edx, byte ptr [edx + ecx]
        call {A['spart']:#x}
        test edx, edx
        je   lp
        mov  edx, dword ptr [eax]
        sub  edx, ebx
        cmp  edx, {vm['wall']:#x}
        je   yes
        cmp  edx, {vm['door']:#x}
        je   yes
        jmp  lp
    yes:
        mov  eax, 1
        pop  esi
        ret
    no:
        xor  eax, eax
        pop  esi
        ret
    """

    # fld: eax = x, edx = y, ebx = delta -> eax = worldflood's field or 0 off the grid.  Clobbers ecx.
    R["fld"] = f"""
        test eax, eax
        js   no
        test edx, edx
        js   no
        cmp  eax, dword ptr [ebx + {B + O_IW:#x}]
        jge  no
        cmp  edx, dword ptr [ebx + {B + O_IH:#x}]
        jge  no
        mov  ecx, dword ptr [ebx + {B + O_ILVL:#x}]
        mov  ecx, dword ptr [ecx + 0x74]
        mov  eax, dword ptr [ecx + eax*4]
        mov  ecx, dword ptr [ebx + {B + O_ILVL:#x}]
        mov  ecx, dword ptr [ecx + 0x78]
        add  eax, dword ptr [ecx + edx*4]
        ret
    no:
        xor  eax, eax
        ret
    """

    # relax: esi = x, edi = y -> eax = 1 if this hex just took the current mark from a neighbour.
    # A hex with bit 0x08 never takes a mark, one with bit 0x10 not while the wall-stop flag is set,
    # the border not while the stop flag is set.
    R["relax"] = f"""
        push ebp
        mov  eax, esi
        mov  edx, edi
        call {A['fld']:#x}
        test eax, eax
        je   no
        mov  ebp, eax
        mov  cl, byte ptr [ebx + {B + O_MARK:#x}]
        test byte ptr [ebp + {F_FLAGS:#x}], cl
        jne  no
        test byte ptr [ebp + {F_FLAGS:#x}], 8
        jne  no
        cmp  dword ptr [ebx + {B + O_WSTOP:#x}], 0
        je   nw
        test byte ptr [ebp + {F_FLAGS:#x}], 0x10
        jne  no
    nw:
        cmp  dword ptr [ebx + {B + O_STOP:#x}], 0
        je   nb
        cmp  byte ptr [ebp + 0x14], {BORDER}
        je   no
    nb:
        push 0
    nl:
        mov  eax, esi
        and  eax, 1
        imul eax, eax, 0x30
        mov  ecx, dword ptr [esp]
        lea  eax, [eax + ecx*8]
        add  eax, ebx
        mov  edx, dword ptr [eax + {T_DELTA + 4:#x}]
        mov  eax, dword ptr [eax + {T_DELTA:#x}]
        add  eax, esi
        add  edx, edi
        call {A['fld']:#x}
        test eax, eax
        je   nn
        mov  cl, byte ptr [ebx + {B + O_MARK:#x}]
        test byte ptr [eax + {F_FLAGS:#x}], cl
        jne  hit
    nn:
        inc  dword ptr [esp]
        cmp  dword ptr [esp], 6
        jl   nl
        add  esp, 4
    no:
        xor  eax, eax
        pop  ebp
        ret
    hit:
        add  esp, 4
        mov  cl, byte ptr [ebx + {B + O_MARK:#x}]
        or   byte ptr [ebp + {F_FLAGS:#x}], cl
        mov  eax, 1
        pop  ebp
        ret
    """

    # sweep: eax = 1 forward / 0 backward over the grid -> eax = 1 if any hex took the mark.
    R["sweep"] = f"""
        push esi
        push edi
        push ebp
        xor  ebp, ebp
        test eax, eax
        je   bk
        xor  edi, edi
    fy:
        cmp  edi, dword ptr [ebx + {B + O_IH:#x}]
        jge  done
        xor  esi, esi
    fx:
        cmp  esi, dword ptr [ebx + {B + O_IW:#x}]
        jge  fyn
        call {A['relax']:#x}
        or   ebp, eax
        inc  esi
        jmp  fx
    fyn:
        inc  edi
        jmp  fy
    bk:
        mov  edi, dword ptr [ebx + {B + O_IH:#x}]
        dec  edi
    byl:
        test edi, edi
        js   done
        mov  esi, dword ptr [ebx + {B + O_IW:#x}]
        dec  esi
    bxl:
        test esi, esi
        js   byn
        call {A['relax']:#x}
        or   ebp, eax
        dec  esi
        jmp  bxl
    byn:
        dec  edi
        jmp  byl
    done:
        mov  eax, ebp
        pop  ebp
        pop  edi
        pop  esi
        ret
    """

    # flood: eax = mark bit, edx = stop at the border -> sweeps until no hex changes.
    R["flood"] = f"""
        push esi
        mov  dword ptr [ebx + {B + O_MARK:#x}], eax
        mov  dword ptr [ebx + {B + O_STOP:#x}], edx
        mov  esi, {PASS_CAP}
    fl:
        mov  eax, 1
        call {A['sweep']:#x}
        push eax
        xor  eax, eax
        call {A['sweep']:#x}
        pop  edx
        or   eax, edx
        je   xit
        dec  esi
        jne  fl
    xit:
        pop  esi
        ret
    """

    # inside_build: eax = map.  Bit 0x01 of [field+0x1B] = inside the walls, on every hex of
    # level 0: reached from the centre without crossing a wall, gate or the border (mark 0x10),
    # or not reachable from the border without crossing a wall or gate (mark 0x04 misses it), or a
    # wall or gate hex itself (0x08).  Bit 0x02 is the engine's and stays as it was.
    R["inside_build"] = f"""
        push ebx
        push esi
        push edi
        push ebp
        mov  ebp, eax
        call {A['get_delta']:#x}
        mov  ebx, eax
        xor  edx, edx
        mov  eax, dword ptr [ebp + 0x10]
        call {GETMAPLEVEL_T:#x}
        test eax, eax
        je   xit
        mov  ecx, dword ptr [eax + 0xc]
        mov  edx, dword ptr [eax + 0x10]
        test ecx, ecx
        jle  xit
        test edx, edx
        jle  xit
        mov  esi, ecx
        imul esi, edx
        cmp  esi, {MAXCELLS}
        ja   xit
        mov  dword ptr [ebx + {B + O_ILVL:#x}], eax
        mov  dword ptr [ebx + {B + O_IW:#x}], ecx
        mov  dword ptr [ebx + {B + O_IH:#x}], edx
        mov  dword ptr [ebx + {B + O_WSTOP:#x}], 0
        xor  ebp, ebp
    ay:
        cmp  ebp, dword ptr [ebx + {B + O_IH:#x}]
        jge  ad
        xor  esi, esi
    ax_:
        cmp  esi, dword ptr [ebx + {B + O_IW:#x}]
        jge  an
        mov  eax, esi
        mov  edx, ebp
        call {A['fld']:#x}
        mov  edi, eax
        and  byte ptr [edi + {F_FLAGS:#x}], 0xe2
        call {A['iswall']:#x}
        test eax, eax
        je   ac
        or   byte ptr [edi + {F_FLAGS:#x}], 8
    ac:
        cmp  byte ptr [edi + 0x14], {BORDER}
        jne  ac2
        test byte ptr [edi + {F_FLAGS:#x}], 8
        jne  ac2
        or   byte ptr [edi + {F_FLAGS:#x}], 4
    ac2:
        inc  esi
        jmp  ax_
    an:
        inc  ebp
        jmp  ay
    ad:
        mov  eax, dword ptr [ebx + {B + O_IW:#x}]
        sar  eax, 1
        mov  edx, dword ptr [ebx + {B + O_IH:#x}]
        sar  edx, 1
        call {A['fld']:#x}
        test byte ptr [eax + {F_FLAGS:#x}], 8
        jne  edge
        cmp  byte ptr [eax + 0x14], {BORDER}
        je   edge
        or   byte ptr [eax + {F_FLAGS:#x}], 0x10
        mov  eax, 0x10
        mov  edx, 1
        call {A['flood']:#x}
    edge:
        mov  eax, 4
        xor  edx, edx
        call {A['flood']:#x}
        xor  ebp, ebp
    fy:
        cmp  ebp, dword ptr [ebx + {B + O_IH:#x}]
        jge  xit
        xor  esi, esi
    fx:
        cmp  esi, dword ptr [ebx + {B + O_IW:#x}]
        jge  fn
        mov  eax, esi
        mov  edx, ebp
        call {A['fld']:#x}
        mov  cl, byte ptr [eax + {F_FLAGS:#x}]
        test cl, 0x18
        jne  inside
        test cl, 4
        je   inside
        and  cl, 0xe2
        jmp  wr
    inside:
        and  cl, 0xe2
        or   cl, 1
    wr:
        mov  byte ptr [eax + {F_FLAGS:#x}], cl
        inc  esi
        jmp  fx
    fn:
        inc  ebp
        jmp  fy
    xit:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """

    # fogon: replaces RandomMap's `call [ecx+0x100]` (SetFogEnabled; eax = map, dl = 1): the
    # template and its walls are loaded, no unit is placed yet.
    R["fogon"] = f"""
        pushad
        call {A['inside_build']:#x}
        popad
        jmp  dword ptr [ecx + 0x100]
    """

    # unitfield: eax = combat object, ebx = delta -> eax = the hex of a live unit, else 0.
    # Preserves esi/edi/ebp.
    R["unitfield"] = f"""
        push esi
        mov  esi, eax
        test eax, eax
        je   no
        mov  edx, dword ptr [ebx + {IAT_TCOMBATUNIT:#x}]
        call {A['isclass']:#x}
        test al, al
        je   no
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   no
        mov  eax, dword ptr [esi + 0x60]
        test eax, eax
        je   no
        mov  eax, dword ptr [eax + 4]
        pop  esi
        ret
    no:
        xor  eax, eax
        pop  esi
        ret
    """

    # oneplayer: eax = AoW player id (1..31), edx = TCombatData, ecx = object count, ebx = delta.
    # Flood from every live unit of that player (mark bit 0x04), stopped by solid blockers
    # ([field+0x1B] bit 0x08), by standing walls and gates (bit 0x10) unless one of its units stands
    # inside the walls, and by the border; explore what the flood reached plus the blockers
    # touching it.  Bit 0x02 is the engine's "a unit here" (GetPlayer): never written.
    R["oneplayer"] = f"""
        push esi
        push edi
        push ebp
        sub  esp, 0x14
        mov  dword ptr [esp + 0x10], 0
        mov  dword ptr [esp], eax
        mov  dword ptr [esp + 4], edx
        mov  dword ptr [esp + 8], ecx
        mov  dword ptr [esp + 0xc], 0
    sd:
        mov  eax, dword ptr [esp + 0xc]
        cmp  eax, dword ptr [esp + 8]
        jge  sdd
        mov  edx, eax
        mov  eax, dword ptr [esp + 4]
        call {A['cd_objects']:#x}
        mov  edi, eax
        call {A['unitfield']:#x}
        test eax, eax
        je   sn
        mov  esi, eax
        mov  eax, edi
        call {GETPLAYER_T:#x}
        movzx eax, al
        cmp  eax, dword ptr [esp]
        jne  sn
        or   byte ptr [esi + {F_FLAGS:#x}], 4
        test byte ptr [esi + {F_FLAGS:#x}], 1
        je   sn
        mov  dword ptr [esp + 0x10], 1
    sn:
        inc  dword ptr [esp + 0xc]
        jmp  sd
    sdd:
        xor  eax, eax
        cmp  dword ptr [esp + 0x10], 0
        sete al
        mov  dword ptr [ebx + {B + O_WSTOP:#x}], eax
        mov  eax, 4
        mov  edx, 1
        call {A['flood']:#x}
        mov  ecx, dword ptr [esp]
        dec  ecx
        mov  eax, 1
        shl  eax, cl
        mov  dword ptr [esp + 0xc], eax
        xor  ebp, ebp
    ey:
        cmp  ebp, dword ptr [ebx + {B + O_IH:#x}]
        jge  ed
        xor  esi, esi
    ex:
        cmp  esi, dword ptr [ebx + {B + O_IW:#x}]
        jge  en
        mov  eax, esi
        mov  edx, ebp
        call {A['fld']:#x}
        mov  edi, eax
        test byte ptr [edi + {F_FLAGS:#x}], 4
        jne  mark
        test byte ptr [edi + {F_FLAGS:#x}], 8
        jne  face
        cmp  dword ptr [ebx + {B + O_WSTOP:#x}], 0
        je   ec
        test byte ptr [edi + {F_FLAGS:#x}], 0x10
        je   ec
    face:
        push 0
    nl:
        mov  eax, esi
        and  eax, 1
        imul eax, eax, 0x30
        mov  ecx, dword ptr [esp]
        lea  eax, [eax + ecx*8]
        add  eax, ebx
        mov  edx, dword ptr [eax + {T_DELTA + 4:#x}]
        mov  eax, dword ptr [eax + {T_DELTA:#x}]
        add  eax, esi
        add  edx, ebp
        call {A['fld']:#x}
        test eax, eax
        je   nn
        test byte ptr [eax + {F_FLAGS:#x}], 4
        jne  nhit
    nn:
        inc  dword ptr [esp]
        cmp  dword ptr [esp], 6
        jl   nl
        add  esp, 4
        jmp  ec
    nhit:
        add  esp, 4
    mark:
        mov  eax, dword ptr [esp + 0xc]
        or   dword ptr [edi + 0x18], eax
    ec:
        inc  esi
        jmp  ex
    en:
        inc  ebp
        jmp  ey
    ed:
        xor  ebp, ebp
    cy:
        cmp  ebp, dword ptr [ebx + {B + O_IH:#x}]
        jge  xit
        xor  esi, esi
    cx_:
        cmp  esi, dword ptr [ebx + {B + O_IW:#x}]
        jge  cn
        mov  eax, esi
        mov  edx, ebp
        call {A['fld']:#x}
        and  byte ptr [eax + {F_FLAGS:#x}], 0xfb
        inc  esi
        jmp  cx_
    cn:
        inc  ebp
        jmp  cy
    xit:
        add  esp, 0x14
        pop  ebp
        pop  edi
        pop  esi
        ret
    """

    # worldflood: eax = map.  At battle start outside exploration sites, each player explores
    # everything a flood from its units reaches without crossing a sight blocker or the border.
    # Scratch 0x04/0x08/0x10 are cleared after; 0x01, the engine's 0x02 and 0x20-0x80 are kept.
    R["worldflood"] = f"""
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, 0x18
        mov  dword ptr [esp + 0xc], eax
        mov  ebp, eax
        call {A['get_delta']:#x}
        mov  ebx, eax
        mov  eax, dword ptr [ebp + 0xe4]
        test eax, eax
        je   xit
        cmp  byte ptr [eax + 0x40], 1
        je   xit
        mov  eax, dword ptr [eax + 0xc]
        test eax, eax
        je   xit
        mov  dword ptr [esp], eax
        call {A['cd_count']:#x}
        mov  dword ptr [esp + 4], eax
        xor  edx, edx
        mov  eax, dword ptr [ebp + 0x10]
        call {GETMAPLEVEL_T:#x}
        test eax, eax
        je   xit
        mov  ecx, dword ptr [eax + 0xc]
        mov  edx, dword ptr [eax + 0x10]
        test ecx, ecx
        jle  xit
        test edx, edx
        jle  xit
        mov  esi, ecx
        imul esi, edx
        cmp  esi, {MAXCELLS}
        ja   xit
        mov  dword ptr [ebx + {B + O_ILVL:#x}], eax
        mov  dword ptr [ebx + {B + O_IW:#x}], ecx
        mov  dword ptr [ebx + {B + O_IH:#x}], edx
        mov  dword ptr [ebx + {B + O_XPL:#x}], 1
        call {A['bmap_build']:#x}
        xor  ebp, ebp
    ay:
        cmp  ebp, dword ptr [ebx + {B + O_IH:#x}]
        jge  ad
        xor  esi, esi
    ax_:
        cmp  esi, dword ptr [ebx + {B + O_IW:#x}]
        jge  an
        mov  eax, esi
        mov  edx, ebp
        call {A['fld']:#x}
        mov  edi, eax
        and  byte ptr [edi + {F_FLAGS:#x}], 0xe3
        mov  eax, ebp
        imul eax, dword ptr [ebx + {B + O_BW:#x}]
        add  eax, esi
        bt   dword ptr [ebx + {B + O_BMAP:#x}], eax
        jae  ac
        or   byte ptr [edi + {F_FLAGS:#x}], 8
    ac:
        bt   dword ptr [ebx + {B + O_WMAP:#x}], eax
        jae  ac2
        or   byte ptr [edi + {F_FLAGS:#x}], 0x10
    ac2:
        inc  esi
        jmp  ax_
    an:
        inc  ebp
        jmp  ay
    ad:
        mov  dword ptr [esp + 8], 0
        mov  dword ptr [esp + 0x10], 0
    pl:
        mov  eax, dword ptr [esp + 0x10]
        cmp  eax, dword ptr [esp + 4]
        jge  fin
        mov  edx, eax
        mov  eax, dword ptr [esp]
        call {A['cd_objects']:#x}
        mov  edi, eax
        call {A['unitfield']:#x}
        test eax, eax
        je   pn
        mov  eax, edi
        call {GETPLAYER_T:#x}
        movzx eax, al
        test eax, eax
        je   pn
        cmp  eax, 31
        ja   pn
        bt   dword ptr [esp + 8], eax
        jb   pn
        bts  dword ptr [esp + 8], eax
        mov  edx, dword ptr [esp]
        mov  ecx, dword ptr [esp + 4]
        call {A['oneplayer']:#x}
    pn:
        inc  dword ptr [esp + 0x10]
        jmp  pl
    fin:
        call {A['wclose']:#x}
        xor  ebp, ebp
    fy:
        cmp  ebp, dword ptr [ebx + {B + O_IH:#x}]
        jge  fd
        xor  esi, esi
    fx:
        cmp  esi, dword ptr [ebx + {B + O_IW:#x}]
        jge  fn
        mov  eax, esi
        mov  edx, ebp
        call {A['fld']:#x}
        and  byte ptr [eax + {F_FLAGS:#x}], 0xe3
        inc  esi
        jmp  fx
    fn:
        inc  ebp
        jmp  fy
    fd:
        mov  eax, dword ptr [esp + 0xc]
        mov  byte ptr [eax + 0x30], 1
        mov  dword ptr [ebx + {B + O_SIG:#x}], 0
    xit:
        add  esp, 0x18
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """

    # startflood: replaces TTacticalCombat.Execute's `call SetSeatedCombatPlayer` (eax = map,
    # dl = seat): the map, its decorations and every unit are placed by now.
    R["startflood"] = f"""
        push eax
        push edx
        call {SETSEAT:#x}
        pop  edx
        pop  eax
        pushad
        call {A['worldflood']:#x}
        popad
        ret
    """

    # expl: eax = field, edx = map -> eax 1 if the seated player has explored it.  Clobbers ecx.
    R["expl"] = f"""
        movsx ecx, byte ptr [edx + 0xa5]
        cmp  ecx, -1
        je   yes
        cmp  byte ptr [edx + 0xc9], 0
        je   yes
        test ecx, ecx
        je   yes
        dec  ecx
        bt   dword ptr [eax + 0x18], ecx
        jae  no
    yes:
        mov  eax, 1
        ret
    no:
        xor  eax, eax
        ret
    """

    # decor: eax = field, edx = visible list, ebx = delta.  Adds the field's dynamic objects whose
    # class is a map decoration (T_DECOR) -- an explored hex nobody sees keeps its corpses, walls,
    # trees, fire and dropped items, never its units, unit shadows or effects.
    R["decor"] = f"""
        push esi
        push edi
        push ebp
        mov  edi, eax
        mov  ebp, edx
        movzx esi, byte ptr [edi + 0xd]
        dec  esi
    dl_:
        movzx eax, byte ptr [edi + 0xe]
        cmp  esi, eax
        jl   done
        mov  eax, dword ptr [edi + 8]
        mov  eax, dword ptr [eax + esi*4]
        test eax, eax
        je   dn
        mov  edx, dword ptr [eax]
        sub  edx, ebx
        mov  ecx, dword ptr [ebx + {T['decor']:#x}]
    tl:
        test ecx, ecx
        je   dn
        cmp  edx, dword ptr [ebx + ecx*4 + {T['decor']:#x}]
        je   add_
        dec  ecx
        jmp  tl
    add_:
        mov  edx, ebp
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xf0]
    dn:
        dec  esi
        jmp  dl_
    done:
        pop  ebp
        pop  edi
        pop  esi
        ret
    """

    # bmap_build: eax = level, ebx = delta -> eax = hash of the blocking cells (0 if no bitmap).
    # Obstacles (blocker mask 4) go into the solid bitmap unless [O_XPL] is set (exploration in
    # a world battle): then they are left out, and a standing wall under one stays a wall.
    R["bmap_build"] = f"""
        push esi
        push edi
        push ebp
        sub  esp, 0x10
        mov  ebp, eax
        mov  dword ptr [ebx + {B + O_LVL:#x}], eax
        mov  dword ptr [ebx + {B + O_NB:#x}], 0
        mov  dword ptr [ebx + {B + O_BW:#x}], 0
        mov  ecx, dword ptr [ebp + 0xc]
        mov  edx, dword ptr [ebp + 0x10]
        test ecx, ecx
        jle  fail
        test edx, edx
        jle  fail
        mov  eax, ecx
        imul eax, edx
        cmp  eax, {MAXCELLS}
        ja   fail
        mov  dword ptr [ebx + {B + O_BW:#x}], ecx
        mov  dword ptr [ebx + {B + O_BH:#x}], edx
        mov  dword ptr [esp + 0xc], ecx
        lea  edi, [ebx + {B + O_BMAP:#x}]
        xor  eax, eax
        mov  ecx, {MAXCELLS // 32}
        rep stosd
        lea  edi, [ebx + {B + O_WMAP:#x}]
        mov  ecx, {MAXCELLS // 32}
        rep stosd
        mov  esi, {FNV0:#x}
        mov  dword ptr [esp + 8], 0
        mov  dword ptr [esp + 4], 0
    yl:
        mov  eax, dword ptr [esp + 4]
        cmp  eax, dword ptr [ebx + {B + O_BH:#x}]
        jge  done
        mov  dword ptr [esp], 0
    xl:
        mov  eax, dword ptr [esp]
        cmp  eax, dword ptr [esp + 0xc]
        jge  yn
        mov  edx, dword ptr [ebp + 0x74]
        mov  edi, dword ptr [edx + eax*4]
        mov  edx, dword ptr [ebp + 0x78]
        mov  eax, dword ptr [esp + 4]
        add  edi, dword ptr [edx + eax*4]
        call {A['blocker']:#x}
        test eax, eax
        je   nx
        mov  ecx, dword ptr [esp + 8]
        test al, 1
        jne  sol
        test al, 4
        je   wl
        cmp  dword ptr [ebx + {B + O_XPL:#x}], 0
        je   sol
        test al, 2
        je   nx
    wl:
        bts  dword ptr [ebx + {B + O_WMAP:#x}], ecx
        mov  eax, 2
        jmp  cnt
    sol:
        bts  dword ptr [ebx + {B + O_BMAP:#x}], ecx
        mov  eax, 1
    cnt:
        inc  dword ptr [ebx + {B + O_NB:#x}]
        shl  eax, 16
        or   eax, ecx
        xor  esi, eax
        imul esi, esi, {FNVP:#x}
    nx:
        inc  dword ptr [esp + 8]
        inc  dword ptr [esp]
        jmp  xl
    yn:
        inc  dword ptr [esp + 4]
        jmp  yl
    done:
        mov  eax, esi
        jmp  xit
    fail:
        xor  eax, eax
    xit:
        add  esp, 0x10
        pop  ebp
        pop  edi
        pop  esi
        ret
    """

    # los: [esp+4] cx, +8 cy, +0xC tx, +0x10 ty; ebx = delta -> eax 1 clear / 0 blocked; ret 0x10.
    R["los"] = f"""
        cmp  dword ptr [ebx + {B + O_NB:#x}], 0
        jne  go
        mov  eax, 1
        ret  0x10
    go:
        push esi
        push edi
        push ebp
        sub  esp, 0x20
        mov  eax, dword ptr [esp + 0x38]
        mov  ecx, eax
        and  ecx, 1
        sub  eax, ecx
        sar  eax, 1
        mov  ecx, dword ptr [esp + 0x3c]
        sub  ecx, eax
        mov  dword ptr [esp + 0x18], ecx
        mov  dword ptr [esp], 0
    init:
        mov  esi, dword ptr [esp + 0x30]
        mov  edi, dword ptr [esp + 0x34]
        mov  dword ptr [esp + 4], {STEP_CAP}
    step:
        cmp  esi, dword ptr [esp + 0x38]
        jne  walk
        cmp  edi, dword ptr [esp + 0x3c]
        je   clear
    walk:
        dec  dword ptr [esp + 4]
        js   clear
        mov  dword ptr [esp + 8], 0x7fffffff
        mov  dword ptr [esp + 0x14], 0
    side:
        mov  eax, esi
        and  eax, 1
        imul eax, eax, 0x30
        mov  ecx, dword ptr [esp + 0x14]
        lea  eax, [eax + ecx*8]
        add  eax, ebx
        mov  edx, dword ptr [eax + {T_DELTA + 4:#x}]
        mov  eax, dword ptr [eax + {T_DELTA:#x}]
        add  eax, esi
        add  edx, edi
        push eax
        push edx
        mov  ecx, eax
        and  ecx, 1
        mov  ebp, eax
        sub  ebp, ecx
        sar  ebp, 1
        sub  edx, ebp
        sub  eax, dword ptr [esp + 0x40]
        sub  edx, dword ptr [esp + 0x20]
        mov  ecx, eax
        add  ecx, edx
        neg  ecx
        mov  ebp, eax
        sar  ebp, 31
        xor  eax, ebp
        sub  eax, ebp
        mov  ebp, edx
        sar  ebp, 31
        xor  edx, ebp
        sub  edx, ebp
        mov  ebp, ecx
        sar  ebp, 31
        xor  ecx, ebp
        sub  ecx, ebp
        add  eax, edx
        add  eax, ecx
        sar  eax, 1
        pop  edx
        pop  ecx
        cmp  eax, dword ptr [esp + 8]
        jl   take
        jg   nside
        cmp  dword ptr [esp], 0
        je   nside
    take:
        mov  dword ptr [esp + 8], eax
        mov  dword ptr [esp + 0xc], ecx
        mov  dword ptr [esp + 0x10], edx
    nside:
        inc  dword ptr [esp + 0x14]
        cmp  dword ptr [esp + 0x14], 6
        jl   side
        mov  esi, dword ptr [esp + 0xc]
        mov  edi, dword ptr [esp + 0x10]
        cmp  esi, dword ptr [esp + 0x38]
        jne  mid
        cmp  edi, dword ptr [esp + 0x3c]
        je   clear
    mid:
        test esi, esi
        js   step
        test edi, edi
        js   step
        cmp  esi, dword ptr [ebx + {B + O_BW:#x}]
        jge  step
        cmp  edi, dword ptr [ebx + {B + O_BH:#x}]
        jge  step
        mov  eax, edi
        imul eax, dword ptr [ebx + {B + O_BW:#x}]
        add  eax, esi
        bt   dword ptr [ebx + {B + O_BMAP:#x}], eax
        jb   fail
        cmp  dword ptr [ebx + {B + O_VIN:#x}], 0
        jne  step
        bt   dword ptr [ebx + {B + O_WMAP:#x}], eax
        jb   fail
        jmp  step
    clear:
        mov  eax, 1
        jmp  xit
    fail:
        cmp  dword ptr [esp], 0
        jne  blocked
        mov  dword ptr [esp], 1
        jmp  init
    blocked:
        xor  eax, eax
    xit:
        add  esp, 0x20
        pop  ebp
        pop  edi
        pop  esi
        ret  0x10
    """

    # fill: [esp+4] cx, +8 cy, +0xC R, +0x10 mode (0 count, 1 explore), +0x14 mask; ebx = delta.
    # -> eax = hexes newly explored (mode 1).  ret 0x14.
    R["fill"] = f"""
        push esi
        push edi
        push ebp
        sub  esp, 0x18
        mov  dword ptr [esp + 0xc], 0
        cmp  dword ptr [ebx + {B + O_BW:#x}], 0
        je   xit
        mov  eax, dword ptr [ebx + {B + O_LVL:#x}]
        mov  dword ptr [esp + 0x10], eax
        mov  dword ptr [ebx + {B + O_VIN:#x}], 0
        mov  eax, dword ptr [esp + 0x28]
        mov  edx, dword ptr [esp + 0x2c]
        test eax, eax
        js   v0
        test edx, edx
        js   v0
        cmp  eax, dword ptr [ebx + {B + O_BW:#x}]
        jge  v0
        cmp  edx, dword ptr [ebx + {B + O_BH:#x}]
        jge  v0
        mov  ecx, dword ptr [esp + 0x10]
        mov  ecx, dword ptr [ecx + 0x74]
        mov  eax, dword ptr [ecx + eax*4]
        mov  ecx, dword ptr [esp + 0x10]
        mov  ecx, dword ptr [ecx + 0x78]
        add  eax, dword ptr [ecx + edx*4]
        movzx eax, byte ptr [eax + {F_FLAGS:#x}]
        and  eax, 1
        mov  dword ptr [ebx + {B + O_VIN:#x}], eax
    v0:
        mov  eax, dword ptr [esp + 0x28]
        sub  eax, dword ptr [esp + 0x30]
        jns  a1
        xor  eax, eax
    a1:
        mov  dword ptr [esp + 0x14], eax
        mov  eax, dword ptr [esp + 0x28]
        add  eax, dword ptr [esp + 0x30]
        mov  ecx, dword ptr [ebx + {B + O_BW:#x}]
        dec  ecx
        cmp  eax, ecx
        jle  a2
        mov  eax, ecx
    a2:
        mov  dword ptr [esp], eax
        mov  ecx, dword ptr [esp + 0x30]
        lea  ecx, [ecx*2 + 1]
        mov  eax, dword ptr [esp + 0x2c]
        sub  eax, ecx
        jns  a3
        xor  eax, eax
    a3:
        mov  dword ptr [esp + 4], eax
        mov  eax, dword ptr [esp + 0x2c]
        add  eax, ecx
        mov  ecx, dword ptr [ebx + {B + O_BH:#x}]
        dec  ecx
        cmp  eax, ecx
        jle  a4
        mov  eax, ecx
    a4:
        mov  dword ptr [esp + 8], eax
    xl:
        mov  esi, dword ptr [esp + 0x14]
        cmp  esi, dword ptr [esp]
        jg   xit
        mov  edi, dword ptr [esp + 4]
    yl:
        cmp  edi, dword ptr [esp + 8]
        jg   xn
        mov  eax, dword ptr [esp + 0x2c]
        push eax
        mov  eax, dword ptr [esp + 0x2c]
        push eax
        mov  eax, esi
        mov  edx, edi
        call {A['hd']:#x}
        cmp  eax, dword ptr [esp + 0x30]
        jg   yn
        push edi
        push esi
        mov  eax, dword ptr [esp + 0x34]
        push eax
        mov  eax, dword ptr [esp + 0x34]
        push eax
        call {A['los']:#x}
        test eax, eax
        je   yn
        mov  ecx, dword ptr [esp + 0x10]
        mov  edx, dword ptr [ecx + 0x74]
        mov  eax, dword ptr [edx + esi*4]
        mov  edx, dword ptr [ecx + 0x78]
        add  eax, dword ptr [edx + edi*4]
        cmp  dword ptr [esp + 0x34], 0
        jne  ex
        cmp  byte ptr [eax + 0x1a], 0xff
        je   yn
        inc  byte ptr [eax + 0x1a]
        jmp  yn
    ex:
        mov  ecx, dword ptr [esp + 0x38]
        test dword ptr [eax + 0x18], ecx
        jne  yn
        or   dword ptr [eax + 0x18], ecx
        inc  dword ptr [esp + 0xc]
    yn:
        inc  edi
        jmp  yl
    xn:
        inc  dword ptr [esp + 0x14]
        jmp  xl
    xit:
        mov  eax, dword ptr [esp + 0xc]
        add  esp, 0x18
        pop  ebp
        pop  edi
        pop  esi
        ret  0x14
    """

    # fog_update: eax = map.  Recounts [field+0x1A] when the signature changes.
    R["fog_update"] = f"""
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, 0x10
        mov  ebp, eax
        call {A['get_delta']:#x}
        mov  ebx, eax
        mov  edx, dword ptr [ebp + 0x88]
        mov  eax, dword ptr [ebp + 0x10]
        call {GETMAPLEVEL_T:#x}
        test eax, eax
        je   xit
        mov  esi, eax
        mov  dword ptr [ebx + {B + O_XPL:#x}], 0
        call {A['bmap_build']:#x}
        mov  edi, {FNV0:#x}
        xor  edi, eax
        imul edi, edi, {FNVP:#x}
        xor  edi, ebp
        imul edi, edi, {FNVP:#x}
        xor  edi, esi
        imul edi, edi, {FNVP:#x}
        movsx eax, byte ptr [ebp + 0xa5]
        mov  dword ptr [esp + 0xc], eax
        xor  edi, eax
        imul edi, edi, {FNVP:#x}
        cmp  eax, dword ptr [ebx + {B + O_SEAT:#x}]
        je   seatok
        mov  dword ptr [ebx + {B + O_SEAT:#x}], eax
        mov  eax, ebp
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xd8]
    seatok:
        mov  dword ptr [ebx + {B + O_NU:#x}], 0
        mov  eax, dword ptr [ebp + 0xe4]
        test eax, eax
        je   sig
        mov  eax, dword ptr [eax + 0xc]
        test eax, eax
        je   sig
        mov  dword ptr [esp + 8], eax
        call {A['cd_count']:#x}
        mov  dword ptr [esp + 4], eax
        mov  dword ptr [esp], 0
    lp:
        mov  eax, dword ptr [esp]
        cmp  eax, dword ptr [esp + 4]
        jge  sig
        mov  edx, eax
        mov  eax, dword ptr [esp + 8]
        call {A['cd_objects']:#x}
        test eax, eax
        je   nx
        mov  esi, eax
        mov  edx, dword ptr [ebx + {IAT_TCOMBATUNIT:#x}]
        call {A['isclass']:#x}
        test al, al
        je   nx
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   nx
        mov  eax, dword ptr [esi + 0x60]
        test eax, eax
        je   nx
        mov  eax, dword ptr [eax + 4]
        test eax, eax
        je   nx
        mov  eax, esi
        call {GETPLAYER_T:#x}
        movsx eax, al
        cmp  eax, dword ptr [esp + 0xc]
        jne  nx
        mov  eax, esi
        call {A['csight']:#x}
        test eax, eax
        jns  r1
        xor  eax, eax
    r1:
        cmp  eax, {RMAX}
        jle  r2
        mov  eax, {RMAX}
    r2:
        shl  eax, 16
        mov  edx, dword ptr [esi + 0x60]
        mov  edx, dword ptr [edx + 4]
        movzx ecx, byte ptr [edx + 0x11]
        shl  ecx, 8
        or   eax, ecx
        movzx ecx, byte ptr [edx + 0x10]
        or   eax, ecx
        xor  edi, eax
        imul edi, edi, {FNVP:#x}
        mov  ecx, dword ptr [ebx + {B + O_NU:#x}]
        cmp  ecx, {MAXU}
        jge  nx
        mov  dword ptr [ebx + ecx*4 + {B + O_UNITS:#x}], eax
        inc  dword ptr [ebx + {B + O_NU:#x}]
    nx:
        inc  dword ptr [esp]
        jmp  lp
    sig:
        cmp  edi, dword ptr [ebx + {B + O_SIG:#x}]
        je   xit
        mov  dword ptr [ebx + {B + O_SIG:#x}], edi
        cmp  dword ptr [ebx + {B + O_BW:#x}], 0
        je   xit
        mov  ebp, dword ptr [ebx + {B + O_LVL:#x}]
        xor  esi, esi
    zy:
        cmp  esi, dword ptr [ebx + {B + O_BH:#x}]
        jge  fl
        xor  edi, edi
    zx:
        cmp  edi, dword ptr [ebx + {B + O_BW:#x}]
        jge  zyn
        mov  edx, dword ptr [ebp + 0x74]
        mov  eax, dword ptr [edx + edi*4]
        mov  edx, dword ptr [ebp + 0x78]
        add  eax, dword ptr [edx + esi*4]
        mov  byte ptr [eax + 0x1a], 0
        inc  edi
        jmp  zx
    zyn:
        inc  esi
        jmp  zy
    fl:
        xor  esi, esi
    fu:
        cmp  esi, dword ptr [ebx + {B + O_NU:#x}]
        jge  xit
        mov  eax, dword ptr [ebx + esi*4 + {B + O_UNITS:#x}]
        push 0
        push 0
        mov  ecx, eax
        shr  ecx, 16
        push ecx
        movzx ecx, ah
        push ecx
        movzx ecx, al
        push ecx
        call {A['fill']:#x}
        inc  esi
        jmp  fu
    xit:
        add  esp, 0x10
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """

    # uds: TAoWCombatMap VMT +0xDC.  eax = map.
    R["uds"] = f"""
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, 0x10
        mov  ebp, eax
        call {A['get_delta']:#x}
        mov  ebx, eax
        cmp  byte ptr [ebp + 0xc9], 0
        je   van
        test byte ptr [ebp + 0x3c], 2
        jne  van
        cmp  byte ptr [ebp + 0xa5], 0xff
        je   base
        cmp  byte ptr [ebp + 0xc8], 0
        je   nofog
        mov  eax, ebp
        call {A['fog_update']:#x}
    nofog:
        mov  ecx, dword ptr [ebx + {IAT_HSE:#x}]
        add  ecx, {hse['reset']:#x}
        mov  eax, ebp
        call ecx
        mov  edx, dword ptr [ebp + 0x88]
        mov  eax, dword ptr [ebp + 0x10]
        call {GETMAPLEVEL_T:#x}
        mov  dword ptr [esp], eax
        test eax, eax
        je   ovl
        mov  eax, dword ptr [ebp + 0x94]
        mov  dword ptr [esp + 4], eax
        add  eax, dword ptr [ebp + 0x9c]
        mov  dword ptr [esp + 8], eax
        mov  eax, dword ptr [ebp + 0x98]
        add  eax, dword ptr [ebp + 0xa0]
        dec  eax
        mov  dword ptr [esp + 0xc], eax
    xl:
        mov  esi, dword ptr [esp + 4]
        cmp  esi, dword ptr [esp + 8]
        jge  ovl
        mov  edi, dword ptr [esp + 0xc]
    yl:
        cmp  edi, dword ptr [ebp + 0x98]
        jl   xn
        mov  ecx, dword ptr [esp]
        test esi, esi
        js   yn
        test edi, edi
        js   yn
        cmp  esi, dword ptr [ecx + 0xc]
        jge  yn
        cmp  edi, dword ptr [ecx + 0x10]
        jge  yn
        mov  edx, dword ptr [ecx + 0x74]
        mov  eax, dword ptr [edx + esi*4]
        mov  edx, dword ptr [ecx + 0x78]
        add  eax, dword ptr [edx + edi*4]
        push eax
        mov  edx, ebp
        call {A['vis']:#x}
        test eax, eax
        jne  full
        mov  eax, dword ptr [esp]
        mov  edx, ebp
        call {A['expl']:#x}
        test eax, eax
        pop  eax
        je   yn
        mov  edx, dword ptr [ebp + 0x20]
        call {A['decor']:#x}
        jmp  yn
    full:
        pop  eax
        mov  ecx, dword ptr [ebx + {IAT_HSE:#x}]
        add  ecx, {hse['copy']:#x}
        mov  edx, dword ptr [ebp + 0x20]
        call ecx
    yn:
        dec  edi
        jmp  yl
    xn:
        inc  dword ptr [esp + 4]
        jmp  xl
    ovl:
        mov  eax, dword ptr [ebp + 0x28]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  esi, eax
        xor  edi, edi
    ol:
        cmp  edi, esi
        jge  fin
        mov  edx, edi
        mov  eax, dword ptr [ebp + 0x28]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        mov  edx, dword ptr [ebp + 0x20]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xf0]
        inc  edi
        jmp  ol
    fin:
        mov  eax, dword ptr [ebp + 0x20]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x90]
        mov  byte ptr [ebp + 0x31], 0
        add  esp, 0x10
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    base:
        mov  ecx, dword ptr [ebx + {IAT_HSE:#x}]
        add  ecx, {hse['base']:#x}
        jmp  tail
    van:
        lea  ecx, [ebx + {UDS_VAN_T:#x}]
    tail:
        mov  eax, ebp
        add  esp, 0x10
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        jmp  ecx
    """

    # explore: ExploreArea ABI -- eax = map, edx = x, ecx = y, [esp+4] radius, [esp+8] player,
    # [esp+0xC] level; ret 0xC; eax = 1 if anything new.
    R["explore"] = f"""
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, 8
        mov  ebp, eax
        mov  esi, edx
        mov  edi, ecx
        mov  dword ptr [esp + 4], 0
        test byte ptr [ebp + 0x3c], 2
        jne  xit
        movzx ecx, byte ptr [esp + 0x20]
        test ecx, ecx
        je   xit
        cmp  ecx, 32
        ja   xit
        dec  ecx
        mov  eax, 1
        shl  eax, cl
        mov  dword ptr [esp], eax
        call {A['get_delta']:#x}
        mov  ebx, eax
        mov  dword ptr [ebx + {B + O_SIG:#x}], 0
        mov  dword ptr [ebx + {B + O_XPL:#x}], 1
        mov  eax, dword ptr [ebp + 0xe4]
        test eax, eax
        je   xw
        cmp  byte ptr [eax + 0x40], 1
        jne  xw
        mov  dword ptr [ebx + {B + O_XPL:#x}], 0
    xw:
        mov  edx, dword ptr [esp + 0x24]
        mov  eax, dword ptr [ebp + 0x10]
        call {GETMAPLEVEL_T:#x}
        test eax, eax
        je   xit
        call {A['bmap_build']:#x}
        mov  eax, dword ptr [esp + 0x1c]
        test eax, eax
        jns  r1
        xor  eax, eax
    r1:
        add  eax, {EXPLORE_BUF}
        cmp  eax, {RMAX}
        jle  r2
        mov  eax, {RMAX}
    r2:
        mov  ecx, dword ptr [esp]
        push ecx
        push 1
        push eax
        push edi
        push esi
        call {A['fill']:#x}
        mov  dword ptr [esp + 4], eax
        call {A['wclose']:#x}
        test eax, eax
        jne  dirty
        cmp  dword ptr [esp + 4], 0
        je   xit
        movsx ecx, byte ptr [ebp + 0xa5]
        movzx edx, byte ptr [esp + 0x20]
        cmp  ecx, edx
        jne  xit
    dirty:
        mov  byte ptr [ebp + 0x30], 1
    xit:
        xor  eax, eax
        cmp  dword ptr [esp + 4], 0
        setne al
        add  esp, 8
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret  0xc
    """

    # spart: eax = object, edx = its part number on this hex (the byte after the field's child
    # pointers: [[field+8] + [field+0xC]*4 + child index]) -> edx 1 when that part is solid.  An
    # object is a child of its own hex (part 0) and of every hex its sprite overlaps (a tree 4, a
    # house or gate 7, big buildings up to 37); only the parts its resource's terrain list
    # ([[obj+8]+0x28]) marks used are solid (TTerrainList.GetUsed, as TCombatStructure.CanMoveOn
    # tests).  Part 0 is always solid; walls, gates, terrain hexagons and every other class are
    # solid on part 0 only (TCityWall.CanMoveOn tests part 0).  Preserves all but edx.
    R["spart"] = f"""
        test edx, edx
        je   yes
        push ecx
        mov  ecx, dword ptr [eax]
        sub  ecx, ebx
        cmp  ecx, {vm['house']:#x}
        je   tl
        cmp  ecx, {vm['struct']:#x}
        je   tl
        cmp  ecx, {vm['town']:#x}
        je   tl
        cmp  ecx, {vm['work']:#x}
        je   tl
        cmp  ecx, {vm['main']:#x}
        je   tl
        cmp  ecx, {vm['obst']:#x}
        je   tl
        cmp  ecx, {vm['terr']:#x}
        jne  no_
    tl:
        mov  ecx, dword ptr [eax + 8]
        test ecx, ecx
        je   no_
        mov  ecx, dword ptr [ecx + 0x28]
        test ecx, ecx
        je   no_
        cmp  edx, dword ptr [ecx + 4]
        jge  no_
        mov  ecx, dword ptr [ecx + 8]
        movzx edx, word ptr [ecx + edx*2]
        and  edx, 0x8080
        cmp  edx, 0x8080
        je   no_
        pop  ecx
    yes:
        mov  edx, 1
        ret
    no_:
        pop  ecx
        xor  edx, edx
        ret
    """

    # wclose: ebx = delta; the level and size bmap_build left in O_LVL/O_BW/O_BH.  A wall, gate,
    # house or other structure is drawn over the hexes next to its solid hex, and DrawFog blacks
    # out whatever part of it lies over an unexplored hex.  Pass 1 marks (bit 0x04 of [field+0x1B])
    # every explored hex holding such an object at a solid part (spart); pass 2 gives each marked
    # hex's explored bits of players 1..12 (0x0FFF; bits 12-15 are the engine's movement flags) to
    # the neighbouring hexes holding the same object, and clears the mark.  Only hexes explored
    # before the call give, so it never chains along a wall.  -> eax = 1 if any bit changed.
    R["wclose"] = f"""
        push esi
        push edi
        push ebp
        sub  esp, 0x20
        mov  ebp, esp
        mov  dword ptr [ebp + 0xc], 0
        cmp  dword ptr [ebx + {B + O_BW:#x}], 0
        je   xit
        mov  dword ptr [ebp + 8], 0
    pass:
        mov  dword ptr [ebp + 4], 0
    yl:
        mov  eax, dword ptr [ebp + 4]
        cmp  eax, dword ptr [ebx + {B + O_BH:#x}]
        jge  pend
        mov  dword ptr [ebp], 0
    xl:
        mov  eax, dword ptr [ebp]
        cmp  eax, dword ptr [ebx + {B + O_BW:#x}]
        jge  yn
        mov  edx, dword ptr [ebp + 4]
        mov  ecx, dword ptr [ebx + {B + O_LVL:#x}]
        mov  edi, dword ptr [ecx + 0x74]
        mov  edi, dword ptr [edi + eax*4]
        mov  ecx, dword ptr [ecx + 0x78]
        add  edi, dword ptr [ecx + edx*4]
        movzx eax, word ptr [edi + 0x18]
        and  eax, 0xfff
        mov  dword ptr [ebp + 0x10], eax
        cmp  dword ptr [ebp + 8], 0
        jne  pb
        test eax, eax
        je   xn
        jmp  scan
    pb:
        test byte ptr [edi + {F_FLAGS:#x}], 4
        je   xn
        and  byte ptr [edi + {F_FLAGS:#x}], 0xfb
    scan:
        movzx eax, byte ptr [edi + 0xd]
        mov  dword ptr [ebp + 0x1c], eax
    cl_:
        dec  dword ptr [ebp + 0x1c]
        js   xn
        mov  ecx, dword ptr [ebp + 0x1c]
        mov  esi, dword ptr [edi + 8]
        mov  eax, dword ptr [esi + ecx*4]
        test eax, eax
        je   cl_
        mov  edx, dword ptr [eax]
        sub  edx, ebx
        cmp  edx, {vm['wall']:#x}
        je   bld
        cmp  edx, {vm['door']:#x}
        je   bld
        cmp  edx, {vm['house']:#x}
        je   bld
        cmp  edx, {vm['struct']:#x}
        je   bld
        cmp  edx, {vm['town']:#x}
        je   bld
        cmp  edx, {vm['work']:#x}
        je   bld
        cmp  edx, {vm['main']:#x}
        jne  cl_
    bld:
        movzx edx, byte ptr [edi + 0xc]
        lea  edx, [esi + edx*4]
        movzx edx, byte ptr [edx + ecx]
        call {A['spart']:#x}
        test edx, edx
        je   cl_
        cmp  dword ptr [ebp + 8], 0
        jne  prop
        or   byte ptr [edi + {F_FLAGS:#x}], 4
        jmp  xn
    prop:
        mov  dword ptr [ebp + 0x14], eax
        mov  dword ptr [ebp + 0x18], 6
    nl:
        dec  dword ptr [ebp + 0x18]
        js   cl_
        mov  eax, dword ptr [ebp]
        mov  ecx, eax
        and  ecx, 1
        imul ecx, ecx, 48
        mov  edx, dword ptr [ebp + 0x18]
        lea  ecx, [ecx + edx*8]
        add  ecx, ebx
        add  eax, dword ptr [ecx + {T_DELTA:#x}]
        mov  edx, dword ptr [ebp + 4]
        add  edx, dword ptr [ecx + {T_DELTA + 4:#x}]
        test eax, eax
        js   nl
        test edx, edx
        js   nl
        cmp  eax, dword ptr [ebx + {B + O_BW:#x}]
        jge  nl
        cmp  edx, dword ptr [ebx + {B + O_BH:#x}]
        jge  nl
        mov  ecx, dword ptr [ebx + {B + O_LVL:#x}]
        mov  esi, dword ptr [ecx + 0x74]
        mov  esi, dword ptr [esi + eax*4]
        mov  ecx, dword ptr [ecx + 0x78]
        add  esi, dword ptr [ecx + edx*4]
        movzx ecx, byte ptr [esi + 0xd]
        mov  edx, dword ptr [esi + 8]
        mov  eax, dword ptr [ebp + 0x14]
    hl:
        dec  ecx
        js   nl
        cmp  eax, dword ptr [edx + ecx*4]
        jne  hl
        movzx eax, word ptr [esi + 0x18]
        mov  edx, eax
        or   edx, dword ptr [ebp + 0x10]
        cmp  edx, eax
        je   nl
        mov  word ptr [esi + 0x18], dx
        mov  dword ptr [ebp + 0xc], 1
        jmp  nl
    xn:
        inc  dword ptr [ebp]
        jmp  xl
    yn:
        inc  dword ptr [ebp + 4]
        jmp  yl
    pend:
        cmp  dword ptr [ebp + 8], 0
        jne  xit
        mov  dword ptr [ebp + 8], 1
        jmp  pass
    xit:
        mov  eax, dword ptr [ebp + 0xc]
        add  esp, 0x20
        pop  ebp
        pop  edi
        pop  esi
        ret
    """

    # csight: eax = TCombatUnit -> eax = combat sight; clobbers ecx/edx like the vcall it
    # replaces.  The engine's GetVisibilityRange (+0xA4) is base = 3 + Vision level, halved and
    # rounded DOWN inside an exploration site ([unit+8] = TCombat, +0x40 == 1) without Night
    # Vision (0x27).  Inside a site combat sight is base halved and rounded UP (owner, 2026-10-26):
    # base - floor(base/2), base re-read through the Vision level query (+0x144, ability 0x40);
    # with Night Vision the engine's unhalved base.  Elsewhere SIGHT_MUL x the engine value.
    R["csight"] = f"""
        push ebx
        push esi
        mov  ebx, eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xa4]
        mov  esi, eax
        test esi, esi
        jle  done
        mov  eax, dword ptr [ebx + 8]
        test eax, eax
        je   tri
        cmp  byte ptr [eax + 0x40], 1
        jne  tri
        mov  eax, dword ptr [ebx + 0x4c]
        test eax, eax
        je   done
        mov  edx, 0x27
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  done
        mov  eax, dword ptr [ebx + 0x4c]
        mov  edx, 0x40
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x144]
        lea  eax, [eax + 3]
        sub  eax, esi
        mov  esi, eax
        jmp  done
    tri:
        imul esi, esi, {SIGHT_MUL}
    done:
        call {A['get_delta']:#x}
        cmp  byte ptr [eax + {MIST_ENTRY:#x}], 0xe9
        jne  fin
        mov  eax, esi
        mov  edx, ebx
        call {MIST_ENTRY:#x}
        mov  esi, eax
    fin:
        mov  eax, esi
        pop  esi
        pop  ebx
        ret
    """

    # reexplore: eax = map.  Every live unit explores as if it had just moved.
    R["reexplore"] = f"""
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, 0xc
        mov  ebp, eax
        call {A['get_delta']:#x}
        mov  ebx, eax
        test ebp, ebp
        je   xit
        mov  eax, dword ptr [ebp + 0xe4]
        test eax, eax
        je   xit
        mov  eax, dword ptr [eax + 0xc]
        test eax, eax
        je   xit
        mov  dword ptr [esp + 8], eax
        call {A['cd_count']:#x}
        mov  dword ptr [esp + 4], eax
        mov  dword ptr [esp], 0
    lp:
        mov  eax, dword ptr [esp]
        cmp  eax, dword ptr [esp + 4]
        jge  xit
        mov  edx, eax
        mov  eax, dword ptr [esp + 8]
        call {A['cd_objects']:#x}
        mov  esi, eax
        call {A['unitfield']:#x}
        test eax, eax
        je   nx
        mov  edi, eax
        push 0
        mov  eax, esi
        call {GETPLAYER_T:#x}
        movsx eax, al
        push eax
        mov  eax, esi
        call {A['csight']:#x}
        push eax
        movzx edx, byte ptr [edi + 0x10]
        movzx ecx, byte ptr [edi + 0x11]
        mov  eax, ebp
        call {A['explore']:#x}
    nx:
        inc  dword ptr [esp]
        jmp  lp
    xit:
        add  esp, 0xc
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """

    # wallhp: replaces `mov eax,[ebp-8]; mov edx,[ebp-4]` ahead of `mov [edx+0x20],eax` in
    # TCityWall.SetHitPoints and TCombatStructure.SetHitPoints (ebp = their frame: [ebp-8] the
    # new hit points, clamped to >= 0, [ebp-4] Self).  On the drop to 0 it writes the 0 itself,
    # then reexplore; the setter's own write stores the same 0.
    R["wallhp"] = f"""
        mov  eax, dword ptr [ebp - 8]
        mov  edx, dword ptr [ebp - 4]
        test eax, eax
        jne  xit
        test edx, edx
        je   xit
        cmp  dword ptr [edx + {HP_OFF:#x}], 0
        jle  xit
        mov  dword ptr [edx + {HP_OFF:#x}], 0
        pushad
        call {A['get_delta']:#x}
        mov  eax, dword ptr [eax + {V_SCREEN:#x}]
        call {A['reexplore']:#x}
        popad
    xit:
        mov  eax, dword ptr [ebp - 8]
        mov  edx, dword ptr [ebp - 4]
        ret
    """
    # xpl: GetExplored ABI (eax = field, edx = player) for the move-order and cursor sites: a move
    # may target any hex the seated player has explored (expl), seen or not.  nil -> 0.
    R["xpl"] = f"""
        test eax, eax
        je   no
        push eax
        call {A['get_delta']:#x}
        mov  edx, dword ptr [eax + {V_SCREEN:#x}]
        pop  eax
        test edx, edx
        je   yes
        jmp  {A['expl']:#x}
    yes:
        mov  eax, 1
        ret
    no:
        xor  eax, eax
        ret
    """

    # hidn: eax = an occupant unit's HS, edx = the pathfinder's position record ([edx] = move
    # settings, whose +0x1E0 is the moving unit's HS).  -> eax 1 when the local player is planning
    # a move order (O_PLAN, set by calcwrap) for one of its own units and cannot see the occupant's
    # hex: the planner then treats the hex as empty.  Preserves every register but eax.
    R["hidn"] = f"""
        push ebx
        push ecx
        push edx
        push esi
        mov  esi, eax
        call {A['get_delta']:#x}
        mov  ebx, eax
        cmp  dword ptr [ebx + {B + O_PLAN:#x}], 0
        je   no
        mov  ecx, dword ptr [ebx + {V_SCREEN:#x}]
        test ecx, ecx
        je   no
        mov  eax, dword ptr [edx]
        test eax, eax
        je   no
        mov  eax, dword ptr [eax + 0x1e0]
        test eax, eax
        je   no
        cmp  eax, esi
        je   no
        mov  eax, dword ptr [eax + 0x1c]
        test eax, eax
        je   no
        push ecx
        call {GETPLAYER_T:#x}
        pop  ecx
        movsx eax, al
        movsx edx, byte ptr [ecx + 0xa5]
        cmp  eax, edx
        jne  no
        mov  eax, dword ptr [esi + 4]
        test eax, eax
        je   no
        mov  edx, ecx
        call {A['vis']:#x}
        test eax, eax
        jne  no
        mov  eax, 1
        jmp  xit
    no:
        xor  eax, eax
    xit:
        pop  esi
        pop  edx
        pop  ecx
        pop  ebx
        ret
    """

    # calcwrap: TCombatUnitSelectionControl VMT +8 (CalculateMovePath: eax = control, edx =
    # index, ecx = x, [esp+4] level, [esp+8] y; ret 8), the only way the local player's move
    # orders, previews and group plans are pathed.  Sets O_PLAN around the original.  aispot
    # clears it as well, so an exception inside cannot leave it set for an AI turn.
    R["calcwrap"] = f"""
        push ebx
        push eax
        call {A['get_delta']:#x}
        mov  ebx, eax
        pop  eax
        mov  dword ptr [ebx + {B + O_PLAN:#x}], 1
        push dword ptr [esp + 0xc]
        push dword ptr [esp + 0xc]
        add  ebx, {CALC_ORIG:#x}
        call ebx
        push eax
        call {A['get_delta']:#x}
        mov  dword ptr [eax + {B + O_PLAN:#x}], 0
        pop  eax
        pop  ebx
        ret  8
    """

    # canon: TTacticalCombatUnitHS VMT +0xD0 (CanMoveOn: eax = occupant HS, edx = position
    # record, ecx = the cost record it may veto).  A hidden occupant (hidn) vetoes nothing.
    R["canon"] = f"""
        push eax
        call {A['hidn']:#x}
        test eax, eax
        pop  eax
        jne  skip
        push eax
        call {A['get_delta']:#x}
        add  eax, {CANON_ORIG:#x}
        xchg eax, dword ptr [esp]
        ret
    skip:
        ret
    """

    # canover: VMT +0xD4 (CanMoveOver, transit; -> eax 1 passable).  A hidden occupant (hidn)
    # is passable; anything else goes to what the slot held before (T_PREV: the vanilla thunk,
    # or build_group_move_tc.py's cave_unit).
    R["canover"] = f"""
        push eax
        call {A['hidn']:#x}
        test eax, eax
        pop  eax
        jne  pass_
        push eax
        call {A['get_delta']:#x}
        push ecx
        mov  ecx, dword ptr [eax + {T_PREV:#x}]
        add  eax, ecx
        pop  ecx
        xchg eax, dword ptr [esp]
        ret
    pass_:
        mov  eax, 1
        ret
    """

    # stepchk: replaces DefaultMove's `call TAoWMapField.GetPlayer` on the next step's hex
    # (STEP_SITE; ebp = DefaultMove's frame, [ebp-4] = the move TE: +0x14 path list, +0x18 steps
    # left, path[0] the destination, +0x1C the unit).  Vanilla stops the move when that hex is
    # occupied.  When it is free, a plain move (TCombatMoveTE, not a melee or touch move) also
    # stops when the mover sees an occupied hex further along its path: within its combat sight,
    # with a clear line.  -> al 0xFF go on, anything else stop.  Synchronised state only.
    # The look-ahead skips path[0], the destination (2026-10-29): the battle AI orders plain moves
    # onto an enemy's hex, which vanilla walks until the next-hex test stops it alongside.  Scanning
    # path[0] stopped such a move before its first step, and the AI re-issued it every cycle: an AI
    # Pikeman on a wall re-ordered a move onto a Bone Horror in the gate ~6 times a second, forever.
    R["stepchk"] = f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        call {A['get_delta']:#x}
        mov  ebx, eax
        mov  eax, esi
        call {FPLAYER_T:#x}
        cmp  al, 0xff
        jne  xit
        sub  esp, 0x10
        mov  eax, dword ptr [ebp - 4]
        test eax, eax
        je   clr
        mov  dword ptr [esp], eax
        mov  edx, dword ptr [eax]
        sub  edx, ebx
        cmp  edx, {MOVETE_VMT:#x}
        jne  clr
        mov  edx, dword ptr [eax + 0x1c]
        test edx, edx
        je   clr
        mov  ecx, dword ptr [edx + 0x60]
        test ecx, ecx
        je   clr
        mov  ecx, dword ptr [ecx + 4]
        test ecx, ecx
        je   clr
        mov  dword ptr [esp + 0xc], ecx
        mov  eax, edx
        call {A['csight']:#x}
        cmp  eax, {RMAX}
        jle  s1
        mov  eax, {RMAX}
    s1:
        mov  dword ptr [esp + 8], eax
        mov  eax, dword ptr [ebx + {V_SCREEN:#x}]
        test eax, eax
        je   clr
        xor  edx, edx
        mov  eax, dword ptr [eax + 0x10]
        call {GETMAPLEVEL_T:#x}
        test eax, eax
        je   clr
        mov  dword ptr [ebx + {B + O_XPL:#x}], 0
        call {A['bmap_build']:#x}
        mov  ecx, dword ptr [esp + 0xc]
        movzx eax, byte ptr [ecx + {F_FLAGS:#x}]
        and  eax, 1
        mov  dword ptr [ebx + {B + O_VIN:#x}], eax
        mov  eax, dword ptr [esp]
        mov  eax, dword ptr [eax + 0x18]
        sub  eax, 2
        mov  dword ptr [esp + 4], eax
    lp:
        cmp  dword ptr [esp + 4], 0
        jle  clr
        mov  eax, dword ptr [esp]
        mov  eax, dword ptr [eax + 0x14]
        mov  edx, dword ptr [esp + 4]
        call {XYLGET_T:#x}
        mov  edx, eax
        mov  eax, dword ptr [esp]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x50]
        test eax, eax
        je   nx
        mov  edi, eax
        call {FPLAYER_T:#x}
        cmp  al, 0xff
        je   nx
        movsx eax, byte ptr [edi + 0x11]
        push eax
        movsx eax, byte ptr [edi + 0x10]
        push eax
        mov  ecx, dword ptr [esp + 0x14]
        movsx edx, byte ptr [ecx + 0x11]
        movsx eax, byte ptr [ecx + 0x10]
        call {A['hd']:#x}
        cmp  eax, dword ptr [esp + 8]
        jg   nx
        movsx eax, byte ptr [edi + 0x11]
        push eax
        movsx eax, byte ptr [edi + 0x10]
        push eax
        mov  ecx, dword ptr [esp + 0x14]
        movsx eax, byte ptr [ecx + 0x11]
        push eax
        movsx eax, byte ptr [ecx + 0x10]
        push eax
        call {A['los']:#x}
        test eax, eax
        jne  stop
    nx:
        dec  dword ptr [esp + 4]
        jmp  lp
    stop:
        add  esp, 0x10
        xor  eax, eax
        jmp  xit
    clr:
        add  esp, 0x10
        mov  eax, 0xff
    xit:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return R


ORDER = ("get_delta", "vis", "seen", "aispot", "hover", "drawfog", "hd", "blocker", "bmap_build",
         "los", "fill", "fog_update", "uds", "explore", "fld", "relax", "sweep", "flood",
         "unitfield", "oneplayer", "worldflood", "startflood", "expl", "decor", "iswall",
         "inside_build", "fogon", "reexplore", "wallhp", "csight", "spart", "wclose", "xpl", "hidn",
         "calcwrap", "canon", "canover", "stepchk")


def resolve_thunks(d):
    """Find each import's thunk (FF 25 iat) and check the fixed ones."""
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    from aowsyms import get_symbols
    pe, base, syms, iat = get_symbols("AoWTCPCK.dpl")
    by_name = {}
    for slot, name in iat.items():
        o = d.find(b"\xFF\x25" + struct.pack("<I", slot))
        if o != -1:
            by_name[name.split("!", 1)[1]] = (P.IMAGE_BASE + 0x1000 + o - _code_raw(d), slot)
    for va, name in THUNK.items():
        got = by_name.get(name)
        if not got or got[0] != va:
            sys.exit("ABORT: thunk for %s is %s, expected %08X" % (name, got, va))
    out = {}
    for key, name in IAT_NAMES.items():
        if name not in by_name:
            sys.exit("ABORT: no import thunk for %s" % name)
        out[key] = by_name[name][0]
    if iat.get(IAT_TCOMBATUNIT, "").split("!")[-1] != "AoWE..TCombatUnit":
        sys.exit("ABORT: IAT %08X is %s, expected AoWE..TCombatUnit" % (IAT_TCOMBATUNIT, iat.get(IAT_TCOMBATUNIT)))
    if iat.get(IAT_HSE, "").split("!")[-1] != HSE["anchor"][1]:
        sys.exit("ABORT: IAT %08X is %s, expected %s" % (IAT_HSE, iat.get(IAT_HSE), HSE["anchor"][1]))
    return out


def _code_raw(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    for i in range(nsec):
        o = e + 24 + opt + 40 * i
        if d[o:o + 4] == b"CODE":
            vaddr, rsize, raw = struct.unpack_from("<III", d, o + 12)
            assert vaddr == 0x1000
            return raw
    sys.exit("ABORT: no CODE section")


def check_static(d):
    def u32(va):
        return struct.unpack_from("<I", d, P.va2off(d, va))[0]
    for key, (va, name) in list(VMT.items()) + list(DECOR.items()):
        if u32(va - 0x40) != va:
            sys.exit("ABORT: %08X is not a VMT (%s)" % (va, name))
        np_ = u32(va - 0x20)
        o = P.va2off(d, np_)
        if d[o + 1:o + 1 + d[o]].decode("latin-1") != name:
            sys.exit("ABORT: VMT %08X is not %s" % (va, name))
    if u32(VMT_UDS) not in (UDS_VAN_T, E_UDS, OLD_ZONE[0] + 8):
        sys.exit("ABORT: TAoWCombatMap VMT +0xDC holds %08X" % u32(VMT_UDS))
    if u32(CALC_SLOT) not in (CALC_ORIG, E["calcwrap"]):
        sys.exit("ABORT: TCombatUnitSelectionControl VMT +8 holds %08X" % u32(CALC_SLOT))
    if u32(CANON_SLOT) not in (CANON_ORIG, E["canon"]):
        sys.exit("ABORT: TTacticalCombatUnitHS VMT +0xD0 holds %08X" % u32(CANON_SLOT))
    cur = u32(CANOVER_SLOT)
    PREV[0] = u32(T_PREV) if cur == E["canover"] else cur
    if PREV[0] != CANOVER_VAN and not GM_ZONE[0] <= PREV[0] < GM_ZONE[1]:
        sys.exit("ABORT: TTacticalCombatUnitHS VMT +0xD4 led to %08X, neither the vanilla thunk nor "
                 "build_group_move_tc.py's cave" % PREV[0])
    # HSEPack exports at their preferred addresses
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    from aowsyms import get_symbols
    _pe, _b, hs, _i = get_symbols("HSEPack.dpl")
    for key, (va, name) in HSE.items():
        if hs.get(va) != name:
            sys.exit("ABORT: HSEPack %08X is %s, expected %s" % (va, hs.get(va), name))


def layout(thunks, tables):
    T = {}
    va = T_DELTA
    blobs = [("t_delta", va, delta_table())]
    va += 0x60
    for key, cls in (("terr", RC_TERR), ("single", RC_SINGLE), ("main", RC_MAIN), ("decor", None)):
        gl = sorted(tables[cls]) if cls else sorted(v for v, _n in DECOR.values())
        blob = struct.pack("<I", len(gl)) + b"".join(struct.pack("<I", g) for g in gl)
        T[key] = va
        blobs.append(("t_" + key, va, blob))
        va = (va + len(blob) + 0xF) & ~0xF
    code0 = va
    A = dict(thunks)
    # pass 1 sizes with every routine at code0, pass 2 real addresses (repeat until stable)
    for r in ORDER:
        A[r] = code0
    sizes = None
    for _ in range(4):
        src = routines(A, T)
        cur, addr = {}, code0
        new = dict(A)
        for r in ORDER:
            new[r] = addr
            addr = (addr + len(asm(src[r], A[r])) + 0xF) & ~0xF
        src = routines(new, T)
        cur = {r: asm(src[r], new[r]) for r in ORDER}
        if new == A and sizes == {r: len(b) for r, b in cur.items()}:
            break
        A, sizes = new, {r: len(b) for r, b in cur.items()}
    else:
        sys.exit("ABORT: cave layout did not settle")
    for r in ORDER:
        blobs.append((r, A[r], cur[r]))
    stubs = b"".join(jmp8(E[n], A[n]) for n in STUBS)
    blobs.insert(0, ("stubs", ZONE[0], stubs))
    blobs.insert(1, ("t_prev", T_PREV, struct.pack("<I", PREV[0])))
    end = max(va + len(b) for _n, va, b in blobs)
    assert end <= ZONE[1], "caves overflow the zone (%08X)" % end
    return blobs, A


def hooks():
    h = [(RM_EXPL, RM_EXPL_VAN, RM_EXPL_NEW), (RM_FOG, RM_FOG_VAN, RM_FOG_NEW),
         (ST_SITE, call_to(ST_SITE, SETSEAT), call_to(ST_SITE, E_START)),
         (RM_FOGON, RM_FOGON_VAN, call_to(RM_FOGON, E_FOGON) + NOP1)]
    h += [(s, call_to(s, EXPLOREAREA_T), call_to(s, E_EXPLORE)) for s in EX_SITES]
    h.append((VMT_UDS, struct.pack("<I", UDS_VAN_T), struct.pack("<I", E_UDS)))
    h.append((DF_SITE, call_to(DF_SITE, DRAWFOG_T), call_to(DF_SITE, E_DRAWFOG)))
    h += [(s, call_to(s, GETEXPLORED_T), call_to(s, E_SEEN)) for s in CAM_SITES]
    h += [(s, call_to(s, GETEXPLORED_T), call_to(s, E["xpl"])) for s in INPUT_SITES]
    h.append((AI_SITE, call_to(AI_SITE, GETEXPLORED_T), call_to(AI_SITE, E_AISPOT)))
    h += [(s, HOVER_VAN, call_to(s, E_HOVER) + NOP1) for s, _lo, _hi in HOVER_SITES]
    h += [(s, HP_VAN, call_to(s, E_WALLHP) + NOP1) for s, _lo, _hi in HP_SITES]
    h += [(s, CS_VAN, call_to(s, E_CSIGHT) + NOP1) for s in CS_SITES]
    h.append((CALC_SLOT, struct.pack("<I", CALC_ORIG), struct.pack("<I", E["calcwrap"])))
    h.append((CANON_SLOT, struct.pack("<I", CANON_ORIG), struct.pack("<I", E["canon"])))
    h.append((CANOVER_SLOT, struct.pack("<I", PREV[0]), struct.pack("<I", E["canover"])))
    h.append((STEP_SITE, call_to(STEP_SITE, FPLAYER_T), call_to(STEP_SITE, E["stepchk"])))
    return h


def old_hooks():
    """The hook set as it was installed in OLD_ZONE (until 2026-10-25)."""
    o = {n: OLD_ZONE[0] + 8 * i for i, n in enumerate(STUBS[:10])}
    h = [(RM_EXPL, RM_EXPL_VAN, RM_EXPL_NEW), (RM_FOG, RM_FOG_VAN, RM_FOG_NEW),
         (ST_SITE, call_to(ST_SITE, SETSEAT), call_to(ST_SITE, o["startflood"])),
         (RM_FOGON, RM_FOGON_VAN, call_to(RM_FOGON, o["fogon"]) + NOP1)]
    h += [(s, call_to(s, EXPLOREAREA_T), call_to(s, o["explore"])) for s in EX_SITES]
    h.append((VMT_UDS, struct.pack("<I", UDS_VAN_T), struct.pack("<I", o["uds"])))
    h.append((DF_SITE, call_to(DF_SITE, DRAWFOG_T), call_to(DF_SITE, o["drawfog"])))
    h += [(s, call_to(s, GETEXPLORED_T), call_to(s, o["seen"])) for s in SEEN_SITES]
    h.append((AI_SITE, call_to(AI_SITE, GETEXPLORED_T), call_to(AI_SITE, o["aispot"])))
    h += [(s, HOVER_VAN, call_to(s, o["hover"]) + NOP1) for s, _lo, _hi in OLD_HOVER]
    h += [(s, HP_VAN, call_to(s, o["wallhp"]) + NOP1) for s, _lo, _hi in HP_SITES]
    h += [(s, CS_VAN, call_to(s, o["csight"]) + NOP1) for s in CS_SITES]
    return h


def migrate(argv):
    """Until 2026-10-25 the caves lived in OLD_ZONE.  On --apply / --undo, undo that install first
    (hooks vanilla, the old zone zeroed).  -> True while it is still installed (dry run)."""
    d = bytearray(open(P.TARGET, "rb").read())
    now = {va: new for va, _van, new in hooks()}
    olds = [h for h in old_hooks() if now.get(h[0]) != h[2]]    # the ones that pointed at OLD_ZONE
    st = []
    for va, van, new in olds:
        o = P.va2off(d, va)
        cur = bytes(d[o:o + len(van)])
        st.append("installed" if cur == new else "vanilla" if cur == van else "other")
    if "installed" not in st:
        return False
    if set(st) != {"installed"}:
        sys.exit("ABORT: the old-zone install is partial (%d of %d hooks)"
                 % (st.count("installed"), len(st)))
    if not ({"--apply", "--undo"} & set(argv)):
        print("  old-zone install at %08X present -- --apply or --undo migrates it" % OLD_ZONE[0])
        return True
    P.kill_aow()
    for va, van, new in olds:
        o = P.va2off(d, va)
        d[o:o + len(van)] = van
    zo, zh = P.va2off(d, OLD_ZONE[0]), P.va2off(d, OLD_ZONE[1])
    d[zo:zh] = b"\0" * (zh - zo)
    open(P.TARGET, "wb").write(d)
    print("  old-zone install undone: %d hooks vanilla, %08X-%08X zeroed" % (len(st), *OLD_ZONE))
    return False


INTERIOR = [(RM_EXPL, RM_EXPL + 3, 0x004245EC, 0x00426644),
            (RM_FOGON, RM_FOGON + 6, 0x004245EC, 0x00426644)] + \
    [(s, s + 6, lo, hi) for s, lo, hi in HOVER_SITES + HP_SITES]


# ---------------------------------------------------------------- --test (Python model)
def _cube(x, y):
    return x, y - ((x - (x & 1)) >> 1)


def _dist(a, b):
    ax, az = _cube(*a)
    bx, bz = _cube(*b)
    dx, dz = ax - bx, az - bz
    return (abs(dx) + abs(dz) + abs(dx + dz)) // 2


def model_walk(c, t, tie_last):
    cur, path, cap = c, [], STEP_CAP
    while cur != t:
        cap -= 1
        if cap < 0:
            return None
        best, bd = None, 1 << 31
        for dx, dy in (DELTAS_ODD if cur[0] & 1 else DELTAS_EVEN):
            cand = (cur[0] + dx, cur[1] + dy)
            dd = _dist(cand, t)
            if dd < bd or (tie_last and dd == bd):
                best, bd = cand, dd
        cur = best
        if cur != t:
            path.append(cur)
    return path


def model_los(block, c, t):
    for tie in (False, True):
        p = model_walk(c, t, tie)
        if p is None or not any(h in block for h in p):
            return True
    return False


def run_test():
    import itertools
    ok = True
    # 1. every walk is a shortest path (length == hex distance - 1 intermediates, steps adjacent)
    for c in itertools.product(range(8, 12), range(8, 12)):
        for t in itertools.product(range(0, 20), range(0, 20)):
            if t == c:
                continue
            for tie in (False, True):
                p = model_walk(c, t, tie)
                if p is None or len(p) != _dist(c, t) - 1:
                    print("  FAIL walk %s->%s" % (c, t)); ok = False
                    continue
                prev = c
                for h in p + [t]:
                    if _dist(prev, h) != 1:
                        print("  FAIL step %s->%s in %s->%s" % (prev, h, c, t)); ok = False
                    prev = h
    print("  [1] both walks are shortest paths over adjacent hexes: %s" % ("ok" if ok else "FAIL"))
    # 2. along an axis there is one shortest path: an adjacent blocker is seen, the hex behind is not
    for c in ((10, 10), (11, 10)):
        for k in range(6):
            dx, dy = (DELTAS_ODD if c[0] & 1 else DELTAS_EVEN)[k]
            b = (c[0] + dx, c[1] + dy)
            dx2, dy2 = (DELTAS_ODD if b[0] & 1 else DELTAS_EVEN)[k]
            t = (b[0] + dx2, b[1] + dy2)
            good = model_los({b}, c, b) and not model_los({b}, c, t) and model_los(set(), c, t)
            if not good:
                print("  FAIL axis %d from %s: blocker %s, behind %s" % (k, c, b, t)); ok = False
    print("  [2] adjacent blocker seen, the hex behind it hidden (both parities): %s" % ("ok" if ok else "FAIL"))
    # 3. a solid ring at distance 2 hides everything beyond it
    c = (10, 10)
    ring = {h for h in itertools.product(range(0, 21), range(0, 21)) if _dist(h, c) == 2}
    hidden = all(not model_los(ring, c, t) for t in itertools.product(range(0, 21), range(0, 21))
                 if _dist(t, c) >= 3)
    print("  [3] a solid ring at distance 2 hides everything beyond it: %s" % ("ok" if hidden else "FAIL"))
    ok &= hidden
    print("TEST %s" % ("PASSED" if ok else "FAILED"))
    return ok


# ---------------------------------------------------------------- --emulate (unicorn)
def run_emulate(d, blobs, A, tables):
    """Run the caves themselves on a fake combat map and compare with the Python model.
    The image is loaded unrebased (load delta 0); every import the caves reach is stubbed."""
    import random
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX,
                                   UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI,
                                   UC_X86_REG_EBP, UC_X86_REG_ESP)
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    IMG, HEAP, STUB, STK, MAGIC = 0x400000, 0x10000000, 0x20000000, 0x30000000, 0x40000000
    mu.mem_map(IMG, 0x100000)
    mu.mem_map(HEAP, 0x800000)
    mu.mem_map(STUB, 0x10000)
    mu.mem_map(STK, 0x100000)
    mu.mem_map(MAGIC, 0x1000)
    for vsize, vaddr, rsize, raw in P.sections(d)[1]:
        mu.mem_write(IMG + vaddr, bytes(d[raw:raw + min(rsize, vsize or rsize)]))
    for _n, va, blob in blobs:
        mu.mem_write(va, blob)
    w32 = lambda a, v: mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))
    r32 = lambda a: struct.unpack("<I", mu.mem_read(a, 4))[0]
    w8 = lambda a, v: mu.mem_write(a, bytes([v & 0xFF]))
    r8 = lambda a: mu.mem_read(a, 1)[0]
    heap = [HEAP]

    def alloc(n):
        a = heap[0]
        heap[0] += (n + 15) & ~15
        return a
    stub_at = [STUB]

    def stub(src, at=None):
        a = at if at is not None else stub_at[0]
        b = asm(src, a)
        mu.mem_write(a, b)
        if at is None:
            stub_at[0] += (len(b) + 15) & ~15
        return a

    def cell(thunk):
        assert r32(thunk) & 0xFFFF == 0x25FF, "%08X is not a thunk" % thunk
        return struct.unpack("<I", mu.mem_read(thunk + 2, 4))[0]
    LOG = alloc(0x4000)
    W, H = 65, 59                   # the combat maps' size, so the real templates fit
    L = alloc(0x80)
    fields = alloc(W * H * 0x40)
    cols, rows = alloc(W * 4), alloc(H * 4)
    for x in range(W):
        w32(cols + 4 * x, fields + 0x40 * x)
    for y in range(H):
        w32(rows + 4 * y, 0x40 * W * y)
    w32(L + 0xC, W); w32(L + 0x10, H); w32(L + 0x74, cols); w32(L + 0x78, rows)
    F = lambda x, y: fields + 0x40 * (W * y + x)
    for y in range(H):
        for x in range(W):
            f = F(x, y)
            w32(f + 8, alloc(0x30)); w8(f + 0xC, 8); w8(f + 0xD, 0); w8(f + 0x10, x); w8(f + 0x11, y)
    # stubs for every import the caves reach
    w32(cell(GETMAPLEVEL_T), stub("mov eax, %#x\nret" % L))
    w32(cell(A["cd_count"]), stub("mov eax, dword ptr [eax]\nret"))
    w32(cell(A["cd_objects"]), stub("mov eax, dword ptr [eax + edx*4 + 0x40]\nret"))
    w32(cell(A["isclass"]), stub("mov eax, dword ptr [eax]\nxor ecx, ecx\ncmp eax, edx\nsete cl\nmov eax, ecx\nret"))
    w32(cell(GETPLAYER_T), stub("movzx eax, byte ptr [eax + 0x45]\nret"))
    w32(cell(GETEXPLORED_T), stub("test edx, edx\nje one\nlea ecx, [edx - 1]\nbt dword ptr [eax + 0x18], ecx\n"
                                  "setb al\nmovzx eax, al\nret\none:\nmov eax, 1\nret"))
    w32(cell(UDS_VAN_T), stub("mov dword ptr [%#x], 0x7a7a\nret" % LOG))
    w32(cell(DRAWFOG_T), stub("mov dword ptr [%#x], 0xd4a7\nret" % LOG))
    X = STUB + 0x8000
    w32(IAT_HSE, X)
    stub("mov dword ptr [%#x], 0\nret" % LOG, X - 0x450)                      # ResetVisibleDynamicHS
    stub("mov dword ptr [%#x], 0xba5e\nret" % LOG, X - 0x22C)                 # base UpdateDynamicScene
    stub("mov ecx, dword ptr [%#x]\nmov dword ptr [ecx*4 + %#x], eax\ninc dword ptr [%#x]\nret"
         % (LOG, LOG + 4, LOG), X - 0x5D44)                                   # CopyDynamicVisibleHS
    UV = alloc(0x100)                                                          # fake TCombatUnit VMT
    w32(UV + 0x60, stub("mov eax, 1\nret"))
    w32(UV + 0xA4, stub("push ebx\nmov ebx, eax\nmov eax, dword ptr [ebx + 0x4c]\n"
                        "mov ecx, dword ptr [eax]\nmov edx, 0x40\ncall dword ptr [ecx + 0x144]\n"
                        "lea edx, [eax + 3]\nmov eax, dword ptr [ebx + 8]\n"
                        "cmp byte ptr [eax + 0x40], 1\njne o\npush edx\n"
                        "mov eax, dword ptr [ebx + 0x4c]\nmov ecx, dword ptr [eax]\nmov edx, 0x27\n"
                        "call dword ptr [ecx + 0x148]\npop edx\ntest al, al\njne o\nsar edx, 1\n"
                        "o:\nmov eax, edx\npop ebx\nret"))
    AUV = alloc(0x200)                                                         # fake TAbstractUnit VMT
    w32(AUV + 0x144, stub("mov eax, dword ptr [eax + 0x10]\nret"))           # Vision level
    w32(AUV + 0x148, stub("xor ecx, ecx\ncmp edx, 0x27\njne n\nmovzx ecx, byte ptr [eax + 0x14]\n"
                          "n:\nmov eax, ecx\nret"))                         # has ability (NV only)
    w32(IAT_TCOMBATUNIT, UV)
    OLV, VLV, FV = alloc(0x100), alloc(0x100), alloc(0x100)
    w32(OLV + 0x54, stub("xor eax, eax\nret"))
    w32(VLV + 0x90, stub("ret"))
    w32(FV + 0x80, stub("mov eax, 0x55aa\nret"))
    OL, VL = alloc(16), alloc(16)
    w32(OL, OLV); w32(VL, VLV)
    COMBAT, DATA = alloc(0x80), alloc(0x200)
    M = alloc(0x200)
    w32(M + 0x10, alloc(16)); w32(M + 0x88, 0); w8(M + 0xA5, 3); w8(M + 0xC8, 1); w8(M + 0xC9, 1)
    w8(M + 0x3C, 0); w32(M + 0xE4, COMBAT); w32(COMBAT + 0xC, DATA); w8(COMBAT + 0x40, 2)
    w8(M + 0xEC, 1); w8(DATA + 0x31, 2)    # seated combat player 1; the AI moves player 2
    w32(M + 0x94, 0); w32(M + 0x98, 0); w32(M + 0x9C, W); w32(M + 0xA0, H)
    w32(M + 0x20, VL); w32(M + 0x28, OL)
    w32(V_SCREEN, M)
    MV, USS = alloc(0x200), alloc(16)                                          # map VMT
    w32(M, MV)
    w32(MV + 0xD8, stub("inc dword ptr [%#x]\nret" % USS))                     # UpdateStaticScene
    STOP = STACK_TOP = STK + 0xF0000
    fails = []

    def call(addr, eax=0, edx=0, ecx=0, ebx=0, args=(), ebp=0xB9B9B9B9):
        sp = STACK_TOP
        for a in reversed(args):
            sp -= 4; w32(sp, a)
        sp -= 4; w32(sp, MAGIC)
        for reg, v in ((UC_X86_REG_EAX, eax), (UC_X86_REG_EDX, edx), (UC_X86_REG_ECX, ecx),
                       (UC_X86_REG_EBX, ebx), (UC_X86_REG_ESI, 0x51515151),
                       (UC_X86_REG_EDI, 0xD1D1D1D1), (UC_X86_REG_EBP, ebp),
                       (UC_X86_REG_ESP, sp)):
            mu.reg_write(reg, v & 0xFFFFFFFF)
        mu.emu_start(addr, MAGIC, count=200_000_000)
        out = mu.reg_read(UC_X86_REG_EAX)
        if mu.reg_read(UC_X86_REG_ESP) != STACK_TOP:
            fails.append("%08X: esp off by %d" % (addr, mu.reg_read(UC_X86_REG_ESP) - STACK_TOP))
        for reg, v, nm in ((UC_X86_REG_ESI, 0x51515151, "esi"), (UC_X86_REG_EDI, 0xD1D1D1D1, "edi"),
                           (UC_X86_REG_EBP, ebp, "ebp"), (UC_X86_REG_EBX, ebx, "ebx")):
            if mu.reg_read(reg) != v & 0xFFFFFFFF:
                fails.append("%08X: %s not preserved" % (addr, nm))
        return out

    def check(name, cond):
        print("  [%s] %s" % ("ok" if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    def sight(u, r, nv=0):
        au = alloc(0x20)
        w32(au, AUV); w32(au + 0x10, r - 3); w8(au + 0x14, nv)
        w32(u + 0x4c, au); w32(u + 8, COMBAT)

    def obj(vmt, hp=None, guid=None, solid=None):
        o = alloc(0x60)
        w32(o, vmt)
        if hp is not None:
            w32(o + HP_OFF, hp)
        if guid is not None or solid is not None:
            res = alloc(0x40)
            w32(res + 0xC, guid or 0)
            w32(o + 8, res)
            if solid is not None:                     # terrain list: 7 parts, `solid` used
                tl, data = alloc(0x10), alloc(0x20)
                w32(tl + 4, 7); w32(tl + 8, data)
                for k in range(7):
                    mu.mem_write(data + 2 * k, b"\x00\x00" if k in solid else b"\xff\xff")
                w32(res + 0x28, tl)
        return o

    def put(x, y, objs, dynamic=0, hn=None):
        f = F(x, y)
        arr = r32(f + 8)
        for i, o in enumerate(objs):
            w32(arr + 4 * i, o)
            w8(arr + 32 + i, (hn or [0] * len(objs))[i])
        w8(f + 0xD, len(objs)); w8(f + 0xE, len(objs) - dynamic)

    vm = {k: v[0] for k, v in VMT.items()}
    g_terr, g_single, g_main = tables[RC_TERR][0], tables[RC_SINGLE][0], tables[RC_MAIN][0]
    # 1. blocker, class by class
    cases = [("wall standing", [obj(vm["wall"], hp=5)], 2), ("wall destroyed", [obj(vm["wall"], hp=0)], 0),
             ("gate standing", [obj(vm["door"], hp=3)], 2), ("house standing", [obj(vm["house"], hp=9)], 4),
             ("wall + tree", [obj(vm["wall"], hp=5), obj(vm["terr"], guid=tables[RC_TERR][0])], 6),
             ("house destroyed", [obj(vm["house"], hp=0)], 0), ("obstacle", [obj(vm["obst"])], 4),
             ("lair rock", [obj(vm["iso"])], 1), ("tree", [obj(vm["terr"], guid=g_terr)], 4),
             ("shrub (unlisted terrain)", [obj(vm["terr"], guid=0x7EADBEEF)], 0),
             ("wall single hex", [obj(vm["single"], guid=g_single)], 1),
             ("floor single hex", [obj(vm["single"], guid=0x7EADBEEF)], 0),
             ("inn standing", [obj(vm["main"], hp=4, guid=g_main)], 4),
             ("inn destroyed", [obj(vm["main"], hp=0, guid=g_main)], 0),
             ("unit HS only", [obj(UV)], 0), ("empty", [], 0),
             ("unit + tree", [obj(UV), obj(vm["terr"], guid=g_terr)], 4)]
    for name, objs, want in cases:
        put(0, 0, objs)
        mu.reg_write(UC_X86_REG_EDI, F(0, 0))
        sp = STACK_TOP - 4
        w32(sp, MAGIC)
        mu.reg_write(UC_X86_REG_ESP, sp); mu.reg_write(UC_X86_REG_EBX, 0)
        mu.emu_start(A["blocker"], MAGIC, count=1_000_000)
        got = mu.reg_read(UC_X86_REG_EAX)
        check("blocker: %s -> %d" % (name, want), got == want)
    # the bitmap per mode: rock, a tree, a wall under a tree
    put(0, 0, [obj(vm["iso"])]); put(1, 0, [obj(vm["terr"], guid=g_terr)])
    put(2, 0, [obj(vm["wall"], hp=5), obj(vm["terr"], guid=g_terr)])
    bits = {}
    for xpl in (0, 1):
        w32(BSS + O_XPL, xpl)
        call(A["bmap_build"], eax=L)
        bits[xpl] = (r8(BSS + O_BMAP) & 7, r8(BSS + O_WMAP) & 7, r32(BSS + O_NB))
    check("bitmap: sight puts rock, tree and wall-under-tree in the solid map; exploration keeps "
          "the rock, drops the tree, keeps the wall as a wall", bits == {0: (7, 0, 3), 1: (1, 4, 2)})
    for x in range(3):
        put(x, 0, [])
    # an object blocks only on its solid parts, not on the hexes its sprite overlaps
    tree, big = obj(vm["terr"], guid=g_terr, solid=(0,)), obj(vm["terr"], guid=g_terr, solid=(0, 1))
    wl, hs1 = obj(vm["wall"], hp=5), obj(vm["house"], hp=5, solid=(0,))
    put(20, 20, [tree]); put(20, 19, [tree], hn=[1])
    put(24, 20, [big]); put(24, 19, [big], hn=[1])
    put(28, 20, [wl]); put(28, 19, [wl], hn=[1])
    put(32, 20, [hs1]); put(33, 20, [hs1], hn=[2])
    w32(BSS + O_XPL, 0)
    call(A["bmap_build"], eax=L)
    sb = lambda x, y: (r8(BSS + O_BMAP + (y * W + x) // 8) >> ((y * W + x) % 8)) & 1
    wb = lambda x, y: (r8(BSS + O_WMAP + (y * W + x) // 8) >> ((y * W + x) % 8)) & 1
    got = (sb(20, 20), sb(20, 19), sb(24, 19), wb(28, 20), wb(28, 19), sb(32, 20), sb(33, 20))
    check("bitmap: a tree, a wall and a house block on their own hex only, not where their sprites "
          "reach; a part the terrain list marks used blocks too", got == (1, 0, 1, 1, 0, 1, 0))
    mu.reg_write(UC_X86_REG_EDI, F(28, 19)); mu.reg_write(UC_X86_REG_EBX, 0)
    sp = STACK_TOP - 4; w32(sp, MAGIC); mu.reg_write(UC_X86_REG_ESP, sp)
    mu.emu_start(A["iswall"], MAGIC, count=100_000)
    check("iswall: a wall's sprite hex is not a wall hex", mu.reg_read(UC_X86_REG_EAX) == 0)
    for h in ((20, 20), (20, 19), (24, 20), (24, 19), (28, 20), (28, 19), (32, 20), (33, 20)):
        put(h[0], h[1], [])
    # multi-hex buildings are explored whole
    a, b = obj(vm["wall"], hp=5), obj(vm["door"], hp=5)
    hs, tr = obj(vm["house"], hp=5, solid=(0,)), obj(vm["terr"], guid=g_terr, solid=(0,))
    put(5, 5, [a]); put(6, 5, [a, b], hn=[1, 6]); put(7, 5, [b]); put(10, 5, [hs])
    put(11, 5, [hs], hn=[2]); put(14, 5, [tr]); put(15, 5, [tr], hn=[2])
    for x in range(3, 18):
        w32(F(x, 5) + 0x18, 0)
    w32(F(5, 5) + 0x18, 0x4001); w32(F(10, 5) + 0x18, 0x0004); w32(F(14, 5) + 0x18, 0x0002)
    w32(BSS + O_XPL, 0)
    call(A["bmap_build"], eax=L)
    first = call(A["wclose"])
    got = {x: r32(F(x, 5) + 0x18) & 0xFFFF for x in (5, 6, 7, 10, 11, 14, 15)}
    check("wclose: an explored wall and house reach the hexes their sprites cover; the gate whose "
          "own hex is unexplored, and a tree, give nothing; bits 12-15 not carried",
          first == 1 and got == {5: 0x4001, 6: 1, 7: 0, 10: 4, 11: 4, 14: 2, 15: 0})
    check("wclose: nothing left to close -> 0", call(A["wclose"]) == 0)
    for x in range(3, 18):
        put(x, 5, []); w32(F(x, 5) + 0x18, 0)

    def reset():
        for y in range(H):
            for x in range(W):
                f = F(x, y)
                w8(f + 0xD, 0); w32(f + 0x18, 0); w8(f + 0x14, 0)

    def nbrs(h):
        return [(h[0] + dx, h[1] + dy) for dx, dy in (DELTAS_ODD if h[0] & 1 else DELTAS_EVEN)]

    def ref_flood(block, border, seeds):
        allh = {(x, y) for x in range(W) for y in range(H)}
        reg, st = set(seeds), []
        for sd in seeds:
            st += nbrs(sd)
        while st:
            h = st.pop()
            if h in reg or h in block or h in border or h not in allh:
                continue
            reg.add(h); st += nbrs(h)
        return reg | {h for h in block if any(n in reg for n in nbrs(h))}

    def unit(h, p, r=3, nv=0):
        u = alloc(0x80)
        w32(u, UV); w8(u + 0x45, p); sight(u, r, nv)
        hs = alloc(0x20)
        w32(hs + 4, F(*h))
        w32(u + 0x60, hs)
        return u

    def ref_inside(wall, border):
        allh = {(x, y) for x in range(W) for y in range(H)}
        ins, st, c = set(), [(W // 2, H // 2)], (W // 2, H // 2)
        if c not in wall and c not in border:
            while st:
                h = st.pop()
                if h in ins or h in wall or h in border or h not in allh:
                    continue
                ins.add(h); st += nbrs(h)
        out, st = set(), list(border - wall)
        while st:
            h = st.pop()
            if h in out or h in wall or h not in allh:
                continue
            out.add(h); st += nbrs(h)
        return ins | (allh - out - wall) | wall

    sys.path.insert(0, os.path.join(P.GAME, "Zig Modding Tools"))
    import zig_hsm as Z
    FAKE = alloc(0x200)
    w32(FAKE + 0x100, stub("ret"))

    def pat(x, y):          # the engine's bit 0x02 and other scripts' 0x20-0x80, set before the floods
        return (0x02 if (3 * x + y) % 4 == 0 else 0) | (0xE0 if (x + 5 * y) % 7 == 0 else 0)

    def load_walls(fn):
        reset()
        m = Z.Map(os.path.join(P.GAME, "TCMaps", fn))
        wall, border, wobj = set(), set(), {}
        for idx, rec in enumerate(m.records(0)):
            x, y = idx % W, idx // W
            for _tag, cls, _g in Z.record_children(rec):
                if cls in (0x220505, 0x220507):
                    o = obj(vm["wall"] if cls == 0x220505 else vm["door"], hp=1)
                    put(x, y, [o]); wall.add((x, y)); wobj[(x, y)] = o
                if cls == 0x20558:
                    w8(F(x, y) + 0x14, BORDER); border.add((x, y))
        for y in range(H):
            for x in range(W):
                w8(F(x, y) + F_FLAGS, pat(x, y))
        call(A["fogon"], eax=M, ecx=FAKE, edx=1)
        return wall, border, wobj

    def flags_clean(units=()):
        """scratch 0x04/0x08/0x10 clear; 0x02 and 0x20-0x80 as set before (0x02 also on units)."""
        return all(r8(F(x, y) + F_FLAGS) & 0xFE == pat(x, y) | (2 if (x, y) in units else 0)
                   for y in range(H) for x in range(W))

    # 1b. inside/outside on the real walled templates
    for fn in ("0126c000.HSM", "0xxxc000.hsm", "TFort000.hsm", "023xc000.HSM"):
        wall, border, _w = load_walls(fn)
        got = {(x, y) for y in range(H) for x in range(W) if r8(F(x, y) + F_FLAGS) & 1}
        want = ref_inside(wall, border)
        check("inside map %s: %d inside hexes == reference, scratch bits cleared, 0x02/0xE0 kept"
              % (fn, len(want) - len(wall)), got == want and flags_clean())
    # 1c. one-way walls, the start flood and destroyed walls on 0126c000 with scattered trees
    wall, border, wobj = load_walls("0126c000.HSM")
    inside = ref_inside(wall, border)
    random.seed(11)
    trees = set()
    while len(trees) < 80:
        h = (random.randrange(W), random.randrange(H))
        if h not in wall and h not in border and _dist(h, (W // 2, H // 2)) > 2:
            put(h[0], h[1], [obj(vm["terr"], guid=g_terr)]); trees.add(h)
    pocket = next(h for h in sorted((x, y) for x in range(W) for y in range(H))
                  if h not in inside and h not in border and h not in trees
                  and min(_dist(h, w) for w in wall) > 3 and min(_dist(h, b) for b in border) > 3
                  and not any(n in trees for n in nbrs(h)))
    for n in nbrs(pocket):
        put(n[0], n[1], [obj(vm["terr"], guid=g_terr)]); trees.add(n)
    w32(BSS + O_XPL, 0)
    call(A["bmap_build"], eax=L)
    random.seed(5)
    near = [h for h in sorted((x, y) for x in range(W) for y in range(H))
            if h not in border and any(_dist(h, w) <= 4 for w in sorted(wall)[::3])]
    bad = crossing = 0
    for _ in range(3000):
        c, t = random.choice(near), random.choice(near)
        if _dist(c, t) > 12 or c in wall or c in trees:
            continue
        vin = 1 if c in inside else 0
        w32(BSS + O_VIN, vin)
        want = model_los(trees if vin else trees | wall, c, t)
        if call(A["los"], args=(c[0], c[1], t[0], t[1])) != int(want):
            bad += 1
        crossing += model_los(trees, c, t) != model_los(trees | wall, c, t)
    check("one-way walls: los == model on 3000 pairs (%d mismatches, %d cross a wall)" % (bad, crossing),
          bad == 0 and crossing > 100)
    free = [h for h in sorted((x, y) for x in range(W) for y in range(H))
            if h not in wall and h not in trees and h not in border]
    p1 = [(W // 2, H // 2), (W // 2 + 1, H // 2)]
    p2 = [h for h in free if h not in inside and h != pocket][::97][:2]
    us = [unit(h, 1) for h in p1] + [unit(h, 2) for h in p2] + [obj(vm["wall"], hp=1)]
    w32(DATA, len(us))
    for i, u in enumerate(us):
        w32(DATA + 0x40 + 4 * i, u)
    for h in p1 + p2:       # placed units: the engine's "a unit here" (TTacticalCombatUnitHS.UpdateMapField)
        w8(F(*h) + F_FLAGS, r8(F(*h) + F_FLAGS) | 2)
    w8(M + 0x30, 0)
    call(A["worldflood"], eax=M)
    for p, seeds, blk, where in ((1, p1, set(), "inside, over the walls"), (2, p2, wall, "outside")):
        got = {(x, y) for y in range(H) for x in range(W) if r32(F(x, y) + 0x18) & (1 << (p - 1))}
        want = ref_flood(blk, border, seeds)
        check("start flood: player %d (%s) explores %d hexes == reference, trees passed"
              % (p, where, len(want)), got == want and pocket in got)
    check("start flood: inside bits kept, scratch bits cleared, 0x02 (units) and 0xE0 kept, "
          "static scene flagged",
          {(x, y) for y in range(H) for x in range(W) if r8(F(x, y) + F_FLAGS) & 1} == inside
          and flags_clean(set(p1 + p2)) and r8(M + 0x30) == 1)
    for y in range(H):
        for x in range(W):
            w32(F(x, y) + 0x18, r32(F(x, y) + 0x18) & 0xFFFF0000)
    w8(COMBAT + 0x40, 1)
    call(A["worldflood"], eax=M)
    check("start flood: nothing inside an exploration site",
          not any(r32(F(x, y) + 0x18) & 0xFFFF for y in range(H) for x in range(W)))
    w8(COMBAT + 0x40, 2)

    def counts_model(us, standing=True):
        want = {}
        for x, y, r in us:
            blk = trees if (x, y) in inside or not standing else trees | wall
            for ty in range(H):
                for tx in range(W):
                    if _dist((x, y), (tx, ty)) <= SIGHT_MUL * r and model_los(blk, (x, y), (tx, ty)):
                        want[(tx, ty)] = want.get((tx, ty), 0) + 1
        return want

    def counts():
        return {(x, y): r8(F(x, y) + 0x1A) for y in range(H) for x in range(W) if r8(F(x, y) + 0x1A)}
    seat_units = [(W // 2, H // 2)] + [h for h in free if h not in inside and h in near][:6:3] + \
                 [h for h in free if h in inside and h in near][::40][:3]
    us = [unit(h, 3) for h in seat_units]
    w32(DATA, len(us))
    for i, u in enumerate(us):
        w32(DATA + 0x40 + 4 * i, u)
    w32(BSS + O_SIG, 0)
    call(A["fog_update"], eax=M)
    n_in = sum(1 for h in seat_units if h in inside)
    check("one-way walls: fog counters == model (%d units inside, %d outside)"
          % (n_in, len(seat_units) - n_in), counts() == counts_model([(x, y, 3) for x, y in seat_units]))
    def explored3():
        return {(x, y) for y in range(H) for x in range(W) if r32(F(x, y) + 0x18) & 4}

    def explore_model(gone=(), who=seat_units):
        got = set()
        for c in who:
            blk = set() if c in inside else wall - set(gone)
            got |= {(tx, ty) for ty in range(H) for tx in range(W)
                    if _dist(c, (tx, ty)) <= SIGHT_MUL * 3 + EXPLORE_BUF and model_los(blk, c, (tx, ty))}
        return got
    for y in range(H):
        for x in range(W):
            w32(F(x, y) + 0x18, r32(F(x, y) + 0x18) & 0xFFFF0000)
    call(A["reexplore"], eax=M)
    base = explore_model()
    check("reexplore: every unit's explore == model (%d hexes)" % len(base), explored3() == base)
    att = [h for h in free if h not in inside and h in near][:6:3]
    ua = [unit(h, 3) for h in att]
    w32(DATA, len(ua))
    for i, u in enumerate(ua):
        w32(DATA + 0x40 + 4 * i, u)
    for y in range(H):
        for x in range(W):
            w32(F(x, y) + 0x18, r32(F(x, y) + 0x18) & 0xFFFF0000)
    call(A["reexplore"], eax=M)
    base = explore_model(who=att)
    gain = {w: len(explore_model((w,), att) - base) for w in sorted(wall)}
    w = max(gain, key=gain.get)
    frame = alloc(0x20) + 0x10
    w32(frame - 8, 0); w32(frame - 4, wobj[w])
    eax = call(A["wallhp"], ecx=0xC1C1C1C1, ebp=frame)
    regs = (eax, mu.reg_read(UC_X86_REG_EDX), mu.reg_read(UC_X86_REG_ECX))
    want = base | explore_model((w,), att)
    check("wallhp: a wall at %s dropping to 0 explores the %d hexes behind it, HP written 0"
          % (w, len(want - base)), explored3() == want and len(want) > len(base)
          and r32(wobj[w] + HP_OFF) == 0 and regs == (0, wobj[w], 0xC1C1C1C1))
    for y in range(H):
        for x in range(W):
            w32(F(x, y) + 0x18, r32(F(x, y) + 0x18) & 0xFFFF0000)
    call(A["wallhp"], ebp=frame)
    w2 = sorted(wall - {w})[0]
    w32(frame - 8, 5); w32(frame - 4, wobj[w2])
    eax = call(A["wallhp"], ebp=frame)
    check("wallhp: no explore when already 0 or not dropping to 0, HP left to the setter",
          not explored3() and eax == 5 and r32(wobj[w2] + HP_OFF) == 1)
    w32(wobj[w] + HP_OFF, 1)
    w32(DATA, len(us))
    for i, u in enumerate(us):
        w32(DATA + 0x40 + 4 * i, u)
    for o in wobj.values():
        w32(o + HP_OFF, 0)
    call(A["fog_update"], eax=M)
    check("destroyed walls block nobody (recount on the wall change)",
          counts() == counts_model([(x, y, 3) for x, y in seat_units], standing=False))
    w32(DATA, 0)
    reset()
    # 1c. an explored hex nobody sees keeps its decorations, never its units or effects
    LOGSTUB = stub("mov ecx, dword ptr [%#x]\nmov dword ptr [ecx*4 + %#x], eax\ninc dword ptr [%#x]\nret"
                   % (LOG, LOG + 4, LOG))
    for va in (DECOR["corpse"][0], DECOR["wall"][0], 0x00412D08, 0x00412028):   # + unit HS, fx
        w32(va + 0xF0, LOGSTUB)
    c_o, w_o = obj(DECOR["corpse"][0]), obj(DECOR["wall"][0], hp=0)
    u_o, fx_o = obj(0x00412D08), obj(0x00412028)
    put(10, 10, [c_o, u_o, w_o, fx_o], dynamic=4)
    w32(F(10, 10) + 0x18, 1 << 2)                 # explored by player 3, counter 0
    w32(BSS + O_SIG, 0)
    call(A["uds"], eax=M)
    n = r32(LOG)
    check("fogged hex: wall and corpse drawn, unit and effect not",
          [r32(LOG + 4 + 4 * i) for i in range(n)] == [w_o, c_o])
    reset()
    # 2. bitmap + line of sight against the model on a random field
    random.seed(23)
    block, solid = set(), set()
    for y in range(H):
        for x in range(W):
            if random.random() < 0.15:
                block.add((x, y))
                rock = random.random() < 0.5
                if rock:
                    solid.add((x, y))
                put(x, y, [obj(UV), obj(vm["iso" if rock else "obst"])])
    w32(BSS + O_XPL, 0)
    call(A["bmap_build"], eax=L)
    check("bitmap: %d blocking cells counted" % len(block), r32(BSS + O_NB) == len(block))
    bad = 0
    for _ in range(3000):
        c = (random.randrange(W), random.randrange(H))
        t = (random.randrange(W), random.randrange(H))
        if _dist(c, t) > 14:
            continue
        if call(A["los"], args=(c[0], c[1], t[0], t[1])) != int(model_los(block, c, t)):
            bad += 1
    check("los == model on 3000 random pairs (%d mismatches)" % bad, bad == 0)
    # 3. fog counters through fog_update
    units = [(5, 5, 3, 3), (12, 8, 5, 3), (20, 20, 2, 3), (30, 10, 6, 1), (8, 25, 4, 2)]   # x y r player
    objs = []
    for x, y, r, p in units:
        u = alloc(0x80)
        w32(u, UV); w8(u + 0x45, p); sight(u, r)
        hs = alloc(0x20)
        w32(hs + 4, F(x, y))
        w32(u + 0x60, hs)
        objs.append(u)
    objs.append(obj(vm["wall"], hp=1))          # a non-unit object in the list
    w32(DATA, len(objs))
    for i, o in enumerate(objs):
        w32(DATA + 0x40 + 4 * i, o)
    def model_counts(us, site=False):
        want = {}
        for x, y, r, p in us:
            if p != 3:
                continue
            rad = (r + 1) // 2 if site else SIGHT_MUL * r
            for ty in range(H):
                for tx in range(W):
                    if _dist((x, y), (tx, ty)) <= rad and model_los(block, (x, y), (tx, ty)):
                        want[(tx, ty)] = want.get((tx, ty), 0) + 1
        return want

    def counts():
        return {(x, y): r8(F(x, y) + 0x1A) for y in range(H) for x in range(W) if r8(F(x, y) + 0x1A)}
    w32(BSS + O_SIG, 0)
    call(A["fog_update"], eax=M)
    want = model_counts(units)
    check("fog counters == model (%d hexes seen)" % len(want), counts() == want)
    w8(F(5, 5) + 0x1A, 77)
    call(A["fog_update"], eax=M)
    check("unchanged signature skips the recount", r8(F(5, 5) + 0x1A) == 77)
    w32(r32(objs[0] + 0x60) + 4, F(6, 5))
    w8(F(6, 5) + 0x10, 6)
    call(A["fog_update"], eax=M)
    moved = [(6, 5, 3, 3)] + units[1:]
    check("a moved unit triggers a full recount", counts() == model_counts(moved))
    w32(r32(objs[0] + 0x60) + 4, F(5, 5))
    w32(BSS + O_SIG, 0)
    call(A["fog_update"], eax=M)
    check("moved back: counters == model again", counts() == want)
    w32(BSS + O_SEAT, 7); w8(M + 0x30, 0); w32(USS, 0)
    call(A["fog_update"], eax=M)
    n1 = r32(USS)
    call(A["fog_update"], eax=M)
    check("seat change: the static scene is rebuilt at once, never flagged from inside ShowScene",
          n1 == 1 and r32(USS) == 1 and r8(M + 0x30) == 0)
    # 4. explore
    for y in range(H):
        for x in range(W):
            w32(F(x, y) + 0x18, r32(F(x, y) + 0x18) & 0xFFFF0000)
    w8(M + 0x30, 0)
    ret = call(A["explore"], eax=M, edx=12, ecx=8, args=(SIGHT_MUL * 3, 3, 0))
    wantx = {(tx, ty) for ty in range(H) for tx in range(W)
             if _dist((12, 8), (tx, ty)) <= SIGHT_MUL * 3 + EXPLORE_BUF and model_los(solid, (12, 8), (tx, ty))}
    gotx = {(x, y) for y in range(H) for x in range(W) if r32(F(x, y) + 0x18) & (1 << 2)}
    behind = {h for h in wantx if not model_los(block, (12, 8), h)}
    check("explore: player 3 bits == model, radius %d x 3 + %d, rock blocks, obstacles do not "
          "(%d hexes, %d behind obstacles)" % (SIGHT_MUL, EXPLORE_BUF, len(wantx), len(behind)),
          gotx == wantx and behind)
    check("explore: returns 1, static scene flagged, signature cleared",
          ret == 1 and r8(M + 0x30) == 1 and r32(BSS + O_SIG) == 0)
    others = {(x, y) for y in range(H) for x in range(W) if r32(F(x, y) + 0x18) & 0xFFFB & 0xFFFF}
    check("explore: no other player's bit touched", not others)
    check("explore: second call reports nothing new",
          call(A["explore"], eax=M, edx=12, ecx=8, args=(SIGHT_MUL * 3, 3, 0)) == 0)
    check("explore: player 0 does nothing",
          call(A["explore"], eax=M, edx=12, ecx=8, args=(SIGHT_MUL * 3, 0, 0)) == 0)
    # 4b. combat sight: 3 x (3 + Vision), halved (rounded down) in a site without Night Vision
    cs = [(kind, r, nv) for kind in (2, 1) for r in (3, 4, 5, 6) for nv in (0, 1)]
    got_cs = {}
    for kind, r, nv in cs:
        w8(COMBAT + 0x40, kind)
        u = alloc(0x80); w32(u, UV); sight(u, r, nv)
        got_cs[(kind, r, nv)] = call(A["csight"], eax=u)
    want_cs = {(k, r, nv): (r if nv else (r + 1) // 2) if k == 1 else 3 * r for k, r, nv in cs}
    check("csight: world 3 x sight; site 3 + Vision, halved and rounded up without Night Vision "
          "(3 -> 9 / 2, 4 -> 12 / 2, 5 -> 15 / 3)",
          got_cs == want_cs and (got_cs[(1, 3, 0)], got_cs[(1, 4, 0)], got_cs[(1, 5, 0)]) == (2, 2, 3))
    w8(COMBAT + 0x40, 1)
    for y in range(H):
        for x in range(W):
            w32(F(x, y) + 0x18, r32(F(x, y) + 0x18) & 0xFFFF0000)
    call(A["explore"], eax=M, edx=12, ecx=8, args=(2, 3, 0))
    wants = {(tx, ty) for ty in range(H) for tx in range(W)
             if _dist((12, 8), (tx, ty)) <= 2 + EXPLORE_BUF and model_los(block, (12, 8), (tx, ty))}
    gotx = {(x, y) for y in range(H) for x in range(W) if r32(F(x, y) + 0x18) & (1 << 2)}
    check("exploration site: explore radius 2 + %d, obstacles block (%d hexes)"
          % (EXPLORE_BUF, len(wants)), gotx == wants and len(wants) < len(wantx))
    call(A["fog_update"], eax=M)
    wantc = model_counts(units, site=True)
    check("exploration site: fog counters == model at sight halved and rounded up, recounted on the kind "
          "change (%d hexes)" % len(wantc), counts() == wantc)
    w8(COMBAT + 0x40, 2)
    call(A["fog_update"], eax=M)
    check("world battle again: fog counters back at %d x sight" % SIGHT_MUL, counts() == want)
    call(A["explore"], eax=M, edx=12, ecx=8, args=(SIGHT_MUL * 3, 3, 0))
    # 5. uds: copies exactly the explored and seen hexes, in vanilla order
    call(A["explore"], eax=M, edx=5, ecx=5, args=(SIGHT_MUL * 3, 3, 0))
    call(A["explore"], eax=M, edx=20, ecx=20, args=(SIGHT_MUL * 2, 3, 0))
    w32(BSS + O_SIG, 0)
    call(A["uds"], eax=M)
    n = r32(LOG)
    logged = [r32(LOG + 4 + 4 * i) for i in range(n)]
    order = [F(x, y) for x in range(W) for y in range(H - 1, -1, -1)
             if (r32(F(x, y) + 0x18) & 4) and r8(F(x, y) + 0x1A)]
    check("uds: %d hexes drawn, exactly explored-and-seen, vanilla order" % len(order), logged == order)
    w8(M + 0xA5, 0xFF)
    call(A["uds"], eax=M)
    check("uds: no seated player -> HSEngine base routine", r32(LOG) == 0xBA5E)
    w8(M + 0xA5, 3); w8(M + 0xC9, 0)
    call(A["uds"], eax=M)
    check("uds: exploration off -> vanilla routine", r32(LOG) == 0x7A7A)
    w8(M + 0xC9, 1)
    # 6. seen / aispot / hover / drawfog
    seen_f = next(F(x, y) for x in range(W) for y in range(H)
                  if (r32(F(x, y) + 0x18) & 4) and r8(F(x, y) + 0x1A))
    fog_f = next(F(x, y) for x in range(W) for y in range(H)
                 if (r32(F(x, y) + 0x18) & 4) and not r8(F(x, y) + 0x1A))
    dark_f = next(F(x, y) for x in range(W) for y in range(H) if not (r32(F(x, y) + 0x18) & 4))
    check("seen: nil 0, seen 1, fogged 0, unexplored 0",
          [call(A["seen"], eax=f, edx=3) for f in (0, seen_f, fog_f, dark_f)] == [0, 1, 0, 0])
    w8(M + 0xA5, 0xFF)
    check("seen: watching non-participant sees everything", call(A["seen"], eax=dark_f, edx=-1) == 1)
    w8(M + 0xA5, 3)
    check("aispot: open battle -> 1 everywhere", call(A["aispot"], eax=dark_f, edx=3) == 1)
    w8(COMBAT + 0x40, 1)
    check("aispot: exploration site -> explored bit",
          [call(A["aispot"], eax=f, edx=3) for f in (fog_f, dark_f, 0)] == [1, 0, 0])
    w8(COMBAT + 0x40, 2)
    frame = alloc(0x40) + 0x20                  # EvalBattle's ebp; [ebp-0xC] = ring index
    w8(DATA + 0x31, 1)                          # the AI now plays the seated player (Space, Auto)
    w32(frame - 0xC, 0)
    check("aispot: AI playing the seat, unit's own hex -> seen only",
          [call(A["aispot"], eax=f, edx=3, ebp=frame) for f in (seen_f, fog_f, dark_f, 0)] == [1, 0, 0, 0])
    w32(frame - 0xC, 3)
    check("aispot: AI playing the seat, ring hexes never count",
          call(A["aispot"], eax=seen_f, edx=3, ebp=frame) == 0)
    w8(COMBAT + 0x40, 1)
    w32(frame - 0xC, 0)
    check("aispot: AI playing the seat inside a site -> seen, not merely explored",
          [call(A["aispot"], eax=f, edx=3, ebp=frame) for f in (seen_f, fog_f)] == [1, 0])
    w8(COMBAT + 0x40, 2); w8(DATA + 0x31, 2)
    for f in (seen_f, fog_f, dark_f):
        w32(f, FV)
    check("hover: seen hex reaches the real lookup", call(A["hover"], eax=seen_f, edx=0x220104, ecx=FV) == 0x55AA)
    check("hover: fogged and unexplored hexes find nothing",
          [call(A["hover"], eax=f, edx=0x220104, ecx=FV) for f in (fog_f, dark_f)] == [0, 0])
    w32(LOG, 0)
    call(A["drawfog"], eax=M)
    check("drawfog: seated player -> DrawFog", r32(LOG) == 0xD4A7)
    w32(LOG, 0); w8(M + 0xA5, 0xFF)
    call(A["drawfog"], eax=M)
    check("drawfog: no seated player -> skipped", r32(LOG) == 0)
    w8(M + 0xA5, 3)
    # 6. move orders: explored hexes take them, the planner ignores units the player cannot see
    for f in (seen_f, fog_f, dark_f):
        w32(f, 0)
    check("xpl: nil 0, seen 1, fogged but explored 1, unexplored 0",
          [call(A["xpl"], eax=f, edx=3) for f in (0, seen_f, fog_f, dark_f)] == [0, 1, 1, 0])
    LOG2 = alloc(0x40)
    stub("mov dword ptr [%#x], eax\nmov dword ptr [%#x], edx\nmov dword ptr [%#x], ecx\n"
         "push eax\nmov eax, dword ptr [esp + 8]\nmov dword ptr [%#x], eax\n"
         "mov eax, dword ptr [esp + 0xc]\nmov dword ptr [%#x], eax\n"
         "mov eax, dword ptr [%#x]\nmov dword ptr [%#x], eax\npop eax\nmov eax, 0x77\nret 8"
         % (LOG2, LOG2 + 4, LOG2 + 8, LOG2 + 0xC, LOG2 + 0x10, BSS + O_PLAN, LOG2 + 0x14), CALC_ORIG)
    got = call(A["calcwrap"], eax=0x1111, edx=2, ecx=5, args=(0, 7))
    check("calcwrap: CalculateMovePath runs with the planning flag set, arguments intact, flag "
          "cleared after", got == 0x77 and [r32(LOG2 + 4 * i) for i in range(6)] == [0x1111, 2, 5, 0, 7, 1]
          and r32(BSS + O_PLAN) == 0)
    w32(BSS + O_PLAN, 1)
    call(A["aispot"], eax=seen_f, edx=3)
    check("aispot: an AI turn clears the planning flag", r32(BSS + O_PLAN) == 0)
    LOG3 = alloc(0x40)
    stub("mov dword ptr [%#x], 0xc0\nmov dword ptr [%#x], edx\nmov dword ptr [%#x], ecx\nret"
         % (LOG3, LOG3 + 4, LOG3 + 8), CANON_ORIG)
    stub("mov dword ptr [%#x], 0xd4\nmov eax, 0x1234\nret" % LOG3, PREV[0])

    def mover(p):
        u = unit((1, 1), p)
        hs = alloc(0x40); w32(hs + 0x1C, u); w32(hs + 4, F(1, 1))
        st = alloc(0x200); w32(st + 0x1E0, hs)
        rec = alloc(0x20); w32(rec, st); return rec
    occ = {}
    for name, f in (("seen", seen_f), ("fog", fog_f)):
        occ[name] = alloc(0x40); w32(occ[name] + 4, f)
    cost = alloc(0x20)

    def canon(o, rec, plan):
        w32(BSS + O_PLAN, plan); w32(LOG3, 0)
        call(A["canon"], eax=o, edx=rec, ecx=cost)
        return r32(LOG3) == 0xC0 and r32(LOG3 + 4) == rec and r32(LOG3 + 8) == cost
    mine, theirs = mover(3), mover(2)
    check("canon: planning my own move, an occupant I cannot see vetoes nothing; one I see, or "
          "outside planning, or another player's mover, reaches CanMoveOn",
          [canon(occ["fog"], mine, 1), canon(occ["seen"], mine, 1), canon(occ["fog"], mine, 0),
           canon(occ["fog"], theirs, 1)] == [False, True, True, True])

    def canover(o, rec, plan):
        w32(BSS + O_PLAN, plan); w32(LOG3, 0)
        return call(A["canover"], eax=o, edx=rec, ecx=cost), r32(LOG3)
    check("canover: a hidden occupant is passable; otherwise the previous CanMoveOver (%08X) answers"
          % PREV[0], [canover(occ["fog"], mine, 1), canover(occ["seen"], mine, 1),
                      canover(occ["fog"], mine, 0)] == [(1, 0), (0x1234, 0xD4), (0x1234, 0xD4)])
    w32(BSS + O_PLAN, 0)
    # 7. a plain move stops when its mover sees an occupied hex further along its path
    reset()
    for y in range(H):
        for x in range(W):
            w8(F(x, y) + 0x3C, 0xFF)
    stub("movzx ecx, dl\nmovzx eax, dh\nimul eax, eax, %d\nadd eax, ecx\nshl eax, 6\nadd eax, %#x\nret"
         % (W, fields), 0x004080E8)                                            # TCombatMoveTE.GetMapF
    w32(cell(XYLGET_T), stub("mov eax, dword ptr [eax + edx*4]\nret"))
    w32(cell(FPLAYER_T), stub("movzx eax, byte ptr [eax + 0x3c]\nret"))
    mv = unit((10, 10), 3)
    te = alloc(0x40); w32(te, MOVETE_VMT); w32(te + 0x1C, mv)
    frame = alloc(0x40) + 0x20
    w32(frame - 4, te)

    def path(cells):
        lst = alloc(4 * len(cells))
        for i, (x, y) in enumerate(cells):
            w32(lst + 4 * i, x | y << 8)
        w32(te + 0x14, lst); w32(te + 0x18, len(cells))
    east = [(16, 10), (15, 10), (14, 10), (13, 10), (12, 10), (11, 10)]
    path(east)

    def step():
        call(A["bmap_build"], eax=L)
        return call(A["stepchk"], eax=F(11, 10), ebp=frame) & 0xFF
    w8(F(11, 10) + 0x3C, 2)
    r_next = step()
    w8(F(11, 10) + 0x3C, 0xFF)
    r_free = step()
    w8(F(16, 10) + 0x3C, 2)
    r_seen = step()
    rocks = [(13, y) for y in range(5, 16)]
    for h in rocks:
        put(h[0], h[1], [obj(vm["iso"])])
    r_behind = step()
    for h in rocks:
        put(h[0], h[1], [])
    w32(te, 0x004077C0)                                                         # TCMeleeMoveTE
    r_melee = step()
    w32(te, MOVETE_VMT)
    path([(16, 10), (11, 10)][1:])
    r_last = step()
    w8(F(16, 10) + 0x3C, 0xFF)
    far = [(10 + k, 10) for k in range(SIGHT_MUL * 3 + 3, 0, -1)]
    path(far)
    w8(F(far[0][0], 10) + 0x3C, 2)
    r_far = step()
    w8(F(far[0][0], 10) + 0x3C, 0xFF)
    check("stepchk: next hex occupied -> its player; free path -> go; occupied hex in sight -> stop; "
          "behind rock, beyond sight, melee move or last step -> go",
          (r_next, r_free, r_seen, r_behind, r_far, r_melee, r_last) == (2, 0xFF, 0, 0xFF, 0xFF, 0xFF, 0xFF))
    print("EMULATION %s" % ("PASSED" if not fails else "FAILED: " + "; ".join(fails)))
    return not fails


V2_FOGON = (0x00424FD5, b"\xE8" + struct.pack("<i", 0x0043D030 - 0x00424FDA) + b"\x90",
            bytes.fromhex("ff9100010000"))


def clear_v2(argv):
    """The 2026-10-23 one-way-wall build hooked RandomMap's SetFogEnabled call at 0x424FD5 into the
    stub that is now startflood's.  Put it back to vanilla before --apply / --undo."""
    va, old, van = V2_FOGON
    d = bytearray(open(P.TARGET, "rb").read())
    o = P.va2off(d, va)
    if bytes(d[o:o + 6]) != old:
        return
    if not ({"--apply", "--undo"} & set(argv)):
        print("  v2 hook at %08X still installed -- --apply or --undo restores it" % va)
        return
    P.kill_aow()
    d[o:o + 6] = van
    open(P.TARGET, "wb").write(d)
    print("  v2 hook at %08X restored to vanilla" % va)


def main():
    if "--test" in sys.argv[1:]:
        sys.exit(0 if run_test() else 1)
    d = open(P.TARGET, "rb").read()
    check_static(d)
    thunks = resolve_thunks(d)
    tables = guid_tables()
    blobs, A = layout(thunks, tables)
    print("blocking guids: terrain %d, single hex %d, main structure %d" %
          tuple(len(tables[c]) for c in (RC_TERR, RC_SINGLE, RC_MAIN)))
    print("routines: " + ", ".join("%s %08X" % (r, A[r]) for r in ORDER))
    if "--emulate" in sys.argv[1:]:
        sys.exit(0 if run_emulate(d, blobs, A, tables) else 1)
    argv = [a for a in sys.argv[1:] if a != "--test"]
    clear_v2(argv)
    if migrate(argv):
        print("\n(dry run -- nothing written)")
        return
    if "--apply" in argv:
        snap = os.path.join(P.GAME, "backups", "AoWTCPCK.dpl.pre-tacticallos")
        if not os.path.exists(snap):
            os.makedirs(os.path.dirname(snap), exist_ok=True)
            import shutil
            shutil.copy2(P.TARGET, snap)
            print("snapshot: backups/AoWTCPCK.dpl.pre-tacticallos")
    run("build_tactical_los", hooks(), blobs, ZONE, INTERIOR, argv=argv,
        reloc_ok=(VMT_UDS, CALC_SLOT, CANON_SLOT, CANOVER_SLOT))


if __name__ == "__main__":
    main()
