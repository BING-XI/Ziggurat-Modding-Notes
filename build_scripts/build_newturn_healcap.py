#!/usr/bin/env python
r"""
build_newturn_healcap.py -- fix TAbstractUnit.NewTurn's 8-bit overheal wrap (a LATENT VANILLA BUG),
and in doing so make HP pools up to 127 safe for the DAM/HP doubling.

THE BUG (verified by live disassembly 2026-08-24)
-------------------------------------------------
TAbstractUnit.NewTurn applies per-turn healing like this (0x55780DE6..0x55780DFD):

    8B C6                    mov  eax, esi
    8B 10                    mov  edx, [eax]
    FF 92 E0 00 00 00        call [edx+0xE0]        ; GetHitPoints (current)
    8B D0                    mov  edx, eax
    02 D3                    add  dl, bl            ; cur += heal  -- 8-BIT, UNCAPPED
    8B C6                    mov  eax, esi
    8B 08                    mov  ecx, [eax]
    FF 91 E4 00 00 00        call [ecx+0xE4]        ; SetHitPoints(dl)

The heal in BL is either round(maxHP * 0.1) floored at 1 (natural), or -- with Regeneration
(ability 0x31) -- THE FULL maxHP. `add dl, bl` wraps at 127: a Regeneration unit with cur + max
> 127 goes NEGATIVE, and SetHitPoints turns that into a near-dead unit. This can fire TODAY
(high-XP Regeneration units; a hero with a regeneration item at high current HP) and binds the
whole HP-doubling plan: without the fix the practical HP ceiling is 64 for Regeneration carriers.

THE FIX
-------
Replace those 24 bytes with `call cave` + NOPs. The cave (position-independent: register-indirect
calls only, no globals, no relocs -- verified none in the displaced window) does the sum in 32 bits
and clamps to maxHP before SetHitPoints:

    heal32 = EBX; cur = GetHitPoints(); max = GetHits()
    SetHitPoints(min(cur + heal32, max))

Semantics preserved exactly for every non-wrapping case (SetHitPoints previously received
cur+heal and vanilla relied on downstream behaviour; now it receives min(cur+heal, max), which is
what every sane path produced anyway). Regeneration still heals to full.

EDI/EBP are not touched (NewTurn does not save them); only EAX/ECX/EDX + one stack slot are used.

USAGE
    python build_newturn_healcap.py            verify / dry run
    python build_newturn_healcap.py --dis      also disassemble the cave
    python build_newturn_healcap.py --apply    hook + write the cave
    python build_newturn_healcap.py --undo     restore the 24 bytes, zero the cave
"""
import os, sys, struct, shutil, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_statdouble import kill_aow  # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-newturnheal")
IMAGE_BASE = 0x55700000

HOOK_VA = 0x55780DE6
HOOK_LEN = 24
ORIG = bytes.fromhex("8bc68b10ff92e00000008bd002d38bc68b08ff91e4000000")
CAVE_VA = 0x55818040          # verified zero 2026-08-24; markers end at 0x55818014
CAVE_MAX = 0x40               # body is 49 B; build_medal_hpmv.py's cap cave starts at 0x55818080

# NB keystone parses ';' as a statement SEPARATOR, never a comment -- keep this source bare.
# Layout: GetHits (vmt+0xD0) -> max; GetHitPoints (vmt+0xE0) -> cur; 32-bit sum clamped to max;
# SetHitPoints (vmt+0xE4). EBX (the heal) is preserved for the caller.
CAVE_SRC = """
    push ebx
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx + 0xD0]
    movsx ecx, al
    push ecx
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx + 0xE0]
    movsx edx, al
    pop  ecx
    pop  ebx
    add  edx, ebx
    cmp  edx, ecx
    jle  _ok
    mov  edx, ecx
_ok:
    mov  eax, esi
    mov  ecx, [eax]
    call dword ptr [ecx + 0xE4]
    ret
"""


def va2off(d, va):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    sec, rva = e + 24 + opt, va - IMAGE_BASE
    for _ in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, sec + 8)
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
        sec += 40
    return None


def build_cave():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    body = bytes(ks.asm(CAVE_SRC, CAVE_VA)[0])
    assert len(body) <= CAVE_MAX, "cave grew past its zone"
    return body


def hook_bytes():
    rel = CAVE_VA - (HOOK_VA + 5)
    return b"\xe8" + struct.pack("<i", rel) + b"\x90" * (HOOK_LEN - 5)


def show(body):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return
    for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(body, CAVE_VA):
        print("    %08X  %-20s %s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))


def main():
    ap = argparse.ArgumentParser(description="NewTurn overheal wrap fix")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()

    d = bytearray(open(TARGET, "rb").read())
    ho, co = va2off(d, HOOK_VA), va2off(d, CAVE_VA)
    cave = build_cave()
    hook = hook_bytes()
    cur = bytes(d[ho:ho + HOOK_LEN])
    if cur == ORIG:
        state = "clean"
    elif cur == hook:
        state = "applied"
    else:
        sys.exit("ABORT: hook window holds neither the vanilla bytes nor our hook:\n  %s" % cur.hex(" "))

    print("build_newturn_healcap -- NewTurn 8-bit overheal wrap fix")
    print("hook %08X (%d B) -> cave %08X (%d B) | state: %s\n" % (HOOK_VA, HOOK_LEN, CAVE_VA, len(cave), state.upper()))
    if a.dis:
        show(cave)

    if state == "clean":
        zone = bytes(d[co:co + CAVE_MAX])
        if any(zone) and zone[:len(cave)] != cave:
            sys.exit("ABORT: cave zone %08X not free:\n  %s" % (CAVE_VA, zone.hex(" ")))

    if not (a.apply or a.undo):
        print("(dry run -- nothing written)")
        return
    if a.undo:
        if state == "clean":
            print("nothing to undo."); return
        kill_aow()
        d[ho:ho + HOOK_LEN] = ORIG
        d[co:co + CAVE_MAX] = b"\x00" * CAVE_MAX
        open(TARGET, "wb").write(bytes(d))
        print("UNDONE -- vanilla bytes restored, cave zeroed.")
        return
    if state == "applied":
        print("already applied -- nothing to do (idempotent)."); return
    kill_aow()
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP); print("  backup -> %s" % os.path.basename(BACKUP))
    d[co:co + len(cave)] = cave
    d[ho:ho + HOOK_LEN] = hook
    open(TARGET, "wb").write(bytes(d))
    print("APPLIED -- per-turn healing is now clamped at max HP in 32-bit arithmetic.")


if __name__ == "__main__":
    main()
