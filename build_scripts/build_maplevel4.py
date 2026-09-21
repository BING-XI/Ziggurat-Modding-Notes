#!/usr/bin/env python3
r"""
AoW1 mod -- the FIRMAMENT: a FOURTH map level, index 3, filled with Sky
terrain (0x0E) and treated as SURFACE by the rules that matter.

DISPLAY NAME: **Firmament**.  The script filename predates the naming ruling
and is left alone; every user-visible string says "Firmament", deliberately
distinct from the Sky *terrain* (id 0x0E) that fills it.  The level-strip
caption literal lives in the exes and belongs to build_skylevel_ui.py.

Target: AoWEPACK.dpl ONLY.  The AoW.exe / AoWCompat.exe world-map level-strip
UI is a separate feature (build_skylevel_ui.py, exe cave 0x0062A000); this
script does not touch either exe.

USER RULINGS BAKED IN (2026-09-06)
  * The Firmament is level INDEX 3.  Display order is the UI half's problem.
  * Vision: the Firmament counts as SURFACE -- unhalved, and no Night Vision
    needed.  BOTH `VisibilityRange` level compares flip.
  * Global-target spells are ALLOWED from the Firmament (the "cannot cast
    underground" gate gets the same surface-or-firmament predicate).
  * v2 (2026-09-06): STORM SPELLS and BIRD'S VIEW follow the same global-target
    ruling -- castable while viewing the Firmament, still refused on Caverns
    and Depths.  Three more gates, section F below.
  * Towers are BUILDABLE on the Firmament, and on every other level, because
    TTowerConstructionControl.CanConstruct @0x557C38D4 has no live level gate
    left: its `cmp byte [ebp-3],0` at 0x557C390D is followed by `90 90` where
    the pristine DLL has `jne 0x557C3922`, so the result is discarded.  This
    script deliberately does not touch the function -- but "not touched" does
    NOT mean "still blocked", and an earlier version of this note said it did.
    The NOP pair is an undocumented pre-convention live edit owned by no build
    script.  Byte-compared against AoWEPACK_original_backup.dpl 2026-09-09.
  * The 6-hex border ring (terrain 0x0F) stays on the Firmament, like every
    other level.
  * Earth elementals do NOT heal on the Firmament, and (v6, 2026-09-06) AIR
    elementals DO -- both live in build_waterheal.py (cave 0x55824000), not
    here.  See the FORWARD HAZARD below.

NO RANDOM DRAWS.  Not one block in this cave rolls anything, so neither RNG is
involved and `rng_audit.py --owners` is unchanged by this feature.

================================================================================
WHAT IS PATCHED  (every byte below read LIVE with re_tools/dasm.py, 2026-09-06;
                  every displaced range checked .reloc-free)
================================================================================
A. THE CAP BYTE -- 1 byte, no cave
   TAoWHSMap.AddMapLevel @0x55777684
     5577768B  83 7E 14 03   cmp dword ptr [esi+0x14], 3
     5577768F  jge <bail>
   The imm8 at 0x5577768E (file 0x76A8E) is the level ceiling: `>= 3 -> refuse`.
   03 -> 04.  Nothing else in the DLL encodes the ceiling.

B. THE FIRMAMENT FILL -- hook @0x5577747E -> cave_fillterr
   TAoWHSMap.InitializeMapLevel @0x557773CC (EAX=map, DL=level) has two arms:
   level 0 fills the interior with Water(0) inset 6; every other level fills the
   interior with EarthWall(7) from 1..w-7.  Both arms then fall into the shared
   6-hex border ring at terrain 0x0F.
   The `!= 0` arm's inner loop, live:
     55777479  53              push ebx          ; loop entry -- back-jump target
     5577747A  8A 44 24 08     mov  al, [esp+8]  ; AL = the level parameter
     5577747E  50              push eax          ; param5 = level
     5577747F  6A 07           push 7            ; param6 = TERRAIN  <-- the knob
     55777481  8B CE           mov  ecx, esi
     55777483  8B 44 24 0C     mov  eax, [esp+0xC]
     ...       call [ebp+0x50]                   ; SetTerrain-alike
   The param order was read off the level-0 arm (`push ebx / push 0 / push 0` --
   level 0, terrain 0 = water) and off the ring (`push ebx / push al / push 0xF`),
   so param6 is unambiguously the terrain byte.
   AL ALREADY HOLDS THE LEVEL one instruction before the terrain push, which is
   why the hook sits at 0x5577747E and not at the push itself: 0x5577747E..82
   (`50 6A 07 8B CE`) is exactly 5 bytes -- one E9, nothing displaced twice, and
   the cave never has to re-read the stack.  Resumes at 0x55777483.
   ⚠ 0x55777479 (the loop's back-jump target) is BEFORE the hook and untouched.

C. THE VISION PREDICATE -- two hooks -> cave_vis1 / cave_vis2
   TAbstractUnit.VisibilityRange @0x55780EF8, live:
     55780F2D  call TAbstractUnit.GetLocation   ; locals: [esp]=x [esp+1]=y [esp+2]=level
     55780F32  80 7C 24 02 00  cmp byte [esp+2], 0
     55780F37  74 13           je  0x55780F4C     ; surface -> skip the Night Vision test
     55780F39  ...             GetAbility(0x27)   ; underground: need Night Vision
     55780F4A  74 2A           je  0x55780F76     ; ...else HALVE
     55780F4C  80 7C 24 02 00  cmp byte [esp+2], 0
     55780F51  75 26           jne 0x55780F79     ; underground -> done, no halve
     55780F53  ...             surface: player flag bit 3 -> halve
     55780F76  46 / D1 EE      inc esi ; shr esi,1
   Each 5-byte compare becomes `E9 -> cave`.  The cave sets ZF exactly as the
   compare would for levels 0/1/2 and ADDITIONALLY sets ZF for level 3 (the
   Firmament), then
   jumps back to the je/jne that follows.  `pop` does not touch flags, which is
   what makes the save/restore of EAX free:
       push eax
       movzx eax, byte [esp+6]     ; +2 for the local, +4 for the push
       cmp  eax, 3
       jne  .l                     ; level 3 -> force EAX 0 so the test sets ZF
       xor  eax, eax
     .l: test eax, eax             ; ZF = (level == 0 or level == 3)
       pop  eax
       jmp  <the je/jne>
   ⚠ build_vision9.py owns 0x55780F12 in this same function (the `add esi,3`
   ceiling site).  Different bytes, no overlap -- but do not let the two scripts'
   verify ranges drift into each other.

D. THE GLOBAL-TARGET SPELL GATE -- hook @0x5579E78B -> cave_spellgate
   GlobalTargetSpells.TGlobalTargetSpell.CanActivate @0x5579E73C, live:
     5579E786  call TAbstractUnit.GetLocation   ; [ebp-7] = level
     5579E78B  80 7D F9 00     cmp byte [ebp-7], 0
     5579E78F  74 25           je  0x5579E7B6   ; surface -> allowed
     5579E791  xor ebx, ebx                     ; underground -> refuse +
     5579E793  ...             LoadResString CannotCastSpellInUndergound...
   The compare is the disp8 form (FOUR bytes), so the hook takes cmp+je = 6
   bytes: E9 rel32 + one 0x90.  The cave computes the same
   surface-or-Firmament predicate and jumps to 0x5579E7B6 (allow) or
   0x5579E791 (refuse) itself.
   ⚠ The reloc'd `mov eax,[0x558E8FE4]` at 0x5579E796 is well clear of the
   displaced range; the range itself carries no .reloc entry (checked).

E. TCave.PlaceHX GUARD -- hook @0x557B36BB -> cave_placeguard
   Cave.TCave.PlaceHX @0x557B3670 pairs a cave with a twin on the neighbouring
   level.  [esi+0x30] is the polarity flag: 1 = upper mouth, twin at level+1;
   0 = lower mouth, twin at level-1.
     557B36B1  cmp byte [esi+0x30], 1
     557B36B5  jne 0x557B373D                 ; the flag-0 (twin at level-1) arm
     557B36BB  0F BE 45 08     movsx eax, byte [ebp+8]   ; [ebp+8] = the level
     557B36BF  40              inc eax                   ; twin at level+1
     557B36C0  50              push eax  ; -> GetField(map, x, y, level+1)
   With four levels, a flag-1 cave placed on level 2 would now SUCCEED in
   digging its twin into the Firmament.  The guard blocks level >= 2 outright:
       movsx eax, byte [ebp+8]
       cmp   eax, 2
       jge   .block
       inc   eax
       jmp   0x557B36C0
     .block:
       xor   ebx, ebx
       jmp   0x557B37BA        ; mov eax,ebx / pop esi / pop ebx / leave / ret 8
   0x557B37BA is the function's single epilogue and returns EBX, so EBX=0 is
   "placement failed" -- byte-identical in shape to the engine's OWN failure
   return at 0x557B372F.  Nothing is half-created: the guard fires BEFORE the
   twin is allocated.

   ⚠ DEVIATION FROM THE SPEC, and the reason.  The spec proposed bailing to
   0x557B373D (the flag-0 arm).  That is not a bail-out, it is the MIRROR arm,
   and the two arms are not interchangeable: each one's "twin already exists"
   branch asserts the OPPOSITE polarity on the twin it finds
   (flag-1 arm 0x557B371A `cmp [twin+0x30],0 / sete bl`; flag-0 arm 0x557B379C
   `cmp [twin+0x30],1 / sete bl`).  Sending a flag-1 object down the flag-0 arm
   makes it create a twin at level-1 that ALSO carries flag 1; that twin's own
   PlaceHX (VMT slot +0x118) then finds the original, sees the wrong polarity,
   `sete bl` -> 0, and DESTROYS it via [vmt-4].  A guard that destroys the cave
   it was protecting is worse than the bug.  Hence the clean failure return.

F. STORM SPELLS + BIRD'S VIEW -- v2, three more gates (2026-09-06 ruling)
   All three are the SAME instruction pair as section D, in the SAME operand
   form (`80 7D F9 00` -- byte [ebp-7], filled by a
   TAbstractUnit.GetLocation(EAX=unit, EDX=&x, ECX=&y, [esp]=&level) call a few
   instructions earlier), so each takes a 6-byte E9+0x90 hook and its own stub.
   The stubs cannot be shared with cave_spellgate: the predicate is identical
   but the two branch targets differ per site, and they are baked as rel32
   tails.  Live bytes read with dasm.py 2026-09-06; all three ranges carry no
   .reloc entry (63883-entry scan, none within +/-3 bytes).

     site                                        displaced      allow / deny
     Storms.TStormSpell.CanActivate
       @0x557CDCC8   80 7D F9 00 74 25           cmp+je 6 B     0x557CDCF3 /
                                                                0x557CDCCE
     Storms.TStormSpell.AICastSpellPriority
       @0x557CDF88   80 7D F9 00 75 66           cmp+jne 6 B    0x557CDF8E /
                                                                0x557CDFF4
     GlobalSpells.TBirdsView.CanActivate
       @0x557EAB90   80 7D F9 00 74 25           cmp+je 6 B     0x557EABBB /
                                                                0x557EAB96

   ⚠ The AI site's polarity is INVERTED (jne, not je): "underground" is the
   JUMP there, and the target 0x557CDF8E is simply the fall-through address.
   Its deny target 0x557CDFF4 is the finally-epilogue, entered with EDI = -1
   from `or edi,0xFFFFFFFF` @0x557CDF74 -- i.e. the engine's own "no priority"
   return.  Jumping to 0x557CDFF1 instead would re-execute that `or` harmlessly
   but is one byte further from the shape the vanilla code uses; the stub uses
   0x557CDFF4 so the deny path is byte-for-byte the vanilla one.
   ⚠ Both CanActivate sites' allow target skips a `xor ebx,ebx` as well as the
   CannotCastSpellInUndergound message -- EBX is the return value, so falling
   through would refuse the cast AND leave the message set.  The stubs jump to
   the je target, never to the compare's fall-through.

================================================================================
LEFT ALONE ON PURPOSE -- these keep reading `level != 0` as "underground"
================================================================================
  Path of Life / Path of Decay   0x557801A4 / 0x557801C4
  Raise Terrain's underground arm, the terrain-change and road gates
  Air- and Earth-elemental healing  build_waterheal.py cave 0x55824000
  TCombatUnit.GetVisibilityRange 0x55724AD0 -- NOT level-derived at all; it
    halves on `cmp byte [combat+0x40], 1`, and [TCombat+0x40] is the combat KIND
    (1 = exploration-site interior, written at TExplorationSite.SetupCombat
    0x557C1A17; 2 = default armies, TCombat.InitDefaultArmies 0x55727BF5), read
    the same way by TAoWHSMap.DestroyCombat 0x5577894D.  A Firmament field
    battle is kind 2 and already gets full tactical vision.  No patch needed.

NOT in the list above, because its gate no longer reads anything:
  TTowerConstructionControl.CanConstruct 0x557C38D4 -- `cmp byte [ebp-3],0` at
    0x557C390D is followed by `90 90` where the pristine DLL has `jne
    0x557C3922`, so towers build on EVERY level, Firmament included.  An
    undocumented pre-convention live edit; no build script owns those two bytes.

⚠ FORWARD HAZARD -- build_waterheal.py cave 0x55824000 and this script both
  encode the level-3 predicate.  Re-applying an OLD revision of waterheal alone
  reverts the Earth-elemental Firmament skip (v5) and the Air-elemental
  Firmament heal (v6) without touching anything here, and nothing in this
  script will notice.

================================================================================
CAVE 0x55844000..0x558443FF
================================================================================
Verified all-zero on disk (0x55843E00..0x558445FF is clear) and unclaimed:
the nearest neighbours in build_scripts/ are 0x55843000 and 0x55846000.
CODE section, so file offset = VA - 0x55700C00.

POSITION INDEPENDENCE: mandatory (AoWEPACK.dpl never loads at its preferred
base).  This cave needs NO globals at all -- every block is register/stack-only
plus rel32 jumps back into the module, so there is not one absolute memory
operand and no call/pop anchor is required.  Asserted at build time by scanning
the capstone listing of every block for a `0x55......` memory operand.

RE-TUNE IN PLACE (project convention -- never revert-and-reapply).  v2 appends
its three stubs AFTER the five v1 blocks, so every v1 hook still points at the
same address and the v1 hook bytes are unchanged.  --apply therefore accepts
either the vanilla state or the installed v1 state (five v1 hooks patched,
three v2 sites still original, cave[:v1 len] == the regenerated v1 payload,
everything past it zero) and rewrites the cave in place.  A no-arg run over an
installed v1 reports "NEEDS RE-TUNE", never "applied".  --undo restores all
NINE sites -- v1's and v2's -- and zeroes the whole v2 length.

Usage:
  no args   dry run: verify + report the state of all nine sites
  --apply   patch (verify-before-write; backup only from proven-vanilla;
            in-place rewrite from an installed v1)
  --undo    surgical: cap byte 04->03, restore all eight hook sites, zero the
            emitted cave.  No backup touched.
  --dis / --show   capstone-disassemble every block and every hook, exit
"""
import os
import struct
import sys
import shutil

