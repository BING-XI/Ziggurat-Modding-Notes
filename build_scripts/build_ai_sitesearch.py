#!/usr/bin/env python3
r"""
AoW1 mod -- "ai_sitesearch": AI players path to, and search, exploration sites.

================================================================================
THE VANILLA GAP
================================================================================
Every exploration-site class inherits TStructure's AI entry points, and both are
no-op stubs:

    AoWE.TStructure.ExecuteAI       @0x5575E698   33 C0 C3   xor eax,eax; ret
    AoWE.TStructure.UpdateAITarget  @0x5575E69C   C3         ret

so an AI player never advertises a site as a move target and never searches one.
The AI's only loot source is hero drops.

Two overrides fix that:

  * VMT +0x1C0 (ExecuteAI)       -> cave_execai   -- mints the search token event
  * VMT +0x0CC (MapFieldMsgProc) -> cave_msgproc  -- answers the AI target
                                     broadcast (msg 0x1200) with a priority

on all seven site classes.

Design source: Inioch's build_ai_sitesearch.py v2 (his tree, his cave VAs -- NOT
reused here).  Every engine address below was re-derived on OUR AoWEPACK.dpl.

================================================================================
WHY MapFieldMsgProc (+0xCC) AND NOT UpdateAITarget (+0x1C4)
================================================================================
Verified call chain (our binaries, 2026-09-02):

  AoWE.TAoWMapField.GetAITarget @0x55771D84
      builds a 0x24-byte message on its stack:
          [msg+0x00] = 0x1200
          [msg+0x04] = the map field   (filled by SendMapFieldMsg)
          [msg+0x08] = ctx             (ecx arg: player/relation/mode bytes)
          [msg+0x0C] = result record   (stack arg; FillChar'd to 0x18 zero bytes)
          [msg+0x10] = the ASKING TAIGroupControl   <-- only visible here
          [msg+0x18] = per-object layer byte        (set by SendMapFieldMsg)
          [msg+0x1C] = stop-propagation flag
      -> HSEngine.TMapField.SendMapFieldMsg @HSEPack 0x55607944
             for each object on the field, top index down:
                 [msg+0x18] = layerbyte[i]
                 call [obj_vmt + 0xCC]        <-- MapFieldMsgProc
             stops as soon as [msg+0x1C] changes
      -> AoWE.TStructure.MapFieldMsgProc @0x5575F730
             gate: GetTerrain([self+8]->[0x28], [msg+0x18]) >= 0
             msg 0x1200: ecx=[msg+0xC], edx=[msg+8], call [vmt+0x1C4]
                         then if [rec+0] < 0 -> [msg+0x1C] = 1  (veto, stops loop)

The +0x1C4 dispatch passes ONLY ctx and the result record.  The asking group --
which the strength ladder needs -- lives at [msg+0x10] and is unreachable from
there.  So the override goes one level up, at +0xCC, and chains the inherited
TStructure implementation first.  +0x1C4 is deliberately left as the vanilla stub.

Both GetAITarget callers were checked; both pass a real TAIGroupControl:
  AoWE.TAIMoveTargetSelector.ProcessStates @0x55743343 / 0x55743634
        edx = [selector+0x24C], written by TAIMoveTargetSelector.Search
        @0x55743847 from the plugin's Activate arg, which
        TAIGroupControl.ActivatePlugin @0x557390FA passes as edx = the gc.
  AoWE.TAIGroupControlTarget.Validate @0x55737FF5
        edx = [targetlist+0xC], set by TAIGroupControl.Create @0x557388FF
        ([gc+0x24] = list;  [list+0xC] = gc).

================================================================================
CAVE A -- cave_execai  (VMT +0x1C0)
================================================================================
Called from AoWE.TStructureAIPA.Process @0x55762632:
        eax = the structure
        dl  = [player+0xA6]      the AI player index
        ecx = [aipa+0x14]        the pass number
        al  = result: 0 -> drop this structure from the pass worklist (vanilla
              stub behaviour); non-zero -> keep queued AND break the loop.
Passes are exactly 1 and 2 (TStructurePhase1AIPA.Create @0x557626A3 writes 1,
TStructurePhase2AIPA.Create @0x557626E3 writes 2).  We accept both, matching
Altar.TAltar.ExecuteAI @0x557CF2C4, the only vanilla implementation.

The cave:
  1. pass in {1,2}, else return 0.
  2. ExploreS.TExplorationSite.CanSearch @0x557C1E1C (eax=site, dl=player):
        [vmt+0x1F0] GetExplored == 0   (site still holds loot)   AND
        [site+4] is the TMapField; [mapfield_vmt+0x80] is
        HSEngine.TMapField.FindOwnedChild @HSEPack 0x556077D4, so
        FindOwnedChild(field, 0x20217 TArmyHS)->[+0x1C]->[+0x12] == player
        (i.e. THIS player's army is standing on the site).
  3. strength gate (see STRENGTH below) -- no defenders always mints.  If the player's leader
     is in the army on the site: mint only when his HP >= 75% of his maximum and
     S_army >= 2*S_def.  Any other army: mint when 3*S_army >= 2*S_def.
  4. mint the search TE VERBATIM from the engine's own no-dialog branch of
     ExploreS.TExplorationSite.Search @0x557C1F34..0x557C1F7B:
        [vmt+0x160] TStructure.CreateTE   -> TStructureTE
        [vmt+0x164] TStructure.SetupTE    (binds ClassID + x/y/l)
        [te+0x18] = 0                      -> ExecuteTE routes to ExecuteSearch
        [te+0x20] = 1                      -> auto-resolve combat
        GetTokenControl(map[+0x23C], movsx byte [te+0x13])   thunk @0x5570372C
        [tokenctrl_vmt+0x10](te)           submit
        [te_vmt+0x2C]                      release
     Copying the engine's own token mint is what keeps this MP-safe: the token
     is serialised through the same stream vanilla uses, and ExecuteSearch
     @0x557C1A20 revalidates via CanSearch on every peer.
  5. always returns 0.

================================================================================
CAVE B -- cave_msgproc  (VMT +0xCC)
================================================================================
  1. chain AoWE.TStructure.MapFieldMsgProc @0x5575F730 unchanged (so 0x1106,
     0x1124, 0x1102, 0x1103, 0x1131, 0x1122, 0x1126, 0x1127, 0x110C keep working).
  2. only msg 0x1200.
  3. replicate the vanilla entry gate exactly:
        GetTerrain([site+8]->[0x28], [msg+0x18]) >= 0
     via the AoWEPACK thunk @0x55701C8C -> HSEngine.TTerrainList.GetTerrain.
     (Inioch's v2 instead guards [msg+0x18] == 0.  REJECTED: [msg+0x18] is the
     per-object layer byte SendMapFieldMsg copies out of the field's parallel
     byte array, NOT a sub-hex index, so "== 0" is an untested assumption whose
     failure mode is the whole targeting feature silently doing nothing.)
  4. ctx gates: mode [ctx+2] == 0, asking player [ctx+0] != 0 (no neutral raiders).
  5. site still holds loot: [vmt+0x1F0] GetExplored == 0.
  6. never overwrite a veto: skip if [rec+0] < 0.
  7. tag the field for the asking group with S_def (SITE RECRUIT below); a looted site
     clears its tag instead and answers nothing.
  8. ladder, then MAX-combine into [rec+0] ONLY.  [rec+8] and [rec+0xC] are the
     AI's gold/mana cost fields -- writing them corrupts its economics.

     S_def = the site's defenders, S_grp = [gc+0x50] (STRENGTH below)

        S_def == 0           ->  100    (free loot, city-tier draw)
        the group holds the asking player's leader:
            leader HP < 75%, or 4*S_grp < 7*S_def (below 1.75x)  ->  nothing
            else the ladder from 1.5x below
        any other group, 2*S_grp < 3*S_def  ->  15 (PRI_WEAK): the tag gives the target
                                 its required strength, and the engine's own selector
                                 gathers forces for it or drops it
        S_grp   >= 10*S_def  ->  100
        S_grp   >=  5*S_def  ->   75
        S_grp   >=  3*S_def  ->   45
        S_grp   >=  2*S_def  ->   30
        else (>= 1.5x)       ->   15

     Both sides use the same engine metric, so the ladder is a pure RATIO and is
     scale-free: Ziggurat's stat doubling moves S_grp and S_def together.  Do NOT
     rescale it.  For reference, a neutral mine advertises 0x32 = 50
     (Mine.TMine.UpdateAITarget @0x557B44ED).

================================================================================
STRENGTH -- every kind of damage, one metric for all three numbers
================================================================================
  S_def   = TUnitList.GetStrengthMax @0x55783338 ([site+0x34], dx=dtAll 0x3FF), at least 1
            when the roster holds a unit (a unit with no offensive band scores 0)
  S_army  = TUnitList.GetStrengthMax (the army on the site, dx=0x3FF)
  S_grp   = [gc+0x50], which TAIGroupControl.UpdateGroupChanges builds as the same sum,
            GetStrengthMax(unit, dtAll) per unit (0x55738ADC..0x55738AEA), and which the
            engine's own TAIGroupTargetSelector compares against a target's requirement.
  TUnitList.GetStrengthMax sums TAbstractUnit.GetStrengthMax @0x5577F924: the unit's best
  band among the masked kinds, (band+10) * [unit+0x34].
  ⚠ Until 2026-10-21 all four calls passed damage KIND 0 -- TUnitList.GetStrength(dl=0) and
  TAIGroupControl.GetStrengthMax(dx=1) -- which is Fire alone: GetStrength reads
  byte [unit+0x28+dl], and a band is non-zero only for the damage kinds a unit's strikes
  carry (TStrikeAbility.GetDamageTypes adds Fire only for Fire Strike).  A roster with no
  fire attack read as undefended (priority 100 for every group, a search with no gate), and
  a fire-defended site was never advertised.  Found through Inioch's share9 (README lesson
  1, ai-site-leader-safety.md v4: his "suicide site raids").

================================================================================
THE LEADER (2026-10-21, from Inioch's share9 leader-safety v6)
================================================================================
  The group's attraction (cave B) and the search (cave A) judge different things: the whole
  group, then the one army standing on the site.  So a strong group could send its leader's
  stack ahead and the leader would search alone.  Both now ask leader_in: the player's
  leader is [player+0xD4] (TPlayer.SetLeader 0x55752CF0), the player from
  TPlayerList.GetPlayers([map+0x140], index); a TUnitList holds him when he is among its
  items ([[list+8]+4], count = VMT +0x54).  HP: VMT +0xE0 GetHitPoints over +0xD0 GetHits
  (the pair ShowEx feeds HitPointsToHitPcnt), both bytes, unsigned here.
     attraction, the group holds the leader:  HP >= 75% and S_grp >= 1.75 * S_def
     search, the army on the site holds him:   HP >= 75% and S_army >= 2 * S_def

================================================================================
SITE RECRUIT -- cave C and the two finder hooks (2026-10-21, from share9)
================================================================================
  The strategic AI already gathers forces for a target it cannot take alone:
  TAIGroupTargetSelector.Process 0x5573D2C0 compares a target's required strength --
  GetRequiredBattleFieldStrength 0x5573CAC4 = [t+0x40] * the selector's superiority
  ([sel+0x70] / [sel+0x74]) -- with [gc+0x50], and calls its cooperation, recruitment and
  production controls when the group is short.  A site's defenders are a unit list on the
  site, not a map army, so [t+0x40] (TargetFoundEvent 0x5573A209, the enemy strength along
  the path) never saw them: every site looked free, and cave B had to refuse weak groups.
  Now:
    * cave B tags (asking group, the field's GetXYL key) with S_def on every site answer;
    * TFE 0x5573A20C (6 B `mov eax,[edi+0x2C] / cmp eax,-1` -> jmp cave_tfe): EBX = the new
      TAIGroupControlTarget, EDI = the TMoveTarget, ESI = the finder.  [t+0x40] = max(itself,
      tag of ([finder+0x1C], [movetarget+0x24])), then the replayed instructions;
    * ACT 0x5573A30C (the 5-byte prologue of TAIGroupTargetFinder.Activate, EDX = the group ->
      jmp cave_act): a new search drops that group's old tags, then the prologue is replayed.
  Why a table keyed by group: the selector BUFFERS its finds (ProcessStates 0x55743343 queues
  a TMoveTarget per answering field; ProcessBufferedTargets 0x55742F6C fires the event later)
  and a search runs over several Process calls (Search only sets [sel+0x10] = 1), so two
  groups' searches can overlap.  A group's event always follows that group's own query of the
  field in the same search, which wrote or cleared the tag, and its Activate cleared anything
  older -- so a stale tag is never read.
  The table: 64 entries {group, key, strength} + a ring index, 776 bytes from System.@GetMem
  (thunk 0x55701008) on first use, zeroed; its pointer is the BSS dword 0x558FAF1C (zero at
  load).  A new tag takes the first empty slot; only a full table overwrites (ring).  The
  block lives for the process.  The AI is an unsynchronised context: its decisions reach the
  other peers as tokens (the search TE above), so this process-local table is never part of
  the replicated state.

Both rosters are TArmy instances, so TUnitList.GetStrengthMax applies to both:
  [site+0x34] = TDefendersArmy, built by TArmy.Create in
                ExploreS.TExplorationSite.Create @0x557C17F4, and it is the very
                list ExecuteSearch @0x557C1A78 feeds to the search combat.
  [armyHS+0x1C] = TArmy, built by TArmy.Create in
                AoWE.TArmyHS.Create @0x557908E5.
  TArmy's VMT carries AoWE.TUnitList.GetStrength unoverridden at slots +0x90/+0x1B4.

================================================================================
REGISTER PRESERVATION -- every callee checked, not assumed
================================================================================
Delphi register convention: EAX/EDX/ECX scratch, EBX/ESI/EDI/EBP preserved.
Each of these was read to confirm it really does push/pop what we rely on:

  TExplorationSite.CanSearch     @0x557C1E1C   push ebx,esi / pop
  TUnitList.GetStrengthMax       @0x55783338   push ebx,esi,edi / pop  (ecx, edx destroyed)
  TPlayerList.GetPlayers         @0x557544D0   eax, ecx, edx only
  TMapField.GetXYL               @HSEPack 0x55606E6C   eax, ecx, edx only
  System.@GetMem                 VCL30, through 0x55701008: Delphi convention
  Cave C's own functions keep EBX/ESI/EDI/EBP; cave_act also keeps EAX/ECX/EDX for the
  replayed Activate.
  TMapField.FindOwnedChild       @0x556077D4   push ebx,esi,edi / pop   <-- this
        is the one worth checking: cave_execai holds S_def in EDI across it.
  TTerrainList.GetTerrain        @0x55605054   5 instructions, eax/edx only
  TStructure.MapFieldMsgProc     @0x5575F730   push ebx,esi,edi / pop
  GetExplored (all three impls)  @0x557C1844 (mov al,1;ret), @0x557C2930,
                                 @0x557C5A74  push ebx / pop
  CreateTE / SetupTE / GetTokenControl / token submit / TE release: vanilla
        TExplorationSite.Search keeps EBX (the site) and ESI (the TE) live
        across exactly this sequence, which is the proof we need.

================================================================================
RNG
================================================================================
No cave draws.  Every function they call is RNG-free (CanSearch,
GetStrengthMax, GetPlayers, GetXYL, GetMem, the HP getters, CreateTE, SetupTE,
GetTokenControl, GetTerrain, TStructure.MapFieldMsgProc).  The search's own rolls happen later inside
ExecuteSearch, on the engine's existing synchronised stream, unchanged.
After --apply, re-run:  python "Modding Resources/re_tools/rng_audit.py" --owners
and confirm no new site appears for this feature.

================================================================================
SAFETY
================================================================================
* PIC: the DPL rebases.  cave_msgproc is rel32 / register / virtual-call only.
  cave_execai needs the map holder 0x558E9494 and reaches it with the standard
  `call $+5; pop ecx; mov eax,[ecx + (0x558E9494 - anchor)]` delta idiom -- one
  anchor scheme, used once.  No other absolute data reference exists in either cave.
  Cave C reaches the map holder and the BSS tag cell through lib_delta (`call $+5;
  pop eax; sub eax, <link address>` = the rebase delta), the same idiom.
* .reloc: the 14 VMT slots carry HIGHLOW relocs, which stay valid because the new
  targets are in-image VAs; the two finder hooks displace no reloc (checked every
  run, with every branch into their displaced bytes).  The 8 KB cave reservation
  contains no relocs.
* Caves: A 0x55834000, B 0x55834400, C 0x55834800 (0x400 each); 0x55834C00..
  0x55835FFF stays zero.
* Cave zone 0x55834000..0x55836000, verified all-zero in BOTH the live DLL and
  Modding Resources/AoWEPACK_original_backup.dpl; the last non-zero byte anywhere
  in CODE is at 0x55832328 and CODE runs to 0x558E7918.  No build_scripts/*.py
  references any VA in 0x55834000..0x5583FFFF.
* Backup AoWEPACK.dpl.pre-aisitesearch is taken ONLY when the file is proved to
  be free of this feature (all 14 slots vanilla AND both cave zones zero).  It is
  never taken on --undo and never on a re-tune, because in both cases the file on
  disk is this script's own previous output, not an unpatched reference.
* --undo is surgical: restores the slots and the two finder hooks we own and zeroes
  the reservation.  It touches no backup, so features applied later survive.  The
  tag table is heap memory and goes with the process.

Unproven, static checks cannot reach it: that the AI now gathers forces for a site it
cannot take alone (the engine's recruitment decides, and a low-priority target minus
the selector's travel penalty may still lose to other targets), and how often a leader
stack is held back.

VA -> file offset for the CODE section is  off + 0x55700C00.

Usage:  python build_scripts/build_ai_sitesearch.py            dry run + verify
        python build_scripts/build_ai_sitesearch.py --dis      disassemble caves
        python build_scripts/build_ai_sitesearch.py --apply    write
        python build_scripts/build_ai_sitesearch.py --undo     surgical removal
"""

