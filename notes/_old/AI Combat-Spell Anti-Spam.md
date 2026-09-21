# AI Combat-Spell Anti-Spam (once-per-combat)

**One-line:** Stop the AI wasting tactical-combat turns re-casting the same combat spell.

- **Turn Undead** — always scores extremely low (tactical value ÷ 64, floor 1). AI only casts it when it's the *only* combat spell it has, instead of throwing it at non-undead.
- **Terror** — one cast per combat.
- **Slow / Hunter's Mark** — first-cast priority **boosted** (the AI would otherwise never pick it), then one cast per combat.
- **Ooze** — one cast per combat.

The three "once per combat" spells reset at the start of each battle and stay eligible (value floored at 1) if a spell is the AI's only option.

**⚠ THIS RECORDS A THIRD-PARTY BUILD, NOT A ZIGGURAT FEATURE.** Confirmed working in *his* binary; there is no build script for it in `build_scripts/` and none of it is applied here. Read it as an exact-byte RE reference. **Terror alone has since been implemented natively — see `Terror_OncePerCombat.md` (`build_terror_oncepercombat.py`), which reuses none of the addresses below.**

**⚠⚠ EVERY ADDRESS BELOW COLLIDES WITH A LIVE ZIGGURAT FEATURE.** The flag bytes `0x558FAF20/21/22` are owned by `build_shipyard_income.py`; the caves `0x5580DCE8` / `0x5580DD14` / `0x5580DD34` sit in a block where `0x5580DD0E`, `0x5580DD20` and `0x5580DD30` are already ours. Re-pick before reusing anything here.

**Status (his build):** CONFIRMED WORKING in-game. Target: `AoWEPACK.dll` (ImageBase `0x55700000`, VA = file_off + `0x55700C00`). All caves PIC-safe (delta-trick). Apply script: `ai_combat_spell_antispam_patch.py` (exact byte-diff of our pre-feature backup vs the confirmed build; self-verifies every original byte). **Cave VAs are our free-space picks and overlap BXL's — read as an exact-byte RE reference.**

---

## The AI combat-spell architecture (the reusable part)

Two **distinct** combat contexts, with **different value and cast paths**. This split was the entire difficulty — a hook that works in one doesn't fire in the other.

### Value (how the AI scores a candidate cast)
- **Fast / auto-resolve combat:** `fcPrefetchCombatCommands` (spell VMT **+0x90**) scores each target via `fcGetDamageValueEx` (**+0x98**), then **`cmp [output],0; je skip`** — a command with value **0 is dropped**; otherwise it's queued with priority `DVtoDEV(value)`.
- **Tactical combat** (what the player watches): the AI uses the **`tc` value** — `tcGetDamageValueEx` (**+0x88**, base `0x5577969C`) which calls **`GetCombatDamageValueEx` +0x84** (the real per-target scorer). `+0x88`'s "Ex" fills an output struct via `+0x84`.
  ⚠ **Derive a VMT base from the export table, never by subtracting an assumed slot offset.** The `..Class` symbol *is* the base — `CombatSpells..TTerror` = `0x557F61D4`, so `0x557F625C` in the table below is **+0x88** (`TTerror.tcGetDamageValueEx`), not +0x84. A base off by 4 renames every slot by one.

So: to control a spell in **both** contexts, gate **both** `+0x84` and `+0x98`.

### Cast execution (where the effect actually applies)
- **Fast combat:** `fcExecuteCombatCommand` (**+0x94**) → `CreateCA` (**+0x78**, shared base `0x557F72C0`, present in 21 combat-spell VMTs) → `TCombat.ExecuteCombatAction` `0x55727224`.
- **Tactical combat:** the cast runs as a **combat action (CA)**. Some spells have a dedicated tactical CA (`TTacticalCombatTerrorCA.Execute` `0x557F990C`); spells without one use a **generic** CA (`TCombatSpellCA` / `TExclusiveCombatSpellCA` / `TMultiTargetCombatSpellCA`). **Ooze uses a generic CA — it has no Ooze-specific tactical method to hook.**

### ⭐ The universal tactical cast-completion: `TSpell.CombatCastingDone` @`0x557794E8`
Every generic combat-spell CA `.Execute` calls it (also `TSpell.CombatSpellCast`, `TUnitSpell.ExecuteCA`), **always with `eax` = the spell object**. This is *the* reliable, spell-carrying, cast-only hook for tactical combat. Identify a specific spell by comparing `[eax]` (its VMT pointer) to that spell's runtime VMT — delta-trick `lea reg,[delta + preferredVMT]` (Ooze VMT base = `0x557F5DD4`, found by searching the image for a known Ooze method pointer and subtracting the slot offset).

> Note: the AI spell-list driver keys off VMT **+0x5c** `AIPrefetchCastSpellActions`, but **nothing calls `[reg+0x5c]`** (0 sites) and Ooze's `+0x5c` is the empty base anyway — don't rely on it.

