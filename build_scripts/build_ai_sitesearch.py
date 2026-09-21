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
  3. strength gate -- mint only when 3*S_army >= 2*S_def; undefended always mints.
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
  7. ladder, then MAX-combine into [rec+0] ONLY.  [rec+8] and [rec+0xC] are the
     AI's gold/mana cost fields -- writing them corrupts its economics.

     S_def = AoWE.TUnitList.GetStrength @0x55783300 (eax=[site+0x34], dl=0)
     S_grp = AoWE.TAIGroupControl.GetStrengthMax @0x557389D4 (eax=gc, dx=1)

        S_def == 0           ->  100    (free loot, city-tier draw)
        2*S_grp <  3*S_def   ->  nothing at all  (no straggler gathering)
        S_grp   >= 10*S_def  ->  100
        S_grp   >=  5*S_def  ->   75
        S_grp   >=  3*S_def  ->   45
        S_grp   >=  2*S_def  ->   30
        else (>= 1.5x)       ->   15

     Both sides use the same engine metric, so the ladder is a pure RATIO and is
     scale-free: Ziggurat's stat doubling moves S_grp and S_def together.  Do NOT
     rescale it.  For reference, a neutral mine advertises 0x32 = 50
     (Mine.TMine.UpdateAITarget @0x557B44ED).

Both rosters are TArmy instances, so TUnitList.GetStrength applies to both:
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
  TUnitList.GetStrength          @0x55783300   push ebx,esi,edi,ebp / pop
  TAIGroupControl.GetStrengthMax @0x557389D4   push esi / pop  (ecx destroyed)
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
Neither cave draws.  Every function they call is RNG-free (CanSearch,
GetStrength, GetStrengthMax, CreateTE, SetupTE, GetTokenControl, GetTerrain,
TStructure.MapFieldMsgProc).  The search's own rolls happen later inside
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
* .reloc: nothing is displaced.  Only VMT slots are rewritten, and all 21 slots
  involved were verified to carry HIGHLOW relocs which stay valid because both
  new targets are in-image VAs.  The 8 KB cave reservation contains no relocs.
