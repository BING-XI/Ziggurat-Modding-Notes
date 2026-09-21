# v4 Leak: why the AI STILL sometimes razes non-cities — full analysis for review

**Status: diagnosis 2026-07-12. Self-contained for a reviewer with NO Ghidra access — every
address, decompile, and cave listing needed is inlined here.** Companion to
`AI_Raze_Decision_CodeMap.md` (the vanilla pipeline) and `Unit_Spellcasting_INDEX.md`.

Module: `AoWEPACK.dpl`, Ghidra image base `0x55700000`. CODE file offset = VA − 0x55700C00.
Delphi 3 register convention (EAX,EDX,ECX; stack right-to-left; callee-cleans `ret N`).
Virtual call = `mov eax,self; mov ecx,[eax]; call [ecx+slot]`.

---

## 0. The observation (ground truth from in-game, v4 live)

Given the AI **extremely powerful units**, in one turn it: **razed 1 mine**, captured 5 mines
uneventfully, **failed a raze on 1 node** (attacked its raze-defenders and lost), captured 4 nodes.
So the AI reached the *raze path* for exactly **2** non-city structures and was blocked/kept for
the other 9. v4 was supposed to make AI non-city razes **impossible**. It is leaking.

"Sporadic (2 of ~11)" is the critical clue: a *systematically* broken gate would raze 0 or all;
2-of-11 is a **flag leaking** into specific invocations.

---

## 1. What v4 is and why it should block this

`cave_forcefail` (v4) is hooked into `TStructure.CanRaze` @0x5575FB80 at the veto-decode point
`0x5575FC90` (6 bytes `8b 45 f0 8a 40 14` = `mov eax,[ebp-0x10]; mov al,[eax+0x14]` replaced with
`E9 rel32` → cave). Live disassembly of the cave (`0x5580D150`, verified on disk):

```
5580D150 call  0x5580d155          ; PIC load-delta
5580D155 pop   ecx
5580D156 sub   ecx, 0x5580d155     ; ecx = runtime−linktime delta
5580D15C cmp   byte [ecx+0x558FA801], 0   ; FLAG_RAZEOK
5580D163 jne   Lcount(0x5580D185)  ; *** razeok set -> BYPASS straight to the forces check ***
5580D165 mov   eax,[ecx+0x558E9494]; map global
5580D16B mov   eax,[eax]
5580D16D mov   eax,[eax+0x140]     ; player list
5580D173 movsx edx, byte [ebp-5]   ; razing player index (CanRaze local param_2)
5580D177 call  0x557544D0          ; TPlayerList.GetPlayers -> eax = TPlayer
5580D17C cmp   byte [eax+0xA7], 0   ; 0 = human, !=0 = AI  (SAME test vanilla Raze uses, see §3)
5580D183 jne   Lai(0x5580D1A0)     ; AI -> city-only gate
Lcount(5580D185):
5580D185 mov   eax,[ebp-0x10]      ; predictor
5580D188 mov   eax,[eax+0x10]      ; predictor+0x10 = side-1 list (razer/AddOpponent)
5580D18B mov   eax,[eax+8]         ; TList.Count
5580D18E test  eax,eax
5580D190 je    Lnoforce(0x5580D199)
5580D192 mov   bl,1                ; forces present -> CAN RAZE
5580D194 jmp   0x5575FCB3          ; (test bl,bl -> nonzero -> cleanup -> return true)
Lnoforce(5580D199):
5580D199 xor   ebx,ebx             ; refuse
5580D19B jmp   0x5575FCB7          ; CanRaze "not enough forces" message block
Lai(5580D1A0):
5580D1A0 call  0x5580d1a5          ; PIC delta again
5580D1A5 pop   ecx
5580D1A6 sub   ecx, 0x5580d1a5
5580D1AC lea   edx,[ecx+0x557A73F0]; TCity VMT base
5580D1B2 mov   eax,[ebp-4]         ; CanRaze self = the structure
5580D1B5 call  0x557010C0          ; System._IsClass(structure, TCity)
5580D1BA test  al,al
5580D1BC je    Lnoforce(0x5580D199); NON-CITY AI raze -> REFUSE  <-- the v4 block
5580D1BE mov   eax,[ebp-0x10]
5580D1C1 mov   al,[eax+0x14]       ; predictor result
5580D1C4 jmp   0x5575FC96          ; CITY -> fall into the ORIGINAL vanilla veto
```

