r"""Editor Level Up / Level Down follow the DISPLAY order of a 4-level map.

Companion to `build_skylevel_ui.py` (the game's World Map level strip).  A 4th map level is
STORED at index 3 and DISPLAYED ABOVE Surface, captioned "Firmament":

    display order (more than 3 levels):  slot 0 1 2 3  ->  level 3 0 1 2
                                         "Firmament | Surface | Caverns | Depths"
    display order (3 levels or fewer):   identity     ->  vanilla behaviour, byte for byte

The editor's Level Up / Level Down speed buttons step the STORED level by -1 / +1, so after
Add Level the 4th level lands below Depths and Firmament is unreachable from Surface.  This
script makes both buttons step the SLOT instead: level -> slot (RORDER), slot -/+ 1, clamp,
slot -> level (ORDER).

Target: `Ziggurat\AoWDevEd.exe` (zigexe.SRC_EDITOR), and nothing else.  The game exes are NOT
touched (that is `build_skylevel_ui.py`); nor is `AoWEPACK.dpl` or the New Map dialog.

================================================================================
⚠⚠ THE EDITOR EXE TRAP -- an editor patch is TWO steps
================================================================================
`Ziggurat\AoWDevEd.exe` is the PATCH SOURCE, and nothing runs it.  The editor the owner
actually launches is `Ziggurat\AoWzEd.exe` (zigexe.LIVE_EDITOR), which `build_zigeditor.py`
REBUILDS from AoWDevEd.exe.  Skip the second step and the patch sits in a file no one loads
-- silently:

    python build_deved_levelnav.py --apply    # patches Ziggurat\AoWDevEd.exe
    python build_zigeditor.py      --apply    # rebuilds -> Ziggurat\AoWzEd.exe

(build_zigeditor.py takes --apply / --undo / --png PATH; no args = dry run.)

⚠ `AoWEd.exe` WAS the second target and is NO LONGER ONE.  The 2026-09-09 move left no copy
in the overlay -- only the game root's stock one, which is VANILLA and must never be patched.
Its `TMainForm` body is structurally identical here and its addresses run **0x64 BELOW**
AoWDevEd.exe's in this region, but its import thunks and its map global sit elsewhere, which
is why every site was declared and byte-verified per binary rather than derived by offset.
Kept as reusable RE machinery, NOT as a live target:

    cave_mode  section (stock 6-section file: 7 free header slots, so `.lvn` fits)
    mapglob    0x00432898        setpage 0x004023E8
    up_hook    0x00429EA2 n=30   up_resume 0x00429EC0   up_noop 0x00429F77
      up_orig  80b81d020000000f84c80000000fbe901d02000083ea017105e86071fdff
    dn_hook    0x00429D4A n=17   dn_resume 0x00429D80   dn_noop 0x00429E3B
      dn_orig  0fbe901d02000083c2017105e8c572fdff
    fl_hook    0x00429F51 n=9    fl_set    0x00429F5A   fl_skip 0x00429F6B
      fl_orig  80b81d020000007511
    sm_hook    0x00429CB0 n=23   sm_after  0x00429CD8   sm_surf 0x00429CC7
      sm_orig  85f67e138b93840200008b8340020000e82387fdffeb11

--------------------------------------------------------------------------------------
THE FOUR SITES  (AoWDevEd.exe addresses; image base 0x400000, byte-verified 2026-09-06)
--------------------------------------------------------------------------------------
Both handlers reach the editor document as `THSMEdit = [TMainForm+0x22C]`, hold the current
level in the SIGNED BYTE `[THSMEdit+0x21D]`, and have already passed the "map loaded" guard
`[THSMEdit+0x1BC] != 0` before any hook site below.  The live level count is
`[[[MAPGLOB]]+0x10]+0x14` -- the very chain vanilla's Level Down already walks.

1. `TMainForm.LevelUpBtnClick @0x00429ED8`  ("up" = towards slot 0)

   hook 0x00429F06, 30 bytes -> `E9 <cave_up>` + 25 nops
       before  80 b8 1d 02 00 00 00   cmp  byte ptr [eax+0x21d], 0
               0f 84 c8 00 00 00      je   0x00429FDB          ; level 0 -> do nothing
               0f be 90 1d 02 00 00   movsx edx, byte ptr [eax+0x21d]
               83 ea 01               sub  edx, 1
               71 05                  jno  0x00429F24
               e8 fc 70 fd ff         call 0x00401020          ; System.@IntOver
   The cave maps level->slot, refuses at slot 0 by jumping to the function's own no-op exit
   0x00429FDB, else steps the slot down, maps back to a level and resumes at 0x00429F24 --
   the vanilla `bound edx,[0x0042A00C] / call SetSceneLevel` pair, left untouched.

   ⚠ The displaced range STOPS at 0x00429F23 on purpose.  0x00429F26 is the absolute dword
   of `bound edx, qword ptr [0x0042A00C]` and carries a type-3 base relocation; a longer
   displacement would have the loader apply that fixup on top of cave code.  0x00429F06..
   0x00429F23 carries no relocation at all (the script re-checks this from the .reloc
   directory on every run, per binary, and aborts if it ever stops being true).

2. `TMainForm.LevelDownBtnClick @0x00429D80`  ("down" = towards the last slot)

   hook 0x00429DAE, 17 bytes -> `E9 <cave_dn>` + 12 nops
       before  0f be 90 1d 02 00 00   movsx edx, byte ptr [eax+0x21d]
               83 c2 01               add  edx, 1
               71 05                  jno  0x00429DBF
               e8 61 72 fd ff         call 0x00401020
   The cave maps level->slot, refuses when the slot is already the last (`slot+1 >= count`)
   by jumping to 0x00429E9F, else steps the slot up, maps back and resumes at **0x00429DE4**
   -- skipping vanilla's `slot+1 == count` test and its second copy of the increment
   (0x00429DBF..0x00429DE3), which become dead code.  That dead run is LEFT IN PLACE so its
   relocation at 0x00429DC1 (the `0x0043289C` dword) stays valid; the resume point's own
   relocation at 0x00429DE6 is untouched for the same reason.

3. Level Up's page-control flip -- hook 0x00429FB5, 9 bytes -> `E9 <cave_upflip>` + 4 nops
       before  80 b8 1d 02 00 00 00   cmp  byte ptr [eax+0x21d], 0
               75 11                  jne  0x00429FCF
   Vanilla activates the SURFACE page (`[TMainForm+0x244]`) only when the new level is 0.
   The cave activates it when the new level is 0 **or 3**, so Firmament gets the surface
   page rather than the underground one.  It re-uses vanilla's own two branch targets --
   0x00429FBE (set the page) and 0x00429FCF (leave it) -- and duplicates no code.

   Level DOWN's flip needs no change and is not touched: a down step can only ever land on
   levels 0..2, and vanilla's `cmp byte,0 / jle` already leaves the surface page alone for 0
   and selects the underground page for 1 and 2.

4. `TMainForm.SetMapLevel @0x00429C68` -- hook 0x00429D14, 23 bytes -> `E9 <cave_smp>` + 18
   nops.  Vanilla is `test esi,esi / jle surface` (esi = the requested level), i.e.
   "anything above 0 is underground".  The cave makes it "1 or 2 is underground, everything
   else is the surface page" via `lea eax,[esi-1] / cmp eax,1 / ja surface`, which is
   identical to vanilla for every level a 3-level map can hold and puts level 3 on the
   surface page.  eax is dead at that point (the preceding `TStatusPanel.SetText` returns
   nothing either branch reads) and both vanilla branch targets are re-used unchanged.

--------------------------------------------------------------------------------------
CAVE
--------------------------------------------------------------------------------------
0x180 bytes:

    cave+0x000  ORDER[4]   slot  -> level  = 3, 0, 1, 2
    cave+0x010  RORDER[4]  level -> slot   = 1, 2, 3, 0
    cave+0x020  cave_up, cave_dn, cave_upflip, cave_smp, packed and dword-aligned (236 B)

Two homing modes exist because the two binaries had different amounts of PE header left.
Only `slack` is reachable now; `section` is kept because it is generic and the retired
AoWEd.exe used it -- **a new section `.lvn` @0x004DF000**, appended with the usual
add-section pattern (`build_editor_autosave.py` / `build_spellcast_card_v2.py`),
characteristics 0xE0000060 = code / execute / read / write.

**AoWDevEd.exe -- page slack inside `.tres` @0x00592080.**  ⚠ AoWDevEd.exe CANNOT take
another section: `e_lfanew` is 0x100 and its 13 section headers end at exactly 0x400, which
is where CODE's raw data begins -- there is not one spare byte for a 14th descriptor, and
the seven custom sections already there (`.dlgd` dlgdirs, `.mtb` toolbar, `.ctp` terrain
palette, `.vgo` validation-goto, `.pty` party random, `.tres` timer resolution, `.nmg` new
map gen) used the room up.  `.tres` is the right host: it is already read/write/execute, its
owner `build_editor_timerres.py` uses a fixed 118 (0x76) bytes of a 512-byte raw block and
has no growth path, and every byte from 0x76 to 0x200 is verified zero before anything is
written.  The cave starts at +0x80, leaving a 10-byte gap above the timerres cave, and
`.tres`'s VirtualSize is raised 0x76 -> 0x200 so the bytes are formally part of the section
rather than relying on the loader mapping past VirtualSize.  `--undo` zeroes the 0x180-byte
window and puts VirtualSize back to 0x76.

⚠ FORWARD HAZARD: `build_editor_timerres.py` must never be allowed to grow past
`.tres`+0x80, and nothing else may claim `0x00592080..0x005921FF`.  See the cave-ownership
table in `Zig notes/12-re-toolchain.md`.

Both editor exes have the fixed base 0x400000 and neither cave is position-independent --
absolute addresses are correct here and the section carries no relocations of its own.
The cave contains no filesystem path and no username.  It makes no random draw of any kind.

--------------------------------------------------------------------------------------
UNDO
--------------------------------------------------------------------------------------
`--undo` is surgical and touches no backup.  It restores the four original byte-runs, then
reclaims the cave: in `slack` mode by zeroing the 0x180-byte window in `.tres` and restoring
that section's VirtualSize to 0x76; in `section` mode by dropping `.lvn` (which is by
construction the LAST section header and the LAST raw block in the file, so the removal is a
header-slot zero, a NumberOfSections decrement, a recomputed SizeOfImage and a truncate back
to the section's own raw offset -- refused unless it really is last in both senses).

--------------------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------------------
    python build_deved_levelnav.py           dry run: verify the current state
    python build_deved_levelnav.py --apply    patch (backup to <game dir>\backups\)
    python build_deved_levelnav.py --undo     surgical restore
    python build_deved_levelnav.py --dis      capstone-disassemble every cave block
"""

