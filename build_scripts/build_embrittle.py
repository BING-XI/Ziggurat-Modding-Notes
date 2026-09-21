# -*- coding: utf-8 -*-
r"""
build_embrittle.py — new tactical combat spell "Embrittle" (id 109) + new passive
ability "Embrittled" (id 0xB2): the afflicted unit takes DOUBLE physical damage.

    python build_scripts/build_embrittle.py            dry run + verify + disassembly
    python build_scripts/build_embrittle.py --apply     write it
    python build_scripts/build_embrittle.py --undo      restore all 7 hooks, zero the cave
    python build_scripts/build_embrittle.py --dis       disassemble the installed caves

EFFECT
    Embrittle is cast in tactical combat at a single enemy unit, opposed by the
    target's Resistance exactly like Slow. On a hit the unit gains the "Embrittled"
    passive for the rest of that combat; while it holds, EVERY incoming damage roll
    whose damage-type mask includes the physical bit is DOUBLED.

    It is the mirror of Physical Protection (which halves), and it is deliberately the
    same magnitude, so a unit holding BOTH takes exactly normal damage — see
    "CANCEL EXACTLY" below.

    Physical Immunity targets are refused: the cast fizzles rather than applying.

TARGET: AoWEPACK.dpl (7 sites + one cave zone) and AoWTCPCK.dpl (ONE byte).
        AoW.exe / AoWCompat.exe are NOT touched by this script — but see CEILINGS.

────────────────────────────────────────────────────────────────────────────────────────────
WHERE THE EFFECT LIVES — one shared function, both combat systems
────────────────────────────────────────────────────────────────────────────────────────────
AoWE.TCombatObject.ExecuteDamageRole   @0x557269F0   (VMT +0x110)
AoWE.TCombatObject.ExecuteDamageRoleEx @0x55726A6C   (VMT +0x114)

are the ONLY damage roll in the game. Structurally identical; Ex picks Resistance
(VMT +0x74) instead of Defence (+0x70) when its first arg is 1. Vanilla tail:

    55726A38  mov  edi,eax                 ; EDI = the rolled damage
    55726A3A  mov  eax,ebx                 ; \
    55726A3C  mov  edx,[eax]               ;  } HOOKED, 10 bytes
    55726A3E  call [edx+0x80]              ; /  TCombatObject.GetProtectionTypes -> AX
    55726A44  not  eax
    55726A46  and  ax,si                   ; ESI = ~immunity & damage-type mask
    55726A49  mov  dx,[0x55726A68]         ; a zero word constant
    55726A50  cmp  dx,ax
    55726A53  jne  0x55726A5D              ; not every bit covered -> no halve
    55726A55  inc  edi / sar edi,1 / ...   ; (dmg+1)>>1  = Physical Protection's halve

Neither class overrides these — TCombatObject and TCombatUnit both carry 0x557269F0 at
+0x110 (Ghidra_VMT_Layouts.md) and AoWTCPCK's TTacticalCombatUnit reaches them through an
import thunk. So ONE patch covers manual tactical combat, auto-resolve and the strategic
map alike. Hooking the shared implementation rather than a VMT slot is the same reasoning
build_reformingflesh.py records for the round tick.

⚠ TCombatWall is also a TCombatObject. It answers the ability query through
TCombatObject.GetAbilityEnabled @0x557268D4 (`xor eax,eax; ret`), so walls can never be
embrittled and need no type test — the same free type-gate reformingflesh relies on.

────────────────────────────────────────────────────────────────────────────────────────────
CANCEL EXACTLY — why the doubling goes BEFORE the halve
────────────────────────────────────────────────────────────────────────────────────────────
The cave doubles EDI and then tail-jumps into the vanilla GetProtectionTypes call, so the
vanilla halve (if it fires at all) sees the already-doubled figure:

    embrittled only                 dmg -> 2*dmg
    embrittled + Physical Prot.     dmg -> (2*dmg + 1) >> 1  ==  dmg          (exact)
    Physical Protection only        dmg -> (dmg + 1) >> 1                     (vanilla)

Doubling AFTER the halve would give (dmg+1>>1)*2 — 5 damage would come back as 6, not 5.
That off-by-one is the whole reason for the ordering; do not "simplify" it by moving the
add below the call.

⚠ The halve is an ALL-BITS test: `(~prot & ~imm & mask) == 0` fires only when every damage
type in the mask is covered. The doubling is an ANY-BIT test (`mask & 0x80`), by design —
see SCOPE. So a fire+physical strike on a unit with Physical Protection alone is doubled
and NOT halved. That is intended: the protection genuinely does not apply to that hit in
vanilla either.

────────────────────────────────────────────────────────────────────────────────────────────
SCOPE — the physical bit, and where the bit numbering comes from
────────────────────────────────────────────────────────────────────────────────────────────
AoWE.TAbilityOwner.GetAbProtectionTypesAll @0x5574F97C and GetAbImmunityTypesAll
@0x5574FADC are the two functions that BUILD these masks, and they fix the bit order:

    0x01 Fire   0x02 Cold   0x04 Lightning   0x08 Magic
    0x10 Poison 0x20 Death  0x40 Holy        0x80 PHYSICAL

(Physical Protection = ability 0x4D or 0xA6 -> bit 0x80; Physical Immunity = ability 0x0D
-> bit 0x80.) The cave tests `mask & 0x80`, i.e. ANY hit carrying a physical component —
melee, ranged, physical spells, and elemental-strike weapons whose mask is physical+element.

────────────────────────────────────────────────────────────────────────────────────────────
THE SPELL — no new class, no new save/network ClassID
────────────────────────────────────────────────────────────────────────────────────────────
Adding_New_Spells_Abilities_2026-07-05.md rates "a combat spell that applies its own unit
enchantment" as Tier 2/3: a cloned TSlowCA needs a unique ClassID registered through
RegisterEClasses, because a combat action is a save- and wire-serialized object.

That is avoided entirely. Embrittle IS a `CombatSpells.TSlow` instance (different id,
name, sphere, tier, cost) and it produces genuine `TSlowCA` combat actions. The only thing
that must differ is WHICH ability id the machinery applies, and TSlow hard-codes 0x84 in
exactly three places — all of which already have the spell id to hand:

    TSlow.CreateCA    @0x557F89B3  mov edx,0x84   ; "does the target already have it?"
                      @0x557F89BC  call [ecx+0xA8]   <- HOOKED (6 B)   ESI = the spell
    TSlowCA.Execute   @0x557F884F  mov edx,0x84   <- HOOKED (5 B)      EBX = the CA
                      @0x557F8863  mov edx,0x84   <- HOOKED (5 B)      EBX = the CA

`[spell+0x10]` is the spell id and `[CA+0x18]` is the spell id the CA was built from
(TSlow.CreateCA @0x557F89A1 copies it), so each hook picks 0x84 or 0xB2 from state that is
already in a register. Serialization, network identity and replay are untouched: every
Embrittle CA is a bit-for-bit ordinary TSlowCA.

⚠ The `mov edx,0x84` at 0x557F89B3 is deliberately LEFT ALONE. The cave at 0x557F89BC
recomputes EDX itself, so patching both would be redundant — and one fewer displaced run is
one fewer thing to verify.

⚠ Slow itself is untouched and must stay that way: every hook re-derives 0x84 for any spell
id that is not ours. `--undo` restores all three verbatim.

────────────────────────────────────────────────────────────────────────────────────────────
PHYSICAL IMMUNITY — the fizzle, and why it is not a UI gate
────────────────────────────────────────────────────────────────────────────────────────────
Manual tactical combat has NO damage-based target gate. Proof: TSlow.GetCombatDamageValueEx
@0x557F8948 returns an all-zero struct and Slow is still freely castable. TSpell's
tcGetDamageValueEx (+0x88) just forwards to GetCombatDamageValueEx (+0x84), and nothing
consults it for validity. Only FAST combat gates on a value — fcPrefetchCombatCommands
@0x557F76BC skips a target whose fcGetDamageValueEx first dword is 0.

So the engine's own idiom for "this spell does not apply to that target" is a fizzle in
CreateCA, and CombatSpells.TTurnUndead is the worked vanilla example: TTurnUndead.CreateCA
@0x557F7C50 builds the CA and only calls the hit-roll setup if the target is undead —
casting Turn Undead at a living unit is permitted and simply does nothing.

The cave copies that: on a Physical Immunity target it returns AL=1, i.e. "already has the
ability", which is the existing vanilla path for re-casting Slow on a slowed unit. The
caller skips HitRole, `[CA+0x14]` stays 0, and TSlowCA.Execute does nothing.

⚠ CONSEQUENCE, and it is a real one: the cast is still SPENT (mana and casting points go).
This is exactly how re-casting Slow on an already-slowed unit behaves in vanilla, so it is
consistent — but it is a fizzle, not a greyed-out target. A hard UI gate would mean
surgery on AoWTCPCK's targeting (TTacticalCombatUnitHS.SelectSpell and friends) and is a
separate feature.

Physical Immunity already makes the ability inert on its own — ExecuteDamageRole returns 0
before reaching the cave when `~immunity & mask` is empty — so the fizzle is about not
wasting the cast, not about correctness.

────────────────────────────────────────────────────────────────────────────────────────────
THE ABILITY — instantiate TSlowEnchantmentAbility, do not build a class
────────────────────────────────────────────────────────────────────────────────────────────
PassiveAb.TSlowEnchantmentAbility (classref ptr 0x557B96B8, Create @0x557B9E78) overrides
only Create, CreateEnchantment and CombatDone, and every one of them is driven by the
ability's OWN id field rather than a constant:

    CombatDone @0x557B9F24   owner := combatUnit.GetAbilityOwner()   ; VMT +0xB8
                             owner.RemoveAbility([self+0x0C])        ; VMT +0x98

so a second instance with `[+0x0C] = 0xB2` removes 0xB2 at end of combat, entirely on its
own. No VMT clone, no new class, no RegisterEClasses. The cave calls the vanilla
constructor, overwrites the id and the name, and registers it.

⚠ NOT CreateEnhancementAbility. A plain TEnhancementAbility has the wrong AbilityDataClass:
TSlowCA.Execute @0x557F8863 does GetAbilityData(unit, id) and then calls +0x54/+0x58 on
`[data+0x10]`, which only exists because TUnitEnchantmentAbility's data class carries a
TUnitEnchantment there. Registering 0xB2 as an enhancement would fault or silently no-op.

The constructor leaves `[+0x20]` (the TAbilitySelectionType mask) at 0, so Embrittled is
never offered in the editor, on items, or at hero level-up — the same as Slow's 0x84. That
is why no FExpandCost store is emitted here, unlike build_reformingflesh.py: an ability
that cannot be selected cannot be bought.

────────────────────────────────────────────────────────────────────────────────────────────
REGISTRATION SITES — chain, never re-use
────────────────────────────────────────────────────────────────────────────────────────────
ability  0x557BCE65  the LAST still-direct `call TAbilityControl.RegisterAbility` inside
                     PassiveAb.RegisterPassiveAbilities @0x557BC1CC (len 0xE00). Measured
                     live 2026-09-01: 83 of the 87 calls there are still direct; the four
                     already repointed are 0x557BCE9A (reformingflesh -> 0x55826000),
                     0x557BCECF (shield -> 0x55823128), 0x557BCF04 (caster_cost ->
                     0x558208B4) and 0x557BCF39 (drillmaster -> 0x55816000).
                     assert_sites() re-measures rather than trusting this comment.
spell    0x557FA83F  the LAST `call TSpellControl.RegisterSpell` in
                     CombatSpells.RegisterCombatSpells @0x557FA50C (it registers
                     TSacrificialFlame). Still vanilla — `grep -rn 557FA8 build_scripts/`
                     came up empty 2026-09-01.

⚠ Taking a site another feature already repointed is the documented silent-unlink failure
(see the Magebane/Shield chain note in CLAUDE.md): the earlier feature's cave stops being
called and nothing reports it. Both sites above are verified byte-for-byte as the ORIGINAL
direct `call` before anything is written.

At both sites EBX holds the control object (TAbilityControl / TSpellControl) for the whole
of the enclosing function, and the instruction immediately before is `mov eax,ebx` — which
is what `mov eax,ebx` in each cave relies on.

────────────────────────────────────────────────────────────────────────────────────────────
AoWTCPCK — SpellTypes[109], the one byte that stops the spell vanishing
────────────────────────────────────────────────────────────────────────────────────────────
`AoWTC.SpellTypes` @0x004672F4 (AoWTCPCK.dpl DATA, file offset 0x662F4) is byte[0..130] =
each spell's tactical-combat class. ID_Ceilings.md S3: a spell with id >= 100 whose byte is
0 is SILENTLY DELETED from the research list by AoW.exe @0x0042F304.

109 is the vanilla registry hole, so its byte is 0. It is set to 0x07 — measured, not
guessed: SpellTypes[110] (Slow) and SpellTypes[111] (Entangle) are both 0x07, the
single-enemy-unit-target tactical class, which is exactly what Embrittlement is.

Own-module DATA at a fixed base — no reloc concern, no cave.

────────────────────────────────────────────────────────────────────────────────────────────
CEILINGS — TWO OTHER SCRIPTS MUST BE RE-RUN (this one cannot do it)
────────────────────────────────────────────────────────────────────────────────────────────
Vanilla's highest ability id was 0xA9, so nine `cmp <counter>, 0xAA` loop terminators exist
across AoWTCPCK.dpl, AoW.exe and AoWCompat.exe. Both ladder scripts currently sit at 0xB2
(correct while 0xB1 was the top id). Registering 0xB2 makes them one short, and the failure
is a SILENCE, not a crash — the ability works but is invisible to the tactical AI, the item
banner popup, the unit hover popup, and CreateTCAbList.

After --apply, run BOTH (their LADDERs already carry 0xB3, appended by this feature):

    python build_scripts/build_abilityid_ceilings.py --apply     # 6 sites + 2 lockstep twins
    python build_scripts/build_tcablist_ceiling.py  --apply      # 1 site

Each derives the target from re_tools/ability_names.py, so 0xB2 was added to its MODDED map
as part of this feature — without that entry the ability prints as `?` and the ladders would
not know to move. Shield shipped four days before anyone noticed that omission.

────────────────────────────────────────────────────────────────────────────────────────────
NOT DONE HERE (data-side, deliberately deferred)
────────────────────────────────────────────────────────────────────────────────────────────
Release/Spells.pfs record 119 (= 109 + 10) is written by build_embrittle_pfs.py, so
spellbook description and NO icon, and keeps the costs this cave sets. Release/Ability.pfs
record 188 (= 0xB2 + 10) likewise does not exist, so Embrittled has no description text.
Both materialize the moment the set is saved from AoWDevEd, and from then on THE DATA FILE
WINS for tags 0xA-0x11 (cost/research/sphere/tier/description/icon) — see
Adding_New_Spells_Abilities_2026-07-05.md §7d. Requested to be left for later.

PIC: the DPL never loads at its preferred base. cave_createca, cave_absel and cave_dmg are
register-only + rel32 and need no anchor. The two registration caves need the runtime
address of a classref pointer and of a name literal, so each uses the standard
`call <addr> ; pop <reg>` delta trick with the rel32 zeroed. Nothing anywhere uses an
absolute address. No RNG draw is added — HitRole is called by the untouched host.
"""
import os, sys, struct, shutil, subprocess

