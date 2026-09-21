#!/usr/bin/env python
"""
build_ai_itempickup.py — let AI heroes pick up ground items into a matching empty equip slot.

PROBLEM
-------
AI players have NO runtime item acquisition path at all.  Their heroes' gear is whatever the
scenario author gave them, minus whatever they permanently drop on death — static and monotonically
decreasing.  Full analysis in `Modding Resources/Investigation_AI_Item_Pickup.md`; the short form:

  * `THero.PlaceItem@0x55788e94` (the only producer of the "place item" token, and hence the only
    route an item takes *into* a live hero) has ZERO callers inside the DLL — it is driven solely by
    AoW.exe's `TUnitWindow` drag/drop UI.
  * `TItemHS` (a ground item) can never be an AI target: no `MapFieldMsgProc` (so it never receives
    the `0x1200` AI-target broadcast), no `UpdateAITarget`, no `GetDefaultAITargetPriority`.
  * `TAbstractUnit.MovedTo` performs no pickup, so there is no automatic pickup for anyone.

Items *leave* a hero engine-side (`THero.Killed` → `ExecutePlaceItem(hero,id,0xE)` for all 14 slots,
no token) but can only *enter* one through the exe.  This patch closes that asymmetry for the AI.

FIX
---
Two hooks call one shared worker.  For an AI-owned hero on the strategic map, the worker walks the
six equip slots and, for each, looks for an item lying on the hero's own hex that fits:

    for p in 0..5:
        list = THero.GetItemsOnGround(hero)          # NULL when the hex holds no item hot-spot
        for i in 0..:
            item = TItemList.GetItem(list, i)        # bounds-checked, returns 0 past the end
            if THeroItems.CanPlaceItem(hero+0x70, item, p):
                THero.ExecutePlaceItem(hero, item.ID, p);  break   # list may now be FREED

`THeroItems.CanPlaceItem@0x5578674c` IS the whole predicate the feature needs — it already enforces
`pos < 6` (equip slots only), `GetPositionItem(pos) == 0` (slot empty) and
`GetPositionItemType(pos) == item.type` (correct type).  Nothing is hand-rolled.

Deliberately NOT used: `THeroItems.GetItemTypePosition@0x55786740`.  It is an unchecked 7-byte table
read (`0x558e8db8` = 01 04 00 02 03 0F 0F, immediately followed by an unrelated bitmask table), and
more importantly the tables are asymmetric — the inverse table `0x558e8db0` = 02 00 03 04 01 04 shows
**item type 4 owns TWO slots (3 and 5)** while GetItemTypePosition can only ever return 3.  Scanning
0..5 reaches slot 5; the table lookup cannot.  The scan also compares the type rather than indexing
by it, so a malformed item type can never produce an out-of-range read.

No backpack fallback: equip slots only, by design.  An AI can never re-equip from its backpack, so a
stashed item would be dead weight.

WHY DIRECT EXECUTION, NOT A TOKEN
---------------------------------
`ExecutePlaceItem` is called directly rather than going through `THero.PlaceItem` (which mints a
`THeroUpdateTE` token).  This is correct, and it is what makes the slot scan exact — a token path
would let two items be queued into the same slot in one pass, the second silently failing later.

It is also MP-safe at *these two injection points specifically*, because both run on every peer:

  * `THero.NewTurn` has no direct callers; it is reached by message broadcast — `TAbstractUnit.MsgProc
    @0x55781238` dispatches msg 0x20020002 to unit VMT +0x13c.  The chain from
    `TEndTurnTE.Execute@0x557473c4` onward has no locality gate (at 0x55747431 the
    `CALL [ECX+0x84]` result is discarded, not tested).
  * `TAbstractUnit.MovedTo` is reached from `TMoveArmyTE.ExecuteMove@0x557481fc` →
    `TArmyHS.MoveTo@0x55791068` → `TArmy.MovedTo@0x5578de24`, which explicitly iterates army members
    calling each one's VMT +0x18c.  A hero inside a moving army does receive it.

`ExecutePlaceItem` itself is side-effect-clean: no RNG, no event log, no sound, no dialog, no token,
no `map+0xA5` (local-player) read.  Its only non-state effect is `THero.Changed` (VMT +0x90 — stat
recompute plus a UI notify), which `TAbstractUnit.Killed` already calls unconditionally on all peers.
Engine precedent for untokenised placement: `THero.Killed@0x55787164`.

A manual token mint would be actively WRONG here: since the injection points run on every peer, every
peer would mint the token, giving N pickups (or an exception on the non-authoritative peers).

SAFETY
------
  * Slots are the OUTER loop and the ground list is refetched per slot, with an immediate break after
    a successful placement.  This matters: `TItemHS.ItemsChanged@0x55795d10` calls `[VMT-4]`
    (Destroy) when the list empties, freeing the TItemHS *and its TItemList* — so the list pointer is
    dead the instant a pickup succeeds.  Nothing is touched after a mutation, and it terminates in
    <= 6 passes.  Only item IDs (integers) ever cross a mutation boundary, never pointers.
  * `GetItemsOnGround` returns NULL on any hex with no item hot-spot (i.e. almost every hex) — null
    checked before use.
  * `TPlayerList.GetPlayers` is bounds-checked and returns 0 out of range — null checked.
  * Gated on `map+0x11c == 0` (strategic map only).  Nonzero = tactical combat, where
    `THero.CanPlaceItem` skips its co-location test.
  * Gated on `player+0xa7 != 0` (AI).  0 = human — humans keep using the normal UI.
  * Hook B additionally gates on `IsClass(unit, THero)`, since `MovedTo` fires for every unit.
    `TLeader` parents to `THero` (VMT chain 0x55712238 -> 0x55711fec) so the wizard/leader is
    included; `TUnit` parents directly to `TAbstractUnit` and is correctly rejected.

Caves are position-independent (rel32 calls, register-indirect, call/pop delta for the two globals),
as required for the rebasing .dpl.

SCOPE
-----
Opportunistic only.  `TItemHS` cannot be an AI target, so the AI never *paths toward* an item — it
picks up what it happens to stand on.  In vanilla the AI also never searches exploration sites
(`TStructure.ExecuteAI@0x5575e698` is a bare `return 0` for all seven site VMTs), so the main source
of reachable ground items is dead heroes' drops — including the AI's own.

USAGE
-----
    python build_scripts/build_ai_itempickup.py                  # dry run / verify current state
    python build_scripts/build_ai_itempickup.py --apply          # write (auto-backup .pre-aipickup)
    python build_scripts/build_ai_itempickup.py --undo           # dry run of the surgical revert
    python build_scripts/build_ai_itempickup.py --undo --apply   # write the revert

Close AoW.exe / AoWCompat.exe / AoWDevEd.exe first — they lock the DLL.

REVERT — `--undo --apply`, never a snapshot
-------------------------------------------
`--undo` is surgical: it restores the two displaced hook sites to their vanilla bytes and zeroes
this script's own cave zone (0x55810000..0x55810180), touching no backup file. `--apply` remains the
write switch, so `--undo` on its own only reports — same dry-run-by-default contract as apply.

Every write is verify-before-write, reusing `site_state()`: it refuses if a hook site holds neither
the vanilla run nor this script's own hook, and the pre-existing cave-zone guard means the zone can
only ever be zeroed when it holds exactly this script's caves (or is already zero). So a foreign
patch layered on top of either site aborts the undo rather than being silently clobbered.

Do NOT revert by restoring a `.pre-*` snapshot. There is no `AoWEPACK.dpl.pre-aipickup` on disk, and
a snapshot restore would in any case wipe every feature layered onto the DLL afterwards — see
Investigation_AI_Item_Pickup.md "Revert-layer lesson".

⚠ This script and `build_ai_itemloot.py` both want hook sites 0x55787FD7 and 0x5578051B, and exactly
one may own them. `build_ai_itemloot.py` supersedes this script; run `--undo --apply` here before
applying that one. (It detects this state and refuses rather than taking the sites over silently.)
"""

