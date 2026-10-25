#!/usr/bin/env python3
r"""
build_deathfire_pfs.py -- Spells.pfs records for the Death/Fire dual-sphere battle spells
(build_deathfire_combat.py registers them): record 90 Taint the Flame (spell 80), record 91 Pillar
of Banefire (spell 81).  Splice machinery is build_embrittle_pfs.py's (sorted insert, wide index,
CRC repaired, every other record proved byte-identical), imported.

    python build_scripts/build_deathfire_pfs.py            dry run + state
    python build_scripts/build_deathfire_pfs.py --apply     write both records
    python build_scripts/build_deathfire_pfs.py --undo      remove both

RECORD 90 = High Prayer's record 112 (its class drives Taint's look: sparkles, then one aura per
  unit), with tag 0x0C's two effect slots pointed at Effects\BANEFIRE.ILB (build_banefire_fx.py):
  slot 0 sparkles 20,21,22,21 (was PARTICLE.ILB 12,13,14,13), slot 1 the flame 0-13 anchored on the
  unit (was MAGIC.ILB 89-109 at -41,-61), the book icon 156 (build_dual_spell_icons.py), and Death
  Rays' (record 113) sound list as tag 0x0B.
RECORD 91 = Geyser's record 128, slots 0/1/2 pointed at BANEFIRE.ILB (spray 30,31,32,30; burst
  40-44; loop 43,44,42,43,44 -- the same frame orders Geyser uses), icon 157, and Triple Fireball's
  (record 127) sound list: cue 0 plays during the fall, cue 1 at the landing.
Both: description (owner's text), mana, research (the typical single tier N+1 figure: it prices
Wizard's Tower offers), sphere 7 (dual), tier, caster family 1 (Evoker).  Upkeep none.
"""
import importlib.util, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("_emb", os.path.join(HERE, "build_embrittle_pfs.py"))
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)
from aowepack_patch import kill_aow                          # noqa: E402

TAG_SFX, TAG_IMG, TAG_FAMILY = 0x0B, 0x0C, 0x12
FX = b"EFFECTS\\BANEFIRE.ILB"

SPELLS = [
    dict(rec=90, donor=112, sfx_from=113, icon=156, mana=8, research=80, tier=1, family=1,
         desc="Strikes every unit that's burning or has Living Flame ability with Death damage.",
         slots={0: ([20, 21, 22, 21], None), 1: (list(range(14)), (-12, -40))}),
    dict(rec=91, donor=128, sfx_from=127, icon=157, mana=16, research=160, tier=2, family=1,
         desc="The flame of the underworld burns the essence and can even destroy stone walls.",
         slots={0: ([30, 31, 32, 30], None), 1: (list(range(40, 45)), None),
                2: ([43, 44, 42, 43, 44], None)}),
]


# ---- tag 0x0C: TImageSequenceList (u32 count; per slot u8 flag 0 = sequence follows) ----------
def _seq(v, o):
    ln = struct.unpack_from("<I", v, o)[0]; o += 4
    s = {"name": bytes(v[o:o + ln])}; o += ln
    s["f8"], s["f18"], s["kind"] = v[o], v[o + 1], v[o + 2]; o += 3
    s["f20"], s["xs"], s["ys"] = struct.unpack_from("<Iii", v, o); o += 12
    if s["kind"] in (4, 5):
        s["ft10"], n = struct.unpack_from("<II", v, o); o += 8
        s["frames"] = list(struct.unpack_from("<%dI" % n, v, o)); o += 4 * n
    ch = v[o]; o += 1
    s["chain"] = None
    if ch:
        s["chain"], o = _seq(v, o)
    return s, o


def seq_parse(v):
    n = struct.unpack_from("<I", v, 0)[0]; o = 4; out = []
    for _ in range(n):
        f = v[o]; o += 1
        if f:
            out.append(None)
            continue
        s, o = _seq(v, o)
        out.append(s)
    assert o == len(v), "trailing bytes in tag 0x0C"
    return out


