#!/usr/bin/env python3
r"""
build_clogwin_gate.py -- toggle the combat log's EXE-side pieces, for A/B isolation of the "Blt Error"
that fires on any damage to a combat WALL.

STATE OF THE INVESTIGATION (2026-07-22)
---------------------------------------
The freeze (a wall's `+0x4C` misread as a strategic-unit pointer by the DLL worker) is FIXED and
confirmed in-game. Separately, an `Error - FCWin` / `Blt Error` dialog fires on **any** hit to a wall
-- confirmed with cannons, so not touch-ability specific -- and per the user does not occur without
the combat log feature.

Isolation so far, all against the reliable "hit the wall" repro:
  * `touch` DLL hooks off          -> error persists
  * ALL SEVEN DLL hooks off        -> error persists   <== the DLL half is EXONERATED
  * exe: window forced never-visible -> error persists <== visibility is EXONERATED

Every earlier test in this investigation, including the six-step backup bisection, swapped only
AoWEPACK.dpl -- the exe half had never been tested at all until now.

WHAT REMAINS, and what this toggles
-----------------------------------
`build_combatlog_exe.py` adds three things to AoWz.exe: the `.clog` section, a cloned `TCombatLogWin`
(created by an extra CreateForm), and `cave_drain` hooked into the PAINT PUMP. Two are toggleable
here without unpicking the section:

  vis    0x61055C  cave_drain's visibility decision -> always `_nowant`, so the window never shows.
                   Leaves the section, window object, drain and hooks in place.
  drain  0x451218  `TMWindow.MapWindowUpdate`. Restoring the stock prologue removes cave_drain from
                   the per-frame pump entirely, leaving the section, the CreateForm and the window
                   object. Isolates "our per-frame code" from "our window merely existing".

⚠ The exe cave has MOVED since the project notes were written: they say cave_drain is at 0x60F600;
it is really at 0x6105A0, so `_vis` is at 0x61055C. Re-derive if it moves again -- a stale address
makes this tool ABORT (never corrupt), because every site is verified against both known encodings.

USAGE
    python build_clogwin_gate.py (--off | --on) [--vis] [--drain] [--apply]
      --off  restores STOCK behaviour for the named group(s)
      --on   restores OUR behaviour

Patches BOTH canonical mod exes `Ziggurat\AoWz.exe` and `Ziggurat\AoWzCompat.exe` (names from
`zigexe.py`) and verifies each separately -- the notes record the compat twin being silently left
unpatched once. ⚠ Follow a write with ⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.) Idempotent, verify-before-write, dry-run by default, refuses to write while the game is
running.

NO BACKUP IS MINTED, deliberately (changed 2026-09-09). This script is a pure TOGGLE: every site
has both its stock bytes and ours written out in full, each write is verified against the other
state first, and `--off`/`--on` are exact inverses -- so the script is already its own surgical
revert, which is the project's revert path anyway. The old `<exe>.pre-clogwinhide` snapshot was
gated on "no backup file exists yet", which is not a proof of anything: after the 2026-09-09 rename
no `AoWz.exe.pre-clogwinhide` can exist, so that gate would have minted one holding whatever state
the exe happened to be in. There is no "unpatched" state for a toggle to snapshot honestly.
"""
import os, struct, subprocess, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                   # mod binary names (AoWz.exe / AoWzCompat.exe)
EXES = zigexe.EXES

# group -> (va, STOCK bytes, OURS bytes, description)
SITES = {
    # NB the convention: slot 2 = what "--off" writes (our behaviour DISABLED), slot 3 = "--on".
    # For `vis`, disabling our behaviour means the window never shows, so the diagnostic `jmp
    # _nowant` is the OFF state and the normal visibility rule is the ON state. Getting these the
    # wrong way round once already made `--on --vis` silently hide the window.
    "vis":   (0x61055C,
              bytes.fromhex("eb26909090"),      # OFF: jmp _nowant (+0x26)  -- never visible
              bytes.fromhex("a10cd06000"),      # ON : mov eax,[0x60D00C]   -- normal rule
              "cave_drain _vis -> show/never-show the window"),
    "drain": (0x451218,
              bytes.fromhex("538bd8a17cdf4500"),  # stock TMWindow.MapWindowUpdate prologue
              bytes.fromhex("e983f31b00909090"),  # jmp cave_drain @0x6105A0 + 3 nops
              "TMWindow.MapWindowUpdate -> cave_drain (per-frame pump)"),
    # The LAST active piece. The hook replaces `call Application.Run` with a jump into
    # cave_createwin, which appends one more TApplication.CreateForm(TCombatLogWin) after the 78
    # vanilla ones and then calls Run itself. Restoring the stock call means the cloned window is
    # NEVER CREATED -- nothing of the combat log exists at runtime except a dead .clog section.
    "createwin": (0x459FAF,
              b"\xE8" + struct.pack("<i", 0x401764 - (0x459FAF + 5)),   # OFF: call Application.Run
              b"\xE9" + struct.pack("<i", 0x610340 - (0x459FAF + 5)),   # ON : jmp cave_createwin
                                                                        # (notes say 0x60F5E0 -- stale;
                                                                        #  the exe cave has moved twice)
              "Application.Run call -> cave_createwin (creates the cloned window)"),
}

