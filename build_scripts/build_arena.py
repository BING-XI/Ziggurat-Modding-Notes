#!/usr/bin/env python3
r"""
AoW1 mod -- "arena" STAGES 1+2+3: the Arena stops being a unit-training shop and becomes a place you
fight arena battles against a hidden independent stack, for gold, XP and treasure.

FULL DESIGN: Modding Resources/Arena_Rework_Feasibility.md

================================================================================
STAGE 1 -- persistent per-arena state
================================================================================
TArena (VMT 0x557D6240) is the thinnest structure subclass in the game: instance size 0x30, exactly
its parent TStructure's, i.e. it adds NO fields and has NO ReadWrite of its own. Stage 1 gives it
two:

    arena[+0x30]  byte  flags   bit0 = EMPTY (fought out)   bit1 = SEEDED
    arena[+0x34]  dword seed    roster seed for this stocking

  D1  instance size word [VMT-0x1C] @0x557D6224 : 0x30 -> 0x38
  D2  VMT +0x018 (ReadWrite) @0x557D6258 : TStructure.ReadWrite -> cave_rw
  D3  VMT +0x174 (NewDay)    @0x557D63B4 : TStructure.NewDay    -> cave_newday

Serialisation is SAFE to extend: AoW streams objects through Engine.TPropertyTable, a table indexed
by numeric property id. TEReadStorageStream.rwByte/rwInteger call TPropertyTable.FindOffset
@0x5550FE70 and SKIP the read when it returns -1 (rwByte additionally zeroes the target, verified at
0x55510F89). So an old save simply lacks our ids and the fields keep their zero-init value -- which
is deliberately "stocked, unseeded". New ids 0x70 / 0x71.

  PROPERTY-ID COLLISION SCAN (2026-07-30, read from the bytes, whole TArena chain):
    TMapObject.ReadWrite   @0x55609824 (HSEPack) : rwInteger 1
    TMultiHexMO.ReadWrite  @0x5560AAB8 (HSEPack) : rwByte 3, rwByte 4
    TStructure.ReadWrite   @0x5575E658           : rwByte 0, rwInteger 0x62, rwByteEx 0x63
  => {0,1,3,4,0x62,0x63} in use. 0x70/0x71 are clear. (Sibling classes use 5,6 / 0x14-0x17 /
  0x1C / 0x1E-0x21 -- not in TArena's chain, but avoided anyway.)

  Stream vtable slots (dumped from TEReadStorageStream VMT 0x5550DE38 and TEWriteStorageStream
  0x5550DF08, both identical in layout):
    +0x1C rwData(ptr,size,id)  +0x2C rwInteger(ptr,id)  +0x30 rwByte(ptr,id)  +0x44 rwByteEx

cave_newday runs once per GAME DAY per arena (TStructure.NewDay is a bare `ret`; NewDay is the
synchronised once-per-day event TExplorationSite/TWizardsTower already hook). It:
    * seeds an unseeded arena  (covers new maps AND pre-existing saves on first load)
    * if EMPTY, rolls TAoWHSMap.Random(map,10)==0 -> restock + fresh seed        (= 10 %/day)
TAoWHSMap.Random @0x5577827C is the MP-safe RNG: it installs map[+0x230], draws, and writes the
advanced seed back, so every peer walks the same sequence. Same call the vanilla item roller uses.

================================================================================
STAGE 2 -- the battle (FAST combat, category from the TE nibble, no rewards yet)
================================================================================
  D4  TArena.UnitTrainCost @0x557D6704 : `push ebx; push esi; mov...` -> `xor eax,eax; ret`
  D5  TArena.ExecuteTE     @0x557D6819 : 5 bytes -> E9 rel32 -> cave_fight

D4 makes every unit in the visiting stack report training cost 0. Consequence chain (all vanilla):
TArena.Enter sets the "trainable" bit for every unit whose cost != -1, so ALL eight checkboxes
enable; CanTrainUnits sums 0 and passes the gold test; the Select button works. So stage 2 is driven
from the EXISTING dialog with ZERO changes to AoW.exe: tick any unit, press Select, the battle runs.
(The dialog is rewritten properly in stage 4; the whole training code path is dead after this.)
NOTE this also makes build_copper_medal.py's byte at 0x557D673A (`cmp al,2`->`cmp al,3` inside
UnitTrainCost) dead code. Harmless -- but do not go looking for a live effect from it.

D5 hooks TArena.ExecuteTE right AFTER its `cmp [te+0x18],1 ; jne epilogue`, so non-train TEs (raze
uses -1, handled by TStructure.ExecuteTE which already ran) are untouched. The cave runs inside
ExecuteTE's SEH frame but builds its OWN stack frame, so ExecuteTE's managed-string locals
([ebp-0x10]/[ebp-0x14]/[ebp-0x18]/[ebp-0x24], cleared by the epilogue) and its [ebp-5] result byte
are never disturbed. It exits by jumping to ExecuteTE's own epilogue at 0x557D6967 with ESP/EBP
exactly as found.

The combat construction is transplanted from build_razebattle_tower.py's cave_towerraze, which is
CONFIRMED WORKING in-game (Stage 1, 2026-07-10) -- same sequence, same slots, same arg order:
    TArmy.Create(TDefendersArmy) -> fill -> CreateCombat(map,0x202B0) -> combat[+0x2C]/[+0x30]
    -> TCombat.Setup slot 0x60 (9 stack args) -> AddArmy(side 0) -> AddArmyEx(side 1, -1,-1,-1)
    -> combat[+0x40]=1 -> Lock/run 0x68,0x70,0x64,0x74,0x6C/Unlock -> latch combat[+0x14]
    -> TCombatEventLog -> DestroyCombat -> UnlockGameOverEvent
Two deliberate differences from the raze cave:
  * the roster is built HERE from a hardcoded index table (see ROSTERS) rather than from
    GenerateRazeDefenders, because TStructureResource.Create @0x5576046C creates the raze-defender
    collection at resource[+0x5C] EMPTY and nothing in Release.hss is known to populate the Arena's.
    Seeded from arena[+0x34] so the stack is stable for a given stocking.
  * combat[+0x2C] is set to 0 = NO completion callback. Verified safe: TCombat.UnlockExecuted
    @0x55728104 fires it only when `word [combat+0x2E] != 0`, i.e. the high half of the callback
    pointer -- a null pointer is a no-op. Fast combat is synchronous so the result is read inline.
    Stage 3 replaces this with a real callback for the gold/XP/item rewards.

WALLS: the razer party's behind-wall flag is cleared (`mov byte [party+0x18],0` on AddArmy's return)
exactly as the raze cave does. That is the only input to TCombat.Initialize's wall branch, so NO
TCombatWall is built -- an arena fight is a wall-less "inside" battle. This also keeps stage 3's
survivor walk away from the TCombatWall `+0x4C` alias that froze the game twice
(Raze_Dialog_Freeze_Fix.md §8/§9). Keep it that way.

================================================================================
STAGE 3 -- rewards (flat per category)
================================================================================
Done INLINE in cave_fight, not from a completion callback. The fast path is synchronous, and the
insertion point -- after UnlockExecuted, before DestroyCombat -- is exactly where vanilla's
CombatExecuted -> ExecuteSearchDone fires, so combatData is still alive and the ordering matches the
engine's own. (Stage 5 will move this block into a real callback for the tactical/async path.)

  (a) XP   +5 / +10 / +15 to every SURVIVING unit of the arena player, ANY outcome.
      ⚠ From the STRATEGIC side. Re-fetch the army off the arena's field
      (self[+4].vmt[0x80](0x20217) -> [+0x1C], owner-checked), walk it with vmt[0x54] /
      TUnitList.GetUnit, and do unit.vmt[0x15C]() + N -> unit.vmt[0x160]() (TAbstractUnit slots, so
      TUnit and THero both take their proper rank-up / UpdateDefaultAbilities path).

      DO NOT walk combat[+0x0C]. The first build did, and XP silently did nothing while gold
      worked. TCombatUnit.Finalize @0x55724D44 (slot 0x0D0, called by TCombat.Finalize = slot 0x6C,
      which we invoke BEFORE this block) Places each survivor back on the map and then calls
      `(*vmt-4)(obj,1)` -- Delphi 3's vmtDestroy -- on the combat object. Every object whose party
      has a map field is therefore already FREED; only the off-map militia party is spared, because
      AddArmyEx's -1,-1,-1 leaves party[+0x0C] == -1. This is also exactly why vanilla's
      TExplorationSite.CombatExecuted only ever touches GetPlayer()==0 objects: they are the only
      ones still alive there. Finalize has already removed the dead, so the re-fetched army list IS
      the survivor set.
      NOTE a stalemate (result 2) leaves survivors and therefore still pays XP -- that follows the
      spec "XP to all surviving units" literally.

  (b) GOLD +100 / +200 / +300, **win only** (result byte combat[+0x14] in {3,6}, the same test
      ExecuteSearchDone uses). TPlayer.SetGems takes an ABSOLUTE value, so it is
      player[+0xC4] + GOLD[cat]. Win-gating closes the "sell your army for 300 gold" hole that flat
      gold on a loss would open; the XP half self-limits (lose => no survivors => no XP).

  (c) ITEM on "strong" (category 2) only, and only on a win. Seed System.RandSeed from
      TAoWHSMap.Random FIRST -- GenerateItem draws through the global seed, so peers diverge
      otherwise; TItemExplorationSite.Generate does exactly this. GenerateItem does NOT construct
      an item: it builds a weighted candidate list from TItemControl's existing unplaced items and
      returns one (or 0 if the pool is exhausted), so the item is already registered and
      TItem.PlaceOnMap alone completes the award. Dropped on the arena's own hex.

⚠ keystone lands a trap here: `push 0xFFFF` assembles as `6A FF` = push imm8 -1 (0xFFFFFFFF), not
`68 FF FF 00 00`. As a value cap that would reject every item and silently award nothing. The cave
goes through EAX instead and build_all() asserts the encoding. Audited 2026-07-31: no other script
in build_scripts/ pushes a >imm8 literal that keystone truncates.

================================================================================
NOT IN THIS BUILD (by design -- stages 4/5)
================================================================================
  * the three-category dialog (AoW.exe DFM + handlers); stages 1-3 always fight the category in the
    TE's high nibble, which vanilla TrainUnits leaves 0 => WEAK. So gold/XP/item are wired for all
    three tiers but only tier 0 is reachable until stage 4.
  * tactical combat + the hardened TCombatTypeRequestEventLog contract
  * an SEH frame around the combat lifecycle (the raze cave has none either; a throw between
    CreateCombat and DestroyCombat leaks map[+0x120] for the session -- symptom to watch is
    "Combat already created" on every later battle). Mitigated by the map[+0x120] pre-check.

================================================================================
SAFETY
================================================================================
* .reloc VERIFIED (2026-07-30) at every site: 0x557D6224 none, 0x557D6258 HAS one (VMT slot -- a
  cave VA stored there rebases correctly), 0x557D63B4 HAS one, 0x557D6704 none, 0x557D6819 none.
  TArena owns a physically distinct VMT, so the two slot repoints are ARENA-ONLY.
* PIC: every cave reaches its globals through the standard `call $+5; pop ecx; sub ecx,<linktime>`
  load-delta anchor. No absolute data reference is emitted without it.
* Instance growth is a proven technique here (build_spellcast.py grows TUnit 0x48->0x94 at
  [VMT-0x1C]); Delphi's InitInstance zero-fills, so the new fields need no Create override.
* Cave zone 0x55814000..0x55814900 -- inside the contiguous verified-zero CODE run
  0x5581307F..0x558E7918 (870,553 B free, measured on the LIVE dll 2026-07-30). Clear of
  build_sitedefender_vary.py (0x55812400/0x55812440) and of the crowded 0x5580C000-0x5580E400 pocket.
* NO BSS is claimed. (Free BSS, if a later stage needs it, is 0x558FA844-0x558FA85F and
  0x558FA862+; 0x558FA800/0x801 were double-claimed once and silently corrupted every battle for
  weeks -- see Raze_Dialog_Freeze_Fix.md §7.)
* DOWNSTREAM RNG DRIFT: cave_newday advances map[+0x230] once or twice per arena per day, so a game
  with arenas will not reproduce an arena-free draw sequence. Deterministic and identical on every
  peer, which is what matters for MP.

Backup: AoWEPACK.dpl.pre-arena
Dry-run by default; --apply to write (close ALL AoW binaries first -- they lock the DLL).
--undo removes the feature SURGICALLY (restores the 5 sites, zeroes the caves) WITHOUT touching any
.pre-* backup, so features applied later survive. Prefer it over restoring the backup.
Idempotent: re-running with no args verifies the currently-installed state.
"""

