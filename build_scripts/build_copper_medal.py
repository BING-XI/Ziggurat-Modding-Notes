#!/usr/bin/env python3
"""
Copper medal -- a THIRD unit rank (Copper / Silver / Gold)  [AoWEPACK.dpl + Images/*Combat.ILB]
==============================================================================================
Units ranked None -> Silver -> Gold.  This inserts Copper BELOW silver, so the ladder becomes
None -> Copper(1) -> Silver(2) -> Gold(3).  Full RE writeup: ../Copper_Medal_Design.md

Rank is DERIVED from the XP byte (unit+0x3C) every time it is asked for -- nothing stores it --
so the feature is: new thresholds + remapping the few consumers of the rank number.  Old saves
load unchanged (they store XP, never the rank) and re-derive their medal from the new ladder.

LADDER: copper = tier*2, silver = tier*6, gold = tier*15 (TIER_SCALED = True), and all three medals
grant the SAME stat bonus (+1 ATK / +1 RES).  Copper also gets its own per-unit bonus-ability set.
Retune via LADDER / TIER_SCALED / STAT_TABLES / COPPER_GRANTS_ABILITIES below; the script REWRITES
ITS OWN CAVES IN PLACE, so re-tuning never needs a revert -- verify-before-write accepts the
pristine bytes, the target bytes, or the output of any earlier tuning (regenerated from
PRIOR_TUNINGS; append a tuple there whenever the tuning changes).

⚠ Warmonger (a CITY ENCHANTMENT, ceiWarmonger) grants a flat 15 XP via cave 0x5580C029, so against
a tier-scaled ladder it yields gold at tier 1, silver at tier 2, copper at tier 3-4.

WHAT IS PATCHED (every range verified .reloc-free before displacement):
  1. TUnit.GetRank              0x5578294C (44B)  -> 4-level ladder, returns 0..3 in a clean EAX
  2. TUnit.GetNextRankExperience0x55782920 (44B)  -> next threshold, 0 when maxed (kept convention)
  3. TUnit.SetRank              0x55782978 (86B)  -> ranks 1/2/3 set XP per the ladder
  4. grant-loop remap  3 sites  0x557828F4 / 0x55782C21 / 0x55782CD5 (11B each) -> cave
  5. medal painter TUnit.ShowEx head 0x557826FC (10B) + 0x55782712 (5B) -> icon by rank via cave.
       The dead gold block 0x5578272F.. is LEFT ALONE on purpose: it carries a .reloc at
       0x55782734 (absolute [0x558FA044]) and nothing reaches it once the head is rewritten.
  6. rank stat tables 0x558E83C4..D7 -- each already had a free 4th byte (0x90 filler); getters
       index table[rank & 0x7F], so rank 3 needs no code change.
  7. Arena.TArena.UnitTrainCost gate 0x557D6739 `cmp al,2` -> `cmp al,3` (gold still untrainable).
  8. Images/Combat.ILB (+ _Combat.ILB if present): NEW image id 8 = copper recolour of the silver
       medal (id 5), DISC ONLY -- the ribbon is copied byte-identically, because only the disc
       carries the rank colour.  REQUIRED, not cosmetic: ImageLib.TCustomImageLibrary.Get (ILPACK
       0x5521A8B8) has NO bounds check -- it indexes lib+0x48 straight by image id -- so pointing
       the painter at an absent id reads past the table.  ids 8/9 are holes (ids run 0..7,10..146).
  9. COPPER_GRANTS_ABILITIES: a 4th ability owner in TUnitResource, serialised as new pfs tag 0x20.
       ⚠ SLOT ORDER IS RANK ORDER -- both the grant loops and the editor index owners as
       [unitres + rank*4 + 0x38], so the slots must read base / copper / silver / gold.  Slot 3
       (+0x44) was the transport-capacity byte, which moves to the dead +0x32 gap; silver and gold
       shift up one slot each to let copper take slot 1.  Also patches AoWDevEd.exe: the
       transport-capacity spin write, and a 4th "Copper" rank tab in the DFM.

NOT patched: AoW.exe / AoWCompat.exe / any .pfs / Release.hss.  The exe imports only UnitTrainCost
from this system and reads "(cur/next)" through the virtual getters.  Heroes never draw medals
(THero overrides ShowEx and all stat getters).  No unit carries tag 0x20 until one is authored in
the editor, so copper ability sets start empty.

Sprite16 (ILB type 22) is UNCOMPRESSED RGB565 of the clip rect: the 5 trailing dwords are
[clipw, cliph, clipx, clipy, transparent] and payload == clipw*cliph*2 bytes exactly.

Dry-run by default; --apply to write.  Idempotent (re-run with no args = verify current state).
Backups all go to <game dir>/backups/, never beside the target: AoWEPACK.dpl.pre-coppermedal,
AoWDevEd.exe.pre-coppermedal, Combat.ILB.pre-coppermedal (+ _Combat.ILB.pre-coppermedal).
There is no --undo here; a .pre-* restore is a whole-file copy, not a revert path.
Needs: pip install capstone keystone-engine.  Close every AoW binary before --apply.
"""
import os, sys, struct, shutil

import capstone
import keystone

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
import ilb                                                    # noqa: E402
import dfm_edit                                               # noqa: E402
from ilb_rle16 import rgb565_to_rgb, rgb_to_rgb565            # noqa: E402

DLL    = os.path.join(GAME, "AoWEPACK.dpl")
EDITOR = os.path.join(GAME, "AoWDevEd.exe")
ILBS  = [os.path.join(GAME, "Images", "Combat.ILB"),
         os.path.join(GAME, "Images", "_Combat.ILB")]         # 2nd = vanilla spare, patched if present
SUFFIX = ".pre-coppermedal"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)


def bak_path(p):
    """<game dir>/backups/<file>.pre-coppermedal -- basename(), so the two ILBs under Images/ keep
    their own names instead of colliding."""
    return os.path.join(BACKUP_DIR, os.path.basename(p) + SUFFIX)


# ⚠ VA->file offset is PER SECTION.  CODE is file_off + 0x55700C00, but DATA (the rank stat
# tables at 0x558E83xx) is file_off + 0x55701200 -- using the CODE delta there silently reads
# 0x600 bytes past the tables.  Always go through off().
SECTIONS = []                                                 # (va_start, va_end, file_off), filled below

