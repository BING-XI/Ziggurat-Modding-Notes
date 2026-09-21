#!/usr/bin/env python3
r"""
AoW1 mod -- "Use items, fully functional": make `itUse` items in a hero's backpack deliver
everything an equipped item delivers, and fix the two vanilla bugs that break the use-item
abilities the engine already ships.

Background + full reverse-engineering: `Modding Resources/Investigation_Items.md`
(§0.4 two stat routes, §0.6 the two ability-query APIs, §0.7 the capability matrix,
 FEATURE 3 for the defects). Read §0.6 before touching anything here.

================================================================================
WHY USE ITEMS ARE CRIPPLED IN VANILLA
================================================================================
A hero has two item aggregates: `THeroItems` at hero+0x70 (the 6 worn slots) and
`THeroInventory` at hero+0x74 (8 backpack slots). `THeroInventory` implements ONLY the ability
half of the protocol -- and gates every method on `item+0x34 == 6` (itUse). It has **no**
GetAttack/GetDefense/GetDamage/GetResistance, no GetImmunityTypes/GetProtectionTypes/GetMoveTypes.
So a use item can currently contribute abilities and nothing else.

That was deliberate: ability legality is a bitmask handshake (`TAbility.CanExpand`, ability+0x20 vs
owner vtable[+0x8c]) in which itUse is its own bit (6), and only ten *activatable* ability classes
declare it. Use items were the "wand / potion" lane; passive modifiers lived on worn gear.
This mod widens that lane deliberately -- see §3.10 for what does and does not leak.

================================================================================
WHAT THIS SCRIPT CHANGES  (4 groups, 13 DLL sites + 1 editor byte)
================================================================================
P1  Healing (0x2F) and Dispel Magic (0x3C) stop being infinitely usable from an item.
    Vanilla writes the "used this turn" flag to one object and reads it from another:
      `THealingCA.Execute@0x5576BCE0`  -> SetEnabled(ab, [healerCombatUnit+0x4C], 0)  = the HERO
      the gate (`TFastCombatUnit.fcExecute@0x55744268` -> THero.GetAbilityEnabled) resolves to
      the ITEM, whose `GetEnabled` finds no data record and therefore returns ENABLED.
    So the flag never latches -> one heal per round, forever. `TDispelMagicAbility` is the same
    code shape and the same bug; those two are the ONLY ability classes with a SetEnabled.
    Fix: hook each `GetEnabled` *after* its self-only GetAbSet test and *before* the data lookup,
    and redirect the data lookup from the item to the wielding hero
    (`item+4` = container, `container+4` = hero -- true for both THeroItems and THeroInventory).
    The set-test still runs on the item, so the ability is still "present"; only the shared
    per-turn record moves to the unit, where `NewTurn`'s IsClass(TAbstractUnit) gate already
    refreshes it. One 5-byte hook per ability; no message-delivery work needed.

P2  Passive abilities on an item actually take effect for ranged attack + damage.
    `GetAttackRA@0x5576E65C` and `GetDamageRA@0x5576E614` ask the shooter via the SELF-ONLY pair
    (`vtable+0x88` GetAbEnabled / `+0x84` GetAbLevel), which on a THero is the un-overridden
    TAbilityOwner implementation -- it sees only innate abilities. Repointed to the item-aware
    pair (`+0x148` GetAbilityEnabled / `+0x144` GetAbilityLevel). Pure displacement edit: both are
    already `call dword ptr [ecx+disp32]`, so the length is unchanged and no cave is needed.
    NOTE this also fixes item-granted Marksmanship from Head/Torso/Defense/Ring, which the
    engine's own legality mask (0x0237) says was always meant to work.
    ⚠ `GetAttackRA` is already hooked by the pre-existing `cave_5580C240` (marksmanship rework +
    height penalty) at 0x5576E689, and its `test al,al / jz` at 0x5576E678 is NOP'd. The two call
    sites we edit sit *before* that and are untouched by it -- the edits compose. Do NOT revert a
    `.pre-*` backup to "restore" this site.

P3  Immunities / Protections / Movement types from a use item.
    `THero.GetX = TAbstractUnit.GetX | THeroItems.GetX(hero+0x70)` -- hero+0x74 is simply absent
    from the expression. Each `THeroItems.GetX` is replaced by a cave that runs the original loop
    over the worn list AND a second, type-6-filtered loop over the backpack.

P4  The flat ATK/DEF/DAM/RES bytes (item+0x46..0x49) from a use item. Same treatment as P3 for
    the four `THeroItems` stat aggregators.
    Authoring: AoWDevEd greys the four stat spinners for itUse at `0x0041349C`
    (`cmp byte [eax+0x34],6` -> `je` the clBtnFace path). That branch only calls SetColor -- it
    never calls SetEnabled -- so the controls may well already be editable and merely *look*
    disabled. Flipping the compared type to an impossible value (6 -> 0x7F) makes itUse take the
    normal clWindow path so the UI matches reality. Values can also be written straight into
    `Release/ITEMS.PFS` (tags 0x0B/0x0C/0x0D/0x0E) with `re_tools/pfs.py`.

Every one of the seven `THeroItems` aggregators has EXACTLY ONE caller (its matching THero.GetX),
verified by whole-module rel32 xref scan -- which is why replacing them wholesale is safe.

================================================================================
SAFETY
================================================================================
- All caves are position-independent: register-relative or rel32 within AoWEPACK.dpl. The only
  absolute references (three class-ref variables, for P1's IsClass checks) are reached through the
  standard call/pop rebase-delta idiom, exactly as build_magebane.py does.
- No displaced byte range carries a `.reloc` entry (audited; the script re-checks at build time).
- Verify-before-write: every site must hold either its known-vanilla bytes or this mod's bytes.
  Mixed/foreign -> abort.
- `--undo` is surgical: restores the 13 DLL sites + the editor byte and zeroes only this cave.
  It touches no backup, so it survives any amount of later layering.

================================================================================
⚠⚠ THE EDITOR EXE TRAP -- the P4 editor byte takes TWO steps
================================================================================
`Ziggurat\AoWDevEd.exe` (zigexe.SRC_EDITOR) is the PATCH SOURCE, and nothing runs it. The editor
the owner actually launches is `Ziggurat\AoWzEd.exe` (zigexe.LIVE_EDITOR), which
`build_zigeditor.py` REBUILDS from AoWDevEd.exe. Skip the second step and the un-greyed spinners
never appear -- silently:

    python build_useitems.py  --apply    # patches AoWEPACK.dpl + Ziggurat\AoWDevEd.exe
    python build_zigeditor.py --apply    # rebuilds -> Ziggurat\AoWzEd.exe

(build_zigeditor.py takes --apply / --undo / --png PATH; no args = dry run.)
The AoWEPACK.dpl half needs no second step -- `Ziggurat\AoWEPACK.dpl` IS the live file.

⚠ `AoWEd.exe` is NO LONGER A TARGET. The 2026-09-09 move left no copy in the overlay -- only the
game root's stock one, which is VANILLA and must never be patched. This mattered: `editor_paths()`
filtered it out with an `isfile` test, so the script reported "Already applied and up to date"
while silently skipping an exe it still believed in.

Backups: `<game dir>\backups\AoWEPACK.dpl.pre-useitems` and `<game dir>\backups\
AoWDevEd.exe.pre-useitems`, each minted only from a file PROVED unpatched at its own sites.
There is no snapshot layer to fall back on -- both `.pre-*` stacks were purged (2026-08-08,
2026-09-03); revert is `--undo`.
Dry-run by default; --apply to commit; --undo to remove; --verify for status; --show to disassemble.
"""

