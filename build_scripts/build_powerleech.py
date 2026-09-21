#!/usr/bin/env python3
r"""
AoW1 POWER LEECH (ex Power Leak) -- AoWEPACK.dpl, 5 host bytes + one cave.

DESIGN (user ruling 2026-09-07)
------------------------------
Vanilla Power Leak halves EVERY player's net power, including its caster's. That is dropped.
Power Leech instead makes the caster STEAL 25% of the power income of every magic node owned by
another player: the owner loses it, the caster gains it. Only one may be active map-wide --
requirement C, which is ALREADY VANILLA and needed no code (see "Requirement C" below).

Cost and upkeep stay 100 / 10. Not touched here or anywhere.

THE THREE WRITES
----------------
  1. 0x5577CEC5  4 bytes -- the rel32 of the `call` that OPENS
     `AoWE.TPlayerMagicControl.GetNetPower @0x5577CEC4`, repointed from
     `GetPower @0x5577CA00` to `cave_powerleech @0x55848000`.
       vanilla  E8 37 FB FF FF   call 0x5577CA00
       patched  E8 37 B1 0C 00   call 0x55848000
     Nothing is displaced, no `.reloc` entry is disturbed (the only one in
     0x5577CEB0..0x5577CEF0 is 0x5577CECB, the `mov edx,[0x558FA040]` operand -- four bytes
     past the end of our window), and the undo is a 4-byte write.
     ⚠ The hook MUST be at the opening call: on entry EAX is the TPlayerMagicControl. Anything
     later cannot recover it -- GetPower returns the sum in EAX and restores ebx/esi/edi.

  2. 0x5577CED8  1 byte  08 -> 00 -- kills the vanilla halving in place.
       vanilla  F6 42 10 08   test byte ptr [edx+0x10], 8   (bit 3 = a Power Leak is active)
       patched  F6 42 10 00   test byte ptr [edx+0x10], 0   -> ZF always set, the `je` at
                              0x5577CED9 always taken, `inc eax / sar eax,1 / jns / adc` skipped.
     Same instruction lengths, no displacement, one-byte undo.

  3. cave_powerleech @ 0x55848000, span 0x400, EXCLUSIVE. 0x55847016..0x5584A000 verified all
     zero; starting at exactly 0x55848000 clears the zero-asserts of both neighbours
     (build_spellward_rescope.py owns 0x55847000+0x100 and asserts zero to 0x55848000;
     build_spellcast_herotier.py owns 0x55846000+0x80 and asserts zero to 0x55848000).

THE CAVE
--------
    cave_powerleech(EAX = TPlayerMagicControl) -> EAX = power, adjusted
        base = GetPower(pmc)                      the real function, called first
        if no Power Leech is active            -> return base
        caster = the first enchantment in [gmc+0x14] with [e+0x18] == 3, its [e+0x19]
        if [[pmc+0x10]+0xA6] == caster         -> return base + SUM over every OTHER player of
                                                  nodepower(that player) >> 2
        else                                   -> return base - nodepower(pmc) >> 2

    nodepower(EAX = TPlayerMagicControl) -> EAX
        walks the player's own TPowerSourceList [pmc+0x40] exactly as GetPower does, keeps only
        sources whose VMT +0x50 is `TPlayerStructurePowerSource.Power` AND whose target
        structure's VMT +0x1F8 is `TPowerNode.GetPower`, and sums the virtual's return.

⚠ NOT a percentage of GetPower. That sum also carries city production (TProductionPlace
registers a power source too) and hero mana generation, neither of which this design touches.

⚠ NO CACHE, deliberately. Ownership changes mid-turn and GetNetPower runs on UI repaint, so a
day-keyed cache would be wrong. Worst case ~600 iterations, for one player.

WHY THE VMT SLOT IS THE NODE DISCRIMINATOR
------------------------------------------
All seven node classes (Power, Life, Death, Earth, Air, Fire, Water) descend from TPowerNode and
override only ClassID and GetMagicSphere, so all seven SHARE `TPowerNode.GetPower` in slot
+0x1F8. `[[struct]+0x1F8] == TPowerNode.GetPower` is therefore true for exactly those seven,
false for cities and false for TRandomNode (a TProductionPlace descendant). No IsClass, no
seven-way ClassID compare, and it survives a node type added later.

The +0x50 source-class test comes first and is not optional: a TPowerSourceList also holds
THeroPowerSource and TExternalPowerSource, whose `[src+8]` is not a TStructure at all.

⚠ NODE POWER IS 12 ON THIS INSTALL, NOT VANILLA'S 10
----------------------------------------------------
    557D03E4  live  B8 0C 00 00 00   mov eax, 0xC   (12)
              van   B8 0A 00 00 00   mov eax, 0xA   (10)
An undocumented pre-convention hand edit -- `grep -rl 557D03` over build_scripts/ finds nothing.
This script ABORTS if that byte is not 0x0C, because 25% of 12 is exactly 3 and per-node and
per-player rounding therefore coincide today; they diverge the moment node power stops being a
multiple of 4. (Adjacent and owned: TProductionPlace.GetPower @0x557BE4CC is picks*6 + 6 --
build_shipyard_income.py:611.)

PIC -- the anchor resolves to TPowerNode.GetPower, not to a data global
----------------------------------------------------------------------
The DPL never loads at its preferred base. The standard `call $+5 ; pop ecx ; sub ecx, <imm>`
rebase anchor is used once, via assemble_pic() lifted verbatim from
build_spellcast_herotier.py:132. It is subtracted so that EDI ends up holding the RUNTIME
address of `TPowerNode.GetPower` itself -- not the bare rebase delta. Two consequences:

  * the node test is `cmp dword ptr [edx+0x1F8], edi`, with no immediate at all;
  * every other absolute the cave needs is reached as a SMALL signed offset from EDI
    (AoWHSMap = edi + 0x129C78, TPlayerStructurePowerSource.Power = edi - 0x6E874), so the
    assembled cave contains NO 0x55xxxxxx operand of any kind, and needs no .reloc entry.

All three resolved addresses are re-derived from the assembled bytes at build time and asserted
against 0x557D03C8 / 0x558FA040 / 0x55761B54 -- a PIC anchor that is short by even 0x4C
assembles clean, verifies clean and reads the wrong memory forever (2026-08 Vision IX).

RNG / DETERMINISM
-----------------
Nothing here draws. The result is a pure function of replicated state -- the enchantment list,
[ench+0x19], the player list and [struct+0x30] -- with no draw and no cache, so it is identical
on every peer. `rng_audit.py --owners` must gain ZERO sites.

NEUTRAL PLAYER 0 -- what this build does, stated rather than guessed
-------------------------------------------------------------------
Player index 0 is a REAL TPlayer: TPlayerList.SetNumberOfPlayers @0x557546B0 creates it like any
other (giving it [+0xA7] = 4) and TPlayer.Create @0x55750EA8 gives every player a
TPlayerMagicControl unconditionally; TPowerNode.SetPlayer @0x557D0584 registers a power source
for any owner byte != 0xFF, so an owner-0 node IS in player 0's list. The engine's own
GetNumberOfPlayers returns count-1 and RaceToPlayer starts at 1, i.e. it treats 0 as not-a-player.

*** This cave walks the WHOLE player list, index 0 included: a node owned by the neutral player
is leeched like any other, and the neutral player's own net power drops by the same amount. ***
The alternative (skip index 0) would have to skip it in BOTH branches or power would vanish, and
uniformity is the simpler rule. Truly OWNERLESS nodes ([struct+0x30] == 0xFF) are in nobody's
power-source list and give nothing, which is the user's "strict transfer" ruling. Whether any
shipped/generated map actually assigns a node to owner 0 is an IN-GAME OBSERVABLE, listed in the
checklist -- it does not change the code either way.

WHAT WAS SETTLED AND NEEDED NO CODE
-----------------------------------
Requirement C, one at a time: `TGlobalEnchantment.CanActivate @0x5577DAE8` reads [ench+0x18] and
for a type code in 1..7 does `bt dword ptr [gmc+0x10], eax`, refusing if set. [gmc+0x10] is
rebuilt from the whole enchantment list by UpdateActiveEnchantments @0x5577E46C with NO
per-player filter, so one Power Leech anywhere blocks every player including its caster.
TPowerLeakEnchantment VMT +0x64 is that inherited CanActivate. VERIFIED, NOT BUILT.

Caster elimination: `TPlayer.SetGameOverStatus @0x55751848` calls
`TGlobalMagicControl.RemovePlayerEnchantments @0x5577E37C` when [player+0x44] == 2, and that walks
[gmc+0x14] removing every enchantment whose [e+0x19] equals the eliminated player's index. A
defeated caster's leech therefore ends by itself. VERIFIED at 0x55751B03, not assumed.

TPlayer holds NO back-pointer to the map -- TPlayer.Create wires back-pointers the other way
(pmc[+0x10] = player, AI control [+8] = player). The map global is the only route to the player
list, which is why the anchor exists.

Cast and dispel already take effect immediately: `TPowerLeakEnchantment.Activate @0x557F1080` and
`Deactivate @0x557F10C8` loop every player calling TPlayerMagicControl.Update. ⚠ DO NOT TOUCH
THEM.

WHAT THIS SCRIPT DOES NOT DO
----------------------------
  * the spell/enchantment NAME  -> build_resstr_names.py (ResStr.txt:7495, one row, which also
    fixes the "%s is already active" refusal because TPowerLeakEnchantment.Create loads
    [ench+0x1C] from the same AoWE.PowerLeakRStr)
  * the spell DESCRIPTION       -> build_pfs_typos.py (Release/Spells.pfs record 58)
  * the realm-window row        -> AoW.exe/AoWCompat.exe, see 10-ai-and-structures.md §6.4
  * cost / upkeep / AI priority -> unchanged. GetAIUpkeepPriority @0x557F1078 still returns 750;
    the AI budget reads GetManaIncome, so it follows the new value automatically.

UNDO
----
`--undo --apply` is surgical and touches no backup: the rel32 goes back to GetPower, 0x5577CED8
goes back to 0x08, and 0x55848000..0x558483FF is zeroed. Round-trips to a byte-identical file.

Backup `backups/AoWEPACK.dpl.pre-powerleech` is minted ONLY from a file proved to be in the
pre-feature state (hook still pointing at GetPower AND the halving byte still 0x08 AND our zone
still zero) -- never on --undo, never on a re-tune, never because the backup file is absent.

Usage:
  python build_scripts/build_powerleech.py            dry run + verify current state
  python build_scripts/build_powerleech.py --apply    patch
  python build_scripts/build_powerleech.py --undo --apply    surgical revert
  python build_scripts/build_powerleech.py --dis      disassemble the cave and stop
"""
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys

