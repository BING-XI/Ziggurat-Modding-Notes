#!/usr/bin/env python3
r"""
AoW1 mod -- Vision becomes a 9-level ability, +1 sight per level instead of +2.

  sight = 3 + level        (was 3 + 2*level, capped at level 4 -> 11)
  levels I..IX             (was I..IV)
  new ceiling 3 + 9 = 12   (was 3 + 2*4 = 11)

Vision is ability id 0x40, class `TVisionAbility : TMultiLevelAbility : TAbility`. It already sits
on the engine's multi-level framework, so the ceiling is a single immediate and the level plumbing
(CanExpand / Expand / ExpandCost / GetSkillPoints) needs no changes at all.

TWO FILES: five patches + three cave blocks in AoWEPACK.dpl, and one length-changing field rewrite
in Release/Ability.pfs. No exe patch, so no AoWCompat lockstep.

The unit data is deliberately NOT rescaled. Unitres.pfs / HEROES.PFS / ITEMS.PFS keep the Vision
levels they already assign, so every existing holder simply sees less (level IV goes 11 -> 7). That
nerf is the intended balance change, not an oversight; levels V..IX are headroom. Do not add a
rescale path.

A. CAP 4 -> 9.  `TVisionAbility.Create` @0x557B9864 seeds the ceiling:
       557B9889  c7 46 28 04 00 00 00     mov dword [esi+0x28], 4
   `TMultiLevelAbility.CanExpand` @0x55765308 is the only gate --
       55765334  cmp eax, [ebx+0x28] / jl -- and Vision inherits it (VMT +0xC4 = 0x55765308),
   so raising this one immediate raises the ceiling everywhere.

B/C. RANGE x2 -> x1.  TWO sites compute the sight radius, and both must be patched or the
   strategic map and the tactical battle disagree:
       55780F12   TAbstractUnit.VisibilityRange   @0x55780EF8
       55724AEE   TCombatUnit.GetVisibilityRange  @0x55724AD0
   Both read `03 F6  83 C6 03` = `add esi,esi` (the x2) then `add esi,3` (the base). We NOP the
   doubling only; the base is untouched. Neither run carries a .reloc entry (verified by parsing
   .reloc, not assumed).
   !! The `83 C6 03` base of 3 is a PRE-EXISTING undocumented Ziggurat edit -- the pristine DLL
   has `83 C6 04`. The script verifies the live base and ABORTS if it finds 4, because that would
   mean it is looking at an install this change was not costed against.

D. PER-LEVEL COST LIST.  `[ability+0x2C]` is a TIntegerList of per-level expand costs; the ctor
   Puts cost[1..4] in four identical 18-byte blocks at 0x557B9897..0x557B98DE (72 B, no relocs).
   `Engine.TIntegerList.Get` is bounds-checked and returns the list's default (`[list+0x10]`)
   instead of raising, so levels 5..9 would silently cost ZERO skill points -- a balance defect,
   not a crash, which is exactly the kind that ships. `TIntegerList.Put` auto-grows via SetCount,
   so nine Puts work exactly like four. We replace the whole 72-byte run with a jump to
   `cave_vcosts`, which loops Put(list, 1..9, COST_EACH) and jumps back to 0x557B98DF.

E. LEVEL NAMES V..IX.  `TVisionAbility.GetLevelName` @0x557B98F8 does `cmp edx,4 / ja 0x557B99F2`
   -- and 0x557B99F2 is the SEH TEARDOWN, not a default arm, so level >= 5 returns with the out
   string never assigned (renders empty). Both the unit info card and the hero level-up dialog
   route through VMT +0x10C (`TMultiLevelAbility.GetName` @0x55765298 and `ExpandName`
   @0x557652BC -- the latter names level+1, so an empty name shows up before anyone even owns
   Vision V).

   !! DO NOT extend the existing jump table.  `jmp dword [edx*4 + 0x557B9920]` looks trivially
   repointable, but all five entries (0x557B9920/24/28/2C/30) carry .reloc entries; a cave-hosted
   replacement table would have none and every entry would go stale the moment the package
   rebases. Instead we repoint the VMT SLOT, which is itself relocated:
       TVisionAbility VMT base 0x557B502C, slot +0x10C = 0x557B5138
   -- verified to be the ONLY reference to 0x557B98F8 anywhere in the module, and it carries a
   .reloc entry, so changing the VALUE keeps the loader fixing it up after the rebase.

   `cave_vlname` (EAX=self, EDX=level, ECX=out:PAnsiString):
       level 0..4   -> tail-`jmp` the original, byte-for-byte vanilla behaviour
       level 5..9   -> call original with level 0 to get the translated bare "Vision", then
                       @LStrCat3 a suffix onto it
       level >= 10  -> tail-`jmp` the original with level forced to 0, so an out-of-range query
                       yields the bare name instead of vanilla's unassigned (empty) string
   Calling the original with level 0 is how build_leadership4.py's cave_lsname gets the base name,
   and it is the reason this cave needs no absolute reference to the resourcestring record: the
   vanilla arm's `mov eax,[0x558E90C0]` is an absolute memory ref that CANNOT be replicated in a
   position-independent cave, but the arm-0 call reaches it through already-relocated code.

   SUFFIX LITERALS.  The game's own " I".." IV" live at 0x557B9A24/30/3C/4C as Delphi const
   AnsiStrings (refcount -1 at ptr-8, length at ptr-4). " V" exists once more at 0x5576DE04, and
   " VI" / " VII" / " VIII" / " IX" exist NOWHERE in the DLL. We mint all FIVE in the cave rather
   than borrowing 0x5576DE04: a const string is refcount -1 and never written, so a read+execute
   CODE cave is a valid home, and minting avoids a cross-feature dependency on TSpellCastingAbility
   data that this project actively patches. (build_leadership4.py borrows the game's literals; that
   is fine when they belong to an untouched class.)

POSITION INDEPENDENCE
  The .dpl always rebases, so no cave may contain an un-relocated absolute reference. cave_vcosts
  is rel32-only. cave_vlname needs the addresses of its own suffix table and literals, so it
  computes the LOAD DELTA with the standard call/pop trick (`call _n; pop ebp; sub ebp, <link addr
  of _n>`) and indexes `[ebp + edx*4 + SUF_TAB]`; the stored dwords are link-time VAs to which the
  same delta is added. Every call out (original GetLevelName, TIntegerList.Put, LStrCat3, LStrClr)
  is rel32.

RAISING MAX_LEVEL AGAIN -- two ceilings, and the NEARER one is not the arithmetic
  Measured, not reasoned:

    MAX_LEVEL  rec-74 tag-9 dir offset   sight nibble   outcome
        9  (now)          223                 12        ok
       10                 240                 13        ok
       11                 257                 14        ABORTS -- u8 ceiling, in pfs_plan
       12                 274                 15        ABORTS -- u8 ceiling, in pfs_plan
       13                 291                 16        ABORTS -- NIBBLE guard, at import
                                                        (u8 would block too, but is never reached)

  1. THE U8 BODY-DIRECTORY CEILING BITES FIRST, at MAX_LEVEL 11. Each extra level adds a
     15-byte `Level N  (+N)\r\n` line to the tag-5 description (17 once N reaches double digits),
     which pushes tags 6/7/8/9 further down record 74's body; those directory offsets are single
     bytes. 223 of 255 is used today -- ONE level of headroom, since 10 fits at 240 and 11 does
     not at 257. THE ESCAPE IS REAL AND CHEAP: the format supports wide (u32) directory entries
     and 25 records in this very file already use them (32, 67, 68, 71, ...). pfs_plan aborts
     with that instruction rather than truncating.

  2. The arithmetic wall is two rungs further out: 12 is the last safe MAX_LEVEL, 13 breaks it.
     `TArmy.UpdateVisibilityRanges` @0x5578E10C packs the stack maximum into a NIBBLE PAIR at
     [army+0x29] with no clamp whatsoever:
         5578E155  shl ebx, 4                 ; max TrueVisionRange -> high nibble
         5578E158  add bl, byte ptr [esp]     ; max VisibilityRange -> low nibble
         5578E15B  mov byte ptr [esi+0x29], bl
     and the two getters split it back with `and al,0xf` / `shr eax,4`. So BASE_SIGHT + MAX_LEVEL
     must stay <= 15 or sight overflows into the army's TrueVision range. This one has no cheap
     escape -- it is the engine's storage format -- so it is the real ceiling on the feature.

  Both raise SystemExit rather than assert, so `python -O` cannot strip them (see below).

F. DESCRIPTION -- Release/Ability.pfs record 74 (= ability id 0x40 + 10), tag 5. The info card's
   text still promised "+2/+4/+6/+8" for four levels. Rewritten to +1..+9 over nine levels, same
   header sentence, same `Level N  (+N)` double-space, trailing CRLF kept. Tag 6 (the point cost,
   8) is left alone -- it already agrees with COST_EACH.

   This is the risky part: it is the only LENGTH-CHANGING .pfs write in the project. See the big
   comment block above ABIL_PFS for the three traps it has to survive (u32- not u8-prefixed string;
   the last record's body swallowing the trailing CRC; u8 body-directory offsets running to 223 of
   a 255 ceiling). The rewrite derives the index layout from the file, shifts the 87 record offsets
   that sit after record 74, repairs the CRC, and then re-parses the result and asserts that all
   151 records still parse, that the other 150 are byte-identical, and that record 74 still carries
   exactly tags {5,6,7,8,9} with 6/7/8/9 unchanged. That check runs during the DRY RUN too, so a
   rewrite that would damage the file is caught before --apply.

CAVE ADDRESSES
  ⚠⚠ THIS FEATURE RESERVES 0x55817000..0x55817400 (1024 B). DO NOT ALLOCATE INSIDE IT.
  Content is only ~280 B, but the block is written and zeroed AS ONE UNIT -- that is what makes a
  shrinking re-tune leave no stale bytes, and it is why the whole range must stay ours. The
  ownership test is the two hooks (VMT slot -> CAVE_NAME, ctor jmp -> CAVE_COSTS) pointing into
  the block; it does not inspect the block's contents, so anything a future feature parks in the
  reserved range WILL be silently overwritten on --apply and zeroed on --undo. Measured 2026-08-09:
  0 .reloc entries, 0 exports and 0 inbound references of any kind land in the range.

  It sits inside the free zeroed run 0x558160ED..0x558E7A00 (0xD1913 zero bytes, measured on the
  unpatched file; an earlier note said 0x9F13 to 0x55820000, which is a conservative sub-range, not
  a different measurement) and past 0x55816000, the highest address any other build script
  references (build_drillmaster.py, whose content ends at 0x558160ED -- 0xF13 bytes of clearance).
  Zone freeness is re-asserted at write time.

RE-TUNING
  Change MAX_LEVEL / COST_EACH / SUFFIXES and re-run --apply. Do NOT revert first: there is no
  snapshot layer at all, and --undo is the only revert path.

  Both halves rewrite IN PLACE. The caves verify against either the installed bytes or the new
  ones and assert the growth zone is still zero. The Ability.pfs description accepts any text
  matching the SHAPE this script produces (header sentence + a `Level N  (+V)` run counting from
  1), not one exact string -- so changing MAX_LEVEL and re-applying works, and so does --undo from
  any of them. See desc_shape(); an exact-match guard made the re-tune above impossible and needed
  the old MAX_LEVEL restored before --undo would run.

  MAX_LEVEL 10 is the last value that fits without more work -- see "RAISING MAX_LEVEL AGAIN".

Idempotent, verify-before-write, free-space asserted, dry-run by default / --apply / --undo / --dis.
"""
import os, re, sys, shutil, struct, zlib, importlib.util
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

