#!/usr/bin/env python3
r"""
AoW1 mod -- Shipyard gold income from contiguous adjacent water.

A shipyard produces 1 gold per HEXES_PER_GOLD hexes of the water body/bodies it
touches, divided between every shipyard on that body.

  pot(region)   = area(region) div HEXES_PER_GOLD   (per body, remainder discarded)
  share         = pot div N                    (N = qualifying shipyards on the body)
  income(yard)  = SUM over the distinct regions the yard touches of share

HEXES_PER_GOLD is the single balance knob (currently 5 -- one gold per 5 hexes; it was
10 until the 2026-08-26 re-tune that doubled the income). It is defined ONCE, next to
CODE_VA_BASE, and everything else derives from it: the `mov ecx, N` before the pot
divide in `entry`, every --sim expectation, and verify_cave check 8, which reads the
immediate back off the assembled bytes. Re-tuning the rate is that one line -- do not
write the number anywhere else. Note the two divides in `entry` are NOT the same knob:
the first divides by HEXES_PER_GOLD (the pot), the second by N (the shipyard count).

RULES (all user-decided; do not "improve" them in this cave):
  * a shipyard gathers from EVERY distinct water region it touches, a divided share
    from each;
  * the divisor N includes independent / unflagged (owner 0xFF) shipyards, which
    therefore dilute the pot WITHOUT collecting -- deliberate, ruled, not a bug;
  * razed shipyards are excluded; under-construction shipyards are excluded entirely
    (not in the divisor, not earning);
  * water is terrain [field+0x14] in {0x00 Water, 0x0A CaveWater} EXACTLY -- overlay
    ignored (so a bridged hex still counts), Ice(6) is NOT water, and on this install
    0x0E is SKY / 0x0B is CHASM (build_chasm_sky_movement.py), so the historical
    "water family" {0,6,0x0A,0x0E} would be catastrophically wrong;
  * regions never span map levels (the engine's HN walk record has no L field);
  * zero income shows nothing (all four vanilla display gates hide at 0) -- accepted.

================================================================================
THE HOOK -- one 4-byte data write
================================================================================
  0x557C7350   TShipyard VMT +0x1F4  GetIncome   0x557BE500 -> CAVE entry

  *** 0x557C7388 (VMT +0x22C GetBaseIncome, = 0x557C75D0 `xor eax,eax; ret`) IS NOT
      TOUCHED, AND MUST NOT BE. *** Twelve `call [reg+0x22C]` consumers change
  GAMEPLAY on a non-zero base income: AoW.exe 0x00440AD3 adds a Merchandise item to
  the shipyard's production queue, 0x0043F33F enables a production-screen control,
  TProductionPlace.GetCurrentActivityText 0x557BE8AD flips the Realm column to
  "Producing Merchandise", and TProductionPlace.ListIncomeInfo 0x557BE59C opens a
  latent nil-deref at 0x557BE643. Hooking GetIncome instead leaves every one of them
  reading 0. It also replaces TProductionPlace.GetIncome's +25%-when-idle branch
  (0x557BE523) outright, which is what makes the number stable.
  The two display surfaces this costs -- the map structure-info panel's gold row and the
  Realm window's income list -- are fixed exe-side by build_shipyard_income_display.py.
  Nothing in this script needs to change for them.

Contract of the replaced virtual: IN eax = Self, no args. OUT eax = gold (>= 0).
Preserves ebx/esi/edi/ebp/esp/DF. Terminates with a bare `ret` (never `ret n`).

================================================================================
THE CAVE
================================================================================
  0x55822000  table      0x80  the engine's OWN per-parity neighbour deltas, dumped
                               from HSEPack.dpl 0x5562E250/0x5562E290 at build time
                               and asserted byte-for-byte (never referenced across
                               DPLs by absolute address -- both modules rebase)
  entry        the GetIncome replacement + guard set + the payout sum
  ensure       two-tier cache validation, calls the builders
  regions_of   shipyard hex + its six neighbours -> up to 4 distinct region ids
  build_t1     water marking + iterative BFS labelling (expensive, once per game day)
  build_t2     walks the CACHED shipyard sub-list -> per-region shipyard counts
  harvest      the ONLY registry sweep: TStructureControl -> an array of TShipyard*,
               re-run only when GetCount moves or the tier-1 key changes

Cave zone 0x55822000..0x55822FFF (0x1000). Verified all-zero, no .reloc entries, and
unclaimed in BOTH patch trees (Inioch's tree claims nothing in 0x5582xxxx). The zone
above, 0x55823000.., is left alone.

  Neighbours BELOW, as of 2026-08-26 -- this list was already stale once, so re-derive it
  rather than trusting it: build_los_terrain.py 0x55820000..0x55820800,
  build_caster_cost.py 0x55820800..0x55820FFF, build_dispelmagic5.py 0x55821000..0x558213FF.
  "Unclaimed" is a statement about a moment in time, not a reservation.

Mutable state: BSS page slack header at 0x558FAB00 (0x78 bytes used of the 0x80
window 0x558FAB00..0x558FAB7F). BSS has no file backing (raw size 0), so nothing is
written to disk for it and it is zero at load.

  BSS NEIGHBOUR SURVEY (re-measured 2026-08-26 by grepping BOTH patch trees; the
  earlier version of this block understated Inioch's claims).
    ours (build_scripts/): 0x558FA040/44/48 are the engine's own globals, then
      0x558FA800..0x558FA870, 0x558FA900, 0x558FA940..0x558FA960, 0x558FAA00,
      0x558FAA01 (build_los_terrain, PENDING).  Highest claim below us: 0x558FAA01.
    Inioch's tree:
      0x558FA800..0x558FAA00   32 x 16 B retaliation mark table (an earlier revision
                               was 32 x 12 B ending at 0x558FA980, and its phase-2
                               scratch sat AT 0x558FA980 -- both are claimed)
      0x558FA810               weakness-ability id table (inside the above)
      0x558FA8F0               spring-of-life diagnostics (inside the above)
      0x558FAA00 (+0x20)       scratch, counter at +0x20 -> ends 0x558FAA24
      0x558FAF20..0x558FAF24   per-combat AI-spell flags + the two damage flags
      0x558FAF40               abilitydata guard recorder
      0x558FAF60 (+0x24)       diagnostic recorder, 14 dwords -> ends ~0x558FAF98
      0x558FAFA0..0x558FB000   12 x 12 B mark table, runs to the BSS page end
  So the occupied spans are 0x558FA800..0x558FAA24 and 0x558FAF20..0x558FB000, and
  our window 0x558FAB00..0x558FAB7F sits in the clear gap between them either way.

Bulk storage is the Delphi heap: ONE block, grown on demand, never freed (this keeps
alloc/free churn off the per-day path). Layout: labels[] (2 B/cell, per level),
the BFS queue, area[], count[], and the cached shipyard sub-list (MAX_YARDS dwords,
4 KB). Worst case ~1.1 MB at the 0x8000-cells-per-level ceiling; a real 127x127x3 map
is ~550 KB.

POSITION INDEPENDENCE (mandatory -- AoWEPACK.dpl never loads at its preferred base):
every block starts `push.. / call $+5 / pop ebx / sub ebx, <link-time VA>` so ebx is
the load delta, and every global is reached as [ebx + <link-time VA>]. There is not
one bare absolute memory operand in the cave; asserted at build time by scanning the
capstone listing. Every call/jmp is rel32 inside the module.

================================================================================
CACHING -- two tiers, and why the tiers are split
================================================================================
Naive recompute-per-call is catastrophic. TPlayer.UpdateIncome 0x55751F88 calls
Income() on EVERY registered source it holds (the loop 0x55751FA9-0x55751FC4,
`call [vmt+0x50]` per entry), so ONE UpdateIncome already costs Y shipyard
evaluations. Multiply that by however many UpdateIncome calls an event drives and
by the per-evaluation cost, and the shape is O(N * Y * <per-evaluation>).

  HOW BAD IS THE REGISTRATION STORM, REALLY -- measured statically 2026-08-26.
  RegisterIncomeSource 0x55752068 only calls UpdateIncome when the player's update
  lock [player+8] is zero (0x5575208B `cmp dword ptr [ebx+8],0` / `jne`), and
  TPlayer.EndUpdate 0x55751EC8 calls UpdateIncome once at +0x22 when the lock drops
  back to zero. So the question is whether map load holds that lock. IT DOES:

      TAoWHSMap.MsgProc 0x55778498, message 0x20000008 (the activate message)
        557784C1  call TPlayerList.BeginUpdate   -- +1 on EVERY player's [+8]
        55778500  call HSEngine.THSMap.MsgProc   -- dispatches the activate down to
                                                    every map object, i.e. this is
                                                    where TProductionPlace.Activate
                                                    0x557BEE9C -> RegisterIncomeSource
                                                    fires, once per structure
        55778522  call TPlayerList.EndUpdate     -- one UpdateIncome per player

  (TAoWHSMap.Activate 0x55778000 runs inside that window too, and its own
  BeginUpdate/EndUpdate pair at +0x109/+0x114 is EMPTY -- two adjacent calls with
  nothing between them, so it is a refresh trigger, not a second wrapper.)
  => the map-load registration storm collapses on its own: ONE UpdateIncome per
  player, not one per structure. The O(N*Y*S) map-load catastrophe is not real.

  It is NOT dead scope, though. A brute E8 scan of the whole CODE section (run
  against the live DLL and against Modding Resources/AoWEPACK_original_backup.dpl --
  identical six hits in both) finds SIX direct callers of TPlayer.UpdateIncome
  0x55751F88, of which THREE have no lock gate at all:

      site       enclosing function                             lock-gated?
      5574B6FD   AoWE.TDisbandUnitTE.Execute           +0x269   NO
      55751EEA   AoWE.TPlayer.EndUpdate                +0x22    n/a: this IS the
                                                                lock-release path
      55752093   AoWE.TPlayer.RegisterIncomeSource     +0x2B    yes -- 5575208B
                                                                cmp [ebx+8],0 / jne
      557520BA   AoWE.TPlayer.UnregisterIncomeSource   +0x1E    yes -- 557520B2
                                                                cmp [ebx+8],0 / jne
      557A61AB   Crops.TPlayerCropStructure.SetIncome  +0x2F    NO
      557BED10   PrdPlace.TProductionPlace.Update      +0x2C    NO

  So the ungated set is exactly {TProductionPlace.Update, TDisbandUnitTE.Execute,
  TPlayerCropStructure.SetIncome}. The tests guarding the Crops and Disband sites are
  on structure state and owner (SetIncome: 557A6180 `cmp dl,[esi+0x3c]`, 557A6191
  `cmp bl,0xFF`), never on the update lock [player+8].

  *** TProductionPlace.SetPlayer 0x557BF0BC IS NOT ONE OF THEM. *** An earlier
  version of this block named it as the second ungated direct caller. It is neither
  direct nor ungated: the bytes at 0x557BF0BC are `E8 A7 2F F9 FF` -> 0x55752068
  TPlayer.RegisterIncomeSource, which is itself gated at 0x5575208B. Recorded because
  it is a tempting re-derivation (a method called SetPlayer plainly does touch income
  registration on capture) and because designing around a gate that does not exist
  there, while missing the two real ungated drivers, is the concrete cost.

  TProductionPlace.Update remains the live one: S structures each driving one
  UpdateIncome, each sweeping Y income sources, is O(S * Y * <per-evaluation>). With
  a full registry walk per evaluation that is O(S^2 * Y). Hence the cached sub-list
  below. The tier split and the sub-list are BOTH worth having, and the corrected
  inventory strengthens that case rather than weakening it -- three ungated drivers,
  not two. Only the specific "map load performs O(S^2) Income calls" claim in the
  first version of this header was wrong, and it is deleted rather than left
  standing.

  TIER 1 (the flood fill, expensive):  key = map ptr, [map+0x174] day counter,
      [container+0x14] level count, [level0+0x14] W*H, [level0+0x2C] field-array base.
      TPlayerControl.NewDay 0x55754DCB does `inc [map+0x174]` immediately before
      TPlayerList.BeginUpdate 0x55754DDC drives the income sweep, so the day key is
      already fresh when the sweep runs. Lazy rebuild on first miss covers save-load
      and map change for free.
  TIER 2 (the count pass, cheap):  NOT KEYED AT ALL -- it runs on EVERY call.
      It used to be keyed on tier-1 key PLUS TStructureControl.GetCount, and that was
      measurably wrong. Completing construction does not move the registry count:

          5575F13F  call dword ptr [ecx + 0x14C]   TStructure.SetRazed(false)
          5575F145  mov  byte ptr [ebx + 0x24], 0xFF   builder cleared IN PLACE

      -- there is no TStructureControl call anywhere in TStructure.BuildingDone, so a
      GetCount-keyed count[] never noticed. On a body holding a complete yard A and a
      yard B that finished this turn, the next UpdateIncome paid A the WHOLE pot and B
      the whole pot -- twice the pot -- self-correcting only at the next day rollover.
      (That defect is rate-independent; it is not restated in gold here, because the
      gold figure would silently rot the next time HEXES_PER_GOLD moves.) Razing had
      the mirror-image lag (the razed yard stopped earning at once via G2, but the
      survivors' shares did not rise until the next day).
      Running the pass unconditionally makes BOTH live, because every membership byte
      ([s+0x48] razed, [s+0x24] building, [s+0x04] field) is re-read on every
      evaluation.

  THE SHIPYARD SUB-LIST (what the tier-2 pass actually walks)
      The pass stays unconditional, but it no longer walks the whole structure
      registry. A full registry step is not cheap-and-flat:

          TStructureControl.GetStructure 0x55762364
            5576236E  mov eax,ebx / call 0x55762390   GetCount, on EVERY index
            55762379  mov eax,[ebx+8] / [eax+8] / [eax+4] / [eax+esi*4]
          TStructureControl.GetCount 0x55762390
            55762390  mov eax,[eax+8] / mov edx,[eax] / call [edx+0x54]   -- virtual

      i.e. 2 indirect calls + ~10 loads per registry entry, plus the ClassID virtual
      call the filter needs. So `harvest` does that walk ONCE and caches the
      resulting TShipyard* array in the heap block; the tier-2 pass then walks Y
      entries instead of S. O(S*Y*<walk>) becomes O(S*Y*Y).

      *** THE HARVEST IS THE ONLY THING CACHED. *** Every membership byte is still
      re-read on EVERY evaluation, off the cached pointers:
          [s+0x48] razed   [s+0x24] building   [s+0x04] map field
      That is what keeps a mid-turn completion and a mid-turn razing live, which is
      the whole point of the unconditional pass. Caching the membership decision --
      or the count[] array -- would put the over-pay bug straight back.

      Invalidation, in the order the cave tests it:
        * build_t1 clears H_YVALID (and H_YN) on entry, so ANY tier-1 key move (new
          map, new day, reallocated field array) forces a re-harvest before the
          sub-list is read again. This is mandatory, not belt-and-braces: build_t1 can
          ReallocMem the heap block, which moves the array the pointers live in.
          That is not left to this sentence -- verify_cave check 7 asserts on the
          ASSEMBLED BYTES that both stores exist in build_t1 and that both execute
          BEFORE the ReallocMem call site.
        * build_t2 calls GetCount exactly once per evaluation and re-harvests if it
          differs from H_YCOUNT, BEFORE anything in the sub-list is dereferenced. A
          structure entering or leaving the registry always moves that count by
          exactly one (TStructureControl.Register 0x5576244C does one list Add,
          Unregister 0x557624F8 one Remove), so any SINGLE lifecycle event landing
          between two evaluations is caught.

          RESIDUAL -- THE SAME-COUNT SWAP. GetCount is a witness, not a lock: it is
          only OBSERVED between evaluations. A Deactivate+Activate PAIR falling inside
          one evaluation-to-evaluation gap leaves GetCount unchanged and a freed
          pointer live in yards[]. Do NOT restore the sentence this replaced ("a
          cached pointer can never outlive its registry entry") -- that is an absolute
          this mechanism does not deliver. The tier-1 key is not a second net for it
          either: a same-day swap moves no tier-1 key term (map ptr, [map+0x174],
          [container+0x14], [level0+0x14], [level0+0x2C]), so tier 1 nets only the
          heap-move case.
          How tight the window is: TStructureControl has exactly two mutators, each
          with exactly ONE direct caller in the whole CODE section --
          TStructure.Activate +0x17 (0x5575F6D7) -> Register and
          TStructure.Deactivate +0x10 (0x5575F720) -> Unregister -- each moving the
          count by one. So a swap needs precisely one of each inside one gap, and no
          lifecycle event occurs at all within a single UpdateIncome sweep.
          Blast radius if it ever does fire: READS ONLY. A cached pointer is used for
          [s+0x48], [s+0x24] and [s+0x04] in build_t2 and then [field+0x10/0x11/0x12]
          in regions_of; nothing in this cave writes through one. Worst case is an
          access violation (the one-shot Delphi dialog described under GUARDS) or a
          wrong divisor for one evaluation. Never a stray write, never heap
          corruption.
          THIS IS A THEORY, NOT A MEASURED BUG. No code path has been shown to perform
          a Deactivate+Activate pair between two consecutive GetIncome calls; it is
          recorded so the next session starts from a bounded statement instead of
          re-deriving the absolute. Closing it properly would mean a generation
          counter bumped by both mutators, which is a hook this round does not own.
        * the list is capped at MAX_YARDS entries; on overflow the harvest stops
          scanning and caches the truncated list (documented degradation, not a
          crash). 1024 shipyards on one map is not reachable in practice.
        * a negative GetCount aborts the pass outright.

      Cost per evaluation: 1 GetCount (2 indirect calls) + O(Y) pointer loads +
      O(Y*7) neighbour reads, NO registry walk and NO flood. The registry walk only
      happens on a registry-size change.

  *** GetCount -- OR ANYTHING ELSE THAT MOVES PER STRUCTURE -- MUST NEVER ENTER THE
  TIER-1 KEY. *** The structure registry grows one entry at a time during map load
  and shifts whenever a structure is created or destroyed in play; a label cache
  keyed on it would run a full flood pass per registry change -- the O(S * flood)
  catastrophe the tier split exists to avoid. Only TIER 2 and the harvest may be
  eager; tier 1 stays keyed on exactly (map ptr, [map+0x174], [container+0x14],
  [level0+0x14], [level0+0x2C]).

  This is NOT enforced by this paragraph. It is enforced twice, mechanically:
    * `--sim` runs a MAP-LOAD STORM scenario (run_sim, `def storm`) that grows the
      yard list one registration at a time, evaluates every yard after each one, and
      asserts t1_runs == 1 across all 21 evaluations. The completion and razing
      scenarios CANNOT catch this regression -- they hold the yard list fixed and
      only flip membership bytes, so GetCount never moves and a per-structure key
      term never fires. QA demonstrated exactly that on 2026-08-26: a subclass with
      `len(self.yards)` in the tier-1 key passed all 35 of the old checks.
      `--sim` therefore also runs the storm against that exact regressed subclass
      (`_RegressedEngine`) and asserts it FAILS -- a guard nobody has watched fail is
      not a guard.
    * verify_cave asserts on the ASSEMBLED BYTES that GETCOUNT 0x55762390 is called
      zero times inside `ensure` and exactly once inside `build_t2` (and nowhere
      else in the cave), and that GETSTRUCT 0x55762364 appears only in `harvest`.
      Prose in a docstring stops nobody; a build-time abort does.
      (These count DECODED DIRECT-CALL TARGETS, not source strings, which is the
      right technique and stronger than a text match -- but it means an indirect call
      such as `mov edi, 0x55762390 / call edi` would pass unseen. There is none in
      this cave and none is wanted; the limit is recorded so nobody mistakes the
      assertion for a total ban on reaching those routines.)
    * verify_cave check 7 asserts, again on the assembled bytes, that build_t1 zeroes
      BOTH H_YVALID and H_YN and that both stores precede the single ReallocMem call
      site. That ordering is the use-after-free guard for the cached sub-list.

[level0+0x2C] is a deliberate strengthening beyond the spec's four key terms: the
field array is reallocated by TMapLevel.CreateMapFieldList on every new map / map
load, so it catches "File > New Map in AoWDevEd reuses the same map pointer with day 0
and identical dimensions". It cannot introduce an MP divergence -- it only makes
invalidation MORE eager, and only at map (re)creation, which every peer performs.

================================================================================
GUARDS -- every one returns `xor eax,eax; ret`, which is exactly vanilla
================================================================================
G1  self nil                       G9   level count < 1 or > 3
G2  [self+0x48] == 1  razed        G10  registry [map+0x100] nil
G3  [self+0x24] != 0xFF  building  G11  per level: level nil, [+0x2C] nil, [+0x28] < 4,
G4  [self+0x30] == 0xFF  unowned        W < 1, H < 1, W*H > 0x8000, [+0x14] != W*H
      (PAYEE ONLY -- see below)         -> that level is treated as EMPTY, the pass
G5  [self+0x04] == 0  no map field      is NOT aborted
G6  busy latch                     G12  movsx L, reject L < 0 or L >= nlevels
G7  map global 0x558FA040 nil      G13  movsx x/y, four-test clamp
G8  container [map+0x10] nil       G14  every neighbour clamped before any index
                                   G15  count[r] == 0 -> skip that region
                                   G16  ReallocMem nil -> cache "built and empty"
                                   G17  sub-list: GetCount < 0 aborts the pass;
                                        H_YVALID == 0 or GetCount != H_YCOUNT forces
                                        a re-harvest BEFORE any cached pointer is
                                        read; a nil entry is skipped; the harvest
                                        stops at MAX_YARDS

  *** THE TWO MEMBERSHIP TESTS ARE DIFFERENT AND CONFLATING THEM IS THE PREDICTED BUG.
      divisor  = [s+0x48] != 1  &&  [s+0x24] == 0xFF                  (NO +0x30 test)
      payee    = that, PLUS [s+0x30] != 0xFF
  An unowned shipyard is never registered as an income source (TProductionPlace.Activate
  gates at 0x557BEEB1 on `cmp byte [ebx+0x30],0xFF`), so it dilutes and collects
  nothing. Ruled behaviour.

  *** DO NOT copy PrdPlace.TProductionPlace.GetPower's ownership idiom. *** Its gate is
  `cmp byte [ebx+0x30],0; jle` -- a SIGNED test that also excludes player 0. Ours is
  `cmp byte [.. +0x30],0xFF; je`, the idiom TProductionPlace.Activate uses.

Reentrancy: `ensure` sets busy=1 around the builders and clears it at the end. If an
exception ever escapes a BUILDER, busy latches at 1 and every SUBSEQUENT call returns 0
-- permanent, silent degradation to vanilla, which is the intended steady state.

  *** THE BUSY LATCH DOES NOT COVER THE WHOLE CAVE. *** busy is set only inside
  `ensure`, and only around the two builder calls (build_t1 and build_t2, the latter
  of which now also owns `harvest`). Everything else runs OUTSIDE the busy window:
  `entry`'s guard set, `entry`'s own `regions_of` call (which is made AFTER `ensure`
  has returned and cleared busy), and the payout loop. An exception escaping THERE
  would not latch anything -- the dialog would come back on every subsequent
  evaluation, not once. Only a builder escape degrades to quiet vanilla.
  `regions_of` is the same code either way, so in practice a fault inside it during
  `entry` would already have faulted inside build_t2 a moment earlier and latched;
  but the latch is not what makes that true, and this block used to imply it was.

  *** The FIRST escape is NOT silent. *** Nothing in this cave installs an SEH frame,
  so that first exception propagates out of GetIncome through
  TPlayerStructureIncomeSource.Income 0x55761AF8 --

      55761AF8  mov  eax, dword ptr [eax + 8]
      55761AFB  mov  edx, dword ptr [eax]
      55761AFD  call dword ptr [edx + 0x1f4]
      55761B03  ret

  -- and into TPlayer.UpdateIncome: four instructions, no SEH frame, no `ret n`, so
  nothing on that path catches or rewrites the exception. The user sees a Delphi
  exception dialog mid-turn, once, and quiet-vanilla behaviour from then on. Do not
  describe this as graceful. Wrapping the builders in an SEH frame would make it
  graceful; that is deliberately not done here (it is scope this round does not own).

  Related: System.@ReallocMem RAISES EOutOfMemory rather than returning nil, so the
  t1_nomem path is largely unreachable in practice -- an allocation failure takes the
  dialog route above. G16/t1_nomem is kept as a belt-and-braces guard for a nil that
  arrives by some other route (e.g. a zero-byte request), not as the expected OOM path.

================================================================================
CORRECTION TO THE SPEC -- x/y come from the MAP FIELD, not from the structure
================================================================================
The spec's G13 said `movsx [s+0x10] / [s+0x11]`. Measured this session, that is WRONG:
TStructure descends from HSEngine.TMapObject, whose own accessors read the coordinates
out of the map field, not out of the object --

  TMapObject.GetXhx 0x556094CC   ...  mov eax,[ebx+4] / mov al,[eax+0x10]
  TMapObject.GetYhx 0x55609538   ...  mov eax,[ebx+4] / mov al,[eax+0x11]
  TMapObject.GetLhx 0x556095A4   ...  mov eax,[ebx+4] / mov al,[eax+0x12]

TMapObject's own +0x04 is the field and +0x08 is the resource id (TMapObject.ReadWrite
0x5560987E streams `lea edx,[ebx+8]`); +0x10 belongs to a descendant and is not x.
TMapLevel.CreateMapFieldList 0x55608853-0x55608862 is the positive proof for the field
side: it writes x -> [field+0x10], y -> [field+0x11], L -> [field+0x12] as it builds the
array. So this cave reads all three from [s+0x04], keeps the four-test clamp, and is
self-consistent (L and x/y come from one source).

================================================================================
THE FIELD ARRAY IS CONTIGUOUS -- no GetField calls anywhere in this cave
================================================================================
TMapLevel.CreateMapFieldList 0x556087CC allocates [level+0x2C] as one GetMem block of
[level+0x30] bytes and fills it outer-y / inner-x with a constant stride [level+0x28]
(= TMapField.InstanceSize, read at RUNTIME, never assumed):

    field(x, y) = [level+0x2C] + (y * W + x) * [level+0x28]

so the water sweep is a linear stride walk and the BFS indexes an array. This also
sidesteps TMapLevel.GetField 0x556087B8, which has NO bounds check.

================================================================================
RECORDED FAILED APPROACHES -- DO NOT RE-TRY
================================================================================
1. ANY terrain-changed notification as the cache-invalidation trigger.
   build_los_terrain v1 repointed TAoWHSMap VMT+0x94 (TriggerTerrainChangedEvent
   0x557724EC) and got unbounded recursion: MapChanged 0x55772538 calls the slot,
   InvalidateMap 0x557725C0 calls MapChanged per level, and UpdateVisibility ends in
   InvalidateMap. It FROZE THE EDITOR ON MAP OPEN. AoWEPACK has NO terrain-change-only
   notification -- the byte writer lives in HSEPack. The day-keyed cache IS the
   invalidation mechanism. Full stop.
2. Hooking GetBaseIncome (+0x22C) -- see the header block above. Not even as a "flat 1
   sentinel".
3. HSEngine.LocationsConnected 0x5560E754 as the fill. Its marker at 0x5560E6B0 is
   DIRECTLY RECURSIVE with depth = component size, and its inner loop rescans a
   TXYLList through the linear TXYLList.IndexOf. Quadratic AND a stack overflow.
   Algorithmic template only.
4. Recursion of any kind. Explicit heap queue, always.
5. TFloodControl.Setup 0x557F1384's bounds strategy -- latent OOB read on the last row.
   Only its heap-side-array pattern was borrowed.
6. Byte-copying TStructureAIPA.Activate 0x55762594's registry walk -- it uses absolute
   `mov eax,[0x558FA040]` loads and is NOT position-independent. Its *shape* is copied,
   its bytes are not.
7. The water family {0, 6, 0x0A, 0x0E}. See the rules block.
8. A NewDay hook at 0x55754DCB. Buys nothing over the lazy rebuild and adds displaced-
   byte risk inside an SEH frame.
9. `[s+0x30] <= 0` as "owned" (signed; excludes player 0).
10. Restoring a .pre-* backup as the revert path. --undo is surgical.

================================================================================
FOUR UNDOCUMENTED LIVE-vs-VANILLA EDITS IN/NEAR THIS UNIT
================================================================================
No build script and no doc owns any of them, so this script verifies against the LIVE
file and asserts they are present (a vanilla-based verify would abort):

  0x557C7605   live 0A (10)  vanilla 19 (25)   shipyard rebuild cost, gold
  0x557C7609   live 01       vanilla 02        shipyard rebuild time, turns
  0x557C774A   live 14 (20)  vanilla 32 (50)   shipyard build cost
  0x557BE4CC   live 90 90 6B C0 06 83 C0 06    vanilla 74 08 8D 04 80 83 C0 0A
               (PrdPlace.TProductionPlace.GetPower)

--------------------------------------------------------------------------------
Dry-run by default. --apply (rewrites its caves IN PLACE, never needs a revert),
--undo (surgical: restores the slot and zeroes exactly this build's emitted length
from 0x55822000, touching no backup), --dis (full capstone listing), --sim
(pure-Python reference of the whole rule over synthetic maps). Backup
AoWEPACK.dpl.pre-shipyardincome is minted ONLY from a positively-verified original
state.

  *** THIS SCRIPT OWNS THE WHOLE 0x55822000..0x55822FFF RESERVATION. *** --apply
  writes all 0x1000 bytes (payload + zero fill), so there is no such thing as a
  co-tenant in the unused tail -- do not claim, in code comments or messages, that
  anything protects one. --undo writes back only the emitted length purely because
  that is the smallest write that is provably correct, not because it is sharing the
  zone. If the zone ever does need to be shared, CAVE_LIMIT must shrink to the
  emitted length first and the apply path must stop zero-filling.
"""

