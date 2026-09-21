#!/usr/bin/env python3
r"""
AoW1 mod -- NEW ability "Assassin" (= Hero Slaying): +5 attack / +5 damage on a MELEE strike vs a HERO.
PHASE 1 of the slayer work (melee + registration). PHASE 2 (the RANGED branch for Assassin AND the
existing Monster Slaying / Holy&Unholy Champion) is build_ranged_slayers.py. Idea credit: modder "Inioch".

MECHANISM (template = Dragon/Monster Slaying, verified): melee "slayer" bonuses are hard-coded in
`CreateStrikeCA` @0x557665e4 -- each `if attacker.GetAbilityEnabled(X) && target-matches -> attack+=N,
damage+=N`. There EBP=attacker, ESI=target, EBX(BL)=attack, [ESP+3]=damage; the Monster Slaying block
(0x70 vs marker 0x3f, +3/+3) sits at 0x557666a1..0x557666ce, then the CA is built at 0x557666cf.

Assassin needs NO "Hero" marker ability -- heroes are the THero class (like Holy/Unholy Champion key off
the built-in alignment). The hero test is `guard_hero(target)` from combatunitguard.py.

AoW1 keeps TWO parallel melee slayer tables, so the melee bonus needs TWO hooks:
  * the global CreateStrikeCA @0x557665e4 -- used by Round Attack / attack-of-opportunity / ability strikes.
  * TMeleeRound.CalculateStrikes @0x55767b24 -- the combat-object twin a DELIBERATE melee attack uses
    (TStrikeAbility.fcExecuteCombatCommand -> TMeleeRound.Calculate -> CalculateStrikes). Hooking only the
    first left deliberate attacks unbuffed while opportunities worked -- the symptom that exposed the twin.
  (A third twin, CalculateUnitStrikes @0x557677cc, works on the STRATEGIC units for the opportunity/predictor
   path; it is NOT the deliberate-attack copy, so we do not hook it.)

╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║ ⚠⚠ THE WALL CRASH -- fixed 2026-09-11, and the false premise that caused it                  ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
This file used to claim, verbatim:

    "CreateStrikeCA's callers are all melee-strike commands (RoundAttack/Possess/Web/... -- never
     walls), so combat+0x4c is a valid unit-or-null; the null-check covers the rest."

**That is wrong. A wall is a legal melee target**, and it reached both caves. `+0x4C` exists only on
`TCombatUnit`; `TCombatWall` (instsize 0x50, a sibling of TCombatUnit under TCombatObject) reuses
those four bytes for PACKED DATA -- `+0x4C` = wall type, `+0x4D` = wall HP. Ziggurat's stone wall
(type 2, HP 40) therefore reads back as the dword `0x00002802`, a small NON-ZERO integer that walks
straight through `test eax,eax` and into `System.@IsClass`, which has no validity test on a non-nil
pointer -- it goes straight to `mov eax,[eax]` to read the VMT. ⚠ @IsClass IS nil-safe (entry
0x41303A14 = `test eax,eax / je`; the export RVA is 14868 = 0x3A14). The defect class is a GARBAGE
object pointer, not a nil one. 0x41303A18 is the LOOP BODY -- the back-edge target of the `jne` at
0x41303A23 -- which is why it is the reported fault address. Captured live:

    Exception EAccessViolation in module VCL30.dpl at 00003A18. Read of address 00002802.
    (then, as fallout: "Combat already created." at AoWEPACK.dpl 000787AE -- the AV aborts the TE,
     the half-built combat is never torn down, and the next CreateCombat trips its own guard.
     Chasing that second dialog is a dead end; it is a symptom, not a second bug.)

Only units carrying Assassin (0x38) could trigger it -- Orc Assassin, Shadow -- which is why it
looked like a unit-specific bug rather than a wall bug.

FIX: both caves now call `guard_hero` in the shared cave `combatunitguard.py` installs at
0x55849000. It does `IsClass(obj, TCombatUnit)` **before** touching `+0x4C`, so a wall (or a nil,
or any future TCombatObject descendant) returns AL=0 and the vanilla no-bonus path is taken.
TFastCombatUnit descends from TCombatUnit, so auto-resolve keeps the bonus.

⭐ WHY A HELPER CALL AND NOT AN IN-PLACE BYTE SPLICE. `mov eax,[reg+0x4c]; test eax,eax; je skip`
is 7 bytes and `mov eax,<reg>; call helper` is also 7, so a surgical splice would have fitted. It
was not used because the requirement -- and CLAUDE.md's re-tuning rule -- is that the SOURCE must
stop being able to emit the broken bytes, so the cave GENERATORS are fixed and the bodies are
regenerated whole. The regenerated bodies are then shorter, so they are nop-padded to their pinned
lengths (below) to hold 0x5580E0E0 / 0x5580E10C / 0x5580E120. Magebane's half of the same fix has a
harder constraint of the same kind -- build_shield.py asserts on an absolute address inside its
cave -- and that is documented there.

The identical defect was found and fixed in build_magebane.py's three strike caves at the same time;
build_ranged_slayers.py, build_replaylog.py and build_combatlog_dll.py already had the correct
ordering and are the model.

THREE OWN CAVES + ONE SHARED (no new DLL):
  cave_melee   @0x5580E070, 106 B  -- round-attack / opportunity / ability-strike melee bonus. Hooks the
                  Monster-Slaying block start @0x557666a1 (global CreateStrikeCA); REPLAYS Monster
                  Slaying (0x70/0x3f) and adds the Assassin block, then jmp 0x557666cf.
  cave_asnreg  @0x5580E0E0        -- hooks the last strike RegisterAbility call @0x557675c4 (MagicStrike);
                  re-issues that register (displaced), then CreateEnhancementAbility(ASSASSIN,"Assassin",
                  icon)@0x5576601c + RegisterAbility. EBX = the ability-control throughout FUN_557672b4.
                  (The strike factory 0x5576727c registered fine but its ability failed combat
                  GetAbilityEnabled -- see ENH_FACTORY.)
  name literal @0x5580E10C ("Assassin" AnsiString, value ptr 0x5580E114)
  cave_melee3  @0x5580E120, 104 B  -- DELIBERATE-attack melee bonus. Hooks the Monster-Slaying block start
                  @0x55767c5c in TMeleeRound.CalculateStrikes the same way (combat objects ESI/EDI,
                  EBX=strike record), then jmp 0x55767c89.
  cave_guard   @0x55849000        -- SHARED with build_magebane.py; see combatunitguard.py.

⭐ THE FOUR ADDRESSES AND THE TWO CAVE LENGTHS ARE PINNED, and the bodies are nop-padded to fit.
The 2026-09-11 fix made both bodies SHORTER (the THero classref load moved into the shared guard).
Letting them shrink would have slid cave_asnreg, the name literal and cave_melee3 down by 16 bytes,
which `build_trueseeing.py` / `build_invis_penalty.py` document by address and which would have left
stale bytes behind. Padding is cheaper than re-verifying four scripts.

⚠ CHAIN: both caves' exit jumps are CHAIN LINKS that downstream features repoint --
    cave_melee  -> cave_ts_melee  (0x5580E370, build_invis_penalty) -> magebane melee1 (0x558129E0)
    cave_melee3 -> cave_ts_melee3 (0x5580E3B0, build_invis_penalty) -> magebane melee3 (0x55812A10)
`preserve_terminator()` keeps whatever exit is installed, so re-running this script never unlinks them.

ASSASSIN id = 0x38 (a free slot < 0xAA; the set auto-grows anyway -- see aow1-path-of-sand memory). Icon =
*(0x557675f0), the strike-ability category (shared by Life Stealing / Dragon Slaying), so it lists with them.

USAGE
-----
    build_assassin.py                     dry run: verify current state + print the caves
    build_assassin.py --dis               disassemble the caves this build would write
    build_assassin.py --apply             write (snapshot to <game dir>\backups\ ONLY on a
                                          proven-unpatched file -- see the gate in process())
    build_assassin.py --undo-wallguard    SURGICAL: put the two caves back to their pre-2026-09-11
                                          (raw +0x4C read) bodies and drop the shared guard if no
                                          other feature still calls it. Exits, hooks, bonuses and
                                          the chain are untouched. This is the fix's revert path.
    build_assassin.py --undo              SURGICAL, WHOLE FEATURE: restore the three hook byte-runs
                                          and zero all four caves + the name literal. REFUSES while
                                          a downstream cave is spliced into either exit jump (it
                                          names the address); undo those features first.

A `.pre-*` restore is NOT a revert path: it is a whole-file copy that would drop every feature
applied since, and there is no snapshot layer left in any case (both stacks purged, 2026-08-08 /
2026-09-09).
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import combatunitguard as cug

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never the game root (rule 2026-09-03)
ks=Ks(KS_ARCH_X86,KS_MODE_32); cs=Cs(CS_ARCH_X86,CS_MODE_32)

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
def patch(code, va, pop_op, disps):     # anchor = E8 <rel0> <pop_op>; call->next + placeholder disps->(tgt-anchor)
    code=bytearray(code)
    i=next(k for k in range(len(code)-5) if code[k]==0xE8 and code[k+5]==pop_op)
    anchor=va+i+5; code[i+1:i+5]=struct.pack("<i",0)
    for ph,tgt in disps:
        hits=[k for k in range(len(code)-3) if code[k:k+4]==struct.pack("<I",ph)]
        assert len(hits)==1, f"placeholder {ph:#x} found {len(hits)}x"
        code[hits[0]:hits[0]+4]=struct.pack("<i",tgt-anchor)
    return bytes(code)

DLL_BASE=0x55700000
ENH_FACTORY=0x5576601C; REGISTER_ABIL=0x55750238; ISCLASS=0x557010C0   # CreateEnhancementAbility (Path-of-Sand's
                       # factory -> TEnhancementAbility). The strike factory 0x5576727c (TStrikeEnhancementAbility)
                       # registered + listed + assigned fine, and showed on the unit, but combat GetAbilityEnabled
                       # returned FALSE for it (proven by --diag), so the melee bonus never fired. TEnhancementAbility
                       # passes GetAbilityEnabled on the raw bit (Path of Sand works), so use it. Id/category unchanged.
THERO_CLASSREF=0x55711FAC          # CELL holding the THero class ref. Used only by the LEGACY bodies now --
                                   # the live bodies reach it through combatunitguard.guard_hero.
ICON_VA=0x557675F0                 # strike-ability category word (Life Stealing / Dragon Slaying share it)
ASSASSIN_ID=0x38                   # free ability id
# 5% CONVERSION (2026-08-18): the ATTACK bonus doubles, the DAMAGE bonus does NOT.
# One constant used to feed both, which is only safe while they are equal.
#   add bl, N                    -> BL      = ATTACK        (doubles)
#   add byte ptr [esp+3], N      -> [ESP+3] = DAMAGE        (unchanged)
#   add dword ptr [ebx], N       -> [EBX]   = ATTACK slot   (doubles)   (cave_melee3, strike record)
#   add dword ptr [ebx+4], N     -> [EBX+4] = DAMAGE slot   (unchanged)
# Register conventions are the ones this file's own header documents.
MELEE_ATK_BONUS=5   # 2026-08-24 buff re-grade: 6 -> 5 (odd grade the 5% slope unlocked)
MELEE_DAM_BONUS=5   # was 3 (vanilla), 6 (DAM/HP doubling), now 5 (re-grade)

# --- hooks ---
REG_INJ=0x557675C4; REG_ORIG=b"\xE8"+rel32(0x557675C4,REGISTER_ABIL)   # last strike RegisterAbility call
MELEE_INJ=0x557666A1; MELEE_ORIG=bytes.fromhex("ba 70 00 00 00")       # MOV EDX,0x70 (Monster-Slaying block start)
MELEE_CONT=0x557666CF                                                  # -> XOR ECX,ECX (build the CA)

# --- PINNED LAYOUT (see the header). Changing any of these moves bytes other scripts document. ---
CAVE=0x5580E070
CAVE_MELEE  = CAVE
MELEE_LEN   = 106                  # cave_melee footprint; keeps CAVE_REG at 0x5580E0E0
CAVE_REG    = 0x5580E0E0
NAME_BLOB_VA= 0x5580E10C
NAME_VA     = NAME_BLOB_VA + 8     # 0x5580E114
CAVE_MELEE3 = 0x5580E120
MELEE3_LEN  = 104                  # cave_melee3 footprint; ends at 0x5580E188, below
                                   # build_ranged_slayers.py's CAVE_RNG = 0x5580E190
MELEE3_INJ=0x55767C5C; MELEE3_ORIG=bytes.fromhex("ba 70 00 00 00"); MELEE3_CONT=0x55767C89

PH_THERO=0x71111117; PH_NAME=0x72222227; PH_THERO3=0x73333337

DIAG="--diag" in sys.argv          # drop the hero check so Assassin fires vs ANY target
                                   # (isolates attacker-check vs hero-check). Diagnostic only.

# ════════════════════════════════════════════════════════════════════════════════════════
# CAVE SOURCES
#   *_src        -- what we install today: the wall-safe form.
#   *_src_legacy -- what was installed before 2026-09-11: the raw `[reg+0x4C]` read guarded
#                   only by a nil test.  KEPT so verify-before-write accepts a pre-fix DLL
#                   (CLAUDE.md: "verify against EITHER the installed bytes OR the new ones")
#                   and so --undo-wallguard has something exact to write back.
#                   ⚠ Do not "clean up" the legacy text -- it IS the acceptance predicate.
# ════════════════════════════════════════════════════════════════════════════════════════
def _pad_to(src_text, va, target_len, tail_label):
    """Assemble, then re-assemble with N nops inserted at `tail_label` so the body is exactly
    `target_len` bytes. The nops go BEFORE the terminating jmp, never after: preserve_terminator()
    and the chain logic both expect `body[-5] == 0xE9`."""
    b = bytes(ks.asm(src_text, va)[0])
    pad = target_len - len(b)
    if pad < 0:
        raise SystemExit("ERROR: body at %08X is %d B, over its pinned %d B by %d"
                         % (va, len(b), target_len, -pad))
    if pad:
        src_text = src_text.replace(tail_label + ":", tail_label + ":\n" + "    nop\n" * pad, 1)
        b = bytes(ks.asm(src_text, va)[0])
    assert len(b) == target_len, (len(b), target_len)
    assert b[-5] == 0xE9, "padded body does not end in a jmp"
    return b

def melee_text(atk, dam, legacy):
    """cave_melee. EBP=attacker ESI=target BL=attack [ESP+3]=damage."""
    if legacy:
        # 2026-09-11: THE DEFECT. `mov eax,[esi+0x4c]` on a TCombatWall yields packed bytes.
        hero = "" if DIAG else f"""
    mov eax, [esi+0x4c]
    test eax, eax
    jz _asn
    mov edx, [edi + 0x{PH_THERO:X}]
    call 0x{ISCLASS:X}
    test al, al
    jz _asn"""
        head = f"""
    call 0x{CAVE_MELEE:X}
    pop edi"""
    else:
        hero = "" if DIAG else f"""
    mov eax, esi
    call 0x{cug.GUARD_HERO:X}
    test al, al
    jz _asn"""
        head = ""      # the PIC anchor died with the THero load; EDI is no longer clobbered
    return f"""{head}
    mov edx, 0x70
    mov eax, ebp
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jz _mons
    mov edx, 0x3f
    mov eax, esi
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jz _mons
    add bl, {atk}
    add byte ptr [esp+3], {dam}
