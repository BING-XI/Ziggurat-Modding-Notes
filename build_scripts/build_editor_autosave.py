#!/usr/bin/env python3
r"""
EDITOR AUTOSAVE (v2)  --  Ziggurat\HSEPack.dpl only.

WHAT IT DOES
  Every AUTOSAVE_MINUTES the map editor writes the open map to
      <engine data root>Scenario\Autosave\Autosave 1.hsm / 2 / 3
  overwriting whichever of the three is OLDEST (a missing file counts as oldest), so the three
  always hold the last three autosaved states, newest by file date. The user's own filename,
  title bar and modified flag are untouched: Save still writes the user's file, and closing still
  asks about unsaved changes. Both folders are created on demand. No new import, no exe byte, so
  no `build_zigeditor.py` step: AoWzEd.exe loads Ziggurat\HSEPack.dpl directly.

  A tick saves only when ALL hold (else it does nothing and waits for the next tick):
    * [THSMEdit+0x1BC] != 0            a map is open (the test THSMEdit.Save makes)
    * [engine+0x34] & 0x1E == 0        the engine is not loading/saving a map or mapset
                                       (bits set by LoadHSM 2, SaveHSM 4, LoadHSS 8, SaveHSS 0x10)
    * [map+0x3C] & 0x99 == 0x81        modified (bit 0), EDITED SINCE THE LAST AUTOSAVE (bit 7,
                                       this patch), not being read (0x10) or destroyed (8)
    * IsWindowEnabled(parent form)     no modal dialog or message box is up over the editor
  so an idle editor, a map the user has just saved, and a map with no edit since the last
  autosave all write nothing.

HOW -- three edits, all in HSEPack.dpl (preferred base 0x55600000; it rebases, cave is PIC)
  1. THSMap.SetModified @0x5560C3C0 ORs the set constant at 0x5560C3D0 into [map+0x3C].
     That constant 01 -> 81: every SetModified now also sets bit 7, "edited since the last
     autosave". ResetModified's constant (0x5560C3E8) stays 01, so a manual save clears bit 0
     only; the tick clears bit 7. Bit 7 of [THSMap+0x3C] is otherwise unused: every byte access
     to +0x3C on a map in HSEPack, AoWEPACK, AoWDevEd.exe and AoWz.exe is a single-bit test or
     an OR/AND with a set constant (1, 2, 4, 8, 0x10). The game calls SetModified too and gets
     the bit; nothing there reads it, and [map+0x3C] is runtime state, not serialized.
  2. THSMEdit.SetHSEngine @0x55613CD0 entry, 6 B `85 D2 74 13 8B CA` (test edx,edx / je /
     mov ecx,edx) -> `jmp hook_seteng` + nop. Called once, from TMainForm.FormCreate
     (AoWDevEd/AoWzEd 0x0042864F); the game imports no THSMEdit symbol. hook_seteng replays the
     test and, for a non-nil engine, creates ONE VCL TTimer (owner = the THSMEdit, so it dies
     with the map view) with OnTimer = tick (Data = the THSMEdit), Interval = the period.
     Guarded by G_TIMER so a second SetHSEngine makes no second timer.
  3. Cave, CODE zero tail (see OWNERSHIP): hook_seteng + make_timer at +0, seh_restore +0xD0,
     getdelta +0xF0, tick + set_len + set_len_mkdir +0x100, the three path literals +0x300.

  VCL30 is reached with no new import: vcl_delta = [HSEPack IAT slot of TOpenDialog.Create
  0x556308DC] - 0x4137AFB0, then TTimer VMT 0x413542F8, TTimer.Create 0x41356AE8,
  TTimer.SetInterval 0x41356C78, SysUtils.CreateDir 0x4130C194, SysUtils.FileAge 0x4130B3EC,
  Forms.GetParentForm 0x41335578 (all preferred VAs + delta). HSEPack's own thunks cover
  TWinControl.GetHandle (0x55601834) and user32!IsWindowEnabled (0x5560153C), reached rel32.
  TTimer fields (vcl30, instsize 0x38): FInterval +0x24, FOnTimer.Code +0x2C, .Data +0x30.
  Setting the fields and then calling SetInterval runs UpdateTimer, which calls SetTimer.

  The save is THSMEdit.Save's call without its filename store:
  `push 0 / push 0 / edx = path / eax = engine / call [[eax]+0xAC]` = THSEngine.SaveHSM
  @0x5561043C. A nil progress callback is safe: TEStorageStream.ShowProgress tests only the
  high word. ⚠⚠ SaveHSM CLEARS THE MODIFIED BIT ITSELF: TAoWHSMap.ReadWrite (AoWEPACK
  0x55776DD5) calls THSMap.ResetModified whenever (stream mode & 6) == 2, i.e. on every binary
  write -- THSMEdit.Save's own ResetModified is redundant. Measured live: 0x87 -> 0x06. So the
  tick ORs bit 0 back after the call, and a hand-built SEH frame around the call (handler
  seh_restore, map pointer pushed just above the record) ORs it back if SaveHSM raises and then
  returns ExceptionContinueSearch. HSEPack has no load config, so the handler needs no SafeSEH
  entry.
  ⚠ Exceptions: TTimer.WndProc (vcl30 0x41356B68) wraps OnTimer in try/except ->
  Application.HandleException, so a failed save (read-only file, disk full, no Scenario\)
  shows the VCL error box and the editor carries on. Bit 7 is cleared BEFORE the save, so a
  failing target costs one box per burst of edits, not one per tick.

  Path: FStartupDirectory = [engine+0x2C] (TEngine; always ends in '\', see build_dlgdirs.py)
  + "Scenario" (CreateDir) + "\Autosave" (CreateDir) + "\Autosave N.hsm", built in G_PATH, a
  Delphi AnsiString with refcount -1 (callees deep-copy it, never free it). Nothing is baked:
  the root is read at run time. Roots over ROOT_MAX chars skip the save.

OWNERSHIP (record in 12-re-toolchain.md §6.2 HSEPack)
  0x5561C000..0x5561C3FF  CODE zero tail, exclusive. HSEPack's last CODE export ends
                          ~0x5561ACEB; build_hss_exception_detail.py reserves 0x5561B000..+0x1FF.
                          CODE is R+X only -- no state here.
  0x5562FC00..0x5562FFFF  BSS page slack past VirtualSize 0x88D (loader-zeroed, RW, no file
                          bytes), exclusive: G_TIMER +0, G_PATH StrRec +8/+0xC, chars +0x10.
  0x55613CD0 (6 B)        hook site.   0x5560C3D0 (1 B)  SetModified's set constant.
  No .reloc entry in any of these ranges (asserted); the cave uses no absolute address.

RANDOMNESS: none drawn. Multiplayer: the game-side effect is one extra bit in a runtime map field.

UNPROVEN (static checks cannot show it): that no editor edit path marks the map modified
without THSMap.SetModified (such an edit is only autosaved after the next SetModified edit).
Mapset (.hss / .pfs) edits are not autosaved -- only the map.

USAGE
  python build_editor_autosave.py            dry run: state + cave disassembly
  python build_editor_autosave.py --apply    write (kills AoW binaries holding the DLL)
  python build_editor_autosave.py --undo     surgical: hook bytes, the constant, zero the cave
                                             and nothing else
  Re-tune (AUTOSAVE_MINUTES, SLOTS, folder names) by editing the constants and re-running
  --apply: the cave is rewritten in place.

v1 (2026-07-07, reverted) hooked TMainForm.HSMEditUpdateFrame in AoWDevEd.exe; that is an
event fired only while the mouse is over a hex with the app active, so its frame counter never
advanced. v1 is gone; this file is v2.
"""
import os, struct, subprocess, sys

