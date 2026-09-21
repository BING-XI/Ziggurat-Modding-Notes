#!/usr/bin/env python
r"""
build_minddecay_oos.py -- Mind Decay: make the combat to-hit roll DRAW-COUNT INVARIANT,
and add the nil check vanilla lacks.  (AoWEPACK.dpl only.)

STATUS: APPLIED, UNTESTED (2026-09-03).  Never label it confirmed without
the user's in-game test -- and the MP half needs two machines.

============================ WHY THIS IS A BUG =============================
AoW1 has two random generators sharing one seed variable (Zig notes/12-re-toolchain.md 4):

  SYNCED  AoWE.TAoWHSMap.Random @0x5577827C -- draws from the replicated store
          [map+0x230] and writes it back.  That store is exactly what the
          out-of-sync comparator (TPlayerControl.GetSyncValue) reads.
  RAW     System.@RandInt via the AoWEPACK thunk 0x55701080 -- draws from
          System.RandSeed, a per-process global.

AoWE.TCombat.Execute @0x557282C8 is a one-liner:
        System.RandSeed := TAoWHSMap.Random(map, $FFFFFF)
so a battle RE-ANCHORS the raw seed from one synchronised draw and then runs the
whole fight off raw draws, deterministically, on every peer.

The consequence this fix is about: **raw combat draws are invisible to the
out-of-sync comparator, but they only reproduce across machines if every peer
consumes the SAME NUMBER of draws.**  A conditional raw draw therefore diverges
*silently* -- different to-hit results, different deaths, and an OOS dialog
raised much later and far from the cause.

CombatSpells.TMindDecay.CreateCA @0x557F85DC has the widest such surface of any
combat spell.  Its one HitRole call sits behind FIVE gates, four of which
dereference the target's STRATEGIC unit [combatunit+0x4C] (TSlow / TEntangle
gate on a single check through the combat unit's own virtuals):

    IsClass(target, TCombatUnit)            -> else no roll
    u.GetUnitType()          == 2           -> no roll     (u = [target+0x4C])
    u.GetRace()              == 0x0B        -> no roll
    u.GetAbilityEnabled(0x81)               -> no roll     (0x81 = Animated)
    IsClass(u, TLeader)                     -> no roll

================================= THE FIX ==================================
Hoist the DRAW so it always happens; gate only the STORE.

    <the same five gates, no early exit>   -> eligible = 0/1
    eligible ? res = target.GetResistance() : res = 0
    ALWAYS   eax = [spell+0x34] - res ; call HitRole      (exactly one @RandInt)
    eligible ? [ca+0x14] = al : leave it 0, as vanilla

  * Eligible target  : identical outcome AND identical draw order to vanilla,
                       and an identical call graph (the gate virtuals and
                       GetResistance are called exactly where vanilla calls them).
  * Ineligible target: one extra @RandInt is consumed and discarded --
                       UNIFORMLY on every machine, since every peer runs this
                       same DLL.  No balance effect; the stream is random.
  * Plus the nil check vanilla lacks (see below).

====== WHY ONLY THE CALL IS HOISTED, NOT GetResistance -- IMPORTANT =========
Draw-count invariance depends on the NUMBER OF HitRole CALLS, not on their
inputs.  AoWE.HitRole is straight-line with exactly one unconditional
`call 0x55701080`; the two forward branches in it only clamp the chance to
10..90, and the draw is `@RandInt(100)` whatever the input.  So passing a
different (and discarded) input on the ineligible path costs exactly one draw
and nothing else.  This script re-asserts that property against the LIVE bytes
at write time and refuses to patch if HitRole ever stops making exactly one
@RandInt call.

⚠ That matters because the roll's other input is NOT safe to hoist.  The
resistance comes from the target's VMT slot +0x74, and it is true that the slot
is a TCombatObject base-class slot -- but TCombatUnit OVERRIDES it, and the
override is nothing but a forward through the strategic unit:

    AoWE.TCombatUnit.GetResistance @0x557254A8   (VMT 0x55715A94, slot +0x74)
        557254A8  8b 40 4c        mov  eax, [eax + 0x4C]     <-- STRATEGIC UNIT
        557254AB  8b 10           mov  edx, [eax]
        557254AD  ff 92 cc 00 00  call [edx + 0xCC]          ; TUnit.GetResistance
        557254B3  c3              ret
    AoWE.TCombatObject.GetResistance @0x55726864 = `xor eax,eax; ret`   (safe)

So calling GetResistance unconditionally would access-violate on exactly the
nil-[target+0x4C] case the new nil check exists to fix, and would additionally
call TUnit.GetResistance on a path where vanilla never calls it.  This script
therefore hoists ONLY the HitRole call and substitutes res = 0 on the ineligible
path.  Same objective, strictly smaller behavioural delta.

⚠⚠ FOR INIOCH.  His shipped `Inioch/share6/patch scripts/build_minddecay_oos.py`
hoists GetResistance out of the gate, on the stated premise that "resistance
comes from the target's own VMT+0x74 ... NOT from [target+0x4C]".  The premise is
false as shown above (his tree and ours agree byte-for-byte on 0x557254A8), so
that version carries a latent AV on any combat unit with a nil strategic twin --
the very crash its own nil check was added to remove.  Worth sending back.

THE NIL CHECK.  Vanilla dereferences [target+0x4C] at 0x557F862C guarded only by
IsClass(target, TCombatUnit) -- a combat unit with no strategic unit AVs there.
The cave tests it and falls through to "ineligible".  TCombatUnit instance size
is 92 (0x5C) so +0x4C is in bounds; the field is simply allowed to be nil.

HONEST SCOPE.  This removes the one concrete, mechanically verifiable RNG
asymmetry unique to Mind Decay.  The gates read synced state, so on two
correctly-synced machines they *should* already agree -- meaning this stops a
divergence from CASCADING through every later combat roll, and is NOT a proven
root-cause fix for any specific reported desync.  It cannot make things worse
(the extra draw is uniform on every peer), and it fixes a real crash risk on the
way.  NOT DONE, deliberately: nothing else in the OOS investigation.  This is one
function; TSlow / TEntangle / the other HitRole callers are untouched.

=========================== VERIFIED ON OUR DLL ============================
(2026-09-03, live AoWEPACK.dpl vs Modding Resources/AoWEPACK_original_backup.dpl)

  * CombatSpells.TMindDecay.CreateCA 0x557F85DC..0x557F869C is **byte-identical
    to pristine** -- the whole gate chain is VANILLA on our DLL.  This is a
    vanilla defect; neither Ziggurat nor Inioch's tree introduced it.
  * 0x55715A54 -> VMT 0x55715A94, selfptr ok, class name "TCombatUnit".
    0x557121F8 -> VMT 0x55712238, selfptr ok, class name "TLeader".
  * 0x557010C0 = `jmp [0x558FB6BC]` = VCL30!System.@IsClass, live == pristine.
  * Tail 0x557F868F = 8b c6 5f 5e 5b 59 5d c2 04, live == pristine.
  * Instance sizes: TCombatUnit 92 (+0x4C in bounds), TMindDecay 64 (+0x34 in
    bounds), TMindDecayCA 28 (+0x14 in bounds).
  * Cave zone 0x55842000..0x55843000: all zero, no .reloc entry anywhere in
    0x55830000..0x55850000, claimed by no other build script
    (`grep -ri 55842 build_scripts/` -> no hits).  It sits inside the
    0x558385ED..0x558E7918 zero run.  Nothing branches into it and no absolute
    dword constant in CODE points into it.

⚠ TWO LIVE-vs-PRISTINE DELTAS a future session will otherwise trip on:

  1. **AoWE.HitRole @0x55725D98 IS MODDED on our DLL** by build_hitslope5.py:
     pristine `add eax,eax / lea eax,[eax+eax*4]` (x10) is live `nop / nop /
     imul eax,eax,5` (x5) -- the 10pp -> 5pp to-hit slope conversion.  **The
     pristine decompile is the wrong reference for that function.**  What this
     patch depends on is unaffected: still straight-line, still exactly one
     unconditional @RandInt(100), still clamped 10..90.

  2. **CombatSpells.TMindDecay.Create IS MODDED on our DLL** (3 bytes) even
     though CreateCA is vanilla:
         [spell+0x34]  0x05 -> 0x0C   (set at 0x557F857F)
         [spell+0x39]  0x0C -> 0x08
         [spell+0x3A]  0x03 -> 0x04
     [spell+0x34] is the strength constant THIS roll consumes.  It is still a
     compile-time constant written in Create and never derived from the target,
     so the hoist is unaffected -- the cave simply reads whatever Create stored,
     exactly as vanilla does.

============================== HOOK SITE ===================================
Hook the 5-byte `call 0x557010C0` at **0x557F8623**:

    557F861B  8b c3               mov  eax, ebx              <- left intact
    557F861D  8b 15 54 5a 71 55   mov  edx, [0x55715A54]     <- left intact
    557F8623  e8 98 8a f0 ff      call 0x557010C0            <- becomes `jmp cave`

⭐ **This site was chosen BECAUSE IT IS RELOC-FREE.**  A `call rel32` carries no
base relocation, so nothing in the .reloc directory is touched: the directory is
byte-identical before and after --apply.  There are also no orphan bytes (5 for
5), and vanilla loads the TCombatUnit classref for us, so the cave needs one PIC
reference instead of two.

⚠ **REJECTED ALTERNATIVE -- 0x557F861B.  Do not "improve" this back.**  Hooking
the two instructions above instead (`mov eax,ebx` + `mov edx,[...]`, the `je`
target from 0x557F8613) displaces the imm32 of that `mov`, which carries a
**type-3 HIGHLOW base relocation at 0x557F861F** -- inside the five bytes a jmp
would overwrite.  The loader would then apply the fixup on top of our rel32 on
any rebased load, and AoWEPACK.dpl never loads at its preferred base.  That is
this project's most expensive bug class ("crashes on his machine, not mine,
identical files").  It can be handled -- neutralise the entry type 3 -> 0 on
apply, restore it on undo -- and an earlier revision of this script did exactly
that and round-tripped cleanly.  It was dropped anyway: eliminating the category
beats handling it correctly.  Inioch's script uses that site and does the reloc
surgery; ours does not need to.

⚠ THE CAVE DEPENDS ON THE TWO INSTRUCTIONS ABOVE THE HOOK.  It is entered with
EAX = target and EDX = the TCombatUnit classref, both set up by vanilla at
0x557F861B..0x557F8622, and its first instruction is the IsClass call it
displaced.  The script therefore pins those 8 bytes on every run and refuses to
write if anything else has hooked them.

Branch sweep (byte-aligned E8/E9/0F8x/7x/EB scan of the whole CODE section):
**nothing anywhere branches into 0x557F8623..0x557F8627**, so the 5 displaced
bytes are entered only by fall-through from 0x557F861D.  (The `je` at 0x557F8613
lands on 0x557F861B, which we leave intact.)  0x557F8628..0x557F868E becomes
unreachable; its only inbound branches come from within itself.  The shared tail
at 0x557F868F stays live and is where the cave returns.

PIC: AoWEPACK.dpl never loads at its preferred base, so the cave takes the load
delta with `call $+5 / pop edx / sub edx, <anchor VA>` (⚠ pop EDX, not EAX -- AL
carries the IsClass result at that point), parks it in a stack slot, and reaches
the TLeader classref cell as [delta + 0x557121F8].  Every call/jmp is rel32
within the same image.  No absolute memory operand, no baked path.

=================================== RNG ====================================
The cave calls HitRole, which is a *caller* of the RNG, not an RNG entry point,
so `rng_audit.py --owners` reports the same site count as before (23).  The draw
stays RAW, which is CORRECT: this is tactical combat, riding the seed
TCombat.Execute re-anchored.  Do NOT "fix" it to SYNCED -- a synced draw here
would trip the GetSynchronised guard and perturb [map+0x230], and the point of
this patch is draw-count symmetry, not changing the generator.

================================== PATCH ===================================
  0x557F8623  e8 98 8a f0 ff   ->   e9 <rel32 to cave>      (5 for 5, no orphans)
  0x55842000  cave_mdroll (PIC, 171 B in a 256 B reservation)
  .reloc                            UNTOUCHED

Usage:  python build_scripts/build_minddecay_oos.py           # dry run + verify
        python build_scripts/build_minddecay_oos.py --dis     # cave disassembly
        python build_scripts/build_minddecay_oos.py --apply   # write
        python build_scripts/build_minddecay_oos.py --undo    # surgical revert
Idempotent, verify-before-write, dry-run by default.  --undo restores the five
bytes and zeroes the cave -- touching no backup.  The snapshot
`<game dir>\backups\AoWEPACK.dpl.pre-minddecayoos` is taken ONLY from a file
positively proved free of this feature (vanilla call bytes at the hook + cave
zone zero).

RE-TUNE.  Never "revert and re-apply" -- there is no snapshot layer to fall back
on.  Editing SRC and re-running --apply REWRITES the cave in place: the state
check accepts a non-zero reservation as our own previous output (the zone is
exclusive to this script and reachable only through our own hook), zeroes the
whole reservation before writing, and asserts the rest of the exclusive zone
0x55842100..0x55843000 is still zero so the cave can grow safely.  No backup is
taken on that path -- the file already carries the feature, so it would not be a
pre-feature snapshot.
"""
import os
import re
import shutil
import struct
import subprocess
import sys