import os, sys, struct, shutil

import zigexe

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(GAME, "Modding Resources", "re_tools"))

from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

IB = 0x400000
SEC_NAME = b".lvn"
SEC_SIZE = 0x180
SEC_CHARS = 0xE0000060                    # code | execute | read | write
SAVED_HDR = 0x100                         # cave window holding the 40 bytes the new section
SAVED_HDR_N = 40                          # header slot displaced -- see drop_section()
BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP_SUFFIX = ".pre-levelnav"

ORDER_VALS = (3, 0, 1, 2)                 # slot  -> level
RORDER_VALS = (1, 2, 3, 0)                # level -> slot

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)


def require(cond, msg):
    if not cond:
        sys.exit("ABORT: " + msg)


def align(x, a):
    return (x + a - 1) // a * a


# ---------------------------------------------------------------- per-binary site table
# ⚠ ONE target. AoWEd.exe was the second and is retired (see the trap in the docstring, which
# keeps its whole site table). Sites are declared per binary, never derived by offset.
TARGETS = {
    zigexe.SRC_EDITOR: dict(
        # no PE header room for a 14th section -- the cave lives in .tres page slack
        cave_mode="slack", host=b".tres", cave=0x00592080,
        host_vsz_orig=0x76, host_vsz_new=0x200,
        mapglob=0x0043289C,               # -> THSMap container -> +0x10 -> +0x14 = level count
        setpage=0x004023F0,               # VCL30 ComCtrls.TPageControl.SetActivePage thunk
        up_hook=0x00429F06, up_n=30, up_resume=0x00429F24, up_noop=0x00429FDB,
        up_orig="80b81d020000000f84c80000000fbe901d02000083ea017105e8fc70fdff",
        dn_hook=0x00429DAE, dn_n=17, dn_resume=0x00429DE4, dn_noop=0x00429E9F,
        dn_orig="0fbe901d02000083c2017105e86172fdff",
        fl_hook=0x00429FB5, fl_n=9, fl_set=0x00429FBE, fl_skip=0x00429FCF,
        fl_orig="80b81d020000007511",
        sm_hook=0x00429D14, sm_n=23, sm_after=0x00429D3C, sm_surf=0x00429D2B,
        sm_orig="85f67e138b93840200008b8340020000e8c786fdffeb11",
    ),
}


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
        self.salign = struct.unpack_from("<I", d, self.opt + 32)[0]
        self.falign = struct.unpack_from("<I", d, self.opt + 36)[0]
        require(struct.unpack_from("<I", d, self.opt + 28)[0] == IB,
                "%s: unexpected image base" % path)
        self.secs = []
        for i in range(self.nsec):
            b = self.sectbl + i * 40
            name = bytes(d[b:b + 8]).rstrip(b"\0")
            vsz, rva, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
            self.secs.append(dict(name=name, vsz=vsz, rva=rva, rsz=rsz, raw=raw, hdr=b))

    # -- addressing -----------------------------------------------------------
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

    # -- .reloc ---------------------------------------------------------------
    def relocs(self):
        out = set()
        sec = [s for s in self.secs if s["name"] == b".reloc"]
        if not sec:
            return out
        s = sec[0]
        blk = self.d[s["raw"]:s["raw"] + min(s["rsz"], s["vsz"])]
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

    # -- section ops ----------------------------------------------------------
    def find_sec(self, name):
        for s in self.secs:
            if s["name"] == name:
                return s
        return None

    def sizeofimage(self):
        return struct.unpack_from("<I", self.d, self.opt + 56)[0]

    def save(self):
        with open(self.path, "wb") as f:
            f.write(self.d)


