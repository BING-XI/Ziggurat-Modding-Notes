#!/usr/bin/env python
"""
build_scroll_spellbook.py -- Scrolls as a PERMANENT per-hero spellbook grant.

⚠⚠ THIS SCRIPT NOW OWNS BYTES BELONGING TO A SECOND FEATURE (2026-09-03) ⚠⚠
---------------------------------------------------------------------------
`cave_bookfilter@0x0060C0A8` is shared.  Its stage-1 prune is the UNIT-SPELLCASTING book filter
(M3/M4), which this script absorbed verbatim when it rewrote the cave in place on 2026-07-30.  On
2026-09-03 that prune was CHANGED here to make the tier test unit-only, per the user ruling
"Spellcasting level should only restrict tier of spell that's castable for units, not heroes".
So this file is now the only place the hero-tier exemption exists on the exe side.

  Pairs with:  build_spellcast_herotier.py  (AoWEPACK.dpl -- the cast-gate half of the same ruling)
  Both halves are needed.  Either one alone is a silent no-op:
    * book half missing  -> a hero never SEES the too-high-tier spell, so nothing changes;
    * cast half missing  -> the hero sees it, clicks it, and nothing happens with no message
                            (`cave_tiergate`'s fail arm returns silently).

⚠ `--undo` HERE SILENTLY RE-BREAKS THE HERO EXEMPTION.  `--undo` restores `old_cave`, which is
`build_spellcast_book_exe.py`'s original 130-byte filter -- and that one prunes by tier for
EVERY caster.  Heroes go back to being tier-limited, with no error and nothing in any log.  It
also removes the scroll behaviour, which is the part you were probably aiming at.

  REVERT ORDER (drop the whole hero-tier ruling, both halves):
      python build_scripts/build_spellcast_herotier.py --undo --apply     # DLL first
      python build_scripts/build_scroll_spellbook.py  --undo --apply      # exes second
  REVERT ORDER (drop only the SCROLL feature, keep the hero exemption):
      not possible with `--undo` as written -- it would take the exemption with it.  Re-apply
      this script with the scroll stage disabled instead: `--append-upto=0`, which keeps the
      current (hero-exempt) stage-1 prune and emits no scroll append.
  The DLL half is independent of the scroll feature and can be undone on its own at any time.

WHAT IT DOES
------------
While a hero CARRIES an `itScroll` item (item type 5), that item's spell (`item+0x38`) appears in
THAT hero's spellbook and is castable, even though the player never researched it.  The scroll is
never consumed and the spell never becomes globally known -- drop the scroll, lose the spell.

Design decisions baked in (chosen by the user 2026-07-30):
  * The M2 tier gate is RETAINED FOR SCROLLS -- a scroll spell is only offered if
    `spell.tier (TSpell+0x21) <= hero's Spellcasting level`.  A scroll for a tier-4 spell is inert
    in the hands of a low-skill hero.
    ⚠ Since 2026-09-03 a RESEARCHED tier-4 spell is NOT inert for that same hero (the ruling
    above exempted heroes from the tier gate).  Scrolls are therefore deliberately stricter than
    research.  This asymmetry is SANCTIONED -- it is the 2026-07-30 ruling left standing on
    purpose, not an oversight.  Do not "harmonise" the two without asking the user.
  * ONLY Spellcasting heroes benefit -- an explicit `level != 0` test.  (Heroes without the
    Spellcasting ability have `GetCastingPointsMax` == 0 (@0x55788614 returns 0 when the ability
    query at vtable+0x148 fails), so they could not cast anyway; the test makes it explicit rather
    than relying on tier >= 1, because `TSpell+0x21 == 0` legitimately means "not researchable".)
  * AI heroes are NOT covered -- see "NOT DONE" below.

WHY IT WORKS
------------
Research gating lives ENTIRELY in the book.  Neither `THero.CanCastSpell@0x55789710` nor
`THero.CanCastCombatSpell@0x55789a3c` nor the cast token ever consults the researched list; they
check not-already-casting, mana / channelling points, and the spell's own CanActivate.  So a spell
merely has to APPEAR in the list and the stock machinery casts it.  Full analysis:
`Modding Resources/Investigation_Items.md` Feature 1b.

HOW IT HOOKS
------------
`TSpellBook` (AoWz.exe) fills every tab by calling `TPlayerMagicControl.ListSpells` directly at five
sites; the exe never calls `THero.ListSpells`, so a DLL-side list hook is inert (lesson paid for in
`Unit_Spellcasting_Polish_2026-07-06.md` §M3).  Those five sites are already redirected to
`cave_bookfilter@0x0060C0A8` by `build_spellcast_book_exe.py`.

** This patch REWRITES cave_bookfilter IN PLACE (0x82 -> ~0x120 bytes), extending it rather than
chaining a second cave. **  The five call sites are NOT touched -- they already point here.  Doing it
this way is deliberate:
  * `.sc` has only 0xD6 free bytes after the old cave, but 0x158 counting the cave itself -- a
    separate wrapper cave did not fit, and borrowing another feature's section slack (`.tres` has
    0x120 spare) is exactly the crowded-pocket trap CLAUDE.md warns about.
  * The category mask arrives in CL and is consumed by the inner `ListSpells` call, so an append
    stage needs to be inside the same prologue that captures it.
Per CLAUDE.md this is the endorsed pattern (verify-before-write against EITHER the currently
installed bytes OR the new ones, assert the grown-into zone is still zero, fresh feature-named
backup) -- precedent: `build_invis_penalty.py` rewriting `build_trueseeing.py`'s caves.

**  WARNING: re-running `build_spellcast_book_exe.py --apply` will overwrite this cave with its own
shorter version and silently remove BOTH the scroll behaviour AND the hero-tier exemption (its
verify step accepts the original bytes... which we no longer have, so it will simply report a
mismatch and abort -- but do not force it).  Its MISMATCH on a plain dry run is EXPECTED and is not
a broken state; it is that script observing this rewrite.  If you need to re-tune the tier/Cosmos
filter, edit THIS script's `_loop` stage instead.  **

The rewritten cave keeps the existing tier/Cosmos prune byte-for-byte in behaviour, then appends.
All three book tabs (`TSpellBook+0x222`: 0=Combat, 1=Unit, 2=Global) share those five sites, so one
cave covers strategic AND tactical casting.  The captured CL mask is re-applied to appended spells
(`TSpell+0x22` category) so a combat spell does not leak onto the Global tab.

All three book tabs (`TSpellBook+0x222`: 0=Combat, 1=Unit, 2=Global) share those five sites, so one
cave covers strategic AND tactical casting.  The saved CL mask is re-applied to appended spells
(`TSpell+0x22` category) so a combat spell does not leak onto the Global tab.

Engine primitives are reached with NO new imports:
  * `TSpellControl.GetSpell` and `System.@IsClass` are already imported (thunks 0x4025A4/0x401070).
  * `TSpellList.Add` is NOT imported -> reached via the runtime rebase delta
        dll_delta = [0x0045DF78] - 0x558FA044          # [IAT slot for AoWE.AoWHSSet] - its pref VA
    then `call 0x5577A03C + dll_delta`.  (Trick from `Party_Random_Generator.md`.)  Using the real
    Add avoids the TList capacity edge case a manual append would have.

ALSO PATCHED -- kill the vanilla consume-on-use path
----------------------------------------------------
Stock `itScroll` behaviour is a one-shot TOME: Use -> `ExecuteSpellResearched` (spell becomes
globally researched) -> item destroyed.  That is the opposite of "permanent", so both type-5 gates
are retargeted to item type 7, which no item uses:
  * AoWz.exe / AoWzCompat.exe @0x0040A657  -- `cmp byte [edi+0x34],5` -> 7   (Use button never shows)
  * AoWEPACK.dpl @0x557940D1 (TItem.CanUse)    -- imm 5 -> 7               (refuses, MP-safe)
  * AoWEPACK.dpl @0x55793FA9 (TItem.ExecuteUse) -- imm 5 -> 7              (defence in depth)

PREREQUISITES (data -- NOT done by this script)
-----------------------------------------------
  1. At least one type-5 item must exist.  Author it in AoWDevEd:
     Main menu -> Open Item Library (`TMainForm.OpenItemLibraryClick@0x0042B034`) -> New Item ->
     set Type = "Scroll" -> the "Scroll spell:" dropdown appears -> pick the spell.
  2. Scroll icons: `Release/ITEMGFX.PFS` records 316-319 are typed 6 (itUse), so
     `FindItemTypeGFX(5)` returns -1 and a new scroll has no picture.  Fixed by
     `build_scroll_gfx.py` in this folder.

NOT DONE
--------
  * AI heroes.  Two independent gaps: (a) `build_ai_itempickup.py` only fills equip slots 0-5 via
    `CanPlaceItem`, which rejects scrolls (no equip slot) -- it would need `THero.AutoPlaceItem`;
    (b) the AI's candidates come from `TCastSpellAIPA.PrefetchCastSpellActions@0x5577ba54`, which
    calls `ListSpells` inside the DLL and never runs this cave.  (b) is easy to add later: that
    function receives the hero, so the same scan can append with the in-module
    `TSpellList.Add@0x5577a03c`.
  * `ItemUsePnl` visibility defect (AoWz.exe DFM @0x1F3EBD) -- untouched; irrelevant now that the
    Use button is disabled anyway.

Targets `Ziggurat/AoWz.exe` + `AoWzCompat.exe` (names from `zigexe.py`) and `AoWEPACK.dpl`.
⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)
Idempotent, verify-before-write, snapshot to `backups/<file>.pre-scrollbook` taken ONLY from a
file whose every site still holds its untouched pre-feature bytes.
(This docstring is not a raw string -- keep paths in it forward-slashed.)
Dry-run by default; `--apply` to write, `--undo` to remove surgically (restores the five sites to
cave_bookfilter, zeroes only this cave, restores the three imm bytes -- touches no backup).
"""
import os, sys, shutil, struct
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                   # mod binary names (AoWz.exe / AoWzCompat.exe)

