#!/usr/bin/env python3
r"""
veh_capture.py -- capture the registers, stack and fault site of a CRASHED AoW1, without a debugger.

WHEN TO REACH FOR THIS
----------------------
The game *exits* or throws a runtime error and you need to know where. Especially when the crash
REFUSES TO REPRODUCE under a debugger: AoW1 is Delphi 3 and uses its own memory manager, so
attaching a debugger perturbs the heap layout enough that an out-of-bounds read lands on benign
memory and the fault simply stops happening. `_NO_DEBUG_HEAP` does not help -- that switch governs
the *Windows* heap, not Delphi's.

    crashed / vanished / "Runtime error 216"  ->  veh_capture.py   (this tool)
    frozen, still alive, no input             ->  hang_stack.py    (sibling tool)

HOW IT DODGES THE HEISENBUG
---------------------------
No debugger is ever attached. The tool launches the target SUSPENDED, `VirtualAllocEx`s an RWX
region, writes x86 shellcode for a **vectored exception handler** plus a small install stub,
`CreateRemoteThread`s the stub (which calls `RtlAddVectoredExceptionHandler`), then `ResumeThread`s.
The handler therefore runs IN-PROCESS: no debug port, no debug heap, the real Delphi allocator, the
real crash. On a matching fault it copies the `CONTEXT` and `EXCEPTION_RECORD` into its region and
then **spins (`pause; jmp $`) so the faulting thread never unwinds**. The process is left frozen but
completely intact, so this side can read registers, stack and any memory at leisure.

Ported from Inioch's `diag_inject_veh.py` (share6) -- the mechanism is his. Changed here: no
hard-coded install path, selectable target, a data-driven filter instead of one baked-in fault
address, runtime module resolution, an exception census, and an end-to-end self-test.

USAGE
-----
    python veh_capture.py --self-test          # prove the whole chain works, no game involved
    python veh_capture.py                      # launch AoWz.exe, wait for the first access violation
    python veh_capture.py --exe AoWzEd.exe     # the editor instead
    python veh_capture.py --attach 1234        # inject into an ALREADY-RUNNING process (never kills it)
    python veh_capture.py --census             # arm nothing; just list the exceptions the game raises
    python veh_capture.py --at AoWEPACK.dpl+0x7B24E      # freeze only on a fault at that instruction
    python veh_capture.py --fault-range 0-0x100000       # only near-null dereferences
    python veh_capture.py --code 0xC000001D              # illegal instruction instead of an AV
    python veh_capture.py --skip 3             # ignore the first 3 matches (Delphi handles AVs itself)
    python veh_capture.py --dis                # disassemble the shellcode and exit -- nothing launched

⚠ Delphi raises exceptions constantly as *control flow* (code 0x0EEDFADE), and it also raises and
handles genuine access violations inside `try..except`. So the first AV is not always the fatal one.
If the capture lands somewhere innocent, re-run with `--skip N`, or run `--census` first to see what
actually flies past before choosing a filter.

⚠ The census is polled out of the target every 20 ms, so when the target dies of an exception the
handler did NOT freeze on, the last entry or two can be lost with its address space -- the report
is only as fresh as the final successful read. A census is reconnaissance; to be certain of keeping
a particular exception, arm a filter that matches it so the thread freezes instead of dying.

READING THE OUTPUT
------------------
Every address is resolved against the module bases the target ACTUALLY loaded at, which matters
because the `.dpl` packages rebase. For a package the report also prints the link-time VA
(preferred ImageBase + RVA) and the file offset resolved through that module's PE section table --
those are the two forms the build scripts, the docs and Ghidra all speak, e.g.

    AoWEPACK.dpl+0x7B24E   link VA 0x5577BE4E   file 0x0007B24E   (CODE)

⚠ The VA<->file-offset delta is PER SECTION (CODE is `file + 0x55700C00`, DATA is `file +
0x55701200`); this tool reads the section table rather than applying a flat delta.

SAFETY / SIDE EFFECTS
---------------------
* Nothing is written to any game file. This tool never patches a binary.
* `--attach` never terminates the process it attached to. On timeout or Ctrl-C the handler is
  DISARMED (it stays resident as a harmless counter until the process exits) so the game cannot be
  frozen later with nobody watching.
* A captured process is left frozen only long enough to dump it; the PID and the kill command are
  always printed.
* The RWX region is placed away from every game module's preferred ImageBase, so injecting it does
  not push `AoWEPACK.dpl` off 0x55700000. The report prints each module's real base and flags any
  that were relocated anyway.
"""
import argparse
import ctypes as C
import ctypes.wintypes as W
import os
import struct
import sys
import tempfile
import time

# This file's help text and report use non-ASCII (arrows, warning signs). On a machine
# whose console is cp1252 -- the default here -- argparse's --help died with
# UnicodeEncodeError before printing anything. Force UTF-8 and never let an encoding
# fault take down a diagnostic tool.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
from zignames import zigexe

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(TOOLS, "..", ".."))
ROOT = os.path.dirname(GAME)          # the vanilla install -- and where the RUNNABLE mod pair sits
OUT = os.path.join(TOOLS, "veh_capture.txt")

#: Which tree holds the RUNNABLE copy of a given name. This tool LAUNCHES its target, so the
#: distinction matters: AoWz.exe / AoWzCompat.exe exist in BOTH trees, and the pair in Ziggurat\
#: is LIVE and runs from Ziggurat/ (build_overlay.py's root-exe indirection was retired 2026-09-09)
#: at the ROOT, with their imports rewritten to Ziggurat\<pkg>.dpl. The editors are the other way
#: round: they run from Ziggurat\.
_RUNS_FROM_ROOT = {zigexe.GAME_EXE, zigexe.COMPAT_EXE, zigexe.VANILLA_EXE, zigexe.VANILLA_COMPAT}


def resolve_target(name):
    """--exe takes a NAME (or an absolute path); find the copy that is meant to be launched."""
    if os.path.isabs(name):
        return name
    first = ROOT if name in _RUNS_FROM_ROOT else GAME
    for d in (first, GAME if first is ROOT else ROOT):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return os.path.join(first, name)          # let the caller report the miss against one path

# ---------------------------------------------------------------------------------------------
# Win32
# ---------------------------------------------------------------------------------------------
k32 = C.WinDLL("kernel32", use_last_error=True)
VP = C.c_void_p

for _fn, _res, _args in (
    ("CreateProcessW", W.BOOL, None),
    ("OpenProcess", VP, [W.DWORD, W.BOOL, W.DWORD]),
    ("VirtualAllocEx", VP, [VP, VP, C.c_size_t, W.DWORD, W.DWORD]),
    ("VirtualFreeEx", W.BOOL, [VP, VP, C.c_size_t, W.DWORD]),
    ("VirtualQueryEx", C.c_size_t, None),
    ("CreateRemoteThread", VP, [VP, VP, C.c_size_t, VP, VP, W.DWORD, VP]),
    ("WriteProcessMemory", W.BOOL, [VP, VP, C.c_char_p, C.c_size_t, C.POINTER(C.c_size_t)]),
    ("ReadProcessMemory", W.BOOL, [VP, VP, VP, C.c_size_t, C.POINTER(C.c_size_t)]),
    ("WaitForSingleObject", W.DWORD, [VP, W.DWORD]),
    ("ResumeThread", W.DWORD, [VP]),
    ("TerminateProcess", W.BOOL, [VP, W.UINT]),
    ("GetExitCodeProcess", W.BOOL, [VP, C.POINTER(W.DWORD)]),
    ("GetExitCodeThread", W.BOOL, [VP, C.POINTER(W.DWORD)]),
    ("CloseHandle", W.BOOL, [VP]),
    ("CreateToolhelp32Snapshot", VP, [W.DWORD, W.DWORD]),
    ("OpenThread", VP, [W.DWORD, W.BOOL, W.DWORD]),
    ("Wow64GetThreadContext", W.BOOL, None),
    ("SetErrorMode", W.UINT, [W.UINT]),
):
    _f = getattr(k32, _fn)
    _f.restype = _res
    if _args:
        _f.argtypes = _args

CREATE_SUSPENDED = 0x00000004
MEM_COMMIT_RESERVE = 0x3000
MEM_RELEASE = 0x8000
PAGE_EXECUTE_READWRITE = 0x40
MEM_COMMIT = 0x1000
MEM_IMAGE = 0x1000000
STILL_ACTIVE = 259
INFINITE = 0xFFFFFFFF
TH32CS_SNAPTHREAD = 0x00000004
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
THREAD_GET_CONTEXT = 0x0008
WOW64_CONTEXT_CONTROL_INTEGER = 0x00010003
PROC_ACCESS = 0x0043A  # VM_OP|VM_READ|VM_WRITE|CREATE_THREAD|QUERY_INFORMATION|TERMINATE
INVALID_HANDLE = C.c_void_p(-1).value


class STARTUPINFOW(C.Structure):
    _fields_ = [("cb", W.DWORD), ("lpReserved", W.LPWSTR), ("lpDesktop", W.LPWSTR),
                ("lpTitle", W.LPWSTR), ("dwX", W.DWORD), ("dwY", W.DWORD),
                ("dwXSize", W.DWORD), ("dwYSize", W.DWORD), ("dwXCountChars", W.DWORD),
                ("dwYCountChars", W.DWORD), ("dwFillAttribute", W.DWORD), ("dwFlags", W.DWORD),
                ("wShowWindow", W.WORD), ("cbReserved2", W.WORD),
                ("lpReserved2", C.POINTER(C.c_byte)), ("hStdInput", W.HANDLE),
                ("hStdOutput", W.HANDLE), ("hStdError", W.HANDLE)]


class PROCESS_INFORMATION(C.Structure):
    _fields_ = [("hProcess", W.HANDLE), ("hThread", W.HANDLE),
                ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD)]


class MBI(C.Structure):
    """MEMORY_BASIC_INFORMATION in the *host* Python's bitness -- c_void_p/c_size_t make ctypes
    lay out the 64-bit form under 64-bit Python (with the alignment hole before RegionSize) and the
    32-bit form otherwise, which is exactly what VirtualQueryEx expects from each."""
    _fields_ = [("BaseAddress", VP), ("AllocationBase", VP), ("AllocationProtect", W.DWORD),
                ("RegionSize", C.c_size_t), ("State", W.DWORD), ("Protect", W.DWORD),
                ("Type", W.DWORD)]


