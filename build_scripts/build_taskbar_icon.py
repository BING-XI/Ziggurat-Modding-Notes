#!/usr/bin/env python3
r"""
TASKBAR ICON  --  give the Windows taskbar button a real icon instead of the grey
placeholder.  AoWz.exe + AoWzCompat.exe + AoWDevEd.exe (-> AoWzEd.exe).

THE DEFECT -- narrower than it looks: ICON_BIG was ALREADY correct, ICON_SMALL was 0
  The taskbar button belongs to Delphi 3's hidden owner window, class `TApplication`.
  Measured live on that window BEFORE this patch (AoWzEd.exe, hwnd 0xA0594, ctypes probe):

      GCL_HICON              = 0
      GCL_HICONSM            = 0
      WM_GETICON ICON_SMALL  = 0
      WM_GETICON ICON_BIG    = a real HICON: 32x32 32bpp, 664 opaque px, md5 a7d4500a...,
                               BYTE-IDENTICAL to MAINICON RT_ICON id 1 in the exe
      WM_GETICON ICON_SMALL2 = a real HICON: 16x16, 189 opaque px, a downscale of the same

  ICON_BIG was therefore already set, and already MAINICON.
  `Forms.TApplication.CreateHandle @0x4133ACB0` is what sets it.  At 0x4133ADB6 it tests
  `Controls.NewStyleControls` (`mov eax,[0x413E2504]` -> BSS flag 0x413E3738;
  `cmp byte ptr [eax],0`; `je` past), and when true runs 0x4133ADC0..0x4133ADD3:

      mov eax,ebx / call 0x4133B754        ; the TApplication icon handle
      push eax / push 1 / push 0x80        ; lParam=hIcon, wParam=ICON_BIG, WM_SETICON
      mov eax,[ebx+0x24] / push eax        ; hWnd = FHandle -- the OWNER WINDOW itself
      call user32!SendMessageA

  It targets `[ebx+0x24]`, the same window this cave targets -- not a form.  That flag is
  evidently true at runtime, since the probe found the icon set.

  What is missing is ICON_SMALL.  vcl30.dpl has 14 `push 0x80` sites in CODE; the three
  inside TApplication all push wParam **1**, never 0:

      0x4133ADCA   CreateHandle                      lParam = the icon handle
      0x4133C337   IconChanged (send @0x4133C340)    same shape, same NewStyleControls gate
      0x4133AC5E   TApplication.Destroy @0x4133AC5A  lParam **0** -- clears it on shutdown

  Delphi 3 never sends ICON_SMALL at all, and no module in the process imports
  SetClassLongA, so GCL_HICONSM stays 0 too.  The taskbar resolves
  ICON_SMALL2 -> ICON_SMALL -> GCL_HICONSM, and the only non-zero answer available to it
  was DefWindowProc's synthesised SMALL2.  Win11 drew the grey placeholder anyway.

  ⚠ WHY the taskbar rejects that synthesised SMALL2 is NOT measured -- do not assert it.
  What IS measured: ICON_BIG set and correct, ICON_SMALL and GCL_HICONSM zero, taskbar
  grey.  The change this patch makes is the **ICON_SMALL send**; the ICON_BIG send is
  belt-and-braces (harmless, and it makes the cave independent of NewStyleControls).
  The in-game test is what decides.

  The icon RESOURCE was never at fault -- `MAINICON` (RT_GROUP_ICON) is in all four exes
  and LoadIconA finds it.

THE FIX -- call-retarget, 4 bytes changed per binary, nothing displaced
  Each exe's program block calls `Forms.TApplication.Initialize` exactly once.  That
  `call rel32` is retargeted to a cave; the cave sets both icons on Application.Handle and
  tail-jumps to the real Initialize import thunk.  See `aow1-call-retarget-thunk`: no host
  instruction is overwritten, so there is no orphan tail and --undo is a 5-byte restore.

  | binary                    | hook VA    | file off | vanilla bytes  | Initialize thunk |
  |---------------------------|------------|----------|----------------|------------------|
  | AoWz.exe / AoWzCompat.exe | 0x004599DE | 0x058DDE | e8 71 7d fa ff | 0x00401754       |
  | AoWDevEd.exe (-> AoWzEd)   | 0x0042EE52 | 0x02E252 | e8 d1 24 fd ff | 0x00401328       |

  Both thunks verified as `jmp dword ptr [<IAT>]` against
  `VCL30.dpl!Forms.TApplication.Initialize@23EDC2EF`.

CAVES -- 96 bytes each, exe fixed base 0x400000 so absolute operands are legal
  | binary        | cave VA    | file off | reserved span | host section          |
  |---------------|------------|----------|---------------|-----------------------|
  | AoWz.exe      | 0x0062B000 | 0x225200 | 0x100         | .hcol 0x612000+0x1C000|
  | AoWzCompat.exe| 0x0062B000 | 0x225200 | 0x100         | .hcol (lockstep)      |
  | AoWDevEd.exe  | 0x00590180 | 0x18A380 | 0x80          | .vgo  0x590000+0x200  |

  `.hcol` 0x0062A200..0x0062D000 is a 11.5 KB zero run; 0x0062B000 sits in the middle of
  it, 0x100 is reserved, `grep -rl 0x62B` over build_scripts/ returns nothing.
  `.vgo` has SizeOfRawData 0x200 but VirtualSize 0x16D, and the cave sits at +0x180.  Bytes
  past VirtualSize inside SizeOfRawData are mapped in practice, but this script does not
  rely on that: --apply raises `.vgo` VirtualSize 0x16D -> 0x200 so the header states what
  is really there, and --undo puts it back.  SizeOfImage (0x19A000) already covers it, so
  nothing else in the header moves and the file length never changes.

THE REBASE DELTA -- why the cave reaches into vcl30.dpl at all
  **LoadIconA is in no exe's IAT**, so the delta is needed whatever else is available.
  SendMessageA is the one that differs per binary, and it is NOT absent everywhere:

      AoWz.exe / AoWzCompat.exe    1 user32 import  -- UnionRect @0x0045D3A8.  No SendMessageA.
      AoWDevEd.exe / AoWzEd.exe   19 user32 imports -- SendMessageA @0x00432248.

  The editor could call its own SendMessageA and skip one of the two vcl30 loads.  It does
  not, deliberately: routing both through vcl30 keeps ONE cave body across all four files
  with only four immediates differing, which is what makes the lockstep check and the
  editor derive cheap to verify.  It costs 6 bytes.

  vcl30.dpl is a package and rebases, so its runtime addresses are recovered from an import
  the exe already has:

      delta = [<exe IAT slot for Forms.TApplication.GetExeName>] - 0x4133C0F8

  0x4133C0F8 is that export's preferred VA in `Ziggurat\vcl30.dpl` (ImageBase 0x41300000),
  read out of its .edata.  Everything else is `[edx + <preferred VA>]`:

      0x413E46F8  vcl30 IAT slot, user32!LoadIconA       (verified by import-table walk)
      0x413E468C  vcl30 IAT slot, user32!SendMessageA    (verified by import-table walk)
      0x4133ABCC  vcl30's own 'MAINICON' literal         (bytes at that VA are "MAINICON\0")

  Using vcl30's own literal means this cave carries no string of its own.  It is the exact
  pointer TApplication.Create pushes at 0x4133AAE1 when it loads Application.Icon.
  Precedent for the idiom: `Zig notes\08-editor.md` 9.3 (WinExec via vclx30.dpl).
  6.1's `vcl_delta` worked example does NOT reproduce -- use the GetExeName anchor.

PER-BINARY IAT SLOTS (resolved by import-table walk, not by eye)
  |                                          | AoWz / AoWzCompat | AoWDevEd / AoWzEd |
  | VCL30!Forms.Application       (data)     | 0x0045D5F4        | 0x00432224        |
  | VCL30!Forms.TApplication.GetExeName      | 0x0045D56C        | 0x00432178        |
  | kernel32!GetModuleHandleA                | 0x0045D39C        | 0x00432160        |

  TApplication.FHandle is at +0x24, proven from SetHandle @0x4133B900:
  `cmp esi,[ebx+0x24]` ... `mov [ebx+0x24],eax`.

REGISTER DISCIPLINE (this is where the first draft was wrong)
  EDX holds the delta, and EDX is caller-save under stdcall -- GetModuleHandleA is free to
  trash it.  Both vcl30 IAT slots are therefore loaded into ESI/EDI BEFORE the first call,
  and EDX is never read again afterwards.  EBX holds hWnd, ESI becomes hIcon after
  LoadIconA returns.  pushad/popad brackets the whole thing so the program block sees no
  register change at all.

  ONE LoadIconA handle is used for both ICON_BIG and ICON_SMALL.  User32 downscales the
  32x32 for the small slot; there is no 16x16 in the group, so a real LoadImageA call would
  downscale the identical bitmap.  ICON_SMALL is the send that does the work here -- see
  THE DEFECT; ICON_BIG merely restates what CreateHandle already set.

KEYSTONE imm8 -- DEFENCE IN DEPTH, not a workaround for an observed miscompile
  Measured on the installed keystone: `push 0x80` -> `68 80 00 00 00`, i.e. the correct
  5-byte form.  The standing imm8 trap is real but lands on SIGN-EXTENSION cases --
  `push 0x7F` -> `6a 7f`, `push 0xFFFF` -> `6a ff` (both re-measured here) -- and 0x80 is
  not one of them, because 0x80 does not round-trip through a signed imm8.
  The explicit `.byte 0x68, 0x80, 0x00, 0x00, 0x00` emission and the _assert_encoding()
  self-disassembly are kept anyway: WM_SETICON IS 0x80, so a `6A 80` would mean message
  0xFFFFFF80 with every byte check still passing, and that failure mode is silent enough
  to be worth 0 bytes of cost and a hard assert.  The guard fails the build unless both
  pushes decode as a 5-byte `push 0x80`.
  (WM_SETICON = 0x0080, WM_GETICON = 0x007F -- do not transpose.)

.reloc
  A `call rel32` displacement never carries a base relocation, and it is confirmed here:
  AoWz.exe has entries at 0x004599BE and 0x004599E5 with nothing in 0x004599DF..0x004599E2;
  AoWDevEd.exe has 0x0042EE4C and 0x0042EE58 with nothing in 0x0042EE53..0x0042EE56.  Zero
  entries anywhere in 0x0060C000..0x00630000 or in `.vgo`.  Run `build_relocfix.py` anyway.

RULED OUT (each with its reason, one line each)
  * SetClassLongA/W -- in no IAT, would need GetProcAddress, and Win11 reads WM_GETICON not
    GCL_HICONSM anyway.
  * LoadImageA for a true 16x16 -- imported by zero modules, and the group has no 16x16.
  * Reading Application.Icon.Handle -- D3's TIcon is a TIconImage indirection, not a bare
    HICON: two unverified offsets plus a lifetime question.
  * Patching vcl30's WNDCLASS template at 0x413E19A4 (hIcon at +0x14) -- hIcon must be a
    runtime HANDLE; any static non-zero there is a garbage handle.
  * AoWz.exe `.hcol` below 0x00628000 -- build_herodlg_columns.py line 1547 does
    `exe.wr(SEC_VA, b"\0" * (SQUATTER_FLOOR - SEC_VA))`, zeroing 0x00612000..0x00628000 on
    EVERY --apply.  The "free" 0x00624200..0x00628000 the ownership table advertises is
    inside that wipe.
  * AoWz.exe `.syd` / `.pyar` -- both owners rewrite the whole 0x1000 section and then
    verify `d[SEC_FOFF:SEC_FOFF+SEC_SIZE] == BLOB`.
  * AoWz.exe `.hcol` at/above 0x0062D0A0 -- build_powerleech_ui.py asserts
    0x0062D300..0x0062E000 is zero.
  * A new PE section in AoWDevEd.exe -- e_lfanew 0x100, 13 headers end at exactly file
    0x400 = CODE's PointerToRawData.  Room for zero more.  (AoWz.exe has room for exactly
    one; not worth spending on 96 bytes.)
  * AoWDevEd.exe `.dlgd` 0x004E02D0 -- usable, but build_dlgdirs.py --undo zeroes all 0x400
    of that section.  Kept as the fallback only if the cave ever outgrows `.vgo`.

ALTERNATIVE NOT TAKEN
  One PIC cave in `Ziggurat\vcl30.dpl` hooking TApplication.Run @0x4133BC9C would fix
  AoWz.exe, AoWzCompat.exe and AoWzEd.exe at once with no rebase delta, since all three
  load that package.  Rejected: it couples to build_wheel_editor.py's existing cave at
  0x413A8800 in the same file, it must be position-independent, and it would leave the
  editor SOURCE (AoWDevEd.exe) unpatched so every future editor build would ship without it.

RNG
  No roll.  No generator, no P1-P5 pattern, rng_audit.py not applicable.

CONVENTIONS
  Dry run by default (prints the disassembly and the planned byte diffs); --apply writes;
  --undo is surgical (restores the 5 hook bytes, zeroes ONLY this feature's reserved cave
  span, restores `.vgo` VirtualSize) and mints no snapshot; --show/--dis disassembles.
  Verify-before-write throughout: --apply accepts a site that is exactly vanilla or exactly
  this feature's own output and aborts on anything else, so re-tuning is an in-place cave
  rewrite and never a revert-and-reapply.
  Snapshot -> `<game dir>\backups\<file>.pre-taskbaricon`, minted on --apply ONLY and only
  when the hook site is PROVEN vanilla, so it can never capture a patched state.

  !! AoWzEd.exe IS DERIVED.  This script patches AoWDevEd.exe, the source.  After --apply
  or --undo you MUST run `build_zigeditor.py --apply` or the live editor keeps the old
  bytes while every static check here passes.  The script prints this and reports whether
  the live editor is currently in sync.

IN-GAME CHECKLIST (nobody has run it -- status is APPLIED, UNTESTED)
  1. Launch `Ziggurat\AoWz.exe`.  It must reach the main menu at all: this cave runs in the
     program block, which is startup code, and per project rule a startup cave is only
     proved by launching the exe.
  2. Look at the taskbar button -- the purple dragon, not the grey placeholder.
  3. Alt-Tab: the switcher entry must show the same icon.
  4. Win+Tab / taskbar thumbnail preview: icon present in the corner.
  5. Repeat 1-4 for `Ziggurat\AoWzCompat.exe`.
  6. Repeat 1-4 for `Ziggurat\AoWzEd.exe` (after build_zigeditor.py --apply) -- and open a
     map, to confirm the editor still works, not just that it starts.
  7. Pin one to the taskbar and relaunch from the pin: the running button must merge with
     the pinned one rather than appearing twice with different art.

  ⭐ DISCRIMINATOR if it half-works: **Alt-Tab reads ICON_BIG, the taskbar button reads
  ICON_SMALL.**  ICON_BIG was already correct before this patch, so "Alt-Tab right, taskbar
  still grey" means the ICON_SMALL send is the suspect -- not the icon, not LoadIconA, not
  the rebase delta (any of those failing would break both).  "Both wrong" points at the
  cave not running at all, i.e. the hook or the startup path.

Needs: pip install keystone-engine capstone
"""
import argparse, os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

