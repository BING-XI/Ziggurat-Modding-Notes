#!/usr/bin/env python3
"""
AoW1 Unit Spellcasting -- Phase 1b: manual/tactical combat cast gate, AoWTCPCK.dpl.

The tactical combat screen gates the "can this unit cast" logic on `is THero`.
Four sites, each already scoped to the Spellcasting ability:
    cmp [ebp-X], 0x34            ; ability id == Spellcasting
    jne skip
    mov eax, [combatUnit+0x4C]   ; the STRATEGIC unit backing the combat unit
    mov edx, [THero classref]
    call @IsClass (0x401058)     ; <-- retarget to cave_iscaster
    ...THero.CanCastSpellInstantly...
Retargeting each call to a TCPCK-local cave_iscaster (return obj.GetAbilityEnabled(0x34))
lets units with Spellcasting pass, exactly like the AoWEPACK combat gates. The gated
object is a TAbstractUnit descendant, so vtable+0x148 (GetAbilityEnabled) is valid.
No behaviour change for heroes (a hero with Spellcasting still passes; one without it
couldn't cast anyway).

Requires the AoWEPACK Phase-1a patch (instance growth etc.) to be applied too.
Rebase-safe: gate calls are rel32 (PIC); cave is register/immediate-only (PIC).
Idempotent, verifies originals, backs up before writing. Dry-run unless --apply.
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DPL    = os.path.join(GAME, "AoWTCPCK.dpl")
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here
BACKUP = os.path.join(BACKUP_DIR, "AoWTCPCK.dpl.pre-spellcast")
IMAGE_BASE = 0x00400000
ISCLASS = 0x00401058              # TCPCK System.@IsClass thunk
CAVE_BASE = 0x00438100            # inside 191 KB zero run at 0x438080

def load_sections(data):
    e=struct.unpack_from("<I",data,0x3C)[0]
    nsec=struct.unpack_from("<H",data,e+6)[0]
    optsize=struct.unpack_from("<H",data,e+20)[0]
    sec=e+24+optsize; secs=[]
    for i in range(nsec):
        vsize,vaddr,rsize,raw=struct.unpack_from("<IIII",data,sec+8)
        secs.append((vaddr,vsize,raw,rsize)); sec+=40
    return secs
def va2off(secs,va):
    rva=va-IMAGE_BASE
    for vaddr,vsize,raw,rsize in secs:
        if vaddr<=rva<vaddr+max(vsize,rsize): return raw+(rva-vaddr)
    raise ValueError(hex(va))

# reloc set (dir 5)
def reloc_set(data,secs):
    e=struct.unpack_from("<I",data,0x3C)[0]; opt=e+24
    nrva=struct.unpack_from("<I",data,opt+92)[0]
    rva,size=struct.unpack_from("<II",data,opt+96+5*8)
    off=va2off(secs,IMAGE_BASE+rva); end=off+size; p=off; out=set()
    while p<end-8:
        page,blk=struct.unpack_from("<II",data,p)
        if blk==0: break
        for i in range((blk-8)//2):
            ent=struct.unpack_from("<H",data,p+8+i*2)[0]
            if ent>>12==3: out.add(IMAGE_BASE+page+(ent&0xFFF))
        p+=blk
    return out

ks=Ks(KS_ARCH_X86,KS_MODE_32); cs=Cs(CS_ARCH_X86,CS_MODE_32)
isc,_=ks.asm("mov ecx,[eax]\n mov edx,0x34\n jmp dword ptr [ecx+0x148]", CAVE_BASE)
CAVE=bytes(isc)
def rel32(src,dst): return struct.pack("<i", dst-(src+5))

GATE_CALLS=[0x00418739,0x00418B86,0x00418F71,0x004195D4]
patches=[]
for site in GATE_CALLS:
    patches.append((site, b"\xE8"+rel32(site,ISCLASS), b"\xE8"+rel32(site,CAVE_BASE),
                    f"tactical cast gate @ {site:08X} -> cave_iscaster"))
patches.append((CAVE_BASE, bytes(len(CAVE)), CAVE, "cave_iscaster"))

print("cave:")
for ins in cs.disasm(CAVE,CAVE_BASE): print(f"  {ins.address:08X} {ins.bytes.hex(' '):<18}{ins.mnemonic} {ins.op_str}")

with open(DPL,'rb') as fh: data=bytearray(fh.read())
secs=load_sections(data); rl=reloc_set(data,secs)
# safety: gate calls + cave must not be relocated
for site in GATE_CALLS+[CAVE_BASE, CAVE_BASE+0x4]:
    if (site+1 if site in GATE_CALLS else site) in rl:
        print(f"WARN reloc at {site:08X}")
ok=True; already=0; topatch=0
for va,orig,new,desc in patches:
    off=va2off(secs,va); cur=bytes(data[off:off+len(orig)])
    if cur==new: already+=1
    elif cur==orig: topatch+=1
    else:
        print(f"MISMATCH @ {va:08X} ({desc}):\n  exp {orig.hex(' ')}\n  got {cur.hex(' ')}"); ok=False
print(f"{already} already, {topatch} to patch, {len(patches)} total")
if not ok: print("ABORT"); sys.exit(1)
if '--apply' not in sys.argv: print("\nDry run OK. --apply to write."); sys.exit(0)
if not os.path.exists(BACKUP): os.makedirs(BACKUP_DIR, exist_ok=True); shutil.copyfile(DPL,BACKUP); print(f"Backup: {BACKUP}")
else: print(f"Backup kept: {BACKUP}")
for va,orig,new,desc in patches:
    off=va2off(secs,va); data[off:off+len(new)]=new; print(f"patched {va:08X} {desc}")
with open(DPL,'wb') as fh: fh.write(data)
print("AoWTCPCK.dpl Phase-1b patched.")
