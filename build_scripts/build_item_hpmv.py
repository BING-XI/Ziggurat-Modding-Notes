#!/usr/bin/env python3
r"""
build_item_hpmv.py -- items grant bonus HIT POINTS and MOVEMENT, exactly as they already grant
ATK / DEF / DAM / RES.

Background + full reverse-engineering: `Modding Resources/Zig notes/Investigation_Items.md`
FEATURE 2 (and its shared foundation SS0.4 / SS0.5 / SS0.7). Read the OVERFLOW note below before
touching any arithmetic here.

================================================================================
WHAT VANILLA DOES, AND WHAT IS MISSING
================================================================================
A hero's four combat stats are additive functions that each add an item aggregate:

    THero.GetAttack @0x55788360 = res+0x24 + Sum(ability terms) + THeroItems.GetAttack + hero+0x6a

`THeroItems.GetAttack @0x55786354` and its three siblings each loop the equipped item list and sum
ONE byte off each item: +0x46 ATK, +0x47 DEF, +0x48 DAM, +0x49 RES.

`THero.GetHits @0x5578859C` and `THero.GetMoves @0x557885C0` have the SAME additive shape --
`res+0x27 + hero+0x6d` and `res+0x28 + hero+0x6e` -- but no item term, and `THeroItems` has no
HP/MV aggregator at all. That is the whole of the gap: HP/MV are not hardcoded and not resolved
once, they simply never ask the items.

This script adds the missing term. It does NOT touch the clamps -- `build_hero_clamps.py` owns
those (HITS ceiling 100 / floor 2; MOVES ceiling 80 / floor 1) and the caves here deliberately
re-enter vanilla just above them so both features compose and either can be undone alone.

================================================================================
WHAT THIS SCRIPT CHANGES  (3 hooks + 5 caves, AoWEPACK.dpl only)
================================================================================
STORAGE   item+0x4A = HP bonus, item+0x4B = MV bonus. Both are FREE zero-init bytes inside the
          existing 0x4C-byte TItem allocation -- no instance growth, and every existing item and
          save defaults to 0. (Re-verified 2026-08-31 with `re_tools/fieldrefs.py 0x4a 0x4b
          --size byte --validate 0x46`: the only hits belong to TUnitSelectionControl /
          TFlagControl and to misaligned decodes. TItem instsize is 0x4C = [VMT-0x1C].)
          Values are SIGNED (-128..127), so a cursed item can carry a penalty. That matches how
          the engine ultimately reads the total (`movsx` before the clamp).

H1/C1-C2  `THero.GetHits @0x5578859C` -> cave_gethits -> agg_hits (sums item+0x4A)
H2/C3-C4  `THero.GetMoves @0x557885C0` -> cave_getmoves -> agg_moves (sums item+0x4B)
          Each hook displaces 6 bytes at the function head (`mov edx,[eax+0x40]` +
          `mov dl,[edx+0x27]`), pads 1, and the cave re-enters vanilla at the `movsx edx,al`
          just before the clamp pair -- 0x557885A7 for Hits, 0x557885CB for Moves.

H3/C5     `TItem.ReadWrite @0x557945C8` -> cave_readwrite, adding tags 0x17 -> +0x4A and
          0x18 -> +0x4B through the byte accessor `stream.vtable[0x30]`, the same one tags
          0x0B..0x0E use for the four combat bytes. Tagged-property format => OLD SAVES LOAD
          FINE (an absent tag leaves the field at its zero-init value).

The two aggregators walk the worn list AND the `item+0x34 == 6` (itUse) backpack list, matching
what `build_useitems.py` (applied) already did to the four stat aggregators. Set P_BACKPACK=False
for vanilla's worn-only rule.

================================================================================
!! THE OVERFLOW TRAP -- the reason the caves are 32-bit
================================================================================
Vanilla computes `add dl, [eax+0x6d]` -- an EIGHT-BIT add -- and only afterwards sign-extends and
compares against the clamp. `hero+0x6d` is the skill-point-purchased HP upgrade
(`THero.SetUnitHits @0x557878A0`), and the level-up screen lets it grow until GetHits reaches its
ceiling. So `base + hero+0x6d` sits EXACTLY AT the ceiling for a maxed hero.

At the 2026-08-24 ceiling of 120 an item bonus of just +8 pushed the byte to 128, wrapped it to
-128, tripped the FLOOR clamp and returned 2 HP -- silently, and only on high-level heroes. The
2026-08-31 ruling lowered the ceiling to 100, which widens the margin to 27 but does not remove
the class of defect.

=> Both getter caves recompute the whole sum in 32-bit registers (movzx base, movzx purchased,
   movsx each item byte, add as dwords) and saturate to [-128, 127] before handing AL back to
   vanilla's clamp. Do not "simplify" this back into byte arithmetic.
   Same defect class as `build_medal_hpmv.py` v2->v3 and the DAM/HP byte-widening lesson: a clamp
   is a STRICTER consumer than the byte store in front of it.

================================================================================
FINDINGS THAT MADE THE HOOK SITES SAFE (both cost real time -- do not re-derive)
================================================================================
* `TItem.ReadWrite`'s TAIL IS NOT HOOKABLE. At 0x55794726 the function does `mov ebx,[eax]`,
  overwriting the item pointer with the stream vtable, so at the `pop edi/esi/ebx/ret` at
  0x5579472B **EBX is the item on one path and a vtable pointer on the other** (the `test al,4`
  at 0x55794718 skips tag 0x16 entirely). Hooking there would write our two fields through a
  garbage base pointer on one of the two paths. We hook at 0x55794712 instead, where EBX is
  still the item on BOTH paths, and replay the displaced `mov eax,esi / mov edx,[eax] / call
  [edx]` inside the cave.
* THE .PFS / SAVE DIRECTORY DOES NOT REQUIRE ASCENDING TAG KEYS. Hooking before tag 0x16 means
  our 0x17/0x18 are emitted out of order. Measured across the shipped data: **50 of 50
  HEROES.PFS records already have non-ascending key order**, plus 2 of 83 in ITEMS.PFS. The
  reader is a keyed scan, not a binary search. (This also means our fields are written on both
  branches of the `test al,4` gate -- correct, because they are library data like +0x46..+0x49,
  which are likewise ungated.)

================================================================================
SAFETY
================================================================================
- Every cave is POSITION-INDEPENDENT: register-relative operands only, plus `call`/`jmp` rel32
  within AoWEPACK.dpl. No absolute memory references, so the DPL's runtime rebase is irrelevant.
- No displaced byte range carries a `.reloc` entry (0 of 63,883 relocation targets fall inside
  0x5578859C..0x557885E2 or 0x55794712..0x55794718; the script re-checks at build time).
- Verify-before-write: every hook site must hold either its known-vanilla bytes or this mod's
  bytes, and the whole cave span must be zero-or-ours. Anything else aborts with nothing written.
- `--undo` is SURGICAL: it restores the three hook sites and zeroes only this script's cave span.
  It touches no backup, so it survives any amount of later layering.
- AoW.exe / AoWCompat.exe / AoWTCPCK.dpl need NO patch. `TCombatUnit.GetHits @0x5572504C` and
  `GetMoves @0x55724FE0` read `[src+0x4c].vtable[0xD0]/[0xD4]`, and AoWTCPCK makes 74 virtual
  calls through `TCombatUnit` VMT +0x84 -- so the strategic card, tactical combat AND auto-resolve
  all pick this up for free. `THero` and `TLeader` share both getter slots, so heroes and the
  wizard are both covered.

NOT DONE HERE (deliberate, see the doc):
- No editor UI. Values are authored straight into `Release/ITEMS.PFS` tags 0x17/0x18.
- `TItem.SetItemType @0x5579457C` zeroes +0x46..+0x49 on a type change but is NOT extended to
  zero +0x4A/+0x4B -- changing an item's type keeps its HP/MV bonus rather than silently wiping
  a typed-in value.
- The `TItemBanner` info panel (AoW.exe) still lists only the four combat bonuses; the hero's own
  card shows the new HP/MV totals immediately because the getters are patched at source.

Backup: AoWEPACK.dpl.pre-itemhpmv
Dry-run by default; --apply to commit; --undo to remove; --dis to disassemble the caves.
"""

