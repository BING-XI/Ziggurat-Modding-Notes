#!/usr/bin/env python3
r"""
build_shredderbolt_banejavelin.py -- the Orc Shredder Bolt (Release/Unitres.pfs record 256) carries
Shoot Bane Javelin (0xBE) in place of Shoot Bolt (0x39).  Owner's ruling 2026-10-19 ("Shredder Bolt
for now"); vanilla gave this unit Shoot Black Javelin, the physical + death javelin, and nothing else.

WHAT CHANGES
    The base ability owner (record tag 0x19) only: bit 0x39 cleared, bit 0xBE set.  The set grows to
    0xBF bits: tag 2 (the size in bits, u32) 77 -> 191, tag 3 (the bitset, LSB-first, bit = id)
    10 -> 24 bytes.  Shoot Bolt has no per-ability record here (the owner's tag 0x31 list names only
    Marksmanship 0x20) and Shoot Bane Javelin needs none.  The copper/silver/gold owners
    (Marksmanship each) are untouched.

HOW
    build_unitres_reclist.py's full-fidelity directory codec (entry order, small/wide form and payload
    layout preserved), applied to the owner and then to the record; the record is re-spliced, the
    file index shifted and the CRC-32 repaired.  Every other record is proved byte-identical, the
    whole file is re-parsed by re_tools/pfs.py, and the CRC residue is checked.

UNDO
    Byte-exact while the record is still this script's output: the original record is embedded
    below.  If something has re-saved the record since (the editor, the Manual's unit editor),
    --undo clears 0xBE and sets 0x39 in place instead -- the same abilities, not the same bytes.

Units already on a map keep the abilities they were created with: a Unitres edit reaches new games,
newly built units and units that rank up (memory aow1-pfs-data-decoder).

    python build_scripts/build_shredderbolt_banejavelin.py            dry run + state
    python build_scripts/build_shredderbolt_banejavelin.py --apply
    python build_scripts/build_shredderbolt_banejavelin.py --undo
"""
import base64, hashlib, importlib.util, os, struct, sys, zlib

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = _load("_reclist", os.path.join(HERE, "build_unitres_reclist.py"))
pfs = _load("_pfs", os.path.join(HERE, "..", "re_tools", "pfs.py"))
from aowepack_patch import kill_aow                                    # noqa: E402

UNITRES = R.PFS
UNIT, UNIT_NAME = 256, "Shredder Bolt"
OWNER = 0x19                                    # base
OLD, NEW = 0x39, 0xBE                           # Shoot Bolt -> Shoot Bane Javelin
TAG_SIZE, TAG_BITS = 2, 3

ORIG_SHA = "7f54c4252321ec71"                   # sha1[:16] of the record as it was 2026-10-19
ORIG = zlib.decompress(base64.b64decode(
    "eNqNUs1u00AQ3jghCiEpobRFFGin/IOqSDwCkZC4cGm5cJysx/Gi9U7YXSfkNeANOADPwIV34HmQYNaGqkgcasn6xt5vvplvZrezTH3sK6U6"
    "Kut1B4PRcDI6GB9uwdWjyd1r97bvX3+w83D30d7jG09uPt1/c0uYnzKlbgt+Frwj+EXwQPCr4KHgD0EQ/Cn47bsbdFUj37zj09JTnpOHGdvY"
    "/5X1sp29vvQgger2nm2d7L9KzF7Dzl5O/uYmwQ4Ib6iudDJQL0T8uY0l14sSKtIlOqPR2g3kpijIk4tQeK5Aew5hzutwDHM5NyFigKJ2Ohp2"
    "8K42kSCYylj0djOF2RkHfTqgBUGFujSOAsQSY/O/4hCBpI6orCgVpaXlDeUgBMtuAR7dQjJwgcYJl2MpnmtnYpCj5kPEHGgTN7CWmmEKr0sy"
    "Ht6iCEpOW6fW4o4lQq1rSZTASRHynG8cVka3MiIIc65tGiwXgKAx4rK2cQqntCKP9px5LQlLzyuTE9B7TdamYWkWHhTsz3JDU8tjJUGMVC2j"
    "EWORYe5JJpKqSPcfAnAdJTW5mI6H4+GMNNaBUiOxsVQSrsQlc07imGUevm7Gf5wIm3bSltdJu5I22sUtLWpKv5qgGU84t4uUhDZwO57C48JY"
    "+jPUfwwku3NqaYTBNNuSFtK6pN+RXKxMtbfv8snukWqfzn8vXg8uyrx0YWYX1G/nxu0L"))
assert hashlib.sha1(ORIG).hexdigest()[:16] == ORIG_SHA


def _bits_get(bs, i):
    return i < 8 * len(bs) and bool(bs[i >> 3] & (1 << (i & 7)))


def owner_ids(body):
    top = R.dir_parse(body, top=True)
    ow = R.dir_parse(top["data"][OWNER], top=False)
    return set(pfs.bits(ow["data"].get(TAG_BITS, b"")))