For an **AI mine/node** (razeok clear, `[+0xA7]!=0`, not TCity) the path is
`jne Lai → IsClass false → je Lnoforce → refuse`. `CanRaze` returns **false**. And `Raze` (§3)
only proceeds if `CanRaze` returns true. So with `razeok` clear, v4 is correct and the mine is
kept. **The only way an AI non-city reaches a raze is `razeok` being set at `5580D15C`.**

---

## 2. The AI raze call chain (all in AoWEPACK; NOT cross-module — aowInt.dpl/AoW.exe have no AI raze code)

```
TAIGroupRazeControl.Process        @0x557D74E4   (post-capture: group stands on the taken structure)
  -> FindNoneTransparentHS(field, TStructure @0x55713bd8)     ; ANY razeable structure
  -> if GetRazeable (slot 0x154 = TStructure.GetRazeable @0x5575EDDC returns [template+0x58]) :
  -> SetupBattleFieldInfo @0x5575C098 / RetrieveBattleFieldInfo   ; masks DAT_5575C0D8=0x04 / DAT_5575C0DC=0x0A
  -> IsClass(TCity 0x557A73B0) ? ValidateRazeCity @0x557D7440 : ValidateRazeStructure @0x557D74B4
  -> if valid: TAIGroupRazeControl.ExecuteRaze @0x557D742C
TAIGroupRazeControl.ExecuteRaze    @0x557D742C   -> vcall slot 0x1E8  (= TStructure.Raze)
TStructure.Raze                    @0x557602F8   -> CanRaze (slot 0x1EC); if TRUE and player is AI -> RazeEx (slot 0x158)
TStructure.CanRaze                 @0x5575FB80   -> [cave_forcefail @0x5575FC90 -> 0x5580D150]  (the v4 gate)
RazeEx (slot 0x158)                -> ExecuteRaze (slot 0x1B0)
ExecuteRaze slot 0x1B0             = cave_towerraze @0x5580C910  (mod: TTower + Stage-8 TMine/TFarm/TPowerNode/
                                     TProductionPlace/TAltar/TTeleport; TCity keeps its OWN 0x557AB414)
```

`TAIGroupRazeControl.ExecuteRaze` decompiled (proves slot 0x1E8 = Raze, i.e. CanRaze IS in the path):
```c
void TAIGroupRazeControl_ExecuteRaze(int self, int *structure){
  int grp = *(int*)(*(int*)(self+0x1c)+0xc);
  (**(code**)(*structure + 0x1e8))(structure, (byte)*(char*)(grp+0x28)); // Raze(structure, groupPlayer)
}
```

