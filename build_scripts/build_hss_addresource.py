#!/usr/bin/env python3
r"""
AoW1 mod -- add road/bridge resources for terrains that have none:
    Dirt (0x0C) road          cloned from the Wasteland road
    Chasm (0x0B) bridges      cloned from the CaveWater bridges
    Sky (0x0E) bridges        cloned from the Water bridges
(donors chosen by the owner, 2026-09-20)

WHY NEW RESOURCES ARE THE ONLY ROUTE
  `HSEngine.TAbstractRoad.CanPlace @0x5560A820` compares the hex's terrain byte
  (`field[0x14]`) against **entry 0 of the resource's own TTerrainList** (`res[0x28]`,
  tag 7) and refuses on mismatch.  So one road/bridge resource serves exactly ONE
  terrain, and the shipped set is:
      Road      (class 0x20165)  Grass Desert Snow Steppe Wasteland          -- no Dirt
      EngBridge (class 0x20175)  Water Lava CaveWater CaveIce Ice
      HexBridge (class 0x2087B)  Water Ice Lava CaveWater CaveIce
  `HxBridge.THexagonBridge.CanPlace @0x55799AE0` calls the same `TAbstractRoad.CanPlace`
  before its own `DirectionValid` axis test, so all three classes share the rule.
  There is no image-sequence indirection to exploit the way structure pads have --
  the art is embedded per resource (tag 8 is a whole ILB, `\x04ILB`, ~6.6 KB), which
  is also why cloning a donor is the cheap way to get art that fits.

  ⭐ `AoWE.Land @0x5575AEA4` (byte-identical to vanilla) returns "not land" only for
  {0 Water, 6 Ice, 9 Lava, 10 CaveWater, 13 CaveIce}, so **Chasm and Sky already count
  as land**.  `THexagonBridge.DirectionValid @0x55799C04` requires both opposite
  neighbours to be land and `NeighbourTerrainChanged @0x5579A054` frees the bridge when
  no axis qualifies -- so a chasm bridge will NOT delete itself, and (unlike a water
  bridge) it can also be strung across open chasm rather than only shore to shore.

  ⚠ The movement cells must exist too or these are decorative: the Bridge column
  (overlay 5 -> table index 6) of rows 0xB/0xE, owned by `build_chasm_sky_movement.py`
  v2.  Dirt already carried `Road=3` in vanilla.

THE CONTAINER -- a length-CHANGING .hss splice, the first in this project
  Release.hss is nested tagged directories (the codec zig_hsm.py round-trips over 30
  real maps).  The resource list is  root(0x37) -> tag 5 -> tag 1 -> children, each
  child `u32 class` + its own tagged directory.  Child offsets are stored RELATIVE to
  the payload base that follows the child table, so:

    * appending an entry to the child table (+8 bytes per wide entry, and nwide+1)
      shifts that payload base and every child WITH it -- no child offset changes;
    * appending the new records at the END of the payload region disturbs no existing
      child either;
    * what DOES have to move is every ROOT tag whose offset points past the child
      table -- tags 1, 6, 7, 10, 11, 17, 18 -- each bumped by the total growth.
      Root tags 2, 4, 5 point before it and are left alone.  Tag 5's own subtable
      (`f5`) has no entry past tag 1, so nothing there moves.

  Then the trailing CRC32 is recomputed (`HSEngine.THSEngine.LoadHSS`, HSEPack
  0x5560F75C, raises an unhandled Exception('Invalid HSSET') on mismatch and both
  exes vanish with no dialog).

  ⚠⚠ Child ids are DENSE 0..N-1 in the shipped file; new ones continue the run.
  Resource ids (tag 1) are the guid maps store, so new resources get fresh ids and no
  existing map is touched.

USAGE
  build_hss_addresource.py          -- verify / dry run (default, no write)
  build_hss_addresource.py --apply  -- write
  build_hss_addresource.py --undo   -- remove exactly the records this script added
Close every AoW binary first -- the editor locks Release.hss.
"""
import argparse, os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
import hss_crc                                                         # noqa: E402

HSS = os.path.join(GAME, "Release", "Release.hss")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(HSS) + ".pre-addresource")

ROAD, ENGBRIDGE, HEXBRIDGE = 0x20165, 0x20175, 0x2087B
TN = {0: "Water", 5: "Wasteland", 10: "CaveWater", 11: "Chasm", 12: "Dirt", 14: "Sky"}

