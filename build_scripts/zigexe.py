#!/usr/bin/env python3
r"""
ZIGGURAT BINARY NAMES -- the single place a mod executable is named.

WHY THIS EXISTS
  On 2026-09-09 the mod moved into `<root>\Ziggurat\` and its executables were renamed
  `AoW.exe` -> `AoWz.exe`, `AoWCompat.exe` -> `AoWzCompat.exe`, so that the purple-icon
  mod pair could not be confused with the vanilla pair at a glance.  Those two names were
  hard-coded in **twenty-one** build scripts.  Every one of them broke at once, and the
  repair was twenty-one near-identical edits.  This module exists so the next rename is
  one edit.

  ⚠ It supplies NAMES, not paths.  Every build script already resolves its own `GAME`
  (`__file__/../..` -> `<root>\Ziggurat`); joining is the caller's job:

      import zigexe
      EXES = zigexe.EXES
      path = os.path.join(GAME, EXES[0])          # <root>\Ziggurat\AoWz.exe

  A sibling `import zigexe` resolves from any working directory because Python puts the
  running script's own directory at the head of `sys.path`.  No dependencies, no I/O, no
  path resolution -- keep it that way.

WHICH NAME IS WHICH
  AoWz.exe                    the mod game exe, in `Ziggurat\`.  PATCH THIS.  Live as soon
                              as it is written: it runs from `Ziggurat/`.
  AoWzEd.exe                  the LIVE editor, in `Ziggurat\`, built by build_zigeditor.py
                              from AoWDevEd.exe.
  AoWDevEd.exe                the SOURCE editor, in `Ziggurat\`.  Patch this; AoWzEd.exe
                              is rebuilt from it.
  AoW.exe / AoWCompat.exe     ⚠⚠ VANILLA, at the game ROOT.  NEVER a patch target.
                              Named here only so a script can compare against stock.
                              GOG ships the two byte-identical: AoWCompat.exe exists only
                              so GOG can pin Windows compatibility layers (NT4SP5
                              DISABLEDWM HIGHDPIAWARE, keyed by path) to the copy it
                              launches.  The mod's twin, AoWzCompat.exe, carried no layers
                              and was retired 2026-09-28.

Needs no third-party packages.
"""

# --- the mod's own binaries (all live in <root>\Ziggurat\) --------------------
GAME_EXE = "AoWz.exe"                 # canonical mod exe -- patch target
SRC_EDITOR = "AoWDevEd.exe"           # editor patch source
LIVE_EDITOR = "AoWzEd.exe"            # editor the owner actually runs

#: every game exe an exe feature patches.  One since AoWzCompat.exe was retired
#: (2026-09-28); scripts still loop over it, so a list rather than a name.
EXES = [GAME_EXE]

#: every mod executable, for "is this file locked / does this name exist" sweeps
ALL_EXES = [GAME_EXE, SRC_EDITOR, LIVE_EDITOR]

# --- vanilla, at the game ROOT -- reference only, NEVER a write target --------
VANILLA_EXE = "AoW.exe"
VANILLA_COMPAT = "AoWCompat.exe"      # byte-identical to AoW.exe; see WHICH NAME IS WHICH

#: process names that hold a lock on the game files (bare, no .exe) -- kill these
#: before writing.  Standing authorization; see CLAUDE.md.
LOCKING_PROCESSES = ["AoW", "AoWz", "AoWCompat",
                     "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup"]
