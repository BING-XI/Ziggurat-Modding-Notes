#!/usr/bin/env python3
r"""
AoW1 mod -- elemental terrain healing ("elemheal"; the feature grew out of
waterheal, and keeps that script name, cave, hook and backup for continuity).
Each classic elemental heals while moving through its own element on the
strategic map, with the Healing SFX at half volume iff the heal happened:

  Air   Elemental (224/0xE0)  +1 HP on the SURFACE level or the FIRMAMENT
                              (level 3) -- any terrain
  Earth Elemental (225/0xE1)  +1 HP on any UNDERGROUND level, or on a
                              Mountain-overlay hex on ANY level; NEVER on the
                              Firmament
  Fire  Elemental (226/0xE2)  +4 HP on Lava (terrain 0x09)
  Water Elemental (227/0xE3)  +2 HP on Water (0x00) or cave water (0x0A)

Heal amounts are in displayed (post-DAM/HP-doubling) HP.  Unit ids verified
against the live Release/Unitres.pfs 2026-08-30 (`pfs.py names`; Fire Sprite
228 anchors the range).  Mountain is NOT a terrain: it is overlay 0 in the
field's overlay byte [field+0x15] (0xFF = none), the same code on every
terrain row and level (Movement_Tables_Terrain_Types.md) -- so "any mountain"
is one byte-compare.  Level byte [field+0x12]: 0 = surface (the engine's own
Path of Life/Decay gate is `cmp byte [edx+0x12],0` = surface-only,
Chasm_Sky_Terrain_Design.md item 5), 1+ = the underground levels (the editor
allows up to 8 levels, z <= 7).

v1 (2026-08-30): Water Elemental only, no transport gate.
v2 (2026-08-30): transport gate -- heal only on the elemental's own movement,
    not while being carried by a transport (the rule the Path abilities use).
v3 (2026-08-30): all four elementals, dispatch on resource index.
v4 (2026-08-30): per-elemental chime volume (user ruling) -- Air/Earth heals
    play the chime at QUARTER volume (0x19 = 25/100), Water/Fire keep HALF
    (0x32 = 50/100).  EBP now packs (volume << 16) | heal at dispatch.
v5 (2026-09-06): the EARTH arm excludes the Firmament (build_maplevel4.py's
    level 3).  Its rule is "any level != 0", which would otherwise have made
    open sky count as underground.
v6 (2026-09-06): the AIR arm ACCEPTS the Firmament as well as the surface --
    `cmp [esi+0x12],0 / jne _out` becomes `cmp 0 / je ok / cmp 3 / jne _out`
    at 0x5582407E.  Earth's v5 exclusion is unchanged.  User ruling: the
    Firmament is open sky, so air elementals heal there and earth ones do not.

Target: AoWEPACK.dpl ONLY.  Backup: AoWEPACK.dpl.pre-waterheal (taken ONLY from
a byte-verified vanilla state; never overwritten -- it is the vanilla reference).

MECHANISM
  Hook @0x557803BA in TAbstractUnit.MovedTo @0x55780328 (EBX=unit, ESI=entered
  field): the 8 bytes `movsx eax,[esi+0x14]; cmp ax,7` -> `jmp cave` + 3 NOP.
  The v4 cave (saves EBX/ESI/EDI/EBP; EBP carries (volume << 16) | heal across
  the hp/max vcalls and SetHitPoints -- Delphi callees preserve
  EBX/ESI/EDI/EBP, QA-verified through the GetHits redirect chain):
    1. TRANSPORT GATE (shared, first) -- replicates the Path-ability gate at
       0x557803EF..0x55780418 in the same function, including the
       build_path_transportgate.py refinement (semantics copied, NOT its cave
       called -- no cross-feature dependency):
         owner = [ebx+4]; if IsClass(owner, TArmy)  (classref [0x557130AC],
         System.@IsClass thunk @0x557010C0) then
         t = TArmy.Transporter(owner, DL=0xFF) @0x5578E00C  -- first unit in
         the army with transport capacity, else 0.  t != 0 and t != EBX
         (a transporter that ISN'T me == I am carried) -> no heal, no sound.
         t == 0, t == EBX (I am the transporter), or owner not a TArmy ->
         own movement, proceed.  Polarity matches the Path gate exactly.
    2. unit resource-index via [ebx+0x40]->resource (null-guarded), [+4]->list,
       vcall [list_vmt+0x84]; dispatch on 0xE0..0xE3, anything else exits;
    3. per-elemental condition (bytes re-read via ESI, which the cave never
       modifies); EBP = (chime volume << 16) | heal amount:
         0xE0 air:   [esi+0x12] == 0 or 3 (surface/Firmament, v6)
                                                       -> EBP = 0x190001 (1, quarter)
         0xE1 earth: [esi+0x12] != 0 AND != 3 (v5), OR
                     [esi+0x15] == 0 (Mountain, any lvl) -> EBP = 0x190001 (1, quarter)
         0xE2 fire:  [esi+0x14] == 0x09 (Lava)          -> EBP = 0x320004 (4, half)
         0xE3 water: [esi+0x14] == 0x00 or 0x0A         -> EBP = 0x320002 (2, half)
       Loaded with `mov ebp, imm32` (5-byte BD form -- no imm8 narrowing).
    4. hp = vcall [vmt+0xE0] GetHitPoints, max = vcall [vmt+0xD0] GetHits.
       ⚠ TUnit.GetHitPoints is `mov al,[eax+0x3e]; ret` -- AL only, upper EAX
       dirty -- so both values are movsx'd before the 32-bit compare (the
       DAM/HP "promoted dirty bits" lesson). hp >= max -> no heal, no sound;
    5. vcall [vmt+0xE4] SetHitPoints(hp+heal) via `movzx edx,bp` (heal = low
       16 bits of the pack) + `add edx,edi`; the setter clamps to [0,max]
       (byte-compares BL vs GetHits AL at 0x557827D4);
    6. sound is PRESENTATION-ONLY and fog-gated (the heal is NOT fog-gated --
       MP determinism): TAoWHSMap.WatchingTerrain @0x55775ABC, mirroring the
       engine site 0x557B1A2F..57: EAX=map, DL=x [esi+0x10], CL=y [esi+0x11],
       stack level [esi+0x12] pushed first then radius 1 (frame: [ebp+8]=1,
       [ebp+0xC]=level).  Returns AL; false -> skip sound;
    7. Healing SFX: ctl=[[SET_VAR]+0x80], TAbilityControl.GetAbility
       @0x557501C0 (EDX=0x2F Healing), lib=[ability+0x18], then PlayEx thunk
       @0x55702CFC: EAX=lib, EDX=0 (sound index), ECX = pack >> 16 (the
       per-elemental volume: 0x32 half for Water/Fire, 0x19 quarter for
       Air/Earth; engine full-volume site 0x557C6419 uses ECX=0x64), five
       stack args pushed in engine order: 0 (loop), 0 (delay), 1, 0, 0.
       Every pointer on the way is null-guarded.
    8. tail replays the displaced `movsx eax,[esi+0x14]; cmp ax,7` LAST (the
       cmp's flags feed the jne at 0x557803C2) and jumps to 0x557803C2.

  Register liveness across the hook (disassembly of MovedTo, 2026-08-30):
  everything after 0x557803C2 redefines EAX/ECX/EDX before reading them
  (movsx eax @03C4, movsx ecx @03D2, xor edx,edx @03D6; the 03E5 branch reads
  [ebp-4] then EBX/ESI).  So v3 clobbering ECX/EDX on EVERY path (v2 only did
  on the water path) is safe; EBX/ESI/EDI/EBP are push/pop-preserved.

  Globals, position-independently (aow1-dpl-rebasing): TWO call/pop delta
  anchors.  Anchor 1 (into EDX, immediately consumed) reads the TArmy classref
  [0x557130AC] for the gate.  Anchor 2 (into EDI, dead by then) reads
  [0x558FA040] (the AoWHSMap object) and [0x558FA044] (the AoWHSSet object --
  cf. THealingCA.Play @0x5576BDC4) as [edi+disp32].  All other calls are rel32.
  No absolute memory operand anywhere in the cave.

Cave @0x55824000 (verified all-zero 0x55823E00..0x55825200 pre-install; no
other build script references 0x55824* -- grep re-checked 2026-08-30).

RE-TUNE IN PLACE (project convention -- never revert-and-reapply): --apply
accepts the vanilla state (hook original + cave zero) OR any installed
v1..v5 state (hook patched + exact old cave bytes, regenerated by this script
for the byte-compare, with the zone the new cave grows into verified all-zero)
and rewrites the cave in place.  v6 is the longest.  Every earlier source is
FROZEN -- editing one destroys the recognition and turns the rewrite blind.
The backup is taken only from the vanilla state and only if absent -- an
existing .pre-waterheal is never overwritten.

Usage:
  no args   dry run: verify + report current state (vanilla/v1..v6/other)
  --apply   patch (vanilla -> v6, or in-place rewrite v1..v5 -> v6)
  --undo    surgical: restore the 8 hook bytes, zero the full v6 cave length
            (from any recognised applied state); no backup used
  --dis / --show   capstone-disassemble the v6 cave and exit
"""
import os, sys, shutil, struct
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script; AOW_GAME_DIR overrides.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: never the game root
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-waterheal")

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

