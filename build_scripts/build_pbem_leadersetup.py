#!/usr/bin/env python3
r"""
AoW1 mod -- "pbemleader": PBEM turn-1 leader customisation (skill points + spheres).

FULL ANALYSIS: Modding Resources/Zig notes/07-ui.md  section 10 (stage 1 10.5, stage 2 10.6).

    stage 1  the window opens over the map, saves nothing   CONFIRMED WORKING 2026-09-24
    stage 2  the choices stick                               APPLIED, UNTESTED 2026-09-24

On a PBEM game's day 1, when a human player's turn starts on their own machine, vanilla's
leader-customisation window (`TLeaderSetupWin`) opens over the strategic map in mode 6
(`lsmSettings|lsmSpheres`: the skill-point page, then the sphere page).  On Finish, stage 2
copies the window's leader back into the live one, sends the in-game post-upgrade
notifications, runs the (deferred) day-1 spell grant from the NEW spheres, and lets the event
queue continue to the research prompt.  The Available list on the skill-point page is the
per-race level-up offer roll with every chance doubled, capped at 100%.

Owner rulings (07-ui.md section 10): full rebuild (vanilla Down/Remove/Clear/Default kept);
ability menu = the doubled per-race roll; skill-point page + sphere page only.

================================================================================
THE SHARED PREDICATE -- build_scripts/pbemday1.py, one definition, four sites
================================================================================
    map[+0x13A] == 2  &&  map[+0x174] == 1  &&  player[+0xA7] == 0  &&  player[+0xD4] != 0

    C_RAISE  (here)                        raises the window
    C_GATE   (here)                        defers the day-1 grant
    C_APPLY  (here)                        runs the deferred grant
    C_TURN1  (build_hero_turn1_upgrade.py) withholds the leader's artificial level-up lag
                                           (+ hero == player[+0xD4])

ONE PLAYER, FOUR SITES.  All four resolve the same TPlayer, list[bl], where bl is the player
whose TTurnPlayerControl.NewTurn is running:
  * C_RAISE: GetPlayers([map+0x140], movsx bl), in that NewTurn's day-1 block.
  * C_GATE: [magic+0x10].  TPlayerMagicControl.MsgProc (0x5577D278) runs NewTurn only when
    [[magic+0x10]+0xA6] == the message's player, which TPlayerControl.NewTurn sets to movsx bl
    (0x55755540); [player+0xA6] is its list index (SetNumberOfPlayers 0x557546E2).
  * C_TURN1: GetPlayers([map+0x140], movsx [hero+0x24]); THero.NewTurn only reaches it when
    [hero+0x24] == bl (0x55787FDC).
  * C_APPLY: G_PLAYER = GetPlayers(movsx [event+0x10]), and C_RAISE writes bl there.
C_GATE and C_TURN1 run inside TPlayerControl.NewTurn (0x557569DA), C_RAISE later in the same
TTurnPlayerControl.NewTurn; C_APPLY later the same day with input locked.  None of the four
predicate fields can change in between.  In PBEM map[+0x139] = 1 (DefaultStartMap 0x55756F45),
so the day-1 block adds no seated-player test, and TTurnPlayerControl.NewTurn runs for a PBEM
human only on the recipient's machine (TPBEMPlayerControl.NewTurn 0x55757E6E).

================================================================================
STAGE 1 -- the window (unchanged in behaviour; re-tuned in place for stage 2)
================================================================================
AoWEPACK.dpl (PIC; the package never loads at its preferred base):
  0x55756B94  5 B E9 over `movsx edi,bl ; mov edx,edi` in TTurnPlayerControl.NewTurn's day-1
              block -> C_RAISE.  Inbound sweep: one candidate, 0x55756B27, is the imm32 of
              `mov eax,0x55756C78` (re-proved every run).  No .reloc.
  C_RAISE     predicate -> TPlayerMagicEventLog.Create (VMT derived PIC: call $+5 / pop /
              add 0x5570AD0C - anchor; [0x5570ACCC] is its vmtSelfPtr) ; mode [+0x18] := 3 ;
              player [+0x10] := bl (stage 2) ; TriggerExecuteEventLog ([map]+0x12C) ; Release
              -- vanilla's own mode-2 raise at 0x55756BEA.
  0x5577C3FF  1 B 4B -> 47: TPlayerMagicEventLog.Execute treats modes >= 3 like mode 2 (only
              the re-execution path; every vanilla creator uses modes 0/1/2).
AoWz.exe + AoWzCompat.exe (fixed base, absolutes fine):
  0x0044F183  the rel32 of `jmp 0x44F51E` (TheMapExecuteEventLog, modes >= 3) -> C_SHOW.
  C_SHOW      mode 3 only; stores event (AddRef) + completion TMethod; ctrl =
              TLeaderSetupControl.Create; [ctrl+0x0C].Assign(leader); [ctrl+0x14].Assign(
              [ctrl+0x0C]); mode 6; OnDone = C_DONE; hides the 9 other TitleWin panels;
              TitleWin forced Modal (+0x104) and shown; Setup; SetOverPri(0x31); Release.
              Stage 2: the player is the EVENT's ([event+0x10]), stored in G_PLAYER.
  C_DONE      SetOverPri(0); TitleWin hidden, Modal restored; panels' +0x75 restored by byte
              write; stage 2: C_APPLY; then the callback, fired as the spellbook does.

  The 9 other TitleWin panels (every exe DFM component whose AOWWindow is TitleWin; the set
  is re-derived from the DFMs and asserted equal on every run; each CreateForm site and
  published field is checked):
        TTitleWindow.TitlePnl    0x45A28C +0x48    TTitleWindow.SplashPnl  0x45A28C +0x4C
        TMultiWindow.MultiPnl    0x45A598 +0x54    TScenSetup.ScenSetupPnl 0x45A30C +0xA0
        TWorldMap.WorldPnl       0x45A174 +0x4C    TCampaignJoinDlg.CharGenPnl 0x45A100 +0x44
        TSelFactionWin.FactionPnl 0x45A230 +0x44   TPyreScreen.DeadPnl     0x45A2F0 +0x44
        TResultsWin.ResultsPnl   0x45A20C +0x9C    (TLeaderSetupWin.LeaderPnl +0x2CC is shown)
  Restore is a byte write, not SetVisible(True): TAOWPanel.SetVisible fires OnShow and
  ResultsPnl has one.  Modal = TAOWWindow field +0x104 (RTTI get = set = field), read on every
  input event.  Finish's TSetupEvents 0x41468C call is safe: [[[0x45A454]]+0x48] is a DFM
  component created at startup.

================================================================================
STAGE 2 -- PART 1: COPY-BACK (C_APPLY, AoWEPACK.dpl, PIC)
================================================================================
C_DONE calls C_APPLY only when [ctrl+0x1C] == 2 (lssDone), before firing the completion
callback, through the documented cross-module rebase delta (the party-random-generator idiom):

    esi = [0x45DF7C]                  ; runtime &AoWE.AoWHSMap (an imported variable)
    esi = esi - 0x558FA040 + C_APPLY  ; AoWEPACK.dpl's rebase delta + C_APPLY's preferred VA
    C_APPLY(EAX = ctrl, EDX = G_PLAYER, ECX = map, [esp+4] = AoWEngine) ; ret 4

so C_APPLY needs no absolute operand (the TArmy VMT is derived PIC like C_RAISE's).
    SynchroniseBegin(map) ... SynchroniseEnd(map) around everything -- the bracket
      TPBEMPlayerControl uses in its own UI callbacks (0x55758009); they inc/dec [map+0x234],
      and GetSynchronised (0x55775608) returns true while it is non-zero, which is what
      TAoWHSMap.Random and AddEvent assert.
    1. the copy-back, exactly TSetupControl.SetupMap's (0x557E0CAB):
         UpdateFromLibraryBegin(live) ; live.Assign(ctrl[+0x14], ECX = AoWEngine) (vmt +0x3C) ;
         UpdateFromLibraryEnd(live).  ctrl[+0x14] holds the window's leader: Finish calls
         0x415A94 first, which Assigns [dlg+0x2E4] into it.  Under the library bit
         THero.ReadWrite keeps [hero+0x24] and skips the item/inventory objects.
    2. THeroUpgradeTE.Execute's tail (0x557854DB, live): if [leader+4] IsClass TArmy ->
         TArmy.UpdateFormation (the Leadership aura refresh build_leadership_aura.py added);
         [leader+0x54] (upgrade_pending) := 0.  Its stat setters are plain field writes and it
         calls nothing else, so there is no further "Changed" to send.
    3. the deferred day-1 grant, under exactly C_GATE's conditions (predicate, [player+0xA6]
         != 0, and the [map+0x11A] == 1 preseed test): ESI = player[+0x54] ; call 0x5580EE30.

================================================================================
STAGE 2 -- PART 2: GRANT DEFERRAL (C_GATE, AoWEPACK.dpl)
================================================================================
0x5577CC5C, 22 B -> E9 C_GATE + 17 nop.  The displaced bytes are vanilla's last two grant
guards in TPlayerMagicControl.NewTurn ([map+0x11A] == 1 and a preseeded [magic+0x30]),
replayed exactly; the predicate follows them, so the grant is deferred precisely when it
would otherwise run.  Deferred -> 0x5577CD4A; otherwise -> 0x5577CC72.  No .reloc in the
run (the entry at 0x5577CC58 ends at 0x5577CC5B), no inbound branch.

THE GRANT ROUTINE IS build_tierresearch_dll.py's cave_day1, RE-TUNED IN PLACE TO v2 (a
callable routine: `call` at 0x5577CC72, `ret` tail, `jmp 0x5577CD4A` at 0x5577CC79).  Chosen
over a chain from here because a jmp-exit cave can only be "called" through a synthetic
return frame, and over a second copy of the grant here because a copy would drift silently.
This script pins the routine's bytes (TR_DAY1_SHA) and the two v2 sites on every run and
refuses --apply otherwise.

ROLL -- P1 SYNCED, kept (12-re-toolchain.md 4.10).  Q1: the grant writes replicated state (the
researched-spell list) -> not P3.  Q2: it is not re-evaluated -- it runs once per player per
game and is saved -> Q3/Q4: AoWEPACK.dpl; C_APPLY draws nothing itself, the grant draws
TAoWHSMap.Random, and the roll's subject is replicated game state -> P1.  Moving the draw from
TPlayerMagicControl.NewTurn to C_APPLY on the same machine, later in the same turn, changes
only its position in the synced stream; in PBEM exactly one machine plays the turn and the
result travels in the file, so no peer has to reproduce the order.  The "Invalid AoWHSMap.Random
use" dialog's only path is GetSynchronised == 0, excluded by the Synchronise bracket.  Bit 3
of [map+0x3C] is not touched.  rng_audit.py --owners: 24 modded sites before and after; the
grant's draw 0x5580EE76 is attributed to both scripts.

================================================================================
STAGE 2 -- PART 3: LEVEL-UP GUARD (build_hero_turn1_upgrade.py v3)
================================================================================
C_TURN1 (0x5584B000) skips the level-cache decrement for a hero that is its human player's
leader in a PBEM game on day 1 (pbemday1 predicate + hero == player[+0xD4]).  RE-TUNED IN
PLACE in that script rather than chained from here: a chain would retarget that script's own
`call` at 0x55787FE7 and break its --undo.  This script accepts that cave only fully v3 or
fully absent.

================================================================================
STAGE 2 -- PART 4: OFFER ROLL (C_OFFER, AoWz.exe + AoWzCompat.exe)
================================================================================
0x004161C9, 6 B (`mov edx,[esi+0x2E4]`) -> E9 C_OFFER + nop, in TLeaderSetupWin's available
loop after the mask test (je 0x416251 at 0x4161AF) and before CanExpand (0x4161D1).  EAX =
the TAbility, ESI = the window.  Accept -> replay + 0x4161CF; reject -> 0x416251.
  * Only while our PBEM window is open (G_EVENT != 0).  ⚠ ASSUMPTION, not an owner ruling:
    the pre-game "Customize leaders" screen (hotseat, network) keeps vanilla's full menu.
  * P4 DERIVED HASH, build_heroskill_race.py's cave_fill hash byte for byte: rngstd basis,
    salt [[0x45DF7C]]+0x22C (nil-guarded), [hero+0x18], movzx [hero+0x4C], ability id
    [ability+0xC], fmix32, range_n(100).  hero = the window's leader [dlg+0x2E4] (it carries
    the live leader's +0x18 / +0x4C -- QA 2026-09-23).  Selection test: Q2 yes (the list is
    rebuilt on every Add/Remove, and reopening the incoming PBEM file must not re-roll), Q2b
    no (CanExpand drops owned abilities, so the set shrinks) -> P4.  In an exe P1 is
    unavailable anyway.
  * Row = min(race [[hero+0x40]+0x20], RACELESS_ROW) exactly as cave_fill; ids >= 0x100, a
    nil hero and a nil chassis fail open.  Offer iff u < min(2 * pct, 100), pct from the SAME
    baked table, located through build_heroskill_race.py's own state() (its pattern search +
    table checksum) on every run -- nothing about the table is hard-coded here.
  * The hash bytes are rngstd's verbatim; HSR._assert_rngstd_shape checks them.
    rng_audit.py --hash lists the new site at 0x0062C301.

================================================================================
LAYOUT, RESERVATIONS, RE-TUNE, UNDO
================================================================================
AoWEPACK.dpl  EXCLUSIVE 0x5584C000..0x5584C3FF (stage 1: ..0x5584C0FF; grown 2026-09-24, the
              growth zone proved zero by the known-body hash).  Fixed entries: C_RAISE
              0x5584C000, C_GATE 0x5584C100, C_APPLY 0x5584C180 (the exe calls this constant).
exes          EXCLUSIVE 0x0062C000..0x0062C3FF.  Globals G_EVENT/G_CODE/G_DATA/G_MODAL at
              0x0062C000, C_SHOW 0x0062C010 (fixed), then C_DONE, C_PANEL, C_OFFER, the panel
              table, G_VIS, G_PLAYER, 16-aligned; addresses printed by the dry run.
Re-tune: --apply rewrites a span in place only if it holds a KNOWN earlier body of this
script (EXE_KNOWN_BODIES / DLL_KNOWN_BODIES, sha256 of the non-zero prefix) and every site is
vanilla, current, or an E9 into our own span.  No backup is minted from a patched file.
--undo: restores all five sites, zeroes exactly the emitted bodies.

⚠ UNDO ORDER / COUPLINGS
  * This script's --undo first, before any change to build_tierresearch_dll.py's cave_day1:
    C_APPLY CALLS 0x5580EE30.  That script has no --undo; its v2 is behaviour-identical for
    everyone else, so leave it installed.
  * build_hero_turn1_upgrade.py --undo may run at any time (it removes the guard with the rest
    of that feature; with no artificial lag the leader gets no turn-1 prompt either way).
  * build_heroskill_race.py: C_OFFER reads its table and copies its hash; a re-bake of
    heroskill_races.json changes both dialogs at once, intended.  Undoing it makes this
    script's checks abort until it is re-applied.
  * The DLL half must never ship without the exe half: a patched AoWEPACK.dpl under an
    unpatched exe routes every mode-3 event to vanilla's `jmp 0x44F51E`, which never fires
    the completion callback -- the event queue stalls on every PBEM day 1.
  * C_SHOW stores G_EVENT and AddRefs before Assign/Setup; an exception inside either would
    leave the queue locked behind the backdrop.  G_EVENT must be set before Setup, because
    C_OFFER keys on it while Setup fills the list.  Not addressed.
  * PBEM only: C_APPLY mutates state without a token.

================================================================================
NOT VERIFIABLE WITHOUT THE GAME
================================================================================
  * Whether the live leader, its army and its items are intact after the copy-back.
  * Whether UpdateFormation is the only refresh the map needs (morale caches, panels).
  * A save made between NewTurn and the window (no autosave in PBEM, input locked by the
    earlier dialogs) would carry a deferred grant that never runs.

================================================================================
USAGE
================================================================================
    python build_scripts/build_pbem_leadersetup.py           # verify + disassemble, writes nothing
    python build_scripts/build_pbem_leadersetup.py --apply   # patch all three files (re-tunes)
    python build_scripts/build_pbem_leadersetup.py --undo    # surgical: 5 sites, zero both bodies
    python build_scripts/build_pbem_leadersetup.py --dis     # disassembly only (--show alias)

Needs `pip install capstone keystone-engine`.
"""
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True          # a .pyc embeds the absolute source path -- never mint one

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                               # noqa: E402
import pbemday1                                             # noqa: E402  the shared predicate
import build_heroskill_race as HSR                          # noqa: E402  offer table + hash shape
import rngstd                                               # noqa: E402

BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: never the game root
FEATURE = "pbemleader"
DLL_NAME = "AoWEPACK.dpl"

# ================================================================ AoWEPACK.dpl ==
D_HOOK = 0x55756B94              # movsx edi,bl ; mov edx,edi
D_HOOK_ORIG = bytes.fromhex("0fbefb8bd7")
D_RESUME = 0x55756B99
D_EXEC = 0x5577C3FE              # TPlayerMagicEventLog.Execute: jmp 0x5577C44B -> 0x5577C447
D_EXEC_ORIG = bytes.fromhex("eb4b")
D_EXEC_NEW = bytes.fromhex("eb47")

F_GETPLAYERS = 0x557544D0        # AoWE.TPlayerList.GetPlayers  EAX=list EDX=index -> EAX=player
F_PMEL_CREATE = 0x5577C304       # AoWE.TPlayerMagicEventLog.Create  EAX=VMT DL=alloc ECX=0
PMEL_CLASSREF = 0x5570ACCC       # vmtSelfPtr cell, holds the VMT (relocated)
PMEL_VMT = 0x5570AD0C

MAP_PLAYERS = 0x140
PL_LEADER = pbemday1.PL_LEADER
EV_MODE = 0x18
EV_PLAYER = 0x10                 # TEventLog player index byte (TEventLog.Create 0x557FD3D1)
MODE_LEADER = 3
V_TRIGGER_EVLOG = 0x12C          # TAoWHSMap.TriggerExecuteEventLog
V_ADDREF, V_RELEASE = 0x28, 0x2C

# ---- stage 2: the grant gate, C_APPLY ---------------------------------------------------
D_GATE = 0x5577CC5C              # TPlayerMagicControl.NewTurn: the [map+0x11A] / preseed tests
D_GATE_ORIG = bytes.fromhex("80b81a01000001" "750d" "8b4630" "83780800" "0f85d8000000")  # 22 B
D_GATE_LEN = 22
GRANT_ENTRY = 0x5577CC72         # build_tierresearch_dll.py v2: `call cave_day1`
GRANT_SKIP = 0x5577CD4A          # where the grant returns to (and vanilla's skip target)
TR_DAY1 = 0x5580EE30             # build_tierresearch_dll.py cave_day1 v2: a callable routine
TR_DAY1_LEN = 0xB6
TR_BACK = 0x5577CC79             # v2 return path `jmp 0x5577CD4A`

F_SYNC_BEGIN = 0x557755F8        # TAoWHSMap.SynchroniseBegin   inc [map+0x234]
F_SYNC_END = 0x55775600          # TAoWHSMap.SynchroniseEnd     dec [map+0x234]
F_UFL_BEGIN = 0x557869E4         # THero.UpdateFromLibraryBegin sets [hero+0x5D] bit 0
F_UFL_END = 0x557869F8           # THero.UpdateFromLibraryEnd
F_ISCLASS = 0x557010C0           # thunk -> VCL30 System.@IsClass  EAX=obj EDX=class -> AL
F_UPDATEFORMATION = 0x5578D034   # AoWE.TArmy.UpdateFormation  EAX=army
TARMY_CLASSREF = 0x557130AC      # vmtSelfPtr cell of TArmy (read by build_leadership_aura.py)
TARMY_VMT = 0x557130EC
HERO_OWNER_OBJ = 0x04            # TEObject owner container (TArmy while on the map)
HERO_UPGRADE_PENDING = 0x54
PL_INDEX = 0xA6
PL_MAGIC = 0x54                  # TPlayerMagicControl
MAGIC_KNOWN = 0x30               # TIntegerList of researched spells
MAP_MODE_11A = 0x11A
LSC_STATUS = 0x1C
LSS_DONE = 2

D_CAVE = 0x5584C000
C_RAISE = 0x5584C000             # fixed: the NewTurn hook targets it
C_GATE = 0x5584C100              # fixed: the grant-gate hook targets it
C_APPLY = 0x5584C180             # fixed: the exe calls it through the rebase delta
D_SPAN_END = 0x5584C400          # exclusive reservation (stage 1: 0x5584C100)

# the one inbound-branch candidate the byte sweep finds, proved to be an immediate byte
D_WHITELIST = {0x55756B27: (0x55756B26, bytes.fromhex("b8786c7555"),
                            "imm32 byte of `mov eax,0x55756C78`")}

# vanilla code the cave mirrors or calls into -- asserted on every run
D_ANCHORS = [
    (0x55756BEA, "33c9b201a1ccac7055e80c5702008bd8c64318026a006a0033c98bd38b068b38ff972c010000"
                 "8bc38b10ff522c", "vanilla mode-2 research raise"),
    (0x5577C3F1, "8a46182c0172107406fec87449", "Execute mode switch head"),
    (0x5577C447, "b001eb0233c0", "Execute: mode-2 arm / reject arm"),
    (0x557544D0, "85d27c128b48083b51087d0a8b40088b", "TPlayerList.GetPlayers"),
    (0x5577C304, "535684d2740883c4f0e8c64df8ff8bda", "TPlayerMagicEventLog.Create"),
    (0x55756B26, "b8786c7555", "the whitelisted immediate"),
    # stage 2
    (0x5577CC35, "a140a08f5583b874010000010f85030100008b461080b8a6000000000f84f3000000"
                 "a140a08f55", "grant host: day 1, [player+0xA6] != 0, map into EAX"),
    (0x5577CD4A, "8b5e34", "grant host resume"),
    (0x5577D278, "813e0200022075188b46188b53100fbe92a60000003bc275078bc3",
     "TPlayerMagicControl.MsgProc: NewTurn only for [[magic+0x10]+0xA6] == msg player"),
    (0x55755540, "0fbec38945e8", "TPlayerControl.NewTurn: msg player := movsx bl"),
    (0x55787FDC, "3a5e24", "THero.NewTurn: only on the owner's turn ([hero+0x24] == bl)"),
    (0x557546D7, "8bc78b10ff52548bd08bc6e851d1ffff",
     "TPlayerList.SetNumberOfPlayers: [player+0xA6] := its list index"),
    (0x55756F43, "8b0380b83a0100000274208b0380b83a0100000075118b038b80400100008b401c"
                 "837808017f0433c0eb02b0018b13",
     "DefaultStartMap: map[+0x139] := 1 for PBEM, so the day-1 block needs no seated test"),
    (0x557755F8, "ff8034020000c390ff8834020000c390", "SynchroniseBegin / SynchroniseEnd"),
    (0x55775608, "83b8340200000075188b", "GetSynchronised: [map+0x234] != 0 -> true"),
    (0x5577827C, "53568bf28bd8a140a08f55f6403c08753e8bc3e874d3ffff84c0",
     "TAoWHSMap.Random asserts GetSynchronised"),
    (0x557869E4, "538bd8a0f46978550a435d88435d5bc3", "UpdateFromLibraryBegin"),
    (0x557869F8, "538bd8a00c6a7855f7d022435d88435d5bc3", "UpdateFromLibraryEnd"),
    (0x557E0CAB, "8b86d4000000e82e5dfaff8b45fc8b40288bd3e831e9ffff8b501c8b0d5c948e558b09"
                 "8b86d40000008b38ff573c8b86d4000000e8145dfaff",
     "TSetupControl.SetupMap copy-back: Begin / Assign(vmt+0x3C, ECX=AoWEngine) / End"),
    (0x557854DB, "8b561c8bc7e85b9c0800c6475400",
     "THeroUpgradeTE.Execute tail (live): abilities + aura cave, then [hero+0x54] := 0"),
    (0x557010C0, "ff25bcb68f55", "thunk System.@IsClass"),
    (0x5578D034, "558bec33c95151515151", "TArmy.UpdateFormation"),
]