# ---- tunables -------------------------------------------------------------------------------
LADDER      = (2, 6, 15)     # copper / silver / gold XP thresholds
TIER_SCALED = True           # True: each value is multiplied by the unit's tier (unittype+0x2F).
                             # (the pre-2026-07-30 install was tier-scaled 2/6; vanilla was flat 10/20)
ICON_COPPER, ICON_SILVER, ICON_GOLD = 8, 5, 6                 # COMBAT.ILB image ids
SRC_MEDAL, NEW_MEDAL = 5, 8                                   # clone silver -> new copper id
NEW_SUBID   = 145                                             # authoring metadata only (143/144 = silver/gold)

# Give copper its OWN per-unit bonus-ability set, like silver (pfs tag 0x1E) and gold (0x1F).
# TUnitResource gets a 4th ability owner in the contiguous array, which means slot 3 (+0x44) --
# today the transport-capacity byte -- has to move into the dead +0x32..0x37 gap first.  See the
# doc; this also patches AoWDevEd.exe, which writes that byte.  ⚠ Setting this False again only
# reverts the rank->set mapping; it does NOT move the field back (the script keeps both states
# consistent, so just re-run and it will restore every site it owns).
COPPER_GRANTS_ABILITIES = True
COPPER_TAG   = 0x20        # new Unitres.pfs tag (highest vanilla tag is 0x1F)
CAP_OLD, CAP_NEW = 0x44, 0x32                                 # transport capacity: old -> new offset
# rank stat bonuses, index = rank 0..3.  Silver/gold keep today's live values.
# All three medals grant the SAME bonus (the value silver already gave); rank 0 = no medal = none.
# Tuples are (none, copper, silver, gold).  v5: medals became CUMULATIVE — each rank grants
# another point of ATK and RES instead of every medal granting a flat +1 — and gold picked up
# +1 Damage.  HP and MV are cumulative too, but they are not set here: the GetHits / GetMoves
# caves override this table, so they are handled by build_medal_hpmv.py.
STAT_TABLES = [(0x558E83C4, "Defense",    (0, 0, 0, 1)),
               (0x558E83C8, "Attack",     (0, 1, 2, 3)),
               (0x558E83CC, "Damage",     (0, 0, 1, 2)),   # H2 2026-08-24: gold +2 on the doubled damage scale
               (0x558E83D0, "Resistance", (0, 1, 2, 3)),
               (0x558E83D4, "Hits",       (0, 0, 0, 0))]      # dead: GetHits cave multiplies rank by 0
# luminance -> copper ramp for the recoloured medal
COPPER_RAMP = [(0, (0, 0, 0)), (40, (46, 20, 10)), (90, (105, 52, 24)), (140, (160, 88, 44)),
               (190, (208, 132, 74)), (230, (236, 180, 130)), (255, (255, 226, 196))]

CAVE_VA, CAVE_LEN = 0x55813000, 0xA0                          # free (highest claimed elsewhere: 0x55812900)
GRANT_CAVE, ICON_CAVE, RW_CAVE = CAVE_VA, CAVE_VA + 0x20, CAVE_VA + 0x60

UPDATE_DEFAULT_ABILITIES = 0x5574F518
GETRANK_VA               = 0x5578294C

# --- TUnitResource sites for the 4th ability owner (all live-verified 2026-07-30) ---------------
# ⚠ SLOT ORDER IS RANK ORDER.  Both the grant loops and the editor index owners as
# `[unitres + rank*4 + 0x38]`, so slot 1 MUST be copper, slot 2 silver, slot 3 gold.  Inserting
# copper at the far end (+0x44) instead is a real bug that shows up as "the Copper tab lists
# silver's abilities and Gold is empty" -- and in-game as copper units gaining silver's abilities.
OWNER_SLOTS_ON = [(0x38, 0x19, "base"), (0x3C, 0x20, "copper"),
                  (0x40, 0x1E, "silver"), (0x44, 0x1F, "gold")]
OWNER_SLOTS_OFF = [(0x38, 0x19, "base"), (0x3C, 0x1E, "silver"), (0x40, 0x1F, "gold")]


# v1 of the 4-owner layout put copper at the far end instead of in rank order.  Kept ONLY so the
# corrected build is a rewrite-in-place rather than a revert -- do not use it.
OWNER_SLOTS_BUGGY = [(0x38, 0x19, "base"), (0x3C, 0x1E, "silver"),
                     (0x40, 0x1F, "gold"), (0x44, 0x20, "copper")]


def slot_of(tag, copper_abilities, slots_on=None):
    """Which TUnitResource offset a pfs ability-owner tag is (de)serialised to."""
    slots = (slots_on or OWNER_SLOTS_ON) if copper_abilities else OWNER_SLOTS_OFF
    return next(off for off, t, _n in slots if t == tag)


RW_SILVER_VA = 0x55784F33     # disp byte of `mov edx,[edi+0x3C]` for tag 0x1E in ReadWrite
RW_GOLD_VA   = 0x55784F3B     # 15B: mov ecx,0x1F / mov edx,[edi+0x40] / mov eax,esi / mov ebx,[eax] / call [ebx+0xC]
CAP_READ_VA  = 0x55784D46     # disp byte of `mov dl, byte ptr [ebx+0x44]` in GetTransportCapacity
CAP_RW_VA    = 0x55784ED0     # disp byte of `lea edx, [edi+0x44]`        in ReadWrite (tag 0x18)
CREATE_N_VA  = 0x55784C8E     # imm of `cmp bl,3` in Create   (owner-alloc loop)
DESTROY_N_VA = 0x55784CEA     # imm of `cmp bl,3` in Destroy  (owner-free loop)
VALID_N_VA   = 0x55784F66     # imm of `cmp bl,3` in ReadWrite (ValidateOwnerTypeAbilities loop)
# AoWDevEd.exe: disp byte of `mov byte ptr [esi+0x44], al` -- the transport-capacity spin write
ED_CAP_VA    = 0x00411168
ED_DELTA     = 0x400C00       # AoWDevEd.exe CODE: VA = file_offset + this

