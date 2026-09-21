#!/usr/bin/env python3
r"""
AoW1 mod -- "rtugearth": Raise Terrain castable UNDERGROUND, and underground DIRT
becomes TEMPORARY EARTH with the vanilla raise glow.

    underground (level != 0) + Dirt(0x0C)  ->  Earth(7) for 2-4 of the caster's
                                               turns, then back to Dirt, with the
                                               green raise-glow animation.

Surface behaviour is untouched and no mountain placement changes anywhere.

SHIPPED SETTINGS -- both knobs are ON; read the two SCOPE NOTES before changing them.

    EXCLUDE_ROAD_OVERLAY = True    hexes whose overlay is 4 (road) or 5 (bridge)
                                   are skipped, because converting the terrain
                                   under one destroys it permanently
    LAVA_SURFACE_ONLY    = True    the lava -> 50% dirt arm owned by
                                   build_raiseterrain_lavadirt.py is gated to the
                                   surface, so unlocking underground casting does
                                   not silently give lava a new behaviour

With these settings the shared cave_lavadirt loses FIVE bytes, not one:
0x5580DB6C..0x5580DB70, `1c b8 02 00 00` -> `26 e9 0e 06 03` (the `jne`
displacement, then `mov eax,2` becoming `jmp C_LAVAGATE`). Set both to False and
the diff drops to the single `jne` displacement byte. `--dis` always prints the
measured diff, so trust it over any prose here.

================================================================================
WHY THIS SCRIPT REWRITES ANOTHER FEATURE'S CAVE
================================================================================
build_raiseterrain_lavadirt.py is APPLIED and owns the only usable injection point
-- the per-hex site 0x557A333E, right after the hex passes RaiseTerrain's own
validity test. There is no second post-validity 5-byte window in the loop: the
instruction before it (`mov eax,[0x558e92e8]` @0x557A3313) carries a .reloc entry
and must not be displaced, and everything earlier runs before validity is known.
That script has no --undo and no trustworthy backup, so it cannot be reverted
first. The project's answer to exactly this situation is the in-place cave rewrite
(build_invis_penalty.py over build_trueseeing.py's caves); this is that.

The rewrite is deliberately as small as it can be:

    0x5580DB6C   the rel8 displacement of `jne` inside cave_lavadirt   0x1C -> 0x26
    0x5580DB6D   `mov eax,2` -> `jmp C_LAVAGATE`, ONLY when             (5 bytes)
                 LAVA_SURFACE_ONLY is set, which it currently is
    0x5580DB93   5 bytes of DEAD tail left behind by a superseded      -> jmp C_UGDIRT
                 lavadirt cut, verified to have no live inbound
                 reference anywhere in any EXECUTE section

Nothing else in that cave moves. The 50% roll itself -- `call 0x55827000`, the
synced RNG stub -- stays at its exact address 0x5580DB72, which also matters to
build_rng_lockstep.py because that VA is a literal in its SITES table. The `test
eax,eax`, the 50% branch, `mov ebx,[esp+8]`, `jmp ANIM`, `jmp CONT` and the
`_mountain` replay block are all byte-identical afterwards, because the script
builds its NEW image by COPYING the installed 51-byte image and writing into the
copy. The lava path is never regenerated, so it cannot drift. `--dis` prints both
images side by side and lists the measured differing offsets.

C_LAVAGATE restores EAX = 2 and re-enters the lava arm at 0x5580DB72, so a
SURFACE lava hex executes exactly the instruction stream it did before; only an
underground one is diverted to the vanilla mountain path.

Keeping `call 0x55827000` at 0x5580DB72 also matters to build_rng_lockstep.py,
which has that literal VA in its SITES table.

CONSEQUENCE, on purpose: build_raiseterrain_lavadirt.py can no longer re-apply.
Its cave_priors check covers 0x5580DB60..0x5580DB93 and the jne byte is inside it,
so it will report a mismatch and ABORT BEFORE WRITING -- the safe failure. Undo
this feature first if that script ever has to run again.

⚠⚠ SECOND CONSEQUENCE, LOUDER, added with the sparkle fix (P6): this script now
also rewrites six bytes inside build_gripofwinter.py's C_SHOW cave. That script
compares the whole 20-byte C_SHOW blob, so while this feature is installed
build_gripofwinter.py can neither --apply NOR --undo -- both abort with
"cave 0x5582A4E0 is foreign". Both abort BEFORE writing, so nothing is corrupted,
but the revert order is now fixed:

        *** UNDO build_raiseterrain_ug_earth.py BEFORE build_gripofwinter.py ***

Our --undo restores C_SHOW to its exact gripofwinter-only contents, which hands
that script its undo back. There is no way to avoid this coupling short of
editing build_gripofwinter.py itself: every insertion point -- its C_SHOW cave,
or the E9 at its Show hook 0x55764BD0 -- is a run it byte-compares. Owning the
change here rather than there was the deliberate choice; the cost is this
ordering rule.

================================================================================
THE THREE MECHANISMS
================================================================================
P0  UNDERGROUND CASTING (1 byte, no cave)
    The gate was never in ValidTarget*. TGlobalTargetSpell's target-error routine
    @0x5579E73C does:
        cmp byte [esi+0x39],0 ; je ok        <- a SURFACE-ONLY flag on the spell
        <get x,y,level via 0x5577ED94>
        cmp byte [ebp-7],0    ; je ok        <- level
        <resourcestring [0x558E8FE4] "must be cast on the surface">
    TRaiseTerrain.Create sets it: `mov byte [esi+0x39],1` @0x557A3579.
    FIX: the immediate at 0x557A357C, 0x01 -> 0x00. Verified clean on our DLL.
    (Credit: diagnosed by Inioch, Modding Resources/Inioch/share6. Re-verified here
    against both the live and the pristine DLL.)

P1  THE CONVERSION (cave C_UGDIRT)
    Reached only for hexes that already passed RaiseTerrain's per-hex validity
    check. Underground + Dirt spawns a TFrozenWaterHS marker, flips the terrain to
    Earth, and jumps into the vanilla raise-glow block @0x557A3414 with EBX = the
    map field, exactly as the lava arm does -- so the hex sparkles and no mountain
    is placed. Anything else replays the two displaced instructions and returns to
    the vanilla mountain path @0x557A3343.

P2  THE TEMPORARY STATE -- ALREADY BUILT, NOTHING NEW HERE
    build_gripofwinter.py is applied and has already extended TFrozenWaterHS
    (VMT 0x557147B4, classref holder [0x55714774], instance size [VMT-0x1C] = 0x10)
    with precisely the two bytes this feature needs, with precisely these meanings:

        [hs+0x0C]  countdown, decremented on the owner's turn (vanilla)
        [hs+0x0D]  owner player                               (vanilla)
        [hs+0x0E]  terrain to RESTORE   -- 0 means "plain vanilla ice marker"
        [hs+0x0F]  terrain this marker SET

    and the three consumers are already installed and applied:

        C_RW    @0x5582A320  ReadWrite persists +0x0E as property id 0x20 and
                             +0x0F as 0x21  ->  SAVE/LOAD IS ALREADY HANDLED.
                             Property tables are id-indexed, so a save written
                             before this feature simply lacks the ids and loads
                             both bytes as 0 = a vanilla ice marker.
        C_MELT  @0x5582A3A0  MeltIce: +0x0E != 0 and the hex still holds +0x0F
                             -> ChangeTerrain back to +0x0E; otherwise Destroy.
                             -> THE REVERT IS ALREADY HANDLED.
        C_HSTC  @0x5582A460  TerrainChanged: +0x0E != 0 -> keep the marker while
                             the hex holds +0x0F, else free it.
        C_SHOW  @0x5582A4E0  Show: +0x0E != 0 -> draw nothing.
                             *** THIS IS THE SPARKLE, AND IT SUPPRESSED OURS.
                             See "THE SPARKLE" below. ***

    So this script writes NO melt cave, NO TerrainChanged cave and NO ReadWrite
    cave. It only mints a marker whose +0x0E/+0x0F say "restore Dirt, I set Earth".
    *** build_gripofwinter.py must stay applied for the revert to work. ***
    The script refuses to apply if those four sites are not hooked.

    PlaceHX IS CHECKED (QA finding (a)). Vanilla checks its result at 0x557A3400
    (`test al,al; je CONT`) and so does C_UGDIRT. If the hex's HS array is full,
    TEObject.Create succeeds but PlaceHX fails, [marker+4] stays nil and NewTurn
    is never delivered -- so converting anyway would strand the hex as Earth for
    ever. On that path the cave frees the orphan (Destroy at VMT-0x04, the same
    call MeltIce makes) and leaves the hex completely untouched. Vanilla leaks its
    mountain object in the equivalent case; we do not.

    Marker/flip ordering is deliberate: stamp +0x0E/+0x0F FIRST, then flip. The
    flip's own TerrainChanged notification reaches C_HSTC, which sees new terrain
    == [+0x0F] and keeps the marker. Stamping afterwards would let C_HSTC destroy
    it. If the create fails the cave bails to CONT without touching terrain, so a
    hex can never be left converted with no marker to restore it.

================================================================================
THE SPARKLE  (P6 -- added after the first in-game test)
================================================================================
First test: "underground dirt->earth converts and reverts, but there is no
sparkle." The green raise glow was there (that is the vanilla ANIM block, which
this feature jumps to); what was missing was the Freeze Water shimmer that marks
a hex as temporary.

WHY IT WAS MISSING -- and why the existing comment about it is wrong.
TFrozenWaterHS.Show (VMT slot +0xA8, @0x55764BD0) makes exactly ONE outbound call:

    0x55764C60  call 0x5570291C
                -> ILPACK.dpl!ImageLib.TImageSequenceList.ShowLoopedEx
                   eax = [[0x558FA044]+0x94]   the image-sequence list
                   edx = 0x46                  the sequence index
                   ecx = screen x
                   stack: canvas, phase, [[0x558FA040]+0x40], screen y
                   phase = hexX + 3*hexY  -- per-hex offset so adjacent hexes do
                   not pulse in step; the third stack arg is the global anim tick

A LOOPED IMAGE SEQUENCE driven by a global tick and a per-hex phase is an
animation, and it is the ONLY thing Show draws. It is the shimmer. There is no
ice tile here at all -- the ice LOOK comes from the terrain byte (6 / 0xD)
painted by the terrain renderer, not from Show. A module-wide scan finds exactly
one caller of ShowLoopedEx in the whole of AoWEPACK, and it is this one.

So build_gripofwinter.py's "C_SHOW: no ice sprite over cooled land" is a
misreading of what that call does. What C_SHOW actually suppresses, for every
marker with +0x0E != 0, is THE SPARKLE. Our markers set +0x0E = Dirt, so they
were caught by it. The sparkle and the "ice sprite" are not separable, because
there is only the sparkle: C_SHOW is an all-or-nothing gate on precisely the
thing the user asked for.

THE FIX (P6). Replace C_SHOW's first SIX bytes -- its `cmp byte [eax+0x0E],0` and
`jne SKIP` -- with `jmp C_SHOWGATE` + a nop, and re-implement the predicate in
our own cave with one extra clause:

    +0x0E == 0        -> shimmer   (a plain ice marker: unchanged)
    +0x0F == Earth(7) -> shimmer   (OURS: this is the fix)
    otherwise         -> ret 4     (Grip of Winter cooled land: unchanged)

C_SHOWGATE does not return into itself: both outcomes jump back to
build_gripofwinter.py's OWN bytes, still in place -- 0x5582A4E6 for the vanilla
replay and 0x5582A4F1 for the `ret 4`. Its remaining 14 bytes are untouched and
are still the code that executes.

PROOF THAT GRIP OF WINTER LOOKS EXACTLY AS IT DID. Enumerate every marker state
that can reach Show; there are only three, because +0x0E and +0x0F are only ever
written by build_gripofwinter.py's C_TCFIN and by this script:

  marker                        +0x0E   +0x0F   before            after
  vanilla ice (Freeze Water     0       0       cmp/je -> replay  je -> jmp to the
    water arm; also every                       -> jmp 0x55764BD6   SAME replay
    marker in a pre-feature
    save, which reads 0/0)
  Grip cooled land              2/4/1   4/1/3   jne -> ret 4      jne -> jmp to the
    (Desert/Steppe/Grass)                                           SAME ret 4
  raised earth (ours)           0x0C    7       jne -> ret 4      -> shimmer
                                                (THE BUG)         (THE FIX)

Only our own state changes outcome. The other two reach the identical final
instructions, at their original addresses, one extra jump earlier. C_SHOWGATE
touches no register (it only reads two bytes off EAX and sets flags), uses no
stack, and the replay it jumps to does not read flags -- so nothing else can
differ. `--dis` prints the before/after images with the changed offsets listed.

WHY +0x0F == 7 IS A SAFE DISCRIMINATOR, and the coupling it creates.
build_gripofwinter.py's ladder is Desert->Steppe, Steppe->Grass, Grass->Snow, so
the terrains it can ever record in +0x0F are {1,3,4}; its ice arm writes {0}. 7
(Earth) is not on that ladder and is written only here.
*** If Earth is ever added to that ladder, this discriminator breaks and cooled
land would start to shimmer. Change it to test +0x0E == Dirt as well. ***

TINT: the shimmer is drawn from a fixed sequence index (edx = 0x46), so raised
earth shimmers IDENTICALLY to Freeze Water ice. That is what was asked for, and
it is also the do-nothing option -- there is no tint parameter on this call.

================================================================================
DESIGN DECISION -- UP-FRONT FLIP, NOT THE FRAME-9 FLIP
================================================================================
The lava arm converts at glow frame 9, from inside
NewFrameRaiseTerrainAnimation. This feature converts UP FRONT, in the synchronised
TE, and lets the glow be purely cosmetic. Reasons, in order of weight:

  1. It touches NOTHING at the second shared hook. cave_dirtdelay @0x5580DC20 and
     the hook @0x557A31E9 stay byte-identical, so the blast radius over
     build_raiseterrain_lavadirt.py is one jump displacement instead of two caves.
     (cave_dirtdelay gates on `[field+0x14] == 9`; an Earth hex never matches, so
     it no-ops for us with no change at all.)
  2. Multiplayer. Marker spawn, duration roll, owner and terrain change all happen
     in one synchronised context in a fixed order, so peers cannot diverge. The
     frame-9 route is anim-timed and Inioch flags it as an MP residual in his own
     notes; it is a residual we already carry once for lava and there is no reason
     to buy a second one.
  3. No RNG-guard hack. The frame-9 route has to set bit 3 of [*0x558FA040+0x3C]
     to stop ChangeTerrain's variant roll tripping the "Invalid AoWHSMap.Random
     use" assert from the render context. Up front, in the TE, the variant roll
     draws SYNCED like everything else and no flag is touched. CLAUDE.md is
     explicit that the bit-3 flag is not a fix.
  4. Robustness. If the glow is culled or never ticks, an up-front flip has already
     happened; a frame-9 flip would leave a marker promising to restore a terrain
     that was never set, which then silently self-destructs on melt.

  COST, stated plainly: the earth appears the instant the spell resolves and the
  glow plays over it, instead of appearing at the moment the glow peaks. The glow
  is present either way -- that is what the user asked for -- but the timing is
  NOT identical to the lava arm. There is deliberately NO knob for the other
  behaviour: building it would mean rewriting cave_dirtdelay @0x5580DC20 as well,
  which is the whole thing this choice avoids. If the timing turns out to matter
  more than items 1-4, that is a rewrite, not a flag.

================================================================================
SCOPE NOTE -- underground LAVA
================================================================================
Two instructions in the brief collide on exactly one cell of the matrix, and it
cannot be split:

  "preserve the lava arm's behaviour exactly"  vs
  "underground terrains other than Dirt must behave exactly as they do today".

Underground lava was unreachable before this feature, because the spell was
surface-only, so the second instruction had no defined answer for it.

RESOLVED, and SHIPPED, as LAVA_SURFACE_ONLY = True: the lava arm is gated to the
surface, so a surface lava hex behaves exactly as it always has and an underground
one takes the vanilla mountain path rather than gaining a behaviour nobody asked
for. It costs one 5-byte run in the shared cave: `mov eax,2` @0x5580DB6D becomes
`jmp C_LAVAGATE`, and that cave tests the level and either restores EAX = 2 and
re-enters the lava arm at 0x5580DB72 -- so `call 0x55827000` still sits at the VA
build_rng_lockstep.py records -- or falls to the mountain path.

Set it to False to make the lava arm's `terrain == 9` test unconditional again, in
which case underground lava also rolls 50% dirt.

================================================================================
SCOPE NOTE -- roads and bridges
================================================================================
SHIPPED as EXCLUDE_ROAD_OVERLAY = True. Inioch hit a real bug with this same
machinery: converting the terrain under a road/bridge DELETED it permanently,
because the restore puts the terrain back but not the overlay. The fix is to skip
hexes whose [field+0x15] overlay is 4 (road) or 5 (bridge), which the gate at the
head of C_UGDIRT now does. Excluded hexes fall through to the vanilla mountain
path exactly as any other non-Dirt hex would.

Set it to False to convert road and bridge hexes too, and lose them.

⚠ This is an exclusion, not a repair: it prevents the loss, it does not make the
restore put overlays back. Anything else that changes terrain under a road still
destroys it.

================================================================================
ADDRESSES -- ALL RE-VERIFIED ON THIS INSTALL
================================================================================
  0x557A357C  surface-only immediate, context c6 46 39 01 @0x557A3579     clean
  0x5580DB60  cave_lavadirt, 51 B, live image asserted verbatim
  0x5580DB93  dead superseded-cave tail, no live inbound reference
  0x557A3343  RESUME -- back into the vanilla mountain-resource scan
  0x557A3414  ANIM   -- the vanilla raise-glow block, wants EBX = anim data
  0x557A3498  CONT   -- per-hex continue
  0x55701FFC  find-HS-on-field thunk    (eax=field, edx=classref -> hs|0)
  0x55703064  TEObject create thunk     (eax=classref, dl=1, ecx=0)
  0x557025F4  PlaceHX thunk             (eax=map, edx=hs, ecx=x, push level, push y)
  0x5577827C  AoWE.TAoWHSMap.Random     (eax=map, edx=n)  SYNCED
  0x55714774  TFrozenWaterHS classref holder -> 0x557147B4, name at [VMT-0x20]
  0x558E9494  map holder; [0x558E9494] == 0x558FA040, so the DOUBLE deref used by
              RaiseTerrain and the SINGLE deref used by MeltIce reach one object.
              This cave uses the double deref -- the idiom of the function it is
              spliced into -- and never touches 0x558FA040.

The three engine entry points and the create/place/find call shapes are copied
POSITIONALLY out of vanilla TFreezeWaterTE.TerrainChanged @0x5579E924..0x5579E987,
which builds this exact class on a map field. The duration formula and the caster
byte are copied positionally out of the host function itself (0x557A3392 and
0x557A33AC). Nothing here was inferred from parameter names.

RNG
  re_tools/rng_audit.py --functions puts Mountain.TRaiseTerrainTE.RaiseTerrain in
  the SYNC list (and only there) for both the live and the pristine module, so the
  duration roll calls AoWE.TAoWHSMap.Random directly, the same way vanilla does
  twice in this very function (0x557A3397, 0x557A346E). Baseline before this
  feature: 23 modded sites. After: 24, the new one being the cave's Random call,
  which must print `ok`.

PIC
  The .dpl rebases, so the two globals are reached with ONE anchor scheme and one
  anchor: `call $+5 ; pop ebp` leaves the RUNTIME anchor in EBP with NO `sub`, and
  every global is addressed as [ebp + (target_preferred - anchor_preferred)].
  Mixing that with `sub reg, anchor` displacements is what crashed Inioch's first
  cut; there is exactly one scheme in this cave and no `sub`.

REGISTERS
  RaiseTerrain keeps EDI (field container, read at 0x557A32EA/F3/0x557A3306) and
  EBP (mountain-resource list, read at 0x557A3345/0x557A334C) live ACROSS loop
  iterations; both are saved and restored around the cave body. EAX/EBX/ECX/EDX/ESI
  are free -- the ANIM block reloads all of them and only reads EBX. The three
  engine calls preserve EBX/ESI/EDI/EBP, which is proved positionally by vanilla
  TFreezeWaterTE.TerrainChanged keeping ESI (field), EDI (TE) and EBX (marker)
  live across all three. TAoWHSMap.Random pushes/pops EBX and ESI and clobbers
  ECX, which the cave reloads.

TOTAL FOOTPRINT at the shipped settings -- five runs. Verify with --dis, which
measures them rather than quoting them.
  0x557A357C     1 B   01 -> 00                       the surface-only flag
  0x5580DB6C     5 B   jne disp + mov eax,2           inside cave_lavadirt
                       -> jne disp + jmp C_LAVAGATE   (build_raiseterrain_lavadirt)
  0x5580DB93     5 B   dead bytes -> jmp C_UGDIRT     superseded-cave tail
  0x5582A4E0     6 B   cmp/jne -> jmp C_SHOWGATE      inside C_SHOW
                                                      (build_gripofwinter), P6
  0x5583E000   512 B   the reservation: C_UGDIRT 267 B, C_SHOWGATE 22 B,
                       C_LAVAGATE 29 B, remainder zero
Twelve bytes sit inside code that executes today; the rest was zero or dead.

SAFETY CHECKS RUN AGAINST THE LIVE FILE (all clean)
  * no .reloc entry falls in the cave zone, the trampoline, the jne byte, the flag
    immediate, or either lavadirt cave
  * no call/jmp rel32 and no absolute dword anywhere in any EXECUTE section points
    into 0x5583E000..0x55840000, and the only one pointing into the dead tail is
    that dead code's own `call $+5`
  * cave zone verified all-zero; no other build script references any VA in it
  * no absolute path of any kind is assembled into the cave: it holds no data at
    all -- 203 bytes of register/rel32 code and not one printable run
  * apply / re-tune / undo round-trip on a scratch copy returns the file
    byte-identical to the original, and cave_dirtdelay, the 0x557A31E9 hook and
    build_gripofwinter.py's caves come back bit-for-bit untouched

RE-TUNE, AND WHY THERE IS NO "REVERT FIRST"
  The reservation is treated as ONE owned run, and every run carries the set of
  images this script could previously have written (all knob combinations). A
  second --apply with different constants is recognised as a re-tune: the runs are
  overwritten in place, the whole reservation is rewritten in one go so a shorter
  cave cannot leave a stale tail, and NO backup is taken, because the file on disk
  is this script's own earlier output. Bytes that match none of those images are
  FOREIGN and the script writes nothing at all.

A VETOED REVERT, AND WHY NO GUARD WAS ADDED  (QA finding (c))
  TFrozenWaterHS.NewTurn @0x55764B98 decrements FIRST and has no `<= 0` pre-guard,
  unlike TRaisedMountain.NewTurn @0x557A3064 which tests before decrementing:

      HS   dec byte [eax+0x0C] ; cmp byte [eax+0x0C],0 ; jg ret ; call MeltIce
      MNT  cmp byte [eax+0x1E],0 ; jle ret ; dec ; cmp ; jne ret ; call Expire

  So if something on the hex vetoes the terrain change (TStructure /
  TArmyHS.CanChangeTerrain), TerrainChanged never fires, the marker is never
  destroyed, and the counter runs past zero.

  MEASURED, not assumed: `jg` is SIGNED, so 0 -> 0xFF is -1, which is not > 0 and
  therefore still calls MeltIce. The marker RETRIES EVERY TURN for 129 turns
  (0 down through -128). Only the 130th decrement, 0x80 -> 0x7F, produces +127 and
  starts a 127-turn dormancy -- after which it resumes retrying. It is never
  permanently stuck, and for the first 129 turns the behaviour is exactly what you
  would want: keep trying until the veto lifts.

  DECISION: no guard. Adding one means editing vanilla NewTurn, which is shared
  with Freeze Water ice and with build_gripofwinter.py's cooled land, so it would
  silently change two other features to fix a case that needs 129 consecutive
  vetoed owner-turns first. The exposure is also smaller than it looks here:
  ValidTargetMapF already rejects any hex carrying a TStructure ([0x55713bd8],
  verified), so our markers can never be created under a structure in the first
  place.

  If it is ever wanted, the one-instruction fix is to make the counter saturate
  instead of wrap. It belongs in build_gripofwinter.py, which owns that class.

TWO THINGS THIS SCRIPT CANNOT SETTLE WITHOUT THE GAME
  * TRaiseTerrain.ValidTargetMapF @0x557A35B8 requires the hex OVERLAY to be
    NON-zero (`mov al,[ebx+0x15]; test al,al; je FAIL`) as well as rejecting
    terrain 0/6/0xA/0xD (and, via build_chasm_sky_spellguard.py, 0xB/0xE). If
    underground Dirt floor hexes carry overlay 0 they will still refuse to be
    targeted, and the fix would be a separate edit there. Inioch's in-game test of
    the same unpatched gate says underground hexes DO pass, but that is his
    install, not a byte fact about ours. First thing to check in game.
  * ValidTargetSelectionMapF @0x557A3610 (the cursor highlight) has the identical
    conditions and, like ValidTargetMapF, NO level gate -- confirmed by reading
    both on this DLL. Its extra guard [0x55713bd8] is TStructure, not
    TFrozenWaterHS, so our marker never blocks a re-cast.

USAGE
    python build_scripts/build_raiseterrain_ug_earth.py            verify only
    python build_scripts/build_raiseterrain_ug_earth.py --dis      + disassembly
    python build_scripts/build_raiseterrain_ug_earth.py --apply    write
    python build_scripts/build_raiseterrain_ug_earth.py --undo     surgical
"""
import os
import shutil
import struct
import subprocess
import sys

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-rtugearth")
BASE = 0x55700C00                       # CODE: VA = file_offset + BASE