DLL_BASE = 0x55700000
SUFFIX = ".pre-vision9"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)


def require(cond, msg):
    """A guard that `python -O` CANNOT strip.

    ⚠ Do not write these as `assert`. Every guard in this script exists to turn a silently-wrong
    patch into a loud abort -- a mis-sized cave, a keystone encoding that moved, a sight value that
    overflows the engine's nibble. `-O` removes `assert` outright, and a stripped guard here does
    not fail: it writes a broken DLL that boots and then misbehaves. (Measured: under `-O` with
    MAX_LEVEL = 13 the module ran to completion with no abort at all.)
    """
    if not cond:
        raise SystemExit("ABORT: " + msg)

# ---------------------------------------------------------------- tunables
MAX_LEVEL  = 9          # ability ceiling  (vanilla 4)
BASE_SIGHT = 3          # `add esi, 3` -- Ziggurat's value; pristine DLL has 4
COST_EACH  = 4          # skill points per level -- halved from 8 on author instruction 2026-08-09
COST_PREV  = 8          # what was installed BEFORE this feature, and what --undo restores.
# ⚠ NOT vanilla's 5. Ziggurat had already retuned the ctor Put from 5 to 8 (and Ability.pfs tag 6
# with it) before this feature existed, so `.pre-vision9` carries 8 on both sides. Restoring 5
# would be a silent extra edit dressed up as an undo.
#
# ⚠⚠ FOR A MULTI-LEVEL ABILITY THE DLL IS AUTHORITATIVE, NOT Ability.pfs tag 6.
# `TAbility.ExpandCost` @0x5574E908 returns tag 6 (instance +0x14), but
# `TMultiLevelAbility.ExpandCost` OVERRIDES it and reads the per-level TIntegerList at
# [ability+0x2C] -- the list cave_vcosts fills. Tag 6 is therefore inert for cost here; it is
# written purely so the two agree, because the Ziggurat Manual reads tag 6 for its "Hero cost"
# column and would otherwise print a number the game does not charge. Leadership is the standing
# proof: tag 6 still says 20 while its ctor Put was retuned.
SUFFIXES   = (" V", " VI", " VII", " VIII", " IX")   # names for levels 5..MAX_LEVEL

# Release/Ability.pfs record 74 tag 5, the in-game description. GENERATED from the curve rather
# than pasted, so it cannot drift from MAX_LEVEL.
DESC_HEAD = "Gives the unit increased visual range in addition to the base 3 range.\r\n"


def desc_enumerated(levels, step):
    """Vanilla's shape: one `Level N  (+V)` line per level. Only DESC_OLD uses it now."""
    return DESC_HEAD + "".join("Level %d  (+%d)\r\n" % (i, i * step) for i in range(1, levels + 1))