EXES = list(zigexe.EXES)
DLL  = "AoWEPACK.dpl"
SUFFIX = ".pre-scrollbook"
BACKUP_DIR = os.path.join(GAME, "backups")      # ⚠ backups/, never the game root -- rule 2026-09-03

IB = 0x00400000
# --- exe: the five TSpellBook -> ListSpells sites already point at CAVE_VA; we do not touch them ---
SITES      = [0x0042F0F9, 0x0042F20C, 0x00430D58, 0x00430DDE, 0x00430EDD]
CAVE_VA    = 0x0060C0A8          # cave_bookfilter -- rewritten in place, extended
SC_BASE    = 0x0060C000
SC_LIMIT   = 0x0060C200          # .sc raw is 0x200 from 0x0060C000; .clog follows immediately
LISTSPELLS = 0x00402654          # TPlayerMagicControl.ListSpells import thunk

# --- exe primitives (all pre-existing) ---
ISCLASS        = 0x00401070      # System.@IsClass(eax=obj, edx=class) -> al
GETSPELL       = 0x004025A4      # TSpellControl.GetSpell(eax=control, edx=id) -> eax
THERO_CLASSREF = 0x0045DFC4      # [.] = THero class ref (covers THero AND TLeader)
HSSET_SLOT     = 0x0045DF78      # IAT slot: value = runtime addr of AoWE.AoWHSSet
HSSET_PREF     = 0x558FA044      # AoWE.AoWHSSet preferred VA in AoWEPACK.dpl (verified export)
SPELLLIST_ADD  = 0x5577A03C      # AoWE.TSpellList.Add(eax=list, edx=spell)   -- not imported
TITEM_VMT      = 0x5570FAFC      # AoWE..TItem class ref (= its VMT). The exe imports NO TItem class
                                 # reference, so this is reached through the same rebase delta as
                                 # TSpellList.Add and compared against each entry's [obj] VMT slot.
