#!/usr/bin/env python
r"""
build_unit_vfx.py -- how Invisibility and Mistform units look.  AoWEPACK.dpl + AoWTCPCK.dpl.
Owner's request 2026-10-29: an invisible unit stays opaque most of the time and every few seconds
eases into semi-transparency and back; a Mistform unit is drawn permanently misty, partly
transparent and partly tinted towards a cloudy pale white ("don't go overboard").

WHAT IT DRAWS
    Invisibility (ability 0x36): opaque, except a dip of PULSE_DIP_S seconds every PULSE_PERIOD_S
        seconds, a raised cosine down to PULSE_FLOOR opacity and back.  Each unit (each army on the
        world map) has its own phase, a hash of its hotspot's address, so they do not pulse together.
    Mistform (enchantment 0x54, build_airwater_ench.py): MIST_OPACITY opacity, its colours moved
        MIST_TINT of the way towards MIST_COLOUR, for as long as the enchantment lasts.
    Both: the mist with the pulse multiplied into its opacity.
    Where: both maps.  In manual combat every unit is drawn for both sides (vanilla gives
    Invisibility no combat effect; build_invis_penalty.py's ATK penalty is what it shows).  On the
    world map the army figure is the unit TArmyHS+0x20 names (unit 0, or the first unconcealed unit
    when the viewer sees through concealment): it pulses or mists when that unit holds the ability.
    An army is drawn only for viewers who can see it -- its owner, and enemies within True Vision
    range when it is concealed -- so that is who sees the effect.  Shadows, banners, health bars and
    status overlays are drawn as before.

THE CLOCK
    The frame counter of the map being drawn, [map+0x40] (HSEngine.THSMap.NewFrame increments it
    once per display frame; AoWz.exe's TDisplay runs at 30 frames a second, FPS).  The army
    figure's own animation and vanilla's pulsing banner on a concealed army run on the same counter.
    Display only: the caves read the counter and the units' abilities and write pixels.  Nothing is
    stored, no game state changes, no random number is drawn.

HOW (vfx_core, one copy per module)
    Both views repaint every frame: THSMapViewer.ShowScene blits the cached static scene and calls
    every dynamic object's Show.  vfx_core(image, x, y, surface, opacity, tint, map) takes the union
    of the image's visual rectangles (VMT +0x38 GetVisualDimensions, (0,0,w,h) and (xshift,yshift)+
    (w,h); a TImageNode adds each child's), clips it to the surface's clip rectangle, copies those
    pixels to a stack buffer (page-probed, at most MAX_PIXELS), lets the engine draw the image
    normally (VMT +0x84 Show), then rewrites every pixel the draw changed:
        out = old + (tint(m(new)) - old) * opacity,  tint(c) = c + (MIST_COLOUR - c) * tint
    per channel in RGB565 or RGB555 (surface +0x28; any other format, or a larger rectangle, draws
    normally).  m is the identity when map is 0; otherwise map points at 64 RGB565 words followed by
    64 RGB555 words, and m(c) is the entry for c's 6-bit luminance (r*154 + g*150 + b*58 >> 8 in
    565, g*300 in 555, clamped to 63).  Generic on purpose: most unit sprites are TRLESprite08,
    which has no transparent or blended draw in ILPACK, and the rest are TRLESprite16 / TSprite16.
    A sprite pixel identical to the background behind it is left as it was.
    Other callers (AoWTCPCK, the pinned T_CORE): build_mirrorimage.py's dispatch draws Mirror
    Image's copies through it (opacity 128) and Stone Gaze's statues (opacity 256, map = Stone
    Gaze's colour table), after testing this zone's header.

AoWEPACK (world map)
    M   0x557916C5 0x5579180A 0x55791AA9  TArmyHS.Show's three figure draws, `call [ebx+0x84]`
        (6 B each; one per branch: ordinary, owner's concealed army, seen through concealment) ->
        call vfx_map + nop.  ESI = the TArmyHS throughout Show (asserted: Show is vanilla apart from
        these sites).  vfx_map: unit = TUnitList.GetUnit(army [hs+0x1C], [hs+0x20]); Mistform and
        Invisibility through the item-aware GetAbilityEnabled (VMT +0x148); clock AoWHSMap+0x40.
AoWTCPCK (manual combat)
    No hook of its own.  build_mirrorimage.py's Show wrapper owns the six body draws: while this
    zone's header "UVX1" (0x0044C000) is present, its cave_show sets bit 2 (DRAW_VFX) of the draw
    byte [unit+0x6A] for a live unit, and its dispatch jumps here (vfx_tc, 0x0044C010, pinned) for a
    body draw that is neither a Stone Gaze statue (bit 1) nor a mirror copy (bit 0).  vfx_tc: the
    combat unit [hs+0x1C], abilities through its VMT +0xA8 (TCombatUnit.GetAbilityEnabled, which
    asks the source unit, so Mistform vanishes the moment a blow ends it); clock: the combat map,
    AoWTCPCK's 0x0046C064, +0x40.
    ⚠ COUPLING: the combat half is drawn only while build_mirrorimage.py is applied.  Either script
    may be undone first: Mirror Image tests the header before marking or calling vfx_core, and this
    zone holds no call into Mirror Image.  vfx_tc 0x0044C010 and vfx_core 0x0044C800 are pinned
    (Mirror Image calls both); a change to vfx_core's arguments needs build_mirrorimage.py's
    cave_disp rewritten with it, and --apply of this script first (Mirror Image's checks compare
    the bytes at 0x0044C800 with this script's vfx_core while the header is present).

TUNING  the constants below; --apply rewrites both zones in place.
Slots: AoWEPACK 0x558CA000-0x558CA7FF, AoWTCPCK 0x0044C000-0x0044CFFF (header 0x0044C000-0x0044C00F
written as a hook), exclusive.  PIC.  Surgical --undo (both modules).

    python build_scripts/build_unit_vfx.py            dry run + state
    python build_scripts/build_unit_vfx.py --apply
    python build_scripts/build_unit_vfx.py --undo
    python build_scripts/build_unit_vfx.py --dis
"""
import math, os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