DLL_BASE   = 0x55700000
HOOK       = 0x557803BA                  # in TAbstractUnit.MovedTo
# movsx eax,[esi+0x14]; cmp ax,7 -- byte-diffed vs AoWEPACK_original_backup.dpl
# 2026-08-30: the cmp is the imm8 form 66 83 F8 07 (NOT 66 3D 07 00).
HOOK_ORIG  = bytes.fromhex("0FBE4614 6683F807".replace(" ", ""))
CONT       = 0x557803C2                  # the jne the replayed cmp feeds
CAVE       = 0x55824000
ISCLASS    = 0x557010C0                  # VCL30 System.@IsClass thunk
TRANSPORTER= 0x5578E00C                  # AoWE.TArmy.Transporter(EAX=army, DL=mask)
CLS_VAR    = 0x557130AC                  # ptr -> AoWE.TArmy class reference
WATCHTERR  = 0x55775ABC                  # AoWE.TAoWHSMap.WatchingTerrain
GETABILITY = 0x557501C0                  # AoWE.TAbilityControl.GetAbility
PLAYEX     = 0x55702CFC                  # SoundP thunk Sound.TSFXLibrary.PlayEx
MAP_VAR    = 0x558FA040                  # AoWE.AoWHSMap object lives here
SET_VAR    = 0x558FA044                  # AoWE.AoWHSSet object lives here
WATER, UWATER = 0x00, 0x0A               # terrain byte [field+0x14]
LAVA           = 0x09                    # terrain byte
OVL_MOUNTAIN   = 0x00                    # overlay byte [field+0x15] (0xFF=none)
LVL_SURFACE    = 0x00                    # level byte [field+0x12]
LVL_SKY        = 0x03                    # the Sky map level (build_maplevel4.py)
IDX_AIR_ELEM   = 0xE0                    # 224 -- ids read from live Unitres.pfs
IDX_EARTH_ELEM = 0xE1                    # 225
IDX_FIRE_ELEM  = 0xE2                    # 226
IDX_WATER_ELEM = 0xE3                    # 227
ABIL_HEALING   = 0x2F
HEAL_AIR, HEAL_EARTH, HEAL_FIRE, HEAL_WATER = 1, 1, 4, 2   # displayed HP
HEAL_AMOUNT    = 2                       # v1/v2 amount -- state recognition only
SFX_VOLUME     = 0x32                    # v1..v3 flat volume -- recognition only
VOL_HALF       = 0x32                    # 50/100: Water + Fire chime
VOL_QUARTER    = 0x19                    # 25/100: Air + Earth chime (user ruling)
# v4: EBP = (chime volume << 16) | heal amount, set once per dispatch block.
def pack(vol, heal):
    assert 0 < heal < 0x10000 and 0 < vol <= 0x64
    return (vol << 16) | heal