# The Windows console defaults to cp1252, which cannot encode the U+26A0 warning sign used
# throughout. Without this the script writes its bytes correctly and THEN dies with a
# UnicodeEncodeError while printing, which reads as a failed patch when it was a successful
# one. Same idiom as build_shield.py / build_reformingflesh.py.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

try:
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    sys.exit("needs keystone-engine and capstone:  py -m pip install keystone-engine capstone")

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL   = os.path.join(GAME, "AoWEPACK.dpl")
TCPCK = os.path.join(GAME, "AoWTCPCK.dpl")
DLL_BACKUP   = os.path.join(BACKUP_DIR, os.path.basename(DLL)   + ".pre-embrittle")
TCPCK_BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TCPCK) + ".pre-embrittle")
DLL_BASE   = 0x55700000
TCPCK_BASE = 0x00400000

# ================================================================== the knobs
SPELL_ID      = 109         # free id, reserved by ID_Ceilings.md for a combat-castable spell
ABILITY_ID    = 0xB2        # first free ability id (0xB1 Reforming Flesh is the current top)

SPELL_NAME    = b"Embrittle"      # the SPELL: an imperative verb, like Entangle / Bless /
                                  # Desiccate / Vaporize. Chosen 2026-09-01 over
                                  # "Embrittlement", which would have been the only -ment
                                  # process-noun among all 109 spell names.
