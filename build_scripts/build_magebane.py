#!/usr/bin/env python3
r"""
AoW1 mod -- "Magebane": a NEW ability granting +1 ATK / +1 DMG per ENCHANTMENT active on the target.

    A unit with Magebane hits harder the more magic is sustained on its victim.
    Stacking, uncapped by default. Melee (deliberate + retaliation + opportunity/round/ability
    strikes) and ranged/breath are all covered.

================================================================================
WHAT COUNTS AS AN ENCHANTMENT
================================================================================
The engine's own notion: a unit's enchantments are exactly the abilities it has whose class is
`TUnitEnchantmentAbility`. That class creates a real `TEnchantment` object, which carries an
OWNING PLAYER, an UPKEEP, and a DISPEL path -- i.e. "a sustained magical effect a caster is paying
for and Dispel Magic can strip". Contrast `TDurationAbility` (Burning 0x7F, Panicked 0x6C, Poisoned,
Cursed, Vertigo, Crusader) which is just a timer with no owner -- those do NOT count.

The counting loop below mirrors `TAbstractUnit.RegisterEnchantments @0x5577F29C` exactly:

    list = [[HSSet+0x80] + 0x1C]                      ; TAbilityTypeList
    for i = [list+8]-1 downto 0:
        ab = TAbilityTypeList.GetAbility(list, i)     ; 0x557500AC
        if IsClass(ab, TUnitEnchantmentAbility)       ; 0x557010C0, class ptr var @0x55722324
           and target.vmt[0x148](ab[0xC]):            ; GetAbilityEnabled(abilityId)
               count++

The 21 enchantment classes are: Haste 0x98, Stone Skin, Fire Protection 0xA7, Enchanted Weapon,
Fury 0x9C, Free Movement 0x9D, Holy Champion, Unholy Champion, Blessed, Dark Gift 0xA9,
Concealment 0xA2, Fire Aura, Water Walking 0xA4, Wind Walking 0xA5, Liquid Form 0xA6,
Summoned 0x9B, Cosmetic Surgery, and the four hostile ones below.

**EXCLUDED by request** (they are enchantments, but your own crowd control should not feed your
damage): Slow 0x84, Entangled 0x5E, Frozen 0x5F, Turned Undead 0x22.
Summoned 0x9B is INCLUDED -- it is permanent on every summoned creature, so Magebane gets a flat
+1/+1 against summons. Set INCLUDE_SUMMONED = False to drop it.

================================================================================
INJECTION -- chained onto the existing slayer/invis caves
================================================================================
The three strike sites already carry our Assassin / slayer / true-seeing caves. Rather than rewrite
those cave bodies, this script REPOINTS EACH CAVE'S FINAL EXIT JUMP into a Magebane block that does
its work and then jumps to the original return address. Minimal (4 bytes of rel32 each) and
reversible.

  site                              exit jmp        was ->            Magebane block returns to
  CreateStrikeCA        (melee 1)   0x5580E399  ->  0x557666CF        same
  TMeleeRound.CalculateStrikes (m3) 0x5580E3D9  ->  0x55767C89        same
  CreateRangedAttackCA  (ranged)    0x5580E298  ->  0x5576EB39        same

Register / slot state at each exit (read from the live binary, not the design docs):
  melee1 : attacker=EBP, target=ESI(combat), ATK=BL, DMG=byte[esp+3]; EAX/ECX/EDX are DEAD
           (0x557666CF immediately does xor ecx,ecx / mov dl,1 / mov eax,[abs]).
  melee3 : attacker=ESI, target=EDI(combat), ATK=dword[EBX], DMG=dword[EBX+4]; EAX/EDX dead.
  ranged : attacker=ESI, target=[EBP-4](combat), stack is [esp]=damage, [esp+4]=attack.
           ⚠ EAX and EDX are LIVE here (0x5576EB39 is `call [edx+0xb8]`), so the block saves and
           restores them; after its 3 pushes the slots sit at [esp+12] / [esp+16].

Target enchantments live on the STRATEGIC unit, reached from the combat object via `[combat+0x4C]`
(the same bridge the Assassin block already uses).

╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║ ⚠⚠ `[combat+0x4C]` MUST BE TYPE-GATED -- fixed 2026-09-11                                    ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
All three blocks used to read `[target+0x4C]` raw and pass it to `cave_count`, guarded only by
`test eax,eax`.  `+0x4C` exists only on `TCombatUnit`; `TCombatWall` is a SIBLING class (both
descend from `TCombatObject`, instsize 0x4C) and reuses those bytes as wall type / wall HP, so a
Ziggurat stone wall reads back as `0x00002802` -- non-zero, so the nil test passes, and
`cave_count`'s `mov ebp,eax / mov ecx,[eax] / call [ecx+0x148]` then dereferences it.  A wall is a
legal melee AND ranged target, so any Magebane carrier attacking a walled city would have crashed.

Found by sweeping mod cave space after the byte-identical defect crashed the game live in
`build_assassin.py` (see that file's header for the captured exception).  Never observed in-game
here only because no Magebane unit had yet swung at a wall.

FIX: `cave_count` now takes the **combat object**, not the strategic unit, and its first
instruction is `call guard_unit` in the shared cave `combatunitguard.py` installs at 0x55849000.
`guard_unit` does `IsClass(obj, TCombatUnit)` BEFORE reading `+0x4C` and returns 0 for a wall, a
nil or any other TCombatObject descendant; `cave_count` then returns AL=0 and the existing
`test al,al / jz mb_out` at each site takes the no-bonus path.  TFastCombatUnit descends from
TCombatUnit, so auto-resolve keeps the bonus.

⭐ The guard lives in cave_count, not at the three sites, on purpose: a `call` at each site costs
4 bytes more than the `mov eax,[reg+0x4C]` it replaces, which pushed the ranged block past
`build_shield.py`'s tail pin (`RNG_TAIL_PIN`).  Doing it inside cave_count makes every site
SHORTER instead, and cave_count's own 14 bytes of alignment slack absorb the 10 bytes it adds --
so not one address in this cave moved.  ⚠ If you ever grow cave_count, re-check that slack: at
188/192 bytes there are 4 left before `melee1` slides 16 bytes down and the pin assert fires.

⚠ CROSS-SCRIPT COUPLING: those three exit jumps live inside caves owned by `build_assassin.py`,
`build_ranged_slayers.py` and `build_invis_penalty.py`. **Re-running any of those will rewrite its
cave and silently drop the Magebane chain** -- re-run this script afterwards. `--verify` reports it.

================================================================================
REGISTRATION
================================================================================
Hooks `0x557BCF6E` -- the LAST VANILLA `call RegisterAbility` in `RegisterPassiveAbilities`
(145 of the 149 call sites are still vanilla; the 4 patched ones are our Assassin/slayer regs).
`EBX` holds the ability control there, and every vanilla ability is already registered by that
point. The cave re-issues the displaced call, then creates + registers Magebane and jumps to
0x557BCF73.

Category word is taken from `[0x557BCFC0]` = 0x37 -- the same one Path of Sand uses, which is
confirmed to make the ability appear in the editor's assignable list. (The neighbours at this site
use `[0x557BCFC8]` = 0x237; not used here.)

⚠ ABILITY ID = 0xAA. Our `Ability_ID_Budget.md` recommends 0xAA-0xCD (36 ids above vanilla's max --
Dark Gift 0xA9, independently confirmed here). Inioch reports a Localize.dpl crash above 0xA9 on his
AoW+ build, which is UNRESOLVED. Both failure modes are LOUD and immediate at startup
("Ability already registered" assert, or a Localize crash), so this doubles as the decisive test.
If it crashes, set MAGEBANE_ID to a verified sub-0xA9 gap and re-run.

The icon will be BLANK -- expected for a brand-new id (no ILB entry), same as Path of Sand.

Backup: backups\AoWEPACK.dpl.pre-magebane -- minted by --apply as a diagnostic artefact.
⚠ NOT a revert path: restoring it puts back the WHOLE file and silently wipes every
feature applied after it was taken. Revert with --undo.
Dry-run by default; --apply to commit; --undo to remove surgically; --verify to check the chain.
"""

