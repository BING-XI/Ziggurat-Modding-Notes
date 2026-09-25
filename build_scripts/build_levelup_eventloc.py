#!/usr/bin/env python3
r"""
AoW1 mod -- "levelupeventloc": right-clicking a hero LEVEL-UP event in the event log centres the
map on the hex where the level-up HAPPENED, not on where the hero stands now.

Ported from Inioch's AoWx fix (Modding Resources/Inioch/share8/claude memory 2026-09-23/
hero-levelup-event-fixed-location.md) and re-derived against our DLL.  Two of his choices did not
survive the check -- see "DEVIATIONS FROM THE PORT".  Record: Zig notes/07-ui.md section 11.

================================================================================
THE LEAK
================================================================================
THeroUpgradeEventLog (VMT 0x55711B88, instance 0x24) overrides ViewLocation, VMT slot +0x74
(0x55711BFC -> 0x557857E0):

    TUnitControl.FindUnit(map[+0xFC], event[+0x18]) -> TAbstractUnit.GetLocation -> CenterViewTo

That is the hero's CURRENT hex.  In multiplayer or PBEM, right-clicking an enemy hero's level-up
event tracks the hero for the rest of the game.  Battle events store their hex instead
(TCombatEventLog.ViewLocation 0x55729274); this patch makes level-up events do the same.  It
applies to every level-up event, the player's own included.  AoWz.exe's logbook right-click is
`call [vmt+0x74]` at 0x004236AB, so the VMT slot is the whole path.

================================================================================
WHERE THE EVENT IS BORN -- and why the capture is there
================================================================================
THero.ValidateHeroUpgrade @0x55787D54 is the ONLY creator.  The classref cell 0x55711B48 has two
readers: this function and the class registration in TAoWEngine.Create+0x4A6.  No class derives
from THeroUpgradeEventLog; AoWz.exe only IsClass-tests it (0x0044F1DB).  On entry the function
calls GetLocation(hero) into a 3-byte local and leaves WITHOUT an event when the hero is unplaced
(local[0] = 0xFF) or owned by player 0.  Then:

    55787F46  TEventLog.Create(THeroUpgradeEventLog)
    55787F4F  [+0x1C] := old level      [+0x1D] := new level
    55787F6F  [+0x20] := player[+0x5C]              <- the owner's TURN COUNTER, see below
    55787F7B  [+0x18] := hero id
    55787F93  DistributeLocationEventLog(event, owner, x, y, level, 1)    <- HOOK

DistributeLocationEventLog @0x557FE558 walks every player.  For the owner, and for any player the
hex is not fogged for (FoggedForPlayer(x, y, level)), it makes a TEObject.Copy of the event and
calls TEventLogbook.AddEvent, then Execute for the seated human.  TEObject.Copy streams the event
out and back in (TEngine.WriteEObject/ReadEObject -> TEObject.MainReadWrite 0x555193B1 ->
VMT+0x18), so every per-player copy carries exactly what ReadWrite serialises.

So the capture is a CALL RETARGET of that `call` at 0x55787F93: 4 displacement bytes, nothing
displaced.  C_CAP stores the call's own (x, y, level) arguments into the event and tail-jumps to
DistributeLocationEventLog.  It stamps exactly the hex the engine uses for its fog test, so an
event only ever reaches a player who could see that hex, and it points there.

================================================================================
THE STORAGE -- a new field, because +0x20 IS in use
================================================================================
⚠ Inioch's note calls [+0x20] "serialised but otherwise unused".  In our DLL, which is vanilla
here (byte-identical to the root copy), it is written at 0x55787F6F with the owner's turn counter
player[+0x5C] (incremented in TPlayerControl.NewTurn at 0x55755524), and read back in
THeroUpgradeEventLog.Execute at 0x55785757:

    [hero+0x54] == 0 (no upgrade pending):
        player[+0x5C] == event[+0x20] -> "CanOnlyUpgradeHeroOnce"
        otherwise                     -> "CanOnlyUpgradeOnTheDayALevelIsMade"

Overwriting it with a location makes the double-click message wrong on the day of the level-up.
So the class GROWS by one dword instead (the technique of build_arena.py and build_spellcast.py;
memory note aow1-property-table-serialization):

    S1  instance size [VMT-0x1C] @0x55711B6C : 0x24 -> 0x28          (no .reloc; plain integer)
    new field  +0x24 x   +0x25 y   +0x26 map level   +0x27 valid flag = 1
    S2  VMT +0x18 ReadWrite @0x55711BA0 : 0x55785508 -> C_RW         (.reloc KEPT)
        C_RW calls the original, then rwInteger(&self[+0x24], id 0x1D).

Property ids share one namespace down the chain.  Read from the bytes: TEObject.ReadWrite is a
bare `ret`; TEventLog.ReadWrite 0x557FD44C uses 0x0A, 0x0B, 0x0C; THeroUpgradeEventLog.ReadWrite
0x55785508 uses 0x19, 0x1A, 0x1B, 0x1C.  0x1D is free.  The reader looks properties up by id
(TPropertyTable.FindOffset returns -1 and rwInteger skips), so an event from an older save lacks
0x1D and keeps its zero-initialised field, flag 0.  Delphi's InitInstance zero-fills the grown
instance, so no Create override is needed.

    S3  VMT +0x74 ViewLocation @0x55711BFC : 0x557857E0 -> C_VIEW    (.reloc KEPT)
        flag set   -> CenterViewTo(self, DL=[+0x24], CL=[+0x25], push [+0x26])
        flag clear -> jmp 0x557857E0 (vanilla: follows the hero -- events logged before this
                      patch, e.g. in existing saves)

Both slots hold absolute pointers that carry a HIGHLOW .reloc entry; the cave's preferred-base VA
goes in and the entry stays, so the loader rebases it.  Nothing is displaced anywhere.

⚠ S1 and S4 are one unit: C_CAP writes +0x24..+0x27, which is past the end of a 0x24-byte
instance.  This script writes and removes all four sites together and refuses any mixed state.

================================================================================
THE CAVES -- register/rel32 only, no anchor, no absolute operand
================================================================================
C_CAP  0x5584D000   entered by `call` from 0x55787F93.  EAX = event, DL = owner, CL = x,
                    [esp+4] = 1, [esp+8] = level, [esp+0xC] = y (Delphi pushes p4..p6 left to
                    right).  Seven byte moves (EDX saved round them), then jmp 0x557FE558 with
                    the stack exactly as found; its `ret 0xC` returns to 0x55787F98.
C_RW   0x5584D040   EAX = self, EDX = stream.  EBX/ESI saved.
C_VIEW 0x5584D080   EAX = self.  Uses EAX/ECX/EDX only.  CenterViewTo ends `ret 4`.
EXCLUSIVE reservation 0x5584D000..0x5584D0FF, asserted zero-or-ours on every run; --undo zeroes
the emitted bytes only.

================================================================================
DEVIATIONS FROM THE PORT (both deliberate)
================================================================================
1. Storage: a new dword at +0x24 (instance 0x24 -> 0x28, property 0x1D), not [+0x20]..[+0x23].
   Reason above: [+0x20] is the turn stamp Execute compares against.
2. Capture: at the creation call 0x55787F93, not by retargeting AddEvent's GetSynchronised call
   at 0x557FDB9D.  AddEvent has 37 callers -- every event class, our raze-event cave at
   0x5581452D and DistributeCombatEvent among them -- so a capture there needs a PIC VMT test,
   FindUnit and GetLocation on every event.  Here the engine has already computed the hex and
   passes it as arguments, and no other event class can reach the cave at all.

================================================================================
MULTIPLAYER / PBEM
================================================================================
Deterministic.  AddEvent asserts TAoWHSMap.GetSynchronised (0x557FDB9D), so a level-up event is
created and logged only inside synchronised execution (TAoWHSMap.MsgProc and the PBEM controls
bracket that with SynchroniseBegin/End at map[+0x234]).  Every peer runs ValidateHeroUpgrade ->
DistributeLocationEventLog -> Copy -> AddEvent in one call chain, with the hero on the same hex,
and nothing adds a level-up event later on a remote machine.  The field streams as property 0x1D,
so saves and PBEM files carry it.  No RNG of any kind; not a P4 site.  ⚠ Standing rule: no mixed
modded / unmodded multiplayer.

BEHAVIOUR NOTES
* A captured event centres on its stored hex even after the hero has died; vanilla did nothing
  when FindUnit failed.  The hex reveals nothing current.
* The hex is where the hero stood when ValidateHeroUpgrade ran: the start of the owner's turn
  (THero.NewTurn), which is when the event appears.
* Pre-patch events (existing saves) keep following the hero.
* After --undo, a save made with the patch still loads: the reader ignores property 0x1D.

BINARY -- AoWEPACK.dpl only.  Nothing in AoWz.exe / AoWzCompat.exe changes.

USAGE
    python build_scripts/build_levelup_eventloc.py            # verify only (never writes)
    python build_scripts/build_levelup_eventloc.py --dis      # + cave and site disassembly
    python build_scripts/build_levelup_eventloc.py --apply    # write (kills running AoW binaries)
    python build_scripts/build_levelup_eventloc.py --undo     # surgical: 4 sites back, caves zeroed
"""
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True          # a .pyc embeds the absolute source path -- never mint one
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                           # noqa: E402  -- names of the processes that lock binaries

