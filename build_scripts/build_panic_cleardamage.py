#!/usr/bin/env python
r"""
build_panic_cleardamage.py -- a Panicked (0x6C) unit can shake off the panic: a Resistance check at
power 10 (Cause Fear's) each time damage lands on it, and again at the start of each of its own
side's turns in battle.  AoWEPACK.dpl only.  Owner 2026-10-25: Curse of Lethe's sleep now ends on
damage, so Panic no longer ends on every hit; until then (2026-09-09) any landed damage cleared it.

THE ROLL (cave_roll, eax = the combat object -> eax 1 = recovers): HitRole(10 - RES) is the panic
  holding; the unit recovers when it fails: 5 x RES %, clamped 10-90 % (HitRole 0x55725D98 =
  50 + 5k %).  RES = the combat object's GetResistance (VMT +0x74, the value every Resistance check
  reads).  Removal: the ability owner (combat VMT +0xB8; nil for walls) -> RemoveAbility(0x6C)
  (+0x98), which calls Changed() itself -- the call Healing and Remedy make.  A unit that is not
  panicked never rolls: the owner's self-only GetAbSet (+0x4C) is asked first (0x6C never comes from
  an item), which also spares every other unit RemoveAbility's bitset growth.

D   0x55726C58  TCombatObject.ExecuteDamage's entry (6 B: push ebx/esi/edi/ebp, mov ebx,edx) ->
    cave_damage: the displaced bytes, then for damage EDX > 0 on a panicked unit, the roll -- unless
    the unit holds Mistform (0x54), whose absorb (build_airwater_ench.py, later in this function)
    turns the blow into no damage.  One body
    serves TCombatObject, TCombatUnit, TCombatWall and TFastCombatUnit, and AoWTCPCK's
    TTacticalCombatUnit +0x124 wrapper (0x00420250, build_facing_retal.py's site inside it)
    delegates into it with the damage still in EDX: melee, retaliation, ranged, breath, touch,
    spells, self-destruct, the Burning/Decay ticks and auto-resolve.  A miss never gets here; a
    fully absorbed hit arrives with EDX = 0.  TStrikeCA.Execute deals its damage (0x55766769)
    before it grants Cause Fear's panic (0x55766800), so a blow that panics is not rolled against.
T   0x557B68CC  TPanickedAbility VMT +0xF8 NewCombatTurn (.reloc kept) -> cave_turn: the original
    (TDurationAbility.NewCombatTurn, which never ticks Panic's mode 3), then, for id 0x6C only
    (Rallied, 0xC3, is a TPanickedAbility on the same VMT) and the turn of the unit's own side
    (CL == [obj+0x45]), the roll.  TNewCombatTurnCA and auto-resolve's turn loop call it for every
    status a unit holds; removing one there is what TDurationAbility.NewCombatTurn does itself.

RNG: manual combat -- System.RandSeed := TAoWHSMap.Random(map, $FFFFFF) before each roll (P1 bridge,
as build_stonegaze.py at the same turn start: the turn-start event is synchronised, raw draws are
not); auto-resolve (TFastCombatUnit) -- P2 COMBAT RAW.  Sites: RNG_SITES.
Slot 0x55829000-0x558291FF, exclusive.  PIC.  Surgical --undo.

Couplings: build_panic_nomelee.py gates the same status (separate hooks; either may be undone
alone).  build_airwater_ench.py's absorb sits later in ExecuteDamage; this cave reads its id only.  build_lethe.py's wake hook sits later in ExecuteDamage (0x55726CB3), independent.

    python build_scripts/build_panic_cleardamage.py            dry run + state
    python build_scripts/build_panic_cleardamage.py --apply
    python build_scripts/build_panic_cleardamage.py --undo
    python build_scripts/build_panic_cleardamage.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic

PANICKED, POWER = 0x6C, 10
MISTFORM = 0x54                             # build_airwater_ench.py: its absorb takes the blow
SLOT = (0x55829000, 0x55829200)
D_SITE, D_VAN, D_RESUME = 0x55726C58, bytes.fromhex("535657558bda"), 0x55726C5E
VMT_PANIC = 0x557B67D4
T_SLOT, T_ORIG = VMT_PANIC + 0xF8, 0x55764D8C
HSRANDOM, HITROLE = 0x5577827C, 0x55725D98
VAR_AOWHSMAP, CELL_RANDSEED = 0x558FA040, 0x558FB720
VMT_FAST = 0x5571D4BC
A = {}


def c_roll(va):
    src = f"""
        push ebx
        push esi
        mov  esi, eax
        {{ANC}}
        lea  edx, [ebx + {{FAST}}]
        cmp  dword ptr [esi], edx
        je   r_raw
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  edx, 0xffffff
        call {HSRANDOM:#x}
        mov  edx, dword ptr [ebx + {{SEED}}]
        mov  dword ptr [edx], eax
    r_raw:
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx edx, al
        mov  eax, {POWER}
        sub  eax, edx
        call {HITROLE:#x}
        xor  al, 1
        movzx eax, al
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"FAST": VMT_FAST, "MAP": VAR_AOWHSMAP, "SEED": CELL_RANDSEED})


