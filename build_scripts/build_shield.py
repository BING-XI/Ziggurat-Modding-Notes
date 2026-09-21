# -*- coding: utf-8 -*-
r"""
build_shield.py -- new passive ability: Shield (id 0xB0). ** RANGED ATTACKS ONLY. **

    python build_scripts/build_shield.py                 dry run + disassembly (default)
    python build_scripts/build_shield.py --apply          write it
    python build_scripts/build_shield.py --undo           surgical revert (no backup touched)
    python build_scripts/build_shield.py --dis            disassemble the installed caves
    python build_scripts/build_shield.py --sim            offline maths validation, touches nothing
    python build_scripts/build_shield.py --apply --stage=reg,ranged
                                                          stage the links (default: all)

EFFECT
    MANUAL TACTICAL COMBAT (TTacticalCombatUnit, instance size 0x68)
      A unit with Shield takes -5 on the ATTACK number of every RANGED blow that arrives from
      its front hex or its front-LEFT hex, i.e. relative bearing (D-F) mod 6 in {0,5} where
      D = hex direction defender->attacker and F = the defender's facing byte (HS+0x14).
      The geometric arc test is UNCHANGED by the 2026-08-27 re-tune -- only the magnitude moved.

    AUTO-RESOLVE (TFastCombatUnit, instance size 0x64)
      Auto-resolve has no hexes and no facing, so the arc cannot be evaluated there. Shield
      instead applies the same -5 with a flat 75% probability per incoming ranged shot
      (AUTO_CHANCE below). User ruling 2026-08-27: in manual battle units mostly end up facing
      each other, so the arc's REALISED hit-rate is far above the uniform 2/6, and 75% is the
      chosen stand-in. This is a deliberate approximation, not a derived number.
      Before 2026-08-27 Shield was a silent no-op in auto-resolve (the class guard rejected
      TFastCombatUnit); it is now an explicit, rolled effect.

    ⚠ RANGED IS DISCRIMINATED BY SITE, NOT BY A FLAG. Both engines build a ranged blow through
    the SAME function, AoWE.TRangedAttackAbility.CreateRangedAttackCA @0x5576EAE4, which is
    where the `ranged` link already sits; melee goes through CreateStrikeCA and never reaches
    it. So "is this ranged" needs no test at all, in either mode. Auto-resolve callers are
    TRangedAttackAbility.fcExecuteCombatCommand @0x5576EB70 and TBreathAbility
    .fcExecuteCombatCommand @0x5576F058 (so BREATH is covered too, in both modes, exactly as
    it already was in manual). Manual callers are AoWTCPCK 0x0040C443 / 0x00421139 / 0x0042125D
    through its import thunk 0x00402874. No other module imports the function.

    ⚠ The 75% is rolled PER SHOT, not per attack action: fcExecuteCombatCommand loops
    GetAttackRepeatRA (ability VMT+0x118) times and builds one CA per shot. A 3-shot archer
    therefore gets the shield on ~2.25 of 3 shots. Manual combat calls the same constructor per
    shot, so the two modes stay structurally consistent.

    ⚠ The AI does NOT know about Shield in either mode. Target scoring runs through
    TRangedAttackAbility.fcGetDamageValueEx @0x5576E8D4 (ability VMT+0xE4, auto-resolve and
    manual) and GetDamageValueEx @0x5576E7FC (VMT+0xDC, the COMBAT PREDICTOR / raze gate / AI
    build priority). Both are left vanilla ON PURPOSE -- see DETERMINISM below. Consequence:
    the auto-resolve AI keeps shooting shielded units as if unshielded.

    ** MELEE IS DELIBERATELY NOT COVERED (user ruling, 2026-08-27). ** Vanilla Parry (0x71)
    already grants a melee defence buff (`sub dword [ebx],8` @0x55767BE1, -8 ATK, every
    bearing), so a melee Shield is conceptually redundant with an ability the game already
    ships. Shield is therefore the RANGED counterpart to Parry, and the two are meant to be
    bought separately. The three melee links this script used to install (two per-strike
    CreateStrikeCA arms and the melee1 chain tail) were removed on 2026-08-27; their analysis
    is retained under "RETIRED -- MELEE LINKS" below because the machinery is reusable and the
    sites were expensive to find. RETIRED_SITES (below) now asserts on every run that all three
    are back to their pre-Shield bytes, so a half-installed older build cannot hide.

    A second consequence of ranged-only, worth stating because it is not obvious: Shield no
    longer depends on the defender's melee-time facing, which is why build_facing_retal.py
    (AoWTCPCK.dpl deferred-retaliation facing) was reverted the same day. That script still
    works and is kept re-appliable; it is simply not needed by this feature any more.

    -5 attack is arithmetically identical to +5 defence: the roll only ever sees
    d = attack - defence, formed by one unclamped 32-bit `sub eax,edx` at 0x55726A2C
    (TCombatObject.ExecuteDamageRole). Vanilla Parry (0x71) is implemented exactly this way
    (`sub dword [ebx],8` @0x55767BE1). On this install the slope is 5 percentage points per
    point of ATK-DEF, so -5 is -25pp of hit chance.
    (Mechanically, on the ranged path: AoWE.ExecuteDamageRole @0x55725EAC rolls a d20 and sets
    the zero-damage threshold to `10 - d`, so each point of d is exactly one d20 face = 5pp.)

    UNDERFLOW IS NOT A HAZARD -- the attack byte is read back SIGN-extended:
      TRangedAttackCA VMT+0x68 -> TDamageCA.Generate @0x55729C46
      `movsx edx, byte ptr [ebp+0x10]`
    so 0xFB reads as -5, never 251. `sub byte [esp+4],5` touches ONE byte and its borrow does
    not propagate, and the consumer reads only that byte, so the upper three bytes of the
    pushed dword are irrelevant. The byte is a PRIVATE stack slot of this one CA -- not a
    shared accumulator, and there is no clamp anywhere on the path. Headroom: the whole chain
    on this install subtracts at most ~12 (slayers -5, invisibility -2/-5, Shield -5) from a
    non-negative base, so -128 is unreachable. Exact precedent for the identical instruction
    and constant: build_ranged_slayers' cave @0x5580E428 is `80 6c 24 04 05`.

DETERMINISM -- why a random draw is safe HERE, and only here
    AoW1 is token-lockstep with a shared RNG, and TSyncTE compares the SEED VALUE, i.e. the
    DRAW COUNT. A conditionally executed draw is the failure mode; an unconditional-per-peer
    one is not.

    * WHICH GENERATOR. The roll uses the raw VCL Delphi LCG, System.@RandInt, through
      AoWEPACK's own in-module thunk 0x55701080 (`jmp [0x558FB6DC]`, IAT entry verified to
      resolve to VCL30.dpl!System.@RandInt). Body @0x41303384:
          imul edx,[RandSeed],0x08088405 / inc edx / mov [RandSeed],edx / mul edx / mov eax,edx
      EAX = range in, EAX in [0,range-1] out, clobbering ONLY EAX/EDX/flags -- so ESI, EBP and
      the [esp+4] argument all survive it and no save/restore is needed.
      This is the SAME primitive every existing combat roll uses: AoWE.HitRole @0x55725DC0 and
      AoWE.ExecuteDamageRole @0x55725EBC both call it (the latter via build_combatlog_dll.py's
      transparent logging cave 0x558114E0 -- that redirect belongs to the combat log, NOT to
      the 5%/DAM-HP conversion, whatever older notes say).
      It is lockstep because AoWE.TCombat.Execute @0x557282C8 is, in its entirety,
      `System.RandSeed := AoWHSMap.Random($FFFFFF)` -- one synchronised draw that re-anchors
      the plain stream at the start of every combat. TFastCombat.Execute @0x55744A0C calls it
      first; AoWTCPCK repeats the idiom per manual action at 0x00421102.
    * WHY NOT TAoWHSMap.Random @0x5577827C. It advances [map+0x230], the very value TSyncTE
      compares, so a stray draw there would corrupt the sync word instead of riding it; it
      needs a PIC anchor for the global at 0x558FA040; and it has a live trap -- when
      GetSynchronised @0x55775608 is false it pops a modal ShowMessage and RETURNS 0, which a
      `cmp/jae` test would silently read as "apply".
    * THE ROLL IS CONDITIONAL, AND THAT IS FINE, because every condition is replicated shared
      state: victim non-nil, victim has ability 0xB0 (from the strategic unit + its items), and
      victim instance size == 0x64. None of them reads fog, a timer, a pointer value or any
      player-local setting, and the containing call chain (TArmyCombatMoveTE.ExecuteCombat ->
      TFastCombat.Execute -> ExecuteCombatRound -> fcExecute -> fcExecuteCombatCommand ->
      CreateRangedAttackCA) is turn-event driven and seeded once per combat.
    * ⚠ NOT PREDICTOR-REACHABLE -- checked, not assumed, so NO expected-value gate is needed.
      TCombatPredictor is a separate arithmetic simulator: TCombatPredictor.Execute @0x5572B028
      is ResetCombat/SetupCombat/ExecuteCombatRound*/FinishCombat, and
      TCombatPredictorUnit.ExecuteRound @0x5572AAA0 just does `target.hp -= entry.dmg`. It
      never builds a TCombatAction and takes NO random draw of any kind (no predictor address
      appears among the ~110 xrefs to @RandInt or the ~110 to TAoWHSMap.Random).
      Three independent proofs that it cannot reach this cave: CreateRangedAttackCA has exactly
      two in-DLL callers, both fcExecuteCombatCommand bodies; ability VMT slot 0xA4 has exactly
      one call site in the whole DLL (TFastCombatUnit.fcExecute @0x5574445E); and
      TStructure.CanRaze @0x5575FB80 instantiates a TCombatPredictor, never a TFastCombat.
      TCombatPredictorUnit's instance size is 0x54 anyway, so the class test would reject it.
      ⚠ This is exactly why fcGetDamageValueEx / GetDamageValueEx are left vanilla: those ARE
      speculative (prefetch, scoring, the raze gate), and a draw there WOULD be the unsafe
      placement.
    * ⚠ Do not "fix" the bias: @RandInt is a multiply-shift, not a `%`. AUTO_CHANCE = (3,4)
      is EXACTLY 75.000% because 4 divides 2^32 (RandInt(4) is literally the top two seed
      bits). (75,100) would be 75% to within ~2e-8 and is equally acceptable.

WHERE IT HOOKS -- ONE link site, one registration site.

  reg     0x557BCECF  the `call TAbilityControl.RegisterAbility` that registers vanilla
                      ability 0x8E, inside PassiveAb.RegisterPassiveAbilities.
                      ⚠ NOT 0x557BCF04 (the address the design spec named): that call is
                      already `call 0x558208B4` -- build_caster_cost.py's cave, which
                      registers 0xAC/0xAD/0xAE/0xAF. 0x557BCF39 is Drillmaster's and
                      0x557BCF6E is Magebane's. 0x557BCECF is the last intact vanilla one.
                      Replaced with `call cave_reg`; cave_reg re-issues the displaced call
                      and `ret`s back to 0x557BCED4 -- so no absolute jump is needed.

  ranged  0x55812A7B  tail of build_magebane.py's ranged cave (stock exit `jmp 0x5576EB39`).
                      ⚠ ZERO byte slack -- 0x55812A80 is live magebane code
                      (`e8 b3 d7 f3 ff`). The replacement must be exactly 5 bytes.
                      ⚠ EAX and EDX are LIVE at that tail (0x5576EB39 is `call [edx+0xb8]`),
                      so the cave must end `mov eax,esi; mov edx,[eax]` before its jmp.
                      [esp] = damage, [esp+4] = the absolute attack pushed at 0x5576EB1D
                      (traced through the whole chain: the slayers cave re-issues vanilla's
                      stolen `push eax` at 0x5580E293).
                      ESI = shooter, [EBP-4] = victim and CAN BE NIL (missile absorbed).
                      EAX/ECX/EDX are dead at entry (popped at 0x55812A78-7A).
                      The full chain into it: 0x5576EB34 -> 0x5580E400 (ranged slayers) ->
                      0x5580E190 (invisibility) -> magebane's ranged cave -> 0x55812A7B ->
                      Shield 0x558230D0 -> resume 0x5576EB39.
                      ⚠ This ONE link serves BOTH engines. Manual tactical reaches
                      CreateRangedAttackCA by a cross-module import from AoWTCPCK.dpl;
                      auto-resolve reaches it from AoWEPACK's own fcExecuteCombatCommand. The
                      mode is told apart INSIDE the cave by the victim's instance size (0x68
                      tactical vs 0x64 fast), which is free, exact and rebase-invariant.
                      ⚠ Test `>= 0x68` for tactical and `== 0x64` for fast, never `>= 0x64`
                      for fast -- that admits BOTH and would run the 75% roll in manual too.

  REVERT ORDER: Shield's ranged link sits on MAGEBANE's cave tail.
  Undo Shield BEFORE undoing Magebane -- magebane's `--undo` zeroes the whole cave, which strands
  our cave at 0x558230D0 with nothing calling it (silent, not a crash).
  ⚠ RE-APPLYING magebane is safe as of 2026-08-29: its ranged tail is chain-aware (it detects our
  cave and re-emits `jmp 0x558230D0`), and it pins that tail to RNG_TAIL so this script's site
  never moves. Only the UNDO direction still needs ordering.

RETIRED -- MELEE LINKS, removed 2026-08-27 (user ruling: Parry 0x71 already covers melee)
  Applied 2026-08-26, byte-verified, never validated in game; reverted by `--undo` on
  2026-08-27 as a SCOPE decision, not because of a defect. Kept because the sites were
  expensive to find, the register contracts are reusable by any future per-strike melee mod,
  and one of the notes is a recorded failed approach that would otherwise be re-derived.

  0x55767EBA  AoWE.TMeleeRound.CreateStrikeCA, side-0 arm  (attacker delivering)
  0x55767F2A  same function,                   side-1 arm  (defender retaliating)
              Displaced window in each: `add al,[edi] ; push eax ; mov eax,[ebx+off]`
              (0x55767EBA `...+0x10`, 0x55767F2A `...+0x14`). That `push eax` is the ATTACK
              ARGUMENT to TStrikeCA.Generate ([ebp+0x10] there, read back with movsx), not a
              save -- so a modifier is `sub byte [esp],N` on the already-pushed value, and
              pushad must NOT be used because [esp] has to stay on the argument.
              ⚠ These are the PER-STRIKE sites, and that was the whole point.
              ⚠ RECORDED FAILED APPROACH -- do not "rediscover" it as a cheap melee re-add:
              the melee3 chain tail 0x55812A2E (in CalculateStrikes) was the design spec's
              melee link, but CalculateStrikes runs ONCE PER ROUND at 0x00409208, before any
              facing change, so it cannot express a per-strike arc. Never move a melee link
              back there.
              ⚠ The side is decided STRUCTURALLY, by which arm's cave you are in -- nothing
              reads the strike record's side byte at [edi+0x0C]. In BOTH arms EBP is the
              striker; the receiving unit is the OTHER round field:
              arm A victim = [ebx+0x14], arm B victim = [ebx+0x10].
              ⚠ Neither arm proves its victim non-nil: arm A dereferences [ebx+0x10] but only
              LOADS [ebx+0x14] (0x55767ECE). A `test eax,eax / je` in each cave was mandatory,
              not defensive style.
              Live at the hook: EBX (round), ESI (the CA), EDI (strike record), EBP (striker);
              EAX/ECX/EDX free. Covered manual tactical melee + retaliation (via AoWTCPCK
              0x00409B5E) and auto-resolve (fcExecuteCombatCommand @0x55767097). Auto-resolve
              passes TFastCombatUnit (instance size 0x64), which GETHEX's class guard rejects,
              so these melee links were a silent no-op in auto-resolve.
              ⚠ DO NOT carry that "silent no-op" over to the RANGED link -- it stopped being
              true on 2026-08-27. The ranged cave now tests the same instance size EXPLICITLY
              and gives 0x64 a 75% roll instead of nothing (see AUTO_CHANCE). If these melee
              links are ever revived, decide deliberately whether they get the same treatment;
              inheriting the old no-op by accident is the easy mistake here.
              Note the fast unit DOES pass the ability query (its VMT+0xA8 is the real
              GetAbilityEnabled, inherited from TCombatUnit @0x55725004), so that guard is
              load-bearing on a live path and must be kept for any future melee link.

  0x55812A09  tail of build_magebane.py's melee1 cave (stock exit `jmp 0x557666CF`).
              (was 0x558129EC before magebane's 2026-08-29 re-tune)
              AoWE.CreateStrikeCA -- free swing during movement + touch abilities.
              Chain: 0x5580E070 slayers -> 0x5580E370 invis -> 0x558129C0 magebane -> tail.
              ESI = target, EBP = attacker, BL = absolute attack byte; 0x55766699 `add bl,4` /
              0x5576669C `add byte [esp+3],4` is the alignment bonus, so BL is the attack and
              [esp+3] the damage. Resume 0x557666CF.
              ⚠ This byte run lives INSIDE MAGEBANE'S CAVE. Reverting it means restoring
              magebane's jump, NOT zeroing. ⚠ The ADDRESS moved to 0x55812A09 on 2026-08-29
              when magebane was re-tuned -- see the M1_TAIL comment. Never hand-edit it.

THE ARC MATHS
    Melee and ranged use the SAME exact primitive, so a Shield arc and a breath cone can never
    disagree: r = HSEngine.dHXtoRad (AoWEPACK thunk 0x5570266C), hn = HSEngine.dHXtoHN (thunk
    0x557026A4, a spiral index), then inline
        k      = hn - (3*r*(r-1) + 1)
        sector = ((k + ((r-1) div 2)) div r) mod 6
        dir    = sector + 1
    ⚠ dHXtoHNfast (thunk 0x557026AC) is a sign-of-dx/dy quadrant classifier, exact only for
    adjacency and 29.5% wrong beyond it. Never use it at range.
    ⚠ GetRangedDirIndex is a missile sprite ANGLE, not a hex direction.
    `--sim` reproduces all 60 entries of AoWTC.BreathDir @0x004673A8 from that formula and
    checks the pre-mod quotient never exceeds 6 (one cmp/sub in the cave is then enough).
    Both thunks are `jmp [IAT]` into HSEPack.dpl, verified `ret 4`, and both preserve
    EBX/ESI/EDI/EBP.

    ⚠ WHAT --sim's 60/60 DOES *NOT* PROVE. It re-derives r from hn in Python and never calls
    the engine, so it validates the k/sector ring decomposition ONLY. A reversed direction
    sense inside dHXtoHN would sail straight through it and silently mirror the arc.
    That gap is closed separately, by reading HSEPack.dpl (QA, 2026-08-27) -- keep this so a
    future session does not re-derive it:
      * HSEngine.TranslateHX @0x5560E298 does `sub ecx,eax` (x2-x1) and `sub esi,edx` (y2-y1),
        so dHXtoHN(x1,y1,x2,y2) is the bearing FROM (x1,y1) TO (x2,y2). SHIELD_ARC loads the
        DEFENDER into (EAX,EDX) and the ATTACKER into (ECX,[esp]), so D = defender->attacker,
        which is what the arc test assumes.
      * dHXtoHNfast @0x5560E338 returns 1 for dx=0, y2<y1, and HNtoXYTable @0x5562E024 decodes
        to 1=(0,-1) 2=(+1,-1) 3=(+1,0) 4=(0,+1) 5=(-1,0) 6=(-1,-1): direction 1 is North and
        the numbering runs CLOCKWISE. So ARC=(0,5) is front + one step ANTICLOCKWISE in MAP
        coordinates. Whether that is the left-hand side ON SCREEN still needs the user's eyes --
        the sprite/display transform is the one link no static read settles (see ARC below).

GETTING THE HEXES -- read the fields, never the VMT
    ⚠ On TTacticalCombatUnit, VMT +0x74 is GetResistance and +0x78 is GetDamage. GetXhx/GetYhx
    live at those offsets on the HS classes only. Feeding Resistance and Damage into the
    direction maths would shield the wrong arc with NO crash. The chain is
        obj -> [obj+0x60] = HS -> [HS+0x04] = TMapField -> X = byte[field+0x10],
                                                          Y = byte[field+0x11]
    (TUnitHS.GetXhx @0x55783F50 is literally `mov eax,[eax+4]; mov al,[eax+0x10]; ret`, and it
    writes only AL, so the direct read is both equivalent and safer.)
    ⚠ Mandatory class guard first: `mov ecx,[obj]; cmp dword [ecx-0x1C],0x68; jb bad`.
    [obj+0x60] is an HS only at instance size 0x68 (TTacticalCombatUnit). TFastCombatUnit is
    0x64 and its +0x60 is NOT an HS. Instance sizes read from VMT-0x1C in the live files:
      TCombatObject 0x4C, TCombatPredictorUnit 0x54, TCombatUnit 0x5C, TFastCombatUnit 0x64
      (AoWEPACK), TTacticalCombatUnit 0x68 (AoWTCPCK, class-ref 0x00412B4C).
    The guard survives inside GETHEX as a safety net, but the `ranged` cave now makes the same
    test EXPLICITLY and branches on it, because the size is also the manual/auto discriminator.
    (A wall or a bare combat object can never get that far: TCombatObject.GetAbilityEnabled
    @0x557268D4 is `return 0`, so the ability query filters them first. TFastCombatUnit does
    NOT override VMT+0xA8 -- it inherits TCombatUnit.GetAbilityEnabled @0x55725004, which
    nil-checks [+0x4C] and forwards to the item-searching strategic API at VMT+0x148, so an
    item-granted Shield is honoured in auto-resolve exactly as in manual.)

CAVE  0x55823000..0x55823FFF -- THIS SCRIPT OWNS THE WHOLE PAGE.
    ⚠ NOT 0x55822A00 (the design spec's address): that is inside
    build_shipyard_income.py's declared exclusive reservation 0x55822000..0x55822FFF, whose
    --apply zero-checks and whose --undo zero-asserts across the whole page. The bytes there
    are zero, but a zero run is not a reservation.
    Verified before claiming: all-zero live and in AoWEPACK_original_backup.dpl, zero .reloc
    type-3 entries, inside CODE (0x60000020), and named by no other build script.
    Caves are rel32/register-only => position-independent; the .dpl rebases. The only absolute
    datum is the ability name, reached by a call/pop PIC anchor.

Release/Ability.pfs
    ⚠ Tag 9 OVERWRITES the selection mask the cave passes, and tag 6 OVERWRITES the level-up
    cost -- both go through the same bidirectional AoWE.TAbility.ReadWrite @0x5574F07C
    (tag 6 <-> [ability+0x14], tag 9 <-> [ability+0x20], width 2). Record for ability 0xB0 is
    id 0xB0+10 = 186.

    ⚠ RECORD 186 NOW EXISTS (measured 2026-08-27; earlier revisions of this docstring and of
    both Zig notes say it does not -- they predate the round-trip). An AoWDevEd save minted
    records 182..186 (abilities 0xAC..0xB0: the four caster abilities plus Shield). `max_rid`
    is 181 in every Ability.pfs backup on disk and 179 in `Release - Vanilla`, which is how the
    change is dated. Consequences, all of them live:
      * tag 9 arrives as 0x0111. That has astUnit's 0x100 but NOT 0x200, and hero level-up
        needs BOTH (see the ability-selection-mask note), so Shield is currently not properly
        hero-buyable. --apply now writes tag 9 = 0x03FF and repairs the CRC. This is a real
        fix, not bookkeeping.
      * tag 6 = 8 is present, so the DATA FILE now permanently OVERRIDES EXPAND_COST below.
        Shield's hero level-up cost is 8, the same as Parry, whatever this script stores. The
        cave's `mov dword [eax+0x14],6` is decorative from here on. Changing the number is an
        AoWDevEd edit, not a script edit.
      * record 186 carries NO tag 5, so Shield has no info-card description. Adding one is a
        record-LENGTH change, so it must go through AoWDevEd -- never through this script,
        which only ever rewrites fixed-width values in place.

⚠ THE HERO LEVEL-UP COLUMN IS NOT THIS SCRIPT'S TO WRITE -- AND EDITING herodlg_cats.py IS NOT
  ENOUGH. Shield is hero-buyable, so it needs a column in the level-up dialog. The category map
  lives in `herodlg_cats.py`, but that file is only a SOURCE: the 256-byte lookup table is
  baked into AoW.exe and AoWCompat.exe by `build_herodlg_columns.py`
  (`exe.wr(D["cattbl"], CATS.lookup_table())`). Adding `176: (2, "Shield")` to the dict and
  stopping there leaves the two executables holding the OLD table, so Shield silently appears in
  the Magic column (herodlg_cats.DEFAULT_CAT = 4) instead of Melee -- with every verifier,
  including this script's, reporting green. Found by QA on 2026-08-27, after exactly that.
  The fix is `python build_scripts/build_herodlg_columns.py --apply` (it writes BOTH exes, so
  the AoW.exe / AoWCompat.exe lockstep applies: they must still differ only at file 0x3BB7C).
"""
import os, sys, struct, shutil, zlib

