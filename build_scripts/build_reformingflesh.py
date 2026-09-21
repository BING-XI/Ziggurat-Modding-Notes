# -*- coding: utf-8 -*-
r"""
build_reformingflesh.py — new passive ability: Reforming Flesh (id 0xB1).

    python build_scripts/build_reformingflesh.py            dry run + verify + disassembly
    python build_scripts/build_reformingflesh.py --apply     write it
    python build_scripts/build_reformingflesh.py --undo      restore hook + reg site, zero caves
    python build_scripts/build_reformingflesh.py --dis       disassemble the installed caves

EFFECT
    A unit with Reforming Flesh heals +5 HP at the start of EVERY combat round, round 1
    included, clamped at its maximum HP. Works for units and heroes, in manual tactical
    combat and in auto-resolve alike.

    HEAL is a single named constant below — a re-tune is one line. The 5 is already on the
    post-doubling Ziggurat scale (every HP pool and damage source is x2); do NOT "convert" it.

TARGET: AoWEPACK.dpl ONLY. No other binary is touched.

────────────────────────────────────────────────────────────────────────────────────────────
THE ROUND TICK — one hook covers both combat systems
────────────────────────────────────────────────────────────────────────────────────────────
TCombat.NewRound @0x557273FC (VMT +0x7C) creates and executes TNewCombatRoundCA, whose
Execute @0x5572A398 is the per-round "tell every combat object a round began" loop:

    5572A39C  mov  eax,[esi+0x0C]        ; TCombatData
    5572A39F  inc  dword [eax+0x44]      ; the round counter, bumped BEFORE the loop
    5572A3A5  call TCombatData.GetCount @0x55728BEC
    5572A3AA  mov  ebx,eax / dec ebx     ; EBX = index, counts DOWN
    5572A3B2  mov  edx,ebx               ; <- loop top
    5572A3B7  call TCombatData.GetObjects @0x55728BF8    ; EAX = combat object
    5572A3BC  mov  edx,[eax]             ; \ HOOKED, 8 bytes
    5572A3BE  call dword ptr [edx+0xF4]  ; / = obj.NewRound()
    5572A3C4  dec  ebx / cmp ebx,-1 / jne 0x5572A3B2

Hooking the *dispatch* rather than a VMT slot is what buys both systems at once:
    manual   AoWTCPCK!TTacticalCombat.Execute -> call [edx+0x7C] -> thunk -> AoWEPACK!TCombat.NewRound
    auto     TFastCombat.ExecuteCombatRound @0x55744856 -> same inherited +0x7C slot
⚠ Do NOT "simplify" this to repointing TCombatUnit VMT +0xF4: TTacticalCombatUnit's VMT lives
in AoWTCPCK.dpl @0x00412B4C and its +0xF4 is an import thunk, so a DLL-only VMT patch would
work in auto-resolve and do nothing at all in manual combat.

At the hook: EAX = combat object, ESI = the TCombat, EBX = loop index. The cave touches only
EAX/ECX/EDX — all volatile under Delphi's register convention — so EBX/ESI/EDI/EBP survive
without being saved.

⚠ ESI is the **TCombat**, not the CA. Measured 2026-08-31, not assumed, because the round-1 gate
below is arithmetic on it:
    TCombat.ExecuteCombatAction @0x55727224   mov esi,edx (the CA) / mov ebx,eax (the TCombat)
    ...then @0x5572723D                       mov edx,ebx / mov eax,esi / call [ecx+0x50]
i.e. Execute is entered with EAX = the CA (self) and EDX = the TCombat (arg1), and
TNewCombatRoundCA.Execute's own `mov esi,edx` @0x5572A39A parks the TCombat in ESI.
Cross-checked against TCombat.GetRound @0x5572721C = `mov eax,[eax+0x0C] / mov eax,[eax+0x44] /
ret`, so [TCombat+0x0C] = TCombatData and [TCombatData+0x44] = the round counter. The field
arithmetic was always right; only the register's NAME was wrong in this docstring's first draft.

────────────────────────────────────────────────────────────────────────────────────────────
⚠⚠ THE HEAL-THEM-TO-DEATH TRAP — why every arithmetic step below is 32-bit
────────────────────────────────────────────────────────────────────────────────────────────
TUnit.SetHitPoints @0x557827C4 takes the new HP in DL and treats it as a SIGNED BYTE:

    557827C6  mov  ebx,edx
    557827CE  call [edx+0xD0]        ; GetHits = max
    557827D4  cmp  bl,al             ; SIGNED byte compare
    557827D6  jle  0x557827E4        ;   129 -> BL = 0x81 = -127 -> "already below max"
    ...                              ;   so the max-clamp is SKIPPED
    557827E4  test bl,bl
    557827E6  jge  0x557827EA
    557827E8  xor  ebx,ebx           ; *** and the zero-clamp fires: HP := 0 ***

So a unit at 119 HP handed 119+10 does not cap at max — it DIES. That is the recorded vanilla
Regeneration bug (Zig notes/DamHP_Double_Decisions.md); build_newturn_healcap.py exists solely
to fix the same wrap on the per-turn heal, and this cave copies its idiom: do the sum and the
comparison in 32-bit registers, clamp to max BEFORE the call, so SetHitPoints only ever
receives a value already inside [1, max].

⚠ Second half of the same trap: the accessors return a BYTE and leave EAX's top 24 bits dirty.

    TUnit.GetHitPoints @0x557827C0   mov al,[eax+0x3e] / ret      <- writes AL only
    THero.GetHitPoints @0x55787044   mov al,[eax+0x7a] / ret      <- writes AL only
    TUnit.GetHits      @0x55782B68   tail-calls build_medal_hpmv's cave, which does its
                                     arithmetic in AL (`add al,[edx+0x2c]`, `div cl`)

Using EAX directly would import whatever the previous call left in the upper bytes — the
"widening an 8-bit computation to a 32-bit compare promotes previously-truncated dirty bits"
lesson from the DAM/HP doubling. Every read below is `movsx <reg>, al`. `movsx` (not `movzx`)
matches how the engine itself reads the field: SetHitPoints's own `test bl,bl / jge` treats it
as signed, and legitimate values are 0..120 so bit 7 is never set on a healthy unit.

⚠ Do NOT copy the cave shape in Zig notes/HOWTO_Lifesteal_RoundAttack.md — it does a bare
`add eax,2` with no clamp at all, and only survives because +2 rarely crosses 127.

────────────────────────────────────────────────────────────────────────────────────────────
GATING — walls and structures exclude themselves for free
────────────────────────────────────────────────────────────────────────────────────────────
The loop visits every combat OBJECT, not just units. The cave asks each one
GetAbilityEnabled(0xB1) through VMT +0xA8:

    TCombatUnit.GetAbilityEnabled   @0x55725004  -> forwards to [self+0x4c].vmt[0x148]
    TCombatObject.GetAbilityEnabled @0x557268D4  -> xor eax,eax / ret

so walls, structures and every other non-unit answer "no" and are skipped without a type test.
+0x148 is the ITEM-AWARE query (not the self-only +0x84/+0x88 pair), so a Reforming Flesh
*item* would work too — see the "two ability-query APIs" note; picking the wrong pair is a
documented way to ship an ability that does nothing.

⚠ TCombatUnit's own accessors all delegate to `[self+0x4c]` and return 0 when it is nil
(0x5572505E / 0x55725076 / 0x55725016 are each `xor eax,eax; ret`). The corpse check catches
that, and the max<=0 guard backstops it — see the cave comments.

────────────────────────────────────────────────────────────────────────────────────────────
⚠⚠ HERO LEVEL-UP COST — a REGISTRATION-TIME STORE CANNOT WORK. THE .pfs LOAD ZEROES IT.
────────────────────────────────────────────────────────────────────────────────────────────
THE COST IS SET IN cave_cost, HOOKED INTO TAbility.ReadWrite. Nowhere else. If you are here
looking for "where is Reforming Flesh's level-up cost", it is EXPAND_COST below, and it reaches
[ability+0x14] through that hook — NOT through cave_reg, which no longer stores it at all.

TAbility.FExpandCost lives at [ability+0x14], is a 32-bit Integer, and is returned verbatim by
TAbility.ExpandCost @0x5574E908 (`mov eax,[eax+0x14]; ret`) — which TEnhancementAbility does NOT
override (VMT 0x5571DABC +0xC8 == 0x5574E908, checked). So the field IS what the dialog charges.

⚠ CreateEnhancementAbility @0x5576601C never initialises it; the whole of what it writes is the
id at [ebx+0x0C], the name at [ebx+8] and the selection mask at [ebx+0x20]. v1 of this script
therefore shipped free, and v2 added `mov dword [eax+0x14], 50` to cave_reg to fix it. **v2 did
not work, and could not have.** Owner-reported 2026-09-10 ("still costs 0"), root-caused the
same day:

    RegisterPassiveAbilities runs at package init and builds the ability list.
    LATER, Release/Ability.pfs is loaded:
      TAbilityControl.ReadWrite @0x55750164   for EVERY non-nil list index i,
                                              stream.rwEObject(ability, tag = i + 10)
      TEReadStorageStream.rwEObject @0x555116B0
            FindOffset(tag) == -1  ->  jumps over the sub-stream open...
            ...but STILL calls MainReadWrite -> [VMT+0x18] = TAbility.ReadWrite. Always.
      TAbility.ReadWrite @0x5574F07C   ->  rwInteger(&[ability+0x14], tag 6)
      TEReadStorageStream.rwInteger @0x55510EF4
            55510F08  cmp esi,-1
            55510F0B  je  0x55510F39
            55510F39  xor eax,eax
            55510F3B  mov dword ptr [edi], eax      *** MISSING TAG 6 => FIELD := 0 ***

A missing tag is not "leave the field alone" — it is "write the default", and the default is 0.
So ANY value a registration cave puts in [ability+0x14] is destroyed by the next data load. The
.pfs does not merely win when it has a record; it wins unconditionally, and absent means free.

⚠ THE TWO STREAM PRIMITIVES DISAGREE, WHICH IS WHY THIS LOOKED IMPOSSIBLE:
    tag 9 -> rwData    @0x5551128C   missing tag: `je` straight to the epilogue, BUFFER UNTOUCHED
    tag 6 -> rwInteger @0x55510EF4   missing tag: FIELD EXPLICITLY ZEROED
so cave_reg's selection mask (SEL_TYPES) SURVIVES a missing record while its cost does not. That
is exactly the observed symptom: Reforming Flesh is offered at hero level-up, and is free.
(⚠ It also means the "Ability.pfs tag 9 always overwrites the registered mask" claim elsewhere in
this project is only true when a record EXISTS.)

THE FIX — cave_cost, spliced into TAbility.ReadWrite immediately AFTER the tag-6 rwInteger call:

    5574F0A7  call [edi+0x2c]        ; rwInteger(&FExpandCost, tag 6) -- has just zeroed it
    5574F0AA  mov  ecx, 7            ; <- HOOKED, exactly 5 bytes (B9 07 00 00 00), no padding
    5574F0AF  mov  edx,[ebx+0x18]    ; resume here

EBX is the ability for the whole body (set at 0x5574F081, not clobbered until 0x5574F0E0), so
the cave needs no reload. It touches EFLAGS and nothing else before replaying `mov ecx,7`, so
EAX/ECX/EDX/ESI/EDI all survive untouched. `.reloc` carries no entry in 0x5574F0AA..0x5574F0AE
(the nearest is 0x5574F0BE, inside `push 0x557028D4`), so nothing is displaced that must relocate.
TAbility.ReadWrite is byte-identical to the pristine root DLL — no other feature owns this site.

⚠ FORWARD HAZARD — if Release/Ability.pfs ever grows a record 187 WITH a tag 6, THE FILE WINS and
EXPAND_COST below becomes decorative. cave_cost only fills in a ZERO, deliberately: a non-zero
tag 6 is somebody's explicit choice and is left alone. A tag 6 of 0 cannot occur, because the
writer omits a field whose value equals the default (measured: the editor wrote records 186 and
188 with no tag 6 at all, and 187 with tag 6 only because it was non-zero).

⚠ THE SAME BUG IS LATENT IN EVERY MOD-ADDED ABILITY WITH NO .pfs RECORD — Path of Sand 0x9F and
anything else registered from a cave. Fixing one of those is a second (id, cost) pair in
COST_FIXES below and nothing more; the cave is written as a loop-free chain of compares.

⚠ AND THE EDITOR CAN WRITE TO THE WRONG TREE. The owner's 20 landed in <game root>\Release\
Ability.pfs — the VANILLA data root — because the editor binary he ran resolves its startup
directory from HKCU\...\Triumph Studios\Age of Wonders, not \Age of Wonders Z. Neither
Ziggurat\AoWDevEd.exe nor Ziggurat\AoWzEd.exe carries the regiso patch (checked: no "Age of
Wonders Z" string in either), so both read and write <root>\Release\, while the game reads
Ziggurat\Release\. The edit persisted perfectly — into a file nothing loads.

────────────────────────────────────────────────────────────────────────────────────────────
CAVE PLACEMENT — ⚠ NOT the design spec's 0x55824200
────────────────────────────────────────────────────────────────────────────────────────────
The spec named 0x55824200 on the strength of "an 800,936-byte zero run begins at 0x55824158".
The run is real, but it is the TAIL OF build_waterheal.py's CAVE: that script sets
CAVE = 0x55824000 and asserts `CAVE + LEN4 <= 0x55825200`, i.e. it declares the whole
0x55824000..0x55825200 window as its own growth zone, and it is currently INSTALLED (its cave
body occupies 0x55824000..0x55824158). Dropping a cave at 0x55824200 would sit inside another
feature's reservation and be silently overwritten the day waterheal grows a v5 — the same
mistake build_shield.py caught and documented when its spec named 0x55822A00 inside
build_shipyard_income.py's reservation.

This script therefore allocates from 0x55826000 — page-aligned, above every address claimed by
any build script (highest prior claim: waterheal's 0x55825200), with 793,104 zero bytes ahead
of it. Verified with:  grep -rl "55826" "Modding Resources/build_scripts/"   -> no hits.

cave_cost joins the SAME blob rather than taking a page of its own, so there is still exactly one
cave write and one whole-blob comparison. It is laid LAST, which is what makes an EXPAND_COST
re-tune free: `mov r/m32, imm32` is length-stable, so no address in the zone moves and neither
tail jump changes. The blob grew 171 B -> 208 B; 0x558260AB..0x55827000 was proved zero (3,925 B)
before claiming it, and 0x55827000 is somebody else's.

PIC: the DPL never loads at its preferred base. cave_round and cave_cost use only
register-indirect / register-relative operands and one rel32 `jmp` back, so neither needs an
anchor. cave_reg needs the *address* of the name literal, so it uses the standard
`call $+5 ; pop eax` delta trick. The feature is stateless — no BSS slack needed.
"""
import os, sys, struct, shutil, zlib, subprocess