PACK_AIR   = pack(VOL_QUARTER, HEAL_AIR)     # 0x190001
PACK_EARTH = pack(VOL_QUARTER, HEAL_EARTH)   # 0x190001
PACK_FIRE  = pack(VOL_HALF,    HEAL_FIRE)    # 0x320004
PACK_WATER = pack(VOL_HALF,    HEAL_WATER)   # 0x320002

# ⚠ "this feature's sites are original" is NOT proof the FILE is unpatched --
# after --undo it is exactly the state this script itself just produced, over a
# DLL carrying every other feature.  A snapshot minted there would sit on disk
# looking authoritative while holding a patched image.  So gate the backup on a
# positive byte-compare against the pristine reference instead.
PRISTINE = os.path.join(GAME, "Modding Resources", "AoWEPACK_original_backup.dpl")


def proven_pristine():
    """True only if the live DLL is byte-identical to the pristine reference."""
    try:
        with open(PRISTINE, "rb") as f:
            ref = f.read()
    except OSError:
        return False
    with open(DLL, "rb") as f:
        return f.read() == ref


def sd(x):                               # signed hex displacement for asm text
    return f"+{x:#x}" if x >= 0 else f"-{-x:#x}"

def cave_src(d_map, d_set, d_cls=None):
    # ⚠ FROZEN v1/v2 SOURCE -- kept ONLY so --apply / --undo can byte-recognise
    # a previously-installed cave.  Do not edit: its assembled bytes must stay
    # identical to what v1/v2 of this script wrote.  d_cls None -> v1 (no gate).
    gate = "" if d_cls is None else f"""
    // ---- transport gate: same rule as the Path abilities (v2) ----
    mov eax, dword ptr [ebx+4]           // unit's owner
    call _a1                             // PIC anchor 1 (EDX scratch)
_a1:
    pop edx
    mov edx, dword ptr [edx{sd(d_cls)}]  // [0x557130AC] -> TArmy classref
    call {ISCLASS:#x}                    // System.@IsClass -> AL
    test al, al
    jz _own                              // owner not a TArmy -> own movement
    mov eax, dword ptr [ebx+4]           // army (EAX clobbered by IsClass)
    mov dl, 0xff
    call {TRANSPORTER:#x}                // TArmy.Transporter -> transporter|0
    test eax, eax
    jz _own                              // no transporter in army
    cmp eax, ebx                         // the transporter is me?
    jne _out                             // carried by another: no heal, no sound
_own:
"""
    return f"""
    mov al, byte ptr [esi+0x14]
    cmp al, {WATER}
    je _water
    cmp al, {UWATER}
    jne _tail
_water:
    push ebx
    push esi
    push edi
{gate}
    mov edx, dword ptr [ebx+0x40]        // resource; null unit-resource -> out
    test edx, edx
    jz _out
    mov eax, dword ptr [edx+4]           // resource list (self)
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x84]            // -> resource index
    cmp eax, {IDX_WATER_ELEM}
    jne _out
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx+0xE0]            // GetHitPoints -> AL (upper bits dirty)
    movsx edi, al
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx+0xD0]            // GetHits (max) -> AL
    movsx eax, al
    cmp edi, eax
    jge _out                             // full HP: no heal -> no sound
    lea edx, [edi+{HEAL_AMOUNT}]
    mov eax, ebx
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0xE4]            // SetHitPoints (clamps to max)
    call _a2                             // PIC anchor 2 (EDI is dead now)
_a2:
    pop edi
    mov eax, dword ptr [edi{sd(d_map)}]  // AoWHSMap object
    test eax, eax
    jz _out
    movsx ecx, byte ptr [esi+0x12]
    push ecx                             // level  ([ebp+0xC] in callee)
    push 1                               // radius ([ebp+0x8])
    mov dl, byte ptr [esi+0x10]          // x
    mov cl, byte ptr [esi+0x11]          // y
    call {WATCHTERR:#x}                  // WatchingTerrain -> AL
    test al, al
    jz _out                              // fogged: heal stays, sound skipped
    mov eax, dword ptr [edi{sd(d_set)}]  // AoWHSSet object
    test eax, eax
    jz _out
    mov eax, dword ptr [eax+0x80]        // TAbilityControl
    test eax, eax
    jz _out
    mov edx, {ABIL_HEALING}
    call {GETABILITY:#x}                 // GetAbility(ctl, 0x2F)
    test eax, eax
    jz _out
    mov eax, dword ptr [eax+0x18]        // SFX library
    test eax, eax
    jz _out
    push 0                               // loop flag (first-pushed, engine order)
    push 0                               // delay
    push 1
    push 0
    push 0
    mov ecx, {SFX_VOLUME}                // half volume
    xor edx, edx                         // sound index 0
    call {PLAYEX:#x}                     // TSFXLibrary.PlayEx
_out:
    pop edi
    pop esi
    pop ebx
_tail:
    movsx eax, byte ptr [esi+0x14]       // replay displaced bytes LAST --
    cmp ax, 7                            // flags feed the jne at CONT
    jmp {CONT:#x}
"""

