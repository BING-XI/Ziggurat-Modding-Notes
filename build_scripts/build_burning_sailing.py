#!/usr/bin/env python
r"""
build_burning_sailing.py -- SAILING units and MACHINES take multiplied Burning damage.

Boats burn, and so do siege engines. `PassiveAb.TBurningAbility.NewCombatTurn @0x557BA3D4` rolls
`HitRole(20 - RES)` once per combat turn and, on a hit, calls `TCombatObject.ExecuteDamage` with a
flat base tick in EDX. This patch multiplies that tick by MULT_SAILING when the burning object has
the Sailing ability, and by MULT_MACHINE when it is a machine. The two MULTIPLY: a Sailing machine
takes MULT_SAILING * MULT_MACHINE.

TRACK: AoWEPACK.dpl ONLY. `TBurningAbility` occurs 7x here and 0x in AoWTCPCK.dpl / AoW.exe /
AoWCompat.exe / AoWDevEd.exe / aowInt.dpl / HSEPack.dpl. There is NO exe lockstep for this
feature -- do not touch AoW.exe or AoWCompat.exe.

--------------------------------------------------------------------------------------------
HOOK -- 0x557BA479..0x557BA482 (10 bytes), resume 0x557BA483
--------------------------------------------------------------------------------------------
    557BA430  mov  eax, esi / mov edx,[eax] / call [edx+0xB8]   ; -> the ability owner
    557BA43A  mov  edx, [0x55710700]    ; the TAbstractUnit class VMT (a .reloc'd global)
  # 557BA440  call 0x557010C0           ; System.@IsClass -> AL              \
  # 557BA445  test al, al / je 0x557BA49A   ; NOT a TAbstractUnit -> leave    > GUARDED, 21 bytes
  # 557BA449  mov  eax, esi / mov edx,[eax] / call [edx+0xB8]  ; owner again  |  (see note 5a --
  # 557BA453  mov  ebx, eax   ; ⭐ EBX = the TAbstractUnit, IsClass-PROVEN    /   walls bail here)
    557BA455  mov  eax, ebx / mov edx,[eax] / call [edx+0xCC]   ; TAbstractUnit.GetResistance
    557BA463  mov  eax, 0x14            ; power 20 (Ziggurat; vanilla 4)   <-- GUARDED, untouched
    557BA46B  call 0x55725D98           ; AoWE.HitRole -- per-combat-turn re-roll
    557BA470  test al, al / je 0x557BA49A
    557BA474  mov  edx, 4               ; base tick   OWNED BY build_damhp_gapfix.py <-- GUARDED
  > 557BA479  mov  eax, esi             ; \
  > 557BA47B  mov  ecx, [eax]           ;  > DISPLACED (10 bytes)
  > 557BA47D  call [ecx+0x124]          ; /  TCombatObject.ExecuteDamage
    557BA483  jmp  0x557BA49A           ; <-- RESUME here (not 0x557BA474, not 0x557BA49A)

⚠ The untouchable span is 0x557BA474..0x557BA478 INCLUSIVE. `build_damhp_gapfix.py:49` verifies
  the \xBA opcode at 0x557BA474 and reads the imm32 at 0x557BA475 against a ladder. Hooking there
  would make that script abort. Our window starts one byte later, at 0x557BA479.

Only two bytes in the whole function differ from pristine -- 0x557BA464 (power 4->20, the 5%
to-hit conversion) and 0x557BA475 (damage 1->4, build_damhp_gapfix.py). Both are asserted
unchanged before and after every write. The 10-byte window itself is byte-identical to pristine.

--------------------------------------------------------------------------------------------
CAVE -- 0x5582E000, 58 bytes
--------------------------------------------------------------------------------------------
⚠⚠ The original spec for this feature named 0x5582D000. That address is TAKEN by
   `build_embrittle.py` (CAVE_ZONE_LEN 0x300, applied). 0x5582E000 is zero in BOTH live and
   pristine, opens a contiguous zero run of ~756 KB, carries no .reloc entry, and no other build
   script references it (`grep -rl 5582E000 build_scripts/` -> this file only).

  Entry: EDX = the base tick, ESI = TCombatObject, EBX = TAbstractUnit.

    push edx                    ; 52                 EDX is caller-saved across the virtual
    mov  edx, 0x17              ; BA 17 00 00 00     Sailing. imm32 -- see the keystone trap
    mov  eax, esi               ; 89 F0              esi = TCombatObject           [class!]
    mov  ecx, [eax]             ; 8B 08
    call [ecx+0xA8]             ; FF 91 A8 00 00 00  TCombatObject.GetAbilityEnabled -> AL
    pop  edx                    ; 5A                 restore BEFORE the test (see note 3)
    test al, al                 ; 84 C0              Delphi Boolean: AL only, never EAX
    je   nosail                 ; 74 03
    imul edx, edx, 2            ; 6B D2 02           x MULT_SAILING  (see note 4)
  nosail:
    push edx                    ; 52
    mov  eax, ebx               ; 89 D8              ebx = TAbstractUnit           [class!]
    mov  ecx, [eax]             ; 8B 08
    call [ecx+0x114]            ; FF 91 14 01 00 00  TAbstractUnit.GetUnitType -> AL  (note 2)
    pop  edx                    ; 5A
    cmp  al, 2                  ; 3C 02              utMachine. AL only -- see note 2
    jne  nomach                 ; 75 03
    imul edx, edx, 2            ; 6B D2 02           x MULT_MACHINE
  nomach:
    mov  eax, esi               ; 89 F0           \
    mov  ecx, [eax]             ; 8B 08            > displaced run, RE-ASSEMBLED not copied
    call [ecx+0x124]            ; FF 91 24 01 00 00/  TCombatObject.ExecuteDamage
    jmp  0x557BA483             ; E9 rel32

Four deliberate choices:

 1. SAILING is asked of `esi` through TCombatObject VMT **+0xA8**, not of `ebx` through
    TAbstractUnit VMT +0x148.
      * TCombatObject +0xA8 = TCombatObject.GetAbilityEnabled @0x557268D4 (`xor eax,eax; ret`);
        TCombatUnit overrides it with the nil-guarded TCombatUnit.GetAbilityEnabled @0x55725004:
            mov ecx,[eax+0x4C] / test ecx,ecx / je -> return 0 / mov eax,ecx / call [ecx+0x148]
        i.e. it forwards to the identical TAbstractUnit.GetAbilityEnabled on [combatobj+0x4C].
        Same query as +0x148, plus a nil guard, plus a graceful 0 for TCombatWall, which would
        otherwise misread its +0x4C -- the "Blt Error" type-alias bug. That nil guard is the
        reason to prefer +0xA8; it is NOT the reason walls are safe. See note 5.

 2. MACHINE is asked of `ebx` through TAbstractUnit VMT **+0x114** = GetUnitType.
    ⚠⚠ +0x114 ALIASES ACROSS CLASSES. On the *combat* VMT, +0x114 is
       `TCombatObject.ExecuteDamageRoleEx @0x55726A6C` -- calling it on `esi` would fire a whole
       damage role with junk arguments. The sequence above is correct only because the call is on
       `ebx`. That is why every slot number in this file states its class.
         TAbstractUnit +0x114 = GetUnitType @0x5577FD88   `xor eax,eax; ret`  (utNormal)
         TUnit         +0x114 = GetUnitType @0x55782808   `mov eax,[eax+0x40]; mov al,[eax+0x30]`
         THero         +0x114 = GetUnitType @0x55786C38   `xor eax,eax; ret`  (heroes never 2)
    ⚠ TUnit's override returns a BYTE in AL and leaves the upper 24 bits of EAX holding the
      `[eax+0x40]` pointer. `cmp al, 2` is mandatory; `cmp eax, 2` would never match.
    `ebx` is safe to use and must NOT be treated as scratch: it is written at 0x557BA453 from a
    value that `System.@IsClass(TAbstractUnit)` had just approved at 0x557BA43A, with a bail to
    0x557BA49A at 0x557BA447. That 12-byte run is GUARDED below -- the guard is what makes "ebx
    is a TAbstractUnit" a checked fact rather than an assumption. EBX/ESI are callee-saved under
    the Delphi register ABI, and both GetAbilityEnabled implementations preserve them.
    This is also the cheap machine test: no second `call [edx+0xB8]`, no vmt[0xB8] hop.

 3. `pop edx` before the flag test in both halves. `pop` does not touch EFLAGS either way; this
    ordering removes the question entirely.

 4. `imul edx, edx, N` (6B D2 0N), not `shl edx, k`. Same 3 bytes, same "scales with whatever
    build_damhp_gapfix.py set the base tick to" property, and the multiplier need not be a power
    of two. Re-tuning either MULT rewrites the cave IN PLACE (no revert, no backup churn);
    --undo remains available.
    ⚠ The tunable range is NOT 1..127 per multiplier. See check_damage_ceiling(): the product
      times the live base tick must be <= 126 or `TCombatObject.ExecuteDamage @0x55726C58`
      raises EAssertionFailed. At the shipped tick of 4 that means product <= 31.

 5. ⚠⚠ WHY WALLS ARE SAFE -- and why the machine leg is NOT wall-safe by construction.
    Do not reason "the +0xA8 nil guard keeps walls out"; that covers only the Sailing leg. The
    machine leg asks `ebx`, and **`AoWE.TWallUnit.GetUnitType @0x557836F4` is `B0 02` --
    `mov al, 2` -- so a wall reports utMachine.** If a wall ever reached this cave, the machine
    multiplier WOULD fire on it. Two independent vanilla facts stop that, and both were checked
    against the live file:
      a. Walls never reach the cave at all. `TCombatObject.GetAbilityOwner @0x557268D0` is
         `xor eax,eax; ret` and TCombatWall inherits it, so the owner fetched at 0x557BA430 is
         nil, `System.@IsClass(nil, TAbstractUnit)` at 0x557BA440 returns false, and
         NewCombatTurn bails at 0x557BA447 -- upstream of the hook. This is the load-bearing
         one, and the 21-byte GUARD at 0x557BA440 asserts that whole chain is still intact.
      b. Even downstream, a wall cannot hold Burning. `TWallUnit.GetImmunityTypes @0x5578363C`
         computes `not 0x0100 and 0x03FF = 0x02FF` -- immune to every damage type except
         dtWall -- so `ExecuteCombatDamageEffects`' `test bl, 1` (dtFire) can never be true
         for one.
    A future third multiplier must re-derive this, not inherit it: the moment a leg queries
    something other than the IsClass-approved `ebx`, (a) stops applying.

Only EDX is live across the cave; EAX/ECX are written before read by the displaced run.

⚠ VERIFY-BEFORE-WRITE IS A LADDER, NOT A TWO-STATE MANIFEST. This cave has had two *shapes*:
  the v1 39-byte single-multiplier cave and the v2 58-byte two-multiplier cave. `zone_state()`
  recognises the installed bytes as v1-with-any-imm8 OR v2-with-any-two-imm8s by wildcarding the
  `6B D2 xx` operand bytes, so a re-shape is a "retune" (rewrite in place, no backup) rather than
  a "foreign" abort. A two-state manifest cannot express a re-shape.

PIC: rel32 out, rel32 back, register-indirect calls, immediates only. No absolute 0x55xxxxxx
operand anywhere -- machine-checked by pic_check() below. No .reloc entry is needed and none
exists in either zone (63,883 entries scanned; re-asserted at apply time).

RNG: the cave adds NO draw and sits below the HitRole call; rng_free() asserts it calls none of
the three generator entry points. NewCombatTurn is in neither the SYNC nor the RAW set and stays
that way.

USAGE
    python build_scripts/build_burning_sailing.py            verify / dry run (writes nothing)
    python build_scripts/build_burning_sailing.py --apply    install, or re-tune/re-shape in place
    python build_scripts/build_burning_sailing.py --undo     surgical: restore 10 bytes, zero cave
    python build_scripts/build_burning_sailing.py --dis      disassemble the assembled cave
"""
import os
import sys
import struct
import shutil
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