import argparse
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

DLL = os.path.join(GAME, "AoWEPACK.dpl")
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-aisitesearch")
PRISTINE = os.path.join(GAME, "Modding Resources", "AoWEPACK_original_backup.dpl")

VA_BASE = 0x55700C00            # CODE:  VA = file_offset + this
CODE_END = 0x558E7918           # end of CODE (vsize)

# ---------------------------------------------------------------- engine addrs
STUB_EXECAI      = 0x5575E698   # AoWE.TStructure.ExecuteAI       (xor eax,eax; ret)
STUB_UPDATEAI    = 0x5575E69C   # AoWE.TStructure.UpdateAITarget  (ret)  -- untouched
STRUCT_MSGPROC   = 0x5575F730   # AoWE.TStructure.MapFieldMsgProc
CANSEARCH        = 0x557C1E1C   # ExploreS.TExplorationSite.CanSearch(eax=site, dl=player)
LIST_STRENGTHMAX = 0x55783338   # AoWE.TUnitList.GetStrengthMax(eax=list, dx=mask) -> eax = sum over
                                #   the units of TAbstractUnit.GetStrengthMax(unit, mask)
DT_ALL           = 0x03FF       # AoWE.dtAll (0x558E8044): every damage kind
GETPLAYERS       = 0x557544D0   # AoWE.TPlayerList.GetPlayers(eax=list, edx=index) -> player | nil
GETXYL           = 0x55701FAC   # thunk -> HSEPack.dpl!HSEngine.TMapField.GetXYL(eax=field) -> key
GETMEM           = 0x55701008   # thunk -> VCL30.dpl!System.@GetMem(eax=size) -> block
GETTOKENCTL      = 0x5570372C   # thunk -> Network.dpl!NetworkE.TTokenManager.GetTokenControl
GETTERRAIN       = 0x55701C8C   # thunk -> HSEPack.dpl!HSEngine.TTerrainList.GetTerrain
MAPPTR           = 0x558E9494   # -> ptr -> the TAoWHSMap object
TAG_ARMYHS       = 0x20217      # GetObjectOfType tag for TArmyHS
TAG_CELL         = 0x558FAF1C   # BSS dword: pointer to the site-tag table (0 until first use)

