#!/usr/bin/env python3
r"""
AoW1 mod -- "heroskill_keep": a hero who spends no skill points at a level-up is offered the same
abilities at the next level-up.  Owner's design, 2026-10-29, after two players lost the expensive
ability they had saved points for to the next level-up's re-roll.

    "if they didn't spend any points on the previous level up, then the previous level up's
     offered ability list should be preserved for the next level up and offered the same that
     time."

No new button.  Spending nothing covers Done with nothing bought and never opening the dialog.
Any points spent (a stat or an ability) and the next level-up rolls fresh, as before.  Record:
Zig notes/07-ui.md section 2.8c.

================================================================================
HOW THE OFFER IS ROLLED -- why one stored byte is enough
================================================================================
The Upgrades columns are filtered by build_heroskill_race.py's gate in AoWz.exe (P4 derived hash,
no draw): an ability is offered iff hash(salt map[+0x22C], hero unit id, LEVEL, ability id) % 100
< its race's percentage.  The offer is therefore a pure function of that level byte.  Keeping an
offer = hashing the old level again.  Since 2026-10-29 the gate hashes [hero+0x4D] when it is
non-zero and the level cache [hero+0x4C] otherwise; this script maintains [hero+0x4D].

    [hero+0x4D]  OFFER LEVEL   the level whose roll the hero is offered.  0 = none stored.
                               Streamed as THero property 0x400.  Synchronised state.
    [hero+0x4E]  word, scratch THero.UsedSkillPoints before an upgrade is applied (C_PRE -> C_POST
                               within one THeroUpgradeTE.Execute).  Not streamed.

+0x4D..+0x4F are alignment padding between the level-cache byte +0x4C (property 0x16) and the
dword +0x50 (property 0x27).  Proved unused 2026-10-29: fieldrefs over AoWEPACK, AoWz.exe,
AoWzEd.exe, AoWTCPCK and every mod code section found no THero/TLeader access to +0x4D..+0x4F and
every THero access to +0x4C is a byte access.  THero instance 0x9C, TLeader 0xA4 (its only
subclass) -- neither grows.

================================================================================
THE STATE MACHINE -- every write happens in synchronised engine code
================================================================================
    level-up  (C_LVL, ValidateHeroUpgrade, every peer at the start of the owner's turn)
              offer level 0  -> offer level := the new level            (a fresh roll)
              offer level set -> unchanged                              (the kept roll)
              owner is an AI ([player+0xA7] != 0) -> offer level := 0  (see AI below)
    upgrade   (C_PRE + C_POST, THeroUpgradeTE.Execute, every peer: the token event Done sends)
              UsedSkillPoints changed across the upgrade -> offer level := 0
    dialog    (build_heroskill_race.py's gate, AoWz.exe, the owner's machine only, read-only)
              seed := offer level, or the level cache when it is 0

Traces.  Level 5, buys nothing (Done or never opens): offer level stays 5.  Level 6 offers level
5's roll again; buys something: offer level := 0.  Level 7: 0 -> 7, a fresh roll.

"Points spent" = THero.UsedSkillPoints @0x55786CC8 differs before and after the upgrade.  It sums
the six stats at their prices and every own ability's ExpandCost minus the chassis's, so any stat
or ability bought counts, and Done with nothing bought does not.  An ability whose cost is 0
(no Ability.pfs tag 6) is not spending: the offer is kept and CanExpand drops the bought ability.
The check is in the engine, not the dialog, so it is identical on every peer and also covers the
PBEM turn-1 leader window (build_pbem_leadersetup.py), which sends the same token event.

================================================================================
EDGE CASES (settled 2026-10-29)
================================================================================
* Several levels at once.  ValidateHeroUpgrade jumps the level cache straight to the new level and
  raises ONE event, so a two-level gain is one level-up: one dialog, one stored roll.  A dialog
  can only be used on the day its level is made (the turn start clears [hero+0x54]); a hero who
  skips it carries the points and, under this rule, the offer.
* An ability gained in between (event, scenario, Heroic choice).  The gate sits after CanExpand
  and the astHeroUpgrade mask test, so a single-level ability the hero now owns drops out of the
  kept list and a multi-level one is offered at its next level.  Gaining one is not spending: the
  check runs only inside THeroUpgradeTE.Execute.  Items do not touch the hero's own abilities.
* An ability no longer allowed (mask, level cap, a re-baked race table).  Same filters, same
  place: the kept list is the old roll intersected with what is allowed now.  A re-baked
  heroskill_races table changes the kept list too (the thresholds are read live).
* AI heroes.  The rule does not apply: THero.ExecuteUpgradeHeroAI picks from every ability and
  never sees the gate.  C_LVL zeroes an AI hero's offer level at each level-up, so a hero that
  later passes to a human starts with a fresh roll.
* Old saves.  The byte is 0 until the hero's first level-up under this patch, and the gate then
  hashes the level cache -- the same offer as before.  A pending level-up dialog in an old save
  shows what it showed.
* Campaign carry-over.  The offer level travels with the hero, but the salt map[+0x22C] belongs to
  the new game, so the next map's kept list is a different (still unbiased) roll.
* Day 1.  build_hero_turn1_upgrade.py's day-1 lag is a level-up like any other: a leader who
  spends nothing on day 1 keeps the day-1 roll.

Dialog-before-C_LVL ordering is harmless: DistributeLocationEventLog can open the dialog for the
seated human before C_LVL runs, but C_LVL only ever turns 0 into the current level, which is what
the gate already falls back to.

================================================================================
RNG -- no draw (12-re-toolchain.md 4.10)
================================================================================
This script draws nothing.  The only randomness is build_heroskill_race.py's P4 derived hash in
AoWz.exe; this changes one of its inputs (the level byte) to synchronised, streamed hero state.
Q1: the offer is player-visible state that must agree on a reopen and on every peer -> not P3.
Q2: the same situation must give the same answer later (reopen, save/reload, the NEXT level-up)
-> P4, as before.  rng_audit.py --owners: nothing new; --hash: the one heroskill_race site.

================================================================================
SITES  (AoWEPACK.dpl; nothing here is a VMT slot, so no .reloc entry is involved)
================================================================================
    0x557888BC  THero.ReadWrite: call TAbstractUnit.ReadWrite      rel32 -> C_RW
    0x55787FAE  ValidateHeroUpgrade: call TPlayerList.GetPlayers   rel32 -> C_LVL
                (the level-up branch, after the event; EBP = hero, [ebp+0x4C] = new level)
    0x55785495  THeroUpgradeTE.Execute: call THero.SetUnitAttack   rel32 -> C_PRE
                (first instruction of the applied path; EAX = EDI = hero, ESI = the event)
    0x557854E9  THeroUpgradeTE.Execute epilogue, 5 B `mov eax,ebx ; pop edi ; pop esi ; pop ebx`
                -> `jmp C_POST`.  Every path out of Execute lands here (three `je` from the
                validation); the original `ret` at 0x557854EE stays and is unreachable.  No
                .reloc entry and no branch target inside the 5 bytes (asserted).

THero.ReadWrite is reached by TLeader.ReadWrite through a direct call (0x5578B47B), so the leader
streams the byte too; that is why the hook is inside THero.ReadWrite and not on a VMT slot.

================================================================================
CAVES  0x558CE000..0x558CE0FF, exclusive.  PIC: rel32 and register-relative only.
================================================================================
    C_RW   0x558CE000  TAbstractUnit.ReadWrite, then rwByte(&hero[+0x4D], 0x400).  EBX and ESI are
                       kept: THero.ReadWrite holds the owner byte in BL across this call.
    C_LVL  0x558CE040  0 -> new level; GetPlayers; AI -> 0.  EAX returned unchanged.
    C_PRE  0x558CE080  [hero+0x4E] := UsedSkillPoints; [event+0x1B] := 1; jmp SetUnitAttack.
    C_POST 0x558CE0C0  if [event+0x1B]: clear it; UsedSkillPoints != [hero+0x4E] -> [hero+0x4D]
                       := 0.  Then vanilla's epilogue.

[event+0x1B] is THeroUpgradeTE's padding byte (+0x1A is the last stat delta, +0x1C the ability
owner; instance 0x20, zero-filled on both the sender and every receiving peer).  It is the "C_PRE
ran" mark, so C_POST never measures a unit the validation rejected.

Property 0x400: ids in the THero chain are TCustomAbilityList 2, TAbilityOwner 3 and 0x31,
TAbstractUnit 4-6 and 0x2F-0x30, THero 7-0x27, TLeader 0x2D, and 0x32 + ability id for every
levelled ability (up to 0x131 for ability 0xFF).  The gaps below 0x32 may be ids older editors
wrote, so 0x400, a long-format entry (TPropertyTable.SaveToStream writes ids > 0x7F in full).
rwByte writes nothing for 0, so a hero without a kept offer adds nothing to a save, and an
unpatched DLL ignores the id.

================================================================================
FORWARD HAZARDS
================================================================================
* build_heroskill_race.py's cave reads [hero+0x4D] (HERO_OFFER).  Both halves are safe alone:
  without this script the byte stays 0 and the gate hashes the level cache.
* build_leadership_aura.py owns the call at 0x557854E0 and build_pbem_leadersetup.py pins
  0x557854DB..0x557854E8; C_POST starts right after that run.  Neither is touched.
* build_heroicchoice.py's cave_teexec (THeroUpgradeTE VMT +0x4C) sends heroes on to the vanilla
  Execute this script hooks; its TUnit path never reaches C_PRE/C_POST.
* build_levelup_eventloc.py pins 0x55787F3D..0x55787F92; C_LVL's site 0x55787FAE is after it.
* Any further THero field in +0x4F, or a THero/TLeader property 0x400, collides with this.

BINARY -- AoWEPACK.dpl here; the AoWz.exe half is build_heroskill_race.py (input 3).

USAGE
    python build_scripts/build_heroskill_keep.py            # verify only (never writes)
    python build_scripts/build_heroskill_keep.py --dis      # + cave disassembly
    python build_scripts/build_heroskill_keep.py --apply    # write (kills running AoW binaries)
    python build_scripts/build_heroskill_keep.py --undo     # surgical: 4 sites back, caves zeroed
"""
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
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-heroskillkeep")

