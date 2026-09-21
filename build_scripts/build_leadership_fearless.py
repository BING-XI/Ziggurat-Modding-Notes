#!/usr/bin/env python3
r"""
AoW1 mod -- "leadfearless": Leadership IV makes the whole stack count as Fearless.

FULL ANALYSIS: Modding Resources/Zig notes/Leadership4_Grants_Fearless.md
Related:       Zig notes/Leadership_FourLevels_And_Fix.md  (the 4-level ability)
               Zig notes/Leadership_Disable_Bug_RootCause.md  (the aura machinery)
               Zig notes/Terror_OncePerCombat.md  (shares two of these functions)

================================================================================
WHAT FEARLESS ACTUALLY IS
================================================================================
Fearless (id 0x43) is a PLAIN BIT-ONLY passive -- registered by PassiveAb, no
ability class, no per-owner data record. It means exactly one thing: "cannot be
given the Panicked status (0x6C)". The only producers of Panicked in the whole
module are the melee Cause Fear strike and the two Terror CAs; there is no
morale-driven panic to be immune to (GetUnitMoraleValue only READS Panicked).

================================================================================
THE PROPAGATION IS FREE -- NO AURA IS BUILT HERE
================================================================================
AoWE.TArmy.UpdateFormation @0x5578D034 pass 2 already runs over EVERY unit in the
army with no gate:  if GetAbilityLevel(u,0x2E) < armyMax: SetExternalSource(u,...)
So every member of a Leadership-IV stack -- the leader included -- already reads
GetAbilityLevel(unit, 0x2E) == 4.

*** UPDATED 2026-09-16: pass 2 is now build_leadership_others.py's cave_pass2 ***
    That feature makes the aura skip its own holder, so a stack's SOLE Leadership-IV
    leader no longer receives 4 -- it receives max2, the next-best own level. This
    feature is unaffected because GetAbilityLevel (VMT+0x144 -> TLeadershipAbility.
    GetLevel @0x557661C4) still returns max(OWN, borrowed): the leader reads 4 from
    its own record, the followers read 4 from their borrowed one.
    ⚠ FORWARD HAZARD: that is exactly why build_leadership_others.py deliberately does
    NOT port the upstream author's "GetLevel returns own only" change. Making GetLevel
    own-only would silently drop every FOLLOWER out of the Fearless stack while every
    static check here still passed.  AoWE.TCombatUnit.SetParty @0x557250D6 re-runs
UpdateFormation at combat start, so it holds in tactical AND fast/auto-resolve.

This patch therefore writes NOTHING to any unit: it derives the answer at query
time from state the engine already replicates. No new state, no save-format
interaction, no RNG, nothing to garbage-collect.

*** WHY NOT SET THE FEARLESS BIT ON STACK MEMBERS ***
    Fearless has no data record, so there is no data[+0x0c] own-level byte to tell
    "borrowed from the aura" from "inherent". That is the Leadership disable bug's
    shape (Leadership_Disable_Bug_RootCause.md) with the discriminator removed
    entirely -- un-granting would need a bespoke shadow store, and a bug in it
    PERMANENTLY STRIPS NATIVE FEARLESS from undead, elementals and everything else
    that ships with it. User ruling 2026-09-01: effect only, no unit-card entry.

*** THE STRATEGIC MAP NEEDS NO PATCH ***
    AoWE.TAbstractUnit.ExecuteLifeMasteryFearRole @0x55780B90 tests Fearless at
    +0x26 and then tests LEADERSHIP at +0x39 (mov edx,0x2E @0x55780BC9, jne out).
    Vanilla already exempts any Leadership holder from Life Mastery fear.

================================================================================
THE FIVE SITES -- one shape, one cave
================================================================================
Every consumer that matters is the SAME 15-byte run, and all five are
byte-identical to the pristine DLL (no other Ziggurat patch touches them):

    ba <id> 00 00 00   mov edx, <ability id>
    8b c6 / 8b c3      mov eax, esi / ebx        ; the combat object under test
    8b 08              mov ecx, [eax]
    ff 91 a8 00 00 00  call [ecx+0xA8]           ; TCombatUnit.GetAbilityEnabled

  1 0x557668F5  AoWE.TStrikeCA.Generate+0x41                 0x43 esi  melee Cause Fear
  2 0x557F983D  CombatSpells.TFastCombatTerrorCA.Generate    0x43 ebx  Terror, auto-resolve
  3 0x557F99C1  CombatSpells.TTacticalCombatTerrorCA.Gen.    0x43 ebx  Terror, tactical
  4 0x557F9D4E  CombatSpells.TTerror.tcGetDamageValueEx      0x6C esi  AI value, tactical
  5 0x557F9B64  CombatSpells.TTerror.fcPrefetchCombatCmds    0x6C ebx  AI value, fast

Sites 1-3 are the effect. Sites 4-5 are the AI's "is this target worth counting"
test: vanilla checks only Panicked there and NEVER Fearless, so the AI already
overvalues Terror against immune targets. Routing them through the same cave makes
the AI score a Leadership-IV stack as a non-target, and incidentally fixes that
pre-existing vanilla case for natively-Fearless units. (User ruling 2026-09-01.)

The `mov edx,<id>` stays in place, so ONE cave serves both ids:

    ba <id> 00 00 00   mov edx, <id>      ; unchanged
    8b c6 / 8b c3      mov eax, <reg>     ; unchanged
    e8 <rel32>         call C_FEAR
    90 90 90                              ; 15 bytes exactly, nothing displaced

================================================================================
*** THE TRAP: +0xB0 GetAbilityLevel CANNOT BE USED HERE ***
================================================================================
The obvious cave calls TCombatUnit.GetAbilityLevel (VMT +0xB0) directly. That
CRASHES. Ghidra_VMT_Layouts.md records the rule -- +0xB0 is not nil-guarded and may
only be called "directly behind a +0xA8 gate on the same object in the same
function". The subtlety that bites here is what "behind the gate" means:

    55725004  +0xA8 GetAbilityEnabled: mov ecx,[eax+0x4C]/test ecx,ecx/je ->0  GUARDED
    55725028  +0xB0 GetAbilityLevel:   mov eax,[eax+0x4C]/mov ecx,[eax]/call   NOT

+0xA8 returns 0 for BOTH "nil [obj+0x4C]" and "ability not enabled" -- and this
cave proceeds precisely when the first query returned FALSE. So a +0xA8 that
returned false is not proof of a non-nil owner; the gate the rule means is a +0xA8
that returned TRUE. A nil [combatobj+0x4C] is normal engine state, not corruption,
so +0xB0 here would be a real intermittent crash.

THE FIX -- +0xB8 GetAbilityOwner, which is nil-safe on both classes:

    55725000  TCombatUnit.GetAbilityOwner:    mov eax,[eax+0x4C] / ret   nil in -> nil out
    557268D0  TCombatObject.GetAbilityOwner:  xor eax,eax / ret          walls, structures

Test EAX for nil, then dispatch TAbstractUnit.GetAbilityLevel (+0x144, item-aware)
on the strategic unit -- the same function +0xB0 would have forwarded to. No
IsClass, no classref global, no absolute reference.

GENERALISABLE: a nil-guarded accessor returning FALSE does not discharge the guard
for its ungated sibling. When a cave needs the same object twice and the first
query may legitimately return false, reach for the accessor that returns the
POINTER and test it, rather than inferring safety from a boolean.

================================================================================
CAVE
================================================================================
C_FEAR = 0x5582C000 in CODE, one cave, ~60 bytes.
  entry: EAX = combat object, EDX = the original ability id (0x43 or 0x6C)
  exit:  EAX = 0/1, "treat this target as immune"

    push ebx / mov ebx,eax
    mov ecx,[eax] / call [ecx+0xA8]     ; the original query, verbatim semantics
    test al,al / jne .true
    mov eax,ebx / mov ecx,[eax] / call [ecx+0xB8]   ; GetAbilityOwner (nil-safe)
    test eax,eax / je .false
    mov edx,0x2E / mov ecx,[eax] / call [ecx+0x144] ; GetAbilityLevel(Leadership)
    cmp eax,LEAD_LEVEL / jl .false
  .true:  mov eax,1 / pop ebx / ret
  .false: xor eax,eax / pop ebx / ret

NO absolute references and NO rel32 calls at all -- every call is an indirect VMT
dispatch -- so position-independence is free: the .dpl rebases at runtime and this
cave needs no call/pop delta anchor.

Register safety: Delphi makes EAX/EDX/ECX volatile and EBX/ESI/EDI/EBP callee-saved.
All five host functions keep the object in ESI/EBX/EDI and EBP; the cave saves the
one register it uses.

*** 0x5582B000..0x5582B200 is build_item_hpmv.py -- do not encroach. ***
Nearest other claims: 0x5582A000..0x5582A200 (build_terror_oncepercombat.py) and
0x55828000..0x55828068 (build_panic_no_offensive_melee.py). 0x5582C000 is clear of
all of them and verified all-zero in the live DLL.

================================================================================
COLLISION AUDIT (2026-09-01, all clear)
================================================================================
  build_lifesteal_roundattack.py  jmp @0x557668E2, cave returns to 0x557668E7
                                  -> site 1 is 0x557668F5. Clear.
  build_terror_oncepercombat.py   entry jmp @0x557F9B20 (7 B, ends 0x557F9B27)
                                  -> site 5 is 0x557F9B64. Clear.
  build_terror_oncepercombat.py   wraps tcGetDamageValueEx at the VMT SLOT
                                  0x557F625C; the function body is untouched
                                  -> site 4 is in the body. Clear.
  build_panic_no_offensive_melee  caves 0x55828000..0x55828068. Clear.

C_WRAPTC interaction checked and benign: Terror_OncePerCombat.md summarises the
tactical wrapper as "value = max(1, value>>6)", which would have inflated an immune
target's fresh 0 back to 1. The actual cave short-circuits first
(mov eax,[ebx]; test eax,eax; je done @0x5582A151), so a zero stays zero.

RNG  -- the cave makes no draw of any kind. Re-run re_tools/rng_audit.py --owners
        after --apply anyway; that is the standing rule.
MP   -- nothing is written to any unit; all five hooks are pure derivations of
        state the engine already replicates. No save-format interaction.
BINARY -- AoWEPACK.dpl only. Fearless is not queried by AoW.exe, AoWTCPCK.dpl or
        aowInt.dpl, so there is no AoW.exe/AoWCompat lockstep half.

USAGE
    python build_scripts/build_leadership_fearless.py            # verify only
    python build_scripts/build_leadership_fearless.py --dis      # + cave disasm
    python build_scripts/build_leadership_fearless.py --apply
    python build_scripts/build_leadership_fearless.py --undo     # surgical
"""
import os
import struct
import subprocess
import sys

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-leadfearless")