# TAIGroupTargetFinder hooks (site recruit)
TFE_SITE   = 0x5573A20C         # TargetFoundEvent: mov eax,[edi+0x2C] / cmp eax,-1
TFE_ORIG   = bytes.fromhex("8b472c83f8ff")
TFE_RESUME = 0x5573A212
TFE_FN     = (0x5573A18C, 0x5573A234)
ACT_SITE   = 0x5573A30C         # Activate prologue: push ebx/esi/edi, mov esi,edx
ACT_ORIG   = bytes.fromhex("5356578bf2")
ACT_RESUME = 0x5573A311
ACT_FN     = (0x5573A30C, 0x5573A348)

VMT_MSGPROC      = 0x0CC        # MapFieldMsgProc
VMT_CREATETE     = 0x160        # TStructure.CreateTE
VMT_SETUPTE      = 0x164        # TStructure.SetupTE
VMT_EXECUTEAI    = 0x1C0        # TStructure.ExecuteAI
VMT_UPDATEAI     = 0x1C4        # TStructure.UpdateAITarget -- left as the stub
VMT_GETEXPLORED  = 0x1F0        # GetExplored  (1 = looted/cleared)
VMT_FINDCHILD    = 0x080        # TMapField.FindOwnedChild, on the field at [site+4]
VMT_TOKEN_SUBMIT = 0x010        # token control: submit a TE
VMT_TE_RELEASE   = 0x02C        # TE: release

VMT_COUNT        = 0x054        # TUnitList.Count
VMT_MAXHP        = 0x0D0        # TAbstractUnit: maximum hit points (al)
VMT_HP           = 0x0E0        # TAbstractUnit: hit points (al)  -- both as ShowEx feeds HitPointsToHitPcnt

FLD_DEFENDERS    = 0x34         # site -> TDefendersArmy (TArmy)
FLD_ARMY         = 0x1C         # TArmyHS -> TArmy
FLD_PLAYERS      = 0x140        # map -> TPlayerList
FLD_LEADER       = 0xD4         # player -> the leader unit (TPlayer.SetLeader 0x55752CF0)
FLD_GC_UNITS     = 0x0C         # TAIGroupControl -> its units (TUnitList)
FLD_GC_STRENGTH  = 0x50         # TAIGroupControl: sum of GetStrengthMax(unit, dtAll)
FLD_FINDER_GC    = 0x1C         # TAIGroupTargetFinder -> its TAIGroupControl
FLD_MT_XYL       = 0x24         # TMoveTarget: GetXYL of the answering field
FLD_T_REQ        = 0x40         # TAIGroupControlTarget: the strength the selector requires
FLD_MAP_TOKENMGR = 0x23C        # map -> token manager
FLD_TE_KIND      = 0x18         # TStructureTE: 0 = search
FLD_TE_AUTO      = 0x20         # TStructureTE: 1 = auto-resolve
FLD_TE_PLAYER    = 0x13         # TStructureTE: player byte for GetTokenControl
FLD_STRUCT_TYPE  = 0x08         # structure -> type record ([type+0x28] = terrain list)