`TStructure.Raze` decompiled (proves it ACTS on CanRaze's bool, and the AI branch = RazeEx slot 0x158):
```c
void TStructure_Raze(int *self, undefined4 player){
  ... SEH frame installed (push &LAB_55760434) ...          // <-- silently catches exceptions
  char ok = (**(code**)(*self+0x1ec))(self, player, &msg);  // CanRaze
  if (ok != 0){
    if (!GetPlayers(player).GetBusy()){
      if (GetPlayers(player)[+0xA7] == 0) { ...human confirm dialog... }   // human
      else (**(code**)(*self+0x158))(self, player);                        // AI -> RazeEx
    }
  }
  ...
}
```
Note: vanilla `Raze` itself uses `player[+0xA7]==0` to mean human — so the `forcefail` cave's identical
test is CORRECT; **[+0xA7] is not the bug.**

---

## 3. The `razeok` flag and the leak (the root cause)

`FLAG_RAZEOK = 0x558FA801` — a 1-byte flag in BSS page-slack (mapped RW, zero-init, no file bytes).
Purpose: `ExecuteRaze` (the vanilla raze @0x5575FFC8) **re-calls `CanRaze` at its top**; that
post-combat re-entry must NOT be re-vetoed, so the mod sets `razeok=1` around it → `cave_forcefail`
sees it and bypasses to the forces check (pass). Legitimate and necessary.

**Every setter is linear `set=1 → call EXECUTE_RAZE → set=0`, with NO try/finally.** From
`build_scripts/build_razebattle_tower.py`:

- `cave_towerraze` won-raze branch `Lraze` (lines 909-916):
  `mov [razeok],1 ; call EXECUTE_RAZE(0x5575FFC8) ; mov [razeok],0 ; jmp Lepi`
- Stage-1 fast lifecycle (lines 528-534): same shape.
- `cave_razedone` async/tactical (lines 1048-1056): same shape.
- Defensive **entry-heal** in `cave_towerraze` (lines 590-593): `xor eax,eax; mov [noflee],al;
  mov [survivors],eax; mov [razeok],al` — with the comment: *"heal ALL raze flags a prior THROWN
  raze could have left stuck: … razeok (would bypass the CanRaze AI veto …)."*

**THE LEAK.** `EXECUTE_RAZE` = `TStructure.ExecuteRaze @0x5575FFC8`, which does a great deal
(re-call CanRaze, destroy the structure, transfer income via the class SetPlayer override, generate
+ place raze-defenders, set up their AG, fire event-logs). If ANY of that raises a Delphi exception,
it unwinds to the SEH frame installed by `Raze` (§2) — **caught silently, no crash** — and the
`mov [razeok],0` immediately after the call is **never executed**. `razeok` stays **1**.

Now the flag is stuck across subsequent raze *decisions*:
1. Structure A's raze wins → `Lraze` → `razeok=1` → `EXECUTE_RAZE` **throws** → `razeok` stuck at 1.
2. Structure B (a mine/node) → `RazeControl.Process` → `Raze` → **`CanRaze#1`** → `cave_forcefail`
   sees `razeok=1` at `5580D15C` → **bypasses the city gate** → forces present → returns TRUE.
3. `Raze` proceeds (AI) → `RazeEx` → `cave_towerraze` → its **entry-heal clears `razeok`** — but
   that is at step 3, *after* step 2 already consulted the stale flag. Too late for the gate.
4. So B is razed (if its combat wins) or attempted-and-lost (result 4 → loss-garrison). Either way
   its `cave_towerraze` entry-heal cleared `razeok`, so structure C is protected again.

⇒ **Each stuck `razeok` leaks exactly ONE subsequent non-city raze past the v4 gate.** A short chain
of throwing razes yields precisely the observed "1 mine razed + 1 node attempted, rest kept." The
entry-heal *bounds* the damage to one structure per leak but **cannot prevent that one**, because it
sits downstream of the gate it is meant to protect.

Corollary: the flag also persists **across turns / the whole session** (BSS, never reset except by
the entry-heal), so the very first leaked raze in a session can be seeded by a throw from an earlier
turn — there need not be a prior raze in the *same* turn.

---

## 4. Why the other candidate causes are ruled out

- **Not `[+0xA7]` mis-ID:** vanilla `Raze` uses the identical `player[+0xA7]==0` test for human vs AI
  (§2). If it were unreliable the human/AI split would be wrong everywhere, not sporadically.
- **Not the `IsClass(TCity)` gate misfiring:** that would be systematic (all or nothing), not 2-of-11.
- **Not `simfly`:** `simfly` only makes the predictor *harsher* (adds retaliation) → fewer razes. It
  cannot create razes. (Its flag `0x558FA800` is a different byte and is set/cleared tightly around the
  three `Execute` call-sites by `cave_exec`.)
- **Not cross-module:** `aowInt.dpl` = UI/image package (`AOWInterfaceImgLib`, `TInterfaceIL`), zero
  raze/AI strings; `AoW.exe` has only the human `RazeBtn`/`RazeBtnClick`, no `CanRaze`/`TAIGroup`.
- **Confirmed the ONLY pass-path for an AI non-city in `cave_forcefail` is the `razeok` bypass** (§1):
  the human path needs `[+0xA7]==0`, the city path needs `IsClass(TCity)`; neither holds for an AI mine.

---

## 5a. FIX IMPLEMENTED — v5 — **CONFIRMED WORKING in-game (2026-07-12)**

User retest passed: AI captures mines/nodes with zero raze attempts; city/human razing unchanged.
The whole non-city raze rework is now confirmed; TCity remains future work.

Implemented as a rewrite of `cave_forcefail` only (same slot 0x5580D150, same FC90 hook, 138 B,
`build_razebattle_tower.py` src_forcefail; backup unchanged `.pre-razebattle`):

1. **Structural re-entry test** (replaces the leaky `razeok` read): bypass iff CanRaze's RETURN
   ADDRESS, delta-normalized (`[ebp+4] - loaddelta`), lies in **[ExecuteRaze 0x5575FFC8, Raze
   0x557602F8)**. Capstone-verified: the only CanRaze call sites in that range are ExecuteRaze's
   top-gate vcall @0x5575FFF3 and **RazeEx's re-check @0x5576025F** (RazeEx = slot 0x158 =
   0x5576023C — a second legit re-validation site discovered during verification). retaddr−delta ==
   link-time address, so the compare is rebase-proof. A stuck flag can no longer influence the gate.
2. **First-entry heal**: every non-re-entry CanRaze clears `razeok` before anything reads it —
   protects `cave_skipavenger`'s later read from a THROW-stuck flag. The gate itself no longer
   consults `razeok` at all; the flag remains set/cleared around `EXECUTE_RAZE` purely for the
   avenger skip.

