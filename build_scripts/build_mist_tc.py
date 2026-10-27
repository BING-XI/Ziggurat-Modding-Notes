#!/usr/bin/env python
r"""
build_mist_tc.py -- the AoWTCPCK half of Mist (id 89), the Air/Water dual tier-2 battle spell:
for the rest of the battle every enemy unit without True Seeing sees 3 hexes less, at least 1.
AoWEPACK half: build_mist.py.  Data: build_airwater_pfs.py.  Owner's design 2026-10-26
(05-spells-added.md, "Air/Water -- agreed design"): sight only -- the battle AI sees everything
and auto-resolve has no sight, so against the AI it changes nothing.

THE STATE  bit s of [TTacticalCombat+0x4D] = side s is misted.  TTacticalCombat's instance is 0x50
  (TCombat's 0x4C plus its byte +0x4C); +0x4D is alignment padding that no code reads or writes,
  and the object is created and zero-filled per battle, so the mark ends with the battle.  It is
  set in TE code, so every peer holds the same value.
mist_hit  eax = a combat object -> 1 when its side (GetSide & 0x7F, 0 or 1) is misted and it lacks
  True Seeing 0x29 (combat VMT +0xA8, item-aware, nil-safe).
ENTRY  0x0043CC40 (pinned) `jmp mist_adj`: eax = combat sight, edx = the unit -> eax.  A misted unit
  sees 3 less, at least 1; sight 0 or 1 is unchanged.  build_tactical_los.py's csight calls it while
  its first byte is E9, so fog, explore (sight + 8), re-explore and the step check all follow it.
  csight is read live and the fog signature hashes every seated unit's sight, so the view changes on
  the next frame.  Explored hexes stay explored.
THE CAST  SpellTypes[89] = 0x25 (High Prayer's instant class: no target; NewFrame spawns sparkles,
  then one kind-0x26 aura per kept unit).
  C   0x0040B44D  TCAbRangedTE.Execute phase 0's `call TSpell.CombatSpellCast` (the one call per cast,
      on every peer) -> call cave_cast: the call (mana, the combat-log cast line), then for spell 89
      the caster's opposing side gets its bit.  A second cast changes nothing.
  F1  0x0042DD33  the sparkle loop's `call GetObjects` -> call cave_f1: for spell 89 ([fx+0x14] =
      0x34, [fx+0x18] = 89) the cave keeps a misted unit (0x0042DD4A) and skips the rest
      (0x0042DE2C) itself, so the loop never reaches build_deathfire_tc.py's filter at 0x0042DD38
      (which reads [fx+0x2C], nil for 89).
  F2  0x0042DECA  the aura loop's `call GetObjects` -> call cave_f2: for spell 89 every unit is
      skipped (0x0042DFC7): no aura lands, so Mist creates no CA.
  The battle AI never casts it: TCAI.CheckUnit sends 89 to its default case and build_mist.py's
  value overrides are 0.

RNG: none added (the sparkle loop's own RandInt jitter is display only, as for High Prayer).
Slot 0x0043CC40-0x0043CFFF, exclusive (entry pinned at its start).  PIC.  Surgical --undo.

    python build_scripts/build_mist_tc.py            dry run + state
    python build_scripts/build_mist_tc.py --apply
    python build_scripts/build_mist_tc.py --undo
    python build_scripts/build_mist_tc.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000
from aowepack_patch import asm, run

MIST = 89
TRUE_SEEING, CUT = 0x29, 3
MARK = 0x4D                                 # [TTacticalCombat + 0x4D]
SLOT = (0x0043CC40, 0x0043D000)
ENTRY = SLOT[0]
SPELLTYPES, CLASS_INSTANT = 0x004672F4, 0x25
GETSIDE, GETOBJECTS, SPELLCAST = 0x0040252C, 0x00402634, 0x004029AC
SITES = {   # name: (va, vanilla call target)
    "cast": (0x0040B44D, SPELLCAST),
    "f1":   (0x0042DD33, GETOBJECTS),
    "f2":   (0x0042DECA, GETOBJECTS),
}
F1_KEEP, F1_SKIP, F2_SKIP = 0x0042DD4A, 0x0042DE2C, 0x0042DFC7
A = {}


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def c_entry(va):
    return b"\xE9" + struct.pack("<i", A["adj"] - (va + 5))      # always the E9 form: csight tests it


def c_hit(va):
    return asm(f"""
        push ebx
        mov  ebx, eax
        test ebx, ebx
        je   h_no
        mov  eax, dword ptr [ebx + 8]
        test eax, eax
        je   h_no
        movzx ecx, byte ptr [eax + {MARK:#x}]
        test ecx, ecx
        je   h_no
        push ecx
        mov  eax, ebx
        call {GETSIDE:#x}
        pop  ecx
        and  eax, 0x7f
        cmp  eax, 1
        ja   h_no
        bt   ecx, eax
        jnc  h_no
        mov  eax, ebx
        mov  edx, {TRUE_SEEING:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  h_no
        mov  eax, 1
        pop  ebx
        ret
    h_no:
        xor  eax, eax
        pop  ebx
        ret
    """, va)


def c_adj(va):
    """eax = sight, edx = the unit -> eax; keeps ebx/esi/edi/ebp."""
    return asm(f"""
        cmp  eax, 1
        jle  a_out
        push esi
        mov  esi, eax
        mov  eax, edx
        call {A['hit']:#x}
        test eax, eax
        mov  eax, esi
        pop  esi
        je   a_out
        sub  eax, {CUT}
        cmp  eax, 1
        jge  a_out
        mov  eax, 1
    a_out:
        ret
    """, va)


def c_cast(va):
    """Replaces `call TSpell.CombatSpellCast` (eax = the spell, edx = the caster); [ebp-4] = the TE."""
    return asm(f"""
        call {SPELLCAST:#x}
        mov  eax, dword ptr [ebp - 4]
        cmp  dword ptr [eax + 0x18], {MIST}
        jne  c_out
        push ebx
        mov  ebx, dword ptr [eax + 0x10]
        test ebx, ebx
        je   c_pop
        mov  eax, ebx
        call {GETSIDE:#x}
        and  eax, 0x7f
        cmp  eax, 1
        ja   c_pop
        xor  eax, 1
        mov  ecx, eax
        mov  edx, 1
        shl  edx, cl
        mov  eax, dword ptr [ebx + 8]
        test eax, eax
        je   c_pop
        or   byte ptr [eax + {MARK:#x}], dl
    c_pop:
        pop  ebx
    c_out:
        ret
    """, va)


def c_f1(va):
    """Replaces the sparkle loop's `call GetObjects`; [ebp-8] = the effect."""
    return asm(f"""
        call {GETOBJECTS:#x}
        mov  edx, dword ptr [ebp - 8]
        cmp  dword ptr [edx + 0x14], 0x34
        jne  f_ret
        cmp  dword ptr [edx + 0x18], {MIST}
        jne  f_ret
        call {A['hit']:#x}
        test eax, eax
        lea  esp, [esp + 4]
        jne  {F1_KEEP:#x}
        jmp  {F1_SKIP:#x}
    f_ret:
        ret
    """, va)


def c_f2(va):
    """Replaces the aura loop's `call GetObjects`; [ebp-8] = the effect."""
    return asm(f"""
        call {GETOBJECTS:#x}
        mov  edx, dword ptr [ebp - 8]
        cmp  dword ptr [edx + 0x14], 0x34
        jne  g_ret
        cmp  dword ptr [edx + 0x18], {MIST}
        jne  g_ret
        lea  esp, [esp + 4]
        jmp  {F2_SKIP:#x}
    g_ret:
        ret
    """, va)


BUILDERS = [("entry", c_entry), ("hit", c_hit), ("adj", c_adj), ("cast", c_cast), ("f1", c_f1),
            ("f2", c_f2)]


def layout():
    for name, _b in BUILDERS:
        A.setdefault(name, SLOT[0] + 0x200)
    for _ in range(3):
        va, blobs = SLOT[0], []
        for name, b in BUILDERS:
            A[name] = va
            blob = b(va)
            if name == "entry":
                assert len(blob) == 5 and blob[0] == 0xE9, "the entry must be a 5-byte jmp"
            blobs.append(("cave_" + name, va, blob))
            va = (va + len(blob) + 15) & ~15
    assert A["entry"] == ENTRY and va <= SLOT[1], "layout"
    return blobs


def checks(d):
    rb = lambda va, n: bytes(d[P.va2off(d, va):P.va2off(d, va) + n])
    for va, want, what in ((0x0040B447, "8b55fc8b5210", "phase 0's `mov edx,[ebp-4] / mov edx,[edx+0x10]`"),
                           (0x0040B452, "a120944600", "the load after CombatSpellCast"),
                           (F1_KEEP, "b21f", "the sparkle loop's keep path"),
                           (0x0042DEE1, "b226", "the aura loop's keep path")):
        if rb(va, len(want) // 2).hex() != want:
            sys.exit("ABORT: %s is not at %08X" % (what, va))


def main():
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d)
    hooks = [(va, call_to(va, tgt), call_to(va, A[n])) for n, (va, tgt) in SITES.items()]
    hooks.append((SPELLTYPES + MIST, b"\x00", bytes([CLASS_INSTANT])))
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    run("build_mist_tc -- Mist (AoWTCPCK)", hooks, blobs, SLOT, [])


if __name__ == "__main__":
    main()
