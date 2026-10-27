#!/usr/bin/env python
r"""
build_wotw_anim.py -- Weight of the World's field animation in manual combat: wavy amber contour
lines, like the lines on a map of air pressure or elevation, contracting towards the field's centre
and fading (owner's pick 2026-10-26: amber, 2 px, from three previewed colours).  AoWTCPCK only.
The field is marked by build_wotw_tc.py's landing: bit 0x20 of [field+0x1B] on every hex within 6 of
the target, bit 0x40 on the centre, for the rest of the battle.

HOOK  0x0041BFCA  TAoWCombatMap.DrawDynamicScene's `call HSEngine.THSMap.DrawDynamicScene` (thunk
  0x0040229C; 5 B, EAX = the combat map, EDX = the locked surface descriptor) -> call cave_anim: the
  lines, then the original call.  So they lie over the ground and under every dynamic object (units,
  walls, trees, effects), and the fog pass that follows covers them where the ground is hidden.
  build_tactical_los.py's drawfog hook (0x0041BFDF) is a later call in the same function.
EACH FRAME  for every hex carrying bit 0x40 in the visible hex range ([map+0x94]/[map+0x98], size
  [map+0x9C]/[map+0xA0]) widened by 6, inside the level: four contours, each at life
  u = (t + phase + 30 k) mod 120, t = [map+0x40] (the map's frame counter: 30 a second), phase a
  hash of the centre so fields drift apart.  A contour is a circle of radius 200 (1 - u/120) px
  around the centre, its radius scaled by 1 + 0.08 sin(3a + p1 + w) + 0.05 sin(5a + p2 - 0.7w) +
  0.05 sin(2a + p3) (w turns once in 12 s), sampled at 1024 / 512 / 256 angles by radius and plotted
  as 2x2 dots; a dot is drawn only on a hex carrying bit 0x20, so the lines stop at the field's edge.
  Opacity rises over the first 15 % of a contour's life and falls to 0 at the centre (at most 88 %).
  Colour amber (255, 170, 60), alpha-blended in RGB565 or RGB555 (the descriptor's format; anything
  else draws nothing) with 64-bit products, so every channel is exact.
Display only: nothing here changes game state or draws a random number.
Slot 0x00446000-0x00446FFF, exclusive.  PIC.  Surgical --undo.

    python build_scripts/build_wotw_anim.py            dry run + state
    python build_scripts/build_wotw_anim.py --apply
    python build_scripts/build_wotw_anim.py --undo
    python build_scripts/build_wotw_anim.py --dis
    python build_scripts/build_wotw_anim.py --preview <out.gif>   the same maths, drawn off-line
"""
import math, os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000
from aowepack_patch import asm, run
from piccave import pic

SLOT = (0x00446000, 0x00447000)
HOOK, BASE = 0x0041BFCA, 0x0040229C
GETMAPLEVEL = 0x00401E64
FIELD_BIT, CENTRE_BIT = 0x20, 0x40
PERIOD, RINGS, RMAX, WSPAN = 120, 4, 200, 360
COLOUR = (255, 170, 60)
OPACITY = 0.88
FMT565, FMT555 = 0x56509310, 0x55509310
M565, M555 = 0x07E0F81F, 0x03E07C1F
PHASES = [(0.6, 2.1, 4.0), (1.9, 0.4, 2.7), (3.1, 5.0, 1.2), (4.4, 3.3, 0.5)]   # radians, as previewed


def expand(p, m):
    return (p | (p << 16)) & m


def colour(fmt):
    r, g, b = COLOUR
    return ((r >> 3) << 11 | (g >> 2) << 5 | b >> 3) if fmt == 565 else ((r >> 3) << 10 | (g >> 3) << 5 | b >> 3)