BACKUP_DIR = os.path.join(GAME, "backups")      # rule 2026-09-03; never beside the target
BACKUP_SUFFIX = ".pre-taskbaricon"

# ---- vcl30.dpl constants (preferred base 0x41300000) -----------------------------
VCL_GETEXENAME_PREF = 0x4133C0F8   # export Forms.TApplication.GetExeName -- the anchor
VCL_LOADICON_IAT    = 0x413E46F8   # vcl30 IAT slot: user32!LoadIconA
VCL_SENDMSG_IAT     = 0x413E468C   # vcl30 IAT slot: user32!SendMessageA
VCL_MAINICON_LIT    = 0x4133ABCC   # vcl30's own "MAINICON\0"

APP_FHANDLE_OFF = 0x24             # TApplication.FHandle, from SetHandle @0x4133B900
WM_SETICON      = 0x80
ICON_BIG        = 1
ICON_SMALL      = 0

# ---- per-binary constants --------------------------------------------------------
# derived=True  -> built by build_zigeditor.py from `src`; reported, never written.
TARGETS = [
    dict(name="AoWz.exe",       derived=False, src=None,
         hook_va=0x004599DE, thunk=0x00401754,
         app_slot=0x0045D5F4, getexename_slot=0x0045D56C, getmodhandle_slot=0x0045D39C,
         cave_va=0x0062B000, cave_span=0x100, section=".hcol", vsz_bump=None),
    dict(name="AoWzCompat.exe", derived=False, src=None,
         hook_va=0x004599DE, thunk=0x00401754,
         app_slot=0x0045D5F4, getexename_slot=0x0045D56C, getmodhandle_slot=0x0045D39C,
         cave_va=0x0062B000, cave_span=0x100, section=".hcol", vsz_bump=None),
    dict(name="AoWDevEd.exe",   derived=False, src=None,
         hook_va=0x0042EE52, thunk=0x00401328,
         app_slot=0x00432224, getexename_slot=0x00432178, getmodhandle_slot=0x00432160,
         cave_va=0x00590180, cave_span=0x80,  section=".vgo",
         vsz_bump=(b".vgo", 0x0000016D, 0x00000200)),
    dict(name="AoWzEd.exe",     derived=True,  src="AoWDevEd.exe",
         hook_va=0x0042EE52, thunk=0x00401328,
         app_slot=0x00432224, getexename_slot=0x00432178, getmodhandle_slot=0x00432160,
         cave_va=0x00590180, cave_span=0x80,  section=".vgo",
         vsz_bump=(b".vgo", 0x0000016D, 0x00000200)),
]

