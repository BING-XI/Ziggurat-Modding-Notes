#!/usr/bin/env python3
r"""
AoW1 mod -- strategic-map terrain LOS blocking + fog-refcount rebuild on terrain change
            + Mantle of Gloom (v4, 2026-09-26): enemy Trail of Darkness armies thicken the fog.

Terrain 7 (Earth) and 8 (Rock) block strategic line of sight. Every area fill in
TAoWMapLevel (fog on, fog off, explore, unfog+explore) is filtered per hex: a hex is only
fogged/unfogged/explored if the hex line from the walk centre to it crosses no blocking
terrain. Both endpoints are excluded, so the first blocking hex itself stays visible.

================================================================================
PART 1 -- the LOS filter (four fill hooks + one shared cave)
================================================================================
All four fills iterate hexes with HSEngine.InitHNWalk/WalkToNextHN (ring spiral); walk
state at [ebp-0x24] in every fill:  +0x10/+0x14 current x,y ([ebp-0x14]/[ebp-0x10]),
+0x18/+0x1C centre x,y ([ebp-0x0C]/[ebp-0x08]).  ebx = TAoWMapLevel in all four.

Hooked immediately after the field pointer is computed; on "blocked" the hook jumps to
that fill's WalkToNextHN tail, so the walk still advances and ONLY the mutation is
skipped:

  fill                       hook VA      displaced bytes          resume       skip->tail
  FogArea                    0x55771F36   8A501A80FA01 (6)         0x55771F3C   0x55771F48
  UnFogArea                  0x55771FA6   8A501A84D2   (5)         0x55771FAB   0x55771FB7
  UnFogExploreArea           0x5577204D   807E1A00750B (6)         53/5E split  0x557720B6
  ExploreArea                0x55772170   0FBE7D0C8BD7 (6)         0x55772176   0x557721B6

SYMMETRY (correctness-critical): FogArea and UnFogArea stubs call the SAME los_core
entry -- fog is a refcount at [field+0x1A]; any asymmetry corrupts it permanently.
Asserted at build time, every run.

los_core (v3, permissive): greedy hex line-walk centre->target using the game's own
per-parity neighbour deltas (copied from HSEPack's walk table @0x5562E250 into this cave
-- never referenced by absolute cross-DPL address; both DPLs rebase). Grid is odd-q
offset, parity on x (WalkToNextHN: parity = [state+0x10] & 1). Cube conversion
z = y - ((x - (x&1)) >> 1); distance = (|dx|+|dy|+|dz|)/2.

The walk runs up to TWICE with opposite tie-breaking: walk A takes the FIRST side
minimising cube distance (strict <), walk B the LAST (<=). When no step ever ties the
two walks coincide; when they differ (distance-2 "through a vertex" pairs and diagonal
lines) they trace the two extreme shortest paths. The hex is visible if EITHER walk
crosses no blocking terrain -- fixes the watch-tower case where the greedy single walk
arbitrarily committed to the blocked one of two equally-short paths. Ties are detected
in cube distance, so the odd-q parity of the column never enters the tie-break.
(Known, accepted approximation: at distance >= 3 off-axis there can be MORE than two
shortest paths; a middle path that is clear while both extremes are blocked still reads
as hidden. The reference in --test measures this gap; the two-walk result is never
falsely visible.) Tie-break order is deterministic and shared by fog-on and fog-off, so
refcount symmetry is preserved. Intermediate hexes with terrain [field+0x14] in {7,8}
=> blocked. Off-map intermediates are skipped (non-blocking). Step cap 64 per walk =>
fail-open (visible). Returns ZF=1 blocked / ZF=0 clear; preserves all registers
(pushad).

⚠ ExploreArea hosts a HAND EDIT at 0x557721BE (E8 7D B4 09 00 90 -> hand cave
0x5580D640, explore = sight+2, no owning script). Our hook at 0x55772170 does not touch
it; verify/apply/undo all byte-check it and refuse to run if it is missing.

================================================================================
PART 2 -- the rebuild path (terrain changes desync fog refcounts)
================================================================================
Observers (TArmy +0x17, TPlayerStructure +0x38, TReflectingPool +0x38, TWatcherHS +0x0D
-- the complete caller set of TAbstractAoWHSMap.FogArea/UnFogArea) cache their unfog
radius and later fog-off with CURRENT terrain. If terrain changed in between, the
subtraction no longer matches the recorded addition -> permanent refcount leak.

⚠ FAILED APPROACH -- DO NOT RE-TRY: v1 repointed TAoWHSMap VMT+0x94 (@0x5570E908,
"TriggerTerrainChangedEvent") to a cave that set PENDING and called UpdateVisibility,
on the theory that the slot is a terrain-change funnel. It is NOT: slot +0x94 is the
generic map-changed/redraw notification, invoked by TAbstractAoWHSMap.MapChanged
(@0x5577251C, `call [vmt+0x94]` @0x55772538), which is called per level by
InvalidateMap (@0x557725C0) -- and UpdateVisibility itself ends with `call
InvalidateMap` (@0x5577844D). MapChangedRad (@0x55772544) is likewise called by the
Fog/UnFog/Explore AREA wrappers on every fill. Result: UpdateVisibility -> InvalidateMap
-> slot -> cave -> UpdateVisibility, unbounded recursion. Measured live 2026-08-21
(hang_stack + ESP scan of frozen AoWDevEd): repeating frames 0x55778452 (ret after
InvalidateMap) / 0x557725FA (MapChanged loop) / 0x5577253E (ret after `call [vmt+0x94]`)
/ 0x558203F1 (v1 cave_tc ret after its UpdateVisibility call). Froze the editor on map
open and the game on the first unit move (fill -> area wrapper -> MapChangedRad -> slot).
There is NO terrain-change-only notification in AoWEPACK; the byte writer is
HSEngine.TMapField.UpdateTerrainType over in HSEPack.dpl.

v2 trigger (this script): the VMT slot stays VANILLA. Instead, four vanilla
`call InvalidateMap` sites are retargeted to cave `trig`, which calls InvalidateMap,
sets PENDING and calls TAoWHSMap.UpdateVisibility (@0x55778408; eax = the map at every
site, live-verified):
  TTurnPlayerControl.NewTurn          0x55756A27   (per turn -- the standing heal)
  TTurnPlayerControl.SetSeatedPlayer  0x55756D3C   (game load / every seat change)
  TFloodControl.Flood                 0x557F15BE   (mass terrain change: immediate heal)
  TFloodControl.Restore               0x557F1851   (mass terrain change: immediate heal)
No recursion: with the slot vanilla, UpdateVisibility's own InvalidateMap call and the
fills' MapChangedRad path are vanilla-equivalent. PROTECTION TRADED AWAY: a mid-turn
terrain change (Ice Storm, raise terrain...) no longer rebuilds immediately; fog counts
can be transiently stale until the next trigger (at latest the next NewTurn), then heal
completely -- the rebuild reconstructs counts from live observers, not from history.
If visibility is locked ([map+0x1F4]) UpdateVisibility defers and re-fires at unlock;
PENDING waits for the first unlocked run.

uv_hook (@0x5577841E in UpdateVisibility, after both early-out gates): when PENDING:
  1. FLAG=1; broadcast msg 0x20020008 -- each observer's hooked UpdateUnfog entry sees
     FLAG and just zeroes its cached radius byte and returns (no fog math). TArmy's
     MsgProc gate `[map+0xA5]==0xFF -> skip UpdateUnfog` (@0x5578F92D) is bypassed while
     FLAG is set so army caches are zeroed even seatless (AI turns in hotseat).
  2. FLAG=0.
  3. ResetFog (@0x557721D4, zero callers in vanilla) on every map level -- all fog
     counts to 0. (Explored bits untouched -- explored is monotone by design.)
  4. fall through into the original UpdateVisibility broadcast: every observer sees
     cache 0, skips fog-off, re-unfogs fresh through the LOS-filtered fills.
Invariant after: count == sum of live contributions, all recorded under current terrain.

Serialization (measured): TAoWMapField.ReadWrite serializes the whole dword at
[field+0x18] (explored bits + fog count), so fog counts DO live in saves. Covered by
trig_seat: loading a game runs TTurnPlayerControl.SetSeatedPlayer, whose retargeted
call fires a full rebuild, so pre-patch saves self-heal on load.

Observer entry hooks (jmp-style; FLAG path zeroes the cache byte and rets):
  TArmy.UpdateUnfog            0x5578E228  5356578BF8      (5)  cache +0x17  resume 0x5578E22D
  TPlayerStructure.UpdateUnfog 0x55761228  5356575583C4F8  (7)  cache +0x38  resume 0x5576122F
  TReflectingPool.UpdateUnfog  0x557D50FC  5356575583C4F8  (7)  cache +0x38  resume 0x557D5103
  TWatcherHS.UpdateUnfog       0x5579FCB4  5356578BF8      (5)  cache +0x0D  resume 0x5579FCB9
  TArmy.MsgProc 0xA5-gate      0x5578F92D  80B8A5000000FF  (7)  call-style, returns flags
  UpdateVisibility             0x5577841E  8BC3E847A0FFFF  (7)  jmp-style wipe hook
  4x trig sites (above)        E8 rel32 retarget only (5) -- no displaced code, no reloc

Known gap (accepted): during a hotseat AI turn with no seated player ([map+0xA5]==0xFF)
step 4's army re-unfog is vanilla-gated off, so the spectator display goes dark until
the next seat change (0x20020006 re-unfogs from the clean zero state). Counts stay
correct throughout; single-player keeps the human seated during AI turns.

================================================================================
PART 3 -- Mantle of Gloom (v4, 2026-09-26, APPLIED, UNTESTED)
================================================================================
Every hex within GLOOM_R (6) of an army that (a) is at war with the LOCAL SEATED player
(owner's GetDiplomaticRelation(seated) == 1, the vanilla trail's own test) and (b) holds a
unit answering GetAbilityEnabled(0x1A Trail of Darkness) costs 2 sight instead of 1.
los_core charges each walk 1 per step plus 1 per gloom hex stepped onto (target included,
observer's own hex not); a terrain-clear walk whose cost exceeds the fill radius [ebp+8]
is "gloom-hidden". los_core now answers ZF=1 terrain-blocked / CF=1 gloom-hidden / neither
visible. Cost is measured along the two sight lines, never a detour around the aura.

  FOG honours gloom: stub_fog and stub_unfog skip on ZF or CF (same flags, same skip);
  stub_ue does the unfog half only when visible, the explore half whenever terrain-clear.
  EXPLORATION ignores gloom (stub_ex branches on ZF only). Reason: explored bits are per
  player and computed on every machine, while the gloom list is relative to the local
  seat -- gloomed exploration would diverge between multiplayer peers. Fog is already
  per-seat display state in vanilla, so gloom there is as safe as vanilla's own fog.

Source list (BSS, runtime only): G_CNT 0x558FAD40, G_OVF 0x558FAD44, G_INUV 0x558FAD45,
G_ENT 0x558FAD50 = 32 x {army ptr, TAoWMapLevel ptr, cube x (word), cube z (word)}, ends
0x558FAED0. SYMMETRY: the list is written ONLY inside the rebuild's zeroing pass
(stub_army, FLAG set: `qualify` the army, append), after uv_hook has cleared it and
before ResetFog + the fresh re-unfog. Between rebuilds it is constant, so every fog-off
filters through the same gloom as its fog-on. Overflow (> 32 sources) sets G_OVF and
ignores the extras. Exploration during the zeroing pass sees a partial list -- harmless,
exploration never reads gloom.

Following a moving unit: stub_army's normal path (FLAG clear) re-qualifies the army on
every TArmy.UpdateUnfog (TArmy.Update, SetPlayer, PlaceOnMap, the 0x20020006/8
broadcasts). If its source status, level or position differs from its recorded entry
(or it newly qualifies and the list has room) it sets PEND and calls UpdateVisibility --
a full rebuild per step of an enemy Trail of Darkness army. Guards: never while PEND is
already set (a locked UpdateVisibility defers to UnLockUpdateVisibility), never while
G_INUV is set -- uv_hook sets it at the top of UpdateVisibility's body and `uv_end`
(retargeted closing `call InvalidateMap` @0x5577844D) clears it, so no rebuild can start
inside another. Vanilla UpdateUnfog only compares radius with its cache, so an outer
broadcast that resumes after a nested rebuild finds every cache current and does nothing.
A destroyed army's entry lingers until the next rebuild (dangling pointer is compared,
never dereferenced). `trig_dipl` retargets SetDiplomaticRelation's `call UpdateVisibility`
(@0x5575433E) through `trig_uv` (PEND=1) so war/peace changes re-qualify everyone.

TRUE SEEING PIERCES THE GLOOM (v5, 2026-09-26, APPLIED, UNTESTED). Owner ruling: an observer
army holding a True Seeing (0x29) unit ignores the gloom surcharge out to its TRUE range, the
high nibble of [army+0x29] (= the holder's own sight; every non-holder's TrueVisionRange is 1).
Beyond that range the army's wider sight is gloomed as before; Earth/Rock still block.
  los_core: a terrain-clear walk is visible if cost <= radius OR steps <= true range.
  The fill does not know its observer, so the true range comes from a second BSS list,
  T_ENT 0x558FAC20 = 28 x {TAoWMapLevel ptr, x | y<<8 | radius<<16 | true range<<24}, T_CNT
  0x558FAC10, T_OVF 0x558FAC14, looked up by the fill's own (level, centre, radius) -- `tslook`.
  SYMMETRY: the list is written only in the rebuild's zeroing pass (stub_army rec -> `tsrec`)
  and cleared by uv_hook with the gloom list, so between rebuilds a (level, centre, radius)
  always gets the same answer and fog-off matches its fog-on. Observer = TArmy.UpdateUnfog's
  own test (own army, or owner allied (relation 2) to the seated player) -- `tsqual`.
  Following changes: stub_army's normal path calls `tscheck` when the gloom check wants no
  rebuild. While any gloom source sits on the army's level within radius + GLOOM_R (a sight
  line never leaves `radius` of its centre, so farther away the answer cannot change what is
  seen), it compares the list's answer for the army's current key with the range it holds now
  and requests a rebuild on a mismatch -- moving, gaining or losing True Seeing, radius change.
  A full list (T_OVF) suppresses the "missing entry" rebuild, so overflow cannot loop.
  Cost: a rebuild per step of a friendly True Seeing army moving within reach of the gloom.
  Cave 2 0x5584F480..0x5584F77F (EXCLUSIVE, asserted zero-or-ours): tsqual, tslook, tsrec,
  tscheck. Cave 1 grew by the lookup in los_core, the walkclear test, stub_army's tsck/tsr.

Trail of Darkness itself: ExecuteTrailOfDarkness's ring bound `cmp dword [esp+0x14], N`
@0x5578016C is TRAIL_R = 6 (vanilla 1; an unowned hand edit had made it 5 -- --undo
restores the 5).

Engine: GetPlayers 0x557544D0, GetDiplomaticRelation 0x55750A10 (1 = war, per the AI's
attack-target mask), unit VMT +0x148 GetAbilityEnabled, army +0x08 unit list (count
[+8], items [+4]), +0x10 bit0 active, +0x12 owner, +0x13/14/15 x/y/level (0xFF = off map),
+0x17 fog cache; map +0xA5 seated player, +0x140 player list, +0x10 level container.

The strategic AI reads no fog at all (no TAI* function calls VisibleForPlayer, Visible,
Watching, GetExplored or FoggedForPlayer, nor reads [field+0x1A]), so gloom -- like
Earth/Rock -- hides enemy AI units from a human, never a human's units from the AI.

.reloc: measured -- none of the displaced code runs carries a reloc entry; the VMT slot
does (kept valid: we only change the dword value, same-image VA). Re-verified on every
apply/undo.

Cave: 0x55820000..0x55820800 (CODE, file-backed, measured zero; above every claimed
zone -- vision9/marksmanship8 reserve ends at 0x55820000, statdouble marker 0x55818000).
Mutable state: BSS page slack FLAG=0x558FAA00, PENDING=0x558FAA01 (runtime-only, zero at
load, no file backing -- nothing written for them). Position-independent throughout:
call/pop delta for every global; rel32 for every call/jmp.

Backup: AoWEPACK.dpl.pre-losterrain -- taken ONLY when every hook site byte-matches the
original bytes (never minted from a patched state; the undo/re-tune paths take none).
Dry-run by default; --apply / --undo (surgical) / --verify / --dis / --test.
"""

