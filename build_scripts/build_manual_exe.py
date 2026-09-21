#!/usr/bin/env python3
r"""Package the Ziggurat Manual toolchain as `Modding Resources/Ziggurat Manual.exe`.

    python build_scripts/build_manual_exe.py          # build + smoke-test the exe

Not a binary patch -- no --apply/--undo; it (re)writes the exe and nothing else. The exe is a thin
runner (see manual_exe_stub.py): it executes the on-disk build_ziggurat_manual.py, so **editing the
builder does NOT require re-running this**. Re-run only when:

  * the builder family gains a new import (the exe fails loudly with ModuleNotFoundError), or
  * Python / openpyxl / Pillow are upgraded and you want the bundle to follow.

Requires: pip install pyinstaller  (6.22 against Python 3.14 when first built, 2026-08-14).
"""

import os
import shutil
import subprocess
import sys
import tempfile

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MR = os.path.join(GAME, "Modding Resources")
# The builder and the exe both live in the mod root now (owner's rule 2026-09-09:
# all Ziggurat work inside Ziggurat/). MR still holds the workshop assets we bundle.
BUILDER = os.path.join(GAME, "build_ziggurat_manual.py")
DIST = GAME
STUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manual_exe_stub.py")
NAME = "Ziggurat Manual"


def _bundled_data():
    """--add-data for everything the builder reads that a PLAYER will not have.

    The exe still runs the ON-DISK builder when one sits beside it, so a developer's edits
    need no rebuild; these copies are the fallback that lets a shipped Manual work with no
    workshop present. Re-run this script whenever the workbook or re_tools change, or the
    shipped Manual goes stale against them.

    ⚠ Destinations mirror the workshop's own layout, because the builder walks up for the
    workshop and settles on _MEIPASS when there is none on disk. Change one, change both.
    The design workbook is NO LONGER bundled: manual_data.json replaced it 2026-09-11.
    """
    items = [
        (BUILDER, "."),
        (os.path.join(MR, "manual_data.json"), "."),
        (os.path.join(MR, "re_tools"), "re_tools"),
        (os.path.join(MR, "Release - Vanilla"), "Release - Vanilla"),
        (os.path.join(MR, "Zig notes", "spell_names.json"), "Zig notes"),
        # ⚠ re_tools/ability_names.py reaches SIDEWAYS for these:
        #   os.path.join(re_tools, "..", "build_scripts", "herodlg_cats.py")
        # so they must land in a build_scripts/ SIBLING of the bundled re_tools, or a
        # standalone run dies with FileNotFoundError deep inside read_passive_abilities.
        # Missed until 2026-09-11 because the earlier standalone test left Modding
        # Resources/ on disk, so the builder used the on-disk re_tools and never
        # exercised the bundled copy at all.
        (os.path.join(MR, "build_scripts", "herodlg_cats.py"), "build_scripts"),
        (os.path.join(MR, "build_scripts", "heroskill_races.py"), "build_scripts"),
        (os.path.join(MR, "build_scripts", "heroskill_races.json"), "build_scripts"),
    ]
    out = []
    for src, dst in items:
        if not os.path.exists(src):
            # the builder degrades on most of these; say so rather than failing the build
            print("[bundle] MISSING, not bundled: %s" % src)
            continue
        out += ["--add-data", "%s%s%s" % (src, os.pathsep, dst)]
        print("[bundle] %s -> %s" % (os.path.basename(src), dst))
    return out


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit("PyInstaller is not installed. Run:\n  %s -m pip install pyinstaller"
                         % sys.executable)
    for p in (STUB, BUILDER):
        if not os.path.isfile(p):
            raise SystemExit("missing %s" % p)

    work = tempfile.mkdtemp(prefix="zm_exe_")
    cmd = [sys.executable, "-m", "PyInstaller", "--onefile", "--noconsole", "--noconfirm",
           "--name", NAME, "--distpath", DIST, "--workpath", work, "--specpath", work,
           # --noconsole, not --console: the manual opens as its OWN program now (pywebview on
           # the embedded WebView2 control), so a console window alongside it would be the one
           # thing still making it look like a script. The stub redirects both streams to
           # "Ziggurat Manual.log" beside the exe before anything prints -- under --noconsole
           # PyInstaller sets sys.stdout to None and the builder's first print() would
           # otherwise raise -- and pops a MessageBox naming the log if the build fails.
           # pywebview reaches its backend and its WebView2 interop DLLs (webview/lib/*.dll)
           # only through runtime lookups, so ordinary analysis finds none of them; collect
           # the three packages wholesale. clr is pythonnet's import name.
           "--collect-all", "webview",
           "--collect-all", "clr_loader",
           "--collect-all", "pythonnet",
           "--hidden-import", "clr",
           "--hidden-import", "webview.platforms.winforms",
           # ⚠ No --collect-submodules openpyxl: that reaches its optional pandas/numpy
           # integration and the bundle balloons 30 MB -> 153 MB (measured). The one lazy corner
           # the builder needs, openpyxl.cell.rich_text, is imported at the top of the stub, so
           # ordinary analysis already ships it. The excludes are belt-and-braces against any
           # library growing an optional heavyweight import later.
           "--exclude-module", "tkinter", "--exclude-module", "numpy",
           "--exclude-module", "pandas", "--exclude-module", "matplotlib",
           ] + _bundled_data() + [STUB]
    print("[pyinstaller] %s" % " ".join(cmd))
    if subprocess.call(cmd) != 0:
        raise SystemExit("PyInstaller failed; its work dir is kept for diagnosis: %s" % work)

    exe = os.path.join(DIST, NAME + ".exe")
    if not os.path.isfile(exe):
        raise SystemExit("PyInstaller reported success but %s does not exist" % exe)
    print("[ok  ] %s  (%.1f MB)" % (exe, os.path.getsize(exe) / 1048576.0))

    # Smoke test: --check runs the ENTIRE read side (workbook via openpyxl, every .pfs, both DLL
    # scans, portrait decode via Pillow) and writes nothing, so a missing bundled module surfaces
    # here and not on the author's next double-click.
    rc = subprocess.call([exe, "--check"], env=dict(os.environ, ZM_NO_OPEN="1"))
    if rc != 0:
        raise SystemExit("the exe failed its --check smoke test (exit %d)" % rc)
    print("[test] --check passed")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
