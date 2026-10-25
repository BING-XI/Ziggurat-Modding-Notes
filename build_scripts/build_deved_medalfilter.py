#!/usr/bin/env python3
r"""
ABILITY EDITOR: A RANK TAB OFFERS ONLY WHAT THE LOWER RANKS DO NOT ALREADY GIVE
(AoWDevEd.exe -> AoWzEd.exe)

Owner's request 2026-10-20.  Unit Properties > Rank Abilities > Edit opens the Ability Editor on one
tab's ability set.  Vanilla lists whatever that set alone could take, so a Silver tab offered
Forestry to a unit whose base already has it, and Marksmanship I to one whose base has
Marksmanship II.  Now the sets of the tabs before it count too -- None < Copper < Silver < Gold, and
all four for each Heroic tab:

    single-level  held by a lower set -> not listed
    multi-level   listed as the level after the highest a lower set holds, not listed once that is
                  the cap; Add takes this tab's set straight to that level
    otherwise     as vanilla

THE RULE (best_owner): of this tab's set and every lower set that holds the ability (owner HasAb,
VMT +0x4C), take the one with the highest GetLevel (ability VMT +0x70), ties to the lower set.  The
ability is listed when CanExpand (ability VMT +0xC4) is true on this tab's set -- vanilla's test --
and on that best set, and is named by ExpandName (VMT +0xCC) on the best set.  CanExpand is "not
held, owner mask matches" for a single-level ability and "level below the cap" for every levelled
class (TMultiLevelAbility, Leadership, Turn Undead, Dispel Magic), so no cap or class is restated
here.  GetLevel is 0 for every single-level ability, hence the HasAb test.

ABILITIES THAT NEED STRIKE (owner, 2026-10-20).  The strike enhancements' CanExpand wants Strike
(0x15) in the same set, which a medal or Heroic tab never holds when the unit's base has it; Round
Attack takes the same test since build_strike_prereqs.py (Monster Slaying and Parry no longer do).
So where CanExpand fails, strike_ok asks it again with Strike from the lower sets: the ability's
class is TStrikeEnhancementAbility or TRoundAttackAbility, TAbility's own test passes on this tab's
set (not held, mask), and a lower set holds 0x15.  Both the list (cave_offer) and the Add button
(cave_canadd) use it.  The classes are recognised by their VMTs, found through the rebase delta of
the AoWHSSet import: [HSSET_CELL] - DLL_HSSET + DLL_SE_VMT / DLL_RA_VMT (all three preferred
addresses asserted against AoWEPACK.dpl).

The dialog (TAbilitySelectionDlg, VMT 0x00410014) edits a COPY of the tab's set, [dlg+0x214].  Its
Owner [dlg+4] is the Unit Properties form -- class checked (VMT 0x004107F0); any other owner gets
vanilla behaviour -- whose resource [form+0x214] holds the live rank sets at +0x38 + 4*tab
(tab = [form+0x2D8] & 0x7F; lower = tabs 0 .. min(tab, 4) - 1; Heroic tabs are 4..6).

HOOKS
    F1 0x00410375  available-list fill: `mov ecx,[eax] / call [ecx+0xC4]` (8 B, CanExpand on the
                   dialog's set) -> call cave_offer + 3 nop
    F2 0x0041038A  available-list fill: `call [edi+0x8C]` (6 B, the dialog's name-for-id) ->
                   call cave_name + nop
    M1 0x0041018C  TAbilitySelectionDlg's method table, AddBtnClick's code 0x00410690 ->
                   cave_addclick: the original handler (one ExpandAbility, through
                   build_deved_heroicchoice.py's three-ability cap when that is applied), then --
                   only if the set now holds the ability -- ExpandAbility (owner VMT +0x94) again
                   until GetLevel passes the highest lower level (at most MAX_STEPS = 20 calls, stopping when one
                   makes no progress), then the four refreshes AddBtnClick ends with.  The DFM
                   binds OnClick by name through this table; nothing calls 0x00410690 directly.
                   The entry's .reloc stays valid: the new value is inside the image.
    M2 0x004100A8  TAbilitySelectionDlg VMT +0x94, the Add button's can-add(id) 0x004105B4
                   (CanExpand on the dialog's set) -> cave_canadd: the original, else strike_ok.
                   Only the slot reaches 0x004105B4; its .reloc stays valid.
    Audited each run: no .reloc entry in F1, F2 or the cave, no branch into F1 or F2.

    code   0x0050E000 .. 0x0050E3FF   `.mtb`, inside the DEAD TMAINFORM DFM master (file
           0x109600), directly above build_deved_heroicchoice.py's window.  No `TPF0`, no
           `\x08MaxValue\x02`; the original bytes are embedded below and --undo restores them.
           `.mtb` is executable since build_deved_listarrows.py (asserted).
    roll   NONE -- no random number is drawn or inherited.

Couplings: none in bytes -- F1, F2, M1, M2 and the window belong to no other script.  As layout it
reads build_copper_medal.py's four rank sets and build_deved_heroicchoice.py's Heroic tab numbers;
without either there are fewer tabs and the same code is still right.  Which abilities need
Strike at all is build_strike_prereqs.py's (AoWEPACK.dpl), not this script's.

    python build_scripts/build_deved_medalfilter.py            dry run + state
    python build_scripts/build_deved_medalfilter.py --apply    then: build_zigeditor.py --apply
    python build_scripts/build_deved_medalfilter.py --undo     then: build_zigeditor.py --apply
    python build_scripts/build_deved_medalfilter.py --dis
"""
import argparse, base64, hashlib, os, struct, subprocess, sys, zlib

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import zigexe                       # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
TARGET = os.path.join(GAME, zigexe.SRC_EDITOR)
LIVE = os.path.join(GAME, zigexe.LIVE_EDITOR)
BASE = 0x00400000

