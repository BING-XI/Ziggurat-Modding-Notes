#!/usr/bin/env python3
"""
AoW1 Unit Spellcasting mod -- Phase 1a (auto/fast-combat casting), AoWEPACK.dpl only.

Makes the Spellcasting ability (ID 0x34) functional on ordinary units in
AUTO-RESOLVE / fast combat (and the point-accounting + per-turn point refill
that underpins all casting). No EXE / AoWTCPCK changes -> no manual-combat
cast button and no strategic spellbook yet (those are Phase 1b / Phase 2).

What it does (all verified against the live binary, see Modding Resources doc):
  D1/D2  grow TUnit / TAdjustableUnit instance size 0x48 -> 0x94 so every unit
         carries the hero casting-state cluster at THero's own offsets (+0x7C..+0x93)
  D3-D5  redirect TUnit/TAdj VMT slots +0x128/+0x12C/+0x130 (GetCastingPoints[Max]/
         SetCastingPoints) to THero's class-agnostic implementations
  C1     install cave_unit_newturn into VMT +0x13C: calls TAbstractUnit.NewTurn
         then refills casting points (points := GetCastingPointsMax) on the owner's
         turn -- exactly THero.NewTurn's refill line, nothing hero-only
  G2/G3/G5/G7  replace the combat `is THero` gates with GetAbilityEnabled(0x34)
         via cave_iscaster (units/heroes with Spellcasting pass; walls & non-casters
         fail cleanly with no OOB read)
  G4     same retarget on the strategic-completion gate (inert until Phase 2, but
         harmless and avoids re-touching the site later)

Deliberately NOT done here (later phases):
  - GetPowerGeneration redirect (+0x134)  -> Phase 3 (mana generation)
  - ReadWrite persistence of the cluster   -> Phase 2 (points reset to full each load)
  - strategic ability button / spellbook   -> Phase 2 (needs AoW.exe gates)
  - manual tactical cast button            -> Phase 1b (needs AoWTCPCK.dpl gate)

Rebase-safe by construction (see MovePredictor_Fix notes): the DLL never loads at
its preferred base. Overwritten VMT slots already have .reloc entries; new pointer
values are same-module preferred VAs (relocate correctly). Instance-size words are
plain constants (no reloc). Gate retargets and cave bodies are rel32/register-only
(position independent) -- no absolute memory references anywhere in the caves.

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
BACKUP = os.path.join(BACKUP_DIR, "AoWEPACK.dpl.pre-spellcast")   # current (move-fix) state
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

# ---- game addresses (all verified) -------------------------------------------
TABSU_NEWTURN   = 0x55780D4C     # TAbstractUnit.NewTurn(eax=self, edx=player)
THERO_GETCPMAX  = 0x55788614     # THero.GetCastingPointsMax(eax=self) -> al
ISCLASS_THUNK   = 0x557010C0     # System.@IsClass thunk (current gate call target)

CAVE_BASE = 0x5580D900           # after move-fix cave (ends 0x5580D8A2)

# ---- assemble caves with keystone --------------------------------------------
ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

# cave_iscaster(eax=object) -> al : return object.GetAbilityEnabled(0x34)
ISC = CAVE_BASE
isc_src = """
    mov ecx, [eax]
    mov edx, 0x34
    jmp dword ptr [ecx + 0x148]
"""
isc, _ = ks.asm(isc_src, ISC); isc = bytes(isc)

# cave_unit_newturn(eax=self, edx=player) : TAbstractUnit.NewTurn + point refill
NEWTURN = CAVE_BASE + len(isc)
nt_src = f"""
    push esi
    push edi
    mov  esi, eax
    mov  edi, edx
    mov  eax, esi
    mov  edx, edi
    call 0x{TABSU_NEWTURN:X}
    mov  eax, edi
    and  eax, 0xFF
    movzx ecx, byte ptr [esi + 0x24]
    cmp  ecx, eax
    jne  _done
    mov  eax, esi
    call 0x{THERO_GETCPMAX:X}
    mov  byte ptr [esi + 0x80], al
_done:
    pop  edi
    pop  esi
    ret