def cave_src_v3(d_map, d_set, d_cls):
    # ⚠ FROZEN v3 SOURCE -- kept ONLY so --apply / --undo can byte-recognise a
    # previously-installed v3 cave.  Do not edit: its assembled bytes must stay
    # identical to what v3 of this script wrote.
    return f"""
    push ebx
    push esi
    push edi
    push ebp                             // EBP = heal amount after dispatch
    // ---- transport gate (shared, first): heal only on own movement ----
    mov eax, dword ptr [ebx+4]           // unit's owner
    call _a1                             // PIC anchor 1 (EDX scratch)
_a1:
    pop edx
    mov edx, dword ptr [edx{sd(d_cls)}]  // [0x557130AC] -> TArmy classref
    call {ISCLASS:#x}                    // System.@IsClass -> AL
    test al, al
    jz _own                              // owner not a TArmy -> own movement
    mov eax, dword ptr [ebx+4]           // army (EAX clobbered by IsClass)
    mov dl, 0xff
    call {TRANSPORTER:#x}                // TArmy.Transporter -> transporter|0
    test eax, eax
    jz _own                              // no transporter in army
    cmp eax, ebx                         // the transporter is me?
    jne _out                             // carried by another: no heal, no sound
_own:
    // ---- resource index (shared) ----
    mov edx, dword ptr [ebx+0x40]        // resource; null unit-resource -> out
    test edx, edx
    jz _out
    mov eax, dword ptr [edx+4]           // resource list (self)
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x84]            // -> resource index
    // ---- dispatch: per-elemental condition, heal amount into EBP ----
    cmp eax, {IDX_AIR_ELEM}
    je _air
    cmp eax, {IDX_EARTH_ELEM}
    je _earth
    cmp eax, {IDX_FIRE_ELEM}
    je _fire
    cmp eax, {IDX_WATER_ELEM}
    jne _out
    mov al, byte ptr [esi+0x14]          // water: terrain Water or uWater
    cmp al, {WATER}
    je _wtr
    cmp al, {UWATER}
    jne _out
_wtr:
    mov ebp, {HEAL_WATER}
    jmp _heal
_air:
    cmp byte ptr [esi+0x12], {LVL_SURFACE}   // air: surface level only
    jne _out
    mov ebp, {HEAL_AIR}
    jmp _heal
_earth:
    cmp byte ptr [esi+0x12], {LVL_SURFACE}   // earth: any underground level...
    jne _ert
    cmp byte ptr [esi+0x15], {OVL_MOUNTAIN}  // ...or Mountain overlay anywhere
    jne _out
_ert:
    mov ebp, {HEAL_EARTH}
    jmp _heal
_fire:
    cmp byte ptr [esi+0x14], {LAVA}          // fire: Lava terrain
    jne _out
    mov ebp, {HEAL_FIRE}
_heal:
    // ---- shared hp/max check + SetHitPoints(hp+EBP) ----
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx+0xE0]            // GetHitPoints -> AL (upper bits dirty)
    movsx edi, al
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx+0xD0]            // GetHits (max) -> AL
    movsx eax, al
    cmp edi, eax
    jge _out                             // full HP: no heal -> no sound
    lea edx, [edi+ebp]                   // hp + amount
    mov eax, ebx
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0xE4]            // SetHitPoints (clamps to max)
    // ---- shared fog gate + half-volume Healing chime ----
    call _a2                             // PIC anchor 2 (EDI is dead now)
_a2:
    pop edi
    mov eax, dword ptr [edi{sd(d_map)}]  // AoWHSMap object
    test eax, eax
    jz _out
    movsx ecx, byte ptr [esi+0x12]
    push ecx                             // level  ([ebp+0xC] in callee)
    push 1                               // radius ([ebp+0x8])
    mov dl, byte ptr [esi+0x10]          // x
    mov cl, byte ptr [esi+0x11]          // y
    call {WATCHTERR:#x}                  // WatchingTerrain -> AL
    test al, al
    jz _out                              // fogged: heal stays, sound skipped
    mov eax, dword ptr [edi{sd(d_set)}]  // AoWHSSet object
    test eax, eax
    jz _out
    mov eax, dword ptr [eax+0x80]        // TAbilityControl
    test eax, eax
    jz _out
    mov edx, {ABIL_HEALING}
    call {GETABILITY:#x}                 // GetAbility(ctl, 0x2F)
    test eax, eax
    jz _out
    mov eax, dword ptr [eax+0x18]        // SFX library
    test eax, eax
    jz _out
    push 0                               // loop flag (first-pushed, engine order)
    push 0                               // delay
    push 1
    push 0
    push 0
    mov ecx, {SFX_VOLUME}                // half volume
    xor edx, edx                         // sound index 0
    call {PLAYEX:#x}                     // TSFXLibrary.PlayEx
_out:
    pop ebp
    pop edi
    pop esi
    pop ebx
    movsx eax, byte ptr [esi+0x14]       // replay displaced bytes LAST --
    cmp ax, 7                            // flags feed the jne at CONT
    jmp {CONT:#x}
"""

