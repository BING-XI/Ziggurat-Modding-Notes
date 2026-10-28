#!/usr/bin/env python
r"""
build_awaken_volcano.py -- Awaken Volcano, the Earth/Fire dual tier-3 world-map ritual.  AoWEPACK.dpl.
Owner's design 2026-10-25 (05-spells-added.md, "Earth/Fire -- agreed design"): 40 mana, upkeep 5
from the cast until the spreading ends, range 12, Ritualist; the AI never casts it (the
TGlobalTargetSpell family has no AI).

THE SPELL (id 85) -- a TLevelTerrain INSTANCE (classref cell 0x5579D2B8, Create 0x5579F1D0), like
  Surtr's Chasm, registered at 0x557A2481 (a `call RegisterSpell` in RegisterGlobalTargetSpells,
  replayed first).  Mana 40, research 240 (the single tier-4 figure), upkeep 5 (the book's figure;
  the ritual record below charges it), sphere 7 (dual), tier 3.  Spells.pfs record 95:
  build_awaken_volcano_pfs.py.  build_surtrs_chasm.py's TLevelTerrain caves send id 85 here:
  cave_vt and cave_vts to VOLC_VT, cave_rad to the one-hex cursor, cave_exec to VOLC_EXEC.

THE TARGET (VOLC_VT, eax = spell, edx = field -> al): overlay 0 (mountain), and a child of the field
  is a TMountainMO (ClassID 0x20168) that COVERS this hex (its TTerrainList slot at GetHNofHS holds
  a terrain >= 0; overhang hexes belong to no mountain).  The mountain covers 4 or 9 hexes
  (TTerrainList.UsedTerrain; the game has only 1-, 4- and 9-hex mountains, and 1-hex ones are
  refused), is not a volcano already (a volcano's list has 65 slots), and a volcano resource with
  the same covered slots exists: a TMountainMOR (0x20169) in [[AoWHSSet+0x24]+8] with terrain 5 and
  65 slots -- MOUNTAIN\WL_VOLCS.ILB covers 4 hexes, WL_VOLCL.ILB 9.  Level Terrain's own tests
  follow (no structure, no army).

THE CAST (VOLC_EXEC, inside TLevelTerrainTE.Process after PlayDefaultEffects, before the mana):
  - the mountain object swaps its resource in place, as TTerrainMO.ChangeTerrain does: RandSeed from
    the synced map Random, RemoveFromMap (+0xB0), SetResource (+0x110), SetOwner (+8), PlaceOnMap
    (+0xAC), vanilla's [[[V+0x18]+0x3C]+0x30] line, then TMultiHexMO.OverrideTerrain, which writes
    Wasteland and overlay 0 into every covered hex and fires TerrainChanged.  The object saves its
    resource id, so the volcano reloads as a volcano.
  - the ritual record: a TSpellWardEnchantment (classref 0x557EF574, Create 0x557F374C) re-typed by
    TGlobalEnchantment.Setup 0x5577DA8C to REC_TYPE (>= 8: CanActivate never refuses it; the
    active-set SetElem drops it, range-checked), name "Awaken Volcano", upkeep 5 (+0x20, which the
    ward's VMT +0x50 returns and GetEnchantmentUpkeep sums).  Cast (VMT +0x70, DL = the caster,
    [TE+0x18]) adds it to the global magic list; Release (+0x2C) drops our reference.  Its state
    follows the 0x24-byte TGlobalEnchantment in the instance, grown to INST: level, d3 delay
    (synced), 10 spill turns, and a list of hexes -- the volcano's covered hexes (dir 0), then each
    lava hex with the HN it was reached in.  Saved by ReadWrite as one block (id RW_ID).
  - a glitter marker on every volcano hex.

EACH TURN (VOLC_MSG, the record's MsgProc slot; message 0x20020003 to the caster comes after upkeep,
  as for Flood): the delay counts down; on the turn it reaches 0 and the 9 after it, the volcano
  spills d2 hexes.  Each hex is picked by weight among the land hexes touching the volcano or this
  ritual's lava: STRAIGHT_W where it continues a lava hex in the direction that hex was reached,
  else OTHER_W.  Land = Grass, Desert, Snow, Steppe, Wasteland, Dirt; no mountain (overlay 0), no
  structure or city.  Per picked hex: a road (overlay 4/5) is freed as Flood frees it,
  THSMap.ClearTerrain burns forests and hills, the units are handled (below), ChangeTerrain (VMT
  +0xD0) makes it Lava, Snow beside it becomes Steppe, Ice Water and underground Ice underground
  Water (an army that cannot stand on the result vetoes it), and it gets a glitter marker.  A hex
  the map refuses keeps a flag in its entry and spreads nothing.  After the 10th spill turn the
  record deactivates itself (TENode.SendMsg walks the list downwards, so the removal is safe).
UNITS ON NEW LAVA (before the terrain changes): a unit that can stand on Lava
  (TAbstractUnit.ValidTerrain(9, -1)) stays, and the whole party stays if its transporter can.
  Every other unit loses d20 HP (no to-hit roll), halved rounding down by Fire Protection
  (GetProtectionTypes bit 0) and x1.5 rounding up by Fire Weakness (ability 0xB3, VMT +0x148), the
  two cancelling (owner 2026-10-25, build_weakness.py's rule); TArmy.Validate then kills the fallen.
  Each survivor tries the six neighbours in a synced shuffled order, skipping this ritual's hexes
  and lava: it joins a friendly party there (same player, not moving, TArmy.AddUnitSelection's
  room check) where it can stand or the party has a transporter (a ship: owner 2026-10-25), or
  forms a new party (TArmyHS.Create, SetPlayer, AddUnitSelection, PlaceEx, Activate, as the vanilla
  split 0x5578E9E0 does) on an empty hex with no owner and no structure where it can stand.  A
  unit with no hex is set to 0 HP and dies at the next Validate.  The party is held open with
  BeginUpdate while units leave and re-fetched through the field afterwards.
THE END -- whatever ends the record (the last spill turn, unpaid upkeep, the owner removing it,
  Disjunction, the caster's defeat) runs Deactivate (VMT +0x60), whose hook first removes this
  ritual's glitter markers.  Lava and volcano stay.
GLITTER -- a TFrozenWaterHS marker, as Freeze Water places them; its Show draws the shimmer.
  Stamp: +0x0C = 0x7F countdown, +0x0D = 0xFF owner (no player's turn, so NewTurn never counts it
  down; also how this script tells its markers from others), +0x0E = +0x0F = the hex's terrain
  (Grip of Winter's caves read these as "restore this terrain / I set this terrain", so its melt,
  were it ever reached, would restore the same terrain, and its TerrainChanged cave frees the
  marker when anything else changes the hex).  Grip of Winter's Show gate hides markers with
  +0x0E set; the Show slot (0x5571485C) goes to VOLC_SHOW, which runs vanilla Show's body
  (0x55764BD6, after its prologue) for owner 0xFF and sends every other marker to the gated entry
  0x55764BD0 unchanged.

HOOKS
    reg     0x557A2481  call RegisterSpell -> call VOLC_REG
    TSpellWardEnchantment VMT 0x557EF5B4: +0x18 ReadWrite, +0x44 MsgProc, +0x60 Deactivate -> the
            entries below (.reloc kept); instance size 0x557EF598 0x24 -> INST.  Astral Ward
            (type 6) passes through every cave unchanged.
    TFrozenWaterHS VMT +0xA8 Show (0x5571485C) -> VOLC_SHOW (.reloc kept)
Entries (pinned): VT +0, EXEC +5, RW +10, MSG +15, DEACT +20, SHOW +25, REG +30.

RNG: P1 SYNCED DRAW throughout.  Cast: inside TLevelTerrainTE.Process (a token event): the RandSeed
reseed before the swap and the d3.  Turns: inside the global magic control's 0x20020003 broadcast
(TPlayerControl.NewTurn; TFloodEnchantment.NewTurn draws there too): the d2, the weighted pick,
the d20 per unit, the neighbour shuffle; ChangeTerrain reseeds RandSeed itself.  Every draw is
gated on replicated state only.  The sites are RNG_SITES (checked against the assembled core).

Slot 0x558BB000-0x558BCFFF, exclusive.  PIC (one call/pop anchor, get_anc).  Surgical --undo.

Couplings
  * build_surtrs_chasm.py dispatches id 85 into this slot (VOLC_VT, VOLC_EXEC); either can be undone
    alone (without this script spell 85 is not registered, so the dispatch is never taken).
  * build_globalench_active.py restores the active bit of every global record after a load.
  * build_blazing_moon.py chains the record's MsgProc slot in front of ENTRY["msg"].  Its entry
    there reads as this script's applied state; --apply and --undo refuse while it is there: undo
    build_blazing_moon.py first.
  * build_gripofwinter.py / build_raiseterrain_ug_earth.py own the other TFrozenWaterHS caves.

Unproven, static checks cannot reach it: the swap's redraw, the shimmer's draw order against the
volcano sprite, shunts onto hexes PlaceEx refuses, new parties of AI players (no AI group), and the
record's line in the Magic window.

    python build_scripts/build_awaken_volcano.py            dry run + state
    python build_scripts/build_awaken_volcano.py --apply
    python build_scripts/build_awaken_volcano.py --undo
    python build_scripts/build_awaken_volcano.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import run
from piccave import pic, ansistr

SPELL_ID, SPELL_NAME = 85, "Awaken Volcano"
MANA, RESEARCH, UPKEEP, SPHERE, TIER = 40, 240, 5, 7, 3
REC_TYPE = 0x56
DELAY_DIE, SPILL_TURNS, SPILL_DIE, DAMAGE_DIE = 3, 10, 2, 20
STRAIGHT_W, OTHER_W = 3, 1
FIRE_WEAKNESS = 0xB3                       # build_weakness.py
SLOT = (0x558BB000, 0x558BD000)
# the six synced draws in the assembled core (rng_audit --owners reads these literals)
RNG_SITES = {"d2": 0x558BB043, "pick": 0x558BB1DA, "d20": 0x558BB39F, "shuffle": 0x558BB4D6,
             "reseed": 0x558BB9A1, "d3": 0x558BBA40}

# record state (TGlobalEnchantment is 0x24 bytes; this block follows)
ST_LEVEL, ST_DELAY, ST_SPILLS, ST_COUNT, ST_ENT = 0x24, 0x25, 0x26, 0x27, 0x28
MAX_ENT = 32                               # 4 bytes each: x, y, dir (0 = volcano), refused flag
INST = ST_ENT + 4 * MAX_ENT                # 0xA8
BLOCK_LEN, RW_ID = INST - 0x24, 0x10
MAX_CAND = 64

# terrain
WATER, SNOW, STEPPE, WASTELAND, ICE, LAVA, CAVE_WATER, CAVE_ICE = 0, 3, 4, 5, 6, 9, 0x0A, 0x0D
LAND = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5) | (1 << 0xC)
MTN_CLASSID, MTNRES_CLASSID, VOLC_LEN = 0x20168, 0x20169, 65
MARK_COUNT, MARK_OWNER = 0x7F, 0xFF

# data cells (reached through the anchor)
AOWHSMAP, AOWHSSET = 0x558FA040, 0x558FA044
SEED_CELL = 0x558FB720               # IAT -> System.RandSeed
LT_CELL = 0x5579D2B8                 # -> TLevelTerrain
WARD_CELL = 0x557EF574               # -> TSpellWardEnchantment
FW_CELL = 0x55714774                 # -> TFrozenWaterHS
ROAD_IAT = 0x558FC0F0                # IAT -> HSEngine..TAbstractRoad
STRUCT_CELL = 0x55713BD8             # -> TStructure
ARMYHS_CELL = 0x55713360             # -> TArmyHS

# code
REGISTER_SPELL, LSTRASG = 0x55779B40, 0x55701150
LT_CREATE, WARD_CREATE = 0x5579F1D0, 0x557F374C
GE_SETUP, GE_RW, GE_DEACT, MSGPROC_THUNK = 0x5577DA8C, 0x5577DA1C, 0x5577DC3C, 0x557030F4
TEOBJ_CREATE, PLACEHX, FINDOWNEDHS = 0x55703064, 0x557025F4, 0x55701FFC
GETHNOFHS, TL_USED, OVERRIDE = 0x5570207C, 0x55701CA4, 0x5570241C
CENTERHN, GETFIELD = 0x55702694, 0x557020FC          # CenterHNtoHX(x, y, hn; var ox, oy)
GETMAPLEVEL, LEVEL_GETFIELD = 0x557020EC, 0x557020DC
CLEARTERRAIN, HAS_HS, ARMY_ON, FIELD_GETPLAYER = 0x557025DC, 0x55702004, 0x55771EB0, 0x55771C98
RANDOM = 0x5577827C
UNIT_VALIDTERRAIN, ARMY_TRANSPORTER, ARMY_VALIDATE = 0x5577FFFC, 0x5578E00C, 0x5578CF7C
ARMY_GETUNIT, ADDUNITSEL = 0x5578309C, 0x5578E6B4
ARMYHS_CREATE, SETPLAYER, PLACEEX = 0x557908BC, 0x5578D690, 0x55791F58
PLACE_FLAGS = 3                      # the vanilla split's PlaceEx set (byte at 0x5578EA98)
BEGINUPD, ENDUPD, OBJ_FREE = 0x55703284, 0x5570328C, 0x557010B8
FW_SHOW, FW_BODY = 0x55764BD0, 0x55764BD6

# hook sites
REG_SITE = 0x557A2481
WARD_VMT = 0x557EF5B4
SLOT_RW, SLOT_MSG, SLOT_DEACT = WARD_VMT + 0x18, WARD_VMT + 0x44, WARD_VMT + 0x60
WARD_INST = WARD_VMT - 0x1C
FW_SHOW_SLOT = 0x5571485C
ENTRIES = ("vt", "exec", "rw", "msg", "deact", "show", "reg")
ENTRY = {n: SLOT[0] + 5 * i for i, n in enumerate(ENTRIES)}
VOLC_VT, VOLC_EXEC = ENTRY["vt"], ENTRY["exec"]


def build_core(va):
    """One blob: the seven pinned entries, then the routines.  ebx = the anchor (get_anc) in every
    routine that reads a data cell; esi = the record wherever its state is read.  step's frame
    (ebp): +0 picks left, +4 first new entry, +8 candidates, +0xC total weight, +0x10 entry,
    +0x14 HN, +0x18/+0x1C candidate x/y, +0x24 lava loop, +0x28/+0x2C lava x/y, +0x30 its field,
    +0x34 the party, +0x38 unit index, +0x3C shuffle/try index, +0x40 the HN order (6 bytes),
    +0x48 a new party's HS, +0x4C neighbour field, +0x50/+0x54 neighbour x/y, +0x58 the party
    there, +0x5C unit count, +0x60 melt HN, +0x64 damage, +0x68 Fire Protection,
    +0x100 candidates (x | y << 8 | HN << 16 | weight << 24)."""
    src = f"""
        jmp  e_vt
        jmp  e_exec
        jmp  e_rw
        jmp  e_msg
        jmp  e_deact
        jmp  e_show
        jmp  e_reg

    step:
        push ebp
        push edi
        sub  esp, 0x200
        mov  ebp, esp
        cmp  byte ptr [esi + {ST_DELAY:#x}], 0
        je   st_spill
        dec  byte ptr [esi + {ST_DELAY:#x}]
        jne  st_ret
    st_spill:
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edx, {SPILL_DIE}
        call {RANDOM:#x}
        inc  eax
        mov  dword ptr [ebp], eax
        movzx eax, byte ptr [esi + {ST_COUNT:#x}]
        mov  dword ptr [ebp + 4], eax
    st_pick:
        cmp  dword ptr [ebp], 0
        je   st_lava
        call choose
        test al, al
        je   st_lava
        dec  dword ptr [ebp]
        jmp  st_pick
    st_lava:
        mov  eax, dword ptr [ebp + 4]
        mov  dword ptr [ebp + 0x24], eax
    st_lv:
        movzx eax, byte ptr [esi + {ST_COUNT:#x}]
        cmp  dword ptr [ebp + 0x24], eax
        jge  st_done
        mov  ecx, dword ptr [ebp + 0x24]
        movzx eax, byte ptr [esi + ecx*4 + {ST_ENT:#x}]
        movzx edx, byte ptr [esi + ecx*4 + {ST_ENT + 1:#x}]
        call lava
        test al, al
        jne  st_lvok
        mov  ecx, dword ptr [ebp + 0x24]
        mov  byte ptr [esi + ecx*4 + {ST_ENT + 3:#x}], 1
    st_lvok:
        inc  dword ptr [ebp + 0x24]
        jmp  st_lv
    st_done:
        dec  byte ptr [esi + {ST_SPILLS:#x}]
        jne  st_ret
        add  esp, 0x200
        pop  edi
        pop  ebp
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x60]
        ret
    st_ret:
        add  esp, 0x200
        pop  edi
        pop  ebp
        ret

    choose:
        mov  dword ptr [ebp + 8], 0
        mov  dword ptr [ebp + 0xc], 0
        movzx eax, byte ptr [esi + {ST_COUNT:#x}]
        cmp  eax, {MAX_ENT}
        jae  ch_none
        mov  dword ptr [ebp + 0x10], 0
    ch_e:
        movzx eax, byte ptr [esi + {ST_COUNT:#x}]
        cmp  dword ptr [ebp + 0x10], eax
        jge  ch_pick
        mov  ecx, dword ptr [ebp + 0x10]
        cmp  byte ptr [esi + ecx*4 + {ST_ENT + 3:#x}], 0
        jne  ch_enext
        mov  dword ptr [ebp + 0x14], 1
    ch_hn:
        mov  ecx, dword ptr [ebp + 0x10]
        movzx eax, byte ptr [esi + ecx*4 + {ST_ENT:#x}]
        movzx edx, byte ptr [esi + ecx*4 + {ST_ENT + 1:#x}]
        mov  ecx, dword ptr [ebp + 0x14]
        call nb
        mov  dword ptr [ebp + 0x18], eax
        mov  dword ptr [ebp + 0x1c], edx
        call in_ent
        test al, al
        jne  ch_next
        mov  eax, dword ptr [ebp + 0x18]
        mov  edx, dword ptr [ebp + 0x1c]
        call valid_lava
        test al, al
        je   ch_next
        mov  ecx, dword ptr [ebp + 0x10]
        movzx eax, byte ptr [esi + ecx*4 + {ST_ENT + 2:#x}]
        mov  edi, {OTHER_W}
        test eax, eax
        je   ch_w
        cmp  eax, dword ptr [ebp + 0x14]
        jne  ch_w
        mov  edi, {STRAIGHT_W}
    ch_w:
        mov  eax, dword ptr [ebp + 0x18]
        and  eax, 0xff
        mov  edx, dword ptr [ebp + 0x1c]
        and  edx, 0xff
        shl  edx, 8
        or   eax, edx
        mov  edx, dword ptr [ebp + 0x14]
        shl  edx, 16
        or   eax, edx
        xor  ecx, ecx
    ch_find:
        cmp  ecx, dword ptr [ebp + 8]
        jge  ch_add
        mov  edx, dword ptr [ebp + ecx*4 + 0x100]
        cmp  dx, ax
        je   ch_have
        inc  ecx
        jmp  ch_find
    ch_have:
        shr  edx, 24
        cmp  edi, edx
        jbe  ch_next
        sub  edi, edx
        add  dword ptr [ebp + 0xc], edi
        add  edi, edx
        shl  edi, 24
        or   eax, edi
        mov  dword ptr [ebp + ecx*4 + 0x100], eax
        jmp  ch_next
    ch_add:
        cmp  ecx, {MAX_CAND}
        jge  ch_next
        add  dword ptr [ebp + 0xc], edi
        shl  edi, 24
        or   eax, edi
        mov  dword ptr [ebp + ecx*4 + 0x100], eax
        inc  dword ptr [ebp + 8]
    ch_next:
        inc  dword ptr [ebp + 0x14]
        cmp  dword ptr [ebp + 0x14], 7
        jl   ch_hn
    ch_enext:
        inc  dword ptr [ebp + 0x10]
        jmp  ch_e
    ch_pick:
        mov  edx, dword ptr [ebp + 0xc]
        test edx, edx
        je   ch_none
        mov  eax, dword ptr [ebx + {{MAP}}]
        call {RANDOM:#x}
        xor  ecx, ecx
    ch_walk:
        mov  edx, dword ptr [ebp + ecx*4 + 0x100]
        shr  edx, 24
        cmp  eax, edx
        jb   ch_got
        sub  eax, edx
        inc  ecx
        cmp  ecx, dword ptr [ebp + 8]
        jl   ch_walk
        jmp  ch_none
    ch_got:
        mov  edi, dword ptr [ebp + ecx*4 + 0x100]
        mov  eax, edi
        and  eax, 0xff
        mov  edx, edi
        shr  edx, 8
        and  edx, 0xff
        mov  ecx, edi
        shr  ecx, 16
        and  ecx, 0xff
        call add_ent
        ret
    ch_none:
        xor  eax, eax
        ret

    lava:
        mov  dword ptr [ebp + 0x28], eax
        mov  dword ptr [ebp + 0x2c], edx
        call gf
        test eax, eax
        je   lv_fail
        mov  dword ptr [ebp + 0x30], eax
        mov  cl, byte ptr [eax + 0x15]
        sub  cl, 4
        cmp  cl, 2
        jae  lv_clear
        mov  edx, dword ptr [ebx + {{ROAD}}]
        call {FINDOWNEDHS:#x}
        test eax, eax
        je   lv_clear
        mov  dl, 1
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx - 4]
    lv_clear:
        movsx eax, byte ptr [esi + {ST_LEVEL:#x}]
        push eax
        push 0
        push -1
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  ecx, dword ptr [ebp + 0x2c]
        mov  edx, dword ptr [ebp + 0x28]
        call {CLEARTERRAIN:#x}
        call shunt
        push dword ptr [ebp + 0x2c]
        movsx eax, byte ptr [esi + {ST_LEVEL:#x}]
        push eax
        push 0
        push {LAVA}
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edi, dword ptr [eax]
        mov  ecx, dword ptr [ebp + 0x28]
        xor  edx, edx
        call dword ptr [edi + 0xd0]
        mov  eax, dword ptr [ebp + 0x30]
        cmp  byte ptr [eax + 0x14], {LAVA}
        jne  lv_fail
        mov  eax, dword ptr [ebp + 0x28]
        mov  edx, dword ptr [ebp + 0x2c]
        mov  cl, {LAVA}
        call marker_add
        mov  dword ptr [ebp + 0x60], 1
    lv_melt:
        mov  eax, dword ptr [ebp + 0x28]
        mov  edx, dword ptr [ebp + 0x2c]
        mov  ecx, dword ptr [ebp + 0x60]
        call nb
        mov  dword ptr [ebp + 0x50], eax
        mov  dword ptr [ebp + 0x54], edx
        call gf
        test eax, eax
        je   lv_mnext
        mov  cl, byte ptr [eax + 0x14]
        mov  edx, {STEPPE}
        cmp  cl, {SNOW}
        je   lv_mdo
        mov  edx, {WATER}
        cmp  cl, {ICE}
        je   lv_mdo
        mov  edx, {CAVE_WATER}
        cmp  cl, {CAVE_ICE}
        jne  lv_mnext
    lv_mdo:
        push dword ptr [ebp + 0x54]
        movsx eax, byte ptr [esi + {ST_LEVEL:#x}]
        push eax
        push 0
        push edx
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edi, dword ptr [eax]
        mov  ecx, dword ptr [ebp + 0x50]
        xor  edx, edx
        call dword ptr [edi + 0xd0]
    lv_mnext:
        inc  dword ptr [ebp + 0x60]
        cmp  dword ptr [ebp + 0x60], 7
        jl   lv_melt
        mov  al, 1
        ret
    lv_fail:
        xor  eax, eax
        ret

    shunt:
        mov  eax, dword ptr [ebp + 0x30]
        call {ARMY_ON:#x}
        test eax, eax
        je   sh_ret
        mov  eax, dword ptr [eax + 0x1c]
        test eax, eax
        je   sh_ret
        mov  dword ptr [ebp + 0x34], eax
        mov  dl, 0xff
        call {ARMY_TRANSPORTER:#x}
        test eax, eax
        je   sh_dmg
        mov  dl, {LAVA}
        mov  cl, 0xff
        call {UNIT_VALIDTERRAIN:#x}
        test al, al
        jne  sh_ret
    sh_dmg:
        mov  eax, dword ptr [ebp + 0x34]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  dword ptr [ebp + 0x5c], eax
        mov  dword ptr [ebp + 0x38], 0
    sh_d1:
        mov  eax, dword ptr [ebp + 0x38]
        cmp  eax, dword ptr [ebp + 0x5c]
        jge  sh_validate
        mov  edx, eax
        mov  eax, dword ptr [ebp + 0x34]
        call {ARMY_GETUNIT:#x}
        mov  edi, eax
        mov  dl, {LAVA}
        mov  cl, 0xff
        call {UNIT_VALIDTERRAIN:#x}
        test al, al
        jne  sh_d1n
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edx, {DAMAGE_DIE}
        call {RANDOM:#x}
        inc  eax
        mov  dword ptr [ebp + 0x64], eax
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xf0]
        and  eax, 1
        mov  dword ptr [ebp + 0x68], eax
        mov  eax, edi
        mov  edx, {FIRE_WEAKNESS:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        setne al
        movzx eax, al
        mov  ecx, dword ptr [ebp + 0x64]
        cmp  eax, dword ptr [ebp + 0x68]
        je   sh_d2
        test eax, eax
        jne  sh_weak
        shr  ecx, 1
        jmp  sh_d2
    sh_weak:
        lea  ecx, [ecx + ecx*2 + 1]
        shr  ecx, 1
    sh_d2:
        push ecx
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        movzx eax, al
        pop  ecx
        sub  eax, ecx
        jge  sh_d3
        xor  eax, eax
    sh_d3:
        mov  edx, eax
        mov  eax, edi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xe4]
    sh_d1n:
        inc  dword ptr [ebp + 0x38]
        jmp  sh_d1
    sh_validate:
        mov  eax, dword ptr [ebp + 0x34]
        call {ARMY_VALIDATE:#x}
        mov  eax, dword ptr [ebp + 0x30]
        call {ARMY_ON:#x}
        test eax, eax
        je   sh_ret
        mov  eax, dword ptr [eax + 0x1c]
        test eax, eax
        je   sh_ret
        mov  dword ptr [ebp + 0x34], eax
        call {BEGINUPD:#x}
    sh_find:
        mov  eax, dword ptr [ebp + 0x34]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov  dword ptr [ebp + 0x5c], eax
        mov  dword ptr [ebp + 0x38], 0
    sh_f1:
        mov  eax, dword ptr [ebp + 0x38]
        cmp  eax, dword ptr [ebp + 0x5c]
        jge  sh_end
        mov  edx, eax
        mov  eax, dword ptr [ebp + 0x34]
        call {ARMY_GETUNIT:#x}
        mov  edi, eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        test al, al
        je   sh_f1n
        mov  eax, edi
        mov  dl, {LAVA}
        mov  cl, 0xff
        call {UNIT_VALIDTERRAIN:#x}
        test al, al
        jne  sh_f1n
        call move_one
        test al, al
        jne  sh_find
        mov  eax, edi
        xor  edx, edx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xe4]
        jmp  sh_find
    sh_f1n:
        inc  dword ptr [ebp + 0x38]
        jmp  sh_f1
    sh_end:
        mov  eax, dword ptr [ebp + 0x34]
        call {ENDUPD:#x}
        mov  eax, dword ptr [ebp + 0x30]
        call {ARMY_ON:#x}
        test eax, eax
        je   sh_ret
        mov  eax, dword ptr [eax + 0x1c]
        test eax, eax
        je   sh_ret
        call {ARMY_VALIDATE:#x}
    sh_ret:
        ret

    move_one:
        mov  dword ptr [ebp + 0x40], 0x04030201
        mov  dword ptr [ebp + 0x44], 0x00000605
        mov  dword ptr [ebp + 0x3c], 5
    mo_shuf:
        mov  edx, dword ptr [ebp + 0x3c]
        inc  edx
        mov  eax, dword ptr [ebx + {{MAP}}]
        call {RANDOM:#x}
        mov  ecx, dword ptr [ebp + 0x3c]
        mov  dl, byte ptr [ebp + ecx + 0x40]
        mov  dh, byte ptr [ebp + eax + 0x40]
        mov  byte ptr [ebp + ecx + 0x40], dh
        mov  byte ptr [ebp + eax + 0x40], dl
        dec  dword ptr [ebp + 0x3c]
        jne  mo_shuf
    mo_try:
        cmp  dword ptr [ebp + 0x3c], 6
        jge  mo_fail
        mov  ecx, dword ptr [ebp + 0x3c]
        movzx ecx, byte ptr [ebp + ecx + 0x40]
        mov  eax, dword ptr [ebp + 0x28]
        mov  edx, dword ptr [ebp + 0x2c]
        call nb
        mov  dword ptr [ebp + 0x50], eax
        mov  dword ptr [ebp + 0x54], edx
        call in_ent
        test al, al
        jne  mo_next
        mov  eax, dword ptr [ebp + 0x50]
        mov  edx, dword ptr [ebp + 0x54]
        call gf
        test eax, eax
        je   mo_next
        mov  dword ptr [ebp + 0x4c], eax
        cmp  byte ptr [eax + 0x14], {LAVA}
        je   mo_next
        call {ARMY_ON:#x}
        test eax, eax
        je   mo_new
        mov  eax, dword ptr [eax + 0x1c]
        test eax, eax
        je   mo_next
        mov  dword ptr [ebp + 0x58], eax
        mov  edx, dword ptr [ebp + 0x34]
        mov  cl, byte ptr [edx + 0x12]
        cmp  cl, byte ptr [eax + 0x12]
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
        call mo_mask
        mov  edx, dword ptr [ebp + 0x34]
        mov  eax, dword ptr [ebp + 0x58]
        call {ADDUNITSEL:#x}
        test al, al
        jne  mo_next
        mov  al, 1
        ret
    mo_new:
        mov  eax, dword ptr [ebp + 0x4c]
        call {FIELD_GETPLAYER:#x}
        cmp  al, 0xff
        jne  mo_next
        mov  eax, dword ptr [ebp + 0x4c]
        mov  edx, dword ptr [ebx + {{STRUCT}}]
        call {HAS_HS:#x}
        test eax, eax
        jne  mo_next
        call mo_stand
        test al, al
        je   mo_next
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, dword ptr [ebx + {{ARMYHS}}]
        call {ARMYHS_CREATE:#x}
        mov  dword ptr [ebp + 0x48], eax
        mov  eax, dword ptr [eax + 0x1c]
        call {BEGINUPD:#x}
        mov  edx, dword ptr [ebp + 0x34]
        movsx edx, byte ptr [edx + 0x12]
        mov  eax, dword ptr [ebp + 0x48]
        mov  eax, dword ptr [eax + 0x1c]
        call {SETPLAYER:#x}
        call mo_mask
        mov  edx, dword ptr [ebp + 0x34]
        mov  eax, dword ptr [ebp + 0x48]
        mov  eax, dword ptr [eax + 0x1c]
        call {ADDUNITSEL:#x}
        test al, al
        jne  mo_free
        movsx eax, byte ptr [esi + {ST_LEVEL:#x}]
        push eax
        push {PLACE_FLAGS}
        mov  dl, byte ptr [ebp + 0x50]
        mov  cl, byte ptr [ebp + 0x54]
        mov  eax, dword ptr [ebp + 0x48]
        call {PLACEEX:#x}
        test al, al
        je   mo_back
        mov  eax, dword ptr [ebp + 0x48]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xe0]
        mov  eax, dword ptr [ebp + 0x48]
        mov  eax, dword ptr [eax + 0x1c]
        call {ENDUPD:#x}
        mov  al, 1
        ret
    mo_back:
        mov  edx, dword ptr [ebp + 0x48]
        mov  edx, dword ptr [edx + 0x1c]
        mov  eax, dword ptr [ebp + 0x34]
        mov  cl, 0xff
        call {ADDUNITSEL:#x}
    mo_free:
        mov  eax, dword ptr [ebp + 0x48]
        call {OBJ_FREE:#x}
    mo_next:
        inc  dword ptr [ebp + 0x3c]
        jmp  mo_try
    mo_fail:
        xor  eax, eax
        ret

    mo_stand:
        mov  eax, dword ptr [ebp + 0x4c]
        mov  dl, byte ptr [eax + 0x14]
        mov  cl, byte ptr [eax + 0x15]
        mov  eax, edi
        call {UNIT_VALIDTERRAIN:#x}
        ret

    mo_mask:
        mov  ecx, dword ptr [ebp + 0x38]
        mov  edx, 1
        shl  edx, cl
        mov  ecx, edx
        ret

    get_anc:
        {{ANC}}
        ret

    gf:
        push edi
        mov  edi, eax
        push edx
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x10]
        movsx edx, byte ptr [esi + {ST_LEVEL:#x}]
        call {GETMAPLEVEL:#x}
        pop  ecx
        test eax, eax
        je   gf_no
        test edi, edi
        js   gf_no
        cmp  edi, dword ptr [eax + 0xc]
        jge  gf_no
        test ecx, ecx
        js   gf_no
        cmp  ecx, dword ptr [eax + 0x10]
        jge  gf_no
        mov  edx, edi
        call {LEVEL_GETFIELD:#x}
        pop  edi
        ret
    gf_no:
        xor  eax, eax
        pop  edi
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

    in_ent:
        push edi
        movzx ecx, byte ptr [esi + {ST_COUNT:#x}]
        lea  edi, [esi + {ST_ENT:#x}]
    ie_loop:
        test ecx, ecx
        je   ie_no
        cmp  byte ptr [edi], al
        jne  ie_next
        cmp  byte ptr [edi + 1], dl
        jne  ie_next
        mov  al, 1
        pop  edi
        ret
    ie_next:
        add  edi, 4
        dec  ecx
        jmp  ie_loop
    ie_no:
        xor  eax, eax
        pop  edi
        ret

    add_ent:
        push edi
        movzx edi, byte ptr [esi + {ST_COUNT:#x}]
        cmp  edi, {MAX_ENT}
        jae  ae_no
        lea  edi, [esi + edi*4 + {ST_ENT:#x}]
        mov  byte ptr [edi], al
        mov  byte ptr [edi + 1], dl
        mov  byte ptr [edi + 2], cl
        mov  byte ptr [edi + 3], 0
        inc  byte ptr [esi + {ST_COUNT:#x}]
        mov  al, 1
        pop  edi
        ret
    ae_no:
        xor  eax, eax
        pop  edi
        ret

    valid_lava:
        call gf
        test eax, eax
        je   vl_no
        movzx ecx, byte ptr [eax + 0x14]
        cmp  ecx, 15
        ja   vl_no
        mov  edx, {LAND:#x}
        bt   edx, ecx
        jae  vl_no
        cmp  byte ptr [eax + 0x15], 0
        je   vl_no
        mov  edx, dword ptr [ebx + {{STRUCT}}]
        call {HAS_HS:#x}
        test eax, eax
        jne  vl_no
        mov  al, 1
        ret
    vl_no:
        xor  eax, eax
        ret

    marker_add:
        push edi
        push ebp
        sub  esp, 0xc
        mov  ebp, esp
        mov  dword ptr [ebp], eax
        mov  dword ptr [ebp + 4], edx
        movzx ecx, cl
        mov  dword ptr [ebp + 8], ecx
        call gf
        test eax, eax
        je   ma_out
        mov  edx, dword ptr [ebx + {{FW}}]
        call {FINDOWNEDHS:#x}
        test eax, eax
        jne  ma_out
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, dword ptr [ebx + {{FW}}]
        call {TEOBJ_CREATE:#x}
        mov  edi, eax
        mov  byte ptr [edi + 0xc], {MARK_COUNT:#x}
        mov  byte ptr [edi + 0xd], {MARK_OWNER:#x}
        mov  eax, dword ptr [ebp + 8]
        mov  byte ptr [edi + 0xe], al
        mov  byte ptr [edi + 0xf], al
        push dword ptr [ebp + 4]
        movsx eax, byte ptr [esi + {ST_LEVEL:#x}]
        push eax
        mov  ecx, dword ptr [ebp]
        mov  edx, edi
        mov  eax, dword ptr [ebx + {{MAP}}]
        call {PLACEHX:#x}
        test al, al
        jne  ma_out
        mov  dl, 1
        mov  eax, edi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx - 4]
    ma_out:
        add  esp, 0xc
        pop  ebp
        pop  edi
        ret

    marker_del:
        call gf
        test eax, eax
        je   md_out
        mov  edx, dword ptr [ebx + {{FW}}]
        call {FINDOWNEDHS:#x}
        test eax, eax
        je   md_out
        cmp  byte ptr [eax + 0xd], {MARK_OWNER:#x}
        jne  md_out
        mov  dl, 1
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx - 4]
    md_out:
        ret

    find_mtn:
        push esi
        push edi
        push ebp
        mov  esi, eax
        xor  edi, edi
    fm_loop:
        movzx eax, byte ptr [esi + 0xd]
        cmp  edi, eax
        jge  fm_no
        mov  eax, dword ptr [esi + 8]
        mov  ebp, dword ptr [eax + edi*4]
        test ebp, ebp
        je   fm_next
        mov  eax, ebp
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x24]
        cmp  eax, {MTN_CLASSID:#x}
        jne  fm_next
        mov  edx, ebp
        mov  eax, esi
        call {GETHNOFHS:#x}
        test eax, eax
        js   fm_next
        mov  edx, dword ptr [ebp + 8]
        mov  edx, dword ptr [edx + 0x28]
        cmp  eax, dword ptr [edx + 4]
        jge  fm_next
        mov  edx, dword ptr [edx + 8]
        cmp  byte ptr [edx + eax*2], 0
        jl   fm_next
        mov  eax, ebp
        jmp  fm_out
    fm_next:
        inc  edi
        jmp  fm_loop
    fm_no:
        xor  eax, eax
    fm_out:
        pop  ebp
        pop  edi
        pop  esi
        ret

    find_volc:
        push esi
        push edi
        push ebp
        sub  esp, 8
        mov  esi, dword ptr [eax + 8]
        mov  esi, dword ptr [esi + 0x28]
        cmp  dword ptr [esi + 4], {VOLC_LEN}
        je   fv_no
        mov  eax, esi
        call {TL_USED:#x}
        cmp  eax, 4
        je   fv_n
        cmp  eax, 9
        jne  fv_no
    fv_n:
        mov  dword ptr [esp], eax
        mov  eax, dword ptr [ebx + {{SET}}]
        mov  eax, dword ptr [eax + 0x24]
        mov  eax, dword ptr [eax + 8]
        mov  dword ptr [esp + 4], eax
        xor  edi, edi
    fv_loop:
        mov  eax, dword ptr [esp + 4]
        cmp  edi, dword ptr [eax + 8]
        jge  fv_no
        mov  eax, dword ptr [eax + 4]
        mov  ebp, dword ptr [eax + edi*4]
        test ebp, ebp
        je   fv_next
        mov  eax, ebp
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x24]
        cmp  eax, {MTNRES_CLASSID:#x}
        jne  fv_next
        cmp  byte ptr [ebp + 0x45], {WASTELAND}
        jne  fv_next
        mov  eax, dword ptr [ebp + 0x28]
        cmp  dword ptr [eax + 4], {VOLC_LEN}
        jne  fv_next
        call {TL_USED:#x}
        cmp  eax, dword ptr [esp]
        jne  fv_next
        xor  ecx, ecx
    fv_cmp:
        cmp  ecx, {VOLC_LEN}
        jge  fv_hit
        mov  eax, dword ptr [ebp + 0x28]
        mov  eax, dword ptr [eax + 8]
        movsx eax, byte ptr [eax + ecx*2]
        shr  eax, 31
        mov  edx, 1
        cmp  ecx, dword ptr [esi + 4]
        jge  fv_m
        mov  edx, dword ptr [esi + 8]
        movsx edx, byte ptr [edx + ecx*2]
        shr  edx, 31
    fv_m:
        cmp  eax, edx
        jne  fv_next
        inc  ecx
        jmp  fv_cmp
    fv_hit:
        mov  eax, ebp
        jmp  fv_out
    fv_next:
        inc  edi
        jmp  fv_loop
    fv_no:
        xor  eax, eax
    fv_out:
        add  esp, 8
        pop  ebp
        pop  edi
        pop  esi
        ret

    e_vt:
        push ebx
        call get_anc
        cmp  byte ptr [edx + 0x15], 0
        jne  ev_no
        mov  eax, edx
        call find_mtn
        test eax, eax
        je   ev_no
        call find_volc
        test eax, eax
        je   ev_no
        mov  al, 1
        pop  ebx
        ret
    ev_no:
        xor  eax, eax
        pop  ebx
        ret

    e_exec:
        push ebp
        push ebx
        push esi
        push edi
        sub  esp, 0x30
        mov  ebp, esp
        mov  dword ptr [ebp], eax
        call get_anc
        mov  eax, dword ptr [ebp]
        movsx ecx, byte ptr [eax + 0x22]
        push ecx
        movsx ecx, byte ptr [eax + 0x21]
        movsx edx, byte ptr [eax + 0x20]
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x10]
        call {GETFIELD:#x}
        test eax, eax
        je   x_out
        call find_mtn
        test eax, eax
        je   x_out
        mov  dword ptr [ebp + 4], eax
        call find_volc
        test eax, eax
        je   x_out
        mov  dword ptr [ebp + 8], eax
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edx, 0xffffff
        call {RANDOM:#x}
        mov  edx, dword ptr [ebx + {{SEED}}]
        mov  dword ptr [edx], eax
        mov  esi, dword ptr [ebp + 4]
        mov  eax, dword ptr [esi + 4]
        mov  dword ptr [ebp + 0xc], eax
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xb0]
        mov  edx, dword ptr [ebp + 8]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x110]
        mov  edx, dword ptr [ebp + 0xc]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 8]
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xac]
        mov  eax, dword ptr [ebp + 8]
        cmp  dword ptr [eax + 0x2c], 0xf
        jg   x_ovr
        mov  eax, dword ptr [eax + 0x18]
        mov  eax, dword ptr [eax + 0x3c]
        mov  byte ptr [eax + 0x30], 1
    x_ovr:
        mov  eax, esi
        call {OVERRIDE:#x}
        movsx eax, byte ptr [esi + 0x10]
        mov  dword ptr [ebp + 0x10], eax
        movsx eax, byte ptr [esi + 0x11]
        mov  dword ptr [ebp + 0x14], eax
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, dword ptr [ebx + {{WARD}}]
        call {WARD_CREATE:#x}
        mov  esi, eax
        push {UPKEEP}
        lea  ecx, [ebx + {{NAME}}]
        mov  dl, {REC_TYPE:#x}
        mov  eax, esi
        call {GE_SETUP:#x}
        mov  eax, dword ptr [ebp]
        mov  al, byte ptr [eax + 0x22]
        mov  byte ptr [esi + {ST_LEVEL:#x}], al
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edx, {DELAY_DIE}
        call {RANDOM:#x}
        inc  eax
        mov  byte ptr [esi + {ST_DELAY:#x}], al
        mov  byte ptr [esi + {ST_SPILLS:#x}], {SPILL_TURNS}
        mov  byte ptr [esi + {ST_COUNT:#x}], 0
        mov  dword ptr [ebp + 0x1c], 0
    x_cov:
        mov  eax, dword ptr [ebp + 8]
        mov  eax, dword ptr [eax + 0x28]
        mov  ecx, dword ptr [ebp + 0x1c]
        cmp  ecx, dword ptr [eax + 4]
        jge  x_cast
        mov  eax, dword ptr [eax + 8]
        cmp  byte ptr [eax + ecx*2], 0
        jl   x_cnext
        mov  eax, dword ptr [ebp + 0x10]
        mov  edx, dword ptr [ebp + 0x14]
        call nb
        mov  dword ptr [ebp + 0x20], eax
        mov  dword ptr [ebp + 0x24], edx
        xor  ecx, ecx
        call add_ent
        mov  eax, dword ptr [ebp + 0x20]
        mov  edx, dword ptr [ebp + 0x24]
        mov  cl, {WASTELAND}
        call marker_add
    x_cnext:
        inc  dword ptr [ebp + 0x1c]
        jmp  x_cov
    x_cast:
        mov  eax, dword ptr [ebp]
        mov  dl, byte ptr [eax + 0x18]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x70]
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
    x_out:
        add  esp, 0x30
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret

    e_rw:
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        call {GE_RW:#x}
        cmp  byte ptr [ebx + 0x18], {REC_TYPE:#x}
        jne  er_out
        push {RW_ID}
        lea  edx, [ebx + 0x24]
        mov  ecx, {BLOCK_LEN:#x}
        mov  eax, esi
        mov  edi, dword ptr [eax]
        call dword ptr [edi + 0x1c]
    er_out:
        pop  edi
        pop  esi
        pop  ebx
        ret

    e_msg:
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        call {MSGPROC_THUNK:#x}
        cmp  byte ptr [esi + 0x18], {REC_TYPE:#x}
        jne  em_out
        test byte ptr [esi + 0x10], 1
        je   em_out
        cmp  dword ptr [edi], 0x20020003
        jne  em_out
        movsx eax, byte ptr [esi + 0x19]
        cmp  eax, dword ptr [edi + 0x18]
        jne  em_out
        call get_anc
        call step
    em_out:
        pop  edi
        pop  esi
        pop  ebx
        ret

    e_deact:
        cmp  byte ptr [eax + 0x18], {REC_TYPE:#x}
        jne  ed_orig
        test byte ptr [eax + 0x10], 1
        je   ed_orig
        push eax
        push edx
        push ebx
        push esi
        push edi
        mov  esi, eax
        call get_anc
        xor  edi, edi
    ed_loop:
        movzx eax, byte ptr [esi + {ST_COUNT:#x}]
        cmp  edi, eax
        jge  ed_done
        movzx eax, byte ptr [esi + edi*4 + {ST_ENT:#x}]
        movzx edx, byte ptr [esi + edi*4 + {ST_ENT + 1:#x}]
        call marker_del
        inc  edi
        jmp  ed_loop
    ed_done:
        pop  edi
        pop  esi
        pop  ebx
        pop  edx
        pop  eax
    ed_orig:
        jmp  {GE_DEACT:#x}

    e_show:
        cmp  byte ptr [eax + 0xd], {MARK_OWNER:#x}
        jne  {FW_SHOW:#x}
        push ebp
        mov  ebp, esp
        add  esp, -8
        jmp  {FW_BODY:#x}

    e_reg:
        call {REGISTER_SPELL:#x}
        push esi
        push ebx
        mov  esi, ebx
        call get_anc
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, dword ptr [ebx + {{LTCELL}}]
        call {LT_CREATE:#x}
        push eax
        lea  edx, [ebx + {{NAME}}]
        add  eax, 8
        call {LSTRASG:#x}
        pop  eax
        mov  dword ptr [eax + 0x10], {SPELL_ID}
        mov  dword ptr [eax + 0x14], {MANA}
        mov  dword ptr [eax + 0x18], {RESEARCH}
        mov  dword ptr [eax + 0x1c], {UPKEEP}
        mov  byte ptr [eax + 0x20], {SPHERE}
        mov  byte ptr [eax + 0x21], {TIER}
        mov  edx, eax
        mov  eax, esi
        call {REGISTER_SPELL:#x}
        pop  ebx
        pop  esi
        ret
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP, "SET": AOWHSSET, "SEED": SEED_CELL,
                                "LTCELL": LT_CELL, "WARD": WARD_CELL, "FW": FW_CELL,
                                "ROAD": ROAD_IAT, "STRUCT": STRUCT_CELL, "ARMYHS": ARMYHS_CELL,
                                "NAME": ("TAIL", 8)}, ansistr(SPELL_NAME))


CAVES = [("cave_core", SLOT[0], build_core(SLOT[0]))]


def checks():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    _n, va, blob = CAVES[0]
    for i, name in enumerate(ENTRIES):
        assert blob[5 * i] == 0xE9, "entry %s is not a 5-byte jmp" % name
    code = blob[:blob.rindex(ansistr(SPELL_NAME))].rstrip(b"\x90")
    ins = list(Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, va))
    assert sum(i.size for i in ins) == len(code), "the core does not disassemble cleanly"
    for i in ins:
        if i.mnemonic == "push" and i.op_str.startswith("0x"):
            v = int(i.op_str, 16)
            assert v < 0x80 or v == 0xFFFFFFFF, "%08X: push %s (imm8 sign trap)" % (i.address, i.op_str)
    assert va + len(blob) <= SLOT[1]
    draws = [i.address for i in ins if i.mnemonic == "call" and i.op_str == "%#x" % RANDOM]
    assert draws == sorted(RNG_SITES.values()), "RNG_SITES are stale: %s" % " ".join("%08X" % a for a in draws)
    d = open(P.TARGET, "rb").read()
    van = open(os.path.join(os.path.dirname(P.GAME), "AoWEPACK.dpl"), "rb").read()
    u = lambda b, v: struct.unpack_from("<I", b, P.va2off(b, v))[0]
    if u(d, WARD_CELL) != WARD_VMT:
        sys.exit("ABORT: %08X no longer holds TSpellWardEnchantment" % WARD_CELL)
    if u(d, FW_CELL) + 0xA8 != FW_SHOW_SLOT:
        sys.exit("ABORT: TFrozenWaterHS's Show slot moved")
    o = P.va2off(van, FW_SHOW)
    if van[o:o + 6] != bytes.fromhex("558bec83c4f8"):
        sys.exit("ABORT: vanilla Show's prologue is not push ebp / mov ebp,esp / add esp,-8")
    o = P.va2off(d, FW_BODY)
    if d[o:o + 6] != van[o:o + 6]:
        sys.exit("ABORT: Show's body at %08X is not vanilla" % FW_BODY)
    _e, secs = P.sections(d)
    for _vs, sva, rs, ra in secs:            # nobody else creates spell 85
        for i in range(ra, ra + rs - 7):
            src = P.IMAGE_BASE + sva + (i - ra)
            if SLOT[0] <= src < SLOT[1]:
                continue
            if d[i:i + 3] == b"\xc7\x40\x10" and struct.unpack_from("<I", d, i + 3)[0] == SPELL_ID:
                sys.exit("ABORT: %08X also stores spell id %d" % (src, SPELL_ID))
    dual = d[P.va2off(d, 0x558B6000):P.va2off(d, 0x558B6000) + 0x100]
    if not any(struct.unpack_from("<HBB", dual, k) == (SPELL_ID, 3, 5) for k in range(0, 0xFC, 4)):
        print("  NOTE: build_dual_sphere.py's TABLE does not list spell %d as Earth/Fire yet" % SPELL_ID)


call_to = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
pk = lambda v: struct.pack("<I", v)
HOOKS = [
    (REG_SITE, call_to(REG_SITE, REGISTER_SPELL), call_to(REG_SITE, ENTRY["reg"])),
    (SLOT_RW, pk(GE_RW), pk(ENTRY["rw"])),
    (SLOT_MSG, pk(MSGPROC_THUNK), pk(ENTRY["msg"])),
    (SLOT_DEACT, pk(GE_DEACT), pk(ENTRY["deact"])),
    (FW_SHOW_SLOT, pk(FW_SHOW), pk(ENTRY["show"])),
    (WARD_INST, pk(0x24), pk(INST)),
]
INTERIOR = [(REG_SITE, REG_SITE + 5, 0x557A23A4, 0x557A24FE)]
RELOC_OK = (SLOT_RW, SLOT_MSG, SLOT_DEACT, FW_SHOW_SLOT)

if __name__ == "__main__":
    print("  core %08X, %d of %d B; entries %s" % (SLOT[0], len(CAVES[0][2]), SLOT[1] - SLOT[0],
          ", ".join("%s %08X" % (n, v) for n, v in ENTRY.items())))
    checks()
    # build_blazing_moon.py's cave_msg (pinned there) chains in front of ENTRY["msg"]: an accepted
    # applied state for SLOT_MSG; --apply and --undo refuse while it is in place.
    MOON_MSG = 0x558C51C0
    _d = open(P.TARGET, "rb").read()
    if _d[P.va2off(_d, SLOT_MSG):P.va2off(_d, SLOT_MSG) + 4] == pk(MOON_MSG):
        if "--apply" in sys.argv or "--undo" in sys.argv:
            sys.exit("REFUSED: build_blazing_moon.py chains through %08X; undo it first." % SLOT_MSG)
        HOOKS = [(va, van, pk(MOON_MSG) if va == SLOT_MSG else new) for va, van, new in HOOKS]
        print("  chained: build_blazing_moon.py holds %08X (accepted as applied)" % SLOT_MSG)
    run("build_awaken_volcano", HOOKS, CAVES, SLOT, INTERIOR, reloc_ok=RELOC_OK)
