#!/usr/bin/env python3
r"""
AoW1 Unit Spellcasting -- C2: persist a unit's casting state across save/load. AoWEPACK.dpl only.

Problem: TUnit / TAdjustableUnit ReadWrite (the object serializer) does NOT write the casting
cluster, so on load a unit's points reset (to 0 -> refills next turn) and any in-progress channel
is lost. THero.ReadWrite @0x55788880 DOES serialize those fields; we mirror it for units.

The stream is property-table based (`TPropertyTable.PropertyExist`): each field is written with a
numeric TAG; on read a missing tag falls back to a default. So appending new tagged fields is
save-compatible both ways -- old saves lack the tags (units load with cleared casting state), and a
mod-made save loaded by an UNPATCHED game just ignores the extra properties. THero's casting tags
(0xd,0xe,0x1f,0x22,0x23) do NOT collide with TUnit's (7/8/9/0xa) or the base chain
(TAbstractUnit 4/5/6/0x2f, TAbilityOwner 0x31/0x32+) -- verified; they coexist inside THero already.

Fields persisted (exactly THero's tagged calls, transcribed): +0x80 points (byte, tag 0xd,
stream vtable+0x30); +0x84 spell-in-progress id (int, 0xe, +0x2c); +0x88 progress (int, 0x1f,
+0x2c); +0x8c mana required (int, 0x22, +0x2c); +0x90 ready-event id (int, default -1, tag 0x23,
+0x40). NOT persisted: +0x7C power-source ptr (THero doesn't persist it either -- runtime only;
units use the player's mana pool, no per-unit power source).

Mechanism: redirect the ReadWrite VMT slot (+0x18) of TUnit and TAdjustableUnit to thin wrappers
that call the ORIGINAL ReadWrite (different per class!) then a shared cave that appends the 5 tagged
casting fields. Register-only / rel32 caves (position independent). TUnit VMT +0x18 = TUnit.ReadWrite
(0x55782CEC); TAdjustableUnit VMT +0x18 = TAbstractUnit.ReadWrite (0x557820E4).

Independent of M1/M2 (persistence works with or without multi-turn). Requires Phase-1 (grown
instances). Backup AoWEPACK.dpl.pre-persist. Idempotent, verify-before-write. Dry-run / --apply.
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
BACKUP = os.path.join(BACKUP_DIR, "AoWEPACK.dpl.pre-persist")     # = state before C2 (i.e. M1+M2 applied)
IMAGE_BASE = 0x55700000

TUNIT_RW = 0x55782CEC     # TUnit.ReadWrite            (TUnit VMT +0x18)
TABSU_RW = 0x557820E4     # TAbstractUnit.ReadWrite    (TAdjustableUnit VMT +0x18)
TUNIT_VMT = 0x55710CAC
TADJ_VMT  = 0x55712A54
PERSIST_BASE = 0x5580D990  # free zero space after the M2 tiergate cave (ends 0x5580D98D)

def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]; nsec = struct.unpack_from("<H", data, e+6)[0]
    opt = e+24; optsize = struct.unpack_from("<H", data, e+20)[0]; sec = opt+optsize; secs=[]
    for i in range(nsec):
        vsize,vaddr,rsize,raw = struct.unpack_from("<IIII", data, sec+8); secs.append((vaddr,vsize,raw,rsize)); sec+=40
    return secs
def va2off(secs, va):
    rva = va - IMAGE_BASE
    for vaddr,vsize,raw,rsize in secs:
        if vaddr <= rva < vaddr+max(vsize,rsize): return raw+(rva-vaddr)
    raise ValueError(f"VA {va:08X} not in any section")

ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

# shared: append the 5 casting fields (in: edi=self, esi=stream) -- exact transcription of THero.
CF = PERSIST_BASE
cf_src = """
    lea edx, [edi+0x80]
    mov ecx, 0xd
    mov eax, esi
    mov ebx, [eax]
    call dword ptr [ebx+0x30]
    lea edx, [edi+0x84]
    mov ecx, 0xe
    mov eax, esi
    mov ebx, [eax]
    call dword ptr [ebx+0x2c]
    lea edx, [edi+0x88]
    mov ecx, 0x1f
    mov eax, esi
    mov ebx, [eax]
    call dword ptr [ebx+0x2c]
    lea edx, [edi+0x8c]
    mov ecx, 0x22
    mov eax, esi
    mov ebx, [eax]
    call dword ptr [ebx+0x2c]
    push 0x23
    lea edx, [edi+0x90]
    or ecx, 0xffffffff
    mov eax, esi
    mov ebx, [eax]
    call dword ptr [ebx+0x40]
    ret