# ---------------------------------------------------------------- tunables ----
LEAD_LEVEL = 4                  # Leadership level at which the stack becomes immune

# ---------------------------------------------------------------- addresses ---
AB_FEARLESS   = 0x43
AB_PANICKED   = 0x6C
AB_LEADERSHIP = 0x2E

SLOT_ENABLED = 0xA8             # TCombatUnit.GetAbilityEnabled  (nil-GUARDED)
SLOT_OWNER   = 0xB8             # TCombatUnit.GetAbilityOwner    (nil-safe both classes)
SLOT_LEVEL   = 0x144            # TAbstractUnit.GetAbilityLevel  (item-aware)

# site -> (description, ability id, register holding the combat object)
SITES = {
    0x557668F5: ("AoWE.TStrikeCA.Generate+0x41              melee Cause Fear",
                 AB_FEARLESS, "esi"),
    0x557F983D: ("CombatSpells.TFastCombatTerrorCA.Gen+0x5D Terror, auto-resolve",
                 AB_FEARLESS, "ebx"),
    0x557F99C1: ("CombatSpells.TTacticalCombatTerrorCA+0x29 Terror, tactical",
                 AB_FEARLESS, "ebx"),
    0x557F9D4E: ("CombatSpells.TTerror.tcGetDamageValueEx   AI value, tactical",
                 AB_PANICKED, "esi"),
    0x557F9B64: ("CombatSpells.TTerror.fcPrefetchCombatCmds AI value, fast",
                 AB_PANICKED, "ebx"),
}

