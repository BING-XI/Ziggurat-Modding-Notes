#!/usr/bin/env python3
r"""
hang_stack.py -- capture WHERE a frozen AoW1 is stuck, without installing a debugger.

THE PROBLEM IT SOLVES
---------------------
The game hangs (sound still running, no input, exclusive fullscreen so you often cannot even alt-tab
to start a tool). It is FROZEN, not crashed: the process is alive and its stack is intact. So instead
of bisecting features one play-session at a time, read the stuck thread's EIP and walk its call
frames from outside. That names the exact function in one run.

This is `live_ui.py`'s trick (out-of-band ReadProcessMemory) extended with Wow64GetThreadContext, so
it needs no debugger, no symbols and no game cooperation. It only SUSPENDS a thread briefly to take a
consistent register snapshot and always resumes it, so it is safe to run against a healthy game too.

USAGE
-----
    python hang_stack.py --watch            # start BEFORE playing; auto-dumps when the game stalls
    python hang_stack.py                    # one-shot snapshot right now
    python hang_stack.py --watch --stall 8  # require 8 consecutive identical samples

`--watch` is the practical mode: start it, play until the freeze, and it writes `hang_stack.txt` next
to this script the moment the main thread stops moving. Nothing to alt-tab to.

READING THE OUTPUT
------------------
Addresses are resolved to `module+RVA`, and for AoWEPACK.dpl also to its LINK-TIME VA (RVA +
0x55700000) so they paste straight into Ghidra and match every address in the build scripts and docs.
A frame inside 0x5580xxxx-0x5581xxxx is one of OUR CAVES, and the cave map in the build scripts says
which feature owns it. Anything else is stock game code.

CAVEAT: the EBP chain is only as good as the frames' prologues. Delphi keeps EBP frames in most
functions but not all, so treat the top frame (EIP) as authoritative and the rest as strong hints;
a frame that looks absurd is probably a missing-prologue gap, not proof.
"""
import ctypes as C
import ctypes.wintypes as W
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zignames import zigexe

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "hang_stack.txt")
LOGF = os.path.join(HERE, "hang_watch.log")
AOWEPACK_LINK_BASE = 0x55700000

def log(msg):
    """Everything the watcher does goes to hang_watch.log as well as the console. Two silent
    no-capture runs happened because the tool could fail (access denied, no modules, no thread
    contexts) with nothing on disk to show which stage broke. Instrument the instrument."""
    line = "%s  %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOGF, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass

TH32CS_SNAPTHREAD   = 0x00000004
TH32CS_SNAPMODULE   = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ           = 0x0010
THREAD_SUSPEND_RESUME = 0x0002
THREAD_GET_CONTEXT    = 0x0008
WOW64_CONTEXT_FULL    = 0x00010007

k32 = C.WinDLL("kernel32", use_last_error=True)

# ctypes defaults every restype to 32-bit int. On 64-bit Python that TRUNCATES returned HANDLEs and
# every subsequent call silently fails with no exception -- declare them explicitly.
k32.CreateToolhelp32Snapshot.restype = W.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
k32.OpenThread.restype = W.HANDLE
k32.OpenThread.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.OpenProcess.restype = W.HANDLE
k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.CloseHandle.argtypes = [W.HANDLE]
k32.Wow64SuspendThread.restype = W.DWORD
k32.Wow64SuspendThread.argtypes = [W.HANDLE]
k32.ResumeThread.restype = W.DWORD
k32.ResumeThread.argtypes = [W.HANDLE]
k32.Wow64GetThreadContext.restype = W.BOOL
k32.ReadProcessMemory.restype = W.BOOL
k32.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t,
                                  C.POINTER(C.c_size_t)]
INVALID_HANDLE = C.c_void_p(-1).value

class THREADENTRY32(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ThreadID", W.DWORD),
                ("th32OwnerProcessID", W.DWORD), ("tpBasePri", W.LONG),
                ("tpDeltaPri", W.LONG), ("dwFlags", W.DWORD)]

class MODULEENTRY32(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("th32ModuleID", W.DWORD), ("th32ProcessID", W.DWORD),
                ("GlblcntUsage", W.DWORD), ("ProccntUsage", W.DWORD),
                ("modBaseAddr", C.POINTER(C.c_byte)), ("modBaseSize", W.DWORD),
                ("hModule", W.HMODULE), ("szModule", C.c_char * 256),
                ("szExePath", C.c_char * 260)]

class WOW64_FLOATING_SAVE_AREA(C.Structure):
    _fields_ = [("ControlWord", W.DWORD), ("StatusWord", W.DWORD), ("TagWord", W.DWORD),
                ("ErrorOffset", W.DWORD), ("ErrorSelector", W.DWORD), ("DataOffset", W.DWORD),
                ("DataSelector", W.DWORD), ("RegisterArea", C.c_byte * 80), ("Cr0NpxState", W.DWORD)]