# ---------------------------------------------------------------- cave source
def _count(reg, mapglob):
    return f"""
        mov  {reg}, dword ptr [{mapglob:#x}]
        mov  {reg}, dword ptr [{reg}]
        mov  {reg}, dword ptr [{reg}+0x10]
        mov  {reg}, dword ptr [{reg}+0x14]
    """


def cave_sources(cfg, cave):
    order, rorder = cave + 0x00, cave + 0x10
    src_up = f"""
        /* entry: eax = THSMEdit, map already known loaded.  ecx/edx are scratch. */
        movsx edx, byte ptr [eax+0x21d]                 /* current level */
        {_count('ecx', cfg['mapglob'])}
        cmp  ecx, 3
        jle  Uslot
        cmp  edx, 3
        ja   Uslot
        mov  edx, dword ptr [edx*4 + {rorder:#x}]       /* level -> slot */
Uslot:
        test edx, edx
        jle  Unoop                                      /* already the topmost slot */
        dec  edx
        cmp  ecx, 3
        jle  Uout
        cmp  edx, 3
        ja   Uout
        mov  edx, dword ptr [edx*4 + {order:#x}]        /* slot -> level */
Uout:
        jmp  {cfg['up_resume']:#x}
Unoop:
        jmp  {cfg['up_noop']:#x}
"""
    src_dn = f"""
        /* entry: eax = THSMEdit, map already known loaded.  ecx/edx are scratch. */
        movsx edx, byte ptr [eax+0x21d]
        {_count('ecx', cfg['mapglob'])}
        cmp  ecx, 3
        jle  Dslot
        cmp  edx, 3
        ja   Dslot
        mov  edx, dword ptr [edx*4 + {rorder:#x}]
Dslot:
        inc  edx
        cmp  edx, ecx
        jge  Dnoop                                      /* already the last slot */
        cmp  ecx, 3
        jle  Dout
        cmp  edx, 3
        ja   Dout
        mov  edx, dword ptr [edx*4 + {order:#x}]
Dout:
        jmp  {cfg['dn_resume']:#x}
Dnoop:
        jmp  {cfg['dn_noop']:#x}
"""
    src_fl = f"""
        /* entry: eax = THSMEdit (just reloaded), edx dead.  Surface page for level 0 or 3. */
        mov  dl, byte ptr [eax+0x21d]
        dec  dl
        cmp  dl, 1
        ja   Fset                                       /* level-1 not in {{0,1}} => 0 or 3 */
        jmp  {cfg['fl_skip']:#x}
Fset:
        jmp  {cfg['fl_set']:#x}
"""
    src_sm = f"""
        /* entry: esi = requested level, ebx = TMainForm, eax dead. */
        lea  eax, [esi-1]
        cmp  eax, 1
        ja   Msurf                                      /* not 1 or 2 => surface page */
        mov  edx, dword ptr [ebx+0x284]                 /* underground page */
        mov  eax, dword ptr [ebx+0x240]                 /* the TPageControl */
        call {cfg['setpage']:#x}
        jmp  {cfg['sm_after']:#x}
Msurf:
        jmp  {cfg['sm_surf']:#x}
"""
    return [("cave_up", src_up), ("cave_dn", src_dn),
            ("cave_upflip", src_fl), ("cave_smp", src_sm)]


