#!/usr/bin/env python3
r"""build_abiltypes_relocate.py -- move `AoWTC.AbilTypes` out of its 170-byte hole and widen the
nine `bound` pairs that guard it from [0,169] to [0,255].

FIXES A LIVE CRASH: "Error during Create Unit List"
--------------------------------------------------
Observed in game 2026-09-01, on an AI turn with priest heroes present. Reproduced with the Turn
Undead feature reverted, so it is NOT that feature -- it is a latent defect that
`build_abilityid_ceilings.py` armed.

`AoWTC.AbilTypes @0x00467248` is a **170-byte table, one category byte per ability id 0..169**
(vanilla's highest id was 0xA9 = 169). Fifteen hardware `BOUND eax,(0,169)` instructions guard
every read of it. Above 169 the `BOUND` raises #BR, which Delphi turns into a range-check error;
the tactical AI's caller swallows it into the modal **"Error during Create Unit List"**.

`build_abilityid_ceilings.py` raised the four `TCAI.EvalBattle` ability-scan loops from 0xAA to
0xB3 so the AI would stop being blind to Ziggurat's ids 0xAA..0xB2. Its docstring justified that
with "our ids are safe above the bound only because they are TEnhancementAbility and so never
become *selectable*". **That is true of the map-click path and FALSE of these four loops.**
Disassembled at scan 1 -- there is no `GetControlType` gate anywhere between the enabled-test and
the `bound`:

    0041870D  mov  edx, [ebp-0x14]      ; the ability id, the raised counter
    00418715  call [ecx+0xA8]           ; GetAbilityEnabled(id)
    0041871B  test al,al / je next      ; not enabled -> skip
    00418723  cmp  [ebp-0x14], 0x34     ; the only other test on the path
    ...
    004188E9  bound eax, [0x41B03C]     ; {0,169} -- reached by ANY enabled id
    004188EF  cmp  byte [eax+0x467248], 0

So any unit carrying an enabled ability with id 170..178 (Magebane 0xAA .. Embrittled 0xB2)
crashes the scan. Priest heroes carry several.

⚠⚠ THE TWO FEATURES ARE A MATCHED PAIR, IN BOTH DIRECTIONS
-----------------------------------------------------------
This script is a **prerequisite** for `build_abilityid_ceilings.py`, and therefore
`--undo` here is unsafe while that one is applied: it would restore `bound {0,169}` under scan
loops still enumerating to 0xB2, which is exactly the crash configuration. **`--undo` reads the
four terminators and refuses** unless they are back at <= 0xAA; run
`build_abilityid_ceilings.py --undo` first. Every run prints the pair's state.

WHY RELOCATE INSTEAD OF EXTENDING IN PLACE -- and why "just widen the bounds" is a TRAP
---------------------------------------------------------------------------------------
`AoWTC.AbilTypes` ends at 0x004672F1 and `AoWTC.SpellTypes` begins at 0x004672F4, leaving two
bytes of alignment padding that happen to contain `8B C0`. A widen-only fix reads straight
through them and then through SpellTypes itself. Measured against the pre-patch file:

    id 0xAA Magebane      -> 0x8B (139)   padding @0x004672F2   <-- a nonzero fake category
    id 0xAB Drillmaster   -> 0xC0 (192)   padding @0x004672F3   <-- a nonzero fake category
    id 0xAC..0xB2         -> 0x00         AoWTC.SpellTypes[0..6]
    (and id 0xB6 would reach SpellTypes[10] = 0x07, a real attack category)

139 and 192 clear every `cmp cat,0` gate in the engine, so Magebane and Drillmaster would have
been scored by the AI as attack actions of an undefined kind. That is the argument for the
relocation being *necessary*, not merely tidy.

⚠ `Modding Resources/Inioch/share5/patch scripts/build_spelltypes_bounds_fix.py` lists **exactly
these same nine limit words** -- independent third-party confirmation that the census below is
complete. But its premise, "every byte in [131..255] there reads 0", does not hold for AbilTypes:
see the four lines above. Do not port that script's widen-only shape onto this table.

⚠⚠ THE RELOCATION AND THE LIMIT RAISE ARE ATOMIC AND MUST STAY THAT WAY.
Limits raised **without** the relocation is strictly worse than the crash it removes: silent
garbage categories instead of a loud modal. There is one `PATCHES` set, one state verdict over all
23 sites, and any mixed state ABORTS.

WHAT THIS SCRIPT DOES (AoWTCPCK.dpl only -- the exes are not involved)
----------------------------------------------------------------------
1. Writes a **256-byte** table at `0x00469440`, being `AbilTypes[0..169]` copied verbatim from the
   live file plus `[170..255] = 0`.
2. Repoints all **13** references at it -- 12 direct `[reg+disp32]` displacements and the one
   pointer cell `0x004693DC`. Same-module retarget, so their `.reloc` entries stay correct; the
   script asserts each still carries one afterwards.
3. Repoints the **export** `AoWTC.AbilTypes@57EAA6ED` (ordinal 481) from RVA 0x00067248 to
   0x00069440. Export RVAs are relative and carry no `.reloc`. No module in the game directory
   imports it today -- but the sibling `AoWTC.SpellTypes` **is** imported by AoW.exe and
   AoWCompat.exe, so this class of export demonstrably gets consumed, and an export left naming a
   dead table is a trap for whoever consumes it next.
4. Raises the `hi` dword of all **9** distinct `{lo=0, hi=169}` limit words to **255**. That
   clears the hard save-format ability ceiling of 0xCD -- see `Zig notes/Ability_ID_Budget.md` §1
   -- with headroom.
5. Leaves the table bytes at `0x00467248` **untouched**, so the diff stays reversible and any
   reader missed by the census keeps vanilla behaviour.

⚠⚠ RAISING THE BOUND IS ONLY HALF OF "AN ID ABOVE 169 NOW WORKS"
-----------------------------------------------------------------
Every new entry `[170..255]` is category **0**, and 0 is **inert at every consumer** -- that is
deliberate (it reproduces the pre-crash behaviour for the passives that exist today) but it is not
a blank cheque. A *selectable* ability minted at id >= 170 would appear in the panel and then
**deselect itself the instant it is clicked**:

    0041EC66  mov  al, [eax+0x469440]   ; the category byte
    0041EC72  sub  al, 1
    0041EC74  jb   0x41EC7F             ; CF set <=> category == 0
    0041EC7F  or   edx, 0xFFFFFFFF      ; -1
    0041EC85  call 0x00422F0C           ; TTacticalCombatUnitHS.SelectAbility(-1) = DESELECT

It would also be invisible to the AI, draw no ranged path, and be excluded from `EvalPath` /
`CheckUnit`. **So the rule for a new id >= 170 is: the bound no longer blocks you, but you must
also set `[0x00469440 + id]` to the right category or the ability does nothing.** The live table
uses 1/2/3/5/7/11 for attack categories and 4 for touch/command (`sub al,1; jb` = 0, then
`sub al,3; je` = 4). Do not invent values outside that set.

THE CENSUS -- measured, not quoted. Re-derive it with the checks this script runs on every
invocation; `--census` prints them.
  12 direct displacements (all `.reloc`-covered), each preceded by its own `bound`:
     VA of dword   instruction                                  bound @    limit word
     0x00414807    cmp  byte [eax+AbilTypes], 4                 0x004147FF 0x00414D04
     0x00414BA8    cmp  byte [eax+AbilTypes], 4                 0x00414BA0 0x00414D04
     0x00414DDF    mov  al, byte [eax+AbilTypes]                0x00414DD7 0x00415128
     0x00416DA8    movzx eax, byte [eax+AbilTypes]              0x00416D9F 0x00418130
     0x004188F1    cmp  byte [eax+AbilTypes], 0                 0x004188E9 0x0041B03C
     0x00418907    cmp  byte [eax+AbilTypes], 4                 0x004188FF 0x0041B03C
     0x004189F0    mov  al, byte [eax+AbilTypes]                0x004189E8 0x0041B03C
     0x00418CB5    cmp  byte [eax+AbilTypes], 0                 0x00418CAD 0x0041B03C
     0x00419090    cmp  byte [eax+AbilTypes], 0                 0x00419088 0x0041B03C
     0x0041970E    cmp  byte [eax+AbilTypes], 0                 0x00419706 0x0041B03C
     0x0041EC68    mov  al, byte [eax+AbilTypes]                0x0041EC60 0x0041EDF8
     0x004280DF    mov  al, byte [eax+AbilTypes]                0x004280D7 0x004288A8
  1 pointer cell 0x004693DC (`.reloc`-covered), read by three `mov edx,[0x4693DC]; ..[edx+eax]`:
     0x00409D05 (bound 0x00409CFF, limit 0x0040B0FC)
     0x0040B417 (bound 0x0040B411, limit 0x0040CDCC)
     0x0040F3D2 (bound 0x0040F3CC, limit 0x0040F4A8)
  1 export Address Table Entry (ordinal 481), holding an RVA, no `.reloc`.
  => 15 reads, 9 distinct limit words, 14 things to repoint. 12+1+1+9 = 23 sites.

  Checked for a *computed* access that a raw dword scan would miss: no dword anywhere in the file
  holds a value in 0x467249..0x4672F1 (the table's interior), so nothing addresses it off a
  neighbouring base. Cross-module reach is checked **by name and by ordinal** across every PE in
  the game directory, and the script aborts if an importer ever appears.

WHY 0x00469440 IS SAFE
----------------------
DATA runs 0x00467000..0x0046B7C8 (vsize). The package's global pointer table ends with the dword
at 0x00469428, so the last live byte is 0x0046942B and everything from 0x0046942C to the end of
the section is zero.

⚠ A naive zero-run scan reports the run as starting at **0x0046942B** -- that byte is the zero
high byte of the live pointer `0x0046E970` at 0x00469428, not free space. 0x00469440 is chosen
16-byte aligned and 20 bytes clear of the true first free byte.

Proved dead, and re-proved on every invocation: **no dword anywhere in the file** -- reloc'd or
not -- holds a value inside 0x00469440..0x0046953F, and no `.reloc` entry is sited there. (The one
hot neighbour, 0x00469420 with 289 references, is a scalar cell read as `mov eax,[0x469420]`
holding a **pointer to** `AoWTC.AoWCombatMap` -- the BSS export at 0x0046C064 -- not an array
base, so it cannot be indexed into our region.)

⚠ FUTURE EDITS TO AbilTypes MUST TARGET THE NEW TABLE. Once this is applied, writing a category
byte at 0x00467248+id does nothing -- every reader has moved. The dry run discriminates the two
drift directions using `<game dir>\backups\AoWTCPCK.dpl.pre-abiltypes` (which holds the original as
it stood at apply time; it is minted only from a file proved unpatched at all 23 sites):
  * ORIGINAL EDITED  -- the table at 0x00467248 moved; `--apply` re-copies ids 0..169 in place and
    leaves 170..255 alone.
  * NEW TABLE EDITED -- somebody wrote ids 0..169 in the new table; `--apply` **refuses**, because
    overwriting would silently revert their feature.
⚠ Edits to ids **170..255** in the new table are preserved by `--apply` but **zeroed by `--undo`**,
which restores the whole 256-byte region. They do not survive a round trip; `--undo` lists what it
is about to discard.

Usage:
  python build_scripts/build_abiltypes_relocate.py            dry run + verify current state
  python build_scripts/build_abiltypes_relocate.py --apply    relocate + widen (atomic)
  python build_scripts/build_abiltypes_relocate.py --undo     surgical: restore 14 refs, 9 limits,
                                                              zero the new table; no backup touched
  python build_scripts/build_abiltypes_relocate.py --show     hexdump both tables
  python build_scripts/build_abiltypes_relocate.py --dis      disassemble all 15 guarded reads
  python build_scripts/build_abiltypes_relocate.py --census   re-derive the reference census
"""
import os
import shutil
import struct
import subprocess
import sys