# (label, class, donor terrain, new terrain, new resource id)
SPECS = [
    ("Dirt road",            ROAD,      5,  12, 0x5A190001),
    ("Chasm engine bridge",  ENGBRIDGE, 10, 11, 0x5A190002),
    ("Chasm hexagon bridge", HEXBRIDGE, 10, 11, 0x5A190003),
    ("Sky engine bridge",    ENGBRIDGE, 0,  14, 0x5A190004),
    ("Sky hexagon bridge",   HEXBRIDGE, 0,  14, 0x5A190005),
]


# ------------------------------------------------------------------ codec helpers
def tbl(d, p):
    b = d[p]; p += 1
    nwide = 0
    if b & 0x80:
        nwide = struct.unpack_from("<I", d, p)[0]; p += 4
    f = {}
    for _ in range(b & 0x7F):
        f[d[p]] = d[p + 1]; p += 2
    for _ in range(nwide):
        t, o = struct.unpack_from("<II", d, p); f[t] = o; p += 8
    return f, p


def tbl_geom(d, p):
    """-> (narrow_count, nwide, table_end, wide_start)."""
    b = d[p]; q = p + 1
    nwide = 0
    if b & 0x80:
        nwide = struct.unpack_from("<I", d, q)[0]; q += 4
    q += 2 * (b & 0x7F)
    return b & 0x7F, nwide, q + 8 * nwide, q


class Hss:
    def __init__(self, d):
        self.d = d
        self.rf, self.base = tbl(d, 0x37)
        self.root_narrow, self.root_nwide, _, self.root_wide = tbl_geom(d, 0x37)
        self.f5, self.b5 = tbl(d, self.base + self.rf[5])
        self.kp = self.b5 + self.f5[1]
        self.kids, self.kb = tbl(d, self.kp)
        self.knarrow, self.knwide, self.kend, self.kwide = tbl_geom(d, self.kp)
        assert self.kend == self.kb
        # children are contiguous in offset order; the region ends where the next
        # root section begins.
        self.order = sorted(self.kids.items(), key=lambda kv: kv[1])
        self.region_end = self.base + self.rf[6]
        assert self.kb + self.order[-1][1] < self.region_end

    def extent(self, i):
        """(start, end) of the i-th child in offset order."""
        s = self.kb + self.order[i][1]
        e = self.kb + self.order[i + 1][1] if i + 1 < len(self.order) else self.region_end
        return s, e

    def info(self, i):
        s, e = self.extent(i)
        cls = struct.unpack_from("<I", self.d, s)[0]
        f, b1 = tbl(self.d, s + 4)
        resid = struct.unpack_from("<I", self.d, b1 + f[1])[0] if 1 in f else None
        terr = self.d[b1 + f[7] + 4] if 7 in f else None
        # Engine.TEResource.ReadWrite @EngineP 0x5551B064:
        #   tag 1 -> [res+0x0C] guid, tag 2 -> [res+0x10] EDIT ID, tag 3 -> [res+0x14] GRID SLOT
        editid = struct.unpack_from("<i", self.d, b1 + f[2])[0] if 2 in f else None
        gridpos = struct.unpack_from("<i", self.d, b1 + f[3])[0] if 3 in f else None
        return dict(cid=self.order[i][0], start=s, end=e, cls=cls, resid=resid, terr=terr,
                    editid=editid, gridpos=gridpos,
                    resid_pos=(b1 + f[1] - s) if 1 in f else None,
                    terr_pos=(b1 + f[7] + 4 - s) if 7 in f else None,
                    gridpos_pos=(b1 + f[3] - s) if 3 in f else None)

    def all_info(self):
        return [self.info(i) for i in range(len(self.order))]


def rootbump(out, h, delta):
    """Add `delta` to every root wide entry whose offset is past the child table."""
    moved = []
    for k in range(h.root_nwide):
        pos = h.root_wide + 8 * k
        tag, off = struct.unpack_from("<II", out, pos)
        if off > h.rf[5]:
            struct.pack_into("<I", out, pos + 4, off + delta)
            moved.append(tag)
    # the narrow entries must all point before the child table
    for k in range(h.root_narrow):
        pos = 0x37 + 1 + (4 if h.root_nwide else 0) + 2 * k
        tag, off = out[pos], out[pos + 1]
        assert off <= h.rf[5], f"narrow root tag {tag} offset {off} is past the child table"
    return moved