# AoWDevEd.exe: the TUnitResourceEditForm DFM (RCDATA "TUNITRESOURCEEDITFORM"), as a RAW FILE
# OFFSET + the resource's exact size from the PE resource directory.
#
# ⚠ The DFM CANNOT GROW: resource data entries in this exe are packed with ZERO padding (the next
# form's "TPF0" starts immediately at the end of this one), so lengthening the tab captions has to
# be paid for from inside the same form.  It is paid for by deleting
# `AbilityRankTabs.TabOrder = 0` (11 bytes): that control is the FIRST child of its group box, so
# creation order gives it TabOrder 0 regardless -- verified, and its sibling AbilityBtn sets 1
# explicitly.  11 freed + 20 old caption bytes = 31, and the four full captions cost 28.
# (Hunting for shorter integer encodings instead is a dead end -- Delphi already emits vaInt8
# wherever the value fits.  A runtime `Tabs.Add` cave is also avoidable: the editor imports neither
# TCustomTabControl.GetTabs nor TStrings.Insert.)
#
# Tab order maps to owner slots 0..3 (base / copper / silver / gold) because the editor indexes
# [unitres + tabIndex*4 + 0x38].
ED_DFM_OFF, ED_DFM_SIZE = 0xDA3C4, 0x12B8
ED_TABS_CTL = "AbilityRankTabs"
TAB_CAPTIONS_ON = ["None", "Copper", "Silver", "Gold"]
TAB_CAPTIONS_OFF = ["None", "Silver", "Gold"]

ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32)
cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)

# pristine 15-byte gold-owner block in TUnitResource.ReadWrite (the hook site)
RW_GOLD_ORIG = bytes.fromhex("b91f0000008b57408bc68b18ff530c")


def asm(code, at):
    b, _ = ks.asm(code, at)
    return bytes(b)


def pad(b, n, fill=b"\x90"):
    assert len(b) <= n, "code is %d bytes, only %d available" % (len(b), n)
    return b + fill * (n - len(b))


# ---- code -----------------------------------------------------------------------------------
def gen(ladder, tier_scaled, stat_tables, copper_abilities=False, slots_on=None):
    """Build every byte this feature writes, for a given tuning.  Returns {VA: bytes} plus the
    cave.  Parameterised so that PRIOR TUNINGS can be regenerated and accepted as a valid
    'before' state -- that is what makes re-tuning a rewrite-in-place instead of a revert."""
    C1, C2, C3 = ladder

    # `tier` is only loaded when the ladder is tier-scaled; the flat form needs no extra load.
    _TIER = ("    mov  ecx, dword ptr [eax+0x40]\n"
             "    movsx ecx, byte ptr [ecx+0x2F]\n") if tier_scaled else ""

    def _thresh(reg, c):
        """compare the XP in EDX against threshold `c`, via `reg`."""
        if tier_scaled:
            return "    imul %s, ecx, %d\n    cmp  edx, %s\n" % (reg, c, reg)
        return "    mov  %s, %d\n    cmp  edx, %s\n" % (reg, c, reg)

    def _setxp(c):
        """SetRank: put the XP for a wanted rank into EDX (EAX = tier when tier-scaled)."""
        return "    imul edx, eax, %d\n" % c if tier_scaled else "    mov  edx, %d\n" % c

    GETRANK = pad(asm("""
    push ebx
    xor  edx, edx
    mov  dl,  byte ptr [eax+0x3C]
%s    xor  eax, eax
%s    jb   done
    inc  eax
%s    jb   done
    inc  eax
%s    jb   done
    inc  eax
done:
    pop  ebx
    ret
""" % (_TIER, _thresh("ebx", C1), _thresh("ebx", C2), _thresh("ebx", C3)), GETRANK_VA), 44)

    GETNEXT = pad(asm("""
    push esi
    xor  edx, edx
    mov  dl,  byte ptr [eax+0x3C]
%s%s    jb   out
%s    jb   out
%s    jb   out
    xor  esi, esi
out:
    mov  eax, esi
    pop  esi
    ret
""" % (_TIER, _thresh("esi", C1), _thresh("esi", C2), _thresh("esi", C3)), 0x55782920), 44)

    SETRANK = pad(asm("""
    push ebx
    push esi
    mov  ebx, edx
    mov  esi, eax
    mov  eax, esi
    call 0x%X
    cmp  bl, al
    je   out
    test bl, bl
    jne  setxp
    mov  byte ptr [esi+0x3C], 0
    jmp  out
setxp:
    cmp  bl, 3
    ja   out
%s    cmp  bl, 1
    jne  n2
%s    jmp  doset
n2:
    cmp  bl, 2
    jne  n3
%s    jmp  doset
n3:
%sdoset:
    mov  eax, esi
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx+0x160]
out:
    pop  esi
    pop  ebx
    ret
""" % (GETRANK_VA,
       ("    mov  eax, dword ptr [esi+0x40]\n"
        "    movsx eax, byte ptr [eax+0x2F]\n") if tier_scaled else "",
       _setxp(C1), _setxp(C2), _setxp(C3)), 0x55782978), 86)

    # EAX = loop index (0..rank), EDX = unittype, ESI = unit.
    if copper_abilities:
        # 4 contiguous owners exist, so rank -> set is the identity again:
        # 0 base, 1 copper, 2 silver, 3 gold.
        GRANT = asm("""
    mov  edx, dword ptr [edx+eax*4+0x38]
    mov  eax, esi
    jmp  0x%X
""" % UPDATE_DEFAULT_ABILITIES, GRANT_CAVE)
    else:
        # Only 3 owners: copper (1) grants nothing, 2/3 use the silver/gold delta sets at
        # type+0x38 + (index-1)*4.  ⚠ Never let index 3 through here -- +0x44 is not an owner.
        GRANT = asm("""
    cmp  eax, 1
    je   skip
    jb   zero
    dec  eax
zero:
    mov  edx, dword ptr [edx+eax*4+0x38]
    mov  eax, esi
    jmp  0x%X
skip:
    ret
""" % UPDATE_DEFAULT_ABILITIES, GRANT_CAVE)

    # AL = rank (1..3) -> ECX = COMBAT.ILB image id, consumed by the rewritten `mov edx,ecx`.
    ICON = asm("""
    cmp  al, 1
    jne  n2
    mov  ecx, %d
    ret
n2:
    cmp  al, 2
    jne  n3
    mov  ecx, %d
    ret
n3:
    mov  ecx, %d
    ret
""" % (ICON_COPPER, ICON_SILVER, ICON_GOLD), ICON_CAVE)

    # ReadWrite: serialise the gold owner (tag 0x1F) exactly as the displaced code did, then the
    # new copper owner (tag 0x20).  ESI = the reader/writer, EDI = the resource; EBX is scratch
    # here (ReadWrite reuses it for the vtable pointer throughout) and nothing after the hook
    # depends on it.  Register-only + rel32, so it survives rebasing.
    RW = asm("""
    mov  ecx, 0x1F
    mov  edx, dword ptr [edi+0x%02X]
    mov  eax, esi
    mov  ebx, dword ptr [eax]
    call dword ptr [ebx+0x0C]
    mov  ecx, 0x%02X
    mov  edx, dword ptr [edi+0x%02X]
    mov  eax, esi
    mov  ebx, dword ptr [eax]
    call dword ptr [ebx+0x0C]
    ret
""" % (slot_of(0x1F, copper_abilities, slots_on), COPPER_TAG,
       slot_of(COPPER_TAG, copper_abilities, slots_on)), RW_CAVE) if copper_abilities else b""

    cave = pad(pad(GRANT, 0x20, b"\x00") + pad(ICON, 0x40, b"\x00") + RW, CAVE_LEN, b"\x00")

    PAINT_HEAD = pad(asm("""
    test al, al
    jz   0x55782756
    call 0x%X
""" % ICON_CAVE, 0x557826FC), 10)

    out = {0x55782920: GETNEXT, 0x5578294C: GETRANK, 0x55782978: SETRANK,
           0x557826FC: PAINT_HEAD,
           0x55782712: bytes.fromhex("8bd1909090"),      # mov edx,ecx (was mov edx,5)
           0x557D6739: bytes.fromhex("3c03")}            # gold is rank 3, not rank 2
    for va, _nm in ((0x557828F4, "SetExperience"), (0x55782C21, "SetUnitResource"),
                    (0x55782CD5, "NewDay")):
        out[va] = pad(asm("call 0x%X" % GRANT_CAVE, va), 11)
    for va, _nm, vals in stat_tables:
        out[va] = bytes(vals)

    # --- the 4th ability owner ------------------------------------------------------------------
    cap = CAP_NEW if copper_abilities else CAP_OLD
    n_owners = 4 if copper_abilities else 3
    out[CAP_READ_VA] = bytes([cap])          # GetTransportCapacity reads the (moved) byte
    out[CAP_RW_VA] = bytes([cap])            # ReadWrite serialises it (tag 0x18)
    out[RW_SILVER_VA] = bytes([slot_of(0x1E, copper_abilities, slots_on)])  # silver moves up for copper
    out[CREATE_N_VA] = bytes([n_owners])     # Create: allocate N owners
    out[DESTROY_N_VA] = bytes([n_owners])    # Destroy: free N
    out[VALID_N_VA] = bytes([n_owners])      # ReadWrite: validate N
    out[RW_GOLD_VA] = (pad(asm("call 0x%X" % RW_CAVE, RW_GOLD_VA), 15) if copper_abilities
                       else RW_GOLD_ORIG)
    return out, cave