* Cave zone 0x55834000..0x55836000, verified all-zero in BOTH the live DLL and
  Modding Resources/AoWEPACK_original_backup.dpl; the last non-zero byte anywhere
  in CODE is at 0x55832328 and CODE runs to 0x558E7918.  No build_scripts/*.py
  references any VA in 0x55834000..0x5583FFFF.
* Backup AoWEPACK.dpl.pre-aisitesearch is taken ONLY when the file is proved to
  be free of this feature (all 14 slots vanilla AND both cave zones zero).  It is
  never taken on --undo and never on a re-tune, because in both cases the file on
  disk is this script's own previous output, not an unpatched reference.
* --undo is surgical: restores the slots we own and zeroes the reservation.
  It touches no backup, so features applied later survive.

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
LIST_STRENGTH    = 0x55783300   # AoWE.TUnitList.GetStrength(eax=list, dl=kind) -> eax
GC_STRENGTHMAX   = 0x557389D4   # AoWE.TAIGroupControl.GetStrengthMax(eax=gc, dx=mask) -> eax
GETTOKENCTL      = 0x5570372C   # thunk -> Network.dpl!NetworkE.TTokenManager.GetTokenControl
GETTERRAIN       = 0x55701C8C   # thunk -> HSEPack.dpl!HSEngine.TTerrainList.GetTerrain
MAPPTR           = 0x558E9494   # -> ptr -> the TAoWHSMap object
TAG_ARMYHS       = 0x20217      # GetObjectOfType tag for TArmyHS

VMT_MSGPROC      = 0x0CC        # MapFieldMsgProc
VMT_CREATETE     = 0x160        # TStructure.CreateTE
VMT_SETUPTE      = 0x164        # TStructure.SetupTE
VMT_EXECUTEAI    = 0x1C0        # TStructure.ExecuteAI
VMT_UPDATEAI     = 0x1C4        # TStructure.UpdateAITarget -- left as the stub
VMT_GETEXPLORED  = 0x1F0        # GetExplored  (1 = looted/cleared)
VMT_FINDCHILD    = 0x080        # TMapField.FindOwnedChild, on the field at [site+4]
VMT_TOKEN_SUBMIT = 0x010        # token control: submit a TE
VMT_TE_RELEASE   = 0x02C        # TE: release

FLD_DEFENDERS    = 0x34         # site -> TDefendersArmy (TArmy)
FLD_ARMY         = 0x1C         # TArmyHS -> TArmy
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

# ladder / gate constants (ratios -- scale-free, do NOT rescale)
PRI_FREE   = 100                # undefended, unlooted
PRI_10X    = 100
PRI_5X     = 75
PRI_3X     = 45
PRI_2X     = 30
PRI_1_5X   = 15

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
        mov   ebx, eax                     ; ebx = site  (edx keeps the player in dl)
        call  0x%(CANSEARCH)X              ; loot left AND our army is standing on it
        test  al, al
        je    _out

        mov   eax, [ebx + 0x%(FLD_DEFENDERS)X]
        test  eax, eax
        je    _mint
        mov   ecx, [eax + 8]               ; inner TList
        test  ecx, ecx
        je    _mint
        xor   edx, edx                     ; kind 0
        call  0x%(LIST_STRENGTH)X
        mov   edi, eax                     ; edi = S_def
        test  edi, edi
        jle   _mint                        ; undefended -> always search

        mov   edx, 0x%(TAG_ARMYHS)X
        mov   eax, [ebx + 4]               ; the TMapField
        mov   ecx, [eax]
        call  dword ptr [ecx + 0x%(VMT_FINDCHILD)X]   ; FindOwnedChild (preserves edi)
        test  eax, eax
        je    _out
        mov   eax, [eax + 0x%(FLD_ARMY)X]  ; TArmyHS -> TArmy
        test  eax, eax
        je    _out
        mov   ecx, [eax + 8]
        test  ecx, ecx
        je    _out
        xor   edx, edx
        call  0x%(LIST_STRENGTH)X          ; eax = S_army
        lea   ecx, [eax + eax*2]           ; 3 * S_army
        lea   edx, [edi + edi]             ; 2 * S_def
        cmp   ecx, edx
        jl    _out                         ; too weak -> no suicide search

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
        pop   edi
        pop   esi
        pop   ebx
    _no:
        xor   eax, eax
        ret
    """ % globals()

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

        mov   eax, esi
        mov   edx, [eax]
        call  dword ptr [edx + 0x%(VMT_GETEXPLORED)X]
        test  al, al
        jne   _done                        ; already looted

        mov   eax, [esi + 0x%(FLD_DEFENDERS)X]
        test  eax, eax
        je    _undef
        mov   ecx, [eax + 8]
        test  ecx, ecx
        je    _undef
        xor   edx, edx
        call  0x%(LIST_STRENGTH)X
        mov   ebp, eax                     ; ebp = S_def
        test  ebp, ebp
        jle   _undef

        mov   eax, [edi + 0x10]            ; the asking TAIGroupControl
        test  eax, eax
        je    _done
        mov   dx, 1                        ; kind-0 bit
        call  0x%(GC_STRENGTHMAX)X         ; eax = S_grp

        lea   ecx, [ebp + ebp*2]           ; 3 * S_def
        lea   edx, [eax + eax]             ; 2 * S_grp
        cmp   edx, ecx
        jl    _done                        ; < 1.5x -> contribute nothing

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
    """ % globals()
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
        LIST_STRENGTH: "TUnitList.GetStrength",
        GC_STRENGTHMAX: "TAIGroupControl.GetStrengthMax",
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
    if CAVE_HI > CODE_END:
        sys.exit("ERROR: cave reservation runs past the end of CODE")

    pad_a = ca + b"\x00" * (CAVE_A_END - CAVE_A - len(ca))
    pad_b = cb + b"\x00" * (CAVE_B_END - CAVE_B - len(cb))

    edits = [
        (CAVE_A, b"\x00" * len(pad_a), pad_a, "cave_execai  (VMT +0x1C0)", "cave"),
        (CAVE_B, b"\x00" * len(pad_b), pad_b, "cave_msgproc (VMT +0x0CC)", "cave"),
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
    slots = [(va, ob, nb, lbl) for va, ob, nb, lbl, k in edits if k == "slot"]
    owned = [(va, ob, nb, lbl) for va, ob, nb, lbl in slots
             if bytes(data[off(va):off(va) + 4]) == nb]
    foreign = [(va, lbl) for va, ob, nb, lbl in slots
               if bytes(data[off(va):off(va) + 4]) not in (ob, nb)]
    if foreign:
        sys.exit("ABORT: %d VMT slot(s) hold bytes that are neither vanilla nor ours:\n  %s"
                 % (len(foreign), "\n  ".join("0x%08X %s" % f for f in foreign)))
    if not owned:
        print("Nothing to undo: no VMT slot points at our caves.")
        return 0

    # never zero a neighbour's bytes: outside our two caves the reservation must
    # already be zero
    tail = bytes(data[off(CAVE_B_END):off(CAVE_HI)])
    if set(tail) not in ({0}, set()):
        sys.exit("ABORT: 0x%08X..0x%08X inside our reservation is not zero -- refusing "
                 "to wipe it blind." % (CAVE_B_END, CAVE_HI - 1))

    print("UNDO -- restoring %d VMT slot(s) and zeroing 0x%08X..0x%08X (%d bytes):"
          % (len(owned), CAVE_LO, CAVE_HI - 1, CAVE_HI - CAVE_LO))
    for va, ob, nb, lbl in owned:
        print("   0x%08X  %s  -> %s" % (va, lbl, ob[::-1].hex()))
        data[off(va):off(va) + 4] = ob
    data[off(CAVE_LO):off(CAVE_HI)] = b"\x00" * (CAVE_HI - CAVE_LO)
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
    print("  reserved: 0x%08X..0x%08X (%d bytes, zeroed by --undo)"
          % (CAVE_LO, CAVE_HI - 1, CAVE_HI - CAVE_LO))
    print("  PIC     : anchor 0x%08X, map delta disp 0x%08X"
          % (anchor, (MAPPTR - anchor) & 0xFFFFFFFF))
    print()

    if args.dis:
        disasm(ca, CAVE_A, "cave_execai @0x%08X" % CAVE_A)
        print()
        disasm(cb, CAVE_B, "cave_msgproc @0x%08X" % CAVE_B)
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
    bad_slots = [s for s in slot_states if s[0] == "FOREIGN"]
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
    tail = bytes(data[off(CAVE_B_END):off(CAVE_HI)])
    if set(tail) not in ({0}, set()):
        sys.exit("ABORT: 0x%08X..0x%08X (our reserved tail) is not zero."
                 % (CAVE_B_END, CAVE_HI - 1))

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
