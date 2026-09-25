#!/usr/bin/env python3
r"""
AoW1 EDITOR  "Developer > Delete Unused Heroes" and "Delete Unused Items"  --  AoWDevEd.exe ONLY.

DELETE UNUSED ITEMS (added 2026-09-25, from Inioch's share8 patch_devx_prune_unused_v2.py)
  A second Developer-menu item, PruneFreeItemsItem -> PruneFreeItemsClick, same shape as the
  heroes one: count, confirm, delete, SetModified, inside the same render pause/resume.
      delete iff  item[+0x04] (Owner) == nil      -- the item is in no hero, army, site or hex
  over TItemControl = map+0xF4 (TAoWHSMap.Create 0x557748D4), its TList at [ic+8], walked
  downward.  Deletion is AoWE.TItemControl.UnRegisterItem 0x55794F08 (Remove from the list,
  clear the registered flag [item+0x1C]&2, Release -> destroy at refcount 0).  The editor does
  not import it: the cave takes RegisterItem's import (IAT 0x4326E0, preferred 0x55794E7C) plus
  the fixed distance 0x8C and compares 10 bytes of UnRegisterItem's prologue before calling;
  a mismatch shows "AoWEPACK.dpl does not match the expected layout" and deletes nothing.
  The map selection is dropped first (THSMEdit.DeselectPlaceHS) in case it is a victim.
  ⚠ Unplaced items are also GenerateItem's random-treasure pool (the refcount-1 test at
  0x55794F7F): after a prune, sites and hotspots that roll random treasure find nothing.  The
  same kind of consequence as Delete Unused Heroes emptying the join pool.

WHAT IT DOES
  Adds a Developer-menu item that prunes the open map's hero roster down to
      (heroes placed on the map)  U  (leaders)
  and deletes everything else.  TAoWHSMap.InitializeNewMap @0x55777590 bulk-copies the
  whole mapset hero library into every new map's roster; this removes that bloat, and
  the prune persists into the .hsm because THeroControl.ReadWrite @0x5578A304 streams
  the roster under property id 0x14.

THE PREDICATE -- the engine's own test
      delete iff  hero[+0x04] == 0  AND  NOT IsClass(hero, TLeader)
  +0x04 is Engine.TEObject.Owner, the container holding the hero, so ONE test covers
  on-a-tile armies, city garrisons and site-defender armies alike (all TArmy).
  Confirmed three ways: THeroControl.ValidateLibraryHeroes @0x5578A480 frees an orphaned
  library hero only when hero[+4]==0 (`cmp dword ptr [ebx+4],0 / jne` at 0x5578A4CB);
  TPlayer.MakeHeroEmerge @0x55752520 and GlobalSpells.TCallHero.FindCallHero @0x557ECBDC
  pick candidates the same way; TAbstractUnit.SetOwner @0x5577F524 is the only writer.
  Dead heroes (hero[+0x55]&1) and hidden ones (hero[+0x78]) are NOT spared -- user
  ruling 2026-09-08, the predicate above is the whole rule.

TEMPLATE
  TMainForm.RemoveLeadersMIClick @0x0042D598 (138 B) -- a shipping bulk operation over
  the same list with the same IsClass test, inverted.  Loop shape copied verbatim:
  iterate DOWNWARD count-1 -> 0 and re-fetch GetHero after the class test, because
  @IsClass clobbers eax and the deletion mutates the list under the loop.  Per victim:
      call [h_vmt + 0x188]   THero.Deactivate  -- unregisters the power source and
                                                 removes the hero from player[+0x80]
      call [h_vmt + 0x2C]    TAbstractUnit.Release -- refcount 1->0 -> THero.Destroy
                             -> THeroControl.UnRegisterHero -> heroList.RemoveChild
                             -> Changed() -> grid refresh
  Every back-reference is covered by that pair; player[+0xD4] is never reached because
  leaders are excluded, and army membership cannot apply because the predicate demands
  Owner == nil.  No quest or event class resolves a hero -- THeroControl.FindID
  @0x5578A3D8 has exactly three callers (THero.Activate, THero.CanActivate,
  TItemTE.Execute).

  The template's SetOwner(nil) (VMT+0x08, edx=0) is DELIBERATELY OMITTED: the predicate
  guarantees Owner == nil and TAbstractUnit.SetOwner early-outs on
  `cmp esi,[ebx+4] / je` at 0x5577F52B, so it is a provable no-op.

  SetModified(map) is called ONCE after the loop (thunk 0x00401FF0, eax = map).
  RemoveLeadersMIClick omits it -- arguably a vanilla bug; THeroControlGrid.DeleteHero
  does it per hero.  The map-render pause/resume bracket around the work comes from
  TMainForm.DeleteHeroBtnClick @0x0042AD10: [Self+0x22C] = THSMEdit, guard byte
  [edit+0x1BC], THSMEdit VMT +0x90/+0x94 = DisplayC.TCustomDisplay.PauseFrameUpdateLoop /
  ResumeFrameUpdateLoop (resolved through HSEPack.dpl THSMEdit VMT 0x55612564).

CONFIRMATION DIALOG
  Two passes: count, prompt, delete.  The prompt is TMainForm.MsgDlg @0x0042BBE4
  (eax=Self, edx=AnsiString, cl=3 mtConfirmation, push buttons_word, push 0; returns ax,
  6 = mrYes), buttons word 11 = mbYes|mbNo|mbCancel exactly as DeleteHeroBtnClick uses
  it ([0x42ADB0] = 11).  With dlgtype 3 and buttons 11, MsgDlg matches its own constant
  at [0x42BCAC] and takes the Win32 path: @LStrToPChar -> TApplication.MessageBox with
  MB_YESNOCANCEL|MB_ICONQUESTION and the localised ConfirmRStr caption.  That path never
  does LStrAsg on the message, so the AnsiString is consumed entirely inside the call --
  which is why this cave can build it on the STACK (header at [ebp-0x50], refcount -1,
  text at [ebp-0x48]) instead of claiming writable memory.  .ctp is CODE|EXECUTE|READ,
  NOT writable, so a static buffer would have needed either a section-flag change or a
  fresh BSS-slack allocation; neither is worth it for a transient 33-byte message.

  When the count is zero the cave shows an MB_OK|MB_ICONINFORMATION box through
  TApplication.MessageBox directly (thunk 0x00401348, eax=Application, edx=Text PChar,
  ecx=Caption PChar, push flags, ret 4) rather than asking "Delete 0 unused heroes?".
  Both PChars are read-only literals in the cave.  This is the one deviation from the
  spec's "use MsgDlg"; MsgDlg is still the confirm path.

UI
  A TMenuItem sibling inserted immediately after RemoveLeadersItem, the last child of
  DeveloperItems (Caption '&Developer') under MainMenu1:
      name PruneFreeHeroesItem, Caption 'Delete Unused Heroes',
      OnClick PruneFreeHeroesClick
  A new published method name means TMainForm's method table must be RELOCATED with one
  entry appended (it cannot grow in place -- the DFM starts one pad byte after it).
  Same mechanism as build_deved_terrainpal.py: table format is a count word followed by
  {EntrySize:word, Code:dword, Name:shortstr}, and VMT-0x28 is repointed.
      TMainForm VMT 0x00425D00, InstanceSize 0x6AC, VMT-0x28 = 0x00425CD8.
  No TSpeedButton is added to HeroPnl: that panel is hand-packed and the 640x432 dialog
  resize clamp makes geometry changes the expensive kind.  A menu item is free.

CAVE ALLOCATION -- inside .ctp's existing raw data, no new section, no section growth
      .ctp   VA 0x0052E000  file 0x00128E00  VirtualSize 0x61350  SizeOfRawData 0x61400
      0x0052E000..0x0052E05F   build_deved_terrainpal.py's two terrain stubs
      0x0052E060..0x0052ECF2   terrainpal's 134-entry TMainForm method table (3219 B), dead
                               once VMT-0x28 is repointed.  Since 2026-09-25 BOTH HANDLERS
                               LIVE HERE (heroes 0x0052E060, items 0x0052E290, ~1.2 KB),
                               and strip() re-emits the table from the live table's first
                               134 entries before pointing VMT-0x28 back at it
      0x0052ECF4..0x0058E3EC   live TMAINFORM DFM (0x5F644 B + 181 B for the two nodes)
      0x0058E3F0..0x0058F0B7   the relocated 136-entry method table (3272 B)
      ZONE_CEIL 0x0058F100     this script's tail ends here; strip() zeroes up to it and no
                               further, so build_deved_valcircle.py (0x0058F100) and
                               build_deved_gamesettings_tab.py (0x0058F280) above it survive
                               both --apply and --undo
  AoWDevEd.exe is at a fixed ImageBase 0x400000 with DYNAMIC_BASE clear, so the cave may
  use absolute addresses (CLAUDE.md); no .reloc entries are added and none are displaced.
  SizeOfRawData is NOT changed -- .ctp's raw data ends at file 0x18A200, which is exactly
  .vgo's PointerToRawData.  The file length is identical before and after --apply.
  VirtualSize is raised 0x61350 -> 0x61400 so the header states what is really there.

ORDERING AND FORWARD HAZARD
  Run AFTER dlgdirs -> modtoolbar -> terrainpal -> valgoto -> partyrnd -> timerres ->
  levelnav -> newmapgen.
  build_deved_terrainpal.py --apply after this feature is SAFE: its line 389 guard
  ("already patched (.ctp section present) - idempotent no-op") returns before it touches
  the DFM, the method table or the section.  build_editor_toolbar.py has the same guard
  on .mtb.
  !! The real hazard is the inverse.  terrainpal is now INERT, so a future terrain-palette
  change means DELETING .ctp first and re-running it -- and that deletion destroys this
  feature AND build_deved_toolbar_trim.py, both of which live in the section terrainpal
  owns.  Re-apply both behind it, toolbar_trim then heroprune.  This script aborts with a
  chain diagnosis if .ctp is absent.
  !! build_deved_toolbar_trim.py --undo is BLOCKED while this feature is applied: its
  line 483 computes already = (new_blob == blob), and this feature's 92-byte menu node
  makes the live DFM 0x5F6A0 instead of the trimmed 0x5F644, so line 494 refuses with
  "live blob is not the trimmed output - refusing to undo".  Fail-safe, not a defect --
  its snapshot is 0x6065C bytes and restoring it would write straight through this cave
  and the relocated method table.  Undo order is heroprune FIRST, then toolbar_trim.

RNG
  This feature rolls no dice.  rng_audit.py --functions reports
  "AoWDevEd.exe: SYNC 0 site(s) / RAW 3 site(s) in 1 function" (build_party_random.py's
  Randomize + RandInt) before and after; that count must not change.  Nobody should reach
  for a generator here.

CONVENTIONS
  dry-run by default; --apply to write; --dis to disassemble the cave; --undo to revert
  surgically; idempotent; verify-before-write.  --apply over an existing install REWRITES
  in place (strip, then rebuild) so re-tuning never needs revert-and-reapply and never
  mints a second backup.  The backup is gated on a POSITIVE test that the file is
  unpatched by this feature, not on the absence of a backup file:
  backups\AoWDevEd.exe.pre-heroprune.
  AoW.exe / AoWCompat.exe / AoWEPACK.dpl / HSEPack.dpl / AoWEd.exe are untouched.
  AoWEd.exe is out of scope by owner ruling 2026-09-07 (patched but not shipped).

!! APPLIED, UNTESTED until the user opens AoWDevEd.exe.  A wrong method table or a
   malformed DFM makes TMainForm fail to LOAD, and every static check in here still
   passes.

Needs: pip install keystone-engine capstone
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXE = "AoWDevEd.exe"
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
BACKUP_NAME = EXE + ".pre-heroprune"
BASE = 0x400000

# ---- verified against the live AoWDevEd.exe, 2026-09-08 ---------------------------
VMT = 0x00425D00                # TMainForm
VMT_METHODTABLE = VMT - 0x28    # 0x00425CD8
OLD_MT_VA = 0x0052E060          # build_deved_terrainpal.py's relocated table
OLD_MT_COUNT = 134
ZONE_CEIL = 0x0058F100          # this script owns .ctp's tail only up to here (2026-09-25)
OLD_MT_LEN = 3219               # 0x0052E060..0x0052ECF2; the DFM starts one pad byte later
ORIG_DFM_SIZE = 0x0005F644
CTP_NAME = b".ctp"
CTP_VSIZE_OLD = 0x61350
CTP_VSIZE_NEW = 0x61400
CTP_RAWSIZE = 0x61400

MAP_SLOT = 0x0043289C           # IAT: AoWE.AoWHSMap  -- [[slot]] = TAoWHSMap
TLEADER_SLOT = 0x004328AC       # IAT: AoWE..TLeader (class reference)
APP_SLOT = 0x00432224           # IAT: Forms.Application -- [[slot]] = TApplication
T_GETCOUNT = 0x00401E60         # AoWE.THeroControl.GetCount   (eax=hc)
T_GETHERO = 0x00401E58          # AoWE.THeroControl.GetHero    (eax=hc, edx=i)
T_ISCLASS = 0x00401048          # System.@IsClass              (eax=obj, edx=class)
T_SETMODIFIED = 0x00401FF0      # HSEngine.THSMap.SetModified  (eax=map)
T_MSGBOX = 0x00401348           # Forms.TApplication.MessageBox(eax,edx,ecx,+flags) ret 4
MSGDLG = 0x0042BBE4             # TMainForm.MsgDlg (eax,edx,cl,+buttons,+helpctx) ret 8

HC_OFF = 0xF8                   # TAoWHSMap -> THeroControl
OWNER_OFF = 0x04                # Engine.TEObject.Owner
HSMEDIT_OFF = 0x22C             # TMainForm -> THSMEdit
HSMEDIT_GUARD = 0x1BC
DISPLAY_PAUSE = 0x90            # THSMEdit VMT
DISPLAY_RESUME = 0x94
HERO_DEACTIVATE = 0x188         # THero VMT
HERO_RELEASE = 0x2C             # TAbstractUnit VMT
MB_YESNOCANCEL_BUTTONS = 11     # mbYes|mbNo|mbCancel, == the word at [0x0042ADB0]
MT_CONFIRMATION = 3
MR_YES = 6
MB_OK_INFO = 0x40               # MB_OK | MB_ICONINFORMATION

ANCHOR_ITEM = "RemoveLeadersItem"
NEW_ITEM = "PruneFreeHeroesItem"
NEW_CAPTION = "Delete Unused Heroes"
NEW_HANDLER = "PruneFreeHeroesClick"
ITEM_ITEM = "PruneFreeItemsItem"
ITEM_CAPTION = "Delete Unused Items"
ITEM_HANDLER = "PruneFreeItemsClick"

S_PRE = b"Delete \x00"
S_ONE = b" unused hero?\x00"
S_MANY = b" unused heroes?\x00"
S_NONE = b"No unused heroes to delete.\x00"
S_CAP = b"Delete Unused Heroes\x00"
SI_ONE = b" unused item?\x00"
SI_MANY = b" unused items?\x00"
SI_NONE = b"No unused items to delete.\x00"
SI_CAP = b"Delete Unused Items\x00"
SI_BAD = b"AoWEPACK.dpl does not match the expected layout; no items were deleted.\x00"

IC_OFF = 0xF4                   # TAoWHSMap -> TItemControl ([ic+8] = TList of TItem)
T_DESELECT = 0x00402DE8         # HSMEdit.THSMEdit.DeselectPlaceHS (eax=edit)
IAT_REGISTERITEM = 0x004326E0   # IAT: AoWE.TItemControl.RegisterItem (preferred 0x55794E7C)
UNREG_DELTA = 0x55794F08 - 0x55794E7C   # -> TItemControl.UnRegisterItem, not imported
UNREG_SIG = bytes.fromhex("53568bda8bf0f6431c02")
MB_OK_WARN = 0x30


# ---- PE ---------------------------------------------------------------------------
def load_pe(d):
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e + 6)[0]
    optsz = struct.unpack_from('<H', d, e + 20)[0]
    opt = e + 24
    sectbl = opt + optsz
    secs = []
    for i in range(nsec):
        b = sectbl + i * 40
        vsz, va, rsz, raw = struct.unpack_from('<IIII', d, b + 8)
        secs.append((d[b:b + 8].rstrip(b'\0'), va, vsz, raw, rsz, b))
    return dict(e=e, nsec=nsec, opt=opt, sectbl=sectbl, secs=secs,
                salign=struct.unpack_from('<I', d, opt + 32)[0],
                falign=struct.unpack_from('<I', d, opt + 36)[0])


def rva2off(secs, r):
    for _nm, va, vsz, raw, rsz, _b in secs:
        if va <= r < va + max(vsz, rsz):
            return raw + (r - va)
    raise ValueError('rva %#x is in no section' % r)


def va2off(secs, va):
    return rva2off(secs, va - BASE)


def find_dfm_entry(d, F):
    """The TMAINFORM IMAGE_RESOURCE_DATA_ENTRY.  Never hard-code where it points."""
    rrva = struct.unpack_from('<I', d, F['opt'] + 96 + 2 * 8)[0]
    ro = rva2off(F['secs'], rrva)
    hits = []

    def nm_at(v):
        off = ro + (v & 0x7FFFFFFF)
        n = struct.unpack_from('<H', d, off)[0]
        return d[off + 2:off + 2 + 2 * n].decode('utf-16le')

    def walk(diroff, path):
        nn, ni = struct.unpack_from('<HH', d, ro + diroff + 12)
        for i in range(nn + ni):
            eo = ro + diroff + 16 + i * 8
            v, off = struct.unpack_from('<II', d, eo)
            label = nm_at(v) if v & 0x80000000 else '#%d' % v
            if off & 0x80000000:
                walk(off & 0x7FFFFFFF, path + [label])
            elif any(p.upper() == 'TMAINFORM' for p in path + [label]):
                rva, size = struct.unpack_from('<II', d, ro + off)
                hits.append((ro + off, rva, size))

    walk(0, [])
    assert len(hits) == 1, 'TMAINFORM resource entries: %d' % len(hits)
    return hits[0]


# ---- Delphi published-method table ------------------------------------------------
def read_method_table(d, secs, mt_va):
    o = va2off(secs, mt_va)
    count = struct.unpack_from('<H', d, o)[0]
    p, out = o + 2, []
    for _ in range(count):
        size, code = struct.unpack_from('<HI', d, p)
        assert size >= 7, 'corrupt method table at %#x' % mt_va
        nl = d[p + 6]
        assert size == 7 + nl, 'method entry size %d != 7+%d' % (size, nl)
        out.append((code, d[p + 7:p + 7 + nl].decode('latin1')))
        p += size
    return out, o, p - o


def emit_method_table(entries):
    b = struct.pack('<H', len(entries))
    for code, name in entries:
        nb = name.encode('latin1')
        b += struct.pack('<HI', 7 + len(nb), code) + bytes([len(nb)]) + nb
    return b


# ---- DFM ---------------------------------------------------------------------------
# Parser lifted verbatim from build_deved_terrainpal.py, which is the one proven on
# THIS blob.  re_tools/dfm_parse.py is hard-wired to AoW.exe at import time and cannot
# be used as a library; re_tools/dfm_verify.py's walker had no vt 14 (vaCollection)
# case and died at blob offset 0x898 on TMAINFORM until this session added one.
def ss(s):
    b = s.encode('latin1')
    assert len(b) < 256
    return bytes([len(b)]) + b


class DfmParser(object):
    def __init__(self, data):
        self.d = data

    def rstr(self, o):
        n = self.d[o]
        return self.d[o + 1:o + 1 + n].decode('latin1'), o + 1 + n

    def value(self, o):
        d = self.d
        vt = d[o]
        o += 1
        if vt == 0:
            return o
        if vt == 2:
            return o + 1
        if vt == 3:
            return o + 2
        if vt == 4:
            return o + 4
        if vt == 5:
            return o + 10
        if vt in (6, 7):
            _s, o = self.rstr(o)
            return o
        if vt in (8, 9, 13):
            return o
        if vt == 10:
            return o + 4 + struct.unpack_from('<I', d, o)[0]
        if vt == 11:
            while True:
                s, o = self.rstr(o)
                if s == '':
                    return o
        if vt == 1:
            while d[o] != 0:
                o = self.value(o)
            return o + 1
        if vt == 12:
            return o + 4 + struct.unpack_from('<I', d, o)[0]
        if vt == 15:
            return o + 4
        if vt in (16, 17):
            return o + 8
        if vt == 18:
            return o + 4 + 2 * struct.unpack_from('<I', d, o)[0]
        if vt == 14:                                    # vaCollection
            while d[o] != 0:
                if d[o] in (2, 3, 4):
                    o = self.value(o)
                assert d[o] == 1
                o += 1
                while d[o] != 0:
                    _s, o = self.rstr(o)
                    o = self.value(o)
                o += 1
            return o + 1
        raise ValueError('valuetype %d @ %#x' % (vt, o - 1))

    def obj(self, o):
        d = self.d
        start = o
        if (d[o] & 0xF0) == 0xF0:
            o += 1
            if d[start] & 0x02:
                o = self.value(o)
        cls, o = self.rstr(o)
        name, o = self.rstr(o)
        props = {}
        while True:
            pn, o2 = self.rstr(o)
            if pn == '':
                o = o2
                break
            vs = o2
            o = self.value(o2)
            props[pn] = (o2 - 1 - len(pn), vs, o)
        kids = []
        while d[o] != 0:
            c = self.obj(o)
            kids.append(c)
            o = c['end']
        return dict(cls=cls, name=name, start=start, props=props,
                    children=kids, end=o + 1)


def find_node(node, name):
    if node['name'] == name:
        return node
    for c in node['children']:
        r = find_node(c, name)
        if r:
            return r
    return None


def all_names(node, out=None):
    out = [] if out is None else out
    out.append(node['name'])
    for c in node['children']:
        all_names(c, out)
    return out


def new_menu_node():
    return b''.join(ss('TMenuItem') + ss(item)
                    + ss('Caption') + b'\x06' + ss(cap)
                    + ss('OnClick') + b'\x07' + ss(handler)
                    + b'\x00' + b'\x00'
                    for item, cap, handler in ((NEW_ITEM, NEW_CAPTION, NEW_HANDLER),
                                               (ITEM_ITEM, ITEM_CAPTION, ITEM_HANDLER)))


def dfm_insert(blob):
    """Splice the new item in as the sibling right after RemoveLeadersItem."""
    root = DfmParser(blob).obj(4)
    assert root['cls'] == 'TMainForm', root['cls']
    anchor = find_node(root, ANCHOR_ITEM)
    assert anchor is not None, '%s not found in the DFM' % ANCHOR_ITEM
    assert find_node(root, NEW_ITEM) is None, '%s already present' % NEW_ITEM
    at = anchor['end']
    out = blob[:at] + new_menu_node() + blob[at:]
    return out, at


def dfm_remove(blob):
    """Remove whichever of the two nodes are present (an older install has only the heroes one)."""
    at = None
    for name in (ITEM_ITEM, NEW_ITEM):
        node = find_node(DfmParser(blob).obj(4), name)
        if node is not None:
            blob, at = blob[:node['start']] + blob[node['end']:], node['start']
    assert at is not None, '%s is not in the DFM' % NEW_ITEM
    return blob, at


def dfm_check(blob, expect_new):
    """Reparse exactly as TReader will: the walk must consume the stream exactly."""
    root = DfmParser(blob).obj(4)
    assert root['end'] == len(blob), (
        'DFM walk consumed %#x of %#x -- malformed' % (root['end'], len(blob)))
    names = all_names(root)
    dupes = sorted({n for n in names if n and names.count(n) > 1})
    assert not dupes, 'duplicate component names: %s' % dupes
    assert (NEW_ITEM in names) == expect_new, (
        '%s presence is %s, expected %s' % (NEW_ITEM, NEW_ITEM in names, expect_new))
    if expect_new:
        anchor = find_node(root, ANCHOR_ITEM)
        node = find_node(root, NEW_ITEM)
        assert node['start'] == anchor['end'], 'the new item is not the next sibling'
        for parent in (find_node(root, 'DeveloperItems'),):
            kids = [c['name'] for c in parent['children']]
            assert kids[-3:] == [ANCHOR_ITEM, NEW_ITEM, ITEM_ITEM], (
                'DeveloperItems tail is %s' % kids[-4:])
    return root


# ---- the cave ----------------------------------------------------------------------
def assemble(cave_va):
    """eax = TMainForm on entry (Delphi: edx = Sender, unused).  Returns (code, text).

    Stack frame:  [ebp-0x50] AnsiString refcount (-1)
                  [ebp-0x4C] AnsiString length
                  [ebp-0x48] message text, 64 B
                  [ebp-0x04] victim count
    ebx = loop index / scratch, esi = Self, edi = string cursor / THSMEdit / victim.
    Delphi callees preserve ebx/esi/edi/ebp, which is what lets the index live in ebx
    across GetHero and @IsClass -- the template relies on the same thing.
    """
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    # literals go after the code; their addresses are patched in on a second pass
    marks = {}

    def build(lit):
        A = []
        a = A.append
        a('push ebp')
        a('mov  ebp, esp')
        a('sub  esp, 0x50')
        a('push ebx')
        a('push esi')
        a('push edi')
        a('mov  esi, eax')                                   # Self

        a('mov  eax, [%d]' % MAP_SLOT)                       # a map must be open
        a('mov  eax, [eax]')
        a('test eax, eax')
        a('je   L_exit')

        # ---- pause the map render loop (TMainForm.DeleteHeroBtnClick pattern)
        a('mov  edi, [esi + %d]' % HSMEDIT_OFF)
        a('test edi, edi')
        a('je   L_nopause')
        a('cmp  byte ptr [edi + %d], 0' % HSMEDIT_GUARD)
        a('je   L_nopause')
        a('mov  eax, edi')
        a('mov  edx, [eax]')
        a('call dword ptr [edx + %d]' % DISPLAY_PAUSE)
        a('L_nopause:')

        # ---- pass 1: count the victims
        a('mov  dword ptr [ebp - 4], 0')
        a('call L_gethc')
        a('test eax, eax')
        a('je   L_resume')
        a('call 0x%X' % T_GETCOUNT)
        a('mov  ebx, eax')
        a('dec  ebx')
        a('js   L_counted')
        a('L_cloop:')
        a('call L_gethc')
        a('mov  edx, ebx')
        a('call 0x%X' % T_GETHERO)
        a('test eax, eax')                                   # the roster can hold nils
        a('je   L_cnext')
        a('cmp  dword ptr [eax + %d], 0' % OWNER_OFF)        # Owner <> nil -> in use
        a('jne  L_cnext')
        a('mov  edx, [%d]' % TLEADER_SLOT)
        a('call 0x%X' % T_ISCLASS)
        a('test al, al')                                     # a leader -> keep
        a('jne  L_cnext')
        a('inc  dword ptr [ebp - 4]')
        a('L_cnext:')
        a('dec  ebx')
        a('cmp  ebx, -1')
        a('jne  L_cloop')
        a('L_counted:')

        # ---- build "Delete <n> unused hero(es)?" as a stack AnsiString literal
        a('lea  edi, [ebp - 0x48]')
        a('mov  edx, %d' % lit['pre'])
        a('call L_copyz')
        a('mov  eax, [ebp - 4]')
        a('xor  ecx, ecx')
        a('mov  ebx, 10')
        a('L_dig:')
        a('xor  edx, edx')
        a('div  ebx')
        a('add  dl, 0x30')
        a('push edx')
        a('inc  ecx')
        a('test eax, eax')
        a('jne  L_dig')
        a('L_emit:')
        a('pop  eax')
        a('mov  [edi], al')
        a('inc  edi')
        a('dec  ecx')
        a('jne  L_emit')
        a('mov  edx, %d' % lit['many'])
        a('cmp  dword ptr [ebp - 4], 1')
        a('jne  L_plural')
        a('mov  edx, %d' % lit['one'])
        a('L_plural:')
        a('call L_copyz')
        a('mov  byte ptr [edi], 0')
        a('lea  eax, [ebp - 0x48]')
        a('sub  edi, eax')
        a('mov  [ebp - 0x4C], edi')                          # AnsiString length
        a('mov  dword ptr [ebp - 0x50], -1')                 # refcount -1 = a literal

        # ---- nothing to do -> say so, and stop
        a('cmp  dword ptr [ebp - 4], 0')
        a('jne  L_confirm')
        a('push %d' % MB_OK_INFO)
        a('mov  ecx, %d' % lit['cap'])
        a('mov  edx, %d' % lit['none'])
        a('mov  eax, [%d]' % APP_SLOT)
        a('mov  eax, [eax]')
        a('call 0x%X' % T_MSGBOX)                            # ret 4
        a('jmp  L_resume')

        # ---- confirm
        a('L_confirm:')
        a('push %d' % MB_YESNOCANCEL_BUTTONS)
        a('push 0')
        a('lea  edx, [ebp - 0x48]')
        a('mov  cl, %d' % MT_CONFIRMATION)
        a('mov  eax, esi')
        a('call 0x%X' % MSGDLG)                              # ret 8
        a('cmp  ax, %d' % MR_YES)
        a('jne  L_resume')

        # ---- pass 2: delete, downward, re-fetching after the class test
        a('call L_gethc')
        a('test eax, eax')
        a('je   L_resume')
        a('call 0x%X' % T_GETCOUNT)
        a('mov  ebx, eax')
        a('dec  ebx')
        a('js   L_modified')
        a('L_dloop:')
        a('call L_gethc')
        a('mov  edx, ebx')
        a('call 0x%X' % T_GETHERO)
        a('test eax, eax')
        a('je   L_dnext')
        a('cmp  dword ptr [eax + %d], 0' % OWNER_OFF)
        a('jne  L_dnext')
        a('mov  edx, [%d]' % TLEADER_SLOT)
        a('call 0x%X' % T_ISCLASS)
        a('test al, al')
        a('jne  L_dnext')
        a('call L_gethc')                                    # @IsClass clobbered eax
        a('mov  edx, ebx')
        a('call 0x%X' % T_GETHERO)
        a('mov  edi, eax')
        a('test edi, edi')
        a('je   L_dnext')
        a('mov  eax, edi')
        a('mov  edx, [eax]')
        a('call dword ptr [edx + %d]' % HERO_DEACTIVATE)
        a('mov  eax, edi')
        a('mov  edx, [eax]')
        a('call dword ptr [edx + %d]' % HERO_RELEASE)
        a('L_dnext:')
        a('dec  ebx')
        a('cmp  ebx, -1')
        a('jne  L_dloop')

        a('L_modified:')
        a('mov  eax, [%d]' % MAP_SLOT)
        a('cmp  dword ptr [eax], 0')
        a('je   L_resume')
        a('mov  eax, [%d]' % MAP_SLOT)
        a('mov  eax, [eax]')
        a('call 0x%X' % T_SETMODIFIED)

        a('L_resume:')
        a('mov  edi, [esi + %d]' % HSMEDIT_OFF)
        a('test edi, edi')
        a('je   L_exit')
        a('cmp  byte ptr [edi + %d], 0' % HSMEDIT_GUARD)
        a('je   L_exit')
        a('mov  eax, edi')
        a('mov  edx, [eax]')
        a('call dword ptr [edx + %d]' % DISPLAY_RESUME)

        # Both dialog calls clean their own stack arguments (MsgDlg ret 8, MessageBox
        # ret 4).  The epilogue does not TRUST that: it reloads esp from ebp before the
        # register pops, so a cleanup mismatch could not restore garbage into ebx/esi/edi
        # and hand a corrupt frame back to the VCL.
        a('L_exit:')
        a('lea  esp, [ebp - 0x5C]')                          # = esp after the 3 pushes
        a('pop  edi')
        a('pop  esi')
        a('pop  ebx')
        a('mov  esp, ebp')
        a('pop  ebp')
        a('ret')

        # ---- helpers
        a('L_gethc:')                                        # -> eax = THeroControl|nil
        a('mov  eax, [%d]' % MAP_SLOT)
        a('mov  eax, [eax]')
        a('test eax, eax')
        a('je   L_gethc_out')
        a('mov  eax, [eax + %d]' % HC_OFF)
        a('L_gethc_out:')
        a('ret')

        a('L_copyz:')                                        # edx = src, edi = dest
        a('mov  al, [edx]')
        a('test al, al')
        a('je   L_copyz_out')
        a('mov  [edi], al')
        a('inc  edi')
        a('inc  edx')
        a('jmp  L_copyz')
        a('L_copyz_out:')
        a('ret')
        return '\n'.join(A)

    # two passes: the first sizes the code so the literals can be placed after it
    zero = dict(pre=0, one=0, many=0, none=0, cap=0)
    enc, _ = ks.asm(build(zero), cave_va)
    code_len = (len(enc) + 15) // 16 * 16
    at = cave_va + code_len
    lit = {}
    blobs = b''
    for key, s in (('pre', S_PRE), ('one', S_ONE), ('many', S_MANY),
                   ('none', S_NONE), ('cap', S_CAP)):
        lit[key] = at + len(blobs)
        blobs += s
        while len(blobs) % 4:
            blobs += b'\x00'
    text = build(lit)
    enc, _ = ks.asm(text, cave_va)
    assert len(enc) <= code_len, 'code grew between passes (%d > %d)' % (len(enc), code_len)
    body = bytes(enc) + b'\x90' * (code_len - len(enc)) + blobs
    marks['code_len'] = len(enc)
    marks['lit'] = lit
    return body, text, marks


def assemble_items(cave_va):
    """PruneFreeItemsClick.  eax = TMainForm.  Same frame, dialogs and render bracket as the
    heroes handler; the predicate is item[+0x04] (Owner) == nil, the deletion
    TItemControl.UnRegisterItem (removes it from the list, clears the registered flag,
    Release).  Returns (body, marks)."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    sig0, sig1 = struct.unpack_from('<II', UNREG_SIG, 0)
    sig2 = struct.unpack_from('<H', UNREG_SIG, 8)[0]

    def build(lit):
        src = """
            push ebp
            mov  ebp, esp
            sub  esp, 0x50
            push ebx
            push esi
            push edi
            mov  esi, eax
            mov  eax, [MAP_SLOT]
            mov  eax, [eax]
            test eax, eax
            je   L_exit
            mov  edi, [esi + HSMEDIT_OFF]
            test edi, edi
            je   L_nopause
            cmp  byte ptr [edi + HSMEDIT_GUARD], 0
            je   L_nopause
            mov  eax, edi
            mov  edx, [eax]
            call dword ptr [edx + DISPLAY_PAUSE]
        L_nopause:
            mov  dword ptr [ebp - 4], 0
            call L_getic
            test eax, eax
            je   L_counted
            mov  eax, [eax + 8]
            mov  ebx, [eax + 8]
            dec  ebx
            js   L_counted
        L_cloop:
            call L_getic
            mov  eax, [eax + 8]
            mov  eax, [eax + 4]
            mov  eax, [eax + ebx*4]
            test eax, eax
            je   L_cnext
            cmp  dword ptr [eax + OWNER_OFF], 0
            jne  L_cnext
            inc  dword ptr [ebp - 4]
        L_cnext:
            dec  ebx
            jns  L_cloop
        L_counted:
            lea  edi, [ebp - 0x48]
            mov  edx, LIT_PRE
            call L_copyz
            mov  eax, [ebp - 4]
            xor  ecx, ecx
            mov  ebx, 10
        L_dig:
            xor  edx, edx
            div  ebx
            add  dl, 0x30
            push edx
            inc  ecx
            test eax, eax
            jne  L_dig
        L_emit:
            pop  eax
            mov  [edi], al
            inc  edi
            dec  ecx
            jne  L_emit
            mov  edx, LIT_MANY
            cmp  dword ptr [ebp - 4], 1
            jne  L_plural
            mov  edx, LIT_ONE
        L_plural:
            call L_copyz
            mov  byte ptr [edi], 0
            lea  eax, [ebp - 0x48]
            sub  edi, eax
            mov  [ebp - 0x4C], edi
            mov  dword ptr [ebp - 0x50], -1
            cmp  dword ptr [ebp - 4], 0
            jne  L_confirm
            push MB_OK_INFO
            mov  ecx, LIT_CAP
            mov  edx, LIT_NONE
            mov  eax, [APP_SLOT]
            mov  eax, [eax]
            call T_MSGBOX
            jmp  L_resume
        L_confirm:
            push MB_YESNOCANCEL_BUTTONS
            push 0
            lea  edx, [ebp - 0x48]
            mov  cl, MT_CONFIRMATION
            mov  eax, esi
            call MSGDLG
            cmp  ax, MR_YES
            jne  L_resume
            mov  edi, [IAT_REGISTERITEM]
            add  edi, UNREG_DELTA
            cmp  dword ptr [edi], SIG0
            jne  L_bad
            cmp  dword ptr [edi + 4], SIG1
            jne  L_bad
            cmp  word ptr [edi + 8], SIG2
            jne  L_bad
            mov  eax, [esi + HSMEDIT_OFF]
            test eax, eax
            je   L_nodesel
            call T_DESELECT
        L_nodesel:
            call L_getic
            test eax, eax
            je   L_resume
            mov  eax, [eax + 8]
            mov  ebx, [eax + 8]
            dec  ebx
            js   L_modified
        L_dloop:
            call L_getic
            mov  edx, [eax + 8]
            mov  edx, [edx + 4]
            mov  edx, [edx + ebx*4]
            test edx, edx
            je   L_dnext
            cmp  dword ptr [edx + OWNER_OFF], 0
            jne  L_dnext
            call edi
        L_dnext:
            dec  ebx
            jns  L_dloop
        L_modified:
            mov  eax, [MAP_SLOT]
            mov  eax, [eax]
            test eax, eax
            je   L_resume
            call T_SETMODIFIED
            jmp  L_resume
        L_bad:
            push MB_OK_WARN
            mov  ecx, LIT_CAP
            mov  edx, LIT_BAD
            mov  eax, [APP_SLOT]
            mov  eax, [eax]
            call T_MSGBOX
        L_resume:
            mov  edi, [esi + HSMEDIT_OFF]
            test edi, edi
            je   L_exit
            cmp  byte ptr [edi + HSMEDIT_GUARD], 0
            je   L_exit
            mov  eax, edi
            mov  edx, [eax]
            call dword ptr [edx + DISPLAY_RESUME]
        L_exit:
            lea  esp, [ebp - 0x5C]
            pop  edi
            pop  esi
            pop  ebx
            mov  esp, ebp
            pop  ebp
            ret
        L_getic:
            mov  eax, [MAP_SLOT]
            mov  eax, [eax]
            test eax, eax
            je   L_getic_out
            mov  eax, [eax + IC_OFF]
        L_getic_out:
            ret
        L_copyz:
            mov  al, [edx]
            test al, al
            je   L_copyz_out
            mov  [edi], al
            inc  edi
            inc  edx
            jmp  L_copyz
        L_copyz_out:
            ret
        """
        names = dict(MAP_SLOT=MAP_SLOT, HSMEDIT_OFF=HSMEDIT_OFF, HSMEDIT_GUARD=HSMEDIT_GUARD,
                     DISPLAY_PAUSE=DISPLAY_PAUSE, DISPLAY_RESUME=DISPLAY_RESUME,
                     OWNER_OFF=OWNER_OFF, MB_OK_INFO=MB_OK_INFO, MB_OK_WARN=MB_OK_WARN,
                     APP_SLOT=APP_SLOT, T_MSGBOX=T_MSGBOX,
                     MB_YESNOCANCEL_BUTTONS=MB_YESNOCANCEL_BUTTONS,
                     MT_CONFIRMATION=MT_CONFIRMATION, MSGDLG=MSGDLG, MR_YES=MR_YES,
                     IAT_REGISTERITEM=IAT_REGISTERITEM, UNREG_DELTA=UNREG_DELTA,
                     SIG0=sig0, SIG1=sig1, SIG2=sig2, T_DESELECT=T_DESELECT,
                     T_SETMODIFIED=T_SETMODIFIED, IC_OFF=IC_OFF,
                     LIT_PRE=lit['pre'], LIT_ONE=lit['one'], LIT_MANY=lit['many'],
                     LIT_NONE=lit['none'], LIT_CAP=lit['cap'], LIT_BAD=lit['bad'])
        for k in sorted(names, key=len, reverse=True):
            src = src.replace(k, '0x%X' % names[k])
        return src

    zero = dict(pre=0, one=0, many=0, none=0, cap=0, bad=0)
    enc, _ = ks.asm(build(zero), cave_va)
    code_len = (len(enc) + 15) // 16 * 16
    at = cave_va + code_len
    lit, blobs = {}, b''
    for key, st in (('pre', S_PRE), ('one', SI_ONE), ('many', SI_MANY),
                    ('none', SI_NONE), ('cap', SI_CAP), ('bad', SI_BAD)):
        lit[key] = at + len(blobs)
        blobs += st
        while len(blobs) % 4:
            blobs += b'\x00'
    enc, _ = ks.asm(build(lit), cave_va)
    assert len(enc) <= code_len, 'code grew between passes (%d > %d)' % (len(enc), code_len)
    body = bytes(enc) + b'\x90' * (code_len - len(enc)) + blobs
    return body, dict(code_len=len(enc), lit=lit)


