#!/usr/bin/env python3
r"""Editor: UP/DOWN arrow keys move the Abilities and Spells list selection.

In AoWDevEd's **Settings -> Abilities** and **Settings -> Spells** tabs, clicking a list
entry refreshes the detail panels but the keyboard arrows did nothing at all.  Two
independent defects, both fixed here, each behind its own state report and its own
`--undo` branch (`--part arrows` / `--part guard` / `--part both`, default both).

Target: `Ziggurat\AoWDevEd.exe` (zigexe.SRC_EDITOR), and nothing else.  No `.dpl`, no
game exe.  The cave makes no random draw, contains no filesystem path and no username.

================================================================================
⚠⚠ THE EDITOR EXE TRAP -- an editor patch is TWO steps
================================================================================
`Ziggurat\AoWDevEd.exe` is the PATCH SOURCE, and nothing runs it.  The editor the owner
launches is `Ziggurat\AoWzEd.exe` (zigexe.LIVE_EDITOR), which `build_zigeditor.py`
REBUILDS from AoWDevEd.exe.  Skip the second step and every check here passes against a
binary nobody loads -- silently:

    python build_deved_listarrows.py --apply   # patches Ziggurat\AoWDevEd.exe
    python build_zigeditor.py        --apply   # rebuilds -> Ziggurat\AoWzEd.exe

This holds for `--undo` exactly as hard as for `--apply`.  AoWzEd.exe is NOT a byte copy
of AoWDevEd.exe (icon re-skin, ~4.4 KB of `.rsrc` differs), so never compare file hashes
-- compare the cave region and the hook sites.  `show_state()` below prints a read-only
AoWzEd.exe line for exactly this reason; it never writes to it.

--------------------------------------------------------------------------------------
DEFECT 1 -- `Application.OnMessage` confiscates every arrow key
--------------------------------------------------------------------------------------
`TMainForm.FormCreate` installs an `Application.OnMessage` filter (Code `[App+0x9c]` =
`0x004280DC`, Data `[App+0xa0]` = the form; both assigned at `0x00428630`).  The handler:

    004280E8  mov  eax,[ebx+4]            ; TMsg.message   (ebx = @TMsg, esi = TMainForm)
    004280EB  cmp  eax,0x100 / jl  OUT    ; WM_KEYFIRST..
    004280F2  cmp  eax,0x108 / jg  OUT    ; ..WM_KEYLAST
    004280F9  cmp  eax,0x100 / jne OUT    ; WM_KEYDOWN only
    00428100  mov  eax,[ebx+8]            ; wParam = the virtual key
    00428108  ..0x00428126                ; accept VK 0x25 LEFT 0x27 RIGHT 0x26 UP 0x28 DOWN
    00428128  mov  eax,[0x432220]         ; Forms.Screen
    0042812D  mov  eax,[eax]
    0042812F  cmp  esi,[eax+0x5c]         ; Screen.ActiveForm = MainForm ?   <-- HOOK HERE
    00428132  jne  0x00428157
    00428134  mov  eax,[ebx+0xc]          ; ..forward to [esi+0x22c] (HSMEdit) KeyDown
              call 0x401220               ;   Forms.KeyDataToShiftState
              mov  eax,[esi+0x22c] / mov bx,0xffdf / call @CallDynaInst
    00428154  mov  byte ptr [eax],1       ; Handled := True   <<< THE KEY DIES HERE
    00428157  pop ecx/edx/esi/ebx; ret    ; "not ours" exit -- Handled stays False

`TApplication.ProcessMessage` calls `OnMessage` BEFORE `IsKeyMsg` / `TranslateMessage` /
`DispatchMessage`, so the focused listbox never receives WM_KEYDOWN at all.  That is why
the mouse works and the keyboard does not: nothing is wrong with the listboxes.

FIX: gate the swallow.  Hook `0x0042812F` (5 B, the displaced `cmp esi,[eax+0x5c]` +
`jne 0x428157`) with `E9 <cave>` and let the message through untouched when `TMsg.hwnd`
is one of the two listbox handles.  Vanilla VCL then does the rest -- see below.

⚠ **Do NOT hook at `0x00428128`.**  That 5-byte `mov eax,[0x432220]` is the obvious site
and it is a trap: the `.reloc` directory carries a type-3 HIGHLOW fixup at `0x00428129`,
so the loader would apply a rebase delta on top of the hook's own rel32.  The two type-3
entries in `0x428100..0x428180` are exactly `0x00428129` and `0x0042817C`; the window
`0x0042812F..0x00428133` carries none, and this script re-checks that on every run.

WHY NO REFRESH CODE IS NEEDED -- the native LISTBOX already sends LBN_SELCHANGE for a
keyboard move exactly as it does for a click, and `StdCtrls.TCustomListBox.CNCommand
@0x41352984` (vcl30.dpl) turns that into OnClick:

    41352987  mov  ax,[edx+6]             ; NotifyCode
    4135298B  dec  ax / je  0x41352997    ; 1 = LBN_SELCHANGE
    41352997  call Controls.TControl.Changed
    413529A0  mov  bx,0xfff0 / call @CallDynaInst     ; = Click -> OnClick
    413529AB  ..                          ; 2 = LBN_DBLCLK -> bx 0xffef

so `AbilityListBoxClick @0x0042C33C` and `SpellListBoxClick @0x0042BF60` fire unchanged
(the DFM wires both as `OnClick`, published method table entries `0x0042BF60` /
`0x0042C33C`).  One hook serves both lists; no refresh code exists in this cave.

SCOPE: the cave whitelists ONLY the two listboxes.  Comparing `TMsg.hwnd` against
`HSMEdit.Handle` instead would be one comparison shorter and would hand the arrows back
to every control on the form -- a behaviour change nobody asked for.

--------------------------------------------------------------------------------------
DEFECT 2 -- `SpellListBoxClick` guards on the WRONG listbox (a vanilla copy-paste bug)
--------------------------------------------------------------------------------------
    0042BF84  mov  eax,[0x432898] / cmp dword ptr [eax],0 / je bail   ; map loaded?
    0042BF92  8B 83 A0 04 00 00   mov  eax,[ebx+0x4a0]    ; <-- AbilityListBox. WRONG.
    0042BF98  call StdCtrls.TCustomListBox.GetItemIndex
    0042BF9D  inc  eax / je bail                          ; index -1 -> do nothing
    0042BFA4  mov  esi,[ebx+0x4dc]                        ; ..then works off SpellListBox

So the Spells panel stays blank until an ability has been selected at least once, in the
same session.  One byte at `0x0042BF94`: `A0` -> `DC`.

⚠ `AbilityListBoxClick`'s own copy of the same idiom is CORRECT and is not touched:
`0x0042C362` = `0f 84 86 01 00 00` (the map-loaded guard), `0x0042C368` =
`mov eax,[esi+0x4a0]`, which is the ability list and is what it should read.

--------------------------------------------------------------------------------------
OFFSETS -- verified against TMainForm's PUBLISHED FIELD TABLE, not inferred
--------------------------------------------------------------------------------------
Field table `0x00425D92`, 305 entries (VMT-0x2C), parsed entry by entry:

    +0x22C = HSMEdit           (class idx 5)     the editor document
    +0x4A0 = AbilityListBox    (class idx 19)    }  same class -- both TListBox
    +0x4DC = SpellListBox      (class idx 19)    }
    +0x240 = MORPageControl    +0x244 = SurfaceSheet   (unused here, for orientation)

    +0xCC  = TWinControl.FHandle, from `Controls.TWinControl.GetHandle @0x41346158`
             in vcl30.dpl: `call HandleNeeded / mov eax,[ebx+0xcc] / ret`.

⚠ A wrong offset here is SILENT -- the cave simply never matches and the arrows stay
dead.  Re-derive from the field table, never from a decompile's guess.

--------------------------------------------------------------------------------------
CAVE  0x0052D640, 0x60 bytes, in `.mtb` page slack
--------------------------------------------------------------------------------------
AoWDevEd.exe CANNOT take a 14th section (`e_lfanew` 0x100, 13 section headers ending at
exactly 0x400, which is where CODE's raw data begins).  `.mtb` -- `build_editor_toolbar.py`'s
toolbar-bitmap section -- has VirtualSize 0x4C63B against SizeOfRawData 0x4C800, i.e. 453
bytes of slack at VA `0x0052D63B`, verified all-zero.  The cave takes `0x0052D640..
0x0052D69F`, dword-aligned, leaving 5 bytes below it and 352 above.

`.mtb` VirtualSize 0x4C63B -> 0x4C800 so the cave is formally inside the section rather
than relying on the loader mapping past VirtualSize, and Characteristics 0x40000040 ->
0x60000040 (| IMAGE_SCN_MEM_EXECUTE) because the section is data-only as it stands.
`--undo` restores BOTH.  Raising VirtualSize cannot collide: `.mtb` RVA 0xE1000 + 0x4C800
= 0x12D800, and the next section `.ctp` starts at RVA 0x12E000.  SizeOfImage is unchanged
(the last section still decides it).  `.mtb` carries no base relocations of its own.

Entry state: ESI = TMainForm, EBX = @TMsg, EAX = Screen^.  EAX/ECX/EDX are dead at both
resume points (`0x00428134` reloads eax from `[ebx+0xc]`; `0x00428157` pops ecx/edx as
stack discards), so the cave is free to clobber them.  ESI and EBX are preserved.
`TMsg.hwnd` is at `[ebx+0]` -- for a key message that is the focus window.

    cmp   esi,[eax+0x5c]        ; displaced original
    jne   OUT                   ; some other form is active -> vanilla "not ours"
    mov   eax,[ebx]             ; TMsg.hwnd
    test  eax,eax
    je    CONT                  ; no window -> behave exactly like vanilla
    mov   edx,[esi+0x4a0]       ; AbilityListBox
    test  edx,edx
    je    S1
    cmp   eax,[edx+0xcc]        ; TWinControl.FHandle
    je    OUT                   ; the ability list has focus -> let the key through
S1: mov   edx,[esi+0x4dc]       ; SpellListBox
    test  edx,edx
    je    CONT
    cmp   eax,[edx+0xcc]
    je    OUT                   ; the spell list has focus -> let the key through
CONT: jmp  0x00428134           ; vanilla: forward to HSMEdit, Handled := True
OUT:  jmp  0x00428157           ; vanilla "not ours": Handled stays False

Both editor exes have the fixed base 0x400000, so absolute addressing is permitted here;
the cave uses none beyond the two absolute `jmp rel32` back into CODE.

⚠ FORWARD HAZARD: `0x0052D640..0x0052D69F` in `.mtb` is now owned by this script.
`build_editor_toolbar.py` owns the section itself and is a no-op once `.mtb` exists, but
nothing else may claim that window.  See the cave-ownership table in
`Zig notes/12-re-toolchain.md`.

⚠⚠ FORWARD HAZARD (2026-09-25): `build_deved_casterfamily.py` owns the rest of the slack,
`0x0052D6A0..0x0052D7FF`, and its cave RELIES on the `.mtb` VirtualSize 0x4C800 and
MEM_EXECUTE that this script's `--apply` sets.  `--undo` here puts them back and leaves
that cave past VirtualSize in a non-executable section.  Undo casterfamily FIRST.

--------------------------------------------------------------------------------------
UNDO
--------------------------------------------------------------------------------------
Surgical, touches no backup.  `--undo` restores the 5 hook bytes, zeroes the 0x60-byte
cave window (refusing if it holds bytes this script did not write), and puts `.mtb`'s
VirtualSize and Characteristics back; the guard half restores the single `A0` byte.
`--part` selects one half so undoing one cannot silently revert the other.

--------------------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------------------
    python build_deved_listarrows.py                 dry run: verify the current state
    python build_deved_listarrows.py --apply         patch (backup -> <game dir>\backups\)
    python build_deved_listarrows.py --undo          surgical restore
    python build_deved_listarrows.py --dis           capstone-disassemble the cave
    python build_deved_listarrows.py --apply --part guard    one half only
"""