from capstone import CS_ARCH_X86, CS_MODE_32, Cs
from keystone import KS_ARCH_X86, KS_MODE_32, Ks

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-powerleech")
IMAGE_BASE = 0x55700000

# ---- addresses (preferred-base VAs; every one byte-verified against the live file) ---------
GETNETPOWER = 0x5577CEC4      # AoWE.TPlayerMagicControl.GetNetPower -- opens with the call
HOOK_CALL = 0x5577CEC4        # the `E8 rel32` whose displacement we repoint
GETPOWER = 0x5577CA00         # AoWE.TPlayerMagicControl.GetPower   (EAX = pmc -> EAX = sum)
HALVE_BYTE = 0x5577CED8       # the `08` of `test byte ptr [edx+0x10], 8`
GETITEMS = 0x5577C2A0         # AoWE.TPowerSourceList.GetItems      (EAX = list, EDX = i)
GETENCH = 0x5577E13C          # AoWE.TGlobalEnchantmentList.GetEnchantments (EAX = list, EDX = i)
GETPLAYERS = 0x557544D0       # AoWE.TPlayerList.GetPlayers         (EAX = list, EDX = i)

NODE_GETPOWER = 0x557D03C8    # PowerNode.TPowerNode.GetPower  -- the anchor AND the node test
PS_POWER = 0x55761B54         # AoWE.TPlayerStructurePowerSource.Power -- the source-class test
AOWHSMAP = 0x558FA040         # AoWE.AoWHSMap (the map pointer itself, not a pointer to it)
NODE_VALUE_VA = 0x557D03E4    # `mov eax, 0xC` inside TPowerNode.GetPower -- asserted to be 12