from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

DLL_BASE = 0x55700000
SUFFIX = ".pre-minddecayoos"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)

HOOK = 0x557F8623                       # the `call System.@IsClass` -- reloc-free, 5 for 5
ORIG = bytes.fromhex("e8988af0ff")      # call 0x557010C0
PRE_VA = 0x557F861B                     # the two instructions the cave's entry state depends on
PRE_BYTES = bytes.fromhex("8bc38b15545a7155")   # mov eax,ebx / mov edx,[TCombatUnit classref]
POST_VA = 0x557F8628                    # version pin (dead once hooked, but pins the build)
POST_BYTES = bytes.fromhex("84c0")      # test al,al
TAIL = 0x557F868F                       # mov eax,esi / pop edi,esi,ebx,ecx,ebp / ret 4
TAIL_BYTES = bytes.fromhex("8bc65f5e5b595dc204")

CAVE = 0x55842000                       # exclusive zone 0x55842000..0x55843000
CAVE_ZONE_LEN = 0x100                   # reservation incl. growth slack; asserted zero (or ours)
ZONE_END = 0x55843000                   # rest of the exclusive zone: asserted zero, never written

CLS_LEADER = 0x557121F8                 # -> VMT 0x55712238 "TLeader"
ISCLASS = 0x557010C0                    # jmp [0x558FB6BC] = VCL30!System.@IsClass (EAX=obj, EDX=cls)
HITROLE = 0x55725D98                    # AoWE.HitRole (EAX = stat diff -> AL 0/1, one @RandInt)
RANDINT = 0x55701080                    # AoWEPACK thunk -> VCL30!System.@RandInt
ANIMATED = 0x81                         # PassiveAb.TAnimatedAbility

