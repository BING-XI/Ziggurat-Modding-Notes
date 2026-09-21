#!/usr/bin/env python3
r"""
AoW1 mod -- COMBAT LOG, exe side (window + ring buffer). See Combat_Log_Implementation_Design.md.

Adds to BOTH canonical mod exes `Ziggurat\AoWz.exe` and `Ziggurat\AoWzCompat.exe` (names from
`zigexe.py`; byte-identical builds -- verified: they differ by ONE byte @foff 0x3BB7C, untouched
here; every address below is valid for both).
⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)

  .clog section @ VA 0x60D000 (RVA 0x20D000, file append @0x207A00, RWE) containing:
    +0x000  ring buffer: magic 'CLG1', wrIdx (DLL-owned), rdIdx (exe-owned), 64 slots x 64 B
            (slot = shortstring line; writer = AoWEPACK cave, build_combatlog_dll.py)
    +0x1020 clone class 'TCombatLogWin' = byte-copy of TChatWindow's VMT block [V-0x40,V+0x28)
            with self-ptr, ClassName ptr and MethodTable ptr repointed; FieldTable/TypeInfo/parent
            SHARED with the donor (fields bind, palette works; exe is fixed-base so absolute ok)
    - clone method table = donor's 7 entries + 'CombatLogUpdate' -> cave_drain
    - new RCDATA resource 'TCOMBATLOGWIN': transformed copy of the TCHATWINDOW DFM
      (root CombatLog:TCombatLogWin; ChatEdit/PlayerList/NSBar/Translator dropped; chat-dock
      handlers dropped; memo widened; title 'Combat Log'; OnUpdate -> CombatLogUpdate)
    - rebuilt RCDATA name directory (82 sorted entries; 81 originals keep their old offsets)
      + lang subdir + data entry for the new resource
    - cave_createwin: one more TApplication.CreateForm(TCombatLogWin, @0x45B2E0) appended after
      the 78 vanilla CreateForm calls, hooked at the Application.Run call @0x459FAF
    - cave_drain: the CombatLogUpdate OnUpdate handler -- drains ring slots -> ChatMemo strings
      (TStringList.Add is self-refreshing), scrolls to bottom, auto-shows the window on new lines

  patches: 5-byte hook @0x459FAF; RCDATA type-entry dword @foff 0x72224 -> new name dir;
           section header + SizeOfImage.

Key exe facts (agents B/C): CreateForm thunk 0x40175C (eax=App, edx=classref, ecx=@gvar; EBX=&App
live at hook); Run thunk 0x401764; return to 0x459FB4. Instance gvar -> exe BSS slack 0x45B2E0.
TChatWindow VMT 0x412D5C (selfptr slot V-0x40 @0x412D1C, FieldTable V-0x2C -> 0x412D84, MethodTable
V-0x28 -> 0x412E23, ClassName V-0x20); fields: +0x44 ChatWin, +0x48 ChatMemo, +0x68 ChatSB, +0x70
scroll flag. Memo: +0x118 FStrings TStringList, Add = [vmt+0x34]. Window ctl: +0x75 visible,
SetVisible = [vmt+0x6C] (eax=ctl, dl). Scrollbar: +0x13C Max, +0x158 NumberVisible;
TAOWScrollBar.SetFPos thunk 0x4031CC. RCDATA level-2 dir @foff 0x72270 (81 entries), type-entry
dword @foff 0x72224. TCHATWINDOW DFM @foff 0x92D4C size 0x1AE9.

Idempotent, verify-before-write, backups .pre-combatlog, dry-run default / --apply.
Revert: NOT by snapshot -- .pre-combatlog is layer 4/8 on both exes, so restoring it wipes
tierresearch, clogfix, clogwinhide and bltprobe. Undo surgically instead. (The exe half is
independent of the DLL patch; the DLL cave goes inert when the magic is absent.)
"""
import sys, os, shutil, struct
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                       # mod binary names (AoWz.exe / AoWzCompat.exe)
BACKUP_DIR = os.path.join(GAME, "backups")   # ⚠ backups/, never the game root -- rule 2026-09-03
ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

# ---------- fixed addresses (AoWz.exe == AoWzCompat.exe) ----------
IMG_BASE   = 0x400000
SEC_VA     = 0x60D000          # new .clog section VA
SEC_RVA    = SEC_VA - IMG_BASE
SEC_FOFF   = 0x207A00          # current EOF of both exes
RSRC_RVA   = 0x76000           # .rsrc RVA (resource offsets are relative to this)
HOOK_VA    = 0x459FAF          # call Application.Run  (E8 rel32 -> 0x401764)
HOOK_CONT  = 0x459FB4
THUNK_CREATEFORM = 0x40175C
THUNK_RUN        = 0x401764
THUNK_SETFPOS    = 0x4031CC
GVAR_INSTANCE    = 0x45B2E0    # exe BSS slack: TCombatLogWin instance global
DONOR_VMT  = 0x412D5C          # TChatWindow
DONOR_MTAB = 0x412E23
DFM_FOFF   = 0x92D4C; DFM_SIZE = 0x1AE9
RCDATA_DIRPATCH_FOFF = 0x72224 # dword: 0x80000000|subdir-offset of the RCDATA name dir (=0x80000070)
RCDATA_NAMEDIR_HDR   = 0x72270 # existing name dir HEADER (16 B; named=81)
RCDATA_NAMEDIR_ENTS  = 0x72280 # its 81 8-byte entries
IAT_LSTRFROMSTRING = 0x45D30C
IAT_LSTRCLR        = 0x45D320
# v2 pump: TMWindow.MapWindowUpdate ticks EVERY frame the map is visible (incl. tactical combat) and
# runs OUTSIDE our window's own visibility gate -- the memo's OnUpdate only fires when already visible
# (TAoWComponent.Update @aowInt 0x59803698 tests [self+0x2c] enabled && [self+0x75] visible), which made
# the v1 "auto-show from the memo's OnUpdate" design circular (hidden => never ticks => never shows).
MAPUPD_HOOK = 0x451218
MAPUPD_ORIG = bytes.fromhex("538bd8a17cdf4500")   # push ebx; mov ebx,eax; mov eax,[0x45df7c]
MAPUPD_CONT = 0x451220
CHATMEMOUPDATE = b"ChatMemoUpdate"   # stock handler: scroll-to-bottom via self+0x70 flag + self+0x68 SB