# The Windows console defaults to cp1252, which cannot encode the U+26A0 warning sign printed by
# the --dis path when an OLDER LAYOUT IS ON DISK. Without this, that warning -- the single most
# load-bearing diagnostic in this script, since a stale tail jump is the silent-unlink failure --
# truncates mid-sentence and the script dies on a UnicodeEncodeError. Same idiom as
# build_shield.py. Degrade unencodable glyphs instead of raising.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

try:
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    sys.exit("needs keystone-engine and capstone:  py -m pip install keystone-engine capstone")

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-reformingflesh")
DLL_BASE = 0x55700000

# ============================================================================== the two knobs
HEAL = 5            # HP restored at the start of every combat round.
                    # Already on the post-doubling Ziggurat scale — do NOT scale it to 10.

EXPAND_COST = 20    # hero level-up point cost -> [ability+0x14], via cave_cost. THE OWNER'S
                    # NUMBER, chosen 2026-09-10 and typed into AoWDevEd; it supersedes the 50
                    # this script shipped with. (50 came from "between 5x Regeneration and 3x
                    # Lifestealing" and never reached the game — see the docstring.) For scale,
                    # measured live from Ziggurat Release/Ability.pfs tag 6: Round Attack 2,
                    # Regeneration 8, Parry 8, Shield 8, Magebane 8, Extra Strike 8,
                    # Drillmaster 10, First Strike 20, Lifestealing 20.
                    # ⚠ A re-tune is this one line + --apply: cave_cost is rewritten in place and
                    # no address in the zone moves. There is no revert-and-re-apply here.
                    # ⚠ Set to None to emit no cave_cost at all — which means FREE, permanently.