import os
import sys
import shutil
import struct
import argparse

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

DLL = os.path.join(GAME, "AoWEPACK.dpl")
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-arena")

DLL_BASE = 0x55700000
VA_BASE = 0x55700C00                     # CODE: file_offset = VA - VA_BASE
CODE_END = 0x558E7918                    # end of CODE vsize

# ---------------------------------------------------------------- patch sites
VA_INSTSIZE   = 0x557D6224               # TArena VMT-0x1C
VA_VMT_RW     = 0x557D6258               # TArena VMT+0x018  ReadWrite
VA_VMT_NEWDAY = 0x557D63B4               # TArena VMT+0x174  NewDay
VA_TRAINCOST  = 0x557D6704               # TArena.UnitTrainCost entry
VA_EXECTE     = 0x557D6819               # TArena.ExecuteTE, just after `cmp [te+0x18],1 / jne`

ORIG_INSTSIZE = 0x30
NEW_INSTSIZE  = 0x38
ORIG_RW       = 0x5575E658               # AoWE.TStructure.ReadWrite
ORIG_NEWDAY   = 0x5575F338               # AoWE.TStructure.NewDay  (a bare `ret`)
ORIG_TRAINCOST = bytes.fromhex("535 68b".replace(" ", ""))   # placeholder, fixed below
ORIG_TRAINCOST = bytes.fromhex("53568b")                     # push ebx; push esi; mov ...
NEW_TRAINCOST  = bytes.fromhex("33c0c3")                     # xor eax,eax; ret
ORIG_EXECTE   = bytes.fromhex("8d45f0508b")                  # lea eax,[ebp-0x10]; push eax; mov...
VA_EXECTE_EPI = 0x557D6967               # ExecuteTE epilogue (SEH unlink + string cleanup)

# ---- stage 4 sites (all verified .reloc-clean 2026-07-31) ----
VA_AVAIL        = 0x557D6C3F             # in TArena.Enter, just before the event log is Shown
VA_AVAIL_RESUME = 0x557D6C45             # the `mov dl,1` after the displaced three instructions
ORIG_AVAIL      = bytes.fromhex("6a006a00b1")                # push 0; push 0; mov cl,1
VA_SETSEL       = 0x557D6DA4             # TEnterArenaEventLog.SetSelection

ORIG_SETSEL     = bytes.fromhex("22501d8850")                # and dl,[eax+0x1d]; mov [eax+0x1c],..
VA_TRAIN        = 0x557D6DAC             # TEnterArenaEventLog.Train
VA_CANTRAIN     = 0x557D6E28             # TEnterArenaEventLog.CanTrain
ORIG_PROLOG5    = bytes.fromhex("5356575551")                # push ebx/esi/edi/ebp/ecx (both)
VA_SELINFO      = 0x557D6EA4             # TEnterArenaEventLog.GetSelectionInfo
ORIG_SELINFO    = bytes.fromhex("558bec83c4")                # push ebp; mov ebp,esp; add esp,..
# ---- stage 4b sites ----
VA_GETUNIT          = 0x557D6D6C         # TEnterArenaEventLog.GetUnit
ORIG_GETUNIT        = bytes.fromhex("53568bf28b")            # push ebx; push esi; mov esi,edx; ..
VA_EVDESTROY        = 0x557D6D38         # TEnterArenaEventLog.Destroy
# ⚠ Displace SIX bytes, not five: the prologue is
#     53 push ebx | 56 push esi | 8B DA mov ebx,edx | 8B F0 mov esi,eax | 8B 46 20 mov eax,[esi+20]
# Five bytes would end mid-`mov esi,eax`, and the resume address 0x557D6D3A that implies lands
# INSIDE our own E9's rel32 operand -- the cave jumped into its own jump, executed the displacement
# bytes as code, and reached `mov eax,[esi+0x20]` with ESI garbage. That is exactly the
# "Access violation ... Read of address 00000020" seen in-game 2026-07-31.
VA_EVDESTROY_RESUME = 0x557D6D3E         # the `mov eax,[esi+0x20]` after all four replayed insns
ORIG_EVDESTROY      = bytes.fromhex("53568bda8bf0")          # the four-instruction prologue
# ---- stage 5 sites ----
VA_VMT_TERRIMG  = 0x557D636C             # TArena VMT +0x12C = GetTerrainTypeImage
ORIG_VMT_TERRIMG = 0x5575E6A0            # AoWE.TStructure.GetTerrainTypeImage
FN_STRUCT_TERRIMG = 0x5575E6A0
FN_GET_IMAGESEQ = 0x557028E4             # ILPACK thunk: TImageSequenceList.GetImageSequence
VA_ENTER_JE     = 0x557D6BC3             # the `je 0x557D6C59` right after CanEnter in Enter
ORIG_ENTER_JE   = bytes.fromhex("0f8490000000")              # je rel32 -> 0x557D6C59
VA_ENTER_RESUME = 0x557D6BC9             # CanEnter passed, arena stocked -> build the event log
VA_ENTER_TRUE   = 0x557D6C55             # `mov al,1` epilogue
VA_ENTER_FALSE  = 0x557D6C59             # `xor eax,eax` epilogue
# ---- the per-unit budget surcharge (H1) ----
# 0x5575B2CF `add [ebp-0xc],eax` is the ONE place FillWithRandomUnits adds an ACCEPTED unit's cost
# to the running total, so taxing the cost call just above it is the whole of the surcharge.
# The three other `call [reg+0x174]` sites in that function are lookahead ("would this unit fit"),
# and leaving them untaxed only means the loop may overshoot by up to 5 before the terminate check
# at 0x5575B2E1 stops it -- self-correcting, so one hook is enough.
VA_UNITCOST     = 0x5575B2C9             # call dword ptr [edx+0x174]  (6 B, .reloc-clean)
ORIG_UNITCOST   = bytes.fromhex("ff9274010000")
VA_UNITCOST_RES = 0x5575B2CF             # the `add [ebp-0xc],eax`
# ⚠ FillWithRandomUnits is SHARED with raze militia / site defenders / dungeon prisoners / city
# rebels, whose budgets are tuned to vanilla costs. The surcharge is therefore gated on a BSS flag
# that only cave_fight raises, so nothing else in the game changes.
FLAG_ARENAFILL  = 0x558FA870             # free BSS (claimed: ..0x800/0x801 path, 0x860/0x861 simfly)

# ---------------------------------------------------------------- callees (all rel32 from a cave)
FN_STRUCT_RW      = 0x5575E658   # TStructure.ReadWrite         EAX=self, EDX=stream
FN_STRUCT_NEWDAY  = 0x5575F338   # TStructure.NewDay            EAX=self  (bare ret)
FN_MAP_RANDOM     = 0x5577827C   # TAoWHSMap.Random             EAX=map, EDX=range -> EAX; keeps EBX/ESI
FN_TARMY_CREATE   = 0x5578C16C   # TArmy.Create                 EAX=classVMT, DL=1, ECX=0 -> EAX
FN_UIL_CREATE     = 0x5578506C   # TUnitIndexList.Create        EAX=classVMT, DL=1 -> EAX
FN_ILIST_ADD      = 0x55702E74   # TIntegerList.Add (thunk)     EAX=list, EDX=value
FN_FILL_RND       = 0x5575B160   # FillWithRandomUnits          EAX=list, EDX=army, ECX=maxlvl, +push budget, +push flags
FN_UNITLIST_GET   = 0x5578309C   # TUnitList.GetUnit            EAX=list, EDX=i -> EAX
FN_OBJ_FREE       = 0x557010B8   # TObject.Free (thunk)         EAX=obj
FN_LOCK_GAMEOVER  = 0x55776830   # TAoWHSMap.LockGameOverEvent  EAX=map
FN_UNLOCK_GAMEOVER= 0x55776774   # TAoWHSMap.UnlockGameOverEvent
FN_CREATE_COMBAT  = 0x55778714   # TAoWHSMap.CreateCombat       EAX=map, EDX=flag -> EAX
FN_DESTROY_COMBAT = 0x557787F8   # TAoWHSMap.DestroyCombat      EAX=map
FN_LOCK_EXEC      = 0x55728100   # TCombat.LockExecuted
FN_UNLOCK_EXEC    = 0x55728104   # TCombat.UnlockExecuted
FN_ADD_ARMY       = 0x55727804   # TCombat.AddArmy    EAX=combat,EDX=army,CL=side +push l,y,x; ret 0xC
FN_ADD_ARMY_EX    = 0x557279D0   # TCombat.AddArmyEx  EAX=combat,EDX=army,CL=side +push -1,-1,-1,pos; ret 0x10
FN_EVENTLOG_CREATE= 0x557FD398   # TEventLog.Create   EAX=classVMT, DL=1, ECX=0 -> EAX
FN_SET_COMBAT_LOG = 0x55728F2C   # TCombatEventLog.SetCombatLogbook  EAX=log, EDX=combat[+0x18]
FN_GET_PLAYERS    = 0x557544D0   # TPlayerList.GetPlayers  EAX=map[+0x140], EDX=idx -> EAX
FN_ADD_EVENT      = 0x557FDB90   # TEventLogbook.AddEvent  EAX=player[+0xD8], EDX=eventlog
# ---- stage 3 rewards ----
FN_SET_GEMS       = 0x55751F38   # TPlayer.SetGems         EAX=player, EDX=ABSOLUTE new value
# The four below are NOT used any more -- the XP award moved to the strategic side (see the comment
# in src_fight). Kept because they are verified and the next stage may want them.
FN_IS_CLASS       = 0x557010C0   # System.@IsClass         EAX=obj, EDX=classVMT -> AL
FN_TCD_GETCOUNT   = 0x55728BEC   # TCombatData.GetCount    EAX=data -> EAX   ([[[data+0x34]+8]+8])
FN_TCD_GETOBJECTS = 0x55728BF8   # TCombatData.GetObjects  EAX=data, EDX=i -> EAX
FN_COBJ_GETPLAYER = 0x557268E4   # TCombatObject.GetPlayer EAX=obj -> AL (reads obj[+0x45])
FN_GENERATE_ITEM  = 0x55794F40   # TItemControl.GenerateItem EAX=ctrl, DL=typemask, ECX=0, +push cap; ret 4
FN_PLACE_ON_MAP   = 0x55794730   # TItem.PlaceOnMap        EAX=item, EDX=map, CL=x, +push y, +push l
# ---- stage 4 (category selection + the battle TE) ----
FN_LSTRASG        = 0x55701150   # System.@LStrAsg         EAX=&dest, EDX=src (refcount -1 = literal)
FN_AUNIT_CREATE   = 0x5577EB28   # TAbstractUnit.Create    EAX=classVMT, DL=1, ECX=0 -> EAX
FN_GET_UNITRES    = 0x55785050   # TUnitResourceList.GetUnitResource  EAX=list, EDX=idx -> EAX
FN_SET_UNITRES    = 0x55782BE4   # TUnit.SetUnitResource   EAX=unit, EDX=resource
FN_ILIST_GET      = 0x55702E94   # TIntegerList.Get (thunk) EAX=list, EDX=i -> EAX
CLASSREF_TUNIT    = 0x55710C6C   # *  = TUnit VMT
PTR_AOWHSSET      = 0x558FA044   # AoWHSSet; [+0x5C] = the TUnitResourceList
FN_GET_BUSY       = 0x557516D0   # TPlayer.GetBusy         EAX=player -> AL
FN_GET_TOKEN_CTRL = 0x5570372C   # NetworkE.GetTokenControl EAX=map[+0x23C], EDX=player -> EAX
MAP_TOKENMGR_OFF  = 0x23C

