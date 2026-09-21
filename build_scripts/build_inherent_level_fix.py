#!/usr/bin/env python3
r"""
AoW1 bugfix -- Turn Undead and Dispel Magic can be bought/granted past level I again.

Two VMT dwords.  No cave, no hook, no assembler.

THE DEFECT
  `build_leadership_fix.py` repointed the two `GetAbLevel` call sites in
  `AoWE.TAbilityOwner.UpdateDefaultAbilities` (`0x5574F54D` template side, `0x5574F55B` unit
  side) at `cave_abinherent @0x5580F100`, which dispatches the ability's
  `VMT+0x94 GetInherentLevel` instead of `VMT+0x70 GetLevel`.  That is the right comparison --
  an effective level borrowed from a Leadership aura must not mask a grant -- but two ability
  classes override `GetLevel` and inherit the BASE `TAbility.GetInherentLevel @0x5574E954`,
  which is `xor eax,eax / ret`:

      AoWE..TTurnUndeadAbility    VMT 0x5571FDFC   +0x70 = 0x5576AE8C   +0x94 = 0x5574E954 (base)
      AoWE..TDispelMagicAbility   VMT 0x55721D78   +0x70 = 0x5576CEFC   +0x94 = 0x5574E954 (base)

  So both sides of the comparison return 0, the `jle` at `0x5574F565` is taken, and the
  ability-data record copy is skipped.  It only bites when the owner ALREADY holds the bit --
  the `je` at `0x5574F547` jumps straight to the grant otherwise -- i.e. buying level II or
  above: the points are deducted and no level is applied.  Medal rank-ups whose templates carry
  a Turn Undead or Dispel Magic level fail the same way.

THE FIX -- give each of those two classes its own getter in the inherent slot
      VA 0x5571FE90  (TTurnUndeadAbility  VMT+0x94)   0x5574E954 -> 0x5576AE8C
      VA 0x55721E0C  (TDispelMagicAbility VMT+0x94)   0x5574E954 -> 0x5576CEFC
  i.e. `+0x94` is set to the SAME function as that class's `+0x70`.

WHY THIS IS SAFE -- verified against the live DLL and both pristine references
  1. It restores exact VANILLA behaviour for these two abilities.  Vanilla's comparison went
     through `+0x84 TAbilityOwner.GetAbLevel` -> the ability's `+0x70 GetLevel` -> these very two
     functions.  Pointing `+0x94` at the same target makes the post-leadership_fix comparison
     vanilla-equivalent for Turn Undead / Dispel Magic, while Leadership and the other
     `TMultiLevelAbility` descendants keep the intended inherent comparison.
  2. `cave_abinherent` is the ONLY consumer of an ability's `GetInherentLevel`.  A scan of every
     EXECUTE section of `AoWEPACK.dpl` found 89 `call [reg+0x94]` sites; all but five are other
     class hierarchies (`+0x94` is `TAbilityOwner.ExpandAbility` on the `TAbstractUnit` tree, and
     unrelated slots elsewhere).  ⚠ Read the `GetInherentAbilityLevel` bullet below before trusting
     the word ONLY -- the DLL scan is complete, but the consumer reached THROUGH
     `GetInherentAbilityLevel` lives in the exes and this scan does not cover them.
     The five that dispatch `+0x94` on an ABILITY object are
     `TMultiLevelAbility.ExpandCost @0x557652EB`, `.CanExpand @0x5576532E`,
     `.GetSkillPoints @0x55765352`, `TAbstractUnit.GetInherentAbilityLevel @0x5577F5D1`, and
     `cave_abinherent @0x5580F128`.
       - The three `TMultiLevelAbility` methods can never see TU/DM: both classes override
         `GetSkillPoints` (`0x5576B12C` / `0x5576D174`), `CanExpand` (`0x5576B0F0` / `0x5576D138`),
         `ExpandCost` (`0x5576B0DC` / `0x5576D130`), `Expand` and `Remove` with their own
         implementations.  `GetInherentLevel` is the ONLY thing they inherit from the base.
       - `TAbstractUnit.GetInherentAbilityLevel @0x5577F5A8` (ability dispatch at `0x5577F5D1`)
         DOES have callers -- FOUR, and they are the second live consumer of this patch.
         ⚠⚠ THE TRAP: they are in the EXEs, and the first scan covered only
         `AoWEPACK.dpl` / `AoWTCPCK.dpl` / `aowInt.dpl`, where there is indeed no TAbstractUnit
         receiver (32 / 18 / 0 `call [reg+0xbc]` sites, all map, army, event-log, TSpell or
         VCL-event receivers). `AoWz.exe` and `AoWzCompat.exe` carry 13 each, of which 4 take a
         HERO receiver -- `THero` VMT `0x55711FEC + 0xBC` IS `GetInherentAbilityLevel`.
         **This is the project's own per-binary rule: verify the call path in EVERY binary, not
         just the one that owns the function.** Caught by QA 2026-09-10, after the analysis had
         already been called complete.

         All four sit in `THeroUpgradeDlg`, the hero level-up dialog, and each is a BEFORE/AFTER
         pair over the same ability id -- `[dlg+0x1d8]` = the hero as he was, `[dlg+0x1dc]` = the
         working copy being edited:

             00446AE5..00446B09  ability-list fill: levels equal -> print the plain label,
                                 differ -> print the cost delta
             00447185..004471AB  RemoveBtnClick: levels equal -> REFUSE to remove,
                                 differ -> allow, then TAbstractUnit.RemoveAbility (+0x98)

         Vanilla returned 0 from BOTH sides for TU/DM (the base stub), so the dialog always took
         the "equal" arm: the cost column showed the label, and Remove was permanently refused.
         After this patch both sides return the real record level, so a level bought in this
         dialog session prints a cost delta and can be un-bought.

         That is CORRECTIVE, not a regression, and it is the whole point of the before/after
         comparison: it enables Remove only for a level bought in THIS session and so protects
         levels the hero already held. It also makes TU/DM behave exactly like the six
         `MLA-94` classes (TMultiLevelAbility, TTransportAbility, TLeadershipAbility,
         TSpellCastingAbility, TVisionAbility, TMarksmanshipAbility), which have always taken the
         non-equal arm. ⚠ But it IS a behaviour change versus vanilla at a control that removes
         an ability, so safety argument (1) -- "restores exact vanilla behaviour" -- holds ONLY at
         `cave_abinherent`, where vanilla's `+0x84 GetAbLevel @0x5574FD44` is byte-identical to
         the cave but for `+0x70` vs `+0x94`. It does NOT hold here. The in-game checklist item
         about the Cost column and the Remove button exists to close exactly this.
         (Still unmeasured: that `[dlg+0x1d8]`/`[dlg+0x1dc]` really are a before/after pair of the
         same hero. Everything else about the site is confirmed by disassembly.)
       - `TAbility.fcValidRoundDistance+0x15 @0x5574E799` dispatches `+0x94` on a COMBAT-UNIT
         receiver (`esi`, whose `[esi+8]` is handed to `TFastCombat.GetRoundDistance`), not on an
         ability.
  3. Both target VMT slots carry `.reloc` entries (type 3 HIGHLOW, at `0x5571FE90` and
     `0x55721E0C`; 63,883 entries in the file), so a value swap stays rebase-correct -- only the
     value changes, the relocation is untouched.  Same idiom `build_leadership4.py` used to
     relocate the Leadership bonus tables.  The script re-runs that scan on every invocation.
  4. Both replacement functions are byte-identical to vanilla (checked against the game root's
     `AoWEPACK.dpl` and `Modding Resources/AoWEPACK_original_backup.dpl`), so we are not pointing
     the slot at modified code.  Re-checked on every invocation.
  5. A whole-image VMT walk (self-pointer at `VMT-0x40`, classname short-string at `VMT-0x20`),
     filtered to VMTs whose `+0x94` is an ability `GetInherentLevel`, finds EXACTLY these two
     classes with the "overridden `+0x70`, base `+0x94`" shape -- out of 82 ability VMTs.  That is
     `--audit`, and it runs as part of the no-args verify.  It is not a name regex, so an added
     ability with an unconventional class name cannot hide from it.

SEMANTIC NUANCE -- why each class's OWN getter, not `TMultiLevelAbility.GetInherentLevel`
  `TTurnUndeadAbility.GetLevel @0x5576AE8C` is behaviourally identical to
  `TMultiLevelAbility.GetInherentLevel @0x55765200`: `owner ? (rec ? rec[+0xC] : 0) : 0`.  Clean
  inherent semantics; either would have done.

  `TDispelMagicAbility.GetLevel @0x5576CEFC` differs in three ways, and they all matter:
    - it first tests `owner.GetAbSet(0x3C)` through the self-only `[ecx+0x4C]` and returns 0 when
      the bit is absent;
    - with the bit but NO record it returns **1** (`mov eax,1` @0x5576CF2A) -- vanilla's own item
      fallback;
    - it reads the level from **`[rec+0xD]`, not `[rec+0xC]`**.  For `TDispelMagicAbilityData`
      (ClassID `0x202CD`) `+0xC` is the ENABLED flag and `+0xD` is the level, so
      `TMultiLevelAbility.GetInherentLevel` would have read the WRONG BYTE for Dispel Magic even
      if it had been inherited.  That is the strongest argument for using each class's own getter.
  The "returns 1 when recordless" case is not a regression: vanilla's comparison reached the same
  function, so behaviour is unchanged from stock.

DEPENDENCY
  This fix exists only because `build_leadership_fix.py` is applied.  The script asserts both of
  its call sites still read `E8 <rel32> 90 90 90` resolving to `cave_abinherent @0x5580F100`, and
  refuses to write if they do not -- without that feature, `+0x94` is never queried on an ability
  and this patch would be dead weight.  `--undo` is still allowed in that state, so the two
  features can be reverted in either order.

REVERT -- use --undo
  `--undo` is surgical: it writes `0x5574E954` back into both slots and touches no backup, so it
  stays correct however many later features are stacked on the DLL.  It verifies before writing --
  each slot must read as either ours or vanilla -- and aborts on anything foreign.
  The `<game dir>\backups\AoWEPACK.dpl.pre-inherentlevelfix` snapshot is NOT a revert path: it is
  a WHOLE-FILE copy, so restoring it would destroy every feature applied to AoWEPACK.dpl after
  this one.  It is minted on `--apply` ONLY, and only when both slots still read vanilla, so it
  can never be a copy of this script's own output.

TARGET
  `<game dir>\Ziggurat\AoWEPACK.dpl` only -- that IS the live file, so there is no
  ⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)  No exe or editor half: nothing outside this DLL queries an
  ability's `+0x94`.

RNG: no draw added, none inherited.  Not an RNG site at all -- this patch writes two function
pointers.

IN-GAME CHECKLIST (nobody has played this -- status ceiling is APPLIED, UNTESTED)
  1. Hero with Turn Undead I: buy Turn Undead II at level-up.  The points must be spent AND the
     ability must read II afterwards, and still read II after save/reload.
  2. Same for Turn Undead III, to prove it is not a one-off.
  3. Hero with Dispel Magic I -> buy Dispel Magic II.  Check the displayed level and that the
     dispel strength actually changed in combat (the `[rec+0xD]` byte is the one being read).
  4. A unit whose medal/rank template carries Turn Undead: rank it up and confirm the level lands
     (this is the non-hero path -- units cache stats, heroes recompute, so test both).
  5. Do 1 and 3 again WHILE the hero is stacked under a Leadership aura -- that is the condition
     `build_leadership_fix.py` exists for, and it must not reintroduce the masking.
  6. Confirm Leadership, Vision, Marksmanship and Spellcasting still level normally (they share
     the patched comparison but not the patched slots).

Usage:
    python build_scripts/build_inherent_level_fix.py             # verify current state (dry run)
    python build_scripts/build_inherent_level_fix.py --audit     # VMT walk only
    python build_scripts/build_inherent_level_fix.py --dis       # + disassemble the getters
    python build_scripts/build_inherent_level_fix.py --apply     # write
    python build_scripts/build_inherent_level_fix.py --undo      # surgical revert
"""