# ---------------------------------------------------------------- addresses ---
THERO_VMT    = 0x55711FEC       # AoWE..THero
TLEADER_VMT  = 0x55712238       # AoWE..TLeader (THero's only subclass)
TE_VMT       = 0x55711920       # AoWE..THeroUpgradeTE

S_RW         = 0x557888BC       # THero.ReadWrite: call TAbstractUnit.ReadWrite
S_LVL        = 0x55787FAE       # THero.ValidateHeroUpgrade: call TPlayerList.GetPlayers
S_PRE        = 0x55785495       # THeroUpgradeTE.Execute: call THero.SetUnitAttack
S_POST       = 0x557854E9       # THeroUpgradeTE.Execute: epilogue (5 B displaced)

F_ABSU_RW    = 0x557820E4       # AoWE.TAbstractUnit.ReadWrite   EAX=self EDX=stream
F_GETPLAYERS = 0x557544D0       # AoWE.TPlayerList.GetPlayers    EAX=list EDX=index -> EAX
F_SETATTACK  = 0x557877BC       # AoWE.THero.SetUnitAttack       EAX=hero DL=value
F_USEDSP     = 0x55786CC8       # AoWE.THero.UsedSkillPoints     EAX=hero -> EAX

HERO_LEVEL   = 0x4C             # level cache (byte, property 0x16)
HERO_OFFER   = 0x4D             # kept offer level (byte, property PROP_ID)
HERO_BEFORE  = 0x4E             # word scratch: UsedSkillPoints before an upgrade
TE_MARK      = 0x1B             # THeroUpgradeTE padding byte: C_PRE ran
PLAYER_AI    = 0xA7             # TPlayer: AI level, 0 = human
PROP_ID      = 0x400
STREAM_RWBYTE = 0x30            # stream VMT slot: rwByte(EAX=stream, EDX=ptr, ECX=id)

