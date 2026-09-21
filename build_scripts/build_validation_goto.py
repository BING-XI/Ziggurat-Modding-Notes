#!/usr/bin/env python3
r"""
MAP VALIDATION DIALOG: CLICKABLE ENTRIES  --  AoWDevEd.exe only.

WHAT IT DOES
  Double-clicking a line in the editor's Map Validation dialog (Developer menu ->
  Validate Map; TMapValidationDlg, a read-only TMemo) centres the map view on the
  object that line refers to, switching surface/underground level if needed.
  Clicking an indented "  Warning: ..." line walks UP to its "<Name> at location
  (x, y, z)" header line; lines with no location above them (e.g. "Map validated
  successfully") do nothing.

HOW (all facts verified against this build 2026-07-28, see
Modding Resources/Validation_Dialog_Clickable_Entries.md)
  * The listing is filled by AoWEPACK's TStructure.MainValidateMap: per object a
    header "%0:s at location %1:s" where %1 is "(" x ", " y ", " z ")" built from
    IntToStr -- the "(x, y, z)" group is ALWAYS the last paren group of a header
    line and survives dictionary translation, so the handler parses the clicked
    line's text (walking upward until a line parses) instead of needing any
    side-channel data.
  * Hook: TMainForm.ValidateMapBtnClick's `call TCustomForm.ShowModal` at
    0x42CEE2 (E8 01 44 FD FF) -> `call install_cave`. At that point EAX = the
    just-created dialog. The cave writes Memo.FOnDblClick (TMethod: Code at
    +0xAC, Data at +0xB0 -- layout proven from VCL30 TControl.DblClick, which
    calls [self+0xAC] with EAX=[self+0xB0], EDX=self) and tail-jumps to the
    ShowModal import thunk. Dialog field +0x1DC = Memo (from the hooked
    function itself: `mov eax,[ebx+0x1DC]; mov edx,[eax+0x130]` = Memo.Lines).
  * Handler (TNotifyEvent: EDX = the memo):
      line := Perform(memo, EM_LINEFROMCHAR, -1, 0)       ; caret = clicked line
      loop: text := Perform(memo, EM_GETLINE, line, @buf) ; walk up while no match
            find LAST '(' ; parse "x, y, z)" (spaces optional, ints capped 999)
      TMainForm.SetMapLevel(mainform, z)   ; 0x429C68 -- no-op if already there,
                                           ; updates the level UI, BOUND-guarded
                                           ; (shortint) hence the z <= 7 sanity cap
      THSMEdit.CenterView(ctrl, x, y, z)   ; thunk 0x402E28; ctrl = mainform+0x22C
                                           ; (EAX=ctrl, EDX=x, ECX=y, push level;
                                           ; clamps to map edges itself)
    Perform is called via AoWDevEd's own IAT slot [0x432354]
    (Controls.TControl.Perform) -- no new imports. MainForm instance:
    [[0x42F0A8]]. All this mirrors TPlayerInfoFloater.StructureGridDblClick
    (0x425BEC), the editor's own dblclick-to-centre precedent.
  * Both caves go in a new PE section ".vgo" (read+exec, no writable state,
    absolute addresses fine -- AoWDevEd.exe is fixed-base 0x400000).

CONVENTIONS: dry-run by default (prints a capstone disassembly of the caves),
--apply to write; idempotent (no-op if .vgo present + hook patched);
verify-before-write (aborts unless the hook site bytes are exactly the vanilla
call or exactly the patched call); auto-backup to `<game dir>\backups\AoWDevEd.exe.pre-valgoto`.
Editor-only -- AoW.exe/AoWCompat.exe untouched. Close AoWDevEd.exe first.
Revert: there is no --undo here, and a .pre-valgoto restore is NOT a revert path -- it is a
WHOLE-FILE copy, so it drops every other AoWDevEd feature (terrainpal, partyrnd, timerres,
modtoolbar, dlgdirs, coppermedal). Undo surgically: restore the 5 hook bytes at HOOK_VA and zero
the .vgo caves.

Needs: pip install keystone-engine capstone
"""
import argparse, os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXE  = "AoWDevEd.exe"
BACKUP_SUFFIX = ".pre-valgoto"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)
SECT_NAME = b".vgo\0\0\0\0"

