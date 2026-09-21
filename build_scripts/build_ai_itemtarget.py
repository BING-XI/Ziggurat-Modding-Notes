#!/usr/bin/env python
"""
build_ai_itemtarget.py — make ground items valid AI targets, so AI heroes path toward them.

Companion to `build_ai_itempickup.py` (CONFIRMED WORKING 2026-07-21), which already makes an AI hero
*standing on* a hex equip a matching item.  That patch supplied the pickup half; this one supplies
the movement half — the AI now has a reason to walk there.

PROBLEM
-------
`TItemHS` (the ground-item hot-spot, class id 0x20271) never registers as an AI target, so the AI
never paths to an item.  Full analysis in `Modding Resources/Investigation_AI_Item_Pickup.md` §3.3.

AI target discovery: `TAoWMapField.GetAITarget@0x55771d84` zeroes a 24-byte result record, broadcasts
map-field message **0x1200**, and returns `record[0] != 0`.  Handlers max-accumulate a priority into
`record[0]`, which lands at `TAIGroupControlTarget+0x18` and is sorted DESCENDING by
`SortOnPriority@0x557381ac`.

`TItemHS` DOES receive 0x1200 — it inherits `THexagonSprite.MapFieldMsgProc` (VMT +0xCC, currently the
HSEPack thunk `0x55701d4c`) and silently ignores the message.  It simply contributes nothing, so the
record stays 0 and the field is never a target.

FIX
---
Repoint `TItemHS` VMT **+0xCC** (VA `0x55710244`) to a cave that chains to the inherited handler, then
answers 0x1200 with a priority derived from the items lying on the hex.

Modelled verbatim on `TArmyHS.MapFieldMsgProc@0x55791c30` — a non-structure hot-spot that does exactly
this: chain to parent, guard on `msg[6] == 0`, then for 0x1200 compute the priority inline.  **No new
virtual slot is needed** (`TArmyHS` calls `TArmy.UpdateAITarget@0x55790618` directly rather than
through a VMT slot).

Message record (msg is int*):  `[0]` msgid · `[1]` TMapField* · `[2]` query ctx · `[3]` result rec ·
`[4]` TAIGroupControl* · `[6]` hex sub-index · `[7]` stop-propagation.
Query ctx is 3 bytes: `[0]` player index, `[1]` relation, `[2]` **mode** (0 = normal target search,
set by `TAIGroupTargetFinder.Setup@0x5573a298`).
Result rec `[0]` = priority.  **Only `record[0]` is written** — `+0x08`/`+0x0C` are gold/mana cost and
writing them would make the AI try to spend resources it does not owe via `MakeTargetExpense`.

PRIORITY
--------
`p = 10 + min(maxObtainValue / 10, 20)` → **10..30**, max-combined (`if (*out < p) *out = p`, the same
combine `TCity` uses — NOT plain assignment, which would clobber a higher-priority hot-spot on the
same field).  `TItem.GetObtainValue@0x557945b4` = `max(item+0x2c, 10)`.

Observed vanilla priority scale, for calibration:
    TPlayerStructure 10 flat · TAltar byte[+0x41]*10+10 · enemy army 50 · army with hero 100 ·
    army with wizard 300 · enemy/neutral city (size-1)*10+100 = 100..130 · own-city defence 600..1000+
So an item outranks a bare player-structure and loses to every army and city — it wins only when
nothing else is in reach.  Reach is naturally bounded: `TAIMoveTargetSelector` floods movement with a
250-field budget (100 for transport), so only items within practical travel distance are ever seen.

DELIBERATELY NOT DONE
---------------------
* **No visibility/fog gate.**  Vanilla AI targeting does not gate on fog anywhere —
  `TMine.UpdateAITarget@0x557b4498` checks only ownership and diplomatic relation, and `TCity`'s
  `byte[city+0x44] & 2` is a city state flag, not a per-player seen test.  Adding one here would make
  items behave differently from every other target type.  (`TPlayer.PlayerSeen@0x55753664` is a
  SETTER that marks a hex seen — it is not a query, and must not be used as one.)
* **No hero-only group filter.**  `msg[4]` is the `TAIGroupControl` and its `+0xC` is a `TAIGroup`
  (itself a `TUnitList`), so filtering to hero-bearing groups is possible — but priority tuning is the
  cheaper, safer lever.  Add the filter only if testing shows military stacks detouring for loot.

KNOWN RISKS (in-game observation needed — not resolvable statically)
--------------------------------------------------------------------
1. **Delivery assumption (~90%).**  `SendMapFieldMsg` lives in HSEPack.dpl, which Ghidra does not
   have, so it is not statically proven that 0x1200 reaches a `TSingleHS` hot-spot.  The evidence is
   `TArmyHS` — a single-hex `THexagonSprite` descendant that receives 0x1200 at the same +0xCC slot
   and demonstrably works (the AI targets armies).  If the AI ignores items after this patch, that
   assumption is the first thing to test.
2. **Unequippable-item oscillation.**  The pickup patch only fills an *empty equip slot of matching
   type*.  A hero that walks to an item it cannot take leaves it on the ground, where it remains a
   valid target.  Low priority makes this cheap rather than harmful, but watch for a hero loitering.
   Mitigation if seen: return 0 unless some hero in the asking group can actually take the item.

Cave is position-independent (rel32 calls only, no absolute memory refs).  The VMT slot carries a
`.reloc` HIGHLOW fixup, so writing a cave VA there rebases correctly — this is the project's
"reuse a VMT slot that already has a reloc entry" pattern.

⚠ Do NOT point this slot at `TStructure.MapFieldMsgProc@0x5575f730`: that handler calls VMT slots
+0x1c4/+0x188/+0x184/+0x180/+0x170/+0x16c, all past the end of TItemHS's 68-slot (0x110-byte) VMT —
they land in the NEXT class's table — and reads `self+0x2c`, past the 20-byte instance.

USAGE
-----
    python build_scripts/build_ai_itemtarget.py            # dry run / verify current state
    python build_scripts/build_ai_itemtarget.py --apply    # write (auto-backup .pre-aiitemtarget)

Close AoW.exe / AoWCompat.exe / AoWDevEd.exe first — they lock the DLL.
Revert = --revert (SURGICAL: restores TItemHS VMT+0xCC and zeroes the cave, no backup touched).
A whole-file .pre-* restore is NOT a revert path: it would wipe every feature applied after the
snapshot was taken. There is no snapshot layer at all now -- both stacks were purged (2026-08-08
and 2026-09-09) -- and any snapshot this script mints goes to <game dir>/backups/.
"""

