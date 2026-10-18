#!/usr/bin/env python
r"""
build_window_zoom.py -- a zoom factor for the game's Window mode: the window stays freely
resizable, the game fills it, and every game pixel is drawn ZxZ.  Dcpack.dpl + AoWz.exe.

Owner's request 2026-10-18: "the window is normally freely resizeable, hence only the zoom factor
is meaningful as a definition"; default 2x.  Before this the only magnification was Windows'
DPI virtualisation of the DPI-unaware game (150 % on the owner's 4K screen), which cannot be set
per program, and cnc-ddraw (build_ddraw_preload.py) switches it off.

SETTING  HKCU\Software\Triumph Studios\Age of Wonders Z\Video, DWORD "Window Zoom" (AoWzSetup.exe):
    absent or 255 = Auto: the zoom that brings the game area closest to 1920x1080 on the primary
    screen, min(round(W/1920), round(H/1080)), at least 1 -- 2 on 3840x2160, 1 on 2560x1440 and
    1920x1080, 3 on 5120x2880 (owner, 2026-10-18: "target 1920x1080-like").  W, H are physical
    pixels (GetSystemMetrics after SetProcessDPIAware).  0 = off: nothing is touched, Windows' DPI
    stretch applies as before.  1..4 = DPI-aware at that whole-number zoom.  Other values read as 4.
    Fullscreen modes are never zoomed.

VANILLA (Dcpack.dpl, DisplayC; byte-identical to the root copy)
    Window mode uses TWindowsDC (GDI).  TCustomDisplay.Resize 0x55105014 sets the DC's output rect
    [dc+0x30] = {0,0,clientW,clientH} and calls ResizeBackSurfaces (vmt+0x9C, 0x55104EF4) with the
    client size; the back surfaces are GFXE.TDIB32Surface.  Presenting is a stretch already:
    FlipSurface/BltSurface -> TDIB32Surface.BltDC (vmt+0x24, StretchDIBits of the whole back
    surface into [dc+0x30]); BltInvalidatedSurface 0x55103994 -> TSurface.BltStretch (vmt+0x28)
    per dirty region with a source rect and a destination rect at [esp+0x58].  Input: the
    window's WM_MOUSE* messages through TCustomDisplay.WndProc 0x551051DC (VCL OnMouse* events),
    and TDisplayCtrl.GetMousePos 0x55103FC0 (vmt+0x98), which HSEPack polls through
    TCustomDisplay.GetMousePos.  No game module calls GetCursorPos/ScreenToClient itself.
    A DC is the windowed one iff its vmt+0x80 is TWindowsDC.FlipSurface 0x55105E84 (inherited by
    TWindows08/16/24/32DC; the DirectDraw DCs override it).

THE PATCH (Z from Dcpack BSS slack 0x55110800, written by AoWz.exe; 0 in any other host, so the
editors are untouched)
    zoomw        helper: eax = DC -> Z if the DC is windowed and Z > 1, else 0.
    zfit         helper: eax = DC, edx/ecx = client w/h -> w, h := max(1, floor(x / Z)) and that DC's
                 output rect right/bottom := w*Z, h*Z, so the stretch is exactly Z.
    0x551050A9   TCustomDisplay.Resize, its `call [esi+0x9C]` ResizeBackSurfaces (6 B): zfit with
                 the current DC [display+0x1A8].
    0x55105DBC   TWindowsDC.Activate, its `call [ebx+0x9C]` (6 B): zfit with the DC being activated
                 (esi).  It runs BEFORE ActivateDC stores the new DC in [display+0x1A8]
                 (0x551056E3), so v1, which hooked ResizeBackSurfaces' entry and read
                 [display+0x1A8], left a window-mode start unzoomed: picture 1:1 in the top-left
                 quarter, mouse outside it read as off-screen, fixed only by a manual resize
                 (owner, 2026-10-18).  The other ResizeBackSurfaces callers pass explicit sizes
                 (SetBackSurfaceWidth/Height, fullscreen SwitchResolution) and are untouched.
    0x55103C81   BltInvalidatedSurface, before the BltStretch call (5 B): destination rect *= Z and
                 the region goes out through the back surface's BltDC (vmt+0x24, StretchDIBits) to
                 the window DC [dc+0x4C], as FlipSurface does; result into [esp+8], resume 0x55103CAD.
                 TSurface.BltStretch itself refuses unequal sizes (0x80000002, nothing drawn).
    0x55104107   GetMousePos exit (8 B): outside the output rect -> -1/-1, else x/Z, y/Z.
    0x551051DC   WndProc entry (5 B): WM_MOUSEFIRST..0x20D except WM_MOUSEWHEEL (screen
                 coordinates): lParam's signed x, y /= Z.
    Caves in CODE's file slack 0x5510E46C.., CODE VirtualSize 0xD46C -> 0xD600 so the loader maps
    them (still inside the section's page).  All PIC (call/pop).
    AoWz.exe 0x459962 (7 B, right after the entry prologue, before InitExe; build_ddraw_preload.py
    owns the entry itself and resumes here): read the setting with advapi32!RegGetValueA, call
    user32!SetProcessDPIAware, store Z into Dcpack's variable.  Both functions are found by
    walking the export tables of the already-loaded DLLs (the exe imports neither).

Rolls: none.  Local display state only.
UNPROVEN: the Windows cursor and VCL dialogs (message boxes, file dialogs) are no longer stretched
by Windows once the process is DPI-aware, so they show at 1:1 physical size.

WHERE  Dcpack.dpl CODE slack 0x5510E46C-0x5510E5FF (exclusive) + BSS 0x55110800 (4 B).
       AoWz.exe .hcol 0x0062B300-0x0062B5FF (exclusive).
USAGE  python build_window_zoom.py [--dis] | --apply | --undo   (surgical; kills running AoW)
"""
import os, sys, struct
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, kill_aow, show, jmp_to
import exe_patch as X

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
DLL = os.path.join(GAME, "Dcpack.dpl")
P.TARGET, P.IMAGE_BASE = DLL, 0x55100000

