#!/usr/bin/env python3
"""build_herodlg_columns.py -- Hero level-up dialog: 5 category columns (10 lists) instead of one.

Splits the single "Upgrades" list into five category columns, each keeping its own separate Cost
column -- 10 list columns in total. Categories are defined in `herodlg_cats.py` (the game has no
category data of its own). This script also owns the dialog's overall size and therefore
SUPERSEDES `build_herodlg_tall.py`.

  Wayfaring 27 | Resistances 18 | Melee 21 | Ranged 20 | Magic 16   (102 abilities categorised)
  (counts drift as abilities are added -- `python build_scripts/herodlg_cats.py` prints the live
  ones. They no longer size the dialog: see "How tall" below.)

⚠ RE-RUN --apply AFTER ANY EDIT TO herodlg_cats.py. That file is only the source; the 256-byte
  lookup table lives in the two executables and is written here by `exe.wr(D["cattbl"], ...)`.
  An edit there with no --apply here leaves the old table live and the ability silently lands in
  DEFAULT_CAT (Magic). Caught by QA on 2026-08-27 for build_shield.py's id 176.

## How tall -- height buys LIST ROWS and nothing else

    height = FURNITURE_H + ROW_H * rows  =  389 + 17 * rows      (default 8 rows -> 525)

389 px of the dialog is fixed regardless of how many abilities are offered: 53 title knotwork,
224 box A (portrait, banner, the six stat rows and their spinners, skill points, Current
Abilities), 8 gap, 47 box B header (Remove/Add/Done/Cancel + the five sort headers), 4 pad,
45 bottom knotwork band, 8 list border. The constant is derived from those in one place and
cross-checked against layout()'s own arithmetic, so it cannot drift.

⚠ **Sizing to the static category counts is obsolete.** Until 2026-09-10 the dialog was 860 px
for 27 rows so that the tallest category (Wayfaring, 27) never scrolled. `build_heroskill_race.py`
then went live and a hero is offered ~16-22 of the 102 abilities -- ~3-5 per column, so 22 rows
per column were empty. Vanilla's own list depth is 5 rows (its single Upgrades list was
WinHeight 107). Measured against the live race table, the chance that at least one of the five
columns overflows and has to be scrolled is ~50% at 5 rows (worst race, Undead), 8.7% at 7 and
**2.7% at 8**, which is the current default. Overflow scrolls -- it never drops entries -- because
`cave_setfmax` drives all five scrollbars off `GetCount()-1`.

⚠ The height only ever quantises to whole rows: "10% taller than 474" is 521.4, and 525 = 389 +
17*8 is the rung it lands on. Do not expect `--height 521` to give 521 -- the DFM will hold 521
but the list shows floor((521-389+8-8)/17) = 7 rows and the extra 4 px is dead space.

## How it works

The layout is a Delphi DFM in RCDATA `THEROUPGRADEDLG`. Column 0 reuses the existing
AvailableAbilities / Cost / SB / sort-buttons; columns 1-4 are **byte-clones** of those five
components with a new name, x-position, height and header caption. The clones deliberately keep
the ORIGINAL event-handler names (`AvailableAbilitiesChange`, `...SortClick`, `...MouseDown`,
`...SBChange`) -- those handlers are rewritten by caves to be Sender-aware, so **no method-table
extension is needed**. Sender arrives in EDX (Delphi register convention) and is live at every
hook site.

The grown DFM (+~17 KB) cannot stay in place, so it is relocated into a new RWX PE section
(`.hcol`) together with the caves and the category table. The original DFM bytes stay untouched in
`.rsrc`, which is what makes `--undo` a pure repoint.

⚠⚠ **`VScrollBar` is the one property a byte-clone must NOT inherit** (fixed 2026-09-10, after the
owner reported "the wheel only works in some of these columns" and "the costs aren't scrolling
alongside the names" -- ONE defect, two symptoms). Vanilla hangs the scrollbar off the **Cost**
list, never the name list: `AvailableAbilitiesCost.VScrollBar = AvailableAbilitiesSB`, and the
name list is driven instead by the form's `AvailableAbilitiesSBChange`. Cloned verbatim, all four
new Cost lists pointed at **column 0's** bar, and in `aowInt.dpl` that one reference drives three
different things (all verified by disassembly, addresses in the `cave_setfmax` note below):

  * `TAOWListBox.SetSize` is what **positions, sizes, shows and feeds** a bar -- SetFMin/FMax/FPos/
    FNum, `SetLeft(list.left+list.width-bar.width)`, `SetTop`, `SetHeight`, `SetVisible`, priority
    +1, and `VanishWhenFull`. It only ever does that for the list that REFERENCES the bar, so
    `AvailSB2..5` were never positioned and never made visible (their DFM `Visible` is False --
    vanilla's is too, and column 0's bar is shown by exactly this path), while
    `AvailableAbilitiesSB` was yanked to whichever cost list ran SetSize last.
  * `TAOWListBox.Update` force-assigns `ListOff := VScrollBar.FPos`, so every scroll of columns 2-5
    was undone on the next repaint -- the "costs aren't scrolling" report.
  * `WheelScroll`'s case 1 (`build_wheel_aowint.py`) takes the hovered list's own `[lb+0x118]`
    before it ever tries the sibling search, so a notch over any cost column scrolled column 0.
    The wheel foundation itself is correct and needed no change; the name lists always worked
    because they have no bar and fall through to case 2's geometric sibling search.

`build_dfm()` asserts the wiring both ways: each cost list points at its own bar, and no name list
owns one (a name list that did would drag the bar to `name.left + 126 - 17`, on top of the Cost
column).

## ⚠⚠ THE STALE-SELECTION TRAP -- never cache which column the buttons act on

Fixed 2026-09-10, after "adding more than one level of a multilevel ability no longer works" and
"after an Add and a Remove, Add won't re-add it until I deselect, select something else and
reselect". ONE bug, and it had nothing to do with scrollbars.

    THeroUpgradeDlg.AddAbilityBtnClick @0x004470D0 decides what to add from ONE number:
        0x004470E3  call cave_activelist        -> esi = the column's name list
        0x004470E9  mov  edi,[esi+0x120]        -> that list's `Selected`
        0x004470EF  cmp  edi,-1 / je            -> -1 means "do nothing"

`cave_activelist` used to answer from a cached `activecol`, and `cave_fill` -- the head of
`PopulateLists @0x446954`, which Add AND Remove both call -- reset that cache to 0 on every
repopulate. The refill clears each list's **Strings**, never the listbox, so `Selected` stays put:
after any Add the true selection is still sitting in column c while the cache says column 0.

The cache could not be repaired by the obvious user action, which is why it looked like a dead
button rather than a wrong one. `TAOWListBox.CheckMouseDown @0x598171C4` fires OnChange only when
the clicked row DIFFERS from `Selected`:

    59817300  cmp  ebx,[esi+0x120]
    59817306  je   -> no OnChange

so clicking the row that is already highlighted is a no-op, `cave_change` never runs, and Add
keeps reading column 0 -- whose `Selected` is -1, because `cave_change` cleared it on the way out.
Only a click that CHANGES a selection (deselect, or a different row) rebuilt the cache.

Multi-level abilities are the sharp case: `TMultiLevelAbility.CanExpand @0x55765308` keeps the row
listed while `level < [ability+0x28]`, so the ONLY route from Vision II to Vision III is a second
Add against a row the hero already partly owns -- exactly the Add that read the wrong column.
Single-level abilities merely felt awkward, because the row leaves the list anyway.

**The rule: derive the active column, do not cache it.** `cave_activelist` now scans the five name
lists for the one whose `Selected` is not -1. That is exact by construction -- the DFM ships every
list `Selected = -1`, `cave_change` clears the four it did not land on, and a repopulate leaves the
field alone -- and it needs no OnChange to have fired, so the CheckMouseDown latch stops mattering.
`cave_setfmax` drops a selection the refill pushed out of range, which is the one thing preserving
`Selected` across a repopulate would otherwise break.

⚠ `cave_setfmax`'s scroll sync (added the same day) was NOT the cause and was kept. It writes
`[bar+0x148]`, `[bar+0xA4]` and each list's `[+0x15C]` ListOff -- never `Selected`, never
`activecol`. Proved by diffing `.hcol`'s code block in the 2026-09-09 staged exe against the live
one: the sync is the ONLY code difference, and `mov dword [activecol],0` is present in both.
⚠ The per-race offer gate is not the cause either: `build_heroskill_race.py` keys its hash on
`[ebx+0x1D8]`, the ORIGINAL hero, so unit id and level cache cannot drift while the dialog is open
and an ability that passed for level II still passes for level III.

⚠ **`.hcol` HAS FIVE OTHER TENANTS**, the lowest being `build_heroskill_race.py` at `0x00628000`.
This layout allocates upward from `SEC_VA 0x612000` and currently tops out at `0x00624200`, so
there is ~16 KB of headroom -- and `plan()`'s `assert D["code"] + len(code) < SQUATTER_FLOOR`
(not the section end, which would not catch a squatter collision) is what enforces it. Full list
at `SQUATTER_FLOOR` below. `add_section()` returns early when `.hcol` exists, so an ordinary
re-apply here does not reallocate the section and the other tenants survive; only a rebuild after
`.hcol` was removed would clobber them.

⚠ **`apply_to()` zeroes `[SEC_VA, SQUATTER_FLOOR)` before writing the blob** -- exactly that
range, never a byte higher. Without it a blob that ever SHRINKS leaves the previous `cave_fill`'s
tail live above its new end, and those bytes can still present an `E9 <rel32> 90 | 3d 00 01 00 00`
for `build_heroskill_race.find_sites()` to match a second time.

⚠⚠ **THIS SCRIPT UNLINKS `build_heroskill_race.py`'s HOOK, AND RE-CHAINS IT.** `--apply`
regenerates `cave_fill` from source, which restores the vanilla `8b 45 f4 8b 40 0c` at the site
that script hooks (`cf_gate`, today `0x00623E5D`) and moves it -- the Magebane/Shield failure
mode, and silent. `relink_racegate()` therefore runs between `apply_to()` and `save()` and calls
`build_heroskill_race.relink_bytes()`, which re-locates the site by pattern and rewrites the
6-byte hook plus both of that cave's fixed tail jumps. It prints `re-chained` or `not installed`
on every run and never nothing, and a FAILED re-chain **raises before `save()`** so the exe on
disk is left untouched rather than shipped with the gate unlinked. `--undo` is deliberately NOT
re-chained: restoring the vanilla fill loop correctly leaves the gate cave inert.

New published fields (bound by the DFM reader once the field table is extended; instance size at
[VMT-0x1C] grows 480 -> 576 = 0x240; NEW_INSTSIZE below is authoritative):
    +0x1E0..0x1EC AvailAb2..5   +0x1F0..0x1FC AvailCost2..5   +0x200..0x20C AvailSB2..5
    +0x210..0x21C AvailSort2..5 +0x220..0x22C AvailCSort2..5

Hooks (`Ziggurat/AoWz.exe` + `Ziggurat/AoWzCompat.exe`, in lockstep; names from `zigexe.py`.
⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)
    0x446972..0x446A53  whole available-abilities fill loop -> cave_fill (distribute by category)
    0x446BB2..0x446BD1  SetFMax on one scrollbar            -> cave_setfmax (all five, then
                                                              re-clamp each bar, push its position
                                                              into BOTH of its lists, and drop a
                                                              Selected the refill left out of range)
    0x4468A0            sort the available pair             -> cave_sortall (all five, honours mode)
    0x447008 / 0x44701C list OnChange                       -> cave_change (Sender-aware)
    0x447030            scrollbar OnChange                  -> cave_sbchange (Sender-aware)
    0x4470E3            Add button reads the list           -> cave_activelist (the column whose
                                                              Selected is not -1; see the trap)
    0x4473EC / 0x4473FB info popup reads the list           -> `mov reg,edx` (use Sender directly)

Two base relocations (0x446995, 0x4469B8 -- the absolute `mov eax,[0x45DF78]` operands inside the
fill loop) fall in displaced bytes; they are set to type 0 and restored by --undo. The image is
not /DYNAMICBASE so they are never applied in practice, but stale relocs are not left behind.

## Usage

    (no args)                        verify the state of both exes
    --apply                          patch (an UNPATCHED exe is first snapshotted to
                                     backups/<exe>.pre-herodlgcolumns; a patched one is not)
    --apply --width W --height H     re-tune the size in place (default 960x525 = 8 list rows)
    --undo                           surgical restore: resource repoint, VMT fields, every hook
                                     site, and the relocs. The .hcol section is left (inert).
    --dis [name]                     disassemble the caves at their real VAs (all, or one by
                                     name substring) and exit -- writes nothing

Do NOT run `build_herodlg_tall.py` afterwards -- it will see an unrecognised slot and refuse,
which is the safe outcome. Use `--height` here instead.
"""
import argparse
import os
import struct
import shutil
import subprocess
import sys
import time

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dfm_edit
import zigexe                                      # mod binary names
import herodlg_cats as CATS
import build_herodlg_tall as TALL
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