import os
import shutil
import struct
import sys

import zigexe

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))

from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

IB = 0x400000
TARGET = zigexe.SRC_EDITOR                      # AoWDevEd.exe -- the PATCH SOURCE
LIVE = zigexe.LIVE_EDITOR                       # AoWzEd.exe   -- read-only report only

BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP_SUFFIX = ".pre-listarrows"

# ---- defect 1: the OnMessage arrow filter -------------------------------------------
HOOK = 0x0042812F
HOOK_N = 5
HOOK_ORIG = bytes.fromhex("3b705c7523")         # cmp esi,[eax+0x5c] ; jne 0x428157
RESUME_SWALLOW = 0x00428134                     # vanilla: forward to HSMEdit, Handled:=True
RESUME_PASS = 0x00428157                        # vanilla: "not ours", Handled stays False

CAVE = 0x0052D640
CAVE_SIZE = 0x60
HOST = b".mtb"
HOST_VSZ_ORIG = 0x0004C63B
HOST_VSZ_NEW = 0x0004C800
HOST_CHARS_ORIG = 0x40000040                    # CNT_INITIALIZED_DATA | MEM_READ
HOST_CHARS_NEW = 0x60000040                     # | MEM_EXECUTE

F_ABILITYLIST = 0x4A0                           # TMainForm.AbilityListBox
F_SPELLLIST = 0x4DC                             # TMainForm.SpellListBox
F_FHANDLE = 0xCC                                # TWinControl.FHandle

