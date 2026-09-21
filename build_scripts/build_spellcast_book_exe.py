#!/usr/bin/env python3
r"""
AoW1 Unit Spellcasting -- UI: hide too-high-tier spells from the casting book.
Patches the canonical mod exes `Ziggurat\AoWz.exe` AND `Ziggurat\AoWzCompat.exe` (names from
`zigexe.py`).  ⚠ Follow --apply with ⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)

Why this and not the DLL: the "Cast Global Spell" book is filled by the exe calling
TPlayerMagicControl.ListSpells DIRECTLY (import thunk 0x402654) -- it never routes through
THero.ListSpells (the exe doesn't even import it). So the earlier DLL-side list filter was inert.
The exe's book-population sites derive their spell list from the *player's* researched spells and
carry no caster level -- BUT the current caster IS stored in the window object at [window+0x22C]
(proven: the CastSpell / CanCastSpellInstantly sites in the same functions call
THero.CastSpell([window+0x22C], ...)). At every ListSpells call site EDX = &collector =
window+0x224, so caster = [EDX+8].

Fix: redirect each `call 0x402654` (5 sites) to a cave that (a) runs the real ListSpells to fill
the collector, then (b) reads caster = [EDX+8], and prunes the collector's TSpellList in place
(compaction, no DLL calls), dropping a spell when EITHER:
  - its tier (TSpell+0x21) exceeds the caster's Spellcasting level (GetAbilityLevel(0x34) via
    vtable +0x144); OR
  - it is a **Cosmos** spell (sphere byte TSpell+0x20 == 0) AND the caster is NOT hero-family.
"Hero-family" = IsClass(caster, THero) [exe classref [0x45DFC4], @IsClass 0x401070], which is true
for THero *and* its subclass TLeader (the player's wizard) -- so heroes and the leader keep Cosmos,
only true units (TUnit/TAdjustableUnit) lose it. (Sphere 0 = Cosmos confirmed via
TLeader.GetSpherePicks @0x5578B17C: GetSpherePicks(0) hard-returns 4 = the "researchable regardless
of sphere picks" rule.) Consistent with the M2 CanCastSpell gate; this is the UX/enforcement layer
for humans. NOTE: the AI lists via TPlayerMagicControl.ListSpells directly (not this cave), so a
DLL-side Cosmos gate would be needed to also stop AI units -- not done (see polish doc).

Cave lives in the existing ".sc" section (added by build_spellcast_card_v2.py) -- so this patch
DEPENDS on the card patch being applied. Revert: NOT by snapshot -- *.pre-bookfilter is layer 2/8 on
the exes (costs 6 features) and *.pre-cardv2 is layer 1/8 (costs 7). Undo surgically instead; to change
the cave, rewrite it in place rather than reverting.

TSpellList layout: [+4]=inner TList; TList[+8]=count, TList[+4]=items (dword array of TSpell*).
Idempotent, verify-before-write, backs up first. Dry-run by default; --apply to write.
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                       # mod binary names (AoWz.exe / AoWzCompat.exe)
EXES = list(zigexe.EXES)
BACKUP_DIR = os.path.join(GAME, "backups")   # ⚠ backups/, never the game root -- rule 2026-09-03

IB = 0x00400000
THUNK  = 0x00402654                                   # call TPlayerMagicControl.ListSpells (import thunk)
SITES  = [0x0042F0F9, 0x0042F20C, 0x00430D58, 0x00430DDE, 0x00430EDD]
SC_VA  = 0x0060C000                                   # ".sc" section (card cave lives at +0)
CAVE_VA= 0x0060C0A8                                   # after the ~0xA1 card cave, 8-aligned
GETLEVEL_SLOT = 0x144                                 # unit vtable +0x144 = GetAbilityLevel(edx=id)->al
SPELLCASTING  = 0x34
THERO_CLASSREF = 0x0045DFC4                            # [.] = THero class reference (exe IAT); IsClass edx=this
ISCLASS        = 0x00401070                            # System.@IsClass(eax=obj, edx=class) -> al  (thunk)
# TSpell fields: +0x20 = sphere (0 = Cosmos), +0x21 = research tier (1..4)

ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

# cave: entered via redirected `call 0x402654`. in: eax=magic, edx=&collector, cl=mask.
# Runs the real ListSpells, then prunes the collector's TSpellList in place, dropping any spell
# whose tier (TSpell+0x21) > caster level, OR that is Cosmos (sphere 0) when the caster is NOT
# a hero-family object (IsClass THero covers THero + TLeader; a unit is neither -> loses Cosmos).
# EBP frame locals: [ebp-4]=&collector, [ebp-8]=heroFamily(1/0), [ebp-0xC]=level.
cave_src = f"""
    push ebp
    mov ebp, esp
    sub esp, 0x0C
    push ebx
    push esi
    push edi
    mov [ebp-4], edx
    call 0x{THUNK:X}
    mov edx, [ebp-4]
    mov eax, [edx+8]
    test eax, eax
    jz _done
    mov edx, dword ptr [0x{THERO_CLASSREF:X}]
    call 0x{ISCLASS:X}
    movzx eax, al
    mov [ebp-8], eax
    mov eax, [ebp-4]
    mov eax, [eax+8]
    mov ecx, [eax]
    mov edx, 0x{SPELLCASTING:X}
    call dword ptr [ecx+0x{GETLEVEL_SLOT:X}]
    movzx eax, al
    mov [ebp-0xC], eax
    mov edx, [ebp-4]
    mov esi, [edx]
    mov esi, [esi+4]
    mov ebx, [esi+4]
    xor eax, eax
    xor edx, edx