EXES = list(zigexe.EXES)                          # AoWz.exe + AoWzCompat.exe
BACKUP_SUFFIX = ".pre-herodlgcolumns"
BACKUP_DIR = os.path.join(GAME, "backups")        # ⚠ never the game root -- rule 2026-09-03
SECNAME = b".hcol\0\0\0"
SEC_VA = 0x612000                 # first 0x1000-aligned VA past .tres (ends 0x611EE0)
SEC_SIZE = 0x1C000                # 112 KB: grown DFM (~72 KB) + field table + caves + tables

# ⚠ This section has FIVE squatters above us, none of which own a header entry -- they live in
# .hcol's zero tail because this script created the section. `SEC_VA + SEC_SIZE` (0x62E000) is the
# section end and does NOT protect them: growing our blob past 0x628000 silently overwrites the
# lot, and nothing would report it. Bound growth at the lowest squatter instead.
#   0x00628000  build_heroskill_race.py        (0x2000: code 0x628010, tails 0x628200/0x628205,
#                                               16x256 table 0x629000 ending at 0x0062A000)
#   0x0062A000  build_skylevel_ui.py           (0x200)
#   0x0062D000  build_unitwin_ability.py
#   0x0062D020  build_savedate_format.py       (ends 0x0062D079)
#   0x0062D100  build_powerleech_ui.py         (0x200)
# Measured 2026-09-10: our blob ends at 0x00624200, so this leaves ~15.5 KB of headroom.
# Canonical list: Zig notes/12-re-toolchain.md §6.2. Raise this only after moving the squatters.
SQUATTER_FLOOR = 0x00628000
DEFAULT_W = 960
NCOL = 5
LIST_W, COST_W, SB_W = 126, 46, 17

# ---- two-box layout -----------------------------------------------------------------------
# Box A ("StatePnl", new) = the hero as he is: portrait+banner, stats, Current Abilities.
# Box B ("UpgradePnl", reused) = the pickable listings, with Remove/Add/Done/Cancel as its header.
# Both are framed TAOWPanels of the same width, stacked, so no horizontal space is wasted.
FRAME_ILB = "IntGfxMod.GenericF"
FRAME_IDX = 88                    # GenericF set 88 = NGFrOut, a 3 px "outer" grouping frame
BOX_X = 26                        # left/right margin (the window frame itself is 22 px)
BOXA_Y, BOXA_H = 53, 224          # under the title knotwork
BOX_GAP = 8
BOXB_Y = BOXA_Y + BOXA_H + BOX_GAP
BAND_FROM_BOTTOM = 45             # bottom knotwork band + margin

# box A internals (relative to box A)
A_PAD = 4
A_TOPPNL = (4, 4, 365, 142)       # x, y, w, h -- portrait + name + "made a level" banner
A_STATS = (4, 150, 347, 70)       # the six stat rows, stacked under the portrait block
A_CURAB_X, A_CURAB_TOP, A_CURAB_BOT = 380, 19, 8
A_CURAB_COST_W = 60

# box B internals (relative to box B)
B_PAD = 4
B_BTN_Y, B_BTN_W = 4, 135         # the header button row
B_HDR_Y = 32                      # column sort-button headers
B_LIST_TOP, B_LIST_BOT = 47, 4

# ---- the vertical budget: height = FURNITURE_H + ROW_H * rows -------------------------------
# --height buys LIST ROWS AND NOTHING ELSE. Everything else on the dialog is fixed, so the
# height cannot go below FURNITURE_H no matter how few abilities are offered:
#     53  BOXA_Y            title knotwork above box A
#    224  BOXA_H            box A: portrait + "made a level" banner, the six stat rows with their
#                           spinners, the skill-points readout, Current Abilities (11 rows)
#      8  BOX_GAP
#     47  B_LIST_TOP        box B header: Remove/Add/Done/Cancel, then the five sort headers
#      4  B_LIST_BOT        box B bottom pad
#     45  BAND_FROM_BOTTOM  bottom knotwork band + margin
#      8  LIST_BORDER       a TAOWListBox's BorderHeight, 4 top + 4 bottom
#    ---
#    389
# Box A is rigid (its portrait block is 4+142 and its stat stack 150..220), so shortening the
# dialog below 389 + a few rows means restructuring box A, not re-tuning --height.
ROW_H = 17                        # TAOWListBox ItemHeight, read off the pristine DFM
LIST_BORDER = 8                   # BorderHeight 4 top + 4 bottom
FURNITURE_H = (BOXA_Y + BOXA_H + BOX_GAP + B_LIST_TOP + B_LIST_BOT
               + BAND_FROM_BOTTOM + LIST_BORDER)
MIN_ROWS = 3                      # below this the columns stop being usable as columns
# 8 rows (2026-09-10, owner's request: "about 10% taller"). 474 x 1.1 = 521.4 and the height
# quantises to whole rows, so 525 = 389 + 17*8 is the nearest rung. It is also where the chance
# that ANY of the five columns overflows and needs scrolling falls to 2.7% (5 rows was 50%).
# Vanilla's own list depth was 5 rows (WinHeight 107); see the table in §2.1a of Zig notes/07-ui.md.
DEFAULT_ROWS = 8
DEFAULT_H = FURNITURE_H + ROW_H * DEFAULT_ROWS       # 525

VMT = 0x4458C8
VMT_FIELDTABLE = VMT - 0x2C
VMT_INSTSIZE = VMT - 0x1C
ORIG_INSTSIZE = 480
ORIG_FIELDTABLE = 0x4458F0
ORIG_FIELDCOUNT = 96
NEW_INSTSIZE = 0x240              # 576 = 480 + 20 column fields + StatePnl + 3 knotwork bands
STATEPNL_OFF = 0x230              # box A's panel (referenced only by its children's AOWWindow,
                                  # but given a real field so the binding is not left to chance)
# purely decorative, referenced by nothing; given fields anyway so they bind like everything else
BAND_FIELDS = [("BCelt", 0x234, "TCelt"), ("MCeltL", 0x238, "TCeltL"), ("MCelt", 0x23C, "TCelt")]

DLG_OFF = 0x44                    # published field: the dialog's own AOW window
UPGRADEPNL_OFF = 0x74             # box B

# ---- geometry self-heal (see "Surviving a game-window resize") ------------------------------
# The three panels whose rects the engine's clamp-to-parent pass destroys, in the order they must
# be restored: the dialog first, then its two boxes (a child cannot be sized against a parent that
# is still wrong). Values come from layout(), so --width/--height stay authoritative.
# Left/Top for Dlg are deliberately NOT restored: it is awCenter/ahCenter, so ReAlign owns them.
GEOM_ROWS = 3                     # Dlg, StatePnl, UpgradePnl
CTL_W, CTL_H, CTL_L, CTL_T = 0x7C, 0x80, 0x84, 0x88
CTL_ALIGNED, CTL_SIZED = 0x2D, 0x2E   # zeroing both is the toolkit's "re-layout me" signal
CTL_CHILDREN = 0xD0               # Classes.TList: count at +8, item array at +4

COL_NAME  = [0x80, 0x1E0, 0x1E4, 0x1E8, 0x1EC]
COL_COST  = [0x98, 0x1F0, 0x1F4, 0x1F8, 0x1FC]
COL_SB    = [0x84, 0x200, 0x204, 0x208, 0x20C]
COL_SORT  = [0x9C, 0x210, 0x214, 0x218, 0x21C]
COL_CSORT = [0x94, 0x220, 0x224, 0x228, 0x22C]

GETCOUNT, GETABILITY = 0x4023CC, 0x4023D4
INTTOSTR = 0x4013AC
SETFMAX = 0x4031BC
SETINDEX, SETLISTOFF = 0x40365C, 0x403664

# aowInt.dpl instance fields the setfmax cave touches directly (verified by disassembling
# AoWListBox / AoWVScroll in Ziggurat/aowInt.dpl, 2026-09-10):
#   TAOWListBox.NumberVisible +0x11C   -- the row count TAOWListBox.Update @0x59817138 clamps
#                                         ListOff against, so it is the bound the bar must respect
#   TAOWScrollBar.FPos        +0x148   -- TAOWScrollBar.SetFPos @0x5980CA28 writes exactly this,
#                                         plus the dirty byte below; there is no other side effect,
#                                         which is why the cave inlines it instead of importing it
#   TAOWListBox.Selected      +0x120  -- the published property `Selected` reads this field
#                                        DIRECTLY (RTTI GetProc FF000120) and writes it through
#                                        TAOWListBox.SetIndex @0x598168B8. The pristine DFM sets
#                                        `Selected = -1` on every list, and the byte-clones
#                                        inherit it, so "nothing chosen" is -1 on all ten lists
#                                        from the moment the dialog is built.
#   TAOWControl "needs redraw" +0xA4  -- set to 0 by SetIndex, SetListOff and TAOWListBox.Update
#                                        whenever they change their field. It is a repaint flag
#                                        and carries no selection state.
LB_NUMVIS, SB_FPOS, CTL_DIRTY, LB_SEL = 0x11C, 0x148, 0xA4, 0x120
SORTFNS = [0x401B14, 0x401B1C, 0x401B24, 0x401B2C]   # nameAsc nameDesc costAsc costDesc
ABILITYCTRL = 0x45DF78
HERO = 0x1DC
SORTMODE = 0x1D4

FILL_LO, FILL_HI = 0x446972, 0x446A53
FMAX_LO, FMAX_HI = 0x446BB2, 0x446BD1
H_SORT = 0x4468A0
H_CHANGE = [0x447008, 0x44701C]
H_SBCHANGE = 0x447030
H_ADDLIST = 0x4470E3
H_MOUSE = [0x4473EC, 0x4473FB]
H_SORTCLICK = [0x447238, 0x447270]     # name-header click, cost-header click
RELOC_VAS = [0x446995, 0x4469B8]
CLICKSOUND = 0x455DFC                  # the button-click feedback the vanilla handlers make
CLICKSOUND_GLOBAL = 0x45A420

# verify-before-write: the vanilla bytes at every site we overwrite (read off the binary, not
# transcribed -- each string ends on an instruction boundary)
ORIG_AT = {
    FILL_LO:     bytes.fromhex("8b83800000008b80140100008b10ff5240"),
    FMAX_LO:     bytes.fromhex("8b83800000008b80140100008b10ff5214"),
    H_SORT:      bytes.fromhex("518b90d4010000"),
    H_CHANGE[0]: bytes.fromhex("8b90800000008b9220010000e83ffcffffc3"),
    H_CHANGE[1]: bytes.fromhex("8b90980000008b9220010000e82bfcffffc3"),
    H_SBCHANGE:  bytes.fromhex("538bd88b8384000000"),
    H_ADDLIST:   bytes.fromhex("8bb380000000"),
    H_MOUSE[0]:  bytes.fromhex("8b83800000"+"00"),
    H_MOUSE[1]:  bytes.fromhex("8bb38000000"+"0"),
    H_SORTCLICK[0]: bytes.fromhex("538bd8a120a445008b0033d2"),
    H_SORTCLICK[1]: bytes.fromhex("538bd8a120a445008b0033d2"),
}