# The Windows console defaults to cp1252, which cannot encode the U+26A0 warning sign used in
# this script's output. Without this, --apply writes its bytes correctly and THEN dies with a
# UnicodeEncodeError partway through printing its checklist, exiting 1 -- which reads as a failed
# patch when it was actually a successful one. Degrade unencodable glyphs instead of raising.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    sys.exit("needs keystone-engine and capstone:  py -m pip install keystone-engine capstone")

# game dir = two levels up from this script (<game>/Modding Resources/build_scripts/);
# override with AOW_GAME_DIR. No machine-specific path may ever appear in this file.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-shield")
DLL_BASE = 0x55700000
TCPCK = os.path.join(GAME, "AoWTCPCK.dpl")          # read-only, for --sim
TCPCK_BASE = 0x00400000

# ---------------------------------------------------------------- tuning knobs
ABILITY_ID   = 0xB0
ABILITY_NAME = b"Shield"
SEL_TYPES    = 0x03FF        # astUnit..astEditor -- hero-buyable. Ability.pfs tag 9 overrides.

# Relative bearing (D-F) mod 6 that Shield covers. 0 = dead ahead, 5 = one step
# ANTIclockwise = front-LEFT (user, 2026-08-26).
# The MAP handedness is settled: HNtoXYTable @0x5562E024 decodes 1=(0,-1) 2=(+1,-1) 3=(+1,0)
# 4=(0,+1) 5=(-1,0) 6=(-1,-1), so direction 1 is North and the numbering runs clockwise; 5 is
# therefore one step anticlockwise of the facing. The SCREEN handedness is not -- the
# sprite-set/display transform is the one link no static read settles.
# ⚠ If the in-game look shows the protected side is the wrong one, flip this to (0, 1) and
# re-apply. Nothing else changes; --apply rewrites the cave in place.
ARC = (0, 5)
SHIELD_ATK = 5               # points off the attack number when Shield applies (both modes)

