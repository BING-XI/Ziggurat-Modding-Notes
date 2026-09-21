#!/usr/bin/env python3
r"""
build_combatdiag.py -- DIAGNOSTIC ONLY. Logs every combat create/destroy and every raze to a FILE.

WHY A FILE. The bug under investigation FREEZES the game (sound running, no input), so anything that
reports through the UI -- the combat-log window, the ring buffer, a popup -- is unreadable exactly
when it matters: the window never repaints and the drain pump never ticks. `razediag.log` is opened,
appended and CLOSED per line, so every record written before the freeze is already on disk and
survives killing AoW.exe.

WHAT IT ANSWERS. The open question is whether `TAoWHSMap.CreateCombat @0x55778714` is raising
"Combat already created" -- it raises whenever `map[+0x120] != 0` -- because a raze battle created a
combat and never destroyed it. That would explain "Exception occured during TArmyCombatMoveTE",
both stacks vanishing, and the freeze. This patch logs `map[+0x120]` AS SEEN AT ENTRY to every
CreateCombat, plus every DestroyCombat and every TStructure.Raze, each with its caller.

READING THE LOG. One record per line, all values hex, addresses normalised to LINK TIME (runtime
minus load delta) so they can be compared directly against Ghidra//the build scripts:

    CCRE <flag> <map[+0x120] at entry> <caller>
    CDES <map[+0x120] at entry> 00000000 <caller>
    RAZE <player> <structure VMT> <caller>

  * flag 000202B0 = fast combat, 00220110 = tactical/modal.
  * THE SMOKING GUN IS ANY `CCRE` LINE WHOSE SECOND FIELD IS NON-ZERO -- that call is the one that
    raises. Whoever created that stuck combat is the previous CCRE with no matching CDES.
  * caller 5580Cxxx = our cave_towerraze; 55749A8A/55749A9D = TArmyCombatMoveTE.ExecuteCombat;
    557C1AB9/557C1BE6 = TExplorationSite.ExecuteSearch.
  * A healthy session pairs every CCRE with a CDES before the next CCRE.

PURELY ADDITIVE + OBSERVATIONAL. Three 5-byte entry hooks on VANILLA functions (each displaces whole
instructions, each verified free of .reloc fixups -- the trap that crashed cave_cityseed v1), a brand
new cave in virgin space at 0x55810400, and scratch in BSS page slack at 0x558FA900 (above every
claimed flag; see the BSS map in Raze_Dialog_Freeze_Fix.md -- note 0x558FA800/801 are DOUBLE-CLAIMED
and must not be reused). It changes NO game behaviour: every hook saves all registers and flags,
writes its line, restores, replays the displaced instructions and jumps back.

COST. One open/append/close per combat event -- trivial at this rate, and deliberately unbuffered so
nothing is lost to the freeze.

REMOVE IT when the investigation is done: `--revert` restores the three hooks and zeroes the cave.

Idempotent; verify-before-write; dry-run by default, --apply to write (close all AoW binaries first:
AoW.exe / AoWCompat.exe / AoWDevEd.exe all lock the DLL). Backup AoWEPACK.dpl.pre-combatdiag.
"""
import os, sys, shutil, struct
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)
DLL  = os.path.join(GAME, "AoWEPACK.dpl")
BASE = 0x55700000

