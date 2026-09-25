# Inioch / AoWx — fellow-modder reference

Maps `Modding Resources/Inioch/` — reverse-engineering notes, patch scripts and tooling shared by
Inioch, a fellow AoW1 modder who maintains his own mod, **AoWx**. Covers who he is and how his module
names map to ours; what each drop in the archive actually contains and the order it really arrived
in; which of his findings we have adopted into our own build scripts; what he catalogued that we have
not built; the standing constraints his RE has placed on our own future work; a merged, de-duplicated
trap list; and the share4/share5 catalogue gap.

It does **not** re-derive his RE in full. The 21 files in `Inioch/share1/` (our own distillation of
his first two drops) and `Inioch_Share6_Catalogue.md` (our distillation of his sixth) remain the
detailed reference and are pointed at throughout rather than duplicated — §3 is a one-line-each map of
what each of the 21 holds. It does **not** catalogue `Inioch/share4/` or `Inioch/share5/` beyond what
is already known (§8): those two drops were reviewed and their catalogue deliberately retired, so
this file records what came out of them rather than re-deriving them.

## Status table

| feature | status | owning script | binary |
|---|---|---|---|
| AI paths to and searches exploration sites | 🔨 APPLIED, UNTESTED (2026-09-03) | `build_scripts/build_ai_sitesearch.py` | `AoWEPACK.dpl` |
| AI heroes pick up / equip / upgrade-swap items; items become group-aware AI targets | 🔨 APPLIED, UNTESTED (2026-09-03) | `build_scripts/build_ai_itemloot.py` | `AoWEPACK.dpl` |
| Crash capture via VEH injection (diagnostic tool, not a patch) | n/a — tool, not on the ladder | `re_tools/veh_capture.py` | n/a |
| Registry isolation — own settings tree (`…\Age of Wonders Z`) | 🔨 APPLIED, UNTESTED (2026-09-09) | `build_scripts/build_regiso.py` | `AoWEPACK.dpl`, `AoWSetup.exe` |
| AoWSetup install-check `'.'` fallback (his 2026-08-13 fix) | ✅ CONFIRMED WORKING (2026-09-09) | `build_scripts/build_aowsetup_installcheck.py` | `AoWSetup.exe` |

Everything else this file discusses is third-party reference material, an open cataloguing gap, or a
standing constraint on future work — not a patch of ours, so none of it carries a status-ladder tag.
Full addresses, cave layout and the in-game checklist for the two applied scripts live in
`10-ai-and-structures.md`; this file gives only what is specific to their Inioch provenance (§4).

## 1. Provenance and standing rules