# ------------------------------------------------------------------ knobs -----
EXCLUDE_ROAD_OVERLAY = True             # see "SCOPE NOTE -- roads and bridges"
                                        # ON: a road/bridge hex is never converted. Without this,
                                        # the revert restores terrain but NOT the overlay, so the
                                        # road is destroyed permanently (Inioch hit this). Data
                                        # loss, not a design choice -- do not turn this off.
LAVA_SURFACE_ONLY = True                # see "SCOPE NOTE -- underground LAVA"
                                        # ON: the lava 50%-dirt arm stays SURFACE-ONLY, exactly as
                                        # it behaved before UG casting was unlocked. The user asked
                                        # for UG dirt->earth and explicitly nothing else; unlocking
                                        # UG casting would otherwise silently extend the lava arm
                                        # underground. Ruled 2026-09-02.

# --------------------------------------------------------------- terrain ids --
# 0 Water 1 Grass 2 Desert 3 Snow 4 Steppe 5 Wasteland 6 Ice 7 Earth 8 Rock
# 9 Lava  A CaveWater  B Chasm  C Dirt  D CaveIce  E Sky  F Border
DIRT = 0x0C
EARTH = 0x07
OVL_ROAD, OVL_BRIDGE = 4, 5

# ---------------------------------------------------- P0: surface-only flag ---
# `mov byte [esi+0x39], imm8` in TRaiseTerrain.Create. The context assert covers
# the OPCODE ONLY -- the immediate at 0x557A357C is the byte this script owns, so
# including it here would make the assert fail the moment the feature is applied
# (which is exactly what it did before this was split).
FLAG_CTX = 0x557A3579
FLAG_CTX_BYTES = bytes.fromhex("c64639")
FLAG_IMM = 0x557A357C                   # the immediate; 0x01 surface-only, 0x00 free
FLAG_ON, FLAG_OFF = b"\x01", b"\x00"