CAVE_BASE    = 0x558CE000
CAVE_END     = 0x558CE100       # EXCLUSIVE reservation, asserted zero-or-ours
C_RW         = 0x558CE000
C_LVL        = 0x558CE040
C_PRE        = 0x558CE080
C_POST       = 0x558CE0C0

POST_ORIG    = bytes.fromhex("8bc35f5e5b")      # mov eax,ebx ; pop edi ; pop esi ; pop ebx

# Context the caves depend on (live bytes 2026-10-29).  Asserted every run.
CONTEXT = [
    (0x55788880, "53565755518bf28bf88a5f248d5744b9080000008bc68b28ff552c8bc68b10ff1222053"
                 "48b78558a15388b78553ad075078bc7e8ccf0ffff8bd68bc7",
     "THero.ReadWrite to the hooked call: ESI = stream, EDI = hero, BL = owner across it"),
    (0x557888C1, "8bc68b10ff12", "THero.ReadWrite after the call: reads ESI again"),
    (0x5578B470, "5356578bf28bd88bd68bc3e800d4ffff",
     "TLeader.ReadWrite calls THero.ReadWrite directly"),
    (0x55787F30, "c64554010fb67d4c8bc688454c",
     "ValidateHeroUpgrade level-up branch: pending := 1, [ebp+0x4C] := new level"),
    (0x55787F98, "8bc68b10ff522c0fbe5524a140a08f558b8040010000",
     "ValidateHeroUpgrade: event vcall, then GetPlayers(owner) -- EBP is still the hero"),
    (0x55787FB3, "80b8a70000000074078bc5e861faffff",
     "ValidateHeroUpgrade: [player+0xA7] != 0 -> ExecuteUpgradeHeroAI"),
    (0x55785450, "5356578bf08bc6e8f8e1f7ff8bd8a140a08f558b80fc0000008b5610e8d794ffff8bf885ff"
                 "74728bc78b10ff92e000000084c074648a47243a4614755c8a576a0256158bc7",
     "THeroUpgradeTE.Execute: ESI = event, EDI = hero, EBX = result; validation jumps to 0x557854E9"),
    (0x5578549A, "8a576b0256168bc7e8612300008a576f0256178bc7e8842400008a576c0256188bc7e893"
                 "2300008a576e0256198bc7e81e2400008a576d02561a8bc7e8c5230000",
     "THeroUpgradeTE.Execute: the other five stat setters (ESI/EDI untouched)"),
    (0x557854EE, "c3", "THeroUpgradeTE.Execute: the ret after the displaced epilogue"),
    (0x55786CC8, "5356578bf0", "THero.UsedSkillPoints prologue: EAX = hero, callee-saved EBX/ESI/EDI"),
]


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
            self.secs.append((nm, self.base + va, vsz, raw, rsz))
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
    """Standing authorisation: the game/editor lock the binaries."""
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
    rw = asm_at([
        # EAX = hero, EDX = stream (THero.ReadWrite's own call); BL must survive
        "push ebx",
        "push esi",
        "mov ebx, eax",
        "mov esi, edx",
        "call %s" % hex(F_ABSU_RW),                          # what the call did
        "lea edx, [ebx + %s]" % hex(HERO_OFFER),
        "mov ecx, %s" % hex(PROP_ID),
        "mov eax, esi",
        "mov esi, dword ptr [eax]",                          # stream VMT (esi's last use)
        "call dword ptr [esi + %s]" % hex(STREAM_RWBYTE),    # rwByte(stream, &hero[+0x4D], 0x400)
        "pop esi",
        "pop ebx",
        "ret",
    ], C_RW)
    lvl = asm_at([
        # EAX = player list, EDX = owner index; EBP = hero, [ebp+0x4C] = the new level
        "cmp byte ptr [ebp + %s], 0" % hex(HERO_OFFER),
        "jne {KEPT}",
        "mov cl, byte ptr [ebp + %s]" % hex(HERO_LEVEL),
        "mov byte ptr [ebp + %s], cl" % hex(HERO_OFFER),     # no kept offer: this level's roll
        "KEPT:",
        "call %s" % hex(F_GETPLAYERS),                       # what the call did; EAX = player
        "cmp byte ptr [eax + %s], 0" % hex(PLAYER_AI),
        "je {HUMAN}",
        "mov byte ptr [ebp + %s], 0" % hex(HERO_OFFER),      # AI: spends now, never sees an offer
        "HUMAN:",
        "ret",
    ], C_LVL)
    pre = asm_at([
        # EAX = EDI = hero, DL = new ATK, ESI = the THeroUpgradeTE; validation has passed
        "push eax",
        "push edx",
        "call %s" % hex(F_USEDSP),                           # points used before the upgrade
        "mov edx, dword ptr [esp + 4]",
        "mov word ptr [edx + %s], ax" % hex(HERO_BEFORE),
        "mov byte ptr [esi + %s], 1" % hex(TE_MARK),         # this Execute applies
        "pop edx",
        "pop eax",
        "jmp %s" % hex(F_SETATTACK),                         # what the call did
    ], C_PRE)
    post = asm_at([
        # every path out of Execute: EBX = result, ESI = the event, EDI = hero (or not)
        "cmp byte ptr [esi + %s], 0" % hex(TE_MARK),
        "je {OUT}",
        "mov byte ptr [esi + %s], 0" % hex(TE_MARK),
        "mov eax, edi",
        "call %s" % hex(F_USEDSP),                           # points used after the upgrade
        "cmp ax, word ptr [edi + %s]" % hex(HERO_BEFORE),
        "je {OUT}",
        "mov byte ptr [edi + %s], 0" % hex(HERO_OFFER),      # spent: the next level-up rolls fresh
        "OUT:",
        "mov eax, ebx",                                      # the displaced epilogue
        "pop edi",
        "pop esi",
        "pop ebx",
        "ret",
    ], C_POST)
    caves = {C_RW: ("C_RW", rw), C_LVL: ("C_LVL", lvl), C_PRE: ("C_PRE", pre),
             C_POST: ("C_POST", post)}

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


