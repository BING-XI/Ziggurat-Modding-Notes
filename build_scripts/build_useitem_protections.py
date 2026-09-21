#!/usr/bin/env python3
r"""Make Immunity and Protection abilities legal on **use/misc-slot** items (`itUse`).

    python build_scripts/build_useitem_protections.py            # dry run + verify current state
    python build_scripts/build_useitem_protections.py --apply
    python build_scripts/build_useitem_protections.py --undo

================================================================================
WHAT WAS ACTUALLY MISSING (only half of what it looks like)
================================================================================
Ability legality is a bitmask handshake, `TAbility.CanExpand @0x5574E8B8`:

    owner.GetAbilitySelectionTypes(vmt+0x8C)  &  ability[+0x20]

`TItem.GetAbilitySelectionTypes @0x557944AC` returns ONE bit chosen by item type —
`itUse` is **bit 6 = 0x0040** (`astUseItem`). So an ability may live on a use item only if bit 6
is set in its mask. Measured live in `Release/Ability.pfs` (tag 9, record = ability id + 10):

    Immunities  0x06..0x0C  mask 0x03FF   -> bit 6 ALREADY SET
                0x0D        mask 0x027F   -> bit 6 ALREADY SET
    Protections 0x46..0x4D  mask 0x03BF   -> bit 6 CLEAR   <-- 0x03FF minus exactly 0x0040

**So immunities were already legal on use items and only the protections were excluded** — the
vanilla masks say so deliberately, 0x03BF being 0x03FF with the one bit knocked out. This script
sets bit 6 on all sixteen; the eight immunity rows verify as already-correct and exist so a later
AoWDevEd re-save that cleared them would be caught.

⚠ **The runtime half is already done and is NOT this script's job.** `build_useitems.py` (applied
2026-08-02) replaced the three `THeroItems` aggregators with caves that also walk the hero's
**inventory** (`hero+0x74`, gated `item+0x34 == 6` = itUse):

    THero.GetImmunityTypes  @0x55786FD8 = TAbstractUnit.GetImmunityTypes | THeroItems.GetImmunityTypes
    THeroItems.GetImmunityTypes  @0x55786470 -> cave 0x558152C0   (equipped loop + inventory loop)
    THeroItems.GetProtectionTypes@0x557864C0 -> cave 0x55815350   (same shape)

So a protection sitting on a use item already takes effect — there was simply no way to author one,
because the editor's picker honours the mask. This script only opens the authoring gate.

⚠ **The data file wins over the DLL.** `TAbilityControl.ReadWrite @0x55750164` loads `Ability.pfs`
record `id+10` tag 9 into `[ability+0x20]` *after* `CreateEnhancementAbility` registers its own
value — measured: all 21 vanilla registration sites disagree with their own record. Patching the
DLL would change nothing on screen, so this is a pure `.pfs` edit.

⚠ The mask is **not enforced at runtime for items**: `ValidateOwnerTypeAbilities @0x5574F154`'s only
caller is `TUnitResource.ReadWrite`. It gates the editor/level-up picker, i.e. what you can *author*.
Nothing already on an item is stripped by narrowing it again, so `--undo` is safe.

Not touched: `0xA7 Fire Protection Enchantment` — that is the spell-applied enchantment, not an
item-authorable ability.

The write is a length-preserving u16, so no record directory or index offset moves; only the
trailing CRC-32 needs repairing. Backup `Release/Ability.pfs.pre-useitemprot`; revert with `--undo`.
"""

import argparse
import importlib.util
import os
import shutil
import struct
import sys
import zlib

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

ABIL_PFS = os.path.join(GAME, "Release", "Ability.pfs")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(ABIL_PFS) + ".pre-useitemprot")
PFS_RESIDUE = 0x2144DF1C          # crc32(d[4:]) of an intact .pfs -- see PFS_Format_CRC.md

USE_BIT = 0x0040                  # astUseItem, bit 6
REC_BASE = 10                     # Ability.pfs record id = ability id + 10

# (ability id, name, ORIGINAL vanilla mask as shipped)
# ⚠ This is the ORIGINAL, not "the original with bit 6 knocked off". `--undo` restores exactly this
# value, so the eight immunity rows -- whose vanilla masks ALREADY carry bit 6 -- are no-ops in both
# directions. An earlier draft stored `orig & ~USE_BIT`, and its `--undo` therefore *cleared* the bit
# on the immunities: it narrowed eight masks that had never been widened. Caught by diffing the
# undone file against the backup; the round trip is byte-exact now.
TARGETS = [
    (0x06, "Magic Immunity",        0x03FF),
    (0x07, "Fire Immunity",         0x03FF),
    (0x08, "Cold Immunity",         0x03FF),
    (0x09, "Lightning Immunity",    0x03FF),
    (0x0A, "Poison Immunity",       0x03FF),
    (0x0B, "Death Immunity",        0x03FF),
    (0x0C, "Holy Immunity",         0x03FF),
    (0x0D, "Physical Immunity",     0x027F),
    (0x46, "Death Protection",      0x03BF),
    (0x47, "Fire Protection",       0x03BF),
    (0x48, "Holy Protection",       0x03BF),
    (0x49, "Poison Protection",     0x03BF),
    (0x4A, "Lightning Protection",  0x03BF),
    (0x4B, "Magic Protection",      0x03BF),
    (0x4C, "Cold Protection",       0x03BF),
    (0x4D, "Physical Protection",   0x03BF),
]