import os
import sys
import shutil
import struct
import argparse

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-losterrain")

VA_BASE = 0x55700C00            # CODE section: file off = VA - VA_BASE
CAVE_VA = 0x55820000
CAVE_LIMIT = 0x800

# ---- tuning ----------------------------------------------------------------
BLOCKING = (7, 8)               # Earth, Rock -- the only blocking terrain ids
STEP_CAP = 64                   # line-walk safety cap; exhausted => visible
GLOOM = True                    # False: no army ever qualifies -> v3 behaviour, same hooks
GLOOM_R = 6                     # Mantle of Gloom radius around an enemy Trail of Darkness army
TRAIL_R = 6                     # Trail of Darkness un-explore radius (vanilla 1, hand edit 5)
# ----------------------------------------------------------------------------

# mutable state (BSS page slack; runtime-only, no file backing)
FLAG = 0x558FAA00               # 1 while the zero-cache broadcast runs
PEND = 0x558FAA01               # 1 = rebuild requested
# Mantle of Gloom source list -- BSS clear gap 0x558FAC04..0x558FAF1F (FAD00..FAD23 taken)
G_CNT  = 0x558FAD40             # dword: entries recorded by the last rebuild
G_OVF  = 0x558FAD44             # byte: 1 = more sources than G_MAX (extras ignored)
G_INUV = 0x558FAD45             # byte: 1 while UpdateVisibility's body runs
G_ENT  = 0x558FAD50             # G_MAX x 12 B: army ptr, level ptr, cube x (w), cube z (w)
G_MAX  = 32
G_END  = G_ENT + G_MAX * 12     # 0x558FAED0 -- must stay below 0x558FAF20
assert G_END <= 0x558FAF20
# v5 True Seeing list -- same clear gap, below the Town Quake dword at 0x558FAD00
T_CNT  = 0x558FAC10             # dword: entries recorded by the last rebuild
T_OVF  = 0x558FAC14             # byte: 1 = more True Seeing observers than T_MAX
T_ENT  = 0x558FAC20             # T_MAX x 8 B: level ptr, x | y<<8 | radius<<16 | true range<<24
T_MAX  = 28
assert T_ENT + T_MAX * 8 <= 0x558FAD00

# v5 second cave: the True Seeing helpers (the 0x800 reservation above is nearly full and
# 0x55820800 belongs to build_caster_cost.py). EXCLUSIVE, asserted zero-or-ours.
CAVE2_VA = 0x5584F480
CAVE2_LIMIT = 0x300

# engine entry points (all AoWEPACK.dpl, live-verified this session)
UPDVIS    = 0x55778408          # TAoWHSMap.UpdateVisibility
LOCKMCE   = 0x5577246C          # TAbstractAoWHSMap.LockMapChangedEvent
INITMSG   = 0x5570347C          # thunk EngineP!Engine.InitMsg
GETLVL    = 0x557020EC          # thunk HSEPack!TMapContainer.GetMapLevel
RESETFOG  = 0x557721D4          # TAoWMapLevel.ResetFog (zero callers in vanilla)
INVMAP    = 0x557725C0          # TAbstractAoWHSMap.InvalidateMap
GETPLAYERS = 0x557544D0         # TPlayerList.GetPlayers (eax=list, edx=idx -> player|nil)
GETREL    = 0x55750A10          # TPlayerDiplomaticRelations.GetDiplomaticRelation (dl=other)
MAPVAR    = 0x558FA040          # AoWE.AoWHSMap global (read via load delta)
ABIL_TOD  = 0x1A                # Trail of Darkness; unit VMT +0x148 = GetAbilityEnabled
REL_WAR   = 1                   # the relation value the vanilla trail tests
REL_ALLY  = 2                   # the relation TArmy.UpdateUnfog unfogs for (0x5578E27E)
VMT_SLOT  = 0x5570E908          # TAoWHSMap VMT +0x94 -- VANILLA in v2 (v1 repointed it)
VMT_ORIG  = bytes.fromhex("EC247755")           # -> 0x557724EC TriggerTerrainChangedEvent
LEGACY_VMT = bytes.fromhex("D0038255")          # v1 cave_tc @0x558203D0 -- migrated away

# v2 trigger sites: vanilla `call InvalidateMap` (E8 rel32) retargeted to cave `trig`.
TRIG_SITES = [
    ("trig_newturn", 0x55756A27),   # TTurnPlayerControl.NewTurn
    ("trig_seat",    0x55756D3C),   # TTurnPlayerControl.SetSeatedPlayer
    ("trig_flood",   0x557F15BE),   # TFloodControl.Flood
    ("trig_restore", 0x557F1851),   # TFloodControl.Restore
]

# v4 call retargets with their own vanilla targets: (name, site, vanilla target, cave)
CALL_SITES = [
    ("uv_end",    0x5577844D, INVMAP, "uv_end"),    # UpdateVisibility's closing call
    ("trig_dipl", 0x5575433E, UPDVIS, "trig_uv"),   # TPlayerList.SetDiplomaticRelation
]

# v4 raw byte edits: (name, va, pre-script bytes, new bytes)
# ExecuteTrailOfDarkness ring bound `cmp dword [esp+0x14], N`. Vanilla N=1; an unowned
# hand edit made it 5 before this script took the byte over. --undo restores the 5.
RAW_SITES = [
    ("trail_r", 0x5578016C, bytes.fromhex("837C241405"),
     bytes.fromhex("837C2414") + bytes([TRAIL_R])),
]