def _seq_build(s):
    out = struct.pack("<I", len(s["name"])) + s["name"] + bytes([s["f8"], s["f18"], s["kind"]])
    out += struct.pack("<Iii", s["f20"], s["xs"], s["ys"])
    if s["kind"] in (4, 5):
        out += struct.pack("<II", s["ft10"], len(s["frames"])) + struct.pack("<%dI" % len(s["frames"]),
                                                                            *s["frames"])
    return out + (b"\x01" + _seq_build(s["chain"]) if s["chain"] else b"\x00")


def seq_build(slots):
    return struct.pack("<I", len(slots)) + b"".join(
        b"\x01" if s is None else b"\x00" + _seq_build(s) for s in slots)


def fields(body):
    ent, dsz = E.T.body_dir(body)
    return dict(E.T.slice_fields(body, ent, dsz))


def builder_for(spec_, sfx):
    def build(donor):
        f = fields(donor)
        f[E.TAG_DESC] = E.pstr32(spec_["desc"])
        f[E.TAG_MANA] = struct.pack("<I", spec_["mana"])
        f[E.TAG_RESEARCH] = struct.pack("<I", spec_["research"])
        f[E.TAG_SPHERE] = bytes([7])
        f[E.TAG_TIER] = bytes([spec_["tier"]])
        f[TAG_FAMILY] = bytes([spec_["family"]])
        f[TAG_SFX] = sfx
        slots = seq_parse(f[TAG_IMG])
        for k, (frames, anchor) in spec_["slots"].items():
            s = slots[k]
            assert s is not None and s["kind"] in (4, 5) and s["chain"] is None, \
                "record %d slot %d is not a plain frame sequence" % (spec_["donor"], k)
            s["name"], s["frames"] = FX, frames
            if anchor:
                s["xs"], s["ys"] = anchor
        icon = slots[10]
        assert icon is not None and icon["name"] == E.ICON_PATH and icon["kind"] == 0, "slot 10 is not the icon"
        icon["f20"] = spec_["icon"]
        f[TAG_IMG] = seq_build(slots)
        assert seq_parse(f[TAG_IMG]) == slots
        return E.reserialise(f)
    return build


def main():
    undo, apply_ = "--undo" in sys.argv, "--apply" in sys.argv
    d = E.read(E.SPELLS)
    if (E.zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF) != E.PFS_RESIDUE:
        sys.exit("ABORT: Spells.pfs CRC residue already wrong")
    out = bytearray(d)
    changed = False
    for sp in SPELLS:
        base, _ent, _ws, span = E.records(out)
        sfx = fields(E.body_of(out, base, span, sp["sfx_from"]))[TAG_SFX]
        build = builder_for(sp, sfx)
        want = build(E.body_of(out, base, span, sp["donor"]))
        present = sp["rec"] in span
        match = present and E.body_of(out, base, span, sp["rec"]) == want
        print("  Spells.pfs record %d: %s" % (sp["rec"], "present, matches" if match else
                                              "PRESENT, differs" if present else "absent"))
        if not (apply_ or undo) or (apply_ and match) or (undo and not present):
            continue
        before = bytes(out)
        if present:
            out = E.remove(out, sp["rec"])
        if apply_:
            out = E.insert(out, sp["rec"], sp["donor"], build)[0]
        E.fix_crc(out)
        problem = E.audit(bytearray(before), out, sp["rec"], expect_present=apply_)
        if problem:
            sys.exit("ABORT: record %d audit failed -- %s (nothing written)" % (sp["rec"], problem))
        changed = True
    if changed:
        kill_aow()
        open(E.SPELLS, "wb").write(out)
        print("    %s (%d -> %d B, CRC repaired)" % ("WRITTEN" if apply_ else "REMOVED", len(d), len(out)))
    if not (apply_ or undo):
        print("\n(dry run -- nothing written.  --apply to write, --undo to remove)")


if __name__ == "__main__":
    main()
