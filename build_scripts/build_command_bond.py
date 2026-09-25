#!/usr/bin/env python
r"""
build_command_bond.py -- control by Seduce / Charm / Dominate (and evil Turn Undead) lasts only
while the commander does; commanders pay 1 Resistance per unit they hold; Dispel Magic can wrest a
bound unit away.  AoWEPACK.dpl.  Owner's design 2026-09-25 (Zig notes/02-abilities-modded.md,
"Command abilities -- limiting permanent control": ideas A, B, E).

TWO NEW ABILITIES, registered at package init (⚠ prove by launching the exe)
    0xBB  Bound       a TCommandedAbility instance (the Seduced/Charmed/Dominated class), mask 0.
                      Its TCommandedAbilityData record, already saved by ReadWrite @0x5576FA8C,
                      holds [+0x14] the master's unit id (unit+0x18) and [+0x10] the master's
                      Resistance when the bond was made.  A separate status, not the vanilla
                      three: re-seizing a bound unit strips the vanilla status (TCommandCA.Execute
                      loop 2 -> Uncommand), so reusing them would launder a bond whenever a
                      re-seizure is reverted in the same battle.
    0xBC  Commanding  a TMultiLevelAbility instance, mask 0.  Level (data [+0xC]) = the number of
                      live units bound to this unit; Resistance -1 per level.
    Spliced at the last direct `call RegisterAbility` in PassiveAb.RegisterPassiveAbilities,
    0x557BCDAF (EBX = the ability control there).  Record ids 197/198: build_command_bond_pfs.py.
    Ceilings: LADDER 0xBD in build_abilityid_ceilings.py and build_tcablist_ceiling.py.

A  BOND
    CD 0x5576FB4C  TCommandedAbility.CombatDone -> c_cdone (whole function).  Bound itself: kept.
                   A vanilla commanded status on a unit still alive at Finalize: resolve the
                   commander (TCombatData.FindID on data [+0x10], a TCombatUnit, not destroyed),
                   bind the unit to it (master id + master's strategic RES), then the vanilla
                   Remove.  Finalize calls CombatDone on every object before its settlement passes.
    CO 0x5576FB6C  TCommandedAbility.CombatObjectDestroyed -> c_cod: skip for Bound (its [+0x14] is
                   a unit id, not the controller ability id vanilla reads there).
    TN 0x5578F7BE  TArmy.NewTurn's `call UpdateDesertion` -> c_turn.  At the owner's turn start:
                   recount every Commanding unit in the army (scan of TUnitControl[+0x10]); strip
                   the bond of each unit whose master is gone, killed (unit+0x25 bit 0x10) or
                   owned by someone else (so disbanding a commander, which makes it independent,
                   frees its thralls); if any, TArmy.Desert(army, mask) under a BSS flag, and no
                   ordinary desertion roll that turn.  Independent armies are stripped silently.
    DM 0x5578F3F8  TArmy.Desert's `call DistributeLocationEventLog` -> c_dmsg: with the flag set,
                   the flag is cleared and the reason text ([log+0x20], a TStringList) is replaced
                   through TStrings.SetTextStr, VMT +0x2C -- Desert's own call -- with the bond text,
                   singular or plural on Desert's own count [ebp-0x14].  ⚠ v1 (2026-09-25) called
                   +0x38 believing it Clear; it is AddObject, and every revert raised "Exception
                   occured during TEndTurnTE" mid-Desert: bonds already stripped, units not moved,
                   the game-over lock (map+0x1C8, not saved) and the flag left set until restart.
    DT 0x55727591  TCombat.ObjectDestroyed's `call CheckTerminate` -> c_death.  Every combat mode
                   reaches it (TCombat and TFastCombat VMT +0x50; AoWTCPCK's TTacticalCombat
                   thunks to it).  When a TCombatUnit dies, every live unit in the battle bound to
                   it changes side at once (SetCombatPlayer, CO VMT +0x68) to the opposing combat
                   player -- independents preferred.  Settlement follows the combat player
                   (TCombatUnit.Finalize), so the unit ends the battle with that side; if that side
                   is independent the bond is stripped, otherwise the next turn-start check frees it.

B  COMMANDING
    VR 0x5571E034  TMultiLevelAbility VMT +0x64 (GetResistance) -> c_res: -level for 0xBC.
    VL 0x5571E0DC  TMultiLevelAbility VMT +0x10C (GetLevelName) -> c_lname: "Commanding N".
                   Both cells carry .reloc entries, kept (the new value is inside this image).
                   Units cache RES at unit+0x46 (TUnit.Changed); every level change calls
                   Changed (owner VMT +0x90).  Level changes: +1 on each new bond, -1 on the old
                   master when a bond moves, and an absolute recount at the commander's turn start.

E  DISPEL MAGIC
    E1 0x5577F454  TAbstractUnit.CanDispelEnchantment epilogue -> c_cande.  Also a valid target: a
                   unit under a vanilla command status whose strategic owner is the dispeller's
                   player (seized from them this battle), or a unit with a current bond whose owner
                   is not.  Own control never makes a unit a target.  All four Dispel routes ask it.
    E2 0x5576CC18  TDispelMagicCA.Generate entry -> c_gen (battle, spell and ability).  Roll
                   HitRoleProbability(dispeller RES - controller RES) against TAoWHSMap.Random(100),
                   the generator Generate already uses; the controller's RES is the live commander's
                   (vanilla status) or the stored one (bond).  Success appends a sentinel to the CA's
                   id list [ca+0x10] (Execute's FindID ignores it; the list travels with the CA).
                   TDispelMagicAbility.CreateCA clears the list when its touch misses an enemy.
    E3 0x5576CB4C  TDispelMagicCA.Execute's `call TObject.Free` -> c_exec.  Sentinel FRESH:
                   the controller's Uncommand (back to its own side, any older bond intact).
                   Sentinel BOUND: SetCombatPlayer to the dispeller's combat player, rebind to the
                   dispeller.
    E4 0x557E8AE3  TDispelMagic.ExecuteSpell's `call ListEnchantments` -> c_mspell (world map).
    E5 0x5576D824  TDispelMagicAbilityTE.Execute's `test eax,eax / setg bl` -> c_tegate, so a
                   bound target with no enchantments still passes the ability's gate.
    E6 0x5576D84E  TDispelMagicAbilityTE.Execute's `call GetDispelMana` -> c_teflip (world map).
                   Map roll: caster's strategic RES vs the stored RES, synced Random(100) (both
                   hosts draw from it).  Success: the unit leaves for the caster's player the way
                   TDisbandUnitTE.Execute re-homes a unit (detach + TAbstractUnit.Place, or
                   TArmy.SetPlayer for a lone unit outside a player structure) and is rebound to
                   the caster.  The dispelled count shown to the caster includes it.

RNG: map draws are P1 SYNCED (TAoWHSMap.Random), exactly the generator every Dispel host function
already draws from; the battle draw sits in Generate, which draws from the same one.  No draw
anywhere in A or B.

Slot 0x5584E500-0x5584F200, exclusive.  BSS 0x558FAD20 (1 byte, the Desert text flag).  PIC:
rel32 calls, register-relative data through a call/pop delta helper.  Surgical --undo.

COUPLINGS: build_command_resroll.py (C) is independent.  CommandAbilityIDs is untouched; the
evil Turn Undead status 0x89 (build_turnundead_evilcommand.py) is one of the four vanilla-style
statuses handled here.  TArmy.NewTurn's entry belongs to build_drillmaster.py; this hook is the
later UpdateDesertion call.  TDispelMagicAbilityTE.Execute also carries
build_abilityte_itemgrant.py's call at 0x5576D7FC.

    python build_scripts/build_command_bond.py            dry run + state
    python build_scripts/build_command_bond.py --apply
    python build_scripts/build_command_bond.py --undo
    python build_scripts/build_command_bond.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584E500, 0x5584F200)
BOUND_ID, CMDING_ID = 0xBB, 0xBC
STATUS_IDS = (0x30, 0x95, 0x96, 0x89)          # Seduced, Charmed, Dominated, Commanded Undead
SENT_FRESH, SENT_BOUND = 0x7FFFFFF0, 0x7FFFFFF1
G_FLAG = 0x558FAD20

# ---- engine (verified against the live DLL 2026-09-25) ----
MAP_CELL, HSSET_CELL = 0x558FA040, 0x558FA044
CLS_COMBATUNIT, CLS_ARMY, CLS_PSTRUCT = 0x55715A54, 0x557130AC, 0x55714300
CLS_CMDED, CLS_MULTILEVEL = 0x557201D8, 0x5571DF90
GET_ABILITY, GET_ABDATA, ADD_ABDATA, REMOVE_ABDATA_ID = 0x557501C0, 0x5574F1C4, 0x5574F278, 0x5574F2B8
SETAB, REGISTER = 0x5574E718, 0x55750238
CMDED_CREATE, ML_CREATE, ML_GETLEVEL = 0x5576FADC, 0x55765168, 0x557651D8
TAB_GETRES, ML_GETLNAME = 0x5574E998, 0x55765230
FINDUNIT, FINDID, CD_COUNT, CD_GET = 0x5577E948, 0x55728C68, 0x55728BEC, 0x55728BF8
ISCLASS, GETSIDE, GETPLAYER, CPL_GET = 0x557010C0, 0x55726660, 0x557268E4, None
RANDOM, HITPROB = 0x5577827C, 0x55725DCC
INTLIST_ADD, INTLIST_GET, TOBJ_FREE = 0x55702E74, 0x55702E94, 0x557010B8
LSTRASG, INTTOSTR, LSTRCAT3, LSTRCLR = 0x55701150, 0x5570158C, 0x55701190, 0x55701140
DESERT, UPDDESERT, DISTRIB, CHECKTERM = 0x5578F0E0, 0x5578F680, 0x557FE558, 0x557274D8
GETLOC, GETFIELD, FINDNTHS, PLACE, ARMY_SETPLAYER = 0x5577ED94, 0x557020FC, 0x55702004, 0x557810FC, 0x5578D690
LISTENCH, GETDMANA_AB = 0x5577F45C, 0x5576CEA8

TXT_BOUND = b"Bound"
TXT_CMDING = b"Commanding"
TXT_PREFIX = b"Commanding "
TXT_ONE = b"With its master gone, this one breaks free of your control."
TXT_MANY = b"With their master gone, these break free of your control."


def cpl_get_addr():
    """TCombatPlayerList.GetPlayers -- the call inside TCombatObject.GetSide @0x55726660."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    d = open(P.TARGET, "rb").read()
    o = P.va2off(d, GETSIDE)
    for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(d[o:o + 0x28], GETSIDE):
        if i.mnemonic == "call":
            return int(i.op_str, 16)
    sys.exit("ABORT: TCombatPlayerList.GetPlayers not found inside GetSide")