TARGET = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-burningsailing")

IMAGE_BASE = 0x55700000
AOW_PROCS = ("AoW", "AoWCompat", "AoWDevEd", "AoWEd")

# ---------------------------------------------------------------- the hook --
HOOK = 0x557BA479
HOOK_LEN = 10
RESUME = 0x557BA483
HOOK_ORIG = bytes.fromhex("8bc68b08ff9124010000")   # mov eax,esi / mov ecx,[eax] / call [ecx+124]

# Bytes we depend on but never write. Asserted unchanged before and after every write, so a
# collision aborts instead of corrupting a neighbour's manifest -- or, for the first entry,
# instead of letting the cave call a virtual on something that is not a TAbstractUnit.
GUARDS = (
    (0x557BA440, bytes.fromhex("e87b6cf4ff" "84c0" "7451" "8bc68b10ff92b8000000" "8bd8"),
     "call System.@IsClass / test al,al / je 0x557BA49A / GetAbilityOwner / mov ebx,eax -- the "
     "whole chain that makes ebx a VERIFIED TAbstractUnit, and the reason a TCombatWall never "
     "reaches the cave (its GetAbilityOwner is nil, so @IsClass fails and the function bails "
     "here). Walls DO report utMachine (note 5), so this guard is load-bearing."),
    (0x557BA463, bytes.fromhex("b814000000"),
     "HitRole power 20 (5% to-hit conversion; vanilla 4)"),
    (0x557BA474, bytes.fromhex("ba04000000"),
     "Burning base tick 4 -- OWNED BY build_damhp_gapfix.py"),
)