# --- v3: state-driven visibility ---------------------------------------------------------------
# Visible IFF (tactical combat active) OR (fast-combat replay window open). The two TTCMapEvents
# handlers are the authoritative combat enter/exit events; each has a clean 5-byte entry window.
TCACT_HOOK  = 0x4581A4; TCACT_ORIG  = bytes.fromhex("5356578bf0"); TCACT_CONT  = 0x4581A9  # TCMapActivateMap
TCDEACT_HOOK= 0x458570; TCDEACT_ORIG= bytes.fromhex("5657558bf8"); TCDEACT_CONT= 0x458575  # TCMapDeActivateMap
# TFastCombatWindow instance gvar (BSS). ⚠ Game code reaches it INDIRECTLY: DATA slot 0x45A4F0 holds
# the constant 0x45B1B0 (one entry in a pointer table at 0x45A4D0.. mixing BSS-gvar and .idata slots),
# and TheMapExecuteEventLog does `mov eax,[0x45A4F0]; mov eax,[eax]`. Consequence: xref.py shows NO
# direct code refs to 0x45B1B0 -- absence of xrefs is NOT proof a BSS gvar is dead. That misread caused
# the failed 2026-07-21 "clogfix": reading [[0x45A4F0]] is byte-for-byte the same value as [0x45B1B0],
# the single deref below was always correct, and mode 2 demonstrably fired during v6 testing (the user
# saw the replay placement and asked for it moved). Do not "fix" this again.
GVAR_FASTCOMBAT = 0x45B1B0          # [gvar] = TFastCombatWindow instance; ctl = +0x44, visible = +0x75
RING_TACTICAL   = 0x60D00C          # our flag: 1 while the tactical combat map is active
# --- v5: RUNTIME geometry driven from the LIVE unit-card rect (MEASURED, not inferred).
# live_ui.py on the running game (desktop 2560x1369) showed:
#     stock TCUnitWin   DFM 150x262 -> ACTUALLY 457x802 @(2103,519)
#     stock TTCScanner              -> ACTUALLY 457x519 @(2103,0)
#     our TCombatLogWin DFM 150x87  -> ACTUALLY 150x87        <-- obeys its DFM
# => the STOCK sidebar windows are laid out by game CODE at runtime: it overwrites their WinWidth/
# WinHeight (~3.05x their DFM values) AND resets their alignment offsets (our patched BottomOffset=87 is
# verifiably IN the resource yet reads 0 live). No resource edit can move the card -- the former
# TTCUNIT_PATCHES were futile and are removed. Our window ISN'T touched by that code, which is exactly
# why it sat at a literal 150x87 beside a 457-wide sidebar (the "too small" report).
# FIX: awNone/ahNone so ReAlign early-exits (@0x5980311F) and never fights us, then set our rect every
# frame from the card's LIVE rect in cave_drain -> inherits the game's own scaling for free.
# Priority 11 > the card's 10 => we draw OVER its lower third (user's choice).
GVAR_UNITCARD = 0x45B1A8      # TTCUnit instance; window ctl at +0x44
CARD_DIV      = 3             # our height = cardH / CARD_DIV (lower third)
# ⚠ v5.1 -- a HIDDEN window's ORIGIN IS STALE. ReAlign only runs for VISIBLE components (Setup's
# visible gate), so while the unit card is closed its Left/Top still hold the raw DFM values
# (490,170) even though its W/H are correct (457x802). v5 copied the card's Left/Top and therefore
# threw the log into the left half of the screen whenever the card was closed. NEVER copy a hidden
# window's origin -- DERIVE it. Measured on the live game (parent == WinManager, borders L/T/R/B =
# 0/0/0/48):
#     L = parentW - cardW                    = 2560-457       = 2103  (== the scanner's Left)
#     cardTop = parentH - borderBottom - H   = 1369-48-802    = 519   (== the card's live Top)
#     logH = cardH/3 = 267 ; logT = parentH - borderBottom - logH = 1054 ; bottom 1321 == card bottom
# Only W/H are read from the card (reliable while hidden); the origin comes from the manager.
MGR_BORDER_BOTTOM = 0x120     # TAOWWinManager.BorderBottom (=48, the toolbar strip)
# v6: TWO placement modes, applied ONCE PER MODE CHANGE so the player keeps drag/resize.
#   mode 1 (tactical)  -> sidebar, lower third of the unit card   (W/H from the card, origin derived)
#   mode 2 (replay)    -> mid-LEFT, sized from the screen (the card may be unsized on the world map)
# v5 rewrote the rect EVERY frame, which instantly stomped any drag -> "cannot be resized or moved".
# Scratch in exe BSS slack (NOT the ring: that is a wire format shared with the DLL script).
BSS_LASTMODE = 0x45B2F4       # 0 = hidden/none, 1 = tactical, 2 = replay
BSS_DL, BSS_DT, BSS_DW, BSS_DH = 0x45B300, 0x45B304, 0x45B308, 0x45B30C   # desired rect temps
REPLAY_W_DIV, REPLAY_H_DIV, REPLAY_L_SHIFT = 5, 3, 4   # W=PW/5, H=PH/3, L=PW>>4 (mid-left margin)