# ----------------------------------------------------------------------- splice
def build(d, undo):
    h = Hss(d)
    infos = h.all_info()
    have = {(x["cls"], x["terr"]): x for x in infos}
    mine = {x["resid"]: x for x in infos if x["resid"] in {s[4] for s in SPECS}}

    if undo:
        drop = [x for x in infos if x["resid"] in mine]
        if not drop:
            return None, ["nothing this script added is present (no-op)"]
        notes = [f"  drop cid {x['cid']} class {x['cls']:#x} terrain {x['terr']} "
                 f"({x['end']-x['start']} bytes)" for x in drop]
        # rebuild without them
        keep = [x for x in infos if x["resid"] not in mine]
        return rebuild(d, h, keep, []), notes

    # ⚠⚠ A cloned record must NOT keep its donor's tag 3.  `TECustomResourceGrid.
    # SetResource @EngineP 0x5551FBB8` places a resource at grid slot [res+0x14] and
    # **DESTROYS whatever already occupies that slot** (`mov dl,1; mov ecx,[eax];
    # call [ecx-4]`).  A clone that keeps the donor's slot therefore frees the donor,
    # and every other reference to it dangles -- which is the EAccessViolation that
    # made this look like a 1128-resource ceiling.  Allocate a fresh slot per edit id.
    nextslot = {}
    for x in infos:
        if x["editid"] is not None and x["gridpos"] is not None:
            nextslot[x["editid"]] = max(nextslot.get(x["editid"], -1), x["gridpos"])

    new = []
    notes = []
    for label, cls, dter, nter, resid in SPECS:
        if (cls, nter) in have:
            ex = have[(cls, nter)]
            if ex["resid"] == resid:
                notes.append(f"  {label}: already present (cid {ex['cid']})")
                continue
            raise SystemExit(f"ABORT: a class {cls:#x} resource for terrain {nter} already "
                             f"exists (cid {ex['cid']}, resource id {ex['resid']}) and it is "
                             f"not one of ours -- refusing to add a duplicate")
        if (cls, dter) not in have:
            raise SystemExit(f"ABORT: no donor -- class {cls:#x} terrain {dter} not found")
        src = have[(cls, dter)]
        if src["gridpos_pos"] is None:
            raise SystemExit(f"ABORT: donor cid {src['cid']} has no tag 3 (grid slot); cloning it "
                             f"would collide on slot 0 -- pick a different donor")
        rec = bytearray(d[src["start"]:src["end"]])
        struct.pack_into("<I", rec, src["resid_pos"], resid)
        rec[src["terr_pos"]] = nter
        slot = nextslot[src["editid"]] + 1
        nextslot[src["editid"]] = slot
        struct.pack_into("<i", rec, src["gridpos_pos"], slot)
        new.append((label, bytes(rec), src, nter, resid))
        notes.append(f"  {label}: clone cid {src['cid']} (class {cls:#x}, {TN.get(dter,dter)}) "
                     f"-> terrain {nter} {TN.get(nter,'')}, resource id {resid}, "
                     f"edit id {src['editid']} grid slot {src['gridpos']} -> {slot}, "
                     f"{len(rec)} bytes")
    if not new:
        return None, notes
    return rebuild(d, h, infos, new), notes


def rebuild(d, h, keep, new):
    """Reassemble the file with `keep` children (in order) plus `new` records."""
    out = bytearray()
    out += d[:h.kp]                                   # everything before the child table

    recs = [(x["cid"], bytes(d[x["start"]:x["end"]])) for x in keep]
    nextcid = max(c for c, _ in recs) + 1
    for i, (_, rec, _, _, _) in enumerate(new):
        recs.append((nextcid + i, rec))

    # child table: keep the shipped narrow entries as-is, rewrite the wide list
    narrow = []
    p = h.kp + 1 + (4 if h.knwide else 0)
    for _ in range(h.knarrow):
        narrow.append((d[p], d[p + 1])); p += 2
    narrow_tags = {t for t, _ in narrow}

    payload, offsets = bytearray(), {}
    for cid, rec in recs:
        offsets[cid] = len(payload)
        payload += rec
    wide = [(cid, off) for cid, off in offsets.items() if cid not in narrow_tags]
    for t, o in narrow:
        assert offsets[t] == o, f"narrow child {t} offset moved ({o} -> {offsets[t]})"

    table = bytearray()
    table.append(0x80 | len(narrow))
    table += struct.pack("<I", len(wide))
    for t, o in narrow:
        table += bytes((t, o))
    for t, o in sorted(wide):
        table += struct.pack("<II", t, o)

    out += table
    out += payload
    out += d[h.region_end:]                           # every later root section, verbatim

    growth = (len(table) - (h.kb - h.kp)) + (len(payload) - (h.region_end - h.kb))
    rootbump(out, h, growth)
    return bytes(out), growth