class WOW64_CONTEXT(C.Structure):
    _fields_ = [("ContextFlags", W.DWORD), ("Dr0", W.DWORD), ("Dr1", W.DWORD), ("Dr2", W.DWORD),
                ("Dr3", W.DWORD), ("Dr6", W.DWORD), ("Dr7", W.DWORD),
                ("FloatSave", WOW64_FLOATING_SAVE_AREA),
                ("SegGs", W.DWORD), ("SegFs", W.DWORD), ("SegEs", W.DWORD), ("SegDs", W.DWORD),
                ("Edi", W.DWORD), ("Esi", W.DWORD), ("Ebx", W.DWORD), ("Edx", W.DWORD),
                ("Ecx", W.DWORD), ("Eax", W.DWORD), ("Ebp", W.DWORD), ("Eip", W.DWORD),
                ("SegCs", W.DWORD), ("EFlags", W.DWORD), ("Esp", W.DWORD), ("SegSs", W.DWORD),
                ("ExtendedRegisters", C.c_byte * 512)]

def find_game():
    """The running MOD game, by name.

    ⚠ Only zigexe.EXES is searched. The root's AoW.exe / AoWCompat.exe are VANILLA, and a hang
    captured out of one of those would name stock functions while claiming to describe Ziggurat --
    a wrong answer with no error. Use --pid to point this at anything else on purpose."""
    import subprocess
    for name in zigexe.EXES:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + name, "/NH", "/FO", "CSV"],
                             capture_output=True, text=True).stdout
        if name.lower() in out.lower() and '"' in out:
            parts = [p.strip('"') for p in out.strip().splitlines()[0].split('","')]
            return int(parts[1]), parts[0]
    return None, None

