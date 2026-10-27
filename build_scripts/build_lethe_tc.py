#!/usr/bin/env python
r"""
build_lethe_tc.py -- the AoWTCPCK half of Curse of Lethe (id 86).  AoWEPACK half: build_lethe.py.
Owner's design 2026-10-25 (05-spells-added.md, "Death/Water -- agreed design").

CURSE OF LETHE rides Geyser's class, as Pillar of Banefire does (SpellTypes 0x1E: the burst drawn at
  the target hex, then the spray), with no target unit, so no knock-back.
  - SpellTypes[86] = 0x1E.
  N  0x0040F0E9  NextStrike's per-id switch (9 B, after build_deathfire_tc.py's alias resume):
     86 -> Disease Cloud's case 0x68 ([fx+0x2C] = nil).
  P  0x00428280  the ranged preview's switch (9 B): 86 -> case 2, the 7-hex outline.
  A  0x00415C31  TCAI.CheckUnit's per-id switch (9 B): 86 -> Triple Fireball's case 0x75 (the
     radius-1 area search; the values come from build_lethe.py's VMT copy: 0 for a unit that
     cannot sleep, own units subtracted).
  G  0x00415E11  the end of that case's candidate loop (6 B): for spell 86, the units on the 7 hexes
     around the chosen centre that can sleep are counted, enemies minus own (GetSide); below 2 the
     path and area values are zeroed, so the AI does not cast it (the owner's "at least two more
     enemies than own units").
  L  0x0040C85E  TCAbRangedTE.Execute's landing dispatch (10 B, after build_deathfire_tc.py's land
     resume): for kind 0x1E, sub-kind 0x34 and spell 86, each live, enabled combat unit on the 7
     hexes around the target hex (the unit HS of its field) gets the spell's own CreateCA (VMT +0x78:
     the sleep filter and Resistance roll, build_lethe.py) and TCombat.ExecuteCombatAction, after
     System.RandSeed := TAoWHSMap.Random(map, $FFFFFF); both sides alike.  Then the spell's sound
     cue 1.  No 0x31003 message: walls, terrain and structures are untouched.
Strike count: 1 shot, so one burst.  The spray is Geyser's (build_deathfire_tc.py's falling spray is
Pillar's only).

RNG: P1 SYNCED, the bridge (each CA's raw HitRole follows a reseed from the synced map Random).
Sites: RNG_SITES.
Slot 0x0043D000-0x0043D7FF, exclusive.  PIC.  Surgical --undo.

Coupling: N, A and L hook build_deathfire_tc.py's resume addresses; they work with that script
applied or undone, but a later script on these addresses must chain.

    python build_scripts/build_lethe_tc.py            dry run + state
    python build_scripts/build_lethe_tc.py --apply
    python build_scripts/build_lethe_tc.py --undo
    python build_scripts/build_lethe_tc.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000
from aowepack_patch import asm, run
from piccave import pic

LETHE = 86
SLOT = (0x0043D000, 0x0043D800)
SPELLTYPES = 0x004672F4
ASLEEP, MAGIC_IMMUNITY, ANIMATED, RACE_UNDEAD, UT_MACHINE = 0x50, 0x06, 0x81, 0x0B, 2
MIN_NET = 2

GETXYZ, HPTOHX, CENTERHN = 0x00402DF4, 0x004022C4, 0x004022AC
GETMAPLEVEL, GETFIELD = 0x00401E64, 0x00401E54
GETSPELL, SFXPLAY, RANDOM = 0x004029B4, 0x004022F4, 0x0040298C
EXEC_CA, GETSIDE = 0x0040259C, 0x0040252C
VAR_CONTAINER, VAR_COMBATMAP, VAR_HSSET = 0x00469420, 0x0046C064, 0x0046E8D0
VAR_MAP, VAR_SEED = 0x0046E8D4, 0x0046DC08
UNIT_HS, L_W, L_H = 0x220104, 0x0C, 0x10
LANDING_DONE = 0x0040CAF2
# the six-byte jcc rel32 targets of the switches, read from the vanilla bytes
SITES = {   # name: (va, vanilla bytes)
    "n": (0x0040F0E9, "83f81e0f8735010000"),
    "p": (0x00428280, "83f81a0f8702020000"),
    "a": (0x00415C31, "83f81c0f878e080000"),
    "g": (0x00415E11, "8b45d48945f8"),
    "l": (0x0040C85E, "74112c020f8431020000"),
}
A = {}


def ja_target(name):
    va, orig = SITES[name]
    b = bytes.fromhex(orig)
    return va + 9 + struct.unpack_from("<i", b, 5)[0]


def c_switch(va, name, delta, case):
    """eax = id - delta at the hook; 86 -> case; then the displaced `cmp eax,imm / ja`."""
    site, orig = SITES[name]
    limit = bytes.fromhex(orig)[2]
    return asm(f"""
        cmp  eax, {(LETHE - delta) & 0xFFFFFFFF:#x}
        jne  s_go
        mov  eax, {case:#x}
    s_go:
        cmp  eax, {limit:#x}
        ja   {ja_target(name):#x}
        jmp  {site + 9:#x}
    """, va)


def c_sleeper(va):
    """eax = combat object -> eax 1 when it can sleep (build_lethe.py's filter, without IsClass:
    callers take it from a field's unit HS)."""
    return asm(f"""
        push ebx
        push esi
        mov  ebx, eax
        mov  edx, {MAGIC_IMMUNITY}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  k_no
        mov  eax, ebx
        mov  edx, {ASLEEP:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  k_no
        mov  esi, dword ptr [ebx + 0x4c]
        test esi, esi
        je   k_no
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xa4]
        cmp  al, {RACE_UNDEAD}
        je   k_no
        mov  eax, esi
        mov  edx, {ANIMATED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  k_no
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x114]
        cmp  al, {UT_MACHINE}
        je   k_no
        mov  eax, 1
        pop  esi
        pop  ebx
        ret
    k_no:
        xor  eax, eax
        pop  esi
        pop  ebx
        ret
    """, va)


def c_unit_at(va):
    """eax = x, edx = y -> eax = the live, enabled combat unit there, or 0.  ebx = anchor."""
    src = f"""
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        mov  eax, dword ptr [ebx + {{CONTAINER}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x10]
        xor  edx, edx
        call {GETMAPLEVEL:#x}
        test eax, eax
        je   u_no
        cmp  esi, dword ptr [eax + {L_W:#x}]
        jae  u_no
        cmp  edi, dword ptr [eax + {L_H:#x}]
        jae  u_no
        mov  edx, esi
        mov  ecx, edi
        call {GETFIELD:#x}
        test eax, eax
        je   u_no
        mov  edx, {UNIT_HS:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        je   u_no
        mov  eax, dword ptr [eax + 0x1c]
        test eax, eax
        je   u_no
        test byte ptr [eax + 0x47], 1
        jne  u_no
        push eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        pop  eax
        jne  u_out
    u_no:
        xor  eax, eax
    u_out:
        pop  edi
        pop  esi
        ret
    """
    # the anchor lives in the caller (ebx); fields resolve against it
    return src


def c_land(va):
    """[ebp-0x20] the effect, [ebp-4] the TE ([+0x10] the caster); scratch as build_deathfire_tc's
    and build_satchels_tc's landings use it: [ebp-0x28]/[ebp-0x2C] the centre, [ebp-0x14]/[ebp-0x18]
    a hex, [ebp-0x10] the spell, [ebp-0x24] the CreateCA address, then the CA, [ebp-0x38] the unit."""
    l_go = SITES["l"][0]
    b = bytes.fromhex(SITES["l"][1])
    je1 = l_go + 2 + b[1]
    je2 = l_go + 4 + 6 + struct.unpack_from("<i", b, 6)[0]
    src = f"""
        mov  eax, dword ptr [ebp - 0x20]
        cmp  byte ptr [eax + 0x34], 0x1e
        jne  l_orig
        cmp  dword ptr [eax + 0x14], 0x34
        jne  l_orig
        cmp  dword ptr [eax + 0x18], {LETHE}
        jne  l_orig
        push ebx
        push esi
        push edi
        {{ANC}}
        lea  eax, [ebp - 0x2c]
        push eax
        mov  eax, dword ptr [ebp - 0x20]
        mov  eax, dword ptr [eax + 0x1c]
        xor  edx, edx
        call {GETXYZ:#x}
        mov  eax, dword ptr [eax + 8]
        push eax
        mov  eax, dword ptr [ebp - 0x20]
        mov  eax, dword ptr [eax + 0x1c]
        xor  edx, edx
        call {GETXYZ:#x}
        mov  eax, dword ptr [eax + 4]
        lea  ecx, [ebp - 0x28]
        pop  edx
        call {HPTOHX:#x}
        mov  eax, dword ptr [ebx + {{HSSET}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x84]
        mov  edx, {LETHE}
        call {GETSPELL:#x}
        mov  dword ptr [ebp - 0x10], eax
        test eax, eax
        je   l_out
        xor  edi, edi
    l_hex:
        lea  eax, [ebp - 0x14]
        push eax
        lea  eax, [ebp - 0x18]
        push eax
        mov  ecx, edi
        mov  edx, dword ptr [ebp - 0x2c]
        mov  eax, dword ptr [ebp - 0x28]
        call {CENTERHN:#x}
        mov  eax, dword ptr [ebp - 0x14]
        mov  edx, dword ptr [ebp - 0x18]
        call l_unit
        test eax, eax
        je   l_skip
        mov  dword ptr [ebp - 0x38], eax
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax]
        mov  edx, 0xffffff
        call {RANDOM:#x}
        mov  edx, dword ptr [ebx + {{SEED}}]
        mov  dword ptr [edx], eax
        mov  eax, dword ptr [ebp - 0x10]
        mov  ecx, dword ptr [eax]
        mov  ecx, dword ptr [ecx + 0x78]
        mov  dword ptr [ebp - 0x24], ecx
        push 0
        mov  ecx, dword ptr [ebp - 0x38]
        mov  edx, dword ptr [ebp - 4]
        mov  edx, dword ptr [edx + 0x10]
        call dword ptr [ebp - 0x24]
        mov  dword ptr [ebp - 0x24], eax
        mov  edx, eax
        mov  eax, dword ptr [ebx + {{CONTAINER}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0xe4]
        call {EXEC_CA:#x}
        mov  eax, dword ptr [ebp - 0x24]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
    l_skip:
        inc  edi
        cmp  edi, 7
        jne  l_hex
        mov  eax, dword ptr [ebx + {{COMBATMAP}}]
        cmp  byte ptr [eax + 0x129], 0
        je   l_out
        mov  eax, dword ptr [ebp - 0x10]
        mov  eax, dword ptr [eax + 0x28]
        mov  edx, 1
        call {SFXPLAY:#x}
    l_out:
        pop  edi
        pop  esi
        pop  ebx
        jmp  {LANDING_DONE:#x}
    l_orig:
        mov  al, byte ptr [eax + 0x34]
        sub  al, 5
        je   {je1:#x}
        sub  al, 2
        je   {je2:#x}
        jmp  {l_go + 10:#x}
    l_unit:
    """ + c_unit_at(va)
    return pic(src, va, "ebx", {"CONTAINER": VAR_CONTAINER, "COMBATMAP": VAR_COMBATMAP,
                                "HSSET": VAR_HSSET, "MAP": VAR_MAP, "SEED": VAR_SEED})


def c_gate(va):
    """End of TCAI.CheckUnit's case 0x75 loop: [ebp-0x60] the spell id, [ebp+0x14] the caster,
    [ebp-0x2C]/[ebp-0x30] the chosen centre x/y, [ebp-0x58]/[ebp-0x64] the path and area values."""
    g_go = SITES["g"][0]
    src = f"""
        cmp  dword ptr [ebp - 0x60], {LETHE}
        jne  g_orig
        push ebx
        push esi
        push edi
        sub  esp, 8
        {{ANC}}
        xor  esi, esi
        xor  edi, edi
    g_hex:
        lea  eax, [esp + 4]
        push eax
        lea  eax, [esp + 4]
        push eax
        mov  ecx, edi
        mov  edx, dword ptr [ebp - 0x30]
        mov  eax, dword ptr [ebp - 0x2c]
        call {CENTERHN:#x}
        mov  eax, dword ptr [esp + 4]
        mov  edx, dword ptr [esp]
        call g_unit
        test eax, eax
        je   g_next
        push eax
        call {A['sleeper']:#x}
        test eax, eax
        pop  eax
        je   g_next
        call {GETSIDE:#x}
        push eax
        mov  eax, dword ptr [ebp + 0x14]
        call {GETSIDE:#x}
        pop  edx
        and  al, 0x7f
        and  dl, 0x7f
        cmp  al, dl
        je   g_own
        inc  esi
        jmp  g_next
    g_own:
        dec  esi
    g_next:
        inc  edi
        cmp  edi, 7
        jne  g_hex
        cmp  esi, {MIN_NET}
        jge  g_keep
        xor  eax, eax
        mov  dword ptr [ebp - 0x58], eax
        mov  dword ptr [ebp - 0x64], eax
    g_keep:
        add  esp, 8
        pop  edi
        pop  esi
        pop  ebx
    g_orig:
        mov  eax, dword ptr [ebp - 0x2c]
        mov  dword ptr [ebp - 8], eax
        jmp  {g_go + 6:#x}
    g_unit:
    """ + c_unit_at(va)
    return pic(src, va, "ebx", {"CONTAINER": VAR_CONTAINER})


BUILDERS = [
    ("n", lambda va: c_switch(va, "n", 0x64, 0x68 - 0x64)),
    ("p", lambda va: c_switch(va, "p", 0x68, 2)),
    ("a", lambda va: c_switch(va, "a", 0x64, 0x75 - 0x64)),
    ("sleeper", c_sleeper),
    ("g", c_gate),
    ("l", c_land),
]


def layout():
    for _ in range(2):
        va, blobs = SLOT[0], []
        for name, b in BUILDERS:
            A[name] = va
            blob = b(va)
            blobs.append(("cave_" + name, va, blob))
            va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    return blobs


def rng_sites(blobs):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    out = []
    for _n, va, blob in blobs:
        out += [i.address for i in md.disasm(blob, va) if i.mnemonic == "call" and i.op_str == "%#x" % RANDOM]
    return out


RNG_SITES = (0x0043D271,)


def main():
    blobs = layout()
    hooks = []
    for name, (va, orig) in SITES.items():
        orig = bytes.fromhex(orig)
        hooks.append((va, orig, b"\xE9" + struct.pack("<i", A[name] - (va + 5)) + b"\x90" * (len(orig) - 5)))
    hooks.append((SPELLTYPES + LETHE, b"\x00", b"\x1e"))
    from build_deathfire_tc import interior_jumps
    d = open(P.TARGET, "rb").read()
    bad = interior_jumps(d, [(va, va + len(bytes.fromhex(o))) for va, o in SITES.values()])
    if bad:
        sys.exit("ABORT: jumps into a hook's interior: " + ", ".join("%08X->%08X" % x for x in bad))
    found = rng_sites(blobs)
    if tuple(found) != RNG_SITES:
        sys.exit("ABORT: RNG_SITES are stale: %s" % " ".join("%08X" % a for a in found))
    print("  interior sweep: no branch lands inside a displaced range")
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    run("build_lethe_tc -- Curse of Lethe (AoWTCPCK)", hooks, blobs, SLOT, [])


if __name__ == "__main__":
    main()