# ---- hook sites (prologue bytes verified reloc-free + no internal branch lands inside) ----
CREATE_COMBAT   = 0x55778714; CREATE_ORIG  = bytes.fromhex("5356578bf2"); CREATE_CONT  = 0x55778719
DESTROY_COMBAT  = 0x557787F8; DESTROY_ORIG = bytes.fromhex("558bec6a00"); DESTROY_CONT = 0x557787FD
RAZE_ENTRY      = 0x557602F8; RAZE_ORIG    = bytes.fromhex("558bec6a00"); RAZE_CONT    = 0x557602FD
# v2: round pump. 7-byte displacement (whole instructions), reloc-free, continue past them.
# (Never fired -- TFastCombat evidently overrides UpdateStatus, so the base hook is dead. Kept for
# tactical combats; the fast path is covered by the two v4 hooks below.)
UPDSTATUS       = 0x557282E4; UPD_ORIG     = bytes.fromhex("53568bd88b431c"); UPD_CONT   = 0x557282EB
# v4: the FAST-combat lifecycle -- the hang is between CreateCombat and DestroyCombat on flag 0x202B0.
FCEXECUTE       = 0x55744A0C; FCE_ORIG     = bytes.fromhex("558bec6a00");     FCE_CONT   = 0x55744A11
FCUNIT          = 0x55744268; FCU_ORIG     = bytes.fromhex("5356575583c4e4"); FCU_CONT   = 0x5574426F
# v5: bracket CreateCombat -> Execute. User reports the fast combat NEVER STARTS and both stacks are
# deleted, so the fault is in this window: Setup -> AddArmy(xN) -> Initialize -> (Activate) -> Execute.
CB_SETUP        = 0x55727310; SET_ORIG     = bytes.fromhex("558bec5153");     SET_CONT   = 0x55727315
CB_ADDARMY      = 0x55727804; ADD_ORIG     = bytes.fromhex("558bec83c4cc");   ADD_CONT   = 0x5572780A
CB_INIT         = 0x55727C94; INI_ORIG     = bytes.fromhex("5356575 58bf0".replace(" ","")); INI_CONT = 0x55727C9A
# v6: the HP-bar draw. AoWE.ShowHitPcnt @0x5575A830 builds a clip rect from a hit-point PERCENTAGE:
#   local_30 = x + ((pcnt+3)>>2) ; if (ctx[6] < local_30) local_30 = ctx[6]
# and `local_30` IS ctx[6] -- the rect's RIGHT edge. An inverted/degenerate rect is what aowInt
# rejects with "Blt Error". TCombatWall.ShowHitAnimation (+0x104) dispatches to Show (+0xFC), which
# calls this on EVERY hit to a wall -- exactly when the error fires. Capture the real arguments so we
# can see WHY the rect is bad instead of guessing (four theories have already died here).
# Entry regs (verified against the call site @0x55725CF3): EAX=x, EDX=y, ECX=ctx, [esp+4]=pcnt.
HITPCNT         = 0x5575A830; HITP_ORIG    = bytes.fromhex("558bec83c4bc"); HITP_CONT  = 0x5575A836

# ---- kernel32 IAT slots (already imported by AoWEPACK.dpl; module-relative -> reach via delta) ----
IAT_CREATEFILEA    = 0x558FB7B0
IAT_WRITEFILE      = 0x558FB788
IAT_CLOSEHANDLE    = 0x558FB7B4
IAT_SETFILEPOINTER = 0x558FB790

# ---- cave + BSS scratch ----
CAVE      = 0x55810400          # virgin zero space (itemtarget ends 0x558102AD); ~880KB free above
BUF       = 0x558FA900          # 64 B line buffer   ) BSS page slack, committed + zero-filled,
NWRITTEN  = 0x558FA940          # WriteFile out-param ) all ABOVE the highest claimed flag 0x558FA840.
V1        = 0x558FA944
V2        = 0x558FA948
V3        = 0x558FA94C
V4        = 0x558FA950
V5        = 0x558FA954
RNDCNT    = 0x558FA958          # round-log cap counter (log would otherwise be unbounded on a spin)
RND_CAP   = 400                 # 400 ROND lines is plenty to prove "spinning" vs "stopped dead"
FCCNT     = 0x558FA95C          # per-unit fast-combat pump counter
FC_CAP    = 600                 # 600 FCEX lines proves a spin and names the unit it spins on
HPCNT     = 0x558FA960          # HP-bar probe counter
HP_CAP    = 250                 # ShowHitPcnt can fire per-frame; cap it
# 2026-07-22: these WERE 0x558FA800/804. The 0x800 dword is now watched only for regression -- it
# belongs to build_path_outerring.py (SX/SY) and legitimately holds map coordinates, which is exactly
# what this probe caught clobbering simfly's flag. simfly + razeok have since moved to 0x860/0x861,
# so MODFLAGS_A now watches the NEW pair and must read 0 at the start of every battle.
MODFLAGS_A = 0x558FA860         # dword: simfly(860) razeok(861) -(862) -(863)   <- expect 00000000
MODFLAGS_B = 0x558FA804         # dword: razeplayer(804) razeguard(805) razenoflee(806) -(807)

