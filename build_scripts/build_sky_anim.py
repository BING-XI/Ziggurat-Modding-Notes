#!/usr/bin/env python3
r"""
build_sky_anim.py -- TRIAL: animated cloud Sky (terrain 0xE).  AoWEPACK.dpl + Release/Release.hss.
Owner request 2026-10-05: hook up Modding Resources/cloud_sky_animation.gif as an alternative Sky,
easy to revert to the current Sky set.  --undo restores both files exactly.

STATUS: REVERTED 2026-10-05.  Worked live in AoWzEd (owner); reverted because the cloud art does
not fit the game's style.  The mechanism is sound for any future animated land terrain.

SOURCE
    cloud_sky_animation.gif: 555x555, 66 frames at 100 ms, looping.  The art is a 5x upscale of a
    48x32 hexagon at (155,200)..(394,359), every 5x5 block uniform, its silhouette identical to the
    shipped Sky tile's (1056 opaque pixels).  Sampled at the block centres -> 66 game-size frames.
    Colours go to RGB565 by truncation (ilb_rle16.rgb_to_rgb565), the tile pixel format.

WHY AN OVERLAY
    Land hexagons (TAoWHexagon, Sky included) are painted once into the cached static scene and
    never revisited; only TAoWWaterHexagon has a per-frame draw.  Owner ruling 2026-10-05: keep Sky a
    land hexagon (so the long cliff curtain, the water/ice-to-void fades, bridges and structure pads
    keep working) and draw the animation over it in the dynamic pass.

HOW
    1. Release.hss: all 8 Sky variants (`H_co.BMP`, RLESprite16) are re-skinned in place with frame 0.
       RLE size depends only on the silhouette, so every record keeps its length; CRC repaired.
    2. AoWEPACK.dpl: hook TAoWHSMap.DrawDynamicScene's entry 0x55778A60 (6 B: push ebx / push esi /
       mov esi,edx / mov ebx,eax -- no .reloc, nothing jumps inside) -> cave_sky, which runs before
       the inherited dynamic draw (so units, fog and the selection still draw on top), then replays
       the prologue.  eax = map, edx = the locked surface descriptor (+0x0C pitch, +0x10..+0x1C clip
       left/top/right/bottom, +0x20 pixels, +0x28 pixel format; layout read from
       ImageLib.TSprite16.ShowOpaque).  Each frame the editor (THSMEdit.BuildDynamicScene) copies
       the whole static scene to the back buffer and then calls this, so nothing persists between
       frames and no dirty-rect bookkeeping is needed.
       cave_sky: live map only ([MAPVAR]); RGB565 (id 0x56509310) or RGB555 (0x55509310 -- what
       AoWzEd's DIB surface actually is, measured with --diag) pick the matching frame table; the
       555 table is converted with ILPACK's own remap (to555), so the frame-0 match is exact; frame =
       (tick ms / FRAME_MS) mod NFRAMES from KUSER_SHARED_DATA (0x7FFE0320 x 0x7FFE0004 >> 24,
       what GetTickCount computes -- a fixed system address, no .reloc); frame 0 draws nothing.
       It walks the visible hexes ([map+0x94]/+0x9C columns, [map+0x98]/+0xA0 rows, level [map+0x88])
       and, for every field whose terrain byte is 0xE, places the tile where THexagon.Show does:
       (hx*32 - [map+0x80], hy*32 + (hx&1)*16 - [map+0x84]).
       blit: a pixel is replaced ONLY where the back buffer still holds that hex's frame-0 pixel --
       i.e. plain Sky.  Anything the static scene drew over Sky (curtains, fades, bridges, pads,
       neighbours' transitions) differs and is left alone.  Clipped to the surface clip rectangle.
    Data: spans (32 x L,R bytes) at DATA_VA, then 66 frames of the 1056 opaque pixels, row-major.

Every Sky hex plays the same frame (the tile is designed to tile; per-hex phase would break the
seams).  The game (AoWz.exe) shares the code; whether its view redraws every frame was not
measured -- if it does not, Sky shows the static frame 0 there.
Rolls: none (display only).  PIC: rel32 + load-delta for module data.
Slot 0x55852200..0x55877FFF (AoWEPACK CODE, measured zero), exclusive.
"""
import argparse
import base64
import hashlib
import os
import re
import struct
import sys
import zlib

sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm

GAME = P.GAME
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))
import ilb  # noqa: E402
import hss_crc  # noqa: E402
from ilb_rle16 import decode, reskin, rgb_to_rgb565  # noqa: E402

HSS = os.path.join(GAME, "Release", "Release.hss")
GIF = os.path.join(GAME, "Modding Resources", "cloud_sky_animation.gif")
SKY = 0x0E
GIF_BOX = (155, 200, 395, 360)          # 240x160 = 48x32 at 5x
SCALE = 5
FRAME_MS = 100

HOOK = 0x55778A60
HOOK_ORIG = bytes.fromhex("53568bf28bd8")
RESUME = 0x55778A66
SLOT = (0x55852200, 0x5589A000)
CAVE = 0x55852200
DATA_VA = 0x55853000                     # spans (64 B), then frames
FRAMES_VA = DATA_VA + 0x40
MAPVAR = 0x558FA040
GETLVL = 0x557020EC                      # thunk HSEPack!TMapContainer.GetMapLevel
FMT565 = 0x56509310
FMT555 = 0x55509310                      # AoWzEd's DIB surface (measured 2026-10-05)
DIAG_VA = 0x558FAF00                     # --diag only: 8 dwords of counters (BSS)

ORIG_SHA = "2512fb36114f14bc"   # today's 8 Sky tiles (after build_sky_dense_retire), file order
ORIG = zlib.decompress(base64.b64decode(
    "eNp9XM3KZUcVvUiwy6BBQgwSQqBmtQcGLzjwAwd248AqxMiHAxMcCDqQc8EIgi+gsxZ7YN4iEV+k8ya2A/EBPKdqr73WPrc1"
    "Tae/n3vr1M+uvddee+373cvlMj7+4NKqWbdhtv875p9Srfb9Z6Wur1s9Xve9+fr399eX/Sf7q/ff7v/V+U7/2vbfmR2/P97z"
    "/uX78z3vXY6x15jzdYYn8Z3HLNYIx+t/MN/37Yu/Zn/fesX83v/2+eo1g2FtzuN4zw/ne9+9mM+z+5P89T5z/DlWs9Yw/93f"
    "96P5/ncux++6ySrnKPh3Mzx1+AzWKvav9vf+eI7x9qVbqecRsBdrBZ07sdawdmGu5e3LT+Y437wcv2lzd9f5xOv2928mI+/f"
    "+05gtmvX9jF+Nsd6a55Fmast8+mt9ljZ2uceu7P2GvPc/Gf7T/dxfj7H+/q+xrWeuVtznFI5O6wd/3bD/ncfb9jNz/3rl1/M"
    "Md+cNjafO62wz3cVX3/njte1uo5ZYrT9781/uj9jH++Xc9xymeu2ts5pzdO/Wk+kZdh8YnGbXTvx/HrzkdeMjn0tl1/Nsb96"
    "wesxkunal337CvikedLYhWufs1//93ns4/5mjv/GJazULWTtt+9TxV6seWN+y/qWHVvsj57u8Yw3Lr+dz/jKRe/CmmmTEVo8"
    "K3asLqv0e1wxbp9ngJP2J+/jH2sp/p7mcz5mW2JfxjzxdZfWM5Y3OcZofpeaW7rN1WzzTIZbodncL1vjmj8FO2IW5+53oPlI"
    "xe2+1eLPkPXM13f6IuN+9TUbnIyPcbvCV5WKp/mc53pGfB++ad1jf+I8Pd+v43yaew/c22PEbzy7rVe6v7DYzxJfH3u54Wa6"
    "TeB2b/MevyH22ypuQ3GfUPymYsT1m1JlHvvf51ecP+794R+3uYavxt1rbj/wcrR+nISP6V5izbTwnsSJuA3uY8JfWESs5u/r"
    "fpI+c8wrIlwRX7nWGXuzjwff5hYXO0Of1mSX8dWyN/ppeNbl2+h/wyNI9MC63FLDytfOfvp4uza548c4iA2l8t7BPjFynBPu"
    "KfySr3+ueB+D8coqsYAx2oQPwJ10KzPs2zHO2xI7EaW3adc9Inbx0ygcJfyNzdiJ+D0EW2DHhtxb/L/ICRzvA3ZYc4at9dgf"
    "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"
))


