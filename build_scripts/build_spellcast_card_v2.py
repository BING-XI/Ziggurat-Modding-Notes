#!/usr/bin/env python3
r"""
AoW1 Unit Spellcasting -- UI: casting points in the unit card's Mana cell (safe approach).

Hooks the KNOWN-SAFE upkeep caption-set in the unit-card paint (0x40916A upkeep>0,
0x4091A6 upkeep<=0; both SetGText(eax=UpKeep,edx=str) with the UNIT in EBX and &form in ESI --
proven reachable & non-crashing by the earlier upkeep cave). The cave (a) does the original
UpKeep SetGText, then (b) if the unit has Spellcasting, builds "cur/max" and writes it to the
*Mana* label (field +0x70, L416 = the hero's casting-points cell, with its own viewport -- no
clipping). The game's own Mana/CP writer (0x408824) is gated off for units, so no conflict; for
heroes it writes the same value first and we harmlessly rewrite it.

Avoids the entangled is-THero gate at 0x407E43 (which crashed: object there isn't always a unit,
and flipping edi breaks the paint's hero assumptions).

Cave in a new executable ".sc" section (no inline slack). Game imports: IntToStr 0x4013AC,
@LStrCatN 0x401128, @LStrArrayClr 0x4010E0, SetGText 0x403254, "/" literal 0x404234.
Idempotent, verify-before-write, backs up first.
Targets the canonical mod exes in `Ziggurat\` (names from `zigexe.py`).
⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)
Usage: [AoWz.exe|AoWzCompat.exe] [--apply]
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                       # mod binary names (AoWz.exe / AoWzCompat.exe)
EXE_NAME=next((a for a in sys.argv[1:] if not a.startswith('--')),zigexe.GAME_EXE)
EXE=os.path.join(GAME,EXE_NAME)
BACKUP_DIR = os.path.join(GAME, "backups")   # ⚠ backups/, never the game root -- rule 2026-09-03
# reached only after the ".sc section present" early-exit, i.e. proved unpatched.
BACKUP=os.path.join(BACKUP_DIR, EXE_NAME+".pre-cardv2")
IB=0x00400000
INTTOSTR=0x4013AC; LSTRCATN=0x401128; LSTRARRCLR=0x4010E0; SETGTEXT=0x403254; SLASH=0x404234
HOOK1=0x0040916A; HOOK2=0x004091A6
MANA_FIELD=0x70

def load_sections(d):
    e=struct.unpack_from('<I',d,0x3C)[0]; nsec=struct.unpack_from('<H',d,e+6)[0]
    optsz=struct.unpack_from('<H',d,e+20)[0]; opt=e+24; sectbl=opt+optsz; secs=[]
    for i in range(nsec):
        b=sectbl+i*40; vsz,va,rsz,raw=struct.unpack_from('<IIII',d,b+8); secs.append((va,vsz,raw,rsz,b))
    return dict(e=e,nsec=nsec,opt=opt,salign=struct.unpack_from('<I',d,opt+32)[0],
                falign=struct.unpack_from('<I',d,opt+36)[0],sectbl=sectbl,secs=secs)
def align(x,a): return (x+a-1)//a*a
def va2off(secs,va):
    r=va-IB
    for va0,vsz,raw,rsz,_ in secs:
        if va0<=r<va0+max(vsz,rsz): return raw+(r-va0)
    raise ValueError(hex(va))

d=bytearray(open(EXE,'rb').read()); F=load_sections(d)
newva=align(max(s[0]+max(s[1],s[3]) for s in F['secs']), F['salign'])
newraw=align(len(d), F['falign']); CAVE=IB+newva
ks=Ks(KS_ARCH_X86,KS_MODE_32); cs=Cs(CS_ARCH_X86,CS_MODE_32)
src=f"""
    push ebp
    mov  ebp, esp
    sub  esp, 0x0C
    call 0x{SETGTEXT:X}
    xor  eax, eax
    mov  [ebp-4], eax
    mov  [ebp-8], eax
    mov  [ebp-0x0C], eax
    mov  eax, ebx
    mov  ecx, [ebx]
    mov  edx, 0x34
    call dword ptr [ecx+0x148]
    test al, al
    jz   cdone
    mov  eax, [esi]
    mov  eax, [eax+0x70]
    mov  dl, 1
    mov  ecx, [eax]
    call dword ptr [ecx+0x6c]
    mov  eax, ebx
    mov  ecx, [ebx]
    call dword ptr [ecx+0x12C]
    movsx eax, al
    lea  edx, [ebp-4]
    call 0x{INTTOSTR:X}
    mov  eax, ebx
    mov  ecx, [ebx]
    call dword ptr [ecx+0x128]
    movsx eax, al
    lea  edx, [ebp-8]
    call 0x{INTTOSTR:X}
    push dword ptr [ebp-4]
    push 0x{SLASH:X}
    push dword ptr [ebp-8]
    lea  eax, [ebp-0x0C]
    mov  edx, 3
    call 0x{LSTRCATN:X}
    mov  edx, [ebp-0x0C]
    mov  eax, [esi]
    mov  eax, [eax+0x{MANA_FIELD:X}]
    call 0x{SETGTEXT:X}
    mov  eax, [esi]
    mov  eax, [eax+0x6c]
    mov  dl, 1
    mov  ecx, [eax]
    call dword ptr [ecx+0x6c]
    lea  eax, [ebp-0x0C]
    mov  edx, 3
    call 0x{LSTRARRCLR:X}