# ------------------------------------------------------------------ our caves
CAVE_LO   = 0x55834000          # exclusive reservation, 8 KB
CAVE_HI   = 0x55836000
CAVE_A    = 0x55834000          # cave_execai
CAVE_A_END = 0x55834400
CAVE_B    = 0x55834400          # cave_msgproc
CAVE_B_END = 0x55834800
CAVE_C    = 0x55834800          # helpers, the tag table code, the two finder hooks' caves
CAVE_C_END = 0x55834C00

# ladder / gate constants (ratios -- scale-free, do NOT rescale)
PRI_FREE   = 100                # undefended, unlooted
PRI_10X    = 100
PRI_5X     = 75
PRI_3X     = 45
PRI_2X     = 30
PRI_1_5X   = 15
PRI_WEAK   = 15                 # a leaderless group below 1.5x: the engine's recruitment decides

TAG_N      = 64                 # tag table entries {group, field key, strength}
TAG_BYTES  = 8 + 12 * TAG_N     # header: ring index, spare

PH_MAP = 0x11111111             # placeholder for the PIC delta displacement

SITES = [
    ("TExplorationSite",     0x557C1440),
    ("TItemExplorationSite", 0x557C23BC),
    ("TMonsterlair",         0x557C2D24),
    ("TDungeon",             0x557C557C),
    ("TCrypt",               0x557C64D0),
    ("TRuin",                0x557C68FC),
    ("TPyramid",             0x557C6D20),
]


def off(va):
    return va - VA_BASE


# ---------------------------------------------------------------- assembling
def asm(src, addr):
    """Assemble, stripping ';' comments first.

    keystone HANGS on a line containing a ';' comment, so the comments are
    removed here rather than omitted from the source.
    """
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    clean = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(clean, addr)
    if code is None:
        sys.exit("ERROR: keystone failed to assemble the cave at 0x%08X" % addr)
    return bytearray(code)


def build_lib():
    """cave C: the helpers cave_execai and cave_msgproc call, the site-tag table, and the two
    TAIGroupTargetFinder hook caves.  Each function is assembled at its own 16-aligned address,
    after every function it calls.  Delphi register convention throughout: EAX/ECX/EDX scratch,
    EBX/ESI/EDI/EBP kept.  Returns ({name: va}, blob)."""
    at, blob = {}, bytearray()

    def place(name, src):
        nonlocal blob
        blob += b"\x00" * ((-len(blob)) % 16)
        va = CAVE_C + len(blob)
        at[name] = va
        blob += asm(src, va)

    # eax = the image's rebase delta (runtime - link).  `sub eax, _ld` takes _ld's LINK address
    # as an immediate; there is no .reloc entry under it, so it is never rebased.
    place("lib_delta", """
        call  _ld
    _ld:
        pop   eax
        sub   eax, _ld
        ret
    """)

    # -> eax = the tag table, allocated and zeroed on first use; its pointer lives in BSS.
    place("tag_table", f"""
        call  {at['lib_delta']:#x}
        lea   ecx, [eax + {TAG_CELL:#x}]
        mov   eax, [ecx]
        test  eax, eax
        jne   _tt_ret
        push  ecx
        mov   eax, {TAG_BYTES:#x}
        call  {GETMEM:#x}
        pop   ecx
        mov   [ecx], eax
        push  edi
        push  eax
        mov   edi, eax
        xor   eax, eax
        mov   ecx, {TAG_BYTES // 4:#x}
        rep   stosd
        pop   eax
        pop   edi
    _tt_ret:
        ret
    """)

    # tag_put(eax = group, edx = map field, ecx = strength): set the group's tag for that field.
    # Strength 0 clears an existing tag and never makes a new one.  A new tag takes the first
    # empty slot; only a full table overwrites, at the ring index in the header.  Entry k at
    # +8+12k: group, key, strength (0 = empty).
    place("tag_put", f"""
        push  ebx
        push  esi
        push  edi
        push  ebp
        mov   ebx, eax
        mov   ebp, ecx
        test  edx, edx
        je    _tp_out
        mov   eax, edx
        call  {GETXYL:#x}
        mov   esi, eax
        call  {at['tag_table']:#x}
        test  eax, eax
        je    _tp_out
        mov   edi, eax
        or    eax, -1
        xor   ecx, ecx
    _tp_find:
        lea   edx, [ecx + ecx*2]
        cmp   dword ptr [edi + edx*4 + 0x10], 0
        jne   _tp_live
        test  eax, eax
        jns   _tp_next
        mov   eax, ecx
        jmp   _tp_next
    _tp_live:
        cmp   [edi + edx*4 + 8], ebx
        jne   _tp_next
        cmp   [edi + edx*4 + 0xc], esi
        je    _tp_set
    _tp_next:
        inc   ecx
        cmp   ecx, {TAG_N:#x}
        jl    _tp_find
        test  ebp, ebp
        jle   _tp_out
        mov   ecx, eax
        test  ecx, ecx
        jns   _tp_slot
        mov   ecx, [edi]
        lea   eax, [ecx + 1]
        cmp   eax, {TAG_N:#x}
        jl    _tp_wrap
        xor   eax, eax
    _tp_wrap:
        mov   [edi], eax
    _tp_slot:
        lea   edx, [ecx + ecx*2]
    _tp_set:
        mov   [edi + edx*4 + 8], ebx
        mov   [edi + edx*4 + 0xc], esi
        mov   [edi + edx*4 + 0x10], ebp
    _tp_out:
        pop   ebp
        pop   edi
        pop   esi
        pop   ebx
        ret
    """)

    # tag_get(eax = group, edx = field key) -> eax = the tagged strength, 0 if none.
    place("tag_get", f"""
        push  ebx
        push  esi
        push  edi
        mov   ebx, eax
        mov   esi, edx
        call  {at['tag_table']:#x}
        test  eax, eax
        je    _tg_none
        mov   edi, eax
        xor   ecx, ecx
    _tg_find:
        lea   edx, [ecx + ecx*2]
        mov   eax, [edi + edx*4 + 0x10]
        test  eax, eax
        je    _tg_next
        cmp   [edi + edx*4 + 8], ebx
        jne   _tg_next
        cmp   [edi + edx*4 + 0xc], esi
        je    _tg_ret
    _tg_next:
        inc   ecx
        cmp   ecx, {TAG_N:#x}
        jl    _tg_find
    _tg_none:
        xor   eax, eax
    _tg_ret:
        pop   edi
        pop   esi
        pop   ebx
        ret
    """)

    # tag_clear(eax = group): drop every tag of that group.
    place("tag_clear", f"""
        push  ebx
        push  edi
        mov   ebx, eax
        call  {at['tag_table']:#x}
        test  eax, eax
        je    _tc_out
        mov   edi, eax
        xor   ecx, ecx
    _tc_loop:
        lea   edx, [ecx + ecx*2]
        cmp   [edi + edx*4 + 8], ebx
        jne   _tc_next
        mov   dword ptr [edi + edx*4 + 0x10], 0
    _tc_next:
        inc   ecx
        cmp   ecx, {TAG_N:#x}
        jl    _tc_loop
    _tc_out:
        pop   edi
        pop   ebx
        ret
    """)

    # site_def(eax = site) -> eax = S_def: the defenders' all-kinds strength, at least 1 when the
    # roster holds a unit (a unit with no offensive band scores 0), 0 when it holds none.
    place("site_def", f"""
        mov   eax, [eax + {FLD_DEFENDERS:#x}]
        test  eax, eax
        je    _sd_zero
        mov   ecx, [eax + 8]
        test  ecx, ecx
        je    _sd_zero
        cmp   dword ptr [ecx + 8], 0
        jle   _sd_zero
        mov   edx, {DT_ALL:#x}
        call  {LIST_STRENGTHMAX:#x}
        test  eax, eax
        jg    _sd_ret
        mov   eax, 1
    _sd_ret:
        ret
    _sd_zero:
        xor   eax, eax
        ret
    """)

    # leader_in(eax = TUnitList, edx = player index) -> eax = that player's leader if the list
    # holds him, else 0.
    place("leader_in", f"""
        push  ebx
        push  esi
        push  edi
        mov   esi, eax
        mov   edi, edx
        test  esi, esi
        je    _li_no
        call  {at['lib_delta']:#x}
        mov   eax, [eax + {MAPPTR:#x}]
        mov   eax, [eax]
        test  eax, eax
        je    _li_no
        mov   eax, [eax + {FLD_PLAYERS:#x}]
        mov   edx, edi
        call  {GETPLAYERS:#x}
        test  eax, eax
        je    _li_no
        mov   ebx, [eax + {FLD_LEADER:#x}]
        test  ebx, ebx
        je    _li_no
        mov   eax, esi
        mov   edx, [eax]
        call  dword ptr [edx + {VMT_COUNT:#x}]
        mov   ecx, eax
        mov   eax, [esi + 8]
        test  eax, eax
        je    _li_no
        mov   eax, [eax + 4]
    _li_loop:
        dec   ecx
        jl    _li_no
        cmp   [eax + ecx*4], ebx
        jne   _li_loop
        mov   eax, ebx
        jmp   _li_out
    _li_no:
        xor   eax, eax
    _li_out:
        pop   edi
        pop   esi
        pop   ebx
        ret
    """)

    # hp_ok(eax = unit) -> al = 1 when 4*HP >= 3*maximum, i.e. at least 75%.
    place("hp_ok", f"""
        push  ebx
        push  esi
        mov   esi, eax
        mov   edx, [eax]
        call  dword ptr [edx + {VMT_MAXHP:#x}]
        movzx ebx, al
        mov   eax, esi
        mov   edx, [eax]
        call  dword ptr [edx + {VMT_HP:#x}]
        movzx eax, al
        shl   eax, 2
        lea   ebx, [ebx + ebx*2]
        cmp   eax, ebx
        setge al
        pop   esi
        pop   ebx
        ret
    """)

    # TargetFoundEvent at TFE_SITE: EBX = the new target, EDI = the TMoveTarget, ESI = the finder.
    # Raise the target's required strength to the site tag of this finder's group, then replay.
    place("cave_tfe", f"""
        mov   eax, [esi + {FLD_FINDER_GC:#x}]
        mov   edx, [edi + {FLD_MT_XYL:#x}]
        call  {at['tag_get']:#x}
        cmp   eax, [ebx + {FLD_T_REQ:#x}]
        jle   _tf_done
        mov   [ebx + {FLD_T_REQ:#x}], eax
    _tf_done:
        mov   eax, [edi + 0x2c]
        cmp   eax, -1
        jmp   {TFE_RESUME:#x}
    """)

    # TAIGroupTargetFinder.Activate entry (EAX = finder, EDX = its group): a new search starts,
    # so drop that group's old tags; then replay the 5-byte prologue.
    place("cave_act", f"""
        push  eax
        push  ecx
        push  edx
        mov   eax, edx
        call  {at['tag_clear']:#x}
        pop   edx
        pop   ecx
        pop   eax
        push  ebx
        push  esi
        push  edi
        mov   esi, edx
        jmp   {ACT_RESUME:#x}
    """)
    return at, bytes(blob)