# ---------------------------------------------------------------- the cave --
CAVE = 0x5582E000
CAVE_ZONE = 0x80        # exclusive reservation 0x5582E000..0x5582E07F; asserted zero-or-ours
TAIL_ZERO = 16          # bytes past the last written byte that must still be zero

AB_SAILING = 0x17       # Move ability id: Walking 0, Flying 1, ... Sailing 0x17, Floating 0x3B
MACHINE_UNIT_TYPE = 2   # TUnitType.utMachine, as returned in AL by GetUnitType

# ⚠ Every slot number carries its class. +0x114 means two different methods on the two VMTs in
#   play here, and the wrong one is a live damage role rather than a type query.
SLOT_CO_GETABILITYENABLED = 0xA8    # TCombatObject VMT +0xA8   (TAbstractUnit's is +0x148)
SLOT_CO_EXECUTEDAMAGE = 0x124       # TCombatObject VMT +0x124
SLOT_AU_GETUNITTYPE = 0x114         # TAbstractUnit VMT +0x114  ⚠ TCombatObject's +0x114 is
                                    #   ExecuteDamageRoleEx @0x55726A6C -- never call it on esi

# ⚠ THE BINDING LIMIT IS THE PRODUCT TIMES THE BASE TICK, NOT EITHER MULTIPLIER.
#   `TCombatObject.ExecuteDamage @0x55726C58` asserts the value it is handed in EDX:
#       55726C60  test ebx, ebx / jl  0x55726C69      ; negative -> assert
#       55726C64  cmp  ebx, 0x7F / jl 0x55726C7D      ; >= 127   -> assert
#       55726C78  call System.@Assert  "Invalid Damage Value (TCombatUnit.ExecuteDamage)"
#   so the legal range is 0..126 inclusive. With gapfix's base tick of 4 that caps the PRODUCT
#   at 31. Each multiplier alone must also fit the `imul r32,r32,imm8` operand (1..127), but
#   that is the looser of the two -- MULT_SAILING=8 with MULT_MACHINE=8 satisfies both imm8
#   ranges, applies cleanly, passes every mechanical check, and then raises EAssertionFailed on
#   the first burning Galley. check_damage_ceiling() reads the base tick LIVE and rejects that.
MULT_SAILING = 2        # tunable; see check_damage_ceiling() for the real range
MULT_MACHINE = 2        # tunable; MULTIPLIES with the above (a Sailing machine takes x4)

MULT_IMM8_MAX = 127     # `imul r32, r32, imm8` operand range, the looser constraint
MAX_DAMAGE_VALUE = 126  # the largest EDX ExecuteDamage's assert accepts (it tests `< 0x7F`)
BASE_TICK_VA = 0x557BA475   # the imm32 of `mov edx, N` at 0x557BA474 -- OWNED BY gapfix

# The three RNG entry points. A cave that calls one of these is an RNG site and must be declared
# to rng_audit.py; this feature adds no draw, so rng_free() asserts none of them is reachable.
RNG_ENTRIES = {
    0x5577827C: "AoWE.TAoWHSMap.Random (SYNCED)",
    0x55701080: "System.@RandInt thunk (RAW)",
    0x55725D98: "AoWE.HitRole",
}


