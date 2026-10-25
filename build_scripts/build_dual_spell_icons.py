# -*- coding: utf-8 -*-
r"""
build_dual_spell_icons.py -- spellbook icons for the dual-sphere spells: a new glyph per spell on a
yin-yang glow of its two spheres' discs.  APPENDS new entries to Images/SpellIcn.ILB and to its
half-resolution twin Images/_SpellIcn.ILB (a new image id must exist in BOTH twins, or a lookup can
index past the twin's table: memory aow1-ilb-underscore-halfres).

    python build_scripts/build_dual_spell_icons.py            dry run + state
    python build_scripts/build_dual_spell_icons.py --apply     write / refresh them
    python build_scripts/build_dual_spell_icons.py --undo      remove this script's entries

Owner's ruling 2026-10-25 (05-spells-added.md, "Death/Fire -- the first pair"): a spell-specific
glyph over a glow; a dual spell's glow is a yin-yang of its two spheres' colours, the first-named
sphere on the left, with the two opposite-colour dots.

ENTRY SHAPE (re_tools/spell_icons.py walks it): a composite top record (40x35 Sprite16 frame, the
disc) plus one sub record (the glyph, a grey ink stamp on white; 0xFFFF is transparent), its trailer
dword 0 and the -1 sub-list terminator.  The twin's frame is 20x18 and its SUB is full size, as in
every vanilla pair.  The two unknown dwords before the pixel-format marker are copied from icon 129.

HOW IT WRITES: new records go at the end of the directory, BEFORE its closing -1 (the game's
loader stops at that terminator: 2026-10-25 they were first appended after it and never loaded),
their pixels at the end of the file; `imgdir` and the file-length dword move by the inserted size.  Image offsets are
relative to `imgdir`, so every existing image stays valid.  Before writing, the file is re-walked and
every old entry must come back with identical fields and pixels, and a walk that stops at the first
top-level -1 (as the game's does) must see every new id.  An id already present is refreshed in
place (same geometry); records found after the terminator are moved before it.  --undo requires
this script's entries to be the last records (before or after the closing -1) and the LAST pixel
data (true unless another script appended after them) and cuts them off.

DISCS are read from the live file at apply time: Death = icon 28 (Death Rays), Fire = icon 61
(Living Flame; icon 72 carries two stray blue pixels).  Add a sphere to DISC before using it.
Glyph ART is frozen text on build_embrittle_icon.py's ramp ('.' white = transparent, '#' black,
':' '-' '+' '*' the anti-aliased greys); drawn 2026-10-25 from supersampled shapes; edit by hand.

Snapshots (first --apply only): <Ziggurat>\backups\SpellIcn.ILB.pre-dualicons and
_SpellIcn.ILB.pre-dualicons.  Not a revert path: --undo is.
"""
import os, struct, sys, shutil, importlib.util

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TWINS = [os.path.join(GAME, "Images", "SpellIcn.ILB"), os.path.join(GAME, "Images", "_SpellIcn.ILB")]
BACKUPS = os.path.join(GAME, "backups")
TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "re_tools")
TEMPLATE_ID = 129                      # source of the two unknown dwords per record
PIXFMT = 0x56509310
RAMP = {"#": 0, "*": 56, "+": 112, "-": 160, ":": 208, ".": 255}
DISC = {"Death": 28, "Fire": 61}       # sphere -> a donor icon whose frame is that sphere's disc
GW, GH, GX, GY = 34, 31, 3, 2          # glyph clip (w, h) and inset

