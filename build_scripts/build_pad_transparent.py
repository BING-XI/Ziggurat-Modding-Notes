#!/usr/bin/env python3
r"""
AoW1 mod -- structure PADS draw nothing on Water, Lava, CaveWater and Chasm.

WHAT A PAD IS, AND WHY IT IS THE THING TO PATCH
  `AoWE.TStructureResource.Create @0x5576046C` sets `res[0x44] = 1` for EVERY
  structure resource, so every structure goes through the pad system:
      AoWE.TStructure.CanPlace @0x5575ECC8 -> TPadControl.CanPlacePad @0x5574B958
      AoWE.TStructure.PlaceHX  @0x5575ED10 -> TPadControl.PlacePad    @0x5574B9B0
  A TPad is a real map object placed UNDER the structure, and it carries its own
  terrain-indexed art.  That raised lump of ground under a tower is the pad, not
  part of the structure's own sprite -- the teleporter's layer 1, for instance,
  is only the stone circle.

  Four pad resources live in Release/Release.hss (class 0x20107 = TPadResource),
  one per footprint size, registered by TPadResource at index = the number of
  hexes it covers (`TStructureResource.CalculatePadIndex @0x55760524` counts the
  resource's own terrain list): PAD1.ILB 1 hex, PAD2 2, PAD3 3, PAD4 4.

  Each pad resource's tag-10 image-sequence list is indexed BY TERRAIN ID, and
  vanilla fills {1 Grass, 2 Desert, 3 Snow, 4 Steppe, 5 Wasteland, 11, 12 Dirt}
  with `Pad_Gr/Pad_De/Pad_sn/Pad_st/Pad_Wl/Padu_wl/padu_ca`, each drawn at an
  offset that lifts it ~30px -- that lift is what makes it read as a mound.

WHAT THIS SCRIPT DOES
  Terrain 0xB was appropriated as CHASM (ex-uWasteland, see 09-terrain-movement),
  so every structure on a Chasm hex still gets `Padu_wl` -- a wasteland mound
  hanging in a void.  Ziggurat had already added Water/Lava/CaveWater entries to
  PAD1 by pointing them at FLAT combat base-hex tiles (`TCOMBAT\BASE_HEX\
  H_ugWa.ILB`, `H_La.ILB`) at offset (-9,-1) instead of a lifted PAD1 mound --
  better, but still a disc of ground under a structure standing on liquid.

  This makes all four of those terrains draw NOTHING:
      slot 0  Water      slot 9  Lava      slot 10 CaveWater      slot 11 Chasm
  by appending a fully transparent image to whichever ILB each slot already
  names, then repointing that slot's image index at it.  The image index is a
  bare i32 inside the layer record, so **the .hss edit does not change length** --
  no directory offsets move, only the trailing CRC32 is recomputed.

  Sky (0xE) is NOT listed here: a pad list only has 13 slots (0..12) and the
  editor cannot author past its stored count.  `build_pad_skyalias.py` handles
  Sky by making TPad's GetTerrainTypeImage map 0x0E -> 0x0B, so Sky inherits the
  Chasm slot this script blanks.  The two scripts are independent but only make
  sense together.

WHY A FULLY TRANSPARENT RLESprite16 IS SAFE
  The blitter is ILPACK `0x55210B54` (reached from TRLESprite16.ShowOpaque
  @0x55210310 / ShowTransparent @0x55210474).  It keeps the image's transparent
  colour in ESP and walks each row record as
      u32 reclen ; then pairs of [transparent u16][skip-bytes u16] and literal
      RGB565 pixels, until reclen-4 bytes are consumed
  A `[transparent][skip]` pair advances the destination pointer and writes
  nothing.  The `ecx < 8` tail path at `0x55210D0F` handles a marker as the only
  thing in a row (reads the pair, `add edi,ebx`, ecx hits 0, row ends), so a row
  of exactly `08 00 00 00 <transp> <clipw*2>` means "skip this whole row".  An
  image made of cliph such rows blits as nothing at all.
  No shipped tile uses that encoding (checked across PAD1..4 and the base hexes),
  which is why the blitter was read rather than assumed.

  A transparent image is needed rather than simply deleting the slot: the pad
  slot existing is what makes the terrain legal.  `ILTer.TILTerrainMO.
  ValidTerrainType` (HSEPack 0x5561873C) returns "is there an image sequence at
  GetTerrainTypeImage(terrain)"; drop the slot and the structure becomes
  unplaceable and `GetValidTerrainType @0x55618780` converts the hex instead.

ILB APPEND
  Directory record cloned verbatim from an existing image in the same file, with
  only id / subid / size / offset / name rewritten, inserted just before the
  directory's `-1` terminator at `imgdir-4`; payload appended at end of file;
  header `imgdir` (+16) and `filelen` (+20) bumped.  Image offsets are stored
  RELATIVE to imgdir, so every pre-existing image survives the shift untouched --
  same technique as build_copper_medal.py.  The new image is named ZIG_BLANK.BMP
  so --undo can find it without a stored id.

TARGETS (all under <game>/Ziggurat/, never the vanilla root)
  Release/Release.hss                     -- 4 pad resources, 1 i32 per slot
  Images/PAD1.ILB .. PAD4.ILB             -- +1 transparent image each
  Images/TCOMBAT/BASE_HEX/H_ugWa.ILB      -- +1 transparent image
  Images/TCOMBAT/BASE_HEX/H_La.ILB        -- +1 transparent image

USAGE
  build_pad_transparent.py            -- verify current state (default, no write)
  build_pad_transparent.py --apply    -- write
  build_pad_transparent.py --undo     -- restore vanilla/previous image indices
                                         and drop the appended ZIG_BLANK images
Close every AoW binary first -- the editor locks Release.hss.
"""
import argparse, os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: never beside the target
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
import ilb                                                             # noqa: E402
import hss_crc                                                         # noqa: E402