# ---- v7: finish the replay's CUT step-buttons (PrevSeqBtn/NextSeqBtn) ----------------------------
# They are unfinished dev content: laid out (24px each, left of Close) but Visible=False, ILIndexLit=0
# (no hover art) and NO OnClick at all -- which is why they never responded. Their tooltip is a
# copy-paste of PlayBtn's. Names + the SequencePosition/SequenceSpeed sliders say the intent: step the
# replay BACK/FORWARD one action ("sequence"), vs PlayBtn (continuous) and InitialView/FinalView
# (jump to start/end). We wire them to exactly that.
# NO resource surgery needed: OnClick is a plain TMethod on the button object, so we poke it at runtime.
#   TAOWButton: +0x74 CaptureInput · +0x75 Visible · +0x124 ILIndexUp · +0x128 ILIndexDown
#               +0x12c ILIndexLit · +0x134 btn-dirty · +0x2c validated-dirty
#               +0x138 OnClick.Code · +0x13c OnClick.Data   (dispatch @aowInt 0x598117BE:
#               `mov edx,ebx(Sender); mov eax,[ebx+0x13c](Data); call [ebx+0x138]` => Handler(eax=Data, edx=Sender))
# TFastCombatWindow: +0xEC SequencePositionSld (pos at sld+0x148) · +0xFC PrevSeqBtn · +0x100 NextSeqBtn
#                    +0x144 TCombatViewer (valid iff `test byte[viewer+4],1`)
FCW_HOOK = 0x435244                                  # TFastCombatWindow.FastCombatWindowCreate (OnCreate,
FCW_ORIG = bytes.fromhex("538bd8b201")               #  fires once, after the DFM built the children)
FCW_CONT = 0x435249                                  # push ebx; mov ebx,eax; mov dl,1
FCW_PREV_BTN, FCW_NEXT_BTN = 0xFC, 0x100
FCW_SEQ_SLD, FCW_VIEWER    = 0xEC, 0x144
GVAR_GENERAL   = 0x45A420                            # TGeneral (for the stock click sound)
SND_CLICK      = 0x455DFC                            # what every stock ...Click handler calls first
VIEWER_PAUSE   = 0x402254                            # AoWEPACK TCombatViewer.Pause(eax=viewer)
SEQ_SLD_CHANGE = 0x436218                            # stock handler: viewer.SetPosition(sld.Pos) + refresh
BTN_ONCLICK_CODE, BTN_ONCLICK_DATA = 0x138, 0x13C
BTN_IL_UP, BTN_IL_LIT = 0x124, 0x12C
# Priority 56: the replay window FCWin is Priority=55 / Modal=True, and modal screens call
# TAOWWinManager.SetOverPri(theirPriority) -- everything BELOW that threshold is drawn dimmed (the
# "whole-screen shader" the user saw greying the log). At 56 we sit just above the threshold, so we
# render undimmed during a replay, and still above the unit card (10) in tactical combat. We never
# overlap the replay window itself (it is centred; our replay placement is mid-left).
LOGGEOM = dict(Priority=56, WinLeft=490, WinTop=345, WinWidth=150, WinHeight=87,
               MinWidth=0, MinHeight=0)   # all replaced at runtime; Min*=0 so SetSize cannot clamp us
# ⚠ SLOT_SZ **MUST** equal build_combatlog_dll.py's SLOT_SZ. They are two halves of one wire format:
# the DLL writes slot i at SLOTS + i*SLOT_SZ, this exe reads it back at the same stride. A mismatch does
# NOT fail loudly -- line 0 still lands (both agree at offset 0) and every later line is read from the
# MIDDLE of an earlier line, yielding stale/blank names, duplicated fragments, a garbage shortstring
# length byte (over-read -> heap corruption -> "Runtime error 216" at exit), and eventually writes past
# the ring into the clone VMT. This bit the v3 build. Keep them in lockstep.
RING_SLOTS = 64; SLOT_SZ = 128
assert SLOT_SZ in (64,128,256) and (SLOT_SZ & (SLOT_SZ-1))==0, "slot size must be a power of two"
SLOT_SHIFT = SLOT_SZ.bit_length()-1              # index -> byte offset shift, derived (never hard-code)
RING_BYTES = 0x20 + RING_SLOTS*SLOT_SZ           # header + slots = 0x2020
MAGIC = b"CLG1"

CLASSNAME = b"TCombatLogWin"                     # clone class (resource = uppercase)
RESNAME   = "TCOMBATLOGWIN"
METHNAME  = b"CombatLogUpdate"                   # new OnUpdate handler name

# ---------- helpers ----------
def u16(d,o): return struct.unpack_from("<H",d,o)[0]
def u32(d,o): return struct.unpack_from("<I",d,o)[0]
def p32(v):   return struct.pack("<I",v)

def va2off(va):                                  # CODE va=0x401000 raw=0x400 (contiguous file layout)
    SEC=[(0x401000,0x400,0x59000),(0x45A000,0x59400,0x800),(0x45C000,0x59C00,0x12400),
         (0x46F000,0x6C000,0x6200),(0x476000,0x72200,0x195600),(0x60C000,0x207800,0x200)]
    for v,r,s in SEC:
        if v<=va<v+s: return r+(va-v)
    raise ValueError(hex(va))

# ---------- DFM parse / serialize (Delphi 3 binary form data) ----------
class Obj:
    __slots__=("cls","name","props","kids")
    def __init__(s,c,n): s.cls=c; s.name=n; s.props=[]; s.kids=[]

def dfm_parse(d, o):
    def rstr(o):
        n=d[o]; return d[o+1:o+1+n], o+1+n
    def skipval(o):
        vt=d[o]; o+=1
        if vt in (0,13): return o
        if vt==2: return o+1
        if vt==3: return o+2
        if vt==4: return o+4
        if vt==5: return o+10
        if vt in (6,7):
            return o+1+d[o]
        if vt in (8,9): return o
        if vt in (10,12):
            n=u32(d,o); return o+4+n
        if vt==11:
            while True:
                n=d[o]; o+=1+n
                if n==0: return o
        if vt==1:
            while d[o]!=0: o=skipval(o)
            return o+1
        raise ValueError("vt %d @%X"%(vt,o-1))
    def parse(o):
        b=d[o]
        if (b&0xF0)==0xF0:
            o+=1
            if b&2: o=skipval(o)
        cn,o=rstr(o); nm,o=rstr(o)
        node=Obj(cn,nm)
        while True:
            pn,o=rstr(o)
            if pn==b"": break
            v0=o; o=skipval(o)
            node.props.append([pn, d[v0:o]])
        while d[o]!=0:
            k,o=parse(o)
            node.kids.append(k)
        return node,o+1
    assert d[o:o+4]==b"TPF0"
    return parse(o+4)