def cave_src_v4(d_map, d_set, d_cls):
    # ⚠ FROZEN v4 SOURCE -- recognition only, exactly like v1/v2/v3 above.
    # Its assembled bytes must stay identical to what v4 wrote.  Do not edit.
    return f"""
    push ebx
    push esi
    push edi
    push ebp                             // EBP = (volume<<16)|heal after dispatch
    // ---- transport gate (shared, first): heal only on own movement ----
    mov eax, dword ptr [ebx+4]           // unit's owner
    call _a1                             // PIC anchor 1 (EDX scratch)
_a1:
    pop edx
    mov edx, dword ptr [edx{sd(d_cls)}]  // [0x557130AC] -> TArmy classref
    call {ISCLASS:#x}                    // System.@IsClass -> AL
    test al, al
    jz _own                              // owner not a TArmy -> own movement
    mov eax, dword ptr [ebx+4]           // army (EAX clobbered by IsClass)
    mov dl, 0xff
    call {TRANSPORTER:#x}                // TArmy.Transporter -> transporter|0
    test eax, eax
    jz _own                              // no transporter in army
    cmp eax, ebx                         // the transporter is me?
    jne _out                             // carried by another: no heal, no sound
_own:
    // ---- resource index (shared) ----
    mov edx, dword ptr [ebx+0x40]        // resource; null unit-resource -> out
    test edx, edx
    jz _out
    mov eax, dword ptr [edx+4]           // resource list (self)
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x84]            // -> resource index
    // ---- dispatch: EBP = (chime volume << 16) | heal amount ----
    cmp eax, {IDX_AIR_ELEM}
    je _air
    cmp eax, {IDX_EARTH_ELEM}
    je _earth
    cmp eax, {IDX_FIRE_ELEM}
    je _fire
    cmp eax, {IDX_WATER_ELEM}
    jne _out
    mov al, byte ptr [esi+0x14]          // water: terrain Water or uWater
    cmp al, {WATER}
    je _wtr
    cmp al, {UWATER}
    jne _out
_wtr:
    mov ebp, {PACK_WATER:#x}             // heal 2, chime half volume
    jmp _heal
_air:
    cmp byte ptr [esi+0x12], {LVL_SURFACE}   // air: surface level only
    jne _out
    mov ebp, {PACK_AIR:#x}               // heal 1, chime quarter volume
    jmp _heal
_earth:
    cmp byte ptr [esi+0x12], {LVL_SURFACE}   // earth: any underground level...
    jne _ert
    cmp byte ptr [esi+0x15], {OVL_MOUNTAIN}  // ...or Mountain overlay anywhere
    jne _out
_ert:
    mov ebp, {PACK_EARTH:#x}             // heal 1, chime quarter volume
    jmp _heal
_fire:
    cmp byte ptr [esi+0x14], {LAVA}          // fire: Lava terrain
    jne _out
    mov ebp, {PACK_FIRE:#x}              // heal 4, chime half volume
_heal:
    // ---- shared hp/max check + SetHitPoints(hp + heal) ----
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx+0xE0]            // GetHitPoints -> AL (upper bits dirty)
    movsx edi, al
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx+0xD0]            // GetHits (max) -> AL
    movsx eax, al
    cmp edi, eax
    jge _out                             // full HP: no heal -> no sound
    movzx edx, bp                        // heal amount = low 16 bits of pack
    add edx, edi                         // hp + heal
    mov eax, ebx
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0xE4]            // SetHitPoints (clamps to max)
    // ---- shared fog gate + per-elemental-volume Healing chime ----
    call _a2                             // PIC anchor 2 (EDI is dead now)
_a2:
    pop edi
    mov eax, dword ptr [edi{sd(d_map)}]  // AoWHSMap object
    test eax, eax
    jz _out
    movsx ecx, byte ptr [esi+0x12]
    push ecx                             // level  ([ebp+0xC] in callee)
    push 1                               // radius ([ebp+0x8])
    mov dl, byte ptr [esi+0x10]          // x
    mov cl, byte ptr [esi+0x11]          // y
    call {WATCHTERR:#x}                  // WatchingTerrain -> AL
    test al, al
    jz _out                              // fogged: heal stays, sound skipped
    mov eax, dword ptr [edi{sd(d_set)}]  // AoWHSSet object
    test eax, eax
    jz _out
    mov eax, dword ptr [eax+0x80]        // TAbilityControl
    test eax, eax
    jz _out
    mov edx, {ABIL_HEALING}
    call {GETABILITY:#x}                 // GetAbility(ctl, 0x2F)
    test eax, eax
    jz _out
    mov eax, dword ptr [eax+0x18]        // SFX library
    test eax, eax
    jz _out
    push 0                               // loop flag (first-pushed, engine order)
    push 0                               // delay
    push 1
    push 0
    push 0
    mov ecx, ebp                         // volume from the pack...
    shr ecx, 16                          // ...high 16 bits: 0x32 or 0x19
    xor edx, edx                         // sound index 0
    call {PLAYEX:#x}                     // TSFXLibrary.PlayEx
_out:
    pop ebp
    pop edi
    pop esi
    pop ebx
    movsx eax, byte ptr [esi+0x14]       // replay displaced bytes LAST --
    cmp ax, 7                            // flags feed the jne at CONT
    jmp {CONT:#x}
"""

def cave_src_v5(d_map, d_set, d_cls):
    return f"""
    push ebx
    push esi
    push edi
    push ebp                             // EBP = (volume<<16)|heal after dispatch
    // ---- transport gate (shared, first): heal only on own movement ----
    mov eax, dword ptr [ebx+4]           // unit's owner
    call _a1                             // PIC anchor 1 (EDX scratch)
_a1:
    pop edx
    mov edx, dword ptr [edx{sd(d_cls)}]  // [0x557130AC] -> TArmy classref
    call {ISCLASS:#x}                    // System.@IsClass -> AL
    test al, al
    jz _own                              // owner not a TArmy -> own movement
    mov eax, dword ptr [ebx+4]           // army (EAX clobbered by IsClass)
    mov dl, 0xff
    call {TRANSPORTER:#x}                // TArmy.Transporter -> transporter|0
    test eax, eax
    jz _own                              // no transporter in army
    cmp eax, ebx                         // the transporter is me?
    jne _out                             // carried by another: no heal, no sound
_own:
    // ---- resource index (shared) ----
    mov edx, dword ptr [ebx+0x40]        // resource; null unit-resource -> out
    test edx, edx
    jz _out
    mov eax, dword ptr [edx+4]           // resource list (self)
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x84]            // -> resource index
    // ---- dispatch: EBP = (chime volume << 16) | heal amount ----
    cmp eax, {IDX_AIR_ELEM}
    je _air
    cmp eax, {IDX_EARTH_ELEM}
    je _earth
    cmp eax, {IDX_FIRE_ELEM}
    je _fire
    cmp eax, {IDX_WATER_ELEM}
    jne _out
    mov al, byte ptr [esi+0x14]          // water: terrain Water or uWater
    cmp al, {WATER}
    je _wtr
    cmp al, {UWATER}
    jne _out
_wtr:
    mov ebp, {PACK_WATER:#x}             // heal 2, chime half volume
    jmp _heal
_air:
    cmp byte ptr [esi+0x12], {LVL_SURFACE}   // air: surface level only
    jne _out
    mov ebp, {PACK_AIR:#x}               // heal 1, chime quarter volume
    jmp _heal
_earth:
    cmp byte ptr [esi+0x12], {LVL_SKY}       // v5: Sky (level 3) is NOT underground
    je _out                                  // -- earth elementals never heal there
    cmp byte ptr [esi+0x12], {LVL_SURFACE}   // earth: any underground level...
    jne _ert
    cmp byte ptr [esi+0x15], {OVL_MOUNTAIN}  // ...or Mountain overlay anywhere
    jne _out
_ert:
    mov ebp, {PACK_EARTH:#x}             // heal 1, chime quarter volume
    jmp _heal
_fire:
    cmp byte ptr [esi+0x14], {LAVA}          // fire: Lava terrain
    jne _out
    mov ebp, {PACK_FIRE:#x}              // heal 4, chime half volume
_heal:
    // ---- shared hp/max check + SetHitPoints(hp + heal) ----
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx+0xE0]            // GetHitPoints -> AL (upper bits dirty)
    movsx edi, al
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx+0xD0]            // GetHits (max) -> AL
    movsx eax, al
    cmp edi, eax
    jge _out                             // full HP: no heal -> no sound
    movzx edx, bp                        // heal amount = low 16 bits of pack
    add edx, edi                         // hp + heal
    mov eax, ebx
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0xE4]            // SetHitPoints (clamps to max)
    // ---- shared fog gate + per-elemental-volume Healing chime ----
    call _a2                             // PIC anchor 2 (EDI is dead now)
_a2:
    pop edi
    mov eax, dword ptr [edi{sd(d_map)}]  // AoWHSMap object
    test eax, eax
    jz _out
    movsx ecx, byte ptr [esi+0x12]
    push ecx                             // level  ([ebp+0xC] in callee)
    push 1                               // radius ([ebp+0x8])
    mov dl, byte ptr [esi+0x10]          // x
    mov cl, byte ptr [esi+0x11]          // y
    call {WATCHTERR:#x}                  // WatchingTerrain -> AL
    test al, al
    jz _out                              // fogged: heal stays, sound skipped
    mov eax, dword ptr [edi{sd(d_set)}]  // AoWHSSet object
    test eax, eax
    jz _out
    mov eax, dword ptr [eax+0x80]        // TAbilityControl
    test eax, eax
    jz _out
    mov edx, {ABIL_HEALING}
    call {GETABILITY:#x}                 // GetAbility(ctl, 0x2F)
    test eax, eax
    jz _out
    mov eax, dword ptr [eax+0x18]        // SFX library
    test eax, eax
    jz _out
    push 0                               // loop flag (first-pushed, engine order)
    push 0                               // delay
    push 1
    push 0
    push 0
    mov ecx, ebp                         // volume from the pack...
    shr ecx, 16                          // ...high 16 bits: 0x32 or 0x19
    xor edx, edx                         // sound index 0
    call {PLAYEX:#x}                     // TSFXLibrary.PlayEx
_out:
    pop ebp
    pop edi
    pop esi
    pop ebx
    movsx eax, byte ptr [esi+0x14]       // replay displaced bytes LAST --
    cmp ax, 7                            // flags feed the jne at CONT
    jmp {CONT:#x}
"""