import aowepack_patch as P
from aowepack_patch import run
from piccave import pic

# ---------------------------------------------------------------- tuning
FPS = 30                          # AoWz.exe TDisplay FrameRate: the map frame counters' rate
PULSE_PERIOD_S = 5.0              # Invisibility: one dip every this many seconds
PULSE_DIP_S = 1.2                 # the dip lasts this long, opaque -> PULSE_FLOOR -> opaque
PULSE_FLOOR = 0.40                # opacity at the bottom of the dip
MIST_OPACITY = 0.70               # Mistform: opacity
MIST_TINT = 0.40                  # Mistform: how far each colour moves towards MIST_COLOUR
MIST_COLOUR = (228, 234, 242)     # Mistform: the cloudy pale white (R, G, B)
MAX_PIXELS = 32768                # larger visible rectangles draw normally (64 KB of stack)

# ---------------------------------------------------------------- engine
EPACK = P.TARGET
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")
ROOT_EPACK = os.path.join(os.path.dirname(P.GAME), "AoWEPACK.dpl")
INVIS, MISTFORM = 0x36, 0x54
FMT565, FMT555 = 0x56509310, 0x55509310
GET_PREF = 0x5521A8B8                            # ILPACK TCustomImageLibrary.Get (preferred VA)
VMT_NODE = 0x5520A65C                            # ILPACK TImageNode
IMG_VISDIM, IMG_SHOW = 0x38, 0x84
NODE_ITEMS, NODE_COUNT = 0x40, 0x48

E_SLOT = (0x558CA000, 0x558CA800)
E_IAT_GET = 0x558FC1A0
E_HSMAP = 0x558FA040                             # AoWE.AoWHSMap
E_GETUNIT = 0x5578309C                           # TUnitList.GetUnit (nil when out of range)
V_ABENABLED_UNIT = 0x148                         # TAbstractUnit/THero GetAbilityEnabled
ARMYHS_SHOW = (0x557914D8, 0x55791BEC)
E_SITES = (0x557916C5, 0x5579180A, 0x55791AA9)
E_VANILLA = bytes.fromhex("ff9384000000")

T_MAGIC_VA, T_MAGIC = 0x0044C000, 0x31585655     # "UVX1": build_mirrorimage.py tests it
T_SLOT = (0x0044C010, 0x0044D000)
T_ENTRY = 0x0044C010                             # build_mirrorimage.py's dispatch jumps here
T_CORE = 0x0044C800                              # ... and calls this vfx_core (copies, statues)
T_IAT_GET = 0x0046DE04
T_CMAP = 0x0046C064                              # AoWTCPCK's combat map variable
V_ABENABLED_CU = 0xA8                            # TCombatUnit.GetAbilityEnabled