import argparse
import os
import struct
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_statdouble import kill_aow  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-itemhpmv")

VA_BASE = 0x55700C00           # AoWEPACK.dpl CODE: VA - VA_BASE == file offset
IMAGE_BASE = 0x55700000

# ---- feature switch -------------------------------------------------------------------------
P_BACKPACK = True              # also sum itUse backpack items (matches applied build_useitems.py)
# ---------------------------------------------------------------------------------------------

HP_OFF, MV_OFF = 0x4A, 0x4B    # the two free TItem bytes
HP_TAG, MV_TAG = 0x17, 0x18    # TItem.ReadWrite's last tag is 0x16 -> these are free
ITUSE = 6                      # item+0x34 == itUse
INV_OFF = 0x74                 # hero+0x74 = THeroInventory
ITEMS_OFF = 0x70               # hero+0x70 = THeroItems

# ---- hook sites: (VA, vanilla bytes, resume VA, label) --------------------------------------
H_HITS = (0x5578859C, bytes.fromhex("8b50408a5227"), 0x557885A7, "THero.GetHits")
H_MOVES = (0x557885C0, bytes.fromhex("8b50408a5228"), 0x557885CB, "THero.GetMoves")
H_RW = (0x55794712, bytes.fromhex("8bc68b10ff12"), 0x55794718, "TItem.ReadWrite")
HOOKS = [H_HITS, H_MOVES, H_RW]

