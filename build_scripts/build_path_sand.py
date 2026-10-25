#!/usr/bin/env python3
r"""
AoW1 mod -- ADD A NEW ABILITY: "Path of Sand" (a 4th Path ability).

A moving unit with Path of Sand DRIES the terrain it leaves behind toward Desert, using the SAME
stepwise progression as the user's Desiccate spell (repurposed Rejuvenate, cave FUN_5580c001):
    Grass(1)->Steppe(4);  Snow(3)->Grass(1);  Steppe(4)->Desert(2);  Wasteland(5)->Desert(2);  Dirt(C)->Steppe(4)
(read-once, no cascade -> each proc dries a hex ONE stage; Desert(2) is terminal). Footprint matches
the other three Paths after the outer-ring mod: radius 2, inner disk 100% + 25% proc on the outer ring.
LEVELS (owner, 2026-10-22): nothing on the cave levels -- Caverns 1, Depths 2, the Abyss 4 (the level
of the hex being left); the surface and the Firmament keep it.  Vanilla gates Life/Decay to the
surface only (0x55780421), but 0x557804B7 is reached past that gate, so cave_sanddispatch tests the
level itself.  That grew it 16 bytes and moved cave_sandreg 0x5580E000 -> 0x5580E010; --apply
recognises the earlier layout and rewrites the zone 0x5580DF00..0x5580E05F in place.  The owner
launched the game after the move (2026-10-22): it starts.

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
# LEVEL GATE (owner, 2026-10-22): Path of Sand does nothing on the cave levels -- Caverns 1, Depths 2,
# the Abyss 4 (`[field+0x12]`, the level of the hex being left; Firmament 3 and the surface 0 keep
# it).  Vanilla gates Life/Decay to the surface only (0x55780421 `cmp byte [field+0x12],0`), and
# 0x557804B7 is reached past that gate, so Sand needs its own test.  EAX/EDX are free here.
# DIAGNOSTIC: with --diag, DROP the GetAbilityEnabled gate so the Sand terraform fires on EVERY
# non-transported move (any unit, any faction). Used to isolate "cave works, ability-check is the
# problem" (terrain dries for all units) vs "cave broken" (nothing changes). NOT for normal use.
DIAG="--diag" in sys.argv
ZONE=(0x5580DF00, 0x5580E060)        # this script's caves; build_path_transportgate.py starts at 0x5580E060
LEVEL_GATE_SRC = """
    mov eax, [ebp-4]
    mov al, byte ptr [eax+0x12]
    dec al
    cmp al, 1
    jbe _skip
    cmp al, 3
    je _skip"""
_gate = "" if DIAG else f"""
    mov edx, {SAND_ID}
    mov eax, ebx
    mov ecx, [eax]
    call dword ptr [ecx+0x148]
    test al, al
    jz _skip"""


def layout(icon, level_gate=True):
    """-> {name: (va, bytes)} for cave_sanddispatch, cave_sandreg and the name literal, and the
    Frost-registration hook bytes.  level_gate=False is the 2026-07..2026-10-21 layout, kept so a
    re-tune recognises it and rewrites in place."""
    disp_va=(CAVE_PROC+len(proc_sand)+0xF)&~0xF
    disp_src=(LEVEL_GATE_SRC if level_gate else "") + _gate + f"""
    call 0x{disp_va:X}
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
    disp=patch(bytes(ks.asm(disp_src,disp_va)[0]),disp_va,0x5F,[(PH_PROC,CAVE_PROC),(PH_MAP,MAPPTR)])
    # cave_sandreg: hooked by repointing the Frost RegisterAbility call. Re-issue Frost's register
    # (the displaced call), then create + register Path of Sand. EAX=ctrl,EDX=frost_obj on entry;
    # EBX=ctrl.  Runs at PACKAGE INIT: a moved cave_sandreg is only proved by launching the exe.
    reg_va=(disp_va+len(disp)+0xF)&~0xF
    def reg_src(name_ph, ic):
        return f"""
        call 0x{REGISTER_ABIL:X}
        call 0x{reg_va:X}
        pop eax
        lea edx, [eax + 0x{name_ph:X}]
        mov ecx, 0x{ic:X}
        mov eax, 0x{SAND_ID:X}
        call 0x{CREATE_ENH:X}
        mov edx, eax
        mov eax, ebx
        call 0x{REGISTER_ABIL:X}
        ret
    """
    probe=bytes(ks.asm(reg_src(PH_NAME, 0x8000),reg_va)[0])
    blob_va=(reg_va+len(probe)+0x3)&~0x3
    name_va=blob_va+8                                   # pointer handed to CreateEnhancementAbility
    reg=patch(bytes(ks.asm(reg_src(PH_NAME, icon),reg_va)[0]),reg_va,0x58,[(PH_NAME,name_va)])
    name=b"Path of Sand"
    blob=struct.pack("<iI",-1,len(name))+name+b"\x00"
    assert blob_va+len(blob) <= ZONE[1], "the caves overrun %08X" % ZONE[1]
    return {"cave_sanddispatch": (disp_va, disp), "cave_sandreg": (reg_va, reg),
            'name literal "Path of Sand"': (blob_va, blob),
            "frostreg_hook": b"\xE8"+rel32(FROSTREG_INJ,reg_va), "disp_hook": b"\xE9"+rel32(DISP_INJ,disp_va),
            "name_va": name_va}


