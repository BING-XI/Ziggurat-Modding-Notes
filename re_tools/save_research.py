#!/usr/bin/env python3
r"""Decode every player's SPELL RESEARCH state out of an AoW1 save.

Why this exists: the tier-research rules are cheap to read in the disassembler and expensive to
reason about, because the answer depends on *which spells are already in the researched list* --
and that list is only observable in a save. Two separate 2026 bug reports about "sphere X tier N
is gated behind an unrelated sphere" were argued from first principles and got nowhere. This
prints the ground truth instead.

⚠ Both of those reports turned out to be the VANILLA one-research-at-a-time UI lock in
`TSpellBook.FillSlot` (`AoW.exe` 0x0042EB97-0x0042EC0D): while `magic+0x34` is non-zero the
Research Book greys every entry and calls `SetVisible(FALSE)` on its button. The entry SET was
always correct -- so before reaching for this tool, ask whether the entry was **absent** (list
path: `ListResearchSpells` -> `ValidResearchSpell` -> `cave_group`) or **present but greyed**
(enable path: `FillSlot`). Full write-up in `Zig notes/Spell_Research_System_2026-07-18.md`.
This tool is still the right instrument for the absent case, and for confirming that a group
grant actually fired (a COMPLETE group) versus a Tome (a PARTIAL one).

Usage:  python save_research.py [<save.asg>]            (default: <game>/Save/autosave.asg)
        python save_research.py --predict               (also print what ValidResearchSpell
                                                         SHOULD offer each player, per-sphere)

FORMAT
------
`.asg` / `.acg` = 5-byte header `CFS\0\x02` then a raw **zlib** stream.

Inside, every serialised object is a property table (id-indexed, NOT positional -- which is why
growing a class stays save-compatible). Layout, decoded 2026-09-03 against
`AoWE.TPlayerMagicControl.ReadWrite @0x5577C748`:

    [ ...header... ][ id, payload_off ] * N  [ payload bytes ]

with ids ASCENDING and `payload_off` a byte offset into the payload that follows the directory.
Properties left at their default are simply absent -- so the directory's id set varies per object
and you must key on ids, never on position.

TPlayerMagicControl property ids (from the ReadWrite body, in emission order):

    id    field    meaning
    0x14  +0x24    mana pool                       (dword)
    0x15  +0x2c    research % of power income      (ranged byte; absent when default)
    0x16  +0x30    RESEARCHED SPELL IDS            (TIntegerList: dword capacity, dword count,
                                                    then `count` dwords)
    0x17  +0x34    current research spell id       (dword, 0 = none)
    0x18  +0x38    research points remaining       (dword)
    0x19  +0x3c    enchantment list
    0x1a  +0x44 / 0x1b +0x18 / 0x1c +0x1c / 0x1e   (not decoded here)

⚠ A researched "spell id" is the spell's **registry index** (`TSpellControl.GetSpell` is a plain
`TList.Get`), and `Release/Spells.pfs` numbers the same spells **+10**: record = index + 10.
Verified 2026-09-03 -- the day-1 grant in a live save decoded to registry ids {20,77,103,130},
which map to pfs records {30,87,113,140} = exactly the four Death tier-1 spells, a complete group.
⭐ **+10 is the UNIQUE offset**: sweeping k over -20..+40, k=+10 is the only value for which those
four indices all resolve to existing records that share ONE (sphere, tier) at all -- let alone a
complete group. So this mapping is measured, not assumed; re-run that sweep if the spell table
ever changes rather than trusting the constant.

WHAT TO LOOK FOR
----------------
* A tier group that is **complete** (n/n) = `cave_day1` or `cave_grant` fired correctly.
* A tier group that is **partial** (1/4) = a Tome (`TItem.ExecuteUse` -> ExecuteSpellResearched
  grants ONE spell and is the only non-cave caller), or a group grant that failed.
* `--predict` applies the vanilla per-sphere ladder from `ValidResearchSpell @0x5577CFF0`:
  a spell is offerable iff tier <= maxUnlocked(its sphere), where maxUnlocked starts at 1 and
  increments while `count[tier] >= 2` counting ONLY researched spells of that same sphere.
  It cannot see the leader's sphere picks (rule 1, `tier <= GetSpherePicks(sphere)`), so it is an
  UPPER BOUND on what the Research Book should show.
Read-only: never writes to the save.
"""
import os, sys, struct, zlib, importlib.util

TOOLS = os.path.dirname(os.path.abspath(__file__))
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(TOOLS, "..", ".."))

SPHERE = {0: "Cosmos", 1: "Life", 2: "Death", 3: "Earth", 4: "Air", 5: "Fire", 6: "Water"}
PFS_ID_OFFSET = 10          # pfs record id = registry index + 10