# ---------------------------------------------------------------- data slots (reached via delta)
PTR_MAPCTRL       = 0x558E9494   # **PTR_MAPCTRL = the map object
PTR_RANDSEED      = 0x558FB720   # *PTR_RANDSEED  = &System.RandSeed
CLASSREF_DEFARMY  = 0x557C1274   # *  = TDefendersArmy VMT (0x557C12B4)
CLASSREF_UIL      = 0x557110D8   # *  = TUnitIndexList VMT (0x55711118)
VMTREF_EVENTLOG   = 0x557171BC   # *  = TCombatEventLog VMT
CLASSREF_CBTUNIT  = 0x55715A54   # *  = TCombatUnit VMT (0x55715A94) -- the IsClass gate
PTR_ITALL         = 0x558E8F40   # *  = &itAll byte (item-type bitmask; masks scrolls out)

FIELD_SELECTOR    = 0x20217      # field slot 0x80 selector -> the co-located army container
FLAG_COMBAT_FAST  = 0x202B0      # CreateCombat flag: fast/synchronous
FILL_FLAGS        = 7            # byte pushed by GenerateRazeDefenders (DAT @0x5575FE08 = 0x07)
FILL_MAXLEVEL     = 4            # ECX, as GenerateRazeDefenders
SEED_RANGE        = 0xFFFFFF     # matches TExplorationSite.Generate (the item roller)
REFILL_ONE_IN     = 10           # 10 % per game day

PROP_FLAGS = 0x70                # new property ids (collision scan in the header)
PROP_SEED  = 0x71

OFF_FLAGS = 0x30                 # arena[+0x30] byte
OFF_SEED  = 0x34                 # arena[+0x34] dword
BIT_EMPTY  = 1
BIT_SEEDED = 2

# ---------------------------------------------------------------- cave placement
# NOTE when growing this zone: CAVE_LIMIT must never SHRINK between builds, or bytes written by a
# previous build would be orphaned outside the region this script zeroes on re-apply.
CAVE_RW      = 0x55814000
CAVE_NEWDAY  = 0x55814060
CAVE_FIGHT   = 0x55814100
CAVE_AVAIL   = 0x55814600        # stage 4: TArena.Enter -> category mask + display units
CAVE_RADIO   = 0x558146C0        # stage 4: SetSelection -> one category at a time
CAVE_TRAIN   = 0x55814700        # stage 4: Train -> issue the arena-battle TE
CAVE_CANTRAIN= 0x55814820        # stage 4: CanTrain -> gates the Select button
CAVE_SELINFO = 0x55814860        # stage 4: GetSelectionInfo -> the description text
CAVE_GETUNIT = 0x558148C0        # stage 4b: GetUnit -> the display units
CAVE_EVDESTR = 0x55814920        # stage 4b: event-log Destroy -> free the display units
# ---- data ----
CAVE_DISPTAB = 0x55814980        # 6 dwords: the display unit resource indices
CAVE_ROSTER  = 0x558149A0        # roster table: 3 records, stride 0x40
CAVE_BUDGET  = 0x55814A60        # 3 dwords: combat-strength budget per category
CAVE_GOLD    = 0x55814A70        # 3 dwords: flat gold per category (win only)
CAVE_XP      = 0x55814A80        # 3 dwords: flat XP per surviving unit per category
CAVE_STRTAB  = 0x55814A90        # link-time VAs of the literals (STR_INFO, STR_EMPTY)
CAVE_STRINGS = 0x55814AC0        # the description literals (Delphi AnsiString form)
CAVE_TERRIMG = 0x55814C40        # stage 5: GetTerrainTypeImage -> the "empty" map sprite
CAVE_ENTEREMPTY = 0x55814CC0
CAVE_UNITCOST = 0x55814D40       # H1: the arena-only per-unit budget surcharge
CAVE_LIMIT   = 0x55814E00        # whole zone must be zero, or ours, before we write

ROSTER_STRIDE = 0x40             # dd count, then up to 15 unit indices

# Unit indices read from the INSTALLED Release/Unitres.pfs (= the Ziggurat data, not vanilla)
# via `python re_tools/pfs.py names Unitres.pfs`.
# Gold costs in the comments are Unitres.pfs tag 0x1b, i.e. the Ziggurat values, and are what the
# budget is spent in -- plus UNIT_COST_SURCHARGE per unit.
ROSTERS = [
    # weak    (budget 100)
    [237,  # Wolf                13
     236,  # Giant Frog          30
     235,  # Wild Boar           24
     222,  # Black Spider        24
     167,  # Kobold               4
     183,  # Goblin Spearman      2
     27,   # Scorpion             4   (moved down from medium)
     40,   # Dire Penguin        15
     201], # Undead Swordsman     8
    # medium  (budget 200)
    [173,  # Minotaur            40
     190,  # Werewolf            20
     184,  # Troll               80
     60,   # Giant Slug          16
     234,  # Great Eagle         32
     182,  # Goblin Wolf Rider   16
     57,   # Lizardman Club-Sword 8
     38,   # Frostling Wolf Rider 12
     23,   # Elephant            37
     41,   # Yeti                70   (also still in strong)
     189], # Goblin Butcher      28
    # strong  (budget 500)
    [240,  # Hydra              180
     113,  # Giant              105
     65,   # Basilisk           203
     187,  # Karagh             175
     24,   # Beholder           106
     41,   # Yeti                70
     170,  # Red Dragon         215
     168,  # Doom Bat            55   (moved up from medium)
     166,  # Orc Warlord         60
     149,  # Dark Elf Executioner 90
     204,  # Undead Bone Horror 104
     205], # Demon               90
]
# Budget is measured in GOLD: FillWithRandomUnits accumulates unit.vmt[0x174] = TUnit.GetObtainValue
# = unitResource[+0x4C] until it passes the budget (then the trim tail caps the stack at 8).
# Costs come from Unitres.pfs tag 0x1b.
BUDGETS = [100, 200, 500]
# Every unit costs this much EXTRA against the arena budget only (H1). Stops 2-4 gold chaff --
# Goblin 2, Scorpion 4, Halfling Swordsman 8 -- from filling a stack almost for free.
UNIT_COST_SURCHARGE = 5
GOLD    = [100, 200, 300]        # flat gold, paid ONLY on a win (result 3 or 6)
XP      = [5, 10, 15]            # flat XP added to every SURVIVING unit of the arena player
ITEM_CATEGORY = 2                # only "strong" drops an item (and only on a win)

# SelectionInfoLbl text. [0..2] = the chosen category, [3] = nothing chosen yet.
# Entry 3 has to say which box is which until stage 4b labels the checkboxes in the DFM.
# ⚠ TAOWLabel IS STRICTLY SINGLE-LINE. An earlier build joined the three offers with CRLF on the
# strength of ImageLib.ParseFontText @0x552147A0 (which does split on 0x0A/0x0D/0x20) -- but that
# function has **no callers in any code section**, it is dead code. The renderer TAOWLabel.Draw
# actually reaches is 0x55214320: a per-character glyph loop that looks each byte up in the font's
# table and silently SKIPS anything with no glyph, CR and LF included. So the three lines were drawn
# as one long line and ran off the panel edge (screenshot 2026-08-02).
# => one line at a time, selected by category. Getting all three visible at once needs three real
#    label controls (DFM clone + resource relocation, the build_herodlg_columns.py technique).
INFO_LINES = [
    "Battle the likes of wolves and boars for a reward of 100 gold and 5 experience.",
    "Battle the likes of minotaurs and trolls for a reward of 200 gold and 10 experience.",
    "Battle the likes of basilisks and giants for 300 gold, 15 experience and a magical item.",
]
CHOOSE_LINE = "Choose an opponent."
# Shown instead of opening the dialog at all when the arena is fought out (cave_enterempty).
EMPTY_MESSAGE = "The arena is empty. New challengers will arrive in time."
STRINGS = INFO_LINES + [CHOOSE_LINE, EMPTY_MESSAGE]
STR_CHOOSE, STR_EMPTY = 3, 4
# ONE representative unit per category, drawn on that category's box. Indices from Unitres.pfs.
# Exactly one per box on purpose: the painter @0x0044C24C skips any index >= GetCount, so a list of
# three means boxes 4..8 draw NOTHING AT ALL -- no alignment frame, no sprite, no cost number. Two
# units per box would need an AoW.exe cave to call the painter twice; a longer list would light up
# boxes that are not categories. Keeping it at three is what makes this feature DPL-only.
# Keep these in step with the first unit named on the matching INFO_LINES row.
DISPLAY_UNITS = [
    237,   # weak   : Wolf      ("wolves and boars")
    173,   # medium : Minotaur  ("minotaurs and trolls")
    65,    # strong : Basilisk  ("basilisks and giants")   -- was Hydra 240
]
AVAIL_MASK = 0x07                # while stocked; 0 when fought out -> a cross over every box


def off(va):
    return va - VA_BASE


# ============================================================================ assembler helpers
def _ks():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return Ks(KS_ARCH_X86, KS_MODE_32)


def asm_at(lines, va):
    """Assemble `lines` as if located at `va`; return bytes."""
    ks = _ks()
    src = "\n".join(lines)
    enc, _ = ks.asm(src, va)
    if enc is None:
        raise RuntimeError("keystone failed to assemble:\n" + src)
    return bytes(enc)


def build_pic(pre, post, cave_va):
    """
    Assemble  <pre> + `call $+5; pop ecx; sub ecx,<anchor>` + <post>  at cave_va.
    The anchor is the LINK-TIME VA of the `pop ecx`, so at runtime ECX = runtime-linktime delta and
    any absolute address A is reachable as [ecx + A].
    """
    pre_bytes = asm_at(pre, cave_va) if pre else b""
    call_va = cave_va + len(pre_bytes)
    anchor = call_va + 5                       # the `pop ecx`
    mid = ["call 0x%X" % anchor, "pop ecx", "sub ecx, 0x%X" % anchor]
    return asm_at(pre + mid + post, cave_va)


