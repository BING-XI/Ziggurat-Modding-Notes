#!/usr/bin/env python
r"""
build_flight_fall.py -- a unit that loses flight over Sky or Chasm falls to the next map level below
instead of dying (owner, 2026-10-27); a fall onto enemies starts a battle (step two, owner 2026-10-28);
a unit that loses its footing on water, lava, a mountain, Earth or Rock takes damage and is shunted
instead of dying (hazards, owner 2026-10-28).  AoWEPACK.dpl + AoWTCPCK.dpl.

THE RULES (owner's rulings 2026-10-27; 09-terrain-movement.md, "Falling")
  * Sky (0x0E) and Chasm (0x0B).  The fall lands on the same x, y one level down in the level
    order (Firmament 3 -> Surface 0 -> Caverns 1 -> Depths 2 -> Abyss 4, disabled levels skipped:
    build_fly_levels.py's DN table and the map mask [map+0x41C]).  A landing hex that is Sky or Chasm
    again falls on; no level below -> vanilla's "crushed" death.
  * Damage: (size + 1) x 2d10 per level fallen, size from GetUnitSize (VMT +0x178: a unit's
    resource size 0-3, a hero's base 1), PHYSICAL (owner 2026-10-28): no roll to hit, but
    immunity, protection and weakness apply as to any map hit (see HAZARDS).  0 HP -> dead.
  * A survivor that cannot stand on the landing hex's terrain (water for a walker, lava, rock) takes
    that terrain's hazard as well (HAZARDS; owner 2026-10-28, until then it died) and, if it lives,
    is shunted alone before the others land.
  * The survivors land together: a new party on the hex when it is empty, unowned and has no
    structure, or they join the faller's own party there (not moving, with room).  An ENEMY there
    (an army, a city or a structure: the hex's owner is at war with the faller, or independent)
    starts a battle (below).  Otherwise -- an allied or full party, a city or structure -- each
    survivor is shunted as Awaken Volcano shunts: the six neighbours on the landing level in a
    synced shuffled order, joining an own party (not moving, with room, where it can stand or with
    a transporter) or forming a new party on an empty unowned hex without a structure where it can
    stand; with no such hex it dies.
  * Units that can still stand where they were (flyers) stay; a transporter that can stand keeps
    its passengers (vanilla: nobody is flagged).
  * An airship's passengers fall the same way when it is destroyed over Sky or Chasm (owner,
    2026-10-27), in battle and on the world map (below).

THE HOOK  TArmy.ValidateTerrainEx @0x5578CC9C, after its gates ([map+0x3C] & 2 clear, [map+0x174]
  set: a live game) and the per-unit flags in BL (bit i = unit i cannot stand), before the
  drown / burn / crush loop:
    0x5578CD44  `mov eax,esi / call BeginUpdate` (7 B) -> jmp cave_entry
  Sky/Chasm -> fall(); any other terrain -> hazard() (HAZARDS); handled -> 0x5578CF3D (TArmy.Validate,
  which removes the dead and the empty party, then the function's own exit); not handled (no level
  below, an empty army) -> the displaced bytes and back to 0x5578CD4B, vanilla's kill.

AIRSHIP PASSENGERS (2026-10-27)
  In battle, a unit that cannot stand on the battle terrain and rides a transporter is cargo
  ([cu+0x54], TCombat.AddArmy, never a conquer object); TCombatUnit.ObjectDestroyed destroys it with
  its transport (vmt+0x120, "is lost with its transport").  It now stays aboard instead, on every
  terrain (2026-10-28; until then it fled over Sky/Chasm, and a fled object turns result 4 into
  9, "Battle Drawn"): the destroy call is skipped unless it is already dead or fled ([cu+0x47] & 9).
    0x557252DB  `call [edx+0x120]` (6 B) -> `nop / call ENT_CARGO` -- the return address stays
                0x557252E1, which build_combatlog_endings.py names "lost with its transport"; no
                passenger line is printed now.
  TCombatUnit.Finalize puts each survivor back with TAbstractUnit.Place on its party's hex (flags 2:
  that hex only), in passes 0 and 1 of TCombat.Finalize -- a passenger refused in pass 0 because its
  ship was not placed yet is retried in pass 1.  A pass-1 refusal over Sky or Chasm now falls:
    0x55724E25  `test eax,eax / je 0x55724F1F` (8 B) -> jmp ENT_FIN: Place returned 0, the pass ([esp+4],
                TCombat.Finalize's EBX, saved by the prologue) is 1, the party hex ([party+0xC/+0x10/
                +0x14]) -> fbplace() (a fall battle's attacker, below), else fp() when the unit
                cannot stand on that hex: over Sky or Chasm
                the same levels and damage as fall(), the hazard if it cannot stand below, then Place
                (flags 0, the player argument as vanilla: 0 for a player whose [+0x44] is 2) on the
                hex below, else on a neighbour in synced shuffled order; placed -> the vanilla
                success path 0x55724E2D (the combat object is freed), else 0x55724F1F (lost, as
                vanilla).  An ATTACKER's passenger over enemies is put back on its party's hex
                instead (fplace, no terrain test) and falls into a battle after this one.  On any
                other terrain fp() is the hazard: its dice and type, then a neighbour on the same
                level in synced shuffled order, else lost.
  On the world map nothing re-checks a party that loses its transport (a storm, map fire, Meteor
  Storm): TArmy.Validate just removes the dead.  At its end:
    0x5578D028  `call TAoWHSMap.UnlockGameOverEvent` -> call ENT_VEND: the displaced call, then, for a
                party on the map (its hex holds its own army HS) with a living unit that cannot
                stand there and no transporter that can -- on Sky or Chasm, or (2026-10-28) on any
                other hex unless the party is moving ([army+0x11] & 4: TArmyHS.MoveTo validates
                mid-step while boarding) -- TArmy.ValidateTerrain -> the hook above.  It recurses through Validate once more and finds nothing left to drop.
                Units in a battle are out of their armies (Finalize places them back), so this
                never acts mid-battle.  It runs only past ValidateTerrainEx's own gates (a live
                game: [map+0x3C] & 2 clear, [map+0x174] set), and BSS GUARD 0x558FAEF4 is held
                while its ValidateTerrain runs, so the nested Validate cannot loop.

STEP TWO -- A FALL ONTO ENEMIES IS A BATTLE (owner's rulings 2026-10-28)
  The fallers attack the hex below from the hex above, as a party attacks through a cave entrance
  (party position 7, TCombat.GetPartyPosition).  fall() takes the damage, then queues a vanilla
  TArmyCombatMoveTE with the two-node path [landing hex, hex above] through
  TTokenExecuter.AddSystemEvent, exactly as TArmyCombatMoveTE.CombatExecuted queues a winner's move
  into a conquered hex.  build_fly_levels.py's cave_vp makes TMoveControl.ValidPath accept that path
  (terrain only).  The TE is filled by mkte(), a copy of TMoveArmyTE.Setup without its movement-point
  cut (build_patch.py's TrueReachPos would refuse a faller with no MP).  A one-level fall waits in its
  own party (the selection is the fallers; vanilla splits them off at InitializeMove); a longer fall
  forms a party on the last Sky/Chasm hex above the landing hex, which must be empty.  The waiting
  party is held in a pending table (heap, 8 x {army, token-event stamp}; an entry lapses after 8
  completed token events) so a re-validation does not drop it twice; the table is full or the hex
  above is taken -> the old "blocked" rule.  So is an independent faller, or one whose player's
  [+0x44] is not 0: TArmyCombatMoveTE.CanMoveNext would end the TE without a battle.
  Vanilla SetupCombat then decides fast / tactical / ask, the hot-seat "You are being attacked"
  hand-over, network seats, the walkover against an empty city or structure and the capture.
  Auto-combat is forced ([te+0x39] = 1) in a network game, and for a human faller who is not the local
  seat ([map+0xA5]: another human's turn in hot-seat or PBEM) -- the cases vanilla never produces.
  A cancelled type choice fights in auto-combat.
  A fall battle is recognised everywhere by its geometry: the attacker stands on Sky or Chasm at the
  defender's x, y on another level (the TE's path, or the combat data [cd+0x14/0x18/0x1C] vs
  [cd+8/0xC/0x10]).  Vanilla never makes such a battle (no cave entrance is on Sky).
    0x5574A17E  TArmyCombatMoveTE.ProcessMove's `cmp [ebx+0x39],0 / je / mov eax,ebx / call
                ExecuteCombat` (13 B) -> jmp ENT_PM: for a fall TE, release the pending mark, a
                cancelled choice becomes auto, the TE waits a frame while another combat still exists
                ([map+0x120]; ProcessMove returns 1), build_razebattle_tower.py's FLAG_RAZENOFLEE (0x558FA806,
                read only by its cave_noflee on the auto-combat flee gate 0x557444A9) is held around
                the battle, and after an auto-combat that leaves the fallers on the hex above (no
                win) they are dropped again with NOBATTLE.  For any other battle that ends without a
                move-in, the attacker's party on its hex is re-checked (vcheck: waiting passengers).
    0x557489BC  TArmyCombatMoveTE.Validate's `call TMoveArmyTE.Validate` -> call ENT_VAL: a fall TE
                releases its pending mark; if it no longer validates (an enemy gone, a faller dead, the
                player can no longer attack),
                the party is dropped again with NOBATTLE and [te+0x28] is cleared so FinishMove does
                not touch it.
    0x55727BF5  TCombat.InitDefaultArmies' `mov byte [esi+0x40],2 / push edi` (5 B) -> jmp ENT_IDA:
                a fall battle keeps combat kind 0, so TRndTacHsm.RandomMap builds the landing hex's
                own map (a city's siege map) and its defender formation; kind 2 is the cave-entrance
                map variant.  combat+0x40 == 2 is read nowhere else.
    0x557497D6, 0x55749803  CombatExecuted's two `call CreateArmyMoveXYLTE` (the tactical winner's
                move-in, path-found, which cannot find a vertical step) -> call ENT_XYL: for a drop
                from Sky/Chasm onto the same x, y, mkte() builds the two-node move (combat type,
                [te+0x3A] = 1: no second battle, a city is entered and captured) and marks the party
                pending; any other move -> CreateArmyMoveXYLTE.
    0x55749913  CombatExecuted's epilogue (7 B) -> jmp ENT_CEX: after a manual fall battle without a
                move-in, the fallers left on the hex above are dropped again with NOBATTLE; after any
                other manual battle the attacker's party is re-checked (vcheck).
  TCombatUnit.Finalize puts a fall battle's attackers back on the hex above, where they cannot stand:
  fin's pass-1 refusal calls fbplace(), which places a side-0 unit of a fall battle there without the
  terrain test (fplace = TAbstractUnit.Place's body without CanPlace).  The vanilla aftermath then
  finds them there: an auto-combat winner walks on into the landing hex in the same TE.
  NOBATTLE (BSS 0x558FAEF5) makes fall() skip the damage (they fell already) and treat enemies as
  blocked, so a draw or a loss ends as the old rule: shunted or dead.

  No retreat:
    auto-combat  only attackers withdraw, at the flee gate 0x557444A9 (FLAG_RAZENOFLEE, above);
    manual       AoWTCPCK: the flee hexes (TFleeLocation, class 0x220528; TCombatMoveTE.
                 ExecuteDefaultMove's test, attackers only) and Surrender (TAoWCombatMap.Surrender,
                 the only maker of TCEndCombatTE):
      0x00408374  `mov edx,0x220528` (5 B) -> call tc_flee: in a fall battle the lookup asks for class
                  0x7FFFFFFF, which no hex holds, so no unit flees.  The flee hexes are still drawn.
      0x0041CC84  Surrender's prologue (6 B) -> jmp tc_sur: returns at once in a fall battle.
  Inside the walls:
    auto-combat  GetWallInBetween ignores party position 7: no wall between the fallers and anyone.
    manual       the attackers' party position 7 is drawn at edge 1 (TRndTacHsm.PlaceCombatUnits).
      0x00426FD7  TRndTacHsm.SetupUnit's facing code (9 B) -> jmp tc_dep: a fall battle's attacker,
                  when the battle has walls ([cd+0x50], the TCombatWall), takes the defender
                  formation's slot for direction 4 (tables 0x467024 / 0x4670E4, index 24 + slot) --
                  inside the city, on the far side from the defenders (direction 1) -- and faces
                  them (1).  Vanilla's nearest-free-hex walk settles the two slots both share.
    The fallers' party is never inside a city's footprint, so the city answers message 0x1123 with 0
    for it: party +0x18 stays 0 and TTacticalCombat.ValidateWallCombat passes.

HAZARDS -- LOSING ITS FOOTING ANYWHERE ELSE (owner's rulings 2026-10-28)
  Vanilla's drown / burn / crush loop set each unit that cannot stand to 0 HP and sent a TArmyEventLog
  ("Units drowned" for Water and Cave Water, "burned" for Lava, "crushed" for everything else) listing
  each unit's remaining HP as its damage.  Now hazard() deals typed damage instead, by the hex's
  terrain byte: Water 0 / Cave Water 0xA 3d10 physical, Lava 9 4d10 fire, anything else (a mountain,
  Earth, Rock, the border) 2d10 physical; no roll to hit, not size-dependent.  The survivors are
  shunted as the fall shunts (move_one: a neighbour on the same level), else they die.  The same
  event log is sent, built as vanilla builds it, with each unit's real HP loss.
  Typed damage: hit() calls TAbstractUnit.ExecuteDamageRole (0x55781AC4) with the dice total as both
  damage and FORCE, and its core roll is retargeted:
    0x55781B0D  `call AoWE.ExecuteDamageRole` (the 0..damage to-hit roll) -> call ENT_FORCE: FORCE
                (BSS 0x558FAEFC) set -> return it, else the vanilla roll.
  So immunity (VMT +0xEC: no damage), protection (+0xF0: halved, rounded up), build_weakness.py's
  weakness (0x55781B14), Spectral Wings' and Mistform's caves (build_airwater_ench.py 0x55781B1E,
  0x55781B37; a Mistform absorb is queued, not re-entrant) and build_firefeed.py's Living Flame heal
  (the entry) all apply; a negative result counts as 0.  The fall uses the same call, physical.
  Awaken Volcano still handles its own lava first (d20, its shunt); a unit it could not move now takes
  the lava hazard as well before it dies.

RNG: P1 SYNCED DRAW (12-re-toolchain.md section 4.10): TAoWHSMap.Random for the dice and the
neighbour shuffle, gated on replicated state only (the army, its units, the fields).  Flight is lost
inside token events (a dispel, an enchantment's upkeep, Mistform's absorb drained at
TArmy.Validate) and in TCombat.Finalize, the same contexts Awaken Volcano's shunt and the battle
results draw in.  Sites: RNG_SITES (checked against the assembled core).  Step two adds no draw of
its own; the queued TE makes vanilla's one Random(0xFFFFF) at TMoveTE.Execute on every machine.

Slots: AoWEPACK 0x558C6800-0x558C87FF, AoWTCPCK 0x00448000-0x004481FF, both exclusive.  BSS 0x558FAEF4
(GUARD), 0x558FAEF5 (NOBATTLE), 0x558FAEF8 (the pending table's pointer), 0x558FAEFC (FORCE).  PIC.
Entries are found by a 4-byte marker `CC 5A 46 n` placed before each (never executed).
Surgical --undo.

FORWARD HAZARDS
  * build_fly_levels.py's cave_vp is what validates the vertical path: undo it and every fall battle
    fails Validate, so the fallers drop with NOBATTLE (shunted or dead) -- no battle, nothing worse.
  * build_razebattle_tower.py owns the auto-combat flee gate; it has no --undo.
  * build_combatlog_endings.py hooks 0x4083B8 (flee) and 0x407E06 (surrender) in AoWTCPCK; the hooks
    here sit before them and change no return address.
  * TAbstractUnit.ExecuteDamageRole is shared: build_firefeed.py (entry), build_weakness.py
    (0x55781B14), build_airwater_ench.py (0x55781B1E, 0x55781B37) and this script (0x55781B0D, the
    core call) each own a site; none overlaps, and FORCE is 0 outside hit().

Unproven, static checks cannot reach it: a fall in game; the new party's map refresh on the other
level; no event-log or combat-log line is written for a fall itself; a passenger that stays aboard
a sunk ship until the battle ends (auto-combat and manual); every hazard in game; every step-two
path in game (the queued TE, the dialog, the manual battle, the inside-
walls deployment, a draw's drop), and none of hot-seat, PBEM or network.

    python build_scripts/build_flight_fall.py            dry run + state, both modules
    python build_scripts/build_flight_fall.py --apply
    python build_scripts/build_flight_fall.py --undo
    python build_scripts/build_flight_fall.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import run
from piccave import pic

EPACK = os.path.join(P.GAME, "AoWEPACK.dpl")
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")

SKY, CHASM, NO = 0x0E, 0x0B, 0xFF
DN_T = [1, 2, 4, 0, NO]                 # build_fly_levels.py's DN table: level -> the level below
MASK_OFF = 0x41C
DIE = 10
PLACE_FLAGS = 3

SLOT = (0x558C6800, 0x558C8800)
HOOK, HOOK_VAN, RESUME, HANDLED = 0x5578CD44, bytes.fromhex("8bc6e83965f7ff"), 0x5578CD4B, 0x5578CF3D

AOWHSMAP = 0x558FA040
STRUCT_CELL, ARMYHS_CELL = 0x55713BD8, 0x55713360
RANDOM, BEGINUPD, ENDUPD, OBJ_FREE = 0x5577827C, 0x55703284, 0x5570328C, 0x557010B8
CENTERHN, GETMAPLEVEL, LEVEL_GETFIELD = 0x55702694, 0x557020EC, 0x557020DC
HAS_HS, ARMY_ON, FIELD_GETPLAYER = 0x55702004, 0x55771EB0, 0x55771C98
UNIT_VALIDTERRAIN, ARMY_TRANSPORTER = 0x5577FFFC, 0x5578E00C
ARMY_GETUNIT, ADDUNITSEL = 0x5578309C, 0x5578E6B4
ARMYHS_CREATE, SETPLAYER, PLACEEX = 0x557908BC, 0x5578D690, 0x55791F58
SETSTATUS, CO_GETPLAYER, GETPLAYERS, PLACE = 0x557256BC, 0x557268E4, 0x557544D0, 0x557810FC
UNLOCK_GO, ARMY_VALIDATETERRAIN = 0x55776774, 0x5578CF70
FIN_OK, FIN_FAIL = 0x55724E2D, 0x55724F1F
GUARD = 0x558FAEF4                       # BSS byte: set while vcheck's ValidateTerrain runs
# step two
EXEC_COMBAT, MOVEARMY_VALIDATE, CREATE_XYL = 0x55749924, 0x55747C20, 0x5574A248
MOVETE_CREATE, CMTE_CELL = 0x55747960, 0x5571C994        # TMoveArmyTE.Create; TArmyCombatMoveTE class cell
XYL_CLEAR, XYL_ADD, ARMY_VALSEL, INTLIST_ADD = 0x55701CDC, 0x55701CCC, 0x5578D440, 0x55702E74
ADDSYSEV, GETDIPLREL, GETSIDE = 0x557036CC, 0x55750A10, 0x55726660
ISCLASS, FAST_CELL, PLACEHX, GETMEM = 0x557010C0, 0x5571D77C, 0x557025F4, 0x55701008
FLAG_NOFLEE = 0x558FA806                 # build_razebattle_tower.py's FLAG_RAZENOFLEE
NOBAT, PENDP = 0x558FAEF5, 0x558FAEF8    # BSS: NOBATTLE byte; the pending table's pointer
PM_BACK, PM_CANCEL, IDA_BACK = 0x5574A18B, 0x5574A199, 0x55727BFA
VMT_CMTE = 0x5571C9D4
# hazards (2026-10-28)
EXECDMGROLE, CORE_ROLL, FORCE_SITE = 0x55781AC4, 0x55725EAC, 0x55781B0D
FORCE = 0x558FAEFC                       # BSS dword: the amount the forced core roll returns (0 = off)
PHYS, FIRE = 0x80, 0x01                  # TDamageType bits dtPhysical, dtFire
HAZ = {"water": (3, PHYS), "lava": (4, FIRE), "other": (2, PHYS)}   # dice of d10, damage type
ALOG_CELL, ALOG_CREATE, ALOG_GAMEOVER = 0x557135E8, 0x5578BB6C, 0x5578BDDC
DISTLOC, BYTELIST_ADD = 0x557FE558, 0x55702EFC
LOADRES, TRANSLATE, LSTRASG, LSTRARRCLR = 0x55701210, 0x557249FC, 0x55701150, 0x55701148
RS_DROWN, RS_BURN, RS_CRUSH = 0x55707154, 0x5570715C, 0x55707164      # UnitsDrown/Burned/CrushedRStr
# the four synced draws in the assembled core (rng_audit --owners reads these literals)
RNG_SITES = {"dice (falls and hazards)": 0x558C72DF, "fp shuffle": 0x558C7607,
             "shunt shuffle": 0x558C7C54}


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


HOOKS2 = {   # site: (vanilla, marker, form)
    0x557252DB: (bytes.fromhex("ff9220010000"), 1, "nopcall"),
    0x55724E25: (bytes.fromhex("85c00f84f2000000"), 2, "jmp"),
    0x5578D028: (bytes.fromhex("e84797feff"), 3, "call"),
    0x5574A17E: (bytes.fromhex("807b390074158bc3") + call_to(0x5574A186, EXEC_COMBAT), 4, "jmp"),
    0x557489BC: (call_to(0x557489BC, MOVEARMY_VALIDATE), 5, "call"),
    0x55727BF5: (bytes.fromhex("c646400257"), 6, "jmp"),
    0x557497D6: (call_to(0x557497D6, CREATE_XYL), 7, "call"),
    0x55749803: (call_to(0x55749803, CREATE_XYL), 7, "call"),
    0x55749913: (bytes.fromhex("595a5d5f5e5bc3"), 8, "jmp"),
    FORCE_SITE: (call_to(FORCE_SITE, CORE_ROLL), 9, "call"),
}

# frame (ebp) of fall() and fp()
F_ARMY, F_MASK, F_X, F_Y, F_L, F_N, F_FIELD, F_I, F_CNT, F_UNIT = (0x00, 0x04, 0x08, 0x0C, 0x10, 0x14,
                                                                   0x18, 0x1C, 0x20, 0x24)
F_DMG, F_DICE, F_SURV, F_HS, F_DEST, F_TRY, F_SHUF, F_OX, F_OY, F_NF = (0x28, 0x2C, 0x30, 0x34, 0x38,
                                                                        0x3C, 0x40, 0x48, 0x4C, 0x50)
F_TER, F_OVL, F_PLAYER, F_PL, F_L0, F_HSB, F_MSKB = 0x54, 0x55, 0x58, 0x5C, 0x60, 0x64, 0x68
F_LOG, F_STR, F_UP, F_HP0, F_LOGP, F_KIND, F_TYPES, F_HDICE, F_RS = (0x6C, 0x70, 0x78, 0x98, 0xA0, 0xA4,
                                                                    0xA8, 0xAC, 0xB0)
F_SIZE = 0xB4


MARK = bytes([0xCC, 0x5A, 0x46])


def mark(n):
    return "    .byte 0xcc, 0x5a, 0x46, %d" % n


def tail():
    t = bytes(DN_T)
    return t + b"\x00" * (-len(t) % 4)


def core(va):
    src = f"""
    entry:
        mov  al, byte ptr [ebp - 1]
        cmp  al, {SKY:#x}
        je   e_fall
        cmp  al, {CHASM:#x}
        je   e_fall
        push eax
        pushad
        movzx ecx, byte ptr [ebp - 2]
        shl  ecx, 16
        mov  ch, byte ptr [ebp - 1]
        mov  cl, byte ptr [ebp + 8]
        mov  eax, esi
        movzx edx, bl
        call hazard
        mov  dword ptr [esp + 0x20], eax
        popad
        pop  eax
        test al, al
        je   e_van
        jmp  {HANDLED:#x}
    e_van:
        mov  eax, esi
        call {BEGINUPD:#x}
        jmp  {RESUME:#x}
    e_fall:
        push eax
        pushad
        mov  eax, esi
        movzx edx, bl
        call fall
        mov  dword ptr [esp + 0x20], eax
        popad
        pop  eax
        test al, al
        je   e_van
        jmp  {HANDLED:#x}

    fall:
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, {F_SIZE:#x}
        mov  ebp, esp
        mov  dword ptr [ebp + {F_ARMY:#x}], eax
        mov  dword ptr [ebp + {F_MASK:#x}], edx
        call get_anc
        mov  esi, eax
        cmp  byte ptr [ebx + {{NOBAT}}], 0
        jne  f_go
        call pend_has
        test al, al
        jne  f_done
    f_go:
        movzx eax, byte ptr [esi + 0x13]
        mov  dword ptr [ebp + {F_X:#x}], eax
        movzx eax, byte ptr [esi + 0x14]
        mov  dword ptr [ebp + {F_Y:#x}], eax
        movsx eax, byte ptr [esi + 0x15]
        mov  dword ptr [ebp + {F_L:#x}], eax
        mov  dword ptr [ebp + {F_L0:#x}], eax
        movsx eax, byte ptr [esi + 0x12]
        mov  dword ptr [ebp + {F_PLAYER:#x}], eax
        mov  eax, dword ptr [ebp + {F_X:#x}]
        mov  edx, dword ptr [ebp + {F_Y:#x}]
        mov  ecx, dword ptr [ebp + {F_L:#x}]
        call gf
        test eax, eax
        je   f_no
        mov  cl, byte ptr [eax + 0x14]
        mov  byte ptr [ebp + {F_TER:#x}], cl
        mov  cl, byte ptr [eax + 0x15]
        mov  byte ptr [ebp + {F_OVL:#x}], cl
        mov  dword ptr [ebp + {F_N:#x}], 0
    f_down:
        mov  eax, dword ptr [ebp + {F_L:#x}]
        mov  dword ptr [ebp + {F_PL:#x}], eax
        call below
        test eax, eax
        js   f_no
        mov  dword ptr [ebp + {F_L:#x}], eax
        inc  dword ptr [ebp + {F_N:#x}]
        mov  ecx, eax
        mov  eax, dword ptr [ebp + {F_X:#x}]
        mov  edx, dword ptr [ebp + {F_Y:#x}]
        call gf
        test eax, eax
        je   f_no
        mov  dword ptr [ebp + {F_FIELD:#x}], eax
        mov  cl, byte ptr [eax + 0x14]
        cmp  cl, {SKY:#x}
        je   f_down
        cmp  cl, {CHASM:#x}
        je   f_down

        mov  eax, dword ptr [ebp + {F_ARMY:#x}]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  dword ptr [ebp + {F_CNT:#x}], eax
        mov  dword ptr [ebp + {F_I:#x}], 0
    f_dmg:
        mov  eax, dword ptr [ebp + {F_I:#x}]
        cmp  eax, dword ptr [ebp + {F_CNT:#x}]
        jge  f_move
        mov  ecx, eax
        mov  edx, 1
        shl  edx, cl
        test dword ptr [ebp + {F_MASK:#x}], edx
        je   f_dnext
        mov  edx, eax
        mov  eax, dword ptr [ebp + {F_ARMY:#x}]
        call {ARMY_GETUNIT:#x}
        mov  dword ptr [ebp + {F_UNIT:#x}], eax
        cmp  byte ptr [ebx + {{NOBAT}}], 0
        jne  f_stand
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x178]
        movzx eax, al
        inc  eax
        imul eax, dword ptr [ebp + {F_N:#x}]
        shl  eax, 1
        call roll
        mov  edx, eax
        mov  ecx, {PHYS:#x}
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        call hit
    f_stand:
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        test al, al
        je   f_dnext
        mov  eax, dword ptr [ebp + {F_FIELD:#x}]
        mov  dl, byte ptr [eax + 0x14]
        mov  cl, byte ptr [eax + 0x15]
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        call {UNIT_VALIDTERRAIN:#x}
        test al, al
        jne  f_dnext
        cmp  byte ptr [ebx + {{NOBAT}}], 0
        jne  f_dnext
        mov  eax, dword ptr [ebp + {F_FIELD:#x}]
        mov  dl, byte ptr [eax + 0x14]
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        call hzhit
    f_dnext:
        inc  dword ptr [ebp + {F_I:#x}]
        jmp  f_dmg

    f_move:
        call stuck
        test eax, eax
        je   f_landers
        bsf  ecx, eax
        mov  dword ptr [ebp + {F_I:#x}], ecx
        mov  edx, ecx
        mov  eax, dword ptr [ebp + {F_ARMY:#x}]
        call {ARMY_GETUNIT:#x}
        mov  dword ptr [ebp + {F_UNIT:#x}], eax
        call move_one
        test al, al
        jne  f_move
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        xor  edx, edx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xe4]
        jmp  f_move
    f_landers:
        call scan
        mov  dword ptr [ebp + {F_SURV:#x}], eax
        test eax, eax
        je   f_done
        cmp  byte ptr [ebx + {{NOBAT}}], 0
        jne  f_land
        test byte ptr [esi + 0x11], 4
        jne  f_land
        mov  eax, dword ptr [ebp + {F_FIELD:#x}]
        mov  edx, dword ptr [ebp + {F_PLAYER:#x}]
        call enemy
        test al, al
        je   f_land
        call battle
        test al, al
        jne  f_done
    f_land:
        mov  eax, dword ptr [ebp + {F_FIELD:#x}]
        call {ARMY_ON:#x}
        test eax, eax
        je   f_lnew
        mov  eax, dword ptr [eax + 0x1c]
        test eax, eax
        je   f_shunt
        mov  dword ptr [ebp + {F_DEST:#x}], eax
        movsx ecx, byte ptr [eax + 0x12]
        cmp  ecx, dword ptr [ebp + {F_PLAYER:#x}]
        jne  f_shunt
        test byte ptr [eax + 0x11], 4
        jne  f_shunt
        mov  ecx, dword ptr [ebp + {F_SURV:#x}]
        mov  edx, dword ptr [ebp + {F_ARMY:#x}]
        call {ADDUNITSEL:#x}
        test al, al
        jne  f_shunt
        jmp  f_done
    f_lnew:
        mov  eax, dword ptr [ebp + {F_FIELD:#x}]
        mov  dword ptr [ebp + {F_NF:#x}], eax
        mov  eax, dword ptr [ebp + {F_X:#x}]
        mov  dword ptr [ebp + {F_OX:#x}], eax
        mov  eax, dword ptr [ebp + {F_Y:#x}]
        mov  dword ptr [ebp + {F_OY:#x}], eax
        mov  ecx, dword ptr [ebp + {F_SURV:#x}]
        call newparty
        test al, al
        jne  f_done
    f_shunt:
        call scan
        test eax, eax
        je   f_done
        bsf  ecx, eax
        mov  dword ptr [ebp + {F_I:#x}], ecx
        mov  edx, ecx
        mov  eax, dword ptr [ebp + {F_ARMY:#x}]
        call {ARMY_GETUNIT:#x}
        mov  dword ptr [ebp + {F_UNIT:#x}], eax
        call move_one
        test al, al
        jne  f_shunt
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        xor  edx, edx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xe4]
        jmp  f_shunt
    f_done:
        mov  eax, 1
        jmp  f_ret
    f_no:
        xor  eax, eax
    f_ret:
        add  esp, {F_SIZE:#x}
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret

    battle:
        mov  edx, dword ptr [ebp + {F_PLAYER:#x}]
        call can_attack
        test al, al
        je   bt_no
        mov  eax, dword ptr [ebp + {F_PL:#x}]
        cmp  eax, dword ptr [ebp + {F_L0:#x}]
        jne  bt_mid
        mov  eax, dword ptr [ebp + {F_X:#x}]
        mov  edx, dword ptr [ebp + {F_Y:#x}]
        mov  ecx, dword ptr [ebp + {F_L0:#x}]
        call gf
        test eax, eax
        je   bt_no
        call {ARMY_ON:#x}
        test eax, eax
        je   bt_no
        cmp  dword ptr [eax + 0x1c], esi
        jne  bt_no
        mov  dword ptr [ebp + {F_HSB:#x}], eax
        mov  eax, esi
        call pend_add
        test al, al
        je   bt_no
        mov  eax, dword ptr [ebp + {F_SURV:#x}]
        mov  dword ptr [ebp + {F_MSKB:#x}], eax
        jmp  bt_queue
    bt_mid:
        call pend_room
        test al, al
        je   bt_no
        mov  eax, dword ptr [ebp + {F_X:#x}]
        mov  edx, dword ptr [ebp + {F_Y:#x}]
        mov  ecx, dword ptr [ebp + {F_PL:#x}]
        call gf
        test eax, eax
        je   bt_no
        mov  dword ptr [ebp + {F_NF:#x}], eax
        call {ARMY_ON:#x}
        test eax, eax
        jne  bt_no
        mov  eax, dword ptr [ebp + {F_X:#x}]
        mov  dword ptr [ebp + {F_OX:#x}], eax
        mov  eax, dword ptr [ebp + {F_Y:#x}]
        mov  dword ptr [ebp + {F_OY:#x}], eax
        push dword ptr [ebp + {F_L:#x}]
        mov  eax, dword ptr [ebp + {F_PL:#x}]
        mov  dword ptr [ebp + {F_L:#x}], eax
        mov  ecx, dword ptr [ebp + {F_SURV:#x}]
        call newparty
        pop  dword ptr [ebp + {F_L:#x}]
        test al, al
        je   bt_no
        mov  eax, dword ptr [ebp + {F_HS:#x}]
        mov  dword ptr [ebp + {F_HSB:#x}], eax
        mov  eax, dword ptr [eax + 0x1c]
        call pend_add
        mov  dword ptr [ebp + {F_MSKB:#x}], 0xff
    bt_queue:
        call autoflag
        movzx edx, al
        shl  edx, 16
        mov  eax, dword ptr [ebp + {F_MSKB:#x}]
        and  eax, 0xff
        or   edx, eax
        mov  ecx, dword ptr [ebp + {F_PL:#x}]
        shl  ecx, 24
        mov  eax, dword ptr [ebp + {F_L:#x}]
        and  eax, 0xff
        shl  eax, 16
        or   ecx, eax
        mov  eax, dword ptr [ebp + {F_Y:#x}]
        and  eax, 0xff
        shl  eax, 8
        or   ecx, eax
        mov  eax, dword ptr [ebp + {F_X:#x}]
        and  eax, 0xff
        or   ecx, eax
        mov  eax, dword ptr [ebp + {F_HSB:#x}]
        call mkte
        call queue_te
        mov  al, 1
        ret
    bt_no:
        xor  eax, eax
        ret

    can_attack:
        test edx, edx
        jle  ca_no
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x140]
        call {GETPLAYERS:#x}
        cmp  byte ptr [eax + 0x44], 0
        jne  ca_no
        mov  al, 1
        ret
    ca_no:
        xor  eax, eax
        ret

    autoflag:
        mov  ecx, dword ptr [ebx + {{MAP}}]
        cmp  byte ptr [ecx + 0x13a], 1
        je   af_yes
        mov  edx, dword ptr [ebp + {F_PLAYER:#x}]
        test edx, edx
        jle  af_no
        mov  eax, dword ptr [ecx + 0x140]
        call {GETPLAYERS:#x}
        cmp  byte ptr [eax + 0xa7], 0
        jne  af_no
        mov  ecx, dword ptr [ebx + {{MAP}}]
        movsx eax, byte ptr [ecx + 0xa5]
        cmp  eax, dword ptr [ebp + {F_PLAYER:#x}]
        je   af_no
    af_yes:
        mov  al, 1
        ret
    af_no:
        xor  eax, eax
        ret

    enemy:
        push esi
        push edi
        mov  esi, edx
        call {FIELD_GETPLAYER:#x}
        movsx edi, al
        cmp  edi, -1
        je   en_no
        cmp  edi, esi
        je   en_no
        test esi, esi
        jle  en_yes
        test edi, edi
        jle  en_yes
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x140]
        mov  edx, esi
        call {GETPLAYERS:#x}
        mov  eax, dword ptr [eax + 0x40]
        mov  edx, edi
        call {GETDIPLREL:#x}
        test al, al
        je   en_no
        cmp  al, 2
        je   en_no
    en_yes:
        mov  al, 1
        jmp  en_out
    en_no:
        xor  eax, eax
    en_out:
        pop  edi
        pop  esi
        ret

    mkte:
        push esi
        push edi
        push ebp
        sub  esp, 0x10
        mov  esi, eax
        mov  dword ptr [esp], edx
        mov  dword ptr [esp + 4], ecx
        mov  eax, dword ptr [ebx + {{CMTE}}]
        xor  ecx, ecx
        mov  dl, 1
        call {MOVETE_CREATE:#x}
        mov  edi, eax
        mov  eax, dword ptr [edi + 0x14]
        call {XYL_CLEAR:#x}
        mov  edx, dword ptr [esp + 4]
        and  edx, 0xffffff
        mov  eax, dword ptr [edi + 0x14]
        call {XYL_ADD:#x}
        mov  edx, dword ptr [esp + 4]
        mov  ecx, edx
        shr  ecx, 24
        shl  ecx, 16
        and  edx, 0xffff
        or   edx, ecx
        mov  eax, dword ptr [edi + 0x14]
        call {XYL_ADD:#x}
        mov  dword ptr [edi + 0x28], esi
        mov  eax, dword ptr [esi + 0x1c]
        mov  al, byte ptr [eax + 0x12]
        mov  byte ptr [edi + 0x2c], al
        mov  byte ptr [edi + 0x1c], 0
        movzx eax, byte ptr [esp + 4]
        movzx edx, byte ptr [esp + 5]
        movzx ecx, byte ptr [esp + 6]
        call gf
        mov  dl, 0xff
        test eax, eax
        je   mk_own
        call {FIELD_GETPLAYER:#x}
        mov  dl, al
    mk_own:
        mov  byte ptr [edi + 0x2d], dl
        mov  al, byte ptr [esp + 4]
        mov  byte ptr [edi + 0x2e], al
        mov  al, byte ptr [esp + 5]
        mov  byte ptr [edi + 0x2f], al
        mov  al, byte ptr [esp + 6]
        mov  byte ptr [edi + 0x30], al
        mov  eax, dword ptr [esi + 0x1c]
        mov  dl, byte ptr [esp]
        call {ARMY_VALSEL:#x}
        mov  byte ptr [edi + 0x24], al
        mov  eax, dword ptr [esi + 0x1c]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  dword ptr [esp + 8], eax
        mov  dword ptr [esp + 0xc], 0
    mk_id:
        mov  ecx, dword ptr [esp + 0xc]
        cmp  ecx, dword ptr [esp + 8]
        jge  mk_ids
        movzx eax, byte ptr [esp]
        bt   eax, ecx
        jae  mk_inext
        mov  edx, ecx
        mov  eax, dword ptr [esi + 0x1c]
        call {ARMY_GETUNIT:#x}
        mov  edx, dword ptr [eax + 0x18]
        mov  eax, dword ptr [edi + 0x20]
        call {INTLIST_ADD:#x}
    mk_inext:
        inc  dword ptr [esp + 0xc]
        jmp  mk_id
    mk_ids:
        mov  eax, dword ptr [esi + 0x1c]
        mov  dl, byte ptr [eax + 0x25]
        mov  byte ptr [edi + 0x31], dl
        mov  dl, byte ptr [eax + 0x26]
        mov  byte ptr [edi + 0x32], dl
        mov  dl, byte ptr [eax + 0x27]
        mov  byte ptr [edi + 0x33], dl
        mov  al, byte ptr [esp + 1]
        mov  byte ptr [edi + 0x3a], al
        mov  al, byte ptr [esp + 2]
        mov  byte ptr [edi + 0x39], al
        mov  eax, edi
        add  esp, 0x10
        pop  ebp
        pop  edi
        pop  esi
        ret

    queue_te:
        push eax
        mov  edx, eax
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x23c]
        mov  eax, dword ptr [eax + 4]
        call {ADDSYSEV:#x}
        pop  eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
        ret

    ptab:
        mov  eax, dword ptr [ebx + {{PENDP}}]
        test eax, eax
        jne  pt_out
        mov  eax, 0x40
        call {GETMEM:#x}
        test eax, eax
        je   pt_out
        push edi
        push ecx
        push eax
        mov  edi, eax
        mov  ecx, 0x10
        xor  eax, eax
        rep stosd
        pop  eax
        pop  ecx
        pop  edi
        mov  dword ptr [ebx + {{PENDP}}], eax
    pt_out:
        ret

    stamp:
        mov  eax, dword ptr [ebx + {{MAP}}]
        test eax, eax
        je   st_out
        mov  eax, dword ptr [eax + 0x23c]
        test eax, eax
        je   st_out
        mov  eax, dword ptr [eax + 4]
        test eax, eax
        je   st_out
        mov  eax, dword ptr [eax + 0x18]
    st_out:
        ret

    pend_has:
        push esi
        push edi
        push edx
        push ecx
        mov  esi, eax
        test esi, esi
        je   ph_no
        call ptab
        test eax, eax
        je   ph_no
        mov  edi, eax
        call stamp
        mov  edx, eax
        xor  ecx, ecx
    ph_loop:
        cmp  ecx, 8
        jge  ph_no
        cmp  dword ptr [edi + ecx*8], esi
        jne  ph_next
        mov  eax, edx
        sub  eax, dword ptr [edi + ecx*8 + 4]
        cmp  eax, 8
        jbe  ph_yes
        mov  dword ptr [edi + ecx*8], 0
    ph_next:
        inc  ecx
        jmp  ph_loop
    ph_yes:
        mov  al, 1
        jmp  ph_out
    ph_no:
        xor  eax, eax
    ph_out:
        pop  ecx
        pop  edx
        pop  edi
        pop  esi
        ret

    pend_room:
        push edi
        push edx
        push ecx
        call ptab
        test eax, eax
        je   pr_no
        mov  edi, eax
        call stamp
        mov  edx, eax
        xor  ecx, ecx
    pr_loop:
        cmp  ecx, 8
        jge  pr_no
        cmp  dword ptr [edi + ecx*8], 0
        je   pr_yes
        mov  eax, edx
        sub  eax, dword ptr [edi + ecx*8 + 4]
        cmp  eax, 8
        ja   pr_yes
        inc  ecx
        jmp  pr_loop
    pr_yes:
        mov  al, 1
        jmp  pr_out
    pr_no:
        xor  eax, eax
    pr_out:
        pop  ecx
        pop  edx
        pop  edi
        ret

    pend_add:
        push esi
        push edi
        push edx
        push ecx
        mov  esi, eax
        test esi, esi
        je   pa_no
        call pend_del
        call ptab
        test eax, eax
        je   pa_no
        mov  edi, eax
        call stamp
        mov  edx, eax
        xor  ecx, ecx
    pa_loop:
        cmp  ecx, 8
        jge  pa_no
        cmp  dword ptr [edi + ecx*8], 0
        je   pa_put
        mov  eax, edx
        sub  eax, dword ptr [edi + ecx*8 + 4]
        cmp  eax, 8
        ja   pa_put
        inc  ecx
        jmp  pa_loop
    pa_put:
        mov  dword ptr [edi + ecx*8], esi
        mov  dword ptr [edi + ecx*8 + 4], edx
        mov  al, 1
        jmp  pa_out
    pa_no:
        xor  eax, eax
    pa_out:
        pop  ecx
        pop  edx
        pop  edi
        pop  esi
        ret

    pend_del:
        push esi
        push edi
        push ecx
        mov  esi, eax
        test esi, esi
        je   pd_out
        mov  edi, dword ptr [ebx + {{PENDP}}]
        test edi, edi
        je   pd_out
        xor  ecx, ecx
    pd_loop:
        cmp  dword ptr [edi + ecx*8], esi
        jne  pd_next
        mov  dword ptr [edi + ecx*8], 0
    pd_next:
        inc  ecx
        cmp  ecx, 8
        jl   pd_loop
    pd_out:
        pop  ecx
        pop  edi
        pop  esi
        ret

    ter_void:
        test eax, eax
        je   tv_no
        mov  cl, byte ptr [eax + 0x14]
        cmp  cl, {SKY:#x}
        je   tv_yes
        cmp  cl, {CHASM:#x}
        je   tv_yes
    tv_no:
        xor  eax, eax
        ret
    tv_yes:
        mov  eax, 1
        ret

    isfallte:
        mov  eax, dword ptr [eax + 0x14]
        test eax, eax
        je   it_no
        cmp  dword ptr [eax + 8], 2
        jne  it_no
        mov  eax, dword ptr [eax + 4]
        mov  ecx, dword ptr [eax]
        mov  edx, dword ptr [eax + 4]
        cmp  cx, dx
        jne  it_no
        mov  eax, ecx
        shr  eax, 16
        mov  ecx, edx
        shr  ecx, 16
        cmp  al, cl
        je   it_no
        movzx ecx, cl
        movzx eax, dl
        movzx edx, dh
        call gf
        jmp  ter_void
    it_no:
        xor  eax, eax
        ret

    isfall_cd:
        test eax, eax
        je   ic_no
        mov  ecx, dword ptr [eax + 0x14]
        cmp  ecx, dword ptr [eax + 8]
        jne  ic_no
        mov  ecx, dword ptr [eax + 0x18]
        cmp  ecx, dword ptr [eax + 0xc]
        jne  ic_no
        mov  ecx, dword ptr [eax + 0x1c]
        cmp  ecx, dword ptr [eax + 0x10]
        je   ic_no
        mov  edx, dword ptr [eax + 0x18]
        mov  ecx, dword ptr [eax + 0x1c]
        mov  eax, dword ptr [eax + 0x14]
        call gf
        jmp  ter_void
    ic_no:
        xor  eax, eax
        ret

    te_army:
        mov  eax, dword ptr [eax + 0x14]
        test eax, eax
        je   ha_no
        cmp  dword ptr [eax + 8], 2
        jl   ha_no
        mov  eax, dword ptr [eax + 4]
        mov  edx, dword ptr [eax + 4]
    item_army:
        mov  ecx, edx
        shr  ecx, 16
        movzx ecx, cl
        movzx eax, dl
        movzx edx, dh
    hex_army:
        call gf
        test eax, eax
        je   ha_no
        call {ARMY_ON:#x}
        test eax, eax
        je   ha_no
        mov  eax, dword ptr [eax + 0x1c]
        ret
    ha_no:
        xor  eax, eax
        ret

    cd_army:
        mov  edx, dword ptr [eax + 0x18]
        mov  ecx, dword ptr [eax + 0x1c]
        mov  eax, dword ptr [eax + 0x14]
        jmp  hex_army

    redrop:
        test eax, eax
        je   rd_out
        push eax
        call pend_del
        pop  eax
        mov  byte ptr [ebx + {{NOBAT}}], 1
        call vcheck
        mov  byte ptr [ebx + {{NOBAT}}], 0
    rd_out:
        ret

    hazard:
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, {F_SIZE:#x}
        mov  ebp, esp
        mov  dword ptr [ebp + {F_ARMY:#x}], eax
        mov  dword ptr [ebp + {F_MASK:#x}], edx
        mov  byte ptr [ebp + {F_LOGP:#x}], cl
        mov  byte ptr [ebp + {F_TER:#x}], ch
        shr  ecx, 16
        mov  byte ptr [ebp + {F_OVL:#x}], cl
        call get_anc
        mov  esi, eax
        movzx eax, byte ptr [esi + 0x13]
        mov  dword ptr [ebp + {F_X:#x}], eax
        movzx eax, byte ptr [esi + 0x14]
        mov  dword ptr [ebp + {F_Y:#x}], eax
        movsx eax, byte ptr [esi + 0x15]
        mov  dword ptr [ebp + {F_L:#x}], eax
        movsx eax, byte ptr [esi + 0x12]
        mov  dword ptr [ebp + {F_PLAYER:#x}], eax
        mov  dword ptr [ebp + {F_STR:#x}], 0
        mov  dword ptr [ebp + {F_STR + 4:#x}], 0
        mov  al, byte ptr [ebp + {F_TER:#x}]
        call hzclass
        mov  dword ptr [ebp + {F_KIND:#x}], eax
        mov  dword ptr [ebp + {F_TYPES:#x}], ecx
        mov  dword ptr [ebp + {F_HDICE:#x}], edx
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        test eax, eax
        jle  hz_none
        cmp  eax, 8
        jle  hz_cnt
        mov  eax, 8
    hz_cnt:
        mov  dword ptr [ebp + {F_CNT:#x}], eax
        mov  dword ptr [ebp + {F_I:#x}], 0
    hz_rec:
        mov  ecx, dword ptr [ebp + {F_I:#x}]
        cmp  ecx, dword ptr [ebp + {F_CNT:#x}]
        jge  hz_log
        mov  edx, ecx
        mov  eax, esi
        call {ARMY_GETUNIT:#x}
        mov  ecx, dword ptr [ebp + {F_I:#x}]
        mov  dword ptr [ebp + ecx*4 + {F_UP:#x}], eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        mov  ecx, dword ptr [ebp + {F_I:#x}]
        mov  byte ptr [ebp + ecx + {F_HP0:#x}], al
        inc  dword ptr [ebp + {F_I:#x}]
        jmp  hz_rec
    hz_log:
        call mklog
        mov  dword ptr [ebp + {F_I:#x}], 0
    hz_dmg:
        mov  ecx, dword ptr [ebp + {F_I:#x}]
        cmp  ecx, dword ptr [ebp + {F_CNT:#x}]
        jge  hz_shunt
        mov  eax, dword ptr [ebp + {F_MASK:#x}]
        bt   eax, ecx
        jae  hz_dnext
        mov  eax, dword ptr [ebp + ecx*4 + {F_UP:#x}]
        mov  dword ptr [ebp + {F_UNIT:#x}], eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        test al, al
        je   hz_dnext
        mov  eax, dword ptr [ebp + {F_HDICE:#x}]
        call roll
        mov  edx, eax
        mov  ecx, dword ptr [ebp + {F_TYPES:#x}]
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        call hit
    hz_dnext:
        inc  dword ptr [ebp + {F_I:#x}]
        jmp  hz_dmg
    hz_shunt:
        call scan
        test eax, eax
        je   hz_fill
        bsf  ecx, eax
        mov  dword ptr [ebp + {F_I:#x}], ecx
        mov  edx, ecx
        mov  eax, dword ptr [ebp + {F_ARMY:#x}]
        call {ARMY_GETUNIT:#x}
        mov  dword ptr [ebp + {F_UNIT:#x}], eax
        call move_one
        test al, al
        jne  hz_shunt
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        xor  edx, edx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xe4]
        jmp  hz_shunt
    hz_fill:
        mov  dword ptr [ebp + {F_I:#x}], 0
    hz_fl:
        mov  ecx, dword ptr [ebp + {F_I:#x}]
        cmp  ecx, dword ptr [ebp + {F_CNT:#x}]
        jge  hz_send
        mov  eax, dword ptr [ebp + ecx*4 + {F_UP:#x}]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        movzx eax, al
        mov  ecx, dword ptr [ebp + {F_I:#x}]
        movzx edx, byte ptr [ebp + ecx + {F_HP0:#x}]
        sub  edx, eax
        jge  hz_byte
        xor  edx, edx
    hz_byte:
        mov  eax, dword ptr [ebp + {F_LOG:#x}]
        mov  eax, dword ptr [eax + 0x28]
        call {BYTELIST_ADD:#x}
        mov  eax, dword ptr [ebp + {F_LOG:#x}]
        mov  eax, dword ptr [eax + 0x2c]
        mov  dl, 9
        call {BYTELIST_ADD:#x}
        inc  dword ptr [ebp + {F_I:#x}]
        jmp  hz_fl
    hz_send:
        mov  eax, dword ptr [ebp + {F_LOG:#x}]
        call {ALOG_GAMEOVER:#x}
        mov  al, byte ptr [ebp + {F_Y:#x}]
        push eax
        mov  al, byte ptr [ebp + {F_L:#x}]
        push eax
        push 1
        mov  cl, byte ptr [ebp + {F_X:#x}]
        mov  dl, byte ptr [ebp + {F_PLAYER:#x}]
        mov  eax, dword ptr [ebp + {F_LOG:#x}]
        call {DISTLOC:#x}
        mov  eax, dword ptr [ebp + {F_LOG:#x}]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
        lea  eax, [ebp + {F_STR:#x}]
        mov  edx, 2
        call {LSTRARRCLR:#x}
        mov  eax, 1
        jmp  hz_ret
    hz_none:
        xor  eax, eax
    hz_ret:
        add  esp, {F_SIZE:#x}
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret

    mklog:
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, dword ptr [ebx + {{ALOG}}]
        call {ALOG_CREATE:#x}
        mov  dword ptr [ebp + {F_LOG:#x}], eax
        mov  dl, byte ptr [ebp + {F_LOGP:#x}]
        mov  byte ptr [eax + 0x10], dl
        mov  ecx, dword ptr [ebp + {F_KIND:#x}]
        lea  eax, [ebx + {{RSD}}]
        test ecx, ecx
        je   ml_rs
        lea  eax, [ebx + {{RSB}}]
        cmp  ecx, 1
        je   ml_rs
        lea  eax, [ebx + {{RSC}}]
    ml_rs:
        mov  dword ptr [ebp + {F_RS:#x}], eax
        lea  edx, [ebp + {F_STR:#x}]
        call {LOADRES:#x}
        mov  eax, dword ptr [ebp + {F_STR:#x}]
        lea  edx, [ebp + {F_STR + 4:#x}]
        call {TRANSLATE:#x}
        mov  edx, dword ptr [ebp + {F_STR + 4:#x}]
        mov  eax, dword ptr [ebp + {F_LOG:#x}]
        add  eax, 0x1c
        call {LSTRASG:#x}
        mov  eax, dword ptr [ebp + {F_RS:#x}]
        lea  edx, [ebp + {F_STR:#x}]
        call {LOADRES:#x}
        mov  eax, dword ptr [ebp + {F_STR:#x}]
        lea  edx, [ebp + {F_STR + 4:#x}]
        call {TRANSLATE:#x}
        mov  edx, dword ptr [ebp + {F_STR + 4:#x}]
        mov  eax, dword ptr [ebp + {F_LOG:#x}]
        mov  eax, dword ptr [eax + 0x20]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x34]
        mov  ecx, dword ptr [ebp + {F_KIND:#x}]
        mov  eax, 3
        test ecx, ecx
        je   ml_icon
        xor  eax, eax
        cmp  ecx, 1
        je   ml_icon
        mov  eax, 2
    ml_icon:
        mov  edx, dword ptr [ebp + {F_LOG:#x}]
        mov  dword ptr [edx + 0x24], eax
        mov  eax, dword ptr [ebp + {F_LOG:#x}]
        mov  eax, dword ptr [eax + 0x18]
        mov  cl, 0xff
        mov  edx, esi
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0xc0]
        ret

    hzclass:
        cmp  al, 0
        je   hc_water
        cmp  al, 0xa
        je   hc_water
        cmp  al, 9
        je   hc_lava
        mov  eax, 2
        mov  ecx, {HAZ['other'][1]:#x}
        mov  edx, {HAZ['other'][0]}
        ret
    hc_water:
        xor  eax, eax
        mov  ecx, {HAZ['water'][1]:#x}
        mov  edx, {HAZ['water'][0]}
        ret
    hc_lava:
        mov  eax, 1
        mov  ecx, {HAZ['lava'][1]:#x}
        mov  edx, {HAZ['lava'][0]}
        ret

    roll:
        push esi
        push edi
        mov  esi, eax
        xor  edi, edi
    rl_loop:
        test esi, esi
        jle  rl_out
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edx, {DIE}
        call {RANDOM:#x}
        lea  edi, [edi + eax + 1]
        dec  esi
        jmp  rl_loop
    rl_out:
        mov  eax, edi
        pop  edi
        pop  esi
        ret

    hit:
        push esi
        push edi
        mov  esi, eax
        mov  dword ptr [ebx + {{FORCE}}], edx
        push ecx
        mov  ecx, edx
        xor  edx, edx
        call {EXECDMGROLE:#x}
        mov  dword ptr [ebx + {{FORCE}}], 0
        test eax, eax
        jge  ht_dmg
        xor  eax, eax
    ht_dmg:
        mov  edi, eax
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        movzx eax, al
        sub  eax, edi
        jg   ht_set
        xor  eax, eax
    ht_set:
        mov  edi, eax
        mov  edx, eax
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xe4]
        test edi, edi
        setne al
        pop  edi
        pop  esi
        ret

    get_anc:
        {{ANC}}
        ret

{mark(1)}
    cargo:
        test byte ptr [eax + 0x47], 9
        jne  c_orig
        ret
    c_orig:
        mov  edx, dword ptr [eax]
        jmp  dword ptr [edx + 0x120]

{mark(2)}
    fin:
        test eax, eax
        jne  fn_ok
        cmp  byte ptr [esp + 4], 1
        jne  fn_fail
        mov  eax, esi
        mov  edx, ebx
        call fbplace
        test al, al
        jne  fn_ok
        mov  eax, esi
        mov  edx, ebx
        call fp
        test al, al
        jne  fn_ok
    fn_fail:
        jmp  {FIN_FAIL:#x}
    fn_ok:
        jmp  {FIN_OK:#x}

    fbplace:
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        call get_anc
        mov  eax, dword ptr [esi + 8]
        test eax, eax
        je   fb_no
        mov  eax, dword ptr [eax + 0xc]
        call isfall_cd
        test al, al
        je   fb_no
        mov  eax, esi
        call {GETSIDE:#x}
        test al, al
        jne  fb_no
        mov  eax, esi
        call {CO_GETPLAYER:#x}
        movzx eax, al
        push eax
        push dword ptr [edi + 0x14]
        mov  eax, dword ptr [esi + 0x4c]
        mov  edx, dword ptr [edi + 0xc]
        mov  ecx, dword ptr [edi + 0x10]
        call fplace
        test eax, eax
        setne al
        jmp  fb_out
    fb_no:
        xor  eax, eax
    fb_out:
        pop  edi
        pop  esi
        pop  ebx
        ret

    fplace:
        push ebx
        push esi
        push edi
        push ebp
        mov  esi, eax
        mov  edi, edx
        mov  ebp, ecx
        test esi, esi
        je   fl_no
        call get_anc
        mov  eax, edi
        mov  edx, ebp
        mov  ecx, dword ptr [esp + 0x14]
        call gf
        test eax, eax
        je   fl_no
        call {ARMY_ON:#x}
        test eax, eax
        je   fl_new
        push eax
        mov  edx, esi
        mov  eax, dword ptr [eax + 0x1c]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xac]
        test al, al
        pop  eax
        jne  fl_out
        jmp  fl_no
    fl_new:
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, dword ptr [ebx + {{ARMYHS}}]
        call {ARMYHS_CREATE:#x}
        push eax
        cmp  byte ptr [esp + 0x1c], 0xff
        je   fl_add
        mov  dl, byte ptr [esp + 0x1c]
        mov  eax, dword ptr [eax + 0x1c]
        call {SETPLAYER:#x}
    fl_add:
        mov  eax, dword ptr [esp]
        mov  edx, esi
        mov  eax, dword ptr [eax + 0x1c]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xac]
        test al, al
        je   fl_free
        push ebp
        push dword ptr [esp + 0x1c]
        mov  ecx, edi
        mov  edx, dword ptr [esp + 8]
        mov  eax, dword ptr [ebx + {{MAP}}]
        call {PLACEHX:#x}
        test al, al
        je   fl_free
        pop  eax
        jmp  fl_out
    fl_free:
        pop  eax
        call {OBJ_FREE:#x}
    fl_no:
        xor  eax, eax
    fl_out:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret  8

    fp:
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, {F_SIZE:#x}
        mov  ebp, esp
        call get_anc
        mov  esi, eax
        mov  eax, dword ptr [esi + 0x4c]
        test eax, eax
        je   p_no
        mov  dword ptr [ebp + {F_UNIT:#x}], eax
        mov  eax, dword ptr [edx + 0xc]
        mov  dword ptr [ebp + {F_X:#x}], eax
        mov  eax, dword ptr [edx + 0x10]
        mov  dword ptr [ebp + {F_Y:#x}], eax
        mov  eax, dword ptr [edx + 0x14]
        mov  dword ptr [ebp + {F_L:#x}], eax
        mov  dword ptr [ebp + {F_L0:#x}], eax
        mov  eax, esi
        call {CO_GETPLAYER:#x}
        movsx edx, al
        mov  dword ptr [ebp + {F_PLAYER:#x}], edx
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x140]
        call {GETPLAYERS:#x}
        cmp  byte ptr [eax + 0x44], 2
        jne  p_pl
        mov  dword ptr [ebp + {F_PLAYER:#x}], 0
    p_pl:
        mov  eax, dword ptr [ebp + {F_X:#x}]
        mov  edx, dword ptr [ebp + {F_Y:#x}]
        mov  ecx, dword ptr [ebp + {F_L:#x}]
        call gf
        test eax, eax
        je   p_no
        mov  dword ptr [ebp + {F_FIELD:#x}], eax
        mov  dl, byte ptr [eax + 0x14]
        mov  cl, byte ptr [eax + 0x15]
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        call {UNIT_VALIDTERRAIN:#x}
        test al, al
        jne  p_no
        mov  eax, dword ptr [ebp + {F_FIELD:#x}]
        mov  cl, byte ptr [eax + 0x14]
        cmp  cl, {SKY:#x}
        je   p_go
        cmp  cl, {CHASM:#x}
        je   p_go
        mov  al, cl
        call hzclass
        push ecx
        mov  eax, edx
        call roll
        mov  edx, eax
        pop  ecx
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        call hit
        test al, al
        je   p_no
        jmp  p_nbr
    p_go:
        mov  dword ptr [ebp + {F_N:#x}], 0
    p_down:
        mov  eax, dword ptr [ebp + {F_L:#x}]
        call below
        test eax, eax
        js   p_no
        mov  dword ptr [ebp + {F_L:#x}], eax
        inc  dword ptr [ebp + {F_N:#x}]
        mov  ecx, eax
        mov  eax, dword ptr [ebp + {F_X:#x}]
        mov  edx, dword ptr [ebp + {F_Y:#x}]
        call gf
        test eax, eax
        je   p_no
        mov  dword ptr [ebp + {F_FIELD:#x}], eax
        mov  cl, byte ptr [eax + 0x14]
        cmp  cl, {SKY:#x}
        je   p_down
        cmp  cl, {CHASM:#x}
        je   p_down
        cmp  byte ptr [ebx + {{NOBAT}}], 0
        jne  p_dmg
        mov  eax, esi
        call {GETSIDE:#x}
        test al, al
        jne  p_dmg
        mov  eax, dword ptr [ebp + {F_FIELD:#x}]
        mov  edx, dword ptr [ebp + {F_PLAYER:#x}]
        call enemy
        test al, al
        je   p_dmg
        push dword ptr [ebp + {F_PLAYER:#x}]
        push dword ptr [ebp + {F_L0:#x}]
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        mov  edx, dword ptr [ebp + {F_X:#x}]
        mov  ecx, dword ptr [ebp + {F_Y:#x}]
        call fplace
        test eax, eax
        jne  p_yes
    p_dmg:
        call fdamage
        test al, al
        je   p_no
        mov  eax, dword ptr [ebp + {F_X:#x}]
        mov  edx, dword ptr [ebp + {F_Y:#x}]
        call pplace
        test eax, eax
        jne  p_yes
    p_nbr:
        mov  dword ptr [ebp + {F_SHUF:#x}], 0x04030201
        mov  dword ptr [ebp + {F_SHUF + 4:#x}], 0x00000605
        mov  dword ptr [ebp + {F_TRY:#x}], 5
    p_shuf:
        mov  edx, dword ptr [ebp + {F_TRY:#x}]
        inc  edx
        mov  eax, dword ptr [ebx + {{MAP}}]
        call {RANDOM:#x}
        mov  ecx, dword ptr [ebp + {F_TRY:#x}]
        mov  dl, byte ptr [ebp + ecx + {F_SHUF:#x}]
        mov  dh, byte ptr [ebp + eax + {F_SHUF:#x}]
        mov  byte ptr [ebp + ecx + {F_SHUF:#x}], dh
        mov  byte ptr [ebp + eax + {F_SHUF:#x}], dl
        dec  dword ptr [ebp + {F_TRY:#x}]
        jne  p_shuf
    p_try:
        cmp  dword ptr [ebp + {F_TRY:#x}], 6
        jge  p_lost
        mov  ecx, dword ptr [ebp + {F_TRY:#x}]
        movzx ecx, byte ptr [ebp + ecx + {F_SHUF:#x}]
        mov  eax, dword ptr [ebp + {F_X:#x}]
        mov  edx, dword ptr [ebp + {F_Y:#x}]
        call nb
        call pplace
        test eax, eax
        jne  p_yes
        inc  dword ptr [ebp + {F_TRY:#x}]
        jmp  p_try
    p_lost:
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        xor  edx, edx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xe4]
    p_no:
        xor  eax, eax
        jmp  p_ret
    p_yes:
        mov  eax, 1
    p_ret:
        add  esp, {F_SIZE:#x}
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret

    pplace:
        push dword ptr [ebp + {F_L:#x}]
        push dword ptr [ebp + {F_PLAYER:#x}]
        push 0
        mov  ecx, edx
        mov  edx, eax
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        call {PLACE:#x}
        ret

    fdamage:
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x178]
        movzx eax, al
        inc  eax
        imul eax, dword ptr [ebp + {F_N:#x}]
        shl  eax, 1
        call roll
        mov  edx, eax
        mov  ecx, {PHYS:#x}
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        call hit
        test al, al
        je   fd_out
        mov  eax, dword ptr [ebp + {F_FIELD:#x}]
        mov  dl, byte ptr [eax + 0x14]
        mov  cl, byte ptr [eax + 0x15]
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        call {UNIT_VALIDTERRAIN:#x}
        test al, al
        jne  fd_out
        mov  eax, dword ptr [ebp + {F_FIELD:#x}]
        mov  dl, byte ptr [eax + 0x14]
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        call hzhit
    fd_out:
        ret

    hzhit:
        push esi
        mov  esi, eax
        mov  al, dl
        call hzclass
        push ecx
        mov  eax, edx
        call roll
        mov  edx, eax
        pop  ecx
        mov  eax, esi
        call hit
        pop  esi
        ret

    stuck:
        push esi
        push edi
        call scan
        mov  esi, eax
        xor  edi, edi
    sk_loop:
        test esi, esi
        je   sk_out
        bsf  ecx, esi
        btr  esi, ecx
        push ecx
        mov  edx, ecx
        mov  eax, dword ptr [ebp + {F_ARMY:#x}]
        call {ARMY_GETUNIT:#x}
        mov  ecx, dword ptr [ebp + {F_FIELD:#x}]
        mov  dl, byte ptr [ecx + 0x14]
        mov  cl, byte ptr [ecx + 0x15]
        call {UNIT_VALIDTERRAIN:#x}
        pop  ecx
        test al, al
        jne  sk_loop
        bts  edi, ecx
        jmp  sk_loop
    sk_out:
        mov  eax, edi
        pop  edi
        pop  esi
        ret

{mark(3)}
    vend:
        call {UNLOCK_GO:#x}
        pushad
        mov  eax, edi
        call vcheck
        popad
        ret

    vcheck:
        push ebx
        push esi
        push edi
        push ebp
        mov  esi, eax
        call get_anc
        test esi, esi
        je   v_no
        cmp  byte ptr [ebx + {{GUARD}}], 0
        jne  v_no
        mov  ecx, dword ptr [ebx + {{MAP}}]
        test ecx, ecx
        je   v_no
        test byte ptr [ecx + 0x3c], 2
        jne  v_no
        cmp  dword ptr [ecx + 0x174], 0
        je   v_no
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        test eax, eax
        je   v_no
        movzx eax, byte ptr [esi + 0x13]
        movzx edx, byte ptr [esi + 0x14]
        movsx ecx, byte ptr [esi + 0x15]
        call gf
        test eax, eax
        je   v_no
        mov  ebp, eax
        mov  cl, byte ptr [eax + 0x14]
        cmp  cl, {SKY:#x}
        je   v_void
        cmp  cl, {CHASM:#x}
        je   v_void
        test byte ptr [esi + 0x11], 4
        jne  v_no
    v_void:
        call {ARMY_ON:#x}
        test eax, eax
        je   v_no
        cmp  dword ptr [eax + 0x1c], esi
        jne  v_no
        mov  eax, esi
        mov  dl, 0xff
        call {ARMY_TRANSPORTER:#x}
        test eax, eax
        je   v_units
        mov  dl, byte ptr [ebp + 0x14]
        mov  cl, byte ptr [ebp + 0x15]
        call {UNIT_VALIDTERRAIN:#x}
        test al, al
        jne  v_no
    v_units:
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  edi, eax
    v_loop:
        dec  edi
        js   v_no
        mov  edx, edi
        mov  eax, esi
        call {ARMY_GETUNIT:#x}
        push eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        test al, al
        pop  eax
        je   v_loop
        mov  dl, byte ptr [ebp + 0x14]
        mov  cl, byte ptr [ebp + 0x15]
        call {UNIT_VALIDTERRAIN:#x}
        test al, al
        jne  v_loop
        mov  byte ptr [ebx + {{GUARD}}], 1
        mov  dl, byte ptr [ebp + 0x14]
        mov  cl, byte ptr [ebp + 0x15]
        mov  eax, esi
        call {ARMY_VALIDATETERRAIN:#x}
        mov  byte ptr [ebx + {{GUARD}}], 0
    v_no:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret

{mark(4)}
    pm:
        push ebx
        push esi
        mov  esi, ebx
        call get_anc
        mov  eax, esi
        call isfallte
        test al, al
        je   pm_plain
        mov  eax, esi
        call te_army
        call pend_del
        cmp  byte ptr [esi + 0x39], 0
        jne  pm_go
        mov  byte ptr [esi + 0x39], 1
    pm_go:
        mov  eax, dword ptr [ebx + {{MAP}}]
        cmp  dword ptr [eax + 0x120], 0
        jne  pm_back
        mov  byte ptr [ebx + {{NOFLEE}}], 1
        mov  eax, esi
        call {EXEC_COMBAT:#x}
        mov  byte ptr [ebx + {{NOFLEE}}], 0
        mov  eax, dword ptr [ebx + {{MAP}}]
        cmp  dword ptr [eax + 0x120], 0
        jne  pm_back
        cmp  dword ptr [esi + 0x28], 0
        jne  pm_back
        mov  eax, esi
        call te_army
        call redrop
        jmp  pm_back
    pm_plain:
        cmp  byte ptr [esi + 0x39], 0
        je   pm_cancel
        mov  eax, esi
        call {EXEC_COMBAT:#x}
        mov  eax, dword ptr [ebx + {{MAP}}]
        cmp  dword ptr [eax + 0x120], 0
        jne  pm_back
        cmp  dword ptr [esi + 0x28], 0
        jne  pm_back
        mov  eax, dword ptr [esi + 0x14]
        test eax, eax
        je   pm_back
        mov  ecx, dword ptr [esi + 0x18]
        test ecx, ecx
        jl   pm_back
        cmp  ecx, dword ptr [eax + 8]
        jge  pm_back
        mov  eax, dword ptr [eax + 4]
        mov  edx, dword ptr [eax + ecx*4]
        call item_army
        call vcheck
    pm_back:
        pop  esi
        pop  ebx
        jmp  {PM_BACK:#x}
    pm_cancel:
        pop  esi
        pop  ebx
        jmp  {PM_CANCEL:#x}

{mark(5)}
    val:
        push ebx
        push esi
        mov  esi, eax
        call {MOVEARMY_VALIDATE:#x}
        push eax
        call get_anc
        mov  eax, esi
        call isfallte
        test al, al
        je   vl_out
        mov  eax, esi
        call te_army
        test eax, eax
        je   vl_out
        push eax
        call pend_del
        cmp  byte ptr [esp + 4], 0
        je   vl_fail
        movsx edx, byte ptr [esi + 0x2c]
        call can_attack
        test al, al
        jne  vl_pop
        mov  byte ptr [esp + 4], 0
    vl_fail:
        pop  eax
        call redrop
        mov  dword ptr [esi + 0x28], 0
        jmp  vl_out
    vl_pop:
        pop  eax
    vl_out:
        pop  eax
        pop  esi
        pop  ebx
        ret

{mark(6)}
    ida:
        mov  byte ptr [esi + 0x40], 2
        push ebx
        call get_anc
        mov  eax, dword ptr [esi + 0xc]
        call isfall_cd
        pop  ebx
        test al, al
        je   ida_out
        mov  byte ptr [esi + 0x40], 0
    ida_out:
        push edi
        jmp  {IDA_BACK:#x}

{mark(7)}
    xyl:
        push ebx
        push esi
        push edi
        push ebp
        mov  esi, eax
        movzx edi, dl
        movzx ebp, cl
        call get_anc
        test esi, esi
        je   xy_van
        mov  eax, dword ptr [esi + 0x1c]
        movzx ecx, byte ptr [eax + 0x13]
        cmp  ecx, ebp
        jne  xy_van
        movzx ecx, byte ptr [eax + 0x14]
        movzx edx, byte ptr [esp + 0x20]
        cmp  ecx, edx
        jne  xy_van
        movzx ecx, byte ptr [eax + 0x15]
        movzx edx, byte ptr [esp + 0x1c]
        cmp  ecx, edx
        je   xy_van
        push ecx
        mov  eax, ebp
        movzx edx, byte ptr [esp + 0x24]
        call gf
        call ter_void
        pop  ecx
        test al, al
        je   xy_van
        shl  ecx, 24
        movzx eax, byte ptr [esp + 0x1c]
        shl  eax, 16
        or   ecx, eax
        movzx eax, byte ptr [esp + 0x20]
        shl  eax, 8
        or   ecx, eax
        or   ecx, ebp
        mov  edx, edi
        or   edx, 0x100
        mov  eax, esi
        call mkte
        push eax
        mov  eax, dword ptr [esi + 0x1c]
        call pend_add
        pop  eax
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret  0x10
    xy_van:
        mov  eax, esi
        mov  edx, edi
        mov  ecx, ebp
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        jmp  {CREATE_XYL:#x}

{mark(8)}
    cex:
        pushad
        mov  esi, ebx
        call get_anc
        mov  edx, dword ptr [ebx + {{FASTC}}]
        mov  eax, esi
        call {ISCLASS:#x}
        test al, al
        jne  cx_out
        mov  edi, dword ptr [esi + 0xc]
        test edi, edi
        je   cx_out
        mov  eax, edi
        call isfall_cd
        test al, al
        je   cx_plain
        mov  eax, edi
        call cd_army
        test eax, eax
        je   cx_out
        push eax
        call pend_has
        test al, al
        pop  eax
        jne  cx_out
        call redrop
        jmp  cx_out
    cx_plain:
        mov  eax, edi
        call cd_army
        call vcheck
    cx_out:
        popad
        pop  ecx
        pop  edx
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret

{mark(9)}
    force:
        push ebx
        call get_anc
        mov  ebx, dword ptr [ebx + {{FORCE}}]
        test ebx, ebx
        je   fo_roll
        mov  eax, ebx
        pop  ebx
        ret
    fo_roll:
        pop  ebx
        jmp  {CORE_ROLL:#x}

    scan:
        push esi
        push edi
        xor  esi, esi
        mov  eax, dword ptr [ebp + {F_ARMY:#x}]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  edi, eax
    sc_loop:
        dec  edi
        js   sc_out
        mov  edx, edi
        mov  eax, dword ptr [ebp + {F_ARMY:#x}]
        call {ARMY_GETUNIT:#x}
        push eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        test al, al
        pop  eax
        je   sc_loop
        mov  dl, byte ptr [ebp + {F_TER:#x}]
        mov  cl, byte ptr [ebp + {F_OVL:#x}]
        call {UNIT_VALIDTERRAIN:#x}
        test al, al
        jne  sc_loop
        bts  esi, edi
        jmp  sc_loop
    sc_out:
        mov  eax, esi
        pop  edi
        pop  esi
        ret

    below:
        push ecx
        push esi
        mov  ecx, dword ptr [ebx + {{MAP}}]
    b_loop:
        cmp  eax, 4
        ja   b_no
        lea  esi, [ebx + {{DNT}}]
        movzx eax, byte ptr [esi + eax]
        cmp  eax, {NO:#x}
        je   b_no
        mov  esi, dword ptr [ecx + 0x10]
        cmp  eax, dword ptr [esi + 0x14]
        jge  b_no
        movzx esi, byte ptr [ecx + {MASK_OFF:#x}]
        bt   esi, eax
        jb   b_loop
        jmp  b_ret
    b_no:
        or   eax, -1
    b_ret:
        pop  esi
        pop  ecx
        ret

    gf:
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        mov  edx, ecx
        mov  eax, dword ptr [ebx + {{MAP}}]
        test eax, eax
        je   g_no
        mov  eax, dword ptr [eax + 0x10]
        test edx, edx
        js   g_no
        cmp  edx, dword ptr [eax + 0x14]
        jge  g_no
        call {GETMAPLEVEL:#x}
        test eax, eax
        je   g_no
        test esi, esi
        js   g_no
        cmp  esi, dword ptr [eax + 0xc]
        jge  g_no
        test edi, edi
        js   g_no
        cmp  edi, dword ptr [eax + 0x10]
        jge  g_no
        mov  edx, esi
        mov  ecx, edi
        call {LEVEL_GETFIELD:#x}
        pop  edi
        pop  esi
        ret
    g_no:
        xor  eax, eax
        pop  edi
        pop  esi
        ret

    nb:
        push edi
        sub  esp, 8
        mov  edi, esp
        push edi
        lea  edi, [edi + 4]
        push edi
        call {CENTERHN:#x}
        mov  eax, dword ptr [esp]
        mov  edx, dword ptr [esp + 4]
        add  esp, 8
        pop  edi
        ret

    newparty:
        push ecx
        mov  eax, dword ptr [ebp + {F_NF:#x}]
        call {FIELD_GETPLAYER:#x}
        cmp  al, 0xff
        jne  np_no
        mov  eax, dword ptr [ebp + {F_NF:#x}]
        mov  edx, dword ptr [ebx + {{STRUCT}}]
        call {HAS_HS:#x}
        test eax, eax
        jne  np_no
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, dword ptr [ebx + {{ARMYHS}}]
        call {ARMYHS_CREATE:#x}
        mov  dword ptr [ebp + {F_HS:#x}], eax
        mov  eax, dword ptr [eax + 0x1c]
        call {BEGINUPD:#x}
        mov  edx, dword ptr [ebp + {F_PLAYER:#x}]
        mov  eax, dword ptr [ebp + {F_HS:#x}]
        mov  eax, dword ptr [eax + 0x1c]
        call {SETPLAYER:#x}
        mov  ecx, dword ptr [esp]
        mov  edx, dword ptr [ebp + {F_ARMY:#x}]
        mov  eax, dword ptr [ebp + {F_HS:#x}]
        mov  eax, dword ptr [eax + 0x1c]
        call {ADDUNITSEL:#x}
        test al, al
        jne  np_free
        push dword ptr [ebp + {F_L:#x}]
        push {PLACE_FLAGS}
        mov  dl, byte ptr [ebp + {F_OX:#x}]
        mov  cl, byte ptr [ebp + {F_OY:#x}]
        mov  eax, dword ptr [ebp + {F_HS:#x}]
        call {PLACEEX:#x}
        test al, al
        je   np_back
        mov  eax, dword ptr [ebp + {F_HS:#x}]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        mov  eax, dword ptr [ebp + {F_HS:#x}]
        mov  eax, dword ptr [eax + 0x1c]
        call {ENDUPD:#x}
        pop  ecx
        mov  al, 1
        ret
    np_back:
        mov  edx, dword ptr [ebp + {F_HS:#x}]
        mov  edx, dword ptr [edx + 0x1c]
        mov  eax, dword ptr [ebp + {F_ARMY:#x}]
        mov  cl, 0xff
        call {ADDUNITSEL:#x}
    np_free:
        mov  eax, dword ptr [ebp + {F_HS:#x}]
        call {OBJ_FREE:#x}
    np_no:
        pop  ecx
        xor  eax, eax
        ret

    move_one:
        mov  dword ptr [ebp + {F_SHUF:#x}], 0x04030201
        mov  dword ptr [ebp + {F_SHUF + 4:#x}], 0x00000605
        mov  dword ptr [ebp + {F_TRY:#x}], 5
    mo_shuf:
        mov  edx, dword ptr [ebp + {F_TRY:#x}]
        inc  edx
        mov  eax, dword ptr [ebx + {{MAP}}]
        call {RANDOM:#x}
        mov  ecx, dword ptr [ebp + {F_TRY:#x}]
        mov  dl, byte ptr [ebp + ecx + {F_SHUF:#x}]
        mov  dh, byte ptr [ebp + eax + {F_SHUF:#x}]
        mov  byte ptr [ebp + ecx + {F_SHUF:#x}], dh
        mov  byte ptr [ebp + eax + {F_SHUF:#x}], dl
        dec  dword ptr [ebp + {F_TRY:#x}]
        jne  mo_shuf
    mo_try:
        cmp  dword ptr [ebp + {F_TRY:#x}], 6
        jge  mo_fail
        mov  ecx, dword ptr [ebp + {F_TRY:#x}]
        movzx ecx, byte ptr [ebp + ecx + {F_SHUF:#x}]
        mov  eax, dword ptr [ebp + {F_X:#x}]
        mov  edx, dword ptr [ebp + {F_Y:#x}]
        call nb
        mov  dword ptr [ebp + {F_OX:#x}], eax
        mov  dword ptr [ebp + {F_OY:#x}], edx
        mov  ecx, dword ptr [ebp + {F_L:#x}]
        call gf
        test eax, eax
        je   mo_next
        mov  dword ptr [ebp + {F_NF:#x}], eax
        call {ARMY_ON:#x}
        test eax, eax
        je   mo_new
        mov  eax, dword ptr [eax + 0x1c]
        test eax, eax
        je   mo_next
        mov  dword ptr [ebp + {F_DEST:#x}], eax
        movsx ecx, byte ptr [eax + 0x12]
        cmp  ecx, dword ptr [ebp + {F_PLAYER:#x}]
        jne  mo_next
        test byte ptr [eax + 0x11], 4
        jne  mo_next
        mov  dl, 0xff
        call {ARMY_TRANSPORTER:#x}
        test eax, eax
        jne  mo_join
        call mo_stand
        test al, al
        je   mo_next
    mo_join:
        mov  ecx, dword ptr [ebp + {F_I:#x}]
        mov  edx, 1
        shl  edx, cl
        mov  ecx, edx
        mov  edx, dword ptr [ebp + {F_ARMY:#x}]
        mov  eax, dword ptr [ebp + {F_DEST:#x}]
        call {ADDUNITSEL:#x}
        test al, al
        jne  mo_next
        mov  al, 1
        ret
    mo_new:
        call mo_stand
        test al, al
        je   mo_next
        mov  ecx, dword ptr [ebp + {F_I:#x}]
        mov  edx, 1
        shl  edx, cl
        mov  ecx, edx
        call newparty
        test al, al
        jne  mo_ok
    mo_next:
        inc  dword ptr [ebp + {F_TRY:#x}]
        jmp  mo_try
    mo_ok:
        mov  al, 1
        ret
    mo_fail:
        xor  eax, eax
        ret

    mo_stand:
        mov  eax, dword ptr [ebp + {F_NF:#x}]
        mov  dl, byte ptr [eax + 0x14]
        mov  cl, byte ptr [eax + 0x15]
        mov  eax, dword ptr [ebp + {F_UNIT:#x}]
        call {UNIT_VALIDTERRAIN:#x}
        ret
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP, "STRUCT": STRUCT_CELL, "ARMYHS": ARMYHS_CELL,
                                "GUARD": GUARD, "NOBAT": NOBAT, "PENDP": PENDP, "NOFLEE": FLAG_NOFLEE,
                                "CMTE": CMTE_CELL, "FASTC": FAST_CELL, "FORCE": FORCE, "ALOG": ALOG_CELL,
                                "RSD": RS_DROWN, "RSB": RS_BURN, "RSC": RS_CRUSH, "DNT": ("TAIL", 0)}, tail())


# ---- AoWTCPCK -------------------------------------------------------------------------------
T_SLOT = (0x00448000, 0x00448200)
T_CMAP, T_HSMAP = 0x0046C064, 0x0046E8D4        # the combat map global; the AoWHSMap import cell
T_GETFIELD, T_SETDIR = 0x00401E6C, 0x00402AF4   # HSEngine.TMapContainer.GetField / TUnitHS.SetDirection
T_TABX, T_TABY = 0x00467024, 0x004670E4         # SetupUnit's defender formation, 6 directions x 8 slots
FLEE_CLASS, NO_CLASS = 0x220528, 0x7FFFFFFF
SUR_BACK, DEP_BACK, DEP_CITY, DEP_PLACE = 0x0041CC8A, 0x00426FE0, 0x0042700C, 0x0042707D
T_HOOKS2 = {   # site: (vanilla, marker, form, function range for the interior check)
    0x00408374: (bytes.fromhex("ba28052200"), 1, "call", (0x00408278, 0x004085F0)),
    0x0041CC84: (bytes.fromhex("558bec83c4f4"), 2, "jmp", (0x0041CC84, 0x0041CD12)),
    0x00426FD7: (bytes.fromhex("8b45fc80780800752c"), 3, "jmp", (0x00426D1C, 0x004271D4)),
}


def tc_core(va):
    src = f"""
    tc_isfall:
        mov  eax, dword ptr [ebx + {{CMAP}}]
        test eax, eax
        je   tf_no
        mov  eax, dword ptr [eax + 0xe4]
        test eax, eax
        je   tf_no
        mov  eax, dword ptr [eax + 0xc]
        test eax, eax
        je   tf_no
        mov  ecx, dword ptr [eax + 0x14]
        cmp  ecx, dword ptr [eax + 8]
        jne  tf_no
        mov  ecx, dword ptr [eax + 0x18]
        cmp  ecx, dword ptr [eax + 0xc]
        jne  tf_no
        mov  ecx, dword ptr [eax + 0x1c]
        cmp  ecx, dword ptr [eax + 0x10]
        je   tf_no
        push eax
        push ecx
        mov  edx, dword ptr [eax + 0x14]
        mov  ecx, dword ptr [eax + 0x18]
        mov  eax, dword ptr [ebx + {{HSMAP}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x10]
        call {T_GETFIELD:#x}
        pop  ecx
        test eax, eax
        je   tf_no
        mov  dl, byte ptr [eax + 0x14]
        cmp  dl, {SKY:#x}
        je   tf_yes
        cmp  dl, {CHASM:#x}
        jne  tf_no
    tf_yes:
        mov  eax, ecx
        ret
    tf_no:
        xor  eax, eax
        ret

    get_anc:
        {{ANC}}
        ret

{mark(1)}
    tc_flee:
        push ebx
        call get_anc
        call tc_isfall
        pop  ebx
        mov  edx, {FLEE_CLASS:#x}
        test eax, eax
        je   tl_out
        mov  edx, {NO_CLASS:#x}
    tl_out:
        ret

{mark(2)}
    tc_sur:
        push eax
        push edx
        push ebx
        call get_anc
        call tc_isfall
        test eax, eax
        pop  ebx
        pop  edx
        pop  eax
        jne  ts_no
        push ebp
        mov  ebp, esp
        add  esp, -0xc
        jmp  {SUR_BACK:#x}
    ts_no:
        ret

{mark(3)}
    tc_dep:
        cmp  byte ptr [ebp - 5], 0
        jne  td_van
        push ebx
        call get_anc
        call tc_isfall
        test eax, eax
        je   td_pop
        cmp  dword ptr [eax + 0x50], 0
        je   td_pop
        mov  ecx, dword ptr [ebp - 0x24]
        and  ecx, 7
        add  ecx, 24
        mov  edx, dword ptr [ebx + ecx*4 + {{TABX}}]
        mov  dword ptr [ebp - 0x18], edx
        mov  edx, dword ptr [ebx + ecx*4 + {{TABY}}]
        mov  dword ptr [ebp - 0x1c], edx
        pop  ebx
        mov  dl, 1
        mov  eax, dword ptr [ebp - 0x10]
        call {T_SETDIR:#x}
        jmp  {DEP_PLACE:#x}
    td_pop:
        pop  ebx
    td_van:
        mov  eax, dword ptr [ebp - 4]
        cmp  byte ptr [eax + 8], 0
        jne  {DEP_CITY:#x}
        jmp  {DEP_BACK:#x}
    """
    return pic(src, va, "ebx", {"CMAP": T_CMAP, "HSMAP": T_HSMAP, "TABX": T_TABX, "TABY": T_TABY})


def entry_offset(blob, n):
    sig = bytes([0xCC, 0x5A, 0x46, n])
    hits = [i for i in range(len(blob) - 3) if blob[i:i + 4] == sig]
    assert len(hits) == 1, "entry marker %d found %d times" % (n, len(hits))
    return hits[0] + 4


def markers_unique(blob, count):
    k = [i for i in range(len(blob) - 2) if blob[i:i + 3] == MARK]
    assert len(k) == count, "%d entry markers, expected %d" % (len(k), count)


def segments(blob, va):
    """The core cut at its entry markers, so a linear disassembly never decodes a marker."""
    cuts = [0] + [i for i in range(len(blob) - 3) if blob[i:i + 3] == MARK] + [len(blob)]
    out = []
    for a, b in zip(cuts, cuts[1:]):
        a += 4 if blob[a:a + 3] == MARK else 0
        out.append((va + a, blob[a:b]))
    return out


def rng_sites(blob, va):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    return [i.address for sva, seg in segments(blob, va) for i in md.disasm(seg, sva)
            if i.mnemonic == "call" and i.op_str == "%#x" % RANDOM]


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def checks(d):
    u = lambda v: struct.unpack_from("<I", d, P.va2off(d, v))[0]
    rb = lambda va, n: bytes(d[P.va2off(d, va):P.va2off(d, va) + n])
    if rb(0x5578CD1B, 8) != bytes.fromhex("84db0f8421020000"):
        sys.exit("ABORT: ValidateTerrainEx's `test bl,bl / je` is not before the gates")
    if rb(0x55724E20, 5) != call_to(0x55724E20, PLACE):
        sys.exit("ABORT: 0x55724E20 is not TCombatUnit.Finalize's `call TAbstractUnit.Place`")
    if rb(0x557252D7, 4) != bytes.fromhex("8bc38b10"):
        sys.exit("ABORT: TCombatUnit.ObjectDestroyed's `mov eax,ebx / mov edx,[eax]` moved")
    if rb(HANDLED, 2) != b"\x8b\xc6" or rb(HANDLED + 2, 1) != b"\xe8":
        sys.exit("ABORT: %08X is not `mov eax,esi / call TArmy.Validate`" % HANDLED)
    for cell in (STRUCT_CELL, ARMYHS_CELL, FAST_CELL):
        if not 0x55700000 < u(cell) < 0x55900000:
            sys.exit("ABORT: class cell %08X does not hold a VMT" % cell)
    if u(CMTE_CELL) != VMT_CMTE or u(VMT_CMTE - 0x40) != VMT_CMTE:
        sys.exit("ABORT: the TArmyCombatMoveTE class cell moved")
    if u(VMT_CMTE + 0x54) != 0x5574A144 or u(VMT_CMTE + 0x58) != 0x557489BC:
        sys.exit("ABORT: TArmyCombatMoveTE's ProcessMove / Validate slots moved")
    if rb(0x5574A178, 6) != bytes.fromhex("807b3802751d") or rb(0x557489C1, 1) != b"\xc3":
        sys.exit("ABORT: ProcessMove's state test or Validate's ret moved")
    if rb(0x557496DB, 2) != b"\x8b\xda":
        sys.exit("ABORT: CombatExecuted no longer keeps the combat in EBX")
    if rb(0x55727BD8, 5) != bytes.fromhex("8bf08b5e0c"):
        sys.exit("ABORT: InitDefaultArmies no longer keeps the combat in ESI")


def tc_checks(t):
    u = lambda v: struct.unpack_from("<I", t, P.va2off(t, v))[0]
    rb = lambda va, n: bytes(t[P.va2off(t, va):P.va2off(t, va) + n])
    if rb(0x00408379, 8) != bytes.fromhex("8b45f48b08ff517c"):
        sys.exit("ABORT: ExecuteDefaultMove's flee lookup is not `mov eax,[ebp-0xc] / call [ecx+0x7c]`")
    if rb(0x0041CC8A, 6) != bytes.fromhex("8855f78945fc"):
        sys.exit("ABORT: Surrender's prologue moved")
    if rb(0x00426FE0, 5) != bytes.fromhex("a164c04600"):
        sys.exit("ABORT: SetupUnit's non-city facing code moved")
    xs = struct.unpack_from("<48i", t, P.va2off(t, T_TABX))
    ys = struct.unpack_from("<48i", t, P.va2off(t, T_TABY))
    if xs[24:32] != (32, 34, 30, 32, 36, 28, 34, 30) or ys[24:32] != (32, 31, 31, 30, 30, 30, 29, 29):
        sys.exit("ABORT: the defender formation table changed")


def tc_interior(t, fn, lo, hi):
    """Branches and jump-table dwords in fn landing strictly inside (lo, hi), plus rel32s file-wide."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.skipdata = True
    o = P.va2off(t, fn[0])
    buf = bytes(t[o:o + fn[1] - fn[0]])
    bad = []
    for x in md.disasm(buf, fn[0]):
        if (x.mnemonic.startswith("j") or x.mnemonic == "call") and not lo <= x.address < hi:
            try:
                tg = int(x.op_str, 16)
            except ValueError:
                continue
            bad += [x.address] if lo < tg < hi else []
    bad += [fn[0] + i for i in range(len(buf) - 3) if lo < struct.unpack_from("<I", buf, i)[0] < hi]
    return bad + P.rel32_into(t, lo, hi)


def hook_bytes(site, van, tgt, form):
    if form == "nopcall":
        return b"\x90" + call_to(site + 1, tgt)
    if form == "jmp":
        return b"\xE9" + struct.pack("<i", tgt - (site + 5)) + b"\x90" * (len(van) - 5)
    return call_to(site, tgt) + b"\x90" * (len(van) - 5)


def go(argv):
    from build_lethe import interior_jumps
    # ---- AoWTCPCK
    module(TCPCK, 0x00400000)
    t = open(TCPCK, "rb").read()
    tc_checks(t)
    tva = T_SLOT[0]
    tblob = tc_core(tva)
    assert tva + len(tblob) <= T_SLOT[1], "AoWTCPCK slot overflow"
    markers_unique(tblob, 3)
    for site, (van, n, form, fn) in T_HOOKS2.items():
        bad = tc_interior(t, fn, site, site + len(van))
        if bad:
            sys.exit("ABORT: jumps into %08X's interior from %s" % (site, ", ".join("%08X" % a for a in bad)))
    t_hooks = [(site, van, hook_bytes(site, van, tva + entry_offset(tblob, n), form))
               for site, (van, n, form, _fn) in T_HOOKS2.items()]
    print("  AoWTCPCK core %08X, %d B" % (tva, len(tblob)))
    run("build_flight_fall [AoWTCPCK] -- fall battles: no retreat, inside the walls", t_hooks,
        [("tc_fall", tva, tblob)], T_SLOT, [], argv)
    print()
    # ---- AoWEPACK
    module(EPACK, 0x55700000)
    d = open(EPACK, "rb").read()
    checks(d)
    va = SLOT[0]
    blob = core(va)
    assert va + len(blob) <= SLOT[1], "slot overflow"
    markers_unique(blob, 9)
    ranges = [(HOOK, HOOK + len(HOOK_VAN))] + [(s, s + len(v)) for s, (v, _n, _f) in HOOKS2.items()]
    bad = interior_jumps(d, ranges)
    if bad:
        sys.exit("ABORT: jumps into a hook's interior: " + ", ".join("%08X->%08X" % x for x in bad))
    print("  core %08X, %d B; RNG sites (synced TAoWHSMap.Random): %s"
          % (va, len(blob), ", ".join("%08X" % a for a in rng_sites(blob, va))))
    assert sorted(rng_sites(blob, va)) == sorted(RNG_SITES.values()), \
        "the core's Random calls moved: update RNG_SITES"
    hooks = [(HOOK, HOOK_VAN, b"\xE9" + struct.pack("<i", va - (HOOK + 5)) + b"\x90\x90")]
    hooks += [(site, van, hook_bytes(site, van, va + entry_offset(blob, n), form))
              for site, (van, n, form) in HOOKS2.items()]
    run("build_flight_fall [AoWEPACK] -- falling to the level below, fall battles", hooks,
        [("cave_fall", va, blob)], SLOT, [], argv)


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])   # both modules verify first
        print("\n" + "=" * 60)
    go(argv)