def rel32(op, site, to):
    return bytes([op]) + struct.pack("<i", to - (site + 5))


# (va, original, patched, description)
def sites():
    return [
        (S_RW, rel32(0xE8, S_RW, F_ABSU_RW), rel32(0xE8, S_RW, C_RW),
         "THero.ReadWrite: call TAbstractUnit.ReadWrite -> C_RW"),
        (S_LVL, rel32(0xE8, S_LVL, F_GETPLAYERS), rel32(0xE8, S_LVL, C_LVL),
         "ValidateHeroUpgrade: call GetPlayers -> C_LVL"),
        (S_PRE, rel32(0xE8, S_PRE, F_SETATTACK), rel32(0xE8, S_PRE, C_PRE),
         "THeroUpgradeTE.Execute: call SetUnitAttack -> C_PRE"),
        (S_POST, POST_ORIG, rel32(0xE9, S_POST, C_POST),
         "THeroUpgradeTE.Execute: epilogue -> jmp C_POST"),
    ]


# ================================================================== checks =====
def check_identity(pe):
    """Prove the VMTs and the context the caves assume."""
    for vmt, name, inst in ((THERO_VMT, b"THero", 0x9C), (TLEADER_VMT, b"TLeader", 0xA4),
                            (TE_VMT, b"THeroUpgradeTE", 0x20)):
        if pe.u32(vmt - 0x40) != vmt:
            sys.exit("ABORT: [0x%08X] is not the vmtSelfPtr of 0x%08X" % (vmt - 0x40, vmt))
        np = pe.u32(vmt - 0x20)
        n = pe.rd(np, 1)[0]
        if pe.rd(np + 1, n) != name:
            sys.exit("ABORT: VMT 0x%08X is not %s" % (vmt, name.decode()))
        if pe.u32(vmt - 0x1C) != inst:
            sys.exit("ABORT: %s instance size is 0x%X, expected 0x%X -- the padding claim "
                     "(+0x4D..+0x4F, event +0x1B) must be re-proved"
                     % (name.decode(), pe.u32(vmt - 0x1C), inst))
    if pe.u32(pe.u32(TLEADER_VMT - 0x18)) != THERO_VMT:          # vmtParent is double-indirect
        sys.exit("ABORT: TLeader's parent is not THero")
    for va, hx, desc in CONTEXT:
        want = bytes.fromhex(hx)
        if pe.rd(va, len(want)) != want:
            sys.exit("ABORT: context moved at 0x%08X (%s)" % (va, desc))