def dfm_write(node, out):
    out+=bytes([len(node.cls)])+node.cls+bytes([len(node.name)])+node.name
    for pn,raw in node.props:
        out+=bytes([len(pn)])+pn+raw
    out+=b"\x00"
    for k in node.kids:
        dfm_write(k,out)
    out+=b"\x00"

def enc_ident(s):  return bytes([7,len(s)])+s
def enc_str(s):    return bytes([6,len(s)])+s
def enc_int(v):
    if -128<=v<=127:   return bytes([2])+struct.pack("<b",v)
    if -32768<=v<=32767: return bytes([3])+struct.pack("<h",v)
    return bytes([4])+struct.pack("<i",v)
def enc_false():   return bytes([8])
def enc_true():    return bytes([9])

def transform_dfm(d):
    root,_=dfm_parse(d,0)
    assert root.cls==b"TChatWindow" and root.name==b"ChatWindow"
    root.cls=CLASSNAME; root.name=b"CombatLog"
    # Min dropped: in battle the log has no dismiss button -- visibility is state-driven (see caves).
    keep={b"ChatWin",b"ChatMemo",b"SIcon",b"IWTitle",b"ChatPnl",b"ChatSB"}
    root.kids=[k for k in root.kids if k.name in keep]
    assert {k.name for k in root.kids}==keep, {k.name for k in root.kids}
    def obj(nm): return next(k for k in root.kids if k.name==nm)
    def drop(o,*names):
        o.props=[p for p in o.props if p[0] not in names]
    def setp(o,name,raw):
        for p in o.props:
            if p[0]==name: p[1]=raw; return
        o.props.append([name,raw])
    w=obj(b"ChatWin")
    # chat-only handlers dropped: OnShow/OnHide dock the chat bar via TGeneral; ChatWinResize does
    # bespoke layout math on chat internals. We need none -- children follow via Alignment (below).
    drop(w,b"OnHide",b"OnShow",b"OnDrag",b"OnResize")
    setp(w,b"Draggable",enc_true()); setp(w,b"Resizable",enc_true())
    for k,v in LOGGEOM.items(): setp(w,k.encode(),enc_int(v))
    setp(w,b"Alignment.AlignWidth",  enc_ident(b"awNone"))     # ReAlign early-exits => cave owns the rect
    setp(w,b"Alignment.AlignHeight", enc_ident(b"ahNone"))
    setp(w,b"Alignment.LeftOffset",  enc_int(0))
    setp(w,b"Alignment.RightOffset", enc_int(0))
    setp(w,b"Alignment.TopOffset",   enc_int(LOGGEOM["WinTop"]))
    setp(w,b"Alignment.BottomOffset",enc_int(0))
    m=obj(b"ChatMemo")
    setp(m,b"OnUpdate",enc_ident(CHATMEMOUPDATE))          # stock scroll handler (shares our field layout)
    setp(m,b"WinWidth",enc_int(120))
    setp(m,b"WinHeight",enc_int(220))
    setp(m,b"Alignment.RightOffset",enc_int(19))           # leave the 17px scrollbar its column
    setp(m,b"Alignment.BottomOffset",enc_int(1))           # was 21: reserved for the removed ChatEdit
    sb=obj(b"ChatSB")                                       # anchor the scrollbar so resizing works
    setp(sb,b"Alignment.AlignWidth", enc_ident(b"awRight"))
    setp(sb,b"Alignment.AlignHeight",enc_ident(b"ahBoth"))
    setp(sb,b"Alignment.LeftOffset", enc_int(0))
    setp(sb,b"Alignment.RightOffset",enc_int(0))
    setp(sb,b"Alignment.TopOffset",  enc_int(0))
    setp(sb,b"Alignment.BottomOffset",enc_int(1))
    t=obj(b"IWTitle")
    setp(t,b"Text",enc_str(b"Combat Log"))
    out=bytearray(b"TPF0"); dfm_write(root,out)
    return bytes(out)

# ---------- section blob layout ----------
def asm(src, addr):
    code,_=ks.asm(src,addr)
    return bytes(code)