# ----------------------------------------------------------------- art
def load_frames():
    from PIL import Image
    im = Image.open(GIF)
    frames, mask = [], None
    for i in range(im.n_frames):
        im.seek(i)
        a = im.convert("RGBA").crop(GIF_BOX)
        px = a.load()
        rows = []
        for y in range(32):
            row = []
            for x in range(48):
                r, g, b, al = px[x * SCALE + 2, y * SCALE + 2]
                row.append(rgb_to_rgb565(r, g, b) if al else None)
            rows.append(row)
        m = [[p is not None for p in r] for r in rows]
        if mask is None:
            mask = m
        assert m == mask, "frame %d: silhouette differs" % i
        frames.append(rows)
    return frames, mask


def spans_of(mask):
    out = []
    for y, row in enumerate(mask):
        xs = [x for x, v in enumerate(row) if v]
        assert xs and xs == list(range(xs[0], xs[-1] + 1)), "row %d not one span" % y
        out.append((xs[0], xs[-1] + 1))
    return out


def sky_tiles(data):
    out = []
    for m in re.finditer(rb"\x04ILB\x00", data):
        s = m.start()
        if data[s - 6:s - 2] != b"\x01\x00\x00\x00" or data[s - 1] != 0xFE or data[s - 2] != SKY:
            continue
        p = ilb.parse(data[s:s + struct.unpack_from("<I", data, s + 20)[0]])
        r = p["images"][0]
        off = s + p["hdr"]["imgdir"] + r["offset"]
        out.append((off, bytes(data[off:off + r["size"]]), r["clipw"], r["cliph"], r["transparent"]))
    return out