def check_reloc(pe):
    """⚠ A stale .reloc entry corrupts live code at every load.  No entry may touch a site or the
    cave span."""
    rt = pe.reloc_types()
    bad = []
    for va, o, _p, desc in sites():
        for a in range(va - 3, va + len(o)):     # a dword starting up to 3 bytes before overlaps
            if a in rt and any(t != 0 for t in rt[a]):
                bad.append("0x%08X overlaps %s (entry %s)" % (a, desc, rt[a]))
    for a in range(CAVE_BASE - 3, CAVE_END):
        if a in rt and any(t != 0 for t in rt[a]):
            bad.append("cave span: entry at 0x%08X" % a)
    if bad:
        sys.exit("ABORT: .reloc:\n  " + "\n  ".join(bad))


def check_no_branch_into(pe):
    """No rel8/rel32 branch in CODE may land strictly inside the displaced epilogue.  The scan is
    linear over raw bytes, so a hit is a candidate to read, not proof."""
    lo, hi = S_POST, S_POST + len(POST_ORIG)
    hits = []
    for nm, sva, vsz, raw, rsz in pe.secs:
        if nm != "CODE":
            continue
        blob = bytes(pe.d[raw:raw + min(vsz, rsz)])
        for i in range(len(blob) - 6):
            b = blob[i]
            tgt = None
            if b in (0xE8, 0xE9):
                tgt = sva + i + 5 + struct.unpack_from("<i", blob, i + 1)[0]
            elif b == 0x0F and 0x80 <= blob[i + 1] <= 0x8F:
                tgt = sva + i + 6 + struct.unpack_from("<i", blob, i + 2)[0]
            elif 0x70 <= b <= 0x7F or b == 0xEB:
                tgt = sva + i + 2 + struct.unpack_from("<b", blob, i + 1)[0]
            if tgt is not None and lo < tgt < hi:
                hits.append((sva + i, tgt))
    return hits