def build_blob(exe):
    """Return (blob, patch-list-extras, layout dict). exe = original file bytes."""
    L={}
    blob=bytearray()
    def align(n):
        while len(blob)%n: blob.append(0)
    # -- ring buffer --
    L["ring"]=SEC_VA
    blob+=MAGIC+p32(0)+p32(0)+b"\x00"*(0x20-12)+b"\x00"*(RING_SLOTS*SLOT_SZ)
    assert len(blob)==RING_BYTES
    # -- clone class block (donor [V-0x40, V+0x28)) --
    align(4)
    doff=va2off(DONOR_VMT-0x40)
    block=bytearray(exe[doff:doff+0x68])
    L["clone_block"]=SEC_VA+len(blob)
    L["clone_vmt"]=L["clone_block"]+0x40
    blob+=block            # patched below once other addresses known (in-place)
    # -- clone method table: donor entries + CombatLogUpdate -> cave_drain (fnptr patched later) --
    align(4)
    L["mtab"]=SEC_VA+len(blob)
    mo=va2off(DONOR_MTAB)
    cnt=u16(exe,mo); p=mo+2
    for _ in range(cnt):
        sz=u16(exe,p); p+=sz
    donor_mtab=exe[mo+2:p]
    new_entry_size=2+4+1+len(METHNAME)
    L["mtab_fnptr"]=L["mtab"]+2+len(donor_mtab)+2          # dword inside the appended entry
    blob+=struct.pack("<H",cnt+1)+donor_mtab
    blob+=struct.pack("<H",new_entry_size)+p32(0xDEADBEEF)+bytes([len(METHNAME)])+METHNAME
    # -- clone class name shortstring --
    L["clsname"]=SEC_VA+len(blob)
    blob+=bytes([len(CLASSNAME)])+CLASSNAME
    # -- transformed DFM --
    align(4)
    dfm=transform_dfm(exe[DFM_FOFF:DFM_FOFF+DFM_SIZE])
    L["dfm"]=SEC_VA+len(blob); L["dfm_size"]=len(dfm)
    blob+=dfm
    # -- resource machinery --
    align(4)
    L["resname"]=SEC_VA+len(blob)                          # {len:word, UTF-16LE chars}
    blob+=struct.pack("<H",len(RESNAME))+RESNAME.encode("utf-16le")
    align(4)
    L["langdir"]=SEC_VA+len(blob)                          # lang subdir: header + 1 id entry
    # mirror the donor chain's lang id: read TCHATWINDOW entry chain
    donor_lang_id=read_donor_langid(exe)
    L["dataentry"]=L["langdir"]+0x18
    blob+=b"\x00"*12+struct.pack("<HH",0,1)                # hdr: 0 named, 1 id
    blob+=p32(donor_lang_id)+p32((L["dataentry"]+IMG_BASE-IMG_BASE)-RSRC_RVA)  # placeholder fixed below
    # data entry {DataRVA, Size, CodePage, 0}
    blob+=p32(L["dfm"]-IMG_BASE)+p32(L["dfm_size"])+p32(0)+p32(0)
    # -- rebuilt RCDATA name dir: header + 82 sorted entries --
    align(4)
    L["namedir"]=SEC_VA+len(blob)
    hdr=exe[RCDATA_NAMEDIR_HDR:RCDATA_NAMEDIR_HDR+16]
    n_named=u16(hdr,12); n_id=u16(hdr,14)
    assert (n_named,n_id)==(81,0), (n_named,n_id)
    entries=[]
    for i in range(81):
        e=RCDATA_NAMEDIR_ENTS+8*i
        entries.append((u32(exe,e),u32(exe,e+4)))
    def entry_name(ne):
        off=(ne&0x7FFFFFFF)
        fo=va2off(IMG_BASE+RSRC_RVA+off)
        ln=u16(exe,fo)
        return exe[fo+2:fo+2+2*ln].decode("utf-16le")
    named=[(entry_name(a),a,b) for a,b in entries]
    ours=(RESNAME, 0x80000000|(L["resname"]-IMG_BASE-RSRC_RVA), 0x80000000|(L["langdir"]-IMG_BASE-RSRC_RVA))
    named.append(ours)
    named.sort(key=lambda t:t[0])
    blob+=hdr[:12]+struct.pack("<HH",82,0)
    for _nm,a,b in named:
        blob+=p32(a)+p32(b)
    # -- caves --
    align(16)
    L["cave_createwin"]=SEC_VA+len(blob)
    cw=asm(f"""
        mov edx, 0x{L['clone_vmt']:X}
        mov ecx, 0x{GVAR_INSTANCE:X}
        mov eax, [ebx]
        call 0x{THUNK_CREATEFORM:X}
        mov eax, [ebx]
        call 0x{THUNK_RUN:X}
        jmp 0x{HOOK_CONT:X}
    """, L["cave_createwin"])
    blob+=cw
    align(16)
    L["cave_drain"]=SEC_VA+len(blob)
    t_from=find_thunk(exe,IAT_LSTRFROMSTRING); t_clr=find_thunk(exe,IAT_LSTRCLR)
    L["thunk_lstrfromstring"]=t_from; L["thunk_lstrclr"]=t_clr
    dr=asm(f"""
        pushad
        mov  ebx, [0x{GVAR_INSTANCE:X}]
        test ebx, ebx
        jz   _done
        mov  eax, [ebx+0x48]
        test eax, eax
        jz   _done
        mov  ecx, [ebx+0x44]
        test ecx, ecx
        jz   _drain
        mov  eax, [ecx+0xCC]
        test eax, eax
        jz   _drain
        mov  esi, [0x{RING_TACTICAL:X}]
        test esi, esi
        jz   _m_fc
        mov  esi, 1
        jmp  _m_have
    _m_fc:
        mov  esi, [0x{GVAR_FASTCOMBAT:X}]
        test esi, esi
        jz   _m_none
        mov  esi, [esi+0x44]
        test esi, esi
        jz   _m_none
        cmp  byte ptr [esi+0x75], 0
        je   _m_none
        mov  esi, 2
        jmp  _m_have
    _m_none:
        cmp  dword ptr [0x{BSS_LASTMODE:X}], 0
        je   _drain
        mov  dword ptr [0x{BSS_LASTMODE:X}], 0
        mov  eax, [ebx+0x48]
        test eax, eax
        jz   _cleared
        mov  eax, [eax+0x118]
        test eax, eax
        jz   _cleared
        mov  edx, [eax]
        call dword ptr [edx+0x40]
    _cleared:
        mov  eax, [0x{SEC_VA+4:X}]
        mov  [0x{SEC_VA+8:X}], eax
        jmp  _drain
    _m_have:
        cmp  esi, [0x{BSS_LASTMODE:X}]
        je   _drain
        cmp  esi, 2
        je   _m_replay
        mov  edx, [0x{GVAR_UNITCARD:X}]
        test edx, edx
        jz   _drain
        mov  edx, [edx+0x44]
        test edx, edx
        jz   _drain
        mov  edi, [edx+0x7C]
        test edi, edi
        jle  _drain
        mov  [0x{BSS_DW:X}], edi
        mov  edx, [edx+0x80]
        test edx, edx
        jle  _drain
        push eax
        mov  eax, edx
        xor  edx, edx
        mov  edi, {CARD_DIV}
        div  edi
        mov  [0x{BSS_DH:X}], eax
        pop  eax
        mov  edx, [eax+0x7C]
        sub  edx, [0x{BSS_DW:X}]
        mov  [0x{BSS_DL:X}], edx
        mov  edx, [eax+0x80]
        sub  edx, [eax+0x{MGR_BORDER_BOTTOM:X}]
        sub  edx, [0x{BSS_DH:X}]
        mov  [0x{BSS_DT:X}], edx
        jmp  _m_apply
    _m_replay:
        push eax
        mov  eax, [eax+0x7C]
        xor  edx, edx
        mov  edi, {REPLAY_W_DIV}
        div  edi
        mov  [0x{BSS_DW:X}], eax
        pop  eax
        push eax
        mov  eax, [eax+0x80]
        xor  edx, edx
        mov  edi, {REPLAY_H_DIV}
        div  edi
        mov  [0x{BSS_DH:X}], eax
        pop  eax
        mov  edx, [eax+0x7C]
        shr  edx, {REPLAY_L_SHIFT}
        mov  [0x{BSS_DL:X}], edx
        mov  edx, [eax+0x80]
        sub  edx, [eax+0x{MGR_BORDER_BOTTOM:X}]
        sub  edx, [0x{BSS_DH:X}]
        shr  edx, 1
        mov  [0x{BSS_DT:X}], edx
    _m_apply:
        mov  edx, [0x{BSS_DL:X}]
        mov  [ecx+0x84], edx
        mov  edx, [0x{BSS_DT:X}]
        mov  [ecx+0x88], edx
        mov  edx, [0x{BSS_DW:X}]
        mov  [ecx+0x7C], edx
        mov  edx, [0x{BSS_DH:X}]
        mov  [ecx+0x80], edx
        mov  [0x{BSS_LASTMODE:X}], esi
        mov  byte ptr [ecx+0x2D], 0
        mov  byte ptr [ecx+0x2E], 0
    _drain:
        mov  esi, [0x{SEC_VA+8:X}]
        mov  edi, [0x{SEC_VA+4:X}]
        cmp  esi, edi
        je   _vis
    _next:
        mov  eax, esi
        and  eax, {RING_SLOTS-1}
        shl  eax, {SLOT_SHIFT}
        add  eax, 0x{SEC_VA+0x20:X}
        push 0
        mov  edx, eax
        mov  eax, esp
        call 0x{t_from:X}
        mov  edx, [esp]
        mov  eax, [ebx+0x48]
        mov  eax, [eax+0x118]
        mov  ecx, [eax]
        call dword ptr [ecx+0x34]
        mov  eax, esp
        call 0x{t_clr:X}
        pop  ecx
        inc  esi
        cmp  esi, edi
        jne  _next
        mov  [0x{SEC_VA+8:X}], esi
        mov  byte ptr [ebx+0x70], 1
    _vis:
        mov  eax, [0x{RING_TACTICAL:X}]
        test eax, eax
        jnz  _want
        mov  eax, [0x{GVAR_FASTCOMBAT:X}]
        test eax, eax
        jz   _nowant
        mov  eax, [eax+0x44]
        test eax, eax
        jz   _nowant
        movzx eax, byte ptr [eax+0x75]
        test eax, eax
        jz   _nowant
    _want:
        mov  edx, 1
        jmp  _apply
    _nowant:
        xor  edx, edx
    _apply:
        mov  eax, [ebx+0x44]
        test eax, eax
        jz   _done
        movzx ecx, byte ptr [eax+0x75]
        cmp  ecx, edx
        je   _done
        mov  ecx, [eax]
        call dword ptr [ecx+0x6C]
    _done:
        popad
        ret
    """, L["cave_drain"])
    blob+=dr
    align(16)
    L["cave_mapupd"]=SEC_VA+len(blob)
    blob+=asm(f"""
        call 0x{L['cave_drain']:X}
        push ebx
        mov  ebx, eax
        mov  eax, [0x45DF7C]
        jmp  0x{MAPUPD_CONT:X}
    """, L["cave_mapupd"])
    # ---- v7: replay step buttons ----
    def stepsrc(va, delta):
        return f"""
            push ebx
            push esi
            mov  ebx, eax
            mov  eax, [0x{GVAR_GENERAL:X}]
            mov  eax, [eax]
            xor  edx, edx
            call 0x{SND_CLICK:X}
            mov  esi, [ebx+0x{FCW_VIEWER:X}]
            test esi, esi
            jz   _sd
            test byte ptr [esi+4], 1
            jz   _sd
            mov  eax, esi
            call 0x{VIEWER_PAUSE:X}
            mov  eax, [ebx+0x{FCW_SEQ_SLD:X}]
            test eax, eax
            jz   _sd
            mov  edx, [eax+0x148]
            add  edx, {delta}
            call 0x{THUNK_SETFPOS:X}
            mov  eax, ebx
            call 0x{SEQ_SLD_CHANGE:X}
        _sd:
            pop  esi
            pop  ebx
            ret
        """
    align(16); L["cave_prevseq"]=SEC_VA+len(blob)
    blob+=asm(stepsrc(L["cave_prevseq"], -1), L["cave_prevseq"])
    align(16); L["cave_nextseq"]=SEC_VA+len(blob)
    blob+=asm(stepsrc(L["cave_nextseq"], 1), L["cave_nextseq"])
    align(16); L["cave_fcwinit"]=SEC_VA+len(blob)
    def wire(btn_off, handler):
        return f"""
            mov  ebx, [eax+0x{btn_off:X}]
            test ebx, ebx
            jz   _w{btn_off:X}
            mov  dword ptr [ebx+0x{BTN_ONCLICK_CODE:X}], 0x{handler:X}
            mov  [ebx+0x{BTN_ONCLICK_DATA:X}], eax
            mov  edx, [ebx+0x{BTN_IL_UP:X}]
            mov  [ebx+0x{BTN_IL_LIT:X}], edx
            mov  byte ptr [ebx+0x75], 1
            mov  byte ptr [ebx+0x134], 0
            mov  byte ptr [ebx+0x2C], 0
        _w{btn_off:X}:
        """
    blob+=asm(f"""
        push ebx
        push edx
        {wire(FCW_PREV_BTN, L["cave_prevseq"])}
        {wire(FCW_NEXT_BTN, L["cave_nextseq"])}
        pop  edx
        pop  ebx
        push ebx
        mov  ebx, eax
        mov  dl, 1
        jmp  0x{FCW_CONT:X}
    """, L["cave_fcwinit"])
    align(16)
    L["cave_tcact"]=SEC_VA+len(blob)
    blob+=asm(f"""
        mov  dword ptr [0x{RING_TACTICAL:X}], 1
        push ebx
        push esi
        push edi
        mov  esi, eax
        jmp  0x{TCACT_CONT:X}
    """, L["cave_tcact"])
    align(16)
    L["cave_tcdeact"]=SEC_VA+len(blob)
    blob+=asm(f"""
        mov  dword ptr [0x{RING_TACTICAL:X}], 0
        push esi
        push edi
        push ebp
        mov  edi, eax
        jmp  0x{TCDEACT_CONT:X}
    """, L["cave_tcdeact"])
    # -- fixups inside blob --
    bo=L["clone_block"]-SEC_VA
    struct.pack_into("<I",blob,bo+0x00,L["clone_vmt"])         # V-0x40 selfptr
    struct.pack_into("<I",blob,bo+0x18,L["mtab"])              # V-0x28 method table
    struct.pack_into("<I",blob,bo+0x20,L["clsname"])           # V-0x20 class name
    struct.pack_into("<I",blob,(L["mtab_fnptr"]-SEC_VA),L["cave_drain"])
    # fix langdir entry offset (was placeholder)
    struct.pack_into("<I",blob,(L["langdir"]-SEC_VA)+0x14,(L["dataentry"]-IMG_BASE)-RSRC_RVA)
    align(0x200)
    return bytes(blob),L