import os
import sys
import shutil
import struct
import argparse
import subprocess

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL = os.path.join(GAME, "AoWEPACK.dpl")
HSE = os.path.join(GAME, "HSEPack.dpl")
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: never the game root
BAK = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-shipyardincome")

CODE_VA_BASE = 0x55700C00       # AoWEPACK CODE: file off = VA - this  (PER SECTION!)

# ---- THE BALANCE KNOB -----------------------------------------------------
# Hexes of water per 1 gold of pot:  pot(region) = area(region) div HEXES_PER_GOLD.
# This is THE ONLY place the rate is written down. It drives
#   * the `mov ecx, N` immediately before the first `div ecx` in `entry`
#     (0x55822106 in the 2026-08-26 layout -- the pot divide, NOT the divide by the
#     shipyard count that follows it at the second `div ecx`),
#   * sim_pot() and therefore every --sim expectation, and
#   * verify_cave check 8, which reads the immediate back off the ASSEMBLED BYTES and
#     aborts if the cave and this constant have drifted apart.
# Re-tuning the rate is this one line. Do NOT restate the number anywhere else --
# not in a check() `want`, not in a comment that says "-> pot 10". Derive it.
#   2026-08-26: 10 -> 5 (income doubled, user-requested balance re-tune).
# Below 1 the cave would divide by zero; the assertion is right here.
HEXES_PER_GOLD = 5
assert HEXES_PER_GOLD >= 1, "HEXES_PER_GOLD < 1 would make `div ecx` fault"

