#!/usr/bin/env python3
r"""
AoW1 mod -- "Raise Terrain: lava hexes -> 50% dirt, timed to the raise glow, no mountain".

Raise Terrain (TRaiseTerrainTE.RaiseTerrain @0x557A3280) already ACCEPTS lava as a
valid target (ValidTargetMapF rejects only Water/Ice/CaveWater/CaveIce 0/6/A/D) but
mountain placement fails on lava so it silently wastes the cast. This makes each LAVA
hex in the area have a 50% chance to become DIRT(0xC) -- no mountain, but WITH the same
green "raise" glow, and the terrain flip happens at the SAME MOMENT the glow reveals a
mountain (frame 9), not up front. Non-lava hexes keep normal mountain behaviour.

TIMING (why two patches)
  Vanilla places the mountain HIDDEN immediately and reveals it at frame 9 of the glow
  via TRaisedMountain.NewFrameRaiseTerrainAnimation (@0x557A31B0). Our first cut changed
  the terrain up front, so dirt appeared before the glow peaked. Fix: don't change
  terrain up front -- defer it into that same frame-9 callback.

PATCH 1 -- cave_lavadirt @0x5580DB60 (loop injection @0x557A333E: XOR EAX,EAX ; MOV ESI,
  [EBP+8], 5 bytes). field=[ESP+8]; terrain!=Lava -> replay + jmp 0x557A3343 (mountain).
  Lava -> RandInt(2) (thunk 0x55701080); nonzero (50%) -> jmp 0x557A3498 (nothing). Else
  (convert): set EBX=field and jmp 0x557A3414 -- the vanilla raise-anim block, which builds
  the green-glow TImageSequenceAnimation, wires NewFrameRaiseTerrainAnimation as its
  per-frame callback with data=EBX(field), and PlaceHX'es it. NO terrain change here.

PATCH 2 -- cave_dirtdelay @0x5580DBD0 (callback augment @0x557A31E9: MOV EBX,EAX ; MOV EDX,
  0x2016A, 7 bytes). NewFrameRaiseTerrainAnimation runs every frame with EAX=field of the
  anim's hex, EDI=frame. Injected right after the field is fetched: if frame==9 AND the hex
  is still Lava(9), ChangeTerrainEx(map, 0, x, 0xC, 0, level, y) using the field's own
  coords (field+0x10=x, +0x11=y, +0x12=level -- confirmed via TIceStorm.StormTerrainChanged),
  then replay MOV EBX,EAX ; MOV EDX,0x2016A and continue at 0x557A31F0. Shared with real
  mountains, but their hex is never lava, so it no-ops for them. The frame==9 gate + the
  lava check make it fire exactly once, in lock-step with the mountain reveal.

cave_dirtdelay calls the LOWER-level HSEngine.THSMap.ChangeTerrainEx (0x557025D4) directly,
NOT the AoWE.TAoWHSMap.ChangeTerrainEx wrapper (vtable+0xD0): the wrapper seeds the variant
RNG via AoWHSMap.Random, which pops "Invalid AoWHSMap.Random use" when called from the render/
animation context (guard: map[0x3c]&8==0 && !GetSynchronised). The lower fn uses the raw RNG
(System.RandInt), no guard. It doesn't touch EDI, so the frame reg stays intact for mountains.

Rebase-safe (aow1-dpl-rebasing): map via call/pop-delta on [0x558E9494]; everything else
register-relative + rel32.

Idempotent (accepts the earlier up-front-conversion cave in place); verifies originals;
backs up to <game dir>\backups\AoWEPACK.dpl.pre-rtlavadirt; dry-run default, --apply.
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
def patch_anchor(code):                          # call/pop-delta: E8.. followed by pop eax (0x58)
    code = bytearray(code)
    i = next(k for k in range(len(code)-5) if code[k]==0xE8 and code[k+5]==0x58)
    anchor = CAVE_ANCHOR_BASE[0] + i + 5
    code[i+1:i+5] = struct.pack("<i", 0)         # call -> next (rel 0)
    assert code[i+6]==0x8B and code[i+7]==0x80, "expected mov eax,[eax+disp32] after pop"
    code[i+8:i+12] = struct.pack("<i", MAPPTR - anchor)
    return bytes(code)
def patch_anchor_multi(code, base, targets):     # patch each placeholder disp to (target - anchor)
    code = bytearray(code)
    i = next(k for k in range(len(code)-5) if code[k]==0xE8 and code[k+5]==0x58)
    anchor = base + i + 5
    code[i+1:i+5] = struct.pack("<i", 0)
    for ph, tgt in targets:
        j = code.find(struct.pack("<I", ph)); assert j!=-1, f"ph {ph:#x} missing"
        code[j:j+4] = struct.pack("<i", tgt - anchor)
    return bytes(code)

DLL_BASE  = 0x55700000
INJ       = 0x557A333E                           # loop: XOR EAX,EAX ; MOV ESI,[EBP+8]
INJ_ORIG  = bytes.fromhex("33 c0 8b 75 08")
RESUME    = 0x557A3343                            # -> mountain-resource loop
CONT      = 0x557A3498                            # per-hex continue
ANIM      = 0x557A3414                            # vanilla raise-glow anim block
CB_INJ    = 0x557A31E9                            # callback: MOV EBX,EAX ; MOV EDX,0x2016A
CB_ORIG   = bytes.fromhex("8b d8 ba 6a 01 02 00")
CB_CONT   = 0x557A31F0                            # resume original callback
RANDINT   = 0x55701080                            # System.@RandInt thunk (RAW, per-process seed)
# ⚠ The 50% lava roll must draw SYNCED: it decides replicated terrain state, and vanilla
# TRaiseTerrainTE.RaiseTerrain -- the function this cave is spliced into -- draws from
# TAoWHSMap.Random TWICE (0x557A3397, and 0x557A346E inside the very anim block at 0x557A3414
# that this cave jumps to). RNG_SYNC is the drop-in stub installed by build_rng_lockstep.py
# (same @RandInt ABI: EAX=n in, 0..n-1 out). Rule: "Zig notes/12-re-toolchain.md" section 4.
# ⚠ This does NOT apply to cave_dirtdelay below -- the frame-9 callback is NOT a synchronised
# context (GetSynchronised is false there, which is why it needs the flag suppression).
RNG_SYNC  = 0x55827000                            # rng_sync stub -> AoWE.TAoWHSMap.Random
CHTERR    = 0x557025D4                            # HSEngine.THSMap.ChangeTerrainEx thunk (7-param; DON'T call directly)
MAPPTR    = 0x558E9494                            # PTR: map = *(*MAPPTR)
RNDMAPPTR = 0x558FA040                            # PTR: flag-map = *(RNDMAPPTR); AoWHSMap.Random tests (*RNDMAPPTR)+0x3c bit3
PH_FLAG   = 0x11111111
PH_MAP    = 0x22222222
LAVA      = 9
DIRT      = 0x0C
CAVE      = 0x5580DB60                            # cave_lavadirt
CAVE_DF   = 0x5580DC20                            # cave_dirtdelay (fresh; moved off 0x5580DBD0 to skip stale bytes)
OLD_CAVE_DF = 0x5580DBD0                          # earlier cave_dirtdelay location (now dead) -- for cb-redir prior
PH_DISP   = 0x11111111
CAVE_ANCHOR_BASE = [CAVE_DF]                      # base used by patch_anchor (set per-cave below)

# ---- PATCH 1: cave_lavadirt (deferred: no up-front terrain change) ----
def make_lavadirt(rng=None):
    src = f"""
        mov eax, [esp+8]
        movsx eax, byte ptr [eax+0x14]
        cmp eax, {LAVA}
        jne _mountain
        mov eax, 2
        call 0x{(rng or RNG_SYNC):X}
        test eax, eax
        jnz _nolava
        mov ebx, [esp+8]
        jmp 0x{ANIM:X}
    _nolava:
        jmp 0x{CONT:X}
    _mountain:
        xor eax, eax
        mov esi, [ebp+8]
        jmp 0x{RESUME:X}
    """
    code, _ = ks.asm(src, CAVE); return bytes(code)

# ---- prior (up-front-conversion) cave, kept only to accept the currently-applied bytes ----
def make_lavadirt_upfront(glow):
    CAVE_ANCHOR_BASE[0] = CAVE
    if glow:
        conv_end = f"mov ebx, [esp+8]\n        jmp 0x{ANIM:X}"; jnz_lbl=exit_lbl="_nolava"
    else:
        conv_end = ""; jnz_lbl=exit_lbl="_skip"
    src = f"""
        mov eax, [esp+8]
        movsx eax, byte ptr [eax+0x14]
        cmp eax, {LAVA}
        jne _mountain
        mov eax, 2
        call 0x{RANDINT:X}
        test eax, eax
        jnz {jnz_lbl}
        mov eax, [esp+0x20]
        push eax
        mov eax, [esp+0x04]
        movsx eax, byte ptr [eax+0x22]
        push eax
        push 0
        push 0x{DIRT:X}
        call 0x{CAVE:X}
        pop eax
        mov eax, [eax + 0x{PH_DISP:X}]
        mov eax, [eax]
        mov ecx, [esp+0x2c]
        xor edx, edx
        mov esi, [eax]
        call dword ptr [esi+0xd0]
        {conv_end}
    {exit_lbl}:
        jmp 0x{CONT:X}
    _mountain:
        xor eax, eax
        mov esi, [ebp+8]
        jmp 0x{RESUME:X}
    """
    code, _ = ks.asm(src, CAVE); return patch_anchor(code)

# ---- PATCH 2: cave_dirtdelay -- lava->dirt at glow frame 9, popup suppressed ----
# The vtable+0xD0 ChangeTerrainEx (4 stack params) is the one that actually works; it calls
# AoWHSMap.Random for the variant, which pops "Invalid AoWHSMap.Random use" from the render
# context. We temporarily set the flag it tests -- (*0x558FA040)+0x3c bit3 -- so Random takes
# the unguarded raw-RandInt path, then restore it. (Calling the lower 0x557025D4 directly is a
# 7-param fn -> stack corruption; the earlier "lower" attempt is only kept to accept in place.)
def make_dirtdelay():                            # v3: active (popup-suppressed vtable call)
    src = f"""
        cmp edi, 9
        jne _orig
        cmp byte ptr [eax+0x14], {LAVA}
        jne _orig
        push eax
        call 0x{CAVE_DF:X}
        pop eax
        mov ebx, [eax + 0x{PH_FLAG:X}]
        movzx edx, byte ptr [ebx+0x3c]
        push edx
        or byte ptr [ebx+0x3c], 8
        mov eax, [eax + 0x{PH_MAP:X}]
        mov eax, [eax]
        mov edx, [esp+4]
        movzx ecx, byte ptr [edx+0x11]
        push ecx
        movzx ecx, byte ptr [edx+0x12]
        push ecx
        push 0
        push 0x{DIRT:X}
        movzx ecx, byte ptr [edx+0x10]
        xor edx, edx
        mov esi, [eax]
        call dword ptr [esi+0xd0]
        pop edx
        mov [ebx+0x3c], dl
        pop eax
    _orig:
        mov ebx, eax
        mov edx, 0x2016a
        jmp 0x{CB_CONT:X}
    """
    code, _ = ks.asm(src, CAVE_DF)
    return patch_anchor_multi(code, CAVE_DF, [(PH_FLAG, RNDMAPPTR), (PH_MAP, MAPPTR)])

def make_dirtdelay_old(style):                   # priors: 'wrapper' (v1) / 'lower' (v2)
    CAVE_ANCHOR_BASE[0] = CAVE_DF
    tc = f"call 0x{CHTERR:X}" if style=='lower' else "mov edi, [eax]\n        call dword ptr [edi+0xd0]"
    src = f"""
        cmp edi, 9
        jne _orig
        cmp byte ptr [eax+0x14], {LAVA}
        jne _orig
        push eax
        movzx ecx, byte ptr [eax+0x11]
        push ecx
        movzx ecx, byte ptr [eax+0x12]
        push ecx
        push 0
        push 0x{DIRT:X}
        call 0x{CAVE_DF:X}
        pop eax
        mov eax, [eax + 0x{PH_DISP:X}]
        mov eax, [eax]
        mov ecx, [esp+0x10]
        movzx ecx, byte ptr [ecx+0x10]
        xor edx, edx
        {tc}
        pop eax
    _orig:
        mov ebx, eax
        mov edx, 0x2016a
        jmp 0x{CB_CONT:X}
    """
    code, _ = ks.asm(src, CAVE_DF); return patch_anchor(code)

lavadirt = make_lavadirt()
dirtdelay = make_dirtdelay()
redir   = b"\xE9" + rel32(INJ, CAVE)
cb_redir    = b"\xE9" + rel32(CB_INJ, CAVE_DF)     + b"\x90\x90"
cb_redir_old= b"\xE9" + rel32(CB_INJ, OLD_CAVE_DF) + b"\x90\x90"
assert len(redir)==5 and len(cb_redir)==len(CB_ORIG)==7

L = len(lavadirt)
def fit(b): return (b + bytes(L))[:L]
# priors: pristine zero cave, the two up-front-conversion cuts, and the pre-2026-08-31 form of
# THIS cave that rolled through the raw thunk (same length, one rel32 different)
cave_priors = [bytes(L), fit(make_lavadirt(RANDINT)),
               fit(make_lavadirt_upfront(True)), fit(make_lavadirt_upfront(False))]

dll_patches = [
    (CAVE,    cave_priors,  lavadirt,  "cave_lavadirt (lava->50% dirt, defer to glow)"),
    (INJ,     INJ_ORIG,     redir,     "RaiseTerrain -> cave_lavadirt"),
    (CAVE_DF, bytes(len(dirtdelay)), dirtdelay, "cave_dirtdelay (convert at glow frame 9, popup-suppressed)"),
    (CB_INJ,  [CB_ORIG, cb_redir_old], cb_redir,  "NewFrameRaiseTerrainAnimation -> cave_dirtdelay"),
]

print(f"cave_lavadirt @ {CAVE:08X}  ({len(lavadirt)} B)")
for ins in cs.disasm(lavadirt, CAVE):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<20} {ins.mnemonic} {ins.op_str}")
print(f"cave_dirtdelay @ {CAVE_DF:08X}  ({len(dirtdelay)} B)")
for ins in cs.disasm(dirtdelay, CAVE_DF):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<20} {ins.mnemonic} {ins.op_str}")
print(f"redirect  @ {INJ:08X}: {INJ_ORIG.hex(' ')} -> {redir.hex(' ')}")
print(f"cb-redir  @ {CB_INJ:08X}: {CB_ORIG.hex(' ')} -> {cb_redir.hex(' ')}")

APPLY = "--apply" in sys.argv
def _accepts(orig, cur):
    return cur in orig if isinstance(orig,(list,tuple)) else cur==orig
def process(path, base, patches, backup_suffix=".pre-rtlavadirt"):
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
    """cave_lavadirt's 50% roll calls the rng_sync stub. Writing that call while the stub is
    still a zeroed cave would send the roll into 0x00 bytes, so refuse rather than ship a crash."""
    data = open(p,"rb").read(); secs = load_sections(bytearray(data))
    o = mkva2off(DLL_BASE)(secs, RNG_SYNC)
    return data[o:o+8] != bytes(8)

print()
if APPLY and not stub_installed(path):
    print(f"[x] rng_sync stub @{RNG_SYNC:08X} is not installed -- the 50% roll would call into\n"
          f"    zeroed cave space. Run:  python build_scripts/build_rng_lockstep.py --apply\n"
          f"    then re-run this script.")
    sys.exit(2)
ok = process(path, DLL_BASE, dll_patches)
if not APPLY:
    print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first.")
elif ok:
    print("\n[done] Applied. Revert: undo surgically by hand -- a .pre-* restore is not a revert path.")
else:
    print("\n[!] Not applied -- see above.")