BLOCK_NAMES = ["cave_up", "cave_dn", "cave_upflip", "cave_smp"]


def build_cave(cfg, cave):
    """Assemble the four blocks sequentially from cave+0x20.  No forward references exist
    between blocks, so one pass is exact."""
    addrs, parts, va = {}, {}, cave + 0x20
    for name, src in cave_sources(cfg, cave):
        b = bytes(ks.asm(src, va)[0])
        addrs[name] = va
        parts[name] = b
        va += len(b)
        va = (va + 3) & ~3
    used = va - cave
    require(used <= SEC_SIZE, "cave content is %d B, larger than the %d B section"
            % (used, SEC_SIZE))

    require(used <= SAVED_HDR, "the cave body overruns the saved-header window")
    blob = bytearray(SEC_SIZE)
    for i, v in enumerate(ORDER_VALS):
        struct.pack_into("<I", blob, 0x00 + i * 4, v)
    for i, v in enumerate(RORDER_VALS):
        struct.pack_into("<I", blob, 0x10 + i * 4, v)
    for name, b in parts.items():
        o = addrs[name] - cave
        blob[o:o + len(b)] = b
    return bytes(blob), addrs, parts, used


def hook_bytes(at, dst, n):
    require(n >= 5, "hook at %08X is only %d bytes" % (at, n))
    return b"\xE9" + struct.pack("<i", dst - (at + 5)) + b"\x90" * (n - 5)


