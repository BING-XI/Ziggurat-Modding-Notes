#!/usr/bin/env python3
r"""
AoW1 UNIT WINDOW -- party prev/next arrows in EVERY entry path
(`Ziggurat\AoWz.exe` + `AoWzCompat.exe`, LOCKSTEP; names from `zigexe.py`).
⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)

USER REPORT
      Opening a unit's window from the PARTY SIDE WINDOW shows the small prev/next arrows under
      the portrait (cycle the stack).  Opening the SAME window from the EVENTS-WINDOW PORTRAIT or
      the ITEMS-FOUND pickup dialog shows no arrows.  Wanted: arrows in every path, driven by the
      unit's own army rather than by whatever is selected on the map.

RE -- WHY THE ARROWS VANISH  (all addresses re-verified on OUR AoWz.exe, 2026-09-03)
      Every entry path funnels through ONE refresh routine, TUnitWindow.UpdateUnitWindow
      @0x00407DB8 (eax = Self).  Its arrow decision is 0x00407E52..0x00407EAC and HIDES if any of

        1. [[0x0045EBDC]] (AoWTC.AoWCombatMap)      <> nil   -- tactical combat
        2. [G + 0xA4]                               == nil
        3. TGeneral.PartyIndexOfUnit(G, unit)       <  0
        4. [G + 0x88]  (party slot 1)               <= -1     -- fewer than 2 visible units

      else SHOWS at 0x00407E8D.  `G` = [[0x0045A420]] (= BSS 0x0045B2C0), the TGeneral data
      module; `esi` throughout the routine is the constant 0x0045B070, the TUnitWindow pointer
      slot, so [esi] is the window instance.

      TGeneral's party fields are written by EXACTLY ONE routine -- TMapEvents.TheMapArmySelected
      @0x0044EC30, verified here by disassembly: it clears [G+0x84..+0xA0], walks the army with
      GetCount (VMT+0x54) filling slots with the indices of units NOT concealed from the local
      player (VMT+0xB8, cl = [[0x0045DF7C]] + 0xA5), then stores the army itself in [G+0xA4].
      So those fields describe the army SELECTED ON THE MAP -- the bottom control bar's contents.
      The party side window is a view of that selection, so its path always satisfies tests 2-4.
      The events-portrait and item-pickup paths only set [G+0xC0] = unit and refresh, so if no
      army is selected -- or the selected army is not this unit's -- the arrows are hidden.
      Nothing is wrong with those callers.

      *** There is NO ownership gate anywhere in this chain. ***  TheMapArmySelected has no
      ownership test, so clicking an ENEMY or INDEPENDENT stack on the map fills the slots and
      vanilla shows WORKING arrows for it.  A patch that gates the new logic on "unit's player ==
      local player" therefore produces arrows-visible/clicks-dead on enemy stacks.  That exact
      regression was hit by the third-party author this port is based on and is deliberately not
      reproduced here.

THE FIX -- drive the arrows from the unit's OWN army, vanilla-first
      army := [unit+4] (Engine.TEObject.Owner -- written by Engine.TEObject.SetOwner @0x55519318,
      which is TArmy VMT+0x08 and whose body is `mov [ebx+4], eax`), guarded by an IsClass(TArmy)
      equivalent.  Units concealed from the local player are skipped with the very slot vanilla
      uses, TArmy.GetUnitConcealedForPlayer = VMT+0xB8, so the cycle order matches vanilla's.

      ** The class check is NOT optional. **  TUnitList's VMT ends at +0xB4 (measured: +0xB8 in
      that table reads 0x6E555409, which is the next VMT's class-name shortstring, not a
      function).  Calling +0xB8 on a TUnitList jumps into data.

      AoWz.exe does not import the TArmy class reference (its IAT carries TArmy *methods* and the
      ..THero / ..TArmyHSList classrefs, but no ..TArmy), so the cave identifies the class by
      walking the Delphi 3 VMT header: self-pointer at [vmt-0x40] (validity guard), class name
      shortstring at [vmt-0x20], parent at [vmt-0x18].  Rebase-proof, no new import.

      *** [vmt-0x18] is a POINTER TO the parent class reference, not the parent VMT. ***  It must
      be dereferenced TWICE.  Measured on TArmy: [0x557130EC-0x18] = 0x55710E88, and
      [0x55710E88] = 0x55710EC8 = the TUnitList VMT.  A single deref makes the ancestor walk dead
      code that only ever matches the exact class -- and AoWEPACK.dpl has THREE TArmy descendants
      (TArmyView @0x55713210, TDefendersArmy @0x557C12B4, TPrisonersArmy @0x557C53F4; TArmyView
      even overrides GetUnitConcealedforPlayer), all of which would silently get no arrows.

      VANILLA-FIRST.  The visibility hook sits on the HIDE block, so whenever vanilla's own chain
      passes, the cave is never reached and the party-window path is bit-for-bit unchanged.  The
      rewritten click handlers mirror that: they first ask PartyIndexOfUnit @0x00454100 -- the
      same test the vanilla handler uses, and one that already subsumes tests 2 and 4 (it returns
      -1 when [G+0x84] <= -1 or [G+0xA4] is nil) -- and, when it passes, replay the displaced
      prologue and jump BACK INTO the vanilla body.  Only when vanilla would have done nothing
      does the own-army path run.  This structurally rules out the arrows-visible/clicks-dead
      failure mode: every case vanilla could handle is still handled by vanilla's own code.

PATCH SITES (all three verified reloc-free, and byte-identical in AoWz.exe, AoWzCompat.exe and
the pristine `Ziggurat upload/AoW.exe` -- that donor is VANILLA and keeps its vanilla name)
      0x00407EAD  8 B  8B 06 8B 80 14 02 00 00   -> E9 rel32 + 90 90 90   (hide-arrows block)
                  The only inbound branches are the four chain exits at 0x00407E5A / 0x00407E6A /
                  0x00407E7B / 0x00407E8B and all four land exactly ON 0x00407EAD; a CODE-wide
                  scan finds nothing branching into 0x00407EAE..0x00407EB4.
      0x0040ABF0  5 B  53 56 8B F0 A1            -> E9 rel32   (TUnitWindow.PPrevClick)
      0x0040AC9C  5 B  53 56 8B F0 A1            -> E9 rel32   (TUnitWindow.PNextClick)
                  Both prologues are `push ebx / push esi / mov esi,eax` + the first byte of
                  `mov eax,[0x0045A420]`, so the vanilla resume points are 0x0040ABF4 / 0x0040ACA0
                  -- instruction boundaries, asserted against the pristine exe.

      NOTE the published-method-table entries are NOT repointed; they still hold 0x0040ABF0 /
      0x0040AC9C.  build_wheel_ext.py's aowInt.dpl cave identifies the party arrows by comparing
      the button's OnClick [btn+0x138] against exactly those two constants, so its mouse-wheel
      unit preview keeps working.  Repointing the method table would have broken it silently.

CAVE -- a NEW PE section `.pyar`
      AoWz.exe already has 11 sections and every free tail belongs to another feature
      (.hcol is build_herodlg_columns.py's, and build_unitwin_ability.py squats at 0x0062D000
      inside it; .syd is build_shipyard_income_display.py's; .clog is build_combatlog_exe.py's;
      .tres is build_tierresearch_exe.py's).  A zero run at the end of a patch-owned section is
      often that feature's runtime buffer, so this script appends its own section instead.

        .pyar   VA 0x0062F000   VirtualSize 0x1000   raw 0x00229200   SizeOfRawData 0x1000
                Characteristics 0x60000020 (CODE | EXECUTE | READ -- no WRITE; the cave holds no
                mutable state, so a stray write faults instead of corrupting silently).

      SizeOfImage arithmetic -- recomputed from the MAX end over ALL sections, never from our own:
        before   max(rva + max(VirtualSize, SizeOfRawData)) = 0x22F000  (.syd)   -> SOI 0x22F000
        after    max(..., 0x22F000 + 0x1000)                = 0x230000          -> SOI 0x230000
      Computing it from the new section alone happens to give the same answer here only because
      .pyar is the highest section; the loop is what makes that safe when it is not.  (That bug
      class has already cost this project a fully unmapped cave page -- see
      build_shipyard_income_display.py's docstring.)

      Header room: the section table starts at file 0x1F8, 11 entries end at 0x3B0, SizeOfHeaders
      is 0x400 and 0x3B0..0x400 is all zero -- room for 2 more headers; we take one.

      RE-APPLY is an IN-PLACE overwrite of the section body.  It never rebuilds the file as
      d[:raw] + body, which would destroy every section appended after ours.
      --UNDO restores the three hook sites and zeroes the cave, and deliberately LEAVES THE
      SECTION HEADER IN PLACE (inert, all-zero body).  Nothing is truncated and no section is
      renumbered, so it cannot disturb another section-appending script, and a later --apply
      simply finds .pyar and overwrites it.

      ASLR is off (DllCharacteristics = 0x0000, ImageBase 0x400000), so plain absolutes in the
      cave are correct.  .reloc is real (0x6034 bytes, 11909 entries) and was scanned: no entry
      overlaps any of the three sites or the new section.

LOCKSTEP
      AoWzCompat.exe is AoWz.exe with exactly one byte different (file 0x3BB7C, 0x0F vs 0x05 -- the
      MP build number).  Both get the identical patch, both are verified before either is written,
      and after writing the script asserts the two files still differ in exactly that one byte.

BACKUPS  backups\AoWz.exe.pre-unitwinpartyarrows / backups\AoWzCompat.exe.pre-unitwinpartyarrows
      Taken ONLY from a file positively proved free of THIS feature (all three sites hold the
      vanilla bytes AND .pyar is either absent or entirely zero).  Never on --undo, never on a
      re-tune over an existing install, and never gated merely on "no backup file exists yet".

Usage:
  python build_scripts/build_unitwin_party_arrows.py            dry run + verify current state
  python build_scripts/build_unitwin_party_arrows.py --apply    patch both exes (in-place re-tune ok)
  python build_scripts/build_unitwin_party_arrows.py --undo     surgical revert (hooks + zero cave)
  python build_scripts/build_unitwin_party_arrows.py --dis      disassemble the cave as it would be built
  python build_scripts/build_unitwin_party_arrows.py --selftest run every build + host guard
"""
import os
import re
import shutil
import struct
import subprocess
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                   # mod binary names (AoWz.exe / AoWzCompat.exe)

