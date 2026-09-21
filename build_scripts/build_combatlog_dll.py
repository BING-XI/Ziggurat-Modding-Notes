#!/usr/bin/env python3
r"""
AoW1 mod -- COMBAT LOG, DLL side (capture + line formatting).  v2 = natural language.
Companion of build_combatlog_exe.py (which hosts the ring buffer + the TCombatLogWin window).
Design + all decoded combat math: Modding Resources/Combat_Log_Implementation_Design.md (§0 especially).

LINE FORMAT (v2, user-chosen "natural + stats", no A/D side markers, no unit numbers):
    Elf Ranger hits Elephant for 1 damage  (60%, atk 6 vs def 3)
    Elephant hits back at Elf Ranger for 2 damage  (30%, atk 2 vs def 4)
    Azrac Yaka Avatar CRITS Elephant for 6 damage  (80%, atk 7 vs def 3)
    Elephant misses Elf Ranger - fumble  (30%, atk 2 vs def 4)
    High Priest hits Zombie for 8 damage +poisoned  (50%, atk 9 vs res 4)
    Elf Ranger hits Fire Elemental - immune  (60%, atk 6 vs def 3)

HOOKS (7):
 1/2. tails of the two roll funnels -- every damage-bearing CA passes through exactly one:
      TDamageCA.Generate   @0x55729C20, epilogue @0x55729C8C (5 pops) -> stub_gen   -> ret 0xC  @0x55729C91
      TDamageCA.GenerateEx @0x55729C98, epilogue @0x55729D08 (5 pops) -> stub_genex -> ret 0x10 @0x55729D0D
      Frame at the epilogue (identical in both): EBX=CA, ESI=target, [EBP-4]=attacker,
      attack sbyte @[EBP+0x10] (Gen) / @[EBP+0x14] (GenEx); GenEx's extra byte @[EBP+8].
 3.   the RandInt(20) call inside AoWE.ExecuteDamageRole @0x55725EBC -> cave_roll, which records the
      roll R so crit/fumble can be reported EXACTLY. (rolled==max cannot identify the auto-max branch:
      formula rounding also reaches max ~15-20% of the time -- it would ~2x over-report.)
 4.   Turn Undead's inlined stage-1 roll: call HitRole @0x5576B55C -> cave_touch (v8 -- a stage-1 miss
      never reaches GenerateEx, so it was invisible before this).
 5-7. the v9 touch-family unit (trole): entry TTouchAbility.CombatTouchRole @0x557681B0 + its two
      roll sites @0x557681D6 / @0x55768216 ("missed" vs "resisted").
      build_touchlog_gate.py toggles hooks 4-7 without rebuilding the cave.

DECODED MECHANICS USED (see design doc §0 for the full derivation):
 * hit% = clamp(50 + 10*(attack - defstat), 10, 90)   -- pure linear, no table. Inlined (28 B) rather
   than calling HitRoleProbability@0x55725DCC, which returns a float and would need a writable temp.
 * AoWE.ExecuteDamageRole @0x55725EAC: R=RandInt(20); R<=1 -> AUTO-MISS (flat 10%, ignores attack);
   R>=18 -> AUTO-MAX (flat 10%, bypasses the to-hit check) = what the user calls a "critical".
   AoW1 has NO named crit mechanic (zero `crit` bytes in any binary).
 * WHICH DEFENSIVE STAT: Generate rolls vs GetDefense (target vmt+0x70); GenerateEx rolls vs
   GetResistance (vmt+0x74) IFF its extra byte==1, else GetDefense.  <-- v1 printed def unconditionally,
   which was WRONG for Turn Undead / combat spells. Fixed here (stub_genex computes useRes).
 * IMMUNE is free: word[CA+0x11] == 0  => target immune to every incoming type (roll returned 0 early).
 * EFFECT LANDINGS: word[CA+0x13], same bit positions as the damage types:
      0x01 fire->burning · 0x02 cold->frozen · 0x04 lightning->stunned · 0x08 magic->(none)
      0x10 poison->poisoned · 0x20 death->cursed · 0x40 holy->vertigo · 0x80 physical->(none)
 * retaliation = byte[CA+0x0c] bit0; rolled damage = byte[CA+0x10] (0 = miss).
NOT reported (deliberate, user decision 2026-07-16): per-ability bonus attribution (Monster Slaying/
Champion/Assassin/True Seeing/Charge/Parry). The atk/dam printed ALREADY include every bonus; itemising
them would need tag bits inside 6 confirmed-working caves (see design doc). CA+0x18 strike flags
(panicked/entangled/lifesteal) are also out: they are set by TStrikeCA.Generate AFTER the base returns,
so they read 0 at these hooks -- would need a 4th hook at TStrikeCA.Generate's exit @0x55766969.
FAST-COMBAT GATE RESTORED 2026-07-22 (see the FAST-COMBAT gate section below): auto-resolved battles are
NOT logged live -- logging during TFastCombatWindow's animation aborted the animated action; replay lines
come from build_replaylog.py instead.

Strings: names via strategic GetName (unit vmt+0xF8; unit = combatObj+0x4c, may be NIL -> "?");
numbers via SysUtils.IntToStr thunk 0x5570158C; assembly via @LStrLAsg/@LStrCat thunks; all LStr temps
stack-zeroed first and @LStrArrayClr'd after (Delphi ref rules). Cave-embedded literals use refcount -1
so the VCL never writes/frees them (safe in an RX cave).
PIC: one call/pop anchor (EDI); every literal/table/BSS ref is anchor-relative (the DPL rebases). The
only absolute addresses are the EXE's (0x40003C / 0x60Dxxx) -- correct, AoW.exe is fixed-base.
Host guard (the DLL also loads in AoWDevEd.exe): exe SizeOfImage >= 0x20E000 AND magic 'CLG1' @0x60D000.

Idempotent, verify-before-write, backup <game dir>\backups\AoWEPACK.dpl.pre-clogtypegate, dry-run
/ --apply.
REVERT: NOT by snapshot. Restoring a whole-file .pre-* wipes every feature applied after it, and
there is no snapshot layer at all now (both stacks were purged, 2026-08-08 and 2026-09-09). This
script has no --undo flag: back it out by hand, restoring the original bytes listed in `patches`.
"""
import sys, os, shutil, struct
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

def load_sections(data):
    e=struct.unpack_from("<I",data,0x3C)[0]; n=struct.unpack_from("<H",data,e+6)[0]
    op=struct.unpack_from("<H",data,e+20)[0]; s=e+24+op; secs=[]
    for i in range(n):
        vs,va,rs,raw=struct.unpack_from("<IIII",data,s+8); secs.append((va,vs,raw,rs)); s+=40
    return secs
def mkva2off(base):
    def f(secs,va):
        rva=va-base
        for va0,vs,raw,rs in secs:
            if va0<=rva<va0+max(vs,rs): return raw+(rva-va0)
        raise ValueError(hex(va))
    return f
def rel32(src,dst): return struct.pack("<i",dst-(src+5))

DLL_BASE  = 0x55700000
GEN_HOOK  = 0x55729C8C; GEN_RET   = 0x55729C91      # ret 0xC
GENEX_HOOK= 0x55729D08; GENEX_RET = 0x55729D0D      # ret 0x10
POPS      = bytes.fromhex("5f5e5b595d")             # pop edi/esi/ebx/ecx/ebp
ROLL_HOOK = 0x55725EBC                              # `call RandInt` inside ExecuteDamageRole
RANDINT   = 0x55701080
# vanilla bytes = `call RANDINT`. MUST be a computed constant, never read from the live file:
# reading it would make the "already applied" re-check compare the patched bytes against themselves.
ROLL_ORIG = b"\xE8"+struct.pack("<i",RANDINT-(ROLL_HOOK+5))
# DLL thunks (rel32-callable from a cave; all rebase together)
INTTOSTR  = 0x5570158C   # eax=int, edx=@out LStr
LSTRLASG  = 0x55701158   # eax=@dest, edx=src value
LSTRCAT   = 0x55701188   # eax=@dest, edx=src value  -> dest := dest+src
LSTRARRCLR= 0x55701148   # eax=@first, edx=count
GETNAME_V = 0xF8         # strategic-unit VMT slot: GetName(eax=unit, edx=@out LStr)

