#!/usr/bin/env python
r"""
heroicchoice.py -- the one definition of the heroic-medal choice data, shared by
build_heroicchoice_data.py (AoWEPACK.dpl: TUnitResource carries the options),
build_deved_heroicchoice.py (AoWDevEd.exe: the editor's Heroic 1-3 and Always tabs) and
build_heroicchoice.py (AoWEPACK.dpl + AoWz.exe: the game rules and the dialog).
Patches nothing on its own.

A unit type carries up to three OPTIONS.  Each option is one ability owner (the bundle: up to three
abilities, a multi-level ability counting once) plus six signed stat deltas.  An option is present
when its owner has any ability bit set or any of its deltas is non-zero.

It also carries one ALWAYS owner (owner's design 2026-10-20): abilities every heroic unit of the
type gains on becoming heroic, in addition to the option it takes.  No stat deltas.

TUnitResource instance, grown 0x54 -> INSTSIZE:
    +0x54 +0x58 +0x5C   option owners 1..3        (pfs tags OWNER_TAGS)
    +0x60 .. +0x71      option deltas, 6 per option, in STAT_FIELDS order (pfs tags STAT_TAG0 + i)
    +0x74               the Always owner          (pfs tag ALWAYS_TAG)
The deltas follow the base stats' own field order (+0x29..+0x2E), so delta i of an option adds to
the stat whose base byte is at +0x29 + i.

TUnit +0x3F (vanilla's dead padding byte) holds the unit's state, pfs/save tag UNIT_TAG:
    bits 0-1  the option taken, 1..3; 0 = none yet
    bit  6    the Always owner has been granted
    bit  7    the prompt has been raised at least once
"""

INSTSIZE_OLD = 0x54
INSTSIZE = 0x78
OWNER_OFFS = (0x54, 0x58, 0x5C)
STATS_OFF = 0x60
NSTATS = 6
STAT_FIELDS = ("Attack", "Defense", "Damage", "Hits", "Moves", "Resistance")   # +0x29..+0x2E
OWNER_TAGS = (0x21, 0x22, 0x23)
STAT_TAG0 = 0x24                     # option k, stat i -> STAT_TAG0 + 6*k + i  (0x24..0x35)
ALWAYS_OFF = 0x74
ALWAYS_TAG = 0x36
ALL_OWNER_OFFS = OWNER_OFFS + (ALWAYS_OFF,)
DELTA_MIN, DELTA_MAX = -10, 10       # editor spinner range
MAX_ABILITIES = 3                    # distinct abilities per option (editor cap; not the Always owner)
ALWAYS_TAB = 7                       # editor rank tab: None, Copper, Silver, Gold, Heroic 1-3, Always

DATA_SLOT = (0x558B0000, 0x558B0400)  # build_heroicchoice_data.py, exclusive
DATA_PRESENT = 0x558B00B0        # build_heroicchoice_data.py cave_present: EAX = TUnitResource -> AL = any option or Always

UNIT_STATE_OFF = 0x3F
UNIT_TAG = 0x24                      # free in the TUnit chain: 4-6/0x2F, 7-0xA, 0xD/0xE/0x1F/0x22/0x23, 0x31+
STATE_PICK_MASK = 0x03
STATE_ALWAYS = 0x40
STATE_ANNOUNCED = 0x80


def stat_off(k, i):
    return STATS_OFF + NSTATS * k + i


def stat_tag(k, i):
    return STAT_TAG0 + NSTATS * k + i


assert len(set(OWNER_TAGS) | {stat_tag(k, i) for k in range(3) for i in range(NSTATS)}
           | {ALWAYS_TAG}) == 3 + 18 + 1
assert stat_off(2, NSTATS - 1) < ALWAYS_OFF and ALWAYS_OFF + 4 == INSTSIZE and INSTSIZE % 4 == 0
assert not STATE_ALWAYS & (STATE_PICK_MASK | STATE_ANNOUNCED)