BITS = [(0x001, "unit"), (0x002, "Head"), (0x004, "Torso"), (0x008, "Attack"), (0x010, "Defense"),
        (0x020, "Ring"), (0x040, "USE"), (0x080, "CustLeader"), (0x100, "HeroUp"), (0x200, "Editor")]


def _pfs_module():
    spec = importlib.util.spec_from_file_location(
        "pfs", os.path.join(GAME, "Modding Resources", "re_tools", "pfs.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tag9_offsets(d):
    """{ability id: file offset of its record's tag-9 word}. Derived every run, never hard-coded --
    AoWDevEd rewrites this file whole and every offset inside it moves."""
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        sys.exit("ABORT: Ability.pfs CRC residue is %#010x, expected %#010x -- the file is ALREADY\n"
                 "       damaged, before this script has edited anything. Refusing to touch it:\n"
                 "       repairing the CRC over the damage would stamp it valid and destroy the\n"
                 "       evidence. Restore Release/Ability.pfs or re-save it from AoWDevEd."
                 % (zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF, PFS_RESIDUE))
    recs = _pfs_module().parse_index(bytes(d))
    starts, at = {}, len(d)
    for rid, body in reversed(recs):
        at -= len(body)
        starts[rid] = at
    bodies = dict(recs)
    out = {}
    for abid, name, _orig in TARGETS:
        key = abid + REC_BASE
        if key not in starts:
            sys.exit("ABORT: Ability.pfs has no record %d for %s (%#04x)." % (key, name, abid))
        a, body = starts[key], bodies[key]
        p = 1 + (4 if body[0] & 0x80 else 0)
        ent = [(body[1 + 2 * k], body[2 + 2 * k]) for k in range(body[0] & 0x7f)]
        p += 2 * len(ent)
        for k in range(struct.unpack_from("<I", body, 1)[0] if body[0] & 0x80 else 0):
            t, o = struct.unpack_from("<II", body, p + 8 * k)
            ent.append((t, o))
        p += 8 * (len(ent) - (body[0] & 0x7f))
        for t, o in ent:
            if t == 9:
                out[abid] = a + p + o
                break
        else:
            sys.exit("ABORT: record %d (%s) carries no tag 9 (selection mask)." % (key, name))
    return out


def spell(mask):
    return "|".join(n for b, n in BITS if mask & b) or "(none)"


def main():
    ap = argparse.ArgumentParser(
        description="Allow Immunity/Protection abilities on use-slot (itUse) items")
    ap.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    ap.add_argument("--undo", action="store_true",
                    help="clear bit 6 again on every row (restores the vanilla masks)")
    args = ap.parse_args()

    if not os.path.isfile(ABIL_PFS):
        sys.exit("ERROR: not found: %s\n(set AOW_GAME_DIR)" % ABIL_PFS)
    d = bytearray(open(ABIL_PFS, "rb").read())
    offs = tag9_offsets(d)

    print("build_useitem_protections  (%s)" % ("undo" if args.undo else "apply"))
    todo = []
    for abid, name, orig in TARGETS:
        o = offs[abid]
        cur = struct.unpack_from("<H", d, o)[0]
        if cur not in (orig, orig | USE_BIT):
            sys.exit("ABORT: %s (%#04x) mask is %#06x, expected %#06x (vanilla) or %#06x (widened).\n"
                     "       Someone re-tuned the mask (an AoWDevEd save?). Review the TARGETS\n"
                     "       table before running again."
                     % (name, abid, cur, orig, orig | USE_BIT))
        want = (orig if args.undo else orig | USE_BIT)
        state = "  already" if cur == want else "  %#06x ->" % cur
        print("  %#04x %-22s %s %#06x  %s" % (abid, name, state, want, spell(want)))
        if cur != want:
            todo.append((o, want))

    if not todo:
        print("Nothing to do -- every row is already in the target state.")
        return
    if not args.apply and not args.undo:
        print("DRY RUN -- re-run with --apply to commit.")
        print("(Close AoW.exe / AoWDevEd.exe first -- they lock Release/.)")
        return

    if not args.undo and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(ABIL_PFS, BACKUP)
        print("backup -> %s" % os.path.basename(BACKUP))

    for o, want in todo:
        struct.pack_into("<H", d, o, want)          # length-preserving u16: no offsets move
    struct.pack_into("<I", d, len(d) - 4, zlib.crc32(bytes(d[4:-4])) & 0xFFFFFFFF)
    # not an `assert`: python -O strips those, and a stripped guard here would write a file the
    # game and the editor reject on load.
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        sys.exit("ABORT: CRC repair produced residue %#010x, expected %#010x -- nothing written."
                 % (zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF, PFS_RESIDUE))
    try:
        open(ABIL_PFS, "wb").write(bytes(d))
    except PermissionError:
        sys.exit("ERROR: Release/Ability.pfs is locked. Close the AoW binaries and retry.")

    print("%s %d row(s). CRC repaired." % ("UNDID" if args.undo else "APPLIED", len(todo)))
    if not args.undo:
        print("TEST: in AoWDevEd, edit a use/misc-slot item -- the eight Protection abilities")
        print("      should now be offerable, and a hero carrying that item should gain the")
        print("      protection (the runtime half is already in place via build_useitems.py).")


if __name__ == "__main__":
    main()