MAP_OFF = AOWHSMAP - NODE_GETPOWER        # +0x129C78
PSP_OFF = PS_POWER - NODE_GETPOWER        # -0x6E874

# struct offsets, all read out of live code rather than assumed
O_GMC = 0x188                 # [map + 0x188]     TGlobalMagicControl
O_ENCH_SET = 0x10             # [gmc + 0x10]      byte-set of active enchantment type codes
O_ENCH_LIST = 0x14            # [gmc + 0x14]      TGlobalEnchantmentList
O_PLAYERS = 0x140             # [map + 0x140]     TPlayerList
O_INNER = 0x08                # [list + 8]        the inner TList (count at +8, array at +4)
O_ENCH_TYPE = 0x18            # [ench + 0x18]     type code; Power Leak/Leech is 3
O_ENCH_CASTER = 0x19          # [ench + 0x19]     caster player index
O_PMC_PLAYER = 0x10           # [pmc + 0x10]      TPlayer
O_PMC_SOURCES = 0x40          # [pmc + 0x40]      TPowerSourceList
O_PLAYER_PMC = 0x54           # [player + 0x54]   TPlayerMagicControl
O_PLAYER_IDX = 0xA6           # [player + 0xA6]   player index (== its TPlayerList position)
O_SRC_TARGET = 0x08           # [src + 8]         the TStructure a TPlayerStructurePowerSource
                              #                   points at