# ---- cave layout ----------------------------------------------------------------------------
CAVE_VA = 0x5582B000
CAVE_END = 0x5582B200          # asserted zero-or-ours across the whole span
C_AGG_HP = 0x5582B000
C_AGG_MV = 0x5582B0A0
C_GETHITS = 0x5582B140
C_GETMOVES = 0x5582B180
C_READWRITE = 0x5582B1C0


def off(va):
    return va - VA_BASE


def jmp_to(src, dst):
    return b"\xE9" + struct.pack("<i", dst - (src + 5))


# =============================================================================================
# cave construction
# =============================================================================================
def _walk_loop(tag, filtered, item_off):
    """Loop a TItemList held in EBP, adding each item's signed byte at `item_off` into EBX.

    Shape cloned from the vanilla aggregator THeroItems.GetAttack @0x55786354 (and from
    build_useitems.py's replacement cave at 0x55815080, which is the proof that EBX/ESI/EDI/EBP
    survive the per-list virtual call). The ONE deliberate difference from vanilla: vanilla does
    `add bl,[eax+0x46]` -- an 8-bit accumulate -- and we accumulate 32-bit, so a stack of items
    cannot wrap the running total.
    """
    flt = ""
    if filtered:
        flt = "cmp byte ptr [eax + 0x%X], %d\n jne %s_next\n" % (0x34, ITUSE, tag)
    return """
        mov  edx, [ebp]
        mov  eax, ebp
        call dword ptr [edx + 0x54]      /* GetCount */
        mov  esi, eax
        xor  edi, edi
    %(t)s_loop:
        cmp  edi, esi
        jge  %(t)s_end
        mov  eax, [ebp + 8]
        test eax, eax
        je   %(t)s_end
        mov  eax, [eax + 4]
        test eax, eax
        je   %(t)s_end
        mov  eax, [eax + edi*4]
        test eax, eax
        je   %(t)s_next
        %(flt)s
        movsx edx, byte ptr [eax + 0x%(off)X]
        add  ebx, edx
    %(t)s_next:
        inc  edi
        jmp  %(t)s_loop
    %(t)s_end:
    """ % {"t": tag, "flt": flt, "off": item_off}


def _aggregator(tag, item_off):
    """EAX = THeroItems (hero+0x70). Returns the signed 32-bit sum in EAX.

    Unlike the vanilla aggregators this does NOT mask to a byte -- the only callers are our two
    getter caves, which saturate the grand total themselves.
    """
    backpack = ""
    if P_BACKPACK:
        backpack = """
        mov  eax, [esp]                  /* [esp] = this (THeroItems) */
        mov  eax, [eax + 4]              /* THeroItems+4 = the owning hero */
        test eax, eax
        je   %(t)s_done
        mov  eax, [eax + 0x%(inv)X]      /* hero+0x74 = THeroInventory */
        test eax, eax
        je   %(t)s_done
        mov  ebp, eax
        %(loop)s
        """ % {"t": tag, "inv": INV_OFF,
               "loop": _walk_loop(tag + "b", True, item_off)}
    return """
        push ebx
        push esi
        push edi
        push ebp
        push eax
        xor  ebx, ebx
        mov  ebp, eax
        %(worn)s
        %(backpack)s
    %(t)s_done:
        mov  eax, ebx
        pop  ecx
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """ % {"t": tag, "worn": _walk_loop(tag + "a", False, item_off),
           "backpack": backpack}


