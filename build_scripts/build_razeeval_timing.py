#!/usr/bin/env python3
r"""
AoW1 mod -- "razetiming": make the AI's post-capture raze evaluation DETERMINISTIC.

THE BUG (vanilla, discovered 2026-07-12 via the diag ladder; full account in
Modding Resources/AI_Raze_Decision_CodeMap.md + the raze memory file):
TAIGroupTargetSelector state 0x15 decides whether a completed journey ended in "I took my
target" (status 5 -> the behavior AGC attaches TAIGroupRazeControl = the raze evaluation)
or "target still stands" (status 3 -> nothing). It decides by IndexOf(assigned target) in
the control's target list -- relying on a VALIDATION pass having pruned the now-owned
structure from that list (TAIGroupControlTargetList.Validate re-queries UpdateAITarget;
owner==requester -> invalid -> Delete). But validation only interleaves if the state pump
(TAIGroupControlPlugin.MainProcess) BROKE between arrival and state 0x15: capture BATTLES
break it deterministically (deferred combat events); walk-in captures usually resolve in
the SAME pump -> target still listed -> status 3 -> the raze question is NEVER asked (the
structure is now owned and can never be a target again). Emergent result: only fought-for
captures ever get raze-evaluated -- cities almost always, walk-in mines almost never
(except stochastic AI-time-slice/turn-boundary breaks). A fourth, accidental gate.

THE FIX: hook state 0x15's entry to run TAIGroupControlTargetList.Validate on the
control's list BEFORE the IndexOf. Every completed capture then observes the pruned list
-> status 5 fires for walk-ins and fought captures alike -> the REAL gates (regional-
desperation want + the v6 CanRaze verdict) decide uniformly. Safety: identical
validate-then-IndexOf sequence already exists in TAIGroupTargetSelector.Validate
@0x5573CEC4 (IndexOf compares pointers, never derefs a pruned target). Double-validation
is harmless. NOTE the deliberate side effect: Scorcher now razes UNDEFENDED hostile
cities it walks into (the design's letter; vanilla's timing bug accidentally skipped them).

HOOK  @0x5573DC6A (case 0x15 of TAIGroupTargetSelector.Process @0x5573D2C0):
    8B 46 10   mov eax,[esi+0x10]   ; control          (ESI = selector, preserved by callee)
    8B 40 24   mov eax,[eax+0x24]   ; target-list obj
  -> E9 rel32 + NOP to cave_valfix @0x5580D200 (free cave space after cave_forcefail v6,
     which ends 0x5580D1F8; the razeroster seed cave starts 0x5580D600).

cave_valfix (18 B, naturally position-independent -- same-module rel32 only):
    mov eax,[esi+0x10] ; mov eax,[eax+0x24]   ; (displaced) EAX = list object
    push eax
    call 0x55738208                            ; TAIGroupControlTargetList.Validate(EAX)
    pop eax                                    ; EAX = list object again
    jmp 0x5573DC70                             ; resume: mov eax,[eax+8] -> IndexOf ...
Register safety: Validate is Delphi (clobbers EAX/ECX/EDX, preserves EBX/ESI/EDI/EBP);
EBX (the selector Process return flag, 0 here) and ESI (selector) survive.

Idempotent; verify-before-write; dry-run by default, --apply to write (close all AoW
binaries first); auto-backup <game dir>\backups\AoWEPACK.dpl.pre-razetiming.
REVERT: NOT by snapshot. Restoring a whole-file .pre-* wipes every feature applied after it, and
there is no snapshot layer at all now (both stacks were purged, 2026-08-08 and 2026-09-09). This
script has no --undo flag: back it out by hand, restoring the original bytes listed in `patches`.
"""
import os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)
DLL_BASE = 0x55700000

def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e+6)[0]
    optsize = struct.unpack_from("<H", data, e+20)[0]
    sec = e+24+optsize; secs=[]
    for i in range(nsec):
        vsize,vaddr,rsize,raw = struct.unpack_from("<IIII", data, sec+8)
        secs.append((vaddr,vsize,raw,rsize)); sec+=40
    return secs
def va2off(secs, va):
    rva = va-DLL_BASE
    for vaddr,vsize,raw,rsize in secs:
        if vaddr <= rva < vaddr+max(vsize,rsize):
            return raw+(rva-vaddr)
    raise ValueError(f"VA {va:08X} not mapped")
def rel32(src, dst): return struct.pack("<i", dst-(src+5))

HOOK       = 0x5573DC6A
HOOK_ORIG  = bytes.fromhex("8b 46 10 8b 40 24")
RESUME     = 0x5573DC70
CAVE       = 0x5580D200
LIST_VALIDATE = 0x55738208     # TAIGroupControlTargetList.Validate (EAX=self)

src = f"""
    mov eax, dword ptr [esi+0x10]
    mov eax, dword ptr [eax+0x24]
    push eax
    call 0x{LIST_VALIDATE:X}
    pop eax
    jmp 0x{RESUME:X}
"""
cave, _ = ks.asm(src, CAVE); cave = bytes(cave)
hook = b"\xE9" + rel32(HOOK, CAVE) + b"\x90"
assert len(hook) == 6
assert CAVE + len(cave) <= 0x5580D600, "cave overruns the razeroster seed reserve"

print(f"cave_valfix @ {CAVE:08X}  ({len(cave)} B)")
for ins in cs.disasm(cave, CAVE):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<18} {ins.mnemonic} {ins.op_str}")
print(f"hook @ {HOOK:08X}: {HOOK_ORIG.hex(' ')} -> {hook.hex(' ')}")

patches = [
    (CAVE, [bytes(len(cave))], cave, "cave_valfix (state-0x15 pre-IndexOf list validation)"),
    (HOOK, [HOOK_ORIG],        hook, "selector state 0x15 entry -> cave_valfix"),
]

APPLY = "--apply" in sys.argv
def _accepts(prior, cur): return cur in prior if isinstance(prior,(list,tuple)) else cur==prior
path = os.path.join(GAME, "AoWEPACK.dpl")
data = bytearray(open(path,"rb").read())
secs = load_sections(data)
def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
if all(rd(va,len(new))==new for va,_p,new,_d in patches):
    print(f"\n[= ] AoWEPACK.dpl: already applied"); sys.exit(0)
ok=True
for va,prior,new,desc in patches:
    cur=rd(va,len(new))
    if not _accepts(prior,cur) and cur!=new:
        ok=False; print(f"[!] {va:08X} ({desc})\n     exp {prior[0].hex(' ')}\n     got {cur.hex(' ')}")
if not ok:
    print("[x] originals mismatch -- not written"); sys.exit(1)
if not APPLY:
    print("\n[dry] originals verified. Re-run with --apply to write (close all AoW binaries)."); sys.exit(0)
os.makedirs(BACKUP_DIR, exist_ok=True)
bak = os.path.join(BACKUP_DIR, os.path.basename(path) + ".pre-razetiming")
if not os.path.exists(bak):
    shutil.copy2(path, bak); print(f"[bak] {bak}")
for va,prior,new,desc in patches:
    o=va2off(secs,va); data[o:o+len(new)]=new; print(f"[w ] {va:08X} {desc}")
try:
    open(path,"wb").write(data)
except PermissionError:
    print("[x] AoWEPACK.dpl LOCKED -- close all AoW binaries and retry"); sys.exit(1)
print("[done] Applied razetiming. Revert: undo surgically by hand -- a .pre-* restore is not a revert path.")
