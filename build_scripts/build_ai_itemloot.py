#!/usr/bin/env python
r"""
build_ai_itemloot.py -- AI heroes pick up, equip, UPGRADE-SWAP and stash ground items, and ground
items become AI targets that only the groups who could USE them will path to.

Supersedes BOTH `build_ai_itempickup.py` (confirmed working 2026-07-21, empty slots only) and
`build_ai_itemtarget.py` (applied then REVERTED 2026-07-22).  One script, because pickup ("is this
item better than what I am wearing?") and targeting ("would anyone in this group take it?") must
answer with the SAME valuation; a cross-script `call rel32` into another script's cave would couple
the two scripts' `--undo` paths together.

WHY THE 2026-07 TARGETING PATCH WAS REVERTED, AND WHAT IS DIFFERENT NOW
----------------------------------------------------------------------
`build_ai_itemtarget.py` answered AI-target broadcast 0x1200 with `10 + min(GetObtainValue/10, 20)`
-- a flat 10..30 that ignored who was asking.  AI stacks with no hero, or with heroes already
better equipped, still walked to the item and then loitered next to something they could not take.
This version answers **only if some hero/leader in the ASKING group would actually take the item**,
using the same take/swap rule the pickup worker uses, so a group that cannot use the loot is never
attracted to it at all.

THE VALUE METRIC
----------------
    value(item) = 5*ATK + 10*DEF + 10*DAM + 5*RES  +  SUM over granted abilities of ExpandCost

Stat bytes: `[item+0x46]` ATK, `[+0x47]` DEF, `[+0x48]` DAM, `[+0x49]` RES -- re-derived on THIS
install, not taken on trust: our live DLL has `THeroItems.GetAttack/GetDefense/GetDamage/
GetResistance` @0x55786354/88/BC/F0 hooked out to caves at 0x55815080/110/1A0/230, and those caves
sum exactly `[item+0x46..0x49]` (they add an inventory pass that vanilla lacks).  `TItem.ReadWrite
@0x557945C8` maps file tags 0x0B/0x0C/0x0D/0x0E onto those four bytes through the SIGNED byte
reader (`[stream_vmt+0x30]`), which is why the cave uses `movsx`, not `movzx`.

Abilities: `TItem` is an ability OWNER.  `TItem` VMT+0x4C is `TCustomAbilityList.GetAbSet
@0x5574E0E0` = `cmp edx,[item+0xC]; jae false; bt [[item+8]],edx` -- so `[item+8]` is the BITSET
pointer and `[item+0xC]` is the BIT CAPACITY.  The cave copies that accessor including its bound.
Each set bit's id indexes the global registry `[[0x558FA044]+0x80]` via `TAbilityControl.GetAbility
@0x557501C0`, and the cost is the virtual `[ability_vmt+0xC8]` ExpandCost -- the same number the
hero level-up system charges.

PICKUP / UPGRADE-SWAP  (AI heroes, strategic map, on their owner's turn and on every move)
------------------------------------------------------------------------------------------
Pass 1, ONE carry item into a free inventory slot.  Pass 2, equip slots 0..5: the slot's required
type comes from the engine's own pos->type table (`THeroItems.GetPositionItemType @0x55786734`,
table 0x558E8DB0 = `02 00 03 04 01 04`, so slots 3 AND 5 are both rings).

⚠ A CARRY ITEM IS `type >= 5`, NOT `type == 5`.  Do not "simplify" that back to an equality test.
The Delphi RTTI enum shipped in the binary is
    TItemTypes = (itHead, itTorso, itAttack, itDefense, itRing, itScroll, itUse)
-- i.e. **itScroll = 5 and itUse = 6** -- and the type->pos table at 0x558E8DB8
(`01 04 00 02 03 0F 0F`) maps BOTH of them to 0x0F, "no equip slot".  Two independent censuses
agree that type 5 has no instances: `Release/ITEMS.PFS` has 0 of 83 at type 5 (our 2026-07-30 RTTI
read), and the live library `User/Zig.ail` has 0 of 325 -- while `Zig.ail` holds **73 items at type
6**.  So an `== 5` test picks up an item class that exists in neither tree and silently ignores
every real potion and wand; a targeting arm that rejects `type > 5` throws all 73 away.  The design
this script is ported from had exactly that bug in both places.  The best matching ground
item that is STRICTLY better than what is worn replaces it: drop the old one with
`ExecutePlaceItem(hero, oldID, 0xE)`, then place the new one at the slot.  Equal value -> no
switch, so the AI cannot thrash between two equivalent items.  Empty slot -> any matching item.

Drop-before-place is what makes the swap possible at all, and it works for a non-obvious reason
worth recording.  `ExecutePlaceItem` revalidates through `THero.CanPlaceItem @0x55788D08`, which on
the strategic map requires the ITEM and the HERO to report the same hex.  `TItem.GetLocation
@0x557942B4` delegates to its container's VMT+0x90, and the base `TItemList.GetLocation @0x55794A5C`
just writes the 0xFF "nowhere" sentinel -- which would make every drop a silent no-op.  It works
because `THeroItems` overrides that slot: `THeroItems.GetLocation @0x5578633C` is `[self+4]` (the
owning hero) forwarded to the hero's own location getter, so a worn item reports the hero's tile
exactly.  `THeroInventory` overrides it the same way.  This is also why `THero.Killed` can drop all
14 slots in vanilla.  If a future change re-points either +0x90 slot, the swap stops working
silently -- there is no error, the item simply never leaves the slot.

PRIORITY (targeting)
--------------------
    priority = 10 + min(bestQualifyingValue / 2, 65)      ->  10..75, max-combined into [rec+0]

Calibrated against the LIVE item library `User/Zig.ail` (325 records), not against vanilla
ITEMS.PFS: measured value distribution is median 19, p75 32, p90 48, max 114 (Blade of Erebus).
With divisor 2 the 65-point cap only bites at value 130 -- 14% above the highest item that exists --
so nothing in the shipped library pins at the ceiling and the whole band stays usable.  That
measurement UNDERSTATES the true metric (231 of the ability references on items have no `Ability.pfs`
tag-6 cost because their cost is set in code), which is the second reason for keeping the divisor at
2 rather than 1: it leaves ~1.5x of headroom before the cap starts flattening the top of the range.
Against the vanilla priority scale -- re-verified in `TArmy.UpdateAITarget @0x55790618`: enemy army
**50**, army with a hero **100**, army with a wizard **300**, plus player-structure 10 and city
100..130 -- that puts the median item at 19 (above a bare structure, well below any army) and only
the best ~2% of items above the enemy-army line.  Divisor 1 would have put a third of the library
above 50 and had loot outbid combat.

MP SAFETY
---------
Both pickup hooks run on EVERY peer -- `THero.NewTurn` is reached by broadcast with no locality
gate, and `TAbstractUnit.MovedTo` is reached from `TArmy.MovedTo` iterating army members -- and
`ExecutePlaceItem` is side-effect-clean (no RNG, log, sound, dialog or token), so the result is
identical on every peer.  **Minting a token here would be WRONG**: N peers would each mint one and
the item would be placed N times.  The targeting cave only writes an AI query result -- no state.
NO CAVE IN THIS SCRIPT DRAWS FROM EITHER RNG; `--check` asserts that
(see Zig notes/12-re-toolchain.md section 4).

OWNERSHIP HANDOVER
------------------
`build_ai_itempickup.py` owns hook sites 0x55787FD7 and 0x5578051B while it is installed.  This
script REFUSES to apply until those sites are handed back; it never takes them over silently.

USAGE
-----
    python build_scripts/build_ai_itemloot.py            # dry run + verify current state
    python build_scripts/build_ai_itemloot.py --dis      # dry run + full cave disassembly
    python build_scripts/build_ai_itemloot.py --apply    # write (auto-backup .pre-aiitemloot)
    python build_scripts/build_ai_itemloot.py --undo     # SURGICAL: restore 2 hooks + the VMT
                                                         #   slot, zero the whole cave zone
"""

import os
import re
import shutil
import struct
import subprocess
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-aiitemloot")
BASE = 0x55700000

