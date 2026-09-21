"""Panicked `0x6C` is removed the moment the unit takes damage.

Any damage that actually lands clears Panic -- no threshold, no source filter.  A miss never
reaches this code at all (the strike only calls DoDamage on a hit) and a fully-absorbed hit
arrives with EDX = 0, so "only a landed blow clears it" falls out of the hook site for free.

    hook   AoWE.TCombatObject.ExecuteDamage @0x55726C58   (VMT slot +0x124)
    cave   0x55829000  (reservation 0x55829000-0x558290FF)
    file   AoWEPACK.dpl only

One body serves all four combat classes *inside this DLL* -- `TCombatObject` VMT `0x557158EC`,
`TCombatUnit` `0x55715A94`, `TCombatWall` `0x55715C40`, `TFastCombatUnit` `0x5571D4BC` -- and a
scan of `AoWEPACK.dpl` finds the dword `0x55726C58` at exactly those four `+0x124` slots and
nowhere else.  So the single hook covers melee (normal / round / retaliation / free swing), ranged,
breath, touch, every `TDamageCA` and spell damage path, self-destruct, Command CA damage, the
Burning and Decay combat ticks, **and auto-resolve** (`TFastCombatUnit` overrides neither
`ExecuteDamage` nor `GetAbilityOwner`).  `AoW.exe` and `aowInt.dpl` hold no reference at all.

⚠ **`AoWTCPCK.dpl` DOES override `+0x124`** -- and a same-module dword scan cannot see it, because
the overriding VMT slot holds a *local* address.  `AoWTC.TTacticalCombatUnit` (VMT `0x00412B4C`,
instsize `0x68`) carries `+0x124 = 0x00420250`, its own `ExecuteDamage`:

    00420250  push ebp / mov ebp,esp / add esp,-0x4c
    00420256  jmp  0x437FE0        <- build_facing_retal.py cave; stores [ebp-4]=eax, [ebp-8]=edx
    0042025D  push ebp / call 0x420048 / pop ecx
    00420264  mov  edx, [ebp-8]    ; the ORIGINAL damage, unmodified
    00420267  mov  eax, [ebp-4]    ; the object
    0042026A  call 0x40256C        ; -> AoWEPACK.dpl!AoWE.TCombatObject.ExecuteDamage (our hook)

**Coverage is intact**: the override is a wrapper that delegates with the damage still in EDX, so
the patched body runs on the tactical path too, and there is no second binary to keep in lockstep.
⭐ The reusable lesson: **a cross-module override is invisible to a same-module dword scan.**  To
find one, enumerate the other module's VMTs by their self-pointer at `VMT-0x40` and read the slot.
Done here for all 78 AoWTCPCK VMTs: `TTacticalCombatUnit` is the only class occupying `+0x124`, and
its `+0xB8` resolves to `AoWEPACK.dpl!AoWE.TCombatUnit.GetAbilityOwner` (not overridden either).

⚠ **Forward hazard -- `build_facing_retal.py` owns `0x00420256 -> 0x00437FE0` inside that wrapper.**
Anything that rewrites `TTacticalCombatUnit.ExecuteDamage` interacts with that script.

Companion feature, and a forward hazard -- `build_panic_nomelee.py` gates Panicked at six
"may I initiate melee?" sites (caves `0x55828000` / `0x55828040` in this DLL, `0x00438300`..`0x004383C0`
in AoWTCPCK.dpl).  Keep the two scripts separate, for reasons that are about the features and not
about the code: they answer different questions (that one GATES a permission predicate and returns to
one of two branch targets; this one REMOVES the status as a side effect of a damage path), they are
separately tunable in play -- no-melee makes Panic matter, clear-on-damage makes it short, and the
owner may well want one without the other -- and each therefore needs its own `--undo` and its own
in-game checklist.  Reverting either leaves the other working.

## Why the cave looks the way it does

`TDurationAbility.CombatDone @0x55764E00` is the vanilla model, instruction for instruction --
`mov eax,<combat object>; mov edx,[eax]; call [edx+0xB8]` to reach the ability owner, then
`mov edx,<id>; mov ecx,[eax]; call [ecx+0x98]` to remove.  This cave is that, plus two nil/present
guards vanilla does not need in its own context.

- **`GetAbilityOwner` (`+0xB8`), not `GetAbilityEnabled` (`+0xA8`).**  `+0xA8` returns false both
  for "the ability is disabled" and for "there is no owner", and the `+0xB0` follow-up is not
  nil-guarded.  Testing `+0xB8`'s result is also what makes walls safe with no `IsClass`:
  `TCombatObject.GetAbilityOwner @0x557268D0` is `xor eax,eax / ret`, and `TCombatWall` inherits it
  (live `TCombatWall+0xB8 = 0x557268D0`), so a wall hit falls straight out of the cave.
  `TCombatUnit.GetAbilityOwner @0x55725000` is `mov eax,[eax+0x4C] / ret`, which can itself be nil
  -- hence the `test eax,eax`.  The two `0x4C`s in this feature never collide: `TCombatObject` has
  instsize `0x4C` (`[VMT-0x1C]`), so it has no `+0x4C` *field* to misread, and the cave's `+0x4C` is
  a VMT slot on the *owner*, not on the combat object.

- **The `GetAbSet` (`+0x4C`) pre-check.**  `ExecuteDamage` is the hottest path in combat and also
  runs inside auto-resolve batch simulation.  ⚠ The cost it avoids is **not** a `Changed()` recompute
  -- `Changed()` would not fire.  `TAbilityOwner.RemoveAbility @0x5574F5EC` gates it on `Remove`'s
  result (`5574F60E mov ebx,eax / test bl,bl / je 0x5574F61E`, skipping `call [edx+0x90]`), and
  `TDurationAbility.Remove @0x557650D8` returns 0 on the nil-data path (`0x55765119 xor ebx,ebx`).
  The real cost is an allocation: on that same nil-data path `Remove` still calls
  `TAbility.SetAb(owner, 0x6C, 0)` @`0x5574E718` -> `TCustomAbilityList.SetAbSet @0x5574E0BC`, whose
  `id >= AbCount` arm (`cmp edx,[eax+0xC] / jae`) falls through to `SetAbCount(0x6D)` @`0x5574E0F8`
  and grows the bitset -- `System.@ReallocMem` @`0x5574E138` plus a `@FillChar` zero-fill whenever
  the byte count moves.  Without the pre-check every unit in the game takes a bitset realloc on its
  first damaging hit.  `+0x4C` is one virtual call returning a byte from an id-indexed bitset
  (`TCustomAbilityList.GetAbSet @0x5574E0E0`: `cmp edx,[eax+0xC]` / `bt [eax+8],edx`) and is the
  same predicate `TAbilityOwner.TriggerCombatDone @0x5574FEC4` uses.  `THero` overrides it
  (`THero.GetAbSet @0x55788104`) with a tail call to the same body, so it stays **self-only** --
  correct here, because `0x6C` can never come from an item.

- **Removal primitive.**  `owner->vmt[0x98](owner, 0x6C)` -> `TAbstractUnit.RemoveAbility
  @0x5577F6EC` -> `TAbilityOwner.RemoveAbility @0x5574F5EC` -> `TDurationAbility.Remove
  @0x557650D8` -> `RemoveAbilityData` -> `Changed()`.  Exactly the call `THealingAbility.HealUnit
  @0x5576C41C` and `TRemedy.ExecuteSpell` already make against `0x6C`, and exactly the one
  `TDurationAbility.CombatDone` makes at battle end.  **`Changed()` is called by that chain
  itself, so no `build_debuffcache.py`-style stat-cache follow-up is needed.**  Safe when the unit
  is not panicked: `Remove` handles `data == nil`, returns false, and `Changed()` is skipped.
  `THero` does not override `+0x98` (live `THero+0x98 = 0x5577F6EC`, same as `TUnit`).
  ⚠ `+0x98` on a *`TCombatObject`* is `GetExperience @0x55726894` -- you must go through
  `GetAbilityOwner` first, and getting it backwards is silent.

## Ordering -- no discriminator needed, and adding one would be wrong

Live-verified in `TStrikeCA.Execute`: `call [ebp+0x108]` (DoDamage -> ExecuteDamage) at
`0x55766769` runs before the Panicked grant in the same function -- **136 bytes** to the
`mov edx,0x6C` @`0x557667F1`, **151 bytes** to the `call [ecx+0xD0]` @`0x55766800` that applies it.
The hook therefore fires strictly before
the grant and Cause Fear works unchanged.  Multi-strike rounds are self-consistent: strike 2's
damage clears strike 1's grant, then re-grants.  Both Terror CAs (`0x557F990C`, `0x557F977C`)
apply `0x6C` and deal no damage in the same CA.

## Site choice: entry, not the tail

The documented fallback is `0x55726CCF` (`8B C5 5D 5F 5E`, exactly 5 bytes, reloc-free, ESI =
object, EBP = post-clamp effective damage).  Both sites sit in this same function body, so they get
identical coverage -- the AoWTCPCK wrapper above delegates into the whole of it, and the choice
turns on object lifetime alone.  The tail is *not* used, because it runs after the lethal-blow
`DestroyObject` call at `0x55726CC9`, where `GetAbilityOwner` can hand back a detached pointer.
At the entry site the object is alive by construction, and `Changed()` runs before
`SetHitPoints` rather than after `DestroyObject`.  `TUnit.Changed @0x55782B34` is four
`GetAbXxxAll` aggregations plus `TAbstractUnit.Changed` (morale/strength/enchanted recompute, then
a `TAoWHSMap.UnitChanged` notify-event) and `THero.Changed @0x55786BDC` adds only
`THeroControl.HeroChanged`; nothing in either re-enters `TCombatObject`.

## Traps hit while building this

- `.reloc` is clear across `0x55726C58`-`0x55726C5D` (nearest entries `0x55726C6F` and
  `0x55726CA9`).  ⚠ **Do not relocate the hook to `0x55726CA8`** -- it sits directly on the
  `0x55726CA9` reloc and the loader would add the rebase delta into the `E9` displacement.  The
  script re-runs the `.reloc` scan on every invocation and aborts on a hit.
- The only patched byte inside this function is `0x55726C66` (`cmp ebx,0x32` -> `0x7F`,
  `build_burning_sailing.py`), twelve bytes past the hook window and untouched here.
- Keystone rejects `;` comments in the assembly source, and `mov edx,0x6C` must come out as
  `BA 6C 00 00 00` (five bytes) -- the standing imm8 trap.  `--dis` exists to read that back.

RNG: the cave adds no draw and inherits none.  `ExecuteDamage`, `GetAbilityOwner`, `GetAbSet`,
`RemoveAbility`, `Remove`, `RemoveAbilityData` and `Changed` are in neither the SYNC nor the RAW
list, so there is nothing to pick.

Usage:
    python build_scripts/build_panic_cleardamage.py            # verify current state (dry run)
    python build_scripts/build_panic_cleardamage.py --dis      # + disassemble the cave
    python build_scripts/build_panic_cleardamage.py --apply    # write
    python build_scripts/build_panic_cleardamage.py --undo     # surgical revert
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys

import capstone
import keystone

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

FEATURE = "paniccleardamage"
TARGET_NAME = "AoWEPACK.dpl"
PRISTINE = os.path.join(GAME, "Modding Resources", "AoWEPACK_original_backup.dpl")

PANICKED = 0x6C                 # ability id, applied by Cause Fear 0x33 and both Terror CAs

HOOK = 0x55726C58               # AoWE.TCombatObject.ExecuteDamage
HOOK_LEN = 6                    # push ebx/esi/edi/ebp + mov ebx,edx -> clean boundary
RESUME = 0x55726C5E             # mov esi, eax
VANILLA_HOOK = bytes([0x53, 0x56, 0x57, 0x55, 0x8B, 0xDA])

CAVE = 0x55829000               # reservation 0x55829000-0x558290FF
CAVE_ZONE = 0x100

# virtual slots, all on the object the slot's own class defines
VMT_GETABILITYOWNER = 0xB8      # TCombatObject -- nil for walls
VMT_GETABSET        = 0x4C      # TAbilityOwner -- self-only presence bit
VMT_REMOVEABILITY   = 0x98      # TAbilityOwner -- removes + calls Changed()

LOCKING = ("AoW", "AoWCompat", "AoWDevEd", "AoWEd")


# ---------------------------------------------------------------------------
# minimal PE helper (VA -> file offset is PER SECTION)
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

    def off(self, va):
        rva = va - self.image_base
        for name, vaddr, vsize, raw, rawsz in self.sections:
            if vaddr <= rva < vaddr + max(vsize, rawsz):
                o = raw + (rva - vaddr)
                if o >= len(self.data):
                    raise SystemExit(f"{self.path}: VA {va:#x} outside raw data")
                return o
        raise SystemExit(f"{self.path}: VA {va:#x} in no section")

    def read(self, va, n):
        o = self.off(va)
        return bytes(self.data[o:o + n])

    def write(self, va, blob):
        o = self.off(va)
        self.data[o:o + len(blob)] = blob

    def section_of(self, va):
        rva = va - self.image_base
        for s in self.sections:
            if s[1] <= rva < s[1] + max(s[2], s[4]):
                return s
        return None

    def relocs_in(self, lo, hi):
        """Every .reloc target VA in [lo, hi).  Overwriting one corrupts the image at load."""
        rva, size = struct.unpack_from("<II", self.data, self.datadir + 5 * 8)
        if not rva or not size:
            return []
        p = self.off(self.image_base + rva)
        end = p + size
        hits = []
        while p < end:
            page, blk = struct.unpack_from("<II", self.data, p)
            if blk < 8:
                break
            for i in range((blk - 8) // 2):
                e = struct.unpack_from("<H", self.data, p + 8 + i * 2)[0]
                if e >> 12 == 0:            # IMAGE_REL_BASED_ABSOLUTE = padding
                    continue
                va = self.image_base + page + (e & 0xFFF)
                if lo <= va < hi:
                    hits.append(va)
            p += blk
        return sorted(hits)

    def save(self):
        with open(self.path, "wb") as fh:
            fh.write(self.data)


# ---------------------------------------------------------------------------
# the cave
# ---------------------------------------------------------------------------
def build_cave(cave):
    """Assemble at the final VA so keystone emits correct rel32s.  No ';' comments -- keystone
    rejects them.  Stack is balanced on all four exits; `pop` does not touch flags."""
    src = "\n".join([
        "push ebx",
        "push esi",
        "push edi",
        "push ebp",
        "mov ebx, edx",
        "test ebx, ebx",
        "jle out",
        "push eax",
        "mov ecx, [eax]",
        f"call dword ptr [ecx+{VMT_GETABILITYOWNER:#x}]",
        "test eax, eax",
        "jz popobj",
        "push eax",
        f"mov edx, {PANICKED:#x}",
        "mov ecx, [eax]",
        f"call dword ptr [ecx+{VMT_GETABSET:#x}]",
        "test al, al",
        "pop eax",
        "jz popobj",
        f"mov edx, {PANICKED:#x}",
        "mov ecx, [eax]",
        f"call dword ptr [ecx+{VMT_REMOVEABILITY:#x}]",
        "popobj:",
        "pop eax",
        "out:",
        f"jmp {RESUME:#x}",
    ])
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32)
    blob, _ = ks.asm(src, cave)
    blob = bytes(blob)
    if len(blob) > CAVE_ZONE:
        raise SystemExit(f"cave {len(blob)} B exceeds reservation {CAVE_ZONE} B")
    # keystone imm8 trap: `mov edx,0x6C` must be BA 6C 00 00 00, five bytes, twice.
    if blob.count(bytes([0xBA, PANICKED, 0x00, 0x00, 0x00])) != 2:
        raise SystemExit(
            "keystone did not emit `mov edx,0x6C` as BA 6C 00 00 00 twice -- imm8 trap. "
            f"blob = {blob.hex(' ').upper()}")
    return blob


def hook_bytes(cave):
    """E9 rel32 + nop padding to the instruction boundary at RESUME."""
    jmp = b"\xE9" + struct.pack("<i", cave - (HOOK + 5))
    return jmp + b"\x90" * (HOOK_LEN - len(jmp))


def disasm(blob, va, indent="      "):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    return "\n".join(f"{indent}{i.address:08X}  {i.mnemonic:<7s} {i.op_str}"
                     for i in md.disasm(blob, va))


def check_pic(blob, va, tag):
    """A .dpl cave must carry no absolute memory reference -- AoWEPACK never loads at its base."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    bad = []
    for ins in md.disasm(blob, va):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                bad.append(f"{ins.address:08X} {ins.mnemonic} {ins.op_str}")
    if bad:
        raise SystemExit(f"{tag}: cave is NOT position-independent:\n  " + "\n  ".join(bad))


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


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the patch")
    ap.add_argument("--undo", action="store_true", help="surgical revert (restore hook, zero cave)")
    ap.add_argument("--dis", "--show", dest="dis", action="store_true",
                    help="disassemble the cave and the hook site")
    args = ap.parse_args()

    if args.apply and args.undo:
        raise SystemExit("--apply and --undo are mutually exclusive")

    path = os.path.join(GAME, TARGET_NAME)
    if not os.path.isfile(path):
        raise SystemExit(f"missing {path}")

    blob = build_cave(CAVE)
    check_pic(blob, CAVE, "paniccleardamage")
    hook = hook_bytes(CAVE)

    if args.apply or args.undo:
        kill_game()

    pe = PEFile(path)
    sec = pe.section_of(CAVE)
    print(f"=== {TARGET_NAME}  (image base {pe.image_base:#x}) ===")
    print(f"  hook  {HOOK:#010x}  AoWE.TCombatObject.ExecuteDamage  ({HOOK_LEN} B displaced, "
          f"resume {RESUME:#010x})")
    print(f"  cave  {CAVE:#010x}  {len(blob)} B in {sec[0]}  "
          f"(reservation {CAVE:#x}-{CAVE + CAVE_ZONE - 1:#x})")

    # --- standing safety scans, every run -----------------------------------
    rel = pe.relocs_in(HOOK, HOOK + HOOK_LEN)
    if rel:
        raise SystemExit(f"ABORT: .reloc entry inside the hook window: "
                         + ", ".join(f"{v:#x}" for v in rel))
    rel = pe.relocs_in(CAVE, CAVE + CAVE_ZONE)
    if rel:
        raise SystemExit(f"ABORT: .reloc entry inside the cave reservation: "
                         + ", ".join(f"{v:#x}" for v in rel))
    print(f"  .reloc: clear across the hook window and the cave reservation")

    live_hook = pe.read(HOOK, HOOK_LEN)
    live_cave = pe.read(CAVE, CAVE_ZONE)
    if live_hook == VANILLA_HOOK:
        state = "vanilla"
    elif live_hook == hook and live_cave[:len(blob)] == blob:
        state = "installed"
    elif live_hook == hook:
        state = "retune"          # our hook, a different cave body (constants changed)
    else:
        state = "foreign"
    print(f"  state: {state}   (hook now {live_hook.hex(' ').upper()})")

    if args.dis:
        print("\n  --- cave ---")
        print(disasm(blob, CAVE))
        print("\n  --- hook site as it would read after --apply ---")
        print(disasm(hook + pe.read(RESUME, 10), HOOK))

    if state == "foreign":
        raise SystemExit(
            f"{TARGET_NAME}: {HOOK:#x} holds bytes that are neither vanilla nor ours -- "
            "another patch owns this site. Aborting without writing.")

    # --- undo ---------------------------------------------------------------
    if args.undo:
        if state == "vanilla":
            print("  nothing to undo (already vanilla)")
            return
        pe.write(HOOK, VANILLA_HOOK)
        pe.write(CAVE, b"\0" * CAVE_ZONE)
        pe.save()
        print("  UNDONE (hook restored, cave reservation zeroed) -- no backup touched")
        return

    if state == "installed":
        print("  already installed, bytes verified identical -- nothing to do")
        return

    # --- verify-before-write ------------------------------------------------
    # accept the zone if it is all zero (fresh) or already carries our body (re-tune);
    # in both cases everything past the new blob must be zero.
    if state == "vanilla" and live_cave != b"\0" * CAVE_ZONE:
        raise SystemExit(
            f"cave zone {CAVE:#x} is not free (first bytes "
            f"{live_cave[:16].hex(' ').upper()}). Aborting without writing.")
    if live_cave[len(blob):] != b"\0" * (CAVE_ZONE - len(blob)):
        raise SystemExit(
            f"the growth zone {CAVE + len(blob):#x}-{CAVE + CAVE_ZONE - 1:#x} is not zero. "
            "Aborting without writing.")

    if not args.apply:
        print("\n  DRY RUN -- nothing written. Re-run with --apply.")
        return

    # --- backup, gated on a POSITIVE test that this file is unpatched HERE ---
    # A .pre-* snapshot must never be minted from our own previous output: on the re-tune path
    # the live bytes ARE our last write.  Only the vanilla state proves freshness, and it is
    # checked against the pristine reference DLL, not against the absence of a backup file.
    if state == "vanilla":
        fresh = live_hook == VANILLA_HOOK and live_cave == b"\0" * CAVE_ZONE
        if os.path.isfile(PRISTINE):
            ref = PEFile(PRISTINE)
            fresh = fresh and ref.read(HOOK, HOOK_LEN) == live_hook \
                          and ref.read(CAVE, CAVE_ZONE) == live_cave
        else:
            print(f"  note: pristine reference missing ({PRISTINE}) -- "
                  "freshness proved from the vanilla byte pattern alone")
        if fresh:
            backup_dir = os.path.join(GAME, "backups")
            os.makedirs(backup_dir, exist_ok=True)
            backup = os.path.join(backup_dir, f"{TARGET_NAME}.pre-{FEATURE}")
            if not os.path.exists(backup):
                shutil.copy2(path, backup)
                print(f"  backup -> backups\\{os.path.basename(backup)}")
        else:
            print("  no backup minted -- this file is not provably unpatched at the hook site")
    else:
        print("  re-tune over an existing install -- rewriting the cave in place, no backup minted")

    pe.write(CAVE, blob + b"\0" * (CAVE_ZONE - len(blob)))
    pe.write(HOOK, hook)
    pe.save()
    print("  APPLIED")


if __name__ == "__main__":
    main()