# ---- verified addresses (AoWDevEd.exe, base 0x400000) ---------------------------
HOOK_VA          = 0x42CEE2   # in TMainForm.ValidateMapBtnClick
SHOWMODAL_THUNK  = 0x4012E8   # VCL30 Forms.TCustomForm.ShowModal import thunk
ORIG_HOOK        = b"\xE8" + struct.pack("<i", SHOWMODAL_THUNK - (HOOK_VA + 5))
PERFORM_IAT      = 0x432354   # IAT slot: VCL30 Controls.TControl.Perform
MAINFORM_GVAR    = 0x42F0A8   # -> ptr -> TMainForm instance
HSMEDIT_OFF      = 0x22C      # TMainForm field: the THSMEdit map-edit control
SETLEVEL_FN      = 0x429C68   # TMainForm.<SetMapLevel>(EAX=form, EDX=level)
CENTERVIEW_THUNK = 0x402E28   # HSEPack HSMEdit.THSMEdit.CenterView import thunk
DLG_MEMO_OFF     = 0x1DC      # TMapValidationDlg field: the TMemo
ONDBL_CODE_OFF   = 0xAC       # TControl.FOnDblClick.Code
ONDBL_DATA_OFF   = 0xB0       # TControl.FOnDblClick.Data
EM_GETLINE       = 0xC4
EM_LINEFROMCHAR  = 0xC9
MAX_COORD        = 999        # parse cap (any real x/y/level is far below)
MAX_LEVEL        = 7          # sanity cap before SetMapLevel (BOUND is shortint)

# ---- caves ----------------------------------------------------------------------
def install_src(handler_va):
    return f"""
        push eax
        mov  eax, dword ptr [eax + {DLG_MEMO_OFF:#x}]
        mov  dword ptr [eax + {ONDBL_CODE_OFF:#x}], {handler_va:#x}
        mov  dword ptr [eax + {ONDBL_DATA_OFF:#x}], eax
        pop  eax
        jmp  {SHOWMODAL_THUNK:#x}
    """