PERIOD = int(round(PULSE_PERIOD_S * FPS))
DIP = int(round(PULSE_DIP_S * FPS))
MIST_A = int(round(256 * MIST_OPACITY))
MIST_T = int(round(256 * MIST_TINT))
assert 0 < DIP <= PERIOD < 0x10000 and 0 <= MIST_A <= 256 and 0 <= MIST_T <= 256
assert 0.0 <= PULSE_FLOOR <= 1.0


def pulse_table():
    """Opacity 0..256 for each frame of the dip: a raised cosine, 256 at both ends."""
    out = []
    for t in range(DIP):
        dip = (1 - math.cos(2 * math.pi * t / DIP)) / 2
        out.append(int(round(256 * (1 - (1 - PULSE_FLOOR) * dip))))
    return out


PULSE = pulse_table()


def mist_channels():
    r, g, b = MIST_COLOUR
    return {565: (r >> 3, g >> 2, b >> 3), 555: (r >> 3, g >> 3, b >> 3)}


def build_core(va, iat_get):
    """vfx_core(EAX image, EDX x, ECX y, [esp+4] surface, [esp+8] opacity 0..256,
    [esp+0xC] tint 0..256, [esp+0x10] colour map or 0), `ret 0x10`, saves EBX/ESI/EDI.
    Locals: -4 image, -8 x, -0xC y, -0x10..-0x1C rect L T R B, -0x20 w, -0x24 h, -0x28 buffer,
    -0x2C ESP after the pushes, -0x30 pitch, -0x34 first pixel, -0x38 red shift, -0x3C green mask,
    -0x40/-0x44/-0x48 mist R G B, -0x4C rows left, -0x50 columns left, -0x54 new, -0x58 old,
    -0x5C result, -0x60 this format's map (or 0), -0x64 green luminance weight,
    -0x80..-0x74 a scratch rectangle."""
    m = mist_channels()
    src = f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x90
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp - 0x2c], esp
        mov  dword ptr [ebp - 4], eax
        mov  dword ptr [ebp - 8], edx
        mov  dword ptr [ebp - 0xc], ecx
        {{ANC}}
        mov  esi, dword ptr [ebp + 8]
        mov  eax, dword ptr [esi + 0x28]
        mov  ecx, dword ptr [ebp + 0x14]
        cmp  eax, {FMT565:#x}
        jne  c_555
        mov  dword ptr [ebp - 0x38], 11
        mov  dword ptr [ebp - 0x3c], 63
        mov  dword ptr [ebp - 0x64], 150
        mov  dword ptr [ebp - 0x40], {m[565][0]}
        mov  dword ptr [ebp - 0x44], {m[565][1]}
        mov  dword ptr [ebp - 0x48], {m[565][2]}
        jmp  c_fmt
    c_555:
        cmp  eax, {FMT555:#x}
        jne  c_plain
        mov  dword ptr [ebp - 0x38], 10
        mov  dword ptr [ebp - 0x3c], 31
        mov  dword ptr [ebp - 0x64], 300
        mov  dword ptr [ebp - 0x40], {m[555][0]}
        mov  dword ptr [ebp - 0x44], {m[555][1]}
        mov  dword ptr [ebp - 0x48], {m[555][2]}
        test ecx, ecx
        je   c_fmt
        add  ecx, 0x80
    c_fmt:
        mov  dword ptr [ebp - 0x60], ecx
        cmp  dword ptr [esi + 0x20], 0
        je   c_plain
        mov  dword ptr [ebp - 0x10], 0x7fffffff
        mov  dword ptr [ebp - 0x14], 0x7fffffff
        mov  dword ptr [ebp - 0x18], 0x80000000
        mov  dword ptr [ebp - 0x1c], 0x80000000
        mov  eax, dword ptr [ebp - 4]
        call c_radd
        mov  ecx, dword ptr [edi + {{GETIAT}}]
        sub  ecx, {GET_PREF:#x}
        add  ecx, {VMT_NODE:#x}
        mov  eax, dword ptr [ebp - 4]
        cmp  dword ptr [eax], ecx
        jne  c_rect
        mov  ebx, dword ptr [eax + {NODE_COUNT:#x}]
        mov  esi, dword ptr [eax + {NODE_ITEMS:#x}]
        test esi, esi
        je   c_rect
    c_node:
        dec  ebx
        js   c_rect
        mov  eax, dword ptr [esi + ebx*4]
        test eax, eax
        je   c_node
        call c_radd
        jmp  c_node
    c_rect:
        mov  eax, dword ptr [ebp - 0x10]
        cmp  eax, dword ptr [ebp - 0x18]
        jge  c_plain
        mov  eax, dword ptr [ebp - 0x14]
        cmp  eax, dword ptr [ebp - 0x1c]
        jge  c_plain
        mov  esi, dword ptr [ebp + 8]
        mov  eax, dword ptr [ebp - 8]
        add  dword ptr [ebp - 0x10], eax
        add  dword ptr [ebp - 0x18], eax
        mov  eax, dword ptr [ebp - 0xc]
        add  dword ptr [ebp - 0x14], eax
        add  dword ptr [ebp - 0x1c], eax
        mov  eax, dword ptr [esi + 0x10]
        cmp  eax, dword ptr [ebp - 0x10]
        jle  k_1
        mov  dword ptr [ebp - 0x10], eax
    k_1:
        mov  eax, dword ptr [esi + 0x14]
        cmp  eax, dword ptr [ebp - 0x14]
        jle  k_2
        mov  dword ptr [ebp - 0x14], eax
    k_2:
        mov  eax, dword ptr [esi + 0x18]
        cmp  eax, dword ptr [ebp - 0x18]
        jge  k_3
        mov  dword ptr [ebp - 0x18], eax
    k_3:
        mov  eax, dword ptr [esi + 0x1c]
        cmp  eax, dword ptr [ebp - 0x1c]
        jge  k_4
        mov  dword ptr [ebp - 0x1c], eax
    k_4:
        mov  eax, dword ptr [ebp - 0x18]
        sub  eax, dword ptr [ebp - 0x10]
        jle  c_plain
        mov  dword ptr [ebp - 0x20], eax
        mov  ecx, dword ptr [ebp - 0x1c]
        sub  ecx, dword ptr [ebp - 0x14]
        jle  c_plain
        mov  dword ptr [ebp - 0x24], ecx
        imul eax, ecx
        cmp  eax, {MAX_PIXELS}
        ja   c_plain
        lea  ecx, [eax + eax + 0xfff]
        and  ecx, 0xfffff000
    c_probe:
        sub  esp, 0x1000
        or   dword ptr [esp], 0
        sub  ecx, 0x1000
        jne  c_probe
        mov  dword ptr [ebp - 0x28], esp
        mov  eax, dword ptr [esi + 0xc]
        mov  dword ptr [ebp - 0x30], eax
        mov  eax, dword ptr [ebp - 0x14]
        imul eax, dword ptr [esi + 0xc]
        add  eax, dword ptr [esi + 0x20]
        mov  edx, dword ptr [ebp - 0x10]
        lea  eax, [eax + edx*2]
        mov  dword ptr [ebp - 0x34], eax
        mov  esi, eax
        mov  edi, dword ptr [ebp - 0x28]
        mov  ebx, dword ptr [ebp - 0x24]
    c_save:
        push esi
        mov  ecx, dword ptr [ebp - 0x20]
        rep movsw word ptr es:[edi], word ptr [esi]
        pop  esi
        add  esi, dword ptr [ebp - 0x30]
        dec  ebx
        jne  c_save
        push dword ptr [ebp + 8]
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [ebp - 8]
        mov  ecx, dword ptr [ebp - 0xc]
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + {IMG_SHOW:#x}]
        mov  esi, dword ptr [ebp - 0x28]
        mov  edi, dword ptr [ebp - 0x34]
        mov  eax, dword ptr [ebp - 0x24]
        mov  dword ptr [ebp - 0x4c], eax
    c_row:
        push edi
        mov  eax, dword ptr [ebp - 0x20]
        mov  dword ptr [ebp - 0x50], eax
    c_px:
        movzx eax, word ptr [edi]
        movzx edx, word ptr [esi]
        cmp  eax, edx
        je   c_next
        mov  ebx, dword ptr [ebp - 0x60]
        test ebx, ebx
        je   c_blend
        mov  dword ptr [ebp - 0x58], edx
        mov  ecx, dword ptr [ebp - 0x38]
        mov  edx, eax
        shr  edx, cl
        and  edx, 31
        imul ecx, edx, 154
        mov  edx, eax
        shr  edx, 5
        and  edx, dword ptr [ebp - 0x3c]
        imul edx, dword ptr [ebp - 0x64]
        add  ecx, edx
        and  eax, 31
        imul eax, eax, 58
        add  ecx, eax
        shr  ecx, 8
        cmp  ecx, 63
        jbe  c_lum
        mov  ecx, 63
    c_lum:
        movzx eax, word ptr [ebx + ecx*2]
        mov  edx, dword ptr [ebp - 0x58]
    c_blend:
        mov  dword ptr [ebp - 0x54], eax
        mov  dword ptr [ebp - 0x58], edx
        mov  ecx, dword ptr [ebp - 0x38]
        shr  eax, cl
        and  eax, 31
        shr  edx, cl
        and  edx, 31
        mov  ebx, dword ptr [ebp - 0x40]
        call c_mix
        shl  eax, cl
        mov  dword ptr [ebp - 0x5c], eax
        mov  eax, dword ptr [ebp - 0x54]
        shr  eax, 5
        and  eax, dword ptr [ebp - 0x3c]
        mov  edx, dword ptr [ebp - 0x58]
        shr  edx, 5
        and  edx, dword ptr [ebp - 0x3c]
        mov  ebx, dword ptr [ebp - 0x44]
        call c_mix
        shl  eax, 5
        or   dword ptr [ebp - 0x5c], eax
        mov  eax, dword ptr [ebp - 0x54]
        and  eax, 31
        mov  edx, dword ptr [ebp - 0x58]
        and  edx, 31
        mov  ebx, dword ptr [ebp - 0x48]
        call c_mix
        or   eax, dword ptr [ebp - 0x5c]
        mov  word ptr [edi], ax
    c_next:
        add  esi, 2
        add  edi, 2
        dec  dword ptr [ebp - 0x50]
        jne  c_px
        pop  edi
        add  edi, dword ptr [ebp - 0x30]
        dec  dword ptr [ebp - 0x4c]
        jne  c_row
        jmp  c_out
    c_plain:
        push dword ptr [ebp + 8]
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [ebp - 8]
        mov  ecx, dword ptr [ebp - 0xc]
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + {IMG_SHOW:#x}]
    c_out:
        mov  esp, dword ptr [ebp - 0x2c]
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret  0x10
    c_mix:
        sub  ebx, eax
        imul ebx, dword ptr [ebp + 0x10]
        add  ebx, 0x80
        sar  ebx, 8
        add  eax, ebx
        sub  eax, edx
        imul eax, dword ptr [ebp + 0xc]
        add  eax, 0x80
        sar  eax, 8
        add  eax, edx
        ret
    c_radd:
        push ebx
        mov  ebx, eax
        lea  edx, [ebp - 0x80]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {IMG_VISDIM:#x}]
        call c_uadd
        xor  eax, eax
        mov  dword ptr [ebp - 0x80], eax
        mov  dword ptr [ebp - 0x7c], eax
        mov  eax, dword ptr [ebx + 0x20]
        mov  dword ptr [ebp - 0x78], eax
        mov  eax, dword ptr [ebx + 0x24]
        mov  dword ptr [ebp - 0x74], eax
        call c_uadd
        mov  eax, dword ptr [ebx + 0x28]
        add  dword ptr [ebp - 0x80], eax
        add  dword ptr [ebp - 0x78], eax
        mov  eax, dword ptr [ebx + 0x2c]
        add  dword ptr [ebp - 0x7c], eax
        add  dword ptr [ebp - 0x74], eax
        call c_uadd
        pop  ebx
        ret
    c_uadd:
        mov  eax, dword ptr [ebp - 0x80]
        cmp  eax, dword ptr [ebp - 0x78]
        jge  u_out
        mov  edx, dword ptr [ebp - 0x7c]
        cmp  edx, dword ptr [ebp - 0x74]
        jge  u_out
        cmp  eax, dword ptr [ebp - 0x10]
        jge  u_1
        mov  dword ptr [ebp - 0x10], eax
    u_1:
        cmp  edx, dword ptr [ebp - 0x14]
        jge  u_2
        mov  dword ptr [ebp - 0x14], edx
    u_2:
        mov  eax, dword ptr [ebp - 0x78]
        cmp  eax, dword ptr [ebp - 0x18]
        jle  u_3
        mov  dword ptr [ebp - 0x18], eax
    u_3:
        mov  eax, dword ptr [ebp - 0x74]
        cmp  eax, dword ptr [ebp - 0x1c]
        jle  u_out
        mov  dword ptr [ebp - 0x1c], eax
    u_out:
        ret
    """
    return pic(src, va, "edi", {"GETIAT": iat_get})


def params_src(core_va):
    """The shared tail of both entries: frame counter in EAX, [ebp-0x10] Mistform, [ebp-0x20]
    Invisibility, [ebp-0x1C] the hotspot (phase), EDI the anchor; draws through vfx_core or plainly.
    Frame: [ebp] EDI, +4 ESI, +8 EBX, +0xC EBP, +0x10 return, +0x14 surface; locals -4 image,
    -8 x, -0xC y, -0x14 opacity, -0x18 tint."""
    return f"""
        mov  dword ptr [ebp - 0x14], 0x100
        mov  dword ptr [ebp - 0x18], 0
        cmp  dword ptr [ebp - 0x10], 0
        je   p_inv
        mov  dword ptr [ebp - 0x14], {MIST_A}
        mov  dword ptr [ebp - 0x18], {MIST_T}
    p_inv:
        cmp  dword ptr [ebp - 0x20], 0
        je   p_done
        mov  ecx, dword ptr [ebp - 0x1c]
        shr  ecx, 4
        imul ecx, ecx, -0x61c8864f
        shr  ecx, 16
        add  eax, ecx
        xor  edx, edx
        mov  ecx, {PERIOD}
        div  ecx
        cmp  edx, {DIP}
        jae  p_done
        movzx eax, word ptr [edi + edx*2 + {{PULSE}}]
        imul eax, dword ptr [ebp - 0x14]
        shr  eax, 8
        mov  dword ptr [ebp - 0x14], eax
    p_done:
        cmp  dword ptr [ebp - 0x14], 0x100
        jne  p_fx
        cmp  dword ptr [ebp - 0x18], 0
        je   v_plain
    p_fx:
        push 0
        push dword ptr [ebp - 0x18]
        push dword ptr [ebp - 0x14]
        push dword ptr [ebp + 0x14]
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [ebp - 8]
        mov  ecx, dword ptr [ebp - 0xc]
        call {core_va:#x}
        jmp  v_out
    v_plain:
        push dword ptr [ebp + 0x14]
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [ebp - 8]
        mov  ecx, dword ptr [ebp - 0xc]
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + {IMG_SHOW:#x}]
    v_out:
        mov  esp, ebp
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret  4
    """


def pulse_tail():
    t = b"".join(struct.pack("<H", v) for v in PULSE)
    return t + b"\0" * (-len(t) % 4)


def build_map(va, core_va):
    """vfx_map: called in place of TArmyHS.Show's `call [ebx+0x84]`; ESI = the TArmyHS."""
    src = f"""
        push ebp
        push ebx
        push esi
        push edi
        mov  ebp, esp
        sub  esp, 0x20
        mov  dword ptr [ebp - 4], eax
        mov  dword ptr [ebp - 8], edx
        mov  dword ptr [ebp - 0xc], ecx
        mov  dword ptr [ebp - 0x1c], esi
        {{ANC}}
        mov  eax, dword ptr [esi + 0x1c]
        test eax, eax
        je   v_plain
        movzx edx, byte ptr [esi + 0x20]
        call {E_GETUNIT:#x}
        test eax, eax
        je   v_plain
        mov  ebx, eax
        mov  edx, {MISTFORM:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ABENABLED_UNIT:#x}]
        movzx eax, al
        mov  dword ptr [ebp - 0x10], eax
        mov  eax, ebx
        mov  edx, {INVIS:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ABENABLED_UNIT:#x}]
        movzx eax, al
        mov  dword ptr [ebp - 0x20], eax
        mov  eax, dword ptr [edi + {{MAP}}]
        test eax, eax
        je   v_clock
        mov  eax, dword ptr [eax + 0x40]
    v_clock:
    """ + params_src(core_va)
    return pic(src, va, "edi", {"MAP": E_HSMAP, "PULSE": ("TAIL", 0)}, pulse_tail())


def build_tc(va, core_va):
    """vfx_tc: jumped to from build_mirrorimage.py's dispatch in place of a body draw's
    `call [ebx+0x84]`; EBP is still TTacticalCombatUnitHS.Show's frame, [ebp-4] = the hotspot."""
    src = f"""
        push ebp
        push ebx
        push esi
        push edi
        mov  esi, dword ptr [ebp - 4]
        mov  ebp, esp
        sub  esp, 0x20
        mov  dword ptr [ebp - 4], eax
        mov  dword ptr [ebp - 8], edx
        mov  dword ptr [ebp - 0xc], ecx
        mov  dword ptr [ebp - 0x1c], esi
        {{ANC}}
        mov  ebx, dword ptr [esi + 0x1c]
        test ebx, ebx
        je   v_plain
        mov  eax, ebx
        mov  edx, {MISTFORM:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ABENABLED_CU:#x}]
        movzx eax, al
        mov  dword ptr [ebp - 0x10], eax
        mov  eax, ebx
        mov  edx, {INVIS:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ABENABLED_CU:#x}]
        movzx eax, al
        mov  dword ptr [ebp - 0x20], eax
        mov  eax, dword ptr [edi + {{MAP}}]
        test eax, eax
        je   v_clock
        mov  eax, dword ptr [eax + 0x40]
    v_clock:
    """ + params_src(core_va)
    return pic(src, va, "edi", {"MAP": T_CMAP, "PULSE": ("TAIL", 0)}, pulse_tail())


def align(va):
    return (va + 0xF) & ~0xF


def e_layout():
    va = E_SLOT[0]
    probe = build_map(va, va)
    core_va = align(va + len(probe))
    core = build_core(core_va, E_IAT_GET)
    caves = [("vfx_map", va, build_map(va, core_va)), ("vfx_core", core_va, core)]
    return {"map": va, "core": core_va}, caves


def t_layout():
    """Both pinned: build_mirrorimage.py jumps to vfx_tc and calls vfx_core."""
    tc = build_tc(T_ENTRY, T_CORE)
    assert T_ENTRY + len(tc) <= T_CORE, "vfx_tc (with its pulse table) overruns vfx_core"
    caves = [("vfx_tc", T_ENTRY, tc), ("vfx_core", T_CORE, build_core(T_CORE, T_IAT_GET))]
    return {"tc": T_ENTRY, "tccore": T_CORE}, caves


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def checks():
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    from aowsyms import get_symbols
    module(EPACK, 0x55700000)
    d = open(EPACK, "rb").read()
    van = open(ROOT_EPACK, "rb").read()
    rd = lambda va: struct.unpack_from("<I", d, P.va2off(d, va))[0]
    lo, hi = ARMYHS_SHOW
    a, b = bytearray(d[P.va2off(d, lo):P.va2off(d, hi)]), bytearray(van[P.va2off(van, lo):P.va2off(van, hi)])
    for s in E_SITES:
        a[s - lo:s - lo + 6] = b[s - lo:s - lo + 6]
    if a != b:
        sys.exit("ABORT: TArmyHS.Show differs from the vanilla root copy outside the three sites")
    for s in E_SITES:
        if van[P.va2off(van, s):P.va2off(van, s) + 6] != E_VANILLA:
            sys.exit("ABORT: %08X is not `call [ebx+0x84]` in vanilla" % s)
    if d[P.va2off(d, 0x557914E7):P.va2off(d, 0x557914E7) + 2] != bytes.fromhex("8bf0"):
        sys.exit("ABORT: TArmyHS.Show does not keep the hotspot in ESI")
    _p, _b, ex, iat = get_symbols("AoWEPACK.dpl")
    for va, want in ((E_GETUNIT, "AoWE.TUnitList.GetUnit"), (E_HSMAP, "AoWE.AoWHSMap"),
                     (ARMYHS_SHOW[0], "AoWE.TArmyHS.Show")):
        if ex.get(va) != want:
            sys.exit("ABORT: %08X is not %s" % (va, want))
    if not iat.get(E_IAT_GET, "").endswith("ImageLib.TCustomImageLibrary.Get"):
        sys.exit("ABORT: AoWEPACK %08X is not the ILPACK Get import" % E_IAT_GET)
    for vmt, cls in ((0x55710740, "TAbstractUnit"), (0x55710CAC, "TUnit"), (0x55711FEC, "THero")):
        name = ex.get(rd(vmt + V_ABENABLED_UNIT), "")
        if not name.endswith(".GetAbilityEnabled"):
            sys.exit("ABORT: %s VMT +%#x is not GetAbilityEnabled" % (cls, V_ABENABLED_UNIT))
    if ex.get(rd(0x55715A94 + V_ABENABLED_CU)) != "AoWE.TCombatUnit.GetAbilityEnabled":
        sys.exit("ABORT: TCombatUnit VMT +%#x is not GetAbilityEnabled" % V_ABENABLED_CU)
    module(TCPCK, 0x00400000)
    t = open(TCPCK, "rb").read()
    _p, _b, ext, iatt = get_symbols("AoWTCPCK.dpl")
    if not iatt.get(T_IAT_GET, "").endswith("ImageLib.TCustomImageLibrary.Get"):
        sys.exit("ABORT: AoWTCPCK %08X is not the ILPACK Get import" % T_IAT_GET)
    o = P.va2off(t, 0x004220BD)
    if ext.get(T_CMAP) != "AoWTC.AoWCombatMap" or t[o:o + 5] != b"\xa1" + struct.pack("<I", T_CMAP):
        sys.exit("ABORT: %08X is not AoWTC.AoWCombatMap, read by TTacticalCombatUnitHS.Show" % T_CMAP)
    if t[P.va2off(t, T_MAGIC_VA):P.va2off(t, T_MAGIC_VA) + 16] not in (bytes(16), T_HEAD):
        sys.exit("ABORT: the header bytes at %08X are someone else's" % T_MAGIC_VA)
    _p, _b, exi, _i = get_symbols("Ilpack.dpl")
    il = open(os.path.join(P.GAME, "Ilpack.dpl"), "rb").read()
    P.IMAGE_BASE = 0x55200000
    ri = lambda va: struct.unpack_from("<I", il, P.va2off(il, va))[0]
    if exi.get(GET_PREF) != "ImageLib.TCustomImageLibrary.Get" or exi.get(VMT_NODE) != "ImageLib..TImageNode":
        sys.exit("ABORT: ILPACK's Get or TImageNode moved")
    base_vmt = 0x5520A514
    if exi.get(ri(base_vmt + IMG_SHOW)) != "ImageLib.TLibraryImage.Show" or \
            exi.get(ri(base_vmt + IMG_VISDIM)) != "ImageLib.TLibraryImage.GetVisualDimensions":
        sys.exit("ABORT: TLibraryImage's Show / GetVisualDimensions slots moved")
    if il[P.va2off(il, 0x5520D669):P.va2off(il, 0x5520D669) + 3] != bytes.fromhex("8b5848") or \
            il[P.va2off(il, 0x5520D67B):P.va2off(il, 0x5520D67B) + 3] != bytes.fromhex("8b4040"):
        sys.exit("ABORT: TImageNode.Show no longer walks [+0x40] x [+0x48]")
    import build_mirrorimage as MI
    if (MI.VFX_MAGIC_VA, MI.VFX_MAGIC, MI.VFX_ENTRY, MI.VFX_CORE) != (T_MAGIC_VA, T_MAGIC, T_ENTRY, T_CORE):
        sys.exit("ABORT: build_mirrorimage.py's VFX constants disagree with this script")
    module(EPACK, 0x55700000)


E_AT, E_CAVES = e_layout()
T_AT, T_CAVES = t_layout()
call6 = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5)) + b"\x90"
E_HOOKS = [(s, E_VANILLA, call6(s, E_AT["map"])) for s in E_SITES]
E_INTERIOR = [(s, s + 6, ARMYHS_SHOW[0], ARMYHS_SHOW[1]) for s in E_SITES]
T_HEAD = struct.pack("<I", T_MAGIC) + bytes(12)
T_HOOKS = [(T_MAGIC_VA, bytes(16), T_HEAD)]
# entry points, asserted
ENTRY = {"map": 0x558CA000, "tc": 0x0044C010, "tccore": 0x0044C800}
assert E_AT["map"] == ENTRY["map"] and T_AT["tc"] == ENTRY["tc"] and T_AT["tccore"] == ENTRY["tccore"], \
    "an entry moved"


def go(argv):
    module(EPACK, 0x55700000)
    run("build_unit_vfx [AoWEPACK]", E_HOOKS, E_CAVES, E_SLOT, E_INTERIOR, argv)
    module(TCPCK, 0x00400000)
    run("build_unit_vfx [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, [], argv)
    module(EPACK, 0x55700000)


if __name__ == "__main__":
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in {**E_AT, **T_AT}.items()))
    print("  pulse: every %d frames, a %d-frame dip to %d/256; mist: opacity %d/256, tint %d/256 "
          "towards %s" % (PERIOD, DIP, min(PULSE), MIST_A, MIST_T, MIST_COLOUR))
    checks()
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])
        print("\n" + "=" * 60)
    go(argv)