def sites(cfg):
    """[(label, va, n, original bytes)] in a fixed order."""
    return [("LevelUp   compute 0x%08X" % cfg["up_hook"], cfg["up_hook"], cfg["up_n"],
             bytes.fromhex(cfg["up_orig"]), "cave_up"),
            ("LevelDown compute 0x%08X" % cfg["dn_hook"], cfg["dn_hook"], cfg["dn_n"],
             bytes.fromhex(cfg["dn_orig"]), "cave_dn"),
            ("LevelUp   pageflip 0x%08X" % cfg["fl_hook"], cfg["fl_hook"], cfg["fl_n"],
             bytes.fromhex(cfg["fl_orig"]), "cave_upflip"),
            ("SetMapLevel  flip  0x%08X" % cfg["sm_hook"], cfg["sm_hook"], cfg["sm_n"],
             bytes.fromhex(cfg["sm_orig"]), "cave_smp")]


# ---------------------------------------------------------------- state
def cave_va_of(img, cfg):
    """The VA the cave occupies, installed or planned."""
    if cfg["cave_mode"] == "slack":
        return cfg["cave"]
    s = img.find_sec(SEC_NAME)
    if s:
        return IB + s["rva"]
    return IB + align(max(x["rva"] + max(x["vsz"], x["rsz"]) for x in img.secs), img.salign)


def _mask(b):
    """The cave window with the saved-header slot blanked -- that window holds whatever the
    file already had in the section-table slot .lvn took over, so it is never predictable."""
    b = bytearray(b)
    b[SAVED_HDR:SAVED_HDR + SAVED_HDR_N] = b"\x00" * SAVED_HDR_N
    return bytes(b)


def cave_present(img, cfg, blob):
    """(installed?, empty?) for the cave window."""
    if cfg["cave_mode"] == "slack":
        host = img.find_sec(cfg["host"])
        require(host is not None,
                "%s: host section %s is missing" % (img.path, cfg["host"].decode()))
        o = host["raw"] + (cfg["cave"] - IB - host["rva"])
        require(o + SEC_SIZE <= host["raw"] + host["rsz"],
                "%s: the cave overruns %s's raw block" % (img.path, cfg["host"].decode()))
        cur = bytes(img.d[o:o + SEC_SIZE])
        return cur == blob, set(cur) <= {0}
    s = img.find_sec(SEC_NAME)
    if s is None:
        return False, True
    return _mask(img.d[s["raw"]:s["raw"] + SEC_SIZE]) == _mask(blob), False


