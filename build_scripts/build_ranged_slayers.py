#!/usr/bin/env python3
r"""
AoW1 mod -- PHASE 2 of the slayer work: give all four "slayer" bonuses a RANGED branch (+1 attack /
+1 damage) so they fire on ranged shots AND breath attacks, not just melee. Slayers covered:
  Monster Slaying (0x70, vs target marker 0x3f) | Holy Champion (0x92 or enchant 0xA0, vs EVIL target)
  Unholy Champion (0x93 or enchant 0xA1, vs GOOD target) | Assassin (0x38, vs HERO target -- Phase 1).
Melee stays as-is (Monster/Assassin +3/+3, Champions +2/+2); ranged is a uniform +1/+1 per matching slayer
(stacks, like the melee blocks). Idea credit: modder "Inioch" (the Assassin concept).

WHERE (verified by tracing, per the melee lesson -- don't assume one builder):
  A ranged shot AND a breath attack both go TRangedAttackAbility/TBreathAbility.fcExecuteCombatCommand ->
  `CreateRangedAttackCA` @0x5576eae4, called once PER SHOT (fcExecuteCombatCommand loops GetAttackRepeatRA
  times). There is NO predictor twin for ranged (unlike melee's CalculateStrikes/CalculateUnitStrikes) --
  CreateRangedAttackCA is the sole builder, so ONE hook covers ranged + breath.

  Inside CreateRangedAttackCA (EBX=ability, ESI=attacker[combat], [EBP-4]=target[combat], [EBP+8]=wall/cover):
    attack = GetAttackRA(VMT+0x114) - wall     -> pushed @0x5576eb1d   (on the stack as uVar4)
    damage = GetDamageRA(VMT+0x110)            -> in AL after the call @0x5576eb2e, pushed @0x5576eb34
  (VMT+0x110=damage / VMT+0x114=attack are confirmed by GetDamageValue@0x5576e764, which feeds both to
  StatisticsToLimitedDV.) VMT+0x110/0x11c take only register args, so the pushed attack survives to the
  CA setup (VMT+0x68, a TStrikeCA-style (ca,attacker,target,+3 stack) setter -- NOT TDamageCA.Setup).

  We hook @0x5576eb34 (the `PUSH EAX` of the damage, where AL=damage and [ESP]=the already-pushed attack).
  The cave computes the slayer bonus on the COMBAT objects (GetAbilityEnabled@VMT+0xa8, alignment@VMT+0x90,
  hero via *(target+0x4c)->IsClass THero -- exactly the melee cave_melee3 convention) and bumps BOTH the
  damage (AL) and the attack ([ESP]) by +1 per matching slayer, then replays the 3 displaced instrs.

COMPOSES with the user's existing ranged caves: the Marksmanship-scaling rework + the Cave/Depths -2 no-
Night-Vision malus both live UPSTREAM in GetAttackRA/FUN_5580c240 (attacker-only), which we never touch.

Position-independent (call/pop-edi PIC anchor for the THero classref). Idempotent, verify-before-write,
free-space asserted, backup .pre-rangedslayers, dry-run by default / --apply.
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
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
ISCLASS=0x557010C0; THERO_CLASSREF=0x55711FAC   # IsClass(obj,classref); classref = CONTENTS of 0x55711fac
TCU_CLASSREF=0x55715A54                         # TCombatUnit classref CELL: [0x55715A54] = 0x55715A94 (verified).
                                                # A CELL, so `mov edx,[cell]` -- contrast 0x5571D4BC, which is a VMT
                                                # BASE and needs `lea`. Getting that backwards makes the gate inert.
ASSASSIN_ID=0x38                                 # Phase-1 Assassin ability id
# 5% CONVERSION (2026-08-18): the ATTACK bonus doubles, the DAMAGE bonus does NOT.
# Previously one constant fed both, which is only safe while they are equal.
#
# STACK INSIDE THIS CAVE (the header above describes the stack AT THE HOOK, which is different --
# that difference caused a real misreading).  cave_rng entry is `push edi; push eax`, so in the body:
#     [esp]    = EAX  = the DAMAGE      -> must NOT double (damage is not part of the stat difference)
#     [esp+4]  = EDI  = saved register
#     [esp+8]  =        the ATTACK      -> doubles
# Verified by tracing: CreateRangedAttackCA pushes the attack at 0x5576EB1D, the hook at 0x5576EB34
# reaches cave_ts_rng (0x5580E400) which does `push eax` then `sub [esp+4],3` for the invisibility
# ATTACK penalty and `pop eax` before jumping here.
RANGED_ATK_BONUS=2                                # ranged ATTACK bonus per matching slayer (was 1)
RANGED_DAM_BONUS=2                                # ranged DAMAGE bonus per matching slayer (2026-08-24 DAM/HP doubling: was 1)

# --- hook: the damage PUSH in CreateRangedAttackCA (AL=damage, [ESP]=attack) ---
RNG_INJ=0x5576EB34; RNG_ORIG=bytes.fromhex("50 8b c6 8b 10")   # PUSH EAX; MOV EAX,ESI; MOV EDX,[EAX]
RNG_CONT=0x5576EB39                                             # -> CALL [EDX+0xb8] (strategicUnit for VMT+0x11c)
CAVE_RNG=0x5580E190                                            # free zeroed cave zone (past the Assassin caves @..E188)
PH_THERO=0x71111117
PH_TCU=0x71111118

# cave_rng: 4 slayer checks on combat attacker(ESI)/target([EBP-4]); each match bumps damage([ESP]) + attack([ESP+8]).
# Stack (after the two saves + PIC anchor): [ESP]=damage, [ESP+4]=saved EDI, [ESP+8]=attack(uVar4). EDI = PIC anchor.
rng_src=f"""
    push edi
    push eax
    call 0x{CAVE_RNG:X}
    pop edi
    mov edx, 0x70
    mov eax, esi
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jz _c1
    mov eax, [ebp-4]
    mov edx, 0x3f
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jz _c1
    add byte ptr [esp], {RANGED_DAM_BONUS}
    add byte ptr [esp+8], {RANGED_ATK_BONUS}