# ---------------------------------------------------------------------------
# Engine addresses.  EVERY ONE re-verified on THIS install (live AoWEPACK.dpl and
# Modding Resources/AoWEPACK_original_backup.dpl) against the DLL's own .edata export table --
# all resolve EXACT, i.e. they are the first byte of the named export, not an offset into it.
# ---------------------------------------------------------------------------
GETPLAYERS = 0x557544D0   # AoWE.TPlayerList.GetPlayers(EAX=list, EDX=idx) -> player | 0
GETITEMS   = 0x55788C7C   # AoWE.THero.GetItemsOnGround(EAX=hero)          -> TItemList* | 0
GETITEM    = 0x55794A2C   # AoWE.TItemList.GetItem(EAX=list, EDX=i)        -> TItem* | 0 (bounded)
GETUNIT    = 0x5578309C   # AoWE.TUnitList.GetUnit(EAX=list, EDX=i)        -> unit | 0  (bounded)
GETPOSITEM = 0x55786718   # AoWE.THeroItems.GetPositionItem(EAX, EDX=pos)  -> TItem* | 0 (bounded)
GETPOSTYPE = 0x55786734   # AoWE.THeroItems.GetPositionItemType(DL=pos)    -> AL = item type
INVGETSLOT = 0x55786284   # AoWE.THeroInventory.GetSlot(EAX=inv, DL=6..13) -> TItem* | 0
EXECPLACE  = 0x5578907C   # AoWE.THero.ExecutePlaceItem(EAX, EDX=itemID, ECX=pos)
GETABILITY = 0x557501C0   # AoWE.TAbilityControl.GetAbility(EAX=ctl, EDX=id) -> TAbility | nil
ISCLASS    = 0x557010C0   # System.@IsClass(EAX=obj, EDX=classref) -> AL   (thunk into VCL30)
ABSNEWTURN = 0x55780D4C   # AoWE.TAbstractUnit.NewTurn  [the call displaced by hook A]
INHERITED  = 0x55701D4C   # THexagonSprite.MapFieldMsgProc thunk (jmp [0x558FC078] -> HSEPack)

EXPANDCOST_SLOT = 0xC8    # ability VMT slot: ExpandCost.  Only FOUR implementations exist in the
                          # whole DLL (TAbility / TMultiLevelAbility / TTurnUndeadAbility /
                          # TDispelMagicAbility) and all four are pure reads -- see the EDX note
                          # in build_value().
COUNT_SLOT      = 0x54    # TUnitList/TItemList VMT slot: GetCount

# --- globals reached through the call/pop rebase-delta anchor (no reloc on these cells) ---
MAP_GLOBAL   = 0x558FA040  # AoWE.AoWHSMap  ; [+0x11C] combat obj, [+0x140] TPlayerList
HSSET_GLOBAL = 0x558FA044  # AoWE.AoWHSSet  ; [+0x80] = TAbilityControl (registry)
HEROREF_CELL = 0x55711FAC  # vmtSelfPtr cell holding the THero classref (VMT 0x55711FEC) - HAS reloc
TABREF_CELL  = 0x5570F214  # vmtSelfPtr cell holding the TAbility classref (VMT 0x5570F254) - reloc

# ---- hook sites -----------------------------------------------------------
HOOK_NT_VA   = 0x55787FD7            # THero.NewTurn: call TAbstractUnit.NewTurn
HOOK_NT_ORIG = bytes([0xE8, 0x70, 0x8D, 0xFF, 0xFF])

HOOK_MV_VA   = 0x5578051B            # TAbstractUnit.MovedTo epilogue: pop edi/esi/ebx/ecx/ebp
HOOK_MV_ORIG = bytes([0x5F, 0x5E, 0x5B, 0x59, 0x5D])

VMT_SLOT_VA  = 0x55710244            # TItemHS VMT+0xCC (VMT 0x55710178) -- carries a HIGHLOW reloc
SLOT_ORIG    = struct.pack("<I", INHERITED)

# ---- the sites build_ai_itempickup.py owns while it is installed ----------
OLD_PICKUP_SCRIPT = "build_ai_itempickup.py"
OLD_ZONE_LO, OLD_ZONE_HI = 0x55810000, 0x55810180
OLD_HOOK_NT = 0x55810100
OLD_HOOK_MV = 0x55810140

# ---- OUR cave zone: 0x55838000..0x5583C000, exclusively reserved ----------
# Verified all-zero and reloc-free in both the live and the pristine DLL.  CODE section runs
# 0x55701000..0x558E7A00 with file offset = VA - 0x55700C00 (resolved through the section table,
# never a flat delta).  Nothing else in this tree lives above 0x55832329.
ZONE_VA, ZONE_LEN = 0x55838000, 0x4000

CAVE_VALUE     = 0x55838000   # item worth              (EAX=TItem*)               budget 0x100
CAVE_WOULDTAKE = 0x55838100   # would this hero take it (EAX=hero,EDX=item,ECX=val) budget 0x100
CAVE_PICKUP    = 0x55838200   # pickup / swap worker    (EAX=THero*)               budget 0x200
CAVE_TARGET    = 0x55838400   # TItemHS.MapFieldMsgProc (EAX=self,EDX=msg)         budget 0x180
CAVE_NT        = 0x55838580   # hook A wrapper                                     budget 0x40
CAVE_MOVED     = 0x558385C0   # hook B wrapper                                     budget 0x40

CAVES = (("cave_value",     CAVE_VALUE,     0x100),
         ("cave_wouldtake", CAVE_WOULDTAKE, 0x100),
         ("cave_pickup",    CAVE_PICKUP,    0x200),
         ("cave_target",    CAVE_TARGET,    0x180),
         ("cave_nt",        CAVE_NT,        0x040),
         ("cave_moved",     CAVE_MOVED,     0x040))

# ---- tunables -------------------------------------------------------------
COST_ATT, COST_DEF, COST_DAM, COST_RES = 5, 10, 10, 5
PRIO_BASE, PRIO_DIV, PRIO_CAP = 10, 2, 65     # 10 + min(value/2, 65) -> 10..75
AB_ID_CEIL = 192              # hard ceiling on the bitset walk, ON TOP of the engine's [item+0xC]
FIRST_CARRY_TYPE = 5          # >= this = unequippable, carried in the backpack.  TItemTypes RTTI:
                              # itScroll = 5, itUse = 6, and the type->pos table maps BOTH to 0x0F.
                              # ⚠ This is a >= test on purpose -- see the warning in the docstring;
                              # `== 5` would ignore all 73 type-6 use items in User/Zig.ail.
EQUIP_SLOTS = 6
INV_LO, INV_HI = 6, 14        # ExecutePlaceItem dispatch: <6 equip, 6..13 inventory, 0xE ground
GROUND_POS = 0x0E


# ---------------------------------------------------------------- PE helpers

def pe_sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    tbl = pe + 24 + optsz
    out = []
    for i in range(nsec):
        o = tbl + i * 40
        out.append((struct.unpack_from("<I", data, o + 12)[0],   # vaddr
                    struct.unpack_from("<I", data, o + 8)[0],    # vsize
                    struct.unpack_from("<I", data, o + 20)[0],   # praw
                    struct.unpack_from("<I", data, o + 16)[0]))  # rsize
    return out


def va_to_off(data, va):
    """VA -> file offset THROUGH THE SECTION TABLE.  Never a flat delta: in AoWEPACK.dpl CODE and
    DATA have different VA->offset deltas."""
    rva = va - BASE
    for vaddr, vsize, praw, rsize in pe_sections(data):
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return praw + (rva - vaddr)
    raise ValueError("VA %#x is not in any section" % va)


