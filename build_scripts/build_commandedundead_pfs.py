#!/usr/bin/env python3
r"""
build_commandedundead_pfs.py -- Ability.pfs records for the two Turn-Undead evil-command
abilities that build_turnundead_evilcommand.py registers at package init:

    key 147  ability 0x89 "Commanded Undead"    the status on a seized undead. Cloned from
                                                key 44 (0x22 "Turned Undead", the vanilla flee
                                                status) so the Ankh overhead effect appears
                                                over the seized unit in combat.
    key 146  ability 0x88 "Can Command Undead"  the caster's controller handle. Description
                                                only, with the vanilla EMPTY image list so it
                                                draws no overhead icon.

    python build_scripts/build_commandedundead_pfs.py            dry run + verify current state
    python build_scripts/build_commandedundead_pfs.py --apply     write both records
    python build_scripts/build_commandedundead_pfs.py --undo      remove them again (surgical)
    python build_scripts/build_commandedundead_pfs.py --dis       decode the records' fields

TARGET: Release/Ability.pfs ONLY. No binary is touched.

------------------------------------------------------------------------------------------
WHY A RECORD IS NEEDED
------------------------------------------------------------------------------------------
build_turnundead_evilcommand.py (CONFIRMED WORKING 2026-09-02) registers 0x88/0x89 in a cave
at package init, before the .pfs pass, so both abilities exist when the loader runs -- but
neither has an Ability.pfs record (key = ability id + 10; keys 146 and 147 were absent, 157
records measured). `AoWE.TAbility.ReadWrite @0x5574F07C` reads exactly five tags:

    tag 5 -> [+0x10] description  (u32-length-prefixed string, NOT the u8 Pascal form of names)
    tag 6 -> [+0x14] hero level-up point cost
    tag 7 -> [+0x18] SFX node
    tag 8 -> [+0x1C] TImageSequenceList: the overhead effect drawn over a unit that owns it
    tag 9 -> [+0x20] selection mask (u16)

No record means an empty image list, so the seized undead shows no icon and the unit panel has
no description. The vanilla flee status 0x22 (key 44) DOES show the Ankh: its tag 8 is one
TCOMBAT\OBJECTS\SEFFECT.ILB sequence, 10 frames ping-pong 0x96..0x9B..0x97. That record is the
exact donor for 0x89 -- the same kind of object (a combat-only status on an undead) with the
same presentation wanted. Tags 7, 8 and 9 are cloned byte-identical; only the text changes.
The donor is resolved by RECORD ID, never by its text: three near-identical descriptions exist
elsewhere in the file and text-matching has misfired before.

------------------------------------------------------------------------------------------
THE TWO THINGS THAT MUST NOT CHANGE
------------------------------------------------------------------------------------------
tag 9 must be 00 00.  The loader writes tag 9 into [ability+0x20] AFTER the cave has set it
to 0, so the data file wins. 0 keeps both abilities unofferable (editor, items, hero level-up),
which is what the cave intends; any other value would put them on the level-up menu. Both
builders assert it on the donor and the clone.

no tag 6.  The donor has none, and 0x89 must stay free -- a level-up cost is meaningless on a
status nobody can pick. The builders never add one.

------------------------------------------------------------------------------------------
KEY 146 (0x88): the EMPTY image list, not a missing tag 8  -- measured, not guessed
------------------------------------------------------------------------------------------
The spec proposed omitting tag 8 for 0x88. Census of the installed file (157 records): EVERY
record carries tag 8, and 105 of them carry tag 8 = `00 00 00 00` -- a TImageSequenceList with
zero sequences, the form every ordinary passive (Archery, Vision, ...) uses to say "no overhead
icon". A record with no tag 8 at all would be a shape this file has never had, read through a
nested-object reader (property-reader slot +0x18, with create/free callbacks) whose absent-tag
behaviour nobody has measured; the empty list goes through a path the loader takes 105 times
per load. So key 146 gets the empty-list tag 8. The result is the same -- nothing is drawn --
by the route that is proven.

------------------------------------------------------------------------------------------
THE CONTAINER -- a splice, not a rebuild
------------------------------------------------------------------------------------------
Index shape (Zig notes/PFS_Format_CRC.md): <u8 n> [<u32 wide>] small(u8 key,u8 off)*
wide(u32,u32)*, then the payload; every offset is relative to the END of the directory.
Inserting a record = one new wide index entry (the payload base moves +8 by itself), offsets
of records AFTER the splice point += len(body), wide count += 1, trailing CRC-32 recomputed.
Nothing else moves; every other record survives byte-identical, and the audit proves that
BEFORE the write. Records are sorted by id AND by offset and both orders must agree, so 146
and 147 are spliced between 142 and 148, not appended at the end. The machinery is
build_embrittle_pfs.py's, reading the index through build_pfs_typos.py; the directory is never
regenerated from scratch (a .pfs record directory cannot be re-derived).

CRC-32: crc32(d[4:]) of an intact .pfs is 0x2144DF1C. Wrong = the game fails silently.
Verified before the edit (the file must be intact to begin with) and after.

Backup: `<game dir>\backups\Ability.pfs.pre-commandedundead`, taken ONLY when the file is proven to be in
the pre-state (CRC intact, neither key present) -- never on --undo, never on a rewrite over a
stale build, both of which would snapshot this script's own output. Per CLAUDE.md the backup
is a courtesy; the revert path is --undo, which removes whichever of the two keys is present
and repairs the CRC, touching no backup.

AoWDevEd rewrites Ability.pfs whole when the set is saved. Nothing here is hard-coded to a file
offset; a save after applying bakes the records in, and --undo then removes the editor's copy,
which is still keyed 146/147 and still ours.

Companion: build_turnundead_evilcommand.py (the mechanics). Design: Zig notes/
TurnUndead_EvilCommand_Design.md.
"""
import os, sys, struct, shutil, zlib, importlib.util

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
HERE = os.path.dirname(os.path.abspath(__file__))
ABILS = os.path.join(GAME, "Release", "Ability.pfs")
PFS_RESIDUE = 0x2144DF1C
SUFFIX = ".pre-commandedundead"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(ABILS) + SUFFIX)