EXES = zigexe.EXES
# ⚠ VANILLA_EXE keeps the name `AoW.exe` on purpose -- this is the 2025-03-21 stock donor under
# `Ziggurat upload\`, a READ-ONLY reference, not a patch target. It was NOT renamed in 2026-09-09.
PRISTINE = os.path.join("Ziggurat upload", zigexe.VANILLA_EXE)  # the only unpatched exe left
DLL = "AoWEPACK.dpl"
SUFFIX = ".pre-unitwinpartyarrows"
BACKUP_DIR = os.path.join(GAME, "backups")      # ⚠ backups/, never the game root -- rule 2026-09-03

IMAGE_BASE = 0x00400000
COMPAT_BYTE_OFF = zigexe.COMPAT_BYTE    # the ONE byte AoWz.exe / AoWzCompat.exe differ in

# ---------------------------------------------------------------- the new section
SEC_NAME = b".pyar"
SEC_RVA = 0x0022F000                    # VA 0x0062F000
SEC_VSIZE = 0x1000
SEC_RSIZE = 0x1000
SEC_CHARS = 0x60000020                  # CODE | MEM_EXECUTE | MEM_READ
CAVE_VA = IMAGE_BASE + SEC_RVA          # 0x0062F000

# ---------------------------------------------------------------- hook sites
HOOK_VIS = 0x00407EAD
VIS_ORIG = bytes.fromhex("8b068b8014020000")        # mov eax,[esi] / mov eax,[eax+0x214]
VIS_SHOW = 0x00407E8D                               # vanilla "show PPrev + PNext"
VIS_CONT = 0x00407EB5                               # rest of the vanilla hide block

HOOK_PREV = 0x0040ABF0
HOOK_NEXT = 0x0040AC9C
CLICK_ORIG = bytes.fromhex("53568bf0a1")            # push ebx/push esi/mov esi,eax/ mov eax,
VAN_PREV = 0x0040ABF4                               # vanilla PPrevClick body resume
VAN_NEXT = 0x0040ACA0                               # vanilla PNextClick body resume