# Auto-resolve probability, as (numerator, denominator) -- Shield applies iff
# RandInt(den) < num. Auto-resolve has no hexes and no facing, so this stands in for ARC.
# (3,4) = exactly 75.000%: RandInt is a multiply-shift, and 4 divides 2^32, so RandInt(4) is
# literally the top two seed bits. (75,100) is the same to within ~2e-8 if a finer dial is
# wanted; any (num,den) with 1 <= num < den <= 0x7FFFFFFF assembles.
# ⚠ den is emitted as `mov eax,imm32` (always 5 bytes) and num as `cmp eax,imm` -- keystone
# WILL shorten the cmp to imm8 for num < 128, which is correct here but is exactly the family
# of encodings the project's `push 0xFFFF` trap lives in. --dis prints it; read it.
AUTO_CHANCE = (3, 4)

# Hero level-up point cost. ⚠ A BALANCE PLACEHOLDER PICKED BY THE BUILD, NOT BY THE USER --
# confirm the number before the AoWDevEd round-trip, because after that the data file wins.
#
# The field is TAbility.FExpandCost at [ability+0x14]. VERIFIED, not assumed:
#   AoWE.TAbility.ReadWrite @0x5574F07C decompiles to
#       (**(code **)(*stream + 0x2c))(stream, ability + 0x14, 6);
#   i.e. tag 6 <-> [ability+0x14], passed BY ADDRESS, through the same bidirectional ReadWrite
#   the loader and AoWDevEd's saver both drive. So on load the file value overwrites whatever
#   the cave stored, exactly as tag 9 does for the selection mask.
# ⚠ CreateEnhancementAbility @0x5576601C never initialises it -- it writes only [+0xC] = id,
#   [+0x8] = name and [+0x20] = mask. With no store here and no tag 6 in the data file the
#   ability is PERMANENTLY FREE at level-up, not merely displayed as free.
#   Live proof of both halves: record 180 (Magebane 0xAA) carries NO tag 6 -- free; record 123
#   (Parry 0x71) carries 8; record 181 (Drillmaster 0xAB) carries 10 even though its cave stores
#   nothing, so the editor's own cost field can set/override the value at save time too.
# Reference points for the balance call: Parry 8 (-8 ATK, melee, every bearing), Drillmaster 10,
# the four caster abilities 20/40/40/40. Shield is -5 on 2 of 6 bearings, ranged only (75% of
# ranged shots in auto-resolve), so it is priced below Parry. Change the number and re-run
# --apply; the cave is rewritten in place (no revert needed).
EXPAND_COST = 6
# ------------------------------------------------------------------------------