CPL_GET = cpl_get_addr()


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def lit(s):
    """Delphi AnsiString literal (refcount -1); the string pointer is 8 bytes in."""
    return struct.pack("<iI", -1, len(s)) + s + b"\0"


# ---------------------------------------------------------------- sources
# S maps every cave / literal name to its VA; each builder takes (va, S).

def s_delta(va, S):
    return f"""
        call gd_l0
    gd_l0:
        pop eax
        sub eax, {va + 5:#x}
        ret
    """


def s_get_ability(va, S):
    return f"""
        push ebx
        mov ebx, eax
        call {S['h_delta']:#x}
        mov eax, dword ptr [eax + {HSSET_CELL:#x}]
        mov eax, dword ptr [eax + 0x80]
        mov edx, ebx
        call {GET_ABILITY:#x}
        pop ebx
        ret
    """


def s_find_unit(va, S):
    return f"""
        push ebx
        mov ebx, eax
        call {S['h_delta']:#x}
        mov eax, dword ptr [eax + {MAP_CELL:#x}]
        mov eax, dword ptr [eax + 0xFC]
        mov edx, ebx
        call {FINDUNIT:#x}
        pop ebx
        ret
    """


def s_is_cu(va, S):
    return f"""
        test eax, eax
        je iscu_no
        push ebx
        mov ebx, eax
        call {S['h_delta']:#x}
        mov edx, dword ptr [eax + {CLS_COMBATUNIT:#x}]
        mov eax, ebx
        call {ISCLASS:#x}
        pop ebx
        ret
    iscu_no:
        xor eax, eax
        ret
    """


