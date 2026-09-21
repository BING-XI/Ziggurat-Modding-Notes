#!/usr/bin/env python3
r"""
AoW1 mod -- "gripofwinter": Freeze Water becomes GRIP OF WINTER.

FULL DESIGN: Modding Resources/Zig notes/GripOfWinter_Design.md
Prior art (same file, same hook idiom): build_icestorm_lava.py, build_terror_oncepercombat.py

================================================================================
WHAT THIS DOES
================================================================================
  1. COOLS TERRAIN, one step per cast:  Desert(2) -> Steppe(4) -> Grass(1) -> Snow(3)
     Snow is the floor. Wasteland/Lava/Dirt/Ice are deliberately NOT on the ladder.
  2. CASTABLE ON ANY HEX, not just water (both target gates widened).
  3. THE COOLING REVERTS, on the same timer that melts the ice back.
  4. The water arm is untouched: Water(0)->Ice(6), CaveWater(A)->CaveIce(D).

The rename itself is NOT here -- it is a data row in `Dict/ResStr.*`
(build_resstr_names.py) plus the `Release/Spells.pfs` rec 20 tag 10 description
(build_pfs_typos.py). This script is the binary half only.

================================================================================
BASELINE -- verified, and it matters for --undo
================================================================================
Every Freeze Water function is byte-identical to AoWEPACK_original_backup.dpl
EXCEPT one byte:

    0x5579E96B   mov edx,0xB  ->  mov edx,0x20      (live)

That is the initial freeze countdown range: pristine Random(0xB) = 1-4 turns,
live Random(0x20) = 2-8 turns. It is a PRE-CONVENTION ORPHAN EDIT with no owning
build script and nothing to re-derive it from.

*** This script must never touch it, and --undo must not "restore" it. ***
The hook at 0x5579E984 sits 0x19 bytes past it and does not displace it.

================================================================================
THE TEMPORARY-TERRAIN MARKER  (why this feature is cheap)
================================================================================
AoWE.TFrozenWaterHS (ClassID 0x2016C, VMT 0x557147B4, class-ref slot 0x55714774)
already does all the hard work: a per-turn countdown, an owner, save/load, and a
melt that goes through ChangeTerrainEx so transitions/roads/bridges update.

    instance size [VMT-0x1C] = 0x10
    +0x04  map field        +0x0C  countdown        +0x0D  owner
    +0x0E, +0x0F            FREE -- Delphi alignment padding

All eight of its methods were disassembled; NONE references +0x0E or +0x0F. (The
only `+8` in the family is [ebx+8] inside TerrainChanged, which is the incoming
notification struct in EDX, not Self.) So no class resize, no allocation change.

    +0x0E = terrain to RESTORE.  0 means "vanilla ice marker" -- which is also
            vanilla's restore value for Ice(6), so the sentinel is free, and every
            marker in an existing save reads 0 and behaves exactly as before.
    +0x0F = the terrain this marker SET, so TerrainChanged can tell "my change
            still stands" from "someone else overwrote this hex".

RE-CASTING (user decision 2026-08-31): the marker REMEMBERS THE ORIGINAL.
Cool a hex desert -> steppe -> grass and it reverts straight to DESERT in one hop.
This is why C_HSTC exists: ChangeTerrainEx notifies the marker BEFORE the spell's
own commit callback runs, so C_HSTC is the only place that sees the second cast
while +0x0E still holds the original. Without it the marker would destroy itself
there, C_TCFIN would build a fresh one saying "restore steppe", and one step of
cooling would become permanent.

================================================================================
THE EIGHT EDITS
================================================================================
Seven E9 hooks + two in-place gate widenings (the gates share no cave).

  C_COOL   0x5579E89B  TFreezeWaterTE.ChangeTerrain -- the ladder. Sits AFTER the
                       GetArmyHS gate, so cooling inherits "not under an army".
  C_TCCLS  0x5579E90E  TFreezeWaterTE.TerrainChanged -- decides whether this hex
                       earns a marker (water arm OR a legal ladder step).
  C_TCFIN  0x5579E984  ... and stamps +0x0E/+0x0F once the marker exists.
  C_RW     0x55764ACB  TFrozenWaterHS.ReadWrite -- persist the two new bytes.
  C_MELT   0x55764AE0  TFrozenWaterHS.MeltIce -- restore [self+0x0E] instead of
                       the hard-coded 0/0xA.
  C_HSTC   0x55764B8B  TFrozenWaterHS.TerrainChanged -- survive our own change.
  C_SHOW   0x55764BD0  TFrozenWaterHS.Show -- no ice sprite over cooled land.
  GATE_VTM 0x5579EBA0  TFreezeWater.ValidTargetMapF          } water-only test
  GATE_VTS 0x5579EBF0  TFreezeWater.ValidTargetSelectionMapF } -> jmp past it

*** BOTH GATES MOVE TOGETHER. *** ValidTargetMapF decides validity;
ValidTargetSelectionMapF decides what the cursor highlights. Patch one and the
spell is either uncastable or untargetable.

SAVE/LOAD
    ReadWrite persists +0x0C as property id 0x1E and +0x0D as 0x1F (EDX = field
    address, ECX = property id, EAX = archive, through [archive_vmt+0x3C]).
    Property ids are a PER-CLASS running counter, not a global namespace -- a
    survey of all 223 ReadWrite methods in the module shows every class numbering
    its own fields upward from 0x0A. TFrozenWaterHS's ancestors consume 0x0A..0x1D
    and its own two are next, so 0x20/0x21 are this class's next free ids. The
    table is id-indexed rather than positional, so old saves that lack them load
    fine (Zig notes / [[aow1-property-table-serialization]]).

    *** C_RW re-assembles the displaced run using EDI as the archive-vtable
    scratch, NOT EBX. Vanilla's last field does `mov ebx,[eax]`, destroying Self,
    which it gets away with only because nothing follows. Two more fields do. ***

SAFETY CHECKS ALREADY RUN AGAINST THE LIVE FILE
    * no .reloc entry falls inside any displaced run
    * no branch anywhere in CODE targets the middle of a displaced run
    * the only absolute dword pointing at a run start is 0x55764BD0 = Show's own
      VMT slot (+0xA8); calls through it land on the E9 and take the hook.

CAVES
    0x5582A200..0x5582A600 in CODE. The preceding span 0x5582A000..0x5582A200 is
    reserved by build_terror_oncepercombat.py -- highest occupied byte 0x5582A16D.
    Verified all-zero and clear of every AoWEPACK address any build script claims.
    All caves are position-independent: registers + rel32, and the one absolute
    global (AoWE.AoWHSMap @0x558FA040, needed by C_MELT) is reached through the
    call/pop delta idiom. The .dpl rebases at runtime.

RNG
    No cave draws a random number. Note ChangeTerrain already draws from the
    SYNCED generator (TAoWHSMap.Random @0x5577827C at 0x5579E8DC) and the marker's
    countdown likewise at 0x5579E96F, both correct for a synchronised TE context.
    Re-run re_tools/rng_audit.py --owners after --apply anyway; new sites must
    print ok.

MULTIPLAYER
    The ladder is a pure function of the hex's own terrain byte, and the marker's
    countdown comes from the synced generator, so every peer cools and melts the
    same hexes on the same turns.

USAGE
    python build_scripts/build_gripofwinter.py            # verify only
    python build_scripts/build_gripofwinter.py --dis      # + cave disassembly
    python build_scripts/build_gripofwinter.py --apply
    python build_scripts/build_gripofwinter.py --undo     # surgical, no backup touched
"""
import os
import struct
import subprocess
import sys

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-gripofwinter")
BASE = 0x55700C00                      # CODE: VA = file_offset + BASE

