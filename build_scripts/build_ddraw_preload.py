#!/usr/bin/env python
r"""
build_ddraw_preload.py -- AoWz.exe loads "ddraw.dll" by name at startup, so a DirectDraw wrapper
placed beside it (cnc-ddraw) takes over the display.  AoWz.exe (exe_patch.py).

WHY
    The game never imports ddraw.dll.  It creates DirectDraw through COM (GFXEPACK and AoWSetup:
    CoCreateInstance(CLSID_DirectDraw)), and the CLSID's InprocServer32 is the absolute
    %SystemRoot%\system32\ddraw.dll, so a ddraw.dll in the game folder is never loaded (measured
    2026-10-18: only the system copy in the module list).  cnc-ddraw hooks that COM call once its
    DLL is in the process -- what its proxy DLLs exist to arrange.  Loading it ourselves at entry
    needs no third-party proxy.  Measured with a scratch launcher doing the same LoadLibraryA: the
    process then holds Ziggurat\ddraw.dll and d3d9.dll and no system ddraw.dll, and fullscreen and
    resolution switches work (owner, 2026-10-18).

    On this machine DirectDraw reports no 16-bit display modes (32-bit only, 640x480..3840x2160),
    and both the game's video list (GFXE.ListDisplayModes) and AoWSetup's ask for 16-bit only, so
    without a wrapper fullscreen cannot be selected at all.  cnc-ddraw supplies the modes.

THE PATCH
    Entry point 0x45995C, 6 B `push ebp / mov ebp,esp / add esp,-0x14` -> jmp cave_preload + nop.
    The cave: GetModuleHandleA("kernel32.dll") (the exe's own import, IAT 0x45D39C), walks
    kernel32's export names for "LoadLibraryA" (real code in SysWOW64's kernel32, not a forwarder),
    calls LoadLibraryA("ddraw.dll"), replays the six bytes and resumes at 0x459962.  All registers
    preserved.  Self-contained on purpose: borrowing vcl30.dpl's LoadLibraryA import slot would tie
    this to a file Ziggurat also patches.
    ddraw is not a KnownDLL, so the name resolves to the game folder first.  With no ddraw.dll there,
    it loads the system copy, which COM would load moments later anyway: behaviour unchanged.
    The presence of Ziggurat\ddraw.dll is the switch.

Slot 0x0062AE80-0x0062AF7F in .hcol, exclusive.  No randomness.

USAGE
    python build_ddraw_preload.py [--dis]   verify / dry run
    python build_ddraw_preload.py --apply
    python build_ddraw_preload.py --undo    surgical
"""
import sys
sys.dont_write_bytecode = True
from exe_patch import asm, jmp_to, run

SLOT = (0x0062AE80, 0x0062AF80)
STR_K32, STR_LLA, STR_DDRAW, CAVE = 0x0062AE80, 0x0062AE90, 0x0062AEA0, 0x0062AEB0
ENTRY, ENTRY_VAN, RESUME = 0x0045995C, bytes.fromhex("558bec83c4ec"), 0x00459962
IAT_GETMODULEHANDLEA = 0x0045D39C

SRC = f"""
    pushad
    push {STR_K32:#x}
    call dword ptr [{IAT_GETMODULEHANDLEA:#x}]
    test eax, eax
    je Ldone
    mov ebx, eax
    mov eax, dword ptr [ebx+0x3c]
    mov eax, dword ptr [ebx+eax+0x78]
    test eax, eax
    je Ldone
    lea esi, [ebx+eax]
    mov ecx, dword ptr [esi+0x18]
    mov edx, dword ptr [esi+0x20]
    add edx, ebx
Lname:
    dec ecx
    js Ldone
    mov edi, dword ptr [edx+ecx*4]
    add edi, ebx
    push ecx
    push esi
    mov esi, {STR_LLA:#x}
    mov ecx, 13
    repe cmpsb
    pop esi
    pop ecx
    jne Lname
    mov edx, dword ptr [esi+0x24]
    add edx, ebx
    movzx eax, word ptr [edx+ecx*2]
    mov edx, dword ptr [esi+0x1c]
    add edx, ebx
    mov eax, dword ptr [edx+eax*4]
    add eax, ebx
    push {STR_DDRAW:#x}
    call eax
Ldone:
    popad
    push ebp
    mov ebp, esp
    add esp, -0x14
    jmp {RESUME:#x}
"""

caves = [("str_kernel32", STR_K32, b"kernel32.dll\0"),
         ("str_loadlibrarya", STR_LLA, b"LoadLibraryA\0"),
         ("str_ddraw", STR_DDRAW, b"ddraw.dll\0"),
         ("cave_preload", CAVE, asm(SRC, CAVE))]
hooks = [(ENTRY, ENTRY_VAN, jmp_to(ENTRY, CAVE, len(ENTRY_VAN)))]

if __name__ == "__main__":
    run("build_ddraw_preload", hooks, caves, SLOT)
