# RNG lockstep — which generator a cave must draw from

**Status: CONFIRMED from the binaries (2026-08-31).** Every claim below is derived from
`AoWEPACK_original_backup.dpl` (pristine) and the live modules, not from reasoning about
what a lockstep engine "should" do. Audit tool: `re_tools/rng_audit.py`.

AoW1 has **two random generators** and they are not interchangeable. Picking the wrong one
is silent — it assembles, it verifies, it plays perfectly in single player, and it diverges
the map on the first cast of a LAN game.

---

## 1. The two generators

### SYNCED — `AoWE.TAoWHSMap.Random @0x5577827C`

```
EAX = map instance, EDX = n   ->   EAX in 0..n-1
```

It **is** `System.@RandInt` with the replicated seed swapped in and out (vanilla body):

```asm
5577827C  push ebx / push esi / mov esi,edx / mov ebx,eax
55778282  mov  eax,[0x558FA040]           ; AoWE.AoWHSMap (the flag map)
55778287  test byte ptr [eax+0x3c], 8
5577828B  jne  0x557782CB                 ; flag set -> plain RandInt, NO bookkeeping
5577828D  call 0x55775608                 ; TAoWHSMap.GetSynchronised
55778294  test al,al
55778296  je   0x557782BC                 ; not synchronised -> ShowMessage + return 0
55778298  mov  eax,[0x558FB720]           ; &System.RandSeed
5577829D  mov  edx,[ebx+0x230]            ; the REPLICATED seed
557782A3  mov  [eax],edx                  ;   -> RandSeed
557782A5  mov  eax,esi
557782A7  call 0x55701080                 ; System.@RandInt
557782AC  mov  edx,[0x558FB720]
557782B2  mov  edx,[edx]
557782B4  mov  [ebx+0x230],edx            ; advanced seed written BACK
```

- `map[+0x230]` is replicated state, so every peer walks the same sequence.
- It is also **the value the out-of-sync comparator reads** —
  `TPlayerControl.GetSyncValue @0x55754CE8` returns `[AoWHSMap+0x230]`.
- Outside a synchronised context it pops the modal
  **"Invalid AoWHSMap.Random use"** and returns 0.

Canonical call site (copied verbatim from vanilla `TIceStorm.ChangeStormTerrain @0x557CCF12`):

```asm
mov  eax, [0x558E9494]     ; ptr -> AoWE.AoWHSMap
mov  eax, [eax]            ; the map
mov  edx, N
call 0x5577827C
```

Registers: pushes/pops EBX and ESI (so those survive), returns in EAX, **clobbers EAX, EDX,
ECX and flags**. ECX is the one that catches people out — in a terrain hook ECX is usually
the pointer to the terrain byte. Push it.

### RAW — `System.@RandInt`, AoWEPACK thunk `0x55701080`

`jmp [0x558FB6DC]` → `VCL30.dpl!System.@RandInt`, body at `0x41303384`. `EAX = n` → `0..n-1`.
Draws from `System.RandSeed`, a **per-process global**. Two machines running the same code
get different numbers, and nothing detects it.

`System.@RandInt` is a multiply-shift, not a `%` — `RandInt(4)` is literally the top two seed
bits, so `RandInt(4) < 3` is exactly 75.000%. Do not "fix the bias".

---

## 2. The rule

> **A cave draws from the generator the function it is injected into already uses.**
> Where that function makes no draw of its own, the generator is decided by what the roll
> decides — replicated game state ⇒ SYNCED; pixels ⇒ RAW.

Check it with one command before writing the cave:

```bash
python "Modding Resources/re_tools/rng_audit.py" AoWEPACK.dpl --functions
```

That prints, for the pristine DLL, every function that draws and which generator it uses.
If the hook target is in the SYNC list, the cave uses `0x5577827C`. If it is in the RAW
list, the cave uses `0x55701080` and inherits whatever property vanilla already had there.

### Why "match the function" and not "always use the synced one"

Vanilla is not sloppy about this — it draws **111 synced** and **110 raw** times, and the
split is principled:

