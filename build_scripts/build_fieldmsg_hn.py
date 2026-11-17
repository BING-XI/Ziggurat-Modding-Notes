#!/usr/bin/env python
r"""
build_fieldmsg_hn.py -- a map-field message no longer reaches a sprite with another sprite's hex
number when the field is resized during the dispatch.  HSEPack.dpl only.

THE BUG (vanilla)
    HSEngine.TMapField.SendMapFieldMsg @0x55607944 delivers a message to every sprite registered on
    a field, setting Msg.HN (= the field's spiral index relative to that sprite's centre) before
    each MapFieldMsgProc call.  A field stores its sprites and their HNs in ONE block: FHSList
    ([field+8]) holds FCapacity ([field+0xC], byte) pointers, then FCapacity HN bytes.  The function
    computes the HN array's address once, before the loop:

        5560794D..55607960   HNs := FHSList + FCapacity*4      -> [esp]
        55607974             movzx eax, byte [ [esp] + ebx ]   ; Msg.HN := HNs[I]
        55607980             mov eax,[esi+8] / mov eax,[eax+ebx*4]   ; FHSList re-read every time

    A handler that adds a sprite to the same field (TMapField.AddHS @0x556072A4 grows the block by
    one slot through Resize -> ReallocMem when FCount = FCapacity) moves the HN array.  The loop
    keeps reading the old address, so the sprites still to come get stale HN bytes -- often 0,
    which every sprite centred on the field (terrain, blood, the corpse) has.

    In tactical combat: a unit registers on its own field (HN 0) and its six neighbours (HN 1..6);
    TTacticalCombatUnitHS.MapFieldMsgProc @0x00420E5C acts on damage messages only at HN 0.  A
    breath or Witchfire strike (0x31012) on the field of an adjacent enemy kills it, its death adds
    blood and a TCCorpseHS to that field mid-dispatch, the block is reallocated, and the attacker's
    own entry on that field (HN 1..6) can read HN 0: its handler runs CreateRangedAttackCA(attacker,
    attacker).  Combat log:
        Dwarf Miner is slain
        stunned 65% vs res 7 - landed                       <- the attacker's RES
        Dragon Golem hits Dragon Golem for 1 damage +stunned
    Every message sent through a field is exposed (spells, Call Flames, Fire), not only breath.

THE FIX
    The function is rewritten in place (89 B, same entry, same registers and Msg offsets): the HN
    address is recomputed from the current FHSList and FCapacity on every iteration.  Everything
    else is unchanged: the countdown from FCount, the `I < Count` guard (virtual +0x54), the stop
    when a handler changes Msg.Result ([msg+0x1C]), Msg.MapField ([msg+4]) and Msg.HN ([msg+0x18]).
    The local slot it used is gone (no `push ecx` / `pop edx`).

    No RNG, no new state: a handler sees exactly the HN vanilla meant it to see, so every peer
    computes the same thing.  No .reloc entry and no foreign jump lands inside the function
    (both asserted).  AoWz.exe and AoWzEd.exe load this one HSEPack.dpl copy.

COUPLINGS
    None: no other build script touches HSEPack.dpl 0x55607944..0x5560799D.

Usage:
    python build_fieldmsg_hn.py            # verify current state (dry run)
    python build_fieldmsg_hn.py --dis      # + disassemble vanilla and fixed bodies
    python build_fieldmsg_hn.py --apply    # write (kills running AoW binaries first)
    python build_fieldmsg_hn.py --undo     # restore the vanilla bytes
"""
import argparse
import os
import struct
import subprocess
import sys

sys.dont_write_bytecode = True

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TARGET = os.path.join(GAME, "HSEPack.dpl")
REFERENCE = os.path.join(os.path.dirname(GAME), "HSEPack.dpl")     # the vanilla root copy
IMAGE_BASE = 0x55600000
AOW_PROCS = ("AoW", "AoWz", "AoWCompat", "AoWzCompat", "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup")

FN = 0x55607944                       # HSEngine.TMapField.SendMapFieldMsg
VANILLA = bytes.fromhex(
    "53565755518bfa8bf08b6f1c33db8a5e0d33c08a460cc1e002034608890424897704eb264b8bc68b10ff5254"
    "3bd87d1a8b04240fb604188947188bd78b46088b04988b08ff91cc00000085db74053b6f1c74d15a5d5f5e5bc3")
FN_END = FN + len(VANILLA)            # 0x5560799D, the `lea eax,[eax]` filler after the ret

