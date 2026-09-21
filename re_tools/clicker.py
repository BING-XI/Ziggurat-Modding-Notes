"""Message-based UI driver (no cursor movement, no focus steal).

Usage:
  clicker.py tabs <pagecontrol-hwnd-hex> <cycles> <delay_ms>   -- cycle all tabs via TCM_SETCURFOCUS
  clicker.py click <hwnd-hex> <client_x> <client_y> [n] [delay_ms]  -- post move+down+up
  clicker.py clickscreen <hwnd-hex> <screen_x> <screen_y> [n] [delay_ms]
  clicker.py key <hwnd-hex> <vk-hex> [n] [delay_ms]            -- post WM_KEYDOWN/UP
"""
import sys, time, ctypes
from ctypes import wintypes
u32 = ctypes.WinDLL("user32", use_last_error=True)

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x200, 0x201, 0x202
WM_KEYDOWN, WM_KEYUP = 0x100, 0x101
TCM_GETITEMCOUNT, TCM_SETCURFOCUS, TCM_GETCURSEL = 0x1304, 0x1330, 0x130B
SMTO_ABORTIFHUNG = 0x2

def send(hwnd, msg, wp=0, lp=0):
    res = ctypes.c_size_t()
    u32.SendMessageTimeoutW(hwnd, msg, wp, lp, SMTO_ABORTIFHUNG, 2000, ctypes.byref(res))
    return res.value

def lparam_xy(x, y):
    return (y << 16) | (x & 0xFFFF)

def post_click(hwnd, x, y):
    lp = lparam_xy(x, y)
    u32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
    time.sleep(0.06)
    u32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lp)   # MK_LBUTTON
    time.sleep(0.03)
    u32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)

cmd = sys.argv[1]
hwnd = int(sys.argv[2], 16)

if cmd == "tabs":
    cycles = int(sys.argv[3]); delay = int(sys.argv[4]) / 1000
    n = send(hwnd, TCM_GETITEMCOUNT)
    print(f"tab count={n}, cycling {cycles}x, delay {delay*1000:.0f}ms")
    t0 = time.perf_counter()
    for c in range(cycles):
        for i in range(n):
            t1 = time.perf_counter()
            send(hwnd, TCM_SETCURFOCUS, i)
            t2 = time.perf_counter()
            print(f"  tab {i}: setcurfocus took {1000*(t2-t1):.0f}ms")
            time.sleep(delay)
    print(f"total {time.perf_counter()-t0:.1f}s")
elif cmd in ("click", "clickscreen"):
    x, y = int(sys.argv[3]), int(sys.argv[4])
    n = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    delay = (int(sys.argv[6]) if len(sys.argv) > 6 else 400) / 1000
    if cmd == "clickscreen":
        pt = wintypes.POINT(x, y)
        u32.ScreenToClient(hwnd, ctypes.byref(pt))
        x, y = pt.x, pt.y
        print(f"client coords: {x},{y}")
    for i in range(n):
        post_click(hwnd, x + (i % 5) * 40, y + (i // 5) * 40)
        time.sleep(delay)
    print("clicks done")
elif cmd == "key":
    vk = int(sys.argv[3], 16)
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    delay = (int(sys.argv[5]) if len(sys.argv) > 5 else 300) / 1000
    for i in range(n):
        u32.PostMessageW(hwnd, WM_KEYDOWN, vk, 1)
        time.sleep(0.03)
        u32.PostMessageW(hwnd, WM_KEYUP, vk, 0xC0000001)
        time.sleep(delay)
    print("keys done")