# engine entry points (all reached by rel32 => position-independent)
REGISTER_ABIL = 0x55750238   # AoWE.TAbilityControl.RegisterAbility  (EAX=ctrl, EDX=ability)
CREATE_ENH    = 0x5576601C   # AoWE.CreateEnhancementAbility        (EAX=id, EDX=name, CX=mask)
DHX_TO_RAD    = 0x5570266C   # thunk -> HSEPack.dpl!HSEngine.dHXtoRad  (EAX=x1 EDX=y1 ECX=x2 [esp]=y2, ret 4)
DHX_TO_HN     = 0x557026A4   # thunk -> HSEPack.dpl!HSEngine.dHXtoHN   (same tuple, ret 4)
GAE           = 0xA8         # combat-object VMT slot: GetAbilityEnabled(EDX=id) -> AL
# AoWEPACK's own import thunk `jmp [0x558FB6DC -> VCL30.dpl!System.@RandInt]`. In-module, so a
# rel32 `call` to it is rebase-invariant and needs no PIC anchor. EAX = range in, EAX in
# [0,range-1] out; clobbers ONLY EAX/EDX/flags. Same primitive as HitRole/ExecuteDamageRole.
# ⚠ NOT TAoWHSMap.Random @0x5577827C -- see the DETERMINISM block in the module docstring.
RANDINT       = 0x55701080

# The two instance sizes the `ranged` cave branches on. Read from VMT-0x1C, so they are the
# engine's own numbers, not layout guesses.
SZ_TACTICAL   = 0x68         # AoWTC..TTacticalCombatUnit -- manual, has hexes + facing
SZ_FAST       = 0x64         # AoWE..TFastCombatUnit      -- auto-resolve, has neither

# ---- sites --------------------------------------------------------------------------------
REG_INJ   = 0x557BCECF; REG_ORIG   = bytes.fromhex("e8 64 33 f9 ff")   # call 0x55750238
RNG_TAIL  = 0x55812A7B; RNG_DEST   = 0x5576EB39     # magebane ranged cave exit

# ---- RETIRED sites: the three melee links removed 2026-08-27 --------------------------------
# These are NOT patched any more (Parry 0x71 already covers melee -- see the RETIRED block in
# the module docstring). They are listed so every run can PROVE they are back to their
# pre-Shield bytes.
#
# ⚠ This guard is the thing that makes the dangerous shortcut impossible. If someone were to
# drop the melee entries from SITES and --apply over an installed older build, the three melee
# sites would stay patched while the cave beneath them was rewritten to the shorter ranged-only
# layout -- 0x55767EBA would then jump to 0x558230D0, which in THIS layout is the `ranged`
# sub-cave: it reads [ebp-4] as the victim inside a CreateStrikeCA frame and exits
# `jmp 0x5576EB39` into the RANGED function from inside melee. Guaranteed corruption, and every
# verifier would report green because the sites are no longer in SITES. Hence: checked always,
# on every code path, including --undo and --dis.
#
# ⚠ This address is inside build_magebane.py's melee1 cave, so its clean state is MAGEBANE'S JUMP
# (jmp 0x557666CF), not zeros. Never zero it and never hand-edit it.
#
# ⚠⚠ IT MOVES WHEN MAGEBANE IS RE-TUNED. It was 0x558129EC until 2026-08-29, when magebane lifted
# its `imul` into cave_count (+27 B) and every block after `count` shifted down; the melee1 tail is
# now 0x55812A09. The old value then sat mid-body and this guard aborted the whole script with
# "a PRE-2026-08-27 build of Shield is half-installed" -- a completely false diagnosis.
# If you re-tune magebane again, re-read the tail from `build_magebane.py --show` (last
# instruction of the melee1 block) and update this. Magebane's RANGED tail does NOT move: it is
# pinned to RNG_TAIL precisely because this script patches it.
# (Running build_magebane.py is safe again as of 2026-08-29 -- its ranged tail is now chain-aware
# and re-emits the jump into our cave rather than the stock exit.)
M1_TAIL = 0x55812A09; M1_DEST = 0x557666CF          # magebane melee1 cave exit
RETIRED_SITES = {
    0x55767EBA: (bytes.fromhex("02 07 50 8b 43 10"),
                 "CreateStrikeCA side-0 arm (vanilla bytes)"),
    0x55767F2A: (bytes.fromhex("02 07 50 8b 43 14"),
                 "CreateStrikeCA side-1 arm (vanilla bytes)"),
    # derived, not hard-coded, so a mistyped constant cannot pass as magebane's jump.
    # (jmp32() itself is defined below this block, hence the inline encoding.)
    M1_TAIL:    (b"\xE9" + struct.pack("<i", M1_DEST - (M1_TAIL + 5)),
                 "magebane melee1 tail (magebane's own jmp %08X)" % M1_DEST),
}

CAVE_VA    = 0x55823000
CAVE_LIMIT = 0x1000          # the whole page is Shield's reservation

STAGES = ("reg", "ranged")

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)
PH_NAME = 0x61111116


_ASM_CACHE = {}


def asm(src, va):
    """Memoised: prior_caves() re-assembles the same sub-caves thousands of times."""
    key = (src, va)
    if key not in _ASM_CACHE:
        _ASM_CACHE[key] = bytes(ks.asm(src, va)[0])
    return _ASM_CACHE[key]


def jmp32(frm, to):
    return b"\xE9" + struct.pack("<i", to - (frm + 5))


def call32(frm, to):
    return b"\xE8" + struct.pack("<i", to - (frm + 5))


def fix_pic(code, va, pop_op, subs):
    """`call <anything> ; pop <reg>` -> a delta anchor; rewrite the placeholders.

    The call's rel32 is zeroed so it falls straight through to the pop, which then holds the
    RUNTIME address of itself. Every placeholder becomes (target - anchor), so `lea reg,[reg+ph]`
    yields the rebased target. This is why nothing here uses an absolute data address: the .dpl
    never loads at its preferred base.

    ⚠ never write the anchor as `call $+5` -- keystone assembles that to NOTHING, silently, and
    the scan below then latches onto an earlier E8 and zeroes ITS rel32 (in this cave that would
    be `call RegisterAbility`). build_drillmaster.py:fix_pic carries the same warning.
    """
    code = bytearray(code)
    i = next(k for k in range(len(code) - 5) if code[k] == 0xE8 and code[k + 5] == pop_op)
    anchor = va + i + 5
    code[i + 1:i + 5] = struct.pack("<i", 0)
    for ph, tgt in subs:
        hits = [k for k in range(len(code) - 3) if code[k:k + 4] == struct.pack("<I", ph)]
        if len(hits) != 1:
            sys.exit("placeholder %#x found %d times" % (ph, len(hits)))
        code[hits[0]:hits[0] + 4] = struct.pack("<i", tgt - anchor)
    return bytes(code)


# ============================================================== cave sources
def src_gethex():
    """ESI = combat object -> ESI = HS, EBX = x, EDI = y ; CF = 1 on failure. Clobbers ECX."""
    return """
        test esi, esi
        jz   _gh_bad
        mov  ecx, [esi]
        cmp  dword ptr [ecx - 0x1C], 0x68
        jb   _gh_bad
        mov  esi, [esi + 0x60]
        test esi, esi
        jz   _gh_bad
        mov  ecx, [esi + 4]
        test ecx, ecx
        jz   _gh_bad
        movzx ebx, byte ptr [ecx + 0x10]
        movzx edi, byte ptr [ecx + 0x11]
        clc
        ret
    _gh_bad:
        stc
        ret
    """


def src_arc(gethex_va, arc):
    """ret 8 ; [ebp+8] = defender obj, [ebp+0xC] = attacker obj -> AL = 1 when inside the arc."""
    # diff = (D-1) - (F-1) lands in -5..5, so each covered bearing b needs both b and b-6.
    vals = sorted({v for b in arc for v in (b, b - 6) if -5 <= v <= 5})
    tests = []
    for v in vals:
        if v == 0:
            tests.append("        test eax, eax\n        jz   _arc_hit")
        else:
            tests.append("        cmp  eax, %d\n        je   _arc_hit" % v)
    return """
        push ebp
        mov  ebp, esp
        sub  esp, 0x14
        push ebx
        push esi
        push edi
        mov  esi, [ebp + 8]
        call 0x%X
        jc   _arc_fail
        movzx eax, byte ptr [esi + 0x14]
        dec  eax
        cmp  eax, 6
        jae  _arc_fail
        mov  [ebp - 0x14], eax
        mov  [ebp - 0x04], ebx
        mov  [ebp - 0x08], edi
        mov  esi, [ebp + 0x0C]
        call 0x%X
        jc   _arc_fail
        mov  [ebp - 0x0C], ebx
        mov  [ebp - 0x10], edi
        push dword ptr [ebp - 0x10]
        mov  eax, [ebp - 0x04]
        mov  edx, [ebp - 0x08]
        mov  ecx, [ebp - 0x0C]
        call 0x%X
        test eax, eax
        jz   _arc_fail
        mov  ebx, eax
        push dword ptr [ebp - 0x10]
        mov  eax, [ebp - 0x04]
        mov  edx, [ebp - 0x08]
        mov  ecx, [ebp - 0x0C]
        call 0x%X
        mov  ecx, ebx
        dec  ecx
        imul ecx, ebx
        lea  ecx, [ecx + ecx*2]
        inc  ecx
        sub  eax, ecx
        mov  ecx, ebx
        dec  ecx
        shr  ecx, 1
        add  eax, ecx
        xor  edx, edx
        div  ebx
        cmp  eax, 6
        jb   _arc_nowrap
        sub  eax, 6
    _arc_nowrap:
        sub  eax, [ebp - 0x14]
%s
        jmp  _arc_fail
    _arc_hit:
        mov  eax, 1
        jmp  _arc_done
    _arc_fail:
        xor  eax, eax
    _arc_done:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret  8
    """ % (gethex_va, gethex_va, DHX_TO_RAD, DHX_TO_HN, "\n".join(tests))


