#!/usr/bin/env python3
r"""
!!! SHELVED / DO NOT APPLY (2026-07-07) !!!
Raise Terrain is NOT actually bugged. User tested unmodified vanilla in-game and mountains
already match the underlying terrain. The premise below ("places grass mountains / forces grass")
was an UNVERIFIED inference that turned out wrong -- the mountain rendering/forcing lives in
HSEPack.dpl (never analyzed). This script was only ever dry-run, never applied. Keep it shelved
unless a real per-terrain mismatch is demonstrated in-game. See Terrain_Changing_Spells_Map.md.

AoW1 mod -- "Raise Terrain places the RIGHT mountain for the pre-existing terrain".

Vanilla TRaiseTerrainTE.RaiseTerrain @0x557A3280 always picks the same
TRaisedMountainResource (ClassID 0x2016B, first with UsedTerrain==1) regardless of
the target hex's terrain -- the grass variant -- and PlaceHX (HSEPack) stamps that
resource's terrain (grass) onto the hex. So raised mountains are always grass and
turn the ground to grass.

FIX (user's idea): mountains follow the underlying terrain for their art (that's how
static TMountainMO renders per terrain). So after PlaceHX places the grass mountain,
change the hex terrain back to the pre-existing terrain -- the mountain auto-repaints
to that terrain's mountain variant AND the ground stays correct.

The pre-existing terrain is already saved by vanilla at MO+0x1F (= field+0x15, the
byte RaiseTerrain stores at 0x557A33B6 and TRaisedMountain.RestoreTerrain restores on
expiry). We reuse it. If in-game shows the wrong terrain, switch the source byte to
the true display terrain captured pre-spell (field+0x14).

MECHANISM
  Redirect the 9 bytes at 0x557A3408 (right after the PlaceHX success test):
      8A 43 1C            mov al, [ebx+0x1c]
      0A 05 B4 34 7A 55   or  al, [0x557A34B4]        ; MO anim-flag set (absolute)
  -> E9 <rel32 to cave> + 4x NOP (fills through 0x557A3410; 0x557A3411 = mov [ebx+0x1c],al
     continues untouched). EBX = mountain MO here (vanilla relies on it right after PlaceHX).

  cave_raisemtn (at 0x5580DB40, verified zero space above cave_icelava):
    - map ptr & the [0x557A34B4] flag are read via call/pop-delta -> rebase-safe
      (no fresh absolute refs), per aow1-dpl-rebasing.
    - ChangeTerrainEx(map, 0, x, terrain=MO+0x1F, 0, level, y) mirrored EXACTLY from
      TLevelTerrainTE.LevelTerrain's working call @0x5579F14D (map.vtable+0xD0;
      EAX=map, EDX=0, ECX=x; pushed args y, level, 0, terrain).
      x/y/level from the MO position struct [EBX+4] (+0x10/+0x11/+0x12, as
      TRaisedMountain.RestoreTerrain reads them).
    - ChangeTerrainEx is a Delphi register call: preserves EBX/ESI/EDI/EBP; the anim
      block after 0x557A3411 reloads all volatiles, so clobbering EAX/ECX/EDX/ESI is safe.
      EDI is unused by RaiseTerrain's body, so we use it to hold the call/pop anchor.
    - Then replay `mov al,[ebx+0x1c]; or al,[0x557A34B4]` and jmp 0x557A3411.

Idempotent; verifies originals; backs up to <game dir>\backups\AoWEPACK.dpl.pre-raisemtn;
dry-run by default, --apply.
CAVE HAZARD: this cave sits at 0x5580DB40, above cave_icelava (0x5580DB20). Any whole-file restore
of an AoWEPACK snapshot taken before this patch -- build_icestorm_lava's included -- wipes this
feature along with every other one applied since. That is why a .pre-* restore is not a revert path.
Revert THIS: ** no revert path. ** There is no --undo flag and no snapshot on disk (both stacks were
purged, 2026-08-08 and 2026-09-09). Undo it by hand: restore the patched site's original bytes and
zero the cave at 0x5580DB40.
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e+6)[0]
    optsize = struct.unpack_from("<H", data, e+20)[0]
    sec = e+24+optsize; secs=[]
    for i in range(nsec):
        vsize,vaddr,rsize,raw = struct.unpack_from("<IIII", data, sec+8)
        secs.append((vaddr,vsize,raw,rsize)); sec+=40
    return secs
def mkva2off(base):
    def va2off(secs, va):
        rva = va-base
        for vaddr,vsize,raw,rsize in secs:
            if vaddr <= rva < vaddr+max(vsize,rsize):
                return raw+(rva-vaddr)
        raise ValueError(f"VA {va:08X} not mapped")
    return va2off
def rel32(src, dst): return struct.pack("<i", dst-(src+5))

DLL_BASE   = 0x55700000
INJ        = 0x557A3408                         # mov al,[ebx+0x1c] ; or al,[0x557A34B4]
INJ_ORIG   = bytes.fromhex("8a 43 1c 0a 05 b4 34 7a 55")   # 9 bytes -> through 0x557A3410
CONT       = 0x557A3411                         # mov [ebx+0x1c],al (vanilla continues)
DAT_FLAG   = 0x557A34B4                         # MO anim-flag byte (absolute in vanilla)
MAPPTR     = 0x558E9494                         # *(*MAPPTR) = TAoWHSMap  (has .reloc in vanilla code)
CAVE       = 0x5580DB40                         # zero space, above cave_icelava (ends 0x5580DB33)

ANCHOR = CAVE + 5                               # `call CAVE+5` (E8 00000000) -> pop edi = ANCHOR
disp_map = MAPPTR   - ANCHOR
disp_dat = DAT_FLAG - ANCHOR

cave_src = f"""
    call 0x{ANCHOR:X}
    pop edi
    mov eax, [edi + {disp_map}]
    mov eax, [eax]
    mov edx, [ebx+4]
    movsx ecx, byte ptr [edx+0x11]
    push ecx
    movsx ecx, byte ptr [edx+0x12]
    push ecx
    push 0
    movsx ecx, byte ptr [ebx+0x1f]
    push ecx
    movzx ecx, byte ptr [edx+0x10]
    xor edx, edx
    mov esi, [eax]
    call dword ptr [esi+0xd0]
    mov al, byte ptr [ebx+0x1c]
    or  al, byte ptr [edi + {disp_dat}]
    jmp 0x{CONT:X}