# ------------------------------------------------------------------ the ladder --
# terrain ids: 0 Water 1 Grass 2 Desert 3 Snow 4 Steppe 5 Wasteland 6 Ice
#              9 Lava  A CaveWater  C Dirt  D CaveIce
# One step per cast; Snow(3) is the floor and is not a key, so nothing cools past it.
LADDER = [(0x2, 0x4),                  # Desert -> Steppe
          (0x4, 0x1),                  # Steppe -> Grass
          (0x1, 0x3)]                  # Grass  -> Snow

ICE = (0x6, 0x0D)                      # the terrains the vanilla water arm produces

# ---------------------------------------------------------------- addresses ----
# GlobalTargetSpells.TFreezeWaterTE.ChangeTerrain @0x5579E884
COOL_HOOK   = 0x5579E89B               # movsx eax,[ebx]; test ax,ax           (6 B)
COOL_RESUME = 0x5579E8A1               #   -> the `jne` that follows
COOL_DONE   = 0x5579E8F7               #   -> the function epilogue

# GlobalTargetSpells.TFreezeWaterTE.TerrainChanged @0x5579E900
TCCLS_HOOK  = 0x5579E90E               # the new/old terrain classification    (11 B)
TC_CREATE   = 0x5579E924               #   -> FindOwnedHS / create / refresh
TC_NOTHING  = 0x5579E98A               #   -> the function epilogue
TCFIN_HOOK  = 0x5579E984               # mov al,[edi+0x18]; mov [ebx+0xd],al    (6 B)