def state(img, cfg):
    """('orig' | 'patched' | 'partial' | 'unknown', notes)."""
    cave = cave_va_of(img, cfg)
    blob, addrs, _parts, _used = build_cave(cfg, cave)
    have, empty = cave_present(img, cfg, blob)
    bad, orig_all, new_all = [], True, True
    for label, va, n, orig, block in sites(cfg):
        require(len(orig) == n, "%s: original byte-run length" % label)
        cur = img.read(va, n)
        new = hook_bytes(va, addrs[block], n)
        if cur != orig:
            orig_all = False
        if cur != new:
            new_all = False
        if cur not in (orig, new):
            bad.append("%s: %s" % (label, cur.hex(" ")))
    if bad:
        return "unknown", bad, blob, addrs
    if orig_all and empty:
        return "orig", [], blob, addrs
    if new_all and have:
        return "patched", [], blob, addrs
    return "partial", [], blob, addrs


def reloc_check(img, cfg):
    rel = img.relocs()
    hits = []
    for label, va, n, orig, block in sites(cfg):
        # a relocation's dword starts up to 3 bytes before the range and still overlaps it
        h = [x for x in rel if va - 3 <= x < va + n]
        if h:
            hits.append("%s: %s" % (label, [hex(x) for x in sorted(h)]))
    return hits


# ---------------------------------------------------------------- reporting
def show_state():
    for exe, cfg in TARGETS.items():
        path = os.path.join(GAME, exe)
        if not os.path.exists(path):
            print("%-14s  MISSING -- skipped" % exe)
            continue
        img = Image(path)
        st, bad, blob, addrs = state(img, cfg)
        have, empty = cave_present(img, cfg, blob)
        home = ("%s page slack" % cfg["host"].decode()) if cfg["cave_mode"] == "slack" \
            else ("section %s" % SEC_NAME.decode())
        print("%-14s  %-8s  cave 0x%08X in %s  (installed=%s empty=%s)"
              % (exe, st, cave_va_of(img, cfg), home, have, empty))
        for label, va, n, orig, block in sites(cfg):
            cur = img.read(va, n)
            new = hook_bytes(va, addrs[block], n)
            tag = "ORIG" if cur == orig else ("PATCHED" if cur == new else "?????")
            print("    %-28s %-8s %s" % (label, tag, cur[:8].hex(" ") + (" ..." if n > 8 else "")))
        for b in bad:
            print("    !! " + b)
        hits = reloc_check(img, cfg)
        print("    .reloc over the displaced ranges: %s"
              % ("CLEAN" if not hits else "!! " + "; ".join(hits)))


def disassemble():
    for exe, cfg in TARGETS.items():
        path = os.path.join(GAME, exe)
        if not os.path.exists(path):
            continue
        img = Image(path)
        cave = cave_va_of(img, cfg)
        blob, addrs, parts, used = build_cave(cfg, cave)
        print("==== %s  cave 0x%08X (%d of %d B used) ====" % (exe, cave, used, SEC_SIZE))
        print("  ORDER  slot->level @0x%08X = %s" % (cave, list(ORDER_VALS)))
        print("  RORDER level->slot @0x%08X = %s\n" % (cave + 0x10, list(RORDER_VALS)))
        for name in BLOCK_NAMES:
            print("---- %s @0x%08X (%d B) ----" % (name, addrs[name], len(parts[name])))
            for i in cs.disasm(parts[name], addrs[name]):
                print("  %08X  %-22s %s %s"
                      % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str))
            print()
        print("---- displaced-site replacements ----")
        for label, va, n, orig, block in sites(cfg):
            print("  %-28s %s\n  %-28s %s"
                  % (label, orig.hex(" "), "", hook_bytes(va, addrs[block], n).hex(" ")))
        print()