# v3: the combat-log ring in AoW.exe (fixed base, so absolute reads are correct from the DLL --
# same convention build_combatlog_dll.py already uses). Guarded by the 'CLG1' magic exactly as that
# script does, so a host without the .clog section logs zeros instead of faulting.
# WHY: the exe drain (build_combatlog_exe.py `_drain`) loops `while (rd != wr) { rd++ }` -- once per
# INDEX, not per slot -- and only commits rd AFTER the loop. If the writer laps the 64-slot ring
# (which is what happens while TFastCombatWindow animates, because the drain pumps off
# MapWindowUpdate and that does not tick then), the loop runs wr-rd times, re-reading the same 64
# slots and doing a self-refreshing TStringList.Add per iteration. A large wr-rd gap here is the
# smoking gun for the freeze-on-automatic-battle.
RING      = 0x60D000
RING_WR   = RING + 4
RING_RD   = RING + 8
RING_MAGIC = 0x31474C43         # 'CLG1'

def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e+6)[0]
    opt  = struct.unpack_from("<H", data, e+0x14)[0]
    secs = []
    for i in range(nsec):
        o = e + 0x18 + opt + i*40
        vs, va, rs, ptr = struct.unpack_from("<IIII", data, o+8)
        secs.append((va, vs, rs, ptr))
    return secs

def foff(secs, va):
    r = va - BASE
    for sva, vs, rs, ptr in secs:
        if sva <= r < sva + max(vs, rs):
            return ptr + (r - sva)
    raise ValueError(f"VA 0x{va:X} not mapped")