MOV_EAX = {"esi": bytes.fromhex("8bc6"), "ebx": bytes.fromhex("8bc3")}

CAVE_BASE = 0x5582C000
C_FEAR    = 0x5582C000
CAVE_END  = 0x5582C080          # asserted zero-or-ours across this whole span

_BASE = None                    # VA = file_offset + _BASE, resolved from the PE


def orig_bytes(site):
    """The 15-byte vanilla run at a site, rebuilt from its (id, reg)."""
    _, ab, reg = SITES[site]
    return (b"\xBA" + struct.pack("<I", ab) + MOV_EAX[reg]
            + bytes.fromhex("8b08") + b"\xFF\x91" + struct.pack("<I", SLOT_ENABLED))


def patched_bytes(site):
    """Same 15 bytes, but the indirect call replaced by `call C_FEAR` + 3 nops."""
    o = orig_bytes(site)
    rel = C_FEAR - (site + 7 + 5)           # the call starts 7 bytes into the run
    p = o[:7] + b"\xE8" + struct.pack("<i", rel) + b"\x90" * 3
    assert len(p) == len(o) == 15
    return p


def off(va):
    return va - _BASE


def resolve_base(d):
    """Set the flat VA->offset delta from the CODE section, and assert every
    address this script touches really lives in CODE (a flat delta is silently
    wrong outside it)."""
    global _BASE
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    image_base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        name = d[o:o + 8].rstrip(b"\0").decode("latin1")
        vsz, va, _rsz, ro = struct.unpack_from("<IIII", d, o + 8)
        if name != "CODE":
            continue
        lo, hi = image_base + va, image_base + va + vsz
        _BASE = lo - ro
        for a in list(SITES) + [CAVE_BASE, CAVE_END - 1]:
            if not lo <= a < hi:
                sys.exit("ABORT: 0x%08X is outside CODE (0x%08X..0x%08X)" % (a, lo, hi))
        return
    sys.exit("ABORT: no CODE section in %s" % DLL)