_c1:
    mov edx, 0x92
    mov eax, esi
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jnz _c1hit
    mov edx, 0xa0
    mov eax, esi
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jz _c2
_c1hit:
    mov eax, [ebp-4]
    mov ecx, [eax]
    call dword ptr [ecx+0x90]
    add al, 0xfc
    sub al, 0x2
    jnc _c2
    add byte ptr [esp], {RANGED_DAM_BONUS}
    add byte ptr [esp+8], {RANGED_ATK_BONUS}
_c2:
    mov edx, 0x93
    mov eax, esi
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jnz _c2hit
    mov edx, 0xa1
    mov eax, esi
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jz _c3
_c2hit:
    mov eax, [ebp-4]
    mov ecx, [eax]
    call dword ptr [ecx+0x90]
    sub al, 0x2
    jnc _c3
    add byte ptr [esp], {RANGED_DAM_BONUS}
    add byte ptr [esp+8], {RANGED_ATK_BONUS}
_c3:
    mov edx, 0x{ASSASSIN_ID:X}
    mov eax, esi
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jz _cdone
    /* [ebp-4] is the TARGET, and a target CAN be a TCombatWall -- see the note above _c3.
       +0x4C is TCombatUnit-only (TCombatWall reuses it for packed bytes), so the class check
       must come BEFORE the read. Reading first and NIL-checking is exactly the bug that cost a
       full session in build_replaylog.py / build_combatlog_dll.py: a wall's small nonzero
       integer passes `test eax,eax`, then @IsClass dereferences it -> access violation. */
    mov eax, [ebp-4]
    test eax, eax
    jz _cdone
    mov edx, [edi + 0x{PH_TCU:X}]
    call 0x{ISCLASS:X}
    test al, al
    jz _cdone
    mov eax, [ebp-4]
    mov eax, [eax+0x4c]
    test eax, eax
    jz _cdone
    mov edx, [edi + 0x{PH_THERO:X}]
    call 0x{ISCLASS:X}
    test al, al
    jz _cdone
    add byte ptr [esp], {RANGED_DAM_BONUS}
    add byte ptr [esp+8], {RANGED_ATK_BONUS}
