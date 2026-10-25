#!/usr/bin/env python
r"""
build_deathfire_tc.py -- the AoWTCPCK half of Taint the Flame (id 80) and Pillar of Banefire (id 81).
AoWEPACK half: build_deathfire_combat.py.  Owner's design: 05-spells-added.md, "Death/Fire".

TAINT THE FLAME rides High Prayer's class (SpellTypes 0x25: instant, no target; NewFrame kind 0x25
  spawns sparkles, then one kind-0x26 effect per unit, whose landing applies the spell's CA).
  - SpellTypes[80] = 0x25.
  - NextStrike's per-id table (0x0040F0E3) maps 80 to High Prayer's case 0x66 (puts the caster in
    [fx+0x2C]; an unmapped id leaves it nil and faults at 0x0042DD41).
  - The two per-unit spawn loops keep only units on the caster's side (0x0042DD38 sparkles,
    0x0042DECF auras); for Taint they keep every unit, either side, holding Burning 0x7F, Living
    Flame 0x52 or its enchantment 0xA3 (combat VMT +0xA8).  The loops already skip non-units.
  - TCAI.CheckUnit's per-id case (0x00415C2B) maps 80 to Sacred Wrath's (0x7D: EvalAll, enemies
    minus own side).  build_deathfire_combat.py's VMT copy makes non-qualifiers worth 0.
PILLAR OF BANEFIRE rides Geyser's class (SpellTypes 0x1E: the burst drawn at the target hex for 5
  ticks, then looped; 100 ticks of spray particles), with no target unit, so no knock-back.
  - SpellTypes[81] = 0x1E; NextStrike maps 81 to Disease Cloud's case 0x68 ([fx+0x2C] = nil).
  - The strike count is forced to 1 (0x0040B5F2): one burst, not one per shot.
  - The landing dispatch (0x0040C856), for kind 0x1E and spell 81, sends Triple Fireball's area
    message 0x31003 TWICE to each of the 19 hexes within radius 2 (two strikes), carrying the spell
    id at msg+0xC and the marker 'BANE' at msg+0x10; then plays the spell's sound cue 1.
  - The four 0x31003 handlers' `mov edx,0x75` (unit 0x00421001, wall 0x00405F06, terrain
    0x00410404, structure 0x00432CC7) become `call cave_hid`: the marked id, else 0x75.  So units,
    walls, gates and structures are hit as by Triple Fireball, with Pillar's own CA / combat info.
  - The spray (0x0042E2C4) starts each Pillar particle at its arc's peak (z = vz^2, gravity 0.5)
    with vz = 0: it only falls, spreading out over the area.  Geyser is unchanged.
  - TCAI.CheckUnit maps 81 to Triple Fireball's case 0x75 (radius-1 area scoring); the ranged
    preview (0x0042827A) maps 81 to Ooze's 0x7C (19-hex outline).
Randomness: none added (manual combat reseeds from the synced map Random before every CA).
Slot 0x0043E800-0x0043EFFF, exclusive.  PIC (the package rebases).  Surgical --undo.

    python build_scripts/build_deathfire_tc.py            dry run + state
    python build_scripts/build_deathfire_tc.py --apply
    python build_scripts/build_deathfire_tc.py --undo
    python build_scripts/build_deathfire_tc.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
import aowepack_patch as P
P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000
from aowepack_patch import asm, run
from piccave import pic

TAINT, PILLAR = 80, 81
MARKER = 0x454E4142                      # 'BANE'
SLOT = (0x0043E800, 0x0043F000)
SPELLTYPES = 0x004672F4
BURNING, LIVING_FLAME, LIVING_FLAME_ENCH = 0x7F, 0x52, 0xA3

# AoWTCPCK thunks / data (preferred VAs; data reached PIC)
GETXYZ, HPTOHX, CENTERHN = 0x00402DF4, 0x004022C4, 0x004022AC
GETMAPLEVEL, GETFIELD, SENDMSG = 0x00401E64, 0x00401E54, 0x00401DDC
GETSPELL, SFXPLAY = 0x004029B4, 0x004022F4
VAR_CONTAINER, VAR_COMBATMAP, VAR_HSSET = 0x00469420, 0x0046C064, 0x0046E8D0

SITES = {   # name: (va, original bytes, resume va)
    "alias":   (0x0040F0E3, "8b401883c09c", 0x0040F0E9),
    "ai":      (0x00415C2B, "8b45a083c09c", 0x00415C31),
    "preview": (0x0042827A, "8b403883c098", 0x00428280),
    "strike":  (0x0040B5F2, "0fbe45d08b55fc894228", 0x0040B5FC),
    "land":    (0x0040C856, "8b45e08a40342c05", 0x0040C85E),
    "filt1":   (0x0042DD38, "8a40458b55f88b522c3a4245", 0x0042DD44),
    "filt2":   (0x0042DECF, "8a40458b55f88b522c3a4245", 0x0042DEDB),
}
HID_SITES = [0x00421001, 0x00405F06, 0x00410404, 0x00432CC7]
SPRAY = 0x0042E2C4
LANDING_DONE = 0x0040CAF2
A = {}


def jmp(src, dst):
    return b"\xE9" + struct.pack("<i", dst - (src + 5))


def call(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def c_alias(va):
    return asm(f"""
        mov  eax, dword ptr [eax + 0x18]
        cmp  eax, {TAINT}
        jne  L1
        mov  eax, 0x66
        jmp  L2
    L1: cmp  eax, {PILLAR}
        jne  L2
        mov  eax, 0x68
    L2: add  eax, -0x64
        jmp  {SITES['alias'][2]:#x}
    """, va)


def c_ai(va):
    return asm(f"""
        mov  eax, dword ptr [ebp - 0x60]
        cmp  eax, {TAINT}
        jne  L1
        mov  eax, 0x7d
        jmp  L2
    L1: cmp  eax, {PILLAR}
        jne  L2
        mov  eax, 0x75
    L2: add  eax, -0x64
        jmp  {SITES['ai'][2]:#x}
    """, va)


def c_preview(va):
    return asm(f"""
        mov  eax, dword ptr [eax + 0x38]
        cmp  eax, {PILLAR}
        jne  L1
        mov  eax, 0x7c
    L1: add  eax, -0x68
        jmp  {SITES['preview'][2]:#x}
    """, va)


def c_strike(va):
    return asm(f"""
        movsx eax, byte ptr [ebp - 0x30]
        mov  edx, dword ptr [ebp - 4]
        cmp  dword ptr [edx + 0x18], {PILLAR}
        jne  L1
        mov  eax, 1
    L1: mov  dword ptr [edx + 0x28], eax
        jmp  {SITES['strike'][2]:#x}
    """, va)


def c_hid(va):
    # replaces `mov edx,0x75` in the four 0x31003 handlers; [ebp-8] = the message there
    return asm(f"""
        mov  edx, dword ptr [ebp - 8]
        cmp  dword ptr [edx + 0x10], {MARKER:#x}
        jne  L75
        mov  edx, dword ptr [edx + 0xc]
        ret
    L75:
        mov  edx, 0x75
        ret
    """, va)


def c_filter(va):
    # called from the two spawn-loop stubs; eax = the object, [ebp-8] = the effect.  Returns the
    # flags the following `jne` tests: ZF set = keep the unit.
    return asm(f"""
        mov  edx, dword ptr [ebp - 8]
        cmp  dword ptr [edx + 0x18], {TAINT}
        jne  Lorig
        push ebx
        mov  ebx, eax
        mov  ecx, dword ptr [ebx]
        mov  edx, {BURNING:#x}
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  Lyes
        mov  eax, ebx
        mov  ecx, dword ptr [ebx]
        mov  edx, {LIVING_FLAME:#x}
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  Lyes
        mov  eax, ebx
        mov  ecx, dword ptr [ebx]
        mov  edx, {LIVING_FLAME_ENCH:#x}
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  Lyes
        pop  ebx
        or   eax, 1
        ret
    Lyes:
        pop  ebx
        xor  eax, eax
        ret
    Lorig:
        mov  al, byte ptr [eax + 0x45]
        mov  edx, dword ptr [edx + 0x2c]
        cmp  al, byte ptr [edx + 0x45]
        ret
    """, va)


def c_stub(va, resume):
    return asm(f"""
        call {A['filter']:#x}
        jmp  {resume:#x}
    """, va)


def c_spray(va):
    # replaces `xor eax,eax / mov [ebp-0x28],eax` before MakeArcPath in Geyser's NewFrame
    return asm(f"""
        mov  eax, dword ptr [ebp - 8]
        cmp  dword ptr [eax + 0x14], 0x34
        jne  Lzero
        cmp  dword ptr [eax + 0x18], {PILLAR}
        jne  Lzero
        fld  dword ptr [ebp - 0x30]
        fmul st(0), st(0)
        fstp dword ptr [ebp - 0x28]
        mov  dword ptr [ebp - 0x30], 0
        ret
    Lzero:
        xor  eax, eax
        mov  dword ptr [ebp - 0x28], eax
        ret
    """, va)


def c_land(va):
    # TCAbRangedTE.Execute's landing dispatch: [ebp-0x20] = effect, [ebp-4] = TE, message at
    # [ebp-0x64] (as Triple Fireball builds it at 0x0040B823), hex scratch [ebp-0x28]/[ebp-0x2C],
    # loop [ebp-0x10], field [ebp-0x18]/[ebp-0x14].  [ebp-0x1C] (the effect loop) is not touched.
    src = f"""
        mov  eax, dword ptr [ebp - 0x20]
        cmp  byte ptr [eax + 0x34], 0x1e
        jne  Lorig
        cmp  dword ptr [eax + 0x14], 0x34
        jne  Lorig
        cmp  dword ptr [eax + 0x18], {PILLAR}
        jne  Lorig
        push ebx
        {{ANC}}
        mov  dword ptr [ebp - 0x64], 0x31003
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x10]
        mov  dword ptr [ebp - 0x5c], eax
        mov  dword ptr [ebp - 0x58], {PILLAR}
        mov  dword ptr [ebp - 0x54], {MARKER:#x}
        mov  dword ptr [ebp - 0x48], 0xffffffff
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
        mov  dword ptr [ebp - 0x10], 0
    Lhex:
        lea  eax, [ebp - 0x14]
        push eax
        lea  eax, [ebp - 0x18]
        push eax
        mov  ecx, dword ptr [ebp - 0x10]
        cmp  ecx, 19
        jl   Lhn
        sub  ecx, 19
    Lhn:
        mov  edx, dword ptr [ebp - 0x2c]
        mov  eax, dword ptr [ebp - 0x28]
        call {CENTERHN:#x}
        mov  eax, dword ptr [ebx + {{CONTAINER}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x10]
        xor  edx, edx
        call {GETMAPLEVEL:#x}
        mov  ecx, dword ptr [ebp - 0x18]
        mov  edx, dword ptr [ebp - 0x14]
        call {GETFIELD:#x}
        test eax, eax
        je   Lskip
        lea  edx, [ebp - 0x64]
        call {SENDMSG:#x}
    Lskip:
        inc  dword ptr [ebp - 0x10]
        cmp  dword ptr [ebp - 0x10], 38
        jne  Lhex
        mov  dword ptr [ebp - 0x54], 0
        mov  eax, dword ptr [ebx + {{COMBATMAP}}]
        cmp  byte ptr [eax + 0x129], 0
        je   Lout
        mov  eax, dword ptr [ebx + {{HSSET}}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0x84]
        mov  edx, {PILLAR}
        call {GETSPELL:#x}
        mov  eax, dword ptr [eax + 0x28]
        mov  edx, 1
        call {SFXPLAY:#x}
    Lout:
        pop  ebx
        jmp  {LANDING_DONE:#x}
    Lorig:
        mov  al, byte ptr [eax + 0x34]
        sub  al, 5
        jmp  {SITES['land'][2]:#x}
    """
    return pic(src, va, "ebx", {"CONTAINER": VAR_CONTAINER, "COMBATMAP": VAR_COMBATMAP,
                                "HSSET": VAR_HSSET})


BUILDERS = [("alias", c_alias), ("ai", c_ai), ("preview", c_preview), ("strike", c_strike),
            ("hid", c_hid), ("filter", c_filter),
            ("stub1", lambda va: c_stub(va, SITES["filt1"][2])),
            ("stub2", lambda va: c_stub(va, SITES["filt2"][2])),
            ("spray", c_spray), ("land", c_land)]


def layout():
    for _ in range(2):
        va, blobs = SLOT[0], []
        for name, b in BUILDERS:
            A[name] = va
            blob = b(va)
            blobs.append((name, va, blob))
            va = (va + len(blob) + 15) & ~15
    return blobs


def interior_jumps(d, ranges):
    """Every branch in AoWTCPCK's CODE whose target is strictly inside one of `ranges` (the
    displaced bytes of a multi-instruction hook), by a linear capstone sweep with skipdata."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.skipdata = True
    lo, hi = 0x00401000, 0x00401000 + 0x65BAC
    o = P.va2off(bytearray(d), lo)
    bad = []
    for ins in md.disasm(bytes(d[o:o + (hi - lo)]), lo):
        if ins.mnemonic.startswith("j") or ins.mnemonic == "call":
            try:
                t = int(ins.op_str, 16)
            except ValueError:
                continue
            for a, b in ranges:
                if a < t < b and not (a <= ins.address < b):
                    bad.append((ins.address, t))
    return bad


def main():
    blobs = layout()
    hooks = []
    for name, (va, orig, _resume) in SITES.items():
        orig = bytes.fromhex(orig)
        target = A["stub1"] if name == "filt1" else A["stub2"] if name == "filt2" else A[name]
        new = jmp(va, target) + b"\x90" * (len(orig) - 5)
        hooks.append((va, orig, new))
    for va in HID_SITES:
        hooks.append((va, bytes.fromhex("ba75000000"), call(va, A["hid"])))
    hooks.append((SPRAY, bytes.fromhex("33c08945d8"), call(SPRAY, A["spray"])))
    hooks.append((SPELLTYPES + TAINT, b"\x00", b"\x25"))
    hooks.append((SPELLTYPES + PILLAR, b"\x00", b"\x1e"))
    d = open(P.TARGET, "rb").read()
    bad = interior_jumps(d, [(va, va + len(bytes.fromhex(o))) for va, o, _r in SITES.values()])
    if bad:
        sys.exit("ABORT: jumps into a hook's interior: " +
                 ", ".join("%08X->%08X" % x for x in bad))
    print("interior sweep: no branch lands inside a displaced range")
    run("build_deathfire_tc -- Taint the Flame + Pillar of Banefire (AoWTCPCK)", hooks, blobs,
        SLOT, [])


if __name__ == "__main__":
    main()