HAND_EDIT_VA = 0x557721BE
HAND_EDIT    = bytes.fromhex("E87DB4090090")    # call 0x5580D640 ; nop (sight+2 cave)

# The game's ring-walk neighbour deltas, HSEPack @0x5562E250 (dumped this session).
# parity = x & 1. Layout mirrors the engine: parity*0x40 + side*8, 8 slots per parity.
DELTAS_EVEN = [(1, 0), (0, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
DELTAS_ODD  = [(1, 1), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, 0)]

# hook sites: (name, va, original bytes, kind)
# kind: 'jmp' = jmp cave (+nop pad), 'call' = call cave (+nop pad)
SITES = [
    ("fill_fog",     0x55771F36, bytes.fromhex("8A501A80FA01"),   "jmp"),
    ("fill_unfog",   0x55771FA6, bytes.fromhex("8A501A84D2"),     "jmp"),
    ("fill_ue",      0x5577204D, bytes.fromhex("807E1A00750B"),   "jmp"),
    ("fill_ex",      0x55772170, bytes.fromhex("0FBE7D0C8BD7"),   "jmp"),
    ("army_unfog",   0x5578E228, bytes.fromhex("5356578BF8"),     "jmp"),
    ("ps_unfog",     0x55761228, bytes.fromhex("5356575583C4F8"), "jmp"),
    ("pool_unfog",   0x557D50FC, bytes.fromhex("5356575583C4F8"), "jmp"),
    ("watch_unfog",  0x5579FCB4, bytes.fromhex("5356578BF8"),     "jmp"),
    ("army_gate",    0x5578F92D, bytes.fromhex("80B8A5000000FF"), "call"),
    ("uv_hook",      0x5577841E, bytes.fromhex("8BC3E847A0FFFF"), "jmp"),
]


def off(va):
    return va - VA_BASE


def hook_bytes(kind, src, dst, length):
    op = b"\xE9" if kind == "jmp" else b"\xE8"
    b = op + struct.pack("<i", dst - (src + 5))
    return b + b"\x90" * (length - 5)


def is_ours_hook(kind, va, c, length):
    """A hook whose rel32 target lands inside THIS script's exclusive cave
    reservation (a stale layout from an earlier version of this script). Ownership
    of 0x55820000..+0x800 is exclusive -- nothing else may point there. Used only
    to recognise our own previous output for re-tune/undo; the BACKUP gate never
    accepts this (backups are minted from positively-original bytes only)."""
    if kind == "raw":
        return False
    op = 0xE9 if kind == "jmp" else 0xE8
    if len(c) != length or c[0] != op or c[5:] != b"\x90" * (length - 5):
        return False
    tgt = va + 5 + struct.unpack("<i", c[1:5])[0]
    return CAVE_VA <= tgt < CAVE_VA + CAVE_LIMIT


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    out = {}

    def align(x):
        return (x + 0xF) & ~0xF

    def asm(name, addr, src):
        # this keystone build treats ';' as a syntax error (and can hang on it) --
        # strip end-of-line comments before assembling
        src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
        b = bytes(ks.asm(src, addr)[0])
        out[name] = (addr, b)
        return addr + len(b)

    # ======== CAVE 2 (v5): True Seeing sees through the Mantle of Gloom ========
    # --- tsqual: eax = army -> eax = TAoWMapLevel (0 = not an observer for the seated
    # player), edx = x | y<<8 | radius<<16 | true range<<24. Observer = the exact test
    # TArmy.UpdateUnfog uses to unfog at all: active, on the map, seated player present,
    # owner == seated or owner's relation to seated == ally. radius / true range are the
    # nibble pair [army+0x29] -- radius is what UpdateUnfog passes to the fills.
    # Preserves ebx/esi/edi/ebp.
    a2 = CAVE2_VA
    a_tsq = a2
    pop_at = a2 + 9                 # 4 x push(1) + call(5)
    nxt2 = asm("tsqual", a2, f"""
        push ebx
        push esi
        push edi
        push ebp
        call 0x{pop_at:X}
        pop  ebp
        sub  ebp, 0x{pop_at:X}          ; ebp = load delta
        mov  ebx, eax
        test byte ptr [ebx+0x10], 1
        jz   tqno
        cmp  byte ptr [ebx+0x13], 0xFF
        je   tqno
        cmp  byte ptr [ebx+0x15], 0xFF
        je   tqno
        mov  esi, [ebp + 0x{MAPVAR:X}]
        test esi, esi
        jz   tqno
        mov  al, [esi+0xA5]             ; seated player
        cmp  al, 0xFF
        je   tqno
        cmp  al, [ebx+0x12]
        je   tqobs                        ; own army
        movsx edx, byte ptr [ebx+0x12]
        mov  eax, [esi+0x140]
        test eax, eax
        jz   tqno
        call 0x{GETPLAYERS:X}
        test eax, eax
        jz   tqno
        mov  eax, [eax+0x40]
        test eax, eax
        jz   tqno
        mov  dl, [esi+0xA5]
        call 0x{GETREL:X}
        cmp  al, {REL_ALLY}
        jne  tqno
    tqobs:
        movsx edx, byte ptr [ebx+0x15]
        mov  eax, [esi+0x10]
        call 0x{GETLVL:X}
        test eax, eax
        jz   tqno
        movzx ecx, byte ptr [ebx+0x29]  ; true range << 4 | radius
        mov  edx, ecx
        and  edx, 0x0F
        shr  ecx, 4
        shl  ecx, 8
        or   ecx, edx
        shl  ecx, 8
        mov  cl, [ebx+0x14]             ; y
        shl  ecx, 8
        mov  cl, [ebx+0x13]             ; x
        mov  edx, ecx
        jmp  tqout
    tqno:
        xor  eax, eax
        xor  edx, edx
    tqout:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """)

    # --- tslook: eax = key (x | y<<8 | radius<<16), ebx = TAoWMapLevel, edx = load delta
    # -> eax = recorded true range | 0x100 when an entry matches, else 0. Clobbers ecx/edx.
    a2 = align(nxt2)
    a_tsl = a2
    nxt2 = asm("tslook", a2, f"""
        push esi
        push edi
        mov  ecx, [edx + 0x{T_CNT:X}]
        cmp  ecx, {T_MAX}
        jbe  l0
        mov  ecx, {T_MAX}
    l0:
        lea  edx, [edx + 0x{T_ENT:X}]
    l1:
        dec  ecx
        js   lno
        cmp  [edx], ebx
        jne  l2
        mov  esi, [edx+4]
        mov  edi, esi
        and  esi, 0xFFFFFF
        cmp  esi, eax
        je   lhit
    l2:
        add  edx, 8
        jmp  l1
    lhit:
        shr  edi, 24
        lea  eax, [edi + 0x100]
        jmp  lout
    lno:
        xor  eax, eax
    lout:
        pop  edi
        pop  esi
        ret
    """)

    # --- tsrec: the rebuild's zeroing pass (FLAG set). ebx = army, ebp = load delta.
    # Records the army if it is an observer holding True Seeing (true range > 1 -- every
    # other unit's TrueVisionRange is 1). Clobbers eax/ecx/edx.
    a2 = align(nxt2)
    a_tsr = a2
    nxt2 = asm("tsrec", a2, f"""
        mov  eax, ebx
        call 0x{a_tsq:X}
        test eax, eax
        jz   rdone
        mov  ecx, edx
        shr  ecx, 24
        cmp  ecx, 1
        jbe  rdone
        mov  ecx, [ebp + 0x{T_CNT:X}]
        cmp  ecx, {T_MAX}
        jb   rstore
        mov  byte ptr [ebp + 0x{T_OVF:X}], 1
        jmp  rdone
    rstore:
        lea  ecx, [ebp + ecx*8 + 0x{T_ENT:X}]
        mov  [ecx], eax
        mov  [ecx+4], edx
        inc  dword ptr [ebp + 0x{T_CNT:X}]
    rdone:
        ret
    """)

    # --- tscheck: stub_army's normal path. ebx = army, ebp = load delta -> eax = 1 when
    # a rebuild is needed because what the list says for this army's (level, hex, radius)
    # is not what it now holds. Only consulted while some gloom source is on this level
    # within radius + GLOOM_R of the army (a sight line never leaves radius of its centre,
    # so outside that the answer cannot change what is seen). Preserves ebx/ebp.
    a2 = align(nxt2)
    a_tsc = a2
    nxt2 = asm("tscheck", a2, f"""
        cmp  dword ptr [ebp + 0x{G_CNT:X}], 0
        je   tzero                      ; no gloom anywhere
        mov  eax, ebx
        call 0x{a_tsq:X}
        test eax, eax
        jz   tzero                      ; not an observer: it fills nothing
        push ebx
        push ebp
        mov  esi, eax                   ; level
        mov  edi, edx                   ; packed
        movzx eax, dl                   ; x
        movzx ecx, dh                   ; y
        mov  edx, eax
        and  edx, 1
        mov  ebx, eax
        sub  ebx, edx
        sar  ebx, 1
        sub  ecx, ebx                   ; ecx = cube z, eax = cube x
        mov  ebx, edi
        shr  ebx, 16
        and  ebx, 0xFF
        add  ebx, {GLOOM_R}
        add  ebx, ebx                   ; 2 x (radius + GLOOM_R)
        mov  edx, [ebp + 0x{G_CNT:X}]
        cmp  edx, {G_MAX}
        jbe  r0
        mov  edx, {G_MAX}
    r0:
        push edx                        ; [esp] = sources left
        lea  ebp, [ebp + 0x{G_ENT:X}]
    rl:
        dec  dword ptr [esp]
        js   rno
        cmp  [ebp+4], esi
        jne  rn
        push eax
        push ecx
        movsx edx, word ptr [ebp+8]
        sub  edx, eax                   ; dx
        movsx eax, word ptr [ebp+10]
        sub  eax, ecx                   ; dz
        lea  ecx, [eax+edx]
        test edx, edx
        jns  ta1
        neg  edx
    ta1:
        test eax, eax
        jns  ta2
        neg  eax
    ta2:
        test ecx, ecx
        jns  ta3
        neg  ecx
    ta3:
        add  eax, edx
        add  eax, ecx                   ; 2 x hex distance
        cmp  eax, ebx
        pop  ecx
        pop  eax
        jbe  ryes
    rn:
        add  ebp, 12
        jmp  rl
    rno:
        pop  edx
        pop  ebp
        pop  ebx
    tzero:
        xor  eax, eax
        ret
    ryes:
        pop  edx
        pop  ebp                        ; load delta again
        mov  eax, edi
        and  eax, 0xFFFFFF              ; key
        mov  ebx, esi
        mov  edx, ebp
        call 0x{a_tsl:X}                ; eax = listed range | 0x100 found
        mov  ecx, edi
        shr  ecx, 24                    ; wanted range
        cmp  ecx, 1
        ja   w1
        xor  ecx, ecx                   ; no True Seeing: wants no entry
    w1:
        movzx edx, al
        cmp  ecx, edx
        je   tsame
        test ecx, ecx
        jz   tneed                      ; lost True Seeing (or moved): stale entry
        test eax, 0x100
        jnz  tneed                      ; listed with a different range
        cmp  byte ptr [ebp + 0x{T_OVF:X}], 0
        jne  tsame                      ; list full: a rebuild could not record it
    tneed:
        mov  eax, 1
        pop  ebx
        ret
    tsame:
        xor  eax, eax
        pop  ebx
        ret
    """)
    out["_end2"] = nxt2

    # ======== CAVE 1 ========
    # --- neighbour delta table: parity*0x40 + side*8 -> (dx dword, dy dword)
    a_tab = CAVE_VA
    tab = bytearray(0x80)
    for p, dl in ((0, DELTAS_EVEN), (1, DELTAS_ODD)):
        for s, (dx, dy) in enumerate(dl):
            struct.pack_into("<ii", tab, p * 0x40 + s * 8, dx, dy)
    out["table"] = (a_tab, bytes(tab))

    # --- los_core: the shared per-hex filter. Preserves every register; answers in flags:
    #   ZF=1          terrain-blocked: neither tie-break walk is free of Earth/Rock
    #   ZF=0, CF=1    gloom-hidden: a walk is terrain-clear, but every clear walk costs more
    #                 than the fill radius (1 per step, +1 more per Mantle of Gloom hex entered)
    #   ZF=0, CF=0    visible
    # Reads the fill's frame via ebp (identical layout in all four fills):
    #   [ebp-0x0C]/[ebp-0x08] centre x,y   [ebp-0x14]/[ebp-0x10] target x,y   [ebp+8] radius
    # ebx = TAoWMapLevel (from the pushad frame at [esp+0x50]).
    # Frame: [esp+0x00] load delta  +0x04/+0x08 cand x,y  +0x0C bestd  +0x10 cap
    #        +0x14 t_x  +0x18 t_z (cube)  +0x1C side  +0x20/+0x24 best x,y
    #        +0x28 mode (0 = walk A first-tie-wins, 1 = walk B last-tie-wins)
    #        +0x2C radius  +0x30 walk cost  +0x34 1 = some walk was terrain-clear
    a_los = align(a_tab + 0x80)
    pop_at = a_los + 9          # pushad(1) + sub esp,0x40(3) + call(5)
    src_los = f"""
        pushad
        sub  esp, 0x40
        call 0x{pop_at:X}
        pop  eax
        sub  eax, 0x{pop_at:X}
        mov  [esp], eax                 ; [esp+0x00] load delta
        mov  eax, [ebp-0x14]            ; target x
        mov  [esp+0x14], eax            ; t_x
        mov  ecx, eax
        and  ecx, 1
        sub  eax, ecx
        sar  eax, 1
        mov  ecx, [ebp-0x10]            ; target y
        sub  ecx, eax
        mov  [esp+0x18], ecx            ; t_z (cube)
        mov  eax, [ebp+8]
        mov  [esp+0x2C], eax            ; fill radius
        movzx eax, byte ptr [ebp+8]     ; v5: key = x | y<<8 | radius<<16 of this fill
        shl  eax, 8
        mov  al, byte ptr [ebp-0x08]
        shl  eax, 8
        mov  al, byte ptr [ebp-0x0C]
        mov  edx, [esp]
        call 0x{a_tsl:X}                ; ebx = the fill's level, untouched so far
        movzx eax, al
        mov  [esp+0x38], eax            ; True Seeing range of this observer, 0 = none
        mov  dword ptr [esp+0x34], 0    ; no terrain-clear walk yet
        mov  dword ptr [esp+0x28], 0    ; mode = walk A
    walkinit:
        mov  esi, [ebp-0x0C]            ; cur x = centre x
        mov  edi, [ebp-0x08]            ; cur y = centre y
        mov  dword ptr [esp+0x10], {STEP_CAP}
        mov  dword ptr [esp+0x30], 0    ; cost
    step:
        cmp  esi, [ebp-0x14]
        jne  notdone
        cmp  edi, [ebp-0x10]
        je   walkclear                  ; reached the target with no blocking hex
    notdone:
        dec  dword ptr [esp+0x10]
        js   walkclear                  ; cap exhausted -> fail open
        mov  dword ptr [esp+0x0C], 0x7FFFFFFF   ; bestd
        mov  dword ptr [esp+0x1C], 0            ; side
    sides:
        mov  ecx, [esp+0x1C]
        mov  eax, esi
        and  eax, 1
        shl  eax, 6
        lea  eax, [eax + ecx*8]
        add  eax, [esp]                 ; + load delta
        mov  edx, [eax + 0x{a_tab + 4:X}]   ; dy
        mov  eax, [eax + 0x{a_tab:X}]       ; dx
        add  eax, esi                   ; cand x
        add  edx, edi                   ; cand y
        mov  [esp+4], eax
        mov  [esp+8], edx
        call dist
        cmp  eax, [esp+0x0C]
        jl   take                       ; strictly better: take in both modes
        jg   nextside
        cmp  dword ptr [esp+0x28], 0    ; tie (cube distance equal)
        je   nextside                   ; walk A: first tied candidate stands
    take:
        mov  [esp+0x0C], eax            ; walk B: last tied candidate wins
        mov  eax, [esp+4]
        mov  [esp+0x20], eax            ; best x
        mov  eax, [esp+8]
        mov  [esp+0x24], eax            ; best y
    nextside:
        inc  dword ptr [esp+0x1C]
        cmp  dword ptr [esp+0x1C], 6
        jl   sides
        mov  esi, [esp+0x20]
        mov  edi, [esp+0x24]
        inc  dword ptr [esp+0x30]       ; one step of sight
        mov  ebx, [esp+0x50]            ; level (saved ebx in pushad frame)
        test esi, esi
        js   step                       ; off-map intermediate: no gloom, no terrain
        test edi, edi
        js   step
        cmp  esi, [ebx+0x0C]
        jge  step
        cmp  edi, [ebx+0x10]
        jge  step
        mov  eax, [esp]
        call gloom
        add  [esp+0x30], eax            ; a Mantle of Gloom hex costs one more
        cmp  esi, [ebp-0x14]
        jne  check
        cmp  edi, [ebp-0x10]
        je   step                       ; the target: gloom counts, terrain never blocks
    check:
        mov  eax, [ebx+0x74]
        mov  eax, [eax + esi*4]
        mov  edx, [ebx+0x78]
        add  eax, [edx + edi*4]         ; field
        mov  dl, [eax+0x14]             ; terrain
        cmp  dl, {BLOCKING[0]}
        je   walkfail
        cmp  dl, {BLOCKING[1]}
        je   walkfail
        jmp  step
    walkclear:                          ; this walk crossed no blocking terrain
        mov  dword ptr [esp+0x34], 1
        mov  eax, [esp+0x30]
        cmp  eax, [esp+0x2C]
        jle  visible
        mov  eax, {STEP_CAP}            ; v5: steps taken, gloom not charged
        sub  eax, [esp+0x10]
        cmp  eax, [esp+0x38]
        jle  visible                    ; within the True Seeing range: gloom ignored
    walkfail:                           ; blocked, or clear but too costly
        cmp  dword ptr [esp+0x28], 0
        jne  decide
        mov  dword ptr [esp+0x28], 1    ; retry with opposite tie-break
        jmp  walkinit
    decide:
        cmp  dword ptr [esp+0x34], 0
        je   blocked
        add  esp, 0x40                  ; gloom-hidden: ZF=0 CF=1
        popad
        test esp, esp
        stc
        ret
    blocked:
        add  esp, 0x40
        popad
        cmp  eax, eax                   ; ZF=1 CF=0
        ret
    visible:
        add  esp, 0x40
        popad
        test esp, esp                   ; ZF=0 CF=0 (esp never 0)
        ret
    dist:                               ; eax=x, edx=y -> eax = hexdist to target
        mov  ecx, eax                   ; (locals shifted +4 by the ret addr)
        and  ecx, 1
        mov  ebx, eax
        sub  ebx, ecx
        sar  ebx, 1
        sub  edx, ebx                   ; z
        sub  eax, [esp+0x18]            ; dx  (= [esp+4+0x14])
        sub  edx, [esp+0x1C]            ; dz  (= [esp+4+0x18])
        mov  ecx, eax
        add  ecx, edx
        neg  ecx                        ; dy = -(dx+dz)
        mov  ebx, eax
        sar  ebx, 31
        xor  eax, ebx
        sub  eax, ebx
        mov  ebx, edx
        sar  ebx, 31
        xor  edx, ebx
        sub  edx, ebx
        mov  ebx, ecx
        sar  ebx, 31
        xor  ecx, ebx
        sub  ecx, ebx
        add  eax, edx
        add  eax, ecx
        sar  eax, 1
        ret
    gloom:                              ; eax=delta esi=x edi=y ebx=level -> eax 1|0
        push ebp                        ; clobbers ecx/edx only
        push esi
        push edi
        mov  ecx, esi
        and  ecx, 1
        mov  edx, esi
        sub  edx, ecx
        sar  edx, 1
        sub  edi, edx                   ; edi = cube z, esi = cube x
        mov  ecx, [eax + 0x{G_CNT:X}]
        cmp  ecx, {G_MAX}
        jbe  gcnt
        mov  ecx, {G_MAX}
    gcnt:
        lea  ebp, [eax + 0x{G_ENT:X}]
    gloop:
        test ecx, ecx
        jz   gno
        cmp  [ebp+4], ebx               ; same map level?
        jne  gnext
        movsx eax, word ptr [ebp+8]
        movsx edx, word ptr [ebp+10]
        sub  eax, esi                   ; dx
        sub  edx, edi                   ; dz
        push ecx
        lea  ecx, [eax+edx]             ; -(dy)
        test eax, eax
        jns  ga
        neg  eax
    ga:
        test edx, edx
        jns  gb
        neg  edx
    gb:
        test ecx, ecx
        jns  gc
        neg  ecx
    gc:
        add  eax, edx
        add  eax, ecx                   ; = 2 x hex distance
        pop  ecx
        cmp  eax, {2 * GLOOM_R}
        jbe  gyes
    gnext:
        add  ebp, 12
        dec  ecx
        jmp  gloop
    gno:
        xor  eax, eax
        jmp  gout
    gyes:
        mov  eax, 1
    gout:
        pop  edi
        pop  esi
        pop  ebp
        ret
    """
    nxt = asm("los_core", a_los, src_los)

    # --- fill stubs (jmp'd into; jmp back). All four call the SAME los_core.
    # Fog counts (FogArea, UnFogArea, UnFogExploreArea's unfog) honour gloom; EXPLORATION
    # never does (ExploreArea, UnFogExploreArea's explore half) -- explored bits are per
    # player on every machine, and the gloom list is relative to the local seated player.
    a = align(nxt)
    nxt = asm("stub_fog", a, f"""
        call 0x{a_los:X}
        jz   skip
        jc   skip
        mov  dl, [eax+0x1A]
        cmp  dl, 1
        jmp  0x55771F3C
    skip:
        jmp  0x55771F48
    """)
    a = align(nxt)
    nxt = asm("stub_unfog", a, f"""
        call 0x{a_los:X}
        jz   skip
        jc   skip
        mov  dl, [eax+0x1A]
        test dl, dl
        jmp  0x55771FAB
    skip:
        jmp  0x55771FB7
    """)
    a = align(nxt)
    nxt = asm("stub_ue", a, f"""
        call 0x{a_los:X}
        jz   skip
        jc   exonly
        cmp  byte ptr [esi+0x1A], 0
        jne  taken
        jmp  0x55772053
    taken:
        jmp  0x5577205E
    exonly:
        jmp  0x55772069
    skip:
        jmp  0x557720B6
    """)
    a = align(nxt)
    nxt = asm("stub_ex", a, f"""
        call 0x{a_los:X}
        jz   skip
        movsx edi, byte ptr [ebp+0x0C]
        mov  edx, edi
        jmp  0x55772176
    skip:
        jmp  0x557721B6
    """)

    # --- observer UpdateUnfog entry stubs: FLAG set -> zero cache byte, ret.
    def unfog_stub(name, addr, cache_off, displaced, resume):
        pop_at = addr + 6       # push ecx(1) + call(5)
        return asm(name, addr, f"""
        push ecx
        call 0x{pop_at:X}
        pop  ecx
        sub  ecx, 0x{pop_at:X}
        cmp  byte ptr [ecx + 0x{FLAG:X}], 0
        pop  ecx
        jne  fz
        {displaced}
        jmp  0x{resume:X}
    fz:
        mov  byte ptr [eax + 0x{cache_off:X}], 0
        ret
    """)

    d5 = "push ebx\npush esi\npush edi\nmov edi, eax"
    d7 = "push ebx\npush esi\npush edi\npush ebp\nadd esp, -8"
    # --- qualify: is this army a Mantle of Gloom source for the local seated player?
    # eax = army -> eax = TAoWMapLevel (0 = not a source), edx = cube x | cube z << 16.
    # Source = active, on the map, owner != seated, owner's relation to seated == war,
    # and some unit answers GetAbilityEnabled(Trail of Darkness) -- the vanilla trail's
    # own query (TAbstractUnit.MovedTo @0x55780507). Preserves ebx/esi/edi/ebp.
    a = align(nxt)
    a_qual = a
    pop_at = a + 9 + (0 if GLOOM else 5)    # [off-switch 5] + 4 x push(1) + call(5)
    nxt = asm("qualify", a, ("" if GLOOM else """
        xor  eax, eax
        xor  edx, edx
        ret
    """) + f"""
        push ebx
        push esi
        push edi
        push ebp
        call 0x{pop_at:X}
        pop  ebp
        sub  ebp, 0x{pop_at:X}          ; ebp = load delta
        mov  ebx, eax                   ; army
        test byte ptr [ebx+0x10], 1
        jz   qno
        cmp  byte ptr [ebx+0x13], 0xFF
        je   qno
        cmp  byte ptr [ebx+0x15], 0xFF
        je   qno
        mov  esi, [ebp + 0x{MAPVAR:X}]  ; map
        test esi, esi
        jz   qno
        mov  al, [esi+0xA5]             ; seated player
        cmp  al, 0xFF
        je   qno
        cmp  al, [ebx+0x12]
        je   qno
        movsx edx, byte ptr [ebx+0x12]
        mov  eax, [esi+0x140]
        test eax, eax
        jz   qno
        call 0x{GETPLAYERS:X}
        test eax, eax
        jz   qno
        mov  eax, [eax+0x40]            ; the owner's diplomatic relations
        test eax, eax
        jz   qno
        mov  dl, [esi+0xA5]
        call 0x{GETREL:X}
        cmp  al, {REL_WAR}
        jne  qno
        mov  eax, [ebx+8]               ; unit list
        test eax, eax
        jz   qno
        mov  edi, [eax+8]               ; count
    qunit:
        dec  edi
        js   qno
        mov  eax, [ebx+8]
        mov  eax, [eax+4]
        mov  eax, [eax + edi*4]
        test eax, eax
        jz   qunit
        mov  edx, {ABIL_TOD}
        mov  ecx, [eax]
        call dword ptr [ecx+0x148]      ; GetAbilityEnabled
        test al, al
        jz   qunit
        movsx edx, byte ptr [ebx+0x15]
        mov  eax, [esi+0x10]
        call 0x{GETLVL:X}
        test eax, eax
        jz   qno
        movsx edx, byte ptr [ebx+0x14]  ; y
        movsx ecx, byte ptr [ebx+0x13]  ; x
        mov  edi, ecx
        and  edi, 1
        mov  esi, ecx
        sub  esi, edi
        sar  esi, 1
        sub  edx, esi                   ; cube z
        shl  edx, 16
        and  ecx, 0xFFFF
        or   edx, ecx
        jmp  qout
    qno:
        xor  eax, eax
        xor  edx, edx
    qout:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """)

    # --- stub_army: TArmy.UpdateUnfog entry (eax = army).
    #   FLAG (rebuild zeroing pass): record the army if it is a source, zero cache, ret.
    #   otherwise: if the army's source status or position no longer matches what the
    #   last rebuild recorded, request a rebuild (PEND) and run UpdateVisibility -- that
    #   is what makes the aura follow a moving unit. Never from inside UpdateVisibility
    #   (G_INUV) or while a rebuild is already pending.
    a = align(nxt)
    pop_at = a + 6              # pushad(1) + call(5)
    nxt = asm("stub_army", a, f"""
        pushad
        call 0x{pop_at:X}
        pop  ebp
        sub  ebp, 0x{pop_at:X}          ; ebp = load delta
        mov  ebx, eax                   ; army
        cmp  byte ptr [ebp + 0x{FLAG:X}], 0
        jne  rec
        cmp  byte ptr [ebp + 0x{PEND:X}], 0
        jne  go
        cmp  byte ptr [ebp + 0x{G_INUV:X}], 0
        jne  go
        call 0x{a_qual:X}
        mov  esi, eax                   ; level | 0
        mov  edi, edx                   ; packed cube
        mov  ecx, [ebp + 0x{G_CNT:X}]
        cmp  ecx, {G_MAX}
        jbe  fcnt
        mov  ecx, {G_MAX}
    fcnt:
        lea  edx, [ebp + 0x{G_ENT:X}]
    find:
        test ecx, ecx
        jz   notrec
        cmp  [edx], ebx
        je   isrec
        add  edx, 12
        dec  ecx
        jmp  find
    isrec:
        test esi, esi
        jz   need                       ; recorded, no longer a source
        cmp  [edx+4], esi
        jne  need                       ; changed level
        cmp  [edx+8], edi
        jne  need                       ; moved
        jmp  tsck
    notrec:
        test esi, esi
        jz   tsck                       ; not a source, never was
        cmp  byte ptr [ebp + 0x{G_OVF:X}], 0
        jne  tsck                       ; list full: cannot record it anyway
    need:
        mov  byte ptr [ebp + 0x{PEND:X}], 1
        mov  eax, [ebp + 0x{MAPVAR:X}]
        call 0x{UPDVIS:X}
        jmp  go
    tsck:                               ; v5: is its True Seeing entry still right?
        call 0x{a_tsc:X}
        test eax, eax
        jnz  need
    go:
        popad
        push ebx
        push esi
        push edi
        mov  edi, eax
        jmp  0x5578E22D
    rec:
        call 0x{a_qual:X}
        test eax, eax
        jz   tsr
        mov  ecx, [ebp + 0x{G_CNT:X}]
        cmp  ecx, {G_MAX}
        jb   store
        mov  byte ptr [ebp + 0x{G_OVF:X}], 1
        jmp  tsr
    store:
        lea  ecx, [ecx + ecx*2]
        lea  ecx, [ebp + ecx*4 + 0x{G_ENT:X}]
        mov  [ecx], ebx
        mov  [ecx+4], eax
        mov  [ecx+8], edx
        inc  dword ptr [ebp + 0x{G_CNT:X}]
    tsr:
        call 0x{a_tsr:X}                ; v5: record a True Seeing observer
    zero:
        popad
        mov  byte ptr [eax + 0x17], 0
        ret
    """)
    a = align(nxt); nxt = unfog_stub("stub_ps",    a, 0x38, d7, 0x5576122F)
    a = align(nxt); nxt = unfog_stub("stub_pool",  a, 0x38, d7, 0x557D5103)
    a = align(nxt); nxt = unfog_stub("stub_watch", a, 0x0D, d5, 0x5579FCB9)

    # --- TArmy.MsgProc 0xA5-gate (call-style; returns comparison flags).
    a = align(nxt)
    pop_at = a + 6
    nxt = asm("stub_gate", a, f"""
        push ecx
        call 0x{pop_at:X}
        pop  ecx
        sub  ecx, 0x{pop_at:X}
        cmp  byte ptr [ecx + 0x{FLAG:X}], 0
        pop  ecx
        jne  fz
        cmp  byte ptr [eax + 0xA5], 0xFF
        ret
    fz:
        test esp, esp                   ; ZF=0 -> the je falls through -> UpdateUnfog runs
        ret
    """)

    # --- uv_hook: the wipe, run inside UpdateVisibility when PENDING.
    a = align(nxt)
    pop_at = a + 5
    nxt = asm("uv_hook", a, f"""
        call 0x{pop_at:X}
        pop  eax
        sub  eax, 0x{pop_at:X}
        mov  byte ptr [eax + 0x{G_INUV:X}], 1   ; cleared by uv_end at the body's end
        cmp  byte ptr [eax + 0x{PEND:X}], 0
        jne  wipe
    orig:
        mov  eax, ebx
        call 0x{LOCKMCE:X}
        jmp  0x55778425
    wipe:
        mov  byte ptr [eax + 0x{PEND:X}], 0
        mov  dword ptr [eax + 0x{G_CNT:X}], 0   ; the zeroing pass re-records sources
        mov  byte ptr [eax + 0x{G_OVF:X}], 0
        mov  dword ptr [eax + 0x{T_CNT:X}], 0   ; v5: True Seeing list re-recorded too
        mov  byte ptr [eax + 0x{T_OVF:X}], 0
        mov  byte ptr [eax + 0x{FLAG:X}], 1
        push eax                        ; save load delta
        sub  esp, 0x30
        mov  eax, esp
        mov  ecx, ebx
        mov  edx, 0x20020008
        call 0x{INITMSG:X}
        mov  edx, esp
        mov  ecx, ebx
        mov  eax, ebx
        mov  esi, [eax]
        call dword ptr [esi + 0x68]     ; zero-cache broadcast (FLAG short-circuits)
        add  esp, 0x30
        pop  eax
        mov  byte ptr [eax + 0x{FLAG:X}], 0
        xor  esi, esi
    lvl:
        mov  eax, [ebx + 0x10]
        test eax, eax
        jz   orig
        cmp  esi, [eax + 0x14]
        jge  orig                       ; done -> continue original (fresh broadcast)
        mov  edx, esi
        call 0x{GETLVL:X}
        test eax, eax
        jz   nxt
        call 0x{RESETFOG:X}
    nxt:
        inc  esi
        jmp  lvl
    """)

    # --- trig: shared target of the four retargeted `call InvalidateMap` sites.
    # eax = the map at every site (live-verified). InvalidateMap first (the vanilla
    # behaviour the sites paid for), then PENDING=1 and one UpdateVisibility -- whose
    # uv_hook consumes PENDING. No recursion: the VMT slot is vanilla in v2.
    a = align(nxt)
    pop_at = a + 11             # push eax(1) + call INVMAP(5) + call $+5(5)
    nxt = asm("trig", a, f"""
        push eax                        ; save the map
        call 0x{INVMAP:X}
        call 0x{pop_at:X}
        pop  eax
        sub  eax, 0x{pop_at:X}
        mov  byte ptr [eax + 0x{PEND:X}], 1
        pop  eax                        ; the map
        call 0x{UPDVIS:X}
        ret
    """)

    # --- uv_end: UpdateVisibility's closing `call InvalidateMap` (@0x5577844D), retargeted.
    # Reached by both the wipe and the plain path; clears G_INUV. eax = the map.
    a = align(nxt)
    pop_at = a + 6              # push eax(1) + call(5)
    nxt = asm("uv_end", a, f"""
        push eax
        call 0x{pop_at:X}
        pop  eax
        sub  eax, 0x{pop_at:X}
        mov  byte ptr [eax + 0x{G_INUV:X}], 0
        pop  eax
        jmp  0x{INVMAP:X}
    """)

    # --- trig_uv: TPlayerList.SetDiplomaticRelation's `call UpdateVisibility`, retargeted:
    # a change of war/peace changes who is a gloom source, so ask for a rebuild.
    a = align(nxt)
    pop_at = a + 6
    nxt = asm("trig_uv", a, f"""
        push eax
        call 0x{pop_at:X}
        pop  eax
        sub  eax, 0x{pop_at:X}
        mov  byte ptr [eax + 0x{PEND:X}], 1
        pop  eax
        jmp  0x{UPDVIS:X}
    """)

    out["_end"] = nxt

    # SYMMETRY ASSERTION: fog and unfog filter through one byte-identical code path.
    for k in ("stub_fog", "stub_unfog", "stub_ue", "stub_ex"):
        va, b = out[k]
        assert b[0] == 0xE8, k
        tgt = va + 5 + struct.unpack("<i", b[1:5])[0]
        assert tgt == a_los, f"{k} does not call the shared los_core"
    # ...and fog-on and fog-off both skip on ZF (jz) and then on CF (jc).
    for k in ("stub_fog", "stub_unfog"):
        b = out[k][1]
        assert b[5] == 0x74 and b[7] == 0x72, f"{k}: expected jz rel8 ; jc rel8 after the call"
    return out


CAVE_ORDER = ("table", "los_core", "stub_fog", "stub_unfog", "stub_ue", "stub_ex",
              "qualify", "stub_army", "stub_ps", "stub_pool", "stub_watch", "stub_gate",
              "uv_hook", "trig", "uv_end", "trig_uv")
CAVE2_ORDER = ("tsqual", "tslook", "tsrec", "tscheck")

STUB_FOR_SITE = {
    "fill_fog": "stub_fog", "fill_unfog": "stub_unfog", "fill_ue": "stub_ue",
    "fill_ex": "stub_ex", "army_unfog": "stub_army", "ps_unfog": "stub_ps",
    "pool_unfog": "stub_pool", "watch_unfog": "stub_watch",
    "army_gate": "stub_gate", "uv_hook": "uv_hook",
    "trig_newturn": "trig", "trig_seat": "trig",
    "trig_flood": "trig", "trig_restore": "trig",
}


def reloc_check(data):
    """Assert no displaced code run carries a reloc entry (VMT slot is data: allowed)."""
    # section table walk (PE headers)
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe_off + 6)[0]
    opt = struct.unpack_from("<H", data, pe_off + 20)[0]
    sec0 = pe_off + 24 + opt
    reloc = None
    for i in range(nsec):
        s = sec0 + i * 40
        name = data[s:s + 8].rstrip(b"\0").decode()
        vsize, vaddr, sraw, praw = struct.unpack_from("<IIII", data, s + 8)
        if name == ".reloc":
            reloc = (vaddr, vsize, praw, sraw)
    assert reloc, "no .reloc section?"
    vaddr, vsize, praw, sraw = reloc
    rd = data[praw:praw + vsize]
    ranges = [(va, va + len(ob)) for _, va, ob, _ in SITES]
    ranges += [(va, va + 5) for _, va in TRIG_SITES]
    ranges += [(va, va + 5) for _, va, _, _ in CALL_SITES]
    ranges += [(va, va + len(ob)) for _, va, ob, _ in RAW_SITES]
    ranges.append((CAVE_VA, CAVE_VA + CAVE_LIMIT))
    ranges.append((CAVE2_VA, CAVE2_VA + CAVE2_LIMIT))
    base = 0x55700000
    i = 0
    while i + 8 <= len(rd):
        page, size = struct.unpack_from("<II", rd, i)
        if size < 8:
            break
        for j in range(i + 8, min(i + size, len(rd)), 2):
            e = struct.unpack_from("<H", rd, j)[0]
            if e >> 12 == 3:
                va = base + page + (e & 0xFFF)
                for lo, hi in ranges:
                    if lo <= va < hi:
                        sys.exit("ABORT: reloc entry at 0x%08X inside displaced/cave "
                                 "range 0x%08X..0x%08X" % (va, lo, hi))
        i += size
    # the VMT slot must STILL carry its reloc (we rely on it for rebasing)
    # cheap positive check: it was measured present; re-find it
    found = False
    i = 0
    while i + 8 <= len(rd):
        page, size = struct.unpack_from("<II", rd, i)
        if size < 8:
            break
        if base + page <= VMT_SLOT < base + page + 0x1000:
            for j in range(i + 8, min(i + size, len(rd)), 2):
                e = struct.unpack_from("<H", rd, j)[0]
                if e >> 12 == 3 and base + page + (e & 0xFFF) == VMT_SLOT:
                    found = True
        i += size
    if not found:
        sys.exit("ABORT: VMT slot 0x%08X has lost its .reloc entry" % VMT_SLOT)