import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-aiitemtarget")
BASE = 0x55700000

# ---- call targets (verified present) ---------------------------------------
INHERITED   = 0x55701D4C   # THexagonSprite.MapFieldMsgProc thunk (JMP [0x558FC078])
GETITEM     = 0x55794A2C   # TItemList.GetItem(EAX=list, EDX=i) -> EAX (0 past end, bounds-checked)
GETOBTAIN   = 0x557945B4   # TItem.GetObtainValue(EAX=item)     -> EAX = max(item+0x2c, 10)

# ---- hook: TItemHS VMT +0xCC ----------------------------------------------
# classref cell 0x55710138 -> VMT base 0x55710178; +0xCC = 0x55710244
VMT_SLOT_VA = 0x55710244
SLOT_ORIG = struct.pack("<I", INHERITED)

CAVE = 0x55810200          # high-water before this patch: 0x5581016E (end of build_ai_itempickup)
CAVE_BUDGET = 0x100

MSG_ID = 0x1200


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
            struct.unpack_from("<I", data, o + 12)[0],
            struct.unpack_from("<I", data, o + 8)[0],
            struct.unpack_from("<I", data, o + 20)[0],
            struct.unpack_from("<I", data, o + 16)[0],
        ))
    return out


def va_to_off(data, va):
    rva = va - BASE
    for vaddr, vsize, praw, rsize in pe_sections(data):
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return praw + (rva - vaddr)
    raise ValueError("VA %#x is not in any section" % va)