def tables():
    sin = b"".join(struct.pack("<h", int(round(16384 * math.sin(2 * math.pi * i / 1024)))) for i in range(1024))
    rad = bytes(int(round(RMAX * (PERIOD - u) / PERIOD)) for u in range(PERIOD))
    alpha = bytes(int(round(32 * OPACITY * min(1.0, (u / PERIOD) / 0.15) * (1 - u / PERIOD))) for u in range(PERIOD))
    ph = b"".join(struct.pack("<H", int(round(p / (2 * math.pi) * 1024)) & 1023) for trio in PHASES for p in trio)
    tail = sin + rad + alpha + ph
    return tail, {"SIN": 0, "RAD": len(sin), "ALPHA": len(sin) + len(rad), "PH": len(sin) + len(rad) + len(alpha)}


def c_anim(va):
    tail, off = tables()
    ec565, ec555 = expand(colour(565), M565), expand(colour(555), M555)
    src = f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x90
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp - 4], eax
        mov  dword ptr [ebp - 8], edx
        {{ANC}}
        mov  ecx, dword ptr [edx + 0x28]
        cmp  ecx, {FMT565:#x}
        jne  k555
        mov  dword ptr [ebp - 0x34], {M565:#x}
        mov  dword ptr [ebp - 0x30], {ec565:#x}
        jmp  kfmt
    k555:
        cmp  ecx, {FMT555:#x}
        jne  kdone
        mov  dword ptr [ebp - 0x34], {M555:#x}
        mov  dword ptr [ebp - 0x30], {ec555:#x}
    kfmt:
        mov  eax, dword ptr [edx + 0xc]
        mov  dword ptr [ebp - 0x18], eax
        mov  eax, dword ptr [edx + 0x20]
        test eax, eax
        je   kdone
        mov  dword ptr [ebp - 0x1c], eax
        mov  eax, dword ptr [edx + 0x10]
        mov  dword ptr [ebp - 0x20], eax
        mov  eax, dword ptr [edx + 0x14]
        mov  dword ptr [ebp - 0x24], eax
        mov  eax, dword ptr [edx + 0x18]
        mov  dword ptr [ebp - 0x28], eax
        mov  eax, dword ptr [edx + 0x1c]
        mov  dword ptr [ebp - 0x2c], eax
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [eax + 0x88]
        mov  eax, dword ptr [eax + 0x10]
        test eax, eax
        je   kdone
        call {GETMAPLEVEL:#x}
        test eax, eax
        je   kdone
        mov  dword ptr [ebp - 0xc], eax
        mov  ecx, dword ptr [eax + 0xc]
        mov  dword ptr [ebp - 0x70], ecx
        mov  ecx, dword ptr [eax + 0x10]
        mov  dword ptr [ebp - 0x74], ecx
        mov  eax, dword ptr [ebp - 4]
        mov  ecx, dword ptr [eax + 0x80]
        mov  dword ptr [ebp - 0x10], ecx
        mov  ecx, dword ptr [eax + 0x84]
        mov  dword ptr [ebp - 0x14], ecx
        mov  eax, dword ptr [eax + 0x40]
        mov  dword ptr [ebp - 0x38], eax
        xor  edx, edx
        mov  ecx, {WSPAN}
        div  ecx
        mov  eax, edx
        shl  eax, 10
        xor  edx, edx
        div  ecx
        mov  dword ptr [ebp - 0x3c], eax
        imul eax, eax, 717
        shr  eax, 10
        mov  dword ptr [ebp - 0x40], eax
        mov  eax, dword ptr [ebp - 4]
        mov  ecx, dword ptr [eax + 0x94]
        mov  edx, ecx
        add  edx, dword ptr [eax + 0x9c]
        sub  ecx, 6
        jge  kx0
        xor  ecx, ecx
    kx0:
        add  edx, 6
        cmp  edx, dword ptr [ebp - 0x70]
        jle  kx1
        mov  edx, dword ptr [ebp - 0x70]
    kx1:
        mov  dword ptr [ebp - 0x44], ecx
        mov  dword ptr [ebp - 0x4c], edx
        mov  ecx, dword ptr [eax + 0x98]
        mov  edx, ecx
        add  edx, dword ptr [eax + 0xa0]
        sub  ecx, 6
        jge  ky0
        xor  ecx, ecx
    ky0:
        add  edx, 6
        cmp  edx, dword ptr [ebp - 0x74]
        jle  ky1
        mov  edx, dword ptr [ebp - 0x74]
    ky1:
        mov  dword ptr [ebp - 0x48], ecx
        mov  dword ptr [ebp - 0x50], edx
        mov  esi, dword ptr [ebp - 0x48]
    scan_y:
        cmp  esi, dword ptr [ebp - 0x50]
        jge  kdone
        mov  edi, dword ptr [ebp - 0x44]
    scan_x:
        cmp  edi, dword ptr [ebp - 0x4c]
        jge  next_y
        mov  eax, dword ptr [ebp - 0xc]
        mov  ecx, dword ptr [eax + 0x78]
        mov  ecx, dword ptr [ecx + esi*4]
        mov  eax, dword ptr [eax + 0x74]
        add  ecx, dword ptr [eax + edi*4]
        test ecx, ecx
        je   next_x
        test byte ptr [ecx + 0x1b], {CENTRE_BIT:#x}
        je   next_x
        push esi
        push edi
        mov  eax, edi
        mov  edx, esi
        call draw_field
        pop  edi
        pop  esi
    next_x:
        inc  edi
        jmp  scan_x
    next_y:
        inc  esi
        jmp  scan_y
    kdone:
        pop  edi
        pop  esi
        pop  ebx
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [ebp - 8]
        mov  esp, ebp
        pop  ebp
        jmp  {BASE:#x}

    draw_field:
        mov  ecx, eax
        shl  ecx, 5
        add  ecx, 24
        sub  ecx, dword ptr [ebp - 0x10]
        mov  dword ptr [ebp - 0x54], ecx
        mov  ecx, edx
        shl  ecx, 5
        add  ecx, 16
        test al, 1
        je   d_even
        add  ecx, 16
    d_even:
        sub  ecx, dword ptr [ebp - 0x14]
        mov  dword ptr [ebp - 0x58], ecx
        lea  ecx, [eax*8]
        sub  ecx, eax
        imul edx, edx, 13
        add  ecx, edx
        and  ecx, 0x7f
        mov  dword ptr [ebp - 0x8c], ecx
        mov  dword ptr [ebp - 0x5c], 0
    ring:
        mov  eax, dword ptr [ebp - 0x5c]
        imul eax, eax, {PERIOD // RINGS}
        add  eax, dword ptr [ebp - 0x38]
        add  eax, dword ptr [ebp - 0x8c]
        xor  edx, edx
        mov  ecx, {PERIOD}
        div  ecx
        movzx eax, byte ptr [ebx + edx + {{RAD}}]
        mov  dword ptr [ebp - 0x60], eax
        movzx eax, byte ptr [ebx + edx + {{ALPHA}}]
        mov  dword ptr [ebp - 0x64], eax
        cmp  dword ptr [ebp - 0x60], 6
        jl   ring_next
        cmp  dword ptr [ebp - 0x64], 0
        je   ring_next
        mov  dword ptr [ebp - 0x68], 4
        cmp  dword ptr [ebp - 0x60], 50
        jl   step_ok
        mov  dword ptr [ebp - 0x68], 2
        cmp  dword ptr [ebp - 0x60], 100
        jl   step_ok
        mov  dword ptr [ebp - 0x68], 1
    step_ok:
        mov  eax, dword ptr [ebp - 0x5c]
        imul eax, eax, 6
        movzx ecx, word ptr [ebx + eax + {{PH}}]
        mov  dword ptr [ebp - 0x7c], ecx
        movzx ecx, word ptr [ebx + eax + {{PH2}}]
        mov  dword ptr [ebp - 0x80], ecx
        movzx ecx, word ptr [ebx + eax + {{PH4}}]
        mov  dword ptr [ebp - 0x84], ecx
        mov  dword ptr [ebp - 0x6c], 0
    samp:
        mov  esi, dword ptr [ebp - 0x6c]
        lea  eax, [esi + esi*2]
        add  eax, dword ptr [ebp - 0x7c]
        add  eax, dword ptr [ebp - 0x3c]
        and  eax, 1023
        movsx eax, word ptr [ebx + eax*2 + {{SIN}}]
        imul eax, eax, 1311
        sar  eax, 14
        mov  edi, eax
        lea  eax, [esi + esi*4]
        add  eax, dword ptr [ebp - 0x80]
        sub  eax, dword ptr [ebp - 0x40]
        and  eax, 1023
        movsx eax, word ptr [ebx + eax*2 + {{SIN}}]
        imul eax, eax, 819
        sar  eax, 14
        add  edi, eax
        lea  eax, [esi + esi]
        add  eax, dword ptr [ebp - 0x84]
        and  eax, 1023
        movsx eax, word ptr [ebx + eax*2 + {{SIN}}]
        imul eax, eax, 819
        sar  eax, 14
        add  edi, eax
        add  edi, 16384
        mov  eax, dword ptr [ebp - 0x60]
        imul eax, edi
        sar  eax, 14
        mov  edi, eax
        lea  eax, [esi + 256]
        and  eax, 1023
        movsx eax, word ptr [ebx + eax*2 + {{SIN}}]
        imul eax, edi
        sar  eax, 14
        add  eax, dword ptr [ebp - 0x54]
        mov  ecx, eax
        movsx eax, word ptr [ebx + esi*2 + {{SIN}}]
        imul eax, edi
        sar  eax, 14
        add  eax, dword ptr [ebp - 0x58]
        mov  edx, eax
        call plot2
        mov  eax, dword ptr [ebp - 0x68]
        add  dword ptr [ebp - 0x6c], eax
        cmp  dword ptr [ebp - 0x6c], 1024
        jl   samp
    ring_next:
        inc  dword ptr [ebp - 0x5c]
        cmp  dword ptr [ebp - 0x5c], {RINGS}
        jl   ring
        ret

    plot2:
        push ecx
        push edx
        mov  eax, ecx
        add  eax, dword ptr [ebp - 0x10]
        sub  eax, 8
        sar  eax, 5
        cmp  eax, 0
        jl   p_pop
        cmp  eax, dword ptr [ebp - 0x70]
        jge  p_pop
        mov  ecx, edx
        add  ecx, dword ptr [ebp - 0x14]
        test al, 1
        je   p_even
        sub  ecx, 16
    p_even:
        sar  ecx, 5
        cmp  ecx, 0
        jl   p_pop
        cmp  ecx, dword ptr [ebp - 0x74]
        jge  p_pop
        mov  edx, dword ptr [ebp - 0xc]
        push eax
        mov  eax, dword ptr [edx + 0x78]
        mov  ecx, dword ptr [eax + ecx*4]
        pop  eax
        mov  edx, dword ptr [edx + 0x74]
        add  ecx, dword ptr [edx + eax*4]
        test byte ptr [ecx + 0x1b], {FIELD_BIT:#x}
        je   p_pop
        pop  edx
        pop  ecx
        call px1
        inc  ecx
        call px1
        inc  edx
        call px1
        dec  ecx
        call px1
        ret
    p_pop:
        pop  edx
        pop  ecx
        ret

    px1:
        cmp  ecx, dword ptr [ebp - 0x20]
        jl   x_ret
        cmp  ecx, dword ptr [ebp - 0x28]
        jge  x_ret
        cmp  edx, dword ptr [ebp - 0x24]
        jl   x_ret
        cmp  edx, dword ptr [ebp - 0x2c]
        jge  x_ret
        push ecx
        push edx
        push esi
        push edi
        mov  eax, edx
        imul eax, dword ptr [ebp - 0x18]
        add  eax, dword ptr [ebp - 0x1c]
        lea  esi, [eax + ecx*2]
        movzx eax, word ptr [esi]
        mov  edi, eax
        shl  edi, 16
        or   edi, eax
        and  edi, dword ptr [ebp - 0x34]
        mov  eax, dword ptr [ebp - 0x30]
        sub  eax, edi
        imul dword ptr [ebp - 0x64]
        shrd eax, edx, 5
        add  eax, edi
        and  eax, dword ptr [ebp - 0x34]
        mov  edx, eax
        shr  edx, 16
        or   eax, edx
        mov  word ptr [esi], ax
        pop  edi
        pop  esi
        pop  edx
        pop  ecx
    x_ret:
        ret
    """
    fields = {"SIN": ("TAIL", off["SIN"]), "RAD": ("TAIL", off["RAD"]), "ALPHA": ("TAIL", off["ALPHA"]),
              "PH": ("TAIL", off["PH"]), "PH2": ("TAIL", off["PH"] + 2), "PH4": ("TAIL", off["PH"] + 4)}
    return pic(src, va, "ebx", fields, tail)


def preview(path):
    """The cave's arithmetic, in Python, on a mock battlefield: an animated GIF for the owner."""
    from PIL import Image, ImageDraw
    tail, off = tables()
    sin = struct.unpack("<1024h", tail[:2048])
    rad, alpha = tail[off["RAD"]:off["RAD"] + PERIOD], tail[off["ALPHA"]:off["ALPHA"] + PERIOD]
    ph = struct.unpack("<%dH" % (3 * RINGS), tail[off["PH"]:off["PH"] + 6 * RINGS])
    W, H, cx, cy = 520, 440, 8, 6
    sx, sy = cx * 32 + 24, cy * 32 + (cx & 1) * 16 + 16

    def dist(a, b):
        def cube(h):
            x, z = h[0], h[1] - (h[0] - (h[0] & 1)) // 2
            return x, -x - z, z
        p, q = cube(a), cube(b)
        return max(abs(p[i] - q[i]) for i in range(3))
    frames = []
    for t in range(0, PERIOD * 3, 3):
        im = Image.new("RGB", (W, H), (78, 104, 52))
        px = im.load()
        w = (t % WSPAN) * 1024 // WSPAN
        w7 = w * 717 >> 10
        phase = (cx * 7 + cy * 13) & 0x7F
        for k in range(RINGS):
            u = (t + phase + k * (PERIOD // RINGS)) % PERIOD
            r, a = rad[u], alpha[u]
            if r < 6 or a == 0:
                continue
            step = 4 if r < 50 else 2 if r < 100 else 1
            p1, p2, p3 = ph[3 * k:3 * k + 3]
            for i in range(0, 1024, step):
                m = 16384 + (sin[(3 * i + p1 + w) & 1023] * 1311 >> 14) + (sin[(5 * i + p2 - w7) & 1023] * 819 >> 14) \
                    + (sin[(2 * i + p3) & 1023] * 819 >> 14)
                rm = r * m >> 14
                x = sx + (rm * sin[(i + 256) & 1023] >> 14)
                y = sy + (rm * sin[i] >> 14)
                hx = (x - 8) >> 5
                hy = (y - (hx & 1) * 16) >> 5
                if dist((hx, hy), (cx, cy)) > 6:
                    continue
                for ddx, ddy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                    if 0 <= x + ddx < W and 0 <= y + ddy < H:
                        o = px[x + ddx, y + ddy]
                        px[x + ddx, y + ddy] = tuple(o[c] + ((COLOUR[c] - o[c]) * a >> 5) for c in range(3))
        frames.append(im)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)


def main():
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
        return
    va = SLOT[0]
    blob = c_anim(va)
    assert va + len(blob) <= SLOT[1], "slot overflow"
    d = open(P.TARGET, "rb").read()
    van = b"\xE8" + struct.pack("<i", BASE - (HOOK + 5))
    if bytes(d[P.va2off(d, HOOK):P.va2off(d, HOOK) + 5]) not in (van, b"\xE8" + struct.pack("<i", va - (HOOK + 5))):
        sys.exit("ABORT: %08X holds neither the vanilla call nor ours" % HOOK)
    hooks = [(HOOK, van, b"\xE8" + struct.pack("<i", va - (HOOK + 5)))]
    print("  cave_anim %08X, %d B (tables included)" % (va, len(blob)))
    run("build_wotw_anim -- Weight of the World's field animation (AoWTCPCK)", hooks,
        [("cave_anim", va, blob)], SLOT, [])


if __name__ == "__main__":
    main()