# --------------------------------------------------------------- engine anchors (AoWz.exe)
REFRESH = 0x00407DB8        # TUnitWindow.UpdateUnitWindow(eax = Self)
PARTYIDX = 0x00454100       # TGeneral.PartyIndexOfUnit(eax = G, edx = unit) -> eax, -1 = not in party
SOUND = 0x00455DFC          # TGeneral UI-sound dispatcher, selected by dl (dl = 0 -> click)
GETUNIT = 0x004026C4        # thunk -> AoWEPACK.dpl!AoWE.TUnitList.GetUnit(eax = list, edx = i)
P_GENERAL = 0x0045A420      # -> &TGeneral            (G = [[P_GENERAL]])
P_MAP = 0x0045DF7C          # IAT slot -> &AoWE.AoWHSMap
P_COMBAT = 0x0045EBDC       # IAT slot -> &AoWTC.AoWCombatMap
IAT_GETUNIT = 0x0045DD00    # the slot GETUNIT's thunk jumps through

# ---------------------------------------------------------------- struct offsets
G_SLOT0 = 0x84              # TGeneral party slot 0   (slots 0..7 at +0x84..+0xA0)
G_ARMY = 0xA4               # TGeneral: the army those slots index
G_UNIT = 0xC0               # TGeneral: the unit the unit window is showing
MAP_LOCALPLAYER = 0xA5      # TAoWHSMap: local (seated) player id, byte
OBJ_OWNER = 0x04            # Engine.TEObject.Owner
VMT_GETCHILD = 0x4C         # Engine.TEChangeNotifyNode.GetChild(eax=self, edx=i)
VMT_GETCOUNT = 0x54         # Engine.TEChangeNotifyNode.GetCount(eax=self)
VMT_CONCEALED = 0xB8        # TArmy.GetUnitConcealedForPlayer(eax=army, edx=i, cl=player) -> al
VMT_SELFPTR = 0x40          # Delphi 3 VMT header: [vmt-0x40] == vmt
VMT_CLASSNAME = 0x20        # [vmt-0x20] -> shortstring
VMT_PARENT = 0x18           # [vmt-0x18] -> POINTER TO the parent classref (deref twice)
WIN_PNEXT = 0x210           # TUnitWindow.PNext  (TAOWButton)
WIN_PPREV = 0x214           # TUnitWindow.PPrev  (TAOWButton)

CLASS_TARGET = b"TArmy"
NAME_D0 = struct.unpack("<I", CLASS_TARGET[0:4])[0]     # 'TArm' -> 0x6D724154
NAME_B4 = CLASS_TARGET[4]                               # 'y'    -> 0x79

SITES = ((HOOK_VIS, VIS_ORIG, "hide-arrows block"),
         (HOOK_PREV, CLICK_ORIG, "TUnitWindow.PPrevClick"),
         (HOOK_NEXT, CLICK_ORIG, "TUnitWindow.PNextClick"))


