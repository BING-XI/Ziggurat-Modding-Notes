#!/usr/bin/env python
r"""
build_replay_turnseed.py -- the auto-combat window shows the Burning ticks the battle actually rolled.
AoWEPACK.dpl only.  Owner's report 2026-10-27: "sometimes when units die to burning in auto-combat,
they come back to life ... they also sometimes seem able to still act when they die."  Vanilla.

WHAT THE OWNER SAW
    The auto-combat window is not the battle; it is a re-simulation of it.
      TCombat.Initialize @0x55727C94 -> TCombatLogbook.SetInitialData @0x55728E30 copies the battle's
          TCombatData into the logbook before round 1 (units are re-created from the stream, with
          their own ability data).
      TCombat.ExecuteCombatAction @0x55727224 adds every action to [[combat+0x18]+0x14] (a
          TCombatActionList; TEReferenceNode.AddChild keeps the object itself) and then Executes it.
      TFastCombat.Execute @0x55744A0C runs the whole battle, then AoWz.exe's fast-combat window plays
          the logbook through a TCombatViewer: Initialize @0x55729420 loads the initial copy into its
          own plain TCombat, Update @0x55729610 calls each action's Play (+0x54), SetPosition
          @0x557294D8 re-Executes actions 0..pos-1 on a slider drag and loads the logbook's FINAL
          copy (SetFinalData @0x55728E44) at the end position.
    Strikes replay exactly: TStrikeCA.Execute @0x55766738 applies the damage ([CA+0x10]) and effect
    bits ([CA+0x18]) that Generate rolled.  The turn-start action does not:
      TCombat.NewTurn @0x5572743C -> TNewCombatTurnCA.Execute @0x5572A308 -> every object's
      NewCombatTurn (+0xF0) -> TCombatUnit @0x55724B28 -> TAbilityOwner.TriggerNewCombatTurn
      @0x5574FE68 -> ability +0xF8 -> TBurningAbility.NewCombatTurn @0x557BA3D4, whose HitRole
      (0x557BA46B -> @0x55725D98, one raw @RandInt) is rolled INSIDE Execute.
    TNewCombatTurnCA.Play @0x5572A348 calls its own Execute on the viewer's combat at tick 0, so the
    window rolls every Burning tick again from whatever System.RandSeed holds by then.  A tick that
    missed in the battle can hit and kill in the window; the unit then still makes the strikes the
    battle recorded for it, and at the end position the window loads the real final state, where it
    is alive.  The converse (a burn death the window misses) shows as a unit vanishing at the end.
    The battle's own result is consistent: ExecuteDamage @0x55726C58 clamps damage to the current
    HP, DestroyObject sets [obj+0x47] bit 1, no code clears that bit, and TCombatUnit.Finalize
    @0x55724D44 frees flagged objects.

THE FIX -- record the turn's seed in the action, replay it from there
    TNewCombatTurnCA (VMT 0x5571659C, no descendants) grows 0x10 -> 0x14 bytes:
        +0x0D  byte   1 = a seed is recorded (alignment padding until now)
        +0x10  dword  System.RandSeed at the action's first Execute
    cave_exec, entered from the Execute entry: the first Execute stores RandSeed and sets the flag
    (the battle; RandSeed is only read, so the battle draws exactly what it drew before); any later
    Execute of the same action (the viewer's Play, a slider re-Execute) writes the stored seed back to
    RandSeed first.  The whole turn-start pass then draws the same numbers over the same state, so the
    window shows the battle's Burning ticks -- and Searing Aura (0xC5), Rime Aura (0xC8) and Smoky
    Haze (0xCA), whose auto-resolve rolls are raw HitRoles in the same pass.
    cave_rw, inside TNewCombatTurnCA.ReadWrite @0x5572A2E4: after the player byte (tag 0x14) also
    rwByte(+0x0D, tag 0x15) and rwInteger(+0x10, tag 0x16), so a replay opened from Event History
    after a load matches too.  TEObject.ReadWrite (EngineP) writes no tags.  A record saved before
    this patch has neither tag: the fields stay 0 and that replay re-rolls as vanilla did.

SITES
    0x55716580   TNewCombatTurnCA instance size  10 00 00 00 -> 14 00 00 00
    0x5572A308   Execute entry, 5 B   push ebx/esi/edi; mov edi,edx  -> jmp cave_exec, resume 0x5572A30D
    0x5572A2FB   ReadWrite, 7 B   mov eax,esi; mov ebx,[eax]; call [ebx+0x30] -> jmp cave_rw + 2 nop,
                 resume 0x5572A302 (pop esi; pop ebx; ret).  EBX is still the action at the hook;
                 cave_rw keeps it across the first call, which the host's own sequence clobbered.
    Stream slots (EngineP TEReadStorageStream): +0x2C rwInteger, +0x30 rwByte; EAX = stream,
    EDX = field, ECX = tag.  No .reloc entry in either hook window or the slot; no jump lands inside
    either window.  Byte-identical to the root DLL before this patch (instance size, both hooks).

RANDOMNESS
    No draw added.  The battle: P2 COMBAT RAW, untouched (RandSeed read, never written).  The
    window: P5 RESEED-FROM-STATE -- RandSeed := the seed persisted in the action, then the same
    turn-start code draws a sequence fixed in length and order.  The viewer is local display; vanilla
    already left RandSeed arbitrary after it, so no peer-visible state changes.

RULED OUT (2026-10-27, against the live DLL)
    Signed-byte HP wrap: ExecuteDamage passes HP - min(dmg, HP), never negative.  Reforming Flesh's
    round heal (0x5572A3BC): deterministic, skips HP <= 0, replays identically.  Living Flame, Dark
    Gift / lifesteal on round attacks, Lucky, Static Shield / Mistform absorb, Curse of Lethe, Panic
    clear: all applied from stored action data inside ExecuteDamage or TStrikeCA.Execute.  The 200-round
    cap: battle loop only.  Poisoned: a stat debuff with no turn tick.  Decay: a fixed tick, no roll.

COUPLINGS
    * build_burning_sailing.py / build_damhp_gapfix.py / build_combatlog_ticks.py own bytes inside
      TBurningAbility.NewCombatTurn; this script touches none of them and needs none of them.
    * build_reformingflesh.py hooks TNewCombatRoundCA.Execute (0x5572A3BC), a different action.
    * build_combatlog_replays.py prints "X is slain" for a death across a replayed action, so the
      window's log showed the re-rolled burn deaths too; it now shows the battle's.  The tick lines
      (build_combatlog_ticks.py) print only in a live manual battle and are unaffected.
    * rng_audit.py does not list cave_exec: it reaches the RandSeed cell through the call/pop anchor,
      not by constant, and makes no draw.

Slot 0x558C4000-0x558C40FF, exclusive.  PIC (call/pop anchor for the RandSeed IAT cell 0x558FB720).
Surgical --undo restores the three sites and zeroes the slot.

    python build_scripts/build_replay_turnseed.py            dry run + state
    python build_scripts/build_replay_turnseed.py --apply
    python build_scripts/build_replay_turnseed.py --undo
    python build_scripts/build_replay_turnseed.py --dis
    python build_scripts/build_replay_turnseed.py --emulate   run both caves under unicorn
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import aowepack_patch as P
from aowepack_patch import asm, run, jmp_to
from piccave import pic

SLOT = (0x558C4000, 0x558C4100)
CAVE_EXEC, CAVE_RW = 0x558C4000, 0x558C4040

VMT = 0x5571659C                               # TNewCombatTurnCA
SIZE_AT = VMT - 0x1C
SIZE_VAN, SIZE_NEW = 0x10, 0x14
F_REC, F_SEED = 0x0D, 0x10                     # recorded flag, seed
TAG_REC, TAG_SEED = 0x15, 0x16                 # vanilla uses 0x14 for the player byte

EXEC, EXEC_RESUME, EXEC_END = 0x5572A308, 0x5572A30D, 0x5572A346
EXEC_VAN = bytes.fromhex("5356578bfa")         # push ebx / push esi / push edi / mov edi,edx
RW_FN, RW_HOOK, RW_RESUME, RW_END = 0x5572A2E4, 0x5572A2FB, 0x5572A302, 0x5572A305
RW_VAN = bytes.fromhex("8bc68b18ff5330")       # mov eax,esi / mov ebx,[eax] / call [ebx+0x30]
CELL_RANDSEED = 0x558FB720                     # IAT cell -> VCL30 System.RandSeed
RW_INTEGER, RW_BYTE = 0x2C, 0x30               # TEReadStorageStream / TEWriteStorageStream slots


def build_exec(va):
    return pic(f"""
        push ebx
        push esi
        push edi
        mov  edi, edx
        {{ANC}}
        mov  ecx, dword ptr [ecx + {{SEED}}]
        cmp  byte ptr [eax + {F_REC:#x}], 0
        jne  _rep
        mov  edx, dword ptr [ecx]
        mov  dword ptr [eax + {F_SEED:#x}], edx
        mov  byte ptr [eax + {F_REC:#x}], 1
        jmp  _go
    _rep:
        mov  edx, dword ptr [eax + {F_SEED:#x}]
        mov  dword ptr [ecx], edx
    _go:
        mov  edx, edi
        jmp  {EXEC_RESUME:#x}
    """, va, "ecx", {"SEED": CELL_RANDSEED})


def build_rw(va):
    return asm(f"""
        push ebx
        mov  eax, esi
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + {RW_BYTE:#x}]
        mov  ebx, dword ptr [esp]
        lea  edx, [ebx + {F_REC:#x}]
        mov  ecx, {TAG_REC:#x}
        mov  eax, esi
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + {RW_BYTE:#x}]
        pop  ebx
        lea  edx, [ebx + {F_SEED:#x}]
        mov  ecx, {TAG_SEED:#x}
        mov  eax, esi
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + {RW_INTEGER:#x}]
        jmp  {RW_RESUME:#x}
    """, va)


caves = [("cave_exec", CAVE_EXEC, build_exec(CAVE_EXEC)), ("cave_rw", CAVE_RW, build_rw(CAVE_RW))]
hooks = [
    (SIZE_AT, struct.pack("<I", SIZE_VAN), struct.pack("<I", SIZE_NEW)),
    (EXEC, EXEC_VAN, jmp_to(EXEC, CAVE_EXEC, len(EXEC_VAN))),
    (RW_HOOK, RW_VAN, jmp_to(RW_HOOK, CAVE_RW, len(RW_VAN))),
]
interior = [(EXEC, EXEC + len(EXEC_VAN), EXEC, EXEC_END),
            (RW_HOOK, RW_HOOK + len(RW_VAN), RW_FN, RW_END)]


def selfcheck():
    """Shapes the hooks depend on, read from the live file: no descendant of TNewCombatTurnCA (a
    child would inherit the grown fields at its own, unchanged size), the host code around both
    windows, and that nothing in the cave names an absolute address inside the image."""
    d = open(P.TARGET, "rb").read()
    u = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    e, secs = P.sections(d)
    vsize, vaddr, rsize, raw = secs[0]
    for off in range(raw, raw + min(vsize, rsize) - 4, 4):
        v = P.IMAGE_BASE + vaddr + (off - raw) + 0x40
        if struct.unpack_from("<I", d, off)[0] == v and v != VMT:
            cell = u(v - 0x18)
            if P.IMAGE_BASE <= cell < 0x55A00000 and u(cell) == VMT:
                sys.exit("ABORT: class at %08X descends from TNewCombatTurnCA" % v)
    assert u(VMT + 0x50) == EXEC and u(VMT + 0x18) == RW_FN, "TNewCombatTurnCA VMT moved"
    o = P.va2off(d, RW_FN)
    assert d[o + 0x0F:o + 0x17] == bytes.fromhex("8d530cb914000000"), "ReadWrite: lea edx,[ebx+0C]/mov ecx,14 moved"
    assert d[o + 0x1E:o + 0x21] == bytes.fromhex("5e5bc3"), "ReadWrite epilogue moved"
    o = P.va2off(d, EXEC_RESUME)
    assert d[o:o + 5] == bytes.fromhex("8bf08b5f0c"), "Execute: mov esi,eax / mov ebx,[edi+0C] moved"
    for _n, va, blob in caves:
        for k in range(len(blob) - 3):
            w = struct.unpack_from("<I", blob, k)[0]
            assert not (P.IMAGE_BASE <= w < 0x55A00000), "%s: absolute in-image dword at +%d" % (_n, k)


# ---------------------------------------------------------------- --emulate (unicorn)
def emulate():
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
    from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
                                   UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP,
                                   UC_X86_REG_EIP)
    d = bytearray(open(P.TARGET, "rb").read())
    for va, van, new in hooks:                         # patch a private copy, vanilla or installed
        o = P.va2off(d, va)
        assert bytes(d[o:o + len(van)]) in (van, new), "%08X foreign" % va
        d[o:o + len(new)] = new
    IMG, HEAP, STUB, STK, MAGIC = P.IMAGE_BASE, 0x10000000, 0x20000000, 0x30000000, 0x40000000
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    e, secs = P.sections(d)
    top = max(vaddr + max(vsize, rsize) for vsize, vaddr, rsize, raw in secs)
    mu.mem_map(IMG, (top + 0xFFF) & ~0xFFF)
    for vsize, vaddr, rsize, raw in secs:
        mu.mem_write(IMG + vaddr, bytes(d[raw:raw + rsize]))
    for _n, va, blob in caves:
        mu.mem_write(va, blob)
    for base in (HEAP, STUB, STK, MAGIC):
        mu.mem_map(base, 0x10000)
    r32 = lambda a: struct.unpack("<I", mu.mem_read(a, 4))[0]
    w32 = lambda a, v: mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))
    SEEDVAR = HEAP + 0x100
    w32(CELL_RANDSEED, SEEDVAR)
    regs = (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP)

    def call(entry, eax, edx, until=None):
        sentinel = [0xB0B0, 0x5151, 0xD1D1, 0xBEBE]
        for r, v in zip(regs, sentinel):
            mu.reg_write(r, v)
        mu.reg_write(UC_X86_REG_ESP, STK + 0x8000)
        w32(STK + 0x8000, MAGIC)
        mu.reg_write(UC_X86_REG_EAX, eax)
        mu.reg_write(UC_X86_REG_EDX, edx)
        mu.emu_start(entry, until or MAGIC, count=10_000)
        return sentinel

    # 1. Execute entry: first pass records, RandSeed untouched; second pass restores.
    CA, COMBAT = HEAP + 0x200, HEAP + 0x300
    mu.mem_write(CA, b"\0" * 0x14)
    mu.mem_write(CA + 0xC, b"\x02")
    for n, seed_now, want_seed, want_rs in ((1, 0x12345678, 0x12345678, 0x12345678),
                                             (2, 0x0BADF00D, 0x12345678, 0x12345678),
                                             (3, 0x77777777, 0x12345678, 0x12345678)):
        w32(SEEDVAR, seed_now)
        sent = call(EXEC, CA, COMBAT, until=EXEC_RESUME)
        esp = mu.reg_read(UC_X86_REG_ESP)
        pushed = [r32(esp + 8), r32(esp + 4), r32(esp)]
        ok = (mu.reg_read(UC_X86_REG_EIP) == EXEC_RESUME and esp == STK + 0x8000 - 12
              and pushed == sent[:3] and mu.reg_read(UC_X86_REG_EDI) == COMBAT
              and mu.reg_read(UC_X86_REG_EAX) == CA and mu.reg_read(UC_X86_REG_EDX) == COMBAT
              and mu.reg_read(UC_X86_REG_EBX) == sent[0] and mu.reg_read(UC_X86_REG_ESI) == sent[1]
              and mu.reg_read(UC_X86_REG_EBP) == sent[3]
              and mu.mem_read(CA + F_REC, 1)[0] == 1 and r32(CA + F_SEED) == want_seed
              and r32(SEEDVAR) == want_rs and mu.mem_read(CA + 0xC, 1)[0] == 2)
        print("  Execute pass %d: RandSeed %08X -> %08X, stored %08X  %s"
              % (n, seed_now, r32(SEEDVAR), r32(CA + F_SEED), "ok" if ok else "FAIL"))
        if not ok:
            sys.exit("EMULATION FAILED")

    # 2. ReadWrite: the three stream calls, in order, with EBX/ESI restored on return.
    TEOBJ_RW_THUNK = 0x557030FC
    o = P.va2off(d, TEOBJ_RW_THUNK)
    assert d[o:o + 2] == b"\xff\x25", "TEObject.ReadWrite thunk shape"
    STREAM, SVMT = HEAP + 0x400, HEAP + 0x500
    w32(STREAM, SVMT)
    stub_ret = STUB + 0x10
    mu.mem_write(stub_ret, b"\xc3")
    w32(struct.unpack_from("<I", d, o + 2)[0], stub_ret)          # TEObject.ReadWrite -> ret
    names = {}
    for slot, name in ((RW_BYTE, "rwByte"), (RW_INTEGER, "rwInteger")):
        w32(SVMT + slot, STUB + slot)
        mu.mem_write(STUB + slot, b"\xc3")
        names[STUB + slot] = name
    log = []

    def on_code(uc, addr, size, _):
        if addr in names:
            log.append((names[addr], uc.reg_read(UC_X86_REG_EAX), uc.reg_read(UC_X86_REG_EDX),
                        uc.reg_read(UC_X86_REG_ECX)))
    mu.hook_add(UC_HOOK_CODE, on_code, begin=STUB, end=STUB + 0x100)
    sent = call(RW_FN, CA, STREAM)
    want = [("rwByte", STREAM, CA + 0xC, 0x14), ("rwByte", STREAM, CA + F_REC, TAG_REC),
            ("rwInteger", STREAM, CA + F_SEED, TAG_SEED)]
    ok = (log == want and mu.reg_read(UC_X86_REG_ESP) == STK + 0x8004
          and [mu.reg_read(r) for r in regs] == sent)
    for c in log:
        print("  ReadWrite: %-9s stream=%08X field=CA+%02X tag=%02X" % (c[0], c[1], c[2] - CA, c[3]))
    print("  ReadWrite: %s" % ("ok" if ok else "FAIL"))
    if not ok:
        sys.exit("EMULATION FAILED")
    print("EMULATION OK")


if __name__ == "__main__":
    selfcheck()
    if "--emulate" in sys.argv:
        emulate()
    else:
        run("build_replay_turnseed", hooks, caves, SLOT, interior)