# frame: [ebp-4]=x [ebp-8]=y [ebp-0xC]=z [ebp-0x10]=len [ebp-0x14]=digits
#        [ebp-0x120 .. ebp-0x21] = 256B line buffer (EM_GETLINE cap 254)
HANDLER_SRC = f"""
        push ebp
        mov  ebp, esp
        sub  esp, 0x120
        push ebx
        push esi
        push edi
        mov  ebx, edx                       ; the memo control

        push 0                              ; LParam
        or   ecx, -1                        ; WParam -1 = caret
        mov  edx, {EM_LINEFROMCHAR:#x}
        mov  eax, ebx
        call dword ptr [{PERFORM_IAT:#x}]   ; clicked line index
        mov  esi, eax

    lineloop:
        test esi, esi
        js   done

        mov  word ptr [ebp - 0x120], 0xFE   ; EM_GETLINE buffer capacity
        lea  eax, [ebp - 0x120]
        push eax
        mov  ecx, esi
        mov  edx, {EM_GETLINE:#x}
        mov  eax, ebx
        call dword ptr [{PERFORM_IAT:#x}]
        mov  dword ptr [ebp - 0x10], eax    ; chars copied

        lea  edx, [ebp - 0x120]
        mov  ecx, eax                       ; scan for the LAST '('
    findparen:
        dec  ecx
        js   nextline
        cmp  byte ptr [edx + ecx], 0x28
        jne  findparen

        lea  edi, [edx + ecx + 1]           ; p  = after '('
        add  edx, dword ptr [ebp - 0x10]    ; end = buf + len

        call getint
        cmp  eax, -1
        je   nextline
        mov  dword ptr [ebp - 4], eax       ; x
        mov  cl, 0x2C
        call getsym
        test eax, eax
        jnz  nextline
        call getint
        cmp  eax, -1
        je   nextline
        mov  dword ptr [ebp - 8], eax       ; y
        mov  cl, 0x2C
        call getsym
        test eax, eax
        jnz  nextline
        call getint
        cmp  eax, -1
        je   nextline
        mov  dword ptr [ebp - 0xC], eax     ; z (level)
        mov  cl, 0x29
        call getsym
        test eax, eax
        jnz  nextline
        jmp  goto_loc

    nextline:
        dec  esi                            ; indented warning -> try header above
        jmp  lineloop

    goto_loc:
        mov  eax, dword ptr [ebp - 0xC]
        cmp  eax, {MAX_LEVEL}
        ja   done
        mov  edx, eax
        mov  eax, dword ptr [{MAINFORM_GVAR:#x}]
        mov  eax, dword ptr [eax]
        test eax, eax
        jz   done
        call {SETLEVEL_FN:#x}               ; switch displayed level (no-op if same)
        mov  eax, dword ptr [{MAINFORM_GVAR:#x}]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + {HSMEDIT_OFF:#x}]
        push dword ptr [ebp - 0xC]
        mov  edx, dword ptr [ebp - 4]
        mov  ecx, dword ptr [ebp - 8]
        call {CENTERVIEW_THUNK:#x}          ; centre view (clamps to map edges)

    done:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret

    getint:                                 ; edi=p (io), edx=end -> eax=val | -1
        xor  eax, eax
        mov  dword ptr [ebp - 0x14], 0
    gi_sp:
        cmp  edi, edx
        jae  gi_chk
        cmp  byte ptr [edi], 0x20
        jne  gi_dig
        inc  edi
        jmp  gi_sp
    gi_dig:
        cmp  edi, edx
        jae  gi_chk
        movzx ecx, byte ptr [edi]
        sub  ecx, 0x30
        cmp  ecx, 9
        ja   gi_chk
        imul eax, eax, 10
        add  eax, ecx
        cmp  eax, {MAX_COORD}
        ja   gi_fail
        inc  edi
        inc  dword ptr [ebp - 0x14]
        jmp  gi_dig
    gi_chk:
        cmp  dword ptr [ebp - 0x14], 0
        jne  gi_ok
    gi_fail:
        or   eax, -1
    gi_ok:
        ret

    getsym:                                 ; cl=expected char; skips spaces first
    gs_sp:                                  ; -> eax=0 ok (p past char) | 1 fail
        cmp  edi, edx
        jae  gs_fail
        cmp  byte ptr [edi], 0x20
        jne  gs_chk
        inc  edi
        jmp  gs_sp
    gs_chk:
        cmp  byte ptr [edi], cl
        jne  gs_fail
        inc  edi
        xor  eax, eax
        ret
    gs_fail:
        mov  eax, 1
        ret
"""

def asm_src(ks, src, va):
    """keystone (LLVM) has no ';' comments in Intel mode -- strip them first."""
    clean = "\n".join(ln.split(";", 1)[0] for ln in src.splitlines())
    code, _ = ks.asm(clean, va)
    return bytes(code)

# ---- PE helpers (same shapes as the other AoWDevEd build scripts) ---------------
def load_sections(d):
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e+6)[0]
    optsz = struct.unpack_from('<H', d, e+20)[0]
    opt = e+24; sectbl = opt+optsz
    secs = []
    for i in range(nsec):
        b = sectbl+i*40
        vsz, va, rsz, raw = struct.unpack_from('<IIII', d, b+8)
        secs.append((va, vsz, raw, rsz, b))
    return dict(e=e, nsec=nsec, opt=opt, sectbl=sectbl, secs=secs,
                salign=struct.unpack_from('<I', d, opt+32)[0],
                falign=struct.unpack_from('<I', d, opt+36)[0],
                hdrsz=struct.unpack_from('<I', d, opt+84)[0])

def align(x, a): return (x + a - 1) // a * a