def reloc_hits(data, lo_va, hi_va):
    """Every .reloc fixup VA inside [lo,hi).  Overwriting a byte-run that carries one corrupts the
    image at load, so every displaced range is checked before it is written."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    nrva = struct.unpack_from("<I", data, pe + 24 + 92)[0]
    if nrva < 6:
        return []
    rrva, rsize = struct.unpack_from("<II", data, pe + 24 + 96 + 5 * 8)
    if not rrva:
        return []
    base_off = va_to_off(data, BASE + rrva)
    hits, off = [], 0
    while off < rsize:
        page, blen = struct.unpack_from("<II", data, base_off + off)
        if blen < 8:
            break
        pv = BASE + page
        if pv + 0x1000 > lo_va and pv < hi_va:
            for i in range((blen - 8) // 2):
                e = struct.unpack_from("<H", data, base_off + off + 8 + i * 2)[0]
                if (e >> 12) == 0:
                    continue
                va = pv + (e & 0xFFF)
                if lo_va <= va < hi_va:
                    hits.append(va)
        off += blen
    return hits


# ------------------------------------------------------- tiny two-pass asm
#
# Item kinds:
#   ("i", "instr")     keystone-assembled, VA-independent encoding
#   ("c", target_va)   call rel32                        (5 bytes)
#   ("j", cc, label)   jump rel32; "jmp" = 5 bytes, conditional = 6
#   ("L", name)        label
#   ("b", raw_bytes)   literal bytes
#
# One instruction per keystone call and no ';' anywhere -- keystone HANGS on a ';' comment inside an
# asm block.  All jumps are forced to rel32 so the two passes agree on every size.

_CC = {"jz": b"\x0F\x84", "jnz": b"\x0F\x85", "jl": b"\x0F\x8C", "jle": b"\x0F\x8E",
       "jg": b"\x0F\x8F", "jge": b"\x0F\x8D", "jae": b"\x0F\x83", "jnc": b"\x0F\x83",
       "jb": b"\x0F\x82", "jmp": b"\xE9"}


def _ks():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return Ks(KS_ARCH_X86, KS_MODE_32)


def assemble(items, base_va):
    ks = _ks()
    enc = {}
    for idx, it in enumerate(items):
        if it[0] == "i":
            enc[idx] = bytes(ks.asm(it[1], base_va)[0])
        elif it[0] == "b":
            enc[idx] = it[1]

    def size(idx, it):
        if it[0] in ("i", "b"):
            return len(enc[idx])
        if it[0] == "c":
            return 5
        if it[0] == "j":
            return 5 if it[1] == "jmp" else 6
        return 0

    pos, labels = base_va, {}
    for idx, it in enumerate(items):
        if it[0] == "L":
            labels[it[1]] = pos
        pos += size(idx, it)

    out, pos = bytearray(), base_va
    for idx, it in enumerate(items):
        n = size(idx, it)
        if it[0] in ("i", "b"):
            out += enc[idx]
        elif it[0] == "c":
            out += b"\xE8" + struct.pack("<i", it[1] - (pos + 5))
        elif it[0] == "j":
            out += _CC[it[1]] + struct.pack("<i", labels[it[2]] - (pos + n))
        pos += n
    return bytes(out)


def _disp(reg, target, anchor):
    """Displacement text for the call/pop rebase anchor: [reg + (target - anchor)] resolves to the
    global's RUNTIME address whatever base the package is loaded at."""
    d = target - anchor
    return "%s %s 0x%X" % (reg, "+" if d >= 0 else "-", abs(d))


def with_anchor(builder, va):
    """Assemble a cave twice: once with a placeholder anchor to MEASURE where its `call $+5; pop`
    lands, then again with the true runtime anchor.

    Never hand-count the anchor offset.  Getting it wrong does not fail to assemble and does not
    fail to verify -- it silently shifts every global reference by a constant, so the cave reads
    the wrong memory.  (The first draft of this script did exactly that: a hand-computed anchor
    for cave_value was 0x4C short, which pointed the TAbility classref at 0x5570F260 instead of
    0x5570F214 and the AoWHSSet global at 0x558FA090 instead of 0x558FA044.  It was caught only by
    disassembling the cave and reading it.)
    """
    first = builder(va, va)
    i = first.find(b"\xE8\x00\x00\x00\x00")
    if i == -1:
        raise AssertionError("no `call $+5` anchor found in this cave")
    if not (0x58 <= first[i + 5] <= 0x5F):
        raise AssertionError("byte after `call $+5` is %#04x, not a `pop reg`" % first[i + 5])
    anchor = va + i + 5
    out = builder(va, anchor)
    if len(out) != len(first) or out.find(b"\xE8\x00\x00\x00\x00") != i:
        raise AssertionError("resolving the anchor moved it -- displacement encoding is unstable")
    return out


# ---------------------------------------------------------------- cave build

def build_value(va, anchor):
    """value(item).  IN: EAX = TItem* (may be nil).  OUT: EAX = weighted worth.
    Preserves EBX/ESI/EDI/EBP.

    Frame: [esp]=TAbility classref  [esp+4]=TAbilityControl  [esp+8]=current ability

    Two things here are load-bearing and were each a crash in the design this is ported from:

    * `[item+8]` is the ability BITSET, not a TList of children -- walking it as a list reads
      bitmask word 1 (0 for every low-id item) as a data-array pointer.  `[item+0xC]` is the BIT
      CAPACITY and MUST bound the scan; a fixed 192-bit walk reads past smaller bitsets.  Both come
      straight from the engine's own accessor, TItem VMT+0x4C = TCustomAbilityList.GetAbSet.

    * ExpandCost is effectively `ExpandCost(self, unit)` -- it never writes EDX, so whatever the
      caller left there flows into `[vmt+0x94] GetInherentLevel(self, unit)`.  With a garbage EDX
      (e.g. the ability's own VMT pointer) TMultiLevelAbility.GetInherentLevel dereferences it as an
      ability owner and chases `[x+0x10]`/`[x+8]` through the vtable.  **EDX is explicitly zeroed.**
      A nil unit returns level 0 immediately, which makes ExpandCost yield the level-1 cost -- the
      same value the hero level-up dialog shows for an ability the hero does not yet have.
    """
    return assemble([
        ("i", "push ebx"), ("i", "push esi"), ("i", "push edi"), ("i", "push ebp"),
        ("i", "sub esp, 0x0C"),
        ("i", "mov ebx, eax"),
        ("i", "xor esi, esi"),                          # ESI = running value
        ("i", "test ebx, ebx"), ("j", "jz", "done"),

        # ---- flat stat bonuses (SIGNED bytes: TItem.ReadWrite uses the signed byte reader) ----
        ("i", "movsx eax, byte ptr [ebx + 0x46]"), ("i", "imul eax, eax, %d" % COST_ATT),
        ("i", "movsx ecx, byte ptr [ebx + 0x47]"), ("i", "imul ecx, ecx, %d" % COST_DEF),
        ("i", "add eax, ecx"),
        ("i", "movsx ecx, byte ptr [ebx + 0x48]"), ("i", "imul ecx, ecx, %d" % COST_DAM),
        ("i", "add eax, ecx"),
        ("i", "movsx ecx, byte ptr [ebx + 0x49]"), ("i", "imul ecx, ecx, %d" % COST_RES),
        ("i", "add eax, ecx"),
        ("i", "mov esi, eax"),

        # ---- granted abilities: bounded exactly as GetAbSet bounds itself ----
        ("i", "mov ebp, dword ptr [ebx + 0x0C]"),       # EBP = bit capacity
        ("i", "test ebp, ebp"), ("j", "jle", "done"),
        ("i", "cmp ebp, %d" % AB_ID_CEIL), ("j", "jle", "capok"),
        ("i", "mov ebp, %d" % AB_ID_CEIL),
        ("L", "capok"),
        ("i", "cmp dword ptr [ebx + 8], 0"), ("j", "jz", "done"),

        ("b", b"\xE8\x00\x00\x00\x00"),                 # call $+5
        ("i", "pop edx"),                               # EDX = runtime VA of the anchor
        ("i", "mov eax, dword ptr [%s]" % _disp("edx", TABREF_CELL, anchor)),
        ("i", "mov dword ptr [esp], eax"),              # TAbility classref (cell has a reloc)
        ("i", "mov eax, dword ptr [%s]" % _disp("edx", HSSET_GLOBAL, anchor)),
        ("i", "test eax, eax"), ("j", "jz", "done"),
        ("i", "mov eax, dword ptr [eax + 0x80]"),       # TAbilityControl (the ability registry)
        ("i", "test eax, eax"), ("j", "jz", "done"),
        ("i", "mov dword ptr [esp + 4], eax"),
        ("i", "xor edi, edi"),                          # EDI = ability id

        ("L", "bit"),
        ("i", "cmp edi, ebp"), ("j", "jge", "done"),
        ("i", "mov eax, dword ptr [ebx + 8]"),
        ("i", "bt dword ptr [eax], edi"),               # engine's own bit-string idiom
        ("j", "jnc", "nextbit"),
        ("i", "mov edx, edi"),
        ("i", "mov eax, dword ptr [esp + 4]"),
        ("c", GETABILITY),                              # nil for an unregistered id; asserts only
        ("i", "test eax, eax"), ("j", "jz", "nextbit"), #   on a NEGATIVE id, which cannot occur
        ("i", "cmp dword ptr [eax], 0"), ("j", "jz", "nextbit"),
        ("i", "mov dword ptr [esp + 8], eax"),
        ("i", "mov edx, dword ptr [esp]"),
        ("c", ISCLASS),                                 # real TAbility descendant?
        ("i", "test al, al"), ("j", "jz", "nextbit"),
        ("i", "mov eax, dword ptr [esp + 8]"),
        ("i", "mov ecx, dword ptr [eax]"),
        ("i", "xor edx, edx"),                          # nil unit -- see the docstring
        ("i", "call dword ptr [ecx + 0x%X]" % EXPANDCOST_SLOT),
        ("i", "add esi, eax"),
        ("L", "nextbit"),
        ("i", "inc edi"), ("j", "jmp", "bit"),

        ("L", "done"),
        ("i", "mov eax, esi"),
        ("i", "add esp, 0x0C"),
        ("i", "pop ebp"), ("i", "pop edi"), ("i", "pop esi"), ("i", "pop ebx"), ("i", "ret"),
    ], va)


