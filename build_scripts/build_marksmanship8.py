#!/usr/bin/env python3
r"""
AoW1 mod -- Marksmanship becomes an 8-level ability. Curve and cost are UNCHANGED.

  levels I..VIII       (was I..IV)
  ATK  +level          (unchanged: the installed formula is already `add bl, al`)
  DMG  +level/2        (unchanged: the installed formula is already `shr eax,1`)
  cost 6 skill points per level, 48 to reach VIII   (unchanged per level)

Marksmanship is ability id 0x20, class `TMarksmanshipAbility : TMultiLevelAbility : TAbility`.

THE CENTRAL FINDING, AND WHY THIS SCRIPT IS SMALL
  Vanilla computed both bonuses with 4-rung `dec eax / jz` LADDERS, which would have had to be
  rewritten to reach level 8. This install does not: a PRE-EXISTING Ziggurat rework (owned by no
  build script -- it predates the note-taking convention) already replaced both ladders with
  ARITHMETIC, and arithmetic generalises for free.

      site                                   vanilla                    live (Ziggurat)
      TRangedAttackAbility.GetAttackRA       ladder +1/+1/+2/+2         call 0x5580C240 -> `add bl,al`
        @0x5576E65C                                                     ( = +level )
      TRangedAttackAbility.GetDamageRA       ladder +0/+1/+1/+2         `shr eax,1; add ebx,eax`
        @0x5576E614                                                     ( = +level/2 )

  So levels V..VIII already produce +5..+8 ATK and +2/+3/+3/+4 DMG with NO consumer change. This
  script therefore touches neither function. Both are left exactly as found.

  ⚠ Corollary for anyone re-tuning the curve later: 0x5580C240 is an UNOWNED cave. A script that
  wants to change the curve must verify against the LIVE bytes, not against Ghidra's vanilla image,
  which still holds the ladder. (Same trap build_vision9.py hit with `add esi,4` vs `add esi,3`.)

  ⚠ 0x5580C240 also carries the Cave/Depths -2 malus, gated on Night Vision (0x27). That is why
  `test al,al / jz` at 0x5576E678 is NOP'd in the live file: the malus must apply to units that do
  NOT have Marksmanship, so the has-ability test cannot be allowed to skip the call. Do not
  "repair" that NOP. (GetAbilityLevel returns 0 for a non-carrier, so `add bl, 0` is a no-op and
  the arithmetic is still correct.)

SCOPE -- one DLL, one data file. Verified with re_tools/abquery.py on all four modules: id 0x20 is
queried at exactly TWO sites, both in AoWEPACK.dpl (the two above). AoWTCPCK.dpl, aowInt.dpl and
AoW.exe contain no query at all, so there is NO exe patch and NO AoWCompat lockstep.

Both queries use the ITEM-AWARE VMT pair (+0x148 GetAbilityEnabled / +0x144 GetAbilityLevel) --
build_useitems.py switched them from the self-only pair. Untouched here. `GetSuperlativeAbOwner`
takes a MAX not a sum, so an item cannot stack on top of an innate level.

⚠ CORRECTION 2026-08-28 -- an earlier version of this paragraph said "it means an item-granted
Marksmanship level works". It is VACUOUS: censusing BOTH item tables -- `Release/ITEMS.PFS` (83
records) and the mod's own item library `User/Zig.ail` (325 records) -- **no item grants
Marksmanship 0x20 at all**. It would in any case only hold for an item carrying an `id+0x32`
ability sub-record; a bits-only grant has the ability with no level and resolves through the item
leg at level 0 (vanilla Crown of Kings / Leadership is the shipped example). Ziggurat does author
these records routinely -- 61 Zig.ail items carry 76 of them, levelling Spell Casting 0x34,
Vision 0x40, Leadership 0x2E and four enchantment ids -- so if a Marksmanship item is ever added,
give it the sub-record. Making the queries item-aware fixed the QUERY half only; the LEVEL half is
data, authored per item. See Investigation_Items.md §3.3d.

THREE PATCHES + ONE CAVE BLOCK in AoWEPACK.dpl, and one length-changing field rewrite in
Release/Ability.pfs.

A. CAP 4 -> 8.  `TMarksmanshipAbility.Create` @0x557BBCF8 seeds the ceiling:
       557BBD60  c7 46 28 04 00 00 00     mov dword [esi+0x28], 4
   `TMultiLevelAbility.CanExpand` @0x55765308 is the ONLY gate --
       55765334  cmp eax, [ebx+0x28] / jl -- comparing GetInherentLevel (VMT +0x94),
   and TMarksmanshipAbility declares no CanExpand of its own, so raising this one immediate raises
   the ceiling everywhere. No .reloc entry covers the site (verified by parsing .reloc).

B. PER-LEVEL COST LIST.  `[ability+0x2C]` is a TIntegerList of per-level expand costs; the ctor
   Puts cost[1..4] in four identical 18-byte blocks at 0x557BBD67..0x557BBDAF (72 B, no relocs).
   `Engine.TIntegerList.Get` is bounds-checked and returns the list's default rather than raising,
   so levels 5..8 would silently cost ZERO skill points -- a balance defect, not a crash, which is
   exactly the kind that ships. `TIntegerList.Put` auto-grows via SetCount, so eight Puts work
   exactly like four. The whole 72-byte run is replaced with a jump to `cave_mcosts`, which loops
   Put(list, 1..8, COST_EACH) and jumps back to 0x557BBDAF.

   ⚠ FOR A MULTI-LEVEL ABILITY THE DLL IS AUTHORITATIVE, NOT Ability.pfs tag 6.
   `TAbility.ExpandCost` @0x5574E908 returns tag 6, but `TMultiLevelAbility.ExpandCost` OVERRIDES
   it and reads this list. Tag 6 is inert for cost; it is kept in step only so the Ziggurat Manual
   (which reads tag 6 for its "Hero cost" column) does not print a number the game never charges.
   Here both are already 6, so tag 6 is written unchanged.

C. LEVEL NAMES V..VIII.  `TMarksmanshipAbility.GetLevelName` @0x557BBDEC does
       557BBE04  cmp edx, 4
       557BBE07  ja  0x557BBEE6
   -- and 0x557BBEE6 is the SEH TEARDOWN, not a default arm, so level >= 5 returns with the out
   string never assigned (renders empty). Both the unit info card and the hero level-up dialog
   route through VMT +0x10C (`TMultiLevelAbility.GetName` @0x55765298 and `ExpandName`
   @0x557652BC -- the latter names level+1, so an empty name would show up in the buy dialog
   before anyone even owns Marksmanship V).

   !! DO NOT extend the existing jump table.  `jmp dword [edx*4 + 0x557BBE14]` looks trivially
   repointable, but ALL FIVE entries (0x557BBE14/18/1C/20/24) carry .reloc entries; a cave-hosted
   replacement table would have none and every entry would go stale the moment the package
   rebases. Instead we repoint the VMT SLOT, which is itself relocated:
       TMarksmanshipAbility VMT base 0x557B7144, slot +0x10C = 0x557B7250
   -- verified to be the ONLY reference to 0x557BBDEC anywhere in the module, and it carries a
   .reloc entry, so changing the VALUE keeps the loader fixing it up after the rebase.
   (⚠ The VMT base is the `PassiveAb..TMarksmanshipAbility` symbol at 0x557B7144, NOT
   `PassiveAb.TMarksmanshipAbility` at 0x557B7270 -- the latter is 0x12C further on and every slot
   number computed from it is wrong.)

   `cave_mlname` (EAX=self, EDX=level, ECX=out:PAnsiString):
       level 0..4    -> tail-`jmp` the original, byte-for-byte vanilla behaviour
       level 5..8    -> call the original with level 0 to get the translated bare "Marksmanship",
                        then @LStrCat3 a suffix onto it
       level >= 9    -> tail-`jmp` the original with level forced to 0, so an out-of-range query
                        yields the bare name instead of the current unassigned (empty) string
   Calling the original with level 0 is how build_leadership4.py's cave_lsname and
   build_vision9.py's cave_vlname get the base name, and it is the reason this cave needs no
   absolute reference to the resourcestring record: arm 0's `mov eax,[0x558E9498]` is an absolute
   memory ref that CANNOT be replicated in a position-independent cave, but the arm-0 call reaches
   it through already-relocated code.

   The original preserves EBX and EBP and clobbers EAX/ECX/EDX; the cave saves and restores
   EBX/ESI/EDI/EBP, so it is strictly more conservative than what it replaces.

   SUFFIX LITERALS.  The game's own " I".." IV" live at 0x557BBF18/24/30/40 as Delphi const
   AnsiStrings (refcount -1 at ptr-8, length at ptr-4). " V" also exists at 0x5576DE04
   (TSpellCastingAbility's), and build_vision9.py minted " V".." IX" at 0x558170DC..0x55817114.
   We mint our OWN four rather than borrowing either:
     - 0x5576DE04 belongs to a class this project actively patches;
     - ⚠ Vision's literals sit inside the block build_vision9.py RESERVES and ZEROES on --undo, so
       borrowing them would make `build_vision9.py --undo` silently blank Marksmanship's level
       names. Four literals cost 56 bytes; a cross-feature dependency costs a debugging session.
   A const string is refcount -1 and never written, so a read+execute CODE cave is a valid home.

RAISING MAX_LEVEL AGAIN -- the Ability.pfs u8 directory is the wall, and 8 is the last value
  There is no arithmetic ceiling here (unlike Vision, whose sight had to fit the [army+0x29]
  nibble): the ATK bonus lands in BL added to a base of well under 100, and to-hit is
  clamp(50+10*(atk-def),10,90), so a large value saturates rather than wrapping.

  The real wall is record 42's body directory in Ability.pfs. Its offsets are single bytes, and
  every extra level adds a 21-byte `Level N (At+N/Dm+M)\r\n` line to tag 5, pushing tags 6/7/8/9
  further down. Measured, not reasoned (tag-9 offset = len(description) + 16):

    MAX_LEVEL   description   tag-9 dir offset   outcome
        4  (was)     143            159          ok
        8  (now)     227            243          ok -- 12 bytes of headroom left
        9            248            264          ABORTS -- u8 ceiling, in pfs_plan

  THE ESCAPE IS REAL AND CHEAP if a 9th level is ever wanted: the format supports wide (u32)
  directory entries and 25 records in this very file already use them (32, 67, 68, 71, ...);
  alternatively, drop the per-level enumeration for a one-line curve as build_vision9.py did,
  which removes the growth entirely. pfs_plan aborts with that instruction rather than truncating.

D. DESCRIPTION -- Release/Ability.pfs record 42 (= ability id 0x20 + 10), tag 5. The info card's
   text enumerates the curve for four levels; it is regenerated for eight from the SAME formula
   the code uses (At+level / Dm+level//2), so it cannot drift from MAX_LEVEL. Header sentence,
   single-space `Level N (At+A/Dm+D)` layout and trailing CRLF are all preserved exactly as the
   installed text has them.

   This is a LENGTH-CHANGING .pfs write. The machinery (and its three traps: the u32- not
   u8-prefixed string, the last record's body swallowing the trailing CRC, and the u8 body
   directory) is build_vision9.py's, proven there in both the grow and the shrink direction. The
   rewrite derives the index layout from the file, shifts the record offsets that sit after
   record 42, repairs the CRC, then re-parses the result and asserts that all 151 records still
   parse, that the other 150 are byte-identical, and that record 42 still carries exactly tags
   {5,6,7,8,9} with 7/8/9 unchanged. That check runs during the DRY RUN too, so a rewrite that
   would damage the file is caught before --apply.

BALANCE -- nothing existing gets stronger
  Unit data is NOT rescaled and must not be: Unitres.pfs assigns Marksmanship to 82 units topping
  out at IV (51 reach II, 16 III, 15 IV), HEROES.PFS gives it to 9 hero chassis at level I, and no
  item carries it. Nothing in the shipped data exceeds IV, so every existing holder behaves exactly
  as before. Levels V..VIII are pure headroom for hero purchases (6 points each) and editor
  assignment. Ability.pfs tag 9 = 0x381 already carries astHeroUpgrade (0x100) and astEditor
  (0x200), so both paths offer the new levels with no mask change.

CAVE ADDRESSES
  ⚠⚠ THIS FEATURE RESERVES 0x55817400..0x55817800 (1024 B). DO NOT ALLOCATE INSIDE IT.
  Content is only ~264 B, but the block is written and zeroed AS ONE UNIT -- that is what makes a
  shrinking re-tune leave no stale bytes, and it is why the whole range must stay ours. The
  ownership test is the two hooks (VMT slot -> CAVE_NAME, ctor jmp -> CAVE_COSTS) pointing into
  the block; it does not inspect the block's contents, so anything a future feature parks in the
  reserved range WILL be silently overwritten on --apply and zeroed on --undo.

  ⚠ It starts at 0x55817400 precisely because build_vision9.py reserves 0x55817000..0x55817400
  immediately below. Measured 2026-08-15 on the live file: 0x55817400..0x55817800 is entirely
  zero, carries 0 .reloc entries and 0 inbound references of any kind. Zone freeness is
  re-asserted at write time.

POSITION INDEPENDENCE
  The .dpl always rebases, so no cave may contain an un-relocated absolute reference. cave_mcosts
  is rel32-only. cave_mlname needs the addresses of its own suffix table and literals, so it
  computes the LOAD DELTA with the standard call/pop trick (`call _n; pop ebp; sub ebp, <link addr
  of _n>`) and indexes `[ebp + edx*4 + SUF_TAB]`; the stored dwords are link-time VAs to which the
  same delta is added. Every call out (original GetLevelName, TIntegerList.Put, LStrCat3, LStrClr)
  is rel32.

RE-TUNING
  Change MAX_LEVEL / COST_EACH / SUFFIXES and re-run --apply. Do NOT revert first: there is no
  snapshot layer at all, and --undo is the only revert path. Both halves rewrite IN
  PLACE -- the caves verify against either the installed bytes or the new ones and assert the
  growth zone is still zero, and the description is matched by SHAPE (a header plus a
  `Level N (At+A/Dm+D)` run counting from 1) rather than by exact string, so --apply and --undo
  both work from any tune this script could have produced.

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
SUFFIX = ".pre-marksmanship8"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)


def require(cond, msg):
    """A guard that `python -O` CANNOT strip.

    ⚠ Do not write these as `assert`. Every guard here exists to turn a silently-wrong patch into a
    loud abort -- a mis-sized cave, a keystone encoding that moved, a directory offset that
    overflows its byte. `-O` removes `assert` outright, and a stripped guard does not fail: it
    writes a broken file that loads and then misbehaves.
    """
    if not cond:
        raise SystemExit("ABORT: " + msg)

# ---------------------------------------------------------------- tunables
MAX_LEVEL = 8           # ability ceiling  (vanilla and installed: 4)
COST_EACH = 6           # skill points per level -- UNCHANGED, author instruction 2026-08-15
COST_PREV = 6           # what was installed BEFORE this feature, and what --undo restores.
# Cost is deliberately untouched, so these are equal. Kept as two names anyway: build_vision9.py's
# COST_PREV exists because Ziggurat had retuned the cost before that feature was written, and the
# same could become true here. If COST_EACH is ever changed, COST_PREV must stay at what is
# actually installed today, or --undo becomes a silent extra edit dressed up as a revert.
SUFFIXES = (" V", " VI", " VII", " VIII")     # names for levels 5..MAX_LEVEL

# Release/Ability.pfs record 42 tag 5, the in-game description. GENERATED from the same curve the
# code implements, so it cannot drift from MAX_LEVEL.
DESC_HEAD = "Gives the unit increased proficiency with ranged attacks.\r\n"


def atk_bonus(level):
    """`add bl, al` in the cave at 0x5580C240 -- the attack bonus IS the level."""
    return level


def dmg_bonus(level):
    """`shr eax,1; add ebx,eax` in GetDamageRA @0x5576E614 -- floor(level / 2)."""
    return level // 2


def desc_enumerated(levels):
    """The installed shape: header sentence + one `Level N (At+A/Dm+D)` line per level.

    ⚠ SINGLE space before the bracket. Vision's record uses a double space; this one does not, and
    the difference is load-bearing -- desc_shape() has to match the text that is actually on disk
    or the very first dry run refuses to touch a file it wrote itself.
    """
    return DESC_HEAD + "".join(
        "Level %d (At+%d/Dm+%d)\r\n" % (i, atk_bonus(i), dmg_bonus(i))
        for i in range(1, levels + 1))


DESC_OLD = desc_enumerated(4)              # what is installed today: 4 levels
DESC_NEW = desc_enumerated(MAX_LEVEL)      # ours: 8 levels, same curve


def desc_shape(text):
    """Truthy if `text` is a description THIS SCRIPT COULD HAVE WRITTEN, else None.

    Returns [(level, atk, dmg)]; callers only test truthiness, and that list is non-empty for any
    real curve.

    ⚠ Why a shape test and not `text in (DESC_OLD, DESC_NEW)`: DESC_NEW is derived from MAX_LEVEL,
    so an exact-match guard makes the documented re-tune impossible. Apply, change MAX_LEVEL,
    --apply -> the installed text matches neither constant and phase 1 refuses; --undo refuses for
    the same reason, so recovery needs the OLD value put back first. That is exactly the "rewrite
    in place, never revert-and-re-apply" rule from CLAUDE.md, applied to a .pfs field.

    ⚠ ONE arm today, because this script has only ever emitted one format. WHENEVER THE EMITTED
    FORMAT CHANGES, KEEP THE PREVIOUS ARM -- a real install can be carrying it, and dropping the
    arm strands exactly those installs: --apply AND --undo both refuse and the only recovery is
    editing this file. build_vision9.py carries three arms for precisely that reason.

    ⚠ `not shape`, never `shape is None`: header-only text parses as a well-formed run of ZERO
    levels and returns [], which is not None. This script cannot emit that, so it could only
    arrive as a hand-edit -- which is what the guard is for.
    """
    if not text.startswith(DESC_HEAD):
        return None
    rest = text[len(DESC_HEAD):]
    if rest and not rest.endswith("\r\n"):
        return None
    out = []
    for i, line in enumerate(rest.split("\r\n")[:-1] if rest else [], start=1):
        m = re.fullmatch(r"Level (\d+) \(At\+(\d+)/Dm\+(\d+)\)", line)
        if not m or int(m.group(1)) != i:
            return None
        out.append((i, int(m.group(2)), int(m.group(3))))
    return out


require(len(SUFFIXES) == MAX_LEVEL - 4, "need one suffix per level 5..%d" % MAX_LEVEL)
require(desc_shape(DESC_NEW) and desc_shape(DESC_OLD),
        "desc_shape() rejects this script's own output -- the generator and the matcher disagree")

# ---------------------------------------------------------------- addresses (verified on the live DLL)
CAP_SITE  = 0x557BBD60   # mov dword [esi+0x28], 4      (7 B: C7 46 28 04 00 00 00)
COST_RUN  = 0x557BBD67   # first of four 18-byte Put blocks
COST_END  = 0x557BBDAF   # `xor eax, eax` -- where the ctor resumes (SEH teardown)
PUT_FN    = 0x55702EB4   # AoWEPACK thunk -> EngineP.dpl!Engine.TIntegerList.Put (EAX,EDX,ECX)
VMT_SLOT  = 0x557B7250   # TMarksmanshipAbility VMT +0x10C (GetLevelName); vmt base 0x557B7144
ORIG_NAME = 0x557BBDEC   # TMarksmanshipAbility.GetLevelName
LSTRCAT3  = 0x55701190   # System.@LStrCat3 (EAX=dest, EDX=s1, ECX=s2)
LSTRCLR   = 0x55701140   # System.@LStrClr  (EAX=&str)

COST_LEN = COST_END - COST_RUN            # 72
require(COST_LEN == 0x48, "the ctor Put run is %d B, expected 0x48" % COST_LEN)

# ---------------------------------------------------------------- cave block
CAVE_COSTS = 0x55817400
CAVE_NAME  = 0x55817440
CAVE_DATA  = 0x558174C0                   # suffix pointer table, then the literals
SUF_TAB    = CAVE_DATA
LIT_BASE   = CAVE_DATA + 4 * len(SUFFIXES)
VISION_BLOCK_END = 0x55817400             # build_vision9.py owns 0x55817000..here
require(CAVE_COSTS >= VISION_BLOCK_END,
        "cave block would overlap build_vision9.py's reserved 0x55817000..0x55817400")


def rel32(src, dst):
    return struct.pack("<i", dst - (src + 5))


# ---------------------------------------------------------------- cave_mcosts
# Entered from the ctor with ESI = self (the ability) and EBX = the @ClassCreate flag that the
# epilogue later reads as `test bl, bl`. Vanilla clobbers EAX/EDX/ECX here and relies on ESI and
# EBX surviving; EDI is ours to borrow as long as we give it back.
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

# ---------------------------------------------------------------- cave_mlname
# Replaces TMarksmanshipAbility.GetLevelName via the VMT. EAX=self, EDX=level, ECX=out:PAnsiString.
# EBP holds the load delta for the 5..MAX_LEVEL branch. `push 0` makes a nil PAnsiString temp on
# the stack; the original writes the bare translated name into it, LStrCat3 appends the suffix into
# the caller's out slot, LStrClr releases the temp.
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
require(len(cave_name) == len(_p1), "cave_mlname shifted between passes -- LINK_N is wrong")
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
# Rebuilt from COST_EACH so --undo restores exactly what was displaced (the INSTALLED value).
cost_orig = b"".join(
    b"\xB9" + struct.pack("<I", COST_PREV)          # mov ecx, COST_PREV
    + b"\xBA" + struct.pack("<I", lvl)              # mov edx, lvl
    + b"\x8B\x46\x2C"                               # mov eax, [esi+0x2c]
    + b"\xE8" + rel32(COST_RUN + (lvl - 1) * 18 + 13, PUT_FN)
    for lvl in (1, 2, 3, 4))
require(len(cost_orig) == COST_LEN,
        "rebuilt Put run is %d B, expected %d" % (len(cost_orig), COST_LEN))
cost_new = b"\xE9" + rel32(COST_RUN, CAVE_COSTS) + b"\x90" * (COST_LEN - 5)

# ---------------------------------------------------------------- layout guards
require(len(cave_costs) <= CAVE_NAME - CAVE_COSTS, "cave_mcosts overruns cave_mlname")
require(len(cave_name) <= CAVE_DATA - CAVE_NAME, "cave_mlname overruns the data block")
CAVE_TOP = CAVE_DATA + len(data_blob)

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
# A LENGTH-CHANGING .pfs write -- the field grows 143 -> 227 bytes and the record 172 -> 256 -- so
# every index offset downstream of record 42 has to be rebuilt and the trailing CRC repaired. The
# machinery is build_vision9.py's, proven there in both directions.
#
# ⚠ Tag 5 is a u32-LENGTH-PREFIXED Delphi string, NOT the u8 Pascal form `pfs.pstr()` assumes.
#   The field is `<u32 len><len bytes latin-1>`; 4 + 143 == 147 exactly, which is how it was
#   confirmed on this record.
#
# ⚠ The LAST record's body swallows the file's 4-byte trailing CRC -- `parse_index` gives it
#   `d[start:len(d)]`. Harmless for a byte-splice rewrite like this one, but any "did any other
#   record change?" comparison must strip those 4 bytes or it reports a false positive.
#
# ⚠ Record-body directory offsets are u8 when the body uses SMALL entries. Record 42's largest
#   offset goes 159 -> 243 against a 255 ceiling; it fits, but only just (see "RAISING MAX_LEVEL
#   AGAIN" in the header), so it is asserted rather than assumed.
ABIL_PFS = os.path.join(GAME, "Release", "Ability.pfs")
PFS_RESIDUE = 0x2144DF1C      # crc32(d[4:]) of an intact file -- see PFS_Format_CRC.md
PFS_REC = 0x20 + 10           # Ability.pfs record id = ability id + 10  -> 42
PFS_RECORD_COUNT = 151
PFS_DESC_TAG = 5
PFS_COST_TAG = 6          # inert for cost on a multi-level ability; kept in sync for the manual


def _pfs_mod():
    """Load re_tools/pfs.py relative to THIS SCRIPT, not to GAME.

    ⚠ `AOW_GAME_DIR` points at a game install to patch; the toolkit travels with the script.
    Resolving the parser under `GAME` breaks the moment the script is pointed at a throwaway copy,
    which is exactly how it gets tested. Same rule as `TOOLS` in re_tools/*.py.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "pfs", os.path.join(here, "..", "re_tools", "pfs.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pfs_index_layout(d):
    """(payload_base, [(record_id, offset, offset_field_pos, field_width)]) for the file index.

    Derived from the bytes -- AoWDevEd rewrites this file whole when the author saves a map and
    every offset in it moves, so nothing here may be hard-coded. Mirrors re_tools/pfs.py:
    parse_index, but also reports WHERE each offset lives so it can be rewritten.
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
    None answer must read as "not the text you asked about" rather than a traceback.
    """
    try:
        pfs = _pfs_mod()
        cur = pfs.parse_dir(dict(pfs.parse_index(d))[PFS_REC], top=False)[PFS_DESC_TAG]
        n = struct.unpack_from("<I", cur, 0)[0]
        return cur[4:].decode("latin-1") if 4 + n == len(cur) else None
    except (ValueError, IndexError, KeyError, struct.error):
        return None


def pfs_plan(d, want_text, want_cost):
    """Pure: (status, new_bytes, note). Never writes. status in {'same', 'ok', 'error'}."""
    # Integrity gate. It lives HERE rather than only in the caller so the pure function fails closed
    # for any future caller. What it actually buys, stated honestly:
    #   CATCHES  incoherent damage -- a flipped payload byte, a truncated file: anything whose bytes
    #            no longer match the stored CRC.
    #   MISSES   a coherent-but-wrong layout. Nudge a wide index offset AND re-repair the CRC and
    #            this plans `ok`. pfs_collateral cannot catch that either, because it parses the old
    #            and the new file with the same wrong offsets.
    # ⚠ Do NOT "strengthen" this by tiling body lengths backwards from EOF and comparing them to the
    #   index offsets. That check is CIRCULAR and can never fail: parse_index derives those lengths
    #   from the very offsets being checked. It was in build_vision9.py and build_drillmaster.py,
    #   passed a deliberate nudge, and was removed from both on 2026-08-09.
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        return "error", None, ("CRC residue is wrong before any edit -- the file is already "
                               "damaged; refusing to rewrite it")
    # ⚠ Both parsers PROBE for the index layout, so an unfamiliar file makes them raise rather than
    # return. That is a realistic input, not a hypothetical: AoWDevEd rewrites this whole file when
    # the author saves a map. A traceback here would be a bug report; return a readable error.
    try:
        pfs = _pfs_mod()
        recs = pfs.parse_index(bytes(d))
        base, ent = pfs_index_layout(bytes(d))
    except (ValueError, IndexError, KeyError, struct.error) as exc:
        return "error", None, (f"cannot parse the Ability.pfs index ({exc}) -- the file's layout is "
                               "not one this script recognises, so it will not be rewritten")

    # Two independent parses of the index must agree on the record list. This checks the layout
    # DISCOVERY (both probe for the wide-array start, separately), not the data -- data integrity
    # is the CRC above.
    if [a for a, _, _, _ in ent] != [r for r, _ in recs]:
        return "error", None, "index entry ids disagree with parse_index"

    bodies = dict(recs)
    if PFS_REC not in bodies:
        return "error", None, f"no record {PFS_REC} (ability {PFS_REC - 10:#04x}) in Ability.pfs"
    body = bodies[PFS_REC]
    off42 = dict((a, b) for a, b, _, _ in ent)[PFS_REC]
    a0 = base + off42

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
                f"MAX_LEVEL {MAX_LEVEL} makes the description too long for the small-entry form. "
                "Either convert this body to WIDE (u32) entries -- records 32/67/68/71 in this "
                "same file already use them -- or replace the per-level enumeration with a "
                "one-line curve, as build_vision9.py does.")
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
        if off <= off42:
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
                              f"{sum(1 for _r, o, _p, _w in ent if o > off42)} later "
                              f"offsets {shift:+d}, max body-dir offset "
                              f"{max(o for _t, o in new_dents)}/255")


def pfs_collateral(old_d, new_d, want_text, want_cost):
    """'' if the rewrite touched nothing but record PFS_REC, else a description of what moved."""
    pfs = _pfs_mod()
    o = pfs.parse_index(old_d)
    n = pfs.parse_index(new_d)
    if [r for r, _ in o] != [r for r, _ in n]:
        return "record id list changed"
    if len(n) != PFS_RECORD_COUNT:
        return f"expected {PFS_RECORD_COUNT} records, got {len(n)}"
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
    # 7/8/9 must be untouched. 6 is checked against the value we MEANT to write, not against the
    # old one, because keeping it in step with the DLL is an intended edit even when (as here) the
    # two values happen to be equal.
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
        print(f"[pfs ] collateral check: {PFS_RECORD_COUNT}/{PFS_RECORD_COUNT} records parse, "
              f"{PFS_RECORD_COUNT - 1} byte-identical, record {PFS_REC} tags 7/8/9 unchanged, "
              f"tag 6 (hero cost) = {want_cost}, CRC residue {PFS_RESIDUE:#010X} OK")
        if DIS:
            for ln in want_text.rstrip("\r\n").split("\r\n"):
                print(f"         | {ln}")
    if not commit:
        return True, False
    # Back up only from an UNPATCHED file. ⚠ Two ways to mint a lying `.pre-marksmanship8` here, and
    # both produce the "a .pre-* file is not proof of anything" artefact CLAUDE.md warns about:
    #   1. the undo path: the current file is the PATCHED state;
    #   2. a RE-TUNE after the real backup has been pruned -- the current file is then our own
    #      8-level text, not the pre-feature original.
    # `cur_is_original` is the discriminator: desc_shape() deliberately accepts our own past output
    # as well as the installed text, so "it parses as a description we recognise" does NOT mean
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
    shape = desc_shape(want_text) or []
    print(f"[w ] Ability.pfs record {PFS_REC} tag 5: Marksmanship description -> "
          f"enumerated, {len(shape)} levels")
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

    # --- the two consumers must still be the ARITHMETIC form, or the curve is not what we costed --
    # This is the analogue of build_vision9.py's `add esi, 4` check. If an install carries VANILLA's
    # ladders, levels 5..8 would silently give +0 ATK and +0 DMG -- the ability would gain levels
    # that do nothing at all. Cheaper to refuse than to ship that.
    for va, want, who, what in (
            (0x5576E689, b"\xE8", "TRangedAttackAbility.GetAttackRA",
             "call 0x5580C240 (`add bl, al` -> ATK +level)"),
            # H9 (2026-08-24, DAM/HP doubling): the damage rider was retuned +level/2 -> +level by
            # NOPping the shr (see DamHP_Double_Decisions.md). Both generations are the arithmetic
            # form this feature relies on -- accept either.
            (0x5576E641, (b"\xD1\xE8\x01\xC3", b"\x90\x90\x01\xC3"), "TRangedAttackAbility.GetDamageRA",
             "`[shr eax,1|nop;nop]; add ebx,eax` (the DMG rider, either generation)")):
        wants = want if isinstance(want, tuple) else (want,)
        want = wants[0]
        if all(rd(va, len(w)) != w for w in wants):
            print(f"[x] {va:08X} ({who}) is not the arithmetic form this feature relies on.\n"
                  f"    expected {want.hex(' ')}  ({what})\n"
                  f"    got      {rd(va, len(want)).hex(' ')}\n"
                  f"    This install may carry VANILLA's 4-rung ladder, in which case levels 5..8 "
                  f"would grant NOTHING.\n    Re-derive the curve before applying.")
            return False
    if rd(0x5576E689 + 1, 4) != rel32(0x5576E689, 0x5580C240)[:4]:
        print(f"[x] 5576E689 calls {0x5576E689 + 5 + struct.unpack('<i', rd(0x5576E68A, 4))[0]:08X}, "
              f"not the expected marksmanship cave 5580C240 -- curve unverified, refusing.")
        return False

    # (va, original bytes, new bytes, description, ours)
    #
    # `ours(cur)` -> "cur is a value THIS SCRIPT wrote, just with different constants". Sites whose
    # new bytes depend on a tunable need it, or an in-place re-tune is impossible: at MAX_LEVEL 9
    # the installed cap `c7 46 28 08..` matches neither the original `04` nor the new `09`, so both
    # --apply and --undo would refuse. Sites whose bytes are constant (the rel32 hook, the VMT slot)
    # need nothing -- `orig`/`new` already cover them.
    anylevel = (lambda cur: cur[:3] == b"\xC7\x46\x28" and cur[4:] == b"\x00\x00\x00")
    patches = [
        (CAVE_COSTS, b"\x00" * CAVE_BLOCK, cave_blob,
         f"cave block {CAVE_BLOCK} B: cave_mcosts + cave_mlname + suffix table/literals",
         lambda cur: hooks_ours),
        (CAP_SITE, bytes.fromhex("c7462804000000"),
         b"\xC7\x46\x28" + struct.pack("<I", MAX_LEVEL),
         f"cap {CAP_SITE:08X}: [esi+0x28] = 4 -> {MAX_LEVEL}", anylevel),
        (COST_RUN, cost_orig, cost_new,
         f"ctor {COST_RUN:08X}: 4 inline Puts ({COST_LEN} B) -> jmp cave_mcosts", None),
        (VMT_SLOT, struct.pack("<I", ORIG_NAME), struct.pack("<I", CAVE_NAME),
         f"VMT+0x10C {VMT_SLOT:08X}: GetLevelName -> cave_mlname", None),
    ]

    def ours(va, cur):
        """True if `cur` at `va` is something this script wrote under different constants."""
        for pva, _o, _n, _d, pred in patches:
            if pva == va:
                return bool(pred and pred(cur))
        return False

    print(f"[curve] ATK +level, DMG +level/2 (UNCHANGED), levels 1..{MAX_LEVEL} (was 1..4)")
    print(f"        {'  '.join('%s:+%d/+%d' % (('I','II','III','IV','V','VI','VII','VIII','IX')[i-1], atk_bonus(i), dmg_bonus(i)) for i in range(1, MAX_LEVEL + 1))}")
    print(f"[cost ] {COST_EACH} skill points per level (unchanged), "
          f"{COST_EACH * MAX_LEVEL} total to reach level {MAX_LEVEL}")
    if not quiet:
        print(f"[verif] 5576E689 -> cave 5580C240 (`add bl,al`), 5576E641 `shr eax,1` -- "
              f"both consumers are the arithmetic form, so V..VIII need no code change")
        show("cave_mcosts", CAVE_COSTS, cave_costs)
        show("cave_mlname", CAVE_NAME, cave_name)
        print(f"[data ] {CAVE_DATA:08X} suffix table {[f'{v:08X}' for v in _ptrs]}")
        for s, v in zip(SUFFIXES, _ptrs):
            off = v - CAVE_DATA
            print(f"         {v:08X} refcnt={struct.unpack_from('<i', data_blob, off - 8)[0]:<3}"
                  f" len={struct.unpack_from('<I', data_blob, off - 4)[0]}  {s!r}")
        print(f"[cave ] block {CAVE_COSTS:08X}..{CAVE_TOP:08X} ({CAVE_TOP - CAVE_COSTS} B "
              f"used of {CAVE_BLOCK} reserved; build_vision9.py owns 55817000..55817400 below)")

        if DIS:
            print("\n[dis  ] --- as INSTALLED in the live file ---")
            show("cave_mcosts (live)", CAVE_COSTS, rd(CAVE_COSTS, len(cave_costs)))
            show("cave_mlname (live)", CAVE_NAME, rd(CAVE_NAME, len(cave_name)))
            print(f"[dis  ] data   (live) {rd(CAVE_DATA, len(data_blob)).hex(' ')}")
            for va, _o, _n, desc, _p in patches[1:]:
                print(f"[dis  ] {va:08X} {rd(va, len(_n)).hex(' '):<40} {desc}")
            print()

    applied = all(rd(va, len(new)) == new for va, _o, new, _d, _p in patches)
    pristine = all(rd(va, len(orig)) == orig for va, orig, _n, _d, _p in patches)

    # Is the reserved cave block ours? The two hooks point INTO it, and both values are independent
    # of MAX_LEVEL / COST_EACH / SUFFIXES, so this still recognises a block written by a DIFFERENT
    # tune of this same script -- which is what lets both --apply and --undo work in place after a
    # constant changes.
    hooks_ours = (rd(VMT_SLOT, 4) == struct.pack("<I", CAVE_NAME)
                  and rd(COST_RUN, len(cost_new)) == cost_new)
    live_blk = rd(CAVE_COSTS, CAVE_BLOCK)

    # ------------------------------------------------------------------ undo
    if UNDO:
        if pristine:
            if not quiet:
                print("[= ] not applied -- nothing to undo")
            return True
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
        # Log AFTER the write lands, not before: these lines describe the file on disk, and printing
        # them up front makes a failed write look like four successful ones.
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
    # revert-and-re-apply" rule actually hold: requiring zero-or-identical looks safe but bricks the
    # documented re-tune, because after changing MAX_LEVEL the installed cave is neither zero nor
    # the new bytes, so --apply aborts -- and --undo aborts too.
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
    # `.pre-marksmanship8` holding a patched state -- the trap CLAUDE.md warns about. Only ever back
    # up from an unpatched file.
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
          "Revert: build_marksmanship8.py --undo (surgical, both files).")
elif written:
    print(f"\n[!] HALF-{'UNDONE' if UNDO else 'APPLIED'} -- wrote {', '.join(written)}, then "
          f"failed before finishing.\n"
          f"    The install is INCONSISTENT. Re-run the same command to complete it; both halves "
          f"are idempotent,\n    so finishing is safe and nothing is written twice.")
else:
    print("\n[!] nothing was written -- the install is unchanged.")
sys.exit(0 if ok else 1)