V_COUNT = 0x54                # [listvmt + 0x54]  count
V_SRC_POWER = 0x50            # [srcvmt  + 0x50]  TPowerSource.Power
V_GETPOWER = 0x1F8            # [structvmt + 0x1F8] TStructure.GetPower
ENCH_TYPE_POWERLEAK = 3

CAVE = 0x55848000             # exclusive reservation for this feature
CAVE_SPAN = 0x400             # bytes this script owns and zeroes on --undo
ZONE_END = 0x5584A000         # verified all-zero to here; asserted beyond the cave

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)


def assemble_pic(src_fn, addr, npops=1):
    """Two-pass assemble: src_fn(pop_vas) places `pop ecx` immediately after each `call L`;
    iterate until the guessed pop VAs converge (the call/pop rebase-delta idiom).

    Lifted verbatim from build_spellcast_herotier.py:132 -- do not re-derive it."""
    guess = [addr + 0x20 * (i + 1) for i in range(npops)]
    for _ in range(6):
        code = bytes(ks.asm(src_fn(guess), addr)[0])
        pops = [ins.address for ins in cs.disasm(code, addr)
                if ins.mnemonic == "pop" and ins.op_str == "ecx"][:npops]
        if pops == guess:
            return code
        assert len(pops) == npops, f"expected {npops} pops, found {len(pops)}"
        guess = pops
    raise RuntimeError("two-pass assembly did not converge")


def src_powerleech(p):
    """p[0] = the VA the single `pop ecx` will land on. NOTE: keystone hangs on ';' comments
    inside the source -- keep this block bare (project trap)."""
    anchor_imm = p[0] - NODE_GETPOWER          # ecx = runtime(TPowerNode.GetPower) after the sub
    return f"""
        push ebp
        mov ebp, esp
        add esp, -0x10
        push ebx
        push esi
        push edi
        mov dword ptr [ebp-4], eax
        call 0x{GETPOWER:X}
        mov esi, eax
        call L1
    L1: pop ecx
        sub ecx, 0x{anchor_imm:X}
        mov edi, ecx
        mov eax, dword ptr [edi + 0x{MAP_OFF:X}]
        test eax, eax
        je Ldone
        mov eax, dword ptr [eax + 0x{O_GMC:X}]
        test eax, eax
        je Ldone
        test byte ptr [eax + 0x{O_ENCH_SET:X}], {1 << ENCH_TYPE_POWERLEAK}
        je Ldone
        mov ebx, dword ptr [eax + 0x{O_ENCH_LIST:X}]
        test ebx, ebx
        je Ldone
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x{V_COUNT:X}]
        mov dword ptr [ebp-0x10], eax
        mov dword ptr [ebp-0xC], 0
    Lench:
        mov edx, dword ptr [ebp-0xC]
        cmp edx, dword ptr [ebp-0x10]
        jge Ldone
        mov eax, ebx
        call 0x{GETENCH:X}
        test eax, eax
        je Lenchnext
        cmp byte ptr [eax + 0x{O_ENCH_TYPE:X}], {ENCH_TYPE_POWERLEAK}
        je Lfound
    Lenchnext:
        inc dword ptr [ebp-0xC]
        jmp Lench
    Lfound:
        movzx eax, byte ptr [eax + 0x{O_ENCH_CASTER:X}]
        mov dword ptr [ebp-8], eax
        mov edx, dword ptr [ebp-4]
        mov edx, dword ptr [edx + 0x{O_PMC_PLAYER:X}]
        test edx, edx
        je Ldone
        movzx edx, byte ptr [edx + 0x{O_PLAYER_IDX:X}]
        cmp edx, eax
        je Lcaster
        mov eax, dword ptr [ebp-4]
        call Lnodepower
        sar eax, 2
        sub esi, eax
        jmp Ldone
    Lcaster:
        mov eax, dword ptr [edi + 0x{MAP_OFF:X}]
        mov eax, dword ptr [eax + 0x{O_PLAYERS:X}]
        test eax, eax
        je Ldone
        mov ebx, eax
        mov eax, dword ptr [ebx + 0x{O_INNER:X}]
        test eax, eax
        je Ldone
        mov eax, dword ptr [eax + 0x{O_INNER:X}]
        mov dword ptr [ebp-0x10], eax
        mov dword ptr [ebp-0xC], 0
    Lplayer:
        mov ecx, dword ptr [ebp-0xC]
        cmp ecx, dword ptr [ebp-0x10]
        jge Ldone
        cmp ecx, dword ptr [ebp-8]
        je Lplnext
        mov edx, ecx
        mov eax, ebx
        call 0x{GETPLAYERS:X}
        test eax, eax
        je Lplnext
        mov eax, dword ptr [eax + 0x{O_PLAYER_PMC:X}]
        test eax, eax
        je Lplnext
        call Lnodepower
        sar eax, 2
        add esi, eax
    Lplnext:
        inc dword ptr [ebp-0xC]
        jmp Lplayer
    Ldone:
        mov eax, esi
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret

    Lnodepower:
        push ebp
        mov ebp, esp
        add esp, -0x0C
        push ebx
        push esi
        xor esi, esi
        test eax, eax
        je Lnpdone
        mov eax, dword ptr [eax + 0x{O_PMC_SOURCES:X}]
        test eax, eax
        je Lnpdone
        mov dword ptr [ebp-4], eax
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x{V_COUNT:X}]
        mov dword ptr [ebp-8], eax
        mov dword ptr [ebp-0xC], 0
    Lnploop:
        mov edx, dword ptr [ebp-0xC]
        cmp edx, dword ptr [ebp-8]
        jge Lnpdone
        mov eax, dword ptr [ebp-4]
        call 0x{GETITEMS:X}
        test eax, eax
        je Lnpnext
        mov ebx, eax
        mov edx, dword ptr [ebx]
        lea ecx, [edi + 0x{PSP_OFF & 0xFFFFFFFF:X}]
        cmp dword ptr [edx + 0x{V_SRC_POWER:X}], ecx
        jne Lnpnext
        mov eax, dword ptr [ebx + 0x{O_SRC_TARGET:X}]
        test eax, eax
        je Lnpnext
        mov edx, dword ptr [eax]
        cmp dword ptr [edx + 0x{V_GETPOWER:X}], edi
        jne Lnpnext
        call edi
        add esi, eax
    Lnpnext:
        inc dword ptr [ebp-0xC]
        jmp Lnploop
    Lnpdone:
        mov eax, esi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    """