# ------------------------------------- the shared cave owned by lavadirt ------
LD_CAVE = 0x5580DB60
LD_CAVE_LEN = 51
# the exact image build_raiseterrain_lavadirt.py leaves behind, asserted verbatim
LD_CAVE_INSTALLED = bytes.fromhex(
    "8b4424080fbe401483f809751cb802000000e88994010085c075098b5c2408"
    "e99058f9ffe90f59f9ff31c08b7508e9b057f9ff")
LD_JNE_OP = 0x0B                        # offset of the `jne` opcode in that image
LD_JNE_DISP = 0x0C                      # offset of its rel8 displacement
LD_MOUNTAIN = 0x5580DB89                # where 0x1C points -- lavadirt's own replay
LD_TRAMP = 0x5580DB93                   # dead tail of a superseded lavadirt cut
LD_TRAMP_ORIG = bytes.fromhex("8b8002b90d")
LD_LAVA_MOVEAX = 0x5580DB6D             # `mov eax,2`, only touched by LAVA_SURFACE_ONLY
LD_LAVA_MOVEAX_ORIG = bytes.fromhex("b802000000")
LD_LAVA_ROLL = 0x5580DB72               # `call 0x55827000` -- build_rng_lockstep SITES

# ------------------------------------------ vanilla sites in RaiseTerrain -----
RESUME = 0x557A3343                     # -> the mountain-resource scan
ANIM = 0x557A3414                       # -> the raise-glow block; wants EBX = anim data
CONT = 0x557A3498                       # -> per-hex continue

