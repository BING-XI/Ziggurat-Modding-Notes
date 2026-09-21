# Raise Terrain underground — Dirt becomes temporary Earth, with the Freeze Water sparkle

> **Status: 🔨 APPLIED, UNTESTED (2026-09-03).** Written to the live `AoWEPACK.dpl`; every static
> check and the scratch round-trip pass; **nobody has played it.** First applied 2026-09-02, then
> re-tuned in place on 2026-09-03 with the sparkle fix (P6). Promote to `✅ CONFIRMED WORKING` only
> on the user's in-game test (§10).

```
underground (level != 0) + Dirt(0x0C)  ->  Earth(7) for 2-4 of the caster's turns,
                                           then back to Dirt, with the green raise glow
                                           and the Freeze Water shimmer
```

Surface behaviour is untouched and no mountain placement changes anywhere.

| | |
|---|---|
| script | `build_scripts/build_raiseterrain_ug_earth.py` → `AoWEPACK.dpl` |
| backup | `AoWEPACK.dpl.pre-rtugearth` (taken 2026-09-02 from a file proved free of this feature) |
| revert | `python build_scripts/build_raiseterrain_ug_earth.py --undo` — surgical, writes immediately, touches no backup |
| ⚠ revert **order** | **undo this BEFORE `build_gripofwinter.py`** — see §6 |
| ⚠ hard dependency | **`build_gripofwinter.py` must stay applied** — without it the raised earth is PERMANENT. See §4 |
| part of | `Terrain_System_INDEX.md`; the marker machinery is `GripOfWinter_Design.md` §4 |

`VA = file_offset + 0x55700C00` (CODE). Terrain ids: 0 Water, 1 Grass, 2 Desert, 3 Snow, 4 Steppe,
5 Wasteland, 6 Ice, **7 Earth**, 8 Rock, 9 Lava, A CaveWater, B Chasm, **C Dirt**, D CaveIce, E Sky,
F Border.

---

## 1. Footprint — five byte-runs

| VA | bytes | what | whose code |
|---|---|---|---|
| `0x557A357C` | 1 | the surface-only flag immediate, `01` → `00` | vanilla `TRaiseTerrain.Create` |
| `0x5580DB6C` | 5 | `jne` rel8 `0x1C` → `0x26`, then `mov eax,2` → `jmp C_LAVAGATE` | **`build_raiseterrain_lavadirt.py`'s `cave_lavadirt`** |
| `0x5580DB93` | 5 | dead tail of a superseded lavadirt cut → `jmp C_UGDIRT` | same cave's dead bytes |
| `0x5582A4E0` | 6 | `cmp byte [eax+0x0E],0` + `jne` → `jmp C_SHOWGATE` + `nop` | **`build_gripofwinter.py`'s `C_SHOW`** |
| `0x5583E000` | 512 | our reservation: `C_UGDIRT` 267 B, `C_SHOWGATE` 22 B, `C_LAVAGATE` 29 B, remainder zero | ours, exclusively |

**Twelve bytes sit inside code that executes today**; the rest was zero or provably dead. `--dis`
prints the installed-vs-rewritten images of both foreign caves side by side and lists the measured
differing offsets — trust that over any prose here.

Exclusive zone `0x5583E000..0x55840000` (8 KB). `--undo` zeroes `0x5583E000..0x5583E200`; the tail
`0x5583E200..0x55840000` is asserted still zero on every run, which is the "assert the zone the cave
grows into is still zero" half of the in-place-rewrite rule.

---

## 2. P0 — underground casting is one byte, and the gate was never in `ValidTarget*`

`TGlobalTargetSpell`'s target-error routine `@0x5579E73C`:

```
cmp byte [esi+0x39], 0 ; je ok          <- a SURFACE-ONLY flag on the spell
<get x,y,level via 0x5577ED94>
cmp byte [ebp-7], 0    ; je ok          <- the level
<resourcestring [0x558E8FE4] "must be cast on the surface">
```