LIB, LIB_BLOB = build_lib()


def jmp6(src, dst, length):
    """`jmp dst` (E9 rel32) padded with nops to the displaced length."""
    return b"\xE9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (length - 5)


def build_execai():
    """VMT +0x1C0.  eax=site, dl=AI player index, ecx=AIPA pass.  Returns al=0."""
    src = """
        cmp   ecx, 1                       ; TStructurePhase1AIPA
        je    _go
        cmp   ecx, 2                       ; TStructurePhase2AIPA
        jne   _no
    _go:
        push  ebx
        push  esi
        push  edi
        push  ebp
        movsx ebp, dl                      ; ebp = the AI player index
        mov   ebx, eax                     ; ebx = site
        mov   edx, ebp
        call  0x%(CANSEARCH)X              ; loot left AND our army is standing on it
        test  al, al
        je    _out

        mov   eax, ebx
        call  0x%(SITE_DEF)X               ; eax = S_def, all damage kinds
        mov   edi, eax
        test  edi, edi
        jle   _mint                        ; no defenders -> always search

        mov   edx, 0x%(TAG_ARMYHS)X
        mov   eax, [ebx + 4]               ; the TMapField
        mov   ecx, [eax]
        call  dword ptr [ecx + 0x%(VMT_FINDCHILD)X]   ; FindOwnedChild (preserves edi, ebp)
        test  eax, eax
        je    _out
        mov   esi, [eax + 0x%(FLD_ARMY)X]  ; TArmyHS -> TArmy
        test  esi, esi
        je    _out
        mov   eax, esi
        mov   edx, 0x%(DT_ALL)X
        call  0x%(LIST_STRENGTHMAX)X       ; eax = S_army
        push  eax
        mov   eax, esi
        mov   edx, ebp
        call  0x%(LEADER_IN)X              ; is our leader in this army?
        test  eax, eax
        je    _plain
        call  0x%(HP_OK)X
        test  al, al
        pop   eax                          ; S_army (pop keeps the flags)
        je    _out                         ; leader below 75%% HP -> no search
        lea   edx, [edi + edi]             ; 2 * S_def
        cmp   eax, edx
        jl    _out                         ; leader's army below 2x -> no search
        jmp   _mint
    _plain:
        pop   eax
        lea   ecx, [eax + eax*2]           ; 3 * S_army
        lea   edx, [edi + edi]             ; 2 * S_def
        cmp   ecx, edx
        jl    _out                         ; below 2/3x -> no suicide search

    _mint:
        mov   eax, ebx
        mov   edx, [eax]
        call  dword ptr [edx + 0x%(VMT_CREATETE)X]
        mov   esi, eax                     ; esi = the TStructureTE
        test  esi, esi
        je    _out
        mov   edx, esi
        mov   eax, ebx
        mov   ecx, [eax]
        call  dword ptr [ecx + 0x%(VMT_SETUPTE)X]
        xor   eax, eax
        mov   [esi + 0x%(FLD_TE_KIND)X], eax
        mov   dword ptr [esi + 0x%(FLD_TE_AUTO)X], 1
        call  _anchor
    _anchor:
        pop   ecx                          ; ecx = runtime VA of _anchor
        mov   eax, [ecx + 0x%(PH_MAP)X]    ; -> ptr -> map   (delta-patched below)
        mov   eax, [eax]
        mov   eax, [eax + 0x%(FLD_MAP_TOKENMGR)X]
        movsx edx, byte ptr [esi + 0x%(FLD_TE_PLAYER)X]
        call  0x%(GETTOKENCTL)X
        mov   edx, esi
        mov   ecx, [eax]
        call  dword ptr [ecx + 0x%(VMT_TOKEN_SUBMIT)X]
        mov   eax, esi
        mov   edx, [eax]
        call  dword ptr [edx + 0x%(VMT_TE_RELEASE)X]
    _out:
        pop   ebp
        pop   edi
        pop   esi
        pop   ebx
    _no:
        xor   eax, eax
        ret
    """ % dict(globals(), SITE_DEF=LIB["site_def"], LEADER_IN=LIB["leader_in"],
               HP_OK=LIB["hp_ok"])

    code = asm(src, CAVE_A)

    # locate the `call $+5` (E8 00000000) that immediately precedes `pop ecx` (59)
    hits = [k for k in range(len(code) - 5)
            if code[k] == 0xE8 and code[k + 1:k + 5] == b"\x00\x00\x00\x00"
            and code[k + 5] == 0x59]
    if len(hits) != 1:
        sys.exit("ERROR: expected exactly one `call $+5; pop ecx` anchor, found %d"
                 % len(hits))
    anchor = CAVE_A + hits[0] + 5

    n = code.count(struct.pack("<I", PH_MAP))
    if n != 1:
        sys.exit("ERROR: expected exactly one PIC placeholder in cave_execai, found %d" % n)
    j = code.find(struct.pack("<I", PH_MAP))
    code[j:j + 4] = struct.pack("<i", MAPPTR - anchor)
    return bytes(code), anchor