# =====================================================================================
# The cave. One assembly unit, four call/pop delta anchors (core + one per stub).
# Register discipline in every stub: pushad/pushfd ... popfd/popad, so the replayed prologue
# runs with byte-identical register and flag state. Return address of the hooked function is at
# [esp+0x24] inside a stub (32 pushad + 4 pushfd; the call/pop anchor nets to zero).
# =====================================================================================
def src(p):
    return f"""
        jmp Lstubs

    Lfname:  .ascii "razediag.log\\0"
    Ltag_cc: .ascii "CCRE "
    Ltag_cd: .ascii "CDES "
    Ltag_rz: .ascii "RAZE "
    Ltag_rn: .ascii "ROND "
    Ltag_fe: .ascii "FEXE "
    Ltag_fu: .ascii "FCEX "
    Ltag_st: .ascii "SETU "
    Ltag_aa: .ascii "ADDA "
    Ltag_in: .ascii "INIT "
    Ltag_hp: .ascii "HITP "

    /* ---- Lhex: EAX = value, EDI = dest cursor -> writes 8 hex digits + ' ', advances EDI ---- */
    Lhex:
        push ecx
        push edx
        mov ecx, 8
    Lhexloop:
        rol eax, 4
        mov dl, al
        and dl, 0x0F
        add dl, 0x30
        cmp dl, 0x39
        jbe Lhexok
        add dl, 7
    Lhexok:
        mov byte ptr [edi], dl
        inc edi
        dec ecx
        jnz Lhexloop
        mov byte ptr [edi], 0x20
        inc edi
        pop edx
        pop ecx
        ret

    /* ---- Lflags: EBX = load delta -> V4/V5 = the mod's BSS flag dwords. ----
       V4 low byte = simfly (0x860), next = razeok (0x861). V5 third byte = razenoflee (0x806),
       which gates cave_noflee inside fcExecute -- the hook that stops side 0 ever withdrawing. */
    Lflags:
        push eax
        mov eax, dword ptr [ebx + 0x{MODFLAGS_A:X}]
        mov dword ptr [ebx + 0x{V4:X}], eax
        mov eax, dword ptr [ebx + 0x{MODFLAGS_B:X}]
        mov dword ptr [ebx + 0x{V5:X}], eax
        pop eax
        ret

    /* ---- Lcore: EBX = load delta, ESI = runtime ptr to a 5-char tag. Emits one line. ----
       Assumes the caller already saved every register and the flags. */
    Lcore:
        lea edi, [ebx + 0x{BUF:X}]
        mov ecx, 5
    Ltagcpy:
        mov al, byte ptr [esi]
        mov byte ptr [edi], al
        inc esi
        inc edi
        dec ecx
        jnz Ltagcpy
        mov eax, dword ptr [ebx + 0x{V1:X}]
        call Lhex
        mov eax, dword ptr [ebx + 0x{V2:X}]
        call Lhex
        mov eax, dword ptr [ebx + 0x{V3:X}]
        call Lhex
        mov eax, dword ptr [ebx + 0x{V4:X}]
        call Lhex
        mov eax, dword ptr [ebx + 0x{V5:X}]
        call Lhex
        mov byte ptr [edi], 0x0D
        inc edi
        mov byte ptr [edi], 0x0A
        inc edi
        lea eax, [ebx + 0x{BUF:X}]
        mov esi, edi
        sub esi, eax                         /* esi = byte count */

        push 0                               /* hTemplateFile */
        push 0x80                            /* FILE_ATTRIBUTE_NORMAL */
        push 4                               /* OPEN_ALWAYS */
        push 0                               /* lpSecurityAttributes */
        push 1                               /* FILE_SHARE_READ */
        push 0x40000000                      /* GENERIC_WRITE */
        lea eax, [ebx + Lfname]
        push eax
        call dword ptr [ebx + 0x{IAT_CREATEFILEA:X}]
        cmp eax, -1
        je Lcore_out
        mov edi, eax                         /* handle */
        push 2                               /* FILE_END */
        push 0
        push 0
        push edi
        call dword ptr [ebx + 0x{IAT_SETFILEPOINTER:X}]
        push 0
        lea eax, [ebx + 0x{NWRITTEN:X}]
        push eax
        push esi
        lea eax, [ebx + 0x{BUF:X}]
        push eax
        push edi
        call dword ptr [ebx + 0x{IAT_WRITEFILE:X}]
        push edi
        call dword ptr [ebx + 0x{IAT_CLOSEHANDLE:X}]
    Lcore_out:
        ret

    Lstubs:
    /* ---- CreateCombat(EAX=map, EDX=flag): log flag, map[+0x120] BEFORE the call, caller ---- */
    Lh_create:
        pushad
        pushfd
        call La1
    La1:
        pop ebx
        sub ebx, 0x{p[0]:X}
        mov dword ptr [ebx + 0x{V1:X}], edx          /* combat flag */
        mov ecx, dword ptr [eax + 0x120]             /* live combat slot -- non-zero here = the raise */
        mov dword ptr [ebx + 0x{V2:X}], ecx
        mov ecx, dword ptr [esp + 0x24]              /* caller return address */
        sub ecx, ebx                                 /* -> link-time */
        mov dword ptr [ebx + 0x{V3:X}], ecx
        /* v2: the mod's own BSS flag bytes as the combat starts. A stuck flag here changes shared
           combat code for EVERY battle: simfly(800) rescopes damage values, razenoflee(806) stops
           side 0 withdrawing. 0x800/0x801 are also written by path cave_stash on every unit move. */
        call Lflags                                  /* v4 = simfly/razeok pair, v5 = razenoflee pair */
        lea esi, [ebx + Ltag_cc]
        call Lcore
        popfd
        popad
        push ebx
        push esi
        push edi
        mov esi, edx
        jmp 0x{CREATE_CONT:X}

    /* ---- DestroyCombat(EAX=map): log map[+0x120] before teardown, caller ---- */
    Lh_destroy:
        pushad
        pushfd
        call La2
    La2:
        pop ebx
        sub ebx, 0x{p[1]:X}
        mov ecx, dword ptr [eax + 0x120]
        mov dword ptr [ebx + 0x{V1:X}], ecx
        mov dword ptr [ebx + 0x{V2:X}], 0
        mov ecx, dword ptr [esp + 0x24]
        sub ecx, ebx
        mov dword ptr [ebx + 0x{V3:X}], ecx
        call Lflags                                  /* flag state at battle end */
        lea esi, [ebx + Ltag_cd]
        call Lcore
        popfd
        popad
        push ebp
        mov ebp, esp
        push 0
        jmp 0x{DESTROY_CONT:X}

    /* ---- TStructure.Raze(EAX=self, DL=player): log player, structure VMT (class id), caller ---- */
    Lh_raze:
        pushad
        pushfd
        call La3
    La3:
        pop ebx
        sub ebx, 0x{p[2]:X}
        movzx ecx, dl
        mov dword ptr [ebx + 0x{V1:X}], ecx
        mov ecx, dword ptr [eax]                     /* structure VMT ptr */
        sub ecx, ebx                                 /* -> link-time: identifies the class */
        mov dword ptr [ebx + 0x{V2:X}], ecx
        mov ecx, dword ptr [esp + 0x24]
        sub ecx, ebx
        mov dword ptr [ebx + 0x{V3:X}], ecx
        mov dword ptr [ebx + 0x{V4:X}], 0
        mov dword ptr [ebx + 0x{V5:X}], 0
        lea esi, [ebx + Ltag_rz]
        call Lcore
        popfd
        popad
        push ebp
        mov ebp, esp
        push 0
        jmp 0x{RAZE_CONT:X}

    /* ---- TCombat.UpdateStatus(EAX=combat): once per round. Proves spin-vs-stall. ----
       Capped at {RND_CAP} lines: an infinite round pump would otherwise fill the disk, and 400
       identical records already prove the pump is looping. V1 = combat[+0x14] (the status/result
       byte as it stands ON ENTRY), V2 = round ordinal, V4 = the razenoflee/razeguard flag dword. */
    Lh_round:
        pushad
        pushfd
        call La4
    La4:
        pop ebx
        sub ebx, 0x{p[3]:X}
        mov ecx, dword ptr [ebx + 0x{RNDCNT:X}]
        inc ecx
        mov dword ptr [ebx + 0x{RNDCNT:X}], ecx
        cmp ecx, {RND_CAP}
        ja Lrn_out
        mov dword ptr [ebx + 0x{V2:X}], ecx
        movzx ecx, byte ptr [eax + 0x14]
        mov dword ptr [ebx + 0x{V1:X}], ecx
        mov ecx, dword ptr [esp + 0x24]
        sub ecx, ebx
        mov dword ptr [ebx + 0x{V3:X}], ecx
        mov ecx, dword ptr [ebx + 0x{MODFLAGS_B:X}]
        mov dword ptr [ebx + 0x{V4:X}], ecx
        mov dword ptr [ebx + 0x{V5:X}], 0
        lea esi, [ebx + Ltag_rn]
        call Lcore
    Lrn_out:
        popfd
        popad
        push ebx
        push esi
        mov ebx, eax
        mov eax, dword ptr [ebx + 0x1C]
        jmp 0x{UPD_CONT:X}

    /* ---- TFastCombat.Execute(EAX=combat): once per auto-resolved battle. Proves we got in. ---- */
    Lh_fexe:
        pushad
        pushfd
        call La5
    La5:
        pop ebx
        sub ebx, 0x{p[4]:X}
        mov dword ptr [ebx + 0x{V1:X}], eax          /* combat ptr */
        movzx ecx, byte ptr [eax + 0x14]             /* status byte on entry */
        mov dword ptr [ebx + 0x{V2:X}], ecx
        mov ecx, dword ptr [esp + 0x24]
        sub ecx, ebx
        mov dword ptr [ebx + 0x{V3:X}], ecx
        mov dword ptr [ebx + 0x{FCCNT:X}], 0         /* reset the per-battle pump counter */
        call Lflags
        lea esi, [ebx + Ltag_fe]
        call Lcore
        popfd
        popad
        push ebp
        mov ebp, esp
        push 0
        jmp 0x{FCE_CONT:X}

    /* ---- TFastCombatUnit.fcExecute(EAX=unit): the per-unit pump. THE spin detector. ----
       Capped at {FC_CAP}. If the log ends with {FC_CAP} FCEX lines the pump is looping; V2 (the unit
       pointer) says whether it is stuck on ONE unit or cycling. cave_noflee (build_razebattle_tower)
       is hooked 0x41 bytes into this same function, so V5's razenoflee byte is logged alongside. */
    Lh_fcunit:
        pushad
        pushfd
        call La6
    La6:
        pop ebx
        sub ebx, 0x{p[5]:X}
        mov ecx, dword ptr [ebx + 0x{FCCNT:X}]
        inc ecx
        mov dword ptr [ebx + 0x{FCCNT:X}], ecx
        cmp ecx, {FC_CAP}
        ja Lfu_out
        mov dword ptr [ebx + 0x{V1:X}], ecx
        mov dword ptr [ebx + 0x{V2:X}], eax          /* the unit being pumped */
        mov ecx, dword ptr [esp + 0x24]
        sub ecx, ebx
        mov dword ptr [ebx + 0x{V3:X}], ecx
        call Lflags
        lea esi, [ebx + Ltag_fu]
        call Lcore
    Lfu_out:
        popfd
        popad
        push ebx
        push esi
        push edi
        push ebp
        add esp, -0x1C
        jmp 0x{FCU_CONT:X}

    /* ---- TCombat.Setup(EAX=combat, EDX=?, CL=?) ---- */
    Lh_setup:
        pushad
        pushfd
        call La7
    La7:
        pop ebx
        sub ebx, 0x{p[6]:X}
        mov dword ptr [ebx + 0x{V1:X}], eax
        mov dword ptr [ebx + 0x{V2:X}], edx
        mov ecx, dword ptr [esp + 0x24]
        sub ecx, ebx
        mov dword ptr [ebx + 0x{V3:X}], ecx
        call Lflags
        lea esi, [ebx + Ltag_st]
        call Lcore
        popfd
        popad
        push ebp
        mov ebp, esp
        push ecx
        push ebx
        jmp 0x{SET_CONT:X}

    /* ---- TCombat.AddArmy(EAX=combat, EDX=army, CL=side) ---- */
    Lh_addarmy:
        pushad
        pushfd
        call La8
    La8:
        pop ebx
        sub ebx, 0x{p[7]:X}
        mov dword ptr [ebx + 0x{V1:X}], eax
        mov dword ptr [ebx + 0x{V2:X}], edx          /* the army object */
        mov ecx, dword ptr [esp + 0x24]
        sub ecx, ebx
        mov dword ptr [ebx + 0x{V3:X}], ecx
        call Lflags
        lea esi, [ebx + Ltag_aa]
        call Lcore
        popfd
        popad
        push ebp
        mov ebp, esp
        add esp, -0x34
        jmp 0x{ADD_CONT:X}

    /* ---- TCombat.Initialize(EAX=combat) -- builds walls; last stop before Activate/Execute ---- */
    Lh_init:
        pushad
        pushfd
        call La9
    La9:
        pop ebx
        sub ebx, 0x{p[8]:X}
        mov dword ptr [ebx + 0x{V1:X}], eax
        mov dword ptr [ebx + 0x{V2:X}], 0
        mov ecx, dword ptr [esp + 0x24]
        sub ecx, ebx
        mov dword ptr [ebx + 0x{V3:X}], ecx
        call Lflags
        lea esi, [ebx + Ltag_in]
        call Lcore
        popfd
        popad
        push ebx
        push esi
        push edi
        push ebp
        mov esi, eax
        jmp 0x{INI_CONT:X}

    /* ---- ShowHitPcnt(EAX=x, EDX=y, ECX=ctx, [esp+4]=pcnt) -- the HP-bar clip-rect builder ----
       V1=x  V2=y  V3=pcnt (SIGNED)  V4=ctx  V5=ctx[6] (the rect's right-edge bound).
       The bad blit is whatever makes `x + ((pcnt+3)>>2)` an invalid right edge against ctx[6].
       Capped at {HP_CAP}: this can be called per frame while a wall is on screen. */
    Lh_hitp:
        pushad
        pushfd
        call La10
    La10:
        pop ebx
        sub ebx, 0x{p[9]:X}
        mov edi, dword ptr [ebx + 0x{HPCNT:X}]
        inc edi
        mov dword ptr [ebx + 0x{HPCNT:X}], edi
        cmp edi, {HP_CAP}
        ja Lhp_out
        mov dword ptr [ebx + 0x{V1:X}], eax
        mov dword ptr [ebx + 0x{V2:X}], edx
        mov edi, dword ptr [esp + 0x28]      /* pcnt: retaddr at +0x24, arg above it */
        mov dword ptr [ebx + 0x{V3:X}], edi
        mov dword ptr [ebx + 0x{V4:X}], ecx
        test ecx, ecx
        jz Lhp_noctx
        mov edi, dword ptr [ecx + 0x18]      /* ctx[6] = the clamp bound Show* overwrites */
        mov dword ptr [ebx + 0x{V5:X}], edi
        jmp Lhp_emit
    Lhp_noctx:
        mov dword ptr [ebx + 0x{V5:X}], 0
    Lhp_emit:
        lea esi, [ebx + Ltag_hp]
        call Lcore
    Lhp_out:
        popfd
        popad
        push ebp
        mov ebp, esp
        add esp, -0x44
        jmp 0x{HITP_CONT:X}
    """