import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-aipickup")
BASE = 0x55700000

# ---- call targets (all verified present in the live DLL) --------------------
GETPLAYERS  = 0x557544D0   # TPlayerList.GetPlayers(EAX=list, EDX=idx) -> EAX (0 if out of range)
GETITEMS    = 0x55788C7C   # THero.GetItemsOnGround(EAX=hero) -> EAX = TItemList* or 0
GETITEM     = 0x55794A2C   # TItemList.GetItem(EAX=list, EDX=i)  -> EAX = TItem* or 0
CANPLACE    = 0x5578674C   # THeroItems.CanPlaceItem(EAX=items, EDX=item, ECX=pos) -> AL
EXECPLACE   = 0x5578907C   # THero.ExecutePlaceItem(EAX=hero, EDX=itemID, ECX=pos)
ISCLASS     = 0x557010C0   # System.@IsClass(EAX=obj, EDX=classref) -> AL  (thunk into VCL30)
ABSNEWTURN  = 0x55780D4C   # TAbstractUnit.NewTurn(EAX=unit, EDX=playerIdx)  [displaced by hook A]

# ---- globals reached via the call/pop delta anchor --------------------------
MAP_GLOBAL   = 0x558FA040  # AoWHSMap*
HEROREF_CELL = 0x55711FAC  # cell holding the THero class reference (= VMT 0x55711fec)