ABILITY_NAME  = b"Embrittled"     # the STATUS on the afflicted unit. Vanilla inflects these:
                                  # TBlessedEnchantment loads BlessedRStr (spell "Bless"), and
                                  # abilities 0x28/0x5E ship as "Entangle"/"Entangled".

SPHERE        = 3           # TMagicSphere: 0 msCosmos 1 msLife 2 msDeath 3 msEarth
                            #               4 msAir    5 msFire 6 msWater
RESEARCH_TIER = 3           # [spell+0x21]; 0 = not researchable
MANA_COST     = 14          # [spell+0x14] -- Tremors (the other Earth tier-3 combat spell)
RESEARCH_COST = 80          # [spell+0x18] -- likewise Tremors

SPELL_POWER   = 9           # [spell+0x34]; HitRole(power - target Resistance) in TSlow.CreateCA.
                            # Left at Slow's own value deliberately. Already on the Ziggurat
                            # scale -- do NOT rescale it. THE tuning knob if the spell lands
                            # too often or too rarely.

DMG_CLAMP     = 126         # TCombatObject.ExecuteDamage @0x55726C58 asserts damage < 0x7F
                            # ("Invalid Damage Value"). Ziggurat already raised that bound from
                            # vanilla's 0x31 as part of the DAM/HP doubling, so 126 is the live
                            # ceiling, not 49. Reachable only in absurd cases; the clamp exists
                            # so a doubling can never turn a big hit into an assert dialog.
PHYS_BIT      = 0x80        # damage-type mask bit for Physical (GetAbProtectionTypesAll)
# ===========================================================================

# --- engine entry points (all verified against the live DLL 2026-09-01) ----------
REGISTER_ABIL   = 0x55750238    # AoWE.TAbilityControl.RegisterAbility
REGISTER_SPELL  = 0x55779B40    # AoWE.TSpellControl.RegisterSpell
SLOWENCH_CREATE = 0x557B9E78    # PassiveAb.TSlowEnchantmentAbility.Create   (EAX=class, DL=1)
SLOWENCH_CLSPTR = 0x557B96B8    # ptr -> PassiveAb..TSlowEnchantmentAbility
TSLOW_CREATE    = 0x557F8890    # CombatSpells.TSlow.Create                  (EAX=class, DL=1)
TSLOW_CLSPTR    = 0x557F4DC0    # ptr -> CombatSpells..TSlow
LSTRASG         = 0x55701150    # thunk -> VCL30.dpl!System.@LStrAsg   (EAX=@dest, EDX=src)