CAVE, CAVE_END, CAVE_FILE = 0x0050E000, 0x0050E400, 0x00109600
WIN_SHA = "f796fa9caaf40711"
WIN_ORIG_B64 = (
    "eNpdU8mO00AQ/S6EEEJIIw4sM4lju9tb4t1tJ/EkzubdzmJmgsSVEwf+gAsHLvwDEhJiOMCf8NoSI0HUspxy9atXr14VLtlZwtoc"
    "1qFSBUrp0TZUM1sqHHkaTL78+/v980ftU3wqHNIG6j7SMpfmrtxEJHWEltF9qJ5m+j7UWuC4tPJIEyAfaLTpI4dIfbO2TgvjvDEb"
    "pjRMTU1xZ0m5Q3BSS9wYw4qBBg7/WwUcEyCnxDzE2pSZ92R+3X0vAev2yAx1DSSXASlcqZtrp0gHz5qROkBHBGhbS8gsEQf553hc"
    "uqR0yCnWz4vJYa41kZJbUmZJm7Gw1K4Kl0uRB/LaEqpALVySmTJAaqZ0iXG4NrqFkTliYgwCVweZu29fCxvXxdyW2pBuLGFlDPHe"
    "xfox1qqAlK5cuwSRvoq4NYWFdokXdAdwMO+S8XlhVn5PdSys9SHOUr/aOULmiduJENNX0LxGsx7lT6g9VW821tvS28c6pMZQwLn0"
    "VCK+/PzpI9pvQqUJae7LbaTw5NjALXBA7w0DgoJThzRzOe3SkUDmnEzqSLlZ2/0nJXVGS/UK4DjgjH5rpnNloJ6PimhH3Jmj1B7l"
    "IeHBSNlMONvckzE+GGmpD549fQSJPrx/l3riyhoCsLTlmhOW4YHeJEo317u5AiOVXPMhxnGYqryuTypG2kiF8UAAw0UQFaEMbu2n"
    "FO5NxgOI9jrSURfxY8y7hmf6BnFRhc6FDYPJiT68ePLw3kK3XYuplRgZo4eZBnBk4h3zaiK5mUkz5TmfiMvbhDh1QOqQAPY01bAy"
    "qAW7Luglnjt7hDGtJoPKp5VLMOsD00pfznvCCO5nk/PGAc9EG+yZDmIY98XjB/+tWJ0lUBXitC7BaqQTrnnhYxFksNraQu6I3Ng+"
    "aNDUGiFnZQxm0gt4BjQQWRqDY9SvIVOxiTB55f1dTKbeXo+PU/28tktP3pli+QdE3b7M")

