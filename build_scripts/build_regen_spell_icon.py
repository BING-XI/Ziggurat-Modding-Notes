# -*- coding: utf-8 -*-
r"""
build_regen_spell_icon.py -- the Regeneration spell's book icon: a heart inside a circular arrow
on the Water disc, written into Images/SpellIcn.ILB by REUSING dead entry 129, as
build_embrittle_icon.py reused 128.  No format surgery: every write is exact-size.

    python build_scripts/build_regen_spell_icon.py            dry run + state
    python build_scripts/build_regen_spell_icon.py --apply     write it
    python build_scripts/build_regen_spell_icon.py --undo      restore entry 129 (embedded below)

Entry 129 is cut content (a Syron glyph on a Cosmos disc) that no Spells.pfs record references.
Spells.pfs record 89 (build_regen_spell_pfs.py) points the spell at it.

THE THREE WRITES, offsets measured each run with re_tools/spell_icons.py (file offset = walk's
`off` + its base; the frame's transparent dword is at clip_off + 0x10):
  1. frame pixels, 40x35 RGB565, 2800 B  <- icon 100's (Healing Water: the real SI-Water.BMP disc),
     read from the live file at apply time
  2. frame transparent dword 0 -> 0xFFFF, what every Water frame declares (icon 100 included)
  3. sub pixels, 24x29 RGB565, 1392 B (the entry's own clip, at 9,3) <- ART below

ART is a character grid on build_embrittle_icon.py's RAMP ('.' white = the sub's transparent
0xFFFF, '#' black, ':' '-' '+' '*' the anti-aliased greys vanilla stamps use).  Drawn 2026-10-22
from a supersampled heart and circular arrow, then frozen as text: edit it by hand.

--undo writes back the entry's original 4196 bytes, stored compressed below and SHA-checked
(the root copy of SpellIcn.ILB has another size, so it cannot supply them by offset).
"""
import base64, hashlib, os, struct, sys, zlib, importlib.util

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ILB = os.path.join(GAME, "Images", "SpellIcn.ILB")
TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "re_tools")
ICON_ID, DONOR_ID = 129, 100
SUB_W, SUB_H = 24, 29
TRANSP_WATER = 0x0000FFFF
RAMP = {"#": 0, "*": 56, "+": 112, "-": 160, ":": 208, ".": 255}

ART = [
    "........................",
    "........................",
    "........................",
    "........................",
    ".......-::..............",
    ".......*##**:...........",
    "......:*####............",
    ".....-#####-............",
    "....-###*#*.............",
    "...-###:.*:.........:...",
    "...*##:..:........:*#...",
    "..-##-............-##-..",
    "..*#*....-:..:-....*#*..",
    ".:##+..:*##++##*:..+##:.",
    ".:##-..+########+..-##:.",
    ".:##:..+########+..:##:.",
    ".:##-..:########:..-##:.",
    ".:##+...-######-...+##:.",
    "..*#*....:*##*:....*#*..",
    "..-##-....:##:....-##-..",
    "...*##:....--....:##*...",
    "...-###:........:###-...",
    "....-###+:....:+###-....",
    ".....-####****####-.....",
    "......:*########*:......",
    "........:-+**+-:........",
    "........................",
    "........................",
    "........................",
]

ORIGINAL = (
    "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"
)
ORIGINAL_SHA = "70ff53fcf3250148"


def layout(d):
    spec = importlib.util.spec_from_file_location("si", os.path.join(TOOLS, "spell_icons.py"))
    si = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(si)
    entries, base = si.walk(d)
    ents = {t["id"]: (t, s) for t, s in entries}
    t, subs = ents[ICON_ID]
    dt, _ds = ents[DONOR_ID]
    assert (t["w"], t["h"], t["size"]) == (40, 35, 2800) and len(subs) == 1, "entry 129 is not a 40x35 icon"
    assert subs[0]["clip"][:2] == [SUB_W, SUB_H] and subs[0]["size"] == SUB_W * SUB_H * 2, \
        "entry 129's sub is not 24x29: %r" % subs[0]["clip"]
    assert (dt["w"], dt["h"], dt["size"]) == (40, 35, 2800) and dt["name"] == "SI-Water.BMP", \
        "icon 100 is not the Water disc"
    return {"frame": base + t["off"], "transp": t["clip_off"] + 0x10, "sub": base + subs[0]["off"],
            "donor": base + dt["off"], "donor_transp": dt["clip_off"] + 0x10}


def stamp(art):
    assert len(art) == SUB_H and all(len(r) == SUB_W for r in art), "ART must be 24x29"
    out = bytearray()
    for row in art:
        for ch in row:
            g = RAMP[ch]
            out += struct.pack("<H", ((g >> 3) << 11) | ((g >> 2) << 5) | (g >> 3))
    return bytes(out)


def original():
    raw = zlib.decompress(base64.b64decode("".join(ORIGINAL)))
    assert hashlib.sha256(raw).hexdigest().startswith(ORIGINAL_SHA), "embedded original is corrupt"
    return raw[:2800], raw[2800:2804], raw[2804:]


def writes(d, L, undo):
    if undo:
        fr, tr, sub = original()
    else:
        fr = bytes(d[L["donor"]:L["donor"] + 2800])
        tr = struct.unpack_from("<I", d, L["donor_transp"])[0]
        assert tr == TRANSP_WATER, "icon 100 declares %#x, not 0xFFFF" % tr
        tr, sub = struct.pack("<I", tr), stamp(ART)
    return [(L["frame"], fr, "frame pixels"), (L["transp"], tr, "frame transparent"),
            (L["sub"], sub, "sub pixels")]


def main():
    undo, apply_ = "--undo" in sys.argv, "--apply" in sys.argv
    d = bytearray(open(ILB, "rb").read())
    L = layout(d)
    cur = [bytes(d[o:o + len(b)]) for o, b, _n in writes(d, L, False)]
    st = ("applied" if cur == [b for _o, b, _n in writes(d, L, False)] else
          "original" if cur == [b for _o, b, _n in writes(d, L, True)] else "OTHER")
    print("build_regen_spell_icon -- %s\n  entry %d: %s" % (ILB, ICON_ID, st))
    if st == "OTHER":
        sys.exit("ABORT: entry 129 is neither original nor this build -- refusing to write")
    if not (apply_ or undo) or (apply_ and st == "applied") or (undo and st == "original"):
        print("  (nothing written)")
        return
    size = len(d)
    for o, b, n in writes(d, L, undo):
        d[o:o + len(b)] = b
        print("  wrote %-17s @%#08x (%d B)" % (n, o, len(b)))
    assert len(d) == size
    open(ILB, "wb").write(bytes(d))
    print("  %s" % ("RESTORED" if undo else "APPLIED"))


if __name__ == "__main__":
    main()