# ------------------------------------------------------------- mini assembler --
def _ks():
    try:
        from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    except ImportError:
        sys.exit("keystone-engine not installed:  pip install keystone-engine")
    return Ks(KS_ARCH_X86, KS_MODE_32)


def asm_layout(frags, base):
    """frags: list of (label|None, text|bytes|None). Text may use {LABEL}
    placeholders. Iterates to a fixed point so forward references settle."""
    ks = _ks()
    labels = {lab: base for lab, _ in frags if lab}
    for _ in range(8):
        va, out, seen = base, b"", {}
        for lab, item in frags:
            if lab:
                seen[lab] = va
            if item is None:
                continue
            if isinstance(item, (bytes, bytearray)):
                out += bytes(item)
                va += len(item)
                continue
            text = item.format(**{k: hex(v) for k, v in labels.items()})
            enc, _ = ks.asm(text, va)
            if enc is None:
                raise RuntimeError("keystone failed on: %s" % text)
            out += bytes(enc)
            va += len(enc)
        if seen == labels:
            return out
        labels = seen
    raise RuntimeError("cave layout did not converge")


def build_caves():
    """Return {cave_va: bytes}."""
    blob = asm_layout([
        (None,     "push ebx"),
        (None,     "mov ebx, eax"),
        # the original query, unchanged semantics (EDX still holds the caller's id)
        (None,     "mov ecx, dword ptr [eax]"),
        (None,     "call dword ptr [ecx + %s]" % hex(SLOT_ENABLED)),
        (None,     "test al, al"),
        (None,     "jne {TRUE}"),
        # ...else: does this object's stack carry Leadership >= LEAD_LEVEL?
        # +0xB8 GetAbilityOwner, NOT +0xB0 GetAbilityLevel -- see THE TRAP above.
        (None,     "mov eax, ebx"),
        (None,     "mov ecx, dword ptr [eax]"),
        (None,     "call dword ptr [ecx + %s]" % hex(SLOT_OWNER)),
        (None,     "test eax, eax"),
        (None,     "je {FALSE}"),
        (None,     "mov edx, %s" % hex(AB_LEADERSHIP)),
        (None,     "mov ecx, dword ptr [eax]"),
        (None,     "call dword ptr [ecx + %s]" % hex(SLOT_LEVEL)),
        (None,     "cmp eax, %d" % LEAD_LEVEL),
        (None,     "jl {FALSE}"),
        ("TRUE",   "mov eax, 1"),
        (None,     "pop ebx"),
        (None,     "ret"),
        ("FALSE",  "xor eax, eax"),
        (None,     "pop ebx"),
        (None,     "ret"),
    ], C_FEAR)
    if len(blob) > CAVE_END - CAVE_BASE:
        raise RuntimeError("cave is %d bytes, the span is %d"
                           % (len(blob), CAVE_END - CAVE_BASE))
    # position-independence: no absolute reference may appear in the cave. Every
    # call here is an indirect VMT dispatch, so no dword in the image's VA range
    # should occur at all.
    for i in range(len(blob) - 3):
        w = struct.unpack_from("<I", blob, i)[0]
        if 0x55700000 <= w < 0x55A00000:
            raise RuntimeError("cave holds what looks like an absolute VA 0x%08X "
                               "at +0x%X -- it must be position-independent" % (w, i))
    return {C_FEAR: blob}