# game dir = two levels up from this script (<game>/Ziggurat/Modding Resources/build_scripts/ ->
# <game>/Ziggurat); override with AOW_GAME_DIR (leave it unset for the real install).
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-levelupeventloc")

# ---------------------------------------------------------------- addresses ---
VMT          = 0x55711B88       # AoWE..THeroUpgradeEventLog
VMT_SELF     = VMT - 0x40       # vmtSelfPtr cell (the classref ValidateHeroUpgrade loads)
S_INSTSIZE   = VMT - 0x1C       # 0x55711B6C  instance size
S_VMT_RW     = VMT + 0x18       # 0x55711BA0  ReadWrite slot
S_VMT_VIEW   = VMT + 0x74       # 0x55711BFC  ViewLocation slot
S_CAPCALL    = 0x55787F93       # THero.ValidateHeroUpgrade: call DistributeLocationEventLog

F_HUEL_RW    = 0x55785508       # AoWE.THeroUpgradeEventLog.ReadWrite     EAX=self EDX=stream
F_HUEL_VIEW  = 0x557857E0       # AoWE.THeroUpgradeEventLog.ViewLocation  EAX=self (follows hero)
F_CENTERVIEW = 0x557FD5F4       # EventLog.TEventLog.CenterViewTo  EAX=self DL=x CL=y [push lvl], ret 4
F_DISTRIBUTE = 0x557FE558       # EventLog.DistributeLocationEventLog(ev, owner, x; y, lvl, popup), ret 0xC

