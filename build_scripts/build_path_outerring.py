#!/usr/bin/env python3
r"""
AoW1 mod -- "Path abilities: radius +1, with 25% proc on the OUTER ring only."

Path of Life(0x45)/Decay(0x44)/Frost(0x6d) terraform a disk around the departed hex as a
unit moves (TAbstractUnit.MovedTo @0x55780328 -> map area-callback, radius hard-coded 1).
This expands the disk to radius 2 and makes the NEW outer ring (hex-distance 2) convert only
25% of the time, while the original inner disk (distance <=1) stays 100%.

MECHANISM (reusable "per-hex ring detection" technique):
  1. Radius: three 1-byte edits 6A 01 -> 6A 02 (the `push 1` radius arg at each Path call:
     0x5578044E Life, 0x55780495 Decay, 0x557804DA Frost).
  2. Center stash: hook MovedTo @0x5578041E (just after the not-transported gate, [EBP-4] =
     the departed/center hex). cave_stash writes center x/y (field+0x10/+0x11) to a 2-byte
     scratch in the cave region (moves are single-threaded -> a scratch global is safe), then
     replays the displaced `mov eax,[ebp-4]; cmp byte[eax+0x12],0` and continues.
  3. Proc-gate: the three per-hex terrain callbacks are re-pointed (their pushed pointers have
     .reloc, so writing the cave's preferred VA rebases correctly) to caves that compute the
     hex's ring: HN = dHXtoHN(cx,cy, field.x,field.y) (@0x557026A4; EAX=x1,EDX=y1,ECX=x2,push
     y2 -> EAX=spiral index; HN<7 = center+inner-ring, HN 7..18 = outer ring 2). If inner ->
     run the real callback (100%). If outer -> roll AoWHSMap.Random(map,4) (@0x5577827C, the
     SYNCED RNG -- correct for MP determinism during move execution); on 0 (25%) run it, else
     skip (leave terrain unchanged). Frost's separate spawn-notify (0x5578024C) is self-gating
     (only spawns FrozenWater when the hex actually became ice), so it needs no gate.

Position-independent (scratch + map read via call/pop-delta; dHXtoHN/Random via rel32; real
callbacks via rel32). Caves at 0x5580DD20 (clear of the lifesteal caves ending ~0x5580DD0E).
Idempotent, verify-before-write, dry-run default / --apply. Snapshot goes to
`<game dir>\backups\AoWEPACK.dpl.pre-pathring`.

Revert: there is no --undo flag here. Undo by hand -- restore each hook site's ORIG bytes and zero
the 0x5580DD20 caves. A `.pre-*` restore is NOT a revert path: it is a whole-file copy that drops
every feature applied since, and there is no snapshot layer left at all.

⚠ build_path_sand.py DEPENDS on this patch: its proc_sand reuses this mod's callback/scratch layout,
so undoing this one breaks Path of Sand too.

NOTE: if AoWHSMap.Random trips its "Invalid ... use" guard here (shouldn't -- move execution is
synchronised), switch the outer roll to the flag-suppress trick (see aow1-terrain memory).
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never the game root (rule 2026-09-03)
ks=Ks(KS_ARCH_X86,KS_MODE_32); cs=Cs(CS_ARCH_X86,CS_MODE_32)

def load_sections(data):
    e=struct.unpack_from("<I",data,0x3C)[0]; n=struct.unpack_from("<H",data,e+6)[0]
    op=struct.unpack_from("<H",data,e+20)[0]; s=e+24+op; secs=[]
    for i in range(n):
        vs,va,rs,raw=struct.unpack_from("<IIII",data,s+8); secs.append((va,vs,raw,rs)); s+=40
    return secs
def mkva2off(base):
    def f(secs,va):
        rva=va-base
        for va0,vs,raw,rs in secs:
            if va0<=rva<va0+max(vs,rs): return raw+(rva-va0)
        raise ValueError(hex(va))
    return f
def rel32(src,dst): return struct.pack("<i",dst-(src+5))

DLL_BASE=0x55700000
DHXTOHN=0x557026A4; RANDOM=0x5577827C; MAPPTR=0x558FA040
INNER_MAX=7          # RadToHN(1): HN<7 = inner (rings 0-1); >=7 = outer ring 2
DENOM=4              # 1/DENOM = 25% proc on the outer ring
RADIUS_SITES=[0x5578044E,0x55780495,0x557804DA]     # 6A 01 -> 6A 02
STASH_INJ=0x5578041E; STASH_ORIG=bytes.fromhex("8b 45 fc 80 78 12 00"); STASH_CONT=0x55780425
CB=[(0x55780452,0x557801A4,"Life"),(0x55780499,0x557801C4,"Decay"),(0x557804DE,0x557801E4,"Frost")]
PH_CX=0x71111117; PH_CY=0x72222227; PH_MAP=0x73333337

# Scratch MUST be in a WRITABLE section -- the CODE section (0x557xxxxx/0x558xxxxx caves) is
# read-only at runtime (flags 0x60000020), so a write there faults ("Exception ... TArmyDefaultMoveTE").
# BSS (0x558EA000, flags 0xC0000000=WRITE) page-rounds to 0x558FB000; 0x558FA800 is committed, zeroed,
# and past the declared vsize (0x10231 -> ends 0x558FA231) so it's unused by the game. Addressed from
# the caves via call/pop-delta (BSS & CODE share the rebase delta -> constant offset).
SCRATCH=0x558FA800; SX=SCRATCH+0; SY=SCRATCH+1        # 2 scratch bytes in BSS slack (writable)
CAVE_STASH=0x5580DD30

def patch(code, va, pop_op, disps):     # anchor = E8 <rel0> <pop_op>; patch call->next + placeholder disps
    code=bytearray(code)
    i=next(k for k in range(len(code)-5) if code[k]==0xE8 and code[k+5]==pop_op)
    anchor=va+i+5; code[i+1:i+5]=struct.pack("<i",0)
    for ph,tgt in disps:
        hits=[k for k in range(len(code)-3) if code[k:k+4]==struct.pack("<I",ph)]
        assert len(hits)==1, f"placeholder {ph:#x} found {len(hits)}x"
        code[hits[0]:hits[0]+4]=struct.pack("<i",tgt-anchor)
    return bytes(code)

# ---- cave_stash: write center x/y to scratch, replay displaced, jmp back ----
stash_src=f"""
    mov eax, [ebp-4]
    movzx ecx, byte ptr [eax+0x10]
    movzx edx, byte ptr [eax+0x11]
    call 0x{CAVE_STASH:X}
    pop eax
    mov byte ptr [eax + 0x{PH_CX:X}], cl
    mov byte ptr [eax + 0x{PH_CY:X}], dl
    mov eax, [ebp-4]
    cmp byte ptr [eax+0x12], 0
    jmp 0x{STASH_CONT:X}