# =====================================================================================
# the cave
# =====================================================================================
# keystone HANGS (not errors) on ';' comment lines in this project's asm blocks, so every
# comment is stripped before ks.asm().  The three entry points are reached through a fixed
# 3-slot jmp table at the head of the cave: keystone exposes no symbol table, and measuring
# label offsets by assembling line prefixes breaks on forward references.
ASM = r"""
    jmp _vis
    jmp _prev
    jmp _next

_armyof:
    test eax, eax
    jz   _ao_zero
    mov  eax, dword ptr [eax + {owner}]
    test eax, eax
    jz   _ao_zero
    push ebx
    push esi
    mov  esi, eax
    mov  edx, dword ptr [eax]
    mov  ecx, 8
_ao_walk:
    test edx, edx
    jz   _ao_pop
    test dl, 3
    jnz  _ao_pop
    cmp  edx, 0x10000
    jb   _ao_pop
    cmp  edx, dword ptr [edx - {selfptr}]
    jne  _ao_pop
    mov  ebx, dword ptr [edx - {cname}]
    test ebx, ebx
    jz   _ao_pop
    cmp  byte ptr [ebx], {namelen}
    jne  _ao_up
    cmp  dword ptr [ebx + 1], {named0:#x}
    jne  _ao_up
    cmp  byte ptr [ebx + 5], {nameb4:#x}
    jne  _ao_up
    mov  eax, esi
    pop  esi
    pop  ebx
    ret
_ao_up:
    mov  edx, dword ptr [edx - {parent}]
    test edx, edx
    jz   _ao_pop
    test dl, 3
    jnz  _ao_pop
    cmp  edx, 0x10000
    jb   _ao_pop
    mov  edx, dword ptr [edx]
    dec  ecx
    jnz  _ao_walk
_ao_pop:
    pop  esi
    pop  ebx
_ao_zero:
    xor  eax, eax
    ret

_viscount:
    push ebx
    push esi
    push edi
    push ebp
    sub  esp, 8
    mov  ebx, eax
    xor  esi, esi
    xor  edi, edi
    mov  dword ptr [esp + 4], 0
    mov  eax, dword ptr [{pmap:#x}]
    test eax, eax
    jz   _vc_done
    mov  eax, dword ptr [eax]
    test eax, eax
    jz   _vc_done
    movzx eax, byte ptr [eax + {locpl}]
    mov  dword ptr [esp], eax
    mov  eax, ebx
    mov  edx, dword ptr [eax]
    call dword ptr [edx + {getcount}]
    mov  dword ptr [esp + 4], eax
_vc_loop:
    cmp  edi, dword ptr [esp + 4]
    jge  _vc_done
    mov  eax, ebx
    mov  ebp, dword ptr [eax]
    mov  ecx, dword ptr [esp]
    mov  edx, edi
    call dword ptr [ebp + {concealed}]
    test al, al
    jnz  _vc_skip
    inc  esi
    cmp  esi, 2
    jge  _vc_done
_vc_skip:
    inc  edi
    jmp  _vc_loop
_vc_done:
    mov  eax, esi
    add  esp, 8
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret

_vis:
    push ebx
    push esi
    push edi
    push ebp
    mov  eax, dword ptr [{pcombat:#x}]
    test eax, eax
    jz   _vis_nocombat
    cmp  dword ptr [eax], 0
    jne  _vis_hide
_vis_nocombat:
    mov  eax, dword ptr [{pgen:#x}]
    test eax, eax
    jz   _vis_hide
    mov  eax, dword ptr [eax]
    test eax, eax
    jz   _vis_hide
    mov  eax, dword ptr [eax + {gunit}]
    call _armyof
    test eax, eax
    jz   _vis_hide
    call _viscount
    cmp  eax, 2
    jl   _vis_hide
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    jmp  {visshow:#x}
_vis_hide:
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    mov  eax, dword ptr [esi]
    mov  eax, dword ptr [eax + {wpprev}]
    jmp  {viscont:#x}

_prev:
    mov  ecx, -1
    call _stepwork
    test dl, dl
    jnz  _prev_ret
    push ebx
    push esi
    mov  esi, eax
    jmp  {vanprev:#x}
_prev_ret:
    ret

_next:
    mov  ecx, 1
    call _stepwork
    test dl, dl
    jnz  _next_ret
    push ebx
    push esi
    mov  esi, eax
    jmp  {vannext:#x}
_next_ret:
    ret

_stepwork:
    push ebx
    push esi
    push edi
    push ebp
    sub  esp, 20
    mov  dword ptr [esp], ecx
    mov  dword ptr [esp + 4], eax
    mov  eax, dword ptr [{pgen:#x}]
    test eax, eax
    jz   _sw_handled
    mov  ebp, dword ptr [eax]
    test ebp, ebp
    jz   _sw_handled
    mov  eax, ebp
    mov  edx, dword ptr [ebp + {gunit}]
    call {partyidx:#x}
    test eax, eax
    jge  _sw_vanilla
_sw_own:
    mov  eax, ebp
    xor  edx, edx
    call {sound:#x}
    mov  esi, dword ptr [ebp + {gunit}]
    test esi, esi
    jz   _sw_handled
    mov  eax, esi
    call _armyof
    test eax, eax
    jz   _sw_handled
    mov  ebx, eax
    mov  eax, ebx
    mov  edx, dword ptr [eax]
    call dword ptr [edx + {getcount}]
    mov  dword ptr [esp + 8], eax
    cmp  eax, 2
    jl   _sw_handled
    mov  dword ptr [esp + 12], eax
    mov  eax, dword ptr [{pmap:#x}]
    test eax, eax
    jz   _sw_handled
    mov  eax, dword ptr [eax]
    test eax, eax
    jz   _sw_handled
    movzx eax, byte ptr [eax + {locpl}]
    mov  dword ptr [esp + 16], eax
    xor  edi, edi
_sw_find:
    cmp  edi, dword ptr [esp + 8]
    jge  _sw_handled
    mov  eax, ebx
    mov  edx, edi
    call {getunit:#x}
    cmp  eax, esi
    je   _sw_step
    inc  edi
    jmp  _sw_find
_sw_step:
    mov  eax, edi
    add  eax, dword ptr [esp]
    cmp  eax, 0
    jge  _sw_nowrap
    mov  eax, dword ptr [esp + 8]
    dec  eax
_sw_nowrap:
    cmp  eax, dword ptr [esp + 8]
    jl   _sw_inrange
    xor  eax, eax
_sw_inrange:
    mov  edi, eax
    mov  eax, ebx
    mov  ebp, dword ptr [eax]
    mov  ecx, dword ptr [esp + 16]
    mov  edx, edi
    call dword ptr [ebp + {concealed}]
    test al, al
    jz   _sw_gotit
    dec  dword ptr [esp + 12]
    jnz  _sw_step
    jmp  _sw_handled
_sw_gotit:
    mov  eax, ebx
    mov  edx, edi
    call {getunit:#x}
    test eax, eax
    jz   _sw_handled
    cmp  eax, esi
    je   _sw_handled
    mov  edx, dword ptr [{pgen:#x}]
    test edx, edx
    jz   _sw_handled
    mov  edx, dword ptr [edx]
    test edx, edx
    jz   _sw_handled
    mov  dword ptr [edx + {gunit}], eax
    mov  eax, dword ptr [esp + 4]
    call {refresh:#x}
_sw_handled:
    mov  dl, 1
    jmp  _sw_ret
_sw_vanilla:
    xor  dl, dl
_sw_ret:
    mov  eax, dword ptr [esp + 4]
    add  esp, 20
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret
"""

ASM_CONSTS = dict(
    owner=OBJ_OWNER, selfptr=VMT_SELFPTR, cname=VMT_CLASSNAME, parent=VMT_PARENT,
    namelen=len(CLASS_TARGET), named0=NAME_D0, nameb4=NAME_B4,
    pmap=P_MAP, pgen=P_GENERAL, pcombat=P_COMBAT,
    locpl=MAP_LOCALPLAYER, getcount=VMT_GETCOUNT, concealed=VMT_CONCEALED,
    gunit=G_UNIT, wpprev=WIN_PPREV,
    visshow=VIS_SHOW, viscont=VIS_CONT, vanprev=VAN_PREV, vannext=VAN_NEXT,
    partyidx=PARTYIDX, sound=SOUND, getunit=GETUNIT, refresh=REFRESH,
)