# --- cave_mdroll -------------------------------------------------------------
# entry: EAX = target combat object, EDX = TCombatUnit classref  (both loaded by the
#        vanilla instructions at 0x557F861B..0x557F8622, which we leave intact)
#        EBX = target, ESI = the TMindDecayCA, EDI = the TMindDecay spell, EBP = caller frame.
#        EBX/ESI/EDI/EBP survive every call below (Delphi register convention; vanilla
#        relies on exactly that across the same calls).
# frame: [esp+0] = PIC load delta,  [esp+4] = eligible flag
# ⚠ keystone HANGS on ';' comment lines inside an asm block -- keep SRC comment-free.
SRC = """
    call {isclass:#x}
    sub  esp, 8
    call _anch
_anch:
    pop  edx
    sub  edx, {anchor:#x}
    mov  dword ptr [esp], edx
    mov  dword ptr [esp + 4], 0
    test al, al
    je   _roll

    mov  eax, dword ptr [ebx + 0x4C]
    test eax, eax
    je   _roll

    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0x114]
    cmp  al, 2
    je   _roll

    mov  eax, dword ptr [ebx + 0x4C]
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0xA4]
    movsx eax, al
    cmp  ax, 0xB
    je   _roll

    mov  eax, dword ptr [ebx + 0x4C]
    mov  edx, {animated:#x}
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0x148]
    test al, al
    jne  _roll

    mov  eax, dword ptr [ebx + 0x4C]
    mov  edx, dword ptr [esp]
    mov  edx, dword ptr [edx + {clsleader:#x}]
    call {isclass:#x}
    test al, al
    jne  _roll

    mov  dword ptr [esp + 4], 1

_roll:
    xor  edx, edx
    cmp  dword ptr [esp + 4], 0
    je   _diff
    mov  eax, ebx
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0x74]
    movsx edx, al
_diff:
    movsx eax, byte ptr [edi + 0x34]
    sub  eax, edx
    call {hitrole:#x}
    cmp  dword ptr [esp + 4], 0
    je   _out
    mov  byte ptr [esi + 0x14], al
_out:
    add  esp, 8
    jmp  {tail:#x}
"""