| vanilla uses SYNCED in | vanilla uses RAW in |
|---|---|
| `*.ExecuteTE`, `*.Execute`, `*.Process`, `NewTurn`, `NewDay` | `*.Show`, `*.ShowAnimation`, `*.NewFrame`, `UpdateTransition` |
| `TAoWHSMap.ChangeTerrain` / `ChangeTerrainEx` / `PlaceTerrain` | `TCity.Show`, `TStructure.ShowRazeAnimation`, `TWorldFXHS.NewFrame` |
| `TRaiseTerrainTE.RaiseTerrain`, `TIceStorm.ChangeStormTerrain` | `TFireStorm.UpdateStorm` (frame counter, not state) |
| `TCity.CheckRebellion`, `GenerateDefenders` (PrdPlace), `TItemHS.GenerateItems` | `ExecuteDamageRole`, `HitRole` — **combat rolls** |
| `TCombat.Execute` (the per-combat re-anchor, see below) | `TSetupControl.hPickMap`, `TEmailGameControl.*`, `FillWithRandomUnits` — pre-game / map generation |
| every AI `Process` / `ExecuteAI` | `TAoWWaterHexagon.Create/ShowDynamic` — tile art phase |

**Inside tactical combat, RAW is the correct answer and SYNCED is the wrong one.**
`TCombat.Execute @0x557282C8` is nothing but one line:

```asm
557282C8  mov  edx, 0xFFFFFF
557282CD  mov  eax, [0x558FA040]
557282D2  call 0x5577827C            ; TAoWHSMap.Random(map, $FFFFFF)
557282D7  mov  edx, [0x558FB720]
557282DD  mov  [edx], eax            ; System.RandSeed := that
```

So a battle re-anchors `System.RandSeed` from **one** synchronised draw and then runs the
whole fight off raw draws, deterministically, on every peer. Calling the synced generator
mid-combat would be wrong twice over: `GetSynchronised` is false there (modal popup, returns
0), and it would advance `[map+0x230]` — the very value the desync comparator watches.

That single-draw re-anchor is also the sanctioned **bridge** when a cave must use raw draws
in a synchronised context (e.g. it calls an engine routine that draws internally):
`System.RandSeed := TAoWHSMap.Random(map, $FFFFFF)` **first**, then call the routine.
`build_arena.py` does exactly this before `GenerateItem`, and vanilla
`TItemExplorationSite.Generate` does the same.

### ⭐⚠ The second rule: inside combat, the DRAW COUNT is the invariant

Because of that re-anchor, "RAW = every machine gets a different number" is **false inside a
battle**. Both peers start the fight from the same seed, so the raw stream is replicated —
**but only while both consume the same NUMBER of `@RandInt` draws.**

> **A conditional raw draw in combat is a silent desync.** It assembles, it verifies, it plays
> perfectly in single player, and it is invisible to the out-of-sync comparator (which watches
> `[map+0x230]`, untouched by raw draws). The symptom surfaces later and elsewhere: one peer's
> to-hit rolls shift by one draw, units die differently, and the OOS dialog finally fires on some
> unrelated synced draw.

So picking the right *generator* is necessary but not sufficient. A cave in a combat context must
also draw the **same number of times on every path**. Where a roll is gated, hoist the draw out of
the gate and gate only the *store* — discarding an unwanted result costs one draw uniformly on
every machine and preserves determinism exactly.

⚠ **Hoisting is only safe if the draw's INPUTS are safe to evaluate on the rejected path too.**
This is the trap: it looks like a pure refactor and is not. Worked example, `TMindDecay.CreateCA`
(`build_minddecay_oos.py` — 🔨 **APPLIED, UNTESTED (2026-09-03)**, full write-up in
`MindDecay_OOS_Fix.md`) — its `HitRole` sits behind five gates, four of which
dereference the target's strategic unit `[combatunit+0x4C]`. The obvious move is to hoist the whole
expression `[spell+0x34] − target.GetResistance()`. **That AVs.** `GetResistance` is VMT `+0x74`,
a `TCombatObject` base slot (`0x55726864` = `xor eax,eax; ret`, harmless) — but `TCombatUnit`
**overrides** it at `0x557254A8` with `mov eax,[eax+0x4C]` → `call [edx+0xCC]`, i.e. the very
dereference the gates were protecting. Hoist the **call** only, substitute a constant for the
input on the rejected path. Draw-count invariance depends on the number of `HitRole` calls, not on
what they are passed.

⚠ Verify the callee actually draws unconditionally before relying on it. `HitRole @0x55725D98`
makes exactly **one** `@RandInt` call, with only forward clamp branches around it — check this by
disassembly rather than assumption, and have the build script assert it at write time.

**Vanilla is not clean here.** `TMindDecay`'s gate chain is byte-identical to
`AoWEPACK_original_backup.dpl`, so this defect is stock AoW1, not something the mod introduced.
Assume other conditional combat draws exist; `HitRole`'s callers are the place to look —
`TStrikeCA.Generate` (×2), `TTouchAbility.CombatTouchRole` (×2),
`TTurnUndeadAbility.CreateTurnUndeadCA`, `ExecuteLifeMasteryFearRole`,
`ExecuteDeathMasteryCurseRole`, `ExecuteResistanceRole`, `TBurningAbility.NewCombatTurn`,
`TMindDecay`/`TSlow`/`TEntangle.CreateCA`, `TFastCombatTerrorCA`/`TTacticalCombatTerrorCA.Generate`.