import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never the game root (rule 2026-09-03)

try:
    import zigexe
    LOCKING = tuple(zigexe.LOCKING_PROCESSES)
except ImportError:                      # sibling module missing -- stay runnable
    LOCKING = ("AoW", "AoWz", "AoWCompat", "AoWzCompat",
               "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup")

FEATURE = "inherentlevelfix"
TARGET_NAME = "AoWEPACK.dpl"
BACKUP_NAME = TARGET_NAME + ".pre-" + FEATURE

#: pristine references, in preference order.  The vanilla game ROOT is the baseline (2026-09-09);
#: the workshop copy is belt-and-braces and byte-identical to it.
PRISTINE = [
    os.path.join(GAME, os.pardir, TARGET_NAME),
    os.path.join(GAME, "Modding Resources", "AoWEPACK_original_backup.dpl"),
]

# --- ability VMT slots -------------------------------------------------------
SLOT_GETLEVEL = 0x70            # TAbility.GetLevel
SLOT_INHERENT = 0x94            # TAbility.GetInherentLevel   <-- the slot we rewrite
BASE_GETLEVEL = 0x5574E9B0      # TAbility.GetLevel            -- xor eax,eax / ret
BASE_INHERENT = 0x5574E954      # TAbility.GetInherentLevel     -- xor eax,eax / ret  (the bug)
MLA_INHERENT = 0x55765200       # TMultiLevelAbility.GetInherentLevel -- reads rec[+0xC]