def src_ranged(arc_va, pen, auto):
    """ranged chain tail -- the ONLY combat link Shield installs, serving BOTH engines.

    ESI = shooter, [EBP-4] = victim (CAN BE NIL), [esp] = damage, [esp+4] = the attack dword.
    EAX/ECX/EDX are dead at entry.

    Shape:
        victim nil?                       -> out
        victim lacks ability 0xB0?        -> out
        instance size >= 0x68 (tactical)  -> geometric arc test, unchanged
        instance size == 0x64 (fast)      -> RandInt(den) < num
        anything else                     -> out (belt-and-braces; nothing else can get here)

    ⚠ EAX/EDX must be re-established before the exit jmp: 0x5576EB39 is `call [edx+0xb8]`.
    ⚠ Both branches must leave ESP exactly where they found it before `sub byte [esp+4]`:
      SHIELD_ARC is `ret 8` so it eats its own two pushes, and the @RandInt call/ret pair is
      balanced. Any stray push would silently shift the argument slot.
    ⚠ @RandInt clobbers EAX/EDX/flags only, so ESI/EBP and the stack argument survive it with
      no save/restore -- verified against the VCL30 body, not assumed.

    `auto is None` reproduces the PRE-2026-08-27 body byte for byte (no discriminator, no
    roll, arc-only, silent no-op in auto-resolve). It exists so prior_caves() can recognise an
    already-installed older Shield and rewrite it IN PLACE. Do not delete it.
    """
    if auto is None:
        return """
            mov  eax, [ebp - 4]
            test eax, eax
            je   _rg_out
            mov  edx, 0x%X
            mov  ecx, [eax]
            call dword ptr [ecx + 0x%X]
            test al, al
            je   _rg_out
            push esi
            push dword ptr [ebp - 4]
            call 0x%X
            test al, al
            je   _rg_out
            sub  byte ptr [esp + 4], %d
        _rg_out:
            mov  eax, esi
            mov  edx, [eax]
            jmp  0x%X
        """ % (ABILITY_ID, GAE, arc_va, pen, RNG_DEST)

    num, den = auto
    return """
        mov  eax, [ebp - 4]
        test eax, eax
        je   _rg_out
        mov  edx, 0x%X
        mov  ecx, [eax]
        call dword ptr [ecx + 0x%X]
        test al, al
        je   _rg_out
        mov  eax, [ebp - 4]
        mov  ecx, [eax]
        mov  ecx, [ecx - 0x1C]
        cmp  ecx, 0x%X
        jb   _rg_fast
        push esi
        push dword ptr [ebp - 4]
        call 0x%X
        test al, al
        je   _rg_out
        jmp  _rg_hit
    _rg_fast:
        cmp  ecx, 0x%X
        jne  _rg_out
        mov  eax, %d
        call 0x%X
        cmp  eax, %d
        jae  _rg_out
    _rg_hit:
        sub  byte ptr [esp + 4], %d
    _rg_out:
        mov  eax, esi
        mov  edx, [eax]
        jmp  0x%X
    """ % (ABILITY_ID, GAE, SZ_TACTICAL, arc_va, SZ_FAST, den, RANDINT, num, pen, RNG_DEST)


def src_reg(cave_va, expand_cost=None):
    """Re-issue the displaced RegisterAbility (ability 0x8E), then create + register Shield.

    Entered by `call`, so the trailing `ret` lands on 0x557BCED4 with no absolute jump.
    At entry EAX = EBX = the TAbilityControl and EDX = the 0x8E ability, both set by vanilla
    at 0x557BCECB/0x557BCECD. EBX holds the control for the whole function.

    The FExpandCost store goes BETWEEN CreateEnhancementAbility and RegisterAbility because EAX
    is the freshly built ability only in that window (`mov edx,eax` below consumes it).
    ⚠ `is not None`, not truthiness: cost 0 is a legitimate, deliberate choice and must emit the
    store, otherwise "explicitly free" and "nobody set it" assemble to the same bytes.
    """
    cost = ("        mov  dword ptr [eax + 0x14], %d\n" % expand_cost) \
        if expand_cost is not None else ""
    return """
        call 0x%X
        call 0x%X
        pop  eax
        lea  edx, [eax + 0x%X]
        mov  ecx, 0x%X
        mov  eax, 0x%X
        call 0x%X
%s        mov  edx, eax
        mov  eax, ebx
        call 0x%X
        ret
    """ % (REGISTER_ABIL, cave_va, PH_NAME, SEL_TYPES, ABILITY_ID, CREATE_ENH, cost,
           REGISTER_ABIL)


# ============================================================== cave layout
def build_cave(arc=ARC, pen=SHIELD_ATK, cost=EXPAND_COST, auto=AUTO_CHANCE):
    """Lay the sub-caves out back to back at CAVE_VA. -> (blob, {label: (va, len)}).

    Every sub-cave only references addresses of things EARLIER in the list, so one forward pass
    resolves everything -- no iteration, no label arithmetic, no `call $+5`.

    ⚠ `mk` is a CALLABLE taking the sub-cave's final VA, and it is invoked only AFTER the
    4-alignment padding has been laid down. Assembling first and padding afterwards moves the
    block without moving what keystone assumed, so every rel32 in it lands N bytes past its
    target -- `call dHXtoRad` became `call dHXtoRad+2`, silently, in the first build of this
    script. Only the `--dis` read caught it.
    """
    parts, blob = [], bytearray()

    def emit(label, mk, desc):
        while len(blob) % 4:                                     # 4-align for a readable --dis
            blob.append(0)
        va = CAVE_VA + len(blob)
        code = mk(va) if callable(mk) else mk
        blob.extend(code)
        parts.append((label, va, len(code), desc))
        return va

    gethex = emit("GETHEX", lambda va: asm(src_gethex(), va),
                  "class guard + hex read (ESI=obj -> ESI=HS, EBX=x, EDI=y, CF=fail)")
    arcva = emit("SHIELD_ARC", lambda va: asm(src_arc(gethex, arc), va),
                 "ret 8; [ebp+8]=defender [ebp+0xC]=attacker -> AL, arc %s" % (tuple(arc),))
    # csca_a / csca_b / melee1 used to sit here. Removed 2026-08-27 -- Shield is ranged-only.
    emit("ranged", lambda va: asm(src_ranged(arcva, pen, auto), va),
         "ranged link, BOTH engines: tactical(0x%X)=arc %s, fast(0x%X)=%s, -%d ATK"
         % (SZ_TACTICAL, tuple(arc), SZ_FAST,
            "no-op" if auto is None else "%d/%d roll" % (auto[0], auto[1]), pen))

    # cave_reg needs the name blob's VA, which follows it: placeholder + fix_pic, exactly as
    # build_drillmaster.py does. `lea edx,[eax+imm32]` is length-stable, so the patch is in place.
    while len(blob) % 4:
        blob.append(0)
    reg_va = CAVE_VA + len(blob)
    probe = fix_pic(asm(src_reg(reg_va, cost), reg_va), reg_va, 0x58, [(PH_NAME, 0)])
    name_blob_va = (reg_va + len(probe) + 3) & ~3
    name_va = name_blob_va + 8                                   # past refcount+length header
    reg = fix_pic(asm(src_reg(reg_va, cost), reg_va), reg_va, 0x58, [(PH_NAME, name_va)])
    if len(reg) != len(probe):
        sys.exit("cave_reg changed length between passes -- layout is unstable")
    emit("cave_reg", reg, "re-register 0x8E + create/register Shield 0x%02X, level-up cost %s"
         % (ABILITY_ID, "not set (PERMANENTLY FREE)" if cost is None else cost))

    while CAVE_VA + len(blob) < name_blob_va:
        blob.append(0)
    # refcount -1 so Delphi's LStrAsg shares the literal and never frees it
    emit("name_blob", struct.pack("<iI", -1, len(ABILITY_NAME)) + ABILITY_NAME + b"\x00",
         'AnsiString literal "%s" (pointer = blob+8)' % ABILITY_NAME.decode())

    labels = {l: (va, n, desc) for l, va, n, desc in parts}
    return bytes(blob), labels


CAVE, LABELS = build_cave()
ARC_VA = LABELS["SHIELD_ARC"][0]
REG_VA = LABELS["cave_reg"][0]

if len(CAVE) > CAVE_LIMIT:
    sys.exit("cave is %d bytes, reservation is %d" % (len(CAVE), CAVE_LIMIT))

# Every cave variant this script could have shipped, so a re-tune (a different ARC, a different
# magnitude, or a different hero level-up cost) is a REWRITE IN PLACE and never needs a revert.
# There is almost no backup stack left; "revert and re-apply" is not a procedure.
#
# ⚠ The cost dimension is in here because it CHANGES THE CAVE'S LENGTH: with EXPAND_COST set,
# cave_reg gains a 7-byte `mov dword [eax+0x14],imm32` and everything after it (the name blob)
# slides. Leave a tunable out of this list and the installed cave matches neither CAVE nor any
# variant, cave_state() returns "other", and --apply aborts on a file it wrote itself.
#
# ⚠ AUTO=None IS THE 2026-08-26 LAYOUT and it is load-bearing right now: that is the build
# currently on disk (arc-only, -4, silent no-op in auto-resolve). Without it in this list the
# 2026-08-27 re-tune could not recognise its own predecessor and would abort. The auto branch
# also changes the cave's length, so it slides the name blob exactly as the cost does.
#
# Computed lazily, and asm() is memoised, so the whole product costs well under a second --
# and only on the re-tune path, which is the only path that asks.
_PRIOR_BUILDS = None
_PRIOR_AUTOS = [None, (3, 4), (1, 2), (2, 3), (4, 5), (9, 10),
                (75, 100), (50, 100), (80, 100), (90, 100)]