# ============================================================================ cave sources
def src_rw():
    """TArena.ReadWrite(EAX=self, EDX=stream). Register/rel32 only -- no PIC anchor needed."""
    return [
        "push ebx", "push esi", "push edi",
        "mov esi, edx",                        # stream
        "mov ebx, eax",                        # self
        "mov edx, esi",
        "mov eax, ebx",
        "call 0x%X" % FN_STRUCT_RW,            # parent first (preserves EBX/ESI/EDI)
        # rwByte(stream, &self[+0x30], id=PROP_FLAGS)   -- absent on read => target zeroed
        "lea edx, [ebx + 0x%X]" % OFF_FLAGS,
        "mov ecx, 0x%X" % PROP_FLAGS,
        "mov eax, esi",
        "mov edi, [eax]",
        "call dword ptr [edi + 0x30]",
        # rwInteger(stream, &self[+0x34], id=PROP_SEED)
        "lea edx, [ebx + 0x%X]" % OFF_SEED,
        "mov ecx, 0x%X" % PROP_SEED,
        "mov eax, esi",
        "mov edi, [eax]",
        "call dword ptr [edi + 0x2C]",
        "pop edi", "pop esi", "pop ebx",
        "ret",
    ]


def src_newday(cave_va):
    """
    TArena.NewDay(EAX=self). Once per game day per arena.
      * unseeded -> take a seed
      * empty    -> 1-in-REFILL_ONE_IN chance to restock (and reseed)
    TAoWHSMap.Random preserves EBX and ESI, so self/map live there across the calls.
    """
    pre = [
        "push ebx", "push esi",
        "mov ebx, eax",                        # self
        "call 0x%X" % FN_STRUCT_NEWDAY,        # parent (bare ret; called for form)
    ]
    post = [
        "mov esi, [ecx + 0x%X]" % PTR_MAPCTRL,
        "test esi, esi",
        "jz Lnd_done",
        "mov esi, [esi]",                      # map
        "test esi, esi",
        "jz Lnd_done",

        "test byte ptr [ebx + 0x%X], 0x%X" % (OFF_FLAGS, BIT_SEEDED),
        "jnz Lnd_chk",
        "mov eax, esi",
        "mov edx, 0x%X" % SEED_RANGE,
        "call 0x%X" % FN_MAP_RANDOM,
        "mov [ebx + 0x%X], eax" % OFF_SEED,
        "or byte ptr [ebx + 0x%X], 0x%X" % (OFF_FLAGS, BIT_SEEDED),

        "Lnd_chk:",
        "test byte ptr [ebx + 0x%X], 0x%X" % (OFF_FLAGS, BIT_EMPTY),
        "jz Lnd_done",
        "mov eax, esi",
        "mov edx, 0x%X" % REFILL_ONE_IN,
        "call 0x%X" % FN_MAP_RANDOM,
        "test eax, eax",
        "jnz Lnd_done",
        "and byte ptr [ebx + 0x%X], 0x%X" % (OFF_FLAGS, 0xFF & ~BIT_EMPTY),
        "mov eax, esi",
        "mov edx, 0x%X" % SEED_RANGE,
        "call 0x%X" % FN_MAP_RANDOM,
        "mov [ebx + 0x%X], eax" % OFF_SEED,

        "Lnd_done:",
        "pop esi", "pop ebx",
        "ret",
    ]
    return pre, post