VMT_ABIL_ENABLED = 0xA8         # TCombatObject.GetAbilityEnabled  (item-aware on TCombatUnit)
VMT_IMMUNITY     = 0x7C         # TCombatObject.GetImmunityTypes
VMT_PROTECTION   = 0x80         # TCombatObject.GetProtectionTypes

# --- hook sites, with their exact vanilla bytes -----------------------------------
REG_ABIL_INJ   = 0x557BCE65
REG_ABIL_ORIG  = b"\xE8" + struct.pack("<i", REGISTER_ABIL - (REG_ABIL_INJ + 5))
REG_SPELL_INJ  = 0x557FA83F
REG_SPELL_ORIG = b"\xE8" + struct.pack("<i", REGISTER_SPELL - (REG_SPELL_INJ + 5))

CREATECA_INJ   = 0x557F89BC
CREATECA_ORIG  = bytes.fromhex("ff91a8000000")          # call dword ptr [ecx+0xA8]

ABSEL_INJS     = (0x557F884F, 0x557F8863)
ABSEL_ORIG     = bytes.fromhex("ba84000000")            # mov edx, 0x84

# (VA, original 10 bytes, ebp displacement of the damage-type mask argument)
DMG_INJS = ((0x55726A3A, 0x08, "TCombatObject.ExecuteDamageRole"),
            (0x55726ACF, 0x0C, "TCombatObject.ExecuteDamageRoleEx"))
DMG_ORIG = bytes.fromhex("8bc38b10ff9280000000")        # mov eax,ebx / mov edx,[eax] / call [edx+0x80]

# --- AoWTCPCK: the SpellTypes byte -------------------------------------------------
SPELLTYPES_VA   = 0x004672F4
SPELLTYPES_OFF  = SPELLTYPES_VA - TCPCK_BASE            # resolved properly via va2off()
ST_DONOR        = 110                                   # Slow -- same tactical class
ST_VANILLA      = 0x00

# --- cave placement ----------------------------------------------------------------
# 0x5582D000: page-aligned, above EVERY address claimed by any build script (highest prior
# claim is 0x5582C080, build_terror_oncepercombat.py / build_gripofwinter.py), 764,416
# zero bytes ahead of it, and no .reloc entry anywhere in the zone. Verified 2026-09-01:
#     grep -rn "5582D" "Modding Resources/build_scripts/"   -> no hits
# ⚠ Do not "reclaim" the apparent gap below this. build_rng_lockstep.py's rng_sync stub and
# build_panic_nomelee.py both sit inside what looks like one enormous free run -- read those
# two scripts for their addresses rather than trusting the zeros. A zero run is not proof a
# zone is unclaimed; it is usually another feature's growth reservation, a mistake recorded
# three times in this folder.
# ⚠ and do not quote their raw addresses here: re_tools/rng_audit.py --owners attributes an
# RNG site to every build script whose TEXT contains the address, so naming rng_lockstep's
# cave in this comment made the audit report build_embrittle.py as an owner of a synced RNG
# draw it has nothing to do with. This feature adds no RNG draw at all -- HitRole is called
# by the untouched host, not by any cave here.
CAVE = 0x5582D000
CAVE_ZONE_LEN = 0x300           # reservation, incl. growth slack; asserted zero before write

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

PH_ABNAME  = 0x71111101         # placeholders replaced with (target - PIC anchor)
PH_ABCLS   = 0x71111102
PH_SPNAME  = 0x71111103
PH_SPCLS   = 0x71111104

AOW_PROCS = ["AoW", "AoWCompat", "AoWDevEd", "AoWEd"]


def kill_aow():
    """Game files are locked while any AoW binary runs; AoWDevEd loads AoWEPACK.dpl too.
    Standing authorization to kill them -- the game autosaves per turn and the editor
    prompts on its own next launch."""
    killed = [n for n in AOW_PROCS
              if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                                capture_output=True, text=True).returncode == 0]
    if killed:
        print("  killed running: " + ", ".join(killed))


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def fix_pic(code, va, pop_op, subs):
    """`call <addr> ; pop <reg>` -> a runtime delta anchor; rewrite placeholders as
    (target - anchor).

    The call's rel32 is zeroed so it falls straight through to the pop, which then holds
    the RUNTIME address of itself. Nothing in a DPL cave may use an absolute address.

    ⚠ never write the anchor as `call $+5` in the source -- keystone assembles that to
    NOTHING, silently, and the search below then latches onto whatever earlier E8 happens
    to sit five bytes before a matching pop and zeroes ITS rel32. Emit a real
    `call <addr>`; the target is irrelevant because the rel32 is zeroed here anyway.
    """
    code = bytearray(code)
    i = next(k for k in range(len(code) - 5) if code[k] == 0xE8 and code[k + 5] == pop_op)
    anchor = va + i + 5
    code[i + 1:i + 5] = struct.pack("<i", 0)
    for ph, tgt in subs:
        hits = [k for k in range(len(code) - 3) if code[k:k + 4] == struct.pack("<I", ph)]
        assert len(hits) == 1, "placeholder %#x found %d times" % (ph, len(hits))
        code[hits[0]:hits[0] + 4] = struct.pack("<i", tgt - anchor)
    return bytes(code)


# refcount -1 => LStrAsg shares the literal and never tries to free it (Path of Sand recipe)
def literal(s):
    return struct.pack("<iI", -1, len(s)) + s + b"\x00"


# --------------------------------------------------------------- cave_reg_abil
def build_reg_abil(va, name_va):
    """Re-issue the displaced RegisterAbility, then build + register Embrittled (0xB2).

    On entry vanilla has just set EAX = the TAbilityControl and EDX = the ability it built
    for id 0x8C, so the leading `call` finishes vanilla's business unchanged. EBX holds the
    control for the whole of RegisterPassiveAbilities -- 0x557BCE63 `mov eax,ebx`
    immediately before our site is the proof -- which is what `mov eax,ebx` below uses.

    Both runtime addresses are resolved from ONE anchor before any call, because the
    constructor clobbers every volatile register.
    """
    src = """
        call 0x%X
        call 0x%X
        pop  ecx
        mov  eax, ecx
        add  eax, 0x%X
        push eax
        add  ecx, 0x%X
        mov  eax, dword ptr [ecx]
        mov  dl, 1
        call 0x%X
        pop  edx
        push eax
        add  eax, 8
        call 0x%X
        pop  eax
        mov  dword ptr [eax + 0x0C], 0x%X
        mov  edx, eax
        mov  eax, ebx
        call 0x%X
        ret
    """ % (REGISTER_ABIL, va, PH_ABNAME, PH_ABCLS, SLOWENCH_CREATE, LSTRASG,
           ABILITY_ID, REGISTER_ABIL)
    return fix_pic(asm(src, va), va, 0x59,                       # 0x59 = pop ecx
                   [(PH_ABNAME, name_va), (PH_ABCLS, SLOWENCH_CLSPTR)])