def s_bond_data(va, S):
    return f"""
        test eax, eax
        je bd_z
        mov edx, {BOUND_ID:#x}
        jmp {GET_ABDATA:#x}
    bd_z:
        ret
    """


def s_bond_master(va, S):
    return f"""
        push ebx
        mov ebx, eax
        call {S['h_bond_data']:#x}
        test eax, eax
        je bm_z
        mov eax, dword ptr [eax + 0x14]
        call {S['h_find_unit']:#x}
        test eax, eax
        je bm_z
        test byte ptr [eax + 0x25], 0x10
        jne bm_z
        mov dl, byte ptr [eax + 0x24]
        cmp dl, byte ptr [ebx + 0x24]
        jne bm_z
        pop ebx
        ret
    bm_z:
        xor eax, eax
        pop ebx
        ret
    """


def s_fresh_data(va, S):
    body = ""
    for n, sid in enumerate(STATUS_IDS):
        body += f"""
        mov edx, {sid:#x}
        mov eax, ebx
        call {GET_ABDATA:#x}
        test eax, eax
        jne fd_done
    """
    return f"""
        push ebx
        mov ebx, eax
        test ebx, ebx
        je fd_z
        {body}
    fd_z:
        xor eax, eax
    fd_done:
        pop ebx
        ret
    """


def s_burden_get(va, S):
    return f"""
        test eax, eax
        je bg_z
        mov edx, {CMDING_ID:#x}
        call {GET_ABDATA:#x}
        test eax, eax
        je bg_z
        movzx eax, byte ptr [eax + 0xC]
        ret
    bg_z:
        xor eax, eax
        ret
    """


def s_burden_set(va, S):
    return f"""
        push ebx
        push esi
        push edi
        mov ebx, eax
        mov esi, edx
        test ebx, ebx
        je bs_out
        test esi, esi
        jge bs_a
        xor esi, esi
    bs_a:
        cmp esi, 0xFF
        jle bs_b
        mov esi, 0xFF
    bs_b:
        mov eax, {CMDING_ID:#x}
        call {S['h_get_ability']:#x}
        mov edi, eax
        test edi, edi
        je bs_out
        mov edx, {CMDING_ID:#x}
        mov eax, ebx
        call {GET_ABDATA:#x}
        test esi, esi
        jne bs_pos
        test eax, eax
        je bs_changed
        mov edx, {CMDING_ID:#x}
        mov eax, ebx
        call {REMOVE_ABDATA_ID:#x}
        push 0
        mov ecx, {CMDING_ID:#x}
        mov edx, ebx
        mov eax, edi
        call {SETAB:#x}
        jmp bs_changed
    bs_pos:
        test eax, eax
        jne bs_have
        mov eax, edi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x108]
        xor ecx, ecx
        mov dl, 1
        call dword ptr [eax + 0x20]
        mov word ptr [eax + 0xE], {CMDING_ID:#x}
        mov byte ptr [eax + 0xC], 0
        push eax
        mov edx, eax
        mov eax, ebx
        call {ADD_ABDATA:#x}
        push 1
        mov ecx, {CMDING_ID:#x}
        mov edx, ebx
        mov eax, edi
        call {SETAB:#x}
        pop eax
    bs_have:
        mov edx, esi
        mov byte ptr [eax + 0xC], dl
    bs_changed:
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x90]
    bs_out:
        pop edi
        pop esi
        pop ebx
        ret
    """


def s_burden_adj(va, S):
    return f"""
        test eax, eax
        je ba_r
        push ebx
        push esi
        mov ebx, eax
        mov esi, edx
        call {S['h_burden_get']:#x}
        add eax, esi
        mov edx, eax
        mov eax, ebx
        call {S['h_burden_set']:#x}
        pop esi
        pop ebx
    ba_r:
        ret
    """


def s_strip(va, S):
    return f"""
        test eax, eax
        je st_r
        push ebx
        mov ebx, eax
        mov eax, {BOUND_ID:#x}
        call {S['h_get_ability']:#x}
        test eax, eax
        je st_p
        mov edx, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0xD4]
    st_p:
        pop ebx
    st_r:
        ret
    """