def cave_src_v6(d_map, d_set, d_cls):
    # v6 (2026-09-06): the AIR arm accepts the Firmament (level 3) as well as
    # the surface -- the Firmament IS open sky, and build_maplevel4.py already
    # treats it as surface for vision and for the global-target spell gates.
    # The EARTH arm keeps its v5 level-3 exclusion unchanged.  Only the air arm
    # moves; everything else is v5 verbatim, so the cave simply grows by the
    # one extra compare and its jump.
    return f"""
    push ebx
    push esi
    push edi
    push ebp                             // EBP = (volume<<16)|heal after dispatch
    // ---- transport gate (shared, first): heal only on own movement ----
    mov eax, dword ptr [ebx+4]           // unit's owner
    call _a1                             // PIC anchor 1 (EDX scratch)
_a1:
    pop edx
    mov edx, dword ptr [edx{sd(d_cls)}]  // [0x557130AC] -> TArmy classref
    call {ISCLASS:#x}                    // System.@IsClass -> AL
    test al, al
    jz _own                              // owner not a TArmy -> own movement
    mov eax, dword ptr [ebx+4]           // army (EAX clobbered by IsClass)
    mov dl, 0xff
    call {TRANSPORTER:#x}                // TArmy.Transporter -> transporter|0
    test eax, eax
    jz _own                              // no transporter in army
    cmp eax, ebx                         // the transporter is me?
    jne _out                             // carried by another: no heal, no sound
_own:
    // ---- resource index (shared) ----
    mov edx, dword ptr [ebx+0x40]        // resource; null unit-resource -> out
    test edx, edx
    jz _out
    mov eax, dword ptr [edx+4]           // resource list (self)
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x84]            // -> resource index
    // ---- dispatch: EBP = (chime volume << 16) | heal amount ----
    cmp eax, {IDX_AIR_ELEM}
    je _air
    cmp eax, {IDX_EARTH_ELEM}
    je _earth
    cmp eax, {IDX_FIRE_ELEM}
    je _fire
    cmp eax, {IDX_WATER_ELEM}
    jne _out
    mov al, byte ptr [esi+0x14]          // water: terrain Water or uWater
    cmp al, {WATER}
    je _wtr
    cmp al, {UWATER}
    jne _out
_wtr:
    mov ebp, {PACK_WATER:#x}             // heal 2, chime half volume
    jmp _heal
_air:
    cmp byte ptr [esi+0x12], {LVL_SURFACE}   // air: the surface level...
    je _airok
    cmp byte ptr [esi+0x12], {LVL_SKY}       // v6: ...or the Firmament (level 3)
    jne _out
_airok:
    mov ebp, {PACK_AIR:#x}               // heal 1, chime quarter volume
    jmp _heal
_earth:
    cmp byte ptr [esi+0x12], {LVL_SKY}       // v5: the Firmament is NOT underground
    je _out                                  // -- earth elementals never heal there
    cmp byte ptr [esi+0x12], {LVL_SURFACE}   // earth: any underground level...
    jne _ert
    cmp byte ptr [esi+0x15], {OVL_MOUNTAIN}  // ...or Mountain overlay anywhere
    jne _out
_ert:
    mov ebp, {PACK_EARTH:#x}             // heal 1, chime quarter volume
    jmp _heal
_fire:
    cmp byte ptr [esi+0x14], {LAVA}          // fire: Lava terrain
    jne _out
    mov ebp, {PACK_FIRE:#x}              // heal 4, chime half volume
_heal:
    // ---- shared hp/max check + SetHitPoints(hp + heal) ----
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx+0xE0]            // GetHitPoints -> AL (upper bits dirty)
    movsx edi, al
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx+0xD0]            // GetHits (max) -> AL
    movsx eax, al
    cmp edi, eax
    jge _out                             // full HP: no heal -> no sound
    movzx edx, bp                        // heal amount = low 16 bits of pack
    add edx, edi                         // hp + heal
    mov eax, ebx
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0xE4]            // SetHitPoints (clamps to max)
    // ---- shared fog gate + per-elemental-volume Healing chime ----
    call _a2                             // PIC anchor 2 (EDI is dead now)
_a2:
    pop edi
    mov eax, dword ptr [edi{sd(d_map)}]  // AoWHSMap object
    test eax, eax
    jz _out
    movsx ecx, byte ptr [esi+0x12]
    push ecx                             // level  ([ebp+0xC] in callee)
    push 1                               // radius ([ebp+0x8])
    mov dl, byte ptr [esi+0x10]          // x
    mov cl, byte ptr [esi+0x11]          // y
    call {WATCHTERR:#x}                  // WatchingTerrain -> AL
    test al, al
    jz _out                              // fogged: heal stays, sound skipped
    mov eax, dword ptr [edi{sd(d_set)}]  // AoWHSSet object
    test eax, eax
    jz _out
    mov eax, dword ptr [eax+0x80]        // TAbilityControl
    test eax, eax
    jz _out
    mov edx, {ABIL_HEALING}
    call {GETABILITY:#x}                 // GetAbility(ctl, 0x2F)
    test eax, eax
    jz _out
    mov eax, dword ptr [eax+0x18]        // SFX library
    test eax, eax
    jz _out
    push 0                               // loop flag (first-pushed, engine order)
    push 0                               // delay
    push 1
    push 0
    push 0
    mov ecx, ebp                         // volume from the pack...
    shr ecx, 16                          // ...high 16 bits: 0x32 or 0x19
    xor edx, edx                         // sound index 0
    call {PLAYEX:#x}                     // TSFXLibrary.PlayEx
_out:
    pop ebp
    pop edi
    pop esi
    pop ebx
    movsx eax, byte ptr [esi+0x14]       // replay displaced bytes LAST --
    cmp ax, 7                            // flags feed the jne at CONT
    jmp {CONT:#x}
"""