# ---- combat-object TYPE GATE (bugfix 2026-07-22) -------------------------------------------------
# `combatObj+0x4C` is the strategic-unit back-pointer -- but ONLY on TCombatUnit. Instance sizes:
#   TCombatObject 0x4C · TCombatUnit 0x5C (adds the unit link at +0x4C) · TCombatWall 0x50
# TCombatWall reuses that same +0x4C for its OWN packed bytes (TCombatWall.Setup writes a setup byte
# at +0x4C and hitpoints at +0x4D), so on a wall the "unit pointer" is a small integer like 0x1403.
# The old code only NIL-checked it, which a nonzero small integer passes, then did `mov ecx,[eax]`
# and called through it -> access violation inside the combat pump -> the TE aborts, both armies are
# lost, the combat never finalizes and the game FREEZES (sound still running).
# Reached whenever anything damages a WALL: a wall-crushing attacker vs a walled city. The raze
# rework's wall-less battles had masked this for weeks; AI fast-combat city assaults exposed it.
# Fix: verify the object really IS a TCombatUnit before trusting +0x4C; otherwise fall through to the
# existing "?" fallback, so the line still logs with a placeholder name instead of crashing.
IS_CLASS        = 0x557010C0   # System.@IsClass thunk: EAX=obj, EDX=classref VALUE -> AL (ret 0)
TCOMBATUNIT_VMT = 0x55715A94   # TCombatUnit VMT base (== [0x55715A54]); reach via the cave's delta
TCOMBATSPELLCA_VMT = 0x557F3CC8  # TCombatSpellCA VMT base (classref cell 0x557F3C88 holds it; selfptr
                               # at VMT-64 verified). Descends TDamageCA and does NOT override
                               # Generate/GenerateEx (VMT+0x68/+0x6C still = 0x55729C20/0x55729C98),
                               # so damaging spells already arrive at our epilogue hooks.
                               # TTurnUndeadSpellCA descends from it -> covered by @IsClass for free;
                               # the Turn Undead ABILITY CA (TTurnUndeadCA) does not -> excluded.
AOWHSSET   = 0x558FA044        # AoWE.AoWHSSet global (a POINTER cell); TSpellControl at +0x84
SPELLCTRL_OFF = 0x84
GETSPELL   = 0x55779AC8        # TSpellControl.GetSpell(eax=ctrl, edx=id) -> eax=TSpell (0 if id>=count)
                               # ⚠ RAISES a Delphi range error on a NEGATIVE id -- never pass one.
SPELL_NAME = 0x08              # TSpell+0x08 = the spell name, a plain LStr VALUE (not a VMT call)
TCOMBATWALL_VMT = 0x55715C40   # TCombatWall VMT base (classname shortstring @0x55715D74, selfptr
                               # verified at VMT-64). Walls have no strategic unit, so they can never
                               # go through GetName -- they get the literal "Wall" instead of "?".

# ---- FAST-COMBAT gate (bugfix 2026-07-22) --------------------------------------------------------
# Logging during AUTO-RESOLVED battles makes cave_drain SetVisible(1) our cloned log window while
# TFastCombatWindow is animating. Both are TAOWWindows in aowInt.dpl's blit list, and the clone's
# rect is derived for the map screen -- the resulting blit raises **"Blt Error"** (the string lives in
# aowInt.dpl beside TAOWWindowControl.Blt). FastCombatWin's handler catches it and ABORTS the action
# it was animating, so e.g. a wall-crush never applies its damage. With a melee-only stack that can
# stall the battle permanently: nothing else can breach the wall.
# v3 deliberately DROPPED the original fast-combat gate ("autocombat logged on purpose so replays
# have content") having found it inert. It was inert because of a `mov edx,[0x5571D4BC]` where the
# AoWE..TFoo export IS the VMT -- it needed `lea`. Restored here, correctly, with lea-via-delta.
# The reason it was dropped is now obsolete: build_replaylog.py (confirmed working 2026-07-21) emits
# replay lines from TDamageCA.Play, so replays get content without logging live autocombat.
# TFastCombatUnit DERIVES from TCombatUnit, so the type gate above does NOT exclude it -- this is a
# separate, explicit check.
TFASTCOMBATUNIT_VMT = 0x5571D4BC   # VMT BASE (verified: [0x5571D4BC] is not a VMT -- do NOT deref)
# exe-side ring (fixed base 0x400000; never rebases)
RING=0x60D000; WR=RING+4; RD=RING+8; SLOTS=RING+0x20
MAGIC=0x31474C43         # 'CLG1'
# ⚠ SLOT_SZ/SLOTS_N are HALF of a wire format shared with build_combatlog_exe.py (which reads these
# slots back). A mismatch is silent and vicious -- see that file's comment. Cross-checked below.
SLOT_SZ=128; SLOTS_N=64
def _check_wire():
    import re
    p=os.path.join(os.path.dirname(os.path.abspath(__file__)),"build_combatlog_exe.py")
    try: t=open(p).read()
    except OSError: return
    m=re.search(r"RING_SLOTS\s*=\s*(\d+);\s*SLOT_SZ\s*=\s*(\d+)",t)
    assert m, "cannot find RING_SLOTS/SLOT_SZ in build_combatlog_exe.py"
    n,sz=int(m.group(1)),int(m.group(2))
    assert (n,sz)==(SLOTS_N,SLOT_SZ), (
        f"WIRE-FORMAT MISMATCH: dll has slots={SLOTS_N} size={SLOT_SZ}, exe has slots={n} size={sz}. "
        "Both scripts must agree, and BOTH must be re-applied after any change.")
_check_wire()
SCRATCH_R = 0x558FA810   # DLL BSS page slack (0x800 simfly / 804,808,80C raze) -- see design doc

# ---- v3: MISSED TOUCH ATTACKS -------------------------------------------------------------------
# A touch attack (Turn Undead et al) is a TWO-stage roll:
#   stage 1  attacker.GetAttack (vmt+0x6c) vs target.GetDefense (vmt+0x70) -> AoWE.HitRole
#   stage 2  only if stage 1 HIT: GenerateEx -> ExecuteDamageRoleEx vs RESISTANCE (what we already log)
# CreateTurnUndeadCA @0x5576B528 branches `je 0x5576B5A5` on a stage-1 miss and NEVER calls GenerateEx,
# so a missed touch never reached the log at all, and the stage-1 ATK-vs-DEF was never reported.
# Hook stage 1's `call HitRole` @0x5576B55C. Registers there (verified):
#   EAX = attack-defense · EDX = defense · ESI = attacker · EBP = target · EDI = the CA · EBX = ability
# On a miss we REUSE the normal worker (no duplicate formatter) by handing it the fresh CA:
#   CA+0x10 (damage) is still 0        -> worker takes its "misses" path      (correct)
#   CA+0x0c bit0 is 0                  -> not flagged as a retaliation        (correct)
#   CA+0x11 (types) is still 0         -> worker would wrongly say "- immune" -> we temporarily force it
#                                         to 0xFFFF and RESTORE it (the field feeds the miss animation)
#   SCRATCH_R                          -> forced to -1 so no bogus "- fumble" tag
# useRes=0 so the worker re-reads GetDefense and prints "N ATK vs N DEF" = the real stage-1 roll.
TOUCH_HOOK = 0x5576B55C
TOUCH_ORIG = b"\xE8"+struct.pack("<i",0x55725D98-(TOUCH_HOOK+5))   # call AoWE.HitRole
HITROLE    = 0x55725D98