# =================================================================== PE container
class Exe:
    def __init__(self, path):
        self.path = path
        self.d = bytearray(open(path, "rb").read())
        self.pe = struct.unpack_from("<I", self.d, 0x3C)[0]
        self.optsize = struct.unpack_from("<H", self.d, self.pe + 20)[0]
        self.opt = self.pe + 24
        self.sectbl = self.opt + self.optsize
        self.base = struct.unpack_from("<I", self.d, self.opt + 28)[0]

    @property
    def nsec(self):
        return struct.unpack_from("<H", self.d, self.pe + 6)[0]

    def sections(self):
        out = []
        for i in range(self.nsec):
            s = self.sectbl + 40 * i
            nm = bytes(self.d[s:s + 8]).rstrip(b"\0").decode("latin1")
            vsz, va = struct.unpack_from("<II", self.d, s + 8)
            rsz, raw = struct.unpack_from("<II", self.d, s + 16)
            out.append((nm, va, vsz, raw, rsz, s))
        return out

    def rva2off(self, rva):
        for _n, va, vsz, raw, rsz, _s in self.sections():
            if va <= rva < va + max(vsz, rsz):
                return raw + (rva - va)
        raise ValueError("RVA 0x%X unmapped" % rva)

    def off(self, va):
        return self.rva2off(va - self.base)

    def rd(self, va, n):
        o = self.off(va)
        return bytes(self.d[o:o + n])

    def wr(self, va, blob):
        o = self.off(va)
        self.d[o:o + len(blob)] = blob

    def u32(self, va):
        return struct.unpack_from("<I", self.d, self.off(va))[0]

    def w32(self, va, v):
        struct.pack_into("<I", self.d, self.off(va), v)

    def sec(self, name):
        for n, va, vsz, raw, rsz, s in self.sections():
            if n == name:
                return (va, vsz, raw, rsz, s)
        return None

    def dfm_entry(self):
        """-> (file offset of the resource data entry, dfm rva, dfm size)"""
        rsrc = struct.unpack_from("<I", self.d, self.opt + 112)[0]

        def entries(diroff):
            nn = struct.unpack_from("<H", self.d, diroff + 12)[0]
            ni = struct.unpack_from("<H", self.d, diroff + 14)[0]
            out = []
            for i in range(nn + ni):
                e = diroff + 16 + 8 * i
                nm, val = struct.unpack_from("<II", self.d, e)
                if nm & 0x80000000:
                    no = self.rva2off(rsrc + (nm & 0x7FFFFFFF))
                    ln = struct.unpack_from("<H", self.d, no)[0]
                    nm = self.d[no + 2:no + 2 + 2 * ln].decode("utf-16le")
                else:
                    nm = "#%d" % nm
                out.append((nm, val))
            return out

        rc = next(v for n, v in entries(self.rva2off(rsrc)) if n == "#10")
        ent = next(v for n, v in entries(self.rva2off(rsrc + (rc & 0x7FFFFFFF)))
                   if n == "THEROUPGRADEDLG")
        lang = entries(self.rva2off(rsrc + (ent & 0x7FFFFFFF)))[0][1]
        de = self.rva2off(rsrc + (lang & 0x7FFFFFFF))
        rva, size = struct.unpack_from("<II", self.d, de)
        return de, rva, size

    def add_section(self, name, va, size):
        if self.sec(name.rstrip(b"\0").decode("latin1")):
            return
        hdr_end = self.sectbl + 40 * (self.nsec + 1)
        assert hdr_end <= struct.unpack_from("<I", self.d, self.opt + 60)[0], \
            "no spare section-header slot inside SizeOfHeaders"
        filealign = struct.unpack_from("<I", self.d, self.opt + 36)[0]
        secalign = struct.unpack_from("<I", self.d, self.opt + 32)[0]
        raw = len(self.d)
        assert raw % filealign == 0, "EOF 0x%X not file-aligned" % raw
        s = self.sectbl + 40 * self.nsec
        rva = va - self.base                     # section headers hold RVAs, not VAs
        struct.pack_into("<8sIIII", self.d, s, name, size, rva, size, raw)
        struct.pack_into("<IIHHI", self.d, s + 24, 0, 0, 0, 0, 0xE0000060)
        self.d += bytearray(size)
        struct.pack_into("<H", self.d, self.pe + 6, self.nsec + 1)
        top = ((rva + size) + secalign - 1) // secalign * secalign
        struct.pack_into("<I", self.d, self.opt + 56, top)          # SizeOfImage

    def set_reloc_types(self, vas, newtype):
        """Set the type nibble of the reloc entries targeting `vas`. -> how many changed."""
        r = self.sec(".reloc")
        _va, vsz, raw, rsz, _s = r
        end = raw + min(vsz, rsz)
        want = set(vas)
        p, n = raw, 0
        while p + 8 <= end:
            page, blk = struct.unpack_from("<II", self.d, p)
            if blk < 8 or p + blk > end:
                break
            for q in range(p + 8, p + blk, 2):
                w = struct.unpack_from("<H", self.d, q)[0]
                if (self.base + page + (w & 0xFFF)) in want:
                    struct.pack_into("<H", self.d, q, (newtype << 12) | (w & 0xFFF))
                    n += 1
            p += blk
        return n


# =================================================================== DFM surgery
def enc_int(prop, val):
    return TALL.enc_int(prop, val)


def enc_ident(prop, val):
    return dfm_edit.shortstr(prop) + bytes([dfm_edit.IDENT]) + dfm_edit.shortstr(val)


def enc_str(prop, val):
    return dfm_edit.shortstr(prop) + bytes([dfm_edit.STR]) + dfm_edit.shortstr(val)


def enc_bool(prop, val):
    return dfm_edit.shortstr(prop) + bytes([dfm_edit.TRUE if val else dfm_edit.FALSE])


def comp_spans(w):
    starts = [(p[0].split("/")[-1], p[3]) for p in w.props if p[1] == "$class"]
    out = {}
    for i, (nm, s) in enumerate(starts):
        out[nm] = (s, starts[i + 1][1] if i + 1 < len(starts) else w.consumed - 1)
    return out


def comp_props(w):
    out = {}
    for path, nm, t, s, e, v in w.props:
        out.setdefault(path.split("/")[-1], {})[nm] = (s, e, t, v)
    return out


def obj_name_pos(blob):
    p = 1 if (blob[0] & 0xF0) == 0xF0 else 0
    assert p == 0 or not (blob[0] & 0x02), "ffChildPos component not handled"
    p2 = p + 1 + blob[p]                       # skip the class-name shortstring
    return p2, blob[p2 + 1:p2 + 1 + blob[p2]].decode("latin1")


def clone(dfm, span, props, newname, edits):
    """Copy a component, rename it, replace/append properties."""
    s, e = span
    blob = bytearray(dfm[s:e])
    npos, oldnm = obj_name_pos(blob)
    blob[npos:npos + 1 + len(oldnm)] = dfm_edit.shortstr(newname)
    delta = len(newname) - len(oldnm)
    reps, appends = [], b""
    for pname, nb in edits.items():
        if pname in props:
            ps, pe, _t, _v = props[pname]
            reps.append((ps - s + delta, pe - s + delta, nb))
        else:
            appends += nb
    out, pos = bytearray(), 0
    for ps, pe, nb in sorted(reps):
        assert pos <= ps, "overlapping clone edits on %s" % newname
        out += blob[pos:ps] + nb
        pos = pe
    out += blob[pos:]
    if appends:
        assert out[-2:] == b"\0\0", "unexpected component tail on %s" % newname
        out = out[:-2] + appends + out[-2:]
    return bytes(out)


def layout(width, height):
    """-> dict of every derived coordinate, so the geometry is stated once and asserted once."""
    L = {}
    L["box_w"] = width - 2 * BOX_X
    L["boxb_h"] = height - BAND_FROM_BOTTOM - BOXB_Y
    inner = L["box_w"] - 2 * B_PAD                      # usable width inside a box
    # --- box B: five column pairs, evenly pitched across the box
    pair = LIST_W + COST_W - 3                          # cost list overlaps the name list by 3 px
    L["pitch"] = (inner - pair) // (NCOL - 1)
    L["col_x"] = [B_PAD + c * L["pitch"] for c in range(NCOL)]
    L["list_h"] = L["boxb_h"] - B_LIST_TOP - B_LIST_BOT
    L["rows"] = (L["list_h"] - LIST_BORDER) // ROW_H
    # ties FURNITURE_H to the arithmetic above rather than restating it -- if a box constant moves
    # and FURNITURE_H is not updated with it, this fires instead of silently drifting.
    assert L["list_h"] == height - FURNITURE_H + LIST_BORDER, \
        "FURNITURE_H (%d) no longer matches the box constants" % FURNITURE_H
    # --- box B header buttons: Remove/Add at the left, Done/Cancel at the right
    L["btn_x"] = {"RemoveBtn": B_PAD,
                  "AddAbilityBtn": B_PAD + B_BTN_W + 10,
                  "Done": L["box_w"] - B_PAD - 2 * B_BTN_W - 10,
                  "CancelBtn": L["box_w"] - B_PAD - B_BTN_W}
    # --- box A: Current Abilities fills everything right of the portrait/stats stack
    L["a_cost_x"] = L["box_w"] - A_PAD - A_CURAB_COST_W
    L["a_name_w"] = L["a_cost_x"] + 3 - A_CURAB_X
    L["a_sb_x"] = L["box_w"] - A_PAD - SB_W
    L["a_list_h"] = BOXA_H - A_CURAB_TOP - A_CURAB_BOT
    L["a_rows"] = (L["a_list_h"] - LIST_BORDER) // ROW_H

    last = L["col_x"][-1] + pair
    assert last <= inner + B_PAD, (
        "%d columns need %d px but the box is only %d -- raise --width"
        % (NCOL, last, inner + B_PAD))
    assert L["btn_x"]["AddAbilityBtn"] + B_BTN_W < L["btn_x"]["Done"], \
        "header buttons overlap -- raise --width"
    assert L["a_name_w"] > 150, "Current Abilities column too narrow -- raise --width"
    # ⚠ This used to be `rows >= max(CATS.counts())`, i.e. "every ability in the tallest category
    # must fit with no scrolling" -- 27 rows, height 848 minimum. That premise died on 2026-09-10
    # when build_heroskill_race.py's per-race gate went live: a hero is now offered ~16-22 of the
    # 102 abilities, ~3-5 per column, so sizing the dialog to the STATIC category count reserved
    # 22 empty rows per column. The columns keep their own scrollbars (cave_setfmax drives all
    # five off GetCount()-1), so an over-full column scrolls rather than losing entries.
    assert L["rows"] >= MIN_ROWS, (
        "height %d leaves only %d list rows -- the fixed furniture alone is %d px, so %d rows "
        "needs --height %d" % (height, L["rows"], FURNITURE_H, MIN_ROWS,
                               FURNITURE_H + ROW_H * MIN_ROWS))
    return L


def geom_table(width, height):
    """-> the cave's {field offset, W, H, Left, Top} rows, in restore order (parents first).

    Same numbers build_dfm() writes into the DFM, derived from layout() rather than repeated, so
    --width/--height can never drift between the resource and the self-heal. Left/Top of -1 means
    "leave alone": Dlg is awCenter/ahCenter, so ReAlign owns its origin and writing one would
    fight the centring.
    """
    L = layout(width, height)
    rows = [(DLG_OFF, width, height, -1, -1),
            (STATEPNL_OFF, L["box_w"], BOXA_H, BOX_X, BOXA_Y),
            (UPGRADEPNL_OFF, L["box_w"], L["boxb_h"], BOX_X, BOXB_Y)]
    assert len(rows) == GEOM_ROWS
    return b"".join(struct.pack("<Iiiii", *r) for r in rows)