---

## Mechanism (per-combat flags)

Writable-BSS flag bytes (PIC delta-addressed; **not** valid at flat file offset — BSS rawsize 0):
`F_OOZE = 0x558FAF20`, `F_TERROR = 0x558FAF21`, `F_SLOW = 0x558FAF22`.

- **Reset:** hook `TCombat.Create` @`0x5572708C` → cave zeros all three at the start of each battle. (Verified once-per-combat, not per-turn.)
- **Set:** a cast-time hook flips the spell's flag.
- **Gate:** a wrapper on the spell's AI value method shrinks/zeros the score when the flag is set.

### Per-spell hooks/caves

| Spell | Set (flag ← 1) | Value wrapper | Behavior |
|---|---|---|---|
| **Turn Undead** | — (unconditional) | tc-slot `0x557F4350` → cave `0x5580FA49` | `value = max(1, value>>6)` always |
| **Terror** | `TTacticalCombatTerrorCA.Execute` `0x557F990C` → set F_TERROR (cave in `0x5580DCE8` block) | tc-slot `0x557F625C` (**VMT +0x88**) → wrapper `0x5580DD34` | if F_TERROR: `value = max(1, value>>6)` |

⚠ **Terror's fast-combat arm is missing from this table, and the obvious slot is a trap.** Terror *does* override VMT **+0x98** (`TTerror.fcGetDamageValueEx` `0x557F9C2C`, slot `0x557F626C`) — but that method is **never called**: `TTerror.fcPrefetchCombatCommands` `0x557F9B20` accumulates the value inline into EBP and tests it itself. Module-wide it has 0 direct rel32 refs and exactly 1 absolute dword ref (its own slot). A wrapper there assembles, verifies, disassembles correctly and does nothing. The working fast-combat pair is gate `fcPrefetchCombatCommands` `0x557F9B20` + set `TTerror.fcExecuteCombatCommand` `0x557F9BE8` — see `Terror_OncePerCombat.md`. **An override is not evidence that the method is on the path.**
| **Slow / Hunter's Mark** | `TSlowCA.Execute` `0x557F8818` → set F_SLOW | tc-slot `0x557F4E88` → wrapper `0x5580D2AA` | **unflagged: `value = value*8 + 100`**; flagged: `value>>6` |
| **Ooze** | `TSpell.CombatCastingDone` `0x557794E8` → VMT-identity vs TOoze → set F_OOZE (cave `0x5580D792`); **plus** fast-combat set-thunks on VMT `+0x74`/`+0x78`/`+0x94` | `+0x84` slot `0x557F5E58` → `0x5580D6D4` **and** `+0x98` slot `0x557F5E6C` → `0x5580D704` | if F_OOZE: **force value 0** (drops the command) |

Shared reset cave lives in the `0x5580DCE8` block.

---

## Why Ooze took ~10 iterations (landmines)

1. **÷64-floor-1 is not enough for a fc/tc-command spell.** The command driver drops a candidate only when its value is **exactly 0**; any value ≥ 1 keeps it queued (just lower priority) and it still wins when the AI has nothing better. **Force 0** to actually drop it. (Terror worked with ÷64 because its driver picks the single highest-priority action, so ÷64 makes it lose — different driver semantics.)
2. **Tactical ≠ fast combat.** Ooze's tactical cast never touched `ActivateCombat` (+0x74), `CreateCA` (+0x78), or `fcExecuteCombatCommand` (+0x94) — all fast-combat-only. Hooking the spell's own cast VMT methods failed silently; only `CombatCastingDone` (downstream of the generic-CA path) fires in tactical.
3. **Terror / Turn Undead were easy** because they have their own `tc`-value overrides / a dedicated tactical CA, so hooking the tc-slot + tactical CA Execute worked directly. Ooze / Slow **inherit the base**, forcing the generic-path solution.
4. **Diagnostic that cracked it:** repoint a candidate value method to return **unconditional 0**. If the spell stops casting entirely, that method *is* the control point — proving the value path before hunting the (harder) cast point. Also: BSS flag bytes are runtime-only; assert on file bytes there and you'll chase a phantom.

---

## Tuning
- Deprioritize strength: the `shr eax,6` (÷64) in each wrapper.
- Slow first-cast boost: `shl eax,3` (×8) + `add eax,100` in `0x5580D2AA`.
- Ooze hard-drop: the `mov dword [output],0` in the `+0x84`/`+0x98` wrappers (change to a shift to soften).
- To add another spell: reset its flag in the `0x5580DCE8` cave, set it at that spell's cast point (its tactical CA Execute, or `CombatCastingDone` with a VMT check if it uses a generic CA), and wrap its `+0x84` (and `+0x98` for fast combat) value slot.