# ------------------------------------------------- engine entry points --------
FIND_HS = 0x55701FFC
CREATE = 0x55703064
PLACEHX = 0x557025F4
MAP_RANDOM = 0x5577827C
CLASSREF = 0x55714774                   # holder of the TFrozenWaterHS class reference
MAPPTR = 0x558E9494                     # map = *(*MAPPTR)

# ------------------------------- build_gripofwinter.py, which owns the revert --
GRIP_SITES = {
    0x55764ACB: ("ReadWrite  -> C_RW   (persists +0x0E/+0x0F: save/load)", 5),
    0x55764AE0: ("MeltIce    -> C_MELT (restores +0x0E: the revert)", 5),
    0x55764B8B: ("TerrainChanged -> C_HSTC (marker survives our own flip)", 5),
    0x55764BD0: ("Show       -> C_SHOW (the sparkle gate; P6 edits its head)", 5),
}

# ---- P6: the sparkle. Six bytes at the head of build_gripofwinter.py's C_SHOW --
C_SHOW = 0x5582A4E0
C_SHOW_LEN = 20
# the exact image build_gripofwinter.py leaves behind, asserted verbatim
C_SHOW_INSTALLED = bytes.fromhex("80780e00750b558bec83c4f8e9e5a6f3ffc20400")
C_SHOW_HEAD = 6                         # cmp byte [eax+0x0e],0  +  jne SKIP
C_SHOW_REPLAY = 0x5582A4E6              # its `push ebp; mov ebp,esp; add esp,-8`
C_SHOW_RET4 = 0x5582A4F1                # its `ret 4`