# TAbilitySelectionDlg (VMT 0x00410014) and TUnitResourceEditForm (VMT 0x004107F0)
VMT_UNITFORM = 0x004107F0
D_OWNER, D_SET, D_AVAIL = 0x04, 0x214, 0x204          # TComponent.Owner, edited set, AvailableAbBox
DV_FILLAVAIL, DV_FILLSEL = 0x80, 0x84                 # dialog VMT
F_RES, F_TAB = 0x214, 0x2D8                           # unit form: resource, current rank tab
R_RANKS, N_RANKS = 0x38, 4                            # TUnitResource: None/Copper/Silver/Gold sets
ORIG_ADD, UPD_ADDBTN, UPD_DELBTN = 0x00410690, 0x004105E0, 0x00410638
# engine (through the editor's import thunks / the AoWHSSet cell)
HSSET_CELL, HS_ABCONTROL, TH_GETABILITY = 0x00432898, 0x80, 0x00401C18
TH_GETITEMINDEX, LB_ITEMS, SL_GETOBJECT = 0x00401AC0, 0x118, 0x18
AB_ID, AB_MASK, AB_GETLEVEL, AB_CANEXPAND, AB_EXPANDNAME = 0x0C, 0x20, 0x70, 0xC4, 0xCC
OW_HASAB, OW_GETMASK, OW_EXPAND = 0x4C, 0x8C, 0x94
STRIKE = 0x15
ORIG_CANADD = 0x004105B4                              # dialog VMT +0x94
DLL_HSSET = 0x558FA044                                # AoWEPACK.dpl: the AoWHSSet variable,
DLL_SE_VMT, DLL_RA_VMT = 0x5571E4D0, 0x5571FFA0       # TStrikeEnhancement- / TRoundAttackAbility
MAX_STEPS = 20                                        # Mirror Image has 20 levels

HOOKS = {   # name: (va, original bytes as read off the binary)
    "F1": (0x00410375, bytes.fromhex("8b08ff91c4000000")),
    "F2": (0x0041038A, bytes.fromhex("ff978c000000")),
    "M1": (0x0041018C, struct.pack("<I", ORIG_ADD)),
    "M2": (0x004100A8, struct.pack("<I", ORIG_CANADD)),
}


def check_dll():
    """The three preferred AoWEPACK.dpl addresses strike_ok's rebase delta rests on."""
    import aowepack_patch as AP
    d = open(AP.TARGET, "rb").read()
    rd = lambda va: d[AP.va2off(d, va):AP.va2off(d, va) + 5]
    u32 = lambda va: struct.unpack("<I", rd(va)[:4])[0]
    for vmt, name in ((DLL_SE_VMT, b"TStrikeEnhancementAbility"), (DLL_RA_VMT, b"TRoundAttackAbility")):
        cn = AP.va2off(d, u32(vmt - 0x20))
        assert u32(vmt - 0x40) == vmt and d[cn + 1:cn + 1 + d[cn]] == name, \
            "%s's VMT is not at %08X" % (name.decode(), vmt)
    assert rd(0x55766A6B) == b"\xbf" + struct.pack("<I", DLL_HSSET), \
        "AoWHSSet moved (TStrikeAbility.Remove's `mov edi, offset AoWHSSet` at 0x55766A6B)"
INTERIOR = ("F1", "F2")


def asm(src, va):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, va)
    return bytes(enc)


class Layout:
    def __init__(self):
        self.va, self.parts, self.sym = CAVE, [], {}

    def add(self, name, blob):
        self.sym[name] = self.va
        self.parts.append((name, self.va, blob))
        self.va = (self.va + len(blob) + 15) & ~15

    def blob(self):
        out = bytearray()
        for _n, va, b in self.parts:
            out += b"\xcc" * (va - CAVE - len(out)) + b
        assert CAVE + len(out) <= CAVE_END, "cave overflows its window"
        return bytes(out)