HSS = os.path.join(GAME, "Release", "Release.hss")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(HSS) + ".pre-padtransparent")

PAD_CLASS = 0x20107
BLANK_NAME = b"ZIG_BLANK.BMP"
# terrain ids whose pad must draw nothing.  0xB is CHASM (ex-uWasteland); Sky
# (0xE) is out of range of a 13-slot pad list and is handled by the alias cave.
BLANK_SLOTS = {0: "Water", 9: "Lava", 10: "CaveWater", 11: "Chasm"}


# --------------------------------------------------------------- .hss directory
def tbl(d, p):
    """Tagged directory at p -> ({tag: offset}, payload_base).  Same codec as
    Zig Modding Tools/zig_hsm.py, which round-trips 30 real maps byte-identically."""
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


def walk_sequences(d, q):
    """tag-10 image-sequence list -> [ (slot, [ (lib, img_field_pos, img) ]) ].

    u32 count, then per slot a marker byte: 1 = empty, 0 = present followed by
    one or more layer records.  A layer is
        u32 namelen + name, u8 layer, u8 flag, u8 mode,
        mode 4: i32 image, i32 dx, i32 dy, i32 z, u32 nframes, i32 frames[]
        else  : i32 image, i32 dx, i32 dy
        u8 more   (1 = another layer follows, 0 = end of slot)
    Cross-checked against the editor: Teleport index 12 layer 1 reads back the
    'Frame Table: 2' the Complex tab shows.
    """
    n = struct.unpack_from("<I", d, q)[0]; q += 4
    out = []
    for i in range(n):
        m = d[q]; q += 1
        if m == 1:
            out.append((i, None)); continue
        assert m == 0, f"bad slot marker {m} at {q-1:#x}"
        layers = []
        while True:
            ln = struct.unpack_from("<I", d, q)[0]
            assert 0 < ln <= 80, f"implausible name length {ln} at {q:#x}"
            name = d[q + 4:q + 4 + ln].decode("latin-1"); q += 4 + ln
            mode = d[q + 2]; q += 3
            layers.append((name, q))                    # q is the image i32
            if mode == 4:
                nf = struct.unpack_from("<I", d, q + 16)[0]
                q += 20 + 4 * nf
            else:
                q += 12
            more = d[q]; q += 1
            if more == 0:
                break
            assert more == 1, f"bad layer terminator {more}"
        out.append((i, layers))
    return out, q