IMAGE_BASE = 0x400000


# ---- PE helpers ------------------------------------------------------------------
def pe(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    opt = e + 24
    sectbl = opt + optsz
    secs = []
    for i in range(nsec):
        b = sectbl + i * 40
        nm = bytes(d[b:b + 8])
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
        secs.append(dict(name=nm, va=va, vsz=vsz, raw=raw, rsz=rsz, hdr=b))
    return dict(e=e, opt=opt, sectbl=sectbl, nsec=nsec, secs=secs)


def va2off(F, va):
    rva = va - IMAGE_BASE
    for s in F["secs"]:
        if s["va"] <= rva < s["va"] + max(s["vsz"], s["rsz"]):
            return s["raw"] + (rva - s["va"])
    raise ValueError(f"VA {va:#x} is in no section")


def find_sec(F, name8):
    for s in F["secs"]:
        if s["name"][:len(name8)] == name8 and s["name"][len(name8):].strip(b"\0") == b"":
            return s
    return None


# ---- the cave --------------------------------------------------------------------
def cave_src(t):
    """Same body for every target; only four immediates differ."""
    return f"""
        pushad
        mov  ecx, dword ptr [{t['app_slot']:#x}]        ; &Forms.Application
        mov  ecx, dword ptr [ecx]                       ; the TApplication object
        test ecx, ecx
        jz   done
        mov  ebx, dword ptr [ecx + {APP_FHANDLE_OFF:#x}]  ; FHandle = the owner window
        test ebx, ebx
        jz   done
        mov  edx, dword ptr [{t['getexename_slot']:#x}]
        sub  edx, {VCL_GETEXENAME_PREF:#x}              ; edx = vcl30 rebase delta
        mov  esi, dword ptr [edx + {VCL_LOADICON_IAT:#x}]   ; user32!LoadIconA
        mov  edi, dword ptr [edx + {VCL_SENDMSG_IAT:#x}]    ; user32!SendMessageA
        lea  eax, [edx + {VCL_MAINICON_LIT:#x}]         ; vcl30's own 'MAINICON'
        push eax                                        ; LoadIconA arg2 lpIconName
        push 0
        call dword ptr [{t['getmodhandle_slot']:#x}]    ; GetModuleHandleA(NULL); trashes edx
        push eax                                        ; LoadIconA arg1 hInstance
        call esi
        mov  esi, eax                                   ; hIcon
        test esi, esi
        jz   done
        push esi
        push {ICON_BIG}
        .byte 0x68, 0x80, 0x00, 0x00, 0x00              ; push WM_SETICON  (NOT `push 0x80`)
        push ebx
        call edi
        push esi
        push {ICON_SMALL}
        .byte 0x68, 0x80, 0x00, 0x00, 0x00              ; push WM_SETICON  (NOT `push 0x80`)
        push ebx
        call edi
    done:
        popad
        jmp  {t['thunk']:#x}
    """


def assemble(t):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    src = "\n".join(ln.split(";", 1)[0] for ln in cave_src(t).splitlines())
    code, _ = ks.asm(src, t["cave_va"])
    blob = bytes(code)
    _assert_encoding(blob, t)
    return blob


def _assert_encoding(blob, t):
    """The keystone imm8 trap, checked rather than trusted (CLAUDE.md)."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    ins = list(cs.disasm(blob, t["cave_va"]))
    assert ins, "cave did not disassemble at all"
    pushes = [i for i in ins if i.mnemonic == "push" and i.op_str == "0x80"]
    assert len(pushes) == 2, (
        f"{t['name']}: expected exactly 2 `push 0x80` (WM_SETICON), found {len(pushes)} -- "
        "keystone imm8 trap")
    for i in pushes:
        assert i.bytes == b"\x68\x80\x00\x00\x00", (
            f"{t['name']}: WM_SETICON push encoded as {i.bytes.hex()} not 6880000000 -- "
            "that is push -128, the silent-wrong-message trap")
    assert ins[-1].mnemonic == "jmp" and ins[-1].op_str == f"{t['thunk']:#x}", (
        f"{t['name']}: tail jump is {ins[-1].mnemonic} {ins[-1].op_str}, "
        f"expected jmp {t['thunk']:#x}")
    assert len(blob) <= t["cave_span"], (
        f"{t['name']}: cave is {len(blob)}B but only {t['cave_span']}B is reserved at "
        f"{t['cave_va']:#x}")


def orig_hook(t):
    return b"\xE8" + struct.pack("<i", t["thunk"] - (t["hook_va"] + 5))


def patched_hook(t):
    return b"\xE8" + struct.pack("<i", t["cave_va"] - (t["hook_va"] + 5))


# ---- state -----------------------------------------------------------------------
def inspect(t, blob):
    """Read the file and classify. Never writes."""
    path = os.path.join(GAME, t["name"])
    d = bytearray(open(path, "rb").read())
    F = pe(d)
    ho = va2off(F, t["hook_va"])
    co = va2off(F, t["cave_va"])
    hook_now = bytes(d[ho:ho + 5])
    cave_now = bytes(d[co:co + t["cave_span"]])

    vsz_state = None
    if t["vsz_bump"]:
        nm, orig, new = t["vsz_bump"]
        s = find_sec(F, nm)
        assert s is not None, f"{t['name']}: section {nm!r} not found"
        vsz_state = (s, s["vsz"], orig, new)

    if hook_now == orig_hook(t):
        state = "VANILLA"
    elif hook_now == patched_hook(t):
        state = "PATCHED"
    else:
        state = "FOREIGN"
    return dict(path=path, d=d, F=F, ho=ho, co=co, hook_now=hook_now,
                cave_now=cave_now, state=state, vsz=vsz_state,
                cave_matches=cave_now[:len(blob)] == blob,
                tail_zero=all(v == 0 for v in cave_now[len(blob):]),
                all_zero=all(v == 0 for v in cave_now))


def report(t, st, blob):
    tag = f"[{t['name']:<14}]"
    extra = ""
    if t["derived"]:
        extra = "  (DERIVED from %s by build_zigeditor.py -- not a write target)" % t["src"]
    if st["state"] == "PATCHED" and st["cave_matches"] and st["tail_zero"]:
        v = ""
        if st["vsz"]:
            s, cur, orig, new = st["vsz"]
            v = f", .vgo VirtualSize {cur:#x}" + ("" if cur == new else f" (expected {new:#x})")
        print(f"{tag} INSTALLED: hook {t['hook_va']:#x} -> cave {t['cave_va']:#x} "
              f"({len(blob)}B){v}{extra}")
    elif st["state"] == "PATCHED":
        print(f"{tag} PATCHED but cave DIFFERS "
              f"(matches={st['cave_matches']} tail_zero={st['tail_zero']}){extra}")
    elif st["state"] == "VANILLA":
        print(f"{tag} not installed: hook {t['hook_va']:#x} is vanilla "
              f"({st['hook_now'].hex()}), cave span zero={st['all_zero']}{extra}")
    else:
        print(f"{tag} !! FOREIGN hook bytes at {t['hook_va']:#x}: {st['hook_now'].hex()} "
              f"(vanilla {orig_hook(t).hex()}, ours {patched_hook(t).hex()}){extra}")


def disasm(blob, va, title):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    print(f"---- {title} ({len(blob)} bytes) ----")
    for i in cs.disasm(blob, va):
        print(f"  {i.address:08X}  {i.bytes.hex():<14s} {i.mnemonic:<8s} {i.op_str}")


def zigeditor_note(action):
    print()
    print("  !! REQUIRED NEXT STEP -- AoWzEd.exe is DERIVED, not patched here:")
    print("       python \"%s\" --apply"
          % os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_zigeditor.py"))
    print(f"     Without it the live editor keeps its pre-{action} bytes while every static")
    print("     check in this script still passes against AoWDevEd.exe.")


# ---- main ------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="taskbar icon for the Ziggurat executables")
    ap.add_argument("--apply", action="store_true", help="write the patch")
    ap.add_argument("--undo", action="store_true",
                    help="surgical revert: 5 hook bytes + this feature's cave span only")
    ap.add_argument("--show", "--dis", dest="show", action="store_true",
                    help="disassemble the caves (planned and, where present, installed)")
    args = ap.parse_args()
    if args.apply and args.undo:
        print("--apply and --undo are mutually exclusive")
        return 1

    writable = [t for t in TARGETS if not t["derived"]]
    blobs = {t["name"]: assemble(t) for t in TARGETS}

    # ---- read-only pass: classify everything before touching anything ------------
    states = {}
    for t in TARGETS:
        states[t["name"]] = inspect(t, blobs[t["name"]])
        report(t, states[t["name"]], blobs[t["name"]])

    if args.show or not (args.apply or args.undo):
        for t in TARGETS:
            if t["derived"]:
                continue
            disasm(blobs[t["name"]], t["cave_va"], f"{t['name']} cave (planned)")
            st = states[t["name"]]
            if st["state"] == "PATCHED" and not st["cave_matches"]:
                disasm(st["cave_now"].rstrip(b"\x00"), t["cave_va"],
                       f"{t['name']} cave (INSTALLED, differs)")
            print(f"---- {t['name']} hook @ {t['hook_va']:#x}: "
                  f"{orig_hook(t).hex()} -> {patched_hook(t).hex()}")

    if args.show and not (args.apply or args.undo):
        return 0

    # ---- verify-before-write -----------------------------------------------------
    if args.apply:
        for t in writable:
            st = states[t["name"]]
            if st["state"] == "FOREIGN":
                print(f"ABORT: {t['name']} hook {t['hook_va']:#x} is neither vanilla nor "
                      f"ours ({st['hook_now'].hex()}) -- another feature owns it")
                return 1
            if st["state"] == "VANILLA" and not st["all_zero"]:
                print(f"ABORT: {t['name']} cave span {t['cave_va']:#x}"
                      f"..{t['cave_va'] + t['cave_span']:#x} is not zero and the hook is "
                      f"vanilla -- someone else is using that space")
                return 1
            if st["state"] == "PATCHED" and not st["tail_zero"]:
                print(f"ABORT: {t['name']} growth zone past {t['cave_va'] + len(blobs[t['name']]):#x} "
                      f"is not zero -- refusing to overwrite in place")
                return 1
            if st["vsz"]:
                s, cur, orig, new = st["vsz"]
                if cur not in (orig, new):
                    print(f"ABORT: {t['name']} {s['name'].rstrip(chr(0).encode()).decode()} "
                          f"VirtualSize is {cur:#x}, expected {orig:#x} or {new:#x}")
                    return 1

        if all(states[t["name"]]["state"] == "PATCHED"
               and states[t["name"]]["cave_matches"]
               and (not states[t["name"]]["vsz"] or
                    states[t["name"]]["vsz"][1] == states[t["name"]]["vsz"][3])
               for t in writable):
            print("\nalready installed and identical - no-op")
            print("  (AoWzEd.exe status above tells you whether the editor derive is stale)")
            return 0

        for t in writable:
            st = states[t["name"]]
            blob = blobs[t["name"]]
            d = st["d"]

            # snapshot: --apply ONLY, and only from a PROVEN-VANILLA hook site, so it can
            # never capture this script's own previous output (CLAUDE.md, 2026-09-10).
            if st["state"] == "VANILLA":
                bp = os.path.join(BACKUP_DIR, t["name"] + BACKUP_SUFFIX)
                if not os.path.exists(bp):
                    os.makedirs(BACKUP_DIR, exist_ok=True)
                    shutil.copy2(st["path"], bp)
                    print(f"    backup -> {bp}")
            else:
                print(f"    {t['name']}: re-tune over our own cave - no snapshot minted")

            d[st["co"]:st["co"] + t["cave_span"]] = blob + b"\x00" * (t["cave_span"] - len(blob))
            d[st["ho"]:st["ho"] + 5] = patched_hook(t)
            if st["vsz"]:
                s, cur, orig, new = st["vsz"]
                struct.pack_into("<I", d, s["hdr"] + 8, new)

            try:
                open(st["path"], "wb").write(d)
            except PermissionError:
                print(f"[{t['name']}] LOCKED - close every AoW binary and retry")
                return 1
            print(f"[{t['name']:<14}] applied: hook {t['hook_va']:#x} -> cave "
                  f"{t['cave_va']:#x} ({len(blob)}B in {t['section']})")

        zigeditor_note("patch")
        print("\n  Then: python build_relocfix.py   (standing audit)")
        print("  STATUS: APPLIED, UNTESTED -- only an in-game launch can promote it.")
        return 0

    # ---- undo --------------------------------------------------------------------
    if args.undo:
        touched = False
        for t in writable:
            st = states[t["name"]]
            if st["state"] == "VANILLA" and st["all_zero"] and (
                    not st["vsz"] or st["vsz"][1] == st["vsz"][2]):
                print(f"[{t['name']:<14}] already reverted - no-op")
                continue
            if st["state"] == "FOREIGN":
                print(f"ABORT: {t['name']} hook {t['hook_va']:#x} is {st['hook_now'].hex()}, "
                      f"not ours - refusing to restore over another feature")
                return 1
            d = st["d"]
            d[st["ho"]:st["ho"] + 5] = orig_hook(t)
            d[st["co"]:st["co"] + t["cave_span"]] = b"\x00" * t["cave_span"]
            if st["vsz"]:
                s, cur, orig, new = st["vsz"]
                struct.pack_into("<I", d, s["hdr"] + 8, orig)
            try:
                open(st["path"], "wb").write(d)
            except PermissionError:
                print(f"[{t['name']}] LOCKED - close every AoW binary and retry")
                return 1
            touched = True
            print(f"[{t['name']:<14}] reverted: hook restored, cave span {t['cave_va']:#x}"
                  f"..{t['cave_va'] + t['cave_span']:#x} zeroed")
        if touched:
            zigeditor_note("undo")
        print("\n  No snapshot was read or written - this revert is surgical.")
        return 0

    print("\ndry run - re-run with --apply to write, --undo to revert, --show to disassemble")
    return 0


if __name__ == "__main__":
    sys.exit(main())