# ---- Dcpack.dpl ----
ZONE = (0x5510E46C, 0x5510E600)
VSIZE_VAN, VSIZE_NEW = 0xD46C, 0xD600
ZVAR, FLIP_WIN, SLOT_FLIP = 0x55110800, 0x55105E84, 0x80
H_BLT, VAN_BLT, BLT_RET, BLT_DONE = 0x55103C81, bytes.fromhex("8d44245850"), 0x55103C86, 0x55103CAD
H_RSZ, VAN_RSZ, RSZ_RET = 0x551050A9, bytes.fromhex("ff969c000000"), 0x551050AF   # Resize
H_ACT, VAN_ACT, ACT_RET = 0x55105DBC, bytes.fromhex("ff939c000000"), 0x55105DC2   # TWindowsDC.Activate
H_GMP, VAN_GMP = 0x55104107, bytes.fromhex("83c4285d5f5e5bc3")
H_WND, VAN_WND, WND_RET = 0x551051DC, bytes.fromhex("558bec5153"), 0x551051E1
FUNCS = {H_BLT: (0x55103994, 0x55103D2B), H_RSZ: (0x55105014, 0x551050E6),
         H_ACT: (0x55105D30, 0x55105DFA), H_GMP: (0x55103FC0, 0x55104110),
         H_WND: (0x551051DC, 0x551052DC)}