from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL = os.path.join(GAME, "HSEPack.dpl")

AUTOSAVE_MINUTES = 5
SLOTS = 3                                  # Autosave 1 .. Autosave SLOTS  (1..9)
DIR1 = b"Scenario"                         # under the engine data root
DIR2 = b"\\Autosave"
FILE = b"\\Autosave 1.hsm"                 # the digit is FILE[-5]

PREF_BASE = 0x55600000

# --- edit 1: THSMap.SetModified's set constant ---------------------------------------------
SETMOD_FN = 0x5560C3C0
SETMOD_FN_BYTES = bytes.fromhex("538bd8a0d0c36055")     # push ebx/mov ebx,eax/mov al,[0x5560C3D0]
SETMOD_CONST = 0x5560C3D0
CONST_VANILLA, CONST_OURS = 0x01, 0x81

# --- edit 2: THSMEdit.SetHSEngine entry ----------------------------------------------------
HOOK_VA = 0x55613CD0
HOOK_ORIG = bytes.fromhex("85d274138bca")               # test edx,edx / je +0x13 / mov ecx,edx
HOOK_RESUME = 0x55613CD6                                # mov [eax+0x1C0],ecx
HOOK_NIL = 0x55613CE7                                   # xor edx,edx (the nil-engine path)

# --- edit 3: the cave and its state --------------------------------------------------------
CAVE = 0x5561C000
CAVE_END = 0x5561C400
SEH_RESTORE = CAVE + 0xD0
GETDELTA = CAVE + 0xF0
TICK = CAVE + 0x100                                     # fixed: make_timer stores its address
LITS = CAVE + 0x300
LIT_DIR1, LIT_DIR2, LIT_FILE = LITS, LITS + 0x10, LITS + 0x20