_loop:
    cmp eax, [esi+8]
    jge _wb
    mov ecx, [ebx+eax*4]
    movzx edi, byte ptr [ecx+0x21]
    cmp edi, [ebp-0xC]
    jg _skip
    cmp dword ptr [ebp-8], 0
    jne _keep
    cmp byte ptr [ecx+0x20], 0
    je _skip
_keep:
    mov [ebx+edx*4], ecx
    inc edx
_skip:
    inc eax
    jmp _loop
_wb:
    mov [esi+8], edx
_done:
    pop edi
    pop esi
    pop ebx
    mov esp, ebp
    pop ebp
    ret
"""
cave = bytes(ks.asm(cave_src, CAVE_VA)[0])

print(f"cave_bookfilter @ {CAVE_VA:08X}  ({len(cave)} bytes)  ends {CAVE_VA+len(cave):08X}")
for ins in cs.disasm(cave, CAVE_VA):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<22} {ins.mnemonic} {ins.op_str}")
print()

def load_secs(d):
    e=struct.unpack_from('<I',d,0x3C)[0]; nsec=struct.unpack_from('<H',d,e+6)[0]
    optsz=struct.unpack_from('<H',d,e+20)[0]; opt=e+24; sect=opt+optsz
    secs=[]
    for i in range(nsec):
        b=sect+i*40; nm=d[b:b+8].rstrip(b'\0').decode('latin1')
        vs,va,rs,raw=struct.unpack_from('<IIII',d,b+8); secs.append((nm,va,vs,raw,rs,b))
    return secs
def va2off(secs,va):
    r=va-IB
    for nm,v,vs,raw,rs,b in secs:
        if v<=r<v+max(vs,rs): return raw+(r-v)
    raise ValueError(hex(va))
def rel(s,dd): return struct.pack('<i', dd-(s+5))

def process(exe):
    path=os.path.join(GAME,exe)
    # ⚠ backups/, never the game root -- rule 2026-09-03.
    backup=os.path.join(BACKUP_DIR, exe+".pre-bookfilter")
    d=bytearray(open(path,'rb').read()); secs=load_secs(d)
    sc=[s for s in secs if s[0]=='.sc']
    if not sc:
        print(f"{exe}: ABORT -- no '.sc' section (run build_spellcast_card_v2.py first)."); return False
    _,scva,scvs,scraw,scrs,schdr = sc[0]
    cave_off = scraw + (CAVE_VA - (IB+scva))
    if cave_off + len(cave) > scraw + scrs:
        print(f"{exe}: ABORT -- cave overflows .sc raw."); return False
    # patch table: 5 site redirects + the cave body
    patches=[]
    for s in SITES:
        patches.append((va2off(secs,s), b"\xE8"+rel(s,THUNK), b"\xE8"+rel(s,CAVE_VA), f"site {s:08X}"))
    patches.append((cave_off, bytes(len(cave)), cave, f"cave @ {CAVE_VA:08X}"))
    ok=True; already=0; todo=0
    for off,orig,new,desc in patches:
        cur=bytes(d[off:off+len(orig)])
        if cur==new: already+=1
        elif cur==orig: todo+=1
        else:
            print(f"{exe}: MISMATCH {desc}: exp {orig.hex(' ')} found {cur.hex(' ')}"); ok=False
    print(f"{exe}: {already} already, {todo} to patch, {len(patches)} total  (.sc vsz {scvs:X})")
    if not ok: return False
    if '--apply' not in sys.argv: return True
    # ⚠ SNAPSHOT ONLY FROM A FILE PROVED UNPATCHED. "no backup file yet" is not that proof --
    # it accepts this script's own past output, and after the 2026-09-09 rename no
    # AoWz.exe.pre-bookfilter can exist, so the old gate would have minted a ".pre-" holding
    # the PATCHED state under an authoritative-looking name. todo==len(patches) is the
    # positive test: every site still carries its original bytes.
    if todo != len(patches):
        print(f"  no backup taken ({already} sites already patched -- a .pre-* of a patched file is a lie)")
    elif not os.path.exists(backup):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copyfile(path,backup); print(f"  backup {backup}")
    for off,orig,new,desc in patches: d[off:off+len(new)]=new
    # grow .sc VirtualSize to cover the cave, if needed
    need = (CAVE_VA - (IB+scva)) + len(cave)
    if scvs < need: struct.pack_into('<I', d, schdr+8, need); print(f"  .sc vsz {scvs:X}->{need:X}")
    open(path,'wb').write(d); print(f"  {exe}: book filter applied.")
    return True

allok=all(process(e) for e in EXES)
if '--apply' not in sys.argv and allok: print("\nDry run OK. Re-run with --apply to write.")
