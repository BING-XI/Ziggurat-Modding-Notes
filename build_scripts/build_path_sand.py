#!/usr/bin/env python3
r"""
AoW1 mod -- ADD A NEW ABILITY: "Path of Sand" (a 4th Path ability).

A moving unit with Path of Sand DRIES the terrain it leaves behind toward Desert, using the SAME
stepwise progression as the user's Desiccate spell (repurposed Rejuvenate, cave FUN_5580c001):
    Grass(1)->Steppe(4);  Snow(3)->Grass(1);  Steppe(4)->Desert(2);  Wasteland(5)->Desert(2);  Dirt(C)->Steppe(4)
(read-once, no cascade -> each proc dries a hex ONE stage; Desert(2) is terminal). Footprint matches
the other three Paths after the outer-ring mod: radius 2, inner disk 100% + 25% proc on the outer ring.

THIS SCRIPT HAS TWO INDEPENDENT HALVES (both position-independent caves, no new DLL):

  A. REGISTRATION -- make the ability EXIST in the engine's ability registry, exactly like the
     vanilla Path abilities are made. In PassiveAb.RegisterPassiveAbilities the three Paths are just:
         obj = CreateEnhancementAbility(id, name, icon);  RegisterAbility(ctrl, obj)
     (CreateEnhancementAbility @0x5576601c: TEnhancementAbility.Create, then obj+0xC=id,
      LStrAsg(obj+8,name), obj+0x20=icon. No special class -- Paths are generic instances.)
     We REPOINT the Path-of-Frost RegisterAbility call @0x557bc9e9 to cave_sandreg, which re-issues
     Frost's registration (the displaced call) and then creates + registers Path of Sand. EBX holds
     the ability-control for the whole function, so RegisterAbility(ctrl=EBX, sand_obj) is trivial.
     Name = a literal Delphi AnsiString (refcount -1 -> LStrAsg shares it, never frees it).
     Icon  = the SAME word the Paths use (*0x557bcfc0) -> Path of Sand looks like a Path ability.
     NEW ID = 0x9F -- a FREE slot inside the vanilla range (see SAND_ID note). The first attempt used
     0xB0 (above vanilla); it registered + listed + assigned in DevEd fine, but did NOTHING in-game
     because unit abilities are a fixed-width bitset (width 0xAA) and 0xB0 is out of range. Must be a
     free id < 0xAA.

  B. BEHAVIOR -- terraform on move. TAbstractUnit.MovedTo @0x55780328 hard-codes each Path as
         if GetAbilityEnabled(unit, ID): map.Flood(VMT+0xd4)(...callback...,radius,...)
     We hook @0x557804b7 (the `MOV EDX,0x6d` that begins the Frost check -- reached for EVERY
     non-transported move, so Sand is an independent 4th Path that never fires while transported).
     cave_sanddispatch does the Sand GetAbilityEnabled + a radius-2 Flood through proc_sand, then
     replays `MOV EDX,0x6d` and continues into the Frost check. proc_sand is the SAME ring-gate as
     the outer-ring mod's proc_life/decay/frost (dHXtoHN vs stashed center; inner 100% / outer 25%
     via synced AoWHSMap.Random), routing to cave_sand_cb -- a clone of PathOfDecayTerrainChange
     (@0x557801c4: ECX=terrain*, EDX=field, RET 4) carrying the Desiccate mapping instead of ->5.

DEPENDS ON build_path_outerring.py BEING APPLIED: proc_sand reuses that mod's
cave_stash (writes the move's centre x/y to BSS scratch 0x558FA800 at MovedTo entry) and its SCRATCH.
The script aborts if the stash hook @0x5578041E isn't present.

Caves at 0x5580DF00+ (clear of the lifesteal @0x5580DC80 and outer-ring @0x5580DD30..~DE80 caves).
Idempotent, verify-before-write, dry-run by default / --apply. Snapshot goes to
`<game dir>\backups\AoWEPACK.dpl.pre-pathsand`.

Revert: there is no --undo flag here. Undo by hand -- restore each hook site's ORIG bytes and zero
the 0x5580DF00 caves. A `.pre-*` restore is NOT a revert path: it is a whole-file copy that drops
every feature applied since, and there is no snapshot layer left at all.

NOTE (visibility): this REGISTERS the ability (name+icon, save-safe) but does NOT assign it to any
unit -- per the user's "register only". Whether it appears in the DevEd ability picker / main-game
unit card is the follow-up "listings" investigation; if a unit is given ability 0xB0 (via DevEd or a
later hard-assign cave), the behavior above fires immediately.
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
def patch(code, va, pop_op, disps):     # anchor = E8 <rel0> <pop_op>; call->next + placeholder disps->(tgt-anchor)
    code=bytearray(code)
    i=next(k for k in range(len(code)-5) if code[k]==0xE8 and code[k+5]==pop_op)
    anchor=va+i+5; code[i+1:i+5]=struct.pack("<i",0)
    for ph,tgt in disps:
        hits=[k for k in range(len(code)-3) if code[k:k+4]==struct.pack("<I",ph)]
        assert len(hits)==1, f"placeholder {ph:#x} found {len(hits)}x"
        code[hits[0]:hits[0]+4]=struct.pack("<i",tgt-anchor)
    return bytes(code)

DLL_BASE=0x55700000
# --- shared engine addresses ---
DHXTOHN=0x557026A4; RANDOM=0x5577827C; MAPPTR=0x558FA040
CREATE_ENH=0x5576601C; REGISTER_ABIL=0x55750238
INNER_MAX=7; DENOM=4                                   # HN<7 inner (100%); outer ring -> Random(map,4)==0 = 25%
SCRATCH=0x558FA800; SX=SCRATCH+0; SY=SCRATCH+1          # centre x/y written by outer-ring cave_stash (BSS, writable)
SAND_ID=0x9F   # A free ability-id slot. CONFIRMED WORKING in-game. (History: the id/bitset-width was a RED
               # HERRING. Abilities are a width-checked bitset -- GetAbilitySet@0x5577f618 `if id<unit+0xC:
               # bit(id) else 0` -- but NOT capped: the setter SetAbSet@0x5574e0bc auto-grows (`if width<=id:
               # SetAbCount(id+1)`) and DevEd persists high ids, so the first try 0xB0 would have worked too.
               # The real "assignable but does nothing" cause was (1) the test unit had the TRANSPORT ability
               # -> MovedTo gates ALL Path abilities off transporter units @0x55780418 (vanilla), and (2)
               # testing on desert/lava, which the Desiccate mapping no-ops. 0x9F is just a clean unused slot
               # (verified vs all four (Un)Register*Abilities lists) that keeps the registry count at 0xAA.
               # Other free ids: 0x21,0x38,0x3B,0x4E-0x55,0x5B,0x66-0x69,0x6E,0x85-0x89,0x97.
ICON_VA=0x557bcfc0                                      # word the Path abilities pass as CreateEnhancementAbility icon

# --- REGISTRATION hook: repoint Path-of-Frost RegisterAbility call ---
FROSTREG_INJ=0x557bc9e9; FROSTREG_ORIG=b"\xE8"+rel32(0x557bc9e9,REGISTER_ABIL)   # call RegisterAbility
# --- BEHAVIOR hook: MovedTo, start of the Frost ability check ---
DISP_INJ=0x557804b7; DISP_ORIG=bytes.fromhex("ba 6d 00 00 00")                   # MOV EDX,0x6d
FROST_CONT=0x557804bc                                                            # continue: MOV EAX,EBX (Frost check)

# --- cave layout (clear of lifesteal + outer-ring caves) ---
CAVE_CB   = 0x5580DF00
PH_PROC=0x61111116; PH_MAP=0x62222226; PH_NAME=0x63333336         # cave_sanddispatch / cave_sandreg sentinels
PH_SX=0x71111117; PH_SY=0x72222227; PH_MP=0x73333337             # proc_sand sentinels (distinct blob)

# cave_sand_cb: clone of TAbstractUnit.PathOfDecayTerrainChange (ECX=terrain*, EDX=field, RET 4),
# carrying the Desiccate progression (read terrain once; exclusive branches = no cascade).
cb_src=f"""
    push ebp
    mov ebp, esp
    movsx eax, byte ptr [ecx]
    cmp ax, 1
    jnz _s3
    mov byte ptr [ecx], 4
    jmp _done