def build_cave():
    """Assemble the cave at CAVE_VA. Returns (bytes, {entry: va})."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = ASM.format(**ASM_CONSTS)
    lines = [ln.split(";")[0].rstrip() for ln in src.splitlines()]
    blob, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(
        "\n".join(ln for ln in lines if ln.strip()), CAVE_VA)
    code = bytes(blob)
    entries = {"_vis": CAVE_VA, "_prev": CAVE_VA + 5, "_next": CAVE_VA + 10}
    return code, entries


def hook_blobs(entries):
    def e9(src, dst, pad=0):
        return b"\xE9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * pad
    return {
        HOOK_VIS: e9(HOOK_VIS, entries["_vis"], len(VIS_ORIG) - 5),
        HOOK_PREV: e9(HOOK_PREV, entries["_prev"]),
        HOOK_NEXT: e9(HOOK_NEXT, entries["_next"]),
    }


# =====================================================================================
# minimal PE surgery
# =====================================================================================
def _pe(d):
    return struct.unpack_from("<I", d, 0x3C)[0]


def _sec_tab(d):
    pe = _pe(d)
    return pe + 0x18 + struct.unpack_from("<H", d, pe + 0x14)[0]


def sections(d):
    """[(name, rva, vsize, raw, rsize, chars, hdr_off)] in table order."""
    pe, tab = _pe(d), _sec_tab(d)
    out = []
    for i in range(struct.unpack_from("<H", d, pe + 6)[0]):
        o = tab + i * 40
        nm = bytes(d[o:o + 8]).rstrip(b"\0").decode("latin1")
        vs, rva, rs, raw = struct.unpack_from("<IIII", d, o + 8)
        ch = struct.unpack_from("<I", d, o + 36)[0]
        out.append((nm, rva, vs, raw, rs, ch, o))
    return out


def va2off(d, va):
    rva = va - IMAGE_BASE
    for nm, srva, vs, raw, rs, ch, o in sections(d):
        if srva <= rva < srva + max(vs, rs):
            return raw + (rva - srva)
    raise ValueError("VA %#010x is not mapped" % va)


def max_section_end(d):
    """max(rva + max(VirtualSize, SizeOfRawData)) over ALL sections -- never just our own."""
    return max(srva + max(vs, rs) for nm, srva, vs, raw, rs, ch, o in sections(d))


def recompute_soi(d):
    """SizeOfImage = align_up(max end over ALL sections, SectionAlignment). Returns the value."""
    pe = _pe(d)
    align = struct.unpack_from("<I", d, pe + 0x38)[0]
    soi = (max_section_end(d) + align - 1) // align * align
    struct.pack_into("<I", d, pe + 0x50, soi)
    return soi


def find_section(d, name):
    for s in sections(d):
        if s[0] == name:
            return s
    return None


def ensure_section(d):
    """Append .pyar if absent. Returns (raw_off, created)."""
    nm = SEC_NAME.decode()
    s = find_section(d, nm)
    if s:
        _, srva, vs, raw, rs, ch, o = s
        if (srva, rs) != (SEC_RVA, SEC_RSIZE):
            raise SystemExit("ABORT: existing .pyar is rva %#x rsize %#x, expected %#x / %#x"
                             % (srva, rs, SEC_RVA, SEC_RSIZE))
        return raw, False

    pe, tab = _pe(d), _sec_tab(d)
    n = struct.unpack_from("<H", d, pe + 6)[0]
    hdr = tab + n * 40
    if hdr + 40 > struct.unpack_from("<I", d, pe + 0x54)[0]:
        raise SystemExit("ABORT: no room in the PE header for a 12th section")
    if any(d[hdr:hdr + 40]):
        raise SystemExit("ABORT: header slot at %#x is not zero" % hdr)
    if max(raw + rs for _, _, _, raw, rs, _, _ in sections(d)) != len(d):
        raise SystemExit("ABORT: EOF %#x is not the end of the last section's raw data -- "
                         "another tool has appended data; refusing to append a section"
                         % len(d))
    if SEC_RVA != max_section_end(d):
        raise SystemExit(
            "ABORT: .pyar wants rva %#x but the highest section now ends at %#x -- another "
            "feature appended a section first.  Do NOT overlap it: raise SEC_RVA to %#x "
            "(= the new max end) and re-run; the hooks are computed from CAVE_VA, so nothing "
            "else needs editing." % (SEC_RVA, max_section_end(d), max_section_end(d)))

    raw = len(d)
    d.extend(b"\0" * SEC_RSIZE)
    d[hdr:hdr + 8] = SEC_NAME.ljust(8, b"\0")
    struct.pack_into("<IIII", d, hdr + 8, SEC_VSIZE, SEC_RVA, SEC_RSIZE, raw)
    struct.pack_into("<IIII", d, hdr + 24, 0, 0, 0, SEC_CHARS)
    struct.pack_into("<H", d, pe + 6, n + 1)
    return raw, True


def relocs(d):
    """Every VA whose 4-byte field carries a base relocation."""
    pe = _pe(d)
    rva, size = struct.unpack_from("<II", d, pe + 0x78 + 5 * 8)
    out = set()
    if not rva:
        return out
    p, end = va2off(d, IMAGE_BASE + rva), None
    end = p + size
    while p < end - 8:
        page, blk = struct.unpack_from("<II", d, p)
        if blk < 8:
            break
        for i in range((blk - 8) // 2):
            e = struct.unpack_from("<H", d, p + 8 + i * 2)[0]
            if e >> 12:
                out.add(IMAGE_BASE + page + (e & 0xFFF))
        p += blk
    return out


# =====================================================================================
# guards
# =====================================================================================
def build_checks(code, entries, hooks):
    """G1..G6 -- offline; they tie the ASSEMBLED CAVE to the constants above."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    ins = list(md.disasm(code, CAVE_VA))
    bounds = {i.address for i in ins}
    fail = []

    # G1 -- the 3-slot entry table really is three 5-byte near jmps.
    for i, off in enumerate((0, 5, 10)):
        if code[off] != 0xE9:
            fail.append("G1: entry slot %d is %02X, not E9 (keystone shortened a jmp; the "
                        "table layout has shifted)" % (i, code[off]))

    # G2 -- every external branch target the cave relies on is encoded exactly once, correctly.
    want = {VIS_SHOW: "jmp", VIS_CONT: "jmp", VAN_PREV: "jmp", VAN_NEXT: "jmp",
            PARTYIDX: "call", SOUND: "call", REFRESH: "call"}
    seen = {}
    for i in ins:
        if i.mnemonic in ("jmp", "call") and re.fullmatch(r"0x[0-9a-f]+", i.op_str):
            t = int(i.op_str, 16)
            if not (CAVE_VA <= t < CAVE_VA + SEC_VSIZE):
                seen.setdefault(t, []).append(i.mnemonic)
    for va, mn in want.items():
        if va not in seen:
            fail.append("G2: no %s to %#010x in the cave" % (mn, va))
        elif mn not in seen[va]:
            fail.append("G2: %#010x is reached by %s, expected %s" % (va, seen[va], mn))
    for t, mns in seen.items():
        if t not in want and t != GETUNIT:
            fail.append("G2: cave branches to UNEXPECTED %#010x (%s)" % (t, mns))
    if GETUNIT not in seen:
        fail.append("G2: no call to the TUnitList.GetUnit thunk %#010x" % GETUNIT)

    # G3 -- hook blob lengths match the runs they displace, and every hook lands on a cave entry.
    for va, orig, nm in SITES:
        if len(hooks[va]) != len(orig):
            fail.append("G3: hook at %#010x is %d B, displaces %d B" % (va, len(hooks[va]), len(orig)))
        tgt = va + 5 + struct.unpack_from("<i", hooks[va], 1)[0]
        if tgt not in entries.values():
            fail.append("G3: hook at %#010x targets %#010x, not a cave entry" % (va, tgt))
        if any(b != 0x90 for b in hooks[va][5:]):
            fail.append("G3: hook at %#010x pads with something other than 0x90" % va)

    # G4 -- the class-name immediates really spell CLASS_TARGET.
    spelled = struct.pack("<I", NAME_D0) + bytes([NAME_B4])
    if spelled != CLASS_TARGET or len(CLASS_TARGET) != 5:
        fail.append("G4: name immediates spell %r, not %r" % (spelled, CLASS_TARGET))

    # G5 -- the cave fits, and holds no drive-letter path of any kind (privacy + correctness).
    if len(code) > SEC_VSIZE:
        fail.append("G5: cave is %d B, section is %d B" % (len(code), SEC_VSIZE))
    if re.search(rb"[A-Za-z]:[\\/]", code):
        fail.append("G5: cave contains a drive-letter absolute path")

    # G6 -- no internal branch lands mid-instruction (catches a mis-encoded label).
    for i in ins:
        if i.mnemonic.startswith(("j", "call")) and re.fullmatch(r"0x[0-9a-f]+", i.op_str):
            t = int(i.op_str, 16)
            if CAVE_VA <= t < CAVE_VA + len(code) and t not in bounds:
                fail.append("G6: %#010x %s %#010x lands mid-instruction" % (i.address, i.mnemonic, t))
    return fail