# ------------------------------------------------------------- our cave zone --
ZONE_LO, ZONE_HI = 0x5583E000, 0x55840000      # exclusive to this feature
RESV_LO, RESV_HI = 0x5583E000, 0x5583E200      # what --undo zeroes
C_UGDIRT = 0x5583E000                          # slot to 0x5583E140 (320 B)
C_SHOWGATE = 0x5583E140                        # slot to 0x5583E180 (64 B)
C_LAVAGATE = 0x5583E180                        # slot to RESV_HI; only when LAVA_SURFACE_ONLY

PH_CLS = 0x11111111                     # anchor-relative placeholder: CLASSREF
PH_MAP = 0x22222222                     # anchor-relative placeholder: MAPPTR


def off(va):
    return va - BASE


# ------------------------------------------------------------ mini assembler --
def _ks():
    try:
        from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    except ImportError:
        sys.exit("keystone-engine not installed:  pip install keystone-engine")
    return Ks(KS_ARCH_X86, KS_MODE_32)


def asm_layout(frags, base):
    """frags: [(label|None, text|bytes|None)]. Text may use {LABEL} placeholders.
    Iterated to a fixed point so forward references settle.
    Never pass ';' to keystone -- it hangs on comment lines."""
    ks = _ks()
    labels = {lab: base for lab, _ in frags if lab}
    for _ in range(16):
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
            assert ";" not in text, text
            enc, _ = ks.asm(text, va)
            if enc is None:
                raise RuntimeError("keystone failed on: %s" % text)
            out += bytes(enc)
            va += len(enc)
        if seen == labels:
            return bytearray(out)
        labels = seen
    raise RuntimeError("cave layout did not converge")


def bind_anchor(code, base, targets):
    """Locate the `call $+5 ; pop ebp` anchor and rewrite every placeholder
    displacement to (target_preferred - anchor_preferred).

    ONE scheme, and it is the proven one: EBP holds the RUNTIME anchor address
    with NO `sub`, so [ebp + (target_pref - anchor_pref)] resolves to the runtime
    target under any rebase. Subtracting the preferred anchor as well -- which is
    what crashed the first cut of the upstream design -- would leave the effective
    address off by a whole image base."""
    sig = b"\xE8\x00\x00\x00\x00\x5D"
    i = code.find(sig)
    assert i != -1 and code.find(sig, i + 1) == -1, "expected exactly one anchor"
    anchor = base + i + 5
    for ph, tgt, want in targets:
        n, pat = 0, struct.pack("<I", ph)
        while True:
            j = code.find(pat)
            if j == -1:
                break
            code[j:j + 4] = struct.pack("<i", tgt - anchor)
            n += 1
        assert n == want, "placeholder %08X used %d times, expected %d" % (ph, n, want)
    return code


# --------------------------------------------------------------- the cave -----
def build_cave(road=None):
    """C_UGDIRT: underground Dirt -> temporary Earth + the vanilla raise glow.

    Entry is a plain `jmp` from inside cave_lavadirt with NO pushes anywhere along
    the way, so ESP is exactly what it is at the vanilla hook site 0x557A333E:
        [esp]   = Self       (vanilla reads the level from [Self+0x22] @0x557A33C0)
        [esp+4] = arg2       (vanilla reads the caster from [arg2+0x24] @0x557A33AC)
        [esp+8] = map field  (stored @0x557A330D)
    """
    road = EXCLUDE_ROAD_OVERLAY if road is None else road
    f = []

    # ---- gate ---------------------------------------------------------------
    f += [(None, "mov eax, dword ptr [esp + 8]"),
          (None, "cmp byte ptr [eax + 0x14], %s" % hex(DIRT)),
          (None, "jne {VANILLA}"),
          (None, "mov edx, dword ptr [esp]"),
          (None, "cmp byte ptr [edx + 0x22], 0"),
          (None, "je {VANILLA}")]
    if road:
        f += [(None, "cmp byte ptr [eax + 0x15], %s" % hex(OVL_ROAD)),
              (None, "je {VANILLA}"),
              (None, "cmp byte ptr [eax + 0x15], %s" % hex(OVL_BRIDGE)),
              (None, "je {VANILLA}")]

    # ---- save the two registers the enclosing loop needs across iterations ---
    # after both pushes: [esp+8]=Self [esp+0xC]=arg2 [esp+0x10]=field
    f += [(None, "push ebp"),
          (None, "push edi"),
          (None, "mov esi, dword ptr [esp + 0x10]"),
          (None, b"\xE8\x00\x00\x00\x00\x5D")]          # call $+5 ; pop ebp

    # ---- find or create the marker (positional copy of 0x5579E924..0x5579E962)
    f += [(None, "mov edx, dword ptr [ebp + %s]" % hex(PH_CLS)),
          (None, "mov eax, esi"),
          (None, "call %s" % hex(FIND_HS)),
          (None, "mov ebx, eax"),
          (None, "test ebx, ebx"),
          (None, "jne {HAVE}"),
          (None, "xor ecx, ecx"),
          (None, "mov dl, 1"),
          (None, "mov eax, dword ptr [ebp + %s]" % hex(PH_CLS)),
          (None, "call %s" % hex(CREATE)),
          (None, "mov ebx, eax"),
          (None, "test ebx, ebx"),
          (None, "je {BAIL}"),
          (None, "movsx eax, byte ptr [esi + 0x11]"),
          (None, "push eax"),
          (None, "movsx eax, byte ptr [esi + 0x12]"),
          (None, "push eax"),
          (None, "movsx ecx, byte ptr [esi + 0x10]"),
          (None, "mov eax, dword ptr [ebp + %s]" % hex(PH_MAP)),
          (None, "mov eax, dword ptr [eax]"),
          (None, "mov edx, ebx"),
          (None, "call %s" % hex(PLACEHX)),
          # PlaceHX returns AL. Vanilla checks it (0x557A3400 `test al,al; je CONT`)
          # and so must we: a full HS array on a busy hex fails the place, leaving
          # [marker+4] nil so NewTurn is never delivered. Converting anyway would
          # strand the hex as Earth for ever. Free the orphan and leave the hex alone.
          (None, "test al, al"),
          (None, "je {FREE}")]

    # ---- countdown + owner (positional copy of 0x557A3392..0x557A33B5) -------
    # (Random(0xB) - 5) / 5 + 3  ->  2..4 owner turns, the raised mountain's own
    # duration. SYNCED: rng_audit puts this function in the SYNC list.
    f += [("HAVE", "mov eax, dword ptr [ebp + %s]" % hex(PH_MAP)),
          (None, "mov eax, dword ptr [eax]"),
          (None, "mov edx, 0xb"),
          (None, "call %s" % hex(MAP_RANDOM)),
          (None, "sub eax, 5"),
          (None, "mov ecx, 5"),
          (None, "cdq"),
          (None, "idiv ecx"),
          (None, "add al, 3"),
          (None, "mov byte ptr [ebx + 0x0c], al"),
          (None, "mov eax, dword ptr [esp + 0x0c]"),
          (None, "mov al, byte ptr [eax + 0x24]"),
          (None, "mov byte ptr [ebx + 0x0d], al")]

    # ---- stamp the temporary-terrain bytes BEFORE the flip ------------------
    # +0x0E only when it is still 0, so a marker that somehow already exists on
    # this hex keeps the ORIGINAL terrain rather than recording an intermediate.
    f += [(None, "cmp byte ptr [ebx + 0x0e], 0"),
          (None, "jne {SETTGT}"),
          (None, "mov byte ptr [ebx + 0x0e], %s" % hex(DIRT)),
          ("SETTGT", "mov byte ptr [ebx + 0x0f], %s" % hex(EARTH))]

    # ---- flip, in this synchronised TE context ------------------------------
    # Call shape copied positionally from vanilla TFrozenWaterHS.MeltIce
    # (0x55764AF0..0x55764B1D). Map VMT +0xD0 is TAoWHSMap.ChangeTerrain
    # @0x55778D84 (`ret 0x10`, four stack args) -- NOT ChangeTerrainEx
    # @0x55778DCC, which is `ret 0x1C` and takes seven. Shape:
    #   eax = map, edx = requester, ecx = x, stack: terrain, 0, level, y.
    f += [(None, "movzx eax, byte ptr [esi + 0x11]"),
          (None, "push eax"),
          (None, "movzx eax, byte ptr [esi + 0x12]"),
          (None, "push eax"),
          (None, "push 0"),
          (None, "push %s" % hex(EARTH)),
          (None, "movzx ecx, byte ptr [esi + 0x10]"),
          # EDX is the REQUESTER, excluded from the CanChangeTerrain veto poll --
          # vanilla MeltIce passes the marker here (`mov edx,ebx` @0x55764B14) and so
          # does build_gripofwinter.py's C_MELT (@0x5582A3DB). Passing 0 works today
          # only because TArmyHS.CanChangeTerrain nil-checks it. Pass the marker.
          # This must precede the `mov ebx,[eax]` below, which clobbers EBX.
          (None, "mov edx, ebx"),
          (None, "mov eax, dword ptr [ebp + %s]" % hex(PH_MAP)),
          (None, "mov eax, dword ptr [eax]"),
          (None, "mov ebx, dword ptr [eax]"),
          (None, "call dword ptr [ebx + 0xd0]")]

    # ---- glow, no mountain --------------------------------------------------
    f += [(None, "pop edi"),
          (None, "pop ebp"),
          (None, "mov ebx, dword ptr [esp + 8]"),
          (None, "jmp %s" % hex(ANIM))]

    # ---- place failed: free the orphan, then leave the hex alone ------------
    # Destroy shape copied positionally from vanilla MeltIce @0x55764B60
    # (`mov dl,1; mov eax,<self>; mov ecx,[eax]; call [ecx-4]`) -- Destroy lives at
    # VMT-0x04. Reached ONLY when PlaceHX failed, so the marker is on no hex list.
    # Vanilla leaks its mountain object here; we do not.
    f += [("FREE", "mov dl, 1"),
          (None, "mov eax, ebx"),
          (None, "mov ecx, dword ptr [eax]"),
          (None, "call dword ptr [ecx - 4]")]

    # ---- create failed (EBX is nil, nothing to free): leave the hex alone ---
    f += [("BAIL", "pop edi"),
          (None, "pop ebp"),
          (None, "jmp %s" % hex(CONT))]

    # ---- everything else: the two displaced instructions, then vanilla ------
    f += [("VANILLA", "xor eax, eax"),
          (None, "mov esi, dword ptr [ebp + 8]"),
          (None, "jmp %s" % hex(RESUME))]

    code = asm_layout(f, C_UGDIRT)
    code = bind_anchor(code, C_UGDIRT,
                       [(PH_CLS, CLASSREF, 2), (PH_MAP, MAPPTR, 3)])
    if C_UGDIRT + len(code) > C_SHOWGATE:
        raise RuntimeError("C_UGDIRT is %d bytes, its slot is %d"
                           % (len(code), C_SHOWGATE - C_UGDIRT))
    return bytes(code)