"""
cf = bytes(ks.asm(cf_src, CF)[0])

def wrapper_src(orig):
    return f"""
    push edi
    push esi
    push ebx
    mov edi, eax
    mov esi, edx
    call 0x{orig:X}
    call 0x{CF:X}
    pop ebx
    pop esi
    pop edi
    ret
"""
RT = CF + len(cf)                       # cave_rw_tunit
rt = bytes(ks.asm(wrapper_src(TUNIT_RW), RT)[0])
RA = RT + len(rt)                       # cave_rw_tadj
ra = bytes(ks.asm(wrapper_src(TABSU_RW), RA)[0])

BLOB = cf + rt + ra
CAVE_END = CF + len(BLOB)

print(f"cave_cast_fields @ {CF:08X} ({len(cf)}B)")
print(f"cave_rw_tunit    @ {RT:08X} ({len(rt)}B) -> calls TUnit.ReadWrite {TUNIT_RW:08X}")
print(f"cave_rw_tadj     @ {RA:08X} ({len(ra)}B) -> calls TAbstractUnit.ReadWrite {TABSU_RW:08X}")
print(f"blob {len(BLOB)}B, ends {CAVE_END:08X}")
for ins in cs.disasm(BLOB, CF):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<22} {ins.mnemonic} {ins.op_str}")
print()

def ptr(v): return struct.pack("<I", v)
patches = [
    (CF, bytes(len(BLOB)), BLOB, "C2 persist caves (cast_fields + 2 RW wrappers)"),
    (TUNIT_VMT+0x18, ptr(TUNIT_RW), ptr(RT), "C2 TUnit  +0x18 ReadWrite -> wrapper"),
    (TADJ_VMT +0x18, ptr(TABSU_RW), ptr(RA), "C2 TAdj   +0x18 ReadWrite -> wrapper"),
]

with open(DPL,'rb') as fh: data = bytearray(fh.read())
secs = load_sections(data)
def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
if rd(0x55710C90,4) != struct.pack("<I",0x94):
    print("ABORT: Phase 1 not applied (TUnit instance size != 0x94)."); sys.exit(1)

ok=True; already=0; topatch=0
for va,orig,new,desc in patches:
    cur = rd(va, len(orig))
    if cur==new: already+=1
    elif cur==orig: topatch+=1
    else:
        print(f"MISMATCH @ {va:08X} ({desc}): exp {orig.hex(' ')} found {cur.hex(' ')}"); ok=False
print(f"{already} already, {topatch} to patch, {len(patches)} total")
if not ok: print("ABORT."); sys.exit(1)
if '--apply' not in sys.argv:
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)
if not os.path.exists(BACKUP): os.makedirs(BACKUP_DIR, exist_ok=True); shutil.copyfile(DPL, BACKUP); print(f"Backup written: {BACKUP}")
else: print(f"Backup exists (kept): {BACKUP}")
for va,orig,new,desc in patches:
    o=va2off(secs,va); data[o:o+len(new)]=new; print(f"patched {va:08X}  {desc}")
with open(DPL,'wb') as fh: fh.write(data)
print("AoWEPACK.dpl casting-state save/load persistence patched.")