# ---- hook sites ------------------------------------------------------------
HOOK_NT_VA = 0x55787FD7    # THero.NewTurn: call TAbstractUnit.NewTurn
HOOK_NT_ORIG = bytes([0xE8, 0x70, 0x8D, 0xFF, 0xFF])

HOOK_MV_VA = 0x5578051B    # TAbstractUnit.MovedTo epilogue: pop edi/esi/ebx/ecx/ebp
HOOK_MV_ORIG = bytes([0x5F, 0x5E, 0x5B, 0x59, 0x5D])

# ---- caves (big verified zero run; content ends 0x5580f959) -----------------
CAVE_PICKUP = 0x55810000
CAVE_NT     = 0x55810100
CAVE_MOVED  = 0x55810140
ZONE_VA, ZONE_LEN = 0x55810000, 0x180


# ---------------------------------------------------------------- PE helpers

def pe_sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    tbl = pe + 24 + optsz
    out = []
    for i in range(nsec):
        o = tbl + i * 40
        out.append((
            struct.unpack_from("<I", data, o + 12)[0],   # vaddr
            struct.unpack_from("<I", data, o + 8)[0],    # vsize
            struct.unpack_from("<I", data, o + 20)[0],   # praw
            struct.unpack_from("<I", data, o + 16)[0],   # rsize
        ))
    return out


def va_to_off(data, va):
    rva = va - BASE
    for vaddr, vsize, praw, rsize in pe_sections(data):
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return praw + (rva - vaddr)
    raise ValueError("VA %#x is not in any section" % va)


# ------------------------------------------------------- tiny two-pass asm
#
# Item kinds:
#   ("i", "instr")    keystone-assembled, VA-independent encoding
#   ("c", target_va)  call rel32                       (5 bytes)
#   ("j", cc, label)  jump rel32; cc "jmp" = 5 bytes, conditional = 6 bytes
#   ("L", name)       label
#   ("b", raw_bytes)  literal bytes
#
# All jumps are forced to rel32 so sizes are fixed and the two passes agree.