# (ability id, cost) pairs cave_cost repairs. One compare chain, no loop, ~14 bytes per extra
# pair. Only a ZERO is filled in, so an Ability.pfs tag 6 always wins. Path of Sand (0x9F) has
# the identical defect and is NOT listed — it is the owner's call, not a build decision.
COST_FIXES = [(0xB1, EXPAND_COST)] if EXPAND_COST is not None else []
# ===========================================================================================

ABILITY_ID   = 0xB1
ABILITY_NAME = b"Reforming Flesh"

# CreateEnhancementAbility's third argument is a TAbilitySelectionType bitmask (it lands in the
# word at [ability+0x20]) — NOT an icon, whatever build_path_sand.py's docstring says. There is
# no art or icon work in this feature; the game has none for abilities.
#   0x001 astUnit         0x002 astHeadItem      0x004 astTorsoItem   0x008 astAttackItem
#   0x010 astDefenseItem  0x020 astRingItem      0x040 astUseItem     0x080 astCustomizeLeader
#   0x100 astHeroUpgrade  0x200 astEditor
# Hero level-up needs BOTH of the top two: the dialog's fill loop tests astHeroUpgrade, and
# TAbility.CanExpand @0x5574E8B8 ANDs the mask with THero.GetAbilitySelectionTypes, which
# returns astEditor. Miss either and the ability registers, works, and is never offered.
SEL_TYPES = 0x03FF

REGISTER_ABIL = 0x55750238      # AoWE.TAbilityControl.RegisterAbility
CREATE_ENH    = 0x5576601C      # AoWE.CreateEnhancementAbility

VMT_GET_HITS     = 0x84         # TCombatUnit.GetHits         @0x5572504C  (max HP)
VMT_GET_HP       = 0x88         # TCombatUnit.GetHitPoints    @0x55725064
VMT_SET_HP       = 0x8C         # TCombatUnit.SetHitPoints    @0x5572507C
VMT_ABIL_ENABLED = 0xA8         # TCombatUnit.GetAbilityEnabled @0x55725004
VMT_NEW_ROUND    = 0xF4         # the displaced dispatch

# --- hook sites ---------------------------------------------------------------------------
# The LAST still-direct `call RegisterAbility` inside PassiveAb.RegisterPassiveAbilities
# @0x557BC1CC (len 0xE00). 84 of the 88 calls there are still direct; the four already
# repointed are 0x557BC9E9 (path_sand), 0x557BCECF (shield), 0x557BCF04 (caster_cost) and
# 0x557BCF39 (drillmaster). assert_reg_site() below re-measures rather than trusting this.
REG_INJ  = 0x557BCE9A
REG_ORIG = b"\xE8" + struct.pack("<i", REGISTER_ABIL - (REG_INJ + 5))

ROUND_INJ  = 0x5572A3BC                                     # mov edx,[eax] ; call [edx+0xF4]
ROUND_ORIG = bytes.fromhex("8b10ff92f4000000")              # 8 bytes, file offset 0x297BC
ROUND_BACK = 0x5572A3C4                                     # the `dec ebx` after the call

# TAbility.ReadWrite @0x5574F07C, the instruction straight after the tag-6 rwInteger call.
# `mov ecx,7` is EXACTLY 5 bytes, so the E9 displaces one whole instruction and needs no NOP
# padding. EBX = the ability here. See the cost section of the docstring.
RW_INJ  = 0x5574F0AA
RW_ORIG = bytes.fromhex("b907000000")                       # mov ecx, 7
RW_BACK = 0x5574F0AF                                        # mov edx,[ebx+0x18]
ABIL_ID_OFF   = 0x0C                                        # TAbility.FID
ABIL_COST_OFF = 0x14                                        # TAbility.FExpandCost (Integer)

CAVE_REG = 0x55826000       # see the placement note above — NOT 0x55824200

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)
PH_NAME = 0x61111116


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def fix_pic(code, va, pop_op, subs):
    """`call $+5 ; pop <reg>` -> a runtime delta anchor; rewrite placeholders as (target-anchor).

    The call's rel32 is zeroed so it falls straight through to the pop, which then holds the
    RUNTIME address of itself. Nothing here may use an absolute address: the DPL rebases.

    ⚠ never write the anchor as `call $+5` in the source — keystone assembles that to NOTHING,
    silently, and the search below then latches onto whatever earlier E8 happens to sit five
    bytes before a matching pop and zeroes ITS rel32. Emit a real `call <addr>`; the target is
    irrelevant because the rel32 is zeroed here anyway.
    """
    code = bytearray(code)
    i = next(k for k in range(len(code) - 5) if code[k] == 0xE8 and code[k + 5] == pop_op)
    anchor = va + i + 5
    code[i + 1:i + 5] = struct.pack("<i", 0)
    for ph, tgt in subs:
        hits = [k for k in range(len(code) - 3) if code[k:k + 4] == struct.pack("<I", ph)]
        assert len(hits) == 1, "placeholder %#x found %d times" % (ph, len(hits))
        code[hits[0]:hits[0] + 4] = struct.pack("<i", tgt - anchor)
    return bytes(code)


# --- cave_reg: re-issue the displaced RegisterAbility, then create + register ours ----------
def build_reg(name_va, cost=None):
    """Re-issue the displaced RegisterAbility, then create + register Reforming Flesh.

    At the splice site vanilla has just set EAX = the TAbilityControl and EDX = the ability it
    built for id 0x8D, so the leading `call` finishes vanilla's business unchanged. EBX holds
    the control for the whole of RegisterPassiveAbilities — 0x557BCE98 `mov eax,ebx` immediately
    before our site is the proof — which is what `mov eax,ebx` below relies on.

    ⚠⚠ `cost` IS A DEAD PARAMETER AND EVERY SHIPPED BUILD NOW PASSES None. It emits
    `mov dword [eax+0x14], cost` between CreateEnhancementAbility and RegisterAbility, which is
    the only window where EAX is the fresh ability — and the Ability.pfs load then zeroes that
    field a moment later, unconditionally, because rwInteger writes the default when tag 6 is
    absent. v2 shipped it, the ability still cost 0 in game, and cave_cost replaced it. It is
    kept ONLY so PRIOR_BUILDS can reproduce the v2 bytes for verify-before-write.
    ⚠ The store changes the cave's LENGTH — see the zone note below for why that matters.
    """
    store = ("        mov dword ptr [eax + 0x14], %d\n" % cost) if cost is not None else ""
    src = """
        call 0x%X
        call 0x%X
        pop eax
        lea edx, [eax + 0x%X]
        mov ecx, 0x%X
        mov eax, 0x%X
        call 0x%X
%s        mov edx, eax
        mov eax, ebx
        call 0x%X
        ret
    """ % (REGISTER_ABIL, CAVE_REG, PH_NAME, SEL_TYPES,
           ABILITY_ID, CREATE_ENH, store, REGISTER_ABIL)
    return fix_pic(asm(src, CAVE_REG), CAVE_REG, 0x58, [(PH_NAME, name_va)])