⚠ `rng_audit.py` **cannot see this class of bug.** It matches references to the RNG *entry points*;
a cave that reaches the generator through a caller like `HitRole` adds no site and the count does
not move. The audit proves you picked the right generator, not that your draw count is symmetric.

### The trap that makes a "synced" call silently raw

`TAoWHSMap.Random` skips all its seed bookkeeping when **bit 3 of `[*0x558FA040 + 0x3C]`**
is set (the branch to `0x557782CB` above). Setting that flag is the known way to suppress the
"Invalid AoWHSMap.Random use" popup when engine code you are calling draws internally from a
non-synchronised context — but understand what it buys: **it converts the draw to a raw one,
with no warning.** It silences the diagnostic; it does not make the call safe.
`build_raiseterrain_lavadirt.py`'s `cave_dirtdelay` uses it deliberately (see §4).

---

## 3. The audit tool

```bash
python "Modding Resources/re_tools/rng_audit.py"                 # every module vs its pristine ref
python "Modding Resources/re_tools/rng_audit.py" --owners        # attribute each site to a build script
python "Modding Resources/re_tools/rng_audit.py" --functions     # which functions draw, and from which generator
python "Modding Resources/re_tools/rng_audit.py" AoWEPACK.dpl --all-sites
```

It finds `call`/`jmp` rel32, `call`/`jmp [iat]`, **and bare address constants** in every
EXECUTE section — the last two matter because a cave can reach the RNG without a call target
the scan could match:

- the cross-module rebase-delta idiom (`add esi, 0x55701080 ; call esi`) leaves only a
  constant, and `build_party_random.py` uses it in `AoWDevEd.exe`;
- that cave lives in a custom `.pty` section, so a `CODE`/`.text` name whitelist misses it
  entirely. The tool walks section **characteristics** instead.

`--owners` maps a site to the nearest preceding VA literal in `build_scripts/` — an exact
grep for the call's own VA finds nothing, because the script only ever names the cave base.

Reference binaries: `AoWEPACK_original_backup.dpl` and `Ziggurat upload/AoW.exe` are pristine.
⚠ **`Ziggurat upload/AoWEPACK.dpl` and `Ziggurat upload/AoWTCPCK.dpl` are NOT** — they are a
snapshot of a patched build (hash differs from the pristine DLL). There is no vanilla
`AoWTCPCK.dpl` in the tree, so that module cannot be diffed; it is clean by inspection instead
(no script that patches it adds a draw — verified 2026-08-31).

---

## 4. Audit of every modded RNG site (2026-08-31; re-measured 2026-09-03)

22 modded sites in `AoWEPACK.dpl`, 3 in `AoWDevEd.exe`, none anywhere else.

**Re-measured 2026-09-03 — 24 modded sites in total.** Four features were applied on 2026-09-02/03;
their effect on this audit is:

| Feature (script) | new sites | note |
|---|---|---|
| `build_raiseterrain_ug_earth.py` | **+1** — `0x5583E095`, prints `ok` | `Random(0xB)` for the marker duration inside `TRaiseTerrainTE.RaiseTerrain`, which vanilla itself draws SYNC in twice. Also re-uses the shared `0x55827000` stub, so `0x55827011` now lists it as a fourth owner. `RaiseTerrain_UG_Earth.md` |
| `build_ai_sitesearch.py` | none | neither cave draws; the search's own rolls stay inside `ExecuteSearch` on the existing synced stream. `AI_Sites_And_Loot.md` |
| `build_ai_itemloot.py` | none | no cave draws; the script's own `selfcheck()` asserts it for call/jmp rel32 **and** bare address constants. `AI_Sites_And_Loot.md` |
| `build_minddecay_oos.py` | **none, by construction** | ⚠ it reaches the RNG through `HitRole`, a *caller*, so this audit cannot see it at all — see §2's second rule and `MindDecay_OOS_Fix.md` |

### Wrong generator — APPLIED 2026-08-31, NOT YET TESTED IN GAME

Fixed by `build_scripts/build_rng_lockstep.py` (24-byte `rng_sync` stub at `0x55827000`, three
`call` rel32s retargeted, `--undo` round-tripped). The three owning caves are otherwise
untouched — no cave grew, no branch target moved. **Needs the user's in-game test:** cast
Raise Terrain on lava, Ice Storm, and Fire Storm and confirm each still behaves as before
(the numbers that come out will differ — see "Behaviour" in the build script — but the
proportions and the visuals should be unchanged, and no "Invalid AoWHSMap.Random use" modal
should appear).