# ---- the hook -------------------------------------------------------------
VMT_GETINCOME = 0x557C7350      # TShipyard VMT +0x1F4
VMT_ORIG      = 0x557BE500      # TProductionPlace.GetIncome

# slots that must NOT move -- asserted on every run
UNTOUCHED = [
    (0x557C7388, 0x557C75D0, "VMT+0x22C GetBaseIncome (the zero stub)"),
    (0x557C7310, 0x557BE828, "VMT+0x1B4 GetCurrentActivityText"),
    (0x557C7398, 0x557BE59C, "VMT+0x23C ListIncomeInfo"),
]

# ---- cave / state ---------------------------------------------------------
CAVE_VA    = 0x55822000
CAVE_LIMIT = 0x1000             # the reservation, owned ENTIRELY by this script:
                                # --apply writes all 0x1000 (payload + zero fill).
                                # --undo writes back only the emitted length because
                                # that is the smallest provably-correct write, NOT
                                # because the tail is shared with anyone.
TABLE_VA   = CAVE_VA            # 0x80 bytes of neighbour deltas

# MAX_LEVELS is the ONE place the level ceiling lives. It must track the engine's
# own cap byte at TAoWHSMap.AddMapLevel 0x5577768E, which build_maplevel4.py raised
# from 3 to 4 on 2026-09-06 to make room for the Sky level (index 3). Everything
# below derives from it: the three per-level arrays in the BSS header AND the four
# `cmp edx, MAX_LEVELS` loop/guard bounds in the cave (entry's sanity check, and
# build_t1's dim / mark / bfs loops). Do not write the number anywhere else --
# a header that is 4 slots wide while a loop still stops at 3 silently drops the
# Sky level's water from every region.
MAX_LEVELS = 4

HDR = 0x558FAB00                # BSS page slack, 0x80-byte window
H_MAP      = HDR + 0x00         # cached map ptr (0 => cache invalid)
H_DAY      = HDR + 0x04         # cached [map+0x174]
H_NLEV     = HDR + 0x08         # cached [container+0x14]
H_L0CNT    = HDR + 0x0C         # cached [level0+0x14]
H_L0BASE   = HDR + 0x10         # cached [level0+0x2C]
# NOTE: there is deliberately NO tier-2 key field. The count pass is unconditional --
# see the CACHING block. A GetCount cache field here is what made a mid-turn
# construction completion over-pay for one turn; do not reintroduce one.
H_BUSY     = HDR + 0x14
H_NLEVELS  = HDR + 0x18         # levels actually usable (0 after an alloc failure)
H_HEAP     = HDR + 0x1C
H_CAP      = HDR + 0x20
# ---- three [MAX_LEVELS] dword arrays; every field after them shifts with the
#      ceiling, which is why they are derived and not spelled out.
H_LABOFF   = HDR + 0x24                    # [MAX_LEVELS] heap byte offsets
H_W        = H_LABOFF + 4 * MAX_LEVELS     # [MAX_LEVELS]
H_H        = H_W      + 4 * MAX_LEVELS     # [MAX_LEVELS]
H_QOFF     = H_H      + 4 * MAX_LEVELS
H_AOFF     = H_QOFF + 0x04
H_COFF     = H_QOFF + 0x08
H_NREG     = H_QOFF + 0x0C      # highest region id assigned
H_NRSLOTS  = H_QOFF + 0x10      # slot count of area[]/count[]
# ---- the cached shipyard sub-list (see THE SHIPYARD SUB-LIST above) -------
# Only the HARVEST is cached -- never a membership decision, never count[].
H_YOFF     = H_QOFF + 0x14      # byte offset into the heap block of yards[]
H_YN       = H_QOFF + 0x18      # entries actually cached, 0..MAX_YARDS
H_YCOUNT   = H_QOFF + 0x1C      # TStructureControl.GetCount at the last harvest
H_YVALID   = H_QOFF + 0x20      # 1 = yards[] is usable; build_t1 clears it
HDR_END    = H_QOFF + 0x24
HDR_WINDOW = 0x80

# ---- engine entry points (all live-verified this session) -----------------
MAPGLOBAL = 0x558FA040          # AoWE.AoWHSMap
GETLVL    = 0x557020EC          # thunk -> HSEngine.TMapContainer.GetMapLevel
                                #   eax=container edx=index -> eax=level.  NO bounds
                                #   check (mov eax,[eax+8]/[eax+4]/[eax+edx*4]) and it
                                #   clobbers ONLY eax.
GETCOUNT  = 0x55762390          # TStructureControl.GetCount    eax=registry -> eax=n
GETSTRUCT = 0x55762364          # TStructureControl.GetStructure eax=registry edx=i
                                #   -> eax=obj (bounds-checked, nil out of range)
REALLOC   = 0x55701018          # thunk -> System.@ReallocMem   eax=&ptr edx=bytes
FILLCHAR  = 0x55701078          # thunk -> System.@FillChar     eax=ptr edx=n cl=value

CLASSID_SHIPYARD = 0x000204BE   # TShipyard.ClassID 0x557C75C8, unique, no subclasses

# ---- structure / level / field offsets ------------------------------------
S_FIELD = 0x04                  # TMapObject.Owner: the TMapField*
S_BUILD = 0x24                  # builder byte; 0xFF = not building (GetBuilding 0x5575F008)
S_OWNER = 0x30                  # owner byte;   0xFF = unowned
S_RAZED = 0x48                  # razed flag;   1 = razed (GetRazed 0x557BE558)
F_X, F_Y, F_L, F_TERR = 0x10, 0x11, 0x12, 0x14
L_W, L_H, L_COUNT, L_STRIDE, L_FIELDS = 0x0C, 0x10, 0x14, 0x28, 0x2C
MAP_CONTAINER, MAP_REGISTRY, MAP_DAY = 0x10, 0x100, 0x174
CONT_NLEV = 0x14

MAX_CELLS_PER_LEVEL = 0x8000    # G11 sanity ceiling (127*127 = 16129)
MAX_REGION_ID = 0xFFFE          # 0xFFFF is the "water, unlabelled" marker
MAX_YARDS = 1024                # cap on the cached shipyard sub-list (4 KB of heap).
                                # On overflow the harvest stops and caches the
                                # truncated list -- degradation, not a crash.

WATER = (0x00, 0x0A)            # EXACTLY these. Not 6 (Ice), not 0x0E (SKY here).

# ---- the game's own ring-walk neighbour deltas ----------------------------
# HSEPack.dpl 0x5562E250 (even x) / 0x5562E290 (odd x); parity = x & 1.
# Layout mirrors the engine: parity*0x40 + side*8 -> (dx dword, dy dword).
# Slots 6 and 7 are (0,0) pads -- slot 6 is reused here as "the shipyard's own hex",
# which is what makes "adjacent" and "connected" structurally unable to disagree.
DELTA_EVEN_VA = 0x5562E250
DELTA_ODD_VA  = 0x5562E290
DELTAS_EVEN = [(1, 0), (0, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (0, 0), (0, 0)]
DELTAS_ODD  = [(1, 1), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, 0), (0, 0), (0, 0)]

# ---- the four undocumented live edits (verify against LIVE, never vanilla) -
LIVE_EDITS = [
    (0x557C7605, bytes([0x0A]), bytes([0x19]), "shipyard rebuild cost 25->10 gold"),
    (0x557C7609, bytes([0x01]), bytes([0x02]), "shipyard rebuild time 2->1 turns"),
    (0x557C774A, bytes([0x14]), bytes([0x32]), "shipyard build cost 50->20"),
    (0x557BE4CC, bytes.fromhex("90906BC00683C006"),
                 bytes.fromhex("74088D048083C00A"), "TProductionPlace.GetPower"),
]


# ============================================================================
# PE plumbing
# ============================================================================
def pe_sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    sec0 = pe + 24 + opt
    out = []
    for i in range(nsec):
        s = sec0 + i * 40
        name = data[s:s + 8].rstrip(b"\0").decode(errors="replace")
        vsize, vaddr, sraw, praw = struct.unpack_from("<IIII", data, s + 8)
        out.append((name, vaddr, vsize, praw, sraw))
    return base, out


def va_to_off(data, va):
    """Resolve VA -> file offset THROUGH THE SECTION TABLE. Never a flat delta:
    in AoWEPACK.dpl CODE is off+0x55700C00 but DATA is off+0x55701200."""
    base, secs = pe_sections(data)
    rva = va - base
    for name, vaddr, vsize, praw, sraw in secs:
        if vaddr <= rva < vaddr + max(vsize, sraw):
            d = rva - vaddr
            if d >= sraw:
                return None                     # BSS / beyond raw data
            return praw + d
    return None


def off(va):
    """AoWEPACK CODE section only -- every VA this script writes to lives there."""
    assert 0x55701000 <= va < 0x558E7918, "VA 0x%08X is not in CODE" % va
    return va - CODE_VA_BASE