# refcount -1 => LStrAsg shares the literal and never tries to free it (the Path of Sand recipe)
NAME_BLOB = struct.pack("<iI", -1, len(ABILITY_NAME)) + ABILITY_NAME + b"\x00"


def build_round(cave_va, heal=None, skip_round1=False):
    """The per-round heal. EAX = combat object on entry; EBX/ESI belong to the host loop.

    Stack discipline: exactly one slot (the object) is live across the body, pushed at entry
    and popped at `done`; the max is parked in a second slot only across the GetHitPoints
    call. Every early-out jumps to `done`, so the pop is on every path.

    ── the round-1 gate is a PARAMETER, not a snippet to paste ──────────────────────────────
    `skip_round1=True` makes the heal start in round 2. It is a parameter because the comment
    that used to sit here was WRONG and would have crashed the game if anyone had followed it:

            mov eax, [esi + 0x0C]          <- WRONG: destroys the combat object
            cmp dword ptr [eax + 0x44], 1
            jle done

    ⚠ EAX must still be the combat object TWO INSTRUCTIONS LATER, at `mov ecx,[eax]` /
    `call [ecx+0xA8]`. Leaving TCombatData in EAX there dispatches GetAbilityEnabled through
    TCombatData's VMT with EAX = TCombatData: access violation, or silent garbage if the slot
    happens to be populated. The old note spotted the EAX clobber but reasoned only about the
    replay at `done` — which the pushed copy does cover — and missed the dispatch in between.

    The gate emitted below therefore scratches in EDX, which the very next instruction
    (`mov edx, ABILITY_ID`) overwrites anyway: no clobber, no reload, three instructions.
    ESI = the TCombat (see the header), [+0x0C] = TCombatData, [+0x44] = the round counter,
    already incremented at 0x5572A39F, so round 1 reads 1 and `jle` skips it.
    Being a parameter, it is assembled, disassembled by --dis and length-tracked like any other
    dimension of the cave — a comment can rot into a landmine, generated code cannot.
    """
    gate = ("        mov edx, [esi + 0x0C]\n"
            "        cmp dword ptr [edx + 0x44], 1\n"
            "        jle done\n") if skip_round1 else ""
    src = """
        push eax
%s        mov edx, 0x%X
        mov ecx, [eax]
        call dword ptr [ecx + 0x%X]
        test al, al
        je done
        mov eax, [esp]
        mov ecx, [eax]
        call dword ptr [ecx + 0x%X]
        movsx ecx, al
        test ecx, ecx
        jle done
        push ecx
        mov eax, [esp + 4]
        mov ecx, [eax]
        call dword ptr [ecx + 0x%X]
        movsx edx, al
        pop ecx
        test edx, edx
        jle done
        add edx, %d
        cmp edx, ecx
        jle ok
        mov edx, ecx
    ok:
        mov eax, [esp]
        mov ecx, [eax]
        call dword ptr [ecx + 0x%X]
    done:
        pop eax
        mov edx, [eax]
        call dword ptr [edx + 0x%X]
        jmp 0x%X
    """ % (gate, ABILITY_ID, VMT_ABIL_ENABLED,
           VMT_GET_HITS,                       # max FIRST, so the <=0 guard runs before any add
           VMT_GET_HP,
           HEAL if heal is None else heal,
           VMT_SET_HP,
           VMT_NEW_ROUND, ROUND_BACK)
    return asm(src, cave_va)
    # Line by line, and why each guard is here:
    #   push eax                    keep the object; EAX is volatile across every call below
    #   GetAbilityEnabled(0xB1)     +0xA8; non-units answer via TCombatObject's xor eax,eax/ret
    #   test al,al / je done        Delphi Boolean is a byte
    #   GetHits -> movsx ecx,al     ⚠ the accessor writes AL only — never trust the full EAX
    #   test ecx,ecx / jle done     max<=0 means [obj+0x4c] is nil (or the object is bogus).
    #                               WITHOUT this guard the clamp below would set HP := max = 0
    #                               and kill it — healing something to death is the exact
    #                               failure this feature must not have, so the guard stays even
    #                               though the corpse check makes it near-unreachable. 4 bytes.
    #   GetHitPoints -> movsx edx,al   same byte-width trap
    #   test edx,edx / jle done     never heal a corpse back to life
    #   add edx, HEAL               32-BIT. `add dl, bl` is what wraps and kills.
    #   cmp edx,ecx / jle ok / mov edx,ecx    *** the 32-bit clamp — DO NOT OMIT ***
    #   SetHitPoints(edx)           now guaranteed in [1, max], so its signed-byte path is safe
    #   done: pop eax               the displaced dispatch, replayed verbatim
    #   jmp ROUND_BACK


def build_cost(cave_va, fixes):
    """Re-instate a level-up cost that the Ability.pfs load has just zeroed. EBX = the ability.

    Emitted straight after `call [edi+0x2c]` (rwInteger, tag 6) inside TAbility.ReadWrite, so at
    entry [ebx+0x14] holds either the file's tag 6 or — when the record or the tag is missing —
    the 0 rwInteger wrote as the default. Only the 0 is replaced; a non-zero figure came out of
    the data file and is somebody's explicit choice.

    ⚠ NOTHING BUT EFLAGS MAY BE CLOBBERED before the replayed `mov ecx,7`: the host sets EDX, EAX
    and EDI *after* the splice point but ESI (the stream) and EBX (the ability) are live across
    it, and the tag-7 call two instructions later consumes ECX. Every instruction here is a
    compare or a store against [ebx+disp8]; no register is written.

    ⚠ THE KEYSTONE imm8 TRAP. `cmp dword ptr [ebx+0x0c], 0xB1` has a 4-byte encoding
    (83 7B 0C B1) whose imm8 SIGN-EXTENDS to 0xFFFFFFB1 — it assembles, it verifies, and it never
    matches. Today keystone picks the 7-byte imm32 form; assert_encoding() below re-reads the
    assembled bytes with capstone and aborts if that ever changes, rather than trusting it.
    """
    src = ""
    for i, (aid, cost) in enumerate(fixes):
        src += ("        cmp dword ptr [ebx + 0x%X], 0x%X\n"
                "        jne n%d\n"
                "        cmp dword ptr [ebx + 0x%X], 0\n"
                "        jne n%d\n"
                "        mov dword ptr [ebx + 0x%X], %d\n"
                "    n%d:\n" % (ABIL_ID_OFF, aid, i, ABIL_COST_OFF, i, ABIL_COST_OFF, cost, i))
    src += "        mov ecx, 7\n        jmp 0x%X\n" % RW_BACK
    code = asm(src, cave_va)
    assert_encoding(code, cave_va, fixes)
    return code


def assert_encoding(code, va, fixes):
    """Read the assembled cave back with capstone and check every immediate is what we meant.

    This is the keystone-round-trip rule made mechanical rather than a habit: a sign-extended
    imm8 disassembles as 0xffffffb1, which no ability id can ever equal, and the only symptom in
    game would be that the cost stayed 0 — i.e. exactly the bug being fixed, unchanged.
    """
    want = []
    for aid, cost in fixes:
        want += [aid, 0, cost]
    got = []
    for ins in cs.disasm(code, va):
        if ins.mnemonic in ("cmp", "mov") and ins.op_str.startswith("dword ptr [ebx"):
            got.append(int(ins.op_str.rsplit(", ", 1)[1], 0))
    assert got == want, ("cave_cost immediates came back as %s, expected %s — keystone chose a "
                         "sign-extending imm8 form. Emit the imm32 encoding by hand."
                         % ([hex(x) for x in got], [hex(x) for x in want]))


