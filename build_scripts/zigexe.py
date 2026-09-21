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
  AoWz.exe / AoWzCompat.exe   the CANONICAL mod exes, in `Ziggurat\`.  PATCH THESE.
                              ⚠ Nothing runs them directly.  The runnable pair at the
                              game ROOT is a DERIVED artefact -- follow every exe patch
                              ⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)
  AoWzEd.exe                  the LIVE editor, in `Ziggurat\`, built by build_zigeditor.py
                              from AoWDevEd.exe.
  AoWDevEd.exe                the SOURCE editor, in `Ziggurat\`.  Patch this; AoWzEd.exe
                              is rebuilt from it.
  AoW.exe / AoWCompat.exe     ⚠⚠ VANILLA, at the game ROOT.  NEVER a patch target.
                              Named here only so a script can compare against stock.
                              (GOG ships the two byte-identical; the COMPAT_BYTE split
                              below is a Ziggurat property, not a vanilla one.)

Needs no third-party packages.
"""

# --- the mod's own binaries (all live in <root>\Ziggurat\) --------------------
GAME_EXE = "AoWz.exe"                 # canonical mod exe -- patch target
COMPAT_EXE = "AoWzCompat.exe"         # its lockstep twin -- patch target
SRC_EDITOR = "AoWDevEd.exe"           # editor patch source
LIVE_EDITOR = "AoWzEd.exe"            # editor the owner actually runs

#: the pair every exe feature patches, in lockstep, in this order
EXES = [GAME_EXE, COMPAT_EXE]

#: every mod executable, for "is this file locked / does this name exist" sweeps
ALL_EXES = [GAME_EXE, COMPAT_EXE, SRC_EDITOR, LIVE_EDITOR]

#: AoWzCompat.exe is AoWz.exe with exactly this file offset changed (0x0F -> 0x05,
#: build number 15 -> 5).  A lockstep check asserts the diff is exactly [COMPAT_BYTE].
COMPAT_BYTE = 0x3BB7C

# --- vanilla, at the game ROOT -- reference only, NEVER a write target --------
VANILLA_EXE = "AoW.exe"
VANILLA_COMPAT = "AoWCompat.exe"

#: process names that hold a lock on the game files (bare, no .exe) -- kill these
#: before writing.  Standing authorization; see CLAUDE.md.
LOCKING_PROCESSES = ["AoW", "AoWz", "AoWCompat", "AoWzCompat",
                     "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup"]