GETLEVEL_SLOT  = 0x144           # unit vtable +0x144 = GetAbilityLevel(edx=id) -> al
INVCOUNT_SLOT  = 0x54            # THeroInventory vtable +0x54 = GetCount -> eax
SPELLCASTING   = 0x34
HERO_INV_OFF   = 0x74            # THero+0x74 = THeroInventory (equipped aggregate is +0x70)
ITEM_TYPE_OFF  = 0x34
ITEM_SPELL_OFF = 0x38
SCROLL_TYPE    = 5               # itScroll
DEAD_TYPE      = 7               # a TItemTypes value no item uses -> disables the Use path

# --- consume-on-use kill sites: (file-offset-of-imm resolved at runtime, old, new) ---
EXE_UI_GATE_VA = 0x0040A657      # cmp byte [edi+0x34], 5   -> imm at +3
DLL_CANUSE_OFF   = 0x0934D1      # cmp byte [esi+0x34], 5   -> imm at +3   (VA 0x557940D1)
DLL_EXECUSE_OFF  = 0x0933A9      # mov al,[ebx+0x34]; sub al,5 -> imm at +4 (VA 0x55793FA9)

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

# ---- BISECT CONTROLS (added 2026-07-31 after the full patch broke the spell book) ----------------
# `--append-upto N` truncates the scroll-append stage with a `jmp _done` after step N:
#   0  nothing (== the old --stage1only): prune only.      RESULT 2026-07-31: spell book WORKS.
#   1  + heroFamily/level guards + `mov esi,[caster+0x74]` + null test
#   2  + the virtual GetCount call and its count test
#   3  + the inventory WALK ONLY: loads items[i] each iteration, never dereferences the item
#   4  + the item null test and the `byte [item+0x34] == 5` test, but NEVER reaches GetSpell/Add
#   5  full (default): GetSpell + tier/category filter + dedupe + TSpellList.Add
# RESULTS (in-game, user, 2026-07-31): N=0 WORKS.  N=2 WORKS.  N=3 WORKS.  full BREAKS
# (spells + icons gone, error dialog, freeze).  So the caster pointer, its `+0x74` inventory, the
# virtual GetCount and the array walk are ALL fine -- the fault is in what N=4/5 add.  N=4 splits
# the last two candidates:
#   (A) `[item+0x34]` itself faults  -> some slot holds a stale/wild pointer.  N=4 still breaks.
#   (B) the deref is safe but returns 5 for some slot, so GetSpell runs with a garbage id and a
#       bogus TSpell* is appended to the book -> icons fail to draw, then hang.  N=4 works.
# N=4 WORKS -> (B) CONFIRMED.  The deref is safe; some slot legitimately reads 5 at +0x34, so
# `GetSpell` ran with a garbage id and a bogus TSpell* was appended to the book -- the icon draw then
# choked on it.  Root cause: **the inventory array can hold entries that are not live TItems** (these
# engine lists are sparse: removal is sparse-or-compacting by style bit 8, so FCount can exceed the
# live entries and a dead slot need not be NULL), and a type-byte test alone cannot tell them apart.
# FIX (2026-07-31): before touching +0x34, require the entry's VMT to BE TItem's --
#   `cmp [entry], (0x5570FAFC + dll_delta)` -- reached via the same rebase delta as TSpellList.Add.
# Paid for by dropping the dedupe pass (.sc is exhausted at 344/344); the only cost is that a scroll
# whose spell the player has ALSO researched now appears twice in the book. Restore it when the cave
# gets its own PE section.
STAGE1_ONLY = '--stage1only' in sys.argv
APPEND_UPTO = 0 if STAGE1_ONLY else 5      # 5 == full. (Was left at 4 when the ladder gained a
                                           # level, so a bare --apply silently installed a bisect
                                           # build instead of the real feature. Keep in sync.)
