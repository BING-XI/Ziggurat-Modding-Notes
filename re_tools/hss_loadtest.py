#!/usr/bin/env python3
r"""Ask a RUNNING AoWzEd to load <game>/Release/Release.hss, and report whether it worked.

WHY THIS EXISTS
    On 2026-09-20 a length-changing Release.hss splice was passed by a "launch the
    editor, is the process still alive after 16s" check.  It was alive -- with a window,
    at 40 MB -- and the mapset had not loaded at all.  **AoWzEd survives a failed mapset
    load and merely puts up a modal dialog**; the only failure that makes the exe vanish
    is the CRC one (`Exception('Invalid HSSET')` unhandled at startup).  So process
    liveness proves nothing and must never be used as the test again.

WHAT IT ACTUALLY CHECKS
    Drives the editor's own menu: `Developer > Open Mapset` (WM_COMMAND id 52), types
    the path into the file dialog's edit, presses Return, then looks for the modal
    `TMessageForm` that `HSSEdit.THSSEdit.LoadHSSFile` (HSEPack 0x55615D78) raises on
    any exception out of `THSEngine.LoadHSS`.  Dialog present => FAIL.

    ⚠ The editor does NOT load the mapset at startup unless AoWEd_LastDirs.ini has a
    `Set=` line, which is why this drives the menu rather than just restarting it.
    ⚠ The file-name edit comes up EMPTY, so the path is written with WM_SETTEXT; just
    posting Return to a freshly opened dialog loads nothing and looks like a pass.

Usage:
    hss_loadtest.py            -- find AoWzEd, load, print PASS/FAIL, dismiss the dialog
    hss_loadtest.py <pid>      -- same, for a specific process
Exit code 0 = loaded, 1 = failed to load, 2 = could not drive the editor.
"""
import ctypes, os, sys, time
from ctypes import wintypes

u32 = ctypes.WinDLL("user32", use_last_error=True)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
WM_COMMAND, WM_SETTEXT, WM_KEYDOWN, WM_KEYUP = 0x111, 0x000C, 0x100, 0x101
VK_RETURN = 0x0D
MENU_OPEN_MAPSET = 52

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
HSS = os.path.join(GAME, "Release", "Release.hss")


def tops(pid):
    out = []

    def cb(h, l):
        p = wintypes.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid:
            cls = ctypes.create_unicode_buffer(128); u32.GetClassNameW(h, cls, 128)
            t = ctypes.create_unicode_buffer(256); u32.GetWindowTextW(h, t, 256)
            out.append((h, cls.value, t.value))
        return True

    u32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def children(top, want):
    out = []

    def cb(h, l):
        cls = ctypes.create_unicode_buffer(128); u32.GetClassNameW(h, cls, 128)
        if cls.value == want:
            out.append(h)
        return True

    u32.EnumChildWindows(top, WNDENUMPROC(cb), 0)
    return out


def find_pid():
    import subprocess
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(Get-Process AoWzEd -ErrorAction SilentlyContinue).Id"],
                       capture_output=True, text=True)
    ids = [int(x) for x in r.stdout.split()]
    return ids[0] if ids else None


def msgforms(pid):
    return [h for h, c, t in tops(pid) if c == "TMessageForm"]


def main():
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else find_pid()
    if not pid:
        print("no AoWzEd running -- start it first"); return 2
    main_hwnd = next((h for h, c, t in tops(pid) if c == "TMainForm"), None)
    if not main_hwnd:
        print("no TMainForm -- editor not ready"); return 2

    for h in msgforms(pid):                      # clear anything stale
        u32.PostMessageW(h, 0x0010, 0, 0)        # WM_CLOSE
    time.sleep(0.5)

    u32.PostMessageW(main_hwnd, WM_COMMAND, MENU_OPEN_MAPSET, 0)
    time.sleep(2.5)
    dlg = next((h for h, c, t in tops(pid) if c == "#32770"), None)
    if not dlg:
        print("the Open dialog never appeared"); return 2
    edits = children(dlg, "Edit")
    if not edits:
        print("no filename edit in the Open dialog"); return 2
    u32.SendMessageW(edits[0], WM_SETTEXT, 0, ctypes.c_wchar_p(HSS))
    time.sleep(0.3)
    u32.PostMessageW(edits[0], WM_KEYDOWN, VK_RETURN, 0)
    u32.PostMessageW(edits[0], WM_KEYUP, VK_RETURN, 0)

    for _ in range(40):                          # up to ~20 s for a big mapset
        time.sleep(0.5)
        bad = msgforms(pid)
        if bad:
            for h in bad:
                u32.PostMessageW(h, 0x0010, 0, 0)
            print(f"FAIL - 'Error loading' dialog ({os.path.getsize(HSS)} bytes)")
            return 1
        if not any(c == "#32770" for _, c, _ in tops(pid)):
            time.sleep(2.0)                      # settle, then re-check
            if msgforms(pid):
                for h in msgforms(pid):
                    u32.PostMessageW(h, 0x0010, 0, 0)
                print(f"FAIL - 'Error loading' dialog ({os.path.getsize(HSS)} bytes)")
                return 1
            print(f"PASS - mapset loaded ({os.path.getsize(HSS)} bytes)")
            return 0
    print("TIMEOUT - neither the Open dialog closed nor an error appeared")
    return 2


if __name__ == "__main__":
    sys.exit(main())