def check_immediates(code, cave_va, want=None):
    """keystone assembles `push 0xFFFF` as 6A FF = -1, silently.  Read every push
    immediate back out of the ENCODING and compare with what the source asked for."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    want = want or [MB_OK_INFO, MB_YESNOCANCEL_BUTTONS, 0]
    got = []
    for i in cs.disasm(code, cave_va):
        if i.mnemonic == 'push' and i.op_str.startswith('0x'):
            got.append(int(i.op_str, 16))
        elif i.mnemonic == 'push' and i.op_str.isdigit():
            got.append(int(i.op_str))
    assert got == want, 'push immediates decoded as %s, expected %s' % (got, want)
    return got


def disassemble(code, cave_va, marks):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    inv = {v: k for k, v in marks['lit'].items()}
    for i in cs.disasm(code[:marks['code_len']], cave_va):
        note = ''
        for va, nm in inv.items():
            if ('0x%x' % va) in i.op_str:
                note = '   ; -> literal %s' % nm
        print('        %08X  %-8s %-34s%s' % (i.address, i.mnemonic, i.op_str, note))


# ---- process control ----------------------------------------------------------------
def kill_aow():
    names = ['AoW.exe', 'AoWCompat.exe', 'AoWDevEd.exe', 'AoWEd.exe']
    killed = []
    for n in names:
        try:
            r = subprocess.run(['taskkill', '/F', '/IM', n],
                               capture_output=True, text=True, timeout=20)
            if r.returncode == 0:
                killed.append(n)
        except Exception:                                    # noqa: BLE001
            pass
    return killed


# ---- state ---------------------------------------------------------------------------
def read_state(d, F):
    entry_off, dfm_rva, dfm_size = find_dfm_entry(d, F)
    dfm_off = rva2off(F['secs'], dfm_rva)
    blob = bytes(d[dfm_off:dfm_off + dfm_size])
    mt_va = struct.unpack_from('<I', d, va2off(F['secs'], VMT_METHODTABLE))[0]
    mt, mt_off, mt_len = read_method_table(d, F['secs'], mt_va)
    ctp = next((s for s in F['secs'] if s[0] == CTP_NAME), None)
    return dict(entry_off=entry_off, dfm_rva=dfm_rva, dfm_size=dfm_size,
                dfm_off=dfm_off, blob=blob, mt_va=mt_va, mt=mt, mt_off=mt_off,
                mt_len=mt_len, ctp=ctp)


def strip(d, F, S, quiet=False):
    """Surgical removal, in memory: DFM node out, tail zeroed, VMT-0x28 and .ctp
    VirtualSize restored.  Everything this script wrote lives in .ctp's tail, so the
    tail returning to all-zero IS the check."""
    _nm, ctp_va, _vsz, ctp_raw, ctp_rsz, ctp_hdr = S['ctp']
    new_dfm, at = dfm_remove(S['blob'])
    assert len(new_dfm) == ORIG_DFM_SIZE, (
        'stripped DFM is %#x B, expected %#x' % (len(new_dfm), ORIG_DFM_SIZE))
    dfm_check(new_dfm, expect_new=False)

    # terrainpal's 134-entry table at OLD_MT_VA is where the two handlers live while this
    # feature is applied (2026-09-25).  Re-emit it from the live table's first 134 entries,
    # which are those same entries, before pointing VMT-0x28 back at it.
    assert [n for _c, n in S['mt'][:OLD_MT_COUNT]][-2:] == ['SkyBtnClick', 'ChasmBtnClick'] \
        or len(S['mt']) == OLD_MT_COUNT, 'live table does not start with terrainpal\'s 134'
    old_bytes = emit_method_table(S['mt'][:OLD_MT_COUNT])
    assert len(old_bytes) == OLD_MT_LEN, (
        're-emitted table is %d B, expected %d' % (len(old_bytes), OLD_MT_LEN))
    mo = va2off(F['secs'], OLD_MT_VA)
    d[mo:mo + OLD_MT_LEN] = old_bytes
    old_mt, _o, _l = read_method_table(d, F['secs'], OLD_MT_VA)
    assert len(old_mt) == OLD_MT_COUNT

    d[S['dfm_off']:S['dfm_off'] + len(S['blob'])] = new_dfm + bytes(
        len(S['blob']) - len(new_dfm))
    zero_from = S['dfm_off'] + ORIG_DFM_SIZE
    zero_to = va2off(F['secs'], ZONE_CEIL)
    if zero_from <= S['mt_off'] < zero_to:
        # a pre-2026-09-25 install kept its table past the ceiling (it ended at 0x0058F27A)
        zero_to = max(zero_to, S['mt_off'] + S['mt_len'])
    d[zero_from:zero_to] = bytes(zero_to - zero_from)
    struct.pack_into('<II', d, S['entry_off'], S['dfm_rva'], ORIG_DFM_SIZE)
    struct.pack_into('<I', d, va2off(F['secs'], VMT_METHODTABLE), OLD_MT_VA)
    struct.pack_into('<I', d, ctp_hdr + 8, CTP_VSIZE_OLD)
    if not quiet:
        print('      DFM node removed at %#x (-%d B); tail file %#x..%#x zeroed (%d B)'
              % (at, len(S['blob']) - len(new_dfm), zero_from, zero_to,
                 zero_to - zero_from))
        print('      VMT-0x28 -> %#x | .ctp VirtualSize -> %#x'
              % (OLD_MT_VA, CTP_VSIZE_OLD))
    return d


def build(d, F, S, args):
    """Grow the DFM in place, then lay the cave and the relocated table after it."""
    _nm, ctp_va, _vsz, ctp_raw, ctp_rsz, ctp_hdr = S['ctp']
    ctp_end_off = va2off(F['secs'], ZONE_CEIL)
    ctp_end_va = ZONE_CEIL

    assert S['dfm_size'] == ORIG_DFM_SIZE, (
        'DFM is %#x B, expected the vanilla-plus-terrainpal %#x -- another patch has'
        ' changed it; re-read this script before continuing'
        % (S['dfm_size'], ORIG_DFM_SIZE))
    assert S['mt_va'] == OLD_MT_VA, (
        'VMT-0x28 points at %#x, expected terrainpal\'s %#x' % (S['mt_va'], OLD_MT_VA))
    assert len(S['mt']) == OLD_MT_COUNT, (
        'method table has %d entries, expected %d' % (len(S['mt']), OLD_MT_COUNT))
    assert NEW_HANDLER not in [n for _c, n in S['mt']], '%s already published' % NEW_HANDLER
    assert ITEM_HANDLER not in [n for _c, n in S['mt']], '%s already published' % ITEM_HANDLER
    tail_off = S['dfm_off'] + S['dfm_size']
    assert all(x == 0 for x in d[tail_off:ctp_end_off]), (
        '.ctp tail file %#x..%#x is not all zero -- something else owns it'
        % (tail_off, ctp_end_off))

    new_dfm, at = dfm_insert(S['blob'])
    dfm_check(new_dfm, expect_new=True)
    grow = len(new_dfm) - len(S['blob'])

    # both handlers go where terrainpal's (now dead) 134-entry table sat; strip() re-emits it
    cave_va = OLD_MT_VA
    body, text, marks = assemble(cave_va)
    check_immediates(body[:marks['code_len']], cave_va)
    icave_va = (cave_va + len(body) + 15) // 16 * 16
    ibody, imarks = assemble_items(icave_va)
    check_immediates(ibody[:imarks['code_len']], icave_va,
                     [MB_OK_INFO, MB_YESNOCANCEL_BUTTONS, 0, MB_OK_WARN])
    hbody = body
    body = body + bytes(icave_va - cave_va - len(body)) + ibody

    assert cave_va + len(body) <= OLD_MT_VA + OLD_MT_LEN, (
        'handlers are %d B, the dead table is %d B' % (len(body), OLD_MT_LEN))
    body = body + bytes(OLD_MT_LEN - len(body))
    mt_va = (BASE + S['dfm_rva'] + len(new_dfm) + 3) // 4 * 4
    new_mt = S['mt'] + [(cave_va, NEW_HANDLER), (icave_va, ITEM_HANDLER)]
    mtb = emit_method_table(new_mt)

    end_va = mt_va + len(mtb)
    assert end_va <= ctp_end_va, (
        'the cave ends at %#x, past .ctp raw end %#x -- %d bytes short'
        % (end_va, ctp_end_va, end_va - ctp_end_va))

    # ---- the relocated table must round-trip, and must not reorder
    probe, p = [], 2
    for _ in range(struct.unpack_from('<H', mtb, 0)[0]):
        size, code = struct.unpack_from('<HI', mtb, p)
        nl = mtb[p + 6]
        assert size == 7 + nl, 'method entry size %d != 7+%d' % (size, nl)
        probe.append((code, mtb[p + 7:p + 7 + nl].decode('latin1')))
        p += size
    assert p == len(mtb) and len(probe) == OLD_MT_COUNT + 2, \
        'relocated method table does not round-trip'
    assert [n for _c, n in probe[:OLD_MT_COUNT]] == [n for _c, n in S['mt']], \
        'method table reordered'
    assert probe[-2:] == [(cave_va, NEW_HANDLER), (icave_va, ITEM_HANDLER)], \
        'the new entries are not last'

    print('      DFM  %#x -> %#x B (+%d) | node spliced at blob %#x (after %s)'
          % (S['dfm_size'], len(new_dfm), grow, at, ANCHOR_ITEM))
    # the pad between the ret and the first literal is alignment, not literal bytes --
    # folding it into the literal count is what put a wrong "97 B" into the notes once.
    _lit0 = min(marks['lit'].values()) - cave_va
    print('      %s %#x..%#x (%d B code, %d B pad, %d B literals)'
          % (NEW_HANDLER, cave_va, cave_va + len(hbody) - 1, marks['code_len'],
             _lit0 - marks['code_len'], len(hbody) - _lit0))
    print('      %s %#x..%#x (%d B code + literals) | dead-table zone %#x..%#x'
          % (ITEM_HANDLER, icave_va, icave_va + len(ibody) - 1, len(ibody),
             OLD_MT_VA, OLD_MT_VA + OLD_MT_LEN - 1))
    print('      literals: ' + ', '.join('%s@%#x' % (k, v)
                                         for k, v in sorted(marks['lit'].items(),
                                                            key=lambda kv: kv[1])))
    print('      method table -> %#x (%d entries, %d B, was %d/%d at %#x)'
          % (mt_va, len(new_mt), len(mtb), OLD_MT_COUNT, S['mt_len'], OLD_MT_VA))
    print('      .ctp tail used %d of %d B (%d free) | VirtualSize %#x -> %#x'
          % (end_va - (BASE + S['dfm_rva'] + ORIG_DFM_SIZE),
             ctp_end_va - (BASE + S['dfm_rva'] + ORIG_DFM_SIZE),
             ctp_end_va - end_va, CTP_VSIZE_OLD, CTP_VSIZE_NEW))

    if args.dis:
        print('      --- %s @ %#x ---' % (NEW_HANDLER, cave_va))
        disassemble(hbody, cave_va, marks)
        print('      --- %s @ %#x ---' % (ITEM_HANDLER, icave_va))
        disassemble(ibody, icave_va, imarks)

    def write(dd):
        off = S['dfm_off']
        dd[off:off + len(new_dfm)] = new_dfm
        co = rva2off(F['secs'], cave_va - BASE)
        dd[co:co + len(body)] = body
        mo = rva2off(F['secs'], mt_va - BASE)
        dd[mo:mo + len(mtb)] = mtb
        # anything past the table must still be zero: nothing else may live down here
        eo = rva2off(F['secs'], end_va - BASE)
        assert all(x == 0 for x in dd[eo:ctp_end_off]), 'growth zone is not zero'
        struct.pack_into('<II', dd, S['entry_off'], S['dfm_rva'], len(new_dfm))
        struct.pack_into('<I', dd, va2off(F['secs'], VMT_METHODTABLE), mt_va)
        struct.pack_into('<I', dd, ctp_hdr + 8, CTP_VSIZE_NEW)
        return dd

    return write, dict(cave_va=cave_va, icave_va=icave_va, mt_va=mt_va, end_va=end_va,
                       dfm_len=len(new_dfm), body=body, marks=marks)


# ---- main -----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description='AoWDevEd: Developer > Delete Unused Heroes')
    ap.add_argument('--apply', action='store_true', help='write the patch')
    ap.add_argument('--undo', action='store_true', help='surgical revert')
    ap.add_argument('--dis', action='store_true', help='disassemble the cave')
    args = ap.parse_args()

    path = os.path.join(GAME, EXE)
    backup = os.path.join(BACKUP_DIR, BACKUP_NAME)
    d = bytearray(open(path, 'rb').read())
    orig_len = len(d)
    F = load_pe(d)

    ctp = next((s for s in F['secs'] if s[0] == CTP_NAME), None)
    if ctp is None:
        print('[%s] .ctp IS ABSENT.' % EXE)
        print('      This patch lives in the tail of the section build_deved_terrainpal.py'
              ' creates,')
        print('      and it repoints the method table terrainpal relocated there.'
              '  Run the editor')
        print('      patch chain first: dlgdirs -> modtoolbar -> terrainpal -> valgoto ->'
              ' partyrnd')
        print('      -> timerres -> levelnav -> newmapgen, then this one.')
        return 1
    _nm, ctp_va, ctp_vsz, ctp_raw, ctp_rsz, ctp_hdr = ctp
    later = [s for s in F['secs'] if s[3] > ctp_raw]
    S = read_state(d, F)
    applied = (S['mt_va'] != OLD_MT_VA) or (NEW_ITEM in all_names(
        DfmParser(S['blob']).obj(4)))
    pristine = (S['mt_va'] == OLD_MT_VA
                and S['dfm_size'] == ORIG_DFM_SIZE
                and NEW_ITEM not in all_names(DfmParser(S['blob']).obj(4))
                and ctp_vsz == CTP_VSIZE_OLD
                and all(x == 0 for x in d[S['dfm_off'] + ORIG_DFM_SIZE:ctp_raw + ctp_rsz]))

    print('[%s] %d B | .ctp va %#x raw %#x rawsz %#x vsize %#x'
          % (EXE, orig_len, BASE + ctp_va, ctp_raw, ctp_rsz, ctp_vsz))
    print('      TMainForm VMT %#x | VMT-0x28 -> %#x (%d entries, %d B)'
          % (VMT, S['mt_va'], len(S['mt']), S['mt_len']))
    print('      TMAINFORM DFM rva %#x size %#x (file %#x) | %s published: %s'
          % (S['dfm_rva'], S['dfm_size'], S['dfm_off'], NEW_HANDLER,
             NEW_HANDLER in [n for _c, n in S['mt']]))
    print('      state: %s' % ('APPLIED' if applied else
                               ('clean (unpatched by this feature)' if pristine
                                else 'NEITHER -- inspect before writing')))

    if args.undo:
        if not applied:
            print('      nothing to undo.')
            return 0
        kill_aow()
        strip(d, F, S, quiet=False)
        assert len(d) == orig_len
        F2 = load_pe(d)
        S2 = read_state(d, F2)
        assert S2['mt_va'] == OLD_MT_VA and S2['dfm_size'] == ORIG_DFM_SIZE
        assert len(S2['mt']) == OLD_MT_COUNT
        dfm_check(S2['blob'], expect_new=False)
        try:
            open(path, 'wb').write(d)
        except PermissionError:
            print('      LOCKED -- close the editor and retry')
            return 1
        print('      REVERTED.  The 3219-byte table at %#x is re-emitted and live again; the'
              ' .ctp tail is zero up to %#x.' % (OLD_MT_VA, ZONE_CEIL))
        print('      Now run build_zigeditor.py --apply.')
        return 0

    if applied and not pristine:
        # re-tune / re-apply: strip in memory first, never touching the backup
        print('      already applied -- rebuilding IN PLACE (strip, then lay down again)')
        before = bytes(d)
        strip(d, F, S, quiet=True)
        F = load_pe(d)
        S = read_state(d, F)
    else:
        before = None

    write, info = build(d, F, S, args)

    if not args.apply:
        print('\n      DRY RUN.  Nothing written.  --apply to patch.')
        return 0

    killed = kill_aow()
    if killed:
        print('      killed: %s' % ', '.join(killed))

    if pristine:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
            print('      backup -> backups\\%s (taken from a file PROVED unpatched by'
                  ' this feature)' % BACKUP_NAME)
    else:
        print('      no backup taken: the on-disk file is this script\'s own previous'
              ' output, not an unpatched original')

    write(d)

    # ---- post-conditions, before the write hits the disk
    assert len(d) == orig_len, 'file length changed: %d -> %d' % (orig_len, len(d))
    F2 = load_pe(d)
    ctp2 = next(s for s in F2['secs'] if s[0] == CTP_NAME)
    assert ctp2[4] == CTP_RAWSIZE, 'SizeOfRawData changed'
    assert ctp2[2] == CTP_VSIZE_NEW, 'VirtualSize not raised'
    assert ctp2[3] == ctp_raw, 'PointerToRawData changed'
    for s in later:
        s2 = next(x for x in F2['secs'] if x[0] == s[0])
        assert s2[3] == s[3], '%s PointerToRawData moved' % s[0].decode()
        assert s2[1] == s[1] and s2[4] == s[4], '%s moved' % s[0].decode()
    S2 = read_state(d, F2)
    assert S2['mt_va'] == info['mt_va'] and len(S2['mt']) == OLD_MT_COUNT + 2
    assert S2['mt'][-2:] == [(info['cave_va'], NEW_HANDLER), (info['icave_va'], ITEM_HANDLER)]
    assert S2['dfm_size'] == info['dfm_len']
    root = dfm_check(S2['blob'], expect_new=True)
    methods = {n for _c, n in S2['mt']}
    for node, handler in ((find_node(root, NEW_ITEM), NEW_HANDLER),
                          (find_node(root, ITEM_ITEM), ITEM_HANDLER)):
        assert node is not None and handler in methods, 'OnClick would not resolve at load'
    if before is not None and bytes(d) == before:
        print('\n      already applied and byte-identical -- nothing written.')
        return 0

    try:
        open(path, 'wb').write(d)
    except PermissionError:
        print('      LOCKED -- close the editor and retry')
        return 1

    print('\n      APPLIED.  %s @ %#x, %s @ %#x; method table %#x (136); DFM %#x B.'
          % (NEW_HANDLER, info['cave_va'], ITEM_HANDLER, info['icave_va'], info['mt_va'],
             info['dfm_len']))
    print('      !! APPLIED, UNTESTED.  Launch AoWDevEd.exe and open the Developer menu:')
    print('         a bad method table or a malformed DFM fails at FORM LOAD and every')
    print('         check above still passes.  Revert with --undo.')
    print('      !! DELETING .ctp to re-run build_deved_terrainpal.py destroys this feature')
    print('         and build_deved_toolbar_trim.py too (terrainpal --apply itself is a')
    print('         safe no-op while .ctp exists).  Undo order: heroprune, then toolbar_trim.')
    print('      Now run build_zigeditor.py --apply.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
