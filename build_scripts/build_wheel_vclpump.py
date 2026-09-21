#!/usr/bin/env python3
r"""
build_wheel_vclpump.py -- mouse-wheel scrolling, foundation half 2 of 2: vcl30.dpl.

Spec: Modding Resources/Zig notes/Mouse_Wheel_Scrolling.md (aow-pm, 2026-09-02).
Reference (NEVER run it -- same target filename, GAME one level up):
  Modding Resources/Inioch/share5/patch scripts/build_wheel_vcl_pump.py

WHY THIS SHAPE
--------------
The game receives ZERO WM_MOUSEWHEEL (its render window is never the focused window; measured by
Inioch's probe), so no queue / WndProc / WH_MOUSE design can see the wheel. Only WH_MOUSE_LL does,
and a low-level hook's callback runs on the thread that INSTALLED it at the mouse's report rate
(~1000/s for a gaming mouse) -- owning it on the render thread cost frame rate and ghosted the cursor.
So:

  * H5  Forms.TApplication.ProcessMessage+0x25 = 0x4133BA6D, the 5-byte `cmp dword [esp+8],WM_QUIT`
        right after PeekMessageA succeeded, becomes `call PUMP`. The cave ends by replaying that
        compare at its shifted offset (`cmp dword [esp+0xC],0x12; ret`), so the caller's `je` still
        sees the flags. The site is reached only when a message WAS retrieved -- which is why the LL
        proc's WM_NULL wake-up post is load-bearing for "wheel while the mouse is still".
  * PUMP 0x413A8A00 (game thread, every retrieved message):
        - refreshes G_HWND from every non-zero msg.hwnd (the wake-up target must stay alive);
        - resolves aowInt.dpl's base once into G_AOWBASE (0 = unresolved, -1 = absent, so an
          aowInt-less process never calls GetModuleHandleA per message forever);
        - validates the CONTRACT HEADER at aowInt RVA 0x24000: magic 'AZWH' and major == 1. This is
          the ONLY aowInt address hard-coded here; everything else (latch block RVA + count, helper
          slots) is read from the header, so a changed helper prologue can no longer break anything
          (Inioch's signature-byte coupling silently killed his wheel once);
        - G1: creates the WH_MOUSE_LL owner thread lazily, the first time the header is valid AND
          any latch is non-zero. (!) The editors import 23 aowInt symbols INCLUDING the
          TAOWWinManager VMT, so H1/CLR runs there too; whether a latch can ever arm in an editor is
          UNPROVEN -- verify with re_tools/wheel_probe.py that G_THREADED stays 0 in AoWDevEd.exe;
        - drains G_PENDING in whole notches: n = G_PENDING / 120 toward zero, |n| <= 8,
          `lock sub` n*120 back, and per notch calls the header's helper slots in order until one
          returns 1 (a sub-120 touchpad/free-spin remainder waits for the next notch).
  * LL   0x413A8B80 LowLevelMouseProc (owner thread; must not touch UI): G2 gating, in order:
          nCode == 0, wParam == WM_MOUSEWHEEL, G_AOWBASE valid + magic present, any latch != 0,
          GetWindowThreadProcessId(GetForegroundWindow()) == G_PID, and
          GetWindowThreadProcessId(WindowFromPoint(GetCursorPos())) == G_PID.
        All hold -> `lock add` the raw delta to G_PENDING, PostMessageA(G_HWND, WM_NULL) to wake the
        game thread, return 1 (swallow). Otherwise CallNextHookEx -- another application's wheel is
        never swallowed. GetCursorPos (logical pixels, what a DPI-unaware process sees), not
        MSLLHOOKSTRUCT.pt (physical). The two Win32 calls run only on wheel events.
  * TH   0x413A8D00 owner thread: SetWindowsHookExA(WH_MOUSE_LL=14, LL, hMod = delta+0x41300000, 0)
        then WaitMessage / PeekMessageA(PM_REMOVE) forever. Idle cost ~0.

Globals (.idata slack 0x413E713C..0x413E7200, RW, raw-backed; DATA's 44 B is left for others):
    G_PENDING 0x413E7140  G_HWND 0x413E7144  G_THREADED 0x413E7148  G_PID 0x413E714C
    G_AOWBASE 0x413E7150  G_HHOOK 0x413E7154  (0x413E7158..0x413E717F spare)
    --diag counters 0x413E7180.. (16 dwords), read live with re_tools/wheel_probe.py.
IAT slots (all already imported, resolved by name 2026-09-02; reached as `call [delta+slot]`):
    GetModuleHandleA 0x413E43BC  CreateThread 0x413E41E8  GetCurrentProcessId 0x413E43EC
    SetWindowsHookExA 0x413E463C  CallNextHookEx 0x413E4894  PostMessageA 0x413E46C8
    PeekMessageA 0x413E46CC  WaitMessage 0x413E4604  GetForegroundWindow 0x413E47C0
    GetWindowThreadProcessId 0x413E4744  GetCursorPos 0x413E47DC  WindowFromPoint 0x413E45FC
Every cave is position-independent (`call $+5; pop; sub reg,<VA>` delta); the only string is the
NUL-preceded leaf "aowInt.dpl" in the pump cave. CODE file = VA - 0x41300C00, DATA - 0x41301200,
.idata - 0x41302A00 (section-aware va2off below). Caves 0x413A8A00..0x413A8D80 in the CODE zero tail
(content ends 0x413A8306): PUMP 0x413A8A00 (0x180), LL 0x413A8B80 (0x180), TH 0x413A8D00 (0x80) --
the spec's 0x100-each plan did not hold the pump (see PUMP_BUDGET). 0x413A8400..0x413A8A00 belongs
to build_wheel_editor.py.

Processes that load vcl30.dpl: AoW.exe, AoWCompat.exe, AoWDevEd.exe, AoWEd.exe -- exactly the
standing kill list. No exe is patched, so there is no AoWCompat lockstep step.

Usage
  python build_scripts/build_wheel_vclpump.py            dry run: site/cave/global state + chain
  python build_scripts/build_wheel_vclpump.py --apply    patch (backup vcl30.dpl.pre-wheelpump, once,
                                                         only from a proven-unpatched file)
  python build_scripts/build_wheel_vclpump.py --undo     surgical: restore H5, zero caves + globals
  python build_scripts/build_wheel_vclpump.py --dis      disassemble every cave (read it!)
  --diag   build with live counters; re-apply rewrites the caves in place
Apply order: build_wheel_aowint.py first, then this. Undo order: this first, then aowint.
"""
import os
import re
import shutil
import struct
import sys