# ---- defect 2: SpellListBoxClick guards on AbilityListBox ---------------------------
GUARD = 0x0042BF94                              # the disp32 low byte of mov eax,[ebx+0x4a0]
GUARD_ORIG = 0xA0                               # -> [ebx+0x4a0]  AbilityListBox (wrong)
GUARD_NEW = 0xDC                                # -> [ebx+0x4dc]  SpellListBox   (right)
GUARD_CTX = 0x0042BF92                          # whole instruction, for verification
GUARD_CTX_ORIG = bytes.fromhex("8b83a0040000")
GUARD_CTX_NEW = bytes.fromhex("8b83dc040000")

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)


def require(cond, msg):
    if not cond:
        sys.exit("ABORT: " + msg)


# ---------------------------------------------------------------- PE image
class Image:
    def __init__(self, path):
        self.path = path
        self.d = bytearray(open(path, "rb").read())
        d = self.d
        self.e = struct.unpack_from("<I", d, 0x3C)[0]
        self.nsec = struct.unpack_from("<H", d, self.e + 6)[0]
        optsz = struct.unpack_from("<H", d, self.e + 20)[0]
        self.opt = self.e + 24
        self.sectbl = self.opt + optsz
        require(struct.unpack_from("<I", d, self.opt + 28)[0] == IB,
                "%s: unexpected image base" % path)
        self.secs = []
        for i in range(self.nsec):
            b = self.sectbl + i * 40
            name = bytes(d[b:b + 8]).rstrip(b"\0")
            vsz, rva, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
            chars = struct.unpack_from("<I", d, b + 36)[0]
            self.secs.append(dict(name=name, vsz=vsz, rva=rva, rsz=rsz, raw=raw,
                                  chars=chars, hdr=b))

    def off(self, va):
        r = va - IB
        for s in self.secs:
            if s["rva"] <= r < s["rva"] + max(s["vsz"], s["rsz"]):
                o = s["raw"] + (r - s["rva"])
                require(o < len(self.d), "VA %08X is past the end of %s" % (va, self.path))
                return o
        sys.exit("ABORT: VA %08X is not mapped in %s" % (va, self.path))

    def read(self, va, n):
        o = self.off(va)
        return bytes(self.d[o:o + n])

    def write(self, va, b):
        o = self.off(va)
        self.d[o:o + len(b)] = b

    def find_sec(self, name):
        for s in self.secs:
            if s["name"] == name:
                return s
        return None

    def host(self):
        """The cave's host section, with the cave window proved to be inside its RAW data.

        ⚠ Not `off()`: the cave sits ABOVE VirtualSize before the patch, so a VA lookup
        that honours VirtualSize would miss it in the unpatched file and hit it in the
        patched one -- state would depend on the state."""
        s = self.find_sec(HOST)
        require(s is not None, "%s: host section %s is missing" % (self.path, HOST.decode()))
        rel = CAVE - IB - s["rva"]
        require(0 <= rel and rel + CAVE_SIZE <= s["rsz"],
                "%s: the cave 0x%08X+0x%X is outside %s's raw block"
                % (self.path, CAVE, CAVE_SIZE, HOST.decode()))
        return s, s["raw"] + rel

    def relocs(self):
        out = set()
        sec = self.find_sec(b".reloc")
        if not sec:
            return out
        blk = self.d[sec["raw"]:sec["raw"] + min(sec["rsz"], sec["vsz"])]
        i = 0
        while i + 8 <= len(blk):
            page, size = struct.unpack_from("<II", blk, i)
            if size < 8 or i + size > len(blk):
                break
            for j in range(i + 8, i + size, 2):
                w = struct.unpack_from("<H", blk, j)[0]
                if w >> 12:
                    out.add(IB + page + (w & 0xFFF))
            i += size
        return out

    def save(self):
        with open(self.path, "wb") as f:
            f.write(self.d)


