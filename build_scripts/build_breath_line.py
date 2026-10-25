r"""Breath attacks and Flame Throwing: each damaging strike's obstruction line runs to the hex that
strike damages and stops there; the flame is drawn on vanilla's sweep, cut at the first obstacle
or at the blocking distance.  Damage half ported from Inioch's `patch_breath_line_v1.py` (share8,
RE only; his cave VA is not reused); the drawn sweep added 2026-10-22.

    file   AoWTCPCK.dpl only (tactical combat).  Auto-resolve never reaches it: AoWEPACK does not
           import AoWTCPCK, and TCAbRangedTE is created only by TTacticalCombatUnitHS.AbRangedTC.
    hook A 0x0040D5F1  CombatTE.TCAbRangedTE.NextStrike, category-5 case (0x40D345..0x40D72F),
           5 B `6A 32 8B 45 FC` (push 0x32 / mov eax,[ebp-4]) = first push of the MakeRangedPath
           call at 0x40D65F.  No .reloc in the window; the only branch to it is the merge jump at
           0x40D5C6 (to its first byte).
    hook B 0x0040F0B1  category-5 tail after the block loop, 8 B `8B 45 F0 33 D2 89 50 2C`
           (mov eax,[ebp-0x10] / xor edx,edx / mov [eax+0x2C],edx), replayed byte-exact at the end
           of cave B, which resumes at the `jmp 0x40F227` (0x40F0B9).  No .reloc, no branch inside.
    caves  A 0x00439400 (220 B), B 0x004394E0 (607 B); reservation 0x439400-0x4397FF, inside the
           CODE zero run 0x438080-0x466BAC.
    state  G 0x0046CA20-0x0046CA43, BSS, 9 dwords: latch te/s, saved sweep aim x/y/ox/oy, D2, hex.

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

Cave A (damage line)
--------------------
It first saves te, s and vanilla's sweep aim ([ebp-0x48]/[ebp-0x4C], [ebp-0x3C]/[ebp-0x40]) in G.
For s < 12 it recomputes that same damage hex (same functions, same inputs, same tables, read
through the relocated DATA slots 0x469404/0x46940C/0x469414 via a call/pop anchor) into
[ebp-0x48]/[ebp-0x4C] and zeroes the offsets, so the line runs centre to centre and MakeRangedPath
skips its own end hex.  Every range check (s 0..11, HN 1..60 = vanilla's bound at 0x40F44C,
index 0..71 = 0x40F454) runs BEFORE anything is written; on any failure the frame is untouched
and vanilla runs.  (Inioch's version zeroed the offsets first and then checked the dHXtoHN result
against 1..6, reading it as a direction; it is a spiral index.)  Strikes 12-19 are untouched.

Cave B (drawn flame)
--------------------
The drawn points [ca+0x1C] and the block list come from the one MakeRangedPath call, and the
block loop reads each block's hex back out of the drawn points (record+4 = point index), so
cave A alone would draw the damage line.  After the block loop has decided the strike, cave B
(latched on te and s from G, s < 12 only) notes the blocking distance when [ca+0x24] was zeroed
(D2 = squared pixel length of the truncated damage line, + 1), frees the damage line's block
records (MakeRangedPath's TList.Clear does not), calls MakeRangedPath again with the saved
vanilla aim, then cuts that sweep after the first record whose hex passes the block loop's own
obstacle test, and, if the strike was blocked, back to the blocking distance.  The epilogue
0x40F3F7 frees the sweep's records.  Strikes 12-19 are untouched.

The cut is deterministic at every obstacle, so the drawn flame also stops at obstacles vanilla
blocks only by chance (an adjacent wall 50 %, overlay 8 by height).  Only the drawing differs.

Multiplayer: neither cave draws, and MakeRangedPath has no Random call (0x427630-0x427DAD).
Cave A changes how many SYNCED Random(100) block rolls vanilla makes, identically on every peer:
the line is a function of the shooter's hex, the streamed target hex, [te+0x34] and static
tables - the inputs vanilla already uses for the damage hex.  Cave B runs after the last roll.
The TE ends only when the effect list is empty (0x40CB16), so path length cannot lose damage.

Couplings: build_combatlog_siege.py hooks 0x40F05E/0x40F079 inside the block loop, before hook B;
build_extrashots.py bumps [te+0x34] at 0x40F436, after it.  Neither shares bytes with this script.

Unproven: [ca+0x24] = 0 is read as "blocked"; a damaged hex in column 0 would also read so and
trim the drawn flame to the damage line's length.

Usage:
    python build_breath_line.py            # verify current state (dry run)
    python build_breath_line.py --dis      # + disassemble both caves
    python build_breath_line.py --apply    # write (kills running AoW binaries first)
    python build_breath_line.py --undo     # surgical revert: both hooks restored, reservation zeroed
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

# --- the drawn sweep (hook B, 2026-10-22) ---
HOOK_B = 0x0040F0B1           # category-5 tail after the block loop: mov eax,[ebp-0x10] / xor edx,edx
VANILLA_HOOK_B = bytes.fromhex("8B45F033D289502C")       #   / mov [eax+0x2C],edx
RESUME_B = 0x0040F0B9         # vanilla `jmp 0x40F227`
G = 0x0046CA20                # BSS state, 9 dwords: te, s, x, y, ox, oy, D2, hx, hy (no file bytes)
MRP = 0x00427630              # AoWTC.MakeRangedPath
GETSIDE = 0x0040252C          # thunk -> AoWE.TCombatObject.GetSide
LIST_GET = 0x0040153C         # thunk -> Classes.TList.Get(list, i)
OBJ_FREE = 0x00401050         # thunk -> System.TObject.Free
XYZ_DEL, XYZ_GET, XYZ_CNT = 0x00402DEC, 0x00402DF4, 0x00402DFC   # aowFX.TXYZList Delete/GetXYZ/GetCount
GETMAPLEVEL = 0x00401E64      # thunk -> HSEngine.TMapContainer.GetMapLevel(container, 0)
GETFIELD = 0x00401E54         # thunk -> HSEngine.TMapLevel.GetField(level, x, y)
HPTOHX = 0x004022C4           # thunk -> HSEngine.HPtoHX(px, py, var hx, [var hy])
P_MAP = 0x00469420            # DATA slot -> the combat map; [[map]+0x10] = its TMapContainer
BLOCK_TAGS = (0x220166, 0x220504, 0x220506)   # the block loop's obstacle objects (0x40EF00/32/64)

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
    """Cave A.  Saves te, s and the vanilla sweep aim (hex [ebp-0x48]/[ebp-0x4C], pixel offset
    [ebp-0x3C]/[ebp-0x40]) in G for cave B, then (s < 12) re-aims the line at the damage hex.
    The rebase delta is kept on the stack between the save and the table reads."""
    return "\n".join([
        "push ebx", "push esi", "push edi",
        "call anchor",
        "anchor:",
        "pop ebx",
        f"sub ebx, {anchor:#x}",
        "mov esi, dword ptr [ebp-4]",
        "mov edi, dword ptr [esi+0x34]",
        f"mov dword ptr [ebx+{G:#x}], esi",
        f"mov dword ptr [ebx+{G + 4:#x}], edi",
        "mov eax, dword ptr [ebp-0x48]", f"mov dword ptr [ebx+{G + 8:#x}], eax",
        "mov eax, dword ptr [ebp-0x4c]", f"mov dword ptr [ebx+{G + 0xC:#x}], eax",
        "mov eax, dword ptr [ebp-0x3c]", f"mov dword ptr [ebx+{G + 0x10:#x}], eax",
        "mov eax, dword ptr [ebp-0x40]", f"mov dword ptr [ebx+{G + 0x14:#x}], eax",
        f"cmp edi, {STRIKES}",
        "jae done",
        "push ebx",
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
        "mov ebx, dword ptr [esp+8]",
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
        "add esp, 4",
        "jmp done",
        "bail:",
        "add esp, 12",
        "done:",
        "pop edi", "pop esi", "pop ebx",
        "push 0x32",
        "mov eax, dword ptr [ebp-4]",
        f"jmp {RESUME:#x}",
    ])


def sweep_src(anchor):
    """Cave B, entered by `jmp` from HOOK_B (category 5 only, after the block loop).  For a damaging
    strike (s < 12) whose latch in G matches this TE and strike:
      1. the damage line was blocked when the loop zeroed [fx+0x24]; D2 = squared pixel distance
         from the first to the last point of the (truncated) damage line, else D2 = 0;
      2. free the damage line's block records ([ebp-0x5C]; MakeRangedPath's TList.Clear does not
         free them, and the epilogue 0x40F3F7 frees whatever the list holds afterwards);
      3. MakeRangedPath again with vanilla's saved sweep aim, exactly as 0x40D5F1..0x40D65F calls it:
         [fx+0x1C] = the vanilla sweep (TXYZList.Clear frees the old points), [ebp-0x5C] = its records;
      4. cut the sweep after the first record whose hex holds a blocker -- the block loop's own
         test (objects 0x220166/0x220504/0x220506, terrain 0xF/7, overlay 8); every record
         MakeRangedPath makes has chance > 0, so the chance check is only a guard;
      5. if blocked, also cut it back to the blocking distance (points farther than D2 dropped).
    No Random call anywhere (MakeRangedPath draws none).  Then the replayed tail and RESUME_B."""
    tags = "\n".join(f"""
        mov  eax, edx
        push edx
        mov  edx, {t:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx+0x80]
        pop  edx
        test eax, eax
        jne  b_cut""" for t in BLOCK_TAGS)
    return f"""
        pushad
        call anchor
    anchor:
        pop  ebx
        sub  ebx, {anchor:#x}
        mov  edi, dword ptr [ebp-4]
        mov  esi, dword ptr [edi+0x34]
        cmp  esi, {STRIKES}
        jae  b_out
        cmp  dword ptr [ebx+{G:#x}], edi
        jne  b_out
        cmp  dword ptr [ebx+{G + 4:#x}], esi
        jne  b_out
        mov  dword ptr [ebx+{G:#x}], 0
        mov  esi, dword ptr [ebp-0x10]
        mov  dword ptr [ebx+{G + 0x18:#x}], 0
        cmp  dword ptr [esi+0x24], 0
        jg   b_free
        mov  dword ptr [ebx+{G + 0x18:#x}], 1
        mov  eax, dword ptr [esi+0x1c]
        call {XYZ_CNT:#x}
        cmp  eax, 2
        jl   b_free
        lea  edx, [eax-1]
        mov  eax, dword ptr [esi+0x1c]
        call {XYZ_GET:#x}
        push dword ptr [eax+8]
        push dword ptr [eax+4]
        xor  edx, edx
        mov  eax, dword ptr [esi+0x1c]
        call {XYZ_GET:#x}
        pop  ecx
        sub  ecx, dword ptr [eax+4]
        imul ecx, ecx
        pop  edx
        sub  edx, dword ptr [eax+8]
        imul edx, edx
        add  ecx, edx
        inc  ecx
        mov  dword ptr [ebx+{G + 0x18:#x}], ecx
    b_free:
        mov  eax, dword ptr [ebp-0x5c]
        mov  edi, dword ptr [eax+8]
    b_fl:
        dec  edi
        js   b_mrp
        mov  edx, edi
        mov  eax, dword ptr [ebp-0x5c]
        call {LIST_GET:#x}
        call {OBJ_FREE:#x}
        jmp  b_fl
    b_mrp:
        mov  edi, dword ptr [ebp-4]
        push 0x32
        mov  eax, dword ptr [edi+0x10]
        mov  eax, dword ptr [eax+0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        push eax
        mov  eax, dword ptr [edi+0x10]
        mov  eax, dword ptr [eax+0x60]
        mov  edx, dword ptr [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        push dword ptr [ebx+{G + 8:#x}]
        push dword ptr [ebx+{G + 0xC:#x}]
        push dword ptr [ebx+{G + 0x10:#x}]
        push dword ptr [ebx+{G + 0x14:#x}]
        push 0
        lea  eax, [esi+0x1c]
        push eax
        lea  eax, [ebp-0x5c]
        push eax
        mov  eax, dword ptr [edi+0x10]
        call {GETSIDE:#x}
        mov  cx, 0x14
        mov  dx, 0x32
        call {MRP:#x}
        xor  edi, edi
    b_rec:
        mov  eax, dword ptr [ebp-0x5c]
        cmp  edi, dword ptr [eax+8]
        jge  b_dist
        mov  edx, edi
        call {LIST_GET:#x}
        cmp  dword ptr [eax+8], 0
        jle  b_next
        push dword ptr [eax+4]
        mov  edx, dword ptr [eax+4]
        mov  eax, dword ptr [esi+0x1c]
        call {XYZ_GET:#x}
        lea  ecx, [ebx+{G + 0x20:#x}]
        push ecx
        lea  ecx, [ebx+{G + 0x1C:#x}]
        mov  edx, dword ptr [eax+8]
        mov  eax, dword ptr [eax+4]
        call {HPTOHX:#x}
        mov  eax, dword ptr [ebx+{P_MAP:#x}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax+0x10]
        xor  edx, edx
        call {GETMAPLEVEL:#x}
        mov  ecx, dword ptr [ebx+{G + 0x20:#x}]
        mov  edx, dword ptr [ebx+{G + 0x1C:#x}]
        call {GETFIELD:#x}
        test eax, eax
        je   b_skip
        mov  edx, eax
        movsx eax, byte ptr [edx+0x14]
        cmp  eax, 0xf
        je   b_cut
        cmp  eax, 7
        je   b_cut
        movsx eax, byte ptr [edx+0x15]
        cmp  eax, 8
        je   b_cut
{tags}
    b_skip:
        add  esp, 4
    b_next:
        inc  edi
        jmp  b_rec
    b_cut:
        pop  edi
    b_cut2:
        mov  eax, dword ptr [esi+0x1c]
        call {XYZ_CNT:#x}
        lea  edx, [edi+1]
        cmp  eax, edx
        jle  b_dist
        lea  edx, [eax-1]
        mov  eax, dword ptr [esi+0x1c]
        call {XYZ_DEL:#x}
        jmp  b_cut2
    b_dist:
        cmp  dword ptr [ebx+{G + 0x18:#x}], 0
        je   b_out
    b_d2:
        mov  eax, dword ptr [esi+0x1c]
        call {XYZ_CNT:#x}
        cmp  eax, 2
        jl   b_out
        mov  edi, eax
        lea  edx, [eax-1]
        mov  eax, dword ptr [esi+0x1c]
        call {XYZ_GET:#x}
        push dword ptr [eax+8]
        push dword ptr [eax+4]
        xor  edx, edx
        mov  eax, dword ptr [esi+0x1c]
        call {XYZ_GET:#x}
        pop  ecx
        sub  ecx, dword ptr [eax+4]
        imul ecx, ecx
        pop  edx
        sub  edx, dword ptr [eax+8]
        imul edx, edx
        add  ecx, edx
        inc  ecx
        cmp  ecx, dword ptr [ebx+{G + 0x18:#x}]
        jle  b_out
        lea  edx, [edi-1]
        mov  eax, dword ptr [esi+0x1c]
        call {XYZ_DEL:#x}
        jmp  b_d2
    b_out:
        popad
    """


def build_sweep(va):
    """Two passes like build_cave: the anchor's own VA is an imm32 in the source."""
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32)
    first = bytes(ks.asm(sweep_src(0x40000000), va)[0])
    i = first.find(b"\xE8\x00\x00\x00\x00\x5B\x81\xEB")
    if i < 0:
        raise SystemExit("cave B: anchor sequence not found")
    anchor = va + i + 5
    blob = bytes(ks.asm(sweep_src(anchor), va)[0])
    if len(blob) != len(first) or blob[i + 8:i + 12] != struct.pack("<I", anchor):
        raise SystemExit("cave B: pass 2 layout differs from pass 1")
    # the replayed tail, byte-exact (keystone would emit 31 D2 for vanilla's 33 D2), then jmp back
    blob += VANILLA_HOOK_B
    blob += b"\xE9" + struct.pack("<i", RESUME_B - (va + len(blob) + 5))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    targets, bad, n = set(), [], 0
    for ins in md.disasm(blob, va):
        n += ins.size
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                bad.append(f"{ins.address:#x} {ins.mnemonic} {ins.op_str}")
        if ins.mnemonic in ("call", "jmp") and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            t = ins.operands[0].imm
            if not va <= t < va + len(blob):
                targets.add(t)
    if n != len(blob):
        raise SystemExit("cave B does not disassemble cleanly")
    if bad:
        raise SystemExit("cave B is NOT position-independent: " + "; ".join(bad))
    want = {XYZ_CNT, XYZ_GET, XYZ_DEL, LIST_GET, OBJ_FREE, GETSIDE, MRP, HPTOHX, GETMAPLEVEL,
            GETFIELD, RESUME_B}
    if targets != want:
        raise SystemExit("cave B: unexpected external targets: " + ", ".join(map(hex, sorted(targets ^ want))))
    if blob[-13:-5] != VANILLA_HOOK_B or blob[-14] != 0x61 or blob[-5] != 0xE9:
        raise SystemExit("cave B: tail is not popad + the replayed 8 bytes + jmp")
    return blob


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


def build_zone():
    """-> (the whole reservation's bytes, cave B's VA): cave A at CAVE, cave B 16-aligned after it."""
    a = build_cave()
    b_va = (CAVE + len(a) + 0xF) & ~0xF
    b = build_sweep(b_va)
    if b_va + len(b) > CAVE + ZONE:
        raise SystemExit(f"caves end at {b_va + len(b):#x}, past the reservation")
    zone = a + b"\0" * (b_va - CAVE - len(a)) + b
    return zone + b"\0" * (ZONE - len(zone)), b_va


def hook_b_bytes(b_va):
    return b"\xE9" + struct.pack("<i", b_va - (HOOK_B + 5)) + b"\x90" * 3


def ours_b(live_b):
    """Hook B holds a jmp into our reservation (this build's or an earlier layout's)."""
    if len(live_b) < 5 or live_b[0] != 0xE9:
        return False
    t = HOOK_B + 5 + struct.unpack("<i", live_b[1:5])[0]
    return CAVE <= t < CAVE + ZONE and live_b[5:] == b"\x90" * 3


def branches_into_b(pe):
    """Relative branches inside NextStrike (0x40D290..0x40F440) landing strictly inside hook B."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    lo, hi = 0x0040D290, 0x0040F440
    bad = []
    for ins in md.disasm(pe.read(lo, hi - lo), lo):
        if HOOK_B <= ins.address < HOOK_B + 8:
            continue
        if ins.mnemonic.startswith("j") or ins.mnemonic == "call":
            try:
                t = int(ins.op_str, 16)
            except ValueError:
                continue
            if HOOK_B < t < HOOK_B + 8:
                bad.append(ins.address)
    return bad


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


def state_of(live_hook, live_b, live_zone, zone, b_va):
    if live_hook == VANILLA_HOOK:
        if live_b != VANILLA_HOOK_B:
            return "foreign"
        return "vanilla" if live_zone == b"\0" * ZONE else "zone-occupied"
    if live_hook == hook_bytes():
        if live_b == hook_b_bytes(b_va) and live_zone == zone:
            return "installed"
        if live_b == VANILLA_HOOK_B or ours_b(live_b):
            return "retune"
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
    zone, b_va = build_zone()
    a_len = len(build_cave())
    pe = PEFile(path)
    print(f"=== Ziggurat\\{TARGET_NAME} (image base {pe.base:#x}) ===")
    print(f"  hook A {HOOK:#010x} NextStrike category-5 case, 5 B, resume {RESUME:#010x}")
    print(f"  hook B {HOOK_B:#010x} category-5 tail after the block loop, 8 B, resume {RESUME_B:#010x}")
    print(f"  cave A {CAVE:#010x} {a_len} B, cave B {b_va:#010x} {len(zone.rstrip(bytes(1))) - (b_va - CAVE)} B "
          f"(reservation {CAVE:#x}-{CAVE + ZONE - 1:#x}); state G {G:#x}..{G + 0x24:#x} (BSS)")
    rel = pe.relocs_in(HOOK, RESUME) + pe.relocs_in(HOOK_B, HOOK_B + 8) + pe.relocs_in(CAVE, CAVE + ZONE)
    if rel:
        raise SystemExit("ABORT: .reloc under the patch: " + ", ".join(map(hex, rel)))
    inner = branches_into_b(pe)
    if inner:
        raise SystemExit("ABORT: a branch lands inside hook B: " + ", ".join(map(hex, inner)))
    print("  .reloc: clear across both hook windows and the reservation; no branch into hook B; caves are PIC")
    ctx = context_ok(pe)
    live_b = pe.read(HOOK_B, 8)
    st = state_of(pe.read(HOOK, 5), live_b, pe.read(CAVE, ZONE), zone, b_va)
    print(f"  state: {st} (hook A {pe.read(HOOK, 5).hex(' ').upper()}, hook B {live_b.hex(' ').upper()})")
    if a.dis:
        print("\n  --- caves ---\n" + disasm(zone[:a_len], CAVE) + "\n" +
              disasm(zone[b_va - CAVE:].rstrip(bytes(1)), b_va))
        print("\n  --- hooks after --apply ---\n" + disasm(hook_bytes(), HOOK) + "\n" +
              disasm(hook_b_bytes(b_va), HOOK_B))
    if st in ("foreign", "zone-occupied"):
        raise SystemExit(f"ABORT: {st} - another patch owns a hook site or the reservation")

    if a.undo:
        if st == "vanilla":
            print("  nothing to undo")
            return
        kill_game()
        with open(path, "r+b") as fh:            # re-verify under the write handle
            fh.seek(pe.off(HOOK))
            if fh.read(5) != hook_bytes():
                raise SystemExit("ABORT: hook A changed since the read")
            fh.seek(pe.off(HOOK_B))
            nb = fh.read(8)
            if nb != VANILLA_HOOK_B and not ours_b(nb):
                raise SystemExit("ABORT: hook B changed since the read")
            fh.seek(pe.off(HOOK))
            fh.write(VANILLA_HOOK)
            fh.seek(pe.off(HOOK_B))
            fh.write(VANILLA_HOOK_B)
            fh.seek(pe.off(CAVE))
            fh.write(b"\0" * ZONE)
        print("  UNDONE (both hooks restored, reservation zeroed, no backup touched)")
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
        fh.seek(pe.off(HOOK_B))
        now_b = fh.read(8)
        fh.seek(pe.off(CAVE))
        now_zone = fh.read(ZONE)
        if state_of(now_hook, now_b, now_zone, zone, b_va) != st:
            raise SystemExit("ABORT: file changed since the read")
        fh.seek(pe.off(CAVE))
        fh.write(zone)
        fh.seek(pe.off(HOOK))
        fh.write(hook_bytes())
        fh.seek(pe.off(HOOK_B))
        fh.write(hook_b_bytes(b_va))
    print("  APPLIED")


if __name__ == "__main__":
    main()
