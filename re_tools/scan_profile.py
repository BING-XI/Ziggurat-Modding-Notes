"""Self-contained: activate editor, profile idle CPU scanner-ON vs scanner-OFF.

No cursor movement, no clicks. Activation + sampling in one process (no focus-steal).
Usage: scan_profile.py <main-hwnd-hex> <seconds>
"""
import sys, os, time, ctypes, bisect
from ctypes import wintypes
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowsyms import get_symbols, GAME

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)

MAIN = int(sys.argv[1], 16)
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 10
VK_MENU = 0x12; WM_COMMAND = 0x111; SCANNER_ID = 77

TH32CS_SNAPPROCESS = 0x2; TH32CS_SNAPTHREAD = 0x4
PROC_RIGHTS = 0x0410; THREAD_RIGHTS = 0x0002 | 0x0008 | 0x0040
LIST_MODULES_ALL = 0x03; WOW64_CONTEXT_CONTROL = 0x10001

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]
class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD), ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", ctypes.c_long), ("tpDeltaPri", ctypes.c_long), ("dwFlags", wintypes.DWORD)]
class MODULEINFO(ctypes.Structure):
    _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wintypes.DWORD), ("EntryPoint", ctypes.c_void_p)]
class WOW64_CONTEXT(ctypes.Structure):
    _fields_ = [("ContextFlags", wintypes.DWORD)] + [(n, wintypes.DWORD) for n in
        ("Dr0","Dr1","Dr2","Dr3","Dr6","Dr7")] + [("FloatSave", ctypes.c_byte*112)] + \
        [(n, wintypes.DWORD) for n in ("SegGs","SegFs","SegEs","SegDs","Edi","Esi","Ebx","Edx",
        "Ecx","Eax","Ebp","Eip","SegCs","EFlags","Esp","SegSs")] + [("Ext", ctypes.c_byte*512)]
psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
psapi.GetModuleInformation.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(MODULEINFO), wintypes.DWORD]
psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_wchar_p, wintypes.DWORD]

def find_pid_of_hwnd(hwnd):
    pid = wintypes.DWORD(); u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)); return pid.value

def list_threads(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32(); te.dwSize = ctypes.sizeof(te); out = []
    if k32.Thread32First(snap, ctypes.byref(te)):
        while True:
            if te.th32OwnerProcessID == pid: out.append(te.th32ThreadID)
            if not k32.Thread32Next(snap, ctypes.byref(te)): break
    k32.CloseHandle(snap); return out

def module_map(hproc):
    arr = (ctypes.c_void_p * 512)(); needed = wintypes.DWORD()
    psapi.EnumProcessModulesEx(hproc, arr, ctypes.sizeof(arr), ctypes.byref(needed), LIST_MODULES_ALL)
    mods = []
    for i in range(min(512, needed.value // ctypes.sizeof(ctypes.c_void_p))):
        mi = MODULEINFO(); psapi.GetModuleInformation(hproc, arr[i], ctypes.byref(mi), ctypes.sizeof(mi))
        buf = ctypes.create_unicode_buffer(520); psapi.GetModuleFileNameExW(hproc, arr[i], buf, 520)
        mods.append((mi.lpBaseOfDll or 0, mi.SizeOfImage, os.path.basename(buf.value)))
    mods.sort(); return mods

symcache = {}
def load_syms(modname):
    key = modname.lower()
    if key in symcache: return symcache[key]
    entry = None
    if os.path.exists(os.path.join(GAME, modname)) and key.endswith((".dpl", ".exe")):
        try:
            pe, base, syms, _ = get_symbols(modname); entry = (base, sorted(syms.items()))
        except Exception: entry = None
    symcache[key] = entry; return entry

def profile(hproc, mods, seconds, hz=200):
    tids = list_threads(find_pid_of_hwnd(MAIN))
    handles = [h for h in (k32.OpenThread(THREAD_RIGHTS, False, t) for t in tids) if h]
    ctx = WOW64_CONTEXT(); samples = []
    interval = 1.0 / hz; t_end = time.perf_counter() + seconds
    while time.perf_counter() < t_end:
        t0 = time.perf_counter()
        for h in handles:
            if k32.SuspendThread(h) == 0xFFFFFFFF: continue
            try:
                ctx.ContextFlags = WOW64_CONTEXT_CONTROL
                if k32.Wow64GetThreadContext(h, ctypes.byref(ctx)): samples.append(ctx.Eip)
            finally: k32.ResumeThread(h)
        dt = time.perf_counter() - t0
        if dt < interval: time.sleep(interval - dt)
    for h in handles: k32.CloseHandle(h)
    return samples

def locate(mods, eip):
    for base, size, name in mods:
        if base <= eip < base + size:
            off = eip - base; entry = load_syms(name)
            if entry:
                pref, symlist = entry; va = pref + off; keys = [s[0] for s in symlist]
                i = bisect.bisect_right(keys, va) - 1
                if i >= 0 and va - symlist[i][0] < 0x4000: return f"{name}!{symlist[i][1]}"
            return f"{name}+{off:#x}"
    return "?"

def report(tag, samples, mods):
    n = len(samples) or 1
    modh = Counter(); symh = Counter()
    for eip in samples:
        loc = locate(mods, eip); modh[loc.split("!")[0].split("+")[0]] += 1; symh[loc] += 1
    print(f"\n===== {tag}: {len(samples)} samples =====")
    print("-- by module --")
    for m, c in modh.most_common(8): print(f"  {c:6d} {100*c/n:5.1f}%  {m}")
    print("-- scanner/draw-relevant symbols --")
    for s, c in symh.most_common(40):
        if any(k in s for k in ("Scanner","AoWTools","GFXE","ILPACK","DrawMap","DrawObj","Blt","HSEngine")):
            print(f"  {c:6d} {100*c/n:5.1f}%  {s}")

# ---- run ----
prev_fg = u32.GetForegroundWindow()
u32.keybd_event(VK_MENU, 0, 0, 0); u32.SetForegroundWindow(MAIN); u32.keybd_event(VK_MENU, 0, 2, 0)
time.sleep(0.9)
print("editor active:", u32.GetForegroundWindow() == MAIN)
hproc = k32.OpenProcess(PROC_RIGHTS, False, find_pid_of_hwnd(MAIN))
mods = module_map(hproc)

s_on = profile(hproc, mods, SECONDS)
u32.PostMessageW(MAIN, WM_COMMAND, SCANNER_ID, 0); time.sleep(1.2)
print("scanner toggled off")
s_off = profile(hproc, mods, SECONDS)
u32.PostMessageW(MAIN, WM_COMMAND, SCANNER_ID, 0); time.sleep(0.5)

k32.CloseHandle(hproc)
report("SCANNER ON (idle)", s_on, mods)
report("SCANNER OFF (idle)", s_off, mods)

if prev_fg and prev_fg != MAIN:
    u32.keybd_event(VK_MENU, 0, 0, 0); u32.SetForegroundWindow(prev_fg); u32.keybd_event(VK_MENU, 0, 2, 0)
print("\nrestored")