_CC = {"jz": b"\x0F\x84", "jnz": b"\x0F\x85", "jl": b"\x0F\x8C", "jmp": b"\xE9"}


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

    # pass 1 — label addresses
    pos, labels = base_va, {}
    for idx, it in enumerate(items):
        if it[0] == "L":
            labels[it[1]] = pos
        pos += size(idx, it)

    # pass 2 — emit
    out, pos = bytearray(), base_va
    for idx, it in enumerate(items):
        n = size(idx, it)
        if it[0] in ("i", "b"):
            out += enc[idx]
        elif it[0] == "c":
            out += b"\xE8" + struct.pack("<i", it[1] - (pos + 5))
        elif it[0] == "j":
            op = _CC[it[1]]
            out += op + struct.pack("<i", labels[it[2]] - (pos + n))
        pos += n
    return bytes(out)


def _disp(name, target, anchor):
    d = target - anchor
    return "%s %s 0x%X" % (name, "+" if d >= 0 else "-", abs(d))


# ---------------------------------------------------------------- cave build

def build_pickup(va):
    """Shared worker.  IN: EAX = THero*.  Clobbers EAX/ECX/EDX; preserves EBX/ESI/EDI/EBP."""
    anchor = va + 11        # after push*4 (4) + mov ebp,eax (2) + call $+5 (5)
    return assemble([
        ("i", "push ebx"), ("i", "push esi"), ("i", "push edi"), ("i", "push ebp"),
        ("i", "mov ebp, eax"),                       # EBP = hero, survives every call
        ("b", b"\xE8\x00\x00\x00\x00"),              # call $+5
        ("i", "pop edi"),                            # EDI = runtime VA of the anchor
        ("i", "mov eax, dword ptr [%s]" % _disp("edi", MAP_GLOBAL, anchor)),
        ("i", "test eax, eax"), ("j", "jz", "done"),
        ("i", "cmp dword ptr [eax + 0x11c], 0"),     # strategic map only
        ("j", "jnz", "done"),
        ("i", "mov eax, dword ptr [eax + 0x140]"),   # TPlayerList*
        ("i", "movsx edx, byte ptr [ebp + 0x24]"),   # hero owner index (signed)
        ("c", GETPLAYERS),
        ("i", "test eax, eax"), ("j", "jz", "done"), # bounds-checked -> may be 0
        ("i", "cmp byte ptr [eax + 0xa7], 0"),       # 0 = human -> leave it to the UI
        ("j", "jz", "done"),
        ("i", "cmp dword ptr [ebp + 0x70], 0"),      # THeroItems present?
        ("j", "jz", "done"),
        ("i", "xor edi, edi"),                       # EDI = slot p

        ("L", "slot"),
        ("i", "mov eax, ebp"),
        ("c", GETITEMS),                             # refetched per slot: may have been freed
        ("i", "test eax, eax"), ("j", "jz", "done"),
        ("i", "mov ebx, eax"),                       # EBX = TItemList*
        ("i", "xor esi, esi"),                       # ESI = item index

        ("L", "item"),
        ("i", "mov edx, esi"), ("i", "mov eax, ebx"),
        ("c", GETITEM),                              # bounds-checked -> 0 past the end
        ("i", "test eax, eax"), ("j", "jz", "nextslot"),
        ("i", "mov edx, eax"),
        ("i", "push edx"),                           # CanPlaceItem clobbers EDX
        ("i", "mov ecx, edi"),
        ("i", "mov eax, dword ptr [ebp + 0x70]"),
        ("c", CANPLACE),                             # slot<6 + empty + type match
        ("i", "pop edx"),
        ("i", "test al, al"), ("j", "jz", "nextitem"),
        ("i", "mov edx, dword ptr [edx + 0x14]"),    # item ID (integer, never a pointer)
        ("i", "mov ecx, edi"),
        ("i", "mov eax, ebp"),
        ("c", EXECPLACE),
        ("j", "jmp", "nextslot"),                    # list may be FREED - never touch EBX again

        ("L", "nextitem"),
        ("i", "inc esi"), ("j", "jmp", "item"),

        ("L", "nextslot"),
        ("i", "inc edi"), ("i", "cmp edi, 6"), ("j", "jl", "slot"),

        ("L", "done"),
        ("i", "pop ebp"), ("i", "pop edi"), ("i", "pop esi"), ("i", "pop ebx"), ("i", "ret"),
    ], va)


