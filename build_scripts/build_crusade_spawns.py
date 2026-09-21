#!/usr/bin/env python3
r"""
AoW1 mod -- "crusade_spawns": replace the Crusade spell's hardcoded spawn lists with a
table-driven roster (3 weighted outcomes x 3 army stacks x mixed tier composition).

FULL ANALYSIS: Modding Resources/Investigation_Crusade_Spell.md

================================================================================
VANILLA
================================================================================
GlobalSpells.TCrusade.ExecuteTE @0x557ED340 rolls Random(100):
  20%  -> 1 army of 1 unit, type = TABLE_A[Random(1)]   <- Random(1) is a DEAD ROLL, always Astra
  80%  -> 2 armies of Random(3)+4 units, each unit TABLE_B[Random(2)]  (only 2 types!)
          + 1 army of 2-3 units, all TABLE_C[Random(3)] (rolled ONCE -> homogeneous)
Tables are 6 dwords at 0x558E8E98. Net: at most 3 distinct unit types per cast, and the bulk
of every cast is the same two units. Crusade's RNG is otherwise CORRECT (it goes through
TAoWHSMap.Random) -- the repetitiveness is table size, not a seeding bug.

================================================================================
THIS PATCH
================================================================================
Replaces the entire spawn section with one cave driven by the SPEC table below. The cave
reproduces vanilla's per-unit sequence exactly (create -> set resource -> grant Crusader 0x65 ->
add to army -> post-init) and reuses vanilla's own PlaceParty for placement, so behaviour is
unchanged apart from *which* units appear.

Every roll still goes through AoWE.TAoWHSMap.Random @0x5577827C, so the map RNG state is
advanced correctly and MP peers stay in lockstep.

Hook: 0x557ED3CC (`mov edx,0x64`, the Random(100) that starts the spawn section), 5 bytes ->
      exact 5-byte jmp, no padding.
Resume: 0x557ED611 (the tail: CastingDone + SFX). The 581 bytes of vanilla spawn code between
      those points become unreachable and are left in place untouched.

Registers: EBX/ESI/EDI are pushed by the function prologue and are not read by the tail, so the
cave owns them. Cave locals live in its own 0x18-byte stack frame (balanced before the resume
jmp). EBP frame is untouched -- [ebp-4] = Self (spell), [ebp-8] = caster, both needed by
PlaceParty.

PIC: every global is reached through the standard `call $+5; pop; sub` load delta, kept in the
cave's stack frame because Random() clobbers EAX/EDX/ECX. All calls/jmps are rel32. No absolute
data reference is emitted, so this is rebase-safe.

================================================================================
TUNING -- edit SPEC / LISTS below and re-run
================================================================================
a = tier1, b = tier2, c = tier3, d = catapult; ";" separates army stacks.

Backup: backups\AoWEPACK.dpl.pre-crusadespawns -- minted by --apply as a diagnostic
artefact. ⚠ NOT a revert path: restoring it puts back the WHOLE file and silently wipes
every feature applied after it was taken. Revert with --undo.
Dry-run by default; --apply to commit; --undo to remove surgically (no backup touched).
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
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-crusadespawns")

VA_BASE = 0x55700C00
CAVE_VA = 0x55812500          # free CODE (verified run 0x55812219..0x558E7918);
                              # 0x55812400..0x5581247F is owned by sitedefender_vary
CAVE_LIMIT = 0x300            # bytes reserved for this feature
CODE_ZERO_END = 0x558E7918

HOOK_VA = 0x557ED3CC
HOOK_ORIG = bytes.fromhex("ba64000000")        # mov edx,0x64
RESUME_VA = 0x557ED611                         # the CastingDone tail

# ---- engine entry points (all verified in the vanilla spawn code) -------------
FN_RANDOM        = 0x5577827C   # TAoWHSMap.Random(EAX=map, EDX=range) -> EAX
FN_ARMYHS_CREATE = 0x557908BC   # TArmyHS.Create(EAX=classref, DL=1, ECX=0) -> EAX
FN_SETPLAYER     = 0x5578D690   # TArmy.SetPlayer(EAX=army, EDX=idx)
FN_UNIT_CREATE   = 0x5577EB28   # TAbstractUnit.Create(EAX=classref, DL=1, ECX=0) -> EAX
FN_GETUNITRES    = 0x55785050   # TUnitResourceList.GetUnitResource(EAX=list, EDX=id) -> EAX
FN_SETUNITRES    = 0x55782BE4   # TUnit.SetUnitResource(EAX=unit, EDX=res)
FN_PLACEPARTY    = 0x557ED1EC   # TCrusade.PlaceParty(EAX=Self, EDX=caster, ECX=armyHS) -> AL
FN_FREE          = 0x557010B8   # TObject.Free(EAX=obj)

PTR_MAP    = 0x558E9494         # -> ptr -> map object
PTR_HSSET  = 0x558E92E8         # -> ptr -> HSSet ; unit resource list at [[HSSET]+0x5C]
CLS_ARMYHS = 0x55713360
CLS_UNIT   = 0x55710C6C

ABIL_CRUSADER = 0x65            # PassiveAb.TCrusaderAbility (TDurationAbility -> temporary)
ARMY_CAP = 8                    # AoW1 stack limit -- validated, warned about, not enforced

# =============================================================================
# SPEC -- what Crusade summons.  EDIT HERE.
# =============================================================================
# Named unit pools. A pool of one element is just "always this unit".
LISTS = [
    ("a  tier1", [126, 127, 129, 135]),   # Highman Archer, Chanter, Legionary, Legionary
    ("b  tier2", [128, 130, 136]),        # Highman Paladin, Spirit Puppet, Highman Chariot
    ("c  tier3", [131, 132, 134]),        # Titan, Valkyrie, Highman Avenger
    ("astra",    [133]),                  # Astra
    ("d  catapult", [251]),               # Catapult
    ("valkyrie", [132]),                  # Valkyrie
]
L_A, L_B, L_C, L_ASTRA, L_D, L_VALK = range(6)

# (chance%, [stack, stack, stack]) -- each stack is a list of (pool, count).
# Chances must sum to 100. Exactly 3 stacks per outcome, max 3 entries per stack.
SPEC = [
    (20, "Astra; 8a; 8a", [
        [(L_ASTRA, 1)],
        [(L_A, 8)],
        [(L_A, 8)],
    ]),
    (20, "3 Valkyries; 4b4a; 4b4a", [
        [(L_VALK, 3)],
        [(L_B, 4), (L_A, 4)],
        [(L_B, 4), (L_A, 4)],
    ]),
    (60, "3b4a1d; 2c5b1d; 1c3b4a", [
        [(L_B, 3), (L_A, 4), (L_D, 1)],
        [(L_C, 2), (L_B, 5), (L_D, 1)],
        [(L_C, 1), (L_B, 3), (L_A, 4)],     # was 5a = 9 units; trimmed to the 8-unit army cap
    ]),
]

MAX_STACKS = 3
MAX_ENTRIES = 3


# ---------------------------------------------------------------- data layout
def build_data():
    """THRESH[3] | LISTOFS[6] | LISTLEN[6] | LISTS blob | OUTCOMES[3*18]"""
    if len(SPEC) != 3:
        sys.exit("ERROR: SPEC must have exactly 3 outcomes (the cave's selector is fixed at 3)")
    if sum(c for c, _, _ in SPEC) != 100:
        sys.exit("ERROR: SPEC chances must sum to 100")

    thresh, acc = [], 0
    for chance, _, _ in SPEC:
        acc += chance
        thresh.append(acc)
    thresh[-1] = 100

    blob, offs, lens = bytearray(), [], []
    for name, ids in LISTS:
        if not ids:
            sys.exit("ERROR: pool %r is empty (Random(0) is undefined)" % name)
        for u in ids:
            if not 0 <= u <= 255:
                sys.exit("ERROR: unit id %d in pool %r does not fit in a byte" % (u, name))
        offs.append(len(blob))
        lens.append(len(ids))
        blob += bytes(ids)

    outcomes = bytearray()
    for chance, label, stacks in SPEC:
        if len(stacks) != MAX_STACKS:
            sys.exit("ERROR: outcome %r must have exactly %d stacks" % (label, MAX_STACKS))
        for st in stacks:
            if len(st) > MAX_ENTRIES:
                sys.exit("ERROR: stack in %r has %d entries, max %d" % (label, len(st), MAX_ENTRIES))
            for pool, n in st:
                outcomes += bytes([pool, n])
            outcomes += bytes([0, 0]) * (MAX_ENTRIES - len(st))

    data = bytes(thresh) + bytes(offs) + bytes(lens) + bytes(blob) + bytes(outcomes)
    layout = dict(
        THRESH=0,
        LISTOFS=3,
        LISTLEN=3 + len(LISTS),
        LISTS=3 + 2 * len(LISTS),
        OUTCOMES=3 + 2 * len(LISTS) + len(blob),
    )
    return data, layout


def build_code(code_va, d):
    """Assemble the cave body. `d` maps symbol -> absolute VA."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    delta_lbl = code_va + 3 + 5          # VA of the `pop eax` after `sub esp,0x18` + `call`

    asm = f"""
        sub  esp, 0x18
        call 0x{delta_lbl:X}
        pop  eax
        sub  eax, 0x{delta_lbl:X}
        mov  [esp], eax

        mov  eax, [esp]
        mov  eax, [eax + 0x{PTR_MAP:X}]
        mov  eax, [eax]
        mov  edx, 100
        call 0x{FN_RANDOM:X}

        mov  ecx, [esp]
        xor  edx, edx
    sel_loop:
        movzx ebx, byte ptr [ecx + edx + 0x{d['THRESH']:X}]
        cmp  eax, ebx
        jb   sel_done
        inc  edx
        cmp  edx, 2
        jb   sel_loop
    sel_done:
        imul edx, edx, {MAX_STACKS * MAX_ENTRIES * 2}
        mov  ecx, [esp]
        lea  esi, [ecx + 0x{d['OUTCOMES']:X}]
        add  esi, edx
        mov  dword ptr [esp + 8], {MAX_STACKS}

    stack_loop:
        mov  eax, [esp]
        mov  eax, [eax + 0x{CLS_ARMYHS:X}]
        xor  ecx, ecx
        mov  dl, 1
        call 0x{FN_ARMYHS_CREATE:X}
        mov  edi, eax
        mov  eax, [edi + 0x1C]
        xor  edx, edx
        call 0x{FN_SETPLAYER:X}
        mov  dword ptr [esp + 0xC], {MAX_ENTRIES}

    entry_loop:
        movzx eax, byte ptr [esi]
        mov  [esp + 0x10], eax
        movzx eax, byte ptr [esi + 1]
        test eax, eax
        jz   entry_next
        mov  [esp + 4], eax

    unit_loop:
        mov  ecx, [esp]
        mov  eax, [esp + 0x10]
        movzx edx, byte ptr [ecx + eax + 0x{d['LISTLEN']:X}]
        mov  eax, [ecx + 0x{PTR_MAP:X}]
        mov  eax, [eax]
        call 0x{FN_RANDOM:X}

        mov  ecx, [esp]
        mov  edx, [esp + 0x10]
        movzx edx, byte ptr [ecx + edx + 0x{d['LISTOFS']:X}]
        add  edx, eax
        movzx eax, byte ptr [ecx + edx + 0x{d['LISTS']:X}]
        mov  [esp + 0x14], eax

        mov  eax, [esp]
        mov  eax, [eax + 0x{CLS_UNIT:X}]
        xor  ecx, ecx
        mov  dl, 1
        call 0x{FN_UNIT_CREATE:X}
        mov  ebx, eax

        mov  edx, [esp + 0x14]
        mov  ecx, [esp]
        mov  eax, [ecx + 0x{PTR_HSSET:X}]
        mov  eax, [eax]
        mov  eax, [eax + 0x5C]
        call 0x{FN_GETUNITRES:X}
        mov  edx, eax
        mov  eax, ebx
        call 0x{FN_SETUNITRES:X}

        mov  edx, 0x{ABIL_CRUSADER:X}
        mov  eax, ebx
        mov  ecx, [eax]
        call dword ptr [ecx + 0x94]

        mov  eax, [edi + 0x1C]
        mov  edx, ebx
        mov  ecx, [eax]
        call dword ptr [ecx + 0xAC]

        mov  eax, ebx
        mov  edx, [eax]
        call dword ptr [edx + 0x2C]

        dec  dword ptr [esp + 4]
        jnz  unit_loop

    entry_next:
        add  esi, 2
        dec  dword ptr [esp + 0xC]
        jnz  entry_loop

        mov  ecx, edi
        mov  edx, [ebp - 8]
        mov  eax, [ebp - 4]
        call 0x{FN_PLACEPARTY:X}
        test al, al
        jne  placed
        mov  eax, edi
        call 0x{FN_FREE:X}
    placed:
        dec  dword ptr [esp + 8]
        jnz  stack_loop

        add  esp, 0x18
        jmp  0x{RESUME_VA:X}
    """
    enc, _ = ks.asm(asm, code_va)
    return bytes(enc)