def modules(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    mods = []
    if not snap or snap == INVALID_HANDLE:
        return mods
    me = MODULEENTRY32(); me.dwSize = C.sizeof(MODULEENTRY32)
    if k32.Module32First(snap, C.byref(me)):
        while True:
            base = C.cast(me.modBaseAddr, C.c_void_p).value or 0
            mods.append((me.szModule.decode(errors="ignore"), base, me.modBaseSize))
            if not k32.Module32Next(snap, C.byref(me)):
                break
    k32.CloseHandle(snap)
    return sorted(mods, key=lambda m: m[1])

def threads(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    out = []
    if not snap or snap == INVALID_HANDLE:
        return out
    te = THREADENTRY32(); te.dwSize = C.sizeof(THREADENTRY32)
    if k32.Thread32First(snap, C.byref(te)):
        while True:
            if te.th32OwnerProcessID == pid:
                out.append(te.th32ThreadID)
            if not k32.Thread32Next(snap, C.byref(te)):
                break
    k32.CloseHandle(snap)
    return out

def is_wow64(pid):
    """True iff `pid` is a 32-bit process on 64-bit Windows -- the only case Wow64GetThreadContext
    serves. Every AoW1 binary is i386 (machine 0x014C) so they always qualify; a 64-bit target
    returns ERROR_INVALID_PARAMETER (87) from Wow64GetThreadContext, which is silent unless checked."""
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        return None
    try:
        b = W.BOOL()
        if not k32.IsWow64Process(h, C.byref(b)):
            return None
        return bool(b.value)
    finally:
        k32.CloseHandle(h)

def ctx_of(tid):
    h = k32.OpenThread(THREAD_GET_CONTEXT | THREAD_SUSPEND_RESUME, False, tid)
    if not h:
        return None
    try:
        if k32.Wow64SuspendThread(h) == 0xFFFFFFFF:
            return None
        try:
            c = WOW64_CONTEXT(); c.ContextFlags = WOW64_CONTEXT_FULL
            if not k32.Wow64GetThreadContext(h, C.byref(c)):
                return None
            return c
        finally:
            k32.ResumeThread(h)
    finally:
        k32.CloseHandle(h)

def resolve(addr, mods):
    for name, base, size in mods:
        if base <= addr < base + size:
            rva = addr - base
            s = "%s+0x%X" % (name, rva)
            if name.lower() == "aowepack.dpl":
                s += "  (link 0x%08X)" % (AOWEPACK_LINK_BASE + rva)
                if 0x5580C000 <= AOWEPACK_LINK_BASE + rva < 0x55812000:
                    s += "  <<< MOD CAVE"
            return s
    return "0x%08X (unknown)" % addr

def walk(hproc, ctx, mods, depth=32):
    frames = [("EIP", ctx.Eip)]
    ebp, seen = ctx.Ebp, set()
    buf = (C.c_byte * 8)(); n = C.c_size_t()
    for _ in range(depth):
        if not ebp or ebp in seen or ebp & 3:
            break
        seen.add(ebp)
        if not k32.ReadProcessMemory(hproc, C.c_void_p(ebp), buf, 8, C.byref(n)):
            break
        raw = bytes(bytearray(buf))
        nxt = int.from_bytes(raw[0:4], "little")
        ret = int.from_bytes(raw[4:8], "little")
        if not ret:
            break
        frames.append(("ret", ret))
        ebp = nxt
    return frames

def snapshot(pid, label=""):
    mods = modules(pid)
    hproc = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    lines = ["=== AoW hang stack %s ===" % label,
             "pid %d" % pid, ""]
    for name, base, size in mods:
        if name.lower().endswith((".exe", ".dpl")):
            lines.append("  module %-20s base 0x%08X size 0x%X" % (name, base, size))
    lines.append("")
    for tid in threads(pid):
        c = ctx_of(tid)
        if not c:
            continue
        lines.append("thread %d   EIP %s" % (tid, resolve(c.Eip, mods)))
        lines.append("           EAX %08X EBX %08X ECX %08X EDX %08X ESI %08X EDI %08X EBP %08X ESP %08X"
                     % (c.Eax, c.Ebx, c.Ecx, c.Edx, c.Esi, c.Edi, c.Ebp, c.Esp))
        for kind, a in walk(hproc, c, mods)[1:]:
            lines.append("             %-4s %s" % (kind, resolve(a, mods)))
        lines.append("")
    if hproc:
        k32.CloseHandle(hproc)
    return "\n".join(lines)

def main():
    watch = "--watch" in sys.argv
    stall_n = 6
    if "--stall" in sys.argv:
        stall_n = int(sys.argv[sys.argv.index("--stall") + 1])

    # A stale file from a previous run must never be mistaken for this run's capture.
    if os.path.exists(OUT):
        os.remove(OUT)
        print("(removed stale %s)" % os.path.basename(OUT))

    if "--pid" in sys.argv:                     # --pid N: target any 32-bit process (self-test)
        pid = int(sys.argv[sys.argv.index("--pid") + 1]); name = "pid %d" % pid
    else:
        pid, name = find_game()
        if not pid and watch:
            # Wait rather than exit: the natural order is to start the watcher, THEN launch the game.
            print("waiting for %s to start ... (Ctrl-C to quit)" % " / ".join(zigexe.EXES))
            while not pid:
                time.sleep(2.0)
                pid, name = find_game()
            print("game detected.")
    if not pid:
        sys.exit("No %s running. Start the game first, or use --watch to wait for it."
                 % " / ".join(zigexe.EXES))
    print("watching %s (pid %d)" % (name, pid))
    w = is_wow64(pid)
    if w is False:
        sys.exit("[x] pid %d is a 64-BIT process. This tool reads 32-bit (WOW64) contexts, which is\n"
                 "    what %s are (PE machine 0x014C). Point it at the game."
                 % (pid, "/".join(zigexe.EXES)))
    if w is None:
        print("[!] could not determine bitness (need PROCESS_QUERY_INFORMATION); continuing anyway")

    if not watch:
        txt = snapshot(pid, "one-shot")
        open(OUT, "w").write(txt); print(txt); print("\nwritten to", OUT)
        return

    print("Play until it freezes. A stall of %d consecutive identical samples writes %s"
          % (stall_n, OUT))
    hist, ticks = {}, 0          # tid -> ((Eip, Esp), consecutive-identical-count)
    while True:
        tids = threads(pid)
        if not tids:
            # The game exited (or you killed a frozen one before the stall threshold). Go back to
            # waiting so the watcher survives a restart instead of dying silently.
            print("\n[!] game process gone with no stall captured -- waiting for a restart. "
                  "If it WAS frozen, kill it more slowly next time or use a lower --stall.")
            pid = None
            while not pid:
                time.sleep(2.0)
                pid, _n = find_game()
            print("game detected again; watching.")
            hist = {}
            continue
        # PER-THREAD stall detection. The first version required EVERY thread to hold the same
        # (Eip, Esp) simultaneously -- which never happens here, because the symptom is "frozen but
        # SOUND STILL RUNNING": the audio thread keeps moving and reset the counter every sample.
        # Track each thread separately and fire as soon as a GAME-CODE thread stops moving.
        mods = modules(pid)
        ticks += 1
        stalled = None
        for tid in tids:
            c = ctx_of(tid)
            if not c:
                continue
            sig = (c.Eip, c.Esp)
            prev = hist.get(tid)
            cnt = prev[1] + 1 if prev and prev[0] == sig else 0
            hist[tid] = (sig, cnt)
            # Only game code counts. Threads parked in ntdll/kernel32 waits are legitimately static
            # forever and would false-trigger constantly.
            in_game = any(nm.lower().endswith((".exe", ".dpl")) and b <= c.Eip < b + s
                          for nm, b, s in mods)
            if cnt >= stall_n and in_game and stalled is None:
                stalled = (tid, c.Eip, cnt)
        if ticks % 30 == 0:
            hot = max((v[1] for v in hist.values()), default=0)
            print("  ... watching (%d samples, %d threads, longest stall %d/%d)"
                  % (ticks, len(tids), hot, stall_n), flush=True)
        if stalled:
            tid, eip, cnt = stalled
            txt = snapshot(pid, "STALL: thread %d static %d samples at %s"
                                % (tid, cnt, resolve(eip, mods)))
            open(OUT, "w").write(txt)
            print("\n*** STALL -- stack written to %s ***\n" % OUT, flush=True)
            print(txt)
            return
        time.sleep(1.0)

if __name__ == "__main__":
    main()