# ============================================================================
# --test: pure-Python model vs an independent cube-space reference
# ============================================================================
def _to_cube(x, y):
    return x, y - ((x - (x & 1)) >> 1)


def _dist(a, b):
    ax, az = _to_cube(*a)
    bx, bz = _to_cube(*b)
    dx, dz = ax - bx, az - bz
    dy = -dx - dz
    return (abs(dx) + abs(dy) + abs(dz)) // 2


def model_walk(centre, target, cap=STEP_CAP, tie_last=False):
    """Mirror of the cave's greedy walk. Yields intermediate hexes (both endpoints
    excluded). tie_last=False is walk A (first tied side wins), True is walk B
    (last tied side wins) -- ties compared in cube distance."""
    cur = centre
    path = []
    while cur != target:
        cap -= 1
        if cap < 0:
            return path
        best, bestd = None, 1 << 31
        deltas = DELTAS_ODD if cur[0] & 1 else DELTAS_EVEN
        for dx, dy in deltas:
            cand = (cur[0] + dx, cur[1] + dy)
            d = _dist(cand, target)
            if d < bestd or (tie_last and d == bestd):
                best, bestd = cand, d
        cur = best
        if cur != target:
            path.append(cur)
    return path


CUBE_DIRS = [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)]  # side order, cube space


