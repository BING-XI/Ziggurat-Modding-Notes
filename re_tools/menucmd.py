"""Menu automation: list menu tree with command IDs, or send WM_COMMAND.

Usage: menucmd.py <main-hwnd-hex> list
       menucmd.py <main-hwnd-hex> exec <id>
"""
import sys, ctypes
from ctypes import wintypes
u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.GetMenu.restype = ctypes.c_void_p
u32.GetSubMenu.restype = ctypes.c_void_p
u32.GetSubMenu.argtypes = [ctypes.c_void_p, ctypes.c_int]
u32.GetMenuItemCount.argtypes = [ctypes.c_void_p]
u32.GetMenuItemID.argtypes = [ctypes.c_void_p, ctypes.c_int]
u32.GetMenuStringW.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_wchar_p, ctypes.c_int, wintypes.UINT]

hwnd = int(sys.argv[1], 16)
cmd = sys.argv[2]
WM_COMMAND = 0x111
MF_BYPOSITION = 0x400

def walk(menu, depth):
    n = u32.GetMenuItemCount(menu)
    for i in range(n):
        buf = ctypes.create_unicode_buffer(128)
        u32.GetMenuStringW(menu, i, buf, 128, MF_BYPOSITION)
        mid = u32.GetMenuItemID(menu, i)
        sub = u32.GetSubMenu(menu, i)
        tag = f"id={mid}" if mid != 0xFFFFFFFF else "submenu"
        print("  " * depth + f"[{i}] {buf.value!r} {tag}")
        if sub:
            walk(sub, depth + 1)

if cmd == "list":
    menu = u32.GetMenu(hwnd)
    print(f"menu={menu}")
    walk(menu, 0)
elif cmd == "exec":
    mid = int(sys.argv[3])
    u32.PostMessageW(hwnd, WM_COMMAND, mid, 0)
    print(f"posted WM_COMMAND {mid}")