def build_nt(va):
    """Hook A wrapper.  Entered by the retargeted call at HOOK_NT_VA; returns to HOOK_NT_VA+5.

    EAX = hero and EDX = turn player are already set by vanilla.  ESI = hero and BL = turn player
    provably survive the displaced call: vanilla itself does CMP BL,[ESI+0x24] on return."""
    return assemble([
        ("c", ABSNEWTURN),                           # displaced TAbstractUnit.NewTurn
        ("i", "cmp bl, byte ptr [esi + 0x24]"),      # only on this hero's owner's turn
        ("j", "jnz", "out"),
        ("i", "pushad"),
        ("i", "mov eax, esi"),
        ("c", CAVE_PICKUP),
        ("i", "popad"),
        ("L", "out"),
        ("i", "ret"),
    ], va)


def build_moved(va):
    """Hook B wrapper.  Entered by a jmp from HOOK_MV_VA; replays the displaced epilogue.

    EBX = unit, live since 0x55780334 (vanilla does MOV EAX,EBX at 0x55780516, three instructions
    before the hook).  The unit is stashed on the stack across the IsClass call so nothing depends
    on what that RTL helper preserves."""
    anchor = va + 9         # after pushad (1) + push ebx (1) + mov eax,ebx (2) + call $+5 (5)
    return assemble([
        ("i", "pushad"),
        ("i", "push ebx"),                           # stash the unit
        ("i", "mov eax, ebx"),
        ("b", b"\xE8\x00\x00\x00\x00"),              # call $+5
        ("i", "pop edi"),
        ("i", "mov edx, dword ptr [%s]" % _disp("edi", HEROREF_CELL, anchor)),
        ("c", ISCLASS),                              # THero (and therefore TLeader) only
        ("i", "pop ecx"),                            # ECX = unit
        ("i", "test al, al"), ("j", "jz", "out"),
        ("i", "mov eax, ecx"),
        ("c", CAVE_PICKUP),
        ("L", "out"),
        ("i", "popad"),
        # replayed epilogue (the displaced 5 bytes) + the untouched ret 4 that followed
        ("i", "pop edi"), ("i", "pop esi"), ("i", "pop ebx"), ("i", "pop ecx"), ("i", "pop ebp"),
        ("i", "ret 4"),
    ], va)


def build_hook_call(site_va, cave_va):
    return b"\xE8" + struct.pack("<i", cave_va - (site_va + 5))


def build_hook_jmp(site_va, cave_va):
    return b"\xE9" + struct.pack("<i", cave_va - (site_va + 5))


def disasm(code, va, indent="      "):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return indent + code.hex()
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    return "\n".join("%s%08x  %-20s %s %s" % (indent, i.address, i.bytes.hex(), i.mnemonic, i.op_str)
                     for i in md.disasm(code, va))


# ---------------------------------------------------------------- main