# Every earlier tuning, so a retune stays a rewrite-in-place instead of a revert.  Append a tuple
# here whenever LADDER / TIER_SCALED / STAT_TABLES change again.
#   v1 2026-07-30  tier-scaled 1/2/6, copper no stat bonus
#   v2 2026-07-30  flat 2/6/15, all medals +1 ATK/+1 RES
#   v3 2026-07-30  tier-scaled 2/6/15, all medals +1 ATK/+1 RES, copper had no ability set
V1_STATS = [(0x558E83C4, "Defense", (0, 0, 0, 0)), (0x558E83C8, "Attack", (0, 0, 1, 2)),
            (0x558E83CC, "Damage", (0, 0, 0, 0)), (0x558E83D0, "Resistance", (0, 0, 1, 2)),
            (0x558E83D4, "Hits", (0, 0, 2, 4))]
#   v4 2026-07-30  tier-scaled 2/6/15 + copper ability set, but copper wrongly at slot 3
#   v5 2026-08-07  cumulative ATK/RES (0,1,2,3) and gold +1 Damage  <- current STAT_TABLES
# ⚠ These entries must hold LITERALS, not a reference to STAT_TABLES. They used to name the
# live variable, so editing STAT_TABLES silently rewrote the "prior" tunings too and the
# script would stop recognising the bytes actually installed — turning a rewrite-in-place
# into a failed verify. V4_STATS is the tuning that shipped before v5.
V4_STATS = [(0x558E83C4, "Defense", (0, 0, 0, 0)), (0x558E83C8, "Attack", (0, 1, 1, 1)),
            (0x558E83CC, "Damage", (0, 0, 0, 0)), (0x558E83D0, "Resistance", (0, 1, 1, 1)),
            (0x558E83D4, "Hits", (0, 0, 0, 0))]
#   v5 2026-08-07  cumulative ATK/RES (0,1,2,3), gold +1 Damage
V5_STATS = [(0x558E83C4, "Defense", (0, 0, 0, 0)), (0x558E83C8, "Attack", (0, 1, 2, 3)),
            (0x558E83CC, "Damage", (0, 0, 0, 1)), (0x558E83D0, "Resistance", (0, 1, 2, 3)),
            (0x558E83D4, "Hits", (0, 0, 0, 0))]
#   v6 2026-08-07  Damage moves down to silver (0,0,1,1); gold gains +1 Defense
V6_STATS = [(0x558E83C4, "Defense", (0, 0, 0, 1)), (0x558E83C8, "Attack", (0, 1, 2, 3)),
            (0x558E83CC, "Damage", (0, 0, 1, 1)), (0x558E83D0, "Resistance", (0, 1, 2, 3)),
            (0x558E83D4, "Hits", (0, 0, 0, 0))]