# The Windows console defaults to cp1252 and cannot encode the warning signs above. Without this
# the script writes its bytes correctly and THEN dies printing them, exiting non-zero -- which
# reads as a failed patch when it was a successful one. Degrade instead of raising.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MODULE = "AoWTCPCK.dpl"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never the game root (rule 2026-09-03)
SUFFIX = ".pre-abiltypes"


def backup_path(path):
    r"""<game dir>\backups\<file>.pre-abiltypes. The read site (backup_original, which parses the
    snapshot to tell ORIGINAL EDITED from NEW TABLE EDITED) and the write site must agree, so both
    go through here."""
    return os.path.join(BACKUP_DIR, os.path.basename(path) + SUFFIX)

OLD_TABLE = 0x00467248          # AoWTC.AbilTypes, 170 bytes, ids 0..169 -- never written by us
OLD_LEN = 170
NEW_TABLE = 0x00469440          # 16-byte aligned, inside the proven-dead DATA tail
NEW_LEN = 0x100                 # 256 bytes: ids 0..255
OLD_HI, NEW_HI = 169, 255

EXPORT_NAME = b"AoWTC.AbilTypes"

# (VA of the dword, hex of the bytes that must immediately precede it, description)
# The prefix is the verify-before-write proof that we are patching a displacement inside the
# expected instruction and not a coincidental constant.
DIRECT = [
    (0x00414807, "80b8",   "cmp  byte [eax+AbilTypes], 4"),
    (0x00414BA8, "80b8",   "cmp  byte [eax+AbilTypes], 4"),
    (0x00414DDF, "8a80",   "mov  al, byte [eax+AbilTypes]"),
    (0x00416DA8, "0fb680", "movzx eax, byte [eax+AbilTypes]"),
    (0x004188F1, "80b8",   "cmp  byte [eax+AbilTypes], 0   (EvalBattle scan 1)"),
    (0x00418907, "80b8",   "cmp  byte [eax+AbilTypes], 4   (EvalBattle scan 1)"),
    (0x004189F0, "8a80",   "mov  al, byte [eax+AbilTypes]  (EvalBattle scan 1)"),
    (0x00418CB5, "80b8",   "cmp  byte [eax+AbilTypes], 0   (EvalBattle scan 2)"),
    (0x00419090, "80b8",   "cmp  byte [eax+AbilTypes], 0   (EvalBattle scan 3)"),
    (0x0041970E, "80b8",   "cmp  byte [eax+AbilTypes], 0   (EvalBattle scan 4)"),
    (0x0041EC68, "8a80",   "mov  al, byte [eax+AbilTypes]"),
    (0x004280DF, "8a80",   "mov  al, byte [eax+AbilTypes]"),
]
POINTER_CELL = 0x004693DC       # DATA cell holding the table base; read by 3 sites