import os
import sys
import shutil
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import combatunitguard as cug
import argparse

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-magebane")

VA_BASE = 0x55700C00
CAVE_VA = 0x55812900          # free CODE. Taken: 0x55812400-47F sitedefender, 0x55812500-7FF
                              # crusade, 0x55812800-83F stormeffectroll, 0x55812880-8DF masterycost
CAVE_LIMIT = 0x200
CODE_ZERO_END = 0x558E7918

# ---- tuning ----------------------------------------------------------------
MAGEBANE_ID = 0xAA
BONUS_PER   = 2               # +N ATK and +N DMG per enchantment -- 2026-08-24: was 1.
# One knob covers BOTH sides of the DAM/HP doubling AND the 5% conversion's missed ATK half:
# the bonus is a COUNT (enchantments), not an immediate, so the conversion could not see it.
CAP         = 0               # 0 = uncapped
INCLUDE_SUMMONED = True       # Summoned 0x9B is permanent on every summon
SUMMONED_ID    = 0x9B
SUMMONED_BONUS = 5            # 2026-08-29 (user ruling): a unit carrying Summoned is worth
                              # +5/+5 on its own, not the flat BONUS_PER the other enchantments
                              # give. Implemented as a TOP-UP of (SUMMONED_BONUS - BONUS_PER)
                              # applied after the multiply, because Summoned is also counted by
                              # the ordinary loop -- so a bare summon reads exactly +5/+5, and a
                              # hasted summon reads +7/+7 (5 + one ordinary enchantment).
                              # Set == BONUS_PER to disable the special case.
