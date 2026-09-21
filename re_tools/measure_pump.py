"""Measure UI-thread pump latency of the editor WITHOUT any cursor movement or clicks.

Activates the editor via SetForegroundWindow (Alt trick), fires WM_NULL round-trips
(gated by the DCPACK frame loop), reports min/median/max. Optionally toggles the
Scanner floater (posted WM_COMMAND 77) to compare scanner-open vs scanner-closed.
Restores the previous foreground window at the end.

Usage: measure_pump.py <main-hwnd-hex> <hsmedit-hwnd-hex>
"""
import sys, time, ctypes, statistics
from ctypes import wintypes
u32 = ctypes.WinDLL("user32", use_last_error=True)
VK_MENU = 0x12; WM_COMMAND = 0x111; SCANNER_ID = 77

MAIN = int(sys.argv[1], 16)
HSM = int(sys.argv[2], 16)

def activate(hwnd):
    u32.keybd_event(VK_MENU, 0, 0, 0)
    u32.SetForegroundWindow(hwnd)
    u32.keybd_event(VK_MENU, 0, 2, 0)
    time.sleep(0.8)
    return u32.GetForegroundWindow()

def probe(hwnd, timeout_ms=5000):
    t0 = time.perf_counter(); res = ctypes.c_size_t()
    ok = u32.SendMessageTimeoutW(hwnd, 0, 0, 0, 0x2, timeout_ms, ctypes.byref(res))
    return (time.perf_counter() - t0) * 1000, ok != 0

def sample(tag, n=25):
    vals = []
    for _ in range(n):
        ms, ok = probe(HSM)
        if ok:
            vals.append(ms)
        time.sleep(0.01)
    if not vals:
        print(f"[{tag}] no successful probes (app inactive?)")
        return
    vals.sort()
    print(f"[{tag}] n={len(vals)} min={vals[0]:.1f} median={statistics.median(vals):.1f} "
          f"max={vals[-1]:.1f} ms")

prev_fg = u32.GetForegroundWindow()
fg = activate(MAIN)
print(f"editor foreground: {'YES' if fg == MAIN else 'NO (got %#x)' % fg}")

sample("scanner ON")
# toggle scanner off
u32.PostMessageW(MAIN, WM_COMMAND, SCANNER_ID, 0)
time.sleep(1.0)
sample("scanner OFF")
# scanner back on
u32.PostMessageW(MAIN, WM_COMMAND, SCANNER_ID, 0)
time.sleep(0.5)

if prev_fg and prev_fg != MAIN:
    u32.keybd_event(VK_MENU, 0, 0, 0)
    u32.SetForegroundWindow(prev_fg)
    u32.keybd_event(VK_MENU, 0, 2, 0)
print("restored")
