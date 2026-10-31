#!/usr/bin/env python
r"""
build_lost_display.py -- the game survives losing the screen (monitor sleep, minimise, Alt+Tab,
screen lock).  Gfxepack.dpl + Dcpack.dpl, vanilla code in both.

PLAYER REPORT (2026-10-31, relayed): after the monitor went to sleep the game could not be
un-minimised; a box "Exception occured during ExecuteBltSurface event" on a black screen.  Later:
"it does it when i minimise too now".

CAUSE (read from the code; not reproduced -- this machine has no 16-bit fullscreen mode)
  1. The box is TCustomDisplay.ExecuteBltSurfaceEvent (Dcpack 0x55105340): the step that copies a
     finished frame from the back surface to the screen.  Callers: UpdateFrame (every frame) and
     WM_PAINT of the window or the fullscreen control.  The main display's DFM sets
     BackSurfaceControlMode = bmBltSurface, no OnBltSurface handler, so the step is just
     DC.BltSurface.  Its except arm shows the box and then RE-RAISES (@RaiseAgain 0x55105419).
     UpdateFrameMode is umSynchrone: the frame loop is TCustomDisplay.StartUpdateFrameLoop
     (`UpdateFrame; Application.ProcessMessages` while [display+0x184] bit 0).  The re-raised
     exception unwinds out of that loop past its epilogue, the loop bit stays set, and
     StartUpdateFrameLoop refuses to start again -- no frame is ever drawn after the box.
  2. Window mode presents with TWindowsDC.BltSurface -> TDIB16Surface.BltDC (StretchDIBits): it
     cannot raise.  So the player plays fullscreen: TDDrawFullScr16DC, DC.BltSurface =
     TDDrawDC.BltSurface -> TSurface.BltStretch -> TDDrawSurface.Blt (Gfxepack 0x550099F0), whose
     only raises are 'SURFACE IS LOCKED' / 'DESTSURFACE IS LOCKED' -- the wrapper's lock flag
     ([surface+0x1D] bit 1, counts [+0x20] Lock and [+0x24] LockEx).  Lost surfaces themselves
     come back as HRESULTs and are restored by the surface's OnLost event (TDDrawDC.SurfaceLost
     -> VerifyLostSurfaces).
  3. The flag sticks in TDDrawSurface.Unlock (0x55009F70) and UnlockEx (0x5500A128): when
     IDirectDrawSurface::Unlock fails they return early and keep the count and the flag.  It fails
     when the surface was lost while locked, and a monitor power-off, display mode change,
     Alt+Tab or screen lock takes the surfaces away from another process, at any point of a
     frame -- the frame spends most of its time drawing into the locked back surface.  From then
     on Lock hands back the stale cached pointer without locking, every Blt of that surface raises,
     and the first present raises -> (1).
  ⚠ An exception thrown between a Lock and its Unlock (no try/finally in the draw code) leaks the
  flag the same way; that case shows its own box first ("Exception during WinManager
  DrawSurface", "Exception occurred during Update" or an aowInt "Error - <name>"), the player
  reported none, and this script does not heal it (see UNPROVEN).

THE PATCH (in place, no cave, no .reloc under any site)
  Gfxepack.dpl  0x55009FAD  74 1D -> 90 90   TDDrawSurface.Unlock: a failed DirectDraw Unlock still
                                             decrements [+0x20] and clears the flag when [+0x24] is
                                             0; the failure HRESULT is still returned.
  Gfxepack.dpl  0x5500A147  74 1B -> 90 90   TDDrawSurface.UnlockEx: the same for [+0x24].
      A lost surface holds no lock in DirectDraw; the wrapper now agrees.  Unlock never fails in
      normal play, and window mode (TDIB*Surface) never reaches either routine.
  Dcpack.dpl    0x55105414  call ShowMessage; call @RaiseAgain -> jmp 0x5510541E (@DoneExcept)
      The except arm swallows: no box, no re-raise; the frame is skipped and the loop carries on.
      The next present goes through Blt's own lost-surface path, and the vanilla deactivate /
      reactivate (TDDrawFullScrDC.MainWindowHook: WM_ACTIVATEAPP / WM_DISPLAYCHANGE -> Hide;
      0x69FF -> Show: SetCooperativeLevel, SetDisplayMode, VerifyLostSurfaces) brings the screen
      back.  No caller reads the step's result (UpdateFrame, both WM_PAINT handlers).  Silent
      because the step only presents a finished frame -- it holds no game logic -- and its
      failures are display states the next frame retries; game faults in the draw itself still
      reach their own boxes, with module and offset (build_error_detail.py).

Couplings: none.  Gfxepack.dpl had no patch before this; Dcpack.dpl's other sites belong to
build_window_zoom.py (0x55103C81, 0x55104107, 0x551050A9, 0x551051DC, 0x55105DBC, CODE tail) --
disjoint, either can be undone first.  Both modules load in the editors too (window mode, unaffected).
Rolls: none.  Local display state only.
UNPROVEN: the trigger on the player's machine (a failed DirectDraw Unlock) -- the chain above is
from the code; the only exception the present step can raise after this patch is a leaked lock
(⚠ above) or a fault inside ddraw.dll, and either now costs a frozen picture instead of a box.

USAGE  python build_lost_display.py [--dis] | --apply | --undo   (surgical; kills running AoW)
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import run

GFX = os.path.join(P.GAME, "Gfxepack.dpl")
DC = os.path.join(P.GAME, "Dcpack.dpl")

# Gfxepack.dpl (preferred base 0x55000000): `test al, al; je <keep the lock>` after ActiveX.Succeeded
G_UNLOCK, G_UNLOCKEX = 0x55009FAB, 0x5500A145
G_HOOKS = [(G_UNLOCK, bytes.fromhex("84c0741d"), bytes.fromhex("84c09090")),
           (G_UNLOCKEX, bytes.fromhex("84c0741b"), bytes.fromhex("84c09090"))]
G_FUNCS = [(G_UNLOCK, G_UNLOCK + 4, 0x55009F70, 0x55009FD1),      # TDDrawSurface.Unlock
           (G_UNLOCKEX, G_UNLOCKEX + 4, 0x5500A128, 0x5500A169)]  # TDDrawSurface.UnlockEx

# Dcpack.dpl (preferred base 0x55100000): ExecuteBltSurfaceEvent's except arm
D_SITE, D_DONE = 0x55105414, 0x5510541E
SHOWMESSAGE, RAISEAGAIN = 0x551019EC, 0x551010C0                   # import thunks


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


D_VAN = call_to(D_SITE, SHOWMESSAGE) + call_to(D_SITE + 5, RAISEAGAIN)
D_NEW = b"\xEB" + bytes([D_DONE - (D_SITE + 2)]) + b"\x90" * 8
D_FUNC = (D_SITE, D_SITE + len(D_VAN), 0x55105340, 0x5510542A)   # ExecuteBltSurfaceEvent


def go(argv):
    P.TARGET, P.IMAGE_BASE = GFX, 0x55000000
    run("build_lost_display [Gfxepack.dpl]", G_HOOKS, [], (G_UNLOCK, G_UNLOCK), G_FUNCS, argv)
    P.TARGET, P.IMAGE_BASE = DC, 0x55100000
    run("build_lost_display [Dcpack.dpl]", [(D_SITE, D_VAN, D_NEW)], [], (D_SITE, D_SITE),
        [D_FUNC], argv)


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])   # both modules verify first
        print("\n" + "=" * 60)
    go(argv)