SRC = """
    push ebx
    push esi
    push edi
    push ebp
    mov  edi, edx
    mov  esi, eax
    mov  ebp, dword ptr [edi+0x1c]
    movzx ebx, byte ptr [esi+0xd]
    mov  dword ptr [edi+4], esi
    jmp  test_
loop_:
    dec  ebx
    mov  eax, esi
    mov  edx, dword ptr [eax]
    call dword ptr [edx+0x54]
    cmp  ebx, eax
    jge  test_
    movzx eax, byte ptr [esi+0xc]
    mov  edx, dword ptr [esi+8]
    lea  eax, [edx+eax*4]
    movzx eax, byte ptr [eax+ebx]
    mov  dword ptr [edi+0x18], eax
    mov  edx, edi
    mov  eax, dword ptr [esi+8]
    mov  eax, dword ptr [eax+ebx*4]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx+0xcc]
test_:
    test ebx, ebx
    je   done_
    cmp  ebp, dword ptr [edi+0x1c]
    je   loop_
done_:
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret
"""


def fixed():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(SRC, FN)
    body = bytes(enc)
    assert len(body) <= len(VANILLA), "fixed body is %d B, the slot is %d B" % (len(body), len(VANILLA))
    return body + b"\x90" * (len(VANILLA) - len(body))


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    return e, [struct.unpack_from("<IIII", d, e + 24 + opt + 40 * i + 8) for i in range(nsec)]


def va2off(d, va):
    rva = va - IMAGE_BASE
    for vsize, vaddr, rsize, raw in sections(d)[1]:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
    sys.exit("ABORT: VA %08X is in no section" % va)


def relocs_in(d, lo, hi):
    e = sections(d)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 136)
    off = va2off(d, IMAGE_BASE + rva)
    end, hits = off + size, []
    while off < end:
        page, blk = struct.unpack_from("<II", d, off)
        if blk < 8:
            break
        for k in range((blk - 8) // 2):
            ent = struct.unpack_from("<H", d, off + 8 + 2 * k)[0]
            va = IMAGE_BASE + page + (ent & 0xFFF)
            if ent >> 12 and va < hi and va + 4 > lo:
                hits.append(va)
        off += blk
    return hits


def rel32_into(d, lo, hi):
    """E8/E9 rel32 anywhere in the file that lands strictly inside (lo, hi): a call to the entry is fine."""
    hits = []
    for vsize, vaddr, rsize, raw in sections(d)[1]:
        for i in range(raw, raw + min(vsize or rsize, rsize) - 5):
            if d[i] in (0xE8, 0xE9):
                src = IMAGE_BASE + vaddr + (i - raw)
                if lo <= src < hi:
                    continue
                t = src + 5 + struct.unpack_from("<i", d, i + 1)[0]
                if lo < t < hi:
                    hits.append(src)
    return hits


def show(title, blob):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    print("\n  ---- %s @%08X (%d B)" % (title, FN, len(blob)))
    for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob, FN):
        print("    %08X  %-24s %s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))


def kill_aow():
    for n in AOW_PROCS:
        if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                          capture_output=True, text=True).returncode == 0:
            print("  killed running %s.exe" % n)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()

    new = fixed()
    d = open(TARGET, "rb").read()
    print("build_fieldmsg_hn -- %s" % TARGET)
    if os.path.exists(REFERENCE):
        ref = open(REFERENCE, "rb").read()
        o = va2off(ref, FN)
        print("  reference %s: %s" % (REFERENCE, "vanilla" if ref[o:o + len(VANILLA)] == VANILLA
                                      else "UNEXPECTED BYTES"))
    o = va2off(d, FN)
    cur = d[o:o + len(VANILLA)]
    state = "VANILLA" if cur == VANILLA else "INSTALLED" if cur == new else "FOREIGN"
    print("  SendMapFieldMsg %08X-%08X: %s" % (FN, FN_END, state))
    rl = relocs_in(d, FN, FN_END)
    inner = rel32_into(d, FN, FN_END)
    print("  .reloc inside: %s" % (", ".join("%08X" % v for v in rl) or "none"))
    print("  rel32 into the interior: %s" % (", ".join("%08X" % v for v in inner) or "none"))
    if a.dis:
        show("vanilla", VANILLA)
        show("fixed", new)
    if state == "FOREIGN":
        sys.exit("ABORT: the function holds foreign bytes: %s" % cur.hex())
    if rl or inner:
        sys.exit("ABORT: a .reloc entry or a foreign jump lands inside the function")
    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    want = new if a.apply else VANILLA
    if cur == want:
        print("\nalready %s -- nothing to do" % ("installed" if a.apply else "vanilla"))
        return
    kill_aow()
    with open(TARGET, "r+b") as f:
        f.seek(o)
        f.write(want)
    back = open(TARGET, "rb").read()
    assert back[o:o + len(want)] == want, "%08X did not stick" % FN
    print("\n%s" % ("APPLIED" if a.apply else "UNDONE -- vanilla bytes restored"))


if __name__ == "__main__":
    main()
