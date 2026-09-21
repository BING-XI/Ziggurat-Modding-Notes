#!/usr/bin/env python3
r"""Parser for AoW1's `.pfs` resource files -- the unit / item / spell / hero / ability data.

The DPLs contain the *code*; the game's actual content tables live in `<game>/Release/*.pfs`:
  Unitres.pfs  units      ITEMS.PFS  items       Spells.pfs  spells
  HEROES.PFS   heroes     HERORES.PFS hero res   Ability.pfs ability metadata
NOTE the installed data may be a total-conversion mod (this install is Ziggurat, not vanilla) -- the
binaries are stock AoW1 but every .pfs is modded, so counts derived here describe the INSTALLED game.

## Format (decoded from AoWEPACK.dpl; see the ReadWrite methods listed per section)

Both the file index and every record body use the same **directory** shape:

    <u8 n>                       n & 0x7f = count of SMALL entries
    [<u32 wide_count>]           present only if n & 0x80
    small entries: (u8 key, u8 offset) * (n & 0x7f)
    wide  entries: (u32 key, u32 offset) * wide_count
    <payload>                    offsets are relative to the END of the directory

For the file index the key is a record id; for a record body the key is a field tag. A single body
MIXES the two entry forms freely -- Ability.pfs record 158 is 4 small + 1 wide, because its last
field sits past the u8 offset ceiling.

⚠ The 4-byte class/version word before a body's directory (`top=True`) is PER FILE, and cannot be
detected by trial -- `top=False` on a Unitres record SUCCEEDS, returning 16 plausible tags instead
of the right 24.
    present : Unitres.pfs, ITEMS.PFS, HEROES.PFS, HERORES.PFS  -> top=True
    absent  : Ability.pfs, Spells.pfs                          -> top=False

Field encodings: integers are little-endian. ⚠ Strings come in TWO forms and `pstr()` below only
knows the second:
    u32-prefixed  <u32 len><bytes>   descriptions (Ability.pfs tag 5) -- pstr() MISREADS these
    Pascal        <u8 len><bytes>    names (tag 10/11), filenames
Sniff by whether `4 + n` or `1 + n` equals the field length. `build_scripts/build_pfs_typos.py`
does that, and is the writer to use for any text edit (it handles the length change, the index
offsets and the CRC).

### Ability bitsets  (`TCustomAbilityList.ReadWrite @0x5574E2BC`, `SetAbSet @0x5574E0BC`)
    tag 2 = bit count (u32)
    tag 3 = (count+7)//8 bytes, **LSB-first, and the bit index IS the ability id** (no offset).
The setter auto-grows the set, which is why any ability id works -- see the Path-of-Sand notes.

### Units  (`TUnitResource.ReadWrite @0x55784DE4`, `TAbilityOwner.ReadWrite @0x5574F318`)
A unit carries THREE ability owners, and the medal ones are **deltas, not full sets**:
    tag 0x19 = base chassis      tag 0x1E = silver medal      tag 0x1F = gold medal

Tag -> in-memory TUnitResource offset (decoded from ReadWrite, 2026-07-30). Useful because engine
code addresses these by OFFSET while the file addresses them by TAG:
    0x0A->+0x1C race   0x0B->+0x24 name   0x0C->+0x28   0x0D->+0x20
    0x0E->+0x29 ATK    0x0F->+0x2A DEF    0x10->+0x2B DMG   0x11->+0x2C HP
    0x12->+0x2D Move   0x13->+0x2E RES    0x14->+0x2F level
    0x15->+0x30 UNIT TYPE    0x16->+0x21   0x17->+0x31   0x18->+0x44
    0x1A->+0x48 description  0x1B->+0x4C gold  0x1C->+0x50  0x1D->+0x51

**tag 0x15 = unit type** (1 byte), read by `TUnit.GetUnitType` @0x55782808 (VMT +0x114):
    0 = humanoid / racial      1 = monster / creature      2 = MACHINE
Only 0-2 occur in the installed data (96 / 61 / 23 of 180 units); the roster-generator filter
argument is a bitset over these values and supports 0-7. Machines (2) are gated out of several
mechanics: vertigo, stun, and lifesteal healing all test `GetUnitType() != 2`.

### Abilities  (`Ability.pfs`)
    record id = ability id + 10        tag 5 = description      tag 6 = hero level-up point cost

### Ability-data sub-records on ANY owner (item, unit, hero) -- derived 2026-08-28
A tag-3 bitset names the abilities an owner grants but carries no level. Levels live in nested
sub-records, and `TAbilityOwner.ReadWrite @0x5574F318` says exactly how:

    0x5574F37A   tag 0x31 = an integer LIST of the ability ids that own a data record
    0x5574F3A1   for each: TIntegerList.Get(i) ... add eax, 0x32   -> the sub-record's tag

So **sub-record tag = ability id + 0x32**, and `TAbilityOwner.GetAbilityData @0x5574F1C4` walks
the `[owner+0x10]` list these build. Verified across 426 owners / 649 sub-records in Unitres,
HEROES, HERORES and ITEMS: the tag<->id arithmetic never fails.

⚠ **The loader drives off tag 0x31, not off scanning the 0x32..0xD2 range.** A sub-record whose
id is absent from tag 0x31 is never read.

⚠ **The level is NOT at a fixed tag inside the sub-record -- it is per data class:**

    TMultiLevelAbilityData  ClassID 0x00022001  tag 0x0A = LEVEL      tag 0x0B = ability id
    TLeadershipAbilityData  ClassID 0x000202CE  (same shape)
    TDispelMagicAbilityData ClassID 0x000202CD  tag 0x0A = ENABLED    tag 0x0B = LEVEL
    THealingAbilityData     ClassID 0x000202AE  tag 0x0A = ENABLED    (no level at all)

Reading "the level" as tag 0x0A gives Dispel Magic's *enabled flag* instead. Worked example:
Ankh of Turning = `01 20 02 00 | 02 | 0a 00 0b 01 | 02 26 00` -> ClassID 0x22001, level 2, id 0x26.

⚠ In ITEMS.PFS only **two** records carry any sub-record (Ankh of Turning tag 0x58, Helm of Eyes
tag 0x72); Crown of Kings sets the Leadership bit with no record, so it resolves level 0.

⚠ **The bitset and the level record are independent, and an item can have the bit without the
record.** That is not an editor limitation -- 2 of the 3 vanilla items granting a multi-level
ability do have one (Ankh of Turning 0x58, Helm of Eyes 0x72); Crown of Kings does not. The
consequence is a real in-game effect, because `TMultiLevelAbility.GetLevel @0x557651D8`,
`TTurnUndeadAbility.GetLevel @0x5576AE8C` and `TLeadershipAbility.GetLevel @0x557661C4` all end
`GetAbilityData(owner) ? [rec+0xC] : 0` -- no record means level **0**, i.e. the ability is
listed and does nothing. `TDispelMagicAbility.GetLevel @0x5576CEFC` is the one class where
vanilla returns 1 instead. So a bits-only item is authored, not broken code: add the sub-record
in AoWDevEd rather than patching the engine.

Validation anchors (all confirmed): Ring of Invisibility -> ability 54 (0x36), Ring of True Sight -> 41
(0x29), Crown of Kings -> 46 (Leadership), Ring of Regeneration -> 49.

## CLI
    python pfs.py tags   <file.pfs> <record-id>     show a record's raw tags (format archaeology)
    python pfs.py names  <file.pfs>                 list record ids + names
    python pfs.py has    <file.pfs> <ability-id>    list records whose ability set contains the id
    python pfs.py counts <ability-id> [<ability-id> ...]   the cross-file summary
"""
import struct, os, sys

