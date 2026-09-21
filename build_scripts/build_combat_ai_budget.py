r"""Tactical-combat AI responsiveness: raise TCAI.EvalBattle's per-frame work budget from 1 to 16.

================================================================================
WHY -- measured, not guessed (2026-09-12)
================================================================================
In manual combat the AI pauses between every unit's move. It is NOT thinking time and it is NOT
the animation: a read-only probe of a live AI turn (184 Hz sampling of the token executer, the
TCAI state, and the display's own fps field) accounted for 42.6 s as

    EvalBattle state 1 -- queue EMPTY, nothing animating   32 x 692 ms = 21.2 s   50%
    TCAbRangedTE running (real animation)                  13 x 958 ms = 12.7 s   30%
    TCombatMoveTE running (real animation)                 17 x 263 ms =  4.3 s   10%
    EvalBattle states 3,4,5,0 (one frame each)             31 x  33 ms =  4.4 s   10%

Half the AI's turn is one repeating 692 ms stall with an empty token queue and nothing on screen.

`AoWTC.TCAI.EvalBattle @0x418170` is a resumable state machine on `cai[+0x1c]` (jump table at
`0x4181DB`), entered once per rendered frame from `TAoWCombatMap.NewFrame @0x41C440` via
`TCAI.ContinueTurn @0x4135A4`. The observed ring is **0 -> 1 -> 3 -> 4 -> 5 -> 0 for EVERY unit
action** (state 2 is skipped by the second increment at `0x41944C`; state 5 resets `cai[+0x1c]` to 0
at `0x41AF80`). States 3/4/5/0 each cost exactly one frame.

State 1 scans the combat-object list `cai[+8]`, indexed by `cai[+0x20]`, with `cai[+0x24]` as a
per-frame work counter:

    0041925C  add dword [cai+0x20], 1     ; i++
    0041926A  add dword [cai+0x24], 1     ; budget++
    00419289  cmp dword [cai+0x24], 1     ; <-- THE KNOB (83 78 24 01)
    0041928D  jl  0x418AF8                ; under budget -> another unit THIS frame
              ...                          ; else fall through; 0x41950F resets budget to 0

The budget starts at 0 (`0x418AB3`) and is reset to 0 on the not-finished exit (`0x41950F`), so
**exactly one unit is evaluated per rendered frame** -- and the whole scan restarts for every
action. The cost is O(units) frames per action x O(actions) per turn, i.e. QUADRATIC in army size.
That is why it is invisible in a skirmish and brutal with a few dozen units. The measured
692 ms / 33.3 ms ~= 21 frames ~= the units in that battle.

Nothing here is a clock. `AoWTCPCK.dpl` imports no time function at all (no `timeGetTime`, no
`GetElapsedMilliSeconds`, no `GetTickCount`), so all of tactical combat is counted in display
frames, paced at `AoWz.exe`'s DFM `FrameRate` = 30 -> 33.3 ms
(`DCPACK.dpl!DisplayC.TUpdateFrameThread.Execute @0x55104674`).

================================================================================
WHAT THIS CHANGES -- and what it deliberately does not
================================================================================
Only HOW MANY units the AI evaluates per rendered frame. It does not change what the AI decides,
does not touch any animation, and does not alter the frame rate.

*** The engine already ships a larger budget at the third site: state 3 uses 50 (`0x419E78`). ***
This script only raises the two that are set to 1; site 3 is read as a sentinel and never written.

RNG: the scan calls `TCAI.CheckUnit`, `TSpellControl.GetSpell` and `THero.CanCastSpellInstantly`,
and never `TAoWHSMap.Random` -- verified across the whole state-1/state-2 range. Draws are
therefore per-unit, not per-frame, so the DRAW COUNT is unchanged by the budget and multiplayer
lockstep is unaffected (Zig notes 12-re-toolchain.md S4.10).

================================================================================
THE PATCH -- two imm8 bytes, no cave, nothing displaced
================================================================================
Target: `Ziggurat\AoWTCPCK.dpl` (tactical combat package; NOT an exe, so no AoWz/AoWzCompat
lockstep pair applies here).

  VA          file off   enc            scan
  0x00419289  0x18689    83 78 24 01    state 1 -- the 692 ms stall      <- patched
  0x00419B2C  0x18F2C    83 78 24 01    state 2 -- same idiom            <- patched
  0x00419E78  0x19278    83 78 24 32    state 3 -- engine's own 50       <- sentinel, read only

Because the edit is an immediate operand inside an existing instruction, nothing moves: no cave, no
E9 hook, no displaced bytes, and therefore no `.reloc` hazard (contrast
`Zig notes/12-re-toolchain.md` on stale relocations). Position-independence is moot for the same
reason -- no new code is emitted, so the package may rebase freely.

Revert: `--undo` writes 1 back to both sites, surgically. Re-tuning is an in-place rewrite --
`--budget N` accepts EITHER the stock 1 or any value this script installed, because the
`83 78 24` opcode anchor proves it is the right byte.

Usage:
  python build_combat_ai_budget.py                 # dry-run: report current state
  python build_combat_ai_budget.py --apply         # patch to 16
  python build_combat_ai_budget.py --apply --budget 50   # match the engine's own site-3 value
  python build_combat_ai_budget.py --undo          # restore vanilla 1

The game and editor lock the package -- close them first (the coder kills them; standing
authorization per CLAUDE.md).

================================================================================
CONFIRMED WORKING in game (2026-09-12, owner's test)
================================================================================
Of the ~0.7 s inter-move stall, **0.5 s+ is gone**. No stutter, no change in how the AI plays.

The residue (~0.2 s) is the floor this knob cannot reach: states 3, 4, 5 and 0 each cost exactly
one frame per action no matter what the budget is, so ~4 x 33.3 ms is structural at FrameRate 30.
Shortening that further means the frame clock itself -- `AoWz.exe` / `AoWzCompat.exe` DFM
`FrameRate` 30 at file offset 0x12F8D4 -- which scales the strategic map identically and is a
separate decision.
"""
import argparse, os, shutil, sys