INST_OLD, INST_NEW = 0x24, 0x28
FLD          = 0x24             # +0 x  +1 y  +2 map level  +3 valid flag
PROP_ID      = 0x1D             # new property id (chain uses 0x0A-0x0C, 0x19-0x1C)
STREAM_RWINT = 0x2C             # stream VMT slot: rwInteger(EAX=stream, EDX=ptr, ECX=id)

CAVE_BASE    = 0x5584D000
CAVE_END     = 0x5584D100       # EXCLUSIVE reservation, asserted zero-or-ours
C_CAP        = 0x5584D000
C_RW         = 0x5584D040
C_VIEW       = 0x5584D080

# Context the caves depend on, as installed in vanilla (and verified byte-identical in the live
# DLL 2026-09-24).  Asserted on every run: a mismatch means the contract below has moved.
CONTEXT = [
    # ValidateHeroUpgrade tail: Create(THeroUpgradeEventLog) .. stores .. the Distribute call.
    # Pins EAX = the new event (esi), CL = local[0], pushes local[1], local[2], 1.
    (0x55787F3D, "33c9b201a1481b7155e84d5407008bf08bc788461c8a454c88461d0fbe5524a140a08f55"
                 "8b8040010000e864c5fcff8b405c8946208a45248846108b45188946188a442401508a44"
                 "2406506a018a4c240c8a55248bc6",
     "ValidateHeroUpgrade: create event, stamp, push y/level/1, CL=x, EAX=event"),
    (0x557FE558, "558bec83c4f4535657884dfa8855fb",
     "DistributeLocationEventLog prologue: CL=x, DL=owner, stack y/level/popup"),
    (F_HUEL_RW, "5356578bf28bd88bd68bc3e8347f07008d5318b9190000008bc68b38ff572c8d531cb91a00"
                "00008bc68b38ff57308d531db91b0000008bc68b38ff57308d5320b91c0000008bc68b18ff"
                "532c5f5e5bc3",
     "THeroUpgradeEventLog.ReadWrite: ids 0x19-0x1C, fields end at +0x23"),
    (0x557FD44C, "5356578bf28bd88bd68bc3e8a05cf0ff8d5308b90a0000008bc68b38ff572c8d5310b90b00"
                 "00008bc68b38ff57308d530cb90c0000008bc68b18ff532c5f5e5bc3",
     "TEventLog.ReadWrite: ids 0x0A-0x0C"),
    (F_HUEL_VIEW, "53518bd8a140a08f558b80fc0000008b5318e85191ffff85c0742c8d542402528d4c2405"
                  "8d542404e88795ffff803c24ff74148a442402508a4c24058a5424048bc3e8cd7d07005a"
                  "5bc3",
     "THeroUpgradeEventLog.ViewLocation (the fallback)"),
    (F_CENTERVIEW, "558bec515356884dff8bda0fbe4508500fbe4dff0fbed3a194948e558b008b30ff96bc00"
                   "00008a450850a194948e558b008a4dff8bd3e8bd4df7ff5e5b595dc20400",
     "TEventLog.CenterViewTo: DL=x CL=y [ebp+8]=level, ret 4"),
]