def s_bind(va, S):
    return f"""
        push ebx
        push esi
        push edi
        push ebp
        mov ebx, eax
        mov esi, edx
        mov ebp, ecx
        test ebx, ebx
        je bi_out
        test esi, esi
        je bi_out
        test ebp, ebp
        jge bi_r1
        xor ebp, ebp
    bi_r1:
        cmp ebp, 0xFF
        jle bi_r2
        mov ebp, 0xFF
    bi_r2:
        mov eax, ebx
        call {S['h_bond_data']:#x}
        mov edi, eax
        test edi, edi
        jne bi_have
        mov eax, {BOUND_ID:#x}
        call {S['h_get_ability']:#x}
        test eax, eax
        je bi_out
        push eax
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x108]
        xor ecx, ecx
        mov dl, 1
        call dword ptr [eax + 0x20]
        mov edi, eax
        mov dword ptr [edi + 0xC], {BOUND_ID:#x}
        mov dword ptr [edi + 0x14], 0
        mov byte ptr [edi + 0x10], 0
        mov byte ptr [edi + 0x18], 0
        mov edx, edi
        mov eax, ebx
        call {ADD_ABDATA:#x}
        pop eax
        push 1
        mov ecx, {BOUND_ID:#x}
        mov edx, ebx
        call {SETAB:#x}
        jmp bi_newm
    bi_have:
        mov eax, dword ptr [edi + 0x14]
        cmp eax, dword ptr [esi + 0x18]
        je bi_setf
        call {S['h_find_unit']:#x}
        mov edx, -1
        call {S['h_burden_adj']:#x}
    bi_newm:
        mov eax, esi
        mov edx, 1
        call {S['h_burden_adj']:#x}
    bi_setf:
        mov eax, dword ptr [esi + 0x18]
        mov dword ptr [edi + 0x14], eax
        mov eax, ebp
        mov byte ptr [edi + 0x10], al
    bi_out:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """


def s_chance(va, S):
    return f"""
        call {HITPROB:#x}
        push 0x64
        fimul dword ptr [esp]
        fistp dword ptr [esp]
        pop eax
        ret
    """


def s_rand100(va, S):
    return f"""
        call {S['h_delta']:#x}
        mov eax, dword ptr [eax + {MAP_CELL:#x}]
        mov edx, 0x64
        jmp {RANDOM:#x}
    """


def s_count_thralls(va, S):
    return f"""
        push ebx
        push esi
        push edi
        push ebp
        mov ebx, eax
        xor ebp, ebp
        call {S['h_delta']:#x}
        mov eax, dword ptr [eax + {MAP_CELL:#x}]
        mov eax, dword ptr [eax + 0xFC]
        mov eax, dword ptr [eax + 0x10]
        mov esi, dword ptr [eax + 4]
        mov edi, dword ptr [eax + 8]
    ct_lp:
        dec edi
        js ct_done
        mov eax, dword ptr [esi + edi*4]
        cmp eax, ebx
        je ct_lp
        test byte ptr [eax + 0x25], 0x10
        jne ct_lp
        mov dl, byte ptr [eax + 0x24]
        cmp dl, byte ptr [ebx + 0x24]
        jne ct_lp
        call {S['h_bond_data']:#x}
        test eax, eax
        je ct_lp
        mov ecx, dword ptr [eax + 0x14]
        cmp ecx, dword ptr [ebx + 0x18]
        jne ct_lp
        inc ebp
        jmp ct_lp
    ct_done:
        mov eax, ebp
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """


def s_ctv(va, S):
    return f"""
        push ebx
        push esi
        mov ebx, eax
        mov esi, edx
        test ebx, ebx
        je cv_no
        mov eax, ebx
        call {S['h_fresh_data']:#x}
        test eax, eax
        je cv_nf
        mov eax, esi
        cmp al, byte ptr [ebx + 0x24]
        sete al
        jmp cv_done
    cv_nf:
        mov eax, ebx
        call {S['h_bond_master']:#x}
        test eax, eax
        je cv_no
        mov eax, esi
        cmp al, byte ptr [ebx + 0x24]
        setne al
        jmp cv_done
    cv_no:
        xor eax, eax
    cv_done:
        pop esi
        pop ebx
        ret
    """


def s_pick(va, S):
    """EAX = the dead master's combat object, EDX = the thrall's -> EAX = a combat-player index on
    the side AWAY from the master (-1 if none, or the thrall already stands there), EDX = its
    strategic player.  Independents preferred."""
    return f"""
        push ebx
        push esi
        push edi
        push ebp
        mov edi, eax
        mov esi, edx
        call {GETSIDE:#x}
        cmp al, 2
        jae pk_none
        xor al, 1
        movzx ebp, al
        mov eax, esi
        call {GETSIDE:#x}
        movzx eax, al
        cmp eax, ebp
        je pk_none
        mov esi, dword ptr [edi + 8]
        mov esi, dword ptr [esi + 0xC]
        mov esi, dword ptr [esi + 0x38]
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov ebx, eax
        mov edi, -1
        push -1
    pk_lp:
        dec ebx
        js pk_end
        mov edx, ebx
        mov eax, esi
        call {CPL_GET:#x}
        test eax, eax
        je pk_lp
        movzx ecx, byte ptr [eax + 0xA]
        cmp ecx, ebp
        jne pk_lp
        movsx ecx, byte ptr [eax + 8]
        cmp edi, -1
        jne pk_c0
        mov edi, ebx
        mov dword ptr [esp], ecx
    pk_c0:
        test ecx, ecx
        jne pk_lp
        mov edi, ebx
        mov dword ptr [esp], ecx
    pk_end:
        pop edx
        mov eax, edi
        jmp pk_done
    pk_none:
        mov eax, -1
        xor edx, edx
    pk_done:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """


def s_transfer(va, S):
    """EAX = unit, DL = new owner -> AL success.  TDisbandUnitTE.Execute's re-homing, for a player."""
    return f"""
        push ebx
        push esi
        push edi
        push ebp
        sub esp, 8
        mov ebx, eax
        movzx ebp, dl
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x28]
        lea eax, [esp + 2]
        push eax
        lea ecx, [esp + 5]
        lea edx, [esp + 4]
        mov eax, ebx
        call {GETLOC:#x}
        call {S['h_delta']:#x}
        mov esi, dword ptr [eax + {MAP_CELL:#x}]
        mov esi, dword ptr [esi + 0x10]
        movsx eax, byte ptr [esp + 2]
        push eax
        movsx ecx, byte ptr [esp + 5]
        movsx edx, byte ptr [esp + 4]
        mov eax, esi
        call {GETFIELD:#x}
        mov esi, eax
        xor edi, edi
        test esi, esi
        je tr_nos
        call {S['h_delta']:#x}
        mov edx, dword ptr [eax + {CLS_PSTRUCT:#x}]
        mov eax, esi
        call {FINDNTHS:#x}
        mov edi, eax
    tr_nos:
        mov esi, dword ptr [ebx + 4]
        call {S['h_delta']:#x}
        mov edx, dword ptr [eax + {CLS_ARMY:#x}]
        mov eax, esi
        call {ISCLASS:#x}
        test al, al
        je tr_place
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        dec eax
        jg tr_place
        test edi, edi
        je tr_whole
        cmp byte ptr [edi + 0x30], 0
        jg tr_place
    tr_whole:
        mov edx, ebp
        mov eax, esi
        call {ARMY_SETPLAYER:#x}
        mov al, 1
        jmp tr_fin
    tr_place:
        mov eax, ebx
        xor edx, edx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 8]
        movsx eax, byte ptr [esp + 2]
        push eax
        push ebp
        push 1
        movsx ecx, byte ptr [esp + 0xD]
        movsx edx, byte ptr [esp + 0xC]
        mov eax, ebx
        call {PLACE:#x}
        test eax, eax
        setne al
    tr_fin:
        push eax
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x2C]
        pop eax
        add esp, 8
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """


def s_map_dispel(va, S):
    return f"""
        push ebx
        push esi
        push edi
        push ebp
        mov ebx, eax
        mov esi, edx
        test ebx, ebx
        je md_no
        test esi, esi
        je md_no
        mov eax, ebx
        call {S['h_bond_master']:#x}
        test eax, eax
        je md_no
        mov al, byte ptr [ebx + 0x24]
        cmp al, byte ptr [esi + 0x24]
        je md_no
        mov eax, ebx
        call {S['h_bond_data']:#x}
        movzx edi, byte ptr [eax + 0x10]
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0xCC]
        movsx ebp, al
        mov eax, ebp
        sub eax, edi
        call {S['h_chance']:#x}
        mov edi, eax
        call {S['h_rand100']:#x}
        cmp eax, edi
        jge md_no
        mov dl, byte ptr [esi + 0x24]
        mov eax, ebx
        call {S['h_transfer']:#x}
        test al, al
        je md_no
        mov ecx, ebp
        mov edx, esi
        mov eax, ebx
        call {S['h_bind']:#x}
        mov al, 1
        jmp md_done
    md_no:
        xor eax, eax
    md_done:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """


# ---- hosts ----

def s_reg(va, S):
    return f"""
        call {REGISTER:#x}
        push esi
        push edi
        call {S['h_delta']:#x}
        mov esi, eax
        mov eax, dword ptr [esi + {CLS_CMDED:#x}]
        xor ecx, ecx
        mov dl, 1
        call {CMDED_CREATE:#x}
        mov edi, eax
        mov dword ptr [edi + 0xC], {BOUND_ID:#x}
        mov word ptr [edi + 0x20], 0
        lea eax, [edi + 8]
        lea edx, [esi + {S['lit_bound']:#x}]
        call {LSTRASG:#x}
        mov edx, edi
        mov eax, ebx
        call {REGISTER:#x}
        mov eax, dword ptr [esi + {CLS_MULTILEVEL:#x}]
        xor ecx, ecx
        mov dl, 1
        call {ML_CREATE:#x}
        mov edi, eax
        mov dword ptr [edi + 0xC], {CMDING_ID:#x}
        mov word ptr [edi + 0x20], 0
        lea eax, [edi + 8]
        lea edx, [esi + {S['lit_cmding']:#x}]
        call {LSTRASG:#x}
        mov edx, edi
        mov eax, ebx
        call {REGISTER:#x}
        pop edi
        pop esi
        ret
    """


def s_res(va, S):
    return f"""
        cmp dword ptr [eax + 0xC], {CMDING_ID:#x}
        jne rs_orig
        call {ML_GETLEVEL:#x}
        movzx eax, al
        cmp eax, 0x7F
        jbe rs_k
        mov eax, 0x7F
    rs_k:
        neg eax
        ret
    rs_orig:
        jmp {TAB_GETRES:#x}
    """


def s_lname(va, S):
    """Level 0 gives the plain name, as TVisionAbility.GetLevelName does: the exe's ability card
    (0x40AB87 and six siblings -> 0x40701C) asks GetName with a NIL owner, so its level reads 0."""
    return f"""
        cmp dword ptr [eax + 0xC], {CMDING_ID:#x}
        jne ln_orig
        test edx, edx
        jne ln_num
        push ecx
        call {S['h_delta']:#x}
        lea edx, [eax + {S['lit_cmding']:#x}]
        pop eax
        jmp {LSTRASG:#x}
    ln_num:
        push ebp
        mov ebp, esp
        push 0
        push ebx
        push esi
        mov esi, ecx
        mov ebx, edx
        lea edx, [ebp - 4]
        mov eax, ebx
        call {INTTOSTR:#x}
        call {S['h_delta']:#x}
        lea edx, [eax + {S['lit_prefix']:#x}]
        mov ecx, dword ptr [ebp - 4]
        mov eax, esi
        call {LSTRCAT3:#x}
        lea eax, [ebp - 4]
        call {LSTRCLR:#x}
        pop esi
        pop ebx
        pop ecx
        pop ebp
        ret
    ln_orig:
        jmp {ML_GETLNAME:#x}
    """