def build_dfm(pristine, width, height):
    """pristine DFM -> the two-box, five-column DFM (grown; caller relocates it)."""
    w = dfm_edit.walk(pristine)
    spans, props = comp_spans(w), comp_props(w)
    L = layout(width, height)
    # keyed by (component, property) so a later call overrides an earlier one instead of
    # producing two edits on the same byte span -- place() then stretch_v() both set the
    # vertical anchors, and last-write-wins is exactly what is wanted there.
    edits = {}

    def setp(comp, prop, blob):
        """Replace a property, or insert it if this component does not carry one yet."""
        if prop in props[comp]:
            s, e, _t, _v = props[comp][prop]
        else:
            s = e = spans[comp][1] - 2        # just before the end-of-props/end-of-children pair
        edits[(comp, prop)] = (s, e, blob)

    def place(comp, x, y, cw=None, ch=None, parent=None, aw="awLeft", ah="ahTop"):
        """Pin a control at an explicit position inside its parent, killing every percentage."""
        setp(comp, "WinLeft", enc_int("WinLeft", x))
        setp(comp, "WinTop", enc_int("WinTop", y))
        setp(comp, "Alignment.AlignWidth", enc_ident("Alignment.AlignWidth", aw))
        setp(comp, "Alignment.AlignHeight", enc_ident("Alignment.AlignHeight", ah))
        setp(comp, "Alignment.LeftOffset", enc_int("Alignment.LeftOffset", x))
        setp(comp, "Alignment.TopOffset", enc_int("Alignment.TopOffset", y))
        if cw is not None:
            setp(comp, "WinWidth", enc_int("WinWidth", cw))
        if ch is not None:
            setp(comp, "WinHeight", enc_int("WinHeight", ch))
        for pp in ("Alignment.LeftOffPercent", "Alignment.RightOffPercent",
                   "Alignment.TopOffPercent", "Alignment.BottomOffPercent",
                   "Alignment.WidthPercent", "Alignment.HeightPercent"):
            if pp in props[comp]:
                setp(comp, pp, enc_int(pp, 0))
        if parent:
            setp(comp, "AOWWindow", enc_ident("AOWWindow", parent))

    def stretch_v(comp, top, bottom, ch):
        """ahBoth: pin top and bottom inside the parent box so the height tracks the box."""
        setp(comp, "Alignment.AlignHeight", enc_ident("Alignment.AlignHeight", "ahBoth"))
        setp(comp, "Alignment.TopOffset", enc_int("Alignment.TopOffset", top))
        setp(comp, "Alignment.BottomOffset", enc_int("Alignment.BottomOffset", bottom))
        setp(comp, "WinTop", enc_int("WinTop", top))
        setp(comp, "WinHeight", enc_int("WinHeight", ch))

    def framed(comp):
        setp(comp, "ILFrame", enc_ident("ILFrame", FRAME_ILB))
        setp(comp, "ILIndexFrame", enc_int("ILIndexFrame", FRAME_IDX))

    # root designer-only props: delete (byte budget, same trick as the tall patch)
    for p in ("Left", "Top", "Height", "Width"):
        s, e, _t, _v = props["HeroUpgradeDlg"][p]
        edits[("HeroUpgradeDlg", p)] = (s, e, b"")

    setp("Dlg", "WinWidth", enc_int("WinWidth", width))
    setp("Dlg", "WinHeight", enc_int("WinHeight", height))

    # The bottom knotwork band follows the dialog height.  Vanilla filled it with three discrete
    # 27 px CeltDeco medallions (CeltL/M/R) flanking the Done/Cancel buttons; the top band instead
    # uses ONE wide TAOWImage (TCelt) which TILES the same medallion into a continuous swirl.
    # Now that the buttons have moved into box B, hide the three loose medallions and mirror the
    # top band exactly with a tiled BCelt (appended below) -- otherwise the tiling phase and the
    # fixed medallions collide and the band looks doubled.
    for comp in ("BCeltL", "CeltM", "CeltL", "CeltR"):
        setp(comp, "WinTop", enc_int("WinTop", height - 37))
    for comp in ("CeltM", "CeltL", "CeltR"):
        setp(comp, "Visible", enc_bool("Visible", False))

    # ---- box B: UpgradePnl reused as the framed listings box ------------------------------
    place("UpgradePnl", BOX_X, BOXB_Y, L["box_w"], L["boxb_h"])
    framed("UpgradePnl")
    # header row: Remove/Add at the left, Done/Cancel at the right, all inside the box
    for comp in ("RemoveBtn", "AddAbilityBtn", "Done", "CancelBtn"):
        place(comp, L["btn_x"][comp], B_BTN_Y, B_BTN_W, parent="UpgradePnl")
    # column 0 (the original controls); columns 1-4 are cloned further down
    x = L["col_x"][0]
    place("AvailableAbilitiesSort", x, B_HDR_Y, LIST_W - 1)
    setp("AvailableAbilitiesSort", "Text", enc_str("Text", CATS.CATEGORIES[0]))
    place("AvailableAbilityCostSort", x + LIST_W - 1, B_HDR_Y, COST_W - 2)
    place("AvailableAbilities", x, B_LIST_TOP, LIST_W)
    stretch_v("AvailableAbilities", B_LIST_TOP, B_LIST_BOT, L["list_h"])
    place("AvailableAbilitiesCost", x + LIST_W - 3, B_LIST_TOP, COST_W)
    stretch_v("AvailableAbilitiesCost", B_LIST_TOP, B_LIST_BOT, L["list_h"])
    setp("AvailableAbilitiesSB", "WinLeft",
         enc_int("WinLeft", x + LIST_W + COST_W - 3 - SB_W))
    setp("AvailableAbilitiesSB", "WinTop", enc_int("WinTop", B_LIST_TOP))
    setp("AvailableAbilitiesSB", "WinHeight", enc_int("WinHeight", L["list_h"]))

    # ---- box A: everything about the hero as he is, reparented into the new StatePnl ------
    place("TopPnl", A_TOPPNL[0], A_TOPPNL[1], A_TOPPNL[2], A_TOPPNL[3], parent="StatePnl")
    place("StatisicsPnl", A_STATS[0], A_STATS[1], A_STATS[2], A_STATS[3], parent="StatePnl")
    place("SelectedAbilitiesSort", A_CURAB_X, A_PAD, L["a_name_w"] - 1, parent="StatePnl")
    place("SelectedAbilitiesCostSort", L["a_cost_x"], A_PAD, A_CURAB_COST_W - 2,
          parent="StatePnl")
    place("SelectedAbilities", A_CURAB_X, A_CURAB_TOP, L["a_name_w"], parent="StatePnl")
    stretch_v("SelectedAbilities", A_CURAB_TOP, A_CURAB_BOT, L["a_list_h"])
    place("SelectedAbilitiesCost", L["a_cost_x"], A_CURAB_TOP, A_CURAB_COST_W,
          parent="StatePnl")
    stretch_v("SelectedAbilitiesCost", A_CURAB_TOP, A_CURAB_BOT, L["a_list_h"])
    setp("SelectedAbilitiesSB", "WinLeft", enc_int("WinLeft", L["a_sb_x"]))
    setp("SelectedAbilitiesSB", "WinTop", enc_int("WinTop", A_CURAB_TOP))
    setp("SelectedAbilitiesSB", "WinHeight", enc_int("WinHeight", L["a_list_h"]))
    setp("SelectedAbilitiesSB", "AOWWindow", enc_ident("AOWWindow", "StatePnl"))

    body = TALL.apply_edits(pristine[:w.consumed], list(edits.values()))

    # ---- appended clones: box A's panel, then columns 1..4 --------------------------------
    clones = clone(pristine, spans["UpgradePnl"], props["UpgradePnl"], "StatePnl", {
        "WinLeft": enc_int("WinLeft", BOX_X),
        "WinTop": enc_int("WinTop", BOXA_Y),
        "WinWidth": enc_int("WinWidth", L["box_w"]),
        "WinHeight": enc_int("WinHeight", BOXA_H),
        "Alignment.AlignWidth": enc_ident("Alignment.AlignWidth", "awLeft"),
        "Alignment.AlignHeight": enc_ident("Alignment.AlignHeight", "ahTop"),
        "Alignment.LeftOffset": enc_int("Alignment.LeftOffset", BOX_X),
        "Alignment.TopOffset": enc_int("Alignment.TopOffset", BOXA_Y),
        "Alignment.LeftOffPercent": enc_int("Alignment.LeftOffPercent", 0),
        "Alignment.RightOffPercent": enc_int("Alignment.RightOffPercent", 0),
        "Alignment.BottomOffPercent": enc_int("Alignment.BottomOffPercent", 0),
        "Alignment.BottomOffset": enc_int("Alignment.BottomOffset", 0),
        "ILFrame": enc_ident("ILFrame", FRAME_ILB),
        "ILIndexFrame": enc_int("ILIndexFrame", FRAME_IDX),
    })

    # ---- knotwork bands ------------------------------------------------------------------
    # BCelt: the bottom band, an exact mirror of the top's tiled TCelt.
    clones += clone(pristine, spans["TCelt"], props["TCelt"], "BCelt", {
        "Alignment.AlignHeight": enc_ident("Alignment.AlignHeight", "ahBottom"),
        "Alignment.BottomOffset": enc_int("Alignment.BottomOffset", 10),
        "WinTop": enc_int("WinTop", height - 37),
        "WinWidth": enc_int("WinWidth", width - 58),
    })
    # MCeltL/MCelt: the same band again behind box B's header row, so Remove/Add/Done/Cancel sit
    # on knotwork exactly the way vanilla's Done/Cancel sat on the bottom bar.  Priority 0/100 is
    # below the buttons' 1000, and the band shares the row's height, so this costs no extra space.
    band_y = B_BTN_Y - 2
    clones += clone(pristine, spans["TCeltL"], props["TCeltL"], "MCeltL", {
        "AOWWindow": enc_ident("AOWWindow", "UpgradePnl"),
        "Alignment.AlignWidth": enc_ident("Alignment.AlignWidth", "awLeft"),
        "Alignment.AlignHeight": enc_ident("Alignment.AlignHeight", "ahTop"),
        "Alignment.LeftOffset": enc_int("Alignment.LeftOffset", B_PAD),
        "Alignment.TopOffset": enc_int("Alignment.TopOffset", band_y),
        "WinLeft": enc_int("WinLeft", B_PAD),
        "WinTop": enc_int("WinTop", band_y),
        "WinWidth": enc_int("WinWidth", L["box_w"] - 2 * B_PAD),
    })
    clones += clone(pristine, spans["TCelt"], props["TCelt"], "MCelt", {
        "AOWWindow": enc_ident("AOWWindow", "UpgradePnl"),
        "Alignment.AlignWidth": enc_ident("Alignment.AlignWidth", "awLeft"),
        "Alignment.AlignHeight": enc_ident("Alignment.AlignHeight", "ahTop"),
        "Alignment.LeftOffset": enc_int("Alignment.LeftOffset", B_PAD + 6),
        "Alignment.TopOffset": enc_int("Alignment.TopOffset", band_y),
        "WinLeft": enc_int("WinLeft", B_PAD + 6),
        "WinTop": enc_int("WinTop", band_y),
        "WinWidth": enc_int("WinWidth", L["box_w"] - 2 * B_PAD - 12),
        # higher Priority draws on top (vanilla: Done=250 sits over CeltM=100 over BCeltL=0).
        # TCelt's inherited 100 would TIE with RemoveBtn's 100, so drop the band below them all.
        "Priority": enc_int("Priority", 1),
    })

    for c in range(1, NCOL):
        x, n = L["col_x"][c], c + 1

        def geom(dx, cw, ch=None, vstretch=False, _x=x):
            g = {
                "WinLeft": enc_int("WinLeft", _x + dx),
                "WinWidth": enc_int("WinWidth", cw),
                "Alignment.AlignWidth": enc_ident("Alignment.AlignWidth", "awLeft"),
                "Alignment.LeftOffset": enc_int("Alignment.LeftOffset", _x + dx),
                "Alignment.LeftOffPercent": enc_int("Alignment.LeftOffPercent", 0),
                "Alignment.RightOffPercent": enc_int("Alignment.RightOffPercent", 0),
            }
            if ch is not None:
                g["WinHeight"] = enc_int("WinHeight", ch)
            if vstretch:
                g["Alignment.AlignHeight"] = enc_ident("Alignment.AlignHeight", "ahBoth")
                g["Alignment.TopOffset"] = enc_int("Alignment.TopOffset", B_LIST_TOP)
                g["Alignment.BottomOffset"] = enc_int("Alignment.BottomOffset", B_LIST_BOT)
                g["WinTop"] = enc_int("WinTop", B_LIST_TOP)
            else:
                g["WinTop"] = enc_int("WinTop", B_HDR_Y)
                g["Alignment.TopOffset"] = enc_int("Alignment.TopOffset", B_HDR_Y)
            return g

        clones += clone(pristine, spans["AvailableAbilities"], props["AvailableAbilities"],
                        "AvailAb%d" % n, geom(0, LIST_W, L["list_h"], True))
        # ⚠⚠ THE ONE PROPERTY A BYTE-CLONE MUST NOT INHERIT: `VScrollBar`.
        # Vanilla hangs the bar off the COST list, not the name list (`AvailableAbilitiesCost.
        # VScrollBar = AvailableAbilitiesSB`; the name list has none and is driven by the form's
        # SBChange handler). Cloned verbatim, all four new cost lists pointed at COLUMN 0's bar,
        # which is a correctness bug on three separate paths -- see the note above `cave_setfmax`.
        cg = geom(LIST_W - 3, COST_W, L["list_h"], True)
        cg["VScrollBar"] = enc_ident("VScrollBar", "AvailSB%d" % n)
        clones += clone(pristine, spans["AvailableAbilitiesCost"],
                        props["AvailableAbilitiesCost"], "AvailCost%d" % n, cg)
        clones += clone(pristine, spans["AvailableAbilitiesSB"], props["AvailableAbilitiesSB"],
                        "AvailSB%d" % n, {
                            "WinLeft": enc_int("WinLeft", x + LIST_W + COST_W - 3 - SB_W),
                            "WinTop": enc_int("WinTop", B_LIST_TOP),
                            "WinHeight": enc_int("WinHeight", L["list_h"])})
        s = geom(0, LIST_W - 1)
        s["Text"] = enc_str("Text", CATS.CATEGORIES[c])
        clones += clone(pristine, spans["AvailableAbilitiesSort"],
                        props["AvailableAbilitiesSort"], "AvailSort%d" % n, s)
        clones += clone(pristine, spans["AvailableAbilityCostSort"],
                        props["AvailableAbilityCostSort"], "AvailCSort%d" % n,
                        geom(LIST_W - 1, COST_W - 2))

    assert body[-1:] == b"\x00", "unexpected DFM tail"
    out = body[:-1] + clones + b"\x00"

    w2 = dfm_edit.walk(out)
    assert w2.consumed == len(out), "DFM desync: consumed %d of %d" % (w2.consumed, len(out))
    got = comp_spans(w2)
    assert "StatePnl" in got, "box A panel missing"
    for c in range(1, NCOL):
        for pre in ("AvailAb", "AvailCost", "AvailSB", "AvailSort", "AvailCSort"):
            assert "%s%d" % (pre, c + 1) in got, "clone %s%d missing" % (pre, c + 1)
    # ⚠ Each column must own its bar. Cloned verbatim they all pointed at column 0's, which broke
    # the wheel (the hovered cost list handed WheelScroll the wrong bar), left columns 2-5's own
    # bars invisible and unpositioned (TAOWListBox.SetSize is what shows and places a bar, and it
    # only ever does that for the list that REFERENCES it), and let TAOWListBox.Update drag every
    # cost list back to column 0's offset. Assert it rather than trusting the clone edits.
    p2 = comp_props(w2)
    want = dict(AvailableAbilitiesCost="AvailableAbilitiesSB",
                **{"AvailCost%d" % (c + 1): "AvailSB%d" % (c + 1) for c in range(1, NCOL)})
    for lst, bar in want.items():
        assert p2[lst].get("VScrollBar", (0, 0, 0, None))[3] == bar, \
            "%s.VScrollBar is %r, must be %s" % (lst, p2[lst].get("VScrollBar"), bar)
    for lst in ["AvailableAbilities"] + ["AvailAb%d" % (c + 1) for c in range(1, NCOL)]:
        assert "VScrollBar" not in p2[lst], (
            "%s must NOT own the bar: TAOWListBox.SetSize would move it to that list's right edge "
            "(list.left + list.width - bar.width), i.e. on top of the Cost column" % lst)
    return out