from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script; AOW_GAME_DIR overrides.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-maplevel4")

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


ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

DLL_BASE = 0x55700000

SKY_LEVEL = 3          # the Firmament level index (user ruling)
SKY_TERRAIN = 0x0E     # build_chasm_sky_movement.py: 0x0E = SKY, 0x0B = CHASM
WALL_TERRAIN = 0x07    # EarthWall -- what every non-surface level fills with

# ---- A. the cap byte --------------------------------------------------------
CAP_VA = 0x5577768B                                # cmp dword [esi+0x14], 3
CAP_ORIG = bytes.fromhex("837E1403")
CAP_NEW = bytes.fromhex("837E1404")
CAP_IMM_VA = 0x5577768E                            # the imm8 itself (file 0x76A8E)

# ---- B..E. the five hook sites ----------------------------------------------
FILL_HOOK = 0x5577747E
FILL_ORIG = bytes.fromhex("506A078BCE")            # push eax; push 7; mov ecx,esi
FILL_CONT = 0x55777483

VIS1_HOOK = 0x55780F32
VIS1_ORIG = bytes.fromhex("807C240200")            # cmp byte [esp+2], 0
VIS1_CONT = 0x55780F37                             # the je

VIS2_HOOK = 0x55780F4C
VIS2_ORIG = bytes.fromhex("807C240200")
VIS2_CONT = 0x55780F51                             # the jne

