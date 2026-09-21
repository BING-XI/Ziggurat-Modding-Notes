"""Capture a window (even if occluded) via PrintWindow. Usage: grabwin.py <hwnd-hex> <out.png> [scale]"""
import sys, ctypes
from ctypes import wintypes
u32 = ctypes.WinDLL("user32"); g32 = ctypes.WinDLL("gdi32")

hwnd = int(sys.argv[1], 16)
out = sys.argv[2]
r = wintypes.RECT(); u32.GetWindowRect(hwnd, ctypes.byref(r))
w, h = r.right - r.left, r.bottom - r.top
hdc = u32.GetWindowDC(hwnd)
mdc = g32.CreateCompatibleDC(hdc)
bmp = g32.CreateCompatibleBitmap(hdc, w, h)
g32.SelectObject(mdc, bmp)
PW_RENDERFULLCONTENT = 2
ok = u32.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT)

class BMPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

bi = BMPINFOHEADER(); bi.biSize = ctypes.sizeof(BMPINFOHEADER)
bi.biWidth = w; bi.biHeight = -h; bi.biPlanes = 1; bi.biBitCount = 32; bi.biCompression = 0
buf = ctypes.create_string_buffer(w * h * 4)
g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)

# write PNG via PIL if available, else BMP
try:
    from PIL import Image
    img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1)
    if len(sys.argv) > 3:
        s = float(sys.argv[3])
        img = img.resize((int(w*s), int(h*s)))
    img.save(out)
    print(f"saved {out} {w}x{h} printwindow_ok={ok}")
except ImportError:
    import struct
    with open(out.replace('.png', '.bmp'), 'wb') as f:
        fsz = 54 + len(buf.raw)
        f.write(b'BM' + struct.pack('<IHHI', fsz, 0, 0, 54))
        f.write(struct.pack('<IiiHHIIiiII', 40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0))
        f.write(buf.raw)
    print(f"saved BMP (no PIL) {w}x{h} printwindow_ok={ok}")
g32.DeleteObject(bmp); g32.DeleteDC(mdc); u32.ReleaseDC(hwnd, hdc)
