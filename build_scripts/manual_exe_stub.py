#!/usr/bin/env python3
r"""Entry point frozen into "Ziggurat Manual.exe" by build_manual_exe.py.

The exe is a THIN RUNNER, not a frozen copy of the builder. It bundles a Python interpreter plus
the third-party libraries (Pillow; openpyxl dropped 2026-09-11 with the workbook), then executes the **on-disk**
`build_ziggurat_manual.py` and opens the result. Because the builder is read from disk on every
run, editing it never requires rebuilding the exe -- the page a double-click produces can never lag
the builder or the game data.

The one way the exe can go stale: the builder family gains an import that is not baked into the
list below (PyInstaller analyses THIS file only; it never sees the builder). The symptom is loud,
not silent -- the exe dies with ModuleNotFoundError while `python build_ziggurat_manual.py` works.
The fix is one line here + re-running `build_scripts/build_manual_exe.py`.
"""

# ---------------------------------------------------------------------------------------------
# The frozen bundle ships ONLY what the analysis of this file reaches, so this list must be the
# union of every import in build_ziggurat_manual.py, re_tools/pfs.py, re_tools/ability_names.py
# and re_tools/aowsyms.py (which the builder loads from disk at runtime). Greppable check:
#   grep -o "import [a-z_.]*\|from [A-Za-z_.]* import" <those files> | sort -u
# ---------------------------------------------------------------------------------------------
import argparse, atexit, base64, bisect, builtins, codecs, collections, datetime, glob  # noqa
import hashlib, html, io, json, os, re, runpy, shutil, struct, subprocess, sys          # noqa
import tempfile, time, traceback, zlib                                                  # noqa
import importlib.util                                                                   # noqa
from PIL import Image                                                                   # noqa
import webview                                                                          # noqa

LOG_NAME = "Ziggurat Manual.log"


def _has_console():
    """Is a real console attached to this process?

    ⚠ DO NOT go back to testing `sys.stdout is None`. That is the documented behaviour of
    --noconsole and it is what this code checked first, but PyInstaller 6 on this toolchain
    hands a windowed build a WORKING bit-bucket stream instead: prints neither raise nor
    appear anywhere. The None-test therefore concluded "console present", skipped the log,
    and silently discarded every build line -- precisely the failure the log exists to
    prevent (measured 2026-08-27: window opened, no log written). GetConsoleWindow() answers
    the question that is actually being asked.
    """
    try:
        import ctypes                                               # noqa: PLC0415
        return bool(ctypes.windll.kernel32.GetConsoleWindow())
    except Exception:                                               # noqa: BLE001
        return sys.stdout is not None and sys.stdout.isatty()


def _start_log(base):
    """Redirect both streams to a log file beside the exe before anything runs. ALWAYS, for a
    frozen build -- never conditional on whether a console looks present.

    This is not cosmetic. The builder reports its counts and every `WARN:` line on stdout --
    nav/section mismatches, ungrouped rules, unreadable portraits, missing .pfs reads. Losing
    that turns a degraded build into a silent one.

    The unconditional rule exists because the windowed bootloader gives a working bit-bucket
    stdout, so output can vanish with no error in two different situations (double-clicked,
    and launched from a terminal that the windowed process never attaches to). Rather than
    enumerate them, log always: it costs one small file per run, and a developer who wants
    live output runs `python build_ziggurat_manual.py` directly, which never comes through
    here. Returns the log path.
    """
    path = os.path.join(base, LOG_NAME)
    try:
        f = io.open(path, "w", encoding="utf-8", errors="replace")
    except OSError:
        return None
    sys.stdout = sys.stderr = f
    atexit.register(f.close)
    print("Ziggurat Manual - build log")
    return path


def _alert(title, text):
    """A windowed build cannot print a failure anywhere the user will look. ctypes MessageBoxW
    needs no dependency and no console."""
    try:
        import ctypes                                               # noqa: PLC0415
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)   # MB_ICONERROR
    except Exception:                                               # noqa: BLE001
        pass


def main():
    frozen = getattr(sys, "frozen", False)
    base = os.path.dirname(os.path.abspath(sys.executable if frozen else __file__))
    if not frozen:                       # run as a plain script it lives in build_scripts/
        base = os.path.abspath(os.path.join(base, ".."))
    log = _start_log(base) if frozen else None
    script = os.path.join(base, "build_ziggurat_manual.py")

    # --watch respawns [sys.executable, <script>, ...]; frozen, sys.executable IS this exe, so a
    # child's argv leads with the script path. Drop it rather than feed it to argparse.
    args = [a for a in sys.argv[1:]
            if not (os.path.isabs(a) and os.path.normcase(os.path.abspath(a)) ==
                    os.path.normcase(script))]

    # A plain double-click should end with the page on screen. The builder owns HOW it opens
    # (--open: a standalone app window, not a browser tab), so window behaviour can change
    # without rebuilding this exe; the stub only decides WHETHER this run opens at all.
    if (not any(x in args for x in ("--check", "--watch", "--open"))
            and not os.environ.get("ZM_NO_OPEN")):
        args.append("--open")

    code = 0
    try:
        if not os.path.isfile(script):
            # Fall back to the copy bundled into the exe. On-disk always WINS when it is
            # there, so a developer editing the builder still sees changes without a
            # rebuild; the bundled copy is what makes a shipped Manual work standalone,
            # with no workshop beside it.
            bundled = os.path.join(getattr(sys, "_MEIPASS", ""), "build_ziggurat_manual.py")
            if os.path.isfile(bundled):
                print("using the builder bundled in the exe (none found on disk at %s)" % script)
                script = bundled
            else:
                raise SystemExit("cannot find build_ziggurat_manual.py next to the exe, "
                                 "and none is bundled:\n  %s" % script)
        sys.argv = [script] + args
        runpy.run_path(script, run_name="__main__")
    except SystemExit as exc:
        if isinstance(exc.code, int) or exc.code is None:
            code = exc.code or 0
        else:
            print(exc.code)
            code = 1
    except Exception:                                                   # noqa: BLE001
        traceback.print_exc()
        code = 1

    if code != 0:
        print("\nBUILD FAILED - the manual was NOT updated. Details above.")
        sys.stdout.flush()
        if log and not _has_console():
            # No console to read and no window to show, so the only way the user learns the
            # double-click did nothing is a dialog that names the log.
            # ⚠ Gated on _has_console(), NOT merely on `log`: the log is now unconditional for
            # frozen builds, and build_manual_exe.py smoke-tests the exe with `--check` from a
            # terminal. An ungated modal here would block that call forever on any failure --
            # turning a failed self-test into a hung build.
            _alert("Ziggurat Manual - build failed",
                   "The manual was NOT updated.\n\nDetails:\n%s" % log)
        elif frozen and sys.stdin is not None:
            try:
                input("Press Enter to close...")
            except EOFError:
                pass
        sys.exit(code)


if __name__ == "__main__":
    main()