`TRaiseTerrain.Create` sets it: `mov byte [esi+0x39],1` at `0x557A3579`, opcode `c6 46 39`,
immediate at `0x557A357C`. **Fix: `0x01` → `0x00`.** The script pins the three opcode bytes as
context and refuses to write if they are not what it expects — a bare `01 → 00` on a wrong address
would be silent. (Diagnosed by Inioch, `Inioch/Inioch_Share6_Catalogue.md` §3 Tier 3; re-verified
here against both the live and the pristine DLL.)

⚠ Neither `ValidTargetMapF @0x557A35B8` nor `ValidTargetSelectionMapF @0x557A3610` has a level gate
at all — confirmed by reading both on this DLL. §9 lists what that still leaves open.

---

## 3. P1 — `C_UGDIRT` @ `0x5583E000`, 267 bytes

Reached by `jmp` from inside `cave_lavadirt`, for hexes that have already passed Raise Terrain's own
per-hex validity check. **No pushes anywhere along the way**, so ESP is exactly what it is at the
vanilla per-hex site `0x557A333E`:

```
[esp]   = Self       (vanilla reads the level from [Self+0x22] @0x557A33C0)
[esp+4] = arg2       (vanilla reads the caster  from [arg2+0x24] @0x557A33AC)
[esp+8] = map field  (stored @0x557A330D)
```

| step | detail |
|---|---|
| gate | `[field+0x14] == 0x0C` (Dirt) and `[Self+0x22] != 0` (underground); with `EXCLUDE_ROAD_OVERLAY`, also `[field+0x15] != 4` and `!= 5` |
| save | `push ebp; push edi` — the enclosing loop keeps EDI (field container, read at `0x557A32EA/F3/0x557A3306`) and EBP (mountain-resource list, `0x557A3345/0x557A334C`) live **across iterations** |
| anchor | `call $+5; pop ebp` at `0x5583E03A` — **one scheme, no `sub`**; `[ebp-0x1298C6]` = classref holder `0x55714774`, `[ebp+0xAB45A]` = map holder `0x558E9494` |
| find/create | `FindHS(field, classref)` thunk `0x55701FFC`; else `TEObject` create thunk `0x55703064` (eax=classref, dl=1, ecx=0); then `PlaceHX` thunk `0x557025F4` (eax=map, edx=hs, ecx=x, push level, push y) |
| duration | `Random(0xB)` via **`AoWE.TAoWHSMap.Random @0x5577827C`** at `0x5583E095`, then `(r-5)/5+3` → **2..4 owner turns** → `[hs+0x0C]`; caster `[arg2+0x24]` → `[hs+0x0D]`. Both copied positionally out of the host function (`0x557A3392`, `0x557A33AC`) — this is the raised mountain's own duration |
| stamp | `[hs+0x0E] = 0x0C` (restore Dirt) **only if it is still 0**, `[hs+0x0F] = 0x07` (we set Earth) |
| flip | map VMT `+0xD0` = `TAoWHSMap.ChangeTerrain @0x55778D84` (`ret 0x10`, four stack args) — **not** `ChangeTerrainEx @0x55778DCC` (`ret 0x1C`, seven). Shape: eax=map, edx=requester, ecx=x, stack: terrain, 0, level, y |
| glow | `pop edi; pop ebp; mov ebx,[esp+8]; jmp 0x557A3414` — the vanilla raise-glow block, which wants EBX = the map field. No mountain is placed |
| else | replay the two displaced instructions (`xor eax,eax; mov esi,[ebp+8]`) and `jmp 0x557A3343`, the vanilla mountain-resource scan |

Vanilla sites used: `RESUME 0x557A3343`, `ANIM 0x557A3414`, `CONT 0x557A3498`.

⭐ **Marker/flip ordering is deliberate: stamp `+0x0E`/`+0x0F` FIRST, then flip.** The flip's own
`TerrainChanged` notification reaches Grip of Winter's `C_HSTC`, which sees new terrain == `[+0x0F]`
and **keeps** the marker. Stamping afterwards would let `C_HSTC` destroy it. If the create fails the
cave bails to `CONT` without touching terrain, so a hex can never be left converted with no marker
to restore it.