# tools dir + game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
TOOLS = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(TOOLS, "..", ".."))
RELEASE = os.path.join(GAME, "Release")

# Tag holding the display name, per file (probed; use `tags` mode to re-derive). Units and heroes
# split it: tag 10 = race ("Human") or the whole name for raceless units ("Shadow", "Air Elemental"),
# tag 11 = the unit's name within its race ("Crossbowman") -> display as "<10> <11>".
# Spells.pfs and Ability.pfs carry NO name field: those names are Delphi resourcestrings in
# AoWEPACK.dpl (e.g. AoWE.InvisibilityRStr, AoWE.TrueVisionRStr), reached via RegisterPassiveAbilities
# @0x557BC1CC -> CreateEnhancementAbility @0x5576601C (eax = id, edx = name global).
NAME_TAG = {"unitres.pfs": (10, 11), "herores.pfs": (10, 11), "heroes.pfs": (10, 11),
            "items.pfs": (8,), "zig.ail": (8,)}
# ⚠ `Release/ITEMS.PFS` IS NOT THE ITEM LIST THE MOD SHIPS. Ziggurat's items live in an item
# LIBRARY, `<game>/User/Zig.ail` -- same container format, same record shape, `top=True`, name in
# tag 8 -- and it holds 325 records against ITEMS.PFS's 83. Any census of "what items exist / what
# do they grant" must read BOTH, and `load()` below searches `User/` as well for exactly that
# reason. Getting this wrong on 2026-08-28 produced the false conclusion "no item grants Spell
# Casting 0x34" (ITEMS.PFS: 0 -- Zig.ail: 31, at authored levels 1..5).
USER = os.path.join(GAME, "User")
# ability-set owners: (tag, label). Medal owners are deltas layered on the chassis.
# Ability-set owners on a unit record, in rank order.  0x20 (copper) is NOT vanilla -- it is added
# by build_scripts/build_copper_medal.py with COPPER_GRANTS_ABILITIES on, which gives TUnitResource
# a 4th ability owner at +0x44; unpatched installs simply never carry the tag.
UNIT_OWNERS = [(0x19, "base"), (0x20, "copper"), (0x1E, "silver"), (0x1F, "gold")]