# earlier bodies this script installed: sha256 of the span's non-zero prefix -> tag.
# --apply rewrites one of these in place; anything else in the span aborts.
KNOWN_BODIES = {}


# ======================================================================== PE ====
class PE:
    """Section-aware view of the DLL.  VA -> file offset is PER SECTION."""

    def __init__(self, path):
        if not os.path.exists(path):
            sys.exit("not found: %s" % path)
        with open(path, "rb") as f:
            self.d = bytearray(f.read())
        d = self.d
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        n = struct.unpack_from("<H", d, pe + 6)[0]
        opt = struct.unpack_from("<H", d, pe + 20)[0]
        self.base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
        self.secs = []
        for i in range(n):
            o = pe + 24 + opt + i * 40
            nm = bytes(d[o:o + 8]).rstrip(b"\0").decode("latin1")
            vsz, va, rsz, raw = struct.unpack_from("<IIII", d, o + 8)
            ch = struct.unpack_from("<I", d, o + 36)[0]
            self.secs.append((nm, self.base + va, vsz, raw, rsz, ch))
        self.reloc_rva, self.reloc_size = struct.unpack_from("<II", d, pe + 24 + 96 + 5 * 8)

    def sec_of(self, va):
        for s in self.secs:
            if s[1] <= va < s[1] + min(s[2], s[4]):        # file-backed only
                return s
        return None

    def off(self, va):
        s = self.sec_of(va)
        if s is None:
            raise ValueError("VA 0x%08X is not file-backed" % va)
        return s[3] + va - s[1]

    def rd(self, va, n):
        if self.sec_of(va + n - 1) is not self.sec_of(va):
            raise ValueError("run 0x%08X+%d crosses a section" % (va, n))
        o = self.off(va)
        return bytes(self.d[o:o + n])

    def u32(self, va):
        return struct.unpack("<I", self.rd(va, 4))[0]

    def reloc_types(self):
        """{target VA: [entry types]} for every entry in the base-relocation directory."""
        out = {}
        if not self.reloc_rva:
            return out
        p = self.off(self.base + self.reloc_rva)
        end = p + self.reloc_size
        while p < end - 8:
            page, blk = struct.unpack_from("<II", self.d, p)
            if blk < 8:
                break
            for q in range(p + 8, p + blk, 2):
                e = struct.unpack_from("<H", self.d, q)[0]
                out.setdefault(self.base + page + (e & 0xFFF), []).append(e >> 12)
            p += blk
        return out