def build_hooks():
    """Return {site_va: (original_bytes, patched_bytes)}."""
    return {s: (orig_bytes(s), patched_bytes(s)) for s in SITES}


# ------------------------------------------------------------------ plumbing ---
def read_dll():
    if not os.path.exists(DLL):
        sys.exit("not found: %s" % DLL)
    with open(DLL, "rb") as f:
        d = bytearray(f.read())
    if _BASE is None:
        resolve_base(d)
    return d


def kill_game():
    """Standing authorization: the game/editor lock the binaries. Just kill them."""
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
         " | Stop-Process -Force"],
        capture_output=True)


def state(d, caves, hooks):
    """-> 'vanilla' | 'applied' | 'mixed'"""
    ok, bad = [], []
    for site, (orig, patch) in hooks.items():
        cur = bytes(d[off(site):off(site) + len(orig)])
        (ok if cur == patch else bad).append(cur == orig)
    for va, blob in caves.items():
        cur = bytes(d[off(va):off(va) + len(blob)])
        (ok if cur == blob else bad).append(cur == bytes(len(blob)))
    if not bad:
        return "applied"
    if not ok and all(bad):
        return "vanilla"
    return "mixed"


def show(d, caves, hooks):
    print("AoWEPACK.dpl  %s" % DLL)
    print("  Leadership >= %d  =>  the whole stack counts as Fearless" % LEAD_LEVEL)
    for site in sorted(hooks):
        orig, patch = hooks[site]
        desc = SITES[site][0]
        cur = bytes(d[off(site):off(site) + len(orig)])
        tag = "PATCHED" if cur == patch else ("vanilla" if cur == orig
                                              else "*** FOREIGN ***")
        print("  site 0x%08X  %-8s  %s" % (site, tag, desc))
    for va, blob in sorted(caves.items()):
        cur = bytes(d[off(va):off(va) + len(blob)])
        tag = "PATCHED" if cur == blob else ("zero" if cur == bytes(len(blob))
                                             else "*** FOREIGN ***")
        print("  cave 0x%08X  %-8s  %d bytes" % (va, tag, len(blob)))
    print("  state: %s" % state(d, caves, hooks).upper())