**Who he is.** Inioch is a fellow AoW1 modder maintaining his own mod, **AoWx**, built on an **AoW+
base** — confirmed by byte-diff: his `GetDeveloper` @ file `0x3A44` is `33 C0 40 C3`, ours is vanilla
`33 C0 C3`. **We are not on an AoW+ base.** He shares reference material with us the way BXL's own
files were shared with this project; `share3/README.md` frames the exchange as reciprocal ("put
together to give back the same way BXL's reference files helped here").

**Module naming map** (his → ours):

| his | ours |
|---|---|
| `AoWEPACK.dll` | `AoWEPACK.dpl` |
| `AoWx.exe` | `AoWz.exe` (renamed from `AoW.exe` 2026-09-09; `<root>/AoW.exe` is now VANILLA) |
| `AoWDevX.exe` | `AoWDevEd.exe` (patch source) / `AoWzEd.exe` (live editor) |
| `VCL30.dpl` | **same filename** ⚠ |

Same VA formula for AoWEPACK (`VA = file_offset + 0x55700C00`, ImageBase `0x55700000`) and the same
file size (2,785,792 bytes), so his documented addresses transfer to ours as byte-verified reference.
Two verification passes confirm this at scale: ~30 anchors matched pristine byte-for-byte on
2026-07-29 (`share1/Inioch_INDEX.md` §0), and the entire mouse-wheel address stack across
`vcl30.dpl`, `aowInt.dpl` and `AoW.exe` matched again on 2026-09-02
(`share1/Inioch_MouseWheel_VCL30.md` §4).

**Standing rules:**

1. ⚠⚠ **Never run any of his scripts against our tree.** Every `*_patch.py` / `patch_*.py` /
   `build_*.py` in his shares is an exact-byte applier against **his** binary. His free-space cave
   picks sit in the same `0x5580xxxx` AoWEPACK pocket ours uses (his share6 zone alone is
   `0x55813200`–`0x55815500`), his BSS scratch collides with ours (`0x558FA800`, `0x558FA810`,
   `0x558FAF20`–`22`), and his aowInt layout (`CLR 0x59822800` / `SET 0x59822840` /
   `HELPER 0x59822880`) overlaps our own un-applied `build_glowboost.py` / `build_bltprobe.py` claims.
   Read every one of his scripts as an RE reference only, never an applier.
2. **His addresses are reliable; his allocations are not.** The byte-level anchors above are
   independently verified against our binaries. That does not extend to any address he picked for a
   *new* cave, a BSS global, or a thunk — those are his free-space choices on his binary, not evidence
   of free space on ours. Re-derive free space from our own binaries every time.
3. **Thunk and helper addresses do not port, even within "the same" module.** He carried an `LStrClr`
   thunk from his AoWSetup notes into `AoWDevX.exe`, where that address was mid-instruction garbage.
   Re-derive from the target binary's own import table every time — the sharper form of our existing
   "per-executable patches only affect that binary" rule: *addresses* don't transfer either, only the
   technique does.
4. **Two of his scripts are actively dangerous if ever run from this game root, by name:**
   - `ai_combat_spell_antispam_patch.py` — bare relative `"AoWEPACK.dll"`, no dry-run, no `--apply`
     gate, no backup, unconditional write at the end. This game root contains a stale `AoWEPACK.dll`
     (2,785,792 bytes, dated 2025-07-29 — **not** the loaded module, which is `AoWEPACK.dpl`) that it
     would target.
   - `mouse_wheel_scrolling_patch.py` — targets `VCL30.dpl`, the one filename we share with him
     outright.
5. **AoW+-specific findings of his do not apply to us.** His Designer-Only Portrait Filter exists only
   to undo an AoW+ change; his `GetLanguage` force-English patch sits on an AoW+ base we don't share.
   Anything at the *engine* level transfers; anything patching an AoW+ deviation does not.

## 2. What the archive contains

⚠ **The folder numbers are not chronological.** True arrival order:

**share2/3 (2026-07-24) → share5 (through 2026-08-15) → share4 (2026-08-15 → 08-24) →
share6 (2026-08-24 → 2026-09-01) → share7 (2026-09-15) → share8 (2026-09-23).**

`share1/` is not a drop at all — it is **our own** distillation of share2+3, written 2026-07-29 →
2026-09-02.

| folder | true date range | subject | files |
|---|---|---|---|
| `share1/` | n/a — ours | our distillation of share2+3, one file per topic + `Inioch_INDEX.md` | 21 (2,658 lines) |
| `share2/` | 2026-07-24 | 55 `patch_*.py` scripts — leveled-ability reworks, XP/medal/rank/morale/upkeep, the Reflecting Pool bundle, GlobalSpells, blood, tools — plus `engp.py`/`hse.py` | 55 |
| `share3/` | 2026-07-24 | 18 feature docs (new abilities, combat rules, system/MP/UI, editor/client, world/graphics, the ability-id map) + 11 appliers + his `README.md` + `Patch Scripts Catalog.md` | 33 |
| `share5/` | 2026-07-31 → 2026-08-15 | 33 memory notes + 75 patch scripts — the mouse-wheel foundation (both halves), the LAN desync investigation, borderless fullscreen, mapgen, the keeper2 crash, defender-retaliation, hero-tactical courage | 109 |
| `share4/` | 2026-08-19 → 2026-08-24 | 11 memory notes + 50 patch scripts — AoWx project internals (installer, release process, exe string pipeline, an AI turn hang) + mouse-wheel extensions (power slider, party-arrow cycling) | 62 |
| `share6/` | 2026-08-24 → 2026-09-01 | 25 new + 12 updated memory notes + 78 new patch scripts + installer/manual sub-trees + `README.txt` — his v1.37.406→407; the parts relevant to us: the AI-site-search/item-loot Tier-1 candidates, the action-stream architecture finding, the `.mld` bank, `diag_inject_veh.py` | 92 |
| `Inioch_Share6_Catalogue.md` (root) | n/a — ours | our distillation of share6, written 2026-09-02 | 1 (317 lines) |
| `share7/` | 2026-09-03 → 2026-09-15 | his 1.37.410 work in progress: 29 memory notes + 36 scripts. Adopted: `build_leadership_others.py` (2026-09-16). Superseded by share8 | 65 |
| `share8/` | 2026-09-03 → 2026-09-23 | his 1.37.408–410: the whole script folder and all 129 memory notes, plus the 410 changelog and an all-releases changelog | 463 |
| `Inioch_Share8_Catalogue.md` (root) | n/a — ours | our distillation of share8, written 2026-09-24 | 1 (555 lines) |

Three more directories sit alongside the shares and are not notes at all — see §10.

## 3. share1 file map — the detailed reference, one line each

**Combat & abilities**

- `Inioch_Ability_Registration_And_IDs.md` — the registration blocker (abilities are built across
  interleaved passes, so "free now" ≠ free; picking a live id gets a Runtime error 217, picking too
  high gets a Localize.dpl crash, only a never-registered id is safe), the id-derivation playbook
  (inline-`Create` scan, the RStr export table, the leveled-base-ctor `0x55765168` shortcut, the
  vmtSelfPtr trick), verified permanent gaps `0x51`–`0x55` / `0x66`–`0x69` / `0x85`–`0x89`, and the
  full verified id map. Open items, below, carries the still-unresolved ceiling question it raises.
- `Inioch_Combat_Damage_Status_Funnels.md` — the **two unit-class VMT layouts** (strategic vs combat —
  `HasAbility` is `[self+0x88]` on one, `[self+0xA8]` on the other; mixing them silently does nothing
  or reads garbage, no crash), the four damage/status funnels and where a multiplier belongs in each,
  the damage-type bit table.
- `Inioch_ATK_Getters_And_Penalties.md` — the stat-level-vs-strike-time design split (a modifier that
  depends on the *target* cannot live at the stat getter, because the target doesn't exist there yet),
  the three strike-time injection sites (the same ones our own slayer work uses), and the
  `GetAttackRA` return-accumulator trap (trap 12, §7).
- `Inioch_AI_Combat_Spell_Architecture.md` — **two combat contexts, two value paths**: fast/auto-resolve
  scores via `fcGetDamageValueEx`, tactical scores via `GetCombatDamageValueEx`. A command-driver
  spell is dropped only by an exact-0 value, never by deprioritising it. The universal tactical
  cast-hook is `TSpell.CombatCastingDone @0x557794E8` — fires for every generic combat-spell CA with
  `eax` = the spell object.
- `Inioch_AI_Hero_LevelUp_Chooser.md` — the vanilla `ExecuteUpgradeHeroAI` weighted-list chooser
  (`Engine.TDoubleItemList`), the two-weight bank/lock-in mechanic vanilla already uses for
  Spellcasting alone, and the infinite-loop landmine (trap 14, §7).

**World & structures**

- `Inioch_Structure_Raze_Framework.md` — razeability is a hardcoded constructor flag
  (`resource+0x58`), not data; the flag alone does nothing without a real `SetRazed`/`GetRazed`
  override (base-class stubs let a "razed" structure keep working and be razed repeatedly); the full
  vanilla raze/rebuild flow, MP-safe via a network token; a worked example on `TReflectingPool`.
- `Inioch_Save_Serializer_Tagged_Fields.md` — an independent discovery of the same version-tolerant
  property-table mechanism documented in `11-engine-internals.md`; adds the corollary that an
  **already-serialized-but-unused** field is free persistent storage, worked via
  `THeroUpgradeEventLog`'s `[+0x20]` (repurposed to hold a stored view location + valid flag).
- `Inioch_PerHex_Decoration_And_Road_Cost.md` — how to read what is *sitting on* a hex: match
  `MapFieldMsgProc == 0x5579BE0C` at VMT `+0xCC`, not `FindChild`/`FindNoneTransparentHS` (both fail
  here); decoration category lives at `[resource+0x44]`; several dead ends documented so they aren't
  retried. Confirms our live road-build cost is already flat 5, not vanilla's flat 10 — an
  undocumented pre-existing Ziggurat change.
- `Inioch_Path_Terraform_Mechanism.md` — the vanilla Path/terraform framework in full (gates, terrain
  callback contract, terrain byte table). Cross-check only — our own Path of Sand already owns both
  of his hook sites, independently, at the same ability id (`0x9F`).

**Systems & UI**

- `Inioch_Sphere_Selection_Model.md` — `TLeader.CanAddSphere` / `GetSpherePicks` fully mapped. We
  already have this feature, byte-identical to what he documents — nothing to port, but the sphere
  enum and `[spell+0x20]` are independently reusable. See `04-spells-modded.md`.
- `Inioch_MP_Race_Setup_Model.md` — the full lobby race-record data model; the key insight that claim
  logic keys off `rec[0xC]==0` (unclaimed), never off the owner-type byte, so changing a default owner
  needs zero claim-logic edits.
- `Inioch_Event_Log_Model.md` — event-log class map, the two `ViewLocation` patterns
  (follow-the-object vs a stored fixed location — battle events already use the latter), and the PIC
  VMT-identity compare technique for identifying an object's class from a hook. See
  `06-unit-spellcasting.md`.
- `Inioch_Registry_Path_Constants.md` — the Delphi const **lengthen-in-place** trick: bump the length
  dword, write the extra characters into the constant's own pad bytes, leave every load site
  untouched. Reusable for any short UI/label text edit that has slack. **Adopted 2026-09-09** as
  `build_regiso.py` (§4).
- `Inioch_MouseWheel_VCL30.md` — the whole wheel stack. The failed WH_MOUSE delivery attempt is in
  Failed approaches, below; the working `WH_MOUSE_LL`-on-a-dedicated-thread architecture and the full
  address-transfer verification against our binaries live in the file itself. Our adoption spec:
  `07-ui.md`, folded into `07-ui.md`.
- `Inioch_Editor_Resource_DFM_Relocation.md` — growing a DFM by appending the enlarged resource at EOF
  and repointing six PE header fields; the dead old-DFM region becomes a safe reloc-free data cave;
  editor CODE zero-runs are *not* safe the same way (trap 15, §7).

**Data formats & tooling**

- `Inioch_PFS_HSS_Format.md` — extends `re_tools/pfs.py`: the ability-owner bitfield encoding,
  `Ability.pfs` tag 9 (the hero-learnability bits), the `ITEMS.PFS` tag map, and a per-face-file
  portrait index-base gotcha (some custom face packs are 1-based, not 0-based).
- `Inioch_ILB_Pixel_Formats.md` — all three ILB pixel formats; the row-stride-rounding trap; 8bpp RLE
  unit sprites and the 6-direction/12-frame layout. Pairs with his later, more format-complete
  `ilb-image-format.md` (§5) — his covers the record/container layer, this covers the pixel layer.
- `Inioch_Custom_Music_IT.md` — wrapping a track as a no-loop single-sample `.IT`; the loudness lesson
  (the 1999 mixer sums **channels**, not sample RMS — trigger 2+ channels rather than hot-rodding a
  single sample).
- `Inioch_Tools_And_Script_Inventory.md` — which of his scripts are safe to even *read* near this game
  root, which are actively dangerous if run (standing rule 4, §1), and the Raise Terrain failed
  approach (Failed approaches, below).
- `Inioch_Cave_And_Hook_Traps.md` — folded into the merged trap list, §7.

## 4. Findings we adopted

### `build_ai_sitesearch.py` and `build_ai_itemloot.py` — his Tier-1 "door we left open"

Our own memory already recorded that AI item pickup shipped (confirmed 2026-07-21) but targeting was
reverted the next day, and that **`TStructure.ExecuteAI` is a `return 0` stub** — a door deliberately
left open. Both scripts walk through it. Both were re-derived independently on **our** `AoWEPACK.dpl`
— his cave VAs were not reused (standing rule 1, §1).

- **The door:** `TStructure.ExecuteAI` (VMT `+0x1C0`, `0x5575E698`, `33 C0 C3`) and `UpdateAITarget`
  (VMT `+0x1C4`, `0x5575E69C`, `C3`) are both no-op stubs on every exploration-site class, dispatched
  from `TStructureAIPA.Execute @0x557625F4` and `TStructure.MapFieldMsgProc @0x5575F730`
  (message `0x1200`).
- **Why the override sits at `MapFieldMsgProc +0xCC`, not `UpdateAITarget +0x1C4`:** the `+0x1C4`
  dispatch receives only `ctx` and a result record — not the asking `TAIGroupControl`, which a
  strength-aware search needs. That group pointer is visible only one level up, at `[msg+0x10]` in the
  message `MapFieldMsgProc` itself receives. (This is v2 of his own script; v1 tried `+0x1C4` and had
  to back out.) Confirmed against both vanilla callers of `GetAITarget`
  (`TAIMoveTargetSelector.ProcessStates`, `TAIGroupControlTarget.Validate`) — both pass a real group.
- **Why targeting works now, where our 2026-07-22 attempt was reverted:** the old
  `build_ai_itemtarget.py` answered the AI-target broadcast with a flat value-based priority that
  ignored *who was asking* — AI stacks with no hero, or with heroes already better equipped, walked to
  the item and then loitered beside it. `build_ai_itemloot.py` answers **only if some hero in the
  asking group would actually take the item**, using the identical valuation the pickup worker itself
  uses, so pickup and targeting can never disagree about whether an item is worth having.
- **Three reusable RE facts that came out of building it** — each a rule for any future code that
  touches `TItem`:
  - `TItem` is an ability **owner**, not a container — `[item+8]` is a **bitset pointer**, not a
    `TList` of children. Walking it as a list AVs on low-id items.
  - `[item+0xC]` is the bit **capacity** and must bound every scan; its own accessor (`GetAbSet`, VMT
    `+0x4C`, `0x5574E0E0`) is `cmp edx,[item+0xC]; jae false; bt [[item+8]],edx`. When replicating an
    engine bitset walk, copy the engine's own accessor, bounds check included.
  - The engine's inventory free-slot finder (`0x5578601C`) returns **−1 on an empty list**, and hero
    inventories start empty — probe with the getter `0x55786284` instead.

Full addresses, cave layout, the `--undo` commands and the in-game checklist: `10-ai-and-structures.md`.

### `build_regiso.py` — registry isolation, his technique and his six addresses

Adopted verbatim where it transfers, and extended where his own scope is short. His six
`AoWEPACK` sites are byte-identical on our DLL *and* on the pristine backup, so his addresses carried
over with no re-derivation — the one place in this archive where that is true of a *patch site* rather
than a read-only anchor, because the constant is vanilla data he never moved.

Two deviations, both ours:

- ⚠ **`AoWSetup.exe` carries three more copies** (`0x066480`, `0x066570`, `0x066668`). His
  `Registry Isolation.md` asserts the path lives only in `AoWEPACK`. That is right for the game exe
  and both editors (scanned, zero hits) and wrong for AoWSetup, which statically links its own `rw*`
  helpers. Half-applied, the setup program writes settings to the old tree while the game reads the
  new one and nothing reports an error. **Worth sending back to him** — if his AoWSetup has them, AoWx
  has this live.
- Our suffix is `" Z"` (`…\Age of Wonders Z\`) against his `" X"`, so the two mods and vanilla each
  hold a distinct key and all three can be installed at once.

**Companion adopted the same day: his AoWSetup install-check fallback** (`build_aowsetup_installcheck.py`).
Applying the isolation collapsed AoWSetup's home screen to Install/Exit, the identical symptom that
bit an AoWx player on 2026-08-13 (`share6/memory/aowsetup-installcheck-devtab.md`). ⚠ **His cause
does not explain ours** — his was a fresh install whose isolated tree did not exist yet, so the read
genuinely returned nil; ours reads correctly and the check still failed, and the mechanism was never
found. His remedy applies regardless because it removes the registry from the check entirely: a `'.'`
fallback when the getter's out-string is nil, so it tests `FileExists('.\aow.exe')`. Cave re-derived
per standing rule 2, not reused (his `0x004698E0`; ours `0x0046980C`/`0x00469820`). Full write-up,
including the ruled-out list so nobody re-measures it: `11-engine-internals.md`.

⭐ **What this settles about coexistence generally:** AoWx's answer to "install alongside vanilla" is
**a separate folder plus this key edit**, never renamed game files — his installer's own wording is
"make a separate *Age of Wonders X* folder (your vanilla folder is copied and left untouched)"
(`Inioch/share6/patch scripts/installer/AoWxInstaller.iss:687`). The `AoWx.exe` / `AoWDevX.exe`
renames are branding only. Reasoning and the argument against renaming ours:
`11-engine-internals.md`.

### `re_tools/veh_capture.py` — ported from his `diag_inject_veh.py`

Called "the single most reusable thing in the drop" (share6 catalogue, Tier 4) for good reason: it
launches the target **suspended**, injects a vectored-exception-handler shellcode via a remote thread,
resumes it, and on a matching fault **freezes the faulting thread in place** (`pause; jmp $`) with
`CONTEXT` and the stack captured — then reads all of it out-of-process. It exists because the crash it
was built to catch **never reproduced under a real debugger**: Delphi 3 uses its own memory manager,
so attaching a debugger perturbs heap layout enough that an out-of-bounds read lands on benign memory
and the fault stops happening (`_NO_DEBUG_HEAP` does not help — that switch only governs the Windows
heap). Complements `re_tools/hang_stack.py`: that tool is for a game that is frozen and alive; this one
is for a game that crashed or vanished.

Changed from his version, not just re-pointed at our binaries: no hard-coded install path, a
selectable target executable, a data-driven fault filter instead of one baked-in address, runtime
module-base resolution (every address is resolved against where the target *actually* loaded, with
both the link-time VA and the file offset printed — the `.dpl` packages rebase), an exception census
mode, and an end-to-end self-test. Full usage: `12-re-toolchain.md`.

## 5. Catalogued but not built

### The `.mld` localisation bank — the centrepiece

Source: share6 `mld-localisation.md` + `patch_mld_repair.py` + `patch_translations_aowx.py` (Tier 4
tooling, `Inioch_Share6_Catalogue.md` §3). **We have no `.mld` tool of our own**, and this is directly
relevant to renaming — any ability/spell/unit name change goes through `Dict/ResStr.mld`.

- Full format reversed: **8 dictionaries**, 6,683 records, a codec that round-trips **32/32** of his
  live files byte-identically.
- **Records have no ID.** The key is the `Original` English string. Never edit `Original` unless the
  matching `Release/*.pfs` record or DFM text changes with it in the same edit — otherwise the lookup
  key breaks and the translation silently orphans.
- ⚠⚠ **`MLDEdit` corrupts every file it saves**: it never writes `Primary`, writes
  `ISODefaultCountry` twice overlapping, never recomputes header offsets, and saves without
  truncating. 6 of his 8 live files were already damaged by it before he wrote this up. **If a `.mld`
  in this project has ever been opened and saved in MLDEdit, check it** — the visible symptom is
  `alAuto` language matching breaking.
- **Not built: nobody has written a reader/writer against this format on our side.** The next time a
  rename needs `.mld` surgery, build a minimal reader/writer from his round-tripping codec description
  rather than touching MLDEdit at all.

### Also catalogued, smaller

- **`ilb-image-format.md`** (share6, Tier 4) — a validated `.ILB` container spec, **689/689** game
  files parse and round-trip. Two terminator gotchas that break naive parsers,
  `clipwide`/`cliphigh`/`xshift`/`yshift` are **signed**, and a latent overflow in IlbMaker's 8-bit run
  counter. Supersedes guesswork if we ever touch ILBs again; pairs with our own
  `share1/Inioch_ILB_Pixel_Formats.md` (§3), which covers the pixel layer his container spec doesn't.
- **`cam-campaign-format.md`** (share6, Tier 4) — `.CAM` fully reversed, all 12 campaign files
  round-trip. Nothing currently needs it; sitting there if campaign tooling is ever wanted.
- **`build_mod_manual.py`'s PFS/ILB decoder** — the one script of his that is directly runnable
  against our install as-is (read-only over `Release/*.pfs` plus the face ILBs; writes one
  `Mod Manual.html`). **Known bug, not yet fixed in the shared copy:** it tests hero-level-up
  eligibility as `bool(sel & 0x80) and bool(sel & 0x100)` (`build_mod_manual.py:156`); the engine
  itself tests only `[ability+0x21] & 1`, i.e. **`sel & 0x100`** alone — `0x80` is
  `astCustomizeLeader`, unrelated. It is coincidentally right for every vanilla ability (bits 7 and 8
  happen to agree in stock data) and wrong for any ability we mint ourselves. **Our own
  `build_ziggurat_manual.py` already uses the correct `& 0x100` test** (line 1105) — only the shared
  hand-out copy carries the bug. One-line fix, worth doing before this copy is handed to anyone else.

## 6. Standing constraints his work established for us

### ⭐⭐ Fast combat is an action-stream architecture — a cave that pokes HP is invisible to the replay

Every tactical-combat effect is a `TCombatAction` object. `AddAction @0x55727224` **records** it into
a replay stream whenever `[combat+8] & 4`, then executes it. **Autocombat "replays" are TCPCK's
`TTacticalCombat` re-executing that deserialised stream** — not a re-simulation. So a cave that writes
a unit's HP directly, anywhere outside a `TCombatAction.Execute`, is invisible to whatever reads the
stream afterwards: the simulation is correct and the screen diverges — units can appear to die,
resurrect, or fail to heal, with no error anywhere. He burned five rounds on exactly this before a
diagnostic ring buffer proved the simulation had been right all along. The fix is always the same
shape: **emit the appropriate `TCombatAction`** (e.g. a `THealingCA` with the amount serialised into
it) instead of writing state directly.

CA layout: `+0x8` refcount, `+0xC` flags (vanilla uses bit 0 only), `+0xD`/`+0xE` unit ids,
`rw = [vmt+0x18]`, `Create` at VMT `+0x20`, `Execute` at `+0x50`, release at `+0x2C`.

**Audited against everything we ship, 2026-09-02 — nothing currently trips it.** Every one of our
in-combat HP writers already hooks *inside* a `TCombatAction.Execute`, by construction rather than by
having been checked against this rule after the fact:

| script | hook point | why it's already safe |
|---|---|---|
| `build_reformingflesh.py` | `TNewCombatRoundCA.Execute`'s own per-object dispatch loop, `0x5572A3BC` | flat +5, no RNG — inside the recorded action |
| `build_lifesteal_roundattack.py`, `build_assassin.py` | inside the `TStrikeCA.Execute` region, `0x5576678C`–`0x557668E7` / `0x557665E4`+ | inside the recorded action |
| `build_firefeed.py` | the strategic `ExecuteDamageRole` / `TriggerFireDamage` path | not fast combat at all — exempt by construction |

**Still a live constraint for the next auto-resolve feature:** anything that changes unit state during
combat must go through the action stream, not around it. Two free facts from the same investigation:
`TCombatUnit.Get/SetHitPoints` (`0x55725064`/`0x5572507C`) forward to the **strategic** unit's
`+0xE0`/`+0xE4` (clamped) — combat HP *is* strategic HP, live, in both combat systems — and
`TCombat.NewRound @0x557273FC` broadcasts to combat slot `+0xF4`, a **vanilla no-op**: a free
extension point for anything that needs to run once per round. Relevant thematic coverage:
`01-combat-maths.md` (the action-stream/RNG substrate) and `10-ai-and-structures.md` (any AI-driven
autocombat feature that would need to respect this).

### The RNG doc is right outside combat, and incomplete inside it

`lan-desync-investigation.md` (share5/6) derives the same two-generator model independently, and adds
one constraint our own RNG doc does not yet state: after `TCombat.Execute`'s one-line re-anchor, the
**raw** stream *is* replicated across machines — **as long as both consume the same number of
`@RandInt` draws between two synced draws.** Our doc's framing ("raw draws mean two machines get
different numbers") is true outside combat and misleading inside it. **A cave that makes a
*conditional* raw draw in combat is a silent MP-divergence risk distinct from picking the wrong
generator** — every static check, including `rng_audit.py`, still passes, because the generator choice
was correct; only the *draw count* differs between machines.

He found and fixed exactly this in **vanilla** `TMindDecay.CreateCA` (five gates, four dereferencing
`[combatunit+0x4C]`, all guarding a `HitRole` call) — `build_minddecay_oos.py` hoists the draw out of
the gates and gates only the *store*. The gates are byte-identical to our own vanilla bytes, so if
Mind Decay ever desyncs for us it is this vanilla defect, not something we introduced (a Tier 2
adoption candidate — not yet built on our side). Also worth carrying forward: **AIPAs and AI run
identically on every machine** — Global players are locally simulated everywhere, never simulated on
one machine and broadcast — which is *why* an AI-side cave can safely mint tokens.

This draw-count refinement is not yet folded into `01-combat-maths.md`'s RNG section (see Open items).

## 7. The trap list — merged and de-duplicated

Core of the list: `Inioch_Share6_Catalogue.md` §5 (11 numbered traps, 1–11 below) plus the four items
`share1/Inioch_INDEX.md`'s adoption list (item 18) flags as genuinely new to us out of
`share1/Inioch_Cave_And_Hook_Traps.md` (12–15 below). That file's other six items are independent
rediscoveries of rules we already hold (PIC rebasing, the `.reloc` steal-the-call trap, BSS-not-CODE
scratch, and the diagnostic of repointing a value method to force-0 to find its control point) — kept
as confirmation, not restated here. Two more genuinely load-bearing traps surfaced elsewhere in share1
and share5 and are folded in as 16–17. Checked against each other, none of the 17 overlap.

1. **Copy a proven call sequence positionally, never by inferred parameter names.** A tactical-heal
   cave AV'd because he permuted `GetFieldXYL`'s arguments by guessing which was x/y/level instead of
   copying the working call's exact `edx`/`ecx`/stack order.
2. **Pick one PIC anchor scheme and stay in it.** Mixing "pop a runtime anchor, no `sub`, address as
   `[reg + (target − anchor)]`" with "pop, `sub` to get the delta, then displace by
   `target − anchor`" produces `target + Δ − anchor` — a wild read. Cost him a first-cast crash.
3. **A code cave in an R-X section may hold code and constants only.** Caching a resolved function
   pointer *inside* a `VCL30.dpl` cave (CODE there is R-X) killed both apps instantly with no dialog —
   an AV inside a `WH_MOUSE_LL` proc goes straight to desktop. Mutable state belongs in a writable
   section or, better, on the stack.
4. **Thunk and helper addresses are per-binary; they do not port even conceptually** — see standing
   rule 3 (§1), which is where this trap came from.
5. **A single call site does not identify a VMT slot — confirm the callee's body.** He inferred
   `+0x18 = SetParent` from one caller; it is `SetName` (`SetParent` is `+0x3C`), and the bug shipped
   to a user.
6. **Never claim "free" space by scanning for zeros in a section you already own.** Zero runs at the
   end of a patch-owned section were runtime buffers; the first write clobbered his own jump tables.
   Use a dedicated appended section instead.
7. **`SizeOfImage` must be recomputed from the MAX end over *all* sections**, not just the one you
   appended — otherwise a later section silently unmaps. Same class of bug: a re-apply path that
   rebuilds the file as `header + body` destroys any section appended after yours; overwrite in place
   when the body fits.
8. **The reachability of code you replace is a superset of the cases your new gate imagines.** He
   added an "own units only" gate to party-arrow display; vanilla had no ownership test at all, so
   enemy stacks got visible-but-dead arrows. Enumerate who actually populates the state a feature
   reads *before* inventing a safety condition it never had.
9. **When rewriting a cave's per-iteration tail, re-audit every `pop` against the push inventory on
   every exit path.** A +4-per-heal stack leak, absorbed by a later `popad`, presented as a crash
   inside an unrelated engine function.
10. **keystone hangs — does not error — on `;` comment lines** inside asm blocks; strip comments
    before `ks.asm()`. It also exposes no symbol table, so measure a cave's internal label offsets
    with a jump table at the cave head, not by assembling line prefixes.
11. **The Bash-tool heredoc unescapes `\\` → `\`**, so a Python byte literal like `b"\\x00"` written
    through a heredoc lands in the file as a real NUL byte. Build such literals with
    `chr(92)+'x00'`, or write the file with Write/Edit instead of a heredoc.
12. **`ebx` is `GetAttackRA`'s return accumulator** (`TRangedAttackAbility.GetAttackRA @0x5576E65C`
    returns via `mov eax,ebx` at every exit). He stashed a range tier in `bh`; a caller that read the
    *wide* return value got a corrupted pointer and crashed in a downstream `GetLocation` call.
    Generalises: before using any register as cave scratch, check what the function returns and how —
    a byte result in a wide register leaves the upper bytes live for some callers.
13. **Guard every display/strength-evaluation path for unplaced or prototype units.** City production,
    unit lists, AI strength evaluation and map-load all call stat getters on units that are not fully
    placed. Guard: null `[unit+4]` (location link), null `[hero+8]` (ability-bitmask pointer), or
    `GetLocation` returning `0xFF` (unplaced sentinel). Both of his melee ATK caves acquired these
    guards only after crashes.
14. **Making a bounded list unbounded removes its terminating condition.** `ExecuteUpgradeHeroAI`
    stops when its option list goes empty; a chooser rewritten to always offer every learnable
    ability makes that list permanently non-empty, and a hero with points below the cheapest option's
    cost then spins forever — a new-game or end-turn hang. Whenever an emptiness/exhaustion exit is
    removed, a replacement exit must be supplied.
15. **In the editor exe, CODE zero-runs are not safe scratch — they carry base relocations.** Opposite
    of `AoWEPACK`: `AoWDevEd.exe`/`AoWDevX.exe` CODE zero-runs are embedded RTTI/data with real
    relocations, and writing there is an access violation. The safe cave in that binary is dead,
    repointed-away `.rsrc` space — e.g. the tail left behind by growing a DFM
    (`share1/Inioch_Editor_Resource_DFM_Relocation.md`, §3).
16. **Two scripts that gate on each other via a shared "magic byte" can be silently unlinked by an
    unrelated edit.** His VCL30 pump hook and its `WH_MOUSE_LL` proc both check
    `cmp byte [aowbase+0x22880], SIG` — the aowInt half's own first opcode byte — before calling into
    it. Rewriting that helper's prologue (`push ebx` → `push ebp`) changed the byte from `0x53` to
    `0x55` and silently killed wheel scrolling everywhere, with no crash. Any cross-script signature
    check must track the *other* script's actual current bytes, and both scripts must be re-applied
    together.
17. **A baked absolute path breaks the moment the project moves machines — and he hit it first.** His
    own dialog-directory-memory patch (his `build_dlgdirs.py`, ported from our own
    `08-editor.md`) originally baked the absolute `AoWEd_LastDirs.ini`
    path into the `.dlgd` sections of `AoWDevX.exe` and `HSEPack.dpl` at build time. His 2026-07-31
    home-PC → laptop transfer silently broke it: reads came back empty (a silent fallback to vanilla
    behaviour) and writes failed with no error. Fixed the same day by deriving the path at runtime
    through `GetModuleFileNameA` (his VCL30 IAT slot `0x413E43C0`) instead of baking it — source:
    `share5/memory/baked-absolute-paths-gotcha.md`. **We hit the identical defect independently** in
    our own `build_dlgdirs.py` (a resolved `GAME` path baked into the blob written into `HSEPack.dpl`
    and `AoWDevEd.exe`); see `08-editor.md` for our occurrence and fix. ⚠ Housekeeping:
    `CLAUDE.md`'s "baked absolute paths" section currently cites this as
    `Inioch_Share4_Share5_Catalogue.md` **trap #17** — that file was deleted 2026-09-02 (§8). This
    entry is its replacement; the citation should be repointed here.

## 8. share4 / share5 — reviewed; the catalogue was retired

**These two drops were gone through.** `Inioch_Share4_Share5_Catalogue.md` existed, did its job, and
was deleted on 2026-09-02 once its findings had been dispositioned — that is the project's own
"delete superseded analysis" rule working, not an oversight. **This is not a backlog.**

**What came out of them:**

| adopted | became |
|---|---|
| exploration-site / AI site handling | `build_scripts/build_ai_sitesearch.py`, `build_scripts/build_ai_itemloot.py` (see `10-ai-and-structures.md`) |
| VEH crash-capture technique | `re_tools/veh_capture.py` |

Everything else — defender retaliation, hero tactical courage / AoO, the keeper2
`ArmyCombatMoveTE` crash family, borderless fullscreen, the mapgen and AoWSetup work — was reviewed
and **not adopted**. Those are AoWx features, tied to his cave allocations and his binaries; nothing
in our tree references them, which is the expected outcome, not a missing record.

⚠ **Per-finding records were deliberately not kept.** If a specific share4/5 finding is ever wanted
again, the raw files below are the source — re-read them rather than assuming a summary exists.

### Archive index — where things are, if you need to go back

Use this to *find* a file, not as a list of work outstanding.

| topic | file(s) | folder |
|---|---|---|
| Hero tactical courage / attack-of-opportunity, v5 | `hero-tactical-courage.md` | share5 (updated in share6) |
| Defender retaliation, v6.1 | `defender-retaliation.md` | share5 (updated in share6) |
| The keeper2 `ArmyCombatMoveTE` crash family | `keeper2-armycombatmovete-crash.md` | share5 (updated in share6) |
| Exploration-site fix | `exploration-site-fix.md` | share5 (updated in share6) |
| Borderless fullscreen | `borderless-fullscreen-feature.md` | share5 (updated in share6) |
| Map generator, v6.4 | `mapgen-build-and-state.md`, `mapgen-no-regen-after-changes.md` | share5 |
| AoWSetup internals | `aowsetup-internals.md`, `aowsetup-installcheck-devtab.md` | share4 / share5 / share6 |
| LAN desync investigation | `lan-desync-investigation.md` | share5 (one finding extracted: §6 above; the rest unread) |
| The release pipeline | `aowx-release-process.md`, `aowx-installer.md`, `aowx-project-overview.md` | share4 |

**Also in the archive** — listed so a specific file can be found again, not as work outstanding:

- **share4/memory:** `aowdevx-binary-notes.md`, `aowepack-ability-system.md`, `aowint-cave-map.md`,
  `aowint-toolkit-internals.md`, `aowx-ai-turn-hang.md`, `aowx-exe-string-pipeline.md`.
- **share5/memory:** `adblocker-hides-adv-classes.md`, `aowepack-dll-is-live.md`,
  `editor-patch-audit-2026-08-05.md`, `ghidra-mcp-setup.md`, `ingame-version-location.md`,
  `intro-video-codec-fix.md`, `magic-sight-spell-re.md`, `map-password-unlock.md`,
  `multilevel-ability-heal.md`, `patching-over-relocs-gotcha.md`, `pfs-unitres-format.md`,
  `project-state-2026-07.md`, `scenario-hp-topup.md`, `spring-of-life-wasteland.md`,
  `summon-mermaid-spell.md`, `summon-silver-dragon-spell.md`, `tcai-defender-hold-response.md`,
  `te-exception-dialog-diagnostic.md`, `transfer-back-home-2026-08-09.md`,
  `unitfloater-selectioncontrol-map.md`, `warp-self-combat-spell.md`.
- Both folders' `patch scripts/` subdirectories (50 + 75 files) are AoWx's own patch appliers —
  reference material, never to be run against our tree (§1). The handful we cared about are named in
  `share1/Inioch_MouseWheel_VCL30.md`.

**What a future pass must cover:** open each memory file, check it against our own tree the way
`Inioch_Share6_Catalogue.md` does (byte-verify any address that touches our binaries, note anything
that contradicts a finding of ours already on record), and produce either a rebuilt
`Inioch_Share4_Share5_Catalogue.md` or a direct merge into this file. Until then, treat every topic
above as **unknown territory**, not as "probably fine because share6 didn't flag it" — share6 only
cross-checks what changed *since* share5, not share5's own content against our tree.

## 9. Redundancy note for future drops

Inioch resends his **entire** Claude memory index with every share, not just what changed. Measured
across share4/5/6: **29 files share one of only 14 basenames** — `MEMORY.md` itself (present in all
three), three more shared between share4 and share6, and ten more shared between share5 and share6.
Six of those are the previous copy verbatim plus a roughly 5-line append.

**When the next share arrives:** diff its `memory/` folder against the *previous* share's `memory/`
folder by basename first, before reading anything. Anything byte-identical or near-identical to a
file already catalogued needs no new read at all; only genuinely new basenames and materially-changed
repeats are worth opening.

## 10. Archive footprint and redistribution

**452 MB total, of which 446 MB (98.7%) is three third-party binary payloads, not notes:**

| item | size | what |
|---|---|---|
| `AoWx_Modding_Tools_1_01_0002/` | 246 MB | his modding-tools distribution |
| `AoWx Installer (version 1.37.407)/` | 200 MB | his game installer |
| `AoWx face selection/` | 176 KB | bitmaps |

The knowledge corpus — share1 through share6 plus `Inioch_Share6_Catalogue.md` — is under 6.5 MB. The
two large payloads are **distributions, not notes**; they are candidates for moving out of the working
tree the next time this archive is groomed, since nothing in this file or its sources reads them for
RE material.

**⚠ Whether any of Inioch's material may be redistributed if this folder is ever shared is a question
for the owner — not asserted here either way.** No licence, copyright or redistribution statement was
found anywhere in the archive (checked, case-insensitively: every `.md`/`.txt` file for
"licence"/"license", "copyright" and "redistribut"). The only two hits are share6's own note about
*our* obligation not to pass his leaked path onward, and an unrelated in-game copyright label
mentioned in passing in a bitmap-fonts memory note. Silence is not permission — ask before sharing.

## Open items

- **The ability-id ceiling conflict is still unresolved by test.** He believes usable ids top out
  around `0xA9` (a Localize.dpl crash above it, on his AoW+ base). Our own figure has since moved past
  the framing he was comparing against — the "`0xCD` is a hard save-format limit" derivation was
  itself wrong; the real constraint is `TAbilityOwner.ReadWrite`'s one-byte tag scheme, current
  recommended range **`0xB3`–`0xCD`** (27 ids, see `03-abilities-added.md`), and that range is
  **untested above `0xCD` regardless**. Neither his `0xA9` ceiling nor our corrected range has been
  settled against the other with an in-game test. The cheap decisive test, still not run: register one
  throwaway ability at `0xAA` and launch. His 21-item permanent-gap enumeration (runs at
  `0x51`–`0x55`, `0x66`–`0x69`, `0x85`–`0x89`) stays useful as a candidate list regardless of how the
  ceiling resolves.
- **The RNG doc's draw-count refinement (§6) is not yet folded into `01-combat-maths.md`.** Do that
  the next time that file is touched, rather than leaving the fuller picture only here.
- **`build_mod_manual.py`'s hero-eligibility bug (§5) is unfixed in the shared copy.** One-line change
  (`& 0x100` in place of `bool(sel&0x80) and bool(sel&0x100)`), harmless to fix any time.
- **`CLAUDE.md`'s "baked absolute paths" section cites a deleted file** —
  `Inioch_Share4_Share5_Catalogue.md` trap #17. Trap 17 in §7 above is its replacement; the citation
  should be repointed there.
- **No `.mld` reader/writer exists on our side** (§5) — the next rename that touches
  `Dict/ResStr.mld` is the trigger to build one from his format description.
- **Nothing outstanding from share4/share5** (§8). They were reviewed, the site-search work was
  adopted, and the rest was dispositioned as AoWx-specific. ⚠ Per-finding records were not kept — if
  one is wanted again (courage, defender-retaliation, the keeper2 crash family), re-read the raw
  files rather than assuming a summary exists.

## Failed approaches — do not retry

- **A `WH_MOUSE` hook at `TApplication.Run`, to detect the mouse wheel in-game.** Never fires in the
  game process — proved with diagnostic message boxes, it fires in the editor and nowhere else.
  Windows delivers `WM_MOUSEWHEEL` only to the **focused** window, and the game's render window never
  becomes focused (it does receive `WM_MOUSEMOVE`). The fix that worked is a system-wide `WH_MOUSE_LL`
  hook on a dedicated thread, decoupled from the render/message-pump thread entirely. The lesson worth
  keeping regardless of feature: **verify delivery before writing any consuming code** — he spent
  effort on the scroll-side logic before checking whether the wheel arrived at all.
- **Attacking Raise Terrain's validity filter to fix underground/lava casting.** Rewrote the terrain
  reject-list into a bitmask and NOP'd the `[field+0x15]` overlay checks — his own script comments
  identify the real blocker even though his catalogue calls it "never found." For lava, the filter was
  never the problem: our own investigation already established `ValidTargetMapF` rejects only
  `0`/`6`/`0xA`/`0xD`, so lava was always a valid target — the cast is wasted because **mountain
  placement fails on lava**, not because targeting rejects it. For underground, his own comment states
  the actual requirement: a second Raised-Mountain-class resource painted Earth, which does not exist
  as an art asset yet. Both failures are asset/placement problems the validity filter was never going
  to fix.