G_TIMER = 0x5562FC00
G_PATH = 0x5562FC10                                     # chars; StrRec refcount -8, length -4
G_END = 0x55630000
ROOT_MAX = 0x300                                        # G_PATH + root + 8+9+15+NUL < G_END

BSS_VA, BSS_VSIZE = 0x5562F000, 0x88D

# HSEPack imports / thunks (rel32 from the cave, so PIC)
IAT_OPENDLG_CREATE = 0x556308DC                         # VCL30 Dialogs.TOpenDialog.Create
THUNK_GETHANDLE = 0x55601834                            # jmp [0x55630750] TWinControl.GetHandle
IAT_GETHANDLE = 0x55630750
THUNK_ISWINENABLED = 0x5560153C                         # jmp [0x55630618] user32!IsWindowEnabled
IAT_ISWINENABLED = 0x55630618

# VCL30 preferred VAs (+ vcl_delta at run time)
VCL_OPENDLG_CREATE = 0x4137AFB0
VCL_TTIMER = 0x413542F8                                 # ExtCtrls..TTimer (VMT)
VCL_TIMER_CREATE = 0x41356AE8
VCL_TIMER_SETINTERVAL = 0x41356C78
VCL_CREATEDIR = 0x4130C194
VCL_FILEAGE = 0x4130B3EC
VCL_GETPARENTFORM = 0x41335578
VCL_EXPECT = {                                          # first bytes, checked against vcl30.dpl
    VCL_TIMER_CREATE: "5356" "84d2" "7408",
    VCL_TIMER_SETINTERVAL: "3b5024" "7408" "895024",
    VCL_CREATEDIR: "53" "8bd8" "6a00",
    VCL_FILEAGE: "55" "8bec" "81c4b4feffff",
    VCL_GETPARENTFORM: "5356" "8bd8" "eb02",
}

# engine / map / view offsets
MAPEDIT_OPEN = 0x1BC        # THSMEdit: map loaded
MAPEDIT_ENGINE = 0x1C0      # THSMEdit: THSEngine
ENGINE_STATE = 0x34         # THSEngine: load/save bits
ENGINE_MAP = 0x3C           # THSEngine: current THSMap
ENGINE_ROOT = 0x2C          # TEngine.FStartupDirectory
MAP_STATE = 0x3C            # THSMap: 1 modified, 8 destroying, 0x10 reading, 0x80 ours
SAVEHSM_SLOT = 0xAC         # THSEngine VMT: SaveHSM(FileName; progress Code, Data) ret 8
TIMER_ONTIMER = 0x2C        # TTimer.FOnTimer.Code (+0x30 Data)


def assemble(ks, src, va):
    """keystone has no ';' comments in Intel mode -- strip them first."""
    clean = "\n".join(ln.split(";", 1)[0] for ln in src.splitlines())
    code, _ = ks.asm(clean, va)
    return bytes(code)