def build_showgate():
    """P6, the sparkle. Reached from the head of build_gripofwinter.py's C_SHOW.

    EAX = the TFrozenWaterHS. This cave reads two bytes off it, sets flags, and
    leaves through gripofwinter's OWN bytes -- it clobbers no register, touches no
    stack, and the replay it jumps to does not read flags, so an ice marker and a
    Grip cooled-land marker execute exactly what they executed before."""
    code = asm_layout([
        (None, "cmp byte ptr [eax + 0x0e], 0"),
        (None, "je {SHIMMER}"),                     # a plain vanilla ice marker
        (None, "cmp byte ptr [eax + 0x0f], %s" % hex(EARTH)),
        (None, "jne {HIDE}"),                       # Grip cooled land: still hidden
        ("SHIMMER", "jmp %s" % hex(C_SHOW_REPLAY)),
        ("HIDE", "jmp %s" % hex(C_SHOW_RET4)),
    ], C_SHOWGATE)
    if C_SHOWGATE + len(code) > C_LAVAGATE:
        raise RuntimeError("C_SHOWGATE is %d bytes, its slot is %d"
                           % (len(code), C_LAVAGATE - C_SHOWGATE))
    return bytes(code)


def build_showcave_image():
    """The NEW 20-byte C_SHOW: gripofwinter's installed image with its first six
    bytes replaced by `jmp C_SHOWGATE` + nop.

    Built by COPYING, like the cave_lavadirt image, so the 14 tail bytes -- the
    vanilla replay, the jump back into Show, and the `ret 4` -- provably cannot
    drift. Those are still the instructions that execute."""
    img = bytearray(C_SHOW_INSTALLED)
    assert img[:4] == bytes.fromhex("80780e00"), "expected cmp byte [eax+0x0e],0"
    assert img[4] == 0x75, "expected `jne` at +4"
    assert C_SHOW + 6 == C_SHOW_REPLAY and img[6:12] == bytes.fromhex("558bec83c4f8")
    assert C_SHOW + 6 + img[5] == C_SHOW_RET4 and img[17:20] == b"\xc2\x04\x00"
    img[:C_SHOW_HEAD] = (b"\xE9" + struct.pack("<i", C_SHOWGATE - (C_SHOW + 5))
                         + b"\x90")
    assert [i for i in range(C_SHOW_LEN) if img[i] != C_SHOW_INSTALLED[i]] \
        == list(range(C_SHOW_HEAD))
    assert img[C_SHOW_HEAD:] == C_SHOW_INSTALLED[C_SHOW_HEAD:]
    return bytes(img)


def build_lavagate():
    """Only reachable when LAVA_SURFACE_ONLY. Replaces `mov eax,2` @0x5580DB6D, so
    it must leave EAX = 2 and re-enter the lava arm at the `call` (0x5580DB72),
    which keeps that call at the VA build_rng_lockstep.py records in SITES."""
    code = asm_layout([
        (None, "mov edx, dword ptr [esp]"),
        (None, "cmp byte ptr [edx + 0x22], 0"),
        (None, "jne {UNDERGROUND}"),
        (None, "mov eax, 2"),
        (None, "jmp %s" % hex(LD_LAVA_ROLL)),
        ("UNDERGROUND", "xor eax, eax"),
        (None, "mov esi, dword ptr [ebp + 8]"),
        (None, "jmp %s" % hex(RESUME)),
    ], C_LAVAGATE)
    if C_LAVAGATE + len(code) > RESV_HI:
        raise RuntimeError("C_LAVAGATE is %d bytes, its slot is %d"
                           % (len(code), RESV_HI - C_LAVAGATE))
    return bytes(code)


def build_lavadirt_image(lava=None):
    """The NEW 51-byte cave_lavadirt: the INSTALLED image with one byte changed.

    Built by COPYING the installed image and writing into it, never regenerated,
    so the lava arm physically cannot drift."""
    lava = LAVA_SURFACE_ONLY if lava is None else lava
    img = bytearray(LD_CAVE_INSTALLED)
    assert img[LD_JNE_OP] == 0x75, "expected `jne` opcode at +0x0B"
    assert img[LD_JNE_DISP] == 0x1C, "expected rel8 0x1C at +0x0C"
    assert LD_CAVE + LD_JNE_DISP + 1 + 0x1C == LD_MOUNTAIN
    new_disp = LD_TRAMP - (LD_CAVE + LD_JNE_DISP + 1)
    assert 0 <= new_disp <= 0x7F
    img[LD_JNE_DISP] = new_disp
    expect = [LD_JNE_DISP]
    if lava:
        # `mov eax,2` (5 B) -> `jmp C_LAVAGATE`; the gate restores EAX and
        # re-enters at 0x5580DB72 so the synced-RNG call never moves.
        k = LD_LAVA_MOVEAX - LD_CAVE
        assert bytes(img[k:k + 5]) == LD_LAVA_MOVEAX_ORIG
        img[k:k + 5] = b"\xE9" + struct.pack("<i", C_LAVAGATE - (LD_LAVA_MOVEAX + 5))
        expect += [i for i in range(k, k + 5) if img[i] != LD_CAVE_INSTALLED[i]]
    diff = [i for i in range(LD_CAVE_LEN) if img[i] != LD_CAVE_INSTALLED[i]]
    assert diff == sorted(expect), (diff, expect)
    assert img[0x12:0x17] == LD_CAVE_INSTALLED[0x12:0x17], "the synced RNG call moved"
    return bytes(img)