def build_dll():
    caves, va = [], ZONE[0]

    def put(name, src):
        nonlocal va
        b = asm(src(va), va)
        caves.append((name, va, b))
        at = va
        va += len(b)
        return at

    zoomw = put("zoomw", lambda v: f"""
        call z1
    z1: pop ecx
        test eax, eax
        je zno
        mov edx, dword ptr [eax]
        mov edx, dword ptr [edx + {SLOT_FLIP:#x}]
        lea eax, [ecx + {FLIP_WIN - (v + 5):#x}]
        cmp edx, eax
        jne zno
        mov eax, dword ptr [ecx + {ZVAR - (v + 5):#x}]
        cmp eax, 1
        jle zno
        ret
    zno:
        xor eax, eax
        ret""")
    zfit = put("zfit", lambda v: f"""
        push ebx
        push esi
        push edi
        mov ebx, eax
        mov esi, edx
        mov edi, ecx
        call {zoomw:#x}
        test eax, eax
        je f_out
        mov ecx, eax
        mov eax, esi
        xor edx, edx
        div ecx
        test eax, eax
        jne f1
        inc eax
    f1: mov esi, eax
        mov eax, edi
        xor edx, edx
        div ecx
        test eax, eax
        jne f2
        inc eax
    f2: mov edi, eax
        mov eax, esi
        imul eax, ecx
        mov dword ptr [ebx + 0x38], eax
        mov eax, edi
        imul eax, ecx
        mov dword ptr [ebx + 0x3c], eax
    f_out:
        mov edx, esi
        mov ecx, edi
        pop edi
        pop esi
        pop ebx
        ret""")
    rsz = put("cave_resize", lambda v: f"""
        push eax
        mov eax, dword ptr [ebx + 0x1a8]
        call {zfit:#x}
        pop eax
        call dword ptr [esi + 0x9c]
        jmp {RSZ_RET:#x}""")
    act = put("cave_activate", lambda v: f"""
        push eax
        mov eax, esi
        call {zfit:#x}
        pop eax
        call dword ptr [ebx + 0x9c]
        jmp {ACT_RET:#x}""")
    blt = put("cave_blt", lambda v: f"""
        mov eax, dword ptr [esp]
        call {zoomw:#x}
        test eax, eax
        je b_van
        xor ecx, ecx
    b_mul:
        mov edx, dword ptr [esp + ecx*4 + 0x58]
        imul edx, eax
        mov dword ptr [esp + ecx*4 + 0x58], edx
        inc ecx
        cmp ecx, 4
        jb b_mul
        push esi
        push edi
        mov edi, dword ptr [esp + 8]
        mov edx, dword ptr [esp + 0xc]
        mov eax, edi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x40]
        mov esi, eax
        lea eax, [esp + 0x60]
        push eax
        lea ecx, [esp + 0x54]
        mov edx, dword ptr [edi + 0x4c]
        mov eax, esi
        mov edi, dword ptr [eax]
        call dword ptr [edi + 0x24]
        pop edi
        pop esi
        mov dword ptr [esp + 8], eax
        jmp {BLT_DONE:#x}
    b_van:
        lea eax, [esp + 0x58]
        push eax
        jmp {BLT_RET:#x}""")
    gmp = put("cave_gmp", lambda v: f"""
        mov eax, ebx
        call {zoomw:#x}
        test eax, eax
        je g_out
        mov ecx, eax
        mov eax, dword ptr [edi]
        cmp eax, -1
        je g_out
        cmp eax, dword ptr [ebx + 0x38]
        jge g_off
        mov eax, dword ptr [ebp]
        cmp eax, dword ptr [ebx + 0x3c]
        jge g_off
        mov eax, dword ptr [edi]
        cdq
        idiv ecx
        mov dword ptr [edi], eax
        mov eax, dword ptr [ebp]
        cdq
        idiv ecx
        mov dword ptr [ebp], eax
        jmp g_out
    g_off:
        mov dword ptr [edi], -1
        mov dword ptr [ebp], -1
    g_out:
        add esp, 0x28
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret""")
    wnd = put("cave_wnd", lambda v: f"""
        push eax
        push edx
        push ebx
        push esi
        mov esi, edx
        mov ecx, dword ptr [esi]
        cmp ecx, 0x200
        jb w_out
        cmp ecx, 0x20d
        ja w_out
        cmp ecx, 0x20a
        je w_out
        mov eax, dword ptr [eax + 0x1a8]
        call {zoomw:#x}
        test eax, eax
        je w_out
        mov ebx, eax
        movsx eax, word ptr [esi + 8]
        cdq
        idiv ebx
        mov word ptr [esi + 8], ax
        movsx eax, word ptr [esi + 10]
        cdq
        idiv ebx
        mov word ptr [esi + 10], ax
    w_out:
        pop esi
        pop ebx
        pop edx
        pop eax
        push ebp
        mov ebp, esp
        push ecx
        push ebx
        jmp {WND_RET:#x}""")
    assert va <= ZONE[1], "Dcpack caves overflow the slack (%08X)" % va
    hooks = [(H_RSZ, VAN_RSZ, jmp_to(H_RSZ, rsz, len(VAN_RSZ))),
             (H_ACT, VAN_ACT, jmp_to(H_ACT, act, len(VAN_ACT))),
             (H_BLT, VAN_BLT, jmp_to(H_BLT, blt, len(VAN_BLT))),
             (H_GMP, VAN_GMP, jmp_to(H_GMP, gmp, len(VAN_GMP))),
             (H_WND, VAN_WND, jmp_to(H_WND, wnd, len(VAN_WND)))]
    return caves, hooks


# ---- AoWz.exe ----
EXE_SLOT = (0x0062B300, 0x0062B600)
E_SITE, E_VAN, E_RET = 0x00459962, bytes.fromhex("535633c08945f0"), 0x00459969
IAT_GMH = 0x0045D39C
AUTO = 0xFF                       # "Window Zoom" absent or 255: pick the zoom from the primary screen
TARGET_W, TARGET_H = 1920, 1080   # Auto aims the game area at about this size (owner, 2026-10-18)
DCPACK_ZVAR_RVA = ZVAR - 0x55100000
STRINGS = [("s_advapi", b"advapi32.dll\0"), ("s_regget", b"RegGetValueA\0"),
           ("s_user32", b"user32.dll\0"), ("s_dpi", b"SetProcessDPIAware\0"),
           ("s_gsm", b"GetSystemMetrics\0"),
           ("s_dcpack", b"Dcpack.dpl\0"), ("s_value", b"Window Zoom\0"),
           ("s_key", rb"Software\Triumph Studios\Age of Wonders Z\Video" + b"\0")]


