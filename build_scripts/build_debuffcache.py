#!/usr/bin/env python
"""
build_debuffcache.py — fix Webbed / Entangled stat modifiers not applying to units.

PROBLEM
-------
`TUnit` serves ATK/DEF/RES/DAM from a cached byte block at unit+0x44..0x47, rebuilt only by
`TUnit.Changed` (owner VMT +0x90).  The only thing that calls `Changed` on an ability apply is the
wrapper `TAbilityOwner.ExpandAbility` @0x5574f5b4 (owner VMT +0x94).

Three combat-action sites apply their status by calling the ability's `Expand` (ability VMT +0xd0)
*directly*, bypassing that wrapper.  The bit and the duration record are created (icon shows, timer
ticks) but the cache is never recomputed, so the -2 DEF has zero effect on a regular unit until some
unrelated event happens to call `Changed`.  `THero` has no cache and recomputes live, so heroes are
unaffected — which is why the bug looks intermittent and unit-only.

  TWebCA.Execute          @0x5576a06c   applies Webbed    0x61
  TEntangleCA.Execute     @0x5576a648   applies Entangled 0x5e
  TEntangleSpellCA.Execute@0x557f89f4   applies Entangled 0x5e  (spell version)

Every other status is applied via `ExpandAbility` from `TAbstractUnit.ExecuteCombatDamageEffects`
@0x55781ed8 and is therefore already correct.

FIX
---
Redirect each site's 6-byte `CALL dword ptr [ECX+0xd0]` to a small cave that performs the original
Expand and then calls `Changed` on the target unit.

All three sites share an identical register contract at the call:
    EAX = ability, EDX = target unit, ECX = ability VMT, EBX = target *combat* unit
and `[EBX+0x4c]` is the underlying unit.  EBX is callee-saved and demonstrably survives the call —
vanilla itself reloads `MOV EAX,[EBX+0x4c]` immediately after it at both Entangle sites.  None of the
three sites consumes the Expand return value in EAX (Web pops and returns; both Entangle sites
overwrite EAX at once), so the cave is free to clobber it.

`Changed` is called unconditionally rather than gated on Expand's result (which is how
`ExpandAbility` does it).  Deliberate: it is idempotent — it just recompacts the four bytes from the
current ability set — and being unconditional also heals a cache left stale by a pre-patch save when
the debuff is re-applied.

Cave is position-independent (register-indirect calls + one rel32 jmp, no absolute memory refs), as
required for the rebasing .dpl.

Does NOT touch `TUnit.GetDefense` @0x55782a40 (which carries a separate, undocumented 2-byte no-op
disabling unit morale->defense) and does NOT touch `TFrozenAbility.GetDefense` @0x557ba0b4 (+2 DEF is
an intentional mod change — Frozen depicts the unit encased in ice).

USAGE
-----
    python build_scripts/build_debuffcache.py            # dry run / verify current state
    python build_scripts/build_debuffcache.py --apply    # write (auto-backup .pre-debuffcache)

Close AoW.exe / AoWCompat.exe / AoWDevEd.exe first — they lock the DLL.
Revert = --revert (SURGICAL: restores the three call sites and zeroes the caves, no backup touched).
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
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-debuffcache")
BASE = 0x55700000

CAVE = 0x5580F900          # start of the big zero run at 0x5580f8c0; caves grow upward from 0x5580C000
CAVE_STRIDE = 0x20         # one 32-byte slot per site
CAVE_LEN = 26              # bytes actually emitted per site

ORIG_CALL = bytes([0xFF, 0x91, 0xD0, 0x00, 0x00, 0x00])   # call dword ptr [ecx+0xd0]

# (label, VA of the CALL, ability id applied)  — return VA is always call_va + 6
SITES = [
    ("TWebCA.Execute",           0x5576A0A1, 0x61),
    ("TEntangleCA.Execute",      0x5576A68D, 0x5E),
    ("TEntangleSpellCA.Execute", 0x557F8A44, 0x5E),
]


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


# ---------------------------------------------------------------- cave build

def build_cave(cave_va, ret_va):
    """Assemble one cave. Returns bytes (length CAVE_LEN)."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    body = bytes(ks.asm(
        "call dword ptr [ecx + 0xd0];"      # original Expand(ability, unit)
        "mov eax, dword ptr [ebx + 0x4c];"  # eax = target unit (EBX survived the call)
        "test eax, eax",
        cave_va)[0])
    body += b"\x74\x08"                      # jz +8  -> skip to the jmp if unit is nil
    body += bytes(ks.asm(
        "mov edx, dword ptr [eax];"         # edx = unit VMT
        "call dword ptr [edx + 0x90]",      # Changed() -> rebuild unit+0x44..0x47
        cave_va + len(body))[0])
    jmp_at = cave_va + len(body)
    body += b"\xE9" + struct.pack("<i", ret_va - (jmp_at + 5))

    assert len(body) == CAVE_LEN, "cave is %d bytes, expected %d" % (len(body), CAVE_LEN)
    return body


def build_hook(call_va, cave_va):
    """5-byte jmp to the cave + 1 nop, replacing the 6-byte call."""
    return b"\xE9" + struct.pack("<i", cave_va - (call_va + 5)) + b"\x90"


def disasm(code, va, indent="      "):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return indent + code.hex()
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    return "\n".join("%s%08x  %-22s %s %s" % (indent, i.address, i.bytes.hex(), i.mnemonic, i.op_str)
                     for i in md.disasm(code, va))