def assemble(addr, npops):
    """Iterate to a fixed point on the call/pop delta-anchor addresses (as build_razebattle_tower)."""
    guess = [addr + 0x80*(i+1) for i in range(npops)]
    for _ in range(10):
        code, _ = ks.asm(src(guess), addr); code = bytes(code)
        insns = list(cs.disasm(code, addr)); anchors = []
        for i, ins in enumerate(insns):
            if ins.mnemonic == "pop" and i > 0 and insns[i-1].mnemonic == "call":
                try: tgt = int(insns[i-1].op_str, 16)
                except ValueError: tgt = None
                if tgt == ins.address:
                    anchors.append(ins.address)
        assert len(anchors) == npops, f"expected {npops} anchors, found {len(anchors)}"
        if anchors == guess:
            return code
        guess = anchors
    raise RuntimeError("assembly did not converge")

cave = assemble(CAVE, 10)
CAVE_WIPE = 0x800      # revert zeroes a fixed window so shrinking the cave can't strand old bytes
assert len(cave) <= CAVE_WIPE, "cave outgrew the revert wipe window"

def jmp5(frm, to, pad=0):
    b, _ = ks.asm(f"jmp 0x{to:X}", frm); b = bytes(b)
    assert len(b) == 5, f"expected 5-byte jmp, got {len(b)}"
    return b + b"\x90" * pad