def build_wouldtake(va, _anchor=None):
    """Would THIS hero take THIS item?  IN: EAX = THero*, EDX = TItem*, ECX = value(item).
    OUT: EAX = 1/0.  Preserves EBX/ESI/EDI/EBP.

    This is the exact predicate the pickup worker applies, factored out so the AI-target answer and
    the pickup decision can never drift apart:
      * carry item (type >= 5, i.e. the types the engine's type->pos table maps to 0x0F) -> needs a
        free inventory slot;
      * equip item -> needs a slot of the matching type that is empty, or holds a STRICTLY worse
        item.  Equal -> no.

    Frame: [esp] = value, [esp+4] = item type.
    """
    return assemble([
        ("i", "push ebx"), ("i", "push esi"), ("i", "push edi"), ("i", "push ebp"),
        ("i", "sub esp, 8"),
        ("i", "mov ebx, eax"),                          # EBX = hero
        ("i", "mov ebp, edx"),                          # EBP = item
        ("i", "mov dword ptr [esp], ecx"),
        ("i", "test ebx, ebx"), ("j", "jz", "no"),
        ("i", "test ebp, ebp"), ("j", "jz", "no"),
        ("i", "movzx eax, byte ptr [ebp + 0x34]"),      # item type
        ("i", "mov dword ptr [esp + 4], eax"),
        ("i", "cmp eax, %d" % FIRST_CARRY_TYPE), ("j", "jl", "equip"),

        # ---- carry item: any free inventory position 6..13 ----
        # THeroInventory.GetFreeSlot @0x5578601C is deliberately NOT used: it walks the inventory
        # LIST and returns -1 when the list is EMPTY, and hero inventories start empty, so it says
        # "full" for every fresh hero.  GetSlot's own semantics (0 = free, and 0 for any index past
        # the list end) are the correct probe.
        ("i", "cmp dword ptr [ebx + 0x74], 0"), ("j", "jz", "no"),
        ("i", "mov esi, %d" % INV_LO),
        ("L", "inv"),
        ("i", "cmp esi, %d" % INV_HI), ("j", "jge", "no"),
        ("i", "mov edx, esi"),
        ("i", "mov eax, dword ptr [ebx + 0x74]"),
        ("c", INVGETSLOT),
        ("i", "test eax, eax"), ("j", "jz", "yes"),
        ("i", "inc esi"), ("j", "jmp", "inv"),

        # ---- equip item: a matching slot that is empty or strictly worse ----
        ("L", "equip"),
        ("i", "cmp dword ptr [ebx + 0x70], 0"), ("j", "jz", "no"),
        ("i", "xor esi, esi"),
        ("L", "slot"),
        ("i", "cmp esi, %d" % EQUIP_SLOTS), ("j", "jge", "no"),
        ("i", "mov edx, esi"),
        ("i", "xor eax, eax"),
        ("c", GETPOSTYPE),
        ("i", "movzx eax, al"),
        ("i", "cmp eax, dword ptr [esp + 4]"), ("j", "jnz", "nextslot"),
        ("i", "mov edx, esi"),
        ("i", "mov eax, dword ptr [ebx + 0x70]"),
        ("c", GETPOSITEM),
        ("i", "test eax, eax"), ("j", "jz", "yes"),     # slot empty
        ("c", CAVE_VALUE),                              # EAX still the equipped item
        ("i", "cmp eax, dword ptr [esp]"), ("j", "jl", "yes"),   # strictly worse -> upgrade
        ("L", "nextslot"),
        ("i", "inc esi"), ("j", "jmp", "slot"),

        ("L", "yes"),
        ("i", "mov eax, 1"), ("j", "jmp", "out"),
        ("L", "no"),
        ("i", "xor eax, eax"),
        ("L", "out"),
        ("i", "add esp, 8"),
        ("i", "pop ebp"), ("i", "pop edi"), ("i", "pop esi"), ("i", "pop ebx"), ("i", "ret"),
    ], va)