| site | cave | injected into | vanilla draws | was | now |
|---|---|---|---|---|---|
| `0x5580DB72` | `0x5580DB60` `cave_lavadirt` (`build_raiseterrain_lavadirt.py`) | `Mountain.TRaiseTerrainTE.RaiseTerrain` | **SYNC ×2** (`0x557A3397`, `0x557A346E`) | RAW | SYNC |
| `0x5580DB46` | `0x5580DB40` `cave_iceroll` (`build_icestorm_lava.py`) | `Storms.TIceStorm.ChangeStormTerrain` | **SYNC** (`0x557CCF1E`) | RAW | SYNC |
| `0x5580BEA8` | `0x5580BE74` Fire Storm terrain helper — **was orphaned, no build script** | `Storms.TFireStorm.ChangeStormTerrain` | none — but its sibling `TIceStorm.ChangeStormTerrain` uses SYNC through the same VMT slot | RAW | SYNC |

All three write **replicated terrain state** off a per-process seed, so peers would paint
different maps from the first cast. The Raise Terrain one is the clearest: vanilla draws
synced *twice in the same function*, once inside the very anim block the cave jumps into.

### Correct as they stand — do not "fix" these

| site | owner | why it is right |
|---|---|---|
| `0x5582310E` | `build_shield.py` — auto-resolve arc, `RandInt(4)<3` | inside combat; rides the seed `TCombat.Execute` re-anchored. A synced draw here would trip the guard *and* perturb the sync value. Reasoned out at length in that script's DETERMINISM block. |
| `0x558114E0` | `build_combatlog_dll.py` transparent logging cave | **replays** vanilla's own `ExecuteDamageRole` draw; adds no draw of its own. |
| `0x5580C50E`, `0x5580C52B` | orphan cave `0x5580C500` replacing `SummonSpells.TSummonSpell.SetupSummonSpellTE` | vanilla draws **raw** at the identical spot (`0x557E4491`); the added `RandInt(5)+3` multi-spawn inherits exactly vanilla's property. `SetupSummonSpellTE` populates the TE *before* `TTokenControl.AddEvent` submits it (`TSummonSpell.Activate @0x557E44B0`), i.e. it runs once on the initiating peer. |
| `0x55814200`, `0x55814495` | `build_arena.py` | the sanctioned bridge — `System.RandSeed := TAoWHSMap.Random(map,$FFFFFF)` before `GenerateItem`. |
| 13 sites | arena, crusade spawns, path-of-sand / outer-ring, tier research, site-defender vary, magebane, mastery cost, storm effect roll | already SYNC. |
| 3 sites in `AoWDevEd.exe` | `build_party_random.py` (`System.Randomize` + raw `RandInt`) | map **editor** only. No peers, nothing replicated; matches vanilla `TSetupControl.hPickMap`. |

### Known deviation, accepted

`build_raiseterrain_lavadirt.py`'s `cave_dirtdelay` sets the bit-3 flag around its
`ChangeTerrainEx` call, which turns that routine's internal **terrain-variant** draw from
synced into raw. It has to: the call is made from `NewFrameRaiseTerrainAnimation`, a
per-frame render callback where `GetSynchronised` is false and the unsuppressed call pops a
modal. Consequence: peers may pick different *tile art variants* for a converted hex. It does
not touch `[map+0x230]`, so it cannot trip the desync alarm; believed cosmetic, unverified.

⚠ Note the two contexts are different even within one feature: the TE body
(`TRaiseTerrainTE.RaiseTerrain`) **is** synchronised — that is where the 50% roll lives and
where SYNC works — while the frame-9 callback is not. Do not generalise one to the other.

---

## 5. Checklist for a new cave that rolls

1. `rng_audit.py --functions` → is the hook target in the pristine SYNC list or the RAW list?
2. Match it. If the function makes no draw, ask what the roll decides: replicated state ⇒ SYNC.
3. SYNC preamble is the 3-instruction one in §1. In a cave, `[0x558E9494]` needs the
   call/pop-delta anchor (`aow1-dpl-rebasing`) — it is an absolute data ref and the DPL rebases.
4. Save ECX across the call if you are holding a pointer in it.
5. Never mint a raw draw to dodge the "Invalid AoWHSMap.Random use" popup. The popup means
   the context is not synchronised — either the hook site is wrong, or the roll belongs
   further up in the TE body.
6. Re-run `rng_audit.py --owners` after `--apply` and confirm your site prints `ok`.