# -------------------------------------------------------------- cave_reg_spell
def build_reg_spell(va, name_va):
    """Re-issue the displaced RegisterSpell, then build + register Embrittlement (109).

    Same shape as cave_reg_abil. `xor ecx,ecx` before the constructor mirrors the vanilla
    call sequence in RegisterCombatSpells (`xor ecx,ecx; mov dl,1; mov eax,[classref]`).

    Fields poked after construction, all of them things TSlow.Create sets for Slow:
        +0x10 spell id     +0x14 mana     +0x18 research     +0x20 sphere (byte)
        +0x21 tier (byte)  +0x34 power (byte, vs target Resistance)
    Everything else -- category, range [+0x39], damage-type word [+0x36], the image and
    SFX nodes -- is inherited from TSlow.Create unchanged, which is the entire point of
    cloning the class rather than writing one.
    """
    src = """
        call 0x%X
        call 0x%X
        pop  ecx
        mov  eax, ecx
        add  eax, 0x%X
        push eax
        add  ecx, 0x%X
        mov  eax, dword ptr [ecx]
        xor  ecx, ecx
        mov  dl, 1
        call 0x%X
        pop  edx
        push eax
        add  eax, 8
        call 0x%X
        pop  eax
        mov  dword ptr [eax + 0x10], %d
        mov  dword ptr [eax + 0x14], %d
        mov  dword ptr [eax + 0x18], %d
        mov  byte  ptr [eax + 0x20], %d
        mov  byte  ptr [eax + 0x21], %d
        mov  byte  ptr [eax + 0x34], %d
        mov  edx, eax
        mov  eax, ebx
        call 0x%X
        ret
    """ % (REGISTER_SPELL, va, PH_SPNAME, PH_SPCLS, TSLOW_CREATE, LSTRASG,
           SPELL_ID, MANA_COST, RESEARCH_COST, SPHERE, RESEARCH_TIER, SPELL_POWER,
           REGISTER_SPELL)
    return fix_pic(asm(src, va), va, 0x59,
                   [(PH_SPNAME, name_va), (PH_SPCLS, TSLOW_CLSPTR)])


# -------------------------------------------------------------- cave_createca
def build_createca(va):
    """Replaces `call [ecx+0xA8]` in TSlow.CreateCA: pick the ability id, then refuse
    Physical Immunity targets.

    Entry (all established earlier in TSlow.CreateCA and unchanged since):
        EAX = target combat object      ECX = its VMT        EBX = the CA
        ESI = the spell                 EDI = target combat object

    Returns AL exactly as GetAbilityEnabled would, so the host's `test al,al / jne` is
    untouched. AL=1 means "already has it", which the host reads as "skip the hit roll" --
    that is the fizzle. Clobbers EAX/ECX/EDX only; ESI/EDI/EBX/EBP are preserved.
    """
    src = """
        mov  edx, 0x84
        cmp  dword ptr [esi + 0x10], %d
        jne  have_id
        mov  edx, %d
    have_id:
        call dword ptr [ecx + 0x%X]
        test al, al
        jnz  out
        cmp  dword ptr [esi + 0x10], %d
        jne  out
        mov  eax, edi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x%X]
        test al, 0x%X
        jz   zero
        mov  al, 1
        ret
    zero:
        xor  al, al
    out:
        ret
    """ % (SPELL_ID, ABILITY_ID, VMT_ABIL_ENABLED, SPELL_ID, VMT_IMMUNITY, PHYS_BIT)
    return asm(src, va)


# ---------------------------------------------------------------- cave_absel
def build_absel(va):
    """Replaces `mov edx, 0x84` at both TSlowCA.Execute sites.

    EBX = the CA there (set at 0x557F881D, not rewritten until 0x557F886D), and
    `[CA+0x18]` is the spell id TSlow.CreateCA stamped in at 0x557F89A1.

    Clobbers EDX and flags. Neither host site reads flags across it: 0x557F884F is followed
    by `mov ecx,[eax]` and 0x557F8863 by `call GetAbilityData`.
    """
    src = """
        mov edx, 0x84
        cmp dword ptr [ebx + 0x18], %d
        jne done
        mov edx, %d
    done:
        ret
    """ % (SPELL_ID, ABILITY_ID)
    return asm(src, va)


# ------------------------------------------------------------------ cave_dmg
def build_dmg(va):
    """The doubling. Shared by ExecuteDamageRole and ExecuteDamageRoleEx.

    Entry:  AX = damage-type mask (loaded by the 4-byte prologue each hook site emits,
                because the two functions carry it at different EBP displacements)
            EBX = the combat object being damaged        EDI = the rolled damage
            ESI = ~immunity & mask, LIVE and needed by the host after the call

    Exit:   tail-jumps into GetProtectionTypes so EAX is the protection mask the host
            expects, and the callee's `ret` lands on the padding nop of the hook site.

    ESI/EDI are pushed around the ability query. Delphi's register convention preserves
    EBX/ESI/EDI/EBP, so this is belt-and-braces -- but GetAbilityEnabled reaches
    THero.GetAbilityEnabled through several frames and ESI carrying the immunity mask is
    the single value whose loss would be invisible (damage would simply stop being halved).
    Two bytes to make that unfalsifiable is a good trade.

    ⚠ `add edi,edi` is placed BEFORE the protection call on purpose -- see CANCEL EXACTLY
    in the docstring. Moving it after would break the exact cancellation.
    """
    src = """
        test edi, edi
        jle  orig
        test al, 0x%X
        jz   orig
        push esi
        push edi
        mov  edx, %d
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x%X]
        pop  edi
        pop  esi
        test al, al
        jz   orig
        add  edi, edi
        cmp  edi, %d
        jle  orig
        mov  edi, %d
    orig:
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        jmp  dword ptr [edx + 0x%X]
    """ % (PHYS_BIT, ABILITY_ID, VMT_ABIL_ENABLED, DMG_CLAMP, DMG_CLAMP, VMT_PROTECTION)
    return asm(src, va)