# An item's per-ability level sub-record tag. See the ITEMS.PFS section of the docstring.
ITEM_ABILITY_RECORD_BASE = 0x32


def item_ability_record_tag(ability_id):
    """Tag under which an ITEMS.PFS record keeps the level for `ability_id`."""
    return ability_id + ITEM_ABILITY_RECORD_BASE


def item_ability_levels(fields):
    """{ability_id: has_level_record} for one owner record's parsed fields.

    False means the bit is set but no data sub-record exists, so `GetAbilityData` misses and the
    ability resolves to level 0 -- listed on the card, doing nothing. (Dispel Magic is the one
    family whose GetLevel returns 1 instead, and only when the bit is set.)

    ⚠ Checks BOTH the sub-record tag and membership of tag 0x31, because the loader drives off
    the tag-0x31 id list: a sub-record the list does not name is never read.
    """
    listed = set()
    if 0x31 in fields:
        raw = fields[0x31]
        # A Delphi TIntegerList: <u32 prefix><u32 count><u32 ids...>.
        # ⚠ FIXED 2026-08-28 -- this used to read the count at offset 0, i.e. the PREFIX, which is
        # always 0. `listed` therefore came back empty, `not listed` was always true, and the
        # membership guard below silently never ran. It failed OPEN, so nothing published off it
        # was wrong, but it was a dead check advertised as a live one. Sample (Zig.ail rec 6,
        # Archmage Scroll): 00000000 00000001 00000034 -> prefix 0, count 1, id 0x34.
        if len(raw) >= 8:
            n = struct.unpack_from("<I", raw, 4)[0]
            if 8 + 4 * n <= len(raw):
                listed = {struct.unpack_from("<I", raw, 8 + 4 * i)[0] for i in range(n)}
    return {a: (item_ability_record_tag(a) in fields and (not listed or a in listed))
            for a in abilities_of(fields)}


def parse_index(d):
    """Split a .pfs into [(record_id, body_bytes)]. The index is the same directory shape as a
    record body, but its small-entry count is discovered by probing: we find the longest strictly
    increasing run of (u32 id, u32 off) pairs, then locate the `n` byte that describes it."""
    best = None
    for s in range(0, 0x40):
        ids = []; offs = []; p = s
        while p + 8 <= len(d):
            i, o = struct.unpack_from("<II", d, p)
            if ids and (i <= ids[-1] or o <= offs[-1]): break
            if i > 0x10000 or o > len(d): break
            ids.append(i); offs.append(o); p += 8
        if len(ids) > 5 and (best is None or len(ids) > len(best[1])): best = (s, ids, offs)
    if best is None: raise ValueError("no wide index found")
    S, wids, woffs = best; N = len(wids)
    small = []
    for p in range(0, S):
        if not (d[p] & 0x80): continue
        if p + 5 > len(d): continue
        if struct.unpack_from("<I", d, p + 1)[0] != N: continue
        ns = d[p] & 0x7f
        if p + 5 + 2 * ns == S:
            small = [(d[p + 5 + 2 * k], d[p + 6 + 2 * k]) for k in range(ns)]
            break
    ids = [i for i, _ in small] + wids
    offs = [o for _, o in small] + woffs
    base = S + 8 * N
    recs = []
    for k in range(len(ids)):
        a = base + offs[k]
        b = base + offs[k + 1] if k + 1 < len(offs) else len(d)
        recs.append((ids[k], d[a:b]))
    return recs


def parse_dir(r, top=True):
    """Parse a directory into {tag: bytes}. top=True skips the 4-byte class/version prefix."""
    p = 4 if top else 0
    n = r[p]; p += 1
    small = n & 0x7f; wide = 0
    if n & 0x80:
        wide = struct.unpack_from("<I", r, p)[0]; p += 4
    ent = []
    for _ in range(small): ent.append((r[p], r[p + 1])); p += 2
    for _ in range(wide):
        t, o = struct.unpack_from("<II", r, p); ent.append((t, o)); p += 8
    ds = p
    order = sorted(range(len(ent)), key=lambda k: ent[k][1])
    f = {}
    for j, k in enumerate(order):
        t, o = ent[k]
        a = ds + o
        b = ds + ent[order[j + 1]][1] if j + 1 < len(order) else len(r)
        if not (0 <= a <= b <= len(r)): raise ValueError("bad offset for tag %d" % t)
        f[t] = r[a:b]
    return f