# =================================================================== field table
def build_field_table(exe):
    ft = ORIG_FIELDTABLE
    cnt = struct.unpack_from("<H", exe.d, exe.off(ft))[0]
    classtab = struct.unpack_from("<I", exe.d, exe.off(ft + 2))[0]
    assert cnt == ORIG_FIELDCOUNT, "field table already altered (count %d)" % cnt
    p, donor = ft + 6, {}
    for _ in range(cnt):
        off_ = struct.unpack_from("<I", exe.d, exe.off(p))[0]
        cls = struct.unpack_from("<H", exe.d, exe.off(p + 4))[0]
        ln = exe.d[exe.off(p + 6)]
        nm = bytes(exe.d[exe.off(p + 7):exe.off(p + 7) + ln]).decode("latin1")
        donor[nm] = cls
        p += 7 + ln
    orig = exe.rd(ft, p - ft)
    new = b""
    for c in range(1, NCOL):
        for pre, offs, src in (("AvailAb", COL_NAME, "AvailableAbilities"),
                               ("AvailCost", COL_COST, "AvailableAbilitiesCost"),
                               ("AvailSB", COL_SB, "AvailableAbilitiesSB"),
                               ("AvailSort", COL_SORT, "AvailableAbilitiesSort"),
                               ("AvailCSort", COL_CSORT, "AvailableAbilityCostSort")):
            new += struct.pack("<IH", offs[c], donor[src]) + \
                dfm_edit.shortstr("%s%d" % (pre, c + 1))
    new += struct.pack("<IH", STATEPNL_OFF, donor["UpgradePnl"]) + dfm_edit.shortstr("StatePnl")
    for nm, off_, src in BAND_FIELDS:
        new += struct.pack("<IH", off_, donor[src]) + dfm_edit.shortstr(nm)
    return struct.pack("<HI", cnt + 21 + len(BAND_FIELDS), classtab) + orig[6:] + new