def build_cave(ks):
    interval = AUTOSAVE_MINUTES * 60 * 1000
    getdelta = f"""
getdelta:                                   ; eax = runtime - preferred (HSEPack rebases)
    call gd1
gd1:
    pop eax
    sub eax, {GETDELTA + 5:#x}
    ret
"""
    seh = f"""
seh_restore:                                ; SEH handler (cdecl): [esp+8] = EstablisherFrame
    mov eax, dword ptr [esp + 8]
    mov eax, dword ptr [eax + 8]            ; the map, pushed just above the record
    or byte ptr [eax + {MAP_STATE:#x}], 1   ; SaveHSM may have reset it before raising
    xor eax, eax
    inc eax                                 ; ExceptionContinueSearch
    ret
"""
    head = f"""
hook_seteng:                                ; THSMEdit.SetHSEngine entry: eax = Self, edx = engine
    test edx, edx
    jz seteng_nil
    push eax
    push edx
    call make_timer
    pop edx
    pop eax
    mov ecx, edx                            ; the displaced instruction
    jmp {HOOK_RESUME:#x}
seteng_nil:
    jmp {HOOK_NIL:#x}

make_timer:                                 ; eax = THSMEdit
    push ebx
    push esi
    push edi
    push ebp
    mov ebx, eax
    call {GETDELTA:#x}
    mov esi, eax
    cmp dword ptr [esi + {G_TIMER:#x}], 0
    jne mt_done
    mov edi, dword ptr [esi + {IAT_OPENDLG_CREATE:#x}]
    sub edi, {VCL_OPENDLG_CREATE:#x}        ; vcl_delta
    lea eax, [edi + {VCL_TTIMER:#x}]
    mov dl, 1
    mov ecx, ebx                            ; Owner = the map view
    lea ebp, [edi + {VCL_TIMER_CREATE:#x}]
    call ebp
    mov dword ptr [esi + {G_TIMER:#x}], eax
    lea ecx, [esi + {TICK:#x}]
    mov dword ptr [eax + {TIMER_ONTIMER:#x}], ecx
    mov dword ptr [eax + {TIMER_ONTIMER + 4:#x}], ebx
    mov edx, {interval:#x}
    lea ebp, [edi + {VCL_TIMER_SETINTERVAL:#x}]
    call ebp                                ; -> UpdateTimer -> SetTimer
mt_done:
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret
"""
    tick = f"""
tick:                                       ; OnTimer: eax = Data = THSMEdit, edx = the timer
    push ebx
    push esi
    push edi
    push ebp
    mov ebx, eax
    cmp byte ptr [ebx + {MAPEDIT_OPEN:#x}], 0
    je t_done
    mov edi, dword ptr [ebx + {MAPEDIT_ENGINE:#x}]
    test edi, edi
    jz t_done
    test byte ptr [edi + {ENGINE_STATE:#x}], 0x1e
    jnz t_done
    mov eax, dword ptr [edi + {ENGINE_MAP:#x}]
    test eax, eax
    jz t_done
    mov cl, byte ptr [eax + {MAP_STATE:#x}]
    and cl, 0x99
    cmp cl, 0x81
    jne t_done
    call {GETDELTA:#x}
    mov esi, eax
    mov ebp, dword ptr [esi + {IAT_OPENDLG_CREATE:#x}]
    sub ebp, {VCL_OPENDLG_CREATE:#x}        ; vcl_delta
    mov eax, ebx
    lea ecx, [ebp + {VCL_GETPARENTFORM:#x}]
    call ecx
    test eax, eax
    jz t_done
    call {THUNK_GETHANDLE:#x}
    push eax
    call {THUNK_ISWINENABLED:#x}            ; a modal window disables the editor's form
    test eax, eax
    jz t_done
    mov eax, dword ptr [edi + {ENGINE_ROOT:#x}]
    test eax, eax
    jz t_done
    mov ecx, dword ptr [eax - 4]
    test ecx, ecx
    jz t_done
    cmp ecx, {ROOT_MAX:#x}
    ja t_done
    push edi                                ; engine -- no exit to t_done until it is popped
    lea edi, [esi + {G_PATH:#x}]
    push esi
    mov esi, eax
    rep movsb                               ; <root>
    pop esi
    push esi
    lea esi, [esi + {LIT_DIR1:#x}]
    mov ecx, {len(DIR1)}
    rep movsb                               ; <root>Scenario
    pop esi
    call set_len_mkdir
    push esi
    lea esi, [esi + {LIT_DIR2:#x}]
    mov ecx, {len(DIR2)}
    rep movsb                               ; <root>Scenario\\Autosave
    pop esi
    call set_len_mkdir
    push esi
    lea esi, [esi + {LIT_FILE:#x}]
    mov ecx, {len(FILE)}
    rep movsb                               ; ...\\Autosave 1.hsm
    pop esi
    call set_len
    sub edi, 5                              ; edi -> the digit
    mov ebx, 0x7fffffff                     ; oldest age so far
    push 0x31                               ; chosen digit
age_loop:
    lea eax, [esi + {G_PATH:#x}]
    lea ecx, [ebp + {VCL_FILEAGE:#x}]
    call ecx                                ; DOS date-time, -1 if missing
    cmp eax, ebx
    jge age_next
    mov ebx, eax
    movzx eax, byte ptr [edi]
    mov dword ptr [esp], eax
age_next:
    inc byte ptr [edi]
    cmp byte ptr [edi], {0x31 + SLOTS:#x}
    jb age_loop
    pop eax
    mov byte ptr [edi], al
    pop edi                                 ; engine
    mov eax, dword ptr [edi + {ENGINE_MAP:#x}]
    and byte ptr [eax + {MAP_STATE:#x}], 0x7f   ; consume "edited since the last autosave"
    push eax                                ; map, read by seh_restore
    lea ecx, [esi + {SEH_RESTORE:#x}]
    push ecx
    push dword ptr fs:[0]
    mov dword ptr fs:[0], esp
    push 0                                  ; progress Data
    push 0                                  ; progress Code = nil
    lea edx, [esi + {G_PATH:#x}]
    mov eax, edi
    mov ecx, dword ptr [eax]
    call dword ptr [ecx + {SAVEHSM_SLOT:#x}]   ; THSEngine.SaveHSM, ret 8
    pop dword ptr fs:[0]
    pop ecx
    pop eax
    or byte ptr [eax + {MAP_STATE:#x}], 1   ; TAoWHSMap.ReadWrite reset it; the user's file is unsaved
t_done:
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret

set_len:                                    ; edi = end of text: NUL + StrRec
    mov byte ptr [edi], 0
    lea eax, [esi + {G_PATH:#x}]
    mov ecx, edi
    sub ecx, eax
    mov dword ptr [eax - 4], ecx
    mov dword ptr [eax - 8], 0xffffffff
    ret

set_len_mkdir:
    call set_len
    lea eax, [esi + {G_PATH:#x}]
    lea ecx, [ebp + {VCL_CREATEDIR:#x}]
    call ecx                                ; False when it exists already -- ignored
    ret
"""
    a = assemble(ks, head, CAVE)
    h = assemble(ks, seh, SEH_RESTORE)
    g = assemble(ks, getdelta, GETDELTA)
    b = assemble(ks, tick, TICK)
    assert CAVE + len(a) <= SEH_RESTORE, f"head overruns seh_restore: {len(a):#x}"
    assert SEH_RESTORE + len(h) <= GETDELTA, f"seh_restore overruns getdelta: {len(h):#x}"
    assert g[:6] == bytes.fromhex("e80000000058"), "getdelta is not call $+5 / pop eax"
    assert TICK + len(b) <= LITS, f"tick overruns literals: {len(b):#x}"
    blob = bytearray(CAVE_END - CAVE)
    blob[0:len(a)] = a
    blob[SEH_RESTORE - CAVE:SEH_RESTORE - CAVE + len(h)] = h
    blob[GETDELTA - CAVE:GETDELTA - CAVE + len(g)] = g
    blob[TICK - CAVE:TICK - CAVE + len(b)] = b
    for va, s in ((LIT_DIR1, DIR1), (LIT_DIR2, DIR2), (LIT_FILE, FILE)):
        assert len(s) < 0x10, s
        blob[va - CAVE:va - CAVE + len(s)] = s
    assert CAVE + len(blob) <= CAVE_END
    return bytes(blob), len(a), len(b), len(h)