def find_pads(d):
    """-> [ (resid, footprint, [(slot, lib, pos, img)]) ] for every TPadResource."""
    rf, base = tbl(d, 0x37)
    f5, b5 = tbl(d, base + rf[5])
    kids, kb = tbl(d, b5 + f5[1])
    pads = []
    for cid, off in sorted(kids.items(), key=lambda kv: kv[1]):
        p = kb + off
        if struct.unpack_from("<I", d, p)[0] != PAD_CLASS:
            continue
        f, b1 = tbl(d, p + 4)
        resid = struct.unpack_from("<I", d, b1 + f[1])[0]
        foot = struct.unpack_from("<I", d, b1 + f[7])[0]
        slots, _ = walk_sequences(d, b1 + f[10])
        entries = []
        for i, layers in slots:
            if not layers or i not in BLANK_SLOTS:
                continue
            assert len(layers) == 1, f"pad {resid} slot {i} has {len(layers)} layers"
            lib, pos = layers[0]
            entries.append((i, lib, pos, struct.unpack_from("<i", d, pos)[0]))
        pads.append((resid, foot, entries))
    assert pads, "no TPadResource records found -- wrong .hss?"
    return pads


# ------------------------------------------------------------------- ILB append
def blank_payload(clipw, cliph, transparent):
    row = struct.pack("<IHH", 8, transparent, clipw * 2)
    return row * cliph


def rec_bounds(r, im):
    """byte range of image `im`'s directory record, and its name length."""
    later = sorted(x["dir_off"] for x in r["images"] if x["dir_off"] > im["dir_off"])
    end = later[0] if later else r["hdr"]["imgdir"] - 4   # last record: stop before -1
    return im["dir_off"], end, len(im["name"])


def ilb_find_blank(data):
    r = ilb.parse(data)
    return next((im for im in r["images"] if im["name"].encode("latin-1") == BLANK_NAME), None)


def ilb_add_blank(data):
    """-> (new bytes, new image id) or (None, existing id) if already present."""
    r = ilb.parse(data)
    have = next((im for im in r["images"] if im["name"].encode("latin-1") == BLANK_NAME), None)
    if have is not None:
        return None, have["id"]

    imgdir, filelen = r["hdr"]["imgdir"], r["hdr"]["filelen"]
    assert filelen == len(data), f"header filelen {filelen} != actual {len(data)}"
    assert data[imgdir - 4:imgdir] == b"\xff\xff\xff\xff", "no -1 terminator ending the directory"

    src = r["images"][-1]
    assert src["type"] == 17, f"template image is type {src['type']}, expected RLESprite16"
    a, b, nlen = rec_bounds(r, src)
    rec = bytearray(data[a:b])
    o_sub, o_size, o_off = 13 + nlen + 16, 13 + nlen + 21, 13 + nlen + 25
    assert struct.unpack_from("<i", rec, 0)[0] == src["id"]
    assert struct.unpack_from("<i", rec, o_sub)[0] == src["subid"]
    assert struct.unpack_from("<i", rec, o_size)[0] == src["size"]
    assert struct.unpack_from("<i", rec, o_off)[0] == src["offset"]
    assert struct.unpack_from("<i", rec, len(rec) - 4)[0] == -1, "record does not end with -1"

    new_id = max(im["id"] for im in r["images"]) + 1
    payload = blank_payload(src["clipw"], src["cliph"], src["transparent"])
    struct.pack_into("<i", rec, 0, new_id)
    struct.pack_into("<i", rec, o_sub, new_id)
    struct.pack_into("<i", rec, o_size, len(payload))
    struct.pack_into("<i", rec, o_off, filelen - imgdir)     # appended at the old data end
    rec = rec[:9] + struct.pack("<I", len(BLANK_NAME)) + BLANK_NAME + rec[13 + nlen:]

    out = bytearray(data)
    out[imgdir - 4:imgdir - 4] = rec                          # insert before the -1 terminator
    struct.pack_into("<I", out, 16, imgdir + len(rec))        # imgdir moves; offsets are relative
    out += payload
    struct.pack_into("<I", out, 20, len(out))                 # filelen

    n = len(rec)
    assert bytes(out[:16]) == data[:16] and bytes(out[24:imgdir - 4]) == data[24:imgdir - 4], \
        "directory bytes before the insert moved"
    assert bytes(out[imgdir - 4 + n:imgdir + n]) == data[imgdir - 4:imgdir], "lost the -1 terminator"
    assert bytes(out[imgdir + n:filelen + n]) == data[imgdir:filelen], "pixel data changed"
    assert bytes(out[filelen + n:]) == payload, "payload is not at the end"

    r2 = ilb.parse(bytes(out))
    keep = lambda im: {k: v for k, v in im.items() if k not in ("idx", "dir_off")}
    before = {im["id"]: keep(im) for im in r["images"]}
    after = {im["id"]: keep(im) for im in r2["images"]}
    assert new_id in after, "the new image did not parse back"
    for k, v in before.items():
        assert after.get(k) == v, f"image {k} changed across the splice"
    assert after[new_id]["size"] == len(payload) and after[new_id]["trailer_ok"]
    assert bytes(out[r2["hdr"]["imgdir"] + after[new_id]["offset"]:][:len(payload)]) == payload
    return bytes(out), new_id


