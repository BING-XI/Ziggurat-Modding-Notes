#!/usr/bin/env python3
r"""AoW1 mod -- "caster_cost": four bit-only hero abilities that halve the INITIAL CASTING COST
of one spell family each, plus the vanilla instant-cast raw-charge fix they depend on.

    Evoker    0xAC  -> the 30 registered TCombatSpell spells            (32 VMTs match)
    Conjurer  0xAD  -> the 13 registered TSummonSpell spells             (14 VMTs match)
    Enchanter 0xAE  -> the 18 registered TUnitSpell spells               (19 VMTs match)
    Ritualist 0xAF  -> the 12 registered TGlobalEnchantmentSpell spells  (13 VMTs match)

  The VMT counts exceed the spell counts because each family's ABSTRACT BASE carries the family
  constant too. Harmless: an abstract base is never registered, so no TSpell instance has it.

OUT OF SCOPE, deliberately: no damage change, no per-turn upkeep change, no research cost change,
no icons (AoW1 abilities have none anywhere in the UI), no level tables, no per-owner data record.
Only AoWEPACK.dpl is written; Ability.pfs records are minted by AoWDevEd (see OUT-OF-BAND below).

Spec: Modding Resources/Zig notes/Caster_Cost_Abilities_SPEC.md

================================================================================
ARCHITECTURE -- SIX SITES, FIVE CAVES
================================================================================
1. HOOK1  0x557894EC  THero.CastingMana ENTRY (7B)     -> cave_cost    classify + halve
2. HOOK2  0x55789510  the shared vanilla epilogue (5B) -> cave_floor   floor of 1, at the EXIT
3. HOOK3  0x557BCF04  a spare `call RegisterAbility`   -> cave_reg     register the four abilities
4. SITE A 0x557EFA7C  TGlobalEnchantmentSpell.Activate -> cave_gench   wallet fix
5. SITE B 0x557E44F8  TSummonSpell.Activate            -> cave_summon  wallet fix (validate band)
6. SITE C 0x557E4353  TSummonSpellTE.Process           IN-PLACE, no cave (wallet fix, the charge)

WHY THE ENTRY AND NOT 0x557894F8. build_mastery_cost.py owns 0x557894F8 and the function's TAIL
(its cave at 0x55812880 exits `jmp 0x55789510`). By 0x557894F3 the caster in EAX has already been
overwritten by `mov eax,[0x558FA040]`, and it is never spilled -- the only pushes are `53 56`. So a
caster-dependent discount cannot chain onto the mastery cave; it must be a PROLOGUE INSERT that
replays the displaced bytes and jumps back.

WHY THE FLOOR IS A SECOND HOOK. A floor applied in the prologue does NOT survive the function: the
mastery cave rescales EBX afterwards, and EBX=1 through its x0.75 arm gives (1*3)>>2 = 0. The exit
0x55789510 is the single convergence point (three arrivals, all targeting it exactly; no .reloc; no
absolute references), so the floor goes there. This also makes the two halves orthogonal to
build_mastery_cost.py: either feature can be undone without breaking the other.

WHY THE WALLET FIX IS PART OF THIS FEATURE, NOT AN EXTRA. THero.CastSpell takes an INSTANT branch
when CastingMana <= [hero+0x80]. On that branch the cost is re-read RAW from [spell+0x14], skipping
CastingMana entirely -- so a discount would show in the spellbook and never reach the wallet; and in
the band D <= P < R the spell is accepted by CastSpell and then REJECTED by TSpellTE.Validate on the
raw cost, i.e. it silently does nothing. At casting level 5 that is 3 summons + 4 global
enchantments doing nothing, and only 1 of 13 summons honouring the discount.

  ** THIS IS A VANILLA BUG. ** All three raw-read sites are byte-identical to
  AoWEPACK_original_backup.dpl, and vanilla applies the sphere-Mastery x2 inline INSIDE CastingMana
  (`call GetSphereManaDoubled` @0x5577E230 at 0x55789501, then `add eax,eax` at 0x5578950A) -- and
  GetSphereManaDoubled has EXACTLY ONE code caller, that site. So any path that skips CastingMana
  skips the multiplier too. Vanilla's x2 PENALTY makes the gate STRICTER than Validate's re-check,
  so the re-check can never trip and the only symptom is an uncharged penalty -- which is why 27
  years of players never noticed. A DISCOUNT pushes the gate the other way and turns the same latent
  defect into "the spell does nothing".

  Consequence the user signed off on: fixing it makes build_mastery_cost.py's x1.50/x0.75
  multiplier reach instantly-cast summons and global enchantments for the first time. (NOT
  vanilla's own x2 -- in the live build that code is unreachable: the mastery cave converges on
  `jmp 0x55789510` at 0x558128B8 and bypasses 0x557894FE..0x5578950E entirely.)

  cave_floor likewise repairs a live mastery_cost defect: Slow (1) and Ooze (1) cast with the
  matching Mastery currently return 0 mana -- free, and consuming no casting points either.

CLASSIFICATION -- rebase-invariant, needs NO PIC anchor. [VMT+0x6C] - [VMT+0x18] is a DIFFERENCE of
two slots, so the runtime load delta cancels. [VMT+0x18] is AoWE.TSpell.ReadWrite @0x55779234 for
all 117 classes in the subtree (exactly one distinct value), which independently proves no derived
class reads extra pfs tags. Combat needs a second test because its +0x6C constant (0x120) is shared
with the abstract TSpell itself. [VMT+0x80] - [VMT+0x18] == 0x7E034 occurs on 31 VMTs -- the
TCombatSpell base plus its 30 subclasses -- and, the property that actually matters, ZERO times
outside the spell subtree anywhere in the file.

ORDER OF OPERATIONS: base -> our halving -> mastery multiplier -> floor. Both truncate.

  TRIPWIRE, Water Mastery (spell 45, cost 250): it is the one global enchantment whose ExecuteTE
  @0x557F0A88 reads the RAW cost (`8b 4b 14`) instead of [TE+0x1C], so SITE A does not cover it.
  It is currently harmless only because 250 -> Ritualist 125 -> own-sphere Mastery 93 still exceeds
  the 90-point casting ceiling (0x5580BF2B `imul eax,eax,0x12`), so it can never take the instant
  branch. Lower its cost, raise the casting-points ladder, or add a second discount and the
  exemption flips into a 250-mana charge against a 93-mana preview. Re-check this if any of those
  three numbers changes.

  KNOWN RESIDUAL BAND, Cosmagic Scrying (spell 59, cost 15, an Enchanter member):
  TCosmeticSurgerySpellCaster.Cast @0x557E8524 pushes the raw cost at 0x557E85F9 rather than going
  through TUnitSpell.CastSpell, so at Spellcasting level 1 (10 casting points) 7 <= 10 < 15 -- the
  cast is accepted and then rejected by Validate, i.e. it does nothing. Empty from level 2 onward
  (20 >= 15). Fixable as a fourth wallet site if wanted; check .reloc on 0x557E85F9 first.

CAVE ZONE: 0x55820800..0x55820FFF EXCLUSIVE RESERVATION. Verified all-zero and .reloc-free before
allocation. Sits between build_los_terrain.py's ceiling (0x55820800) and build_dispelmagic5.py's
floor (0x55821000), touching neither.

  ** A zero run is not a reservation. ** It is a statement about a moment in time. Record a cave in
  the allocation map the day it is claimed, and never let --undo zero a rounded reservation -- that
  is exactly how build_magebane.py destroyed build_dispelmagic5.py's cave. --undo here zeroes only
  the emitted length of each cave.

Backup: AoWEPACK.dpl.pre-castercost
Dry-run by default; --apply to write; --undo to remove surgically; --dis to dump every cave.
"""
import os, sys, struct, shutil, subprocess

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-castercost")