def host_checks(exe_bytes, dll_path, pristine_path):
    """H1..H6 -- tie the constants to the BINARIES rather than to the assembled cave."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    fail = []
    d = exe_bytes

    # H1 -- .reloc carries no entry overlapping any displaced run (a 3-byte lookback catches a
    #       field that starts before the site).
    rl = relocs(d)
    for va, orig, nm in SITES:
        bad = sorted(x for x in rl if va - 3 <= x < va + len(orig))
        if bad:
            fail.append("H1: %s has .reloc entries %s inside the displaced bytes"
                        % (nm, [hex(x) for x in bad]))

    # H2 -- nothing in CODE branches into the MIDDLE of a displaced run.
    code_sec = [s for s in sections(d) if s[0] == "CODE"][0]
    _, srva, vs, raw, rs, _, _ = code_sec
    lim = min(vs, rs)
    holes = [(va + 1, va + len(orig)) for va, orig, nm in SITES]
    for o in range(raw, raw + lim - 6):
        va = IMAGE_BASE + srva + (o - raw)
        b = d[o]
        t = None
        if b == 0xEB or 0x70 <= b <= 0x7F:
            t = va + 2 + struct.unpack_from("<b", d, o + 1)[0]
        elif b in (0xE8, 0xE9):
            t = va + 5 + struct.unpack_from("<i", d, o + 1)[0]
        elif b == 0x0F and 0x80 <= d[o + 1] <= 0x8F:
            t = va + 6 + struct.unpack_from("<i", d, o + 2)[0]
        if t is not None and any(lo <= t < hi for lo, hi in holes):
            fail.append("H2: %#010x branches to %#010x, inside a displaced run" % (va, t))

    # H3 -- the resume addresses are instruction boundaries in the PRISTINE exe.
    if pristine_path and os.path.isfile(pristine_path):
        p = bytearray(open(pristine_path, "rb").read())
        for anchor, span, wanted in ((0x00407E52, 0x80, (VIS_SHOW, HOOK_VIS, VIS_CONT)),
                                     (HOOK_PREV, 0x60, (VAN_PREV,)),
                                     (HOOK_NEXT, 0x60, (VAN_NEXT,))):
            o = va2off(p, anchor)
            bounds = {i.address for i in md.disasm(bytes(p[o:o + span]), anchor)}
            for w in wanted:
                if w not in bounds:
                    fail.append("H3: %#010x is not an instruction boundary in the pristine exe"
                                % w)
            for va, orig, nm in SITES:
                if anchor <= va < anchor + span:
                    po = va2off(p, va)
                    if bytes(p[po:po + len(orig)]) != orig:
                        fail.append("H3: pristine bytes at %s differ from ORIG" % nm)
    else:
        fail.append("H3: SKIPPED -- %s not found (the pristine reference is load-bearing)"
                    % PRISTINE)

    # H4 -- the GETUNIT thunk still jumps through the TUnitList.GetUnit IAT slot.
    o = va2off(d, GETUNIT)
    if not (d[o] == 0xFF and d[o + 1] == 0x25
            and struct.unpack_from("<I", d, o + 2)[0] == IAT_GETUNIT):
        fail.append("H4: %#010x is not `jmp [%#010x]` -- the GetUnit thunk moved" % (GETUNIT, IAT_GETUNIT))

    # H5 -- the DLL still says what the cave assumes about TArmy / TUnitList.
    if os.path.isfile(dll_path):
        fail += _dll_checks(dll_path, md)
    else:
        fail.append("H5: SKIPPED -- %s not found" % os.path.basename(dll_path))
    return fail


def _dll_checks(dll_path, md):
    """H5 -- read AoWEPACK.dpl directly: TArmy VMT header layout, the three VMT slots, and the
    proof that the class check cannot be dropped (TUnitList's VMT is shorter than +0xB8)."""
    fail = []
    d = bytearray(open(dll_path, "rb").read())
    pe = _pe(d)
    base = struct.unpack_from("<I", d, pe + 0x34)[0]
    secs = []
    tab = pe + 0x18 + struct.unpack_from("<H", d, pe + 0x14)[0]
    for i in range(struct.unpack_from("<H", d, pe + 6)[0]):
        o = tab + i * 40
        vs, rva, rs, raw = struct.unpack_from("<IIII", d, o + 8)
        secs.append((rva, vs, raw, rs))

    def off(va):
        r = va - base
        for rva, vs, raw, rs in secs:
            if rva <= r < rva + max(vs, rs):
                return raw + (r - rva)
        return None

    def u32(va):
        o = off(va)
        return struct.unpack_from("<I", d, o)[0] if o is not None and o + 4 <= len(d) else None

    def sstr(va):
        o = off(va)
        if o is None:
            return None
        return bytes(d[o + 1:o + 1 + d[o]])

    def find_vmt(name):
        pat = bytes([len(name)]) + name
        i = 0
        while True:
            i = d.find(pat, i)
            if i < 0:
                return None
            va = None
            for rva, vs, raw, rs in secs:
                if raw <= i < raw + rs:
                    va = base + rva + (i - raw)
            if va is not None:
                j = 0
                key = struct.pack("<I", va)
                while True:
                    j = d.find(key, j)
                    if j < 0:
                        break
                    for rva, vs, raw, rs in secs:
                        if raw <= j < raw + rs:
                            cand = base + rva + (j - raw) + VMT_CLASSNAME
                            if u32(cand - VMT_SELFPTR) == cand:
                                return cand
                    j += 1
            i += 1

    tarmy = find_vmt(b"TArmy")
    tulist = find_vmt(b"TUnitList")
    if tarmy is None or tulist is None:
        fail.append("H5: could not locate the TArmy / TUnitList VMT in %s"
                    % os.path.basename(dll_path))
        return fail
    if sstr(u32(tarmy - VMT_CLASSNAME)) != b"TArmy":
        fail.append("H5: [TArmy VMT-%#x] does not spell 'TArmy'" % VMT_CLASSNAME)
    pcell = u32(tarmy - VMT_PARENT)
    parent = u32(pcell) if pcell else None
    if parent != tulist:
        fail.append("H5: [[TArmy VMT-%#x]] = %s, expected the TUnitList VMT %#010x -- the "
                    "vmtParent DOUBLE dereference is what the ancestor walk depends on"
                    % (VMT_PARENT, ("%#010x" % parent) if parent else parent, tulist))
    lo, hi = base, base + 0x300000
    for off_, nm in ((VMT_GETCHILD, "GetChild"), (VMT_GETCOUNT, "GetCount"),
                     (VMT_CONCEALED, "GetUnitConcealedForPlayer")):
        v = u32(tarmy + off_)
        if not (v and lo <= v < hi):
            fail.append("H5: TArmy VMT+%#x (%s) = %s, not a code pointer" % (off_, nm, v))
    v = u32(tulist + VMT_CONCEALED)
    if v and lo <= v < hi:
        fail.append("H5: TUnitList VMT+%#x looks like a real slot (%#010x) -- the premise that "
                    "the class check is mandatory needs re-deriving" % (VMT_CONCEALED, v))
    return fail


# =====================================================================================
# state
# =====================================================================================
def site_state(d, hooks):
    out = []
    for va, orig, nm in SITES:
        o = va2off(d, va)
        cur = bytes(d[o:o + len(orig)])
        out.append((nm, va, "original" if cur == orig else
                    "applied" if cur == hooks[va] else "FOREIGN"))
    return out


def cave_state(d, code):
    s = find_section(d, SEC_NAME.decode())
    if not s:
        return "absent", None
    raw = s[3]
    body = bytes(d[raw:raw + SEC_RSIZE])
    if body == b"\0" * SEC_RSIZE:
        return "empty", raw
    if body == code + b"\0" * (SEC_RSIZE - len(code)):
        return "current", raw
    return "STALE", raw


def kill_game():
    """Standing authorization: the game/editor lock the binaries. Just kill them."""
    # SCRATCH GUARD: AOW_GAME_DIR set => we are NOT writing to the real install, so we must NOT
    # kill the user's running game.  Standing kill authorization applies to the real install only.
    if os.environ.get("AOW_GAME_DIR"):
        return
    # ⚠ the mod exes were renamed AoWz*/AoWzEd on 2026-09-09; a list that stops at AoW/AoWCompat/
    # AoWDevEd/AoWEd cannot release a lock held by AoWz.exe or AoWzEd.exe. Single source:
    # zigexe.LOCKING_PROCESSES.
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match '^(%s)$' } | Stop-Process -Force"
         % "|".join(zigexe.LOCKING_PROCESSES)],
        capture_output=True)