_mons:
    mov edx, 0x{ASSASSIN_ID:X}
    mov eax, ebp
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jz _asn{hero}
    add bl, {atk}
    add byte ptr [esp+3], {dam}
_asn:
    jmp 0x{MELEE_CONT:X}
"""

def melee3_text(atk, dam, legacy):
    """cave_melee3. ESI=attacker EDI=target EBX=strike record ([EBX]=attack, [EBX+4]=damage)."""
    if legacy:
        hero = f"""
    mov eax, [edi+0x4c]
    test eax, eax
    jz _m3asn
    call 0x{CAVE_MELEE3:X}
    pop ecx
    mov edx, [ecx + 0x{PH_THERO3:X}]
    call 0x{ISCLASS:X}
    test al, al
    jz _m3asn"""
    else:
        hero = f"""
    mov eax, edi
    call 0x{cug.GUARD_HERO:X}
    test al, al
    jz _m3asn"""
    return f"""
    mov edx, 0x70
    mov eax, esi
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jz _m3mons
    mov edx, 0x3f
    mov eax, edi
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jz _m3mons
    add dword ptr [ebx], {atk}
    add dword ptr [ebx+4], {dam}
_m3mons:
    mov edx, 0x{ASSASSIN_ID:X}
    mov eax, esi
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jz _m3asn{hero}
    add dword ptr [ebx], {atk}
    add dword ptr [ebx+4], {dam}