# AoWE.TFrozenWaterHS
RW_HOOK     = 0x55764ACB               # the second ReadWrite field            (15 B)
RW_RESUME   = 0x55764ADA               #   -> pop edi; pop esi; pop ebx; ret
MELT_HOOK   = 0x55764AE0               # MeltIce prologue                       (6 B)
MELT_RESUME = 0x55764AE6               #   -> movsx eax,[eax+0x14]
HSTC_HOOK   = 0x55764B8B               # the self-destruct sequence             (9 B)
HSTC_RESUME = 0x55764B94               #   -> pop esi; pop ebx; ret
SHOW_HOOK   = 0x55764BD0               # Show prologue                          (6 B)
SHOW_RESUME = 0x55764BD6               #   -> push ebx

AOWHSMAP    = 0x558FA040               # AoWE.AoWHSMap -- holds the map OBJECT.
#   ^ MeltIce's own idiom: mov eax,[0x558FA040]; mov ebx,[eax]; call [ebx+0xD0].
#     NOT 0x558E9494, which is a pointer TO the map variable and needs one more
#     dereference. Copy the idiom of the function you are injecting into.

# GlobalTargetSpells.TFreezeWater -- the two water-only target gates
GATE_VTM    = 0x5579EBA0               # ValidTargetMapF          (15 B) -> 0x5579EBAF
GATE_VTM_TO = 0x5579EBAF
GATE_VTS    = 0x5579EBF0               # ValidTargetSelectionMapF (15 B) -> 0x5579EBFF
GATE_VTS_TO = 0x5579EBFF

# displaced runs, verbatim, for verify-before-write. None contains a `call rel32`,
# so a byte copy carries no stale displacement; the runs that ARE replayed are
# re-assembled anyway.
ORIG = {
    COOL_HOOK:  bytes.fromhex("0fbe036685c0"),
    TCCLS_HOOK: bytes.fromhex("8a46142c0674042c077571"),
    TCFIN_HOOK: bytes.fromhex("8a471888430d"),
    RW_HOOK:    bytes.fromhex("8d530db91f0000008bc68b18ff533c"),
    MELT_HOOK:  bytes.fromhex("538bd88b4304"),
    HSTC_HOOK:  bytes.fromhex("b2018bc68b08ff51fc"),
    SHOW_HOOK:  bytes.fromhex("558bec83c4f8"),
}
GATE_ORIG = {
    GATE_VTM: bytes.fromhex("0fbe7b146685ff74066683ff0a7511"),
    GATE_VTS: bytes.fromhex("0fbe7e146685ff74066683ff0a7511"),
}
GATE_TO = {GATE_VTM: GATE_VTM_TO, GATE_VTS: GATE_VTS_TO}

CAVE_BASE = 0x5582A200
CAVE_END  = 0x5582A600                 # asserted zero-or-ours across the whole span
C_COOL    = 0x5582A200
C_TCCLS   = 0x5582A260
C_TCFIN   = 0x5582A2C0
C_RW      = 0x5582A320
C_MELT    = 0x5582A3A0
C_HSTC    = 0x5582A460
C_SHOW    = 0x5582A4E0
CAVE_ORDER = [C_COOL, C_TCCLS, C_TCFIN, C_RW, C_MELT, C_HSTC, C_SHOW]
CAVE_SLOT = {va: (CAVE_ORDER + [CAVE_END])[k + 1] - va
             for k, va in enumerate(CAVE_ORDER)}