# ============================================================================
# build the cave
# ============================================================================
def dump_deltas():
    """Re-dump the engine's neighbour tables from HSEPack.dpl and assert our copy
    matches byte-for-byte. The cave embeds the copy; it never references HSEPack by
    absolute address (both DPLs rebase independently)."""
    if not os.path.isfile(HSE):
        sys.exit("ERROR: not found: %s" % HSE)
    h = open(HSE, "rb").read()
    tab = bytearray(0x80)
    for p, dl in ((0, DELTAS_EVEN), (1, DELTAS_ODD)):
        for s, (dx, dy) in enumerate(dl):
            struct.pack_into("<ii", tab, p * 0x40 + s * 8, dx, dy)
    for p, va in ((0, DELTA_EVEN_VA), (1, DELTA_ODD_VA)):
        o = va_to_off(h, va)
        if o is None:
            sys.exit("ABORT: cannot resolve HSEPack VA 0x%08X" % va)
        live = h[o:o + 0x40]
        ours = bytes(tab[p * 0x40:(p + 1) * 0x40])
        if live != ours:
            sys.exit("ABORT: HSEPack delta table @0x%08X differs from the built-in "
                     "copy.\n  live %s\n  ours %s" % (va, live.hex(), ours.hex()))
    # slot 6 must be the (0,0) pad -- the cave uses it as "the shipyard's own hex"
    for p, dl in ((0, DELTAS_EVEN), (1, DELTAS_ODD)):
        assert dl[6] == (0, 0), "slot 6 of parity %d is not the (0,0) pad" % p
    return bytes(tab)


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    table = dump_deltas()
    T = TABLE_VA

    # ---------------- block sources -------------------------------------
    # Every block opens with the PIC preamble: N one-byte pushes, then
    # `call $+5` (E8 00000000, 5 bytes) and `pop ebx`, so ebx = load delta.
    # pop_at = block + N + 5, which is asserted byte-exactly after assembly.

    def src_entry(A, ensure_va, regions_va):
        # The PIC preamble MUST be the first thing in the block so that pop_at is a
        # hand-verifiable constant (entry + 3 one-byte pushes + 5-byte `call $+5`).
        # That is why the guards run after the frame is up and exit through e_zero_f.
        pop_at = A["entry"] + 3 + 5
        return f"""
        push ebx
        push esi
        push edi
        call 0x{pop_at:X}
        pop  ebx
        sub  ebx, 0x{pop_at:X}
        sub  esp, 0x20
        test eax, eax
        je   e_zero_f
        cmp  byte ptr [eax+0x{S_RAZED:X}], 1
        je   e_zero_f
        cmp  byte ptr [eax+0x{S_BUILD:X}], 0xFF
        jne  e_zero_f
        cmp  byte ptr [eax+0x{S_OWNER:X}], 0xFF
        je   e_zero_f
        cmp  dword ptr [eax+0x{S_FIELD:X}], 0
        je   e_zero_f
        mov  [esp+0x14], eax
        call 0x{ensure_va:X}
        test eax, eax
        je   e_zero_f
        mov  eax, [esp+0x14]
        lea  edi, [esp]
        call 0x{regions_va:X}
        test eax, eax
        je   e_zero_f
        mov  [esp+0x10], eax
        mov  dword ptr [esp+0x18], 0
        xor  edi, edi
    e_loop:
        cmp  edi, [esp+0x10]
        jge  e_done
        mov  esi, [esp + edi*4]
        mov  eax, [ebx + 0x{H_HEAP:X}]
        mov  ecx, eax
        add  ecx, [ebx + 0x{H_AOFF:X}]
        mov  eax, [ecx + esi*4]
        xor  edx, edx
        mov  ecx, {HEXES_PER_GOLD}
        div  ecx
        mov  ecx, [ebx + 0x{H_HEAP:X}]
        add  ecx, [ebx + 0x{H_COFF:X}]
        mov  ecx, [ecx + esi*4]
        test ecx, ecx
        je   e_next
        xor  edx, edx
        div  ecx
        add  [esp+0x18], eax
    e_next:
        inc  edi
        jmp  e_loop
    e_done:
        mov  eax, [esp+0x18]
        add  esp, 0x20
        pop  edi
        pop  esi
        pop  ebx
        ret
    e_zero_f:
        xor  eax, eax
        add  esp, 0x20
        pop  edi
        pop  esi
        pop  ebx
        ret
        """

    def src_ensure(A, t1_va, t2_va):
        # TIER 1 is keyed (map ptr, day, nlev, level0 cell count, level0 field base)
        # and NOTHING per-structure may ever join that key.
        # TIER 2 is NOT keyed -- build_t2 runs on every call.
        #
        # *** `ensure` MUST NOT CALL GetCount 0x55762390. *** It only tests
        # [map+0x100] for nil (guard G10) and discards the pointer. Any GetCount here
        # is a per-structure term one edit away from the tier-1 key, and it cannot buy
        # anything anyway: a GetCount key cannot see a shipyard finishing construction
        # (BuildingDone clears [s+0x24] in place and makes no TStructureControl call),
        # which is what made the body over-pay for the rest of that turn. The single
        # permitted GetCount lives in build_t2, and verify_cave asserts that on the
        # assembled bytes. See the CACHING block.
        return f"""
        push esi
        push edi
        cmp  dword ptr [ebx + 0x{H_BUSY:X}], 0
        jne  en_fail
        mov  esi, [ebx + 0x{MAPGLOBAL:X}]
        test esi, esi
        je   en_fail
        mov  ecx, [esi + 0x{MAP_CONTAINER:X}]
        test ecx, ecx
        je   en_fail
        mov  edx, [ecx + 0x{CONT_NLEV:X}]
        cmp  edx, 1
        jl   en_fail
        cmp  edx, {MAX_LEVELS}
        jg   en_fail
        cmp  dword ptr [esi + 0x{MAP_REGISTRY:X}], 0
        je   en_fail
        cmp  esi, [ebx + 0x{H_MAP:X}]
        jne  en_rebuild
        mov  eax, [esi + 0x{MAP_DAY:X}]
        cmp  eax, [ebx + 0x{H_DAY:X}]
        jne  en_rebuild
        cmp  edx, [ebx + 0x{H_NLEV:X}]
        jne  en_rebuild
        mov  eax, ecx
        xor  edx, edx
        call 0x{GETLVL:X}
        test eax, eax
        je   en_rebuild
        mov  ecx, [eax + 0x{L_COUNT:X}]
        cmp  ecx, [ebx + 0x{H_L0CNT:X}]
        jne  en_rebuild
        mov  ecx, [eax + 0x{L_FIELDS:X}]
        cmp  ecx, [ebx + 0x{H_L0BASE:X}]
        jne  en_rebuild
        jmp  en_tier2
    en_rebuild:
        mov  dword ptr [ebx + 0x{H_BUSY:X}], 1
        call 0x{t1_va:X}
        mov  dword ptr [ebx + 0x{H_BUSY:X}], 0
        cmp  dword ptr [ebx + 0x{H_MAP:X}], 0
        je   en_fail
    en_tier2:
        mov  eax, [ebx + 0x{MAPGLOBAL:X}]
        test eax, eax
        je   en_fail
        mov  eax, [eax + 0x{MAP_REGISTRY:X}]
        test eax, eax
        je   en_fail
        mov  dword ptr [ebx + 0x{H_BUSY:X}], 1
        call 0x{t2_va:X}
        mov  dword ptr [ebx + 0x{H_BUSY:X}], 0
        mov  eax, 1
        pop  edi
        pop  esi
        ret
    en_fail:
        xor  eax, eax
        pop  edi
        pop  esi
        ret
        """

    def src_regions(A):
        # IN  eax = structure, ebx = load delta, edi = 4-dword out buffer
        # OUT eax = number of distinct region ids written (0..4)
        # preserves ebx, edi, ebp, esi is scratch
        return f"""
        push edi
        push ebx
        sub  esp, 0x1C
        mov  dword ptr [esp], 0
        mov  ecx, [eax + 0x{S_FIELD:X}]
        test ecx, ecx
        je   ro_done
        movsx edx, byte ptr [ecx + 0x{F_L:X}]
        test edx, edx
        jl   ro_done
        cmp  edx, [ebx + 0x{H_NLEVELS:X}]
        jge  ro_done
        mov  esi, [ebx + edx*4 + 0x{H_W:X}]
        test esi, esi
        jle  ro_done
        mov  [esp+4], esi
        mov  eax, [ebx + edx*4 + 0x{H_H:X}]
        test eax, eax
        jle  ro_done
        mov  [esp+8], eax
        mov  eax, [ebx + 0x{H_HEAP:X}]
        test eax, eax
        je   ro_done
        add  eax, [ebx + edx*4 + 0x{H_LABOFF:X}]
        mov  [esp+0x0C], eax
        movsx eax, byte ptr [ecx + 0x{F_X:X}]
        mov  [esp+0x10], eax
        movsx eax, byte ptr [ecx + 0x{F_Y:X}]
        mov  [esp+0x14], eax
        mov  dword ptr [esp+0x18], 0
    ro_loop:
        cmp  dword ptr [esp+0x18], 7
        jge  ro_done
        mov  eax, [esp+0x10]
        and  eax, 1
        shl  eax, 6
        mov  ecx, [esp+0x18]
        lea  eax, [eax + ecx*8]
        add  eax, ebx
        mov  edx, [eax + 0x{T + 4:X}]
        mov  eax, [eax + 0x{T:X}]
        add  eax, [esp+0x10]
        add  edx, [esp+0x14]
        test eax, eax
        jl   ro_next
        cmp  eax, [esp+4]
        jge  ro_next
        test edx, edx
        jl   ro_next
        cmp  edx, [esp+8]
        jge  ro_next
        imul edx, [esp+4]
        add  edx, eax
        mov  ecx, [esp+0x0C]
        movzx eax, word ptr [ecx + edx*2]
        test eax, eax
        je   ro_next
        cmp  eax, 0xFFFF
        je   ro_next
        mov  ecx, [esp]
        xor  edx, edx
    ro_dedup:
        cmp  edx, ecx
        jge  ro_add
        cmp  eax, [edi + edx*4]
        je   ro_next
        inc  edx
        jmp  ro_dedup
    ro_add:
        cmp  ecx, 4
        jge  ro_next
        mov  [edi + ecx*4], eax
        inc  ecx
        mov  [esp], ecx
    ro_next:
        inc  dword ptr [esp+0x18]
        jmp  ro_loop
    ro_done:
        mov  eax, [esp]
        add  esp, 0x1C
        pop  ebx
        pop  edi
        ret
        """

    def src_t1(A):
        # frame (0x60):
        #  +00 container  +04 map      +08 nlev     +0C li      +10 total  +14 max
        #  +18 labels/scr +1C need     +20 nextid   +24 qhead   +28 qtail  +2C curid
        #  +30 (spare)    +34 n cells  +38 W        +3C H       +40 x      +44 y
        #  +48 side       +4C nx       +50 saved load delta
        return f"""
        push esi
        push edi
        sub  esp, 0x60
        mov  [esp+0x50], ebx
        mov  dword ptr [ebx + 0x{H_MAP:X}], 0
        mov  dword ptr [ebx + 0x{H_YVALID:X}], 0
        mov  dword ptr [ebx + 0x{H_YN:X}], 0
        mov  esi, [ebx + 0x{MAPGLOBAL:X}]
        mov  [esp+4], esi
        mov  ecx, [esi + 0x{MAP_CONTAINER:X}]
        mov  [esp], ecx
        mov  edx, [ecx + 0x{CONT_NLEV:X}]
        mov  [esp+8], edx
        xor  eax, eax
        mov  [esp+0x10], eax
        mov  [esp+0x14], eax
        mov  [esp+0x0C], eax
    t1_dim:
        mov  edx, [esp+0x0C]
        cmp  edx, {MAX_LEVELS}
        jge  t1_dimdone
        xor  esi, esi
        xor  edi, edi
        cmp  edx, [esp+8]
        jge  t1_store
        mov  eax, [esp]
        call 0x{GETLVL:X}
        test eax, eax
        je   t1_store
        cmp  dword ptr [eax + 0x{L_FIELDS:X}], 0
        je   t1_store
        cmp  dword ptr [eax + 0x{L_STRIDE:X}], 4
        jl   t1_store
        mov  esi, [eax + 0x{L_W:X}]
        test esi, esi
        jle  t1_bad
        mov  edi, [eax + 0x{L_H:X}]
        test edi, edi
        jle  t1_bad
        mov  ecx, esi
        imul ecx, edi
        cmp  ecx, 0x{MAX_CELLS_PER_LEVEL:X}
        jg   t1_bad
        cmp  ecx, [eax + 0x{L_COUNT:X}]
        je   t1_store
    t1_bad:
        xor  esi, esi
        xor  edi, edi
    t1_store:
        mov  edx, [esp+0x0C]
        mov  [ebx + edx*4 + 0x{H_W:X}], esi
        mov  [ebx + edx*4 + 0x{H_H:X}], edi
        mov  eax, [esp+0x10]
        add  eax, eax
        mov  [ebx + edx*4 + 0x{H_LABOFF:X}], eax
        mov  ecx, esi
        imul ecx, edi
        mov  eax, [esp+0x10]
        add  eax, ecx
        mov  [esp+0x10], eax
        cmp  ecx, [esp+0x14]
        jle  t1_dimnext
        mov  [esp+0x14], ecx
    t1_dimnext:
        inc  dword ptr [esp+0x0C]
        jmp  t1_dim
    t1_dimdone:
        mov  eax, [esp+0x10]
        inc  eax
        mov  [ebx + 0x{H_NRSLOTS:X}], eax
        mov  ecx, [esp+0x10]
        add  ecx, ecx
        add  ecx, 3
        and  ecx, -4
        mov  [ebx + 0x{H_QOFF:X}], ecx
        mov  edx, [esp+0x14]
        shl  edx, 2
        add  ecx, edx
        mov  [ebx + 0x{H_AOFF:X}], ecx
        mov  edx, eax
        shl  edx, 2
        add  ecx, edx
        mov  [ebx + 0x{H_COFF:X}], ecx
        add  ecx, edx
        mov  [ebx + 0x{H_YOFF:X}], ecx
        add  ecx, 0x{MAX_YARDS * 4:X}
        mov  [esp+0x1C], ecx
        cmp  ecx, [ebx + 0x{H_CAP:X}]
        jle  t1_haveheap
        lea  eax, [ebx + 0x{H_HEAP:X}]
        mov  edx, ecx
        call 0x{REALLOC:X}
        mov  ebx, [esp+0x50]
        cmp  dword ptr [ebx + 0x{H_HEAP:X}], 0
        je   t1_nomem
        mov  ecx, [esp+0x1C]
        mov  [ebx + 0x{H_CAP:X}], ecx
    t1_haveheap:
        mov  eax, [ebx + 0x{H_HEAP:X}]
        test eax, eax
        je   t1_nomem
        mov  edx, [esp+0x1C]
        xor  ecx, ecx
        call 0x{FILLCHAR:X}
        mov  ebx, [esp+0x50]
        mov  dword ptr [esp+0x0C], 0
    t1_mark:
        mov  edx, [esp+0x0C]
        cmp  edx, {MAX_LEVELS}
        jge  t1_markdone
        mov  eax, [ebx + edx*4 + 0x{H_W:X}]
        test eax, eax
        jle  t1_marknext
        mov  ecx, [ebx + edx*4 + 0x{H_H:X}]
        imul eax, ecx
        mov  [esp+0x34], eax
        mov  eax, [esp]
        call 0x{GETLVL:X}
        test eax, eax
        je   t1_marknext
        mov  esi, [eax + 0x{L_FIELDS:X}]
        mov  edi, [eax + 0x{L_STRIDE:X}]
        mov  edx, [esp+0x0C]
        mov  eax, [ebx + 0x{H_HEAP:X}]
        add  eax, [ebx + edx*4 + 0x{H_LABOFF:X}]
        mov  ecx, [esp+0x34]
    t1_m1:
        test ecx, ecx
        jle  t1_marknext
        mov  dl, byte ptr [esi + 0x{F_TERR:X}]
        test dl, dl
        je   t1_mwater
        cmp  dl, 0x0A
        jne  t1_mland
    t1_mwater:
        mov  word ptr [eax], 0xFFFF
    t1_mland:
        add  esi, edi
        add  eax, 2
        dec  ecx
        jmp  t1_m1
    t1_marknext:
        inc  dword ptr [esp+0x0C]
        jmp  t1_mark
    t1_markdone:
        mov  dword ptr [esp+0x20], 1
        mov  dword ptr [esp+0x0C], 0
    t1_bfs:
        mov  edx, [esp+0x0C]
        cmp  edx, {MAX_LEVELS}
        jge  t1_bfsdone
        mov  eax, [ebx + edx*4 + 0x{H_W:X}]
        mov  [esp+0x38], eax
        test eax, eax
        jle  t1_bfsnext
        mov  ecx, [ebx + edx*4 + 0x{H_H:X}]
        mov  [esp+0x3C], ecx
        imul eax, ecx
        mov  [esp+0x34], eax
        mov  eax, [ebx + 0x{H_HEAP:X}]
        add  eax, [ebx + edx*4 + 0x{H_LABOFF:X}]
        mov  [esp+0x18], eax
        xor  esi, esi
    t1_seed:
        cmp  esi, [esp+0x34]
        jge  t1_bfsnext
        mov  eax, [esp+0x18]
        movzx ecx, word ptr [eax + esi*2]
        cmp  ecx, 0xFFFF
        jne  t1_seednext
        mov  ecx, [esp+0x20]
        cmp  ecx, 0x{MAX_REGION_ID:X}
        jg   t1_bfsdone
        mov  [esp+0x2C], ecx
        inc  dword ptr [esp+0x20]
        mov  word ptr [eax + esi*2], cx
        mov  dword ptr [esp+0x24], 0
        mov  dword ptr [esp+0x28], 1
        mov  eax, esi
        xor  edx, edx
        div  dword ptr [esp+0x38]
        shl  eax, 16
        or   eax, edx
        mov  ecx, [ebx + 0x{H_HEAP:X}]
        add  ecx, [ebx + 0x{H_QOFF:X}]
        mov  [ecx], eax
    t1_pop:
        mov  eax, [esp+0x24]
        cmp  eax, [esp+0x28]
        jge  t1_compdone
        mov  ecx, [ebx + 0x{H_HEAP:X}]
        add  ecx, [ebx + 0x{H_QOFF:X}]
        mov  eax, [ecx + eax*4]
        inc  dword ptr [esp+0x24]
        mov  edi, eax
        shr  edi, 16
        and  eax, 0xFFFF
        mov  [esp+0x40], eax
        mov  [esp+0x44], edi
        mov  dword ptr [esp+0x48], 0
    t1_side:
        cmp  dword ptr [esp+0x48], 6
        jge  t1_pop
        mov  eax, [esp+0x40]
        and  eax, 1
        shl  eax, 6
        mov  ecx, [esp+0x48]
        lea  eax, [eax + ecx*8]
        add  eax, ebx
        mov  edx, [eax + 0x{T + 4:X}]
        mov  eax, [eax + 0x{T:X}]
        add  eax, [esp+0x40]
        add  edx, [esp+0x44]
        test eax, eax
        jl   t1_sidenext
        cmp  eax, [esp+0x38]
        jge  t1_sidenext
        test edx, edx
        jl   t1_sidenext
        cmp  edx, [esp+0x3C]
        jge  t1_sidenext
        mov  [esp+0x4C], eax
        mov  edi, edx
        imul edi, [esp+0x38]
        add  edi, eax
        mov  ecx, [esp+0x18]
        movzx eax, word ptr [ecx + edi*2]
        cmp  eax, 0xFFFF
        jne  t1_sidenext
        mov  eax, [esp+0x2C]
        mov  word ptr [ecx + edi*2], ax
        shl  edx, 16
        or   edx, [esp+0x4C]
        mov  ecx, [ebx + 0x{H_HEAP:X}]
        add  ecx, [ebx + 0x{H_QOFF:X}]
        mov  eax, [esp+0x28]
        mov  [ecx + eax*4], edx
        inc  dword ptr [esp+0x28]
    t1_sidenext:
        inc  dword ptr [esp+0x48]
        jmp  t1_side
    t1_compdone:
        mov  ecx, [ebx + 0x{H_HEAP:X}]
        add  ecx, [ebx + 0x{H_AOFF:X}]
        mov  eax, [esp+0x2C]
        mov  edx, [esp+0x28]
        mov  [ecx + eax*4], edx
    t1_seednext:
        inc  esi
        jmp  t1_seed
    t1_bfsnext:
        inc  dword ptr [esp+0x0C]
        jmp  t1_bfs
    t1_bfsdone:
        mov  eax, [esp+0x20]
        dec  eax
        mov  [ebx + 0x{H_NREG:X}], eax
        mov  eax, [esp+8]
        mov  [ebx + 0x{H_NLEVELS:X}], eax
        jmp  t1_key
    t1_nomem:
        xor  eax, eax
        mov  [ebx + 0x{H_HEAP:X}], eax
        mov  [ebx + 0x{H_CAP:X}], eax
        mov  [ebx + 0x{H_NREG:X}], eax
        mov  [ebx + 0x{H_NLEVELS:X}], eax
        mov  [ebx + 0x{H_YOFF:X}], eax
        mov  [ebx + 0x{H_YN:X}], eax
    t1_key:
        mov  esi, [esp+4]
        mov  eax, [esi + 0x{MAP_DAY:X}]
        mov  [ebx + 0x{H_DAY:X}], eax
        mov  eax, [esp+8]
        mov  [ebx + 0x{H_NLEV:X}], eax
        mov  eax, [esp]
        test eax, eax
        je   t1_key2
        xor  edx, edx
        call 0x{GETLVL:X}
        test eax, eax
        je   t1_key2
        mov  ecx, [eax + 0x{L_COUNT:X}]
        mov  [ebx + 0x{H_L0CNT:X}], ecx
        mov  ecx, [eax + 0x{L_FIELDS:X}]
        mov  [ebx + 0x{H_L0BASE:X}], ecx
        jmp  t1_key3
    t1_key2:
        xor  ecx, ecx
        mov  [ebx + 0x{H_L0CNT:X}], ecx
        mov  [ebx + 0x{H_L0BASE:X}], ecx
    t1_key3:
        mov  [ebx + 0x{H_MAP:X}], esi
        mov  eax, 1
        add  esp, 0x60
        pop  edi
        pop  esi
        ret
        """

    def src_harvest(A):
        # THE ONLY REGISTRY WALK IN THE CAVE. Runs only when GetCount has moved or
        # build_t1 has invalidated the sub-list.
        #   IN  eax = registry count (>= 0), edx = registry, ebx = load delta
        #   OUT H_YN / H_YCOUNT / H_YVALID written; nothing returned
        # frame (0x14): +00 n  +04 registry  +08 yards[]  +0C i  +10 saved delta
        #
        # It caches POINTERS ONLY. Not one membership byte is looked at here -- the
        # razed / building / field tests belong to build_t2, which re-reads them on
        # every evaluation off these pointers. Caching them here would put the
        # over-pay bug straight back.
        return f"""
        push esi
        push edi
        sub  esp, 0x14
        mov  [esp+0x10], ebx
        mov  [esp], eax
        mov  [esp+4], edx
        mov  dword ptr [ebx + 0x{H_YVALID:X}], 0
        mov  dword ptr [ebx + 0x{H_YN:X}], 0
        mov  eax, [ebx + 0x{H_HEAP:X}]
        test eax, eax
        je   hv_done
        add  eax, [ebx + 0x{H_YOFF:X}]
        mov  [esp+8], eax
        mov  dword ptr [esp+0x0C], 0
    hv_loop:
        mov  edx, [esp+0x0C]
        cmp  edx, [esp]
        jge  hv_ok
        mov  eax, [esp+4]
        call 0x{GETSTRUCT:X}
        mov  ebx, [esp+0x10]
        test eax, eax
        je   hv_next
        mov  esi, eax
        mov  eax, [esi]
        call dword ptr [eax + 0x24]
        mov  ebx, [esp+0x10]
        cmp  eax, 0x{CLASSID_SHIPYARD:X}
        jne  hv_next
        mov  ecx, [ebx + 0x{H_YN:X}]
        cmp  ecx, 0x{MAX_YARDS:X}
        jge  hv_ok
        mov  edx, [esp+8]
        mov  [edx + ecx*4], esi
        inc  ecx
        mov  [ebx + 0x{H_YN:X}], ecx
    hv_next:
        inc  dword ptr [esp+0x0C]
        jmp  hv_loop
    hv_ok:
        mov  eax, [esp]
        mov  [ebx + 0x{H_YCOUNT:X}], eax
        mov  dword ptr [ebx + 0x{H_YVALID:X}], 1
    hv_done:
        add  esp, 0x14
        pop  edi
        pop  esi
        ret
        """

    def src_t2(A, regions_va, harvest_va):
        # frame (0x20): +00..+0F region buffer  +10 i  +14 n  +18 registry  +1C delta
        #
        # The FillChar zeroes only count[0..H_NREG], NOT the whole H_NRSLOTS array.
        # That matters because this pass is unconditional -- it runs on EVERY
        # GetIncome call. H_NRSLOTS*4 is up to ~193 KB while H_NREG is typically a few
        # dozen; only ids 1..H_NREG are ever written to labels[], so the rest is dead
        # space and must not be touched.
        #
        # GETCOUNT is called EXACTLY ONCE here and nowhere else in the cave -- that is
        # asserted on the assembled bytes in verify_cave. GETSTRUCT does not appear
        # here at all; the registry walk lives in `harvest`.
        #
        # Every membership byte is re-read here on every call ([+0x48] razed,
        # [+0x24] building, [+0x04] field), off the CACHED pointers, which is what
        # makes a mid-turn construction completion -- and a mid-turn razing -- move the
        # divisor in the SAME evaluation instead of at the next day rollover. Neither
        # of those moves GetCount, so neither triggers a re-harvest, and neither needs
        # to.
        return f"""
        push esi
        push edi
        sub  esp, 0x20
        mov  [esp+0x1C], ebx
        mov  eax, [ebx + 0x{H_HEAP:X}]
        test eax, eax
        je   t2_done
        add  eax, [ebx + 0x{H_COFF:X}]
        mov  edx, [ebx + 0x{H_NREG:X}]
        inc  edx
        shl  edx, 2
        xor  ecx, ecx
        call 0x{FILLCHAR:X}
        mov  ebx, [esp+0x1C]
        mov  eax, [ebx + 0x{MAPGLOBAL:X}]
        test eax, eax
        je   t2_done
        mov  eax, [eax + 0x{MAP_REGISTRY:X}]
        test eax, eax
        je   t2_done
        mov  [esp+0x18], eax
        call 0x{GETCOUNT:X}
        mov  ebx, [esp+0x1C]
        mov  [esp+0x14], eax
        test eax, eax
        js   t2_done
        cmp  dword ptr [ebx + 0x{H_YVALID:X}], 0
        je   t2_harvest
        cmp  eax, [ebx + 0x{H_YCOUNT:X}]
        je   t2_walk
    t2_harvest:
        mov  eax, [esp+0x14]
        mov  edx, [esp+0x18]
        call 0x{harvest_va:X}
        mov  ebx, [esp+0x1C]
        cmp  dword ptr [ebx + 0x{H_YVALID:X}], 0
        je   t2_done
    t2_walk:
        mov  eax, [ebx + 0x{H_YN:X}]
        mov  [esp+0x14], eax
        mov  dword ptr [esp+0x10], 0
    t2_loop:
        mov  edx, [esp+0x10]
        cmp  edx, [esp+0x14]
        jge  t2_done
        mov  eax, [ebx + 0x{H_HEAP:X}]
        add  eax, [ebx + 0x{H_YOFF:X}]
        mov  esi, [eax + edx*4]
        test esi, esi
        je   t2_next
        cmp  byte ptr [esi + 0x{S_RAZED:X}], 1
        je   t2_next
        cmp  byte ptr [esi + 0x{S_BUILD:X}], 0xFF
        jne  t2_next
        cmp  dword ptr [esi + 0x{S_FIELD:X}], 0
        je   t2_next
        mov  eax, esi
        lea  edi, [esp]
        call 0x{regions_va:X}
        test eax, eax
        je   t2_next
        mov  esi, eax
        xor  edx, edx
        mov  edi, [ebx + 0x{H_HEAP:X}]
        add  edi, [ebx + 0x{H_COFF:X}]
    t2_inc:
        cmp  edx, esi
        jge  t2_next
        mov  ecx, [esp + edx*4]
        inc  dword ptr [edi + ecx*4]
        inc  edx
        jmp  t2_inc
    t2_next:
        inc  dword ptr [esp+0x10]
        jmp  t2_loop
    t2_done:
        add  esp, 0x20
        pop  edi
        pop  esi
        ret
        """

    # ---------------- layout to a fixed point ---------------------------
    ORDER = ["entry", "ensure", "regions_of", "build_t1", "build_t2", "harvest"]

    def assemble(A):
        srcs = {
            "entry":      src_entry(A, A["ensure"], A["regions_of"]),
            "ensure":     src_ensure(A, A["build_t1"], A["build_t2"]),
            "regions_of": src_regions(A),
            "build_t1":   src_t1(A),
            "build_t2":   src_t2(A, A["regions_of"], A["harvest"]),
            "harvest":    src_harvest(A),
        }
        out = {}
        for k in ORDER:
            # this keystone build treats ';' as a syntax error -- strip end-of-line
            # comments before assembling
            s = "\n".join(ln.split(";")[0] for ln in srcs[k].splitlines())
            out[k] = bytes(ks.asm(s, A[k])[0])
        return out

    A = {k: TABLE_VA + 0x80 + i * 0x400 for i, k in enumerate(ORDER)}
    blobs = None
    for _ in range(8):
        blobs = assemble(A)
        nxt = {}
        cur = TABLE_VA + 0x80
        for k in ORDER:
            cur = (cur + 0xF) & ~0xF
            nxt[k] = cur
            cur += len(blobs[k])
        if nxt == A:
            break
        A = nxt
    else:
        sys.exit("ABORT: cave layout did not reach a fixed point")
    blobs = assemble(A)                 # final, at the settled addresses

    cave = {"table": (TABLE_VA, table)}
    end = TABLE_VA + 0x80
    for k in ORDER:
        cave[k] = (A[k], blobs[k])
        end = A[k] + len(blobs[k])
    cave["_end"] = end
    cave["_order"] = ["table"] + ORDER

    verify_cave(cave)
    return cave