# ------------------------------------------------------------------------- main
def verify(old, new_bytes, expect_added):
    """Re-parse and prove nothing but the intended records changed."""
    a, b = Hss(old), Hss(new_bytes)
    ai, bi = a.all_info(), b.all_info()
    assert len(bi) - len(ai) == expect_added, \
        f"child count moved by {len(bi)-len(ai)}, expected {expect_added}"
    old_by_cid = {x["cid"]: old[x["start"]:x["end"]] for x in ai}
    new_by_cid = {x["cid"]: new_bytes[x["start"]:x["end"]] for x in bi}
    if expect_added >= 0:
        for cid, blob in old_by_cid.items():
            assert new_by_cid.get(cid) == blob, f"child {cid} changed across the splice"
    # everything ahead of the child table is copied verbatim except the root table's
    # own bumped offsets, which live before `base`
    assert old[a.base:a.kp] == new_bytes[b.base:b.kp], "bytes between base and the child table moved"
    # each root section past the child table must still resolve to the same payload
    for tag in sorted(a.rf):
        if a.rf[tag] <= a.rf[5]:
            continue                       # points before the child table; nothing moved
        oa, ob = a.base + a.rf[tag], b.base + b.rf[tag]
        n = min(256, len(old) - oa - 4, len(new_bytes) - ob - 4)
        assert old[oa:oa + n] == new_bytes[ob:ob + n], f"root section {tag} payload changed"
    # and the whole tail beyond the child payload must be byte-identical (minus the CRC)
    assert old[a.region_end:-4] == new_bytes[b.region_end:-4], "the tail after the resources moved"
    assert hss_crc.verify(new_bytes), "CRC does not verify"
    return bi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    args = ap.parse_args()

    d = open(HSS, "rb").read()
    if not hss_crc.verify(d):
        print(f"ABORT: {os.path.basename(HSS)} already has a BAD CRC -- restore it first")
        return 1

    h = Hss(d)
    print(f"{os.path.basename(HSS)}: {len(d)} bytes, {len(h.order)} child resources, "
          f"child table @{h.kp:#x} ({h.knarrow} narrow + {h.knwide} wide), "
          f"payload {h.kb:#x}..{h.region_end:#x}")
    for x in h.all_info():
        if x["cls"] in (ROAD, ENGBRIDGE, HEXBRIDGE):
            kind = {ROAD: "Road", ENGBRIDGE: "EngBridge", HEXBRIDGE: "HexBridge"}[x["cls"]]
            print(f"   {kind:<10} cid {x['cid']:5d}  terrain {x['terr']:#04x} "
                  f"{TN.get(x['terr'],''):<10} res {x['resid']}")

    built, notes = build(d, args.undo)
    for n in notes:
        print(n)
    if built is None:
        print("nothing to do")
        return 0
    new_bytes, growth = built
    added = len(Hss(new_bytes).order) - len(h.order)
    print(f"  file {len(d)} -> {len(new_bytes)} bytes (+{growth}), "
          f"{added:+d} resource(s); root tags rebased")

    new_bytes = hss_crc.fix(new_bytes)
    verify(d, new_bytes, added)
    print("  verified: every pre-existing child byte-identical, every root section resolves, "
          "CRC ok")
    if not args.apply:
        print("dry run - re-run with --apply to write")
        return 0

    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(HSS, BACKUP)
        print(f"  backup -> {os.path.basename(BACKUP)}")
    try:
        open(HSS, "wb").write(new_bytes)
    except PermissionError:
        print("LOCKED - close every AoW binary and retry")
        return 1
    print(f"applied: {os.path.basename(HSS)} now {len(new_bytes)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