def bits(bs):
    """Ability-set bytes -> [ability ids]. LSB-first; bit index == ability id."""
    return [i * 8 + b for i, byte in enumerate(bs) for b in range(8) if byte & (1 << b)]

def pstr(b):
    return b[1:1 + b[0]].decode("latin-1") if b else ""

def u32(b, d=0):
    return struct.unpack_from("<I", b, 0)[0] if b and len(b) >= 4 else d


def load(name):
    """Open a .pfs/.ail by bare filename (case-insensitively) from <game>/Release or <game>/User."""
    for d in (RELEASE, USER):
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.lower() == name.lower():
                return parse_index(open(os.path.join(d, f), "rb").read()), f.lower()
    raise FileNotFoundError(f"{name} not in {RELEASE} or {USER}")


def abilities_of(fields):
    """Ability ids from a record's own directory (tag 3 = bitset), or [] if it has none."""
    return bits(fields[3]) if 3 in fields else []


def record_abilities(fields, fname):
    """All ability ids a record grants. Units union their three owners; everything else is flat."""
    if fname == "unitres.pfs":
        out = set()
        for tag, _label in UNIT_OWNERS:
            if tag in fields:
                try: out |= set(abilities_of(parse_dir(fields[tag], top=False)))
                except (ValueError, IndexError): pass
        return out
    return set(abilities_of(fields))


def name_of(fields, fname):
    parts = [pstr(fields.get(t, b"")) for t in NAME_TAG.get(fname, (10,))]
    return " ".join(p for p in parts if p) or "?"


# Most files store each record as [classid:u32][table][data]; in these two the root table IS
# the record list and a record starts with its table directly. Parsing them with the classid
# skip eats the count byte and every record silently comes back with ZERO tags — which is what
# it did until 2026-08-07, so anything that read spells or abilities through _iter saw nothing.
NO_CLASSID = {"spells.pfs", "ability.pfs"}


def _iter(fname):
    recs, key = load(fname)
    top = key not in NO_CLASSID
    for rid, body in recs:
        try: yield rid, parse_dir(body, top=top), key
        except (ValueError, IndexError): continue


def main(argv):
    if len(argv) < 2: print(__doc__); return 1
    mode = argv[1]

    if mode == "tags":
        recs, key = load(argv[2]); want = int(argv[3], 0)
        # ⚠ top= is PER FILE (see NO_CLASSID and the docstring). This mode used to hard-code the
        # default top=True, which silently misparses Ability.pfs and Spells.pfs -- record 57 came
        # back as "0 tags" and record 70 raised "bad offset", and a conclusion was published off
        # that before anyone noticed. Never call parse_dir here without consulting NO_CLASSID.
        top = key not in NO_CLASSID
        for rid, body in recs:
            if rid != want: continue
            f = parse_dir(body, top=top)
            print(f"record {rid} of {key}: {len(f)} tags")
            for t in sorted(f):
                v = f[t]
                print(f"  tag {t:#04x} ({len(v):3d} B) {v[:32].hex(' ')}"
                      f"{'  str=' + repr(pstr(v)) if v and v[0] and v[0] < len(v) else ''}")
        return 0

    if mode == "names":
        for rid, f, key in _iter(argv[2]):
            print(f"{rid:4d}  {name_of(f, key)}")
        return 0

    if mode == "has":
        want = int(argv[3], 0); n = 0
        for rid, f, key in _iter(argv[2]):
            if want in record_abilities(f, key):
                where = ""
                if key == "unitres.pfs":
                    where = " [" + ",".join(
                        lbl for tag, lbl in UNIT_OWNERS if tag in f
                        and want in set(abilities_of(parse_dir(f[tag], top=False)))) + "]"
                print(f"{rid:4d}  {name_of(f, key)}{where}"); n += 1
        print(f"-- {n} record(s) in {argv[2]} with ability {want} ({want:#04x})")
        return 0

    if mode == "counts":
        wanted = [int(a, 0) for a in argv[2:]] or [0x36, 0x29]
        files = ["Unitres.pfs", "ITEMS.PFS", "Spells.pfs", "HEROES.PFS"]
        print(f"{'ability':>18} " + " ".join(f"{f.split('.')[0]:>10}" for f in files))
        for w in wanted:
            row = []
            for fn in files:
                try: row.append(sum(1 for _r, f, key in _iter(fn) if w in record_abilities(f, key)))
                except FileNotFoundError: row.append("-")
            print(f"{w:#06x} ({w:>3d})".rjust(18) + " " + " ".join(f"{c:>10}" for c in row))
        return 0

    print(__doc__); return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