# two-pass assembly: pass 1 with disp32-forcing placeholders locates the
# call/pop anchors, pass 2 bakes the real deltas.  Lengths must match.
PH_MAP, PH_SET, PH_CLS = 0x7F7F7F70, 0x7F7F7F74, -0x7F7F7F0

def build_gated(src_fn):
    p1, _ = ks.asm(src_fn(PH_MAP, PH_SET, PH_CLS), CAVE)
    p1 = bytes(p1)
    i1 = p1.find(b"\xe8\x00\x00\x00\x00")            # call _a1
    assert i1 != -1, "call _a1 anchor not found"
    i2 = p1.find(b"\xe8\x00\x00\x00\x00", i1 + 5)    # call _a2
    assert i2 != -1, "call _a2 anchor not found"
    a1 = CAVE + i1 + 5                               # VA of pop edx
    a2 = CAVE + i2 + 5                               # VA of pop edi
    d_cls = CLS_VAR - a1
    d_map, d_set = MAP_VAR - a2, SET_VAR - a2
    assert d_cls < -0x80, "gate delta must be disp32-sized"
    assert d_map > 0x7F and d_set > 0x7F, "deltas must be disp32-sized"
    p2, _ = ks.asm(src_fn(d_map, d_set, d_cls), CAVE)
    p2 = bytes(p2)
    assert len(p2) == len(p1), "pass-2 length drift -- placeholder not disp32"
    return p2, a1, a2

def build_v6(): return build_gated(cave_src_v6)
def build_v5(): return build_gated(cave_src_v5)   # frozen -- recognition only
def build_v4(): return build_gated(cave_src_v4)   # frozen -- recognition only
def build_v3(): return build_gated(cave_src_v3)   # frozen -- recognition only
def build_v2(): return build_gated(cave_src)      # frozen -- recognition only

def build_v1():
    p1, _ = ks.asm(cave_src(PH_MAP, PH_SET), CAVE)
    p1 = bytes(p1)
    i = p1.find(b"\xe8\x00\x00\x00\x00")
    assert i != -1, "v1 anchor not found"
    a = CAVE + i + 5
    p2, _ = ks.asm(cave_src(MAP_VAR - a, SET_VAR - a), CAVE)
    p2 = bytes(p2)
    assert len(p2) == len(p1), "v1 pass-2 length drift"
    return p2

cave_v6, ANCHOR1_VA, ANCHOR2_VA = build_v6()
cave_v5, _, _ = build_v5()
cave_v4, _, _ = build_v4()
cave_v3, _, _ = build_v3()
cave_v2, _, _ = build_v2()
cave_v1 = build_v1()
LEN6, LEN5, LEN4, LEN3, LEN2, LEN1 = (len(cave_v6), len(cave_v5), len(cave_v4),
                                      len(cave_v3), len(cave_v2), len(cave_v1))
assert LEN6 > LEN5 > LEN4 > LEN3 > LEN2 > LEN1
assert CAVE + LEN6 <= 0x55825200, "cave outgrew the verified-zero zone"

def rel32(src, dst): return struct.pack("<i", dst - (src + 5))
hook_new = b"\xE9" + rel32(HOOK, CAVE) + b"\x90\x90\x90"
assert len(hook_new) == len(HOOK_ORIG) == 8

# ---- PE section mapping ------------------------------------------------------
def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e + 6)[0]
    optsize = struct.unpack_from("<H", data, e + 20)[0]
    sec = e + 24 + optsize
    secs = []
    for _ in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", data, sec + 8)
        secs.append((vaddr, vsize, raw, rsize)); sec += 40
    return secs

def va2off(secs, va):
    rva = va - DLL_BASE
    for vaddr, vsize, raw, rsize in secs:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
    raise ValueError(f"VA {va:08X} not mapped")

def disasm(code, va):
    for ins in cs.disasm(code, va):
        print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<24} {ins.mnemonic} {ins.op_str}")

# ---- modes -------------------------------------------------------------------
APPLY = "--apply" in sys.argv
UNDO  = "--undo" in sys.argv
DIS   = "--dis" in sys.argv or "--show" in sys.argv
assert not (APPLY and UNDO), "pick one of --apply / --undo"