# ============================================================================
# build-time assertions on the ASSEMBLED bytes -- never trust the round trip
# ============================================================================
def verify_cave(cave):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    used = cave["_end"] - CAVE_VA
    if used > CAVE_LIMIT:
        sys.exit("ABORT: cave is %d B, over the 0x%X reservation" % (used, CAVE_LIMIT))
    if HDR_END > HDR + HDR_WINDOW:
        sys.exit("ABORT: BSS header overruns its 0x%X window" % HDR_WINDOW)

    # 1. PIC preamble of `entry`: exactly `push ebx/esi/edi`, `call $+5`, `pop ebx`,
    #    and it must be the FIRST thing in the block (that is what makes pop_at a
    #    hand-verifiable constant rather than a byte count).
    va, b = cave["entry"]
    i = b.find(b"\x53\x56\x57\xE8\x00\x00\x00\x00\x5B")
    if i != 0:
        sys.exit("ABORT: entry's PIC preamble is at offset %d, expected 0 "
                 "(bytes: %s)" % (i, b[:16].hex().upper()))
    pop_at = va + i + 3 + 5
    # the `sub ebx, imm32` right after the pop must subtract exactly pop_at
    if b[i + 9] != 0x81 or b[i + 10] != 0xEB:
        sys.exit("ABORT: PIC preamble is not followed by `sub ebx, imm32`")
    imm = struct.unpack_from("<I", b, i + 11)[0]
    if imm != pop_at:
        sys.exit("ABORT: PIC delta subtracts 0x%08X but the pop is at 0x%08X"
                 % (imm, pop_at))

    # 2. no bare absolute memory operand anywhere, and no `ret imm16`
    bad_abs, bad_ret, overlay = [], [], []
    for k in cave["_order"]:
        if k == "table":
            continue
        va, b = cave[k]
        n = 0
        for ins in md.disasm(b, va):
            n += len(ins.bytes)
            txt = "%s %s" % (ins.mnemonic, ins.op_str)
            # a bare absolute operand renders as `[0x55......]`; anything with a base
            # register renders as `[reg + 0x55......]` and is PIC via the load delta
            if "[0x" in ins.op_str:
                bad_abs.append((k, ins.address, txt))
            if ins.mnemonic == "ret" and ins.op_str:
                bad_ret.append((k, ins.address, txt))
            # the overlay byte [field+0x15] must never be read
            if "+ 0x15]" in ins.op_str:
                overlay.append((k, ins.address, txt))
        if n != len(b):
            sys.exit("ABORT: %s did not fully disassemble (%d of %d B)" % (k, n, len(b)))
    terr_reads = overlay
    if bad_abs:
        for k, a, t in bad_abs:
            print("  ABSOLUTE OPERAND  %s 0x%08X  %s" % (k, a, t))
        sys.exit("ABORT: the cave is NOT position-independent")
    if bad_ret:
        for k, a, t in bad_ret:
            print("  RET IMM16  %s 0x%08X  %s" % (k, a, t))
        sys.exit("ABORT: a `ret n` would corrupt the caller's stack")
    if terr_reads:
        for k, a, t in terr_reads:
            print("  OVERLAY READ  %s 0x%08X  %s" % (k, a, t))
        sys.exit("ABORT: the cave must ignore the overlay byte [field+0x15]")

    # 3. the water predicate: exactly {0x00, 0x0A}. There must be no comparand 6 or
    #    0x0E anywhere against the terrain byte.
    va, b = cave["build_t1"]
    txts = ["%s %s" % (i.mnemonic, i.op_str) for i in md.disasm(b, va)]
    if not any("byte ptr [esi + 0x14]" in t for t in txts):
        sys.exit("ABORT: build_t1 never reads the terrain byte [field+0x14]")
    for t in txts:
        if t.startswith("cmp dl,") and t not in ("cmp dl, 0xa",):
            sys.exit("ABORT: unexpected terrain comparand: %s" % t)

    # 4. the keystone imm trap (`push 0xFFFF` silently becomes `6A FF` = -1):
    #    assert every literal 0xffff operand really carries FF FF in its encoding,
    #    and that no `push imm8` exists anywhere in the cave.
    import re
    ffff = re.compile(r"(?<![0-9a-fx])0xffff(?![0-9a-f])")
    seen_ffff = 0
    for k in cave["_order"]:
        if k == "table":
            continue
        va, b = cave[k]
        for ins in md.disasm(b, va):
            if ffff.search(ins.op_str):
                seen_ffff += 1
                if b"\xff\xff" not in ins.bytes:
                    sys.exit("ABORT: %s @0x%08X claims 0xffff but encodes %s"
                             % (k, ins.address, ins.bytes.hex()))
            if ins.mnemonic == "push" and ins.bytes[:1] == b"\x6a":
                sys.exit("ABORT: %s @0x%08X is a push imm8 (the -1 trap)"
                         % (k, ins.address))
    if seen_ffff < 4:
        sys.exit("ABORT: expected at least 4 literal 0xFFFF operands (water marker, "
                 "seed test, neighbour test, regions_of skip), found %d" % seen_ffff)
    # ...and no operand may reach 0xFFFF the OTHER way, through a sign-extended imm8
    # that capstone renders as `-1`. Every 0xFFFF in this cave must be written out.
    for k in cave["_order"]:
        if k == "table":
            continue
        va, b = cave[k]
        for ins in md.disasm(b, va):
            if ins.op_str.endswith(", -1") or ", -1," in ins.op_str:
                sys.exit("ABORT: %s @0x%08X uses a sign-extended -1 immediate (%s) -- "
                         "write the constant out so the listing is unambiguous"
                         % (k, ins.address, "%s %s" % (ins.mnemonic, ins.op_str)))

    # 5. every call target is inside AoWEPACK's CODE section
    for k in cave["_order"]:
        if k == "table":
            continue
        va, b = cave[k]
        for ins in md.disasm(b, va):
            if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
                tgt = int(ins.op_str, 16)
                if not (0x55701000 <= tgt < 0x558E7918):
                    sys.exit("ABORT: %s @0x%08X targets 0x%08X, outside CODE"
                             % (k, ins.address, tgt))

    # 6. THE TIER-1 CATASTROPHE GUARD, AT THE BYTE LEVEL.
    #    Up to now the only thing standing between this cave and an O(S * flood)
    #    map-load catastrophe was a paragraph in the docstring saying "GetCount must
    #    never enter the tier-1 key". Prose does not abort a build. These do.
    #
    #    GETCOUNT 0x55762390 must be called EXACTLY ONCE in the entire cave, and that
    #    one call must be in `build_t2` (the sub-list freshness test). If it ever
    #    appears in `ensure`, something per-structure has been wired into the tier-1
    #    key. GETSTRUCT 0x55762364 -- the registry walk -- must appear ONLY in
    #    `harvest`, exactly once, or the per-evaluation path is walking the registry
    #    again.
    def call_count(block, target):
        va, b = cave[block]
        n = 0
        for ins in md.disasm(b, va):
            if (ins.mnemonic == "call" and ins.op_str.startswith("0x")
                    and int(ins.op_str, 16) == target):
                n += 1
        return n

    expect = [
        ("entry",      GETCOUNT,  0), ("ensure",     GETCOUNT,  0),
        ("regions_of", GETCOUNT,  0), ("build_t1",   GETCOUNT,  0),
        ("build_t2",   GETCOUNT,  1), ("harvest",    GETCOUNT,  0),
        ("entry",      GETSTRUCT, 0), ("ensure",     GETSTRUCT, 0),
        ("regions_of", GETSTRUCT, 0), ("build_t1",   GETSTRUCT, 0),
        ("build_t2",   GETSTRUCT, 0), ("harvest",    GETSTRUCT, 1),
    ]
    names = {GETCOUNT: "TStructureControl.GetCount",
             GETSTRUCT: "TStructureControl.GetStructure"}
    for block, target, want_n in expect:
        got_n = call_count(block, target)
        if got_n != want_n:
            sys.exit("ABORT: %s calls %s 0x%08X %d time(s), expected %d.\n"
                     "  See the CACHING block: GetCount belongs in build_t2 only "
                     "(once), the registry walk in harvest only (once). A GetCount "
                     "reaching `ensure` is the tier-1 catastrophe."
                     % (block, names[target], target, got_n, want_n))
    total_gc = sum(call_count(k, GETCOUNT) for k in cave["_order"] if k != "table")
    if total_gc != 1:
        sys.exit("ABORT: GetCount is called %d times across the cave, expected "
                 "exactly 1" % total_gc)

    # 7. THE USE-AFTER-FREE GUARD, AT THE BYTE LEVEL.
    #    build_t1 can ReallocMem the heap block, and yards[] lives INSIDE that block,
    #    so the realloc can move every pointer the sub-list holds. build_t1's clear of
    #    H_YVALID (and H_YN) is what forces build_t2 to re-harvest afterwards instead
    #    of dereferencing the moved array. It is mandatory, not belt-and-braces, and
    #    the ORDERING is the actual invariant: the clear must execute BEFORE the
    #    ReallocMem call, not merely exist somewhere in the block.
    #
    #    Until now this one line was protected by prose only. QA deleted it from a
    #    scratch copy on 2026-08-26: the build completed clean, verify_cave said
    #    nothing, and the only signal was an unexplained "cave zone differs". Prose in
    #    a docstring stops nobody; this abort does.
    va, b = cave["build_t1"]
    zeroed, realloc_at = {}, []
    for ins in md.disasm(b, va):
        if (ins.mnemonic == "mov" and ins.op_str.endswith(", 0")
                and ins.op_str.startswith("dword ptr [ebx + 0x")):
            disp = int(ins.op_str.split("[ebx + ", 1)[1].split("]", 1)[0], 16)
            zeroed.setdefault(disp, ins.address)
        if (ins.mnemonic == "call" and ins.op_str.startswith("0x")
                and int(ins.op_str, 16) == REALLOC):
            realloc_at.append(ins.address)
    if len(realloc_at) != 1:
        sys.exit("ABORT: build_t1 calls ReallocMem 0x%08X %d time(s), expected exactly "
                 "1. The sub-list invalidation ordering below has no single call site "
                 "to be tested against." % (REALLOC, len(realloc_at)))
    for nm, fld in (("H_YVALID", H_YVALID), ("H_YN", H_YN)):
        if fld not in zeroed:
            sys.exit("ABORT: build_t1 never zeroes %s (0x%08X). That clear is what "
                     "forces a re-harvest after a ReallocMem moves yards[]; without "
                     "it build_t2 dereferences pointers into freed memory. See THE "
                     "SHIPYARD SUB-LIST." % (nm, fld))
        if zeroed[fld] >= realloc_at[0]:
            sys.exit("ABORT: build_t1 zeroes %s (0x%08X) at 0x%08X, which is AT OR "
                     "AFTER the ReallocMem call at 0x%08X. The clear must precede the "
                     "realloc -- a sub-list left valid across a heap move is a "
                     "use-after-free." % (nm, fld, zeroed[fld], realloc_at[0]))

    # 8. THE BALANCE KNOB, READ BACK OFF THE ASSEMBLED BYTES.
    #    `entry` performs exactly two divides: the pot divide by HEXES_PER_GOLD, then
    #    the split by the shipyard count N. Only the FIRST is the rate. This asserts
    #    that the cave really divides by the constant the --sim expectations derive
    #    from -- without it, a re-tune could move sim_pot() and leave the cave on the
    #    old rate (or vice versa) with every check still printing OK.
    #    It also pins the ORDER: pot first, N second. Swapping them changes the answer
    #    (floor(floor(a/N)/rate) != floor(floor(a/rate)/N) in general) and nothing
    #    else in this file would notice.
    va, b = cave["entry"]
    ins_list = list(md.disasm(b, va))
    divs = [i for i, ins in enumerate(ins_list)
            if ins.mnemonic == "div" and ins.op_str == "ecx"]
    if len(divs) != 2:
        sys.exit("ABORT: `entry` contains %d `div ecx` instruction(s), expected exactly "
                 "2 (pot by HEXES_PER_GOLD, then the split by N)." % len(divs))
    # `mov ecx, <immediate>` only -- `mov ecx, eax` and `mov ecx, [ebx + ...]` are the
    # heap-pointer arithmetic a few lines above the divide and are not the rate.
    ecx_imm = re.compile(r"^ecx, (0x[0-9a-fA-F]+|\d+)$")
    imm_movs = [ins for ins in ins_list
                if ins.mnemonic == "mov" and ecx_imm.match(ins.op_str)]
    if len(imm_movs) != 1:
        sys.exit("ABORT: `entry` loads ecx with an immediate %d time(s), expected "
                 "exactly 1 (the rate). Found: %s"
                 % (len(imm_movs), ", ".join("%s %s" % (i.mnemonic, i.op_str)
                                             for i in imm_movs) or "none"))
    setup = ins_list[divs[0] - 1]
    if setup is not imm_movs[0]:
        sys.exit("ABORT: the instruction before the FIRST `div ecx` in `entry` is "
                 "`%s %s`, not the rate load. The pot divide must come first."
                 % (setup.mnemonic, setup.op_str))
    got_rate = int(setup.op_str.split(", ", 1)[1], 0)
    if got_rate != HEXES_PER_GOLD:
        sys.exit("ABORT: the assembled pot divisor is %d but HEXES_PER_GOLD is %d -- "
                 "the cave and the --sim expectations disagree about the rate."
                 % (got_rate, HEXES_PER_GOLD))
    # and the second divide must NOT be by an immediate -- it is the shipyard count
    if any(ins.mnemonic == "mov" and ecx_imm.match(ins.op_str)
           for ins in ins_list[divs[0] + 1:divs[1] + 1]):
        sys.exit("ABORT: an immediate is loaded into ecx between the two divides in "
                 "`entry`; the second must divide by the live shipyard count N.")


