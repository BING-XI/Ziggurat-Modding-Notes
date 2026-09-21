#!/usr/bin/env python3
r"""
AoW1 editor PER-DIALOG-TYPE DIRECTORY MEMORY  --  binary patch for
AoWDevEd.exe + HSEPack.dpl.

PROBLEM
  Every file dialog in the editor (File>Open map, Developer>Open Mapset, the
  SaveAs dialogs, text import/export) opens in the same "last visited folder":
  none of them seed FileName/InitialDir, so they all fall back to Windows'
  per-application MRU folder (and the SaveAs pair seed InitialDir=GetCurrentDir,
  which the common dialog itself repoints on every pick). Scenario files and
  mapset/ruleset files live in different directories -> constant re-navigation.

WHAT IT DOES
  Each dialog *type* gets its own remembered path, persisted across sessions in
      <game dir>\AoWEd_LastDirs.ini   section [LastDirs], keys Map / Set / Text.
  - OPEN dialogs: before Execute, FFileName (+0x6C) := remembered full path and
    FInitialDir (+0x60) := its directory part -> dialog opens in that folder
    with the last-used file preselected. After a successful pick, the chosen
    path is written back to the INI.
  - SAVEAS dialogs (map + set): their `SetInitialDir(GetCurrentDir)` call is
    rerouted: if the INI has a remembered path for that type, its directory
    part is used instead of the CWD; else original behaviour. (When a map
    already has a full path, the VCL puts it in lpstrFile which wins anyway --
    i.e. SaveAs on an existing file still opens at that file's own folder.)
  - First run / missing INI key -> the engine's own data root for the Set
    dialogs (see below), exactly vanilla behaviour for Map/Text; the INI builds
    up as you use the dialogs. No INI file is created until a dialog is accepted.

  Dialog-type -> key map ("Map" is shared by exe-open and HSEPack map dialogs):
    Map : File>Open (exe), THSMEdit.Load, THSMEdit.SaveAs      (*.HSM)
    Set : Developer>Open Mapset (THSSEdit.Load), THSSEdit.SaveAs (*.HSS)
    Text: Export Text / Import Text / Export Ability Info (exe) (*.txt etc.)

v3 -- THE "Set" DIALOGS FALL BACK TO THE ENGINE'S DATA ROOT, NOT THE WINDOWS MRU
  Why this matters more than the other two keys: the editor writes every .PFS
  file to `ExtractFilePath(engine[+0x44])`, and engine[+0x44] is set by
  HSEngine.THSEngine.LoadHSS @0x5560F75C+0x2F (and SaveHSS @0x5560F970+0x71) to
  ExpandFileName(<the .hss the user picked>). So the mapset the Set dialog opens
  decides where Ability.pfs and its ten siblings are SAVED
  (AoWE.TAoWHSSet.ReadWrite @0x5574C528+0x86 is the consumer; the write is
  Engine.TEngine.WriteToFileCRC @0x5574C88F). Pick <root>\Release\Release.hss --
  the VANILLA tree's mapset -- and an ability edit lands in the vanilla install.
  That is exactly what happened on 2026-09-10, and the route in was the no-INI
  fallback: with no remembered Set path the dialog fell through to the Windows
  per-application folder MRU, which had the vanilla tree in it. Correcting the
  INI by hand fixes this install only; the trap re-arms on a fresh install or
  whenever AoWEd_LastDirs.ini is deleted. v3 closes it at the source.

  With no `Set` value in the INI, both Set dialogs now seed
      FInitialDir := <engine data root> + "Release\"
  which under the Ziggurat registry isolation is `<game>\Ziggurat\Release\`.
  An INI value still wins -- v3 only replaces the fallback.

  REACHING THE DATA ROOT, POSITION-INDEPENDENTLY
    Not via AoWEPACK's `AoWE.AoWEngine @0x558FA048`: HSEPack.dpl imports NOTHING
    from AoWEPACK.dpl (checked -- 0 descriptors), so the IAT-delta trick used for
    the VCL30 profile APIs has no anchor here, and AoWEPACK rebases too.
    Instead the engine comes off the instance the hook already has:
      edi = THSSEdit Self at BOTH Set hook sites
            (THSSEdit.Load   @0x55615E64+0x11  `mov edi,eax`)
            (THSSEdit.SaveAs @0x55615BF8+0x08  `mov edi,eax`)
      [edi+0x24] = THSSEdit.FHSEngine, written only by THSSEdit.SetHSEngine
            @0x55615AC8, which hands it to Engine.TEUser.Connect -> it is always
            a TEngine descendant. Both hosts null-check it before the hook runs
            (Load @0x55615E87, SaveAs @0x55615C12).
      [engine+0x2C] = Engine.TEngine.FStartupDirectory, an AnsiString. Declared
            in EngineP.dpl's TEngine (SetStartupDirectory @0x5551B658 writes
            `lea eax,[ebx+0x2c]; @LStrAsg`), i.e. THREE classes above TAoWEngine:
            TEObject -> TECustomNode -> TENode -> TEngine -> THSEngine (instsize
            0x58, HSEPack) -> TAoWEngine (instsize 0x80, AoWEPACK). So +0x2C is
            valid on any engine in any host, not just on a TAoWEngine.
      Trailing '\' is guaranteed: TAoWEngine.UpdateStartupDirectory @0x557982D0
            appends one if the registry value lacks it, and the base
            TEngine.UpdateStartupDirectory @0x5551B5F4 assigns
            ExtractFilePath(Application.ExeName), which keeps the delimiter.
            The cave verifies it anyway and refuses (-> vanilla) if absent.

    ⚠ `Map` must NOT reuse this. THSMEdit is an unrelated class (parent
    DisplayC.TDisplay, instsize 0x270, its own SetHSEngine @0x55613CD0), so
    [edi+0x24] there is not an engine. The engine fallback is gated on the
    module's `engfb` entry and on the key name, so it is emitted for `Set` only
    and AoWDevEd.exe's cave is byte-identical to v2.

  ⚠⚠ EVERY engdir FAILURE PATH FALLS BACK INTO THE TRAP THIS CLOSES. The "->
  exact vanilla" comments on them are accurate and misleading in the same breath:
  vanilla here IS the Windows per-application folder MRU, i.e. the thing that put
  an ability edit into <root>\Release\. Failing open is still the right design --
  failing closed would mean refusing to open the dialog -- but it means a silent
  partial failure looks exactly like no patch at all. The paths are:
    * engine or FStartupDirectory nil/empty, or no trailing '\'
    * data root >= 256 chars. maxroot = DIRBUF_CHARS - len("Release\")-1 = 255.
      Unreachable in practice rather than by construction: a 256-char root makes
      <root>Release\Ability.pfs exceed MAX_PATH, so the editor could not write
      there anyway. To close it by construction, raise DIRBUF_CHARS 0x108 -> 0x110
      (page slack is free) -- but that changes the cave, so classify() needs the
      current v3 bytes kept as a recognised generation first, or --apply will
      report `unknown` against the install and abort.
    * <data root>Release\ does not exist -- Win32 ignores a non-existent
      lpstrInitialDir outright. Nothing in the cave can detect this; it is not a
      bug, just the reason a passing static check is not a passing behaviour check.

WHERE THE INI PATH COMES FROM  (v2 -- this used to be a baked-in absolute path)
  v1 stored the *build machine's* full INI path as a literal in the cave. That
  leaks the packager's profile directory into two shipped binaries and breaks
  on every other install. v2 derives it at runtime instead:

      ensure_ini:  GetModuleFileNameA(NULL, PATHBUF, 0x104)
                   -> back-scan to the last '\'
                   -> append "AoWEd_LastDirs.ini"

  hModule = NULL is deliberate: it yields the *host process* image path, and all
  four hosts (AoWz / AoWzCompat / AoWzEd / AoWDevEd) live in Ziggurat\.
  HSEPack.dpl does not import GetModuleHandleA, so NULL is also the only option.
  The result is cached in PATHBUF; the loader-zeroed first byte is the "not yet
  built" flag, so there is no separate init flag and no init hook.

  ⚠ Do NOT "simplify" this to a bare relative "AoWEd_LastDirs.ini". The
  Get/WritePrivateProfileString APIs resolve a directory-less name against
  %WINDIR%: reads come back empty and writes land in C:\Windows or vanish into
  UAC virtualisation. That is the original bug wearing a different hat.
  ⚠ Do NOT use GetCurrentDirectoryA either -- the SaveAs common dialog repoints
  the process CWD on every pick, so the INI would wander. That is why the
  dirseed wrappers exist in the first place.

  WHERE IT HANGS OFF THE EXISTING WRAPPERS (no change to any *_common body)
    seed_Set    (hook 0x55615E96, THSSEdit.Load's `call TOpenDialog.Create`):
      after `mov ebx,<delta>`, `call engdir`; on success assign the result into
      FInitialDir (+0x60) straight away. seed_common then runs unchanged -- if
      the INI does hold a Set path it overwrites both FFileName and FInitialDir,
      so the INI still wins.
    dirseed_Set (hook 0x55615C5A, THSSEdit.SaveAs's `call SetInitialDir`):
      the wrapper already pushes the original InitialDir string (GetCurrentDir)
      and `dirseed_orig` pops it into edx for the tail call. On success engdir's
      result is stored over that stack slot, so the CWD fallback becomes the data
      root; the INI-hit path discards the slot as before. Nothing is refcounted
      either way -- the caller still owns and clears the GetCurrentDir string.
      (SaveAs also copies engine[+0x44] into FFileName at 0x55615C6C, which wins
      whenever a mapset is already open; this fallback is what you get when one
      is not.)
    ⚠ engdir may NOT build into the shared `buf`: dirseed_common overwrites buf
      with the profile read *before* `dirseed_orig` consumes the pushed pointer,
      which would hand SetInitialDir a run of NULs carrying the old length. Hence
      DIRBUF, its own static AnsiString, with its own StrRec.

HOOKS -- every site is a 5-byte `call <import thunk>` replaced 1:1 by
`call <cave wrapper>`; the wrapper calls the original thunk itself.

  AoWDevEd.exe (fixed base 0x400000):
    seed (call TOpenDialog.Create thunk 0x4019C8):
      0x429840 TMainForm.OpenBtnClick          key Map
      0x42B9AC TMainForm.ImportTextClick       key Text
      0x42B8AC TMainForm.ExportTextClick       key Text  (TSaveDialog, same ctor)
      0x42D436 TMainForm.ExportAbilityInfoClick key Text (TSaveDialog)
    persist (call TOpenDialog.GetFileName thunk 0x4019D0; first call after a
    successful Execute in each handler):
      0x429899 OpenBtnClick / 0x42B9DF ImportText / 0x42B8EC ExportText /
      0x42D488 ExportAbilityInfo

  HSEPack.dpl (preferred 0x55600000, REBASES -> cave is position-independent):
    seed (call Create thunk 0x55601A54):
      0x55615267 THSMEdit.Load   key Map
      0x55615E96 THSSEdit.Load   key Set
    dirseed (call TOpenDialog.SetInitialDir thunk 0x55601A64):
      0x55614D7E THSMEdit.SaveAs key Map
      0x55615C5A THSSEdit.SaveAs key Set
    persist (call GetFileName thunk 0x55601A5C):
      0x556152BD THSMEdit.Load / 0x55614E65 THSMEdit.SaveAs (the post-save one)
      0x55615EE5 THSSEdit.Load / 0x55615C8E THSSEdit.SaveAs

  Ziggurat\HSEPack.dpl is also loaded by AoWz.exe / AoWzCompat.exe / AoWzEd.exe.
  The patched functions are editor-only entry points -- an import-table scan
  confirms only AoWDevEd.exe and AoWzEd.exe import THSSEdit.Load/.SaveAs at all,
  AoWz.exe/AoWzCompat.exe and every .dpl import zero THS?Edit symbols -- and the
  cave is fully self-contained + host-agnostic (no absolute exe addresses), so
  riding along in the game is inert.
  ⚠ AoWEd.exe does NOT get this for free. It exists only at the game ROOT, has 6
  sections and no .dlgd, and it loads the ROOT's vanilla HSEPack.dpl, so it gets
  nothing at all from this patch. (An earlier version of this note claimed the
  opposite; it was written when the exes lived at the root and shared one DLL.)

⚠ THE LIVE EDITOR IS Ziggurat\AoWzEd.exe, WHICH THIS SCRIPT DOES NOT TOUCH
  MODULES targets AoWDevEd.exe, the patch *source*; build_zigeditor.py copies it
  wholesale to AoWzEd.exe and re-skins the icon, which is what the owner runs.
  Measured 2026-09-11: the two differ by 4396 bytes in 1224 runs, ALL inside .rsrc
  (the purple-dragon icon) -- but `.dlgd` raw 0xDC200..0xDC600 is identical and all
  8 exe call sites point into the cave in AoWzEd.exe too, as they do in the third
  copy at the game root (<root>\AoWDevEd.exe is byte-identical to the Ziggurat one).
  So the exe half is live in all three today and v3 changed no exe byte -- nothing
  needs propagating right now. That is luck, not design:

      python build_dlgdirs.py --apply      # or --undo
      python build_zigeditor.py --apply    # <-- ALWAYS, if the exe half changed

  ⚠⚠ In particular `--undo` restores the 8 call sites in Ziggurat\AoWDevEd.exe and
  leaves the 8 in Ziggurat\AoWzEd.exe patched, pointing into a cave that is still
  there but inert. Four sibling editor scripts (build_editor_autosave.py,
  build_editor_spinners.py, build_deved_levelnav.py, build_editor_framerate.py)
  open their docstrings with the same two-step; this one did not, which is the
  whole reason it is spelled out here.

HOW THE CAVES REACH kernel32
  * Profile APIs (neither module imports them). VCL30.dpl contains the IniFiles
    unit, so *its* import table has GetPrivateProfileStringA /
    WritePrivateProfileStringA. Both patched modules import
    VCL30!Dialogs.TOpenDialog.Create, so at runtime:
      vcl_delta = [own IAT slot holding &TOpenDialog.Create] - 0x4137AFB0
                   (0x4137AFB0 = Create's preferred VA inside VCL30.dpl)
      GetPrivateProfileStringA = [0x413E43B8 + vcl_delta]   (VCL30 IAT slot)
      WritePrivateProfileStringA = [0x413E42F8 + vcl_delta] (VCL30 IAT slot)
    IAT slot VAs verified against the VCL30.dpl shipped with the game.
    Own IAT slot: AoWDevEd.exe 0x432598, HSEPack.dpl 0x556308DC.
  * GetModuleFileNameA needs none of that -- BOTH modules already import it
    natively from kernel32 and already carry a Delphi import thunk:
      HSEPack.dpl   thunk 0x556011D8 = jmp dword ptr [0x55630550]
      AoWDevEd.exe  thunk 0x00401158 = jmp dword ptr [0x00432164]
    Both kernel32 descriptors are FirstThunk-only with TimeDateStamp = 0 and
    there is no Bound Import directory, so the loader always resolves them.
    The cave just does `call <thunk>` (rel32, PIC, no new imports). The script
    re-derives thunk -> IAT slot -> imported name from the import table on every
    run and aborts if it does not resolve to kernel32!GetModuleFileNameA --
    the addresses above are documentation, not the source of truth.
  ⚠ Do NOT add an import descriptor / IAT entry to either module for this. It
    was tried and rejected (see Zig notes/Editor_Modernization_DialogDirs_Toolbar.md,
    "Failed approach avoided") and is moot anyway: the API is already imported.

STRING HANDOFF to the VCL
  The INI read buffer doubles as a Delphi 3 static AnsiString:
  [buf-8]=refcount -1 (immutable), [buf-4]=length (set after each read).
  System.@LStrAsg copies when source refcount<0 (verified in VCL30 disasm), so
  assigning it into FFileName/FInitialDir is safe; SetInitialDir copies too.

  Delphi register ABI: eax/ecx/edx caller-saved, ebx/esi/edi callee-saved --
  the caves push/pop ebx/esi/edi and only rely on eax across the orig thunks.
  kernel32 APIs are stdcall (callee-cleaned, ebx/esi/edi preserved).
  ⚠ ecx holds &key and is LIVE at all three ensure_ini call sites, and edx holds
  the picked AnsiString at the save_common one -- so ensure_ini saves and
  restores ecx/edx/esi/edi itself and returns only in eax.

CAVE PLACEMENT
  PE section ".dlgd" (chars 0xE0000060: code+data, exec+read+WRITE).
    HSEPack.dpl   RVA 0x4E000  raw 0x048200  rsz 0x400  cave VA 0x5564E000
    AoWDevEd.exe  RVA 0xE0000  raw 0x0DC200  rsz 0x400  cave VA 0x004E0000
  The HSEPack cave uses one call/pop helper for its own rebase delta; every data
  reference is [reg+disp32] and every call is rel32 -> no .reloc entries needed
  (and .dlgd has none, which matters: .reloc cannot be extended in place).

  ⚠ .dlgd is NOT the last section any more (.rgt follows it in HSEPack.dpl,
  .mtb + 4 more in AoWDevEd.exe). Therefore:
    - SizeOfRawData stays 0x400 and the file size never changes. Growing raw
      would shift every later section's PointerToRawData and invalidate five
      other features' recorded addresses.
    - SizeOfImage is NOT touched (0x50000 / 0x193000 are correct as they stand;
      they are derived from the LAST section, not from .dlgd).
    - The 288-byte PATHBUF therefore lives in the section's PAGE SLACK at
      cave+0x400 (3072 bytes free up to the next section's page), and the only
      header field this script edits on a rewrite is .dlgd's VirtualSize,
      0x321/0x28E -> 0x520 (= 0x400 + 0x120) -> 0x630 in HSEPack.dpl once v3's
      DIRBUF is claimed. The loader zero-fills virtual bytes past SizeOfRawData,
      which is what makes "first byte == 0" a valid one-shot init flag for
      PATHBUF. DIRBUF does not lean on that -- engdir writes its own StrRec
      (refcount -1 + length) on every call.
    - .dlgd spans a full page of virtual space in both modules (HSEPack .dlgd
      RVA 0x4E000, next section .rgt RVA 0x4F000; AoWDevEd .dlgd RVA 0xE0000,
      next .mtb RVA 0xE1000), so a VirtualSize up to 0x1000 cannot overlap the
      next section. process() asserts that before writing it.

  ADDRESSES CLAIMED BY THIS FEATURE (listed literally so that the project's
  `grep -rl "<VA>" "Modding Resources/build_scripts/"` collision check finds
  them -- the script itself computes them, so they appear nowhere else):
      HSEPack.dpl   cave 0x5564E000 .. 0x5564E630   PATHBUF 0x5564E400 (0x120 B)
                                                    DIRBUF  0x5564E520 (0x110 B,
                                                    StrRec at 0x5564E520, chars
                                                    at 0x5564E528)
      AoWDevEd.exe  cave 0x004E0000 .. 0x004E0520   PATHBUF 0x004E0400 (0x120 B)
  Free page slack still unclaimed: 0x5564E630..0x5564EFFF (2512 B) and
  0x004E0524..0x004E0FFF (2780 B).
  ⚠⚠ `build_deved_gamesettings_tab.py` (2026-09-12) owns the dword at 0x004E0520
  in AoWDevEd.exe -- adjacent to PATHBUF, not overlapping it, ONLY because this
  module's entry has `engfb=None`.  Giving AoWDevEd.exe an `engfb` entry puts
  DIRBUF's StrRec at DIRBUF_OFF = PATHBUF_OFF + PATHBUF_SIZE = 0x520, exactly on
  top of it.  If that is ever wanted, move that script's G_GSDLG to 0x004E0630+
  first.

  ⚠ The HSEPack cave is now 990 of 0x400 RAW bytes -- 34 spare. SizeOfRawData
  cannot grow (.rgt follows at raw 0x048600), so the next feature that needs
  code here has to free some first. The obvious 264 bytes: the profile read
  buffer `buf` is runtime-only scratch and could move to page slack the way
  DIRBUF did, leaving only its 8-byte StrRec behind. That changes the data
  layout, so classify()'s v1 probe (which reads `pathstr` at a fixed offset out
  of the installed bytes) has to be re-checked at the same time.

  ⚠ ensure_ini is not thread-safe: a second thread that reads the flag byte
  while the first is mid-`rep movsb` would see a half-built path. Every call
  site is VCL modal-dialog code on the main UI thread, and the failure mode is
  benign (the profile API rejects the path -> vanilla behaviour), so this is
  left alone deliberately rather than guarded.

CONVENTIONS: dry-run by default; --apply to write; idempotent (re-run
verifies); verify-before-write aborts on byte mismatch. Close AoW / AoWCompat /
AoWDevEd / AoWEd before --apply (all of them lock HSEPack.dpl).

REVERT: use `--undo`. It is surgical -- it restores all 16 call sites to the
original import thunks, zeroes the 0x400 cave bytes, and puts .dlgd's
VirtualSize back to 0x400. It touches no backup file and leaves the (now inert,
all-zero) .dlgd section entry in place, so a later --apply can reuse it without
shifting any section header.
Do not use "revert and re-apply" as a re-tune procedure: --apply rewrites the cave
in place instead (it accepts the currently-installed v1, v2 *or* v3 bytes and
overwrites any of them).
SNAPSHOTS: --apply mints one, gated on a positive test of the exact state it is
about to overwrite -- `<game dir>\backups\<file>.pre-dlgdirs` (fresh install, no
.dlgd and all 16 sites vanilla), `.pre-dlgdirs2` (over a proven-v1 install) or
`.pre-dlgdirs3` (over a proven-v2 install). `--undo` and the `undone` state mint
nothing: process() returns from the undo branch long before the backup block, so
a snapshot can never capture this script's own output.
⚠ As of 2026-09-11 exactly one exists: `Ziggurat\backups\HSEPack.dpl.pre-dlgdirs3`
= the v2 install. There is none for AoWDevEd.exe and none for v1, because the two
older stacks were purged (2026-08-08 and 2026-09-09). Do not plan a revert around
copying a snapshot -- `--undo` is the revert path.

Usage:
  python build_dlgdirs.py            # dry-run / verify current state
  python build_dlgdirs.py --disasm   # dump the cave disassembly it would write
  python build_dlgdirs.py --apply    # patch both
  python build_dlgdirs.py --undo     # surgical revert of both
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_SUFFIX  = ".pre-dlgdirs"    # only ever written on a FRESH install (no .dlgd)
BACKUP_SUFFIX2 = ".pre-dlgdirs2"   # only ever written over a proven-v1 install
BACKUP_SUFFIX3 = ".pre-dlgdirs3"   # only ever written over a proven-v2 install
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)
SECT_NAME = b".dlgd\0\0\0"

# The INI file NAME only -- never a path. ensure_ini prepends the host exe's
# own directory at runtime. Deliberately a bare name so that no absolute path
# can end up in the binary even by accident.
INI_NAME    = "AoWEd_LastDirs.ini"          # 18 chars + NUL = 19 bytes
INI_SECTION = "LastDirs"

# PATHBUF lives in .dlgd's page slack, past SizeOfRawData (0x400) but inside
# VirtualSize (0x520). Loader-zeroed, writable, costs zero file bytes.
PATHBUF_OFF  = 0x400
PATHBUF_SIZE = 0x120                        # 288: 259-char dir + 18 + NUL = 278 worst case
DLGD_RSIZE   = 0x400                        # never grows -- .dlgd is not the last section
MAXDIR       = PATHBUF_SIZE - (len(INI_NAME) + 1)   # 269

# DIRBUF: the engine-data-root AnsiString (v3), also in page slack, right after
# PATHBUF. 8-byte Delphi StrRec at DIRBUF_OFF, chars at DIRBUF_OFF+8. Unlike
# PATHBUF it does NOT rely on the loader's zero-fill -- engdir writes refcount
# -1 and the length itself on every call. Only modules with an `engfb` entry
# carry it, so AoWDevEd.exe's VirtualSize stays 0x520.
DIRBUF_OFF   = PATHBUF_OFF + PATHBUF_SIZE   # 0x520 (StrRec)
DIRBUF_CHARS = 0x108                        # same capacity as the profile `buf`
DIRBUF_SIZE  = 8 + DIRBUF_CHARS             # 0x110 -> ends at 0x630
SECT_VSPACE  = 0x1000                       # .dlgd owns one full page in both modules

def dlgd_vsize(M):
    """VirtualSize .dlgd needs in this module: PATHBUF always, DIRBUF only where
    the engine fallback is emitted."""
    end = DIRBUF_OFF + DIRBUF_SIZE if M.get("engfb") else PATHBUF_OFF + PATHBUF_SIZE
    assert end <= SECT_VSPACE, "page slack exhausted -- would run into the next section"
    return end

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

# ---- VCL30.dpl facts (verified against the shipped VCL30.dpl) ----------------
VCL_CREATE_PREF = 0x4137AFB0   # Dialogs.TOpenDialog.Create preferred VA
VCL_GPPS_SLOT   = 0x413E43B8   # VCL30 IAT slot: kernel32!GetPrivateProfileStringA
VCL_WPPS_SLOT   = 0x413E42F8   # VCL30 IAT slot: kernel32!WritePrivateProfileStringA
OFF_FILENAME    = 0x6C         # TOpenDialog.FFileName   (RTTI-verified)
OFF_INITIALDIR  = 0x60         # TOpenDialog.FInitialDir (RTTI-verified)

# ---- engine facts (v3) --------------------------------------------------------
# Engine.TEngine.FStartupDirectory: AnsiString, always ends in '\'. Declared in
# EngineP.dpl (SetStartupDirectory @0x5551B658 does `lea eax,[ebx+0x2c]`), so it
# is inherited by THSEngine (HSEPack) and TAoWEngine (AoWEPACK) alike.
OFF_STARTUPDIR  = 0x2C

# ---- per-module facts ---------------------------------------------------------
# sites: (kind, va, key)  kind in {seed, save, dirseed}
MODULES = {
    "AoWDevEd.exe": dict(
        ib=0x400000,
        thunk_create=0x4019C8, thunk_getfn=0x4019D0,
        thunk_setinidir=None,               # exe has no SetInitialDir import (unused)
        thunk_lstrasg=0x4010C0,
        thunk_gmfn=0x00401158,              # jmp [0x432164] -> kernel32!GetModuleFileNameA
        gmfn_slot=0x00432164,               # re-derived + asserted at run time
        vcl_slot=0x432598,                  # IAT slot: VCL30!Dialogs.TOpenDialog.Create
        engfb=None,                         # no Set dialog here -> cave identical to v2
        keys=("Map", "Text"),
        sites=[
            ("seed", 0x429840, "Map"),   ("save", 0x429899, "Map"),
            ("seed", 0x42B9AC, "Text"),  ("save", 0x42B9DF, "Text"),
            ("seed", 0x42B8AC, "Text"),  ("save", 0x42B8EC, "Text"),
            ("seed", 0x42D436, "Text"),  ("save", 0x42D488, "Text"),
        ],
    ),
    "HSEPack.dpl": dict(
        ib=0x55600000,
        thunk_create=0x55601A54, thunk_getfn=0x55601A5C,
        thunk_setinidir=0x55601A64,
        thunk_lstrasg=0x55601130,
        thunk_gmfn=0x556011D8,              # jmp [0x55630550] -> kernel32!GetModuleFileNameA
        gmfn_slot=0x55630550,               # re-derived + asserted at run time
        vcl_slot=0x556308DC,
        # v3 engine-data-root fallback. `self_reg` is the register the HOST
        # function leaves Self in at BOTH Set hook sites (Load 0x55615E64+0x11,
        # SaveAs 0x55615BF8+0x08 both do `mov edi,eax`) and which neither the
        # seed nor the dirseed wrapper overwrites before engdir runs.
        # ⚠ off_self_engine is a THSSEdit offset ONLY -- THSMEdit is a different
        # class, which is why this is keyed to "Set".
        engfb=dict(key="Set", self_reg="edi", off_self_engine=0x24,
                   sub="Release\\"),
        keys=("Map", "Set"),
        sites=[
            ("seed",    0x55615267, "Map"), ("save", 0x556152BD, "Map"),
            ("dirseed", 0x55614D7E, "Map"), ("save", 0x55614E65, "Map"),
            ("seed",    0x55615E96, "Set"), ("save", 0x55615EE5, "Set"),
            ("dirseed", 0x55615C5A, "Set"), ("save", 0x55615C8E, "Set"),
        ],
    ),
}

# ---- PE helpers ----------------------------------------------------------------
def load_sections(d):
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e+6)[0]
    optsz = struct.unpack_from('<H', d, e+20)[0]
    opt = e+24
    sectbl = opt+optsz
    secs = []
    for i in range(nsec):
        b = sectbl+i*40
        vsz, va, rsz, raw = struct.unpack_from('<IIII', d, b+8)
        secs.append((va, vsz, raw, rsz, b))
    return dict(e=e, nsec=nsec, opt=opt,
                salign=struct.unpack_from('<I', d, opt+32)[0],
                falign=struct.unpack_from('<I', d, opt+36)[0],
                sectbl=sectbl, secs=secs)

def align(x, a): return (x + a - 1) // a * a

def va2off(secs, va, ib):
    """VA -> file offset. Refuses addresses past a section's raw data (which is
    exactly where PATHBUF lives once VirtualSize > SizeOfRawData)."""
    r = va - ib
    for va0, vsz, raw, rsz, _ in secs:
        if va0 <= r < va0 + max(vsz, rsz):
            delta = r - va0
            if delta >= rsz:
                raise ValueError(f"VA 0x{va:08X} is in a section's virtual tail, "
                                 f"not backed by file bytes")
            return raw + delta
    raise ValueError(hex(va))

def find_section(d, F, name5):
    for va, vsz, raw, rsz, b in F["secs"]:
        if bytes(d[b:b+5]) == name5:
            return (va, vsz, raw, rsz, b)
    return None

def rel32(src, dst): return struct.pack('<i', dst - (src + 5))

def cstr(d, o):
    e = d.index(b'\0', o)
    return d[o:e].decode('latin1')

# ---- import-table verification -------------------------------------------------
def assert_gmfn_thunk(d, F, name, M):
    """Prove M['thunk_gmfn'] is `jmp dword ptr [slot]` and that the slot is
    kernel32!GetModuleFileNameA -- parsed from the import table, never assumed."""
    secs, ib, opt = F["secs"], M["ib"], F["opt"]

    def r2o(rva):
        for va0, vsz, raw, rsz, _ in secs:
            if va0 <= rva < va0 + max(vsz, rsz) and (rva - va0) < rsz:
                return raw + (rva - va0)
        raise ValueError(f"rva 0x{rva:X}")

    dd = opt + 96
    imp_rva = struct.unpack_from('<I', d, dd + 8)[0]
    bnd_rva, bnd_sz = struct.unpack_from('<II', d, dd + 11*8)
    if bnd_rva or bnd_sz:
        return f"{name}: unexpected Bound Import directory (0x{bnd_rva:X}/0x{bnd_sz:X})"

    slot_rva = M["gmfn_slot"] - ib
    o, i, found = r2o(imp_rva), 0, None
    while True:
        oft, tds, fc, nm_rva, ft = struct.unpack_from('<IIIII', d, o + i*20)
        if not (oft or tds or fc or nm_rva or ft):
            break
        dll = cstr(d, r2o(nm_rva))
        arr = oft if oft else ft
        to, j = r2o(arr), 0
        while True:
            v = struct.unpack_from('<I', d, to + j*4)[0]
            if v == 0:
                break
            if ft + j*4 == slot_rva:
                if v & 0x80000000:
                    return f"{name}: IAT slot 0x{M['gmfn_slot']:08X} is import-by-ordinal"
                found = (dll, cstr(d, r2o(v + 2)), tds)
            j += 1
        i += 1

    if found is None:
        return f"{name}: IAT slot 0x{M['gmfn_slot']:08X} is not in any import descriptor"
    dll, fn, tds = found
    if dll.lower() != "kernel32.dll" or fn != "GetModuleFileNameA":
        return (f"{name}: IAT slot 0x{M['gmfn_slot']:08X} resolves to "
                f"{dll}!{fn}, expected kernel32.dll!GetModuleFileNameA")
    if tds != 0:
        return f"{name}: kernel32 descriptor TimeDateStamp = 0x{tds:X} (expected 0, unbound)"

    exp = b"\xFF\x25" + struct.pack('<I', M["gmfn_slot"])
    got = bytes(d[va2off(secs, M["thunk_gmfn"], ib):][:6])
    if got != exp:
        return (f"{name}: thunk 0x{M['thunk_gmfn']:08X} is not "
                f"`jmp dword ptr [0x{M['gmfn_slot']:08X}]`\n"
                f"     exp {exp.hex(' ')}  got {got.hex(' ')}")
    return None

# ---- cave construction ---------------------------------------------------------
# Layout: [code][pad4][refcnt -1][len][buf 0x108][sect][keys...][empty][pathstr]
#         [sub]   <- v3, only where M["engfb"]
# plus PATHBUF at cave+0x400 and (v3) DIRBUF at cave+0x520, both in page slack
# and neither part of the blob.
# All addresses in the asm are PREFERRED VAs; at runtime the ebx delta (from the
# call/pop helper) corrects them. In the exe the delta is simply 0.
#
# gen=3 -> current: v2 plus the engine-data-root fallback (engfb modules only)
# gen=2 -> the cave as shipped before the fallback existed; kept so that
#          --apply can verify the bytes it is about to overwrite
# gen=1 -> legacy="<abs path>": reproduce the v1 cave byte-for-byte (pathstr =
#          that absolute path, no ensure_ini), same reason.
# For a module with engfb=None gen 3 and gen 2 are byte-identical by construction.

def build_cave(cave_va, M, gen=3, legacy=None):
    keys = M["keys"]
    if legacy is not None:
        gen = 1
    v2 = gen >= 2
    engfb = M.get("engfb") if gen >= 3 else None
    pathstr = INI_NAME if v2 else legacy

    def asm_source(D):
        # D maps symbolic names -> preferred VAs (dummies on pass 1)
        s = f"""
        /* ---- getdelta: eax := runtime - preferred (module rebase delta) ---- */
        getdelta:
            call gd1
        gd1: pop eax
            sub eax, 0x{D['gd1']:08X}
            ret
        """
        if v2:
            # ---- ensure_ini: build "<host exe dir>\\AoWEd_LastDirs.ini" once ----
            # in : ebx = module delta.  out: eax = &PATHBUF, or 0 on failure.
            # preserves ecx (live: &key), edx (live: picked string), esi, edi.
            s += f"""
        ensure_ini:
            cmp byte ptr [ebx + 0x{D['pathbuf']:08X}], 0
            jne ei_have                         /* already built (loader-zeroed = flag) */
            push ecx
            push edx
            push esi
            push edi
            push 0x104                          /* nSize */
            lea eax, [ebx + 0x{D['pathbuf']:08X}]
            push eax                            /* lpFilename */
            push 0                              /* hModule = NULL -> host exe path */
            call 0x{M['thunk_gmfn']:08X}        /* GetModuleFileNameA (stdcall, cleans 12) */
            test eax, eax
            jz ei_fail
            cmp eax, 0x104
            jae ei_fail                         /* truncated */
            mov ecx, eax
        ei_scan:
            dec ecx
            js ei_fail                          /* no backslash -> give up */
            cmp byte ptr [ebx + ecx + 0x{D['pathbuf']:08X}], 0x5C
            jne ei_scan
            inc ecx                             /* ecx = dir length incl. trailing '\\' */
            cmp ecx, 0x{MAXDIR:X}
            ja ei_fail                          /* would overrun PATHBUF */
            lea edi, [ebx + ecx + 0x{D['pathbuf']:08X}]
            lea esi, [ebx + 0x{D['pathstr']:08X}]
            mov ecx, 0x{len(INI_NAME)+1:X}      /* "AoWEd_LastDirs.ini" incl. NUL */
            cld                                 /* rep movsb needs DF=0 */
            rep movsb
            pop edi
            pop esi
            pop edx
            pop ecx
        ei_have:
            lea eax, [ebx + 0x{D['pathbuf']:08X}]
            ret
        ei_fail:
            mov byte ptr [ebx + 0x{D['pathbuf']:08X}], 0   /* clear flag, allow a retry */
            pop edi
            pop esi
            pop edx
            pop ecx
            xor eax, eax
            ret
        """
        if engfb:
            # ---- engdir: build "<engine data root>Release\\" into DIRBUF -------
            # in : ebx = module delta, edi = THSSEdit Self (the host leaves it
            #      there at both Set hook sites and no wrapper clobbers it).
            # out: eax = &DIRBUF, a static AnsiString, or 0 -> caller does nothing.
            # clobbers eax/ecx/edx only (ebx/esi/edi preserved).
            maxroot = DIRBUF_CHARS - (len(engfb["sub"]) + 1)
            s += f"""
        engdir:
            mov eax, [{engfb['self_reg']} + 0x{engfb['off_self_engine']:02X}]  /* THSSEdit.FHSEngine */
            test eax, eax
            jz engdir_fail                      /* no engine -> exact vanilla */
            mov edx, [eax + 0x{OFF_STARTUPDIR:02X}]  /* TEngine.FStartupDirectory */
            test edx, edx
            jz engdir_fail                      /* '' (nil) -> exact vanilla */
            mov ecx, [edx - 4]                  /* AnsiString length */
            dec ecx
            js engdir_fail                      /* length 0 */
            cmp byte ptr [edx + ecx], 0x5C
            jne engdir_fail                     /* no trailing '\\' -> refuse */
            inc ecx
            cmp ecx, 0x{maxroot:X}
            ja engdir_fail                      /* would overrun DIRBUF */
            push esi
            push edi
            mov esi, edx
            lea edi, [ebx + 0x{D['dirbuf']:08X}]
            lea eax, [ecx + 0x{len(engfb['sub']):X}]
            mov [edi - 4], eax                  /* StrRec.length = root + sub */
            mov dword ptr [edi - 8], -1         /* StrRec.refcount: immutable */
            mov eax, edi                        /* keep &DIRBUF across the copies */
            cld                                 /* rep movsb needs DF=0 */
            rep movsb                           /* <data root>, trailing '\\' incl. */
            lea esi, [ebx + 0x{D['sub']:08X}]
            mov ecx, 0x{len(engfb['sub'])+1:X}
            rep movsb                           /* "{engfb['sub']}" incl. NUL */
            pop edi
            pop esi
            ret
        engdir_fail:
            xor eax, eax
            ret
        """
        # seed wrappers + common (Create sites)
        for k in keys:
            s += f"""
        seed_{k}:
            call 0x{M['thunk_create']:08X}      /* original ctor; eax = dialog */
            push ebx
            push esi
            mov esi, eax
            call getdelta
            mov ebx, eax
            """
            if engfb and k == engfb["key"]:
                # pre-seed FInitialDir from the engine data root; seed_common
                # still overwrites it when the INI holds a path for this key.
                s += f"""
            call engdir
            test eax, eax
            jz seed_nofb_{k}
            mov edx, eax
            lea eax, [esi + 0x{OFF_INITIALDIR:02X}]
            call 0x{M['thunk_lstrasg']:08X}     /* FInitialDir := data root */
        seed_nofb_{k}:
            """
            s += f"""
            lea ecx, [ebx + 0x{D['key'+k]:08X}]
            jmp seed_common
        """
        if v2:
            seed_pre = """
            call ensure_ini
            test eax, eax
            jz seed_done                        /* no INI path -> exact vanilla */
            push eax
            """
        else:
            seed_pre = f"""
            lea eax, [ebx + 0x{D['pathstr']:08X}]
            push eax
            """
        s += f"""
        seed_common:            /* esi=dialog ebx=delta ecx=&key */
            {seed_pre}
            push 0x104
            lea eax, [ebx + 0x{D['buf']:08X}]
            push eax
            lea eax, [ebx + 0x{D['empty']:08X}]
            push eax
            push ecx
            lea eax, [ebx + 0x{D['sect']:08X}]
            push eax
            mov eax, [ebx + 0x{M['vcl_slot']:08X}]
            sub eax, 0x{VCL_CREATE_PREF:08X}
            mov eax, [eax + 0x{VCL_GPPS_SLOT:08X}]
            call eax                            /* GetPrivateProfileStringA -> eax=len */
            test eax, eax
            jz seed_done
            cmp eax, 0x103
            jae seed_done                       /* truncated -> ignore */
            mov [ebx + 0x{D['len']:08X}], eax
            lea eax, [esi + 0x{OFF_FILENAME:02X}]
            lea edx, [ebx + 0x{D['buf']:08X}]
            call 0x{M['thunk_lstrasg']:08X}     /* FFileName := remembered path */
            mov ecx, [ebx + 0x{D['len']:08X}]
        seed_scan:
            dec ecx
            js seed_done                        /* no backslash -> skip InitialDir */
            cmp byte ptr [ebx + ecx + 0x{D['buf']:08X}], 0x5C
            jne seed_scan
            inc ecx
            mov [ebx + 0x{D['len']:08X}], ecx   /* len = dir incl. trailing '\\' */
            lea eax, [esi + 0x{OFF_INITIALDIR:02X}]
            lea edx, [ebx + 0x{D['buf']:08X}]
            call 0x{M['thunk_lstrasg']:08X}     /* FInitialDir := dir part */
        seed_done:
            mov eax, esi                        /* return the dialog */
            pop esi
            pop ebx
            ret
        """
        # save wrappers + common (GetFileName sites)
        for k in keys:
            s += f"""
        save_{k}:
            push ebx
            push esi
            push edi
            mov esi, edx                        /* @out string var */
            mov edi, eax                        /* dialog */
            call getdelta
            mov ebx, eax
            lea ecx, [ebx + 0x{D['key'+k]:08X}]
            jmp save_common
        """
        if v2:
            save_pre = """
            call ensure_ini                     /* preserves ecx=&key, edx=string */
            test eax, eax
            jz save_done                        /* no INI path -> exact vanilla */
            push eax
            """
        else:
            save_pre = f"""
            lea eax, [ebx + 0x{D['pathstr']:08X}]
            push eax
            """
        s += f"""
        save_common:            /* esi=@out edi=dialog ebx=delta ecx=&key */
            push ecx
            mov eax, edi
            mov edx, esi
            call 0x{M['thunk_getfn']:08X}       /* original GetFileName */
            pop ecx
            mov edx, [esi]                      /* AnsiString ptr (0 if empty) */
            test edx, edx
            jz save_done
            {save_pre}
            push edx
            push ecx
            lea eax, [ebx + 0x{D['sect']:08X}]
            push eax
            mov eax, [ebx + 0x{M['vcl_slot']:08X}]
            sub eax, 0x{VCL_CREATE_PREF:08X}
            mov eax, [eax + 0x{VCL_WPPS_SLOT:08X}]
            call eax                            /* WritePrivateProfileStringA */
        save_done:
            pop edi
            pop esi
            pop ebx
            ret
        """
        # dirseed wrappers + common (SetInitialDir sites; HSEPack only)
        if M["thunk_setinidir"]:
            for k in keys:
                s += f"""
        dirseed_{k}:
            push ebx
            push esi
            push edi
            mov esi, eax                        /* dialog */
            push edx                            /* original InitialDir string */
            call getdelta
            mov ebx, eax
            """
                if engfb and k == engfb["key"]:
                    # swap the CWD fallback for the data root; dirseed_orig pops
                    # whatever is in that slot, the INI-hit path discards it.
                    s += f"""
            call engdir
            test eax, eax
            jz dirseed_nofb_{k}
            mov [esp], eax                      /* replace GetCurrentDir result */
        dirseed_nofb_{k}:
            """
                s += f"""
            lea ecx, [ebx + 0x{D['key'+k]:08X}]
            jmp dirseed_common
        """
            if v2:
                dir_pre = """
            call ensure_ini
            test eax, eax
            jz dirseed_orig                     /* no INI path -> exact vanilla */
            push eax
                """
            else:
                dir_pre = f"""
            lea eax, [ebx + 0x{D['pathstr']:08X}]
            push eax
                """
            s += f"""
        dirseed_common:         /* esi=dialog ebx=delta ecx=&key [esp]=orig edx */
            {dir_pre}
            push 0x104
            lea eax, [ebx + 0x{D['buf']:08X}]
            push eax
            lea eax, [ebx + 0x{D['empty']:08X}]
            push eax
            push ecx
            lea eax, [ebx + 0x{D['sect']:08X}]
            push eax
            mov eax, [ebx + 0x{M['vcl_slot']:08X}]
            sub eax, 0x{VCL_CREATE_PREF:08X}
            mov eax, [eax + 0x{VCL_GPPS_SLOT:08X}]
            call eax
            test eax, eax
            jz dirseed_orig
            cmp eax, 0x103
            jae dirseed_orig
            mov ecx, eax
        dirseed_scan:
            dec ecx
            js dirseed_orig                     /* no backslash -> keep orig */
            cmp byte ptr [ebx + ecx + 0x{D['buf']:08X}], 0x5C
            jne dirseed_scan
            inc ecx
            mov [ebx + 0x{D['len']:08X}], ecx
            pop edx                             /* discard original CWD string */
            lea edx, [ebx + 0x{D['buf']:08X}]
            jmp dirseed_call
        dirseed_orig:
            pop edx                             /* original InitialDir */
        dirseed_call:
            mov eax, esi
            pop edi
            pop esi
            pop ebx
            jmp 0x{M['thunk_setinidir']:08X}    /* tail: original SetInitialDir */
        """
        return s

    # pass 1: dummy data VAs (all >0x10000000 so operand sizes are stable)
    dummy = dict(gd1=0x11111111, pathstr=0x11111112, buf=0x11111113,
                 empty=0x11111114, sect=0x11111115, len=0x11111116,
                 pathbuf=0x11111117, sub=0x11111118, dirbuf=0x11111119)
    for k in keys:
        dummy["key"+k] = 0x11111100
    code0, _ = ks.asm(asm_source(dummy), cave_va)
    code_len = len(code0)

    # data layout after code
    off = align(code_len, 4)
    lay = {}
    lay['refcnt'] = off;            off += 4
    lay['len'] = off;               off += 4
    lay['buf'] = off;               off += 0x108
    lay['sect'] = off;              off += len(INI_SECTION) + 1
    for k in keys:
        lay['key'+k] = off;         off += len(k) + 1
    lay['empty'] = off;             off += 1
    lay['pathstr'] = off;           off += len(pathstr) + 1
    if engfb:
        lay['sub'] = off;           off += len(engfb["sub"]) + 1

    D = {n: cave_va + o for n, o in lay.items()}
    D['gd1'] = cave_va + 5          # gd1 label = getdelta+5 (call rel32 is 5 bytes)
    D['pathbuf'] = cave_va + PATHBUF_OFF
    D['dirbuf'] = cave_va + DIRBUF_OFF + 8   # chars; StrRec sits at [-8]/[-4]
    code, _ = ks.asm(asm_source(D), cave_va)
    code = bytes(code)
    assert len(code) == code_len, "cave length changed between passes"

    blob = bytearray(code)
    blob += b"\x00" * (lay['refcnt'] - len(blob))
    blob += struct.pack("<i", -1)                    # static AnsiString refcount
    blob += struct.pack("<I", 0)                     # length (runtime-set)
    blob += b"\x00" * 0x108                          # buf
    blob += INI_SECTION.encode() + b"\x00"
    for k in keys:
        blob += k.encode() + b"\x00"
    blob += b"\x00"                                  # empty default
    blob += pathstr.encode("latin1") + b"\x00"
    if engfb:
        blob += engfb["sub"].encode("latin1") + b"\x00"
    assert len(blob) == off
    return bytes(blob), code, asm_source(D), lay

def find_entry_points(code, cave_va, M, key_vas):
    """Locate wrapper entry VAs. A wrapper is the basic block that ends with
    `lea ecx,[ebx+<key VA>]; jmp <common>`; its entry is the first instruction
    after the previous block terminator (ret / unconditional jmp). This is
    structural -- it does NOT pattern-match prologues, so adding a helper such
    as ensure_ini cannot make it mis-assign hooks to the wrong wrappers."""
    insns = list(cs.disasm(bytes(code), cave_va))
    leaders, last_term = [], -1
    for idx, ins in enumerate(insns):
        if idx == last_term + 1:
            leaders.append(idx)
        if ins.mnemonic == "ret" or ins.mnemonic == "jmp":
            last_term = idx
    leader_at = {}
    for n, li in enumerate(leaders):
        end = leaders[n+1] if n+1 < len(leaders) else len(insns)
        leader_at[li] = end

    # classify: within each block, look for `lea ecx, [ebx + keyva]` then `jmp X`
    by_common = {}          # common target VA -> [(key, entry VA)]
    for li, end in leader_at.items():
        entry = insns[li].address
        for j in range(li, end):
            ins = insns[j]
            if ins.mnemonic != "lea" or not ins.op_str.startswith("ecx, [ebx +"):
                continue
            try:
                disp = int(ins.op_str.split("+")[-1].strip(" ]"), 16)
            except ValueError:
                continue
            key = key_vas.get(disp)
            if key is None or j+1 >= end or insns[j+1].mnemonic != "jmp":
                continue
            by_common.setdefault(insns[j+1].op_str, []).append((key, entry))

    keys = M["keys"]
    kinds = ["seed", "save"] + (["dirseed"] if M["thunk_setinidir"] else [])
    if len(by_common) != len(kinds):
        raise AssertionError(f"expected {len(kinds)} wrapper groups, got {by_common}")
    # groups appear in source order: seed, save, dirseed
    groups = sorted(by_common.items(), key=lambda kv: min(a for _, a in kv[1]))
    entries = {}
    for kind, (_tgt, members) in zip(kinds, groups):
        if sorted(k for k, _ in members) != sorted(keys):
            raise AssertionError(f"{kind} wrappers cover {members}, expected {keys}")
        for k, a in members:
            entries[f"{kind}_{k}"] = a
    return entries

def cave_for(cave_va, M, gen=3, legacy=None):
    blob, code, src, lay = build_cave(cave_va, M, gen, legacy)
    key_vas = {cave_va + lay["key"+k]: k for k in M["keys"]}
    return blob, code, src, lay, find_entry_points(code, cave_va, M, key_vas)

# ---- state classification ------------------------------------------------------
def classify(d, F, name, M):
    """-> (state, info). state in {absent, v3, v2, v1, undone, unknown}.
    v3 is what --apply writes; v2/v1 are earlier generations it is allowed to
    overwrite. For an engfb=None module the v3 and v2 blobs are identical, so
    such a module reports v3 and --apply is a no-op."""
    sec = find_section(d, F, SECT_NAME[:5])
    if sec is None:
        return "absent", {}
    va, vsz, raw, rsz, hdr = sec
    cave_va = M["ib"] + va
    installed = bytes(d[raw:raw+rsz])
    info = dict(sec=sec, cave_va=cave_va, installed=installed)

    new_blob, _c, _s, _l, new_entries = cave_for(cave_va, M)
    info["new_blob"], info["new_entries"] = new_blob, new_entries
    if installed == new_blob + b"\x00" * (rsz - len(new_blob)):
        return "v3", info
    if not any(installed):
        return "undone", info

    # v2? same cave minus the engine-data-root fallback
    v2_blob, _c, _s, _l, v2_entries = cave_for(cave_va, M, gen=2)
    if installed == v2_blob + b"\x00" * (rsz - len(v2_blob)):
        info["v2_entries"] = v2_entries
        return "v2", info

    # v1? its pathstr offset is independent of the string's length, so probe it
    _b, _c, _s, lay0, _e = cave_for(cave_va, M, legacy="")
    try:
        old_path = cstr(installed, lay0["pathstr"])
    except ValueError:
        return "unknown", info
    try:
        v1_blob, _c, _s, _l, v1_entries = cave_for(cave_va, M, legacy=old_path)
    except Exception:
        return "unknown", info
    if installed == v1_blob + b"\x00" * (rsz - len(v1_blob)):
        info["v1_entries"], info["old_path"] = v1_entries, old_path
        return "v1", info
    return "unknown", info

# ---- process one module --------------------------------------------------------
def process(name, mode, show_disasm=False):
    M = MODULES[name]
    ib = M["ib"]
    path = os.path.join(GAME, name)
    d = bytearray(open(path, "rb").read())
    orig_len = len(d)
    F = load_sections(d)
    secs = F["secs"]

    err = assert_gmfn_thunk(d, F, name, M)
    if err:
        print(f"[{name}] ABORT: {err}")
        return False

    thunk_of = dict(seed=M["thunk_create"], save=M["thunk_getfn"],
                    dirseed=M["thunk_setinidir"])
    state, info = classify(d, F, name, M)
    print(f"[{name}] .dlgd state: {state}")

    # ---------- undo ----------
    if mode == "undo":
        if state == "absent":
            print(f"[{name}] no .dlgd section - nothing to undo")
            return True
        if state == "undone":
            print(f"[{name}] already undone - no-op")
            return True
        if state == "unknown":
            print(f"[{name}] ABORT: .dlgd contents match none of v1/v2/v3 - refusing to undo")
            return False
        va, vsz, raw, rsz, hdr = info["sec"]
        for kind, site_va, key in M["sites"]:
            off = va2off(secs, site_va, ib)
            d[off:off+5] = b"\xE8" + rel32(site_va, thunk_of[kind])
        d[raw:raw+rsz] = b"\x00" * rsz
        struct.pack_into("<I", d, hdr+8, DLGD_RSIZE)     # VirtualSize -> inert 0x400
        assert len(d) == orig_len
        if not write_file(path, d, name):
            return False
        print(f"[{name}] undone: 16 sites restored to import thunks, cave zeroed, "
              f".dlgd VirtualSize -> 0x{DLGD_RSIZE:X} (empty section entry kept)")
        return True

    # ---------- verify / apply ----------
    if state == "unknown":
        print(f"[{name}] ABORT: .dlgd contents match none of the v1/v2/v3 caves")
        return False

    if state == "absent":
        # fresh install: prove every site still holds its original thunk
        for kind, site_va, key in M["sites"]:
            exp = b"\xE8" + rel32(site_va, thunk_of[kind])
            got = bytes(d[va2off(secs, site_va, ib):][:5])
            if got != exp:
                print(f"[{name}] ABORT: site 0x{site_va:08X} ({kind}/{key}) mismatch\n"
                      f"     exp {exp.hex(' ')}  got {got.hex(' ')}")
                return False
        if F["sectbl"] + F["nsec"]*40 + 40 > secs[0][2]:
            print(f"[{name}] ABORT: no PE header room for a new section")
            return False
        newva = align(max(s[0] + max(s[1], s[3]) for s in secs), F["salign"])
        cave_va = ib + newva
    else:
        # rewrite in place: NEVER recompute the VA, take it from the header
        va, vsz, raw, rsz, hdr = info["sec"]
        cave_va = info["cave_va"]

    blob, code, _src, lay, entries = cave_for(cave_va, M)
    if len(blob) > DLGD_RSIZE:
        print(f"[{name}] ABORT: cave is {len(blob)}B, does not fit in "
              f"0x{DLGD_RSIZE:X} raw bytes (PATHBUF starts at +0x{PATHBUF_OFF:X})")
        return False

    vsize = dlgd_vsize(M)
    # the page slack is only ours up to the next section's VA
    nxt = min((s[0] for s in secs if s[0] > cave_va - ib), default=None)
    if nxt is not None and (cave_va - ib) + vsize > nxt:
        print(f"[{name}] ABORT: .dlgd VirtualSize 0x{vsize:X} would reach into the "
              f"section at RVA 0x{nxt:X}")
        return False

    print(f"[{name}] cave @ 0x{cave_va:08X}  ({len(code)}B code, {len(blob)}B blob, "
          f"{DLGD_RSIZE - len(blob)}B spare)   PATHBUF @ 0x{cave_va+PATHBUF_OFF:08X} "
          f"({PATHBUF_SIZE}B page slack)")
    if M.get("engfb"):
        print(f"    DIRBUF @ 0x{cave_va+DIRBUF_OFF+8:08X} (StrRec 0x{cave_va+DIRBUF_OFF:08X}, "
              f"{DIRBUF_CHARS}B chars)   .dlgd VirtualSize 0x{vsize:X}   "
              f"engine fallback: [{M['engfb']['self_reg']}+0x{M['engfb']['off_self_engine']:02X}]"
              f"+0x{OFF_STARTUPDIR:02X} + \"{M['engfb']['sub']}\" for key "
              f"{M['engfb']['key']}")
    if show_disasm:
        print(f"----- {name} cave disasm -----")
        for ins in cs.disasm(bytes(code), cave_va):
            print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<21} {ins.mnemonic} {ins.op_str}")
        print("-----")
    for n, a in sorted(entries.items(), key=lambda kv: kv[1]):
        print(f"    {n:<14} 0x{a:08X}")

    # every site must currently hold: the original thunk, or a v1/v2/v3 cave entry
    ok_sites = True
    for kind, site_va, key in M["sites"]:
        cand = {thunk_of[kind]: "orig thunk", entries[f"{kind}_{key}"]: "v3 cave"}
        for gen in (2, 1):
            ents = info.get(f"v{gen}_entries")
            if ents:
                cand.setdefault(ents[f"{kind}_{key}"], f"v{gen} cave")
        off = va2off(secs, site_va, ib)
        got = bytes(d[off:off+5])
        hit = next((c for c in cand if got == b"\xE8" + rel32(site_va, c)), None)
        if hit is None:
            print(f"    site 0x{site_va:08X}  {kind:<8} {key:<4} ABORT: bytes {got.hex(' ')} "
                  f"match none of " + ", ".join(f"0x{c:08X} ({n})" for c, n in cand.items()))
            ok_sites = False
        else:
            print(f"    site 0x{site_va:08X}  {kind:<8} {key:<4} "
                  f"[{cand[hit]}] -> call 0x{entries[f'{kind}_{key}']:08X}")
    if not ok_sites:
        return False

    if mode != "apply":
        if state == "v3":
            print(f"[{name}] verify OK - v3 cave installed and all "
                  f"{len(M['sites'])} sites resolve into it")
        else:
            print(f"[{name}] dry-run OK (state {state}; all {len(M['sites'])} sites verified)")
        return True

    if state == "v3":
        print(f"[{name}] already v3 - idempotent no-op")
        return True

    # ---- backup, gated on a POSITIVE test of what we are about to overwrite ----
    if state == "absent":
        sfx = BACKUP_SUFFIX                # proven: no .dlgd + all 16 sites vanilla
    elif state == "v1":
        sfx = BACKUP_SUFFIX2               # proven: cave bytes are exactly the v1 cave
    elif state == "v2":
        sfx = BACKUP_SUFFIX3               # proven: cave bytes are exactly the v2 cave
    else:
        sfx = None                         # "undone" - nothing worth snapshotting
    bk = os.path.join(BACKUP_DIR, os.path.basename(path) + sfx) if sfx else None
    if bk and not os.path.exists(bk):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, bk)
        print(f"[{name}] backup -> {bk}  "
              f"({'pristine wrt this feature' if state == 'absent' else f'the {state} install'})")

    if state == "absent":
        newraw = align(len(d), F["falign"])
        if len(d) < newraw:
            d += b"\x00" * (newraw - len(d))
        d += bytes(blob) + b"\x00" * (DLGD_RSIZE - len(blob))
        b = F["sectbl"] + F["nsec"]*40
        struct.pack_into("<8sIIII", d, b, SECT_NAME, vsize, newva, DLGD_RSIZE, newraw)
        struct.pack_into("<IIHHI", d, b+24, 0, 0, 0, 0, 0xE0000060)  # code|idata|X|R|W
        struct.pack_into("<H", d, F["e"]+6, F["nsec"]+1)
        # only correct because a freshly appended section IS the last one
        struct.pack_into("<I", d, F["opt"]+56, align(newva + vsize, F["salign"]))
    else:
        va, vsz, raw, rsz, hdr = info["sec"]
        # any zone the cave grows into must still be zero
        grew = info["installed"][len(blob):]
        if any(grew):
            print(f"[{name}] ABORT: bytes the new cave grows into are not zero")
            return False
        d[raw:raw+rsz] = bytes(blob) + b"\x00" * (rsz - len(blob))
        struct.pack_into("<I", d, hdr+8, vsize)          # the ONLY header edit
        assert len(d) == orig_len, "file size must not change"

    for kind, site_va, key in M["sites"]:
        off = va2off(secs, site_va, ib)
        d[off:off+5] = b"\xE8" + rel32(site_va, entries[f"{kind}_{key}"])

    if not write_file(path, d, name):
        return False
    print(f"[{name}] written. Revert = `python build_dlgdirs.py --undo` (surgical); "
          f"a .pre-* whole-file restore is not a revert path.")
    return True

def write_file(path, d, name):
    try:
        open(path, "wb").write(d)
    except PermissionError:
        print(f"[{name}] LOCKED - close AoW/AoWCompat/AoWDevEd/AoWEd and retry")
        return False
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true", help="surgical revert of both modules")
    ap.add_argument("--disasm", "--dis", "--show", dest="disasm", action="store_true",
                    help="dump the cave disassembly")
    args = ap.parse_args()
    if args.apply and args.undo:
        sys.exit("--apply and --undo are mutually exclusive")
    mode = "apply" if args.apply else "undo" if args.undo else "verify"
    ok = True
    print(f"AoW1 editor per-dialog directory memory\n"
          f"  v2: runtime-derived INI path   v3: Set dialogs fall back to the engine data root\n"
          f"  INI file = <host exe dir>\\{INI_NAME}   section [{INI_SECTION}]\n")
    for name in MODULES:
        ok &= process(name, mode, args.disasm)
        print()
    if mode == "verify":
        print("[dry-run] --apply to write, --undo to revert (close the game/editors first).")
        # A no-args run IS the state verifier (project convention), so it must exit non-zero when
        # a module fails to verify -- otherwise anything checking $? gets a false pass off an ABORT.
        if not ok:
            sys.exit(1)
    elif not ok:
        sys.exit(1)
    else:
        print(f"[done] {mode}: both modules.")

main()
