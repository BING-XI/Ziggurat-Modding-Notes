#!/usr/bin/env python3
r"""pbemday1 -- THE PBEM day-1 leader predicate, defined once for every site that tests it.

    map[+0x13A] == 2        the game type is PBEM
    map[+0x174] == 1        the day counter is 1 (TPlayerControl.NewDay +0x27 is its only
                            incrementer; it cannot move inside one TTurnPlayerControl.NewTurn)
    player[+0xA7] == 0      the player is human (vanilla's own test, 0x55756A3B / 0x557569F1)
    player[+0xD4] != 0      the player has a leader

Four sites evaluate it, in two scripts, and they must agree or a player gets two turn-1
grants or none, or two dialogs editing one leader (07-ui.md section 10.3):

    C_RAISE   build_pbem_leadersetup.py   raises the leader window (TTurnPlayerControl.NewTurn)
    C_GATE    build_pbem_leadersetup.py   defers the day-1 spell grant (TPlayerMagicControl.NewTurn)
    C_APPLY   build_pbem_leadersetup.py   runs the deferred grant (the window's OnDone)
    C_TURN1   build_hero_turn1_upgrade.py skips the leader's artificial level-up lag (THero.NewTurn)

Each site resolves `map` and `player` its own way; the proof that they are the same TPlayer is
in build_pbem_leadersetup.py's docstring ("ONE PLAYER, FOUR SITES").  This module only fixes
the TEST, so the four emitted copies cannot drift apart.  The caller guarantees both registers
are non-nil before the emitted code runs.

`asm()` returns keystone source lines using the callers' {LABEL} placeholder convention.
Needs no third-party packages and does no I/O.
"""

MAP_GAMETYPE = 0x13A
GAMETYPE_PBEM = 2
MAP_DAY = 0x174
PL_TYPE = 0xA7
PL_HUMAN = 0
PL_LEADER = 0xD4


def asm(map_reg, player_reg, fail):
    """Fall through when the predicate holds; jump to `fail` (a label text, e.g. "{RESUME}")
    when it does not.  Flags and nothing else are clobbered."""
    return [
        "cmp byte ptr [%s + 0x%x], %d" % (map_reg, MAP_GAMETYPE, GAMETYPE_PBEM),
        "jne " + fail,
        "cmp dword ptr [%s + 0x%x], 1" % (map_reg, MAP_DAY),
        "jne " + fail,
        "cmp byte ptr [%s + 0x%x], %d" % (player_reg, PL_TYPE, PL_HUMAN),
        "jne " + fail,
        "cmp dword ptr [%s + 0x%x], 0" % (player_reg, PL_LEADER),
        "je " + fail,
    ]
