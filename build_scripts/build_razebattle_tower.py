#!/usr/bin/env python3
r"""
AoW1 mod -- "razebattle" STAGE 2: tower raze is a REAL fast combat, GATED on the outcome, with the
battle visible/replayable and the vanilla raze-avengers suppressed.

FULL DESIGN: Modding Resources/Raze_CombatPredictor_Analysis.md section 12b.

STAGE 1 (already CONFIRMED WORKING in-game 2026-07-10) validated the scary plumbing: TTower VMT slot
0x1B0 (ExecuteRaze) -> cave_towerraze which builds a hidden TDefendersArmy militia, constructs a FAST
TCombat (razer=AddArmy side 0, militia=AddArmyEx side 1), runs it synchronously
(Init/Activate/Execute/Deactivate/Finalize wrapped in LockExecuted/UnlockExecuted +
LockGameOverEvent/UnlockGameOverEvent), then ALWAYS re-entered the original ExecuteRaze @0x5575FFC8
(gated by BSS razeok @0x558FA801 so CanRaze @0x5575FB80 does not re-veto). Two expected gaps remained:
the battle was SILENT (no combat-log/replay) and the vanilla raze-avengers still spawned.

STAGE 2 = four additions, one pass (this build):

  (A) RESULT GATE. cave_towerraze latches the fast-combat result byte combat[+0x14] into a stack local
      in the verified-valid window (after the outer UnlockExecuted, BEFORE DestroyCombat), then AFTER
      teardown razes ONLY if the razer (side 0) WON. GATE CONDITION = result in {3,6}:
        3 = TCombat.UpdateStatus @0x557282E4 wrote it -> side0(+0x1C razer) has undestroyed conquer
            objects while side1(+0x20 militia) has none (wipe win);
        6 = TFastCombat.Execute @0x55744A0C wrote it as a pre-round short-circuit -> militia side had
            zero conquer objects (walkover).
      Every other reachable value = razer did NOT take the objective, so the tower STANDS and we skip
      the ExecuteRaze re-entry entirely: 4 = razer wiped (militia won), 5 = mutual annihilation (razer
      also dead), 2 = unresolved / cannot-inflict-damage, 8 = cannot breach wall, 9 = a wall/structure
      conquer object still stands. This is byte-for-byte the same {3,6} test vanilla exploration uses
      in ExecuteSearchDone @0x557C29E0. It is DELIBERATELY NOT the predictor's {3,4,6}+GetSuperiority
      test (TCombatPredictor.FinishCombat is a DIFFERENT class; there 4 means attacker SURVIVORS, here
      4 means the razer LOST -- opposite polarity; using it would raze on a loss).
      ExecuteRaze is a `void` (always returns AL=0, caller treats it as void) so the loss path's
      return value is irrelevant -- we just fall through to the epilogue and the tower is untouched.

  (B) SKIP AVENGERS. New hook at the PlaceRazeDefenders vcall @0x557601F0 (slot 0x1AC,
      FF 91 AC 01 00 00) -> cave_skipavenger: when razeok is set (i.e. inside our post-battle
      ExecuteRaze re-entry) the second-wave avenger militia is suppressed (the battle militia already
      fought). When razeok is clear (normal razes / other structures) the cave replicates the vanilla
      vcall exactly -- behaviour unchanged. Register-exact: EAX=self, ECX=[self] VMT, DL=player all
      preserved; only ESI is used (push/pop balanced); EBX/EDI untouched; POP does not disturb the
      CMP's ZF before the JNZ.

  (C) COMBAT LOG (MINIMAL recipe -- ZERO managed string locals). cave_towerraze, after the run and
      BEFORE DestroyCombat (the only window combat[+0x18]=combat-logbook is valid), builds a
      TCombatEventLog, binds the combat logbook, files it into the razing player's event logbook, and
      -- for the local human razer only -- replays it. This mirrors TExplorationSite.ExecuteSearch's
      fast-branch event block but SKIPS the cosmetic GetName+LStrCatN title munging, so there is NO
      Delphi string temporary (=> no LStrClr, no added try/finally surface). The combat logbook already
      carries the round-by-round text, so the entry is fully replayable. Acting/display player = the
      razing player byte the cave already holds at [ebp-8]; map (for the player list + local-human
      index) reuses the map pointer already in [ebp-0x14].
        TEventLog.Create      0x557FD398  EAX=classVMT(=*0x557171BC), DL=1, ECX=0 -> EAX=eventlog
        SetCombatLogbook      0x55728F2C  EAX=eventlog, EDX=combat[+0x18]
        GetPlayers            0x557544D0  EAX=map[+0x140], EDX=playerIdx -> EAX=player (0 if OOB)
        AddEvent              0x557FDB90  EAX=player[+0xD8], EDX=eventlog  (ASSERTS synchronised)
        eventlog slot 0x70    show/replay (self, EDX=0, ECX=0, +push 0, push 0; ret 8)  -- local human only
        eventlog slot 0x2C    refcount release (self; ret 0)  -- drop our local handle
      The Create->AddEvent(logbook keeps it alive)->slot0x2C(release) order matches vanilla; slot0x2C
      is a REFCOUNT release (dec [+0x14]; destroy only at 0), NOT an unconditional Free, so the filed
      event survives. Net stack delta of the block = 0 (slot0x70 self-cleans its 2 pushes via ret 8).

  (D) SEH FRAME -- DEFERRED (documented loudly, per the Stage-2 requirement's own carve-out).
      *** WHY DEFERRED ***  The minimal event-log (C) introduces ZERO managed string locals, so there
      is nothing for a Delphi try/finally to clean up. The remaining SEH value would be guaranteeing
      DestroyCombat + UnlockGameOverEvent on a mid-combat/AddEvent exception. But our post-run block is
      a FAITHFUL transplant of vanilla TExplorationSite.ExecuteSearch, and vanilla's FS:[0] finally
      there protects ONLY its AnsiString local -- it does NOT protect DestroyCombat/UnlockGameOverEvent
      either (those are try-body-only in vanilla). So our exposure is provably VANILLA-EQUAL: the same
      asserting AddEvent runs before the same unprotected DestroyCombat that ships in every exploration
      combat in the game. Adding a hand-rolled FS:[0] frame in a rebased, reloc-free code cave is
      strictly MORE than vanilla does and is itself crash-prone (the pushed handler pointer must be
      load-delta-computed, not a raw imm32 -- the single most likely way to regress the
      CONFIRMED-WORKING Stage 1). Given Stage 1 already ran the combat clean and the raze executes
      inside ExecuteTE (a synchronised turn/network event, so AddEvent's GetSynchronised assert is
      expected to pass), we take the vanilla-equal risk and DO NOT install SEH.
      *** RESIDUAL RISK (symptom to watch) ***  If AddEvent's `System.Assert('EventLog.pas',0x2c0)`
      (GetSynchronised(map)==0) or any mid-combat raise ever fires, DestroyCombat/UnlockGameOverEvent
      are skipped and the NEXT battle anywhere hits CreateCombat's "Combat already created" cascade --
      exactly the Stage-1 symptom. If that is ever observed on a raze, re-open (D) and install the
      full FS:[0] finally per the seh-frame recipe in the Stage-2 handoff (finally body =
      DestroyCombat + UnlockGameOverEvent, handler pointer via `lea edx,[delta+Lhandler]`).

STAGE 2.1 refinements (2026-07-10):
  * (req1) NO forces present: cave_towerraze's Lnoarmy path (no army container on the tower's own hex)
    now BLOCKS the raze (tower stands) instead of calling ExecuteRaze. And the vanilla raze message
    RT_STRING "Your forces aren't sufficient" is reworded to "Your forces aren't present" (kept at 29
    chars so the string block does not shift) -- CanRaze shows it at click time for genuine no-force.
    (Lempty = you HAVE an army but the tower has no defenders -> still razes: nothing to fight.)
  * (req2) FAILED raze battle: on any non-win result (not in {3,6}) the tower is flagged to the
    independents via TPlayerStructure.SetPlayer(tower, 0) before it is left standing.

STAGE 12a (2026-09-12) -- CITY loss-garrisons get NO AI GROUP AT ALL (exact vanilla parity).
  DEFECT: a victorious city rebel garrison could not be bought off. AoWE.TAbstractUnit.CanJoin
  @0x557821AC gates on the unit's AI-GROUP BEHAVIOUR before any race-relations logic ever runs:
      557821B5  mov ebx,[esi+0x20]  /  test ebx,ebx  /  je 557821CE   ; NO group -> gate SKIPPED
      557821BE  call [eax+0xD0]                                       ; group.Behavior()
      557821C4  add al,0xFE / sub al,2 / jb 55782318                  ; behaviour 2 or 3 -> FALSE
  TGuardAG.Behavior = 2, so the Stage-4 Guard AG made every city loss-garrison un-joinable. The gold
  offer has exactly one path -- TCity.GetMoveAction / IncommingNegotiateRequest / IncommingNegotiate-
  Offer -> TCity.JoinAmount @0x557ACF98 -> TArmy.GetCanJoinSelection @0x5578FA04 -> VMT 0x194 CanJoin
  -- and an empty selection means no offer is ever presented.
  VANILLA PARITY IS THE FIX: CheckRebellion @0x557AB63E-0x557AB6A5 (still present in the live file,
  unreachable behind our jmp @0x557AB632) does TUnitList.Create -> GenerateRebelUnits ->
  TAbstractUnit.Place per unit and NEVER calls SetupRazeDefenderAG -- vanilla rebels have no group.
  THE EDIT is one instruction: src_cityguard's razeguard branch `Lcg2_guard` ends `ret` instead of
  `jmp SETUPAG_HOOK`. Stack is balanced at that label (the `push ecx` is popped before the `jne`),
  EAX still holds self, and the caller ignores the return -- TStructure.PlaceRazeDefenders
  @0x5575FE84 does `call [ebx+0x15c]` @0x5575FF5A then UNCONDITIONALLY `mov bl,1` @0x5575FF60.
  Live bytes @0x5580D2CC: E9 3B 2B F5 FF -> C3 + zero pad.
  SCOPE = ALL CITY loss-garrisons (rebellion, lost city-raze, lost city-loot) and ONLY those. Every
  one funnels cave_lossgarrison @0x5580CE90 -> vcall 0x1AC PlaceRazeDefenders -> TCity VMT slot 0x15C
  = cave_cityguard @0x5580D2B0. STRUCTURES never reach cave_cityguard (it exists only in TCity's VMT)
  and keep the Stage-11 Guard AG -- a deliberate user request. FLAG_RAZEGUARD's other readers,
  cave_genraze @0x5580D080 and cave_citygenraze @0x5580D260 (Stage-11 survivor substitution), are
  untouched, so the garrison is still the literal damaged survivors -- now merely buyable.
  ⚠ THREE THINGS NOT TO DO, each of which looks like the fix and is not:
    * patching CanJoin -- the behaviour-2/3 gate is vanilla and correct;
    * swapping the city AG to kind 5 TRefugeAG -- TAbstractUnit.JoinAmount @0x55782324 special-cases
      behaviour 5 (`cmp al,5 / jne .. / xor eax,eax`) -> cost 0, i.e. FREE rebels;
    * touching cave_setupguard @0x5580CF00 or the SetupRazeDefenderAG hook @0x5575FE0C -- structures
      keeping Guard is intentional.
  RNG: ADDS ZERO DRAWS. TCity.SetupRazeDefenderAG's SYNCED Random(8) @0x557AA38D (the 1/8 kind-5
  raider flavour) was already skipped on the guard branch and still is; the razeguard-clear branch
  still calls the vanilla city fn with its draw. The deviation is versus VANILLA, never between
  PEERS -- FLAG_RAZEGUARD is written by exactly two instructions, both in cave_lossgarrison, reached
  only from combat[+0x14] result gates inside a synchronised token event, so every peer branches
  identically. DO NOT hoist the draw. (MP convention: an algorithm property, not a risk.)

STAGE 12b (2026-09-12) -- the combat report reaches EVERY witness, not just the razing player.
  DEFECT: a fast rebellion/raze/loot battle filed a combat report for one player only, so a defender
  who lost a city to rebels, or a neighbour watching the fight, got nothing. The Stage-2 "(C) MINIMAL
  combat-log recipe" hand-rolled a single TCombatEventLog into the razing player's logbook.
  THE ENGINE ALREADY HAS THE RIGHT FUNCTION: AoWE.DistributeCombatEvent @0x5572928C (EAX =
  TCombatLogbook, DL = show-to-local-human). It loops players 1..count-1 and, for each that can SEE
  the combat hex (TAoWHSMap.VisibleForPlayer @0x557778A4) OR PARTICIPATED (TCombatPlayerList.
  IndexOfPlayer @0x557288B8), creates a TCombatEventLog, SetCombatLogbook, TEventLogbook.AddEvent
  into player[+0xD8]; then if DL != 0 && map[+0xA5]==player && player[+0xA7]==0 && finaldata[+0x30]!=6
  it fires slot 0x70 to replay, and releases via slot 0x2C. Vanilla's own fast-combat call site is
  TArmyCombatMoveTE.ExecuteCombat+0x2b5 @0x55749BD9 -- `mov eax,[esi+0x18]; mov dl,1; call 5572928c`,
  gated on IsClass(combat, TFastCombat) -- identical in shape to our cave, DL=1 included.
  THE EDIT: the whole (C) block (~109 B, Create/SetCombatLogbook/GetPlayers/AddEvent/show-gate/
  Lnoshow/release) is DELETED and replaced, at the same point (after the combat[+0x14] latch into
  [ebp-0x20], before the cave_rehome call and DestroyCombat), by four instructions:
      mov eax,[ebp-0x18] ; mov eax,[eax+0x18] ; mov dl,EVENTLOG_SHOW ; call DISTRIBUTE_COMBAT_EVENT
  ⚠ The L3_askdialog TEventLog.Create @0x557FD398 (the combat-TYPE request dialog) SURVIVES -- it is
  a different event log and deleting it would kill the fast/manual choice. After this edit
  cave_towerraze contains exactly ONE call 0x5572928c and ZERO calls to 0x55728F2C / 0x557FDB90.
  SAFETY: combat[+0x18] is allocated in TCombat.Create+0x84 and its +0xC/+0x10 TCombatData members in
  TCombatLogbook.Create @0x55728D80, so it is never nil; TCombat.Initialize+0x193 / Finalize+0xa0
  populate them and this cave calls both (slots 0x68/0x6C). SetCombatLogbook @0x55728F2C does
  Release(old)/AddRef(new), so N filed events hold N refs and the logbook outlives DestroyCombat.
  DistributeCombatEvent is Delphi-callee-save with a plain `ret 0`; nothing after the deleted block
  reads ESI/EDI. call rel32, same module => PIC. The deletion removes the cave's LAST use of
  VMTREF_EVENTLOG, but that read used the STORED delta at [ebp-0x1C], not a call/pop, so
  assemble_pic's npops==1 assertion still holds (verified: the cave still assembles with npops=1).
  ALSO FIXES raze and loot, which had the identical gap. The TACTICAL half is STAGE 12d below.

STAGE 12d (2026-09-12) -- the TACTICAL (modal) path files a combat report too.
  DEFECT: 12b fixed only cave_towerraze's synchronous fast run. A raze resolved in MODAL tactical
  combat returns from cave_towerraze immediately (Execute -> AL=1) and finishes later through
  cave_razedone @0x5580D500, the combat[+0x2C] completion callback -- which filed no event log at
  all, for anyone.
  ⚠ SCOPE: the human RAZE path only. Rebellion and loot both pack combat-type choice 1 = FAST into
  the ExecuteRaze arg (cave_rebellion owner|0x50, cave_lootbattle owner|0x90; bits 4-5 = choice) and
  cave_towerraze prefers the packed choice over the registry setting, so [ebp-0x20] is 1 for both and
  L3_tactical is unreachable -- 12b already covers them in full. L3_tactical is entered only by a
  LOCAL HUMAN razing a structure or city under Tactical, or under Ask answered manual (cave_typechosen
  re-issues with choice 2).
  THE WINDOW IS THE SAME ONE, and it is provable rather than assumed: TCombat.Initialize LOCKS at
  +0x8 (0x55727C9C) and TCombat.Finalize UNLOCKS at its tail (0x55728084), so on the tactical path
  (where cave_towerraze does NOT take its own lock) the count goes 0->1->0 and TCombat.UnlockExecuted
  @0x55728104 fires combat[+0x2C] from INSIDE Finalize -- after the SetFinalData call at
  Finalize+0xa0 = 0x55727ED8 (the function itself is TCombatLogbook.SetFinalData @0x55728E44) and after
  `finaldata[+0x30] = combat[+0x14]` @0x55727F83, before any DestroyCombat. combat[+0x18] and both
  its TCombatData members are populated. (On the fast path the extra lock makes it 0->1->2->1->0, so
  it fires at cave_towerraze's own UnlockExecuted instead -- same window, same guarantees.)
  THE EDIT: after the razeasync one-shot clear, so it covers EVERY tactical outcome including the
  2/5 standoffs that fall straight to Ldone:
      SynchroniseBegin(map) ; mov eax,[esi+0x18] ; mov dl,EVENTLOG_SHOW_MODAL ; call 0x5572928c ;
      SynchroniseEnd(map)                       (ECX, the load delta, push/pop-preserved across it)
  ⚠⚠ TWO THINGS DIFFER FROM 12b AND BOTH ARE DELIBERATE:
    (1) DL = 0, not 1. Vanilla's own combat[+0x2C] callback -- TArmyCombatMoveTE.CombatExecuted
        @0x557496D4, whose tail @0x55749904 is reached ONLY for a non-fast combat -- uses
        `xor edx,edx`. The tactical raze is only ever reached by the LOCAL HUMAN (cave_razemode
        forces AI/remote to fast), who has just watched the battle; DL=1 would auto-replay it at
        them. Entries still file for every witness; DL controls only the replay.
    (2) The SynchroniseBegin/End pair is MANDATORY, not vanilla mimicry. DistributeCombatEvent files
        through TEventLogbook.AddEvent @0x557FDB90, which asserts GetSynchronised(map) @0x55775608
        (true iff map[+0x234] != 0, OR a token event is executing, OR map[+0x3C] & 2). 12b's site
        runs inside the raze TE so the token-event term covers it; THIS callback fires when the
        combat screen closes, outside the TE, where only the counter can.
  NO DOUBLE-FILING, established by scan not by inspection: the block sits under the `jz Ldone`
  razeasync gate so the fast path cannot reach it, and vanilla's tactical filer can never run for our
  combat because cave_towerraze overwrites combat[+0x2C] with cave_razedone. A module-wide search
  finds exactly THREE callers of 0x5572928C BEFORE this stage -- 0x55749904 (vanilla modal),
  0x55749BD9 (vanilla fast)
  and 0x5580CBA2 (Stage 12b); no other module imports the symbol.
  RELOCATION: the block pushed cave_razedone from 138 B to 174 B, past the 144 B its old slot had
  before cave_rebelchance @0x5580D460, so the cave MOVED to 0x5580D500 (reservation 0x100, landing
  exactly on CAVE_SEED_RESV) and the vacated slot is ZERO-FILLED. cave_lootbattle gained a 0x60
  reservation at the same time. Both absorb dead orphans -- see the reservations block for the
  addresses and the proof (zero rel32/absolute references, zero .reloc entries, in any section).
  RNG: ADDS ZERO DRAWS -- DistributeCombatEvent draws nothing, and neither do Synchronise{Begin,End}
  (they are `inc`/`dec dword [map+0x234]; ret`).

STAGE 12f (2026-09-12) -- L3_tactical passed the COMBAT to DestroyCombat, which takes the MAP.
  DEFECT (pre-existing, byte-identical in backups\AoWEPACK.dpl.pre-panicnomelee, found by the Stage-12d
  QA pass): the sub-branch reached when a TACTICAL Execute (slot 0x64) returns AL != 1 ended
      5580CC6A  mov eax,[ebp-0x18]   ; the COMBAT
      5580CC6D  call 0x557787F8      ; TAoWHSMap.DestroyCombat
  DestroyCombat is `mov esi,eax; cmp dword [esi+0x120],0; je bail`, i.e. EAX = the MAP. [ebp-0x14] is
  the map throughout the cave and [ebp-0x18] is the combat; the FAST path three instructions earlier
  has always had it right (0x5580CBB5 `mov eax,[ebp-0x14]`). VANILLA SETTLES IT: TArmyCombatMoveTE.
  ExecuteCombat has the byte-identical `cmp al,1 / je` @0x55749BAB and its AL!=1 fall-through does
  `mov eax,[0x558fa040] ; call 0x557787f8` @0x55749D09 -- the map.
  THE EDIT is one operand, [ebp-0x18] -> [ebp-0x14]. Both encode as 3 B (8B 45 E8 -> 8B 45 EC), so the
  cave is size-neutral and TOWERRAZE_RESV = 1152 is unaffected.

  ⭐ THE BRANCH IS REACHABLE -- established before patching, not assumed. The tactical path does NOT
  run TCombat.Execute; CreateCombat(0x220110) builds a TTacticalCombat (AoWTCPCK.dpl VMT 0x00413314,
  inst 0x50, the only cross-module TCombat descendant), whose slot 0x64 is TTacticalCombat.Execute
  @0x004295E8. That function sets its return value to 1 at EXACTLY ONE instruction, 0x00429992, and
  only after TAoWCombatMap.NewTurn -- i.e. only once the modal screen is actually up. Three exits
  precede it, all returning non-1:
      AL=8  ValidateWallCombat @0x429540 false.   NOT reachable for a raze: it returns
            `party0[+0x18] == 0`, and the Stage-5 wall fix zeroes exactly that byte, so it is TRUE.
      AL=2  side1.GetCount() == side1[+0x18]   (combat[+0x20] = militia side; slot 0x54 =
            Engine.TENode.GetCount via thunk 0x557031DC).
      AL=6  side1.GetCount() == 0  @0x004296B9 -- YES, it short-circuits when the militia side ends
            Initialize with no combat objects. cave_towerraze's Lempty screens a militia ARMY with
            zero units, but not a militia SIDE that lands zero objects, and it does not screen AL=2.
  CONSEQUENCE OF THE OLD CODE: TTacticalCombat is 0x50 B, so [combat+0x120] is 0xD0 B PAST the end of
  the object -- an out-of-bounds heap read. Zero => DestroyCombat bails, map[+0x120] stays non-null,
  and every later battle raises CreateCombat's "Combat already created" (the 10-ai-and-structures
  §4.5.2 symptom). Non-zero => it dereferences that garbage as a TCombat and calls its VMT slots
  0x74/0x6C -- a virtual call through a wild pointer.

  ⚠ FLAG_RAZEASYNC IS **NOT** LEFT SET ON THIS PATH -- do not "also clear it while you are there".
  cave_razedone's one-shot clear does fire here: TTacticalCombat.Initialize chains to TCombat.
  Initialize @0x00429094 (which locks at 0x55727C9C) and TTacticalCombat.Finalize chains to
  TCombat.Finalize @0x0042952D (whose tail unlocks at 0x55728084), so the Finalize call two
  instructions above takes the count 1->0 and fires combat[+0x2C] = cave_razedone, exactly as the
  Stage-12d window note describes. The report is filed and the raze/garrison gate runs; only the
  DestroyCombat operand was ever wrong. An extra clear would be dead code.

STAGE 12c (2026-09-12) -- FIXED-LENGTH CAVE RESERVATIONS. process() writes exactly len(new) bytes, so
  a cave that SHRINKS between stages leaves the tail of the longer previous blob live in the file.
  ⚠ THAT HAD ALREADY HAPPENED BEFORE STAGE 12 -- an earlier stage shrank cave_towerraze 1152 -> 1140
  and left 12 bytes of orphaned code at 0x5580CD84 (`mov eax,[ebp-4]; movzx edx,[ebp-8];
  call cave_lossgarrison`, then falling straight into cave_canraze @0x5580CD90). Provably unreferenced
  and byte-identical in a pre-Stage-12 snapshot, so it never executed; TOWERRAZE_RESV = 1152 lands
  exactly on CAVE_CANRAZE and zeroes it. Both Stage-12 caves shrink too, so both are zero-padded to
  their reservation, and towerraze_s1_prior is padded to TOWERRAZE_RESV (not to len(cave_towerraze)).

STAGE 12e (2026-09-12) -- THE REMAINING THREE ORPHANS. 12c and 12d each reserved only the caves they
  were themselves editing, so three shrink-tails outlived both sweeps. QA found them on the 12d pass;
  the deadness proof was re-run at 12e rather than inherited (every E8/E9 rel32 in CODE, every literal
  dword in every section of the whole file, all 63880 .reloc entries: ZERO references into any span;
  the two rel8 candidates are false positives, and no fall-through reaches any of them -- see the
  reservations block for the per-span detail).
    0x5580CDA0  11 B  a COMPLETE, instruction-aligned, ENTERABLE duplicate of cave_canraze -- absorbed
                      by CANRAZE_RESV = 0x20
    0x5580CDE0  27 B  the pre-relocation cave_forcefail, dead since the cave moved to 0x5580D150 but
                      never zeroed -- absorbed by SKIPAVENGER_RESV = 0x60
    0x5580D040   5 B  the tail of a 197 B cave_rehome that shrank to 192 -- absorbed by
                      REHOME_RESV = 0x100
  Each reservation lands exactly on the next cave's first byte, so the region 0x5580C910..0x5580D640
  is now covered end to end by fixed-length spans and NOTHING in it is left to the writer's
  len(new). A 12d-style positive on-disk guard fronts all three: the growth zone must be zeros, our
  own applied bytes, or ONLY the identified orphan -- anything else aborts before writing, and the
  orphan exemption lapses once applied so a re-run re-proves they are gone.

MILITIA: still LEAKED, not freed (unchanged from Stage 1 -- a leaked never-touched TArmy cannot fault;
the eventlog/result work does not touch it).

UPGRADE-AWARE APPLY: Stage 1 is ALREADY in the live file. Every patched site accepts EITHER the
vanilla-original bytes OR the currently-applied Stage-1 bytes as a valid "before" state (icestorm
list-of-acceptable-priors pattern), so re-running --apply upgrades Stage 1 -> Stage 2 cleanly. No
backup is minted on such a re-run -- see BACKUP above; the ".pre-razebattle (vanilla)" file this line
used to promise has never existed. Re-running after Stage 2 reports "already applied".
  * VMT slot @0x557C3358 and CanRaze hook @0x5575FB80 are UNCHANGED between Stage 1 and Stage 2
    (cave_towerraze and cave_canraze keep their addresses), so their Stage-2 target == the applied
    Stage-1 bytes; vanilla is the alternate accepted prior.
  * cave_towerraze GROWS in place (Stage-2 code appended); its accepted priors are (a) pristine zeros
    OR (b) the exact Stage-1 cave bytes zero-padded to the Stage-2 length.
  * cave_razedone / cave_canraze are byte-identical to Stage 1 (razedone still just marks
    combathappened; it is the required combat[+0x2C] callback, now vestigial for gating since the gate
    moved into cave_towerraze). Accepted priors: pristine zeros OR the (identical) target bytes.
  * cave_skipavenger and the 0x557601F0 avenger hook are NEW; accepted prior = vanilla (== live,
    Stage 1 never touched that site).

BSS FLAGS (page slack; runtime-only, no file backing; 0x558FA800=simfly):
    0x558FA801  razeok         (set around the post-combat ExecuteRaze re-entry; read by cave_canraze
                               AND now cave_skipavenger)
    0x558FA802  combathappened (cave_razedone marker -- vestigial Stage-1 proof, retained)
    STAGE 2 ADDS NO NEW BSS FLAG (the latched result lives in a stack local [ebp-0x20]); next free
    BSS byte remains 0x558FA803.

CAVE SPACE -- this script owns 0x5580C910..0x5580D640 exclusively (see the ownership table in
Zig notes/12-re-toolchain.md s6). CURRENT layout, not the Stage-2 one this block used to freeze;
`R` = a fixed reservation the writer pads to, everything else is budgeted by the next address:
    0x5580C910  cave_towerraze     R 1152 -> ends exactly on cave_canraze
    0x5580CD90  cave_canraze       R 0x20  -> ends exactly on cave_skipavenger
    0x5580CDB0  cave_skipavenger   R 0x60  -> ends exactly on cave_typechosen
    0x5580CE10  cave_typechosen
    0x5580CE90  cave_lossgarrison
    0x5580CF00  cave_setupguard
    0x5580CF40  cave_noflee
    0x5580CF80  cave_rehome        R 0x100 -> ends exactly on cave_genraze
    0x5580D080  cave_genraze
    0x5580D100  cave_razemode
    0x5580D150  cave_forcefail     (must stay below CAVE_VALFIX_RESV)
    0x5580D200  -- FOREIGN: cave_valfix, build_razeeval_timing.py (18 B) --
    0x5580D220  cave_razedispatch
    0x5580D260  cave_citygenraze
    0x5580D2B0  cave_cityguard     R 33
    0x5580D2E0  cave_cityseed
    0x5580D310  cave_findrazer
    0x5580D3B0  cave_rebellion
    0x5580D3D0  -- VACATED by Stage 12d, zero-filled, 0x90 to cave_rebelchance: FREE --
    0x5580D460  cave_rebelchance
    0x5580D4A0  cave_lootbattle    R 0x60 -> ends exactly on cave_razedone
    0x5580D500  cave_razedone      R 0x100 -> ends exactly on the seed reserve
    0x5580D600  -- FOREIGN: the seed cave, build_razeroster_vary.py, to CAVE_END_LIMIT 0x5580D640 --

Idempotent; verifies every original byte (vanilla OR Stage-1 prior); dry-run by default, pass --apply
(close ALL AoW binaries first -- AoW.exe / AoWCompat.exe / AoWDevEd.exe lock the DLL).
BACKUP: <game dir>\backups\AoWEPACK.dpl.pre-razedlgfix -- the suffix is process()'s `backup_suffix`
default, NOT ".pre-razebattle" as this line used to claim. ⚠ IN PRACTICE NO SNAPSHOT IS EVER MINTED
NOW, and that is correct: since 2026-09-12 the backup is gated on the TTower VMT slot still holding
VMT_ORIG, i.e. on the file being provably untouched by this script. The live DLL has carried Stage 1
since 2026-07-10, so every --apply from here on is a RE-TUNE over our own output and skips the copy.
A snapshot taken at a re-tune would be a patched image wearing a pre-patch name -- see the gate's own
comment in process(). The pristine reference for this DLL is the vanilla game root and
Modding Resources/AoWEPACK_original_backup.dpl, never anything in backups\.
REVERT: NOT by snapshot. Restoring a whole-file .pre-* wipes every feature applied after it, and
there is no snapshot layer at all now (both stacks were purged, 2026-08-08 and 2026-09-09). This
script HAS NO --undo FLAG: back it out by hand, restoring the original bytes listed in `patches`
and zeroing the caves listed under CAVE SPACE above.
⚠ RE-TUNING IS AN IN-PLACE CAVE REWRITE, NEVER REVERT-AND-REAPPLY. _own_prior() (below the patch
table) accepts the CURRENTLY-INSTALLED bytes of a cave we own as a valid prior -- gated on the VMT
hook already pointing at cave_towerraze, i.e. proof this script owns the region -- so --apply
overwrites its own earlier stage after verify-before-write. Stage 12c's fixed reservations are what
make that safe in the SHRINKING direction too.
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e+6)[0]
    optsize = struct.unpack_from("<H", data, e+20)[0]
    sec = e+24+optsize; secs=[]
    for i in range(nsec):
        vsize,vaddr,rsize,raw = struct.unpack_from("<IIII", data, sec+8)
        secs.append((vaddr,vsize,raw,rsize)); sec+=40
    return secs
def mkva2off(base):
    def va2off(secs, va):
        rva = va-base
        for vaddr,vsize,raw,rsize in secs:
            if vaddr <= rva < vaddr+max(vsize,rsize):
                return raw+(rva-vaddr)
        raise ValueError(f"VA {va:08X} not mapped")
    return va2off
def rel32(src, dst): return struct.pack("<i", dst-(src+5))

DLL_BASE = 0x55700000

# ---- callee addresses (Ghidra VAs, image base 0x55700000); all reached by rel32 ----
TARMY_CREATE   = 0x5578C16C   # TArmy.Create               EAX=classVMT, DL=alloc(1), ECX=0 -> EAX=army
LOCK_GAMEOVER  = 0x55776830   # TAoWHSMap.LockGameOverEvent EAX=map
UNLOCK_GAMEOVER= 0x55776774   # TAoWHSMap.UnlockGameOverEvent EAX=map
CREATE_COMBAT  = 0x55778714   # TAoWHSMap.CreateCombat      EAX=map, EDX=flag -> EAX=combat
DESTROY_COMBAT = 0x557787F8   # TAoWHSMap.DestroyCombat     EAX=map
LOCK_EXECUTED  = 0x55728100   # TCombat.LockExecuted        EAX=combat
UNLOCK_EXECUTED= 0x55728104   # TCombat.UnlockExecuted      EAX=combat (fires combat[+0x2C] on 0)
ADD_ARMY       = 0x55727804   # TCombat.AddArmy   EAX=combat,EDX=army,CL=side + push l,y,x; ret 0xC
ADD_ARMY_EX    = 0x557279D0   # TCombat.AddArmyEx EAX=combat,EDX=army,CL=side + push -1,-1,-1,pos; ret 0x10
TOBJ_FREE      = 0x557010B8   # TObject.Free thunk          EAX=obj
EXECUTE_RAZE   = 0x5575FFC8   # TStructure.ExecuteRaze base EAX=self, DL=player  (void; caller ignores AL)
SET_PLAYER     = 0x55760D08   # TPlayerStructure.SetPlayer  EAX=self, DL=player  (TTower slot 0x1F0). Player 0 = independent.

# ---- Stage-2 event-log callees (from TExplorationSite.ExecuteSearch @0x557C1A20; all rel32) ----
TEVENTLOG_CREATE  = 0x557FD398  # TEventLog.Create        EAX=classVMT, DL=1, ECX=0 -> EAX=eventlog; ret 0
#   ⚠ Stage 12b retired the hand-rolled combat-log block, so the next three are NO LONGER referenced by
#   any cave -- they are kept as the documented ABI of what DistributeCombatEvent now does internally.
#   TEVENTLOG_CREATE is still live: L3_askdialog builds the combat-TYPE request dialog with it.
VMTREF_EVENTLOG   = 0x557171BC  # DATA slot; *VMTREF = TCombatEventLog class VMT (0x557171FC). (unused since 12b)
SET_COMBAT_LOGBOOK= 0x55728F2C  # SetCombatLogbook        EAX=eventlog, EDX=combat[+0x18]; ret 0 (unused since 12b)
GET_PLAYERS       = 0x557544D0  # GetPlayers              EAX=map[+0x140], EDX=playerIdx -> EAX=player; ret 0
ADD_EVENT         = 0x557FDB90  # AddEvent                EAX=player[+0xD8], EDX=eventlog; ret 0 (unused since 12b)

# ---- (Stage 12b) engine-native combat-event distribution -- replaces the Stage-2 single-player (C)
#      block. DistributeCombatEvent loops players 1..count-1 and files a TCombatEventLog for every
#      player who can SEE the combat hex (TAoWHSMap.VisibleForPlayer @0x557778A4) or PARTICIPATED
#      (TCombatPlayerList.IndexOfPlayer @0x557288B8), then replays it for the local human when DL != 0
#      (and map[+0xA5]==player && player[+0xA7]==0 && finaldata[+0x30]!=6). Vanilla's own fast-combat
#      call site is TArmyCombatMoveTE.ExecuteCombat+0x2b5 @0x55749BD9:
#          mov eax,[esi+0x18] ; mov dl,1 ; call 0x5572928c
#      -- byte-for-byte the form cave_towerraze now uses. Same module => plain call rel32 => PIC.
DISTRIBUTE_COMBAT_EVENT = 0x5572928C  # EAX = TCombatLogbook (= combat[+0x18]), DL = show-to-local-human; ret 0
EVENTLOG_SHOW           = 1           # DL. 1 = vanilla's fast-combat value (auto-replay for the local human).
                                      # ⚠ KEEP THIS A NAMED CONSTANT: 1 -> 0 is the ONE-BYTE re-tune if the
                                      # auto-popup is unwanted -- entries still file for every witness, they
                                      # just stop opening themselves.

# ---- (Stage 12d) the TACTICAL/modal half of the same fix, in cave_razedone. Vanilla's OWN
#      combat[+0x2C] completion callback -- TArmyCombatMoveTE.CombatExecuted @0x557496D4 -- ends with
#      exactly this sequence, and reaches it ONLY for a non-fast combat (its first act is
#      IsClass(combat, TFastCombat); true jumps straight to the epilogue @0x55749913):
#          557498F5  mov eax,[0x558fa040] ; call 0x557755f8    SynchroniseBegin(map)
#          557498FF  xor edx,edx          ; DL = 0
#          55749901  mov eax,[ebx+0x18]   ; call 0x5572928c    DistributeCombatEvent(logbook)
#          55749909  mov eax,[0x558fa040] ; call 0x55775600    SynchroniseEnd(map)
#      ⚠⚠ THE SYNCHRONISE WRAPPER IS LOAD-BEARING, NOT DECORATION -- omit it and the modal path
#      ASSERTS. DistributeCombatEvent files each witness's entry via TEventLogbook.AddEvent
#      @0x557FDB90, whose FIRST act is GetSynchronised(map) @0x55775608 + System.@Assert on false
#      (EventLog.pas:0x2c0). GetSynchronised is true iff map[+0x234] != 0 (this counter) OR
#      [[map+0x23C]+4][+0x48] != 0 (a token event is currently executing) OR map[+0x3C] & 2. Stage
#      12b's FAST call site runs inside the raze TE, so the token-event term already holds and it
#      needs no wrapper; the MODAL callback fires when the combat screen closes, OUTSIDE the TE, and
#      only the counter can hold. That asymmetry is exactly why vanilla wraps its modal site and not
#      its fast one -- do not "simplify" the wrapper away.
SYNCHRONISE_BEGIN   = 0x557755F8      # TAoWHSMap.SynchroniseBegin  EAX=map -> inc map[+0x234]; ret
SYNCHRONISE_END     = 0x55775600      # TAoWHSMap.SynchroniseEnd    EAX=map -> dec map[+0x234]; ret
EVENTLOG_SHOW_MODAL = 0               # DL for the TACTICAL path. Vanilla's modal value, deliberately NOT
                                      # EVENTLOG_SHOW(1): the tactical raze is only ever reached by the LOCAL
                                      # HUMAN (cave_razemode forces every AI/remote raze to fast), who has just
                                      # WATCHED the battle -- DL=1 would auto-replay it at them the instant it
                                      # ended. Entries still file for every witness either way; DL controls only
                                      # the replay. ⚠ KEEP IT A NAMED CONSTANT: 0 -> 1 is the one-byte re-tune.

# ---- (Design A) survivor re-home callees (all rel32; verified via Ghidra on AoWEPACK.dpl) ----
#   HARVEST model = ExploreS.TExplorationSite.CombatExecuted @0x557C1894 (UNCHANGED on this DLL):
#   per survivor obj (IsClass(TCombatUnit) && GetPlayer==0), refcount order tunit.slot0x28(AddRef) ->
#   obj.slot0x134(0)(SetUnit(0) sever) -> destArmy.slot0xAC(AddUnit) -> tunit.slot0x2C(Release).
TCD_GETCOUNT      = 0x55728BEC  # TCombatData.GetCount    EAX=combatData -> EAX=count; ret 0 ([[[+0x34]+8]+8])
TCD_GETOBJECTS    = 0x55728BF8  # TCombatData.GetObjects  EAX=combatData, EDX=i -> EAX=obj; ret 0
IS_CLASS          = 0x557010C0  # System._IsClass (JMP [0x558fb6bc] thunk)  EAX=obj, EDX=classref -> AL; ret 0
VMTREF_COMBATUNIT = 0x55715A54  # DATA slot: [VMTREF_COMBATUNIT] = TCombatUnit class VMT (reach via load delta)
TCOBJ_GETPLAYER   = 0x557268E4  # TCombatObject.GetPlayer EAX=obj -> AL (0 = independent militia); ret 0
#   obj+0x47 bit0 = dead/destroyed  (VERIFIED: TCombatSide.GetUndestroyedConquerObjects @0x55726e28 counts
#   an object alive iff (obj[+0x47] & 0x09)==0x00; mask 0x09 @0x55726e70, expected 0x00 @0x55726e74 -> bit0=dead).
#   obj+0x4C = the underlying TUnit (model piVar5[0x13]).
#   TArmy/TUnitList enumeration (VERIFIED): slot 0x54 = GetCount (EAX=list -> EAX=count); GetUnit below.
TUNITLIST_GETUNIT = 0x5578309C  # TUnitList.GetUnit  EAX=list, EDX=index -> EAX=unit (0 if OOB); ret 0
#   TUnitList.AddUnit @0x55782F1C is BYTE-IDENTICAL to TArmy.AddUnit @0x5578E86C: AddUnit(EAX=list, EDX=unit)
#   -> unit.slot0x8(EAX=unit, EDX=list) reparents (sets unit[+0x4]=list, DETACHES from old owner list) ->
#   AL=(list==unit[+0x4]); ret 0. This is the MOVE primitive (detach-from-source + add-to-dest).
TUNITLIST_ADDUNIT = 0x55782F1C  # TUnitList.AddUnit  EAX=list, EDX=unit -> move (reparent); ret 0
GENRAZE_CONT_VA   = 0x5575FD23  # GenerateRazeDefenders body resume (after the 7-byte prologue)

CLASSREF_DEF   = 0x557C1274   # DATA slot holding the TDefendersArmy VMT (value 0x557C12B4)
MAP_GLOBAL     = 0x558E9494   # DATA slot: *MAP_GLOBAL is a ptr, **MAP_GLOBAL is the map
FLAG_FIELD_SEL = 0x20217      # selector for field slot 0x80 -> co-located army container

# ---- Stage 3 (manual/tactical raze combat) ----
GET_RESOLVE_MODE = 0x557056A4  # AoWReg.GetCombatResolveMode  EAX=registry -> AL = 0 ask / 1 fast / 2 tactical
ENGINE_GLOBAL    = 0x558FA048  # DATA slot: *ENGINE_GLOBAL = engine; registry = [engine+0x5C]
FLAG_COMBAT_FAST = 0x202B0     # CreateCombat flag: fast (synchronous)
FLAG_COMBAT_TACT = 0x220110    # CreateCombat flag: tactical (modal)

# ---- Stage 3 v2 (ask-mode fast/manual CHOICE dialog, mirrors ExploreS.Search @0x557C1E5C) ----
TYPEREQ_CLASSPTR  = 0x557172AC  # *TYPEREQ_CLASSPTR = TCombatTypeRequestEventLog class VMT (reach via delta)
SET_CENTER_LOC    = 0x55728550  # TCombatTypeRequestEventLog.SetCenterLocation  EAX=self,EDX=x,ECX=y,+push l
GET_TOKEN_CONTROL = 0x5570372C  # NetworkE.GetTokenControl  EAX=[map+0x23C] tokenmgr, EDX=player -> EAX=tokenctrl
MAP_TOKENMGR_OFF  = 0x23C       # map+0x23C = token manager
MAP_SLOT_DISTRIB  = 0x12C       # map VMT slot: DistributeEventLog(EAX=map,EDX=log,CL=1,+push callback,context)
# raze TE re-issue: tower slot 0x160 CreateTE, 0x164 SetupTE; TE+0x18=-1 raze, TE+0x20=player|(choice<<4);
# token control slot 0x10 issues the TE; TE slot 0x2c releases.

FLAG_RAZEOK    = 0x558FA861   # BSS slack (runtime-only): re-entry gate for CanRaze + skip-avenger.
                              # ⚠ MOVED 2026-07-22 from 0x558FA801 = build_path_outerring.py's
                              # SCRATCH+1 (SY), which cave_stash overwrites with a map Y-coordinate on
                              # EVERY UNIT MOVE -- measured live (build_combatdiag.py logged 0x14/0x1D
                              # there mid-game). Bounded damage: v5 made the CanRaze gate stop reading
                              # razeok, so only cave_skipavenger still consumed the corrupted value
                              # (spuriously skipping the avenger spawn). Free BSS runs from 0x558FA844.
FLAG_HAPPENED  = 0x558FA802   # BSS slack (runtime-only): Stage-1 callback-fired proof (vestigial)
FLAG_RAZEASYNC = 0x558FA803   # BSS: set by cave_towerraze for the TACTICAL path -> cave_razedone owns the gate+raze
FLAG_RAZEPLAYER= 0x558FA804   # BSS: razing player byte stashed for cave_razedone (async tactical ExecuteRaze)
FLAG_RAZEGUARD = 0x558FA805   # BSS: set by cave_lossgarrison around PlaceRazeDefenders so the SetupRazeDefenderAG
                              #      hook makes the loss-garrison a GUARD AG (kind 2) not the vanilla WANDER (0xD)
FLAG_RAZENOFLEE= 0x558FA806   # BSS: set around the fast raze lifecycle so the fcExecute hook suppresses the side-0
                              #      (razer) TFleeCA -> razers "count as defenders", fight to a decisive result.
FLAG_RAZESURVIVORS = 0x558FA808  # BSS DWORD (survivor-army ptr): set by cave_rehome on a result==4 loss = the off-map
                              #      TDefendersArmy holding the LITERAL surviving (damaged/XP-carrying) militia; read+cleared
                              #      by cave_genraze (GenerateRazeDefenders entry hook) to SUBSTITUTE the fresh roster.
                              #      0 = none. Occupies 0x808..0x80B (byte 0x807 skipped for dword alignment). Next free 0x80C.
FLAG_LOOTWIN   = 0x558FA80C   # BSS (Part C): set to 1 by cave_towerraze's loot-win branch (result {3,6} with the loot
                              #      bit), cleared to 0 every cave_towerraze entry. cave_lootbattle reads it right after
                              #      the (synchronous, fast) loot battle: 1 -> resume NewTurn case 5 and award the gold;
                              #      0 (loss/stalemate) -> skip the gold (city already flipped by cave_lossgarrison on a loss).
                              #      (Fast-only: the fast/manual choice built on FLAG_LOOTASYNC/FLAG_LOOTWIN2 was reverted
                              #      2026-07-13 after regressions; 0x80D/0x80E are free again. See the raze memory file.)

# ---- cave placements (verified free zero window 0x5580C904..0x5580D640) ----
CAVE_TOWERRAZE   = 0x5580C910   # grown for Stage 3 v2, then Stage 10 (~1045 B; budget now to CAVE_CANRAZE
                                # since Stage 10 relocated cave_razedone into the D-region to free room)
CAVE_RAZEDONE    = 0x5580D500   # (Stage 12d) RELOCATED from 0x5580D3D0. Stage 10 had moved it from
                                # 0x5580CD00 into the D-region when cave_towerraze grew past that wall;
                                # 0x5580D3D0 then had only 144 B before cave_rebelchance @0x5580D460 and
                                # the cave already used 138. Stage 12d's combat-report block needs 32
                                # more, so it moves to the tail of this script's own region, where a
                                # 256 B reservation lands exactly on CAVE_SEED_RESV. The vacated slot is
                                # ZERO-FILLED (RAZEDONE_OLD below), not left live.
CAVE_CANRAZE     = 0x5580CD90
CAVE_SKIPAVENGER = 0x5580CDB0   # (Stage 2)
CAVE_TYPECHOSEN  = 0x5580CE10   # (Stage 3 v2: fast/manual choice dialog callback; ~115 B, ends ~0x5580CE83)
CAVE_LOSSGARRISON= 0x5580CE90   # (Stage 4/req2: shared SetPlayer(0)+Guard-garrison for both loss paths)
CAVE_SETUPGUARD  = 0x5580CF00   # (Stage 4/req2: SetupRazeDefenderAG entry hook -> kind 2 when razeguard set; ~41 B, ends ~0x5580CF29)
CAVE_NOFLEE      = 0x5580CF40   # (Stage 5/walls: fcExecute no-flee hook -> razer never withdraws when razing)
CAVE_REHOME      = 0x5580CF80   # (Design A: harvest surviving militia -> off-map TDefendersArmy; ~200 B budget)
CAVE_GENRAZE     = 0x5580D080   # (Design A: GenerateRazeDefenders entry hook -> substitute survivors)
CAVE_RAZEMODE    = 0x5580D100   # (bugfix: is-local-human gate so AI/remote razes force FAST, never dialog/modal)
CAVE_FORCEFAIL   = 0x5580D150   # (Stage 2.2 + AI-veto: RELOCATED here from 0x5580CDE0 -- grew too big for the
                                #  48 B slot. The old 0x5580CDE0..CE10 region is now dead/unreferenced (the hook
                                #  points here); harmless -- it reverts to zeros on a clean re-apply over vanilla.)
CAVE_END_LIMIT   = 0x5580D640   # next existing mod cave -- stay strictly below
CAVE_SEED_RESV   = 0x5580D600   # RESERVED by build_razeroster_vary.py (seed cave) -- Stage-4/5 caves stay below
CAVE_VALFIX_RESV = 0x5580D200   # RESERVED by build_razeeval_timing.py (cave_valfix, 18 B). cave_forcefail
                                # sits at 0x5580D150 and must stay BELOW this -- the old assert only
                                # checked CAVE_SEED_RESV, so growing forcefail would have silently
                                # overwritten another feature's cave (8 B of clearance as of 2026-07-21).

# ---- (Stage 12c) FIXED-LENGTH RESERVATIONS. process() writes exactly len(new) bytes, so whenever a
#      cave SHRINKS between stages the tail of the longer previous blob survives on disk: unreachable,
#      but live bytes that disassemble as garbage and that a later grow-back would collide with.
#      ⚠ THIS HAD ALREADY HAPPENED AT LEAST ONCE BEFORE STAGE 12 -- it is not a new failure mode, and
#      the reservations exist to stop it recurring, not merely to cover 12a/12b. An earlier stage
#      shrank cave_towerraze 1152 -> 1140 and orphaned 12 bytes at 0x5580CD84..0x5580CD8F:
#          5580CD84  8b 45 fc        mov   eax,[ebp-4]
#          5580CD87  0f b6 55 f8     movzx edx,byte ptr [ebp-8]
#          5580CD8B  e8 00 01 00 00  call  0x5580CE90   ; cave_lossgarrison, then FALLS INTO cave_canraze
#      -- present and byte-identical in backups\AoWEPACK.dpl.pre-panicnomelee, i.e. predating Stage 12.
#      Provably dead (module-wide scan for the absolute dword and for every E8/E9 rel32 in every CODE
#      section found NO reference, and no branch inside cave_towerraze targets >= 0x5580CD22), so the
#      reservation simply absorbs them: TOWERRAZE_RESV is 1152, which lands exactly on CAVE_CANRAZE and
#      zeroes the orphan. Only this script references that region.
#      Both blobs are zero-padded to their reservation, and towerraze_s1_prior is padded to
#      TOWERRAZE_RESV as well (NOT to len(cave_towerraze), which stopped matching the on-disk span the
#      moment 12b shrank the cave).
TOWERRAZE_RESV   = 1152         # 0x5580C910 .. 0x5580CD90 == CAVE_CANRAZE exactly (absorbs the 12 B orphan)
CITYGUARD_RESV   = 33           # 0x5580D2B0 .. 0x5580D2D1 -- 15 B clear of CAVE_CITYSEED
# (Stage 12d) the same doctrine applied to the relocation, and to the TWO further orphans the 12c
# sweep did not reach because they sit above the caves it was auditing. Both were proved dead the
# same way -- a module-wide scan of every E8/E9 rel32 and every absolute dword in EVERY section found
# ZERO references into either span (and zero .reloc entries):
#   0x5580D4E3..0x5580D4FA (23 B) tail of a pre-Part-C-v2 cave_lootbattle -- the older body tested the
#       loot-win flag with `cmp byte [ecx+0x558FA80C],0` (7 B) where the live one uses `movzx` (7 B)
#       plus a shorter branch, so the cave shrank and left its tail. Starts MID-instruction, i.e. it
#       cannot even be entered; absorbed by LOOTBATTLE_RESV.
#   0x5580D550..0x5580D586 (55 B) a complete pre-Stage-10 copy of cave_rebelchance, byte-identical to
#       the live one at 0x5580D460 apart from its two tail jumps; absorbed by RAZEDONE_RESV.
RAZEDONE_RESV    = 0x100        # 0x5580D500 .. 0x5580D600 == CAVE_SEED_RESV exactly
RAZEDONE_OLD     = 0x5580D3D0   # the slot Stage 12d vacates -- zero-filled by its own patch entry
RAZEDONE_OLD_RESV= 0x90         # 0x5580D3D0 .. 0x5580D460 == CAVE_REBELCHANCE exactly
LOOTBATTLE_RESV  = 0x60         # 0x5580D4A0 .. 0x5580D500 == CAVE_RAZEDONE (the new home) exactly
CAVE_RAZEDONE_S1 = 0x5580D3D0   # ⚠ FROZEN. src_towerraze_stage1 exists only to reproduce the bytes we
                                # accept as a Stage-1 prior, so it must keep baking the address it baked
                                # before the relocation. Pointing it at CAVE_RAZEDONE would silently
                                # redefine what "a Stage-1 file" looks like every time the cave moves.

# ---- (Stage 12e) THE LAST THREE ORPHANS in the region. 12c and 12d each reserved only the caves they
#      happened to be editing, so three more shrink-tails survived. Found by QA on the 12d pass
#      (2026-09-12) in the live DLL; all three proved dead by the SAME test 12d used, re-run at 12e:
#      every E8/E9 rel32 in CODE, every literal dword in EVERY section of the whole file, and all
#      63880 .reloc entries -- ZERO references into any of the three spans. Two short-rel8 candidates
#      surfaced and both are false positives: 0x5580CDEB is the forcefail orphan's OWN internal `je`,
#      and 0x5580CFEC is not an instruction boundary at all (it is byte 3 of the displacement in
#      `mov edx,[edx+0x55715a54]` @0x5580CFE8). No fall-through reaches any of them either --
#      cave_canraze ends in `jmp`, cave_skipavenger in `ret` @0x5580CDCE, cave_rehome in `ret`
#      @0x5580D03F.
#   0x5580CDA0..0x5580CDAB (11 B) a COMPLETE, instruction-aligned, enterable duplicate of the live
#       cave_canraze -- `push ebp; mov ebp,esp; add esp,-0x1C; jmp 0x5575FB86`, identical to the cave
#       at 0x5580CD90 but for the 0x10 delta in its rel32. Unlike 12d's mid-instruction lootbattle
#       tail this one COULD be entered, which is exactly why it should not be left lying there.
#       Absorbed by CANRAZE_RESV.
#   0x5580CDE0..0x5580CDFB (27 B) the pre-relocation cave_forcefail (tail jumps 0x5575FCB3 /
#       0x5575FCB7), stranded when the cave moved to 0x5580D150 and outgrew this slot. The
#       CAVE_FORCEFAIL comment has called this region dead since that move but nothing ever zeroed
#       it. Absorbed by SKIPAVENGER_RESV.
#   0x5580D040..0x5580D045 (5 B) `pop ebx; mov esp,ebp; pop ebp; ret` -- the tail of an older 197 B
#       cave_rehome, left when the cave shrank to 192 B. Absorbed by REHOME_RESV.
CANRAZE_RESV     = 0x20         # 0x5580CD90 .. 0x5580CDB0 == CAVE_SKIPAVENGER exactly (cave is 11 B)
SKIPAVENGER_RESV = 0x60         # 0x5580CDB0 .. 0x5580CE10 == CAVE_TYPECHOSEN  exactly (cave is 31 B)
REHOME_RESV      = 0x100        # 0x5580CF80 .. 0x5580D080 == CAVE_GENRAZE     exactly (cave is 192 B)

# ---- (Stage 5/walls) fcExecute no-flee hook: force the side-0 (razer) FLEE gate to the "no-flee" branch
#      when FLAG_RAZENOFLEE is set. Hook the 7-byte slot-0x64 predicate call; the cave REPLAYS the call
#      (preserving any side effect + AL) and, when razing, ORs AL=1 so the following TEST AL,AL;JNZ takes
#      the no-flee path. A perfect passthrough for every non-raze combat. ----
NOFLEE_HOOK    = 0x557444A9
NOFLEE_ORIG    = bytes.fromhex("8b c6 8b 10 ff 52 64")  # mov eax,esi; mov edx,[eax]; call [edx+0x64]
NOFLEE_CONT    = 0x557444B0                              # resume: TEST AL,AL ; JNZ 0x557444DF (no-flee)

# ---- (Design A) GenerateRazeDefenders ENTRY hook: E9 rel32 + 2 NOP over the 7-byte prologue.
#      Substitute the harvested survivors for the fresh roster on the loss-garrison path; else passthrough.
#      COMPOSES with build_razeroster_vary.py's SEED hook @0x5575FD36: the passthrough replays the 7-byte
#      prologue and jmps 0x5575FD23 (before the seed site), so the seed hook still runs untouched. ----
GENRAZE_HOOK   = 0x5575FD1C
GENRAZE_ORIG   = bytes.fromhex("53 56 57 55 83 c4 f8")   # push ebx;push esi;push edi;push ebp;add esp,-8 (vanilla)

# ---- (Stage 4/req2) SetupRazeDefenderAG entry hook: swap the AG kind 0xD(Wander)->2(Guard) when the
#      razeguard flag is set (i.e. only during cave_lossgarrison's PlaceRazeDefenders call). 9-byte
#      E9 rel32 + 4 NOP over the entry: push ebx;push esi;push edi;mov ebx,ecx;mov esi,edx;push 0xd. ----
SETUPAG_HOOK   = 0x5575FE0C
SETUPAG_ORIG   = bytes.fromhex("53 56 57 8b d9 8b f2 6a 0d")  # 9 displaced bytes (thru the PUSH 0xd)
SETUPAG_CONT   = 0x5575FE15                                    # resume: MOV DL,5 (rest of the setup)

# ---- VMT repoint (data patch; slot has a type-3 reloc so link-time VA is rebased at load) ----
VMT_SLOT       = 0x557C3358   # TTower VMT base 0x557C31A8 + 0x1B0
VMT_ORIG       = struct.pack("<I", EXECUTE_RAZE)      # C8 FF 75 55  (vanilla)
VMT_NEW        = struct.pack("<I", CAVE_TOWERRAZE)    # link-time cave VA -> loader rebases it (== Stage 1)

# ---- (Stage 8) generalization: ALL razeable non-city structures. The razeable set = the classes
#      implementing GetRazed/SetRazed (audited 2026-07-11 via VMT scan; metadata layout: self-ptr V-64,
#      classname V-32, instancesize V-28, parent V-24, parent-link = *[V-24] = parent base). All six
#      inherit EVERY collaborator our caves touch (audited slots 0x74/78/7C coords, 0x158 RazeEx,
#      0x15C SetupRazeDefenderAG, 0x160/0x164 CreateTE/SetupTE, 0x1A8 GenerateRazeDefenders,
#      0x1AC PlaceRazeDefenders, 0x1B0 ExecuteRaze=0x5575FFC8 vanilla, 0x1E8 Raze, 0x1EC CanRaze) --
#      the ONLY divergence is slot 0x1F0 SetPlayer: the five TPlayerStructure descendants OVERRIDE it
#      (income-source re-registration etc.) and TTeleport (direct TStructure child, unowned, VMT ends
#      at 0x1EC) has NO SetPlayer -- handled by the IsClass-gated VIRTUAL SetPlayer in cave_lossgarrison.
#      TCity: covered by Stage 9 (own repoints + cave_razedispatch; see the Stage-9 constants block).
#      No other class descends from a razeable one (855-VMT scan).
RAZE_VMT_SLOTS = [                # (class, VMT base) -- patch = base+0x1B0 -> cave_towerraze
    ("TAltar",           0x557CE7C4),
    ("TFarm",            0x557B281C),   # via TPlayerCropStructure < TPlayerStructure
    ("TMine",            0x557B4020),
    ("TPowerNode",       0x557CFFE4),
    ("TProductionPlace", 0x557BD68C),
    ("TTeleport",        0x557A4A28),   # direct TStructure child -- NO SetPlayer slot
]
VMT_PLAYERSTRUCT = 0x55714340     # TPlayerStructure VMT base (IsClass gate arg; reach via load-delta)
TCITY_VMT        = 0x557A73F0     # TCity VMT base (== [0x557A73B0], the classref Process/IsClass uses).
                                  # AI-veto v4/v5: cave_forcefail lets the AI raze ONLY cities
                                  # (v5 = leak-proof structural re-entry test; see src_forcefail).

# ---- CanRaze entry hook (E9 rel32 + NOP over 6 bytes: push ebp;mov ebp,esp;add esp,-0x1C) ----
CANRAZE_ENTRY  = 0x5575FB80
CANRAZE_ORIG   = bytes.fromhex("55 8b ec 83 c4 e4")   # displaced 6-byte prologue (vanilla)
CANRAZE_CONT   = 0x5575FB86                            # resume point (push ebx ...)

# ---- PlaceRazeDefenders avenger vcall hook (Stage 2; E8 rel32 + NOP over 6 bytes) ----
AVENGER_HOOK   = 0x557601F0                            # CALL dword ptr [ECX+0x1ac] = FF 91 AC 01 00 00
AVENGER_ORIG   = bytes.fromhex("ff 91 ac 01 00 00")   # vanilla == live (Stage 1 never touched this site)

# ---- (req1) CanRaze GATE hook: block ANY raze with no attacker forces, showing the vanilla thunk +
#      (reworded) message at click time -- BEFORE the confirm dialog, exactly like vanilla. In the
#      current (side-swapped) live CanRaze the predictor lets an empty-attacker raze pass; this hook
#      restores the vanilla "no forces -> refuse" at the source: the ATTACKER unit count.
#      Hooked at the result-decode (0x5575FC90 MOV EAX,[EBP-0x10]; MOV AL,[EAX+0x14]). The player's
#      units are added to the predictor via AddOpponent -> side 1 -> predictor+0x10 (a TList, count at
#      +8). If that count is 0 (no attacker forces on the structure), force BL=0 and jump into
#      CanRaze's own message block (0x5575FCB7, which LoadResStrings the reworded NotEnoughForces) ->
#      CanRaze returns false -> EXE plays the thunk + shows "Your forces aren't present", no dialog.
#      Otherwise replay the 6 displaced bytes and continue the gate. Structure-agnostic (works for the
#      user's tower whatever its exact class), position-independent (same-module jmps only, no delta),
#      single hook, reuses vanilla's message machinery. razeok re-entry is unaffected (cave_canraze
#      returns true at CanRaze ENTRY before this gate is reached). ----
FORCEFAIL_HOOK   = 0x5575FC90   # MOV EAX,[EBP-0x10] ; MOV AL,[EAX+0x14]  (6 bytes; after simfly's FC8B hook)
FORCEFAIL_ORIG   = bytes.fromhex("8b 45 f0 8a 40 14")
CANRAZE_GATE_CONT= 0x5575FC96   # continue the gate (ADD AL,0xFD ...)
CANRAZE_MSG      = 0x5575FCB7   # CanRaze's "not enough forces" message block (runs when BL==0)
CANRAZE_PASS     = 0x5575FCB3   # TEST BL,BL -> with BL=1 -> JNZ cleanup -> return true (can raze)
PRED_ATTACKER_SIDE = 0x10       # predictor+0x10 = side-1 list (opponents/attacker); TList.Count at +8
RAZE_ENTRY       = 0x557602F8   # TStructure.Raze entry = upper bound of the v5 re-entry range
                                # [EXECUTE_RAZE, RAZE_ENTRY): the ONLY CanRaze call sites inside are
                                # ExecuteRaze's top-gate vcall @0x5575FFF3 and RazeEx's re-check
                                # @0x5576025F (capstone-verified 2026-07-12) -- both post-approval.
GET_SUPERIORITY  = 0x5572B798   # TCombatPredictor.GetSuperiority (EAX=predictor -> EAX). For result
                                # 4 (militia wiped) it returns the RAZER'S predicted loss-strength %
                                # (0=flawless..100=pyrrhic); the v6 scorched-earth gate caps it at 50.

# ---- (Stage 9) CITY raze battles. TCity joins the real-combat raze (design doc:
#      City_Raze_Rebellion_Design.md). TCity.ExecuteRaze @0x557AB414 is a THIN wrapper = base
#      TStructure.ExecuteRaze + race-relation -30 on success, so the towerraze/razedone win paths
#      route through cave_razedispatch (IsClass TCity ? city wrapper : base) to keep the diplomacy
#      hit. TCity.GenerateRazeDefenders @0x557AB408 = GenerateRebelUnits+ret1 (the REBEL MOB: budget
#      25*GetSize, level<=2, typemask 0x03) -- the militia cave_towerraze fights via vcall 0x1A8 is
#      automatically the city mob. Repoints: slot 0x1A8 -> cave_citygenraze (Design-A survivor
#      substitution for cities; jump-in reuses cave_genraze's drain block -- the module load-delta is
#      anchor-independent), slot 0x15C -> cave_cityguard (razeguard -> base entry (hooked -> Guard
#      kind 2), else vanilla city fn incl. its 1/8 kind-5 raider flavor for avenger spawns).
#      Day-term: GenerateRebelUnits' seed store @0x557ABCE7 (`mov eax,[0x558FB720]; mov [eax],ebp`,
#      seed = x*10 + Map[+0x22C] + y) -> cave_cityseed adds Map[+0x174] so the city raze militia AND
#      rebellion mobs re-roll per day (mirrors build_razeroster_vary; user choice 2026-07-12).
#      Cave window note: 0x5580D200-0x5580D211 is cave_valfix (build_razeeval_timing.py) -- Stage-9
#      caves start at 0x5580D220 and must stay below CAVE_SEED_RESV.
TCITY_EXECRAZE   = 0x557AB414   # TCity.ExecuteRaze (base + relation -30)
TCITY_GENRAZE_V  = 0x557AB408   # TCity.GenerateRazeDefenders vanilla (= GenerateRebelUnits + ret 1)
TCITY_SETUPAG_V  = 0x557AA378   # TCity.SetupRazeDefenderAG vanilla (1/8 kind-5 raiders, else base)
# CITYSEED hook: inject the day term at the MAP-SEED add `add ebp,[eax+0x22c]` @0x557ABCD5 (eax already =
# the map ptr there). NOT the seed STORE @0x557ABCE7 -- that instruction's absolute operand [0x558FB720]
# carries a vanilla .reloc fixup at 0x557ABCE8; overwriting it leaves the loader rebasing bytes inside our
# E9 rel32 -> corrupt jump -> AV (the v1 crash, 2026-07-12). 0x557ABCD5 is a register-relative op = no
# reloc (verified against the vanilla .reloc table). eax is live as the map, so cave_cityseed needs no
# load-delta; it just replays the seed add and appends Map[+0x174].
CITYSEED_HOOK    = 0x557ABCD5   # add ebp,[eax+0x22c]   (6 bytes displaced; eax = map ptr, no reloc)
CITYSEED_ORIG    = bytes.fromhex("03 a8 2c 02 00 00")
CITYSEED_CONT    = 0x557ABCDB   # resume: mov eax,ebx  (the y-add + seed store run vanilla)
CAVE_RAZEDISPATCH= 0x5580D220
CAVE_CITYGENRAZE = 0x5580D260
CAVE_CITYGUARD   = 0x5580D2B0
CAVE_CITYSEED    = 0x5580D2E0
# ---- (Stage 9 bugfix) multi-hex razer lookup. cave_towerraze originally read only the CENTER field
#      [self+4].slot0x80(sel); correct for single-hex structures but a CITY is multi-hex and its garrison
#      often sits on a non-center footprint hex, so the lookup returned null -> Lnoarmy -> "raze does
#      nothing". cave_findrazer walks the WHOLE footprint exactly like TStructure.ListUnits @0x5575F37C
#      (the slot-0x1D4 army lister CanRaze uses -- which is why CanRaze passes and the dialog shows), and
#      returns the first footprint field's slot0x80(sel) armyHS. Single-hex structures resolve to [self+4]
#      as before. Naturally PIC (rel32 calls + vtable dispatch + immediates only).
CAVE_FINDRAZER   = 0x5580D310
INITHNWALK       = 0x557026D4   # HSEngine.InitHNWalk (EAX=buf, EDX=x, ECX=y, push l; ret 4)
WALKTONEXTHN     = 0x557026DC   # HSEngine.WalkToNextHN (EAX=buf)
GETFIELD         = 0x557020DC   # TMapLevel.GetField (EAX=level, EDX=x, ECX=y) -> field
GETTERRAIN       = 0x55701C8C   # TTerrainList.GetTerrain (EAX=list, EDX=idx) -> AL (<0 = not in footprint)

# ---- (Stage 10 / Part B) REBELLION BATTLES. A city rebellion is mechanically a city RAZE where
#      "garrison wins -> HOLD (city kept) instead of raze"; the loss (garrison wiped -> city flips
#      independent w/ the rebel mob as garrison) and stalemate outcomes are IDENTICAL to a city raze,
#      and the rebel mob IS the city raze-militia (TCity.GenerateRazeDefenders == GenerateRebelUnits).
#      So rebellions reuse cave_towerraze via a REBELLION BIT packed into the ExecuteRaze arg
#      (DL bit 6 = 0x40; low nibble = player, bits 4-5 = combat-type choice). v1 = FAST combat only
#      (arg = owner|0x10 fast|0x40 rebellion); the local-human fast/manual dialog is a later refinement
#      (needs the TE re-issue to carry the bit). cave_towerraze reads the bit: on the {3,6} win branch
#      (Lraze) it SKIPS the raze (city held); on Lnoarmy (undefended city) it flips via cave_lossgarrison
#      (rebels take the empty city). CheckRebellion @0x557AB534 rebellion branch: NOP the garrison
#      eviction (0x557AB5AC, so the garrison stays to DEFEND), KEEP the "Rebellion in X!" log, and
#      replace the vanilla flip+spawn (from 0x557AB632) with cave_rebellion -> the battle -> epilogue.
CAVE_REBELLION     = 0x5580D3B0
REBELLION_EPILOGUE = 0x557AB6B4   # CheckRebellion's shared epilogue (xor eax,eax; SEH pop; ret)
# ---- (Stage 10b) rebellion CHANCE table. Vanilla fires only at status<2 (Unruly 75% / Unrest 25%).
#      User model: Unruly 30% / Unrest 20% / Oppressed 10% / Enslaved & everything-else 0%. With the
#      user's wall/terrain loyalty bonuses removed, Oppressed/Enslaved now purely reflect garrison
#      strength -> an under-garrisoned suppressed (hostile-race) city drops toward Unrest/Unruly and can
#      revolt (and, via the battle rework, WIN vs a weak garrison). cave_rebelchance replaces the vanilla
#      status gate + threshold: threshold = {0:30, 1:20, 5:10, else 0}; keep the GetRazed skip; fall into
#      the vanilla Random(100) compare with EBX = threshold.
CAVE_REBELCHANCE   = 0x5580D460
REBELCHANCE_HOOK   = 0x557AB55F   # mov eax,ebx; sub al,2; jnc 0x557AB6B4  (10 bytes: the status<2 gate)
REBELCHANCE_ORIG   = bytes.fromhex("8b c3 2c 02 0f 83 4b 01 00 00")
RANDOM_CHECK       = 0x557AB58B   # resume: mov eax,[map]; ... Random(100); cmp EBX,EAX; jl skip
EVICT_NOP_HOOK     = 0x557AB5AC   # CALL MoveArmiesOutOfCity (E8 rel32) -> 5x NOP (keep the garrison)
EVICT_NOP_ORIG     = bytes.fromhex("e8 57 f2 ff ff")
FLIP_HOOK          = 0x557AB632   # xor edx,edx; mov eax,edi; mov ecx,[eax]  (6 bytes) -> E9 rel32 + NOP
FLIP_HOOK_ORIG     = bytes.fromhex("33 d2 8b c7 8b 08")

# ---- (Part C) LOOT BATTLES. Looting a captured city queues a 1-turn "loot" production; the gold is
#      awarded when it COMPLETES in TCityProductionControl.NewTurn @0x557A82A8, case 5. User design: the
#      delay is the penalty (you can't loot-and-run), so the battle fires at COMPLETION, just before the
#      gold. Mechanically a city loot == a city raze whose "looter WON" branch awards gold INSTEAD of
#      razing; loss (looter wiped -> city flips independent + populace garrison) and stalemate are
#      IDENTICAL to a city raze, and the populace IS the raze-militia/rebel-mob. So loot reuses
#      cave_towerraze via a LOOT BIT packed into the ExecuteRaze arg (DL bit 7 = 0x80; with fast bit 0x10
#      -> arg = owner|0x90). FAST only: the ask/tactical async paths (cave_typechosen re-issue,
#      cave_razedone) can't carry the loot bit and would raze. cave_lootbattle (hooked at case-5 top)
#      runs the battle, reads FLAG_LOOTWIN, and either resumes the case (award gold) or jumps to the
#      function epilogue (no gold; balanced updates since it hooks BEFORE BeginUpdate).
CAVE_LOOTBATTLE    = 0x5580D4A0   # after cave_rebelchance (ends ~0x5580D497), below the seed reserve 0x5580D600
LOOT_FAST          = 0x90         # ExecuteRaze arg bits: 0x10 (fast choice) | 0x80 (loot) ; low nibble = owner. Loot is
                                  # FAST-ONLY (the fast/manual choice was built then reverted 2026-07-13; raze memory file).
CITY_BEGINUPDATE   = 0x5575CB6C   # TProductionControl.BeginUpdate (EAX=self) -- the displaced case-5 call
NEWTURN_LOOT_HOOK  = 0x557A85B9   # case-5 top: mov eax,edi; call BeginUpdate  (7 bytes; reg-mov + rel32-call, no reloc)
NEWTURN_LOOT_ORIG  = bytes.fromhex("8b c7 e8 ac 45 fb ff")
NEWTURN_CASE5_RESUME = 0x557A85C0 # resume point after the displaced 7 bytes (xor ecx,ecx ...) = normal loot
NEWTURN_EPILOGUE   = 0x557A8880   # NewTurn shared tail (xor eax,eax; SEH pop; ret) -- loss path lands here


def assemble_pic(src_fn, addr, npops):
    """Two-pass like build_simfly.py, but anchors on load-delta pops robustly: a delta anchor is a
    `pop` whose immediately-preceding instruction is `call <addr-of-this-pop>` (the call/pop trick).
    Plain `pop`/`push` used for register save/restore are ignored, so caves may contain other pops."""
    guess = [addr + 0x40*(i+1) for i in range(npops)]   # big -> stable disp32 encodings
    for _ in range(8):
        code, _ = ks.asm(src_fn(guess), addr); code = bytes(code)
        insns = list(cs.disasm(code, addr)); anchors = []
        for i, ins in enumerate(insns):
            if ins.mnemonic == "pop" and i > 0:
                prev = insns[i-1]
                if prev.mnemonic == "call":
                    try: tgt = int(prev.op_str, 16)
                    except ValueError: tgt = None
                    if tgt == ins.address:
                        anchors.append(ins.address)
        assert len(anchors) == npops, f"expected {npops} delta anchors, found {len(anchors)}"
        if anchors == guess:
            return code
        guess = anchors
    raise RuntimeError("two-pass assembly did not converge")


# =====================================================================================
# STAGE-1 cave_towerraze  -- KEPT VERBATIM only to reproduce the exact Stage-1 bytes for the
# upgrade "acceptable prior". This is NOT written; it is the byte pattern we accept as a valid
# before-state so re-running --apply upgrades Stage 1 -> Stage 2. Do not edit (must match live).
# =====================================================================================
def src_towerraze_stage1(p):
    return f"""
        push ebp
        mov ebp, esp
        sub esp, 0x20
        push ebx
        push esi
        push edi
        mov dword ptr [ebp-4], eax
        mov dword ptr [ebp-8], edx
        call Ldelta
    Ldelta:
        pop ecx
        sub ecx, 0x{p[0]:X}
        mov dword ptr [ebp-0x1C], ecx

        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+4]
        mov edx, 0x{FLAG_FIELD_SEL:X}
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz Lnoarmy
        mov dword ptr [ebp-0xC], eax

        mov ecx, dword ptr [ebp-0x1C]
        mov eax, dword ptr [ecx+0x{CLASSREF_DEF:X}]
        xor ecx, ecx
        mov dl, 1
        call 0x{TARMY_CREATE:X}
        mov dword ptr [ebp-0x10], eax

        mov ecx, eax
        movzx edx, byte ptr [ebp-8]
        mov eax, dword ptr [ebp-4]
        mov ebx, dword ptr [eax]
        call dword ptr [ebx+0x1A8]

        mov eax, dword ptr [ebp-0x10]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x54]
        test eax, eax
        jz Lempty

        mov ecx, dword ptr [ebp-0x1C]
        mov ecx, dword ptr [ecx+0x{MAP_GLOBAL:X}]
        mov ecx, dword ptr [ecx]
        mov dword ptr [ebp-0x14], ecx

        mov eax, ecx
        call 0x{LOCK_GAMEOVER:X}

        mov eax, dword ptr [ebp-0x14]
        mov edx, 0x202B0
        call 0x{CREATE_COMBAT:X}
        mov dword ptr [ebp-0x18], eax

        mov edi, eax
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edi+0x30], edx
        mov ecx, dword ptr [ebp-0x1C]
        lea eax, [ecx+0x{CAVE_RAZEDONE_S1:X}]   /* frozen: NOT CAVE_RAZEDONE -- see the constant */
        mov dword ptr [edi+0x2C], eax

        mov ebx, dword ptr [ebp-4]
        mov esi, dword ptr [ebp-0xC]

        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        push eax
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x7C]
        movsx eax, al
        push eax
        mov eax, dword ptr [ebp-0x10]
        mov al, byte ptr [eax+0x12]
        push eax
        mov eax, dword ptr [ebp-0x10]
        mov al, byte ptr [eax+0x16]
        push eax
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        push eax
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x7C]
        movsx eax, al
        push eax
        push 1
        mov eax, dword ptr [esi+0x1C]
        mov cl, byte ptr [eax+0x16]
        mov dl, byte ptr [eax+0x12]
        mov eax, dword ptr [ebp-0x18]
        mov edi, dword ptr [eax]
        call dword ptr [edi+0x60]

        mov ebx, dword ptr [ebp-4]
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        push eax
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x7C]
        movsx eax, al
        push eax
        xor ecx, ecx
        mov esi, dword ptr [ebp-0xC]
        mov edx, dword ptr [esi+0x1C]
        mov eax, dword ptr [ebp-0x18]
        call 0x{ADD_ARMY:X}

        push -1
        push -1
        push -1
        push 1
        mov cl, 1
        mov edx, dword ptr [ebp-0x10]
        mov eax, dword ptr [ebp-0x18]
        call 0x{ADD_ARMY_EX:X}

        mov eax, dword ptr [ebp-0x18]
        mov byte ptr [eax+0x40], 1

        mov eax, dword ptr [ebp-0x18]
        call 0x{LOCK_EXECUTED:X}
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x68]
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x70]
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x64]
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x74]
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x6C]
        mov eax, dword ptr [ebp-0x18]
        call 0x{UNLOCK_EXECUTED:X}

        mov eax, dword ptr [ebp-0x14]
        call 0x{DESTROY_COMBAT:X}
        mov eax, dword ptr [ebp-0x14]
        call 0x{UNLOCK_GAMEOVER:X}

        mov ecx, dword ptr [ebp-0x1C]
        mov byte ptr [ecx+0x{FLAG_RAZEOK:X}], 1
        movzx edx, byte ptr [ebp-8]
        mov eax, dword ptr [ebp-4]
        call 0x{EXECUTE_RAZE:X}
        push eax
        mov ecx, dword ptr [ebp-0x1C]
        mov byte ptr [ecx+0x{FLAG_RAZEOK:X}], 0
        pop eax
        jmp Lepi

    Lempty:
    Lnoarmy:
        movzx edx, byte ptr [ebp-8]
        mov eax, dword ptr [ebp-4]
        call 0x{EXECUTE_RAZE:X}
    Lepi:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    """


# =====================================================================================
# STAGE-2 cave_towerraze  (EAX=tower, DL=player)  -- ExecuteRaze replacement for TTower
#   Delta from Stage 1: after the synchronous run and BEFORE DestroyCombat we (A) latch the
#   fast-combat result byte combat[+0x14] into [ebp-0x20] and (C) file a replayable combat-log
#   entry; after teardown we (A) raze ONLY when the result is in {3,6} (razer won), else fall
#   through leaving the tower standing.  Locals: [ebp-4]=tower [ebp-8]=player [ebp-0xC]=visitor
#   [ebp-0x10]=militia [ebp-0x14]=map [ebp-0x18]=combat [ebp-0x1C]=load-delta [ebp-0x20]=result.
# =====================================================================================
def src_towerraze(p):
    return f"""
        push ebp
        mov ebp, esp
        sub esp, 0x28                        /* Stage 10: +4 rebellion @[ebp-0x24]; Part C: +4 loot @[ebp-0x28] */
        push ebx
        push esi
        push edi
        mov dword ptr [ebp-4], eax          /* tower (self) */
        /* Arg (DL) bit-packed: low nibble = player; bits 4-5 = chosen combat type (0 ask/1 fast/2 tact);
           bit 6 (0x40) = REBELLION (Stage 10, cave_rebellion); bit 7 (0x80) = LOOT (Part C, cave_lootbattle).
           The first raze has type 0. Rebellion and loot both pack the fast bit (0x10) so they resolve FAST. */
        movzx eax, dl
        mov edx, eax
        and edx, 0xF
        mov dword ptr [ebp-8], edx          /* player = arg & 0x0F */
        mov edx, eax
        shr edx, 4
        and edx, 3
        mov dword ptr [ebp-0x20], edx       /* chosen type (0/1/2) -> reused as effective mode */
        mov edx, eax                        /* (Part C) loot flag = arg bit 7 (0x80) */
        shr edx, 7
        and edx, 1
        mov dword ptr [ebp-0x28], edx       /* loot flag (1 = a loot battle, not a raze/rebellion) */
        shr eax, 6
        and eax, 1
        mov dword ptr [ebp-0x24], eax       /* rebellion flag (1 = this is a rebellion, not a raze) */
        call Ldelta
    Ldelta:
        pop ecx
        sub ecx, 0x{p[0]:X}                  /* ecx = runtime-linktime load delta */
        mov dword ptr [ebp-0x1C], ecx
        /* (Stage 5/walls) defensive: heal a leaked no-flee flag from a prior raze whose combat threw
           before the normal clear (fcExecute is shared; a stuck flag would suppress flee in unrelated
           fast combats). Every raze entry starts clean; the leak window is bounded to one raze. */
        /* (also Design A + AI-veto v3 hardening) heal ALL raze flags a prior THROWN raze could have
           left stuck: noflee (would gag flee in unrelated combats), the survivor-army ptr (would drain
           a stale harvest into the wrong roster), and razeok (would bypass the CanRaze AI veto AND the
           avenger-skip for the rest of the session). EAX is dead here (chosen type already stored). */
        xor eax, eax
        mov byte ptr [ecx+0x{FLAG_RAZENOFLEE:X}], al
        mov dword ptr [ecx+0x{FLAG_RAZESURVIVORS:X}], eax
        mov byte ptr [ecx+0x{FLAG_RAZEOK:X}], al
        mov byte ptr [ecx+0x{FLAG_LOOTWIN:X}], al   /* (Part C) default loot-win = 0 each entry */

        /* --- razing army container: walk the WHOLE footprint (Stage-9 fix for multi-hex cities), not
               just the center field. cave_findrazer returns the first footprint field's slot0x80(sel)
               armyHS -- matching CanRaze's ListUnits walk (slot 0x1D4). Single-hex structures still
               resolve to [self+4]. Without this a city garrison on a non-center hex -> Lnoarmy -> nothing. */
        mov eax, dword ptr [ebp-4]           /* self */
        call 0x{CAVE_FINDRAZER:X}            /* -> EAX = razer armyHS (footprint-wide) or 0 */
        test eax, eax
        jz Lnoarmy
        mov dword ptr [ebp-0xC], eax         /* visitor container (armyHS) */

        /* --- create hidden militia (TDefendersArmy) --- */
        mov ecx, dword ptr [ebp-0x1C]
        mov eax, dword ptr [ecx+0x{CLASSREF_DEF:X}]   /* *CLASSREF_DEF = TDefendersArmy VMT */
        xor ecx, ecx
        mov dl, 1
        call 0x{TARMY_CREATE:X}              /* -> EAX = militia */
        mov dword ptr [ebp-0x10], eax

        /* --- fill via GenerateRazeDefenders (tower VMT slot 0x1A8) --- */
        mov ecx, eax                         /* ECX = out = militia */
        movzx edx, byte ptr [ebp-8]          /* player (ignored by callee) */
        mov eax, dword ptr [ebp-4]           /* tower */
        mov ebx, dword ptr [eax]
        call dword ptr [ebx+0x1A8]

        /* --- roster count (slot 0x54) --- */
        mov eax, dword ptr [ebp-0x10]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x54]
        test eax, eax
        jz Lempty

        /* --- map = **(MAP_GLOBAL) --- */
        mov ecx, dword ptr [ebp-0x1C]
        mov ecx, dword ptr [ecx+0x{MAP_GLOBAL:X}]
        mov ecx, dword ptr [ecx]
        mov dword ptr [ebp-0x14], ecx        /* map */

        /* --- (Stage 3) stash razing player for cave_razedone's async tactical raze --- */
        mov ecx, dword ptr [ebp-0x1C]
        mov al, byte ptr [ebp-8]
        mov byte ptr [ecx+0x{FLAG_RAZEPLAYER:X}], al

        /* --- (Stage 3) effective mode = packed choice (if set) else the registry setting --- */
        cmp dword ptr [ebp-0x20], 0          /* chosen type from the prologue */
        jne L3_modeset                       /* choice already made -> use it as the mode */
        mov eax, dword ptr [ebp-0x1C]
        mov eax, dword ptr [eax+0x{ENGINE_GLOBAL:X}]   /* engine ptr */
        mov eax, dword ptr [eax+0x5C]                  /* registry */
        call 0x{GET_RESOLVE_MODE:X}                    /* -> AL = 0 ask / 1 fast / 2 tactical */
        movzx eax, al
        mov dword ptr [ebp-0x20], eax
    L3_modeset:
        /* (bugfix) Only the LOCAL HUMAN whose raze this is may see the fast/manual dialog or a modal
           tactical fight. An AI/remote razer previously inherited the registry setting -> if it was
           "ask" or "tactical" it presented THIS machine's human a dialog for a battle they aren't in,
           and accepting froze them in a modal combat with no controllable army. Force those to FAST.
           2026-07-21: ALSO require that the army which will actually FIGHT belongs to that same
           player. cave_findrazer returns the FIRST army found on the structure's footprint, which
           for a multi-hex city need not be the razer named in the TE -- so the old check could clear
           a manual fight for a battle whose side 0 is somebody else's stack. Vanilla never offers a
           manual resolve unless a local interactive human is genuinely a party: TArmyCombatMoveTE.
           SetupCombat gates on TCombat.PlayerTypeInvolved(combat, type-set bit0) @0x5572724C.
           Enforcing the equivalent HERE -- before CreateCombat -- is strictly stronger than checking
           after it, because a TACTICAL CreateCombat already disables the map turn timer, so a combat
           we created and then declined to run modal would leave the world stopped. */
        mov eax, dword ptr [ebp-0xC]         /* visitor container (non-NIL: Lnoarmy already screened it) */
        mov eax, dword ptr [eax+0x1C]        /* the army AddArmy will enter as side 0 */
        test eax, eax                        /* read earlier than the old code did -> screen it here too */
        jz L3_forcefast
        movzx eax, byte ptr [eax+0x12]       /* its owning player (same byte Setup passes as atkPlayer) */
        cmp eax, dword ptr [ebp-8]           /* == the player named in the raze TE? */
        jne L3_forcefast
        movzx edx, byte ptr [ebp-8]          /* razing player -> DL */
        call 0x{CAVE_RAZEMODE:X}             /* AL = 1 iff local human's own raze */
        test al, al
        jnz L3_modeok
    L3_forcefast:
        mov byte ptr [ebp-0x20], 1           /* AI/remote/foreign-army -> FAST (dword's upper bytes already 0) */
    L3_modeok:
        /* (bugfix 2026-07-21) Never build a SECOND combat. CreateCombat @0x55778714 raises
           "Combat already created" when map[+0x120] != 0, and this cave has no SEH frame -- the
           unwind would skip DestroyCombat/UnlockGameOverEvent and leave map[+0x120] non-null for the
           rest of the session, after which EVERY later battle raises too. Under simultaneous turns
           another battle really can be live when a raze / rebellion / loot fires. Bail out instead:
           the structure simply stands this time (the AI's RazeControl is one-shot and just moves on;
           a human can click raze again). */
        mov eax, dword ptr [ebp-0x14]        /* map */
        cmp dword ptr [eax+0x120], 0
        jne Lepi
        cmp dword ptr [ebp-0x20], 0          /* ask (0) with no choice yet -> present the dialog */
        je L3_askdialog                      /* (this slot is reused for the result on the fast path) */

        /* --- LockGameOverEvent only on the FAST path (tactical is modal; its lock would leak) --- */
        cmp dword ptr [ebp-0x20], 2
        je L3_nolock
        mov eax, dword ptr [ebp-0x14]
        call 0x{LOCK_GAMEOVER:X}
    L3_nolock:
        /* --- CreateCombat: FAST 0x{FLAG_COMBAT_FAST:X} unless tactical (2) -> 0x{FLAG_COMBAT_TACT:X} --- */
        mov eax, dword ptr [ebp-0x14]
        mov edx, 0x{FLAG_COMBAT_FAST:X}
        cmp dword ptr [ebp-0x20], 2
        jne L3_flag
        mov edx, 0x{FLAG_COMBAT_TACT:X}
    L3_flag:
        call 0x{CREATE_COMBAT:X}
        mov dword ptr [ebp-0x18], eax        /* combat */

        /* --- inline SetupCombat (mirror @0x557C1960) --- */
        mov edi, eax                         /* edi = combat */
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edi+0x30], edx        /* combat[+0x30] = tower (context) */
        mov ecx, dword ptr [ebp-0x1C]
        lea eax, [ecx+0x{CAVE_RAZEDONE:X}]   /* runtime addr of cave_razedone */
        mov dword ptr [edi+0x2C], eax        /* combat[+0x2C] = completion callback */

        mov ebx, dword ptr [ebp-4]           /* ebx = tower (site-coord role) */
        mov esi, dword ptr [ebp-0xC]         /* esi = visitor container */

        /* Setup stack args (right-to-left): visitor coords 74/78/7c */
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        push eax
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x7C]
        movsx eax, al
        push eax
        /* defender player/team from militia (byte moves, upper garbage harmless as vanilla) */
        mov eax, dword ptr [ebp-0x10]
        mov al, byte ptr [eax+0x12]
        push eax
        mov eax, dword ptr [ebp-0x10]
        mov al, byte ptr [eax+0x16]
        push eax
        /* site coords 74/78/7c (ebx = tower) */
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        push eax
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x7C]
        movsx eax, al
        push eax
        /* arg4 isFast: 1 on the fast path, 0 for tactical (matches the CreateCombat flag) */
        mov eax, 1
        cmp dword ptr [ebp-0x20], 2
        jne L3_isfast
        xor eax, eax
    L3_isfast:
        push eax
        /* atk player/team from visitor army [visitor+0x1c] */
        mov eax, dword ptr [esi+0x1C]
        mov cl, byte ptr [eax+0x16]          /* atkTeam  -> CL */
        mov dl, byte ptr [eax+0x12]          /* atkPlayer-> DL */
        mov eax, dword ptr [ebp-0x18]        /* combat */
        mov edi, dword ptr [eax]
        call dword ptr [edi+0x60]            /* TCombat.Setup (callee cleans, ret 0x24) */

        /* AddArmy(combat, visitorArmy, side0, site l,y,x) */
        mov ebx, dword ptr [ebp-4]
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        push eax
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x7C]
        movsx eax, al
        push eax
        xor ecx, ecx                         /* side 0 */
        mov esi, dword ptr [ebp-0xC]
        mov edx, dword ptr [esi+0x1C]        /* visitor army */
        mov eax, dword ptr [ebp-0x18]
        call 0x{ADD_ARMY:X}                  /* ret 0xC -> EAX = razer TCombatParty */

        /* (Stage 5/walls) clear the razer party's behind-wall flag [+0x18]. AddArmy set it from the
           WALLED tower hex via map-msg 0x1123; it is the ONLY input to TCombat.Initialize's wall
           branch, so zeroing it means NO TCombatWall is built -> the raze is a wall-less "inside"
           fight (like an exploration site): a non-flyer engages the militia directly, no result-8
           "cannot breach wall" withdrawal, no result-9. The militia party (AddArmyEx, pos -1) never
           sets [+0x18]. A TCombatWall is not a conquer object, so this cannot flip the confirmed
           flyer win. EAX = the razer party (verified: AddArmy tail MOV EAX,[EBP-8]; RET 0xC). */
        mov byte ptr [eax+0x18], 0

        /* AddArmyEx(combat, militia, side1, partyPos=1, -1,-1,-1) */
        push -1
        push -1
        push -1
        push 1
        mov cl, 1                            /* side 1 */
        mov edx, dword ptr [ebp-0x10]        /* militia */
        mov eax, dword ptr [ebp-0x18]
        call 0x{ADD_ARMY_EX:X}               /* ret 0x10 */

        mov eax, dword ptr [ebp-0x18]
        mov byte ptr [eax+0x40], 1           /* combat[+0x40] = 1 */

        /* --- (Stage 3) tactical (mode 2) resolves via the callback; fast runs synchronously here --- */
        cmp dword ptr [ebp-0x20], 2
        je L3_tactical

        /* FAST path: mark async=0 so cave_razedone leaves the raze to this cave's own gate below */
        mov ecx, dword ptr [ebp-0x1C]
        mov byte ptr [ecx+0x{FLAG_RAZEASYNC:X}], 0
        /* (Stage 5/walls) arm no-flee for the whole fast run: side-0 (razer) units cannot withdraw. */
        mov byte ptr [ecx+0x{FLAG_RAZENOFLEE:X}], 1

        /* --- run the fast-combat lifecycle synchronously --- */
        mov eax, dword ptr [ebp-0x18]
        call 0x{LOCK_EXECUTED:X}
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x68]            /* Initialize */
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x70]            /* Activate */
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x64]            /* Execute (resolve) */
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x74]            /* Deactivate */
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x6C]            /* Finalize */
        mov eax, dword ptr [ebp-0x18]
        call 0x{UNLOCK_EXECUTED:X}           /* 1->0 : fires cave_razedone */
        /* (Stage 5/walls) disarm no-flee -- fcExecute is shared; only OUR raze run may suppress flee. */
        mov ecx, dword ptr [ebp-0x1C]
        mov byte ptr [ecx+0x{FLAG_RAZENOFLEE:X}], 0

        /* === (A) latch fast-combat result byte combat[+0x14] (valid: after run, before Destroy) === */
        mov eax, dword ptr [ebp-0x18]
        movzx eax, byte ptr [eax+0x14]
        mov dword ptr [ebp-0x20], eax        /* result: {3,6}=razer won */

        /* === (Stage 12b) COMBAT REPORT -- file it for EVERY witness, not just the razing player.
               Replaces Stage 2's hand-rolled single-player (C) block. DistributeCombatEvent walks
               players 1..count-1 and files a TCombatEventLog for each that can SEE the combat hex
               (VisibleForPlayer) or PARTICIPATED (IndexOfPlayer), then replays it for the local human
               when DL != 0. Vanilla's own fast-combat call site is TArmyCombatMoveTE.ExecuteCombat
               +0x2b5 @0x55749BD9 -- `mov eax,[esi+0x18]; mov dl,1; call 0x5572928c` -- identical.
               Window is unchanged: after the run, BEFORE DestroyCombat, the only time combat[+0x18]
               is valid. The logbook is never nil (allocated in TCombat.Create+0x84, its +0xC/+0x10
               TCombatData members in TCombatLogbook.Create @0x55728D80) and Initialize/Finalize
               (slots 0x68/0x6C, both called above) populate them. SetCombatLogbook does
               Release(old)/AddRef(new) per filed event, so the logbook outlives DestroyCombat.
               Delphi callee-save, plain `ret 0`; nothing below reads ESI/EDI. === */
        mov eax, dword ptr [ebp-0x18]        /* combat */
        mov eax, dword ptr [eax+0x18]        /* combat[+0x18] = TCombatLogbook */
        mov dl, 0x{EVENTLOG_SHOW:X}          /* 1 = vanilla's fast-combat value (replay for local human) */
        call 0x{DISTRIBUTE_COMBAT_EVENT:X}   /* AoWE.DistributeCombatEvent @0x5572928C */

        /* === (Design A) result==4 (decisive defender win): harvest the LITERAL surviving militia
               (already-damaged, XP-carrying) into an off-map TDefendersArmy stashed in
               FLAG_RAZESURVIVORS -- BEFORE DestroyCombat frees combatData. The result==4 loss gate
               below then routes through cave_lossgarrison -> PlaceRazeDefenders -> GenerateRazeDefenders,
               where cave_genraze substitutes these survivors for the fresh roster. Preserves [ebp-*]
               (cave_rehome uses its own frame + preserves EBX/ESI/EDI). === */
        cmp dword ptr [ebp-0x20], 4
        jne Lno_rehome
        mov eax, dword ptr [ebp-0x18]        /* combat */
        call 0x{CAVE_REHOME:X}
    Lno_rehome:

        mov eax, dword ptr [ebp-0x14]
        call 0x{DESTROY_COMBAT:X}            /* DestroyCombat(map) */
        mov eax, dword ptr [ebp-0x14]
        call 0x{UNLOCK_GAMEOVER:X}           /* UnlockGameOverEvent(map) */

        /* Militia LEAKED (unchanged Stage 1): a never-touched TArmy cannot fault; the unverified
           TDefendersArmy destructor could double-free combat-owned units. Accept the per-raze leak. */

        /* === (A) GATE: three outcomes keyed on the result byte combat[+0x14] (UpdateStatus @0x557282E4):
               3 or 6 = razer WON -> raze;  4 = DECISIVE defender win (razer wiped, militia survive) ->
               Guard garrison;  ELSE (2 stalemate / 5 mutual) -> NOTHING (tower untouched -- no raze, no
               SetPlayer, no garrison). 2 is the harmless-flyer-vs-melee-walkers standoff (neither side
               can destroy the other's conquer objects); with no-flee the razer doesn't withdraw so it
               latches 2, not a flee-loss. 8/9 (wall) are impossible since the wall fix. === */
        mov eax, dword ptr [ebp-0x20]        /* latched result */
        cmp eax, 3
        je Lraze
        cmp eax, 6
        je Lraze
        cmp eax, 4                           /* only a DECISIVE defender win garrisons */
        jne Lepi                             /* 2 (stalemate) / 5 (mutual) / else -> do nothing */
        /* --- (Stage 4/req2) FAILED raze battle: the defenders that beat you GARRISON the tower as a
               GUARD stack. Shared cave_lossgarrison does it in the correct order: SetPlayer(tower,0)
               = independent FIRST (so the roster lands on the now-unowned tower hex, not shunted
               adjacent), THEN PlaceRazeDefenders under the razeguard flag so its AG is a Guard (kind
               2) not the vanilla Wander (0xD). Roster = the same seed-stable composition that just
               fought (per-day seed; see build_razeroster_vary.py). DestroyCombat/UnlockGameOverEvent
               already ran above -> clean post-combat state; the garrison touches only the map. */
        mov eax, dword ptr [ebp-4]           /* tower */
        movzx edx, byte ptr [ebp-8]          /* razing player */
        call 0x{CAVE_LOSSGARRISON:X}         /* SetPlayer(0) + Guard garrison */
        jmp Lepi
    Lraze:
        /* (Part C) a LOOT battle the looter WON -> flag the win for cave_lootbattle and do NOT raze;
           NewTurn case 5 resumes and awards the plunder gold + SetRazed. The looting garrison survives. */
        cmp dword ptr [ebp-0x28], 0
        je Lraze_noloot
        mov ecx, dword ptr [ebp-0x1C]
        mov byte ptr [ecx+0x{FLAG_LOOTWIN:X}], 1
        jmp Lepi
    Lraze_noloot:
        /* (Stage 10) a REBELLION the garrison WON -> city is HELD, do NOT raze. The garrison (side-0,
           real army) survives via the normal combat write-back; the rebel mob is dead. */
        cmp dword ptr [ebp-0x24], 0
        jne Lepi
        mov ecx, dword ptr [ebp-0x1C]
        mov byte ptr [ecx+0x{FLAG_RAZEOK:X}], 1
        movzx edx, byte ptr [ebp-8]          /* Stage3: `and dl,0x0F` when TE[+0x20] is packed */
        mov eax, dword ptr [ebp-4]
        call 0x{CAVE_RAZEDISPATCH:X}         /* Stage 9: base ExecuteRaze, or the TCity wrapper (-30 relation) */
        mov ecx, dword ptr [ebp-0x1C]
        mov byte ptr [ecx+0x{FLAG_RAZEOK:X}], 0
        jmp Lepi

    L3_tactical:                             /* (Stage 3) tactical combat; cave_razedone owns the gate+raze */
        mov ecx, dword ptr [ebp-0x1C]
        mov byte ptr [ecx+0x{FLAG_RAZEASYNC:X}], 1
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x68]            /* Initialize */
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x70]            /* Activate */
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x64]            /* Execute -> AL (1 = went modal) */
        cmp al, 1
        je Lepi                              /* modal: combat is live; callback fires async at modal end */
        /* resolved synchronously (AI/instant): finalize now (cave_razedone fires in Finalize) */
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x74]            /* Deactivate */
        mov eax, dword ptr [ebp-0x18]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x6C]            /* Finalize */
        /* (Stage 12f) DestroyCombat takes the MAP, NOT the combat -- see the header note. This read
           [ebp-0x18] (the combat) from Stage 3 until 2026-09-12; the fast path 3 instructions above
           has always had it right at [ebp-0x14]. */
        mov eax, dword ptr [ebp-0x14]        /* map */
        call 0x{DESTROY_COMBAT:X}
        jmp Lepi

    L3_askdialog:                            /* (Stage 3 v2) present the fast/manual choice; callback re-issues */
        mov ecx, dword ptr [ebp-0x1C]
        mov eax, dword ptr [ecx+0x{TYPEREQ_CLASSPTR:X}]   /* *classptr = TCombatTypeRequestEventLog VMT */
        xor ecx, ecx
        mov dl, 1
        call 0x{TEVENTLOG_CREATE:X}          /* -> EAX = eventlog */
        mov esi, eax                         /* esi = eventlog */
        /* SetCenterLocation(eventlog, x, y, l) from the tower's coords (push l, push y, x in EAX) */
        mov eax, dword ptr [ebp-4]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x7C]            /* l */
        push eax
        mov eax, dword ptr [ebp-4]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x78]            /* y */
        push eax
        mov eax, dword ptr [ebp-4]
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x74]            /* x */
        mov edx, eax                         /* EDX = x */
        mov eax, esi                         /* EAX = eventlog */
        pop ecx                              /* ECX = y */
        call 0x{SET_CENTER_LOC:X}            /* (cleans the pushed l, ret 4) */
        mov al, byte ptr [ebp-8]
        mov byte ptr [esi+0x19], al          /* eventlog[+0x19] = razing player */
        mov byte ptr [esi+0x1A], 0
        /* (bugfix 2026-07-22) eventlog[+0x24] = request-live. Vanilla's own handler
           RequestCombatTypeCallBack @0x557489CC tests this FIRST (`cmp byte [edi+0x24],0; je bail`)
           and vanilla's creator sets it -- but this cave never did. cave_typechosen was taught to
           honour the same contract, which made every choice bail: the dialog appeared, you picked,
           and nothing happened. Set it here so the flag means what the reader assumes. */
        mov byte ptr [esi+0x24], 1
        /* map.DistributeEventLog(eventlog, 1, cave_typechosen, tower) */
        mov eax, dword ptr [ebp-4]           /* context = tower */
        push eax
        mov ecx, dword ptr [ebp-0x1C]
        lea eax, [ecx+0x{CAVE_TYPECHOSEN:X}] /* runtime callback addr */
        push eax
        mov eax, dword ptr [ebp-0x14]        /* map */
        mov cl, 1
        mov edx, esi                         /* eventlog */
        mov ebx, dword ptr [eax]
        call dword ptr [ebx+0x{MAP_SLOT_DISTRIB:X}]   /* (cleans the 2 pushes, ret 8) */
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x2C]            /* release eventlog handle */
        jmp Lepi                             /* return; the callback re-issues the raze with the choice */

    Lempty:                                  /* forces present, tower UNDEFENDED (no roster) -> raze normally */
        cmp dword ptr [ebp-0x24], 0          /* (Stage 10) rebellion with no rebels mustered -> city HELD */
        jne Lepi
        cmp dword ptr [ebp-0x28], 0          /* (Part C) loot of an unpopulated city -> trivially won -> gold */
        je Lempty_raze
        mov ecx, dword ptr [ebp-0x1C]
        mov byte ptr [ecx+0x{FLAG_LOOTWIN:X}], 1
        jmp Lepi
    Lempty_raze:
        movzx edx, byte ptr [ebp-8]
        mov eax, dword ptr [ebp-4]
        call 0x{CAVE_RAZEDISPATCH:X}         /* vanilla undefended raze (Stage 9: dispatched, city keeps -30) */
        jmp Lepi
    Lnoarmy:                                 /* (req1) NO army on the tower's hex -> block; tower stands, no raze.
                                                CanRaze's reworded "forces aren't present" covers the click-time case. */
        cmp dword ptr [ebp-0x24], 0          /* (Stage 10) rebellion in an UNDEFENDED city -> rebels seize it */
        je Lepi
        mov eax, dword ptr [ebp-4]
        movzx edx, byte ptr [ebp-8]
        call 0x{CAVE_LOSSGARRISON:X}         /* SetPlayer(0) + spawn the independent rebel garrison */
    Lepi:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    """

# =====================================================================================
# cave_razedone  (EAX=context=tower, EDX=combat)  -- combat[+0x2C] completion callback.
# FAST path (razeasync=0): cave_towerraze owns the raze after its synchronous run -> here we just
# mark the flag and return. TACTICAL path (razeasync=1): the fast run didn't happen; THIS callback
# (fired at Finalize, sync or async at the modal end) owns the gate + raze/SetPlayer, using the
# razing player stashed in BSS. tower and combat are parked in EDI/ESI at entry (EDX=combat is
# clobbered by the result read, and the result==4 branch's cave_rehome call clobbers EAX=tower), so
# both survive for cave_lossgarrison / ExecuteRaze. cave_razedone fires pre-DestroyCombat, so the
# tactical loss path harvests the LITERAL survivors (cave_rehome) BEFORE the garrison, exactly like
# the fast path. THREE load-delta anchors (the rehome and ExecuteRaze calls each clobber ECX, so the
# delta is recomputed before touching a BSS flag afterward). EBX untouched; ESI/EDI push/pop-balanced.
#
# WHERE THE CALLBACK ACTUALLY FIRES (traced 2026-09-12, needed for the Stage 12d window):
#   TCombat.UnlockExecuted @0x55728104 decrements combat[+0x28] and, on reaching 0 with a callback
#   installed (`cmp word [combat+0x2e],0` -- a high-half non-nil test on the [+0x2c] pointer itself,
#   there is no separate field), does `mov edx,combat ; mov eax,[combat+0x30] ; call [combat+0x2c]`.
#   TCombat.Initialize LOCKS at its own +0x8 (0x55727C9C) and TCombat.Finalize UNLOCKS at its tail
#   (0x55728084), so:
#     * TACTICAL: nobody else locks -> Initialize 0->1, Finalize's tail 1->0 -> WE FIRE INSIDE
#       Finalize, after the SetFinalData call at Finalize+0xa0 = 0x55727ED8 (the function itself is
#       TCombatLogbook.SetFinalData @0x55728E44) and after `finaldata[+0x30] = combat[+0x14]`
#       @0x55727F83, and before cave_towerraze's / the combat screen's DestroyCombat.
#     * FAST: cave_towerraze locks first -> 1, Initialize -> 2, Finalize's tail -> 1 (no fire),
#       cave_towerraze's explicit UnlockExecuted -> 0 -> fires there.
#   Either way combat[+0x18] (the TCombatLogbook) and both its TCombatData members are populated and
#   the combat is alive, which is the window DistributeCombatEvent requires.
#
# STAGE 12d (2026-09-12) -- the TACTICAL path files a combat report. Stage 12b fixed only the fast
# path (in cave_towerraze); a modal raze/rebellion/loot filed NOTHING for anyone. Four instructions
# plus vanilla's Synchronise wrapper, placed immediately after the razeasync one-shot clear so it
# runs for EVERY tactical outcome -- win {3,6}, decisive loss 4 AND the 2/5 standoffs that fall
# straight to Ldone -- and BEFORE the raze/garrison, whose map mutations the logbook snapshot
# (already frozen by Initialize/Finalize) does not see anyway.
#   ⚠ NO DOUBLE-FILING with Stage 12b: the block sits UNDER the `jz Ldone` razeasync gate, so the
#     fast path never reaches it, and vanilla's own tactical filer (TArmyCombatMoveTE.CombatExecuted
#     @0x557496D4, tail @0x55749904) can never run for our combat -- cave_towerraze overwrites
#     combat[+0x2C] with THIS cave. A module-wide scan finds exactly three PRE-STAGE-12d callers of
#     DistributeCombatEvent: those two vanilla sites and Stage 12b's; no other module imports it.
#   ⚠ ECX (the load delta) is push/pop-preserved rather than re-anchored: DistributeCombatEvent is
#     Delphi callee-save (`add esp,0xc; pop ebp; pop edi; pop esi; pop ebx; ret`) and clobbers only
#     EAX/ECX/EDX, and all three callees are `ret 0`, so a plain push/pop is balanced and 10 bytes
#     cheaper than a fourth anchor. assemble_pic ignores pops that are not preceded by a call to
#     their own address, so npops stays 3.
# =====================================================================================
def src_razedone(p):
    return f"""
        push esi
        push edi
        mov edi, eax                         /* EDI = tower (survives the calls) */
        mov esi, edx                         /* ESI = combat (saved before the result read clobbers EDX) */
        call Ld
    Ld:
        pop ecx
        sub ecx, 0x{p[0]:X}                  /* ecx = load delta */
        mov byte ptr [ecx+0x{FLAG_HAPPENED:X}], 1
        cmp byte ptr [ecx+0x{FLAG_RAZEASYNC:X}], 0
        jz Ldone                             /* fast path: cave_towerraze handles the raze */
        mov byte ptr [ecx+0x{FLAG_RAZEASYNC:X}], 0   /* one-shot */

        /* === (Stage 12d) COMBAT REPORT for the TACTICAL path -- vanilla's own modal shape, copied
               from TArmyCombatMoveTE.CombatExecuted's tail @0x557498F5. The Synchronise pair is
               MANDATORY here (see the constants block): this callback fires outside the raze token
               event, and DistributeCombatEvent -> TEventLogbook.AddEvent asserts GetSynchronised.
               DL = 0 = no auto-replay -- the local human just watched this battle. === */
        push ecx                             /* delta; DistributeCombatEvent clobbers EAX/ECX/EDX */
        mov eax, dword ptr [ecx+0x{MAP_GLOBAL:X}]    /* *MAP_GLOBAL (ptr) */
        mov eax, dword ptr [eax]             /* EAX = map */
        push eax                             /* keep it for SynchroniseEnd */
        call 0x{SYNCHRONISE_BEGIN:X}         /* inc map[+0x234] */
        mov eax, dword ptr [esi+0x18]        /* combat[+0x18] = TCombatLogbook */
        mov dl, 0x{EVENTLOG_SHOW_MODAL:X}    /* 0 = file for every witness, replay for nobody */
        call 0x{DISTRIBUTE_COMBAT_EVENT:X}   /* AoWE.DistributeCombatEvent @0x5572928C */
        pop eax                              /* map */
        call 0x{SYNCHRONISE_END:X}           /* dec map[+0x234] */
        pop ecx                              /* delta restored */

        movzx edx, byte ptr [esi+0x14]       /* result byte: 3/6 razer won, 4 defender win, 2/5 standoff */
        cmp edx, 3
        je Lasync_raze
        cmp edx, 6
        je Lasync_raze
        cmp edx, 4                           /* only a DECISIVE defender win garrisons */
        jne Ldone                            /* 2 (stalemate) / 5 (mutual) / else -> do nothing (tower untouched) */
        /* loss (result 4): harvest the LITERAL survivors (cave_rehome) BEFORE the garrison, while
           combatData is still valid (this callback fires pre-DestroyCombat), then SetPlayer(0) FIRST +
           Guard garrison via the shared cave_lossgarrison (cave_genraze substitutes the survivors). */
        mov eax, esi                         /* combat */
        call 0x{CAVE_REHOME:X}               /* stash survivors in FLAG_RAZESURVIVORS */
        call Ld_r
    Ld_r:
        pop ecx
        sub ecx, 0x{p[1]:X}                  /* recompute delta (cave_rehome clobbered ECX) */
        movzx edx, byte ptr [ecx+0x{FLAG_RAZEPLAYER:X}]   /* razing player */
        mov eax, edi                         /* tower */
        call 0x{CAVE_LOSSGARRISON:X}         /* EAX=tower; SetPlayer(0) + PlaceRazeDefenders(Guard) */
        jmp Ldone
    Lasync_raze:
        mov byte ptr [ecx+0x{FLAG_RAZEOK:X}], 1
        movzx edx, byte ptr [ecx+0x{FLAG_RAZEPLAYER:X}]   /* razing player */
        mov eax, edi                         /* tower */
        call 0x{CAVE_RAZEDISPATCH:X}         /* ExecuteRaze(EAX=tower, DL=player) (Stage 9: dispatched) */
        call Ld2
    Ld2:
        pop ecx
        sub ecx, 0x{p[2]:X}
        mov byte ptr [ecx+0x{FLAG_RAZEOK:X}], 0
    Ldone:
        pop edi
        pop esi
        ret
    """

# =====================================================================================
# cave_canraze  -- CanRaze entry hook. The Stage-1 razeok BYPASS (return true when razeok set)
# was REMOVED: it masked the FC90 forcefail gate whenever razeok was ever left set, which let
# no-force razes slip past. The forcefail gate now PASSES whenever the attacker has units, so the
# post-battle re-entry passes naturally (survivors are on the tile) with no bypass needed. This is
# now a bare passthrough: replay the 6 displaced prologue bytes and jump into CanRaze's body.
# razeok is still set by cave_towerraze and read by cave_skipavenger (avenger skip) -- unaffected.
# ECX(=&msg) and all params are untouched here.
# =====================================================================================
def src_canraze(p):
    return f"""
        push ebp
        mov ebp, esp
        add esp, -0x1C
        jmp 0x{CANRAZE_CONT:X}
    """

# =====================================================================================
# cave_skipavenger  (Stage 2, addition B)  -- razeok-gated skip of PlaceRazeDefenders.
# Entry (at 0x557601F0 via E8): EAX=self, ECX=[self] VMT, DL=player, EBX=self(live).
# When razeok set -> skip the second-wave avenger spawn; else replicate the vanilla vcall.
# Only ESI touched (push/pop balanced); EAX/ECX/EDX/EBX/EDI preserved; POP keeps CMP's ZF.
# =====================================================================================
def src_skipavenger(p):
    return f"""
        push esi
        call Ld
    Ld:
        pop esi
        sub esi, 0x{p[0]:X}                  /* esi = load delta */
        cmp byte ptr [esi+0x{FLAG_RAZEOK:X}], 0
        pop esi                              /* restore esi (POP does not affect ZF) */
        jnz Lskip
        call dword ptr [ecx+0x1ac]           /* replicate vanilla PlaceRazeDefenders vcall */
        ret
    Lskip:
        ret
    """


# =====================================================================================
# cave_forcefail  (Stage 2.2 req1 + AI-veto v4 + LEAK-FIX v5)  -- CanRaze gate hook @0x5575FC90.
# Mid-CanRaze: EBP frame valid, sim already ran; predictor=[ebp-0x10], self=[ebp-0x4], player=[ebp-0x5].
# v5 (2026-07-12): the v4 re-entry test (`razeok!=0 -> bypass`) LEAKED. razeok is a session-lifetime
# BSS byte set/cleared LINEARLY around the EXECUTE_RAZE calls (cave_towerraze Lraze, cave_razedone);
# if that vanilla ExecuteRaze THROWS (exception unwinds to a handler above, game continues), the
# clear is skipped and the stuck byte let the NEXT CanRaze -- any player, any structure -- bypass the
# whole human/AI/city gate. Observed in-game as sporadic AI mine/node razes under v4 (2 of 11). The
# entry-heal in cave_towerraze runs DOWNSTREAM of this gate, so it bounded the leak to one structure
# per stuck flag but could not prevent it.
# v5 fix, two parts, no new hooks:
#   (1) STRUCTURAL re-entry test: bypass iff CanRaze's RETURN ADDRESS (delta-normalized) lies in
#       [EXECUTE_RAZE 0x5575FFC8, RAZE_ENTRY 0x557602F8). The only CanRaze call sites in that range
#       are ExecuteRaze's top-gate vcall @0x5575FFF3 and RazeEx's re-check @0x5576025F (verified) --
#       exactly the post-approval re-validations that must not re-veto. retaddr-delta == link-time
#       address, so the compare is rebase-proof. A stuck flag can no longer influence this gate.
#   (2) FIRST-ENTRY HEAL: on every non-re-entry CanRaze, clear razeok BEFORE anything reads it, so a
#       THROW-stuck flag cannot linger for cave_skipavenger either (razeok stays set/cleared around
#       EXECUTE_RAZE purely for the avenger skip; this gate no longer consults it at all).
# Register use as v4: clobbers EAX/ECX/EDX (dead/arg regs at the hook), sets EBX only on the decided
# paths, ESI/EDI/EBP untouched. 2 delta anchors (GET_PLAYERS/IS_CLASS clobber ECX).
# v6 (2026-07-12, user-picked "v6 + stricter margin"): the AI NON-CITY branch is no longer an
# unconditional block -- it re-opens VANILLA'S OWN scorched-earth design with a working feasibility
# check. The regional-dominance want-gate (ValidateRazeStructure @0x557D74B4: ownPlayerStr*2 <
# hostile+neutral PLAYER str in r15, independents excluded -- fully decoded in
# AI_Raze_Decision_CodeMap.md s4/s7b) still runs UPSTREAM in RazeControl.Process, so reaching this
# gate already means "locally doomed". Here we then require the simfly'd CanRaze predictor to say the
# razer wins DECISIVELY and CHEAPLY: result byte == 4 (militia wiped; NOT 2 -- result-2 stalls are
# what sank v2) AND GetSuperiority < 50 (for result 4 that is the razer's predicted loss% -- caps
# pyrrhic attempts; pure strength proxies are what sank v3). Since razeroster, the sim fights the
# SAME seed-stable roster the real battle will manifest that day, so predicted wins convert. AI city
# path (vanilla veto) and human path (forces-present) unchanged from v4/v5.
# =====================================================================================
def src_forcefail(p):
    return f"""
        call Lff_d
    Lff_d:
        pop ecx
        sub ecx, 0x{p[0]:X}                  /* ecx = load delta */
        /* --- v5 structural re-entry test: caller inside [ExecuteRaze, Raze) = the raze-execution
               machinery re-validating a raze CanRaze#1 already approved -> forces-gate only. --- */
        mov eax, dword ptr [ebp+4]           /* CanRaze return address (runtime) */
        sub eax, ecx                         /* -> link-time-normalized */
        cmp eax, 0x{EXECUTE_RAZE:X}
        jb Lfirst
        cmp eax, 0x{RAZE_ENTRY:X}
        jb Lcount                            /* legit re-entry -> NEVER re-veto (won raze must complete) */
    Lfirst:
        /* first entry (Raze's CanRaze#1 / UI enablement): heal any THROW-stuck razeok here, BEFORE
           anything can read it -- kills the v4 leak and protects cave_skipavenger's later read. */
        mov byte ptr [ecx+0x{FLAG_RAZEOK:X}], 0
        /* --- initial raze decision: AI/computer razers get CanRaze's ORIGINAL predictor veto back
               for CITIES and a hard block for everything else; HUMAN razers keep "forces present ->
               attempt it -> the real battle decides". AI vs human = razing player's [+0xA7] (==0
               human; same field Raze @0x557602F8 uses to pick confirm-dialog vs direct RazeEx). --- */
        mov eax, dword ptr [ecx+0x{MAP_GLOBAL:X}]
        mov eax, dword ptr [eax]             /* map */
        mov eax, dword ptr [eax+0x140]       /* player list */
        movsx edx, byte ptr [ebp-0x5]        /* razing player index (CanRaze local_9) */
        call 0x{GET_PLAYERS:X}               /* -> EAX = player */
        cmp byte ptr [eax+0xA7], 0
        jne Lai                              /* [+0xA7] != 0 => AI/computer -> city-only gate */
    Lcount:
        /* HUMAN, or legit re-entry: forces-present gate (attempt any raze; battle decides) */
        mov eax, dword ptr [ebp-0x10]        /* predictor */
        mov eax, dword ptr [eax+0x{PRED_ATTACKER_SIDE:X}]   /* side-1 list = opponents (razer units) */
        mov eax, dword ptr [eax+8]           /* TList.Count */
        test eax, eax
        jz Lnoforce                          /* no attacker units -> block + reworded message */
        mov bl, 1                            /* attacker present -> CAN raze */
        jmp 0x{CANRAZE_PASS:X}               /* TEST BL,BL -> JNZ -> cleanup -> CanRaze returns true */
    Lnoforce:
        xor ebx, ebx                         /* no attacker units -> bVar1=false = cannot raze */
        jmp 0x{CANRAZE_MSG:X}                /* -> CanRaze msg block (reworded), returns false */
    Lai:
        /* AI/computer initial decision (v6). CITY -> CanRaze's ORIGINAL predictor veto (vanilla,
           preserves Scorcher hostile-city razing). NON-CITY -> scorched-earth gate: we are only here
           because ValidateRazeStructure already fired upstream ("locally doomed to another player"),
           so allow the raze IFF the sim ALSO predicts a decisive, cheap win -- result 4 (militia
           wiped; result-2 stalls sank v2) AND predicted losses < 50%% (GetSuperiority for result 4 =
           razer loss%%; strength proxies sank v3). GetPlayers clobbered the first delta, so recompute
           it for the classref (2nd anchor). Structure = CanRaze self at [ebp-0x4]. */
        call Lff_d2
    Lff_d2:
        pop ecx
        sub ecx, 0x{p[1]:X}                  /* fresh load delta */
        lea edx, [ecx+0x{TCITY_VMT:X}]       /* runtime TCity VMT base = the `is TCity` class ref (PIC) */
        mov eax, dword ptr [ebp-0x4]         /* structure (CanRaze param_1 = self) */
        call 0x{IS_CLASS:X}                  /* AL = (structure is TCity) */
        test al, al
        jnz Lcity                            /* city -> original vanilla veto */
        mov eax, dword ptr [ebp-0x10]        /* non-city: predictor */
        mov al, byte ptr [eax+0x14]          /* result byte */
        cmp al, 4
        jne Lnoforce                         /* not a predicted DECISIVE win (militia wiped) -> block */
        mov eax, dword ptr [ebp-0x10]
        call 0x{GET_SUPERIORITY:X}           /* EAX = razer's predicted loss-strength %% */
        cmp eax, 50
        jge Lnoforce                         /* pyrrhic (>=50%% losses) -> block */
        mov bl, 1
        jmp 0x{CANRAZE_PASS:X}               /* desperate + decisive + cheap -> scorched-earth raze */
    Lcity:
        mov eax, dword ptr [ebp-0x10]        /* city -> replay the 2 displaced instrs ... */
        mov al, byte ptr [eax+0x14]          /* ... predictor result byte ... */
        jmp 0x{CANRAZE_GATE_CONT:X}          /* ... and run the ORIGINAL vanilla predictor veto @0x5575FC96 */
    """

# =====================================================================================
# cave_typechosen  (Stage 3 v2, EAX=context=tower, EDX=eventlog)  -- the choice-dialog callback.
# eventlog[+0x18] holds the picked combat type (0 = cancelled). On a real pick, re-issue the raze
# turn-event exactly like RazeEx, but pack the choice into TE+0x20 = razeplayer | (choice<<4) so the
# re-run of cave_towerraze skips the dialog and fights with the chosen type. (Mirrors RazeEx
# @0x5576023C + the re-issue tail of ExploreS.Search.)
#
# 2026-07-21 BUGFIX -- in-game freeze: the human was offered a raze battle they were not part of,
# and accepting hung the game. Three defects, each fixed against VANILLA's own handler for this very
# event log, RequestCombatTypeCallBack @0x557489CC:
#  (1) DWORD-vs-BYTE. The picked type was read `mov ecx,[edx+0x18]` -- but +0x18 is a BYTE and the
#      bytes above it are live fields (+0x19 acting player, +0x1a defender, +0x1b/1c/1d x/y/l).
#      A CANCEL (type 0) with any nonzero player byte above it therefore read back NONZERO and was
#      actioned as a pick; `shl edx,4` of a value >= 0x100 leaves the low byte clear, so the
#      re-issued TE carried choice 0 = ASK -- cancelling re-raised the dialog forever, minting a
#      token event from inside an event-log callback each time (the deadlock shape the engine notes
#      warn about). Vanilla reads `mov al,[edi+0x18]` @0x557489D6. Now a byte read.
#  (2) MISSING LIVE-FLAG CHECK. Vanilla FIRST does `cmp byte [edi+0x24],0; je bail` @0x557489DC --
#      +0x24 is the request-still-active flag. This cave never checked it, so a stale or replayed
#      event log was actioned. Now checked before anything else.
#  (3) WRONG PLAYER UNDER CONCURRENCY. The razing player was taken from the global FLAG_RAZEPLAYER,
#      which cave_towerraze rewrites on EVERY entry, before the mode decision. This dialog is
#      asynchronous, so any forced-FAST AI / rebellion / loot raze landing between raising it and
#      answering it retargeted the answer to a different player -- which is how a human ended up
#      holding a dialog for someone else's raze. Simultaneous turns makes that race routine. The
#      event log already carries the acting player at +0x19 (vanilla reads it @0x55748A20), so take
#      it from there; the global is no longer consulted here and the race is gone.
# EBP is used as the scratch for that player byte (push/pop'd); vanilla's handler does the same
# @0x557489FC, and this cave has no EBP-relative locals.
# =====================================================================================
def src_typechosen(p):
    return f"""
        cmp byte ptr [edx+0x24], 0           /* request still live? (vanilla @0x557489DC) */
        jz Ltc_done
        movzx ecx, byte ptr [edx+0x18]       /* picked type as a BYTE (0 = cancelled) */
        test ecx, ecx
        jz Ltc_done
        push ebx
        push esi
        push edi
        push ebp
        movzx ebp, byte ptr [edx+0x19]       /* acting player, straight from the event log */
        mov edi, ecx                         /* edi = choice */
        mov esi, eax                         /* esi = tower (context) */
        mov eax, esi                         /* tower.CreateTE (slot 0x160) */
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x160]
        mov ebx, eax                         /* ebx = te */
        mov edx, ebx                         /* tower.SetupTE(te) (slot 0x164) */
        mov eax, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x164]
        mov dword ptr [ebx+0x18], -1         /* TE+0x18 = -1 (raze action) */
        call Ltc_d
    Ltc_d:
        pop ecx
        sub ecx, 0x{p[0]:X}                  /* ecx = load delta */
        mov eax, ebp                         /* razing player -- from the event log, NOT the global */
        mov edx, edi                         /* choice */
        shl edx, 4
        or eax, edx                          /* player | (choice<<4) */
        mov dword ptr [ebx+0x20], eax        /* TE+0x20 = packed */
        mov eax, dword ptr [ecx+0x{MAP_GLOBAL:X}]
        mov eax, dword ptr [eax]             /* map */
        mov eax, dword ptr [eax+0x{MAP_TOKENMGR_OFF:X}]   /* token manager */
        movsx edx, byte ptr [ebx+0x13]       /* TE player */
        call 0x{GET_TOKEN_CONTROL:X}         /* -> EAX = token control */
        mov edx, ebx                         /* issue the TE: tokenctrl.slot0x10(te) */
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x10]
        mov eax, ebx                         /* release our TE handle */
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x2C]
        pop ebp
        pop edi
        pop esi
        pop ebx
    Ltc_done:
        ret
    """

# =====================================================================================
# cave_lossgarrison (Stage 4/req2)  -- shared loss-path garrison. EAX=tower, DL=razing player.
# Order is load-bearing: SetPlayer(tower,0)=independent FIRST (so PlaceRazeDefenders lands the roster
# on the now-unowned tower hex instead of shunting it adjacent), THEN PlaceRazeDefenders with the
# razeguard flag set so SetupRazeDefenderAG builds a Guard AG (kind 2). Clears razeguard after.
# SET_PLAYER + the vcall preserve EBX/ESI (Delphi convention), so tower/player survive in EBX/ESI.
# Two load-delta anchors (the vcall clobbers ECX, so recompute the delta before clearing the flag).
# =====================================================================================
def src_lossgarrison(p):
    return f"""
        push ebx
        push esi
        mov ebx, eax                         /* EBX = structure (survives the calls) */
        movzx esi, dl                        /* ESI = razing player */
        call Lg
    Lg:
        pop ecx
        sub ecx, 0x{p[0]:X}                  /* ecx = load delta */
        /* (Stage 8) ownership flip FIRST (so the garrison lands on the now-unowned hex), but ONLY for
           TPlayerStructure descendants (TTeleport is unowned -- its VMT has no slot 0x1F0 at all), and
           VIRTUALLY: TAltar/TFarm/TMine/TPowerNode/TProductionPlace all OVERRIDE SetPlayer (e.g. TMine
           re-registers its income source with the new owner) -- the old static base call would flip
           the owner byte while the razer kept collecting the income. TTower resolves to the base impl
           (no override), identical to the previous static call. */
        lea edx, [ecx+0x{VMT_PLAYERSTRUCT:X}]   /* runtime TPlayerStructure VMT (PIC via delta) */
        mov eax, ebx
        call 0x{IS_CLASS:X}                  /* System._IsClass (`is` op: walks ancestors) -> AL */
        test al, al
        jz Lnoflip
        mov eax, ebx
        xor edx, edx                         /* DL = 0 = independent */
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x1F0]           /* virtual SetPlayer(0) -> per-class override runs */
    Lnoflip:
        call Lg2
    Lg2:
        pop ecx
        sub ecx, 0x{p[1]:X}                  /* recompute delta (IsClass/SetPlayer clobbered ECX) */
        mov byte ptr [ecx+0x{FLAG_RAZEGUARD:X}], 1   /* razeguard = 1 -> Guard AG + survivor substitution */
        mov eax, ebx                         /* structure */
        mov edx, esi                         /* razing player (DL) */
        mov ecx, dword ptr [eax]             /* vtable */
        call dword ptr [ecx+0x1AC]           /* PlaceRazeDefenders -> survivors/roster + Place + Guard AG */
        call Lg3
    Lg3:
        pop ecx
        sub ecx, 0x{p[2]:X}
        mov byte ptr [ecx+0x{FLAG_RAZEGUARD:X}], 0   /* razeguard = 0 (avengers elsewhere unaffected) */
        pop esi
        pop ebx
        ret
    """

# =====================================================================================
# cave_setupguard (Stage 4/req2)  -- SetupRazeDefenderAG entry hook. Replays the 9 displaced entry
# bytes (push ebx;push esi;push edi;mov ebx,ecx;mov esi,edx) then, in place of the vanilla PUSH 0xd
# (the CreateGroup kind arg = Wander), pushes 2 (Guard) IFF razeguard is set, else 0xd. Resumes at
# SETUPAG_CONT (MOV DL,5). EAX is dead across the resume (fe17 = MOV EAX,EBX), so the delta trick may
# clobber it; EBX(param_3)/ESI(param_2) are set exactly as vanilla. Stack at resume == vanilla:
# [kind][edi][esi][ebx][ret]. One load-delta anchor.
# =====================================================================================
def src_setupguard(p):
    return f"""
        push ebx
        push esi
        push edi
        mov ebx, ecx                         /* param_3 (relation/group source) */
        mov esi, edx                         /* param_2 (unit list) */
        call Ld
    Ld:
        pop eax
        sub eax, 0x{p[0]:X}                  /* eax = load delta (dead at resume) */
        cmp byte ptr [eax+0x{FLAG_RAZEGUARD:X}], 0
        jz Lwander
        push 2                               /* Guard kind */
        jmp 0x{SETUPAG_CONT:X}
    Lwander:
        push 0xd                             /* vanilla Wander kind */
        jmp 0x{SETUPAG_CONT:X}
    """

# =====================================================================================
# cave_noflee (Stage 5/walls)  -- fcExecute @0x55744268 flee-gate hook. Reached ONLY for a would-be-
# fleeing side-0 (razer) unit (phase==2 && unit[+0x18]==0 && unit[+0x20]!=0 && GetSide==0). Replays the
# displaced slot-0x64 predicate call (preserving its side effect + AL), then when FLAG_RAZENOFLEE is set
# forces AL nonzero so the following TEST AL,AL;JNZ 0x557444DF takes the NO-FLEE branch (razer stays and
# fights to a decisive result instead of withdrawing). When the flag is clear it is a perfect passthrough
# = identical to vanilla for every non-raze combat. ESI(self) read-only; AL preserved; ECX/EDX are dead
# at the 0x557444B0 rejoin (flee path re-zeros ECX at 0x557444B4; no-flee path uses neither). 1 delta anchor.
# =====================================================================================
def src_noflee(p):
    return f"""
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x64]            /* replay displaced slot-0x64 predicate (AL + side effects) */
        call Ld
    Ld:
        pop ecx
        sub ecx, 0x{p[0]:X}                  /* ecx = load delta */
        cmp byte ptr [ecx+0x{FLAG_RAZENOFLEE:X}], 0
        je Lback                             /* not razing -> vanilla AL */
        or al, 1                             /* razing -> force AL != 0 -> no flee */
    Lback:
        jmp 0x{NOFLEE_CONT:X}                /* 0x557444B0: TEST AL,AL ; JNZ 0x557444DF */
    """

# =====================================================================================
# cave_rehome (Design A)  -- EAX = combat.  Harvest the LITERAL surviving militia units (already
# damaged + XP-carrying; written LIVE to the source TUnit during combat) out of combatData into a
# fresh OFF-MAP TDefendersArmy, stashed in FLAG_RAZESURVIVORS. Faithful transplant of the verified
# re-home model ExploreS.TExplorationSite.CombatExecuted @0x557C1894 (UNCHANGED on this DLL): iterate
# combatData by the FIXED initial GetCount (SetUnit(0) does not shrink combatData), keep
# IsClass(TCombatUnit) && CONQUER-object(obj[+0x48] bit0) && alive (Stage 11: conquer-flag replaced the
# old GetPlayer==0 so PERMANENTLY-CONVERTED garrison units join the winner's garrison; Finalize stripped
# dead+attackers -> survivors only),
# and per survivor run the MANDATORY refcount order AddRef(0x28) -> SetUnit(0)(0x134) -> destArmy
# AddUnit(0xAC) -> Release(0x2C). Destination is off-map (TArmy.Create) so AddUnit cannot reject.
# Extra guards vs the model: skip dead (obj[+0x47] bit0) and null-guard the TUnit (obj[+0x4C]).
# EBX=i / ESI=destArmy / EDI=obj held across calls (Delphi callee-saved); tunit parked at [ebp-0x10].
# One load-delta anchor. Militia/destArmy LEAKED (empty after cave_genraze drains it) -- matches the
# existing per-raze militia leak (a never-faulting off-map TArmy).
# =====================================================================================
def src_rehome(p):
    return f"""
        push ebp
        mov ebp, esp
        sub esp, 0x14
        push ebx
        push esi
        push edi
        mov dword ptr [ebp-4], eax           /* combat */
        call Lrh_d
    Lrh_d:
        pop ecx
        sub ecx, 0x{p[0]:X}                   /* ecx = load delta */
        mov dword ptr [ebp-0x14], ecx         /* delta */

        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+0xC]          /* combatData = [combat+0xC] */
        mov dword ptr [ebp-8], eax

        /* fresh OFF-MAP TDefendersArmy = harvest destination */
        mov ecx, dword ptr [ebp-0x14]
        mov eax, dword ptr [ecx+0x{CLASSREF_DEF:X}]    /* *CLASSREF_DEF = TDefendersArmy VMT */
        xor ecx, ecx
        mov dl, 1
        call 0x{TARMY_CREATE:X}               /* -> EAX = destArmy (off-map) */
        mov esi, eax                          /* ESI = destArmy (callee-saved across the calls) */
        mov ecx, dword ptr [ebp-0x14]
        mov dword ptr [ecx+0x{FLAG_RAZESURVIVORS:X}], eax   /* stash survivor army */

        mov eax, dword ptr [ebp-8]
        call 0x{TCD_GETCOUNT:X}               /* N = GetCount(combatData) -- FIXED initial count */
        mov dword ptr [ebp-0xC], eax
        xor ebx, ebx                          /* i = 0 */
    Lrh_loop:
        cmp ebx, dword ptr [ebp-0xC]
        jge Lrh_done
        mov eax, dword ptr [ebp-8]
        mov edx, ebx
        call 0x{TCD_GETOBJECTS:X}             /* obj = GetObjects(combatData, i) */
        mov edi, eax                          /* EDI = obj (callee-saved) */
        test edi, edi
        jz Lrh_next
        mov eax, edi                          /* IsClass(obj, TCombatUnit)? */
        mov edx, dword ptr [ebp-0x14]
        mov edx, dword ptr [edx+0x{VMTREF_COMBATUNIT:X}]   /* EDX = TCombatUnit classref */
        call 0x{IS_CLASS:X}
        test al, al
        jz Lrh_next
        test byte ptr [edi+0x48], 1           /* (Stage 11) CONQUER object = a unit the winning side KEEPS:
                                                 the militia/rebels AND any permanently-converted (seduced/
                                                 charmed/dominated) garrison unit that changed to their side.
                                                 Replaces the old GetPlayer==0 filter, which missed converts
                                                 (their player is still the loser's at harvest time -> they
                                                 wandered off alone; ownership follows the garrison army on
                                                 placement). Same flag GetUndestroyedConquerObjects @0x55726E28
                                                 uses; excludes summons. cave_rehome only runs on the loss
                                                 path (loser side wiped), so alive conquer objects = the
                                                 winner's keepers; a reverted convert (controller died) is
                                                 back on the wiped side -> dead -> excluded just below. */
        jz Lrh_next
        test byte ptr [edi+0x47], 1           /* dead (obj[+0x47] bit0)? -> skip (belt+braces; Finalize stripped dead) */
        jnz Lrh_next
        mov ecx, dword ptr [edi+0x4C]         /* tunit = obj[+0x4C]; null-guard */
        test ecx, ecx
        jz Lrh_next
        mov dword ptr [ebp-0x10], ecx         /* park tunit (survives SetUnit(0) sever) */

        mov eax, dword ptr [ebp-0x10]         /* 1) tunit.slot0x28 (AddRef / pin) */
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x28]
        mov eax, edi                          /* 2) obj.slot0x134(0) (SetUnit(0) sever from combat obj) */
        xor edx, edx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x134]
        mov eax, esi                          /* 3) destArmy.slot0xAC (AddUnit)(destArmy, tunit) */
        mov edx, dword ptr [ebp-0x10]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0xAC]
        mov eax, dword ptr [ebp-0x10]         /* 4) tunit.slot0x2C (Release; destArmy now holds the ref) */
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x2C]
    Lrh_next:
        inc ebx
        jmp Lrh_loop
    Lrh_done:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    """

# =====================================================================================
# cave_genraze (Design A)  -- GenerateRazeDefenders ENTRY hook (@0x5575FD1C).
# Entry regs (Borland register call): EAX=param_1(self=tower), EDX=param_2(player, UNUSED by the fn),
# ECX=param_3(out-list). If FLAG_RAZEGUARD set (we are inside cave_lossgarrison's PlaceRazeDefenders)
# AND FLAG_RAZESURVIVORS!=0 (cave_rehome stashed survivors) -> SUBSTITUTE: move every unit from the
# survivor army into the out-list via TUnitList.AddUnit @0x55782F1C (which reparents = detach-from-
# survivor + add-to-out-list), clear FLAG_RAZESURVIVORS, and RET emulating GenerateRazeDefenders
# (AL=1, ret 0). The move loop recomputes the survivor GetCount(slot 0x54) each pass and always takes
# the tail (count-1); AddUnit removes the tail so it drains, AND an initial-count bound (EBX) makes an
# infinite loop impossible even if a detach ever fails. Else PASSTHROUGH: replay the 7-byte vanilla
# prologue (push ebx;push esi;push edi;push ebp;add esp,-8) and jmp 0x5575FD23 so the mid-body SEED
# hook (build_razeroster_vary.py @0x5575FD36) still runs. EBX/ESI/EDI preserved for the caller on BOTH
# paths; the passthrough leaves EAX(param_1)/ECX(param_3) exactly as entered. One load-delta anchor.
# =====================================================================================
def src_genraze(p):
    return f"""
        push eax                              /* save param_1 across the flag probe */
        call Lgr_d
    Lgr_d:
        pop eax
        sub eax, 0x{p[0]:X}                   /* eax = load delta */
        cmp byte ptr [eax+0x{FLAG_RAZEGUARD:X}], 0
        je Lgr_pass
        cmp dword ptr [eax+0x{FLAG_RAZESURVIVORS:X}], 0
        je Lgr_pass

        /* === SUBSTITUTE: drain the survivor army into the out-list (ECX=param_3) === */
        pop edx                               /* discard saved param_1 (balance the push eax); edx scratch */
        push ebx
        push esi
        push edi                              /* preserve callee-saved for the Delphi caller */
        mov edi, ecx                          /* EDI = param_3 (out-list) */
        mov esi, dword ptr [eax+0x{FLAG_RAZESURVIVORS:X}]   /* ESI = survivor army */
        mov dword ptr [eax+0x{FLAG_RAZESURVIVORS:X}], 0     /* one-shot: clear the flag */
        mov eax, esi                          /* bound = initial survivor GetCount() -> EBX */
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x54]
        mov ebx, eax
    Lgr_move:
        test ebx, ebx
        jz Lgr_moved
        mov eax, esi                          /* current count (recompute; AddUnit detaches the tail) */
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x54]
        test eax, eax
        jz Lgr_moved
        dec eax                               /* tail index = count-1 */
        mov edx, eax
        mov eax, esi
        call 0x{TUNITLIST_GETUNIT:X}          /* -> EAX = unit */
        test eax, eax
        jz Lgr_moved
        mov edx, eax                          /* unit */
        mov eax, edi                          /* out-list (param_3) */
        call 0x{TUNITLIST_ADDUNIT:X}          /* MOVE: detach from survivor army, add to out-list */
        dec ebx
        jmp Lgr_move
    Lgr_moved:
        pop edi
        pop esi
        pop ebx
        mov al, 1                             /* GenerateRazeDefenders returns AL=1 */
        ret                                   /* emulate GenerateRazeDefenders (ret 0) */

    Lgr_pass:
        pop eax                               /* restore param_1 */
        push ebx                              /* replay the 7 displaced prologue bytes ... */
        push esi
        push edi
        push ebp
        add esp, -8
        jmp 0x{GENRAZE_CONT_VA:X}             /* ... and resume the body (seed hook @0x5575FD36 intact) */
    """

# =====================================================================================
# cave_razemode (bugfix)  -- DL = razing player index -> AL = 1 iff this raze belongs to the LOCAL HUMAN
# (so the fast/manual dialog + modal tactical path may run), else 0 (AI/remote -> caller forces FAST).
# Gate = the SAME proven "this is the local human's combat" test the replay uses: map[+0xA5]==razeplayer
# && GetPlayers(razeplayer)[+0xA7]==0. Self-fetches the map via the MAP_GLOBAL load-delta (own frame).
# EBX=map / ESI=razeplayer held across GetPlayers (Delphi callee-saved). GET_PLAYERS reached by rel32.
# One delta anchor. Fixes: an AI/remote razer previously fell to the registry mode -> could present THIS
# machine's human a dialog for a battle they are not in / drop them into a modal combat with no army.
# =====================================================================================
def src_razemode(p):
    return f"""
        push ebx
        push esi
        movzx esi, dl                        /* ESI = razing player index */
        call Lrm_d
    Lrm_d:
        pop eax
        sub eax, 0x{p[0]:X}                  /* eax = load delta */
        mov eax, dword ptr [eax+0x{MAP_GLOBAL:X}]   /* *MAP_GLOBAL (ptr) */
        mov ebx, dword ptr [eax]             /* EBX = map */
        movzx eax, byte ptr [ebx+0xA5]       /* active local-human player idx */
        cmp eax, esi
        jne Lrm_no
        mov eax, dword ptr [ebx+0x140]       /* player list */
        mov edx, esi                         /* razing player idx */
        call 0x{GET_PLAYERS:X}               /* -> EAX = player */
        cmp byte ptr [eax+0xA7], 0           /* local human (not AI/remote)? */
        jne Lrm_no
        mov al, 1
        pop esi
        pop ebx
        ret
    Lrm_no:
        xor eax, eax
        pop esi
        pop ebx
        ret
    """

# ---- assemble live (Stage 2/3) caves ----
cave_towerraze = assemble_pic(src_towerraze,   CAVE_TOWERRAZE,   1)
# (Stage 12c) pad to the fixed reservation -- 12b SHRANK this cave, and process() writes only
# len(new) bytes, so without the pad the tail of the Stage-11 blob would survive on disk.
TOWERRAZE_CODE = len(cave_towerraze)
assert TOWERRAZE_CODE <= TOWERRAZE_RESV, \
    f"cave_towerraze ({TOWERRAZE_CODE}B) exceeds TOWERRAZE_RESV ({TOWERRAZE_RESV}B) -- raise the reservation" \
    " AND confirm the growth zone is still zero on disk before doing so"
cave_towerraze += bytes(TOWERRAZE_RESV - TOWERRAZE_CODE)
cave_razedone  = assemble_pic(src_razedone,    CAVE_RAZEDONE,    3)   # 3 delta anchors (rehome + ExecuteRaze each clobber ECX)
# (Stage 12d) the cave MOVED this stage, so its reservation must cover the WHOLE new home -- both to
# absorb the dead pre-Stage-10 cave_rebelchance copy at 0x5580D550 and so any future shrink cannot
# leave a tail of THIS blob behind at the new address (the 12c failure mode, at a fresh address).
RAZEDONE_CODE = len(cave_razedone)
assert RAZEDONE_CODE <= RAZEDONE_RESV, \
    f"cave_razedone ({RAZEDONE_CODE}B) exceeds RAZEDONE_RESV ({RAZEDONE_RESV}B) -- raise the reservation" \
    " AND confirm the growth zone is still zero on disk before doing so"
cave_razedone += bytes(RAZEDONE_RESV - RAZEDONE_CODE)
razedone_old_fill = bytes(RAZEDONE_OLD_RESV)          # zero-fill for the slot 12d vacates
cave_canraze   = assemble_pic(src_canraze,     CAVE_CANRAZE,     0)   # passthrough now (no delta / no razeok bypass)
# (Stage 12e) same doctrine as 12c/12d, applied to the three caves neither of them was editing.
CANRAZE_CODE = len(cave_canraze)
assert CANRAZE_CODE <= CANRAZE_RESV, \
    f"cave_canraze ({CANRAZE_CODE}B) exceeds CANRAZE_RESV ({CANRAZE_RESV}B) -- raise the reservation" \
    " AND confirm the growth zone is still zero on disk before doing so"
cave_canraze += bytes(CANRAZE_RESV - CANRAZE_CODE)
cave_skipaveng = assemble_pic(src_skipavenger, CAVE_SKIPAVENGER, 1)
SKIPAVENGER_CODE = len(cave_skipaveng)
assert SKIPAVENGER_CODE <= SKIPAVENGER_RESV, \
    f"cave_skipavenger ({SKIPAVENGER_CODE}B) exceeds SKIPAVENGER_RESV ({SKIPAVENGER_RESV}B) -- raise the" \
    " reservation AND confirm the growth zone is still zero on disk before doing so"
cave_skipaveng += bytes(SKIPAVENGER_RESV - SKIPAVENGER_CODE)
cave_forcefail = assemble_pic(src_forcefail,   CAVE_FORCEFAIL,   2)   # 2 delta anchors (MAP_GLOBAL; then TCity classref)
cave_typechosen= assemble_pic(src_typechosen,  CAVE_TYPECHOSEN,  1)
cave_lossgarr  = assemble_pic(src_lossgarrison, CAVE_LOSSGARRISON, 3)   # IsClass-gated virtual SetPlayer(0)+PlaceRazeDefenders(Guard)
cave_setupguard= assemble_pic(src_setupguard,  CAVE_SETUPGUARD,  1)     # AG kind 0xD->2 when razeguard set
cave_noflee    = assemble_pic(src_noflee,      CAVE_NOFLEE,      1)     # razer no-flee when FLAG_RAZENOFLEE set
cave_rehome    = assemble_pic(src_rehome,      CAVE_REHOME,      1)     # harvest surviving militia -> off-map TDefendersArmy
REHOME_CODE = len(cave_rehome)                                          # (Stage 12e)
assert REHOME_CODE <= REHOME_RESV, \
    f"cave_rehome ({REHOME_CODE}B) exceeds REHOME_RESV ({REHOME_RESV}B) -- raise the reservation" \
    " AND confirm the growth zone is still zero on disk before doing so"
cave_rehome += bytes(REHOME_RESV - REHOME_CODE)
cave_genraze   = assemble_pic(src_genraze,     CAVE_GENRAZE,     1)     # GenerateRazeDefenders entry: substitute survivors
cave_razemode  = assemble_pic(src_razemode,    CAVE_RAZEMODE,    1)     # AI/remote raze -> FAST (no dialog/modal)

# ---- reproduce Stage-1 cave_towerraze bytes for the upgrade "acceptable prior" ----
cave_towerraze_s1 = assemble_pic(src_towerraze_stage1, CAVE_TOWERRAZE, 1)
# (Stage 12c) pad the PRIOR to the RESERVATION, never to len(cave_towerraze). Those two coincide only
# when the cave happens to be at its high-water mark; any stage that shrinks it breaks the identity,
# and the prior must span the same on-disk bytes the writer covers or the "is this a clean Stage-1
# file?" test reads short. (Reservation, not high-water mark, because the cave has shrunk twice now --
# once before Stage 12, orphaning 12 bytes at 0x5580CD84; see the TOWERRAZE_RESV comment.)
assert len(cave_towerraze_s1) <= TOWERRAZE_RESV, \
    "Stage-1 cave_towerraze must fit the reservation"
towerraze_s1_prior = cave_towerraze_s1 + bytes(TOWERRAZE_RESV - len(cave_towerraze_s1))

# ---- cave layout asserts (stay within the verified free window) ----
assert CAVE_TOWERRAZE >= 0x5580C904, "cave_towerraze collides with simfly tail"
assert CAVE_TOWERRAZE + TOWERRAZE_RESV <= CAVE_CANRAZE, \
    f"cave_towerraze reservation ({TOWERRAZE_RESV}B) overruns cave_canraze @0x{CAVE_CANRAZE:X}"
assert CAVE_CANRAZE + CANRAZE_RESV <= CAVE_SKIPAVENGER, \
    f"cave_canraze reservation ({CANRAZE_RESV}B) overruns cave_skipavenger @0x{CAVE_SKIPAVENGER:X}"
assert CAVE_SKIPAVENGER + SKIPAVENGER_RESV <= CAVE_TYPECHOSEN, \
    f"cave_skipavenger reservation ({SKIPAVENGER_RESV}B) overruns cave_typechosen @0x{CAVE_TYPECHOSEN:X}" \
    " (cave_forcefail relocated to 0x5580D150)"
assert CAVE_TYPECHOSEN + len(cave_typechosen) <= CAVE_LOSSGARRISON, \
    f"cave_typechosen ({len(cave_typechosen)}B) overruns cave_lossgarrison"
assert CAVE_LOSSGARRISON + len(cave_lossgarr) <= CAVE_SETUPGUARD, \
    f"cave_lossgarrison ({len(cave_lossgarr)}B) overruns cave_setupguard"
assert CAVE_SETUPGUARD + len(cave_setupguard) <= CAVE_NOFLEE, \
    f"cave_setupguard ({len(cave_setupguard)}B) overruns cave_noflee"
assert CAVE_NOFLEE + len(cave_noflee) <= CAVE_REHOME, \
    f"cave_noflee ({len(cave_noflee)}B) overruns cave_rehome"
assert CAVE_REHOME + REHOME_RESV <= CAVE_GENRAZE, \
    f"cave_rehome reservation ({REHOME_RESV}B) overruns cave_genraze @0x{CAVE_GENRAZE:X}"
assert CAVE_GENRAZE + len(cave_genraze) <= CAVE_RAZEMODE, \
    f"cave_genraze ({len(cave_genraze)}B) overruns cave_razemode"
assert CAVE_RAZEMODE + len(cave_razemode) <= CAVE_FORCEFAIL, \
    f"cave_razemode ({len(cave_razemode)}B) overruns cave_forcefail"
assert CAVE_FORCEFAIL + len(cave_forcefail) <= CAVE_VALFIX_RESV, \
    (f"cave_forcefail ({len(cave_forcefail)}B) would overrun cave_valfix @0x{CAVE_VALFIX_RESV:X} "
     "(build_razeeval_timing.py) -- growing it silently destroys the razetiming fix")
assert CAVE_FORCEFAIL + len(cave_forcefail) <= CAVE_SEED_RESV, \
    f"cave_forcefail ({len(cave_forcefail)}B) overruns the reserved seed cave (razeroster_vary)"

# ---- hooks ----
canraze_hook = b"\xE9" + rel32(CANRAZE_ENTRY, CAVE_CANRAZE) + b"\x90"
assert len(canraze_hook) == len(CANRAZE_ORIG) == 6
forcefail_hook = b"\xE9" + rel32(FORCEFAIL_HOOK, CAVE_FORCEFAIL) + b"\x90"
assert len(forcefail_hook) == len(FORCEFAIL_ORIG) == 6
avenger_hook = b"\xE8" + rel32(AVENGER_HOOK, CAVE_SKIPAVENGER) + b"\x90"
assert len(avenger_hook) == len(AVENGER_ORIG) == 6
# (Stage 4/req2) SetupRazeDefenderAG entry -> cave_setupguard (E9 rel32 + 4 NOP over 9 bytes)
setupag_hook = b"\xE9" + rel32(SETUPAG_HOOK, CAVE_SETUPGUARD) + b"\x90\x90\x90\x90"
assert len(setupag_hook) == len(SETUPAG_ORIG) == 9
# (Stage 5/walls) fcExecute flee-gate -> cave_noflee (E9 rel32 + 2 NOP over 7 bytes)
noflee_hook = b"\xE9" + rel32(NOFLEE_HOOK, CAVE_NOFLEE) + b"\x90\x90"
assert len(noflee_hook) == len(NOFLEE_ORIG) == 7
# (Design A) GenerateRazeDefenders entry -> cave_genraze (E9 rel32 + 2 NOP over the 7-byte prologue)
genraze_hook = b"\xE9" + rel32(GENRAZE_HOOK, CAVE_GENRAZE) + b"\x90\x90"
assert len(genraze_hook) == len(GENRAZE_ORIG) == 7

# ==== (Stage 9) city-raze sources, assembly, hook ====
def src_razedispatch(p):
    return f"""
        push eax                              /* self (ExecuteRaze args: EAX=self, DL=player; ECX = don't-care
                                                 at every call site, same as before the dispatch) */
        push edx
        call Lrd_d
    Lrd_d:
        pop ecx
        sub ecx, 0x{p[0]:X}                   /* ecx = load delta */
        lea edx, [ecx+0x{TCITY_VMT:X}]        /* runtime TCity classref */
        mov eax, dword ptr [esp+4]            /* saved self */
        call 0x{IS_CLASS:X}
        test al, al
        pop edx                               /* (pops don't touch flags) */
        pop eax
        jnz Lrd_city
        jmp 0x{EXECUTE_RAZE:X}                /* structures: base TStructure.ExecuteRaze */
    Lrd_city:
        jmp 0x{TCITY_EXECRAZE:X}              /* cities: base + race relation -30 (vanilla wrapper) */
    """

# (Stage 12a, 2026-09-12) The razeguard branch now RETURNS WITHOUT CREATING ANY AI GROUP -- exact
# vanilla parity for city loss-garrisons, which is what makes a victorious rebel garrison BUYABLE.
# TAbstractUnit.CanJoin @0x557821AC reads the unit's group FIRST (`mov ebx,[esi+0x20]; test ebx,ebx;
# je 557821CE`) and only then calls group.Behavior() @+0xD0, refusing behaviours 2 and 3. TGuardAG =
# 2, so the Stage-4 Guard AG silently emptied TArmy.GetCanJoinSelection @0x5578FA04 and TCity.
# JoinAmount @0x557ACF98 never produced an offer. Vanilla CheckRebellion @0x557AB63E-0x557AB6A5
# (dead code behind our jmp @0x557AB632) places rebels with NO group at all -- so do we.
# ⚠ NOT kind 5 TRefugeAG: TAbstractUnit.JoinAmount @0x55782324 special-cases behaviour 5 to cost 0.
# `ret` is safe here: stack is balanced at Lcg2_guard (the `push ecx` is popped before the `jne`),
# EAX still holds self, and TStructure.PlaceRazeDefenders @0x5575FE84 ignores the result --
# `call [ebx+0x15c]` @0x5575FF5A is followed by an unconditional `mov bl,1` @0x5575FF60.
# STRUCTURES are unaffected: cave_cityguard exists only in TCity's VMT slot 0x15C; they still reach
# cave_setupguard @0x5580CF00 and keep Guard kind 2 (deliberate user request).
# RNG: zero draws either way. The vanilla city fn's SYNCED Random(8) @0x557AA38D was already skipped
# on this branch and still is; the flag-clear branch (avenger spawns) still makes it.
def src_cityguard(p):
    return f"""
        push ecx                              /* param_3 (units) -- ECX needed for the delta */
        call Lcg2_d
    Lcg2_d:
        pop ecx
        sub ecx, 0x{p[0]:X}
        cmp byte ptr [ecx+0x{FLAG_RAZEGUARD:X}], 0
        pop ecx                               /* restore param_3 (pop leaves flags intact) */
        jne Lcg2_guard
        jmp 0x{TCITY_SETUPAG_V:X}             /* vanilla city AG (keeps the 1/8 raider flavor for avengers) */
    Lcg2_guard:
        ret                                   /* (12a) NO AI group -- vanilla-parity rebels, so CanJoin passes */
    """

def src_cityseed(p):
    return f"""
        add ebp, dword ptr [eax+0x22c]        /* replay displaced: ebp += map base-seed (eax = map) */
        add ebp, dword ptr [eax+0x174]        /* += day -> city mob (raze militia + rebels) re-rolls daily */
        jmp 0x{CITYSEED_CONT:X}               /* vanilla y-add + seed store follow */
    """

# cave_findrazer(self in EAX) -> EAX = razer armyHS or 0. Faithful transcription of the footprint walk
# in TStructure.ListUnits @0x5575F37C: buffer at ebp-0x20 (InitHNWalk fills +8=counter, +0x10=x, +0x14=y);
# per hex, skip if the terrain-shape byte is <0 or the coord is out of level bounds, else GetField ->
# slot0x80(sel). ESI/EDI/EBX (self/count/level) are Borland callee-saved across the HS calls.
def src_findrazer(p):
    return f"""
        push ebp
        mov ebp, esp
        add esp, -0x20                       /* walk buffer (vanilla uses 0x20) */
        push ebx
        push esi
        push edi
        mov esi, eax                         /* esi = self */
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x54]            /* footprint hex count */
        mov edi, eax                         /* edi = count */
        mov eax, dword ptr [esi+4]
        mov ebx, dword ptr [eax+4]           /* ebx = map level */
        push 0
        movsx ecx, byte ptr [esi+0x11]       /* y */
        movsx edx, byte ptr [esi+0x10]       /* x */
        lea eax, [ebp-0x20]                  /* buffer */
        call 0x{INITHNWALK:X}               /* ret 4 (cleans the pushed 0) */
        jmp Lfr_chk
    Lfr_body:
        mov eax, dword ptr [esi+8]
        mov eax, dword ptr [eax+0x28]        /* terrain-shape list */
        mov edx, dword ptr [ebp-0x18]        /* counter */
        call 0x{GETTERRAIN:X}               /* AL < 0 -> hex not part of footprint */
        test al, al
        js Lfr_next
        mov eax, dword ptr [ebp-0x10]        /* x */
        test eax, eax
        js Lfr_next
        mov eax, dword ptr [ebp-0xC]         /* y */
        test eax, eax
        js Lfr_next
        mov eax, dword ptr [ebp-0x10]
        cmp eax, dword ptr [ebx+0xc]         /* x < level width */
        jge Lfr_next
        mov eax, dword ptr [ebp-0xC]
        cmp eax, dword ptr [ebx+0x10]        /* y < level height */
        jge Lfr_next
        mov ecx, dword ptr [ebp-0xC]         /* y */
        mov edx, dword ptr [ebp-0x10]        /* x */
        mov eax, ebx                         /* level */
        call 0x{GETFIELD:X}                 /* -> EAX = field */
        mov edx, 0x{FLAG_FIELD_SEL:X}
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x80]            /* field.slot0x80(sel) -> armyHS or 0 */
        test eax, eax
        jnz Lfr_found                        /* first army wins (EAX already the armyHS) */
    Lfr_next:
        lea eax, [ebp-0x20]
        call 0x{WALKTONEXTHN:X}
    Lfr_chk:
        mov eax, dword ptr [ebp-0x18]        /* counter */
        cmp eax, edi                         /* < count ? */
        jl Lfr_body
        xor eax, eax                         /* none found */
    Lfr_found:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    """

# cave_rebellion -- CheckRebellion's flip+spawn replacement. EDI = city (preserved from CheckRebellion's
# entry `mov edi,eax`, untouched through the log code). Fires the raze combat with the rebellion bit
# (fast), then jumps to CheckRebellion's epilogue. cave_towerraze finds the garrison (cave_findrazer,
# footprint-wide), fights it vs the rebel mob, and: garrison wins -> HELD; garrison wiped -> city flips
# independent w/ the rebel-survivor garrison; undefended -> rebels seize it. Naturally PIC.
def src_rebellion(p):
    return f"""
        movzx edx, byte ptr [edi+0x30]       /* owner player (EDI = city) */
        or edx, 0x50                         /* | fast(0x10) | rebellion(0x40) */
        mov eax, edi                         /* self = city */
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x1B0]           /* ExecuteRaze = cave_towerraze -> the rebellion battle */
        jmp 0x{REBELLION_EPILOGUE:X}
    """

# cave_rebelchance -- CheckRebellion status gate + threshold replacement (Stage 10b). EBX = civil status
# (BL), EDI = city. Maps status -> rebellion threshold, keeps the GetRazed skip, and falls into the
# vanilla Random(100) compare (@RANDOM_CHECK) with EBX = threshold. Naturally PIC.
def src_rebelchance(p):
    return f"""
        xor eax, eax                         /* threshold = 0 (Stable/Content/Cheerful/Enslaved -> none) */
        cmp bl, 0
        jne Lrc_1
        mov al, 30                           /* Unruly */
        jmp Lrc_raze
    Lrc_1:
        cmp bl, 1
        jne Lrc_5
        mov al, 20                           /* Unrest */
        jmp Lrc_raze
    Lrc_5:
        cmp bl, 5
        jne Lrc_skip                         /* not 0/1/5 -> no rebellion */
        mov al, 10                           /* Oppressed */
    Lrc_raze:
        push eax                             /* save threshold across GetRazed */
        mov eax, edi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x150]           /* GetRazed -> AL */
        test al, al
        pop eax                              /* restore threshold (pop preserves flags) */
        jnz Lrc_skip                         /* razed city -> no rebellion */
        mov ebx, eax                         /* EBX = threshold for the Random(100) compare */
        jmp 0x{RANDOM_CHECK:X}
    Lrc_skip:
        jmp 0x{REBELLION_EPILOGUE:X}
    """

# cave_lootbattle (Part C) -- hooked at TCityProductionControl.NewTurn case-5 TOP (0x557A85B9, before the
# displaced `mov eax,edi; call BeginUpdate`). EDI = the TCityProductionControl (live). Invokes the city's
# ExecuteRaze (VMT slot 0x1B0 = cave_towerraze) with arg = owner|0x90 (loot + FAST) -- the loot battle is
# FAST-ONLY (fast/manual choice was built then reverted 2026-07-13 after regressions; see the raze memory).
# cave_towerraze preserves EDI (Delphi callee). WIN (FLAG_LOOTWIN set by Lraze) -> resume NewTurn case 5
# (displaced BeginUpdate then jmp 0x557A85C0 -> loot message + size*10 gold + SetRazed = vanilla loot
# semantics). LOSS/stalemate (flag clear) -> jmp the NewTurn epilogue (no gold; the loss path already flipped
# the city independent inside cave_lossgarrison). Hooking BEFORE BeginUpdate keeps the update-lock balanced.
# Owner byte = city[+0x30] (v2 fix: v1 read slot 0x7C = map LEVEL on a structure -> 0 for surface cities ->
# the guard skipped every battle; "even weak units loot, no xp"). One delta anchor.
def src_lootbattle(p):
    return f"""
        mov eax, dword ptr [edi+0x28]        /* city (EDI = TCityProductionControl) */
        movzx ecx, byte ptr [eax+0x30]       /* owner byte city[+0x30] (NOT slot 0x7C = LEVEL on structures) */
        test ecx, ecx
        jz Llb_win                           /* independent owner (unreachable for a looting city) -> pay */
        mov edx, ecx
        or edx, 0x{LOOT_FAST:X}              /* arg = owner | 0x10 (fast) | 0x80 (loot) */
        mov ecx, dword ptr [eax]             /* city vtable (EAX = city = self) */
        call dword ptr [ecx+0x1B0]           /* cave_towerraze (loot mode, fast/synchronous) */
        call Llb_d
    Llb_d:
        pop ecx
        sub ecx, 0x{p[0]:X}                  /* ecx = module load delta */
        movzx eax, byte ptr [ecx+0x{FLAG_LOOTWIN:X}]
        test al, al
        jz Llb_loss                          /* looter lost / stalemate -> no gold, skip the whole case */
    Llb_win:
        mov eax, edi                         /* (displaced) mov eax,edi ; call BeginUpdate */
        call 0x{CITY_BEGINUPDATE:X}
        jmp 0x{NEWTURN_CASE5_RESUME:X}       /* resume NewTurn case 5 -> loot message + gold + SetRazed */
    Llb_loss:
        jmp 0x{NEWTURN_EPILOGUE:X}           /* NewTurn epilogue: no gold; balanced (hooked before BeginUpdate) */
    """

cave_razedispatch = assemble_pic(src_razedispatch, CAVE_RAZEDISPATCH, 1)
cave_cityguard    = assemble_pic(src_cityguard,    CAVE_CITYGUARD,    1)
# (Stage 12c) pad to the fixed reservation -- 12a replaced a 5-byte tail jmp with a 1-byte ret.
CITYGUARD_CODE = len(cave_cityguard)
assert CITYGUARD_CODE <= CITYGUARD_RESV, \
    f"cave_cityguard ({CITYGUARD_CODE}B) exceeds CITYGUARD_RESV ({CITYGUARD_RESV}B)"
cave_cityguard += bytes(CITYGUARD_RESV - CITYGUARD_CODE)
cave_cityseed     = assemble_pic(src_cityseed,     CAVE_CITYSEED,     0)   # eax=map live -> no load-delta
cave_findrazer    = assemble_pic(src_findrazer,    CAVE_FINDRAZER,    0)   # rel32/vtable only -> no delta
cave_rebellion    = assemble_pic(src_rebellion,    CAVE_REBELLION,    0)   # rel32/vtable only -> no delta
cave_rebelchance  = assemble_pic(src_rebelchance,  CAVE_REBELCHANCE,  0)   # rel32/vtable only -> no delta
cave_lootbattle   = assemble_pic(src_lootbattle,   CAVE_LOOTBATTLE,   1)   # (Part C) 1 delta anchor (EBX = load delta)
# (Stage 12d) fixed reservation: absorbs the 23 B tail of the pre-v2 cave_lootbattle orphaned at
# 0x5580D4E3 and puts a clean, zeroed boundary between this cave and cave_razedone's new home.
LOOTBATTLE_CODE = len(cave_lootbattle)
assert LOOTBATTLE_CODE <= LOOTBATTLE_RESV, \
    f"cave_lootbattle ({LOOTBATTLE_CODE}B) exceeds LOOTBATTLE_RESV ({LOOTBATTLE_RESV}B)"
cave_lootbattle += bytes(LOOTBATTLE_RESV - LOOTBATTLE_CODE)

# cave_citygenraze: duplicate cave_genraze's flag gate, then JUMP INTO its substitution block.
# State contract at the jump-in (matches src_genraze exactly): stack top = saved self, EAX = module
# load-delta (the delta is anchor-independent, so a different anchor computes the same value),
# ECX = out-list. The jump-in offset is computed from the ASSEMBLED cave_genraze -- the first
# instruction after the second short `je` (the substitution block's `pop edx`).
_gr = list(cs.disasm(cave_genraze, CAVE_GENRAZE))
_jes = [i for i in _gr if i.mnemonic == "je"]
GENRAZE_SUBST = _jes[1].address + _jes[1].size
assert next(i for i in _gr if i.address == GENRAZE_SUBST).mnemonic == "pop", \
    "cave_genraze substitution block moved -- update cave_citygenraze's jump-in"
def src_citygenraze(p):
    return f"""
        push eax                              /* saved self (matches cave_genraze's gate state) */
        call Lcgr_d
    Lcgr_d:
        pop eax
        sub eax, 0x{p[0]:X}                   /* eax = load delta */
        cmp byte ptr [eax+0x{FLAG_RAZEGUARD:X}], 0
        je Lcgr_van
        cmp dword ptr [eax+0x{FLAG_RAZESURVIVORS:X}], 0
        je Lcgr_van
        jmp 0x{GENRAZE_SUBST:X}               /* drain survivors into the ECX out-list (shared block) */
    Lcgr_van:
        pop eax                               /* restore self */
        jmp 0x{TCITY_GENRAZE_V:X}             /* vanilla city roster (= GenerateRebelUnits + ret 1) */
    """
cave_citygenraze = assemble_pic(src_citygenraze, CAVE_CITYGENRAZE, 1)

assert 0x5580D212 <= CAVE_RAZEDISPATCH, "Stage-9 caves collide with cave_valfix (build_razeeval_timing.py)"
assert CAVE_RAZEDISPATCH + len(cave_razedispatch) <= CAVE_CITYGENRAZE, "cave_razedispatch overruns"
assert CAVE_CITYGENRAZE + len(cave_citygenraze) <= CAVE_CITYGUARD, "cave_citygenraze overruns"
assert CAVE_CITYGUARD + CITYGUARD_RESV <= CAVE_CITYSEED, \
    f"cave_cityguard reservation ({CITYGUARD_RESV}B) overruns cave_cityseed @0x{CAVE_CITYSEED:X}"
assert CAVE_CITYSEED + len(cave_cityseed) <= CAVE_FINDRAZER, "cave_cityseed overruns cave_findrazer"
assert CAVE_FINDRAZER + len(cave_findrazer) <= CAVE_REBELLION, "cave_findrazer overruns cave_rebellion"
assert CAVE_REBELLION + len(cave_rebellion) <= RAZEDONE_OLD, "cave_rebellion overruns the vacated cave_razedone slot"
assert RAZEDONE_OLD + RAZEDONE_OLD_RESV <= CAVE_REBELCHANCE, "the vacated cave_razedone slot overruns cave_rebelchance"
assert CAVE_REBELCHANCE + len(cave_rebelchance) <= CAVE_LOOTBATTLE, "cave_rebelchance overruns cave_lootbattle"
assert CAVE_LOOTBATTLE + LOOTBATTLE_RESV <= CAVE_RAZEDONE, \
    f"cave_lootbattle reservation ({LOOTBATTLE_RESV}B) overruns relocated cave_razedone @0x{CAVE_RAZEDONE:X}"
assert CAVE_RAZEDONE + RAZEDONE_RESV <= CAVE_SEED_RESV, \
    f"cave_razedone reservation ({RAZEDONE_RESV}B) overruns the seed reserve @0x{CAVE_SEED_RESV:X}" \
    " (build_razeroster_vary.py)"
assert RAZEDONE_OLD + RAZEDONE_OLD_RESV <= CAVE_RAZEDONE or \
       CAVE_RAZEDONE + RAZEDONE_RESV <= RAZEDONE_OLD, "the zero-fill overlaps the relocated cave"

cityseed_hook = b"\xE9" + rel32(CITYSEED_HOOK, CAVE_CITYSEED) + b"\x90"
assert len(cityseed_hook) == len(CITYSEED_ORIG) == 6

# (Stage 10) rebellion hooks: NOP the garrison eviction, and redirect flip+spawn -> cave_rebellion.
evict_nop  = b"\x90" * 5
assert len(evict_nop) == len(EVICT_NOP_ORIG) == 5
flip_hook  = b"\xE9" + rel32(FLIP_HOOK, CAVE_REBELLION) + b"\x90"
assert len(flip_hook) == len(FLIP_HOOK_ORIG) == 6
rebelchance_hook = b"\xE9" + rel32(REBELCHANCE_HOOK, CAVE_REBELCHANCE) + b"\x90" * 5
assert len(rebelchance_hook) == len(REBELCHANCE_ORIG) == 10

# (Part C) NewTurn case-5 top -> cave_lootbattle (E9 rel32 + 2 NOP over the 7-byte mov+call)
newturn_loot_hook = b"\xE9" + rel32(NEWTURN_LOOT_HOOK, CAVE_LOOTBATTLE) + b"\x90\x90"
assert len(newturn_loot_hook) == len(NEWTURN_LOOT_ORIG) == 7

# ---- (req1) reword the raze "not enough forces" RT_STRING (kept at 29 chars so the RT_STRING
#      block does NOT shift; the length word before it is untouched) ----
MSG_OLD = "Your forces aren't sufficient".encode("utf-16le")       # vanilla (29 wide chars)
MSG_NEW = "Your forces aren't present   ".encode("utf-16le")       # reworded, padded to 29
assert len(MSG_OLD) == len(MSG_NEW) == 58
_d0 = open(os.path.join(GAME, "AoWEPACK.dpl"), "rb").read()
_mi = _d0.find(MSG_OLD)
if _mi < 0: _mi = _d0.find(MSG_NEW)                                  # already reworded
assert _mi >= 0, "raze message string not found"
assert _d0.find(MSG_OLD, _mi + 1) < 0 and _d0.find(MSG_NEW, _mi + 1) < 0, "raze message not unique"
MSG_VA = next(DLL_BASE + va + (_mi - raw) for va, vs, raw, rs in load_sections(bytearray(_d0))
              if raw <= _mi < raw + rs)

# ---- upgrade over an already-applied file: cave_towerraze/cave_razedone are REWRITTEN this stage,
#      so on a live Stage-1..3 file they hold PREVIOUS-stage bytes that are neither zeros, the Stage-1
#      copy, nor the new bytes. Freezing an exact src for every past stage is impractical, so accept
#      the CURRENT live bytes of a rewritten cave as a valid prior -- GATED on the razebattle VMT hook
#      already pointing at cave_towerraze (proof our code owns that reserved region, so its current
#      contents are our own earlier stage, not foreign data). Vanilla/zeros stay accepted for a clean
#      base. The live-code HOOKS keep their strict vanilla-or-applied priors (unchanged). ----
_secs0 = load_sections(bytearray(_d0)); _v2o0 = mkva2off(DLL_BASE)
def _live(va, n): o = _v2o0(_secs0, va); return bytes(_d0[o:o+n])
_VMT_APPLIED = _live(VMT_SLOT, 4) == VMT_NEW
def _own_prior(va, priors):                    # add current live bytes as a prior iff our region is applied
    if _VMT_APPLIED:
        lb = _live(va, len(priors[-1]) if priors else 0)
        if lb and lb not in priors:
            return priors + [lb]
    return priors

# ---- (Stage 12d) GROWTH-ZONE PROOF for the RELOCATED cave. _own_prior would accept whatever sits at
#      the new home purely because the VMT hook is ours, which is fine for a cave we have always
#      owned but is too loose for an address this script has never written to. So state positively
#      what is allowed to be there: zeros, our own already-applied blob, or -- on the first apply
#      only -- the dead pre-Stage-10 copy of cave_rebelchance identified in the reservations block.
#      Anything else (a future feature that moved in) aborts here rather than being silently absorbed.
_ORPHAN_RC = (0x5580D550, 0x5580D587)          # the 55 B dead cave_rebelchance copy, proved unreferenced
_newhome = _live(CAVE_RAZEDONE, RAZEDONE_RESV)
if _newhome != cave_razedone:                  # not already applied -> must be zero outside the orphan
    _resid = bytearray(_newhome)
    for _i in range(_ORPHAN_RC[0] - CAVE_RAZEDONE, _ORPHAN_RC[1] - CAVE_RAZEDONE):
        _resid[_i] = 0
    assert not any(_resid), (
        f"cave_razedone's new home {CAVE_RAZEDONE:08X}..{CAVE_RAZEDONE+RAZEDONE_RESV:08X} is NOT the"
        " verified-free window it was audited as -- non-zero bytes outside the known dead"
        f" cave_rebelchance copy at {_ORPHAN_RC[0]:08X}. Re-audit before writing.")

# ---- (Stage 12e) GROWTH-ZONE PROOF for the three caves this stage widens. Same reasoning as 12d:
#      _own_prior would accept whatever sits in the newly-covered span purely because the VMT hook is
#      ours, which is too loose for bytes this script has never written. So state positively what is
#      allowed to be there -- zeros, or (on the first apply only) the ONE identified dead orphan.
#      Anything else, including an unaudited shrink-tail of our own, aborts here instead of being
#      silently absorbed. After the apply the exemption lapses: the zone must then be entirely zero,
#      so a later re-run re-proves the orphans really are gone. ----
_ORPHANS_12E = [   # (name, cave VA, code len, reservation, orphan start, orphan end, target blob)
    ("cave_canraze",     CAVE_CANRAZE,     CANRAZE_CODE,     CANRAZE_RESV,
     0x5580CDA0, 0x5580CDAB, cave_canraze),
    ("cave_skipavenger", CAVE_SKIPAVENGER, SKIPAVENGER_CODE, SKIPAVENGER_RESV,
     0x5580CDE0, 0x5580CDFB, cave_skipaveng),
    ("cave_rehome",      CAVE_REHOME,      REHOME_CODE,      REHOME_RESV,
     0x5580D040, 0x5580D045, cave_rehome),
]
for _nm, _cva, _ccode, _cresv, _o0, _o1, _cblob in _ORPHANS_12E:
    assert _cva + _ccode <= _o0 and _o1 <= _cva + _cresv, \
        f"{_nm}: the 12e orphan {_o0:08X}..{_o1:08X} is not inside the growth zone -- re-audit"
    _gz = bytearray(_live(_cva + _ccode, _cresv - _ccode))    # the growth zone as it sits on disk
    if _live(_cva, _cresv) != _cblob:                         # not already applied -> orphan permitted
        for _i in range(_o0 - (_cva + _ccode), _o1 - (_cva + _ccode)):
            _gz[_i] = 0
    assert not any(_gz), (
        f"{_nm}'s growth zone {_cva+_ccode:08X}..{_cva+_cresv:08X} holds bytes that are neither zero"
        f" nor the audited dead orphan at {_o0:08X}..{_o1:08X} -- something moved in. Re-audit"
        " (rel32 / literal-dword / .reloc scan) before writing.")

# ---- patch table: (va, acceptable-prior(s) [bytes | list], new, desc) ----
#      cur is accepted if it equals `new` (already applied) OR any prior (vanilla / Stage-1 / live-own).
Z = lambda n: bytes(n)   # pristine zero cave prior
dll_patches = [
    (CAVE_TOWERRAZE,   _own_prior(CAVE_TOWERRAZE, [Z(len(cave_towerraze)), towerraze_s1_prior]), cave_towerraze,
        "cave_towerraze (Stage 4: real combat + result gate + log; loss->cave_lossgarrison)"),
    (CAVE_RAZEDONE,    _own_prior(CAVE_RAZEDONE, [Z(RAZEDONE_RESV)]),   cave_razedone,
        "cave_razedone (combat[+0x2C] callback; Stage 12d: relocated + tactical combat report)"),
    (RAZEDONE_OLD,     _own_prior(RAZEDONE_OLD, [Z(RAZEDONE_OLD_RESV)]), razedone_old_fill,
        "cave_razedone's vacated slot 0x5580D3D0 zero-filled (Stage 12d relocation)"),
    (CAVE_CANRAZE,     _own_prior(CAVE_CANRAZE, [Z(CANRAZE_RESV)]), cave_canraze,   # accept the manual-era towerraze tail
        "cave_canraze (razeok CanRaze-entry gate; Stage 12e: +R 0x20, absorbs the 5580CDA0 duplicate)"),
    (CAVE_SKIPAVENGER, _own_prior(CAVE_SKIPAVENGER, [Z(SKIPAVENGER_RESV)]),  cave_skipaveng,
        "cave_skipavenger (razeok-gated PlaceRazeDefenders skip; Stage 12e: +R 0x60, absorbs the old cave_forcefail)"),
    (CAVE_FORCEFAIL,   _own_prior(CAVE_FORCEFAIL, [Z(len(cave_forcefail))]),  cave_forcefail,
        "cave_forcefail (CanRaze gate v6: re-entry+heal; AI city veto / non-city scorched-earth)"),
    (CAVE_TYPECHOSEN,  _own_prior(CAVE_TYPECHOSEN, [Z(len(cave_typechosen))]), cave_typechosen,
        "cave_typechosen (choice callback; 2026-07-21 byte-read + live-flag + player-from-eventlog)"),
    (CAVE_LOSSGARRISON,_own_prior(CAVE_LOSSGARRISON, [Z(len(cave_lossgarr))]),   cave_lossgarr,
        "cave_lossgarrison (Stage 8: IsClass-gated virtual SetPlayer(0)+Guard garrison)"),
    (CAVE_SETUPGUARD,  [Z(len(cave_setupguard))], cave_setupguard,
        "cave_setupguard (Stage 4/req2: AG kind 0xD->2 when razeguard set)"),
    (CAVE_NOFLEE,      [Z(len(cave_noflee))],     cave_noflee,
        "cave_noflee (Stage 5/walls: razer no-flee when razing)"),
    (CAVE_REHOME,      _own_prior(CAVE_REHOME, [Z(REHOME_RESV)]),     cave_rehome,
        "cave_rehome (Design A: harvest militia -> off-map TDefendersArmy; Stage 12e: +R 0x100, absorbs its own 5 B tail)"),
    (CAVE_RAZEMODE,    [Z(len(cave_razemode))],   cave_razemode,
        "cave_razemode (bugfix: AI/remote raze -> FAST, no dialog/modal)"),
    (CAVE_GENRAZE,     [Z(len(cave_genraze))],    cave_genraze,
        "cave_genraze (Design A: GenerateRazeDefenders entry -> substitute survivors)"),
    (SETUPAG_HOOK,     [SETUPAG_ORIG],            setupag_hook,
        "SetupRazeDefenderAG entry -> cave_setupguard (Guard-kind gate)"),
    (NOFLEE_HOOK,      [NOFLEE_ORIG],             noflee_hook,
        "fcExecute flee-gate -> cave_noflee (razer no-withdrawal)"),
    (GENRAZE_HOOK,     [GENRAZE_ORIG],            genraze_hook,
        "GenerateRazeDefenders entry -> cave_genraze (survivor substitution)"),
    (VMT_SLOT,         [VMT_ORIG],                VMT_NEW,
        "TTower VMT slot 0x1B0 -> cave_towerraze"),
] + [
    (base + 0x1B0,     [VMT_ORIG],                VMT_NEW,
        f"{cls} VMT slot 0x1B0 -> cave_towerraze (Stage 8)")
    for cls, base in RAZE_VMT_SLOTS
] + [
    (CAVE_RAZEDISPATCH,_own_prior(CAVE_RAZEDISPATCH,[Z(len(cave_razedispatch))]), cave_razedispatch,
        "cave_razedispatch (Stage 9: win-path -> TCity wrapper (-30) or base ExecuteRaze)"),
    (CAVE_CITYGENRAZE, _own_prior(CAVE_CITYGENRAZE, [Z(len(cave_citygenraze))]),  cave_citygenraze,
        "cave_citygenraze (Stage 9: city survivor substitution, else vanilla mob)"),
    (CAVE_CITYGUARD,   _own_prior(CAVE_CITYGUARD,   [Z(len(cave_cityguard))]),    cave_cityguard,
        "cave_cityguard (Stage 9: razeguard -> Guard AG for city loss-garrisons)"),
    (CAVE_CITYSEED,    _own_prior(CAVE_CITYSEED,    [Z(len(cave_cityseed))]),     cave_cityseed,
        "cave_cityseed (Stage 9: city mob seed += day)"),
    (CAVE_FINDRAZER,   _own_prior(CAVE_FINDRAZER,   [Z(len(cave_findrazer))]),    cave_findrazer,
        "cave_findrazer (Stage 9 fix: footprint-wide razer-army lookup for multi-hex cities)"),
    (CAVE_REBELLION,   _own_prior(CAVE_REBELLION,   [Z(len(cave_rebellion))]),    cave_rebellion,
        "cave_rebellion (Stage 10: rebellion = garrison-vs-rebel-mob battle)"),
    (EVICT_NOP_HOOK,   _own_prior(EVICT_NOP_HOOK, [EVICT_NOP_ORIG]),   evict_nop,
        "CheckRebellion: NOP garrison eviction (garrison stays to defend)"),
    (FLIP_HOOK,        _own_prior(FLIP_HOOK, [FLIP_HOOK_ORIG]),        flip_hook,
        "CheckRebellion: flip+spawn -> cave_rebellion (Stage 10)"),
    (CAVE_REBELCHANCE, _own_prior(CAVE_REBELCHANCE, [Z(len(cave_rebelchance))]), cave_rebelchance,
        "cave_rebelchance (Stage 10b: rebellion chance 30/20/10/0 by status)"),
    (REBELCHANCE_HOOK, _own_prior(REBELCHANCE_HOOK, [REBELCHANCE_ORIG]), rebelchance_hook,
        "CheckRebellion: status gate/threshold -> cave_rebelchance (Stage 10b)"),
    (CAVE_LOOTBATTLE,  _own_prior(CAVE_LOOTBATTLE, [Z(LOOTBATTLE_RESV)]), cave_lootbattle,
        "cave_lootbattle (Part C: loot = looter-vs-populace battle; win->gold, loss->city flips)"),
    (NEWTURN_LOOT_HOOK, _own_prior(NEWTURN_LOOT_HOOK, [NEWTURN_LOOT_ORIG]), newturn_loot_hook,
        "TCityProductionControl.NewTurn case 5 -> cave_lootbattle (Part C: gate loot on a battle)"),
    (TCITY_VMT + 0x1B0, [struct.pack('<I', TCITY_EXECRAZE)], struct.pack('<I', CAVE_TOWERRAZE),
        "TCity VMT slot 0x1B0 -> cave_towerraze (Stage 9: city raze = real battle)"),
    (TCITY_VMT + 0x1A8, [struct.pack('<I', TCITY_GENRAZE_V)], struct.pack('<I', CAVE_CITYGENRAZE),
        "TCity VMT slot 0x1A8 -> cave_citygenraze (Stage 9)"),
    (TCITY_VMT + 0x15C, [struct.pack('<I', TCITY_SETUPAG_V)], struct.pack('<I', CAVE_CITYGUARD),
        "TCity VMT slot 0x15C -> cave_cityguard (Stage 9)"),
    (CITYSEED_HOOK,    [CITYSEED_ORIG],           cityseed_hook,
        "GenerateRebelUnits map-seed add -> cave_cityseed (Stage 9: += day; reloc-safe site)"),
    (CANRAZE_ENTRY,    _own_prior(CANRAZE_ENTRY, [CANRAZE_ORIG]), canraze_hook,   # (Part C) accept the prior-target
        "CanRaze entry -> cave_canraze"),
    (FORCEFAIL_HOOK,   _own_prior(FORCEFAIL_HOOK, [FORCEFAIL_ORIG]), forcefail_hook,
        "CanRaze gate -> cave_forcefail (block no-army tower raze)"),
    (AVENGER_HOOK,     [AVENGER_ORIG],            avenger_hook,
        "PlaceRazeDefenders vcall @0x557601F0 -> cave_skipavenger"),
    (MSG_VA,           [MSG_OLD],                 MSG_NEW,
        "raze message reworded -> \"Your forces aren't present\""),
]

# ---- disassembly review ----
for name, addr, code in (("cave_towerraze",   CAVE_TOWERRAZE,   cave_towerraze),
                         ("cave_razedone",    CAVE_RAZEDONE,    cave_razedone),
                         ("cave_canraze",     CAVE_CANRAZE,     cave_canraze),
                         ("cave_skipavenger", CAVE_SKIPAVENGER, cave_skipaveng),
                         ("cave_forcefail",   CAVE_FORCEFAIL,   cave_forcefail),
                         ("cave_typechosen",  CAVE_TYPECHOSEN,  cave_typechosen),
                         ("cave_lossgarrison",CAVE_LOSSGARRISON,cave_lossgarr),
                         ("cave_setupguard",  CAVE_SETUPGUARD,  cave_setupguard),
                         ("cave_noflee",      CAVE_NOFLEE,      cave_noflee),
                         ("cave_rehome",      CAVE_REHOME,      cave_rehome),
                         ("cave_genraze",     CAVE_GENRAZE,     cave_genraze),
                         ("cave_razemode",    CAVE_RAZEMODE,    cave_razemode),
                         ("cave_razedispatch",CAVE_RAZEDISPATCH,cave_razedispatch),
                         ("cave_citygenraze", CAVE_CITYGENRAZE, cave_citygenraze),
                         ("cave_cityguard",   CAVE_CITYGUARD,   cave_cityguard),
                         ("cave_cityseed",    CAVE_CITYSEED,    cave_cityseed),
                         ("cave_findrazer",   CAVE_FINDRAZER,   cave_findrazer),
                         ("cave_rebellion",   CAVE_REBELLION,   cave_rebellion),
                         ("cave_rebelchance", CAVE_REBELCHANCE, cave_rebelchance),
                         ("cave_lootbattle",  CAVE_LOOTBATTLE,  cave_lootbattle)):
    print(f"\n{name} @ {addr:08X}  ({len(code)} B)")
    for ins in cs.disasm(code, addr):
        print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<24} {ins.mnemonic} {ins.op_str}")
print(f"\nStage-12c reservations: cave_towerraze {TOWERRAZE_CODE} B code +{TOWERRAZE_RESV-TOWERRAZE_CODE} B pad "
      f"= {TOWERRAZE_RESV} B (ends {CAVE_TOWERRAZE+TOWERRAZE_RESV:08X}, limit {CAVE_CANRAZE:08X}); "
      f"cave_cityguard {CITYGUARD_CODE} B code +{CITYGUARD_RESV-CITYGUARD_CODE} B pad = {CITYGUARD_RESV} B "
      f"(ends {CAVE_CITYGUARD+CITYGUARD_RESV:08X}, limit {CAVE_CITYSEED:08X})")
print(f"Stage-12d reservations: cave_razedone RELOCATED {RAZEDONE_OLD:08X} -> {CAVE_RAZEDONE:08X}, "
      f"{RAZEDONE_CODE} B code +{RAZEDONE_RESV-RAZEDONE_CODE} B pad = {RAZEDONE_RESV} B "
      f"(ends {CAVE_RAZEDONE+RAZEDONE_RESV:08X}, limit {CAVE_SEED_RESV:08X} = seed reserve); "
      f"vacated slot {RAZEDONE_OLD:08X}..{RAZEDONE_OLD+RAZEDONE_OLD_RESV:08X} zero-filled; "
      f"cave_lootbattle {LOOTBATTLE_CODE} B code +{LOOTBATTLE_RESV-LOOTBATTLE_CODE} B pad "
      f"= {LOOTBATTLE_RESV} B (ends {CAVE_LOOTBATTLE+LOOTBATTLE_RESV:08X}, limit {CAVE_RAZEDONE:08X})")
print(f"Stage-12e reservations: cave_canraze {CANRAZE_CODE} B code +{CANRAZE_RESV-CANRAZE_CODE} B pad "
      f"= {CANRAZE_RESV} B (ends {CAVE_CANRAZE+CANRAZE_RESV:08X}, limit {CAVE_SKIPAVENGER:08X}); "
      f"cave_skipavenger {SKIPAVENGER_CODE} B code +{SKIPAVENGER_RESV-SKIPAVENGER_CODE} B pad "
      f"= {SKIPAVENGER_RESV} B (ends {CAVE_SKIPAVENGER+SKIPAVENGER_RESV:08X}, limit {CAVE_TYPECHOSEN:08X}); "
      f"cave_rehome {REHOME_CODE} B code +{REHOME_RESV-REHOME_CODE} B pad = {REHOME_RESV} B "
      f"(ends {CAVE_REHOME+REHOME_RESV:08X}, limit {CAVE_GENRAZE:08X}); absorbing the dead "
      f"5580CDA0 (11 B) / 5580CDE0 (27 B) / 5580D040 (5 B)")
print(f"Stage-1 cave_towerraze prior: {len(cave_towerraze_s1)} B (+{TOWERRAZE_RESV-len(cave_towerraze_s1)} B zero-pad = {TOWERRAZE_RESV} B)")
print(f"VMT slot @ {VMT_SLOT:08X}: {VMT_ORIG.hex(' ')} -> {VMT_NEW.hex(' ')}  (link-time VA; reloc rebases it; == Stage 1)")
print(f"CanRaze  @ {CANRAZE_ENTRY:08X}: {CANRAZE_ORIG.hex(' ')} -> {canraze_hook.hex(' ')}  (== Stage 1)")
print(f"Avenger  @ {AVENGER_HOOK:08X}: {AVENGER_ORIG.hex(' ')} -> {avenger_hook.hex(' ')}  (NEW Stage 2)")
print(f"SetupAG  @ {SETUPAG_HOOK:08X}: {SETUPAG_ORIG.hex(' ')} -> {setupag_hook.hex(' ')}  (NEW Stage 4/req2)")
print(f"NoFlee   @ {NOFLEE_HOOK:08X}: {NOFLEE_ORIG.hex(' ')} -> {noflee_hook.hex(' ')}  (NEW Stage 5/walls)")
print(f"GenRaze  @ {GENRAZE_HOOK:08X}: {GENRAZE_ORIG.hex(' ')} -> {genraze_hook.hex(' ')}  (NEW Design A: survivor substitution)")
for _cls, _base in RAZE_VMT_SLOTS:
    print(f"Stage8   @ {_base+0x1B0:08X}: {VMT_ORIG.hex(' ')} -> {VMT_NEW.hex(' ')}  ({_cls} slot 0x1B0 -> cave_towerraze)")

APPLY = "--apply" in sys.argv
def _accepts(prior, cur):                     # prior may be bytes or a list of acceptable priors
    return cur in prior if isinstance(prior,(list,tuple)) else cur==prior
def process(path, base, patches, backup_suffix=".pre-razedlgfix"):
    try:
        data = bytearray(open(path,"rb").read())
    except PermissionError:
        print(f"[x] {os.path.basename(path)} LOCKED (read) -- close all AoW binaries and retry"); return False
    secs = load_sections(data); va2off = mkva2off(base)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
    if all(rd(va,len(new))==new for va,_p,new,_d in patches):
        print(f"[= ] {os.path.basename(path)}: already applied (Stage 2)"); return True
    ok=True
    for va,prior,new,desc in patches:
        cur=rd(va,len(new))
        if not _accepts(prior,cur) and cur!=new:
            exp = (prior[0].hex(' ')+" (or prior)") if isinstance(prior,(list,tuple)) else prior.hex(' ')
            ok=False; print(f"[!] {va:08X} ({desc})\n     exp {exp}\n     got {cur.hex(' ')}")
    if not ok:
        print(f"[x] {os.path.basename(path)}: originals mismatch -- not written"); return False
    if not APPLY:
        print(f"[dry] {os.path.basename(path)}: originals verified (vanilla or Stage-1 prior accepted)"); return True
    # ⚠⚠ BACKUP FRESHNESS GATE (added 2026-09-12, after this exact bug fired).
    # `if not os.path.exists(bpath)` is NOT a freshness test. This script has no --undo, so its ONLY
    # re-tune path is --apply over an existing install -- at which point the file on disk is our OWN
    # previous stage. An ungated copy therefore mints a .pre-* that READS as pre-patch and CONTAINS a
    # patched image: the "a .pre-* file is not proof of anything" trap, manufactured by our own script.
    # It fired once, during the Stage-12 apply, because the backups directory had been purged and the
    # exists() short-circuit stopped hiding it; that bogus snapshot was deleted the same day.
    # Gate POSITIVELY on the ORIGINAL bytes: the TTower VMT slot still holding the vanilla
    # TStructure.ExecuteRaze VA is proof this script has never written to this file.
    # (The pristine reference for this DLL is the vanilla game root + Modding Resources/
    #  AoWEPACK_original_backup.dpl -- not anything in backups/.)
    bpath=os.path.join(BACKUP_DIR, os.path.basename(path)+backup_suffix)
    if rd(VMT_SLOT, 4) != VMT_ORIG:
        print(f"[bak] SKIPPED -- VMT {VMT_SLOT:08X} is already ours, so {os.path.basename(path)} is a"
              f"\n      PATCHED image; a snapshot of it would be a fake 'prior'. Re-tune rewrites caves in place.")
    elif os.path.exists(bpath):
        print(f"[bak] {os.path.basename(bpath)} already exists (vanilla) -- not overwritten")
    else:
        made = not os.path.isdir(BACKUP_DIR)
        os.makedirs(BACKUP_DIR, exist_ok=True)     # created ONLY when a snapshot is genuinely minted
        try: shutil.copy2(path,bpath); print(f"[bak] {bpath}")
        except PermissionError:
            if made:                               # don't leave an empty backups\ behind on a failed copy
                try: os.rmdir(BACKUP_DIR)
                except OSError: pass
            print(f"[x] {os.path.basename(path)} LOCKED (backup) -- close all AoW binaries and retry"); return False
    for va,prior,new,desc in patches:
        o=va2off(secs,va); data[o:o+len(new)]=new; print(f"[w ] {va:08X} {desc}")
    try: open(path,"wb").write(data)
    except PermissionError:
        print(f"[x] {os.path.basename(path)} LOCKED -- close all AoW binaries and retry"); return False
    return True

path = os.path.join(GAME,"AoWEPACK.dpl")
print()
ok = process(path, DLL_BASE, dll_patches)
if not APPLY:
    print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first.")
elif ok:
    print("\n[done] Applied. Revert: undo surgically by hand. A .pre-* file is a whole-file"
          "\n       snapshot, so restoring one silently destroys every feature applied after it"
          "\n       was taken -- it is not a revert path.")
else:
    print("\n[!] Not applied -- see above.")
