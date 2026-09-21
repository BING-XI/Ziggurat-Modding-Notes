#!/usr/bin/env python3
r"""
AoW1 mod -- strategic-map terrain LOS blocking + fog-refcount rebuild on terrain change.

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
# ----------------------------------------------------------------------------

# mutable state (BSS page slack; runtime-only, no file backing)
FLAG = 0x558FAA00               # 1 while the zero-cache broadcast runs
PEND = 0x558FAA01               # 1 = rebuild requested

# engine entry points (all AoWEPACK.dpl, live-verified this session)
UPDVIS    = 0x55778408          # TAoWHSMap.UpdateVisibility
LOCKMCE   = 0x5577246C          # TAbstractAoWHSMap.LockMapChangedEvent
INITMSG   = 0x5570347C          # thunk EngineP!Engine.InitMsg
GETLVL    = 0x557020EC          # thunk HSEPack!TMapContainer.GetMapLevel
RESETFOG  = 0x557721D4          # TAoWMapLevel.ResetFog (zero callers in vanilla)
INVMAP    = 0x557725C0          # TAbstractAoWHSMap.InvalidateMap
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

    # --- neighbour delta table: parity*0x40 + side*8 -> (dx dword, dy dword)
    a_tab = CAVE_VA
    tab = bytearray(0x80)
    for p, dl in ((0, DELTAS_EVEN), (1, DELTAS_ODD)):
        for s, (dx, dy) in enumerate(dl):
            struct.pack_into("<ii", tab, p * 0x40 + s * 8, dx, dy)
    out["table"] = (a_tab, bytes(tab))

    # --- los_core: ZF=1 blocked, ZF=0 clear; preserves everything.
    # Reads the fill's frame via ebp (identical layout in all four fills):
    #   [ebp-0x0C]/[ebp-0x08] centre x,y   [ebp-0x14]/[ebp-0x10] target x,y
    # ebx = TAoWMapLevel (from the pushad frame at [esp+0x40]).
    # Frame: [esp+0x00] load delta  +0x04/+0x08 cand x,y  +0x0C bestd  +0x10 cap
    #        +0x14 t_x  +0x18 t_z (cube)  +0x1C side  +0x20/+0x24 best x,y
    #        +0x28 mode (0 = walk A first-tie-wins, 1 = walk B last-tie-wins)
    a_los = align(a_tab + 0x80)
    pop_at = a_los + 9          # pushad(1) + sub esp,0x30(3) + call(5)
    src_los = f"""
        pushad
        sub  esp, 0x30
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
        mov  dword ptr [esp+0x28], 0    ; mode = walk A
    walkinit:
        mov  esi, [ebp-0x0C]            ; cur x = centre x
        mov  edi, [ebp-0x08]            ; cur y = centre y
        mov  dword ptr [esp+0x10], {STEP_CAP}
    step:
        cmp  esi, [ebp-0x14]
        jne  notdone
        cmp  edi, [ebp-0x10]
        je   clear
    notdone:
        dec  dword ptr [esp+0x10]
        js   clear                      ; cap exhausted -> fail open
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
        cmp  esi, [ebp-0x14]
        jne  check
        cmp  edi, [ebp-0x10]
        je   clear                      ; reached target: endpoint excluded
    check:
        mov  ebx, [esp+0x40]            ; level (saved ebx in pushad frame)
        test esi, esi
        js   step                       ; off-map intermediate: skip check
        test edi, edi
        js   step
        cmp  esi, [ebx+0x0C]
        jge  step
        cmp  edi, [ebx+0x10]
        jge  step
        mov  eax, [ebx+0x74]
        mov  eax, [eax + esi*4]
        mov  edx, [ebx+0x78]
        add  eax, [edx + edi*4]         ; field
        mov  dl, [eax+0x14]             ; terrain
        cmp  dl, {BLOCKING[0]}
        je   walkhit
        cmp  dl, {BLOCKING[1]}
        je   walkhit
        jmp  step
    walkhit:                            ; this walk crossed blocking terrain
        cmp  dword ptr [esp+0x28], 0
        jne  blocked                    ; walk B blocked too -> hidden
        mov  dword ptr [esp+0x28], 1    ; retry with opposite tie-break
        jmp  walkinit
    blocked:
        add  esp, 0x30
        popad
        cmp  eax, eax                   ; ZF=1
        ret
    clear:
        add  esp, 0x30
        popad
        test esp, esp                   ; ZF=0 (esp never 0)
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
    """
    nxt = asm("los_core", a_los, src_los)

    # --- fill stubs (jmp'd into; jmp back). All four call the SAME los_core.
    a = align(nxt)
    nxt = asm("stub_fog", a, f"""
        call 0x{a_los:X}
        jz   skip
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
        cmp  byte ptr [esi+0x1A], 0
        jne  taken
        jmp  0x55772053
    taken:
        jmp  0x5577205E
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
    a = align(nxt); nxt = unfog_stub("stub_army",  a, 0x17, d5, 0x5578E22D)
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
        cmp  byte ptr [eax + 0x{PEND:X}], 0
        jne  wipe
    orig:
        mov  eax, ebx
        call 0x{LOCKMCE:X}
        jmp  0x55778425
    wipe:
        mov  byte ptr [eax + 0x{PEND:X}], 0
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

    out["_end"] = nxt

    # SYMMETRY ASSERTION: fog and unfog filter through one byte-identical code path.
    for k in ("stub_fog", "stub_unfog", "stub_ue", "stub_ex"):
        va, b = out[k]
        assert b[0] == 0xE8, k
        tgt = va + 5 + struct.unpack("<i", b[1:5])[0]
        assert tgt == a_los, f"{k} does not call the shared los_core"
    return out


CAVE_ORDER = ("table", "los_core", "stub_fog", "stub_unfog", "stub_ue", "stub_ex",
              "stub_army", "stub_ps", "stub_pool", "stub_watch", "stub_gate",
              "uv_hook", "trig")

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
    ranges.append((CAVE_VA, CAVE_VA + CAVE_LIMIT))
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
    if used > CAVE_LIMIT:
        sys.exit("ERROR: cave overflows its reservation")
    for k in CAVE_ORDER:
        va, b = cv[k]
        print("    %-10s 0x%08X  %4d B" % (k, va, len(b)))

    if args.dis:
        print()
        for k in CAVE_ORDER:
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
        cave_ok = all(cur(cv[k][0], len(cv[k][1])) == cv[k][1] for k in CAVE_ORDER)
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
    # non-fresh: the whole 0x800 reservation was claimed (zone-zero-verified) by the
    # first apply; the hook checks above prove the install is ours, so rewriting the
    # full reservation in place is safe (in-place re-tune convention).

    caves_ok = all(cur(cv[k][0], len(cv[k][1])) == cv[k][1] for k in CAVE_ORDER)
    if done and caves_ok:
        print("Already applied and up to date -- nothing to do.")
        return

    if not args.apply:
        print("DRY RUN (state: %s) -- re-run with --apply to commit."
              % ("original" if fresh else "applied, cave differs (re-tune)"))
        return

    # Backup ONLY from a positively-verified original state -- never from our own
    # output (undo and re-tune paths take none).
    if fresh and not os.path.exists(BAK):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BAK)
        print("backup -> %s" % os.path.basename(BAK))

    payload = bytearray(CAVE_LIMIT)
    for k in CAVE_ORDER:
        va, b = cv[k]
        payload[va - CAVE_VA: va - CAVE_VA + len(b)] = b
    data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = payload
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