EXCLUDED = [0x84, 0x5E, 0x5F, 0x22]        # Slow, Entangled, Frozen, Turned Undead
if not INCLUDE_SUMMONED:
    EXCLUDED = EXCLUDED + [0x9B]
NAME = b"Magebane"
# ----------------------------------------------------------------------------

# engine entry points
GETABILITY   = 0x557500AC     # TAbilityTypeList.GetAbility(EAX=list, EDX=idx) -> EAX
ISCLASS      = 0x557010C0     # System.IsClass(EAX=obj, EDX=classref) -> AL
CREATE_ENH   = 0x5576601C     # CreateEnhancementAbility(EAX=id, EDX=name, CX=cat) -> EAX
REGISTER_AB  = 0x55750238     # RegisterAbility(EAX=control, EDX=obj)
PTR_HSSET    = 0x558E92E8     # -> ptr -> HSSet ; ability control at [HSSet+0x80]
PTR_ENCHCLS  = 0x55722324     # variable holding the TUnitEnchantmentAbility class ref
CATWORD      = 0x557BCFC0     # category word 0x37

# chain repoints: (exit-jmp VA, original target)
CHAINS = [
    ("melee1", 0x5580E399, 0x557666CF),
    ("melee3", 0x5580E3D9, 0x55767C89),
    ("ranged", 0x5580E298, 0x5576EB39),
]
REG_HOOK = 0x557BCF6E
REG_ORIG = b"\xE8" + struct.pack("<i", REGISTER_AB - (REG_HOOK + 5))
REG_CONT = 0x557BCF73


def off(va):
    return va - VA_BASE


def jmp_to(src, dst):
    return b"\xE9" + struct.pack("<i", dst - (src + 5))


def excl_asm(reg):
    return "\n".join("cmp %s, 0x%X\nje ab_next" % (reg, i) for i in EXCLUDED)


def cap_asm():
    if CAP <= 0:
        return ""
    return "cmp eax, %d\njbe no_cap\nmov eax, %d\nno_cap:" % (CAP, CAP)