def _getter(tag, base_off, hero_off, agg_va, resume_va):
    """EAX = hero on entry. Leaves the pre-clamp total in AL and re-enters vanilla at `resume_va`.

    !! 32-BIT THROUGHOUT -- see the overflow note in the module docstring. `base + hero_off`
    already reaches the clamp ceiling on a maxed hero, so adding an item term in 8-bit wraps.
    """
    return """
        push ebx
        push ecx
        mov  ebx, eax                    /* ebx = hero */
        mov  edx, [ebx + 0x40]           /* edx = unit-resource flyweight */
        movzx eax, byte ptr [edx + 0x%(base)X]
        movzx ecx, byte ptr [ebx + 0x%(hero)X]
        add  eax, ecx
        push eax
        mov  eax, [ebx + 0x%(items)X]    /* THeroItems; null on a hero mid-construction */
        test eax, eax
        je   %(t)s_noitems
        call 0x%(agg)X
        jmp  %(t)s_merge
    %(t)s_noitems:
        xor  eax, eax
    %(t)s_merge:
        pop  ecx
        add  eax, ecx
        cmp  eax, 127
        jle  %(t)s_lo
        mov  eax, 127
    %(t)s_lo:
        cmp  eax, -128
        jge  %(t)s_ok
        mov  eax, -128
    %(t)s_ok:
        pop  ecx
        pop  ebx
        jmp  0x%(resume)X
    """ % {"t": tag, "base": base_off, "hero": hero_off, "items": ITEMS_OFF,
           "agg": agg_va, "resume": resume_va}


def _readwrite(resume_va):
    """EBX = item, ESI = stream. Emits tags 0x17/0x18 then replays the displaced instructions.

    EDI is scratch here (the function reloads it before every accessor call and restores it from
    the stack at the epilogue).
    """
    field = """
        lea  edx, [ebx + 0x%X]
        mov  ecx, 0x%X
        mov  eax, esi
        mov  edi, [eax]
        call dword ptr [edi + 0x30]      /* the byte accessor -- same slot tags 0x0B..0x0E use */
    """
    return (field % (HP_OFF, HP_TAG)) + (field % (MV_OFF, MV_TAG)) + """
        mov  eax, esi                    /* replayed displaced run */
        mov  edx, [eax]
        call dword ptr [edx]
        jmp  0x%X
    """ % resume_va


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    out = {}

    def emit(key, va, src, limit):
        blob = bytes(ks.asm(src, va)[0])
        if len(blob) > limit:
            sys.exit("ABORT: cave %s is %d bytes, over its %d-byte slot." % (key, len(blob), limit))
        out[key] = (va, blob)

    emit("agg_hp", C_AGG_HP, _aggregator("agghp", HP_OFF), C_AGG_MV - C_AGG_HP)
    emit("agg_mv", C_AGG_MV, _aggregator("aggmv", MV_OFF), C_GETHITS - C_AGG_MV)
    emit("gethits", C_GETHITS, _getter("gh", 0x27, 0x6D, C_AGG_HP, H_HITS[2]),
         C_GETMOVES - C_GETHITS)
    emit("getmoves", C_GETMOVES, _getter("gm", 0x28, 0x6E, C_AGG_MV, H_MOVES[2]),
         C_READWRITE - C_GETMOVES)
    emit("readwrite", C_READWRITE, _readwrite(H_RW[2]), CAVE_END - C_READWRITE)
    return out


def hook_bytes():
    """The 3 hook-site patches: rel32 jmp into the cave, NOP-padded to the displaced length."""
    return {
        H_HITS[0]: jmp_to(H_HITS[0], C_GETHITS).ljust(len(H_HITS[1]), b"\x90"),
        H_MOVES[0]: jmp_to(H_MOVES[0], C_GETMOVES).ljust(len(H_MOVES[1]), b"\x90"),
        H_RW[0]: jmp_to(H_RW[0], C_READWRITE).ljust(len(H_RW[1]), b"\x90"),
    }