# =============================================================== AoWz.exe pair ==
X_HOOK = 0x0044F183              # jmp 0x44F51E  (E9 rel32)
X_EPI = 0x0044F51E

G_EVENT = 0x0062C000
G_CODE = 0x0062C004
G_DATA = 0x0062C008
G_MODAL = 0x0062C00C
X_SHOW = 0x0062C010              # fixed entry -- the hook targets it
X_SPAN = 0x0062C000
X_SPAN_END = 0x0062C400          # exclusive reservation (v1: 0x0062C200)

# earlier bodies this script has installed: sha256 of the span's non-zero prefix -> tag.
# A "stale" span is rewritten in place ONLY if it is one of these (rest of span zero).
EXE_KNOWN_BODIES = {
    "eb61106620b820da7fb4967a53818334ee1cf5a2f160ad8f9bb9d6b90c43aec7": "stage 1 v1 2026-09-23, 418 B",
    "aa65684daf3f58cbe65fed4422026b59c342a48889d6a27ae4f2b112b0f779fb": "stage 1 v2 2026-09-23, 624 B",
}
DLL_KNOWN_BODIES = {
    "dfbf432f6f4c3350b212fed0fba70dc638655d187bd844cf313974611a7f8a87": "stage 1 C_RAISE 2026-09-23, 106 B",
}

# ---- stage 2: the offer roll in TLeaderSetupWin's available-ability loop ------------------
X_OFFER = 0x004161C9             # mov edx,[esi+0x2E4]  (8B 96 E4 02 00 00), just before CanExpand
X_OFFER_ORIG = bytes.fromhex("8b96e4020000")
X_OFFER_RESUME = 0x004161CF      # mov ecx,[eax] ; call [ecx+0xC4]  (CanExpand)
X_OFFER_REJECT = 0x00416251      # inc ebx ; dec [ebp-0x10] -- where both vanilla rejects go
DLG_LEADER = 0x2E4               # TLeaderSetupWin's own leader (the window's working copy)
ABILITY_ID = 0x0C                # TAbility id (cave_fill's key)
OFFER_CAP = 100                  # min(2 * pct, 100)
V_AOWHSMAP = 0x558FA040          # AoWE.AoWHSMap: [IAT_MAP] - this = AoWEPACK.dpl's rebase delta

# Every other TAOWPanel whose DFM AOWWindow resolves to TitleWin (the set is re-derived from the
# DFMs and asserted equal on every run).  form class, panel, form global, field, CreateForm call.
TITLE_PANELS = [
    ("TTitleWindow",     "TitlePnl",     0x0045A28C, 0x48, 0x00459A76),
    ("TTitleWindow",     "SplashPnl",    0x0045A28C, 0x4C, 0x00459A76),
    ("TMultiWindow",     "MultiPnl",     0x0045A598, 0x54, 0x00459B47),
    ("TScenSetup",       "ScenSetupPnl", 0x0045A30C, 0xA0, 0x00459CD6),
    ("TWorldMap",        "WorldPnl",     0x0045A174, 0x4C, 0x00459C9D),
    ("TCampaignJoinDlg", "CharGenPnl",   0x0045A100, 0x44, 0x00459F10),
    ("TSelFactionWin",   "FactionPnl",   0x0045A230, 0x44, 0x00459C3E),
    ("TPyreScreen",      "DeadPnl",      0x0045A2F0, 0x44, 0x00459BCC),
    ("TResultsWin",      "ResultsPnl",   0x0045A20C, 0x9C, 0x00459E19),
]
SHOWN_PANEL = ("TLeaderSetupWin", "LeaderPnl", 0x0045A3F0, 0x2CC, 0x00459D94)
F_CREATEFORM = 0x0040175C        # thunk -> Forms.TApplication.CreateForm
WIN_VISIBLE = 0x75               # TAoWComponent visible byte

T_GETPLAYERS = 0x00402464        # thunk -> AoWE.TPlayerList.GetPlayers
T_LSC_CREATE = 0x00402474        # thunk -> AoWE.TLeaderSetupControl.Create
T_SETOVERPRI = 0x0040312C        # thunk -> aowInt TAOWWinManager.SetOverPri
IAT_MAP = 0x0045DF7C             # -> AoWE.AoWHSMap        (map = [[IAT_MAP]])
IAT_ENGINE = 0x0045DF74          # -> AoWE.AoWEngine       (engine = [[IAT_ENGINE]])
IAT_LSC_CLASS = 0x0045DFEC       # AoWE..TLeaderSetupControl (VMT = [IAT_LSC_CLASS])
GV_TITLE = 0x0045A28C            # -> TTitleWindow instance var
GV_LEADERDLG = 0x0045A3F0        # -> TLeaderSetupWin instance var
GV_GENERAL = 0x0045A420          # -> TGeneral instance var (+0x44 Manager)
F_SETUP = 0x00416988             # TLeaderSetupWin.Setup(EAX=dlg, EDX=ctrl)
MAP_SEATED = 0xA5
TW_TITLEWIN = 0x44               # TTitleWindow.TitleWin
WIN_MODAL = 0x104                # TAOWWindow.Modal (published, field get/set)
V_SETVISIBLE = 0x6C
V_ASSIGN = 0x3C
GEN_MANAGER = 0x44
LSC_ORIG, LSC_MODE, LSC_COPY, LSC_ONDONE_CODE, LSC_ONDONE_DATA = 0x0C, 0x10, 0x14, 0x20, 0x24
LSM_SETTINGS_SPHERES = 6
OVERPRI_MODAL = 0x31

X_ANCHORS = [
    # stops at the hook (0x44F183); the hook's own bytes are checked by Target.state()
    (0x0044F162, "8bc68b15f0df4500e8011ffbff84c074608bc68a501880ea01720b7422feca7437",
     "TPlayerMagicEventLog dispatch branch up to the hook"),
    (0x0044F516, "8bd68b450cff55085f5e5b5dc20800", "unhandled-class callback + epilogue"),
    (0x0041C8E1, "33c9b201a1ecdf4500e8855bfeff", "campaign recipe: TLeaderSetupControl.Create"),
    (0x0041C8FB, "8b50088b0d74df45008b098b430c8b38ff573c", "campaign recipe: Assign from leader"),
    (0x0041C91C, "8b0d74df45008b098b530c8b43148b38ff573c", "campaign recipe: copy.Assign(orig)"),
    (0x00430A89, "a17cdf45008b000fbe90a5000000a17cdf45008b008b8040010000e8bb19fdff",
     "research handler: seated player"),
    (0x00430B57, "8b80d4000000", "research handler: [player+0xD4] leader"),
    (0x0042E804, "66837c24020074098bd68b442404ff142485f674078bc68b10ff522c",
     "spellbook close: guarded callback + Release"),
    (0x0042E820, "a120a445008b008b404433d2e8fb48fdff", "spellbook close: SetOverPri(0)"),
    (0x00402464, "ff2530de4500", "thunk GetPlayers"),
    (0x00402474, "ff2528de4500", "thunk TLeaderSetupControl.Create"),
    (0x0040312C, "ff25dce94500", "thunk SetOverPri"),
    (0x00416898, "8990e0020000e8b50d0000", "locked sphere-pick count setter"),
    (0x00416988, "558bec83c4f853565733c9894df88bda", "TLeaderSetupWin.Setup"),
    (0x004169A8, "8bc6e8f5feffff", "Setup calls its reset 0x4168A4 ..."),
    (0x00416956, "33d28bc3e839ffffff", "... which sets locked sphere picks = 0 (0x416898)"),
    (0x004141E3, "a10ca345008b008b80a000000033d28b08ff516c",
     "vanilla hides ScenSetupPnl before LeaderPnl"),
    (0x0040175C, "ff25", "thunk CreateForm"),
    (0x00416D9C, "53568bd88bc3e8edecffff8bb3d8020000c6461c0233c08983d802000033d28b83cc020000"
                 "8b08ff516c8b46148b5060a154a445008b00e8b4d8ffff8bc68b10ff524c8bc68b10ff522c",
     "TLeaderSetupWin.Finish (-> Done vmt+0x4C, Release)"),
    (0x004280E5, "a18ca245008b008b404433d28b08ff516c", "vanilla TitleWin.SetVisible(False)"),
    # stage 2
    (0x004161AF, "0f849c000000a178df45008b008b80800000008bd3e80bc2feff",
     "available loop: mask reject -> 0x416251, then GetAbility(ebx) into EAX"),
    (0x004161CF, "8b08ff91c400000084c07476", "available loop: CanExpand (vmt +0xC4), reject"),
    (0x00416251, "43ff4df0", "available loop: next index"),
    (0x00415AAB, "8b0d74df45008b098b83d80200008b40148b93e40200008b30ff563c",
     "0x415A94 (called by Finish first): ctrl[+0x14].Assign([dlg+0x2E4])"),
]

# ====================================================================== PE ======
class PE:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        if not os.path.exists(path):
            sys.exit("not found: %s" % path)
        with open(path, "rb") as f:
            self.d = bytearray(f.read())
        d = self.d
        self.pe = struct.unpack_from("<I", d, 0x3C)[0]
        n = struct.unpack_from("<H", d, self.pe + 6)[0]
        opt = struct.unpack_from("<H", d, self.pe + 20)[0]
        self.base = struct.unpack_from("<I", d, self.pe + 24 + 28)[0]
        self.secs = []
        for i in range(n):
            o = self.pe + 24 + opt + i * 40
            nm = bytes(d[o:o + 8]).rstrip(b"\0").decode("latin1")
            vsz, va, rsz, raw = struct.unpack_from("<IIII", d, o + 8)
            ch = struct.unpack_from("<I", d, o + 36)[0]
            self.secs.append((nm, self.base + va, vsz, raw, rsz, ch))
        self.reloc_rva, self.reloc_size = struct.unpack_from("<II", d, self.pe + 24 + 96 + 5 * 8)

    def sec_of(self, va):
        for s in self.secs:
            nm, sva, vsz, raw, rsz, ch = s
            if sva <= va < sva + min(vsz, rsz):     # file-backed only
                return s
        return None

    def off(self, va):
        s = self.sec_of(va)
        if s is None:
            raise ValueError("%s: VA 0x%08X is not file-backed" % (self.name, va))
        return s[3] + va - s[1]

    def rd(self, va, n):
        o = self.off(va)
        assert self.sec_of(va + n - 1) is self.sec_of(va), "run crosses a section"
        return bytes(self.d[o:o + n])

    def wr(self, va, blob):
        o = self.off(va)
        assert self.sec_of(va + len(blob) - 1) is self.sec_of(va), "run crosses a section"
        self.d[o:o + len(blob)] = blob

    def relocs(self):
        """Every HIGHLOW (type 3) fixup target VA."""
        out = set()
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
                if e >> 12:
                    out.add(self.base + page + (e & 0xFFF))
            p += blk
        return out

    def inbound(self, lo, hi):
        """Byte-scan every executable section for a branch landing in [lo, hi].  A superset:
        an empty answer is proof, a non-empty one must be read."""
        hits = []
        d = self.d
        for nm, sva, vsz, raw, rsz, ch in self.secs:
            if not ch & 0x20000000:
                continue
            n = min(vsz, rsz)
            for i in range(raw, raw + n - 1):
                b = d[i]
                src = sva + (i - raw)
                tg = []
                if b in (0xE8, 0xE9) and i + 5 <= raw + n:
                    tg.append(src + 5 + struct.unpack_from("<i", d, i + 1)[0])
                if b == 0x0F and 0x80 <= d[i + 1] <= 0x8F and i + 6 <= raw + n:
                    tg.append(src + 6 + struct.unpack_from("<i", d, i + 2)[0])
                if b == 0xEB or 0x70 <= b <= 0x7F or 0xE0 <= b <= 0xE3:
                    tg.append(src + 2 + struct.unpack_from("<b", d, i + 1)[0])
                if any(lo <= t <= hi for t in tg):
                    hits.append(src)
        return hits

    def save(self):
        try:
            f = open(self.path, "wb")
        except PermissionError:
            print("    %s locked -> killing AoW processes and retrying" % self.name)
            kill_game()
            time.sleep(1.0)
            f = open(self.path, "wb")
        with f:
            f.write(self.d)