def desc_compact(step):
    """The whole description: one line, no header sentence, independent of MAX_LEVEL.

    ⚠ Two author instructions on 2026-08-09, in order, and BOTH forms must stay recognised by
    desc_shape() because each was installed for a while:
      1. drop the per-level enumeration -- at a flat +1/level "Level 7  (+7)" is redundantly
         obvious and nine lines of it is noise. (The info card does NOT clip; it scrolls. This was
         readability, not a fix.) That produced DESC_HEAD + this line.
      2. drop the header sentence too, leaving JUST the curve.
    Vanilla enumerates because its curve is +2/level over four levels, where the running total is
    worth spelling out. Side benefit of either step: the record no longer grows with MAX_LEVEL,
    which retires the u8 directory ceiling that used to bite at 11.
    """
    return "+%d vision range per level\r\n" % step


DESC_OLD = desc_enumerated(4, 2)          # vanilla/Ziggurat: 4 levels, +2 each
DESC_NEW = desc_compact(1)                # ours: one line, +1 per level


def desc_shape(text):
    """Truthy if `text` is a description THIS SCRIPT COULD HAVE WRITTEN, else None.

    Returns [(level, bonus)] for the enumerated form and [("per-level", step)] for the compact one
    -- callers only test truthiness, and both are non-empty for any real curve.

    ⚠ Why a shape test and not `text in (DESC_OLD, DESC_NEW)`: DESC_NEW is derived from the
    tunables, so an exact-match guard makes the documented re-tune impossible. Apply, change a
    tunable, --apply -> the installed text matches neither constant and phase 1 refuses; --undo
    refuses for the same reason, so recovery needs the OLD value put back first. That is exactly
    the "rewrite in place, never revert-and-re-apply" rule from CLAUDE.md, applied to a .pfs field.

    ⚠ ALL THREE ARMS must stay accepted. None is dead code -- each was the emitted format for a
    while on 2026-08-09, so a real install can be carrying any of them, and dropping an arm strands
    exactly those installs: --apply AND --undo both refuse, and the only recovery is editing this
    file. **Whenever the emitted format changes, KEEP the previous arm.**
        1. bare curve, no header      <- current output
        2. header + bare curve        <- briefly emitted between the two author instructions
        3. header + per-level listing <- vanilla (DESC_OLD), and our first output

    ⚠ `not shape`, never `shape is None`: arm 3 returns [] for header-only text (a well-formed run
    of zero levels), and an empty list is not None.
    """
    CURVE = r"\+(\d+) vision range per level\r\n"
    m = re.fullmatch(CURVE, text)
    if m:                                             # 1. bare curve
        return [("per-level", int(m.group(1)))]
    if not text.startswith(DESC_HEAD):
        return None
    rest = text[len(DESC_HEAD):]
    if rest and not rest.endswith("\r\n"):
        return None
    m = re.fullmatch(CURVE, rest)
    if m:                                             # 2. header + curve
        return [("per-level", int(m.group(1)))]
    out = []                                          # 3. header + per-level listing
    for i, line in enumerate(rest.split("\r\n")[:-1] if rest else [], start=1):
        m = re.fullmatch(r"Level (\d+)  \(\+(\d+)\)", line)
        if not m or int(m.group(1)) != i:
            return None
        out.append((i, int(m.group(2))))
    return out

# ⚠ The nearer ceiling is the u8 body-directory offset in Ability.pfs (bites at MAX_LEVEL 11) and
# pfs_plan raises it; this is the second, harder wall. See "RAISING MAX_LEVEL AGAIN" in the header.
require(BASE_SIGHT + MAX_LEVEL <= 15,
        "sight %d+%d=%d overflows the [army+0x29] nibble pair at TArmy.UpdateVisibilityRanges "
        "@0x5578E10C (shl ebx,4 / add bl,[esp], no clamp) and would corrupt TrueVisionRange"
        % (BASE_SIGHT, MAX_LEVEL, BASE_SIGHT + MAX_LEVEL))
require(len(SUFFIXES) == MAX_LEVEL - 4, "need one suffix per level 5..%d" % MAX_LEVEL)

# ---------------------------------------------------------------- addresses (verified on the live DLL)
CAP_SITE   = 0x557B9889   # mov dword [esi+0x28], 4      (7 B: C7 46 28 04 00 00 00)
VIS_STRAT  = 0x55780F12   # add esi, esi  in TAbstractUnit.VisibilityRange  @0x55780EF8
VIS_COMBAT = 0x55724AEE   # add esi, esi  in TCombatUnit.GetVisibilityRange @0x55724AD0
COST_RUN   = 0x557B9897   # first of four 18-byte Put blocks
COST_END   = 0x557B98DF   # `test bl, bl` -- where the ctor resumes
PUT_FN     = 0x55702EB4   # AoWEPACK thunk -> EngineP.dpl!Engine.TIntegerList.Put (EAX,EDX,ECX)
VMT_SLOT   = 0x557B5138   # TVisionAbility VMT +0x10C (GetLevelName); vmt base 0x557B502C
ORIG_NAME  = 0x557B98F8   # TVisionAbility.GetLevelName
LSTRCAT3   = 0x55701190   # System.@LStrCat3 (EAX=dest, EDX=s1, ECX=s2)
LSTRCLR    = 0x55701140   # System.@LStrClr  (EAX=&str)

COST_LEN   = COST_END - COST_RUN          # 72
require(COST_LEN == 0x48, "the ctor Put run is %d B, expected 0x48" % COST_LEN)

# ---------------------------------------------------------------- cave block
CAVE_COSTS = 0x55817000
CAVE_NAME  = 0x55817040
CAVE_DATA  = 0x558170C0                   # suffix pointer table, then the literals
SUF_TAB    = CAVE_DATA
LIT_BASE   = CAVE_DATA + 4 * len(SUFFIXES)


def rel32(src, dst):
    return struct.pack("<i", dst - (src + 5))


# ---------------------------------------------------------------- cave_vcosts
# Entered from the ctor with ESI = self (the ability). Vanilla clobbers EAX/EDX/ECX and relies on
# ESI and EBX surviving; EDI is ours to borrow as long as we give it back.
costs_src = f"""
    push edi
    mov  edi, 1
_loop:
    mov  eax, [esi + 0x2c]
    mov  edx, edi
    mov  ecx, {COST_EACH}
    call 0x{PUT_FN:X}
    inc  edi
    cmp  edi, {MAX_LEVEL}
    jle  _loop
    pop  edi
    jmp  0x{COST_END:X}
"""
cave_costs = bytes(ks.asm(costs_src, CAVE_COSTS)[0])

# ---------------------------------------------------------------- cave_vlname
# Replaces TVisionAbility.GetLevelName via the VMT. EAX=self, EDX=level, ECX=out:PAnsiString.
# EBP holds the load delta for the 5..MAX_LEVEL branch.
def _name_src(link_n):
    return f"""
    cmp  edx, 4
    jbe  _orig
    cmp  edx, {MAX_LEVEL}
    ja   _clamp
    push ebx
    push esi
    push edi
    push ebp
    mov  edi, ecx
    mov  esi, edx
    mov  ebx, eax
    call _n
_n:
    pop  ebp
    sub  ebp, 0x{link_n:X}
    push 0
    mov  ecx, esp
    xor  edx, edx
    mov  eax, ebx
    call 0x{ORIG_NAME:X}
    lea  edx, [esi - 5]
    mov  ecx, [ebp + edx*4 + 0x{SUF_TAB:X}]
    add  ecx, ebp
    mov  edx, [esp]
    mov  eax, edi
    call 0x{LSTRCAT3:X}
    mov  eax, esp
    call 0x{LSTRCLR:X}
    add  esp, 4
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret
_clamp:
    xor  edx, edx
_orig:
    jmp  0x{ORIG_NAME:X}
"""