_s3:
    cmp ax, 3
    jnz _s4
    mov byte ptr [ecx], 1
    jmp _done
_s4:
    cmp ax, 4
    jnz _s5
    mov byte ptr [ecx], 2
    jmp _done
_s5:
    cmp ax, 5
    jnz _sc
    mov byte ptr [ecx], 2
    jmp _done
_sc:
    cmp ax, 0xc
    jnz _done
    mov byte ptr [ecx], 4
_done:
    pop ebp
    ret 4
"""
cave_cb=bytes(ks.asm(cb_src,CAVE_CB)[0])

# proc_sand: ring-gate (identical to the outer-ring proc caves) routing to cave_sand_cb.
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
        movsx edx, byte ptr [ebx + 0x{PH_SY:X}]
        movsx eax, byte ptr [ebx + 0x{PH_SX:X}]
        call 0x{DHXTOHN:X}
        cmp eax, {INNER_MAX}
        jl _proc
        mov eax, [ebx + 0x{PH_MP:X}]
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
    return patch(bytes(ks.asm(src,va)[0]),va,0x5B,[(PH_SX,SX),(PH_SY,SY),(PH_MP,MAPPTR)])

CAVE_PROC=(CAVE_CB+len(cave_cb)+0xF)&~0xF
proc_sand=make_proc(CAVE_PROC,CAVE_CB)

# cave_sanddispatch: hooked from MovedTo @0x557804b7. Sand GetAbilityEnabled + radius-2 Flood via
# proc_sand, then replay MOV EDX,0x6d and fall into the Frost check. PIC: proc_sand addr & the map
# pointer are reached via an anchor (call/pop edi) + patched displacements.
CAVE_DISP=(CAVE_PROC+len(proc_sand)+0xF)&~0xF
# DIAGNOSTIC: with --diag, DROP the GetAbilityEnabled gate so the Sand terraform fires on EVERY
# non-transported move (any unit, any faction). Used to isolate "cave works, ability-check is the
# problem" (terrain dries for all units) vs "cave broken" (nothing changes). NOT for normal use.
DIAG="--diag" in sys.argv
_gate = "" if DIAG else f"""
    mov edx, {SAND_ID}
    mov eax, ebx
    mov ecx, [eax]
    call dword ptr [ecx+0x148]
    test al, al
    jz _skip"""
disp_src=f"""{_gate}
    call 0x{CAVE_DISP:X}
    pop edi
    mov eax, [ebp-4]
    movsx eax, byte ptr [eax+0x11]
    push eax
    mov eax, [ebp-4]
    movsx eax, byte ptr [eax+0x12]
    push eax
    push 2
    push ebx
    lea eax, [edi + 0x{PH_PROC:X}]
    push eax
    push 0
    push 0
    mov eax, [ebp-4]
    movsx ecx, byte ptr [eax+0x10]
    xor edx, edx
    mov eax, [edi + 0x{PH_MAP:X}]
    mov esi, [eax]
    call dword ptr [esi+0xd4]