# ------------------------------------------------------------------ PE bits --
def pe_sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    o, out = e + 24 + opt, []
    for _ in range(nsec):
        name = d[o:o + 8].rstrip(b"\0").decode("latin1")
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, o + 8)
        out.append((name, vaddr, vsize, raw, rsize))
        o += 40
    return out


def va2off(d, va):
    """VA -> file offset, resolved PER SECTION through the PE section table.
    A flat delta is silently wrong outside CODE in this DLL (DATA uses a different one)."""
    rva = va - IMAGE_BASE
    for name, vaddr, vsize, raw, rsize in pe_sections(d):
        if vaddr <= rva < vaddr + max(vsize, rsize):
            if rsize == 0:
                sys.exit("ABORT: 0x%08X is in %s, which has no file bytes" % (va, name))
            return raw + (rva - vaddr)
    sys.exit("ABORT: VA 0x%08X is outside every section of %s" % (va, TARGET))


def assert_in_code(d, *vas):
    for name, vaddr, vsize, raw, rsize in pe_sections(d):
        if name != "CODE":
            continue
        lo, hi = IMAGE_BASE + vaddr, IMAGE_BASE + vaddr + vsize
        for va in vas:
            if not lo <= va < hi:
                sys.exit("ABORT: 0x%08X is outside CODE (0x%08X..0x%08X)" % (va, lo, hi))
        return
    sys.exit("ABORT: no CODE section in %s" % TARGET)


