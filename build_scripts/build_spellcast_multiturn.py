#!/usr/bin/env python3
"""
AoW1 Unit Spellcasting mod -- Multi-turn channelling + "level >= tier" gate.

M2 v2 (2026-08-28, CONFIRMED WORKING): cave_tiergate now reads the caster's Spell Casting level
through VMT +0x144 instead of calling TAbstractUnit.GetAbilityLevel @0x5577F658 directly. The
static call bypassed THero's override, so an ITEM-granted Spell Casting level read as 0 and every
spell failed the tier compare silently. Pairs with build_unitwin_ability.py (the exe-side gate).
AoWEPACK.dpl only. PREREQUISITE: build_spellcast.py (Phase 1) must be applied.

Two changes, both in AoWEPACK.dpl:

  M1  Fix multi-turn spell progression for units.
      Root cause: casting progress accrues ONLY in THero.NewTurn (@0x55787FCC);
      our Phase-1 cave_unit_newturn ran the *base* TAbstractUnit.NewTurn + a bare
      point refill, so a unit's in-progress spell (+0x84) never advanced (+0x88)
      and CastingReady was never reached -> the channel froze.
      Fix: a NEW cave_unit_newturn that runs the base NewTurn + owner check, then
      JUMPS INTO THero.NewTurn at 0x55787FEC (right past the hero-only
      ValidateHeroUpgrade call). From there the hero's own refill + accrual +
      ready-event code runs in place (with its already-.reloc'd globals) and its
      epilogue (POP EDI/ESI/EBX/RET) balances our matching prologue pushes.
      Completion is already unblocked for units by Phase-1 gate G6 (the is-THero
      inside TSpellCastEventLog.Execute). C1 (VMT +0x13C) is repointed to the new
      cave; the old Phase-1 cave is left as harmless dead bytes.

      Why not just point VMT +0x13C straight at THero.NewTurn? Because its first
      call is ValidateHeroUpgrade @0x55787D54 -- hero-only (experience via vtable
      +0x15c/+0x160, HeroExperienceTable, level cache +0x4C, THeroUpgradeEventLog).
      On a unit those vtable slots are not experience accessors -> garbage dispatch.

  M2  "Spellcasting level >= spell research tier" cast gate (applies to ALL
      casters -- units AND heroes, per user decision 2026-07-06).
      Injected into THero.CanCastSpell @0x55789710 (the generic strategic
      can-cast chokepoint; the exe calls it on the caster object, hero or unit).
      Right after GetSpell resolves the TSpell (0x5578974D), compare
      GetAbilityLevel(caster,0x34) [1..5] against TSpell+0x21 [tier 1..4]; if the
      level is lower, block the cast exactly like the function's own fail exit
      (EBX:=0; jmp common-exit). Gates both instant and multi-turn starts, and the
      AI path (TUnitSpell.AI* also routes through CanCastSpell).

      NOTE: strategic only. Combat (tactical/TCPCK) tier-gating, if wanted, is a
      separate patch in build_spellcast_tcpck.py.
      NOTE: hiding too-high-tier spells from the casting BOOK is done in the EXE
      (build_spellcast_book_exe.py), not here -- the book is filled by the exe
      calling TPlayerMagicControl.ListSpells directly, never THero.ListSpells.

Rebase-safe: caves are rel32/register-only (no absolute mem refs); the accrual
code with absolute globals executes in place inside THero.NewTurn. Overwritten
VMT slots already carry .reloc entries.

Idempotent, verifies every original byte, backs up before writing.
Dry-run by default; pass --apply to write.
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DPL    = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here
BACKUP = os.path.join(BACKUP_DIR, "AoWEPACK.dpl.pre-multiturn")   # state = Phase-1 applied, pre multi-turn
IMAGE_BASE = 0x55700000

# ---- PE section mapping (VA -> file offset) ----------------------------------
def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e+6)[0]
    opt  = e+24
    optsize = struct.unpack_from("<H", data, e+20)[0]
    sec = opt+optsize
    secs=[]
    for i in range(nsec):
        vsize,vaddr,rsize,raw = struct.unpack_from("<IIII", data, sec+8)
        secs.append((vaddr,vsize,raw,rsize)); sec+=40
    return secs
def va2off(secs, va):
    rva = va - IMAGE_BASE
    for vaddr,vsize,raw,rsize in secs:
        if vaddr <= rva < vaddr+max(vsize,rsize):
            return raw+(rva-vaddr)
    raise ValueError(f"VA {va:08X} not in any section")

# ---- game addresses (all verified in Ghidra) ---------------------------------
TABSU_NEWTURN    = 0x55780D4C    # TAbstractUnit.NewTurn(eax=self, edx=player)  -- base
THERO_NEWTURN_ACC= 0x55787FEC    # THero.NewTurn body just past ValidateHeroUpgrade (refill+accrual+ready)
# ⚠ 0x5577F658 is TAbstractUnit.GetAbilityLevel -- the BASE implementation, and THero OVERRIDES it
# (VMT +0x144 -> THero.GetAbilityLevel @0x5578831C, which searches self -> THeroItems -> inventory).
# v1 of cave_tiergate CALLED THE BASE STATICALLY, so an item-granted Spell Casting level resolved
# to 0 and every spell failed the tier compare -- silently, because the fail arm returns with no
# message. Symptom: the spellbook opens and clicking a spell does nothing. Fixed 2026-08-28 by
# dispatching through VMT +0x144 instead; kept here only as the v1 signature the re-tune accepts.
GETABILITYLEVEL  = 0x5577F658    # TAbstractUnit.GetAbilityLevel(eax=self, edx=abilityID) -> al
VMT_GETABILITYLEVEL = 0x144      # the item-aware slot -- dispatch, never call the base direct
PERSIST_BASE     = 0x5580D990    # build_spellcast_persist.py's cave -- cave_tiergate must end below
CANCAST_INJECT   = 0x5578974D    # THero.CanCastSpell: MOV ESI,EAX ; MOVSX EDX,[EBX+0x24]  (right after GetSpell)
CANCAST_CONT     = 0x55789753    # continue point (after the two replicated instrs)
CANCAST_EXIT     = 0x55789826    # common exit (EBX = result)
# build_spellcast_herotier.py (user ruling 2026-09-03: the tier gate is for UNITS ONLY) retargets
# the hook's rel32 to its own wrapper cave, which does IsClass(caster, THero) and then either
# skips the gate entirely (hero/leader) or falls into cave_tiergate unchanged (unit). Listing its
# address here makes that a second accepted "already applied" state, so this script's dry run stays
# clean and a later --apply cannot silently clobber the hero exemption. cave_tiergate itself is
# untouched by that patch and is still verified byte-for-byte below.
HEROTIER_CAVE    = 0x55846000

# Phase-1 cave anchors (from build_spellcast.py)
CAVE_BASE   = 0x5580D900
OLD_NEWTURN = 0x5580D90D         # Phase-1 cave_unit_newturn (CAVE_BASE + 13-byte iscaster)
TUNIT_VMT   = 0x55710CAC
TADJ_VMT    = 0x55712A54

# ---- place the new caves in fresh zero space after the Phase-1 cave ----------
NEW_NEWTURN = 0x5580D940         # verified zero-filled; Phase-1 cave ends 0x5580D93A

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

# M1: new cave_unit_newturn -- base NewTurn + owner check, then jump into
# THero.NewTurn's accrual body (skips the hero-only ValidateHeroUpgrade).
nt_src = f"""
    push ebx
    push esi
    push edi
    mov ebx, edx
    mov esi, eax
    mov edx, ebx
    mov eax, esi
    call 0x{TABSU_NEWTURN:X}
    cmp bl, byte ptr [esi + 0x24]
    jne _ret
    jmp 0x{THERO_NEWTURN_ACC:X}