def read_donor_langid(exe):
    """Follow TCHATWINDOW's name entry -> lang dir -> return its lang id."""
    for i in range(81):
        e=RCDATA_NAMEDIR_ENTS+8*i
        ne,de=u32(exe,e),u32(exe,e+4)
        off=(ne&0x7FFFFFFF); fo=va2off(IMG_BASE+RSRC_RVA+off); ln=u16(exe,fo)
        if exe[fo+2:fo+2+2*ln].decode("utf-16le")=="TCHATWINDOW":
            sub=va2off(IMG_BASE+RSRC_RVA+(de&0x7FFFFFFF))
            n_named=u16(exe,sub+12); n_id=u16(exe,sub+14)
            assert n_named==0 and n_id==1,(n_named,n_id)
            return u32(exe,sub+16)
    raise LookupError("TCHATWINDOW")

def find_thunk(exe, iat_slot):
    """Find the FF25 [iat_slot] stub in CODE."""
    pat=b"\xff\x25"+p32(iat_slot)
    i=exe.find(pat,0x400,0x59400)
    assert i>=0, hex(iat_slot)
    return IMG_BASE+0x1000+(i-0x400)

# ---------- patching ----------
APPLY="--apply" in sys.argv

def process(path):
    exe=bytearray(open(path,"rb").read())
    orig_len=len(exe)
    blob,L=build_blob(bytes(exe))

    # section header
    e=u32(exe,0x3C); nsec=u16(exe,e+6); opt=u16(exe,e+20)
    shdr_off=e+24+opt+40*nsec
    vsize=(len(blob)+0xFFF)&~0xFFF
    sec=struct.pack("<8sIIIIIIHHI",b".clog",len(blob),SEC_RVA,len(blob),SEC_FOFF,0,0,0,0,0xE0000060)
    soi_off=e+24+56
    new_soi=SEC_RVA+vsize

    hook_new=b"\xE9"+struct.pack("<i",L["cave_createwin"]-(HOOK_VA+5))
    hook_orig=b"\xE8"+struct.pack("<i",THUNK_RUN-(HOOK_VA+5))
    dirpatch_new=p32(0x80000000|(L["namedir"]-IMG_BASE-RSRC_RVA))
    dirpatch_orig=p32(0x80000070)

    mapupd_new=b"\xE9"+struct.pack("<i",L["cave_mapupd"]-(MAPUPD_HOOK+5))+b"\x90\x90\x90"
    patches=[  # (file-offset, expected-orig, new, desc)
        (va2off(HOOK_VA), hook_orig, hook_new, "hook: Application.Run call -> cave_createwin"),
        (va2off(MAPUPD_HOOK), MAPUPD_ORIG, mapupd_new, "hook: TMWindow.MapWindowUpdate -> cave_mapupd (drain pump)"),
        (va2off(TCACT_HOOK), TCACT_ORIG, b"\xE9"+struct.pack("<i",L["cave_tcact"]-(TCACT_HOOK+5)),
         "hook: TCMapActivateMap -> tactical flag = 1"),
        (va2off(TCDEACT_HOOK), TCDEACT_ORIG, b"\xE9"+struct.pack("<i",L["cave_tcdeact"]-(TCDEACT_HOOK+5)),
         "hook: TCMapDeActivateMap -> tactical flag = 0"),
        (va2off(FCW_HOOK), FCW_ORIG, b"\xE9"+struct.pack("<i",L["cave_fcwinit"]-(FCW_HOOK+5)),
         "hook: FastCombatWindowCreate -> wire the cut PrevSeq/NextSeq step buttons"),
        (RCDATA_DIRPATCH_FOFF, dirpatch_orig, dirpatch_new, "RCDATA type entry -> new 82-entry name dir"),
        (shdr_off, exe[shdr_off:shdr_off+40] if u16(exe,e+6)>7 else b"\x00"*40, sec, ".clog section header"),
        (soi_off, None, p32(new_soi), "SizeOfImage"),
    ]

    print(f"[{os.path.basename(path)}] blob {len(blob):#x} B  (ring@{L['ring']:08X} vmt@{L['clone_vmt']:08X} "
          f"mtab@{L['mtab']:08X} dfm@{L['dfm']:08X}+{L['dfm_size']:#x} namedir@{L['namedir']:08X} "
          f"createwin@{L['cave_createwin']:08X} drain@{L['cave_drain']:08X} mapupd@{L['cave_mapupd']:08X})")
    print(f"  thunks: LStrFromString={L['thunk_lstrfromstring']:08X} LStrClr={L['thunk_lstrclr']:08X}")

    # "already applied" must compare the WHOLE blob, not just the hook: the caves change far more often
    # than the hook does, so a hook-only test reports "already applied" for a stale build and silently
    # skips the write. (It did exactly that during v6 dev.) Any content change => fall through, which
    # then trips the length check below. Do NOT revert to .pre-combatlog (layer 4/8, costs 4 features).
    inplace=False
    applied = (orig_len>SEC_FOFF and exe[SEC_FOFF:SEC_FOFF+4]==MAGIC)
    if applied:
        if bytes(exe[SEC_FOFF:SEC_FOFF+len(blob)])==blob and \
           bytes(exe[va2off(HOOK_VA):va2off(HOOK_VA)+5])==hook_new:
            print("  [=] already applied"); return True
        # A different build is installed. Do NOT demand a `.pre-combatlog` revert: both exes have
        # tierresearch (.tres) layered on top, so restoring that backup would destroy it -- and `.clog`
        # is boxed in by `.tres` with zero file slack, so the section must not move either. Rewrite the
        # blob IN PLACE, which is safe iff the new blob is exactly the size of the installed section.
        # (See CLAUDE.md's layering rule and re_tools/revert_audit.py.)
        hdr=None
        for i in range(nsec):
            o=e+24+opt+40*i
            if bytes(exe[o:o+5])==b".clog":
                hdr=o; break
        if hdr is None:
            print("  [x] MAGIC present but no .clog section header found -- refusing"); return False
        cur_raw=u32(exe,hdr+16)
        if cur_raw!=len(blob):
            print(f"  [x] installed .clog is {cur_raw:#x} B but the new blob is {len(blob):#x} B."
                  f" Growing it would overrun the following section (.tres) -- refusing."); return False
        print(f"  [i] rewriting the installed .clog blob in place ({len(blob):#x} B, section unmoved)")
        inplace=True
        # Retarget the header write at the EXISTING .clog slot (not a fresh one past the table), and
        # drop the SizeOfImage write -- the section keeps its RVA and size, so SOI is already correct.
        patches=[p for p in patches if p[3] not in (".clog section header","SizeOfImage")]
        patches.append((hdr, bytes(exe[hdr:hdr+40]), sec, ".clog section header (rewritten in place)"))
        # Hooks written by a PREVIOUS build of ours jump to the OLD cave addresses, and those move
        # whenever the blob is rebuilt -- so `cur` matches neither the vanilla original nor the new
        # bytes, and the verifier would refuse. Accept an existing E9 at a hook site as ours: these
        # sites are fixed, hard-coded addresses inside known functions, and the only thing that ever
        # writes an E9 there is this script (its identity was verified on the first apply).
        patches=[(off, (bytes(exe[off:off+len(new)]) if (new[:1]==b"\xE9" and exe[off:off+1]==b"\xE9")
                        else orig), new, desc)
                 for off,orig,new,desc in patches]
    if not inplace and orig_len!=SEC_FOFF:
        print(f"  [x] file length {orig_len:#x} != expected EOF {SEC_FOFF:#x}"); return False
    if not inplace and u16(exe,e+6)!=7:
        print("  [x] expected 7 sections"); return False
    ok=True
    for off,orig,new,desc in patches:
        if orig is None: continue
        cur=bytes(exe[off:off+len(new)])
        if cur!=orig and cur!=new:
            ok=False; print(f"  [!] {off:#x} ({desc})\n      exp {orig.hex(' ')}\n      got {cur.hex(' ')}")
    if not ok: return False
    if not APPLY:
        print("  [dry] all originals verified"); return True
    # In-place rewrites take their OWN backup: `.pre-combatlog` already exists and predates
    # tierresearch, so it is NOT a safe revert target (see CLAUDE.md's layering rule).
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bp=os.path.join(BACKUP_DIR, os.path.basename(path)
                    +(".pre-clogfix" if inplace else ".pre-combatlog"))
    if not os.path.exists(bp): shutil.copy2(path,bp); print(f"  [bak] {bp}")
    for off,orig,new,desc in patches:
        exe[off:off+len(new)]=new; print(f"  [w ] {off:#x} {desc}")
    if inplace:
        exe[SEC_FOFF:SEC_FOFF+len(blob)]=blob           # section already exists and keeps its size
        print(f"  [w ] {SEC_FOFF:#x} .clog blob ({len(blob):#x} B, in place)")
    else:
        struct.pack_into("<H",exe,e+6,8)                # 7 -> 8 sections
        exe+=blob
    open(path,"wb").write(exe)
    return True

