#!/usr/bin/env python3
r"""Editor: drop a picture on AoWzEd to rebuild the level being viewed from it.

Owner request 2026-10-07: drag a PNG (a topographic / world map) onto the editor and the
CURRENT map level is regenerated from its colours -- water, grassland, steppe, desert, and
mountains/hills where the picture shows rocky or snowy relief.  Owner rulings: everything
on that level is replaced; the picture keeps its proportions (centred, cropped); the editor
asks before doing it.

Target: `Ziggurat\AoWDevEd.exe` only, then `build_zigeditor.py --apply` derives the live
`AoWzEd.exe` (see build_deved_listarrows.py, "THE EDITOR EXE TRAP").  The converter is
`Zig Modding Tools\zig_pngmap.py`, run through `devedpng.bat` -> `deved_pngbridge.py`.

FLOW (all inside TMainForm's Application.OnMessage filter, 0x004280DC)
  hook 0x004280EB (7 B `cmp eax,0x100 / jl 0x428157`, no .reloc, nothing jumps inside)
  -> cave_msg:
     * once: DragAcceptFiles(MainForm.Handle, TRUE).  AoWDevEd imports nothing from
       shell32 and only GetModuleHandleA from kernel32, so LoadLibraryA / GetProcAddress
       come out of VCL30.dpl's IAT by the rebase-delta idiom: vcl30 = [0x00432224]
       (Forms.Application) - its export RVA.  DragQueryFileA / DragFinish are kept.
     * WM_DROPFILES (0x233): Handled := True, then do_drop; anything else re-enters the
       vanilla key filter exactly as the displaced bytes would.
  do_drop:
     1. DragQueryFileA(hDrop, 0) -> the picture's path; DragFinish.
     2. No map open (THSMEdit+0x1BC = 0) -> "Open a map first."
     3. Yes/No box naming the level (THSMEdit+0x21D) and the file.
     4. <exe dir> via GetModuleFileNameA (never baked in); THSEngine.SaveHSM writes the map
        AS IT STANDS to Scenario\Custom\zPngImport.hsm ([0x004329C0] - 0x25C, the
        generator's idiom).  The original filename (THSMEdit+0x1E4) is copied aside.
     5. WinExec (vclx30 idiom) `cmd.exe /c ""<dir>Zig Modding Tools\devedpng.bat" "<pic>" <n>"`
        -- the outer pair of quotes is what cmd /c strips; without it a quoted .bat path
        and a quoted argument together break.
     6. The bridge shows the crop-and-tune window (zig_pngcrop.py). Wait for
        zPngImport.done to go absent then present, 50 ms Sleeps, up to 30 minutes;
        .cancel (the window's Cancel) returns silently, .fail shows the warning.
     7. THSMEdit.Close (asks to save unsaved changes; Cancel aborts), TMainForm's LoadMap
        on the handoff file, then SetHSMapFilename(original name) so Save writes the
        user's own file (an untitled map stays untitled), SetSceneLevel(n) back to the
        level that was dropped on, and THSMap.SetModified so closing asks to save.
     On .fail or a timeout: a warning box pointing at Zig Modding Tools\deved_png.log.

SPACE
  code  0x0050CA00..0x0050D1FF  `.mtb`, inside the DEAD TMAINFORM DFM master (file 0x108000).
        That copy is unreferenced since build_deved_terrainpal moved the form to `.ctp`;
        the window holds no `\x08MaxValue\x02` (build_editor_spinners.py scans the whole
        file for it) and no `TPF0`.  The original bytes are embedded below, so --undo
        restores them exactly.  R+X, like listarrows' cave in the same section.
  data  0x00430200..0x00430FFF  BSS page slack (loader-zeroed, RW, past VirtualSize 0x1E5).

Dry run by default; --apply / --undo (surgical); re-running verifies.
"""
import argparse
import base64
import hashlib
import os
import struct
import sys
import zlib

sys.dont_write_bytecode = True
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXE = os.path.join(GAME, "AoWDevEd.exe")
IMAGE_BASE = 0x00400000