def kill_game():
    """Standing authorisation: the game/editor lock the binaries.  Exact names only --
    AowEmailWrapper and Launcher lock nothing and are left alone."""
    if os.environ.get("AOW_GAME_DIR"):      # scratch tree: not the real install
        return
    for p in zigexe.LOCKING_PROCESSES:
        subprocess.run(["taskkill", "/F", "/IM", p + ".exe"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ================================================================ assembler ====
def _ks():
    try:
        from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    except ImportError:
        sys.exit("keystone-engine not installed:  pip install keystone-engine")
    return Ks(KS_ARCH_X86, KS_MODE_32)


def asm_at(lines, va):
    """Assemble `lines` (may use {LABEL} placeholders; a line "LABEL:" defines one) at `va`.
    Iterates to a fixed point so forward references settle."""
    ks = _ks()
    labels = {ln[:-1]: va for ln in lines if ln.endswith(":")}
    for _ in range(8):
        cur, out, seen = va, b"", {}
        for ln in lines:
            if ln.endswith(":"):
                seen[ln[:-1]] = cur
                continue
            text = ln.format(**{k: hex(v) for k, v in labels.items()})
            enc, _ = ks.asm(text, cur)
            if enc is None:
                raise RuntimeError("keystone failed on: %s" % text)
            out += bytes(enc)
            cur += len(enc)
        if seen == labels:
            return out
        labels = seen
    raise RuntimeError("layout did not converge at 0x%08X" % va)


def build_caves():
    """{entry VA: (name, bytes)}"""
    cap = asm_at([
        # EAX = event, DL = owner, CL = x; [esp+4] = 1, [esp+8] = level, [esp+0xC] = y
        "mov byte ptr [eax + %s], cl" % hex(FLD),            # x      (local[0])
        "push edx",                                          # keep DL = owner
        "mov dl, byte ptr [esp + 0x10]",                     # y      (p4, local[1])
        "mov byte ptr [eax + %s], dl" % hex(FLD + 1),
        "mov dl, byte ptr [esp + 0xc]",                      # level  (p5, local[2])
        "mov byte ptr [eax + %s], dl" % hex(FLD + 2),
        "mov byte ptr [eax + %s], 1" % hex(FLD + 3),         # valid
        "pop edx",
        "jmp %s" % hex(F_DISTRIBUTE),                        # stack as found; ret 0xC -> 0x55787F98
    ], C_CAP)
    rw = asm_at([
        # EAX = self, EDX = stream
        "push ebx",
        "push esi",
        "mov ebx, eax",
        "mov esi, edx",
        "call %s" % hex(F_HUEL_RW),                          # the class's own ReadWrite, unchanged
        "lea edx, [ebx + %s]" % hex(FLD),
        "mov ecx, %s" % hex(PROP_ID),
        "mov eax, esi",
        "mov esi, dword ptr [eax]",                          # stream VMT (esi's last use)
        "call dword ptr [esi + %s]" % hex(STREAM_RWINT),     # rwInteger(stream, &self[+0x24], 0x1D)
        "pop esi",
        "pop ebx",
        "ret",
    ], C_RW)
    view = asm_at([
        # EAX = self
        "cmp byte ptr [eax + %s], 0" % hex(FLD + 3),
        "je {ORIG}",
        "movzx ecx, byte ptr [eax + %s]" % hex(FLD + 2),     # level, pushed as CenterViewTo's 4th arg
        "push ecx",
        "mov cl, byte ptr [eax + %s]" % hex(FLD + 1),        # y
        "mov dl, byte ptr [eax + %s]" % hex(FLD),            # x
        "call %s" % hex(F_CENTERVIEW),                       # ret 4 pops the level
        "ret",
        "ORIG:",
        "jmp %s" % hex(F_HUEL_VIEW),                         # pre-patch event: vanilla behaviour
    ], C_VIEW)
    caves = {C_CAP: ("C_CAP", cap), C_RW: ("C_RW", rw), C_VIEW: ("C_VIEW", view)}

    entries = sorted(caves)
    for i, va in enumerate(entries):
        lim = entries[i + 1] if i + 1 < len(entries) else CAVE_END
        if va + len(caves[va][1]) > lim:
            raise RuntimeError("%s overruns 0x%08X" % (caves[va][0], lim))
    for va, (name, blob) in caves.items():
        assert_pic(name, blob, va)
    return caves


def assert_pic(name, blob, va):
    """The .dpl never loads at its preferred base: no memory operand may lack a base/index
    register, and no immediate outside a relative branch may look like an image VA."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    from capstone.x86 import X86_OP_IMM, X86_OP_MEM
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    seen = 0
    for i in md.disasm(blob, va):
        seen += len(i.bytes)
        rel = i.mnemonic == "call" or i.mnemonic.startswith("j")
        for op in i.operands:
            if op.type == X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                raise RuntimeError("%s: absolute memory operand at 0x%08X: %s %s"
                                   % (name, i.address, i.mnemonic, i.op_str))
            if (op.type == X86_OP_IMM and not rel
                    and 0x55700000 <= (op.imm & 0xFFFFFFFF) < 0x55A00000):
                raise RuntimeError("%s: image-VA immediate at 0x%08X: %s %s"
                                   % (name, i.address, i.mnemonic, i.op_str))
    if seen != len(blob):
        raise RuntimeError("%s does not disassemble cleanly" % name)


def rel32_call(site, to):
    return b"\xE8" + struct.pack("<i", to - (site + 5))


# (va, original, patched, description, reloc rule)   reloc rule: "none" | "slot"
def sites():
    return [
        (S_INSTSIZE, struct.pack("<I", INST_OLD), struct.pack("<I", INST_NEW),
         "THeroUpgradeEventLog instance size 0x24 -> 0x28", "none"),
        (S_VMT_RW, struct.pack("<I", F_HUEL_RW), struct.pack("<I", C_RW),
         "VMT +0x18 ReadWrite -> C_RW", "slot"),
        (S_VMT_VIEW, struct.pack("<I", F_HUEL_VIEW), struct.pack("<I", C_VIEW),
         "VMT +0x74 ViewLocation -> C_VIEW", "slot"),
        (S_CAPCALL, rel32_call(S_CAPCALL, F_DISTRIBUTE), rel32_call(S_CAPCALL, C_CAP),
         "ValidateHeroUpgrade: call DistributeLocationEventLog -> C_CAP", "none"),
    ]


# ================================================================== checks =====
def check_identity(pe):
    """Prove VMT really is THeroUpgradeEventLog, and that the context the caves assume holds."""
    if pe.u32(VMT_SELF) != VMT:
        sys.exit("ABORT: [0x%08X] is not the vmtSelfPtr of 0x%08X" % (VMT_SELF, VMT))
    np = pe.u32(VMT - 0x20)
    n = pe.rd(np, 1)[0]
    if pe.rd(np + 1, n) != b"THeroUpgradeEventLog":
        sys.exit("ABORT: VMT 0x%08X is not THeroUpgradeEventLog" % VMT)
    for va, hx, desc in CONTEXT:
        want = bytes.fromhex(hx)
        if pe.rd(va, len(want)) != want:
            sys.exit("ABORT: context moved at 0x%08X (%s)" % (va, desc))


def check_reloc(pe):
    """⚠ A stale .reloc entry corrupts live code at every load.  The two VMT slots MUST keep
    their HIGHLOW entry (that is what rebases the cave pointer); nothing else we own may carry
    one.  Returns the per-slot entry list for the report."""
    rt = pe.reloc_types()
    bad = []
    for va, _o, _p, desc, rule in sites():
        n = 4 if rule == "slot" else len(_o)
        if rule == "slot":
            if rt.get(va) != [3]:
                bad.append("0x%08X (%s) should carry exactly one HIGHLOW entry, has %s"
                           % (va, desc, rt.get(va)))
            for a in range(va + 1, va + n):
                if a in rt:
                    bad.append("0x%08X inside slot 0x%08X carries %s" % (a, va, rt[a]))
        else:
            for a in range(va - 3, va + n):      # a dword starting up to 3 bytes before overlaps
                if a in rt and any(t != 0 for t in rt[a]):
                    bad.append("0x%08X overlaps %s (entry %s)" % (a, desc, rt[a]))
    for a in range(CAVE_BASE - 3, CAVE_END):
        if a in rt and any(t != 0 for t in rt[a]):
            bad.append("cave span: entry at 0x%08X" % a)
    if bad:
        sys.exit("ABORT: .reloc:\n  " + "\n  ".join(bad))
    return {va: rt.get(va) for va, *_r in sites()}


def span_bytes(pe):
    return pe.rd(CAVE_BASE, CAVE_END - CAVE_BASE)


def ours_span(caves):
    s = bytearray(CAVE_END - CAVE_BASE)
    for va, (_n, blob) in caves.items():
        s[va - CAVE_BASE:va - CAVE_BASE + len(blob)] = blob
    return bytes(s)


def installed_known(pe):
    span = span_bytes(pe)
    nz = [i for i, b in enumerate(span) if b]
    if not nz:
        return None
    return KNOWN_BODIES.get(hashlib.sha256(span[:nz[-1] + 1]).hexdigest())


def state(pe, caves):
    cur = [pe.rd(va, len(o)) for va, o, _p, _d, _r in sites()]
    patched = all(c == p for c, (_v, _o, p, _d, _r) in zip(cur, sites()))
    vanilla = all(c == o for c, (_v, o, _p, _d, _r) in zip(cur, sites()))
    span = span_bytes(pe)
    if patched and span == ours_span(caves):
        return "applied"
    if vanilla and not any(span):
        return "vanilla"
    if patched and installed_known(pe):
        return "stale"              # our sites + a known earlier body: re-tune in place
    return "mixed"


def show(pe, caves, relocs=None):
    print("AoWEPACK.dpl  %s" % DLL)
    print("  hero level-up events centre on the level-up hex, not the hero's current one")
    for va, o, p, desc, rule in sites():
        c = pe.rd(va, len(o))
        tag = "PATCHED" if c == p else "vanilla" if c == o else "*** FOREIGN ***"
        rl = ""
        if relocs is not None:
            rl = "  reloc=%s" % (relocs.get(va) or "none")
        print("  site 0x%08X  %-8s %s  (%s)%s" % (va, tag, c.hex(), desc, rl))
    span = span_bytes(pe)
    for va, (name, blob) in sorted(caves.items()):
        c = pe.rd(va, len(blob))
        t = ("PATCHED" if c == blob else "zero" if not any(c) else "*** FOREIGN ***")
        print("  cave 0x%08X  %-8s %-6s %3d B" % (va, t, name, len(blob)))
    extra = [CAVE_BASE + i for i, (a, b) in enumerate(zip(span, ours_span(caves))) if a != b and a]
    if extra:
        print("  span 0x%08X..0x%08X: %d foreign/stale byte(s), first 0x%08X"
              % (CAVE_BASE, CAVE_END, len(extra), extra[0]))
    print("  state: %s" % state(pe, caves).upper())


def disassemble(caves):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    names = {F_HUEL_RW: "THeroUpgradeEventLog.ReadWrite", F_HUEL_VIEW: "THeroUpgradeEventLog.ViewLocation",
             F_CENTERVIEW: "TEventLog.CenterViewTo", F_DISTRIBUTE: "DistributeLocationEventLog"}
    for va, (name, blob) in sorted(caves.items()):
        print("\n---- 0x%08X  %s  (%d B)" % (va, name, len(blob)))
        for i in md.disasm(blob, va):
            note = ""
            if i.mnemonic in ("call", "jmp") and i.op_str.startswith("0x"):
                note = "  ; " + names.get(int(i.op_str, 16), "")
            print("  %08X  %-22s %s %s%s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str,
                                             note.rstrip(" ;")))
    for va, o, p, desc, _r in sites():
        print("\n---- site 0x%08X  %s" % (va, desc))
        print("  vanilla  %s" % o.hex())
        print("  patched  %s" % p.hex())
        if va == S_CAPCALL:
            for lab, run in (("vanilla", o), ("patched", p)):
                for i in md.disasm(run, va):
                    print("    %s  %08X  %s %s" % (lab, i.address, i.mnemonic, i.op_str))


# ================================================================== writing ====
def write_runs(runs):
    """In-place r+b writes of exactly the bytes this script owns."""
    pe = PE(DLL)
    offs = [(pe.off(va), blob) for va, blob in runs]
    for attempt in (1, 2):
        try:
            with open(DLL, "r+b") as f:
                for o, blob in offs:
                    f.seek(o)
                    f.write(blob)
            return
        except PermissionError:
            if attempt == 2:
                raise
            print("  AoWEPACK.dpl locked -> killing AoW processes and retrying")
            kill_game()
            time.sleep(1.0)


def do_apply(pe, caves):
    st = state(pe, caves)
    if st == "applied":
        print("already applied -- nothing to do.")
        return
    if st == "mixed":
        sys.exit("ABORT: partially applied / foreign bytes present.  Nothing written.")
    if st == "vanilla":
        span = span_bytes(pe)
        if any(span):
            sys.exit("ABORT: cave span 0x%08X..0x%08X is not zero" % (CAVE_BASE, CAVE_END))
        for va, o, _p, desc, _r in sites():
            if pe.rd(va, len(o)) != o:
                sys.exit("ABORT: 0x%08X is %s, expected %s (%s)"
                         % (va, pe.rd(va, len(o)).hex(), o.hex(), desc))

    kill_game()
    if st == "vanilla":
        # ⚠ minted on --apply ONLY, and only from a file PROVED unpatched for this feature:
        # all four sites equal their original bytes and the whole span is zero (checked above).
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("backup -> backups%s%s" % (os.sep, os.path.basename(BACKUP)))
    else:
        print("re-tune in place over %s -- no backup (the file is patched)" % installed_known(pe))

    runs = [(CAVE_BASE, ours_span(caves))]            # whole span: an old tail cannot survive
    runs += [(va, p) for va, _o, p, _d, _r in sites()]
    write_runs(runs)
    print("APPLIED: 3 caves, %d sites." % len(sites()))


def do_undo(pe, caves):
    st = state(pe, caves)
    if st == "vanilla":
        print("not applied -- nothing to undo.")
        return
    if st == "stale":
        sys.exit("ABORT: an older body (%s) is installed; run --apply first so --undo zeroes "
                 "exactly what is there" % installed_known(pe))
    for va, o, p, desc, _r in sites():
        c = pe.rd(va, len(o))
        if c not in (o, p):
            sys.exit("ABORT: 0x%08X is foreign (%s) -- %s" % (va, c.hex(), desc))
    span, ours = span_bytes(pe), ours_span(caves)
    for i, (a, b) in enumerate(zip(span, ours)):
        if a and a != b:
            sys.exit("ABORT: cave span byte 0x%08X = 0x%02X is not ours" % (CAVE_BASE + i, a))

    kill_game()
    runs = [(va, o) for va, o, _p, _d, _r in sites()]
    runs += [(va, bytes(len(blob))) for va, (_n, blob) in caves.items()]   # emitted bytes only
    write_runs(runs)
    print("UNDONE: %d sites restored, caves zeroed.  No backup touched." % len(sites()))


def main():
    args = sys.argv[1:]
    pe = PE(DLL)
    check_identity(pe)
    caves = build_caves()
    relocs = check_reloc(pe)
    if "--dis" in args or "--show" in args:
        disassemble(caves)
        print()
    if "--undo" in args:
        do_undo(pe, caves)
    elif "--apply" in args:
        do_apply(pe, caves)
    else:
        show(pe, caves, relocs)
        print("\n(dry run -- pass --apply to write, --dis to disassemble the caves)")
        return
    pe = PE(DLL)
    check_identity(pe)
    show(pe, caves, check_reloc(pe))
    want = "vanilla" if "--undo" in args else "applied"
    if state(pe, caves) != want:
        sys.exit("ABORT: post-write state is %s, expected %s" % (state(pe, caves), want))


if __name__ == "__main__":
    main()