# ---- engine addresses (preferred-base VAs) ------------------------------------------
CASTINGMANA   = 0x557894EC          # THero.CastingMana entry
CM_RESUME     = 0x557894F3          # just past the displaced 7 bytes
EPILOGUE      = 0x55789510          # mov eax,ebx; pop esi; pop ebx; ret
REG_SPLICE    = 0x557BCF04          # a spare `call RegisterAbility` in RegisterPassiveAbilities
REGISTERAB    = 0x55750238          # TAbilityControl.RegisterAbility
CREATEENH     = 0x5576601C          # CreateEnhancementAbility
GENCH_ACT     = 0x557EFA7C          # TGlobalEnchantmentSpell.Activate   raw read
GENCH_RESUME  = 0x557EFA83
SUMMON_ACT    = 0x557E44F8          # TSummonSpell.Activate              raw read
SUMMON_RESUME = 0x557E44FF
SUMMONTE_PROC = 0x557E4353          # TSummonSpellTE.Process             raw read (patched in place)

# ---- ability ids ---------------------------------------------------------------------
EVOKER, CONJURER, ENCHANTER, RITUALIST = 0xAC, 0xAD, 0xAE, 0xAF
ORDER = [EVOKER, CONJURER, ENCHANTER, RITUALIST]
NAMES = {EVOKER: "Evoker", CONJURER: "Conjurer", ENCHANTER: "Enchanter", RITUALIST: "Ritualist"}
FAMILY = {EVOKER: "combat spells", CONJURER: "summons",
          ENCHANTER: "unit enchantments", RITUALIST: "global enchantments"}
SEL_MASK   = 0x03FF                 # all ten TAbilitySelectionType bits; 0x100+0x200 are load-bearing

# ⚠⚠ THESE NUMBERS DO NOT REACH THE GAME. Kept only to document intent, and because the emitted
# `mov [eax+0x14],imm32` is already installed in a CONFIRMED-WORKING binary and is harmless.
#
# WHY (established 2026-08-27, from the user's in-game result and confirmed by decompile):
#   Ability level-up cost has TWO sources, and which one applies is decided by the ability's KIND:
#
#   * MULTI-LEVEL abilities (Leadership, Marksmanship, Dispel Magic, Spellcasting, ...) override
#     ExpandCost in their own class. AoWE.TDispelMagicAbility.ExpandCost @0x5576D130 is literally
#     `return 5`. Such an ability ignores [+0x14] AND Ability.pfs tag 6 entirely -- its cost is in
#     CODE, and code is the only place to change it.
#
#   * SINGLE-LEVEL / bit-only abilities (these four, Path of Sand, Drillmaster, ...) inherit
#     AoWE.TAbility.ExpandCost @0x5574E908, which is just `return [ability+0x14]`. And
#     AoWE.TAbility.ReadWrite @0x5574F07C hands the property reader the ADDRESS of that field for
#     tag 6 -- `(**(code **)(*tbl + 0x2c))(tbl, ability + 0x14, 6)` -- so the Ability.pfs load
#     writes straight into it AFTER registration. Absent tag => the field is set to 0.
#
#   So for a bit-only ability, writing [+0x14] in a registration cave is FUTILE: the pfs load always
#   wins, and with no tag 6 the ability ends up PERMANENTLY FREE (THero.UsedSkillPoints sums
#   ExpandCost). That is what happened here -- the four shipped reading 0 until they were given
#   tag 6 in AoWDevEd. Set the cost in DevEd. A future rebuild of cave_reg should drop the
#   `mov [eax+0x14]` instruction (7 bytes x 4); it is not removed now only because re-patching a
#   confirmed-working install to delete dead bytes is not worth the risk.
#
# The script reports the LIVE tag 6 values below, which are what the game actually uses.
LEVEL_COST = {EVOKER: 20, CONJURER: 40, ENCHANTER: 40, RITUALIST: 40}