def src_fight(cave_va):
    """
    Entered by JMP from inside TArena.ExecuteTE with EBX = the TE and [oldEBP-4] = self.
    Builds its own frame, runs a fast combat, and jumps to ExecuteTE's epilogue.

    Locals:  -4 self  -8 player  -0xC container  -0x10 militia  -0x14 map  -0x18 combat
             -0x1C delta  -0x20 result  -0x24 index-list  -0x28 category
    """
    pre = [
        "mov eax, [ebp - 4]",                  # self, read in ExecuteTE's frame FIRST
        "movzx edx, byte ptr [ebx + 0x20]",    # TE[+0x20] = player | category<<4
        "push ebp",
        "mov ebp, esp",
        "sub esp, 0x30",
        "push ebx", "push esi", "push edi",
        "mov [ebp - 4], eax",                  # self
        "mov eax, edx",
        "and eax, 0x0F",
        "mov [ebp - 8], eax",                  # player
        "shr edx, 4",
        "and edx, 3",
        "cmp edx, 3",
        "jb Lf_cat",
        "xor edx, edx",
        "Lf_cat:",
        "mov [ebp - 0x28], edx",               # category 0..2
    ]
    post = [
        "mov [ebp - 0x1C], ecx",               # load delta
        "mov byte ptr [ecx + 0x%X], 0" % FLAG_ARENAFILL,   # heal a leak from a throw last time

        # --- map ---
        "mov eax, [ecx + 0x%X]" % PTR_MAPCTRL,
        "test eax, eax",
        "jz Lf_epi",
        "mov eax, [eax]",
        "test eax, eax",
        "jz Lf_epi",
        "mov [ebp - 0x14], eax",

        # --- already fought out? ---
        "mov eax, [ebp - 4]",
        "test byte ptr [eax + 0x%X], 0x%X" % (OFF_FLAGS, BIT_EMPTY),
        "jnz Lf_epi",

        # --- the visiting army container on the arena's own hex ---
        "mov eax, [eax + 4]",                  # self[+4] = map field
        "test eax, eax",
        "jz Lf_epi",
        "mov edx, 0x%X" % FIELD_SELECTOR,
        "mov ecx, [eax]",
        "call dword ptr [ecx + 0x80]",
        "test eax, eax",
        "jz Lf_epi",
        "mov [ebp - 0xC], eax",
        "mov eax, [eax + 0x1C]",               # its TUnitList/army
        "test eax, eax",
        "jz Lf_epi",

        # --- hidden militia (TDefendersArmy) ---
        "mov ecx, [ebp - 0x1C]",
        "mov eax, [ecx + 0x%X]" % CLASSREF_DEFARMY,
        "xor ecx, ecx",
        "mov dl, 1",
        "call 0x%X" % FN_TARMY_CREATE,
        "test eax, eax",
        "jz Lf_epi",
        "mov [ebp - 0x10], eax",

        # --- roster: TUnitIndexList of this category's unit indices ---
        "mov ecx, [ebp - 0x1C]",
        "mov eax, [ecx + 0x%X]" % CLASSREF_UIL,
        "xor ecx, ecx",
        "mov dl, 1",
        "call 0x%X" % FN_UIL_CREATE,
        "test eax, eax",
        "jz Lf_epi",
        "mov [ebp - 0x24], eax",

        "mov ecx, [ebp - 0x1C]",
        "lea esi, [ecx + 0x%X]" % CAVE_ROSTER,
        "mov eax, [ebp - 0x28]",
        "shl eax, 6",                          # * ROSTER_STRIDE (0x40)
        "add esi, eax",
        "mov edi, [esi]",                      # count
        "add esi, 4",
        "Lf_add:",
        "test edi, edi",
        "jz Lf_added",
        "mov edx, [esi]",
        "mov eax, [ebp - 0x24]",
        "call 0x%X" % FN_ILIST_ADD,
        "add esi, 4",
        "dec edi",
        "jmp Lf_add",
        "Lf_added:",

        # --- seed the draw from arena[+0x34] so a stocking is stable ---
        "mov ecx, [ebp - 0x1C]",
        "mov edx, [ecx + 0x%X]" % PTR_RANDSEED,   # -> &System.RandSeed
        "mov eax, [ebp - 4]",
        "mov eax, [eax + 0x%X]" % OFF_SEED,
        "mov [edx], eax",

        # --- FillWithRandomUnits(list, militia, 4, budget, flags) : callee cleans (ret 8) ---
        "mov ecx, [ebp - 0x1C]",
        "mov byte ptr [ecx + 0x%X], 1" % FLAG_ARENAFILL,   # arena-only per-unit surcharge ON
        "lea eax, [ecx + 0x%X]" % CAVE_BUDGET,
        "mov edx, [ebp - 0x28]",
        "mov eax, [eax + edx*4]",
        "push eax",
        "push 0x%X" % FILL_FLAGS,
        "mov ecx, 0x%X" % FILL_MAXLEVEL,
        "mov edx, [ebp - 0x10]",
        "mov eax, [ebp - 0x24]",
        "call 0x%X" % FN_FILL_RND,
        "mov ecx, [ebp - 0x1C]",
        "mov byte ptr [ecx + 0x%X], 0" % FLAG_ARENAFILL,   # ...and OFF again
        "mov eax, [ebp - 0x24]",
        "call 0x%X" % FN_OBJ_FREE,             # the index list is ours; free it

        # --- trim to 8 (mirror GenerateRazeDefenders' tail) ---
        "jmp Lf_cnt",
        "Lf_trim:",
        "mov eax, [ebp - 0x10]",
        "mov edx, [eax]",
        "call dword ptr [edx + 0x54]",
        "mov edx, eax",
        "dec edx",
        "mov eax, [ebp - 0x10]",
        "call 0x%X" % FN_UNITLIST_GET,
        "mov edx, eax",
        "mov eax, [ebp - 0x10]",
        "mov ecx, [eax]",
        "call dword ptr [ecx + 0xB0]",
        "Lf_cnt:",
        "mov eax, [ebp - 0x10]",
        "mov edx, [eax]",
        "call dword ptr [edx + 0x54]",
        "cmp eax, 8",
        "jg Lf_trim",

        # --- nothing rolled -> nothing to fight (militia leaked, as the raze cave does) ---
        "mov eax, [ebp - 0x10]",
        "mov edx, [eax]",
        "call dword ptr [edx + 0x54]",
        "test eax, eax",
        "jz Lf_epi",

        # --- never build a second combat (CreateCombat raises when map[+0x120] != 0) ---
        "mov eax, [ebp - 0x14]",
        "cmp dword ptr [eax + 0x120], 0",
        "jne Lf_epi",

        "mov eax, [ebp - 0x14]",
        "call 0x%X" % FN_LOCK_GAMEOVER,
        "mov eax, [ebp - 0x14]",
        "mov edx, 0x%X" % FLAG_COMBAT_FAST,
        "call 0x%X" % FN_CREATE_COMBAT,
        "mov [ebp - 0x18], eax",
        "test eax, eax",
        "jz Lf_nocombat",                      # never ran -> do NOT mark the arena fought out

        # --- inline SetupCombat (mirror TExplorationSite.SetupCombat @0x557C1960) ---
        "mov edi, eax",
        "mov edx, [ebp - 4]",
        "mov [edi + 0x30], edx",               # context
        "mov dword ptr [edi + 0x2C], 0",       # NO callback (stage 3 fills this in)

        "mov ebx, [ebp - 4]",                  # ebx = arena (site coords)
        "mov esi, [ebp - 0xC]",                # esi = visitor container
        # stack args, right-to-left: visitor x/y/l
        "mov eax, esi", "mov edx, [eax]", "call dword ptr [edx + 0x74]", "movsx eax, al", "push eax",
        "mov eax, esi", "mov edx, [eax]", "call dword ptr [edx + 0x78]", "movsx eax, al", "push eax",
        "mov eax, esi", "mov edx, [eax]", "call dword ptr [edx + 0x7C]", "movsx eax, al", "push eax",
        # defender player/team off the militia
        "mov eax, [ebp - 0x10]", "mov al, byte ptr [eax + 0x12]", "push eax",
        "mov eax, [ebp - 0x10]", "mov al, byte ptr [eax + 0x16]", "push eax",
        # site x/y/l
        "mov eax, ebx", "mov edx, [eax]", "call dword ptr [edx + 0x74]", "movsx eax, al", "push eax",
        "mov eax, ebx", "mov edx, [eax]", "call dword ptr [edx + 0x78]", "movsx eax, al", "push eax",
        "mov eax, ebx", "mov edx, [eax]", "call dword ptr [edx + 0x7C]", "movsx eax, al", "push eax",
        "push 1",                              # isFast
        "mov eax, [esi + 0x1C]",
        "mov cl, byte ptr [eax + 0x16]",       # atkTeam
        "mov dl, byte ptr [eax + 0x12]",       # atkPlayer
        "mov eax, [ebp - 0x18]",
        "mov edi, [eax]",
        "call dword ptr [edi + 0x60]",         # TCombat.Setup (ret 0x24)

        # --- AddArmy(visitor, side 0, site l,y,x) ---
        "mov ebx, [ebp - 4]",
        "mov eax, ebx", "mov edx, [eax]", "call dword ptr [edx + 0x74]", "movsx eax, al", "push eax",
        "mov eax, ebx", "mov edx, [eax]", "call dword ptr [edx + 0x78]", "movsx eax, al", "push eax",
        "mov eax, ebx", "mov edx, [eax]", "call dword ptr [edx + 0x7C]", "movsx eax, al", "push eax",
        "xor ecx, ecx",
        "mov esi, [ebp - 0xC]",
        "mov edx, [esi + 0x1C]",
        "mov eax, [ebp - 0x18]",
        "call 0x%X" % FN_ADD_ARMY,             # ret 0xC -> EAX = the visitor TCombatParty
        # wall-less fight: clear the party's behind-wall flag (the only input to Initialize's
        # wall branch) so no TCombatWall is built. Same as the raze cave.
        "test eax, eax",
        "jz Lf_addex",
        "mov byte ptr [eax + 0x18], 0",
        "Lf_addex:",

        # --- AddArmyEx(militia, side 1, partyPos 1, -1,-1,-1) : joins with NO map field ---
        "push -1", "push -1", "push -1", "push 1",
        "mov cl, 1",
        "mov edx, [ebp - 0x10]",
        "mov eax, [ebp - 0x18]",
        "call 0x%X" % FN_ADD_ARMY_EX,          # ret 0x10
        "mov eax, [ebp - 0x18]",
        "mov byte ptr [eax + 0x40], 1",

        # --- run the fast lifecycle synchronously ---
        "mov eax, [ebp - 0x18]", "call 0x%X" % FN_LOCK_EXEC,
        "mov eax, [ebp - 0x18]", "mov edx, [eax]", "call dword ptr [edx + 0x68]",   # Initialize
        "mov eax, [ebp - 0x18]", "mov edx, [eax]", "call dword ptr [edx + 0x70]",   # Activate
        "mov eax, [ebp - 0x18]", "mov edx, [eax]", "call dword ptr [edx + 0x64]",   # Execute
        "mov eax, [ebp - 0x18]", "mov edx, [eax]", "call dword ptr [edx + 0x74]",   # Deactivate
        "mov eax, [ebp - 0x18]", "mov edx, [eax]", "call dword ptr [edx + 0x6C]",   # Finalize
        "mov eax, [ebp - 0x18]", "call 0x%X" % FN_UNLOCK_EXEC,

        # --- latch the result while combatData is still alive ---
        "mov eax, [ebp - 0x18]",
        "movzx eax, byte ptr [eax + 0x14]",
        "mov [ebp - 0x20], eax",

        # ============================ STAGE 3 REWARDS ============================
        # Done INLINE, not from a completion callback: the fast path is synchronous, and this point
        # (after UnlockExecuted, before DestroyCombat) is exactly where vanilla's CombatExecuted ->
        # ExecuteSearchDone fires, so combatData is alive and the ordering matches the engine's own.
        # EBX/ESI/EDI were saved at cave entry and are restored at Lf_epi, so all three are scratch.

        # --- (a) flat XP to every SURVIVING unit of the arena player, any outcome ---
        # ⚠ Award from the STRATEGIC side, NOT by walking combat[+0x0C]. By the time we run (after
        # slot 0x6C), TCombatUnit.Finalize @0x55724D44 has already DESTROYED the player's combat
        # objects: for a party that HAS a map field it calls TAbstractUnit.Place to put the unit
        # back on the map and then `(*vmt-4)(self,1)` -- the Delphi destructor (vmtDestroy = -4).
        # Only the off-map militia party is spared (its party[+0x0C] == -1 from AddArmyEx's
        # -1,-1,-1), which is exactly WHY vanilla's TExplorationSite.CombatExecuted only ever
        # touches GetPlayer()==0 objects: those are the only ones still alive. Walking the combat
        # data here found nothing and silently awarded no XP (observed 2026-07-31).
        # Re-fetch the container from the field rather than trusting [ebp-0xC]: Finalize has just
        # re-placed the survivors, and dead units are already gone from the list.
        "mov eax, [ebp - 4]",
        "mov eax, [eax + 4]",                  # the arena's map field
        "test eax, eax",
        "jz Lr_gold",
        "mov edx, 0x%X" % FIELD_SELECTOR,
        "mov ecx, [eax]",
        "call dword ptr [ecx + 0x80]",
        "test eax, eax",
        "jz Lr_gold",
        "mov eax, [eax + 0x1C]",               # its TUnitList
        "test eax, eax",
        "jz Lr_gold",
        "movzx edx, byte ptr [eax + 0x12]",    # owner of whatever now stands on the hex
        "cmp edx, [ebp - 8]",
        "jne Lr_gold",
        "mov [ebp - 0x2C], eax",
        "mov edx, [eax]",
        "call dword ptr [edx + 0x54]",         # GetCount
        "mov edi, eax",
        "xor esi, esi",
        "Lr_xploop:",
        "cmp esi, edi",
        "jge Lr_gold",
        "mov edx, esi",
        "mov eax, [ebp - 0x2C]",
        "call 0x%X" % FN_UNITLIST_GET,
        "test eax, eax",
        "jz Lr_xpnext",
        "mov ebx, eax",
        "mov edx, [eax]",
        "call dword ptr [edx + 0x15C]",        # TAbstractUnit.GetExperience (TUnit and THero)
        "mov ecx, [ebp - 0x1C]",
        "lea edx, [ecx + 0x%X]" % CAVE_XP,
        "mov ecx, [ebp - 0x28]",
        "add eax, [edx + ecx*4]",
        "mov edx, eax",
        "mov eax, ebx",
        "mov ecx, [eax]",
        "call dword ptr [ecx + 0x160]",        # SetExperience -> rank-up / UpdateDefaultAbilities
        "Lr_xpnext:",
        "inc esi",
        "jmp Lr_xploop",

        # --- (b) flat gold, WIN ONLY (result 3 = wipe, 6 = walkover) ---
        "Lr_gold:",
        "cmp dword ptr [ebp - 0x20], 3",
        "je Lr_gold_do",
        "cmp dword ptr [ebp - 0x20], 6",
        "jne Lr_done",
        "Lr_gold_do:",
        "mov eax, [ebp - 0x14]",
        "mov eax, [eax + 0x140]",
        "movsx edx, byte ptr [ebp - 8]",
        "call 0x%X" % FN_GET_PLAYERS,
        "test eax, eax",
        "jz Lr_item",
        "mov ebx, eax",
        "mov ecx, [ebp - 0x1C]",
        "lea edx, [ecx + 0x%X]" % CAVE_GOLD,
        "mov ecx, [ebp - 0x28]",
        "mov edx, [edx + ecx*4]",
        "add edx, [ebx + 0xC4]",               # SetGems takes an ABSOLUTE value
        "mov eax, ebx",
        "call 0x%X" % FN_SET_GEMS,

        # --- (c) random item, "strong" category only, on a win ---
        "Lr_item:",
        "cmp dword ptr [ebp - 0x28], 0x%X" % ITEM_CATEGORY,
        "jne Lr_done",
        # Seed from the map RNG first, exactly as TItemExplorationSite.Generate does, or peers
        # diverge: GenerateItem draws through the global System.RandSeed.
        "mov eax, [ebp - 0x14]",
        "mov edx, 0x%X" % SEED_RANGE,
        "call 0x%X" % FN_MAP_RANDOM,
        "mov ecx, [ebp - 0x1C]",
        "mov edx, [ecx + 0x%X]" % PTR_RANDSEED,
        "mov [edx], eax",
        # GenerateItem picks an EXISTING unplaced TItem out of TItemControl's pool (weighted) and
        # returns it, or 0 if the pool is exhausted -- it does not construct one, so there is no
        # ownership to fix up and PlaceOnMap alone completes the award.
        # ⚠ NOT `push 0xFFFF` -- keystone mis-assembles that as `6A FF` = push imm8 -1
        # (= 0xFFFFFFFF), which as a signed value cap would reject every item and silently award
        # nothing. Vanilla @0x557C2991 emits `68 FF FF 00 00`. Go through EAX, which is dead here
        # (reloaded with the item control three instructions below). Asserted after assembly.
        "mov eax, 0xFFFF",
        "push eax",
        "mov ecx, [ebp - 0x1C]",
        "mov edx, [ecx + 0x%X]" % PTR_ITALL,
        "mov dl, byte ptr [edx]",              # itAll type bitmask (as vanilla: DL only)
        "mov eax, [ebp - 0x14]",
        "mov eax, [eax + 0xF4]",               # the item control
        "xor ecx, ecx",
        "call 0x%X" % FN_GENERATE_ITEM,        # ret 4
        "test eax, eax",
        "jz Lr_done",
        "mov edi, eax",                        # the item
        "mov ebx, [ebp - 4]",                  # arena, for its x/y/l slots
        "mov eax, ebx", "mov edx, [eax]", "call dword ptr [edx + 0x78]", "push eax",   # y
        "mov eax, ebx", "mov edx, [eax]", "call dword ptr [edx + 0x7C]", "push eax",   # l
        "mov eax, ebx", "mov edx, [eax]", "call dword ptr [edx + 0x74]", "mov ecx, eax",  # x
        "mov edx, [ebp - 0x14]",
        "mov eax, edi",
        "call 0x%X" % FN_PLACE_ON_MAP,
        "Lr_done:",
        # ========================== end STAGE 3 REWARDS ==========================

        # --- file a replayable combat-log entry (no managed string locals) ---
        "mov ecx, [ebp - 0x1C]",
        "mov eax, [ecx + 0x%X]" % VMTREF_EVENTLOG,
        "xor ecx, ecx",
        "mov dl, 1",
        "call 0x%X" % FN_EVENTLOG_CREATE,
        "test eax, eax",
        "jz Lf_teardown",
        "mov esi, eax",
        "mov edx, [ebp - 0x18]",
        "mov edx, [edx + 0x18]",               # combat logbook
        "mov eax, esi",
        "call 0x%X" % FN_SET_COMBAT_LOG,
        "mov eax, [ebp - 0x14]",
        "mov eax, [eax + 0x140]",
        "movsx edx, byte ptr [ebp - 8]",
        "call 0x%X" % FN_GET_PLAYERS,
        "test eax, eax",
        "jz Lf_logrelease",
        "mov edi, eax",
        "mov edx, esi",
        "mov eax, [edi + 0xD8]",
        "call 0x%X" % FN_ADD_EVENT,
        # show it only to the local human whose battle it is
        "mov eax, [ebp - 0x14]",
        "mov al, byte ptr [eax + 0xA5]",
        "cmp al, byte ptr [ebp - 8]",
        "jne Lf_logrelease",
        "cmp byte ptr [edi + 0xA7], 0",
        "jne Lf_logrelease",
        "push 0", "push 0",
        "xor ecx, ecx", "xor edx, edx",
        "mov eax, esi",
        "mov ebx, [eax]",
        "call dword ptr [ebx + 0x70]",         # Show (ret 8)
        "Lf_logrelease:",
        "mov eax, esi",
        "mov edx, [eax]",
        "call dword ptr [edx + 0x2C]",         # release our reference

        "Lf_teardown:",
        "mov eax, [ebp - 0x14]",
        "call 0x%X" % FN_DESTROY_COMBAT,
        "mov eax, [ebp - 0x14]",
        "call 0x%X" % FN_UNLOCK_GAMEOVER,
        # --- the arena is fought out (stage 2: win or lose) ---
        "mov eax, [ebp - 4]",
        "or byte ptr [eax + 0x%X], 0x%X" % (OFF_FLAGS, BIT_EMPTY),
        "jmp Lf_epi",

        # CreateCombat handed back nothing: release the game-over lock and leave the arena stocked.
        "Lf_nocombat:",
        "mov eax, [ebp - 0x14]",
        "call 0x%X" % FN_UNLOCK_GAMEOVER,

        "Lf_epi:",
        "pop edi", "pop esi", "pop ebx",
        "mov esp, ebp",
        "pop ebp",
        "jmp 0x%X" % VA_EXECTE_EPI,
    ]
    return pre, post