# ---------------------------------------------------------------- cave
CAVE_SRC = f"""
        /* entry: esi = TMainForm, ebx = @TMsg, eax = Screen^.  eax/ecx/edx are dead. */
        cmp   esi, dword ptr [eax+0x5c]             /* displaced: Screen.ActiveForm */
        jne   OUT
        mov   eax, dword ptr [ebx]                  /* TMsg.hwnd = the focus window */
        test  eax, eax
        je    CONT
        mov   edx, dword ptr [esi+{F_ABILITYLIST:#x}]
        test  edx, edx
        je    S1
        cmp   eax, dword ptr [edx+{F_FHANDLE:#x}]   /* TWinControl.FHandle */
        je    OUT
S1:
        mov   edx, dword ptr [esi+{F_SPELLLIST:#x}]
        test  edx, edx
        je    CONT
        cmp   eax, dword ptr [edx+{F_FHANDLE:#x}]
        je    OUT
CONT:
        jmp   {RESUME_SWALLOW:#x}                   /* vanilla: swallow for HSMEdit */
OUT:
        jmp   {RESUME_PASS:#x}                      /* vanilla: leave Handled False */
"""


def build_cave():
    body = bytes(ks.asm(CAVE_SRC, CAVE)[0])
    require(len(body) <= CAVE_SIZE,
            "the cave body is %d B, larger than the %d B window" % (len(body), CAVE_SIZE))
    return bytes(bytearray(body) + b"\x00" * (CAVE_SIZE - len(body))), body