#   v7 2026-08-24  DAM/HP doubling decision H2: Damage -> (0,0,1,2) on the doubled damage scale
PRIOR_TUNINGS = [((1, 2, 6), True, V1_STATS, False, None),
                 ((2, 6, 15), False, V4_STATS, False, None),
                 ((2, 6, 15), True, V4_STATS, False, None),
                 ((2, 6, 15), True, V4_STATS, True, OWNER_SLOTS_BUGGY),
                 ((2, 6, 15), True, V5_STATS, True, None),
                 ((2, 6, 15), True, V6_STATS, True, None)]

NEWBYTES, CAVE = gen(LADDER, TIER_SCALED, STAT_TABLES, COPPER_GRANTS_ABILITIES)
assert [t for _o, t, _n in OWNER_SLOTS_ON] == [0x19, COPPER_TAG, 0x1E, 0x1F], (
    "owner slots must be in RANK order: base, copper, silver, gold")
PRIORS = [gen(*t) for t in PRIOR_TUNINGS]

# ---- patch table: (VA, description) in write order; bytes come from NEWBYTES ------------------
DESCS = [
    (0x55782920, "TUnit.GetNextRankExperience -> 4-level ladder"),
    (0x5578294C, "TUnit.GetRank -> 4-level ladder"),
    (0x55782978, "TUnit.SetRank -> ranks 1/2/3"),
    (0x557826FC, "medal painter dispatch -> icon-by-rank cave"),
    (0x55782712, "medal painter: mov edx,5 -> mov edx,ecx"),
    (0x557D6739, "UnitTrainCost: gold-is-rank-2 -> rank-3"),
    (0x557828F4, "SetExperience ability-grant loop -> rank remap"),
    (0x55782C21, "SetUnitResource ability-grant loop -> rank remap"),
    (0x55782CD5, "NewDay ability-grant loop -> rank remap"),
] + [(va, "rank %s bonus table" % nm) for va, nm, _v in STAT_TABLES] + [
    (CAP_READ_VA, "GetTransportCapacity reads capacity at +0x%02X" % CAP_NEW),
    (CAP_RW_VA, "ReadWrite serialises capacity at +0x%02X (tag 0x18)" % CAP_NEW),
    (CREATE_N_VA, "TUnitResource.Create: allocate 4 ability owners"),
    (DESTROY_N_VA, "TUnitResource.Destroy: free 4 ability owners"),
    (VALID_N_VA, "ReadWrite: validate 4 ability owners"),
    (RW_SILVER_VA, "ReadWrite: silver (tag 0x1E) owner slot"),
    (RW_GOLD_VA, "ReadWrite: gold owner + new copper owner (tag 0x%02X)" % COPPER_TAG),
]

# pristine (pre-feature) bytes, so a first-time apply can be told apart from a re-tune
ORIGINALS = {
    0x557826FC: bytes.fromhex("fec87406fec8742beb50"),
    0x55782712: bytes.fromhex("ba05000000"),
    0x557D6739: bytes.fromhex("3c02"),
}
for _va in (0x557828F4, 0x55782C21, 0x55782CD5):
    ORIGINALS[_va] = (bytes.fromhex("8b548238") + b"\x8b\xc6" + b"\xe8" +
                      struct.pack("<i", UPDATE_DEFAULT_ABILITIES - (_va + 11)))
ORIGINALS.update({
    0x55782920: bytes.fromhex("568b50400fbe522f8bf203f633c98a483c3bf17f138bf203f68d34763bce7c0433c0eb068bc65ec38bc65ec3"),
    0x5578294C: bytes.fromhex("5333d28a503c8b48400fbe492f8bd903db3bd37c138bc103c08d04403bd07c04b002eb06b0015bc333c05bc3"),
    0x55782978: bytes.fromhex("53568bda8bf08bc6e8c7ffffff3ad87442"),   # prefix match only (86B body)
    0x558E83C4: bytes.fromhex("00000090"), 0x558E83C8: bytes.fromhex("00010290"),
    0x558E83CC: bytes.fromhex("00000090"), 0x558E83D0: bytes.fromhex("00010290"),
    0x558E83D4: bytes.fromhex("00020490"),
    CAP_READ_VA: bytes([CAP_OLD]), CAP_RW_VA: bytes([CAP_OLD]),
    CREATE_N_VA: b"\x03", DESTROY_N_VA: b"\x03", VALID_N_VA: b"\x03",
    RW_SILVER_VA: b"\x3c", RW_GOLD_VA: RW_GOLD_ORIG,
})


def load_sections(data):
    """Fill SECTIONS from the PE header so VA->offset is correct in every section."""
    if SECTIONS:
        return
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    for i in range(nsec):
        o = pe + 24 + optsz + i * 40
        vsz, va, rsz, ro = struct.unpack_from("<IIII", data, o + 8)
        SECTIONS.append((base + va, base + va + max(vsz, rsz), ro))


def off(va):
    for lo, hi, ro in SECTIONS:
        if lo <= va < hi:
            return ro + (va - lo)
    raise AssertionError("VA %08X is in no section" % va)


def check_dll(data):
    """Verify every site is in a state we are allowed to overwrite.

    -> (fresh, applied, retune, problems).  A site may hold the pristine bytes (fresh), exactly
    what we want (applied), or the output of an earlier tuning of THIS feature (retune -- safe to
    overwrite in place).  Anything else is another feature's code and aborts the run."""
    fresh = applied = retune = 0
    problems = []
    for va, desc in DESCS:
        new = NEWBYTES[va]
        cur = bytes(data[off(va):off(va) + len(new)])
        if cur == new:
            applied += 1
            continue
        if any(cur == p[0][va] for p in PRIORS):
            retune += 1
            continue
        exp = ORIGINALS.get(va)
        if exp is not None and cur[:len(exp)] == exp:
            fresh += 1
        else:
            problems.append("  %08X %-46s\n     expected pristine %s\n     found            %s"
                            % (va, desc, (exp or b"?").hex(" "), cur[:len(exp or cur)].hex(" ")))
    cave = bytes(data[off(CAVE_VA):off(CAVE_VA) + CAVE_LEN])
    if cave == CAVE:
        applied += 1
    elif any(cave == p[1] for p in PRIORS):
        retune += 1
    elif cave == b"\x00" * CAVE_LEN:
        fresh += 1
    else:
        problems.append("  cave zone %08X is neither zero, ours, nor a prior tuning of ours "
                        "(owned by another feature?)" % CAVE_VA)
    return fresh, applied, retune, problems