def span_bytes(pe):
    return pe.rd(CAVE_BASE, CAVE_END - CAVE_BASE)


def ours_span(caves):
    s = bytearray(CAVE_END - CAVE_BASE)
    for va, (_n, blob) in caves.items():
        s[va - CAVE_BASE:va - CAVE_BASE + len(blob)] = blob
    return bytes(s)


def state(pe, caves):
    cur = [pe.rd(va, len(o)) for va, o, _p, _d in sites()]
    patched = all(c == p for c, (_v, _o, p, _d) in zip(cur, sites()))
    vanilla = all(c == o for c, (_v, o, _p, _d) in zip(cur, sites()))
    span = span_bytes(pe)
    if patched and span == ours_span(caves):
        return "applied"
    if vanilla and not any(span):
        return "vanilla"
    return "mixed"


def show(pe, caves):
    print("AoWEPACK.dpl  %s" % DLL)
    print("  a hero who spent nothing at a level-up is offered the same abilities at the next")
    for va, o, p, desc in sites():
        c = pe.rd(va, len(o))
        tag = "PATCHED" if c == p else "vanilla" if c == o else "*** FOREIGN ***"
        print("  site 0x%08X  %-8s %s  (%s)" % (va, tag, c.hex(), desc))
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
    names = {F_ABSU_RW: "TAbstractUnit.ReadWrite", F_GETPLAYERS: "TPlayerList.GetPlayers",
             F_SETATTACK: "THero.SetUnitAttack", F_USEDSP: "THero.UsedSkillPoints"}
    for va, (name, blob) in sorted(caves.items()):
        print("\n---- 0x%08X  %s  (%d B)" % (va, name, len(blob)))
        for i in md.disasm(blob, va):
            note = ""
            if i.mnemonic in ("call", "jmp") and i.op_str.startswith("0x"):
                note = names.get(int(i.op_str, 16), "")
            print("  %08X  %-22s %s %s%s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str,
                                             ("  ; " + note) if note else ""))
    for va, o, p, desc in sites():
        print("\n---- site 0x%08X  %s" % (va, desc))
        for lab, run in (("vanilla", o), ("patched", p)):
            for i in md.disasm(run, va):
                print("  %s  %08X  %-12s %s %s" % (lab, i.address, i.bytes.hex(), i.mnemonic,
                                                   i.op_str))


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
    hits = check_no_branch_into(pe)
    if hits:
        sys.exit("ABORT: a branch lands inside the epilogue window: %s"
                 % [(hex(a), hex(t)) for a, t in hits[:8]])

    kill_game()
    # ⚠ minted on --apply ONLY, from a file PROVED unpatched for this feature: all four sites
    # equal their original bytes and the whole span is zero (state() == "vanilla").
    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("backup -> backups%s%s" % (os.sep, os.path.basename(BACKUP)))
    else:
        print("backup already exists: backups%s%s" % (os.sep, os.path.basename(BACKUP)))

    runs = [(CAVE_BASE, ours_span(caves))]
    runs += [(va, p) for va, _o, p, _d in sites()]
    write_runs(runs)
    print("APPLIED: 4 caves, %d sites." % len(sites()))