# ============================================================================ stage 4 caves
def src_avail(cave_va):
    """
    Hooked over the 5 bytes at VA_AVAIL inside TArena.Enter, just before the event log is Shown.
    ESI = the TEnterArenaEventLog. Two jobs:

    1. +0x1D (the "selectable" mask) -- vanilla filled it with one bit per TRAINABLE UNIT, so a
       one-unit stack could only ever tick box 1. Now a constant, and 0 when the arena is fought
       out, which crosses out every box and (via cave_cantrain) greys Select for free.

    2. Replace ev[+0x20] with DISPLAY UNITS. The box painter @0x0044C24C draws whatever
       GetUnit(index) returns -- alignment frame via vmt[0xFC] GetAlignment, then the sprite via
       vmt[0x1A4] TUnit.ShowEx -- so it needs a real TUnit. Vanilla filled the list with the
       VISITING ARMY's unit ids, which is why every box showed one of your own units. We drop those
       and store one freshly-built TUnit per category (from DISPLAY_UNITS) as a raw pointer; the
       GetUnit hook returns them directly instead of going through FindUnit.
       The units are never Activated, so they get no id and never touch TUnitControl or the map.
       cave_evdestroy frees them with the event log.
    """
    pre = ["mov eax, [esi + 0x18]",               # the arena
           "test eax, eax",
           "jz Lav_mask_done",
           "test byte ptr [eax + 0x%X], 0x%X" % (OFF_FLAGS, BIT_EMPTY),
           "mov al, 0x%X" % AVAIL_MASK,           # does not touch flags
           "jz Lav_set",
           "xor al, al",
           "Lav_set:",
           "mov byte ptr [esi + 0x1D], al",
           "Lav_mask_done:"]
    post = [
        "push ebx", "push edi",
        "push ecx",                               # [esp] = load delta (TUnit.Create clobbers ECX)
        "mov ebx, [esi + 0x20]",                  # the TIntegerList
        "test ebx, ebx",
        "jz Lav_units_done",
        "mov dword ptr [ebx + 8], 0",             # drop the army unit ids (count := 0)
        "xor edi, edi",
        "Lav_mk:",
        "cmp edi, %d" % len(DISPLAY_UNITS),
        "jge Lav_units_done",
        # unit = TUnit.Create
        "mov ecx, [esp]",
        "mov eax, [ecx + 0x%X]" % CLASSREF_TUNIT,
        "xor ecx, ecx",
        "mov dl, 1",
        "call 0x%X" % FN_AUNIT_CREATE,
        "test eax, eax",
        "jz Lav_units_done",
        "push eax",                               # [esp]=unit  [esp+4]=delta
        # resource = GetUnitResource(AoWHSSet[+0x5C], DISPTAB[i])
        "mov ecx, [esp + 4]",
        "lea edx, [ecx + 0x%X]" % CAVE_DISPTAB,
        "mov edx, [edx + edi*4]",
        "mov eax, [ecx + 0x%X]" % PTR_AOWHSSET,
        "mov eax, [eax + 0x5C]",
        "call 0x%X" % FN_GET_UNITRES,
        "test eax, eax",
        "jz Lav_skip",
        "mov edx, eax",
        "mov eax, [esp]",
        "call 0x%X" % FN_SET_UNITRES,
        "mov edx, [esp]",
        "mov eax, ebx",
        "call 0x%X" % FN_ILIST_ADD,               # store the TUnit POINTER as an integer
        "add esp, 4",
        "inc edi",
        "jmp Lav_mk",
        "Lav_skip:",
        "mov eax, [esp]",
        "call 0x%X" % FN_OBJ_FREE,
        "add esp, 4",
        "inc edi",
        "jmp Lav_mk",
        "Lav_units_done:",
        "pop ecx", "pop edi", "pop ebx",
        "push 0", "push 0", "mov cl, 1",          # displaced
        "jmp 0x%X" % VA_AVAIL_RESUME]
    return pre, post


def src_getunit(cave_va):
    """
    TEnterArenaEventLog.GetUnit(EAX=self, EDX=index) -> TUnit.
    ev[+0x20] now holds raw TUnit pointers (see src_avail), not unit ids, so return the entry
    directly instead of resolving it through TUnitControl.FindUnit.
    """
    return ["push ebx",
            "mov ebx, [eax + 0x20]",
            "test ebx, ebx",
            "jz Lgu_nil",
            "test edx, edx",
            "jl Lgu_nil",
            "cmp edx, [ebx + 8]",
            "jge Lgu_nil",
            "mov eax, ebx",
            "call 0x%X" % FN_ILIST_GET,
            "pop ebx",
            "ret",
            "Lgu_nil:",
            "xor eax, eax",
            "pop ebx",
            "ret"]


def src_evdestroy(cave_va):
    """
    TEnterArenaEventLog.Destroy(EAX=self, DL=flags). Free the display units before the inherited
    destructor frees the list that holds their pointers. Replays the displaced prologue.
    """
    return ["push eax", "push edx",               # the incoming self / flags, restored before replay
            "push ebx", "push esi", "push edi",
            "mov esi, eax",
            "mov ebx, [esi + 0x20]",
            "test ebx, ebx",
            "jz Led_done",
            "mov edi, [ebx + 8]",
            "Led_loop:",
            "dec edi",
            "js Led_done",
            "mov eax, ebx",
            "mov edx, edi",
            "call 0x%X" % FN_ILIST_GET,
            "test eax, eax",
            "jz Led_loop",
            "call 0x%X" % FN_OBJ_FREE,
            "jmp Led_loop",
            "Led_done:",
            "pop edi", "pop esi", "pop ebx",
            "pop edx", "pop eax",
            # replay all four displaced instructions, then rejoin at `mov eax,[esi+0x20]`
            "push ebx", "push esi",
            "mov ebx, edx",
            "mov esi, eax",
            "jmp 0x%X" % VA_EVDESTROY_RESUME]


def src_radio():
    """
    TEnterArenaEventLog.SetSelection(EAX=self, DL=requested mask) -- radio, not multi-select.
    U1Change passes (old | bit) when ticking and (old & ~bit) when unticking, then re-reads all
    eight checkbox states back out of +0x1C, so making this keep a single bit gives radio behaviour
    with NO change to AoW.exe at all.
    """
    return ["push ebx", "push ecx",
            "movzx ebx, dl",
            "and bl, byte ptr [eax + 0x1D]",      # only offered categories
            "movzx ecx, byte ptr [eax + 0x1C]",   # what was selected before
            "mov edx, ebx",
            "not ecx",
            "and edx, ecx",                       # bits that just turned ON
            "jz Lrd_keep",                        # none -> an untick; take the mask as given
            "mov ecx, edx",
            "neg edx",
            "and edx, ecx",                       # x & -x = lowest set bit
            "mov byte ptr [eax + 0x1C], dl",
            "pop ecx", "pop ebx", "ret",
            "Lrd_keep:",
            "mov byte ptr [eax + 0x1C], bl",
            "pop ecx", "pop ebx", "ret"]


def src_cantrain():
    """
    TEnterArenaEventLog.CanTrain(EAX=self, EDX=&err) -> AL. Called from U1Change to enable/disable
    SelectBtn. True iff the arena is stocked and a category is chosen.
    """
    return ["mov ecx, [eax + 0x18]",
            "test ecx, ecx",
            "jz Lct_no",
            "test byte ptr [ecx + 0x%X], 0x%X" % (OFF_FLAGS, BIT_EMPTY),
            "jnz Lct_no",
            "cmp byte ptr [eax + 0x1C], 0",
            "je Lct_no",
            "mov al, 1",
            "ret",
            "Lct_no:",
            "xor eax, eax",
            "ret"]


def src_selinfo(cave_va):
    """
    TEnterArenaEventLog.GetSelectionInfo(EAX=self, EDX=&result) -- the text beside the boxes.
    Always the SAME three-line block, whatever is selected: all three offers stay readable and the
    ticked box plus its sprite are the feedback. Assigns a literal AnsiString (refcount -1, so
    @LStrAsg just stores the pointer and never tries to free it); the table holds LINK-TIME VAs,
    rebased with the load delta.
    """
    pre = []
    post = ["push ebx", "push esi",
            "mov esi, edx",                        # &result
            "movzx ebx, byte ptr [eax + 0x1C]",    # the selection bitmask
            "xor eax, eax",
            "test bl, 1", "jnz Lsi_got",
            "inc eax",
            "test bl, 2", "jnz Lsi_got",
            "inc eax",
            "test bl, 4", "jnz Lsi_got",
            "mov eax, %d" % STR_CHOOSE,            # nothing ticked yet
            "Lsi_got:",
            "lea edx, [ecx + 0x%X]" % CAVE_STRTAB,
            "mov edx, [edx + eax*4]",
            "add edx, ecx",                        # link-time VA -> runtime
            "mov eax, esi",
            "call 0x%X" % FN_LSTRASG,
            "pop esi", "pop ebx", "ret"]
    return pre, post