# ---- AoWDevEd.exe: the editor writes the transport-capacity byte, so it moves too -------------
def dfm_retab(region):
    """Normalising transform: force AbilityRankTabs to the wanted captions, and drop (or restore)
    its redundant TabOrder to keep the DFM within its resource's fixed size.

    Idempotent and reachable from ANY earlier state (pristine 3-tab, the abbreviated 4-tab, or the
    target), because it is expressed as 'make it look like this' rather than an old->new byte pair.
    Returns the full padded region, exactly ED_DFM_SIZE bytes."""
    captions = TAB_CAPTIONS_ON if COPPER_GRANTS_ABILITIES else TAB_CAPTIONS_OFF
    keep_taborder = not COPPER_GRANTS_ABILITIES
    w = dfm_edit.walk(region)
    assert w.consumed <= len(region), "DFM walk overran the resource"
    assert all(b == 0 for b in region[w.consumed:]), "unexpected junk after the DFM content"

    ti_a, ti_b = dfm_edit.find(w, ED_TABS_CTL, "TabIndex")
    tabs = [p for p in w.props
            if p[0].endswith(ED_TABS_CTL) and p[1] == "Tabs.Strings" and p[2] == dfm_edit.LIST]
    assert len(tabs) == 1, "expected exactly one Tabs.Strings list"
    ts_a, ts_b = tabs[0][3], tabs[0][4]
    # everything between TabIndex and Tabs.Strings must be nothing or exactly TabOrder, or this
    # reconstruction would silently drop a property
    mid = [p for p in w.props if p[0].endswith(ED_TABS_CTL) and ti_b <= p[3] < ts_a
           and p[1] not in ("$class",)]
    assert all(p[1] == "TabOrder" for p in mid), "unexpected properties between TabIndex and Tabs"

    taborder = dfm_edit.shortstr("TabOrder") + bytes([dfm_edit.I8, 0]) if keep_taborder else b""
    newtabs = (dfm_edit.shortstr("Tabs.Strings") + bytes([dfm_edit.LIST])
               + dfm_edit.string_list(captions))
    out = region[:ti_b] + taborder + newtabs + region[ts_b:w.consumed]
    assert len(out) <= ED_DFM_SIZE, (
        "DFM would grow to %d > %d bytes -- the caption budget is blown; shorten a caption or free "
        "more bytes inside this form" % (len(out), ED_DFM_SIZE))
    out += b"\x00" * (ED_DFM_SIZE - len(out))

    # prove it: re-walk, and require every property to match the original except the intended diffs
    w2 = dfm_edit.walk(out)
    assert all(b == 0 for b in out[w2.consumed:]), "padding is not clean"

    def sig(ww):
        return [(p[0], p[1], p[2], p[5]) for p in ww.props
                if not (p[0].endswith(ED_TABS_CTL) and p[1] in ("TabOrder", "Tabs.Strings"))]
    assert sig(w2) == sig(w), "DFM rewrite disturbed an unrelated property"
    got = [p[5] for p in w2.props
           if p[0].endswith(ED_TABS_CTL) and p[1] == "Tabs.Strings" and p[2] == dfm_edit.LIST]
    assert got == [captions], "captions did not round-trip: %r" % got
    have_to = [p for p in w2.props if p[0].endswith(ED_TABS_CTL) and p[1] == "TabOrder"]
    assert bool(have_to) == keep_taborder, "TabOrder presence is wrong"
    return out


def editor_patches(data):
    """-> [(file_offset, target_bytes, description)] for AoWDevEd.exe."""
    on = COPPER_GRANTS_ABILITIES
    captions = TAB_CAPTIONS_ON if on else TAB_CAPTIONS_OFF
    return [
        (ED_CAP_VA - ED_DELTA, bytes([CAP_NEW if on else CAP_OLD]),
         "transport-capacity spin write -> +0x%02X" % (CAP_NEW if on else CAP_OLD)),
        (ED_DFM_OFF, dfm_retab(bytes(data[ED_DFM_OFF:ED_DFM_OFF + ED_DFM_SIZE])),
         "AbilityRankTabs tabs: %s" % " / ".join(captions)),
    ]


def check_editor(data):
    """-> (state, messages).  state is 'target' | 'todo' | 'bad'."""
    msgs, todo = [], 0
    # sanity-anchor the code site: it must still be `mov byte ptr [esi+disp], al`
    o = ED_CAP_VA - ED_DELTA
    if bytes(data[o - 2:o]) != b"\x88\x46":
        return "bad", ["AoWDevEd.exe 0x%08X is not `mov byte ptr [esi+disp],al` (found %s) -- "
                       "another patch owns it?"
                       % (ED_CAP_VA - 2, bytes(data[o - 2:o + 1]).hex(" "))]
    if data[o] not in (CAP_OLD, CAP_NEW):
        return "bad", ["AoWDevEd.exe 0x%08X: unexpected displacement 0x%02X"
                       % (ED_CAP_VA, data[o])]
    try:
        patches = editor_patches(data)
    except AssertionError as e:
        return "bad", ["AoWDevEd.exe DFM rewrite refused: %s" % e]
    for foff, new, desc in patches:
        if bytes(data[foff:foff + len(new)]) == new:
            continue
        todo += 1
        msgs.append("  will patch: %s" % desc)
    return ("todo", msgs) if todo else ("target", ["AoWDevEd.exe: already at target"])


