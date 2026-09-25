#!/usr/bin/env python3
r"""
AoW1 mod -- "Ice Storm cools Lava to Wasteland".

⚠⚠ DO NOT RUN `--apply`. The ELSE_SITE hook at 0x557CCEF0 was taken over by
build_chasm_sky_spellguard.py, which chains: not Chasm/Sky -> jmp 0x5580DB20, so THIS feature
still runs, untouched. Re-applying would rebuild that redirect and silently unlink the
spellguard. The self-verify mismatch you get at 0x557CCEF0 is that chain, not damage.
(Same failure mode as build_magebane.py vs build_shield.py -- a script that predates a chain
successor rebuilds the link out of existence.)
The 2026-08-31 synced-RNG change to cave_iceroll below is ALREADY INSTALLED, applied by
build_scripts/build_rng_lockstep.py, which retargets the call in place. Nothing to re-run.

Ice Storm (TIceStorm.ChangeStormTerrain @0x557CCED4) maps terrain per hex:
    Water(0) -> Ice(6);  Ice(6) -> (spawn FrozenWater struct);  else -> Snow(3).
Lava(9) currently falls into the catch-all "else" and becomes Snow(3). This patch
makes Lava(9) -> Wasteland(5) instead (matching Healing Showers), leaving every
other terrain untouched.

MECHANISM
  The catch-all "else" is 5 bytes at 0x557CCEF0:
      C6 01 03            mov byte ptr [ecx], 3      ; -> Snow
      EB 44               jmp 0x557CCF39             ; -> epilogue (POP ESI..RET 4)
  ECX points at the live map-field terrain byte; AL still holds the terrain value
  (MOVSX EAX,[ECX] at 0x557CCEDD, untouched since). Replace those 5 bytes with a
  jmp to a code cave that branches on lava:
      cmp al, 9
      jne _snow
      mov byte ptr [ecx], 5     ; Lava -> Wasteland
      jmp 0x557CCF39
   _snow:
      mov byte ptr [ecx], 3     ; everything else -> Snow (unchanged)
      jmp 0x557CCF39

  Position-independent (ECX/AL + rel32 only), per aow1-dpl-rebasing. Cave sits in
  verified zero space at 0x5580DB20 -- above the fire-heal caves (which end at
  0x5580DB16), so it coexists with build_firefeed.py in either apply order.

PATCH 2 -- per-proc skip gate (cave_iceroll @0x5580DB40), skip chance = 1/SKIP_DENOM
  ⚠ Since 2026-09-25 build_icestorm_gate25.py flips this cave's `je` at 0x5580DB4E to `jne`: a proc
  now TAKES EFFECT with chance 1/SKIP_DENOM (25%) instead of skipping with it. The text below
  describes the original sense.
  (currently SKIP_DENOM=4 -> 25% skip; was 2 -> 50%).
  Ice Storm inherits TBlastStorm.UpdateStorm, which re-applies ChangeStormTerrain over
  a GROWING radius at 4 frames (r1/r2/r3/r4 @ frames 8/12/18/22): a center hex is hit
  ~4x, an edge hex 1x. With the one-way chain Lava->Wasteland->Snow that made a snow
  core inside a wasteland ring. Adding a "do nothing" roll on EACH proc of EACH hex
  means fewer follow-through steps land, so more wasteland survives (and some center
  hexes even stay lava) -- a patchier, organic result. Lower skip% (bigger SKIP_DENOM)
  = less surviving wasteland / more full transformation.
  Injected at the function entry (0x557CCEDD, right after the prologue, over
  MOVSX EAX,[ECX] ; TEST AX,AX): roll RandInt(SKIP_DENOM); on 0 (1/DENOM) jump straight
  to the epilogue (no terrain change at all, any terrain); otherwise replay MOVSX/TEST
  and continue normal flow at 0x557CCEE3. ECX (terrain ptr) preserved across the RandInt
  thunk (0x55701080, EAX=N -> 0..N-1). Rebase-safe (reg + rel32 only). The gate wraps the
  whole function, so it also thins water->ice / land->snow / frozen-water spawns by the
  same rate per proc (intended: "each proc, each hex"). To re-tune: change SKIP_DENOM
  (add the new value to KNOWN_DENOMS so it re-applies in place) and re-run --apply.

Idempotent; verifies every original byte; backs up to <game dir>\backups\AoWEPACK.dpl.pre-icelava;
dry-run by default, pass --apply.
REVERT: NOT by snapshot. Restoring a whole-file .pre-* wipes every feature applied after it, and
there is no snapshot layer at all now (both stacks were purged, 2026-08-08 and 2026-09-09). This
script has no --undo flag: back it out by hand, restoring the original bytes listed in `patches`.
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

DLL_BASE = 0x55700000
ELSE_SITE = 0x557CCEF0            # catch-all "mov [ecx],3 ; jmp epilogue"
ELSE_ORIG = bytes.fromhex("c6 01 03 eb 44")
EPILOGUE  = 0x557CCF39            # POP ESI ; POP EBX ; POP EBP ; RET 4
CAVE      = 0x5580DB20            # verified zero space, above the fire-heal caves

cave_src = f"""
    cmp al, 9
    jne _snow
    mov byte ptr [ecx], 5
    jmp 0x{EPILOGUE:X}