import argparse
import os
import shutil
import struct
import sys

import zigexe

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP_DIR = os.path.join(GAME, "backups")
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-useitems")
EDITORS = [zigexe.SRC_EDITOR]           # AoWEd.exe retired 2026-09-09 -- see the trap above

VA_BASE = 0x55700C00          # AoWEPACK.dpl CODE: VA - VA_BASE == file offset
CAVE_VA = 0x55815000          # measured free: 0x55814D0B..0x558E7917 is one 863KB zero run
CAVE_LIMIT = 0x600
CODE_ZERO_END = 0x558E7918

# ---- feature switches (all four were requested; flip to False to omit a group) -------------
P1_FIX_ONESHOT   = True       # Healing / Dispel Magic per-turn flag
P2_RANGED_ITEMS  = True       # ranged atk/dam see item-granted abilities (Marksmanship)
P3_TYPE_WORDS    = True       # immunities / protections / move types from use items
P4_STAT_BYTES    = True       # item+0x46..0x49 from use items
P4_EDITOR_UNGREY = True       # AoWDevEd: stop grey-ing the stat spinners for itUse
# -------------------------------------------------------------------------------------------

# engine entry points / globals (all preferred-base VAs)
ISCLASS          = 0x557010C0     # System.@IsClass(EAX=obj, EDX=classref) -> AL
PTR_TITEM        = 0x5570FABC     # vmtSelfPtr slot; holds the TItem         class ref
PTR_THEROITEMS   = 0x557116F8     # class-ref variable used by THero.Create
PTR_THEROINV     = 0x557115EC     # class-ref variable used by THero.Create
GETAB_IMMUN_ALL  = 0x5574FADC     # TAbilityOwner.GetAbImmunityTypesAll (EAX=owner) -> AX
GETAB_PROT_ALL   = 0x5574F97C     # TAbilityOwner.GetAbProtectionTypesAll             -> AX
GETAB_MOVE_ALL   = 0x5574F764     # TAbilityOwner.GetAbMoveTypesAll                   -> AL