from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32, x86

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
VCL = os.path.join(GAME, "vcl30.dpl")
INT = os.path.join(GAME, "aowInt.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(VCL) + ".pre-wheelpump")

DIAG = "--diag" in sys.argv

# ---- vcl30.dpl map ----
IMAGE_BASE = 0x41300000
MOD_LO, MOD_HI = 0x41300000, 0x41440000
# The spec pencilled in 0x100 per cave (pump 0x413A8A00 / LL 0x413A8B00 / thread 0x413A8C00). The
# pump's mandated header validation + lazy thread creation + notch loop assembles to 316 B (364 B
# --diag), so the three caves are laid out at 0x180/0x180/0x80 in the same free tail instead. The
# pump stays at 0x413A8A00 (the H5 call targets it); nothing else claims 0x413A8A00..0x413A8D80.
PUMP_VA, PUMP_BUDGET = 0x413A8A00, 0x180
LL_VA, LL_BUDGET = 0x413A8B80, 0x180
TH_VA, TH_BUDGET = 0x413A8D00, 0x80
OWN_CODE_LO, OWN_CODE_HI = 0x413A8A00, 0x413A8D80

G_PENDING, G_HWND, G_THREADED = 0x413E7140, 0x413E7144, 0x413E7148
G_PID, G_AOWBASE, G_HHOOK = 0x413E714C, 0x413E7150, 0x413E7154
CNT = 0x413E7180                                   # --diag counters, 16 dwords
OWN_DATA_LO, OWN_DATA_HI = 0x413E7140, 0x413E7200

IAT = dict(GetModuleHandleA=0x413E43BC, CreateThread=0x413E41E8, GetCurrentProcessId=0x413E43EC,
           SetWindowsHookExA=0x413E463C, CallNextHookEx=0x413E4894, PostMessageA=0x413E46C8,
           PeekMessageA=0x413E46CC, WaitMessage=0x413E4604, GetForegroundWindow=0x413E47C0,
           GetWindowThreadProcessId=0x413E4744, GetCursorPos=0x413E47DC, WindowFromPoint=0x413E45FC)

H5_SITE, H5_ORIG = 0x4133BA6D, bytes.fromhex("837c240812")   # cmp dword [esp+8], WM_QUIT
PUMP_TAIL = bytes.fromhex("837c240c12c3")                     # cmp dword [esp+0xC],0x12 ; ret

WM_MOUSEWHEEL, WH_MOUSE_LL, NOTCH, MAX_NOTCHES, HELPER_SLOTS = 0x20A, 14, 120, 8, 4

# ---- the aowInt contract (the only aowInt facts this half knows) ----
AOW_IMAGE_BASE = 0x59800000
HDR_RVA, MAGIC, MAJOR = 0x24000, 0x48575A41, 1
# for the chain verdict only:
AOW_H1_SITE, AOW_H1_ORIG, AOW_CLR_VA = 0x59807094, bytes.fromhex("558bec83c4f4"), 0x59824040

KILL_HINT = ("the DLL is locked by a running AoW binary -- kill it and retry:\n"
             "  Get-Process | Where-Object { $_.ProcessName -match '^(AoW|AoWCompat|AoWDevEd|AoWEd)$' }"
             " | Stop-Process -Force")

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)
cs.detail = True


