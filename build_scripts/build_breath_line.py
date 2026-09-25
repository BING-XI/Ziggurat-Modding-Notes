r"""Breath attacks and Flame Throwing: each damaging strike's obstruction line runs to the hex that
strike damages and stops there.  Ported from Inioch's `patch_breath_line_v1.py` (share8, RE only;
his cave VA is not reused).

    file   AoWTCPCK.dpl only (tactical combat).  Auto-resolve never reaches it: AoWEPACK does not
           import AoWTCPCK, and TCAbRangedTE is created only by TTacticalCombatUnitHS.AbRangedTC.
    hook   0x0040D5F1  CombatTE.TCAbRangedTE.NextStrike, category-5 case (0x40D345..0x40D72F),
           5 B `6A 32 8B 45 FC` (push 0x32 / mov eax,[ebp-4]) = first push of the MakeRangedPath
           call at 0x40D65F.  No .reloc in the window; the only branch to it is the merge jump at
           0x40D5C6 (to its first byte).
    cave   0x00439400  (reservation 0x439400-0x4397FF, inside the CODE zero run 0x438080-0x466BAC)

Vanilla
-------
Category 5 = Flame Throwing 0x1E, Fire/Cold/Black/Divine/Poison Breath 0x56-0x5A (byte table
[0x4693DC]).  Execute sets 20 strikes ([te+0x28] = 0x14).  Strike s draws its line with
MakeRangedPath(shooter -> aim hex [ebp-0x48]/[ebp-0x4C] + pixel offset [ebp-0x3C]/[ebp-0x40]),
the aim hex being BreathHN[dir*12-3] (ring-4 centre) and the offset the fan sweep at
(f*6-30) deg, f = s (s>9: 19-s).  Only strikes 0-11 damage: after the call, 0x40D671-0x40D72A
stores BreathHN[BreathDir[HN-1]*12 + BreathHit[s] - 12] (HN = dHXtoHN(shooter, target)) in
[ca+0x24]/[ca+0x28].  The block loop 0x40EE41 rolls TAoWHSMap.Random(100) (SYNCED) per block
record of that fan line; a hit zeroes [ca+0x24] (0x40F06F) and truncates the drawn points.  So a
strike is blocked by whatever its sweep angle crosses, out to full depth: side walls eat corridor
strikes and obstacles beyond the damaged hex cancel it.

The cave
--------
For s < 12 it recomputes that same damage hex (same functions, same inputs, same tables, read
through the relocated DATA slots 0x469404/0x46940C/0x469414 via a call/pop anchor) into
[ebp-0x48]/[ebp-0x4C] and zeroes the offsets, so the line runs centre to centre and MakeRangedPath
skips its own end hex.  Every range check (s 0..11, HN 1..60 = vanilla's bound at 0x40F44C,
index 0..71 = 0x40F454) runs BEFORE anything is written; on any failure the frame is untouched
and vanilla runs.  (Inioch's version zeroed the offsets first and then checked the dHXtoHN result
against 1..6, reading it as a direction; it is a spiral index.)  Strikes 12-19 are untouched.

Drawn flame: CHANGED, by necessity.  The drawn points [ca+0x1C] and the block list come from the
one MakeRangedPath call, and the block loop reads each block's hex back out of the drawn points
(record+4 = point index) and truncates them.  Keeping the fan would need a second MakeRangedPath
call, a second hook after the block loop, freeing the first call's block records (its
TList.Clear does not) and a truncation pass - and would then draw correctly-unblocked corridor
strikes through the side walls, with the impact splash at the fan's end instead of on the damaged
hex.  So strikes 0-11 now fly to the hex they damage (or stop at the blocker), and the cosmetic
return sweep 12-19 keeps the vanilla full-length fan.

Multiplayer: the cave makes no draw.  It changes how many SYNCED Random(100) block rolls vanilla
makes, identically on every peer: the line is a function of the shooter's hex, the streamed
target hex, [te+0x34] and static tables - the inputs vanilla already uses for the damage hex.
The TE ends only when the effect list is empty (0x40CB16), so a longer path cannot lose damage.

In-game checklist (owner):
  1. A dragon breathing down a 1-hex corridor hits enemies in the cone along the corridor.
  2. An obstacle beyond the target no longer cancels the hit on it.
  3. An obstacle between breather and target still blocks (by its block chance).
  4. Flame Throwing behaves the same.
  5. The spray animation is acceptable: 12 flames of varying length to the damaged hexes, then
     the vanilla 8-flame return sweep.

Usage:
    python build_breath_line.py            # verify current state (dry run)
    python build_breath_line.py --dis      # + disassemble the cave
    python build_breath_line.py --apply    # write (kills running AoW binaries first)
    python build_breath_line.py --undo     # surgical revert: hook restored, reservation zeroed
"""
import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
import capstone      # noqa: E402
import keystone      # noqa: E402
import zigexe        # noqa: E402

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