INV_OFF = 0x74                    # hero+0x74 = THeroInventory
ITUSE   = 6                       # item+0x34 == itUse

# ---- hook sites: (VA, vanilla bytes, label, group) -----------------------------------------
H_HEAL   = 0x5576BF40; R_HEAL   = 0x5576BF45
H_DISPEL = 0x5576CE6C; R_DISPEL = 0x5576CE71
VANILLA_ENABLED_STUB = bytes.fromhex("8b530c8bc6")      # mov edx,[ebx+0xc] ; mov eax,esi

RANGED = [  # (VA, vanilla 6 bytes, patched 6 bytes, label)
    (0x5576E628, "ff91 88000000", "ff91 48010000", "GetDamageRA  GetAbEnabled -> GetAbilityEnabled"),
    (0x5576E63B, "ff91 84000000", "ff91 44010000", "GetDamageRA  GetAbLevel   -> GetAbilityLevel"),
    (0x5576E670, "ff91 88000000", "ff91 48010000", "GetAttackRA  GetAbEnabled -> GetAbilityEnabled"),
    (0x5576E683, "ff91 84000000", "ff91 44010000", "GetAttackRA  GetAbLevel   -> GetAbilityLevel"),
]

STAT_FNS = [  # (VA, item byte offset, label)
    (0x55786354, 0x46, "THeroItems.GetAttack"),
    (0x55786388, 0x47, "THeroItems.GetDefense"),
    (0x557863BC, 0x48, "THeroItems.GetDamage"),
    (0x557863F0, 0x49, "THeroItems.GetResistance"),
]
VANILLA_STAT_PROLOGUE = bytes.fromhex("5356578bf0")     # push ebx,esi,edi ; mov esi,eax

TYPE_FNS = [  # (VA, callee, is_word, label)
    (0x55786470, GETAB_IMMUN_ALL, True,  "THeroItems.GetImmunityTypes"),
    (0x557864C0, GETAB_PROT_ALL,  True,  "THeroItems.GetProtectionTypes"),
    (0x55786424, GETAB_MOVE_ALL,  False, "THeroItems.GetMoveTypes"),
]
VANILLA_TYPE_PROLOGUE = bytes.fromhex("5356575551")     # push ebx,esi,edi,ebp,ecx

# editor: EItem.TItemEditForm.UpdateControls -- `cmp byte ptr [eax+0x34],6 ; je grey ; mov edx,clWindow`
# ⚠ LOCATED BY SIGNATURE, NOT BY ADDRESS. AoWDevEd.exe and the retired AoWEd.exe are different
# builds: the site is 0x0041349C in the former and 0x0041348C in the latter. A fixed VA silently
# hits foreign code in one of them (observed: byte 0xE0). The signature is unique (exactly one hit)
# in both. Kept as reusable RE machinery -- only AoWDevEd.exe is a target now.
ED_SIG = bytes.fromhex("807834067442ba05000080")
ED_IMM = 3          # index of the compared item-type byte inside ED_SIG
ED_OLD, ED_NEW = 0x06, 0x7F


def off(va):
    return va - VA_BASE


def jmp_to(src, dst):
    return b"\xE9" + struct.pack("<i", dst - (src + 5))


def _bx(s):
    return bytes.fromhex(s.replace(" ", ""))