def hook_bytes():
    return b"\xE9" + struct.pack("<i", CAVE - (HOOK + HOOK_N))


# ---------------------------------------------------------------- state
def arrows_state(img, blob):
    """('orig' | 'patched' | 'partial' | 'unknown', detail dict)."""
    sec, o = img.host()
    cur_hook = img.read(HOOK, HOOK_N)
    cur_cave = bytes(img.d[o:o + CAVE_SIZE])
    det = dict(hook=cur_hook, cave_blob=cur_cave == blob, cave_zero=set(cur_cave) <= {0},
               vsz=sec["vsz"], chars=sec["chars"])
    if cur_hook not in (HOOK_ORIG, hook_bytes()):
        return "unknown", det
    orig = (cur_hook == HOOK_ORIG and det["cave_zero"]
            and sec["vsz"] == HOST_VSZ_ORIG and sec["chars"] == HOST_CHARS_ORIG)
    new = (cur_hook == hook_bytes() and det["cave_blob"]
           and sec["vsz"] == HOST_VSZ_NEW and sec["chars"] == HOST_CHARS_NEW)
    return ("orig" if orig else "patched" if new else "partial"), det


def guard_state(img):
    cur = img.read(GUARD_CTX, 6)
    if cur == GUARD_CTX_ORIG:
        return "orig", cur
    if cur == GUARD_CTX_NEW:
        return "patched", cur
    return "unknown", cur