def s_cdone(va, S):
    return f"""
        cmp dword ptr [eax + 0xC], {BOUND_ID:#x}
        jne cdn_go
        ret
    cdn_go:
        push ebx
        push esi
        push edi
        push ebp
        mov ebx, eax
        mov esi, edx
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0xB8]
        mov edi, eax
        test edi, edi
        je cdn_rem
        test byte ptr [esi + 0x47], 1
        jne cdn_rem
        mov edx, dword ptr [ebx + 0xC]
        mov eax, edi
        call {GET_ABDATA:#x}
        test eax, eax
        je cdn_rem
        movzx edx, byte ptr [eax + 0x10]
        mov eax, dword ptr [esi + 8]
        mov eax, dword ptr [eax + 0xC]
        call {FINDID:#x}
        test eax, eax
        je cdn_rem
        mov ebp, eax
        test byte ptr [ebp + 0x47], 1
        jne cdn_rem
        mov eax, ebp
        call {S['h_is_cu']:#x}
        test al, al
        je cdn_rem
        mov ebp, dword ptr [ebp + 0x4C]
        test ebp, ebp
        je cdn_rem
        mov eax, ebp
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0xCC]
        movsx ecx, al
        mov edx, ebp
        mov eax, edi
        call {S['h_bind']:#x}
    cdn_rem:
        mov edx, edi
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0xD4]
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """


def s_cod(va, S):
    return f"""
        cmp dword ptr [eax + 0xC], {BOUND_ID:#x}
        jne cod_go
        ret
    cod_go:
        push ebx
        push esi
        mov esi, edx
        mov ebx, eax
        jmp 0x5576FB72
    """


def s_death(va, S):
    return f"""
        pushal
        mov eax, edi
        call {S['h_is_cu']:#x}
        test al, al
        je dth_out
        mov eax, dword ptr [edi + 0x4C]
        test eax, eax
        je dth_out
        mov ebp, dword ptr [eax + 0x18]
        mov esi, dword ptr [esi + 0xC]
        mov eax, esi
        call {CD_COUNT:#x}
        mov ebx, eax
    dth_lp:
        dec ebx
        js dth_out
        mov edx, ebx
        mov eax, esi
        call {CD_GET:#x}
        mov edi, eax
        test byte ptr [edi + 0x47], 1
        jne dth_lp
        mov eax, edi
        call {S['h_is_cu']:#x}
        test al, al
        je dth_lp
        mov eax, dword ptr [edi + 0x4C]
        call {S['h_bond_data']:#x}
        test eax, eax
        je dth_lp
        cmp dword ptr [eax + 0x14], ebp
        jne dth_lp
        mov edx, edi
        mov eax, dword ptr [esp]
        call {S['h_pick']:#x}
        cmp eax, -1
        je dth_lp
        push edx
        mov edx, eax
        mov eax, edi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x68]
        pop edx
        test dl, dl
        jne dth_lp
        mov eax, dword ptr [edi + 0x4C]
        call {S['h_strip']:#x}
        jmp dth_lp
    dth_out:
        popal
        jmp {CHECKTERM:#x}
    """


def s_turn(va, S):
    return f"""
        push ebx
        push esi
        push edi
        push ebp
        mov ebx, eax
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov edi, eax
        mov esi, dword ptr [ebx + 8]
        mov esi, dword ptr [esi + 4]
    tn_r1:
        dec edi
        js tn_r1d
        mov eax, dword ptr [esi + edi*4]
        push eax
        mov edx, {CMDING_ID:#x}
        call {GET_ABDATA:#x}
        pop ecx
        test eax, eax
        je tn_r1
        push ecx
        mov eax, ecx
        call {S['h_count_thralls']:#x}
        pop ecx
        mov edx, eax
        mov eax, ecx
        call {S['h_burden_set']:#x}
        jmp tn_r1
    tn_r1d:
        xor ebp, ebp
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov edi, eax
    tn_r2:
        dec edi
        js tn_r2d
        mov eax, dword ptr [esi + edi*4]
        push eax
        call {S['h_bond_data']:#x}
        pop ecx
        test eax, eax
        je tn_r2
        mov eax, ecx
        call {S['h_bond_master']:#x}
        test eax, eax
        jne tn_r2
        bts ebp, edi
        jmp tn_r2
    tn_r2d:
        test ebp, ebp
        je tn_tail
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov edi, eax
    tn_r3:
        dec edi
        js tn_r3d
        bt ebp, edi
        jae tn_r3
        mov eax, dword ptr [esi + edi*4]
        call {S['h_strip']:#x}
        jmp tn_r3
    tn_r3d:
        cmp byte ptr [ebx + 0x12], 0
        je tn_quiet
        call {S['h_delta']:#x}
        mov byte ptr [eax + {G_FLAG:#x}], 1
        mov edx, ebp
        mov eax, ebx
        call {DESERT:#x}
        call {S['h_delta']:#x}
        mov byte ptr [eax + {G_FLAG:#x}], 0
    tn_quiet:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    tn_tail:
        mov eax, ebx
        pop ebp
        pop edi
        pop esi
        pop ebx
        jmp {UPDDESERT:#x}
    """


def s_dmsg(va, S):
    """The flag is consumed here, so an exception further on in Desert cannot leave it set.
    TStrings.SetTextStr (VMT +0x2C) replaces the whole text -- the very call Desert used to put
    the vanilla reason there.  ⚠ +0x38 is AddObject, not Clear (VCL30 TStringList VMT, read
    2026-09-25: +0x34 Add, +0x40 Clear); v1 called it with a VMT pointer for a string and raised
    "Exception occured during TEndTurnTE"."""
    return f"""
        push eax
        push edx
        push ecx
        call {S['h_delta']:#x}
        cmp byte ptr [eax + {G_FLAG:#x}], 0
        je dm_skip
        mov byte ptr [eax + {G_FLAG:#x}], 0
        lea edx, [eax + {S['lit_one']:#x}]
        cmp dword ptr [ebp - 0x14], 1
        je dm_one
        lea edx, [eax + {S['lit_many']:#x}]
    dm_one:
        mov eax, dword ptr [ebx + 0x20]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x2C]
    dm_skip:
        pop ecx
        pop edx
        pop eax
        jmp {DISTRIB:#x}
    """