# ------------------------------------------------------------------ cave zone
def build_zone(name_ptr_bias=8, spell_name=None, abil_name=None):
    """Lay every cave out back to back from CAVE, 16-byte aligned, and return
    (blob, [(label, va, code), ...]).

    `name_ptr_bias`, `spell_name` and `abil_name` exist ONLY so a layout this script shipped
    EARLIER can be reproduced byte-for-byte and recognised as a valid pre-state -- see
    PRIOR_ZONES. For a live build the defaults are the only correct values: bias 8, and the
    names above. A name is a variable-length literal, so changing one moves every cave after
    it -- which is exactly why the priors have to carry the old names, not just the old bias.

    Sizes depend on the constants above, so the layout is computed rather than hard-coded:
    a knob change that lengthens one cave must move the ones after it, and a hard-coded
    map would silently overlap.
    """
    blob = bytearray()
    parts = []

    def place(label, builder, align=16):
        nonlocal blob
        pad = (-len(blob)) % align
        blob += bytes(pad)
        va = CAVE + len(blob)
        code = builder(va)
        blob += code
        parts.append((label, va, code))
        return va

    def place_data(label, data, align=4):
        nonlocal blob
        pad = (-len(blob)) % align
        blob += bytes(pad)
        va = CAVE + len(blob)
        blob += data
        parts.append((label, va, None))
        return va

    # The literals are placed FIRST so the caves that point at them already know the address
    # (no two-pass probe needed, unlike build_reformingflesh.py).
    #
    # ⚠⚠ `+ 8` IS LOAD-BEARING AND ITS ABSENCE IS NOT A NO-OP. A Delphi AnsiString variable
    # holds a pointer to the FIRST CHARACTER; the refcount is at ptr-8 and the length at ptr-4.
    # place_data returns the address of the HEADER, so the string pointer is header+8.
    #
    # Passing the header address instead shipped a game that would not launch at all:
    # System.@LStrAsg reads the refcount at (what it thinks is) ptr-8, which was then the zero
    # padding BEFORE the cave. A refcount of 0 is >= 0, i.e. "a live string, not a literal", so
    # LStrAsg InterlockedIncrement'ed it -- a WRITE into the read+execute CODE section, during
    # package init at DLL load. Access violation before any handler exists =
    # **"Runtime error 216 at 00003924"** on startup, from both AoW.exe and the editor.
    # (216 is a GPF. 217 is the duplicate-ability-id error -- see ID_Ceilings.md; do not
    # confuse them when diagnosing.)
    abil_name = ABILITY_NAME if abil_name is None else abil_name
    spell_name = SPELL_NAME if spell_name is None else spell_name
    ab_name_va = place_data("abil name literal", literal(abil_name))
    sp_name_va = place_data("spell name literal", literal(spell_name))
    place("cave_reg_abil", lambda va: build_reg_abil(va, ab_name_va + name_ptr_bias))
    place("cave_reg_spell", lambda va: build_reg_spell(va, sp_name_va + name_ptr_bias))
    place("cave_createca", build_createca)
    place("cave_absel", build_absel)
    place("cave_dmg", build_dmg)

    assert len(blob) <= CAVE_ZONE_LEN, "zone overflow: %d > %d" % (len(blob), CAVE_ZONE_LEN)

    # ---- the guard for the +8 above -----------------------------------------------------
    # Decode the address the assembled cave ACTUALLY resolves for its name literal and assert
    # it lands on the string pointer, not on the header. Written because the off-by-8 shipped
    # a game that would not launch, and neither the assembler, the byte verifier, the .reloc
    # check nor the --undo round-trip could see it: every one of those was perfectly happy.
    # Only running the game found it. This check would have.
    for label, hdr_va in ((("cave_reg_abil", ab_name_va), ("cave_reg_spell", sp_name_va))
                          if name_ptr_bias == 8 else ()):
        code = next(c for l, v, c in parts if l == label)
        base = next(v for l, v, c in parts if l == label)
        i = next(k for k in range(len(code) - 5)                     # the PIC anchor
                 if code[k] == 0xE8 and code[k + 5] == 0x59)         # call ... / pop ecx
        anchor = base + i + 5
        j = code.index(b"\x05", i)                                   # add eax, imm32
        resolved = anchor + struct.unpack_from("<i", code, j + 1)[0]
        assert resolved == hdr_va + 8, (
            "%s resolves its name to %08X; the string POINTER is %08X (header %08X + 8). "
            "A Delphi AnsiString points at the first character -- refcount at ptr-8, length at "
            "ptr-4. Off by 8 here means @LStrAsg refcounts the padding before the cave and "
            "faults on the read-only CODE section: runtime error 216 at startup."
            % (label, resolved, hdr_va + 8, hdr_va))
        assert struct.unpack_from("<i", blob, resolved - 8 - CAVE)[0] == -1, \
            "%s: the dword at ptr-8 is not the -1 literal refcount" % label
    return bytes(blob), parts


ZONE, PARTS = build_zone()

# Every zone layout this script has ever written. Verify-before-write accepts any of them as a
# starting state, so fixing a cave is a REWRITE IN PLACE -- never a revert-and-re-apply, which
# this project forbids because a `.pre-*` restore wipes every feature layered on afterwards.
# Append here whenever a shipped cave changes; never replace.
#   v1 (2026-09-01, ~1h):  name literal passed as its HEADER address instead of header+8.
#                          @LStrAsg refcounted the padding before the cave, wrote to the
#                          read-only CODE section during DLL init, and the game died on launch
#                          with "Runtime error 216 at 00003924". Never worked; no save can
#                          contain spell 109 or ability 0xB2, so there is nothing to migrate.
PRIOR_ZONES = [
    build_zone(name_ptr_bias=0, spell_name=b"Embrittlement")[0],   # v1: the header/+8 bug
    build_zone(spell_name=b"Embrittlement")[0],                    # v2: correct, old name
]

CAVE_REG_ABIL  = next(v for l, v, _ in PARTS if l == "cave_reg_abil")
CAVE_REG_SPELL = next(v for l, v, _ in PARTS if l == "cave_reg_spell")
CAVE_CREATECA  = next(v for l, v, _ in PARTS if l == "cave_createca")
CAVE_ABSEL     = next(v for l, v, _ in PARTS if l == "cave_absel")
CAVE_DMG       = next(v for l, v, _ in PARTS if l == "cave_dmg")


def call_to(site, target):
    return b"\xE8" + struct.pack("<i", target - (site + 5))


