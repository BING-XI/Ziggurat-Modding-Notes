#!/usr/bin/env python3
r"""
AoW1 mod -- "terroronce": each SIDE casts Terror at most ONCE per combat.

FULL ANALYSIS: Modding Resources/Zig notes/Terror_OncePerCombat.md
Prior art (third party, tactical arm only): Modding Resources/Inioch/share1/
    Inioch_AI_Combat_Spell_Architecture.md  +  Zig notes/AI Combat-Spell Anti-Spam.md

================================================================================
THE PROBLEM
================================================================================
The AI re-casts Terror every combat turn it can afford it. Terror's effect does not
stack usefully, so every re-cast is a wasted casting action.

================================================================================
THE TWO COMBAT CONTEXTS  (this split is the whole difficulty)
================================================================================
AoW1 scores and casts combat spells through two completely separate paths. A hook
that works in one does not fire in the other.

  TACTICAL (the battle the player watches)
      value : VMT +0x88  CombatSpells.TTerror.tcGetDamageValueEx @0x557F9D44
              -> writes an output struct through stack arg 1; ret 4
              driver picks the single HIGHEST-priority action, so merely shrinking
              the score is enough to make Terror lose to anything else.
      cast  : CombatSpells.TTacticalCombatTerrorCA.Execute @0x557F990C
              (Terror is one of the few spells with a DEDICATED tactical CA --
              spells without one go through a generic TCombatSpellCA and need the
              much harder TSpell.CombatCastingDone + VMT-identity treatment.)

  FAST / AUTO-RESOLVE
      value : CombatSpells.TTerror.fcPrefetchCombatCommands @0x557F9B20
              *** NOT fcGetDamageValueEx. *** Terror DOES override VMT +0x98
              (fcGetDamageValueEx @0x557F9C2C, slot 0x557F626C) but that method is
              DEAD for Terror: fcPrefetchCombatCommands accumulates the value inline
              into EBP and never calls it. Verified: 0 direct rel32 refs and exactly
              1 absolute dword ref (its own VMT slot) anywhere in the module.
              Gating +0x98 would assemble, verify, and do nothing.
      cast  : CombatSpells.TTerror.fcExecuteCombatCommand @0x557F9BE8 (VMT +0x94)

  Driver semantics differ, and this is the landmine:
      tactical  -- highest-priority action wins   => shrinking the value is enough
      fast      -- a queued command is dropped ONLY when its value is exactly 0
                   (any value >= 1 stays queued and still wins when the AI has
                   nothing better), so "divide by 64" would NOT cap it there.

================================================================================
THE FIX -- a PER-SIDE flag, two writers, two gates
================================================================================
F_SIDE = 0x558FAC00, FOUR bytes of BSS-page slack, indexed by combat side (see
"THE SIDE INDEX" below). Each side of a battle gets its own one-cast budget.

  1. TCombat.Create @0x5572708C -> F_SIDE[0..3] = 0   (once per battle)
  2. TTacticalCombatTerrorCA.Execute+0x12 @0x557F991E -> F_SIDE[side(target)] = 1
  3. TTerror.fcExecuteCombatCommand @0x557F9BE8       -> F_SIDE[side(actor)] = 1
  4. VMT +0x88 slot 0x557F625C -> C_WRAPTC: call the original, then if
     F_SIDE[side(target)]:  value = max(1, value >> 6),  value100 = value / 100
     Floor 1, not 0, deliberately: Terror stays castable when it is that side's
     ONLY combat spell, it just loses to literally anything else.
  5. TTerror.fcPrefetchCombatCommands @0x557F9B20 -> C_FCPRE: if F_SIDE[side(actor)],
     return immediately, so no Terror command is ever queued. This is a HARD cap in
     auto-resolve, because a soft one is not possible there (see driver semantics).

================================================================================
THE SIDE INDEX
================================================================================
AoWE.TCombatObject.GetOpponentSide @0x55726688 is the whole story:

    bl = [obj+0x45]                       ; the object's player slot
    if bl == 0xFF: return 2               ; object with no owning player
    return [GetPlayers([[[obj+8]+0xC]+0x38], bl) + 0xA] XOR 1

-- so a combat side is [player+0xA], sides are exactly {0,1} (the XOR 1 proves it),
and 2 is the no-owner escape. There is no GetSide; GetOpponentSide is the accessor.

Each site derives the CASTING side's index from whatever object it actually has:

    site                              object in hand      index
    tcGetDamageValueEx wrapper        ECX = target        GetOpponentSide(target)
    TacticalCombatTerrorCA.Execute    FindID([CA+0xD])    GetOpponentSide(target)
    fcPrefetchCombatCommands          [EDX+4] = actor     GetOpponentSide(actor) XOR 1
    fcExecuteCombatCommand            EDX    = actor      GetOpponentSide(actor) XOR 1

The two tactical sites use the same target-derived expression, and the two fast
sites use the same actor-derived one, so each MODE is self-consistent -- which is
all that is required, because a battle is either watched or auto-resolved, never
both, and the flags reset at TCombat.Create.

The index is masked to 0..3 and the array is 4 bytes, so the no-owner escape (2,
or 3 after the XOR) can never write out of bounds. GetOpponentSide returns in AL
only -- the upper 24 bits of EAX are the incoming pointer on the escape path -- so
every site does MOVZX EAX,AL before masking.

GetOpponentSide preserves EBX/ESI/EDI/EBP (it push/pops EBX and ESI) and clobbers
EAX/ECX/EDX. Every cave is built around that.

Ordering in fast combat is self-consistent: prefetch (flag clear) -> queue ->
execute (sets flag) -> next round's prefetch returns early.

WHY THE VMT SLOT AND NOT AN E9 HOOK ON 0x557F9D44
    tcGetDamageValueEx has 0 direct rel32 callers and exactly 1 absolute dword ref
    -- its VMT slot. Every call goes through the slot, so repointing it intercepts
    all of them, displaces nothing, and undoes with a 4-byte write. The slot has a
    .reloc entry (RVA 0x0F625C, verified), so the loader rebases our new pointer
    exactly as it rebased the old one.

BSS
    The BSS section is VA 0x558EA000..0x558FA231 with rawsize 0; the loader maps and
    zero-fills the whole final page, so 0x558FA231..0x558FAFFF is committed scratch.
    F_SIDE = 0x558FAC00..0x558FAC03 is fresh: the nearest addresses any build script
    claims are 0x558FAB7F (build_shipyard_income.py) below and 0x558FAF20 above.
    *** 0x558FAF20/21/22 -- the flag bytes the third-party notes use -- are OWNED by
    build_shipyard_income.py. Do not "restore" them. ***
    BSS bytes are runtime-only: asserting on file bytes there chases a phantom.

CAVES
    0x5582A000..0x5582A200 in CODE. Verified all-zero in the live DLL and clear of
    every AoWEPACK address any build script claims (nearest below: 0x55828000).
    *** Do NOT use the third-party cave VAs 0x5580DCE8 / 0x5580DD14 / 0x5580DD34:
    0x5580DD0E, 0x5580DD20 and 0x5580DD30 are already ours. ***
    All caves are position-independent (call/pop/sub delta for the flag byte,
    rel32 for calls and jumps) -- the .dpl rebases at runtime.

RNG
    No cave draws a random number, so the SYNCED/RAW rule does not apply. Re-run
    re_tools/rng_audit.py --owners after --apply anyway; the new sites must print ok.

MULTIPLAYER
    The flag is derived purely from replicated combat state (a cast happened / a
    combat started), so every peer sets and clears it at the same points.

USAGE
    python build_scripts/build_terror_oncepercombat.py            # verify only
    python build_scripts/build_terror_oncepercombat.py --dis      # + cave disasm
    python build_scripts/build_terror_oncepercombat.py --apply
    python build_scripts/build_terror_oncepercombat.py --undo     # surgical
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
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-terroronce")
BASE = 0x55700C00                      # VA = file_offset + BASE

# ---------------------------------------------------------------- addresses ---
F_SIDE = 0x558FAC00                    # BSS-page slack, FOUR bytes, indexed by side

TCOMBAT_CREATE = 0x5572708C            # AoWE.TCombat.Create
TAC_HOOK       = 0x557F991E            # CombatSpells.TTacticalCombatTerrorCA.Execute + 0x12
TAC_RESUME     = 0x557F9926            #   -> resume at `mov edi,eax`
FC_EXECUTE     = 0x557F9BE8            # CombatSpells.TTerror.fcExecuteCombatCommand
FC_PREFETCH    = 0x557F9B20            # CombatSpells.TTerror.fcPrefetchCombatCommands
VMT_TC_SLOT    = 0x557F625C            # CombatSpells..TTerror + 0x88
TC_ORIG        = 0x557F9D44            # CombatSpells.TTerror.tcGetDamageValueEx

GET_OPP_SIDE   = 0x55726688            # AoWE.TCombatObject.GetOpponentSide (EAX=obj -> AL)
FIND_ID        = 0x55728C68            # AoWE.TCombatData.FindID (EAX=data, EDX=id -> EAX=obj)

# displaced runs, verbatim, for verify-before-write at each hook site
ORIG = {
    TCOMBAT_CREATE: bytes.fromhex("558bec5153"),      # push ebp;mov ebp,esp;push ecx;push ebx
    TAC_HOOK:       bytes.fromhex("8b460ce842f3f2ff"),# mov eax,[esi+0xc]; call FindID  (8 bytes)
    FC_EXECUTE:     bytes.fromhex("5356578bf2"),      # push ebx;push esi;push edi;mov esi,edx
    FC_PREFETCH:    bytes.fromhex("5356575583c4f8"),  # ...push ebp;add esp,-8          (7 bytes)
}
# TAC_HOOK's run contains a `call rel32`, so it is RE-ASSEMBLED in the cave rather
# than copied -- a verbatim copy would carry the original site's displacement.
RESUME = {TCOMBAT_CREATE: TCOMBAT_CREATE + 5,
          TAC_HOOK:       TAC_RESUME,
          FC_EXECUTE:     FC_EXECUTE + 5,
          FC_PREFETCH:    FC_PREFETCH + len(ORIG[FC_PREFETCH])}

CAVE_BASE = 0x5582A000
CAVE_END  = 0x5582A200                 # asserted zero-or-ours across this whole span
C_RESET   = 0x5582A000
C_SETTAC  = 0x5582A040
C_SETFC   = 0x5582A080
C_FCPRE   = 0x5582A0C0
C_WRAPTC  = 0x5582A120
CAVE_ORDER = [C_RESET, C_SETTAC, C_SETFC, C_FCPRE, C_WRAPTC]
# each cave must fit in the gap before the next one (the last, before CAVE_END)
CAVE_SLOT = {va: (CAVE_ORDER + [CAVE_END])[k + 1] - va
             for k, va in enumerate(CAVE_ORDER)}

SHIFT = 6                              # tactical deprioritise: value >> SHIFT, floor 1


def off(va):
    return va - BASE


# ------------------------------------------------------------- mini assembler --
def _ks():
    try:
        from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    except ImportError:
        sys.exit("keystone-engine not installed:  pip install keystone-engine")
    return Ks(KS_ARCH_X86, KS_MODE_32)


def asm_layout(frags, base):
    """frags: list of (label|None, text|bytes|None). Text may use {LABEL} placeholders.
    Iterates to a fixed point so forward references settle."""
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
    caves = {}

    # ---- C_RESET: clear all four side flags, replay TCombat.Create's prologue --
    caves[C_RESET] = asm_layout([
        (None,   "push eax"),
        (None,   "call {N}"),
        ("N",    "pop eax"),
        (None,   "sub eax, {N}"),
        (None,   "mov dword ptr [eax + %s], 0" % hex(F_SIDE)),
        (None,   "pop eax"),
        (None,   ORIG[TCOMBAT_CREATE]),
        (None,   "jmp %s" % hex(RESUME[TCOMBAT_CREATE])),
    ], C_RESET)

    # ---- C_SETTAC: tactical cast -> F_SIDE[GetOpponentSide(target)] = 1 --------
    # in:  ebx = the CA, esi = combat data, edx = [CA+0xD] = the target's id.
    # The displaced pair IS the target lookup, so we get the object for free.
    # GetOpponentSide preserves ebx/esi/edi, which the resumed code still needs.
    caves[C_SETTAC] = asm_layout([
        (None,   "mov eax, dword ptr [esi + 0xc]"),   # displaced (re-assembled:
        (None,   "call %s" % hex(FIND_ID)),           #  the run holds a call rel32)
        (None,   "push eax"),                         # keep the target for `mov edi,eax`
        (None,   "call %s" % hex(GET_OPP_SIDE)),      # al = casting side
        (None,   "movzx eax, al"),
        (None,   "and eax, 3"),
        (None,   "push eax"),
        (None,   "call {N}"),
        ("N",    "pop ecx"),
        (None,   "sub ecx, {N}"),
        (None,   "pop eax"),
        (None,   "mov byte ptr [ecx + eax + %s], 1" % hex(F_SIDE)),
        (None,   "pop eax"),                          # restore the target object
        (None,   "jmp %s" % hex(RESUME[TAC_HOOK])),
    ], C_SETTAC)

    # ---- C_SETFC: fast cast -> F_SIDE[GetOpponentSide(actor) ^ 1] = 1 ----------
    # in: eax = self (the spell), edx = the casting combat object.
    caves[C_SETFC] = asm_layout([
        (None,   "push eax"),
        (None,   "push edx"),
        (None,   "mov eax, edx"),
        (None,   "call %s" % hex(GET_OPP_SIDE)),      # al = the OPPOSING side
        (None,   "movzx eax, al"),
        (None,   "xor eax, 1"),                       # -> the casting side
        (None,   "and eax, 3"),
        (None,   "push eax"),
        (None,   "call {N}"),
        ("N",    "pop ecx"),
        (None,   "sub ecx, {N}"),
        (None,   "pop eax"),
        (None,   "mov byte ptr [ecx + eax + %s], 1" % hex(F_SIDE)),
        (None,   "pop edx"),
        (None,   "pop eax"),
        (None,   ORIG[FC_EXECUTE]),
        (None,   "jmp %s" % hex(RESUME[FC_EXECUTE])),
    ], C_SETFC)

    # ---- C_FCPRE: if that side already cast, queue nothing ---------------------
    # in: eax = self, edx = the command list; [edx+4] is the acting combat object
    # (the function's own expression). `pop` does not touch flags, so the cmp
    # result survives the two pops before the jne.
    caves[C_FCPRE] = asm_layout([
        (None,     "push eax"),
        (None,     "push edx"),
        (None,     "mov eax, dword ptr [edx + 4]"),
        (None,     "call %s" % hex(GET_OPP_SIDE)),
        (None,     "movzx eax, al"),
        (None,     "xor eax, 1"),
        (None,     "and eax, 3"),
        (None,     "call {N}"),
        ("N",      "pop ecx"),
        (None,     "sub ecx, {N}"),
        (None,     "cmp byte ptr [ecx + eax + %s], 0" % hex(F_SIDE)),
        (None,     "pop edx"),
        (None,     "pop eax"),
        (None,     "jne {DROP}"),
        (None,     ORIG[FC_PREFETCH]),
        (None,     "jmp %s" % hex(RESUME[FC_PREFETCH])),
        ("DROP",   "ret"),
    ], C_FCPRE)

    # ---- C_WRAPTC: tactical value wrapper -------------------------------------
    # entry: eax=self, ecx=target, [esp+4]=out ptr, callee cleans 4 bytes.
    # The original clobbers ecx, so the target is stashed in esi FIRST; eax/ecx/edx
    # must reach the original untouched. out+0x00 = value, out+0x04 = value/100.
    caves[C_WRAPTC] = asm_layout([
        (None,    "push ebx"),
        (None,    "push esi"),
        (None,    "mov ebx, dword ptr [esp + 0xc]"),  # out ptr
        (None,    "mov esi, ecx"),                    # target, for the side lookup
        (None,    "push ebx"),                        # re-push arg 1
        (None,    "call %s" % hex(TC_ORIG)),          # original; it does ret 4
        (None,    "mov eax, esi"),
        (None,    "call %s" % hex(GET_OPP_SIDE)),     # al = casting side
        (None,    "movzx eax, al"),
        (None,    "and eax, 3"),
        (None,    "call {N}"),
        ("N",     "pop ecx"),
        (None,    "sub ecx, {N}"),
        (None,    "cmp byte ptr [ecx + eax + %s], 0" % hex(F_SIDE)),
        (None,    "je {DONE}"),
        (None,    "mov eax, dword ptr [ebx]"),
        (None,    "test eax, eax"),
        (None,    "je {DONE}"),
        (None,    "shr eax, %d" % SHIFT),
        (None,    "jne {KEEP}"),
        (None,    "inc eax"),                         # floor at 1
        ("KEEP",  "mov dword ptr [ebx], eax"),
        (None,    "mov ecx, 100"),
        (None,    "cdq"),
        (None,    "idiv ecx"),
        (None,    "mov dword ptr [ebx + 4], eax"),
        ("DONE",  "pop esi"),
        (None,    "pop ebx"),
        (None,    "ret 4"),
    ], C_WRAPTC)

    for va in CAVE_ORDER:
        if len(caves[va]) > CAVE_SLOT[va]:
            raise RuntimeError("cave 0x%08X is %d bytes, its slot is %d -- move the "
                               "later caves up" % (va, len(caves[va]), CAVE_SLOT[va]))
    return caves


def build_hooks():
    """Return {site_va: (original_bytes, patched_bytes)} for the E9 hook sites."""
    out = {}
    for site, cave in ((TCOMBAT_CREATE, C_RESET), (TAC_HOOK, C_SETTAC),
                       (FC_EXECUTE, C_SETFC), (FC_PREFETCH, C_FCPRE)):
        orig = ORIG[site]
        rel = cave - (site + 5)
        patch = b"\xE9" + struct.pack("<i", rel) + b"\x90" * (len(orig) - 5)
        assert len(patch) == len(orig)
        out[site] = (orig, patch)
    return out


# ------------------------------------------------------------------ plumbing ---
def read_dll():
    if not os.path.exists(DLL):
        sys.exit("not found: %s" % DLL)
    with open(DLL, "rb") as f:
        return bytearray(f.read())


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
        (ok if cur == patch else bad).append(("hook 0x%08X" % site, cur == orig))
    cur = struct.unpack_from("<I", d, off(VMT_TC_SLOT))[0]
    (ok if cur == C_WRAPTC else bad).append(("vmt slot", cur == TC_ORIG))
    for va, blob in caves.items():
        cur = bytes(d[off(va):off(va) + len(blob)])
        (ok if cur == blob else bad).append(("cave 0x%08X" % va, cur == bytes(len(blob))))
    if not bad:
        return "applied"
    if not ok and all(pristine for _, pristine in bad):
        return "vanilla"
    return "mixed"


def show(d, caves, hooks):
    print("AoWEPACK.dpl  %s" % DLL)
    for site, (orig, patch) in sorted(hooks.items()):
        cur = bytes(d[off(site):off(site) + len(orig)])
        tag = "PATCHED" if cur == patch else ("vanilla" if cur == orig else "*** FOREIGN ***")
        print("  hook 0x%08X  %-22s %s" % (site, cur.hex(), tag))
    cur = struct.unpack_from("<I", d, off(VMT_TC_SLOT))[0]
    tag = "PATCHED" if cur == C_WRAPTC else ("vanilla" if cur == TC_ORIG else "*** FOREIGN ***")
    print("  vmt  0x%08X  -> 0x%08X          %s" % (VMT_TC_SLOT, cur, tag))
    for va, blob in sorted(caves.items()):
        cur = bytes(d[off(va):off(va) + len(blob)])
        tag = "PATCHED" if cur == blob else ("zero" if cur == bytes(len(blob)) else "*** FOREIGN ***")
        print("  cave 0x%08X  %3d bytes                %s" % (va, len(blob), tag))
    print("  flag 0x%08X..%02X  (BSS x4, runtime-only -- not checkable in the file)"
          % (F_SIDE, (F_SIDE + 3) & 0xFF))
    print("  state: %s" % state(d, caves, hooks).upper())


def disassemble(caves):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        sys.exit("capstone not installed:  pip install capstone")
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    names = {C_RESET: "C_RESET  (TCombat.Create -> F_SIDE[0..3]=0)",
             C_SETTAC: "C_SETTAC (tactical cast -> F_SIDE[side(target)]=1)",
             C_SETFC: "C_SETFC  (fast cast -> F_SIDE[side(actor)]=1)",
             C_FCPRE: "C_FCPRE  (fast prefetch -> early ret if that side cast)",
             C_WRAPTC: "C_WRAPTC (VMT +0x88 value wrapper, per-side)"}
    for va, blob in sorted(caves.items()):
        print("\n---- 0x%08X  %s" % (va, names[va]))
        for i in md.disasm(bytes(blob), va):
            print("  %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))


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
    for site, (orig, patch) in hooks.items():
        cur = bytes(d[off(site):off(site) + len(orig)])
        if cur != orig:
            sys.exit("ABORT: 0x%08X is %s, expected %s" % (site, cur.hex(), orig.hex()))
    cur = struct.unpack_from("<I", d, off(VMT_TC_SLOT))[0]
    if cur != TC_ORIG:
        sys.exit("ABORT: vmt slot 0x%08X = 0x%08X, expected 0x%08X"
                 % (VMT_TC_SLOT, cur, TC_ORIG))

    kill_game()
    if not os.path.exists(BACKUP):
        import shutil
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("backup -> %s" % os.path.basename(BACKUP))

    for va, blob in caves.items():
        d[off(va):off(va) + len(blob)] = blob
    for site, (_, patch) in hooks.items():
        d[off(site):off(site) + len(patch)] = patch
    struct.pack_into("<I", d, off(VMT_TC_SLOT), C_WRAPTC)

    with open(DLL, "wb") as f:
        f.write(d)
    print("APPLIED: %d caves, %d hooks, 1 vmt slot." % (len(caves), len(hooks)))


def do_undo(d, caves, hooks):
    st = state(d, caves, hooks)
    if st == "vanilla":
        print("not applied -- nothing to undo.")
        return
    for site, (orig, patch) in hooks.items():
        cur = bytes(d[off(site):off(site) + len(orig)])
        if cur not in (orig, patch):
            sys.exit("ABORT: 0x%08X is foreign (%s)" % (site, cur.hex()))
    cur = struct.unpack_from("<I", d, off(VMT_TC_SLOT))[0]
    if cur not in (TC_ORIG, C_WRAPTC):
        sys.exit("ABORT: vmt slot is foreign (0x%08X)" % cur)
    for va, blob in caves.items():
        c = bytes(d[off(va):off(va) + len(blob)])
        if c not in (blob, bytes(len(blob))):
            sys.exit("ABORT: cave 0x%08X is foreign" % va)

    kill_game()
    for site, (orig, _) in hooks.items():
        d[off(site):off(site) + len(orig)] = orig
    struct.pack_into("<I", d, off(VMT_TC_SLOT), TC_ORIG)
    for va, blob in caves.items():
        d[off(va):off(va) + len(blob)] = bytes(len(blob))
    with open(DLL, "wb") as f:
        f.write(d)
    print("UNDONE: hooks restored, vmt slot restored, caves zeroed. No backup touched.")


def main():
    args = sys.argv[1:]
    caves, hooks = build_caves(), build_hooks()
    d = read_dll()
    if "--dis" in args:
        disassemble(caves)
    if "--undo" in args:
        do_undo(d, caves, hooks)
    elif "--apply" in args:
        do_apply(d, caves, hooks)
    else:
        show(d, caves, hooks)
        if "--dis" not in args:
            print("\n(dry run -- pass --apply to write, --dis to disassemble the caves)")
        return
    show(read_dll(), caves, hooks)


if __name__ == "__main__":
    main()