def asm(anchor):
    src = SRC.format(anchor=anchor, clsleader=CLS_LEADER, isclass=ISCLASS,
                     hitrole=HITROLE, tail=TAIL, animated=ANIMATED)
    return bytes(ks.asm(src, CAVE)[0])


# two-pass: pass 1 locates the call/pop anchor (imm32 length is stable), pass 2 fixes it up.
# ⚠ the FIRST instruction is also an E8, so match on the zero-displacement form only.
_tmp = asm(CAVE)
_ai = _tmp.index(b"\xE8\x00\x00\x00\x00") + 5           # offset of `pop edx`
CAVE_CODE = asm(CAVE + _ai)
assert CAVE_CODE[_ai] == 0x5A, "call/pop anchor mismatch (expected `pop edx`, not `pop eax`)"
assert len(CAVE_CODE) == len(_tmp), "cave length changed between passes"
assert len(CAVE_CODE) <= CAVE_ZONE_LEN, "cave overflows its %d B reservation" % CAVE_ZONE_LEN
# PIC self-check: the DPL rebases, so the cave must contain no absolute memory operand.
# capstone renders one as a bare `[0x........]` with no base register; every legitimate
# reference here is either `[reg + disp32]` (the load-delta idiom) or `[esp...]`.
for _ins in cs.disasm(CAVE_CODE, CAVE):
    assert not re.search(r"\[0x[0-9a-f]+\]", _ins.op_str), \
        "absolute mem operand in cave (breaks on rebase): %08X %s %s" \
        % (_ins.address, _ins.mnemonic, _ins.op_str)