def reloc_hits(img):
    """A relocation's dword starts up to 3 bytes before the range and still overlaps it."""
    rel = img.relocs()
    over_hook = sorted(x for x in rel if HOOK - 3 <= x < HOOK + HOOK_N)
    over_guard = sorted(x for x in rel if GUARD - 3 <= x < GUARD + 1)
    over_cave = sorted(x for x in rel if CAVE - 3 <= x < CAVE + CAVE_SIZE)
    return over_hook, over_guard, over_cave


# ---------------------------------------------------------------- reporting
def report(path, label, writable):
    if not os.path.exists(path):
        print("%-14s  MISSING -- skipped" % label)
        return None
    img = Image(path)
    blob, body = build_cave()
    ast, det = arrows_state(img, blob)
    gst, gcur = guard_state(img)
    sec, _o = img.host()
    print("%-14s  %s" % (label, "" if writable else "(READ-ONLY -- derived by "
                                                    "build_zigeditor.py)"))
    print("    arrows  %-8s hook 0x%08X = %s  cave 0x%08X installed=%s zero=%s"
          % (ast, HOOK, det["hook"].hex(" "), CAVE, det["cave_blob"], det["cave_zero"]))
    print("            %s VirtualSize 0x%X (orig 0x%X / new 0x%X)  Characteristics "
          "0x%08X (orig 0x%08X / new 0x%08X)"
          % (HOST.decode(), sec["vsz"], HOST_VSZ_ORIG, HOST_VSZ_NEW,
             sec["chars"], HOST_CHARS_ORIG, HOST_CHARS_NEW))
    print("    guard   %-8s 0x%08X = %s   (byte 0x%08X = %02X, orig %02X / new %02X)"
          % (gst, GUARD_CTX, gcur.hex(" "), GUARD, img.read(GUARD, 1)[0],
             GUARD_ORIG, GUARD_NEW))
    h, g, c = reloc_hits(img)
    print("    .reloc  hook %s  guard %s  cave %s"
          % ("CLEAN" if not h else "!! " + str([hex(x) for x in h]),
             "CLEAN" if not g else "!! " + str([hex(x) for x in g]),
             "CLEAN" if not c else "!! " + str([hex(x) for x in c])))
    return img, ast, gst


def show_state():
    report(os.path.join(GAME, TARGET), TARGET, True)
    print()
    report(os.path.join(GAME, LIVE), LIVE, False)