SPELL_HOOK = 0x5579E78B
SPELL_ORIG = bytes.fromhex("807DF9007425")         # cmp byte [ebp-7],0 ; je +0x25
SPELL_ALLOW = 0x5579E7B6                           # the je target: allowed
SPELL_DENY = 0x5579E791                            # fall-through: refuse + message

PLACE_HOOK = 0x557B36BB
PLACE_ORIG = bytes.fromhex("0FBE450840")           # movsx eax,[ebp+8] ; inc eax
PLACE_CONT = 0x557B36C0                            # push eax
PLACE_FAIL = 0x557B37BA                            # mov eax,ebx / epilogue / ret 8
PLACE_MAXLEVEL = 2                                 # level >= 2 -> no twin above

# ---- F. v2 (2026-09-06): storm spells + Bird's View -------------------------
# All three are `cmp byte [ebp-7],0` + a 2-byte conditional jump = 6 displaced
# bytes, exactly like SPELL_HOOK.  ALLOW / DENY are absolute VAs the stub jumps
# to itself, so each site needs its own stub even though the predicate is shared.
STORM_HOOK = 0x557CDCC8                            # Storms.TStormSpell.CanActivate
STORM_ORIG = bytes.fromhex("807DF9007425")         # cmp byte [ebp-7],0 ; je +0x25
STORM_ALLOW = 0x557CDCF3
STORM_DENY = 0x557CDCCE