# stub entry offsets, located by their `pushad; pushfd` prologue in the assembled bytes
_hits = [i for i in range(len(cave)-1) if cave[i] == 0x60 and cave[i+1] == 0x9C]
assert len(_hits) == 10, f"expected 10 stub entries (pushad;pushfd), found {len(_hits)}"
(H_CREATE, H_DESTROY, H_RAZE, H_ROUND, H_FEXE, H_FCUNIT,
 H_SETUP, H_ADDARMY, H_INIT, H_HITP) = (CAVE + h for h in _hits)

patches = [
    (CAVE,            [bytes(len(cave))], cave,                              "cave_combatdiag (file logger + 6 stubs)"),
    (CREATE_COMBAT,   [CREATE_ORIG],      jmp5(CREATE_COMBAT,  H_CREATE),    "CreateCombat entry  -> diag stub"),
    (DESTROY_COMBAT,  [DESTROY_ORIG],     jmp5(DESTROY_COMBAT, H_DESTROY),   "DestroyCombat entry -> diag stub"),
    (RAZE_ENTRY,      [RAZE_ORIG],        jmp5(RAZE_ENTRY,     H_RAZE),      "TStructure.Raze entry -> diag stub"),
    (UPDSTATUS,       [UPD_ORIG],         jmp5(UPDSTATUS,      H_ROUND, 2),  "TCombat.UpdateStatus -> round-tick stub"),
    (FCEXECUTE,       [FCE_ORIG],         jmp5(FCEXECUTE,      H_FEXE),      "TFastCombat.Execute -> fast-combat stub"),
    (FCUNIT,          [FCU_ORIG],         jmp5(FCUNIT,         H_FCUNIT, 2), "TFastCombatUnit.fcExecute -> spin detector"),
    (CB_SETUP,        [SET_ORIG],         jmp5(CB_SETUP,       H_SETUP),     "TCombat.Setup -> bracket stub"),
    (CB_ADDARMY,      [ADD_ORIG],         jmp5(CB_ADDARMY,     H_ADDARMY,1), "TCombat.AddArmy -> bracket stub"),
    (CB_INIT,         [INI_ORIG],         jmp5(CB_INIT,        H_INIT, 1),   "TCombat.Initialize -> bracket stub"),
    (HITPCNT,         [HITP_ORIG],        jmp5(HITPCNT,        H_HITP, 1),   "ShowHitPcnt -> HP-bar probe"),
]
reverts = [
    (CAVE,           bytes(CAVE_WIPE)),  (CREATE_COMBAT, CREATE_ORIG),
    (DESTROY_COMBAT, DESTROY_ORIG),      (RAZE_ENTRY,    RAZE_ORIG),
    (UPDSTATUS,      UPD_ORIG),          (FCEXECUTE,     FCE_ORIG),
    (FCUNIT,         FCU_ORIG),          (CB_SETUP,      SET_ORIG),
    (CB_ADDARMY,     ADD_ORIG),          (CB_INIT,       INI_ORIG),
    (HITPCNT,        HITP_ORIG),
]