def build_pickup(va, anchor):
    """Pickup / upgrade-swap worker.  IN: EAX = THero*.  Preserves EBX/ESI/EDI/EBP.

    Frame: [esp]=slot type  [+4]=worn id  [+8]=worn value  [+0xC]=best id  [+0x10]=best value
           [+0x14]=scratch TItem*.   -1 is the "no item" sentinel for both id slots, so an item
           whose id happens to be 0 is not mistaken for "none".

    The ground list is REFETCHED for every slot and the loop breaks to the next slot the instant a
    placement succeeds: TItemHS.ItemsChanged @0x55795D10 calls [VMT-4] Destroy when the list
    empties, freeing the TItemHS *and its TItemList*, so the list pointer is dead the moment a
    pickup lands.  Only item IDs (integers) ever cross a mutation boundary, never pointers.
    """
    return assemble([
        ("i", "push ebx"), ("i", "push esi"), ("i", "push edi"), ("i", "push ebp"),
        ("i", "sub esp, 0x18"),
        ("i", "mov ebp, eax"),                          # EBP = hero, survives every call
        ("b", b"\xE8\x00\x00\x00\x00"),                 # call $+5
        ("i", "pop edi"),
        ("i", "mov eax, dword ptr [%s]" % _disp("edi", MAP_GLOBAL, anchor)),
        ("i", "test eax, eax"), ("j", "jz", "done"),
        ("i", "cmp dword ptr [eax + 0x11C], 0"),        # strategic map only (0 = no combat object)
        ("j", "jnz", "done"),
        ("i", "mov eax, dword ptr [eax + 0x140]"),      # TPlayerList
        ("i", "movsx edx, byte ptr [ebp + 0x24]"),      # owner player index (signed)
        ("c", GETPLAYERS),
        ("i", "test eax, eax"), ("j", "jz", "done"),    # bounds-checked -> may be 0
        ("i", "cmp byte ptr [eax + 0xA7], 0"),          # PlayerType: 0 = human, leave it to the UI
        ("j", "jz", "done"),
        ("i", "cmp dword ptr [ebp + 4], 0"),            # placed?  nil container = not on the map
        ("j", "jz", "done"),
        ("i", "cmp dword ptr [ebp + 0x70], 0"),         # THeroItems present?
        ("j", "jz", "done"),

        # ================= pass 1: ONE carry item into a free inventory slot =================
        ("i", "cmp dword ptr [ebp + 0x74], 0"), ("j", "jz", "equip"),
        ("i", "mov eax, ebp"),
        ("c", GETITEMS),
        ("i", "test eax, eax"), ("j", "jz", "done"),    # nil on every hex with no item hot-spot
        ("i", "mov ebx, eax"),
        ("i", "xor esi, esi"),
        ("L", "uloop"),
        ("i", "mov edx, esi"), ("i", "mov eax, ebx"),
        ("c", GETITEM),
        ("i", "test eax, eax"), ("j", "jz", "equip"),
        ("i", "mov dword ptr [esp + 0x14], eax"),
        ("i", "movzx eax, byte ptr [eax + 0x34]"),
        ("i", "cmp eax, %d" % FIRST_CARRY_TYPE), ("j", "jl", "unext"),
        ("i", "mov edi, %d" % INV_LO),
        ("L", "findu"),
        ("i", "cmp edi, %d" % INV_HI), ("j", "jge", "unext"),
        ("i", "mov edx, edi"),
        ("i", "mov eax, dword ptr [ebp + 0x74]"),
        ("c", INVGETSLOT),
        ("i", "test eax, eax"), ("j", "jz", "gotu"),
        ("i", "inc edi"), ("j", "jmp", "findu"),
        ("L", "gotu"),
        ("i", "mov eax, dword ptr [esp + 0x14]"),
        ("i", "mov edx, dword ptr [eax + 0x14]"),       # item ID (integer, never a pointer)
        ("i", "mov ecx, edi"),                          # inventory position 6..13
        ("i", "mov eax, ebp"),
        ("c", EXECPLACE),
        ("j", "jmp", "equip"),                          # list may be FREED - never touch EBX again
        ("L", "unext"),
        ("i", "inc esi"), ("j", "jmp", "uloop"),

        # ================= pass 2: equip slots 0..5, upgrade-swap by value ===================
        ("L", "equip"),
        ("i", "xor edi, edi"),                          # EDI = slot
        ("L", "slot"),
        ("i", "mov edx, edi"),
        ("i", "xor eax, eax"),
        ("c", GETPOSTYPE),
        ("i", "movzx eax, al"),
        ("i", "mov dword ptr [esp], eax"),              # this slot's required item type
        ("i", "mov edx, edi"),
        ("i", "mov eax, dword ptr [ebp + 0x70]"),
        ("c", GETPOSITEM),
        ("i", "test eax, eax"), ("j", "jz", "cur0"),
        ("i", "mov ecx, dword ptr [eax + 0x14]"),
        ("i", "mov dword ptr [esp + 4], ecx"),
        ("c", CAVE_VALUE),                              # EAX still the worn item
        ("i", "mov dword ptr [esp + 8], eax"),
        ("j", "jmp", "scan"),
        ("L", "cur0"),
        ("i", "mov dword ptr [esp + 4], -1"),
        ("i", "mov dword ptr [esp + 8], -1"),           # empty slot: any item beats it
        ("L", "scan"),
        ("i", "mov dword ptr [esp + 0x0C], -1"),
        ("i", "mov eax, dword ptr [esp + 8]"),
        ("i", "mov dword ptr [esp + 0x10], eax"),
        ("i", "mov eax, ebp"),
        ("c", GETITEMS),                                # refetched per slot: may have been freed
        ("i", "test eax, eax"), ("j", "jz", "done"),
        ("i", "mov ebx, eax"),
        ("i", "xor esi, esi"),
        ("L", "iloop"),
        ("i", "mov edx, esi"), ("i", "mov eax, ebx"),
        ("c", GETITEM),
        ("i", "test eax, eax"), ("j", "jz", "endscan"),
        ("i", "mov dword ptr [esp + 0x14], eax"),
        ("i", "movzx ecx, byte ptr [eax + 0x34]"),
        ("i", "cmp ecx, dword ptr [esp]"), ("j", "jnz", "inext"),
        ("c", CAVE_VALUE),                              # EAX still the ground item
        ("i", "cmp eax, dword ptr [esp + 0x10]"), ("j", "jle", "inext"),   # equal -> no switch
        ("i", "mov dword ptr [esp + 0x10], eax"),
        ("i", "mov ecx, dword ptr [esp + 0x14]"),
        ("i", "mov edx, dword ptr [ecx + 0x14]"),
        ("i", "mov dword ptr [esp + 0x0C], edx"),
        ("L", "inext"),
        ("i", "inc esi"), ("j", "jmp", "iloop"),
        ("L", "endscan"),
        ("i", "cmp dword ptr [esp + 0x0C], -1"), ("j", "jz", "nextslot"),
        ("i", "mov ecx, dword ptr [esp + 4]"),
        ("i", "cmp ecx, -1"), ("j", "jz", "placeonly"),
        ("i", "mov edx, ecx"),
        ("i", "mov ecx, %d" % GROUND_POS),
        ("i", "mov eax, ebp"),
        ("c", EXECPLACE),                               # drop the worn item on this hex
        ("L", "placeonly"),
        ("i", "mov edx, dword ptr [esp + 0x0C]"),
        ("i", "mov ecx, edi"),
        ("i", "mov eax, ebp"),
        ("c", EXECPLACE),                               # equip the better one
        ("L", "nextslot"),
        ("i", "inc edi"),
        ("i", "cmp edi, %d" % EQUIP_SLOTS), ("j", "jl", "slot"),

        ("L", "done"),
        ("i", "add esp, 0x18"),
        ("i", "pop ebp"), ("i", "pop edi"), ("i", "pop esi"), ("i", "pop ebx"), ("i", "ret"),
    ], va)


def build_target(va, anchor):
    """TItemHS.MapFieldMsgProc replacement.  IN: EAX = TItemHS*, EDX = msg (int*).

    Modelled on TArmyHS.MapFieldMsgProc @0x55791C30 -- chain to the inherited handler first, guard
    on the sub-hex index, then answer 0x1200.  Message record, re-derived from
    TAoWMapField.GetAITarget @0x55771D84 on this binary:
        [msg+0x00] msgid   [+0x04] TMapField* (filled by the dispatcher)   [+0x08] query ctx
        [+0x0C] 24-byte result record   [+0x10] TAIGroupControl*   [+0x18] hex sub-index
        [+0x1C] stop-propagation
    Query ctx bytes: [0] player index, [1] diplomatic relation, [2] MODE.  Mode 0 is the group
    target search (TAIGroupTargetFinder.Setup @0x5573A298 writes 0 there); recruitment writes 2 and
    production-location writes 3, so the mode gate keeps this answer out of those searches.

    Only `[rec+0]` is written, and only upwards (max-combine, as TCity does).  `[rec+8]`/`[rec+0xC]`
    are gold/mana costs -- writing them would make the AI try to spend resources it does not owe
    through MakeTargetExpense.

    The asking group is walked from the message, not from the map: [msg+0x10] is the
    TAIGroupControl and [gc+0xC] is its TAIGroup, which IS a TUnitList (proved by
    TAIGroupControl.SetupME calling both TUnitList.GetUnit and TAIGroup.GetAdjacent on it).
    TAIGroupControlTargetList.Validate re-queries with the SAME control ([list+0xC], set in
    TAIGroupControl.Create), so a target that qualified stays valid until someone takes the item.

    Frame: [esp]=item idx [+4]=best [+8]=TAIGroup [+0xC]=item [+0x10]=item value
           [+0x14]=THero classref
    """
    return assemble([
        ("i", "push ebx"), ("i", "push esi"), ("i", "push edi"), ("i", "push ebp"),
        ("i", "sub esp, 0x18"),
        ("i", "mov esi, eax"),                          # ESI = self (freed after the chain)
        ("i", "mov edi, edx"),                          # EDI = msg  (freed after the guards)
        ("i", "mov eax, esi"), ("i", "mov edx, edi"),
        ("c", INHERITED),                               # chain to the inherited handler first
        ("i", "cmp dword ptr [edi], 0x1200"), ("j", "jnz", "done"),
        ("i", "cmp dword ptr [edi + 0x18], 0"), ("j", "jnz", "done"),
        ("i", "mov eax, dword ptr [edi + 8]"),          # query ctx
        ("i", "test eax, eax"), ("j", "jz", "done"),
        ("i", "cmp byte ptr [eax + 2], 0"), ("j", "jnz", "done"),   # mode 0 only
        ("i", "mov ebx, dword ptr [edi + 0x0C]"),       # EBX = result record
        ("i", "test ebx, ebx"), ("j", "jz", "done"),
        ("i", "mov ebp, dword ptr [esi + 0x0C]"),       # EBP = TItemList on this hot-spot
        ("i", "test ebp, ebp"), ("j", "jz", "done"),
        ("i", "mov eax, dword ptr [edi + 0x10]"),       # TAIGroupControl
        ("i", "test eax, eax"), ("j", "jz", "done"),
        ("i", "mov eax, dword ptr [eax + 0x0C]"),       # TAIGroup (a TUnitList)
        ("i", "test eax, eax"), ("j", "jz", "done"),
        ("i", "mov dword ptr [esp + 8], eax"),

        ("b", b"\xE8\x00\x00\x00\x00"),                 # call $+5
        ("i", "pop eax"),
        ("i", "mov eax, dword ptr [%s]" % _disp("eax", HEROREF_CELL, anchor)),
        ("i", "mov dword ptr [esp + 0x14], eax"),       # THero classref
        ("i", "xor eax, eax"),
        ("i", "mov dword ptr [esp], eax"),              # item index
        ("i", "mov dword ptr [esp + 4], eax"),          # best qualifying value

        ("L", "iloop"),
        ("i", "mov edx, dword ptr [esp]"),
        ("i", "mov eax, ebp"),
        ("c", GETITEM),
        ("i", "test eax, eax"), ("j", "jz", "have"),
        ("i", "mov dword ptr [esp + 0x0C], eax"),
        ("c", CAVE_VALUE),
        ("i", "mov dword ptr [esp + 0x10], eax"),
        ("i", "cmp eax, dword ptr [esp + 4]"), ("j", "jle", "inext"),
        ("i", "xor esi, esi"),                          # ESI = unit index within the asking group
        ("L", "uloop"),
        ("i", "mov eax, dword ptr [esp + 8]"),
        ("i", "mov edx, dword ptr [eax]"),
        ("i", "call dword ptr [edx + 0x%X]" % COUNT_SLOT),
        ("i", "cmp esi, eax"), ("j", "jge", "inext"),
        ("i", "mov eax, dword ptr [esp + 8]"),
        ("i", "mov edx, esi"),
        ("c", GETUNIT),
        ("i", "inc esi"),
        ("i", "test eax, eax"), ("j", "jz", "uloop"),
        ("i", "mov edi, eax"),                          # EDI = candidate unit
        ("i", "mov edx, dword ptr [esp + 0x14]"),
        ("c", ISCLASS),                                 # THero (so TLeader too); TUnit rejected
        ("i", "test al, al"), ("j", "jz", "uloop"),
        ("i", "mov eax, edi"),
        ("i", "mov edx, dword ptr [esp + 0x0C]"),
        ("i", "mov ecx, dword ptr [esp + 0x10]"),
        ("c", CAVE_WOULDTAKE),
        ("i", "test al, al"), ("j", "jz", "uloop"),
        ("i", "mov eax, dword ptr [esp + 0x10]"),
        ("i", "mov dword ptr [esp + 4], eax"),
        ("L", "inext"),
        ("i", "inc dword ptr [esp]"), ("j", "jmp", "iloop"),

        ("L", "have"),
        ("i", "mov eax, dword ptr [esp + 4]"),
        ("i", "test eax, eax"), ("j", "jle", "done"),
        ("i", "mov ecx, %d" % PRIO_DIV),
        ("i", "cdq"),
        ("i", "idiv ecx"),
        ("i", "cmp eax, %d" % PRIO_CAP), ("j", "jle", "clamped"),
        ("i", "mov eax, %d" % PRIO_CAP),
        ("L", "clamped"),
        ("i", "add eax, %d" % PRIO_BASE),
        ("i", "cmp dword ptr [ebx], eax"), ("j", "jge", "done"),   # max-combine, never lower
        ("i", "mov dword ptr [ebx], eax"),

        ("L", "done"),
        ("i", "add esp, 0x18"),
        ("i", "pop ebp"), ("i", "pop edi"), ("i", "pop esi"), ("i", "pop ebx"), ("i", "ret"),
    ], va)