def build_reservation(road=None, lava=None, showgate=True):
    """The WHOLE reservation as one image: the caves placed, everything else zero.

    Treating the reservation as a single owned run is what makes a re-tune safe.
    It is written in one go, so a shorter cave can never leave a stale tail behind
    from a longer previous one, and "the zone the cave grows into is still zero"
    holds by construction instead of needing a separate rule."""
    lava = LAVA_SURFACE_ONLY if lava is None else lava
    img = bytearray(RESV_HI - RESV_LO)
    blobs = [(C_UGDIRT, build_cave(road))]
    if showgate:                        # False = the pre-P6 layout, before the
        blobs.append((C_SHOWGATE, build_showgate()))   # sparkle cave existed
    for va, blob in blobs:
        img[va - RESV_LO:va - RESV_LO + len(blob)] = blob
    if lava:
        gate = build_lavagate()
        img[C_LAVAGATE - RESV_LO:C_LAVAGATE - RESV_LO + len(gate)] = gate
    return bytes(img)


# Every (road, lava, showgate) combination this script can write into the SHARED
# cave_lavadirt. That run lives inside another feature's code, so it is verified
# against an enumerated set. `showgate=False` is the pre-P6 layout.
KNOBS = [(r, l, s) for r in (False, True) for l in (False, True)
         for s in (False, True)]

# Sentinel for a run whose current contents are accepted whatever they are.
# It is used for ONE run only: our own exclusive cave reservation. Enumerating
# every image this script has ever emitted there is both fragile and pointless --
# 0x5583E000..0x55840000 is reserved to this feature, was verified all-zero before
# the first apply, and no other build script references any VA inside it, so any
# non-zero byte in it is by definition this script's own earlier output. That is
# exactly the "verify against either the installed bytes or the new ones" rule;
# the reservation is rewritten wholesale, so a shorter cave cannot leave a tail.
# Every run that lives inside SOMEONE ELSE'S code -- the flag byte, cave_lavadirt,
# the dead tail, C_SHOW -- is still enumerated and still rejects foreign bytes.
ANY = "<any: our exclusive reservation>"


def build_edits():
    """[(va, absent, variants, new, label)] -- every byte-run this script owns.

    `absent`   = the image when this feature is NOT installed. --undo writes it,
                 and the backup is taken ONLY when every run already equals it.
    `variants` = every image this script could have written before, across all
                 knob settings. Accepting them is what lets a re-tune rewrite the
                 caves in place instead of demanding a revert first.
    """
    e = [
        (FLAG_IMM, FLAG_ON, [FLAG_OFF], FLAG_OFF,
         "P0 surface-only flag OFF (underground casting)"),
        (LD_CAVE, LD_CAVE_INSTALLED,
         [build_lavadirt_image(l) for _r, l, _s in KNOBS],
         build_lavadirt_image(),
         "cave_lavadirt jne 0x1C -> 0x%02X (lava arm otherwise identical)"
         % build_lavadirt_image()[LD_JNE_DISP]),
        (LD_TRAMP, LD_TRAMP_ORIG,
         [b"\xE9" + struct.pack("<i", C_UGDIRT - (LD_TRAMP + 5))],
         b"\xE9" + struct.pack("<i", C_UGDIRT - (LD_TRAMP + 5)),
         "dead-tail trampoline -> C_UGDIRT"),
        (C_SHOW, C_SHOW_INSTALLED, [build_showcave_image()],
         build_showcave_image(),
         "P6 C_SHOW head -> C_SHOWGATE (the sparkle; tail 14 B untouched)"),
        (RESV_LO, bytes(RESV_HI - RESV_LO), ANY, build_reservation(),
         "reservation 0x%08X..0x%08X (C_UGDIRT%s)"
         % (RESV_LO, RESV_HI, " + C_LAVAGATE" if LAVA_SURFACE_ONLY else "")),
    ]
    for va, absent, variants, new, lbl in e:
        assert len(new) == len(absent), lbl
        if variants is not ANY:
            assert all(len(v) == len(new) for v in variants), lbl
    return e


def known(cur, absent, variants, new):
    """Is this run's current content something this script could have left?"""
    return variants is ANY or cur == absent or cur == new or cur in variants


# ------------------------------------------------------------------ plumbing --
def read_dll():
    if not os.path.exists(DLL):
        sys.exit("not found: %s" % DLL)
    with open(DLL, "rb") as f:
        return bytearray(f.read())


def kill_game():
    """Standing authorization: the game and the editor lock the binaries."""
    # ⚠ SCRATCH GUARD (2026-09-03): AOW_GAME_DIR set => we are NOT writing to the real
    # install, so we must NOT kill the user's running game. Without this, an agent doing a
    # "safe" scratch-copy round-trip still terminates the live game -- which happened, and
    # was misreported as a crash-on-expiry. Standing kill authorization applies to the real
    # install only.
    if os.environ.get("AOW_GAME_DIR"):
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match "
         "'^(AoW|AoWCompat|AoWDevEd|AoWEd)$' } | Stop-Process -Force"],
        capture_output=True)


def rows(d, edits):
    """[(label, current, absent, variants, new)] for every owned run."""
    return [(lbl, bytes(d[off(va):off(va) + len(new)]), absent, variants, new)
            for va, absent, variants, new, lbl in edits]


def state(d, edits):
    """-> 'clean' | 'applied' | 'retune' | 'foreign'

    'retune' means every run is recognisable as either the feature-absent image or
    one of this script's own outputs, but they do not all agree -- an earlier build
    with different knobs, or a write interrupted half way. Those bytes get
    overwritten in place; nothing has to be reverted first."""
    r = rows(d, edits)
    if any(not known(cur, absent, variants, new)
           for _, cur, absent, variants, new in r):
        return "foreign"
    if all(cur == new for _, cur, _a, _v, new in r):
        return "applied"
    if all(cur == absent for _, cur, absent, _v, _n in r):
        return "clean"
    return "retune"


def check_prereqs(d):
    """build_gripofwinter.py owns the revert path AND the cave P6 edits. Without
    it the marker never melts back, the raised earth is permanent, and C_SHOW is
    not there to patch."""
    missing = []
    for va, (what, _n) in sorted(GRIP_SITES.items()):
        if d[off(va)] != 0xE9:
            missing.append("  0x%08X  %s" % (va, what))
    cur = bytes(d[off(C_SHOW):off(C_SHOW) + C_SHOW_LEN])
    if cur not in (C_SHOW_INSTALLED, build_showcave_image()):
        missing.append("  0x%08X  C_SHOW body is not the image this script knows\n"
                       "               got %s\n               exp %s"
                       % (C_SHOW, cur.hex(), C_SHOW_INSTALLED.hex()))
    return missing


def check_zone_tail(d):
    """The ANY rule for the reservation is only safe while the REST of our 8 KB
    exclusive zone stays zero -- that is the "assert the zone the cave grows into
    is still zero" half of the in-place-rewrite rule. Anything non-zero out there
    means either a cave that outgrew its reservation or another feature moving in,
    and both need a human."""
    tail = bytes(d[off(RESV_HI):off(ZONE_HI)])
    if tail != bytes(len(tail)):
        bad = RESV_HI + next(i for i, b in enumerate(tail) if b)
        sys.exit("ABORT: 0x%08X..0x%08X is reserved to this feature and "
                 "must stay zero, but 0x%08X is non-zero. Investigate."
                 % (RESV_HI, ZONE_HI, bad))