# ...and no drive-letter path or other embedded string ever gets baked in.
assert not re.search(rb"[A-Za-z]:\\", CAVE_CODE), "absolute path baked into the cave"

APPLY = "--apply" in sys.argv
UNDO = "--undo" in sys.argv
DIS = "--dis" in sys.argv or "--show" in sys.argv
NOOP = "noop"
if APPLY and UNDO:
    sys.exit("[x] --apply and --undo are mutually exclusive")


def rel32(src, dst):
    return struct.pack("<i", dst - (src + 5))


HOOK_NEW = b"\xE9" + rel32(HOOK, CAVE)          # 5-byte jmp, exactly replacing the 5-byte call


def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    n = struct.unpack_from("<H", data, e + 6)[0]
    op = struct.unpack_from("<H", data, e + 20)[0]
    s = e + 24 + op
    secs = []
    for _ in range(n):
        nm = bytes(data[s:s + 8]).rstrip(b"\0").decode("latin1")
        vs, va, rs, raw = struct.unpack_from("<IIII", data, s + 8)
        secs.append((nm, va, vs, raw, rs))
        s += 40
    return secs


def mkva2off(base):
    def f(secs, va):
        rva = va - base
        for _nm, va0, vs, raw, rs in secs:
            if va0 <= rva < va0 + max(vs, rs):
                return raw + (rva - va0)
        raise ValueError(hex(va))
    return f


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