def prior_builds():
    """[(blob, labels)] for every cave this script could previously have written."""
    global _PRIOR_BUILDS
    if _PRIOR_BUILDS is None:
        _PRIOR_BUILDS = []
        autos = list(_PRIOR_AUTOS)
        if AUTO_CHANCE is not None and tuple(AUTO_CHANCE) not in [
                a for a in autos if a is not None]:
            autos.append(tuple(AUTO_CHANCE))
        for _a in autos:
            for _arc in ((0, 5), (0, 1)):
                for _p in range(1, 13):
                    for _c in [None] + list(range(0, 33)):
                        if (_arc, _p, _c, _a) == (tuple(ARC), SHIELD_ATK, EXPAND_COST,
                                                  None if AUTO_CHANCE is None
                                                  else tuple(AUTO_CHANCE)):
                            continue
                        try:
                            _PRIOR_BUILDS.append(build_cave(_arc, _p, _c, _a))
                        except Exception:                        # noqa: BLE001
                            pass
    return _PRIOR_BUILDS


def prior_caves():
    return [blob for blob, _labels in prior_builds()]


def prior_site_bytes(key):
    """Byte runs a PREVIOUS build of this script could have left at `key`'s injection site.

    ⚠ Without this a re-tune that CHANGES THE CAVE'S LENGTH aborts on its own output. The
    2026-08-27 pass is exactly that case: adding the auto-resolve branch grew the cave by 36
    bytes, so cave_reg slid 55823104 -> 55823124 and the live `call` at 557BCECF matched
    neither REG_ORIG (vanilla) nor the new call. That is a MOVED OWN LINK, not a third-party
    collision, and treating it as the latter would have blocked the in-place rewrite and
    invited the "revert and re-apply" procedure this project forbids.
    """
    out = set()
    for _blob, labels in prior_builds():
        if key == "reg":
            out.add(call32(REG_INJ, labels["cave_reg"][0]))
        elif key == "ranged":
            out.add(jmp32(RNG_TAIL, labels["ranged"][0]))
    return out

SITES = {
    "reg":    (REG_INJ,  REG_ORIG,     call32(REG_INJ, REG_VA),
               "RegisterAbility call @%08X -> cave_reg" % REG_INJ),
    "ranged": (RNG_TAIL, jmp32(RNG_TAIL, RNG_DEST), jmp32(RNG_TAIL, LABELS["ranged"][0]),
               "magebane ranged tail @%08X -> shield_ranged" % RNG_TAIL),
}
STAGE_SITES = {"reg": ["reg"], "ranged": ["ranged"]}


def retired_report(d):
    """Prove the three removed melee sites hold their pre-Shield bytes. Aborts if not.

    Runs on EVERY path, including --undo and --dis: a half-installed pre-2026-08-27 Shield is
    exactly the state in which the shorter cave and the older links would combine into a melee
    site jumping at the ranged sub-cave. See the RETIRED_SITES comment for why that is fatal.
    """
    bad = []
    for va in sorted(RETIRED_SITES):
        want, desc = RETIRED_SITES[va]
        o = va2off(d, va)
        cur = bytes(d[o:o + len(want)])
        ok = cur == want
        print("  %08X  %-5s RETIRED melee site -- %s" % (va, "clean" if ok else "DIRTY", desc))
        if not ok:
            print("              live    %s\n              expected %s"
                  % (cur.hex(" "), want.hex(" ")))
            bad.append(va)
    if bad:
        sys.exit("\nABORT: retired melee site(s) %s do not hold their pre-Shield bytes.\n"
                 "       That almost certainly means a PRE-2026-08-27 build of this script "
                 "(the one with\n       csca_a / csca_b / melee1) is still half-installed. This "
                 "ranged-only version cannot\n       undo those links -- it no longer knows what "
                 "they pointed at.\n       Recover the older build_shield.py, run its --undo "
                 "first, then re-run this one.\n       Nothing written."
                 % ", ".join("%08X" % v for v in bad))


# ============================================================== PE helpers
def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    s, out = pe + 24 + opt, []
    for _ in range(n):
        vs, va, rs, raw = struct.unpack_from("<IIII", d, s + 8)
        out.append((va, max(vs, rs), raw))
        s += 40
    return out


def va2off(d, va, base=DLL_BASE):
    """⚠ per-section, never one global delta -- this DLL's DATA skews differently from CODE."""
    for va0, sz, raw in sections(d):
        if va0 <= va - base < va0 + sz:
            return raw + (va - base - va0)
    raise ValueError("VA %08X not mapped" % va)


def off2va(d, off, base=DLL_BASE):
    for va0, sz, raw in sections(d):
        if raw <= off < raw + sz:
            return base + va0 + (off - raw)
    raise ValueError(off)


def dis_blob(blob, va, title):
    print("\n  ---- %s  @%08X (%d bytes)" % (title, va, len(blob)))
    for ins in cs.disasm(blob, va):
        print("    %08X  %-21s %-6s %s" % (ins.address, ins.bytes.hex(" "),
                                           ins.mnemonic, ins.op_str))


# ============================================================== id collision check
def check_id_free(d):
    """Abort if ABILITY_ID is already registered. Measured, never taken on trust.

    A duplicate id is not a soft failure: the engine raises during unit initialisation and
    Delphi reports `Runtime error 217` before the main window ever appears.
    """
    used = set()
    lo, hi = CAVE_VA, CAVE_VA + len(CAVE)
    for i in range(len(d) - 10):
        if d[i] == 0xB8 and d[i + 5] == 0xE8:
            try:
                va = off2va(d, i + 5)
            except ValueError:
                continue
            if (va + 5 + struct.unpack_from("<i", d, i + 6)[0]) & 0xFFFFFFFF == CREATE_ENH:
                if lo <= va < hi:            # our own cave -- not a collision with ourselves
                    continue
                used.add(struct.unpack_from("<I", d, i + 1)[0])
    data = set()
    try:
        data = {rid - 10 for rid, _b in _pfs_mod().load("ability.pfs")[0]}
    except Exception:                                            # noqa: BLE001
        print("  (could not read Ability.pfs -- id check used the DLL only)")
    if ABILITY_ID in used:
        free = [x for x in range(0, 0xCE) if x not in used | data]
        sys.exit("ABORT: ability id 0x%02X is registered by the DLL already -- this is the "
                 "collision that shows in game as `Runtime error 217`.\n       Free ids: %s"
                 % (ABILITY_ID, ", ".join("0x%02X" % x for x in free[:12])))
    both = used | data
    print("  id 0x%02X free to register (%d ids known, highest 0x%02X)%s"
          % (ABILITY_ID, len(both), max(both),
             "; already assigned to units in Ability.pfs" if ABILITY_ID in data else ""))


# ============================================================== Release/Ability.pfs
# TAbility.ReadWrite @0x5574F07C reads tag 9 straight into the word at [ability+0x20], AFTER
# registration -- so the DATA FILE WINS over whatever mask the cave passed (0 of 21 vanilla
# sites agree with their own data). Patching only the cave would change nothing in game.
ABIL_PFS = os.path.join(GAME, "Release", "Ability.pfs")
ABIL_PFS_BACKUP = os.path.join(BACKUP_DIR, os.path.basename(ABIL_PFS) + ".pre-shield")
PFS_RESIDUE = 0x2144DF1C          # crc32(d[4:]) of an intact file -- see PFS_Format_CRC.md


def _pfs_mod():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pfs", os.path.join(GAME, "Modding Resources", "re_tools", "pfs.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pfs_tag9_offset(d):
    """File offset of record (ABILITY_ID+10)'s tag-9 word, or None if the record is absent.

    Derived, never hard-coded: AoWDevEd rewrites this file whole and every offset inside it
    moves. Record bodies tile the file from the first one to EOF.

    The CRC gate is the file's integrity check and lives here because every path that touches
    Ability.pfs comes through this function. CATCHES incoherent damage; MISSES a
    coherent-but-wrong layout that was re-CRC'd. ⚠ never locate a field by distance from either
    end of a .pfs -- parse the directory.
    """
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        sys.exit("ABORT: Ability.pfs CRC residue is %#010x, expected %#010x -- the file is "
                 "ALREADY damaged, before this script has edited anything.\n"
                 "       Refusing to touch it: repairing the CRC over the damage would stamp "
                 "it valid and destroy the evidence.\n"
                 "       Restore Release/Ability.pfs or re-save it from AoWDevEd, then re-run."
                 % (zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF, PFS_RESIDUE))
    recs = _pfs_mod().parse_index(bytes(d))
    starts, at = {}, len(d)
    for rid, body in reversed(recs):
        at -= len(body)
        starts[rid] = at
    key = ABILITY_ID + 10
    if key not in starts:
        return None
    a, body = starts[key], dict(recs)[key]
    p = 1 + (4 if body[0] & 0x80 else 0)
    ent = [(body[1 + 2 * k], body[2 + 2 * k]) for k in range(body[0] & 0x7f)]
    p += 2 * len(ent)
    for k in range(struct.unpack_from("<I", body, 1)[0] if body[0] & 0x80 else 0):
        t, o = struct.unpack_from("<II", body, p + 8 * k)
        ent.append((t, o))
    p += 8 * (len(ent) - (body[0] & 0x7f))
    for t, o in ent:
        if t == 9:
            return a + p + o
    print("  Ability.pfs   WARN record %d exists but carries no tag 9 (selection mask)." % key)
    return None


def pfs_read(path=None):
    d = bytearray(open(path or ABIL_PFS, "rb").read())
    off = pfs_tag9_offset(d)
    return d, (None if off is None else struct.unpack_from("<H", d, off)[0])


def pfs_write(value):
    d, cur = pfs_read()
    off = pfs_tag9_offset(d)
    if off is None:
        return False
    struct.pack_into("<H", d, off, value)          # length-preserving u16, no offsets move
    struct.pack_into("<I", d, len(d) - 4, zlib.crc32(bytes(d[4:-4])) & 0xFFFFFFFF)
    # ⚠ not an `assert`: `python -O` strips those, and a stripped guard here would write a file
    # the game and the editor reject on load.
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        sys.exit("ABORT: CRC repair produced residue %#010x, expected %#010x -- nothing written."
                 % (zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF, PFS_RESIDUE))
    open(ABIL_PFS, "wb").write(bytes(d))
    return True