# Every VA-valued reference that must be repointed. 12 displacements + the pointer cell.
# (The export ATE is RVA-valued and is handled separately.)
REFS = [va for va, _, _ in DIRECT] + [POINTER_CELL]

# The nine distinct {lo=0, hi=169} limit words. `hi` is the dword at VA+4.
LIMITS = [
    (0x0040B0FC, "guards the pointer-cell read at 0x00409D05"),
    (0x0040CDCC, "guards the pointer-cell read at 0x0040B417"),
    (0x0040F4A8, "guards the pointer-cell read at 0x0040F3D2"),
    (0x00414D04, "guards 0x00414807, 0x00414BA8"),
    (0x00415128, "guards 0x00414DDF"),
    (0x00418130, "guards 0x00416DA8"),
    (0x0041B03C, "guards the six TCAI.EvalBattle reads -- THE CRASH"),
    (0x0041EDF8, "guards 0x0041EC68"),
    (0x004288A8, "guards 0x004280DF"),
]

# (bound VA, limit VA, VA of the read instruction) for --dis. 15 reads.
READS = [
    (0x004147FF, 0x00414D04, 0x00414805), (0x00414BA0, 0x00414D04, 0x00414BA6),
    (0x00414DD7, 0x00415128, 0x00414DDD), (0x00416D9F, 0x00418130, 0x00416DA5),
    (0x004188E9, 0x0041B03C, 0x004188EF), (0x004188FF, 0x0041B03C, 0x00418905),
    (0x004189E8, 0x0041B03C, 0x004189EE), (0x00418CAD, 0x0041B03C, 0x00418CB3),
    (0x00419088, 0x0041B03C, 0x0041908E), (0x00419706, 0x0041B03C, 0x0041970C),
    (0x0041EC60, 0x0041EDF8, 0x0041EC66), (0x004280D7, 0x004288A8, 0x004280DD),
    (0x00409CFF, 0x0040B0FC, 0x00409D05), (0x0040B411, 0x0040CDCC, 0x0040B417),
    (0x0040F3CC, 0x0040F4A8, 0x0040F3D2),
]

