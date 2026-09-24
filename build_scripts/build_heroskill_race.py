#!/usr/bin/env python3
r"""build_heroskill_race.py -- per-race probability gate on hero level-up ability offers.

TARGET: the canonical mod exes `Ziggurat\AoWz.exe` + `Ziggurat\AoWzCompat.exe`, in lockstep
(names from `zigexe.py`).  NOTHING in AoWEPACK.dpl is touched.
⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)

Each ability now has a per-race chance of appearing in the hero level-up dialog's Upgrades
columns.  Turn Undead is offered to High Men, Dark Elves and the Undead and to nobody else; an
Elf sees Archery and Forestry every time; a Dwarf sees Mountaineering and Cave Crawling every
time; most of the rest are a per-level coin flip weighted by race.  The percentages live in
`heroskill_races.py` -- that file is the authoring surface and is meant to be edited.

    (no args)   verify both exes: hook, cave, table checksum, chain integrity
    --apply     patch (or rewrite the cave in place over an existing install)
    --undo      surgical: restore the 6 displaced bytes, zero 0x00628000..0x0062A000
    --dis       capstone-disassemble the cave and print the table summary
    --show      alias for --dis

================================================================================
RNG -- PATTERN P4 DERIVED HASH  (12-re-toolchain.md 4.10)
================================================================================
Selection test, run top to bottom:

    Q1  the offered set is not streamed by any ReadWrite, but it IS player-visible state
        that must agree across a reopen -> not P3.  Continue.
    Q2  "must the same situation give the same answer on a LATER evaluation -- dialog
        reopen, save/reload?"  YES.  `PopulateLists @0x446954` re-runs on every Add and
        every Remove, so a drawn roll would re-shuffle the columns under the player's
        cursor, and a save/reload would re-roll the whole offer.  -> **P4 DERIVED HASH.**
    Q3  (not reached, but it agrees) the hook site is in **AoWz.exe**, which has
        **0 SYNC sites** and does not import `TAoWHSMap.Random`:
            rng_audit.py AoWz.exe --functions  ->  SYNC: 0 / RAW: 1
        so P1 is unavailable here in any case.

**The cave adds no draw**, so `rng_audit.py --owners` is unchanged by this patch; `--hash` is
what proves the site exists.  The hash bytes come from `build_scripts/rngstd.py` verbatim --
`basis() + 4x mix() + fmix32() + range_n(100)` -- and the script asserts that byte-for-byte
before writing (`_assert_rngstd_shape`).  Hand-rolling it is the anti-pattern in 4.10 item 8.

Hash inputs, in this fixed order:

    1  map[+0x22C]          the per-game salt, read as [[0x0045DF7C]] + 0x22C.
                            ⚠ Both dereferences are nil-guarded and fall through to salt 0
                            -- the value is 0 until TPlayerControl.NewDay runs on day 1, and
                            FNV mixes 0 perfectly well.
    2  [hero+0x18]          the network unit id, dword.  Per-hero, serialised.
    3  movzx [hero+0x4C]    the level cache, ONE BYTE (not four).  Included deliberately:
                            the offer re-rolls at every level, so the variable band changes
                            shape each time the dialog opens at a new level.
    4  ability id

`mul` (inside range_n) clobbers EDX:EAX, so the pct and the ability id are pushed across the
hash rather than parked in registers.  EBX (the form), ESI (the loop index) and EBP (the host
frame) all survive -- rngstd touches only EAX/EDX/ECX/flags.

================================================================================
THE HOOK -- located BY PATTERN, never by constant
================================================================================
The offer list is built by `cave_fill`, which is `build_herodlg_columns.py`'s cave in the
`.hcol` section -- **not** vanilla code.  That script regenerates the cave from source on every
--apply, so every internal VA inside it moves.  Nothing here may be a hard-coded address:

    site      pattern                        today       meaning
    cf_gate   8b 45 f4 8b 40 0c 3d 00 01 00 00   0x00623E5D  mov eax,[ebp-0xC] ; mov eax,[eax+0xC]
    resume    cf_gate + 6                        0x00623E93  cmp eax, 0x100
    cf_next   46 ff 4d f0                        0x00623F32  inc esi ; dec dword [ebp-0x10]

Each must match EXACTLY ONCE inside `.hcol` or the script aborts.  (`46 ff 4d f0` matches twice
in the whole file -- the other hit is at file 0x45FA8, in CODE -- which is why the search is
scoped to the section rather than the image.)

The gate goes at `cf_gate`, i.e. AFTER `CanExpand` (mask 0x200) and after
`test byte [ability+0x21],1` (mask 0x100), so it only ever sees abilities the dialog was already
going to list.  6 bytes are displaced; the cave replays both `mov`s, so **EAX = the ability id**
on entry and on every accept path, which is exactly what the resume instruction consumes.

⚠ **The gate sits BEFORE `cave_fill`'s own `cmp eax,0x100` range check**, so ability ids >= 256
reach it.  The first thing the cave does is `cmp eax,0x100 ; jae accept` -- fail open, because the
table has only 256 columns.

================================================================================
THE RACE KEY
================================================================================
    mov   ecx, [hero+0x40]          ; the hero's chassis resource
    movzx ecx, byte ptr [ecx+0x20]  ; the race byte

That is `THero.GetRace @0x55786F9C` inlined -- it is a two-instruction leaf.

⚠ **Do NOT call it through VMT +0xA4.**  Its body is `mov eax,[eax+0x40] ; mov al,[eax+0x20] ;
ret`, so only AL is valid on return: the top 24 bits of EAX are the upper bytes of the resource
POINTER.  Using EAX as a row index after that call indexes megabytes past the table.

`[hero+0x40]` is nil-guarded and fails open.  Row = min(race, 15), so raceless heroes (race 255 --
Mind Vessel, Dragon Golem) land on row 15.  Rows 12-14 are unreachable and hold 100.

================================================================================
WHICH HERO OBJECT -- the ORIGINAL, not the working copy
================================================================================
`THeroUpgradeDlg.Setup @0x446268` keeps two hero pointers:

    0x004462C1  mov eax,[ebx+0x1D8]        <- the ORIGINAL hero
    0x004462C7  call Engine.TEObject.Copy
    0x004462CC  mov [ebx+0x1DC], eax       <- the working copy Add/Remove mutates

`cave_fill` passes the WORKING COPY to `CanExpand`, which is correct for "does he already have
it".  The gate must read `[ebx+0x1D8]` instead: `PopulateLists @0x446954` re-runs on every Add
and Remove, and the working copy's level cache and identity could drift during the session.  The
original is fixed for the life of the dialog, so the offer set cannot shimmer.

================================================================================
THE CAVE -- 0x00628000..0x0062A000 in `.hcol`, 8 KB reserved
================================================================================
    0x00628000    4 B     magic 'RGT1' (dword 0x31544752) -- the "is the gate installed" probe
    0x00628010            cave entry (the E9 target)
    0x00628200    5 B     jmp <resume>     ACCEPT tail
    0x00628205    5 B     jmp <cf_next>    REJECT tail
    0x00629000  4096 B    the table, 16 rows x 256 columns, row = min(race,15)
    0x0062A000            build_skylevel_ui.py's cave -- the ceiling

⚠⚠ **The spec's original layout was arithmetically impossible and was corrected here.**  It put
the magic at 0x00629000 and the 4096-byte table at 0x00629100, which ends at 0x0062A100 -- 256
bytes INSIDE build_skylevel_ui.py's cave at 0x0062A000.  A 16x256 table needs a full page, so the
reservation was moved down to 0x00628000 and the table page-aligned at 0x00629000, ending exactly
at the squatter floor.  `build_herodlg_columns.py`'s `SQUATTER_FLOOR` is therefore lowered to
**0x00628000**, not 0x00629000.

`.hcol` is VA 0x00612000, VirtualSize 0x1C000, characteristics 0xE0000060 (CODE|EXEC|READ|WRITE).
Its free run is 0x0062417C..0x0062A000 (24,196 zero bytes, measured 2026-09-09); this takes the
top 8 KB of it and leaves 16,004 bytes free at 0x0062417C..0x00628000 (0x3E84).

⚠ The two tail jumps live at FIXED offsets (+0x200 / +0x205) precisely so
`build_herodlg_columns.py` can rewrite them from its own pattern search without re-assembling
anything.  Do not move them without editing both scripts.

================================================================================
⚠⚠ THE RE-CHAIN CONTRACT -- build_herodlg_columns.py WOULD OTHERWISE UNLINK THIS
================================================================================
`build_herodlg_columns.py --apply` calls `undo()` and then regenerates `cave_fill` from source.
That silently restores the vanilla `8b 45 f4 8b 40 0c` at cf_gate and moves it -- the exact
Magebane/Shield failure mode.  Three changes were made there:

  1. `SQUATTER_FLOOR` lowered 0x0062A000 -> 0x00628000 with this cave added to its squatter list,
     so its existing `assert D["code"] + len(code) < SQUATTER_FLOOR` protects the table for free.
  2. After the regenerated blob is written it calls `build_heroskill_race.relink_bytes()`, which
     re-installs the 6-byte hook and rewrites both tail jumps from its own pattern search, and
     prints `race-offer gate: re-chained` or `race-offer gate: not installed`.  **Never silent.**
  3. `undo()` is unchanged -- restoring the vanilla fill loop correctly leaves this cave inert.

Both scripts derive the three addresses from the SAME pattern search in the SAME function, so
they produce byte-identical results and either order works.  Re-running either is idempotent.

================================================================================
WHAT THIS DOES NOT DO
================================================================================
The AI is unaffected, structurally.  `THero.ValidateHeroUpgrade @0x55787D54` calls
`ExecuteUpgradeHeroAI @0x55787A24` directly when `player[+0xA7] != 0` and never opens a dialog,
so an AI hero still picks from all 102.  Filtering the AI too would be a SECOND patch, in
`AoWEPACK.dpl` -- and that path IS in the SYNC list (0x55787C35 -> call 0x5577827C), so it would
need the synchronised generator or this same hash.  Out of scope here.

`AoWDevEd.exe` is not touched: the editor's hero screens do not run this dialog.

================================================================================
⚠ A SECOND READER: build_pbem_leadersetup.py (2026-09-24)
================================================================================
The PBEM turn-1 leader window's `C_OFFER` (exe `0x0062C250`) reads THIS table at `TABLE_VA` and
copies this cave's rngstd hash, offering an ability iff `u < min(2*pct, 100)`.  A re-bake changes
both dialogs at once -- intended.  `--undo` here zeroes the table, so every threshold becomes 0 and
the PBEM window's Available list comes up EMPTY (no crash); build_pbem_leadersetup.py's dry run then
reports `chain: BROKEN` and its `--apply` refuses until this script is re-applied.  Its `--undo` works
either way.  Moving or re-shaping the table breaks it: that script imports `TABLE_VA`, `HERO_RES`,
`RES_RACE`, `MAPSLOT`, `MAP_SALT`, `HERO_UNITID`, `HERO_LEVEL`, `RACES.RACELESS_ROW` and
`_assert_rngstd_shape` from here.  (07-ui.md §10.6.)
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import time

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import heroskill_races as RACES
import rngstd
import zigexe                                      # mod binary names

TARGETS = [os.path.join(GAME, n) for n in zigexe.EXES]   # AoWz.exe + AoWzCompat.exe
COMPAT_DIFF_OFF = zigexe.COMPAT_BYTE  # the single byte that makes AoWzCompat AoWzCompat
BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP_SUFFIX = ".pre-heroskillrace"

IMAGE_BASE = 0x00400000
SECTION = ".hcol"

# ---------------------------------------------------------------- cave layout
CAVE = 0x00628000
CAVE_END = 0x0062A000                 # == build_skylevel_ui.py's cave; never write at or above
MAGIC_VA = CAVE
MAGIC = b"RGT1"                       # dword 0x31544752
ENTRY_VA = CAVE + 0x0010
ACCEPT_VA = CAVE + 0x0200             # 5 B  jmp <resume>
REJECT_VA = CAVE + 0x0205             # 5 B  jmp <cf_next>
TABLE_VA = CAVE + 0x1000              # 16 x 256
TABLE_SIZE = RACES.TABLE_ROWS * RACES.TABLE_COLS
CODE_LIMIT = ACCEPT_VA - ENTRY_VA     # 0x1F0 = 496 bytes of code budget

assert TABLE_VA + TABLE_SIZE == CAVE_END, "the table must end exactly at the squatter floor"

# ---------------------------------------------------------------- engine addresses
MAPSLOT = 0x0045DF7C                  # IAT slot -> &AoWE.AoWHSMap;  [[MAPSLOT]] = the map
MAP_SALT = 0x22C                      # map[+0x22C] = the per-game seed constant
DLG_HERO_ORIG = 0x1D8                 # THeroUpgradeDlg: the original hero
HERO_RES = 0x40                       # THero  -> chassis resource
RES_RACE = 0x20                       # resource -> race byte
HERO_UNITID = 0x18                    # TUnit  -> network unit id (dword)
HERO_LEVEL = 0x4C                     # THero  -> level cache (byte)
FRAME_ABILITY = -0x0C                 # cave_fill's [ebp-0x0C] = the TAbility
ABILITY_ID = 0x0C                     # TAbility -> ability id

# ---------------------------------------------------------------- the three patterns
# ⚠ located by pattern EVERY RUN, never by constant: build_herodlg_columns.py regenerates
# cave_fill and every VA inside it moves.
PAT_GATE = bytes.fromhex("8b45f4" "8b400c" "3d00010000")      # 11 B, un-hooked
GATE_ORIG = PAT_GATE[:6]                                      # the 6 bytes we displace
PAT_GATE_TAIL = PAT_GATE[6:]                                  # cmp eax,0x100 -- survives the hook
PAT_NEXT = bytes.fromhex("46" "ff4df0")                       # inc esi ; dec dword [ebp-0x10]
HOOK_LEN = 6


def die(msg):
    raise SystemExit("ABORT: " + msg)


def require(cond, msg):
    if not cond:
        die(msg)


# ===========================================================================
# PE helpers -- deliberately operate on a raw bytearray, so this module and
# build_herodlg_columns.py share ONE code path and cannot emit different bytes.
# ===========================================================================
def sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    require(data[pe:pe + 4] == b"PE\0\0", "bad PE header")
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsize = struct.unpack_from("<H", data, pe + 20)[0]
    sectbl = pe + 24 + optsize
    out = []
    for i in range(nsec):
        s = sectbl + 40 * i
        nm = bytes(data[s:s + 8]).rstrip(b"\0").decode("latin1")
        vsz, va = struct.unpack_from("<II", data, s + 8)
        rsz, raw = struct.unpack_from("<II", data, s + 16)
        out.append((nm, IMAGE_BASE + va, vsz, raw, rsz))
    return out


def sec_named(data, name):
    for s in sections(data):
        if s[0] == name:
            return s
    die("section %s not present -- run build_herodlg_columns.py --apply first" % name)


def off(data, va):
    for _nm, sva, vsz, raw, rsz in sections(data):
        if sva <= va < sva + max(vsz, rsz):
            return raw + (va - sva)
    die("VA 0x%08X is not mapped" % va)


def rd(data, va, n):
    o = off(data, va)
    return bytes(data[o:o + n])


def wr(data, va, blob):
    o = off(data, va)
    data[o:o + len(blob)] = blob


def find_sites(data):
    """-> (cf_gate VA, resume VA, cf_next VA), located by pattern inside `.hcol` only.

    Recognises BOTH states of the gate site:
        un-hooked   8b 45 f4 8b 40 0c | 3d 00 01 00 00
        hooked      E9 <rel32> 90     | 3d 00 01 00 00
    so one search serves --apply, --undo, the dry run and the re-chain.

    ⚠ OUR OWN RESERVATION IS EXCLUDED, and it has to be: the cave REPLAYS the two displaced
    `mov`s and then falls into `cmp eax, 0x100` for the ids>=256 fail-open check, so the cave's
    own first 11 bytes ARE the cf_gate pattern, byte for byte. Without this exclusion the very
    first --apply patches cleanly and then every later run aborts with "matched 2" -- which is
    exactly what happened on 2026-09-09. It is not cosmetic: a locator that can find the copy it
    just wrote could also hook the cave to itself.
    """
    _nm, sva, vsz, raw, rsz = sec_named(data, SECTION)
    n = max(vsz, rsz)
    blob = bytes(data[raw:raw + n])

    def ours(va, length):
        return va < CAVE_END and va + length > CAVE

    gates = []
    p = 0
    while True:
        i = blob.find(PAT_GATE_TAIL, p)
        if i < 0:
            break
        p = i + 1
        if i < HOOK_LEN:
            continue
        head = blob[i - HOOK_LEN:i]
        hooked = head[0] == 0xE9 and head[5] == 0x90
        va = sva + i - HOOK_LEN
        if (head == GATE_ORIG or hooked) and not ours(va, len(PAT_GATE)):
            gates.append(va)
    require(len(gates) == 1,
            "cf_gate pattern must match exactly once in %s outside 0x%08X..0x%08X, matched %d: %s"
            % (SECTION, CAVE, CAVE_END, len(gates), [hex(g) for g in gates]))

    nexts = []
    p = 0
    while True:
        i = blob.find(PAT_NEXT, p)
        if i < 0:
            break
        p = i + 1
        if not ours(sva + i, len(PAT_NEXT)):
            nexts.append(sva + i)
    require(len(nexts) == 1,
            "cf_next pattern must match exactly once in %s outside 0x%08X..0x%08X, matched %d: %s"
            % (SECTION, CAVE, CAVE_END, len(nexts), [hex(x) for x in nexts]))

    return gates[0], gates[0] + HOOK_LEN, nexts[0]


def check_no_reloc(data, lo, hi):
    """Abort if any live .reloc entry targets [lo, hi)."""
    _nm, _sva, vsz, raw, rsz = sec_named(data, ".reloc")
    end = raw + min(vsz, rsz)
    p, hits = raw, []
    while p + 8 <= end:
        page, blk = struct.unpack_from("<II", data, p)
        if blk < 8 or p + blk > end:
            break
        for q in range(p + 8, p + blk, 2):
            w = struct.unpack_from("<H", data, q)[0]
            if (w >> 12) == 0:
                continue
            tgt = IMAGE_BASE + page + (w & 0xFFF)
            if lo <= tgt < hi:
                hits.append(tgt)
        p += blk
    require(not hits, "live .reloc entries inside the displaced window: %s"
            % [hex(h) for h in hits])


def check_no_branch_into(data, lo, hi):
    """Abort if any rel8/rel32 branch in CODE or .hcol lands STRICTLY inside (lo, hi)."""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    hits = []
    for nm in ("CODE", SECTION):
        _n, sva, vsz, raw, rsz = sec_named(data, nm)
        n = max(vsz, rsz)
        blob = bytes(data[raw:raw + n])
        # cheap scan: every E8/E9 rel32 and every 0F 8x rel32 / 7x rel8 in the section
        for i in range(len(blob) - 5):
            b = blob[i]
            tgt = None
            if b in (0xE8, 0xE9):
                tgt = sva + i + 5 + struct.unpack_from("<i", blob, i + 1)[0]
            elif b == 0x0F and 0x80 <= blob[i + 1] <= 0x8F:
                tgt = sva + i + 6 + struct.unpack_from("<i", blob, i + 2)[0]
            elif 0x70 <= b <= 0x7F or b in (0xEB, 0xE3):
                tgt = sva + i + 2 + struct.unpack_from("<b", blob, i + 1)[0]
            if tgt is not None and lo < tgt < hi:
                hits.append((sva + i, tgt))
    require(not hits, "a branch lands inside the displaced bytes: %s"
            % [(hex(a), hex(t)) for a, t in hits[:8]])


# ===========================================================================
# the cave
# ===========================================================================
def _ks():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return Ks(KS_ARCH_X86, KS_MODE_32)


def build_code():
    """-> (code bytes for ENTRY_VA, [(label, va, bytes)] for --dis).

    Assembled fragment by fragment at exact VAs with the rngstd byte blobs spliced between them.
    Every branch target is an absolute constant known before assembly (ACCEPT_VA / REJECT_VA and
    two local labels), so there is no forward-reference pass and no address can drift.
    """
    ks = _ks()
    parts = []
    va = ENTRY_VA

    def asm(label, src):
        nonlocal va
        code = bytes(ks.asm(src, va)[0])
        parts.append((label, va, code))
        va += len(code)

    def raw(label, blob):
        nonlocal va
        parts.append((label, va, blob))
        va += len(blob)

    # ---- gate: replay the displaced movs, range-check, race, table lookup ----------------
    asm("gate", f"""
        mov   eax, [ebp {FRAME_ABILITY}]        /* replay 1: the TAbility           */
        mov   eax, [eax + {ABILITY_ID}]         /* replay 2: EAX = the ability id   */
        cmp   eax, 0x100
        jae   0x{ACCEPT_VA:X}                   /* id past the table -> FAIL OPEN   */
        mov   edx, [ebx + 0x{DLG_HERO_ORIG:X}]  /* the ORIGINAL hero, not [ebx+0x1DC] */
        test  edx, edx
        je    0x{ACCEPT_VA:X}                   /* no hero -> FAIL OPEN             */
        mov   ecx, [edx + 0x{HERO_RES:X}]
        test  ecx, ecx
        je    0x{ACCEPT_VA:X}                   /* no chassis -> FAIL OPEN          */
        movzx ecx, byte ptr [ecx + 0x{RES_RACE:X}]   /* THero.GetRace, inlined      */
        cmp   ecx, {RACES.RACELESS_ROW}
        jbe   rg_row
        mov   ecx, {RACES.RACELESS_ROW}         /* race 255 -> the raceless row     */
    rg_row:
        shl   ecx, 8                            /* row * 256                        */
        movzx ecx, byte ptr [ecx + eax + 0x{TABLE_VA:X}]
        push  ecx                               /* [esp+4] = pct                    */
        push  eax                               /* [esp]   = ability id             */
    """)

    # ---- P4 derived hash: rngstd bytes verbatim, caller's loads interleaved ---------------
    raw("rngstd.basis", rngstd.basis())

    asm("input 1: salt map[+0x22C]", f"""
        xor   edx, edx                          /* nil map -> salt 0                */
        mov   ecx, [0x{MAPSLOT:X}]
        test  ecx, ecx
        je    rg_nosalt
        mov   ecx, [ecx]
        test  ecx, ecx
        je    rg_nosalt
        mov   edx, [ecx + 0x{MAP_SALT:X}]
    rg_nosalt:
    """)
    raw("rngstd.mix", rngstd.mix())

    asm("input 2: hero unit id", f"""
        mov   ecx, [ebx + 0x{DLG_HERO_ORIG:X}]
        mov   edx, [ecx + 0x{HERO_UNITID:X}]
    """)
    raw("rngstd.mix", rngstd.mix())

    asm("input 3: hero level (1 byte)", f"""
        movzx edx, byte ptr [ecx + 0x{HERO_LEVEL:X}]
    """)
    raw("rngstd.mix", rngstd.mix())

    asm("input 4: ability id", """
        mov   edx, [esp]
    """)
    raw("rngstd.mix", rngstd.mix())

    raw("rngstd.fmix32", rngstd.fmix32())
    raw("rngstd.range_n(100)", rngstd.range_n(100))

    asm("decide", f"""
        pop   eax                               /* EAX = ability id again           */
        pop   ecx                               /* ECX = pct                        */
        cmp   edx, ecx                          /* EDX = hash, 0..99                */
        jb    0x{ACCEPT_VA:X}
        jmp   0x{REJECT_VA:X}
    """)

    code = b"".join(b for _l, _v, b in parts)
    require(len(code) <= CODE_LIMIT,
            "cave code is %d bytes, budget is %d (ENTRY 0x%08X .. ACCEPT 0x%08X)"
            % (len(code), CODE_LIMIT, ENTRY_VA, ACCEPT_VA))
    _assert_rngstd_shape(code)
    _assert_cave_sane(code)
    return code, parts


def _assert_rngstd_shape(code):
    """The emitted hash must be rngstd's bytes, in rngstd's order, and nothing else."""
    want = [("basis", rngstd.basis()), ("mix", rngstd.mix()), ("mix", rngstd.mix()),
            ("mix", rngstd.mix()), ("mix", rngstd.mix()), ("fmix32", rngstd.fmix32()),
            ("range_n(100)", rngstd.range_n(100))]
    pos = -1
    for name, blob in want:
        i = code.find(blob, pos + 1)
        require(i > pos, "rngstd.%s missing or out of order in the cave" % name)
        pos = i
    require(code.count(rngstd.basis()) == 1, "rngstd.basis() must appear exactly once")
    require(code.count(rngstd.mix()) == 4, "expected exactly 4 rngstd.mix() (4 hash inputs)")
    require(code.count(rngstd.fmix32()) == 1, "rngstd.fmix32() must appear exactly once")
    require(code.count(rngstd.range_n(100)) == 1, "rngstd.range_n(100) must appear exactly once")
    require(code.count(rngstd.SIGNATURE) == 1,
            "rngstd.SIGNATURE (69 c0 6b ca eb 85) must appear exactly once -- --hash finds P4 "
            "sites by it")
    require(code.count(bytes.fromhex("69c035aeb2c2")) == 1,
            "the second fmix32 constant (69 c0 35 ae b2 c2) must appear exactly once")


def _assert_cave_sane(code):
    """Disassemble the emitted bytes and check the properties the spec pins.

    ⚠ This is the keystone round-trip check, not decoration: `push 0xFFFF` assembles as
    `6A FF` = -1 and nothing complains.  Read what was actually encoded.
    """
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    seen_abs, ins = set(), []
    for i in md.disasm(code, ENTRY_VA):
        ins.append(i)
        require(i.mnemonic not in ("div", "idiv"),
                "the cave must not divide -- range_n is a multiply-shift (found %s at 0x%X)"
                % (i.mnemonic, i.address))
        for op in i.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                seen_abs.add(op.mem.disp & 0xFFFFFFFF)
            elif op.type == capstone.x86.X86_OP_MEM and op.mem.disp >= 0x400000:
                seen_abs.add(op.mem.disp & 0xFFFFFFFF)
    require(seen_abs == {MAPSLOT, TABLE_VA},
            "the only absolute operands may be the map slot 0x%08X and the table base 0x%08X; "
            "found %s" % (MAPSLOT, TABLE_VA, sorted(hex(a) for a in seen_abs)))
    require(sum(1 for i in ins if i.mnemonic == "cmp" and i.op_str == "eax, 0x100") == 1,
            "the ids>=256 fail-open check `cmp eax, 0x100` is missing")
    # nil guards: three `test <reg>,<same reg>` + `je accept`/`je rg_nosalt` pairs
    tests = sum(1 for i in ins if i.mnemonic == "test"
                and i.op_str in ("edx, edx", "ecx, ecx"))
    require(tests == 4, "expected 4 nil guards (hero, hero+0x40, map slot, map), found %d" % tests)
    # the whole stream must decode with nothing left over
    require(sum(i.size for i in ins) == len(code),
            "capstone could not decode the whole cave -- %d of %d bytes"
            % (sum(i.size for i in ins), len(code)))


def tails(resume_va, next_va):
    """-> (accept jmp bytes, reject jmp bytes). The two fixed 5-byte tail slots."""
    return (b"\xE9" + struct.pack("<i", resume_va - (ACCEPT_VA + 5)),
            b"\xE9" + struct.pack("<i", next_va - (REJECT_VA + 5)))


def hook_at(gate_va):
    """-> the 6 bytes that replace GATE_ORIG at `gate_va`."""
    return b"\xE9" + struct.pack("<i", ENTRY_VA - (gate_va + 5)) + b"\x90"


# ===========================================================================
# state
# ===========================================================================
def state(data):
    """-> ('orig' | 'on' | 'stale' | 'partial', detail dict)."""
    gate, resume, nxt = find_sites(data)
    cur = rd(data, gate, HOOK_LEN)
    magic = rd(data, MAGIC_VA, 4)
    code, _parts = build_code()
    acc, rej = tails(resume, nxt)

    hooked_here = cur == hook_at(gate)
    hooked_elsewhere = (cur[0] == 0xE9 and cur[5] == 0x90
                        and CAVE <= gate + 5 + struct.unpack("<i", cur[1:5])[0] < CAVE_END)
    cave_zero = rd(data, CAVE, CAVE_END - CAVE) == b"\0" * (CAVE_END - CAVE)
    code_ok = rd(data, ENTRY_VA, len(code)) == code
    tails_ok = rd(data, ACCEPT_VA, 5) == acc and rd(data, REJECT_VA, 5) == rej
    table_ok = rd(data, TABLE_VA, TABLE_SIZE) == RACES.table()

    d = dict(gate=gate, resume=resume, next=nxt, magic=magic, hooked=hooked_here,
             hooked_into_cave=hooked_elsewhere, cave_zero=cave_zero, code_ok=code_ok,
             tails_ok=tails_ok, table_ok=table_ok)

    if cur == GATE_ORIG and cave_zero:
        return "orig", d
    if hooked_here and magic == MAGIC and code_ok and tails_ok and table_ok:
        return "on", d
    if hooked_elsewhere and magic == MAGIC:
        # our chain, but the cave contents differ -- a table retune or an older code build
        return "stale", d
    return "partial", d


STATE_TEXT = {
    "orig": "unpatched (vanilla cf_gate, cave zero)",
    "on": "applied -- hook, cave, tails and table all current",
    "stale": "applied, but the cave differs from what this build emits (retune: run --apply)",
    "partial": "MIXED / unrecognised -- run --apply to normalise, or --undo",
}


# ===========================================================================
# apply / undo
# ===========================================================================
def kill_game():
    # ⚠ mod exes renamed AoWz*/AoWzEd 2026-09-09; list lives in zigexe.LOCKING_PROCESSES.
    for p in (n + ".exe" for n in zigexe.LOCKING_PROCESSES):
        subprocess.run(["taskkill", "/F", "/IM", p],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def save(path, data):
    try:
        f = open(path, "wb")
    except PermissionError:
        print("    locked -> killing AoW processes and retrying")
        kill_game()
        time.sleep(1.0)
        f = open(path, "wb")
    with f:
        f.write(data)


def backup(path, data):
    """⚠ Mint a snapshot ONLY from a file positively PROVED unpatched.

    Not "there is no backup yet", not "the text looks like ours" -- a positive test against the
    ORIGINAL bytes.  The undo path and a retune both present a file that is our own previous
    output; a .pre-* minted from either is a patched state wearing an authoritative name.
    """
    st, _d = state(data)
    if st != "orig":
        print("    no backup taken (%s is not in the original state: %s)"
              % (os.path.basename(path), st))
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dst = os.path.join(BACKUP_DIR, os.path.basename(path) + BACKUP_SUFFIX)
    if os.path.exists(dst):
        print("    backup already exists: %s" % dst)
        return
    shutil.copyfile(path, dst)
    print("    backup -> %s" % dst)


def apply_one(path, verbose=True):
    data = bytearray(open(path, "rb").read())
    st, d = state(data)
    print("%s: %s" % (os.path.basename(path), STATE_TEXT[st]))
    require(st != "partial",
            "%s is in a mixed state (hook=%s magic=%s code=%s tails=%s table=%s) -- "
            "run --undo first" % (os.path.basename(path), d["hooked"], d["magic"],
                                  d["code_ok"], d["tails_ok"], d["table_ok"]))

    gate, resume, nxt = d["gate"], d["resume"], d["next"]
    check_no_reloc(data, gate, gate + HOOK_LEN)
    check_no_branch_into(data, gate, gate + HOOK_LEN)

    code, _parts = build_code()
    acc, rej = tails(resume, nxt)
    table = RACES.table()

    if st == "orig":
        backup(path, data)
    else:
        print("    already chained -- rewriting the cave in place (no backup touched)")

    # verify-before-write: every byte we are about to overwrite must be either zero, the
    # original, or something THIS script wrote.
    cur_gate = rd(data, gate, HOOK_LEN)
    require(cur_gate == GATE_ORIG or cur_gate == hook_at(gate) or d["hooked_into_cave"],
            "cf_gate at 0x%08X holds foreign bytes %s" % (gate, cur_gate.hex(" ")))
    require(rd(data, MAGIC_VA, 4) in (MAGIC, b"\0\0\0\0"),
            "0x%08X does not hold our magic and is not zero -- another cave owns it" % MAGIC_VA)
    # the growth zone: everything in the reservation we do NOT write must still be zero
    gap1 = rd(data, MAGIC_VA + 4, ENTRY_VA - (MAGIC_VA + 4))
    gap2 = rd(data, ENTRY_VA + len(code), ACCEPT_VA - (ENTRY_VA + len(code)))
    gap3 = rd(data, REJECT_VA + 5, TABLE_VA - (REJECT_VA + 5))
    for nm, g in (("magic..entry", gap1), ("code..accept", gap2), ("reject..table", gap3)):
        require(set(g) <= {0}, "the %s growth zone is not zero -- refusing to write" % nm)

    wr(data, MAGIC_VA, MAGIC)
    wr(data, ENTRY_VA, code)
    wr(data, ACCEPT_VA, acc)
    wr(data, REJECT_VA, rej)
    wr(data, TABLE_VA, table)
    wr(data, gate, hook_at(gate))

    save(path, data)
    if verbose:
        print("    cf_gate 0x%08X -> cave 0x%08X (%d B code); accept -> 0x%08X, reject -> 0x%08X"
              % (gate, ENTRY_VA, len(code), resume, nxt))
        print("    table 0x%08X, %d B, %d rows x %d cols"
              % (TABLE_VA, len(table), RACES.TABLE_ROWS, RACES.TABLE_COLS))


def undo_one(path):
    data = bytearray(open(path, "rb").read())
    st, d = state(data)
    print("%s: %s" % (os.path.basename(path), STATE_TEXT[st]))
    gate = d["gate"]
    cur = rd(data, gate, HOOK_LEN)

    if cur == GATE_ORIG:
        print("    cf_gate is already the original 6 bytes -- leaving it")
    else:
        require(cur[0] == 0xE9 and cur[5] == 0x90, "cf_gate holds neither the original bytes nor "
                "an E9+nop hook: %s" % cur.hex(" "))
        tgt = gate + 5 + struct.unpack("<i", cur[1:5])[0]
        require(CAVE <= tgt < CAVE_END,
                "cf_gate's hook targets 0x%08X, outside our reservation 0x%08X..0x%08X -- it is "
                "not ours, refusing to touch it" % (tgt, CAVE, CAVE_END))
        wr(data, gate, GATE_ORIG)
        print("    cf_gate 0x%08X restored to %s" % (gate, GATE_ORIG.hex(" ")))

    span = CAVE_END - CAVE
    if rd(data, CAVE, span) == b"\0" * span:
        print("    cave 0x%08X..0x%08X already zero" % (CAVE, CAVE_END - 1))
    else:
        require(rd(data, MAGIC_VA, 4) == MAGIC,
                "0x%08X does not hold 'RGT1' -- refusing to zero a cave this script did not write"
                % MAGIC_VA)
        wr(data, CAVE, b"\0" * span)
        print("    cave 0x%08X..0x%08X zeroed (%d B)" % (CAVE, CAVE_END - 1, span))
    save(path, data)


# ===========================================================================
# the re-chain entry point used by build_herodlg_columns.py
# ===========================================================================
def relink_bytes(data):
    """Re-install the hook and both tail jumps into an in-memory exe. -> a status string.

    Called by `build_herodlg_columns.py` after it regenerates `cave_fill`, which restores the
    vanilla bytes at cf_gate and moves it.  Uses the SAME pattern search and the SAME byte
    emitters as --apply, so the two scripts cannot disagree and either order works.

    Never silent: the caller prints whatever this returns.
    """
    if bytes(rd(data, MAGIC_VA, 4)) != MAGIC:
        return "race-offer gate: not installed (0x%08X does not hold 'RGT1')" % MAGIC_VA
    gate, resume, nxt = find_sites(data)
    acc, rej = tails(resume, nxt)
    wr(data, ACCEPT_VA, acc)
    wr(data, REJECT_VA, rej)
    wr(data, gate, hook_at(gate))
    return ("race-offer gate: re-chained -- cf_gate 0x%08X -> 0x%08X, accept -> 0x%08X, "
            "reject -> 0x%08X" % (gate, ENTRY_VA, resume, nxt))


# ===========================================================================
# reporting
# ===========================================================================
def compat_check():
    a = open(TARGETS[0], "rb").read()
    b = open(TARGETS[1], "rb").read()
    require(len(a) == len(b), "%s / %s differ in length" % tuple(zigexe.EXES))
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    require(diff == [COMPAT_DIFF_OFF],
            "the two exes must differ in exactly one byte at 0x%08X; got %s"
            % (COMPAT_DIFF_OFF, [hex(x) for x in diff[:8]]))
    print("lockstep ok: %s and %s differ in exactly one byte, 0x%08X"
          % (zigexe.EXES[0], zigexe.EXES[1], COMPAT_DIFF_OFF))


def show_state():
    for path in TARGETS:
        data = bytearray(open(path, "rb").read())
        st, d = state(data)
        print("%-14s %-8s %s" % (os.path.basename(path), st, STATE_TEXT[st]))
        print("    cf_gate 0x%08X  resume 0x%08X  cf_next 0x%08X"
              % (d["gate"], d["resume"], d["next"]))
        print("    magic %-6s hook=%s code=%s tails=%s table=%s cave_zero=%s"
              % (repr(d["magic"].decode("latin1")), d["hooked"], d["code_ok"],
                 d["tails_ok"], d["table_ok"], d["cave_zero"]))


def disassemble():
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    code, parts = build_code()
    data = bytearray(open(TARGETS[0], "rb").read())
    _gate, resume, nxt = find_sites(data)
    acc, rej = tails(resume, nxt)

    print("cave 0x%08X..0x%08X (%d B reserved)" % (CAVE, CAVE_END - 1, CAVE_END - CAVE))
    print("  magic  0x%08X  %r" % (MAGIC_VA, MAGIC.decode()))
    print("  entry  0x%08X  %d of %d B used" % (ENTRY_VA, len(code), CODE_LIMIT))
    print("  accept 0x%08X  reject 0x%08X" % (ACCEPT_VA, REJECT_VA))
    print("  table  0x%08X  %d B\n" % (TABLE_VA, TABLE_SIZE))
    for label, va, blob in parts:
        print("---- %s @0x%08X (%d B) ----" % (label, va, len(blob)))
        for i in md.disasm(blob, va):
            print("  %08X  %-24s %s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str))
    print("\n---- tails ----")
    for nm, va, blob in (("accept", ACCEPT_VA, acc), ("reject", REJECT_VA, rej)):
        for i in md.disasm(blob, va):
            print("  %-7s %08X  %-24s %s %s"
                  % (nm, i.address, i.bytes.hex(" "), i.mnemonic, i.op_str))
    print("\n---- host site ----")
    print("  cf_gate  %s  ->  %s" % (GATE_ORIG.hex(" "), hook_at(_gate).hex(" ")))
    print()
    RACES.report()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", "--show", dest="dis", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="fail if any race falls outside the 20..30 expected-offer band")
    args = ap.parse_args()
    if args.apply and args.undo:
        ap.error("--apply and --undo are mutually exclusive")

    print("per-race hero level-up offer gate (%s + %s)" % tuple(zigexe.EXES))
    print("cave 0x%08X..0x%08X, table 0x%08X (%d x %d)\n"
          % (CAVE, CAVE_END - 1, TABLE_VA, RACES.TABLE_ROWS, RACES.TABLE_COLS))

    if args.dis:
        disassemble()
        return

    rc = RACES.report(strict=args.strict)
    if rc:
        die("heroskill_races.py is out of band and --strict was given")
    print()

    if args.apply:
        for path in TARGETS:
            apply_one(path)
        print()
        compat_check()
        print()
        show_state()
    elif args.undo:
        for path in TARGETS:
            undo_one(path)
        print()
        compat_check()
        print()
        show_state()
    else:
        show_state()
        print("\ndry run -- nothing written; use --apply to patch, --undo to revert")


if __name__ == "__main__":
    main()