def lockstep_check(paths):
    a = open(paths[0], "rb").read()
    b = open(paths[1], "rb").read()
    if len(a) != len(b):
        return ["LOCKSTEP: lengths differ (%d vs %d)" % (len(a), len(b))]
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if diff != [COMPAT_BYTE_OFF]:
        return ["LOCKSTEP: %s / %s differ at %s, expected only %#x"
                % (EXES[0], EXES[1], [hex(x) for x in diff[:8]], COMPAT_BYTE_OFF)]
    if (a[COMPAT_BYTE_OFF], b[COMPAT_BYTE_OFF]) != (0x0F, 0x05):
        return ["LOCKSTEP: build-number byte is %02X/%02X, expected 0F/05"
                % (a[COMPAT_BYTE_OFF], b[COMPAT_BYTE_OFF])]
    return []


def disassemble(code, entries):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    names = {v: k for k, v in entries.items()}
    ext = {VIS_SHOW: "vanilla show-arrows", VIS_CONT: "vanilla hide-arrows tail",
           VAN_PREV: "vanilla PPrevClick body", VAN_NEXT: "vanilla PNextClick body",
           PARTYIDX: "TGeneral.PartyIndexOfUnit", SOUND: "TGeneral UI sound (dl=0)",
           REFRESH: "TUnitWindow.UpdateUnitWindow", GETUNIT: "thunk AoWE.TUnitList.GetUnit",
           P_GENERAL: "&TGeneral", P_MAP: "&AoWE.AoWHSMap", P_COMBAT: "&AoWTC.AoWCombatMap"}
    print("  ---- cave @ %#010x, %d B ----" % (CAVE_VA, len(code)))
    for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, CAVE_VA):
        tag = ""
        if i.address in names:
            tag = "   <= hook entry %s" % names[i.address]
        for va, why in ext.items():
            if ("%#x" % va) in i.op_str:
                tag = "   ; %s" % why
        print("    %08X  %-24s %-34s%s"
              % (i.address, i.bytes.hex(), "%s %s" % (i.mnemonic, i.op_str), tag))