# ⚠ THE RANGED TAIL IS A CHAIN LINK, NOT A RETURN ADDRESS -- and getting this wrong is what made
# this script un-runnable between 2026-08-26 and 2026-08-29.
#
# build_shield.py hooks the END of our ranged cave: it replaced our `jmp 0x5576EB39` with
# `jmp 0x558230D0` (its own ranged cave), which then resumes at 0x5576EB39 itself. The chain is
#     0x5576EB34 -> ranged slayers -> invisibility -> OUR ranged cave -> Shield -> 0x5576EB39
# so emitting the stock tail would have silently unlinked Shield's ranged penalty -- a
# confirmed-working feature -- with no error anywhere. `caves match: False` on an otherwise-healthy
# feature means LOOK AT THE TAIL JUMP, not the body.
#
# Rather than hard-code either answer, detect it: if Shield's cave is present, chain into it;
# if it has been `--undo`ne (its cave zeroed), go straight back to the engine. Re-applying this
# script is therefore safe in both states, and no revert ordering is required any more.
SHIELD_RANGED_CAVE = 0x558230D0
RANGED_RESUME      = 0x5576EB39
RNG_TAIL_PIN       = 0x55812A7B   # build_shield.py's `RNG_TAIL` -- our ranged tail must stay here
# ⚠ build_shield.py ALSO pins our melee1 tail (`M1_TAIL = 0x55812A09`) as a RETIRED-site assert and
# ABORTS ENTIRELY when the byte-run there is not our `jmp 0x557666CF`. So the melee block LENGTHS
# are pinned too: the 2026-09-11 wall guard shortened both by one byte and bricked build_shield
# until they were nop-padded back. Keep these two numbers and the whole cave stays byte-addressed
# exactly as three other scripts document it.
M1_LEN_PIN         = 46
M3_LEN_PIN         = 48
M1_TAIL_PIN        = 0x55812A09   # == build_shield.py's M1_TAIL


def summoned_asm():
    """Top up the (already multiplied) bonus for a target carrying Summoned.

    Runs inside cave_count, where EBP still holds the strategic target and EAX holds the finished
    bonus. Summoned is also counted by the ordinary loop, so the top-up is the DIFFERENCE."""
    extra = SUMMONED_BONUS - BONUS_PER
    if not INCLUDE_SUMMONED or extra == 0:
        return ""
    op = "add" if extra > 0 else "sub"
    return f"""
        push eax
        mov  edx, 0x{SUMMONED_ID:X}
        mov  eax, ebp
        mov  ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        pop  eax
        jz   no_summoned
        {op}  eax, {abs(extra)}
    no_summoned:
    """


def ranged_tail(data):
    if data is None:
        return RANGED_RESUME
    blob = bytes(data[off(SHIELD_RANGED_CAVE):off(SHIELD_RANGED_CAVE) + 0x60])
    return SHIELD_RANGED_CAVE if any(blob) else RANGED_RESUME


def points_into_cave(cur, src):
    """True if the 5 bytes at `src` are OUR jmp -- i.e. a rel32 landing anywhere in our cave.

    ⚠ Needed because a RE-TUNE moves the blocks inside the cave: after the 2026-08-29 change the
    melee blocks shifted 0x20 down, so the installed chain jumps matched neither the freshly-built
    bytes nor the pre-Magebane originals and the script called its own healthy install "FOREIGN"
    and aborted. Identity is "does it land in our reservation", not "is it byte-equal to what we
    would emit today"."""
    if len(cur) < 5 or cur[0] != 0xE9:
        return False
    tgt = src + 5 + struct.unpack("<i", cur[1:5])[0]
    return CAVE_VA <= tgt < CAVE_VA + CAVE_LIMIT