_skip:
    mov edx, 0x6d
    jmp 0x{FROST_CONT:X}
"""
cave_disp=patch(bytes(ks.asm(disp_src,CAVE_DISP)[0]),CAVE_DISP,0x5F,[(PH_PROC,CAVE_PROC),(PH_MAP,MAPPTR)])

# cave_sandreg: hooked by repointing the Frost RegisterAbility call. Re-issue Frost's register (the
# displaced call), then create + register Path of Sand. EAX=ctrl,EDX=frost_obj on entry; EBX=ctrl.
CAVE_REG=(CAVE_DISP+len(cave_disp)+0xF)&~0xF
def build_reg(icon):
    src=f"""
        call 0x{REGISTER_ABIL:X}
        call 0x{CAVE_REG:X}
        pop eax
        lea edx, [eax + 0x{PH_NAME:X}]
        mov ecx, 0x{icon:X}
        mov eax, 0x{SAND_ID:X}
        call 0x{CREATE_ENH:X}
        mov edx, eax
        mov eax, ebx
        call 0x{REGISTER_ABIL:X}
        ret
    """
    return patch(bytes(ks.asm(src,CAVE_REG)[0]),CAVE_REG,0x58,[(PH_NAME,NAME_VA)])
# name blob laid out right after cave_sandreg; ptr passed to LStrAsg = blob+8 (past refcount+length)
_probe=bytes(ks.asm(f"call 0x{REGISTER_ABIL:X}\ncall 0x{CAVE_REG:X}\npop eax\nlea edx,[eax+0x{PH_NAME:X}]\nmov ecx,0x8000\nmov eax,0x{SAND_ID:X}\ncall 0x{CREATE_ENH:X}\nmov edx,eax\nmov eax,ebx\ncall 0x{REGISTER_ABIL:X}\nret",CAVE_REG)[0])
NAME_BLOB_VA=(CAVE_REG+len(_probe)+0x3)&~0x3
NAME_VA=NAME_BLOB_VA+8                                  # pointer handed to CreateEnhancementAbility
_name=b"Path of Sand"
name_blob=struct.pack("<iI",-1,len(_name))+_name+b"\x00"

APPLY="--apply" in sys.argv
def process(path,base,suffix=".pre-pathsand"):
    global name_blob
    data=bytearray(open(path,"rb").read()); secs=load_sections(data); va2off=mkva2off(base)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
    # dependency: outer-ring cave_stash must be applied (E9 jmp at MovedTo 0x5578041E)
    if rd(0x5578041E,1)!=b"\xE9":
        print("[x] outer-ring patch (build_path_outerring.py) not applied -- apply it first (Sand reuses its centre-stash)."); return False
    icon=struct.unpack("<H",rd(ICON_VA,2))[0]
    cave_reg=build_reg(icon)
    print(f"[i] icon word *({ICON_VA:08X}) = 0x{icon:04X}   SAND_ID = 0x{SAND_ID:02X}   name @ {NAME_VA:08X}")
    patches=[
        (CAVE_CB,   bytes(len(cave_cb)),   cave_cb,   "cave_sand_cb (Desiccate progression)"),
        (CAVE_PROC, bytes(len(proc_sand)), proc_sand, "proc_sand (ring-gate: inner 100% / outer 25%)"),
        (CAVE_DISP, bytes(len(cave_disp)), cave_disp, "cave_sanddispatch (MovedTo Sand branch, radius 2)"),
        (CAVE_REG,  bytes(len(cave_reg)),  cave_reg,  "cave_sandreg (Frost re-register + create/register Sand)"),
        (NAME_BLOB_VA, bytes(len(name_blob)), name_blob, 'name literal "Path of Sand"'),
        (DISP_INJ,  DISP_ORIG, b"\xE9"+rel32(DISP_INJ,CAVE_DISP), "MovedTo 0x557804b7 -> cave_sanddispatch"),
        (FROSTREG_INJ, FROSTREG_ORIG, b"\xE8"+rel32(FROSTREG_INJ,CAVE_REG), "Frost RegisterAbility call -> cave_sandreg"),
    ]
    for nm,va,cave in [("cave_sand_cb",CAVE_CB,cave_cb),("proc_sand",CAVE_PROC,proc_sand),
                       ("cave_sanddispatch",CAVE_DISP,cave_disp),("cave_sandreg",CAVE_REG,cave_reg)]:
        print(f"{nm} @ {va:08X} ({len(cave)} B)")
        for ins in cs.disasm(cave,va): print(f"  {ins.address:08X} {ins.bytes.hex(' '):<24}{ins.mnemonic} {ins.op_str}")
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
ok=process(os.path.join(GAME,"AoWEPACK.dpl"),DLL_BASE)
print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first." if not APPLY
      else ("\n[done] Applied. Revert: no --undo here -- restore the ORIG hook byte-runs and zero the"
            "\n       0x5580DF00 caves by hand. A .pre-* restore is not a revert path." if ok else "\n[!] not applied"))