cave = assemble_pic(src_powerleech, CAVE, 1)
assert len(cave) <= CAVE_SPAN, f"cave {len(cave)} B exceeds owned span {CAVE_SPAN}"
CAVE_REGION = cave + b"\x00" * (CAVE_SPAN - len(cave))
ZERO_REGION = b"\x00" * CAVE_SPAN


def rel32(site, dest):
    return struct.pack("<i", dest - (site + 5))


HOOK_OLD = b"\xE8" + rel32(HOOK_CALL, GETPOWER)
HOOK_NEW = b"\xE8" + rel32(HOOK_CALL, CAVE)
HALVE_OLD = b"\x08"
HALVE_NEW = b"\x00"


# ============================================================ build-time guards
def build_checks(code=None, base=CAVE):
    """G1..G6. They tie the ASSEMBLED BYTES back to the constants -- a hand edit of the source
    that breaks the PIC anchor or trips the keystone imm8 trap must not build clean."""
    code = cave if code is None else code
    ins = list(cs.disasm(code, base))
    txt = [(i.address, i.mnemonic, i.op_str) for i in ins]

    # G1 -- the anchor. `call L1 / pop ecx / sub ecx, imm` must resolve to TPowerNode.GetPower.
    #       A short anchor assembles clean, verifies clean and reads the wrong memory forever.
    pops = [i for i in ins if i.mnemonic == "pop" and i.op_str == "ecx"]
    assert len(pops) == 1, "G1 anchor: %d `pop ecx`, expected exactly 1" % len(pops)
    pop_va = pops[0].address
    calls = [i for i in ins if i.mnemonic == "call" and i.op_str == hex(pop_va)]
    assert len(calls) == 1 and calls[0].address + calls[0].size == pop_va, \
        "G1 anchor: the `call` before `pop ecx` does not target the pop itself"
    subs = [i for i in ins if i.mnemonic == "sub" and i.op_str.startswith("ecx, 0x")]
    assert len(subs) == 1, "G1 anchor: %d `sub ecx, imm`, expected 1" % len(subs)
    resolved = pop_va - int(subs[0].op_str.split(", ")[1], 16)
    assert resolved == NODE_GETPOWER, (
        "G1 anchor: resolves to %08X, expected TPowerNode.GetPower %08X (short by %d)"
        % (resolved, NODE_GETPOWER, NODE_GETPOWER - resolved))

    # G2 -- every EDI-relative absolute lands where it is supposed to. EDI holds
    #       runtime(TPowerNode.GetPower), so `[edi + d]` is the VA NODE_GETPOWER + d.
    disps = set()
    for i in ins:
        for m in re.finditer(r"\[edi ([+-]) (0x[0-9a-f]+)\]", i.op_str):
            d = int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
            disps.add(NODE_GETPOWER + d)
    assert AOWHSMAP in disps, (
        "G2 edi-relative: AoWHSMap %08X is not among the resolved targets %s"
        % (AOWHSMAP, ["%08X" % x for x in sorted(disps)]))
    assert PS_POWER in disps, (
        "G2 edi-relative: TPlayerStructurePowerSource.Power %08X is not among %s"
        % (PS_POWER, ["%08X" % x for x in sorted(disps)]))
    stray = disps - {AOWHSMAP, PS_POWER}
    assert not stray, "G2 edi-relative: unsanctioned target(s) %s" % ["%08X" % x for x in stray]

    # G3 -- no absolute 0x55xxxxxx operand of any kind survives in the cave. Direct calls are
    #       E8 rel32 (capstone prints the resolved target, the BYTES are relative), so they are
    #       excluded by opcode, not by text.
    bad = [(("%08X" % a), m, o) for a, m, o in txt
           if m not in ("call", "jmp", "je", "jne", "jge", "jl", "jle", "jg", "jns")
           and re.search(r"0x55[0-9a-f]{6}", o)]
    assert not bad, "G3 absolutes: %s" % bad

    # G4 -- the keystone imm8 trap: `push 0xFFFF` silently assembles to `6A FF` = push -1.
    #       Test for ANY operand rendering as -1, not for a `, -1` suffix.
    signed = [("%08X" % a, m, o) for a, m, o in txt if re.search(r"(?:^|,\s*)-1\b", o)]
    assert not signed, "G4 imm8 trap: -1 operand(s) %s" % signed

    # G5 -- every direct call goes to a sanctioned engine entry point or stays inside the cave.
    allowed = {GETPOWER, GETENCH, GETPLAYERS, GETITEMS}
    tgts = set()
    for i in ins:
        if i.mnemonic == "call" and i.op_str.startswith("0x"):
            tgts.add(int(i.op_str, 16))
    outside = {t for t in tgts if not (base <= t < base + len(code))} - allowed
    assert not outside, "G5 call targets: unsanctioned %s" % ["%08X" % x for x in sorted(outside)]

    # G6 -- both frames balance: one `mov esp, ebp` + `pop ebp` + `ret` per `mov ebp, esp`.
    n_enter = sum(1 for _a, m, o in txt if m == "mov" and o == "ebp, esp")
    n_leave = sum(1 for _a, m, o in txt if m == "mov" and o == "esp, ebp")
    n_ret = sum(1 for _a, m, _o in txt if m == "ret")
    assert n_enter == n_leave == n_ret == 2, (
        "G6 frames: %d enter / %d leave / %d ret, expected 2/2/2" % (n_enter, n_leave, n_ret))


