# HOWTO — Per-hex ring detection in AoW1 area effects

**Status: technique CONFIRMED WORKING in-game (2026-07-08)** via the Path radius+1 / 25%-outer-ring mod
(`build_scripts/build_path_outerring.py`, backup `.pre-pathring`). This doc generalises that so any future
mechanic can tell, per affected hex, *which ring* it sits on relative to the effect's centre — and then
scale, gate, or randomise behaviour by ring.

Use it for: fading edges (outer ring converts less often), ring-only effects (only the rim burns),
distance-scaled damage/healing, "hollow" auras, or any radius-graded area spell/ability.

---

## 1. The primitive: hex-number (HN) as a distance index

AoW hexes around a centre are numbered in an outward spiral. `HN` (the game's "hex number") *is* the
distance-ordered index, so a single call converts two hex coords into "how far apart, as a ring".

```
dHXtoHN   @0x557026A4   EAX=x1, EDX=y1, ECX=x2, [esp+4]=y2  ->  EAX = HN         (RET 4 / stdcall, 1 stack arg)
HNtoRad   @0x5570267C   EAX=HN  -> EAX = ring radius r
RadToHN   @0x55702684   EAX=r   -> EAX = first HN of ring r
```

The spiral (standard hex geometry — ring `r` has `6r` hexes; cumulative through ring `r` is `1+3r(r+1)`):

| ring r | hexes on it | HN range        | first HN = RadToHN(r) |
|-------:|------------:|-----------------|----------------------:|
| 0      | 1 (centre)  | 0               | 0                     |
| 1      | 6           | 1 .. 6          | 1                     |
| 2      | 12          | 7 .. 18         | 7                     |
| 3      | 18          | 19 .. 36        | 19                    |
| 4      | 24          | 37 .. 60        | 37                    |

So **"which ring is this hex on?"** = `HNtoRad(dHXtoHN(cx,cy, hx,hy))`, or — cheaper — just compare the
raw HN against a threshold. For "is it strictly outside radius R?", the threshold is `RadToHN(R+1)`:

- radius-1 disk vs its ring-2 rim: threshold **7** (`HN < 7` = inner disk, `HN >= 7` = outer ring).
- radius-2 disk vs its ring-3 rim: threshold **19**. Etc. (`RadToHN(R+1)` from the table above.)

`dHXtoHN` is order-independent for distance (it's symmetric in the two points), and it's already used by
the storm/area code, so it's the canonical, MP-safe way to measure hex distance. Don't hand-roll cube
coordinates.

---

## 2. The pattern (three steps)

An area effect that walks a disk of hexes and fires a per-hex callback has no idea where the *centre* is
by the time the callback runs — it only gets the current hex. So:

**Step A — widen the radius.** The radius is usually a `push imm8` right before the area call. Bump the
immediate (`6A 01` → `6A 02` = `push 1` → `push 2`). One byte per call site.

**Step B — stash the centre.** Hook a point where the centre hex is in hand (for Path it's `[EBP-4]`,
the departed field) and copy its `x,y` (field `+0x10`, `+0x11`) into a **2-byte scratch global**. Area
walks are single-threaded, so one shared scratch is fine. *The scratch MUST be in a writable section —
see Gotcha 1.*

**Step C — gate the per-hex callback.** Re-point the callback pointer to a small cave that:
1. reads the current hex's `x,y` (`+0x10/+0x11`),
2. `HN = dHXtoHN(cx,cy, hx,hy)`,
3. `cmp HN, <threshold>` → below ⇒ inner ⇒ run the real callback unconditionally;
   at/above ⇒ outer rim ⇒ roll the RNG and run it only on a hit, else `ret` (leave the hex untouched).

Re-pointing works only if the callback pointer has a `.reloc` entry (so writing the cave's *preferred* VA
gets rebased at load). Verify with the reloc parser before trusting it; the three Path callback push-sites
all had one.

---

## 3. Gotcha 1 — scratch must live in a WRITABLE section (this cost a crash)

AoWEPACK's **CODE section is read-only at runtime** (section flags `0x60000020` — no WRITE bit). The cave
region we assemble into (`0x5580xxxx`) is *in that code section*: fine to **execute**, faults if you
**write**. Putting the centre-scratch at `0x5580DD20` produced *"Exception occurred during
TArmyDefaultMoveTE"* — the move ran but the terraform aborted the instant the stash tried to store.

**Rule: caves may execute from CODE but must never write to it. Put mutable scratch in a writable section:**

| section | VA         | flags        | note                                                            |
|---------|------------|--------------|-----------------------------------------------------------------|
| DATA    | 0x558E8000 | 0xC0000040   | initialised data, writable                                      |
| **BSS** | 0x558EA000 | 0xC0000000   | zero-init, writable. vsize `0x10231` ends ~`0x558FA231`; the page rounds up to `0x558FB000`, so **`0x558FA800` is committed, zeroed, and past everything the game uses** = free scratch |

The Path mod uses `SCRATCH = 0x558FA800` (2 bytes). Because BSS and CODE share the *same* runtime rebase
delta, a code cave reaches BSS with the usual **call/pop-delta** trick and a constant offset — here the
anchor `0x5580DD40` plus `0xECAC0` lands exactly on `0x558FA800`. Position-independent, verified at the
byte level after apply.

## 4. Gotcha 2 — use the MP-safe RNG in synchronised contexts

The proc roll uses the DLL's synchronised RNG:

```
AoWHSMap.Random  @0x5577827C   EAX=map, EDX=N  ->  EAX in 0..N-1     (map = *(0x558FA040))
```

25% = `Random(map,4); test eax,eax; jnz skip` (proc only on `0`). This RNG is deterministic across
multiplayer peers **but asserts** ("Invalid AoWHSMap.Random use") if called outside a synchronised game
context — it checks `(*0x558FA040)+0x3c & 8`. Move execution *is* synchronised, so it passes here. If you
ever reuse this from an unsynced context (render/anim/AI), either use the exe's `System.RandInt`
@0x401030, or briefly set the guard flag `(*0x558FA040)+0x3c |= 8` and restore it (the "flag-suppress"
trick — see the Raise-Terrain lava→dirt fix in `aow1-terrain-changing-spells`).

---

## 5. Worked example — Path radius +1, 25% on the outer ring

`Path of Life(0x45)/Decay(0x44)/Frost(0x6d)` terraform a radius-1 disk behind a moving unit
(`TAbstractUnit.MovedTo @0x55780328` → per-hex terrain callbacks). Goal: radius 2, but the *new* rim
(ring 2) converts only 25% of the time, so the trail frays at its edge instead of a hard circle.

- **Radius:** `6A 01`→`6A 02` at `0x5578044E` (Life), `0x55780495` (Decay), `0x557804DA` (Frost).
- **Centre stash:** hook `0x5578041E` → `cave_stash @0x5580DD30`: reads `[EBP-4]`, writes `cx,cy` to
  `SCRATCH=0x558FA800`, replays the displaced `mov eax,[ebp-4]; cmp byte[eax+0x12],0`, jumps back to
  `0x55780425`.
- **Proc-gates:** the three callback pushes at `0x55780452 / 0x55780499 / 0x557804DE` (targets
  `0x557801A4 / C4 / E4`, each `.reloc`-backed) are re-pointed to `proc_life/decay/frost` @
  `0x5580DD60 / DDC0 / DE20`. Each: `HN=dHXtoHN(cx,cy,hx,hy)`; `cmp eax,7; jl _proc` (inner disk, 100%);
  else `Random(map,4); test eax,eax; jnz _skip` (outer ring, 25%); `_proc:` jmp real callback; `_skip:`
  ret. Registers saved/restored so the area loop's EBX/ESI/EDI/EBP survive.
- Frost's separate FrozenWater spawn-notify (`PathOfFrostTerrainChanged @0x5578024C`) self-gates (only
  fires where a hex actually became ice), so it needs no ring gate.

Caves at `0x5580DD30+`; backup `AoWEPACK.dpl.pre-pathring` — ⚠ **moved** to `Modding Resources/backups/`
on 2026-07-29/30 and now layer **8 of 47**, so "copy the backup back" would destroy 38 later features.
Undo surgically instead (restore the gated callbacks' original bytes, zero the caves at `0x5580DD30+`).

---

## 6. Adapting it — quick recipes

- **Different outer radius:** bump the `push` immediate to R, set the cave threshold to `RadToHN(R+1)`
  from the table (radius 2→ threshold 19, radius 3→ 37, …).
- **Different proc rate on the rim:** change `Random`'s `EDX` (the denominator) — `3`≈33%, `4`=25%,
  `5`=20%, `10`=10% (proc on result `0`). For 75%, proc on `!= 0` instead (`jz _skip`).
- **Graded by ring (not just in/out):** call `HNtoRad` (or compare against several `RadToHN` thresholds)
  and pick a per-ring denominator — e.g. ring1 100%, ring2 50%, ring3 25% for a smooth falloff.
- **Ring-only / hollow effect:** invert the inner test — `jl _skip` instead of `jl _proc`, so the centre
  disk is spared and only the rim fires.
- **Any centre-relative area:** the same stash-centre → `dHXtoHN` per hex works for *any* effect that
  exposes a per-hex hook and a reachable centre; it isn't Path-specific.