GET_ABILITY = f"""
        mov  eax, dword ptr [{HSSET_CELL:#x}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + {HS_ABCONTROL:#x}]
        call {TH_GETABILITY:#x}"""


def build():
    L = Layout()
    # ---- best_owner: EAX = dialog, EDX = ability -> EAX = best set, EDX = highest level a lower
    #      set holds (-1: none).  Keeps EBX ESI EDI EBP. -------------------------------------------
    L.add("best_owner", asm(f"""
        push ebx
        push esi
        push edi
        push ebp
        mov  ebx, eax
        mov  esi, edx
        push dword ptr [ebx + {D_SET:#x}]
        mov  edx, dword ptr [esp]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {AB_GETLEVEL:#x}]
        mov  edi, eax
        or   ebp, -1
        mov  eax, dword ptr [ebx + {D_OWNER:#x}]
        test eax, eax
        je   out
        cmp  dword ptr [eax], {VMT_UNITFORM:#x}
        jne  out
        movzx ecx, byte ptr [eax + {F_TAB:#x}]
        and  ecx, 0x7f
        cmp  ecx, {N_RANKS}
        jbe  have_n
        mov  ecx, {N_RANKS}
    have_n:
        mov  eax, dword ptr [eax + {F_RES:#x}]
        test eax, eax
        je   out
        lea  ebx, [eax + {R_RANKS:#x}]
        lea  ecx, [ebx + ecx*4]
        push ecx
    next_set:
        cmp  ebx, dword ptr [esp]
        jae  done
        mov  eax, dword ptr [ebx]
        test eax, eax
        je   skip
        mov  edx, dword ptr [esi + {AB_ID:#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {OW_HASAB:#x}]
        test al, al
        je   skip
        mov  edx, dword ptr [ebx]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {AB_GETLEVEL:#x}]
        cmp  eax, ebp
        jle  not_higher
        mov  ebp, eax
    not_higher:
        cmp  eax, edi
        jl   skip
        mov  edi, eax
        mov  edx, dword ptr [ebx]
        mov  dword ptr [esp + 4], edx
    skip:
        add  ebx, 4
        jmp  next_set
    done:
        pop  ecx
    out:
        pop  eax
        mov  edx, ebp
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))
    best = L.sym["best_owner"]

    # ---- strike_ok: EAX = dialog, EDX = ability -> AL = a Strike-dependent ability this tab's set
    #      could take with Strike from a lower set.  Keeps EBX ESI EDI EBP. ----------------------
    L.add("strike_ok", asm(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        mov  eax, dword ptr [{HSSET_CELL:#x}]
        sub  eax, {DLL_HSSET - DLL_SE_VMT:#x}
        cmp  dword ptr [esi], eax
        je   needs_strike
        add  eax, {DLL_RA_VMT - DLL_SE_VMT:#x}
        cmp  dword ptr [esi], eax
        jne  no
    needs_strike:
        mov  edi, dword ptr [ebx + {D_SET:#x}]
        test edi, edi
        je   no
        mov  edx, dword ptr [esi + {AB_ID:#x}]
        mov  eax, edi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {OW_HASAB:#x}]
        test al, al
        jne  no
        mov  eax, edi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {OW_GETMASK:#x}]
        test ax, word ptr [esi + {AB_MASK:#x}]
        je   no
        mov  eax, dword ptr [ebx + {D_OWNER:#x}]
        test eax, eax
        je   no
        cmp  dword ptr [eax], {VMT_UNITFORM:#x}
        jne  no
        movzx ecx, byte ptr [eax + {F_TAB:#x}]
        and  ecx, 0x7f
        cmp  ecx, {N_RANKS}
        jbe  have_n
        mov  ecx, {N_RANKS}
    have_n:
        mov  eax, dword ptr [eax + {F_RES:#x}]
        test eax, eax
        je   no
        lea  edi, [eax + {R_RANKS:#x}]
        lea  esi, [edi + ecx*4]
    next_set:
        cmp  edi, esi
        jae  no
        mov  eax, dword ptr [edi]
        test eax, eax
        je   skip
        mov  edx, {STRIKE:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {OW_HASAB:#x}]
        test al, al
        jne  out
    skip:
        add  edi, 4
        jmp  next_set
    no:
        xor  eax, eax
    out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))
    strike_ok = L.sym["strike_ok"]

    # ---- cave_offer (F1): EAX = ability, EDX = the dialog's set, ESI = dialog -> AL -------------
    L.add("cave_offer", asm(f"""
        push ebx
        push edi
        mov  ebx, eax
        mov  edi, edx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {AB_CANEXPAND:#x}]
        test al, al
        jne  listed
        mov  edx, ebx
        mov  eax, esi
        call {strike_ok:#x}
        test al, al
        je   out
    listed:
        mov  edx, ebx
        mov  eax, esi
        call {best:#x}
        cmp  eax, edi
        mov  edx, eax
        mov  al, 1
        je   out
        mov  eax, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {AB_CANEXPAND:#x}]
    out:
        pop  edi
        pop  ebx
        ret
    """, L.va))

    # ---- cave_name (F2): EAX = dialog, EDX = ability id, ECX = @result string -------------------
    L.add("cave_name", asm(f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  edi, ecx
        {GET_ABILITY}
        mov  ebx, eax
        mov  edx, eax
        mov  eax, esi
        call {best:#x}
        mov  edx, eax
        mov  ecx, edi
        mov  eax, ebx
        mov  esi, dword ptr [eax]
        call dword ptr [esi + {AB_EXPANDNAME:#x}]
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))

    # ---- cave_addclick (M1): EAX = dialog, EDX = Sender ----------------------------------------
    L.add("cave_addclick", asm(f"""
        push ebx
        push esi
        push edi
        push ebp
        mov  ebx, eax
        push edx
        mov  esi, dword ptr [ebx + {D_AVAIL:#x}]
        mov  eax, esi
        call {TH_GETITEMINDEX:#x}
        test eax, eax
        jl   plain
        mov  edx, eax
        mov  eax, dword ptr [esi + {LB_ITEMS:#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {SL_GETOBJECT:#x}]
        mov  ebp, eax
        mov  edx, eax
        {GET_ABILITY}
        test eax, eax
        je   plain
        mov  esi, eax
        mov  edx, eax
        mov  eax, ebx
        call {best:#x}
        mov  edi, edx
        pop  edx
        mov  eax, ebx
        call {ORIG_ADD:#x}
        mov  eax, dword ptr [ebx + {D_SET:#x}]
        mov  edx, ebp
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {OW_HASAB:#x}]
        test al, al
        je   out
        push {MAX_STEPS}
    step:
        mov  edx, dword ptr [ebx + {D_SET:#x}]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {AB_GETLEVEL:#x}]
        cmp  eax, edi
        jg   reached
        push eax
        mov  edx, ebp
        mov  eax, dword ptr [ebx + {D_SET:#x}]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {OW_EXPAND:#x}]
        mov  edx, dword ptr [ebx + {D_SET:#x}]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {AB_GETLEVEL:#x}]
        pop  ecx
        cmp  eax, ecx
        jle  stepped
        dec  dword ptr [esp]
        jne  step
    stepped:
        pop  ecx
        jmp  refresh
    reached:
        pop  ecx
        cmp  ecx, {MAX_STEPS}
        je   out
    refresh:
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {DV_FILLSEL:#x}]
        mov  eax, ebx
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {DV_FILLAVAIL:#x}]
        mov  eax, ebx
        call {UPD_ADDBTN:#x}
        mov  eax, ebx
        call {UPD_DELBTN:#x}
        jmp  out
    plain:
        pop  edx
        mov  eax, ebx
        call {ORIG_ADD:#x}
    out:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, L.va))

    # ---- cave_canadd (M2): EAX = dialog, EDX = ability id -> AL --------------------------------
    L.add("cave_canadd", asm(f"""
        push ebx
        push esi
        mov  ebx, eax
        mov  esi, edx
        call {ORIG_CANADD:#x}
        test al, al
        jne  out
        mov  edx, esi
        {GET_ABILITY}
        test eax, eax
        je   out
        mov  edx, eax
        mov  eax, ebx
        call {strike_ok:#x}
    out:
        pop  esi
        pop  ebx
        ret
    """, L.va))
    return L


def hook_bytes(L):
    s = L.sym
    call = lambda va, dst, n: b"\xe8" + struct.pack("<i", dst - (va + 5)) + b"\x90" * (n - 5)
    v = {k: va for k, (va, _o) in HOOKS.items()}
    return {"F1": call(v["F1"], s["cave_offer"], 8),
            "F2": call(v["F2"], s["cave_name"], 6),
            "M1": struct.pack("<I", s["cave_addclick"]),
            "M2": struct.pack("<I", s["cave_canadd"])}


class PE:
    def __init__(self, path):
        self.path = path
        self.d = bytearray(open(path, "rb").read())
        e = struct.unpack_from("<I", self.d, 0x3C)[0]
        n = struct.unpack_from("<H", self.d, e + 6)[0]
        opt = struct.unpack_from("<H", self.d, e + 20)[0]
        self.e = e
        self.secs = [(bytes(self.d[e + 24 + opt + 40 * i:e + 32 + opt + 40 * i]).rstrip(b"\0"),)
                     + struct.unpack_from("<IIII", self.d, e + 24 + opt + 40 * i + 8)
                     + struct.unpack_from("<I", self.d, e + 24 + opt + 40 * i + 36)
                     for i in range(n)]

    def sec(self, va):
        rva = va - BASE
        for s in self.secs:
            if s[2] <= rva < s[2] + s[3]:
                return s
        sys.exit("ABORT: VA %08X has no file bytes" % va)

    def off(self, va):
        _nm, _vs, vaddr, _rs, raw, _ch = self.sec(va)
        return raw + va - BASE - vaddr

    def read(self, va, n):
        o = self.off(va)
        return bytes(self.d[o:o + n])

    def relocs_in(self, lo, hi):
        rva, size = struct.unpack_from("<II", self.d, self.e + 24 + 136)
        out = []
        o = self.off(BASE + rva) if size else 0
        end = o + size
        while o < end:
            page, blk = struct.unpack_from("<II", self.d, o)
            if blk < 8:
                break
            for k in range((blk - 8) // 2):
                ent = struct.unpack_from("<H", self.d, o + 8 + 2 * k)[0]
                va = BASE + page + (ent & 0xFFF)
                if ent >> 12 and va < hi and va + 4 > lo:
                    out.append(va)
            o += blk
        return out

    def code(self):
        for nm, vs, vaddr, rs, raw, _ch in self.secs:
            if nm == b"CODE":
                return BASE + vaddr, bytes(self.d[raw:raw + min(vs, rs)])


def interior_jumps(pe, windows):
    """rel32 call/jmp and decoded short/near branches anywhere in CODE landing strictly inside a
    window (the window's own instructions excluded)."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    base, code = pe.code()
    hits = []
    for i in range(len(code) - 5):
        if code[i] in (0xE8, 0xE9):
            t = base + i + 5 + struct.unpack_from("<i", code, i + 1)[0]
            hits += [base + i for lo, hi in windows if lo < t < hi]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for lo, hi in windows:
        for ins in md.disasm(code[lo - 0x200 - base:hi + 0x200 - base], lo - 0x200):
            if lo <= ins.address < hi or not (ins.mnemonic.startswith("j") or ins.mnemonic == "call"):
                continue
            try:
                t = int(ins.op_str, 16)
            except ValueError:
                continue
            if lo < t < hi and ins.size < 5:
                hits.append(ins.address)
    return sorted(set(hits))


def kill_aow():
    if os.environ.get("AOW_GAME_DIR"):          # scratch copy: never touch the owner's processes
        return
    for n in zigexe.LOCKING_PROCESSES:
        subprocess.run(["taskkill", "/F", "/IM", n + ".exe"], capture_output=True)


def state(pe, L, new):
    blob = L.blob()
    win = pe.read(CAVE, CAVE_END - CAVE)
    orig = zlib.decompress(base64.b64decode(WIN_ORIG_B64))
    assert hashlib.sha256(orig).hexdigest()[:16] == WIN_SHA, "embedded window is corrupt"
    if win == orig:
        cave = "original"
    elif win[:len(blob)] == blob and win[len(blob):] == orig[len(blob):]:
        cave = "ours"
    else:
        cave = "FOREIGN"
    hooks = {}
    for k, (va, o) in HOOKS.items():
        cur = pe.read(va, len(o))
        hooks[k] = "vanilla" if cur == o else "installed" if cur == new[k] else "FOREIGN " + cur.hex(" ")
    return cave, hooks, orig


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()

    check_dll()
    L = build()
    new = hook_bytes(L)
    pe = PE(TARGET)
    cave, hooks, orig = state(pe, L, new)
    print("build_deved_medalfilter -- %s" % TARGET)
    print("  code window %08X-%08X: %s (%d B of %d used)" % (CAVE, CAVE_END, cave, len(L.blob()),
                                                          CAVE_END - CAVE))
    for k, st in hooks.items():
        print("  %-3s %08X  %s" % (k, HOOKS[k][0], st))
    windows = {k: (va, va + len(o)) for k, (va, o) in HOOKS.items()}
    rl = [v for k in INTERIOR for v in pe.relocs_in(*windows[k])] + pe.relocs_in(CAVE, CAVE_END)
    inner = interior_jumps(pe, [windows[k] for k in INTERIOR])
    mtb = pe.sec(CAVE)
    print("  .reloc under F1/F2/cave: %s" % (", ".join("%08X" % v for v in rl) or "none"))
    print("  jumps into a hook's interior: %s" % (", ".join("%08X" % v for v in inner) or "none"))
    print("  %s characteristics %08X (execute: %s)" % (mtb[0].decode(), mtb[5],
                                                      bool(mtb[5] & 0x20000000)))
    if pe.off(CAVE) != CAVE_FILE or b"TPF0" in orig or b"\x08MaxValue\x02" in orig:
        sys.exit("ABORT: the code window is not where, or what, this script expects")
    if os.path.exists(LIVE):
        lc, lh, _ = state(PE(LIVE), L, new)
        print("  %s (read-only): code %s, hooks %s" % (zigexe.LIVE_EDITOR, lc,
              "installed" if all(s == "installed" for s in lh.values()) else
              "vanilla" if all(s == "vanilla" for s in lh.values()) else "MIXED"))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, va, b in L.parts:
            print("\n  ---- %s @%08X (%d B)" % (name, va, len(b)))
            for ins in md.disasm(b, va):
                print("    %08X  %-24s %s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic,
                                                 ins.op_str))
    st = "VANILLA" if cave == "original" and all(s == "vanilla" for s in hooks.values()) else \
        "INSTALLED" if cave == "ours" and all(s == "installed" for s in hooks.values()) else "MIXED"
    print("state: %s" % st)
    if cave == "FOREIGN" or any(s.startswith("FOREIGN") for s in hooks.values()):
        sys.exit("ABORT: foreign bytes at the cave or a hook site")
    if rl or inner:
        sys.exit("ABORT: a .reloc entry or an interior jump conflicts with a hook")
    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    if a.apply and not mtb[5] & 0x20000000:
        sys.exit("ABORT: .mtb is not executable -- build_deved_listarrows.py is not applied")
    if a.apply and st == "INSTALLED":
        print("\nalready installed -- nothing to do")
        return
    if a.undo and st == "VANILLA":
        print("\nalready vanilla -- nothing to do")
        return
    kill_aow()
    with open(TARGET, "r+b") as f:
        f.seek(CAVE_FILE)
        f.write(L.blob() + orig[len(L.blob()):] if a.apply else orig)
        for k, (va, o) in HOOKS.items():
            f.seek(pe.off(va))
            f.write(new[k] if a.apply else o)
    c2, h2, _ = state(PE(TARGET), L, new)
    want = "installed" if a.apply else "vanilla"
    assert c2 == ("ours" if a.apply else "original") and all(s == want for s in h2.values()), \
        "write did not stick"
    print("\n%s" % ("APPLIED" if a.apply else "UNDONE -- hooks vanilla, window restored"))
    print("    !! NOW RUN:  python build_zigeditor.py --apply   (rebuilds %s)" % zigexe.LIVE_EDITOR)


if __name__ == "__main__":
    main()