def s_cande(va, S):
    return f"""
        test al, al
        jne ce_out
        movzx edx, bl
        mov eax, edi
        call {S['h_ctv']:#x}
    ce_out:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """


def s_gen(va, S):
    return f"""
        pushal
        mov esi, eax
        mov edi, edx
        mov ebx, ecx
        mov eax, edi
        call {S['h_is_cu']:#x}
        test al, al
        je gn_out
        mov eax, ebx
        call {S['h_is_cu']:#x}
        test al, al
        je gn_out
        mov eax, edi
        call {GETPLAYER:#x}
        movzx ebp, al
        mov eax, dword ptr [ebx + 0x4C]
        test eax, eax
        je gn_out
        call {S['h_fresh_data']:#x}
        test eax, eax
        je gn_nf
        mov ecx, dword ptr [ebx + 0x4C]
        mov edx, ebp
        cmp dl, byte ptr [ecx + 0x24]
        jne gn_out
        movzx edx, byte ptr [eax + 0x10]
        mov eax, dword ptr [ebx + 8]
        mov eax, dword ptr [eax + 0xC]
        call {FINDID:#x}
        test eax, eax
        je gn_out
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        push {SENT_FRESH:#x}
        jmp gn_roll
    gn_nf:
        mov eax, dword ptr [ebx + 0x4C]
        call {S['h_bond_master']:#x}
        test eax, eax
        je gn_out
        mov ecx, dword ptr [ebx + 0x4C]
        mov edx, ebp
        cmp dl, byte ptr [ecx + 0x24]
        je gn_out
        mov eax, ecx
        call {S['h_bond_data']:#x}
        movzx eax, byte ptr [eax + 0x10]
        push {SENT_BOUND:#x}
    gn_roll:
        push eax
        mov eax, edi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        pop edx
        sub eax, edx
        call {S['h_chance']:#x}
        push eax
        call {S['h_rand100']:#x}
        pop edx
        cmp eax, edx
        pop edx
        jge gn_out
        mov eax, dword ptr [esi + 0x10]
        call {INTLIST_ADD:#x}
    gn_out:
        popal
        push ebp
        mov ebp, esp
        push ecx
        push ebx
        jmp 0x5576CC1D
    """


def s_exec(va, S):
    return f"""
        call {TOBJ_FREE:#x}
        pushal
        mov ebp, dword ptr [esp + 0x28]
        mov eax, dword ptr [esi + 0x10]
        mov ebx, dword ptr [eax + 8]
        push 0
    ex_lp:
        dec ebx
        js ex_lpd
        mov edx, ebx
        mov eax, dword ptr [esi + 0x10]
        call {INTLIST_GET:#x}
        cmp eax, {SENT_FRESH:#x}
        jne ex_n1
        mov dword ptr [esp], 1
        jmp ex_lp
    ex_n1:
        cmp eax, {SENT_BOUND:#x}
        jne ex_lp
        mov dword ptr [esp], 2
        jmp ex_lp
    ex_lpd:
        pop eax
        cmp eax, 1
        je ex_fresh
        cmp eax, 2
        je ex_bound
        jmp ex_out
    ex_fresh:
        mov eax, dword ptr [edi + 0x4C]
        call {S['h_fresh_data']:#x}
        test eax, eax
        je ex_out
        mov eax, dword ptr [eax + 0x14]
        call {S['h_get_ability']:#x}
        test eax, eax
        je ex_out
        mov edx, edi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x130]
        jmp ex_out
    ex_bound:
        movsx edx, byte ptr [ebp + 0x45]
        mov eax, edi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x68]
        mov eax, ebp
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx ecx, al
        mov edx, dword ptr [ebp + 0x4C]
        mov eax, dword ptr [edi + 0x4C]
        call {S['h_bind']:#x}
    ex_out:
        popal
        ret
    """


def s_mspell(va, S):
    return f"""
        push eax
        call {LISTENCH:#x}
        pop eax
        pushal
        mov edx, dword ptr [ebp - 8]
        call {S['h_map_dispel']:#x}
        test al, al
        je ms_o
        inc dword ptr [ebp - 0xC]
    ms_o:
        popal
        ret
    """


def s_tegate(va, S):
    return f"""
        test eax, eax
        setg bl
        jg tg_r
        push eax
        push ecx
        push edx
        mov eax, dword ptr [ebp - 0x18]
        movzx edx, byte ptr [eax + 0x24]
        mov eax, dword ptr [ebp - 0x1C]
        call {S['h_ctv']:#x}
        mov bl, al
        pop edx
        pop ecx
        pop eax
    tg_r:
        ret
    """


def s_teflip(va, S):
    return f"""
        call {GETDMANA_AB:#x}
        push eax
        push ecx
        push edx
        mov eax, dword ptr [ebp - 0x1C]
        mov edx, dword ptr [ebp - 0x18]
        call {S['h_map_dispel']:#x}
        test al, al
        je tf_o
        inc dword ptr [ebp - 8]
    tf_o:
        pop edx
        pop ecx
        pop eax
        ret
    """