"""
cave_stash=patch(bytes(ks.asm(stash_src,CAVE_STASH)[0]),CAVE_STASH,0x58,[(PH_CX,SX),(PH_CY,SY)])

# ---- proc-gates (one per Path callback); ring-detect + 25% outer roll ----
def make_proc(va, real_cb):
    src=f"""
        push ebx
        push eax
        push edx
        push ecx
        call 0x{va:X}
        pop ebx
        mov edx, [esp+4]
        movsx eax, byte ptr [edx+0x11]
        push eax
        movsx ecx, byte ptr [edx+0x10]
        movsx edx, byte ptr [ebx + 0x{PH_CY:X}]
        movsx eax, byte ptr [ebx + 0x{PH_CX:X}]
        call 0x{DHXTOHN:X}
        cmp eax, {INNER_MAX}
        jl _proc
        mov eax, [ebx + 0x{PH_MAP:X}]
        mov edx, {DENOM}
        call 0x{RANDOM:X}
        test eax, eax
        jnz _skip
    _proc:
        pop ecx
        pop edx
        pop eax
        pop ebx
        jmp 0x{real_cb:X}
    _skip:
        pop ecx
        pop edx
        pop eax
        pop ebx
        ret
    """
    return patch(bytes(ks.asm(src,va)[0]),va,0x5B,[(PH_CX,SX),(PH_CY,SY),(PH_MAP,MAPPTR)])

CAVE_LIFE=(CAVE_STASH+len(cave_stash)+0xF)&~0xF
proc_life=make_proc(CAVE_LIFE,0x557801A4)
CAVE_DECAY=(CAVE_LIFE+len(proc_life)+0xF)&~0xF
proc_decay=make_proc(CAVE_DECAY,0x557801C4)
CAVE_FROST=(CAVE_DECAY+len(proc_decay)+0xF)&~0xF
proc_frost=make_proc(CAVE_FROST,0x557801E4)
PROC_VA={"Life":CAVE_LIFE,"Decay":CAVE_DECAY,"Frost":CAVE_FROST}

patches=[(CAVE_STASH,bytes(len(cave_stash)),cave_stash,"cave_stash"),
         (CAVE_LIFE,bytes(len(proc_life)),proc_life,"proc_life"),
         (CAVE_DECAY,bytes(len(proc_decay)),proc_decay,"proc_decay"),
         (CAVE_FROST,bytes(len(proc_frost)),proc_frost,"proc_frost"),
         (STASH_INJ,STASH_ORIG,b"\xE9"+rel32(STASH_INJ,CAVE_STASH)+b"\x90\x90","MovedTo -> cave_stash")]
for va in RADIUS_SITES:
    patches.append((va,b"\x6a\x01",b"\x6a\x02",f"radius +1 @ {va:08X}"))
for site,real,name in CB:
    patches.append((site,struct.pack("<I",real),struct.pack("<I",PROC_VA[name]),f"{name} callback -> proc_{name.lower()}"))

for nm,va,cave in [("cave_stash",CAVE_STASH,cave_stash),("proc_life",CAVE_LIFE,proc_life),
                   ("proc_decay",CAVE_DECAY,proc_decay),("proc_frost",CAVE_FROST,proc_frost)]:
    print(f"{nm} @ {va:08X} ({len(cave)} B)")
    for ins in cs.disasm(cave,va): print(f"  {ins.address:08X} {ins.bytes.hex(' '):<20}{ins.mnemonic} {ins.op_str}")

APPLY="--apply" in sys.argv
def process(path,base,patches,suffix=".pre-pathring"):
    data=bytearray(open(path,"rb").read()); secs=load_sections(data); va2off=mkva2off(base)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
    if all(rd(va,len(new))==new for va,_o,new,_d in patches):
        print(f"[= ] {os.path.basename(path)}: already applied"); return True
    ok=True
    for va,orig,new,desc in patches:
        cur=rd(va,len(new))
        if cur!=orig and cur!=new: ok=False; print(f"[!] {va:08X} ({desc})\n     exp {orig.hex(' ')}\n     got {cur.hex(' ')}")
    if not ok: print("[x] mismatch -- not written"); return False
    if not APPLY: print("[dry] originals verified"); return True
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bp=os.path.join(BACKUP_DIR, os.path.basename(path)+suffix)
    if not os.path.exists(bp): shutil.copy2(path,bp); print(f"[bak] {bp}")
    for va,orig,new,desc in patches:
        o=va2off(secs,va); data[o:o+len(new)]=new; print(f"[w ] {va:08X} {desc}")
    try: open(path,"wb").write(data)
    except PermissionError: print("[x] LOCKED -- close AoW binaries"); return False
    return True

print()
ok=process(os.path.join(GAME,"AoWEPACK.dpl"),DLL_BASE,patches)
print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first." if not APPLY
      else ("\n[done] Applied. Revert: no --undo here -- restore the ORIG hook byte-runs and zero the"
            "\n       0x5580DD20 caves by hand. A .pre-* restore is not a revert path." if ok else "\n[!] not applied"))