def build_nt(va, _anchor=None):
    """Hook A wrapper.  Entered by the retargeted `call` at HOOK_NT_VA, returns to HOOK_NT_VA+5.

    ESI = hero and BL = turn player index provably survive the displaced call: vanilla itself does
    `cmp bl,[esi+0x24]` on return (0x55787FDC)."""
    return assemble([
        ("c", ABSNEWTURN),                              # displaced TAbstractUnit.NewTurn
        ("i", "cmp bl, byte ptr [esi + 0x24]"),         # only on this hero's owner's turn
        ("j", "jnz", "out"),
        ("i", "pushad"),
        ("i", "mov eax, esi"),
        ("c", CAVE_PICKUP),
        ("i", "popad"),
        ("L", "out"),
        ("i", "ret"),
    ], va)


def build_moved(va, anchor):
    """Hook B wrapper.  Entered by a jmp from HOOK_MV_VA; replays the displaced epilogue.

    EBX = the unit: vanilla does `mov eax,ebx` at 0x55780514, three instructions before the hook.
    The unit is stashed on the stack across the IsClass call so nothing depends on what that RTL
    helper preserves."""
    return assemble([
        ("i", "pushad"),
        ("i", "push ebx"),                              # stash the unit
        ("i", "mov eax, ebx"),
        ("b", b"\xE8\x00\x00\x00\x00"),                 # call $+5
        ("i", "pop edi"),
        ("i", "mov edx, dword ptr [%s]" % _disp("edi", HEROREF_CELL, anchor)),
        ("c", ISCLASS),                                 # THero (and therefore TLeader) only
        ("i", "pop ecx"),                               # ECX = the unit
        ("i", "test al, al"), ("j", "jz", "out"),
        ("i", "mov eax, ecx"),
        ("c", CAVE_PICKUP),
        ("L", "out"),
        ("i", "popad"),
        # replayed epilogue (the displaced 5 bytes); the `ret 4` that followed is untouched
        ("i", "pop edi"), ("i", "pop esi"), ("i", "pop ebx"), ("i", "pop ecx"), ("i", "pop ebp"),
        ("i", "ret 4"),
    ], va)


# ---------------------------------------------------------------- disassembly

def disasm(code, va, indent="      "):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return indent + code.hex()
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    out, seen = [], 0
    for i in md.disasm(code, va):
        out.append("%s%08x  %-22s %s %s" % (indent, i.address, i.bytes.hex(), i.mnemonic, i.op_str))
        seen += len(i.bytes)
    if seen != len(code):
        out.append("%s!! %d of %d bytes did not decode" % (indent, len(code) - seen, len(code)))
    return "\n".join(out)


# ---------------------------------------------------------------- self-checks

def selfcheck(blobs):
    """Standing safety checks that do not need the game.  Each returns a list of problems."""
    problems = []

    # (1) RNG lockstep: no cave here may draw from either generator, in any reachable form --
    #     call/jmp rel32, or a bare address constant reached through the rebase-delta idiom.
    SYNCED, RAW = 0x5577827C, 0x55701080
    for name, va, blob in blobs:
        for tgt, label in ((SYNCED, "TAoWHSMap.Random (SYNCED)"), (RAW, "@RandInt thunk (RAW)")):
            if struct.pack("<I", tgt) in blob:
                problems.append("%s embeds the address of %s" % (name, label))
            for i in range(len(blob) - 4):
                if blob[i] in (0xE8, 0xE9):
                    if va + i + 5 + struct.unpack_from("<i", blob, i + 1)[0] == tgt:
                        problems.append("%s calls/jumps to %s" % (name, label))

    # (2) no absolute drive-letter path may appear in anything we write into a binary
    for name, va, blob in blobs:
        if re.search(rb"[A-Za-z]:\\", blob):
            problems.append("%s contains a drive-letter absolute path" % name)

    # (3) caves must be position-independent -- the .dpl never loads at its preferred base.  This is
    #     checked INSTRUCTION-BY-INSTRUCTION, not by scanning raw dwords: a byte-window scan reports
    #     false positives on displacement/opcode boundaries.  Legal here: rel32 call/jmp (relative
    #     by construction) and register-relative memory.  Illegal: a pure-disp32 memory operand or
    #     an immediate holding a module VA.
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32, x86
    except ImportError:
        problems.append("capstone not installed -- cannot run the position-independence check")
        return problems
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    lo, hi = 0x55700000, 0x55A00000
    for name, va, blob in blobs:
        decoded = 0
        for ins in md.disasm(blob, va):
            decoded += len(ins.bytes)
            for op in ins.operands:
                if op.type == x86.X86_OP_IMM and lo <= op.imm < hi and ins.mnemonic not in (
                        "call", "jmp", "je", "jne", "jz", "jnz", "jl", "jle", "jg", "jge",
                        "jae", "jb", "jbe", "ja"):
                    problems.append("%s @%08x: absolute immediate %#x in `%s %s`"
                                    % (name, ins.address, op.imm, ins.mnemonic, ins.op_str))
                if op.type == x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0 \
                        and lo <= (op.mem.disp & 0xFFFFFFFF) < hi:
                    problems.append("%s @%08x: absolute memory ref in `%s %s`"
                                    % (name, ins.address, ins.mnemonic, ins.op_str))
        if decoded != len(blob):
            problems.append("%s: %d of %d bytes did not decode -- refusing to write it"
                            % (name, len(blob) - decoded, len(blob)))

    # (4) every global reached through the call/pop rebase anchor must land on a global we MEANT
    #     to reach.  A wrong anchor assembles, verifies and installs cleanly; it just reads the
    #     wrong address forever.  This resolves each `mov reg, [anchorreg + disp]` back to its VA.
    KNOWN = {MAP_GLOBAL: "AoWHSMap", HSSET_GLOBAL: "AoWHSSet",
             HEROREF_CELL: "THero classref", TABREF_CELL: "TAbility classref"}
    for name, va, blob in blobs:
        i = blob.find(b"\xE8\x00\x00\x00\x00")
        if i == -1:
            continue
        anchor = va + i + 5
        popreg = blob[i + 5] - 0x58            # 0=eax 1=ecx 2=edx 3=ebx 5=ebp 6=esi 7=edi
        creg = {0: x86.X86_REG_EAX, 1: x86.X86_REG_ECX, 2: x86.X86_REG_EDX, 3: x86.X86_REG_EBX,
                5: x86.X86_REG_EBP, 6: x86.X86_REG_ESI, 7: x86.X86_REG_EDI}.get(popreg)
        # Only while the anchor register is still LIVE: stop at the first instruction that writes
        # it or at the first call (after which a callee may have clobbered it).  Past that point
        # the register is ordinary scratch and its uses are not anchor-relative.
        seen = 0
        for ins in md.disasm(blob, va):
            if ins.address <= anchor:
                continue
            for op in ins.operands:
                if op.type == x86.X86_OP_MEM and op.mem.base == creg and op.mem.index == 0:
                    tgt = (anchor + op.mem.disp) & 0xFFFFFFFF
                    seen += 1
                    if tgt not in KNOWN:
                        problems.append("%s @%08x: anchor-relative ref resolves to %#x, which is "
                                        "not a global this feature uses (`%s %s`)"
                                        % (name, ins.address, tgt, ins.mnemonic, ins.op_str))
            _read, written = ins.regs_access()
            if ins.mnemonic == "call" or creg in written:
                break
        if not seen:
            problems.append("%s has a call/pop anchor but no anchor-relative reference" % name)
    return problems