This is options **(B)+(D)** below realized without any new hook (the heal rides the existing FC90
hook, which runs at every CanRaze#1). Option (C) was REJECTED — it would break `cave_skipavenger`,
which reads `razeok` after CanRaze#2 during `PlaceRazeDefenders`.

Expected retest result (same overwhelming-force scenario as the observation in §0): AI captures all
mines/nodes with ZERO raze attempts; AI hostile-city razing (Scorcher) unchanged; human razes
unchanged. Leaks are impossible even if `ExecuteRaze` throws — the stuck flag is healed at the next
CanRaze and never read by the gate.

## 5b. Design rationale — the option space behind v5

The defect is architectural: a persistent global flag whose "set" and "clear" straddle a throw-capable
call, guarded by a heal that runs *after* the reader. The four ways out, and what became of each:

- **(A) SEH-safe clear.** Wrap the `EXECUTE_RAZE` call so `razeok=0` runs on BOTH normal and exception
  exit (a finally/handler in each of the 3 setter sites). Robust and most faithful to intent.
  **Unused** — still available as defense-in-depth should v5 ever prove insufficient.
- **(B) Heal BEFORE the gate.** Clear `razeok` ahead of the reader. Safe because the legitimate
  re-entry (`CanRaze#2`) is reached via `ExecuteRaze` calling `CanRaze` **directly, not through
  `Raze`** — so an early clear never disturbs the re-entry's flag. **Adopted** (the first-entry heal).
- **(C) One-shot consume.** Have `cave_forcefail` clear `razeok` immediately after honoring it.
  **REJECTED — do not re-try:** it breaks `cave_skipavenger`, which reads `razeok` after CanRaze#2
  during `PlaceRazeDefenders`. It also only reduces a stuck flag to a single bypass rather than
  preventing it.
- **(D) Distinguish real re-entry structurally** (return-address range / depth counter) instead of a
  session-lifetime boolean. **Adopted** (the retaddr-delta test in 5a).

---

## 6. Appendix — vanilla `CanRaze` (May-2025 pristine backup) for reference

Vanilla veto (unmodded) at the tail of `CanRaze`, result byte from the predictor
`TCombatPredictor.FinishCombat @0x5572AF4C` (side0 = militia via AddUnit, side1 = razer via
AddOpponent): result **3** = razer wiped (militia wins), **4** = militia wiped (razer wins),
**2** = both survive, **8** = wall. `GetSuperiority @0x5572B798` = winner's margin.
```
5575FC90 mov eax,[ebp-0x10]      ; predictor          (THIS 6-byte pair is what cave_forcefail replaces)
5575FC93 mov al,[eax+0x14]       ; result
5575FC96 add al,0xFD             ; al -= 3
5575FC98 sub al,2                ; (result-3) < 2  -> result in {3,4}
5575FC9A jb  0x5575FCA0
5575FC9C sub al,1                ; result == 6 ?
5575FC9E jne 0x5575FCAD          ;  no, and not {3,4} -> CAN raze
5575FCA0 call GetSuperiority (0x5572B798)
5575FCA8 cmp eax,0x64            ; >= 100 ?
5575FCAB jge 0x5575FCB1          ;  yes -> CANNOT raze
5575FCAD mov bl,1                ; CAN raze
5575FCB1 xor ebx,ebx            ; CANNOT raze -> "not enough forces" msg
```
Net vanilla rule: **refuse iff the raze-militia would win the predicted fight** (result 3, whose
superiority is always ≥100). result 4 (razer wins) has superiority = razer loss% < 100 → allowed.
This is *permissive* (it is the "one Great Eagle razes a metropolis" over-permissiveness), which is
why the mod's `forcefail` replaced it — and why the AI's non-city block is entirely the mod's
`IsClass(TCity)` branch, now defeated by the `razeok` leak above.

## 7. Appendix — BSS flag map (all runtime-only, no file bytes; .idata wall at 0x558FB000)
```
0x558FA800  simfly        (predictor fast-combat economics; set/cleared by cave_exec around Execute)
0x558FA801  razeok        (CanRaze re-entry bypass — THE LEAKING FLAG)
0x558FA802  combathappened
0x558FA803  razeasync     (tactical path: cave_razedone owns the gate+raze)
0x558FA804  razeplayer    (razing player stashed for cave_razedone)
0x558FA805  razeguard     (Guard-AG + survivor-substitution window in cave_lossgarrison)
0x558FA806  razenoflee    (fcExecute suppresses side-0 flee)
0x558FA808  razesurvivors (DWORD: off-map survivor-army ptr from cave_rehome)
```