# =====================================================================================
def main():
    apply_ = "--apply" in sys.argv
    undo = "--undo" in sys.argv
    dis = "--dis" in sys.argv
    selftest = "--selftest" in sys.argv

    code, entries = build_cave()
    hooks = hook_blobs(entries)

    print("build_unitwin_party_arrows -- unit window party arrows in every entry path")
    print("  game dir : %s" % GAME)
    print("  cave     : %s @ %#010x  %d B used of %#x   (_vis %#010x _prev %#010x _next %#010x)"
          % (SEC_NAME.decode(), CAVE_VA, len(code), SEC_VSIZE,
             entries["_vis"], entries["_prev"], entries["_next"]))

    fail = build_checks(code, entries, hooks)
    for f in fail:
        print("  BUILD GUARD %s" % f)
    if fail:
        return 1
    print("  build guards G1-G6 ....... ok")

    paths = [os.path.join(GAME, e) for e in EXES]
    for p in paths:
        if not os.path.isfile(p):
            print("  MISSING %s" % p)
            return 1
    blobs = [bytearray(open(p, "rb").read()) for p in paths]

    hfail = host_checks(blobs[0], os.path.join(GAME, DLL), os.path.join(GAME, PRISTINE))
    for f in hfail:
        print("  HOST GUARD %s" % f)
    hard = [f for f in hfail if "SKIPPED" not in f]
    if hard:
        return 1
    print("  host guards H1-H5 ........ ok")

    lf = lockstep_check(paths)
    for f in lf:
        print("  %s" % f)
    if lf:
        return 1
    print("  lockstep (pre) ........... ok  (differ only at %#x)" % COMPAT_BYTE_OFF)

    states = []
    for exe, d in zip(EXES, blobs):
        ss = site_state(d, hooks)
        cs, raw = cave_state(d, code)
        states.append((exe, ss, cs, raw))
        print("  %s" % exe)
        for nm, va, st in ss:
            print("      %-24s @%#010x  %s" % (nm, va, st))
        print("      %-24s %s%s" % ("section " + SEC_NAME.decode(), cs,
                                    "" if raw is None else "  (raw %#x)" % raw))

    if any(st == "FOREIGN" for _, ss, _, _ in states for _, _, st in ss):
        print("  FOREIGN bytes at a patch site -- refusing to touch anything.")
        return 1

    if dis or selftest:
        disassemble(code, entries)
    if selftest:
        print("  selftest: all build + host guards fired and passed.")
        return 0

    installed = all(st == "applied" for _, ss, _, _ in states for _, _, st in ss) \
        and all(cs == "current" for _, _, cs, _ in states)
    virgin = all(st == "original" for _, ss, _, _ in states for _, _, st in ss) \
        and all(cs in ("absent", "empty") for _, _, cs, _ in states)

    if undo:
        if virgin:
            print("  already original -- nothing to undo.")
            return 0
        kill_game()
        for p, d in zip(paths, blobs):
            for va, orig, nm in SITES:
                o = va2off(d, va)
                d[o:o + len(orig)] = orig
            s = find_section(d, SEC_NAME.decode())
            if s:
                d[s[3]:s[3] + SEC_RSIZE] = b"\0" * SEC_RSIZE
            open(p, "wb").write(bytes(d))
        lf = lockstep_check(paths)
        for f in lf:
            print("  %s" % f)
        print("  UNDONE -- hooks restored, cave zeroed.  The .pyar section header is left in "
              "place (inert): removing it would renumber sections and truncate the file, which "
              "is exactly the operation that can unmap another feature's cave.")
        return 0 if not lf else 1

    if installed:
        print("  already applied and current.")
        return 0

    if not apply_:
        if not dis:
            disassemble(code, entries)
        print("  dry run -- nothing written.  (--apply / --undo / --dis / --selftest)")
        return 0

    kill_game()
    for p, d in zip(paths, blobs):
        ss = site_state(d, hooks)
        cs, _ = cave_state(d, code)
        clean = all(st == "original" for _, _, st in ss) and cs in ("absent", "empty")
        if clean:
            # ⚠ backups/, never the game root -- rule 2026-09-03. The `clean` test above is the
            # POSITIVE pre-feature proof; the backup file's absence proves nothing on its own,
            # and after the 2026-09-09 rename no AoWz.exe.pre-unitwinpartyarrows can exist.
            os.makedirs(BACKUP_DIR, exist_ok=True)
            bak = os.path.join(BACKUP_DIR, os.path.basename(p) + SUFFIX)
            if not os.path.isfile(bak):
                shutil.copy2(p, bak)
                print("  backed up -> %s" % bak)
        else:
            print("  %s already carries this feature -- NO backup taken (it would snapshot a "
                  "patched state)." % os.path.basename(p))

        raw, created = ensure_section(d)
        d[raw:raw + SEC_RSIZE] = b"\0" * SEC_RSIZE          # in place; never d[:raw] + body
        d[raw:raw + len(code)] = code
        soi = recompute_soi(d)
        for va, orig, nm in SITES:
            o = va2off(d, va)
            blob = hooks[va]
            assert len(blob) == len(orig)
            d[o:o + len(blob)] = blob
        try:
            open(p, "wb").write(bytes(d))
        except PermissionError:
            print("  LOCKED: %s is in use" % p)
            return 1
        print("  %s: section %s (%s) raw %#x, SizeOfImage %#x, %d sections"
              % (os.path.basename(p), SEC_NAME.decode(),
                 "appended" if created else "overwritten in place", raw, soi,
                 len(sections(d))))

    lf = lockstep_check(paths)
    for f in lf:
        print("  %s" % f)
    if lf:
        return 1
    print("  lockstep (post) .......... ok")
    print("  APPLIED, UNTESTED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