# Two passes: the first only locates the `pop ebp` anchor. The dummy link_n is deliberately a large
# VA so `sub ebp, imm32` keeps the same 6-byte encoding in both passes and nothing shifts.
_p1 = bytes(ks.asm(_name_src(CAVE_NAME), CAVE_NAME)[0])
_anchor = _p1.index(b"\xE8\x00\x00\x00\x00\x5D") + 5      # offset of `pop ebp`
LINK_N = CAVE_NAME + _anchor
cave_name = bytes(ks.asm(_name_src(LINK_N), CAVE_NAME)[0])
require(len(cave_name) == len(_p1), "cave_vlname shifted between passes -- LINK_N is wrong")
require(cave_name[_anchor] == 0x5D, "call/pop anchor mismatch (expected `pop ebp` at LINK_N)")

# ---------------------------------------------------------------- suffix literals + pointer table
# Delphi 3 const AnsiString: [ptr-8] = refcount (-1), [ptr-4] = length, then chars + NUL.
_lits, _ptrs, _cur = b"", [], LIT_BASE
for s in SUFFIXES:
    raw = s.encode("ascii") + b"\x00"
    raw += b"\x00" * (-len(raw) % 4)
    _lits += struct.pack("<iI", -1, len(s)) + raw
    _ptrs.append(_cur + 8)
    _cur += 8 + len(raw)
data_blob = b"".join(struct.pack("<I", v) for v in _ptrs) + _lits

# ---------------------------------------------------------------- the four vanilla Put blocks
# Rebuilt from COST_EACH so --undo restores exactly what was displaced (the INSTALLED value, which
# is Ziggurat's 8 -- the pristine DLL's 5 is not what we took away).
cost_orig = b"".join(
    b"\xB9" + struct.pack("<I", COST_EACH)          # mov ecx, COST_EACH
    + b"\xBA" + struct.pack("<I", lvl)              # mov edx, lvl
    + b"\x8B\x46\x2C"                               # mov eax, [esi+0x2c]
    + b"\xE8" + rel32(COST_RUN + (lvl - 1) * 18 + 13, PUT_FN)
    for lvl in (1, 2, 3, 4))
require(len(cost_orig) == COST_LEN,
        "rebuilt vanilla Put run is %d B, expected %d" % (len(cost_orig), COST_LEN))
cost_new = b"\xE9" + rel32(COST_RUN, CAVE_COSTS) + b"\x90" * (COST_LEN - 5)

# ---------------------------------------------------------------- layout guards
require(len(cave_costs) <= CAVE_NAME - CAVE_COSTS, "cave_vcosts overruns cave_vlname")
require(len(cave_name) <= CAVE_DATA - CAVE_NAME, "cave_vlname overruns the data block")
CAVE_TOP = CAVE_DATA + len(data_blob)
require(CAVE_TOP < 0x55820000, "cave block leaves the measured free run")

# The whole reserved block is written and undone as ONE unit, so a re-tune cannot leave stale bytes
# from a longer previous build sitting past the new end. Fixed size, independent of MAX_LEVEL.
CAVE_BLOCK = 0x400
require(CAVE_TOP - CAVE_COSTS <= CAVE_BLOCK,
        "cave content is %d B, larger than the %d B reserved block"
        % (CAVE_TOP - CAVE_COSTS, CAVE_BLOCK))
require(CAVE_COSTS + CAVE_BLOCK <= 0x55820000, "reserved block leaves the measured free run")
_blob = bytearray(CAVE_BLOCK)
for _va, _piece in ((CAVE_COSTS, cave_costs), (CAVE_NAME, cave_name), (CAVE_DATA, data_blob)):
    _o = _va - CAVE_COSTS
    _blob[_o:_o + len(_piece)] = _piece      # ⚠ NOT _blob[_o:][:n] -- slicing a bytearray yields
cave_blob = bytes(_blob)                     #   a COPY, so that form silently assigns to nothing
require(cave_blob[:len(cave_costs)] == cave_costs
        and cave_blob[CAVE_NAME - CAVE_COSTS:][:len(cave_name)] == cave_name
        and cave_blob[CAVE_DATA - CAVE_COSTS:][:len(data_blob)] == data_blob
        and any(cave_blob), "cave block assembly lost its content")

APPLY = "--apply" in sys.argv
UNDO = "--undo" in sys.argv
DIS = "--dis" in sys.argv


# ================================================================ Release/Ability.pfs (tag 5)
# The description the info card shows. This is a LENGTH-CHANGING .pfs write -- the field grows
# 136 -> 211 bytes and the record 161 -> 236 -- which no other build script in this project does,
# so every offset downstream of record 74 has to be rebuilt and the trailing CRC repaired.
#
# ⚠ Tag 5 is a u32-LENGTH-PREFIXED Delphi string, NOT the u8 Pascal form `pfs.pstr()` assumes.
#   pstr() on this field returns three leading NULs and drops the last character. The field is
#   `<u32 len><len bytes latin-1>`; 4 + 132 == 136 exactly, which is how it was confirmed.
#
# ⚠ The LAST record's body swallows the file's 4-byte trailing CRC -- `parse_index` gives it
#   `d[start:len(d)]`. Harmless for a byte-splice rewrite like this one, but any "did any other
#   record change?" comparison must strip those 4 bytes or it reports a false positive.
#
# ⚠ Record-body directory offsets are u8 when the body uses SMALL entries. Record 74's largest
#   offset goes 148 -> 223 against a 255 ceiling; it fits, but only just, so it is asserted. The
#   format does support wide (u32) body entries -- 25 records in this very file already use them
#   -- so an overflow is fixable, just not silently.
ABIL_PFS = os.path.join(GAME, "Release", "Ability.pfs")
PFS_RESIDUE = 0x2144DF1C      # crc32(d[4:]) of an intact file -- see PFS_Format_CRC.md
PFS_REC = 0x40 + 10           # Ability.pfs record id = ability id + 10  -> 74
PFS_DESC_TAG = 5
PFS_COST_TAG = 6          # inert for cost on a multi-level ability; kept in sync for the manual


