"""Sampling profiler for AoWzEd.exe (or any AoW process) — read-only.

Suspends each thread briefly at ~HZ, reads EIP (Wow64 context from 64-bit Python),
maps it to module + nearest known symbol (package exports / exe method tables).

Usage: sampler.py [--exe AoWzEd.exe] [--seconds 10] [--hz 150] [--out samples.txt]

⚠ --exe names a RUNNING process. AoWDevEd.exe is the editor PATCH SOURCE and is not launched --
AoWzEd.exe is the one build_zigeditor.py produces and the owner runs.
"""
import sys, os, time, struct, ctypes, argparse, bisect
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowsyms import get_symbols, GAME
from zignames import zigexe

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

TH32CS_SNAPPROCESS = 0x2
TH32CS_SNAPTHREAD = 0x4
PROCESS_ALL_READ = 0x0410  # QUERY_INFORMATION | VM_READ
THREAD_RIGHTS = 0x0002 | 0x0008 | 0x0040  # SUSPEND_RESUME | GET_CONTEXT | QUERY_INFORMATION
LIST_MODULES_32BIT = 0x01
LIST_MODULES_ALL = 0x03

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]

class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD), ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", ctypes.c_long), ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", wintypes.DWORD)]

class MODULEINFO(ctypes.Structure):
    _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wintypes.DWORD),
                ("EntryPoint", ctypes.c_void_p)]

psapi.GetModuleInformation.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                       ctypes.POINTER(MODULEINFO), wintypes.DWORD]
psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                       ctypes.c_wchar_p, wintypes.DWORD]
psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p),
                                       wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]

WOW64_CONTEXT_CONTROL = 0x10001
class WOW64_CONTEXT(ctypes.Structure):
    _fields_ = [("ContextFlags", wintypes.DWORD), ("Dr0", wintypes.DWORD), ("Dr1", wintypes.DWORD),
                ("Dr2", wintypes.DWORD), ("Dr3", wintypes.DWORD), ("Dr6", wintypes.DWORD),
                ("Dr7", wintypes.DWORD), ("FloatSave", ctypes.c_byte * 112),
                ("SegGs", wintypes.DWORD), ("SegFs", wintypes.DWORD), ("SegEs", wintypes.DWORD),
                ("SegDs", wintypes.DWORD), ("Edi", wintypes.DWORD), ("Esi", wintypes.DWORD),
                ("Ebx", wintypes.DWORD), ("Edx", wintypes.DWORD), ("Ecx", wintypes.DWORD),
                ("Eax", wintypes.DWORD), ("Ebp", wintypes.DWORD), ("Eip", wintypes.DWORD),
                ("SegCs", wintypes.DWORD), ("EFlags", wintypes.DWORD), ("Esp", wintypes.DWORD),
                ("SegSs", wintypes.DWORD), ("ExtendedRegisters", ctypes.c_byte * 512)]

def find_pid(exe_name):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PROCESSENTRY32(); pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
    pid = None
    if k32.Process32First(snap, ctypes.byref(pe)):
        while True:
            if pe.szExeFile.decode(errors="replace").lower() == exe_name.lower():
                pid = pe.th32ProcessID; break
            if not k32.Process32Next(snap, ctypes.byref(pe)):
                break
    k32.CloseHandle(snap)
    return pid