# ---- the cave zone: ONE blob at ONE address -----------------------------------------------
# ⚠ EXPAND_COST changes cave_reg's LENGTH (a 7-byte `mov dword [eax+0x14],imm32`), which slides
# everything laid out after it. What that actually did between v1 and v2 — measured off the two
# build_zone() outputs, not assumed:
#
#     piece            v1 (cost=None)     v2 (cost=50)      moved?
#     cave_reg         55826000  42 B     55826000  49 B    no  (it is the anchor; it grew)
#     name literal     5582602C  24 B     55826034  24 B    YES, +8
#     cave_round       55826050  91 B     55826050  91 B    no  — the `& ~0xF` align ate the 7
#     whole zone       171 B              171 B             no
#
# So **only the name literal moved**. cave_round's 16-byte alignment absorbed the growth, the tail
# jump at ROUND_INJ is byte-identical in both builds, and PRIORS[ROUND_INJ] is therefore currently
# a duplicate of the live encoding — harmless dead weight, since classify() returns "done" on the
# equality test before it ever consults a prior.
#
# The one-blob design is still right, but NOT for the reason v1's comment gave (it claimed
# cave_round moved; it did not). The real reason is smaller and still fatal: v1 classified the
# three pieces separately BY VA, and the name literal alone moving is enough to break that. At the
# NEW name VA the file holds the tail of v1's name blob plus padding — matching neither the target,
# nor zero, nor any per-VA "prior" — so --apply aborts with "other" on a file this script wrote
# itself, and the only way forward would be the revert-and-re-apply this project does not have.
# Hence: one write, one whole-blob comparison, priors kept per whole zone.
#
# ⚠ The alignment slack is luck, not a guarantee. A larger edit to cave_reg WOULD push cave_round
# past 0x55826050 and move the tail jump, which is exactly the silent-unlink failure recorded for
# build_magebane.py. That is why the round_jmp priors stay even though today's is redundant.
# build_shield.py's VARIANTS block is the same lesson.
#
# ⚠ TWO DIFFERENT EXTENTS — do not conflate them (v1's comment did):
#     the blob itself   55826000..558260D0   208 B: cave_reg + pad + name + pad + cave_round
#                                                   + pad + cave_cost
#     CAVE_ZONE_END     558260F0             = longest-ever blob + 0x20 growth slack, which the
#                                              write path zeroes and which must therefore be
#                                              PROVED zero first — see the guard in main().
#
# v3 (2026-09-10) appended cave_cost. It is LAST on purpose: `mov r/m32, imm32` is length-stable,
# so an EXPAND_COST re-tune moves nothing and both tail jumps keep their v2 encodings.
def build_zone(heal=HEAL, fixes=None, skip_round1=False, reg_store=None):
    """Lay cave_reg + name literal + cave_round + cave_cost back to back from CAVE_REG.

    -> (blob, [(label, va, bytes), ...]) in layout order.

    `fixes` is COST_FIXES, or [] for a build with no cave_cost at all (v1/v2, and any future
    EXPAND_COST = None). `reg_store` is v2's dead FExpandCost store in cave_reg — None everywhere
    except in PRIOR_BUILDS.

    ⚠ cave_reg is assembled TWICE: once to learn its length, then again with the resolved name
    VA. `lea edx,[eax+imm32]` is length-stable, so the second pass cannot move anything — the
    assert says so out loud rather than trusting it.
    """
    fixes = COST_FIXES if fixes is None else fixes
    probe = build_reg(0, reg_store)
    name_blob_va = (CAVE_REG + len(probe) + 3) & ~3
    reg = build_reg(name_blob_va + 8, reg_store)     # +8 skips the refcount+length header
    assert len(reg) == len(probe), "cave_reg changed length when the name VA was resolved"
    blob = bytearray(reg)
    blob += bytes(name_blob_va - CAVE_REG - len(blob))
    blob += NAME_BLOB
    round_va = (CAVE_REG + len(blob) + 0xF) & ~0xF
    blob += bytes(round_va - CAVE_REG - len(blob))
    rnd = build_round(round_va, heal, skip_round1)
    blob += rnd
    parts = [("cave_reg", CAVE_REG, reg),
             ("name literal", name_blob_va, NAME_BLOB),
             ("cave_round", round_va, rnd)]
    if fixes:
        cost_va = (CAVE_REG + len(blob) + 0xF) & ~0xF
        blob += bytes(cost_va - CAVE_REG - len(blob))
        cst = build_cost(cost_va, fixes)
        blob += cst
        parts.append(("cave_cost", cost_va, cst))
    return bytes(blob), parts


ZONE, PARTS = build_zone()
NAME_BLOB_VA = PARTS[1][1]
CAVE_ROUND = PARTS[2][1]
CAVE_COST = PARTS[3][1] if len(PARTS) > 3 else None

# Every zone layout this script has ever shipped. Verify-before-write accepts any of them as a
# starting state, so a re-tune of HEAL, EXPAND_COST or the round gate is a rewrite IN PLACE and
# never needs a revert-and-re-apply. Append a kwargs dict whenever a shipped cave changes.
#   v1 (2026-08-30): no FExpandCost store — the ability was permanently free at level-up.
#   v2 (2026-08-31): `mov dword [eax+0x14], 50` in cave_reg. STILL FREE in game: the Ability.pfs
#                    load zeroes the field afterwards. Superseded by cave_cost, not re-tuned.
PRIOR_BUILDS = [dict(fixes=[], reg_store=None),
                dict(fixes=[], reg_store=50)]
PRIOR_ZONES = [build_zone(**kw) for kw in PRIOR_BUILDS]

CAVE_ZONE_END = CAVE_REG + max([len(ZONE)] + [len(z) for z, _p in PRIOR_ZONES]) + 0x20
# Where cave_cost's cost immediate sits inside the blob — the ONE field an EXPAND_COST re-tune
# changes. classify() uses it to recognise an installed cave of ours that carries a different
# number, so a re-tune is an in-place rewrite and never a revert-and-re-apply (build_invis_
# penalty.py is the worked example of the same idiom).
# ⚠ DERIVED by disassembling the cave, never counted by hand: the block is 22 bytes today and a
# hand-written offset would rot the moment an instruction changes, silently — a wrong span makes
# classify() call a foreign cave "ours" and overwrite it.
RETUNE_SPANS = []
if CAVE_COST is not None:
    for _ins in cs.disasm(PARTS[3][2], CAVE_COST):
        if _ins.mnemonic == "mov" and _ins.op_str.startswith("dword ptr [ebx + 0x%X]" % ABIL_COST_OFF):
            RETUNE_SPANS.append((_ins.address - CAVE_REG + _ins.size - 4, 4))
    assert len(RETUNE_SPANS) == len(COST_FIXES), "could not locate every cost immediate"


def round_jmp(va):
    return b"\xE9" + struct.pack("<i", va - (ROUND_INJ + 5)) + b"\x90" * 3


def rw_jmp(va):
    return b"\xE9" + struct.pack("<i", va - (RW_INJ + 5))    # exactly 5 bytes, no padding


WRITES = [
    (CAVE_REG, ZONE, "cave zone: cave_reg + name literal @%08X + cave_round @%08X (+%d HP/round)"
                     "%s" % (NAME_BLOB_VA, CAVE_ROUND, HEAL,
                             "" if CAVE_COST is None else
                             " + cave_cost @%08X (cost %d)" % (CAVE_COST, EXPAND_COST))),
    (REG_INJ, b"\xE8" + struct.pack("<i", CAVE_REG - (REG_INJ + 5)),
     "RegisterAbility call @%08X -> cave_reg" % REG_INJ),
    (ROUND_INJ, round_jmp(CAVE_ROUND),
     "round dispatch @%08X -> cave_round" % ROUND_INJ),
]
ORIGINALS = {CAVE_REG: bytes(len(ZONE)), REG_INJ: REG_ORIG, ROUND_INJ: ROUND_ORIG}
if CAVE_COST is not None:
    WRITES.append((RW_INJ, rw_jmp(CAVE_COST),
                   "TAbility.ReadWrite @%08X -> cave_cost" % RW_INJ))
    ORIGINALS[RW_INJ] = RW_ORIG