# =============================================================================================
# safety checks
# =============================================================================================
def reloc_targets(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    optsz = struct.unpack_from("<H", d, pe + 0x14)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    rva, size = struct.unpack_from("<II", d, pe + 0x18 + 0x60 + 5 * 8)
    secs = []
    for i in range(nsec):
        o = pe + 0x18 + optsz + i * 40
        vs, va, rs, pr = struct.unpack_from("<IIII", d, o + 8)
        secs.append((va, max(vs, rs), pr))

    def r2o(r):
        for va, sz, pr in secs:
            if va <= r < va + sz:
                return pr + (r - va)
        return None

    p, end, out = r2o(rva), r2o(rva) + size, set()
    while p < end:
        page, blk = struct.unpack_from("<II", d, p)
        if blk == 0:
            break
        for k in range((blk - 8) // 2):
            e = struct.unpack_from("<H", d, p + 8 + k * 2)[0]
            if e >> 12:
                out.add(IMAGE_BASE + page + (e & 0xFFF))
        p += blk
    return out


def check_relocs(d):
    tg = reloc_targets(d)
    bad = []
    for va, van, _res, name in HOOKS:
        hit = [t for t in tg if va <= t < va + len(van)]
        if hit:
            bad.append("%s @%08X: %s" % (name, va, [hex(h) for h in hit]))
    if bad:
        sys.exit("ABORT: a displaced range carries .reloc entries -- " + "; ".join(bad))


def state_of(d, caves, hooks):
    """-> 'vanilla' | 'ours' | 'mixed'."""
    v = all(bytes(d[off(va):off(va) + len(van)]) == van for va, van, _r, _n in HOOKS)
    o = all(bytes(d[off(va):off(va) + len(b)]) == b for va, b in hooks.items())
    o = o and all(bytes(d[off(va):off(va) + len(b)]) == b for va, b in caves.values())
    if v and not o:
        return "vanilla"
    if o and not v:
        return "ours"
    return "mixed"


def cave_zone_ok(d, caves):
    """Every byte of the cave span must be zero, or exactly one of our blobs."""
    span = bytearray(d[off(CAVE_VA):off(CAVE_END)])
    for va, b in caves.values():
        i = va - CAVE_VA
        span[i:i + len(b)] = b"\x00" * len(b)
    return all(x == 0 for x in span)


# =============================================================================================
def main():
    ap = argparse.ArgumentParser(description="items grant bonus HP and Movement")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true", help="disassemble the caves and exit")
    a = ap.parse_args()

    if not os.path.exists(DLL):
        sys.exit("ERROR: not found: %s" % DLL)
    caves = build()
    hooks = hook_bytes()

    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for key, (va, blob) in caves.items():
            print("\n==== %s @ %08X (%d bytes) ====" % (key, va, len(blob)))
            for ins in md.disasm(blob, va):
                print("  %08X  %-10s %s" % (ins.address, ins.mnemonic, ins.op_str))
        return

    d = bytearray(open(DLL, "rb").read())
    check_relocs(d)

    print("build_item_hpmv -- items grant bonus HP (item+0x%02X) and MV (item+0x%02X)"
          % (HP_OFF, MV_OFF))
    print("backpack itUse items counted: %s\n" % P_BACKPACK)

    st = state_of(d, caves, hooks)
    for va, van, res, name in HOOKS:
        cur = bytes(d[off(va):off(va) + len(van)])
        tag = "vanilla" if cur == van else ("ours" if cur == hooks[va] else "FOREIGN")
        print("  hook %-16s %08X  %-18s %-7s  resume %08X"
              % (name, va, cur.hex(" "), tag, res))
    for key, (va, blob) in sorted(caves.items(), key=lambda kv: kv[1][0]):
        cur = bytes(d[off(va):off(va) + len(blob)])
        zero = all(x == 0 for x in cur)
        print("  cave %-16s %08X  %3d bytes  %s"
              % (key, va, len(blob), "installed" if cur == blob else ("free" if zero else "FOREIGN")))
    print("\nstate: %s" % st)

    if st == "mixed":
        sys.exit("\nABORT: hook sites and caves disagree (partially applied, or another feature "
                 "owns a site). Nothing written.")
    if not cave_zone_ok(d, caves):
        sys.exit("\nABORT: %08X..%08X holds bytes that are neither zero nor ours -- another "
                 "feature has taken this cave span. Nothing written." % (CAVE_VA, CAVE_END))

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written; --apply to install, --dis to read the caves)")
        return

    want = "vanilla" if a.undo else "ours"
    if st == want:
        print("\nalready %s -- nothing to do (idempotent)." % want)
        return

    kill_aow()
    if not a.undo and not os.path.exists(BAK):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BAK)
        print("  backup -> %s" % os.path.basename(BAK))

    if a.undo:
        for va, van, _r, _n in HOOKS:
            d[off(va):off(va) + len(van)] = van
        d[off(CAVE_VA):off(CAVE_END)] = b"\x00" * (CAVE_END - CAVE_VA)
        print("\nUNDONE -- 3 hook sites restored, cave span %08X..%08X zeroed."
              % (CAVE_VA, CAVE_END))
    else:
        for va, blob in caves.values():
            d[off(va):off(va) + len(blob)] = blob
        for va, blob in hooks.items():
            d[off(va):off(va) + len(blob)] = blob
        print("\nAPPLIED -- 3 hooks + %d caves written." % len(caves))
        print("Authoring: write tag 0x%02X (HP) / 0x%02X (MV) into Release/ITEMS.PFS records."
              % (HP_TAG, MV_TAG))

    open(DLL, "wb").write(bytes(d))


if __name__ == "__main__":
    main()