# =================================================================== caves
def cave_sources(D, LBL):
    """-> ordered [(name, asm source)]. Caves are assembled one at a time at their exact VA.
    `LBL` supplies the VAs of caves that other caves call; `assemble()` runs two passes because
    a call is a fixed 5 bytes either way, so the second pass converges."""
    cn, cc, sb = D["colname"], D["colcost"], D["colsb"]
    return [
        # --------------------------------------------------------------- geometry self-heal
        # Runs on every open, from the head of cave_fill. Why it is needed: when the game window
        # is made small enough that the manager's client area no longer holds this dialog, the
        # engine's clamp-to-parent pass rewrites the rects IN PLACE -- any axis that overflows
        # gets offset 0 and the parent's full extent -- and nothing ever puts them back, so the
        # dialog stays mangled after the window is enlarged again. Measured live 2026-08-07 at a
        # 640x432 client: Dlg 960x860 -> 640x432, UpgradePnl 908x530@26,285 -> 640x432@0,0,
        # StatePnl 908x224@26,53 -> 640x224@0,53 (its bottom, 277, still fitted, so its Top and
        # Height survived -- which is what put box A inside box B on screen).
        #
        # Restoring the three panel rects is enough: everything else is anchored and recomputes.
        # The ahBoth lists were already doing correct arithmetic against the wrong box.
        #
        # ⚠ That measurement was at the old 860 px height; the table is generated by layout(), so
        # it tracks --height with no edit. Per-axis verdict at a 640x432 client, current 960x525:
        #   Dlg         960x525          both axes overflow -> healed (Left/Top -1, ReAlign owns)
        #   StatePnl    908x224@26,53    26+908=934 > 640 horizontal clamped; bottom 277 <= 432 ok
        #   UpgradePnl  908x195@26,285   934 > 640 AND bottom 285+195 = 480 > 432 -> BOTH clamped
        # ⚠ UpgradePnl's vertical axis is clamped again at 525. It was clamped at 860, briefly was
        # not at 474 (bottom 429 <= 432), and is at 525. The heal writes W/H/L/T unconditionally
        # for all three rows, so it covers the axis either way -- but this is why the heal is
        # load-bearing again for that panel and not merely a superset.
        # ebx = the form. eax/ecx/edx/esi/edi are free here; ebp must be preserved (cave_fill
        # uses [ebp-0x10] and [ebp-0x0c] further down).
        ("cave_geom", f"""
    push esi
    push edi
    mov esi, {D['geom']}
    mov edi, {GEOM_ROWS}
cg_row:
    mov eax, [esi]
    mov eax, [ebx + eax]
    test eax, eax
    je cg_next
    mov ecx, [esi + 4]
    mov [eax + {CTL_W}], ecx
    mov ecx, [esi + 8]
    mov [eax + {CTL_H}], ecx
    mov ecx, [esi + 12]
    cmp ecx, -1
    je cg_nomove
    mov [eax + {CTL_L}], ecx
    mov ecx, [esi + 16]
    mov [eax + {CTL_T}], ecx
cg_nomove:
    mov byte ptr [eax + {CTL_ALIGNED}], 0
    mov byte ptr [eax + {CTL_SIZED}], 0
    mov edx, [eax + {CTL_CHILDREN}]
    test edx, edx
    je cg_next
    mov ecx, [edx + 8]
    test ecx, ecx
    jle cg_next
    mov edx, [edx + 4]
    test edx, edx
    je cg_next
cg_kid:
    mov eax, [edx]
    test eax, eax
    je cg_kidnext
    mov byte ptr [eax + {CTL_ALIGNED}], 0
cg_kidnext:
    add edx, 4
    dec ecx
    jnz cg_kid
cg_next:
    add esi, 20
    dec edi
    jnz cg_row
    pop edi
    pop esi
    ret
"""),
        # ⚠⚠ DO NOT RESET `activecol` HERE. See "THE STALE-SELECTION TRAP" in the module
        # docstring: this routine is `PopulateLists`, which Add and Remove BOTH call, and it
        # clears the STRINGS, never the listboxes -- so every list keeps its `Selected`. A reset
        # here left the cached column disagreeing with the only real selection on screen, and
        # `TAOWListBox.CheckMouseDown` will not fire OnChange for a re-click on the row that is
        # already selected, so nothing could ever repair it. That is what stopped a second Add
        # from reaching Vision III.
        ("cave_fill", f"""
    call {LBL['cave_geom']}
    xor esi, esi
cf_clr:
    mov eax, [{cn} + esi*4]
    mov eax, [ebx + eax]
    mov eax, [eax + 0x114]
    mov edx, [eax]
    call [edx + 0x40]
    mov eax, [{cc} + esi*4]
    mov eax, [ebx + eax]
    mov eax, [eax + 0x114]
    mov edx, [eax]
    call [edx + 0x40]
    inc esi
    cmp esi, {NCOL}
    jb cf_clr
    mov eax, [{ABILITYCTRL}]
    mov eax, [eax]
    mov eax, [eax + 0x80]
    call {GETCOUNT}
    dec eax
    test eax, eax
    jle cf_done
    mov [ebp - 0x10], eax
    mov esi, 1
cf_loop:
    mov eax, [{ABILITYCTRL}]
    mov eax, [eax]
    mov eax, [eax + 0x80]
    mov edx, esi
    call {GETABILITY}
    mov [ebp - 0x0c], eax
    test eax, eax
    je cf_next
    mov edx, [ebx + {HERO}]
    mov eax, [ebp - 0x0c]
    mov ecx, [eax]
    call [ecx + 0xc4]
    test al, al
    je cf_next
    mov eax, [ebp - 0x0c]
    test byte ptr [eax + 0x21], 1
    je cf_next
    mov eax, [ebp - 0x0c]
    mov eax, [eax + 0x0c]
    cmp eax, 0x100
    jb cf_id_ok
    movzx eax, byte ptr [{D['defcat']}]
    jmp cf_cat
cf_id_ok:
    movzx eax, byte ptr [{D['cattbl']} + eax]
cf_cat:
    mov [{D['curcat']}], eax
    mov eax, [ebp - 0x0c]
    mov eax, [eax]
    mov eax, [eax + 0xcc]
    mov [{D['calltmp']}], eax
    lea ecx, [ebp - 0x14]
    mov edx, [ebx + {HERO}]
    mov eax, [ebp - 0x0c]
    call [{D['calltmp']}]
    mov eax, [{D['curcat']}]
    mov eax, [{cn} + eax*4]
    mov eax, [ebx + eax]
    mov eax, [eax + 0x114]
    mov edx, [eax]
    mov edx, [edx + 0x38]
    mov [{D['calltmp']}], edx
    mov edx, [ebp - 0x14]
    mov ecx, esi
    call [{D['calltmp']}]
    mov edx, [ebx + {HERO}]
    mov eax, [ebp - 0x0c]
    mov ecx, [eax]
    call [ecx + 0xc8]
    lea edx, [ebp - 0x14]
    call {INTTOSTR}
    mov eax, [{D['curcat']}]
    mov eax, [{cc} + eax*4]
    mov eax, [ebx + eax]
    mov eax, [eax + 0x114]
    mov edx, [ebp - 0x14]
    mov ecx, [eax]
    call [ecx + 0x34]
cf_next:
    inc esi
    dec dword ptr [ebp - 0x10]
    jne cf_loop
cf_done:
    jmp {FILL_HI}
"""),
        # Runs at the tail of the same routine as cave_fill, i.e. after EVERY repopulate (open,
        # Add, Remove). ebx = the form; esi and edi are dead here (the fill loops finished), but
        # edi is callee-saved by the host function so the cave pushes it.
        #
        # Per column: SetFMax(count-1) on the bar -- then RE-CLAMP the bar and push its position
        # into BOTH lists, which is what keeps the Cost column on the same screen line as the
        # names. Why each piece is needed:
        #   * TAOWScrollBar.SetFMax @0x5980C9D8 does NOT touch FPos, so a Remove that shrinks a
        #     column leaves the thumb past the new end.
        #   * TAOWListBox.Update @0x59817138 force-assigns `ListOff := VScrollBar.FPos` and then
        #     clamps to `count - NumberVisible`. The Cost list has a bar so it gets both; the name
        #     list has none so Update returns at its `cmp [ebx+0x118],0` early exit and clamps
        #     NOTHING. That asymmetry -- vanilla's too -- is the one way name and cost can end up
        #     on different rows, and it is reachable with a single Remove.
        # Clamping here to `count - NumberVisible` (the list's own +0x11C, the same bound Update
        # uses -- NOT the bar's FNum, which is only correct once SetSize has pushed it) means
        # Update finds nothing left to clamp and both lists hold the identical offset.
        ("cave_setfmax", f"""
    push edi
    xor esi, esi
sf_l:
    mov eax, [{cn} + esi*4]
    mov eax, [ebx + eax]
    mov eax, [eax + 0x114]
    mov edx, [eax]
    call [edx + 0x14]                    /* eax = this column's item count */
    mov edi, eax
    /* Drop a selection the refill has invalidated. `cave_fill` clears the Strings, not the
       listbox, so `Selected` survives a repopulate -- which is deliberate (it is what lets a
       second Add reach the next level of a multi-level ability) but is only safe while the
       index is still in range. Adding a single-level ability drops that row from its column,
       and a selection sitting on the last row would then index one past the end:
       AddAbilityBtnClick feeds it straight to Strings.Objects[] with no SEH frame of its own. */
    mov eax, [{cn} + esi*4]
    mov eax, [ebx + eax]
    cmp dword ptr [eax + {LB_SEL}], edi
    jl sf_sel
    mov dword ptr [eax + {LB_SEL}], -1
    mov byte ptr [eax + {CTL_DIRTY}], 0
    mov eax, [{cc} + esi*4]
    mov eax, [ebx + eax]
    mov dword ptr [eax + {LB_SEL}], -1
    mov byte ptr [eax + {CTL_DIRTY}], 0
sf_sel:
    mov edx, edi
    dec edx
    mov eax, [{sb} + esi*4]
    mov eax, [ebx + eax]
    call {SETFMAX}
    mov eax, [{cc} + esi*4]              /* limit = count - NumberVisible, floored at 0 */
    mov eax, [ebx + eax]
    mov ecx, edi
    sub ecx, [eax + {LB_NUMVIS}]
    jns sf_lim
    xor ecx, ecx
sf_lim:
    mov eax, [{sb} + esi*4]
    mov eax, [ebx + eax]
    mov edi, [eax + {SB_FPOS}]
    cmp edi, ecx
    jle sf_hi
    mov edi, ecx
sf_hi:
    test edi, edi
    jns sf_lo
    xor edi, edi
sf_lo:
    mov [eax + {SB_FPOS}], edi           /* = TAOWScrollBar.SetFPos, inlined (no exe thunk) */
    mov byte ptr [eax + {CTL_DIRTY}], 0
    mov eax, [{cn} + esi*4]
    mov eax, [ebx + eax]
    mov edx, edi
    call {SETLISTOFF}
    mov eax, [{cc} + esi*4]
    mov eax, [ebx + eax]
    mov edx, edi
    call {SETLISTOFF}
    inc esi
    cmp esi, {NCOL}
    jb sf_l
    pop edi
    jmp {FMAX_HI}
"""),
        # sort ONE column (ebx = form, esi = column) by that column's own mode.
        # Mode values are vanilla's: 0 name asc, 1 name desc, 2 cost asc, 3 cost desc -- NOT 1..4.
        # (The first version subtracted 1 here, which made the Cost header sort by name instead.)
        ("cave_sortone", f"""
    push edi
    push ecx                       /* scratch slot: the secondary strings pointer */
    mov edi, [{D['colmode']} + esi*4]
    cmp edi, 4
    jb s1_ok
    xor edi, edi
s1_ok:
    cmp edi, 2
    jb s1_byname
    mov eax, [{cn} + esi*4]        /* sorting by cost: name list is the follower */
    mov ecx, [{cc} + esi*4]
    jmp s1_go
s1_byname:
    mov eax, [{cc} + esi*4]
    mov ecx, [{cn} + esi*4]
s1_go:
    mov eax, [ebx + eax]
    mov eax, [eax + 0x114]
    mov [esp], eax
    mov eax, [ebx + ecx]
    mov eax, [eax + 0x114]
    mov edx, esp
    xor ecx, ecx
    call [{D['sortfns']} + edi*4]
    pop ecx
    pop edi
    ret
"""),
        ("cave_sortall", f"""
    push ebx
    push esi
    mov ebx, eax
    xor esi, esi
sa_l:
    call {LBL['cave_sortone']}
    inc esi
    cmp esi, {NCOL}
    jb sa_l
    pop esi
    pop ebx
    ret
"""),
        # Header clicks: sort ONLY the clicked column. Sender (the button) arrives in EDX and
        # identifies the column; vanilla could hard-code the single list, we cannot.
        ("cave_sortclick_name", f"""
    push ebx
    push esi
    mov ebx, eax
    xor esi, esi
scn_find:
    mov eax, [{D['colsort']} + esi*4]
    cmp edx, [ebx + eax]
    je scn_found
    inc esi
    cmp esi, {NCOL}
    jb scn_find
    xor esi, esi
scn_found:
    mov eax, [{CLICKSOUND_GLOBAL}]
    mov eax, [eax]
    xor edx, edx
    call {CLICKSOUND}
    cmp dword ptr [{D['colmode']} + esi*4], 0
    jne scn_asc
    mov dword ptr [{D['colmode']} + esi*4], 1
    jmp scn_sort
scn_asc:
    mov dword ptr [{D['colmode']} + esi*4], 0
scn_sort:
    call {LBL['cave_sortone']}
    pop esi
    pop ebx
    ret
"""),
        ("cave_sortclick_cost", f"""
    push ebx
    push esi
    mov ebx, eax
    xor esi, esi
scc_find:
    mov eax, [{D['colcsort']} + esi*4]
    cmp edx, [ebx + eax]
    je scc_found
    inc esi
    cmp esi, {NCOL}
    jb scc_find
    xor esi, esi
scc_found:
    mov eax, [{CLICKSOUND_GLOBAL}]
    mov eax, [eax]
    xor edx, edx
    call {CLICKSOUND}
    cmp dword ptr [{D['colmode']} + esi*4], 2
    jne scc_asc
    mov dword ptr [{D['colmode']} + esi*4], 3
    jmp scc_sort
scc_asc:
    mov dword ptr [{D['colmode']} + esi*4], 2
scc_sort:
    call {LBL['cave_sortone']}
    pop esi
    pop ebx
    ret
"""),
        ("cave_change", f"""
    push ebx
    push esi
    push edi
    mov ebx, eax
    xor esi, esi
ch_find:
    mov eax, [{cn} + esi*4]
    cmp edx, [ebx + eax]
    je ch_found
    mov eax, [{cc} + esi*4]
    cmp edx, [ebx + eax]
    je ch_found
    inc esi
    cmp esi, {NCOL}
    jb ch_find
    jmp ch_out
ch_found:
    mov [{D['activecol']}], esi
    mov edi, [edx + 0x120]
    mov eax, [{cn} + esi*4]
    mov eax, [ebx + eax]
    mov edx, edi
    call {SETINDEX}
    mov eax, [{cc} + esi*4]
    mov eax, [ebx + eax]
    mov edx, edi
    call {SETINDEX}
    xor esi, esi
ch_clr:
    cmp esi, [{D['activecol']}]
    je ch_skip
    mov eax, [{cn} + esi*4]
    mov eax, [ebx + eax]
    mov edx, -1
    call {SETINDEX}
    mov eax, [{cc} + esi*4]
    mov eax, [ebx + eax]
    mov edx, -1
    call {SETINDEX}
ch_skip:
    inc esi
    cmp esi, {NCOL}
    jb ch_clr
ch_out:
    pop edi
    pop esi
    pop ebx
    ret
"""),
        ("cave_sbchange", f"""
    push ebx
    push esi
    push edi
    mov ebx, eax
    xor esi, esi
sc_find:
    mov eax, [{sb} + esi*4]
    cmp edx, [ebx + eax]
    je sc_found
    inc esi
    cmp esi, {NCOL}
    jb sc_find
    jmp sc_out
sc_found:
    mov edi, [edx + 0x148]
    mov eax, [{cn} + esi*4]
    mov eax, [ebx + eax]
    mov edx, edi
    call {SETLISTOFF}
    mov eax, [{cc} + esi*4]
    mov eax, [ebx + eax]
    mov edx, edi
    call {SETLISTOFF}
sc_out:
    pop edi
    pop esi
    pop ebx
    ret
"""),
        # Which column the Add button acts on. DERIVED, never cached: scan the five name lists
        # for the one whose `Selected` is not -1. `cave_change` guarantees at most one column
        # holds a selection (it clears the other four), the pristine DFM ships every list with
        # `Selected = -1`, and a repopulate leaves `Selected` alone -- so the scan is exact at
        # every point in the dialog's life, including immediately after an Add or a Remove.
        # Falling back to column 0 is safe precisely because its `Selected` is then -1 too, so
        # AddAbilityBtnClick stops at its own `cmp edi,-1 / je`.
        # ⚠ ECX is free at the call site (0x004470E3): the host loads it at 0x004470FC before
        # any read. ESI is the value the displaced `mov esi,[ebx+0x80]` produced. Flags are
        # dead -- the host's next instruction is its own `cmp edi,-1`.
        ("cave_activelist", f"""
    xor ecx, ecx
al_scan:
    mov esi, [{cn} + ecx*4]
    mov esi, [ebx + esi]
    cmp dword ptr [esi + {LB_SEL}], -1
    jne al_have
    inc ecx
    cmp ecx, {NCOL}
    jb al_scan
    mov esi, dword ptr [{cn}]
    mov esi, [ebx + esi]
    ret
al_have:
    mov dword ptr [{D['activecol']}], ecx
    ret
"""),
    ]