def rva2off(secs, rva):
    for va0, vsz, raw, rsz, _ in secs:
        if va0 <= rva < va0 + max(vsz, rsz):
            return raw + (rva - va0)
    raise ValueError(hex(rva))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    path = os.path.join(GAME, EXE)
    d = bytearray(open(path, "rb").read())
    F = load_sections(d)

    hook_off = rva2off(F["secs"], HOOK_VA - 0x400000)
    hook_now = bytes(d[hook_off:hook_off+5])
    have_sect = any(bytes(d[s[4]:s[4]+4]) == SECT_NAME[:4] for s in F["secs"])

    # ---- lay the section out (deterministically) so we can check both states ----
    newva = align(max(s[0] + max(s[1], s[3]) for s in F["secs"]), F["salign"])
    if have_sect:   # already applied: the section exists; recompute ITS va instead
        for s in F["secs"]:
            if bytes(d[s[4]:s[4]+4]) == SECT_NAME[:4]:
                newva = s[0]
    base_va = 0x400000 + newva

    handler_va = base_va                       # handler first (install refs it)
    hcode = asm_src(ks, HANDLER_SRC, handler_va)
    install_va = base_va + align(len(hcode), 16)
    icode = asm_src(ks, install_src(handler_va), install_va)
    body = hcode + b"\x90" * (install_va - base_va - len(hcode)) + icode

    patched_hook = b"\xE8" + struct.pack("<i", install_va - (HOOK_VA + 5))

    print(f"[{EXE}] handler {len(hcode)}B @ {handler_va:#x}, "
          f"install {len(icode)}B @ {install_va:#x} (section .vgo rva {newva:#x})")

    if have_sect and hook_now == patched_hook:
        print(f"[{EXE}] already patched (.vgo present, hook installed) - no-op")
        return 0
    if have_sect != (hook_now == patched_hook):
        print(f"[{EXE}] INCONSISTENT STATE: section present={have_sect}, "
              f"hook bytes={hook_now.hex()} - refusing to touch")
        return 1
    assert hook_now == ORIG_HOOK, (
        f"hook site {HOOK_VA:#x} is neither vanilla nor patched: {hook_now.hex()} "
        f"(expected {ORIG_HOOK.hex()}) - editor build differs, aborting")
    assert F["sectbl"] + (F["nsec"]+1)*40 <= F["hdrsz"], "no header room for a new section"

    # dry-run review: capstone disassembly of what will be written
    if not args.apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            cs = Cs(CS_ARCH_X86, CS_MODE_32)
            print("---- handler cave ----")
            for i in cs.disasm(hcode, handler_va):
                print(f"  {i.address:08X}  {i.mnemonic:7s} {i.op_str}")
            print("---- install cave ----")
            for i in cs.disasm(icode, install_va):
                print(f"  {i.address:08X}  {i.mnemonic:7s} {i.op_str}")
        except ImportError:
            print("  (capstone not installed - skipping disasm preview)")
        print(f"---- hook @ {HOOK_VA:#x}: {ORIG_HOOK.hex()} -> {patched_hook.hex()}")
        print(f"[{EXE}] dry-run OK - re-run with --apply to write")
        return 0

    backup = os.path.join(BACKUP_DIR, os.path.basename(path) + BACKUP_SUFFIX)
    if not os.path.exists(backup):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, backup)
        print(f"    backup -> {backup}")

    newraw = align(len(d), F["falign"])
    d += b"\x00" * (newraw - len(d))
    rawsz = align(len(body), F["falign"])
    d += bytes(body) + b"\x00" * (rawsz - len(body))
    b = F["sectbl"] + F["nsec"]*40
    struct.pack_into("<8sIIII", d, b, SECT_NAME, len(body), newva, rawsz, newraw)
    struct.pack_into("<IIHHI", d, b+24, 0, 0, 0, 0, 0x60000020)   # code|exec|read
    struct.pack_into("<H", d, F["e"]+6, F["nsec"]+1)
    struct.pack_into("<I", d, F["opt"]+56, align(newva + len(body), F["salign"]))
    d[hook_off:hook_off+5] = patched_hook

    try:
        open(path, "wb").write(d)
    except PermissionError:
        print(f"[{EXE}] LOCKED - close the editor and retry")
        return 1
    print(f"[{EXE}] applied: .vgo @ rva {newva:#x} ({len(body)}B), "
          f"hook {HOOK_VA:#x} -> install cave {install_va:#x}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