HOOK = 0x004280EB
HOOK_ORIG = bytes.fromhex("3d000100007c65")
FILTER_LO, FILTER_HI = 0x004280DC, 0x00428180
KEYS_OUT = 0x00428157                  # the filter's "not ours" exit
KEYS_GO = 0x004280F2                   # vanilla continues here after the jl

CAVE = 0x0050CA00
CAVE_END = 0x0050D200
CAVE_FILE = 0x00108000
WIN_SHA = "8ae66ab903381bbb"   # the dead TMAINFORM master bytes this window replaces
WIN_ORIG = zlib.decompress(base64.b64decode(
    "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"
))

# BSS slack
G_INIT, G_DQF, G_DF, G_LVL = 0x00430200, 0x00430204, 0x00430208, 0x0043020C
B_PNG = 0x00430210                     # 264
B_DIR = 0x00430320                     # 264
B_MSG = 0x00430430                     # 600
H_MAP = 0x00430690; B_MAP = H_MAP + 8  # AnsiString literal headers + 300 B text
H_DONE = 0x004307D0; B_DONE = H_DONE + 8
H_FAIL = 0x00430910; B_FAIL = H_FAIL + 8
H_ORIG = 0x00430A50; B_ORIG = H_ORIG + 8
B_CMD = 0x00430B90                     # 700 (the longest command is about 600)
H_CANC = 0x00430E50; B_CANC = H_CANC + 8
DATA_END = 0x00430F84

# AoWDevEd.exe -- verified (build_deved_newmapgen.py and this script's audit)
MAINFORM_GLOBAL = 0x0042F0A8
MAINFORM_HSMEDIT = 0x22C
LOADMAP = 0x004296D4                   # eax=TMainForm, edx=AnsiString
HSMEDIT_CLOSE = 0x00402E58             # eax=THSMEdit -> al=0 cancelled
ENGINE_GLOBAL = 0x00432894
ENGINE_HSM = 0x3C
NEWHSM_SLOT = 0x004329C0
SAVEHSM_DELTA = 0x25C
VCLX_SLOT, VCLX_EXPORT_RVA, VCLX_WINEXEC_RVA = 0x004332E4, 0x00019604, 0x000243F8
SLEEP_SLOT = 0x004322A0
FILEEXISTS = 0x004017D8
GETMODULEFILENAME_SLOT = 0x00432164
MSGBOX_SLOT = 0x00432180               # Forms.TApplication.MessageBox
APP_SLOT = 0x00432224                  # Forms.Application (variable)
GETHANDLE_SLOT = 0x004322E0            # Controls.TWinControl.GetHandle
SETFILENAME_SLOT = 0x004333A0          # THSMEdit.SetHSMapFilename(eax, edx=string)
SETSCENELEVEL_SLOT = 0x00433368        # THSMEdit.SetSceneLevel(eax, dl)
SETMODIFIED_SLOT = 0x004329DC          # THSMap.SetModified(eax)
HSMEDIT_HASMAP, HSMEDIT_FILENAME, HSMEDIT_LEVEL, HSMEDIT_DOC = 0x1BC, 0x1E4, 0x21D, 0x1C0
# VCL30.dpl RVAs (measured from the module's own export / import tables)
VCL_APPLICATION_RVA = 0x000E36E4
VCL_LOADLIBRARY_RVA = 0x000E4360
VCL_GETPROCADDRESS_RVA = 0x000E43B4