# ============================================================ PE helpers
class Module:
    def __init__(self, path, image_base):
        self.path = path
        self.d = bytearray(open(path, "rb").read())
        d = self.d
        e = struct.unpack_from("<I", d, 0x3C)[0]
        assert d[e:e + 4] == b"PE\0\0", "not a PE: %s" % path
        n = struct.unpack_from("<H", d, e + 6)[0]
        oh = struct.unpack_from("<H", d, e + 0x14)[0]
        self.image_base = struct.unpack_from("<I", d, e + 0x34)[0]
        assert self.image_base == image_base, "%s: image base %#x, expected %#x" % (
            path, self.image_base, image_base)
        self.secs = []
        for i in range(n):
            o = e + 0x18 + oh + i * 40
            name = d[o:o + 8].rstrip(b"\0").decode("latin1")
            vs, va, rs, ptr = struct.unpack_from("<IIII", d, o + 8)
            ch = struct.unpack_from("<I", d, o + 36)[0]
            self.secs.append((name, va, vs, rs, ptr, ch))
        self.reloc_dir = struct.unpack_from("<II", d, e + 0x18 + 96 + 5 * 8)

    def off(self, va, n=1, write=False):
        r = va - self.image_base
        for name, sva, vs, rs, ptr, ch in self.secs:
            if sva <= r < sva + max(vs, rs):
                if r + n - sva > rs:
                    raise ValueError("VA %#x+%#x runs past raw data of %s" % (va, n, name))
                if write and not (ch & 0x80000000):
                    raise ValueError("VA %#x is in %s which is not writable (%08X)" % (va, name, ch))
                return ptr + (r - sva)
        raise ValueError("VA %#x is in no section" % va)

    def read(self, va, n):
        o = self.off(va, n)
        return bytes(self.d[o:o + n])

    def write(self, va, blob):
        o = self.off(va, len(blob))
        self.d[o:o + len(blob)] = blob

    def rva2off(self, rva):
        for name, sva, vs, rs, ptr, ch in self.secs:
            if sva <= rva < sva + max(vs, rs):
                return ptr + rva - sva
        return None

    def reloc_hits(self, ranges):
        rrva, rsz = self.reloc_dir
        off = self.rva2off(rrva)
        if off is None or not rsz:
            return []
        franges = [(self.off(lo), self.off(lo) + (hi - lo)) for lo, hi in ranges]
        end, hits = off + rsz, []
        while off < end:
            page, blk = struct.unpack_from("<II", self.d, off)
            if blk < 8:
                break
            for i in range((blk - 8) // 2):
                w = struct.unpack_from("<H", self.d, off + 8 + i * 2)[0]
                if w >> 12 == 0:
                    continue
                fo = self.rva2off(page + (w & 0xFFF))
                if fo is None:
                    continue
                for lo, hi in franges:
                    if lo <= fo + 3 and fo < hi:
                        hits.append(fo)
            off += blk
        return hits


# ============================================================ assembler helpers
def asm(src, base):
    enc, _ = ks.asm(src, base)
    return bytes(enc)


def dis_lines(blob, base, title, code_len=None):
    n = len(blob) if code_len is None else code_len
    out = ["  --- %s @ %08X (%d B%s) ---" % (title, base, len(blob),
                                            "" if code_len is None else ", %d B code" % code_len)]
    for i in cs.disasm(blob[:n], base):
        out.append("    %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if code_len is not None and code_len < len(blob):
        out.append("    %08X  data: %s" % (base + code_len, blob[code_len:]))
    return out


def pic_lint(blob, base, title, code_len=None):
    n = len(blob) if code_len is None else code_len
    bad, prev = [], None
    for i in cs.disasm(blob[:n], base):
        rel = i.bytes[0] in (0xE8, 0xE9, 0xEB) or 0x70 <= i.bytes[0] <= 0x7F or (
            i.bytes[0] == 0x0F and 0x80 <= i.bytes[1] <= 0x8F)
        for op in i.operands:
            if op.type == x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                bad.append("%s: %08X %s %s  (absolute memory operand)" % (title, i.address,
                                                                           i.mnemonic, i.op_str))
            if op.type == x86.X86_OP_IMM and MOD_LO <= (op.imm & 0xFFFFFFFF) < MOD_HI and not rel:
                delta_idiom = (i.mnemonic == "sub" and prev is not None and prev.mnemonic == "pop"
                               and (op.imm & 0xFFFFFFFF) == prev.address)
                if not delta_idiom:
                    bad.append("%s: %08X %s %s  (module VA as immediate)" % (
                        title, i.address, i.mnemonic, i.op_str))
        prev = i
    return bad


def check_push_imm8(blob, base, title, code_len=None):
    n = len(blob) if code_len is None else code_len
    bad = []
    for i in cs.disasm(blob[:n], base):
        if i.mnemonic == "push" and i.bytes[0] == 0x6A and i.bytes[1] >= 0x80:
            bad.append("%s: %08X push imm8 sign-extended: %s" % (title, i.address, i.op_str))
    return bad


def pad(blob, budget, name):
    assert len(blob) <= budget, "%s is %d B, over its %d B budget" % (name, len(blob), budget)
    return blob + bytes(budget - len(blob))


def cnt(idx):
    return "inc dword ptr [ebx+%#x]" % (CNT + 4 * idx) if DIAG else ""


def diag(line):
    return line if DIAG else ""


# ============================================================ the caves
def src_pump():
    return "\n".join([
        "pushad",
        "call Lp", "Lp:", "pop ebx", "sub ebx, Lp",                 # ebx = load delta
        cnt(0),
        # ---- keep a live window handle for the LL proc's wake-up post
        "mov eax, [esp+0x28]",                                       # msg.hwnd (pushad + retaddr)
        "test eax, eax",
        "jz Lnohwnd",
        "mov [ebx+%#x], eax" % G_HWND,
        "Lnohwnd:",
        # ---- aowInt base: resolve once; -1 = absent
        "mov esi, [ebx+%#x]" % G_AOWBASE,
        "test esi, esi",
        "jnz Lhavebase",
        "lea eax, [ebx+Lstr]",
        "push eax",
        "call dword ptr [ebx+%#x]" % IAT["GetModuleHandleA"],
        "test eax, eax",
        "jnz Lstore",
        "or eax, -1",
        "Lstore:",
        "mov [ebx+%#x], eax" % G_AOWBASE,
        "mov esi, eax",
        "Lhavebase:",
        "cmp esi, -1",
        "je Ldone",
        # ---- contract header: magic + major, else fail-safe (never call anything)
        "cmp dword ptr [esi+%#x], %#x" % (HDR_RVA, MAGIC),
        "jne Ldone",
        "cmp word ptr [esi+%#x], %d" % (HDR_RVA + 6, MAJOR),
        "jne Ldone",
        cnt(1),
        "mov edi, [esi+%#x]" % (HDR_RVA + 8),                        # latch block RVA
        "add edi, esi",
        "mov ecx, [esi+%#x]" % (HDR_RVA + 0xC),                      # latch count
        "test ecx, ecx",
        "jz Ldone",
        "xor eax, eax",
        "Lor:",
        "or eax, [edi+ecx*4-4]",
        "dec ecx",
        "jnz Lor",
        # ---- G1: the hook-owner thread exists only once something has been hovered
        "test eax, eax",
        "jz Ldrain",
        "cmp dword ptr [ebx+%#x], 0" % G_THREADED,
        "jne Ldrain",
        "mov dword ptr [ebx+%#x], 1" % G_THREADED,
        "call dword ptr [ebx+%#x]" % IAT["GetCurrentProcessId"],
        "mov [ebx+%#x], eax" % G_PID,                                # before CreateThread
        "push 0",                                                    # lpThreadId
        "push 0",                                                    # dwCreationFlags
        "push 0",                                                    # lpParameter
        "lea eax, [ebx+%#x]" % TH_VA,
        "push eax",                                                  # lpStartAddress
        "push 0",                                                    # dwStackSize
        "push 0",                                                    # lpThreadAttributes
        "call dword ptr [ebx+%#x]" % IAT["CreateThread"],
        diag("mov [ebx+%#x], eax" % (CNT + 4 * 2)),
        # ---- drain whole notches, toward zero, at most MAX_NOTCHES per message
        "Ldrain:",
        "mov eax, [ebx+%#x]" % G_PENDING,
        "test eax, eax",
        "jz Ldone",
        diag("mov [ebx+%#x], eax" % (CNT + 4 * 13)),
        "cdq",
        "mov ecx, %d" % NOTCH,
        "idiv ecx",
        "test eax, eax",
        "jz Ldone",
        "cmp eax, %d" % MAX_NOTCHES,
        "jle Lc1",
        "mov eax, %d" % MAX_NOTCHES,
        "Lc1:",
        "cmp eax, %d" % -MAX_NOTCHES,
        "jge Lc2",
        "mov eax, %d" % -MAX_NOTCHES,
        "Lc2:",
        "imul ecx, eax, %d" % NOTCH,
        "lock sub dword ptr [ebx+%#x], ecx" % G_PENDING,
        "mov ecx, eax",                                              # count (signed)
        "mov edx, %d" % NOTCH,                                       # per-notch delta
        "test eax, eax",
        "jns Lnotch",
        "neg ecx",
        "neg edx",
        "Lnotch:",                                                   # ecx = |n| > 0, edx = +/-120
        cnt(14),
        "xor edi, edi",
        "Lslot:",
        "mov eax, [esi+edi*4+%#x]" % (HDR_RVA + 0x10),                # helper slot RVA
        "test eax, eax",
        "jz Lnextslot",
        "add eax, esi",
        "push ecx",
        "push edx",
        diag("mov [ebx+%#x], edx" % (CNT + 4 * 5)),
        cnt(3),
        "push edx",                                                  # stdcall(delta)
        "call eax",                                                  # helper: ret 4, eax = handled
        "pop edx",
        "pop ecx",
        "test eax, eax",
        "jnz Lhandled",
        "Lnextslot:",
        "inc edi",
        "cmp edi, %d" % HELPER_SLOTS,
        "jl Lslot",
        "jmp Lnotchdone",
        "Lhandled:",
        cnt(4),
        "Lnotchdone:",
        "dec ecx",
        "jnz Lnotch",
        "Ldone:",
        "popad",
        "cmp dword ptr [esp+0xC], 0x12",                             # displaced cmp, shifted
        "ret",                                                       # flags survive for the je
        ".byte 0",                                                   # NUL-preceded leaf name
        "Lstr:",
        '.ascii "aowInt.dpl"',
        ".byte 0",
    ])


def src_ll():
    return "\n".join([
        "push ebp", "mov ebp, esp",
        "sub esp, 0xC",                                              # -4 pid, -0xC POINT
        "push ebx", "push esi", "push edi",
        "call Lp", "Lp:", "pop ebx", "sub ebx, Lp",
        cnt(6),
        "cmp dword ptr [ebp+8], 0",                                  # nCode == HC_ACTION
        "jne Ltail",
        "cmp dword ptr [ebp+0xC], %#x" % WM_MOUSEWHEEL,
        "jne Ltail",
        cnt(7),
        "mov esi, [ebx+%#x]" % G_AOWBASE,
        "test esi, esi",
        "jz Ltail",
        "cmp esi, -1",
        "je Ltail",
        "cmp dword ptr [esi+%#x], %#x" % (HDR_RVA, MAGIC),
        "jne Ltail",
        "mov edi, [esi+%#x]" % (HDR_RVA + 8),
        "add edi, esi",
        "mov ecx, [esi+%#x]" % (HDR_RVA + 0xC),
        "test ecx, ecx",
        "jz Lunarmed",
        "xor eax, eax",
        "Lor:",
        "or eax, [edi+ecx*4-4]",
        "dec ecx",
        "jnz Lor",
        "test eax, eax",
        "jz Lunarmed",
        # ---- G2: the foreground window must be ours ...
        "call dword ptr [ebx+%#x]" % IAT["GetForegroundWindow"],
        "test eax, eax",
        "jz Lgfg",
        "lea ecx, [ebp-4]",
        "push ecx",
        "push eax",
        "call dword ptr [ebx+%#x]" % IAT["GetWindowThreadProcessId"],
        "mov eax, [ebp-4]",
        "cmp eax, [ebx+%#x]" % G_PID,
        "jne Lgfg",
        # ---- ... and so must the window under the cursor (logical coordinates)
        "lea eax, [ebp-0xC]",
        "push eax",
        "call dword ptr [ebx+%#x]" % IAT["GetCursorPos"],
        "push dword ptr [ebp-8]",                                    # pt.y
        "push dword ptr [ebp-0xC]",                                  # pt.x  (POINT by value)
        "call dword ptr [ebx+%#x]" % IAT["WindowFromPoint"],
        "test eax, eax",
        "jz Lguc",
        "lea ecx, [ebp-4]",
        "push ecx",
        "push eax",
        "call dword ptr [ebx+%#x]" % IAT["GetWindowThreadProcessId"],
        "mov eax, [ebp-4]",
        "cmp eax, [ebx+%#x]" % G_PID,
        "jne Lguc",
        # ---- armed: queue the raw delta, wake the game thread, swallow
        "mov eax, [ebp+0x10]",                                       # MSLLHOOKSTRUCT*
        "mov eax, [eax+8]",                                          # mouseData
        "sar eax, 16",                                               # signed wheel delta
        "lock add dword ptr [ebx+%#x], eax" % G_PENDING,
        cnt(11),
        "mov eax, [ebx+%#x]" % G_HWND,
        "test eax, eax",
        "jz Lswallow",
        "push 0", "push 0", "push 0",                                # lParam, wParam, WM_NULL
        "push eax",
        "call dword ptr [ebx+%#x]" % IAT["PostMessageA"],
        "Lswallow:",
        "mov eax, 1",
        "jmp Lexit",
        "Lunarmed:",
        cnt(8), diag("jmp Ltail"),
        "Lgfg:",
        cnt(9), diag("jmp Ltail"),
        "Lguc:",
        cnt(10),
        "Ltail:",
        "push dword ptr [ebp+0x10]",
        "push dword ptr [ebp+0xC]",
        "push dword ptr [ebp+8]",
        "push dword ptr [ebx+%#x]" % G_HHOOK,
        "call dword ptr [ebx+%#x]" % IAT["CallNextHookEx"],
        "Lexit:",
        "pop edi", "pop esi", "pop ebx",
        "mov esp, ebp", "pop ebp",
        "ret 0xC",
    ])


def src_thread():
    return "\n".join([
        "push ebp", "mov ebp, esp",
        "sub esp, 0x20",                                             # MSG
        "push ebx",
        "call Lp", "Lp:", "pop ebx", "sub ebx, Lp",
        "push 0",                                                    # dwThreadId = 0 (global)
        "lea eax, [ebx+%#x]" % IMAGE_BASE,                           # hMod = this module, rebased
        "push eax",
        "lea eax, [ebx+%#x]" % LL_VA,                                # lpfn
        "push eax",
        "push %d" % WH_MOUSE_LL,
        "call dword ptr [ebx+%#x]" % IAT["SetWindowsHookExA"],
        "mov [ebx+%#x], eax" % G_HHOOK,
        diag("mov [ebx+%#x], eax" % (CNT + 4 * 12)),
        "Lpump:",
        "call dword ptr [ebx+%#x]" % IAT["WaitMessage"],
        "Ldrain:",
        "push 1",                                                    # PM_REMOVE
        "push 0", "push 0", "push 0",
        "lea eax, [ebp-0x20]",
        "push eax",
        "call dword ptr [ebx+%#x]" % IAT["PeekMessageA"],
        "test eax, eax",
        "jnz Ldrain",
        "jmp Lpump",                                                 # never returns
    ])


def build_caves():
    pump = asm(src_pump(), PUMP_VA)
    data = b"\0aowInt.dpl\0"
    assert pump.endswith(PUMP_TAIL + data), "pump must end with the shifted cmp, ret, NUL, leaf name"
    pump_code = len(pump) - len(data)
    assert pump.count(b"aowInt.dpl") == 1
    caves = {
        "PUMP": (PUMP_VA, PUMP_BUDGET, pump, pump_code),
        "LL": (LL_VA, LL_BUDGET, asm(src_ll(), LL_VA), None),
        "TH": (TH_VA, TH_BUDGET, asm(src_thread(), TH_VA), None),
    }
    ll = caves["LL"][2]
    assert ll.endswith(b"\xC2\x0C\x00"), "LL proc must end with ret 0xC"
    return caves


def hook_bytes():
    return b"\xE8" + struct.pack("<i", PUMP_VA - (H5_SITE + 5))


def site_state(mod):
    cur = mod.read(H5_SITE, 5)
    if cur == H5_ORIG:
        return "vanilla", cur
    if cur == hook_bytes():
        return "applied", cur
    return "foreign", cur


def zone_desc(mod, va, budget, blobs):
    z = mod.read(va, budget)
    if set(z) <= {0}:
        return "zero"
    for variant, blob in blobs.items():
        if z == pad(blob, budget, variant):
            return "ours (%s)" % variant
    return "nonzero"


def aowint_half_present():
    try:
        a = Module(INT, AOW_IMAGE_BASE)
    except Exception as e:
        return None, "aowInt.dpl unreadable: %s" % e
    hdr = a.read(AOW_IMAGE_BASE + HDR_RVA, 8)
    magic, ver = struct.unpack("<II", hdr)
    h1 = a.read(AOW_H1_SITE, 6)
    if h1 == AOW_H1_ORIG and magic == 0:
        return False, "vanilla"
    if h1 == b"\xE9" + struct.pack("<i", AOW_CLR_VA - (AOW_H1_SITE + 5)) + b"\x90" and magic == MAGIC:
        return (ver >> 16) == MAJOR, "applied (header v%d.%d)" % (ver >> 16, ver & 0xFFFF)
    return None, "foreign (H1 %s, magic %08X)" % (h1.hex(" "), magic)


def main(argv):
    apply_, undo, show = "--apply" in argv, "--undo" in argv, ("--dis" in argv or "--show" in argv)
    for a in argv:
        if a not in ("--apply", "--undo", "--dis", "--show", "--diag"):
            sys.exit("unknown flag %s" % a)

    global DIAG
    want_diag = DIAG
    variants = {}
    for DIAG in (False, True):
        variants["diag" if DIAG else "plain"] = build_caves()
    DIAG = want_diag
    variant = "diag" if DIAG else "plain"
    caves = variants[variant]

    problems = []
    for name, (va, budget, blob, code_len) in caves.items():
        pad(blob, budget, name)
        problems += pic_lint(blob, va, name, code_len)
        problems += check_push_imm8(blob, va, name, code_len)
        if re.search(rb"[A-Za-z]:\\", blob):
            problems.append("%s contains a drive-letter path" % name)
    if problems:
        print("\n".join(problems))
        sys.exit("ABORT: static checks failed")

    if show:
        print("build variant: %s   NOTCH=%d  MAX_NOTCHES=%d" % (variant, NOTCH, MAX_NOTCHES))
        print("  H5 %08X: %s -> %s" % (H5_SITE, H5_ORIG.hex(" "), hook_bytes().hex(" ")))
        for name, (va, budget, blob, code_len) in caves.items():
            print("\n".join(dis_lines(blob, va, name, code_len)))
        return 0

    mod = Module(VCL, IMAGE_BASE)
    hits = mod.reloc_hits([(H5_SITE, H5_SITE + 5), (OWN_CODE_LO, OWN_CODE_HI), (OWN_DATA_LO, OWN_DATA_HI)])
    if hits:
        sys.exit("ABORT: .reloc entries inside our ranges at file offsets %s" % [hex(h) for h in hits])
    mod.off(OWN_DATA_LO, OWN_DATA_HI - OWN_DATA_LO, write=True)
    for nm, slot in IAT.items():
        mod.off(slot, 4)

    print("build_wheel_vclpump  (%s build)" % variant)
    print("  file: %s" % VCL)
    st, cur = site_state(mod)
    print("  %-42s %08X  %-8s %s" % ("H5 PUMP TApplication.ProcessMessage+25", H5_SITE, st, cur.hex(" ")))
    if st == "foreign":
        sys.exit("ABORT: the hook site is neither vanilla nor ours -- someone else owns it.")
    for name, (va, budget, blob, code_len) in caves.items():
        zd = zone_desc(mod, va, budget, {k: v[name][2] for k, v in variants.items()})
        print("  %-42s %08X  %s  (%d B of %#x)" % ("cave " + name, va, zd, len(blob), budget))
    data_zero = set(mod.read(OWN_DATA_LO, OWN_DATA_HI - OWN_DATA_LO)) <= {0}
    print("  %-42s %08X  %s" % ("globals + counters (.idata slack)", OWN_DATA_LO,
                                "zero" if data_zero else "NONZERO"))

    aow_ok, aow_desc = aowint_half_present()
    vcl_half = st == "applied"
    if vcl_half and aow_ok:
        chain = "complete"
    elif vcl_half and aow_ok is False:
        chain = "vcl30 half only, inert"
    elif (not vcl_half) and aow_ok:
        chain = "aowInt half only, inert"
    elif aow_ok is None:
        chain = "aowInt %s -- ABORT" % aow_desc
    else:
        chain = "absent"
    print("  chain: %s   (aowInt header %08X: %s)" % (chain, AOW_IMAGE_BASE + HDR_RVA, aow_desc))
    if aow_ok is None:
        return 2

    if undo:
        if st == "vanilla":
            print("\nnothing to undo: H5 vanilla")
            return 0
        assert mod.read(H5_SITE, 5) == hook_bytes()
        mod.write(H5_SITE, H5_ORIG)
        mod.write(OWN_CODE_LO, bytes(OWN_CODE_HI - OWN_CODE_LO))
        mod.write(OWN_DATA_LO, bytes(OWN_DATA_HI - OWN_DATA_LO))
        try:
            open(VCL, "wb").write(bytes(mod.d))
        except PermissionError:
            sys.exit("ABORT: " + KILL_HINT)
        chk = Module(VCL, IMAGE_BASE)
        assert chk.read(H5_SITE, 5) == H5_ORIG
        assert set(chk.read(OWN_CODE_LO, OWN_CODE_HI - OWN_CODE_LO)) <= {0}
        print("\nundone: H5 restored, %08X..%08X and %08X..%08X zeroed; no backup touched."
              % (OWN_CODE_LO, OWN_CODE_HI, OWN_DATA_LO, OWN_DATA_HI))
        return 0

    plan = []
    fresh = st == "vanilla"
    if fresh:
        if set(mod.read(OWN_CODE_LO, OWN_CODE_HI - OWN_CODE_LO)) > {0}:
            sys.exit("ABORT: cave zone %08X..%08X is not zero -- someone else owns it." % (OWN_CODE_LO,
                                                                                            OWN_CODE_HI))
        if not data_zero:
            sys.exit("ABORT: global zone is not zero -- someone else owns it.")
        for name, (va, budget, blob, code_len) in caves.items():
            plan.append((va, pad(blob, budget, name), "cave %s (%d B + zero pad)" % (name, len(blob))))
        plan.append((H5_SITE, hook_bytes(), "H5 call -> PUMP"))
    else:
        for name, (va, budget, blob, code_len) in caves.items():
            if mod.read(va, budget) != pad(blob, budget, name):
                plan.append((va, pad(blob, budget, name), "cave %s (rewrite in place)" % name))

    if not plan:
        print("\nalready applied (%s build) -- nothing to write." % variant)
        return 0
    print("\n%s -- %d region(s):" % ("fresh apply" if fresh else "rewrite in place", len(plan)))
    for va, new, desc in plan:
        print("   %08X  %4d B  %s" % (va, len(new), desc))
    if not apply_:
        print("\nDRY RUN -- pass --apply to write.  (--dis shows the caves)")
        return 0

    if fresh and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(VCL, BACKUP)
        print("backup written: %s" % os.path.basename(BACKUP))
    elif fresh:
        print("backup already exists, left as-is: %s" % os.path.basename(BACKUP))
    else:
        print("re-tune over an existing install: no backup taken (the current file is our own output)")

    for va, new, desc in plan:
        cur = mod.read(va, len(new))
        if fresh:
            if va == H5_SITE:
                assert cur == H5_ORIG, "verify-before-write: H5 changed"
            else:
                assert set(cur) <= {0}, "verify-before-write: zone at %08X changed" % va
        mod.write(va, new)
    try:
        open(VCL, "wb").write(bytes(mod.d))
    except PermissionError:
        sys.exit("ABORT: " + KILL_HINT)
    chk = Module(VCL, IMAGE_BASE)
    for va, new, desc in plan:
        assert chk.read(va, len(new)) == new, "read-back mismatch at %08X" % va
    print("written and read back: %d region(s)." % len(plan))
    print("\napplied, UNTESTED -- needs the user's in-game test (spec IN-GAME section).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