# ------------------------------------------------------- tiny two-pass asm
_CC = {"jz": b"\x0F\x84", "jnz": b"\x0F\x85", "jl": b"\x0F\x8C", "jle": b"\x0F\x8E",
       "jge": b"\x0F\x8D", "jae": b"\x0F\x83", "jmp": b"\xE9"}


def assemble(items, base_va):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
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


def build_cave(va):
    """TItemHS.MapFieldMsgProc replacement.  IN: EAX = TItemHS*, EDX = msg (int*)."""
    return assemble([
        ("i", "push ebx"), ("i", "push esi"), ("i", "push edi"), ("i", "push ebp"),
        ("i", "mov esi, eax"),                          # ESI = self
        ("i", "mov edi, edx"),                          # EDI = msg
        # 1. chain to the inherited THexagonSprite handler first (as TArmyHS does)
        ("i", "mov eax, esi"), ("i", "mov edx, edi"),
        ("c", INHERITED),
        # 2. guards
        ("i", "cmp dword ptr [edi + 0x18], 0"),         # msg[6] sub-hex index
        ("j", "jnz", "done"),
        ("i", "cmp dword ptr [edi], %d" % MSG_ID),      # msg[0] == 0x1200 ?
        ("j", "jnz", "done"),
        ("i", "mov eax, dword ptr [edi + 8]"),          # msg[2] = query ctx
        ("i", "test eax, eax"), ("j", "jz", "done"),
        ("i", "cmp byte ptr [eax + 2], 0"),             # mode 0 = normal target search
        ("j", "jnz", "done"),
        ("i", "mov ebx, dword ptr [edi + 0x0c]"),       # msg[3] = result record
        ("i", "test ebx, ebx"), ("j", "jz", "done"),
        ("i", "mov ebp, dword ptr [esi + 0x0c]"),       # TItemHS+0xc = TItemList*
        ("i", "test ebp, ebp"), ("j", "jz", "done"),
        # 3. best = max GetObtainValue over the items on this hex
        ("i", "xor edi, edi"),                          # EDI = index
        ("i", "xor esi, esi"),                          # ESI = best
        ("L", "item"),
        ("i", "mov edx, edi"), ("i", "mov eax, ebp"),
        ("c", GETITEM),                                 # bounds-checked -> 0 past the end
        ("i", "test eax, eax"), ("j", "jz", "have"),
        ("c", GETOBTAIN),                               # EAX = item -> EAX = value
        ("i", "cmp eax, esi"), ("j", "jle", "next"),
        ("i", "mov esi, eax"),
        ("L", "next"),
        ("i", "inc edi"), ("j", "jmp", "item"),
        # 4. p = 10 + min(best/10, 20)   -> 10..30
        ("L", "have"),
        ("i", "test esi, esi"), ("j", "jz", "done"),    # no items on this hex
        ("i", "mov eax, esi"),
        ("i", "cdq"),
        ("i", "mov ecx, 10"),
        ("i", "idiv ecx"),
        ("i", "cmp eax, 20"), ("j", "jle", "clamped"),
        ("i", "mov eax, 20"),
        ("L", "clamped"),
        ("i", "add eax, 10"),
        # 5. max-combine into record[0] (never lower another hot-spot's priority)
        ("i", "cmp dword ptr [ebx], eax"), ("j", "jge", "done"),
        ("i", "mov dword ptr [ebx], eax"),
        ("L", "done"),
        ("i", "pop ebp"), ("i", "pop edi"), ("i", "pop esi"), ("i", "pop ebx"), ("i", "ret"),
    ], va)


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
    # --revert restores TItemHS VMT+0xCC to the inherited handler and zeroes the cave, putting the
    # class back to stock. Added 2026-07-22 to A/B this feature against a freeze that appears when an
    # AI-initiated automatic battle is accepted: the fast combat never starts and both stacks vanish.
    # This is the newest layer on the DLL and went in ~9 minutes before the first freeze, and the
    # cave's item loop terminates ONLY on GetItem returning 0 (an unbounded loop if TItemHS+0x0c is
    # not the TItemList this assumes, or if the list is stale -- cf. the recorded ground-list
    # use-after-free). Reverting is a clean two-write operation; no backup layer is disturbed.
    revert_mode = "--revert" in sys.argv

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s\n(set AOW_GAME_DIR to the game directory)" % DLL)

    data = bytearray(open(DLL, "rb").read())
    cave = build_cave(CAVE)
    if len(cave) > CAVE_BUDGET:
        sys.exit("ABORT: cave is %d bytes, budget %d." % (len(cave), CAVE_BUDGET))

    slot_off = va_to_off(data, VMT_SLOT_VA)
    cave_off = va_to_off(data, CAVE)
    cur_slot = bytes(data[slot_off:slot_off + 4])
    cur_cave = bytes(data[cave_off:cave_off + CAVE_BUDGET])
    want_slot = struct.pack("<I", CAVE)

    if cur_slot == SLOT_ORIG:
        state = "clean"
    elif cur_slot == want_slot:
        state = "applied"
    else:
        sys.exit("ABORT: TItemHS VMT+0xCC @ %#x holds %s\n"
                 "  expected original %s or our cave VA %s.\n"
                 "  Another patch may own this slot — investigate before proceeding."
                 % (VMT_SLOT_VA, cur_slot.hex(), SLOT_ORIG.hex(), want_slot.hex()))

    want_cave = bytearray(b"\x00" * CAVE_BUDGET)
    want_cave[:len(cave)] = cave
    if cur_cave != bytes(want_cave) and any(cur_cave):
        sys.exit("ABORT: cave zone %#x..%#x is neither zero-fill nor our cave.\n"
                 "  Someone else's cave may live here — pick a different CAVE address."
                 % (CAVE, CAVE + CAVE_BUDGET))

    print("AI ground-item targeting  (TItemHS answers AI-target broadcast 0x1200)\n")
    print("cave @ %#010x  %d bytes   TItemHS.MapFieldMsgProc replacement" % (CAVE, len(cave)))
    print(disasm(cave, CAVE))
    print("\nVMT slot TItemHS+0xCC @ %#010x  [%s]" % (VMT_SLOT_VA, state))
    print("      %s -> %s   (%#010x -> %#010x)"
          % (SLOT_ORIG.hex(), want_slot.hex(), INHERITED, CAVE))
    print("      priority = 10 + min(maxObtainValue/10, 20)  =>  10..30, max-combined")
    print()

    if revert_mode:
        want_slot = SLOT_ORIG
        want_cave = bytearray(b"\x00" * CAVE_BUDGET)
        print("*** --revert: restoring TItemHS VMT+0xCC to the inherited handler + zeroing the cave")

    plan = []
    if cur_cave != bytes(want_cave):
        plan.append(("cave", cave_off, cur_cave, bytes(want_cave)))
    if cur_slot != want_slot:
        plan.append(("vmt slot", slot_off, cur_slot, want_slot))

    if not plan:
        print("Already in the requested state — nothing to do.")
        return

    if not apply_mode:
        print("DRY RUN — %d write(s) planned. Re-run with --apply to write." % len(plan))
        for label, off, old, new in plan:
            print("  %-9s file %#08x  %d bytes" % (label, off, len(new)))
        return

    if not os.path.exists(BACKUP):
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
    assert check[slot_off:slot_off + 4] == want_slot, "readback mismatch: vmt slot"
    assert check[cave_off:cave_off + CAVE_BUDGET] == bytes(want_cave), "readback mismatch: cave"

    print("\nAPPLIED and verified.")
    print("TEST: drop an item on the ground within travel range of an AI hero (your own hero can")
    print("drop one, or let an AI hero die).  The AI should now send a hero to that hex and equip")
    print("the item via build_ai_itempickup.  Items score 10-30, below every army (50+) and city")
    print("(100+), so the AI only detours when nothing more important is in reach.")
    print("If NOTHING changes, the first thing to check is whether msg 0x1200 reaches a TSingleHS")
    print("hot-spot at all (the one ~90% assumption) — see KNOWN RISKS in this script's header.")


if __name__ == "__main__":
    main()
