#!/usr/bin/env python3
r"""
AoW1 mod -- "Lifesteal (LifeStealing ability 0x76 + Dark Gift enchantment 0xA9) works on
Round Attack hits" -- reimplemented as an on-hit effect exactly like Death-Strike->Cursed.

BACKGROUND (verified 2026-07-08; see Investigation_Lifesteal_RoundAttack.md):
  On-hit effects are wired two ways. The ones that WORK on round attack (e.g. Cursed from
  Death Strike, attacker ability 0x77) set their flag in TStrikeCA.Generate @0x557668B4
  (which runs for EVERY strike, round included) and apply it in a plain CA+0x18 flag-block
  in TStrikeCA.Execute. The user's lifesteal instead had its flag set only by the
  normal-melee builder (TMeleeRound.CreateStrikeCA) and healed in Execute's FIRST block,
  which is gated on the strike-result byte CA+0x15 -- that block is skipped on round-attack
  strikes (CA+0x15==0 in Execute for them), so neither LifeStealing nor Dark Gift healed.

FIX -- copy the Cursed template with two position-independent caves (no builder changes):
  PATCH 1 cave_lsgen: hook Generate @0x557668E2 (inside its hit-gated `CA+0x10!=0` block,
    EBX=CA/EDI=attacker/ESI=target). If OFFENSIVE (CA+0xc bit0 clear) and attacker
    GetAbilityEnabled(0x76) -> CA+0x18 |= 0x08 ; GetAbilityEnabled(0xA9) -> CA+0x18 |= 0x10.
    (Free flag bits; hit-gated by Generate itself, so no heal on a miss; offensive-gated so
    no lifesteal on defensive/retaliation -- user wants round only.)
  PATCH 2 cave_lsround: hook Execute @0x5576678C (EBX=CA, EDI=attacker). Heal EDI by
    LS_HEAL if CA+0x18&0x08, by DG_HEAL if CA+0x18&0x10 (via GetHitPoints VMT+0x88 /
    SetHitPoints VMT+0x8c, which clamps), then jmp 0x557667CF -- SKIPPING the old first
    block, so the previous cave_5580C150 lifesteal is bypassed (no double-heal). The flag
    already means "damaging offensive hit", so no CA+0x15 check is needed here.

Result: LifeStealing AND Dark Gift lifesteal on all OFFENSIVE strikes -- normal melee AND
round attack -- not defensive. Ranged unaffected (RangedAttackCA is a different Execute).
The old cave_5580C150 / the 0x557667B8 hook / the 0x55766796 NOP are left in place but are
now unreachable (dead fallback); revert this patch to restore the old behaviour.

Caves at 0x5580C400 (clear of the undocumented combat caves @0x5580C150/240/390/500).
Idempotent, verify-before-write, dry-run by default / --apply. A snapshot goes to
`<game dir>\backups\AoWEPACK.dpl.pre-lsround` ONLY when every site still reads its pre-patch
bytes -- on a heal re-tune the live file is this script's own previous output, so none is minted.

Revert: there is no --undo flag here. Undo by hand -- restore EXEC_INJ / GEN_INJ to their ORIG bytes
and zero the caves at 0x5580C400. A `.pre-*` restore is NOT a revert path: it is a whole-file copy
that drops every feature applied since, and there is no snapshot layer left at all.
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never the game root (rule 2026-09-03)
ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

def load_sections(data):
    e=struct.unpack_from("<I",data,0x3C)[0]; nsec=struct.unpack_from("<H",data,e+6)[0]
    optsize=struct.unpack_from("<H",data,e+20)[0]; sec=e+24+optsize; secs=[]
    for i in range(nsec):
        vsize,vaddr,rsize,raw=struct.unpack_from("<IIII",data,sec+8); secs.append((vaddr,vsize,raw,rsize)); sec+=40
    return secs
def mkva2off(base):
    def va2off(secs,va):
        rva=va-base
        for vaddr,vsize,raw,rsize in secs:
            if vaddr<=rva<vaddr+max(vsize,rsize): return raw+(rva-vaddr)
        raise ValueError(f"VA {va:08X} not mapped")
    return va2off
def rel32(src,dst): return struct.pack("<i",dst-(src+5))

DLL_BASE = 0x55700000
LS_ABIL=0x76; DG_ABIL=0xA9; LS_FLAG=0x08; DG_FLAG=0x10
LS_HEAL=4; DG_HEAL=3  # LS: 2026-08-24 DAM/HP doubling, HP pools x2 so the flat drain heals x2 (was 2).
                      # DG: 4 -> 3 on 2026-09-14 (user ruling) so Dark Gift reads +3 Dam / +3 lifestealing.
                      # The two are INDEPENDENT -- 0x76 LifeStealing and 0xA9 Dark Gift are different
                      # abilities; do not "make them consistent".                                   # <-- tune heal amounts here
DEFENSIVE=False   # False: lifesteal on OFFENSIVE strikes only (normal + round attack) -- what the user wants.
                  # True:  ALSO lifesteal on DEFENSIVE/retaliation strikes (drops the CA+0xc offensive gate).
                  #        (Changes the cave bytes -> re-run with --apply after flipping.)

EXEC_INJ=0x5576678C; EXEC_ORIG=bytes.fromhex("80 7b 15 00 74 3d"); EXEC_CONT=0x557667CF
GEN_INJ =0x557668E2; GEN_ORIG =bytes.fromhex("ba 33 00 00 00");    GEN_CONT =0x557668E7
CAVE1=0x5580DC80                                       # cave_lsround (Execute heal) -- clean 256B block past the terrain caves; 0x5580C4xx has more undocumented combat caves

cave1_src=f"""
    test byte ptr [ebx+0x18], {LS_FLAG}
    jz _dg
    mov eax, edi
    mov edx, [eax]
    call dword ptr [edx+0x88]
    add eax, {LS_HEAL}
    mov edx, eax
    mov eax, edi
    mov ecx, [eax]
    call dword ptr [ecx+0x8c]