def main():
    apply  = "--apply"  in sys.argv
    revert = "--revert" in sys.argv
    data = bytearray(open(DLL, "rb").read())
    secs = load_sections(data)

    print(f"cave_combatdiag @ {CAVE:08X}  ({len(cave)} B)   stubs: create={H_CREATE:08X} "
          f"destroy={H_DESTROY:08X} raze={H_RAZE:08X} round={H_ROUND:08X}")
    for ins in cs.disasm(cave, CAVE):
        pass  # (full listing available via --dis)
    if "--dis" in sys.argv:
        for ins in cs.disasm(cave, CAVE):
            print(f"  {ins.address:08X}  {ins.bytes.hex():<20s} {ins.mnemonic} {ins.op_str}")

    todo = [(va, None, new, "revert") for va, new in reverts] if revert else patches
    dirty = False
    for va, priors, new, desc in todo:
        o = foff(secs, va)
        cur = bytes(data[o:o+len(new)])
        if cur == new:
            print(f"[= ] {va:08X} {desc}")
            continue
        if priors is not None and cur not in priors:
            print(f"[x ] {va:08X} {desc}\n     MISMATCH cur={cur.hex()}\n     want any of "
                  + " | ".join(p.hex() for p in priors))
            print("\n[abort] nothing written.")
            return 2
        data[o:o+len(new)] = new
        dirty = True
        print(f"[{'w ' if apply else '+ '}] {va:08X} {desc}")

    if not dirty:
        print("\n[= ] AoWEPACK.dpl: already in the requested state.")
        return 0
    if not apply:
        print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first.")
        return 0
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bak = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-combatdiag")
    if not os.path.exists(bak):
        shutil.copy2(DLL, bak); print(f"[bak] {os.path.basename(bak)}")
    open(DLL, "wb").write(bytes(data))
    print("\n[done] Diagnostic active. Reproduce the freeze, then read razediag.log in the game folder.")
    print("       Remove it afterwards with --revert (it is a diagnostic, not a feature).")
    return 0

if __name__ == "__main__":
    sys.exit(main())
