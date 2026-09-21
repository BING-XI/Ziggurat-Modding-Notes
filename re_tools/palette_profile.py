"""Profile the UI thread while tightly cycling palette tabs, to characterize per-tab paint.

Background thread cycles the given TPageControl's tabs; main thread samples EIP.
Reports EngineP/ILPACK/GDI/ntdll breakdown + top raw offsets (to spot disk I/O vs GDI).
No cursor movement/clicks. Usage: palette_profile.py <main-hwnd> <pagectrl-hwnd> <seconds> <switch_ms>
"""
import sys, os, time, ctypes, bisect, threading
from ctypes import wintypes
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowsyms import get_symbols, GAME

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)

MAIN = int(sys.argv[1], 16); PAGECTRL = int(sys.argv[2], 16)
SECONDS = float(sys.argv[3]) if len(sys.argv) > 3 else 12
SWITCH_MS = int(sys.argv[4]) if len(sys.argv) > 4 else 180
VK_MENU = 0x12; TCM_GETITEMCOUNT = 0x1304; TCM_SETCURFOCUS = 0x1330

TH32CS_SNAPTHREAD = 0x4; PROC_RIGHTS = 0x0410; THREAD_RIGHTS = 0x0002|0x0008|0x0040
LIST_MODULES_ALL = 0x03; WOW64_CONTEXT_CONTROL = 0x10001

class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize",wintypes.DWORD),("cntUsage",wintypes.DWORD),("th32ThreadID",wintypes.DWORD),
        ("th32OwnerProcessID",wintypes.DWORD),("tpBasePri",ctypes.c_long),("tpDeltaPri",ctypes.c_long),("dwFlags",wintypes.DWORD)]
class MODULEINFO(ctypes.Structure):
    _fields_ = [("lpBaseOfDll",ctypes.c_void_p),("SizeOfImage",wintypes.DWORD),("EntryPoint",ctypes.c_void_p)]
class WOW64_CONTEXT(ctypes.Structure):
    _fields_ = [("ContextFlags",wintypes.DWORD)]+[(n,wintypes.DWORD) for n in ("Dr0","Dr1","Dr2","Dr3","Dr6","Dr7")]+\
        [("FloatSave",ctypes.c_byte*112)]+[(n,wintypes.DWORD) for n in ("SegGs","SegFs","SegEs","SegDs","Edi","Esi",
        "Ebx","Edx","Ecx","Eax","Ebp","Eip","SegCs","EFlags","Esp","SegSs")]+[("Ext",ctypes.c_byte*512)]
psapi.EnumProcessModulesEx.argtypes=[wintypes.HANDLE,ctypes.POINTER(ctypes.c_void_p),wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),wintypes.DWORD]
psapi.GetModuleInformation.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.POINTER(MODULEINFO),wintypes.DWORD]
psapi.GetModuleFileNameExW.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.c_wchar_p,wintypes.DWORD]

def pid_of(hwnd):
    p=wintypes.DWORD(); u32.GetWindowThreadProcessId(hwnd,ctypes.byref(p)); return p.value
def threads(pid):
    snap=k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0); te=THREADENTRY32(); te.dwSize=ctypes.sizeof(te); out=[]
    if k32.Thread32First(snap,ctypes.byref(te)):
        while True:
            if te.th32OwnerProcessID==pid: out.append(te.th32ThreadID)
            if not k32.Thread32Next(snap,ctypes.byref(te)): break
    k32.CloseHandle(snap); return out