for _a in sys.argv:
    if _a.startswith('--append-upto'):
        APPEND_UPTO = int(_a.split('=', 1)[1] if '=' in _a else sys.argv[sys.argv.index(_a) + 1])


def _cut(step):
    """Emit `jmp _done` at exactly the one boundary where the bisect level stops.

    Only the FIRST applicable cut is emitted -- later ones would be unreachable and each costs 5
    bytes, which at level 0 overflowed the 344-byte span."""
    return '    jmp  _done' if APPEND_UPTO == step - 1 else ''

# ---------------------------------------------------------------------------------------------
# OLD cave_bookfilter, verbatim from build_spellcast_book_exe.py -- assembled only so we can
# recognise (and, on --undo, restore) the pre-existing installed bytes.
# ---------------------------------------------------------------------------------------------
old_cave_src = f"""
    push ebp
    mov ebp, esp
    sub esp, 0x0C
    push ebx
    push esi
    push edi
    mov [ebp-4], edx
    call 0x{LISTSPELLS:X}
    mov edx, [ebp-4]
    mov eax, [edx+8]
    test eax, eax
    jz _done
    mov edx, dword ptr [0x{THERO_CLASSREF:X}]
    call 0x{ISCLASS:X}
    movzx eax, al
    mov [ebp-8], eax
    mov eax, [ebp-4]
    mov eax, [eax+8]
    mov ecx, [eax]
    mov edx, 0x{SPELLCASTING:X}
    call dword ptr [ecx+0x{GETLEVEL_SLOT:X}]
    movzx eax, al
    mov [ebp-0xC], eax
    mov edx, [ebp-4]
    mov esi, [edx]
    mov esi, [esi+4]
    mov ebx, [esi+4]
    xor eax, eax
    xor edx, edx
_loop:
    cmp eax, [esi+8]
    jge _wb
    mov ecx, [ebx+eax*4]
    movzx edi, byte ptr [ecx+0x21]
    cmp edi, [ebp-0xC]
    jg _skip
    cmp dword ptr [ebp-8], 0
    jne _keep
    cmp byte ptr [ecx+0x20], 0
    je _skip
_keep:
    mov [ebx+edx*4], ecx
    inc edx
_skip:
    inc eax
    jmp _loop
_wb:
    mov [esi+8], edx
_done:
    pop edi
    pop esi
    pop ebx
    mov esp, ebp
    pop ebp
    ret
"""
old_cave = bytes(ks.asm(old_cave_src, CAVE_VA)[0])