STORMAI_HOOK = 0x557CDF88                    # Storms.TStormSpell.AICastSpellPriority
STORMAI_ORIG = bytes.fromhex("807DF9007566")       # cmp byte [ebp-7],0 ; jne +0x66
STORMAI_ALLOW = 0x557CDF8E                         # fall-through (INVERTED polarity)
STORMAI_DENY = 0x557CDFF4                          # epilogue with EDI = -1

BIRD_HOOK = 0x557EAB90                       # GlobalSpells.TBirdsView.CanActivate
BIRD_ORIG = bytes.fromhex("807DF9007425")          # cmp byte [ebp-7],0 ; je +0x25
BIRD_ALLOW = 0x557EABBB
BIRD_DENY = 0x557EAB96

CAVE = 0x55844000
CAVE_LIMIT = 0x400
CAVE_ZERO_END = 0x55844600                         # verified all-zero to here

# (label, VA, original bytes, replacement, generation) -- generation 1 sites
# carry identical bytes in v1 and v2, so only the generation-2 sites separate
# an installed v1 from an installed v2.
SITES = [
    ("cap byte  ", CAP_VA, CAP_ORIG, CAP_NEW, 1),
]


# ---- cave source ------------------------------------------------------------
def src_fillterr():
    return f"""
    push eax                              // param5 = level (AL is already it)
    movzx ecx, al                         // ECX is dead: `mov ecx,esi` follows
    cmp  ecx, {SKY_LEVEL}
    je   _sky
    push {WALL_TERRAIN}                   // param6 = terrain: EarthWall
    jmp  _cont
_sky:
    push {SKY_TERRAIN}                    // param6 = terrain: Sky
_cont:
    mov  ecx, esi                         // displaced tail
    jmp  {FILL_CONT:#x}
"""