# ------------------------------------------------------------------------------------------
class PEFile:
    def __init__(self, data):
        self.d = data
        e = struct.unpack_from("<I", data, 0x3C)[0]
        nsec = struct.unpack_from("<H", data, e + 6)[0]
        opt = e + 24
        self.base = struct.unpack_from("<I", data, opt + 28)[0]
        self.reloc_dir = struct.unpack_from("<II", data, opt + 96 + 5 * 8)
        self.loadcfg_dir = struct.unpack_from("<II", data, opt + 96 + 10 * 8)
        self.dllchars = struct.unpack_from("<H", data, opt + 70)[0]
        sect = opt + struct.unpack_from("<H", data, e + 20)[0]
        self.secs = []
        for i in range(nsec):
            b = sect + 40 * i
            name = data[b:b + 8].rstrip(b"\0")
            vsz, va, rsz, raw = struct.unpack_from("<IIII", data, b + 8)
            self.secs.append((name, va, vsz, raw, rsz))

    def off(self, va):
        rva = va - self.base
        for _, sva, vsz, raw, rsz in self.secs:
            if sva <= rva < sva + rsz:
                return raw + rva - sva
        raise ValueError(f"{va:#x} has no file bytes")

    def rd(self, va, n):
        o = self.off(va)
        return bytes(self.d[o:o + n])

    def relocs(self):
        rva, size = self.reloc_dir
        o = self.off(self.base + rva)
        end, out = o + size, []
        while o < end:
            page, bs = struct.unpack_from("<II", self.d, o)
            if bs == 0:
                break
            for i in range((bs - 8) // 2):
                e = struct.unpack_from("<H", self.d, o + 8 + 2 * i)[0]
                if e >> 12:
                    out.append(self.base + page + (e & 0xFFF))
            o += bs
        return out

    def section(self, name):
        return next(s for s in self.secs if s[0] == name)


def static_checks(pe):
    """Everything the cave assumes about HSEPack.dpl and vcl30.dpl; abort on any mismatch."""
    assert pe.base == PREF_BASE, f"HSEPack preferred base {pe.base:#x}"
    # seh_restore is a raw SEH handler: no SafeSEH table (load config) and no NO_SEH flag
    assert pe.loadcfg_dir[1] == 0 and not pe.dllchars & 0x400, "HSEPack has SafeSEH / NO_SEH"
    assert pe.rd(SETMOD_FN, 8) == SETMOD_FN_BYTES, "THSMap.SetModified differs"
    assert pe.rd(HOOK_VA + 6, 6) == bytes.fromhex("8988c0010000"), "SetHSEngine body differs"
    assert pe.rd(HOOK_NIL, 2) == bytes.fromhex("33d2"), "SetHSEngine nil path differs"
    for thunk, slot in ((THUNK_GETHANDLE, IAT_GETHANDLE), (THUNK_ISWINENABLED, IAT_ISWINENABLED)):
        assert pe.rd(thunk, 6) == b"\xff\x25" + struct.pack("<I", slot), f"thunk {thunk:#x}"
    assert pe.rd(0x55601A54, 6) == b"\xff\x25" + struct.pack("<I", IAT_OPENDLG_CREATE)
    name, va, vsz, raw, rsz = pe.section(b"CODE")
    assert pe.base + va + vsz >= CAVE_END, "cave is past CODE's VirtualSize"
    name, va, vsz, raw, rsz = pe.section(b"BSS")
    assert (pe.base + va, vsz) == (BSS_VA, BSS_VSIZE), f"BSS is {pe.base + va:#x}/{vsz:#x}"
    assert BSS_VA + vsz <= G_TIMER and G_END == (BSS_VA + vsz + 0xFFF) & ~0xFFF
    assert pe.base + pe.section(b".idata")[1] == G_END, ".idata no longer follows BSS's page"
    assert G_PATH + ROOT_MAX + len(DIR1) + len(DIR2) + len(FILE) + 1 <= G_END
    bad = [r for r in pe.relocs()
           if HOOK_VA - 3 <= r < HOOK_VA + 6 or SETMOD_CONST - 3 <= r < SETMOD_CONST + 1
           or CAVE - 3 <= r < CAVE_END]
    assert not bad, "reloc entries in a patched range: " + ", ".join(map(hex, bad))

    vcl = PEFile(open(os.path.join(GAME, "vcl30.dpl"), "rb").read())
    for va, hexs in VCL_EXPECT.items():
        assert vcl.rd(va, len(hexs) // 2).hex() == hexs, f"vcl30 {va:#x} differs"
    vname = struct.unpack("<I", vcl.rd(VCL_TTIMER - 0x20, 4))[0]
    assert vcl.rd(vname, 7) == b"\x06TTimer", "TTimer VMT"
    assert struct.unpack("<I", vcl.rd(VCL_TTIMER - 0x1C, 4))[0] == 0x38, "TTimer instance size"
    assert vcl.rd(VCL_OPENDLG_CREATE, 3) == bytes.fromhex("535684"), "TOpenDialog.Create"


def kill_game():
    # SCRATCH GUARD: AOW_GAME_DIR set => not the real install; never kill the user's game.
    if os.environ.get("AOW_GAME_DIR"):
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match "
         "'^(AoW|AoWz|AoWCompat|AoWzCompat|AoWDevEd|AoWzEd|AoWEd|AoWSetup)$' } | Stop-Process -Force"],
        capture_output=True)


