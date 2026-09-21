"""Time a synchronous full repaint of a window (cross-process). No cursor/clicks.

RedrawWindow(RDW_INVALIDATE|RDW_ERASE|RDW_UPDATENOW) forces WM_PAINT synchronously;
timing it measures the actual paint cost. Usage: paint_timer.py <main-hwnd> <target-hwnd> [n]
"""
import sys, time, ctypes
from ctypes import wintypes
u32 = ctypes.WinDLL("user32", use_last_error=True)
VK_MENU = 0x12
RDW_INVALIDATE=0x1; RDW_ERASE=0x4; RDW_UPDATENOW=0x100; RDW_ALLCHILDREN=0x80

MAIN=int(sys.argv[1],16); TARGET=int(sys.argv[2],16); N=int(sys.argv[3]) if len(sys.argv)>3 else 10

prev=u32.GetForegroundWindow()
u32.keybd_event(VK_MENU,0,0,0); u32.SetForegroundWindow(MAIN); u32.keybd_event(VK_MENU,0,2,0); time.sleep(0.8)

times=[]
for i in range(N):
    t0=time.perf_counter()
    u32.RedrawWindow(TARGET, None, None, RDW_INVALIDATE|RDW_ERASE|RDW_UPDATENOW|RDW_ALLCHILDREN)
    dt=(time.perf_counter()-t0)*1000
    times.append(dt); time.sleep(0.25)
times.sort()
print(f"full-repaint of {TARGET:#x}: n={N} min={times[0]:.1f} median={times[len(times)//2]:.1f} max={times[-1]:.1f} ms")

if prev and prev!=MAIN:
    u32.keybd_event(VK_MENU,0,0,0); u32.SetForegroundWindow(prev); u32.keybd_event(VK_MENU,0,2,0)