def c_damage(va):
    return asm(f"""
        push ebx
        push esi
        push edi
        push ebp
        mov  ebx, edx
        test ebx, ebx
        jle  d_out
        push eax
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xb8]
        test eax, eax
        je   d_pop
        mov  esi, eax
        mov  edx, {PANICKED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        je   d_pop
        call {A['mist']:#x}
        jne  d_pop
        mov  eax, dword ptr [esp]
        call {A['roll']:#x}
        test eax, eax
        je   d_pop
        mov  eax, esi
        mov  edx, {PANICKED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x98]
    d_pop:
        pop  eax
    d_out:
        jmp  {D_RESUME:#x}
    """, va)


def c_turn(va):
    """NewCombatTurn(eax = the status, edx = the combat object, cl = the player whose turn starts)."""
    return asm(f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        mov  edi, ecx
        call {T_ORIG:#x}
        cmp  dword ptr [ebx + 0xc], {PANICKED:#x}
        jne  t_out
        mov  eax, edi
        cmp  al, byte ptr [esi + 0x45]
        jne  t_out
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0xb8]
        test eax, eax
        je   t_out
        mov  edi, eax
        mov  edx, {PANICKED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        je   t_out
        mov  eax, esi
        call {A['roll']:#x}
        test eax, eax
        je   t_out
        mov  eax, edi
        mov  edx, {PANICKED:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x98]
    t_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


def c_mist(va):
    """esi = the unit -> ZF clear when it holds Mistform (placed last so cave_turn keeps its address)."""
    return asm(f"""
        mov  eax, esi
        mov  edx, {MISTFORM:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        ret
    """, va)


BUILDERS = [("roll", c_roll), ("damage", c_damage), ("turn", c_turn), ("mist", c_mist)]
RNG_SITES = (0x5582901F, 0x5582903D)        # the re-anchor and HitRole in cave_roll


def layout():
    for name, _b in BUILDERS:
        A.setdefault(name, SLOT[0] + 0x180)
    for _ in range(3):
        va, blobs = SLOT[0], []
        for name, b in BUILDERS:
            A[name] = va
            blob = b(va)
            blobs.append(("cave_" + name, va, blob))
            va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    assert A["turn"] == 0x558290A0, "cave_turn moved: the T slot holds its address"
    return blobs


def checks(d, blobs):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    u = lambda v: struct.unpack_from("<I", d, P.va2off(d, v))[0]
    cn = P.va2off(d, u(VMT_PANIC - 0x20))
    if u(VMT_PANIC - 0x40) != VMT_PANIC or d[cn + 1:cn + 1 + d[cn]] != b"TPanickedAbility":
        sys.exit("ABORT: TPanickedAbility's VMT moved")
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    found = []
    for _n, va, blob in blobs:
        found += [i.address for i in md.disasm(blob, va)
                  if i.mnemonic == "call" and i.op_str in ("%#x" % HSRANDOM, "%#x" % HITROLE)]
    if tuple(found) != RNG_SITES:
        sys.exit("ABORT: RNG_SITES are stale: %s" % " ".join("%08X" % a for a in found))


def main():
    from build_lethe import interior_jumps
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d, blobs)
    hooks = [(D_SITE, D_VAN, b"\xE9" + struct.pack("<i", A["damage"] - (D_SITE + 5)) + b"\x90"),
             (T_SLOT, struct.pack("<I", T_ORIG), struct.pack("<I", A["turn"]))]
    bad = interior_jumps(d, [(D_SITE, D_SITE + len(D_VAN))])
    if bad:
        sys.exit("ABORT: jumps into a hook's interior: " + ", ".join("%08X->%08X" % x for x in bad))
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    run("build_panic_cleardamage -- Panic: Resistance to recover (AoWEPACK)", hooks, blobs, SLOT, [],
        reloc_ok=(T_SLOT,))


if __name__ == "__main__":
    main()