HOOK_CAVE = {COOL_HOOK: C_COOL, TCCLS_HOOK: C_TCCLS, TCFIN_HOOK: C_TCFIN,
             RW_HOOK: C_RW, MELT_HOOK: C_MELT, HSTC_HOOK: C_HSTC, SHOW_HOOK: C_SHOW}

CAVE_NAME = {
    C_COOL:  "C_COOL   (ChangeTerrain -- the cooling ladder)",
    C_TCCLS: "C_TCCLS  (TerrainChanged -- does this hex earn a marker?)",
    C_TCFIN: "C_TCFIN  (TerrainChanged -- stamp +0x0E restore / +0x0F set)",
    C_RW:    "C_RW     (ReadWrite -- persist +0x0E and +0x0F)",
    C_MELT:  "C_MELT   (MeltIce -- restore [self+0x0E] for a land marker)",
    C_HSTC:  "C_HSTC   (TerrainChanged -- survive our own further cooling)",
    C_SHOW:  "C_SHOW   (Show -- no ice sprite over cooled land)",
}


def off(va):
    return va - BASE


# ------------------------------------------------------------- mini assembler --
def _ks():
    try:
        from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    except ImportError:
        sys.exit("keystone-engine not installed:  pip install keystone-engine")
    return Ks(KS_ARCH_X86, KS_MODE_32)


def asm_layout(frags, base):
    """frags: list of (label|None, text|bytes|None). Text may use {LABEL} placeholders.
    Iterates to a fixed point so forward references settle."""
    ks = _ks()
    labels = {lab: base for lab, _ in frags if lab}
    for _ in range(12):
        va, out, seen = base, b"", {}
        for lab, item in frags:
            if lab:
                seen[lab] = va
            if item is None:
                continue
            if isinstance(item, (bytes, bytearray)):
                out += bytes(item)
                va += len(item)
                continue
            text = item.format(**{k: hex(v) for k, v in labels.items()})
            enc, _ = ks.asm(text, va)
            if enc is None:
                raise RuntimeError("keystone failed on: %s" % text)
            out += bytes(enc)
            va += len(enc)
        if seen == labels:
            return out
        labels = seen
    raise RuntimeError("cave layout did not converge")