def selfcheck(path):
    """Post-conditions on a patched file: resource walk finds TCOMBATLOGWIN; DFM parses; caves disasm."""
    d=open(path,"rb").read()
    if d[SEC_FOFF:SEC_FOFF+4]!=MAGIC: print("  [check] not applied"); return
    blob,L=build_blob(d[:SEC_FOFF])
    assert d[SEC_FOFF:SEC_FOFF+len(blob)]==blob, "blob mismatch on disk"
    nd=SEC_FOFF+(L["namedir"]-SEC_VA)
    n=u16(d,nd+12); names=[]
    for i in range(n):
        e=nd+16+8*i; ne=u32(d,e)
        off=ne&0x7FFFFFFF
        va=IMG_BASE+RSRC_RVA+off
        fo=va2off(va) if va<SEC_VA else SEC_FOFF+(va-SEC_VA)
        ln=u16(d,fo); names.append(d[fo+2:fo+2+2*ln].decode("utf-16le"))
    assert names==sorted(names) and RESNAME in names and len(names)==82, (len(names),names[:3])
    dfm=d[SEC_FOFF+(L["dfm"]-SEC_VA):SEC_FOFF+(L["dfm"]-SEC_VA)+L["dfm_size"]]
    root,_=dfm_parse(dfm,0)
    kids={k.name for k in root.kids}
    assert root.cls==CLASSNAME and root.name==b"CombatLog"
    assert kids=={b"ChatWin",b"ChatMemo",b"SIcon",b"IWTitle",b"ChatPnl",b"ChatSB"}, kids
    print(f"  [check] OK: 82 sorted resources (+{RESNAME}), DFM parses ({len(root.kids)} kids: "
          f"{','.join(sorted(k.decode() for k in kids))}), "
          f"clone VMT selfptr={u32(d,SEC_FOFF+(L['clone_block']-SEC_VA)):08X}")

print()
allok=True
for exe in zigexe.EXES:
    # never let one exe's failure (or a stale self-check) silently skip the other
    try:
        ok1=process(os.path.join(GAME,exe))
        if APPLY and ok1: selfcheck(os.path.join(GAME,exe))
    except Exception as ex:
        ok1=False; print(f"  [x] {type(ex).__name__}: {ex}")
    allok &= ok1
    print()
print("[dry-run] Re-run with --apply to write (close all AoW binaries)." if not APPLY
      else ("[done] Both exes patched. Revert: undo surgically -- .pre-combatlog is layer 4/8, costs 4 features." if allok else "[!] not fully applied"))