# ⚠ The TAIL JUMP moves with the layout, so its old encodings are priors in their own right.
# A stale `jmp` left pointing into the middle of a rebuilt zone is precisely the silent-unlink
# failure recorded for build_magebane.py: "caves match: False means look at the TAIL JUMP, not
# the body."
PRIORS = {CAVE_REG: [z for z, _p in PRIOR_ZONES],
          ROUND_INJ: [round_jmp(p[2][1]) for _z, p in PRIOR_ZONES],
          RW_INJ: [rw_jmp(p[3][1]) for _z, p in PRIOR_ZONES if len(p) > 3]}

AOW_PROCS = ["AoW", "AoWCompat", "AoWDevEd", "AoWEd"]


def kill_aow():
    """Game files are locked while any AoW binary runs; the editor loads the DLL too.
    Standing authorization to kill them — the game autosaves per turn."""
    killed = [n for n in AOW_PROCS
              if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                                capture_output=True, text=True).returncode == 0]
    if killed:
        print("  killed running: " + ", ".join(killed))


# ============================================ Release/Ability.pfs: the mask that actually counts
# TAbilityControl.ReadWrite @0x55750164 serialises every ability under tag `list index + 10`, and
# RegisterAbility parks the object at list[id], so the record key is id + 10. TAbility.ReadWrite
# @0x5574F07C then reads tag 9 straight into the word at [ability+0x20]. That load happens AFTER
# registration, so THE DATA FILE WINS over whatever the cave passed — all 21 vanilla
# CreateEnhancementAbility sites register a mask the .pfs promptly overwrites. Patching only the
# cave would change nothing in game.
#
# ⚠ This writer is LENGTH-PRESERVING ONLY: it stamps an existing record's tag-9 word. It cannot
# MINT a record. Ability 0xB1 has no record until the user assigns it to something in AoWDevEd
# and saves. So a missing record is reported as a TODO and does NOT abort the DLL half — the
# ability still registers and still heals; only the level-up/editor offer waits on the record.
ABIL_PFS = os.path.join(GAME, "Release", "Ability.pfs")
ABIL_PFS_BACKUP = os.path.join(BACKUP_DIR, os.path.basename(ABIL_PFS) + ".pre-reformingflesh")
PFS_RESIDUE = 0x2144DF1C          # crc32(d[4:]) of an intact file — see PFS_Format_CRC.md


def pfs_tag9_offset(d):
    """File offset of record (ABILITY_ID+10)'s tag-9 word, or None if there is no such record.

    Derived, never hard-coded: AoWDevEd rewrites this file whole and every offset inside it
    moves. Record bodies tile the file from the first one to EOF, so absolute starts fall out of
    the body lengths. ⚠ Never locate a field by distance from either end — parse the directory.

    The CRC gate is the file's integrity check, and it lives here because every path that reads
    or writes Ability.pfs comes through this function. Stated honestly:
      CATCHES  incoherent damage — a flipped payload byte, a nudged offset, a truncation.
      MISSES   a coherent-but-wrong layout that was re-CRC'd (by an earlier version of this very
               script, say) — that reads as intact and always will.
    """
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        sys.exit("ABORT: Ability.pfs CRC residue is %#010x, expected %#010x — the file is ALREADY "
                 "damaged, before this script has edited anything.\n"
                 "       Refusing to touch it: repairing the CRC over the damage would stamp it "
                 "valid and destroy the evidence that anything was ever wrong.\n"
                 "       Restore Release/Ability.pfs or re-save it from AoWDevEd, then re-run."
                 % (zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF, PFS_RESIDUE))
    # ⚠ Do NOT add an "integrity check" that reconstructs record starts by tiling body lengths
    #   backwards from EOF and compares against the body parse_index handed back. That is
    #   CIRCULAR and CANNOT FAIL — it proves only that slicing is deterministic. It was removed
    #   from build_drillmaster.py and build_vision9.py for exactly that reason (it passed a
    #   deliberate +3 offset nudge). The CRC residue above is the real check.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pfs", os.path.join(GAME, "Modding Resources", "re_tools", "pfs.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    recs = m.parse_index(bytes(d))
    starts, at = {}, len(d)
    for rid, body in reversed(recs):
        at -= len(body)
        starts[rid] = at
    key = ABILITY_ID + 10
    if key not in starts:
        return None                                    # not minted yet — the user's DevEd step
    a, body = starts[key], dict(recs)[key]
    p = 1 + (4 if body[0] & 0x80 else 0)
    ent = [(body[1 + 2 * k], body[2 + 2 * k]) for k in range(body[0] & 0x7f)]
    p += 2 * len(ent)
    for k in range(struct.unpack_from("<I", body, 1)[0] if body[0] & 0x80 else 0):
        t, o = struct.unpack_from("<II", body, p + 8 * k); ent.append((t, o))
    p += 8 * (len(ent) - (body[0] & 0x7f))
    for t, o in ent:
        if t == 9:
            return a + p + o
    return None                                        # record exists but carries no tag 9


def pfs_read(path=None):
    """-> (buffer, current mask or None). None means 'no record / no tag 9 yet'."""
    try:
        d = bytearray(open(path or ABIL_PFS, "rb").read())
    except OSError as e:
        print("  (Ability.pfs unreadable: %s)" % e)
        return None, None
    off = pfs_tag9_offset(d)
    return d, (None if off is None else struct.unpack_from("<H", d, off)[0])


def pfs_write(value):
    d, _cur = pfs_read()
    off = pfs_tag9_offset(d)
    if off is None:
        return False
    struct.pack_into("<H", d, off, value)              # length-preserving u16, no offsets move
    struct.pack_into("<I", d, len(d) - 4, zlib.crc32(bytes(d[4:-4])) & 0xFFFFFFFF)
    # ⚠ not an `assert`: `python -O` strips those, and a stripped guard here would not fail
    # loudly — it would write a file the game and the editor reject on load.
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        sys.exit("ABORT: CRC repair produced residue %#010x, expected %#010x — nothing written."
                 % (zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF, PFS_RESIDUE))
    open(ABIL_PFS, "wb").write(bytes(d))
    return True


def check_id_free(d):
    """Abort if ABILITY_ID is already registered. Measured from the binary, never taken on trust.

    A collision is not a soft failure: the engine raises during unit initialisation and Delphi
    reports a bare `Runtime error 217` before the main window ever appears — which is why this
    has to fail at BUILD time. The documented "safe band" in Ability_ID_Budget.md has gone stale
    once already (0xAA was called free after it had been taken), so re-measure every build.
    """
    import importlib.util
    used = set()
    for i in range(len(d) - 10):
        if d[i] == 0xB8 and d[i + 5] == 0xE8:
            try:
                va = off2va(d, i + 5)
            except ValueError:
                continue
            if va and (va + 5 + struct.unpack_from("<i", d, i + 6)[0]) & 0xFFFFFFFF == CREATE_ENH:
                # skip OUR OWN cave, or a re-run against an already-applied file reports the id
                # we just installed as a collision
                if CAVE_REG <= va < CAVE_ZONE_END:
                    continue
                used.add(struct.unpack_from("<I", d, i + 1)[0])
    # Ability.pfs only WIDENS the picture when choosing a fresh id. It must not drive the abort:
    # once the ability is assigned to a unit in DevEd the editor writes a record for our own id,
    # and treating that as a collision would block every re-run.
    data = set()
    try:
        sp = os.path.join(GAME, "Modding Resources", "re_tools", "pfs.py")
        spec = importlib.util.spec_from_file_location("pfs", sp)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        data = {rid - 10 for rid, _b in m.load("ability.pfs")[0]}
    except Exception:                                          # noqa: BLE001
        print("  (could not read Ability.pfs — id check used the DLL only)")
    if ABILITY_ID in used:
        free = [x for x in range(0, 0xCE) if x not in used | data]
        sys.exit("ABORT: ability id 0x%02X is registered by the DLL already — this is the "
                 "collision that shows in game as `Runtime error 217`. Free ids: %s"
                 % (ABILITY_ID, ", ".join("0x%02X" % x for x in free[-6:])))
    if ABILITY_ID > 0xCD:
        sys.exit("ABORT: id 0x%02X is above the 0xCD ceiling — TAbilityOwner.ReadWrite "
                 "@0x5574F318 serialises under a ONE-BYTE tag 0x32+id." % ABILITY_ID)
    both = used | data
    print("  id 0x%02X free to register (%d ids known, highest 0x%02X)%s"
          % (ABILITY_ID, len(both), max(both),
             "; already assigned in Ability.pfs" if ABILITY_ID in data else ""))