def do_undo(pe, caves):
    st = state(pe, caves)
    if st == "vanilla":
        print("not applied -- nothing to undo.")
        return
    for va, o, p, desc in sites():
        c = pe.rd(va, len(o))
        if c not in (o, p):
            sys.exit("ABORT: 0x%08X is foreign (%s) -- %s" % (va, c.hex(), desc))
    span, ours = span_bytes(pe), ours_span(caves)
    for i, (a, b) in enumerate(zip(span, ours)):
        if a and a != b:
            sys.exit("ABORT: cave span byte 0x%08X = 0x%02X is not ours" % (CAVE_BASE + i, a))

    kill_game()
    runs = [(va, o) for va, o, _p, _d in sites()]
    runs += [(CAVE_BASE, bytes(CAVE_END - CAVE_BASE))]
    write_runs(runs)
    print("UNDONE: %d sites restored, caves zeroed.  No backup touched." % len(sites()))


def main():
    args = sys.argv[1:]
    pe = PE(DLL)
    check_identity(pe)
    caves = build_caves()
    check_reloc(pe)
    if "--dis" in args or "--show" in args:
        disassemble(caves)
        print()
    if "--undo" in args:
        do_undo(pe, caves)
    elif "--apply" in args:
        do_apply(pe, caves)
    else:
        show(pe, caves)
        print("\n(dry run -- pass --apply to write, --dis to disassemble the caves)")
        return
    pe = PE(DLL)
    check_identity(pe)
    check_reloc(pe)
    show(pe, caves)
    want = "vanilla" if "--undo" in args else "applied"
    if state(pe, caves) != want:
        sys.exit("ABORT: post-write state is %s, expected %s" % (state(pe, caves), want))


if __name__ == "__main__":
    main()