# ---------------------------------------------------------------- apply / undo
def backup(img):
    """Mint a snapshot ONLY from a file positively proved unpatched."""
    st, _bad, _blob, _addrs = state(img, TARGETS[os.path.basename(img.path)])
    if st != "orig":
        print("    no backup taken (%s is not in the original state: %s)"
              % (os.path.basename(img.path), st))
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dst = os.path.join(BACKUP_DIR, os.path.basename(img.path) + BACKUP_SUFFIX)
    if os.path.exists(dst):
        print("    backup already exists: %s" % dst)
        return
    shutil.copyfile(img.path, dst)
    print("    backup -> %s" % dst)


def install_cave(img, cfg, blob):
    if cfg["cave_mode"] == "slack":
        host = img.find_sec(cfg["host"])
        o = host["raw"] + (cfg["cave"] - IB - host["rva"])
        require(set(img.d[o:o + SEC_SIZE]) <= {0},
                "%s: the cave window 0x%08X..0x%08X in %s is not zero"
                % (img.path, cfg["cave"], cfg["cave"] + SEC_SIZE - 1, cfg["host"].decode()))
        require(host["vsz"] == cfg["host_vsz_orig"],
                "%s: %s VirtualSize is 0x%X, expected 0x%X -- its owner may have grown"
                % (img.path, cfg["host"].decode(), host["vsz"], cfg["host_vsz_orig"]))
        img.d[o:o + SEC_SIZE] = blob
        struct.pack_into("<I", img.d, host["hdr"] + 8, cfg["host_vsz_new"])
        return cfg["cave"]
    return add_section(img, blob)[0]


def remove_cave(img, cfg, blob):
    if cfg["cave_mode"] == "slack":
        host = img.find_sec(cfg["host"])
        o = host["raw"] + (cfg["cave"] - IB - host["rva"])
        cur = bytes(img.d[o:o + SEC_SIZE])
        require(cur == blob or set(cur) <= {0},
                "%s: the cave window holds bytes this script did not write -- refusing to "
                "zero it" % img.path)
        img.d[o:o + SEC_SIZE] = b"\x00" * SEC_SIZE
        struct.pack_into("<I", img.d, host["hdr"] + 8, cfg["host_vsz_orig"])
        return
    if img.find_sec(SEC_NAME) is not None:
        drop_section(img)


def add_section(img, blob):
    """Append .lvn, sized SEC_SIZE, as the last section header and the last raw block."""
    d = img.d
    require(img.sectbl + img.nsec * 40 + 40 <= min(s["raw"] for s in img.secs),
            "%s: no PE header room for another section" % img.path)
    require(img.sizeofimage() == align(max(s["rva"] + s["vsz"] for s in img.secs), img.salign),
            "%s: SizeOfImage is not the plain maximum of the section table -- refusing to "
            "add a section" % img.path)
    newrva = align(max(s["rva"] + max(s["vsz"], s["rsz"]) for s in img.secs), img.salign)
    newraw = align(len(d), img.falign)
    require(newraw == len(d), "%s: the file does not end on a file-alignment boundary" % img.path)
    rawsz = align(SEC_SIZE, img.falign)
    b = img.sectbl + img.nsec * 40
    # The slot .lvn takes over is not necessarily zero (AoWEd.exe's carries stale bytes from
    # its own build).  Park its 40 bytes in the cave so --undo can put them back verbatim.
    blob = bytearray(blob)
    blob[SAVED_HDR:SAVED_HDR + SAVED_HDR_N] = d[b:b + SAVED_HDR_N]
    d += bytes(blob) + b"\x00" * (rawsz - SEC_SIZE)
    struct.pack_into("<8sIIII", d, b, SEC_NAME.ljust(8, b"\0"), SEC_SIZE, newrva, rawsz, newraw)
    struct.pack_into("<IIHHI", d, b + 24, 0, 0, 0, 0, SEC_CHARS)
    struct.pack_into("<H", d, img.e + 6, img.nsec + 1)
    struct.pack_into("<I", d, img.opt + 56, align(newrva + SEC_SIZE, img.salign))
    return IB + newrva, newraw