def build(data):
    """Lay the cave out sequentially; every cross-reference is backwards."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    out = {}

    def align(x):
        return (x + 0xF) & ~0xF

    # --- name AnsiString: [refcount=-1][len][chars][NUL]
    name_blob = b"\xFF\xFF\xFF\xFF" + struct.pack("<I", len(NAME)) + NAME + b"\x00"
    a_name = CAVE_VA
    chars = a_name + 8
    out["name"] = (a_name, name_blob)

    # --- cave_count(EAX = COMBAT OBJECT) -> AL = enchantment count
    # ⚠ It takes the COMBAT object, not the strategic unit (changed 2026-09-11 -- see the wall
    # note in the header). guard_unit converts it, returning 0 for a wall/nil, and we bail with
    # AL=0 so every caller's existing `test al,al / jz mb_out` takes the no-bonus path.
    # `jnz cnt_ok` over a 1-byte `ret`, NOT `jz <far label>`: the body is ~180 B, so a jz to the
    # tail would assemble as a 6-byte near jump and blow the 14-byte alignment slack.
    a_cnt = align(a_name + len(name_blob))
    GUARD_PROLOG = 10            # call(5) + test(2) + jnz(2) + ret(1)
    anchor = a_cnt + GUARD_PROLOG + 14   # + push*4(4) + sub esp,8(3) + mov ebp,eax(2) + call(5)
    src_cnt = f"""
        call 0x{cug.GUARD_UNIT:X}
        test eax, eax
        jnz  cnt_ok
        ret
    cnt_ok:
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, 8
        mov  ebp, eax
        call 0x{anchor:X}
        pop  edi
        sub  edi, 0x{anchor:X}
        and  dword ptr [esp], 0
        mov  eax, [edi + 0x{PTR_HSSET:X}]
        mov  eax, [eax]
        mov  eax, [eax + 0x80]
        mov  esi, [eax + 0x1C]
        mov  eax, [esi + 8]
        dec  eax
        mov  [esp+4], eax
    ab_loop:
        cmp  dword ptr [esp+4], 0
        jl   ab_done
        mov  eax, esi
        mov  edx, [esp+4]
        call 0x{GETABILITY:X}
        test eax, eax
        jz   ab_next
        mov  ebx, eax
        mov  edx, [edi + 0x{PTR_ENCHCLS:X}]
        mov  eax, ebx
        call 0x{ISCLASS:X}
        test al, al
        jz   ab_next
        mov  edx, [ebx + 0x0C]
        {excl_asm('edx')}
        mov  eax, ebp
        mov  ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jz   ab_next
        inc  dword ptr [esp]
    ab_next:
        dec  dword ptr [esp+4]
        jmp  ab_loop
    ab_done:
        mov  eax, [esp]
        {cap_asm()}
        {"" if BONUS_PER == 1 else f"imul eax, eax, {BONUS_PER}"}
        {summoned_asm()}
        add  esp, 8
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    b_cnt = bytes(ks.asm(src_cnt, a_cnt)[0])
    assert len(b_cnt) <= 192, (
        "cave_count is %d B; past 192 `melee1` slides 16 bytes down and every tail address "
        "below moves -- including the two build_shield.py pins" % len(b_cnt))
    out["count"] = (a_cnt, b_cnt)

    def pad_to(src, va, want, label):
        """Nop-pad a block to a PINNED length, inserting at `label` so the trailing jmp stays last.

        ⚠ The melee tails are pinned because build_shield.py asserts on them by absolute address:
        `M1_TAIL = 0x55812A09` is the melee1 exit jmp, and its check aborts the WHOLE script when
        the byte-run there is not magebane's `jmp 0x557666CF`. The 2026-09-11 wall guard made both
        melee blocks one byte shorter, which slid that jmp to 0x55812A08 and bricked build_shield.
        Pin the lengths instead of chasing the address through a third script."""
        b = bytes(ks.asm(src, va)[0])
        pad = want - len(b)
        if pad < 0:
            sys.exit("ERROR: block at 0x%08X is %d B, over its pinned %d B" % (va, len(b), want))
        if pad:
            src = src.replace("    %s:" % label, "    %s:\n" % label + "        nop\n" * pad, 1)
            b = bytes(ks.asm(src, va)[0])
        assert len(b) == want and b[-5] == 0xE9, "pad_to produced a malformed block"
        return b

    def has_ability(attacker_reg):
        return f"""
        mov  edx, 0x{MAGEBANE_ID:X}
        mov  eax, {attacker_reg}
        mov  ecx, [eax]
        call dword ptr [ecx + 0xA8]
        test al, al
        jz   mb_out
        """

    # ⚠ EMPTY ON PURPOSE: the multiply (and the Summoned top-up) now live at the END of
    # cave_count, so all three strike sites share one copy and cannot drift apart.
    mul = ""

    # --- melee1 : ATK=BL, DMG=byte[esp+3], target ESI ; EAX/ECX/EDX dead
    a_m1 = align(a_cnt + len(b_cnt))
    src_m1 = f"""
        {has_ability('ebp')}
        mov  eax, esi
        test eax, eax
        jz   mb_out
        call 0x{a_cnt:X}
        {mul}
        test al, al
        jz   mb_out
        add  bl, al
        add  byte ptr [esp+3], al
    mb_out:
        jmp  0x{CHAINS[0][2]:X}
    """
    b_m1 = pad_to(src_m1, a_m1, M1_LEN_PIN, "mb_out")
    assert a_m1 + len(b_m1) - 5 == M1_TAIL_PIN, "melee1 tail moved off build_shield.py's pin"
    out["melee1"] = (a_m1, b_m1)

    # --- melee3 : ATK=dword[EBX], DMG=dword[EBX+4], target EDI
    a_m3 = align(a_m1 + len(b_m1))
    src_m3 = f"""
        {has_ability('esi')}
        mov  eax, edi
        test eax, eax
        jz   mb_out
        call 0x{a_cnt:X}
        {mul}
        movzx ecx, al
        test ecx, ecx
        jz   mb_out
        add  [ebx], ecx
        add  [ebx+4], ecx
    mb_out:
        jmp  0x{CHAINS[1][2]:X}
    """
    b_m3 = pad_to(src_m3, a_m3, M3_LEN_PIN, "mb_out")
    out["melee3"] = (a_m3, b_m3)

    # --- ranged : [esp]=dmg [esp+4]=atk ; EAX/EDX LIVE -> save 3 regs, slots shift +12
    a_rg = align(a_m3 + len(b_m3))
    src_rg = f"""
        push eax
        push edx
        push ecx
        {has_ability('esi')}
        mov  eax, [ebp - 4]
        test eax, eax
        jz   mb_out
        call 0x{a_cnt:X}
        {mul}
        test al, al
        jz   mb_out
        add  byte ptr [esp+12], al
        add  byte ptr [esp+16], al
    mb_out:
        pop  ecx
        pop  edx
        pop  eax
        jmp  0x{ranged_tail(data):X}
    """
    # ⚠ THE TAIL JUMP'S ADDRESS IS LOAD-BEARING. build_shield.py pins it: `RNG_TAIL = 0x55812A7B`
    # is the 5-byte site it rewrites to chain itself in. Moving the ranged block's tail -- which the
    # 2026-08-29 re-tune did, by lifting the `imul` out into cave_count and shrinking the body 3
    # bytes -- would leave Shield patching the MIDDLE of our jmp. So pad the block so the tail lands
    # exactly on the pin, and fail loudly if it can no longer fit.
    b_rg = bytes(ks.asm(src_rg, a_rg)[0])
    pad = RNG_TAIL_PIN - (a_rg + len(b_rg) - 5)
    if pad < 0:
        sys.exit("ERROR: ranged block overruns build_shield.py's tail pin 0x%08X by %d bytes"
                 % (RNG_TAIL_PIN, -pad))
    if pad:
        src_rg = src_rg.replace("    mb_out:", "    mb_out:\n" + "        nop\n" * pad, 1)
        b_rg = bytes(ks.asm(src_rg, a_rg)[0])
    if a_rg + len(b_rg) - 5 != RNG_TAIL_PIN:
        sys.exit("ERROR: ranged tail landed at 0x%08X, not the pin 0x%08X"
                 % (a_rg + len(b_rg) - 5, RNG_TAIL_PIN))
    out["ranged"] = (a_rg, b_rg)

    # --- registration
    a_reg = align(a_rg + len(b_rg))
    reg_anchor = a_reg + 10      # call RegisterAbility(5) + call(5)
    src_reg = f"""
        call 0x{REGISTER_AB:X}
        call 0x{reg_anchor:X}
        pop  eax
        sub  eax, 0x{reg_anchor:X}
        lea  edx, [eax + 0x{chars:X}]
        mov  cx, word ptr [eax + 0x{CATWORD:X}]
        mov  eax, 0x{MAGEBANE_ID:X}
        call 0x{CREATE_ENH:X}
        mov  edx, eax
        mov  eax, ebx
        call 0x{REGISTER_AB:X}
        jmp  0x{REG_CONT:X}
    """
    b_reg = bytes(ks.asm(src_reg, a_reg)[0])
    out["reg"] = (a_reg, b_reg)
    out["_end"] = a_reg + len(b_reg)
    return out