⭐ **`PlaceHX`'s return is checked** (QA finding (a), fixed). Vanilla checks it at `0x557A3400`
(`test al,al; je CONT`) and so does the cave. If the hex's HS array is full, `TEObject.Create`
succeeds but `PlaceHX` fails, `[marker+4]` stays nil and `NewTurn` is never delivered — converting
anyway would strand the hex as Earth for ever. On that path the cave frees the orphan
(`mov dl,1; mov eax,ebx; mov ecx,[eax]; call [ecx-4]` — `Destroy` at **VMT−0x04**, the same call
`MeltIce` makes) and leaves the hex completely untouched. **Vanilla leaks its mountain object in the
equivalent case; we do not.**

⚠ **EDX on the `ChangeTerrain` call is the REQUESTER**, excluded from the `CanChangeTerrain` veto
poll (QA finding (b), fixed). Vanilla `MeltIce` passes the marker (`mov edx,ebx` @`0x55764B14`) and
so does Grip's `C_MELT` (@`0x5582A3DB`). Passing 0 worked only because `TArmyHS.CanChangeTerrain`
nil-checks it. The cave passes the marker, and does so **before** the `mov ebx,[eax]` that clobbers
EBX.

### RNG

`rng_audit.py --functions` puts `Mountain.TRaiseTerrainTE.RaiseTerrain` in the **SYNC** list (and
only there) for both the live and the pristine module, so the duration roll calls
`TAoWHSMap.Random` directly, exactly as vanilla does twice in this very function (`0x557A3397`,
`0x557A346E`). Measured with `rng_audit.py --owners` on 2026-09-03: **23 modded sites before, 24
after**, the new one being `0x5583E095`, which prints `ok`.

---

## 4. P2 — the temporary state is Grip of Winter's, and this feature DEPENDS on it

`build_gripofwinter.py` had already extended `TFrozenWaterHS` (VMT `0x557147B4`, classref holder
`0x55714774`, instance size `[VMT−0x1C]` = `0x10`) with precisely the two padding bytes this feature
needs:

| field | meaning |
|---|---|
| `[hs+0x0C]` | countdown, decremented on the owner's turn (vanilla) |
| `[hs+0x0D]` | owner player (vanilla) |
| `[hs+0x0E]` | terrain to **restore** — `0` means "plain vanilla ice marker" |
| `[hs+0x0F]` | terrain this marker **set** |

and the four consumers are already installed:

| Grip cave | VA | hook | does |
|---|---|---|---|
| `C_RW` | `0x5582A320` | `0x55764ACB` | `ReadWrite` persists `+0x0E` as property id `0x20` and `+0x0F` as `0x21` → **save/load already handled** |
| `C_MELT` | `0x5582A3A0` | `0x55764AE0` | `MeltIce`: `+0x0E != 0` and the hex still holds `+0x0F` → `ChangeTerrain` back to `+0x0E`, else `Destroy` → **the revert already handled** |
| `C_HSTC` | `0x5582A460` | `0x55764B8B` | `TerrainChanged`: `+0x0E != 0` → keep the marker while the hex holds `+0x0F`, else free it |
| `C_SHOW` | `0x5582A4E0` | `0x55764BD0` | `Show`: `+0x0E != 0` → draw nothing. **This is the sparkle gate — see §5** |

So this script writes **no** melt cave, **no** `TerrainChanged` cave and **no** `ReadWrite` cave. It
only mints a marker whose `+0x0E`/`+0x0F` say "restore Dirt, I set Earth".

⚠⚠ **`build_gripofwinter.py` must stay applied.** Without those four hooks the marker never melts
back and **the raised earth is permanent**. The script refuses to apply if any of the four sites
does not start with `E9`, or if the `C_SHOW` body is not one of the two images it knows:

```
ABORT: build_gripofwinter.py is not applied -- it owns the melt,
the save/load fields and the marker-survival rule. Without it the
raised earth would be PERMANENT. Missing hooks: ...
```

Property tables are **id-indexed**, so a save written before either feature simply lacks ids
`0x20`/`0x21` and loads both bytes as 0 = a vanilla ice marker.

---

## 5. P6 — the sparkle, and a correction to `GripOfWinter_Design.md`