FEATURE = "breathline"
TARGET_NAME = "AoWTCPCK.dpl"
REFERENCE = os.path.join(os.path.dirname(GAME), TARGET_NAME)     # the vanilla root copy

HOOK = 0x0040D5F1
RESUME = 0x0040D5F6
VANILLA_HOOK = bytes.fromhex("6A328B45FC")
CAVE = 0x00439400
ZONE = 0x400

STRIKES = 12
DHXTOHN = 0x004022B4          # thunk -> HSEngine.dHXtoHN(x1, y1, x2, [y2]) -> HN 1..60
CENTERHNTOHX = 0x004022AC     # thunk -> HSEngine.CenterHNtoHX(cx, cy, hn, [var x], [var y])
P_BREATHDIR = 0x00469404      # -> AoWTC.BreathDir 0x4673A8, 60 dwords, HN -> dir 1..6
P_BREATHHN = 0x0046940C       # -> AoWTC.BreathHN  0x467498, 6 x 12 dwords
P_BREATHHIT = 0x00469414      # -> AoWTC.BreathHit 0x467378, 12 dwords, strike -> cone entry

# vanilla fingerprints of the code the cave mirrors (hook window zeroed in the first)
CONTEXT = [
    ("NextStrike case-5 body", 0x0040D345, 0x0040D734,
     "5c38e6b30630d7a54f066d0ec0cbcaa13601d5a1b89fa1c313a2ac292df03441"),
    ("MakeRangedPath", 0x00427630, 0x00427DB0,
     "40b762e937195ce1bf3c9d0800a535b9d6334c1a0b28431e2c494b46a1925fa9"),
]


