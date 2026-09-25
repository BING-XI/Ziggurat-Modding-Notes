#!/usr/bin/env python3
r"""
hwbp.py -- hardware WATCHPOINT on one address in a running AoW1: log every instruction that writes
(or touches) it, with registers and the call chain, then detach and leave the game running.

WHEN TO REACH FOR THIS
----------------------
"Something overwrites this field and I don't know what."  A static xref hunt misses writers that
reach the field through a register, a VMT slot or a cave; this catches the instruction in the act.

    crashed / vanished          ->  veh_capture.py
    frozen, no input            ->  hang_stack.py
    a value changes, who did it ->  hwbp.py          (this tool)
    who points at this object   ->  ref_probe.py

Ported 2026-09-25 from Inioch's diag_hwbp.py (share8).  Changed here: target and module names come
from zigexe; the address can be absolute, MODULE+offset or a link-time VA, so a rebased package is
handled; hits are described with link VA and file offset (veh_capture's ModuleMap); the WOW64
single-step code a 64-bit debugger actually receives (0x4000001E) is recognised; access width and
kind are selectable; and nothing is written to disk unless --log is given.

USAGE
-----
    python hwbp.py AoWEPACK.dpl+0x1FA850                 # write-watch a dword in the game
    python hwbp.py @0x558FA850                           # the same, by link-time VA
    python hwbp.py 0x0A3301B4 --len 1 --access rw        # a heap byte, reads too
    python hwbp.py 0x0A3301B4 --pid 1234 --seconds 60 --log <path>

MECHANISM AND ITS COST
----------------------
DebugActiveProcess, then Dr0/Dr7 on every thread (existing threads arrive as CREATE_THREAD events;
new ones are armed as they start).  Each hit is a single-step debug event: the thread is stopped
while this side reads its context and stack, then continued.  DebugSetProcessKillOnExit(False), so
if this tool dies the game keeps running; on exit every thread's Dr7 is cleared and the debugger
detaches.

⚠ Attaching a debugger to a RUNNING process does not switch on the debug heap (that is decided at
process creation), so the heap-layout Heisenbug veh_capture.py exists to dodge does not apply here.
⚠ x86 data breakpoints fire AFTER the access: EIP is the instruction following the writer.  The
report prints both, and disassembles the preceding bytes so the writer itself is visible.
⚠ A hot address (written every frame) floods the log and slows the game.  Use --max-hits.
"""
import argparse
import ctypes as C
import ctypes.wintypes as W
import os
import struct
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import veh_capture as V                       # noqa: E402  (k32, rpm, modules, ModuleMap, disasm)
from zignames import zigexe                   # noqa: E402

k32 = V.k32
k32.DebugActiveProcess.argtypes = [W.DWORD]
k32.DebugActiveProcessStop.argtypes = [W.DWORD]
k32.DebugSetProcessKillOnExit.argtypes = [W.BOOL]
k32.ContinueDebugEvent.argtypes = [W.DWORD, W.DWORD, W.DWORD]
k32.OpenThread.restype = C.c_void_p
k32.OpenThread.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.OpenProcess.restype = C.c_void_p
k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.Wow64GetThreadContext.argtypes = [C.c_void_p, C.c_void_p]
k32.Wow64SetThreadContext.argtypes = [C.c_void_p, C.c_void_p]

DBG_CONTINUE, DBG_EXCEPTION_NOT_HANDLED = 0x00010002, 0x80010001
EXCEPTION_DEBUG_EVENT, CREATE_THREAD_DEBUG_EVENT, CREATE_PROCESS_DEBUG_EVENT = 1, 2, 3
EXIT_PROCESS_DEBUG_EVENT = 5
SINGLE_STEP = (0x80000004, 0x4000001E)        # native, and STATUS_WX86_SINGLE_STEP under WOW64
BREAKPOINT = (0x80000003, 0x4000001F)         # the attach breakpoint, in either form
CTX_I386_DEBUG = 0x00010010                   # CONTEXT_i386 | CONTEXT_DEBUG_REGISTERS
CTX_I386_FULL = 0x00010007                    # CONTROL | INTEGER | SEGMENTS
WCTX_SIZE = 0x2CC
OFF_DR0, OFF_DR6, OFF_DR7 = 0x04, 0x14, 0x18
RW_BITS = {"write": 0b01, "rw": 0b11}
LEN_BITS = {1: 0b00, 2: 0b01, 4: 0b11}