def off(va):
    return va - VA_BASE


def make_hook(cave_va):
    return b"\xE9" + struct.pack("<i", cave_va - (HOOK_VA + 5))


def validate():
    print("Crusade spawn spec:")
    warn = False
    for chance, label, stacks in SPEC:
        sizes = [sum(n for _, n in st) for st in stacks]
        print("  %3d%%  %-28s stacks: %s" % (chance, label, sizes))
        for st, sz in zip(stacks, sizes):
            if sz > ARMY_CAP:
                comp = " + ".join("%dx %s" % (n, LISTS[p][0]) for p, n in st)
                print("        !! WARNING: %d units exceeds the %d-unit army cap  (%s)"
                      % (sz, ARMY_CAP, comp))
                warn = True
    if warn:
        print("        The engine's AddUnit has no explicit cap; the surplus unit will most")
        print("        likely be silently rejected. Adjust SPEC if you want a guaranteed count.")
    print()
    for i, (name, ids) in enumerate(LISTS):
        print("  pool %d %-12s %s" % (i, name, ids))
    print()


def main():
    ap = argparse.ArgumentParser(description="Crusade spawn-list rework")
    ap.add_argument("--apply", action="store_true", help="write the patch (default: dry run)")
    ap.add_argument("--undo", action="store_true",
                    help="surgically remove: restore vanilla bytes + zero the cave. "
                         "No .pre-* backup is touched.")
    args = ap.parse_args()

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s\n(set AOW_GAME_DIR)" % DLL)
    data = bytearray(open(DLL, "rb").read())

    cur_hook = bytes(data[off(HOOK_VA):off(HOOK_VA) + len(HOOK_ORIG)])
    ours = cur_hook == make_hook(CAVE_VA)

    if args.undo:
        if not ours:
            print("Nothing to undo: 0x%08X does not carry this feature." % HOOK_VA)
            return
        data[off(HOOK_VA):off(HOOK_VA) + len(HOOK_ORIG)] = HOOK_ORIG
        data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = b"\x00" * CAVE_LIMIT
        open(DLL, "wb").write(data)
        print("UNDO: restored 0x%08X, zeroed cave 0x%08X..0x%08X. No backup touched."
              % (HOOK_VA, CAVE_VA, CAVE_VA + CAVE_LIMIT - 1))
        return

    blob, layout = build_data()
    dsyms = {k: CAVE_VA + v for k, v in layout.items()}
    code_va = (CAVE_VA + len(blob) + 0xF) & ~0xF          # 16-byte align the code
    code = build_code(code_va, dsyms)
    total = (code_va - CAVE_VA) + len(code)

    validate()
    print("cave 0x%08X: data %d B, code %d B @0x%08X, total %d B (limit %d)"
          % (CAVE_VA, len(blob), len(code), code_va, total, CAVE_LIMIT))
    print("hook 0x%08X: %s -> %s   resume 0x%08X"
          % (HOOK_VA, HOOK_ORIG.hex(), make_hook(code_va).hex(), RESUME_VA))
    print()

    if total > CAVE_LIMIT:
        sys.exit("ERROR: cave needs %d bytes, limit is %d" % (total, CAVE_LIMIT))
    if CAVE_VA + CAVE_LIMIT > CODE_ZERO_END:
        sys.exit("ERROR: cave runs past the end of CODE")

    hook = make_hook(code_va)
    ours = cur_hook == hook

    if not ours and cur_hook != HOOK_ORIG:
        sys.exit("ABORT: unexpected bytes at 0x%08X: %s (want %s or our jmp)"
                 % (HOOK_VA, cur_hook.hex(), HOOK_ORIG.hex()))
    if not ours:
        zone = bytes(data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT])
        if zone != b"\x00" * CAVE_LIMIT:
            sys.exit("ABORT: cave zone 0x%08X..0x%08X is not zero -- someone else owns it"
                     % (CAVE_VA, CAVE_VA + CAVE_LIMIT - 1))

    payload = bytearray(CAVE_LIMIT)
    payload[0:len(blob)] = blob
    payload[code_va - CAVE_VA:code_va - CAVE_VA + len(code)] = code

    if bytes(data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT]) == bytes(payload) and ours:
        print("Already applied and up to date -- nothing to do.")
        return

    if not args.apply:
        print("DRY RUN -- would write hook (%d B) + cave (%d B). Re-run with --apply."
              % (len(hook), CAVE_LIMIT))
        print("(Close AoW.exe / AoWCompat.exe / AoWDevEd.exe first -- they lock the DLL.)")
        return

    if not os.path.exists(BAK):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BAK)
        print("backup -> %s" % os.path.basename(BAK))

    data[off(HOOK_VA):off(HOOK_VA) + len(hook)] = hook
    data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = payload
    try:
        open(DLL, "wb").write(data)
    except PermissionError:
        sys.exit("ERROR: %s is locked. Close the AoW binaries and retry." % os.path.basename(DLL))

    print("APPLIED. Revert with --undo -- surgical. (A .pre-* snapshot is NOT a revert path:")
    print("  it restores the whole file and wipes every feature applied after it.)")
    print("TEST: cast Crusade several times; the 60%% outcome should be the common one.")


if __name__ == "__main__":
    main()