LEVELS = ("Surface", "Caverns", "Depths", "Firmament", "Abyss")
CAPTION = "Rebuild level from picture"


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    lit = {}
    lit_order = [
        ("s_shell", b"shell32.dll\0"), ("s_daf", b"DragAcceptFiles\0"),
        ("s_dqf", b"DragQueryFileA\0"), ("s_df", b"DragFinish\0"),
        ("s_bat", b"Zig Modding Tools\\devedpng.bat\0"),
        ("s_map", b"Scenario\\Custom\\zPngImport.hsm\0"),
        ("s_done", b"Scenario\\Custom\\zPngImport.done\0"),
        ("s_fail", b"Scenario\\Custom\\zPngImport.fail\0"),
        ("s_canc", b"Scenario\\Custom\\zPngImport.cancel\0"),
        ("s_cmd1", b'cmd.exe /c ""\0'), ("s_cmd2", b'" "\0'), ("s_cmd3", b'" \0'),
        ("s_cmd4", b'"\0'),
        ("s_cap", CAPTION.encode() + b"\0"),
        ("s_ask1", b"Rebuild the \0"),
        ("s_ask2", b" level from this picture?\r\n\r\n\0"),
        ("s_ask3", b"\r\n\r\nEverything on this level is replaced: terrain, mountains, "
                   b"hills, structures and units. This cannot be undone.\0"),
        ("s_nomap", b"Open a map first, then drop the picture on it.\0"),
        ("s_failed", b"The picture could not be turned into a map level.\r\n\r\n"
                     b"The reason is in Zig Modding Tools\\deved_png.log.\0"),
    ] + [("s_lv%d" % i, n.encode() + b"\0") for i, n in enumerate(LEVELS)]

    def src(L):
        return f"""
    cave_msg:
        cmp  dword ptr [{G_INIT:#x}], 0
        jne  inited
        call init_drop
    inited:
        cmp  eax, 0x233
        je   drop
        cmp  eax, 0x100
        jl   {KEYS_OUT:#x}
        jmp  {KEYS_GO:#x}
    drop:
        mov  eax, [esp]
        mov  byte ptr [eax], 1
        pushad
        call do_drop
        popad
        jmp  {KEYS_OUT:#x}

    init_drop:
        pushad
        mov  dword ptr [{G_INIT:#x}], 1
        mov  eax, esi
        call dword ptr [{GETHANDLE_SLOT:#x}]
        mov  edi, eax
        mov  ebp, [{APP_SLOT:#x}]
        sub  ebp, {VCL_APPLICATION_RVA:#x}
        push {L['s_shell']:#x}
        call dword ptr [ebp + {VCL_LOADLIBRARY_RVA:#x}]
        test eax, eax
        jz   init_out
        mov  ebx, eax
        push {L['s_dqf']:#x}
        push ebx
        call dword ptr [ebp + {VCL_GETPROCADDRESS_RVA:#x}]
        mov  [{G_DQF:#x}], eax
        push {L['s_df']:#x}
        push ebx
        call dword ptr [ebp + {VCL_GETPROCADDRESS_RVA:#x}]
        mov  [{G_DF:#x}], eax
        push {L['s_daf']:#x}
        push ebx
        call dword ptr [ebp + {VCL_GETPROCADDRESS_RVA:#x}]
        test eax, eax
        jz   init_out
        cmp  dword ptr [{G_DQF:#x}], 0
        je   init_out
        cmp  dword ptr [{G_DF:#x}], 0
        je   init_out
        push 1
        push edi
        call eax
    init_out:
        popad
        ret

    do_drop:
        mov  esi, [ebx + 8]
        cmp  dword ptr [{G_DQF:#x}], 0
        je   dd_ret
        push 260
        push {B_PNG:#x}
        push 0
        push esi
        call dword ptr [{G_DQF:#x}]
        mov  edi, eax
        push esi
        call dword ptr [{G_DF:#x}]
        test edi, edi
        jz   dd_ret
        mov  eax, [{MAINFORM_GLOBAL:#x}]
        mov  esi, [eax]
        test esi, esi
        jz   dd_ret
        mov  ebp, [esi + {MAINFORM_HSMEDIT:#x}]
        test ebp, ebp
        jz   dd_ret
        cmp  byte ptr [ebp + {HSMEDIT_HASMAP:#x}], 0
        jne  have_map
        mov  edx, {L['s_nomap']:#x}
        push 0x30
        call msgbox
        jmp  dd_ret
    have_map:
        movzx eax, byte ptr [ebp + {HSMEDIT_LEVEL:#x}]
        cmp  eax, 4
        ja   dd_ret
        mov  [{G_LVL:#x}], eax

        mov  edi, {B_MSG:#x}
        mov  ebx, {L['s_ask1']:#x}
        call copyz
        mov  eax, [{G_LVL:#x}]
        mov  ebx, [eax*4 + {L['t_lv']:#x}]
        call copyz
        mov  ebx, {L['s_ask2']:#x}
        call copyz
        mov  ebx, {B_PNG:#x}
        call copyz
        mov  ebx, {L['s_ask3']:#x}
        call copyz
        mov  byte ptr [edi], 0
        mov  edx, {B_MSG:#x}
        push 0x24
        call msgbox
        cmp  eax, 6
        jne  dd_ret

        push 260
        push {B_DIR:#x}
        push 0
        call dword ptr [{GETMODULEFILENAME_SLOT:#x}]
        test eax, eax
        jz   dd_ret
        lea  edi, [eax + {B_DIR:#x}]
    scan:
        dec  edi
        cmp  edi, {B_DIR:#x}
        jbe  dd_ret
        cmp  byte ptr [edi], 0x5C
        jne  scan
        mov  byte ptr [edi + 1], 0

        mov  eax, {H_MAP:#x}
        mov  ecx, {L['s_map']:#x}
        call mkpath
        mov  eax, {H_DONE:#x}
        mov  ecx, {L['s_done']:#x}
        call mkpath
        mov  eax, {H_FAIL:#x}
        mov  ecx, {L['s_fail']:#x}
        call mkpath
        mov  eax, {H_CANC:#x}
        mov  ecx, {L['s_canc']:#x}
        call mkpath

        mov  dword ptr [{H_ORIG + 4:#x}], 0
        mov  dword ptr [{H_ORIG:#x}], 0xFFFFFFFF
        mov  byte ptr [{B_ORIG:#x}], 0
        mov  ebx, [ebp + {HSMEDIT_FILENAME:#x}]
        test ebx, ebx
        jz   orig_done
        mov  edi, {B_ORIG:#x}
        call copyz
        mov  byte ptr [edi], 0
        sub  edi, {B_ORIG:#x}
        mov  [{H_ORIG + 4:#x}], edi
    orig_done:

        mov  eax, [{ENGINE_GLOBAL:#x}]
        mov  eax, [eax]
        test eax, eax
        jz   dd_ret
        cmp  dword ptr [eax + {ENGINE_HSM:#x}], 0
        je   dd_ret
        push 0
        push 0
        mov  edx, {B_MAP:#x}
        mov  ecx, [{NEWHSM_SLOT:#x}]
        sub  ecx, {SAVEHSM_DELTA:#x}
        call ecx

        mov  edi, {B_CMD:#x}
        mov  ebx, {L['s_cmd1']:#x}
        call copyz
        mov  ebx, {B_DIR:#x}
        call copyz
        mov  ebx, {L['s_bat']:#x}
        call copyz
        mov  ebx, {L['s_cmd2']:#x}
        call copyz
        mov  ebx, {B_PNG:#x}
        call copyz
        mov  ebx, {L['s_cmd3']:#x}
        call copyz
        mov  eax, [{G_LVL:#x}]
        add  al, 0x30
        mov  [edi], al
        inc  edi
        mov  ebx, {L['s_cmd4']:#x}
        call copyz
        mov  byte ptr [edi], 0

        mov  eax, [{VCLX_SLOT:#x}]
        sub  eax, {VCLX_EXPORT_RVA:#x}
        mov  eax, [eax + {VCLX_WINEXEC_RVA:#x}]
        test eax, eax
        jz   dd_ret
        push 7
        push {B_CMD:#x}
        call eax
        cmp  eax, 31
        jbe  dd_fail

        mov  edi, 600
    w_gone:
        call pump
        mov  eax, {B_DONE:#x}
        mov  edx, {FILEEXISTS:#x}
        call edx
        test al, al
        jz   w_made_init
        dec  edi
        jnz  w_gone
        jmp  dd_fail
    w_made_init:
        mov  edi, 36000
    w_made:
        call pump
        mov  eax, {B_CANC:#x}
        mov  edx, {FILEEXISTS:#x}
        call edx
        test al, al
        jnz  dd_ret
        mov  eax, {B_FAIL:#x}
        mov  edx, {FILEEXISTS:#x}
        call edx
        test al, al
        jnz  dd_fail
        mov  eax, {B_DONE:#x}
        mov  edx, {FILEEXISTS:#x}
        call edx
        test al, al
        jnz  got_it
        dec  edi
        jnz  w_made
        jmp  dd_fail

    got_it:
        mov  eax, [{MAINFORM_GLOBAL:#x}]
        mov  esi, [eax]
        mov  eax, [esi + {MAINFORM_HSMEDIT:#x}]
        mov  edx, {HSMEDIT_CLOSE:#x}
        call edx
        test al, al
        jz   dd_ret
        mov  eax, esi
        mov  edx, {B_MAP:#x}
        mov  ecx, {LOADMAP:#x}
        call ecx
        mov  ebp, [esi + {MAINFORM_HSMEDIT:#x}]
        test ebp, ebp
        jz   dd_ret
        cmp  byte ptr [ebp + {HSMEDIT_HASMAP:#x}], 0
        je   dd_ret
        xor  edx, edx
        cmp  dword ptr [{H_ORIG + 4:#x}], 0
        je   set_name
        mov  edx, {B_ORIG:#x}
    set_name:
        mov  eax, ebp
        call dword ptr [{SETFILENAME_SLOT:#x}]
        mov  eax, ebp
        mov  edx, [{G_LVL:#x}]
        call dword ptr [{SETSCENELEVEL_SLOT:#x}]
        mov  eax, [ebp + {HSMEDIT_DOC:#x}]
        test eax, eax
        jz   dd_ret
        mov  eax, [eax + 0x3C]
        test eax, eax
        jz   dd_ret
        call dword ptr [{SETMODIFIED_SLOT:#x}]
    dd_ret:
        ret
    dd_fail:
        mov  edx, {L['s_failed']:#x}
        push 0x30
        call msgbox
        ret

    msgbox:
        mov  eax, [{APP_SLOT:#x}]
        mov  eax, [eax]
        mov  ecx, {L['s_cap']:#x}
        push dword ptr [esp + 4]
        call dword ptr [{MSGBOX_SLOT:#x}]
        ret  4

    mkpath:
        push eax
        lea  edi, [eax + 8]
        mov  ebx, {B_DIR:#x}
        call copyz
        mov  ebx, ecx
        call copyz
        mov  byte ptr [edi], 0
        pop  eax
        lea  edx, [eax + 8]
        sub  edi, edx
        mov  [eax + 4], edi
        mov  dword ptr [eax], 0xFFFFFFFF
        ret

    copyz:
        mov  al, [ebx]
        test al, al
        jz   copyz_end
        mov  [edi], al
        inc  ebx
        inc  edi
        jmp  copyz
    copyz_end:
        ret

    pump:
        push 50
        call dword ptr [{SLEEP_SLOT:#x}]
        ret
    """

    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    # pass 1 with placeholder literal addresses to size the code
    L = {k: CAVE for k, _ in lit_order}
    L['t_lv'] = CAVE
    code, _ = ks.asm(src(L), CAVE)
    lit_at = (CAVE + len(code) + 0x40 + 0xF) & ~0xF
    blob_lits = bytearray()
    for k, b in lit_order:
        L[k] = lit_at + len(blob_lits)
        blob_lits += b
    while len(blob_lits) % 4:
        blob_lits += b"\0"
    L['t_lv'] = lit_at + len(blob_lits)
    blob_lits += b"".join(struct.pack("<I", L["s_lv%d" % i]) for i in range(len(LEVELS)))
    code2, _ = ks.asm(src(L), CAVE)
    code2 = bytes(code2)
    assert len(code2) <= lit_at - CAVE, "code grew between passes"
    blob = code2.ljust(lit_at - CAVE, b"\xCC") + bytes(blob_lits)
    assert CAVE + len(blob) <= CAVE_END, "cave overflows its window (%d B)" % len(blob)
    return blob