def build_caves():
    """Return {cave_va: bytes}."""
    caves = {}

    # ---- C_COOL: the ladder ---------------------------------------------------
    # in: ebx = -> the live terrain byte (ECX at the call site), eax free.
    # Hooked AFTER the GetArmyHS gate, so an occupied hex never reaches here.
    # A hit writes through ebx and leaves; a miss replays the displaced pair.
    # Only EAX is clobbered, which the vanilla code clobbers too.
    frags = [(None, "movsx eax, byte ptr [ebx]")]
    for k, (src, dst) in enumerate(LADDER):
        nxt = "L%d" % k if k + 1 < len(LADDER) else "PASS"
        frags += [(None, "cmp al, %s" % hex(src)),
                  (None, "jne {%s}" % nxt),
                  (None, "mov byte ptr [ebx], %s" % hex(dst)),
                  (None, "jmp %s" % hex(COOL_DONE))]
        if k + 1 < len(LADDER):
            frags += [("L%d" % k, None)]
    frags += [("PASS", "test ax, ax"),          # eax already holds the terrain
              (None,   "jmp %s" % hex(COOL_RESUME))]
    caves[C_COOL] = asm_layout(frags, C_COOL)

    # ---- C_TCCLS: does this hex earn a marker? --------------------------------
    # in: esi = map field, edi = the TE, [ebp-1] = the OLD terrain (the function
    # stashed CL there at 0x5579E907). [esi+0x14] is already the NEW terrain --
    # this is the commit pass, so the byte is written before the callback runs.
    # Exits to TC_CREATE (find-or-make the marker) or TC_NOTHING (epilogue).
    # Clobbers AL/DL only; TC_CREATE reloads EAX and EDX immediately.
    frags = [
        (None, "mov al, byte ptr [esi + 0x14]"),      # new
        (None, "mov dl, byte ptr [ebp - 1]"),         # old
        (None, "cmp al, dl"),
        (None, "je {NOTHING}"),                       # nothing actually changed
        # water arm: new in {6,D} and old not in {6,D}  (vanilla's own condition)
        (None, "cmp al, %s" % hex(ICE[0])),
        (None, "je {W}"),
        (None, "cmp al, %s" % hex(ICE[1])),
        (None, "jne {LAND}"),
        ("W",  "cmp dl, %s" % hex(ICE[0])),
        (None, "je {NOTHING}"),
        (None, "cmp dl, %s" % hex(ICE[1])),
        (None, "je {NOTHING}"),
        (None, "jmp {CREATE}"),
        ("LAND", None),
    ]
    # land arm: old -> new must be exactly one legal ladder step, so a terrain
    # change made by anything else never mints one of our markers.
    for k, (src, dst) in enumerate(LADDER):
        nxt = "M%d" % k if k + 1 < len(LADDER) else "NOTHING"
        frags += [(None, "cmp dl, %s" % hex(src)),
                  (None, "jne {%s}" % nxt),
                  (None, "cmp al, %s" % hex(dst)),
                  (None, "je {CREATE}"),
                  (None, "jmp {NOTHING}")]
        if k + 1 < len(LADDER):
            frags += [("M%d" % k, None)]
    frags += [("CREATE",  "jmp %s" % hex(TC_CREATE)),
              ("NOTHING", "jmp %s" % hex(TC_NOTHING))]
    caves[C_TCCLS] = asm_layout(frags, C_TCCLS)

    # ---- C_TCFIN: stamp the two new bytes -------------------------------------
    # in: ebx = the marker (both the create and the found path converge on it),
    #     edi = the TE, esi = the field, [ebp-1] = the OLD terrain.
    # +0x0E is written ONLY when it is still 0, so a second cast on an already
    # cooled hex keeps the ORIGINAL terrain and the hex reverts all the way.
    caves[C_TCFIN] = asm_layout([
        (None,   ORIG[TCFIN_HOOK]),                       # displaced: owner tag
        (None,   "mov al, byte ptr [esi + 0x14]"),        # the terrain we set
        (None,   "cmp al, %s" % hex(ICE[0])),
        (None,   "je {ICEMARK}"),
        (None,   "cmp al, %s" % hex(ICE[1])),
        (None,   "je {ICEMARK}"),
        (None,   "mov byte ptr [ebx + 0x0f], al"),        # ... remember it
        (None,   "cmp byte ptr [ebx + 0x0e], 0"),
        (None,   "jne {DONE}"),                           # already knows the original
        (None,   "mov dl, byte ptr [ebp - 1]"),
        (None,   "mov byte ptr [ebx + 0x0e], dl"),        # first cooling: record it
        (None,   "jmp {DONE}"),
        ("ICEMARK", "mov byte ptr [ebx + 0x0e], 0"),      # a plain vanilla ice marker
        (None,   "mov byte ptr [ebx + 0x0f], 0"),
        ("DONE", "jmp %s" % hex(TC_NOTHING)),
    ], C_TCFIN)

    # ---- C_RW: persist +0x0E and +0x0F ----------------------------------------
    # in: ebx = self, esi = the archive. Re-assembled, not copied: vanilla's copy
    # of this run does `mov ebx,[eax]` and destroys Self, which is fine only
    # because nothing follows it. Use EDI (already caller-saved here, and already
    # clobbered by the field before this one) so EBX survives all three writes.
    frags = []
    for fld, pid in ((0x0d, 0x1f), (0x0e, 0x20), (0x0f, 0x21)):
        frags += [(None, "lea edx, [ebx + %s]" % hex(fld)),
                  (None, "mov ecx, %s" % hex(pid)),
                  (None, "mov eax, esi"),
                  (None, "mov edi, dword ptr [eax]"),
                  (None, "call dword ptr [edi + 0x3c]")]
    frags += [(None, "jmp %s" % hex(RW_RESUME))]
    caves[C_RW] = asm_layout(frags, C_RW)

    # ---- C_MELT: restore the saved land terrain -------------------------------
    # in: eax = self. A land marker restores [self+0x0E]; +0x0E == 0 falls through
    # to vanilla, which is also what every marker in an existing save reads.
    # The ChangeTerrainEx shape is copied verbatim from vanilla's own water arm --
    # the LAST push before the call is the new terrain (proven by the CaveIce arm
    # pushing 0xA there where the Water arm pushes 0).
    # The absolute global is reached by call/pop delta: the .dpl rebases.
    caves[C_MELT] = asm_layout([
        (None,   "cmp byte ptr [eax + 0x0e], 0"),
        (None,   "je {VANILLA}"),
        (None,   "push ebx"),
        (None,   "mov ebx, eax"),                          # ebx = self
        (None,   "mov eax, dword ptr [ebx + 4]"),          # eax = the map field
        (None,   "mov al, byte ptr [eax + 0x14]"),
        (None,   "cmp al, byte ptr [ebx + 0x0f]"),
        (None,   "jne {GONE}"),                            # not our terrain any more
        (None,   "mov eax, ebx"),
        (None,   "mov edx, dword ptr [eax]"),
        (None,   "call dword ptr [edx + 0x78]"),
        (None,   "movsx eax, al"),
        (None,   "push eax"),
        (None,   "mov eax, ebx"),
        (None,   "mov edx, dword ptr [eax]"),
        (None,   "call dword ptr [edx + 0x7c]"),
        (None,   "movsx eax, al"),
        (None,   "push eax"),
        (None,   "push 0"),
        (None,   "movzx eax, byte ptr [ebx + 0x0e]"),
        (None,   "push eax"),                              # <- the terrain to restore
        (None,   "mov eax, ebx"),
        (None,   "mov edx, dword ptr [eax]"),
        (None,   "call dword ptr [edx + 0x74]"),
        (None,   "movsx ecx, al"),
        (None,   "mov edx, ebx"),
        (None,   "call {N}"),                              # --- PIC delta ---
        ("N",    "pop eax"),
        (None,   "sub eax, {N}"),
        (None,   "mov eax, dword ptr [eax + %s]" % hex(AOWHSMAP)),
        (None,   "mov ebx, dword ptr [eax]"),
        (None,   "call dword ptr [ebx + 0xd0]"),           # THSMap.ChangeTerrainEx
        (None,   "pop ebx"),
        (None,   "ret"),
        ("GONE", "mov dl, 1"),                             # someone else took the hex
        (None,   "mov eax, ebx"),
        (None,   "mov ecx, dword ptr [eax]"),
        (None,   "call dword ptr [ecx - 4]"),              # Destroy is at VMT-0x04
        (None,   "pop ebx"),
        (None,   "ret"),
        ("VANILLA", ORIG[MELT_HOOK]),
        (None,   "jmp %s" % hex(MELT_RESUME)),
    ], C_MELT)

    # ---- C_HSTC: survive our own further cooling ------------------------------
    # in: esi = self, ebx = the notification struct ([ebx] = the new terrain).
    # Reached only where vanilla was about to self-destruct, i.e. the hex is no
    # longer Ice/CaveIce. A land marker survives when the new terrain is the next
    # rung below the one it set, and it updates +0x0F while KEEPING +0x0E -- that
    # is what makes a twice-cooled hex revert all the way to its original.
    frags = [
        (None, "cmp byte ptr [esi + 0x0e], 0"),
        (None, "je {DESTROY}"),                            # a plain ice marker
        (None, "mov al, byte ptr [ebx]"),                  # the new terrain
        (None, "cmp al, byte ptr [esi + 0x0f]"),
        (None, "je {SURVIVE}"),                            # a redundant notification
        (None, "mov dl, byte ptr [esi + 0x0f]"),
    ]
    for k, (src, dst) in enumerate(LADDER):
        nxt = "K%d" % k if k + 1 < len(LADDER) else "DESTROY"
        frags += [(None, "cmp dl, %s" % hex(src)),
                  (None, "jne {%s}" % nxt),
                  (None, "cmp al, %s" % hex(dst)),
                  (None, "je {ADVANCE}"),
                  (None, "jmp {DESTROY}")]
        if k + 1 < len(LADDER):
            frags += [("K%d" % k, None)]
    frags += [
        ("ADVANCE", "mov byte ptr [esi + 0x0f], al"),      # +0x0E deliberately kept
        ("SURVIVE", "jmp %s" % hex(HSTC_RESUME)),
        ("DESTROY", ORIG[HSTC_HOOK]),                      # indirect call: copy is safe
        (None,      "jmp %s" % hex(HSTC_RESUME)),
    ]
    caves[C_HSTC] = asm_layout(frags, C_HSTC)

    # ---- C_SHOW: no ice animation over cooled land ----------------------------
    # in: eax = self. Show is `ret 4`; the early exit happens before any frame is
    # set up, so there is nothing to unwind.
    caves[C_SHOW] = asm_layout([
        (None,   "cmp byte ptr [eax + 0x0e], 0"),
        (None,   "jne {SKIP}"),
        (None,   ORIG[SHOW_HOOK]),
        (None,   "jmp %s" % hex(SHOW_RESUME)),
        ("SKIP", "ret 4"),
    ], C_SHOW)

    for va in CAVE_ORDER:
        if len(caves[va]) > CAVE_SLOT[va]:
            raise RuntimeError("cave 0x%08X is %d bytes, its slot is %d -- move the "
                               "later caves up" % (va, len(caves[va]), CAVE_SLOT[va]))
    return caves