def ref_walk(centre, target, cap=STEP_CAP, tie_last=False):
    """Independent reference: same greedy in pure cube coordinates."""
    cur = _to_cube(*centre)
    tgt = _to_cube(*target)

    def cd(a, b):
        dx, dz = a[0] - b[0], a[1] - b[1]
        return (abs(dx) + abs(dz) + abs(-dx - dz)) // 2

    def to_off(c):
        x, z = c
        return x, z + ((x - (x & 1)) >> 1)

    path = []
    while cur != tgt:
        cap -= 1
        if cap < 0:
            return path
        best, bestd = None, 1 << 31
        for dx, dz in CUBE_DIRS:
            cand = (cur[0] + dx, cur[1] + dz)
            d = cd(cand, tgt)
            if d < bestd or (tie_last and d == bestd):
                best, bestd = cand, d
        cur = best
        if cur != tgt:
            path.append(to_off(cur))
    return path


def model_visible(terrain, centre, target):
    """The cave's rule: visible if EITHER tie-break walk is clear."""
    for tie_last in (False, True):
        if all(terrain.get(h) not in BLOCKING
               for h in model_walk(centre, target, tie_last=tie_last)):
            return True
    return False


def model_classify(terrain, sources, centre, target, radius, t_range=0):
    """Mirror of los_core v5: 'blocked' (ZF), 'gloom' (CF) or 'visible'. A walk costs 1 per
    step plus 1 per step onto a hex within GLOOM_R of any source (the target included);
    visible if some terrain-clear walk costs <= radius, or takes <= t_range steps (the
    observer's True Seeing range, 0 = none)."""
    def gloomy(h):
        return any(_dist(h, s) <= GLOOM_R for s in sources)
    any_clear = False
    for tie_last in (False, True):
        inter = model_walk(centre, target, tie_last=tie_last)
        if any(terrain.get(h) in BLOCKING for h in inter):
            continue
        any_clear = True
        steps = inter + ([target] if target != centre else [])
        cost = len(steps) + sum(1 for h in steps if gloomy(h))
        if cost <= radius or len(steps) <= t_range:
            return "visible"
    return "gloom" if any_clear else "blocked"