# ---------------------------------------------------------------- main

def kill_game():
    """Standing authorization: the game and the editor lock the DLL.  Just kill them."""
    # ⚠ SCRATCH GUARD (2026-09-03): AOW_GAME_DIR set => we are NOT writing to the real
    # install, so we must NOT kill the user's running game. Without this, an agent doing a
    # "safe" scratch-copy round-trip still terminates the live game -- which happened, and
    # was misreported as a crash-on-expiry. Standing kill authorization applies to the real
    # install only.
    if os.environ.get("AOW_GAME_DIR"):
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match '^(AoW|AoWCompat|AoWDevEd|AoWEd)$' }"
         " | Stop-Process -Force"], capture_output=True)


def main():
    apply_mode = "--apply" in sys.argv
    undo_mode = "--undo" in sys.argv
    show = "--dis" in sys.argv or "--show" in sys.argv
    if apply_mode and undo_mode:
        sys.exit("ERROR: --apply and --undo are mutually exclusive.")

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s\n(set AOW_GAME_DIR to the game directory)" % DLL)
    data = bytearray(open(DLL, "rb").read())

    # ---- assemble ---------------------------------------------------------
    # Caves that reach a global through the call/pop rebase anchor get their anchor MEASURED from
    # the assembled bytes, never hand-counted -- see with_anchor().
    value = with_anchor(build_value, CAVE_VALUE)
    would = build_wouldtake(CAVE_WOULDTAKE)
    pick = with_anchor(build_pickup, CAVE_PICKUP)
    targ = with_anchor(build_target, CAVE_TARGET)
    cnt = build_nt(CAVE_NT)
    cmv = with_anchor(build_moved, CAVE_MOVED)
    blobs = [("cave_value", CAVE_VALUE, value), ("cave_wouldtake", CAVE_WOULDTAKE, would),
             ("cave_pickup", CAVE_PICKUP, pick), ("cave_target", CAVE_TARGET, targ),
             ("cave_nt", CAVE_NT, cnt), ("cave_moved", CAVE_MOVED, cmv)]
    by_name = dict((n, b) for n, _v, b in blobs)

    for (name, start, budget) in CAVES:
        blob = by_name[name]
        if len(blob) > budget:
            sys.exit("ABORT: %s is %d bytes and overruns its %d-byte budget at %#x."
                     % (name, len(blob), budget, start))

    hook_nt = b"\xE8" + struct.pack("<i", CAVE_NT - (HOOK_NT_VA + 5))
    hook_mv = b"\xE9" + struct.pack("<i", CAVE_MOVED - (HOOK_MV_VA + 5))
    want_slot = struct.pack("<I", CAVE_TARGET)

    nt_off = va_to_off(data, HOOK_NT_VA)
    mv_off = va_to_off(data, HOOK_MV_VA)
    slot_off = va_to_off(data, VMT_SLOT_VA)
    zone_off = va_to_off(data, ZONE_VA)

    cur_nt = bytes(data[nt_off:nt_off + 5])
    cur_mv = bytes(data[mv_off:mv_off + 5])
    cur_slot = bytes(data[slot_off:slot_off + 4])
    cur_zone = bytes(data[zone_off:zone_off + ZONE_LEN])

    want_zone = bytearray(b"\x00" * ZONE_LEN)
    for name, start, _budget in CAVES:
        blob = by_name[name]
        want_zone[start - ZONE_VA:start - ZONE_VA + len(blob)] = blob
    want_zone = bytes(want_zone)

    print("AI item loot -- pickup + upgrade-swap + group-aware ground-item AI targeting")
    print("target: %s   (cave zone %#010x..%#010x, %d KB reserved)\n"
          % (os.path.basename(DLL), ZONE_VA, ZONE_VA + ZONE_LEN, ZONE_LEN // 1024))

    # ---- ownership handover ----------------------------------------------
    def old_owner(cur, va):
        if cur[:1] not in (b"\xE8", b"\xE9"):
            return None
        t = va + 5 + struct.unpack_from("<i", cur, 1)[0]
        return t if OLD_ZONE_LO <= t < OLD_ZONE_HI else None

    old_nt, old_mv = old_owner(cur_nt, HOOK_NT_VA), old_owner(cur_mv, HOOK_MV_VA)
    handover = bool(old_nt or old_mv)

    # ---- state ------------------------------------------------------------
    def site_state(label, cur, orig, mine, va):
        if cur == orig:
            return "clean"
        if cur == mine:
            return "applied"
        if handover:
            return "OWNED BY " + OLD_PICKUP_SCRIPT
        sys.exit("ABORT: %s @ %#x holds %s\n  expected vanilla %s or ours %s.\n"
                 "  Another patch may own this site -- investigate before proceeding."
                 % (label, va, cur.hex(), orig.hex(), mine.hex()))

    st_nt = site_state("THero.NewTurn call", cur_nt, HOOK_NT_ORIG, hook_nt, HOOK_NT_VA)
    st_mv = site_state("TAbstractUnit.MovedTo epilogue", cur_mv, HOOK_MV_ORIG, hook_mv, HOOK_MV_VA)
    st_sl = site_state("TItemHS VMT+0xCC", cur_slot, SLOT_ORIG, want_slot, VMT_SLOT_VA)

    if cur_zone not in (b"\x00" * ZONE_LEN, want_zone) and any(cur_zone):
        # Not virgin and not exactly ours: allow a re-tune only if every non-zero byte lies inside
        # a cave slot we own, i.e. the zone holds a PREVIOUS version of our own caves.
        foreign = []
        for i, b in enumerate(cur_zone):
            if not b:
                continue
            va = ZONE_VA + i
            if not any(s <= va < s + n for _nm, s, n in CAVES):
                foreign.append(va)
        if foreign:
            sys.exit("ABORT: cave zone %#x..%#x holds %d non-zero byte(s) outside our cave slots, "
                     "first at %#x.\n  Someone else's cave may live here -- do not write."
                     % (ZONE_VA, ZONE_VA + ZONE_LEN, len(foreign), foreign[0]))
        print("NOTE: the zone holds a previous version of our own caves -- rewriting in place.\n")

    # ---- reloc safety on every displaced range ----------------------------
    for label, lo, n in (("hook A", HOOK_NT_VA, 5), ("hook B", HOOK_MV_VA, 5),
                         ("cave zone", ZONE_VA, ZONE_LEN)):
        hits = reloc_hits(data, lo, lo + n)
        if hits:
            sys.exit("ABORT: %s (%#x..%#x) carries %d .reloc fixup(s), first %#x -- overwriting "
                     "it would corrupt the image at load." % (label, lo, lo + n, len(hits), hits[0]))
    slot_reloc = reloc_hits(data, VMT_SLOT_VA, VMT_SLOT_VA + 4)

    # ---- self-checks ------------------------------------------------------
    problems = selfcheck(blobs)
    if problems:
        for p in problems:
            print("SELF-CHECK FAILED: %s" % p)
        sys.exit("ABORT: refusing to write caves that fail the standing safety checks.")

    # ---- report -----------------------------------------------------------
    for name, start, budget in CAVES:
        blob = by_name[name]
        print("%-14s @ %#010x  %4d / %4d bytes" % (name, start, len(blob), budget))
    print()
    print("hook A  %#010x  [%s]  retargets `call TAbstractUnit.NewTurn` -> cave_nt"
          % (HOOK_NT_VA, st_nt))
    print("        %s" % disasm(hook_nt, HOOK_NT_VA, ""))
    print("hook B  %#010x  [%s]  replaces the MovedTo epilogue pops -> cave_moved"
          % (HOOK_MV_VA, st_mv))
    print("        %s" % disasm(hook_mv, HOOK_MV_VA, ""))
    print("VMT     %#010x  [%s]  TItemHS+0xCC  %08X -> %08X   (reloc: %s)"
          % (VMT_SLOT_VA, st_sl, INHERITED, CAVE_TARGET, "yes" if slot_reloc else "NO"))
    print("\nvalue   = %d*ATK + %d*DEF + %d*DAM + %d*RES + sum(ExpandCost of granted abilities)"
          % (COST_ATT, COST_DEF, COST_DAM, COST_RES))
    print("priority= %d + min(bestQualifyingValue/%d, %d)  ->  %d..%d, max-combined into [rec+0]"
          % (PRIO_BASE, PRIO_DIV, PRIO_CAP, PRIO_BASE, PRIO_BASE + PRIO_CAP))
    print("self-checks: no RNG draw, no absolute VA, no drive-letter path in any cave -- OK")

    if show:
        for name, start, _b in CAVES:
            print("\n--- %s @ %#010x ---" % (name, start))
            print(disasm(by_name[name], start))

    if handover and undo_mode:
        # Surgical undo means "restore only what this script owns".  The hook sites currently
        # belong to the other script, so they are left exactly as they are; only the TItemHS VMT
        # slot and our own cave zone are reverted.
        print("\nNOTE: the hook sites belong to %s -- leaving them untouched." % OLD_PICKUP_SCRIPT)
        plan = []
        if any(cur_zone):
            plan.append(("caves", zone_off, cur_zone, b"\x00" * ZONE_LEN))
        if cur_slot != SLOT_ORIG:
            plan.append(("vmt slot", slot_off, cur_slot, SLOT_ORIG))
        if not plan:
            print("Nothing of ours is installed -- nothing to undo.")
            return 0
        for label, off, old, new in plan:
            assert bytes(data[off:off + len(old)]) == old, "verify-before-write failed at %#x" % off
            data[off:off + len(new)] = new
        try:
            with open(DLL, "wb") as fh:
                fh.write(data)
        except PermissionError:
            kill_game()
            with open(DLL, "wb") as fh:
                fh.write(data)
        print("UNDONE: TItemHS VMT+0xCC restored and the cave zone zeroed.  Hooks left alone.")
        return 0

    if handover:
        print("\n*** HOOK SITES ARE OWNED BY %s -- REFUSING ***\n" % OLD_PICKUP_SCRIPT)
        if old_nt:
            print("  %#010x  ->  %#010x   (that script's cave_nt @ %#010x)"
                  % (HOOK_NT_VA, old_nt, OLD_HOOK_NT))
        if old_mv:
            print("  %#010x  ->  %#010x   (that script's cave_moved @ %#010x)"
                  % (HOOK_MV_VA, old_mv, OLD_HOOK_MV))
        print("\nExactly one script may own a hook site.  Hand them back first:\n")
        print("    python build_scripts/%s --undo\n" % OLD_PICKUP_SCRIPT)
        print("  NOTE: that script currently implements only --apply -- it has no --undo/--revert")
        print("  flag, so the handover has to be done as three surgical writes:")
        print("      %#010x  <- E8 70 8D FF FF        (restore call TAbstractUnit.NewTurn)"
              % HOOK_NT_VA)
        print("      %#010x  <- 5F 5E 5B 59 5D        (restore the MovedTo epilogue pops)"
              % HOOK_MV_VA)
        print("      %#010x..%#010x  <- zero-fill  (that script's three caves)"
              % (OLD_ZONE_LO, OLD_ZONE_HI))
        print("\nThis script has written NOTHING and will not take those sites over silently.")
        return 2

    # ---- plan -------------------------------------------------------------
    if undo_mode:
        tgt_zone = b"\x00" * ZONE_LEN
        tgt_nt, tgt_mv, tgt_sl = HOOK_NT_ORIG, HOOK_MV_ORIG, SLOT_ORIG
        print("\n*** --undo: restoring both hooks and the TItemHS VMT slot, zeroing %d KB of cave "
              "zone.  No backup is touched." % (ZONE_LEN // 1024))
    else:
        tgt_zone, tgt_nt, tgt_mv, tgt_sl = want_zone, hook_nt, hook_mv, want_slot

    plan = []
    if cur_zone != tgt_zone:
        plan.append(("caves", zone_off, cur_zone, tgt_zone))
    if cur_nt != tgt_nt:
        plan.append(("hook A", nt_off, cur_nt, tgt_nt))
    if cur_mv != tgt_mv:
        plan.append(("hook B", mv_off, cur_mv, tgt_mv))
    if cur_slot != tgt_sl:
        plan.append(("vmt slot", slot_off, cur_slot, tgt_sl))

    if not plan:
        print("\nAlready in the requested state -- nothing to do.")
        return 0

    if not (apply_mode or undo_mode):
        print("\nDRY RUN -- %d write(s) planned.  Re-run with --apply to write." % len(plan))
        for label, off, old, new in plan:
            print("  %-9s file %#08x  %d bytes" % (label, off, len(new)))
        return 0

    # ---- write ------------------------------------------------------------
    if apply_mode:
        # Back up ONLY from a file proved to be un-patched by THIS feature.  A backup taken during
        # --undo, or over an existing install (a re-tune), would snapshot our own previous output
        # and sit on disk looking authoritative while containing a patched state.
        virgin = (cur_nt == HOOK_NT_ORIG and cur_mv == HOOK_MV_ORIG
                  and cur_slot == SLOT_ORIG and not any(cur_zone))
        if not virgin:
            print("backup SKIPPED: this DLL already carries part of this feature, so a snapshot "
                  "now would capture our own output, not a pre-feature state.")
        elif os.path.exists(BACKUP):
            print("backup already exists: %s (left as-is)" % os.path.basename(BACKUP))
        else:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(DLL, BACKUP)
            print("backup -> %s" % os.path.basename(BACKUP))

    for label, off, old, new in plan:
        assert bytes(data[off:off + len(old)]) == old, "verify-before-write failed at %#x" % off
        data[off:off + len(new)] = new

    try:
        with open(DLL, "wb") as fh:
            fh.write(data)
    except PermissionError:
        kill_game()
        try:
            with open(DLL, "wb") as fh:
                fh.write(data)
        except PermissionError:
            sys.exit("ERROR: %s is still locked after killing the AoW processes."
                     % os.path.basename(DLL))

    check = open(DLL, "rb").read()
    assert check[nt_off:nt_off + 5] == tgt_nt, "readback mismatch: hook A"
    assert check[mv_off:mv_off + 5] == tgt_mv, "readback mismatch: hook B"
    assert check[slot_off:slot_off + 4] == tgt_sl, "readback mismatch: vmt slot"
    assert check[zone_off:zone_off + ZONE_LEN] == tgt_zone, "readback mismatch: cave zone"

    if undo_mode:
        print("\nUNDONE and verified -- the DLL is back to vanilla at all three sites.")
        return 0

    print("\nAPPLIED and verified -- untested.  Needs an in-game test:")
    print("  * an AI hero standing on a BETTER item of a type it already wears swaps into it and")
    print("    the old item is left on the ground; an equal or worse item is ignored;")
    print("  * an empty equip slot is still filled by any matching item;")
    print("  * potions / wands (item type 6) go into the hero's backpack while it has room;")
    print("  * an AI group that contains a hero who could use a dropped item now WALKS to it;")
    print("  * an AI group with no hero, or whose heroes are all better equipped, does NOT.")
    print("  * humans are unaffected (gated on player+0xA7 != 0).")
    print("Then re-run: python \"Modding Resources/re_tools/rng_audit.py\" --owners")
    return 0


if __name__ == "__main__":
    sys.exit(main())