def spell_table():
    """{registry index: (sphere, tier)} plus {index: description} from Release/Spells.pfs."""
    spec = importlib.util.spec_from_file_location("pfs", os.path.join(TOOLS, "pfs.py"))
    pfs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pfs)
    info, desc = {}, {}
    for rid, f, _ in pfs._iter("spells.pfs"):
        i = rid - PFS_ID_OFFSET
        info[i] = (f[0x10][0] if 0x10 in f else -1, f[0x11][0] if 0x11 in f else -1)
        desc[i] = f.get(0x0A, b"")[4:].decode("cp1252", "replace").strip()
    return info, desc


def load(path):
    d = open(path, "rb").read()
    if d[:3] != b"CFS":
        raise SystemExit(f"{path}: not an AoW save (expected 'CFS' magic)")
    return zlib.decompress(d[5:])


def magic_controls(u, info):
    """Yield (file_offset, {id: payload_off}, payload_base) for every TPlayerMagicControl."""
    for start in range(len(u) - 4):
        if u[start] != 0x14:
            continue
        ids, p, last = {}, start, -1
        while p + 2 <= len(u) and 0x14 <= u[p] <= 0x30 and u[p] > last:
            ids[u[p]] = u[p + 1]
            last = u[p]
            p += 2
        if 0x16 not in ids or len(ids) < 3:
            continue
        try:
            cnt = struct.unpack_from("<I", u, p + ids[0x16] + 4)[0]
            if not 0 <= cnt <= 250:
                continue
            lst = list(struct.unpack_from("<%dI" % cnt, u, p + ids[0x16] + 8))
        except Exception:                                        # noqa: BLE001
            continue
        if any(i not in info for i in lst):
            continue
        yield start, ids, p, lst


def max_unlocked(researched, info, sphere):
    """The vanilla per-sphere ladder from ValidResearchSpell @0x5577CFF0."""
    count = [0] * 6
    for i in researched:
        s, t = info[i]
        if s == sphere and 1 <= t <= 4:
            count[t] += 1
    m = 1
    while m < 4 and count[m] >= 2:
        m += 1
    return m


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else os.path.join(GAME, "Save", "autosave.asg")
    info, desc = spell_table()
    u = load(path)
    print(f"{path}  ({len(u)} bytes decompressed)\n")
    sizes = {}
    for k, v in info.items():
        sizes[v] = sizes.get(v, 0) + 1
    n = 0
    for start, ids, payload, lst in magic_controls(u, info):
        cur_raw = struct.unpack_from("<I", u, payload + ids[0x17])[0] if 0x17 in ids else 0
        if not lst and (cur_raw == 0 or cur_raw not in info):
            continue        # empty stub, or a directory that only looked like one (0x14/0x16
                            # ascending pairs occur by chance in unit/army blocks)
        n += 1
        mana = struct.unpack_from("<I", u, payload + ids[0x14])[0] if 0x14 in ids else None
        cur = struct.unpack_from("<I", u, payload + ids[0x17])[0] if 0x17 in ids else 0
        pts = struct.unpack_from("<i", u, payload + ids[0x18])[0] if 0x18 in ids else None
        cs, ct = info.get(cur, (-1, -1))
        print(f"=== magic control @ {start:06X}   mana={mana}   researched={len(lst)}")
        if cur:
            print(f"    researching: id {cur} = {SPHERE.get(cs,'?')} tier {ct}"
                  f"   points left {pts}   ({desc.get(cur,'')[:60]})")
        groups = {}
        for i in lst:
            groups.setdefault(info[i], []).append(i)
        for k in sorted(groups):
            tot = sizes.get(k, 0)
            have = len(groups[k])
            tag = "COMPLETE" if have == tot else f"PARTIAL -- tome, or a grant that did not fire"
            print(f"      {SPHERE.get(k[0],'?'):7s} T{k[1]}: {have}/{tot}  {sorted(groups[k])}"
                  f"   [{tag}]")
        if "--predict" in sys.argv:
            print("    per-sphere ladder says the Research Book should offer"
                  " (ignoring sphere picks):")
            offer = []
            for s in range(7):
                m = max_unlocked(lst, info, s)
                for t in range(1, m + 1):
                    members = [i for i, v in info.items() if v == (s, t)]
                    if members and not all(i in lst for i in members):
                        offer.append(f"{SPHERE[s]} {'I II III IV'.split()[t-1]}")
            print("      " + (", ".join(offer) if offer else "(nothing)")
                  + f"   -> {len(offer)} entries")
        print()
    if not n:
        print("no TPlayerMagicControl blocks found -- is this an AoW1 .asg/.acg?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
