#!/usr/bin/env python
r"""
build_staticshield.py -- Static Shield's stun: each melee strike that lands on a unit holding Static
Shield (0x55) lets that unit stun the striker, which resists as against a lightning stun.
AoWEPACK.dpl.  The spell and enchantment: build_airwater_ench.py.  Owner's design 2026-10-26
(05-spells-added.md, "Air/Water -- agreed design"; the stun's length: the lightning result).

WHAT IS MELEE  every weapon blow is a TStrikeCA (VMT 0x5571E344) and no class inherits from it.
  Ranged attacks and breath (TRangedAttackCA), spells, Turn Undead, Self Destruct and the touch
  abilities (Web, Entangle, Possess, Invoke Death, Command, Healing, Dispel) have their own CAs and
  never trigger it.  The swing a touched unit makes back is a TStrikeCA, so it does.  Both engines
  build strikes through TStrikeCA.Generate: TMeleeRound.CreateStrikeCA (attack and retaliation)
  and AoWE.CreateStrikeCA (Round Attack, follow-ups, touch swing-backs), reached from AoWTCPCK
  through imports.  Three VMT slots catch every call; nothing calls the methods directly.
  G   0x5571E3AC  TStrikeCA VMT +0x68 Generate (0x557668B4) -> cave_gen: the original, then when the
      strike landed ([CA+0x10] > 0), the struck object holds 0x55 (+0xA8: 0 for a wall, item-aware)
      and the striker is not Stunned (0x5C): the striker's own lightning roll, combat VMT +0x118
      with DX = 4 (ExecuteDamageEffectsRole: Lightning in its immunity types or Lightning Immunity
      0x09 -> no roll; Lightning Protection +4 RES; Lightning Weakness -4; HitRole(10 - RES)).  It
      returns 4 (stunned), or 1 (Burning) for a war machine (build_lightning_ignites.py); AL & 5
      goes to CA+0x17 (TDamageCA alignment padding; Razor Plate owns +0x16).
  X   0x5571E394  TStrikeCA VMT +0x50 Execute (0x55766738) -> cave_exec: the original (damage,
      effects, Razor Plate), then when CA+0x17 is set and the striker is still enabled (Razor
      Plate's cut can kill it), the striker's +0x128 ExecuteDamageEffects with that mask: Stunned
      0x5C as a lightning hit grants it (ExpandAbility, tick player = whoever's turn it is).
      Struck in its own turn (an attack, a Round Attack), the striker loses its remaining strikes
      and its retaliations until its next turn; struck in the holder's turn (a retaliation, a
      swing-back), it also loses its next turn -- the lightning result either way.
  R   0x5571E35C  TStrikeCA VMT +0x18 ReadWrite (0x55766714) -> cave_rw: the original, then CA+0x17
      as a byte with stream id 0x15 (free in the chain; old streams read 0), so the serialised
      combat replays the stun.
  The three slots keep their .reloc entries.  A killing blow on the holder still stuns; a striker
  already stunned is not rolled again; a Round Attack sweep goes on after the stun (vanilla does the
  same for a lightning stun); a blow that Mistform absorbs still counts as landed.

RNG: P2 COMBAT RAW: HitRole (RAW list) via ExecuteDamageEffectsRole from TStrikeCA.Generate.
Auto-resolve rides TCombat.Execute's re-anchor; manual combat's four strike builders each follow a
synced re-anchor (0x004089D6, 0x00409B45, 0x0040A525, 0x0040ABA3).  Every gate is replicated
state, so every peer draws the same number of times.  rng_audit.py --owners cannot see the draw
(it reaches the generator through a caller).
Slot 0x558BEC00-0x558BEFFF, exclusive.  PIC.  Surgical --undo.

    python build_scripts/build_staticshield.py            dry run + state
    python build_scripts/build_staticshield.py --apply
    python build_scripts/build_staticshield.py --undo
    python build_scripts/build_staticshield.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run

STATIC, STUNNED, LIGHTNING = 0x55, 0x5C, 4
FLAG, RW_ID = 0x17, 0x15
SLOT = (0x558BEC00, 0x558BF000)
VMT_STRIKE = 0x5571E344
SLOTS = {   # name: (VMT cell, original method)
    "gen":  (VMT_STRIKE + 0x68, 0x557668B4),
    "exec": (VMT_STRIKE + 0x50, 0x55766738),
    "rw":   (VMT_STRIKE + 0x18, 0x55766714),
}
FINDID = 0x55728C68
VMT_TCU = 0x55715A94
A = {}


def c_gen(va):
    """Generate(EAX CA, EDX striker, ECX struck, three stack args); ret 0xC."""
    return asm(f"""
        push ebp
        mov  ebp, esp
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  edi, edx
        mov  esi, ecx
        push dword ptr [ebp + 0x10]
        push dword ptr [ebp + 0xc]
        push dword ptr [ebp + 8]
        call {SLOTS['gen'][1]:#x}
        mov  byte ptr [ebx + {FLAG:#x}], 0
        cmp  byte ptr [ebx + 0x10], 0
        je   g_out
        test esi, esi
        je   g_out
        test edi, edi
        je   g_out
        mov  eax, esi
        mov  edx, {STATIC:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        je   g_out
        mov  eax, edi
        mov  edx, {STUNNED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        jne  g_out
        mov  eax, edi
        mov  edx, {LIGHTNING}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x118]
        and  al, 5
        mov  byte ptr [ebx + {FLAG:#x}], al
    g_out:
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret  0xc
    """, va)


def c_exec(va):
    """Execute(EAX CA, EDX TCombat)."""
    return asm(f"""
        push ebx
        push esi
        push ebp
        mov  ebx, eax
        mov  ebp, edx
        call {SLOTS['exec'][1]:#x}
        cmp  byte ptr [ebx + {FLAG:#x}], 0
        je   x_out
        xor  edx, edx
        mov  dl, byte ptr [ebx + 0xd]
        mov  eax, dword ptr [ebp + 0xc]
        call {FINDID:#x}
        test eax, eax
        je   x_out
        mov  esi, eax
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x60]
        test al, al
        je   x_out
        movzx edx, byte ptr [ebx + {FLAG:#x}]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x128]
    x_out:
        pop  ebp
        pop  esi
        pop  ebx
        ret
    """, va)


def c_rw(va):
    """ReadWrite(EAX CA, EDX stream)."""
    return asm(f"""
        push ebx
        push esi
        mov  ebx, eax
        mov  esi, edx
        call {SLOTS['rw'][1]:#x}
        lea  edx, [ebx + {FLAG:#x}]
        mov  ecx, {RW_ID:#x}
        mov  eax, esi
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0x30]
        pop  esi
        pop  ebx
        ret
    """, va)


BUILDERS = [("gen", c_gen), ("exec", c_exec), ("rw", c_rw)]


def layout():
    va, blobs = SLOT[0], []
    for name, b in BUILDERS:
        A[name] = va
        blob = b(va)
        blobs.append(("cave_" + name, va, blob))
        va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    return blobs


def checks(d):
    u = lambda v: struct.unpack_from("<I", d, P.va2off(d, v))[0]
    for vmt, name in ((VMT_STRIKE, b"TStrikeCA"), (VMT_TCU, b"TCombatUnit")):
        cn = P.va2off(d, u(vmt - 0x20))
        if u(vmt - 0x40) != vmt or d[cn + 1:cn + 1 + d[cn]] != name:
            sys.exit("ABORT: %s's VMT moved" % name.decode())
    if u(VMT_TCU + 0x60) != 0x55724B70 or u(VMT_TCU + 0x118) != 0x55724C3C or u(VMT_TCU + 0x128) != 0x55724C1C:
        sys.exit("ABORT: TCombatUnit's GetEnabled / ExecuteDamageEffectsRole / ExecuteDamageEffects moved")
    # nothing else reads or writes CA+0x17 through a TStrikeCA register (see the docstring)


def main():
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d)
    hooks = [(cell, struct.pack("<I", orig), struct.pack("<I", A[n])) for n, (cell, orig) in SLOTS.items()]
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    run("build_staticshield -- Static Shield's stun (AoWEPACK)", hooks, blobs, SLOT, [],
        reloc_ok=[cell for cell, _o in SLOTS.values()])


if __name__ == "__main__":
    main()