def assemble(D):
    """-> (code bytes for the whole block, {cave name: VA}). Exact, not inferred."""
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    names = [n for n, _ in cave_sources(D, _StubLabels(D["code"]))]
    labels = {n: D["code"] for n in names}
    blob = b""
    for _pass in range(2):                            # converges: a call is 5 bytes either way
        va, blob, out = D["code"], b"", {}
        for name, src in cave_sources(D, labels):
            out[name] = va
            code = bytes(ks.asm(src, va)[0])
            code += b"\xCC" * ((-len(code)) % 4)      # keep each cave 4-byte aligned
            blob += code
            va += len(code)
        if out == labels:
            return blob, labels
        labels = out
    return blob, labels


def show_caves(width, height, only=None):
    """--dis: disassemble the caves AS THEY WILL BE ASSEMBLED, at their real VAs.

    ⚠ Read the output. keystone silently encodes `push 0xFFFF` as `6A FF` = -1 and nothing else in
    the chain would notice; the project rule is that every cave is disassembled before it ships.
    Sourced from a pristine exe so it works whether or not the patch is installed.
    """
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    ref = _pristine_exe()
    _de, rva, size = ref.dfm_entry()
    cur = ref.rd(ref.base + rva, size)
    st, _h = TALL.state_of(cur)
    pristine = cur if st == "pristine" else TALL.untransform(cur)
    D, _dfm = plan(width, height, pristine)
    code, labels = assemble(D)
    order = sorted(labels.items(), key=lambda kv: kv[1])
    print("caves for %dx%d, block 0x%X..0x%X (%d B), floor 0x%X\n"
          % (width, height, D["code"], D["code"] + len(code), len(code), SQUATTER_FLOOR))
    for i, (name, va) in enumerate(order):
        end = order[i + 1][1] if i + 1 < len(order) else D["code"] + len(code)
        if only and only not in name:
            continue
        print("--- %s @ %08X (%d B) ---" % (name, va, end - va))
        for ins in cs.disasm(code[va - D["code"]:end - D["code"]], va):
            print("  %08X  %-22s %s %s" % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))
        print()


def _pristine_exe():
    """An Exe whose .rsrc still holds an un-relocated THEROUPGRADEDLG. Same candidate list, and
    the same reasoning, as main()'s search for the blanked fill/fmax ranges."""
    for cand in (os.path.join("Ziggurat upload", zigexe.VANILLA_EXE),
                 os.path.join("..", zigexe.VANILLA_EXE),
                 os.path.join("backups", zigexe.GAME_EXE + BACKUP_SUFFIX),
                 os.path.join("backups", zigexe.VANILLA_EXE + BACKUP_SUFFIX)):
        p = os.path.join(GAME, cand)
        if not os.path.exists(p):
            continue
        e = Exe(p)
        if state_of(e) == "off":
            return e
    raise SystemExit("  !! --dis needs an exe whose THEROUPGRADEDLG is still in .rsrc "
                     "(Ziggurat upload\\%s or the root vanilla exe)" % zigexe.VANILLA_EXE)


class _StubLabels(dict):
    """Placeholder label map for the sizing pass -- any cave name resolves to the block start."""
    def __init__(self, va):
        super().__init__()
        self.va = va

    def __missing__(self, _k):
        return self.va


# =================================================================== layout of .hcol
def plan(width, height, pristine):
    """-> (dict of VAs, dfm bytes, field table bytes placeholder resolved later)"""
    dfm = build_dfm(pristine, width, height)
    va = SEC_VA
    D = {}
    D["dfm"] = va
    va += (len(dfm) + 0xF) & ~0xF
    D["fieldtable"] = va
    va += 0x800                       # field table (96+20 entries, ~1.6 KB) -- sized generously
    D["cattbl"] = va;    va += CATS.TABLE_SIZE
    D["defcat"] = va;    va += 4
    D["curcat"] = va;    va += 4
    D["calltmp"] = va;   va += 4
    D["activecol"] = va; va += 4
    D["colname"] = va;   va += 4 * NCOL
    D["colcost"] = va;   va += 4 * NCOL
    D["colsb"] = va;     va += 4 * NCOL
    D["colsort"] = va;   va += 4 * NCOL
    D["colcsort"] = va;  va += 4 * NCOL
    D["colmode"] = va;   va += 4 * NCOL       # per-column sort mode (0 name asc .. 3 cost desc)
    D["colsbtbl"] = D["colsb"]
    D["sortfns"] = va;   va += 4 * 4
    D["geom"] = va;      va += 4 * 5 * GEOM_ROWS   # {field off, W, H, Left, Top} x 3 panels
    va = (va + 0xF) & ~0xF
    D["code"] = va
    return D, dfm


# =================================================================== state / apply
def state_of(exe):
    """Keyed on the VMT fields + where the resource points -- NOT on whether .hcol exists, since
    --undo deliberately leaves that section behind (inert) and must stay re-appliable."""
    ft = exe.u32(VMT_FIELDTABLE)
    inst = exe.u32(VMT_INSTSIZE)
    _de, rva, size = exe.dfm_entry()
    dfm_va = rva + exe.base
    if ft == ORIG_FIELDTABLE and inst == ORIG_INSTSIZE and dfm_va < SEC_VA:
        return "off"
    # NB: don't pin the exact instance size -- it changes whenever this script's layout gains a
    # control, and an older version of our own patch must still be recognised so --apply can
    # upgrade it in place (it undoes first, and undo restores the originals regardless).
    if ft != ORIG_FIELDTABLE and inst != ORIG_INSTSIZE and dfm_va >= SEC_VA:
        try:
            w = dfm_edit.walk(bytes(exe.rd(dfm_va, size)))
            dlg = comp_props(w)["Dlg"]
            return "on", dlg["WinWidth"][3], dlg["WinHeight"][3]
        except Exception:
            return "on", None, None
    return "unknown"