_m3asn:
    jmp 0x{MELEE3_CONT:X}
"""

def build_melee(atk, dam, legacy):
    txt = melee_text(atk, dam, legacy)
    if legacy:
        # the legacy body carries its own call/pop-EDI PIC anchor and a THero placeholder
        b = bytes(ks.asm(txt, CAVE_MELEE)[0])
        b = patch(b, CAVE_MELEE, 0x5F, ([] if DIAG else [(PH_THERO, THERO_CLASSREF)]))
        assert len(b) == MELEE_LEN, "legacy cave_melee is %d B, expected %d" % (len(b), MELEE_LEN)
        return b
    return _pad_to(txt, CAVE_MELEE, MELEE_LEN, "_asn")

def build_melee3(atk, dam, legacy):
    txt = melee3_text(atk, dam, legacy)
    if legacy:
        b = bytes(ks.asm(txt, CAVE_MELEE3)[0])
        b = patch(b, CAVE_MELEE3, 0x59, [(PH_THERO3, THERO_CLASSREF)])
        assert len(b) == MELEE3_LEN, "legacy cave_melee3 is %d B, expected %d" % (len(b), MELEE3_LEN)
        return b
    return _pad_to(txt, CAVE_MELEE3, MELEE3_LEN, "_m3asn")

cave_melee  = build_melee (MELEE_ATK_BONUS, MELEE_DAM_BONUS, legacy=False)
cave_melee3 = build_melee3(MELEE_ATK_BONUS, MELEE_DAM_BONUS, legacy=False)

def build_reg(icon):
    src=f"""
        call 0x{REGISTER_ABIL:X}
        call 0x{CAVE_REG:X}
        pop eax
        lea edx, [eax + 0x{PH_NAME:X}]
        mov cx, 0x{icon:X}
        mov eax, 0x{ASSASSIN_ID:X}
        call 0x{ENH_FACTORY:X}
        mov edx, eax
        mov eax, ebx
        call 0x{REGISTER_ABIL:X}
        ret
    """
    return patch(bytes(ks.asm(src,CAVE_REG)[0]),CAVE_REG,0x58,[(PH_NAME,NAME_VA)])
_probe=bytes(ks.asm(f"call 0x{REGISTER_ABIL:X}\ncall 0x{CAVE_REG:X}\npop eax\nlea edx,[eax+0x{PH_NAME:X}]\nmov cx,0x1234\nmov eax,0x{ASSASSIN_ID:X}\ncall 0x{ENH_FACTORY:X}\nmov edx,eax\nmov eax,ebx\ncall 0x{REGISTER_ABIL:X}\nret",CAVE_REG)[0])
assert NAME_BLOB_VA == (CAVE_REG+len(_probe)+0x3)&~0x3, "cave_asnreg changed size -- the name literal moved"
_name=b"Assassin"
name_blob=struct.pack("<iI",-1,len(_name))+_name+b"\x00"
assert CAVE_MELEE3 == (NAME_BLOB_VA+len(name_blob)+0xF)&~0xF, "the name literal changed size -- cave_melee3 moved"
assert CAVE_MELEE + MELEE_LEN <= CAVE_REG,        "cave_melee overruns cave_asnreg"
assert CAVE_MELEE3 + MELEE3_LEN <= 0x5580E190,    "cave_melee3 overruns build_ranged_slayers.py's CAVE_RNG"

APPLY="--apply" in sys.argv
UNDO_WG="--undo-wallguard" in sys.argv
UNDO_ALL="--undo" in sys.argv and not UNDO_WG
DIS="--dis" in sys.argv or "--show" in sys.argv
WRITES = APPLY or UNDO_WG or UNDO_ALL

# --- in-place cave revision: accept our OWN previously-installed body -------------------------
# This script originally expected each cave site to be ZERO (first install) or byte-identical to the
# body it is about to write.  Re-tuning a constant produces a THIRD state -- our body with the OLD
# value -- which matched neither, so the script refused to write and could not re-tune itself.
# CLAUDE.md's rule is "verify-before-write against EITHER the currently-installed bytes OR the new
# ones".  Regenerate our bodies across the plausible bonus range and accept any of them.
# (The 5% conversion hit this going +3 -> +6 on the ATTACK half.)
# 2026-09-11: the same list now also carries every LEGACY (pre-wall-guard) body, which is what lets
# --apply upgrade a crashing install in place instead of demanding a revert-and-reapply.
def _variants(builder):
    out=[]
    for a in range(1,13):
        for dmg in range(1,13):
            for legacy in (False, True):
                try: out.append(builder(a,dmg,legacy))
                except Exception: pass
    return out
CAVE_VARIANTS = {
    CAVE_MELEE:  _variants(build_melee),
    CAVE_MELEE3: _variants(build_melee3),
}
LEGACY = {                       # exactly what --undo-wallguard writes back
    CAVE_MELEE:  build_melee (MELEE_ATK_BONUS, MELEE_DAM_BONUS, legacy=True),
    CAVE_MELEE3: build_melee3(MELEE_ATK_BONUS, MELEE_DAM_BONUS, legacy=True),
}

# --- CHAIN PRESERVATION -----------------------------------------------------------------------
# This cave's exit `jmp` is a CHAIN LINK, not a private detail.  Downstream features splice
# themselves in by repointing it at their own cave:
#     assassin cave_melee3 --exit--> cave_ts_melee3 (build_invis_penalty) --exit--> magebane
# Regenerating the body with our STOCK destination would silently delete every feature downstream
# of us, and build_invis_penalty.py only VERIFIES that chain (it never rewrites it), so it would
# then refuse to run at all.  So: keep whatever exit target is currently installed.
def preserve_terminator(gen, cave_va, live, stock_dest, quiet=False):
    """Return `gen` with its trailing jmp retargeted to whatever the installed body jumps to."""
    if len(live) < len(gen):
        return gen
    off = len(gen) - 5
    if off < 0 or gen[off] != 0xE9 or live[off] != 0xE9:
        return gen                                  # not the shape we expect -- leave it alone
    live_t = cave_va + off + 5 + struct.unpack_from("<i", live, off + 1)[0]
    if live_t == stock_dest:
        return gen                                  # still stock: nothing chained onto us
    if not quiet:
        print("[chain] %08X exit kept at %08X (stock is %08X) -- a downstream cave is spliced in"
              % (cave_va, live_t, stock_dest))
    return gen[:off + 1] + struct.pack("<i", live_t - (cave_va + off + 5)) + gen[off + 5:]

def exit_target(live, cave_va):
    off = len(live) - 5
    if live[off] != 0xE9: return None
    return cave_va + off + 5 + struct.unpack_from("<i", live, off + 1)[0]

def process(path,base,suffix=".pre-assassin"):
    global cave_melee, cave_melee3, CAVE_VARIANTS, LEGACY
    data=bytearray(open(path,"rb").read()); secs=load_sections(data); va2off=mkva2off(base)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
    def wr(va,b): o=va2off(secs,va); data[o:o+len(b)]=b
    def flush():
        try: open(path,"wb").write(data)
        except PermissionError: print("[x] LOCKED -- close AoW binaries"); return False
        return True

    # Keep whatever exit target is installed (see preserve_terminator).  Applied to the body we are
    # about to write AND to every accept-variant, or a chained cave would never match.
    _lm  = rd(CAVE_MELEE,  MELEE_LEN)
    _lm3 = rd(CAVE_MELEE3, MELEE3_LEN)
    cave_melee  = preserve_terminator(cave_melee,  CAVE_MELEE,  _lm,  MELEE_CONT)
    cave_melee3 = preserve_terminator(cave_melee3, CAVE_MELEE3, _lm3, MELEE3_CONT)
    CAVE_VARIANTS = {
        CAVE_MELEE:  [preserve_terminator(v, CAVE_MELEE,  _lm,  MELEE_CONT,  True) for v in CAVE_VARIANTS[CAVE_MELEE]],
        CAVE_MELEE3: [preserve_terminator(v, CAVE_MELEE3, _lm3, MELEE3_CONT, True) for v in CAVE_VARIANTS[CAVE_MELEE3]],
    }
    LEGACY = {
        CAVE_MELEE:  preserve_terminator(LEGACY[CAVE_MELEE],  CAVE_MELEE,  _lm,  MELEE_CONT,  True),
        CAVE_MELEE3: preserve_terminator(LEGACY[CAVE_MELEE3], CAVE_MELEE3, _lm3, MELEE3_CONT, True),
    }
    OURS = ((CAVE_MELEE, CAVE_MELEE+MELEE_LEN), (CAVE_MELEE3, CAVE_MELEE3+MELEE3_LEN))

    icon=struct.unpack("<H",rd(ICON_VA,2))[0]
    cave_reg=build_reg(icon)
    print(f"[i] icon *({ICON_VA:08X})=0x{icon:04X}  ASSASSIN=0x{ASSASSIN_ID:02X}  name @ {NAME_VA:08X}")

    # ── --undo-wallguard : surgical revert of the 2026-09-11 fix only ─────────────────────
    if UNDO_WG:
        wrote=0
        for va, body, ln in ((CAVE_MELEE, LEGACY[CAVE_MELEE], MELEE_LEN),
                             (CAVE_MELEE3, LEGACY[CAVE_MELEE3], MELEE3_LEN)):
            cur=rd(va,ln)
            if cur==body: print(f"[= ] {va:08X} already legacy"); continue
            if cur not in CAVE_VARIANTS[va]:
                print(f"[x] {va:08X} is neither ours nor a known variant -- refusing\n     got {cur.hex(' ')}")
                return False
            wr(va, body); wrote+=1; print(f"[w ] {va:08X} legacy (raw +0x4C) body restored")
        cug.undo_if_unused(rd, wr, exclude=OURS)
        print("[!] the caves are back to the form that AVs on a walled target -- this is the")
        print("    fix's revert path, not a state to leave the game in.")
        return flush()      # always: undo_if_unused() may have written even when `wrote` is 0

    # ── --undo : whole feature, chain-guarded ────────────────────────────────────────────
    if UNDO_ALL:
        bad=[]
        for va, live, stock in ((CAVE_MELEE,_lm,MELEE_CONT),(CAVE_MELEE3,_lm3,MELEE3_CONT)):
            t=exit_target(live,va)
            if t is not None and t!=stock: bad.append((va,t))
        if bad:
            print("[x] REFUSING: a downstream cave is spliced into our exit jump(s):")
            for va,t in bad: print(f"      {va:08X} exits to {t:08X} (stock {MELEE_CONT if va==CAVE_MELEE else MELEE3_CONT:08X})")
            print("    Removing Assassin now would orphan that feature. Undo it first")
            print("    (build_invis_penalty.py / build_trueseeing.py / build_magebane.py).")
            return False
        for va,orig,desc in ((MELEE_INJ,MELEE_ORIG,"CreateStrikeCA"),
                             (MELEE3_INJ,MELEE3_ORIG,"CalculateStrikes"),
                             (REG_INJ,REG_ORIG,"RegisterAbility")):
            wr(va,orig); print(f"[w ] {va:08X} {desc} hook restored")
        for va,ln,desc in ((CAVE_MELEE,MELEE_LEN,"cave_melee"),(CAVE_REG,len(cave_reg),"cave_asnreg"),
                           (NAME_BLOB_VA,len(name_blob),"name literal"),(CAVE_MELEE3,MELEE3_LEN,"cave_melee3")):
            wr(va,bytes(ln)); print(f"[w ] {va:08X} {desc} zeroed ({ln} B)")
        cug.undo_if_unused(rd, wr, exclude=OURS)
        print("[done] Assassin removed surgically. No backup touched.")
        return flush()

    # ── normal path ─────────────────────────────────────────────────────────────────────
    patches=[
        cug.patch_entry(rd),
        (CAVE_MELEE, bytes(MELEE_LEN), cave_melee, "cave_melee (Monster Slaying replay + Assassin block)"),
        (CAVE_REG,   bytes(len(cave_reg)),   cave_reg,   "cave_asnreg (MagicStrike re-register + register Assassin)"),
        (NAME_BLOB_VA, bytes(len(name_blob)), name_blob, 'name literal "Assassin"'),
        (CAVE_MELEE3, bytes(MELEE3_LEN), cave_melee3, "cave_melee3 (deliberate-melee Assassin via CalculateStrikes)"),
        (MELEE_INJ, MELEE_ORIG, b"\xE9"+rel32(MELEE_INJ,CAVE_MELEE), "CreateStrikeCA 0x557666a1 -> cave_melee (round/opportunity)"),
        (MELEE3_INJ,MELEE3_ORIG,b"\xE9"+rel32(MELEE3_INJ,CAVE_MELEE3),"CalculateStrikes 0x55767c5c -> cave_melee3 (deliberate melee)"),
        (REG_INJ,   REG_ORIG,   b"\xE8"+rel32(REG_INJ,CAVE_REG),     "last strike RegisterAbility -> cave_asnreg"),
    ]
    if DIS:
        cug.show()
        for nm,va,cave in [("cave_melee",CAVE_MELEE,cave_melee),("cave_melee3",CAVE_MELEE3,cave_melee3),
                           ("cave_asnreg",CAVE_REG,cave_reg)]:
            print(f"{nm} @ {va:08X} ({len(cave)} B)")
            for ins in cs.disasm(cave,va): print(f"  {ins.address:08X} {ins.bytes.hex(' '):<24}{ins.mnemonic} {ins.op_str}")
    gstate = cug.state(rd)
    print(f"[i] cave_guard {cug.GUARD_VA:08X}: {gstate}")
    if gstate=="foreign":
        print("[x] the shared guard's zone is occupied by something that is not ours -- aborting")
        return False

    if all(rd(va,len(new))==new for va,_o,new,_d in patches):
        print(f"[= ] already applied (wall-safe form)"); return True
    ok=True; fresh=True
    for va,orig,new,desc in patches:
        cur=rd(va,len(new))
        if cur!=orig: fresh=False
        accept = (cur==orig or cur==new or any(cur==v for v in CAVE_VARIANTS.get(va, [])))
        if not accept:
            ok=False
            print("[!] %08X (%s)" % (va, desc))
            print("     exp " + orig.hex(" "))
            print("     got " + cur.hex(" "))
    if not ok: print("[x] mismatch -- not written"); return False
    if not APPLY: print("[dry] originals verified"); return True

    # ⚠ SNAPSHOT GATE. A `.pre-assassin` is only honest if this file has never had Assassin
    # applied. `not os.path.exists(bp)` is NOT that test -- on a re-tune, an upgrade from the
    # legacy bodies, or after the directory was pruned, it would mint a snapshot OF OUR OWN
    # OUTPUT under a name that reads as pre-patch. Gate on the three hook sites still holding
    # their vanilla byte-runs instead.
    hooks_virgin = all(rd(va,len(o))==o for va,o in
                       ((MELEE_INJ,MELEE_ORIG),(MELEE3_INJ,MELEE3_ORIG),(REG_INJ,REG_ORIG)))
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bp=os.path.join(BACKUP_DIR, os.path.basename(path)+suffix)
    if hooks_virgin and fresh and not os.path.exists(bp):
        shutil.copy2(path,bp); print(f"[bak] {bp}")
    elif not hooks_virgin:
        print("[i] no snapshot: the hook sites are already patched, so this file is NOT pre-Assassin")
    for va,orig,new,desc in patches:
        wr(va,new); print(f"[w ] {va:08X} {desc}")
    return flush()

print()
ok=process(os.path.join(GAME,"AoWEPACK.dpl"),DLL_BASE)
if not WRITES:
    print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first.")
elif ok:
    print("\n[done] Revert: --undo-wallguard (the 2026-09-11 wall fix only) or --undo (whole"
          "\n       feature, refuses while a downstream cave is chained in). Both surgical;"
          "\n       a .pre-* restore is NOT a revert path.")
else:
    print("\n[!] not applied")