def assert_reg_site(d):
    """Re-measure the splice site instead of trusting the constant.

    Requires REG_INJ's rel32 to point at RegisterAbility right now, and that it lies inside
    PassiveAb.RegisterPassiveAbilities. If a previous feature has claimed it, this says so by
    name rather than letting the splice land on someone else's cave call.
    """
    F, L = 0x557BC1CC, 0xE00
    if not (F <= REG_INJ < F + L):
        sys.exit("ABORT: REG_INJ %08X is outside RegisterPassiveAbilities." % REG_INJ)
    cur = bytes(d[va2off(d, REG_INJ):va2off(d, REG_INJ) + 5])
    # ⚠ look the target up BY VA, never by position in WRITES — the list was reordered when the
    # three caves became one zone entry, and the old `WRITES[3][1]` silently became a different
    # site's bytes (here it went out of range, which was luck, not design).
    if cur == next(new for va, new, _t in WRITES if va == REG_INJ):
        return "done"
    if cur != REG_ORIG:
        tgt = (REG_INJ + 5 + struct.unpack_from("<i", cur, 1)[0]) & 0xFFFFFFFF if cur[0] == 0xE8 \
            else None
        sys.exit("ABORT: %08X is not a free `call RegisterAbility` — it holds %s%s.\n"
                 "       Another feature owns this splice site. Pick a different one."
                 % (REG_INJ, cur.hex(" "),
                    " (call %08X)" % tgt if tgt else ""))
    return "clean"


def off2va(d, off):
    for va0, sz, raw in sections(d):
        if raw <= off < raw + sz:
            return DLL_BASE + va0 + (off - raw)
    raise ValueError(off)


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    s, out = pe + 24 + opt, []
    for _ in range(n):
        vs, va, rs, raw = struct.unpack_from("<IIII", d, s + 8)
        out.append((va, max(vs, rs), raw))
        s += 40
    return out


def va2off(d, va):
    """⚠ per-section, never one global delta — this DLL's DATA skews differently from CODE."""
    for va0, sz, raw in sections(d):
        if va0 <= va - DLL_BASE < va0 + sz:
            return raw + (va - DLL_BASE - va0)
    raise ValueError("VA %08X not mapped" % va)


def installed_cave_va(d, inj):
    """Where the E9 at `inj` actually points right now, or None if there is no jump.

    Derived from the file, never from this build's constants — a change to cave_reg's length
    moves everything after it, so an older install's caves sit elsewhere.
    """
    o = va2off(d, inj)
    if d[o] != 0xE9:
        return None
    return (inj + 5 + struct.unpack_from("<i", d, o + 1)[0]) & 0xFFFFFFFF


def installed_round_va(d):
    return installed_cave_va(d, ROUND_INJ)


def dis(d, va, n, title):
    print("\n  ---- %s  @%08X (%d bytes, installed)" % (title, va, n))
    o = va2off(d, va)
    for ins in cs.disasm(bytes(d[o:o + n]), va):
        print("    %08X  %-22s %-7s %s"
              % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))