# ---------------------------------------------------------------- main

def main():
    apply_mode = "--apply" in sys.argv
    revert_mode = "--revert" in sys.argv

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s\n(set AOW_GAME_DIR to the game directory)" % DLL)

    data = bytearray(open(DLL, "rb").read())

    plan = []          # (label, off, old, new, kind)
    state = []         # per-site: "clean" | "applied"

    for idx, (label, call_va, ab_id) in enumerate(SITES):
        cave_va = CAVE + idx * CAVE_STRIDE
        ret_va = call_va + 6
        cave = build_cave(cave_va, ret_va)
        hook = build_hook(call_va, cave_va)

        c_off = va_to_off(data, call_va)
        v_off = va_to_off(data, cave_va)
        cur_call = bytes(data[c_off:c_off + 6])
        cur_cave = bytes(data[v_off:v_off + CAVE_LEN])

        if cur_call == ORIG_CALL:
            site_state = "clean"
        elif cur_call == hook:
            site_state = "applied"
        else:
            sys.exit("ABORT: %s @ %#x has unexpected bytes %s\n"
                     "  expected original %s or our hook %s.\n"
                     "  Another patch may own this site — investigate before proceeding."
                     % (label, call_va, cur_call.hex(), ORIG_CALL.hex(), hook.hex()))

        # cave zone must be untouched zero-fill, or already hold exactly our cave
        if cur_cave != cave and any(cur_cave):
            sys.exit("ABORT: cave zone %#x is neither zero-fill nor our cave:\n  %s\n"
                     "  Someone else's cave may live here — pick a different CAVE address."
                     % (cave_va, cur_cave.hex()))

        state.append(site_state)
        print("%-26s call @ %#010x  cave @ %#010x   [%s]" % (label, call_va, cave_va, site_state))
        print("    ability id applied: %#04x   returns to %#010x" % (ab_id, ret_va))
        print("    cave:")
        print(disasm(cave, cave_va))
        print("    hook (replaces the 6-byte call):")
        print(disasm(hook, call_va))
        print()

        if revert_mode:
            # --revert (added 2026-07-22): put the three call sites back to the stock virtual call
            # and zero the caves. Used to A/B this feature against a freeze localised by
            # build_combatdiag.py to INSIDE a single TFastCombatUnit.fcExecute call in round 2 of an
            # auto-resolved battle. Webbed/Entangled are movement debuffs and this patch changes how
            # units cache ability stat modifiers, so it is a live candidate for a unit that can no
            # longer act. Re-apply by running this script again with --apply.
            if site_state == "applied":
                plan.append((label, c_off, cur_call, ORIG_CALL, "hook"))
            if any(cur_cave):
                plan.append((label, v_off, cur_cave, bytes(CAVE_LEN), "cave"))
        elif site_state == "clean" or cur_cave != cave:
            plan.append((label, v_off, cur_cave, cave, "cave"))
            plan.append((label, c_off, cur_call, hook, "hook"))

    if all(s == "applied" for s in state) and not plan:
        print("All three sites already patched and caves match — nothing to do.")
        return

    if not apply_mode:
        print("DRY RUN — %d write(s) planned. Re-run with --apply to write." % len(plan))
        for label, off, old, new, kind in plan:
            print("  %-26s %-4s file %#08x  %d bytes" % (label, kind, off, len(new)))
        return

    # ---- apply
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("backup -> %s" % os.path.basename(BACKUP))
    else:
        print("backup already exists: %s (left as-is)" % os.path.basename(BACKUP))

    for label, off, old, new, kind in plan:
        assert bytes(data[off:off + len(old)]) == old, "verify-before-write failed at %#x" % off
        data[off:off + len(new)] = new

    try:
        with open(DLL, "wb") as fh:
            fh.write(data)
    except PermissionError:
        sys.exit("ERROR: %s is locked. Close AoW.exe / AoWCompat.exe / AoWDevEd.exe and retry."
                 % os.path.basename(DLL))

    # ---- read back and verify
    check = open(DLL, "rb").read()
    for idx, (label, call_va, _) in enumerate(SITES):
        cave_va = CAVE + idx * CAVE_STRIDE
        # NB: the expectation depends on the MODE. This assert previously hard-coded the apply-mode
        # bytes and therefore threw on every --revert -- AFTER the file had already been written,
        # which is the same shape as the bug that once left AoWCompat.exe silently unpatched. A
        # post-write check must verify what THIS run intended, or it is worse than no check at all.
        want_hook = ORIG_CALL if revert_mode else build_hook(call_va, cave_va)
        want_cave = bytes(CAVE_LEN) if revert_mode else build_cave(cave_va, call_va + 6)
        c_off = va_to_off(data, call_va)
        v_off = va_to_off(data, cave_va)
        assert check[c_off:c_off + 6] == want_hook, "readback mismatch: hook %s" % label
        assert check[v_off:v_off + CAVE_LEN] == want_cave, "readback mismatch: cave %s" % label

    print("\n%s and verified: %d sites." % ("REVERTED" if revert_mode else "APPLIED", len(SITES)))
    print("Test in-game on a NON-HERO unit — heroes recompute live and mask this bug entirely.")
    print("Expect: web/entangle a unit -> its Defense drops by 2 immediately on the unit card.")


if __name__ == "__main__":
    main()