#: (class, VMT, the function that must end up in +0x94, that function's byte length)
#: The length is the exact function extent, used for the vanilla byte-identity check:
#:   0x5576AE8C..0x5576AEB3 = 0x28   0x5576CEFC..0x5576CF3A = 0x3F
CLASSES = [
    ("AoWE..TTurnUndeadAbility",  0x5571FDFC, 0x5576AE8C, 0x28),
    ("AoWE..TDispelMagicAbility", 0x55721D78, 0x5576CEFC, 0x3F),
]

# --- the build_leadership_fix.py dependency ---------------------------------
LFIX_CAVE = 0x5580F100          # cave_abinherent -- dispatches +0x94 instead of +0x70
LFIX_SITES = [
    (0x5574F54D, "UpdateDefaultAbilities: template level"),
    (0x5574F55B, "UpdateDefaultAbilities: unit level"),
]
LFIX_SITE1_BYTES = bytes.fromhex("e8aefb0b00909090")   # byte-exact, as recorded
LFIX_VANILLA_SITE = bytes.fromhex("8b08ff9184000000")  # mov ecx,[eax]; call [ecx+0x84]
CAVE_DISPATCH = bytes.fromhex("ff91 94000000".replace(" ", ""))   # call dword ptr [ecx+0x94]


# ---------------------------------------------------------------------------
# minimal PE helper (VA -> file offset is PER SECTION -- never a flat delta)
# ---------------------------------------------------------------------------
class PEFile:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as fh:
            self.data = bytearray(fh.read())
        pe = struct.unpack_from("<I", self.data, 0x3C)[0]
        if self.data[pe:pe + 4] != b"PE\0\0":
            raise SystemExit(f"{path}: not a PE file")
        nsec = struct.unpack_from("<H", self.data, pe + 6)[0]
        opt = struct.unpack_from("<H", self.data, pe + 20)[0]
        self.opt_off = pe + 24
        self.image_base = struct.unpack_from("<I", self.data, self.opt_off + 28)[0]
        magic = struct.unpack_from("<H", self.data, self.opt_off)[0]
        self.datadir = self.opt_off + (96 if magic == 0x10B else 112)
        self.sections = []
        off = pe + 24 + opt
        for i in range(nsec):
            s = off + i * 40
            name = self.data[s:s + 8].rstrip(b"\0").decode("latin1")
            vsize, vaddr, rawsz, raw = struct.unpack_from("<IIII", self.data, s + 8)
            self.sections.append((name, vaddr, vsize, raw, rawsz))

    def try_off(self, va):
        """File offset for a VA, or None when it maps nowhere with raw bytes behind it."""
        rva = va - self.image_base
        for name, vaddr, vsize, raw, rawsz in self.sections:
            if vaddr <= rva < vaddr + max(vsize, rawsz):
                o = raw + (rva - vaddr)
                if raw and o + 4 <= len(self.data):
                    return o
                return None
        return None

    def off(self, va):
        o = self.try_off(va)
        if o is None:
            raise SystemExit(f"{self.path}: VA {va:#x} maps to no raw bytes")
        return o

    def read(self, va, n):
        o = self.off(va)
        return bytes(self.data[o:o + n])

    def dword(self, va):
        return struct.unpack_from("<I", self.data, self.off(va))[0]

    def try_dword(self, va):
        o = self.try_off(va)
        return None if o is None else struct.unpack_from("<I", self.data, o)[0]

    def write_dword(self, va, value):
        struct.pack_into("<I", self.data, self.off(va), value)

    def section_of(self, va):
        rva = va - self.image_base
        for s in self.sections:
            if s[1] <= rva < s[1] + max(s[2], s[4]):
                return s[0]
        return None

    def reloc_vas(self):
        """Every .reloc target VA in the file.  Overwriting a relocated byte-run corrupts the
        image at load; here we need the opposite guarantee -- that the slots ARE covered."""
        if getattr(self, "_relocs", None) is not None:
            return self._relocs
        rva, size = struct.unpack_from("<II", self.data, self.datadir + 5 * 8)
        out = set()
        if rva and size:
            p = self.off(self.image_base + rva)
            end = p + size
            while p < end:
                page, blk = struct.unpack_from("<II", self.data, p)
                if blk < 8:
                    break
                for i in range((blk - 8) // 2):
                    e = struct.unpack_from("<H", self.data, p + 8 + i * 2)[0]
                    if e >> 12 == 0:          # IMAGE_REL_BASED_ABSOLUTE = padding
                        continue
                    out.add(self.image_base + page + (e & 0xFFF))
                p += blk
        self._relocs = out
        return out

    def sha256(self):
        return hashlib.sha256(self.data).hexdigest()

    def save(self):
        with open(self.path, "wb") as fh:
            fh.write(self.data)


# ---------------------------------------------------------------------------
# the reusable audit -- walk every VMT, find the "overridden GetLevel, base
# GetInherentLevel" shape.  Run this after adding any new leveled ability.
# ---------------------------------------------------------------------------
def walk_vmts(pe):
    """Every Delphi VMT in the image: (classname, vmt VA, section).

    A VMT is identified structurally -- the self-pointer at `VMT-0x40` holds the VMT's own VA --
    and the class name is the short string `[VMT-0x20]` points at.  No name matching anywhere, so
    a class with an unconventional name cannot hide.
    """
    out = []
    for name, vaddr, vsize, raw, rawsz in pe.sections:
        if not raw or not rawsz or name in (".reloc", ".rsrc"):
            continue
        lo = raw
        hi = min(raw + max(vsize, rawsz), len(pe.data)) - 4
        secva = pe.image_base + vaddr
        for o in range(lo, hi, 4):
            va = secva + (o - raw)
            if struct.unpack_from("<I", pe.data, o)[0] != va + 0x40:
                continue
            vmt = va + 0x40
            nameptr = pe.try_dword(vmt - 0x20)
            if not nameptr:
                continue
            no = pe.try_off(nameptr)
            if no is None:
                continue
            ln = pe.data[no]
            if not 1 <= ln <= 63:
                continue
            raw_name = bytes(pe.data[no + 1:no + 1 + ln])
            if any(c < 0x20 or c > 0x7E for c in raw_name):
                continue
            out.append((raw_name.decode("latin1"), vmt, name))
    return out


def audit(pe, verbose=True):
    """Returns (shape_count, broken, fixed, n_ability_vmts, n_vmts).

    `shape_count` counts classes with the defect's SHAPE -- an overridden `+0x70` paired with an
    inherent slot that is either still the base stub (BROKEN) or this patch's value (FIXED).  It
    is 2 before and after applying, so the no-args verify can check it in either state.
    """
    new_targets = {new for _c, _v, new, _l in CLASSES}
    vmts = walk_vmts(pe)

    # Membership is decided by DESCENT, not by the value in +0x94.
    # ⚠ It used to be a value whitelist ({base, MLA's} | our targets), which silently drops any
    # future class that overrides +0x94 with its own function -- such a class would not be counted
    # as an ability VMT at all, so the ability total would fall while `shape count 2` stayed green
    # and the class went unexamined. Keying on the hierarchy cannot miss a descendant however its
    # slots are filled. (QA finding, 2026-09-10.)
    by_vmt = {vmt: cname for cname, vmt, _sec in vmts}
    tability = next((v for v, c in by_vmt.items() if c == "TAbility"), None)

    def descends_from_tability(vmt):
        """Walk the parent-class pointer at VMT-0x18 (a PPClass) up to TAbility."""
        seen, cur = set(), vmt
        while cur and cur not in seen:
            seen.add(cur)
            if cur == tability:
                return True
            pp = pe.try_dword(cur - 0x18)          # -> pointer to the parent's class pointer
            cur = pe.try_dword(pp) if pp else None
        return False

    broken, fixed, other, ability = [], [], [], 0
    for cname, vmt, _sec in vmts:
        s94 = pe.try_dword(vmt + SLOT_INHERENT)
        s70 = pe.try_dword(vmt + SLOT_GETLEVEL)
        if s94 is None or s70 is None:
            continue
        if tability is not None:
            if vmt != tability and not descends_from_tability(vmt):
                continue
        elif s94 not in ({BASE_INHERENT, MLA_INHERENT} | new_targets):
            continue                               # fallback if TAbility's VMT was not found
        ability += 1
        if s70 == BASE_GETLEVEL:
            continue                                  # plain ability: 0 vs 0 either way
        if s94 == BASE_INHERENT:
            broken.append((cname, vmt, s70, s94))
        elif s94 == s70 and s94 in new_targets:
            fixed.append((cname, vmt, s70, s94))
        elif s94 != MLA_INHERENT:
            # Overridden +0x70 with an inherent slot that is neither the base stub, nor
            # TMultiLevelAbility's, nor ours. Not the defect -- but nobody has checked that its
            # +0x94 reads the same byte its data class stores the level in, which is the trap
            # Dispel Magic embodies ([rec+0xD], not [rec+0xC]). Surface it rather than skip it.
            other.append((cname, vmt, s70, s94))
    if verbose:
        print(f"  --- audit: {len(vmts)} VMTs walked, {ability} with an ability GetInherentLevel ---")
        for cname, vmt, s70, s94 in broken:
            print(f"    BROKEN  {cname:<28s} VMT {vmt:08X}  +0x70 {s70:08X}  "
                  f"+0x94 {s94:08X} (base stub, returns 0)")
        for cname, vmt, s70, s94 in fixed:
            print(f"    FIXED   {cname:<28s} VMT {vmt:08X}  +0x70 {s70:08X}  +0x94 {s94:08X}")
        for cname, vmt, s70, s94 in other:
            print(f"    INFO    {cname:<28s} VMT {vmt:08X}  +0x70 {s70:08X}  +0x94 {s94:08X} "
                  f"(own inherent -- verify it reads the level byte its data class stores)")
        if not broken and not fixed:
            print("    no class has the 'overridden +0x70, base +0x94' shape")
    return len(broken) + len(fixed), broken, fixed, ability, len(vmts)


# ---------------------------------------------------------------------------
def disasm(blob, va, indent="      "):
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    return "\n".join(f"{indent}{i.address:08X}  {i.bytes.hex(' '):<18s}{i.mnemonic:<7s}{i.op_str}"
                     for i in md.disasm(blob, va))


def kill_game():
    """Standing authorization: game files are locked while any AoW binary runs."""
    # SCRATCH GUARD: AOW_GAME_DIR set => not the real install, so do not kill the user's game.
    if os.environ.get("AOW_GAME_DIR"):
        return
    if sys.platform != "win32":
        return
    names = "|".join(LOCKING)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         f"Get-Process | Where-Object {{ $_.ProcessName -match '^({names})$' }} | Stop-Process -Force"],
        capture_output=True)