_ret:
    pop edi
    pop esi
    pop ebx
    ret
"""
nt, _ = ks.asm(nt_src, NEW_NEWTURN); nt = bytes(nt)

# M2: cave_tiergate -- entered from CanCastSpell right after GetSpell.
#   in: eax=TSpell*, ebx=caster, edi=&err ; replicate the 2 overwritten instrs.
TIERGATE = NEW_NEWTURN + len(nt)


def tiergate_src(level_call):
    """`level_call` is the asm that leaves the caster's Spell Casting level in AL."""
    return f"""
    mov esi, eax
    push esi
    push edi
    push ebx
    mov eax, ebx
{level_call}
    pop ebx
    pop edi
    pop esi
    movzx eax, al
    movzx edx, byte ptr [esi + 0x21]
    cmp eax, edx
    jl _fail
    movsx edx, byte ptr [ebx + 0x24]
    jmp 0x{CANCAST_CONT:X}
_fail:
    xor ebx, ebx
    jmp 0x{CANCAST_EXIT:X}
"""


# ⚠ `push 0x34 / pop edx` is deliberate: it sets the FULL 32-bit EDX (push imm8 sign-extends, and
# 0x34 is positive) in 3 bytes where `mov edx,0x34` needs 5 -- which is what keeps the re-tuned
# cave inside its slot. `mov dl,0x34` would be 2 bytes but leaves EDX's upper 3 bytes dirty, and
# GetAbilityLevel takes the id as a full dword. Disassemble the cave (this script prints it) rather
# than trusting that reasoning -- see the keystone push-imm8 trap in the project notes.
tg = bytes(ks.asm(tiergate_src(
    "    mov ecx, dword ptr [eax]\n"
    "    push 0x34\n"
    "    pop edx\n"
    f"    call dword ptr [ecx + 0x{VMT_GETABILITYLEVEL:X}]"), TIERGATE)[0])