def build_exe():
    data, addr, va = bytearray(), {}, EXE_SLOT[0]
    for name, s in STRINGS:
        addr[name] = va + len(data)
        data += s
    while len(data) % 4:
        data.append(0)
    addr["zoom"] = va + len(data)
    data += struct.pack("<I", 2)
    addr["size"] = va + len(data)
    data += struct.pack("<I", 4)
    cave = (va + len(data) + 15) & ~15
    a = addr
    src = f"""
        pushad
        mov dword ptr [{a['zoom']:#x}], {AUTO:#x}
        mov dword ptr [{a['size']:#x}], 4
        push {a['s_advapi']:#x}
        call dword ptr [{IAT_GMH:#x}]
        test eax, eax
        je e_have
        mov ebx, eax
        mov esi, {a['s_regget']:#x}
        mov ecx, 13
        call find_export
        test eax, eax
        je e_have
        push {a['size']:#x}
        push {a['zoom']:#x}
        push 0
        push 0x10
        push {a['s_value']:#x}
        push {a['s_key']:#x}
        push 0x80000001
        call eax
        test eax, eax
        je e_have
        mov dword ptr [{a['zoom']:#x}], {AUTO:#x}
    e_have:
        cmp dword ptr [{a['zoom']:#x}], 0
        je e_done
        push {a['s_user32']:#x}
        call dword ptr [{IAT_GMH:#x}]
        test eax, eax
        je e_done
        mov ebx, eax
        mov esi, {a['s_dpi']:#x}
        mov ecx, 19
        call find_export
        test eax, eax
        je e_nodpi
        call eax
    e_nodpi:
        cmp dword ptr [{a['zoom']:#x}], {AUTO:#x}
        jne e_clamp
        mov esi, {a['s_gsm']:#x}
        mov ecx, 17
        call find_export
        test eax, eax
        je e_one
        mov edi, eax
        push 0
        call edi
        add eax, {TARGET_W // 2}
        xor edx, edx
        mov ecx, {TARGET_W}
        div ecx
        mov esi, eax
        push 1
        call edi
        add eax, {TARGET_H // 2}
        xor edx, edx
        mov ecx, {TARGET_H}
        div ecx
        cmp eax, esi
        jbe e_min
        mov eax, esi
    e_min:
        test eax, eax
        jne e_store
    e_one:
        mov eax, 1
    e_store:
        mov dword ptr [{a['zoom']:#x}], eax
    e_clamp:
        mov eax, dword ptr [{a['zoom']:#x}]
        cmp eax, 4
        jbe e1
        mov eax, 4
    e1: mov dword ptr [{a['zoom']:#x}], eax
    e_set:
        push {a['s_dcpack']:#x}
        call dword ptr [{IAT_GMH:#x}]
        test eax, eax
        je e_done
        mov ecx, dword ptr [{a['zoom']:#x}]
        mov dword ptr [eax + {DCPACK_ZVAR_RVA:#x}], ecx
    e_done:
        popad
        push ebx
        push esi
        xor eax, eax
        mov dword ptr [ebp - 0x10], eax
        jmp {E_RET:#x}
    find_export:
        push ebp
        mov ebp, ecx
        mov eax, dword ptr [ebx + 0x3c]
        mov eax, dword ptr [ebx + eax + 0x78]
        test eax, eax
        je f_none
        lea edx, [ebx + eax]
        mov ecx, dword ptr [edx + 0x18]
    f_loop:
        dec ecx
        js f_none
        mov eax, dword ptr [edx + 0x20]
        add eax, ebx
        mov edi, dword ptr [eax + ecx*4]
        add edi, ebx
        push ecx
        push esi
        mov ecx, ebp
        repe cmpsb
        pop esi
        pop ecx
        jne f_loop
        mov eax, dword ptr [edx + 0x24]
        add eax, ebx
        movzx eax, word ptr [eax + ecx*2]
        mov edx, dword ptr [edx + 0x1c]
        add edx, ebx
        mov eax, dword ptr [edx + eax*4]
        add eax, ebx
        pop ebp
        ret
    f_none:
        xor eax, eax
        pop ebp
        ret
    """
    code = asm(src, cave)
    caves = [("data", va, bytes(data)), ("cave_zoominit", cave, code)]
    assert cave + len(code) <= EXE_SLOT[1], "exe cave overflows its slot"
    return caves, [(E_SITE, E_VAN, jmp_to(E_SITE, cave, len(E_VAN)))]