def ilb_drop_blank(data):
    """-> new bytes with ZIG_BLANK removed, or None if it is not there."""
    r = ilb.parse(data)
    im = next((x for x in r["images"] if x["name"].encode("latin-1") == BLANK_NAME), None)
    if im is None:
        return None
    imgdir, filelen = r["hdr"]["imgdir"], r["hdr"]["filelen"]
    a, b, _ = rec_bounds(r, im)
    assert im["offset"] + im["size"] == filelen - imgdir, \
        "ZIG_BLANK is not the last image -- something was appended after it; undo by hand"
    out = bytearray(data)
    del out[filelen - im["size"]:]                            # drop the payload
    del out[a:b]                                              # drop the record
    struct.pack_into("<I", out, 16, imgdir - (b - a))
    struct.pack_into("<I", out, 20, len(out))
    r2 = ilb.parse(bytes(out))
    keep = lambda x: {k: v for k, v in x.items() if k not in ("idx", "dir_off")}
    before = {x["id"]: keep(x) for x in r["images"] if x["id"] != im["id"]}
    after = {x["id"]: keep(x) for x in r2["images"]}
    assert before == after, "removing ZIG_BLANK disturbed another image"
    return bytes(out)


# ------------------------------------------------------------------------ main
def libpath(lib):
    return os.path.join(GAME, "Images", *lib.replace("/", "\\").split("\\"))