def main():
    mode = "apply" if "--apply" in sys.argv else "undo" if "--undo" in sys.argv else "dry"
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    data = bytearray(open(DLL, "rb").read())
    pe = PEFile(data)
    static_checks(pe)

    blob, na, nb, nh = build_cave(ks)
    hook_ours = b"\xE9" + struct.pack("<i", CAVE - (HOOK_VA + 5)) + b"\x90"
    assert blob[:2] == bytes.fromhex("85d2"), "hook_seteng is not at CAVE"

    hook_now = pe.rd(HOOK_VA, 6)
    const_now = pe.rd(SETMOD_CONST, 1)[0]
    cave_now = pe.rd(CAVE, len(blob))
    hook_st = "vanilla" if hook_now == HOOK_ORIG else "ours" if hook_now == hook_ours else "FOREIGN"
    const_st = {CONST_VANILLA: "vanilla", CONST_OURS: "ours"}.get(const_now, "FOREIGN")
    cave_st = ("empty" if cave_now == bytes(len(blob)) else "current" if cave_now == blob
               else "ours-stale" if cave_now[:2] == blob[:2] else "FOREIGN")
    print(f"HSEPack.dpl  hook {HOOK_VA:#x}: {hook_st}   SetModified const: {const_st}   "
          f"cave {CAVE:#x}: {cave_st}")
    print(f"  cave: head {na} B, tick {nb} B; every {AUTOSAVE_MINUTES} min, {SLOTS} slots, "
          f"<root>{DIR1.decode()}{DIR2.decode()}{FILE.decode()}")
    assert "FOREIGN" not in (hook_st, const_st, cave_st), "unexpected bytes -- refusing"

    if mode == "dry":
        cs = Cs(CS_ARCH_X86, CS_MODE_32)
        for start, n in ((CAVE, na), (SEH_RESTORE, nh), (TICK, nb)):
            for i in cs.disasm(blob[start - CAVE:start - CAVE + n], start):
                print(f"  {i.address:08X}  {i.bytes.hex():16s} {i.mnemonic} {i.op_str}")
        print("dry run -- --apply to write, --undo to revert")
        return 0

    if mode == "apply":
        if (hook_st, const_st, cave_st) == ("ours", "ours", "current"):
            print("already applied and current -- no-op")
            return 0
        new = [(CAVE, blob), (SETMOD_CONST, bytes([CONST_OURS])), (HOOK_VA, hook_ours)]
    else:
        if (hook_st, const_st, cave_st) == ("vanilla", "vanilla", "empty"):
            print("not applied -- no-op")
            return 0
        new = [(HOOK_VA, HOOK_ORIG), (SETMOD_CONST, bytes([CONST_VANILLA])),
               (CAVE, bytes(len(blob)))]
    for va, b in new:
        o = pe.off(va)
        data[o:o + len(b)] = b

    for attempt in (1, 2):
        try:
            open(DLL, "wb").write(data)
            break
        except PermissionError:
            if attempt == 2:
                print("HSEPack.dpl is locked -- close the editor and the game")
                return 1
            kill_game()
            import time; time.sleep(1.5)

    chk = PEFile(bytearray(open(DLL, "rb").read()))
    for va, b in new:
        assert chk.rd(va, len(b)) == b, f"verify failed at {va:#x}"
    print(f"{mode}: written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