def _pfs_mod():
    """Load re_tools/pfs.py relative to THIS SCRIPT, not to GAME.

    ⚠ `AOW_GAME_DIR` points at a game install to patch; the toolkit travels with the script.
    Resolving the parser under `GAME` meant that pointing the script at any other install -- which
    is exactly how it gets tested on throwaway copies -- died with FileNotFoundError on
    `<copy>/Modding Resources/re_tools/pfs.py`. Same rule as `TOOLS` in re_tools/*.py.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "pfs", os.path.join(here, "..", "re_tools", "pfs.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pfs_index_layout(d):
    """(payload_base, [(record_id, offset, offset_field_pos, field_width)]) for the file index.

    Derived from the bytes and then ASSERTED against a backwards tiling of the record bodies --
    AoWDevEd rewrites this file whole and every offset in it moves, so nothing here may be
    hard-coded. Mirrors re_tools/pfs.py:parse_index, but also reports WHERE each offset lives so
    it can be rewritten.
    """
    best = None
    for s in range(0, 0x40):
        ids, offs, p = [], [], s
        while p + 8 <= len(d):
            i, o = struct.unpack_from("<II", d, p)
            if ids and (i <= ids[-1] or o <= offs[-1]):
                break
            if i > 0x10000 or o > len(d):
                break
            ids.append(i); offs.append(o); p += 8
        if len(ids) > 5 and (best is None or len(ids) > len(best[1])):
            best = (s, ids, offs)
    if best is None:
        raise ValueError("no wide index found in Ability.pfs")
    S, wids, _woffs = best
    N = len(wids)
    for p in range(0, S):
        if not (d[p] & 0x80):
            continue
        if struct.unpack_from("<I", d, p + 1)[0] != N:
            continue
        ns = d[p] & 0x7F
        if p + 5 + 2 * ns == S:
            ent = [(d[p + 5 + 2 * k], d[p + 6 + 2 * k], p + 6 + 2 * k, 1) for k in range(ns)]
            ent += [(struct.unpack_from("<I", d, S + 8 * k)[0],
                     struct.unpack_from("<I", d, S + 8 * k + 4)[0], S + 8 * k + 4, 4)
                    for k in range(N)]
            return S + 8 * N, ent
    raise ValueError("Ability.pfs index layout not recognised")


def pfs_desc_text(d):
    """Record PFS_REC's tag-5 description text, or None if the file will not give it up.

    Deliberately total: every caller here is asking a yes/no question about the CURRENT file, and a
    None answer must read as "not the text you asked about" rather than a traceback. pfs_plan does
    the same extraction with full diagnostics -- this is the quiet version.
    """
    try:
        pfs = _pfs_mod()
        cur = pfs.parse_dir(dict(pfs.parse_index(d))[PFS_REC], top=False)[PFS_DESC_TAG]
        n = struct.unpack_from("<I", cur, 0)[0]
        return cur[4:].decode("latin-1") if 4 + n == len(cur) else None
    except (ValueError, IndexError, KeyError, struct.error):
        return None


def pfs_plan(d, want_text, want_cost):
    """Pure: (status, new_bytes, note). Never writes. status in {'same', 'ok', 'error'}.

    Rebuilds record PFS_REC with `want_text` in tag 5, shifts every later index offset by the
    delta, and repairs the trailing CRC.
    """
    # Integrity gate. It must live HERE rather than only in the caller so the pure function fails
    # closed for any future caller. What it actually buys, stated honestly:
    #   CATCHES  incoherent damage -- a flipped payload byte, a nudged index offset, a truncated
    #            file: anything whose bytes no longer match the stored CRC.
    #   MISSES   a coherent-but-wrong layout. Nudge a wide index offset by +3 AND re-repair the
    #            CRC and this plans `ok` (measured). pfs_collateral cannot catch that either,
    #            because it parses the old and the new file with the same wrong offsets.
    # ⚠ Do NOT "strengthen" this by reconstructing record starts from body lengths tiled backwards
    #   from EOF and comparing them to the index offsets. That check is CIRCULAR and can never
    #   fail: parse_index derives those body lengths from the very offsets being checked. It was
    #   here, it passed a +3 nudge, and it was removed.
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        return "error", None, ("CRC residue is wrong before any edit -- the file is already "
                               "damaged; refusing to rewrite it")
    # ⚠ Both parsers PROBE for the index layout, so an unfamiliar file makes them raise rather than
    # return. That is a realistic input, not a hypothetical: AoWDevEd rewrites this whole file when
    # the author saves a map (it did so on 2026-08-09, touching tag 8 of 36 records). A traceback
    # here would be a bug report; return a readable error instead, per this function's contract.
    try:
        pfs = _pfs_mod()
        recs = pfs.parse_index(bytes(d))
        base, ent = pfs_index_layout(bytes(d))
    except (ValueError, IndexError, KeyError, struct.error) as exc:
        return "error", None, (f"cannot parse the Ability.pfs index ({exc}) -- the file's layout is "
                               "not one this script recognises, so it will not be rewritten")

    # Two independent parses of the index must agree on the record list. This checks the layout
    # DISCOVERY (parse_index probes for the wide-array start; so does pfs_index_layout, separately),
    # not the data -- data integrity is the CRC above.
    if [a for a, _, _, _ in ent] != [r for r, _ in recs]:
        return "error", None, "index entry ids disagree with parse_index"

    bodies = dict(recs)
    if PFS_REC not in bodies:
        return "error", None, f"no record {PFS_REC} (ability {PFS_REC - 10:#04x}) in Ability.pfs"
    body = bodies[PFS_REC]
    off74 = dict((a, b) for a, b, _, _ in ent)[PFS_REC]
    a0 = base + off74

    if body[0] & 0x80:
        return "error", None, (f"record {PFS_REC} body uses WIDE directory entries; this writer "
                               "only handles the small (u8) form it was verified against")
    nsm = body[0] & 0x7F
    dents = [(body[1 + 2 * k], body[2 + 2 * k]) for k in range(nsm)]
    dsz = 1 + 2 * nsm
    tags = sorted(t for t, _ in dents)
    if tags != [5, 6, 7, 8, 9]:
        return "error", None, f"record {PFS_REC} carries tags {tags}, expected [5, 6, 7, 8, 9]"

    try:
        fields = pfs.parse_dir(body, top=False)  # ability.pfs bodies have no classid prefix
    except (ValueError, IndexError, struct.error) as exc:
        return "error", None, f"record {PFS_REC} body does not parse ({exc})"
    cur = fields[PFS_DESC_TAG]
    if len(cur) < 4:
        return "error", None, f"tag 5 is only {len(cur)} B -- too short to hold a u32 prefix"
    n = struct.unpack_from("<I", cur, 0)[0]
    if 4 + n != len(cur):
        return "error", None, (f"tag 5 is {len(cur)} B but its u32 prefix says {n} "
                               f"(expected {4 + n}); not the u32-prefixed string form")
    cur_text = cur[4:].decode("latin-1")
    c6 = fields.get(PFS_COST_TAG, b"")
    if len(c6) != 4:
        return "error", None, f"tag 6 is {len(c6)} B, expected a 4-byte cost"
    cur_cost = struct.unpack_from("<I", c6, 0)[0]
    if cur_text != want_text:
        shape = desc_shape(cur_text)         # any curve THIS script could have written, not just
        if not shape:                        # the current MAX_LEVEL's -- see desc_shape()
            # ⚠ `not shape`, NOT `shape is None`: desc_shape() returns [] for header-only text (a
            # well-formed run of zero levels), and an empty list is not None, so `is None` would
            # accept it as ours and overwrite it. This script cannot emit header-only text, so it
            # could only arrive as a hand-edit -- which is exactly what this guard is for.
            return "error", None, ("tag 5 is not a description this script wrote (someone or "
                                   "something else has edited it) -- refusing to overwrite:\n"
                                   f"     {cur_text!r}")
    if cur_text == want_text and cur_cost == want_cost:
        return "same", None, (f"tag 5 already the target text ({len(cur)} B), "
                              f"tag 6 already {want_cost}")

    new_field = struct.pack("<I", len(want_text)) + want_text.encode("latin-1")
    shift = len(new_field) - len(cur)

    # --- rebuild the body directory: tag 5 stays at 0, everything after it moves --------------
    off5 = dict(dents)[PFS_DESC_TAG]
    new_dents = [(t, o + shift if o > off5 else o) for t, o in dents]
    for t, o in new_dents:
        if o > 0xFF:
            return "error", None, (
                f"record {PFS_REC} tag {t} offset {o} exceeds the u8 directory ceiling (255). "
                "The description is too long for the small-entry form; convert this body to WIDE "
                "(u32) entries -- records 32/67/68/71 in this same file already use them.")
    new_body = bytearray([nsm])
    for t, o in new_dents:
        new_body += bytes([t, o])
    require(len(new_body) == dsz, "rebuilt record %d directory is %d B, expected %d"
            % (PFS_REC, len(new_body), dsz))
    payload = bytearray(len(body) - dsz + shift)
    for t, o in new_dents:
        blob = (new_field if t == PFS_DESC_TAG
                else struct.pack("<I", want_cost) if t == PFS_COST_TAG else fields[t])
        payload[o:o + len(blob)] = blob
    new_body += payload
    if len(new_body) != len(body) + shift:
        return "error", None, "rebuilt body length is wrong"

    # --- splice + fix every later index offset + repair the CRC -------------------------------
    out = bytearray(d)
    out[a0:a0 + len(body)] = new_body           # index fields all live below `base` <= a0
    for _rid, off, pos, w in ent:
        if off <= off74:
            continue
        v = off + shift
        if w == 1:
            if v > 0xFF:
                return "error", None, f"index small-entry offset {v} overflows u8"
            out[pos] = v
        else:
            struct.pack_into("<I", out, pos, v)
    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
    if zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        return "error", None, "CRC repair failed (residue mismatch)"

    try:
        bad = pfs_collateral(bytes(d), bytes(out), want_text, want_cost)
    except (ValueError, IndexError, KeyError, struct.error) as exc:
        return "error", None, f"the rewritten file no longer parses ({exc})"
    if bad:
        return "error", None, "collateral damage: " + bad
    return "ok", bytes(out), (f"tag 5 {len(cur)} -> {len(new_field)} B, record {len(body)} -> "
                              f"{len(new_body)} B, file {len(d)} -> {len(out)} B, "
                              f"{sum(1 for _r, o, _p, _w in ent if o > off74)} later "
                              f"offsets {shift:+d}")


def pfs_collateral(old_d, new_d, want_text, want_cost):
    """'' if the rewrite touched nothing but record PFS_REC, else a description of what moved."""
    pfs = _pfs_mod()
    o = pfs.parse_index(old_d)
    n = pfs.parse_index(new_d)
    if [r for r, _ in o] != [r for r, _ in n]:
        return "record id list changed"
    if len(n) != 151:
        return f"expected 151 records, got {len(n)}"
    last = n[-1][0]
    ob, nb = dict(o), dict(n)
    for rid in ob:
        a, b = ob[rid], nb[rid]
        if rid == last:                 # its body swallows the 4-byte trailing CRC
            a, b = a[:-4], b[:-4]
        if rid == PFS_REC:
            continue
        if a != b:
            return f"record {rid} changed ({len(a)} -> {len(b)} B)"
    for rid, b in n:                    # everything must still parse
        try:
            pfs.parse_dir(b, top=False)
        except (ValueError, IndexError) as exc:
            return f"record {rid} no longer parses ({exc})"
    f_old = pfs.parse_dir(ob[PFS_REC], top=False)
    f_new = pfs.parse_dir(nb[PFS_REC], top=False)
    if sorted(f_new) != [5, 6, 7, 8, 9]:
        return f"record {PFS_REC} tags became {sorted(f_new)}"
    # 7/8/9 must be untouched. 6 is an INTENDED edit (the displayed hero cost, kept in step with
    # the DLL's per-level list) -- so it is checked against the value we meant to write, not against
    # the old one. Anything else there is still collateral damage.
    for t in (7, 8, 9):
        if f_old[t] != f_new[t]:
            return f"record {PFS_REC} tag {t} changed ({f_old[t].hex()} -> {f_new[t].hex()})"
    if f_new[PFS_COST_TAG] != struct.pack("<I", want_cost):
        return (f"record {PFS_REC} tag 6 is {f_new[PFS_COST_TAG].hex()}, "
                f"expected {struct.pack('<I', want_cost).hex()}")
    got = f_new[5][4:].decode("latin-1")
    if got != want_text or struct.unpack_from("<I", f_new[5], 0)[0] != len(want_text):
        return "record %d tag 5 did not round-trip" % PFS_REC
    return ""


def process_pfs(want_text, want_cost, commit, quiet=False):
    """Plan (and optionally write) the Ability.pfs description. Returns (ok, wrote)."""
    if not os.path.exists(ABIL_PFS):
        print(f"[x] missing {ABIL_PFS}")
        return False, False
    d = open(ABIL_PFS, "rb").read()
    status, out, note = pfs_plan(d, want_text, want_cost)   # pfs_plan gates on the CRC residue
    if status == "error":
        print(f"[x] Ability.pfs: {note}")
        return False, False
    if status == "same":
        if not quiet:
            print(f"[= ] Ability.pfs: {note}")
        return True, False
    if not quiet:
        print(f"[pfs ] {note}")
        print(f"[pfs ] collateral check: 151/151 records parse, 150 byte-identical, "
              f"record {PFS_REC} tags 7/8/9 unchanged, tag 6 (hero cost) = {want_cost}, "
              f"CRC residue {PFS_RESIDUE:#010X} OK")
        if DIS:
            for ln in want_text.rstrip("\r\n").split("\r\n"):
                print(f"         | {ln}")
    if not commit:
        return True, False
    # Back up only from an UNPATCHED file. ⚠ Two ways to mint a lying `.pre-vision9` here, and both
    # produce the "a .pre-* file is not proof of anything" artefact CLAUDE.md warns about -- one
    # that sits on disk looking authoritative:
    #   1. the undo path: the current file is the PATCHED state;
    #   2. a RE-TUNE (e.g. MAX_LEVEL 9 -> 10) after the real backup has been pruned -- the current
    #      file is then our own 9-level text, not the pre-vision9 original.
    # `cur_is_original` is the discriminator: desc_shape() deliberately accepts our own past output
    # as well as the vanilla text, so "it parses as a description we recognise" does NOT mean
    # "unpatched". Only the exact original does. The DLL half gates on `retune` for the same reason.
    cur_is_original = pfs_desc_text(d) == DESC_OLD
    if not UNDO and cur_is_original:
        bp = os.path.join(BACKUP_DIR, os.path.basename(ABIL_PFS) + SUFFIX)
        if not os.path.exists(bp):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(ABIL_PFS, bp)
            print(f"[bak] {bp}")
    try:
        open(ABIL_PFS, "wb").write(out)
    except PermissionError:
        print("[x] Ability.pfs LOCKED -- close AoW.exe / AoWCompat.exe / AoWDevEd.exe")
        return False, False
    # Describe what was actually written, derived from the text -- a hard-coded summary goes stale
    # the moment the format changes (this one still said "9 levels, +1 each" after the description
    # became a single line).
    shape = desc_shape(want_text) or []
    which = ("restored to the original enumerated %d levels" % len(shape) if want_text == DESC_OLD
             else "one line, +%d per level" % shape[0][1] if shape and shape[0][0] == "per-level"
             else "enumerated, %d levels" % len(shape) if shape
             else "custom text")
    print(f"[w ] Ability.pfs record {PFS_REC} tag 5: Vision description -> {which}")
    return True, True


def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    n = struct.unpack_from("<H", data, e + 6)[0]
    op = struct.unpack_from("<H", data, e + 20)[0]
    s = e + 24 + op
    secs = []
    for _ in range(n):
        vs, va, rs, raw = struct.unpack_from("<IIII", data, s + 8)
        secs.append((va, vs, raw, rs))
        s += 40
    return secs


def show(label, va, blob):
    print(f"[cave ] {label} @ {va:08X} ({len(blob)} B)")
    for ins in cs.disasm(blob, va):
        print(f"  {ins.address:08X} {ins.bytes.hex(' '):<26}{ins.mnemonic} {ins.op_str}")


def process(path, commit=False, quiet=False):
    """Verify (commit=False) or verify-then-write (commit=True) the AoWEPACK.dpl half."""
    data = bytearray(open(path, "rb").read())
    secs = load_sections(data)

    def va2off(va):
        rva = va - DLL_BASE
        for va0, vs, raw, rs in secs:
            if va0 <= rva < va0 + max(vs, rs):
                return raw + (rva - va0)
        raise ValueError(hex(va))

    def rd(va, n):
        o = va2off(va)
        return bytes(data[o:o + n])

    # --- the Ziggurat base-sight check: bail rather than mis-cost the change -------------------
    for va, who in ((VIS_STRAT, "TAbstractUnit.VisibilityRange"),
                    (VIS_COMBAT, "TCombatUnit.GetVisibilityRange")):
        tail = rd(va + 2, 3)
        if tail != b"\x83\xC6" + bytes([BASE_SIGHT]):
            if tail == b"\x83\xC6\x04":
                print(f"[x] {va + 2:08X} ({who}) has `add esi, 4` -- this install carries the "
                      f"PRISTINE base sight of 4, not Ziggurat's {BASE_SIGHT}.\n"
                      f"    sight would become 4+level (max {4 + MAX_LEVEL}), not "
                      f"{BASE_SIGHT}+level. Re-check the intended balance before applying.")
            else:
                print(f"[x] {va + 2:08X} ({who}) expected `83 C6 {BASE_SIGHT:02X}`, got {tail.hex(' ')}")
            return False

    # (va, original bytes, new bytes, description, ours)
    #
    # `ours(cur)` -> "cur is a value THIS SCRIPT wrote, just with different constants". Sites whose
    # new bytes depend on a tunable need it, or an in-place re-tune is impossible: at MAX_LEVEL 10
    # the installed cap `c7 46 28 09..` matches neither the vanilla `04` nor the new `0a`, so both
    # --apply and --undo would refuse. Sites whose bytes are constant (the NOPs, the rel32 hook,
    # the VMT slot) need nothing -- `orig`/`new` already cover them.
    anylevel = (lambda cur: cur[:3] == b"\xC7\x46\x28" and cur[4:] == b"\x00\x00\x00")
    patches = [
        (CAVE_COSTS, b"\x00" * CAVE_BLOCK, cave_blob,
         f"cave block {CAVE_BLOCK} B: cave_vcosts + cave_vlname + suffix table/literals",
         lambda cur: hooks_ours),
        (CAP_SITE, bytes.fromhex("c7462804000000"),
         b"\xC7\x46\x28" + struct.pack("<I", MAX_LEVEL),
         f"cap {CAP_SITE:08X}: [esi+0x28] = 4 -> {MAX_LEVEL}", anylevel),
        (VIS_STRAT, b"\x03\xF6", b"\x90\x90",
         f"{VIS_STRAT:08X} VisibilityRange: drop `add esi,esi` -> {BASE_SIGHT}+level", None),
        (VIS_COMBAT, b"\x03\xF6", b"\x90\x90",
         f"{VIS_COMBAT:08X} GetVisibilityRange: drop `add esi,esi` -> {BASE_SIGHT}+level", None),
        (COST_RUN, cost_orig, cost_new,
         f"ctor {COST_RUN:08X}: 4 inline Puts ({COST_LEN} B) -> jmp cave_vcosts", None),
        (VMT_SLOT, struct.pack("<I", ORIG_NAME), struct.pack("<I", CAVE_NAME),
         f"VMT+0x10C {VMT_SLOT:08X}: GetLevelName -> cave_vlname", None),
    ]

    def ours(va, cur):
        """True if `cur` at `va` is something this script wrote under different constants."""
        for pva, _o, _n, _d, pred in patches:
            if pva == va:
                return bool(pred and pred(cur))
        return False

    print(f"[sight] {BASE_SIGHT} + level, levels 1..{MAX_LEVEL} "
          f"(was {BASE_SIGHT} + 2*level, levels 1..4)"
          f"  ->  max {BASE_SIGHT + MAX_LEVEL} (was {BASE_SIGHT + 2 * 4})")
    print(f"[cost ] {COST_EACH} skill points per level, "
          f"{COST_EACH * MAX_LEVEL} total to reach level {MAX_LEVEL}")
    if not quiet:
        print(f"[guard] {BASE_SIGHT}+{MAX_LEVEL}={BASE_SIGHT + MAX_LEVEL} <= 15 "
              f"([army+0x29] nibble pair, TArmy.UpdateVisibilityRanges @5578E10C)")
        show("cave_vcosts", CAVE_COSTS, cave_costs)
        show("cave_vlname", CAVE_NAME, cave_name)
        print(f"[data ] {CAVE_DATA:08X} suffix table {[f'{v:08X}' for v in _ptrs]}")
        for s, v in zip(SUFFIXES, _ptrs):
            off = v - CAVE_DATA
            print(f"         {v:08X} refcnt={struct.unpack_from('<i', data_blob, off - 8)[0]:<3}"
                  f" len={struct.unpack_from('<I', data_blob, off - 4)[0]}  {s!r}")
        print(f"[cave ] block {CAVE_COSTS:08X}..{CAVE_TOP:08X} ({CAVE_TOP - CAVE_COSTS} B)")

        if DIS:
            print("\n[dis  ] --- as INSTALLED in the live file ---")
            show("cave_vcosts (live)", CAVE_COSTS, rd(CAVE_COSTS, len(cave_costs)))
            show("cave_vlname (live)", CAVE_NAME, rd(CAVE_NAME, len(cave_name)))
            print(f"[dis  ] data   (live) {rd(CAVE_DATA, len(data_blob)).hex(' ')}")
            for va, _o, _n, desc, _p in patches[1:]:
                print(f"[dis  ] {va:08X} {rd(va, len(_n)).hex(' '):<40} {desc}")
            print()

    applied = all(rd(va, len(new)) == new for va, _o, new, _d, _p in patches)
    pristine = all(rd(va, len(orig)) == orig for va, orig, _n, _d, _p in patches)

    # Is the reserved cave block ours? The two hooks point INTO it, and both values are
    # independent of MAX_LEVEL / COST_EACH / SUFFIXES, so this still recognises a block written by
    # a DIFFERENT tune of this same script -- which is what lets both --apply and --undo work
    # in place after a constant changes. See the long note in the apply branch.
    hooks_ours = (rd(VMT_SLOT, 4) == struct.pack("<I", CAVE_NAME)
                  and rd(COST_RUN, len(cost_new)) == cost_new)
    live_blk = rd(CAVE_COSTS, CAVE_BLOCK)

    # ------------------------------------------------------------------ undo
    if UNDO:
        if pristine:
            if not quiet:
                print("[= ] not applied -- nothing to undo")
            return True
        # Anything this script wrote under DIFFERENT constants is still ours to undo -- see the
        # `ours` predicates. Without that, undoing a re-tuned install is impossible without first
        # restoring the exact constants it was applied with.
        bad = [f"{va:08X} ({d})" for va, o, n, d, _p in patches
               if rd(va, len(n)) != n and rd(va, len(o)) != o and not ours(va, rd(va, len(n)))]
        if bad:
            print("[x] mixed state, refusing to undo:\n     " + "\n     ".join(bad))
            return False
        if not quiet and any(rd(va, len(n)) != n and ours(va, rd(va, len(n)))
                             for va, _o, n, _d, _p in patches):
            print("[re ] installed with different constants (a re-tune) -- undoing it anyway")
        if not commit:
            print("[dry] undo verified: every site still holds bytes this script wrote")
            return True
        # Log AFTER the write lands, not before: these lines describe the file on disk, and
        # printing them up front made a failed write look like eight successful ones.
        done = []
        for va, orig, new, desc, _p in patches:
            if rd(va, len(new)) != new and not ours(va, rd(va, len(new))):
                continue
            o = va2off(va)
            data[o:o + len(orig)] = orig
            done.append(f"[u ] {va:08X} {desc}")
        try:
            open(path, "wb").write(data)
        except PermissionError:
            print("[x] LOCKED -- close AoW.exe / AoWCompat.exe / AoWDevEd.exe (nothing written)")
            return False
        print("\n".join(done))
        print("[ok] surgically undone: hook sites restored, caves zeroed, no backup touched")
        return True

    # ------------------------------------------------------------------ apply
    # The reserved block must be free (all zero), already exactly ours, or OURS FROM A PREVIOUS
    # TUNE. ⚠ That third case is what makes CLAUDE.md's "rewrite the caves in place, never
    # revert-and-re-apply" rule actually hold. Requiring zero-or-identical looks safe but bricks
    # the documented re-tune: change MAX_LEVEL, --apply, and the installed cave is neither zero
    # nor the new bytes, so it aborts -- and --undo aborts too, because the new script's cave
    # bytes no longer match what is installed. Recovery then needs the OLD MAX_LEVEL restored
    # first, which is precisely the revert-and-re-apply dance the rule forbids. (Measured: apply
    # at 9, set MAX_LEVEL=10, --apply -> "[x] cave zone 55817000 not free".)
    #
    # Ownership test is `hooks_ours`, computed above: the two hooks point INTO this block, and no
    # other feature could be holding those values.
    if live_blk != cave_blob and any(live_blk) and not hooks_ours:
        print(f"[x] cave block {CAVE_COSTS:08X}..{CAVE_COSTS + CAVE_BLOCK:08X} is not free and the "
              f"hooks do not point into it -- another feature may own it:\n"
              f"     {live_blk[:32].hex(' ')} ...")
        return False
    retune = any(rd(va, len(n)) not in (o, n) and ours(va, rd(va, len(n)))
                 for va, o, n, _d, _p in patches)
    if retune and not quiet:
        print(f"[re ] already installed with different constants -- rewriting in place "
              f"(re-tune; no revert needed, whole {CAVE_BLOCK} B cave block is replaced)")
    if applied:
        if not quiet:
            print("[= ] already applied -- chain intact")
        return True
    ok = True
    for va, orig, new, desc, _p in patches:
        cur = rd(va, len(new))
        if cur != orig and cur != new and not ours(va, cur):
            ok = False
            print(f"[!] {va:08X} ({desc})\n     exp {orig.hex(' ')}\n     got {cur.hex(' ')}")
    if not ok:
        print("[x] mismatch -- not written")
        return False
    if not commit:
        print("[dry] originals verified, cave block "
              + ("ours, will be rewritten in place" if retune else "free"))
        return True
    bp = os.path.join(BACKUP_DIR, os.path.basename(path) + SUFFIX)
    # ⚠ On a re-tune the current file is ALREADY PATCHED, so a backup taken now would be a
    # `.pre-vision9` holding a patched state -- the trap CLAUDE.md warns about. Only ever back up
    # from an unpatched file.
    if not retune and not os.path.exists(bp):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, bp)
        print(f"[bak] {bp}")
    done = []
    for va, orig, new, desc, _p in patches:
        o = va2off(va)
        data[o:o + len(new)] = new
        done.append(f"[w ] {va:08X} {desc}")
    try:
        open(path, "wb").write(data)      # log only once the bytes are actually on disk
    except PermissionError:
        print("[x] LOCKED -- close AoW.exe / AoWCompat.exe / AoWDevEd.exe (nothing written)")
        return False
    print("\n".join(done))
    return True


DLL = os.path.join(GAME, "AoWEPACK.dpl")
print()
want = DESC_OLD if UNDO else DESC_NEW
want_cost = COST_PREV if UNDO else COST_EACH   # undo restores what was INSTALLED, not vanilla
WRITE = APPLY or UNDO

# ---- phase 1: verify BOTH files. Nothing is written, so a problem in either aborts the run with
# the install exactly as it was. pfs_plan is pure and rebuilds the whole file in memory, so the
# length-changing rewrite is fully proven here -- including its collateral check -- before phase 2.
pfs_ok, _ = process_pfs(want, want_cost, commit=False)
if not pfs_ok:
    print("\n[!] Ability.pfs cannot be rewritten safely -- AoWEPACK.dpl left alone.")
    sys.exit(1)
if not process(DLL, commit=False):
    print("\n[!] AoWEPACK.dpl did not verify -- nothing written, Ability.pfs left alone.")
    sys.exit(1)
if not WRITE:
    print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first.")
    sys.exit(0)

# ---- phase 2: commit. Ability.pfs goes FIRST. It is the only length-changing write and the only
# one that can fail for a reason phase 1 cannot see (a lock taken between the two phases), so it
# should fail while the DLL is still untouched. A failure BETWEEN the two halves still leaves the
# install inconsistent, so say which file was written rather than printing a flat "not applied" --
# both halves are idempotent, so re-running the same command finishes the job.
written = []
ok, wrote = process_pfs(want, want_cost, commit=True, quiet=True)
if wrote:
    written.append("Release/Ability.pfs")
if ok:
    ok = process(DLL, commit=True, quiet=True)
    if ok:
        written.append("AoWEPACK.dpl")

if ok:
    print("\n[done] Undone: DLL sites restored + caves zeroed, Ability.pfs description restored."
          if UNDO else
          "\n[done] Applied to AoWEPACK.dpl + Release/Ability.pfs. "
          "Revert: build_vision9.py --undo (surgical, both files).")
elif written:
    print(f"\n[!] HALF-{'UNDONE' if UNDO else 'APPLIED'} -- wrote {', '.join(written)}, then "
          f"failed before finishing.\n"
          f"    The install is INCONSISTENT. Re-run the same command to complete it; both halves "
          f"are idempotent,\n    so finishing is safe and nothing is written twice.")
else:
    print("\n[!] nothing was written -- the install is unchanged.")
sys.exit(0 if ok else 1)