"""
cave, _ = ks.asm(cave_src, CAVE); cave = bytes(cave)
redir = b"\xE9" + rel32(INJ, CAVE) + b"\x90\x90\x90\x90"
assert len(redir) == len(INJ_ORIG) == 9, (len(redir), len(INJ_ORIG))

dll_patches = [
    (CAVE, bytes(len(cave)), cave,  "cave_raisemtn (post-place terrain fix-up)"),
    (INJ,  INJ_ORIG,        redir,  "RaiseTerrain -> cave_raisemtn"),
]

print(f"cave_raisemtn @ {CAVE:08X}  ({len(cave)} B)   disp_map={disp_map:#x} disp_dat={disp_dat:#x}")
for ins in cs.disasm(cave, CAVE):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<20} {ins.mnemonic} {ins.op_str}")
print(f"redirect @ {INJ:08X}: {INJ_ORIG.hex(' ')} -> {redir.hex(' ')}")

APPLY = "--apply" in sys.argv
def process(path, base, patches, backup_suffix=".pre-raisemtn"):
    data = bytearray(open(path,"rb").read())
    secs = load_sections(data); va2off = mkva2off(base)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
    if all(rd(va,len(new))==new for va,_o,new,_d in patches):
        print(f"[= ] {os.path.basename(path)}: already applied"); return True
    ok=True
    for va,orig,new,desc in patches:
        cur=rd(va,len(orig))
        if cur!=orig and cur!=new:
            ok=False; print(f"[!] {va:08X} ({desc})\n     exp {orig.hex(' ')}\n     got {cur.hex(' ')}")
    if not ok:
        print(f"[x] {os.path.basename(path)}: originals mismatch -- not written"); return False
    if not APPLY:
        print(f"[dry] {os.path.basename(path)}: originals verified"); return True
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bpath=os.path.join(BACKUP_DIR, os.path.basename(path)+backup_suffix)
    if not os.path.exists(bpath): shutil.copy2(path,bpath); print(f"[bak] {bpath}")
    for va,orig,new,desc in patches:
        o=va2off(secs,va); data[o:o+len(new)]=new; print(f"[w ] {va:08X} {desc}")
    try: open(path,"wb").write(data)
    except PermissionError:
        print(f"[x] {os.path.basename(path)} LOCKED -- close all AoW binaries and retry"); return False
    return True

path = os.path.join(GAME,"AoWEPACK.dpl")
print()
ok = process(path, DLL_BASE, dll_patches)
if not APPLY:
    print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first.")
elif ok:
    print("\n[done] Applied. Revert: .pre-raisemtn does NOT exist -- undo surgically (zero cave 0x5580DB40).")
else:
    print("\n[!] Not applied -- see above.")