class MODULEENTRY32(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("th32ModuleID", W.DWORD), ("th32ProcessID", W.DWORD),
                ("GlblcntUsage", W.DWORD), ("ProccntUsage", W.DWORD),
                ("modBaseAddr", C.POINTER(C.c_byte)), ("modBaseSize", W.DWORD),
                ("hModule", W.HMODULE), ("szModule", C.c_char * 256),
                ("szExePath", C.c_char * 260)]


class THREADENTRY32(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ThreadID", W.DWORD),
                ("th32OwnerProcessID", W.DWORD), ("tpBasePri", W.LONG),
                ("tpDeltaPri", W.LONG), ("dwFlags", W.DWORD)]


class WOW64_FLOATING_SAVE_AREA(C.Structure):
    _fields_ = [("ControlWord", W.DWORD), ("StatusWord", W.DWORD), ("TagWord", W.DWORD),
                ("ErrorOffset", W.DWORD), ("ErrorSelector", W.DWORD), ("DataOffset", W.DWORD),
                ("DataSelector", W.DWORD), ("RegisterArea", C.c_byte * 80),
                ("Cr0NpxState", W.DWORD)]


class WOW64_CONTEXT(C.Structure):
    _fields_ = [("ContextFlags", W.DWORD), ("Dr0", W.DWORD), ("Dr1", W.DWORD), ("Dr2", W.DWORD),
                ("Dr3", W.DWORD), ("Dr6", W.DWORD), ("Dr7", W.DWORD),
                ("FloatSave", WOW64_FLOATING_SAVE_AREA),
                ("SegGs", W.DWORD), ("SegFs", W.DWORD), ("SegEs", W.DWORD), ("SegDs", W.DWORD),
                ("Edi", W.DWORD), ("Esi", W.DWORD), ("Ebx", W.DWORD), ("Edx", W.DWORD),
                ("Ecx", W.DWORD), ("Eax", W.DWORD), ("Ebp", W.DWORD), ("Eip", W.DWORD),
                ("SegCs", W.DWORD), ("EFlags", W.DWORD), ("Esp", W.DWORD), ("SegSs", W.DWORD),
                ("ExtendedRegisters", C.c_byte * 512)]


# ---------------------------------------------------------------------------------------------
# Injected region layout.  All offsets are from the base VirtualAllocEx handed us.
# ---------------------------------------------------------------------------------------------
OFF_HANDLER = 0x0000        # the vectored exception handler
OFF_STUB = 0x0200           # the CreateRemoteThread entry that installs it
OFF_CTL = 0x0300            # control block, below
OFF_CTX = 0x0400            # CONTEXT copy (0x2CC bytes)
OFF_ER = 0x0700             # EXCEPTION_RECORD copy (0x50 bytes)
OFF_RING = 0x1000           # census ring: 64 entries x (code, address, info)
REGION_SIZE = 0x4000

# control block, offsets from OFF_CTL
CTL_ARMED = 0x00      # 0 = record only, never freeze
CTL_CODE = 0x04       # exception code to match, 0 = any
CTL_EIP_LO = 0x08     # fault-instruction range, inactive while EIP_HI == 0
CTL_EIP_HI = 0x0C
CTL_FLT_LO = 0x10     # faulting-data-address range, inactive while FLT_HI == 0
CTL_FLT_HI = 0x14
CTL_SKIP = 0x18       # matches still to be ignored before freezing
CTL_CLAIM = 0x1C      # atomically claimed by the first thread that freezes
CTL_DONE = 0x20       # set once CONTEXT+EXCEPTION_RECORD are fully copied
CTL_VEHRES = 0x24     # return value of RtlAddVectoredExceptionHandler
CTL_SEEN = 0x28       # every exception the handler was offered
CTL_PASSED = 0x2C     # ...of which this many were passed on
CTL_RINGIDX = 0x30    # monotonic census counter
CTL_NAMES = [(CTL_ARMED, "ARMED"), (CTL_CODE, "CODE"), (CTL_EIP_LO, "EIP_LO"),
             (CTL_EIP_HI, "EIP_HI"), (CTL_FLT_LO, "FLT_LO"), (CTL_FLT_HI, "FLT_HI"),
             (CTL_SKIP, "SKIP"), (CTL_CLAIM, "CLAIM"), (CTL_DONE, "DONE"),
             (CTL_VEHRES, "VEHRES"), (CTL_SEEN, "SEEN"), (CTL_PASSED, "PASSED"),
             (CTL_RINGIDX, "RINGIDX")]
RING_ENTRIES = 64

CONTEXT_SIZE = 0x2CC
ER_SIZE = 0x50
# WOW64_CONTEXT field offsets, used to read the copied buffer
CTX_OFF = {"Edi": 0x9C, "Esi": 0xA0, "Ebx": 0xA4, "Edx": 0xA8, "Ecx": 0xAC, "Eax": 0xB0,
           "Ebp": 0xB4, "Eip": 0xB8, "EFlags": 0xC0, "Esp": 0xC4,
           "SegCs": 0xBC, "SegSs": 0xC8, "SegDs": 0x98, "SegEs": 0x94, "SegFs": 0x90,
           "SegGs": 0x8C}

EXC_NAMES = {
    0xC0000005: "ACCESS_VIOLATION", 0xC0000006: "IN_PAGE_ERROR",
    0xC0000008: "INVALID_HANDLE", 0xC000000D: "INVALID_PARAMETER",
    0xC0000017: "NO_MEMORY", 0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000025: "NONCONTINUABLE_EXCEPTION", 0xC0000026: "INVALID_DISPOSITION",
    0xC000008C: "ARRAY_BOUNDS_EXCEEDED", 0xC000008E: "FLT_DIVIDE_BY_ZERO",
    0xC0000090: "FLT_INVALID_OPERATION", 0xC0000091: "FLT_OVERFLOW",
    0xC0000093: "FLT_UNDERFLOW", 0xC0000094: "INT_DIVIDE_BY_ZERO",
    0xC0000095: "INT_OVERFLOW", 0xC0000096: "PRIV_INSTRUCTION",
    0xC00000FD: "STACK_OVERFLOW", 0xC0000409: "STACK_BUFFER_OVERRUN",
    0x80000003: "BREAKPOINT", 0x80000004: "SINGLE_STEP",
    0x40010006: "OUTPUT_DEBUG_STRING", 0x406D1388: "SET_THREAD_NAME",
    0x0EEDFADE: "Delphi language exception (raise / try..except)",
    0xE06D7363: "C++ EH",
}
AV_KIND = {0: "read", 1: "write", 8: "execute (DEP)"}


def exc_name(code):
    return EXC_NAMES.get(code & 0xFFFFFFFF, "unknown")


# ---------------------------------------------------------------------------------------------
# A very small hand assembler.  Every instruction is emitted as literal bytes with the mnemonic
# alongside, and `--dis` runs capstone over the result -- the project rule is that no assembled
# blob is trusted without being read back.
# ---------------------------------------------------------------------------------------------
class Asm:
    def __init__(self):
        self.buf = bytearray()
        self.labels = {}
        self.fixups = []          # (patch_offset, label, kind) kind in {"rel32"}

    def raw(self, data):
        self.buf += bytes(data)
        return self

    def label(self, name):
        self.labels[name] = len(self.buf)
        return self

    def jcc(self, cc, name):
        """Near Jcc, rel32 -- no range worries and no second pass over instruction sizes."""
        self.buf += bytes((0x0F, 0x80 | cc))
        self.fixups.append((len(self.buf), name))
        self.buf += b"\x00\x00\x00\x00"
        return self

    def jmp(self, name):
        """Near jmp, rel32."""
        self.buf += b"\xE9"
        self.fixups.append((len(self.buf), name))
        self.buf += b"\x00\x00\x00\x00"
        return self

    def jmp_back(self, name):
        """Short backwards jmp to an already-defined label."""
        target = self.labels[name]
        self.buf += b"\xEB"
        rel = target - (len(self.buf) + 1)
        assert -128 <= rel <= 127, "backwards jump out of rel8 range"
        self.buf += struct.pack("<b", rel)
        return self

    def done(self):
        for at, name in self.fixups:
            rel = self.labels[name] - (at + 4)
            struct.pack_into("<i", self.buf, at, rel)
        return bytes(self.buf)


CC_B, CC_AE, CC_E, CC_NE = 0x02, 0x03, 0x04, 0x05


def u32(v):
    return struct.pack("<I", v & 0xFFFFFFFF)