class EXCEPTION_RECORD32(C.Structure):
    # A 64-bit debugger receives the 64-bit layout even for a WOW64 debuggee.
    _fields_ = [("ExceptionCode", W.DWORD), ("ExceptionFlags", W.DWORD),
                ("ExceptionRecord", C.c_void_p), ("ExceptionAddress", C.c_void_p),
                ("NumberParameters", W.DWORD), ("ExceptionInformation", C.c_ulonglong * 15)]


class DEBUG_EVENT(C.Structure):
    _fields_ = [("dwDebugEventCode", W.DWORD), ("dwProcessId", W.DWORD),
                ("dwThreadId", W.DWORD), ("u", C.c_ulonglong * 22)]
    # ⚠ The union is 8-aligned on x64, so it starts at +16, not +12. A byte array here would put it
    # at +12 and every ExceptionCode would be read four bytes off (Inioch's original had this).


k32.WaitForDebugEvent.argtypes = [C.POINTER(DEBUG_EVENT), W.DWORD]


def find_pid(name):
    import subprocess
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + name, "/NH", "/FO", "CSV"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == name.lower():
            return int(parts[1])
    return None


def resolve_addr(text, pid):
    """0xABS | MODULE+0xOFF | @0xLINKVA -> the absolute address in THIS run."""
    mods = V.modules(pid)
    if text.startswith("@"):
        link = int(text[1:], 16)
        for name, base, size, path in mods:
            pe = V.disk_pe(path)
            if pe and pe.image_base <= link < pe.image_base + size:
                return base + (link - pe.image_base), "%s link 0x%08X" % (name, link)
        raise SystemExit("[x] no loaded module's preferred range contains 0x%08X" % link)
    if "+" in text:
        mod, _, off = text.partition("+")
        for name, base, size, path in mods:
            if name.lower() == mod.lower():
                return base + int(off, 16), text
        raise SystemExit("[x] module %s is not loaded in pid %d" % (mod, pid))
    return int(text, 16), "absolute"


def set_drs(tid, dr0, dr7):
    ht = k32.OpenThread(0x1FFFFF, False, tid)
    if not ht:
        return False
    try:
        ctx = C.create_string_buffer(WCTX_SIZE)
        struct.pack_into("<I", ctx, 0, CTX_I386_DEBUG)
        if not k32.Wow64GetThreadContext(ht, ctx):
            return False
        struct.pack_into("<I", ctx, OFF_DR0, dr0)
        struct.pack_into("<I", ctx, OFF_DR6, 0)
        struct.pack_into("<I", ctx, OFF_DR7, dr7)
        return bool(k32.Wow64SetThreadContext(ht, ctx))
    finally:
        k32.CloseHandle(ht)


def thread_regs(tid):
    ht = k32.OpenThread(0x1FFFFF, False, tid)
    if not ht:
        return None
    try:
        ctx = C.create_string_buffer(WCTX_SIZE)
        struct.pack_into("<I", ctx, 0, CTX_I386_FULL)
        if not k32.Wow64GetThreadContext(ht, ctx):
            return None
        return {k: struct.unpack_from("<I", ctx, o)[0] for k, o in V.CTX_OFF.items()}
    finally:
        k32.CloseHandle(ht)