def list_threads(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32(); te.dwSize = ctypes.sizeof(THREADENTRY32)
    tids = []
    if k32.Thread32First(snap, ctypes.byref(te)):
        while True:
            if te.th32OwnerProcessID == pid:
                tids.append(te.th32ThreadID)
            if not k32.Thread32Next(snap, ctypes.byref(te)):
                break
    k32.CloseHandle(snap)
    return tids

def module_map(hproc):
    """[(base, size, name)] for 32-bit modules of the process"""
    n = 512
    arr = (ctypes.c_void_p * n)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcessModulesEx(hproc, arr, ctypes.sizeof(arr), ctypes.byref(needed), LIST_MODULES_ALL):
        raise ctypes.WinError(ctypes.get_last_error())
    count = min(n, needed.value // ctypes.sizeof(ctypes.c_void_p))
    mods = []
    for i in range(count):
        mi = MODULEINFO()
        psapi.GetModuleInformation(hproc, arr[i], ctypes.byref(mi), ctypes.sizeof(mi))
        buf = ctypes.create_unicode_buffer(520)
        psapi.GetModuleFileNameExW(hproc, arr[i], buf, 520)
        mods.append((mi.lpBaseOfDll or 0, mi.SizeOfImage, os.path.basename(buf.value)))
    mods.sort()
    return mods

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=zigexe.LIVE_EDITOR)
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--hz", type=float, default=150)
    ap.add_argument("--out", default=None)
    ap.add_argument("--tid", type=int, default=None,
                    help="sample ONLY this thread id (see --window)")
    ap.add_argument("--window", default=None,
                    help="hex HWND: sample only the thread that owns this window. Without it the "
                         "histogram is swamped by idle worker threads sitting in NtWaitFor*.")
    args = ap.parse_args()

    pid = find_pid(args.exe)
    if not pid:
        print(f"process {args.exe} not found"); sys.exit(1)
    hproc = k32.OpenProcess(PROCESS_ALL_READ, False, pid)
    if not hproc:
        raise ctypes.WinError(ctypes.get_last_error())
    mods = module_map(hproc)
    print(f"pid={pid}, {len(mods)} modules")

    # symbol tables for AoW modules present on disk (keyed by lowercase name)
    symcache = {}
    def load_syms(modname):
        key = modname.lower()
        if key in symcache:
            return symcache[key]
        path = os.path.join(GAME, modname)
        entry = None
        if os.path.exists(path) and key.endswith((".dpl", ".exe")):
            try:
                pe, base, syms, _ = get_symbols(modname)
                entry = (base, sorted(syms.items()))
            except Exception:
                entry = None
        symcache[key] = entry
        return entry

    tids = list_threads(pid)
    if args.window:
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        owner = u32.GetWindowThreadProcessId(ctypes.c_void_p(int(args.window, 16)), None)
        if owner:
            args.tid = owner
    if args.tid:
        tids = [t for t in tids if t == args.tid]
        print(f"restricting to thread {args.tid}")
    handles = {}
    for tid in tids:
        h = k32.OpenThread(THREAD_RIGHTS, False, tid)
        if h:
            handles[tid] = h
    print(f"sampling {len(handles)} threads at {args.hz}Hz for {args.seconds}s...")

    interval = 1.0 / args.hz
    samples = []  # (tid, eip)
    t_end = time.perf_counter() + args.seconds
    ctx = WOW64_CONTEXT()
    while time.perf_counter() < t_end:
        t0 = time.perf_counter()
        for tid, h in handles.items():
            if k32.SuspendThread(h) == 0xFFFFFFFF:
                continue
            try:
                ctx.ContextFlags = WOW64_CONTEXT_CONTROL
                if k32.Wow64GetThreadContext(h, ctypes.byref(ctx)):
                    samples.append((tid, ctx.Eip))
            finally:
                k32.ResumeThread(h)
        dt = time.perf_counter() - t0
        if dt < interval:
            time.sleep(interval - dt)

    for h in handles.values():
        k32.CloseHandle(h)
    k32.CloseHandle(hproc)

    # ---- binning ----
    def locate(eip):
        lo, hi = 0, len(mods)
        modname, off = None, None
        for base, size, name in mods:
            if base <= eip < base + size:
                modname, off = name, eip - base
                break
        if modname is None:
            return ("?unknown", None, None)
        entry = load_syms(modname)
        if entry:
            pref_base, symlist = entry
            va = pref_base + off
            keys = [s[0] for s in symlist]
            i = bisect.bisect_right(keys, va) - 1
            if i >= 0 and va - symlist[i][0] < 0x4000:
                return (modname, symlist[i][1], va - symlist[i][0])
        return (modname, None, off)

    from collections import Counter, defaultdict
    per_thread = Counter(t for t, e in samples)
    print(f"\n{len(samples)} samples. per-thread: " +
          ", ".join(f"tid{t}:{c}" for t, c in per_thread.most_common(8)))

    mod_hist = Counter()
    sym_hist = Counter()
    for tid, eip in samples:
        modname, sym, off = locate(eip)
        mod_hist[modname] += 1
        if sym:
            sym_hist[f"{modname}!{sym}"] += 1
        else:
            sym_hist[f"{modname}+{off:#x}" if off is not None else modname] += 1

    lines = []
    lines.append("== module histogram ==")
    for m, c in mod_hist.most_common():
        lines.append(f"{c:6d}  {100*c/len(samples):5.1f}%  {m}")
    lines.append("\n== symbol histogram (top 60) ==")
    for s, c in sym_hist.most_common(60):
        lines.append(f"{c:6d}  {100*c/len(samples):5.1f}%  {s}")
    text = "\n".join(lines)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="ascii", errors="replace") as f:
            f.write(text + "\n\n== raw ==\n")
            for tid, eip in samples:
                f.write(f"{tid} {eip:#x}\n")

if __name__ == "__main__":     # guard: stack_prof.py imports this module for its helpers
    main()