_snow:
    mov byte ptr [ecx], 3
    jmp 0x{EPILOGUE:X}
"""
cave, _ = ks.asm(cave_src, CAVE); cave = bytes(cave)
redir = b"\xE9" + rel32(ELSE_SITE, CAVE)
assert len(redir) == len(ELSE_ORIG) == 5

# ---- PATCH 2: per-proc skip gate at the function entry ----
# Skip chance = 1/SKIP_DENOM.  SKIP_DENOM=2 -> 50%, 4 -> 25%, 3 -> ~33%.
SKIP_DENOM   = 4                               # <-- tune here (currently 25% skip)
KNOWN_DENOMS = [2, 4]                           # prior shipped values, accepted for in-place re-tune
ENTRY_SITE = 0x557CCEDD                       # MOVSX EAX,[ECX] ; TEST AX,AX (6 bytes)
ENTRY_ORIG = bytes.fromhex("0f be 01 66 85 c0")
ENTRY_CONT = 0x557CCEE3                        # JNZ 0x557cceea (resume normal flow)
RANDINT    = 0x55701080                        # System.RandInt thunk: EAX=N -> 0..N-1  (RAW)
# ⚠ The skip roll must draw from the SYNCHRONISED generator, not RANDINT: it decides replicated
# terrain state, and vanilla TIceStorm.ChangeStormTerrain -- the very function this cave is the
# entry hook for -- draws synced at 0x557CCF1E. RNG_SYNC is the drop-in stub installed by
# build_rng_lockstep.py (same @RandInt ABI: EAX=n in, 0..n-1 out). Rule + audit:
# "Modding Resources/Zig notes/12-re-toolchain.md" section 4; check with re_tools/rng_audit.py.
RNG_SYNC   = 0x55827000                        # rng_sync stub -> AoWE.TAoWHSMap.Random
CAVE2      = 0x5580DB40                         # zero space above cave_icelava
# cave_iceroll is EXACTLY 0x20 bytes and ends where cave_lavadirt begins (0x5580DB60) -- it
# cannot grow, which is why the synced draw goes through the stub instead of being inlined.

def make_roll_cave(n, rng=None):
    src = f"""
        push ecx
        mov eax, {n}
        call 0x{(rng or RNG_SYNC):X}
        pop ecx
        test eax, eax
        jz _skip
        movsx eax, byte ptr [ecx]
        test ax, ax
        jmp 0x{ENTRY_CONT:X}
    _skip:
        jmp 0x{EPILOGUE:X}
    """
    code, _ = ks.asm(src, CAVE2); return bytes(code)

cave2 = make_roll_cave(SKIP_DENOM)
# accept a pristine (zero) cave OR any previously-shipped SKIP_DENOM version for in-place
# overwrite -- INCLUDING the pre-2026-08-31 raw-RandInt form, which shipped before the roll was
# moved to the synchronised generator.
cave2_priors = ([bytes(len(cave2))]
                + [make_roll_cave(n, rng) for n in KNOWN_DENOMS for rng in (RNG_SYNC, RANDINT)])
redir2 = b"\xE9" + rel32(ENTRY_SITE, CAVE2) + b"\x90"
assert len(redir2) == len(ENTRY_ORIG) == 6

dll_patches = [
    (CAVE,       bytes(len(cave)),  cave,   "cave_icelava (Lava->Wasteland else Snow)"),
    (ELSE_SITE,  ELSE_ORIG,         redir,  "IceStorm catch-all else -> cave_icelava"),
    (CAVE2,      cave2_priors,      cave2,  f"cave_iceroll (1/{SKIP_DENOM} per-proc skip)"),
    (ENTRY_SITE, ENTRY_ORIG,        redir2, "IceStorm entry -> cave_iceroll"),
]

print(f"cave_icelava @ {CAVE:08X}  ({len(cave)} B)")
for ins in cs.disasm(cave, CAVE):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<16} {ins.mnemonic} {ins.op_str}")
print(f"redirect @ {ELSE_SITE:08X}: {ELSE_ORIG.hex(' ')} -> {redir.hex(' ')}")
print(f"\ncave_iceroll @ {CAVE2:08X}  ({len(cave2)} B)")
for ins in cs.disasm(cave2, CAVE2):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<16} {ins.mnemonic} {ins.op_str}")
print(f"redirect @ {ENTRY_SITE:08X}: {ENTRY_ORIG.hex(' ')} -> {redir2.hex(' ')}")

APPLY = "--apply" in sys.argv
def _accepts(orig, cur):                       # orig may be bytes or a list of acceptable priors
    return cur in orig if isinstance(orig,(list,tuple)) else cur==orig
def process(path, base, patches, backup_suffix=".pre-icelava"):
    data = bytearray(open(path,"rb").read())
    secs = load_sections(data); va2off = mkva2off(base)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
    if all(rd(va,len(new))==new for va,_o,new,_d in patches):
        print(f"[= ] {os.path.basename(path)}: already applied"); return True
    ok=True
    for va,orig,new,desc in patches:
        cur=rd(va,len(new))
        if not _accepts(orig,cur) and cur!=new:
            exp = orig[0].hex(' ')+" (or prior)" if isinstance(orig,(list,tuple)) else orig.hex(' ')
            ok=False; print(f"[!] {va:08X} ({desc})\n     exp {exp}\n     got {cur.hex(' ')}")
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

def stub_installed(p):
    """cave_iceroll calls the rng_sync stub. Writing that call while the stub is still a zeroed
    cave would send the roll into 0x00 bytes, so refuse rather than ship a crash."""
    data = open(p,"rb").read(); secs = load_sections(bytearray(data))
    o = mkva2off(DLL_BASE)(secs, RNG_SYNC)
    return data[o:o+8] != bytes(8)

print()
if APPLY and not stub_installed(path):
    print(f"[x] rng_sync stub @{RNG_SYNC:08X} is not installed -- cave_iceroll's roll would call\n"
          f"    into zeroed cave space. Run:  python build_scripts/build_rng_lockstep.py --apply\n"
          f"    then re-run this script.")
    sys.exit(2)
ok = process(path, DLL_BASE, dll_patches)
if not APPLY:
    print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first.")
elif ok:
    print("\n[done] Applied. Revert: undo surgically by hand -- a .pre-* restore is not a revert path.")
else:
    print("\n[!] Not applied -- see above.")