_dg:
    test byte ptr [ebx+0x18], {DG_FLAG}
    jz _done
    mov eax, edi
    mov edx, [eax]
    call dword ptr [edx+0x88]
    add eax, {DG_HEAL}
    mov edx, eax
    mov eax, edi
    mov ecx, [eax]
    call dword ptr [ecx+0x8c]
_done:
    jmp 0x{EXEC_CONT:X}
"""
cave1,_=ks.asm(cave1_src,CAVE1); cave1=bytes(cave1)
CAVE2=(CAVE1+len(cave1)+0xF)&~0xF                      # cave_lsgen (Generate flags), 16-aligned

_off_gate = "" if DEFENSIVE else "test byte ptr [ebx+0xc], 1\n    jnz _replay\n    "
cave2_src=f"""
    {_off_gate}mov edx, {LS_ABIL}
    mov eax, edi
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jz _dg
    or byte ptr [ebx+0x18], {LS_FLAG}
_dg:
    mov edx, {DG_ABIL}
    mov eax, edi
    mov ecx, [eax]
    call dword ptr [ecx+0xa8]
    test al, al
    jz _replay
    or byte ptr [ebx+0x18], {DG_FLAG}
_replay:
    mov edx, 0x33
    jmp 0x{GEN_CONT:X}