def main():
    apply_, undo, only_dis = "--apply" in sys.argv, "--undo" in sys.argv, "--dis" in sys.argv
    d = bytearray(open(DLL, "rb").read())

    print("Reforming Flesh (id 0x%02X): +%d HP at the start of every combat round" % (ABILITY_ID, HEAL))
    print("caves at %08X..%08X   hook %08X   reg site %08X"
          % (CAVE_REG, CAVE_ZONE_END, ROUND_INJ, REG_INJ))
    if not undo:
        check_id_free(d)
        assert_reg_site(d)
    if only_dis:
        # ⚠ Read the layout OFF THE DISK, never off this build's constants: a prior install has
        # cave_round at a different VA, and disassembling this build's CAVE_ROUND would then
        # quietly show the wrong bytes (or padding) and call them the installed cave.
        rva = installed_round_va(d)
        dis(d, CAVE_REG, NAME_BLOB_VA - CAVE_REG, "cave_reg + padding (this build's extent)")
        nb = bytes(d[va2off(d, NAME_BLOB_VA):va2off(d, NAME_BLOB_VA) + len(NAME_BLOB)])
        print("\n  ---- name literal @%08X (%d bytes, installed)\n    %s   %r"
              % (NAME_BLOB_VA, len(NAME_BLOB), nb.hex(" "), bytes(nb[8:-1])))
        if rva is None:
            print("\n  cave_round: ROUND_INJ holds no E9 — the hook is not installed.")
        else:
            if rva != CAVE_ROUND:
                print("\n  ⚠ the installed tail jump points at %08X, not this build's %08X — "
                      "an older layout is on disk." % (rva, CAVE_ROUND))
            dis(d, rva, len(PARTS[2][2]), "cave_round")
        cva = installed_cave_va(d, RW_INJ)
        if cva is None:
            print("\n  cave_cost: RW_INJ %08X holds no E9 — the level-up cost hook is NOT\n"
                  "  installed, so Reforming Flesh costs whatever Ability.pfs says, i.e. 0."
                  % RW_INJ)
        elif CAVE_COST is None:
            print("\n  ⚠ RW_INJ jumps to %08X but this build emits no cave_cost." % cva)
        else:
            if cva != CAVE_COST:
                print("\n  ⚠ the installed cost hook points at %08X, not this build's %08X — "
                      "an older layout is on disk." % (cva, CAVE_COST))
            dis(d, cva, len(PARTS[3][2]), "cave_cost")
        # The round-1 gate is not installed and never has been; this proves the documented
        # variant assembles to what the docstring claims, which a comment could not.
        gz, gp = build_zone(skip_round1=True)
        print("\n  ---- cave_round WITH skip_round1=True  @%08X (%d bytes, NOT INSTALLED — "
              "verification only)" % (gp[2][1], len(gp[2][2])))
        for ins in cs.disasm(gp[2][2], gp[2][1]):
            print("    %08X  %-22s %-7s %s"
                  % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))
        print("    (whole zone would be %d bytes vs %d installed)" % (len(gz), len(ZONE)))
        return

    def classify(va, new):
        """-> (state, installed length). The length is what the growth-zone proof needs: a
        `clean` zone owns 0 bytes, so on a fresh file the WHOLE zone must be proved zero."""
        o = va2off(d, va)
        cur = bytes(d[o:o + len(new)])
        if cur == new:
            return "done", len(new)
        if cur == ORIGINALS[va]:
            return "clean", 0
        # A re-tune: our own cave with a different EXPAND_COST. Recognised by masking out the
        # cost immediates and comparing everything else, so an in-place rewrite is a normal
        # operation instead of a "MISMATCH, revert and re-apply" this project cannot perform.
        if va == CAVE_REG and RETUNE_SPANS:
            a, b = bytearray(cur), bytearray(new)
            for off, n in RETUNE_SPANS:
                a[off:off + n] = b[off:off + n] = bytes(n)
            if a == b:
                return "retune", len(new)
        for prior in PRIORS.get(va, ()):
            if bytes(d[o:o + len(prior)]) == prior:
                return "prior", len(prior)
        return "other", 0

    seen = [(va, new, t) + classify(va, new) for va, new, t in WRITES]
    states = {st for _va, _n, _t, st, _l in seen}
    print("\ncurrent: %s" % ", ".join(sorted(states)))
    for va, _new, t, st, _l in seen:
        print("  %08X  %-6s %s" % (va, st.upper(), t))
        if st == "retune" and va == CAVE_REG:
            o = va2off(d, va)
            for i, (off, n) in enumerate(RETUNE_SPANS):
                print("           installed cost for id 0x%02X = %d, this build says %d"
                      % (COST_FIXES[i][0], struct.unpack_from("<I", d, o + off)[0],
                         COST_FIXES[i][1]))
    if "other" in states:
        sys.exit("\nABORT: a site matches neither the original nor the target. Investigate.")
    installed_len = dict((va, l) for va, _n, _t, _st, l in seen).get(CAVE_REG, 0)

    # ⚠ THE GROWTH ZONE MUST BE PROVED ZERO ON EVERY PATH — not just from `clean`.
    # This check used to be gated on `"clean" in states`, but the write below zeroes
    # CAVE_REG..CAVE_ZONE_END *unconditionally*, --undo included — and on --undo the state is
    # never `clean` by definition. So the one path that skipped the check was also a path that
    # clobbers. QA planted 0xCC at 0x558260C7 on a scratch copy: the script printed
    # "DONE / nothing to do" with no warning, and --undo then silently zeroed it. Nothing owns
    # that range today, which makes it luck, not safety — and silent-clobber is the exact class
    # of failure this project keeps getting bitten by.
    # Now: computed on every path, and a non-zero tail ABORTS before anything is written.
    # ⚠ v3 tightened the START of the range. It used to be CAVE_ZONE_END - 0x20 — the slack past
    # the longest blob EVER SHIPPED — which silently exempted the 37 bytes v3's cave_cost claims
    # beyond v2's 171. Those bytes were never ours, so they get the same proof as the slack: the
    # range now starts at the end of what is ACTUALLY INSTALLED (0 on a clean file, so the whole
    # zone is proved), which is exactly "bytes we would zero that are not already ours".
    tail_va = CAVE_REG + installed_len
    t0, t1 = va2off(d, tail_va), va2off(d, CAVE_ZONE_END)
    tail = bytes(d[t0:t1])
    if any(tail):
        first = tail_va + next(i for i, b in enumerate(tail) if b)
        sys.exit("\nABORT: the growth zone %08X..%08X is NOT zero, and the write path would zero\n"
                 "it (on --apply AND on --undo). First non-zero byte at %08X.\n"
                 "  %s\n"
                 "Somebody may have claimed this range. Find out who before writing:\n"
                 "  grep -rl \"%08X\" \"Modding Resources/build_scripts/\"\n"
                 "Nothing written."
                 % (tail_va, CAVE_ZONE_END, first, tail.hex(" "), first))
    print("  growth zone %08X..%08X verified zero (%d B)" % (tail_va, CAVE_ZONE_END, len(tail)))

    _pfs, pfs_cur = pfs_read()
    pfs_done = pfs_cur == SEL_TYPES
    if pfs_cur is None:
        print("  Ability.pfs   WAIT  record %d does not exist yet — assign Reforming Flesh to a\n"
              "                      unit in AoWDevEd and save, then re-run to stamp the mask.\n"
              "                      (The DLL half below is independent and still applies.)\n"
              "                      ⚠ The editor must be one that reads the ZIGGURAT data root.\n"
              "                      An AoWDevEd started against the vanilla registry key writes\n"
              "                      <root>\\Release\\Ability.pfs, which nothing loads."
              % (ABILITY_ID + 10))
    else:
        print("  Ability.pfs   %-5s record %d tag 9 (selection mask) = %#06x -> %#06x"
              % ("DONE" if pfs_done else "TODO", ABILITY_ID + 10, pfs_cur, SEL_TYPES))
        if not pfs_done:
            print("                missing%s%s"
                  % ("" if pfs_cur & 0x100 else " astHeroUpgrade(0x100)",
                     "" if pfs_cur & 0x200 else " astEditor(0x200)"))

    print("\n  zone %d B total:   %s" % (len(ZONE), "   ".join(
        "%s %d B @%08X" % (lbl, len(b), va) for lbl, va, b in PARTS)))
    print("  hero level-up cost: %s"
          % ("NO cave_cost — the ability is FREE at level-up" if CAVE_COST is None else
             "%d, set in cave_cost @%08X (mov dword [ebx+0x%X], %d) — NOT in cave_reg: a "
             "registration-time\n                      store is zeroed by the Ability.pfs load"
             % (EXPAND_COST, CAVE_COST, ABIL_COST_OFF, EXPAND_COST)))
    for title, va, blob in PARTS:
        if title.startswith("name"):
            continue
        print("\n  ---- %s @%08X (%d bytes, assembled) ----" % (title, va, len(blob)))
        for ins in cs.disasm(blob, va):
            print("    %08X  %-22s %-7s %s"
                  % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))

    target = "clean" if undo else "done"
    pfs_at_target = True if pfs_cur is None else ((not pfs_done) if undo else pfs_done)
    if states == {target} and pfs_at_target:
        print("\nnothing to do — already %s." % target)
        return
    if not (apply_ or undo):
        print("\ndry run. --apply to write, --undo to revert.")
        return

    kill_aow()

    # ⚠ BACKUP GATING — only ever snapshot a file PROVED unpatched.
    # The gate is a POSITIVE test that every site still holds its original bytes, never "no
    # backup file exists yet". Three paths would otherwise mint a `.pre-*` full of PATCHED
    # bytes: --undo (the file IS the patched state), a HEAL re-tune over an existing install
    # (the file is our own previous output), and any guard that accepts "bytes this script could
    # have written" as proof of freshness. Such a file then sits on disk looking authoritative
    # while containing a patched state.
    if not undo and states == {"clean"} and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("  backup -> %s (taken with every site verified original)" % os.path.basename(BACKUP))
    elif not undo and not os.path.exists(BACKUP):
        print("  no backup taken: the DLL is not in a pristine state for this feature "
              "(a .pre-* full of patched bytes is worse than none).")

    # zero the whole cave zone first: a shrinking cave would otherwise leave a tail of the
    # previous build lying in executable memory
    z0, z1 = va2off(d, CAVE_REG), va2off(d, CAVE_ZONE_END)
    d[z0:z1] = bytes(z1 - z0)
    for va, new, _t in WRITES:
        o = va2off(d, va)
        d[o:o + len(new)] = ORIGINALS[va] if undo else new
    open(DLL, "wb").write(bytes(d))
    print("wrote AoWEPACK.dpl -> %s" % target)

    # Ability.pfs: patch the VALUE, not the file, so a DevEd re-save between apply and undo is
    # not clobbered — the backup exists to remember the old mask, not to be copied back.
    if pfs_cur is None:
        print("Ability.pfs untouched (no record %d yet)" % (ABILITY_ID + 10))
    elif undo:
        if not pfs_done:
            print("Ability.pfs untouched (mask is not ours)")
        elif os.path.exists(ABIL_PFS_BACKUP):
            was = pfs_read(ABIL_PFS_BACKUP)[1]
            if was is not None and pfs_write(was):
                print("Ability.pfs record %d tag 9 -> %#06x (from %s)"
                      % (ABILITY_ID + 10, was, os.path.basename(ABIL_PFS_BACKUP)))
        else:
            print("Ability.pfs left at %#06x — no backup to read the old mask from" % SEL_TYPES)
    elif not pfs_done:
        if not os.path.exists(ABIL_PFS_BACKUP):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(ABIL_PFS, ABIL_PFS_BACKUP)
            print("backup -> %s" % os.path.basename(ABIL_PFS_BACKUP))
        if pfs_write(SEL_TYPES):
            print("Ability.pfs record %d tag 9 %#06x -> %#06x (CRC repaired)"
                  % (ABILITY_ID + 10, pfs_cur, SEL_TYPES))


if __name__ == "__main__":
    main()