cdone:
    mov  esp, ebp
    pop  ebp
    ret
"""
src='\n'.join(l.split(';')[0] for l in src.splitlines())
code=bytes(ks.asm(src, CAVE)[0])
secdata=code
print(f"cave @ {CAVE:08X}  {len(code)}B")
for ins in cs.disasm(code,CAVE): print(f"  {ins.address:08X} {ins.bytes.hex(' '):<20}{ins.mnemonic} {ins.op_str}")
def rel(s,dd): return struct.pack('<i',dd-(s+5))
secs=F['secs']
# idempotency: a prior run added a '.sc' section
if any(bytes(d[s[4]:s[4]+3])==b'.sc' for s in secs):
    print(f"{EXE_NAME}: already patched (.sc section present)."); sys.exit(0)
ok=True
for h in (HOOK1,HOOK2):
    off=va2off(secs,h); cur=bytes(d[off:off+5]); exp=b"\xE8"+rel(h,SETGTEXT)
    if cur!=exp: print(f"HOOK {h:08X} not original SetGText call: {cur.hex(' ')}"); ok=False
if F['sectbl']+F['nsec']*40+40 > F['secs'][0][2]: print("NO header room"); ok=False
print(f"{EXE_NAME}: {'hooks OK, header room OK' if ok else 'PROBLEM'}")
if not ok: print("ABORT"); sys.exit(1)
if '--apply' not in sys.argv: print("Dry run OK. --apply."); sys.exit(0)
if not os.path.exists(BACKUP):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    shutil.copyfile(EXE,BACKUP); print("backup",BACKUP)
if len(d)<newraw: d+=b'\x00'*(newraw-len(d))
rawsz=align(len(secdata),F['falign']); d+=secdata+b'\x00'*(rawsz-len(secdata))
b=F['sectbl']+F['nsec']*40
struct.pack_into('<8sIIII',d,b,b'.sc\0\0\0\0\0',len(secdata),newva,rawsz,newraw)
struct.pack_into('<IIHHI',d,b+24,0,0,0,0,0x60000020)
struct.pack_into('<H',d,F['e']+6,F['nsec']+1)
struct.pack_into('<I',d,F['opt']+56, align(newva+len(secdata),F['salign']))
for h in (HOOK1,HOOK2):
    off=va2off(secs,h); d[off:off+5]=b"\xE8"+rel(h,CAVE)
open(EXE,'wb').write(d)
print(f"{EXE_NAME}: casting points -> Mana cell via upkeep hook.")