def ref_visible(terrain, centre, target):
    """Genuine 'exists ANY clear shortest hex path' check: layered BFS constrained
    to hexes h with dist(c,h) + dist(h,t) == dist(c,t); intermediates only (both
    endpoints excluded, so a blocking endpoint stays visible)."""
    D = _dist(centre, target)
    if D <= 1:
        return True
    frontier = {centre}
    for layer in range(1, D):
        nxt = set()
        for cur in frontier:
            deltas = DELTAS_ODD if cur[0] & 1 else DELTAS_EVEN
            for dx, dy in deltas:
                n = (cur[0] + dx, cur[1] + dy)
                if (_dist(centre, n) == layer and _dist(n, target) == D - layer
                        and terrain.get(n) not in BLOCKING):
                    nxt.add(n)
        frontier = nxt
        if not frontier:
            return False
    return True


def run_test():
    from collections import deque
    fails = 0

    # 1. cube distance == BFS shortest path over the game's own delta tables
    for centre in ((20, 20), (21, 20), (20, 21), (21, 21)):
        dist = {centre: 0}
        q = deque([centre])
        while q:
            cur = q.popleft()
            if dist[cur] >= 13:
                continue
            deltas = DELTAS_ODD if cur[0] & 1 else DELTAS_EVEN
            for dx, dy in deltas:
                n = (cur[0] + dx, cur[1] + dy)
                if n not in dist:
                    dist[n] = dist[cur] + 1
                    q.append(n)
        for h, d in dist.items():
            if _dist(centre, h) != d:
                print("  FAIL dist(%s,%s): cube=%d bfs=%d" % (centre, h, _dist(centre, h), d))
                fails += 1
    print("  [1] cube distance == BFS over game deltas (4 parities, r<=13): %s"
          % ("ok" if not fails else "FAIL"))

    # 2. both greedy walks: length == distance, every intermediate on a shortest
    #    path; each matches the independent cube-space reference for its tie mode
    n2 = 0
    for centre in ((20, 20), (21, 21)):
        for tx in range(centre[0] - 12, centre[0] + 13):
            for ty in range(centre[1] - 12, centre[1] + 13):
                t = (tx, ty)
                D = _dist(centre, t)
                if D > 12:
                    continue
                for tie_last in (False, True):
                    p = model_walk(centre, t, tie_last=tie_last)
                    r = ref_walk(centre, t, tie_last=tie_last)
                    if p != r:
                        print("  FAIL walk mismatch (tie_last=%s) %s->%s\n"
                              "    model %s\n    ref   %s" % (tie_last, centre, t, p, r))
                        fails += 1
                    if t != centre and len(p) != D - 1:
                        print("  FAIL walk length (tie_last=%s) %s->%s: %d hexes, dist %d"
                              % (tie_last, centre, t, len(p), D))
                        fails += 1
                    for i, h in enumerate(p):
                        if _dist(centre, h) != i + 1 or _dist(h, t) != D - i - 1:
                            print("  FAIL off-shortest-path hex %s in (tie_last=%s) %s->%s"
                                  % (h, tie_last, centre, t))
                            fails += 1
                n2 += 1
    print("  [2] both tie-break walks == cube-space reference, shortest-path valid "
          "(%d lines x 2): %s" % (n2, "ok" if not fails else "FAIL"))

    # 3. blocking semantics on a synthetic grid: wall of Earth at x=25
    terrain = {}
    for y in range(64):
        terrain[(25, y)] = 7
    c = (20, 20)
    checks = [
        ((25, 20), True,  "first blocking hex itself visible (endpoint excluded)"),
        ((26, 20), False, "hex immediately behind the wall hidden"),
        ((30, 20), False, "hex far behind the wall hidden"),
        ((24, 20), True,  "hex in front of the wall visible"),
        ((20, 28), True,  "hex on a clear line visible"),
    ]
    for t, want, why in checks:
        got = model_visible(terrain, c, t)
        ok = got == want
        if not ok:
            fails += 1
        print("  [3] %-52s %s" % (why, "ok" if ok else "FAIL (got %s)" % got))
    # Rock blocks too; grass does not
    rock = {(22, y): 8 for y in range(64)}
    if model_visible(rock, c, (24, 20)):
        fails += 1
        print("  [3] rock wall FAILED to block")
    else:
        print("  [3] terrain 8 (Rock) blocks: ok")
    if not model_visible({(22, y): 3 for y in range(64)}, c, (24, 20)):
        fails += 1
        print("  [3] non-blocking terrain wrongly blocked")
    else:
        print("  [3] non-blocking terrain stays transparent: ok")

    # 4. the user's watch-tower fixture: target 2 hexes east ("straight through a
    #    vertex" -- exactly two shortest paths, one intermediate each). Blocking
    #    either single intermediate must leave the target visible; blocking both
    #    hides it. Both column parities (odd-q deltas differ per parity).
    for centre in ((20, 20), (21, 20)):
        target = (centre[0] + 2, centre[1])
        deltas_c = DELTAS_ODD if centre[0] & 1 else DELTAS_EVEN
        deltas_t = DELTAS_ODD if target[0] & 1 else DELTAS_EVEN
        nc = {(centre[0] + dx, centre[1] + dy) for dx, dy in deltas_c}
        nt = {(target[0] + dx, target[1] + dy) for dx, dy in deltas_t}
        inter = sorted(nc & nt)
        if len(inter) != 2:
            print("  FAIL fixture %s->%s: expected 2 common neighbours, got %s"
                  % (centre, target, inter))
            fails += 1
            continue
        wa = model_walk(centre, target, tie_last=False)
        wb = model_walk(centre, target, tie_last=True)
        if wa == wb:
            print("  FAIL fixture %s->%s: the two walks did not diverge (%s)"
                  % (centre, target, wa))
            fails += 1
        for blocked in inter:
            for tid in BLOCKING:
                terr = {blocked: tid}
                if not model_visible(terr, centre, target):
                    print("  FAIL fixture %s->%s: hidden with only %s blocked (terrain %d)"
                          % (centre, target, blocked, tid))
                    fails += 1
                if not ref_visible(terr, centre, target):
                    print("  FAIL fixture reference disagrees (single block %s)" % (blocked,))
                    fails += 1
        both = {h: 7 for h in inter}
        if model_visible(both, centre, target):
            print("  FAIL fixture %s->%s: visible with both intermediates blocked"
                  % (centre, target))
            fails += 1
        if ref_visible(both, centre, target):
            print("  FAIL fixture reference: visible with both intermediates blocked")
            fails += 1
        print("  [4] watch-tower fixture, centre %s (parity %d), intermediates %s: %s"
              % (centre, centre[0] & 1, inter, "ok" if not fails else "see FAILs"))

    # 5. random grids: two-walk model vs the genuine any-shortest-path reference.
    #    Soundness is absolute (model never visible where no clear path exists);
    #    at dist <= 2 the two walks cover EVERY shortest path, so exact equality
    #    is required there. At dist >= 3 off-axis the reference may find a middle
    #    path the two extreme walks miss -- measured and reported, not a failure.
    import random
    rng = random.Random(0xA011)
    n5 = gap = 0
    for trial in range(120):
        centre = (20 + rng.randrange(2), 20 + rng.randrange(2))
        terrain = {}
        for x in range(centre[0] - 9, centre[0] + 10):
            for y in range(centre[1] - 9, centre[1] + 10):
                if (x, y) != centre and rng.random() < 0.22:
                    terrain[(x, y)] = rng.choice(BLOCKING)
        for tx in range(centre[0] - 7, centre[0] + 8):
            for ty in range(centre[1] - 7, centre[1] + 8):
                t = (tx, ty)
                D = _dist(centre, t)
                if D > 7:
                    continue
                m = model_visible(terrain, centre, t)
                r = ref_visible(terrain, centre, t)
                if m and not r:
                    print("  FAIL soundness: model visible, no clear shortest path "
                          "%s->%s" % (centre, t))
                    fails += 1
                if D <= 2 and m != r:
                    print("  FAIL dist<=2 equality: %s->%s model=%s ref=%s"
                          % (centre, t, m, r))
                    fails += 1
                if r and not m:
                    gap += 1
                n5 += 1
    print("  [5] random grids (%d pairs): soundness + dist<=2 equality ok; "
          "accepted permissiveness gap at dist>=3: %d pair(s)" % (n5, gap)
          if not fails else "  [5] random grids: FAIL (see above)")

    # 7. Mantle of Gloom: each hex within GLOOM_R of a source costs 2 sight instead of 1.
    c = (20, 20)
    g_checks = [
        # (sources, target, radius, want, why)
        ([], (28, 20), 8, "visible", "no sources: distance 8 at radius 8 is visible"),
        ([(22, 20)], (22, 20), 4, "visible", "source 2 away, radius 4: cost 4 -> visible"),
        ([(24, 20)], (24, 20), 4, "gloom", "source 4 away, radius 4: cost 8 -> hidden"),
        ([(24, 20)], (24, 20), 8, "visible", "source 4 away, radius 8: cost 8 -> visible"),
        ([(40, 20)], (28, 20), 8, "visible", "aura 12+ away from the line: untouched"),
        ([(34, 20)], (28, 20), 8, "gloom", "line enters the aura at step 8: cost 9 > 8"),
        ([(34, 20)], (28, 20), 9, "visible", "same line at radius 9: cost 9 -> visible"),
    ]
    for srcs, t, r, want, why in g_checks:
        got = model_classify({}, srcs, c, t, r)
        ok = got == want
        if not ok:
            fails += 1
        print("  [7] %-58s %s" % (why, "ok" if ok else "FAIL (got %s)" % got))
    # own hex always visible, even standing in the aura; terrain beats gloom
    if model_classify({}, [c], c, c, 0) != "visible":
        fails += 1
        print("  [7] FAIL: observer's own hex hidden")
    wall = {(22, y): 7 for y in range(64)}
    if model_classify(wall, [(24, 20)], c, (24, 20), 20) != "blocked":
        fails += 1
        print("  [7] FAIL: terrain block reported as gloom")
    # no sources => gloom never appears and visible == the v3 terrain rule
    rng = random.Random(0x6100)
    for trial in range(40):
        terrain = {(x, y): rng.choice(BLOCKING) for x in range(12, 29) for y in range(12, 29)
                   if rng.random() < 0.2 and (x, y) != c}
        for tx in range(13, 28):
            for ty in range(13, 28):
                t = (tx, ty)
                D = _dist(c, t)
                k = model_classify(terrain, [], c, t, D)
                if k == "gloom" or (k == "visible") != model_visible(terrain, c, t):
                    fails += 1
                    print("  [7] FAIL: no-source classify %s != v3 rule at %s" % (k, t))
    # fog-on and fog-off see the same answer: classify is a pure function of the
    # source list, which only changes inside the rebuild (asserted at build time too).
    print("  [7] gloom semantics + no-source equivalence to the v3 terrain rule: %s"
          % ("ok" if not fails else "see FAILs"))

    # 8. v5 True Seeing: within the observer's true range the gloom surcharge is not paid;
    #    beyond it the army's wider sight is gloomed as before; terrain still blocks.
    t_checks = [
        # (sources, target, radius, t_range, want, why)
        ([(24, 20)], (24, 20), 4, 4, "visible", "gloomed hex at 4, True Seeing 4: visible"),
        ([(24, 20)], (24, 20), 4, 3, "gloom", "same hex, True Seeing 3: still hidden"),
        ([(24, 20)], (26, 20), 8, 4, "gloom", "6 away in the aura, radius 8, TS 4: hidden"),
        ([(24, 20)], (26, 20), 8, 6, "visible", "same hex, True Seeing 6: visible"),
        ([], (28, 20), 8, 0, "visible", "no sources, no True Seeing: unchanged"),
    ]
    for srcs, t, r, tr, want, why in t_checks:
        got = model_classify({}, srcs, c, t, r, tr)
        ok = got == want
        if not ok:
            fails += 1
        print("  [8] %-58s %s" % (why, "ok" if ok else "FAIL (got %s)" % got))
    if model_classify(wall, [(24, 20)], c, (24, 20), 20, 20) != "blocked":
        fails += 1
        print("  [8] FAIL: True Seeing saw through Earth")
    else:
        print("  [8] True Seeing does not see through Earth/Rock: ok")

    # 6. symmetry by construction: one function models both directions; the build
    #    asserts stub_fog/stub_unfog target the same cave entry (run it now).
    build()
    print("  [6] build-time symmetry assertion (shared los_core): ok")

    print("\n--test: %s" % ("ALL PASS" if not fails else "%d FAILURE(S)" % fails))
    sys.exit(1 if fails else 0)