# ============================================================================================
# cave construction
# ============================================================================================
def _walk_loop(tag, filtered, body):
    """Loop over a TItemList in EBP. Mirrors the vanilla loop exactly (which is itself proof
    that EBX/ESI/EDI/EBP survive the per-item call). `body` runs with the item in EAX."""
    flt = ""
    if filtered:
        flt = f"cmp byte ptr [eax + 0x34], {ITUSE}\n jne {tag}_next\n"
    return f"""
        mov  edx, [ebp]
        mov  eax, ebp
        call dword ptr [edx + 0x54]      /* GetCount */
        mov  esi, eax
        xor  edi, edi
    {tag}_loop:
        cmp  edi, esi
        jge  {tag}_end
        mov  eax, [ebp + 8]
        test eax, eax
        je   {tag}_end
        mov  eax, [eax + 4]
        test eax, eax
        je   {tag}_end
        mov  eax, [eax + edi*4]
        test eax, eax
        je   {tag}_next
        {flt}
        {body}
    {tag}_next:
        inc  edi
        jmp  {tag}_loop
    {tag}_end:
    """


def _two_pass(tag, body_a, body_b, tail):
    """pass A over the worn list (this), pass B over hero+0x74 filtered to itUse."""
    return f"""
        push ebx
        push esi
        push edi
        push ebp
        push eax                         /* [esp] = this (THeroItems) */
        xor  ebx, ebx
        mov  ebp, eax
        {_walk_loop(tag + "a", False, body_a)}
        mov  eax, [esp]
        mov  eax, [eax + 4]              /* THeroItems+4 = the owning hero */
        test eax, eax
        je   {tag}_done
        mov  eax, [eax + 0x{INV_OFF:X}]  /* hero+0x74 = THeroInventory */
        test eax, eax
        je   {tag}_done
        mov  ebp, eax
        {_walk_loop(tag + "b", True, body_b)}
    {tag}_done:
        {tail}
        pop  ecx
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    out = {}
    cur = CAVE_VA

    def emit(key, src, addr=None):
        nonlocal cur
        a = (cur + 0xF) & ~0xF if addr is None else addr
        b = bytes(ks.asm(src, a)[0])
        out[key] = (a, b)
        cur = a + len(b)
        return a

    # ---- P1: shared holder resolver + two thin stubs ---------------------------------------
    if P1_FIX_ONESHOT:
        a_res = (cur + 0xF) & ~0xF
        anchor = a_res + 10          # push*4 (4) + mov esi,eax (2) + call rel32 (5) -> pop is at +11
        # recompute precisely: push edx,ebx,esi,edi = 4 ; mov esi,eax = 2 ; call = 5  -> anchor = a+11
        anchor = a_res + 11
        src_res = f"""
            push edx
            push ebx
            push esi
            push edi
            mov  esi, eax                     /* owner */
            call 0x{anchor:X}
            pop  edi
            sub  edi, 0x{anchor:X}            /* edi = runtime rebase delta */
            mov  edx, [edi + 0x{PTR_TITEM:X}]
            mov  eax, esi
            call 0x{ISCLASS:X}
            test al, al
            je   rh_keep
            mov  ebx, [esi + 4]               /* container */
            test ebx, ebx
            je   rh_keep
            mov  edx, [edi + 0x{PTR_THEROITEMS:X}]
            mov  eax, ebx
            call 0x{ISCLASS:X}
            test al, al
            jne  rh_hero
            mov  edx, [edi + 0x{PTR_THEROINV:X}]
            mov  eax, ebx
            call 0x{ISCLASS:X}
            test al, al
            je   rh_keep
        rh_hero:
            mov  eax, [ebx + 4]               /* container+4 = hero */
            test eax, eax
            jne  rh_done
        rh_keep:
            mov  eax, esi
        rh_done:
            pop  edi
            pop  esi
            pop  ebx
            pop  edx
            ret
        """
        emit("resolve", src_res, a_res)
        a_res = out["resolve"][0]
        # sanity: the pop must land exactly on `anchor`
        for tag, ret_va in (("heal", R_HEAL), ("dispel", R_DISPEL)):
            emit(tag, f"""
                mov  edx, [ebx + 0x0C]
                mov  eax, esi
                call 0x{a_res:X}
                jmp  0x{ret_va:X}
            """)

    # ---- P4: four stat aggregators ----------------------------------------------------------
    if P4_STAT_BYTES:
        for va, boff, label in STAT_FNS:
            tag = "s%02x" % boff
            body = f"add  bl, byte ptr [eax + 0x{boff:X}]"
            emit("stat_%02x" % boff,
                 _two_pass(tag, body, body, "mov eax, ebx\n and eax, 0xFF"))

    # ---- P3: three type-word aggregators ----------------------------------------------------
    if P3_TYPE_WORDS:
        for va, callee, is_word, label in TYPE_FNS:
            tag = "t%08x" % va
            merge = "or bx, ax" if is_word else "or bl, al"
            body = f"call 0x{callee:X}\n {merge}"
            tail = "mov eax, ebx" + ("" if is_word else "\n and eax, 0xFF")
            emit("type_%08X" % va, _two_pass(tag, body, body, tail))

    out["_end"] = cur
    return out


# ============================================================================================
def edits_for(cv):
    """[(va, vanilla_bytes, patched_bytes, label)] over AoWEPACK.dpl."""
    e = []
    if P1_FIX_ONESHOT:
        e.append((H_HEAL, VANILLA_ENABLED_STUB, jmp_to(H_HEAL, cv["heal"][0]),
                  "P1 Healing GetEnabled"))
        e.append((H_DISPEL, VANILLA_ENABLED_STUB, jmp_to(H_DISPEL, cv["dispel"][0]),
                  "P1 DispelMagic GetEnabled"))
    if P2_RANGED_ITEMS:
        for va, o, n, lbl in RANGED:
            e.append((va, _bx(o), _bx(n), "P2 " + lbl))
    if P3_TYPE_WORDS:
        for va, _c, _w, lbl in TYPE_FNS:
            e.append((va, VANILLA_TYPE_PROLOGUE, jmp_to(va, cv["type_%08X" % va][0]), "P3 " + lbl))
    if P4_STAT_BYTES:
        for va, boff, lbl in STAT_FNS:
            e.append((va, VANILLA_STAT_PROLOGUE, jmp_to(va, cv["stat_%02x" % boff][0]), "P4 " + lbl))
    return e


def cave_keys(cv):
    return [k for k in cv if not k.startswith("_")]


def reloc_audit(data):
    """Abort if any displaced range carries a .reloc entry (they would be fixed up at load)."""
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    opt = pe_off + 0x18
    nsec = struct.unpack_from("<H", data, pe_off + 6)[0]
    ddir = opt + 96
    rel_rva, rel_sz = struct.unpack_from("<II", data, ddir + 5 * 8)
    secs = []
    for i in range(nsec):
        s = pe_off + 0x18 + struct.unpack_from("<H", data, pe_off + 20)[0] + i * 40
        va, raw_sz, raw_ptr = struct.unpack_from("<III", data, s + 12)[0], \
            struct.unpack_from("<I", data, s + 16)[0], struct.unpack_from("<I", data, s + 20)[0]
        secs.append((va, raw_sz, raw_ptr))

    def r2o(rva):
        for va, sz, ptr in secs:
            if va <= rva < va + sz:
                return ptr + (rva - va)
        return None

    hits, p = set(), rel_rva
    while p < rel_rva + rel_sz:
        o = r2o(p)
        if o is None:
            break
        pg, blk = struct.unpack_from("<II", data, o)
        if blk == 0:
            break
        for k in range(8, blk, 2):
            ent = struct.unpack_from("<H", data, r2o(p + k))[0]
            if ent >> 12:
                hits.add(0x55700000 + pg + (ent & 0xFFF))
        p += blk
    return hits


def disasm(b, va, title):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        print("   (capstone not installed -- skipping listing)")
        return
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    print("   --- %s @0x%08X (%d B) ---" % (title, va, len(b)))
    for i in md.disasm(b, va):
        print("   %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))


# ============================================================================================
def editor_paths():
    """[(exe path, snapshot path)] for every editor target that exists.

    ⚠ The `isfile` filter is why a stale target used to vanish without a word. Any name in EDITORS
    that is absent is REPORTED here, not silently dropped."""
    out = []
    for n in EDITORS:
        p = os.path.join(GAME, n)
        if os.path.isfile(p):
            # Snapshot goes in <game dir>\backups\, never beside the binary (CLAUDE.md 2026-09-03).
            out.append((p, os.path.join(BACKUP_DIR, n + ".pre-useitems")))
        else:
            print("  WARN: %s is not present -- skipped" % p)
    return out


def ed_site(data):
    """Locate the itUse stat-spin gate by signature. Returns the file offset of the compared
    item-type byte, or None. Requires exactly one match (the two editors are different builds,
    so a hard-coded VA is wrong for one of them)."""
    for probe in (ED_SIG, ED_SIG[:ED_IMM] + bytes([ED_NEW]) + ED_SIG[ED_IMM + 1:]):
        hits, o = [], 0
        while True:
            k = data.find(probe, o)
            if k < 0:
                break
            hits.append(k)
            o = k + 1
        if len(hits) == 1:
            return hits[0] + ED_IMM
        if len(hits) > 1:
            return None
    return None


def main():
    ap = argparse.ArgumentParser(description="Use items: full function from the use slot")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--show", action="store_true", help="disassemble the caves")
    args = ap.parse_args()

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s" % DLL)
    data = bytearray(open(DLL, "rb").read())
    cv = build()
    edits = edits_for(cv)

    print("build_useitems   P1=%s P2=%s P3=%s P4=%s (editor=%s)"
          % (P1_FIX_ONESHOT, P2_RANGED_ITEMS, P3_TYPE_WORDS, P4_STAT_BYTES, P4_EDITOR_UNGREY))
    print("  cave 0x%08X..0x%08X  (%d B of %d reserved)"
          % (CAVE_VA, cv["_end"] - 1, cv["_end"] - CAVE_VA, CAVE_LIMIT))
    for k in sorted(cave_keys(cv)):
        va, b = cv[k]
        print("    %-14s 0x%08X  %4d B" % (k, va, len(b)))
    print()

    if args.show:
        for k in sorted(cave_keys(cv)):
            disasm(cv[k][1], cv[k][0], k)
        print()

    # --- .reloc safety -----------------------------------------------------------------
    relocs = reloc_audit(data)
    clash = [(va, lbl) for va, o, n, lbl in edits
             if any(va <= r < va + len(o) for r in relocs)]
    if clash:
        sys.exit("ABORT: displaced bytes carry .reloc entries: %s" % clash)

    # --- status ------------------------------------------------------------------------
    if args.verify or (not args.apply and not args.undo):
        for va, o, n, lbl in edits:
            cur = bytes(data[off(va):off(va) + len(o)])
            st = "PATCHED" if cur == n else ("vanilla" if cur == o else "*** FOREIGN ***")
            print("  %-46s 0x%08X  %-14s %s" % (lbl, va, cur.hex(), st))
        caves_ok = all(bytes(data[off(cv[k][0]):off(cv[k][0]) + len(cv[k][1])]) == cv[k][1]
                       for k in cave_keys(cv))
        print("  caves match: %s" % caves_ok)
        for path, _bk in editor_paths():
            ed = bytearray(open(path, "rb").read())
            o = ed_site(ed)
            st = "site NOT FOUND" if o is None else (
                "PATCHED" if ed[o] == ED_NEW else
                ("vanilla" if ed[o] == ED_OLD else "*** FOREIGN ***"))
            print("  %-46s %-10s %-14s %s"
                  % (os.path.basename(path) + " itUse stat-spin gate",
                     "file+0x%X" % o if o is not None else "-",
                     "%02x" % ed[o] if o is not None else "--", st))
        if args.verify:
            done = all(bytes(data[off(v):off(v) + len(o)]) == n for v, o, n, _ in edits)
            print("\nSTATUS: %s" % ("APPLIED and intact" if (done and caves_ok)
                                    else "NOT fully applied -- run with --apply"))
            return

    # --- undo --------------------------------------------------------------------------
    if args.undo:
        n_hooks = 0
        for va, o, n, lbl in edits:
            if bytes(data[off(va):off(va) + len(o)]) == n:
                data[off(va):off(va) + len(o)] = o
                n_hooks += 1
        data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = b"\x00" * CAVE_LIMIT
        open(DLL, "wb").write(data)
        n_ed = 0
        for path, _bk in editor_paths():
            ed = bytearray(open(path, "rb").read())
            o = ed_site(ed)
            if o is not None and ed[o] == ED_NEW:
                ed[o] = ED_OLD
                open(path, "wb").write(ed)
                n_ed += 1
        print("UNDO: restored %d DLL site(s) + %d editor byte(s), zeroed the cave. "
              "No backup touched." % (n_hooks, n_ed))
        return

    # --- pre-flight --------------------------------------------------------------------
    if cv["_end"] - CAVE_VA > CAVE_LIMIT:
        sys.exit("ERROR: cave overflows its %d-byte reservation (%d used)"
                 % (CAVE_LIMIT, cv["_end"] - CAVE_VA))
    if CAVE_VA + CAVE_LIMIT > CODE_ZERO_END:
        sys.exit("ERROR: cave past end of CODE")

    fresh = all(bytes(data[off(v):off(v) + len(o)]) == o for v, o, n, _ in edits)
    done = all(bytes(data[off(v):off(v) + len(o)]) == n for v, o, n, _ in edits)
    if not fresh and not done:
        sys.exit("ABORT: hook sites are in a mixed/foreign state -- inspect before proceeding.")
    if fresh:
        zone = bytes(data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT])
        if zone != b"\x00" * CAVE_LIMIT:
            sys.exit("ABORT: cave zone 0x%08X is not all-zero -- another feature owns it" % CAVE_VA)

    caves_ok = all(bytes(data[off(cv[k][0]):off(cv[k][0]) + len(cv[k][1])]) == cv[k][1]
                   for k in cave_keys(cv))
    def _ed_state(p):
        ed = bytearray(open(p, "rb").read())
        o = ed_site(ed)
        return o is not None and ed[o] == ED_NEW
    ed_done = all(_ed_state(p) for p, _b in editor_paths()) if P4_EDITOR_UNGREY else True
    if done and caves_ok and ed_done:
        print("Already applied and up to date -- nothing to do.")
        return

    if not args.apply:
        print("DRY RUN -- re-run with --apply to commit.")
        print("(Close %s first -- they lock these files. The root's VANILLA AoW.exe / "
              "AoWCompat.exe load the ROOT's packages and lock nothing here.)"
              % " / ".join(zigexe.ALL_EXES))
        return

    # --- write -------------------------------------------------------------------------
    # `fresh` = every DLL site still holds its vanilla bytes, which is the only state a snapshot
    # may be taken from. Reaching here with `done` instead means the DLL is already OUR output --
    # snapshotting that would put a patched file on disk under a name claiming to be the original.
    if not fresh:
        print("no DLL backup taken (AoWEPACK.dpl is already patched at these sites)")
    elif not os.path.exists(BAK):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BAK)
        print("backup -> %s" % BAK)

    payload = bytearray(CAVE_LIMIT)
    for k in cave_keys(cv):
        va, b = cv[k]
        payload[va - CAVE_VA: va - CAVE_VA + len(b)] = b
    data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = payload
    for va, o, n, lbl in edits:
        data[off(va):off(va) + len(o)] = n
    try:
        open(DLL, "wb").write(data)
    except PermissionError:
        sys.exit("ERROR: %s is locked. Close the AoW binaries and retry." % os.path.basename(DLL))
    print("AoWEPACK.dpl: %d site(s) hooked, cave written." % len(edits))

    if P4_EDITOR_UNGREY:
        for path, bk in editor_paths():
            ed = bytearray(open(path, "rb").read())
            o = ed_site(ed)
            if o is None:
                print("  WARN: %s -- gate signature not found (or not unique), skipped"
                      % os.path.basename(path))
                continue
            if ed[o] == ED_NEW:
                print("  %s: already patched." % os.path.basename(path))
                continue
            if ed[o] != ED_OLD:
                print("  WARN: %s -- foreign byte 0x%02x, skipped" % (os.path.basename(path), ed[o]))
                continue
            # Reached only when ed[o] == ED_OLD, i.e. this site is proved vanilla.
            if not os.path.exists(bk):
                os.makedirs(BACKUP_DIR, exist_ok=True)
                shutil.copy2(path, bk)
                print("  backup -> %s" % bk)
            ed[o] = ED_NEW
            try:
                open(path, "wb").write(ed)
            except PermissionError:
                sys.exit("ERROR: %s is locked. Close the editor and retry." % os.path.basename(path))
            print("  %s: itUse stat spinners un-greyed." % os.path.basename(path))

    print("\nAPPLIED. Revert with --undo (surgical) -- do NOT restore a .pre-* backup, it would "
          "wipe every feature layered on top.")
    if P4_EDITOR_UNGREY:
        print("⚠ The editor byte landed in the PATCH SOURCE. Now run:\n"
              "    python build_zigeditor.py --apply     # rebuilds Ziggurat\\AoWzEd.exe")


if __name__ == "__main__":
    main()