"""
nt, _ = ks.asm(nt_src, NEWTURN); nt = bytes(nt)

CAVE = isc + nt

def rel32(src_va, dst_va):
    return struct.pack("<i", dst_va - (src_va + 5))

# ---- patch table: (VA, original_bytes, new_bytes, desc) ----------------------
def vmt(old, new): return struct.pack("<I", old), struct.pack("<I", new)

patches = []
# D1/D2 instance size
patches += [
 (0x55710C90, struct.pack("<I",0x48), struct.pack("<I",0x94), "D1 TUnit instance size 0x48->0x94"),
 (0x55712A38, struct.pack("<I",0x48), struct.pack("<I",0x94), "D2 TAdjustableUnit instance size 0x48->0x94"),
]
# D3-D5 + C1 VMT redirects, TUnit (VMT 0x55710CAC) and TAdjustableUnit (0x55712A54)
for tag, vmtbase in (("TUnit",0x55710CAC), ("TAdj",0x55712A54)):
    o,n = vmt(0x5577FDB8, THERO_GETCPMAX);        patches.append((vmtbase+0x128,o,n,f"D3 {tag} +128 GetCastingPointsMax"))
    o,n = vmt(0x5577FDBC, 0x55788644);            patches.append((vmtbase+0x12C,o,n,f"D4 {tag} +12C GetCastingPoints"))
    o,n = vmt(0x5577FDC0, 0x5578864C);            patches.append((vmtbase+0x130,o,n,f"D5 {tag} +130 SetCastingPoints"))
    o,n = vmt(0x55780D4C, NEWTURN);               patches.append((vmtbase+0x13C,o,n,f"C1 {tag} +13C NewTurn->cave"))
# G gates: retarget the `is THero` IsClass call to cave_iscaster
for site,desc in ((0x5576E418,"G2 fcPrefetchCombatCommands"),
                  (0x5576DF17,"G3 CanCastBreachWallSpell"),
                  (0x5577950C,"G5 CombatCastingDone"),
                  (0x557F76EB,"G7 CombatSpell.fcPrefetch"),
                  (0x557794CD,"G4 CastingDone (strategic completion)"),
                  (0x5576DEB7,"G1 SpellCastingAbility.CanActivate (enable button)"),
                  (0x5577A25C,"G6 SpellCastEventLog.Execute (recast handler)")):
    orig = b"\xE8" + rel32(site, ISCLASS_THUNK)
    new  = b"\xE8" + rel32(site, ISC)
    patches.append((site, orig, new, f"{desc} -> cave_iscaster"))
# the cave itself
patches.append((CAVE_BASE, bytes(len(CAVE)), CAVE, "code cave (iscaster + unit_newturn)"))

# ---- report cave -------------------------------------------------------------
print(f"cave_iscaster    @ {ISC:08X}  ({len(isc)} bytes)")
print(f"cave_unit_newturn@ {NEWTURN:08X}  ({len(nt)} bytes)")
print(f"cave total       {len(CAVE)} (0x{len(CAVE):X}) bytes, ends {CAVE_BASE+len(CAVE):08X}")
print("--- cave disassembly ---")
for ins in cs.disasm(CAVE, CAVE_BASE):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<24} {ins.mnemonic} {ins.op_str}")
print()

# ---- verify + apply ----------------------------------------------------------
with open(DPL,'rb') as fh: data = bytearray(fh.read())
secs = load_sections(data)

ok = True; already = 0; topatch = 0
for va, orig, new, desc in patches:
    off = va2off(secs, va)
    cur = bytes(data[off:off+len(orig)])
    if cur == new:
        already += 1
    elif cur == orig:
        topatch += 1
    else:
        print(f"MISMATCH @ {va:08X} ({desc}):")
        print(f"  expected {orig.hex(' ')}")
        print(f"  found    {cur.hex(' ')}")
        ok = False
print(f"{already} already patched, {topatch} to patch, {len(patches)} total")
if not ok:
    print("ABORT: original bytes did not match."); sys.exit(1)
if '--apply' not in sys.argv:
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)

if not os.path.exists(BACKUP):
    os.makedirs(BACKUP_DIR, exist_ok=True); shutil.copyfile(DPL, BACKUP); print(f"Backup written: {BACKUP}")
else:
    print(f"Backup already exists (kept): {BACKUP}")
for va, orig, new, desc in patches:
    off = va2off(secs, va)
    data[off:off+len(new)] = new
    print(f"patched {va:08X}  {desc}")
with open(DPL,'wb') as fh: fh.write(data)
print("AoWEPACK.dpl Phase-1a patched.")