TAINT = [
    ".................:-...............",
    "................:*#:..............",
    "...............:###+..............",
    "...............*####..............",
    "..............+#####-......:......",
    ".............:######*.....:*:.....",
    ".......++....+#######:...:##:.....",
    ".......##:...########-..-###-.....",
    "......-##*..:########-.-####-.....",
    "......+###+.-########+:#####+.....",
    "......+####:-########**#####+.....",
    "......+####*+###############+.....",
    "......+#####################+.....",
    "......+########*+++#########+.....",
    "......+######+:.....+#######+.....",
    "......+#####+........-######-.....",
    "......+####*.:+:..:+:.+#####:.....",
    "......+####::###::###::#####:.....",
    "......+####.+###--###+.*####......",
    "......+####.:###::###:.*###*......",
    "......+####:.:+:..:+:.:####*......",
    "......+####+....-+....+####+......",
    "......-#####-...**...:#####-......",
    "......-######-......:######:......",
    ".......######+:-:-:--#####*.......",
    ".......+#####--+-+-+-#####-.......",
    "........*####------+:####*........",
    "........:####*******+###*.........",
    ".........:*############+..........",
    "...........-*########*-...........",
    ".............:--++--:.............",
]
PILLAR = [
    ".*##############################*.",
    ":################################:",
    ":################################:",
    ".################################.",
    ".-##############################-.",
    "..-####-.-+++########+++-.-####-..",
    "....::......:###.-###-......::....",
    "............-##*.+###-............",
    "............-##*.+###-............",
    "............-##*.-###-............",
    "............:###.-###:............",
    "............:###:.###:............",
    "............:###-.###:............",
    ".............###-.*##:............",
    "............:###+.*##:............",
    "............:###-.###-............",
    "............-###.-###*............",
    "............*##+.*####............",
    "...........:###+.*####-...........",
    "...........*###*.-#####...........",
    "..........-#####:.#####+..........",
    ".........:######+.*#####:.........",
    ".........*######-.*######:........",
    "......:+*#################+:......",
    "...::::**################**::::...",
    ".....:-+*################*+-:.....",
    "..-++***##################***++-..",
    "..##############################..",
    "..-############################-..",
    "...:+########################*:...",
    ".....-++******************++-.....",
]
DEMON = [
    "..................................",
    "..................................",
    "..................................",
    "..................................",
    ".-***+-....................-+***-.",
    "..:+####+:..............:+####+:..",
    ".....+####+:...........+####+.....",
    "......:+###*..........*###+:......",
    "........:*##+........-##*:........",
    "..........+##:.......##+..........",
    "........:+-*#*++++++*#*-+-........",
    "........*################*........",
    "........*#################........",
    "........##################:.......",
    ".......:##*############*##-.......",
    ".......-##-:-*######*-:-##+.......",
    ".......-##+...:*##*:...+##+.......",
    "........###+-..*##*..-+###:.......",
    "........*####**####**####*........",
    "........-################+........",
    ".........################:........",
    ".........*##############*.........",
    ".........-##:-#:...#-:##+.........",
    "..........##+:*....+:+##:.........",
    "..........:##-......-##-..........",
    "...........-##++++++*#+...........",
    "............+########*............",
    ".............*######*.............",
    ".............:*####*:.............",
    "...............-**-...............",
    "..................................",
]

# icon id -> (glyph name in the record, (left sphere, right sphere), ART)
ICONS = {
    156: ("TaintTheFlame.png", ("Death", "Fire"), TAINT),
    157: ("PillarOfBanefire.png", ("Death", "Fire"), PILLAR),
    158: ("DemonCurse.png", ("Death", "Fire"), DEMON),
}


