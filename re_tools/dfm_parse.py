import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pescan import PE
from zignames import zigexe
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
pe=PE(os.path.join(GAME,zigexe.GAME_EXE)); data=pe.data

def rstr(off):
    n=data[off]; return data[off+1:off+1+n].decode('latin1'), off+1+n
def i8(o): return struct.unpack_from('<b',data,o)[0]
def i16(o): return struct.unpack_from('<h',data,o)[0]
def i32(o): return struct.unpack_from('<i',data,o)[0]

def read_value(off):
    vt=data[off]; off+=1
    if vt==0: return None, off
    if vt==2: return i8(off), off+1
    if vt==3: return i16(off), off+2
    if vt==4: return i32(off), off+4
    if vt==5: return ('ext',), off+10
    if vt==6:  # vaString shortstr
        s,off=rstr(off); return s, off
    if vt==7:  # vaIdent
        s,off=rstr(off); return ('id',s), off
    if vt==8: return False, off
    if vt==9: return True, off
    if vt==10:  # vaBinary
        n=i32(off); off+=4; return ('bin',n), off+n
    if vt==11:  # vaSet
        items=[]
        while True:
            s,off=rstr(off)
            if s=='' : break
            items.append(s)
        return set(items), off
    if vt==1:  # vaList
        items=[]
        while data[off]!=0:
            v,off=read_value(off); items.append(v)
        return items, off+1
    if vt==12:  # vaLString
        n=i32(off); off+=4; return data[off:off+n].decode('latin1'), off+n
    if vt==15: return ('single',), off+4
    if vt==16: return ('curr',), off+8
    if vt==17: return ('date',), off+8
    if vt==18:  # vaWString
        n=i32(off); off+=4; return ('wstr',), off+2*n
    if vt==13: return None, off  # vaNil
    raise ValueError(f"unknown valuetype {vt} at {off-1:X}")

def parse_obj(off, root=False):
    b=data[off]
    if (b & 0xF0)==0xF0:   # filer flags byte only when high nibble = F
        off+=1
        if b & 0x02:       # ffChildPos -> ReadInteger
            _,off=read_value(off)
    cn,off=rstr(off); nm,off=rstr(off)
    props={}
    while True:
        pn,off=rstr(off)
        if pn=='' : break
        v,off=read_value(off); props[pn]=v
    children=[]
    while data[off]!=0:
        c,off=parse_obj(off); children.append(c)
    off+=1
    return {'class':cn,'name':nm,'props':props,'children':children}, off

def dump(node, depth=0):
    p=node['props']
    geo=f"L{p.get('Left','?')} T{p.get('Top','?')} W{p.get('Width','?')} H{p.get('Height','?')}"
    extra=[]
    for k in ('AutoSize','Alignment','Caption','Visible','Font.Height'):
        if k in p: extra.append(f"{k}={p[k]!r}")
    print("  "*depth + f"{node['class']} {node['name']!r}  {geo}  {' '.join(extra)}")
    for c in node['children']: dump(c,depth+1)

TARGET = int(sys.argv[1],16) if len(sys.argv)>1 else 0x1E8B9C
root,_=parse_obj(TARGET+4, root=True)
print(f"=== form {root['class']} {root['name']!r} (file {TARGET:X}) ===")
dump(root)
