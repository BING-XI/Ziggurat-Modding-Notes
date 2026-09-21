#!/usr/bin/env python
r"""
build_lightning_ignites.py -- lightning damage can set MACHINES on fire.

Machines are stun-immune. In `AoWE.TAbstractUnit.ExecuteDamageEffectsRole @0x55781BA4` the
lightning branch tests the target's unit type and, if it is a machine, jumps straight out with
nothing applied -- a dead exit. This patch redirects that exit: instead of leaving, a machine
continues into the roll it was always going to take, and if the roll lands it receives **Burning**
where a non-machine would have received Stunned.

NO NEW DICE. The branch's own roll is reused verbatim -- power 10 versus Resistance, +4 if the
target has Lightning Protection, drawn through `build_effectroll.py`'s "stunned" stub. All this
patch changes is which result bit the successful roll deposits.

--------------------------------------------------------------------------------------------
WHY THIS REACHES BURNING -- the chain, confirmed end to end
--------------------------------------------------------------------------------------------
  ExecuteDamageEffectsRole  returns a bitset of effects in AX
     -> TDamageCA.Generate @0x55729C20 : `call [ecx+0x118]` then
        `mov word ptr [ebx+0x13], ax`        (0x55729C6B)                 -- stored on the CA
     -> TDamageCA.Execute  @0x55729D14 : `call [ecx+0x128]`
     -> TAbstractUnit.ExecuteCombatDamageEffects @0x55781ED8 :
            55781F0D  test bl, 1              ; bit 0 -- the FIRE effect
            55781F10  je   0x55781F3F
            55781F12  mov  edx, 0x7F          ; ability 0x7F = Burning
            55781F17  mov  eax,esi / mov ecx,[eax] / call [ecx+0x94]      ; ExpandAbility
            55781F21  test al,al / je 0x55781F3F
            55781F25  mov  edx, 0x5F          ; ability 0x5F = Frozen
            55781F2A  mov  eax,esi / mov ecx,[eax] / call [ecx+0x98]      ; RemoveAbility

  So depositing bit 0x0001 instead of 0x0004 yields Burning. Removing Frozen comes with it and
  is the expected, correct side effect (you cannot be frozen and burning at once).

This covers melee, ranged, combat spells, self-destruct and turn-undead, because they all reach
the effects through TDamageCA. `TFastCombatUnit` carries the identical `+0x118` / `+0x128`
pointers, so **auto-resolve is covered by the same two hooks** -- there is no second patch.

TRACK: AoWEPACK.dpl ONLY. `ExecuteCombatDamageEffects` / `TDamageCA` / `TBurningAbility` occur
0x in AoW.exe, AoWCompat.exe, AoWDevEd.exe, aowInt.dpl and HSEPack.dpl. AoWTCPCK.dpl only
*imports* `TCombatUnit.ExecuteDamageEffectsRole` and inherits the change for free. There is NO
exe lockstep -- do not touch AoW.exe or AoWCompat.exe.

--------------------------------------------------------------------------------------------
THE VANILLA LIGHTNING BRANCH -- live bytes, and what each hook takes
--------------------------------------------------------------------------------------------
    55781C4B  test si, 4                ; si = surviving damage types; bit 2 = dtLightning
    55781C50  je   0x55781CAB           ; not lightning -> next branch
    55781C52  mov  eax,ebx / mov edx,[eax] / call [edx+0x114]   ; TAbstractUnit.GetUnitType -> AL
  > 55781C5C  cmp  al, 2                ; \  utMachine?
  > 55781C5E  je   0x55781CAB           ;  > B1 WINDOW (9 bytes)  <-- THE DEAD EXIT
  > 55781C60  mov  edx, 9               ; /  ability 9 = Lightning Immunity
    55781C65  mov  eax,ebx / mov ecx,[eax] / call [ecx+0x148]   ; GetAbilityEnabled(9)   RESUME
    55781C6F  test al,al / jne 0x55781CAB                       ; lightning-immune -> skip
    55781C73  test byte ptr [esp+2], 4  ; has Lightning Protection?
    55781C78  je   0x55781C83
    55781C7A  mov  edi,[esp+4] / add edi, 4                     ; RES + 4
    55781C81  jmp  0x55781C90
    55781C83  mov  eax,ebx / mov edx,[eax] / call [edx+0xCC]    ; GetResistance
    55781C8D  movsx edi, al
    55781C90  mov  eax, 0xA             ; power 10 (Ziggurat; vanilla 6)   <-- GUARDED, untouched
    55781C95  sub  eax, edi
    55781C97  call 0x5580F79D           ; the "stunned" roll  OWNED BY build_effectroll.py  ⚠
    55781C9C  test al,al / je 0x55781CAB
    55781CA0  mov  ax, word ptr [0x55781E14]                    ; 0x0004 -- the STUN result bit
  > 55781CA6  or   ax, bp               ; \ B2 WINDOW (5 bytes, exact)
  > 55781CA8  mov  ebp, eax             ; /
    55781CAB  test si, 0x10             ; next branch                                    RESUME

⚠ B2 IS HOOKED AT 0x55781CA6, NOT AT 0x55781CA0. `mov ax, [0x55781E14]` carries a **type-3
  .reloc entry at 0x55781CA2**. An `E9 rel32` planted at 0x55781CA0 puts bytes 2..5 of its
  displacement exactly there, and the loader adds the rebase delta into them at load time. That
  is silent at build time and a wild jump at run time. Starting six bytes later leaves the
  relocated instruction intact and needs exactly the 5 bytes `or ax,bp / mov ebp,eax` occupy.

⚠ 0x55781C97..0x55781C9B IS NOT OURS. `build_effectroll.py` owns SIX roll sites in this function
  -- 0x55781C37 / C97 / CE9 / D3B / D8D / DED, each an `E8 rel32` retargeted to a stub at
  0x5580F785 / 79D / 7B5 / 7CD / 7E5 / 7FD. Both of our windows are clear of all six and must
  stay that way. The site is guarded below against a two-rung ladder (vanilla HitRole *or* the
  effectroll stub) so that undoing effectroll does not make this script abort.

Machine-checked: neither window carries a .reloc entry, both are byte-identical to the pristine
DLL, and a full sweep of every executable section for rel8/rel32 branch targets and 4-byte VA
constants finds **nothing** landing anywhere inside either window.

--------------------------------------------------------------------------------------------
CAVES -- one page, 0x5582F000, two entry points
--------------------------------------------------------------------------------------------
0x5582F000 is zero in BOTH live and pristine, opens a contiguous zero run of ~756 KB, carries no
.reloc entry, and is referenced by no other build script
(`grep -rl 5582F build_scripts/` -> this file only).

  B1 -- entry from 0x55781C5C.  EBX = TAbstractUnit (self), AL = GetUnitType, SI = type mask.

    and  si, 0x7FFF          ; 66 81 E6 FF 7F   clear the mark (see "the mark" below)
    cmp  al, 2               ; 3C 02            utMachine?  ⚠ AL, never EAX -- see note 1
    jne  normal              ; 75 ..            not a machine -> exactly vanilla
    mov  edx, 7              ; BA 07 00 00 00   ability 7 = Fire Immunity
    mov  eax, ebx            ; 89 D8            ⚠ ebx = TAbstractUnit  [class!]
    mov  ecx, [eax]          ; 8B 08
    call [ecx+0x148]         ; FF 91 48 01 00 00  TAbstractUnit.GetAbilityEnabled -> AL
    test al, al              ; 84 C0
    jne  skip                ; 75 ..            fire-immune machine -> the vanilla dead exit
    or   si, 0x8000          ; 66 81 CE 00 80   MARK: this roll's success means BURNING
  normal:
    mov  edx, 9              ; BA 09 00 00 00   displaced tail, RE-ASSEMBLED not copied
    jmp  0x55781C65          ; E9 rel32
  skip:
    jmp  0x55781CAB          ; E9 rel32         the original dead exit, byte-for-byte outcome

  B2 -- entry from 0x55781CA6.  AX = the stun result bit just loaded from 0x55781E14.

    test si, 0x8000          ; 66 F7 C6 00 80
    je   keep                ; 74 04
    mov  ax, 1               ; 66 B8 01 00      FIRE_BIT -- ⚠ 16-bit, see note 2
  keep:
    or   ax, bp              ; 66 0B C5      \  displaced run, RE-ASSEMBLED
    mov  ebp, eax            ; 8B E8         /
    jmp  0x55781CAB          ; E9 rel32

THE MARK -- why bit 15 of SI, and why B1 clears it unconditionally
    `esi` is the function-local surviving-type mask: `esi = ~GetDamageTypes(self)` then
    `si &= dx`. It is callee-saved and vanilla itself relies on it surviving every virtual call
    in the function (it is re-tested at 0x55781CAB, CFD, D4F, DAF). Its low bits are a Delphi
    SET over `TDamageType`, whose RTTI enumerates exactly ten values -- dtFire, dtCold,
    dtLightning, dtMagic, dtPoison, dtDeath, dtHoly, dtPhysical, dtWall, dtNone -- so bits 10..15
    are structurally unused and 0x8000 is inert. It costs no BSS, no PIC anchor and no register.
    At 0x55781E01 the function returns `ax` from `bp`; `si` is discarded, so the mark never
    escapes.

    B1 nevertheless CLEARS bit 15 before it does anything else. That is five bytes spent to turn
    "no caller can set bit 15" from an assumption into a property of this patch: whenever B2
    runs, the mark is whatever B1 decided this call, never something inherited from `dx`. B2 is
    reachable only by falling out of the roll that B1 gates, so the two are strictly paired.
    (Deliberate addition to the spec's listing -- it changes no behaviour under the spec's own
    stated premise, it only removes a silent-failure mode.)

Two things that are easy to get wrong:

 1. `cmp al, 2`, never `cmp eax, 2`. `TUnit.GetUnitType @0x55782808` is
    `mov eax,[eax+0x40] / mov al,[eax+0x30] / ret` -- it returns a byte in AL and leaves a
    POINTER in the upper 24 bits of EAX. (`TAbstractUnit`'s and `THero`'s are `xor eax,eax; ret`,
    so a hero is never type 2 and never ignites.)
    ⚠ +0x114 aliases: on the *TCombatObject* VMT it is `ExecuteDamageRoleEx @0x55726A6C`. Here
    the call is vanilla's own, on `ebx`, and we do not re-issue it -- we consume its AL.

 2. `mov ax, 1` (66 B8 01 00), never `mov eax, 1`. Vanilla's `mov ax, [0x55781E14]` is a 16-bit
    load that leaves EAX's high half holding whatever the roll stub returned, and the following
    `mov ebp, eax` propagates it. `mov eax, 1` would zero that half and change EBP's high bits
    relative to vanilla. Only AX is ever read downstream, but matching vanilla exactly costs
    nothing.

BOTH CAVES ARE PUSH-FREE. The host function keeps three live values on the stack -- `[esp]` the
incoming type word, `[esp+2]` the protection flags, `[esp+4]` the cached Resistance -- and reads
them AFTER our hooks (0x55781C73, 0x55781C7A). A push inside either cave would shift them.

FIRE-IMMUNE MACHINES consume no roll: B1 takes `skip` before reaching 0x55781C65, exactly as
vanilla did. LIGHTNING-IMMUNE machines exit at vanilla's own `GetAbilityEnabled(9)` gate.
Lightning Protection still grants its +4 to the Resistance the roll is made against.

PIC: rel32 out, rel32 back, register-indirect calls, immediates only. No absolute 0x55xxxxxx
operand anywhere -- machine-checked by pic_check(). The result bits are read from the live file
at build time and emitted as immediates, never as a copied `mov ax, [abs]` (a cave gets no
.reloc entry, so a copied absolute operand would not be rebased).

RNG: NO NEW DRAW. rng_free() asserts neither cave calls TAoWHSMap.Random, System.@RandInt or
HitRole, and `rng_audit.py --owners` must still report 23 modded sites with no line attributed
to this script.

⚠ VERIFY-BEFORE-WRITE IS A LADDER, NOT A TWO-STATE MANIFEST. `zone_state()` recognises the
  installed bytes as our shape carrying DIFFERENT constants -- MARK, the fire bit, either
  ability id, the machine type -- by assembling a recognition variant and wildcarding exactly
  the byte positions that move (tunable_positions()). Re-tuning therefore rewrites the caves in
  place and takes NO new backup; without that rung, changing any constant would classify this
  script's own previous output as foreign and abort. `is_our_hook()` accepts an E9 by target
  RANGE rather than exact value, so a re-tune that changes a cave's length -- moving B2's entry
  -- is still recognised and both hooks are rewritten in the same pass.

USAGE
    python build_scripts/build_lightning_ignites.py            verify / dry run (writes nothing)
    python build_scripts/build_lightning_ignites.py --apply    install, or re-tune in place
    python build_scripts/build_lightning_ignites.py --undo     surgical: restore both windows,
                                                               zero our cave, touch no backup
    python build_scripts/build_lightning_ignites.py --dis      disassemble the assembled caves
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
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-lightningignites")

IMAGE_BASE = 0x55700000
AOW_PROCS = ("AoW", "AoWCompat", "AoWDevEd", "AoWEd")

# ------------------------------------------------------------------ hooks --
# B1 -- the dead machine exit. 9 bytes: cmp al,2 / je 0x55781CAB / mov edx,9
HOOK1 = 0x55781C5C
HOOK1_LEN = 9
RESUME1 = 0x55781C65
HOOK1_ORIG = bytes.fromhex("3c02744bba09000000")

# B2 -- the lightning result deposit. 5 bytes exactly: or ax,bp / mov ebp,eax
# ⚠ NOT 0x55781CA0: a type-3 .reloc at 0x55781CA2 would land inside an E9's displacement.
HOOK2 = 0x55781CA6
HOOK2_LEN = 5
RESUME2 = 0x55781CAB
HOOK2_ORIG = bytes.fromhex("660bc58be8")

# The vanilla dead exit both halves fall out to.
DEAD_EXIT = 0x55781CAB

# ------------------------------------------------- constants read from the file --
# Result bits live in the module's literal pool. They are READ and ASSERTED here, then emitted
# as immediates -- never copied as an absolute memory operand (see the docstring).
VA_FIRE_BIT = 0x55781E10        # expect 0x0001
VA_LIGHTNING_BIT = 0x55781E14   # expect 0x0004
EXPECT_FIRE_BIT = 0x0001
EXPECT_LIGHTNING_BIT = 0x0004

# Power of the lightning-effect roll. READ AND ASSERTED ONLY -- this byte run is shared with the
# stun outcome for every non-machine unit in the game. This script must never write it.
VA_POWER_LIGHTNING = 0x55781C90
POWER_LIGHTNING_BYTES = bytes.fromhex("b80a000000")   # mov eax, 10  (Ziggurat; vanilla 6)
EXPECT_POWER_LIGHTNING = 10

ABIL_FIRE_IMMUNITY = 7          # ability 7 -- vanilla's own gate on the fire branch @0x55781C00
ABIL_LIGHTNING_IMMUNITY = 9     # ability 9 -- vanilla's gate, re-emitted as B1's displaced tail
MACHINE_UNIT_TYPE = 2           # TUnitType.utMachine, returned in AL by GetUnitType
MARK = 0x8000                   # si bit 15 -- structurally unused by TDamageType (10 values)

SLOT_AU_GETABILITYENABLED = 0x148   # TAbstractUnit VMT +0x148  (TCombatObject's is +0xA8)

# ------------------------------------------------------------------- caves --
CAVE = 0x5582F000
CAVE_ZONE = 0x100       # exclusive reservation 0x5582F000..0x5582F0FF; asserted zero-or-ours
TAIL_ZERO = 16          # bytes past the last written byte that must still be zero

# The three RNG entry points. This feature adds no draw; rng_free() asserts none is reachable.
RNG_ENTRIES = {
    0x5577827C: "AoWE.TAoWHSMap.Random (SYNCED)",
    0x55701080: "System.@RandInt thunk (RAW)",
    0x55725D98: "AoWE.HitRole",
}

# Bytes we depend on but never write.
#   A plain GUARD is an exact byte run.
#   A LADDER guard accepts any one of several runs -- used where a NEIGHBOURING script legally
#   owns the bytes, so that undoing that script does not make this one abort.
GUARDS = (
    (0x55781C52, bytes.fromhex("8bc38b10ff9214010000"),
     "mov eax,ebx / mov edx,[eax] / call [edx+0x114] -- TAbstractUnit.GetUnitType, the AL that "
     "B1 consumes. (+0x114 on TCombatObject is ExecuteDamageRoleEx, hence the class note.)"),
    (VA_POWER_LIGHTNING, POWER_LIGHTNING_BYTES,
     "lightning-effect roll power 10 -- SHARED with the stun outcome; read-only, never written"),
    (0x55781CA0, bytes.fromhex("66a1141e7855"),
     "mov ax,[0x55781E14] -- carries the type-3 .reloc at 0x55781CA2 that forces HOOK2 to "
     "0x55781CA6 instead of 0x55781CA0"),
    (VA_FIRE_BIT, struct.pack("<H", EXPECT_FIRE_BIT), "dtFire result bit = 0x0001"),
    (VA_LIGHTNING_BIT, struct.pack("<H", EXPECT_LIGHTNING_BIT),
     "dtLightning/stun result bit = 0x0004"),
)

LADDER_GUARDS = (
    (0x55781C97, 5,
     (bytes.fromhex("e8fc40faff"),      # vanilla:    call 0x55725D98  (HitRole)
      bytes.fromhex("e801db0800")),     # effectroll: call 0x5580F79D  (the "stunned" stub)
     "the lightning roll site -- OWNED BY build_effectroll.py. Never displaced by this script."),
)


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
    """spans: list of (lo, hi_exclusive, label). Abort if any reloc lands inside.
    ⚠ This is the check that keeps HOOK2 off 0x55781CA0 -- run it, do not reason about it."""
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
            return out, labels
        labels = seen
    raise RuntimeError("cave layout did not converge")


def read_word(d, va):
    return struct.unpack_from("<H", d, va2off(d, va))[0]


#: The tunable constants of these caves, in one place. `build_caves` takes an override dict so
#: that shape recognition can assemble VARIANTS and learn which byte positions carry a value --
#: see tunable_positions(). Every variant value must keep the same instruction widths.
def default_tune(d):
    fire = read_word(d, VA_FIRE_BIT)
    lightning = read_word(d, VA_LIGHTNING_BIT)
    if fire != EXPECT_FIRE_BIT:
        sys.exit("ABORT: dtFire result bit at 0x%08X is 0x%04X, expected 0x%04X"
                 % (VA_FIRE_BIT, fire, EXPECT_FIRE_BIT))
    if lightning != EXPECT_LIGHTNING_BIT:
        sys.exit("ABORT: dtLightning result bit at 0x%08X is 0x%04X, expected 0x%04X"
                 % (VA_LIGHTNING_BIT, lightning, EXPECT_LIGHTNING_BIT))
    return dict(mark=MARK, fire=fire,
                abil_fire=ABIL_FIRE_IMMUNITY, abil_lightning=ABIL_LIGHTNING_IMMUNITY,
                machine=MACHINE_UNIT_TYPE)


def build_caves(d, tune=None):
    """Assemble both caves into one contiguous blob at CAVE.
    Returns (blob, {'B1': va, 'B2': va}). Result bits come from the live file.

    `tune` overrides the constants; it is used only to assemble recognition variants, and skips
    the live-file assertions that the shipped build must satisfy."""
    t = default_tune(d) if tune is None else tune
    mark, fire = t["mark"], t["fire"]

    blob, labels = asm_layout([
        # ================= B1 -- entry from 0x55781C5C ==================================
        ("B1", None),
        # Clear the mark unconditionally, so that whenever B2 runs the bit is B1's own decision
        # and never something the caller happened to leave in dx. See "THE MARK" above.
        (None, "and si, 0x%X" % (0xFFFF & ~mark)),
        (None, "cmp al, %d" % t["machine"]),           # ⚠ AL: TUnit's override returns a byte
        (None, "jne {NORMAL}"),                        # not a machine -> exactly vanilla
        (None, "mov edx, %d" % t["abil_fire"]),        # ⚠ must be BA .., never 6A ..
        (None, "mov eax, ebx"),                        # ⚠ ebx = TAbstractUnit (self)  [class!]
        (None, "mov ecx, dword ptr [eax]"),
        (None, "call dword ptr [ecx+0x%X]" % SLOT_AU_GETABILITYENABLED),
        (None, "test al, al"),                         # Delphi Boolean lives in AL only
        (None, "jne {SKIP}"),                          # fire-immune machine -> vanilla dead exit
        (None, "or si, 0x%X" % mark),                  # ⚠ must be 66 81 CE 00 80, not 66 83 CE 80
        ("NORMAL", None),
        (None, "mov edx, %d" % t["abil_lightning"]),   # displaced tail, RE-ASSEMBLED
        (None, "jmp 0x%X" % RESUME1),
        ("SKIP", None),
        (None, "jmp 0x%X" % DEAD_EXIT),

        # ================= B2 -- entry from 0x55781CA6 ==================================
        ("B2", None),
        (None, "test si, 0x%X" % mark),
        (None, "je {KEEP}"),
        (None, "mov ax, %d" % fire),                   # ⚠ 16-bit: 66 B8 .., not B8 .. (see note 2)
        ("KEEP", None),
        (None, "or ax, bp"),                           # \ displaced run, RE-ASSEMBLED
        (None, "mov ebp, eax"),                        # /
        (None, "jmp 0x%X" % RESUME2),
    ], CAVE)

    if len(blob) + TAIL_ZERO > CAVE_ZONE:
        sys.exit("ABORT: caves %d bytes + %d tail > reservation %d"
                 % (len(blob), TAIL_ZERO, CAVE_ZONE))
    return blob, labels


# Recognition variant. Every value differs from any plausible shipped value in its LOW byte and,
# where the byte is not structurally constant, in its high byte too -- and every one keeps the
# same instruction width, so branch displacements do not move. These are never written.
VARIANT_TUNE = dict(mark=0x2010, fire=0x0202, abil_fire=0x11, abil_lightning=0x12, machine=3)


def tunable_positions(d):
    """Byte indices inside the cave blob that carry a tunable constant.

    DERIVED, not hand-listed: assemble the caves twice with different constants and take the
    positions that differ. If a later edit adds a tunable, it is picked up with no maintenance,
    and no opcode byte can be wildcarded by accident. Bytes that are the same in both variants
    stay PINNED -- e.g. the three high bytes of `mov edx, imm32` are 00 for every legal ability
    id, so the ladder keeps checking them."""
    a, la = build_caves(d)
    b, lb = build_caves(d, tune=VARIANT_TUNE)
    if len(a) != len(b) or la != lb:
        sys.exit("ABORT: the recognition variant changed the cave layout (%d vs %d bytes). "
                 "VARIANT_TUNE must keep every instruction width identical." % (len(a), len(b)))
    wild = {i for i in range(len(a)) if a[i] != b[i]}
    if not wild:
        sys.exit("ABORT: the recognition variant produced identical bytes -- VARIANT_TUNE is "
                 "not actually varying anything, so the ladder would not recognise a re-tune.")
    return wild


def shape_match(zone, blob, wild):
    """True if `zone` is `blob` (ignoring the byte indices in `wild`) followed by zeros."""
    if len(zone) < len(blob):
        return False
    for i, b in enumerate(blob):
        if i not in wild and zone[i] != b:
            return False
    return set(zone[len(blob):]) <= {0}


def installed_tune(zone, blob, wild):
    """Human-readable summary of how the installed cave differs from the target."""
    diffs = ["cave+0x%02X: %02X -> %02X" % (i, zone[i], blob[i])
             for i in sorted(wild) if zone[i] != blob[i]]
    return ", ".join(diffs) if diffs else "no operand differs"


def is_our_hook(win, hook_len):
    """True if `win` is an E9 into our own cave reservation, padded with NOPs.

    Deliberately does NOT require the exact target: a re-tune that changes a cave's LENGTH moves
    B2's entry, so the installed hook would point at the old offset. Accepting any target inside
    the reservation lets --apply rewrite both the caves and the hooks in one pass, instead of
    classifying our own install as foreign and aborting."""
    if len(win) != hook_len or win[0] != 0xE9:
        return False
    if win[5:] != b"\x90" * (hook_len - 5):
        return False
    return True


def hook_target(win, hook_va):
    return hook_va + 5 + struct.unpack_from("<i", win, 1)[0]


def build_hook(hook_va, hook_len, cave_va):
    rel = cave_va - (hook_va + 5)
    p = b"\xE9" + struct.pack("<i", rel) + b"\x90" * (hook_len - 5)
    assert len(p) == hook_len
    return p


def build_hooks(labels):
    return (build_hook(HOOK1, HOOK1_LEN, labels["B1"]),
            build_hook(HOOK2, HOOK2_LEN, labels["B2"]))


# ------------------------------------------------------------- disassembly --
def disasm(blob, base):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    return list(md.disasm(blob, base))


def show(blob, base, title):
    print("  ---- %s (%d bytes @ 0x%08X) ----" % (title, len(blob), base))
    for i in disasm(blob, base):
        print("  %08X  %-24s %-8s %s"
              % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str))


def pic_check(blob, base):
    """Machine-check position-independence: no absolute [disp32] memory operand, and no
    immediate that looks like a VA in this module. rel32 branch targets are encoded relative and
    so are fine (capstone PRINTS them absolute -- that is why this inspects operands, not text).
    ⚠ This is what catches a copied `mov ax, [0x55781E10]`: a cave gets no .reloc entry, so an
    absolute operand would read from an unrelocated address once the package rebases."""
    from capstone import x86_const as X
    bad = []
    for i in disasm(blob, base):
        for op in i.operands:
            if op.type == X.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                bad.append("%08X %s %s  (absolute [disp32])" % (i.address, i.mnemonic, i.op_str))
            if op.type == X.X86_OP_IMM and 0x55700000 <= op.imm < 0x55A00000 \
                    and not i.mnemonic.startswith(("jmp", "call", "j")):
                bad.append("%08X %s %s  (VA immediate)" % (i.address, i.mnemonic, i.op_str))
    if bad:
        sys.exit("ABORT: cave is not position-independent:\n  " + "\n  ".join(bad))


def rng_free(blob, base):
    """Trap: a cave reaching a generator through a rel32 would be an RNG site and would have to
    be declared in the lockstep audit. This feature reuses the branch's existing roll and adds
    none -- assert that stays true. rng_audit.py --owners confirms it after the write."""
    for i in disasm(blob, base):
        if i.mnemonic in ("call", "jmp") and i.operands and i.operands[0].type == 2:  # IMM
            t = i.operands[0].imm
            if t in RNG_ENTRIES:
                sys.exit("ABORT: cave calls %s at 0x%08X -- this feature must add NO new draw."
                         % (RNG_ENTRIES[t], i.address))


def trap_checks(blob, labels):
    """The traps this feature is known to be able to fall into, asserted on the ASSEMBLED bytes
    -- never on the source line that produced them."""
    # -- keystone sign-extension: the 16-bit immediates must be the imm16 encodings ----------
    exact = (
        (b"\x66\x81\xE6\xFF\x7F", "and si, 0x7FFF"),
        (b"\x66\x81\xCE\x00\x80", "or si, 0x8000"),
        (b"\x66\xF7\xC6\x00\x80", "test si, 0x8000"),
        (b"\x66\xB8" + struct.pack("<H", EXPECT_FIRE_BIT), "mov ax, 1"),
    )
    for want, what in exact:
        if want not in blob:
            sys.exit("ABORT: `%s` did not assemble as %s -- keystone sign-extension trap "
                     "(66 83 CE 80 would be `or si, -128` = 0xFF80)." % (what, want.hex(" ")))
    # The imm8 sign-extended forms of the same operations, explicitly rejected.
    for bad, what in ((b"\x66\x83\xCE\x80", "or si, imm8"),
                      (b"\x66\x83\xE6", "and si, imm8"),
                      (b"\xB8\x01\x00\x00\x00", "mov eax, 1 (32-bit -- would zero EAX's high "
                                                "half, unlike vanilla's 16-bit load)")):
        if bad in blob:
            sys.exit("ABORT: cave contains %s (%s)." % (bad.hex(" "), what))
    # `mov edx, imm` must be BA .. , never the push imm8 form.
    for aid in (ABIL_FIRE_IMMUNITY, ABIL_LIGHTNING_IMMUNITY):
        if b"\xBA" + struct.pack("<I", aid) not in blob:
            sys.exit("ABORT: `mov edx, %d` did not assemble as BA %02X 00 00 00 -- keystone "
                     "imm8 trap (6A xx = push imm8)." % (aid, aid))
        if b"\x6A" + bytes([aid]) in blob:
            sys.exit("ABORT: cave contains 6A %02X (push imm8) -- keystone imm8 trap." % aid)

    ins = disasm(blob, CAVE)

    # -- push-free: the host reads [esp], [esp+2], [esp+4] AFTER both hooks ------------------
    for i in ins:
        if i.mnemonic in ("push", "pop", "pusha", "popa", "pushf", "popf"):
            sys.exit("ABORT: %s at 0x%08X -- both caves must be PUSH-FREE. The host function "
                     "reads [esp], [esp+2] and [esp+4] downstream of these hooks."
                     % (i.mnemonic, i.address))

    # -- ebx is the receiver of GetAbilityEnabled, and esi is never used as one --------------
    if b"\x89\xD8\x8B\x08\xFF\x91\x48\x01\x00\x00" not in blob:
        sys.exit("ABORT: `mov eax,ebx / mov ecx,[eax] / call [ecx+0x148]` is not in the cave. "
                 "+0x148 is GetAbilityEnabled on the TAbstractUnit VMT; the receiver must be "
                 "ebx (self), which is what the host function holds.")
    if b"\xFF\x91\x14\x01\x00\x00" in blob or b"\xFF\x92\x14\x01\x00\x00" in blob:
        sys.exit("ABORT: cave calls slot +0x114. This feature consumes vanilla's GetUnitType "
                 "result in AL and must not re-issue it -- and on the TCombatObject VMT +0x114 "
                 "is ExecuteDamageRoleEx.")

    # -- `cmp al, 2`, never `cmp eax, 2` ------------------------------------------------------
    if b"\x3C\x02" not in blob:
        sys.exit("ABORT: `cmp al, 2` (3C 02) missing -- GetUnitType returns a byte in AL.")
    if any(i.mnemonic == "cmp" and i.op_str.startswith("eax,") for i in ins):
        sys.exit("ABORT: `cmp eax, ..` on GetUnitType -- TUnit's override leaves [self+0x40] in "
                 "the upper 24 bits of EAX. Compare AL.")
    if any(i.mnemonic == "test" and i.op_str == "eax, eax" for i in ins):
        sys.exit("ABORT: `test eax, eax` on a Delphi Boolean -- it is returned in AL only.")

    # -- every terminal branch goes exactly where it is supposed to --------------------------
    want_targets = {RESUME1, RESUME2, DEAD_EXIT}
    for i in ins:
        if i.mnemonic == "jmp" and i.operands and i.operands[0].type == 2:
            t = i.operands[0].imm
            if not (CAVE <= t < CAVE + CAVE_ZONE) and t not in want_targets:
                sys.exit("ABORT: cave jmp at 0x%08X goes to 0x%08X -- not a resume "
                         "(0x%08X / 0x%08X) and not the dead exit 0x%08X."
                         % (i.address, t, RESUME1, RESUME2, DEAD_EXIT))
    tails = [i for i in ins if i.mnemonic == "jmp" and i.operands
             and i.operands[0].type == 2 and i.operands[0].imm in want_targets]
    if len(tails) != 3:
        sys.exit("ABORT: expected exactly 3 exits (B1 normal -> 0x%08X, B1 skip -> 0x%08X, "
                 "B2 -> 0x%08X), found %d" % (RESUME1, DEAD_EXIT, RESUME2, len(tails)))

    # -- the two entry points are where the hooks think they are -----------------------------
    if labels["B1"] != CAVE:
        sys.exit("ABORT: B1 entry is 0x%08X, expected the cave base 0x%08X"
                 % (labels["B1"], CAVE))
    if not CAVE < labels["B2"] < CAVE + CAVE_ZONE:
        sys.exit("ABORT: B2 entry 0x%08X is outside the reservation" % labels["B2"])

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
            print("  guard  0x%08X %-26s %s  %s"
                  % (va, got.hex(" "), "ok " if ok else "BAD", label.split(" -- ")[0]))
        if not ok:
            bad.append("0x%08X expected %s got %s (%s)"
                       % (va, want.hex(" "), got.hex(" "), label))
    for va, n, options, label in LADDER_GUARDS:
        o = va2off(d, va)
        got = bytes(d[o:o + n])
        ok = got in options
        if not quiet:
            print("  ladder 0x%08X %-26s %s  %s"
                  % (va, got.hex(" "), "ok " if ok else "BAD", label.split(" -- ")[0]))
        if not ok:
            bad.append("0x%08X = %s matches none of the accepted forms %s (%s)"
                       % (va, got.hex(" "), [b.hex(" ") for b in options], label))
    if bad:
        sys.exit("ABORT: bytes this patch depends on have moved:\n  " + "\n  ".join(bad))


def zone_state(d, blob):
    """Classify the cave reservation. Returns (kind, note).
      'zero'    -- all zero, nobody home
      'ours'    -- exactly `blob` then zeros
      'retune'  -- OUR shape carrying different tunable constants, then zeros
      'foreign' -- anything else. Never written over.

    ⚠ This is a LADDER, not a two-state manifest. Without the 'retune' rung, changing MARK, the
      fire bit, either ability id or the machine type would make the installed cave -- this
      script's own previous output -- classify as 'foreign', and --apply would abort with no way
      forward but a revert. Part A carries the same ladder for the same reason.
    """
    o = va2off(d, CAVE)
    zone = bytes(d[o:o + CAVE_ZONE])
    if set(zone) <= {0}:
        return "zero", ""
    if zone == blob + b"\x00" * (CAVE_ZONE - len(blob)):
        return "ours", ""
    wild = tunable_positions(d)
    if shape_match(zone, blob, wild):
        return "retune", ("our shape with different constants -- " +
                          installed_tune(zone, blob, wild))
    # Point at where the squatter actually STARTS -- one planted 0x80 into the reservation is
    # invisible if you only print the first 16 bytes of the zone.
    n = next(i for i in range(CAVE_ZONE) if zone[i])
    head = "cave head is empty" if set(zone[:len(blob)]) <= {0} \
        else "cave head is NOT one of ours"
    return "foreign", ("%s; first occupied byte at cave+0x%02X (0x%08X) = %s"
                       % (head, n, CAVE + n, zone[n:n + 8].hex(" ")))


def state(d, blob, labels, verbose=True):
    h1, h2 = build_hooks(labels)
    o1, o2 = va2off(d, HOOK1), va2off(d, HOOK2)
    w1 = bytes(d[o1:o1 + HOOK1_LEN])
    w2 = bytes(d[o2:o2 + HOOK2_LEN])
    zk, znote = zone_state(d, blob)
    if verbose:
        print("  hook B1 0x%08X window   %s" % (HOOK1, w1.hex(" ")))
        print("          expected vanilla %s" % HOOK1_ORIG.hex(" "))
        print("          expected hooked  %s" % h1.hex(" "))
        print("  hook B2 0x%08X window   %s" % (HOOK2, w2.hex(" ")))
        print("          expected vanilla %s" % HOOK2_ORIG.hex(" "))
        print("          expected hooked  %s" % h2.hex(" "))
        print("  cave    0x%08X..0x%08X  %s%s"
              % (CAVE, CAVE + CAVE_ZONE - 1, zk, ("  -- " + znote) if znote else ""))
    if w1 == HOOK1_ORIG and w2 == HOOK2_ORIG and zk == "zero":
        return "clean"
    if w1 == h1 and w2 == h2 and zk == "ours":
        return "applied"
    # A re-tune: our caves, our hooks, different constants. The hooks are accepted by target
    # RANGE rather than exact value so that a length-changing re-shape is still recognised.
    if zk == "retune" and is_our_hook(w1, HOOK1_LEN) and is_our_hook(w2, HOOK2_LEN) \
            and CAVE <= hook_target(w1, HOOK1) < CAVE + CAVE_ZONE \
            and CAVE <= hook_target(w2, HOOK2) < CAVE + CAVE_ZONE:
        return "retune"
    # Both halves must move together: a half-installed chain is broken, never "applied".
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
def cmd_verify(d, blob, labels):
    print("VERIFY  %s" % TARGET)
    guards_ok(d)
    st = state(d, blob, labels)
    print("  status: %s" % {
        "clean": "NOT APPLIED (both windows vanilla, cave empty)",
        "applied": "APPLIED / chain intact (lightning ignites machines)",
        "retune": "APPLIED with different constants -- --apply will rewrite the caves in place",
        "broken": "BROKEN, half-installed or foreign -- see above; --apply will refuse to write",
    }[st])
    return st


def cmd_apply(d, blob, labels):
    print("APPLY   %s" % TARGET)
    assert_in_code(d, HOOK1, HOOK1 + HOOK1_LEN - 1, RESUME1,
                   HOOK2, HOOK2 + HOOK2_LEN - 1, RESUME2, DEAD_EXIT,
                   CAVE, CAVE + CAVE_ZONE - 1)
    guards_ok(d)
    st = state(d, blob, labels)

    if st == "applied":
        print("  already applied -- nothing to write.")
        return 0
    if st == "broken":
        sys.exit("ABORT: a window matches neither vanilla nor our own hook, the two halves "
                 "disagree, or the cave reservation holds foreign bytes. Nothing written.")

    total = check_no_relocs(d, [
        (HOOK1, HOOK1 + HOOK1_LEN, "B1 window"),
        (HOOK2, HOOK2 + HOOK2_LEN, "B2 window"),
        (CAVE, CAVE + CAVE_ZONE, "cave reservation"),
    ])
    print("  relocs: %d entries scanned, none in either hook window or the cave zone" % total)

    pic_check(blob, CAVE)
    trap_checks(blob, labels)
    print("  caves:  %d bytes (B1 @0x%08X, B2 @0x%08X), PIC ok, no new RNG draw"
          % (len(blob), labels["B1"], labels["B2"]))

    co = va2off(d, CAVE)
    if st == "clean" and set(bytes(d[co:co + CAVE_ZONE])) != {0}:
        sys.exit("ABORT: cave reservation is not all zero")
    tail = bytes(d[co + len(blob):co + len(blob) + TAIL_ZERO])
    print("  tail:   %d bytes past the caves currently %s"
          % (TAIL_ZERO, "zero" if set(tail) <= {0} else "NONZERO"))

    # ⚠ Back up ONLY from a file PROVED not to carry this feature. `st == "clean"` is a positive
    # test against BOTH vanilla windows AND an empty cave -- not "a backup file is missing", and
    # not "these bytes look like something this script could have written".
    # ⚠ A RE-TUNE MUST NOT MINT A BACKUP: by definition the file already carries this feature,
    # so a `.pre-lightningignites` written here would be a patched state wearing a pristine name.
    if st == "clean":
        if os.path.exists(BACKUP):
            print("  backup: %s exists, left alone" % os.path.basename(BACKUP))
        else:
            kill_aow()
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(TARGET, BACKUP)
            print("  backup: %s (taken from a file verified un-hooked on BOTH halves)"
                  % os.path.basename(BACKUP))
    else:
        print("  backup: NOT taken -- re-tune over our own install (%s)" % st)

    h1, h2 = build_hooks(labels)
    d[co:co + len(blob)] = blob
    d[co + len(blob):co + CAVE_ZONE] = b"\x00" * (CAVE_ZONE - len(blob))
    o1, o2 = va2off(d, HOOK1), va2off(d, HOOK2)
    d[o1:o1 + HOOK1_LEN] = h1
    d[o2:o2 + HOOK2_LEN] = h2
    write_target(d)

    d2 = read_target()
    guards_ok(d2, quiet=True)
    if state(d2, blob, labels, verbose=False) != "applied":
        sys.exit("ABORT: post-write verification failed")
    print("  wrote:  B1 0x%08X (%d) + B2 0x%08X (%d) + caves 0x%08X (%d)"
          % (HOOK1, HOOK1_LEN, HOOK2, HOOK2_LEN, CAVE, len(blob)))
    print("  status: APPLIED / chain intact (lightning ignites machines; no new RNG draw)")
    print("  NOT confirmed working -- needs the user's in-game test.")
    return 0


def cmd_undo(d, blob, labels):
    print("UNDO    %s" % TARGET)
    guards_ok(d)
    st = state(d, blob, labels)
    if st == "clean":
        print("  not applied -- nothing to undo.")
        return 0
    if st == "broken":
        sys.exit("ABORT: not our hooks / foreign cave. Nothing written.")

    o1, o2, co = va2off(d, HOOK1), va2off(d, HOOK2), va2off(d, CAVE)
    d[o1:o1 + HOOK1_LEN] = HOOK1_ORIG           # restore both displaced runs exactly
    d[o2:o2 + HOOK2_LEN] = HOOK2_ORIG
    d[co:co + CAVE_ZONE] = b"\x00" * CAVE_ZONE   # zero ONLY our own reservation
    write_target(d)

    d2 = read_target()
    guards_ok(d2, quiet=True)
    if state(d2, blob, labels, verbose=False) != "clean":
        sys.exit("ABORT: post-undo verification failed")
    print("  restored 0x%08X = %s" % (HOOK1, HOOK1_ORIG.hex(" ")))
    print("  restored 0x%08X = %s" % (HOOK2, HOOK2_ORIG.hex(" ")))
    print("  zeroed   0x%08X..0x%08X" % (CAVE, CAVE + CAVE_ZONE - 1))
    print("  no .pre-* file was read or written.")
    return 0


def cmd_dis(d, blob, labels):
    print("DISASSEMBLY -- read this, do not trust the source lines (keystone imm8 trap)")
    b2 = labels["B2"] - CAVE
    show(blob[:b2], labels["B1"], "cave B1  (machine -> mark for burning)")
    print()
    show(blob[b2:], labels["B2"], "cave B2  (marked -> deposit the FIRE bit)")
    pic_check(blob, CAVE)
    trap_checks(blob, labels)
    print("  PIC ok (no absolute [disp32], no VA immediate)")
    print("  no new RNG draw (no call to Random / RandInt / HitRole)")
    print("  push-free: the host reads [esp], [esp+2], [esp+4] downstream")
    print("  exits: B1 normal -> 0x%08X, B1 skip -> 0x%08X, B2 -> 0x%08X"
          % (RESUME1, DEAD_EXIT, RESUME2))
    print()
    h1, h2 = build_hooks(labels)
    show(h1, HOOK1, "hook B1, patched")
    show(HOOK1_ORIG, HOOK1, "hook B1, vanilla")
    show(h2, HOOK2, "hook B2, patched")
    show(HOOK2_ORIG, HOOK2, "hook B2, vanilla")
    print()
    o1, o2 = va2off(d, HOOK1), va2off(d, HOOK2)
    show(bytes(d[o1:o1 + HOOK1_LEN]), HOOK1, "hook B1, currently on disk")
    show(bytes(d[o2:o2 + HOOK2_LEN]), HOOK2, "hook B2, currently on disk")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="install, or re-tune in place")
    ap.add_argument("--undo", action="store_true",
                    help="surgical: restore both windows, zero our cave, touch no backup")
    ap.add_argument("--dis", "--show", dest="dis", action="store_true",
                    help="disassemble the assembled caves")
    a = ap.parse_args()
    if a.apply and a.undo:
        sys.exit("ABORT: --apply and --undo are mutually exclusive")

    d = read_target()
    assert_in_code(d, HOOK1, HOOK1 + HOOK1_LEN - 1, RESUME1,
                   HOOK2, HOOK2 + HOOK2_LEN - 1, RESUME2, DEAD_EXIT,
                   CAVE, CAVE + CAVE_ZONE - 1)
    blob, labels = build_caves(d)

    if a.dis:
        return cmd_dis(d, blob, labels)
    if a.undo:
        return cmd_undo(d, blob, labels)
    if a.apply:
        return cmd_apply(d, blob, labels)
    cmd_verify(d, blob, labels)
    return 0


if __name__ == "__main__":
    sys.exit(main())