# ============================================================================
# --sim: pure-Python reference of the whole rule
# ============================================================================
class SimLevel(object):
    def __init__(self, W, H, fill=1):
        self.W, self.H = W, H
        self.t = [fill] * (W * H)      # terrain 1 = plain grass, i.e. not water

    def set(self, x, y, terr):
        self.t[y * self.W + x] = terr


class SimYard(object):
    def __init__(self, L, x, y, owner=0, razed=False, building=False):
        self.L, self.x, self.y = L, x, y
        self.owner, self.razed, self.building = owner, razed, building


class SimOther(object):
    """A non-shipyard entry in the structure registry. The harvest walks past it
    (ClassID != TShipyard) and it must never reach the sub-list."""
    pass


def sim_label(levels):
    """Mirrors build_t1 exactly: mark water 0xFFFF, then BFS in (level, y, x) seed
    order with globally increasing region ids."""
    labels, area, nextid = [], {0: 0}, 1
    stop = False
    for lv in levels:
        W, H = lv.W, lv.H
        lab = [0] * (W * H)
        for i in range(W * H):
            if lv.t[i] in WATER:
                lab[i] = 0xFFFF
        if not stop:
            for seed in range(W * H):
                if lab[seed] != 0xFFFF:
                    continue
                if nextid > MAX_REGION_ID:
                    stop = True
                    break
                rid, nextid = nextid, nextid + 1
                lab[seed] = rid
                q = [(seed % W, seed // W)]
                head = 0
                while head < len(q):
                    x, y = q[head]
                    head += 1
                    for dx, dy in (DELTAS_ODD if (x & 1) else DELTAS_EVEN)[:6]:
                        nx, ny = x + dx, y + dy
                        if not (0 <= nx < W and 0 <= ny < H):
                            continue
                        ni = ny * W + nx
                        if lab[ni] != 0xFFFF:
                            continue
                        lab[ni] = rid
                        q.append((nx, ny))
                area[rid] = len(q)
        labels.append(lab)
    return labels, area


def sim_regions(labels, levels, L, x, y):
    """Mirrors regions_of: sides 0..6, where slot 6 is the (0,0) pad = the own hex.
    Dedupes into at most 4 slots."""
    out = []
    if L < 0 or L >= len(levels):
        return out
    lv = levels[L]
    W, H = lv.W, lv.H
    if W < 1 or H < 1:
        return out
    lab = labels[L]
    for dx, dy in (DELTAS_ODD if (x & 1) else DELTAS_EVEN)[:7]:
        nx, ny = x + dx, y + dy
        if not (0 <= nx < W and 0 <= ny < H):
            continue
        v = lab[ny * W + nx]
        if v == 0 or v == 0xFFFF:
            continue
        if v in out:
            continue
        if len(out) >= 4:
            continue
        out.append(v)
    return out


class SimEngine(object):
    """Mirrors `ensure` -- the two-tier cache, including which tier is keyed, and the
    cached shipyard sub-list that the tier-2 pass walks.

    TIER 1 (sim_label, the flood): keyed on (map identity, day, level count, level-0
    cell count, level-0 field-array base). Rebuilt only when that key moves.
    THE HARVEST (self.yards -> self.ylist): rebuilt only when GetCount moves or tier 1
    ran. Caches POINTERS ONLY.
    TIER 2 (the count pass): NOT keyed -- rebuilt on every call, exactly as the cave
    does, re-reading razed/building off the CACHED entries, so a shipyard that
    completes construction or is razed mid-turn moves the divisor in the SAME
    evaluation without any re-harvest.

    `self.yards` is the STRUCTURE REGISTRY, not the yard list -- it may hold SimOther
    entries, and len(self.yards) is TStructureControl.GetCount.

    The three counters are what the staleness tests assert on:
      t2_runs   must track the call count (the pass is unconditional)
      t1_runs   must NOT -- a per-structure term in the tier-1 key is the O(S*flood)
                catastrophe the split exists to prevent
      harvests  must track registry-size changes ONLY, never evaluations
    """

    def __init__(self, levels, yards, mapid=1, day=0, fieldbase=0x1000):
        self.levels, self.yards = levels, yards
        self.mapid, self.day, self.fieldbase = mapid, day, fieldbase
        self.key = None
        self.labels = self.area = None
        self.t1_runs = self.t2_runs = self.harvests = 0
        self.ylist = []
        self.ycount = None
        self.yvalid = False

    def _t1key(self):
        l0 = self.levels[0]
        return (self.mapid, self.day, len(self.levels), l0.W * l0.H, self.fieldbase)

    def _harvest(self, n):
        """Mirrors `harvest`: one registry walk, ClassID filter, capped at MAX_YARDS.
        Not one membership byte is read here."""
        self.ylist = [s for s in self.yards if isinstance(s, SimYard)][:MAX_YARDS]
        self.ycount = n
        self.yvalid = True
        self.harvests += 1

    def ensure(self):
        k = self._t1key()
        if k != self.key:                              # TIER 1 -- keyed
            self.labels, self.area = sim_label(self.levels)
            self.key = k
            self.t1_runs += 1
            self.yvalid = False                        # the heap block may have moved
        n = len(self.yards)                            # the ONE GetCount call
        if (not self.yvalid) or n != self.ycount:
            self._harvest(n)
        self.count = {}                                # TIER 2 -- unconditional
        for s in self.ylist:                           # DIVISOR membership, re-read
            if s.razed or s.building:                  #   off the CACHED entries:
                continue                               #   not razed, not building,
            for r in sim_regions(self.labels, self.levels, s.L, s.x, s.y):
                self.count[r] = self.count.get(r, 0) + 1   # owner NOT tested
        self.t2_runs += 1

    def income(self, target):
        self.ensure()
        if target.razed or target.building or target.owner == 0xFF:  # PAYEE adds owner
            return 0
        g = 0
        for r in sim_regions(self.labels, self.levels, target.L, target.x, target.y):
            n = self.count.get(r, 0)
            if n == 0:
                continue
            g += sim_share(self.area[r], n)
        return g


def sim_pot(area):
    """area div HEXES_PER_GOLD -- the Python-side mirror of the FIRST `div ecx` in
    `entry`. The rate appears here and in the cave source, nowhere else."""
    return area // HEXES_PER_GOLD


def sim_share(area, n):
    """...and the SECOND `div ecx`, by the shipyard count.

    Written as two floors because the cave does two `div ecx`. Do not "simplify" it to
    one: for positive integers floor(floor(a/b)/c) == floor(a/(b*c)) is an identity, so
    a single divide would give the same NUMBERS while quietly destroying the mapping
    between this function and the two instructions verify_cave check 8 inspects."""
    return sim_pot(area) // n


def sim_income(levels, yards, target):
    """One-shot evaluation on a fresh cache -- the stateless view of the rule."""
    return SimEngine(levels, yards).income(target)


def _sea_column(lv, x, y0, n, terr=0x00):
    """A vertical run in one column is connected under both parities (delta (0,1))
    and touches no other column, so it is a body of exactly n hexes."""
    for i in range(n):
        lv.set(x, y0 + i, terr)


def run_sim():
    fails = []
    ran = [0]          # assertions actually EXECUTED, counted at runtime.
                       # Never hard-code this total in a message: five of the check()
                       # call sites sit in loops, so the source-level count and the
                       # executed count are different numbers and drift apart the
                       # moment a loop range changes.

    def check(name, got, want):
        ran[0] += 1
        ok = got == want
        print("  %-58s %-8s %s" % (name, "got %s" % got,
                                   "OK" if ok else "FAIL (want %s)" % want))
        if not ok:
            fails.append(name)

    print("--sim: pure-Python reference of the shipyard income rule")
    print("       rate: 1 gold per %d hexes (HEXES_PER_GOLD); a body under %d hexes "
          "pays nothing\n" % (HEXES_PER_GOLD, HEXES_PER_GOLD))

    # ---- pot/share arithmetic on a single body -------------------------
    # `want` is DERIVED from HEXES_PER_GOLD via sim_share -- never a transcribed
    # literal, so a re-tune is one line and cannot leave a stale expectation behind.
    # The (area, N) pairs are chosen for their remainders, not their answers:
    #   200/1  exact at both steps        200/2  exact pot, exact split
    #   99/2   remainder at BOTH steps    95/3   exact pot, remainder on the split
    # ...plus the blackout case below, which is the one pair whose MEANING moves with
    # the rate: the "pays nothing" threshold is a body smaller than HEXES_PER_GOLD, so
    # it is expressed as HEXES_PER_GOLD-1 rather than pinned to a hex count.
    for area_n, nyards in ((200, 1), (200, 2), (99, 2), (95, 3),
                           (HEXES_PER_GOLD - 1, 1)):
        lv = SimLevel(12, 260)
        _sea_column(lv, 5, 2, area_n)
        # yards sit in column 4, all adjacent to column 5, spread out so they never
        # touch each other's hexes (they only need to touch the same body)
        yards = [SimYard(0, 4, 3 + k * 20) for k in range(nyards)]
        check("area=%d N=%d" % (area_n, nyards),
              sim_income([lv], yards, yards[0]), sim_share(area_n, nyards))
    # ...and the blackout must really be a ZERO, not just "whatever the formula says".
    # sim_share is the formula under test above, so this line asserts the property
    # independently: a body too small to make one gold pays nothing at all.
    check("a body smaller than the rate pays nothing",
          sim_share(HEXES_PER_GOLD - 1, 1), 0)
    check("a body of exactly the rate pays 1", sim_share(HEXES_PER_GOLD, 1), 1)

    # ---- isthmus: one yard between two disjoint bodies -----------------
    lv = SimLevel(14, 260)
    _sea_column(lv, 4, 2, 100)          # body A, 100 hexes
    _sea_column(lv, 6, 2, 200)          # body B, 200 hexes
    y = SimYard(0, 5, 10)               # column 5 touches both, columns 4 and 6 are
    labels, area = sim_label([lv])      # two apart in x so they never connect
    check("isthmus: two distinct bodies seen", len(sim_regions(labels, [lv], 0, 5, 10)), 2)
    check("isthmus 100+200, alone on both -> %d+%d"
          % (sim_pot(100), sim_pot(200)), sim_income([lv], [y], y),
          sim_share(100, 1) + sim_share(200, 1))

    # ---- Q2: an independent shipyard dilutes but collects nothing ------
    lv = SimLevel(12, 260)
    _sea_column(lv, 5, 2, 200)
    owned = SimYard(0, 4, 3, owner=0)
    indep = SimYard(0, 4, 60, owner=0xFF)
    check("200-hex sea, 1 owned + 1 independent -> owned",
          sim_income([lv], [owned, indep], owned), sim_share(200, 2))
    check("200-hex sea, 1 owned + 1 independent -> independent",
          sim_income([lv], [owned, indep], indep), 0)

    # ---- under construction: out of the divisor AND earns nothing ------
    lv = SimLevel(12, 260)
    _sea_column(lv, 5, 2, 200)
    a = SimYard(0, 4, 3)
    b = SimYard(0, 4, 60, building=True)
    check("under-construction yard does not dilute",
          sim_income([lv], [a, b], a), sim_share(200, 1))
    check("under-construction yard earns nothing", sim_income([lv], [a, b], b), 0)

    # ---- razed: same ---------------------------------------------------
    c = SimYard(0, 4, 60, razed=True)
    check("razed yard does not dilute",
          sim_income([lv], [a, c], a), sim_share(200, 1))
    check("razed yard earns nothing", sim_income([lv], [a, c], c), 0)

    # ---- MID-TURN STATE CHANGES MUST MOVE THE DIVISOR IMMEDIATELY ------
    # This is the whole point of the unconditional tier-2 pass. A yard finishing
    # construction does NOT move TStructureControl.GetCount (BuildingDone clears
    # [s+0x24] in place, no registry call), so a GetCount-keyed count[] would keep
    # paying the pre-completion share for the rest of the day: the complete yard AND
    # the new one would each take the WHOLE pot -- twice the pot.
    lv = SimLevel(12, 260)
    _sea_column(lv, 5, 2, 200)                          # 200 hexes
    a = SimYard(0, 4, 3)
    b = SimYard(0, 4, 60, building=True)
    eng = SimEngine([lv], [a, b])
    check("t0: A alone on a pot-%d sea (B still building)" % sim_pot(200),
          eng.income(a), sim_share(200, 1))
    check("t0: B earns nothing while building", eng.income(b), 0)
    b.building = False                                  # completes THIS turn, same day
    check("completion, SAME day: A's share halves at once",
          eng.income(a), sim_share(200, 2))
    check("completion, SAME day: B collects at once",
          eng.income(b), sim_share(200, 2))
    check("completion, SAME day: body pays exactly its pot",
          eng.income(a) + eng.income(b), sim_pot(200))
    check("...and the flood pass did NOT re-run", eng.t1_runs, 1)
    check("...while the count pass ran once per evaluation", eng.t2_runs, 6)
    # completion does not move GetCount, so it must NOT trigger a re-harvest -- the
    # membership bytes are re-read off the cached pointers instead.
    check("...and the shipyard sub-list was harvested exactly once", eng.harvests, 1)

    # razing has the mirror-image lag under a GetCount key; unconditional tier 2
    # closes that too -- the survivor's share rises in the same evaluation.
    lv = SimLevel(12, 260)
    _sea_column(lv, 5, 2, 200)
    a = SimYard(0, 4, 3)
    b = SimYard(0, 4, 60)
    eng = SimEngine([lv], [a, b])
    check("t0: two yards split a pot-%d sea" % sim_pot(200),
          eng.income(a), sim_share(200, 2))
    b.razed = True                                      # razed THIS turn, same day
    check("razing, SAME day: survivor's share rises at once",
          eng.income(a), sim_share(200, 1))
    check("razing, SAME day: razed yard earns nothing", eng.income(b), 0)
    check("...and the flood pass still did NOT re-run", eng.t1_runs, 1)
    check("...nor was the sub-list re-harvested (razing does not move GetCount)",
          eng.harvests, 1)

    # a new day DOES move the tier-1 key, and only then
    eng.day += 1
    eng.income(a)
    check("a day rollover rebuilds the flood pass", eng.t1_runs, 2)

    # ---- MAP-LOAD REGISTRATION STORM -----------------------------------
    # THE regression test for the tier-1 key, and the one the earlier version of this
    # file did not have. The completion/razing scenarios above CANNOT catch a
    # per-structure key term: they hold the yard list FIXED and only flip membership
    # bytes, so GetCount never moves. QA proved that on 2026-08-26 by subclassing
    # SimEngine with `len(self.yards)` in the tier-1 key -- all 35 checks still passed
    # with the catastrophe installed.
    # Here the registry GROWS one entry at a time, exactly as it does at map load,
    # and every yard is evaluated after each registration.
    def storm(engine_cls):
        lv = SimLevel(12, 260)
        _sea_column(lv, 5, 2, 200)                      # 200 hexes
        eng = engine_cls([lv], [])
        evals = 0
        for k in range(6):
            eng.yards.append(SimYard(0, 4, 3 + k * 20))
            for y in eng.yards:
                eng.income(y)
                evals += 1
        return eng, evals

    eng, evals = storm(SimEngine)
    check("storm: 6 registrations produce 21 evaluations", evals, 21)
    check("storm: the FLOOD PASS RAN ONCE across all of them", eng.t1_runs, 1)
    check("storm: the count pass ran once per evaluation", eng.t2_runs, evals)
    check("storm: one harvest per registry change, not per evaluation",
          eng.harvests, 6)
    check("storm: 6 yards on a pot-%d sea each take %d div 6"
          % (sim_pot(200), sim_pot(200)),
          [eng.income(y) for y in eng.yards], [sim_share(200, 6)] * 6)

    # ...and the storm must actually FAIL against the forbidden key. A guard nobody
    # has watched fail is not a guard, so the regression lives in the file.
    class _RegressedEngine(SimEngine):
        """The exact regression the CACHING block forbids -- a per-structure term in
        the TIER-1 key. Never make SimEngine look like this."""
        def _t1key(self):
            l0 = self.levels[0]
            return (self.mapid, self.day, len(self.levels), l0.W * l0.H,
                    self.fieldbase, len(self.yards))

    bad, _ = storm(_RegressedEngine)
    check("storm DETECTS a per-structure tier-1 key (regressed t1_runs > 1)",
          bad.t1_runs > 1, True)
    print("     (regressed engine ran the flood pass %d times; correct engine 1)"
          % bad.t1_runs)

    # ---- the cached shipyard sub-list tracks the registry ---------------
    lv = SimLevel(12, 260)
    _sea_column(lv, 5, 2, 200)
    a = SimYard(0, 4, 3)
    b = SimYard(0, 4, 60)
    eng = SimEngine([lv], [a])
    check("sub-list: A alone on a pot-%d sea" % sim_pot(200),
          eng.income(a), sim_share(200, 1))
    check("sub-list: one harvest so far", eng.harvests, 1)
    eng.yards.append(b)                     # a yard APPEARS -- GetCount moves
    check("sub-list: a new yard is picked up in the same evaluation",
          eng.income(a), sim_share(200, 2))
    check("sub-list: ...via exactly one re-harvest", eng.harvests, 2)
    eng.yards.remove(b)                     # a yard DISAPPEARS -- GetCount moves
    check("sub-list: a removed yard stops diluting at once",
          eng.income(a), sim_share(200, 1))
    check("sub-list: ...via exactly one more re-harvest", eng.harvests, 3)
    # a mid-turn COMPLETION does not move GetCount, so the membership bytes must be
    # re-read off the cached entry or the completion is invisible
    eng.yards.append(SimYard(0, 4, 60, building=True))
    check("sub-list: a building yard neither dilutes nor earns",
          eng.income(a), sim_share(200, 1))
    h = eng.harvests
    eng.yards[-1].building = False
    check("sub-list: completion is seen WITHOUT a re-harvest",
          eng.income(a), sim_share(200, 2))
    check("sub-list: ...and no re-harvest happened", eng.harvests, h)
    # a tier-1 key move invalidates the sub-list even though GetCount is unchanged
    # (the heap block, and therefore yards[], may have been reallocated)
    h = eng.harvests
    eng.mapid += 1
    eng.income(a)
    check("sub-list: a tier-1 key change forces a re-harvest", eng.harvests, h + 1)
    # non-shipyard registry entries never reach the sub-list
    eng2 = SimEngine([lv], [SimOther(), a, SimOther()])
    check("sub-list: non-shipyards are filtered out of the harvest",
          eng2.income(a), sim_share(200, 1))
    check("sub-list: ...so the sub-list holds only the yard", len(eng2.ylist), 1)
    # the cap truncates rather than overrunning
    many = [SimYard(0, 4, 3) for _ in range(MAX_YARDS + 5)]
    eng3 = SimEngine([lv], many)
    eng3.ensure()
    check("sub-list: the harvest stops at MAX_YARDS", len(eng3.ylist), MAX_YARDS)

    # ---- levels never merge -------------------------------------------
    l0 = SimLevel(12, 260)
    l1 = SimLevel(12, 260)
    _sea_column(l0, 5, 2, 200)          # surface sea, 200
    _sea_column(l1, 5, 2, 100)          # underground sea, 100, same (x,y)
    y0 = SimYard(0, 4, 3)
    y1 = SimYard(1, 4, 3)
    check("level 0 yard sees only the level-0 sea",
          sim_income([l0, l1], [y0, y1], y0), sim_share(200, 1))
    check("level 1 yard sees only the level-1 sea",
          sim_income([l0, l1], [y0, y1], y1), sim_share(100, 1))

    # ---- Ice(6) splits a body; a bridge overlay does not ---------------
    lv = SimLevel(12, 120)
    _sea_column(lv, 5, 2, 100)
    y = SimYard(0, 4, 3)
    check("unsplit 100-hex sea", sim_income([lv], [y], y), sim_share(100, 1))
    lv.set(5, 52, 6)                    # Ice at the 51st hex of the run
    labels, area = sim_label([lv])
    check("Ice(6) splits the body into two", len(area) - 1, 2)
    check("yard now sees only the 50-hex half",
          sim_income([lv], [y], y), sim_share(50, 1))
    # a bridge is an OVERLAY byte at [field+0x15]; terrain stays 0x00 and this cave
    # never reads +0x15 (asserted on the disassembly in verify_cave), so:
    lv2 = SimLevel(12, 120)
    _sea_column(lv2, 5, 2, 100)
    check("bridge overlay leaves the body intact",
          sim_income([lv2], [y], y), sim_share(100, 1))

    # ---- CaveWater 0x0A counts as water --------------------------------
    lv = SimLevel(12, 120)
    _sea_column(lv, 5, 2, 100, terr=0x0A)
    check("CaveWater 0x0A is water", sim_income([lv], [SimYard(0, 4, 3)],
                                                SimYard(0, 4, 3)), sim_share(100, 1))
    lv = SimLevel(12, 120)
    _sea_column(lv, 5, 2, 100, terr=0x0E)      # SKY on this install
    check("terrain 0x0E (SKY) is NOT water", sim_income([lv], [SimYard(0, 4, 3)],
                                                        SimYard(0, 4, 3)), 0)

    # ---- the <=4 slot dedupe over ALL 2^7 centre+ring configurations ---
    worst = 0
    for cx in (4, 5):                                  # both x parities
        for mask in range(128):
            lv = SimLevel(11, 11)
            cy = 5
            ring = (DELTAS_ODD if (cx & 1) else DELTAS_EVEN)[:6]
            cells = [(0, 0)] + list(ring)
            for bit, (dx, dy) in enumerate(cells):
                if mask & (1 << bit):
                    lv.set(cx + dx, cy + dy, 0x00)
            labels, _ = sim_label([lv])
            n = len(sim_regions(labels, [lv], 0, cx, cy))
            worst = max(worst, n)
            # the dedupe array is 4 slots; if a real configuration ever needed a 5th
            # the cave would silently drop it
            if n > 4:
                fails.append("dedupe overflow parity=%d mask=%d" % (cx & 1, mask))
    check("max distinct regions over all 2^7 centre+ring configs (<=4)", worst <= 4, True)
    print("     (measured maximum: %d)" % worst)

    # ---- the built-in delta table still matches the engine's -----------
    # dump_deltas() sys.exit()s on a mismatch, so this line is a real assertion; it is
    # deliberately OUTSIDE the check() tally because it has no got/want pair. That is
    # why the printed check count is one lower than the number of OK lines.
    dump_deltas()
    print("  %-58s %-8s OK" % ("HSEPack delta tables match the embedded copy", ""))

    print("\n--sim: %d checks, %s"
          % (ran[0], "ALL PASS" if not fails
             else "%d FAILURE(S): %s" % (len(fails), ", ".join(fails))))
    return 1 if fails else 0


# ============================================================================
# .reloc
# ============================================================================
def reloc_check(data):
    base, secs = pe_sections(data)
    reloc = None
    for name, vaddr, vsize, praw, sraw in secs:
        if name == ".reloc":
            reloc = (vaddr, vsize, praw, sraw)
    if not reloc:
        sys.exit("ABORT: no .reloc section")
    vaddr, vsize, praw, sraw = reloc
    rd = data[praw:praw + vsize]
    slot_has_reloc = False
    i = 0
    while i + 8 <= len(rd):
        page, size = struct.unpack_from("<II", rd, i)
        if size < 8:
            break
        for j in range(i + 8, min(i + size, len(rd)), 2):
            e = struct.unpack_from("<H", rd, j)[0]
            if e >> 12 != 3:
                continue
            va = base + page + (e & 0xFFF)
            if CAVE_VA <= va < CAVE_VA + CAVE_LIMIT:
                sys.exit("ABORT: .reloc entry at 0x%08X is inside the cave zone" % va)
            if va == VMT_GETINCOME:
                slot_has_reloc = True
        i += size
    if not slot_has_reloc:
        sys.exit("ABORT: VMT slot 0x%08X has lost its .reloc entry -- the DPL rebases "
                 "and the hook would point at a stale VA" % VMT_GETINCOME)


# ============================================================================
# live-file checks
# ============================================================================
def check_untouched(data):
    for va, want, label in UNTOUCHED:
        got = struct.unpack_from("<I", data, off(va))[0]
        if got != want:
            sys.exit("ABORT: %s @0x%08X is 0x%08X, expected 0x%08X -- refusing to "
                     "touch this VMT." % (label, va, got, want))


def check_live_edits(data):
    """The four undocumented live-vs-vanilla edits. Verify against LIVE, never vanilla."""
    for va, live, vanilla, label in LIVE_EDITS:
        got = bytes(data[off(va):off(va) + len(live)])
        if got == live:
            continue
        if got == vanilla:
            sys.exit("ABORT: 0x%08X (%s) holds the VANILLA bytes %s, not the live %s.\n"
                     "  This install is not the one this script was measured against."
                     % (va, label, got.hex().upper(), live.hex().upper()))
        sys.exit("ABORT: 0x%08X (%s) is %s -- neither live nor vanilla."
                 % (va, label, got.hex().upper()))


def kill_aow():
    # ⚠ SCRATCH GUARD (2026-09-03): AOW_GAME_DIR set => not the real install; never kill
    # the user's running game. See the note in build_minddecay_oos.py.
    if os.environ.get("AOW_GAME_DIR"):
        return
    ps = ("Get-Process | Where-Object { $_.ProcessName -match "
          "'^(AoW|AoWCompat|AoWDevEd|AoWEd)$' } | Stop-Process -Force")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=30)
    except Exception:
        pass


def disasm(b, va, title):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        print("   (capstone not installed -- cannot disassemble)")
        return
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    print("   --- %s @0x%08X (%d B) ---" % (title, va, len(b)))
    for ins in md.disasm(b, va):
        print("   %08X  %-14s %-7s %s"
              % (ins.address, ins.bytes.hex().upper(), ins.mnemonic, ins.op_str))


# ============================================================================
def main():
    ap = argparse.ArgumentParser(
        description="Shipyard gold income from contiguous adjacent water "
                    "(AoWEPACK.dpl only)")
    ap.add_argument("--apply", action="store_true", help="write (rewrites in place)")
    ap.add_argument("--undo", action="store_true",
                    help="surgical: restore the VMT slot, zero the cave, no backup")
    ap.add_argument("--dis", "--show", action="store_true", dest="dis",
                    help="full capstone listing of the cave")
    ap.add_argument("--sim", action="store_true",
                    help="pure-Python reference of the rule over synthetic maps")
    args = ap.parse_args()

    if args.sim:
        sys.exit(run_sim())

    if not os.path.isfile(DLL):
        sys.exit("ERROR: not found: %s" % DLL)
    data = bytearray(open(DLL, "rb").read())
    cave = build()

    used = cave["_end"] - CAVE_VA
    print("build_shipyard_income   water={0x00,0x0A}   cave 0x%08X..0x%08X "
          "(%d B of %d)" % (CAVE_VA, cave["_end"] - 1, used, CAVE_LIMIT))
    for k in cave["_order"]:
        va, b = cave[k]
        print("    %-11s 0x%08X  %4d B" % (k, va, len(b)))
    print("    header      0x%08X  %4d B (BSS page slack, window 0x%X)"
          % (HDR, HDR_END - HDR, HDR_WINDOW))

    if args.dis:
        print()
        va, b = cave["table"]
        print("   --- table @0x%08X (%d B)  parity*0x40 + side*8 -> dx,dy ---"
              % (va, len(b)))
        for p, nm in ((0, "even x"), (1, "odd x")):
            row = []
            for s in range(8):
                dx, dy = struct.unpack_from("<ii", b, p * 0x40 + s * 8)
                row.append("(%d,%d)" % (dx, dy))
            print("       %-7s %s" % (nm, " ".join(row)))
        for k in cave["_order"][1:]:
            print()
            va, b = cave[k]
            disasm(b, va, k)
        print()

    reloc_check(data)
    check_untouched(data)
    check_live_edits(data)

    def cur(va, n):
        return bytes(data[off(va):off(va) + n])

    slot = struct.unpack_from("<I", data, off(VMT_GETINCOME))[0]
    entry_va = cave["entry"][0]
    slot_orig = slot == VMT_ORIG
    slot_ours = CAVE_VA <= slot < CAVE_VA + CAVE_LIMIT
    if not (slot_orig or slot_ours):
        sys.exit("ABORT: VMT+0x1F4 @0x%08X holds 0x%08X -- neither the vanilla "
                 "0x%08X nor an address inside this script's cave reservation. "
                 "Inspect before writing." % (VMT_GETINCOME, slot, VMT_ORIG))

    zone = cur(CAVE_VA, CAVE_LIMIT)
    payload = bytearray(CAVE_LIMIT)
    for k in cave["_order"]:
        va, b = cave[k]
        payload[va - CAVE_VA:va - CAVE_VA + len(b)] = b
    payload = bytes(payload)
    zone_zero = zone == b"\x00" * CAVE_LIMIT
    zone_ours = zone == payload

    fresh = slot_orig and zone_zero
    if slot_orig and not zone_zero:
        sys.exit("ABORT: the VMT slot is vanilla but cave zone 0x%08X is NOT zero -- "
                 "someone else owns it. Refusing to write." % CAVE_VA)

    # ---- report / dry run ----
    if not args.apply and not args.undo:
        print()
        print("  vmt+0x1F4   0x%08X  0x%08X  %s"
              % (VMT_GETINCOME, slot,
                 "vanilla (not applied)" if slot_orig else
                 ("-> cave entry 0x%08X" % entry_va if slot == entry_va
                  else "-> 0x%08X inside our cave (stale layout)" % slot)))
        for va, want, label in UNTOUCHED:
            print("  untouched   0x%08X  0x%08X  OK  %s" % (va, want, label))
        print("  cave zone   0x%08X  %s" % (CAVE_VA,
              "all zero" if zone_zero else ("matches this build" if zone_ours
                                            else "differs from this build")))
        ok = (slot == entry_va) and zone_ours
        print("\nSTATUS: %s" % ("APPLIED and up to date" if ok else
                                ("NOT applied -- run --apply" if fresh else
                                 "applied but STALE (cave differs) -- run --apply")))
        if not ok:
            print("DRY RUN -- re-run with --apply to commit.")
        return

    # ---- undo ----
    if args.undo:
        if slot_orig and zone_zero:
            print("Not applied -- nothing to undo.")
            return
        if not (slot_orig or slot_ours):
            sys.exit("ABORT undo: foreign VMT slot")
        # *** Zero ONLY the bytes this build emitted, and only from a zone this build
        # RECOGNISES. What this guard protects against is OUR OWN LAYOUT DRIFT: the
        # installed cave was emitted by a different revision of this script, so
        # `used` -- the length computed from the CURRENT build -- does not describe
        # it. Zeroing `used` bytes of a foreign layout either leaves a tail of live
        # code behind or wipes bytes this script cannot prove it wrote. Neither is
        # acceptable, so drift aborts and the remedy is `--apply` (rewrites the cave
        # in place, re-synchronising the layout) and then `--undo`.
        #
        # This is NOT co-tenant protection, and must not be described as such: --apply
        # writes the full 0x1000 reservation (payload + zero fill), so anything
        # sharing the unused tail is destroyed by the very command this abort tells
        # you to run. The reservation is owned outright -- see CAVE_LIMIT.
        if not (zone_zero or zone_ours):
            sys.exit("ABORT undo: cave zone 0x%08X was not emitted by this revision "
                     "of the script (it is neither zero nor a byte-match for the "
                     "current build's payload), so this build's %d-byte length does "
                     "not describe it. Refusing to zero a layout it cannot account "
                     "for. Run --apply to re-synchronise the cave, then --undo."
                     % (CAVE_VA, used))
        struct.pack_into("<I", data, off(VMT_GETINCOME), VMT_ORIG)
        data[off(CAVE_VA):off(CAVE_VA) + used] = b"\x00" * used
        # everything past our emitted length must already have been zero and stay so
        rest = bytes(data[off(CAVE_VA) + used:off(CAVE_VA) + CAVE_LIMIT])
        if rest != b"\x00" * len(rest):
            sys.exit("BUG: undo left non-zero bytes past 0x%08X -- not writing."
                     % cave["_end"])
        # build_los_terrain owns 0x55820000..0x558207FF -- prove we did not touch it
        keep = bytes(data[off(0x55820000):off(0x55820000) + 0x800])
        orig_keep = open(DLL, "rb").read()[off(0x55820000):off(0x55820000) + 0x800]
        if keep != orig_keep:
            sys.exit("BUG: undo would modify build_los_terrain's cave -- not writing.")
        check_untouched(data)
        check_live_edits(data)
        kill_aow()
        try:
            open(DLL, "wb").write(data)
        except PermissionError:
            sys.exit("ERROR: %s is locked (AoW/AoWCompat/AoWDevEd/AoWEd still "
                     "running?)" % os.path.basename(DLL))
        print("UNDO: VMT+0x1F4 @0x%08X -> 0x%08X; zeroed 0x%08X..0x%08X (%d B, "
              "exactly this build's emitted length; the rest of the 0x%X reservation "
              "was already zero and was left unwritten). No backup touched."
              % (VMT_GETINCOME, VMT_ORIG, CAVE_VA, CAVE_VA + used - 1, used,
                 CAVE_LIMIT))
        return

    # ---- apply (rewrites in place; never needs a revert) ----
    if slot == entry_va and zone_ours:
        print("\nAlready applied and up to date -- nothing to do.")
        return

    if fresh:
        os.makedirs(BACKUP_DIR, exist_ok=True)
    if fresh and not os.path.exists(BAK):
        # Backup ONLY from a positively-verified ORIGINAL state: the slot holds the
        # vanilla 0x557BE500 AND the cave zone is all zero. Never minted on the undo
        # path or on a re-tune -- both of those would snapshot our own output.
        shutil.copy2(DLL, BAK)
        print("backup -> %s" % os.path.basename(BAK))
    elif not fresh:
        print("re-tune: rewriting the cave in place (no backup taken, none needed)")

    data[off(CAVE_VA):off(CAVE_VA) + CAVE_LIMIT] = payload
    struct.pack_into("<I", data, off(VMT_GETINCOME), entry_va)

    # the zone tail beyond the cave must still be zero
    tail = bytes(data[off(cave["_end"]):off(CAVE_VA) + CAVE_LIMIT])
    if tail != b"\x00" * len(tail):
        sys.exit("BUG: the cave-zone tail is not zero -- not writing.")
    check_untouched(data)
    check_live_edits(data)

    kill_aow()
    try:
        open(DLL, "wb").write(data)
    except PermissionError:
        sys.exit("ERROR: %s is locked. Kill AoW/AoWCompat/AoWDevEd/AoWEd and retry."
                 % os.path.basename(DLL))
    print("APPLIED (%s): VMT+0x1F4 @0x%08X -> 0x%08X, cave %d B."
          % ("fresh" if fresh else "re-tune", VMT_GETINCOME, entry_va, used))
    print("Note: --apply wrote the full 0x%X reservation (%d B of payload + zero "
          "fill); this script owns 0x%08X..0x%08X outright."
          % (CAVE_LIMIT, used, CAVE_VA, CAVE_VA + CAVE_LIMIT - 1))
    print("Revert with --undo (surgical -- restores the slot and zeroes exactly these "
          "%d B, which is all this build wrote that is not already zero)." % used)
    print("Status: applied, untested -- needs the user's in-game test.")


if __name__ == "__main__":
    main()