def build_hooks():
    """Return {site_va: (original_bytes, patched_bytes)} for the E9 hook sites."""
    out = {}
    for site, cave in HOOK_CAVE.items():
        orig = ORIG[site]
        rel = cave - (site + 5)
        patch = b"\xE9" + struct.pack("<i", rel) + b"\x90" * (len(orig) - 5)
        assert len(patch) == len(orig)
        out[site] = (orig, patch)
    return out


def build_gates():
    """Return {site_va: (original_bytes, patched_bytes)} for the in-place widenings.

    A 2-byte short jump straight to the structure check, then NOP fill. EDI is only
    the terrain scratch in both functions (pushed on entry, popped on exit), so
    skipping the whole test leaves nothing undefined."""
    out = {}
    for site, orig in GATE_ORIG.items():
        rel = GATE_TO[site] - (site + 2)
        assert -128 <= rel <= 127
        patch = b"\xEB" + struct.pack("<b", rel) + b"\x90" * (len(orig) - 2)
        assert len(patch) == len(orig)
        out[site] = (orig, patch)
    return out


# ------------------------------------------------------------------ plumbing ---
def read_dll():
    if not os.path.exists(DLL):
        sys.exit("not found: %s" % DLL)
    with open(DLL, "rb") as f:
        return bytearray(f.read())