build_checks()


# ============================================================ PE helpers
def load_secs(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    sect = e + 24 + optsz
    secs = []
    for i in range(nsec):
        b = sect + i * 40
        vs, va, rs, raw = struct.unpack_from("<IIII", d, b + 8)
        secs.append((d[b:b + 8].rstrip(b"\0").decode("latin1"), va, vs, raw, rs))
    return secs


def va2off(secs, va):
    """VA -> file offset, resolved PER SECTION. In AoWEPACK.dpl CODE and DATA have DIFFERENT
    deltas (-0xC00 and -0x1200); a flat delta is silently wrong for one of them."""
    r = va - IMAGE_BASE
    for _nm, v, vs, raw, rs in secs:
        if v <= r < v + max(vs, rs):
            return raw + (r - v)
    raise ValueError(hex(va))


def reloc_hits(d, secs, lo, hi):
    """Every .reloc entry whose target VA lies in [lo, hi)."""
    e = struct.unpack_from("<I", d, 0x3C)[0]
    magic = struct.unpack_from("<H", d, e + 24)[0]
    dd = e + 24 + (96 if magic == 0x10B else 112)
    rva, size = struct.unpack_from("<II", d, dd + 5 * 8)
    off = va2off(secs, IMAGE_BASE + rva)
    end, hits = off + size, []
    while off < end:
        pg, blk = struct.unpack_from("<II", d, off)
        if blk == 0:
            break
        for i in range((blk - 8) // 2):
            w = struct.unpack_from("<H", d, off + 8 + i * 2)[0]
            if w >> 12 and lo <= IMAGE_BASE + pg + (w & 0xFFF) < hi:
                hits.append(IMAGE_BASE + pg + (w & 0xFFF))
        off += blk
    return hits


# ============================================================ report
def show_dis():
    print("cave_powerleech @ %08X  (%d bytes, owns %#x to %08X; zone asserted clear to %08X)"
          % (CAVE, len(cave), CAVE_SPAN, CAVE + CAVE_SPAN, ZONE_END))
    labels = {}
    for i in cs.disasm(cave, CAVE):
        if i.mnemonic == "pop" and i.op_str == "ecx":
            labels[i.address] = "L1 (anchor)"
    for i in cs.disasm(cave, CAVE):
        tag = "  <-- " + labels[i.address] if i.address in labels else ""
        print("  %08X  %-24s %s %s%s"
              % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str, tag))
    pop_va = next(i.address for i in cs.disasm(cave, CAVE)
                  if i.mnemonic == "pop" and i.op_str == "ecx")
    sub = next(i for i in cs.disasm(cave, CAVE)
               if i.mnemonic == "sub" and i.op_str.startswith("ecx, 0x"))
    anchor = pop_va - int(sub.op_str.split(", ")[1], 16)
    print()
    print("  anchor: pop ecx @%08X  -  %s  ->  EDI = %08X  (TPowerNode.GetPower, expected %08X)"
          % (pop_va, sub.op_str, anchor, NODE_GETPOWER))
    print("  edi + %#08x -> %08X  AoWE.AoWHSMap                       (expected %08X)"
          % (MAP_OFF, anchor + MAP_OFF, AOWHSMAP))
    print("  edi - %#08x -> %08X  TPlayerStructurePowerSource.Power   (expected %08X)"
          % (-PSP_OFF, anchor + PSP_OFF, PS_POWER))
    print()
    print("  hook  @ %08X: %s -> %s   (only the 4 rel32 bytes at %08X change)"
          % (HOOK_CALL, HOOK_OLD.hex(" "), HOOK_NEW.hex(" "), HOOK_CALL + 1))
    print("  halve @ %08X: %s -> %s   (test byte ptr [edx+0x10], 8 -> , 0)"
          % (HALVE_BYTE, HALVE_OLD.hex(), HALVE_NEW.hex()))


def kill_running():
    # SCRATCH GUARD: AOW_GAME_DIR set => not the real install; never kill the user's game.
    if os.environ.get("AOW_GAME_DIR"):
        return
    ps = ("Get-Process | Where-Object { $_.ProcessName -match "
          "'^(AoW|AoWCompat|AoWDevEd|AoWEd)$' } | Stop-Process -Force")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=30)
    except Exception as ex:                                       # noqa: BLE001
        print("  (could not run the process kill: %s)" % ex)


