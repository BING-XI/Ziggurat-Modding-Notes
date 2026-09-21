#!/usr/bin/env python3
r"""
AoW1 mod -- "lootmult": set the city LOOT gold multiplier (per city size). Vanilla = 9x.

MECHANISM (decoded 2026-07-12; see City_Raze_Rebellion_Design.md 2d):
Looting a captured city queues a 1-turn "loot" production (TCity.Loot @0x557AB038 -> action 5 ->
production id 0xe). The gold is awarded when that production COMPLETES during turn resolution, in
City.TCityProductionControl.NewTurn @0x557A82A8, case 5 (loot). There the loot value is computed
TWICE as  citySize x 9  (citySize = byte at TCity+0x3c):
  * the event-log message text  ("City looted for N gold")  -- IntToStr(size*9)
  * the actual gold award        -- player.gold += size*9  -> TPlayer.SetGems
Both use the 3-byte encoding  LEA reg,[reg+reg*8]  (= reg*9).

THE CHANGE: size*9 -> size*NEW_MULT at BOTH sites so the shown number matches the payout.
  Any multiplier can't be a single LEA (scale maxes at *8), but  imul reg,reg,imm8  is ALSO exactly
  3 bytes (6B /r ib), a perfect in-place swap. Register-only operands -> no .reloc hazard, no cave.

SITE 1 @0x557A8600 (message text):  8D 04 C0  LEA EAX,[EAX+EAX*8]  -> 6B C0 <m>  imul eax,eax,m
SITE 2 @0x557A86BE (gold award):    8D 14 D2  LEA EDX,[EDX+EDX*8]  -> 6B D2 <m>  imul edx,edx,m

Re-appliable: accepts as the current-state EITHER the vanilla x9 LEA OR any previously-applied
imul-at-this-site (so you can retune the multiplier without first reverting). (TCity.Loot only
queues; TCity.CanLoot is a pure bool -- no other loot-value site exists, verified.)

Idempotent; verify-before-write; dry-run by default, --apply to write (close all AoW binaries
first); auto-backup <game dir>\backups\AoWEPACK.dpl.pre-lootmult (created once = the vanilla x9
state). Re-tune in place by editing NEW_MULT and re-applying.
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

NEW_MULT = 10          # <-- the loot multiplier (vanilla 9). Must fit imm8 so imul stays 3 bytes.
assert 0 < NEW_MULT < 128, "multiplier must be a positive imm8 (imul r32,r32,imm8 = 3 bytes)"

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

# ---- the two x9 sites (LEA reg,[reg+reg*8]); modrm identifies the site's dest register ----
SITE1 = 0x557A8600; LEA1 = bytes.fromhex("8d 04 c0"); MODRM1 = 0xC0   # lea eax,[eax+eax*8]  (msg)
SITE2 = 0x557A86BE; LEA2 = bytes.fromhex("8d 14 d2"); MODRM2 = 0xD2   # lea edx,[edx+edx*8]  (gold)

imul_eax,_ = ks.asm(f"imul eax, eax, {NEW_MULT}", SITE1); imul_eax = bytes(imul_eax)
imul_edx,_ = ks.asm(f"imul edx, edx, {NEW_MULT}", SITE2); imul_edx = bytes(imul_edx)
assert len(imul_eax) == 3 and imul_eax[:2] == bytes([0x6B, MODRM1]), imul_eax.hex(' ')
assert len(imul_edx) == 3 and imul_edx[:2] == bytes([0x6B, MODRM2]), imul_edx.hex(' ')

def prior_forms(lea, modrm):
    # acceptable current bytes to overwrite: vanilla x9 LEA, OR any earlier imul reg,reg,imm8 here
    return [lea] + [bytes([0x6B, modrm, m]) for m in range(1, 128)]

patches = [
    (SITE1, prior_forms(LEA1, MODRM1), imul_eax, f"loot event-log message: size*9 -> size*{NEW_MULT}"),
    (SITE2, prior_forms(LEA2, MODRM2), imul_edx, f"loot gold award: size*9 -> size*{NEW_MULT}"),
]

print(f"loot multiplier -> {NEW_MULT}x (city LOOT gold = citySize x {NEW_MULT})")
for tag, va, new in [("msg ", SITE1, imul_eax), ("gold", SITE2, imul_edx)]:
    ins = next(cs.disasm(new, va))
    print(f"  {tag} @{va:08X} -> {new.hex(' ')} ({ins.mnemonic} {ins.op_str})")

APPLY = "--apply" in sys.argv
def _accepts(prior, cur): return cur in prior if isinstance(prior,(list,tuple)) else cur==prior
path = os.path.join(GAME, "AoWEPACK.dpl")
data = bytearray(open(path,"rb").read())
secs = load_sections(data)
def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
if all(rd(va,len(new))==new for va,_p,new,_d in patches):
    print(f"\n[= ] AoWEPACK.dpl: already applied ({NEW_MULT}x)"); sys.exit(0)
ok=True
for va,prior,new,desc in patches:
    cur=rd(va,len(new))
    if not _accepts(prior,cur) and cur!=new:
        ok=False; print(f"[!] {va:08X} ({desc})\n     got {cur.hex(' ')} (not the vanilla LEA nor an imul at this site)")
if not ok:
    print("[x] originals mismatch -- not written"); sys.exit(1)
if not APPLY:
    print("\n[dry] current state accepted. Re-run with --apply to write (close all AoW binaries)."); sys.exit(0)
os.makedirs(BACKUP_DIR, exist_ok=True)
bak = os.path.join(BACKUP_DIR, os.path.basename(path) + ".pre-lootmult")
if not os.path.exists(bak):
    shutil.copy2(path, bak); print(f"[bak] {bak}")
for va,prior,new,desc in patches:
    o=va2off(secs,va); data[o:o+len(new)]=new; print(f"[w ] {va:08X} {desc}")
try:
    open(path,"wb").write(data)
except PermissionError:
    print("[x] AoWEPACK.dpl LOCKED -- close all AoW binaries and retry"); sys.exit(1)
print(f"[done] Applied lootmult ({NEW_MULT}x). Re-tune by editing NEW_MULT + --apply (rewrites in place);\n"
          f"       a .pre-* restore is not a revert path.")