def hook_bytes():
    return b"\xE9" + struct.pack("<i", CAVE - (HOOK + 5)) + b"\x90\x90"


def file_off(va):
    # .mtb: VA 0x4E1000 <-> file 0xDC600; CODE: VA 0x401000 <-> file 0x400
    if 0x004E1000 <= va < 0x0052D800:
        return va - 0x004E1000 + 0x000DC600
    if 0x00401000 <= va < 0x0042F000:
        return va - 0x00401000 + 0x400
    raise ValueError(hex(va))


def relocs_in(d, lo, hi):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 136)
    off, end, hits = 0x3D000, 0x3D000 + size, []    # .reloc raw (VA 0x440000)
    assert rva == 0x40000, "unexpected .reloc RVA %#x" % rva
    while off < end:
        page, blk = struct.unpack_from("<II", d, off)
        if blk < 8:
            break
        for k in range((blk - 8) // 2):
            ent = struct.unpack_from("<H", d, off + 8 + 2 * k)[0]
            va = IMAGE_BASE + page + (ent & 0xFFF)
            if ent >> 12 and lo <= va + 3 and va < hi:
                hits.append(va)
        off += blk
    return hits


def interior_jumps(d):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    o = file_off(FILTER_LO)
    bad = []
    for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(d[o:o + FILTER_HI - FILTER_LO], FILTER_LO):
        if HOOK <= ins.address < HOOK + 7:
            continue
        if ins.mnemonic.startswith("j") or ins.mnemonic == "call":
            try:
                t = int(ins.op_str, 16)
            except ValueError:
                continue
            if HOOK < t < HOOK + 7:
                bad.append(ins.address)
    return bad


def main():
    ap = argparse.ArgumentParser(description="Editor: drop a picture to rebuild the level")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()

    assert hashlib.sha256(WIN_ORIG).hexdigest().startswith(WIN_SHA), "embedded window damaged"
    d = bytearray(open(EXE, "rb").read())
    blob = build()
    wlen = CAVE_END - CAVE
    assert len(WIN_ORIG) == wlen
    co = file_off(CAVE)
    assert co == CAVE_FILE
    win = bytes(d[co:co + wlen])
    want_win = blob + WIN_ORIG[len(blob):]
    ho = file_off(HOOK)
    hook = bytes(d[ho:ho + 7])
    hst = "vanilla" if hook == HOOK_ORIG else "installed" if hook == hook_bytes() else "FOREIGN"
    wst = "original" if win == WIN_ORIG else "ours" if win == want_win else (
        "stale ours" if hst == "installed" else "FOREIGN")
    print("build_deved_pngdrop -- %s" % EXE)
    print("  hook %08X: %s   window %08X..%08X: %s   (code+literals %d B of %d)"
          % (HOOK, hst, CAVE, CAVE_END, wst, len(blob), wlen))
    rl = relocs_in(d, HOOK, HOOK + 7) + relocs_in(d, CAVE, CAVE_END)
    ij = interior_jumps(d)
    print("  .reloc under hook/window: %s; jumps into the hook: %s"
          % (rl or "none", ij or "none"))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob, CAVE):
            if ins.mnemonic == "int3":
                break
            print("    %08X  %-24s %s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic,
                                            ins.op_str))
    if hst == "FOREIGN" or wst == "FOREIGN" or rl or ij:
        sys.exit("ABORT: foreign bytes, a .reloc entry or an interior jump")
    if b"\x08MaxValue\x02" in WIN_ORIG or b"TPF0" in WIN_ORIG:
        sys.exit("ABORT: the window holds a pattern a whole-file scanner looks for")
    if not (a.apply or a.undo):
        print("\nSTATE: %s (dry run -- nothing written)"
              % ("INSTALLED" if hst == "installed" and wst == "ours"
                 else "VANILLA" if hst == "vanilla" and wst == "original" else "MIXED"))
        return
    if a.apply:
        d[co:co + wlen] = want_win
        d[ho:ho + 7] = hook_bytes()
    else:
        d[co:co + wlen] = WIN_ORIG
        d[ho:ho + 7] = HOOK_ORIG
    try:
        open(EXE, "wb").write(d)
    except PermissionError:
        sys.exit("LOCKED -- close AoWDevEd.exe / AoWzEd.exe and retry")
    print("\n%s -- now run build_zigeditor.py --apply to rebuild AoWzEd.exe"
          % ("APPLIED" if a.apply else "UNDONE"))


if __name__ == "__main__":
    main()