# ---- ILB ------------------------------------------------------------------------------------
def disc_start(px, cw, ch, transparent):
    """First row of the medal's DISC, i.e. where the rank colour belongs.

    The sprite is a neutral ribbon on top and a circular disc below it; only the disc is tinted per
    rank (silver is grey throughout, gold is warm only there).  Derived from the GOLD sprite rather
    than hardcoded, so it holds for both the 7x13 HD art and the 3x6 vanilla art: take the
    bottom-most contiguous run of rows that contain a strongly saturated gold pixel.
    (Gold also has a few warm pixels up in the ribbon; those are deliberately NOT included --
    the ribbon must stay the same colour as on the silver/gold medals.)"""
    hot = []
    for y in range(ch):
        sat = 0
        for x in range(cw):
            v = px[y * cw + x]
            if v == transparent:
                continue
            r, g, b = rgb565_to_rgb(v)
            sat = max(sat, max(r, g, b) - min(r, g, b))
        hot.append(sat >= 50)
    y = ch - 1
    while y >= 0 and not hot[y]:            # skip any unsaturated tail (the disc's dark bottom tip)
        y -= 1
    assert y >= 0, "gold medal has no tinted pixels -- wrong image?"
    while y >= 0 and hot[y]:                # walk up through the contiguous tinted run
        y -= 1
    return y + 1


def copper(v, transparent):
    if v == transparent:
        return v
    r, g, b = rgb565_to_rgb(v)
    lum = (r * 299 + g * 587 + b * 114) // 1000
    for i in range(len(COPPER_RAMP) - 1):
        l0, c0 = COPPER_RAMP[i]
        l1, c1 = COPPER_RAMP[i + 1]
        if l0 <= lum <= l1:
            t = (lum - l0) / (l1 - l0) if l1 > l0 else 0.0
            out = tuple(int(round(c0[k] + (c1[k] - c0[k]) * t)) for k in range(3))
            break
    else:
        out = COPPER_RAMP[-1][1]
    return rgb_to_rgb565(*out)