# ----------------------------------------------------------------- code
def build_cave(nframes, frame_bytes, table555, diag=False):
    a_blit = CAVE + 0x200
    D = DIAG_VA
    dg = (lambda t: t) if diag else (lambda t: "")
    pop_at = CAVE + 9                    # pushad(1) + sub esp,0x24(3) + call(5)
    main = asm(f"""
        pushad
        sub  esp, 0x24
        call {pop_at:#x}
        pop  ebp
        sub  ebp, {pop_at:#x}
        mov  [esp], eax
        mov  [esp+4], edx
{dg(f"inc dword ptr [ebp + {D:#x}]")}
        test edx, edx
        jz   out
{dg(f"mov ecx, [edx+0x28]")}
{dg(f"mov [ebp + {D+4:#x}], ecx")}
        cmp  [ebp + {MAPVAR:#x}], eax
        jne  out
        mov  ecx, [edx+0x28]
        lea  eax, [ebp + {FRAMES_VA:#x}]
        cmp  ecx, {FMT565:#x}
        je   fmtok
        lea  eax, [ebp + {table555:#x}]
        cmp  ecx, {FMT555:#x}
        jne  out
    fmtok:
        mov  [esp+0x20], eax
{dg(f"inc dword ptr [ebp + {D+8:#x}]")}
        mov  eax, dword ptr [0x7FFE0320]
        mul  dword ptr [0x7FFE0004]
        shrd eax, edx, 24
        xor  edx, edx
        mov  ecx, {FRAME_MS}
        div  ecx
        xor  edx, edx
        mov  ecx, {nframes}
        div  ecx
{dg(f"mov [ebp + {D+0xC:#x}], edx")}
        test edx, edx
        jz   out
        imul edx, edx, {frame_bytes}
        add  edx, [esp+0x20]
        mov  [esp+0xC], edx
        mov  eax, [esp]
        mov  edx, [eax+0x88]
        mov  eax, [eax+0x10]
        call {GETLVL:#x}
        test eax, eax
        jz   out
        mov  [esp+8], eax
        mov  eax, [esp]
        mov  ecx, [eax+0x94]
        mov  [esp+0x10], ecx
        add  ecx, [eax+0x9C]
        mov  [esp+0x18], ecx
    colloop:
        mov  ecx, [esp+0x10]
        cmp  ecx, [esp+0x18]
        jge  out
        mov  eax, [esp]
        mov  edx, [eax+0x98]
        mov  [esp+0x1C], edx
        add  edx, [eax+0xA0]
        mov  [esp+0x14], edx
    rowloop:
        mov  edx, [esp+0x1C]
        cmp  edx, [esp+0x14]
        jge  nextcol
        mov  ecx, [esp+0x10]
        mov  ebx, [esp+8]
        test ecx, ecx
        js   nextrow
        test edx, edx
        js   nextrow
        cmp  ecx, [ebx+0xC]
        jge  nextrow
        cmp  edx, [ebx+0x10]
        jge  nextrow
        mov  eax, [ebx+0x74]
        mov  eax, [eax+ecx*4]
        mov  esi, [ebx+0x78]
        add  eax, [esi+edx*4]
        cmp  byte ptr [eax+0x14], {SKY:#x}
        jne  nextrow
        mov  eax, [esp]
        mov  esi, ecx
        shl  esi, 5
        sub  esi, [eax+0x80]
        mov  edi, edx
        shl  edi, 5
        mov  ebx, ecx
        and  ebx, 1
        shl  ebx, 4
        add  edi, ebx
        sub  edi, [eax+0x84]
{dg(f"inc dword ptr [ebp + {D+0x10:#x}]")}
        mov  ebx, [esp+4]
        mov  edx, [esp+0xC]
        mov  eax, [esp+0x20]
        call {a_blit:#x}
    nextrow:
        inc  dword ptr [esp+0x1C]
        jmp  rowloop
    nextcol:
        inc  dword ptr [esp+0x10]
        jmp  colloop
    out:
        add  esp, 0x24
        popad
        push ebx
        push esi
        mov  esi, edx
        mov  ebx, eax
        jmp  {RESUME:#x}
    """, CAVE)
    assert CAVE + len(main) <= a_blit, "cave_sky outgrew its slot"
    # blit: esi = ox, edi = oy, ebx = surface desc, edx = frame N, ebp = load delta.
    blit = asm(f"""
        pushad
        sub  esp, 0x20
        mov  [esp+0x10], esi
        mov  [esp+0x14], edi
        mov  [esp+8], edx
        mov  [esp+4], eax
        lea  eax, [ebp + {DATA_VA:#x}]
        mov  [esp], eax
        mov  dword ptr [esp+0xC], 0
    brow:
        mov  ecx, [esp+0xC]
        cmp  ecx, 32
        jge  bdone
        mov  eax, [esp]
        movzx esi, byte ptr [eax+ecx*2]
        movzx edi, byte ptr [eax+ecx*2+1]
        mov  eax, edi
        sub  eax, esi
        mov  [esp+0x18], eax
        mov  eax, [esp+0x14]
        add  eax, ecx
        cmp  eax, [ebx+0x14]
        jl   bnext
        cmp  eax, [ebx+0x1C]
        jge  bnext
        imul eax, [ebx+0xC]
        add  eax, [ebx+0x20]
        add  esi, [esp+0x10]
        add  edi, [esp+0x10]
        xor  edx, edx
        cmp  esi, [ebx+0x10]
        jge  c1
        mov  edx, [ebx+0x10]
        sub  edx, esi
        mov  esi, [ebx+0x10]
    c1:
        cmp  edi, [ebx+0x18]
        jle  c2
        mov  edi, [ebx+0x18]
    c2:
        mov  ecx, edi
        sub  ecx, esi
        jle  bnext
        lea  edi, [eax+esi*2]
        mov  esi, [esp+4]
        lea  esi, [esi+edx*2]
        mov  eax, [esp+8]
        lea  edx, [eax+edx*2]
    inner:
{dg(f"inc dword ptr [ebp + {D+0x18:#x}]")}
{dg(f"mov ax, [edi]")}
{dg(f"mov [ebp + {D+0x1C:#x}], ax")}
{dg(f"mov ax, [esi]")}
{dg(f"mov [ebp + {D+0x1E:#x}], ax")}
        mov  ax, [edi]
        cmp  ax, [esi]
        jne  sk
{dg(f"inc dword ptr [ebp + {D+0x14:#x}]")}
        mov  ax, [edx]
        mov  [edi], ax
    sk:
        add  edi, 2
        add  esi, 2
        add  edx, 2
        dec  ecx
        jnz  inner
    bnext:
        mov  eax, [esp+0x18]
        shl  eax, 1
        add  [esp+4], eax
        add  [esp+8], eax
        inc  dword ptr [esp+0xC]
        jmp  brow
    bdone:
        add  esp, 0x20
        popad
        ret
    """, a_blit)
    return [("cave_sky", CAVE, main), ("blit", a_blit, blit)]