def drop_section(img):
    """Remove .lvn again.  Refuses unless it is last in the table AND last in the file."""
    s = img.find_sec(SEC_NAME)
    require(s is not None, "%s: no %s section to drop" % (img.path, SEC_NAME.decode()))
    require(s["hdr"] == img.sectbl + (img.nsec - 1) * 40,
            "%s: %s is not the last section header -- refusing to drop it"
            % (img.path, SEC_NAME.decode()))
    require(s["raw"] + s["rsz"] == len(img.d),
            "%s: %s is not the last raw block -- refusing to drop it"
            % (img.path, SEC_NAME.decode()))
    saved = bytes(img.d[s["raw"] + SAVED_HDR:s["raw"] + SAVED_HDR + SAVED_HDR_N])
    del img.d[s["raw"]:]
    img.d[s["hdr"]:s["hdr"] + SAVED_HDR_N] = saved        # exactly what the slot held before
    struct.pack_into("<H", img.d, img.e + 6, img.nsec - 1)
    rest = [x for x in img.secs if x["name"] != SEC_NAME]
    struct.pack_into("<I", img.d, img.opt + 56,
                     align(max(x["rva"] + x["vsz"] for x in rest), img.salign))


def run(undo=False, apply_=False):
    for exe, cfg in TARGETS.items():
        path = os.path.join(GAME, exe)
        if not os.path.exists(path):
            print("%s: MISSING -- skipped" % exe)
            continue
        img = Image(path)
        st, bad, blob, addrs = state(img, cfg)
        require(not bad, "%s: unrecognised bytes -- %s" % (exe, "; ".join(bad)))
        hits = reloc_check(img, cfg)
        require(not hits, "%s: a displaced range carries a base relocation -- %s"
                % (exe, "; ".join(hits)))
        print("%s: %s  (cave 0x%08X, .reloc clean)" % (exe, st, cave_va_of(img, cfg)))

        if undo:
            if st == "orig":
                print("    already unpatched, nothing to do")
                continue
            require(st in ("patched", "partial"), "%s: refusing to undo from %r" % (exe, st))
            for label, va, n, orig, block in sites(cfg):
                img.write(va, orig)
            remove_cave(img, cfg, blob)
        else:
            if st == "patched":
                print("    already patched, nothing to do")
                continue
            require(st == "orig",
                    "%s: state is %r -- this feature has no in-place re-tune path; run "
                    "--undo first" % (exe, st))
            if not apply_:
                print("    dry run: would install the cave and write %d hook sites"
                      % len(sites(cfg)))
                continue
            backup(img)
            for label, va, n, orig, block in sites(cfg):
                cur = img.read(va, n)
                require(cur == orig, "%s @%08X: verify-before-write failed\n  exp %s\n  got %s"
                        % (exe, va, orig.hex(" "), cur.hex(" ")))
            cave = install_cave(img, cfg, blob)
            require(cave == cave_va_of(img, cfg), "cave VA moved between planning and writing")
            for label, va, n, orig, block in sites(cfg):
                img.write(va, hook_bytes(va, addrs[block], n))

        if not apply_ and not undo:
            continue
        try:
            img.save()
        except PermissionError:
            # Standing authorisation (CLAUDE.md): the editors lock their own exe -- kill them.
            kill_aow()
            try:
                img.save()
            except PermissionError:
                sys.exit("ABORT: %s is still locked after killing AoW processes" % exe)
        print("    written")

    print()
    show_state()


def kill_aow():
    """Standing authorisation (CLAUDE.md): kill anything holding a game binary open.

    ⚠ The list comes from zigexe.LOCKING_PROCESSES. Naming the pre-2026-09-09 set here missed
    AoWz/AoWzEd entirely -- the kill reported success and the write still failed. The anchored
    `^...$` matters: an unanchored match also hits AowEmailWrapper, which locks nothing."""
    import subprocess
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match '^(%s)$' } | Stop-Process -Force"
         % "|".join(zigexe.LOCKING_PROCESSES)],
        capture_output=True)


def main():
    args = sys.argv[1:]
    print("Editor Level Up / Level Down follow the display order  (%s)"
          % ", ".join(TARGETS))
    print("order slot->level = %s   cave %d B\n" % (list(ORDER_VALS), SEC_SIZE))
    if "--dis" in args or "--show" in args:
        disassemble()
        return
    if "--undo" in args:
        run(undo=True)
        return
    if "--apply" in args:
        run(apply_=True)
        return
    run()
    print("\n(dry run -- nothing written; use --apply)")


if __name__ == "__main__":
    main()
