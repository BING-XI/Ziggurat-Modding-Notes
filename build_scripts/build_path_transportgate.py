#!/usr/bin/env python3
r"""
AoW1 mod -- "Path abilities fire on the TRANSPORTER, not just off carried passengers."

VANILLA BUG (by simplification): TAbstractUnit.MovedTo @0x55780328 gates ALL Path abilities
(Life 0x45 / Decay 0x44 / Frost 0x6d / our Sand 0x9F) behind an ARMY-LEVEL transporter check:

    55780407  CALL TArmy.Transporter(army, 0xff)   ; @0x5578e00c -> first army unit with transport
                                                    ;   capacity (VMT+0x108 GetTransportCapacity>0), else 0
    5578040c  TEST EAX,EAX
    5578040e  JNZ  ...set bVar1=true...             ; army HAS a transporter -> skip every Path branch

So Paths are suppressed for EVERY unit whose army contains a transporter -- including the
transporter itself and any escort, not just the passengers being carried. The original devs only
had SHIP transporters (which live on water, where Paths are no-ops anyway), so the blunt block never
showed. With magical/LAND transporters it does: a land transport that should scar the ground leaves
nothing.

FIX (per-unit, minimal, position-independent): the correct rule is "block only if THIS unit is being
carried". The transporter is exactly the unit `Transporter(0xff)` returns. So we hook that call:
run the real Transporter, then if its result == EBX (the moving unit, i.e. I AM the transporter)
return 0. The unchanged `TEST EAX,EAX; JNZ` then sets bVar1 only when the army has a transporter that
ISN'T me == I'm a passenger. Truth table:
  - normal unit, no transporter in army : Transporter=0        -> EAX 0     -> not blocked (vanilla)
  - the transporter unit itself         : Transporter=EBX      -> EAX 0     -> NOT blocked -> leaves trail (NEW)
  - a carried passenger                 : Transporter=other!=EBX-> EAX !=0   -> blocked (correct, unchanged)

Applies to ALL four Paths (shared gate). EBX = moving unit throughout MovedTo; Transporter preserves
it (callee-saved); ESI(army) isn't needed after the gate. cave via rel32 call (position-independent).
Idempotent, verify-before-write, dry-run by default / --apply. Snapshot goes to
`<game dir>\backups\AoWEPACK.dpl.pre-transportgate`.

Revert: there is no --undo flag here. Undo by hand -- restore HOOK to HOOK_ORIG and zero the cave.
A `.pre-*` restore is NOT a revert path: it is a whole-file copy that drops every feature applied
since, and there is no snapshot layer left at all.
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
TRANSPORTER=0x5578e00c                 # TArmy.Transporter(Self=EAX army, EDX=mask) -> EAX transporter|0
HOOK=0x55780407                        # the `CALL TArmy.Transporter` inside MovedTo's transporter gate
HOOK_ORIG=b"\xE8"+rel32(HOOK,TRANSPORTER)
CAVE=0x5580E060                        # free zero run (past the Path-of-Sand caves/name @ ~0x5580E041)

# cave_transgate: EAX=army, EDX=mask on entry (forwarded from the hooked call site).
#   call Transporter -> EAX=transporter|0 ; if EAX==EBX (I am the transporter) return 0 so I'm not blocked.
# NOTE: keystone asm() treats ';' as a statement separator (NOT a comment) and HANGS on comment text --
# keep the asm string comment-free.
cave_src=f"""
    call 0x{TRANSPORTER:X}
    cmp eax, ebx
    jne _keep
    xor eax, eax
_keep:
    ret
"""
cave=bytes(ks.asm(cave_src,CAVE)[0])
redir=b"\xE8"+rel32(HOOK,CAVE)
assert len(redir)==len(HOOK_ORIG)==5

patches=[
    (CAVE, bytes(len(cave)), cave, "cave_transgate (exempt the transporter itself)"),
    (HOOK, HOOK_ORIG, redir, "MovedTo transporter-gate CALL -> cave_transgate"),
]

print(f"cave_transgate @ {CAVE:08X} ({len(cave)} B)")
for ins in cs.disasm(cave,CAVE): print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<20}{ins.mnemonic} {ins.op_str}")
print(f"redir @ {HOOK:08X}: {HOOK_ORIG.hex(' ')} -> {redir.hex(' ')}")

APPLY="--apply" in sys.argv
def process(path,base,suffix=".pre-transportgate"):
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
ok=process(os.path.join(GAME,"AoWEPACK.dpl"),DLL_BASE)
print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first." if not APPLY
      else ("\n[done] Applied. Revert: no --undo here -- restore HOOK_ORIG and zero the cave by hand."
            "\n       A .pre-* restore is not a revert path." if ok else "\n[!] not applied"))