def kill_game():
    # ⚠ mod exes renamed AoWz*/AoWzEd 2026-09-09; list lives in zigexe.LOCKING_PROCESSES.
    for p in (n + ".exe" for n in zigexe.LOCKING_PROCESSES):
        subprocess.run(["taskkill", "/F", "/IM", p],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def save(exe):
    try:
        f = open(exe.path, "wb")
    except PermissionError:
        print("    locked -> killing AoW processes and retrying")
        kill_game()
        time.sleep(1.0)
        f = open(exe.path, "wb")
    with f:
        f.write(exe.d)


def apply_to(exe, width, height, verbose=True):
    # the pristine DFM: whatever is in .rsrc now, un-tall-patched if needed
    de, rva, size = exe.dfm_entry()
    cur = exe.rd(exe.base + rva, size)
    st, _h = TALL.state_of(cur)
    if st == "pristine":
        pristine = cur
    elif st == "patched":
        pristine = TALL.untransform(cur)
    else:
        raise SystemExit("  !! the DFM in .rsrc is neither pristine nor tall-patched -- aborting")

    D, dfm = plan(width, height, pristine)
    ft_blob = build_field_table(exe)
    assert D["cattbl"] - D["fieldtable"] >= len(ft_blob), "field table larger than its slot"
    code, labels = assemble(D)
    assert D["code"] + len(code) < SQUATTER_FLOOR, (
        "cave block reaches %#010x, at or past the first .hcol squatter %#010x "
        "(build_heroskill_race.py) -- see SQUATTER_FLOOR above"
        % (D["code"] + len(code), SQUATTER_FLOOR))

    exe.add_section(SECNAME, SEC_VA, SEC_SIZE)

    # ⚠⚠ ZERO THE WHOLE BLOB REGION BEFORE REWRITING IT. `add_section` returns early when
    # `.hcol` already exists, and `undo()` deliberately leaves the section populated, so without
    # this every --apply writes the new blob OVER the old one and anything the new blob is too
    # short to cover SURVIVES. Stale bytes here are not inert padding, they are the tail of the
    # previous `cave_fill`: they can still present an `E9 <rel32> 90 | 3d 00 01 00 00`, at which
    # point build_heroskill_race.find_sites() matches twice and aborts -- and until 2026-09-09
    # that abort was caught, printed as a warning, and the broken exe saved anyway.
    #
    # Bounded at SQUATTER_FLOOR and never beyond: every byte from there up belongs to one of the
    # five other tenants listed at the top of this file. [SEC_VA, SQUATTER_FLOOR) is ours alone
    # (verified 2026-09-10: the live blob ends at 0x00624200 and 0x00624200..0x00628000 is zero).
    assert SEC_VA < SQUATTER_FLOOR <= SEC_VA + SEC_SIZE
    exe.wr(SEC_VA, b"\0" * (SQUATTER_FLOOR - SEC_VA))

    # data
    exe.wr(D["dfm"], dfm)
    exe.wr(D["fieldtable"], ft_blob)
    exe.wr(D["cattbl"], CATS.lookup_table())
    exe.wr(D["defcat"], struct.pack("<I", CATS.DEFAULT_CAT))
    exe.wr(D["curcat"], b"\0" * 4)
    exe.wr(D["calltmp"], b"\0" * 4)
    exe.wr(D["activecol"], b"\0" * 4)
    exe.wr(D["colname"], struct.pack("<%dI" % NCOL, *COL_NAME))
    exe.wr(D["colcost"], struct.pack("<%dI" % NCOL, *COL_COST))
    exe.wr(D["colsb"], struct.pack("<%dI" % NCOL, *COL_SB))
    exe.wr(D["colsort"], struct.pack("<%dI" % NCOL, *COL_SORT))
    exe.wr(D["colcsort"], struct.pack("<%dI" % NCOL, *COL_CSORT))
    exe.wr(D["colmode"], b"\0" * (4 * NCOL))          # every column starts name-ascending
    exe.wr(D["sortfns"], struct.pack("<4I", *SORTFNS))
    exe.wr(D["geom"], geom_table(width, height))
    exe.wr(D["code"], code)

    # repoint the resource at the grown DFM
    struct.pack_into("<II", exe.d, de, D["dfm"] - exe.base, len(dfm))
    # class plumbing
    exe.w32(VMT_FIELDTABLE, D["fieldtable"])
    exe.w32(VMT_INSTSIZE, NEW_INSTSIZE)

    # hooks (verify-before-write)
    def hook(va, blob, fill_to=None):
        want = ORIG_AT[va]
        got = exe.rd(va, len(want))
        assert got == want, "byte mismatch at 0x%X: have %s want %s" % (va, got.hex(), want.hex())
        if fill_to:
            blob = blob + b"\xCC" * (fill_to - va - len(blob))
        exe.wr(va, blob)

    def jmp(frm, to):
        return b"\xE9" + struct.pack("<i", to - (frm + 5))

    hook(FILL_LO, jmp(FILL_LO, labels["cave_fill"]), FILL_HI)
    hook(FMAX_LO, jmp(FMAX_LO, labels["cave_setfmax"]), FMAX_HI)
    hook(H_SORT, jmp(H_SORT, labels["cave_sortall"]))
    for h in H_CHANGE:
        hook(h, jmp(h, labels["cave_change"]))
    hook(H_SBCHANGE, jmp(H_SBCHANGE, labels["cave_sbchange"]))
    # 6-byte `mov esi,[ebx+0x80]` -> call the helper (5) + nop
    hook(H_ADDLIST, b"\xE8" + struct.pack(
        "<i", labels["cave_activelist"] - (H_ADDLIST + 5)) + b"\x90")
    hook(H_MOUSE[0], b"\x8b\xc2" + b"\x90" * 4)     # mov eax,edx
    hook(H_MOUSE[1], b"\x8b\xf2" + b"\x90" * 4)     # mov esi,edx
    hook(H_SORTCLICK[0], jmp(H_SORTCLICK[0], labels["cave_sortclick_name"]))
    hook(H_SORTCLICK[1], jmp(H_SORTCLICK[1], labels["cave_sortclick_cost"]))

    n = exe.set_reloc_types(RELOC_VAS, 0)
    assert n == len(RELOC_VAS), "expected %d relocs in the fill loop, found %d" % (len(RELOC_VAS), n)

    if verbose:
        print("    DFM %d -> %d B at 0x%X; caves 0x%X..0x%X; instsize %d; %d relocs neutralised"
              % (size, len(dfm), D["dfm"], D["code"], D["code"] + len(code), NEW_INSTSIZE, n))
    return D


def relink_racegate(exe):
    """⚠⚠ Re-chain build_heroskill_race.py's gate, which apply_to() has just unlinked.

    `apply_to` regenerates `cave_fill` from source. That restores the vanilla
    `8b 45 f4 8b 40 0c` at the site the per-race offer gate hooks AND moves that site, so an
    installed gate silently stops running -- the Magebane/Shield failure mode. The other script
    owns the repair: it re-locates cf_gate / the resume / cf_next by the same pattern search and
    rewrites the 6-byte hook and both of its fixed tail jumps into our in-memory image, before
    save(). Both scripts therefore emit identical bytes and either apply order works.

    NEVER SILENT: prints "re-chained" or "not installed" on every run.

    ⚠⚠ AND NEVER PARTIAL. A failed re-chain RAISES, so main() never reaches save() and the exe on
    disk is untouched. It used to print the failure and carry on -- which shipped an exe whose
    gate was unlinked (the regenerated cave_fill having restored the vanilla bytes at cf_gate)
    while the cave, tails and 4 KB table still sat in `.hcol` looking installed. Loud is not the
    same as safe: the loud message scrolls past and the broken file stays.
    """
    try:
        import build_heroskill_race as RACEGATE
    except Exception as e:                                             # noqa: BLE001
        # No module, so no constants -- fall back to scanning the section for its magic. Present
        # means a gate we have just unlinked and cannot repair; absent means nothing to repair.
        _va, vsz, raw, rsz, _s = exe.sec(SECNAME.rstrip(b"\0").decode("latin1"))
        if b"RGT1" in bytes(exe.d[raw:raw + max(vsz, rsz)]):
            raise SystemExit(
                "  !! race-offer gate: build_heroskill_race.py failed to import (%s) and `.hcol`\n"
                "     carries its 'RGT1' magic, so the gate IS installed and has just been\n"
                "     unlinked. ABORTING before write -- %s is unchanged on disk. Fix the import\n"
                "     and re-run." % (e, os.path.basename(exe.path)))
        print("    race-offer gate: not installed (no 'RGT1' in %s; build_heroskill_race.py "
              "would not import either: %s)" % (SECNAME.rstrip(b"\0").decode("latin1"), e))
        return
    try:
        print("    " + RACEGATE.relink_bytes(exe.d))
    except SystemExit as e:                                            # its require() aborts
        raise SystemExit(
            "  !! race-offer gate: re-chain FAILED (%s)\n"
            "     ABORTING before write -- %s is unchanged on disk. Saving here would ship an\n"
            "     exe with the gate unlinked. Fix the cause and re-run, or run\n"
            "     `python build_heroskill_race.py --undo` first if the gate is not wanted."
            % (e, os.path.basename(exe.path)))


def undo(exe):
    """Surgical: repoint the resource back, restore VMT + every hook site + the relocs."""
    rsrc = exe.sec(".rsrc")
    de, _rva, _size = exe.dfm_entry()
    # the untouched original DFM is still sitting in .rsrc at its old offset
    orig_rva = rsrc[0] + (0xEE9B0 - rsrc[2])
    struct.pack_into("<II", exe.d, de, orig_rva, TALL.ORIG_SIZE)
    exe.w32(VMT_FIELDTABLE, ORIG_FIELDTABLE)
    exe.w32(VMT_INSTSIZE, ORIG_INSTSIZE)
    for va, blob in ORIG_AT.items():
        exe.wr(va, blob)
    exe.wr(FILL_LO, ORIG_FILL_BYTES)
    exe.wr(FMAX_LO, ORIG_FMAX_BYTES)
    exe.set_reloc_types(RELOC_VAS, 3)


# full original bytes of the two ranges we blank, needed by --undo
ORIG_FILL_BYTES = None
ORIG_FMAX_BYTES = None


def main():
    global ORIG_FILL_BYTES, ORIG_FMAX_BYTES
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", nargs="?", const="", metavar="CAVE",
                    help="disassemble the caves (optionally one, by name substring) and exit")
    ap.add_argument("--width", type=int, default=DEFAULT_W)
    ap.add_argument("--height", type=int, default=DEFAULT_H)
    args = ap.parse_args()
    if args.apply and args.undo:
        ap.error("--apply and --undo are mutually exclusive")
    if args.dis is not None:
        show_caves(args.width, args.height, args.dis or None)
        return

    # The two ranges this patch blanks are longer than the ORIG_AT fingerprints, so --undo (and
    # --apply, which undoes first) needs a pristine exe to copy them out of.
    #
    # ⚠ Do not assume `AoW.exe.pre-herodlgcolumns` is there; it was the sole reference when this
    # script was written and its loss turned --apply into a TypeError deep inside undo().
    # Candidates are tried in order and each one is BYTE-CHECKED against the ORIG_AT fingerprints
    # before being trusted — an old exe from a different build is fine for these two ranges but
    # must be proven, not assumed. The snapshot moved to `backups/` on 2026-09-09; the old game-
    # root path is still probed so an install that predates the move still resolves.
    #
    # ⚠ TWO NAMESPACES IN ONE LIST, and mixing them up is the whole point of the 2026-09-09
    # rename. `AoWz.exe*` entries are the MOD's own snapshots, under GAME = <root>\Ziggurat.
    # The `AoW.exe` entries are VANILLA and must keep that name: `Ziggurat upload\AoW.exe` is
    # the 2025-03-21 pristine exe (CLAUDE.md lists it as one of two files that must survive any
    # cleanup), and `..\AoW.exe` is the stock GOG exe at the game root, verified against the
    # hashdb. Both are legitimate donors for these two ranges; neither is ever written to.
    # Pre-rename snapshots (`backups\AoW.exe.pre-herodlgcolumns`) are still probed so an
    # install that predates the rename resolves.
    for cand in (os.path.join("backups", zigexe.GAME_EXE + BACKUP_SUFFIX),
                 os.path.join("backups", zigexe.VANILLA_EXE + BACKUP_SUFFIX),
                 zigexe.GAME_EXE + BACKUP_SUFFIX,
                 os.path.join("Ziggurat upload", zigexe.VANILLA_EXE),
                 os.path.join("..", zigexe.VANILLA_EXE)):
        p = os.path.join(GAME, cand)
        if not os.path.exists(p):
            continue
        r = Exe(p)
        try:
            fill = r.rd(FILL_LO, FILL_HI - FILL_LO)
            fmax = r.rd(FMAX_LO, FMAX_HI - FMAX_LO)
        except Exception:                                          # noqa: BLE001
            continue
        if fill[:len(ORIG_AT[FILL_LO])] == ORIG_AT[FILL_LO] \
                and fmax[:len(ORIG_AT[FMAX_LO])] == ORIG_AT[FMAX_LO]:
            ORIG_FILL_BYTES, ORIG_FMAX_BYTES = fill, fmax
            print("pristine reference for the blanked ranges: %s" % cand)
            break

    for name in EXES:
        path = os.path.join(GAME, name)
        exe = Exe(path)
        st = state_of(exe)
        if st == "off":
            print("%s: single Upgrades column (unpatched)" % name)
        elif st == "unknown":
            print("%s: UNKNOWN state -- not touching it" % name)
            continue
        else:
            rows = ("%d rows/column" % ((st[2] - FURNITURE_H) // ROW_H)
                    if isinstance(st[2], int) else "rows unknown")
            print("%s: %d category columns, dialog %sx%s (%s; furniture %d px + %d px/row)"
                  % (name, NCOL, st[1], st[2], rows, FURNITURE_H, ROW_H))

        if args.apply:
            if st != "off":
                # Always rebuild: the dialog size is NOT a fingerprint of the build (a layout or
                # taxonomy change alters the DFM at the same size), so short-circuiting on it
                # silently skipped real changes. Undo+reapply is idempotent and cheap.
                print("    already patched (%sx%s) -- undoing and rebuilding" % (st[1], st[2]))
                # --apply undoes first, so it needs the same reference --undo does. Without this
                # the missing bytes surfaced as `TypeError: object of type 'NoneType' has no
                # len()` from inside Exe.wr -- a real failure wearing a nonsense message.
                assert ORIG_FILL_BYTES, (
                    "no pristine exe to restore the fill loop from. --apply rebuilds by undoing "
                    "first, and the blanked ranges are longer than the ORIG_AT fingerprints. "
                    "Provide an unpatched exe as backups\\%s%s."
                    % (zigexe.GAME_EXE, BACKUP_SUFFIX))
                undo(exe)
            # ⚠ SNAPSHOT ONLY FROM A FILE PROVED UNPATCHED, and into backups/ -- never the game
            # root (rule 2026-09-03). Both halves were wrong here until 2026-09-09: the mint was
            # gated on "no backup file exists yet", so re-running --apply over an installed state
            # wrote a `.pre-herodlgcolumns` that CONTAINED the patched state, into the game root,
            # under a name that reads as authoritative. `st == "off"` is the positive test.
            bk = os.path.join(BACKUP_DIR, os.path.basename(path) + BACKUP_SUFFIX)
            if st != "off":
                print("    no backup taken (already patched -- a .pre-* of a patched file is a lie)")
            elif os.path.exists(bk):
                print("    backup already exists: %s" % bk)
            else:
                os.makedirs(BACKUP_DIR, exist_ok=True)
                shutil.copy2(path, bk)
                print("    backup -> %s" % bk)
            apply_to(exe, args.width, args.height)
            relink_racegate(exe)          # ⚠ must run BEFORE save(); see its docstring
            save(exe)
            print("    applied: %dx%d, columns %s"
                  % (args.width, args.height, " | ".join(CATS.CATEGORIES)))
        elif args.undo:
            if st == "off":
                print("    already unpatched")
                continue
            assert ORIG_FILL_BYTES, ("need a pristine reference (backups\\%s%s, "
                                     "Ziggurat upload\\AoW.exe, or the root vanilla AoW.exe) "
                                     "to restore the fill loop"
                                     % (zigexe.GAME_EXE, BACKUP_SUFFIX))
            undo(exe)
            save(exe)
            print("    restored (the inert .hcol section is left in place)")

    if not (args.apply or args.undo):
        print("\ndry run -- use --apply to patch, --undo to revert")


if __name__ == "__main__":
    main()