def build_msgproc():
    """VMT +0xCC.  eax=site, edx=msg.  No return value."""
    src = """
        push  ebx
        push  esi
        push  edi
        push  ebp
        mov   esi, eax                     ; esi = site
        mov   edi, edx                     ; edi = msg
        call  0x%(STRUCT_MSGPROC)X         ; chain the inherited handler first

        cmp   dword ptr [edi], 0x1200      ; AI target broadcast?
        jne   _done

        mov   edx, [edi + 0x18]            ; per-object layer byte
        mov   eax, [esi + 0x%(FLD_STRUCT_TYPE)X]
        mov   eax, [eax + 0x28]            ; the structure type's terrain list
        call  0x%(GETTERRAIN)X             ; vanilla's own entry gate
        test  al, al
        jl    _done

        mov   eax, [edi + 8]               ; ctx
        test  eax, eax
        je    _done
        cmp   byte ptr [eax + 2], 0        ; mode 0 only
        jne   _done
        cmp   byte ptr [eax], 0            ; asking player != 0 (no neutral raiders)
        je    _done

        mov   ebx, [edi + 0xC]             ; result record
        test  ebx, ebx
        je    _done
        cmp   dword ptr [ebx], 0
        jl    _done                        ; someone vetoed this hex -- never clobber it

        cmp   dword ptr [edi + 0x10], 0    ; the asking TAIGroupControl
        je    _done

        mov   eax, esi
        mov   edx, [eax]
        call  dword ptr [edx + 0x%(VMT_GETEXPLORED)X]
        test  al, al
        jne   _looted

        mov   eax, esi
        call  0x%(SITE_DEF)X
        mov   ebp, eax                     ; ebp = S_def, all damage kinds
        mov   eax, [edi + 0x10]            ; tag (group, field) with S_def, which the
        mov   edx, [edi + 4]               ; finder hook turns into the target's required
        mov   ecx, ebp                     ; strength (0 clears it)
        call  0x%(TAG_PUT)X
        test  ebp, ebp
        jle   _undef

        mov   eax, [edi + 0x10]
        mov   eax, [eax + 0x%(FLD_GC_UNITS)X]
        mov   edx, [edi + 8]
        movsx edx, byte ptr [edx]          ; the asking player
        call  0x%(LEADER_IN)X              ; is that player's leader in the group?
        test  eax, eax
        je    _noleader
        call  0x%(HP_OK)X
        test  al, al
        je    _done                        ; leader below 75%% HP -> nothing
        mov   eax, [edi + 0x10]
        mov   eax, [eax + 0x%(FLD_GC_STRENGTH)X]   ; eax = S_grp
        lea   ecx, [eax*4]                 ; 4 * S_grp
        lea   edx, [ebp*8]
        sub   edx, ebp                     ; 7 * S_def
        cmp   ecx, edx
        jl    _done                        ; leader's group below 1.75x -> nothing
        jmp   _ladder
    _noleader:
        mov   eax, [edi + 0x10]
        mov   eax, [eax + 0x%(FLD_GC_STRENGTH)X]   ; eax = S_grp
        lea   ecx, [ebp + ebp*2]           ; 3 * S_def
        lea   edx, [eax + eax]             ; 2 * S_grp
        cmp   edx, ecx
        jge   _ladder
        mov   eax, %(PRI_WEAK)d            ; below 1.5x: a low answer, and the tag lets
        jmp   _comb                        ; the selector gather forces for it
    _ladder:
        lea   ecx, [ebp + ebp*2]           ; 3 * S_def
        lea   edx, [ebp + ebp*4]
        add   edx, edx                     ; 10 * S_def
        cmp   eax, edx
        jge   _p10x
        lea   edx, [ebp + ebp*4]           ; 5 * S_def
        cmp   eax, edx
        jge   _p5x
        cmp   eax, ecx                     ; 3 * S_def
        jge   _p3x
        lea   edx, [ebp + ebp]             ; 2 * S_def
        cmp   eax, edx
        jge   _p2x
        mov   eax, %(PRI_1_5X)d
        jmp   _comb
    _p2x:
        mov   eax, %(PRI_2X)d
        jmp   _comb
    _p3x:
        mov   eax, %(PRI_3X)d
        jmp   _comb
    _p5x:
        mov   eax, %(PRI_5X)d
        jmp   _comb
    _p10x:
        mov   eax, %(PRI_10X)d
        jmp   _comb
    _looted:
        mov   eax, [edi + 0x10]            ; looted: drop the field's tag, answer nothing
        mov   edx, [edi + 4]
        xor   ecx, ecx
        call  0x%(TAG_PUT)X
        jmp   _done
    _undef:
        mov   eax, %(PRI_FREE)d
    _comb:
        cmp   dword ptr [ebx], eax         ; MAX-combine into [rec+0] only
        jge   _done
        mov   dword ptr [ebx], eax
    _done:
        pop   ebp
        pop   edi
        pop   esi
        pop   ebx
        ret
    """ % dict(globals(), SITE_DEF=LIB["site_def"], LEADER_IN=LIB["leader_in"],
               HP_OK=LIB["hp_ok"], TAG_PUT=LIB["tag_put"])
    return bytes(asm(src, CAVE_B)), None


# ---------------------------------------------------------------- disassembly
def disasm(data, va, title):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        print("      (capstone not installed -- cannot disassemble)")
        return
    names = {
        CANSEARCH: "TExplorationSite.CanSearch",
        LIST_STRENGTHMAX: "TUnitList.GetStrengthMax",
        GETPLAYERS: "TPlayerList.GetPlayers",
        GETXYL: "->TMapField.GetXYL",
        GETMEM: "->System.@GetMem",
        TFE_RESUME: "back into TargetFoundEvent",
        ACT_RESUME: "back into TAIGroupTargetFinder.Activate",
        GETTOKENCTL: "->TTokenManager.GetTokenControl",
        GETTERRAIN: "->TTerrainList.GetTerrain",
        STRUCT_MSGPROC: "TStructure.MapFieldMsgProc",
    }
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    print("      --- %s (%d bytes) ---" % (title, len(data)))
    for i in md.disasm(bytes(data), va):
        note = ""
        if i.mnemonic in ("call", "jmp") and i.op_str.startswith("0x"):
            t = int(i.op_str, 16)
            if t in names:
                note = "   ; %s" % names[t]
        print("      %08X  %-24s %-7s %s%s"
              % (i.address, i.bytes.hex(), i.mnemonic, i.op_str, note))