"""
cave2,_=ks.asm(cave2_src,CAVE2); cave2=bytes(cave2)

redir_exec=b"\xE9"+rel32(EXEC_INJ,CAVE1)+b"\x90"
redir_gen =b"\xE9"+rel32(GEN_INJ,CAVE2)
assert len(redir_exec)==len(EXEC_ORIG)==6 and len(redir_gen)==len(GEN_ORIG)==5

# --- in-place re-tune: accept our OWN previously-installed cave bodies (CLAUDE.md rule).
# Regenerate cave1 across the plausible heal range so a body with OLD constants verifies as ours.
# `add eax, imm8` keeps its length for 1..8, so CAVE2's aligned base does not move.
def _cave1_with(ls, dg):
    src = cave1_src.replace(f"add eax, {LS_HEAL}", f"add eax, {ls}", 1)
    # the second add is DG_HEAL's; replace whichever value it currently renders as
    i = src.rfind("add eax, ")
    src = src[:i] + f"add eax, {dg}" + src[i + len(f"add eax, {DG_HEAL}"):]
    return bytes(ks.asm(src, CAVE1)[0])
CAVE1_VARIANTS = []
for _ls in (1, 2, 3, 4, 6, 8):
    for _dg in (1, 2, 3, 4, 6, 8):
        try: CAVE1_VARIANTS.append(_cave1_with(_ls, _dg))
        except Exception: pass

patches=[
    (CAVE1,   bytes(len(cave1)), cave1,      "cave_lsround (heal on 0x08/0x10 flags)"),
    (CAVE2,   bytes(len(cave2)), cave2,      "cave_lsgen (set 0x08/0x10 in Generate)"),
    (EXEC_INJ,EXEC_ORIG,        redir_exec,  "TStrikeCA.Execute -> cave_lsround (skips old first block)"),
    (GEN_INJ, GEN_ORIG,         redir_gen,   "TStrikeCA.Generate -> cave_lsgen"),
]

print(f"cave_lsround @ {CAVE1:08X} ({len(cave1)} B)")
for ins in cs.disasm(cave1,CAVE1): print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<20}{ins.mnemonic} {ins.op_str}")
print(f"cave_lsgen   @ {CAVE2:08X} ({len(cave2)} B)")
for ins in cs.disasm(cave2,CAVE2): print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<20}{ins.mnemonic} {ins.op_str}")
print(f"redir Execute  @ {EXEC_INJ:08X}: {EXEC_ORIG.hex(' ')} -> {redir_exec.hex(' ')}")
print(f"redir Generate @ {GEN_INJ:08X}: {GEN_ORIG.hex(' ')} -> {redir_gen.hex(' ')}")

APPLY="--apply" in sys.argv
def process(path,base,patches,suffix=".pre-lsround"):
    data=bytearray(open(path,"rb").read()); secs=load_sections(data); va2off=mkva2off(base)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
    if all(rd(va,len(new))==new for va,_o,new,_d in patches):
        print(f"[= ] {os.path.basename(path)}: already applied"); return True
    ok=True
    for va,orig,new,desc in patches:
        cur=rd(va,len(new))
        if cur!=orig and cur!=new:
            if va==CAVE1 and cur in CAVE1_VARIANTS:
                print(f"[~ ] {va:08X} holds OUR cave with different heal constants -- re-tuning in place")
                continue
            ok=False; print(f"[!] {va:08X} ({desc})\n     exp {orig.hex(' ')}\n     got {cur.hex(' ')}")
    if not ok: print(f"[x] {os.path.basename(path)}: mismatch -- not written"); return False
    if not APPLY: print(f"[dry] {os.path.basename(path)}: originals verified"); return True
    # ⚠ Snapshot ONLY from a file PROVED unpatched at every site. The absence of a .pre-* file is
    # not proof: on the re-tune path (LS_HEAL/DG_HEAL changed over an existing install) the live
    # bytes ARE this script's own previous output, and `if not exists` would mint a
    # ".pre-lsround" holding a fully patched DLL. It did exactly that on 2026-09-14; the file was
    # deleted and this gate added. The revert path is the manual surgery in the docstring anyway.
    fresh = all(rd(va, len(orig)) == orig for va, orig, _n, _d in patches)
    bp=os.path.join(BACKUP_DIR, os.path.basename(path)+suffix)
    if fresh and not os.path.exists(bp):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path,bp); print(f"[bak] {bp}")
    elif not fresh:
        print("[i ] re-tune over an existing install -- rewriting the cave in place, no backup minted")
    for va,orig,new,desc in patches:
        o=va2off(secs,va); data[o:o+len(new)]=new; print(f"[w ] {va:08X} {desc}")
    try: open(path,"wb").write(data)
    except PermissionError: print(f"[x] {os.path.basename(path)} LOCKED -- close all AoW binaries"); return False
    return True

path=os.path.join(GAME,"AoWEPACK.dpl"); print()
ok=process(path,DLL_BASE,patches)
print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first." if not APPLY
      else ("\n[done] Applied. Revert: no --undo here -- restore the two ORIG hook byte-runs and zero the"
            "\n       0x5580C400 caves by hand. A .pre-* restore is not a revert path." if ok else "\n[!] not applied"))