# ---------------------------------------------------------------------------------------------
# NEW cave -- same entry contract (EAX = TPlayerMagicControl, EDX = &collector = TSpellBook+0x224,
# CL = category mask; caster at [&collector+8]).  Stage 1 prunes the listed spells; stage 2 appends
# spells granted by carried scrolls.
#   Locals: [ebp-4]=&collector [ebp-8]=mask [ebp-0xC]=level [ebp-0x10]=heroFamily
#           [ebp-0x14]=caster  [ebp-0x18]=inventory count
#
# ⚠ STAGE 1 ALSO CARRIES ANOTHER FEATURE'S RULE (2026-09-03).  The `_loop` prune below now tests
# heroFamily FIRST and `jne _keep`, so BOTH the tier prune and the Cosmos prune are unit-only:
#
#     hero / leader  -> keep every listed spell (no tier test, no Cosmos test)
#     unit           -> drop tier > level, then drop Cosmos (sphere 0)
#
# Before 2026-09-03 the tier prune ran ahead of the heroFamily test and therefore applied to
# heroes too.  User ruling 2026-09-03: "Spellcasting level should only restrict tier of spell
# that's castable for units, not heroes."  This is the BOOK half of that ruling; the cast-gate
# half is `build_spellcast_herotier.py` (AoWEPACK.dpl).  The change is a pure REORDER -- 36 bytes
# before and 36 after -- which is the only reason it fits a cave whose section has 0 spare bytes.
# Do not reorder it back, and do not let the two halves drift apart: with only one applied the
# feature silently does nothing (book half missing -> hero cannot SEE the spell; cast half missing
# -> hero sees it and clicking does nothing, with no message).
#
# ⚠ SANCTIONED INCONSISTENCY -- DO NOT "HARMONISE" IT.  Stage 2 below keeps its own
# `tier > level -> _next` filter, so a hero casts any RESEARCHED spell regardless of tier but
# still cannot cast a too-high-tier SCROLL spell.  That is the user's 2026-07-30 ruling on
# scrolls, deliberately left standing on 2026-09-03.  It is not a bug and not an oversight.
# ---------------------------------------------------------------------------------------------
new_cave_src = f"""
    push ebp
    mov  ebp, esp
    sub  esp, 0x18
    push ebx
    push esi
    push edi
    mov  [ebp-4], edx
    movzx ecx, cl
    mov  [ebp-8], ecx
    call 0x{LISTSPELLS:X}
    mov  edx, [ebp-4]
    mov  eax, [edx+8]
    test eax, eax
    jz   _done
    mov  [ebp-0x14], eax
    mov  edx, dword ptr [0x{THERO_CLASSREF:X}]
    call 0x{ISCLASS:X}
    movzx eax, al
    mov  [ebp-0x10], eax
    mov  eax, [ebp-0x14]
    mov  ecx, [eax]
    mov  edx, 0x{SPELLCASTING:X}
    call dword ptr [ecx+0x{GETLEVEL_SLOT:X}]
    movzx eax, al
    mov  [ebp-0xC], eax
    mov  edx, [ebp-4]
    mov  esi, [edx]
    mov  esi, [esi+4]
    mov  ebx, [esi+4]
    xor  eax, eax
    xor  edx, edx
_loop:
    cmp  eax, [esi+8]
    jge  _wb
    mov  ecx, [ebx+eax*4]
    cmp  dword ptr [ebp-0x10], 0
    jne  _keep
    movzx edi, byte ptr [ecx+0x21]
    cmp  edi, [ebp-0xC]
    jg   _skip
    cmp  byte ptr [ecx+0x20], 0
    je   _skip
_keep:
    mov  [ebx+edx*4], ecx
    inc  edx
_skip:
    inc  eax
    jmp  _loop
_wb:
    mov  [esi+8], edx
{_cut(1)}
    cmp  dword ptr [ebp-0x10], 0
    je   _done
    cmp  dword ptr [ebp-0xC], 0
    je   _done
    mov  eax, [ebp-0x14]
    mov  esi, [eax+0x{HERO_INV_OFF:X}]
    test esi, esi
    jz   _done
{_cut(2)}
    mov  eax, esi
    mov  ecx, [eax]
    call dword ptr [ecx+0x{INVCOUNT_SLOT:X}]
    mov  [ebp-0x18], eax
    test eax, eax
    jle  _done
{_cut(3)}
    mov  esi, [esi+8]
    mov  esi, [esi+4]
    xor  ebx, ebx
_iloop:
    cmp  ebx, [ebp-0x18]
    jge  _done
    mov  edi, [esi+ebx*4]
{'    jmp  _next' if APPEND_UPTO == 3 else ''}
    test edi, edi
    jz   _next
    mov  eax, dword ptr [0x{HSSET_SLOT:X}]
    sub  eax, 0x{HSSET_PREF:X}
    add  eax, 0x{TITEM_VMT:X}
    cmp  [edi], eax
    jne  _next
    cmp  byte ptr [edi+0x{ITEM_TYPE_OFF:X}], {SCROLL_TYPE}
    jne  _next
{'    jmp  _next' if APPEND_UPTO == 4 else ''}
    mov  edx, [edi+0x{ITEM_SPELL_OFF:X}]
    test edx, edx
    jz   _next
    mov  eax, dword ptr [0x{HSSET_SLOT:X}]
    mov  eax, [eax]
    mov  eax, [eax+0x84]
    call 0x{GETSPELL:X}
    test eax, eax
    jz   _next
    mov  edi, eax
    movzx eax, byte ptr [edi+0x21]
    cmp  eax, [ebp-0xC]
    jg   _next
    movzx eax, byte ptr [edi+0x22]
    cmp  al, 8
    jae  _next
    mov  ecx, [ebp-8]
    bt   ecx, eax
    jnc  _next
    mov  eax, dword ptr [0x{HSSET_SLOT:X}]
    sub  eax, 0x{HSSET_PREF:X}
    add  eax, 0x{SPELLLIST_ADD:X}
    mov  ecx, eax
    mov  eax, [ebp-4]
    mov  eax, [eax]
    mov  edx, edi
    call ecx
_next:
    inc  ebx
    jmp  _iloop
_done:
    pop  edi
    pop  esi
    pop  ebx
    mov  esp, ebp
    pop  ebp
    ret
"""
cave = bytes(ks.asm(new_cave_src, CAVE_VA)[0])
# Pad every variant to one fixed span so the region we own -- and therefore what `--undo` restores --
# is the same size whether or not `--stage1only` was used. Without this, applying with the flag and
# undoing without it (or vice versa) aborts on a length mismatch, which is safe but baffling.
CAVE_SPAN = SC_LIMIT - CAVE_VA          # 0x158 = 344: the whole rest of .sc, so every bisect
                                        # variant (each `jmp _done` costs 5 more bytes) fits one span