# ---- v9: THE WHOLE TOUCH FAMILY (Possess / Charm / Seduce / Dominate / Web / ...) ---------------
# 16 classes descend from TTouchAbility and NOT ONE overrides CombatTouchRole (VMT slot +0x110), so a
# single hook on that function covers the entire family:
#   TCharmAbility TCommandAbility TDispelMagicAbility TDominateAbility TEntangleAbility THealingAbility
#   TInvokeDeathAbility TPossessAbility TPossessedAbility TRoundAttackAbility TSeduceAbility
#   TSelfDestructAbility TTouchAbility TTurnUndeadAbility TWallCrushingAbility TWebAbility
# `TPossessAbility.CreatePossessCA@0x55769BEC` and `TWebAbility.CreateWebCA@0x5576A210` both dispatch
# `call [ebx+0x110]` and feed the result to their CA's Initialize. (CreateHealingCA does NOT roll --
# healing always lands. TTurnUndeadAbility is the odd one out: it INLINES the roll, hence TOUCH_HOOK above.)
#
# CombatTouchRole(eax=self ability, edx=attacker combat obj, ecx=target combat obj) -> AL = success.
# It is itself a TWO-ROLL gate -- both must pass:
#   ROLL 1 @0x557681D6  attacker.GetAttack(vmt+0x6c) - target.GetDefense(vmt+0x70)  -> HitRole
#   ROLL 2 @0x55768216  self.GetTouchAttack(vmt+0x10c) - target.GetResistance(vmt+0x74) -> HitRole
# so a failure is either "missed" (couldn't connect) or "resisted" -- distinct outcomes worth logging.
# Both roll sites have the identical `sub eax,edx` / `call HitRole` shape as Turn Undead:
#   EAX = diff (atk-stat) · EDX = the opposing stat.  We capture each into BSS scratch, then the entry
# trampoline builds one line from the captured stages.
TOUCHROLE   = 0x557681B0
TROLE_ORIG  = bytes.fromhex("53565751890c24")     # push ebx/esi/edi/ecx; mov [esp],ecx  (7 B, relocatable)
TROLE_CONT  = 0x557681B7
TR1_HOOK    = 0x557681D6                          # ROLL 1 (vs DEF)
TR2_HOOK    = 0x55768216                          # ROLL 2 (vs RES)
TR1_ORIG    = b"\xE8"+struct.pack("<i",HITROLE-(TR1_HOOK+5))
TR2_ORIG    = b"\xE8"+struct.pack("<i",HITROLE-(TR2_HOOK+5))
GETNAME_A   = 0x58        # TAbility.GetName(eax=self, ecx=@out) -- = @LStrLAsg(out,[self+8])
# BSS scratch (page slack; 0x800 simfly, 0x804/808/80C raze, 0x810 SCRATCH_R -- see the design doc)
SC_T1 = 0x558FA820        # roll1: +0 ok(-1 = not rolled) +4 diff +8 stat
SC_T2 = 0x558FA82C        # roll2: same layout

# RELOCATED 2026-07-22 from 0x5580E440. The old comment ("free to ~0x5580F400, 3.5 KB") was already
# false when written: build_tierresearch_dll.py put cave_grant at 0x5580ED80, leaving this feature
# only 2368 B -- and the image was 2372 B, so it had been overlapping its neighbour's first 4 bytes
# (harmless padding, but it made verify report "cave zone not free" forever, which is how the feature
# became un-reappliable). Adding the TCombatUnit type gate takes it to ~2446 B, so applying in place
# would have overwritten cave_grant outright.
# The 0x5580Cxxx-0x5580Fxxx pocket is crowded; the genuinely free space is the ~880 KB tail from
# 0x55810000 (see the cave-space measurement in the project notes). Occupancy there: aipickup
# 0x55810000.., combatdiag probe 0x55810400.. -- 0x55811000+ verified all-zero for 8 KB.
LEGACY_CAVE     = 0x5580E440   # old home; vacate with --vacate (see below)
LEGACY_LIMIT    = 0x5580ED80   # tierresearch cave_grant -- never write at or past this
CAVE = 0x55811000        # verified zeroed; nearest neighbour is the diag probe below 0x55810C00

LIT = [
    ("HITS",      " hits "),
    ("HITSBACK",  " hits back at "),
    ("CRITS",     " CRITS "),
    ("CRITSBACK", " CRITS back at "),
    ("MISSES",    " misses "),
    ("MISSBACK",  " misses back at "),
    ("FOR",       " for "),
    ("DAMAGE",    " damage"),
    ("FUMBLE",    " - fumble"),
    ("IMMUNE",    " - immune"),
    ("OPEN",      "  ("),
    ("PCT",       "%, "),
    ("ATKVS",     " ATK vs "),
    ("VSDEF",     " DEF)"),
    ("VSRES",     " RES)"),
    ("UNKNOWN",   "?"),
    ("WALL",      "Wall"),
    ("CASTS",     " casts "),
    ("ONTGT",     " on "),
    ("BUTMISS",   " but misses "),
    ("E0",        " +burning"),
    ("E1",        " +frozen"),
    ("E2",        " +stunned"),
    ("E4",        " +poisoned"),
    ("E5",        " +cursed"),
    ("E6",        " +vertigo"),
    # v9 touch-family sentence: "<A> Possesses <D>" / "<A> fails to Possess <D> - resisted"
    ("SP",        " "),
    ("FAILSTO",   " fails to "),
    ("SUFS",      "s"),           # Charm -> Charms
    ("SUFES",     "es"),          # Possess -> Possesses   (name ends in s/x/z)
    ("MISSED",    " - missed"),   # roll 1 failed: never connected
    ("RESISTED",  " - resisted"), # roll 1 passed, roll 2 failed
]
def lstr_const(s):
    b=s.encode("latin1")
    return struct.pack("<ii",-1,len(b))+b+b"\x00"

APPLY="--apply" in sys.argv
# --no-touch: leave the two damage-funnel tails + the roll capture in place, but point the THREE
# touch-family hooks back at stock. Added 2026-07-22: a bisection of the backup stack converged on
# this feature (combatlog) as the cause of a hang in TFastCombatUnit.fcExecute, and the failing
# battle is a WALL-CRUSHING basilisk against a walled city. TWallCrushing is one of the 16 abilities
# whose CombatTouchRole is caught by the v9 entry hook at 0x557681B0, which makes those three the
# prime suspects. Run with no flag to put them back.
NO_TOUCH="--no-touch" in sys.argv
VACATE="--vacate" in sys.argv    # also zero the pre-relocation cave at LEGACY_CAVE