def check_context(d):
    """The flag immediate is only meaningful if the opcode around it is the one we
    think it is -- a bare `01 -> 00` on a wrong address would be silent."""
    n = len(FLAG_CTX_BYTES)
    got = bytes(d[off(FLAG_CTX):off(FLAG_CTX) + n])
    if got != FLAG_CTX_BYTES:
        sys.exit("ABORT: 0x%08X is %s, expected %s (mov byte [esi+0x39], imm8)"
                 % (FLAG_CTX, got.hex(), FLAG_CTX_BYTES.hex()))
    assert FLAG_CTX + n == FLAG_IMM


def show(d, edits):
    print("AoWEPACK.dpl  %s" % DLL)
    print("  knobs: EXCLUDE_ROAD_OVERLAY=%s  LAVA_SURFACE_ONLY=%s"
          % (EXCLUDE_ROAD_OVERLAY, LAVA_SURFACE_ONLY))
    for lbl, cur, absent, variants, new in rows(d, edits):
        tag = ("PATCHED" if cur == new else "clean" if cur == absent
               else "OURS (earlier build)" if known(cur, absent, variants, new)
               else "*** FOREIGN ***")
        body = cur.hex() if len(cur) <= 12 else "%3d bytes" % len(cur)
        print("  %-22s %-58s %s" % (body, lbl, tag))
    miss = check_prereqs(d)
    print("  build_gripofwinter.py (owns melt/save/keep/hide): %s"
          % ("ALL 4 HOOKS PRESENT" if not miss else "MISSING\n" + "\n".join(miss)))
    print("  state: %s" % state(d, edits).upper())


def disassemble(edits):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        sys.exit("capstone not installed:  pip install capstone")
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    def sidebyside(va, old, new, title):
        print("\n==== %s @0x%08X -- INSTALLED vs REWRITTEN ====" % (title, va))
        a = {i.address: (i.bytes.hex(' '), "%s %s" % (i.mnemonic, i.op_str))
             for i in md.disasm(old, va)}
        for i in md.disasm(new, va):
            ob, ot = a.get(i.address, ("(mid-instruction)", ""))
            nb, nt = i.bytes.hex(' '), "%s %s" % (i.mnemonic, i.op_str)
            mark = "   " if (ob, ot) == (nb, nt) else "-> "
            print("  %s%08X  %-20s %-30s | %-20s %s"
                  % (mark, i.address, ob, ot, nb, nt))
        print("  changed offsets: %s"
              % [hex(i) for i in range(len(old)) if old[i] != new[i]])

    old, new = LD_CAVE_INSTALLED, build_lavadirt_image()
    sidebyside(LD_CAVE, old, new, "cave_lavadirt (build_raiseterrain_lavadirt.py)")
    print("  0x%08X call 0x55827000 (synced RNG stub, build_rng_lockstep SITES): %s"
          % (LD_CAVE + 0x12,
             "UNMOVED" if new[0x12] == 0xE8 and old[0x12:0x17] == new[0x12:0x17]
             else "*** MOVED ***"))

    sold, snew = C_SHOW_INSTALLED, build_showcave_image()
    sidebyside(C_SHOW, sold, snew, "C_SHOW (build_gripofwinter.py)")
    print("  tail 14 B (vanilla replay + jmp Show + ret 4) identical: %s"
          % (sold[C_SHOW_HEAD:] == snew[C_SHOW_HEAD:]))
    print("  every non-ours marker still ends on gripofwinter's own bytes:")
    print("    +0x0E == 0     (ice)          -> jmp 0x%08X  its vanilla replay" % C_SHOW_REPLAY)
    print("    +0x0F != 7     (grip land)    -> jmp 0x%08X  its `ret 4`" % C_SHOW_RET4)
    print("    +0x0F == 7     (raised earth) -> jmp 0x%08X  SHIMMER (the fix)" % C_SHOW_REPLAY)

    caves = [(C_UGDIRT, build_cave(), "C_UGDIRT  underground dirt -> temp earth + glow"),
             (C_SHOWGATE, build_showgate(), "C_SHOWGATE  P6 sparkle predicate")]
    if LAVA_SURFACE_ONLY:
        caves.append((C_LAVAGATE, build_lavagate(),
                      "C_LAVAGATE  surface-only gate for the lava arm"))
    used = sum(len(b) for _v, b, _l in caves)
    for va, blob, lbl in caves:
        print("\n==== 0x%08X  %s   [%d B; reservation 0x%08X..0x%08X, %d/%d used] ===="
              % (va, lbl, len(blob), RESV_LO, RESV_HI, used, RESV_HI - RESV_LO))
        for i in md.disasm(blob, va):
            print("  %08X  %-22s %s %s"
                  % (i.address, i.bytes.hex(' '), i.mnemonic, i.op_str))


def do_apply(d, edits):
    st = state(d, edits)
    if st == "applied":
        print("already applied -- nothing to do.")
        return
    if st == "foreign":
        for lbl, cur, absent, variants, new in rows(d, edits):
            if not known(cur, absent, variants, new):
                print("  FOREIGN: %s\n     got %s" % (lbl, cur.hex()[:96]))
        sys.exit("ABORT: bytes this script does not recognise. Nothing written.\n"
                 "       Someone else has patched a run we own -- investigate before\n"
                 "       forcing anything.")
    check_context(d)
    check_zone_tail(d)
    miss = check_prereqs(d)
    if miss:
        sys.exit("ABORT: build_gripofwinter.py is not applied -- it owns the melt,\n"
                 "the save/load fields and the marker-survival rule. Without it the\n"
                 "raised earth would be PERMANENT. Missing hooks:\n" + "\n".join(miss))

    kill_game()
    # Back up ONLY from a file proved free of THIS feature. st == "clean" means
    # every run we own still holds its feature-absent image. Never on --undo and
    # never on a re-tune: in both of those the file on disk is this script's own
    # earlier output, and a .pre-* snapshot of that would be a lie.
    if st == "clean" and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("backup -> %s" % os.path.basename(BACKUP))
    elif st == "retune":
        print("re-tune: rewriting our runs in place, no backup taken.")

    for va, _a, _v, new, _l in edits:
        d[off(va):off(va) + len(new)] = new
    with open(DLL, "wb") as f:
        f.write(d)
    print("APPLIED: %d byte-runs." % len(edits))


def do_undo(d, edits):
    st = state(d, edits)
    if st == "clean":
        print("not applied -- nothing to undo.")
        return
    if st == "foreign":
        for lbl, cur, absent, variants, new in rows(d, edits):
            if not known(cur, absent, variants, new):
                sys.exit("ABORT: %s is foreign (%s)" % (lbl, cur.hex()[:96]))
    kill_game()
    for va, absent, _v, new, _l in edits:
        d[off(va):off(va) + len(new)] = absent
    with open(DLL, "wb") as f:
        f.write(d)
    print("UNDONE: flag restored, cave_lavadirt back to its installed image, dead\n"
          "        tail restored, 0x%08X..0x%08X zeroed. No backup touched."
          % (RESV_LO, RESV_HI))


def main():
    args = sys.argv[1:]
    edits = build_edits()
    d = read_dll()
    if "--dis" in args:
        disassemble(edits)
    if "--undo" in args:
        do_undo(d, edits)
    elif "--apply" in args:
        do_apply(d, edits)
    else:
        show(d, edits)
        if "--dis" not in args:
            print("\n(dry run -- --apply to write, --undo to remove, --dis to disassemble)")
        return
    show(read_dll(), edits)


if __name__ == "__main__":
    main()