First in-game test: *"underground dirt→earth converts and reverts, but there is no sparkle."* The
green raise glow was there (that is the vanilla ANIM block this feature jumps to); what was missing
was the Freeze Water shimmer that marks a hex as temporary.

**What `TFrozenWaterHS.Show` (VMT `+0xA8`, `@0x55764BD0`) actually does.** It makes exactly **one**
outbound call:

```
0x55764C60  call 0x5570291C   -> ILPACK.dpl!ImageLib.TImageSequenceList.ShowLoopedEx
              eax = [[0x558FA044]+0x94]    the image-sequence list
              edx = 0x46                   the sequence index
              ecx = screen x
              stack: canvas, phase, [[0x558FA040]+0x40], screen y
              phase = hexX + 3*hexY   (so adjacent hexes do not pulse in step)
              the third stack arg is the global anim tick
```

A looped image sequence driven by a global tick and a per-hex phase is an **animation**, and it is
the only thing `Show` draws. **It is the shimmer.** There is no ice tile here at all — the ice
*look* comes from the terrain byte (6 / 0xD) painted by the terrain renderer, not from `Show`. A
module-wide scan finds exactly one caller of `ShowLoopedEx` in the whole of `AoWEPACK.dpl`, and it
is this one.

⚠ **So Grip of Winter's "C_SHOW: no ice sprite over cooled land" is a misreading.** What `C_SHOW`
suppresses, for every marker with `+0x0E != 0`, is **the sparkle** — and our markers set
`+0x0E = Dirt`, so they were caught by it. The sparkle and the "ice sprite" are not separable,
because there is only the sparkle: `C_SHOW` is an all-or-nothing gate on precisely the thing the
user asked for. (`GripOfWinter_Design.md` §4 edit (d) and its in-game checklist item 4 describe it
the old way; this section is the corrected reading.)

**The fix.** Replace `C_SHOW`'s first six bytes with `jmp C_SHOWGATE` + `nop`, and re-implement the
predicate with one extra clause:

```
C_SHOWGATE @0x5583E140   (22 bytes)
  5583E140  80 78 0e 00   cmp byte [eax+0x0e], 0
  5583E144  74 06         je  0x5583E14C        ; plain ice marker -> shimmer
  5583E146  80 78 0f 07   cmp byte [eax+0x0f], 7
  5583E14A  75 05         jne 0x5583E151        ; Grip cooled land  -> still hidden
  5583E14C  e9 95 c3 fe ff  jmp 0x5582A4E6      ; gripofwinter's own vanilla replay
  5583E151  e9 9b c3 fe ff  jmp 0x5582A4F1      ; gripofwinter's own `ret 4`
```

**It does not return into itself.** Both outcomes jump back to `build_gripofwinter.py`'s own bytes,
still in place; its remaining 14 bytes are untouched and are still the code that executes.

**Proof Grip of Winter looks exactly as it did.** `+0x0E`/`+0x0F` are only ever written by Grip's
`C_TCFIN` and by this script, so there are exactly three marker states:

| marker | `+0x0E` | `+0x0F` | before | after |
|---|---|---|---|---|
| vanilla ice (Freeze Water's water arm; also every marker in a pre-feature save, which reads 0/0) | 0 | 0 | `cmp`/`je` → replay → `jmp 0x55764BD6` | `je` → jmp to the **same** replay |
| Grip cooled land (Desert/Steppe/Grass) | 2/4/1 | 4/1/3 | `jne` → `ret 4` | `jne` → jmp to the **same** `ret 4` |
| raised earth (ours) | `0x0C` | 7 | `jne` → `ret 4` — **the bug** | shimmer — **the fix** |

Only our own state changes outcome. `C_SHOWGATE` clobbers no register (it reads two bytes off EAX
and sets flags), uses no stack, and the replay it jumps to does not read flags.

⚠ **`+0x0F == 7` is a safe discriminator only while Earth stays off Grip's ladder.** That ladder is
Desert→Steppe, Steppe→Grass, Grass→Snow, so the terrains it can record in `+0x0F` are `{1,3,4}`;
its ice arm writes `{0}`. **If Earth is ever added to that ladder, cooled land starts to shimmer** —
change the discriminator to test `+0x0E == Dirt` as well.

**Tint:** the shimmer is drawn from a fixed sequence index (`edx = 0x46`), so raised earth shimmers
*identically* to Freeze Water ice. There is no tint parameter on that call.

---

## 6. ⚠⚠ Cross-feature couplings — the expensive part

This feature rewrites bytes inside **two other features' live caves**. Both of those scripts detect
it and **abort before writing** — nothing is corrupted — but neither can run while this is
installed.

| Script | State while this is installed | Verified 2026-09-03 |
|---|---|---|
| `build_raiseterrain_lavadirt.py` | **cannot re-apply.** Its `cave_priors` check covers `0x5580DB60..0x5580DB93` and the `jne` byte is inside it | dry run prints `[!] 5580DB60 ... [x] AoWEPACK.dpl: originals mismatch -- not written` |
| `build_gripofwinter.py` | **can neither `--apply` NOR `--undo`.** It byte-compares the whole 20-byte `C_SHOW` blob | dry run prints `cave 0x5582A4E0 20 bytes *** FOREIGN ***`, `state: MIXED`. `do_apply` exits `ABORT: partially applied / foreign bytes present. Run --undo first.`; `do_undo` exits `ABORT: <run> is foreign (...)` — **both before `kill_game()` and before any write** |

```
*** UNDO build_raiseterrain_ug_earth.py BEFORE build_gripofwinter.py ***
```

Our `--undo` restores `C_SHOW` to its exact gripofwinter-only contents, which hands that script its
undo back. There is no way to avoid the coupling short of editing `build_gripofwinter.py` itself:
every insertion point — its `C_SHOW` cave, or the `E9` at its `Show` hook `0x55764BD0` — is a run it
byte-compares. **Owning the change here rather than there was the deliberate choice; this ordering
rule is the cost.**

### Why another feature's cave had to be rewritten at all

`build_raiseterrain_lavadirt.py` is applied and owns the only usable injection point: the per-hex
site `0x557A333E`, right after the hex passes Raise Terrain's own validity test. There is no second
post-validity 5-byte window in the loop — the instruction before it
(`mov eax,[0x558E92E8]` @`0x557A3313`) **carries a `.reloc` entry** and must not be displaced, and
everything earlier runs before validity is known. That script has no `--undo` and no trustworthy
backup, so it cannot be reverted first. The project's answer to exactly this situation is the
in-place cave rewrite (`build_invis_penalty.py` over `build_trueseeing.py`'s caves); this is that.

The rewrite is as small as it can be, and the script builds its new image by **copying the installed
51-byte image and writing into the copy** — the lava path is never regenerated, so it cannot drift.
Everything else in that cave is byte-identical afterwards, including `call 0x55827000` at
`0x5580DB72`, the synced-RNG stub, whose VA is a literal in `build_rng_lockstep.py`'s `SITES` table.
`C_LAVAGATE` restores `EAX = 2` and re-enters the lava arm at `0x5580DB72`, so a **surface** lava
hex executes exactly the instruction stream it did before.

```
C_LAVAGATE @0x5583E180   (29 bytes, only present when LAVA_SURFACE_ONLY)
  5583E180  8b 14 24        mov edx,[esp]
  5583E183  80 7a 22 00     cmp byte [edx+0x22], 0
  5583E187  75 0a           jne 0x5583E193
  5583E189  b8 02 00 00 00  mov eax, 2
  5583E18E  e9 df f9 fc ff  jmp 0x5580DB72        ; surface: back into the lava arm
  5583E193  31 c0           xor eax, eax
  5583E195  8b 75 08        mov esi,[ebp+8]
  5583E198  e9 a6 51 f6 ff  jmp 0x557A3343        ; underground: vanilla mountain path
```

`cave_dirtdelay @0x5580DC20` and the second lavadirt hook `0x557A31E9` are **byte-identical** and
untouched. That cave gates on `[field+0x14] == 9`; an Earth hex never matches, so it no-ops for us
with no change at all.

---

## 7. Knobs — both shipped ON

| knob | shipped | effect |
|---|---|---|
| `EXCLUDE_ROAD_OVERLAY` | `True` | Hexes whose `[field+0x15]` overlay is 4 (road) or 5 (bridge) are skipped. ⚠ **Data loss, not a design choice — do not turn this off.** Inioch hit the real bug with this same machinery: converting the terrain under a road/bridge **deletes it permanently**, because the restore puts the terrain back but not the overlay. This is an *exclusion*, not a repair; anything else that changes terrain under a road still destroys it. |
| `LAVA_SURFACE_ONLY` | `True` | The lava → 50 % dirt arm stays surface-only. Underground lava was unreachable before this feature (the spell was surface-only), so "underground terrains other than Dirt must behave exactly as today" had no defined answer for it; ruled 2026-09-02 that unlocking underground casting must not silently give lava a new behaviour. Set `False` and underground lava also rolls 50 % dirt. |

With both ON the shared `cave_lavadirt` loses **five** bytes (`0x5580DB6C..0x5580DB70`,
`1c b8 02 00 00` → `26 e9 0e 06 03`), not one. With both OFF the diff is the single `jne`
displacement byte.

---

## 8. Design decision — up-front flip, NOT the frame-9 flip

The lava arm converts at glow frame 9, from inside `NewFrameRaiseTerrainAnimation`. This feature
converts **up front**, in the synchronised TE, and lets the glow be purely cosmetic.

1. **It touches nothing at the second shared hook.** `cave_dirtdelay @0x5580DC20` and the hook
   `0x557A31E9` stay byte-identical, so the blast radius over `build_raiseterrain_lavadirt.py` is
   one jump displacement instead of two caves.
2. **Multiplayer.** Marker spawn, duration roll, owner and terrain change all happen in one
   synchronised context in a fixed order, so peers cannot diverge. The frame-9 route is anim-timed
   and Inioch flags it as an MP residual in his own notes; we already carry that residual once for
   lava and there is no reason to buy a second one.
3. **No RNG-guard hack.** The frame-9 route has to set bit 3 of `[*0x558FA040+0x3C]` to stop
   `ChangeTerrain`'s variant roll tripping the "Invalid AoWHSMap.Random use" assert from the render
   context. Up front, in the TE, the variant roll draws SYNCED like everything else and no flag is
   touched. `CLAUDE.md` is explicit that the bit-3 flag is not a fix.
4. **Robustness.** If the glow is culled or never ticks, an up-front flip has already happened; a
   frame-9 flip would leave a marker promising to restore a terrain that was never set, which then
   silently self-destructs on melt.

**Cost, stated plainly:** the earth appears the instant the spell resolves and the glow plays over
it, instead of appearing at the moment the glow peaks. The glow is present either way, but the
timing is **not** identical to the lava arm. There is deliberately **no knob** for the other
behaviour — building it would mean rewriting `cave_dirtdelay` as well, which is the whole thing this
choice avoids. If the timing turns out to matter more than items 1-4, that is a rewrite, not a flag.

---

## 9. Failed approaches, declined fixes, and open questions

### ⚠ QA finding (c) — countdown underflow: **declined, with a measurement**

`TFrozenWaterHS.NewTurn @0x55764B98` decrements **first** and has no `<= 0` pre-guard, unlike
`TRaisedMountain.NewTurn @0x557A3064` which tests before decrementing:

```
HS   dec byte [eax+0x0C] ; cmp byte [eax+0x0C],0 ; jg ret ; call MeltIce
MNT  cmp byte [eax+0x1E],0 ; jle ret ; dec ; cmp ; jne ret ; call Expire
```

So if something on the hex vetoes the terrain change (`TStructure` / `TArmyHS.CanChangeTerrain`),
`TerrainChanged` never fires, the marker is never destroyed, and the counter runs past zero.

**Measured, not assumed:** `jg` is **signed**, so `0 → 0xFF` is −1, which is not > 0 and therefore
**still calls `MeltIce`**. The marker **retries every turn for 129 turns** (0 down through −128).
Only the 130th decrement, `0x80 → 0x7F`, produces +127 and starts a 127-turn dormancy — after which
it resumes retrying. **It is never permanently stuck**, and for the first 129 turns the behaviour is
exactly what you would want: keep trying until the veto lifts.

**Decision: no guard.** Adding one means editing vanilla `NewTurn`, which is shared with Freeze
Water ice and with Grip of Winter's cooled land, so it would silently change two other features to
fix a case that needs 129 consecutive vetoed owner-turns first. The exposure is also smaller than it
looks: `ValidTargetMapF` already rejects any hex carrying a `TStructure` (`[0x55713BD8]`, verified),
so our markers can never be created under a structure in the first place. If it is ever wanted, the
one-instruction fix is to make the counter **saturate** instead of wrap, and it belongs in
`build_gripofwinter.py`, which owns that class.

### Two things this script cannot settle without the game

* `TRaiseTerrain.ValidTargetMapF @0x557A35B8` requires the hex **overlay** to be **non-zero**
  (`mov al,[ebx+0x15]; test al,al; je FAIL`) as well as rejecting terrain 0/6/0xA/0xD (and, via
  `build_chasm_sky_spellguard.py`, 0xB/0xE). **If underground Dirt floor hexes carry overlay 0 they
  will still refuse to be targeted**, and the fix would be a separate edit there. Inioch's in-game
  test of the same unpatched gate says underground hexes do pass, but that is his install, not a
  byte fact about ours. **First thing to check in game.**
* `ValidTargetSelectionMapF @0x557A3610` (the cursor highlight) has the identical conditions and,
  like `ValidTargetMapF`, no level gate. Its extra guard `[0x55713BD8]` is `TStructure`, not
  `TFrozenWaterHS`, so our marker never blocks a re-cast.

### Re-tune, and why there is no "revert first"

The reservation is treated as **one owned run**, and every foreign run carries the enumerated set of
images this script could previously have written (all knob combinations). A second `--apply` with
different constants is recognised as a re-tune: the runs are overwritten in place, the whole
reservation is rewritten in one go so a shorter cave cannot leave a stale tail, and **no backup is
taken** — the file on disk is this script's own earlier output. Bytes matching none of those images
are FOREIGN and the script writes nothing at all. (This is how the P6 sparkle fix landed on
2026-09-03 without reverting anything.)

The only run whose content is accepted unconditionally is our own exclusive reservation: it was
verified all-zero before the first apply, no other build script references any VA inside it, and
nothing branches into it, so any non-zero byte there is by definition our own earlier output. Every
run that lives inside **someone else's** code — the flag byte, `cave_lavadirt`, the dead tail,
`C_SHOW` — is still enumerated and still rejects foreign bytes.

---

## 10. What still needs the user's in-game test

1. **Cast Raise Terrain underground at all** — the cursor must highlight underground hexes and the
   cast must go through, with no "must be cast on the surface" message. If it refuses, check the
   overlay-non-zero condition in §9 first.
2. **Underground Dirt → Earth**, with the green raise glow, and **no mountain placed**.
3. **The Freeze Water shimmer plays on the raised earth** (P6, the whole point of the re-tune).
4. **It reverts to Dirt after 2-4 of the caster's turns.**
5. **Roads and bridges are skipped** — cast over a road hex underground and the road survives; the
   hex is simply not converted.
6. **Underground lava is unaffected** — it takes the vanilla mountain path, no 50 % dirt roll.
7. **Surface behaviour is completely unchanged**: surface lava still rolls 50 % dirt at glow frame
   9, surface Raise Terrain still raises mountains.
8. **Grip of Winter still looks right** — a Freeze Water ice hex still shimmers, and cooled
   Desert/Steppe/Grass land still does **not** (the §5 table).
9. **Save / load with a raised-earth hex standing.** It must reload and still revert on schedule
   (property ids `0x20`/`0x21`), and a pre-feature save must still load with its ice markers melting
   normally.
10. **Re-cast on an already-raised hex** — the marker keeps its original `+0x0E`, so it must still
    revert to Dirt.
11. No "Invalid AoWHSMap.Random use" popup at any point.