def kill_game():
    """Standing authorization: the game/editor lock the binaries. Just kill them."""
    # ⚠ SCRATCH GUARD (2026-09-03): AOW_GAME_DIR set => we are NOT writing to the real
    # install, so we must NOT kill the user's running game. Without this, an agent doing a
    # "safe" scratch-copy round-trip still terminates the live game -- which happened, and
    # was misreported as a crash-on-expiry. Standing kill authorization applies to the real
    # install only.
    if os.environ.get("AOW_GAME_DIR"):
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match '^(AoW|AoWCompat|AoWDevEd|AoWEd)$' }"
         " | Stop-Process -Force"],
        capture_output=True)


def _rows(d, caves, hooks, gates):
    """[(label, current, patched, pristine)] for every byte-run this script owns."""
    rows = []
    for site, (orig, patch) in sorted(hooks.items()):
        rows.append(("hook 0x%08X" % site,
                     bytes(d[off(site):off(site) + len(orig)]), patch, orig))
    for site, (orig, patch) in sorted(gates.items()):
        rows.append(("gate 0x%08X" % site,
                     bytes(d[off(site):off(site) + len(orig)]), patch, orig))
    for va, blob in sorted(caves.items()):
        rows.append(("cave 0x%08X" % va,
                     bytes(d[off(va):off(va) + len(blob)]), blob, bytes(len(blob))))
    return rows