# v1 of the same cave -- the static call to the base implementation. Accepted as an alternative
# "original" so this script RE-TUNES IN PLACE instead of demanding a revert (see CLAUDE.md).
tg_v1 = bytes(ks.asm(tiergate_src(
    "    mov edx, 0x34\n"
    f"    call 0x{GETABILITYLEVEL:X}"), TIERGATE)[0])

CAVE_END = TIERGATE + len(tg)
TG_SLOT = PERSIST_BASE - TIERGATE
assert len(tg) <= TG_SLOT, (
    "cave_tiergate is %d bytes but only %d are free before build_spellcast_persist.py's cave at "
    "%08X" % (len(tg), TG_SLOT, PERSIST_BASE))
# Write the whole slot so a shorter re-tune cannot leave stale tail bytes behind.
tg_slot = tg + bytes(TG_SLOT - len(tg))
tg_v1_slot = tg_v1 + bytes(TG_SLOT - len(tg_v1))

def rel32(src_va, dst_va):
    return struct.pack("<i", dst_va - (src_va + 5))

# ---- patch table: (VA, original_bytes, new_bytes, desc) ----------------------
def ptr(v): return struct.pack("<I", v)

patches = []
# M1a: repoint C1 (VMT +0x13C) TUnit + TAdjustableUnit: old cave -> new cave
patches.append((TUNIT_VMT+0x13C, ptr(OLD_NEWTURN), ptr(NEW_NEWTURN), "M1 TUnit  +13C NewTurn -> new accrual cave"))
patches.append((TADJ_VMT +0x13C, ptr(OLD_NEWTURN), ptr(NEW_NEWTURN), "M1 TAdj   +13C NewTurn -> new accrual cave"))
# M1b + M2b: the new caves (fresh zero space)
patches.append((NEW_NEWTURN, bytes(len(nt)), nt, "M1 cave_unit_newturn (accrual)"))
patches.append((TIERGATE, (bytes(TG_SLOT), tg_v1_slot), tg_slot,
                "M2 cave_tiergate (level>=tier, item-aware via VMT +0x144)"))
# M2a: inject the tier gate into CanCastSpell (6 bytes: E9 rel32 + NOP)
inj_orig = b"\x8b\xf0\x0f\xbe\x53\x24"                       # mov esi,eax ; movsx edx,[ebx+0x24]
inj_new  = b"\xE9" + rel32(CANCAST_INJECT, TIERGATE) + b"\x90"
inj_hero = b"\xE9" + rel32(CANCAST_INJECT, HEROTIER_CAVE) + b"\x90"
# `new` may be a TUPLE of acceptable already-applied states, newest owner last; element 0 is what
# this script WRITES. Both forms leave cave_tiergate on the path for units.
patches.append((CANCAST_INJECT, inj_orig, (inj_new, inj_hero), "M2 CanCastSpell inject -> cave_tiergate"))