def dmg_hook(site, disp):
    """`mov ax,[ebp+disp]` (4 B) + `call cave_dmg` (5 B) + `nop` = the 10 displaced bytes.

    The mask lives at [ebp+8] in ExecuteDamageRole and [ebp+0xC] in ...Ex, so the load is
    per-site and the cave itself stays shared."""
    return bytes.fromhex("668b45") + bytes([disp]) + call_to(site + 4, CAVE_DMG) + b"\x90"


# ---- the complete AoWEPACK.dpl patch set: (VA, new bytes, original bytes, description) ----
DLL_PATCHES = [
    (CAVE, ZONE, bytes(len(ZONE)),
     "cave zone (%d B): %s" % (len(ZONE), ", ".join("%s@%08X" % (l, v) for l, v, _ in PARTS))),
    (REG_ABIL_INJ, call_to(REG_ABIL_INJ, CAVE_REG_ABIL), REG_ABIL_ORIG,
     "RegisterAbility call -> cave_reg_abil (registers %s, id 0x%02X)"
     % (ABILITY_NAME.decode(), ABILITY_ID)),
    (REG_SPELL_INJ, call_to(REG_SPELL_INJ, CAVE_REG_SPELL), REG_SPELL_ORIG,
     "RegisterSpell call -> cave_reg_spell (registers %s, id %d)"
     % (SPELL_NAME.decode(), SPELL_ID)),
    (CREATECA_INJ, call_to(CREATECA_INJ, CAVE_CREATECA) + b"\x90", CREATECA_ORIG,
     "TSlow.CreateCA ability-id select + Physical Immunity fizzle"),
] + [
    (va, call_to(va, CAVE_ABSEL), ABSEL_ORIG,
     "TSlowCA.Execute ability-id select #%d" % (i + 1))
    for i, va in enumerate(ABSEL_INJS)
] + [
    (va, dmg_hook(va, disp), DMG_ORIG, "%s -> cave_dmg" % desc)
    for va, disp, desc in DMG_INJS
]


# ============================================================== file plumbing
def va2off(d, va, base):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    tbl = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    for i in range(nsec):
        s = tbl + 40 * i
        vsz, rva, rsz, ro = struct.unpack_from("<IIII", d, s + 8)
        if base + rva <= va < base + rva + max(vsz, rsz):
            off = ro + (va - base - rva)
            assert off < ro + rsz, "%08X past raw data" % va
            return off
    raise AssertionError("VA %08X in no section" % va)


def reloc_set(d, base):
    """Every VA the loader will fix up. A displaced run that contains one of these cannot
    be overwritten -- the rebase would rewrite our bytes at load time."""
    out = set()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    tbl = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    for i in range(nsec):
        s = tbl + 40 * i
        if d[s:s + 6] == b".reloc":
            vsz, rva, rsz, ro = struct.unpack_from("<IIII", d, s + 8)
            p, end = ro, ro + rsz
            while p + 8 <= end:
                page, sz = struct.unpack_from("<II", d, p)
                if sz < 8 or p + sz > end:
                    break
                for k in range(p + 8, p + sz, 2):
                    e = struct.unpack_from("<H", d, k)[0]
                    if e >> 12:
                        out.add(base + page + (e & 0xFFF))
                p += sz
    return out


def read(path):
    with open(path, "rb") as f:
        return bytearray(f.read())


def state_of(d, patches, base):
    """-> 'applied' | 'vanilla' | 'stale' | 'mixed', plus a per-site verdict list.

    'stale' = a layout THIS script shipped earlier (PRIOR_ZONES). It is a legitimate
    pre-state and is overwritten in place; only 'FOREIGN' -- bytes belonging to neither this
    feature nor vanilla -- aborts, because that means another feature owns the site.
    """
    verdicts = []
    for va, new, orig, desc in patches:
        o = va2off(d, va, base)
        cur = bytes(d[o:o + len(new)])
        priors = PRIOR_ZONES if va == CAVE else ()
        verdicts.append((va, desc,
                         "applied" if cur == new else
                         "vanilla" if cur == orig[:len(new)] or cur == orig else
                         "stale" if any(cur == p[:len(cur)] for p in priors) else "FOREIGN"))
    kinds = {v for _, _, v in verdicts}
    if kinds == {"applied"}:
        return "applied", verdicts
    if kinds == {"vanilla"}:
        return "vanilla", verdicts
    if kinds <= {"applied", "stale"}:
        return "stale", verdicts
    return "mixed", verdicts


def spelltypes_state(d):
    o = va2off(d, SPELLTYPES_VA, TCPCK_BASE)
    donor = d[o + ST_DONOR]
    cur = d[o + SPELL_ID]
    return o, cur, donor


# =================================================================== reporting
def show():
    d = read(DLL)
    st, verdicts = state_of(d, DLL_PATCHES, DLL_BASE)
    relocs = reloc_set(d, DLL_BASE)

    print("build_embrittle -- %s (spell %d) + %s (ability 0x%02X)"
          % (SPELL_NAME.decode(), SPELL_ID, ABILITY_NAME.decode(), ABILITY_ID))
    print("target: %s" % GAME)
    print()
    for va, desc, v in verdicts:
        print("  %08X  %-8s  %s" % (va, v, desc))

    o, cur, donor = spelltypes_state(read(TCPCK))
    print("  %08X  %-8s  AoWTC.SpellTypes[%d] = 0x%02X (donor SpellTypes[%d] = 0x%02X)"
          % (SPELLTYPES_VA + SPELL_ID,
             "applied" if cur == donor else "vanilla" if cur == ST_VANILLA else "FOREIGN",
             SPELL_ID, cur, ST_DONOR, donor))
    print()
    print("  AoWEPACK state: %s   cave zone %08X..%08X (%d B used of %d reserved)"
          % (st.upper(), CAVE, CAVE + CAVE_ZONE_LEN, len(ZONE), CAVE_ZONE_LEN))

    bad = [hex(x) for va, new, _o, _d in DLL_PATCHES if va != CAVE
           for x in relocs if va <= x < va + len(new)]
    print("  .reloc coverage of every displaced run: %s" % (bad or "clean"))
    return st