# ============================================================================
def disasm(data, va, title):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    print("   --- %s @0x%08X (%d B) ---" % (title, va, len(data)))
    for i in md.disasm(data, va):
        print("   %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))


def main():
    ap = argparse.ArgumentParser(
        description="Terrain LOS blocking (Earth/Rock) + fog rebuild on terrain change")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--dis", "--show", action="store_true", dest="dis")
    ap.add_argument("--test", action="store_true",
                    help="pure-Python line-walk model vs independent reference")
    args = ap.parse_args()

    if args.test:
        run_test()
        return

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s" % DLL)
    data = bytearray(open(DLL, "rb").read())
    cv = build()

    used = cv["_end"] - CAVE_VA
    print("build_los_terrain  blocking={%d,%d}  cave 0x%08X..0x%08X (%d B of %d)"
          % (BLOCKING[0], BLOCKING[1], CAVE_VA, cv["_end"] - 1, used, CAVE_LIMIT))
    used2 = cv["_end2"] - CAVE2_VA
    print("  cave 2 (True Seeing) 0x%08X..0x%08X (%d B of %d)"
          % (CAVE2_VA, cv["_end2"] - 1, used2, CAVE2_LIMIT))
    if used > CAVE_LIMIT or used2 > CAVE2_LIMIT:
        sys.exit("ERROR: cave overflows its reservation")
    for k in CAVE_ORDER + CAVE2_ORDER:
        va, b = cv[k]
        print("    %-10s 0x%08X  %4d B" % (k, va, len(b)))

    if args.dis:
        print()
        for k in CAVE_ORDER + CAVE2_ORDER:
            if k == "table":
                continue
            va, b = cv[k]
            disasm(b, va, k)
        print()

    # desired edits: (va, orig, new, label, kind)
    edits = []
    for name, va, ob, kind in SITES:
        nb = hook_bytes(kind, va, cv[STUB_FOR_SITE[name]][0], len(ob))
        edits.append((va, ob, nb, name, kind))
    for name, va in TRIG_SITES:
        ob = b"\xE8" + struct.pack("<i", INVMAP - (va + 5))
        nb = b"\xE8" + struct.pack("<i", cv["trig"][0] - (va + 5))
        edits.append((va, ob, nb, name, "call"))
    for name, va, vanilla_tgt, cave in CALL_SITES:
        ob = b"\xE8" + struct.pack("<i", vanilla_tgt - (va + 5))
        nb = b"\xE8" + struct.pack("<i", cv[cave][0] - (va + 5))
        edits.append((va, ob, nb, name, "call"))
    for name, va, ob, nb in RAW_SITES:
        edits.append((va, ob, nb, name, "raw"))

    def cur(va, n):
        return bytes(data[off(va):off(va) + n])

    # VMT+0x94 is handled apart from `edits`: v2 keeps it VANILLA. Recognised states:
    # VMT_ORIG (correct) and LEGACY_VMT (the v1 repoint -- both --apply and --undo
    # restore it to VMT_ORIG); anything else is foreign and aborts.
    vmt_cur = cur(VMT_SLOT, 4)
    if vmt_cur not in (VMT_ORIG, LEGACY_VMT):
        sys.exit("ABORT: VMT+0x94 slot @0x%08X is FOREIGN (%s) -- refusing to touch."
                 % (VMT_SLOT, vmt_cur.hex().upper()))

    # the hand edit at 0x557721BE must be intact whatever we do
    hand_ok = cur(HAND_EDIT_VA, len(HAND_EDIT)) == HAND_EDIT
    if not hand_ok:
        sys.exit("ABORT: the sight+2 hand edit @0x%08X is NOT the expected bytes (%s) -- "
                 "the ExploreArea region has changed; re-measure before touching it."
                 % (HAND_EDIT_VA, cur(HAND_EDIT_VA, 6).hex().upper()))

    if args.verify or (not args.apply and not args.undo):
        allok = True
        for va, ob, nb, lbl, kind in edits:
            c = cur(va, len(ob))
            if c == nb:
                st = "LOS"
            elif c == ob:
                st, allok = "original", False
            elif is_ours_hook(kind, va, c, len(ob)):
                st, allok = "LOS (stale layout -- run --apply)", False
            else:
                st, allok = "FOREIGN", False
            print("  %-20s 0x%08X  %-14s %s" % (lbl, va, c.hex().upper(), st))
        cave_ok = all(cur(cv[k][0], len(cv[k][1])) == cv[k][1]
                      for k in CAVE_ORDER + CAVE2_ORDER)
        vmt_ok = vmt_cur == VMT_ORIG
        print("  %-20s 0x%08X  %-14s %s" % ("vmt_slot", VMT_SLOT, vmt_cur.hex().upper(),
              "vanilla (correct)" if vmt_ok else "LEGACY v1 repoint -- run --apply"))
        print("  caves match: %s" % cave_ok)
        print("  hand edit @0x%08X intact: %s" % (HAND_EDIT_VA, hand_ok))
        print("\nSTATUS: %s" % ("APPLIED and intact" if (allok and cave_ok and vmt_ok)
                                else "NOT applied (or partial/legacy) -- run --apply"))
        return

    if args.undo:
        reloc_check(data)
        n = 0
        for va, ob, nb, lbl, kind in edits:
            c = cur(va, len(ob))
            if c == nb or is_ours_hook(kind, va, c, len(ob)):
                data[off(va):off(va) + len(ob)] = ob
                n += 1
            elif c == ob:
                pass                     # already original
            else:
                sys.exit("ABORT undo: %s @0x%08X is FOREIGN (%s) -- refusing to guess."
                         % (lbl, va, c.hex().upper()))
        data[off(VMT_SLOT):off(VMT_SLOT) + 4] = VMT_ORIG   # vanilla whichever state
        data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = b"\x00" * CAVE_LIMIT
        data[off(CAVE2_VA):off(CAVE2_VA) + CAVE2_LIMIT] = b"\x00" * CAVE2_LIMIT
        if cur(HAND_EDIT_VA, len(HAND_EDIT)) != HAND_EDIT:
            sys.exit("BUG: undo would damage the hand edit -- not writing.")
        open(DLL, "wb").write(data)
        print("UNDO: restored %d site(s) + VMT slot, zeroed 0x%08X..0x%08X. "
              "No backup touched; hand edit left intact." % (n, CAVE_VA, CAVE_VA + CAVE_LIMIT))
        return

    # ---- apply path ----
    # Verify-before-write: EVERY site must individually be original or ours (v1 or v2);
    # any foreign byte-run aborts. Mixed original/ours overall is the expected v1->v2
    # migration state (hooks ours, trig sites still original, VMT legacy).
    reloc_check(data)
    for va, ob, nb, lbl, kind in edits:
        c = cur(va, len(ob))
        if c not in (ob, nb) and not is_ours_hook(kind, va, c, len(ob)):
            sys.exit("ABORT: %s @0x%08X is FOREIGN (%s) -- inspect before writing."
                     % (lbl, va, c.hex().upper()))
    fresh = (all(cur(va, len(ob)) == ob for va, ob, nb, _, _ in edits)
             and vmt_cur == VMT_ORIG)
    done = (all(cur(va, len(ob)) == nb for va, ob, nb, _, _ in edits)
            and vmt_cur == VMT_ORIG)
    if fresh:
        zone = cur(CAVE_VA, CAVE_LIMIT)
        if zone != b"\x00" * CAVE_LIMIT:
            sys.exit("ABORT: cave zone 0x%08X is not zero -- someone else owns it" % CAVE_VA)
    # cave 2 (v5) is claimed on its first write, fresh or re-tune: zero or ours only.
    payload2 = bytearray(CAVE2_LIMIT)
    for k in CAVE2_ORDER:
        va, b = cv[k]
        payload2[va - CAVE2_VA: va - CAVE2_VA + len(b)] = b
    zone2 = cur(CAVE2_VA, CAVE2_LIMIT)
    if zone2 != b"\x00" * CAVE2_LIMIT and zone2 != bytes(payload2):
        sys.exit("ABORT: cave 2 zone 0x%08X is neither zero nor this script's payload -- "
                 "someone else owns it (or an older cave-2 layout: --undo first)" % CAVE2_VA)
    # non-fresh: the whole 0x800 reservation was claimed (zone-zero-verified) by the
    # first apply; the hook checks above prove the install is ours, so rewriting the
    # full reservation in place is safe (in-place re-tune convention).

    caves_ok = all(cur(cv[k][0], len(cv[k][1])) == cv[k][1]
                   for k in CAVE_ORDER + CAVE2_ORDER)
    if done and caves_ok:
        print("Already applied and up to date -- nothing to do.")
        return

    if not args.apply:
        print("DRY RUN (state: %s) -- re-run with --apply to commit."
              % ("original" if fresh else "applied, cave differs (re-tune)"))
        return

    # Backup ONLY from a positively-verified original state -- never from our own
    # output (undo and re-tune paths take none).
    # "fresh" only proves THIS script's sites are original -- after --undo that is exactly
    # the state this script produced over a DLL carrying every other feature. So the
    # snapshot also requires a byte-match against the vanilla root copy.
    vanilla = os.path.join(os.path.dirname(GAME), os.path.basename(DLL))
    if (fresh and not os.path.exists(BAK) and os.path.isfile(vanilla)
            and open(vanilla, "rb").read() == bytes(data)):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BAK)
        print("backup -> %s" % os.path.basename(BAK))

    payload = bytearray(CAVE_LIMIT)
    for k in CAVE_ORDER:
        va, b = cv[k]
        payload[va - CAVE_VA: va - CAVE_VA + len(b)] = b
    data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = payload
    data[off(CAVE2_VA):off(CAVE2_VA) + CAVE2_LIMIT] = payload2
    for va, ob, nb, _, _ in edits:
        data[off(va):off(va) + len(ob)] = nb
    data[off(VMT_SLOT):off(VMT_SLOT) + 4] = VMT_ORIG   # v2: slot stays vanilla
    if bytes(data[off(HAND_EDIT_VA):off(HAND_EDIT_VA) + len(HAND_EDIT)]) != HAND_EDIT:
        sys.exit("BUG: apply would damage the hand edit -- not writing.")
    try:
        open(DLL, "wb").write(data)
    except PermissionError:
        sys.exit("ERROR: %s is locked. Kill AoW/AoWCompat/AoWDevEd/AoWEd and retry."
                 % os.path.basename(DLL))
    print("APPLIED (%s). Revert with --undo (surgical)." % ("fresh" if fresh else "re-tune"))
    print("Status: applied, untested -- needs the user's in-game test.")


if __name__ == "__main__":
    main()