def src_train(cave_va):
    """
    TEnterArenaEventLog.Train(EAX=self, EDX=&err) -> AL. Issues the arena-battle turn event.
    Mirrors TArena.TrainUnits' token dance (GetBusy -> CreateTE -> SetupTE -> TokenControl) but
    packs the CATEGORY into the TE alongside the player -- TE[+0x20] = player | category<<4, the
    same nibble-packing the raze rework uses -- and skips the unit-id list entirely, which
    ExecuteTE's arena branch no longer reads.
    Locals: -4 self  -8 category  -0xC player  -0x10 map  -0x14 TE  -0x18 delta
    """
    pre = ["push ebp", "mov ebp, esp", "sub esp, 0x20",
           "push ebx", "push esi", "push edi",
           "mov [ebp - 4], eax"]
    post = ["mov [ebp - 0x18], ecx",
            "mov esi, [ebp - 4]",
            # category = index of the single selected bit
            "movzx ebx, byte ptr [esi + 0x1C]",
            "test bl, bl",
            "jz Ltr_fail",
            "xor eax, eax",
            "test bl, 1", "jnz Ltr_cat",
            "inc eax",
            "test bl, 2", "jnz Ltr_cat",
            "inc eax",
            "Ltr_cat:",
            "cmp eax, 2", "ja Ltr_fail",
            "mov [ebp - 8], eax",
            # the arena must still be stocked
            "mov eax, [esi + 0x18]",
            "test eax, eax",
            "jz Ltr_fail",
            "test byte ptr [eax + 0x%X], 0x%X" % (OFF_FLAGS, BIT_EMPTY),
            "jnz Ltr_fail",
            # map + seated player
            "mov ecx, [ebp - 0x18]",
            "mov eax, [ecx + 0x%X]" % PTR_MAPCTRL,
            "test eax, eax", "jz Ltr_fail",
            "mov eax, [eax]",
            "test eax, eax", "jz Ltr_fail",
            "mov [ebp - 0x10], eax",
            "movzx edx, byte ptr [eax + 0xA5]",
            "mov [ebp - 0xC], edx",
            # never mint a token while the player is mid-pass
            "mov eax, [eax + 0x140]",
            "mov edx, [ebp - 0xC]",
            "call 0x%X" % FN_GET_PLAYERS,
            "test eax, eax", "jz Ltr_fail",
            "call 0x%X" % FN_GET_BUSY,
            "test al, al", "jnz Ltr_fail",
            # CreateTE / SetupTE  (VMT slots 0x160 / 0x164 on the arena)
            "mov eax, [esi + 0x18]",
            "mov edx, [eax]",
            "call dword ptr [edx + 0x160]",
            "test eax, eax", "jz Ltr_fail",
            "mov [ebp - 0x14], eax",
            "mov edx, eax",
            "mov eax, [esi + 0x18]",
            "mov ecx, [eax]",
            "call dword ptr [ecx + 0x164]",
            # TE[+0x20] = player | category<<4 ; TE[+0x18] = 1 (the arena command)
            "mov eax, [ebp - 0x14]",
            "mov edx, [ebp - 8]",
            "shl edx, 4",
            "or edx, [ebp - 0xC]",
            "mov [eax + 0x20], edx",
            "mov dword ptr [eax + 0x18], 1",
            # dispatch through the token manager so every peer executes it
            "mov eax, [ebp - 0x10]",
            "mov eax, [eax + 0x%X]" % MAP_TOKENMGR_OFF,
            "test eax, eax", "jz Ltr_release",
            "mov edx, [ebp - 0xC]",
            "call 0x%X" % FN_GET_TOKEN_CTRL,
            "test eax, eax", "jz Ltr_release",
            "mov edx, [ebp - 0x14]",
            "mov ecx, [eax]",
            "call dword ptr [ecx + 0x10]",
            "Ltr_release:",
            "mov eax, [ebp - 0x14]",
            "mov edx, [eax]",
            "call dword ptr [edx + 0x2C]",
            "mov al, 1",
            "jmp Ltr_out",
            "Ltr_fail:",
            "xor eax, eax",
            "Ltr_out:",
            "pop edi", "pop esi", "pop ebx",
            "mov esp, ebp", "pop ebp", "ret"]
    return pre, post


def src_terrimg(cave_va):
    """
    TArena.GetTerrainTypeImage(EAX=self, EDX=imageIdx) -> EAX, VMT slot +0x12C.

    Mirrors how exploration sites change appearance once explored -- there is no separate
    "animation state" in this engine, a site simply asks for a DIFFERENT IMAGE SEQUENCE:

        ExploreS.TExplorationSite.GetTerrainTypeImage @0x557C1848
            if (GetExplored() && map[+0x174] != 0
                && TImageSequenceList.GetImageSequence(resource[+0x24], idx + 100) != 0)
                    idx += 100;
            return idx;

    So the convention is **base index + 100 = the alternate look**, with a graceful fallback to the
    normal index when the resource has no such sequence. We key on EMPTY instead of explored.
    Because the lookup is guarded, this is a no-op until the Arena resource actually gains a
    sequence at index+100 -- that part is ART, added to the resource, not code.

    Unlike the exploration site we fall through to TStructure.GetTerrainTypeImage when there is no
    alternate, so a razed or under-construction arena keeps its proper rubble/scaffold imagery.
    """
    # Everything lives after the PIC anchor: build_pic assembles `pre` on its own to locate the
    # anchor, so `pre` must not reference a label defined in `post`.
    pre = []
    post = ["test byte ptr [eax + 0x%X], 0x%X" % (OFF_FLAGS, BIT_EMPTY),
            "jz Lti_base",
            "push ebx", "push esi",
            "mov ebx, eax",
            "mov esi, edx",
            "mov eax, [ecx + 0x%X]" % PTR_MAPCTRL,
            "test eax, eax", "jz Lti_pop",
            "mov eax, [eax]",
            "test eax, eax", "jz Lti_pop",
            "cmp dword ptr [eax + 0x174], 0",      # in-game only, as the exploration site does
            "je Lti_pop",
            "mov eax, [ebx + 8]",                  # the structure resource
            "test eax, eax", "jz Lti_pop",
            "mov eax, [eax + 0x24]",               # its TImageSequenceList
            "test eax, eax", "jz Lti_pop",
            "lea edx, [esi + 100]",
            "call 0x%X" % FN_GET_IMAGESEQ,
            "test eax, eax",
            "jz Lti_pop",
            "lea eax, [esi + 100]",                # the alternate exists -> use it
            "pop esi", "pop ebx",
            "ret",
            "Lti_pop:",
            "mov eax, ebx",
            "mov edx, esi",
            "pop esi", "pop ebx",
            "Lti_base:",
            "jmp 0x%X" % FN_STRUCT_TERRIMG]
    return pre, post


def src_enterempty(cave_va):
    """
    Hooked over the 6-byte `je` that follows CanEnter in TArena.Enter. A fought-out arena should
    say so rather than opening an empty-looking battle dialog. [esp] = self (Enter stashed it with
    `mov [esp],eax` after its five pushes, and we arrive by jmp so ESP is untouched).
    The message goes through the map's own notification slot, the one ExecuteTE uses for
    "%d units trained": map.vmt[0x110](EAX=map, EDX=string).
    """
    pre = []
    post = ["test al, al",
            "jz Lee_false",
            "mov eax, [esp]",
            "test byte ptr [eax + 0x%X], 0x%X" % (OFF_FLAGS, BIT_EMPTY),
            "jz Lee_normal",
            "lea edx, [ecx + 0x%X]" % CAVE_STRTAB,
            "mov edx, [edx + %d]" % (STR_EMPTY * 4),
            "add edx, ecx",                        # link-time VA -> runtime
            "mov eax, [ecx + 0x%X]" % PTR_MAPCTRL,
            "test eax, eax", "jz Lee_done",
            "mov eax, [eax]",
            "test eax, eax", "jz Lee_done",
            "mov ecx, [eax]",
            "call dword ptr [ecx + 0x110]",
            "Lee_done:",
            "jmp 0x%X" % VA_ENTER_TRUE,
            "Lee_normal:",
            "jmp 0x%X" % VA_ENTER_RESUME,
            "Lee_false:",
            "jmp 0x%X" % VA_ENTER_FALSE]
    return pre, post


def src_unitcost(cave_va):
    """
    Hooked over the accepted-unit cost call in FillWithRandomUnits. Replays the virtual call, then
    adds UNIT_COST_SURCHARGE **only while cave_fight has the flag raised**, so every other caller
    of this shared function keeps vanilla arithmetic.
    """
    pre = ["call dword ptr [edx + 0x174]"]          # replay: EDX (the VMT) is live on entry
    post = ["cmp byte ptr [ecx + 0x%X], 0" % FLAG_ARENAFILL,
            "jz Luc_done",
            "add eax, %d" % UNIT_COST_SURCHARGE,
            "Luc_done:",
            "jmp 0x%X" % VA_UNITCOST_RES]
    return pre, post


def build_strings():
    """Delphi AnsiString literals: [refcount=-1][len][chars][NUL]; pointers aim at the chars."""
    blob = b""
    ptrs = []
    for s in STRINGS:
        while len(blob) % 4:
            blob += b"\0"
        raw = s.encode("latin-1")
        ptrs.append(CAVE_STRINGS + len(blob) + 8)
        blob += struct.pack("<iI", -1, len(raw)) + raw + b"\0"
    return blob, ptrs