def find_pristine():
    for p in PRISTINE:
        if os.path.isfile(p):
            return PEFile(p), os.path.normpath(p)
    return None, None


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--apply", action="store_true", help="write the two VMT dwords")
    ap.add_argument("--undo", action="store_true",
                    help="surgical revert (restore both slots to the base stub)")
    ap.add_argument("--audit", action="store_true",
                    help="VMT walk only: which classes have the defect's shape")
    ap.add_argument("--dis", "--show", dest="dis", action="store_true",
                    help="disassemble the getters, the cave and the call sites")
    args = ap.parse_args()

    if args.apply and args.undo:
        raise SystemExit("--apply and --undo are mutually exclusive")

    path = os.path.join(GAME, TARGET_NAME)
    if not os.path.isfile(path):
        raise SystemExit(f"missing {path}")

    if args.apply or args.undo:
        kill_game()

    pe = PEFile(path)
    print(f"=== {TARGET_NAME}  (image base {pe.image_base:#x})  sha256 {pe.sha256()} ===")
    print(f"    {os.path.normpath(path)}")

    if args.audit:
        n, broken, fixed, _ab, _v = audit(pe)
        print(f"  shape count {n} (expected 2: TTurnUndeadAbility, TDispelMagicAbility)")
        return 0 if n == 2 else 1

    # --- state of the two slots --------------------------------------------
    slots = []                       # (class, slot VA, vanilla, new, live)
    for cname, vmt, new, flen in CLASSES:
        sva = vmt + SLOT_INHERENT
        slots.append((cname, vmt, sva, BASE_INHERENT, new, flen, pe.dword(sva)))

    print("  slots:")
    for cname, vmt, sva, old, new, _flen, live in slots:
        tag = "vanilla" if live == old else ("ours" if live == new else "FOREIGN")
        print(f"    {sva:08X}  {cname:<28s} VMT{SLOT_INHERENT:#04x}  live {live:08X}  "
              f"[{tag}]  want {new:08X}")

    foreign = [s for s in slots if s[6] not in (s[3], s[4])]
    if foreign:
        for cname, _vmt, sva, old, new, _flen, live in foreign:
            print(f"  [x] {sva:08X} ({cname}) is neither vanilla nor ours\n"
                  f"        vanilla {old:08X}\n        ours    {new:08X}\n        got     {live:08X}")
        raise SystemExit("ABORT: foreign VMT slot value -- another patch owns it. Nothing written.")

    installed = all(s[6] == s[4] for s in slots)
    pristine_state = all(s[6] == s[3] for s in slots)
    state = "installed" if installed else ("vanilla" if pristine_state else "partial")
    print(f"  state: {state}")

    # --- standing safety re-assertions, every run --------------------------
    # (1) each class's +0x70 must BE the function we are about to put in +0x94
    for cname, vmt, _sva, _old, new, _flen, _live in slots:
        s70 = pe.dword(vmt + SLOT_GETLEVEL)
        if s70 != new:
            raise SystemExit(
                f"ABORT: {cname} VMT+0x70 is {s70:08X}, expected {new:08X} -- the class's own "
                "GetLevel has moved or been overridden by another patch. Nothing written.")
    print(f"  check: both classes' VMT+0x70 still equal the intended +0x94 value")

    # (2) both target slots must carry a .reloc entry, so a value swap stays rebase-correct
    relocs = pe.reloc_vas()
    missing = [s[2] for s in slots if s[2] not in relocs]
    if missing:
        raise SystemExit("ABORT: no .reloc coverage for " +
                         ", ".join(f"{v:#x}" for v in missing) +
                         " -- the slot would not be rebased. Nothing written.")
    print(f"  check: .reloc covers both slots ({len(relocs)} entries in the file)")

    # (3) both replacement functions must be byte-identical to vanilla
    ref, refpath = find_pristine()
    if ref is None:
        print("  [!] no pristine reference found -- skipped the byte-identity check on the "
              "replacement functions")
    else:
        for cname, _vmt, _sva, _old, new, flen, _live in slots:
            if pe.read(new, flen) != ref.read(new, flen):
                raise SystemExit(
                    f"ABORT: {cname} GetLevel @{new:08X} ({flen} B) differs from the pristine "
                    f"reference -- the slot would point at modified code. Nothing written.")
        print(f"  check: both replacement functions byte-identical to vanilla "
              f"({os.path.basename(refpath)})")

    # (4) build_leadership_fix.py must still be applied -- it is the only consumer of +0x94
    lfix_ok, lfix_msgs = True, []
    for i, (sva, desc) in enumerate(LFIX_SITES):
        cur = pe.read(sva, 8)
        if cur == LFIX_VANILLA_SITE:
            lfix_ok = False
            lfix_msgs.append(f"    {sva:08X} {desc}: VANILLA (build_leadership_fix.py not applied)")
            continue
        target = sva + 5 + struct.unpack_from("<i", cur, 1)[0]
        if cur[0] != 0xE8 or cur[5:] != b"\x90\x90\x90" or target != LFIX_CAVE:
            lfix_ok = False
            lfix_msgs.append(f"    {sva:08X} {desc}: unrecognised {cur.hex(' ').upper()}")
        if i == 0 and cur != LFIX_SITE1_BYTES:
            lfix_ok = False
            lfix_msgs.append(f"    {sva:08X} {desc}: expected {LFIX_SITE1_BYTES.hex(' ').upper()}, "
                             f"got {cur.hex(' ').upper()}")
    if lfix_ok:
        print(f"  check: build_leadership_fix.py applied -- both call sites -> "
              f"cave_abinherent {LFIX_CAVE:08X}")
        if CAVE_DISPATCH not in pe.read(LFIX_CAVE, 0x40):
            print(f"  [!] cave_abinherent does not contain `call dword ptr [ecx+0x94]` -- it may "
                  f"no longer dispatch the inherent slot; this patch would then be inert")
    else:
        print("  [!] build_leadership_fix.py is NOT applied as recorded:")
        for m in lfix_msgs:
            print(m)

    # --- audit (runs as part of the plain verify) --------------------------
    n, broken, fixed, n_ab, n_vmt = audit(pe)
    if n != 2:
        print(f"  [!] WARNING: shape count is {n}, expected 2. A new leveled ability may have "
              f"been added with an overridden +0x70 and no +0x94 -- extend CLASSES.")

    if args.dis:
        for cname, _vmt, _sva, _old, new, flen, _live in slots:
            print(f"\n  --- {cname}.GetLevel @{new:08X} ({flen} B) -- the new +0x94 target ---")
            print(disasm(pe.read(new, flen), new))
        print(f"\n  --- TAbility.GetInherentLevel @{BASE_INHERENT:08X} (the bug: returns 0) ---")
        print(disasm(pe.read(BASE_INHERENT, 3), BASE_INHERENT))
        print(f"\n  --- cave_abinherent @{LFIX_CAVE:08X} (build_leadership_fix.py) ---")
        print(disasm(pe.read(LFIX_CAVE, 0x31), LFIX_CAVE))
        for sva, desc in LFIX_SITES:
            print(f"\n  --- {desc} @{sva:08X} ---")
            print(disasm(pe.read(sva, 8), sva))

    # --- undo --------------------------------------------------------------
    if args.undo:
        if pristine_state:
            print("\n[= ] not applied -- nothing to undo")
            return 0
        for cname, _vmt, sva, old, _new, _flen, _live in slots:
            pe.write_dword(sva, old)
            print(f"[u ] {sva:08X} restored {old:08X}  ({cname} VMT+0x94 -> base stub)")
        try:
            pe.save()
        except PermissionError:
            raise SystemExit("[x] LOCKED -- an AoW binary still holds the DLL. Re-run.")
        print(f"    sha256 now {PEFile(path).sha256()}")
        print("\n[done] UNDONE -- both slots back to the base stub. No backup touched.")
        return 0

    # --- already done ------------------------------------------------------
    if installed:
        print("\n[= ] ALL ALREADY PATCHED -- both slots hold their class's own GetLevel.")
        return 0

    if not args.apply:
        print("\n[dry-run] verified: slots are vanilla, both getters check out. "
              "Re-run with --apply to write.")
        return 0

    # --- apply -------------------------------------------------------------
    if not lfix_ok:
        raise SystemExit(
            "ABORT: build_leadership_fix.py is not applied, so nothing queries an ability's "
            "VMT+0x94 and THIS PATCH WOULD DO NOTHING. Apply build_leadership_fix.py first (or "
            "leave both features off). Nothing written.")

    # Snapshot on --apply ONLY, and only from a file proven free of THIS feature, so it can never
    # be a copy of our own output.  It is not a revert path -- see the docstring.
    if pristine_state:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        bp = os.path.join(BACKUP_DIR, BACKUP_NAME)
        if not os.path.exists(bp):
            shutil.copy2(path, bp)
            print(f"[bak] {os.path.normpath(bp)}")
        else:
            print(f"[bak] {os.path.normpath(bp)} exists -- left alone")

    for cname, _vmt, sva, old, new, _flen, _live in slots:
        pe.write_dword(sva, new)
        print(f"[w ] {sva:08X} {old:08X} -> {new:08X}  ({cname} VMT+0x94)")
    try:
        pe.save()
    except PermissionError:
        raise SystemExit("[x] LOCKED -- an AoW binary still holds the DLL. Re-run.")
    after = PEFile(path)
    print(f"    sha256 now {after.sha256()}")
    n2, _b2, f2, _a2, _v2 = audit(after, verbose=False)
    print(f"    audit after write: shape count {n2}, FIXED {len(f2)}, BROKEN {n2 - len(f2)}")
    print("\n[done] Applied, UNTESTED. Revert: re-run with --undo (surgical, touches no backup).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
