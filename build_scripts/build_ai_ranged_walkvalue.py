#!/usr/bin/env python
r"""
build_ai_ranged_walkvalue.py -- AI archers stop giving up a shot to walk to a marginally clearer hex.

THE VANILLA BUG (TCAI.CheckUnit's ranged handler, AoWTCPCK.dpl)
    [ebp-0x64] DEV_cur  shot value from the current hex after EvalPath (obstruction, friendly fire)
    [ebp-0x58] X        EvalPath's loss; after search (a) finds a less-obstructed hex on the path,
                        0x4179CE does X += DEV_best, i.e. X := DEV0 -- the new hex valued as CLEAN.
    shoot now (type 3, 0x417D79) = pct * DEV_cur^2 / |DEV_cur + X|
    walk      (type 5, 0x417E62) = pct * (X + pos) * X / |DEV_cur + X|
With X = DEV0 > DEV_cur, any strict improvement makes the walk win and the unit forfeits its shot.

THE FIX -- Inioch's H2/H5/H6 (patch_ai_ranged_obstacles_v1.py), nothing else of his
    H2  0x4179CE  13 B -> E9 + 8 NOPs into a PIC cave:  X := DEV_best * D / 100, where D is the
                  chance the shot is still there next turn -- BASE/HERO/LEADER_PCT by TARGET class
                  (leader first), * DANGER_PCT/100 when the SHOOTER is in mortal danger (cur HP <=
                  summed GetDamage of living enemies within GetMoves/HEX_MP + 1 hexes), := HOPELESS_PCT
                  when it is also low-value (GetTargetStrength < LOWVAL_PCT % of the strongest living
                  own unit).  The danger term is computed inside this cave from the TCAI lists; it
                  reads nothing produced by his heal package.
    H5  0x417D1D  2 B in place: `03 45` -> `EB 0D`, jumping over `add eax,[ebp-0x58]` and the abs,
                  so the shoot divisor [ebp-0x18] = max(DEV_cur, 1) and shoot = pct * DEV_cur.
                  (His H5 was a 16-byte cave hook at 0x417D2C with the same result.)
    H6  0x417E27  1 B in place: `idiv [ebp-0x18]` -> `idiv [ebp-0x58]` (disp8 E8 -> A8), so the walk
                  = pct * (X + pos).  X > 0 is guaranteed there (0x417D7E `jle` exits otherwise).
                  (His H6 was a cave writing [ebp-0x18] := X with the same result.)
The unit now walks only when DEV_best * D / 100 + pos beats the shot it has now.

DEVIATIONS, deliberate:
    * His product `imul ecx / cdq / idiv` discarded the high half; here `imul m32 / idiv` keeps it.
    * If X rounds to 0 while the current shot is FULLY blocked (DEV_cur == 0), X := 1, which keeps
      vanilla's routing (0x417C95: X != 0 and DEV_cur == 0 -> the else-branch walk) instead of
      proposing a pointless 0-value shot into the obstacle.  Only reachable when D = 0 (hopeless).
    * Not ported: his H0/H1/H3/H4/H7 ((b)-search acceptance, else-branch value), the walk-margin
      script, the heal package.  Those hooks use [ebp-0xA4]/[ebp-0x9C], which are fields of the
      16-byte valuation record at [ebp-0xA8] (lea'd at 0x415A67), not free slots.  This subset uses
      no frame slot vanilla does not already use.
    * Side effect of H2 kept: the out-of-range / already-moved walk (0x417F3C) also reads X, so it
      is now valued from the discounted best hex, not from DEV0.

Scale: every constant is a percentage or a ratio; the danger test compares HP with damage, both
doubled in Ziggurat.  HEX_MP = 4 is movement, not HP/damage, and matches vanilla's own `R*4` at
0x417B2D in the same function.  No RNG anywhere.

CAVES (zone 0x438C00..0x4393FF reserved to this script; fixed slots)
    0x438C00 h2     (hook target)
    0x438C40 udist  eax = unit A, edx = unit B -> eax = hex distance
    0x438C80 disc   ecx = 1 with danger, 0 without -> eax = D (percent); PIC via call/pop delta

USAGE
    python build_ai_ranged_walkvalue.py            verify / dry run
    python build_ai_ranged_walkvalue.py --dis      + disassemble the caves
    python build_ai_ranged_walkvalue.py --apply    write (re-tunes the caves in place when installed)
    python build_ai_ranged_walkvalue.py --undo     restore the three sites, zero the slots
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys

from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32, x86

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TARGET = os.path.join(GAME, "AoWTCPCK.dpl")
FEATURE = "airangedwalk"
BACKUP_DIR = os.path.join(GAME, "backups")

# ---- tunables (Inioch's values, percent) ----------------------------------------------------------
BASE_PCT = 65        # walk discount, ordinary target
HERO_PCT = 45        # hero target
LEADER_PCT = 30      # leader target
DANGER_PCT = 50      # multiplier when the shooter is in mortal danger
HOPELESS_PCT = 0     # discount when in danger AND low value (0 = always take the shot)
LOWVAL_PCT = 40      # "low value" = strength below this % of the strongest living own unit
HEX_MP = 4           # move points per hex for the enemy-reach estimate

# ---- engine facts ---------------------------------------------------------------------------------
ISCLASS, DHX = 0x00401058, 0x004022A4          # System.@IsClass; HSEngine.dHXtoRad (x1,y1,x2,[y2])
IAT_THERO, IAT_TLEADER, IAT_TCUNIT = 0x0046E914, 0x0046E910, 0x0046E904
H2_HOOK, H2_RESUME = 0x004179CE, 0x004179DB
H2_ORIG = bytes.fromhex("8b45d0" "0145a8" "7105" "e84d96feff")
H5_SITE, H5_ORIG, H5_NEW = 0x00417D1D, bytes.fromhex("0345"), bytes.fromhex("eb0d")
H6_SITE, H6_ORIG, H6_NEW = 0x00417E27, bytes.fromhex("e8"), bytes.fromhex("a8")
# read-only context anchors around the in-place sites
H5_CTX = (0x00417D1A, bytes.fromhex("8b459c"),                    # mov eax,[ebp-0x64] ; site follows
          bytes.fromhex("a8" "7105" "e80193feff" "9933c22bc2" "8945e8" "837de8017d07c745e801000000"))
H6_CTX = (0x00417E15, bytes.fromhex("6a01" "8b45ec" "f76da8" "7105" "e80492feff" "99" "f77d"),
          bytes.fromhex("8bc8" "8b55a8" "0355ac"))
SLOT_H2, SLOT_UDIST, SLOT_DISC, SLOTS_END = 0x00438C00, 0x00438C40, 0x00438C80, 0x00438E00
ZONE_END = 0x00439400

AOW_PROCS = ("AoW", "AoWz", "AoWCompat", "AoWzCompat", "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup")
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def cave_h2():
    return asm(f"""
        mov ecx, 1
        call {SLOT_DISC:#x}
        imul dword ptr [ebp-0x30]
        mov ecx, 100
        idiv ecx
        test eax, eax
        jne store
        cmp dword ptr [ebp-0x64], 0
        jne store
        inc eax
    store:
        mov dword ptr [ebp-0x58], eax
        jmp {H2_RESUME:#x}
    """, SLOT_H2)


def cave_udist():
    return asm(f"""
        push esi
        push edi
        mov esi, eax
        mov edi, edx
        mov eax, dword ptr [edi+0x60]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, dword ptr [edi+0x60]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        push eax
        mov eax, dword ptr [esi+0x60]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, dword ptr [esi+0x60]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        pop edx
        pop ecx
        call {DHX:#x}
        pop edi
        pop esi
        ret
    """, SLOT_UDIST)


def cave_disc():
    pre = asm("""
        push ebx
        push esi
        push edi
        sub esp, 20
        mov dword ptr [esp+12], ecx
    """, SLOT_DISC)
    anchor = SLOT_DISC + len(pre) + 5
    pre += asm("call %#x" % anchor, SLOT_DISC + len(pre))
    body = asm(f"""
        pop ebx
        sub ebx, {anchor:#x}
        mov dword ptr [esp+16], {BASE_PCT}
        mov eax, dword ptr [ebp+0x10]
        mov edx, dword ptr [ebx+{IAT_TCUNIT:#x}]
        call {ISCLASS:#x}
        test al, al
        jz cls_done
        mov eax, dword ptr [ebp+0x10]
        mov eax, dword ptr [eax+0x4c]
        test eax, eax
        jz cls_done
        mov esi, eax
        mov edx, dword ptr [ebx+{IAT_TLEADER:#x}]
        call {ISCLASS:#x}
        test al, al
        jz not_leader
        mov dword ptr [esp+16], {LEADER_PCT}
        jmp cls_done
    not_leader:
        mov eax, esi
        mov edx, dword ptr [ebx+{IAT_THERO:#x}]
        call {ISCLASS:#x}
        test al, al
        jz cls_done
        mov dword ptr [esp+16], {HERO_PCT}
    cls_done:
        cmp dword ptr [esp+12], 0
        je ret_d
        xor eax, eax
        mov dword ptr [esp], eax
        mov dword ptr [esp+4], eax
        mov dword ptr [esp+8], eax
    en_loop:
        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+0x10]
        mov ecx, dword ptr [esp+4]
        cmp ecx, dword ptr [eax+8]
        jge en_end
        mov eax, dword ptr [eax+4]
        mov esi, dword ptr [eax+ecx*4]
        inc dword ptr [esp+4]
        test esi, esi
        jz en_loop
        test byte ptr [esi+0x47], 9
        jnz en_loop
        mov eax, esi
        mov edx, dword ptr [ebp+0x14]
        call {SLOT_UDIST:#x}
        mov edi, eax
        mov eax, esi
        mov edx, dword ptr [esi]
        call dword ptr [edx+0x94]
        cdq
        mov ecx, {HEX_MP}
        idiv ecx
        inc eax
        cmp edi, eax
        jg en_loop
        mov eax, esi
        mov edx, dword ptr [esi]
        call dword ptr [edx+0x78]
        movsx eax, al
        add dword ptr [esp], eax
        jmp en_loop
    en_end:
        cmp dword ptr [esp], 0
        jle ret_d
        mov eax, dword ptr [ebp+0x14]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x88]
        movsx eax, al
        cmp eax, dword ptr [esp]
        jg ret_d
        xor eax, eax
        mov dword ptr [esp+4], eax
    own_loop:
        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+8]
        mov ecx, dword ptr [esp+4]
        cmp ecx, dword ptr [eax+8]
        jge own_end
        mov eax, dword ptr [eax+4]
        mov esi, dword ptr [eax+ecx*4]
        inc dword ptr [esp+4]
        test esi, esi
        jz own_loop
        test byte ptr [esi+0x47], 9
        jnz own_loop
        mov eax, esi
        mov edx, dword ptr [esi]
        call dword ptr [edx+0x5c]
        cmp eax, dword ptr [esp+8]
        jle own_loop
        mov dword ptr [esp+8], eax
        jmp own_loop
    own_end:
        mov eax, dword ptr [ebp+0x14]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x5c]
        imul eax, eax, 100
        mov ecx, dword ptr [esp+8]
        imul ecx, ecx, {LOWVAL_PCT}
        cmp eax, ecx
        jge in_danger
        mov dword ptr [esp+16], {HOPELESS_PCT}
        jmp ret_d
    in_danger:
        mov eax, dword ptr [esp+16]
        imul eax, eax, {DANGER_PCT}
        cdq
        mov ecx, 100
        idiv ecx
        mov dword ptr [esp+16], eax
    ret_d:
        mov eax, dword ptr [esp+16]
        add esp, 20
        pop edi
        pop esi
        pop ebx
        ret
    """, anchor)
    return pre + body


def caves():
    out = [(SLOT_H2, cave_h2(), SLOT_UDIST), (SLOT_UDIST, cave_udist(), SLOT_DISC),
           (SLOT_DISC, cave_disc(), SLOTS_END)]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    for va, blob, lim in out:
        if va + len(blob) > lim:
            sys.exit("ABORT: cave at %08X (%d B) overflows its slot" % (va, len(blob)))
        n = 0
        for ins in md.disasm(blob, va):
            n += ins.size
            for op in ins.operands:
                if op.type == x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                    sys.exit("ABORT: not PIC at %08X: %s %s" % (ins.address, ins.mnemonic, ins.op_str))
        if n != len(blob):
            sys.exit("ABORT: cave at %08X does not disassemble end to end" % va)
    return out


def slot_image(cs):
    """The full slot region 0x438C00..0x438E00 as this script writes it (zero padded)."""
    img = bytearray(SLOTS_END - SLOT_H2)
    for va, blob, _lim in cs:
        img[va - SLOT_H2:va - SLOT_H2 + len(blob)] = blob
    return bytes(img)


def h2_hook():
    return b"\xE9" + struct.pack("<i", SLOT_H2 - (H2_HOOK + 5)) + b"\x90" * (len(H2_ORIG) - 5)


# ---- PE helpers ---------------------------------------------------------------------------------
def image_base(d):
    return struct.unpack_from("<I", d, struct.unpack_from("<I", d, 0x3C)[0] + 24 + 28)[0]


def va2off(d, va):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    rva = va - image_base(d)
    for i in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, e + 24 + opt + 40 * i + 8)
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
    sys.exit("ABORT: VA %08X is in no section" % va)


def rd(d, va, n):
    o = va2off(d, va)
    return bytes(d[o:o + n])


def relocs_in(d, lo, hi):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 136)
    ib = image_base(d)
    off = va2off(d, ib + rva)
    end, hits = off + size, []
    while off < end:
        page, blk = struct.unpack_from("<II", d, off)
        if blk < 8:
            break
        for k in range((blk - 8) // 2):
            ent = struct.unpack_from("<H", d, off + 8 + 2 * k)[0]
            if ent >> 12:
                va = ib + page + (ent & 0xFFF)
                if va < hi and va + 4 > lo:
                    hits.append(va)
        off += blk
    return hits


def kill_aow():
    if os.environ.get("AOW_GAME_DIR"):
        return
    for n in AOW_PROCS:
        if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                          capture_output=True, text=True).returncode == 0:
            print("  killed running %s.exe" % n)


def state(d):
    """Per-site state; aborts on foreign bytes."""
    lo5, head5, tail5 = H5_CTX
    if rd(d, lo5, len(head5)) != head5 or rd(d, H5_SITE + 2, len(tail5)) != tail5:
        sys.exit("ABORT: context around %08X is not the vanilla shoot-divisor code" % H5_SITE)
    lo6, head6, tail6 = H6_CTX
    if rd(d, lo6, len(head6)) != head6 or rd(d, H6_SITE + 1, len(tail6)) != tail6:
        sys.exit("ABORT: context around %08X is not the vanilla walk-divisor code" % H6_SITE)
    s = {}
    h2 = rd(d, H2_HOOK, len(H2_ORIG))
    s["h2"] = "vanilla" if h2 == H2_ORIG else "ours" if h2 == h2_hook() else None
    h5 = rd(d, H5_SITE, 2)
    s["h5"] = "vanilla" if h5 == H5_ORIG else "ours" if h5 == H5_NEW else None
    h6 = rd(d, H6_SITE, 1)
    s["h6"] = "vanilla" if h6 == H6_ORIG else "ours" if h6 == H6_NEW else None
    for k2, v in s.items():
        if v is None:
            sys.exit("ABORT: site %s holds bytes that are neither vanilla nor ours" % k2)
    return s


def write_runs(runs):
    hdr = open(TARGET, "rb").read(0x1000)
    with open(TARGET, "r+b") as f:
        for va, blob in runs:
            f.seek(va2off(hdr, va))
            f.write(blob)


def main():
    ap = argparse.ArgumentParser(description="AI archers: honest shoot-vs-walk values")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()

    cs = caves()
    img = slot_image(cs)
    d = open(TARGET, "rb").read()
    st = state(d)
    live_slots = rd(d, SLOT_H2, len(img))
    caves_match = live_slots == img
    print("build_ai_ranged_walkvalue -- %s" % TARGET)
    print("discounts: base %d / hero %d / leader %d %%, danger x%d %%, hopeless %d %% (< %d %% value),"
          " reach GetMoves/%d+1" % (BASE_PCT, HERO_PCT, LEADER_PCT, DANGER_PCT, HOPELESS_PCT,
                                    LOWVAL_PCT, HEX_MP))
    for va, blob, _ in cs:
        print("  cave %08X  %3d B" % (va, len(blob)))
    print("sites: H2 %08X %s, H5 %08X %s, H6 %08X %s; caves match: %s"
          % (H2_HOOK, st["h2"], H5_SITE, st["h5"], H6_SITE, st["h6"], caves_match))
    if a.dis:
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for va, blob, _ in cs:
            print("\n  ; ---- %08X ----" % va)
            for ins in md.disasm(blob, va):
                print("    %08X  %-22s %s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))
        new = bytearray(d)
        for va, blob in ((H5_SITE, H5_NEW), (H6_SITE, H6_NEW)):
            o = va2off(new, va)
            new[o:o + len(blob)] = blob
        print("\n  ; ---- in-place sites as patched ----")
        for lo, n in ((0x00417D1A, 0x22), (0x00417E15, 0x13)):
            for ins in md.disasm(rd(new, lo, n), lo):
                print("    %08X  %-22s %s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    for lo, hi in ((H2_HOOK, H2_HOOK + len(H2_ORIG)), (H5_SITE, H5_SITE + 2), (H6_SITE, H6_SITE + 1),
                   (SLOT_H2, ZONE_END)):
        if relocs_in(d, lo, hi):
            sys.exit("ABORT: a .reloc entry covers %08X..%08X" % (lo, hi))

    if a.undo:
        if all(v == "vanilla" for v in st.values()):
            print("\nnothing to undo")
            return
        kill_aow()
        if state(open(TARGET, "rb").read()) != st:
            sys.exit("ABORT: the sites changed under us -- re-run")
        write_runs([(H2_HOOK, H2_ORIG), (H5_SITE, H5_ORIG), (H6_SITE, H6_ORIG),
                    (SLOT_H2, b"\0" * len(img))])
        back = open(TARGET, "rb").read()
        assert all(v == "vanilla" for v in state(back).values()) and not any(rd(back, SLOT_H2, len(img)))
        print("\nUNDONE (three sites restored, slots %08X..%08X zeroed) -- no backup touched"
              % (SLOT_H2, SLOTS_END))
        return

    # --apply
    if all(v == "ours" for v in st.values()) and caves_match:
        print("\nalready installed, bytes identical -- nothing to do")
        return
    if st["h2"] == "vanilla" and any(live_slots):
        sys.exit("ABORT: slots %08X..%08X are not zero but the hook is vanilla" % (SLOT_H2, SLOTS_END))
    if any(rd(d, SLOTS_END, ZONE_END - SLOTS_END)):
        sys.exit("ABORT: zone %08X..%08X is not zero" % (SLOTS_END, ZONE_END))
    kill_aow()
    if all(v == "vanilla" for v in st.values()):        # snapshot only a file PROVED unpatched here
        backup = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-" + FEATURE)
        if not os.path.exists(backup):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(TARGET, backup)
            print("\nbackup -> %s" % backup)
    if state(open(TARGET, "rb").read()) != st:
        sys.exit("ABORT: the sites changed under us -- re-run")
    write_runs([(SLOT_H2, img), (H2_HOOK, h2_hook()), (H5_SITE, H5_NEW), (H6_SITE, H6_NEW)])
    back = open(TARGET, "rb").read()
    assert all(v == "ours" for v in state(back).values()) and rd(back, SLOT_H2, len(img)) == img
    print("\nAPPLIED: H2 %08X -> %08X, H5 %08X = EB 0D, H6 %08X = A8"
          % (H2_HOOK, SLOT_H2, H5_SITE, H6_SITE))


if __name__ == "__main__":
    main()