assert len(cave) <= CAVE_SPAN, f"cave {len(cave)} B exceeds span {CAVE_SPAN}"
cave = cave + b"\x00" * (CAVE_SPAN - len(cave))


def load_secs(d):
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e + 6)[0]
    optsz = struct.unpack_from('<H', d, e + 20)[0]
    sect = e + 24 + optsz
    secs = []
    for i in range(nsec):
        b = sect + i * 40
        nm = d[b:b + 8].rstrip(b'\0').decode('latin1')
        vs, va, rs, raw = struct.unpack_from('<IIII', d, b + 8)
        secs.append((nm, va, vs, raw, rs, b))
    return secs


def va2off(secs, va, base=IB):
    r = va - base
    for nm, v, vs, raw, rs, b in secs:
        if v <= r < v + max(vs, rs):
            return raw + (r - v)
    raise ValueError(hex(va))


def rel(site, dest):
    return struct.pack('<i', dest - (site + 5))


DLL_IB         = 0x55700000
DLL_CANUSE_VA  = 0x557940D1      # cmp byte [esi+0x34], 5   -- must map to DLL_CANUSE_OFF
DLL_EXECUSE_VA = 0x55793FA9      # mov al,[ebx+0x34]; sub al,5 -- must map to DLL_EXECUSE_OFF