def disassemble():
    blob, body = build_cave()
    print("==== cave 0x%08X in %s  (%d of %d B used, %d free) ===="
          % (CAVE, HOST.decode(), len(body), CAVE_SIZE, CAVE_SIZE - len(body)))
    for i in cs.disasm(body, CAVE):
        print("  %08X  %-22s %s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str))
    print("\n---- displaced hook site ----")
    print("  %08X  before  %s" % (HOOK, HOOK_ORIG.hex(" ")))
    for i in cs.disasm(HOOK_ORIG, HOOK):
        print("            %-22s %s %s" % (i.bytes.hex(" "), i.mnemonic, i.op_str))
    print("  %08X  after   %s" % (HOOK, hook_bytes().hex(" ")))
    for i in cs.disasm(hook_bytes(), HOOK):
        print("            %-22s %s %s" % (i.bytes.hex(" "), i.mnemonic, i.op_str))
    print("\n---- SpellListBoxClick guard ----")
    for tag, b in (("before", GUARD_CTX_ORIG), ("after ", GUARD_CTX_NEW)):
        for i in cs.disasm(b, GUARD_CTX):
            print("  %08X  %s  %-22s %s %s"
                  % (GUARD_CTX, tag, i.bytes.hex(" "), i.mnemonic, i.op_str))


# ---------------------------------------------------------------- apply / undo
def backup(img, ast, gst):
    """Mint a snapshot ONLY from a file positively proved unpatched.

    ⚠ The gate is the POSITIVE test -- the hook site reading vanilla 3b705c7523 AND the
    guard byte reading A0 -- never `not os.path.exists(BACKUP)`.  On --undo the current
    file IS the patched state, and on a re-apply it is this script's own previous output;
    an existence check accepts both and mints a `.pre-*` that looks authoritative and is a
    snapshot of a patched binary."""
    if not (ast == "orig" and gst == "orig"):
        print("    no backup taken (%s is not fully unpatched: arrows=%s guard=%s)"
              % (os.path.basename(img.path), ast, gst))
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dst = os.path.join(BACKUP_DIR, os.path.basename(img.path) + BACKUP_SUFFIX)
    if os.path.exists(dst):
        print("    backup already exists: %s" % dst)
        return
    shutil.copyfile(img.path, dst)
    print("    backup -> %s" % dst)


def apply_arrows(img, blob):
    sec, o = img.host()
    require(img.read(HOOK, HOOK_N) == HOOK_ORIG,
            "%08X: verify-before-write failed\n  exp %s\n  got %s"
            % (HOOK, HOOK_ORIG.hex(" "), img.read(HOOK, HOOK_N).hex(" ")))
    require(set(img.d[o:o + CAVE_SIZE]) <= {0},
            "the cave window 0x%08X..0x%08X in %s is not zero"
            % (CAVE, CAVE + CAVE_SIZE - 1, HOST.decode()))
    require(sec["vsz"] == HOST_VSZ_ORIG,
            "%s VirtualSize is 0x%X, expected 0x%X -- its owner may have grown"
            % (HOST.decode(), sec["vsz"], HOST_VSZ_ORIG))
    require(sec["chars"] == HOST_CHARS_ORIG,
            "%s Characteristics are 0x%08X, expected 0x%08X"
            % (HOST.decode(), sec["chars"], HOST_CHARS_ORIG))
    img.d[o:o + CAVE_SIZE] = blob
    struct.pack_into("<I", img.d, sec["hdr"] + 8, HOST_VSZ_NEW)
    struct.pack_into("<I", img.d, sec["hdr"] + 36, HOST_CHARS_NEW)
    img.write(HOOK, hook_bytes())
    print("    arrows: hook 0x%08X -> cave 0x%08X, %s VirtualSize 0x%X->0x%X, "
          "Characteristics 0x%08X->0x%08X"
          % (HOOK, CAVE, HOST.decode(), HOST_VSZ_ORIG, HOST_VSZ_NEW,
             HOST_CHARS_ORIG, HOST_CHARS_NEW))


def undo_arrows(img, blob):
    sec, o = img.host()
    cur = img.read(HOOK, HOOK_N)
    require(cur in (HOOK_ORIG, hook_bytes()),
            "%08X holds bytes this script did not write: %s" % (HOOK, cur.hex(" ")))
    win = bytes(img.d[o:o + CAVE_SIZE])
    require(win == blob or set(win) <= {0},
            "the cave window holds bytes this script did not write -- refusing to zero it")
    require(sec["vsz"] in (HOST_VSZ_ORIG, HOST_VSZ_NEW),
            "%s VirtualSize is 0x%X -- refusing to guess what to restore"
            % (HOST.decode(), sec["vsz"]))
    require(sec["chars"] in (HOST_CHARS_ORIG, HOST_CHARS_NEW),
            "%s Characteristics are 0x%08X -- refusing to guess what to restore"
            % (HOST.decode(), sec["chars"]))
    img.write(HOOK, HOOK_ORIG)
    img.d[o:o + CAVE_SIZE] = b"\x00" * CAVE_SIZE
    struct.pack_into("<I", img.d, sec["hdr"] + 8, HOST_VSZ_ORIG)
    struct.pack_into("<I", img.d, sec["hdr"] + 36, HOST_CHARS_ORIG)
    print("    arrows: restored hook, zeroed the cave, %s VirtualSize/Characteristics back"
          % HOST.decode())


def apply_guard(img):
    cur = img.read(GUARD_CTX, 6)
    require(cur == GUARD_CTX_ORIG,
            "%08X: verify-before-write failed\n  exp %s\n  got %s"
            % (GUARD_CTX, GUARD_CTX_ORIG.hex(" "), cur.hex(" ")))
    img.write(GUARD, bytes([GUARD_NEW]))
    print("    guard : 0x%08X %02X -> %02X  (SpellListBoxClick now reads SpellListBox)"
          % (GUARD, GUARD_ORIG, GUARD_NEW))


def undo_guard(img):
    cur = img.read(GUARD_CTX, 6)
    require(cur in (GUARD_CTX_ORIG, GUARD_CTX_NEW),
            "%08X holds bytes this script did not write: %s" % (GUARD_CTX, cur.hex(" ")))
    img.write(GUARD, bytes([GUARD_ORIG]))
    print("    guard : 0x%08X restored to %02X" % (GUARD, GUARD_ORIG))


def run(part, apply_=False, undo=False):
    path = os.path.join(GAME, TARGET)
    require(os.path.exists(path), "%s is missing" % TARGET)
    img = Image(path)
    blob, _body = build_cave()
    ast, _det = arrows_state(img, blob)
    gst, _g = guard_state(img)
    h, g, c = reloc_hits(img)
    require(not h, "a base relocation overlaps the hook window: %s" % [hex(x) for x in h])
    require(not g, "a base relocation overlaps the guard byte: %s" % [hex(x) for x in g])
    require(not c, "a base relocation lands inside the cave: %s" % [hex(x) for x in c])
    require(ast != "unknown", "%s: the hook site holds unrecognised bytes" % TARGET)
    require(gst != "unknown", "%s: the guard site holds unrecognised bytes" % TARGET)
    print("%s: arrows=%s guard=%s  (.reloc clean)" % (TARGET, ast, gst))

    do_arrows = part in ("both", "arrows")
    do_guard = part in ("both", "guard")
    touched = False

    if undo:
        if do_arrows:
            if ast == "orig":
                print("    arrows: already unpatched, nothing to do")
            else:
                undo_arrows(img, blob)
                touched = True
        if do_guard:
            if gst == "orig":
                print("    guard : already unpatched, nothing to do")
            else:
                undo_guard(img)
                touched = True
    else:
        todo = []
        if do_arrows and ast != "patched":
            require(ast == "orig",
                    "arrows state is %r -- this feature has no in-place re-tune path; run "
                    "--undo --part arrows first" % ast)
            todo.append("arrows")
        if do_guard and gst != "patched":
            require(gst == "orig", "guard state is %r" % gst)
            todo.append("guard")
        if not todo:
            print("    already patched, nothing to do")
        elif not apply_:
            print("    dry run: would patch %s" % ", ".join(todo))
        else:
            backup(img, ast, gst)
            if "arrows" in todo:
                apply_arrows(img, blob)
            if "guard" in todo:
                apply_guard(img)
            touched = True

    if touched:
        try:
            img.save()
        except PermissionError:
            kill_aow()
            try:
                img.save()
            except PermissionError:
                sys.exit("ABORT: %s is still locked after killing AoW processes" % TARGET)
        print("    written")
        # ASCII only in anything PRINTED: the console here is cp1252 and a bare U+26A0
        # raised UnicodeEncodeError *after* the file was already saved.
        print("    !! NOW RUN:  python build_zigeditor.py --apply   "
              "(else %s still carries the old bytes)" % LIVE)

    print()
    show_state()


def kill_aow():
    """Standing authorisation (CLAUDE.md): kill anything holding a game binary open.

    The list comes from zigexe.LOCKING_PROCESSES; the anchored `^...$` matters, because an
    unanchored match also hits AowEmailWrapper, which locks nothing."""
    import subprocess
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match '^(%s)$' } | Stop-Process -Force"
         % "|".join(zigexe.LOCKING_PROCESSES)],
        capture_output=True)


def main():
    args = sys.argv[1:]
    part = "both"
    if "--part" in args:
        i = args.index("--part")
        require(i + 1 < len(args) and args[i + 1] in ("arrows", "guard", "both"),
                "--part takes arrows | guard | both")
        part = args[i + 1]
    print("Editor Abilities/Spells lists: UP/DOWN arrows move the selection  (%s)" % TARGET)
    print("part=%s   cave 0x%08X in %s (%d B)\n" % (part, CAVE, HOST.decode(), CAVE_SIZE))
    if "--dis" in args or "--show" in args:
        disassemble()
        return
    if "--undo" in args:
        run(part, undo=True)
        return
    if "--apply" in args:
        run(part, apply_=True)
        return
    run(part)
    print("\n(dry run -- nothing written; use --apply)")


if __name__ == "__main__":
    main()
