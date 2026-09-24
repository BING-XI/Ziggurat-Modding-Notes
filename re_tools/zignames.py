#!/usr/bin/env python3
r"""
zignames.py -- re_tools' door to `build_scripts/zigexe.py`, the exe-name single source of truth.

WHY THIS EXISTS
  `zigexe.py` lives in `build_scripts/`, so a sibling `import zigexe` does not reach it from here.
  The 2026-09-09 rename (`AoW.exe` -> `AoWz.exe`, `AoWCompat.exe` -> `AoWzCompat.exe`, live editor
  `AoWzEd.exe`) fixed the twenty-one build scripts and missed re_tools entirely; twelve tools here
  still named the pre-rename pair a year of edits later.  Rather than add twelve copies of a
  `sys.path` expression, one module knows where `build_scripts` is:

      from zignames import zigexe
      pe = PE(os.path.join(GAME, zigexe.GAME_EXE))
      for name in zigexe.EXES: ...

  Re-exporting the MODULE rather than its names means a new constant in `zigexe.py` is usable here
  with no edit to this file.

  ⚠ `zigexe` supplies NAMES, not paths.  Joining is the caller's job, and which tree to join
  against is a real decision -- `Ziggurat\AoWz.exe` is the canonical PATCH TARGET while the
  RUNNABLE copy of that same name sits at the game ROOT (see `veh_capture.py`'s resolver).

  ⚠ One re_tools script names an old exe CORRECTLY and must not be swept into this:
  `mod_manifest.py` lists `AoWEd.exe` in `NEVER_SHIP`, a filename to exclude from the release
  payload rather than a target.  (`rng_audit.py` was exempted too until 2026-09-23, wrongly: its
  `AoW.exe` keys were audit targets, not references.  It now uses `zigexe.VANILLA_EXE` /
  `VANILLA_COMPAT` for its references.)

No third-party packages, no I/O beyond the import itself.
"""
import os
import sys

_BUILD_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build_scripts")

if not os.path.isfile(os.path.join(_BUILD_SCRIPTS, "zigexe.py")):
    raise ImportError(
        "zigexe.py not found in %s -- re_tools resolves it as "
        "<this file>/../build_scripts/zigexe.py, so either the workshop moved again or "
        "build_scripts/ is missing." % _BUILD_SCRIPTS)

if _BUILD_SCRIPTS not in sys.path:
    sys.path.insert(0, _BUILD_SCRIPTS)

import zigexe  # noqa: E402  (must follow the sys.path entry above)

__all__ = ["zigexe"]
