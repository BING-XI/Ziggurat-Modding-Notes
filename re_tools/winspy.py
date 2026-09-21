"""Enumerate top-level + child windows of a process: handle, class, title, rect.

Usage: winspy.py <pid>
"""
import sys, ctypes
from ctypes import wintypes
u32 = ctypes.WinDLL("user32", use_last_error=True)

pid = int(sys.argv[1])
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

def info(hwnd):
    cls = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(hwnd, cls, 256)
    txt = ctypes.create_unicode_buffer(256)
    u32.GetWindowTextW(hwnd, txt, 256)
    r = wintypes.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    vis = u32.IsWindowVisible(hwnd)
    return f"{hwnd:#010x} {'v' if vis else '.'} ({r.left},{r.top})-({r.right},{r.bottom}) {cls.value:<24} '{txt.value}'"

tops = []
def cb(hwnd, lp):
    wpid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
    if wpid.value == pid:
        tops.append(hwnd)
    return True
u32.EnumWindows(WNDENUMPROC(cb), 0)

for t in tops:
    print("TOP", info(t))
    kids = []
    def cb2(hwnd, lp):
        kids.append(hwnd)
        return True
    u32.EnumChildWindows(t, WNDENUMPROC(cb2), 0)
    for k in kids:
        print("   ", info(k))