def reloc_vas(d):
    """Every VA carrying a base-relocation entry."""
    e = struct.unpack_from("<I", d, 0x3C)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 96 + 5 * 8)
    if size == 0:
        return set(), 0
    base = va2off(d, IMAGE_BASE + rva)
    p, end, out = base, base + size, set()
    while p < end - 8:
        page, blk = struct.unpack_from("<II", d, p)
        if blk < 8:
            break
        for i in range((blk - 8) // 2):
            w = struct.unpack_from("<H", d, p + 8 + i * 2)[0]
            if w >> 12:
                out.add(IMAGE_BASE + page + (w & 0xFFF))
        p += blk
    return out, len(out)


def check_no_relocs(d, spans):
    """spans: list of (lo, hi_exclusive, label). Abort if any reloc lands inside."""
    vas, total = reloc_vas(d)
    bad = []
    for lo, hi, label in spans:
        hit = sorted(v for v in vas if lo <= v < hi)
        if hit:
            bad.append("%s: %s" % (label, ", ".join("0x%08X" % v for v in hit)))
    if bad:
        sys.exit("ABORT: base relocations inside a zone we write:\n  " + "\n  ".join(bad))
    return total


# ----------------------------------------------------------- mini assembler --
def _ks():
    try:
        from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    except ImportError:
        sys.exit("keystone-engine not installed:  pip install keystone-engine")
    return Ks(KS_ARCH_X86, KS_MODE_32)


def asm_layout(frags, base):
    """frags: [(label|None, text|None)]. Text may use {LABEL} placeholders, which resolve to
    absolute VAs. Iterated to a fixed point so forward references settle."""
    ks = _ks()
    labels = {lab: base for lab, _ in frags if lab}
    for _ in range(8):
        va, out, seen = base, b"", {}
        for lab, text in frags:
            if lab:
                seen[lab] = va
            if text is None:
                continue
            enc, _n = ks.asm(text.format(**{k: hex(v) for k, v in labels.items()}), va)
            if enc is None:
                raise RuntimeError("keystone failed on: %s" % text)
            out += bytes(enc)
            va += len(enc)
        if seen == labels:
            return out
        labels = seen
    raise RuntimeError("cave layout did not converge")


def base_tick(d):
    """The Burning base tick this cave multiplies, read LIVE from the `mov edx, imm32` at
    0x557BA474. That instruction is owned by build_damhp_gapfix.py and its value moves with the
    DAM/HP ladder, so the damage ceiling has to be computed against the file, never a constant."""
    o = va2off(d, BASE_TICK_VA)
    if d[o - 1] != 0xBA:
        sys.exit("ABORT: 0x%08X is not a `mov edx, imm32` (opcode %02X, expected BA) -- the "
                 "base-tick site has moved." % (BASE_TICK_VA - 1, d[o - 1]))
    return struct.unpack_from("<I", d, o)[0]


def check_damage_ceiling(d, sail=None, mach=None, quiet=False):
    """⚠ The multipliers are bounded by the PRODUCT times the live base tick, not individually.

    `TCombatObject.ExecuteDamage @0x55726C58` asserts `0 <= EDX <= 126` and otherwise raises
    EAssertionFailed("Invalid Damage Value (TCombatUnit.ExecuteDamage)"). A pair like 8/8 fits
    both imul imm8 operands and every other check in this script, then kills the game on the
    first burning Galley. Validating each multiplier in isolation does not catch that."""
    sail = MULT_SAILING if sail is None else sail
    mach = MULT_MACHINE if mach is None else mach
    tick = base_tick(d)
    product = sail * mach
    worst = product * tick
    if not quiet:
        print("  damage: base tick %d (live, from 0x%08X) x product %d = %d   ceiling %d  [%s]"
              % (tick, BASE_TICK_VA, product, worst, MAX_DAMAGE_VALUE,
                 "ok" if worst <= MAX_DAMAGE_VALUE else "OVER"))
    if tick < 1:
        sys.exit("ABORT: base tick read as %d -- a Burning tick of 0 would never damage." % tick)
    if worst > MAX_DAMAGE_VALUE:
        sys.exit(
            "ABORT: MULT_SAILING %d x MULT_MACHINE %d = %d, and %d x the live base tick %d = %d, "
            "which exceeds the %d that TCombatObject.ExecuteDamage @0x55726C58 accepts.\n"
            "  A Sailing machine would raise EAssertionFailed(\"Invalid Damage Value "
            "(TCombatUnit.ExecuteDamage)\") the first time it burned.\n"
            "  With the current base tick the product must be <= %d."
            % (sail, mach, product, product, tick, worst, MAX_DAMAGE_VALUE,
               MAX_DAMAGE_VALUE // tick))
    return tick, product, worst


def build_cave(sail=None, mach=None):
    """The v2 58-byte two-multiplier cave. See the module docstring for the annotated listing.

    ⚠ This only enforces the imul imm8 operand range. The BINDING limit is the product against
    the live base tick -- check_damage_ceiling() does that, and callers must run it."""
    sail = MULT_SAILING if sail is None else sail
    mach = MULT_MACHINE if mach is None else mach
    for nm, m in (("MULT_SAILING", sail), ("MULT_MACHINE", mach)):
        if not 1 <= m <= MULT_IMM8_MAX:
            sys.exit("ABORT: %s %d is outside the imul imm8 operand range 1..%d"
                     % (nm, m, MULT_IMM8_MAX))
    blob = asm_layout([
        # ---- Sailing: asked of the TCombatObject in esi, slot +0xA8 -------------------------
        (None, "push edx"),                                    # EDX is caller-saved
        (None, "mov edx, %d" % AB_SAILING),                    # ⚠ must be BA .. , never 6A ..
        (None, "mov eax, esi"),                                # esi = TCombatObject   [class!]
        (None, "mov ecx, dword ptr [eax]"),
        (None, "call dword ptr [ecx+0x%X]" % SLOT_CO_GETABILITYENABLED),
        (None, "pop edx"),                                     # restore BEFORE the test
        (None, "test al, al"),                                 # Delphi Boolean lives in AL only
        (None, "je {NOSAIL}"),
        (None, "imul edx, edx, %d" % sail),
        ("NOSAIL", None),
        # ---- Machine: asked of the TAbstractUnit in ebx, slot +0x114 ------------------------
        (None, "push edx"),
        (None, "mov eax, ebx"),                                # ⚠ ebx = TAbstractUnit [class!]
        (None, "mov ecx, dword ptr [eax]"),
        (None, "call dword ptr [ecx+0x%X]" % SLOT_AU_GETUNITTYPE),
        (None, "pop edx"),
        (None, "cmp al, %d" % MACHINE_UNIT_TYPE),              # ⚠ AL only: EAX carries a pointer
        (None, "jne {NOMACH}"),
        (None, "imul edx, edx, %d" % mach),
        ("NOMACH", None),
        # ---- displaced run, RE-ASSEMBLED not copied ----------------------------------------
        (None, "mov eax, esi"),
        (None, "mov ecx, dword ptr [eax]"),
        (None, "call dword ptr [ecx+0x%X]" % SLOT_CO_EXECUTEDAMAGE),
        (None, "jmp 0x%X" % RESUME),
    ], CAVE)
    if len(blob) + TAIL_ZERO > CAVE_ZONE:
        sys.exit("ABORT: cave %d bytes + %d tail > reservation %d"
                 % (len(blob), TAIL_ZERO, CAVE_ZONE))
    return blob


def build_cave_v1(mult):
    """The v1 39-byte SINGLE-multiplier cave -- the shape this script installed before Sailing
    and Machine were split. Built ONLY so zone_state() can recognise it on disk. It is never
    written; --apply always writes build_cave()."""
    return asm_layout([
        (None, "push edx"),
        (None, "mov edx, %d" % AB_SAILING),
        (None, "mov eax, esi"),
        (None, "mov ecx, dword ptr [eax]"),
        (None, "call dword ptr [ecx+0x%X]" % SLOT_CO_GETABILITYENABLED),
        (None, "pop edx"),
        (None, "test al, al"),
        (None, "jz {PLAIN}"),
        (None, "imul edx, edx, %d" % mult),
        ("PLAIN", None),
        (None, "mov eax, esi"),
        (None, "mov ecx, dword ptr [eax]"),
        (None, "call dword ptr [ecx+0x%X]" % SLOT_CO_EXECUTEDAMAGE),
        (None, "jmp 0x%X" % RESUME),
    ], CAVE)


def imul_imm_positions(blob):
    """Byte indices of the imm8 operand of every `imul r32, r32, imm8` (6B D2 xx) in blob.
    These are the bytes the shape ladder wildcards."""
    out, i = [], 0
    while True:
        j = blob.find(b"\x6B\xD2", i)
        if j < 0:
            return out
        out.append(j + 2)
        i = j + 2


def shape_match(zone, blob, wild):
    """True if `zone` is `blob` (ignoring the byte indices in `wild`) followed by zeros."""
    if len(zone) < len(blob):
        return False
    for i, b in enumerate(blob):
        if i not in wild and zone[i] != b:
            return False
    return set(zone[len(blob):]) <= {0}


def build_hook():
    rel = CAVE - (HOOK + 5)
    p = b"\xE9" + struct.pack("<i", rel) + b"\x90" * (HOOK_LEN - 5)
    assert len(p) == HOOK_LEN
    return p


# ------------------------------------------------------------- disassembly --
def disasm(blob, base):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    return list(md.disasm(blob, base))


def show(blob, base, title):
    print("  ---- %s (%d bytes @ 0x%08X) ----" % (title, len(blob), base))
    for i in disasm(blob, base):
        print("  %08X  %-26s %-8s %s"
              % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str))


def pic_check(blob, base):
    """Machine-check position-independence: no absolute [disp32] memory operand, and no
    immediate that looks like a VA in this module. rel32 branch targets are encoded relative
    and so are fine (capstone PRINTS them absolute -- that is why this inspects operands,
    not the printed text)."""
    from capstone import x86_const as X
    bad = []
    for i in disasm(blob, base):
        for op in i.operands:
            if op.type == X.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                bad.append("%08X %s %s  (absolute [disp32])" % (i.address, i.mnemonic, i.op_str))
            if op.type == X.X86_OP_IMM and 0x55700000 <= op.imm < 0x55A00000 \
                    and i.mnemonic not in ("jmp", "call", "je", "jne", "jz", "jnz"):
                bad.append("%08X %s %s  (VA immediate)" % (i.address, i.mnemonic, i.op_str))
    if bad:
        sys.exit("ABORT: cave is not position-independent:\n  " + "\n  ".join(bad))


def rng_free(blob, base):
    """Trap: a cave that calls a generator through a rel32 is an RNG site and would have to be
    declared in the RNG lockstep audit. This feature adds no draw -- assert that stays true.
    (rng_audit.py --owners catches these too, but only after the bytes are already on disk.)"""
    for i in disasm(blob, base):
        if i.mnemonic in ("call", "jmp") and i.operands and i.operands[0].type == 2:  # IMM
            t = i.operands[0].imm
            if t in RNG_ENTRIES:
                sys.exit("ABORT: cave calls %s at 0x%08X -- this feature must add no RNG draw."
                         % (RNG_ENTRIES[t], i.address))


def trap_checks(blob):
    """The traps this feature is known to be able to fall into, asserted on the ASSEMBLED
    bytes -- never on the source line that produced them."""
    want = b"\xBA" + struct.pack("<I", AB_SAILING)
    if want not in blob:
        sys.exit("ABORT: `mov edx, 0x%X` did not assemble as %s -- keystone imm8 trap "
                 "(6A xx = push imm8, sign-extended)." % (AB_SAILING, want.hex(" ")))
    if b"\x6A" + bytes([AB_SAILING]) in blob:
        sys.exit("ABORT: cave contains 6A %02X (push imm8) -- keystone imm8 trap." % AB_SAILING)

    ins = disasm(blob, CAVE)
    if ins[-1].mnemonic != "jmp":
        sys.exit("ABORT: cave does not end in a jmp")
    tgt = ins[-1].operands[0].imm
    if tgt != RESUME:
        sys.exit("ABORT: cave tail jmp goes to 0x%08X, must be 0x%08X" % (tgt, RESUME))
    if any(i.mnemonic == "test" and i.op_str == "eax, eax" for i in ins):
        sys.exit("ABORT: `test eax, eax` on a Delphi Boolean -- it is returned in AL only.")

    # Both multipliers present, and both as the tunable imm8 form.
    wild = imul_imm_positions(blob)
    if len(wild) != 2:
        sys.exit("ABORT: expected exactly 2 `imul edx, edx, imm8` (6B D2 xx), found %d -- the "
                 "shape ladder in zone_state() keys off them." % len(wild))
    if blob[wild[0]] != MULT_SAILING or blob[wild[1]] != MULT_MACHINE:
        sys.exit("ABORT: assembled multipliers are x%d/x%d, expected x%d/x%d"
                 % (blob[wild[0]], blob[wild[1]], MULT_SAILING, MULT_MACHINE))

    # ⚠ The +0x114 aliasing trap, asserted structurally: GetUnitType must be called on the
    #   TAbstractUnit in EBX. If it were ever reached via ESI it would be
    #   TCombatObject.ExecuteDamageRoleEx instead -- same slot number, different class.
    if b"\x89\xD8\x8B\x08\xFF\x91\x14\x01\x00\x00" not in blob:
        sys.exit("ABORT: `mov eax,ebx / mov ecx,[eax] / call [ecx+0x114]` is not in the cave. "
                 "+0x114 is GetUnitType only on the TAbstractUnit VMT; on TCombatObject it is "
                 "ExecuteDamageRoleEx. The receiver MUST be ebx.")
    if b"\x89\xF0\x8B\x08\xFF\x91\x14\x01\x00\x00" in blob:
        sys.exit("ABORT: cave calls [ecx+0x114] on ESI -- that is "
                 "TCombatObject.ExecuteDamageRoleEx, not GetUnitType.")
    # `cmp al, 2`, never `cmp eax, 2`: TUnit.GetUnitType leaves a pointer in EAX's high bits.
    if b"\x3C\x02" not in blob:
        sys.exit("ABORT: `cmp al, 2` (3C 02) missing -- GetUnitType returns a byte in AL.")
    if any(i.mnemonic == "cmp" and i.op_str.startswith("eax,") for i in ins):
        sys.exit("ABORT: `cmp eax, ..` on GetUnitType -- TUnit's override leaves [self+0x40] in "
                 "the upper 24 bits of EAX. Compare AL.")

    # Trap: the host function reads nothing off esp here, but the pushes must still balance.
    if blob.count(b"\x52") != blob.count(b"\x5A"):
        sys.exit("ABORT: unbalanced push edx / pop edx in the cave")
    rng_free(blob, CAVE)


# ------------------------------------------------------------------- state --
def read_target():
    if not os.path.exists(TARGET):
        sys.exit("ABORT: %s not found" % TARGET)
    return bytearray(open(TARGET, "rb").read())


def guards_ok(d, quiet=False):
    bad = []
    for va, want, label in GUARDS:
        o = va2off(d, va)
        got = bytes(d[o:o + len(want)])
        ok = got == want
        if not quiet:
            print("  guard 0x%08X %-22s %s   %s"
                  % (va, got.hex(" "), "ok " if ok else "BAD", label))
        if not ok:
            bad.append("0x%08X expected %s got %s (%s)"
                       % (va, want.hex(" "), got.hex(" "), label))
    if bad:
        sys.exit("ABORT: a neighbouring script's bytes have moved:\n  " + "\n  ".join(bad))


def zone_state(d, blob):
    """Classify the cave reservation. Returns (kind, note).
      'zero'   -- all zero, nobody home
      'ours'   -- exactly `blob` then zeros
      'retune' -- a cave THIS script built, at different multipliers and/or in the older
                  single-multiplier SHAPE, then zeros
      'foreign'-- anything else. Never written over.

    ⚠ This is a LADDER over shapes, not a two-state manifest. The imm8 operand of each
      `imul edx, edx, N` is wildcarded, so any multiplier matches; both the v2 (two imuls) and
      the v1 (one imul) layouts are recognised. Without the v1 rung, re-shaping this cave would
      classify our own previous output as 'foreign' and abort.
    """
    o = va2off(d, CAVE)
    zone = bytes(d[o:o + CAVE_ZONE])
    if set(zone) <= {0}:
        return "zero", ""
    if zone == blob + b"\x00" * (CAVE_ZONE - len(blob)):
        return "ours", ""

    # rung 1 -- v2 shape (Sailing + Machine), any two multipliers
    w2 = imul_imm_positions(blob)
    if len(w2) == 2 and shape_match(zone, blob, set(w2)):
        return "retune", ("installed x%d Sailing / x%d Machine, target x%d / x%d"
                          % (zone[w2[0]], zone[w2[1]], MULT_SAILING, MULT_MACHINE))

    # rung 2 -- v1 shape (Sailing only), any single multiplier
    v1 = build_cave_v1(MULT_SAILING)
    w1 = imul_imm_positions(v1)
    if len(w1) == 1 and shape_match(zone, v1, set(w1)):
        return "retune", ("installed is the OLD single-multiplier shape (x%d Sailing, no Machine "
                          "test); target is x%d Sailing / x%d Machine -- the cave will be "
                          "re-shaped in place" % (zone[w1[0]], MULT_SAILING, MULT_MACHINE))

    # Point at where the squatter actually STARTS -- one planted 0x40 into the reservation is
    # invisible if you only print the first 16 bytes of the zone.
    n = next(i for i in range(CAVE_ZONE) if zone[i])
    head = "cave head is empty" if set(zone[:len(blob)]) <= {0} \
        else "cave head is NOT one of ours"
    return "foreign", ("%s; first occupied byte at cave+0x%02X (0x%08X) = %s"
                       % (head, n, CAVE + n, zone[n:n + 8].hex(" ")))


def state(d, blob, verbose=True):
    ho = va2off(d, HOOK)
    win = bytes(d[ho:ho + HOOK_LEN])
    hook = build_hook()
    zk, znote = zone_state(d, blob)
    if verbose:
        print("  hook  0x%08X window   %s" % (HOOK, win.hex(" ")))
        print("        expected vanilla %s" % HOOK_ORIG.hex(" "))
        print("        expected hooked  %s" % hook.hex(" "))
        print("  cave  0x%08X..0x%08X  %s%s"
              % (CAVE, CAVE + CAVE_ZONE - 1, zk, ("  -- " + znote) if znote else ""))
    if win == HOOK_ORIG and zk == "zero":
        return "clean"
    if win == hook and zk == "ours":
        return "applied"
    if win == hook and zk == "retune":
        return "retune"
    return "broken"


def kill_aow():
    killed = [n for n in AOW_PROCS
              if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                                capture_output=True, text=True).returncode == 0]
    if killed:
        print("  killed running: " + ", ".join(killed))


def write_target(d):
    kill_aow()
    for attempt in range(3):
        try:
            with open(TARGET, "r+b") as f:
                f.write(bytes(d))
            return
        except PermissionError:
            if attempt == 2:
                raise
            kill_aow()


# ------------------------------------------------------------------ actions --
def cmd_verify(d, blob):
    print("VERIFY  %s" % TARGET)
    guards_ok(d)
    check_damage_ceiling(d)
    st = state(d, blob)
    print("  status: %s" % {
        "clean": "NOT APPLIED (vanilla window, cave empty)",
        "applied": "APPLIED / chain intact (Sailing x%d, Machine x%d, multiplying)"
                   % (MULT_SAILING, MULT_MACHINE),
        "retune": "APPLIED at different multipliers or in the older shape -- --apply will "
                  "rewrite the cave in place",
        "broken": "BROKEN or foreign -- see above; --apply will refuse to write",
    }[st])
    return st


def cmd_apply(d, blob):
    print("APPLY   %s" % TARGET)
    assert_in_code(d, HOOK, HOOK + HOOK_LEN - 1, RESUME, CAVE, CAVE + CAVE_ZONE - 1)
    guards_ok(d)
    # ⚠ Before anything is written: would the multiplied tick trip ExecuteDamage's assert?
    check_damage_ceiling(d)
    st = state(d, blob)

    if st == "applied":
        print("  already applied at Sailing x%d / Machine x%d -- nothing to write."
              % (MULT_SAILING, MULT_MACHINE))
        return 0
    if st == "broken":
        sys.exit("ABORT: the 10-byte window matches neither vanilla nor our own hook, or the "
                 "cave reservation holds foreign bytes. Nothing written.")

    # Acceptance #4 -- re-assert at apply time, on the live file.
    total = check_no_relocs(d, [
        (HOOK, HOOK + HOOK_LEN, "hook window"),
        (CAVE, CAVE + CAVE_ZONE, "cave reservation"),
    ])
    print("  relocs: %d entries scanned, none in the hook window or the cave zone" % total)

    pic_check(blob, CAVE)
    trap_checks(blob)
    print("  cave:   %d bytes, PIC ok, imm32 ok, tail jmp -> 0x%08X" % (len(blob), RESUME))

    co = va2off(d, CAVE)
    # Acceptance #3 -- zero-or-ours across the whole reservation, and a zero tail past our last
    # written byte. (zone_state already proved this; re-assert the tail explicitly.)
    tail = bytes(d[co + len(blob):co + len(blob) + TAIL_ZERO])
    if st == "clean" and set(bytes(d[co:co + CAVE_ZONE])) != {0}:
        sys.exit("ABORT: cave reservation is not all zero")
    print("  tail:   %d bytes past the cave currently %s"
          % (TAIL_ZERO, "zero" if set(tail) <= {0} else "NONZERO"))

    # ⚠ Back up ONLY from a file PROVED not to carry this feature. `st == "clean"` is a positive
    # test against the vanilla window AND an empty cave -- not "a backup file is missing", and
    # not "these bytes look like something this script could have written".
    if st == "clean":
        if os.path.exists(BACKUP):
            print("  backup: %s exists, left alone" % os.path.basename(BACKUP))
        else:
            kill_aow()
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(TARGET, BACKUP)
            print("  backup: %s (taken from a verified un-hooked file)" % os.path.basename(BACKUP))
    else:
        print("  backup: NOT taken -- re-tune over our own install (%s)" % st)

    d[co:co + len(blob)] = blob
    d[co + len(blob):co + CAVE_ZONE] = b"\x00" * (CAVE_ZONE - len(blob))
    ho = va2off(d, HOOK)
    d[ho:ho + HOOK_LEN] = build_hook()
    write_target(d)

    # Acceptance #6 -- read back and re-assert the neighbours.
    d2 = read_target()
    guards_ok(d2, quiet=True)
    if state(d2, blob, verbose=False) != "applied":
        sys.exit("ABORT: post-write verification failed")
    print("  wrote:  hook 0x%08X (%d bytes) + cave 0x%08X (%d bytes)"
          % (HOOK, HOOK_LEN, CAVE, len(blob)))
    print("  status: APPLIED / chain intact (Burning damage: Sailing x%d, Machine x%d, "
          "a Sailing machine x%d)" % (MULT_SAILING, MULT_MACHINE, MULT_SAILING * MULT_MACHINE))
    print("  NOT confirmed working -- needs the user's in-game test.")
    return 0


def cmd_undo(d, blob):
    print("UNDO    %s" % TARGET)
    guards_ok(d)
    # ⚠ Deliberately NO check_damage_ceiling() here. An undo must stay possible even when the
    # multipliers currently in this file are illegal -- otherwise a bad edit would strand the
    # install with no way back out except a backup restore.
    st = state(d, blob)
    if st == "clean":
        print("  not applied -- nothing to undo.")
        return 0
    if st == "broken":
        sys.exit("ABORT: not our hook / foreign cave. Nothing written.")

    ho, co = va2off(d, HOOK), va2off(d, CAVE)
    d[ho:ho + HOOK_LEN] = HOOK_ORIG            # restore the displaced run exactly
    d[co:co + CAVE_ZONE] = b"\x00" * CAVE_ZONE  # zero ONLY our own reservation
    write_target(d)

    d2 = read_target()
    guards_ok(d2, quiet=True)
    if state(d2, blob, verbose=False) != "clean":
        sys.exit("ABORT: post-undo verification failed")
    print("  restored 0x%08X = %s" % (HOOK, HOOK_ORIG.hex(" ")))
    print("  zeroed   0x%08X..0x%08X" % (CAVE, CAVE + CAVE_ZONE - 1))
    print("  no .pre-* file was read or written.")
    return 0


def cmd_dis(d, blob):
    print("DISASSEMBLY -- read this, do not trust the source lines (keystone imm8 trap)")
    show(blob, CAVE, "cave")
    check_damage_ceiling(d)
    pic_check(blob, CAVE)
    trap_checks(blob)
    print("  PIC ok (no absolute [disp32], no VA immediate)")
    print("  imm32 ok: contains %s" % (b"\xBA" + struct.pack("<I", AB_SAILING)).hex(" "))
    print("  tail jmp -> 0x%08X (RESUME)" % RESUME)
    print()
    show(build_hook(), HOOK, "hook, patched")
    show(HOOK_ORIG, HOOK, "hook, vanilla")
    print()
    ho = va2off(d, HOOK)
    show(bytes(d[ho:ho + HOOK_LEN]), HOOK, "hook, currently on disk")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="install, or re-tune/re-shape the cave in place")
    ap.add_argument("--undo", action="store_true",
                    help="surgical: restore the 10 bytes, zero our cave, touch no backup")
    ap.add_argument("--dis", "--show", dest="dis", action="store_true",
                    help="disassemble the assembled cave")
    a = ap.parse_args()
    if a.apply and a.undo:
        sys.exit("ABORT: --apply and --undo are mutually exclusive")

    blob = build_cave()
    d = read_target()
    assert_in_code(d, HOOK, HOOK + HOOK_LEN - 1, RESUME, CAVE, CAVE + CAVE_ZONE - 1)

    if a.dis:
        return cmd_dis(d, blob)
    if a.undo:
        return cmd_undo(d, blob)
    if a.apply:
        return cmd_apply(d, blob)
    cmd_verify(d, blob)
    return 0


if __name__ == "__main__":
    sys.exit(main())