# --- the prerequisite pair. build_abilityid_ceilings.py's four TCAI.EvalBattle terminators.
# The loops are exclusive (`inc; cmp counter,BOUND; jne body`), so a terminator of B enumerates
# ids up to B-1. Vanilla B is 0xAA => max id 0xA9 = 169 = exactly the old bound. Any B above
# 0xAA drives ids past 169 into the `bound`, so restoring {0,169} under a raised B re-arms the
# crash -- which is why --undo refuses.
EVALBATTLE = [
    (0x00418A73, "817dec", "TCAI.EvalBattle ability scan 1"),
    (0x00418D1F, "817df4", "TCAI.EvalBattle ability scan 2"),
    (0x004190FA, "817df4", "TCAI.EvalBattle ability scan 3"),
    (0x0041977F, "817df4", "TCAI.EvalBattle ability scan 4"),
]
SAFE_SCAN_BOUND = 0xAA

AOW_PROCS = ["AoW", "AoWCompat", "AoWDevEd", "AoWEd"]


def kill_aow():
    """Game files are locked while any AoW binary runs; the editor loads the DLLs too.
    Standing authorization to kill them -- the game autosaves per turn."""
    killed = [n for n in AOW_PROCS
              if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                                capture_output=True, text=True).returncode == 0]
    if killed:
        print("  killed running: " + ", ".join(killed))