def build(path):
    data=bytearray(open(path,"rb").read()); secs=load_sections(data); va2off=mkva2off(DLL_BASE)
    def rd_(va,n): o=va2off(secs,va); return bytes(data[o:o+n])

    # ---- layout pass: assemble with placeholder deltas to size everything ----
    def emit(anchor, lit_va, efx_va):
        L={n:lit_va+off for n,off in lit_off.items()}
        def d(n): return L[n]+8-anchor            # literal VALUE ptr, anchor-relative
        def cu():                                 # TCombatUnit classref, EDI-anchor-relative
            o=TCOMBATUNIT_VMT-anchor
            return f"[edi + 0x{o:X}]" if o>=0 else f"[edi - 0x{-o:X}]"
        def cw():                                 # TCombatWall classref, same base
            o=TCOMBATWALL_VMT-anchor
            return f"[edi + 0x{o:X}]" if o>=0 else f"[edi - 0x{-o:X}]"
        def csc():                                # TCombatSpellCA classref, same base
            o=TCOMBATSPELLCA_VMT-anchor
            return f"[edi + 0x{o:X}]" if o>=0 else f"[edi - 0x{-o:X}]"
        def g(addr):                              # a module GLOBAL's cell, anchor-relative
            o=addr-anchor
            return f"[edi + 0x{o:X}]" if o>=0 else f"[edi - 0x{-o:X}]"
        def verbcat(tag, conn):
            """Append the verb and the target name. EDX holds the melee verb literal on entry.

            For a TCombatSpellCA, substitute ' casts <Spell><conn>' so a spell reads as a spell
            rather than as an identical-looking melee swing. Damaging spells already reached this
            worker (TCombatSpellCA inherits TDamageCA.Generate/GenerateEx unoverridden) -- they
            were simply never LABELLED, which is what "spell casts are not recorded" meant.

            ⚠ CA+0x18 is the spell id on TCombatSpellCA ONLY. TStrikeCA reuses that offset for
            strike flags, so an ungated read yields a garbage id -- and GetSpell RAISES a Delphi
            range error on a negative one, inside the combat pump. Same trap family as
            combatObj+0x4C. Every step below is failure-tolerant: any nil//out-of-range result
            falls back to the plain melee verb rather than risking an exception in the pump."""
            return f"""
            mov  [ebp-0x30], edx              /* stash the verb; @IsClass clobbers EDX */
            mov  eax, ebx
            lea  edx, {csc()}
            call 0x{IS_CLASS:X}
            test al, al
            jz   _vp{tag}
            mov  eax, [ebx+0x18]              /* spell id -- valid only past the gate above */
            test eax, eax
            js   _vp{tag}                     /* negative would RAISE inside GetSpell */
            mov  edx, eax
            mov  eax, {g(AOWHSSET)}
            test eax, eax
            jz   _vp{tag}
            mov  eax, [eax+0x{SPELLCTRL_OFF:X}]
            test eax, eax
            jz   _vp{tag}
            call 0x{GETSPELL:X}
            test eax, eax
            jz   _vp{tag}
            mov  edx, [eax+0x{SPELL_NAME:X}]
            test edx, edx
            jz   _vp{tag}
            lea  eax, [ebp-0x2C]              /* hold a counted ref while the line is built */
            call 0x{LSTRLASG:X}
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('CASTS'):X}]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x2C]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d(conn):X}]
            call 0x{LSTRCAT:X}
            jmp  _vt{tag}
        _vp{tag}:
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x30]
            call 0x{LSTRCAT:X}
        _vt{tag}:
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x18]
            call 0x{LSTRCAT:X}
        """
        def notunit(obj, slot, tag):
            """Non-TCombatUnit name fallback: 'Wall' for a TCombatWall, else '?'.
            Reached only when the +0x4C type gate rejected the object, so it must NOT touch +0x4C."""
            return f"""
            mov  eax, {obj}
            test eax, eax
            jz   _uq{tag}
            lea  edx, {cw()}
            call 0x{IS_CLASS:X}
            test al, al
            jz   _uq{tag}
            lea  eax, [ebp-0x{slot:X}]
            lea  edx, [edi + 0x{d('WALL'):X}]
            call 0x{LSTRLASG:X}
            jmp  _ud{tag}
        _uq{tag}:
            lea  eax, [ebp-0x{slot:X}]
            lea  edx, [edi + 0x{d('UNKNOWN'):X}]
            call 0x{LSTRLASG:X}
        _ud{tag}:
        """
        def fcu():                                # TFastCombatUnit classref, EDI-anchor-relative
            o=TFASTCOMBATUNIT_VMT-anchor
            return f"[edi + 0x{o:X}]" if o>=0 else f"[edi - 0x{-o:X}]"
        src=f"""
        _worker:
            push ebp
            mov  ebp, esp
            sub  esp, 0x40
            push ebx
            push esi
            push edi
            mov  [ebp-0x04], eax
            mov  [ebp-0x08], ecx
            mov  [ebp-0x0C], edx
            xor  eax, eax
            mov  [ebp-0x10], eax
            mov  [ebp-0x14], eax
            mov  [ebp-0x18], eax
            mov  [ebp-0x1C], eax
            mov  [ebp-0x2C], eax          /* spell-name LStr; cleared separately at _clean */
            call _anch
        _anch:
            pop  edi
            mov  eax, [0x40003C]
            cmp  dword ptr [eax+0x400050], 0x20E000
            jb   _bail
            cmp  dword ptr [0x{RING:X}], 0x{MAGIC:X}
            jne  _bail
            mov  eax, [0x{WR:X}]
            sub  eax, [0x{RD:X}]
            cmp  eax, {SLOTS_N-1}
            jae  _bail
            /* fast-combat gate: never log an auto-resolved battle (see TFASTCOMBATUNIT_VMT note).
               Check attacker then target -- in a fast combat at least one is a TFastCombatUnit, and
               the target alone is not enough because it can be a TCombatWall. */
            mov  eax, [ebp-0x0C]
            test eax, eax
            jz   _fc2
            lea  edx, {fcu()}
            call 0x{IS_CLASS:X}
            test al, al
            jnz  _bail
        _fc2:
            mov  eax, esi
            test eax, eax
            jz   _fcok
            lea  edx, {fcu()}
            call 0x{IS_CLASS:X}
            test al, al
            jnz  _bail
        _fcok:
            mov  eax, [edi + 0x{SCRATCH_R-anchor:X}]
            mov  [ebp-0x20], eax
            mov  dword ptr [edi + 0x{SCRATCH_R-anchor:X}], -1
            mov  eax, esi
            mov  edx, [eax]
            mov  ecx, [ebp-0x08]
            test ecx, ecx
            jz   _usedef
            call dword ptr [edx+0x74]
            jmp  _gotdef
        _usedef:
            call dword ptr [edx+0x70]
        _gotdef:
            movsx eax, al
            mov  [ebp-0x24], eax
            mov  eax, [ebp-0x04]
            sub  eax, [ebp-0x24]
            add  eax, eax
            imul eax, eax, 5
            add  eax, 0x32
            cmp  eax, 0xA
            jge  _p1
            mov  eax, 0xA
        _p1:
            cmp  eax, 0x5A
            jle  _p2
            mov  eax, 0x5A
        _p2:
            mov  [ebp-0x28], eax
            mov  eax, [ebp-0x0C]
            test eax, eax
            jz   _n1u
            lea  edx, {cu()}
            call 0x{IS_CLASS:X}
            test al, al
            jz   _n1u
            mov  eax, [ebp-0x0C]
            mov  eax, [eax+0x4C]
            test eax, eax
            jz   _n1u
            lea  edx, [ebp-0x14]
            mov  ecx, [eax]
            call dword ptr [ecx+0x{GETNAME_V:X}]
            jmp  _n2
        _n1u:
            {notunit("[ebp-0x0C]", 0x14, "a")}
        _n2:
            mov  eax, esi
            test eax, eax
            jz   _n2u
            lea  edx, {cu()}
            call 0x{IS_CLASS:X}
            test al, al
            jz   _n2u
            mov  eax, esi
            mov  eax, [eax+0x4C]
            test eax, eax
            jz   _n2u
            lea  edx, [ebp-0x18]
            mov  ecx, [eax]
            call dword ptr [ecx+0x{GETNAME_V:X}]
            jmp  _mkline
        _n2u:
            {notunit("esi", 0x18, "b")}
        _mkline:
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x14]
            call 0x{LSTRLASG:X}
            movzx eax, byte ptr [ebx+0x10]
            test eax, eax
            jz   _miss
            mov  eax, [ebp-0x20]
            cmp  eax, 18
            jl   _hitnorm
            test byte ptr [ebx+0x0C], 1
            jnz  _v_critback
            lea  edx, [edi + 0x{d('CRITS'):X}]
            jmp  _v_go
        _v_critback:
            lea  edx, [edi + 0x{d('CRITSBACK'):X}]
            jmp  _v_go
        _hitnorm:
            test byte ptr [ebx+0x0C], 1
            jnz  _v_hitback
            lea  edx, [edi + 0x{d('HITS'):X}]
            jmp  _v_go
        _v_hitback:
            lea  edx, [edi + 0x{d('HITSBACK'):X}]
        _v_go:
            {verbcat("h","ONTGT")}
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('FOR'):X}]
            call 0x{LSTRCAT:X}
            movzx eax, byte ptr [ebx+0x10]
            lea  edx, [ebp-0x1C]
            call 0x{INTTOSTR:X}
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x1C]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('DAMAGE'):X}]
            call 0x{LSTRCAT:X}
            movzx ecx, word ptr [ebx+0x13]
            xor  edx, edx
        _efx:
            test ecx, 1
            jz   _efxn
            mov  eax, [edi + 0x{efx_va-anchor:X} + edx*4]
            test eax, eax
            jz   _efxn
            add  eax, edi
            push ecx
            push edx
            mov  edx, eax
            lea  eax, [ebp-0x10]
            call 0x{LSTRCAT:X}
            pop  edx
            pop  ecx
        _efxn:
            shr  ecx, 1
            inc  edx
            cmp  edx, 8
            jl   _efx
            jmp  _stats
        _miss:
            test byte ptr [ebx+0x0C], 1
            jnz  _v_missback
            lea  edx, [edi + 0x{d('MISSES'):X}]
            jmp  _mv_go
        _v_missback:
            lea  edx, [edi + 0x{d('MISSBACK'):X}]
        _mv_go:
            {verbcat("m","BUTMISS")}
            cmp  word ptr [ebx+0x11], 0
            jne  _misschk
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('IMMUNE'):X}]
            call 0x{LSTRCAT:X}
            jmp  _stats
        _misschk:
            mov  eax, [ebp-0x20]
            test eax, eax
            js   _stats
            cmp  eax, 1
            jg   _stats
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('FUMBLE'):X}]
            call 0x{LSTRCAT:X}
        _stats:
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('OPEN'):X}]
            call 0x{LSTRCAT:X}
            mov  eax, [ebp-0x28]
            lea  edx, [ebp-0x1C]
            call 0x{INTTOSTR:X}
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x1C]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('PCT'):X}]
            call 0x{LSTRCAT:X}
            mov  eax, [ebp-0x04]
            lea  edx, [ebp-0x1C]
            call 0x{INTTOSTR:X}
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x1C]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('ATKVS'):X}]
            call 0x{LSTRCAT:X}
            mov  eax, [ebp-0x24]
            lea  edx, [ebp-0x1C]
            call 0x{INTTOSTR:X}
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x1C]
            call 0x{LSTRCAT:X}
            mov  ecx, [ebp-0x08]
            test ecx, ecx
            jz   _vd
            lea  edx, [edi + 0x{d('VSRES'):X}]
            jmp  _vgo
        _vd:
            lea  edx, [edi + 0x{d('VSDEF'):X}]
        _vgo:
            lea  eax, [ebp-0x10]
            call 0x{LSTRCAT:X}
            mov  eax, [ebp-0x10]
            test eax, eax
            jz   _clean
            mov  ecx, [eax-4]
            cmp  ecx, {SLOT_SZ-1}
            jbe  _len
            mov  ecx, {SLOT_SZ-1}
        _len:
            mov  edx, [0x{WR:X}]
            and  edx, {SLOTS_N-1}
            shl  edx, {SLOT_SZ.bit_length()-1}
            add  edx, 0x{SLOTS:X}
            mov  [edx], cl
            mov  esi, eax
            lea  edi, [edx+1]
            cld
            rep  movsb
            mov  eax, [0x{WR:X}]
            inc  eax
            mov  [0x{WR:X}], eax
        _clean:
            lea  eax, [ebp-0x1C]
            mov  edx, 4
            call 0x{LSTRARRCLR:X}
            lea  eax, [ebp-0x2C]
            mov  edx, 1
            call 0x{LSTRARRCLR:X}
        _bail:
            pop  edi
            pop  esi
            pop  ebx
            mov  esp, ebp
            pop  ebp
            ret
        """
        return bytes(ks.asm(src,CAVE)[0])

    # literal pool offsets
    lit_off={}; pool=b""
    for n,s in LIT:
        lit_off[n]=len(pool); pool+=lstr_const(s)

    # two-pass: size worker, then place pool/table and re-emit
    w0=emit(CAVE+5, CAVE+0x1000, CAVE+0x2000)
    def layout(wlen):
        stub_gen_va = CAVE+((wlen+15)&~15)
        return stub_gen_va
    sg_va=layout(len(w0))
    def stub_src(va,atk_off,ret_va,ex):
        pre = (f"movzx ecx, byte ptr [ebp+8]\n cmp ecx,1\n sete cl\n movzx ecx, cl\n" if ex else "xor ecx, ecx\n")
        return f"""
            movsx eax, byte ptr [ebp+{atk_off:#x}]
            mov   edx, [ebp-4]
            {pre}
            call  0x{CAVE:X}
            pop edi
            pop esi
            pop ebx
            pop ecx
            pop ebp
            jmp 0x{ret_va:X}
        """
    sg0=bytes(ks.asm(stub_src(sg_va,0x10,GEN_RET,False),sg_va)[0])
    sx_va=sg_va+((len(sg0)+7)&~7)
    sx0=bytes(ks.asm(stub_src(sx_va,0x14,GENEX_RET,True),sx_va)[0])
    roll_va=sx_va+((len(sx0)+7)&~7)
    def roll_src(va,anchor):
        return f"""
            call 0x{RANDINT:X}
            push edx
            call _ra
        _ra:
            pop  edx
            mov  [edx + 0x{SCRATCH_R-anchor:X}], eax
            pop  edx
            ret
        """
    r0=bytes(ks.asm(roll_src(roll_va,roll_va),roll_va)[0])
    ra_idx=r0.find(b"\xe8\x00\x00\x00\x00\x5a")
    assert ra_idx>=0
    roll_anchor=roll_va+ra_idx+5
    roll=bytes(ks.asm(roll_src(roll_va,roll_anchor),roll_va)[0])
    assert len(roll)==len(r0)

    # ---- cave_touch: stage-1 touch roll (see the TOUCH_HOOK notes at the top) --------------------
    # in: EAX=attack-defense EDX=defense ESI=attacker EBP=target EDI=CA  ·  out: AL=hit (as HitRole)
    touch_va=roll_va+((len(roll)+7)&~7)
    def touch_src(anchor):
        return f"""
            push edx
            push eax
            call 0x{HITROLE:X}
            push eax
            test al, al
            jnz  _tdone
            call _ta
        _ta:
            pop  eax
            mov  dword ptr [eax + 0x{SCRATCH_R-anchor:X}], -1
            mov  eax, [esp+4]
            add  eax, [esp+8]
            movzx ecx, word ptr [edi+0x11]
            push ecx
            mov  word ptr [edi+0x11], 0xFFFF
            push ebx
            push esi
            mov  edx, esi
            mov  ebx, edi
            mov  esi, ebp
            xor  ecx, ecx
            call 0x{CAVE:X}
            pop  esi
            pop  ebx
            pop  ecx
            mov  [edi+0x11], cx
        _tdone:
            pop  eax
            add  esp, 8
            ret
        """
    t0=bytes(ks.asm(touch_src(touch_va),touch_va)[0])
    ta_idx=t0.find(b"\xe8\x00\x00\x00\x00\x58")
    assert ta_idx>=0, "touch anchor (call/pop eax) not found"
    touch=bytes(ks.asm(touch_src(touch_va+ta_idx+5),touch_va)[0])
    assert len(touch)==len(t0)

    # ---- v9: the touch-family unit (entry trampoline + 2 roll captures + sentence builder) --------
    # One assembled unit, one PIC anchor (edi), two-pass like the worker.
    trole_va=touch_va+((len(touch)+15)&~15)
    # This unit has FOUR independent call/pop anchors (entry, troll1, troll2, tworker), so every
    # PIC delta must be taken from ITS OWN base -- one shared base silently corrupts three of them.
    def trole_emit(a0, aa1, aa2, a1, lit_va2):
        L2={n:lit_va2+off for n,off in lit_off.items()}
        def d(n):   return L2[n]+8-a1     # literals are only read where edi = the _anch1 base
        def cu():                         # TCombatUnit classref, relative to the SAME (_anch1) base
            o=TCOMBATUNIT_VMT-a1
            return f"[edi + 0x{o:X}]" if o>=0 else f"[edi - 0x{-o:X}]"
        def cw():                         # TCombatWall classref, same base
            o=TCOMBATWALL_VMT-a1
            return f"[edi + 0x{o:X}]" if o>=0 else f"[edi - 0x{-o:X}]"
        def notunit(obj, slot, tag):      # see the worker's copy; literals/classrefs use the a1 base
            return f"""
            mov  eax, {obj}
            test eax, eax
            jz   _uq{tag}
            lea  edx, {cw()}
            call 0x{IS_CLASS:X}
            test al, al
            jz   _uq{tag}
            lea  eax, [ebp-0x{slot:X}]
            lea  edx, [edi + 0x{d('WALL'):X}]
            call 0x{LSTRLASG:X}
            jmp  _ud{tag}
        _uq{tag}:
            lea  eax, [ebp-0x{slot:X}]
            lea  edx, [edi + 0x{d('UNKNOWN'):X}]
            call 0x{LSTRLASG:X}
        _ud{tag}:
        """
        def fcu():                        # TFastCombatUnit classref, same base
            o=TFASTCOMBATUNIT_VMT-a1
            return f"[edi + 0x{o:X}]" if o>=0 else f"[edi - 0x{-o:X}]"
        def sc(a):  return a-a1           # _tworker / _tstats  (edi)
        def sc0(a): return a-a0           # _entry              (edi)
        def sc1(a): return a-aa1          # _troll1             (edx)
        def sc2(a): return a-aa2          # _troll2             (edx)
        return f"""
        _entry:
            push ebp
            mov  ebp, esp
            push ebx
            push esi
            push edi
            push ecx
            push edx
            push eax
            call _anch0
        _anch0:
            pop  edi
            mov  dword ptr [edi + 0x{sc0(SC_T1):X}], -1
            mov  dword ptr [edi + 0x{sc0(SC_T2):X}], -1
            mov  eax, [ebp-0x18]
            mov  edx, [ebp-0x14]
            mov  ecx, [ebp-0x10]
            call _stub_orig
            movzx ebx, al
            mov  eax, [ebp-0x18]
            mov  edx, [ebp-0x14]
            mov  ecx, [ebp-0x10]
            push ebx
            call _tworker
            mov  eax, ebx
            lea  esp, [ebp-0x0C]
            pop  edi
            pop  esi
            pop  ebx
            pop  ebp
            ret
        _stub_orig:
            push ebx
            push esi
            push edi
            push ecx
            mov  [esp], ecx
            jmp  0x{TROLE_CONT:X}
        _troll1:
            push ebp
            mov  ebp, esp
            push ecx
            push edx
            push eax
            call 0x{HITROLE:X}
            movzx eax, al
            push eax
            call _a1
        _a1:
            pop  edx
            pop  eax
            mov  [edx + 0x{sc1(SC_T1):X}], eax
            mov  ecx, [ebp-0x0C]
            mov  [edx + 0x{sc1(SC_T1+4):X}], ecx
            mov  ecx, [ebp-0x08]
            mov  [edx + 0x{sc1(SC_T1+8):X}], ecx
            mov  esp, ebp
            pop  ebp
            ret
        _troll2:
            push ebp
            mov  ebp, esp
            push ecx
            push edx
            push eax
            call 0x{HITROLE:X}
            movzx eax, al
            push eax
            call _a2
        _a2:
            pop  edx
            pop  eax
            mov  [edx + 0x{sc2(SC_T2):X}], eax
            mov  ecx, [ebp-0x0C]
            mov  [edx + 0x{sc2(SC_T2+4):X}], ecx
            mov  ecx, [ebp-0x08]
            mov  [edx + 0x{sc2(SC_T2+8):X}], ecx
            mov  esp, ebp
            pop  ebp
            ret
        _tworker:
            push ebp
            mov  ebp, esp
            sub  esp, 0x40
            push ebx
            push esi
            push edi
            mov  [ebp-0x04], eax
            mov  [ebp-0x08], edx
            mov  [ebp-0x0C], ecx
            xor  eax, eax
            mov  [ebp-0x10], eax
            mov  [ebp-0x14], eax
            mov  [ebp-0x18], eax
            mov  [ebp-0x1C], eax
            mov  [ebp-0x20], eax
            call _anch1
        _anch1:
            pop  edi
            mov  eax, [0x40003C]
            cmp  dword ptr [eax+0x400050], 0x20E000
            jb   _tbail
            cmp  dword ptr [0x{RING:X}], 0x{MAGIC:X}
            jne  _tbail
            mov  eax, [0x{WR:X}]
            sub  eax, [0x{RD:X}]
            cmp  eax, {SLOTS_N-1}
            jae  _tbail
            /* fast-combat gate -- same reasoning as the worker's (see TFASTCOMBATUNIT_VMT). */
            mov  eax, [ebp-0x08]
            test eax, eax
            jz   _tfc2
            lea  edx, {fcu()}
            call 0x{IS_CLASS:X}
            test al, al
            jnz  _tbail
        _tfc2:
            mov  eax, [ebp-0x0C]
            test eax, eax
            jz   _tfcok
            lea  edx, {fcu()}
            call 0x{IS_CLASS:X}
            test al, al
            jnz  _tbail
        _tfcok:
            mov  eax, [ebp-0x08]
            test eax, eax
            jz   _tnau
            lea  edx, {cu()}
            call 0x{IS_CLASS:X}
            test al, al
            jz   _tnau
            mov  eax, [ebp-0x08]
            mov  eax, [eax+0x4C]
            test eax, eax
            jz   _tnau
            lea  edx, [ebp-0x14]
            mov  ecx, [eax]
            call dword ptr [ecx+0x{GETNAME_V:X}]
            jmp  _tnd
        _tnau:
            {notunit("[ebp-0x08]", 0x14, "c")}
        _tnd:
            mov  eax, [ebp-0x0C]
            test eax, eax
            jz   _tndu
            lea  edx, {cu()}
            call 0x{IS_CLASS:X}
            test al, al
            jz   _tndu
            mov  eax, [ebp-0x0C]
            mov  eax, [eax+0x4C]
            test eax, eax
            jz   _tndu
            lea  edx, [ebp-0x18]
            mov  ecx, [eax]
            call dword ptr [ecx+0x{GETNAME_V:X}]
            jmp  _tab
        _tndu:
            {notunit("[ebp-0x0C]", 0x18, "d")}
        _tab:
            mov  eax, [ebp-0x04]
            test eax, eax
            jz   _tabu
            lea  ecx, [ebp-0x20]
            mov  edx, [eax]
            call dword ptr [edx+0x{GETNAME_A:X}]
            jmp  _tline
        _tabu:
            lea  eax, [ebp-0x20]
            lea  edx, [edi + 0x{d('UNKNOWN'):X}]
            call 0x{LSTRLASG:X}
        _tline:
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x14]
            call 0x{LSTRLASG:X}
            cmp  dword ptr [ebp+8], 0
            je   _tmiss
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('SP'):X}]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x20]
            call 0x{LSTRCAT:X}
            mov  eax, [ebp-0x20]
            test eax, eax
            jz   _tsufs
            mov  edx, [eax-4]
            test edx, edx
            jz   _tsufs
            movzx edx, byte ptr [eax+edx-1]
            cmp  edx, 0x73
            je   _tsufes
            cmp  edx, 0x78
            je   _tsufes
            cmp  edx, 0x7A
            je   _tsufes
        _tsufs:
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('SUFS'):X}]
            call 0x{LSTRCAT:X}
            jmp  _tsp2
        _tsufes:
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('SUFES'):X}]
            call 0x{LSTRCAT:X}
        _tsp2:
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('SP'):X}]
            call 0x{LSTRCAT:X}
            jmp  _ttgt
        _tmiss:
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('FAILSTO'):X}]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x20]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('SP'):X}]
            call 0x{LSTRCAT:X}
        _ttgt:
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x18]
            call 0x{LSTRCAT:X}
            mov  eax, [edi + 0x{sc(SC_T1):X}]
            cmp  eax, -1
            je   _tst2
            mov  eax, [edi + 0x{sc(SC_T1+4):X}]
            mov  edx, [edi + 0x{sc(SC_T1+8):X}]
            xor  ecx, ecx
            call _tstats
        _tst2:
            mov  eax, [edi + 0x{sc(SC_T2):X}]
            cmp  eax, -1
            je   _ttag
            mov  eax, [edi + 0x{sc(SC_T2+4):X}]
            mov  edx, [edi + 0x{sc(SC_T2+8):X}]
            mov  ecx, 1
            call _tstats
        _ttag:
            cmp  dword ptr [ebp+8], 0
            jne  _temit
            mov  eax, [edi + 0x{sc(SC_T1):X}]
            cmp  eax, 1
            je   _tresist
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('MISSED'):X}]
            call 0x{LSTRCAT:X}
            jmp  _temit
        _tresist:
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('RESISTED'):X}]
            call 0x{LSTRCAT:X}
        _temit:
            mov  eax, [ebp-0x10]
            test eax, eax
            jz   _tclean
            mov  ecx, [eax-4]
            cmp  ecx, {SLOT_SZ-1}
            jbe  _tlen
            mov  ecx, {SLOT_SZ-1}
        _tlen:
            mov  edx, [0x{WR:X}]
            and  edx, {SLOTS_N-1}
            shl  edx, {SLOT_SZ.bit_length()-1}
            add  edx, 0x{SLOTS:X}
            mov  [edx], cl
            mov  esi, eax
            lea  edi, [edx+1]
            cld
            rep  movsb
            mov  eax, [0x{WR:X}]
            inc  eax
            mov  [0x{WR:X}], eax
        _tclean:
            lea  eax, [ebp-0x20]
            mov  edx, 5
            call 0x{LSTRARRCLR:X}
        _tbail:
            pop  edi
            pop  esi
            pop  ebx
            mov  esp, ebp
            pop  ebp
            ret  4
        _tstats:
            mov  [ebp-0x24], eax
            mov  [ebp-0x28], edx
            mov  [ebp-0x2C], ecx
            add  eax, eax
            imul eax, eax, 5
            add  eax, 0x32
            cmp  eax, 0xA
            jge  _tsp1
            mov  eax, 0xA
        _tsp1:
            cmp  eax, 0x5A
            jle  _tsp3
            mov  eax, 0x5A
        _tsp3:
            mov  [ebp-0x30], eax
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('OPEN'):X}]
            call 0x{LSTRCAT:X}
            mov  eax, [ebp-0x30]
            lea  edx, [ebp-0x1C]
            call 0x{INTTOSTR:X}
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x1C]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('PCT'):X}]
            call 0x{LSTRCAT:X}
            mov  eax, [ebp-0x24]
            add  eax, [ebp-0x28]
            lea  edx, [ebp-0x1C]
            call 0x{INTTOSTR:X}
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x1C]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x10]
            lea  edx, [edi + 0x{d('ATKVS'):X}]
            call 0x{LSTRCAT:X}
            mov  eax, [ebp-0x28]
            lea  edx, [ebp-0x1C]
            call 0x{INTTOSTR:X}
            lea  eax, [ebp-0x10]
            mov  edx, [ebp-0x1C]
            call 0x{LSTRCAT:X}
            cmp  dword ptr [ebp-0x2C], 0
            jz   _tsvd
            lea  edx, [edi + 0x{d('VSRES'):X}]
            jmp  _tsvg
        _tsvd:
            lea  edx, [edi + 0x{d('VSDEF'):X}]
        _tsvg:
            lea  eax, [ebp-0x10]
            call 0x{LSTRCAT:X}
            ret
        """
    # pass 1: dummy bases far enough away that every displacement encodes as disp32 (so the size is
    # stable across passes); then locate the four anchors and re-emit with the real bases.
    _dummy=trole_va+0x4000
    tr0=bytes(ks.asm(trole_emit(_dummy,_dummy,_dummy,_dummy, trole_va+0x4000),trole_va)[0])
    def _finds(b,pat,n):
        out=[]; i=-1
        for _ in range(n):
            i=b.find(pat,i+1)
            assert i>=0, f"trole anchor {pat.hex()} #{len(out)+1} not found"
            out.append(i)
        return out
    edis=_finds(tr0,b"\xe8\x00\x00\x00\x00\x5f",2)   # call/pop edi : _anch0 then _anch1
    edxs=_finds(tr0,b"\xe8\x00\x00\x00\x00\x5a",2)   # call/pop edx : _a1 then _a2
    A0,A1 = trole_va+edis[0]+5, trole_va+edis[1]+5
    AA1,AA2 = trole_va+edxs[0]+5, trole_va+edxs[1]+5
    trole_lit_va=trole_va+((len(tr0)+15)&~15)
    trole=bytes(ks.asm(trole_emit(A0,AA1,AA2,A1, trole_lit_va),trole_va)[0])
    assert len(trole)==len(tr0), ("trole size moved between passes",len(trole),len(tr0))
    # the anchors must not have shifted now that the real (smaller) deltas are in
    assert _finds(trole,b"\xe8\x00\x00\x00\x00\x5f",2)==edis and \
           _finds(trole,b"\xe8\x00\x00\x00\x00\x5a",2)==edxs, "trole anchors moved between passes"

    lit_va=trole_lit_va
    efx_va=lit_va+((len(pool)+3)&~3)

    # final worker emit with real addresses
    a_idx=w0.find(b"\xe8\x00\x00\x00\x00\x5f")
    assert a_idx>=0
    anchor=CAVE+a_idx+5
    worker=emit(anchor, lit_va, efx_va)
    assert len(worker)==len(w0), (len(worker),len(w0))

    # effects table: bit index 0..7 -> (literal VALUE ptr - anchor) or 0
    efx=b""
    for i in range(8):
        key={0:"E0",1:"E1",2:"E2",4:"E4",5:"E5",6:"E6"}.get(i)
        efx += struct.pack("<i",(lit_va+lit_off[key]+8-anchor) if key else 0)

    img=bytearray()
    def put(va,b):
        off=va-CAVE
        while len(img)<off: img.append(0)
        img[off:off+len(b)]=b
    put(CAVE,worker); put(sg_va,sg0); put(sx_va,sx0); put(roll_va,roll); put(touch_va,touch)
    put(trole_va,trole); put(lit_va,pool); put(efx_va,efx)
    # Trim trailing alignment padding. `put` zero-fills up to each component's start, so the image
    # can end with pad bytes this feature never uses -- and it then CLAIMS them. build_tierresearch_dll.py
    # placed cave_grant at 0x5580ED80 having measured our last used byte as 0x5580ED7D, which put its
    # prologue inside our 4 trailing pad bytes. Result: verify reported "cave zone not free" forever and
    # the feature became un-reappliable (an orphan). Writing only what we actually use fixes that and
    # stops us silently overwriting a neighbour on the next apply.
    while img and img[-1]==0:
        img.pop()
    img=bytes(img)
    # Entry offsets inside the trole unit. Source order is _entry, _stub_orig, _troll1, _troll2,
    # _tworker -- all but _stub_orig open with `push ebp; mov ebp,esp`, so take that prologue from
    # _entry itself (offset 0) rather than hard-coding an encoding keystone may or may not pick.
    _pro=trole[0:3]
    _pbs=[]; _i=-1
    while True:
        _i=trole.find(_pro,_i+1)
        if _i<0: break
        _pbs.append(_i)
    assert len(_pbs)>=4 and _pbs[0]==0, ("trole prologue scan failed",_pbs)
    TR_ENTRY, TR_TROLL1, TR_TROLL2 = trole_va, trole_va+_pbs[1], trole_va+_pbs[2]
    # cross-check troll1 against the independent stub_orig path (7 relocated bytes + jmp rel32)
    _so=trole.find(TROLE_ORIG); assert _so>0, "stub_orig not found in trole"
    assert TR_TROLL1==trole_va+_so+len(TROLE_ORIG)+5, ("troll1 mislocated",hex(TR_TROLL1))
    # and that each troll's own anchor falls inside it
    assert TR_TROLL1 < AA1 < TR_TROLL2 and AA2 > TR_TROLL2, "troll anchors outside their bodies"

    patches=[
        (CAVE, bytes(len(img)), img,
         f"cave_combatlog v3 (worker@{CAVE:08X} stubs@{sg_va:08X}/{sx_va:08X} roll@{roll_va:08X} "
         f"touch@{touch_va:08X} lit@{lit_va:08X} efx@{efx_va:08X})"),
        (GEN_HOOK,   POPS, b"\xE9"+rel32(GEN_HOOK,  sg_va), "TDamageCA.Generate epilogue -> stub_gen"),
        (GENEX_HOOK, POPS, b"\xE9"+rel32(GENEX_HOOK,sx_va), "TDamageCA.GenerateEx epilogue -> stub_genex"),
        (ROLL_HOOK, ROLL_ORIG, b"\xE8"+rel32(ROLL_HOOK,roll_va), "ExecuteDamageRole RandInt call -> cave_roll (capture R)"),
        (TOUCH_HOOK, TOUCH_ORIG, b"\xE8"+rel32(TOUCH_HOOK,touch_va),
         "CreateTurnUndeadCA stage-1 HitRole -> cave_touch (log missed touches w/ ATK vs DEF)"),
        (TOUCHROLE, TROLE_ORIG, b"\xE9"+rel32(TOUCHROLE,TR_ENTRY)+b"\x90\x90",
         "TTouchAbility.CombatTouchRole entry -> cave_touchrole (whole touch family)"),
        (TR1_HOOK, TR1_ORIG, b"\xE8"+rel32(TR1_HOOK,TR_TROLL1), "CombatTouchRole roll 1 (vs DEF) -> capture"),
        (TR2_HOOK, TR2_ORIG, b"\xE8"+rel32(TR2_HOOK,TR_TROLL2), "CombatTouchRole roll 2 (vs RES) -> capture"),
    ]
    if VACATE:
        # Zero the pre-relocation cave so space scans stop seeing 2.3 KB of orphaned code. Bounded
        # strictly BELOW LEGACY_LIMIT (build_tierresearch_dll.py's cave_grant), which must survive.
        _n = LEGACY_LIMIT - LEGACY_CAVE
        assert CAVE >= LEGACY_LIMIT or CAVE + len(img) <= LEGACY_CAVE, "new cave overlaps legacy zone"
        _cur = rd_(LEGACY_CAVE, _n)
        if any(_cur):
            patches.append((LEGACY_CAVE, _cur, bytes(_n),
                            f"vacate legacy cave {LEGACY_CAVE:08X}..{LEGACY_LIMIT:08X} ({_n} B)"))

    if NO_TOUCH:
        # Swap the three touch entries so the CURRENT (hooked) bytes are the accepted prior and the
        # STOCK bytes are what we write. The cave itself is left intact -- the touch code inside it
        # simply stops being reachable, so this is reversible by re-running with no flag.
        _off = {TOUCHROLE, TR1_HOOK, TR2_HOOK}
        patches = [p for p in patches if p[0] not in _off] + [
            (TOUCHROLE, b"\xE9"+rel32(TOUCHROLE,TR_ENTRY)+b"\x90\x90", TROLE_ORIG,
             "CombatTouchRole entry -> STOCK (touch-family logging OFF)"),
            (TR1_HOOK, b"\xE8"+rel32(TR1_HOOK,TR_TROLL1), TR1_ORIG,
             "CombatTouchRole roll 1 -> STOCK"),
            (TR2_HOOK, b"\xE8"+rel32(TR2_HOOK,TR_TROLL2), TR2_ORIG,
             "CombatTouchRole roll 2 -> STOCK"),
        ]
    print(f"worker {len(worker)} B · stubs {len(sg0)}/{len(sx0)} · roll {len(roll)} · touch {len(touch)} "
          f"· trole {len(trole)} · lit {len(pool)} · efx {len(efx)} · total {len(img)} B @ {CAVE:08X}")
    print(f"  trole: entry@{TR_ENTRY:08X} troll1@{TR_TROLL1:08X} troll2@{TR_TROLL2:08X} "
          f"anchors {A0:08X}/{AA1:08X}/{AA2:08X}/{A1:08X}")
    print(f"  anchor={anchor:08X} SCRATCH_R={SCRATCH_R:08X} slot={SLOT_SZ}B x{SLOTS_N}")

    live=rd_(CAVE,len(img))
    # A cave that is ALREADY OURS must be overwritable, or the feature can never be revised in place
    # (that is exactly how the old 0x5580E440 image became an un-reappliable orphan). Nobody else
    # hooks TDamageCA.Generate's epilogue, so a non-stock epilogue proves this cave is ours.
    _ours = rd_(GEN_HOOK,len(POPS)) != POPS
    if _ours and live!=img:
        print(f"[i ] cave at {CAVE:08X} is our own earlier build -- overwriting in place")
    if live!=img and any(b!=0 for b in live) and not _ours:
        # A bare "not free" tells you nothing about WHY, which cost a whole session: the installed
        # image had diverged from what this script rebuilds and there was no way to see where.
        # Report the divergence so an orphaned cave can be diagnosed instead of guessed at.
        diff=[i for i in range(len(img)) if live[i]!=img[i]]
        print(f"[x] cave zone {CAVE:08X} not free -- {len(diff)} of {len(img)} bytes differ")
        print(f"     first difference at +0x{diff[0]:X}  (VA {CAVE+diff[0]:08X})")
        print(f"     live: {live[diff[0]:diff[0]+16].hex(' ')}")
        print(f"     want: {img [diff[0]:diff[0]+16].hex(' ')}")
        runs=[];cur=diff[0];prev=diff[0]
        for i in diff[1:]:
            if i-prev>8: runs.append((cur,prev)); cur=i
            prev=i
        runs.append((cur,prev))
        print(f"     differing regions ({len(runs)}): "
              + ", ".join(f"+0x{a:X}..+0x{b:X}" for a,b in runs[:8]))
        return False
    if all(rd_(va,len(new))==new for va,_o,new,_d in patches):
        print("[= ] already applied"); return True
    ok=True
    for va,orig,new,desc in patches:
        cur=rd_(va,len(new))
        # When the cave is already ours, its internal stub/trole addresses MOVE whenever the image
        # is revised or relocated, so the live hooks legitimately point at our previous build rather
        # than at `orig` (stock) or `new`. Accept any existing call/jmp at one of OUR OWN hook sites
        # -- nothing else in the project writes them -- otherwise a revision can never be applied.
        if cur!=orig and cur!=new and _ours:
            continue
        if cur!=orig and cur!=new:
            ok=False; print(f"[!] {va:08X} ({desc})\n     exp {orig[:16].hex(' ')}\n     got {cur[:16].hex(' ')}")
    if not ok: print("[x] mismatch -- not written"); return False
    if not APPLY: print("[dry] originals verified, cave zone free"); return True
    # Feature-named per apply-generation, so each change gets its own one-layer backup instead of
    # everything hiding behind a 2026-07-07 snapshot that is now ~20 layers deep and unusable.
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bp=os.path.join(BACKUP_DIR, os.path.basename(path)+".pre-clogtypegate")
    if not os.path.exists(bp): shutil.copy2(path,bp); print(f"[bak] {bp}")
    for va,orig,new,desc in patches:
        o=va2off(secs,va); data[o:o+len(new)]=new; print(f"[w ] {va:08X} {desc}")
    try: open(path,"wb").write(data)
    except PermissionError: print("[x] LOCKED -- close AoW binaries"); return False
    return True

print()
ok=build(os.path.join(GAME,"AoWEPACK.dpl"))
print("\n[dry-run] Re-run with --apply to write." if not APPLY
      else ("\n[done] Applied. Revert is NOT a .pre-* restore: a snapshot is a whole-file copy, so"
            "\n       putting one back silently destroys every feature applied after it was taken."
            "\n       Back this out by hand instead."
            if ok else "\n[!] not applied"))