# ---------------------------------------------------------------- edit table
def build_edits():
    """[(va, orig_bytes, new_bytes, label, kind)] -- kind in {'cave','slot'}."""
    ca, anchor = build_execai()
    cb, _ = build_msgproc()

    if CAVE_A + len(ca) > CAVE_A_END:
        sys.exit("ERROR: cave_execai is %d bytes, exceeds its 0x%X sub-zone"
                 % (len(ca), CAVE_A_END - CAVE_A))
    if CAVE_B + len(cb) > CAVE_B_END:
        sys.exit("ERROR: cave_msgproc is %d bytes, exceeds its 0x%X sub-zone"
                 % (len(cb), CAVE_B_END - CAVE_B))
    if CAVE_C + len(LIB_BLOB) > CAVE_C_END:
        sys.exit("ERROR: cave C is %d bytes, exceeds its 0x%X sub-zone"
                 % (len(LIB_BLOB), CAVE_C_END - CAVE_C))
    if CAVE_HI > CODE_END:
        sys.exit("ERROR: cave reservation runs past the end of CODE")

    pad_a = ca + b"\x00" * (CAVE_A_END - CAVE_A - len(ca))
    pad_b = cb + b"\x00" * (CAVE_B_END - CAVE_B - len(cb))
    pad_c = LIB_BLOB + b"\x00" * (CAVE_C_END - CAVE_C - len(LIB_BLOB))

    edits = [
        (CAVE_A, b"\x00" * len(pad_a), pad_a, "cave_execai  (VMT +0x1C0)", "cave"),
        (CAVE_B, b"\x00" * len(pad_b), pad_b, "cave_msgproc (VMT +0x0CC)", "cave"),
        (CAVE_C, b"\x00" * len(pad_c), pad_c, "cave C (helpers, tags, finder hooks)", "cave"),
        (TFE_SITE, TFE_ORIG, jmp6(TFE_SITE, LIB["cave_tfe"], len(TFE_ORIG)),
         "TAIGroupTargetFinder.TargetFoundEvent hook", "hook"),
        (ACT_SITE, ACT_ORIG, jmp6(ACT_SITE, LIB["cave_act"], len(ACT_ORIG)),
         "TAIGroupTargetFinder.Activate hook", "hook"),
    ]
    for nm, vmt in SITES:
        edits.append((vmt + VMT_EXECUTEAI,
                      struct.pack("<I", STUB_EXECAI), struct.pack("<I", CAVE_A),
                      "%-20s +0x1C0 ExecuteAI" % nm, "slot"))
        edits.append((vmt + VMT_MSGPROC,
                      struct.pack("<I", STRUCT_MSGPROC), struct.pack("<I", CAVE_B),
                      "%-20s +0x0CC MapFieldMsgProc" % nm, "slot"))
    return edits, ca, cb, anchor


