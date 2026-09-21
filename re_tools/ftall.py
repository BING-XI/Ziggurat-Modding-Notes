import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pescan import PE
from zignames import zigexe
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
pe=PE(os.path.join(GAME,zigexe.GAME_EXE)); base=pe.image_base; data=pe.data
def va2off(va): return pe.rva2off(va-base)
def vu32(va):
    o=va2off(va); return struct.unpack_from('<I',data,o)[0] if o is not None else None
VMT=int(sys.argv[1],16)
ft=vu32(VMT-0x2C); o=va2off(ft); count=struct.unpack_from('<H',data,o)[0]; p=o+6
print(f"VMT {VMT:08X} fieldtable {ft:08X} count {count}")
for i in range(count):
    offv=struct.unpack_from('<I',data,p)[0]; idx=struct.unpack_from('<H',data,p+4)[0]
    nlen=data[p+6]; nm=data[p+7:p+7+nlen].decode('latin1','replace')
    print(f"  +0x{offv:03X} = {nm}")
    p+=7+nlen