def src_issurf(cont_va):
    """ZF := (level == 0 or level == SKY_LEVEL), level byte at [esp+2] pre-push."""
    return f"""
    push eax
    movzx eax, byte ptr [esp+6]           // +2 local, +4 for the push above
    cmp  eax, {SKY_LEVEL}
    jne  _t
    xor  eax, eax                         // Sky: make the test below set ZF
_t:
    test eax, eax
    pop  eax                              // pop does not touch flags
    jmp  {cont_va:#x}
"""


def src_spellgate(allow_va=None, deny_va=None):
    """`byte [ebp-7]` level gate: allow on surface (0) or the Firmament (3).

    Shared by the four "cannot cast underground" sites -- they differ only in
    where allow/deny go, and those are rel32 tails, so each needs its own copy.
    Default arguments reproduce the v1 global-target-spell stub BYTE FOR BYTE
    (its recognition depends on that; do not change the body)."""
    allow_va = SPELL_ALLOW if allow_va is None else allow_va
    deny_va = SPELL_DENY if deny_va is None else deny_va
    return f"""
    push eax
    movzx eax, byte ptr [ebp-7]           // frame-based: no esp adjustment
    cmp  eax, {SKY_LEVEL}
    jne  _t
    xor  eax, eax
_t:
    test eax, eax
    pop  eax
    je   {allow_va:#x}                    // surface or Firmament -> allowed
    jmp  {deny_va:#x}                     // underground -> refuse + message
"""


def src_placeguard():
    return f"""
    movsx eax, byte ptr [ebp+8]           // displaced: the level parameter
    cmp   eax, {PLACE_MAXLEVEL}
    jge   _block                          // level+1 would be Sky (or off-map)
    inc   eax                             // displaced: twin one level down
    jmp   {PLACE_CONT:#x}
_block:
    xor   ebx, ebx                        // EBX is the return value
    jmp   {PLACE_FAIL:#x}                 // the function's own epilogue
"""


# ⚠ The five v1 block sources are FROZEN: their assembled bytes must stay
# identical to what v1 wrote, or --apply can no longer recognise an installed
# v1 and the in-place rewrite turns into a blind overwrite.  v2's three stubs
# are APPENDED, never interleaved, so every v1 block keeps its address.
V1_BLOCKS = ["fillterr", "vis1", "vis2", "spellgate", "placeguard"]


def build():
    """Assemble every block at its final VA.  Nothing is position-dependent, so
    one pass is enough -- but the result is still disassembled and scanned."""
    blocks = [
        ("fillterr", src_fillterr()),
        ("vis1", src_issurf(VIS1_CONT)),
        ("vis2", src_issurf(VIS2_CONT)),
        ("spellgate", src_spellgate()),
        ("placeguard", src_placeguard()),
        # ---- v2, 2026-09-06 ----
        ("stormcast", src_spellgate(STORM_ALLOW, STORM_DENY)),
        ("stormai", src_spellgate(STORMAI_ALLOW, STORMAI_DENY)),
        ("birdsview", src_spellgate(BIRD_ALLOW, BIRD_DENY)),
    ]
    out = {}
    order = []
    va = CAVE
    for name, src in blocks:
        code, _ = ks.asm(src, va)
        code = bytes(code)
        out[name] = (va, code)
        order.append(name)
        va = (va + len(code) + 0xF) & ~0xF          # 16-byte align the next block
    out["_order"] = order
    out["_end"] = out[order[-1]][0] + len(out[order[-1]][1])
    last1 = V1_BLOCKS[-1]
    out["_v1end"] = out[last1][0] + len(out[last1][1])
    return out