class PEFile:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as fh:
            self.data = fh.read()
        d = self.data
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        opt = struct.unpack_from("<H", d, pe + 20)[0]
        self.base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
        self.datadir = pe + 24 + 96
        self.sections = []
        for i in range(nsec):
            s = pe + 24 + opt + i * 40
            vsize, vaddr, rawsz, raw = struct.unpack_from("<IIII", d, s + 8)
            self.sections.append((d[s:s + 8].rstrip(b"\0").decode("latin1"),
                                  vaddr, vsize, raw, rawsz))

    def off(self, va):                         # VA -> file offset is PER SECTION
        rva = va - self.base
        for _, vaddr, vsize, raw, rawsz in self.sections:
            if vaddr <= rva < vaddr + max(vsize, rawsz):
                return raw + (rva - vaddr)
        raise SystemExit(f"VA {va:#x} in no section")

    def read(self, va, n):
        o = self.off(va)
        return self.data[o:o + n]

    def relocs_in(self, lo, hi):
        rva, size = struct.unpack_from("<II", self.data, self.datadir + 5 * 8)
        p = self.off(self.base + rva)
        end, hits = p + size, []
        while p < end:
            page, blk = struct.unpack_from("<II", self.data, p)
            if blk < 8:
                break
            for i in range((blk - 8) // 2):
                e = struct.unpack_from("<H", self.data, p + 8 + 2 * i)[0]
                va = self.base + page + (e & 0xFFF)
                if e >> 12 and lo <= va < hi:
                    hits.append(va)
            p += blk
        return hits


def asm_src(anchor):
    return "\n".join([
        "push ebx", "push esi", "push edi",
        "mov esi, dword ptr [ebp-4]",
        "mov edi, dword ptr [esi+0x34]",
        f"cmp edi, {STRIKES}",
        "jae done",
        "mov eax, dword ptr [esi+0x10]", "mov eax, dword ptr [eax+0x60]",
        "mov edx, dword ptr [eax]", "call dword ptr [edx+0x78]",
        "movsx ebx, al",
        "mov eax, dword ptr [esi+0x10]", "mov eax, dword ptr [eax+0x60]",
        "mov edx, dword ptr [eax]", "call dword ptr [edx+0x74]",
        "movsx eax, al",
        "push ebx", "push eax",
        "movzx edx, word ptr [esi+0x22]", "push edx",
        "movzx ecx, word ptr [esi+0x20]",
        "mov edx, ebx",
        f"call {DHXTOHN:#x}",
        "lea edx, [eax-1]",
        "cmp edx, 60",
        "jae bail",
        "call anchor",
        "anchor:",
        "pop ebx",
        f"sub ebx, {anchor:#x}",
        f"mov edx, dword ptr [ebx+{P_BREATHDIR:#x}]",
        "mov eax, dword ptr [edx+eax*4-4]",
        "imul eax, eax, 12",
        f"mov edx, dword ptr [ebx+{P_BREATHHIT:#x}]",
        "add eax, dword ptr [edx+edi*4]",
        "sub eax, 12",
        "cmp eax, 72",
        "jae bail",
        f"mov edx, dword ptr [ebx+{P_BREATHHN:#x}]",
        "mov ecx, dword ptr [edx+eax*4]",
        "pop eax", "pop edx",
        "lea ebx, [ebp-0x48]", "push ebx",
        "lea ebx, [ebp-0x4c]", "push ebx",
        f"call {CENTERHNTOHX:#x}",
        "xor eax, eax",
        "mov dword ptr [ebp-0x3c], eax",
        "mov dword ptr [ebp-0x40], eax",
        "jmp done",
        "bail:",
        "add esp, 8",
        "done:",
        "pop edi", "pop esi", "pop ebx",
        "push 0x32",
        "mov eax, dword ptr [ebp-4]",
        f"jmp {RESUME:#x}",
    ])


def build_cave():
    """Two passes: the anchor's own VA is an imm32 in the source."""
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32)
    first = bytes(ks.asm(asm_src(0x40000000), CAVE)[0])
    i = first.find(b"\xE8\x00\x00\x00\x00\x5B\x81\xEB")
    if i < 0:
        raise SystemExit("anchor sequence not found in pass 1")
    anchor = CAVE + i + 5
    blob = bytes(ks.asm(asm_src(anchor), CAVE)[0])
    if len(blob) != len(first) or blob[i + 8:i + 12] != struct.pack("<I", anchor):
        raise SystemExit("pass 2 layout differs from pass 1")
    if len(blob) > ZONE:
        raise SystemExit(f"cave {len(blob)} B exceeds the reservation")
    # the displaced pair must be replayed byte-exact (keystone imm8 trap: 6A 32, not 68 ...)
    if blob[-10:-5] != VANILLA_HOOK or blob[-5] != 0xE9:
        raise SystemExit("displaced-instruction replay is not 6A 32 8B 45 FC + E9")
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    targets, bad = set(), []
    for ins in md.disasm(blob, CAVE):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                bad.append(f"{ins.address:#x} {ins.mnemonic} {ins.op_str}")
        if ins.mnemonic in ("call", "jmp") and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            t = ins.operands[0].imm
            if not CAVE <= t < CAVE + len(blob):
                targets.add(t)
    if bad:
        raise SystemExit("cave is NOT position-independent: " + "; ".join(bad))
    if targets != {DHXTOHN, CENTERHNTOHX, RESUME}:
        raise SystemExit("unexpected external targets: " + ", ".join(map(hex, sorted(targets))))
    return blob


def hook_bytes():
    return b"\xE9" + struct.pack("<i", CAVE - (HOOK + 5))


def disasm(blob, va):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    return "\n".join(f"      {i.address:08X}  {i.bytes.hex(' ').upper():<24} {i.mnemonic:<6} {i.op_str}"
                     for i in md.disasm(blob, va))


def context_ok(pe):
    ok = True
    for name, lo, hi, want in CONTEXT:
        b = bytearray(pe.read(lo, hi - lo))
        if lo <= HOOK < hi:
            b[HOOK - lo:RESUME - lo] = b"\0" * (RESUME - HOOK)
        same = hashlib.sha256(bytes(b)).hexdigest() == want
        ok &= same
        print(f"  context: {name} {'vanilla' if same else 'MODIFIED'}")
    return ok