def build_handler(region):
    """The vectored exception handler.  Reads its filter from the control block rather than having
    it baked in, so a module-relative filter can be armed later -- when the target is created
    suspended the only module mapped is ntdll, so `AoWEPACK.dpl+0x...` cannot be resolved yet."""
    ctl = region + OFF_CTL
    ring = region + OFF_RING
    a = Asm()
    a.raw(b"\x8B\x44\x24\x04")                       # mov eax,[esp+4]        ExceptionPointers
    a.raw(b"\x8B\x08")                               # mov ecx,[eax]          ExceptionRecord
    a.raw(b"\xF0\xFF\x05" + u32(ctl + CTL_SEEN))     # lock inc dword [SEEN]

    # --- census: record (code, ExceptionAddress, ExceptionInformation[1]) in the ring ---------
    a.raw(b"\xA1" + u32(ctl + CTL_RINGIDX))          # mov eax,[RINGIDX]
    a.raw(b"\x83\xE0" + bytes((RING_ENTRIES - 1,)))  # and eax,63
    a.raw(b"\x8D\x04\x40")                           # lea eax,[eax+eax*2]    (x3)
    a.raw(b"\xC1\xE0\x02")                           # shl eax,2              (x12 = entry size)
    a.raw(b"\x8B\x11")                               # mov edx,[ecx]          code
    a.raw(b"\x89\x90" + u32(ring + 0))               # mov [eax+RING+0],edx
    a.raw(b"\x8B\x51\x0C")                           # mov edx,[ecx+0Ch]      ExceptionAddress
    a.raw(b"\x89\x90" + u32(ring + 4))               # mov [eax+RING+4],edx
    a.raw(b"\x8B\x51\x18")                           # mov edx,[ecx+18h]      ExcInfo[1]
    a.raw(b"\x89\x90" + u32(ring + 8))               # mov [eax+RING+8],edx
    a.raw(b"\xF0\xFF\x05" + u32(ctl + CTL_RINGIDX))  # lock inc dword [RINGIDX]

    # --- filters -----------------------------------------------------------------------------
    a.raw(b"\x83\x3D" + u32(ctl + CTL_ARMED) + b"\x00")   # cmp dword [ARMED],0
    a.jcc(CC_E, "pass")                                   # je pass

    a.raw(b"\x8B\x15" + u32(ctl + CTL_CODE))         # mov edx,[CODE]
    a.raw(b"\x85\xD2")                               # test edx,edx
    a.jcc(CC_E, "code_ok")                           # je code_ok   (0 = any code)
    a.raw(b"\x39\x11")                               # cmp [ecx],edx
    a.jcc(CC_NE, "pass")
    a.label("code_ok")

    a.raw(b"\x8B\x15" + u32(ctl + CTL_EIP_HI))       # mov edx,[EIP_HI]
    a.raw(b"\x85\xD2")                               # test edx,edx
    a.jcc(CC_E, "eip_ok")                            # je eip_ok    (0 = filter off)
    a.raw(b"\x8B\x41\x0C")                           # mov eax,[ecx+0Ch]    ExceptionAddress
    a.raw(b"\x3B\x05" + u32(ctl + CTL_EIP_LO))       # cmp eax,[EIP_LO]
    a.jcc(CC_B, "pass")
    a.raw(b"\x3B\xC2")                               # cmp eax,edx
    a.jcc(CC_AE, "pass")
    a.label("eip_ok")

    a.raw(b"\x8B\x15" + u32(ctl + CTL_FLT_HI))       # mov edx,[FLT_HI]
    a.raw(b"\x85\xD2")                               # test edx,edx
    a.jcc(CC_E, "flt_ok")                            # je flt_ok    (0 = filter off)
    a.raw(b"\x8B\x41\x18")                           # mov eax,[ecx+18h]    faulting address
    a.raw(b"\x3B\x05" + u32(ctl + CTL_FLT_LO))       # cmp eax,[FLT_LO]
    a.jcc(CC_B, "pass")
    a.raw(b"\x3B\xC2")                               # cmp eax,edx
    a.jcc(CC_AE, "pass")
    a.label("flt_ok")

    # --- --skip N: let the first N matches through -------------------------------------------
    a.raw(b"\x83\x3D" + u32(ctl + CTL_SKIP) + b"\x00")    # cmp dword [SKIP],0
    a.jcc(CC_E, "take")                                   # je take
    a.raw(b"\xF0\xFF\x0D" + u32(ctl + CTL_SKIP))          # lock dec dword [SKIP]
    a.jmp("pass")                                         # jmp pass
    a.label("take")

    # --- claim the single capture slot atomically --------------------------------------------
    a.raw(b"\x33\xC0")                               # xor eax,eax
    a.raw(b"\xBA" + u32(1))                          # mov edx,1
    a.raw(b"\xF0\x0F\xB1\x15" + u32(ctl + CTL_CLAIM))  # lock cmpxchg [CLAIM],edx
    a.jcc(CC_NE, "pass")                             # someone else already froze

    # --- copy CONTEXT then EXCEPTION_RECORD into the region ----------------------------------
    a.raw(b"\x8B\x44\x24\x04")                       # mov eax,[esp+4]
    a.raw(b"\x56")                                   # push esi
    a.raw(b"\x57")                                   # push edi
    a.raw(b"\x8B\x70\x04")                           # mov esi,[eax+4]      ContextRecord
    a.raw(b"\xBF" + u32(region + OFF_CTX))           # mov edi,CTXBUF
    a.raw(b"\xB9" + u32(CONTEXT_SIZE // 4))          # mov ecx,0B3h
    a.raw(b"\xF3\xA5")                               # rep movsd
    a.raw(b"\x8B\x44\x24\x0C")                       # mov eax,[esp+0Ch]    (two pushes deep)
    a.raw(b"\x8B\x30")                               # mov esi,[eax]        ExceptionRecord
    a.raw(b"\xBF" + u32(region + OFF_ER))            # mov edi,ERBUF
    a.raw(b"\xB9" + u32(ER_SIZE // 4))               # mov ecx,14h
    a.raw(b"\xF3\xA5")                               # rep movsd
    a.raw(b"\x5F")                                   # pop edi
    a.raw(b"\x5E")                                   # pop esi
    a.raw(b"\xC7\x05" + u32(ctl + CTL_DONE) + u32(1))  # mov dword [DONE],1

    # --- freeze.  `pause` keeps the core from melting while it spins. ------------------------
    a.label("spin")
    a.raw(b"\xF3\x90")                               # pause
    a.jmp_back("spin")                               # jmp spin

    a.label("pass")
    a.raw(b"\xF0\xFF\x05" + u32(ctl + CTL_PASSED))   # lock inc dword [PASSED]
    a.raw(b"\x33\xC0")                               # xor eax,eax   EXCEPTION_CONTINUE_SEARCH
    a.raw(b"\xC2\x04\x00")                           # ret 4
    blob = a.done()
    spin_va = region + OFF_HANDLER + a.labels["spin"]
    assert len(blob) <= OFF_STUB - OFF_HANDLER, "handler overruns the stub"
    return blob, spin_va


def build_stub(region, add_veh):
    """CreateRemoteThread entry: RtlAddVectoredExceptionHandler(1, handler), store the result."""
    a = Asm()
    a.raw(b"\x68" + u32(region + OFF_HANDLER))       # push handler
    a.raw(b"\x6A\x01")                               # push 1        (first in the chain)
    a.raw(b"\xB8" + u32(add_veh))                    # mov eax,RtlAddVectoredExceptionHandler
    a.raw(b"\xFF\xD0")                               # call eax
    a.raw(b"\xA3" + u32(region + OFF_CTL + CTL_VEHRES))  # mov [VEHRES],eax
    a.raw(b"\x33\xC0")                               # xor eax,eax
    a.raw(b"\xC2\x04\x00")                           # ret 4         (stdcall ThreadProc)
    return a.done()


def disasm(code, base, limit=None):
    try:
        import capstone
    except ImportError:
        return ["    (capstone not installed -- pip install capstone to read this back)"]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    out = []
    for i, ins in enumerate(md.disasm(bytes(code), base)):
        if limit and i >= limit:
            break
        out.append("    %08X  %-20s %s %s"
                   % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))
    return out


# ---------------------------------------------------------------------------------------------
# PE helpers (on-disk), for preferred bases and VA <-> file-offset conversion
# ---------------------------------------------------------------------------------------------
class DiskPE:
    def __init__(self, path):
        with open(path, "rb") as fh:
            d = fh.read(0x1000)
        self.ok = False
        if len(d) < 0x40 or d[:2] != b"MZ":
            return
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        if pe + 0xF8 > len(d) or d[pe:pe + 4] != b"PE\0\0":
            return
        self.machine, nsec = struct.unpack_from("<HH", d, pe + 4)
        opt_size = struct.unpack_from("<H", d, pe + 20)[0]
        opt = pe + 24
        if struct.unpack_from("<H", d, opt)[0] != 0x10B:
            return
        self.image_base = struct.unpack_from("<I", d, opt + 0x1C)[0]
        self.size_of_image = struct.unpack_from("<I", d, opt + 0x38)[0]
        self.sections = []
        sec = opt + opt_size
        for _ in range(nsec):
            if sec + 40 > len(d):
                break
            name = d[sec:sec + 8].rstrip(b"\0").decode("latin-1")
            vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", d, sec + 8)
            self.sections.append((name, vaddr, vsize, raw, rsize))
            sec += 40
        self.ok = True

    def rva_to_off(self, rva):
        """PER SECTION -- never a flat delta.  AoWEPACK.dpl's eight sections have eight different
        VA/file deltas (CODE 0x55700C00, DATA 0x55701200, ...) and mixing them is silently wrong.

        Returns (file_offset_or_None, section_name).  The offset is None for a section with no raw
        data (BSS): it shares a PointerToRawData with the next section, so computing an offset
        there would point confidently into somebody else's bytes."""
        for name, vaddr, vsize, raw, rsize in self.sections:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                if rsize == 0 or (rva - vaddr) >= rsize:
                    return None, name
                return raw + (rva - vaddr), name
        return None, None


_disk_pe_cache = {}


def disk_pe(path):
    key = os.path.normcase(path)
    if key not in _disk_pe_cache:
        try:
            p = DiskPE(path)
        except OSError:
            p = None
        _disk_pe_cache[key] = p if (p and p.ok) else None
    return _disk_pe_cache[key]


def game_preferred_ranges():
    """Every game module's preferred [ImageBase, ImageBase+SizeOfImage).  The injected region is
    placed clear of these so that reserving it cannot bump a package (notably AoWEPACK.dpl at
    0x55700000) off its preferred base and make every address in the capture unfamiliar."""
    out = []
    try:
        names = os.listdir(GAME)
    except OSError:
        names = []
    for n in names:
        if not n.lower().endswith((".dpl", ".exe")):
            continue
        p = disk_pe(os.path.join(GAME, n))
        if p:
            out.append((n, p.image_base, p.image_base + p.size_of_image))
    return out


# ---------------------------------------------------------------------------------------------
# Target process access
# ---------------------------------------------------------------------------------------------
def rpm(hp, addr, size):
    buf = (C.c_ubyte * size)()
    n = C.c_size_t()
    if k32.ReadProcessMemory(hp, C.c_void_p(addr), buf, size, C.byref(n)):
        return bytes(buf[:n.value])
    return b""


def rdw(hp, addr):
    b = rpm(hp, addr, 4)
    return struct.unpack("<I", b)[0] if len(b) == 4 else None


def wpm(hp, addr, data):
    n = C.c_size_t()
    ok = k32.WriteProcessMemory(hp, C.c_void_p(addr), bytes(data), len(data), C.byref(n))
    return bool(ok) and n.value == len(data)


def wdw(hp, addr, value):
    return wpm(hp, addr, u32(value))


def modules(pid):
    """Toolhelp module list.  Empty while the process is CREATE_SUSPENDED -- the loader has not
    built PEB_LDR_DATA yet -- which is why ntdll is found by scanning mapped images instead."""
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    mods = []
    if not snap or snap == INVALID_HANDLE:
        return mods
    me = MODULEENTRY32()
    me.dwSize = C.sizeof(MODULEENTRY32)
    if k32.Module32First(snap, C.byref(me)):
        while True:
            base = C.cast(me.modBaseAddr, C.c_void_p).value or 0
            mods.append((me.szModule.decode(errors="ignore"), base & 0xFFFFFFFF,
                         me.modBaseSize, me.szExePath.decode(errors="ignore")))
            if not k32.Module32Next(snap, C.byref(me)):
                break
    k32.CloseHandle(snap)
    return sorted(mods, key=lambda m: m[1])


def threads_of(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    out = []
    if not snap or snap == INVALID_HANDLE:
        return out
    te = THREADENTRY32()
    te.dwSize = C.sizeof(THREADENTRY32)
    if k32.Thread32First(snap, C.byref(te)):
        while True:
            if te.th32OwnerProcessID == pid:
                out.append(te.th32ThreadID)
            if not k32.Thread32Next(snap, C.byref(te)):
                break
    k32.CloseHandle(snap)
    return out


def thread_eip(tid):
    """32-bit registers of a WOW64 thread.  Wow64GetThreadContext is mandatory here: plain
    GetThreadContext from 64-bit Python returns the WOW64 *frame*, not the guest's i386 state."""
    h = k32.OpenThread(THREAD_GET_CONTEXT, False, tid)
    if not h:
        return None
    try:
        c = WOW64_CONTEXT()
        c.ContextFlags = WOW64_CONTEXT_CONTROL_INTEGER
        if not k32.Wow64GetThreadContext(h, C.byref(c)):
            return None
        return c.Eip
    finally:
        k32.CloseHandle(h)


def mapped_images(hp):
    """Walk the target's address space and return every distinct MEM_IMAGE allocation base below
    4 GB.  Works on a suspended process, where the module list does not yet exist."""
    out, addr, seen = [], 0, set()
    mbi = MBI()
    while addr < 0x7FFF0000:
        if not k32.VirtualQueryEx(hp, C.c_void_p(addr), C.byref(mbi), C.sizeof(mbi)):
            break
        rs = int(mbi.RegionSize or 0)
        if rs <= 0:
            break
        ab = int(mbi.AllocationBase or 0)
        if mbi.Type == MEM_IMAGE and mbi.State == MEM_COMMIT and 0 < ab < 0x80000000 \
                and ab not in seen:
            seen.add(ab)
            out.append(ab)
        addr = int(mbi.BaseAddress or 0) + rs
    return out


def pe_export_name(hp, base):
    """Read a mapped image's export-directory Name, and its machine.  Returns (name, machine)."""
    hdr = rpm(hp, base, 0x400)
    if len(hdr) < 0x40 or hdr[:2] != b"MZ":
        return None, 0
    pe = struct.unpack_from("<I", hdr, 0x3C)[0]
    if pe + 0x80 > len(hdr) or hdr[pe:pe + 4] != b"PE\0\0":
        return None, 0
    machine = struct.unpack_from("<H", hdr, pe + 4)[0]
    if struct.unpack_from("<H", hdr, pe + 24)[0] != 0x10B:
        return None, machine
    exp_rva = struct.unpack_from("<I", hdr, pe + 0x78)[0]
    if not exp_rva:
        return None, machine
    exp = rpm(hp, base + exp_rva, 0x28)
    if len(exp) < 0x28:
        return None, machine
    name_rva = struct.unpack_from("<I", exp, 0x0C)[0]
    nm = rpm(hp, base + name_rva, 64).split(b"\0")[0]
    return nm.decode("latin-1", "replace"), machine


def resolve_export(hp, base, want):
    """Resolve an export by name straight out of the TARGET's mapped image.

    ⚠ WOW64: the address must come from the target's own 32-bit ntdll.  Resolving it in this
    64-bit Python process yields a 64-bit ntdll address, which the injected 32-bit stub would call
    into nothing."""
    hdr = rpm(hp, base, 0x400)
    if len(hdr) < 0x40:
        return 0
    pe = struct.unpack_from("<I", hdr, 0x3C)[0]
    exp_rva = struct.unpack_from("<I", hdr, pe + 0x78)[0]
    size_of_image = struct.unpack_from("<I", hdr, pe + 24 + 0x38)[0]
    exp = rpm(hp, base + exp_rva, 0x28)
    if len(exp) < 0x28:
        return 0
    nfun, nname = struct.unpack_from("<II", exp, 0x14)
    faddr, naddr, oaddr = struct.unpack_from("<III", exp, 0x1C)
    if not nname or nname > 100000:
        return 0
    name_rvas = struct.unpack_from("<%dI" % nname, rpm(hp, base + naddr, 4 * nname), 0)
    ordinals = struct.unpack_from("<%dH" % nname, rpm(hp, base + oaddr, 2 * nname), 0)
    funcs = struct.unpack_from("<%dI" % nfun, rpm(hp, base + faddr, 4 * nfun), 0)
    lo, hi = min(name_rvas), max(name_rvas) + 128
    blob = rpm(hp, base + lo, hi - lo)                 # one read for the whole name pool
    for i, nr in enumerate(name_rvas):
        j = nr - lo
        if j < 0 or j >= len(blob):
            continue
        end = blob.find(b"\0", j)
        if end < 0:
            continue
        if blob[j:end] == want:
            va = base + funcs[ordinals[i]]
            if not (base <= va < base + size_of_image):
                return 0                                # forwarder or nonsense -- refuse it
            return va
    return 0


# ---------------------------------------------------------------------------------------------
# The session
# ---------------------------------------------------------------------------------------------
class Capture:
    def __init__(self, args):
        self.args = args
        self.hp = None
        self.hthread = None
        self.pid = 0
        self.region = 0
        self.spin_va = 0
        self.owns_process = False
        self.launched_path = None
        self.exit_code = 0
        self.avoid = game_preferred_ranges()
        # Last good read of the injected state.  Once the target dies its memory is gone, so the
        # counters and the census have to be cached while it is alive or the post-mortem report
        # is empty exactly when it matters most.
        self._ctl_cache = b"\x00" * 0x100
        self._ring_cache = b"\x00" * (RING_ENTRIES * 12)
        self._mods_cache = []
        self._mods_at = 0.0

    # -- lifecycle ----------------------------------------------------------------------------
    def launch(self, exe_path, workdir):
        si = STARTUPINFOW()
        si.cb = C.sizeof(si)
        pi = PROCESS_INFORMATION()
        ok = k32.CreateProcessW(exe_path, None, None, None, False, CREATE_SUSPENDED,
                                None, workdir, C.byref(si), C.byref(pi))
        if not ok:
            raise RuntimeError("CreateProcessW(%s) failed, error %d"
                               % (os.path.basename(exe_path), C.get_last_error()))
        self.hp = C.c_void_p(pi.hProcess).value
        self.hthread = C.c_void_p(pi.hThread).value
        self.pid = pi.dwProcessId
        self.owns_process = True
        self.launched_path = exe_path
        print("launched %s suspended -- pid %d" % (os.path.basename(exe_path), self.pid))

    def attach(self, pid):
        h = k32.OpenProcess(PROC_ACCESS, False, pid)
        if not h:
            raise RuntimeError("OpenProcess(%d) failed, error %d -- run as the same user"
                               % (pid, C.get_last_error()))
        self.hp = h
        self.pid = pid
        self.owns_process = False
        print("attached to pid %d (this tool will NOT terminate it)" % pid)

    def find_add_veh(self):
        if self.args.ntdll_base:
            base = self.args.ntdll_base
            print("ntdll base forced to 0x%08X" % base)
        else:
            base = 0
            for b in mapped_images(self.hp):
                nm, machine = pe_export_name(self.hp, b)
                if nm and nm.lower() == "ntdll.dll" and machine == 0x14C:
                    base = b
                    break
            if not base:
                raise RuntimeError(
                    "could not find a 32-bit ntdll.dll mapped in pid %d. Is the target 32-bit? "
                    "(every AoW1 binary is i386.)  You can force it with --ntdll-base 0x<addr>."
                    % self.pid)
        addr = resolve_export(self.hp, base, b"RtlAddVectoredExceptionHandler")
        if not addr:
            raise RuntimeError("RtlAddVectoredExceptionHandler not found in ntdll @0x%08X" % base)
        probe = rpm(self.hp, addr, 8)
        if len(probe) != 8 or probe == b"\x00" * 8:
            raise RuntimeError("resolved RtlAddVectoredExceptionHandler @0x%08X is unreadable"
                               % addr)
        print("32-bit ntdll @0x%08X   RtlAddVectoredExceptionHandler @0x%08X (%s)"
              % (base, addr, probe[:4].hex()))
        return addr

    def alloc(self):
        """Reserve the RWX region well clear of every game module's preferred ImageBase."""
        cands = [0x30000000, 0x34000000, 0x38000000, 0x3C000000, 0x20000000, 0x24000000,
                 0x28000000, 0x2C000000, 0x10000000, 0x14000000, 0x64000000, 0x68000000]
        for c in cands:
            if any(lo < c + REGION_SIZE and c < hi for _n, lo, hi in self.avoid):
                continue
            r = k32.VirtualAllocEx(self.hp, C.c_void_p(c), REGION_SIZE,
                                   MEM_COMMIT_RESERVE, PAGE_EXECUTE_READWRITE)
            if r:
                self.region = C.c_void_p(r).value & 0xFFFFFFFF
                return
        r = k32.VirtualAllocEx(self.hp, None, REGION_SIZE, MEM_COMMIT_RESERVE,
                               PAGE_EXECUTE_READWRITE)
        if not r:
            raise RuntimeError("VirtualAllocEx failed, error %d" % C.get_last_error())
        self.region = C.c_void_p(r).value & 0xFFFFFFFF
        clash = [n for n, lo, hi in self.avoid
                 if lo < self.region + REGION_SIZE and self.region < hi]
        if clash:
            print("[!] the region landed on the preferred base of %s -- that module will be "
                  "relocated in this run" % ", ".join(clash))

    def inject(self, add_veh):
        handler, self.spin_va = build_handler(self.region)
        stub = build_stub(self.region, add_veh)
        if not wpm(self.hp, self.region + OFF_HANDLER, handler):
            raise RuntimeError("WriteProcessMemory(handler) failed, error %d" % C.get_last_error())
        if not wpm(self.hp, self.region + OFF_STUB, stub):
            raise RuntimeError("WriteProcessMemory(stub) failed, error %d" % C.get_last_error())
        wpm(self.hp, self.region + OFF_CTL, b"\x00" * 0x100)
        self.write_filter()
        ht = k32.CreateRemoteThread(self.hp, None, 0, C.c_void_p(self.region + OFF_STUB),
                                    None, 0, None)
        if not ht:
            raise RuntimeError("CreateRemoteThread failed, error %d" % C.get_last_error())
        if k32.WaitForSingleObject(ht, 10000) != 0:
            raise RuntimeError("the install stub did not finish within 10 s")
        k32.CloseHandle(ht)
        res = self.ctl(CTL_VEHRES)
        if not res:
            raise RuntimeError("RtlAddVectoredExceptionHandler returned NULL -- not installed")
        print("VEH installed: region 0x%08X, handler 0x%08X, cookie 0x%08X"
              % (self.region, self.region + OFF_HANDLER, res))

    def write_filter(self):
        a = self.args
        wdw(self.hp, self.region + OFF_CTL + CTL_CODE, 0 if a.any_code else a.code)
        wdw(self.hp, self.region + OFF_CTL + CTL_SKIP, a.skip)
        if a.fault_range:
            wdw(self.hp, self.region + OFF_CTL + CTL_FLT_LO, a.fault_range[0])
            wdw(self.hp, self.region + OFF_CTL + CTL_FLT_HI, a.fault_range[1])
        if a.eip_range:
            wdw(self.hp, self.region + OFF_CTL + CTL_EIP_LO, a.eip_range[0])
            wdw(self.hp, self.region + OFF_CTL + CTL_EIP_HI, a.eip_range[1])
        armed = not (a.census or a.at)
        wdw(self.hp, self.region + OFF_CTL + CTL_ARMED, 1 if armed else 0)
        if a.census:
            print("census mode: the handler records exceptions but will never freeze the target")
        elif a.at:
            print("filter waits for %s to load before arming" % a.at[0])

    def try_arm_module_filter(self):
        """`--at MODULE+0x...` cannot be resolved at injection time: while the target is suspended
        only ntdll is mapped.  Poll instead, and arm the moment the module appears.  There is no
        race -- code inside a module cannot fault before that module is loaded."""
        a = self.args
        if not a.at or a.census or self.ctl(CTL_ARMED):
            return
        want, off, span = a.at
        for name, base, size, _path in self.mods():
            if name.lower() == want.lower():
                lo = base + off
                wdw(self.hp, self.region + OFF_CTL + CTL_EIP_LO, lo)
                wdw(self.hp, self.region + OFF_CTL + CTL_EIP_HI, lo + span)
                wdw(self.hp, self.region + OFF_CTL + CTL_ARMED, 1)
                print("filter armed: %s+0x%X = 0x%08X..0x%08X (loaded at 0x%08X)"
                      % (name, off, lo, lo + span, base))
                return

    def snapshot(self):
        """Refresh the cached control block, census ring and module list.  Returns False once the
        target's memory can no longer be read (i.e. it has gone)."""
        blk = rpm(self.hp, self.region + OFF_CTL, 0x100)
        if len(blk) != 0x100:
            return False
        self._ctl_cache = blk
        ring = rpm(self.hp, self.region + OFF_RING, RING_ENTRIES * 12)
        if len(ring) == RING_ENTRIES * 12:
            self._ring_cache = ring
        now = time.time()
        if now - self._mods_at > 1.0:
            self._mods_at = now
            m = modules(self.pid)
            if m:
                self._mods_cache = m
        return True

    def ctl(self, off):
        """Read a control word.  Falls back to the last cached snapshot, so the counters survive
        the target's death and can still be reported."""
        v = rdw(self.hp, self.region + OFF_CTL + off)
        if v is None:
            return struct.unpack_from("<I", self._ctl_cache, off)[0]
        return v

    def mods(self):
        if not self._mods_cache or time.time() - self._mods_at > 1.0:
            m = modules(self.pid)
            if m:
                self._mods_cache = m
                self._mods_at = time.time()
        return self._mods_cache

    def alive(self):
        code = W.DWORD()
        if not k32.GetExitCodeProcess(self.hp, C.byref(code)):
            return None, 0
        return code.value == STILL_ACTIVE, code.value

    def disarm(self):
        wdw(self.hp, self.region + OFF_CTL + CTL_ARMED, 0)

    def resume(self):
        if self.hthread:
            k32.ResumeThread(self.hthread)

    def close(self):
        for h in (self.hthread, self.hp):
            if h:
                k32.CloseHandle(h)
        self.hthread = self.hp = None

    # -- the wait -----------------------------------------------------------------------------
    def wait(self):
        """Poll for DONE.  Returns 'captured' / 'exited' / 'timeout' / 'interrupted'."""
        t0 = time.time()
        deadline = t0 + self.args.timeout if self.args.timeout else None
        last_beat = t0
        try:
            while True:
                readable = self.snapshot()
                if self.ctl(CTL_DONE):
                    return "captured"
                alive, exit_code = self.alive()
                if alive is False or not readable:
                    self.exit_code = exit_code
                    return "exited"
                self.try_arm_module_filter()
                now = time.time()
                if deadline and now > deadline:
                    return "timeout"
                if now - last_beat >= 15:
                    last_beat = now
                    print("  ... waiting (%.0fs, %d exceptions seen, %d passed on)"
                          % (now - t0, self.ctl(CTL_SEEN), self.ctl(CTL_PASSED)), flush=True)
                time.sleep(0.02)
        except KeyboardInterrupt:
            return "interrupted"

    # -- reading the capture ------------------------------------------------------------------
    def read_census(self):
        self.snapshot()
        idx = self.ctl(CTL_RINGIDX)
        raw = self._ring_cache
        out = []
        n = min(idx, RING_ENTRIES)
        for k in range(n):
            slot = (idx - n + k) % RING_ENTRIES
            code, addr, info = struct.unpack_from("<III", raw, slot * 12)
            out.append((code, addr, info))
        return out


# ---------------------------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------------------------
class ModuleMap:
    def __init__(self, mods, target_path=None):
        # Toolhelp with SNAPMODULE|SNAPMODULE32 lists the main image twice for a WOW64 target.
        seen, uniq = set(), []
        for m in mods:
            key = (m[0].lower(), m[1])
            if key not in seen:
                seen.add(key)
                uniq.append(m)
        self.mods = uniq
        self.target = os.path.normcase(target_path) if target_path else None

    def find(self, addr):
        for name, base, size, path in self.mods:
            if base <= addr < base + size:
                return name, base, size, path
        return None

    def interesting(self, path):
        """Only the game's own modules (and the launched target) get link-VA and file-offset
        annotation.  System DLLs are ASLR'd, so their on-disk ImageBase is a fiction: printing
        `ntdll.dll+0x6E12B  link 0x4B2EE12B` would be actively misleading."""
        if not path:
            return False
        p = os.path.normcase(os.path.abspath(path))
        if self.target and p == self.target:
            return True
        return os.path.dirname(p) == os.path.normcase(os.path.abspath(GAME))

    def pe_for(self, name, path):
        if not self.interesting(path):
            return None
        return disk_pe(path) or disk_pe(os.path.join(GAME, name))

    def describe(self, addr, want_file=False):
        hit = self.find(addr)
        if not hit:
            return "0x%08X (not in any module)" % addr
        name, base, size, path = hit
        rva = addr - base
        s = "%s+0x%X" % (name, rva)
        pe = self.pe_for(name, path)
        if pe:
            link = pe.image_base + rva
            if link != addr:
                s += "  link 0x%08X" % link
            if want_file:
                off, sec = pe.rva_to_off(rva)
                if off is not None:
                    s += "  file 0x%08X (%s)" % (off, sec)
        return s

    def summary_lines(self):
        lines = []
        for name, base, size, path in self.mods:
            if not name.lower().endswith((".exe", ".dpl")):
                continue
            pe = self.pe_for(name, path)
            note = ""
            if pe:
                if pe.image_base == base:
                    note = "  (preferred base)"
                else:
                    note = ("  (RELOCATED from 0x%08X -- every link-time address in this module "
                            "is shifted by %+d)" % (pe.image_base, base - pe.image_base))
            lines.append("  %-20s base 0x%08X  size 0x%-8X%s" % (name, base, size, note))
        return lines


def stack_report(hp, mm, regs, depth_bytes):
    """The faulting thread is frozen inside the handler, whose frame lives BELOW the fault ESP, so
    everything from ESP upwards is exactly as the fault left it and can be read as deep as we like."""
    lines = []
    esp = regs["Esp"]
    stack = rpm(hp, esp, depth_bytes)
    lines.append("EBP chain (Delphi omits frames in places -- treat EIP as fact, frames as hints):")
    ebp, seen = regs["Ebp"], set()
    for d in range(32):
        if not ebp or ebp & 3 or ebp in seen:
            break
        seen.add(ebp)
        raw = rpm(hp, ebp, 8)
        if len(raw) != 8:
            break
        nxt, ret = struct.unpack("<II", raw)
        if not ret:
            break
        lines.append("  #%-2d ebp 0x%08X  ret 0x%08X  %s" % (d, ebp, ret, mm.describe(ret)))
        if nxt <= ebp:
            break
        ebp = nxt
    lines.append("")
    lines.append("Call-preceded return addresses on the stack (ESP upward, %d bytes):"
                 % len(stack))
    shown = 0
    for i in range(0, max(0, len(stack) - 4), 4):
        v = struct.unpack_from("<I", stack, i)[0]
        if not mm.find(v):
            continue
        pre = rpm(hp, v - 8, 8)
        if len(pre) != 8:
            continue
        kind = None
        if pre[3] == 0xE8:
            tgt = (v + struct.unpack_from("<i", pre, 4)[0]) & 0xFFFFFFFF
            kind = "call 0x%08X  %s" % (tgt, mm.describe(tgt))
        else:
            for back, idx in ((2, 6), (3, 5), (4, 4), (6, 2), (7, 1)):
                if pre[idx] == 0xFF and (pre[idx + 1] & 0x38) == 0x10:
                    kind = "indirect call (%d-byte)" % back
                    break
        if not kind:
            continue
        lines.append("  [esp+0x%04X] 0x%08X  %-34s %s"
                     % (i, v, mm.describe(v), kind))
        shown += 1
        if shown >= 60:
            lines.append("  ... (truncated at 60)")
            break
    if not shown:
        lines.append("  (none -- the stack holds no return addresses into a loaded module)")
    return lines


def build_report(cap, mm, ctx, er):
    a = cap.args
    regs = {k: struct.unpack_from("<I", ctx, off)[0] for k, off in CTX_OFF.items()}
    code, flags, _rec, exc_addr, nparams = struct.unpack_from("<IIIII", er, 0)
    params = struct.unpack_from("<15I", er, 0x14)
    L = []
    L.append("=== AoW VEH crash capture ===")
    L.append("time            %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    L.append("pid             %d" % cap.pid)
    L.append("region          0x%08X (RWX, injected)" % cap.region)
    L.append("")
    L.append("CAUGHT")
    L.append("  exception     0x%08X  %s" % (code, exc_name(code)))
    L.append("  first-chance  %s" % ("no (already unwinding)" if flags & 2 else "yes"))
    L.append("  at            %s" % mm.describe(exc_addr, want_file=True))
    if code in (0xC0000005, 0xC0000006) and nparams >= 2:
        L.append("  access        %s at 0x%08X"
                 % (AV_KIND.get(params[0], "op %d" % params[0]), params[1]))
    L.append("  filter        code=%s eip=%s fault=%s skip=%d"
             % ("any" if a.any_code else "0x%08X" % a.code,
                "%s" % (a.at[0] + "+0x%X" % a.at[1] if a.at else
                        ("0x%08X-0x%08X" % a.eip_range if a.eip_range else "any")),
                ("0x%08X-0x%08X" % a.fault_range) if a.fault_range else "any",
                a.skip))
    L.append("  handler saw   %d exceptions, passed %d on" % (cap.ctl(CTL_SEEN),
                                                              cap.ctl(CTL_PASSED)))
    L.append("")
    L.append("REGISTERS")
    L.append("  EAX %08X  EBX %08X  ECX %08X  EDX %08X"
             % (regs["Eax"], regs["Ebx"], regs["Ecx"], regs["Edx"]))
    L.append("  ESI %08X  EDI %08X  EBP %08X  ESP %08X"
             % (regs["Esi"], regs["Edi"], regs["Ebp"], regs["Esp"]))
    L.append("  EIP %08X  EFL %08X  CS %04X SS %04X DS %04X ES %04X FS %04X GS %04X"
             % (regs["Eip"], regs["EFlags"], regs["SegCs"], regs["SegSs"], regs["SegDs"],
                regs["SegEs"], regs["SegFs"], regs["SegGs"]))
    L.append("")
    L.append("FAULT SITE")
    L.append("  EIP           %s" % mm.describe(regs["Eip"], want_file=True))
    hit = mm.find(regs["Eip"])
    if hit:
        name, base, _size, path = hit
        pe = mm.pe_for(name, path)
        if pe:
            rva = regs["Eip"] - base
            off, sec = pe.rva_to_off(rva)
            link = pe.image_base + rva
            if off is not None:
                L.append("  file offset   0x%08X in section %s  (link VA = file + 0x%08X)"
                         % (off, sec, link - off))
            elif sec:
                L.append("  file offset   none -- section %s has no raw data in the file" % sec)
            L.append('  read it with  python "Modding Resources/re_tools/dasm.py" %s 0x%08X 0x40'
                     % (name, link))
    pre = rpm(cap.hp, regs["Eip"] - 16, 16)
    if pre:
        L.append("  bytes -16     %s" % pre.hex())
    at = rpm(cap.hp, regs["Eip"], 32)
    if at:
        L.append("  bytes @EIP    %s" % at.hex())
        L.extend(disasm(at, regs["Eip"], limit=8))
    L.append("")
    L.extend(stack_report(cap.hp, mm, regs, a.stack_bytes))
    L.append("")
    L.append("MODULES (actual load bases in this run)")
    L.extend(mm.summary_lines())
    census = cap.read_census()
    if census:
        L.append("")
        L.append("EXCEPTION CENSUS (last %d seen, oldest first)" % len(census))
        for c, ad, info in census:
            L.append("  0x%08X %-42s at %s" % (c, exc_name(c), mm.describe(ad)))
    return "\n".join(L), regs


def census_report(cap, mm):
    L = ["=== AoW VEH exception census ===",
         "pid %d, %d exceptions seen, %d passed on" % (cap.pid, cap.ctl(CTL_SEEN),
                                                       cap.ctl(CTL_PASSED)), ""]
    rows = cap.read_census()
    if not rows:
        L.append("  (no exception reached the handler)")
    for c, ad, info in rows:
        extra = "  fault addr 0x%08X" % info if c in (0xC0000005, 0xC0000006) else ""
        L.append("  0x%08X %-42s at %s%s" % (c, exc_name(c), mm.describe(ad), extra))
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------
# A hand-built 32-bit test target, so the whole chain can be proved with no game involved
# ---------------------------------------------------------------------------------------------
TEST_IMAGE_BASE = 0x00400000
TEST_CODE_RVA = 0x1000
TEST_SEH_RVA = 0x1100
TEST_IAT_RVA = 0x1260
FAULT1_ADDR = 0x00000064
FAULT2_ADDR = 0x000000C8


def build_test_exe(path, mode="fault", delay_ms=0):
    """Write a minimal PE32 console exe importing kernel32!SetErrorMode/Sleep/ExitProcess.

    modes:
      'fault'  -- stamp recognisable values into the registers, then load from FAULT1_ADDR. One
                  fatal access violation, with known ground truth for every register.
      'fault2' -- install a frame-based SEH handler that steps over the faulting instruction, take
                  a first (survived) access violation, sleep, then take a second, fatal one with a
                  different register signature.  This is the shape of the real problem: Delphi
                  handles access violations inside `try..except`, so the FIRST one is often not
                  the fatal one.
      'clean'  -- exit 0 without faulting at all.

    Returns {'fault1': VA or None, 'fault2': VA or None}."""
    iat = TEST_IMAGE_BASE + TEST_IAT_RVA
    set_error_mode, sleep_fn, exit_process = iat, iat + 4, iat + 8
    vas = {"fault1": None, "fault2": None}

    code = bytearray()
    code += b"\x68" + u32(0x8003)                    # push SEM_FAILCRITICALERRORS|NOGPFAULTERRORBOX
    code += b"\xFF\x15" + u32(set_error_mode)        # call [SetErrorMode]   -- no WER dialog
    if mode == "fault2":
        code += b"\x68" + u32(TEST_IMAGE_BASE + TEST_SEH_RVA)   # push seh_handler
        code += b"\x64\xFF\x35" + u32(0)             # push dword fs:[0]
        code += b"\x64\x89\x25" + u32(0)             # mov fs:[0],esp
    if delay_ms:
        code += b"\x68" + u32(delay_ms)              # push delay_ms   (imm32: never let an
        code += b"\xFF\x15" + u32(sleep_fn)          # call [Sleep]     assembler shrink this)
    if mode in ("fault", "fault2"):
        code += b"\xB8" + u32(0x00ABCDEF)            # mov eax,00ABCDEFh
        code += b"\xBB" + u32(0xDEADBEEF)            # mov ebx,DEADBEEFh
        code += b"\xBE" + u32(0x11112222)            # mov esi,11112222h
        code += b"\xBF" + u32(0x33334444)            # mov edi,33334444h
        code += b"\xBA" + u32(FAULT1_ADDR)           # mov edx,64h
        vas["fault1"] = TEST_IMAGE_BASE + TEST_CODE_RVA + len(code)
        code += b"\x8B\x0A"                          # mov ecx,[edx]     <-- deliberate fault #1
    if mode == "fault2":
        code += b"\x64\x8F\x05" + u32(0)             # pop dword fs:[0]  unlink the SEH frame
        code += b"\x83\xC4\x04"                      # add esp,4
        code += b"\x68" + u32(800)                   # push 800
        code += b"\xFF\x15" + u32(sleep_fn)          # call [Sleep]      let the observer read SEEN
        code += b"\xB8" + u32(0x0A0B0C0D)            # mov eax,0A0B0C0Dh
        code += b"\xBB" + u32(0x0BADF00D)            # mov ebx,0BADF00Dh
        code += b"\xBA" + u32(FAULT2_ADDR)           # mov edx,0C8h
        vas["fault2"] = TEST_IMAGE_BASE + TEST_CODE_RVA + len(code)
        code += b"\x8B\x0A"                          # mov ecx,[edx]     <-- deliberate fault #2
    code += b"\x6A\x00"                              # push 0
    code += b"\xFF\x15" + u32(exit_process)          # call [ExitProcess]
    code += b"\xCC"
    assert len(code) <= TEST_SEH_RVA - TEST_CODE_RVA, "test code overruns the SEH handler"

    # cdecl(ExceptionRecord, EstablisherFrame, ContextRecord, DispatcherContext): step over the
    # 2-byte `mov ecx,[edx]` and continue.  The image declares no load config, so SafeSEH does not
    # apply and the chain stays well-formed for SEHOP.
    seh = bytearray()
    seh += b"\x8B\x44\x24\x0C"                       # mov eax,[esp+12]      ContextRecord
    seh += b"\x83\x80" + u32(CTX_OFF["Eip"]) + b"\x02"   # add dword [eax+0B8h],2
    seh += b"\x33\xC0"                               # xor eax,eax   ExceptionContinueExecution
    seh += b"\xC3"                                   # ret

    sec = bytearray(b"\x00" * 0x400)                 # one 0x400-byte section: code + imports
    sec[0:len(code)] = code
    sec[TEST_SEH_RVA - 0x1000:TEST_SEH_RVA - 0x1000 + len(seh)] = seh
    thunks = [0x1280, 0x1290, 0x12A0, 0]
    struct.pack_into("<IIIII", sec, 0x1200 - 0x1000, 0x1240, 0, 0, 0x1300, TEST_IAT_RVA)
    for i, t in enumerate(thunks):
        struct.pack_into("<I", sec, 0x1240 - 0x1000 + i * 4, t)
        struct.pack_into("<I", sec, TEST_IAT_RVA - 0x1000 + i * 4, t)
    for rva, nm in ((0x1280, b"SetErrorMode"), (0x1290, b"Sleep"), (0x12A0, b"ExitProcess")):
        o = rva - 0x1000
        struct.pack_into("<H", sec, o, 0)
        sec[o + 2:o + 2 + len(nm)] = nm
    sec[0x300:0x300 + 13] = b"kernel32.dll\x00"

    hdr = bytearray(b"\x00" * 0x200)
    hdr[0:2] = b"MZ"
    struct.pack_into("<I", hdr, 0x3C, 0x40)
    pe = 0x40
    hdr[pe:pe + 4] = b"PE\x00\x00"
    struct.pack_into("<HHIIIHH", hdr, pe + 4, 0x014C, 1, 0, 0, 0, 0xE0, 0x0103)
    opt = pe + 24
    struct.pack_into("<HBB", hdr, opt, 0x10B, 1, 0)
    struct.pack_into("<III", hdr, opt + 0x04, 0x400, 0, 0)
    struct.pack_into("<III", hdr, opt + 0x10, TEST_CODE_RVA, TEST_CODE_RVA, TEST_CODE_RVA)
    struct.pack_into("<III", hdr, opt + 0x1C, TEST_IMAGE_BASE, 0x1000, 0x200)
    struct.pack_into("<HHHHHH", hdr, opt + 0x28, 4, 0, 0, 0, 4, 0)
    struct.pack_into("<III", hdr, opt + 0x34, 0, 0x2000, 0x200)
    struct.pack_into("<IHH", hdr, opt + 0x40, 0, 3, 0)
    struct.pack_into("<IIII", hdr, opt + 0x48, 0x100000, 0x1000, 0x100000, 0x1000)
    struct.pack_into("<II", hdr, opt + 0x58, 0, 16)
    struct.pack_into("<II", hdr, opt + 0x60 + 1 * 8, 0x1200, 40)      # import directory
    struct.pack_into("<II", hdr, opt + 0x60 + 12 * 8, TEST_IAT_RVA, 16)
    s = opt + 0xE0
    hdr[s:s + 8] = b".text\x00\x00\x00"
    struct.pack_into("<IIII", hdr, s + 8, 0x400, TEST_CODE_RVA, 0x400, 0x200)
    struct.pack_into("<I", hdr, s + 0x24, 0xE0000060)   # CODE|DATA|EXEC|READ|WRITE
    with open(path, "wb") as fh:
        fh.write(bytes(hdr) + bytes(sec))
    return vas


# ---------------------------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------------------------
def selftest(base_args):
    print("=" * 78)
    print("SELF-TEST -- hand-built 32-bit target, no AoW binary is touched")
    print("=" * 78)
    tmp = tempfile.mkdtemp(prefix="vehcap_")
    results = []
    made = []

    def scenario(name, mode, delay, expect, mutate=None):
        print("\n--- %s ---" % name)
        # A fresh file per scenario: TerminateProcess is asynchronous and the image section keeps
        # the previous exe locked for a moment afterwards.
        exe = os.path.join(tmp, "vehtest%d.exe" % len(made))
        made.append(exe)
        vas = build_test_exe(exe, mode=mode, delay_ms=delay)
        args = argparse.Namespace(**vars(base_args))
        args.timeout = 25
        args.stack_bytes = 0x400
        if mutate:
            mutate(args, os.path.basename(exe), vas)
        cap = Capture(args)
        outcome = {}
        try:
            cap.launch(exe, tmp)
            add_veh = cap.find_add_veh()
            cap.alloc()
            cap.inject(add_veh)
            cap.resume()
            state = cap.wait()
            outcome["state"] = state
            outcome["vas"] = vas
            if state == "captured":
                ctx = rpm(cap.hp, cap.region + OFF_CTX, CONTEXT_SIZE)
                er = rpm(cap.hp, cap.region + OFF_ER, ER_SIZE)
                regs = {k: struct.unpack_from("<I", ctx, o)[0] for k, o in CTX_OFF.items()}
                ecode, _f, _r, eaddr, _n = struct.unpack_from("<IIIII", er, 0)
                params = struct.unpack_from("<15I", er, 0x14)
                outcome.update(regs=regs, code=ecode, addr=eaddr, params=params,
                               seen=cap.ctl(CTL_SEEN), passed=cap.ctl(CTL_PASSED))
                frozen = [t for t in threads_of(cap.pid)
                          if (thread_eip(t) or 0) in (cap.spin_va, cap.spin_va + 2)]
                outcome["frozen_tids"] = frozen
            elif state == "exited":
                outcome["exit_code"] = cap.exit_code
                outcome["seen"] = cap.ctl(CTL_SEEN)
                outcome["passed"] = cap.ctl(CTL_PASSED)
        finally:
            if cap.hp:
                k32.TerminateProcess(cap.hp, 1)
                k32.WaitForSingleObject(cap.hp, 5000)
            cap.close()
        ok, why = expect(outcome)
        results.append((name, ok, why))
        print("  %s  %s" % ("PASS" if ok else "FAIL", why))
        return outcome

    def check(o, pairs):
        bad = ["%s=0x%08X want 0x%08X" % (n, g, w) for n, g, w in pairs if g != w]
        return bad

    # A -- the happy path: the handler installs, catches the AV, freezes the thread, and every
    #      register the target stamped comes back verbatim.
    def expect_a(o):
        if o.get("state") != "captured":
            return False, "expected a capture, got %r" % o.get("state")
        r, f1 = o["regs"], o["vas"]["fault1"]
        bad = check(o, [
            ("exception code", o["code"], 0xC0000005),
            ("EAX", r["Eax"], 0x00ABCDEF), ("EBX", r["Ebx"], 0xDEADBEEF),
            ("ESI", r["Esi"], 0x11112222), ("EDI", r["Edi"], 0x33334444),
            ("EDX (fault ptr)", r["Edx"], FAULT1_ADDR),
            ("EIP", r["Eip"], f1), ("ExceptionAddress", o["addr"], f1),
            ("AV kind (read)", o["params"][0], 0), ("AV address", o["params"][1], FAULT1_ADDR),
        ])
        if bad:
            return False, "; ".join(bad)
        if not o.get("frozen_tids"):
            return False, "no thread was found spinning in the handler"
        return True, ("captured at EIP 0x%08X, all 10 ground-truth values match, thread %d frozen "
                      "in the spin loop" % (r["Eip"], o["frozen_tids"][0]))

    scenario("A  capture + register ground truth (1.5 s delay before the fault)",
             "fault", 1500, expect_a)

    # B -- the filter must REJECT a non-matching fault, and the tool must report the resulting
    #      unhandled crash honestly rather than silently timing out.  The target survives its
    #      first fault via its own SEH, so the rejection is observable while it is still alive.
    def mutate_b(args, exe_name, vas):
        args.fault_range = (0x00500000, 0x00600000)     # the real faults are at 0x64 / 0xC8

    def expect_b(o):
        if o.get("state") == "captured":
            return False, "the filter let through a fault it should have rejected"
        if o.get("state") != "exited":
            return False, "expected the target to die unhandled, got %r" % o.get("state")
        if o.get("exit_code") != 0xC0000005:
            return False, "exit code 0x%08X, expected 0xC0000005" % o.get("exit_code", 0)
        if not o.get("seen") or not o.get("passed"):
            return False, "handler counters SEEN=%s PASSED=%s -- rejection is unproven" \
                          % (o.get("seen"), o.get("passed"))
        return True, ("filter rejected it: handler saw %d exception(s), passed %d on, target then "
                      "died unhandled with 0xC0000005" % (o["seen"], o["passed"]))

    scenario("B  non-matching filter passes faults through", "fault2", 0, expect_b,
             mutate=mutate_b)

    # C -- a target that never faults must be reported as a normal exit, not as a capture.
    def expect_c(o):
        if o.get("state") != "exited":
            return False, "expected a normal exit, got %r" % o.get("state")
        if o.get("exit_code") != 0:
            return False, "exit code 0x%08X, expected 0" % o.get("exit_code", 0)
        return True, "target exited normally (code 0) and no capture was claimed"

    scenario("C  target exits normally", "clean", 0, expect_c)

    # D -- --skip 1 must let the FIRST access violation through and freeze on the SECOND, which is
    #      exactly the Delphi situation (an AV swallowed by try..except before the fatal one).
    def mutate_d(args, exe_name, vas):
        args.skip = 1

    def expect_d(o):
        if o.get("state") != "captured":
            return False, "expected a capture on the second fault, got %r" % o.get("state")
        r, f2 = o["regs"], o["vas"]["fault2"]
        bad = check(o, [("EIP", r["Eip"], f2), ("EAX", r["Eax"], 0x0A0B0C0D),
                        ("EBX", r["Ebx"], 0x0BADF00D),
                        ("AV address", o["params"][1], FAULT2_ADDR)])
        if bad:
            return False, "froze on the wrong fault: " + "; ".join(bad)
        return True, ("first AV skipped, froze on the SECOND at EIP 0x%08X with its own register "
                      "signature" % r["Eip"])

    scenario("D  --skip 1 skips the first AV and takes the second", "fault2", 0, expect_d,
             mutate=mutate_d)

    # E -- the deferred module-relative arming path (`--at MODULE+0xRVA`), which cannot be armed
    #      at injection time because no module but ntdll is mapped in a suspended process.
    def mutate_e(args, exe_name, vas):
        args.at = (exe_name, vas["fault1"] - TEST_IMAGE_BASE, 1)

    def expect_e(o):
        if o.get("state") != "captured":
            return False, "expected a capture, got %r" % o.get("state")
        if o["regs"]["Eip"] != o["vas"]["fault1"]:
            return False, "froze at 0x%08X, expected 0x%08X" % (o["regs"]["Eip"],
                                                                o["vas"]["fault1"])
        return True, "module-relative filter armed after load and matched at 0x%08X" \
                     % o["regs"]["Eip"]

    scenario("E  --at MODULE+RVA arms once the module is loaded", "fault", 1500, expect_e,
             mutate=mutate_e)

    for f in made:
        for _ in range(20):
            try:
                os.remove(f)
                break
            except OSError:
                time.sleep(0.1)
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    print("\n" + "=" * 78)
    for name, ok, why in results:
        print("  %-4s %s" % ("PASS" if ok else "FAIL", name))
    bad = [r for r in results if not r[1]]
    print("=" * 78)
    print("%d/%d scenarios passed" % (len(results) - len(bad), len(results)))
    return 1 if bad else 0


# ---------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------
def parse_range(text):
    a, _, b = text.partition("-")
    if not b:
        raise argparse.ArgumentTypeError("expected LO-HI, e.g. 0-0x100000")
    return (int(a, 0), int(b, 0))


def parse_at(text):
    """MODULE+0xOFF[:SPAN] -- the fault instruction must lie in [base+OFF, base+OFF+SPAN)."""
    mod, _, rest = text.partition("+")
    if not rest:
        raise argparse.ArgumentTypeError("expected MODULE+0xOFFSET, e.g. AoWEPACK.dpl+0x7B24E")
    off, _, span = rest.partition(":")
    return (mod, int(off, 0), int(span, 0) if span else 1)


def build_parser():
    p = argparse.ArgumentParser(
        prog="veh_capture.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__)
    p.add_argument("--exe", default=zigexe.GAME_EXE,
                   help="target by name, or a full path (default %s). %s and %s also work; the "
                        "name is resolved to whichever tree holds the RUNNABLE copy. "
                        "⚠ AoW.exe / AoWCompat.exe are the VANILLA pair -- only pass one on purpose."
                        % (zigexe.GAME_EXE, zigexe.COMPAT_EXE, zigexe.LIVE_EDITOR))
    p.add_argument("--attach", type=int, metavar="PID",
                   help="inject into an already-running process instead of launching one. "
                        "Never terminates it.")
    p.add_argument("--code", type=lambda s: int(s, 0), default=0xC0000005,
                   help="exception code to freeze on (default 0xC0000005, access violation)")
    p.add_argument("--any-code", action="store_true", help="freeze on any exception code")
    # Both write the same pair of filter words in the injected control block, so allowing both
    # would let one silently win over the other.
    where = p.add_mutually_exclusive_group()
    where.add_argument("--at", type=parse_at, metavar="MOD+OFF[:SPAN]",
                       help="freeze only when the faulting instruction is at MODULE+OFFSET, "
                            "resolved against that module's real load base "
                            "(e.g. AoWEPACK.dpl+0x7B24E:8)")
    where.add_argument("--eip-range", type=parse_range, metavar="LO-HI",
                       help="freeze only on a faulting instruction in this absolute VA range")
    p.add_argument("--fault-range", type=parse_range, metavar="LO-HI",
                   help="freeze only when the faulting DATA address is in this range "
                        "(e.g. 0-0x100000 for near-null dereferences)")
    p.add_argument("--skip", type=int, default=0, metavar="N",
                   help="let the first N matching exceptions through (Delphi handles some AVs "
                        "itself, so the fatal one is not always the first)")
    p.add_argument("--census", action="store_true",
                   help="arm nothing: run the target and list the exceptions it raises, so you "
                        "can choose a filter. Never freezes the target.")
    p.add_argument("--timeout", type=int, default=600, metavar="SEC",
                   help="give up after this many seconds (default 600; 0 = wait forever)")
    p.add_argument("--stack-bytes", type=lambda s: int(s, 0), default=0x2000,
                   help="how much stack above ESP to scan for return addresses (default 0x2000)")
    p.add_argument("--keep", action="store_true",
                   help="leave the frozen process alive after the dump (default: terminate it)")
    p.add_argument("--ntdll-base", type=lambda s: int(s, 0),
                   help="override the target's 32-bit ntdll base if auto-detection fails")
    p.add_argument("--dis", action="store_true",
                   help="disassemble the shellcode and exit -- launches nothing")
    p.add_argument("--self-test", action="store_true",
                   help="prove the whole mechanism against a hand-built 32-bit target")
    return p


def show_shellcode():
    region = 0x30000000
    handler, spin = build_handler(region)
    stub = build_stub(region, 0x77001234)
    print("region 0x%08X   handler 0x%08X (%d bytes)   stub 0x%08X (%d bytes)   spin 0x%08X"
          % (region, region + OFF_HANDLER, len(handler), region + OFF_STUB, len(stub), spin))
    print("control block 0x%08X:" % (region + OFF_CTL))
    print("   " + "  ".join("%s=+0x%02X" % (n, o) for o, n in CTL_NAMES))
    print("\nHANDLER")
    for line in disasm(handler, region + OFF_HANDLER):
        print(line)
    print("\nINSTALL STUB (RtlAddVectoredExceptionHandler shown as 0x77001234 placeholder)")
    for line in disasm(stub, region + OFF_STUB):
        print(line)


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.dis:
        show_shellcode()
        return 0
    if args.self_test:
        k32.SetErrorMode(0x8003)
        return selftest(args)

    if os.path.exists(OUT):
        os.remove(OUT)
        print("(removed stale %s)" % os.path.basename(OUT))

    cap = Capture(args)
    try:
        if args.attach:
            cap.attach(args.attach)
        else:
            exe = resolve_target(args.exe)
            if not os.path.isfile(exe):
                print("[x] no such target: %s" % exe)
                return 2
            pe = disk_pe(exe)
            if pe and pe.machine != 0x014C:
                print("[x] %s is not a 32-bit i386 image (machine 0x%04X). This tool injects "
                      "x86 shellcode." % (os.path.basename(exe), pe.machine))
                return 2
            # cwd = the resolved exe's own directory, not GAME: the runnable pair lives at the ROOT.
            cap.launch(exe, os.path.dirname(exe))
        add_veh = cap.find_add_veh()
        cap.alloc()
        cap.inject(add_veh)
        cap.resume()
    except RuntimeError as e:
        print("[x] %s" % e)
        if cap.owns_process and cap.hp:
            k32.TerminateProcess(cap.hp, 1)
            print("    the suspended target (pid %d) was terminated." % cap.pid)
        cap.close()
        return 2

    if args.census:
        print("running. Play until the crash; Ctrl-C to stop and print the census.")
    else:
        print("running. Play until it crashes -- the faulting thread will freeze and be dumped.")
    state = cap.wait()
    mm = ModuleMap(cap.mods(), cap.launched_path)
    rc = 0

    if state == "captured":
        ctx = rpm(cap.hp, cap.region + OFF_CTX, CONTEXT_SIZE)
        er = rpm(cap.hp, cap.region + OFF_ER, ER_SIZE)
        if len(ctx) != CONTEXT_SIZE or len(er) != ER_SIZE:
            print("[x] the capture buffers could not be read back (process gone?)")
            rc = 2
        else:
            text, regs = build_report(cap, mm, ctx, er)
            frozen = [t for t in threads_of(cap.pid)
                      if (thread_eip(t) or 0) in (cap.spin_va, cap.spin_va + 2)]
            text += "\n\nFROZEN THREAD(S): %s (spinning at 0x%08X inside the handler)" % (
                ", ".join(str(t) for t in frozen) or "none found", cap.spin_va)
            print("\n" + text)
            with open(OUT, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
            print("\nwritten to %s" % OUT)
    elif state == "exited":
        ec = cap.exit_code
        print("\n[!] the target EXITED (code 0x%08X = %d) without a matching capture."
              % (ec, ec if ec < 0x80000000 else ec - (1 << 32)))
        if ec in EXC_NAMES and args.census:
            print("    That exit code IS an exception status (%s), so it crashed. Census mode "
                  "never freezes, by design -- what it saw is below." % exc_name(ec))
        elif ec in EXC_NAMES:
            print("    That exit code IS an exception status (%s), so it crashed -- but not in a "
                  "way this filter matched." % exc_name(ec))
            print("    Re-run with --any-code, or with --skip N, or --census to see what the game "
                  "actually raises before choosing a filter.")
        elif ec == 0:
            print("    Clean exit -- the game shut down normally. Nothing to report.")
        print("    handler saw %d exception(s), passed %d on."
              % (cap.ctl(CTL_SEEN), cap.ctl(CTL_PASSED)))
        print("\n" + census_report(cap, mm))
        rc = 1
    else:
        why = "timed out after %d s" % args.timeout if state == "timeout" else "interrupted"
        alive, _ = cap.alive()
        print("\n[!] %s with no capture. Handler saw %d exception(s), passed %d on."
              % (why, cap.ctl(CTL_SEEN), cap.ctl(CTL_PASSED)))
        print("\n" + census_report(cap, mm))
        if alive:
            cap.disarm()
            print("\n    The handler has been DISARMED, so the target will now crash normally "
                  "instead of freezing with nobody watching.")
            print("    It stays resident (as a harmless counter) until the process exits.")
            print("    pid %d is still running. To end it:  taskkill /PID %d /F"
                  % (cap.pid, cap.pid))
        rc = 1

    if state == "captured":
        if args.keep or not cap.owns_process:
            print("\n    pid %d is left FROZEN (thread spinning in the handler). It will not "
                  "respond to input." % cap.pid)
            print("    To end it:  taskkill /PID %d /F" % cap.pid)
        else:
            k32.TerminateProcess(cap.hp, 1)
            print("\n    frozen pid %d terminated (pass --keep to inspect it further)" % cap.pid)
    cap.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