def disassemble(caves):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        sys.exit("capstone not installed:  pip install capstone")
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for va, blob in sorted(caves.items()):
        print("\n---- 0x%08X  C_FEAR  (Fearless, or Leadership >= %d on the stack)"
              % (va, LEAD_LEVEL))
        for i in md.disasm(bytes(blob), va):
            print("  %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic,
                                           i.op_str))
    print("\n---- patched site runs")
    for site in sorted(SITES):
        print("  0x%08X  %s" % (site, patched_bytes(site).hex()))
        for i in md.disasm(patched_bytes(site), site):
            print("    %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic,
                                             i.op_str))


def check_space(d, caves):
    """Every byte of the cave span must be zero or already ours."""
    span = bytes(d[off(CAVE_BASE):off(CAVE_END)])
    ours = bytearray(CAVE_END - CAVE_BASE)
    for va, blob in caves.items():
        ours[va - CAVE_BASE:va - CAVE_BASE + len(blob)] = blob
    for i, b in enumerate(span):
        if b != 0 and b != ours[i]:
            sys.exit("ABORT: cave span byte 0x%08X = 0x%02X, neither zero nor ours"
                     % (CAVE_BASE + i, b))


def do_apply(d, caves, hooks):
    st = state(d, caves, hooks)
    if st == "applied":
        print("already applied -- nothing to do.")
        return
    if st == "mixed":
        sys.exit("ABORT: partially applied / foreign bytes present. Run --undo first.")
    check_space(d, caves)
    for site, (orig, _patch) in hooks.items():
        cur = bytes(d[off(site):off(site) + len(orig)])
        if cur != orig:
            sys.exit("ABORT: 0x%08X is %s, expected %s" % (site, cur.hex(), orig.hex()))

    kill_game()
    if not os.path.exists(BACKUP):
        import shutil
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("backup -> %s" % os.path.basename(BACKUP))

    for va, blob in caves.items():
        d[off(va):off(va) + len(blob)] = blob
    for site, (_orig, patch) in hooks.items():
        d[off(site):off(site) + len(patch)] = patch

    with open(DLL, "wb") as f:
        f.write(d)
    print("APPLIED: 1 cave, %d sites." % len(hooks))


def do_undo(d, caves, hooks):
    st = state(d, caves, hooks)
    if st == "vanilla":
        print("not applied -- nothing to undo.")
        return
    for site, (orig, patch) in hooks.items():
        cur = bytes(d[off(site):off(site) + len(orig)])
        if cur not in (orig, patch):
            sys.exit("ABORT: 0x%08X is foreign (%s)" % (site, cur.hex()))
    for va, blob in caves.items():
        cur = bytes(d[off(va):off(va) + len(blob)])
        if cur not in (blob, bytes(len(blob))):
            sys.exit("ABORT: cave 0x%08X is foreign" % va)

    kill_game()
    for site, (orig, _patch) in hooks.items():
        d[off(site):off(site) + len(orig)] = orig
    for va, blob in caves.items():
        d[off(va):off(va) + len(blob)] = bytes(len(blob))
    with open(DLL, "wb") as f:
        f.write(d)
    print("UNDONE: %d sites restored, cave zeroed. No backup touched." % len(hooks))


def main():
    args = sys.argv[1:]
    d = read_dll()
    caves, hooks = build_caves(), build_hooks()
    if "--dis" in args:
        disassemble(caves)
    if "--undo" in args:
        do_undo(d, caves, hooks)
    elif "--apply" in args:
        do_apply(d, caves, hooks)
    else:
        show(d, caves, hooks)
        if "--dis" not in args:
            print("\n(dry run -- pass --apply to write, --dis to disassemble the cave)")
        return
    show(read_dll(), caves, hooks)


if __name__ == "__main__":
    main()
