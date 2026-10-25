r"""
launch_proof.py -- the launch test for package-init caves: start AoWz.exe from the Ziggurat folder,
and pass as soon as it shows a main window (any visible window but TApplication's), is still alive
and responding SETTLE seconds later, and shows no error dialog; then kill it.  Every package's
initialization runs before the exe's main block creates that window, so its appearance proves
them (owner, 2026-10-25: keep the game on screen as briefly as possible; it used to wait a fixed
12 s).  Exit 0 = pass.  --wait is only the give-up time.

Skip Intro (owner, 2026-10-22): `HKCU\Software\Triumph Studios\Age of Wonders Z\General\Skip Intro`
is set to 1 for the run and the previous value (or its absence) is put back afterwards, also when
the run fails.  The game reads the same HKCU view as this process, so the setting reaches it even
where the agent shell's HKCU differs from the owner's (12-re-toolchain.md, HKCU divergence).

Running AoW binaries are killed first (CLAUDE.md), and the test instance is killed at the end.

    python re_tools/launch_proof.py              AoWz.exe, give up after 10 s
    python re_tools/launch_proof.py --exe AoWzEd.exe   (back up AoWEd_LastDirs.ini first)
"""
import argparse, ctypes, ctypes.wintypes as W, os, subprocess, sys, time, winreg

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
KEY = r"Software\Triumph Studios\Age of Wonders Z\General"
VALUE = "Skip Intro"
SETTLE = 0.5
AOW = ("AoW", "AoWz", "AoWCompat", "AoWzCompat", "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup")

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
EnumProc = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)


def kill_aow():
    names = ",".join("'%s'" % n for n in AOW)
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-Process | Where-Object { @(%s) -contains $_.ProcessName } | Stop-Process -Force"
                    % names], capture_output=True)


def read_skip():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            return winreg.QueryValueEx(k, VALUE)
    except FileNotFoundError:
        return None


def write_skip(old):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
        if old is None:
            winreg.DeleteValue(k, VALUE)
        else:
            winreg.SetValueEx(k, VALUE, 0, old[1], old[0])


def windows(pid):
    out = []

    def cb(h, _l):
        p = W.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(h):
            t = ctypes.create_unicode_buffer(256)
            c = ctypes.create_unicode_buffer(256)
            u32.GetWindowTextW(h, t, 256)
            u32.GetClassNameW(h, c, 256)
            out.append((t.value, c.value, h))
        return True
    u32.EnumWindows(EnumProc(cb), 0)
    return out


def responding(h):
    r = W.DWORD()
    return bool(u32.SendMessageTimeoutW(h, 0, 0, 0, 0x0002, 3000, ctypes.byref(r)))


def is_error(t, c):
    return "error" in t.lower() or c == "#32770"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default="AoWz.exe")
    ap.add_argument("--wait", type=float, default=10.0, help="give up after this many seconds")
    a = ap.parse_args()
    kill_aow()
    old = read_skip()
    kind = old[1] if old else winreg.REG_DWORD
    write_skip((1, kind) if kind == winreg.REG_DWORD else ("1", kind))
    ok = False
    try:
        p = subprocess.Popen([os.path.join(GAME, a.exe)], cwd=GAME)
        t0 = time.time()
        wins, up = [], None
        while time.time() - t0 < a.wait and p.poll() is None:
            wins = windows(p.pid)
            if any(is_error(t, c) for t, c, _h in wins):
                break
            if up is None and any(c != "TApplication" for _t, c, _h in wins):
                up = time.time() - t0
                time.sleep(SETTLE)
                continue
            if up is not None:
                break
            time.sleep(0.1)
        alive = p.poll() is None
        wins = windows(p.pid) if alive else []
        resp = alive and all(responding(h) for _t, _c, h in wins)
        error = [t for t, c, _h in wins if is_error(t, c)]
        print("%s: %s, alive %s, responding %s, windows %s" % (
            a.exe, "main window after %.1f s" % up if up is not None else
            "no main window in %.0f s" % a.wait, alive, resp,
            ", ".join("[%s] %s" % (c, t) for t, c, _h in wins) or "none"))
        ok = up is not None and alive and resp and not error
        if error:
            print("ERROR DIALOG: %s" % ", ".join(error))
        if alive:
            p.kill()
            p.wait()
    finally:
        write_skip(old)
        back = read_skip()
        print("Skip Intro restored to %s" % (back[0] if back else "absent"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