def plan(data, undo):
    """-> (ilb_edits, hss_edits, notes).  ilb_edits: {path: new bytes}."""
    pads = find_pads(data)
    libs = sorted({lib for _, _, ents in pads for _, lib, _, _ in ents})
    ilb_new, blank_id, notes = {}, {}, []

    for lib in libs:
        path = libpath(lib)
        if not os.path.exists(path):
            raise SystemExit(f"ABORT: {path} does not exist")
        raw = open(path, "rb").read()
        if undo:
            out = ilb_drop_blank(raw)
            if out is not None:
                ilb_new[path] = out
                notes.append(f"  {lib}: drop ZIG_BLANK.BMP ({len(raw)} -> {len(out)} bytes)")
            have = ilb_find_blank(raw)
            blank_id[lib] = have["id"] if have else None
        else:
            out, new_id = ilb_add_blank(raw)
            blank_id[lib] = new_id
            if out is not None:
                ilb_new[path] = out
                notes.append(f"  {lib}: +ZIG_BLANK.BMP id {new_id} "
                             f"({len(raw)} -> {len(out)} bytes)")
            else:
                notes.append(f"  {lib}: ZIG_BLANK.BMP id {new_id} already present")

    hss_edits = []
    for resid, foot, ents in pads:
        for slot, lib, pos, img in ents:
            want = blank_id[lib]
            if undo:
                orig = ORIGINALS.get((resid, slot))
                if orig is None:
                    raise SystemExit(f"ABORT: no recorded original for pad {resid} slot {slot}")
                if img == orig:
                    continue
                if want is None or img != want:
                    raise SystemExit(f"ABORT: pad {resid} slot {slot} holds image {img}, "
                                     f"expected {want} (blank) or {orig} (original)")
                hss_edits.append((pos, orig,
                                  f"  pad{foot} (res {resid}) slot {slot:2d} {BLANK_SLOTS[slot]:<9} "
                                  f"{lib}#{img} -> #{orig} (restore)"))
            else:
                if img == want:
                    continue
                if (resid, slot) in ORIGINALS and img != ORIGINALS[(resid, slot)]:
                    raise SystemExit(f"ABORT: pad {resid} slot {slot} holds image {img}, "
                                     f"expected {ORIGINALS[(resid, slot)]} -- hand-edited since?")
                hss_edits.append((pos, want,
                                  f"  pad{foot} (res {resid}) slot {slot:2d} {BLANK_SLOTS[slot]:<9} "
                                  f"{lib}#{img} -> #{want} (blank)"))
    return ilb_new, hss_edits, notes


# The image index each pad slot carried before this script ran: PAD1's Water /
# Lava / CaveWater entries are Ziggurat's own (flat combat base hexes), the rest
# is vanilla `Padu_wl`.  Verify-before-write keys on these, and --undo restores
# them, so a hand-edit in AoWzEd since the last run aborts instead of silently
# overwriting.  (resid, slot) -> image id.
ORIGINALS = {
    (17, 0): 1, (17, 9): 1, (17, 10): 2, (17, 11): 11,
    (18, 11): 11, (19, 11): 11, (20, 11): 11,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    args = ap.parse_args()

    data = bytearray(open(HSS, "rb").read())
    if not hss_crc.verify(bytes(data)):
        print(f"ABORT: {os.path.basename(HSS)} already has a BAD CRC "
              f"(stored {hss_crc.stored_crc(bytes(data)):#010x}, "
              f"computed {hss_crc.crc_of(bytes(data)):#010x}) -- restore it first")
        return 1

    for resid, foot, ents in find_pads(bytes(data)):
        print(f"pad{foot}  res {resid}: " +
              ", ".join(f"{slot}={lib.rsplit(chr(92), 1)[-1]}#{img}"
                        for slot, lib, _, img in ents) or "(no target slots)")

    ilb_new, hss_edits, notes = plan(bytes(data), args.undo)
    for n in notes:
        print(n)
    for _, _, why in hss_edits:
        print(why)
    if not ilb_new and not hss_edits:
        print("already in the requested state (no-op)")
        return 0
    print(f"  {len(hss_edits)} image index i32(s) in {os.path.basename(HSS)} "
          f"(length unchanged), {len(ilb_new)} ILB file(s) rewritten, then CRC repair")
    if not args.apply:
        print("dry run - re-run with --apply to write")
        return 0

    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(HSS, BACKUP)
        print(f"  backup -> {os.path.basename(BACKUP)}")

    size_before = len(data)
    for pos, val, _ in hss_edits:
        struct.pack_into("<i", data, pos, val)
    assert len(data) == size_before, "the .hss changed length -- it must not"
    before = hss_crc.stored_crc(bytes(data))
    data = bytearray(hss_crc.fix(bytes(data)))
    after = hss_crc.stored_crc(bytes(data))
    assert hss_crc.verify(bytes(data)), "CRC repair failed"

    try:
        for path, blob in ilb_new.items():
            open(path, "wb").write(blob)
        open(HSS, "wb").write(bytes(data))
    except PermissionError:
        print("LOCKED - close every AoW binary (the editor locks Release.hss) and retry")
        return 1
    print(f"applied: {len(hss_edits)} slot(s), {len(ilb_new)} ILB(s); "
          f"CRC {before:#010x} -> {after:#010x}; .hss size unchanged ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