# ---- report caves ------------------------------------------------------------
print(f"cave_unit_newturn (new) @ {NEW_NEWTURN:08X}  ({len(nt)} bytes)")
print(f"cave_tiergate           @ {TIERGATE:08X}  ({len(tg)} bytes)")
print(f"new caves end           @ {CAVE_END:08X}")
print("--- cave_unit_newturn ---")
for ins in cs.disasm(nt, NEW_NEWTURN):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<22} {ins.mnemonic} {ins.op_str}")
print("--- cave_tiergate ---")
for ins in cs.disasm(tg, TIERGATE):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<22} {ins.mnemonic} {ins.op_str}")
print(f"--- CanCastSpell inject @ {CANCAST_INJECT:08X}: {inj_new.hex(' ')} ---")
print()

# ---- load + preconditions ----------------------------------------------------
with open(DPL,'rb') as fh: data = bytearray(fh.read())
secs = load_sections(data)

def rd(va, n):
    o = va2off(secs, va); return bytes(data[o:o+n])

# Phase-1 must be applied: TUnit instance grown + C1 pointing at the Phase-1 cave
if rd(0x55710C90,4) != struct.pack("<I",0x94):
    print("ABORT: Phase 1 (build_spellcast.py) not applied -- TUnit instance size != 0x94."); sys.exit(1)
c1 = rd(TUNIT_VMT+0x13C,4)
if c1 not in (ptr(OLD_NEWTURN), ptr(NEW_NEWTURN)):
    print(f"ABORT: unexpected C1 pointer {c1.hex(' ')} (expected Phase-1 {OLD_NEWTURN:08X} or new {NEW_NEWTURN:08X})."); sys.exit(1)

# ---- verify each patch -------------------------------------------------------
ok = True; already = 0; topatch = 0
for va, orig, new, desc in patches:
    # `orig` may be a TUPLE of acceptable prior states (a ladder), so a cave can be re-tuned in
    # place without reverting -- oldest first, newest last. See CLAUDE.md.
    # `new` may likewise be a TUPLE of acceptable APPLIED states (element 0 is what we write), so a
    # later feature that legitimately owns some of these bytes is not clobbered on a re-run.
    accept = orig if isinstance(orig, tuple) else (orig,)
    done   = new  if isinstance(new,  tuple) else (new,)
    cur = rd(va, len(done[0]))
    if cur in done:       already += 1
    elif cur in accept:   topatch += 1
    else:
        print(f"MISMATCH @ {va:08X} ({desc}):")
        for i, a in enumerate(accept):
            print(f"  accepted[{i}] {a.hex(' ')}")
        for i, a in enumerate(done):
            print(f"  applied[{i}]  {a.hex(' ')}")
        print(f"  found        {cur.hex(' ')}")
        ok = False
print(f"{already} already patched, {topatch} to patch, {len(patches)} total")
if not ok:
    print("ABORT: original bytes did not match."); sys.exit(1)
if '--apply' not in sys.argv:
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)
if topatch == 0:
    # Without this guard a no-op --apply still rewrote the file AND could mint `.pre-multiturn`
    # from an ALREADY-PATCHED image -- a backup that sits on disk looking authoritative while
    # containing the patched state. That is the exact trap CLAUDE.md warns about, manufactured by
    # this script. Nothing to do => touch nothing.
    print("Nothing to do -- already applied. File untouched, no backup minted."); sys.exit(0)

if not os.path.exists(BACKUP):
    os.makedirs(BACKUP_DIR, exist_ok=True); shutil.copyfile(DPL, BACKUP); print(f"Backup written: {BACKUP}")
else:
    print(f"Backup already exists (kept): {BACKUP}")
for va, orig, new, desc in patches:
    off = va2off(secs, va)
    write = new[0] if isinstance(new, tuple) else new
    if rd(va, len(write)) == write or (isinstance(new, tuple) and rd(va, len(write)) in new):
        continue                      # already in an accepted applied state -- do not clobber
    data[off:off+len(write)] = write
    print(f"patched {va:08X}  {desc}")
with open(DPL,'wb') as fh: fh.write(data)
print("AoWEPACK.dpl multi-turn + tier-gate patched.")
