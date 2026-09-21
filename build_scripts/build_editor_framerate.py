r"""Editor responsiveness patch: raise the map view's FrameRate (DFM) from 15 to 60,
and optionally give the scanner progressive redraw (MapDrawSteps 1 -> 8).

Why: the THSMEdit map view is created with FrameRate=15 (DFM vaInt8). While the editor is
active, the render loop paces the message pump at exactly 1000/15 = 67 ms, so every queued
click / tab switch drains at <=15 events per second (measured 2026-07-07 with WM_NULL probes:
67.0 +/- 0.5 ms per pump). One byte per exe fixes the pacing floor.
See Editor_Lag_CopyPaste_Investigation_2026-07-07.md.

================================================================================
⚠⚠ THE EDITOR EXE TRAP -- an editor patch is TWO steps
================================================================================
`Ziggurat\AoWDevEd.exe` (zigexe.SRC_EDITOR) is the PATCH SOURCE, and nothing runs it.
The editor the owner actually launches is `Ziggurat\AoWzEd.exe` (zigexe.LIVE_EDITOR),
which `build_zigeditor.py` REBUILDS from AoWDevEd.exe. Skip the second step and the
patch sits in a file no one loads -- silently:

    python build_editor_framerate.py --apply    # patches Ziggurat\AoWDevEd.exe
    python build_zigeditor.py        --apply    # rebuilds -> Ziggurat\AoWzEd.exe

(build_zigeditor.py takes --apply / --undo / --png PATH; no args = dry run.)

⚠ `AoWEd.exe` is NO LONGER A TARGET. The 2026-09-09 move left no copy in the overlay --
only the game root's stock one, which is VANILLA and must never be patched. Its offsets
are kept here as reusable RE machinery, not as a live target:
    AoWEd.exe  FrameRate prop 0x743D5, value 0x743E0, MapDrawSteps value 0xD2E65

Usage:
  python build_editor_framerate.py            # dry-run: verify current bytes, show plan
  python build_editor_framerate.py --apply    # patch (auto-backup <game dir>\backups\)
  python build_editor_framerate.py --fps 30   # choose a different frame rate (2..120)
  python build_editor_framerate.py --no-steps # skip the scanner MapDrawSteps patch

Revert: there is no snapshot layer -- both `.pre-*` stacks were purged (2026-08-08 and
2026-09-03) and nothing has rebuilt them, so a `.pre-edfps` is at most one disposable copy
of today's file. Re-tune with `--fps N`, which rewrites the byte in place (the DFM anchor
proves it is the right byte, so any current value is a valid source). `--fps 15` restores
vanilla pacing. ⚠ MapDrawSteps has NO restore path here: the patch only fires when the byte
still reads 1, so re-running never puts it back -- edit it by hand if you need 1 again.
The editor locks its own exe; close it before --apply.
"""
import argparse, os, shutil, sys

import zigexe

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")

# (exe, framerate-prop file off, framerate value off, mapdrawsteps value off)
# Prop layout: \x09FrameRate \x02 <byte>   /   \x0cMapDrawSteps \x02 <byte>
TARGETS = [
    (zigexe.SRC_EDITOR, 0x75195, 0x751A0, 0xD3C3D),
]
OLD_FPS = 15
OLD_STEPS = 1
NEW_STEPS = 8
BACKUP_SUFFIX = ".pre-edfps"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--fps", type=int, default=60, help="new FrameRate (default 60)")
    ap.add_argument("--no-steps", action="store_true", help="skip scanner MapDrawSteps 1->8")
    args = ap.parse_args()
    if not (2 <= args.fps <= 120):
        sys.exit("--fps out of range (2..120)")

    for exe, prop_off, fps_off, steps_off in TARGETS:
        path = os.path.join(GAME, exe)
        if not os.path.exists(path):
            print(f"[{exe}] MISSING - skipped")
            continue
        data = bytearray(open(path, "rb").read())

        # verify anchor: shortstr 'FrameRate' + vaInt8 marker
        anchor = b"\x09FrameRate\x02"
        if bytes(data[prop_off:prop_off+len(anchor)]) != anchor:
            print(f"[{exe}] ABORT: FrameRate prop not at {prop_off:#x} (found "
                  f"{bytes(data[prop_off:prop_off+12])!r})")
            continue
        cur_fps = data[fps_off]
        steps_anchor = b"\x0cMapDrawSteps\x02"
        steps_ok = bytes(data[steps_off-len(steps_anchor):steps_off]) == steps_anchor
        cur_steps = data[steps_off] if steps_ok else None

        label = "already at target" if cur_fps == args.fps else (
            "vanilla" if cur_fps == OLD_FPS else f"currently {cur_fps}")
        print(f"[{exe}] FrameRate @ {fps_off:#x}: {cur_fps} ({label})"
              + (f" | MapDrawSteps @ {steps_off:#x}: {cur_steps}" if steps_ok
                 else " | MapDrawSteps anchor NOT found (skipping steps)"))

        if not args.apply:
            continue
        # anchor (\x09FrameRate\x02 above) already proved this is the right byte, so any current
        # value is a valid re-patch source (e.g. 15->60, or 60->120 to retune).

        changes = []
        if cur_fps != args.fps:
            changes.append((fps_off, args.fps, f"FrameRate {cur_fps}->{args.fps}"))
        if steps_ok and not args.no_steps and cur_steps == OLD_STEPS:
            changes.append((steps_off, NEW_STEPS, f"MapDrawSteps {OLD_STEPS}->{NEW_STEPS}"))
        if not changes:
            print(f"[{exe}] nothing to do (idempotent)")
            continue

        # Snapshot goes in <game dir>\backups\, never beside the binary (CLAUDE.md 2026-09-03).
        # Only taken when the FrameRate byte still reads vanilla -- otherwise the "original"
        # it would preserve is our own earlier output.
        backup = os.path.join(BACKUP_DIR, exe + BACKUP_SUFFIX)
        if cur_fps != OLD_FPS:
            print(f"[{exe}] no backup taken (FrameRate is {cur_fps}, not vanilla {OLD_FPS})")
        elif not os.path.exists(backup):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(path, backup)
            print(f"[{exe}] backup -> {backup}")
        for off, val, desc in changes:
            data[off] = val
            print(f"[{exe}] {desc} @ {off:#x}")
        try:
            open(path, "wb").write(data)
        except PermissionError:
            print(f"[{exe}] LOCKED - close the editor first")
            continue
        print(f"[{exe}] written")

    if not args.apply:
        print("\ndry-run only; use --apply to patch")

main()