# ---- Dcpack verify / write ----
def code_hdr(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    hdr = e + 24 + opt                       # first section = CODE
    assert d[hdr:hdr + 4] == b"CODE", "first section is not CODE"
    return hdr


def dll_state(d, caves, hooks):
    states = []
    for va, van, new in hooks:
        o = P.va2off(d, va)
        cur = bytes(d[o:o + len(van)])
        states.append("vanilla" if cur == van else "installed" if cur == new else "FOREIGN " + cur.hex())
    zo = P.va2off(d, ZONE[0])
    zone = bytes(d[zo:zo + ZONE[1] - ZONE[0]])
    img = bytearray(ZONE[1] - ZONE[0])
    for _n, va, b in caves:
        img[va - ZONE[0]:va - ZONE[0] + len(b)] = b
    vs = struct.unpack_from("<I", d, code_hdr(d) + 8)[0]
    if all(s == "vanilla" for s in states) and not any(zone) and vs == VSIZE_VAN:
        st = "VANILLA"
    elif all(s == "installed" for s in states) and zone == bytes(img) and vs == VSIZE_NEW:
        st = "INSTALLED"
    else:
        st = "MIXED"
    return st, states, bytes(img), vs


def main():
    apply_, undo = "--apply" in sys.argv, "--undo" in sys.argv
    print("build_window_zoom")
    dcaves, dhooks = build_dll()
    dd = bytearray(open(DLL, "rb").read())
    st, states, img, vs = dll_state(dd, dcaves, dhooks)
    print("  Dcpack.dpl      %-9s  %s   CODE VirtualSize %#x" % (st, ", ".join(s.split()[0] for s in states), vs))
    rl = [v for va, van, _ in dhooks for v in P.relocs_in(dd, va, va + len(van))] + P.relocs_in(dd, *ZONE)
    inner = []
    for va, van, _ in dhooks:
        inner += P.rel32_into(dd, va, va + len(van)) + P.short_into(dd, va, va + len(van), *FUNCS[va])
    print("    .reloc under hooks/zone: %s | jumps into a hook interior: %s"
          % (", ".join("%08X" % v for v in rl) or "none", ", ".join("%08X" % v for v in inner) or "none"))
    print("    caves: " + ", ".join("%s %08X (%d B)" % (n, va, len(b)) for n, va, b in dcaves)
          + " | ends %08X (limit %08X)" % (dcaves[-1][1] + len(dcaves[-1][2]), ZONE[1]))
    if st == "MIXED" or rl or inner:
        sys.exit("ABORT: Dcpack.dpl is neither vanilla nor this patch, or a hook conflicts")

    ecaves, ehooks = build_exe()
    if "--dis" in sys.argv:
        show(dcaves)
        show(ecaves[1:])
    argv = ["--apply"] if apply_ else ["--undo"] if undo else []
    if not (apply_ or undo):
        X.run("build_window_zoom (AoWz.exe half)", ehooks, ecaves, EXE_SLOT, argv=argv)
        print("\n(dry run -- nothing written)")
        return
    kill_aow()
    if apply_ and st == "VANILLA":
        with open(DLL, "r+b") as f:
            f.seek(code_hdr(dd) + 8)
            f.write(struct.pack("<I", VSIZE_NEW))
            f.seek(P.va2off(dd, ZONE[0]))
            f.write(img)
            for va, _van, new in dhooks:
                f.seek(P.va2off(dd, va))
                f.write(new)
    elif undo and st == "INSTALLED":
        with open(DLL, "r+b") as f:
            for va, van, _new in dhooks:
                f.seek(P.va2off(dd, va))
                f.write(van)
            f.seek(P.va2off(dd, ZONE[0]))
            f.write(bytes(ZONE[1] - ZONE[0]))
            f.seek(code_hdr(dd) + 8)
            f.write(struct.pack("<I", VSIZE_VAN))
    X.run("build_window_zoom (AoWz.exe half)", ehooks, ecaves, EXE_SLOT, argv=argv)
    back = bytearray(open(DLL, "rb").read())
    want = "INSTALLED" if apply_ else "VANILLA"
    got = dll_state(back, dcaves, dhooks)[0]
    assert got == want, "Dcpack.dpl reads %s after writing" % got
    print("  Dcpack.dpl      %s" % got)


if __name__ == "__main__":
    main()