def rel32(src, dst):
    return struct.pack("<i", dst - (src + 5))


CAVE_BLOCKS = build()
HOOKS = [
    ("fill      ", FILL_HOOK, FILL_ORIG, CAVE_BLOCKS["fillterr"][0], 1),
    ("vis1      ", VIS1_HOOK, VIS1_ORIG, CAVE_BLOCKS["vis1"][0], 1),
    ("vis2      ", VIS2_HOOK, VIS2_ORIG, CAVE_BLOCKS["vis2"][0], 1),
    ("spellgate ", SPELL_HOOK, SPELL_ORIG, CAVE_BLOCKS["spellgate"][0], 1),
    ("placehx   ", PLACE_HOOK, PLACE_ORIG, CAVE_BLOCKS["placeguard"][0], 1),
    ("stormcast ", STORM_HOOK, STORM_ORIG, CAVE_BLOCKS["stormcast"][0], 2),
    ("stormai   ", STORMAI_HOOK, STORMAI_ORIG, CAVE_BLOCKS["stormai"][0], 2),
    ("birdsview ", BIRD_HOOK, BIRD_ORIG, CAVE_BLOCKS["birdsview"][0], 2),
]
for _label, _va, _orig, _tgt, _gen in HOOKS:
    _new = b"\xE9" + rel32(_va, _tgt) + b"\x90" * (len(_orig) - 5)
    assert len(_new) == len(_orig) >= 5, "hook %s: %d bytes is too short for E9" % (
        _label.strip(), len(_orig))
    SITES.append((_label, _va, _orig, _new, _gen))

USED = CAVE_BLOCKS["_end"] - CAVE
USED_V1 = CAVE_BLOCKS["_v1end"] - CAVE
assert USED > USED_V1, "v2 payload must be longer than v1 (it appends blocks)"
assert USED <= CAVE_LIMIT, "cave payload %d B outgrew the 0x%X reservation" % (
    USED, CAVE_LIMIT)
assert CAVE + CAVE_LIMIT <= CAVE_ZERO_END, "reservation runs past the verified-zero zone"


# ---- build-time assertions on the ASSEMBLED bytes ---------------------------
def verify_cave():
    """Never trust the keystone round trip -- read the encodings back."""
    for name in CAVE_BLOCKS["_order"]:
        va, code = CAVE_BLOCKS[name]
        n = 0
        for ins in cs.disasm(code, va):
            n += ins.size
            # PIC: no absolute memory operand anywhere.
            if "0x55" in ins.op_str and "ptr [" in ins.op_str:
                sys.exit("ABORT: block %s @0x%08X has an absolute memory operand: "
                         "%s %s" % (name, ins.address, ins.mnemonic, ins.op_str))
        if n != len(code):
            sys.exit("ABORT: block %s does not fully disassemble (%d of %d B)"
                     % (name, n, len(code)))

    # The push-imm8 sign-extension trap: read the terrain immediates back off
    # the bytes rather than trusting the source text.
    fill_va, fill = CAVE_BLOCKS["fillterr"]
    pushes = []
    for ins in cs.disasm(fill, fill_va):
        if ins.mnemonic != "push":
            continue
        try:
            pushes.append(int(ins.op_str, 0))       # imm forms only; regs raise
        except ValueError:
            pass
    want = [WALL_TERRAIN, SKY_TERRAIN]
    if sorted(pushes) != sorted(want):
        sys.exit("ABORT: fillterr terrain immediates decode as %s, expected %s "
                 "(keystone push imm8 trap)" % (pushes, want))

    # Both vision stubs must be byte-identical apart from their tail jmp.
    v1 = CAVE_BLOCKS["vis1"][1]
    v2 = CAVE_BLOCKS["vis2"][1]
    if len(v1) != len(v2) or v1[:-5] != v2[:-5]:
        sys.exit("ABORT: the two vision stubs diverge before their tail jump")

    # All four [ebp-7] gates share one predicate; only the 11-byte tail
    # (je rel32 = 6 B, jmp rel32 = 5 B) may differ.
    gates = ["spellgate", "stormcast", "stormai", "birdsview"]
    heads = {CAVE_BLOCKS[g][1][:-11] for g in gates}
    if len(heads) != 1:
        sys.exit("ABORT: the [ebp-7] gate stubs diverge before their tails")
    for g in gates:
        code = CAVE_BLOCKS[g][1]
        if len(code) != len(CAVE_BLOCKS["spellgate"][1]):
            sys.exit("ABORT: gate stub %s has an unexpected length" % g)
        if not (code[-11] == 0x0F and code[-10] == 0x84 and code[-5] == 0xE9):
            sys.exit("ABORT: gate stub %s does not end je rel32 / jmp rel32" % g)