def kill_game():
    """Standing authorisation: the game/editor lock the binaries.  Exact names only --
    AowEmailWrapper and Launcher lock nothing and are left alone."""
    if os.environ.get("AOW_GAME_DIR"):
        return
    for p in zigexe.LOCKING_PROCESSES:
        subprocess.run(["taskkill", "/F", "/IM", p + ".exe"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ============================================================== assembler ======
def _ks():
    try:
        from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    except ImportError:
        sys.exit("keystone-engine not installed:  pip install keystone-engine")
    return Ks(KS_ARCH_X86, KS_MODE_32)


def asm_layout(frags, base):
    """frags: (label|None, text|callable(labels)->text|bytes|("align", n)|None).  Text may use
    {LABEL} placeholders.  An ("align", n) item pads with int3 to an n-byte boundary and an
    ("org", va) item pads with int3 up to a FIXED entry va (aborting if the code before it
    overran it); a label on either names the resulting address.  Iterates to a fixed point so
    forward references settle."""
    ks = _ks()
    labels = {lab: base for lab, _ in frags if lab}
    for _ in range(12):
        va, out, seen, overrun = base, b"", {}, None
        for lab, item in frags:
            if isinstance(item, tuple) and item[0] in ("align", "org"):
                pad = (-va) % item[1] if item[0] == "align" else item[1] - va
                if pad < 0:                       # judged only once the layout converges
                    overrun, pad = item[1], 0
                out += b"\xCC" * pad
                va += pad
                if lab:
                    seen[lab] = va
                continue
            if lab:
                seen[lab] = va
            if item is None:
                continue
            if isinstance(item, (bytes, bytearray)):
                out += bytes(item)
                va += len(item)
                continue
            text = item(labels) if callable(item) else item.format(
                **{k: hex(v) for k, v in labels.items()})
            enc, _ = ks.asm(text, va)
            if enc is None:
                raise RuntimeError("keystone failed on: %s" % text)
            out += bytes(enc)
            va += len(enc)
        if seen == labels:
            if overrun is not None:
                raise RuntimeError("code overruns the fixed entry 0x%08X" % overrun)
            return out, labels
        labels = seen
    raise RuntimeError("cave layout did not converge")


def build_dll_caves():
    """C_RAISE, C_GATE, C_APPLY at their fixed entries, one blob from D_CAVE."""
    P = pbemday1
    frags = [
        # ---- C_RAISE: NewTurn day-1 block, from 0x55756B94.  bl = player index, esi = &map var.
        ("C_RAISE", "mov eax, dword ptr [esi]"),                   # map
        (None, "movsx edx, bl"),
        (None, "mov eax, dword ptr [eax + %s]" % hex(MAP_PLAYERS)),
        (None, "call %s" % hex(F_GETPLAYERS)),                     # player = list[bl]
        (None, "test eax, eax"),
        (None, "je {RESUME}"),
        (None, "mov ecx, dword ptr [esi]"),                        # map
    ] + [(None, t) for t in P.asm("ecx", "eax", "{RESUME}")] + [
        (None, "push ebx"),
        (None, "call {ANCHOR}"),
        ("ANCHOR", "pop eax"),
        # rebase-invariant: VMT - anchor is a constant difference inside one image
        (None, lambda L: "add eax, %d" % (PMEL_VMT - L["ANCHOR"])),
        (None, "xor ecx, ecx"),
        (None, "mov dl, 1"),
        (None, "call %s" % hex(F_PMEL_CREATE)),
        (None, "mov edi, eax"),
        (None, "mov byte ptr [edi + %s], %d" % (hex(EV_MODE), MODE_LEADER)),
        (None, "mov byte ptr [edi + %s], bl" % hex(EV_PLAYER)),    # the event names ITS player
        (None, "push 0"),
        (None, "push 0"),
        (None, "xor ecx, ecx"),
        (None, "mov edx, edi"),
        (None, "mov eax, dword ptr [esi]"),
        (None, "mov ebx, dword ptr [eax]"),
        (None, "call dword ptr [ebx + %s]" % hex(V_TRIGGER_EVLOG)),
        (None, "mov eax, edi"),
        (None, "mov edx, dword ptr [eax]"),
        (None, "call dword ptr [edx + %s]" % hex(V_RELEASE)),
        (None, "pop ebx"),
        ("RESUME", "movsx edi, bl"),                               # the displaced pair
        (None, "mov edx, edi"),
        (None, "jmp %s" % hex(D_RESUME)),

        # ---- C_GATE: from 0x5577CC5C.  eax = map, esi = TPlayerMagicControl.  The 22 displaced
        # bytes are vanilla's last two grant guards, replayed exactly; the predicate is added
        # after them, so the grant is deferred precisely when it would otherwise run.
        ("C_GATE", ("org", C_GATE)),
        (None, "cmp byte ptr [eax + %s], 1" % hex(MAP_MODE_11A)),
        (None, "jne {G_PRED}"),
        (None, "mov ecx, dword ptr [esi + %s]" % hex(MAGIC_KNOWN)),
        (None, "cmp dword ptr [ecx + 8], 0"),
        (None, "jne {G_SKIP}"),                                    # preseeded: vanilla skips
        ("G_PRED", "mov ecx, dword ptr [esi + 0x10]"),             # the player (msg-filtered)
        (None, "test ecx, ecx"),
        (None, "je {G_GRANT}"),
    ] + [(None, t) for t in P.asm("eax", "ecx", "{G_GRANT}")] + [
        ("G_SKIP", "jmp %s" % hex(GRANT_SKIP)),                    # deferred to C_APPLY
        ("G_GRANT", "jmp %s" % hex(GRANT_ENTRY)),                  # the grant, unchanged

        # ---- C_APPLY(EAX = ctrl, EDX = player, ECX = map, [esp+4] = AoWEngine); ret 4.
        # Called from the exe's C_DONE through the rebase delta.  Delphi convention.
        ("C_APPLY", ("org", C_APPLY)),
        (None, "push ebx"),
        (None, "push esi"),
        (None, "push edi"),
        (None, "push ebp"),
        (None, "mov ebx, eax"),
        (None, "mov esi, edx"),
        (None, "mov edi, ecx"),
        (None, "mov ebp, dword ptr [esp + 0x14]"),                 # AoWEngine
        (None, "test ebx, ebx"),
        (None, "je {A_OUT}"),
        (None, "cmp byte ptr [ebx + %s], %d" % (hex(LSC_STATUS), LSS_DONE)),
        (None, "jne {A_OUT}"),                                     # lssDone only
        (None, "test esi, esi"),
        (None, "je {A_OUT}"),
        (None, "test edi, edi"),
        (None, "je {A_OUT}"),
        (None, "test ebp, ebp"),
        (None, "je {A_OUT}"),
        (None, "mov ebx, dword ptr [ebx + %s]" % hex(LSC_COPY)),   # Finish's 0x415A94 wrote it
        (None, "test ebx, ebx"),
        (None, "je {A_OUT}"),
        (None, "cmp dword ptr [esi + %s], 0" % hex(PL_LEADER)),
        (None, "je {A_OUT}"),
        (None, "mov eax, edi"),
        (None, "call %s" % hex(F_SYNC_BEGIN)),
        # 1. the copy-back, exactly TSetupControl.SetupMap's (0x557E0CAB)
        (None, "mov eax, dword ptr [esi + %s]" % hex(PL_LEADER)),
        (None, "call %s" % hex(F_UFL_BEGIN)),
        (None, "mov eax, dword ptr [esi + %s]" % hex(PL_LEADER)),
        (None, "mov edx, ebx"),                                    # the window's copy
        (None, "mov ecx, ebp"),                                    # AoWEngine
        (None, "mov ebx, dword ptr [eax]"),
        (None, "call dword ptr [ebx + %s]" % hex(V_ASSIGN)),       # live.Assign(copy)
        (None, "mov eax, dword ptr [esi + %s]" % hex(PL_LEADER)),
        (None, "call %s" % hex(F_UFL_END)),
        # 2. THeroUpgradeTE.Execute's tail: the army's formation (Leadership aura) refresh
        #    of build_leadership_aura.py's cave, then upgrade_pending := 0
        (None, "mov ebx, dword ptr [esi + %s]" % hex(PL_LEADER)),
        (None, "mov eax, dword ptr [ebx + %s]" % hex(HERO_OWNER_OBJ)),
        (None, "test eax, eax"),
        (None, "je {A_NOARMY}"),
        (None, "call {A_ANCHOR}"),
        ("A_ANCHOR", "pop edx"),
        (None, lambda L: "add edx, %d" % (TARMY_VMT - L["A_ANCHOR"])),
        (None, "call %s" % hex(F_ISCLASS)),
        (None, "test al, al"),
        (None, "je {A_NOARMY}"),
        (None, "mov eax, dword ptr [ebx + %s]" % hex(HERO_OWNER_OBJ)),
        (None, "call %s" % hex(F_UPDATEFORMATION)),
        ("A_NOARMY", "mov byte ptr [ebx + %s], 0" % hex(HERO_UPGRADE_PENDING)),
        # 3. the deferred day-1 grant, under exactly C_GATE's conditions
    ] + [(None, t) for t in P.asm("edi", "esi", "{A_SYNCEND}")] + [
        (None, "cmp byte ptr [esi + %s], 0" % hex(PL_INDEX)),
        (None, "je {A_SYNCEND}"),                                  # the host's own guard
        (None, "mov eax, dword ptr [esi + %s]" % hex(PL_MAGIC)),
        (None, "test eax, eax"),
        (None, "je {A_SYNCEND}"),
        (None, "cmp byte ptr [edi + %s], 1" % hex(MAP_MODE_11A)),
        (None, "jne {A_GRANT}"),
        (None, "mov ecx, dword ptr [eax + %s]" % hex(MAGIC_KNOWN)),
        (None, "cmp dword ptr [ecx + 8], 0"),
        (None, "jne {A_SYNCEND}"),
        ("A_GRANT", "push esi"),
        (None, "push edi"),
        (None, "mov esi, eax"),
        (None, "call %s" % hex(TR_DAY1)),                         # build_tierresearch_dll v2
        (None, "pop edi"),
        (None, "pop esi"),
        ("A_SYNCEND", "mov eax, edi"),
        (None, "call %s" % hex(F_SYNC_END)),
        ("A_OUT", "pop ebp"),
        (None, "pop edi"),
        (None, "pop esi"),
        (None, "pop ebx"),
        (None, "ret 4"),
    ]
    blob, labels = asm_layout(frags, D_CAVE)
    assert labels["C_RAISE"] == C_RAISE and labels["C_GATE"] == C_GATE
    assert labels["C_APPLY"] == C_APPLY
    if D_CAVE + len(blob) > D_SPAN_END:
        raise RuntimeError("DLL caves are %d B, the reservation is %d"
                           % (len(blob), D_SPAN_END - D_CAVE))
    assert_pic(blob, D_CAVE)
    return blob, labels


def assert_pic(blob, va):
    """Position independence, per INSTRUCTION (a raw dword scan false-alarms on byte runs that
    straddle instructions, e.g. `02 75 55`): no memory operand without a base or index register,
    and no immediate that looks like an image VA outside a relative branch."""
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        from capstone.x86 import X86_OP_IMM, X86_OP_MEM
    except ImportError:
        sys.exit("capstone not installed:  pip install capstone")
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    n = 0
    for i in md.disasm(blob, va):
        n += len(i.bytes)
        rel = i.mnemonic == "call" or i.mnemonic.startswith("j")
        for op in i.operands:
            if op.type == X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                raise RuntimeError("absolute memory operand at 0x%08X: %s %s"
                                   % (i.address, i.mnemonic, i.op_str))
            if op.type == X86_OP_IMM and not rel and 0x55700000 <= (op.imm & 0xFFFFFFFF) < 0x55A00000:
                raise RuntimeError("image-VA immediate at 0x%08X: %s %s"
                                   % (i.address, i.mnemonic, i.op_str))
    if n != len(blob):
        raise RuntimeError("cave does not disassemble cleanly (%d of %d B)" % (n, len(blob)))


def build_exe_cave():
    V = hex
    N = len(TITLE_PANELS)
    frags = [
        (None, bytes(X_SHOW - X_SPAN)),                               # the four globals
        ("C_SHOW", "cmp byte ptr [esi + %s], %d" % (V(EV_MODE), MODE_LEADER)),
        (None, "jne {EPI}"),
        (None, "cmp dword ptr [%s], 0" % V(G_EVENT)),
        (None, "jne {FIRE}"),
        (None, "mov eax, dword ptr [%s]" % V(IAT_MAP)),
        (None, "mov eax, dword ptr [eax]"),
        # stage 2: the EVENT's player (C_RAISE wrote bl there), not the seated one, so the
        # window, the copy-back and the grant all act on the TPlayer C_RAISE tested
        (None, "movsx edx, byte ptr [esi + %s]" % V(EV_PLAYER)),
        (None, "mov eax, dword ptr [eax + %s]" % V(MAP_PLAYERS)),
        (None, "call %s" % V(T_GETPLAYERS)),
        (None, "test eax, eax"),
        (None, "je {FIRE}"),
        (None, "mov ebx, dword ptr [eax + %s]" % V(PL_LEADER)),
        (None, "test ebx, ebx"),
        (None, "je {FIRE}"),
        (None, "mov dword ptr [{G_PLAYER}], eax"),
        # keep the event and its completion callback until the window closes
        (None, "mov dword ptr [%s], esi" % V(G_EVENT)),
        (None, "mov eax, esi"),
        (None, "mov edx, dword ptr [eax]"),
        (None, "call dword ptr [edx + %s]" % V(V_ADDREF)),
        (None, "mov eax, dword ptr [ebp + 8]"),
        (None, "mov dword ptr [%s], eax" % V(G_CODE)),
        (None, "mov eax, dword ptr [ebp + 0xc]"),
        (None, "mov dword ptr [%s], eax" % V(G_DATA)),
        # the control object -- the campaign recipe at 0x41C8E1
        (None, "xor ecx, ecx"),
        (None, "mov dl, 1"),
        (None, "mov eax, dword ptr [%s]" % V(IAT_LSC_CLASS)),
        (None, "call %s" % V(T_LSC_CREATE)),
        (None, "mov edi, eax"),
        (None, "mov ecx, dword ptr [%s]" % V(IAT_ENGINE)),
        (None, "mov ecx, dword ptr [ecx]"),
        (None, "mov edx, ebx"),
        (None, "mov eax, dword ptr [edi + %s]" % V(LSC_ORIG)),
        (None, "mov esi, dword ptr [eax]"),
        (None, "call dword ptr [esi + %s]" % V(V_ASSIGN)),
        (None, "mov ecx, dword ptr [%s]" % V(IAT_ENGINE)),
        (None, "mov ecx, dword ptr [ecx]"),
        (None, "mov edx, dword ptr [edi + %s]" % V(LSC_ORIG)),
        (None, "mov eax, dword ptr [edi + %s]" % V(LSC_COPY)),
        (None, "mov esi, dword ptr [eax]"),
        (None, "call dword ptr [esi + %s]" % V(V_ASSIGN)),
        (None, "mov byte ptr [edi + %s], %d" % (V(LSC_MODE), LSM_SETTINGS_SPHERES)),
        (None, "mov dword ptr [edi + %s], {C_DONE}" % V(LSC_ONDONE_CODE)),
        (None, "mov dword ptr [edi + %s], 0" % V(LSC_ONDONE_DATA)),
        # hide every other TitleWin panel, remembering its visible byte (vanilla hides the host
        # panel before LeaderPnl too: 0x4141F4, 0x41C8C7)
        (None, "xor ebx, ebx"),
        ("HIDE", "mov byte ptr [ebx + {G_VIS}], 0"),
        (None, "call {C_PANEL}"),
        (None, "test eax, eax"),
        (None, "je {HNEXT}"),
        (None, "mov dl, byte ptr [eax + %s]" % V(WIN_VISIBLE)),
        (None, "test dl, dl"),
        (None, "je {HNEXT}"),
        (None, "mov byte ptr [ebx + {G_VIS}], dl"),
        (None, "xor edx, edx"),
        (None, "mov ecx, dword ptr [eax]"),
        (None, "call dword ptr [ecx + %s]" % V(V_SETVISIBLE)),
        ("HNEXT", "inc ebx"),
        (None, "cmp ebx, %d" % N),
        (None, "jb {HIDE}"),
        # host: TitleWin, forced modal, shown
        (None, "mov eax, dword ptr [%s]" % V(GV_TITLE)),
        (None, "mov eax, dword ptr [eax]"),
        (None, "mov eax, dword ptr [eax + %s]" % V(TW_TITLEWIN)),
        (None, "mov dl, byte ptr [eax + %s]" % V(WIN_MODAL)),
        (None, "mov byte ptr [%s], dl" % V(G_MODAL)),
        (None, "mov byte ptr [eax + %s], 1" % V(WIN_MODAL)),
        (None, "mov dl, 1"),
        (None, "mov ecx, dword ptr [eax]"),
        (None, "call dword ptr [ecx + %s]" % V(V_SETVISIBLE)),
        # the window (Setup itself sets the locked sphere-pick count to 0, 0x416956)
        (None, "mov eax, dword ptr [%s]" % V(GV_LEADERDLG)),
        (None, "mov eax, dword ptr [eax]"),
        (None, "mov edx, edi"),
        (None, "call %s" % V(F_SETUP)),
        (None, "mov eax, dword ptr [%s]" % V(GV_GENERAL)),
        (None, "mov eax, dword ptr [eax]"),
        (None, "mov eax, dword ptr [eax + %s]" % V(GEN_MANAGER)),
        (None, "mov edx, %s" % V(OVERPRI_MODAL)),
        (None, "call %s" % V(T_SETOVERPRI)),
        (None, "mov eax, edi"),
        (None, "mov edx, dword ptr [eax]"),
        (None, "call dword ptr [edx + %s]" % V(V_RELEASE)),
        (None, "jmp {EPI}"),
        # complete the event now, as vanilla's unhandled-class path does (guarded)
        ("FIRE", "cmp word ptr [ebp + 0xa], 0"),
        (None, "je {EPI}"),
        (None, "mov edx, esi"),
        (None, "mov eax, dword ptr [ebp + 0xc]"),
        (None, "call dword ptr [ebp + 8]"),
        ("EPI", "jmp %s" % V(X_EPI)),

        # ---- C_DONE: OnDone(EAX=data, EDX=ctrl); preserves ebx/esi/edi/ebp
        ("C_DONE", ("align", 16)),
        (None, "push ebx"),
        (None, "push esi"),
        (None, "push edi"),
        (None, "mov edi, edx"),                                   # ctrl, for C_APPLY
        (None, "mov eax, dword ptr [%s]" % V(GV_GENERAL)),
        (None, "mov eax, dword ptr [eax]"),
        (None, "mov eax, dword ptr [eax + %s]" % V(GEN_MANAGER)),
        (None, "xor edx, edx"),
        (None, "call %s" % V(T_SETOVERPRI)),
        (None, "mov eax, dword ptr [%s]" % V(GV_TITLE)),
        (None, "mov eax, dword ptr [eax]"),
        (None, "mov ebx, dword ptr [eax + %s]" % V(TW_TITLEWIN)),
        (None, "xor edx, edx"),
        (None, "mov eax, ebx"),
        (None, "mov ecx, dword ptr [eax]"),
        (None, "call dword ptr [ecx + %s]" % V(V_SETVISIBLE)),
        (None, "mov al, byte ptr [%s]" % V(G_MODAL)),
        (None, "mov byte ptr [ebx + %s], al" % V(WIN_MODAL)),
        # put back the visible byte of every panel we hid -- a byte write, NOT SetVisible(True),
        # which would fire OnShow (ResultsPnlShow) that vanilla never re-runs here
        (None, "xor ebx, ebx"),
        ("RESTORE", "mov dl, byte ptr [ebx + {G_VIS}]"),
        (None, "test dl, dl"),
        (None, "je {RNEXT}"),
        (None, "call {C_PANEL}"),
        (None, "test eax, eax"),
        (None, "je {RNEXT}"),
        (None, "mov byte ptr [eax + %s], dl" % V(WIN_VISIBLE)),
        ("RNEXT", "mov byte ptr [ebx + {G_VIS}], 0"),
        (None, "inc ebx"),
        (None, "cmp ebx, %d" % N),
        (None, "jb {RESTORE}"),
        # stage 2: make the choices stick -- C_APPLY in AoWEPACK.dpl, reached through the
        # rebase delta [IAT_MAP] - 0x558FA040 (the documented cross-module idiom), BEFORE the
        # completion callback so the research prompt that follows sees the new spheres
        (None, "test edi, edi"),
        (None, "je {NOAPPLY}"),
        (None, "cmp byte ptr [edi + %s], %d" % (V(LSC_STATUS), LSS_DONE)),
        (None, "jne {NOAPPLY}"),
        (None, "mov eax, dword ptr [%s]" % V(IAT_ENGINE)),
        (None, "push dword ptr [eax]"),                           # [esp+4] = AoWEngine
        (None, "mov esi, dword ptr [%s]" % V(IAT_MAP)),          # runtime &AoWE.AoWHSMap
        (None, "mov ecx, dword ptr [esi]"),                       # ECX = map
        (None, "sub esi, %s" % V(V_AOWHSMAP)),                    # = AoWEPACK.dpl's rebase delta
        (None, "add esi, %s" % V(C_APPLY)),                       # = C_APPLY at runtime
        (None, "mov edx, dword ptr [{G_PLAYER}]"),                # EDX = the event's player
        (None, "mov eax, edi"),                                   # EAX = ctrl
        (None, "call esi"),                                       # ret 4 pops the engine
        ("NOAPPLY", "mov dword ptr [{G_PLAYER}], 0"),
        # take and clear, then fire -- the spellbook's close at 0x42E7D5
        (None, "mov ebx, dword ptr [%s]" % V(G_CODE)),
        (None, "mov edi, dword ptr [%s]" % V(G_DATA)),
        (None, "mov esi, dword ptr [%s]" % V(G_EVENT)),
        (None, "xor eax, eax"),
        (None, "mov dword ptr [%s], eax" % V(G_CODE)),
        (None, "mov dword ptr [%s], eax" % V(G_DATA)),
        (None, "mov dword ptr [%s], eax" % V(G_EVENT)),
        (None, "test ebx, 0xffff0000"),
        (None, "je {REL}"),
        (None, "mov edx, esi"),
        (None, "mov eax, edi"),
        (None, "call ebx"),
        ("REL", "test esi, esi"),
        (None, "je {OUT}"),
        (None, "mov eax, esi"),
        (None, "mov edx, dword ptr [eax]"),
        (None, "call dword ptr [edx + %s]" % V(V_RELEASE)),
        ("OUT", "pop edi"),
        (None, "pop esi"),
        (None, "pop ebx"),
        (None, "ret"),

        # ---- C_PANEL: EBX = table index -> EAX = panel or nil.  Clobbers EAX only.
        ("C_PANEL", ("align", 16)),
        (None, lambda L: "mov eax, dword ptr [ebx*8 + %s]" % hex(L["PANELS"])),
        (None, "mov eax, dword ptr [eax]"),              # &instance variable
        (None, "test eax, eax"),
        (None, "je {PRET}"),
        (None, "mov eax, dword ptr [eax]"),              # the form
        (None, "test eax, eax"),
        (None, "je {PRET}"),
        (None, lambda L: "add eax, dword ptr [ebx*8 + %s]" % hex(L["PANELS"] + 4)),
        (None, "mov eax, dword ptr [eax]"),              # the panel (the caller tests it)
        ("PRET", "ret"),
    ] + offer_frags() + [
        # ---- data: (form global, field) per panel, the saved visible bytes, the player
        ("PANELS", ("align", 16)),
        (None, b"".join(struct.pack("<II", gv, fld) for _c, _p, gv, fld, _s in TITLE_PANELS)),
        ("G_VIS", ("align", 16)),
        (None, bytes(16)),
        ("G_PLAYER", ("align", 16)),                     # stage 2: the event's TPlayer
        (None, bytes(16)),
    ]
    blob, labels = asm_layout(frags, X_SPAN)
    assert labels["C_SHOW"] == X_SHOW, "C_SHOW moved to 0x%X" % labels["C_SHOW"]
    assert labels["C_DONE"] % 16 == 0 and labels["PANELS"] % 16 == 0
    assert N <= 16, "G_VIS holds 16 bytes"
    if X_SPAN + len(blob) > X_SPAN_END:
        raise RuntimeError("exe cave is %d B, the reservation is %d"
                           % (len(blob), X_SPAN_END - X_SPAN))
    offer = blob[labels["C_OFFER"] - X_SPAN:labels["PANELS"] - X_SPAN]
    HSR._assert_rngstd_shape(offer)          # build_heroskill_race.py's own shape check
    if blob.count(rngstd.SIGNATURE) != 1:
        raise RuntimeError("the exe span must carry exactly one rngstd signature")
    return blob, labels


def offer_frags():
    """C_OFFER -- stage 2's per-race offer roll, doubled.  From 0x4161C9 (the displaced
    `mov edx,[esi+0x2E4]`): EAX = the TAbility from GetAbility(ebx), ESI = TLeaderSetupWin,
    EBX = the loop index, EBP = the host frame.  Accept -> replay + 0x4161CF (CanExpand);
    reject -> 0x416251, the loop's own next-index label.

    Hash = build_heroskill_race.py's cave_fill hash, byte for byte (rngstd, same four inputs
    in the same order); threshold = min(2 * pct, 100) from the SAME baked table."""
    V = hex
    row_max = HSR.RACES.RACELESS_ROW
    return [
        ("C_OFFER", ("align", 16)),
        (None, "cmp dword ptr [%s], 0" % V(G_EVENT)),
        (None, "je {O_ACCEPT}"),                         # not our PBEM window: vanilla's menu
        (None, "push eax"),                              # keep the TAbility for CanExpand
        (None, "mov edx, dword ptr [eax + %s]" % V(ABILITY_ID)),
        (None, "cmp edx, 0x100"),
        (None, "jae {O_ACCPOP}"),                        # past the table: FAIL OPEN
        (None, "mov ecx, dword ptr [esi + %s]" % V(DLG_LEADER)),
        (None, "test ecx, ecx"),
        (None, "je {O_ACCPOP}"),                         # no leader: FAIL OPEN
        (None, "mov ecx, dword ptr [ecx + %s]" % V(HSR.HERO_RES)),
        (None, "test ecx, ecx"),
        (None, "je {O_ACCPOP}"),                         # no chassis: FAIL OPEN
        (None, "movzx ecx, byte ptr [ecx + %s]" % V(HSR.RES_RACE)),   # THero.GetRace, inlined
        (None, "cmp ecx, %d" % row_max),
        (None, "jbe {O_ROW}"),
        (None, "mov ecx, %d" % row_max),                 # race 255 -> the raceless row
        ("O_ROW", "shl ecx, 8"),
        (None, "movzx ecx, byte ptr [ecx + edx + %s]" % V(HSR.TABLE_VA)),   # pct
        (None, "add ecx, ecx"),                          # every chance doubled ...
        (None, "cmp ecx, %d" % OFFER_CAP),
        (None, "jbe {O_THR}"),
        (None, "mov ecx, %d" % OFFER_CAP),               # ... capped at 100%
        ("O_THR", "push ecx"),                           # [esp+4] = threshold
        (None, "push edx"),                              # [esp]   = ability id
        (None, rngstd.basis()),
        (None, "xor edx, edx"),                          # input 1: salt map[+0x22C], nil -> 0
        (None, "mov ecx, dword ptr [%s]" % V(HSR.MAPSLOT)),
        (None, "test ecx, ecx"),
        (None, "je {O_NOSALT}"),
        (None, "mov ecx, dword ptr [ecx]"),
        (None, "test ecx, ecx"),
        (None, "je {O_NOSALT}"),
        (None, "mov edx, dword ptr [ecx + %s]" % V(HSR.MAP_SALT)),
        ("O_NOSALT", rngstd.mix()),
        (None, "mov ecx, dword ptr [esi + %s]" % V(DLG_LEADER)),     # input 2: unit id
        (None, "mov edx, dword ptr [ecx + %s]" % V(HSR.HERO_UNITID)),
        (None, rngstd.mix()),
        (None, "movzx edx, byte ptr [ecx + %s]" % V(HSR.HERO_LEVEL)),  # input 3: level cache
        (None, rngstd.mix()),
        (None, "mov edx, dword ptr [esp]"),              # input 4: ability id
        (None, rngstd.mix()),
        (None, rngstd.fmix32()),
        (None, rngstd.range_n(100)),                     # EDX = 0..99
        (None, "pop eax"),
        (None, "pop ecx"),                               # ECX = min(2 * pct, 100)
        (None, "cmp edx, ecx"),
        (None, "pop eax"),                               # EAX = the TAbility again
        (None, "jb {O_ACCEPT}"),
        (None, "jmp %s" % V(X_OFFER_REJECT)),            # not offered
        ("O_ACCPOP", "pop eax"),
        ("O_ACCEPT", "mov edx, dword ptr [esi + %s]" % V(DLG_LEADER)),   # the displaced insn
        (None, "jmp %s" % V(X_OFFER_RESUME)),
    ]


def jmp_rel32(frm, to):
    return b"\xE9" + struct.pack("<i", to - (frm + 5))


# ============================================================== per-binary =====
class Target:
    """One binary: its sites (va, orig, patched), its cave span and blob."""

    def __init__(self, pe, sites, span, span_end, blob, known):
        self.pe, self.sites, self.span, self.span_end, self.blob = pe, sites, span, span_end, blob
        self.known = known

    def span_bytes(self):
        return self.pe.rd(self.span, self.span_end - self.span)

    def installed_known(self):
        """The tag of the earlier body in the span, if it is one this script wrote."""
        span = self.span_bytes()
        nz = [i for i, b in enumerate(span) if b]
        if not nz:
            return None
        body = span[:nz[-1] + 1]
        return self.known.get(hashlib.sha256(body).hexdigest())

    def site_class(self, va, orig, patched):
        """'orig' | 'patched' | 'ours' (an E9 into our own span with the same padding, i.e. an
        earlier layout of this script) | 'foreign'."""
        cur = self.pe.rd(va, len(orig))
        if cur == orig:
            return "orig"
        if cur == patched:
            return "patched"
        if (cur[0] == 0xE9 and cur[5:] == patched[5:]
                and self.span <= va + 5 + struct.unpack("<i", cur[1:5])[0] < self.span_end):
            return "ours"
        return "foreign"

    def state(self):
        cls = [self.site_class(va, o, p) for va, o, p, _d in self.sites]
        span = self.span_bytes()
        want = self.blob + bytes(len(span) - len(self.blob))
        if "foreign" in cls:
            return "mixed"
        if all(c == "orig" for c in cls) and not any(span):
            return "vanilla"
        if all(c == "patched" for c in cls) and span == want:
            return "applied"
        if self.installed_known():
            return "stale"            # our sites (any layout) + a known earlier body
        return "mixed"

    def apply(self):
        st = self.state()
        if st == "applied":
            return False
        self.pe.wr(self.span, bytes(self.span_end - self.span))     # stale tail cannot survive
        self.pe.wr(self.span, self.blob)
        for va, _o, p, _d in self.sites:
            self.pe.wr(va, p)
        return True

    def undo(self):
        for va, o, _p, _d in self.sites:
            self.pe.wr(va, o)
        self.pe.wr(self.span, bytes(len(self.blob)))    # the emitted length, never more
        assert not any(self.span_bytes()), "reserved span not zero after undo"


def check_reloc(pe, owned):
    rel = pe.relocs()
    bad = sorted(t for t in rel for a, n in owned if a - 3 <= t < a + n)
    if bad:
        sys.exit("ABORT: %s: .reloc entries touch bytes this patch owns: %s"
                 % (pe.name, ", ".join("0x%08X" % b for b in bad)))
    return rel


def check_anchors(pe, anchors):
    for va, hx, desc in anchors:
        want = bytes.fromhex(hx)
        got = pe.rd(va, len(want))
        if got != want:
            sys.exit("ABORT: %s 0x%08X (%s) is %s, expected %s"
                     % (pe.name, va, desc, got.hex(), want.hex()))


def dll_target(dblob):
    pe = PE(os.path.join(GAME, DLL_NAME))
    for va in (D_HOOK, D_EXEC, D_GATE, D_CAVE, D_SPAN_END - 1, F_GETPLAYERS, F_PMEL_CREATE,
               TR_DAY1, GRANT_ENTRY):
        s = pe.sec_of(va)
        if s is None or s[0] != "CODE":
            sys.exit("ABORT: 0x%08X is not in AoWEPACK.dpl CODE" % va)
    check_anchors(pe, D_ANCHORS)
    rel = check_reloc(pe, [(D_HOOK, 5), (D_EXEC, 2), (D_GATE, D_GATE_LEN),
                           (D_CAVE, D_SPAN_END - D_CAVE)])
    # both class VMTs are derived PIC; prove each constant is that class's vmtSelfPtr target
    for cref, vmt, name in ((PMEL_CLASSREF, PMEL_VMT, b"TPlayerMagicEventLog"),
                            (TARMY_CLASSREF, TARMY_VMT, b"TArmy")):
        if struct.unpack("<I", pe.rd(cref, 4))[0] != vmt or cref != vmt - 0x40:
            sys.exit("ABORT: [0x%08X] is not the vmtSelfPtr of 0x%08X" % (cref, vmt))
        if cref not in rel:
            sys.exit("ABORT: the vmtSelfPtr cell 0x%08X carries no .reloc entry" % cref)
        cn = struct.unpack("<I", pe.rd(vmt - 0x20, 4))[0]
        if pe.rd(cn + 1, pe.rd(cn, 1)[0]) != name:
            sys.exit("ABORT: VMT 0x%08X is not %s" % (vmt, name.decode()))
    # nothing may branch into a displaced run except the whitelisted immediate byte
    for src in (pe.inbound(D_HOOK + 1, D_HOOK + 4) + pe.inbound(D_EXEC + 1, D_EXEC + 1)
                + pe.inbound(D_GATE + 1, D_GATE + D_GATE_LEN - 1)):
        w = D_WHITELIST.get(src)
        if not w or pe.rd(w[0], len(w[1])) != w[1]:
            sys.exit("ABORT: a branch at 0x%08X lands inside a patched run" % src)
    sites = [(D_HOOK, D_HOOK_ORIG, jmp_rel32(D_HOOK, C_RAISE), "NewTurn day-1 -> C_RAISE"),
             (D_EXEC, D_EXEC_ORIG, D_EXEC_NEW, "Execute: mode >= 3 executes"),
             (D_GATE, D_GATE_ORIG, jmp_rel32(D_GATE, C_GATE) + b"\x90" * (D_GATE_LEN - 5),
              "MagicControl.NewTurn grant tests -> C_GATE")]
    return Target(pe, sites, D_CAVE, D_SPAN_END, dblob, DLL_KNOWN_BODIES)


# build_tierresearch_dll.py cave_day1 v2 (a callable routine), sha256 of its 0xB6 bytes.
# C_APPLY CALLS it; if that script ever changes the routine, this pin makes --apply abort.
TR_DAY1_SHA = "95614e3618bd80ef0bf4c744cf67d6057151b3de8f9e580e8606293e26b08575"


def dependencies(pe):
    """-> [(name, ok, detail)].  Stage 2 needs build_tierresearch_dll.py v2 (C_APPLY calls its
    routine) and build_hero_turn1_upgrade.py either absent or v3 (the leader guard)."""
    out = []
    call = pe.rd(GRANT_ENTRY, 7)
    back = pe.rd(TR_BACK, 5)
    body = pe.rd(TR_DAY1, TR_DAY1_LEN)
    sha = hashlib.sha256(body).hexdigest()
    ok = (call == b"\xE8" + struct.pack("<i", TR_DAY1 - (GRANT_ENTRY + 5)) + b"\x90\x90"
          and back == jmp_rel32(TR_BACK, GRANT_SKIP)
          and body.endswith(bytes.fromhex("83c408c3")) and sha == TR_DAY1_SHA)
    out.append(("build_tierresearch_dll.py cave_day1 v2 (callable)", ok,
                "hook %s, back %s, routine sha %s..." % (call.hex(), back.hex(), sha[:16])))

    import build_hero_turn1_upgrade as T1
    caves = T1.build_caves()
    cur = {va: pe.rd(va, n) for va, (_o, _p, n, _d) in T1.SITES.items()}
    sites_on = all(cur[va] == p() for va, (_o, p, _n, _d) in T1.SITES.items())
    sites_off = all(cur[va] == o() for va, (o, _p, _n, _d) in T1.SITES.items())
    span = pe.rd(T1.CAVE_BASE, T1.CAVE_END - T1.CAVE_BASE)
    want = bytearray(len(span))
    for va, blob in caves.items():
        want[va - T1.CAVE_BASE:va - T1.CAVE_BASE + len(blob)] = blob
    if sites_on and span == bytes(want):
        out.append(("build_hero_turn1_upgrade.py", True, "v3 applied (leader guard present)"))
    elif sites_off and not any(span):
        out.append(("build_hero_turn1_upgrade.py", True, "not installed (no artificial lag)"))
    else:
        out.append(("build_hero_turn1_upgrade.py", False,
                    "installed WITHOUT the v3 leader guard -- run it with --apply first"))
    return out


def hsr_dependency(pe):
    """-> (name, ok, detail) for build_heroskill_race.py in one exe.  C_OFFER reads its table at
    HSR.TABLE_VA and copies its hash; with that script undone the table reads 0, every threshold is
    0 and the PBEM window's Available list comes up empty."""
    st, detail = HSR.state(bytearray(pe.d))
    return ("build_heroskill_race.py table in %s" % pe.name, st == "on",
            "%s (%s)" % (st, HSR.STATE_TEXT.get(st, detail)))


def exe_target(name, xblob, xlab, strict=False):
    pe = PE(os.path.join(GAME, name))
    s = pe.sec_of(X_SPAN)
    if s is None or pe.sec_of(X_SPAN_END - 1) is not s:
        sys.exit("ABORT: %s: 0x%08X..0x%08X is not inside one file-backed section"
                 % (name, X_SPAN, X_SPAN_END))
    if s[5] & 0xA0000000 != 0xA0000000:
        sys.exit("ABORT: %s: section %s (0x%08X) is not WRITE+EXECUTE" % (name, s[0], s[5]))
    check_anchors(pe, X_ANCHORS)
    check_reloc(pe, [(X_HOOK, 5), (X_OFFER, len(X_OFFER_ORIG)), (X_SPAN, X_SPAN_END - X_SPAN)])
    if pe.inbound(X_HOOK + 1, X_HOOK + 4) or pe.inbound(X_OFFER + 1, X_OFFER + 5):
        sys.exit("ABORT: %s: a branch lands inside a patched run" % name)
    check_panels(pe)
    # the offer table: build_heroskill_race.py's own pattern search + table check, every run.
    # ⚠ Required for --apply only.  Demanding it for --undo made this feature impossible to remove
    # once build_heroskill_race.py had been undone (QA 2026-09-24); the cave blob uses that
    # script's constants, never its installed state, so --undo and the dry run need nothing from it.
    n_, ok_, d_ = hsr_dependency(pe)
    if strict and not ok_:
        sys.exit("ABORT: %s: build_heroskill_race.py reads %s -- the offer roll reads its "
                 "table at 0x%08X and copies its hash; run that script first"
                 % (name, d_, HSR.TABLE_VA))
    sites = [(X_HOOK, jmp_rel32(X_HOOK, X_EPI), jmp_rel32(X_HOOK, X_SHOW),
              "TheMapExecuteEventLog mode>=3 -> C_SHOW"),
             (X_OFFER, X_OFFER_ORIG, jmp_rel32(X_OFFER, xlab["C_OFFER"]) + b"\x90",
              "TLeaderSetupWin available list -> C_OFFER")]
    return Target(pe, sites, X_SPAN, X_SPAN_END, xblob, EXE_KNOWN_BODIES)



def dfm_titlewin_panels(pe):
    """Every (form class, component) in the exe's DFMs whose AOWWindow resolves to TitleWin
    ('TitleWindow.TitleWin' from other forms, 'TitleWin' inside TTitleWindow itself)."""
    d = bytes(pe.d)

    def rstr(o):
        return d[o + 1:o + 1 + d[o]].decode("latin1"), o + 1 + d[o]

    def value(o):
        vt = d[o]
        o += 1
        if vt in (0, 8, 9, 13):
            return None, o
        if vt in (2, 3, 4):
            return None, o + {2: 1, 3: 2, 4: 4}[vt]
        if vt == 5:
            return None, o + 10
        if vt in (6, 7):
            s, o = rstr(o)
            return (("id", s) if vt == 7 else s), o
        if vt in (10, 12):
            return None, o + 4 + struct.unpack_from("<i", d, o)[0]
        if vt == 11:
            while True:
                s, o = rstr(o)
                if not s:
                    return None, o
        if vt == 1:
            while d[o]:
                _v, o = value(o)
            return None, o + 1
        if vt == 14:
            while d[o]:
                if d[o] in (2, 3, 4):
                    _v, o = value(o)
                if d[o] == 1:
                    o += 1
                while True:
                    pn, o = rstr(o)
                    if not pn:
                        break
                    _v, o = value(o)
            return None, o + 1
        if vt in (15, 16, 17):
            return None, o + {15: 4, 16: 8, 17: 8}[vt]
        if vt == 18:
            return None, o + 4 + 2 * struct.unpack_from("<i", d, o)[0]
        raise ValueError("DFM value type %d" % vt)

    def node(o, out, form):
        b = d[o]
        if b & 0xF0 == 0xF0:
            o += 1
            if b & 2:
                _v, o = value(o)
        cls, o = rstr(o)
        name, o = rstr(o)
        if form is None:
            form = cls
        win = None
        while True:
            pn, o = rstr(o)
            if not pn:
                break
            v, o = value(o)
            if pn == "AOWWindow" and isinstance(v, tuple):
                win = v[1]
        if win in ("TitleWindow.TitleWin",) or (form == "TTitleWindow" and win == "TitleWin"):
            out.add((form, name))
        while d[o]:
            o = node(o, out, form)
        return o + 1

    found = set()
    at = d.find(b"TPF0")
    while at >= 0:
        try:
            node(at + 4, found, None)
        except (ValueError, IndexError, struct.error):
            pass
        at = d.find(b"TPF0", at + 1)
    return found


def check_panels(pe):
    """The panel table is complete, and each row really is that form's field, created at
    startup into that global."""
    want = {(c, p) for c, p, _g, _f, _s in TITLE_PANELS} | {SHOWN_PANEL[:2]}
    got = dfm_titlewin_panels(pe)
    if got != want:
        sys.exit("ABORT: %s: TitleWin panels in the DFMs %s differ from the table %s"
                 % (pe.name, sorted(got ^ want), "(symmetric difference)"))
    for cls, pnl, gv, fld, site in TITLE_PANELS + [SHOWN_PANEL]:
        rel = struct.unpack("<i", pe.rd(site + 1, 4))[0]
        seq = pe.rd(site - 14, 14)
        if (pe.rd(site, 1) != b"\xE8" or site + 5 + rel != F_CREATEFORM
                or seq[:2] != b"\x8b\x0d" or struct.unpack("<I", seq[2:6])[0] != gv
                or seq[6:10] != b"\x8b\x03\x8b\x15"):
            sys.exit("ABORT: %s: 0x%08X is not CreateForm(%s) into [0x%08X]"
                     % (pe.name, site, cls, gv))
        cref = struct.unpack("<I", seq[10:14])[0]
        vmt = struct.unpack("<I", pe.rd(cref, 4))[0]
        cn = struct.unpack("<I", pe.rd(vmt - 0x20, 4))[0]
        if pe.rd(cn + 1, pe.rd(cn, 1)[0]).decode("latin1") != cls:
            sys.exit("ABORT: %s: CreateForm at 0x%08X builds a different class" % (pe.name, site))
        ft = struct.unpack("<I", pe.rd(vmt - 0x2C, 4))[0]
        n = struct.unpack("<H", pe.rd(ft, 2))[0]
        p, ok = ft + 6, False
        for _ in range(n):
            f = struct.unpack("<I", pe.rd(p, 4))[0]
            ln = pe.rd(p + 6, 1)[0]
            if f == fld and pe.rd(p + 7, ln).decode("latin1") == pnl:
                ok = True
            p += 7 + ln
        if not ok:
            sys.exit("ABORT: %s: %s.%s is not published at +0x%X" % (pe.name, cls, pnl, fld))


def lockstep_ok():
    a = open(os.path.join(GAME, zigexe.GAME_EXE), "rb").read()
    b = open(os.path.join(GAME, zigexe.COMPAT_EXE), "rb").read()
    if len(a) != len(b):
        return False, "size mismatch %d vs %d" % (len(a), len(b))
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if diff == [zigexe.COMPAT_BYTE]:
        return True, "lockstep ok: the pair differs at file 0x%X only" % zigexe.COMPAT_BYTE
    return False, "LOCKSTEP BROKEN: %d differing bytes %s" % (len(diff), [hex(x) for x in diff[:8]])


# ============================================================== reporting ======
NAMES = {
    F_GETPLAYERS: "TPlayerList.GetPlayers", F_PMEL_CREATE: "TPlayerMagicEventLog.Create",
    D_RESUME: "NewTurn resume", T_GETPLAYERS: "GetPlayers (thunk)",
    T_LSC_CREATE: "TLeaderSetupControl.Create (thunk)", T_SETOVERPRI: "SetOverPri (thunk)",
    F_SETUP: "TLeaderSetupWin.Setup", X_EPI: "epilogue",
    F_SYNC_BEGIN: "TAoWHSMap.SynchroniseBegin", F_SYNC_END: "TAoWHSMap.SynchroniseEnd",
    F_UFL_BEGIN: "THero.UpdateFromLibraryBegin", F_UFL_END: "THero.UpdateFromLibraryEnd",
    F_ISCLASS: "System.@IsClass", F_UPDATEFORMATION: "TArmy.UpdateFormation",
}


def disassemble(dblob, dlab, xblob, xlab):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        sys.exit("capstone not installed:  pip install capstone")
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    names = dict(NAMES)
    names.update({xlab["C_PANEL"]: "C_PANEL", TR_DAY1: "tierresearch cave_day1 (the grant)",
                  GRANT_ENTRY: "the grant's call (tierresearch v2)", GRANT_SKIP: "grant host resume",
                  X_OFFER_RESUME: "CanExpand", X_OFFER_REJECT: "next index (reject)"})
    blobs = {rngstd.basis(): "rngstd.basis", rngstd.mix(): "rngstd.mix",
             rngstd.fmix32(): "rngstd.fmix32", rngstd.range_n(100): "rngstd.range_n(100)"}

    def dump(title, blob, va, anchors=()):
        print("\n---- 0x%08X  %s  (%d B)" % (va, title, len(blob)))
        for i in md.disasm(blob, va):
            note = ""
            try:
                note = names.get(int(i.op_str, 16), "")
            except ValueError:
                pass
            for a, what in anchors:
                if i.address == a:
                    note = "anchor: reg = runtime 0x%08X" % a
                elif i.mnemonic == "add" and i.address == a + 1:
                    note = what
            print("  %08X  %-24s %s %s%s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str,
                                            ("  ; " + note) if note else ""))

    dump("C_RAISE  AoWEPACK.dpl", dblob[:C_GATE - D_CAVE].rstrip(b"\xcc"), C_RAISE,
         [(dlab["ANCHOR"], "-> TPlayerMagicEventLog VMT 0x%08X" % PMEL_VMT)])
    dump("C_GATE  AoWEPACK.dpl", dblob[C_GATE - D_CAVE:C_APPLY - D_CAVE].rstrip(b"\xcc"), C_GATE)
    dump("C_APPLY  AoWEPACK.dpl", dblob[C_APPLY - D_CAVE:], C_APPLY,
         [(dlab["A_ANCHOR"], "-> TArmy VMT 0x%08X" % TARMY_VMT)])
    print("\n---- exe globals 0x%08X: G_EVENT 0x%08X  G_CODE 0x%08X  G_DATA 0x%08X  G_MODAL 0x%08X"
          % (X_SPAN, G_EVENT, G_CODE, G_DATA, G_MODAL))
    for title, a, b in (("C_SHOW", X_SHOW, xlab["C_DONE"]), ("C_DONE", xlab["C_DONE"], xlab["C_PANEL"]),
                        ("C_PANEL", xlab["C_PANEL"], xlab["C_OFFER"]),
                        ("C_OFFER", xlab["C_OFFER"], xlab["PANELS"])):
        body = xblob[a - X_SPAN:b - X_SPAN]
        dump("%s  AoWz.exe / AoWzCompat.exe" % title, body.rstrip(b"\xcc") if title != "C_OFFER"
             else body.rstrip(b"\xcc"), a)
        if title == "C_OFFER":
            for blob, nm in blobs.items():
                k = body.find(blob)
                print("      %-20s at 0x%08X (%d B, verbatim)" % (nm, a + k, len(blob)))
    print("\n---- 0x%08X  PANELS  (%d x 8 B: form global, field)" % (xlab["PANELS"], len(TITLE_PANELS)))
    for k, (cls, pnl, gv, fld, _s) in enumerate(TITLE_PANELS):
        print("  %08X  [[[0x%08X]] + 0x%03X]   %s.%s" % (xlab["PANELS"] + 8 * k, gv, fld, cls, pnl))
    print("---- 0x%08X  G_VIS  (%d saved visible bytes; 16 reserved)" % (xlab["G_VIS"], len(TITLE_PANELS)))
    print("---- 0x%08X  G_PLAYER  (the event's TPlayer while the window is open)" % xlab["G_PLAYER"])
    print("---- exe body 0x%08X..0x%08X, %d B;  DLL body 0x%08X..0x%08X, %d B"
          % (X_SPAN, X_SPAN + len(xblob), len(xblob), D_CAVE, D_CAVE + len(dblob), len(dblob)))
    for va, orig, new, desc in (
            (D_HOOK, D_HOOK_ORIG, jmp_rel32(D_HOOK, C_RAISE), "AoWEPACK.dpl  NewTurn hook"),
            (D_EXEC, D_EXEC_ORIG, D_EXEC_NEW, "AoWEPACK.dpl  Execute mode switch"),
            (D_GATE, D_GATE_ORIG, jmp_rel32(D_GATE, C_GATE) + b"\x90" * (D_GATE_LEN - 5),
             "AoWEPACK.dpl  grant gate"),
            (X_HOOK, jmp_rel32(X_HOOK, X_EPI), jmp_rel32(X_HOOK, X_SHOW), "exe  dispatch"),
            (X_OFFER, X_OFFER_ORIG, jmp_rel32(X_OFFER, xlab["C_OFFER"]) + b"\x90", "exe  offer roll")):
        print("\n---- site 0x%08X  %s" % (va, desc))
        for label, run in (("vanilla", orig), ("patched", new)):
            for i in md.disasm(run, va):
                print("  %s  %08X  %-14s %s %s" % (label, i.address, i.bytes.hex(),
                                                   i.mnemonic, i.op_str))


def report(targets):
    for t in targets:
        print("%s  state: %s" % (t.pe.name, t.state().upper()))
        for va, o, p, desc in t.sites:
            cur = t.pe.rd(va, len(o))
            tag = "PATCHED" if cur == p else "orig" if cur == o else "*** FOREIGN ***"
            print("  site 0x%08X  %-8s %s  (%s)" % (va, tag, cur.hex(), desc))
        span = t.span_bytes()
        used = len(t.blob)
        known = t.installed_known()
        tag = ("ours" if span[:used] == t.blob and not any(span[used:]) else
               "zero" if not any(span) else
               "earlier body of this script (%s)" % known if known else "*** OTHER ***")
        print("  span 0x%08X..0x%08X  %-6s  body %d B" % (t.span, t.span_end, tag, used))


# ================================================================== main =======
def main():
    args = set(sys.argv[1:])
    unknown = args - {"--apply", "--undo", "--dis", "--show"}
    if unknown or ("--apply" in args and "--undo" in args):
        sys.exit("usage: build_pbem_leadersetup.py [--apply | --undo] [--dis]")

    dblob, dlab = build_dll_caves()
    xblob, xlab = build_exe_cave()
    if args & {"--dis", "--show"} and not args & {"--apply", "--undo"}:
        disassemble(dblob, dlab, xblob, xlab)
        return

    targets = [dll_target(dblob)] + [exe_target(n, xblob, xlab, strict="--apply" in args)
                                     for n in zigexe.EXES]
    ok, msg = lockstep_ok()
    if not ok:
        sys.exit("ABORT: %s" % msg)
    deps = dependencies(targets[0].pe) + [hsr_dependency(t.pe) for t in targets[1:]]
    if "--apply" in args and not all(ok for _n, ok, _d in deps):
        for n, ok, d in deps:
            print("  %-52s %s  %s" % (n, "ok " if ok else "NO ", d))
        sys.exit("ABORT: a stage-2 dependency is not in place -- nothing written")

    if "--apply" in args or "--undo" in args:
        states = {t.pe.name: t.state() for t in targets}
        bad = [n for n, s in states.items() if s == "mixed"]
        if bad:
            report(targets)
            sys.exit("ABORT: foreign or partial bytes in %s -- nothing written" % ", ".join(bad))
        exe_states = {states[n] for n in zigexe.EXES}
        if len(exe_states) != 1:
            sys.exit("ABORT: the exe pair is in different states %s" % exe_states)

    if "--apply" in args:
        if any(t.state() != "applied" for t in targets):
            kill_game()
        for t in targets:
            st = t.state()
            if st == "applied":
                print("%s: already applied" % t.pe.name)
                continue
            if st == "vanilla":
                # ⚠ the snapshot is gated on a POSITIVE test against the original bytes
                os.makedirs(BACKUP_DIR, exist_ok=True)
                bk = os.path.join(BACKUP_DIR, t.pe.name + ".pre-" + FEATURE)
                shutil.copy2(t.pe.path, bk)
                print("%s: backup -> backups\\%s" % (t.pe.name, os.path.basename(bk)))
            else:
                print("%s: older body in the reservation -- rewriting in place, no backup"
                      % t.pe.name)
            t.apply()
            t.pe.save()
            print("%s: applied" % t.pe.name)
        print(lockstep_ok()[1])
        targets = [dll_target(dblob)] + [exe_target(n, xblob, xlab) for n in zigexe.EXES]
    elif "--undo" in args:
        for t in targets:
            st = t.state()
            if st == "vanilla":
                print("%s: not applied" % t.pe.name)
                continue
            if st == "stale":
                sys.exit("ABORT: %s holds an older body; run --apply first so --undo zeroes "
                         "exactly what is installed" % t.pe.name)
        kill_game()
        for t in targets:
            if t.state() == "applied":
                t.undo()
                t.pe.save()
                print("%s: undone (sites restored, %d B zeroed, no backup touched)"
                      % (t.pe.name, len(t.blob)))
        print(lockstep_ok()[1])
        targets = [dll_target(dblob)] + [exe_target(n, xblob, xlab) for n in zigexe.EXES]
    else:
        disassemble(dblob, dlab, xblob, xlab)
        print()

    report(targets)
    print("dependencies (other scripts' caves this feature relies on):")
    deps = dependencies(targets[0].pe) + [hsr_dependency(t.pe) for t in targets[1:]]
    for n, ok, d in deps:
        print("  %-52s %s  %s" % (n, "ok " if ok else "NO ", d))
    states = {t.state() for t in targets}
    # ⚠ The verdict folds the dependencies in: all three files applied over a v1 cave_day1 is a live
    # state in which C_APPLY's call never returns, and it used to print INTACT (QA 2026-09-24).
    missing = [n for n, ok, _d in deps if not ok]
    if states == {"applied"}:
        verdict = ("INTACT (all three applied)" if not missing else
                   "BROKEN -- all three applied but a dependency is missing: %s"
                   % "; ".join(missing))
    elif states == {"vanilla"}:
        verdict = "not installed"
    else:
        verdict = "INCONSISTENT %s" % sorted(states)
    print("\nchain: %s" % verdict)
    if not args & {"--apply", "--undo"}:
        print("(dry run -- pass --apply to write, --undo to revert)")


if __name__ == "__main__":
    main()