# --------------------------------------------------------------------------- minimal PE reader
class PEView(object):
    def __init__(self, data):
        self.d = data
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        assert data[pe:pe + 4] == b"PE\0\0", "bad PE header"
        coff = pe + 4
        nsec = struct.unpack_from("<H", data, coff + 2)[0]
        opt_size = struct.unpack_from("<H", data, coff + 16)[0]
        opt = coff + 20
        self.base = struct.unpack_from("<I", data, opt + 28)[0]
        nrva = struct.unpack_from("<I", data, opt + 92)[0]
        self.dirs = [struct.unpack_from("<II", data, opt + 96 + 8 * i) for i in range(nrva)]
        self.sections = []
        s = opt + opt_size
        for _ in range(nsec):
            name = bytes(data[s:s + 8]).rstrip(b"\0").decode("latin1")
            vsize, rva, rsize, raw = struct.unpack_from("<IIII", data, s + 8)
            self.sections.append((name, rva, vsize, raw, rsize))
            s += 40

    def rva2off(self, rva):
        for _n, va, vsz, raw, rsz in self.sections:
            if va <= rva < va + max(vsz, rsz):
                return raw + (rva - va)
        return None

    def off(self, va):
        """VA -> file offset, resolved through the section table (never a flat delta)."""
        o = self.rva2off(va - self.base)
        assert o is not None, "VA %08X is in no section" % va
        return o

    def sec_of(self, va):
        for n, rva, vsz, raw, rsz in self.sections:
            if self.base + rva <= va < self.base + rva + max(vsz, rsz):
                return n, self.base + rva, vsz, raw, rsz
        return None

    def u32(self, va):
        return struct.unpack_from("<I", self.d, self.off(va))[0]

    def cstr(self, off):
        e = self.d.index(b"\0", off)
        return bytes(self.d[off:e])

    def relocs(self):
        out = set()
        rva, size = self.dirs[5]
        p = self.rva2off(rva)
        end = p + size
        while p < end:
            page, blk = struct.unpack_from("<II", self.d, p)
            if blk == 0:
                break
            for i in range((blk - 8) // 2):
                e = struct.unpack_from("<H", self.d, p + 8 + 2 * i)[0]
                if e >> 12 == 3:
                    out.add(self.base + page + (e & 0xFFF))
            p += blk
        return out

    def dword_refs_into(self, lo, hi):
        """Every dword in any raw section whose value lands in [lo,hi). -> [(VA, value, sec)]"""
        out = []
        for n, rva, _vsz, raw, rsz in self.sections:
            secva = self.base + rva
            for o in range(raw, raw + rsz - 3):
                v = struct.unpack_from("<I", self.d, o)[0]
                if lo <= v < hi:
                    out.append((secva + (o - raw), v, n))
        return out

    def export_ate(self, name):
        """-> (file offset of the Address Table Entry, ordinal, full export name).
        The ATE holds an RVA, not a VA, and carries no .reloc entry."""
        d = self.d
        erva, _sz = self.dirs[0]
        eo = self.rva2off(erva)
        obase = struct.unpack_from("<I", d, eo + 0x10)[0]
        nname = struct.unpack_from("<I", d, eo + 0x18)[0]
        afun, anam, aord = struct.unpack_from("<III", d, eo + 0x1C)
        fo, no, oo = self.rva2off(afun), self.rva2off(anam), self.rva2off(aord)
        hits = []
        for i in range(nname):
            nr = struct.unpack_from("<I", d, no + 4 * i)[0]
            nm = self.cstr(self.rva2off(nr))
            if nm == name or nm.startswith(name + b"@"):
                oi = struct.unpack_from("<H", d, oo + 2 * i)[0]
                hits.append((fo + 4 * oi, oi + obase, nm.decode("latin1")))
        assert len(hits) == 1, ("expected exactly one %s export, found %d"
                                % (name.decode(), len(hits)))
        return hits[0]


def imports_abiltypes(gamedir, ordinal):
    """-> [(module, dll, how)] for every PE in the game dir importing AoWTC.AbilTypes.
    ⚠ Checks BOTH by-name and by-ordinal. A name-only check is a false negative for an ordinal
    import, and the sibling AoWTC.SpellTypes proves this class of export does get consumed."""
    found = []
    for fn in sorted(os.listdir(gamedir)):
        if os.path.splitext(fn)[1].lower() not in (".dpl", ".exe", ".dll"):
            continue
        try:
            data = open(os.path.join(gamedir, fn), "rb").read()
            pv = PEView(data)
        except Exception:                                                # noqa: BLE001
            continue
        irva = pv.dirs[1][0] if len(pv.dirs) > 1 else 0
        if not irva:
            continue
        k = pv.rva2off(irva)
        if k is None:
            continue
        while True:
            try:
                ilt, _ts, _fc, nm, iat = struct.unpack_from("<IIIII", data, k)
            except struct.error:
                break
            if nm == 0:
                break
            so = pv.rva2off(nm)
            if so is None:
                break
            dll = pv.cstr(so).decode("latin1")
            from_us = "AOWTCPCK" in dll.upper()
            to = pv.rva2off(ilt or iat)
            if to is not None:
                j = to
                while True:
                    ent = struct.unpack_from("<I", data, j)[0]
                    if ent == 0:
                        break
                    if ent & 0x80000000:
                        if from_us and (ent & 0xFFFF) == ordinal:
                            found.append((fn, dll, "by ordinal %d" % ordinal))
                    else:
                        ho = pv.rva2off(ent)
                        if ho is not None and EXPORT_NAME in pv.cstr(ho + 2):
                            found.append((fn, dll, "by name %s"
                                          % pv.cstr(ho + 2).decode("latin1")))
                    j += 4
            k += 20
    return found


# --------------------------------------------------------------------------- state
VANILLA, INSTALLED, MIXED = "vanilla", "installed", "MIXED"


def backup_original(path):
    """The AbilTypes bytes as they stood when .pre-abiltypes was taken, or None."""
    bak = backup_path(path)
    if not os.path.exists(bak):
        return None
    try:
        pb = PEView(bytearray(open(bak, "rb").read()))
        o = pb.off(OLD_TABLE)
        return bytes(pb.d[o:o + OLD_LEN])
    except Exception:                                                    # noqa: BLE001
        return None


def classify(pv, path, verbose=True):
    """Single verdict over all 23 sites, plus a table verdict. -> (state, head, tail_extra)."""
    lines = []
    states = []
    for va in REFS:
        v = pv.u32(va)
        st = VANILLA if v == OLD_TABLE else INSTALLED if v == NEW_TABLE else "?%08X" % v
        states.append(st)
        lines.append("  ref    %08X -> %08X  %s" % (va, v, st))
    ate, ordinal, ename = pv.export_ate(EXPORT_NAME)
    rv = struct.unpack_from("<I", pv.d, ate)[0]
    est = (VANILLA if rv == OLD_TABLE - pv.base else
           INSTALLED if rv == NEW_TABLE - pv.base else "?%08X" % rv)
    states.append(est)
    lines.append("  export %s ord %d -> RVA %08X  %s" % (ename, ordinal, rv, est))
    for va, _desc in LIMITS:
        lo, hi = struct.unpack_from("<II", pv.d, pv.off(va))
        if lo != 0:
            lines.append("  limit  %08X lo=%d  !! expected 0" % (va, lo))
            states.append("?lo")
            continue
        st = VANILLA if hi == OLD_HI else INSTALLED if hi == NEW_HI else "?%d" % hi
        states.append(st)
        lines.append("  limit  %08X {0,%3d}  %s" % (va, hi, st))

    if all(s == VANILLA for s in states):
        state = VANILLA
    elif all(s == INSTALLED for s in states):
        state = INSTALLED
    else:
        state = MIXED

    blob = bytes(pv.d[pv.off(NEW_TABLE):pv.off(NEW_TABLE) + NEW_LEN])
    live = bytes(pv.d[pv.off(OLD_TABLE):pv.off(OLD_TABLE) + OLD_LEN])
    zeros = b"\0" * (NEW_LEN - OLD_LEN)
    tail_extra = sorted(OLD_LEN + i for i, b in enumerate(blob[OLD_LEN:]) if b)
    if blob == b"\0" * NEW_LEN:
        head = "empty"
    elif blob[:OLD_LEN] == live:
        head = "populated"
    else:
        # The head disagrees with the original. Which side moved? .pre-abiltypes holds the
        # original as it stood at apply time and is the only thing that can tell them apart.
        was = backup_original(path)
        if was is None:
            head = "DRIFT (indeterminate -- no .pre-abiltypes to compare against)"
        elif live != was and blob[:OLD_LEN] == was:
            head = "ORIGINAL EDITED"
        elif live == was:
            head = "NEW TABLE EDITED"
        else:
            head = "DRIFT (both sides moved)"
    if verbose:
        for ln in lines:
            print(ln)
        print("  table  %08X..%08X  ids 0..169: %s%s"
              % (NEW_TABLE, NEW_TABLE + NEW_LEN - 1, head,
                 "" if not tail_extra else
                 ";  ids 170..255: %d non-zero (%s)"
                 % (len(tail_extra), ", ".join(str(i) for i in tail_extra[:8]))))
    return state, head, tail_extra


def scan_bounds(pv):
    """-> [(va, immediate or None, desc)] for build_abilityid_ceilings.py's four terminators."""
    out = []
    for va, opc, desc in EVALBATTLE:
        o = pv.off(va)
        got = bytes(pv.d[o:o + 3]).hex()
        out.append((va, pv.d[o + 3] if got == opc else None, desc))
    return out


def report_pair(pv):
    """Print the prerequisite pair's state. -> the list from scan_bounds()."""
    sb = scan_bounds(pv)
    print("\n  build_abilityid_ceilings.py -- the four TCAI.EvalBattle scan terminators:")
    for va, imm, desc in sb:
        if imm is None:
            print("    %08X  !! opcode mismatch, cannot read  %s" % (va, desc))
        else:
            print("    %08X  cmp counter, 0x%02X  -> enumerates ids <= 0x%02X   %s"
                  % (va, imm, imm - 1, desc))
    return sb


def safety_checks(pv):
    """Re-derive the invariants the census established. -> list of problems."""
    bad = []
    rel = pv.relocs()

    sec = pv.sec_of(NEW_TABLE)
    if sec is None:
        bad.append("NEW_TABLE %08X is in no section" % NEW_TABLE)
    else:
        n, secva, vsz, _raw, _rsz = sec
        if n != "DATA":
            bad.append("NEW_TABLE is in section %s, expected DATA" % n)
        if NEW_TABLE + NEW_LEN > secva + vsz:
            bad.append("NEW_TABLE overruns DATA vsize end %08X" % (secva + vsz))

    for va in REFS:
        if va not in rel:
            bad.append("reference %08X has NO .reloc entry -- it would not rebase" % va)
    ate, ordinal, _n = pv.export_ate(EXPORT_NAME)
    ate_va = None
    for _n2, rva, vsz, raw, rsz in pv.sections:
        if raw <= ate < raw + rsz:
            ate_va = pv.base + rva + (ate - raw)
    if ate_va is not None and ate_va in rel:
        bad.append("the export ATE at %08X carries a .reloc entry -- it should hold a bare RVA"
                   % ate_va)
    for va, _d in LIMITS:
        if va in rel or va + 4 in rel:
            bad.append("limit word %08X carries a .reloc entry -- it is not plain data" % va)

    for va, prefix, _desc in DIRECT:
        got = bytes(pv.d[pv.off(va) - len(prefix) // 2:pv.off(va)]).hex()
        if got != prefix:
            bad.append("%08X preceded by %s, expected %s -- not the expected instruction"
                       % (va, got, prefix))

    intruders = [(va, v) for va, v, _s in pv.dword_refs_into(NEW_TABLE, NEW_TABLE + NEW_LEN)
                 if va not in REFS]
    for va, v in intruders:
        bad.append("dword at %08X points to %08X, inside the destination -- collision" % (va, v))
    if any(NEW_TABLE <= r < NEW_TABLE + NEW_LEN for r in rel):
        bad.append("a .reloc entry is sited inside the destination")

    for va, v, _s in pv.dword_refs_into(OLD_TABLE + 1, OLD_TABLE + OLD_LEN):
        bad.append("dword at %08X points to %08X, INSIDE the original table -- a computed "
                   "access the repoint would miss" % (va, v))

    for m, dll, how in imports_abiltypes(GAME, ordinal):
        bad.append("%s imports AoWTC.AbilTypes from %s (%s) -- it would read whichever table "
                   "the export names, so the repoint must stay in step" % (m, dll, how))
    return bad


# --------------------------------------------------------------------------- views
def show(pv):
    for label, va, ln in (("ORIGINAL AoWTC.AbilTypes (bytes untouched)", OLD_TABLE, OLD_LEN),
                          ("NEW 256-byte table", NEW_TABLE, NEW_LEN)):
        print("\n%s  @%08X  (%d bytes, file 0x%X)" % (label, va, ln, pv.off(va)))
        o = pv.off(va)
        for i in range(0, ln, 16):
            row = pv.d[o + i:o + i + min(16, ln - i)]
            print("  %08X  %-47s  ids %3d..%3d" % (va + i, " ".join("%02X" % b for b in row),
                                                   i, i + len(row) - 1))
    pad = pv.d[pv.off(OLD_TABLE + OLD_LEN):pv.off(OLD_TABLE + OLD_LEN) + 2]
    print("\n2 bytes of alignment padding after the original: %08X = %s "
          "(AoWTC.SpellTypes begins %08X)"
          % (OLD_TABLE + OLD_LEN, " ".join("%02X" % b for b in pad), 0x004672F4))
    print("A widen-only fix would have served those as ids 170 (%d) and 171 (%d)."
          % (pad[0], pad[1]))


def dis(pv):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        print("capstone not installed -- pip install capstone")
        return
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    print("all 15 guarded reads, decoded from the live file:\n")
    for bva, lva, rva in READS:
        lo, hi = struct.unpack_from("<II", pv.d, pv.off(lva))
        o = pv.off(bva)
        print("  limit %08X = {%d,%d}" % (lva, lo, hi))
        for ins in md.disasm(bytes(pv.d[o:o + (rva - bva) + 8]), bva):
            if ins.address > rva:
                break
            print("    %08X  %-22s %s %s" % (ins.address, ins.bytes.hex(),
                                             ins.mnemonic, ins.op_str))
        print()


def census(pv):
    _ate, ordinal, ename = pv.export_ate(EXPORT_NAME)
    print("dwords holding the OLD table base %08X:" % OLD_TABLE)
    for va, _v, s in pv.dword_refs_into(OLD_TABLE, OLD_TABLE + 1):
        print("  %08X (%s)" % (va, s))
    print("dwords holding the NEW table base %08X:" % NEW_TABLE)
    for va, _v, s in pv.dword_refs_into(NEW_TABLE, NEW_TABLE + 1):
        print("  %08X (%s)" % (va, s))
    print("dwords pointing INSIDE the original table (%08X..%08X) -- must be none:"
          % (OLD_TABLE + 1, OLD_TABLE + OLD_LEN - 1))
    for va, v, s in pv.dword_refs_into(OLD_TABLE + 1, OLD_TABLE + OLD_LEN):
        print("  %08X -> %08X (%s)" % (va, v, s))
    print("dwords pointing into the destination (%08X..%08X):"
          % (NEW_TABLE, NEW_TABLE + NEW_LEN - 1))
    for va, v, s in pv.dword_refs_into(NEW_TABLE, NEW_TABLE + NEW_LEN):
        print("  %08X -> %08X (%s)%s" % (va, v, s, "  [ours]" if va in REFS else "  !! FOREIGN"))
    print("export %s = ordinal %d" % (ename, ordinal))
    print("modules importing it (checked by name AND by ordinal, every PE in the game dir): %s"
          % (imports_abiltypes(GAME, ordinal) or "none"))


def atomic_write(path, data):
    """Truncate-then-write leaves an unparseable DPL if it is interrupted. Stage and rename."""
    tmp = path + ".tmp-abiltypes"
    with open(tmp, "wb") as f:
        f.write(bytes(data))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# --------------------------------------------------------------------------- main
def main(argv):
    apply_ = "--apply" in argv
    undo = "--undo" in argv
    if apply_ and undo:
        print("ABORT: --apply and --undo are mutually exclusive")
        return 2

    path = os.path.join(GAME, MODULE)
    if not os.path.exists(path):
        print("MISSING: %s" % path)
        return 1
    data = bytearray(open(path, "rb").read())
    pv = PEView(data)

    print("%s  (%d bytes)  image base %08X" % (MODULE, len(data), pv.base))
    print("AbilTypes: %08X (%d bytes)  ->  %08X (%d bytes);  bound hi %d -> %d\n"
          % (OLD_TABLE, OLD_LEN, NEW_TABLE, NEW_LEN, OLD_HI, NEW_HI))

    if "--show" in argv:
        show(pv)
        return 0
    if "--dis" in argv:
        dis(pv)
        return 0
    if "--census" in argv:
        census(pv)
        return 0

    state, head, tail_extra = classify(pv, path)
    print("\nSTATE: %s   (table ids 0..169: %s)" % (state.upper(), head))
    sb = report_pair(pv)

    if state == MIXED:
        print("\nABORT: the 23 sites DISAGREE. This patch is atomic by construction -- limits\n"
              "raised without the relocation would read past the 170-byte original into the\n"
              "`8B C0` padding and AoWTC.SpellTypes, handing the AI garbage categories.\n"
              "Do not force it. Work out who wrote the odd site first.")
        return 2

    bad = safety_checks(pv)
    if bad:
        print("\nSAFETY CHECKS FAILED:")
        for b in bad:
            print("  !! %s" % b)
        return 2
    print("\nsafety checks: .reloc coverage, instruction prefixes, destination collision,\n"
          "               original-table interior, cross-module imports (name + ordinal) -- clear")

    # ---- the prerequisite guard. Restoring {0,169} under raised scan loops IS the crash.
    if undo:
        unsafe = [(va, imm, d) for va, imm, d in sb if imm is None or imm > SAFE_SCAN_BOUND]
        if unsafe:
            print("\nABORT: --undo would RE-ARM the crash this script exists to fix.\n")
            for va, imm, d in unsafe:
                print("  %08X enumerates ids up to 0x%02X  %s"
                      % (va, (imm - 1) if imm is not None else 0, d))
            print("\nRestoring bound {0,%d} while those loops still run past id %d is exactly the\n"
                  "configuration that produced \"Error during Create Unit List\" in game on\n"
                  "2026-09-01. Run this FIRST, then retry:\n\n"
                  "    python build_scripts/build_abilityid_ceilings.py --undo\n\n"
                  "(That restores the terminators to 0x%02X. Nothing has been written here.)"
                  % (OLD_HI, OLD_HI, SAFE_SCAN_BOUND))
            return 2
        print("  prerequisite guard: all four terminators are <= 0x%02X, safe to restore the bound"
              % SAFE_SCAN_BOUND)
    else:
        raised = [va for va, imm, _d in sb if imm is not None and imm > SAFE_SCAN_BOUND]
        print("  prerequisite: %d of 4 scan loops enumerate past id %d -- %s"
              % (len(raised), OLD_HI,
                 "this relocation is REQUIRED for them" if raised else
                 "not yet raised, this is pre-emptive"))

    want = VANILLA if undo else INSTALLED
    refresh = (state == INSTALLED and head == "ORIGINAL EDITED")

    if state == INSTALLED and head == "NEW TABLE EDITED":
        print("\nABORT: ids 0..169 of the NEW table at %08X have been edited, and the original at\n"
              "%08X is unchanged. Some other feature owns those bytes now. Overwriting them with\n"
              "a fresh copy of the original would silently revert it, so --apply refuses.\n"
              "If that feature is meant to be reverted, revert it with its own script first."
              % (NEW_TABLE, OLD_TABLE))
        return 2
    if state == INSTALLED and head.startswith("DRIFT"):
        print("\nABORT: %s\nCannot tell which side moved, so it is not safe to rewrite either."
              % head)
        return 2

    if state == want and not refresh:
        print("\nnothing to do -- already %s" % want)
        if tail_extra and not undo:
            print("  (ids 170..255 carry %d non-zero category byte(s); --apply preserves them, "
                  "--undo would not)" % len(tail_extra))
        return 0
    if refresh:
        print("\n⚠ ORIGINAL EDITED: the table at %08X has changed since this patch was applied,\n"
              "  where no reader looks any more. --apply re-copies ids 0..169 into %08X in place\n"
              "  and leaves ids 170..255 alone." % (OLD_TABLE, NEW_TABLE))
    if not (apply_ or undo):
        print("\nDRY RUN -- pass --apply to write (or --undo to restore)")
        return 0

    if undo and tail_extra:
        print("\n⚠ --undo restores the whole 256-byte region, so these ids 170..255 category\n"
              "  bytes will be DISCARDED: %s"
              % ", ".join("%d=%d" % (i, pv.d[pv.off(NEW_TABLE) + i]) for i in tail_extra))

    kill_aow()

    # ⚠ BACKUP GATING -- only ever snapshot a file PROVED unpatched, by a POSITIVE test that all
    # 23 sites hold the ORIGINAL values, never "no backup exists yet". On --undo the file is the
    # patched state by definition; on a refresh it is this script's own previous output. Either
    # would mint a .pre-* full of patched bytes that then sits on disk looking authoritative.
    bak = backup_path(path)
    if apply_ and state == VANILLA and not os.path.exists(bak):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, bak)
        print("backup written: %s (all 23 sites verified original)" % os.path.basename(bak))
    elif apply_ and not os.path.exists(bak):
        print("no backup taken: the file is not in the original state at these sites "
              "(a .pre-* full of patched bytes is worse than none).")

    to_base = OLD_TABLE if undo else NEW_TABLE
    to_hi = OLD_HI if undo else NEW_HI
    no = pv.off(NEW_TABLE)
    changed = 0

    if undo:
        data[no:no + NEW_LEN] = b"\0" * NEW_LEN
        what = "zeroed"
    else:
        live = bytes(data[pv.off(OLD_TABLE):pv.off(OLD_TABLE) + OLD_LEN])
        if state == VANILLA:
            assert bytes(data[no:no + NEW_LEN]) == b"\0" * NEW_LEN, \
                "destination %08X is not all zero -- refusing to write over it" % NEW_TABLE
            data[no:no + NEW_LEN] = live + b"\0" * (NEW_LEN - OLD_LEN)
            what = "written (%d live + %d zero)" % (OLD_LEN, NEW_LEN - OLD_LEN)
        else:                                     # refresh: ids 0..169 only, tail untouched
            data[no:no + OLD_LEN] = live
            what = "ids 0..169 refreshed in place (ids 170..255 left as they were)"

    for va in REFS:
        o = pv.off(va)
        if struct.unpack_from("<I", data, o)[0] != to_base:
            struct.pack_into("<I", data, o, to_base)
            changed += 1
    ate, _ordinal, _ename = pv.export_ate(EXPORT_NAME)
    if struct.unpack_from("<I", data, ate)[0] != to_base - pv.base:
        struct.pack_into("<I", data, ate, to_base - pv.base)
        changed += 1
    for va, _desc in LIMITS:
        o = pv.off(va) + 4
        if struct.unpack_from("<I", data, o)[0] != to_hi:
            struct.pack_into("<I", data, o, to_hi)
            changed += 1
    print("%d of 23 site(s) rewritten; table %s" % (changed, what))

    atomic_write(path, data)
    print("wrote %s" % MODULE)

    # ---- read back from disk and re-verify, including .reloc coverage after the write
    pv2 = PEView(bytearray(open(path, "rb").read()))
    st2, head2, _t2 = classify(pv2, path, verbose=False)
    print("read-back STATE: %s  (table ids 0..169: %s)" % (st2.upper(), head2))
    assert st2 == want, "read-back state is %s, expected %s" % (st2, want)
    if not undo:
        assert head2 == "populated", "read-back table head is %s" % head2
    missing = [va for va in REFS if va not in pv2.relocs()]
    assert not missing, "references lost their .reloc entries: %s" % missing
    print("read-back verified: all 23 sites, and all %d VA references still carry a .reloc entry."
          % len(REFS))

    if undo:
        print("\nundone surgically -- no backup was touched.")
        return 0

    print("""
APPLIED, UNTESTED -- this script cannot confirm anything in game.

NEEDS THE USER'S IN-GAME TEST:
  1. !! THE ACCEPTANCE TEST: replay the battle that produced "Error during Create Unit List"
     (AI turn, priest heroes present). It must not appear.
  2. Fight a tactical battle against the AI with units carrying ids 0xAA..0xB2 (Magebane,
     Drillmaster, Evoker, Conjurer, Enchanter, Ritualist, Shield, Reforming Flesh, Embrittled).
     The AI now enumerates them without a range check; watch for changed, not broken, scoring.
  3. Confirm no ability's behaviour changed: every new entry is category 0 ("not an AI combat
     action"), which is what the AI would have read for these ids had the table been long
     enough all along.""")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