# game dir = two levels up from this script (<game>/Ziggurat/Modding Resources/build_scripts/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")

TARGET = "AoWTCPCK.dpl"
BACKUP_SUFFIX = ".pre-aibudget"
OPCODE = b"\x83\x78\x24"          # cmp dword ptr [eax+0x24], imm8
STOCK = 1
DEFAULT_BUDGET = 16

# (file offset of the opcode, VA, label)
SITES = [
    (0x18689, 0x00419289, "state 1 scan (the 692 ms stall)"),
    (0x18F2C, 0x00419B2C, "state 2 scan"),
]
# read-only sentinel: the engine's own larger budget, proves the offsets have not shifted
SENTINEL = (0x19278, 0x00419E78, 0x32, "state 3 scan (engine default)")


def check(data, off, va, label):
    """returns the current imm8, or None if the opcode anchor does not match"""
    if bytes(data[off:off + 3]) != OPCODE:
        print("  ABORT: no 'cmp [eax+0x24], imm8' at %#x (VA %08X) -- found %s"
              % (off, va, bytes(data[off:off + 4]).hex(" ")))
        return None
    return data[off + 3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--undo", action="store_true", help="restore the vanilla budget of 1")
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET,
                    help="units evaluated per frame (default %d)" % DEFAULT_BUDGET)
    args = ap.parse_args()

    want = STOCK if args.undo else args.budget
    if not (1 <= want <= 127):
        sys.exit("--budget out of range (1..127; the operand is a sign-extended imm8)")

    path = os.path.join(GAME, TARGET)
    if not os.path.exists(path):
        sys.exit("%s not found under %s" % (TARGET, GAME))
    data = bytearray(open(path, "rb").read())
    print("%s  (%d bytes)" % (path, len(data)))

    s_off, s_va, s_want, s_label = SENTINEL
    sentinel = check(data, s_off, s_va, s_label)
    if sentinel is None:
        sys.exit("sentinel site unreadable -- offsets are wrong for this build, refusing to write")
    if sentinel != s_want:
        print("  NOTE: sentinel %s at %#x reads %d, expected %d"
              % (s_label, s_off, sentinel, s_want))
    else:
        print("  sentinel ok: %s @ %#x = %d" % (s_label, s_off, sentinel))

    current = []
    for off, va, label in SITES:
        cur = check(data, off, va, label)
        if cur is None:
            sys.exit("refusing to write")
        state = "vanilla" if cur == STOCK else ("already %d" % cur)
        print("  budget @ %#x (VA %08X) = %-3d (%s)  -- %s" % (off, va, cur, state, label))
        current.append(cur)

    if not (args.apply or args.undo):
        print("\ndry-run only; use --apply to patch (target budget %d) or --undo to restore %d"
              % (args.budget, STOCK))
        return

    changes = [(off, va, cur, label) for (off, va, label), cur in zip(SITES, current) if cur != want]
    if not changes:
        print("\nnothing to do -- both sites already read %d (idempotent)" % want)
        return

    # Snapshot goes in <game dir>\backups\, never beside the binary (CLAUDE.md 2026-09-03), and is
    # minted on a WRITE only -- and only while both sites still read stock, otherwise the
    # "pre-patch" copy it preserves would be this script's own earlier output.
    if all(c == STOCK for c in current):
        backup = os.path.join(BACKUP_DIR, TARGET + BACKUP_SUFFIX)
        if os.path.exists(backup):
            print("\nbackup already present: %s" % backup)
        else:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(path, backup)
            print("\nbackup -> %s" % backup)
    else:
        print("\nno backup taken (sites read %s, not stock %d)" % (current, STOCK))

    for off, va, cur, label in changes:
        data[off + 3] = want
        print("  %#x (VA %08X): budget %d -> %d   [%s]" % (off, va, cur, want, label))
    try:
        open(path, "wb").write(data)
    except PermissionError:
        sys.exit("LOCKED -- close AoWz.exe / AoWzCompat.exe / AoWzEd.exe and retry")
    print("written.  Re-run with no arguments to verify.")


main()