_cdone:
    pop eax
    pop edi
    push eax
    mov eax, esi
    mov edx, [eax]
    jmp 0x{RNG_CONT:X}
"""
cave_rng=patch(bytes(ks.asm(rng_src,CAVE_RNG)[0]),CAVE_RNG,0x5F,[(PH_THERO,THERO_CLASSREF),(PH_TCU,TCU_CLASSREF)])

APPLY="--apply" in sys.argv
def process(path,base,suffix=".pre-rangedslayers"):
    # the body may be re-terminated below to keep a spliced-in chain exit, so it is rebound here
    global cave_rng
    data=bytearray(open(path,"rb").read()); secs=load_sections(data); va2off=mkva2off(base)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
    # `patches` is built by the ownership block below: the cave's "expected original" depends on
    # whether the zone is virgin or already holds our previous build, and the hook entry is added
    # ONLY when the hook is still stock -- it may belong to a chained feature (see the warning).
    patches=[]
    print(f"cave_rng @ {CAVE_RNG:08X} ({len(cave_rng)} B), hook @ {RNG_INJ:08X} -> {RNG_CONT:08X}")
    for ins in cs.disasm(cave_rng,CAVE_RNG):
        print(f"  {ins.address:08X} {ins.bytes.hex(' '):<24}{ins.mnemonic} {ins.op_str}")
    # ---- cave-zone ownership, and the HOOK IS NOT NECESSARILY OURS ----
    #
    # ⚠ THE HOOK AT 0x5576EB34 IS SHARED AND CHAINED. build_trueseeing.py / build_invis_penalty.py
    # interpose `cave_ts_rng` @0x5580E400 in front of us: the hook jumps THERE, and that cave falls
    # through with `jmp 0x5580E190` INTO cave_rng. So "the hook points at CAVE_RNG" is NOT a valid
    # ownership test, and blindly rewriting the hook to point straight at CAVE_RNG would silently
    # DELETE the invisibility/true-seeing feature. Only write the hook when it is still stock.
    #
    # Ownership of the cave ZONE is proven by our own prologue being there. Revise in place --
    # `.pre-rangedslayers` is a whole-file snapshot of AoWEPACK.dpl, so a "revert and re-apply"
    # would destroy every feature added since it was taken (CLAUDE.md).
    # exits a downstream cave may legitimately have spliced in (build_magebane.py)
    CHAIN_EXITS={0x55812A20, 0x55812A40, 0x55812A60, 0x55812A80}
    PROLOGUE=bytes.fromhex("5750e8000000005f")      # push edi; push eax; call $+5; pop edi
    jmp_cave=b"\xE9"+rel32(RNG_INJ,CAVE_RNG)
    cur_hook=rd(RNG_INJ,5)
    live=rd(CAVE_RNG,len(cave_rng))

    patches.append((CAVE_RNG, live, cave_rng,
                    "cave_rng (ranged/breath slayer +1/+1 for all four)"))
    if live==cave_rng:
        pass
    elif rd(CAVE_RNG,len(PROLOGUE))==PROLOGUE:
        # find the installed cave's terminating `jmp RNG_CONT`, then assert every byte we would
        # grow into is still zero (25 B of clearance before the next cave at ~0x5580E2A0)
        # ⚠ The terminator is NOT necessarily `jmp RNG_CONT` any more: build_magebane.py splices
        # itself into this cave's exit (it currently jumps to 0x55812A20). Looking only for the
        # stock destination made this script report a FALSE `[x]` -- "no terminator, refusing to
        # guess its extent" -- while the installed bytes were fine. Accept the stock exit OR any
        # exit the chain currently uses, and remember which, so the rewritten body keeps it.
        # Same defect and same fix as build_assassin.py / build_invis_penalty.py.
        blk=rd(CAVE_RNG,0x200); old_end=None; keep_dest=None
        for i in range(len(blk)-5):
            if blk[i]!=0xE9: continue
            dest=CAVE_RNG+i+5+struct.unpack_from("<i",blk,i+1)[0]
            if dest==RNG_CONT or CHAIN_EXITS and dest in CHAIN_EXITS:
                old_end=i+5; keep_dest=dest; break
        if old_end is None:
            print(f"[x] {CAVE_RNG:08X} has our prologue but no recognised terminator (stock "
                  f"{RNG_CONT:08X} or a known chain exit) -- refusing to guess its extent")
            return False
        if keep_dest!=RNG_CONT:
            print(f"[chain] {CAVE_RNG:08X} exit kept at {keep_dest:08X} (stock is {RNG_CONT:08X})"
                  " -- a downstream cave is spliced in")
            t=len(cave_rng)-5
            if cave_rng[t]==0xE9:
                cave_rng=cave_rng[:t+1]+struct.pack("<i",keep_dest-(CAVE_RNG+t+5))+cave_rng[t+5:]
                patches[-1]=(CAVE_RNG, live, cave_rng, patches[-1][3])
        print(f"[i] revising our cave in place: {old_end} B -> {len(cave_rng)} B")
        if len(cave_rng)>old_end:
            tail=blk[old_end:len(cave_rng)]
            if any(tail):
                print(f"[x] would grow {len(cave_rng)-old_end} B into non-zero bytes "
                      f"at {CAVE_RNG+old_end:08X}: {tail.hex(' ')}"); return False
            print(f"    grows {len(cave_rng)-old_end} B into verified-zero space")
    elif not any(live):
        print(f"[i] fresh install into virgin zone {CAVE_RNG:08X}")
    else:
        print(f"[x] cave zone {CAVE_RNG:08X} is occupied and is not ours:\n     {live.hex(' ')}")
        return False

    if cur_hook==RNG_ORIG:
        patches.append((RNG_INJ, RNG_ORIG, jmp_cave,
                        "CreateRangedAttackCA 0x5576eb34 -> cave_rng"))
    elif cur_hook==jmp_cave:
        pass                                         # ours, direct (nothing chained in front)
    else:
        # someone is chained in front -- PROVE the chain still reaches us before leaving it alone
        tgt=RNG_INJ+5+struct.unpack_from("<i",cur_hook,1)[0] if cur_hook[0]==0xE9 else None
        reaches=False
        if tgt is not None:
            ch=rd(tgt,0x100)
            for i in range(len(ch)-5):
                if ch[i]==0xE9 and tgt+i+5+struct.unpack_from("<i",ch,i+1)[0]==CAVE_RNG:
                    reaches=True; break
        if not reaches:
            print(f"[x] hook {RNG_INJ:08X} points at {tgt and hex(tgt)}, which does NOT chain into "
                  f"cave_rng {CAVE_RNG:08X}. Refusing to touch it."); return False
        print(f"[i] hook is chained via {tgt:08X} (true-seeing/invis) which jumps into cave_rng "
              "-- leaving the hook alone")
    if all(rd(va,len(new))==new for va,_o,new,_d in patches):
        print("[= ] already applied"); return True
    ok=True
    for va,orig,new,desc in patches:
        cur=rd(va,len(new))
        if cur!=orig and cur!=new: ok=False; print(f"[!] {va:08X} ({desc})\n     exp {orig.hex(' ')}\n     got {cur.hex(' ')}")
    if not ok: print("[x] mismatch -- not written"); return False
    if not APPLY: print("[dry] originals verified, cave zone free"); return True
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
      # NOT "revert = copy the backup": `.pre-rangedslayers` is a whole-file snapshot of
      # AoWEPACK.dpl, so restoring it destroys every feature applied after it was taken. There is
      # no snapshot layer at all now (both stacks purged, 2026-08-08 and 2026-09-09).
      # This script rewrites its cave in place, so re-running it is the way to re-tune. Taking the
      # feature OUT is not a simple hook restore either -- the hook belongs to the chained
      # true-seeing cave; you would have to make cave_ts_rng jump to RNG_CONT instead of cave_rng.
      else ("\n[done] Applied. Re-run this script to re-tune (it rewrites the cave in place)."
            if ok else "\n[!] not applied"))