# ---- classification constants (VMT slot DIFFERENCES -- rebase-invariant) --------------
D_SUMMON     = 0x0006B27C
D_GENCH      = 0x000767E0
D_UNIT       = 0x00001FF4
D_COMBAT_PRE = 0x00000120           # shared with abstract TSpell -> needs the confirm below
D_COMBAT_CFM = 0x0007E034           # [VMT+0x80] - [VMT+0x18]; unique across all 857 VMTs

CAVE_VA    = 0x55820800             # EXCLUSIVE RESERVATION 0x55820800..0x55820FFF
CAVE_LIMIT = 0x800
PROCS = ("AoW", "AoWCompat", "AoWDevEd", "AoWEd")

# original bytes at each displaced site (verify-before-write)
ORIG = {
    CASTINGMANA:   b"\x53\x56\x8b\xf2\x8b\x5e\x14",
    EPILOGUE:      b"\x8b\xc3\x5e\x5b\xc3",
    REG_SPLICE:    b"\xe8\x2f\x33\xf9\xff",
    GENCH_ACT:     b"\x8b\x43\x14\x50\x8a\x4e\x24",
    SUMMON_ACT:    b"\x8b\x43\x14\x50\x8b\x45\xfc",
    SUMMONTE_PROC: b"\x8b\x40\x14\x50\x8b\x45\xfc",
}


# ---- PE helpers (VA->file offset is PER-SECTION, never a flat delta) ------------------
def sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    out = []
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        vsz, va, rsz, praw = struct.unpack_from("<IIII", data, o + 8)
        out.append((base + va, max(vsz, rsz), praw))
    return out


def va2off(data, va):
    for sva, sz, praw in sections(data):
        if sva <= va < sva + sz:
            return praw + (va - sva)
    raise ValueError("VA %08X is in no section" % va)