def reloc_hits(d, base, ranges):
    """Every .reloc entry whose target VA lands inside one of `ranges` = [(lo, hi, name)].

    Overwriting a byte-run that carries a relocation corrupts the image at load, and the failure
    is at startup, not at patch time -- so every displaced range gets scanned before any write.
    A module with no relocation directory (both exes are fixed-base) yields no hits."""
    secs = load_secs(d)
    e = struct.unpack_from('<I', d, 0x3C)[0]
    magic = struct.unpack_from('<H', d, e + 24)[0]
    dd = e + 24 + (96 if magic == 0x10B else 112)
    rva, size = struct.unpack_from('<II', d, dd + 5 * 8)
    if not rva or not size:
        return []
    off = va2off(secs, base + rva, base)
    end, hits = off + size, []
    while off < end:
        pg, blk = struct.unpack_from('<II', d, off)
        if blk == 0:
            break
        for i in range((blk - 8) // 2):
            w = struct.unpack_from('<H', d, off + 8 + i * 2)[0]
            if w >> 12:
                va = base + pg + (w & 0xFFF)
                for lo, hi, nm in ranges:
                    if lo <= va < hi:
                        hits.append((nm, va))
        off += blk
    return hits


def check_relocs(name, d, base, ranges):
    hits = reloc_hits(d, base, ranges)
    if hits:
        print(f"{name}: ABORT -- .reloc entries inside a range we overwrite: "
              + ", ".join(f"{nm}@{va:08X}" for nm, va in hits))
        return False
    return True


# the cave region we own: old bytes padded with the zeros that must still be there
OLD_REGION = old_cave + b"\x00" * (len(cave) - len(old_cave))

# Every variant of OUR cave starts `push ebp; mov ebp,esp; sub esp,0x18`; the original
# cave_bookfilter uses `sub esp,0x0C`. That 3-byte signature lets the verify recognise a
# previously-installed bisect variant as ours and overwrite it, instead of aborting on
# "neither the pristine bytes nor the new ones" every time the bisect level changes.
OURS_SIG = b"\x55\x89\xe5\x83\xec\x18"


def is_ours(region):
    return bytes(region[:len(OURS_SIG)]) == OURS_SIG


def patches_for_exe(d):
    """[(file_offset, unpatched_bytes, patched_bytes, desc)]."""
    secs = load_secs(d)
    out = [(va2off(secs, CAVE_VA), OLD_REGION, cave,
            f"cave @{CAVE_VA:08X} ({len(old_cave)}->{len(cave)} B)"),
           (va2off(secs, EXE_UI_GATE_VA) + 3, bytes([SCROLL_TYPE]), bytes([DEAD_TYPE]),
            f"Use-button gate @{EXE_UI_GATE_VA:08X}")]
    return out, secs


def patches_for_dll():
    return [(DLL_CANUSE_OFF + 3, bytes([SCROLL_TYPE]), bytes([DEAD_TYPE]), "TItem.CanUse gate"),
            (DLL_EXECUSE_OFF + 4, bytes([SCROLL_TYPE]), bytes([DEAD_TYPE]), "TItem.ExecuteUse gate")]


def apply_file(name, patches, undo, extra_check=None):
    path = os.path.join(GAME, name)
    if not os.path.exists(path):
        print(f"{name}: MISSING -- skipped"); return False
    d = bytearray(open(path, 'rb').read())
    if extra_check and not extra_check(d):
        return False
    want_new = not undo
    already = todo = virgin = 0
    ok = True
    for off, old, new, desc in patches:
        cur = bytes(d[off:off + len(old)])
        target, other = (new, old) if want_new else (old, new)
        if cur == old:
            virgin += 1                     # still the untouched pre-feature bytes
        if cur == target:
            already += 1
        elif cur == other:
            todo += 1
        elif len(old) > len(OURS_SIG) and is_ours(cur):
            todo += 1                       # a different bisect variant of ours -- safe to replace
        else:
            print(f"{name}: MISMATCH {desc} @{off:#x}: have {cur[:32].hex(' ')}..., "
                  f"expected {old[:32].hex(' ')}... or {new[:32].hex(' ')}...")
            ok = False
    verb = "undo" if undo else "apply"
    print(f"{name}: {already} already {verb}-state, {todo} to change, {len(patches)} total")
    if not ok:
        print(f"{name}: ABORT -- refusing to write over unexpected bytes."); return False
    if '--apply' not in sys.argv:
        return True
    if todo == 0:
        print(f"  {name}: nothing to do."); return True
    # ⚠ Snapshot ONLY from a file PROVED unpatched -- every site still on its untouched pre-feature
    # bytes. Never on --undo (the file IS the patched state by definition), and never merely because
    # no backup file exists: that gate accepts our own past output, and after the 2026-09-09 rename
    # no AoWz.exe.pre-scrollbook can exist, so it would have minted one holding the PATCHED state.
    # Note `is_ours(cur)` counts toward `todo` but NOT toward `virgin` -- an earlier variant of our
    # own cave is not a pre-feature state.
    if undo or virgin != len(patches):
        if not undo:
            print(f"  no backup taken ({len(patches) - virgin} of {len(patches)} site(s) already "
                  f"carry a version of this feature -- a .pre-* of a patched file is a lie)")
    else:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        backup = os.path.join(BACKUP_DIR, os.path.basename(path) + SUFFIX)
        if not os.path.exists(backup):
            shutil.copy2(path, backup); print(f"  backup -> {backup}")
    for off, old, new, desc in patches:
        d[off:off + len(old)] = new if want_new else old
    open(path, 'wb').write(bytes(d))
    print(f"  {name}: {'undone' if undo else 'applied'}.")
    return True


def check_prereqs(d):
    """Abort unless build_spellcast_book_exe.py is applied (the five sites must already call our
    cave address) and the cave still fits inside .sc."""
    secs = load_secs(d)
    if CAVE_VA + len(cave) > SC_LIMIT:
        print(f"  ABORT -- cave overflows .sc ({CAVE_VA + len(cave):#x} > {SC_LIMIT:#x}); "
              "shrink it or add a section."); return False
    bad = [s for s in SITES
           if bytes(d[va2off(secs, s):va2off(secs, s) + 5]) != b"\xE8" + rel(s, CAVE_VA)]
    if bad:
        print(f"  ABORT -- {len(bad)} of {len(SITES)} ListSpells sites do not call {CAVE_VA:08X} "
              f"({', '.join('%08X' % s for s in bad)}). Run build_spellcast_card_v2.py then "
              "build_spellcast_book_exe.py --apply first.")
        return False
    return True


def main():
    undo = '--undo' in sys.argv
    grow = len(cave) - len(old_cave)
    print(f"cave_bookfilter @{CAVE_VA:08X} rewritten in place: {len(old_cave)} -> {len(cave)} B "
          f"(+{grow}), ends {CAVE_VA + len(cave):08X}; .sc limit {SC_LIMIT:08X}, "
          f"{SC_LIMIT - CAVE_VA - len(cave)} spare")
    if '--dis' in sys.argv:
        for ins in cs.disasm(cave, CAVE_VA):
            print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<20} {ins.mnemonic} {ins.op_str}")
    print()
    allok = True
    for exe in EXES:
        path = os.path.join(GAME, exe)
        if not os.path.exists(path):
            print(f"{exe}: MISSING -- skipped"); continue
        d = bytearray(open(path, 'rb').read())
        secs = load_secs(d)
        # the zone the cave grows into must still be zero (or already be our cave)
        coff = va2off(secs, CAVE_VA)
        goff = coff + len(old_cave)
        tail = bytes(d[goff:goff + grow])
        if (tail != b"\x00" * grow and tail != cave[len(old_cave):]
                and not is_ours(d[coff:coff + len(OURS_SIG)])):
            print(f"{exe}: ABORT -- grow zone {CAVE_VA + len(old_cave):08X}.."
                  f"{CAVE_VA + len(cave):08X} is neither zero nor ours: {tail[:16].hex(' ')}")
            allok = False; continue
        if not check_relocs(exe, d, IB,
                            [(CAVE_VA, CAVE_VA + len(cave), "cave_bookfilter"),
                             (EXE_UI_GATE_VA + 3, EXE_UI_GATE_VA + 4, "Use-button gate imm")]):
            allok = False; continue
        p, _ = patches_for_exe(d)
        allok &= apply_file(exe, p, undo, check_prereqs)
        # .sc VirtualSize must cover the cave; on --undo shrink it back so the file returns to
        # exactly its pre-patch bytes (harmless if left grown -- same 0x1000 page -- but a stray
        # byte makes a backup diff look like a failed revert).
        if '--apply' in sys.argv and allok:
            need = (CAVE_VA - SC_BASE) + len(old_cave if undo else cave)
            d = bytearray(open(path, 'rb').read())
            for nm, va, vs, raw, rs, b in load_secs(d):
                if nm == '.sc' and vs != need:
                    struct.pack_into('<I', d, b + 8, need)
                    open(path, 'wb').write(bytes(d))
                    print(f"  .sc VirtualSize {vs:#x} -> {need:#x}")
    dllpath = os.path.join(GAME, DLL)
    if os.path.exists(dllpath):
        dd = bytearray(open(dllpath, 'rb').read())
        dsecs = load_secs(dd)
        # Resolve the two imm bytes through the PE section table -- VA->offset in AoWEPACK.dpl is
        # PER SECTION, so never trust a flat delta. This also pins the addresses: a shifted CODE
        # section would abort here instead of writing a 5 into the wrong instruction.
        for va, off, nm in ((DLL_CANUSE_VA, DLL_CANUSE_OFF, "TItem.CanUse"),
                            (DLL_EXECUSE_VA, DLL_EXECUSE_OFF, "TItem.ExecuteUse")):
            if va2off(dsecs, va, DLL_IB) != off:
                print(f"{DLL}: ABORT -- {nm} VA {va:08X} maps to file "
                      f"{va2off(dsecs, va, DLL_IB):#x}, not {off:#x}."); return 1
        if not check_relocs(DLL, dd, DLL_IB,
                            [(DLL_CANUSE_VA + 3, DLL_CANUSE_VA + 4, "TItem.CanUse imm"),
                             (DLL_EXECUSE_VA + 4, DLL_EXECUSE_VA + 5, "TItem.ExecuteUse imm")]):
            return 1
    allok &= apply_file(DLL, patches_for_dll(), undo)
    print()
    if '--apply' not in sys.argv:
        print("DRY RUN -- nothing written. Re-run with --apply (close every AoW binary first: "
              "AoWz.exe, AoWzCompat.exe, AoWzEd.exe, AoWDevEd.exe all lock these files).")
    elif allok and not undo:
        print("Applied. Still needed before this can be tested:\n"
              "  1. Author a Scroll item in AoWDevEd (Open Item Library -> New Item -> Type=Scroll)\n"
              "  2. python build_scripts/build_scroll_gfx.py --apply   (gives scrolls an icon)")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