def main():
    argv = sys.argv[1:]
    show_dis()
    print()
    if "--dis" in argv or "--show" in argv:
        return 0

    undo = "--undo" in argv
    d = bytearray(open(DLL, "rb").read())
    secs = load_secs(d)

    def rd(va, n):
        o = va2off(secs, va)
        return bytes(d[o:o + n])

    # ---- preconditions ------------------------------------------------------------------
    nodeval = rd(NODE_VALUE_VA, 5)
    if nodeval[0] != 0xB8 or nodeval[4] != 0x00:
        print("ABORT: %08X is %s, not `mov eax, imm32` -- wrong address for the node's power "
              "constant." % (NODE_VALUE_VA, nodeval.hex(" ")))
        return 1
    power = struct.unpack_from("<I", nodeval, 1)[0]
    print("node power constant @%08X = %d" % (NODE_VALUE_VA, power))
    if power != 12:
        print("ABORT: TPowerNode.GetPower returns %d, not 12. This install's value was hand-"
              "edited from vanilla's 10 and nothing owns that edit; 25%% of 12 is exactly 3, so "
              "per-node and per-player rounding coincide only while it stays a multiple of 4. "
              "Re-read the rounding note in this file's docstring before changing this check."
              % power)
        return 1

    # the two engine entry points the cave calls must still be what we think they are
    if rd(GETPOWER, 3) != bytes.fromhex("53 56 57"):
        print("ABORT: GetPower @%08X does not open `push ebx/esi/edi`." % GETPOWER)
        return 1
    if rd(GETITEMS, 3) != bytes.fromhex("8b 40 08") or \
            rd(GETENCH, 3) != bytes.fromhex("8b 40 08") or \
            rd(GETPLAYERS, 2) != bytes.fromhex("85 d2"):
        print("ABORT: one of GetItems/GetEnchantments/GetPlayers does not match its expected "
              "opening bytes.")
        return 1
    if rd(NODE_GETPOWER, 2) != bytes.fromhex("53 8b"):
        print("ABORT: TPowerNode.GetPower @%08X does not open `push ebx / mov ebx,eax`."
              % NODE_GETPOWER)
        return 1
    if rd(PS_POWER, 6) != bytes.fromhex("8b 40 08 8b 10 ff"):
        print("ABORT: TPlayerStructurePowerSource.Power @%08X is not `mov eax,[eax+8] / "
              "mov edx,[eax] / call [edx+0x1F8]`." % PS_POWER)
        return 1

    hits = (reloc_hits(d, secs, CAVE, CAVE + CAVE_SPAN)
            + reloc_hits(d, secs, HOOK_CALL, HOOK_CALL + 5)
            + reloc_hits(d, secs, HALVE_BYTE, HALVE_BYTE + 1))
    if hits:
        print("ABORT: .reloc entries inside the cave or a written window: %s"
              % ["%08X" % h for h in hits])
        return 1

    tail = rd(CAVE + CAVE_SPAN, ZONE_END - CAVE - CAVE_SPAN)
    if set(tail) != {0}:
        print("ABORT: reservation %08X..%08X is not zero." % (CAVE + CAVE_SPAN, ZONE_END))
        return 1

    # ---- patch table --------------------------------------------------------------------
    patches = [
        (HOOK_CALL, HOOK_OLD, HOOK_NEW, "GetNetPower opening call -> cave_powerleech"),
        (HALVE_BYTE, HALVE_OLD, HALVE_NEW, "kill the vanilla halving (test ...,8 -> ,0)"),
        (CAVE, ZERO_REGION, CAVE_REGION, "cave_powerleech @ %08X" % CAVE),
    ]

    ok = True
    already = todo = pristine = 0
    for va, old, new, desc in patches:
        target, other = (old, new) if undo else (new, old)
        cur = rd(va, len(new))
        if cur == target:
            already += 1
            if undo:
                pristine += 1
        elif cur == other:
            todo += 1
            if not undo:
                pristine += 1
        else:
            print("MISMATCH %s @ %08X:\n  pre-feature %s\n  patched     %s\n  found       %s"
                  % (desc, va, old[:24].hex(" "), new[:24].hex(" "), cur[:24].hex(" ")))
            ok = False
    verb = "undone" if undo else "applied"
    print("%d already %s, %d to change, %d total" % (already, verb, todo, len(patches)))
    if not ok:
        print("ABORT: byte mismatch (different/partial patch state).")
        return 1
    if "--apply" not in argv:
        print("\nDry run OK. Re-run with --apply to write, --undo --apply to remove.")
        return 0
    if todo == 0:
        print("Nothing to do.")
        return 0

    kill_running()

    # Backup ONLY from a file PROVED to be in the pre-feature state -- never on --undo (the
    # current file IS the patched state by definition), never on a re-tune, and never merely
    # because no backup file exists. `pristine == len(patches)` is the positive test.
    if not undo and pristine == len(patches):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        if not os.path.exists(BACKUP):
            shutil.copyfile(DLL, BACKUP)
            print("backup -> backups/%s" % os.path.basename(BACKUP))
        else:
            print("backup already exists, left alone")
    elif not undo:
        print("(no backup: file is not in the pre-feature state; --undo is the revert path)")

    for va, old, new, _desc in patches:
        o = va2off(secs, va)
        blob = old if undo else new
        d[o:o + len(blob)] = blob
        print("  wrote %08X  %d byte(s)" % (va, len(blob)))
    open(DLL, "wb").write(bytes(d))
    print("sha-256 %s" % hashlib.sha256(bytes(d)).hexdigest())
    print("undone." if undo else "applied, UNTESTED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