def si():
    spec = importlib.util.spec_from_file_location("si", os.path.join(TOOLS, "spell_icons.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def unpack565(v):
    return (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)


def disc_pixels(d, ents, base, sphere):
    t, _s = ents[DISC[sphere]]
    cw, ch = t["clip"][:2]
    assert t["typ"] == 22 and t["clip"][2:] == [0, 0] and t["size"] == cw * ch * 2, \
        "icon %d is not a plain Sprite16 disc" % DISC[sphere]
    return cw, ch, list(struct.unpack_from("<%dH" % (cw * ch), d, base + t["off"]))


def yinyang_mask(w, h):
    """Coverage 0..255 of the LEFT sphere at each pixel (supersampled, then reduced)."""
    from PIL import Image, ImageDraw
    SS = 8
    W, H = w * SS, h * SS
    cx, cy = W / 2, H / 2
    R = min(W, H) * 16.5 / 35          # 16.5 px on the 40x35 disc
    r = R / 2
    inner = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(inner)
    dr.rectangle([0, 0, cx, H], fill=255)
    dr.ellipse([cx - r, cy - R, cx + r, cy], fill=0)       # upper lobe: right sphere
    dr.ellipse([cx - r, cy, cx + r, cy + R], fill=255)     # lower lobe: left sphere
    dot = R * 2.6 / 16.5
    dr.ellipse([cx - dot, cy - r - dot, cx + dot, cy - r + dot], fill=255)
    dr.ellipse([cx - dot, cy + r - dot, cx + dot, cy + r + dot], fill=0)
    straight = Image.new("L", (W, H), 0)
    ImageDraw.Draw(straight).rectangle([0, 0, cx, H], fill=255)
    circle = Image.new("L", (W, H), 0)
    ImageDraw.Draw(circle).ellipse([cx - R, cy - R, cx + R, cy + R], fill=255)
    m = Image.composite(inner, straight, circle)
    small = m.resize((w, h), Image.LANCZOS)
    return list(small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata())


def glow(d, ents, base, left, right):
    """The yin-yang disc as RGB565, never 0xFFFF (the frame's transparent)."""
    w, h, a = disc_pixels(d, ents, base, left)
    w2, h2, b = disc_pixels(d, ents, base, right)
    assert (w, h) == (w2, h2)
    m = yinyang_mask(w, h)
    out = []
    for pa, pb, k in zip(a, b, m):
        ca, cb = unpack565(pa), unpack565(pb)
        v = rgb565(*[int(round((x * k + y * (255 - k)) / 255.0)) for x, y in zip(ca, cb)])
        out.append(0xFFDF if v == 0xFFFF else v)
    return w, h, struct.pack("<%dH" % len(out), *out)


def stamp(art):
    assert len(art) == GH and all(len(r) == GW for r in art), "ART must be %dx%d" % (GW, GH)
    return b"".join(struct.pack("<H", rgb565(RAMP[c], RAMP[c], RAMP[c])) for row in art for c in row)


def i32(v):
    return struct.pack("<i", v)


def record(iid, name, w, h, size, off, tot, unk, clip, transp, composite):
    b = (i32(iid) + (i32(256) if composite else b"")) if iid is not None else b""
    nm = name.encode("latin1")
    b += i32(22) + bytes([3]) + i32(len(nm)) + nm + i32(w) + i32(h) + i32(0) + i32(0) + i32(0)
    b += bytes([1]) + i32(size) + i32(off) + i32(tot[0]) + i32(tot[1]) + i32(unk[0]) + i32(unk[1])
    b += i32(PIXFMT) + b"".join(i32(x) for x in clip) + struct.pack("<I", transp)
    return b


def unknowns(d, rec):
    """The two dwords before the pixel-format marker (info == 3 records)."""
    p = rec["clip_off"] - 12
    a, b, mk = struct.unpack_from("<iiI", d, p)
    assert mk == PIXFMT, "pixel-format marker not where expected"
    return a, b


def layout(path):
    S = si()
    d = bytearray(open(path, "rb").read())
    entries, base = S.walk(d)
    hdr_imgdir, hdr_len = struct.unpack_from("<II", d, 16)
    assert hdr_imgdir == base and hdr_len == len(d), "header imgdir/filelen disagree with the walk"
    return S, d, entries, base


def wanted(path, d, ents, base):
    """id -> (top fields, top pixels, sub fields, sub pixels) for this twin."""
    half = os.path.basename(path).startswith("_")
    t129, s129 = ents[TEMPLATE_ID]
    top_unk, sub_unk = unknowns(d, t129), unknowns(d, s129[0])
    out = {}
    for iid, (gname, (left, right), art) in ICONS.items():
        w, h, px = glow(d, ents, base, left, right)
        assert (w, h) == ((20, 18) if half else (40, 35)), "disc size %dx%d in %s" % (w, h, path)
        top = dict(name="Dual%s%s.png" % (left, right), w=w, h=h, size=len(px), tot=(w, h),
                   unk=top_unk, clip=[w, h, 0, 0], transp=0xFFFF)
        sub = dict(name=gname, w=40, h=35, size=GW * GH * 2, tot=(40, 35), unk=sub_unk,
                   clip=[GW, GH, GX, GY], transp=0xFFFF)
        out[iid] = (top, px, sub, stamp(art))
    return out


def same_geometry(t, s, top, sub):
    return (t["typ"] == 22 and t["clip"] == top["clip"] and t["size"] == top["size"] and len(s) == 1
            and s[0]["clip"] == sub["clip"] and s[0]["size"] == sub["size"])


def check_old_intact(S, old_d, old_entries, old_base, new_d):
    new_entries, new_base = S.walk(new_d)
    by = {t["id"]: (t, s) for t, s in new_entries}
    for t, s in old_entries:
        t2, s2 = by[t["id"]]
        for a, b in [(t, t2)] + list(zip(s, s2)):
            for k in ("typ", "w", "h", "size", "off", "clip", "transparent", "name"):
                assert a.get(k) == b.get(k), "entry %s field %s moved" % (t["id"], k)
            if a.get("off") is not None:
                assert bytes(old_d[old_base + a["off"]:old_base + a["off"] + a["size"]]) == \
                    bytes(new_d[new_base + b["off"]:new_base + b["off"] + b["size"]]), \
                    "entry %s pixels changed" % t["id"]
    return by, new_base


def game_ids(S, d):
    """The top-level ids the GAME reads: its loader stops at the first top-level -1, the
    directory's closing terminator.  (spell_icons.walk skips a -1 and reads on, which hid the
    2026-10-25 bug: 156-158 were appended after the terminator and the game never saw them.)"""
    import inspect
    src = inspect.getsource(S.walk).replace(
        "            o += 4\n            continue\n        top = rec(True)",
        "            break\n        top = rec(True)").replace(
        "    if o != imgdir:\n        raise", "    if o > imgdir - 4:\n        raise")
    assert "break\n        top = rec(True)" in src and "imgdir - 4" in src, "spell_icons.walk changed"
    ns = dict(S.__dict__)
    exec(src.replace("def walk(", "def gwalk("), ns)
    return [t["id"] for t, _s in ns["gwalk"](d)[0]]


def cut_ours(S, d, entries, ents, base, ours):
    """The file with this script's records and pixels removed.  Our records are the last ones,
    either just before the closing -1 (correct) or after it (the 2026-10-25 layout)."""
    first = min(ours)
    start = bytes(d[:base]).find(struct.pack("<ii", first, 256), 28)
    assert start > 0, "record %d not found" % first
    tail_ids = [t["id"] for t, _s in entries][-len(ours):]
    assert sorted(tail_ids) == sorted(ours), "our icons are not the last directory records"
    data_start = min(min(ents[i][0]["off"], ents[i][1][0]["off"]) for i in ours)
    data_end = max(max(ents[i][0]["off"] + ents[i][0]["size"],
                       ents[i][1][0]["off"] + ents[i][1][0]["size"]) for i in ours)
    assert base + data_end == len(d), "our pixels are not the tail of the file"
    term = b"\xff\xff\xff\xff"
    after = bytes(d[base - 8:base]) == term * 2     # our last sub-list -1, then the closing -1
    if after:
        out = bytearray(d[:start]) + term + d[base:base + data_start]
    else:
        assert bytes(d[start - 4:start]) == term, "no closing -1 before our records"
        out = bytearray(d[:start]) + d[base:base + data_start]
    struct.pack_into("<II", out, 16, len(out) - data_start, len(out))
    check_old_intact(S, d, [(t, s) for t, s in entries if t["id"] not in ours], base, out)
    return out


def apply_twin(path, undo, write):
    S, d, entries, base = layout(path)
    ents = {t["id"]: (t, s) for t, s in entries}
    want = wanted(path, d, ents, base)
    ours = [i for i in ICONS if i in ents]
    seen = set(game_ids(S, d))
    state = []
    for iid, (top, px, sub, sp) in sorted(want.items()):
        if iid not in ents:
            state.append("%d absent" % iid)
            continue
        t, s = ents[iid]
        if not same_geometry(t, s, top, sub):
            sys.exit("ABORT: %s icon %d exists with other geometry -- not ours, refusing" % (path, iid))
        cur = (bytes(d[base + t["off"]:base + t["off"] + t["size"]]),
               bytes(d[base + s[0]["off"]:base + s[0]["off"] + s[0]["size"]]))
        state.append("%d %s%s" % (iid, "current" if cur == (px, sp) else "stale",
                                  "" if iid in seen else " but AFTER THE TERMINATOR (unread)"))
    print("  %s: %s" % (os.path.basename(path), ", ".join(state)))
    if not write:
        return

    if undo:
        if not ours:
            print("    nothing to remove")
            return
        out = cut_ours(S, d, entries, ents, base, ours)
        open(path, "wb").write(bytes(out))
        print("    REMOVED %s" % ", ".join(str(i) for i in sorted(ours)))
        return

    if all(x.endswith("current") for x in state):
        print("    nothing to write")
        return
    snap = os.path.join(BACKUPS, os.path.basename(path) + ".pre-dualicons")
    if ours and not all(i in seen for i in ours):
        # rebuild from the unread layout: take ours out, then insert them properly below
        d = cut_ours(S, d, entries, ents, base, ours)
        entries, base = S.walk(d)
        ents = {t["id"]: (t, s) for t, s in entries}
    # refresh existing entries in place
    for iid, (top, px, sub, sp) in want.items():
        if iid in ents:
            t, s = ents[iid]
            d[base + t["off"]:base + t["off"] + len(px)] = px
            d[base + s[0]["off"]:base + s[0]["off"] + len(sp)] = sp
    # insert missing ones before the directory's closing -1
    assert bytes(d[base - 4:base]) == b"\xff\xff\xff\xff", "the directory has no closing -1"
    new = [i for i in sorted(want) if i not in ents]
    recs, data = b"", b""
    rel = len(d) - base
    for iid in new:
        top, px, sub, sp = want[iid]
        o_top, o_sub = rel + len(data), rel + len(data) + len(px)
        recs += record(iid, top["name"], top["w"], top["h"], top["size"], o_top, top["tot"],
                       top["unk"], top["clip"], top["transp"], True)
        recs += record(None, sub["name"], sub["w"], sub["h"], sub["size"], o_sub, sub["tot"],
                       sub["unk"], sub["clip"], sub["transp"], False)
        recs += i32(0) + i32(-1)                     # sub trailer, sub-list terminator
        data += px + sp
    out = bytearray(d[:base - 4]) + recs + d[base - 4:] + data
    struct.pack_into("<II", out, 16, base + len(recs), len(out))
    old_entries = [(t, s) for t, s in entries]
    by, nb = check_old_intact(S, d, old_entries, base, out)
    for iid, (top, px, sub, sp) in want.items():
        t, s = by[iid]
        assert same_geometry(t, s, top, sub), "icon %d came back with other geometry" % iid
        assert bytes(out[nb + t["off"]:nb + t["off"] + t["size"]]) == px
        assert bytes(out[nb + s[0]["off"]:nb + s[0]["off"] + s[0]["size"]]) == sp
    gseen = game_ids(S, out)
    assert all(i in gseen for i in want), "the game's walk does not reach every icon"
    if not os.path.exists(snap):
        os.makedirs(BACKUPS, exist_ok=True)
        shutil.copyfile(path, snap)
        print("    snapshot %s" % os.path.relpath(snap, GAME))
    open(path, "wb").write(bytes(out))
    print("    APPLIED (%s inserted before the closing -1, %d refreshed)"
          % (", ".join(map(str, new)) or "none", len(want) - len(new)))


def main():
    undo, apply_ = "--undo" in sys.argv, "--apply" in sys.argv
    print("build_dual_spell_icons -- icons %s" % ", ".join(map(str, sorted(ICONS))))
    for p in TWINS:
        apply_twin(p, undo, apply_ or undo)
    if not (apply_ or undo):
        print("  (dry run: nothing written)")


if __name__ == "__main__":
    main()