CODE = [("h_delta", s_delta), ("h_get_ability", s_get_ability), ("h_find_unit", s_find_unit),
        ("h_is_cu", s_is_cu), ("h_bond_data", s_bond_data), ("h_bond_master", s_bond_master),
        ("h_fresh_data", s_fresh_data), ("h_burden_get", s_burden_get),
        ("h_burden_set", s_burden_set), ("h_burden_adj", s_burden_adj), ("h_strip", s_strip),
        ("h_bind", s_bind), ("h_chance", s_chance), ("h_rand100", s_rand100),
        ("h_count_thralls", s_count_thralls), ("h_ctv", s_ctv), ("h_pick", s_pick),
        ("h_transfer", s_transfer), ("h_map_dispel", s_map_dispel),
        ("c_reg", s_reg), ("c_res", s_res), ("c_lname", s_lname), ("c_cdone", s_cdone),
        ("c_cod", s_cod), ("c_death", s_death), ("c_turn", s_turn), ("c_dmsg", s_dmsg),
        ("c_cande", s_cande), ("c_gen", s_gen), ("c_exec", s_exec), ("c_mspell", s_mspell),
        ("c_tegate", s_tegate), ("c_teflip", s_teflip)]
LITS = [("lit_bound", TXT_BOUND), ("lit_cmding", TXT_CMDING), ("lit_prefix", TXT_PREFIX),
        ("lit_one", TXT_ONE), ("lit_many", TXT_MANY)]


def layout():
    """Two passes: sizes from placeholder addresses, then the real ones; sizes must agree."""
    S = {n: SLOT[0] for n, _f in CODE}
    S.update({n: SLOT[0] for n, _t in LITS})
    for _pass in range(3):
        va, caves, newS = SLOT[0], [], {}
        for name, fn in CODE:
            blob = asm(fn(va, S), va)
            caves.append((name, va, blob))
            newS[name] = va
            va = (va + len(blob) + 0xF) & ~0xF
        for name, t in LITS:
            blob = lit(t)
            caves.append((name, va, blob))
            newS[name] = va + 8                      # the character pointer
            va = (va + len(blob) + 0xF) & ~0xF
        if newS == S:
            break
        S = newS
    else:
        sys.exit("ABORT: cave layout did not converge")
    assert va <= SLOT[1], "caves overflow the slot: end %08X" % va
    d = caves[0][2]
    assert d[:5] == b"\xE8\x00\x00\x00\x00", "h_delta anchor did not assemble as call $+5"
    return S, caves


def check_ids():
    """Neither id may already be registered.  Sources that structurally cannot contain our own
    registration drive the abort: exported ability constructors, and every other cave's
    `mov dword [reg+0xC], id` / `mov eax, id` idiom outside our slot."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "re_tools"))
    import ability_names
    ctor = dict(ability_names._from_constructors())                  # noqa: SLF001
    for i in (BOUND_ID, CMDING_ID):
        if i in ctor:
            sys.exit("ABORT: ability %#x is registered by %s" % (i, ctor[i]))
    d = open(P.TARGET, "rb").read()
    lo, hi = 0x5580B000, 0x558E7900
    olo, ohi = P.va2off(d, lo), P.va2off(d, hi)
    mine = (P.va2off(d, SLOT[0]), P.va2off(d, SLOT[1]))
    for i in (BOUND_ID, CMDING_ID):
        for pat in (b"\xB8" + struct.pack("<I", i), b"\x0C" + struct.pack("<I", i)):
            k = d.find(pat, olo, ohi)
            while k >= 0:
                if not mine[0] <= k < mine[1]:
                    sys.exit("ABORT: id %#x appears in another cave at file offset %#x" % (i, k))
                k = d.find(pat, k + 1, ohi)
    print("  ids %#x / %#x free" % (BOUND_ID, CMDING_ID))


S, caves = layout()
hooks = [
    (0x557BCDAF, call_to(0x557BCDAF, REGISTER), call_to(0x557BCDAF, S["c_reg"])),
    (0x5576FB4C, bytes.fromhex("53568bf28b"), jmp_to(0x5576FB4C, S["c_cdone"], 5)),
    (0x5576FB6C, bytes.fromhex("53568bf28bd8"), jmp_to(0x5576FB6C, S["c_cod"], 6)),
    (0x55727591, call_to(0x55727591, CHECKTERM), call_to(0x55727591, S["c_death"])),
    (0x5578F7BE, call_to(0x5578F7BE, UPDDESERT), call_to(0x5578F7BE, S["c_turn"])),
    (0x5578F3F8, call_to(0x5578F3F8, DISTRIB), call_to(0x5578F3F8, S["c_dmsg"])),
    (0x5571E034, struct.pack("<I", TAB_GETRES), struct.pack("<I", S["c_res"])),
    (0x5571E0DC, struct.pack("<I", ML_GETLNAME), struct.pack("<I", S["c_lname"])),
    (0x5577F454, bytes.fromhex("5d5f5e5bc3"), jmp_to(0x5577F454, S["c_cande"], 5)),
    (0x5576CC18, bytes.fromhex("558bec5153"), jmp_to(0x5576CC18, S["c_gen"], 5)),
    (0x5576CB4C, call_to(0x5576CB4C, TOBJ_FREE), call_to(0x5576CB4C, S["c_exec"])),
    (0x557E8AE3, call_to(0x557E8AE3, LISTENCH), call_to(0x557E8AE3, S["c_mspell"])),
    (0x5576D824, bytes.fromhex("85c00f9fc3"), call_to(0x5576D824, S["c_tegate"])),
    (0x5576D84E, call_to(0x5576D84E, GETDMANA_AB), call_to(0x5576D84E, S["c_teflip"])),
]
interior = [(0x5576FB4C, 0x5576FB51, 0x5576FB4C, 0x5576FB6C),
            (0x5576FB6C, 0x5576FB72, 0x5576FB6C, 0x5576FBAA),
            (0x5577F454, 0x5577F459, 0x5577F40C, 0x5577F459),
            (0x5576CC18, 0x5576CC1D, 0x5576CC18, 0x5576CCE0),
            (0x5576D824, 0x5576D829, 0x5576D744, 0x5576DA38)]

if __name__ == "__main__":
    check_ids()
    run("build_command_bond", hooks, caves, SLOT, interior, reloc_ok=(0x5571E034, 0x5571E0DC))