def show_cave():
    print("[cave ] cave_mdroll @ %08X  (%d B, reservation %d B, PIC anchor +0x%X)"
          % (CAVE, len(CAVE_CODE), CAVE_ZONE_LEN, _ai))
    for ins in cs.disasm(CAVE_CODE, CAVE):
        print("  %08X %-24s%s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))


def process(path, base):
    data = bytearray(open(path, "rb").read())
    secs = load_sections(data)
    va2off = mkva2off(base)

    def rd(va, n):
        o = va2off(secs, va)
        return bytes(data[o:o + n])

    def wr(va, blob):
        o = va2off(secs, va)
        data[o:o + len(blob)] = blob

    # --- pin the build ---------------------------------------------------------
    # ⚠ PRE_BYTES is load-bearing, not decoration: the cave is entered with EAX =
    # target and EDX = the TCombatUnit classref, set up by exactly these two
    # instructions. If anything else ever hooks them, the cave gets garbage.
    for lbl, va, want in (("pre-hook setup", PRE_VA, PRE_BYTES),
                          ("post-hook", POST_VA, POST_BYTES),
                          ("tail", TAIL, TAIL_BYTES),
                          ("IsClass thunk", ISCLASS, bytes.fromhex("ff25bcb68f55")),
                          ("HitRole entry", HITROLE, bytes.fromhex("53"))):
        if rd(va, len(want)) != want:
            print("[x] %s @%08X is %s, expected %s -- wrong build, or another feature "
                  "has moved in" % (lbl, va, rd(va, len(want)).hex(" "), want.hex(" ")))
            return False
    # HitRole must still make exactly ONE unconditional @RandInt call: that is what makes
    # the hoisted draw cost exactly one draw regardless of its (discarded) input.
    body = rd(HITROLE, 0x34)
    ncalls = sum(1 for ins in cs.disasm(body, HITROLE)
                 if ins.mnemonic == "call" and ins.op_str == hex(RANDINT))
    nbranch = sum(1 for ins in cs.disasm(body, HITROLE)
                  if ins.mnemonic.startswith("j") and ins.mnemonic != "jmp")
    if ncalls != 1:
        print("[x] HitRole makes %d @RandInt calls, expected exactly 1 -- the hoist would no "
              "longer be draw-count invariant; refusing" % ncalls)
        return False
    print("[chk ] HitRole @%08X: 1 unconditional @RandInt, %d fwd clamp branches "
          "(none skips the draw)" % (HITROLE, nbranch))
    print("[chk ] pre-hook setup @%08X intact: %s" % (PRE_VA, PRE_BYTES.hex(" ")))

    # --- state -----------------------------------------------------------------
    cur_hook = rd(HOOK, len(ORIG))
    cur_cave = rd(CAVE, CAVE_ZONE_LEN)
    zone_ours = cur_cave[:len(CAVE_CODE)] == CAVE_CODE and \
        all(b == 0 for b in cur_cave[len(CAVE_CODE):])
    zone_free = all(b == 0 for b in cur_cave)
    hook_state = "vanilla" if cur_hook == ORIG else "ours" if cur_hook == HOOK_NEW else "FOREIGN"
    # A non-zero reservation reachable ONLY through our own hook is, by construction, our own
    # previous output: this 4 KB zone is exclusive to this script (no other build script names
    # 0x55842xxx) and nothing branches into it. That is what makes an in-place re-tune safe.
    zone_prev = hook_state == "ours" and not zone_ours and not zone_free

    # The rest of the exclusive zone must stay zero -- that is the headroom CAVE_ZONE_LEN can
    # grow into, so a foreign byte there has to stop us before the cave ever expands.
    if any(rd(CAVE + CAVE_ZONE_LEN, ZONE_END - CAVE - CAVE_ZONE_LEN)):
        print("[x] exclusive zone %08X..%08X is not zero beyond the %d B reservation -- "
              "someone else moved in; refusing" % (CAVE + CAVE_ZONE_LEN, ZONE_END, CAVE_ZONE_LEN))
        return False

    zone_word = ("ours" if zone_ours else "free" if zone_free
                 else "ours(old)" if zone_prev else "FOREIGN")
    print("[stat ] hook  %08X  %-9s %s" % (HOOK, hook_state, cur_hook.hex(" ")))
    print("[stat ] cave  %08X  %-9s (%d B of code in a %d B reservation; %08X..%08X zero)"
          % (CAVE, zone_word, len(CAVE_CODE), CAVE_ZONE_LEN, CAVE + CAVE_ZONE_LEN, ZONE_END))

    if hook_state == "FOREIGN" or zone_word == "FOREIGN":
        print("[x] foreign state -- refusing to touch anything.\n"
              "     expected hook %s (vanilla) or %s (ours)" % (ORIG.hex(" "), HOOK_NEW.hex(" ")))
        return False

    fully_vanilla = hook_state == "vanilla" and zone_free
    fully_applied = hook_state == "ours" and zone_ours

    # --- undo ------------------------------------------------------------------
    if UNDO:
        if fully_vanilla:
            print("[= ] not applied -- nothing to undo")
            return NOOP
        kill_game()
        wr(HOOK, ORIG)
        wr(CAVE, bytes(CAVE_ZONE_LEN))
        print("[u ] %08X hook restored (5 bytes, no orphans): %s" % (HOOK, ORIG.hex(" ")))
        print("[u ] %08X cave_mdroll zeroed (%d B reservation)" % (CAVE, CAVE_ZONE_LEN))
        try:
            open(path, "wb").write(data)
        except PermissionError:
            print("[x] LOCKED -- close AoW binaries (AoW.exe/AoWCompat.exe/AoWDevEd.exe)")
            return False
        return True

    # --- apply -----------------------------------------------------------------
    if fully_applied:
        print("[= ] already applied -- chain intact")
        return True
    if not (fully_vanilla or hook_state == "ours"):
        print("[x] inconsistent half-state -- run --undo first")
        return False
    retune = hook_state == "ours"
    if not APPLY:
        print("[dry] originals verified, cave zone %s, .reloc untouched by design%s"
              % (zone_word, "  -- would REWRITE the cave in place (no backup taken)"
                 if retune else ""))
        return True

    kill_game()
    # ⚠ Back up ONLY from a file positively proved free of this feature. Never gate on
    # "no backup file exists" -- on a re-apply/re-tune that would snapshot our own output.
    bp = os.path.join(BACKUP_DIR, os.path.basename(path) + SUFFIX)
    if fully_vanilla:
        if not os.path.exists(bp):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(path, bp)
            print("[bak] %s  (taken from a proven-unpatched file)" % bp)
        else:
            print("[bak] %s already exists -- kept" % bp)
    else:
        print("[bak] skipped: this file already carries the feature (re-tune), so it is NOT "
              "a valid pre-feature snapshot")

    wr(CAVE, bytes(CAVE_ZONE_LEN))
    wr(CAVE, CAVE_CODE)
    wr(HOOK, HOOK_NEW)
    print("[w ] %08X cave_mdroll (%d B)" % (CAVE, len(CAVE_CODE)))
    print("[w ] %08X hook -> jmp cave: %s" % (HOOK, HOOK_NEW.hex(" ")))
    try:
        open(path, "wb").write(data)
    except PermissionError:
        print("[x] LOCKED -- close AoW binaries (AoW.exe/AoWCompat.exe/AoWDevEd.exe)")
        return False
    return True


print()
show_cave()
print()
if DIS and not (APPLY or UNDO):
    sys.exit(0)
ok = process(os.path.join(GAME, "AoWEPACK.dpl"), DLL_BASE)
if UNDO:
    if ok is True:
        print("\n[done] UNDONE -- the displaced call is restored and the cave zeroed. "
              "No backup touched, no .reloc entry ever moved.")
    elif ok != NOOP:
        print("\n[!] not reverted")
elif APPLY:
    print("\n[done] Applied, UNTESTED. Mind Decay now consumes exactly one combat RNG draw "
          "whether or not the target is eligible.\n"
          "       Revert: re-run with --undo (surgical, touches no backup).\n"
          "       Then:   python \"Modding Resources/re_tools/rng_audit.py\" --owners\n"
          "               python \"Modding Resources/re_tools/ghidra_annots.py\" --apply"
          if ok else "\n[!] not applied")
else:
    print("\n[dry-run] Re-run with --apply to write, or --undo to revert.")
sys.exit(0 if ok else 1)