def copper_payload(data, r):
    """Silver medal recoloured to copper on the DISC ONLY; the ribbon is copied verbatim."""
    imgdir = r["hdr"]["imgdir"]
    src = next(im for im in r["images"] if im["id"] == SRC_MEDAL)
    gold = next(im for im in r["images"] if im["id"] == ICON_GOLD)
    cw, ch, cx, cy, tr = src["s16"]
    assert cw * ch * 2 == src["size"], "Sprite16 is not uncompressed clipw*cliph RGB565"
    assert gold["s16"] == src["s16"], "silver and gold medals differ in clip geometry"
    spx = struct.unpack_from("<%dH" % (cw * ch), data, imgdir + src["offset"])
    gpx = struct.unpack_from("<%dH" % (cw * ch), data, imgdir + gold["offset"])
    y0 = disc_start(gpx, cw, ch, tr)
    out = [copper(v, tr) if i // cw >= y0 else v for i, v in enumerate(spx)]
    return struct.pack("<%dH" % len(out), *out), src, y0, ch


def build_ilb(data):
    """-> ILB bytes with image NEW_MEDAL present and up to date, or None if already correct."""
    r = ilb.parse(data)
    payload, src, y0, ch = copper_payload(data, r)
    existing = next((im for im in r["images"] if im["id"] == NEW_MEDAL), None)
    if existing is not None:
        # already spliced in: the geometry is identical, so just refresh the pixels in place
        at = r["hdr"]["imgdir"] + existing["offset"]
        assert existing["size"] == len(payload), "existing copper image has unexpected size"
        if bytes(data[at:at + len(payload)]) == payload:
            return None
        out = bytearray(data)
        out[at:at + len(payload)] = payload
        assert len(out) == len(data), "in-place pixel rewrite changed the file size"
        return bytes(out)
    later = sorted(im["dir_off"] for im in r["images"] if im["dir_off"] > src["dir_off"])
    assert len(later) >= 2, "silver medal is at the end of the directory -- unexpected"
    rec = bytearray(data[src["dir_off"]:later[0]])
    # splice in right after the gold medal, so the new entry lands inside the prefix this parser
    # can walk (it stops at the first composite entry) and can therefore be verified below
    insert_at = later[1]

    # field offsets inside the record, derived from the layout and then ASSERTED against the parse
    nlen = len(src["name"])
    o_sub, o_size, o_off = 13 + nlen + 16, 13 + nlen + 21, 13 + nlen + 25
    assert struct.unpack_from("<I", rec, 0)[0] == SRC_MEDAL
    assert struct.unpack_from("<I", rec, o_sub)[0] == src["subid"]
    assert struct.unpack_from("<I", rec, o_size)[0] == src["size"]
    assert struct.unpack_from("<I", rec, o_off)[0] == src["offset"]

    imgdir, filelen = r["hdr"]["imgdir"], r["hdr"]["filelen"]
    assert filelen == len(data), "header filelen %d != actual %d" % (filelen, len(data))
    assert data[imgdir - 4:imgdir] == b"\xff\xff\xff\xff", "no -1 terminator at end of directory"

    struct.pack_into("<I", rec, 0, NEW_MEDAL)
    struct.pack_into("<I", rec, o_sub, NEW_SUBID)
    struct.pack_into("<I", rec, o_off, filelen - imgdir)       # appended at the old end of data

    out = bytearray(data)
    out[insert_at:insert_at] = rec
    struct.pack_into("<I", out, 16, imgdir + len(rec))         # data start moves; offsets are relative
    out += payload
    struct.pack_into("<I", out, 20, len(out))                  # filelen
    n = len(rec)

    # prove nothing else moved: every byte outside the splice must be identical, and the whole
    # pixel-data block must survive verbatim (image offsets are relative to imgdir, which shifted)
    assert struct.unpack_from("<II", out, 16) == (imgdir + n, len(out)) and \
        len(out) == filelen + n + len(payload), "header not updated"
    assert bytes(out[:16]) == data[:16] and bytes(out[24:insert_at]) == data[24:insert_at], \
        "bytes before the splice changed (only the imgdir/filelen dwords may move)"
    assert bytes(out[insert_at + n:imgdir + n]) == data[insert_at:imgdir], "directory tail changed"
    assert bytes(out[imgdir + n:filelen + n]) == data[imgdir:filelen], "pixel data changed"
    assert bytes(out[filelen + n:]) == payload, "payload not at the end"
    assert out[imgdir + n - 4:imgdir + n] == b"\xff\xff\xff\xff", "lost the -1 terminator"

    # ...and re-parse: every pre-existing image must come back field-for-field identical
    r2 = ilb.parse(bytes(out))
    before = {im["id"]: {k: v for k, v in im.items() if k not in ("idx", "dir_off")}
              for im in r["images"]}
    after = {im["id"]: {k: v for k, v in im.items() if k not in ("idx", "dir_off")}
             for im in r2["images"]}
    assert NEW_MEDAL in after, "new image did not parse back"
    for i, rec_before in before.items():
        assert after[i] == rec_before, "image id %d changed: %s -> %s" % (i, rec_before, after[i])
    new = after[NEW_MEDAL]
    assert (new["w"], new["h"], new["size"], new["s16"]) == \
           (src["w"], src["h"], src["size"], src["s16"]), "new record geometry mismatch"
    assert bytes(out[r2["hdr"]["imgdir"] + new["offset"]:][:new["size"]]) == payload
    return bytes(out)


# ---- main -----------------------------------------------------------------------------------
def main():
    apply = "--apply" in sys.argv
    if "--ladder" in sys.argv:
        print("note: edit LADDER at the top of this script, then re-run (caves rewrite in place)")
    print("game dir: %s" % GAME)
    fmt = "tier*%d" if TIER_SCALED else "%d XP"
    print("ladder:   copper " + fmt % LADDER[0] + ", silver " + fmt % LADDER[1] +
          ", gold " + fmt % LADDER[2])
    print("icons:    copper=%d silver=%d gold=%d\n" % (ICON_COPPER, ICON_SILVER, ICON_GOLD))

    slots = OWNER_SLOTS_ON if COPPER_GRANTS_ABILITIES else OWNER_SLOTS_OFF
    print("copper abilities: %s\nowners (slot = rank): %s\ntransport capacity at +0x%02X\n"
          % ("ON" if COPPER_GRANTS_ABILITIES else "off",
             ", ".join("+0x%02X %s (tag 0x%02X)" % (o, n, t) for o, t, n in slots),
             CAP_NEW if COPPER_GRANTS_ABILITIES else CAP_OLD))

    if "--disasm" in sys.argv:
        for va, nm in [(0x5578294C, "GetRank"), (0x55782920, "GetNextRankXP"),
                       (0x55782978, "SetRank"), (0x557826FC, "painter head"),
                       (RW_GOLD_VA, "ReadWrite gold/copper hook"),
                       (GRANT_CAVE, "grant cave"), (ICON_CAVE, "icon cave"),
                       (RW_CAVE, "ReadWrite owner cave")]:
            code = NEWBYTES.get(va) or CAVE[va - CAVE_VA:]
            print("=== %s" % nm)
            for i in cs.disasm(code.rstrip(b"\x00") or code, va):
                print("  %08x: %-22s %s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str))
        return

    data = bytearray(open(DLL, "rb").read())
    load_sections(data)
    size0 = len(data)
    fresh, applied, retune, problems = check_dll(data)
    print("AoWEPACK.dpl: %d sites pristine, %d already at target, %d from an earlier tuning "
          "(rewritten in place)" % (fresh, applied, retune))
    if problems:
        print("MISMATCH -- refusing to write:")
        print("\n".join(problems))
        sys.exit(1)

    ilb_work = []
    for path in ILBS:
        if not os.path.exists(path):
            print("Images/%s: absent, skipped" % os.path.basename(path))
            continue
        raw = open(path, "rb").read()
        built = build_ilb(raw)
        name = os.path.basename(path)
        _p, _src, y0, ch = copper_payload(raw, ilb.parse(raw))
        where = "rows %d-%d of %d are the disc (recoloured); 0-%d stay as silver" % (
            y0, ch - 1, ch, y0 - 1)
        if built is None:
            print("%-14s image id %d already correct  [%s]" % (name + ":", NEW_MEDAL, where))
        elif len(built) == len(raw):
            print("%-14s refresh image id %d pixels in place  [%s]" % (name + ":", NEW_MEDAL, where))
            ilb_work.append((path, built))
        else:
            print("%-14s add image id %d (copper), %d -> %d bytes  [%s]"
                  % (name + ":", NEW_MEDAL, len(raw), len(built), where))
            ilb_work.append((path, built))

    ed = bytearray(open(EDITOR, "rb").read())
    ed_state, ed_msgs = check_editor(ed)
    print("AoWDevEd.exe: %s" % ed_state)
    print("\n".join(ed_msgs))
    if ed_state == "bad":
        print("MISMATCH -- refusing to write.")
        sys.exit(1)

    if fresh == 0 and retune == 0 and not ilb_work and ed_state == "target":
        print("\nALREADY FULLY APPLIED -- nothing to do.")
        return
    if not apply:
        print("\nDRY RUN ok -- re-run with --apply to write.")
        return

    if fresh or retune:
        bak = bak_path(DLL)
        if not os.path.exists(bak):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(DLL, bak)
            print("backup: %s" % bak)
        # safe to overwrite wholesale: check_dll proved the zone is zero, ours, or a prior tuning
        data[off(CAVE_VA):off(CAVE_VA) + CAVE_LEN] = CAVE
        for va, desc in DESCS:
            new = NEWBYTES[va]
            data[off(va):off(va) + len(new)] = new
        assert len(data) == size0, "DLL size changed -- aborting"
        f, a, r, p = check_dll(data)
        assert not p and f == 0 and r == 0, "post-write verification failed"
        open(DLL, "wb").write(data)
        print("AoWEPACK.dpl patched (%d sites + cave @0x%08X)." % (len(DESCS), CAVE_VA))

    if ed_state == "todo":
        bak = bak_path(EDITOR)
        if not os.path.exists(bak):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(EDITOR, bak)
            print("backup: %s" % bak)
        size_before = len(ed)
        patches = editor_patches(ed)
        for foff, new, desc in patches:
            ed[foff:foff + len(new)] = new
        assert len(ed) == size_before, "AoWDevEd.exe size changed -- aborting"
        assert check_editor(ed)[0] == "target", "post-write verification failed (editor)"
        open(EDITOR, "wb").write(ed)
        print("AoWDevEd.exe patched (%d sites)." % len(patches))

    for path, built in ilb_work:
        bak = bak_path(path)
        if not os.path.exists(bak):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(path, bak)
        open(path, "wb").write(built)
        print("%s: image id %d written." % (os.path.basename(path), NEW_MEDAL))
    print("\nAPPLIED.")


if __name__ == "__main__":
    main()