def disasm(data, va, title):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    print("   --- %s @0x%08X (%d B) ---" % (title, va, len(data)))
    for i in md.disasm(data, va):
        print("   %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))


def main():
    ap = argparse.ArgumentParser(description="Magebane: +1/+1 per enchantment on the target")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--verify", action="store_true", help="report whether the chain is intact")
    ap.add_argument("--show", action="store_true", help="disassemble the caves")
    args = ap.parse_args()

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s" % DLL)
    data = bytearray(open(DLL, "rb").read())
    cv = build(data)

    # the shared wall guard -- same blob build_assassin.py installs; either may create it
    def g_rd(va, n):
        return bytes(data[off(va):off(va) + n])

    def g_wr(va, b):
        data[off(va):off(va) + len(b)] = b
    guard_blob = cug.blob()
    guard_state = cug.state(g_rd)
    OURS = ((CAVE_VA, CAVE_VA + CAVE_LIMIT),)

    print("build_magebane  id=0x%02X  +%d/+%d per enchantment  cap=%s  summoned=%s"
          % (MAGEBANE_ID, BONUS_PER, BONUS_PER, CAP or "none", INCLUDE_SUMMONED))
    print("  excluded ids: %s" % ", ".join(hex(i) for i in EXCLUDED))
    print("  cave 0x%08X..0x%08X (%d B used of %d)"
          % (CAVE_VA, cv["_end"] - 1, cv["_end"] - CAVE_VA, CAVE_LIMIT))
    for k in ("name", "count", "melee1", "melee3", "ranged", "reg"):
        va, b = cv[k]
        print("    %-7s 0x%08X  %3d B" % (k, va, len(b)))
    print("  shared cave_guard 0x%08X (%d B): %s" % (cug.GUARD_VA, len(guard_blob), guard_state))
    print()
    if guard_state == "foreign":
        sys.exit("ABORT: 0x%08X is occupied by something that is not the shared guard." % cug.GUARD_VA)

    if args.show:
        cug.show("   ")
        for k in ("count", "melee1", "melee3", "ranged", "reg"):
            va, b = cv[k]
            disasm(b, va, k)
        print()

    # desired byte edits
    edits = []
    for (nm, src, orig_t), key in zip(CHAINS, ("melee1", "melee3", "ranged")):
        edits.append((src, jmp_to(src, orig_t), jmp_to(src, cv[key][0]), "chain " + nm))
    edits.append((REG_HOOK, REG_ORIG, jmp_to(REG_HOOK, cv["reg"][0]), "registration hook"))

    if args.verify or (not args.apply and not args.undo):
        allok = True
        for va, o_b, n_b, lbl in edits:
            cur = bytes(data[off(va):off(va) + 5])
            if cur == n_b:
                st = "MAGEBANE"
            elif points_into_cave(cur, va):
                st = "MAGEBANE (stale layout -- --apply refreshes)"
            elif cur == o_b:
                st = "vanilla/chain-intact"
            else:
                st = "FOREIGN"
            if cur != n_b:
                allok = False
            print("  %-20s 0x%08X  %s  (%s)" % (lbl, va, cur.hex(), st))
        cave_ok = all(bytes(data[off(cv[k][0]):off(cv[k][0]) + len(cv[k][1])]) == cv[k][1]
                      for k in ("name", "count", "melee1", "melee3", "ranged", "reg"))
        print("  caves match: %s" % cave_ok)
        cave_ok = cave_ok and guard_state == "ours"
        print("  shared guard installed: %s" % (guard_state == "ours"))
        if args.verify:
            print("\nSTATUS: %s" % ("APPLIED and intact" if (allok and cave_ok)
                                    else "NOT fully applied -- re-run with --apply"))
            return

    if args.undo:
        n = 0
        for va, o_b, n_b, lbl in edits:
            cur = bytes(data[off(va):off(va) + 5])
            if cur == n_b or (va != REG_HOOK and points_into_cave(cur, va)):
                data[off(va):off(va) + 5] = o_b
                n += 1
        data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = b"\x00" * CAVE_LIMIT
        # ⚠ SHARED: build_assassin.py calls the same guard. Only drop it when nothing else does.
        cug.undo_if_unused(g_rd, g_wr, exclude=OURS)
        open(DLL, "wb").write(data)
        print("UNDO: restored %d hook(s), zeroed the cave. No backup touched." % n)
        return

    if cv["_end"] - CAVE_VA > CAVE_LIMIT:
        sys.exit("ERROR: cave overflows its %d-byte reservation" % CAVE_LIMIT)
    if CAVE_VA + CAVE_LIMIT > CODE_ZERO_END:
        sys.exit("ERROR: cave past end of CODE")

    fresh = all(bytes(data[off(va):off(va) + 5]) == o_b for va, o_b, n_b, _ in edits)
    done = all(bytes(data[off(va):off(va) + 5]) == n_b
               or (va != REG_HOOK and points_into_cave(bytes(data[off(va):off(va) + 5]), va))
               for va, o_b, n_b, _ in edits)
    if not fresh and not done:
        sys.exit("ABORT: hook sites are in a mixed/foreign state -- inspect before proceeding.\n"
                 "       (Did build_assassin / build_ranged_slayers / build_invis_penalty re-run?)")
    if fresh:
        zone = bytes(data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT])
        if zone != b"\x00" * CAVE_LIMIT:
            sys.exit("ABORT: cave zone 0x%08X is not zero -- someone else owns it" % CAVE_VA)

    caves_ok = all(bytes(data[off(cv[k][0]):off(cv[k][0]) + len(cv[k][1])]) == cv[k][1]
                   for k in ("name", "count", "melee1", "melee3", "ranged", "reg"))
    caves_ok = caves_ok and guard_state == "ours"
    if done and caves_ok:
        print("Already applied and up to date -- nothing to do.")
        return

    if not args.apply:
        print("DRY RUN -- re-run with --apply to commit.")
        print("(Close AoW.exe / AoWCompat.exe / AoWDevEd.exe first -- they lock the DLL.)")
        return

    # ⚠ SNAPSHOT GATE (2026-09-11). `not os.path.exists(BAK)` is NOT proof this file is
    # pre-Magebane: on a re-tune -- or after the backups directory was pruned -- it mints a
    # snapshot OF OUR OWN OUTPUT under a name that reads as pre-patch. `fresh` means all four
    # hook sites still hold their vanilla byte-runs, which is the actual test.
    if fresh and not os.path.exists(BAK):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BAK)
        print("backup -> %s" % os.path.basename(BAK))
    elif not fresh:
        print("no snapshot: the hooks are already Magebane's, so this file is NOT pre-Magebane")

    payload = bytearray(CAVE_LIMIT)
    for k in ("name", "count", "melee1", "melee3", "ranged", "reg"):
        va, b = cv[k]
        payload[va - CAVE_VA: va - CAVE_VA + len(b)] = b
    data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = payload
    if guard_state != "ours":            # zone proved free/ours above; never overwrite a stranger
        g_wr(cug.GUARD_VA, guard_blob)
        print("shared cave_guard -> 0x%08X (%d B)" % (cug.GUARD_VA, len(guard_blob)))
    for va, o_b, n_b, lbl in edits:
        data[off(va):off(va) + 5] = n_b
    try:
        open(DLL, "wb").write(data)
    except PermissionError:
        sys.exit("ERROR: %s is locked. Close the AoW binaries and retry." % os.path.basename(DLL))

    print("APPLIED. Revert with --undo -- surgical. (A .pre-* snapshot is NOT a revert path:")
    print("  it restores the whole file and wipes every feature applied after it.)")
    print("WARNING: if the game asserts 'Ability already registered' or dies in Localize.dpl at")
    print("  startup, ability id 0x%02X is not usable -- change MAGEBANE_ID and re-run."
          % MAGEBANE_ID)


if __name__ == "__main__":
    main()