def to555(p, transparent):
    """ILPACK's RLESprite16 565->555 remap (0x55210A68): drop green's low bit; a result equal to
    the image's transparent colour is bumped by 0x400 (red +1)."""
    q = ((p >> 1) & 0xFFE0) | (p & 0x1F)
    return q + 0x400 if q == transparent else q


def build_data(frames, spans, transparent):
    """-> (spans (0x40 B) + 565 table + 555 table, 555 table VA); a table = every frame's
    opaque pixels, row-major."""
    sp = b"".join(bytes([l, r]) for l, r in spans).ljust(0x40, b"\0")
    t565 = t555 = b""
    for rows in frames:
        for y, (l, r) in enumerate(spans):
            px = rows[y][l:r]
            t565 += struct.pack("<%dH" % len(px), *px)
            t555 += struct.pack("<%dH" % len(px), *(to555(v, transparent) for v in px))
    return sp + t565 + t555, FRAMES_VA + len(t565)


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="TRIAL: animated cloud Sky")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    ap.add_argument("--diag", action="store_true",
                    help="build with BSS counters at DIAG_VA (diagnosis only)")
    a = ap.parse_args()

    assert hashlib.sha256(ORIG).hexdigest().startswith(ORIG_SHA), "embedded originals damaged"
    orig = [ORIG[i * len(ORIG) // 8:(i + 1) * len(ORIG) // 8] for i in range(8)]

    # --- art and blobs
    frames, mask = load_frames()
    spans = spans_of(mask)
    npx = sum(r - l for l, r in spans)
    transparent = {t[4] for t in sky_tiles(open(HSS, "rb").read())}
    assert len(transparent) == 1, "Sky tiles disagree on the transparent colour"
    data_blob, table555 = build_data(frames, spans, transparent.pop())
    blobs = build_cave(len(frames), npx * 2, table555, a.diag)
    blobs.append(("data", DATA_VA, data_blob))
    assert DATA_VA + len(data_blob) <= SLOT[1], "data overflows the slot"
    code_end = max(va + len(b) for n, va, b in blobs if n != "data")
    assert code_end <= DATA_VA
    print("build_sky_anim: %d frames, %d px/hex, data %d B, slot %08X-%08X"
          % (len(frames), npx, len(data_blob), SLOT[0], SLOT[1]))
    if a.dis:
        P.show([b for b in blobs if b[0] != "data"])

    # --- Release.hss state
    hss = bytearray(open(HSS, "rb").read())
    if not hss_crc.verify(bytes(hss)):
        sys.exit("ABORT: Release.hss already has a bad CRC -- find out why first")
    tiles = sky_tiles(hss)
    assert len(tiles) == 8, "expected 8 Sky tiles, found %d" % len(tiles)
    ours = []
    for i, (off, cur, w, h, tr) in enumerate(tiles):
        assert (w, h) == (48, 32) and len(cur) == len(orig[i])
        rows, _ = decode(orig[i], w, h, tr)
        assert [[p is not None for p in r] for r in rows] == mask, "tile %d silhouette" % i
        ours.append(reskin(orig[i], h, tr, lambda x, y: frames[0][y][x]))
    st = ["original" if cur == orig[i] else "frame0" if cur == ours[i] else "FOREIGN"
          for i, (off, cur, *_r) in enumerate(tiles)]
    print("  Release.hss Sky tiles: %s" % ", ".join(st))
    if "FOREIGN" in st:
        sys.exit("ABORT: a Sky tile is neither today's art nor this script's frame 0")

    # --- AoWEPACK.dpl state
    d = bytearray(open(P.TARGET, "rb").read())
    o = P.va2off(d, HOOK)
    hook_new = P.jmp_to(HOOK, CAVE, 6)
    cur = bytes(d[o:o + 6])
    hst = "vanilla" if cur == HOOK_ORIG else "installed" if cur == hook_new else "FOREIGN"
    zo, zh = P.va2off(d, SLOT[0]), P.va2off(d, SLOT[1])
    zone = bytes(d[zo:zh])
    blobs_in = all(bytes(d[P.va2off(d, va):P.va2off(d, va) + len(b)]) == b for _n, va, b in blobs)
    print("  hook %08X: %s; slot: %s" % (HOOK, hst, "zero" if not any(zone)
                                            else "ours" if blobs_in else "NOT ZERO (stale or foreign)"))
    if hst == "FOREIGN":
        sys.exit("ABORT: the hook site holds foreign bytes")
    if P.relocs_in(d, HOOK, HOOK + 6) or P.relocs_in(d, SLOT[0], SLOT[1]):
        sys.exit("ABORT: .reloc entry under the hook or slot")
    if P.rel32_into(d, HOOK, HOOK + 6) or P.short_into(d, HOOK, HOOK + 6, HOOK, HOOK + 0xE0):
        sys.exit("ABORT: a jump lands inside the hook")
    if any(zone) and not blobs_in and hst == "vanilla":
        sys.exit("ABORT: slot is not zero and not ours")

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    P.kill_aow()
    # Release.hss
    for i, (off, cur, *_r) in enumerate(tiles):
        want = ours[i] if a.apply else orig[i]
        hss[off:off + len(want)] = want
    out = hss_crc.fix(bytes(hss))
    assert hss_crc.verify(out) and len(out) == len(hss)
    # AoWEPACK.dpl
    d[zo:zh] = bytes(zh - zo)
    if a.apply:
        for _n, va, b in blobs:
            p = P.va2off(d, va)
            d[p:p + len(b)] = b
    d[o:o + 6] = hook_new if a.apply else HOOK_ORIG
    try:
        open(P.TARGET, "wb").write(d)
        open(HSS, "wb").write(out)
    except PermissionError:
        sys.exit("LOCKED -- close AoWz.exe / AoWzEd.exe and retry")
    print("\n%s" % ("APPLIED: Sky = animated clouds (trial)" if a.apply
                    else "UNDONE: Sky tiles and AoWEPACK restored"))


if __name__ == "__main__":
    main()
