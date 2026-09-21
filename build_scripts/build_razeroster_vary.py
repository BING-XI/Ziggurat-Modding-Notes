#!/usr/bin/env python3
r"""
AoW1 mod -- "razeroster_vary": make the hidden raze-defender roster RE-ROLL each game-day instead of
being identical on every raze attempt at a given structure.

FULL DESIGN: Modding Resources/Raze_CombatPredictor_Analysis.md section 13 (req2 seed variation).

THE BUG (vanilla): TStructure.GenerateRazeDefenders @0x5575FD1C seeds the roster RNG with a value that
depends ONLY on the structure's map position and a per-GAME constant:

    RandSeed := MOVSX(GetX)  +  Map[+0x22C]  +  MOVSX(GetY)

    0x5575FD2B  call [edx+0x74]      ; GetX (byte)      -> MOVSX ESI,AL
    0x5575FD31  mov eax,[0x558FA040] ; map ptr (single deref of the map global)
    0x5575FD36  add esi,[eax+0x22c]  ; + per-game seed constant   <-- HOOK SITE (6 bytes)
    0x5575FD3C  ... call [edx+0x78]  ; GetY (byte)      -> MOVSX EAX,AL  ; + esi
    0x5575FD48  mov eax,[0x558FB720] ; &System.RandSeed
    0x5575FD4D  mov [eax],esi        ; store the seed

Because Map[+0x22C] is fixed for the whole game and X/Y never change, EVERY raze attempt at a given
tower generates the IDENTICAL roster. This function is called by BOTH the CanRaze preview and the
actual raze (and vanilla PlaceRazeDefenders), so preview == combat -- good -- but the roster is
frozen, so re-attempting a raze always faces the same defenders.

THE FIX: add the current game-DAY counter (Map[+0x174], the value TPlayerControl.NewDay @0x55754DA4
increments once per new day, i.e. map[0x5d]++) into the seed:

    RandSeed := MOVSX(GetX)  +  Map[+0x22C]  +  Map[+0x174]  +  MOVSX(GetY)

  * Map[+0x174] is CONSTANT within a turn/day -> CanRaze preview and the same-day raze compute the
    SAME seed -> the shown roster still matches the fought roster (no preview/combat divergence).
  * It changes only when the day advances -> a later raze attempt on a subsequent turn faces a
    freshly-rolled grouping. (Same-turn re-click does NOT re-roll -- required for preview==combat and
    for MP determinism.)
  * Map[+0x174] is authoritative replicated map state advanced through the synchronised turn/NewDay
    event, so all MP clients compute the same seed -> same roster (no desync).

WHY THIS IS POSITION-INDEPENDENT WITH NO DELTA TRICK: at the hook site (0x5575FD36) EAX already holds
the (runtime-relocated) map pointer, loaded by the preceding 0x5575FD31 `mov eax,[0x558FA040]`. The
cave only READS [EAX+off] and writes ESI -- no absolute data reference, no .reloc dependency. The two
JMPs (hook->cave, cave->resume) are same-module rel32, invariant under DPL rebasing. So the cave needs
NO call/pop load-delta anchor at all.

SCOPE: TStructure.GenerateRazeDefenders is shared by all non-city structures (towers, mines, etc.).
City raze uses City.TCity.GenerateRazeDefenders @0x557AB408 -- a SEPARATE function, NOT touched here.
This is the correct scope for the tower raze-battle rework; per-turn variation is harmless/beneficial
for the other structures too.

CAVE PLACEMENT: this cave shares the AoWEPACK free-zero window 0x5580CE83..0x5580D63F with the
razebattle-tower caves. It is parked at the TOP of that window (0x5580D600, 17 B) so the razebattle
restructure can grow upward from 0x5580CE90 without colliding. RESERVATION: razebattle caves must end
strictly below 0x5580D600.

Backup <game dir>\backups\AoWEPACK.dpl.pre-razeroster. Independent region from razebattle (different
hook site, different cave), so the two features do not conflict.
REVERT: NOT by snapshot. Restoring a whole-file .pre-* wipes every feature applied after it, and
there is no snapshot layer at all now (both stacks were purged, 2026-08-08 and 2026-09-09). This
script has no --undo flag: to back out ONLY the seed variation, or everything, do it by hand from
the sites listed in `patches`.

Dry-run by default; pass --apply (close ALL AoW binaries first -- they lock the DLL). Idempotent
(accepts vanilla OR already-applied bytes as the "before" state).
"""
import os, sys, struct, shutil
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

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
def mkva2off(base):
    def va2off(secs, va):
        rva = va-base
        for vaddr,vsize,raw,rsize in secs:
            if vaddr <= rva < vaddr+max(vsize,rsize):
                return raw+(rva-vaddr)
        raise ValueError(f"VA {va:08X} not mapped")
    return va2off
def rel32(src, dst): return struct.pack("<i", dst-(src+5))
def asm(text, addr):
    enc, _ = ks.asm(text, addr)
    return bytes(enc)