def load_sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    oh = struct.unpack_from("<H", d, e + 0x14)[0]
    out = []
    for i in range(n):
        o = e + 0x18 + oh + i * 40
        vs, va, rs, ptr = struct.unpack_from("<IIII", d, o + 8)
        out.append((va, vs, rs, ptr))
    return out

def foff(secs, va):
    r = va - 0x400000
    for sva, vs, rs, ptr in secs:
        if sva <= r < sva + max(vs, rs) and rs:
            return ptr + (r - sva)
    raise ValueError("VA %#x not mapped" % va)

def running():
    try:
        out = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True).stdout
    except Exception:
        return None
    # ⚠ the mod exes were renamed AoWz*/AoWzEd on 2026-09-09; a list that stops at AoW/AoWCompat/
    # AoWDevEd misses the process actually holding the lock. Single source: zigexe.LOCKING_PROCESSES.
    for name in zigexe.LOCKING_PROCESSES:
        if (name + ".exe").lower() in out.lower():
            return name + ".exe"
    return None

def main():
    off = "--off" in sys.argv
    on  = "--on"  in sys.argv
    apply_ = "--apply" in sys.argv
    groups = [g for g in SITES if "--" + g in sys.argv]
    if off == on or not groups:
        sys.exit("usage: build_clogwin_gate.py (--off | --on) [--vis] [--drain] [--apply]\n"
                 "  --vis   : cave_drain's visibility decision (never show the window)\n"
                 "  --drain : cave_drain's hook in the paint pump\n"
                 "  --off = stock behaviour for that group; --on = ours.")

    print("combat-log exe pieces [%s] -> %s\n"
          % (", ".join(groups), "STOCK (off)" if off else "OURS (on)"))

    plan = []
    staged = {}
    for exe in EXES:
        p = os.path.join(GAME, exe)
        if not os.path.exists(p):
            print(f"  {exe:16s} MISSING -- skipped"); continue
        d = bytearray(open(p, "rb").read())
        secs = load_sections(d)
        for g in groups:
            va, stock, ours, desc = SITES[g]
            want, other = (stock, ours) if off else (ours, stock)
            o = foff(secs, va)
            cur = bytes(d[o:o + len(want)])
            if cur == want:
                print(f"  {exe:14s} {g:6s} @{va:08X}  [already]")
            elif cur == other:
                print(f"  {exe:14s} {g:6s} @{va:08X}  -> {want.hex(' ')}  [to change]")
                plan.append((p, exe, o, want, g))
                staged[p] = d
            else:
                sys.exit(f"ABORT: {exe} {g} @{va:08X} holds {cur.hex(' ')}\n"
                         f"  expected {stock.hex(' ')} (stock) or {ours.hex(' ')} (ours).\n"
                         "  The exe combat-log cave may have moved -- re-derive before using this.")

    if not plan:
        print("\n[= ] already in the requested state.")
        return 0
    if not apply_:
        print(f"\n[dry-run] {len(plan)} site(s) would change. Re-run with --apply.")
        return 0
    who = running()
    if who:
        sys.exit(f"[x] {who} is running. Close it and retry.")

    # No snapshot -- see the docstring. The opposite flag is the exact, verified inverse.
    for p, exe, o, want, g in plan:
        staged[p][o:o + len(want)] = want
    for p, d in staged.items():
        open(p, "wb").write(bytes(d))
    for p, exe, o, want, g in plan:
        chk = open(p, "rb").read()
        assert chk[o:o + len(want)] == want, f"readback mismatch in {exe} ({g})"
        print(f"  [ok] {exe:14s} {g:6s} written and verified")
    print("\n[done] Reverse with the opposite flag.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