def state(d, caves, hooks, gates):
    """-> 'vanilla' | 'applied' | 'mixed'"""
    rows = _rows(d, caves, hooks, gates)
    if all(cur == pat for _, cur, pat, _ in rows):
        return "applied"
    if all(cur == pri for _, cur, _, pri in rows):
        return "vanilla"
    return "mixed"


def show(d, caves, hooks, gates):
    print("AoWEPACK.dpl  %s" % DLL)
    for label, cur, pat, pri in _rows(d, caves, hooks, gates):
        tag = "PATCHED" if cur == pat else ("clean" if cur == pri else "*** FOREIGN ***")
        body = cur.hex() if len(cur) <= 15 else "%3d bytes" % len(cur)
        print("  %-16s %-32s %s" % (label, body, tag))
    print("  state: %s" % state(d, caves, hooks, gates).upper())


def disassemble(caves):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        sys.exit("capstone not installed:  pip install capstone")
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for va in CAVE_ORDER:
        blob = caves[va]
        print("\n---- 0x%08X  %s   [%d/%d bytes]"
              % (va, CAVE_NAME[va], len(blob), CAVE_SLOT[va]))
        for i in md.disasm(bytes(blob), va):
            print("  %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))


def check_space(d, caves):
    """Every byte of the cave span must be zero or already ours."""
    span = bytes(d[off(CAVE_BASE):off(CAVE_END)])
    ours = bytearray(CAVE_END - CAVE_BASE)
    for va, blob in caves.items():
        ours[va - CAVE_BASE:va - CAVE_BASE + len(blob)] = blob
    for i, b in enumerate(span):
        if b != 0 and b != ours[i]:
            sys.exit("ABORT: cave span byte 0x%08X = 0x%02X, neither zero nor ours"
                     % (CAVE_BASE + i, b))


def do_apply(d, caves, hooks, gates):
    st = state(d, caves, hooks, gates)
    if st == "applied":
        print("already applied -- nothing to do.")
        return
    if st == "mixed":
        for label, cur, pat, pri in _rows(d, caves, hooks, gates):
            if cur not in (pat, pri):
                print("  %s is foreign: %s" % (label, cur.hex()[:64]))
        sys.exit("ABORT: partially applied / foreign bytes present. Run --undo first.")
    check_space(d, caves)

    kill_game()
    if not os.path.exists(BACKUP):
        import shutil
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("backup -> %s" % os.path.basename(BACKUP))

    for va, blob in caves.items():
        d[off(va):off(va) + len(blob)] = blob
    for site, (_, patch) in list(hooks.items()) + list(gates.items()):
        d[off(site):off(site) + len(patch)] = patch

    with open(DLL, "wb") as f:
        f.write(d)
    print("APPLIED: %d caves, %d hooks, %d gates." % (len(caves), len(hooks), len(gates)))


def do_undo(d, caves, hooks, gates):
    st = state(d, caves, hooks, gates)
    if st == "vanilla":
        print("not applied -- nothing to undo.")
        return
    for label, cur, pat, pri in _rows(d, caves, hooks, gates):
        if cur not in (pat, pri):
            sys.exit("ABORT: %s is foreign (%s)" % (label, cur.hex()[:64]))

    kill_game()
    for site, (orig, _) in list(hooks.items()) + list(gates.items()):
        d[off(site):off(site) + len(orig)] = orig
    for va, blob in caves.items():
        d[off(va):off(va) + len(blob)] = bytes(len(blob))
    with open(DLL, "wb") as f:
        f.write(d)
    print("UNDONE: hooks and gates restored, caves zeroed. No backup touched.")


def main():
    args = sys.argv[1:]
    caves, hooks, gates = build_caves(), build_hooks(), build_gates()
    d = read_dll()
    if "--dis" in args:
        disassemble(caves)
    if "--undo" in args:
        do_undo(d, caves, hooks, gates)
    elif "--apply" in args:
        do_apply(d, caves, hooks, gates)
    else:
        show(d, caves, hooks, gates)
        if "--dis" not in args:
            print("\n(dry run -- pass --apply to write, --dis to disassemble the caves)")
        return
    show(read_dll(), caves, hooks, gates)


if __name__ == "__main__":
    main()
