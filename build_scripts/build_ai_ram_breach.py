#!/usr/bin/env python
r"""
build_ai_ram_breach.py -- after a wall breach the tactical AI stops focusing harmless wall crushers.

WHY
---
A combat object's target value is `TCombatUnit.GetTargetStrength` (VMT+0x5C, AoWEPACK 0x55725850 ->
0x55726454): the average DV over its target list `[obj+0x10]` (TQuadItemList, 16-byte entries
A obj / B CV / C wall CV / D DV), filled once per combat by `SetupTargets 0x557264AC` -- walls
included.  `TWallCrushingAbility` scores 0 against units, so a ram's whole value is wall potential,
and nothing re-reads it after a breach.  Rams never retaliate, so hitting one stays pure gain.

THE HOOK -- inside `TCAI.tcDVtoDEV 0x413664`, the target-value fetch (8 bytes, no .reloc)
    00413673  8B 45 08      mov  eax,[ebp+8]        ; TARGET
    00413676  8B 10         mov  edx,[eax]
    00413678  FF 52 5C      call [edx+0x5c]         ; GetTargetStrength
    0041367B  89 45 EC      mov  [ebp-0x14],eax     ; <- resume
-> E9 to the cave at 0x438800 + 3 NOPs.  The cave re-runs the three instructions, then scales the
value by RAM_VALUE_PCT/100 when ALL hold:
    * walls breached: [[[combatmap 0x46C064]+0xE4]+0xC]+0x4D != 0 (TCombatData; set by
      TCombatWall.DestroyObject 0x55725C64 when any section dies);
    * TARGET IsClass TCombatUnit (IAT 0x46E904);
    * TARGET is an enemy of the AI evaluating: GetSide(TARGET) != [cai+4]  (cai = [ebp-4]);
    * TARGET has Wall Crushing 0x75 (TCombatObject VMT+0xA8);
    * TARGET is harmless to units: no entry of its own target list has A IsClass TCombatUnit and
      D > 0 -- the game's own numbers (rams, drills, transports; Giants/Ents/Elementals keep theirs).
-100 % makes the ram worth minus its value: hit last, still finished off when nothing else is
proposed (phase 4 sorts without dropping negatives).  Before the breach nothing changes.

DEVIATION FROM HIS SCRIPT (patch_ai_ram_focus_v1.py): he tested GetSide(TARGET) != GetSide(SELF).
`MakeTerrainPath` 0x413E53 prices an attack of opportunity with TARGET = the AI's OWN mover and
SELF = the adjacent enemy, so his test devalued the AI's own ram there and turned the AoO cost into a
bonus.  Testing against the AI's side byte [cai+4] (the idiom of EvalAll 0x41464D) excludes it.
Everything else in tcDVtoDEV's 20 callers is unchanged in kind: a ram standing in a shot line (EvalHex)
or caught by a mass spell (EvalAll) is now cheap -- accepted.

PIC: `call $+5 / pop ebx / sub ebx, anchor` gives the load delta; the two in-image absolutes
(0x46C064, IAT 0x46E904) are read as [ebx+VA].  Calls are rel32.  No RNG.  Pure ratio, no rescale.

USAGE
    python build_ai_ram_breach.py            verify / dry run
    python build_ai_ram_breach.py --dis      + disassemble the cave
    python build_ai_ram_breach.py --apply    write (re-tunes RAM_VALUE_PCT in place when installed)
    python build_ai_ram_breach.py --undo     restore the 8 hook bytes, zero the cave
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
FEATURE = "airambreach"
BACKUP_DIR = os.path.join(GAME, "backups")

# ---- tunable ------------------------------------------------------------------------------------
RAM_VALUE_PCT = -100      # harmless crusher's value after a breach, % of vanilla (-128..127)

# ---- engine facts -------------------------------------------------------------------------------
HOOK = 0x00413673
HOOK_ORIG = bytes.fromhex("8b4508" "8b10" "ff525c")
RESUME = 0x0041367B
RESUME_BYTES = bytes.fromhex("8945ec")        # mov [ebp-0x14],eax -- sanity anchor
CAVE, ZONE_END = 0x00438800, 0x00438C00       # zone owned by this script
ISCLASS = 0x00401058                          # thunk System.@IsClass(eax obj, edx class) -> al
GETSIDE = 0x0040252C                          # thunk AoWE.TCombatObject.GetSide(eax) -> al
G_COMBATMAP = 0x0046C064
IAT_TCOMBATUNIT = 0x0046E904
WALL_CRUSHING = 0x75

AOW_PROCS = ("AoW", "AoWz", "AoWCompat", "AoWzCompat", "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup")
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build(pct):
    pre = """
        mov eax, [ebp+8]
        mov edx, [eax]
        call dword ptr [edx+0x5c]
        push ebx
        push esi
        push edi
        push eax
    """
    p = asm(pre, CAVE)
    anchor = CAVE + len(p) + 5
    p += asm("call %#x" % anchor, CAVE + len(p))
    body = f"""
        pop ebx
        sub ebx, {anchor:#x}
        mov eax, dword ptr [ebx+{G_COMBATMAP:#x}]
        test eax, eax
        jz done
        mov eax, dword ptr [eax+0xe4]
        test eax, eax
        jz done
        mov eax, dword ptr [eax+0xc]
        test eax, eax
        jz done
        cmp byte ptr [eax+0x4d], 0
        je done
        mov eax, dword ptr [ebp+8]
        mov edx, dword ptr [ebx+{IAT_TCOMBATUNIT:#x}]
        call {ISCLASS:#x}
        test al, al
        jz done
        mov eax, dword ptr [ebp+8]
        call {GETSIDE:#x}
        mov edx, dword ptr [ebp-4]
        cmp al, byte ptr [edx+4]
        je done
        mov edx, {WALL_CRUSHING:#x}
        mov eax, dword ptr [ebp+8]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0xa8]
        test al, al
        jz done
        mov esi, dword ptr [ebp+8]
        mov esi, dword ptr [esi+0x10]
        test esi, esi
        jz done
        mov edi, dword ptr [esi+8]
        mov esi, dword ptr [esi+4]
    scan:
        dec edi
        js harmless
        mov ecx, edi
        shl ecx, 4
        cmp dword ptr [esi+ecx+0xc], 0
        jle scan
        mov eax, dword ptr [esi+ecx]
        test eax, eax
        jz scan
        mov edx, dword ptr [ebx+{IAT_TCOMBATUNIT:#x}]
        call {ISCLASS:#x}
        test al, al
        jz scan
        jmp done
    harmless:
        mov eax, dword ptr [esp]
        imul eax, eax, {pct}
        cdq
        mov ecx, 100
        idiv ecx
        mov dword ptr [esp], eax
    done:
        pop eax
        pop edi
        pop esi
        pop ebx
        jmp {RESUME:#x}
    """
    p += asm(body, anchor)
    return p


def hook_bytes():
    return b"\xE9" + struct.pack("<i", CAVE - (HOOK + 5)) + b"\x90" * (len(HOOK_ORIG) - 5)


def check_pic(blob):
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    for ins in md.disasm(blob, CAVE):
        for op in ins.operands:
            if op.type == x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                sys.exit("ABORT: cave not PIC at %08X: %s %s" % (ins.address, ins.mnemonic, ins.op_str))
    if sum(i.size for i in md.disasm(blob, CAVE)) != len(blob):
        sys.exit("ABORT: cave does not disassemble cleanly end to end")


def dis(blob):
    for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob, CAVE):
        print("    %08X  %-22s %s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))


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


def rd(d, va, n):
    o = va2off(d, va)
    return bytes(d[o:o + n])


def kill_aow():
    if os.environ.get("AOW_GAME_DIR"):
        return
    for n in AOW_PROCS:
        if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                          capture_output=True, text=True).returncode == 0:
            print("  killed running %s.exe" % n)


def state(d):
    """('vanilla'|'installed', installed_pct or None).  Aborts on anything else."""
    if rd(d, RESUME, 3) != RESUME_BYTES:
        sys.exit("ABORT: %08X is not `mov [ebp-0x14],eax` -- wrong build" % RESUME)
    hk = rd(d, HOOK, len(HOOK_ORIG))
    if hk == HOOK_ORIG:
        return "vanilla", None
    if hk != hook_bytes():
        sys.exit("ABORT: hook %08X holds %s -- neither vanilla nor ours" % (HOOK, hk.hex(" ")))
    for p in range(-128, 128):
        b = build(p)
        if rd(d, CAVE, len(b)) == b:
            return "installed", p
    sys.exit("ABORT: hook is ours but the cave at %08X is not a layout this script writes" % CAVE)


def write_runs(runs):
    with open(TARGET, "r+b") as f:
        for va, blob in runs:
            f.seek(va2off(open(TARGET, "rb").read(0x1000), va))
            f.write(blob)


def main():
    ap = argparse.ArgumentParser(description="AI stops focusing harmless wall crushers after a breach")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    if not -128 <= RAM_VALUE_PCT <= 127:
        sys.exit("RAM_VALUE_PCT must fit imm8 (-128..127)")

    blob = build(RAM_VALUE_PCT)
    check_pic(blob)
    if CAVE + len(blob) > ZONE_END:
        sys.exit("ABORT: cave overflows its zone")
    d = open(TARGET, "rb").read()
    st, cur_pct = state(d)
    print("build_ai_ram_breach -- %s" % TARGET)
    print("hook %08X -> cave %08X (%d B, zone to %08X)   value after breach %d %%"
          % (HOOK, CAVE, len(blob), ZONE_END, RAM_VALUE_PCT))
    print("state: %s" % (st.upper() + ("" if cur_pct is None else " (pct %d)" % cur_pct)))
    if a.dis:
        dis(blob)

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    if relocs_in(d, HOOK, HOOK + len(HOOK_ORIG)) or relocs_in(d, CAVE, ZONE_END):
        sys.exit("ABORT: a .reloc entry covers the hook or the cave zone")

    if a.undo:
        if st == "vanilla":
            print("\nnothing to undo")
            return
        old = build(cur_pct)
        kill_aow()
        fresh = open(TARGET, "rb").read()
        if state(fresh) != (st, cur_pct):
            sys.exit("ABORT: the site changed under us -- re-run")
        write_runs([(HOOK, HOOK_ORIG), (CAVE, b"\0" * len(old))])
        back = open(TARGET, "rb").read()
        assert rd(back, HOOK, 8) == HOOK_ORIG and rd(back, CAVE, len(old)) == b"\0" * len(old)
        print("\nUNDONE (hook restored, %d cave bytes zeroed) -- no backup touched" % len(old))
        return

    # --apply
    if st == "installed" and cur_pct == RAM_VALUE_PCT:
        print("\nalready installed, bytes identical -- nothing to do")
        return
    old_len = len(build(cur_pct)) if st == "installed" else 0
    tail = rd(d, CAVE + old_len, (ZONE_END - CAVE) - old_len)
    if any(tail):
        sys.exit("ABORT: cave zone %08X..%08X is not zero beyond our bytes" % (CAVE + old_len, ZONE_END))
    kill_aow()
    if st == "vanilla":                      # snapshot only a file PROVED unpatched here
        backup = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-" + FEATURE)
        if not os.path.exists(backup):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(TARGET, backup)
            print("\nbackup -> %s" % backup)
    fresh = open(TARGET, "rb").read()
    if state(fresh) != (st, cur_pct):
        sys.exit("ABORT: the site changed under us -- re-run")
    pad = b"\0" * max(0, old_len - len(blob))
    write_runs([(CAVE, blob + pad), (HOOK, hook_bytes())])  # cave first, then the jump into it
    back = open(TARGET, "rb").read()
    assert state(back) == ("installed", RAM_VALUE_PCT), "write did not stick"
    print("\nAPPLIED: hook %08X = %s, cave %08X..%08X"
          % (HOOK, hook_bytes().hex(" "), CAVE, CAVE + len(blob)))


if __name__ == "__main__":
    main()