def zone_image(lay):
    img=bytearray(ZONE[1]-ZONE[0])
    for va,code in ((CAVE_CB,cave_cb),(CAVE_PROC,proc_sand))+tuple(
            v for k,v in lay.items() if isinstance(v,tuple)):
        img[va-ZONE[0]:va-ZONE[0]+len(code)]=code
    return bytes(img)


APPLY="--apply" in sys.argv
def process(path,base,suffix=".pre-pathsand"):
    data=bytearray(open(path,"rb").read()); secs=load_sections(data); va2off=mkva2off(base)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
    # dependency: outer-ring cave_stash must be applied (E9 jmp at MovedTo 0x5578041E)
    if rd(0x5578041E,1)!=b"\xE9":
        print("[x] outer-ring patch (build_path_outerring.py) not applied -- apply it first (Sand reuses its centre-stash)."); return False
    icon=struct.unpack("<H",rd(ICON_VA,2))[0]
    new=layout(icon, True); old=layout(icon, False)
    print(f"[i] icon word *({ICON_VA:08X}) = 0x{icon:04X}   SAND_ID = 0x{SAND_ID:02X}   name @ {new['name_va']:08X}")
    for nm,va,cave in [("cave_sand_cb",CAVE_CB,cave_cb),("proc_sand",CAVE_PROC,proc_sand)]+[
            (k,)+v for k,v in new.items() if isinstance(v,tuple) and not k.startswith("name")]:
        print(f"{nm} @ {va:08X} ({len(cave)} B)")
        for ins in cs.disasm(cave,va): print(f"  {ins.address:08X} {ins.bytes.hex(' '):<24}{ins.mnemonic} {ins.op_str}")
    zone=rd(ZONE[0],ZONE[1]-ZONE[0]); want=zone_image(new)
    disp=rd(DISP_INJ,5); freg=rd(FROSTREG_INJ,5)
    if zone==want and disp==new["disp_hook"] and freg==new["frostreg_hook"]:
        print(f"[= ] {os.path.basename(path)}: already applied"); return True
    zs = "zero" if not any(zone) else "previous layout (no level gate)" if zone==zone_image(old) else None
    ok = zs is not None and disp in (DISP_ORIG,new["disp_hook"]) and freg in (FROSTREG_ORIG,old["frostreg_hook"],new["frostreg_hook"])
    print(f"[i] zone {ZONE[0]:08X}-{ZONE[1]:08X}: {zs or 'FOREIGN'};  MovedTo hook {disp.hex(' ')};  Frost reg hook {freg.hex(' ')}")
    if not ok: print("[x] mismatch -- not written"); return False
    if not APPLY: print("[dry] verified" + ("; --apply rewrites the zone in place" if zs!="zero" else "")); return True
    if zs=="zero":
        os.makedirs(BACKUP_DIR, exist_ok=True)
        bp=os.path.join(BACKUP_DIR, os.path.basename(path)+suffix)
        if not os.path.exists(bp): shutil.copy2(path,bp); print(f"[bak] {bp}")
    for va,blob,desc in ((ZONE[0],want,"the zone"),(DISP_INJ,new["disp_hook"],"MovedTo 0x557804b7 -> cave_sanddispatch"),
                         (FROSTREG_INJ,new["frostreg_hook"],"Frost RegisterAbility call -> cave_sandreg")):
        o=va2off(secs,va); data[o:o+len(blob)]=blob; print(f"[w ] {va:08X} {desc}")
    try: open(path,"wb").write(data)
    except PermissionError: print("[x] LOCKED -- close AoW binaries"); return False
    return True

print()
ok=process(os.path.join(GAME,"AoWEPACK.dpl"),DLL_BASE)
print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first." if not APPLY
      else ("\n[done] Applied. Revert: no --undo here -- restore the ORIG hook byte-runs and zero the"
            "\n       0x5580DF00 caves by hand. A .pre-* restore is not a revert path." if ok else "\n[!] not applied"))