# ============================================================== --sim
def sim():
    """Offline validation. Touches no file except to READ AoWTCPCK.dpl's BreathDir table.

    ⚠ SCOPE. This re-derives r from hn in Python and never calls the engine, so 60/60 means
    "the k/sector ring decomposition is right", NOT "the handedness is right". A reversed
    direction sense inside dHXtoHN would mirror the arc and still score 60/60. The handedness
    is settled separately by reading HSEPack.dpl -- see the ARC MATHS block in the module
    docstring for the addresses.
    """
    print("--sim: ring decomposition vs the engine's own AoWTC.BreathDir table\n")
    print("  (scope: this validates the k/sector maths, NOT the direction sense -- see the\n"
          "   ARC MATHS block in the module docstring for how handedness was settled.)\n")

    def radtohn(r):
        return 3 * r * (r - 1) + 1 if r else 0

    def decompose(hn):
        r = 1
        while radtohn(r + 1) <= hn:
            r += 1
        k = hn - radtohn(r)
        q = (k + ((r - 1) // 2)) // r
        return r, k, q, (q % 6) + 1

    d = bytearray(open(TCPCK, "rb").read())
    o = va2off(d, 0x004673A8, TCPCK_BASE)
    table = list(struct.unpack_from("<60i", d, o))
    bad = [(hn, decompose(hn)[3], table[hn - 1]) for hn in range(1, 61)
           if decompose(hn)[3] != table[hn - 1]]
    print("  BreathDir @004673A8 (AoWTCPCK.dpl): %d/60 reproduced" % (60 - len(bad)))
    for hn, got, want in bad:
        print("    hn=%-3d formula=%d table=%d" % (hn, got, want))

    qmax = max(decompose(hn)[2] for hn in range(1, 61))
    qmax_wide = 0
    for r in range(1, 61):
        for k in range(6 * r):
            qmax_wide = max(qmax_wide, (k + ((r - 1) // 2)) // r)
    print("  max pre-mod quotient: %d over hn 1..60, %d over the full r=1..60 domain "
          "(the cave's single `cmp eax,6 / sub eax,6` is sufficient iff this is <= 6)"
          % (qmax, qmax_wide))

    vals = sorted({v for b in ARC for v in (b - 6, b, b + 6)})
    print("\n  arc = %s   (0 = dead ahead, 5 = one step anticlockwise = front-LEFT)" % (ARC,))
    print("  D = defender->attacker direction, F = defender facing, both 1..6\n")
    print("      F:   " + "  ".join("%2d" % f for f in range(1, 7)))
    for dd in range(1, 7):
        row = []
        for f in range(1, 7):
            row.append(" #" if ((dd - f) % 6) in ARC else " .")
        print("  D=%d      " % dd + "  ".join(row))
    print("\n  ('#' = shielded.)  cave test: diff = (D-1)-(F-1) in -5..5, hit iff diff in %s"
          % sorted(v for v in vals if -5 <= v <= 5))
    ok = all(((((dd - f) % 6) in ARC) == ((dd - f) in [v for v in vals if -5 <= v <= 5]))
             for dd in range(1, 7) for f in range(1, 7))
    print("  cave test agrees with (D-F) mod 6 in %s over all 36 pairs: %s" % (tuple(ARC), ok))
    return 0 if (not bad and qmax_wide <= 6 and ok) else 1


# ============================================================== main
def main():
    # ⚠ SCRATCH GUARD (2026-09-03): AOW_GAME_DIR set => not the real install; never kill
    # the user's running game. See the note in build_minddecay_oos.py.
    if os.environ.get("AOW_GAME_DIR"):
        return
    if "--sim" in sys.argv:
        sys.exit(sim())

    apply_ = "--apply" in sys.argv
    undo = "--undo" in sys.argv
    only_dis = "--dis" in sys.argv
    stages = STAGES
    for a in sys.argv[1:]:
        if a.startswith("--stage="):
            stages = tuple(s.strip() for s in a[8:].split(",") if s.strip())
            bad = [s for s in stages if s not in STAGES]
            if bad:
                sys.exit("unknown stage(s): %s (choose from %s)" % (bad, ", ".join(STAGES)))
    want = [k for st in stages for k in STAGE_SITES[st]]

    d = bytearray(open(DLL, "rb").read())

    print("Shield: ability id 0x%02X, -%d ATK, cave %08X..%08X (%d bytes of the "
          "%#x-byte page this script owns)"
          % (ABILITY_ID, SHIELD_ATK, CAVE_VA, CAVE_VA + len(CAVE), len(CAVE), CAVE_LIMIT))
    print("  manual tactical (instsize 0x%X): geometric arc %s -- (D-F) mod 6"
          % (SZ_TACTICAL, tuple(ARC)))
    if AUTO_CHANCE is None:
        print("  auto-resolve    (instsize 0x%X): NO-OP (no roll emitted)" % SZ_FAST)
    else:
        print("  auto-resolve    (instsize 0x%X): flat %d/%d = %.3f%% per shot, "
              "RandInt @%08X (System.@RandInt)"
              % (SZ_FAST, AUTO_CHANCE[0], AUTO_CHANCE[1],
                 100.0 * AUTO_CHANCE[0] / AUTO_CHANCE[1], RANDINT))
        print("     draw is lockstep-safe: raw @RandInt rides the per-combat seed installed by "
              "TCombat.Execute\n     @0x557282C8; the site is NOT predictor-reachable, so no "
              "expected-value gate is needed.")
    print("stages: %s   (RANGED ONLY -- melee is Parry's job, see the RETIRED block)"
          % ", ".join(stages))
    if EXPAND_COST is None:
        print("  !! hero level-up cost NOT SET -- Shield would be PERMANENTLY FREE to buy.\n"
              "     Set EXPAND_COST and re-run --apply (the cave is rewritten in place).")
    else:
        print("  hero level-up cost: the cave stores %d, but Ability.pfs record %d now carries "
              "tag 6\n     and the DATA FILE WINS -- see the Ability.pfs block in the docstring. "
              "Change it in\n     AoWDevEd, not here. (Parry 8, Drillmaster 10.)"
              % (EXPAND_COST, ABILITY_ID + 10))

    # the retired-melee guard runs before anything else looks at the file, on every path
    print("\n  ---- retired melee sites (must be pre-Shield on every path) ----")
    retired_report(d)

    if only_dis:
        for label, (va, n, desc) in sorted(LABELS.items(), key=lambda kv: kv[1][0]):
            o = va2off(d, va)
            dis_blob(bytes(d[o:o + n]), va, "%s -- %s" % (label, desc))
        return

    if not undo:
        check_id_free(d)

    def cave_state():
        o = va2off(d, CAVE_VA)
        cur = bytes(d[o:o + len(CAVE)])
        if cur == CAVE:
            return "done", len(CAVE)
        if cur == bytes(len(CAVE)):
            # never claim a zero run as a reservation: prove the whole page is free too
            tail = bytes(d[o + len(CAVE):o + CAVE_LIMIT])
            return ("clean", 0) if tail == bytes(len(tail)) else ("other", 0)
        for p in prior_caves():
            if bytes(d[o:o + len(p)]) == p:
                # ⚠ a re-tune may GROW the cave (setting EXPAND_COST adds 7 bytes and slides the
                # name blob). Prove the zone it would grow into is still zero before calling this
                # a safe in-place rewrite -- CLAUDE.md's standing rule for exactly this path.
                tail = bytes(d[o + len(p):o + CAVE_LIMIT])
                if tail != bytes(len(tail)):
                    print("  !! the page past the installed %d-byte cave is NOT zero -- refusing "
                          "to treat this as an in-place rewrite" % len(p))
                    return "other", 0
                return "prior", len(p)
        return "other", 0

    def site_state(key):
        va, orig, new, _t = SITES[key]
        cur = bytes(d[va2off(d, va):va2off(d, va) + len(new)])
        if cur == new:
            return "done"
        if cur == orig:
            return "clean"
        # our own link, pointing at where the sub-cave used to be. Only meaningful when the
        # cave really does hold a prior build -- otherwise a coincidental rel32 could pass.
        if cst == "prior" and cur in prior_site_bytes(key):
            return "prior"
        return "other"

    cst, cur_len = cave_state()
    print("\n  %08X  %-5s cave zone (%d bytes emitted, rest of the page must be zero)"
          % (CAVE_VA, cst.upper(), len(CAVE)))
    for key in SITES:
        va, orig, new, t = SITES[key]
        st = site_state(key)
        mark = "" if key in want else "   (stage not selected)"
        print("  %08X  %-5s %s%s" % (va, st.upper(), t, mark))
        if st == "clean":
            print("              expects %s" % orig.hex(" "))
        elif st == "prior":
            print("              live    %s  <- OUR OWN link at a PREVIOUS cave layout's "
                  "address;\n              new     %s  in-place rewrite will re-point it"
                  % (bytes(d[va2off(d, va):va2off(d, va) + len(new)]).hex(" "), new.hex(" ")))
        elif st == "other":
            print("              live    %s\n              expected %s or %s"
                  % (bytes(d[va2off(d, va):va2off(d, va) + len(new)]).hex(" "),
                     orig.hex(" "), new.hex(" ")))

    if cst == "other":
        sys.exit("\nABORT: the cave page %08X..%08X holds neither zeros nor a Shield build. "
                 "Something else is in there -- investigate before writing."
                 % (CAVE_VA, CAVE_VA + CAVE_LIMIT))
    bad = [k for k in SITES if site_state(k) == "other"]
    if bad:
        sys.exit("\nABORT: %s match neither the original nor the target. A third feature may "
                 "own the site (the two chain tails belong to build_magebane.py -- if a later "
                 "script spliced itself onto one, Shield's exit jmp must be re-pointed at it "
                 "instead of the stock destination). Investigate; nothing written."
                 % ", ".join(bad))
    unwanted = [k for k in SITES if k not in want and site_state(k) == "done"]
    if unwanted and not undo:
        print("\n  note: %s already installed but not in --stage; left alone."
              % ", ".join(unwanted))
    # ⚠ A stale link + a rewritten cave is the one combination --stage can manufacture that
    # corrupts the game: the link would still point at where the old layout put its sub-cave,
    # which in the NEW layout is the middle of something else.
    stale = [k for k in SITES if k not in want and site_state(k) == "prior"]
    if stale and not undo:
        sys.exit("\nABORT: %s hold links into the PREVIOUS cave layout, and this run would "
                 "rewrite the cave without re-pointing them -- they would then jump into the "
                 "middle of the new layout.\n       Re-run without --stage (or include %s). "
                 "Nothing written."
                 % (", ".join(stale), ", ".join(stale)))

    # --- Ability.pfs: DLL half only until the DevEd round-trip creates the record ----------
    pfs_ok, pfs_cur = True, None
    try:
        _p, pfs_cur = pfs_read()
    except FileNotFoundError:
        pfs_ok = False
        print("\n  Ability.pfs   MISSING at %s" % ABIL_PFS)
    if pfs_ok:
        if pfs_cur is None:
            print("\n  Ability.pfs   TODO  record %d (ability 0x%02X) does not exist yet."
                  % (ABILITY_ID + 10, ABILITY_ID))
            print("                Assign \"%s\" to a unit in AoWDevEd and save, then re-run"
                  % ABILITY_NAME.decode())
            print("                --apply to write tag 9 = %#06x and repair the CRC. Until"
                  % SEL_TYPES)
            print("                then the mask the cave passes (%#06x) is what the game uses."
                  % SEL_TYPES)
        else:
            print("\n  Ability.pfs   %-5s record %d tag 9 = %#06x -> %#06x"
                  % ("DONE" if pfs_cur == SEL_TYPES else "TODO",
                     ABILITY_ID + 10, pfs_cur, SEL_TYPES))

    # --- the assembled caves, always printed: disassemble every cave you assemble ----------
    print("\n  ==== assembled cave (read this: keystone imm8 truncation and label arithmetic "
          "are silent) ====")
    for label, (va, n, desc) in sorted(LABELS.items(), key=lambda kv: kv[1][0]):
        dis_blob(CAVE[va - CAVE_VA:va - CAVE_VA + n], va, "%s -- %s" % (label, desc))
    print("\n  (every 0x55xxxxxx operand above is rel32-encoded -- E8/E9 -- so the cave stays "
          "position-independent when the .dpl rebases. The only absolute datum is the name "
          "string, reached through the zeroed `call`/`pop eax` PIC anchor in cave_reg.)")

    target = "clean" if undo else "done"
    at_target = (cst == target and all(site_state(k) == target for k in want))
    if at_target:
        print("\nnothing to do -- already %s." % target)
        return
    if not (apply_ or undo):
        print("\ndry run. --apply to write, --undo to revert, --sim for the maths check.")
        return

    # ⚠ take a backup ONLY from a file proved unpatched BY US. Never on the undo path (the file
    # is the patched state by definition) and never on a re-tune (it is our own previous
    # output). A .pre-* minted from either would sit on disk looking authoritative while holding
    # a patched state.
    fresh = (cst == "clean" and all(site_state(k) == "clean" for k in SITES))
    if apply_ and fresh and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("\nbackup: %s (taken from a file byte-proved free of every Shield site)"
              % os.path.basename(BACKUP))
    elif apply_ and not fresh:
        print("\n(no backup taken: the file already carries Shield bytes, so it is not a "
              "pristine reference. This apply is an in-place rewrite.)")

    o = va2off(d, CAVE_VA)
    if undo:
        n = cur_len or len(CAVE)
        d[o:o + n] = bytes(n)                    # zero ONLY our own emitted length
        for key in SITES:
            # "prior" too: an older layout's link is still OURS and must be restored, not left
            # pointing into a cave we are about to zero.
            if site_state(key) in ("done", "prior"):
                va, orig, _new, _t = SITES[key]
                p = va2off(d, va)
                d[p:p + len(orig)] = orig
    else:
        d[o:o + max(len(CAVE), cur_len)] = CAVE + bytes(max(0, cur_len - len(CAVE)))
        for key in want:
            va, _orig, new, _t = SITES[key]
            p = va2off(d, va)
            d[p:p + len(new)] = new

    try:
        open(DLL, "wb").write(bytes(d))
    except PermissionError:
        sys.exit("ABORT: AoWEPACK.dpl is LOCKED. Kill the AoW binaries and re-run:\n"
                 "  Get-Process | Where-Object { $_.ProcessName -match "
                 "'^(AoW|AoWCompat|AoWDevEd|AoWEd)$' } | Stop-Process -Force")
    print("wrote AoWEPACK.dpl -> %s" % target)

    # Ability.pfs: patch the VALUE, never restore the file -- a DevEd re-save between apply and
    # undo must not be clobbered. The backup exists to remember the old mask, not to be copied.
    if not pfs_ok or pfs_cur is None:
        print("Ability.pfs untouched -- record %d does not exist yet (DevEd round-trip needed)"
              % (ABILITY_ID + 10))
    elif undo:
        if pfs_cur != SEL_TYPES:
            print("Ability.pfs untouched (mask is not ours)")
        elif os.path.exists(ABIL_PFS_BACKUP):
            was = pfs_read(ABIL_PFS_BACKUP)[1]
            if was is not None and pfs_write(was):
                print("Ability.pfs record %d tag 9 -> %#06x (from %s)"
                      % (ABILITY_ID + 10, was, os.path.basename(ABIL_PFS_BACKUP)))
        else:
            print("Ability.pfs left at %#06x -- no backup to read the old mask from" % SEL_TYPES)
    elif pfs_cur != SEL_TYPES:
        if not os.path.exists(ABIL_PFS_BACKUP):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(ABIL_PFS, ABIL_PFS_BACKUP)
            print("backup: %s" % os.path.basename(ABIL_PFS_BACKUP))
        if pfs_write(SEL_TYPES):
            print("Ability.pfs record %d tag 9 %#06x -> %#06x (CRC repaired)"
                  % (ABILITY_ID + 10, pfs_cur, SEL_TYPES))

    if apply_:
        print("""
STATUS: applied, untested. Nothing here has been run in the game.

NEEDS THE USER'S IN-GAME TEST -- none of this can be checked from the binary:
  * MANUAL, magnitude. Shoot a SHIELDED unit in its front or front-left hex, then shoot the
    same unit from its rear or flank. The front/front-left shots must hit visibly less often
    (-%d ATK is about -%d percentage points on this install -- a step up from the -20pp the
    2026-08-26 build gave, so if it feels unchanged the re-tune did not take).
  * MANUAL, arc. The protected side must be the FRONT-LEFT one, not the front-RIGHT one. The
    MAP handedness is settled statically; the on-screen sprite transform is not. If the
    protected side looks mirrored, set ARC = (0, 1) and re-run --apply (rewrites in place).
  * AUTO-RESOLVE, the new behaviour -- THIS IS THE CHANGE THAT NEEDS THE MOST EYES.
    Before today Shield did nothing at all in auto-resolve. Auto-resolve a battle in which a
    shielded unit is shot at repeatedly and compare with the same battle unshielded: the
    shielded side must do measurably better, but NOT by the full -%d every shot (the roll is
    %d/%d, i.e. about %.0f%% of shots). One battle proves nothing -- this needs several, or a
    unit taking many shots, because the effect is statistical by construction.
    ⚠ Bearing is IRRELEVANT in auto-resolve (there are no hexes) -- do not read a
    position-dependent result there as a bug.
  * AUTO-RESOLVE, per shot not per action. A repeat-fire archer (multiple shots per attack)
    rolls independently per shot, so partial protection within one attack is CORRECT.
  * MULTIPLAYER (only if MP is ever played with this build). Auto-resolve the SAME battle on
    two peers and confirm no out-of-sync. The draw is argued lockstep-safe from static
    analysis only; a live MP auto-resolve is the one test that can actually falsify it.
  * BREATH. Breath and Flame Throwing route through the same constructor, so Shield now
    applies to them in BOTH modes (it already did in manual). Confirm that is wanted.
  * MELEE MUST BE INERT, in both modes. Melee a shielded unit from every bearing -- normal
    attacks, retaliation, free swings taken during movement, and touch abilities (web /
    entangle / turn undead), manually AND auto-resolved. Shield must make NO difference to any
    of them. If it does, a melee link survived this narrowing.
  * ranged   a missile that is absorbed or intercepted before it lands must not crash
             (the victim pointer at [ebp-4] is legitimately nil on that path).
  * AI target choice is deliberately unchanged: the auto-resolve AI will keep shooting a
    shielded unit as if it were unshielded. If that reads as wrong in play, say so -- it is a
    separate patch at fcGetDamageValueEx @0x5576E8D4 and it was left out on purpose.
  * hero     Shield still appears in the hero level-up dialog, in the Melee column, and the
             dialog lays out normally. Now that Shield is a RANGED defence, decide whether
             Melee is still the right column -- moving it is herodlg_cats.py plus
             `build_herodlg_columns.py --apply`, which this script does not do.
  * hero     Shield costs 8 points at level-up (Ability.pfs tag 6, NOT this script's %d).
             Confirm 8 is the number you want; the data file wins from here on.
  * hero     Shield is selectable everywhere expected now that tag 9 is %#06x, not 0x0111
             (0x0111 lacked the 0x200 bit that hero level-up requires).
  * boot     the game reaches the main window: no `Runtime error 217`, no "Ability already
             registered".
  * a full manual tactical battle including a siege with walls, plus one auto-resolved
    battle, complete with no exception dialog.

Multiplayer: both peers load this module, so both must carry the identical patch
(standing no-mixed-mod rule).""" % (SHIELD_ATK, 5 * SHIELD_ATK, SHIELD_ATK,
                                    (AUTO_CHANCE or (0, 1))[0], (AUTO_CHANCE or (0, 1))[1],
                                    100.0 * (AUTO_CHANCE or (0, 1))[0]
                                    / (AUTO_CHANCE or (0, 1))[1],
                                    EXPAND_COST, SEL_TYPES))


if __name__ == "__main__":
    main()
