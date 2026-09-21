import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pescan import PE
from zignames import zigexe
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
cs = Cs(CS_ARCH_X86, CS_MODE_32); cs.detail=True; cs.skipdata=True
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
pe=PE(os.path.join(GAME,zigexe.GAME_EXE)); base=pe.image_base
for nm,vaddr,vsize,raw,rsize in pe.sections:
    if nm in ('CODE','.text'): CODE=(vaddr,vsize,raw,rsize)
vaddr,vsize,raw,rsize=CODE; code=pe.data[raw:raw+min(vsize,rsize)]; cbase=base+vaddr
def iat_map():
    iat={}; rva_dir,_=pe.dirs[1]; i=0
    while True:
        ent=pe.read(rva_dir+i*20,20)
        if ent is None or ent==b"\0"*20: break
        oft,ts,fc,name_rva,ft=struct.unpack("<IIIII",ent); j=0; thunk=oft or ft
        while True:
            v=pe.u32(thunk+j*4)
            if not v: break
            if not (v&0x80000000):
                nm=pe.cstr(v+2,2048)
                if nm: iat[base+ft+j*4]=nm
            j+=1
        i+=1
    return iat
iat=iat_map()
classref=[va for va,nm in iat.items() if 'THero@228E24B5' in nm][0]
stub2name={}
for va,nm in iat.items():
    pat=b"\xFF\x25"+struct.pack("<I",va); p=0
    while True:
        k=code.find(pat,p)
        if k<0: break
        stub2name[cbase+k]=nm; p=k+1
VSLOT={0x128:'GetCastingPointsMax',0x12c:'GetCastingPoints',0x130:'SetCastingPoints',
       0xC0:'GetAttack',0xC4:'GetDefense',0xC8:'GetDamage',0xCC:'GetResistance',
       0xD0:'GetHits',0xD4:'GetMoves',0xD8:'GetMovePoints',0xE0:'GetHitPoints',
       0x148:'GetAbilityEnabled',0x144:'GetAbilityLevel'}
def sn(n):
    n=n.split('@')[0]; return n[5:] if n.startswith('AoWE.') else n
def ann(ins):
    if ins.id==0: return ''
    if ins.mnemonic in('call','jmp') and ins.operands and ins.operands[0].type==1:
        t=ins.operands[0].imm&0xffffffff
        if t in stub2name: return '  ; '+sn(stub2name[t])
        if t==0x401070: return '  ; @IsClass'
    for op in ins.operands:
        if op.type==3:
            m=op.mem
            if m.base!=0 and m.index==0 and (m.disp&0xffffffff) in VSLOT and ins.mnemonic=='call':
                return '  ; ->vtbl.'+VSLOT[m.disp&0xffffffff]+f' (reg {ins.reg_name(m.base)})'
            if m.base==0 and m.index==0:
                d=m.disp&0xffffffff
                if d==classref: return '  ; THero classref'
                if d in iat: return '  ; ['+sn(iat[d])+']'
    return ''
def dump(va, length):
    off=va-cbase
    print(f"\n===== {va:08X}..{va+length:08X} =====")
    for ins in cs.disasm(bytes(code[off:off+length]), va):
        print(f"  {ins.address:08X}  {ins.mnemonic:6s} {ins.op_str}{ann(ins)}")

# scan for vtable casting-point call sites anywhere
print("=== vtable casting-point call sites (FF /2 disp 0x128/0x12C) ===")
for slot in (0x128,0x12c,0x130):
    d4=struct.pack("<I",slot)
    p=0
    while True:
        k=code.find(d4,p)
        if k<0: break
        # check preceding bytes look like FF /2 modrm (call [reg+disp32]) => code[k-2]==0xFF, code[k-1] in 0x90..0x97
        if code[k-2]==0xFF and 0x90<=code[k-1]<=0x97:
            print(f"  {cbase+k-2:08X}  call [reg+0x{slot:X}]  ({VSLOT[slot]})")
        p=k+1

import struct as _s
# find function start (scan back for 55 8B EC = push ebp;mov ebp,esp)
def fstart(va):
    off=va-cbase
    for k in range(off,off-0x600,-1):
        if code[k]==0x55 and code[k+1]==0x8B and code[k+2]==0xEC:
            return cbase+k
    return va
dump(0x4087CC, 0xA0)