def build_roster_blob():
    """3 records of ROSTER_STRIDE bytes: dd count, dd idx...  plus the budget table."""
    blob = b""
    for r in ROSTERS:
        if len(r) > (ROSTER_STRIDE // 4) - 1:
            raise SystemExit("roster too long for stride")
        rec = struct.pack("<I", len(r)) + b"".join(struct.pack("<I", u) for u in r)
        blob += rec + b"\0" * (ROSTER_STRIDE - len(rec))
    return blob


def build_all():
    """Return {va: bytes} for every cave/data block."""
    out = {}
    out[CAVE_RW] = asm_at(src_rw(), CAVE_RW)
    pre, post = src_newday(CAVE_NEWDAY)
    out[CAVE_NEWDAY] = build_pic(pre, post, CAVE_NEWDAY)
    pre, post = src_fight(CAVE_FIGHT)
    out[CAVE_FIGHT] = build_pic(pre, post, CAVE_FIGHT)
    pre, post = src_avail(CAVE_AVAIL)
    out[CAVE_AVAIL] = build_pic(pre, post, CAVE_AVAIL)
    out[CAVE_GETUNIT] = asm_at(src_getunit(CAVE_GETUNIT), CAVE_GETUNIT)
    out[CAVE_EVDESTR] = asm_at(src_evdestroy(CAVE_EVDESTR), CAVE_EVDESTR)
    out[CAVE_DISPTAB] = b"".join(struct.pack("<I", u) for u in DISPLAY_UNITS)
    out[CAVE_RADIO] = asm_at(src_radio(), CAVE_RADIO)
    out[CAVE_CANTRAIN] = asm_at(src_cantrain(), CAVE_CANTRAIN)
    pre, post = src_selinfo(CAVE_SELINFO)
    out[CAVE_SELINFO] = build_pic(pre, post, CAVE_SELINFO)
    pre, post = src_train(CAVE_TRAIN)
    out[CAVE_TRAIN] = build_pic(pre, post, CAVE_TRAIN)
    pre, post = src_terrimg(CAVE_TERRIMG)
    out[CAVE_TERRIMG] = build_pic(pre, post, CAVE_TERRIMG)
    pre, post = src_enterempty(CAVE_ENTEREMPTY)
    out[CAVE_ENTEREMPTY] = build_pic(pre, post, CAVE_ENTEREMPTY)
    pre, post = src_unitcost(CAVE_UNITCOST)
    out[CAVE_UNITCOST] = build_pic(pre, post, CAVE_UNITCOST)
    strblob, strptrs = build_strings()
    out[CAVE_STRINGS] = strblob
    out[CAVE_STRTAB] = b"".join(struct.pack("<I", p) for p in strptrs)
    out[CAVE_ROSTER] = build_roster_blob()
    out[CAVE_BUDGET] = b"".join(struct.pack("<I", b) for b in BUDGETS)
    out[CAVE_GOLD] = b"".join(struct.pack("<I", g) for g in GOLD)
    out[CAVE_XP] = b"".join(struct.pack("<I", x) for x in XP)

    # Guard the keystone `push 0xFFFF` -> `6A FF` truncation (see the comment at the site).
    # `B8 FF FF 00 00 50` = mov eax,0xFFFF ; push eax -- the GenerateItem value cap.
    if out[CAVE_FIGHT].count(bytes.fromhex("b8ffff000050")) != 1:
        raise SystemExit("ABORT: the GenerateItem value cap (mov eax,0xFFFF; push eax) is missing "
                         "or duplicated in cave_fight -- keystone may have re-encoded it.")
    return out


# ============================================================================ file plumbing
def read_dll():
    with open(DLL, "rb") as f:
        return bytearray(f.read())


def rel32(src, dst):
    return struct.pack("<i", dst - (src + 5))


def byte_patches(caves):
    """[(va, orig_bytes, new_bytes, label)] for the five discrete sites."""
    return [
        (VA_INSTSIZE, struct.pack("<I", ORIG_INSTSIZE), struct.pack("<I", NEW_INSTSIZE),
         "D1 TArena instance size 0x30 -> 0x38"),
        (VA_VMT_RW, struct.pack("<I", ORIG_RW), struct.pack("<I", CAVE_RW),
         "D2 VMT+0x018 ReadWrite -> cave_rw"),
        (VA_VMT_NEWDAY, struct.pack("<I", ORIG_NEWDAY), struct.pack("<I", CAVE_NEWDAY),
         "D3 VMT+0x174 NewDay -> cave_newday"),
        (VA_TRAINCOST, ORIG_TRAINCOST, NEW_TRAINCOST,
         "D4 UnitTrainCost -> return 0 (every unit selectable)"),
        (VA_EXECTE, ORIG_EXECTE, b"\xE9" + rel32(VA_EXECTE, CAVE_FIGHT),
         "D5 ExecuteTE train branch -> cave_fight"),
        (VA_AVAIL, ORIG_AVAIL, b"\xE9" + rel32(VA_AVAIL, CAVE_AVAIL),
         "E1 Enter: selectable mask -> 3 categories"),
        (VA_SETSEL, ORIG_SETSEL, b"\xE9" + rel32(VA_SETSEL, CAVE_RADIO),
         "E2 SetSelection -> radio (one category)"),
        (VA_TRAIN, ORIG_PROLOG5, b"\xE9" + rel32(VA_TRAIN, CAVE_TRAIN),
         "E3 Train -> issue the arena-battle TE"),
        (VA_CANTRAIN, ORIG_PROLOG5, b"\xE9" + rel32(VA_CANTRAIN, CAVE_CANTRAIN),
         "E4 CanTrain -> gate the Select button"),
        (VA_SELINFO, ORIG_SELINFO, b"\xE9" + rel32(VA_SELINFO, CAVE_SELINFO),
         "E5 GetSelectionInfo -> category description"),
        (VA_GETUNIT, ORIG_GETUNIT, b"\xE9" + rel32(VA_GETUNIT, CAVE_GETUNIT),
         "F1 GetUnit -> the display units"),
        (VA_EVDESTROY, ORIG_EVDESTROY, b"\xE9" + rel32(VA_EVDESTROY, CAVE_EVDESTR) + b"\x90",
         "F2 event-log Destroy -> free the display units"),
        (VA_VMT_TERRIMG, struct.pack("<I", ORIG_VMT_TERRIMG), struct.pack("<I", CAVE_TERRIMG),
         "G1 VMT+0x12C GetTerrainTypeImage -> empty-arena sprite"),
        (VA_ENTER_JE, ORIG_ENTER_JE, b"\xE9" + rel32(VA_ENTER_JE, CAVE_ENTEREMPTY) + b"\x90",
         "G2 Enter -> 'arena is empty' message when fought out"),
        (VA_UNITCOST, ORIG_UNITCOST, b"\xE9" + rel32(VA_UNITCOST, CAVE_UNITCOST) + b"\x90",
         "H1 FillWithRandomUnits -> +%dg per unit (arena only)" % UNIT_COST_SURCHARGE),
    ]


# Every hook that REJOINS the original function must resume strictly past the bytes it displaced.
# Getting this wrong makes the cave jump into the middle of its own E9 operand; the bytes there
# decode as garbage and the fault surfaces somewhere downstream with no obvious link to the hook.
# (Cost one in-game access violation, 2026-07-31 -- F2 resumed at +2 of a 5-byte patch.)
RESUMING_HOOKS = [
    ("D5 ExecuteTE", VA_EXECTE, len(ORIG_EXECTE), VA_EXECTE_EPI),
    ("E1 Enter avail", VA_AVAIL, len(ORIG_AVAIL), VA_AVAIL_RESUME),
    ("F2 event-log Destroy", VA_EVDESTROY, len(ORIG_EVDESTROY), VA_EVDESTROY_RESUME),
]
for _label, _va, _n, _resume in RESUMING_HOOKS:
    if _va <= _resume < _va + _n:
        raise SystemExit(
            "ABORT: %s resumes at 0x%08X, inside the %d displaced bytes at 0x%08X. The cave would "
            "jump into its own jump instruction." % (_label, _resume, _n, _va))


def check_zone(data, caves, state):
    """
    The zone must be one of:
      free       -- all zero, nothing installed yet
      ours       -- byte-identical to the image we are about to write (idempotent re-run)
      ours-prior -- a PREVIOUS build of this feature. Recognised by ANY of our hook sites already
                    holding its applied bytes, which no other mod can produce (the per-site loop has
                    already rejected anything that is neither stock nor ours). "Any" rather than
                    "all" on purpose: a later stage adds new sites, so an upgrade legitimately sees
                    the old sites applied and the new ones still stock.
                    This is what lets the script rewrite its own caves IN PLACE as the code grows,
                    instead of demanding a revert -- restoring a .pre-* backup would destroy every
                    feature layered on top.
    Anything else aborts.
    """
    lo, hi = CAVE_RW, CAVE_LIMIT
    cur = bytes(data[off(lo):off(hi)])
    want = bytearray(hi - lo)
    for va, blob in caves.items():
        want[va - lo:va - lo + len(blob)] = blob
    if cur == bytes(want):
        return "ours"
    if cur == bytes(len(cur)):
        return "free"
    if any(s in ("applied", "moved") for s in state):
        return "ours-prior"
    diffs = [i for i in range(len(cur)) if cur[i] != 0 and cur[i] != want[i]]
    where = ("first at 0x%08X" % (lo + diffs[0])) if diffs else "only in bytes we would zero"
    raise SystemExit(
        "ABORT: cave zone 0x%08X..0x%08X is neither free nor ours -- %d bytes differ, %s, and no "
        "hook site is installed. Another feature may own it; pick a different CAVE_* base."
        % (lo, hi, len(diffs), where))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the file (default: dry run)")
    ap.add_argument("--undo", action="store_true", help="surgically remove (no backup restore)")
    ap.add_argument("--dis", action="store_true", help="disassemble the caves for review")
    ap.add_argument("--xp", type=int, metavar="N",
                    help="override the per-category XP award with N (diagnostic: AoW1 shows no "
                         "numeric XP, so use a large value to make a medal visibly move, then "
                         "re-apply without --xp to restore %s)" % (XP,))
    args = ap.parse_args()

    if args.xp is not None:
        if not 0 <= args.xp <= 0x7FFFFFFF:
            raise SystemExit("--xp must be a non-negative 32-bit value")
        XP[:] = [args.xp] * 3
        print("*** DIAGNOSTIC BUILD: XP award forced to %d for every category ***\n" % args.xp)

    if CAVE_LIMIT > CODE_END:
        raise SystemExit("cave zone runs past the CODE section")

    caves = build_all()
    for va, blob in caves.items():
        nxt = min([v for v in list(caves) + [CAVE_LIMIT] if v > va])
        if va + len(blob) > nxt:
            raise SystemExit("cave at 0x%08X (%d B) overruns 0x%08X" % (va, len(blob), nxt))

    data = read_dll()
    patches = byte_patches(caves)

    # -------------------------------------------------- state
    def points_into_our_zone(va, cur):
        """
        Recognise a PREVIOUS build of ours whose cave has since moved. A hook site holds either an
        `E9 rel32` or a raw cave VA (VMT slot); either way, if it resolves to an address inside our
        own cave zone it can only be ours -- no other feature allocates there. Without this, simply
        relocating a cave makes every hook look like "another mod owns this site" and the only way
        forward would be a .pre-* restore, which destroys every feature layered on top.
        """
        if len(cur) >= 5 and cur[0] == 0xE9:
            target = va + 5 + struct.unpack("<i", cur[1:5])[0]
        elif len(cur) == 4:
            target = struct.unpack("<I", cur)[0]
        else:
            return False
        return CAVE_RW <= target < CAVE_LIMIT

    state = []
    for va, orig, new, label in patches:
        cur = bytes(data[off(va):off(va) + len(new)])
        if cur == new:
            state.append("applied")
        elif cur == orig:
            state.append("stock")
        elif points_into_our_zone(va, cur):
            state.append("moved")            # ours, from a build with a different cave layout
        else:
            raise SystemExit(
                "ABORT: %s @0x%08X is neither stock (%s) nor applied (%s) -- found %s. "
                "Another mod may own this site." % (label, va, orig.hex(" "), new.hex(" "), cur.hex(" ")))
    zone = check_zone(data, caves, state)

    print("=" * 78)
    print("arena stage 1+2   dll=%s" % DLL)
    print("=" * 78)
    for (va, orig, new, label), st in zip(patches, state):
        print("  [%-7s] %-52s @%08X" % (st, label, va))
    print("  [%-7s] cave zone 0x%08X..0x%08X" % (zone, CAVE_RW, CAVE_LIMIT))
    for va, blob in sorted(caves.items()):
        print("            cave @%08X  %4d B" % (va, len(blob)))
    print()

    if args.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        cs = Cs(CS_ARCH_X86, CS_MODE_32)
        for va, blob in sorted(caves.items()):
            if va in (CAVE_ROSTER, CAVE_BUDGET, CAVE_GOLD, CAVE_XP):
                print("; ---- data @%08X ----" % va)
                print("  " + blob.hex(" "))
                continue
            print("; ---- cave @%08X (%d B) ----" % (va, len(blob)))
            for i in cs.disasm(blob, va):
                print("  %08X  %-8s %s" % (i.address, i.mnemonic, i.op_str))
        print()

    # -------------------------------------------------- undo
    if args.undo:
        if all(s == "stock" for s in state) and zone == "free":
            print("nothing to undo -- already at stock.")
            return
        if not args.apply:
            print("DRY RUN (--undo). Add --apply to write.")
            return
        for va, orig, new, label in patches:
            data[off(va):off(va) + len(orig)] = orig
        data[off(CAVE_RW):off(CAVE_LIMIT)] = b"\0" * (CAVE_LIMIT - CAVE_RW)
        with open(DLL, "wb") as f:
            f.write(data)
        print("UNDONE surgically. No .pre-* backup was touched.")
        return

    # -------------------------------------------------- apply
    if all(s == "applied" for s in state) and zone == "ours":
        print("ALREADY APPLIED and byte-identical. Nothing to do.")
        return
    if not args.apply:
        print("DRY RUN. Add --apply to write (close AoW.exe / AoWCompat.exe / AoWDevEd.exe first).")
        return

    if not os.path.exists(BAK):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BAK)
        print("backup -> %s" % BAK)
    else:
        print("backup already exists (kept): %s" % BAK)

    # Zero the WHOLE zone first, so a shorter cave in this build cannot leave tail bytes of a
    # previous, longer one behind.
    data[off(CAVE_RW):off(CAVE_LIMIT)] = b"\0" * (CAVE_LIMIT - CAVE_RW)
    for va, blob in caves.items():
        data[off(va):off(va) + len(blob)] = blob
    for va, orig, new, label in patches:
        data[off(va):off(va) + len(new)] = new
    with open(DLL, "wb") as f:
        f.write(data)
    print("APPLIED (caves rewritten in place; no backup was restored)." if zone == "ours-prior"
          else "APPLIED.")


if __name__ == "__main__":
    main()