def main():
    apply_mode = "--apply" in sys.argv
    # --undo picks the DIRECTION; --apply stays the write switch, so `--undo` alone is a dry run
    # exactly as a bare invocation is.
    undo_mode = "--undo" in sys.argv

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s\n(set AOW_GAME_DIR to the game directory)" % DLL)

    data = bytearray(open(DLL, "rb").read())

    pickup = build_pickup(CAVE_PICKUP)
    cnt = build_nt(CAVE_NT)
    cmv = build_moved(CAVE_MOVED)

    for name, blob, start, limit in (("cave_pickup", pickup, CAVE_PICKUP, CAVE_NT),
                                     ("cave_nt", cnt, CAVE_NT, CAVE_MOVED),
                                     ("cave_moved", cmv, CAVE_MOVED, ZONE_VA + ZONE_LEN)):
        if start + len(blob) > limit:
            sys.exit("ABORT: %s is %d bytes and overruns its slot (%#x..%#x)."
                     % (name, len(blob), start, limit))

    hook_nt = build_hook_call(HOOK_NT_VA, CAVE_NT)
    hook_mv = build_hook_jmp(HOOK_MV_VA, CAVE_MOVED)

    nt_off = va_to_off(data, HOOK_NT_VA)
    mv_off = va_to_off(data, HOOK_MV_VA)
    zone_off = va_to_off(data, ZONE_VA)

    cur_nt = bytes(data[nt_off:nt_off + 5])
    cur_mv = bytes(data[mv_off:mv_off + 5])

    def site_state(label, cur, orig, hook, va):
        if cur == orig:
            return "clean"
        if cur == hook:
            return "applied"
        sys.exit("ABORT: %s @ %#x has unexpected bytes %s\n"
                 "  expected original %s or our hook %s.\n"
                 "  Another patch may own this site — investigate before proceeding."
                 % (label, va, cur.hex(), orig.hex(), hook.hex()))

    st_nt = site_state("THero.NewTurn", cur_nt, HOOK_NT_ORIG, hook_nt, HOOK_NT_VA)
    st_mv = site_state("TAbstractUnit.MovedTo", cur_mv, HOOK_MV_ORIG, hook_mv, HOOK_MV_VA)

    # cave zone must be untouched zero-fill, or already hold exactly our caves
    want_zone = bytearray(b"\x00" * ZONE_LEN)
    want_zone[CAVE_PICKUP - ZONE_VA:CAVE_PICKUP - ZONE_VA + len(pickup)] = pickup
    want_zone[CAVE_NT - ZONE_VA:CAVE_NT - ZONE_VA + len(cnt)] = cnt
    want_zone[CAVE_MOVED - ZONE_VA:CAVE_MOVED - ZONE_VA + len(cmv)] = cmv
    cur_zone = bytes(data[zone_off:zone_off + ZONE_LEN])
    if cur_zone != bytes(want_zone) and any(cur_zone):
        sys.exit("ABORT: cave zone %#x..%#x is neither zero-fill nor our caves.\n"
                 "  Someone else's cave may live here — pick a different CAVE address."
                 % (ZONE_VA, ZONE_VA + ZONE_LEN))

    print("AI hero ground-item pickup  (equip slots only, no backpack fallback)\n")
    print("cave_pickup @ %#010x  %3d bytes   shared worker (EAX = THero*)" % (CAVE_PICKUP, len(pickup)))
    print(disasm(pickup, CAVE_PICKUP))
    print("\ncave_nt     @ %#010x  %3d bytes   hook A: THero.NewTurn        [%s]"
          % (CAVE_NT, len(cnt), st_nt))
    print(disasm(cnt, CAVE_NT))
    print("\ncave_moved  @ %#010x  %3d bytes   hook B: MovedTo epilogue     [%s]"
          % (CAVE_MOVED, len(cmv), st_mv))
    print(disasm(cmv, CAVE_MOVED))
    print("\nhook A @ %#010x (retargets the call to TAbstractUnit.NewTurn):" % HOOK_NT_VA)
    print(disasm(hook_nt, HOOK_NT_VA))
    print("hook B @ %#010x (replaces the 5 pop bytes; cave replays them):" % HOOK_MV_VA)
    print(disasm(hook_mv, HOOK_MV_VA))
    print()

    if undo_mode:
        print("*** --undo: restoring both hook sites to vanilla and zeroing %#010x..%#010x."
              % (ZONE_VA, ZONE_VA + ZONE_LEN))
        print("    No backup file is read or written.\n")

    plan = []
    if undo_mode:
        # Surgical revert. The two hook sites have already been proved by site_state() to hold
        # either the vanilla run or our own hook, and the cave-zone guard above has already proved
        # the zone is either zero-fill or exactly our caves — so nothing here can clobber a foreign
        # patch. The assert restates the second of those as a hard stop, because zeroing 0x180 bytes
        # on a wrong assumption is the one write in this script that cannot be reasoned back from.
        zero_zone = b"\x00" * ZONE_LEN
        if cur_zone != zero_zone:
            assert cur_zone == bytes(want_zone), \
                "refusing to zero a cave zone that is not exactly ours"
            plan.append(("caves", zone_off, cur_zone, zero_zone))
        if st_nt == "applied":
            plan.append(("hook A", nt_off, cur_nt, HOOK_NT_ORIG))
        if st_mv == "applied":
            plan.append(("hook B", mv_off, cur_mv, HOOK_MV_ORIG))
    else:
        if cur_zone != bytes(want_zone):
            plan.append(("caves", zone_off, cur_zone, bytes(want_zone)))
        if st_nt == "clean":
            plan.append(("hook A", nt_off, cur_nt, hook_nt))
        if st_mv == "clean":
            plan.append(("hook B", mv_off, cur_mv, hook_mv))

    if not plan:
        print("Not applied — nothing to undo." if undo_mode
              else "Already patched and caves match — nothing to do.")
        return

    if not apply_mode:
        print("DRY RUN — %d %swrite(s) planned. Re-run with %s to write."
              % (len(plan), "revert " if undo_mode else "",
                 "--undo --apply" if undo_mode else "--apply"))
        for label, off, old, new in plan:
            print("  %-8s file %#08x  %d bytes" % (label, off, len(new)))
        return

    # ---- apply / undo
    # The undo path deliberately takes NO backup: the current file is the patched state by
    # definition, so a snapshot here would mint a `.pre-aipickup` that looks authoritative while
    # containing a patched DLL. A backup is only ever taken from a file that is un-patched.
    if undo_mode:
        pass
    elif not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("backup -> %s" % os.path.basename(BACKUP))
    else:
        print("backup already exists: %s (left as-is)" % os.path.basename(BACKUP))

    for label, off, old, new in plan:
        assert bytes(data[off:off + len(old)]) == old, "verify-before-write failed at %#x" % off
        data[off:off + len(new)] = new

    try:
        with open(DLL, "wb") as fh:
            fh.write(data)
    except PermissionError:
        sys.exit("ERROR: %s is locked. Close AoW.exe / AoWCompat.exe / AoWDevEd.exe and retry."
                 % os.path.basename(DLL))

    check = open(DLL, "rb").read()
    want_nt = HOOK_NT_ORIG if undo_mode else hook_nt
    want_mv = HOOK_MV_ORIG if undo_mode else hook_mv
    want_cav = b"\x00" * ZONE_LEN if undo_mode else bytes(want_zone)
    assert check[nt_off:nt_off + 5] == want_nt, "readback mismatch: hook A"
    assert check[mv_off:mv_off + 5] == want_mv, "readback mismatch: hook B"
    assert check[zone_off:zone_off + ZONE_LEN] == want_cav, "readback mismatch: caves"

    if undo_mode:
        print("\nREVERTED and verified — both hook sites are vanilla again and the cave zone")
        print("%#010x..%#010x is zero-fill. No backup file was read or written." % (ZONE_VA, ZONE_VA + ZONE_LEN))
        print("AI heroes no longer pick up ground items; this is stock behaviour, not a fix.")
        return

    print("\nAPPLIED and verified.")
    print("TEST: give an AI player a hero, drop an item on a hex it will walk over (or let an AI")
    print("hero die so its gear drops, then send another AI hero across that hex).  The item should")
    print("vanish from the ground and appear in the matching equip slot — visible on the hero's")
    print("info card, and its ATK/DEF/DAM/RES should change accordingly.")
    print("Humans are unaffected (gated on player+0xa7 != 0).")


if __name__ == "__main__":
    main()
