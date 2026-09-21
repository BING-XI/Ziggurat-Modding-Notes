import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pescan import PE
from zignames import zigexe
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
pe=PE(os.path.join(GAME,zigexe.GAME_EXE)); base=pe.image_base; data=pe.data
def off2va(off):
    for nm,vaddr,vsize,raw,rsize in pe.sections:
        if raw<=off<raw+rsize: return base+vaddr+(off-raw)
    return None
def va2off(va): return pe.rva2off(va-base)
def vu32(va):
    o=va2off(va); return struct.unpack_from('<I',data,o)[0] if o is not None else None
def shortstr(va):
    o=va2off(va)
    if o is None: return None
    n=data[o]; return data[o+1:o+1+n].decode('latin1','replace')

# 1. enumerate VMT bases in CODE via self-ptr at V-0x40
CODE=None
for nm,vaddr,vsize,raw,rsize in pe.sections:
    if nm=='CODE': CODE=(vaddr,vsize,raw,rsize)
vaddr,vsize,raw,rsize=CODE
vmts=[]
for off in range(raw, raw+min(vsize,rsize)-4, 4):
    va=base+vaddr+(off-raw)
    self_=struct.unpack_from('<I',data,off)[0]
    if self_==va+0x40:  # this dword is vmtSelfPtr, so VMT base = va+0x40
        vmt=va+0x40
        cn=shortstr(vu32(vmt-0x20) or 0)
        vmts.append((vmt,cn))
vmts.sort()
print(f"{len(vmts)} VMTs found")

def enclosing(occ_va):
    best=None
    for vmt,cn in vmts:
        if vmt<=occ_va: best=(vmt,cn)
        else: break
    return best

def fieldmap(vmt):
    ft=vu32(vmt-0x2C)
    if not ft: return {}
    o=va2off(ft); count=struct.unpack_from('<H',data,o)[0]; p=o+6; m={}
    for i in range(count):
        offv=struct.unpack_from('<I',data,p)[0]; idx=struct.unpack_from('<H',data,p+4)[0]
        nlen=data[p+6]; nm=data[p+7:p+7+nlen].decode('latin1','replace')
        m[offv]=nm; p+=7+nlen
    return m

import re
RX=re.compile(r'cost|upkeep|cast|mana|point|\bcp\b|gold|move|attack|defen|hit|resist|damage|name|spell|channel|diamond', re.I)
seen=set()
for target in (0x00403F60,0x00433A40,0x00408F6C,0x0045896D):
    needle=struct.pack('<I',target); q=0
    found=False
    while True:
        k=data.find(needle,q)
        if k<0: break
        q=k+1
        va=off2va(k)
        if va is None or not (base+vaddr<=va<base+vaddr+vsize): continue
        enc=enclosing(va)
        if not enc: continue
        vmt,cn=enc
        if va-vmt<0 or va-vmt>0x400: continue
        if (target,vmt) in seen: continue
        seen.add((target,vmt)); found=True
        print(f"\n=== paint {target:08X} -> class {cn!r} (VMT {vmt:08X}, moff +0x{va-vmt:X}) ===")
        fm=fieldmap(vmt)
        for offv in sorted(fm):
            if RX.search(fm[offv]):
                print(f"    +0x{offv:X} = {fm[offv]!r}")
        break
    if not found:
        print(f"\n{target:08X}: no enclosing VMT")