def modmap(hproc):
    arr=(ctypes.c_void_p*512)(); need=wintypes.DWORD()
    psapi.EnumProcessModulesEx(hproc,arr,ctypes.sizeof(arr),ctypes.byref(need),LIST_MODULES_ALL); mods=[]
    for i in range(min(512,need.value//ctypes.sizeof(ctypes.c_void_p))):
        mi=MODULEINFO(); psapi.GetModuleInformation(hproc,arr[i],ctypes.byref(mi),ctypes.sizeof(mi))
        b=ctypes.create_unicode_buffer(520); psapi.GetModuleFileNameExW(hproc,arr[i],b,520)
        mods.append((mi.lpBaseOfDll or 0,mi.SizeOfImage,os.path.basename(b.value)))
    mods.sort(); return mods
symcache={}
def syms(m):
    k=m.lower()
    if k in symcache: return symcache[k]
    e=None
    if os.path.exists(os.path.join(GAME,m)) and k.endswith((".dpl",".exe")):
        try: pe,base,s,_=get_symbols(m); e=(base,sorted(s.items()))
        except Exception: e=None
    symcache[k]=e; return e
def locate(mods,eip):
    for base,size,name in mods:
        if base<=eip<base+size:
            off=eip-base; e=syms(name)
            if e:
                pref,sl=e; va=pref+off; keys=[x[0] for x in sl]; i=bisect.bisect_right(keys,va)-1
                if i>=0 and va-sl[i][0]<0x4000: return f"{name}!{sl[i][1]}", f"{name}+{off:#x}"
            return f"{name}+{off:#x}", f"{name}+{off:#x}"
    return "?","?"

stop=False
def cycler():
    res=ctypes.c_size_t()
    u32.SendMessageTimeoutW(PAGECTRL,TCM_GETITEMCOUNT,0,0,0x2,2000,ctypes.byref(res))
    n=res.value or 8; i=0
    while not stop:
        u32.SendMessageTimeoutW(PAGECTRL,TCM_SETCURFOCUS,i%n,0,0x2,2000,ctypes.byref(res))
        i+=1; time.sleep(SWITCH_MS/1000)

prev=u32.GetForegroundWindow()
u32.keybd_event(VK_MENU,0,0,0); u32.SetForegroundWindow(MAIN); u32.keybd_event(VK_MENU,0,2,0); time.sleep(0.9)
print("active:",u32.GetForegroundWindow()==MAIN)
hproc=k32.OpenProcess(PROC_RIGHTS,False,pid_of(MAIN)); mods=modmap(hproc)
th=threading.Thread(target=cycler,daemon=True); th.start()

hs=[h for h in (k32.OpenThread(THREAD_RIGHTS,False,t) for t in threads(pid_of(MAIN))) if h]
ctx=WOW64_CONTEXT(); samples=[]; t_end=time.perf_counter()+SECONDS; interval=1/300
while time.perf_counter()<t_end:
    t0=time.perf_counter()
    for h in hs:
        if k32.SuspendThread(h)==0xFFFFFFFF: continue
        try:
            ctx.ContextFlags=WOW64_CONTEXT_CONTROL
            if k32.Wow64GetThreadContext(h,ctypes.byref(ctx)): samples.append(ctx.Eip)
        finally: k32.ResumeThread(h)
    dt=time.perf_counter()-t0
    if dt<interval: time.sleep(interval-dt)
stop=True; time.sleep(SWITCH_MS/1000+0.05)
for h in hs: k32.CloseHandle(h)
k32.CloseHandle(hproc)

n=len(samples) or 1
modh=Counter(); symh=Counter(); rawh=Counter()
for eip in samples:
    s,raw=locate(mods,eip); modh[raw.split("+")[0]]+=1; symh[s]+=1; rawh[raw]+=1
print(f"\n{len(samples)} samples cycling palette tabs @ {SWITCH_MS}ms")
print("-- by module --")
for m,c in modh.most_common(10): print(f"  {c:6d} {100*c/n:5.1f}%  {m}")
print("-- app-code symbols (EngineP/ILPACK/GFXE/GDI) --")
for s,c in symh.most_common(60):
    if any(k in s for k in ("EngineP","ILPACK","GFXE","gdi32","win32u","EResGrid","ImageLib","TEResource","DrawCell","Blt","Show","DIB","Remap","Palette")):
        print(f"  {c:6d} {100*c/n:5.1f}%  {s}")
print("-- top raw offsets --")
for r,c in rawh.most_common(16): print(f"  {c:6d} {100*c/n:5.1f}%  {r}")

if prev and prev!=MAIN:
    u32.keybd_event(VK_MENU,0,0,0); u32.SetForegroundWindow(prev); u32.keybd_event(VK_MENU,0,2,0)
print("restored")