def call_chain(hp, mm, esp, limit=12):
    stack = V.rpm(hp, esp, 0x800)
    rows = []
    for i in range(0, max(0, len(stack) - 3), 4):
        v = struct.unpack_from("<I", stack, i)[0]
        hit = mm.find(v)
        if not hit or not hit[0].lower().endswith((".exe", ".dpl")):
            continue
        pre = V.rpm(hp, v - 8, 8)
        if len(pre) == 8 and (pre[3] == 0xE8 or any(pre[k] == 0xFF and (pre[k + 1] & 0x38) == 0x10
                                                       for k in (1, 2, 4, 5, 6))):
            rows.append("      [esp+0x%03X] %s" % (i, mm.describe(v)))
            if len(rows) >= limit:
                break
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(prog="hwbp.py", formatter_class=argparse.RawDescriptionHelpFormatter,
                                description=__doc__)
    p.add_argument("addr", help="0xABS, MODULE+0xOFF, or @0xLINKVA")
    p.add_argument("--pid", type=int, help="default: the running %s" % zigexe.GAME_EXE)
    p.add_argument("--exe", default=zigexe.GAME_EXE, help="process name to attach to")
    p.add_argument("--len", type=int, choices=(1, 2, 4), default=4, help="watched width (default 4)")
    p.add_argument("--access", choices=("write", "rw"), default="write",
                   help="write (default), or rw = reads too")
    p.add_argument("--seconds", type=int, default=300, help="stop after this long (default 300)")
    p.add_argument("--max-hits", type=int, default=200, help="stop after this many hits")
    p.add_argument("--log", help="also append the report to this file (nothing is written without it)")
    a = p.parse_args(argv)

    pid = a.pid or find_pid(a.exe)
    if not pid:
        print("[x] %s is not running (or pass --pid)" % a.exe)
        return 2
    addr, how = resolve_addr(a.addr, pid)
    if addr % a.len:
        print("[x] 0x%08X is not %d-byte aligned; x86 debug registers need natural alignment"
              % (addr, a.len))
        return 2
    dr7 = 0x1 | (RW_BITS[a.access] << 16) | (LEN_BITS[a.len] << 18)
    logf = open(a.log, "a", encoding="utf-8") if a.log else None

    def log(msg):
        line = time.strftime("%H:%M:%S ") + msg
        print(line, flush=True)
        if logf:
            logf.write(line + "\n")
            logf.flush()

    hp = k32.OpenProcess(0x1FFFFF, False, pid)
    if not hp:
        print("[x] OpenProcess(%d) failed, error %d" % (pid, C.get_last_error()))
        return 2
    if not k32.DebugActiveProcess(pid):
        print("[x] DebugActiveProcess(%d) failed, error %d (another debugger attached?)"
              % (pid, C.get_last_error()))
        return 2
    k32.DebugSetProcessKillOnExit(False)
    mm = V.ModuleMap(V.modules(pid))
    log("attached pid %d; %s-watch %d byte(s) at 0x%08X (%s)  %s"
        % (pid, a.access, a.len, addr, how, mm.describe(addr)))

    armed, hits, t0 = set(), 0, time.time()
    ev = DEBUG_EVENT()
    try:
        while time.time() - t0 < a.seconds and hits < a.max_hits:
            if not k32.WaitForDebugEvent(C.byref(ev), 500):
                continue
            status = DBG_CONTINUE
            code = ev.dwDebugEventCode
            if code in (CREATE_THREAD_DEBUG_EVENT, CREATE_PROCESS_DEBUG_EVENT):
                if set_drs(ev.dwThreadId, addr, dr7):
                    armed.add(ev.dwThreadId)
            elif code == EXIT_PROCESS_DEBUG_EVENT:
                log("the process exited")
                k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status)
                armed.clear()
                break
            elif code == EXCEPTION_DEBUG_EVENT:
                er = EXCEPTION_RECORD32.from_buffer_copy(bytes(ev.u)[:C.sizeof(EXCEPTION_RECORD32)])
                xc = er.ExceptionCode
                if xc in SINGLE_STEP:
                    hits += 1
                    r = thread_regs(ev.dwThreadId) or {}
                    eip = r.get("Eip", 0)
                    now = V.rpm(hp, addr, a.len)
                    val = int.from_bytes(now, "little") if len(now) == a.len else None
                    if not mm.find(eip):
                        mm = V.ModuleMap(V.modules(pid))
                    log("--- hit #%d  thread %d  value now %s" % (
                        hits, ev.dwThreadId, "0x%0*X" % (2 * a.len, val) if val is not None else "?"))
                    log("    after %s" % mm.describe(eip, want_file=True))
                    pre = V.rpm(hp, eip - 12, 12)
                    for line in V.disasm(pre, eip - 12)[-3:]:
                        log("    " + line.strip())
                    log("    EAX %08X EBX %08X ECX %08X EDX %08X ESI %08X EDI %08X EBP %08X ESP %08X"
                        % tuple(r.get(k, 0) for k in ("Eax", "Ebx", "Ecx", "Edx", "Esi", "Edi",
                                                      "Ebp", "Esp")))
                    for line in call_chain(hp, mm, r.get("Esp", 0)):
                        log(line)
                    set_drs(ev.dwThreadId, addr, dr7)      # clears Dr6 for the next hit
                elif xc in BREAKPOINT:
                    pass                                    # the attach breakpoint
                else:
                    status = DBG_EXCEPTION_NOT_HANDLED      # the game's own: let it handle it
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status)
    except KeyboardInterrupt:
        log("interrupted")
    finally:
        for tid in armed:
            set_drs(tid, 0, 0)
        k32.DebugActiveProcessStop(pid)
        k32.CloseHandle(hp)
        log("detached; %d hit(s) logged" % hits)
        if logf:
            logf.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