def kill_game():
    if os.environ.get("AOW_GAME_DIR") or sys.platform != "win32":
        return
    names = "|".join(zigexe.LOCKING_PROCESSES)
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                    f"Get-Process | Where-Object {{ $_.ProcessName -match '^({names})$' }}"
                    " | Stop-Process -Force"], capture_output=True)


def state_of(live_hook, live_zone, blob):
    if live_hook == VANILLA_HOOK:
        return "vanilla" if live_zone == b"\0" * ZONE else "zone-occupied"
    if live_hook == hook_bytes():
        return "installed" if live_zone == blob + b"\0" * (ZONE - len(blob)) else "retune"
    return "foreign"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", "--show", dest="dis", action="store_true")
    a = ap.parse_args()
    if a.apply and a.undo:
        raise SystemExit("--apply and --undo are mutually exclusive")

    path = os.path.join(GAME, TARGET_NAME)
    blob = build_cave()
    pe = PEFile(path)
    print(f"=== Ziggurat\\{TARGET_NAME} (image base {pe.base:#x}) ===")
    print(f"  hook  {HOOK:#010x} NextStrike category-5 case, 5 B, resume {RESUME:#010x}")
    print(f"  cave  {CAVE:#010x} {len(blob)} B (reservation {CAVE:#x}-{CAVE + ZONE - 1:#x})")
    rel = pe.relocs_in(HOOK, RESUME) + pe.relocs_in(CAVE, CAVE + ZONE)
    if rel:
        raise SystemExit("ABORT: .reloc under the patch: " + ", ".join(map(hex, rel)))
    print("  .reloc: clear across the hook window and the reservation; cave is PIC")
    ctx = context_ok(pe)
    st = state_of(pe.read(HOOK, 5), pe.read(CAVE, ZONE), blob)
    print(f"  state: {st} (hook now {pe.read(HOOK, 5).hex(' ').upper()})")
    if a.dis:
        print("\n  --- cave ---\n" + disasm(blob, CAVE))
        print("\n  --- hook after --apply ---\n" + disasm(hook_bytes(), HOOK))
    if st in ("foreign", "zone-occupied"):
        raise SystemExit(f"ABORT: {st} - another patch owns the hook site or the reservation")

    if a.undo:
        if st == "vanilla":
            print("  nothing to undo")
            return
        kill_game()
        with open(path, "r+b") as fh:            # re-verify under the write handle
            fh.seek(pe.off(HOOK))
            if fh.read(5) != hook_bytes():
                raise SystemExit("ABORT: hook changed since the read")
            fh.seek(pe.off(HOOK))
            fh.write(VANILLA_HOOK)
            fh.seek(pe.off(CAVE))
            fh.write(b"\0" * ZONE)
        print("  UNDONE (hook restored, reservation zeroed, no backup touched)")
        return

    if st == "installed":
        print("  installed, bytes identical - nothing to do")
        return
    if not a.apply:
        print("\n  DRY RUN - nothing written. Re-run with --apply.")
        return
    if not ctx:
        raise SystemExit("ABORT: the code this cave mirrors is not vanilla - re-derive first")

    kill_game()
    if st == "vanilla":
        fresh = True
        if os.path.isfile(REFERENCE):
            ref = PEFile(REFERENCE)
            fresh = ref.read(HOOK, 5) == VANILLA_HOOK and ref.read(CAVE, ZONE) == b"\0" * ZONE
        if fresh:
            bdir = os.path.join(GAME, "backups")
            os.makedirs(bdir, exist_ok=True)
            bak = os.path.join(bdir, f"{TARGET_NAME}.pre-{FEATURE}")
            if not os.path.exists(bak):
                shutil.copy2(path, bak)
                print(f"  backup -> backups\\{os.path.basename(bak)}")
    else:
        print("  re-tune: rewriting the cave in place, no backup")
    with open(path, "r+b") as fh:                # re-verify under the write handle
        fh.seek(pe.off(HOOK))
        now_hook = fh.read(5)
        fh.seek(pe.off(CAVE))
        now_zone = fh.read(ZONE)
        if state_of(now_hook, now_zone, blob) != st:
            raise SystemExit("ABORT: file changed since the read")
        fh.seek(pe.off(CAVE))
        fh.write(blob + b"\0" * (ZONE - len(blob)))
        fh.seek(pe.off(HOOK))
        fh.write(hook_bytes())
    print("  APPLIED")


if __name__ == "__main__":
    main()