def disassemble():
    d = read(DLL)
    print()
    for label, va, code in PARTS:
        o = va2off(d, va, DLL_BASE)
        if code is None:
            n = 4 + 4 + len(ABILITY_NAME if "abil" in label else SPELL_NAME) + 1
            print("; ---- %s @%08X (%d B) ----" % (label, va, n))
            print("    %s" % bytes(d[o:o + n]))
            continue
        live = bytes(d[o:o + len(code)])
        # Review the bytes THIS BUILD produces, not whatever is on disk -- before --apply the
        # zone is all zeros and disassembling it prints 60 lines of `add [eax],al`, which is
        # exactly the review the convention asks for made useless. When the live bytes differ
        # AND are not simply an un-applied zero run, print both.
        tag = "" if live == code else ("   (not yet applied)" if set(live) <= {0}
                                       else "   ⚠ LIVE DIFFERS -- shown: THIS BUILD")
        print("; ---- %s @%08X (%d B)%s ----" % (label, va, len(code), tag))
        for ins in cs.disasm(code, va):
            print("  %08X  %-8s %s" % (ins.address, ins.mnemonic, ins.op_str))
    print()
    print("; ---- hook sites (bytes THIS BUILD writes) ----")
    for va, new, _orig, desc in DLL_PATCHES:
        if va == CAVE:
            continue
        for ins in cs.disasm(new, va):
            print("  %08X  %-8s %-28s ; %s" % (ins.address, ins.mnemonic, ins.op_str, desc))
            desc = ""


# ==================================================================== writing
def apply(undo=False):
    kill_aow()
    d = read(DLL)
    st, verdicts = state_of(d, DLL_PATCHES, DLL_BASE)
    foreign = [(va, desc) for va, desc, v in verdicts if v == "FOREIGN"]
    if foreign:
        for va, desc in foreign:
            print("  ABORT: %08X holds neither our bytes nor vanilla -- %s" % (va, desc))
        sys.exit("aborted: another feature owns a site (verify-before-write)")

    want = "vanilla" if undo else "applied"
    if st == want:
        print("  AoWEPACK already %s -- nothing to do" % want)
    else:
        relocs = reloc_set(d, DLL_BASE)
        for va, new, orig, desc in DLL_PATCHES:
            if va != CAVE:
                clash = [x for x in relocs if va <= x < va + len(new)]
                assert not clash, "%08X displaces a .reloc entry %s" % (va, [hex(x) for x in clash])
        if not undo:
            o = va2off(d, CAVE, DLL_BASE)
            zone = bytes(d[o:o + CAVE_ZONE_LEN])
            # all-zero (never applied) or one of OUR earlier layouts (rewrite in place). The
            # tail past the prior blob must still be zero, so a shrinking rewrite cannot leave
            # a stranded fragment and a growing one cannot walk into someone else's zone.
            ok = set(zone) <= {0} or any(zone[:len(p)] == p and set(zone[len(p):]) <= {0}
                                         for p in PRIOR_ZONES)
            assert ok, "cave zone %08X holds bytes that are neither zero nor a layout this " \
                       "script shipped -- someone else is there" % CAVE
        if not os.path.exists(DLL_BACKUP):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(DLL, DLL_BACKUP)
            print("  backup -> %s" % os.path.basename(DLL_BACKUP))
        for va, new, orig, desc in DLL_PATCHES:
            o = va2off(d, va, DLL_BASE)
            blob = orig if undo else new
            d[o:o + len(blob)] = blob
        with open(DLL, "wb") as f:
            f.write(d)
        print("  AoWEPACK.dpl  %s  (%d sites + cave zone)"
              % ("REVERTED" if undo else "PATCHED", len(DLL_PATCHES) - 1))

    t = read(TCPCK)
    o, cur, donor = spelltypes_state(t)
    tgt = ST_VANILLA if undo else donor
    if cur == tgt:
        print("  AoWTCPCK SpellTypes[%d] already 0x%02X -- nothing to do" % (SPELL_ID, tgt))
    elif cur not in (ST_VANILLA, donor):
        sys.exit("  ABORT: SpellTypes[%d] = 0x%02X, neither vanilla nor ours" % (SPELL_ID, cur))
    else:
        if not os.path.exists(TCPCK_BACKUP):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(TCPCK, TCPCK_BACKUP)
            print("  backup -> %s" % os.path.basename(TCPCK_BACKUP))
        t[o + SPELL_ID] = tgt
        with open(TCPCK, "wb") as f:
            f.write(t)
        print("  AoWTCPCK.dpl  SpellTypes[%d] 0x%02X -> 0x%02X" % (SPELL_ID, cur, tgt))

    print()
    if undo:
        print("  reverted. Re-run the two ceiling scripts to drop their bound back to 0xB2:")
        print("      python build_scripts/build_abilityid_ceilings.py --apply")
        print("      python build_scripts/build_tcablist_ceiling.py  --apply")
        print("  (and remove 0xB2 from re_tools/ability_names.py MODDED)")
        return
    print("  NEXT -- these are NOT optional, and their failure mode is silence, not a crash:")
    print("      python build_scripts/build_abilityid_ceilings.py --apply")
    print("      python build_scripts/build_tcablist_ceiling.py  --apply")
    print("      python \"Modding Resources/re_tools/rng_audit.py\" --owners     # expect: ok")
    print()
    print("  NEEDS THE USER'S IN-GAME TEST -- nothing below can be checked from the files:")
    print("   1. %s appears in the Earth sphere, tier %d, of the research list."
          % (SPELL_NAME.decode(), RESEARCH_TIER))
    print("   2. Once researched it is castable IN TACTICAL COMBAT at a single enemy unit")
    print("      (%d mana), and lands or is resisted like Slow." % MANA_COST)
    print("   3. A unit it hits shows \"%s\" in its ability list for the rest of that"
          % ABILITY_NAME.decode())
    print("      combat, and the status is GONE at the start of the next battle.")
    print("   4. A melee hit on that unit does ROUGHLY DOUBLE its normal damage.")
    print("   5. On a unit that also has Physical Protection, damage is back to NORMAL.")
    print("   6. Casting it at a Physical Immunity unit does nothing (the mana is still")
    print("      spent -- that is the documented fizzle, not a bug).")
    print("   7. Slow still works exactly as before, on its own spell and its own status.")
    print("   8. Auto-resolve a battle with an embrittled unit -- no assert dialog.")


if __name__ == "__main__":
    args = set(sys.argv[1:])
    if args - {"--apply", "--undo", "--dis"}:
        sys.exit(__doc__.split("EFFECT")[0])
    if "--undo" in args:
        show(); apply(undo=True)
    elif "--apply" in args:
        show(); apply()
    else:
        show()
        disassemble()
        print()
        print("(dry run -- nothing written.  --apply to patch, --undo to revert)")