# ---------------------------------------------------------------- reloc check
def reloc_set(data, pe):
    rva_dir, size = pe.dirs[5]
    out = set()
    p = pe.rva2off(rva_dir)
    end = p + size
    while p < end:
        page, blk = struct.unpack_from("<II", data, p)
        if blk == 0:
            break
        for i in range((blk - 8) // 2):
            e = struct.unpack_from("<H", data, p + 8 + i * 2)[0]
            if (e >> 12) == 3:
                out.add(pe.image_base + page + (e & 0xFFF))
        p += blk
    return out


def safety_checks(data):
    sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
    try:
        from pescan import PE
    except ImportError:
        print("  (pescan unavailable -- skipping .reloc / section checks)")
        return
    pe = PE(DLL)
    code = [s for s in pe.sections if s[0] == "CODE"][0]
    delta = pe.image_base + code[1] - code[3]
    if delta != VA_BASE:
        sys.exit("ERROR: CODE VA->offset delta is 0x%08X, expected 0x%08X"
                 % (delta, VA_BASE))
    rl = reloc_set(data, pe)
    bad = [r for r in rl if CAVE_LO <= r < CAVE_HI]
    if bad:
        sys.exit("ERROR: %d .reloc entr(ies) inside the cave reservation" % len(bad))
    missing = [(nm, s) for nm, vmt in SITES for s in (VMT_EXECUTEAI, VMT_MSGPROC)
               if (vmt + s) not in rl]
    print("  .reloc  : cave zone clean; all %d VMT slots carry relocs%s"
          % (len(SITES) * 2, "" if not missing else "  !! MISSING: %s" % missing))
    if missing:
        sys.exit("ERROR: a VMT slot we repoint carries no .reloc entry -- refusing")
    under = [r for r in rl for va, n in ((TFE_SITE, len(TFE_ORIG)), (ACT_SITE, len(ACT_ORIG)))
             if r < va + n and r + 4 > va]
    if under:
        sys.exit("ERROR: a .reloc entry sits under a finder hook: %s"
                 % ", ".join("%08X" % r for r in under))
    inner = interior_jumps(data)
    print("  hooks   : no .reloc under either finder hook; jumps into a hook's interior: %s"
          % (", ".join("%08X" % v for v in inner) or "none"))
    if inner:
        sys.exit("ERROR: a branch lands inside a finder hook's displaced bytes")


def interior_jumps(data):
    """Branches that land strictly inside a finder hook's displaced bytes: rel32 calls/jumps from
    anywhere in CODE, and every relative branch in the two hooked functions."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    hooks = [(TFE_SITE, TFE_SITE + len(TFE_ORIG), TFE_FN), (ACT_SITE, ACT_SITE + len(ACT_ORIG), ACT_FN)]
    bad = []
    for i in range(0x400, off(CODE_END) - 5):
        if data[i] in (0xE8, 0xE9):
            src = i + VA_BASE
            t = src + 5 + struct.unpack_from("<i", data, i + 1)[0]
            bad += [src for lo, hi, _f in hooks if lo < t < hi and not lo <= src < hi]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for lo, hi, (flo, fhi) in hooks:
        for ins in md.disasm(bytes(data[off(flo):off(fhi)]), flo):
            if lo <= ins.address < hi or not (ins.mnemonic.startswith("j") or ins.mnemonic == "call"):
                continue
            try:
                t = int(ins.op_str, 16)
            except ValueError:
                continue
            if lo < t < hi:
                bad.append(ins.address)
    return sorted(set(bad))


def pristine_check():
    """Confirm the 14 slots are vanilla in the pristine reference too."""
    if not os.path.isfile(PRISTINE):
        print("  pristine: %s not found -- skipped" % os.path.basename(PRISTINE))
        return
    p = open(PRISTINE, "rb").read()
    bad = []
    for nm, vmt in SITES:
        for s, want in ((VMT_EXECUTEAI, STUB_EXECAI), (VMT_MSGPROC, STRUCT_MSGPROC),
                        (VMT_UPDATEAI, STUB_UPDATEAI)):
            got = struct.unpack_from("<I", p, off(vmt + s))[0]
            if got != want:
                bad.append("%s+0x%X=%08X" % (nm, s, got))
    z = p[off(CAVE_LO):off(CAVE_HI)]
    print("  pristine: 21 slots vanilla=%s  cave zone zero=%s"
          % ("yes" if not bad else "NO -> %s" % bad, set(z) == {0}))


# ---------------------------------------------------------------------- undo
def undo(data, edits):
    slots = [(va, ob, nb, lbl) for va, ob, nb, lbl, k in edits if k in ("slot", "hook")]
    owned = [(va, ob, nb, lbl) for va, ob, nb, lbl in slots
             if bytes(data[off(va):off(va) + len(nb)]) == nb]
    foreign = [(va, lbl) for va, ob, nb, lbl in slots
               if bytes(data[off(va):off(va) + len(nb)]) not in (ob, nb)]
    if foreign:
        sys.exit("ABORT: %d VMT slot(s) hold bytes that are neither vanilla nor ours:\n  %s"
                 % (len(foreign), "\n  ".join("0x%08X %s" % f for f in foreign)))
    if not owned:
        print("Nothing to undo: no VMT slot points at our caves.")
        return 0

    # never zero a neighbour's bytes: outside our two caves the reservation must
    # already be zero
    tail = bytes(data[off(CAVE_C_END):off(CAVE_HI)])
    if set(tail) not in ({0}, set()):
        sys.exit("ABORT: 0x%08X..0x%08X inside our reservation is not zero -- refusing "
                 "to wipe it blind." % (CAVE_C_END, CAVE_HI - 1))

    print("UNDO -- restoring %d VMT slot(s) and hook(s) and zeroing 0x%08X..0x%08X (%d bytes):"
          % (len(owned), CAVE_LO, CAVE_HI - 1, CAVE_HI - CAVE_LO))
    size = len(data)
    for va, ob, nb, lbl in owned:
        print("   0x%08X  %s  -> %s" % (va, lbl, ob[::-1].hex() if len(ob) == 4 else ob.hex(" ")))
        data[off(va):off(va) + len(ob)] = ob
    data[off(CAVE_LO):off(CAVE_HI)] = b"\x00" * (CAVE_HI - CAVE_LO)
    if len(data) != size:
        sys.exit("ERROR: undo would change the file length -- nothing written")
    write(data)
    print("Removed. No .pre-* backup was touched, so later features are intact.")
    return 0


def write(data):
    try:
        with open(DLL, "wb") as f:
            f.write(bytes(data))
    except PermissionError:
        sys.exit("ERROR: %s is locked. Kill AoW.exe / AoWCompat.exe / AoWDevEd.exe / "
                 "AoWEd.exe and retry." % os.path.basename(DLL))


# ---------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="AI players path to and search exploration sites (AoWEPACK.dpl).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the patch (default: dry run)")
    ap.add_argument("--undo", action="store_true",
                    help="surgical removal: restore the 14 VMT slots and zero the cave "
                         "reservation. Touches no backup.")
    ap.add_argument("--dis", "--show", dest="dis", action="store_true",
                    help="disassemble both caves and exit")
    args = ap.parse_args()

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s\n(set AOW_GAME_DIR to the game directory)" % DLL)

    data = bytearray(open(DLL, "rb").read())
    edits, ca, cb, anchor = build_edits()

    print("build_ai_sitesearch -- AI explores/searches exploration sites")
    print("  DLL     : %s" % DLL)
    print("  caves   : cave_execai  0x%08X  %3d bytes (zone 0x%X)"
          % (CAVE_A, len(ca), CAVE_A_END - CAVE_A))
    print("            cave_msgproc 0x%08X  %3d bytes (zone 0x%X)"
          % (CAVE_B, len(cb), CAVE_B_END - CAVE_B))
    print("            cave C       0x%08X  %3d bytes (zone 0x%X): %s"
          % (CAVE_C, len(LIB_BLOB), CAVE_C_END - CAVE_C, ", ".join(LIB)))
    print("  tags    : table of %d entries (%d bytes, GetMem on first use), pointer at BSS 0x%08X"
          % (TAG_N, TAG_BYTES, TAG_CELL))
    print("  reserved: 0x%08X..0x%08X (%d bytes, zeroed by --undo)"
          % (CAVE_LO, CAVE_HI - 1, CAVE_HI - CAVE_LO))
    print("  PIC     : anchor 0x%08X, map delta disp 0x%08X"
          % (anchor, (MAPPTR - anchor) & 0xFFFFFFFF))
    print()

    if args.dis:
        disasm(ca, CAVE_A, "cave_execai @0x%08X" % CAVE_A)
        print()
        disasm(cb, CAVE_B, "cave_msgproc @0x%08X" % CAVE_B)
        print()
        for name, va in sorted(LIB.items(), key=lambda kv: kv[1]):
            nxt = min([v for v in LIB.values() if v > va] + [CAVE_C + len(LIB_BLOB)])
            disasm(LIB_BLOB[va - CAVE_C:nxt - CAVE_C].rstrip(b"\x00") if name != "lib_delta"
                   else LIB_BLOB[va - CAVE_C:nxt - CAVE_C], va, "%s @0x%08X" % (name, va))
        return 0

    if args.undo:
        return undo(data, edits)

    safety_checks(data)
    pristine_check()
    print()

    # ---- verify-before-write
    states = []
    for va, ob, nb, lbl, kind in edits:
        cur = bytes(data[off(va):off(va) + len(nb)])
        st = "original" if cur == ob else "applied" if cur == nb else "FOREIGN"
        states.append((st, va, lbl, kind, cur, ob, nb))

    slot_states = [s for s in states if s[3] == "slot"]
    hook_states = [s for s in states if s[3] == "hook"]
    # ANY slot pointing at our cave proves the cave memory is ours -- nothing else in
    # the tree can produce that value. Using "any" rather than "all" also lets a
    # half-written state (a crash mid-apply) be completed instead of falsely reported
    # as a squatter.
    ours = any(s[0] == "applied" for s in slot_states)

    for st, va, lbl, kind, cur, ob, nb in states:
        extra = ""
        if kind == "cave" and st == "FOREIGN":
            extra = " (ours, contents differ -> rewrite in place)" if ours else \
                    " (%d non-zero bytes)" % sum(1 for b in cur if b)
        print("  %-9s 0x%08X  %s%s" % (st, va, lbl, extra))

    # a FOREIGN slot is always fatal
    bad_slots = [s for s in slot_states + hook_states if s[0] == "FOREIGN"]
    if bad_slots:
        print()
        for st, va, lbl, kind, cur, ob, nb in bad_slots:
            print("  0x%08X %s: found %s, want %s (vanilla) or %s (ours)"
                  % (va, lbl, cur[::-1].hex(), ob[::-1].hex(), nb[::-1].hex()))
        sys.exit("ABORT: a VMT slot we need is owned by something else.")

    # a FOREIGN cave is fatal unless the slots prove the caves are ours (a re-tune)
    bad_caves = [s for s in states if s[3] == "cave" and s[0] == "FOREIGN"]
    if bad_caves and not ours:
        sys.exit("ABORT: cave zone 0x%08X is not zero and the VMT slots do not point at "
                 "us -- someone else owns that memory." % bad_caves[0][1])

    # the unused remainder of the reservation must still be untouched
    tail = bytes(data[off(CAVE_C_END):off(CAVE_HI)])
    if set(tail) not in ({0}, set()):
        sys.exit("ABORT: 0x%08X..0x%08X (our reserved tail) is not zero."
                 % (CAVE_C_END, CAVE_HI - 1))

    planned = [(va, nb, lbl) for st, va, lbl, kind, cur, ob, nb in states if cur != nb]
    print()
    if not planned:
        print("Nothing to do: already applied, and both caves match this build byte-for-byte.")
        return 0

    retune = ours and any(st == "FOREIGN" for st, _, _, k, _, _, _ in states if k == "cave")
    if retune:
        print("RE-TUNE: the VMT slots already point at our caves, so the cave contents")
        print("         are this script's own previous output. Rewriting them in place;")
        print("         no revert, no new backup.")
        print()
    disasm(ca, CAVE_A, "cave_execai @0x%08X" % CAVE_A)
    print()
    disasm(cb, CAVE_B, "cave_msgproc @0x%08X" % CAVE_B)
    print()

    if not args.apply:
        print("DRY RUN -- %d region(s) would be written. Re-run with --apply to commit."
              % len(planned))
        print("(Kill AoW.exe / AoWCompat.exe / AoWDevEd.exe / AoWEd.exe first -- they lock "
              "the DLL.)")
        return 0

    # ---- backup, ONLY from a file proved free of this feature
    fresh = all(s[0] == "original" for s in states)
    if fresh:
        if not os.path.exists(BAK):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(DLL, BAK)
            print("backup -> %s  (taken from a file proved free of this feature)"
                  % os.path.basename(BAK))
        else:
            print("backup already exists, left as-is: %s" % os.path.basename(BAK))
    else:
        print("NO backup taken: the DLL already carries this feature, so it is this "
              "script's own output, not an unpatched reference. Revert with --undo.")

    for va, nb, lbl in planned:
        data[off(va):off(va) + len(nb)] = nb
    write(data)

    print("APPLIED: %d region(s) written%s." % (len(planned), " (re-tune)" if retune else ""))
    print()
    print("Now run:  python \"Modding Resources/re_tools/rng_audit.py\" --owners")
    print("          (this feature must add no RNG site)")
    print("Revert :  python build_scripts/build_ai_sitesearch.py --undo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