def retag(body, clear, setid):
    """The record with `clear` cleared and `setid` set in the base owner; size grown to fit."""
    top = R.dir_parse(body, top=True)
    ow = R.dir_parse(top["data"][OWNER], top=False)
    size = struct.unpack("<I", ow["data"][TAG_SIZE])[0]
    bits = bytearray(ow["data"][TAG_BITS])
    if len(bits) != (size + 7) // 8:
        sys.exit("ABORT: base owner size %d does not match its %d-byte set" % (size, len(bits)))
    size = max(size, setid + 1)
    bits += b"\0" * ((size + 7) // 8 - len(bits))
    bits[clear >> 3] &= ~(1 << (clear & 7)) & 0xFF
    bits[setid >> 3] |= 1 << (setid & 7)
    old_owner = dict(ow["data"])
    ow["data"][TAG_SIZE] = struct.pack("<I", size)
    ow["data"][TAG_BITS] = bytes(bits)
    nowner = R.dir_emit(ow)
    chk = R.dir_parse(nowner, top=False)["data"]
    for t, v in old_owner.items():
        if t not in (TAG_SIZE, TAG_BITS):
            assert chk[t] == v, "owner tag %#x did not survive" % t
    old_rec = dict(top["data"])
    top["data"][OWNER] = nowner
    nbody = R.dir_emit(top)
    chk = R.dir_parse(nbody, top=True)["data"]
    for t, v in old_rec.items():
        if t != OWNER:
            assert chk[t] == v, "record tag %#x did not survive" % t
    return nbody


def splice(d, rid, nbody):
    """The file with record `rid` replaced, index shifted, CRC repaired."""
    base, ent = R.index_layout(d)
    recs = pfs.parse_index(bytes(d))
    assert [a for a, _o, _p, _w in ent] == [r for r, _ in recs], "index ids disagree with parse_index"
    out, offs, pos, last = bytearray(d[:base]), {}, 0, recs[-1][0]
    for r, body in recs:
        if r == last:                           # the final body swallows the trailing CRC dword
            body = body[:-4]
        if r == rid:
            body = nbody
        offs[r] = pos
        out += body
        pos += len(body)
    out += d[-4:]
    for r, _o, fieldpos, w in ent:
        if w == 1:
            assert offs[r] <= 0xFF, "a small index offset overflows u8"
            out[fieldpos] = offs[r]
        else:
            struct.pack_into("<I", out, fieldpos, offs[r])
    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
    return bytes(out)


def audit(old, new, rid):
    if zlib.crc32(new[4:]) & 0xFFFFFFFF != R.PFS_RESIDUE:
        return "CRC residue wrong"
    o, n = pfs.parse_index(old), pfs.parse_index(new)
    if [r for r, _ in o] != [r for r, _ in n]:
        return "record id list changed"
    last = n[-1][0]
    ob, nb = dict(o), dict(n)
    for r in ob:
        a, b = (ob[r][:-4], nb[r][:-4]) if r == last else (ob[r], nb[r])
        if r != rid and a != b:
            return "record %d changed" % r
    for r, body in n:                           # every record and owner still parses
        f = pfs.parse_dir(body, top=True)
        for tag, _l in pfs.UNIT_OWNERS:
            if tag in f:
                pfs.parse_dir(f[tag], top=False)
    return None


def main():
    apply_, undo = "--apply" in sys.argv, "--undo" in sys.argv
    d = open(UNITRES, "rb").read()
    if zlib.crc32(d[4:]) & 0xFFFFFFFF != R.PFS_RESIDUE:
        sys.exit("ABORT: Unitres.pfs CRC residue is wrong -- the file is already damaged")
    body = dict(pfs.parse_index(d))[UNIT]
    name = pfs.name_of(pfs.parse_dir(body, top=True), "unitres.pfs")
    if name != UNIT_NAME:
        sys.exit("ABORT: record %d is %r, not %r" % (UNIT, name, UNIT_NAME))
    ids = owner_ids(body)
    ours = retag(ORIG, OLD, NEW)
    state = ("vanilla-for-us (Shoot Bolt)" if body == ORIG else
             "installed" if body == ours else
             "installed, re-saved since" if NEW in ids and OLD not in ids else
             "Shoot Bolt, re-saved since" if OLD in ids and NEW not in ids else "OTHER")
    print("build_shredderbolt_banejavelin -- %s\n  record %d %s, base abilities %s\n  state: %s"
          % (UNITRES, UNIT, name, " ".join("%#04x" % i for i in sorted(ids)), state))
    if not (apply_ or undo):
        print("\n(dry run -- nothing written)")
        return
    if apply_:
        if state.startswith("installed"):
            print("\nalready installed -- nothing to do")
            return
        if state == "OTHER":
            sys.exit("ABORT: the base owner holds neither the expected 0x39 nor 0xBE alone")
        nbody = ours if body == ORIG else retag(body, OLD, NEW)
    else:
        if not state.startswith("installed"):
            print("\nnot installed -- nothing to undo")
            return
        nbody = ORIG if body == ours else retag(body, NEW, OLD)
    out = splice(d, UNIT, nbody)
    err = audit(d, out, UNIT)
    if err:
        sys.exit("ABORT: audit failed -- %s" % err)
    got = owner_ids(dict(pfs.parse_index(out))[UNIT])
    want = (ids - {OLD}) | {NEW} if apply_ else (ids - {NEW}) | {OLD}
    assert got == want, "base abilities %r, expected %r" % (sorted(got), sorted(want))
    kill_aow()
    tmp = UNITRES + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(out)
    os.replace(tmp, UNITRES)
    print("\n%s -- %d -> %d B, CRC OK; base abilities now %s" % (
        "APPLIED" if apply_ else "UNDONE", len(d), len(out), " ".join("%#04x" % i for i in sorted(got))))


if __name__ == "__main__":
    main()