verify_cave()


# ---- PE section mapping -----------------------------------------------------
def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e + 6)[0]
    optsize = struct.unpack_from("<H", data, e + 20)[0]
    sec = e + 24 + optsize
    secs = []
    for _ in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", data, sec + 8)
        secs.append((vaddr, vsize, raw, rsize))
        sec += 40
    return secs


def va2off(secs, va):
    """VA -> file offset THROUGH THE SECTION TABLE (the delta is per-section:
    CODE is +0x55700C00, DATA is +0x55701200).  Never a flat delta."""
    rva = va - DLL_BASE
    for vaddr, vsize, raw, rsize in secs:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
    raise ValueError("VA %08X not mapped" % va)


def disasm(code, va, title=None):
    if title:
        print("   --- %s @0x%08X (%d B) ---" % (title, va, len(code)))
    for ins in cs.disasm(code, va):
        print("  %08X  %-22s %s %s"
              % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))


def kill_aow():
    import subprocess
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match "
         "'^(AoW|AoWCompat|AoWDevEd|AoWEd)$' } | Stop-Process -Force"],
        capture_output=True)


def main():
    apply_ = "--apply" in sys.argv
    undo = "--undo" in sys.argv
    dis = "--dis" in sys.argv or "--show" in sys.argv
    if apply_ and undo:
        sys.exit("pick one of --apply / --undo")

    print("build_maplevel4   Firmament = level index %d, terrain 0x%02X   "
          "cave 0x%08X..0x%08X (v2 %d B / v1 %d B, of %d)"
          % (SKY_LEVEL, SKY_TERRAIN, CAVE, CAVE_BLOCKS["_end"] - 1, USED,
             USED_V1, CAVE_LIMIT))
    for name in CAVE_BLOCKS["_order"]:
        va, code = CAVE_BLOCKS[name]
        print("    %-11s 0x%08X  %4d B%s"
              % (name, va, len(code), "" if name in V1_BLOCKS else "   [v2]"))

    if dis:
        print()
        for name in CAVE_BLOCKS["_order"]:
            va, code = CAVE_BLOCKS[name]
            disasm(code, va, name)
            print()
        for label, va, orig, new, gen in SITES:
            disasm(new, va, "site %s gen%d (was: %s)"
                   % (label.strip(), gen, orig.hex(" ")))
            print()
        return

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s" % DLL)
    data = bytearray(open(DLL, "rb").read())
    secs = load_sections(data)

    def rd(va, n):
        o = va2off(secs, va)
        return bytes(data[o:o + n])

    def wr(va, b):
        o = va2off(secs, va)
        data[o:o + len(b)] = b

    # Two payloads: the v1 one (the five frozen blocks, everything past them
    # zero) and the v2 one (v1 + the three appended [ebp-7] stubs).  The v1
    # payload is what an installed v1 must byte-match for the in-place rewrite
    # to be recognised rather than blind.
    payload = bytearray(USED)
    for name in CAVE_BLOCKS["_order"]:
        va, code = CAVE_BLOCKS[name]
        payload[va - CAVE:va - CAVE + len(code)] = code
    payload = bytes(payload)
    payload_v1 = payload[:USED_V1]

    cur_cave = rd(CAVE, CAVE_LIMIT)
    cave_zero = cur_cave == bytes(CAVE_LIMIT)
    cave_v1 = (cur_cave[:USED_V1] == payload_v1
               and cur_cave[USED_V1:] == bytes(CAVE_LIMIT - USED_V1))
    cave_v2 = (cur_cave[:USED] == payload
               and cur_cave[USED:] == bytes(CAVE_LIMIT - USED))

    states = {}
    print()
    for label, va, orig, new, gen in SITES:
        cur = rd(va, len(orig))
        st = ("original" if cur == orig else
              "patched" if cur == new else "FOREIGN")
        states[label] = (st, gen)
        print("  %s gen%d 0x%08X  %-17s %s" % (label, gen, va, cur.hex(" "), st))
    print("  cave        0x%08X  %s"
          % (CAVE, "all zero" if cave_zero else
             "v1 payload (%d B), growth zone zero" % USED_V1 if cave_v1 else
             "v2 payload (%d B)" % USED if cave_v2 else
             "DIFFERS from every state this script knows"))

    if any(st == "FOREIGN" for st, _ in states.values()):
        sys.exit("\nABORT: at least one site holds bytes this script neither wrote "
                 "nor expects. Inspect before writing.")

    g1 = [st for st, gen in states.values() if gen == 1]
    g2 = [st for st, gen in states.values() if gen == 2]

    # Three recognised states.  gen-1 sites carry identical bytes in v1 and v2,
    # so it is the gen-2 sites plus the cave tail that separate the two.
    st_orig = all(s == "original" for s in g1 + g2) and cave_zero
    st_v1 = (all(s == "patched" for s in g1)
             and all(s == "original" for s in g2) and cave_v1)
    st_v2 = all(s == "patched" for s in g1 + g2) and cave_v2

    if st_orig:
        print("\nSTATUS: orig -- NOT applied")
    elif st_v1:
        print("\nSTATUS: applied (v1 -- NEEDS RE-TUNE to v2: storm spells and "
              "Bird's View still refuse the Firmament)")
    elif st_v2:
        print("\nSTATUS: applied (v2 -- up to date)")
    else:
        print("\nSTATUS: PARTIAL / UNRECOGNISED -- the site states and the cave "
              "do not add up to orig, v1 or v2.")

    # ---- undo ----
    if undo:
        if st_orig:
            print("Nothing to undo.")
            return
        if not (st_v1 or st_v2):
            sys.exit("ABORT: unrecognised state -- refusing to undo blind.")
        for label, va, orig, new, gen in SITES:
            wr(va, orig)                       # restores v1 AND v2 sites alike
        wr(CAVE, bytes(USED))                  # zero the FULL v2 length
        rest = rd(CAVE + USED, CAVE_LIMIT - USED)
        if rest != bytes(CAVE_LIMIT - USED):
            sys.exit("BUG: undo left non-zero bytes past 0x%08X -- not writing."
                     % CAVE_BLOCKS["_end"])
        kill_aow()
        try:
            open(DLL, "wb").write(data)
        except PermissionError:
            sys.exit("ERROR: AoWEPACK.dpl is locked. Kill AoW/AoWCompat/AoWDevEd/"
                     "AoWEd and retry.")
        print("UNDO: cap byte 0x%08X -> 03, %d hook sites restored, cave "
              "0x%08X zeroed (%d B). No backup touched."
              % (CAP_IMM_VA, len(HOOKS), CAVE, USED))
        return

    if not apply_:
        if not st_v2:
            print("DRY RUN -- re-run with --apply to commit%s."
                  % (" (in-place cave rewrite v1 -> v2)" if st_v1 else ""))
        return

    if st_v2:
        print("\nAlready applied (v2) and up to date -- nothing to do.")
        return

    if not (st_orig or st_v1):
        sys.exit("ABORT: --apply accepts only the orig or the installed-v1 state.")

    # In-place re-tune from v1: assert the zone v2 grows into is still zero
    # BEFORE overwriting, so a stale or foreign cave tail can never be
    # silently absorbed into the new payload.
    if st_v1:
        growth = rd(CAVE + USED_V1, USED - USED_V1)
        if growth != bytes(USED - USED_V1):
            sys.exit("ABORT: the v1->v2 growth zone 0x%08X..0x%08X is not zero."
                     % (CAVE + USED_V1, CAVE + USED - 1))

    # The st_orig check only proves this feature's nine sites and its own cave
    # are unpatched -- it says nothing about the rest of the DLL, and after an
    # --undo it is precisely the state this script itself just produced. So the
    # backup is gated on proven_pristine() (a byte-compare against
    # AoWEPACK_original_backup.dpl), never on st_orig and never on the absence
    # of a backup file.
    if st_orig and not os.path.exists(BACKUP) and proven_pristine():
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("backup -> backups\\%s" % os.path.basename(BACKUP))
    elif st_v1:
        print("v1 -> v2 in-place rewrite: NO backup taken (the file on disk is "
              "this script's own previous output, not a proven-unpatched state)")
    elif not os.path.exists(BACKUP):
        print("backup skipped -- the live DLL is not byte-identical to the "
              "pristine reference, so a snapshot of it would prove nothing")

    for label, va, orig, new, gen in SITES:
        wr(va, new)
    wr(CAVE, payload)
    tail = rd(CAVE_BLOCKS["_end"], CAVE + CAVE_LIMIT - CAVE_BLOCKS["_end"])
    if tail != bytes(len(tail)):
        sys.exit("BUG: the cave-zone tail is not zero -- not writing.")

    kill_aow()
    try:
        open(DLL, "wb").write(data)
    except PermissionError:
        sys.exit("ERROR: AoWEPACK.dpl is locked. Kill AoW/AoWCompat/AoWDevEd/AoWEd "
                 "and retry.")
    print("\nAPPLIED: cap byte 0x%08X 03->04; %d hooks; cave %d B at 0x%08X."
          % (CAP_IMM_VA, len(HOOKS), USED, CAVE))
    print("Revert with --undo (surgical). No RNG draws in this feature.")
    print("Status: applied, untested -- needs the user's in-game test.")


if __name__ == "__main__":
    main()