print(f"cave @ {CAVE:08X}  (v6 {LEN6} B, v5 {LEN5} B, v4 {LEN4} B, v3 {LEN3} B, "
      f"v2 {LEN2} B, v1 {LEN1} B)"
      f"   anchors: pop edx @ {ANCHOR1_VA:08X}, pop edi @ {ANCHOR2_VA:08X}")
if DIS:
    print("--- cave_elemheal v6 ---")
    disasm(cave_v6, CAVE)
    print("--- hook ---")
    disasm(hook_new, HOOK)
    sys.exit(0)

data = bytearray(open(DLL, "rb").read())
secs = load_sections(data)
def rd(va, n):
    o = va2off(secs, va); return bytes(data[o:o + n])
def wr(va, b):
    o = va2off(secs, va); data[o:o + len(b)] = b

cur_hook = rd(HOOK, len(HOOK_ORIG))
cur_cave = rd(CAVE, LEN6)                # read the FULL v6-sized region
zero6    = bytes(LEN6)

vanilla    = cur_hook == HOOK_ORIG and cur_cave == zero6
applied_v1 = (cur_hook == hook_new and cur_cave[:LEN1] == cave_v1
              and cur_cave[LEN1:] == bytes(LEN6 - LEN1))  # growth zone zero
applied_v2 = (cur_hook == hook_new and cur_cave[:LEN2] == cave_v2
              and cur_cave[LEN2:] == bytes(LEN6 - LEN2))  # growth zone zero
applied_v3 = (cur_hook == hook_new and cur_cave[:LEN3] == cave_v3
              and cur_cave[LEN3:] == bytes(LEN6 - LEN3))  # growth zone zero
applied_v4 = (cur_hook == hook_new and cur_cave[:LEN4] == cave_v4
              and cur_cave[LEN4:] == bytes(LEN6 - LEN4))  # growth zone zero
applied_v5 = (cur_hook == hook_new and cur_cave[:LEN5] == cave_v5
              and cur_cave[LEN5:] == bytes(LEN6 - LEN5))  # growth zone zero
applied_v6 = cur_hook == hook_new and cur_cave == cave_v6

def state():
    if vanilla:    return "VANILLA (hook original, cave zero)"
    if applied_v1: return "V1 APPLIED (water only, no gate; growth zone zero)"
    if applied_v2: return "V2 APPLIED (water only + gate; growth zone zero)"
    if applied_v3: return "V3 APPLIED (all four, flat volume; growth zone zero)"
    if applied_v4: return "V4 APPLIED (all four, per-elemental chime volume; growth zone zero)"
    if applied_v5: return "V5 APPLIED (v4 + earth elementals skip the Firmament)"
    if applied_v6: return "V6 APPLIED (v5 + AIR elementals heal on the Firmament)"
    return ("UNRECOGNISED -- hook %s, cave %s" % (
        "original" if cur_hook == HOOK_ORIG else
        "patched" if cur_hook == hook_new else "OTHER: " + cur_hook.hex(" "),
        "zero" if cur_cave == zero6 else "OTHER (first 16: %s)" % cur_cave[:16].hex(" ")))

def save():
    try:
        open(DLL, "wb").write(data)
    except PermissionError:
        print("[x] AoWEPACK.dpl LOCKED -- kill AoW/AoWCompat/AoWDevEd/AoWEd and retry")
        sys.exit(1)

print(f"state: {state()}")

if UNDO:
    if vanilla:
        print("[= ] already vanilla -- nothing to undo"); sys.exit(0)
    if not (applied_v1 or applied_v2 or applied_v3 or applied_v4 or applied_v5
            or applied_v6):
        print("[x] unrecognised state -- refusing to undo blind"); sys.exit(1)
    wr(HOOK, HOOK_ORIG); wr(CAVE, zero6)   # zero the FULL v6 length
    save()
    print(f"[w ] hook {HOOK:08X} restored ({len(HOOK_ORIG)} B); cave {CAVE:08X} zeroed ({LEN6} B)")
    print("[ok] surgical undo complete -- no backup touched")
    sys.exit(0)

if applied_v6:
    print("[= ] already applied (v6)"); sys.exit(0)
if not (vanilla or applied_v1 or applied_v2 or applied_v3 or applied_v4
        or applied_v5):
    print("[x] originals mismatch -- not written"); sys.exit(1)
if not APPLY:
    print("[dry] site verified (%s) -- re-run with --apply to write"
          % ("vanilla" if vanilla else
             "v1, in-place rewrite" if applied_v1 else
             "v2, in-place rewrite" if applied_v2 else
             "v3, in-place rewrite" if applied_v3 else
             "v4, in-place rewrite" if applied_v4 else
             "v5, in-place rewrite"))
    sys.exit(0)

# backup gate: ONLY from the byte-proven vanilla state, and only if absent.
# From the v1/v2/v3 states the current file is this feature's own previous
# output -- NOT vanilla -- so no backup is minted (the existing .pre-waterheal,
# taken from proven-vanilla at first install, stays untouched).
if not os.path.exists(BACKUP) and proven_pristine():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    shutil.copy2(DLL, BACKUP); print(f"[bak] {os.path.basename(BACKUP)}")
elif not os.path.exists(BACKUP):
    print("[bak] skipped -- the live DLL is not byte-identical to the pristine "
          "reference, so a snapshot of it would prove nothing")
wr(HOOK, hook_new); wr(CAVE, cave_v6)
save()
print(f"[w ] hook {HOOK:08X} -> jmp {CAVE:08X} + 3 NOP")
print(f"[w ] cave {CAVE:08X} ({LEN6} B, v6 elemheal: air heals on the Firmament, "
      f"earth still does not)"
      + ("" if vanilla else
         " -- rewrote %s in place" % (
             "v1 (%d B)" % LEN1 if applied_v1 else
             "v2 (%d B)" % LEN2 if applied_v2 else
             "v3 (%d B)" % LEN3 if applied_v3 else
             "v4 (%d B)" % LEN4 if applied_v4 else
             "v5 (%d B)" % LEN5)))
print("[done] applied, untested -- needs the user's in-game check")
