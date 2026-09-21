"""topmost.py <hwnd-hex> <on|off|bottom> — raise/lower a window without activating it."""
import sys, ctypes
u32 = ctypes.WinDLL("user32")
HWND_TOPMOST, HWND_NOTOPMOST, HWND_BOTTOM = -1, -2, 1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
hwnd = int(sys.argv[1], 16)
mode = sys.argv[2]
flags = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
if mode == "on":
    u32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
elif mode == "off":
    u32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
elif mode == "bottom":
    u32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
    u32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, flags)
print("ok", mode)