# ---- addresses (Ghidra VAs, image base 0x55700000) ----
HOOK_VA   = 0x5575FD36                     # ADD ESI,[EAX+0x22c]  (6 bytes) -- the per-game seed add
HOOK_ORIG = bytes.fromhex("03 b0 2c 02 00 00")
RESUME_VA = 0x5575FD3C                     # after the displaced ADD (mov eax,edi; ... GetY)
CAVE_VA   = 0x5580D600                     # top of the razebattle free window (reserved for razeroster)
SEED_OFF  = 0x22C                          # Map[+0x22C] = per-game seed constant
DAY_OFF   = 0x174                          # Map[+0x174] = current-day counter (NewDay increments it)
CAVE_LIMIT= 0x5580D640                     # next existing mod cave -- stay strictly below

# ---- cave: replay the displaced seed add, add the day term, return. Naturally PIC (EAX=map is live;
#      only EAX read / ESI written; both JMPs are same-module rel32). ----
cave = asm(
    f"add esi, dword ptr [eax+0x{SEED_OFF:X}]\n"      # replay displaced: + per-game seed
    f"add esi, dword ptr [eax+0x{DAY_OFF:X}]\n"       # NEW: + current day  -> re-rolls each day
    f"jmp 0x{RESUME_VA:X}\n",                          # resume original body
    CAVE_VA)
assert cave[:6] == HOOK_ORIG, f"cave replay bytes {cave[:6].hex()} != displaced {HOOK_ORIG.hex()}"
assert CAVE_VA + len(cave) <= CAVE_LIMIT, "seed cave overruns next mod cave"

# ---- hook: E9 rel32 + NOP over the 6-byte displaced ADD ----
hook = b"\xE9" + rel32(HOOK_VA, CAVE_VA) + b"\x90"
assert len(hook) == len(HOOK_ORIG) == 6

# ---- patch table: (va, [acceptable priors], new, desc) ----
Z = lambda n: bytes(n)
patches = [
    (CAVE_VA,  [Z(len(cave))], cave, "cave_razeseed (replay seed add + day term)"),
    (HOOK_VA,  [HOOK_ORIG],    hook, "GenerateRazeDefenders seed -> cave_razeseed"),
]

# ---- disassembly review ----
print(f"\ncave_razeseed @ {CAVE_VA:08X}  ({len(cave)} B)")
for ins in cs.disasm(cave, CAVE_VA):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<20} {ins.mnemonic} {ins.op_str}")
print(f"\nseed hook @ {HOOK_VA:08X}: {HOOK_ORIG.hex(' ')} -> {hook.hex(' ')}  (resume {RESUME_VA:08X})")

APPLY = "--apply" in sys.argv
def _accepts(prior, cur):
    return cur in prior if isinstance(prior,(list,tuple)) else cur==prior
def process(path, base, patches, backup_suffix=".pre-razeroster"):
    try:
        data = bytearray(open(path,"rb").read())
    except PermissionError:
        print(f"[x] {os.path.basename(path)} LOCKED (read) -- close all AoW binaries and retry"); return False
    secs = load_sections(data); va2off = mkva2off(base)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
    if all(rd(va,len(new))==new for va,_p,new,_d in patches):
        print(f"[= ] {os.path.basename(path)}: already applied (razeroster)"); return True
    ok=True
    for va,prior,new,desc in patches:
        cur=rd(va,len(new))
        if not _accepts(prior,cur) and cur!=new:
            exp = (prior[0].hex(' ')+" (or prior)") if isinstance(prior,(list,tuple)) else prior.hex(' ')
            ok=False; print(f"[!] {va:08X} ({desc})\n     exp {exp}\n     got {cur.hex(' ')}")
    if not ok:
        print(f"[x] {os.path.basename(path)}: originals mismatch -- not written"); return False
    if not APPLY:
        print(f"[dry] {os.path.basename(path)}: originals verified (vanilla or applied prior accepted)"); return True
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bpath=os.path.join(BACKUP_DIR, os.path.basename(path)+backup_suffix)
    if not os.path.exists(bpath):
        try: shutil.copy2(path,bpath); print(f"[bak] {bpath}")
        except PermissionError:
            print(f"[x] {os.path.basename(path)} LOCKED (backup) -- close all AoW binaries and retry"); return False
    else:
        print(f"[bak] {os.path.basename(bpath)} already exists -- not overwritten")
    for va,prior,new,desc in patches:
        o=va2off(secs,va); data[o:o+len(new)]=new; print(f"[w ] {va:08X} {desc}")
    try: open(path,"wb").write(data)
    except PermissionError:
        print(f"[x] {os.path.basename(path)} LOCKED -- close all AoW binaries and retry"); return False
    return True

path = os.path.join(GAME,"AoWEPACK.dpl")
print()
ok = process(path, DLL_BASE, patches)
if not APPLY:
    print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first.")
elif ok:
    print("\n[done] Applied razeroster. Revert: undo surgically by hand -- a .pre-* restore is not a revert path.")