# ================================================================== the knobs
DONOR = 44             # ability 0x22 "Turned Undead" -- resolved by RECORD ID, never by text
REC_M = 147            # ability 0x89 "Commanded Undead"    (record id = ability id + 10)
REC_N = 146            # ability 0x88 "Can Command Undead"  (record id = ability id + 10)

M_DESC = "The undead has been Commanded, and obeys the orders of its master."
N_DESC = "This unit's Turn Undead seizes control of undead instead of harming them."
# ===========================================================================

TAG_DESC, TAG_COST, TAG_SFX, TAG_IMG, TAG_MASK = 5, 6, 7, 8, 9
EMPTY_IMAGES = b"\x00\x00\x00\x00"    # TImageSequenceList, 0 sequences: 105 of 157 records
DONOR_SFX = b"\x01\x01\x00\x00"       # the SFX node 115 of 157 records carry, the donor included
ILB = b"TCOMBAT\\OBJECTS\\SEFFECT.ILB"
ANKH_FRAMES = [0x96, 0x97, 0x98, 0x99, 0x9A, 0x9B, 0x9A, 0x99, 0x98, 0x97]


def _load(name, rel):
    """Import a sibling module relative to THIS SCRIPT, not to GAME -- the toolkit travels with
    the script; AOW_GAME_DIR may point at a throwaway copy that has no Modding Resources."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, *rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


T = _load("_pfs_typos", ("build_pfs_typos.py",))          # index_layout / body_dir / slice_fields
P = _load("_pfs", ("..", "re_tools", "pfs.py"))            # the independent parser, for the proof


def read(path):
    with open(path, "rb") as f:
        return bytearray(f.read())


def u32(b, p):
    return struct.unpack_from("<I", b, p)[0]


# --------------------------------------------------------------------------- container
def index_header(d, S, N):
    """(pos, small_count) of the index header -- the same probe index_layout() uses."""
    for p in range(0, S):
        if d[p] & 0x80 and u32(d, p + 1) == N:
            ns = d[p] & 0x7F
            if p + 5 + 2 * ns == S:
                return p, ns
    raise ValueError("index header not found")


def records(d):
    """-> (payload_base, entries, wide_start, {id: (offset, end_offset)})."""
    base, ent = T.index_layout(d)
    N = sum(1 for e in ent if e[3] == 4)
    wide_start = base - 8 * N
    order = sorted(ent, key=lambda e: e[1])
    span = {}
    for j, e in enumerate(order):
        end = order[j + 1][1] if j + 1 < len(order) else len(d) - 4 - base
        span[e[0]] = (e[1], end)
    return base, ent, wide_start, span


def body_of(d, base, span, rid):
    a, b = span[rid]
    return bytes(d[base + a: base + b])


def fields_of(body):
    ent, dsz = T.body_dir(body)
    return T.slice_fields(body, ent, dsz)


def reserialise(fields):
    """{tag: bytes} -> a record body, offsets recomputed, entry widths chosen per entry.

    Payload in tag order (the donors' own convention). Offsets are relative to the END of the
    directory, so they do not depend on the directory's size, which lets the width be chosen
    after the offsets are known. Every body this script builds is four small entries, the
    donor's own shape.
    """
    tags = sorted(fields)
    offs, run = {}, 0
    for t in tags:
        offs[t] = run
        run += len(fields[t])
    small = [t for t in tags if offs[t] <= 0xFF]
    wide = [t for t in tags if offs[t] > 0xFF]
    hdr = bytearray([(len(small) & 0x7F) | (0x80 if wide else 0)])
    if wide:
        hdr += struct.pack("<I", len(wide))
    for t in small:
        hdr += bytes([t, offs[t]])
    for t in wide:
        hdr += struct.pack("<II", t, offs[t])
    body = bytes(hdr) + b"".join(fields[t] for t in tags)
    assert fields_of(body) == fields, "re-serialised body does not parse back to the same fields"
    assert P.parse_dir(body, top=False) == fields, "re_tools/pfs.py disagrees with the body"
    return body


def pstr32(text):
    """The u32-length-prefixed string form descriptions use (NOT the u8 Pascal form of names).
    Every vanilla description ends CRLF; keeping that keeps the memo control's line handling
    identical to a stock entry."""
    b = (text + "\r\n").encode("latin1")
    return struct.pack("<I", len(b)) + b


# --------------------------------------------------------------------------- the records
def decode_images(v):
    """(sequence_count, ilb_path, frames) of an Ability.pfs tag 8, for --dis and the donor check.
    Only the one-sequence layout the donor uses is decoded; anything else reports None frames."""
    n = u32(v, 0)
    if n == 0:
        return 0, None, []
    plen = u32(v, 5)
    path = bytes(v[9:9 + plen])
    for nf in range(1, 64):                      # the frame block sits at the tail: u32 n, n*u32, 00
        p = len(v) - 1 - 4 * nf - 4
        if p > 9 + plen and u32(v, p) == nf:
            return n, path, [u32(v, p + 4 + 4 * i) for i in range(nf)]
    return n, path, None


def donor_fields(donor):
    """Record 44's fields, with every property the clone relies on asserted -- if AoWDevEd has
    since rewritten the set and 44 is no longer the Ankh flee status, refuse rather than clone
    something else."""
    f = dict(fields_of(donor))
    assert sorted(f) == [TAG_DESC, TAG_SFX, TAG_IMG, TAG_MASK], \
        "donor %d tag set is %s, expected [5, 7, 8, 9] -- no tag 6, or it is the wrong record" % (DONOR, sorted(f))
    assert f[TAG_MASK] == b"\x00\x00", \
        "donor %d tag 9 (selection mask) is %s, expected 00 00" % (DONOR, f[TAG_MASK].hex(" "))
    assert f[TAG_SFX] == DONOR_SFX, \
        "donor %d tag 7 is %s, expected %s" % (DONOR, f[TAG_SFX].hex(" "), DONOR_SFX.hex(" "))
    n, path, frames = decode_images(f[TAG_IMG])
    assert (len(f[TAG_IMG]), n, path, frames) == (100, 1, ILB, ANKH_FRAMES), \
        "donor %d tag 8 is not the 100-byte SEFFECT.ILB Ankh sequence" % DONOR
    return f


def build_commanded(donor):
    """Key 147 (0x89): the donor with only the description replaced."""
    f = donor_fields(donor)
    f[TAG_DESC] = pstr32(M_DESC)
    body = reserialise(f)
    g = fields_of(body)
    assert TAG_COST not in g and all(g[t] == f[t] for t in (TAG_SFX, TAG_IMG, TAG_MASK)), \
        "clone lost a byte-identical tag"
    return body


def build_controller(donor):
    """Key 146 (0x88): description, the donor's SFX node and mask, the vanilla EMPTY image list."""
    f = donor_fields(donor)
    body = reserialise({TAG_DESC: pstr32(N_DESC), TAG_SFX: f[TAG_SFX],
                        TAG_IMG: EMPTY_IMAGES, TAG_MASK: f[TAG_MASK]})
    g = fields_of(body)
    assert TAG_COST not in g and g[TAG_IMG] == EMPTY_IMAGES and g[TAG_MASK] == b"\x00\x00"
    return body


# (record id, label, builder) -- the user's ask first, the bonus second
TARGETS = [
    (REC_M, "key 147 = 0x89 Commanded Undead", build_commanded),
    (REC_N, "key 146 = 0x88 Can Command Undead", build_controller),
]
OURS = {r for r, _l, _b in TARGETS}


# --------------------------------------------------------------------------- splice / remove
def splice_at(span, rec):
    """Where a new record's body goes: in front of the first record with a LARGER id, or at the
    end of the payload if there is none. Records are sorted by id AND by offset, and both orders
    must agree -- index_layout() probes for exactly that invariant."""
    later = [i for i in span if i > rec]
    return min(span[i][0] for i in later) if later else max(e for _a, e in span.values())


def insert(d, rec, body):
    base, ent, wide_start, span = records(d)
    assert rec not in span, "record %d already present" % rec
    at = splice_at(span, rec)
    N = sum(1 for e in ent if e[3] == 4)
    p, _ns = index_header(d, wide_start, N)
    assert all(i < rec for i, _o, _pos, w in ent if w == 1), \
        "a SMALL index entry has an id past ours; its u8 offset could need to move"
    out = bytearray(d)
    for i, o, pos, w in ent:
        if w == 4 and o >= at:
            struct.pack_into("<I", out, pos, o + len(body))
    k = sum(1 for i, _o, _p, w in ent if w == 4 and i < rec)
    out[wide_start + 8 * k: wide_start + 8 * k] = struct.pack("<II", rec, at)
    struct.pack_into("<I", out, p + 1, N + 1)
    out[base + 8 + at: base + 8 + at] = body                 # payload base moved +8
    return out


def remove(d, rec):
    base, ent, wide_start, span = records(d)
    assert rec in span, "record %d is not present" % rec
    at, end = span[rec]
    n = end - at
    N = sum(1 for e in ent if e[3] == 4)
    p, _ns = index_header(d, wide_start, N)
    out = bytearray(d)
    del out[base + at: base + at + n]
    k = sum(1 for i, _o, _p, w in ent if w == 4 and i < rec)
    del out[wide_start + 8 * k: wide_start + 8 * k + 8]
    struct.pack_into("<I", out, p + 1, N - 1)
    for i, o, pos, w in ent:
        if w == 4 and i != rec and o > at:
            struct.pack_into("<I", out, pos - 8, o - n)
    return out


def crc_ok(d):
    return zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF == PFS_RESIDUE


def fix_crc(out):
    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
    assert crc_ok(out), "CRC repair failed"
    return out


# --------------------------------------------------------------------------- proofs
def audit(old, new, expect_present):
    """Every record that is not ours must survive byte-identical (payload bytes, not offsets);
    ours must be all present (apply) or all absent (undo); nothing else may appear or vanish."""
    ob, _oe, _w, osp = records(old)
    nb, _ne, _w2, nsp = records(new)
    for rid in sorted((set(osp) | set(nsp)) - OURS):
        if rid not in nsp:
            return "record %d disappeared" % rid
        if rid not in osp:
            return "record %d appeared from nowhere" % rid
        if body_of(old, ob, osp, rid) != body_of(new, nb, nsp, rid):
            return "record %d changed" % rid
    for rid in sorted(OURS):
        if expect_present and rid not in nsp:
            return "record %d missing after insert" % rid
        if not expect_present and rid in nsp:
            return "record %d still present after removal" % rid
    if not crc_ok(new):
        return "CRC residue wrong"
    return None


def independent_parse(d):
    """re_tools/pfs.py must still read the whole file: every record, every directory."""
    recs = P.parse_index(bytes(d))
    for rid, body in recs:
        P.parse_dir(body, top=False)
    return len(recs), {rid for rid, _b in recs}


def status():
    d = read(ABILS)
    ok = crc_ok(d)
    base, ent, _w, span = records(d)
    assert DONOR in span, "donor record %d is not in the file" % DONOR
    donor = body_of(d, base, span, DONOR)
    per = {}
    for rec, label, builder in TARGETS:
        want = builder(donor)
        present = rec in span
        per[rec] = dict(label=label, want=want, present=present,
                        match=present and body_of(d, base, span, rec) == want)
    return dict(d=d, ok=ok, n=len(ent), per=per,
                pre_state=ok and not any(p["present"] for p in per.values()))


def show():
    print("build_commandedundead_pfs -- Ability.pfs records for 0x89 Commanded Undead / 0x88 Can Command Undead")
    print("target : %s" % ABILS)
    st = status()
    print("         %d records, CRC %s, donor = record %d (0x%02X)"
          % (st["n"], "OK" if st["ok"] else "WRONG -- file damaged", DONOR, DONOR - 10))
    for rec, _l, _b in TARGETS:
        p = st["per"][rec]
        print("  %-34s %s" % (p["label"],
              ("PRESENT, matches this build" if p["match"] else "PRESENT but DIFFERS -- will be rewritten")
              if p["present"] else "absent"))
    print("  backup : %s %s" % (os.path.basename(BACKUP),
                                "exists" if os.path.exists(BACKUP) else "not yet taken"))
    return st


def dis():
    d = read(ABILS)
    base, _e, _w, span = records(d)
    donor = body_of(d, base, span, DONOR)
    for rec, label, builder in TARGETS:
        installed = rec in span
        body = body_of(d, base, span, rec) if installed else builder(donor)
        print()
        print("; ---- %s (%s, %d B) ----" % (label, "installed" if installed else "THIS BUILD", len(body)))
        print("  directory   : %s" % body[:9].hex(" "))
        for t, v in sorted(fields_of(body).items()):
            if t == TAG_DESC:
                print("  tag %d  description : %r  (u32 len %d)" % (t, v[4:].decode("latin1"), u32(v, 0)))
            elif t == TAG_SFX:
                print("  tag %d  sfx node    : %s" % (t, v.hex(" ")))
            elif t == TAG_IMG:
                n, path, frames = decode_images(v)
                if n == 0:
                    print("  tag %d  images      : %s  = EMPTY list, no overhead icon" % (t, v.hex(" ")))
                else:
                    print("  tag %d  images      : %d B, %d sequence(s), %s, %d frames: %s"
                          % (t, len(v), n, path.decode("latin1"), len(frames or []),
                             " ".join("%#x" % f for f in frames) if frames else "?"))
            elif t == TAG_MASK:
                print("  tag %d  mask        : %s  (selection mask -- 0 keeps it unofferable)" % (t, v.hex(" ")))
            else:
                print("  tag %d  field       : %d B %s" % (t, len(v), v[:16].hex(" ")))
        assert TAG_COST not in fields_of(body), "a level-up cost crept in"


def apply(undo=False):
    st = show()
    if not st["ok"]:
        sys.exit("ABORT: CRC residue already wrong -- refusing to write a damaged file")
    per = st["per"]
    if undo and not any(p["present"] for p in per.values()):
        print("\n  neither record present -- nothing to do")
        return
    if not undo and all(p["match"] for p in per.values()):
        print("\n  already applied -- nothing to do")
        return
    d = st["d"]
    before = len(d)
    print()
    if not undo and st["pre_state"] and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(ABILS, BACKUP)
        print("  backup -> %s  (file proven in the pre-state: CRC OK, keys %s absent)"
              % (BACKUP, sorted(OURS)))
    elif not undo and not os.path.exists(BACKUP):
        print("  no backup taken: the file already carries a record of ours, so a snapshot now "
              "would be this script's own output. The revert path is --undo.")
    out = bytearray(d)
    for rec, label, _b in TARGETS:
        p = per[rec]
        if not undo and p["match"]:
            print("  %-34s already present -- kept" % label)
            continue
        if p["present"]:
            out = remove(out, rec)                    # a stale build, or --undo
            print("  %-34s removed" % label)
        if not undo:
            out = insert(out, rec, p["want"])
            print("  %-34s inserted (%d B)" % (label, len(p["want"])))
    fix_crc(out)
    problem = audit(read(ABILS), out, expect_present=not undo)
    if problem:
        sys.exit("ABORT: post-edit audit failed -- %s (nothing written)" % problem)
    n_parsed, ids = independent_parse(out)
    if (ids >= OURS) != (not undo) or n_parsed != len(records(out)[1]):
        sys.exit("ABORT: re_tools/pfs.py reads the result differently (nothing written)")
    try:
        with open(ABILS, "wb") as f:
            f.write(out)
    except PermissionError:
        sys.exit("ABORT: %s is locked -- an AoW binary (AoW.exe / AoWCompat.exe / AoWDevEd.exe / "
                 "AoWEd.exe) is running. Close or kill it and re-run." % ABILS)
    print("  %s: %s  (%d -> %d bytes, %d records, CRC repaired, re_tools/pfs.py parses all %d)"
          % (os.path.basename(ABILS), "records REMOVED" if undo else "records WRITTEN",
             before, len(out), len(records(out)[1]), n_parsed))
    if not undo:
        print()
        print("  NEEDS THE USER'S IN-GAME TEST:")
        print("   1. An evil caster's Turn Undead seizes an undead: the Ankh appears over the")
        print("      seized unit, and its panel lists Commanded Undead with the new description.")
        print("   2. The caster's panel lists Can Command Undead with its description; nothing")
        print("      is drawn over the caster.")
        print("   3. Neither ability is offered at hero level-up, in the editor, or on items.")
        print("   4. Every OTHER ability still shows its own icon and text -- the audit proves")
        print("      the bytes, not that the game agrees.")


if __name__ == "__main__":
    args = set(sys.argv[1:])
    if "--undo" in args:
        apply(undo=True)
    elif "--apply" in args:
        apply()
    else:
        show()
        dis()
        print()
        print("(dry run -- nothing written.  --apply to write, --undo to remove)")