def relocs_in(data, lo, hi):
    """Every type-3 base relocation in [lo,hi). Displacing one = a crash on some later launch."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    rva, size = struct.unpack_from("<II", data, pe + 24 + 96 + 5 * 8)
    if not rva:
        return []
    p = va2off(data, base + rva); end = p + size; hits = []
    while p < end:
        pg, blk = struct.unpack_from("<II", data, p)
        if blk < 8:
            break
        for k in range(8, blk, 2):
            e = struct.unpack_from("<H", data, p + k)[0]
            if e >> 12 == 3:
                va = base + pg + (e & 0xFFF)
                if lo <= va < hi:
                    hits.append(va)
        p += blk
    return hits


# ---- hand-encoded assembler --------------------------------------------------------
# NOT keystone: `push 0xFFFF` assembles as `6A FF` (= -1) silently, and `call $+5` written as
# source produces nothing while the anchor search zeroes the rel32 of whatever E8 precedes it.
class Asm:
    def __init__(self, base):
        self.base, self.buf, self.lab, self.fix8 = base, bytearray(), {}, []

    def here(self):
        return self.base + len(self.buf)

    def db(self, *b):
        self.buf += bytes(b)

    def raw(self, b):
        self.buf += bytes(b)

    def dd(self, v):
        self.buf += struct.pack("<I", v & 0xFFFFFFFF)

    def label(self, n):
        self.lab[n] = self.here()

    def j8(self, op, n):
        self.db(op); self.fix8.append((len(self.buf), n)); self.db(0)

    def call(self, t):
        self.db(0xE8); self.buf += struct.pack("<i", t - (self.here() + 4))

    def jmp32(self, t):
        self.db(0xE9); self.buf += struct.pack("<i", t - (self.here() + 4))

    def done(self):
        for off, n in self.fix8:
            rel = self.lab[n] - (self.base + off + 1)
            assert -128 <= rel <= 127, "short jump to '%s' out of range (%d)" % (n, rel)
            self.buf[off] = rel & 0xFF
        return bytes(self.buf)


def build_cave_cost(va):
    a = Asm(va)
    # EXACT displaced bytes, never re-assembled: keystone renders `mov esi,edx` as 89 D6 while the
    # original is 8B F2, and a re-assembled replay would fail byte-for-byte verification.
    a.raw(ORIG[CASTINGMANA])                    # push ebx; push esi; mov esi,edx; mov ebx,[esi+14]
    a.db(0x85, 0xC0)                            # test eax,eax
    a.j8(0x74, "back")                          #   nil Self guard
    a.db(0x8B, 0x08)                            # mov ecx,[eax]         ; Self VMT
    a.db(0x39, 0x49, 0xC0)                      # cmp [ecx-0x40],ecx    ; Delphi vmtSelfPtr sanity
    a.j8(0x75, "back")
    a.db(0x8B, 0x0E)                            # mov ecx,[esi]         ; spell VMT
    a.db(0x8B, 0x51, 0x6C)                      # mov edx,[ecx+0x6c]    ; TSpell.Activate slot
    a.db(0x2B, 0x51, 0x18)                      # sub edx,[ecx+0x18]    ; - TSpell.ReadWrite slot
    a.db(0x81, 0xFA); a.dd(D_SUMMON); a.j8(0x74, "conj")
    a.db(0x81, 0xFA); a.dd(D_GENCH);  a.j8(0x74, "ritu")
    a.db(0x81, 0xFA); a.dd(D_UNIT);   a.j8(0x74, "ench")
    a.db(0x81, 0xFA); a.dd(D_COMBAT_PRE); a.j8(0x75, "back")
    a.db(0x8B, 0x91); a.dd(0x80)                # mov edx,[ecx+0x80]    ; GetCombatDamageValue slot
    a.db(0x2B, 0x51, 0x18)                      # sub edx,[ecx+0x18]
    a.db(0x81, 0xFA); a.dd(D_COMBAT_CFM); a.j8(0x75, "back")   # abstract TSpell exits here
    a.db(0xBA); a.dd(EVOKER);    a.j8(0xEB, "query")
    a.label("conj"); a.db(0xBA); a.dd(CONJURER);  a.j8(0xEB, "query")
    a.label("ritu"); a.db(0xBA); a.dd(RITUALIST); a.j8(0xEB, "query")
    a.label("ench"); a.db(0xBA); a.dd(ENCHANTER)
    a.label("query")                            # EXACTLY ONE query per cost evaluation:
    a.db(0x8B, 0x08)                            #   mov ecx,[eax]       ; caster VMT
    a.db(0xFF, 0x91); a.dd(0x148)               #   call [ecx+0x148]    ; item-aware GetAbilityEnabled
    a.db(0x84, 0xC0)                            # test al,al
    a.j8(0x74, "back")
    a.db(0xD1, 0xEB)                            # shr ebx,1             ; NO floor here
    a.label("back")
    a.jmp32(CM_RESUME)
    return a.done()


def build_cave_floor(va):
    a = Asm(va)
    a.db(0x85, 0xDB)                            # test ebx,ebx
    a.j8(0x75, "out")
    a.db(0x83, 0x7E, 0x14, 0x00)                # cmp dword [esi+0x14],0   ; the BASE cost
    a.j8(0x74, "out")                           #   a genuinely free spell stays free
    a.db(0xBB); a.dd(1)                         # mov ebx,1
    a.label("out")
    a.raw(ORIG[EPILOGUE])                       # the vanilla epilogue, executed here
    return a.done()


def build_cave_gench(va):
    a = Asm(va)
    a.db(0x8B, 0xC6)                            # mov eax,esi           ; caster
    a.db(0x8B, 0xD3)                            # mov edx,ebx           ; spell
    a.call(CASTINGMANA)
    a.db(0x50)                                  # push eax              ; the DISCOUNTED cost
    a.db(0x8A, 0x4E, 0x24)                      # mov cl,[esi+0x24]     ; replayed
    a.jmp32(GENCH_RESUME)
    return a.done()


def build_cave_summon(va):
    a = Asm(va)
    a.db(0x8B, 0x45, 0xFC)                      # mov eax,[ebp-4]       ; caster (spilled @557E44BD)
    a.db(0x8B, 0xD3)                            # mov edx,ebx           ; spell
    a.call(CASTINGMANA)
    a.db(0x50)                                  # push eax
    a.db(0x8B, 0x45, 0xFC)                      # mov eax,[ebp-4]       ; replayed
    a.jmp32(SUMMON_RESUME)
    return a.done()


REG_BLOCK = 43          # bytes per registration block -- asserted while building


def build_cave_reg(va):
    lit_start = va + 5 + REG_BLOCK * len(ORDER) + 1     # replay call + blocks + ret
    lits, name_at, addr = bytearray(), {}, lit_start
    for i in ORDER:
        nm = NAMES[i].encode("ascii")
        # Delphi AnsiString literal: <i32 -1 refcount><u32 len><bytes><NUL>. refcount -1 makes
        # LStrAsg share it and never free it. EDX must point at the BYTES, i.e. blob + 8.
        name_at[i] = addr + 8
        lits += b"\xff\xff\xff\xff" + struct.pack("<I", len(nm)) + nm + b"\x00"
        addr += 9 + len(nm)

    a = Asm(va)
    a.call(REGISTERAB)                          # replay the displaced call (registers ability 0x8F)
    for i in ORDER:
        start = a.here()
        # Recompute the PIC anchor per ability: `mov eax,<id>` destroys it, and ESI/EDI are NOT
        # saved by the host (its prologue pushes only EBX), so it cannot be parked in a register.
        a.raw(b"\xE8\x00\x00\x00\x00")          # call $+5   (RAW bytes -- see the Asm note)
        # The call pushed the address of the NEXT byte -- which is where `pop eax` ITSELF sits.
        # Taking the anchor after emitting `pop eax` is an off-by-one that lands EDX on the last
        # byte of the u32 length field instead of the string. Cross-check against Drillmaster's
        # cave: EAX there is 0x5581600A (the `pop eax` address) and +0x2A = 0x55816034 = its bytes.
        anchor = a.here()
        a.db(0x58)                              # pop eax    ; EAX == anchor at runtime
        a.db(0x8D, 0x90); a.dd(name_at[i] - anchor)   # lea edx,[eax + (name - anchor)]
        a.db(0xB9); a.dd(SEL_MASK)              # mov ecx,0x3FF     (only CX is read)
        a.db(0xB8); a.dd(i)                     # mov eax,<id>
        a.call(CREATEENH)                       # -> EAX = the ability object
        # ⚠ NO-OP for a bit-only ability: TAbility.ReadWrite loads [+0x14] from Ability.pfs tag 6
        #   after registration and clobbers this. See the LEVEL_COST note at the top.
        a.db(0xC7, 0x40, 0x14); a.dd(LEVEL_COST[i])   # mov [eax+0x14],<cost>   (ineffective)
        a.db(0x89, 0xC2)                        # mov edx,eax
        a.db(0x89, 0xD8)                        # mov eax,ebx       ; EBX = the ability control
        a.call(REGISTERAB)
        assert a.here() - start == REG_BLOCK, \
            "registration block is %d bytes, REG_BLOCK says %d" % (a.here() - start, REG_BLOCK)
    a.db(0xC3)                                  # ret
    assert a.here() == lit_start, "literal start drifted: %08X vs %08X" % (a.here(), lit_start)
    a.raw(lits)
    body = a.done()
    verify_cave_reg(va, body)
    return body


def verify_cave_reg(va, body):
    """Re-derive, from the EMITTED BYTES, what EDX will actually hold at runtime, and prove it
    lands on the string bytes of a well-formed Delphi AnsiString. This exists because the PIC
    anchor is trivially off-by-one-able: `call $+5` pushes the address of `pop eax` itself, not
    the byte after it, and a one-byte slip points EDX at the length field instead -- which would
    hand LStrAsg a garbage length rather than failing loudly."""
    p = 5                                       # past the replayed `call RegisterAbility`
    for i in ORDER:
        assert body[p:p + 5] == b"\xE8\x00\x00\x00\x00", "block %s: no PIC anchor" % NAMES[i]
        anchor = va + p + 5                     # == the pushed return address == the `pop eax` VA
        assert body[p + 5] == 0x58, "block %s: no `pop eax`" % NAMES[i]
        assert body[p + 6:p + 8] == b"\x8D\x90", "block %s: no `lea edx,[eax+d32]`" % NAMES[i]
        disp = struct.unpack_from("<i", body, p + 8)[0]
        target = anchor + disp                  # what EDX holds at runtime
        k = target - va
        nm = NAMES[i].encode("ascii")
        assert body[k - 8:k - 4] == b"\xff\xff\xff\xff", \
            "%s: EDX -> 0x%08X, refcount field is %s not -1 (off-by-one?)" % (
                NAMES[i], target, body[k - 8:k - 4].hex(" "))
        assert struct.unpack_from("<I", body, k - 4)[0] == len(nm), \
            "%s: EDX -> 0x%08X, length field says %d, name is %d bytes (off-by-one?)" % (
                NAMES[i], target, struct.unpack_from("<I", body, k - 4)[0], len(nm))
        assert body[k:k + len(nm)] == nm, "%s: EDX -> 0x%08X, bytes are %r" % (
            NAMES[i], target, bytes(body[k:k + len(nm)]))
        assert body[k + len(nm)] == 0, "%s: AnsiString not NUL-terminated" % NAMES[i]
        # and the id the block registers must be the one whose name it points at
        assert body[p + 17] == 0xB8 and struct.unpack_from("<I", body, p + 18)[0] == i, \
            "%s: block registers the wrong id" % NAMES[i]
        p += REG_BLOCK


# ---- layout -------------------------------------------------------------------------
def cost_offsets():
    """Byte offsets of the four `mov [eax+0x14],<cost>` immediates inside cave_reg.
    Block layout (43B): call$+5(5) pop(1) lea(6) mov ecx(5) mov eax(5) call(5) mov[+14](7)
    mov edx,eax(2) mov eax,ebx(2) call(5). The imm32 sits 3 bytes into the 7-byte mov."""
    return [5 + i * REG_BLOCK + 30 for i in range(len(ORDER))]


def retuned_costs(cur, new):
    """If `cur` is this same cave differing ONLY in the four level-up costs, return the installed
    costs; otherwise None.

    ⚠ THIS IS WHY THE SCRIPT CAN RE-TUNE IN PLACE. CLAUDE.md forbids "revert and re-apply" as a
    re-tune procedure -- a .pre-* restore wipes every feature layered on top since. Instead the
    cave is rewritten in place, verified against EITHER the currently-installed bytes OR the new
    ones. Only the four cost immediates may differ; any other byte means someone else's data and
    the classifier falls through to OTHER (hard abort)."""
    if len(cur) != len(new):
        return None
    offs = cost_offsets()
    masked_cur, masked_new = bytearray(cur), bytearray(new)
    for o in offs:
        masked_cur[o:o + 4] = b"\0\0\0\0"
        masked_new[o:o + 4] = b"\0\0\0\0"
    if masked_cur != masked_new:
        return None
    return [struct.unpack_from("<I", cur, o)[0] for o in offs]


def align4(v):
    return (v + 3) & ~3


def layout():
    """Place the five caves back to back inside the reservation. Returns (caves, sites)."""
    caves, p = [], CAVE_VA
    for name, fn in (("cave_cost", build_cave_cost), ("cave_floor", build_cave_floor),
                     ("cave_gench", build_cave_gench), ("cave_summon", build_cave_summon),
                     ("cave_reg", build_cave_reg)):
        body = fn(p)
        caves.append((name, p, body))
        p = align4(p + len(body))
    used = p - CAVE_VA
    if used > CAVE_LIMIT:
        sys.exit("ABORT: caves total %d bytes, over the 0x%X reservation" % (used, CAVE_LIMIT))
    at = dict((n, va) for n, va, _ in caves)

    def jmp(src, dst):
        return b"\xE9" + struct.pack("<i", dst - (src + 5))

    def call(src, dst):
        return b"\xE8" + struct.pack("<i", dst - (src + 5))

    sites = [
        (CASTINGMANA, ORIG[CASTINGMANA], jmp(CASTINGMANA, at["cave_cost"]) + b"\x90\x90",
         "HOOK1  CastingMana entry -> cave_cost"),
        (EPILOGUE, ORIG[EPILOGUE], jmp(EPILOGUE, at["cave_floor"]),
         "HOOK2  CastingMana epilogue -> cave_floor"),
        (REG_SPLICE, ORIG[REG_SPLICE], call(REG_SPLICE, at["cave_reg"]),
         "HOOK3  RegisterPassiveAbilities splice -> cave_reg"),
        (GENCH_ACT, ORIG[GENCH_ACT], jmp(GENCH_ACT, at["cave_gench"]) + b"\x90\x90",
         "SITE A TGlobalEnchantmentSpell.Activate -> cave_gench"),
        (SUMMON_ACT, ORIG[SUMMON_ACT], jmp(SUMMON_ACT, at["cave_summon"]) + b"\x90\x90",
         "SITE B TSummonSpell.Activate -> cave_summon"),
        (SUMMONTE_PROC, ORIG[SUMMONTE_PROC], b"\x8b\x45\xfc\xff\x70\x1c\x90",
         "SITE C TSummonSpellTE.Process  (in place: push [TE+0x1C])"),
    ]
    for name, va, body in caves:
        sites.append((va, bytes(len(body)), body, "%s @0x%08X (%dB)" % (name, va, len(body))))
    return caves, sites, used


# ---- safety checks -------------------------------------------------------------------
def read_ability_pfs():
    """Record keys of Release/Ability.pfs, as ability ids (key = id + 10). Returns None if the
    file cannot be read -- callers must treat that as 'unknown', never as 'empty'."""
    import importlib.util
    try:
        sp = os.path.join(GAME, "Modding Resources", "re_tools", "pfs.py")
        spec = importlib.util.spec_from_file_location("pfs", sp)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        return {rid - 10 for rid, _b in m.load("ability.pfs")[0]}
    except Exception:                                       # noqa: BLE001
        return None


def live_costs():
    """The level-up cost the GAME actually uses, i.e. Ability.pfs tag 6 -- NOT the cave immediate.
    Returns {id: cost} for ids that have a record, or None if the file cannot be read.

    A bit-only ability inherits TAbility.ExpandCost @0x5574E908 (`return [ability+0x14]`), and
    TAbility.ReadWrite @0x5574F07C loads that field from tag 6, so the data file is authoritative.
    (Multi-level abilities are the opposite: they override ExpandCost in code and ignore tag 6.)"""
    import importlib.util
    try:
        sp = os.path.join(GAME, "Modding Resources", "re_tools", "pfs.py")
        spec = importlib.util.spec_from_file_location("pfs", sp)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        out = {}
        for rid, rec in m.load("ability.pfs")[0]:
            if rid - 10 not in ORDER:
                continue
            n = rec[0]
            pairs = [(rec[1 + k * 2], rec[2 + k * 2]) for k in range(n)]
            data = rec[1 + n * 2:]
            for idx, (t, off) in enumerate(pairs):
                if t != 6:
                    continue
                end = pairs[idx + 1][1] if idx + 1 < len(pairs) else len(data)
                blob = data[off:end]
                if len(blob) >= 4:
                    out[rid - 10] = struct.unpack_from("<I", blob)[0]
        return out
    except Exception:                                       # noqa: BLE001
        return None


def check_ids_free(data):
    """Scan for `mov eax,<id>; call CreateEnhancementAbility` and abort if any of ours is taken.
    Registering a taken id raises 'Ability already registered (' -> a bare Runtime error 217 at
    startup, with nothing in the message mentioning abilities.

    ⚠ SKIP OUR OWN CAVE. cave_reg literally contains `mov eax,0xAC; call CreateEnhancementAbility`
    x4, so a scan of the whole CODE section reports our own ids as collisions the moment the patch
    is installed -- which would block any legitimate re-apply from a partial state. Same guard as
    build_drillmaster.py:check_id_free().

    Ability.pfs is read only to WIDEN the picture when reporting; it must NOT drive the abort,
    because once DevEd mints records 182-185 for our own ids they would read as collisions."""
    sva, sz, praw = sections(data)[0]
    used = set()
    for o in range(praw, praw + sz - 10):
        if data[o] != 0xB8 or data[o + 5] != 0xE8:
            continue
        ident = struct.unpack_from("<I", data, o + 1)[0]
        if ident > 0xFF:
            continue
        src = sva + (o + 5 - praw)
        if CAVE_VA <= src < CAVE_VA + CAVE_LIMIT:           # our own cave -- not a collision
            continue
        if src + 5 + struct.unpack_from("<i", data, o + 6)[0] == CREATEENH:
            used.add(ident)
    clash = sorted(set(ORDER) & used)
    return sorted(used), clash


def check_cave_zone(data, caves, skip=()):
    """Every byte of the reservation must be zero or already ours. Guards against a co-tenant
    having claimed part of it since -- the failure that broke build_dispelmagic5.py.

    `skip` holds (va, length) ranges already POSITIVELY identified as ours by another check
    (currently: a cave recognised as this feature's own at a different level-up cost). Without it
    a re-tune would read as a foreign claim."""
    mine = {}
    for _, va, body in caves:
        for k in range(len(body)):
            mine[va + k] = body[k]
    bad = []
    for va in range(CAVE_VA, CAVE_VA + CAVE_LIMIT):
        if any(lo <= va < lo + n for lo, n in skip):
            continue
        cur = data[va2off(data, va)]
        if cur == 0 or cur == mine.get(va, 0):
            continue
        bad.append(va)
    return bad


def disasm(code, va):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return "  (capstone not installed -- cave not disassembled)"
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    out, n = [], 0
    for i in md.disasm(code, va):
        out.append("  %08X  %-8s %s" % (i.address, i.mnemonic, i.op_str))
        n += i.size
    if n < len(code):
        out.append("  %08X  <%d trailing data bytes>" % (va + n, len(code) - n))
    return "\n".join(out)


def kill_game():
    # ⚠ SCRATCH GUARD (2026-09-03): AOW_GAME_DIR set => we are NOT writing to the real
    # install, so we must NOT kill the user's running game. Without this, an agent doing a
    # "safe" scratch-copy round-trip still terminates the live game -- which happened, and
    # was misreported as a crash-on-expiry. Standing kill authorization applies to the real
    # install only.
    if os.environ.get("AOW_GAME_DIR"):
        return
    ps = ("Get-Process | Where-Object { $_.ProcessName -match '^(%s)$' } | Stop-Process -Force"
          % "|".join(PROCS))
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)


# ---- main ----------------------------------------------------------------------------
def main():
    apply_ = "--apply" in sys.argv
    undo = "--undo" in sys.argv
    show = "--dis" in sys.argv

    data = bytearray(open(DLL, "rb").read())
    caves, sites, used = layout()

    reg_va = dict((n, va) for n, va, _ in caves)["cave_reg"]
    installed_costs = None

    state = []
    for va, orig, new, desc in sites:
        off = va2off(data, va)
        cur = bytes(data[off:off + len(orig)])
        if cur == new:
            state.append("patched")
        elif cur == orig:
            state.append("vanilla")
        elif va == reg_va:
            got = retuned_costs(cur, new)          # our own cave at a different level-up cost?
            if got is not None:
                installed_costs = got
                state.append("RETUNE")
            else:
                state.append("OTHER")
        else:
            state.append("OTHER")

    print("caster_cost -- Evoker / Conjurer / Enchanter / Ritualist   (%s)" % os.path.basename(DLL))
    live = live_costs()
    for i in ORDER:
        if live is None:
            note = ""
        elif i not in live:
            note = "   cost: NO Ability.pfs record -> PERMANENTLY FREE"
        elif live[i] == 0:
            note = "   cost: tag 6 absent/0 -> PERMANENTLY FREE"
        else:
            note = "   cost: %d" % live[i]
            if live[i] != LEVEL_COST[i]:
                note += " (script constant says %d -- the DATA WINS, edit it in AoWDevEd)" % LEVEL_COST[i]
        print("  %-9s 0x%02X  halves %-20s%s" % (NAMES[i], i, FAMILY[i], note))
    emitted = sum(len(b) for _, _, b in caves)
    print("  caves 0x%08X..0x%08X  %d bytes emitted (%d incl. alignment) of %d reserved\n" %
          (CAVE_VA, caves[-1][1] + len(caves[-1][2]) - 1, emitted, used, CAVE_LIMIT))
    for (va, orig, new, desc), st in zip(sites, state):
        print("  [%-7s] %08X  %s" % (st, va, desc))

    if "RETUNE" in state:
        print("")
        print("  *** IN-PLACE RE-TUNE ***  cave_reg is already this feature's, at different")
        print("      hero level-up costs. --apply rewrites the cave in place; it does NOT")
        print("      revert anything, and no backup is touched.")
        for n, i in enumerate(ORDER):
            was, now = installed_costs[n], LEVEL_COST[i]
            print("        %-9s 0x%02X   %3d -> %3d%s" % (NAMES[i], i, was, now,
                  "" if was != now else "   (unchanged)"))
        pfs = read_ability_pfs()
        if pfs is not None and set(ORDER) & pfs:
            print("      WARNING: Release/Ability.pfs already has records for these ids, and")
            print("               tag 6 OVERRIDES this immediate. The new costs will NOT show")
            print("               in game until you edit the level-up cost in AoWDevEd too.")

    if "OTHER" in state:
        print("\nABORT: a site holds bytes that are neither vanilla nor this patch.")
        for (va, orig, new, desc), st in zip(sites, state):
            if st == "OTHER":
                off = va2off(data, va)
                print("  %08X\n    expected %s\n    or       %s\n    found    %s"
                      % (va, orig.hex(" ")[:72], new.hex(" ")[:72],
                         bytes(data[off:off + len(orig)]).hex(" ")[:72]))
        return 1

    if undo:
        if all(s == "vanilla" for s in state):
            print("\nAlready vanilla -- nothing to undo."); return 0

        # ⚠ THE REAL UNDO HAZARD. TAbilityControl.GetAbility @0x557501C0 bounds-checks and returns
        # nil for an unregistered id, but TAbstractUnit.GetAbilityEnabled @0x5577F5E0 then derefs
        # it unchecked (`mov ecx,[eax]` @0x5577F60A). So a SET BIT for an UNREGISTERED id is an
        # access violation on the next ability query. Once DevEd has minted records 182-185 and
        # the abilities have been assigned to anything, unregistering them here is exactly that.
        pfs = read_ability_pfs()
        if pfs is None:
            print("\n  (could not read Release/Ability.pfs -- cannot check for assigned bits)")
        else:
            minted = sorted(set(ORDER) & pfs)
            if minted and "--force" not in sys.argv:
                print("\nABORT: Release/Ability.pfs already carries record(s) %s -- these abilities"
                      % ", ".join("%d (id 0x%02X)" % (i + 10, i) for i in minted))
                print("       have been assigned in AoWDevEd. Unregistering them now would leave"
                      "\n       set ability bits pointing at nil, and the next ability query would"
                      "\n       access-violate (TAbstractUnit.GetAbilityEnabled derefs GetAbility"
                      "\n       @0x5577F60A with no null check).")
                print("       Strip the abilities from every unit/hero/item in AoWDevEd and save,"
                      "\n       then re-run --undo. Use --force only if you are certain no saved"
                      "\n       game and no .pfs still sets those bits.")
                return 1
            if minted:
                print("\n  --force: unregistering %d id(s) that still have Ability.pfs records."
                      % len(minted))

        kill_game()
        if not os.path.exists(BAK):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(DLL, BAK); print("\nBackup: %s" % BAK)
        # Site order is immaterial: every write lands in one in-memory bytearray that is committed
        # by a single atomic replace below. The ordering hazard is the one handled above.
        for va, orig, new, desc in sites:
            off = va2off(data, va)
            data[off:off + len(orig)] = orig
        commit(data)
        print("\nUNDONE: %d sites restored; %d cave bytes zeroed (emitted length only, never the"
              " 0x%X reservation)." % (len(sites), sum(len(b) for _, _, b in caves), CAVE_LIMIT))
        return 0

    if all(s == "patched" for s in state):
        print("\nALREADY APPLIED -- nothing to do.")
        if show:
            for name, va, body in caves:
                print("\n%s @0x%08X (%d bytes):\n%s" % (name, va, len(body), disasm(body, va)))
        return 0

    # --- pre-flight, only meaningful when something is still vanilla ---
    ids, clash = check_ids_free(data)
    print("\n  ability ids in use: %d, highest 0x%02X" % (len(ids), max(ids)))
    if clash:
        print("  ABORT: id(s) already registered: %s" % ", ".join("0x%02X" % c for c in clash))
        return 1
    print("  ids 0x%02X-0x%02X are free." % (ORDER[0], ORDER[-1]))

    reg_len = dict((n, b) for n, _v, b in caves)["cave_reg"]
    skip = [(reg_va, len(reg_len))] if "RETUNE" in state else []
    bad = check_cave_zone(data, caves, skip)
    if bad:
        print("  ABORT: %d byte(s) of the reservation belong to someone else, first at 0x%08X"
              % (len(bad), bad[0]))
        return 1
    print("  cave reservation 0x%08X..0x%08X is clear." % (CAVE_VA, CAVE_VA + CAVE_LIMIT - 1))

    hits = []
    for va, orig, new, desc in sites[:6]:
        hits += relocs_in(data, va, va + len(orig))
    if hits:
        print("  ABORT: .reloc entries inside a displaced window: %s"
              % ", ".join("0x%08X" % h for h in hits))
        return 1
    print("  no .reloc entries inside any displaced window.")

    for name, va, body in caves:
        print("\n%s @0x%08X (%d bytes):\n%s" % (name, va, len(body), disasm(body, va)))

    if not apply_:
        print("\nDry run OK. Re-run with --apply to write.")
        return 0

    kill_game()
    if not os.path.exists(BAK):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BAK); print("\nBackup: %s" % BAK)
    # Site order is immaterial -- all writes land in one in-memory bytearray committed atomically.
    for va, orig, new, desc in sites:
        off = va2off(data, va)
        data[off:off + len(new)] = new
        print("Patched: %s" % desc)
    commit(data)
    print("\nAoWEPACK.dpl patched.\n")
    print(OUT_OF_BAND)
    return 0


def commit(data):
    """Write via a temp file + os.replace. A bare open(DLL,'wb') truncates on open, so an
    interruption mid-write leaves a 0-byte or half-written DLL and no way back except a backup."""
    tmp = DLL + ".tmp-castercost"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, DLL)


OUT_OF_BAND = """NEXT STEPS -- a build script cannot do these:
  1. Launch the game ONCE and confirm there is no bare 'Runtime error 217' before the main window.
     That is what a duplicate ability id looks like; nothing in the message mentions abilities.
  2. In AoWDevEd, assign each of the four abilities to something and SAVE -- four round trips.
     That is the only way Ability.pfs records 182-185 get minted; no script can create one.
     Then author tag 5 (description) and tag 6 (level-up cost) there.
     WITHOUT tag 6 the ability is PERMANENTLY free, not merely displayed as free.
  3. Re-check tag 9 stayed 0x03FF after every DevEd save -- the data file overwrites the cave's mask.
  4. Add 0xAC-0xAF (and Magebane 0xAA, missing today) to re_tools/ability_names.py MODDED so the
     Ziggurat Manual lists them.
  5. Only then playtest the discounts."""


if __name__ == "__main__":
    sys.exit(main())
