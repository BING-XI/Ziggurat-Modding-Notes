"""Faithful per-tab latency: (A) raw TCM_SETCURFOCUS sync cost, (B) natural time-to-idle
after posting the switch (like a click) with NO forced repaint. No cursor/clicks.

Usage: settle_tab.py <main-hwnd> <pagectrl-hwnd> [probe-hwnd] [label]
"""
import sys, time, ctypes
from ctypes import wintypes
u32 = ctypes.WinDLL("user32", use_last_error=True)
VK_MENU=0x12; TCM_GETITEMCOUNT=0x1304; TCM_SETCURFOCUS=0x1330; WM_NULL=0

MAIN=int(sys.argv[1],16); PAGE=int(sys.argv[2],16)
PROBE=int(sys.argv[3],16) if len(sys.argv)>3 else MAIN
LABEL=sys.argv[4] if len(sys.argv)>4 else ""

def sm(hwnd,msg,wp=0,lp=0,to=5000):
    r=ctypes.c_size_t(); t0=time.perf_counter()
    u32.SendMessageTimeoutW(hwnd,msg,wp,lp,0x2,to,ctypes.byref(r))
    return r.value,(time.perf_counter()-t0)*1000

def probe():
    _,ms=sm(PROBE,WM_NULL); return ms

prev=u32.GetForegroundWindow()
u32.keybd_event(VK_MENU,0,0,0); u32.SetForegroundWindow(MAIN); u32.keybd_event(VK_MENU,0,2,0); time.sleep(0.8)
n,_=sm(PAGE,TCM_GETITEMCOUNT); n=n or 8
base=sorted(probe() for _ in range(8))[4]
print(f"{LABEL} {PAGE:#x}: {n} tabs, baseline pump {base:.1f}ms")
for i in range(n):
    # A: raw synchronous switch cost
    _,tsync=sm(PAGE,TCM_SETCURFOCUS,i)
    # B: natural settle - post another switch to a *different* tab like a click, time to idle
    j=(i+1)%n
    u32.PostMessageW(PAGE,TCM_SETCURFOCUS,j,0)
    t0=time.perf_counter(); idle=0
    while time.perf_counter()-t0 < 3.0:
        if probe() < base*2.5: idle+=1
        else: idle=0
        if idle>=2: break
    settle=(time.perf_counter()-t0)*1000
    print(f"  tab {i}: sync-switch {tsync:6.1f}ms | post+settle {settle:6.1f}ms")
    time.sleep(0.3)
sm(PAGE,TCM_SETCURFOCUS,0)
if prev and prev!=MAIN:
    u32.keybd_event(VK_MENU,0,0,0); u32.SetForegroundWindow(prev); u32.keybd_event(VK_MENU,0,2,0)
